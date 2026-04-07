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

# --- 1. CONFIGURAZIONE ---
st.set_page_config(layout="wide", page_title="BI Extractor Veneto")

# --- 2. FUNZIONI DI SCRAPING ---

def fetch_data(lat, lon, raggio_km, macrosettori):
    """Ricerca iniziale su OpenStreetMap (Inalterata)"""
    url = "https://overpass-api.de/api/interpreter"
    raggio_m = int(raggio_km * 1000)
    filtri = ""
    for ms in macrosettori:
        for t in ATECO_MAP.get(ms, []):
            filtri += f"nwr{t}(around:{raggio_m},{lat},{lon});\n"
    query = f"[out:json][timeout:90];({filtri});out tags center;"
    try:
        r = requests.get(url, params={'data': query}, timeout=100)
        elements = r.json().get('elements', [])
        ris = [] 
        for e in elements:
            t = e.get('tags', {})
            if 'name' in t:
                lat_res = e.get('lat') or e.get('center', {}).get('lat')
                lon_res = e.get('lon') or e.get('center', {}).get('lon')
                if lat_res and lon_res:
                    ris.append({
                        'Ragione Sociale': t.get('name', 'N.D.').strip(),
                        'Sito Web': t.get('website') or t.get('contact:website') or 'N.D.',
                        'Email': t.get('email') or 'N.D.',
                        'Partita IVA': 'N.D.',
                        'Fatturato (da sito)': 'N.D.',
                        'Fatturato (Camerale)': 'N.D.',
                        'Dipendenti': 'N.D.',
                        'lat': lat_res, 'lon': lon_res
                    })
        return pd.DataFrame(ris)
    except: return pd.DataFrame()

def scrape_sito_aziendale(url):
    """Cerca P.IVA ed Email sul sito ufficiale."""
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
    """Cerca dati ufficiali con Regex potenziata."""
    if piva in ["N.D.", "Errore", "Non trovata"] or len(piva) != 11:
        return "N.D.", "N.D."
    url = f"https://www.reportaziende.it/ricerca?q={piva}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0'}
        time.sleep(1.5)
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        testo = soup.get_text(separator=' ')
        # Regex flessibile per il fatturato
        fatt_pattern = r'fatturato\s*(?:\d{4})?[:\s-]*([€\d.,\s]+(?:milioni|mila|mln|k|euro|€)?)'
        dip_pattern = r'dipendenti[:\s-]*(\d+)'
        f_m = re.search(fatt_pattern, testo, re.I)
        d_m = re.search(dip_pattern, testo, re.I)
        return (f_m.group(1).strip() if f_m else "Vedi online", 
                d_m.group(1).strip() if d_m else "N.D.")
    except: return "Errore", "Errore"

# --- 3. GESTIONE STATO ---
if 'results' not in st.session_state: st.session_state.results = pd.DataFrame()
if 'pos' not in st.session_state: st.session_state.pos = {'lat': 45.547, 'lon': 11.545}

# --- 4. INTERFACCIA ---
st.title("🏭 Business Intelligence Veneto")

with st.sidebar:
    st.header("Filtri")
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori", list(ATECO_MAP.keys()))
    if st.button("Reset"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- MAPPA INTERATTIVA (Sistemata) ---
st.subheader("1. Area di Ricerca")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], 
              radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

# Aggiungi marker se ci sono risultati
if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

# Mostra la mappa e cattura il click
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

# --- RISULTATI E PULSANTI DI ARRICCHIMENTO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Risultati e Arricchimento")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)
    
    c1, c2 = st.columns(2)
    
    with c1:
        if st.button("🌐 FASE 1: CERCA P.IVA SUI SITI", use_container_width=True):
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
            
    with c2:
        if st.button("📊 FASE 2: DATI CAMERALI (FATTURATO)", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
            for i, row in df.iterrows():
                # Procediamo solo se abbiamo una P.IVA valida
                if row['Partita IVA'] not in ["N.D.", "Errore", "Non trovata"]:
                    fc, d = scrape_portale_camerale(row['Partita IVA'])
                    df.at[i, 'Fatturato (Camerale)'] = fc
                    df.at[i, 'Dipendenti'] = d
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica CSV", csv, "export_aziende.csv", "text/csv")

