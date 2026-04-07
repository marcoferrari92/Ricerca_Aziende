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

# --- 3. FUNZIONI DI SCRAPING ---

def scrape_sito_aziendale(url):
    """FASE 1: Cerca P.IVA, Email, Fatturato e Capitale Sociale sul sito ufficiale."""
    if not url or url == 'N.D.': return "N.D.", "N.D.", "N.D.", "N.D."
    if not url.startswith('http'): url = 'http://' + url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        testo = soup.get_text(separator=' ') # Separatore per evitare parole attaccate
        
        # 1. Partita IVA (11 cifre)
        piva = re.search(r'\b\d{11}\b', testo)
        
        # 2. Email
        email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
        
        # 3. Fatturato (se presente nel testo)
        fatt = re.search(r'Fatturato[:\s]*([€\d.,\s]+(?:milioni|mila|mln|k|euro|€)?)', testo, re.I)
        
        # 4. Capitale Sociale (Pattern: Cap. Soc. seguito da cifre ed euro)
        # Nuova Regex per il Capitale Sociale
        # Gestisce: "Cap. Soc. Euro 10.000", "Capitale Sociale: 50.000 €", "Cap. Soc. i.v. 10.000,00"
        cap_pattern = r'(?:Capitale\s+Sociale|Cap\.?\s*Soc\.?)\s*(?:i\.v\.)?[:\s]*(?:euro|€)?\s*([\d.,]+(?:\s*(?:euro|€|mila|mln))?)'
        cap_soc = re.search(cap_pattern, testo, re.I)
        
        return (
            piva.group(0) if piva else "N.D.", 
            email.group(0) if email else "N.D.",
            fatt.group(1).strip() if fatt else "N.D.",
            cap_soc.group(1).strip() if cap_soc else "N.D."
        )
    except: 
        return "Errore", "N.D.", "N.D.", "N.D."

def scrape_portale_camerale(piva):
    """FASE 2: Cerca dati ufficiali di bilancio (Versione Potenziata)."""
    if piva in ["N.D.", "Errore", "Non trovata"] or len(piva) != 11:
        return "N.D.", "N.D."
    
    url = f"https://www.reportaziende.it/ricerca?q={piva}"
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'it-IT,it;q=0.9'
        }
        time.sleep(1.5) 
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        testo = soup.get_text(separator=' ').strip()

        fatt_pattern = r'fatturato\s*(?:\d{4})?[:\s-]*([€\d.,\s]+(?:milioni|mila|mln|k|euro|€)?)'
        dip_pattern = r'dipendenti[:\s-]*(\d+)'

        fatt_match = re.search(fatt_pattern, testo, re.IGNORECASE)
        dip_match = re.search(dip_pattern, testo, re.IGNORECASE)

        fatturato = fatt_match.group(1).strip() if fatt_match else "Controlla link"
        dipendenti = dip_match.group(1).strip() if dip_match else "N.D."

        if len(fatturato) < 2: fatturato = "Vedi online"
        return fatturato, dipendenti
    except Exception as e:
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

# --- 5. RISULTATI E ARRICCHIMENTO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Risultati e Arricchimento")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)
    
    c1, c2 = st.columns(2)
    
    with c1:
        if st.button("🌐 FASE 1: CERCA P.IVA SUI SITI", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
    
            # Assicurati che le colonne necessarie esistano per evitare KeyErrors
            if 'Capitale Sociale' not in df.columns:
                df['Capitale Sociale'] = 'N.D.'
            if 'Partita IVA' not in df.columns:
                df['Partita IVA'] = 'N.D.'

            for i, row in df.iterrows():
                # Chiamata alla funzione che restituisce 4 valori
                p, e, f, c = scrape_sito_aziendale(row['Sito Web'])
        
                df.at[i, 'Partita IVA'] = p
                # Aggiorna l'email solo se quella attuale è N.D.
                if row.get('Email') == 'N.D.': 
                    df.at[i, 'Email'] = e
                
                # Gestione Fatturato (colonna creata da fetch_data)
                df.at[i, 'Fatturato'] = f
                df.at[i, 'Capitale Sociale'] = c
        
                bar.progress((i + 1) / len(df))
    
            # IMPORTANTE: Queste due righe devono stare DENTRO il blocco 'if st.button'
            st.session_state.results = df
            st.rerun()
            
    with c2:
        if st.button("📊 FASE 2: DATI CAMERALI (FATTURATO)", use_container_width=True):
            df = st.session_state.results.copy()
            
            # Controllo esistenza colonne per Fase 2
            if 'Dipendenti' not in df.columns:
                df['Dipendenti'] = 'N.D.'
                
            bar = st.progress(0)
            for i, row in df.iterrows():
                # Procediamo solo se abbiamo una P.IVA valida (11 cifre)
                piva_check = str(row.get('Partita IVA', 'N.D.'))
                if piva_check not in ["N.D.", "Errore", "Non trovata"] and len(piva_check) == 11:
                    fc, d = scrape_portale_camerale(piva_check)
                    df.at[i, 'Fatturato'] = fc
                    df.at[i, 'Dipendenti'] = d
                
                bar.progress((i + 1) / len(df))
            
            st.session_state.results = df
            st.rerun()

    # Sezione Download
    st.divider()
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica CSV Completo", csv, "export_aziende.csv", "text/csv", use_container_width=True)
