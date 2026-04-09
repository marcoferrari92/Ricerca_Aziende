import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3

# Disabilita avvisi SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import dei moduli locali
from mapping import ATECO_MAP 
from utils import fetch_data_google, scrape_sito_aziendale, ricerca_dati_ai # <--- Aggiunta ricerca_dati_ai

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor Pro", page_icon="🏭")

# --- INIZIALIZZAZIONE SESSION STATE ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.4642, 'lon': 9.1900} 
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- SIDEBAR: CONFIGURAZIONE ---
with st.sidebar:
    st.header("🔑 Accesso API")
    user_api_key = st.text_input("Google API Key", type="password")
    openai_api_key = st.text_input("OpenAI API Key", type="password", help="Per conferma P.IVA e Dati Finanziari")
    
    st.divider()
    st.header("⚙️ Parametri")
    raggio = st.slider("Raggio Scansione (KM)", 1, 50, 5)
    scelte = st.multiselect("Settori (ATECO)", options=list(ATECO_MAP.keys()))
    max_test = st.number_input("Limite Risultati", 5, 500, 20) 

    if st.button("🗑️ Svuota Database", use_container_width=True):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- LAYOUT PRINCIPALE ---
st.title("🏭 Business Data Extractor")

col_map, col_ctrl = st.columns([2, 1])

with col_map:
    st.subheader("1. Area di Ricerca")
    m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
    folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio * 1000, color="#31333F", fill=True, opacity=0.1).add_to(m)

    if not st.session_state.results.empty:
        for _, row in st.session_state.results.iterrows():
            if pd.notnull(row['lat']) and pd.notnull(row['lon']):
                folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

    map_res = st_folium(m, width="100%", height=450, key="main_map")

    if map_res and map_res['last_clicked']:
        nl, nn = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
        if round(nl, 4) != round(st.session_state.pos['lat'], 4):
            st.session_state.pos = {'lat': nl, 'lon': nn}
            st.rerun()

with col_ctrl:
    st.subheader("2. Comandi")
    st.info(f"📍 Centro: {st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}")
    if st.button("🚀 AVVIA RICERCA GOOGLE", use_container_width=True, type="primary"):
        if not user_api_key: st.error("Inserisci la Google API Key")
        elif not scelte: st.warning("Seleziona un settore")
        else:
            keywords = []
            for s in scelte: keywords.extend(ATECO_MAP.get(s, [s]))
            with st.status("Ricerca su Google Maps...") as status:
                df = fetch_data_google(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, keywords, user_api_key, max_results=max_test)
                st.session_state.results = df
                status.update(label=f"Trovate {len(df)} aziende!", state="complete")
            st.rerun()


# --- TABELLA RISULTATI E SCRAPING ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Aziende Trovate")

    # Creiamo una copia per lo stile senza rovinare i dati originali
    df_to_show = st.session_state.results.copy()

    # Funzione per applicare il colore solo alla colonna specifica
    def apply_color(x):
        # Definiamo i due valori da confrontare
        crawled = str(x['Partita IVA']).strip()
        ai_found = str(x.get('PIVA AI', 'N.D.')).strip()
        
        # Colore base
        style_match = 'background-color: #c3e6cb; color: #155724;' # Verde chiaro
        style_error = 'background-color: #f5c6cb; color: #721c24;' # Rosso chiaro

        if crawled != "Non trovata" and crawled == ai_found:
            return [style_match if v == x['PIVA AI'] else '' for v in x]
        else:
            return [style_error if v == x['PIVA AI'] else '' for v in x]

    # Visualizzazione con lo Styler
    st.dataframe(
        df_to_show.style.apply(apply_color, axis=1),
        use_container_width=True
    )
    
    # --- PULSANTE 1: CRAWLER WEB ---
    with btn_col1:
        if st.button("🌐 1. AVVIA CRAWLER WEB", use_container_width=True):
            df_work = st.session_state.results.copy().astype(object)
            bar = st.progress(0)
            msg = st.empty()
            
            for i, (idx, row) in enumerate(df_work.iterrows()):
                if row['Sito Web'] != 'N.D.':
                    msg.text(f"Scraping Web: {row['Ragione Sociale']}...")
                    p_web, e_web = scrape_sito_aziendale(row['Sito Web'])
                    
                    # Scriviamo SOLO nelle colonne (Crawler)
                    df_work.at[idx, 'P.IVA (Crawler)'] = str(p_web)
                    df_work.at[idx, 'Email (Crawler)'] = str(e_web)
                bar.progress((i + 1) / len(df_work))
            
            st.session_state.results = df_work
            msg.success("✅ Dati Crawler salvati!")
            st.rerun()

    # --- PULSANTE 2: ANALISI AI ---
    with btn_col2:
        if st.button("🤖 2. ANALISI INTELLIGENTE AI", use_container_width=True, type="primary"):
            if not openai_api_key:
                st.error("Inserisci la OpenAI Key!")
            else:
                df_work = st.session_state.results.copy().astype(object)
                bar = st.progress(0)
                msg = st.empty()
                
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    msg.text(f"Analisi AI: {row['Ragione Sociale']}...")
                    
                    # Passiamo all'AI i dati trovati dal crawler come "suggerimento"
                    fatt, dip, p_ai = ricerca_dati_ai(
                        row['Ragione Sociale'], 
                        row['Indirizzo'], 
                        row['Sito Web'], 
                        row['P.IVA (Crawler)'], # Usiamo il dato del crawler per aiutarlo
                        openai_api_key
                    )
                    
                    # Qui dovresti avere una funzione AI che cerca anche l'email se vuoi Email (AI)
                    # Per ora popoliamo IVA, Fatturato e Dipendenti
                    df_work.at[idx, 'P.IVA (AI)'] = str(p_ai)
                    df_work.at[idx, 'Fatturato (AI)'] = str(fatt)
                    df_work.at[idx, 'Dipendenti (AI)'] = str(dip)
                    
                    bar.progress((i + 1) / len(df_work))
                
                st.session_state.results = df_work
                msg.success("✅ Dati AI salvati in colonne separate!")
                st.rerun()

    # --- PULSANTE 3: DOWNLOAD ---
    with btn_col3:
        csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
        st.download_button("📥 SCARICA DATABASE", csv, "aziende_comparate.csv", "text/csv", use_container_width=True)
        
