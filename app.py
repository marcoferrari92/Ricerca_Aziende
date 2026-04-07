import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

# --- 1. CONFIGURAZIONE E MAPPA TAG POTENZIATA ---
st.set_page_config(layout="wide", page_title="ATECO Business Finder")

# Qui usiamo filtri più larghi (~ vuol dire "contiene") per non perdere nulla
ATECO_TAGS = {
    "A - AGRICOLTURA": ["['landuse'~'farm']", "['amenity'~'winery']", "['shop'='farm']", "['craft'='winery']"],
    "C - MANIFATTURIERE": ["['industrial'~'factory']", "['building'='industrial']", "['craft'='sawmill']", "['man_made'='works']"],
    "G - COMMERCIO": ["['shop'~'supermarket']", "['shop'~'wholesale']", "['shop'~'retail']"],
    "I - RISTORAZIONE/HOTEL": ["['amenity'~'restaurant']", "['amenity'~'cafe']", "['tourism'~'hotel']"],
    "K - INFORMATICA/UFFICI": ["['office'~'it']", "['office'~'telecommunication']", "['office'='yes']"]
}

# --- 2. IL MOTORE DI RICERCA (IL PONTE) ---
def fetch_data_overpass(lat, lon, raggio_km, settori_ateco):
    # Usiamo un endpoint molto stabile
    url = "https://overpass-api.de/api/interpreter"
    raggio_metri = int(raggio_km * 1000)
    
    filtri_generati = ""
    for s in settori_ateco:
        per_settore = ATECO_TAGS.get(s, [])
        for t in per_settore:
            # Cerchiamo sia nodi che aree (nwr = node, way, relation)
            filtri_generati += f"nwr{t}(around:{raggio_metri},{lat},{lon});\n"

    # Query completa con istruzione 'center' per ottenere coordinate anche dalle aree grandi
    query = f"""
    [out:json][timeout:120];
    (
      {filtri_generati}
    );
    out tags center;
    """
    
    try:
        r = requests.get(url, params={'data': query}, timeout=130)
        data = r.json()
        elements = data.get('elements', [])
        
        risultati = []
        for e in elements:
            tags = e.get('tags', {})
            if 'name' in tags:
                # Recupero coordinate (se area usa center, se punto usa lat/lon)
                e_lat = e.get('lat') or e.get('center', {}).get('lat')
                e_lon = e.get('lon') or e.get('center', {}).get('lon')
                
                risultati.append({
                    'Ragione Sociale': tags.get('name'),
                    'Settore': tags.get('industrial', tags.get('shop', tags.get('amenity', 'Azienda'))),
                    'Indirizzo': f"{tags.get('addr:street', '')} {tags.get('addr:housenumber', '')}".strip() or "N.D.",
                    'Città': tags.get('addr:city', 'N.D.'),
                    'lat': e_lat,
                    'lon': e_lon
                })
        return pd.DataFrame(risultati)
    except Exception as e:
        st.error(f"Errore di connessione: {e}")
        return pd.DataFrame()

# --- 3. LOGICA DELL'INTERFACCIA ---
st.title("🏢 Business Finder ATECO Interattivo")
st.write("Seleziona i settori, regola il raggio e **clicca sulla mappa** per posizionare il centro.")

if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545} # Centro Vicenza default

# Sidebar
with st.sidebar:
    st.header("Filtri")
    km = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Macrosettori", list(ATECO_TAGS.keys()), default=["A - AGRICOLTURA"])
    st.info("💡 Il cerchio sulla mappa mostra l'area che verrà scansionata.")

# Mappa Interattiva
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)

# Disegna cerchio di anteprima
folium.Circle(
    location=[st.session_state.pos['lat'], st.session_state.pos['lon']],
    radius=km * 1000,
    color="#3186cc", fill=True, fill_opacity=0.2
).add_to(m)
folium.Marker([st.session_state.pos['lat'], st.session_state.pos['lon']]).add_to(m)

out = st_folium(m, width=800, height=450)

# Comunicazione: se clicchi, aggiorna la posizione salvata
if out and out['last_clicked']:
    nl, nn = out['last_clicked']['lat'], out['last_clicked']['lng']
    if nl != st.session_state.pos['lat']:
        st.session_state.pos = {'lat': nl, 'lon': nn}
        st.rerun()

# IL TASTO DI COMANDO
st.write(f"📍 Centro: **{st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}**")
if st.button("🚀 SCANSIONA AREA", use_container_width=True):
    with st.spinner("Interrogazione database..."):
        df = fetch_data_overpass(st.session_state.pos['lat'], st.session_state.pos['lon'], km, scelte)
        
        if not df.empty:
            st.success(f"Trovate {len(df)} attività!")
            st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
            
            # Bottone Download
            csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
            st.download_button("📥 Scarica CSV", csv, "export_aziende.csv", "text/csv")
        else:
            st.warning("Nessun risultato. Prova a cliccare in una zona diversa o aumentare il raggio.")
