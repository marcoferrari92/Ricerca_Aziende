import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3

# 1. DISABILITA AVVISI SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. IMPORT DELLE TUE FUNZIONI (Assicurati che utils.py sia nella stessa cartella)
try:
    from mapping import ATECO_MAP
    from utils import fetch_data_google, scrape_sito_aziendale
    st.sidebar.success("✅ Moduli caricati correttamente")
except Exception as e:
    st.error(f"❌ Errore negli import: {e}")
    st.stop()

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="DEBUG MODE - Business Extractor")

# --- INIZIALIZZAZIONE VARIABILI (Fondamentale per evitare NameError) ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# Definiamo la variabile all'inizio del file così è SEMPRE disponibile
user_api_key = ""

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔑 Autenticazione")
    # Assegniamo il valore della text_input alla nostra variabile
    user_api_key = st.text_input("Google API Key", type="password", key="key_input")
    
    st.header("⚙️ Configurazione")
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori ATECO", list(ATECO_MAP.keys()))
    max_test = st.slider("Limite Risultati", 5, 200, 20) 

    if st.button("🗑️ Reset Totale"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

st.title("🏭 Debugging Tool - Google Maps")

# --- AREA MAPPA ---
st.subheader("1. Seleziona Punto di Ricerca")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Marker([st.session_state.pos['lat'], st.session_state.pos['lon']], popup="Centro Ricerca").add_to(m)

map_res = st_folium(m, width="100%", height=300, key="map_debug")

if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
    st.rerun()

# --- BOTTONE DI RICERCA CON LOG DI DIO ---
st.subheader("2. Esecuzione Ricerca")

if st.button("🚀 AVVIA RICERCA GOOGLE", use_container_width=True, type="primary"):
    # DEBUG 1: Controllo Chiave
    st.write("🔍 **DEBUG LOG:** Controllo input...")
    
    if not user_api_key:
        st.error("❌ LA CHIAVE API È VUOTA! Inseriscila nella barra a sinistra.")
    elif not scelte:
        st.warning("⚠️ Non hai selezionato nessun settore ATECO.")
    else:
        # DEBUG 2: Preparazione Keyword
        keywords_finali = []
        for s in scelte:
            keywords_finali.extend(ATECO_MAP.get(s, [s]))
        
        st.write(f"📡 **DEBUG LOG:** Cerco per {len(keywords_finali)} parole chiave...")
        
        # DEBUG 3: Chiamata a Google
        with st.status("📡 Interrogazione server Google in corso...", expanded=True) as status:
            try:
                st.write("⏳ Invio richiesta a Google Places API...")
                
                df = fetch_data_google(
                    st.session_state.pos['lat'], 
                    st.session_state.pos['lon'], 
                    raggio, 
                    keywords_finali, 
                    user_api_key, 
                    max_results=max_test
                )
                
                if df is None or df.empty:
                    st.error("🤔 Google ha risposto con 0 risultati. Forse il raggio è piccolo?")
                    status.update(label="Ricerca Fallita (0 Risultati)", state="error")
                else:
                    st.session_state.results = df
                    st.success(f"✅ TROVATE {len(df)} AZIENDE!")
                    status.update(label="Ricerca Completata!", state="complete")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"🔥 ERRORE CRITICO DURANTE LA CHIAMATA: {e}")
                status.update(label="Crash Tecnico", state="error")

# --- TABELLA RISULTATI ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("3. Risultati in Memoria")
    st.write("Se vedi questa tabella, i dati sono stati salvati correttamente.")
    st.dataframe(st.session_state.results, use_container_width=True)
    
    # Bottone per scaricare subito (almeno hai i dati se crasha lo scraping)
    csv = st.session_state.results.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Scarica i dati trovati finora", csv, "debug_results.csv", "text/csv")



