import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3
import time

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

# --- INTERFACCIA UTENTE ---
st.title("🏭 Business Data Extractor (Google Edition)")
st.markdown("Ottieni dati aziendali tramite **Google Places** + **Web Scraping**.")

with st.sidebar:
    st.header("🔑 Autenticazione")
    # Campo per inserire la chiave manualmente
    user_api_key = st.text_input("Inserisci la tua Google API Key", type="password", help="La chiave non viene salvata sul server.")
    
    if not user_api_key:
        st.warning("⚠️ Inserisci la API Key per attivare le funzioni di ricerca.")

    st.header("⚙️ Configurazione")
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali (Codici ATECO)", list(ATECO_MAP.keys()))
    max_test = st.slider("Limite Aziende (Safety Block)", 5, 200, 20) 

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

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="100%", height=400, key="map_bi")

if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if abs(new_lat - st.session_state.pos['lat']) > 0.0001:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

# --- BOTTONE DI RICERCA GOOGLE ---
if st.button("🚀 TROVA AZIENDE CON GOOGLE MAPS", use_container_width=True, type="primary"):
    if not user_api_key:
        st.error("❌ Errore: Devi inserire una API Key valida nella barra laterale!")
    elif not scelte:
        st.warning("Seleziona almeno un settore (es. C.25) dalla barra laterale!")
    else:
        keywords_finali = []
        for s in scelte:
            keywords_finali.extend(ATECO_MAP.get(s, [s]))
        
        with st.status(f"Ricerca in corso per {len(keywords_finali)} categorie...", expanded=True) as status:
            st.write("Connessione a Google Places...")
            
            # Passiamo la chiave inserita dall'utente (user_api_key)
            df = fetch_data_google(
                st.session_state.pos['lat'], 
                st.session_state.pos['lon'], 
                raggio, 
                keywords_finali, 
                user_api_key, # <--- Chiave dinamica
                max_results=max_test
            )
            
            st.write(f"Trovate {len(df)} aziende. Elaborazione completata.")
            st.session_state.results = df
            status.update(label="Scansione Completata!", state="complete", expanded=False)
        st.rerun()

# --- RISULTATI E SCRAPING AVANZATO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Aziende Trovate")
    
    view_df = st.session_state.results.drop(columns=['lat', 'lon'], errors='ignore')
    st.dataframe(view_df, use_container_width=True)

    st.subheader("3. Arricchimento Profondo (Email + P.IVA + Bilancio)")
    
    if st.button("🔍 ESTRAI DATI COMPLETI", use_container_width=True):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status_msg = st.empty()
        
        count = len(df_work)
        for i, (idx, row) in enumerate(df_work.iterrows()):
            if row['Sito Web'] and row['Sito Web'] != 'N.D.':
                status_msg.text(f"Analisi ({i+1}/{count}): {row['Ragione Sociale']}...")
                
                piva, email_web = scrape_sito_aziendale(row['Sito Web'])
                df_work.at[idx, 'Partita IVA'] = piva
                if row.get('Email') == 'N.D.':
                    df_work.at[idx, 'Email'] = email_web
    
            progress_bar.progress((i + 1) / count)
        
        st.session_state.results = df_work
        status_msg.success("✅ Arricchimento completato!")
        st.rerun()

    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database Finale (CSV)", csv, "database_aziende.csv", "text/csv")
