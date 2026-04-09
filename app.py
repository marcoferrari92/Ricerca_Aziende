import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3

# Disabilita avvisi SSL per evitare log fastidiosi
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import dei moduli locali (Assicurati che utils.py contenga fetch_data_google, scrape_sito_aziendale, chiedi_a_openai)
from mapping import ATECO_MAP 
from utils import fetch_data_google, scrape_sito_aziendale, chiedi_a_openai

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
    openai_api_key = st.text_input("OpenAI API Key", type="password", help="Per P.IVA, Fatturato e Dipendenti")
    
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
        st.session_state.pos = {'lat': nl, 'lon': nn}
        st.rerun()

with col_ctrl:
    st.subheader("2. Comandi Ricerca")
    st.info(f"📍 Centro: {st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}")
    if st.button("🚀 AVVIA RICERCA GOOGLE", use_container_width=True, type="primary"):
        if not user_api_key: st.error("Inserisci la Google API Key")
        elif not scelte: st.warning("Seleziona un settore")
        else:
            keywords = []
            for s in scelte: keywords.extend(ATECO_MAP.get(s, [s]))
            with st.status("Ricerca su Google Maps...") as status:
                df = fetch_data_google(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, keywords, user_api_key, max_results=max_test)
                
                # Inizializziamo le colonne vuote per evitare errori di visualizzazione
                cols_to_add = ['P.IVA (Crawler)', 'Email (Crawler)', 'P.IVA (AI)', 'Fatturato (AI)', 'Dipendenti (AI)', 'Nota/Fonte (AI)']
                for col in cols_to_add:
                    df[col] = "N.D."
                
                st.session_state.results = df
                status.update(label=f"Trovate {len(df)} aziende!", state="complete")
            st.rerun()

# --- TABELLA RISULTATI E ARRICCHIMENTO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("3. Database Risultati")
    
    # Tabella pulita senza stili CSS/Colori
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon'], errors='ignore'), use_container_width=True)
    
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button("🌐 1. AVVIA CRAWLER WEB", use_container_width=True):
            df_work = st.session_state.results.copy()
            bar = st.progress(0)
            msg = st.empty()
            
            for i, (idx, row) in enumerate(df_work.iterrows()):
                if row['Sito Web'] != 'N.D.':
                    msg.text(f"Scraping: {row['Ragione Sociale']}...")
                    p_web, e_web = scrape_sito_aziendale(row['Sito Web'])
                    df_work.at[idx, 'P.IVA (Crawler)'] = str(p_web)
                    df_work.at[idx, 'Email (Crawler)'] = str(e_web)
                bar.progress((i + 1) / len(df_work))
            
            st.session_state.results = df_work
            msg.success("✅ Dati Crawler completati!")
            st.rerun()

    with btn_col2:
        if st.button("🤖 2. ANALISI INTELLIGENTE AI", use_container_width=True, type="primary"):
            if not openai_api_key:
                st.error("Inserisci la OpenAI Key!")
            else:
                df_work = st.session_state.results.copy()
                bar = st.progress(0)
                msg = st.empty()
                
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    msg.text(f"AI Audit: {row['Ragione Sociale']}...")
                    
                    # Chiamata alla tua funzione che restituisce 4 valori
                    # (Assicurati che utils.py sia aggiornato per ritornare anche piva_ai)
                    fatt, dip, piva_ai, fonte = chiedi_a_openai(
                        row['Ragione Sociale'], 
                        row['P.IVA (Crawler)'], 
                        row['Sito Web'], 
                        openai_api_key
                    )
                    
                    # Assegnazione alle colonne AI
                    df_work.at[idx, 'Fatturato (AI)'] = str(fatt)
                    df_work.at[idx, 'Dipendenti (AI)'] = str(dip)
                    df_work.at[idx, 'P.IVA (AI)'] = str(piva_ai)
                    df_work.at[idx, 'Nota/Fonte (AI)'] = str(fonte)
                    
                    bar.progress((i + 1) / len(df_work))
                
                st.session_state.results = df_work
                msg.success("✅ Analisi AI completata!")
                st.rerun()

    with btn_col3:
        # Download finale del CSV
        csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
        st.download_button("📥 SCARICA DATABASE CSV", csv, "aziende_export.csv", "text/csv", use_container_width=True)
