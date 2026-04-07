
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import re
from bs4 import BeautifulSoup
import time

# Disabilita gli avvisi fastidiosi per i siti senza certificato sicuro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import delle componenti esterne
from mapping import ATECO_MAP 
from utils import fetch_data, scrape_sito_aziendale, scrape_camerale_data

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor")

# --- GESTIONE STATO ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- INTERFACCIA UTENTE ---
st.title("🏭 Business Data Extractor")
st.markdown("Trova aziende sulla mappa e arricchisci i dati con **P.IVA**, **Email**, **Fatturato** e **Dipendenti**.")

with st.sidebar:
    st.header("⚙️ Filtri Ricerca")
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali", list(ATECO_MAP.keys()))
    
    if st.button("🗑️ Reset Database"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

st.subheader("1. Seleziona area e scansiona")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="100%", height=400, key="map_bi")

if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if abs(new_lat - st.session_state.pos['lat']) > 0.0001:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

if st.button("🚀 TROVA AZIENDE NELL'AREA", use_container_width=True):
    if not scelte:
        st.warning("Seleziona almeno un settore dalla barra laterale!")
    else:
        with st.spinner("Scansione OpenStreetMap in corso..."):
            df = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
            st.session_state.results = df
            st.rerun()

# --- RISULTATI E SCRAPING AVANZATO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Aziende Trovate")
    # Escludiamo lat e lon dalla visualizzazione
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon'], errors='ignore'), use_container_width=True)

    st.subheader("3. Arricchimento Profondo (Web Crawler)")
    st.info("Questo processo cercherà la P.IVA sui siti aziendali e recupererà il bilancio.")
    
    if st.button("🔍 ESTRAI DATI COMPLETI (P.IVA + BILANCIO)", use_container_width=True):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status_msg = st.empty()
        
        count = len(df_work)
        for i, row in df_work.iterrows():
            if row['Sito Web'] != 'N.D.':
                status_msg.text(f"Analisi: {row['Ragione Sociale']}...")
                
                # --- STEP 1: CHIAMATA ALLA TUA FUNZIONE (2 VALORI) ---
                # Questa riga ora è corretta perché riceve piva ed email
                piva, email_web = scrape_sito_aziendale(row['Sito Web'])
                
                df_work.at[i, 'Partita IVA'] = piva
                
                # Aggiorna l'email solo se quella di base è N.D.
                if row.get('Email') == 'N.D.':
                    df_work.at[i, 'Email'] = email_web
                
                # --- STEP 2: BILANCIO (SOLO SE P.IVA È VALIDA) ---
                piva_clean = str(piva).strip()
                if piva_clean not in ["Non trovata", "Errore Sito", "N.D."] and len(piva_clean) == 11:
                    # Questa funzione deve restituire 2 valori: fatt e dip
                    fatt, dip = scrape_camerale_data(piva_clean)
                    df_work.at[i, 'Fatturato'] = fatt
                    df_work.at[i, 'Dipendenti'] = dip
            
            progress_bar.progress((i + 1) / count)
        
        # Salvataggio finale
        st.session_state.results = df_work
        status_msg.success("✅ Arricchimento completato!")
        st.rerun()
        

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database Finale (CSV)", csv, "database_aziende.csv", "text/csv")
