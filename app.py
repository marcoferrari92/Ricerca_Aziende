import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3
import time
import random

# Disabilita avvisi SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import moduli locali
from mapping import ATECO_MAP 
from utils import fetch_data_google, scrape_sito_aziendale, estrai_testo_finanziario

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor Pro", page_icon="🏭")

# --- INIZIALIZZAZIONE SESSION STATE ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.4642, 'lon': 9.1900} 
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()
if 'crawler_log' not in st.session_state:
    st.session_state.crawler_log = ""
if 'debug_text_log' not in st.session_state:
    st.session_state.debug_text_log = ""
if 'summary_log' not in st.session_state:
    st.session_state.summary_log = ""

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔑 Accesso API")
    user_api_key = st.text_input("Google API Key", type="password", key="google_key")
    openai_api_key = st.text_input("OpenAI API Key", type="password", key="openai_key")
    
    st.divider()
    st.header("⚙️ Parametri")
    raggio = st.slider("Raggio Scansione (KM)", 1, 50, 5)
    scelte = st.multiselect("Settori (ATECO)", options=list(ATECO_MAP.keys()))
    max_test = st.number_input("Limite Risultati", 5, 500, 20) 

    if st.button("🗑️ Svuota Database", use_container_width=True):
        st.session_state.results = pd.DataFrame()
        st.session_state.crawler_log = ""
        st.session_state.debug_text_log = ""
        st.session_state.summary_log = ""
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
        st.session_state.pos = {'lat': map_res['last_clicked']['lat'], 'lon': map_res['last_clicked']['lng']}
        st.rerun()

with col_ctrl:
    st.subheader("2. Comandi Ricerca")
    st.info(f"📍 Centro: {st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}")
    if st.button("🚀 AVVIA RICERCA GOOGLE", use_container_width=True, type="primary"):
        if not user_api_key or not scelte:
            st.warning("Inserisci API Key e seleziona un settore")
        else:
            keywords = []
            for s in scelte: keywords.extend(ATECO_MAP.get(s, [s]))
            with st.status("Ricerca su Google Maps...") as status:
                df = fetch_data_google(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, keywords, user_api_key, max_results=max_test)
                for col in ['P.IVA (Crawler)', 'Email (Crawler)', 'Fatturato (AI)', 'Dipendenti (AI)', 'testo_raw']:
                    df[col] = "N.D."
                st.session_state.results = df
                status.update(label=f"Trovate {len(df)} aziende!", state="complete")
            st.rerun()

# --- TABELLA E AZIONI ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("3. Database Risultati")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon', 'testo_raw'], errors='ignore'), use_container_width=True)
    
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    progress_placeholder = st.empty()
    log_placeholder = st.empty()

    with btn_col1:
        if st.button("🌐 1. AVVIA CRAWLER WEB", use_container_width=True):
            df_work = st.session_state.results.copy()
            bar = progress_placeholder.progress(0)
            st.session_state.crawler_log = ""
            with log_placeholder.expander("🔍 Debug Crawler", expanded=True):
                debug_area = st.empty()
                for i, (idx, row) in enumerate(df_work.iterrows()):
                    if row['Sito Web'] != 'N.D.':
                        p, e, t, d = scrape_sito_aziendale(row['Sito Web'])
                        df_work.at[idx, 'P.IVA (Crawler)'], df_work.at[idx, 'Email (Crawler)'], df_work.at[idx, 'testo_raw'] = p, e, t
                        st.session_state.crawler_log += f"**{row['Ragione Sociale']}**: {d}\n\n"
                        debug_area.markdown(st.session_state.crawler_log)
                    bar.progress((i + 1) / len(df_work))
                st.session_state.results = df_work
                st.rerun()

    with btn_col2:
        if st.button("🤖 2. VEDI COSA VEDE IL BOT", use_container_width=True, type="primary"):
            st.session_state.debug_text_log = ""
            df_work = st.session_state.results.copy()
            bar = progress_placeholder.progress(0)
            
            # Contenitore per il log in tempo reale
            with log_placeholder.expander("🔍 ISPEZIONE LIVE (Snippet DuckDuckGo)", expanded=True):
                debug_area = st.empty()

                for i, (idx, row) in enumerate(df_work.iterrows()):
                    nome = row['Ragione Sociale']
                    bar.progress((i + 1) / len(df_work), text=f"Analizzando: {nome}")
                    
                    # --- CHIAMATA A VALORE SINGOLO ---
                    testo_visto = cerca_info_finanziarie_per_nome(nome)
                    
                    # Salviamo nel log
                    st.session_state.debug_text_log += f"**AZIENDA:** {nome}\n**IL BOT VEDE:** {testo_visto}\n\n---\n"
                    
                    # Mostriamo a video
                    debug_area.markdown(st.session_state.debug_text_log)
                    
                    time.sleep(2)

            st.session_state.results = df_work
            st.success("Scansione completata!")
            # st.rerun() # Commentato per permetterti di leggere il log prima che la pagina si ricarichi

