import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3

# Disabilita gli avvisi per i siti senza certificato sicuro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import delle componenti esterne
from mapping import ATECO_MAP
from utils import fetch_data_google, scrape_sito_aziendale

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor Pro")

# --- GESTIONE STATO ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- INTERFACCIA SIDEBAR ---
with st.sidebar:
    st.header("🔑 Autenticazione")
    user_api_key = st.text_input("Inserisci la tua Google API Key", type="password")
    
    st.header("⚙️ Configurazione")
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali (Codici ATECO)", list(ATECO_MAP.keys()))
    max_test = st.slider("Limite Aziende", 5, 200, 20) 

    st.divider()
    if st.button("🗑️ Reset Database"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

st.title("🏭 Business Data Extractor")
st.subheader("1. Area di Ricerca")

# --- MAPPA ---
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(
    location=[st.session_state.pos['lat'], st.session_state.pos['lon']], 
    radius=raggio*1000, 
    color="blue", 
    fill=True, 
    opacity=0.1
).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="stretch", height=400, key="map_main")

# Aggiornamento posizione al click sulla mappa
if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if abs(new_lat - st.session_state.pos['lat']) > 0.001:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

# --- BOTTONE RICERCA ---
if st.button("🚀 TROVA AZIENDE CON GOOGLE MAPS", width="stretch", type="primary"):
    if not user_api_key:
        st.error("Inserisci la API Key!")
    elif not scelte:
        st.warning("Seleziona almeno un settore!")
    else:
        keywords = []
        for s in scelte:
            keywords.extend(ATECO_MAP.get(s, [s]))
        
        with st.status("Ricerca in corso...", expanded=True) as status:
            # fetch_data_google restituisce già Stato e Categorie
            df = fetch_data_google(
                st.session_state.pos['lat'], 
                st.session_state.pos['lon'], 
                raggio, 
                keywords, 
                user_api_key, 
                max_results=max_test
            )
            st.session_state.results = df
            status.update(label=f"Trovate {len(df)} aziende!", state="complete", expanded=False)
        st.rerun()

# --- VISUALIZZAZIONE TABELLA ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Aziende Trovate")
    
    # Mostriamo la tabella completa (Stato e Categorie sono incluse nel DF)
    # Rimuoviamo lat e lon solo per la vista, ma restano nel database
    view_df = st.session_state.results.drop(columns=['lat', 'lon'], errors='ignore')
    st.dataframe(view_df, width="stretch")

    st.subheader("3. Arricchimento (Email + P.IVA)")
    
    if st.button("🔍 ESTRAI EMAIL E P.IVA", width='stretch'):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status_msg = st.empty()
        
        count = len(df_work)
        for i, (idx, row) in enumerate(df_work.iterrows()):
            status_msg.info(f"⏳ Analisi {i+1}/{count}: {row['Ragione Sociale']}")
            
            # Solo scraping web (Email e P.IVA)
            piva, email = scrape_sito_aziendale(row['Sito Web'])
            df_work.at[idx, 'Partita IVA'] = piva
            df_work.at[idx, 'Email'] = email
            
            progress_bar.progress((i + 1) / count)
        
        st.session_state.results = df_work
        status_msg.success("✅ Web scraping completato!")
        st.rerun()

    # Esportazione
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica CSV Completo", csv, "aziende_export.csv", "text/csv", width="stretch")
