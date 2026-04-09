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
    st.subheader(f"3. Gestione Risultati ({len(st.session_state.results)} aziende)")
    
    view_cols = [c for c in st.session_state.results.columns if c not in ['lat', 'lon']]
    st.dataframe(st.session_state.results[view_cols], use_container_width=True)

    # Creiamo tre colonne per i pulsanti
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    
    # --- PULSANTE 1: CRAWLER WEB (Email + P.IVA grezza) ---
    with btn_col1:
        if st.button("🌐 1. AVVIA CRAWLER WEB", use_container_width=True, help="Estrae Email e P.IVA navigando il sito (Gratis)"):
            df_work = st.session_state.results.copy().astype(object)
            bar = st.progress(0)
            msg = st.empty()
            
            for i, (idx, row) in enumerate(df_work.iterrows()):
                if row['Sito Web'] != 'N.D.':
                    msg.text(f"Navigazione sito: {row['Ragione Sociale']}...")
                    p_web, e_web = scrape_sito_aziendale(row['Sito Web'])
                    df_work.at[idx, 'Partita IVA'] = str(p_web)
                    df_work.at[idx, 'Email'] = str(e_web)
                bar.progress((i + 1) / len(df_work))
            
            st.session_state.results = df_work
            msg.success("✅ Web Scraping completato!")
            st.rerun()

    # --- PULSANTE 2: ANALISI AI (Fatturato + Conferma) ---
    with btn_col2:
        if st.button("🤖 2. ANALISI INTELLIGENTE AI", use_container_width=True, type="primary", help="Usa OpenAI per Fatturato, Dipendenti e validazione P.IVA"):
            if not openai_api_key:
                st.error("Inserisci la OpenAI Key nella sidebar!")
            else:
                df_work = st.session_state.results.copy().astype(object)
                bar = st.progress(0)
                msg = st.empty()
                
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    msg.text(f"Elaborazione AI: {row['Ragione Sociale']}...")
                    
                    # Usa la funzione AI passando i dati già raccolti dal crawler (se presenti)
                    fatt, dip, p_final = ricerca_dati_ai(
                        row['Ragione Sociale'], 
                        row['Indirizzo'], 
                        row['Sito Web'], 
                        row.get('Partita IVA', 'N.D.'), 
                        openai_api_key
                    )
                    
                    df_work.at[idx, 'Fatturato'] = str(fatt)
                    df_work.at[idx, 'Dipendenti'] = str(dip)
                    df_work.at[idx, 'Partita IVA'] = str(p_final)
                    
                    bar.progress((i + 1) / len(df_work))
                
                st.session_state.results = df_work
                msg.success("✅ Analisi AI completata!")
                st.rerun()

    # --- PULSANTE 3: DOWNLOAD ---
    with btn_col3:
        csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
        st.download_button(
            "📥 SCARICA DATABASE CSV", 
            data=csv, 
            file_name="leads_aziende.csv", 
            mime="text/csv", 
            use_container_width=True
        )
