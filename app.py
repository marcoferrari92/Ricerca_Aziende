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

def scrape_portale_camerale(piva):
    """FASE 2: Estrazione mirata da ReportAziende tramite selettori HTML."""
    if piva in ["N.D.", "Errore", "Non trovata"] or len(piva) != 11:
        return "N.D.", "N.D."
    
    # URL di ricerca univoco per Partita IVA
    url = f"https://www.reportaziende.it/ricerca?q={piva}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
        time.sleep(2) # Importante: i portali camerali sono molto sensibili
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        # Se il sito ci reindirizza alla lista risultati, prendiamo il primo link e ri-entriamo
        # (Spesso succede se la P.IVA non porta direttamente alla scheda)
        if "risultati della ricerca" in res.text.lower():
            link = soup.find('a', href=re.compile(r'/azienda/'))
            if link:
                res = requests.get("https://www.reportaziende.it" + link['href'], headers=headers, timeout=10)
                soup = BeautifulSoup(res.text, 'html.parser')

        testo_completo = soup.get_text(separator=' ', strip=True)

        # --- LOGICA 1: Ricerca nelle tabelle (Più precisa) ---
        fatturato = "N.D."
        dipendenti = "N.D."

        # Cerchiamo tutte le righe delle tabelle
        for row in soup.find_all('tr'):
            cella = row.get_text().lower()
            if 'fatturato' in cella or 'ricavi' in cella:
                # Prende i numeri dalla cella successiva o dalla stessa
                valori = re.findall(r'[\d.,]+\s*(?:€|euro|milioni|mln|mila|k)', cella, re.I)
                if valori: 
                    fatturato = valori[0]
                    break
            
            if 'dipendenti' in cella or 'organico' in cella:
                num = re.search(r'\b\d+\b', cella)
                if num: dipendenti = num.group(0)

        # --- LOGICA 2: Fallback su Regex testuale (se la tabella fallisce) ---
        if fatturato == "N.D.":
            # Pattern specifico per ReportAziende: cerca numero dopo "Fatturato"
            match_f = re.search(r'fatturato\s+([€\d.,\s]+(?:milioni|mln|euro|€))', testo_completo, re.I)
            if match_f: fatturato = match_f.group(1).strip()

        # Pulizia finale per evitare il "Vedi online" generico
        if len(fatturato) < 3: fatturato = "Vedi online"
        
        return fatturato, dipendenti

    except Exception as e:
        return "Errore connessione", "Errore"

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
