import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from mapping import ATECO_MAP
from utils import fetch_data_google, scrape_sito_aziendale

# --- CONFIGURAZIONE ---
st.set_page_config(layout="wide", page_title="Business Extractor")

if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.437, 'lon': 12.332} # Default: Venezia
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔑 API Settings")
    api_key = st.text_input("Google API Key", type="password")
    
    st.header("⚙️ Parametri")
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori ATECO", list(ATECO_MAP.keys()))
    limite = st.slider("Max Risultati", 10, 100, 20)
    
    if st.button("🗑️ Svuota Tutto"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- MAPPA INTERATTIVA ---
st.title("🏭 Lead Generation Tool")
st.subheader("1. Seleziona l'area sulla mappa")

m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="red", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_data = st_folium(m, width="100%", height=400, key="map_lead")

if map_data and map_data['last_clicked']:
    st.session_state.pos = {'lat': map_data['last_clicked']['lat'], 'lon': map_data['last_clicked']['lng']}
    st.rerun()

# --- RICERCA ---
if st.button("🚀 AVVIA RICERCA GOOGLE MAPS", use_container_width=True, type="primary"):
    if not api_key:
        st.error("Inserisci la chiave!")
    elif not scelte:
        st.warning("Scegli un settore!")
    else:
        kws = []
        for s in scelte: kws.extend(ATECO_MAP.get(s, [s]))
        
        with st.status("Ricerca in corso...", expanded=True) as status:
            df = fetch_data_google(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, kws, api_key, limite)
            st.session_state.results = df
            status.update(label="Fatto!", state="complete")
        st.rerun()

# --- VISUALIZZAZIONE TABELLA (SEMPRE VISIBILE SE RISULTATI > 0) ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Aziende Trovate")
    
    # La tabella viene mostrata indipendentemente dai pulsanti
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon'], errors='ignore'), use_container_width=True)

    st.subheader("3. Arricchimento (Web Scraping)")
    if st.button("🔍 ESTRAI P.IVA E EMAIL DAI SITI", use_container_width=True):
        df_work = st.session_state.results.copy()
        msg = st.empty()
        bar = st.progress(0)
        
        for i, (idx, row) in enumerate(df_work.iterrows()):
            msg.text(f"Analisi: {row['Ragione Sociale']}...")
            piva, email = scrape_sito_aziendale(row['Sito Web'])
            df_work.at[idx, 'Partita IVA'] = piva
            df_work.at[idx, 'Email'] = email
            bar.progress((i + 1) / len(df_work))
            
        st.session_state.results = df_work
        msg.success("Dati aggiornati!")
        st.rerun()

    # DOWNLOAD CSV
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database CSV", csv, "export_aziende.csv", "text/csv", use_container_width=True)



