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
from utils import fetch_data

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor")

# --- 2. GESTIONE STATO ---
if 'results' not in st.session_state: 
    st.session_state.results = pd.DataFrame()
if 'pos' not in st.session_state: 
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}

# --- 3. FUNZIONI DI SCRAPING (Spostate qui per evitare NameError) ---

def scrape_sito_aziendale(url):
    """FASE 1: Cerca P.IVA ed Email sul sito ufficiale."""
    if not url or url == 'N.D.': return "N.D.", "N.D.", "N.D."
    if not url.startswith('http'): url = 'http://' + url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        testo = soup.get_text()
        
        piva = re.search(r'\b\d{11}\b', testo)
        email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
        fatt = re.search(r'fatturato[:\s]*([\d.,]+\s*(?:€|euro|milioni|mln))', testo, re.I)
        
        return (piva.group(0) if piva else "N.D.", 
                email.group(0) if email else "N.D.",
                fatt.group(1) if fatt else "N.D.")
    except: return "Errore", "N.D.", "N.D."

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


# --- 4. INTERFACCIA ---
st.title("🏭 Business Intelligence Veneto")

with st.sidebar:
    st.header("Filtri")
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori", list(ATECO_MAP.keys()))
    if st.button("Reset"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- MAPPA INTERATTIVA ---
st.subheader("1. Area di Ricerca")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], 
              radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_data = st_folium(m, width="100%", height=400, key="main_map")

if map_data and map_data.get('last_clicked'):
    nl, ng = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
    if abs(nl - st.session_state.pos['lat']) > 0.001:
        st.session_state.pos = {'lat': nl, 'lon': ng}
        st.rerun()

if st.button("🚀 CERCA AZIENDE", use_container_width=True):
    if scelte:
        with st.spinner("Ricerca in corso..."):
            st.session_state.results = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
            st.rerun()
    else:
        st.warning("Seleziona almeno un settore!")


# --- 5. IL BLOCCO DEI PULSANTI (Dove avevi l'errore) ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Risultati e Arricchimento")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🌐 FASE 1: CERCA P.IVA SUI SITI", use_container_width=True):
            df = st.session_state.results.copy()
            if 'Capitale Sociale' not in df.columns: df['Capitale Sociale'] = 'N.D.'
            bar = st.progress(0)
            for i, row in df.iterrows():
                p, e, f, c = scrape_sito_aziendale(row['Sito Web']) # <--- ORA LA TROVA!
                df.at[i, 'Partita IVA'] = p
                if row.get('Email') == 'N.D.': df.at[i, 'Email'] = e
                df.at[i, 'Fatturato'] = f
                df.at[i, 'Capitale Sociale'] = c
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()

    with c2:
        if st.button("📊 FASE 2: DATI CAMERALI", use_container_width=True):
            df = st.session_state.results.copy()
            if 'Dipendenti' not in df.columns: df['Dipendenti'] = 'N.D.'
            bar = st.progress(0)
            for i, row in df.iterrows():
                piva = str(row.get('Partita IVA', 'N.D.'))
                if len(piva) == 11:
                    fc, d = scrape_portale_camerale(piva)
                    df.at[i, 'Fatturato'] = fc
                    df.at[i, 'Dipendenti'] = d
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()


