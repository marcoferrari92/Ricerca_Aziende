import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3

# Disabilita avvisi SSL per siti non sicuri durante lo scraping
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import dei moduli locali
# Assicurati che utils.py contenga le funzioni aggiornate (fetch_data_google, ecc.)
from mapping import ATECO_MAP 
from utils import fetch_data_google, scrape_sito_aziendale, scrape_camerale_data

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(
    layout="wide", 
    page_title="Business Data Extractor Pro",
    page_icon="🏭"
)

# --- INIZIALIZZAZIONE SESSION STATE ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.4642, 'lon': 9.1900} # Default: Milano
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- SIDEBAR: CONFIGURAZIONE ---
with st.sidebar:
    st.header("🔑 Accesso API")
    user_api_key = st.text_input("Inserisci Google API Key", type="password", help="Necessaria per Google Places")
    openai_api_key = st.text_input("OpenAI API Key", type="password", help="Necessaria per analisi avanzata AI")
    st.divider()
    
    st.header("⚙️ Parametri di Ricerca")
    raggio = st.slider("Raggio Scansione (KM)", 1, 50, 5)
    
    # Selezione codici ATECO dal file mapping.py
    scelte = st.multiselect(
        "Settori Aziendali (Codici ATECO)", 
        options=list(ATECO_MAP.keys()),
        help="Seleziona le categorie da cercare su Google Maps"
    )
    
    max_test = st.number_input("Limite Risultati (Safety)", 5, 500, 20) 

    st.divider()
    if st.button("🗑️ Svuota Database", use_container_width=True):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- LAYOUT PRINCIPALE ---
st.title("🏭 Business Data Extractor")
st.markdown("Cerca aziende nell'area selezionata ed estrai Partita IVA, Email e dati finanziari.")

col_map, col_ctrl = st.columns([2, 1])

with col_map:
    st.subheader("1. Seleziona Posizione")
    # Creazione mappa Folium
    m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
    
    # Cerchio che indica il raggio di ricerca
    folium.Circle(
        location=[st.session_state.pos['lat'], st.session_state.pos['lon']], 
        radius=raggio * 1000, 
        color="#31333F", 
        fill=True, 
        opacity=0.1
    ).add_to(m)

    # Aggiungi marker se ci sono risultati
    if not st.session_state.results.empty:
        for _, row in st.session_state.results.iterrows():
            if pd.notnull(row['lat']) and pd.notnull(row['lon']):
                folium.Marker(
                    [row['lat'], row['lon']], 
                    tooltip=row['Ragione Sociale'],
                    icon=folium.Icon(color='blue', icon='briefcase', prefix='fa')
                ).add_to(m)

    # Visualizzazione mappa con gestione click
    map_res = st_folium(m, width="100%", height=450, key="main_map")

    # Gestione dello spostamento del centro mappa (con soglia di tolleranza)
    if map_res and map_res['last_clicked']:
        click_lat = map_res['last_clicked']['lat']
        click_lon = map_res['last_clicked']['lng']
        
        if round(click_lat, 4) != round(st.session_state.pos['lat'], 4):
            st.session_state.pos = {'lat': click_lat, 'lon': click_lon}
            st.rerun()

with col_ctrl:
    st.subheader("2. Esegui Ricerca")
    st.info(f"📍 **Coordinate:**\n{st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}")
    
    search_btn = st.button("🚀 AVVIA RICERCA GOOGLE", use_container_width=True, type="primary")
    
    if search_btn:
        if not user_api_key:
            st.error("⚠️ Errore: Inserisci la API Key nella sidebar.")
        elif not scelte:
            st.warning("⚠️ Seleziona almeno un settore ATECO.")
        else:
            # Prepara le keyword dalle liste nel mapping
            keywords_finali = []
            for s in scelte:
                keywords_finali.extend(ATECO_MAP.get(s, [s]))
            
            with st.status("Interrogazione Google Places...", expanded=True) as status:
                df_google = fetch_data_google(
                    st.session_state.pos['lat'], 
                    st.session_state.pos['lon'], 
                    raggio, 
                    keywords_finali, 
                    user_api_key, 
                    max_results=max_test
                )
                st.session_state.results = df_google
                status.update(label=f"Trovate {len(df_google)} aziende!", state="complete", expanded=False)
            st.rerun()

# --- TABELLA RISULTATI E SCRAPING ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader(f"3. Risultati ({len(st.session_state.results)} Record)")
    
    # Visualizziamo solo le colonne utili (escludiamo coordinate per pulizia)
    cols_to_show = [c for c in st.session_state.results.columns if c not in ['lat', 'lon']]
    st.dataframe(st.session_state.results[cols_to_show], use_container_width=True)

    c1, c2 = st.columns(2)
    
    with c1:
        if st.button("🔍 ARRICCHISCI DATI (Email + P.IVA)", use_container_width=True):
            df_work = st.session_state.results.copy()
            bar = st.progress(0)
            msg = st.empty()
            
            for i, (idx, row) in enumerate(df_work.iterrows()):
                if row['Sito Web'] != 'N.D.':
                    msg.text(f"Scraping in corso: {row['Ragione Sociale']}...")
                    piva, email = scrape_sito_aziendale(row['Sito Web'])
                    
                    df_work.at[idx, 'Partita IVA'] = piva
                    df_work.at[idx, 'Email'] = email
                    
                    # Se abbiamo una P.IVA valida, proviamo i dati camerali
                    piva_clean = "".join(filter(str.isdigit, str(piva)))
                    if len(piva_clean) == 11:
                        fatt, dip = scrape_camerale_data(piva_clean)
                        df_work.at[idx, 'Fatturato'] = fatt
                        df_work.at[idx, 'Dipendenti'] = dip
                
                bar.progress((i + 1) / len(df_work))
            
            st.session_state.results = df_work
            msg.success("✅ Arricchimento completato!")
            st.rerun()

    with c2:
        # Generazione CSV per download
        csv_data = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
        st.download_button(
            "📥 SCARICA DATABASE CSV", 
            data=csv_data, 
            file_name="estrazione_aziende.csv", 
            mime="text/csv",
            use_container_width=True
        )




