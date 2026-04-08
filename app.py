import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3
import time

# Disabilita gli avvisi per i siti senza certificato sicuro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import delle componenti esterne (Assicurati che fetch_data_google sia in utils.py)
from mapping import ATECO_MAP 
from utils import fetch_data_google, scrape_sito_aziendale, scrape_camerale_data

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor Pro")

# --- GESTIONE CHIAVE API (Dalle impostazioni Streamlit) ---
# Assicurati di averla nel file .streamlit/secrets.toml come: MAPS_API_KEY = "tua_chiave"
API_KEY = st.secrets.get("MAPS_API_KEY", "")

# --- GESTIONE STATO ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- INTERFACCIA UTENTE ---
st.title("🏭 Business Data Extractor (Google Edition)")
st.markdown("Ottieni dati aziendali ad alta precisione tramite **Google Places** + **Web Scraping**.")

with st.sidebar:
    st.header("⚙️ Configurazione")
    if not API_KEY:
        st.error("⚠️ Google API Key non trovata nei Secrets!")
    
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali (Keywords)", list(ATECO_MAP.keys()))
    
    st.divider()
    if st.button("🗑️ Reset Database"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

st.subheader("1. Area di Ricerca")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(
    location=[st.session_state.pos['lat'], st.session_state.pos['lon']], 
    radius=raggio*1000, 
    color="blue", 
    fill=True, 
    opacity=0.1
).add_to(m)

# Aggiungi marker per i risultati già trovati
if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="100%", height=400, key="map_bi")

# Aggiornamento posizione al click
if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if abs(new_lat - st.session_state.pos['lat']) > 0.0001:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

# --- BOTTONE DI RICERCA GOOGLE ---
if st.button("🚀 TROVA AZIENDE CON GOOGLE MAPS", use_container_width=True, type="primary"):
    if not API_KEY:
        st.error("Inserisci la API Key per procedere.")
    elif not scelte:
        st.warning("Seleziona almeno un settore dalla barra laterale!")
    else:
        with st.status("Interrogando Google Places API...", expanded=True) as status:
            st.write("Cercando attività nell'area...")
            # Chiamata alla nuova funzione
            df = fetch_data_google(
                st.session_state.pos['lat'], 
                st.session_state.pos['lon'], 
                raggio, 
                scelte, 
                API_KEY
            )
            st.write(f"Trovate {len(df)} aziende. Salvataggio in corso...")
            st.session_state.results = df
            status.update(label="Scansione Completata!", state="complete", expanded=False)
        st.rerun()

# --- RISULTATI E SCRAPING AVANZATO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Aziende Trovate")
    st.dataframe(
        st.session_state.results.drop(columns=['lat', 'lon'], errors='ignore'), 
        use_container_width=True
    )

    st.subheader("3. Arricchimento Profondo (Email + P.IVA + Bilancio)")
    st.info("Questa fase esegue lo scraping dei siti web trovati da Google.")
    
    if st.button("🔍 ESTRAI DATI COMPLETI", use_container_width=True):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status_msg = st.empty()
        
        count = len(df_work)
        for i, (idx, row) in enumerate(df_work.iterrows()):
            if row['Sito Web'] and row['Sito Web'] != 'N.D.':
                status_msg.text(f"Analisi ({i+1}/{count}): {row['Ragione Sociale']}...")
                
                # --- STEP 1: SCRAPING SITO WEB ---
                piva, email_web = scrape_sito_aziendale(row['Sito Web'])
                df_work.at[idx, 'Partita IVA'] = piva
                
                if row.get('Email') == 'N.D.':
                    df_work.at[idx, 'Email'] = email_web
                
                # --- STEP 2: DATI CAMERALI ---
                piva_clean = "".join(filter(str.isdigit, str(piva)))
                if len(piva_clean) == 11:
                    fatt, dip = scrape_camerale_data(piva_clean)
                    df_work.at[idx, 'Fatturato'] = fatt
                    df_work.at[idx, 'Dipendenti'] = dip
            
            progress_bar.progress((i + 1) / count)
        
        st.session_state.results = df_work
        status_msg.success("✅ Arricchimento completato!")
        st.rerun()

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database Finale (CSV)", csv, "database_aziende.csv", "text/csv")
