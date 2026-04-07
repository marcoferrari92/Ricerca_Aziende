import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

# --- PARTE A: IL MOTORE (Riceve le coordinate e cerca) ---
def fetch_data_overpass(lat, lon, raggio_km, settori_ateco):
    url = "https://overpass-api.de/api/interpreter"
    raggio_metri = raggio_km * 1000
    
    # Mappatura tag (ridotta per esempio)
    mappa_tag = {
        "A - AGRICOLTURA": "node['landuse'='farmyard']",
        "C - MANIFATTURIERE": "node['industrial'='factory']",
        "I - RISTORAZIONE": "node['amenity'='restaurant']"
    }
    
    # Costruiamo la query usando le coordinate passate
    filtri = ""
    for s in settori_ateco:
        tag = mappa_tag.get(s)
        if tag:
            filtri += f"{tag}(around:{raggio_metri},{lat},{lon});\n"

    query = f"[out:json][timeout:90];({filtri});out tags center;"
    
    try:
        r = requests.get(url, params={'data': query})
        elements = r.json().get('elements', [])
        return pd.DataFrame([{'Nome': e['tags'].get('name', 'N.D.'), 'Lat': e.get('lat') or e.get('center', {}).get('lat'), 'Lon': e.get('lon') or e.get('center', {}).get('lon')} for e in elements if 'name' in e['tags']])
    except:
        return pd.DataFrame()

# --- PARTE B: L'INTERFACCIA (Raccoglie i dati) ---
st.title("🚜 ATECO Finder Interattivo")

# 1. Inizializziamo il 'Post-it' se è la prima volta che apriamo l'app
if 'punto_cliccato' not in st.session_state:
    st.session_state.punto_cliccato = {'lat': 45.547, 'lon': 11.545} # Default Vicenza

# Sidebar per raggio e settori
raggio = st.sidebar.slider("Raggio (KM)", 1, 30, 5)
settori = st.sidebar.multiselect("Settori", ["A - AGRICOLTURA", "C - MANIFATTURIERE", "I - RISTORAZIONE"], default=["A - AGRICOLTURA"])

# 2. Mostriamo la mappa e catturiamo il click
m = folium.Map(location=[st.session_state.punto_cliccato['lat'], st.session_state.punto_cliccato['lon']], zoom_start=12)

# Disegniamo il raggio visivo basandoci sul 'Post-it'
folium.Circle(
    location=[st.session_state.punto_cliccato['lat'], st.session_state.punto_cliccato['lon']],
    radius=raggio * 1000,
    color="red", fill=True, opacity=0.2
).add_to(m)

st.write("### 1. Clicca sulla mappa per spostare il centro")
mappa_interattiva = st_folium(m, width=700, height=400)

# 3. COMUNICAZIONE: Se l'utente clicca, aggiorniamo il 'Post-it'
if mappa_interattiva and mappa_interattiva['last_clicked']:
    nuova_lat = mappa_interattiva['last_clicked']['lat']
    nuova_lon = mappa_interattiva['last_clicked']['lng']
    
    # Se il click è diverso da quello salvato, aggiorna e ricarica
    if nuova_lat != st.session_state.punto_cliccato['lat']:
        st.session_state.punto_cliccato = {'lat': nuova_lat, 'lon': nuova_lon}
        st.rerun()

# 4. IL PONTE: Il tasto prende i dati dal 'Post-it' e li manda alla Funzione
st.write(f"📍 Centro attuale: {st.session_state.punto_cliccato['lat']:.4f}, {st.session_state.punto_cliccato['lon']:.4f}")

if st.button("🚀 AVVIA RICERCA AZIENDE"):
    # Qui avviene la magia: passiamo i dati dal session_state alla funzione di ricerca
    risultati = fetch_data_overpass(
        st.session_state.punto_cliccato['lat'], 
        st.session_state.punto_cliccato['lon'], 
        raggio, 
        settori
    )
    
    if not risultati.empty:
        st.success(f"Trovate {len(risultati)} aziende!")
        st.dataframe(risultati)
    else:
        st.warning("Nessun risultato. Prova a spostare il punto o aumentare il raggio.")
