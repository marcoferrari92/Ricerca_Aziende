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

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor")

# --- 2. GESTIONE STATO ---
if 'results' not in st.session_state: 
    st.session_state.results = pd.DataFrame()
if 'pos' not in st.session_state: 
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}

# --- 3. FUNZIONE CAMERALE (FASE 2) ---
def scrape_portale_camerale(piva):
    """Estrazione basata sulla struttura dello screenshot inviato."""
    if piva in ["N.D.", "Errore", "Non trovata"] or len(str(piva)) != 11:
        return "N.D.", "N.D."
    
    url = f"https://www.reportaziende.it/ricerca?q={piva}"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        time.sleep(2)
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        # Se non siamo nella scheda, cerchiamo il primo link utile
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

# --- 4. INTERFACCIA UTENTE ---
st.title("🏭 Business Intelligence Pro")

with st.sidebar:
    st.header("⚙️ Configurazione")
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori", list(ATECO_MAP.keys()))
    if st.button("🗑️ Reset Database"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# Sezione 1: Mappa e Ricerca Iniziale
st.subheader("1. Area di Ricerca")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], 
              radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_data = st_folium(m, width="100%", height=300, key="main_map")

if map_data and map_data.get('last_clicked'):
    nl, ng = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
    if abs(nl - st.session_state.pos['lat']) > 0.001:
        st.session_state.pos = {'lat': nl, 'lon': ng}
        st.rerun()

if st.button("🚀 1. TROVA AZIENDE NELL'AREA", use_container_width=True):
    if scelte:
        with st.spinner("Interrogazione mappe..."):
            st.session_state.results = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
            st.rerun()
    else:
        st.warning("Seleziona almeno un settore!")

# Sezione 2: Elaborazione e Risultati
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Elaborazione Dati")
    
    # Visualizzazione Tabella (senza lat/lon)
    display_df = st.session_state.results.copy()
    cols_to_drop = [c for c in ['lat', 'lon'] if c in display_df.columns]
    st.dataframe(display_df.drop(columns=cols_to_drop), use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🌐 2. SCANSIONA SITI (P.IVA + EMAIL)", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
            status = st.empty()
            
            for i, row in df.iterrows():
                status.text(f"Analisi sito: {row['Ragione Sociale']}...")
                # Riceve 3 valori come definito nella tua funzione utils
                p, e, f = scrape_sito_aziendale(row['Sito Web'])
                
                df.at[i, 'Partita IVA'] = p
                if row.get('Email') == 'N.D.': 
                    df.at[i, 'Email'] = e
                df.at[i, 'Fatturato (da sito)'] = f
                
                bar.progress((i + 1) / len(df))
            
            status.empty()
            st.session_state.results = df
            st.rerun()
            
    with col2:
        if st.button("📊 3. RICERCA CAMERALE (BILANCI)", use_container_width=True):
            df = st.session_state.results.copy()
            # Assicuriamoci che le colonne esistano
            if 'Fatturato (Camerale)' not in df.columns: df['Fatturato (Camerale)'] = 'N.D.'
            if 'Dipendenti' not in df.columns: df['Dipendenti'] = 'N.D.'
            
            bar = st.progress(0)
            status = st.empty()
            
            for i, row in df.iterrows():
                piva = str(row.get('Partita IVA', 'N.D.'))
                if len(piva) == 11 and piva.isdigit():
                    status.text(f"Ricerca bilancio P.IVA {piva}...")
                    f_c, d = scrape_portale_camerale(piva)
                    df.at[i, 'Fatturato (Camerale)'] = f_c
                    df.at[i, 'Dipendenti'] = d
                
                bar.progress((i + 1) / len(df))
            
            status.empty()
            st.session_state.results = df
            st.rerun()

    # Sezione Download
    st.divider()
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 SCARICA DATABASE CSV", csv, "aziende_bi_veneto.csv", "text/csv", use_container_width=True)
