import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import re
from bs4 import BeautifulSoup
import time

# Import delle componenti esterne
from mapping import ATECO_MAP 
from utils import fetch_data, scrape_sito_aziendale

# --- CONFIGURAZIONE E STATO ---
st.set_page_config(layout="wide", page_title="Business Data Extractor")
if 'results' not in st.session_state: st.session_state.results = pd.DataFrame()
if 'pos' not in st.session_state: st.session_state.pos = {'lat': 45.547, 'lon': 11.545}

# --- 3. FUNZIONI DI SCRAPING (Spostate qui per evitare NameError) ---
def scrape_portale_camerale(piva):
    """FASE 2: Estrazione basata sulla struttura dello screenshot."""
    if piva in ["N.D.", "Errore", "Non trovata"] or len(piva) != 11:
        return "N.D.", "N.D."
    
    url = f"https://www.reportaziende.it/ricerca?q={piva}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        time.sleep(2)
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        # Se non siamo nella scheda, clicchiamo il primo link
        if "Dati della società" not in res.text:
            link = soup.find('a', href=re.compile(r'/azienda/'))
            if link:
                res = requests.get("https://www.reportaziende.it" + link['href'], headers=headers)
                soup = BeautifulSoup(res.text, 'html.parser')

        testo = soup.get_text(separator='|', strip=True)
        fatt_match = re.search(r'Fatturato[:\s]*€?\s*([\d.,]+)', testo, re.I)
        dip_match = re.search(r'Dipendenti[:\s]*(\d+)', testo, re.I)

        return (f"€ {fatt_match.group(1)}" if fatt_match else "Vedi online", 
                dip_match.group(1) if dip_match else "N.D.")
    except:
        return "Errore", "Errore"


# --- 3. INTERFACCIA ---

if 'results' not in st.session_state: st.session_state.results = pd.DataFrame()
if 'pos' not in st.session_state: st.session_state.pos = {'lat': 45.547, 'lon': 11.545}

st.title("🏭 Business Intelligence Pro")

with st.sidebar:
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori", list(ATECO_MAP.keys()))
    if st.button("Reset"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# Sezione 1: Mappa e Ricerca
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
st_folium(m, width="100%", height=300)

if st.button("🚀 1. TROVA AZIENDE NELL'AREA", use_container_width=True):
    st.session_state.results = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
    st.rerun()

# Sezione 2: Elaborazione Dati
if not st.session_state.results.empty:
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🌐 2. SCANSIONA SITI (P.IVA + EMAIL)", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
            for i, row in df.iterrows():
                p, e, f = scrape_sito_aziendale(row['Sito Web'])
                df.at[i, 'Partita IVA'] = p
                if row['Email'] == 'N.D.': df.at[i, 'Email'] = e
                df.at[i, 'Fatturato (da sito)'] = f
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()
            
    with col2:
        # Il secondo pulsante funziona solo se abbiamo trovato almeno una P.IVA
        if st.button("📊 3. RICERCA CAMERALE (BILANCI)", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
            for i, row in df.iterrows():
                f_c, d = scrape_portale_camerale(row['Partita IVA'])
                df.at[i, 'Fatturato (Camerale)'] = f_c
                df.at[i, 'Dipendenti'] = d
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 SCARICA DATABASE CSV", csv, "aziende_bi_veneto.csv", "text/csv")
