import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- TRADUTTORE TECNICO ATECO -> TAG PRECISI ---
# Qui usiamo solo i tag che "esistono" davvero nel database cartografico
ATECO_TAGS = {
    "A - AGRICOLTURA": ["node['landuse'='farmyard']", "way['landuse'='farmyard']", "node['shop'='farm']", "node['craft'='winery']"],
    "B - ESTRATTIVE": ["node['landuse'='quarry']", "way['landuse'='quarry']"],
    "C - MANIFATTURIERE": ["node['industrial'='factory']", "way['industrial'='factory']", "node['craft'='sawmill']"],
    "G - COMMERCIO": ["node['shop'='supermarket']", "node['shop'='wholesale']", "node['shop'='retail']"],
    "I - RISTORAZIONE/HOTEL": ["node['amenity'='restaurant']", "node['amenity'='cafe']", "node['tourism'='hotel']"],
    "K - INFORMATICA": ["node['office'='it']", "node['office'='telecommunication']"],
    "N - PROFESSIONALI": ["node['office'='lawyer']", "node['office'='architect']", "node['office'='accountant']"]
}

def fetch_data_clean(lat, lon, raggio_km, macrosettori):
    url = "http://overpass-api.de/api/interpreter"
    raggio_m = raggio_km * 1000
    
    # Costruiamo i filtri basandoci sui tag precisi
    filtri_query = ""
    for ms in macrosettori:
        for tag_completo in ATECO_TAGS.get(ms, []):
            # Aggiungiamo il filtro (around:raggio, lat, lon) a ogni tag
            filtri_query += f"{tag_completo}(around:{raggio_m},{lat},{lon});\n"

    query = f"""
    [out:json][timeout:90];
    (
      {filtri_query}
    );
    out tags center;
    """
    
    try:
        response = requests.get(url, params={'data': query}, timeout=100)
        response.raise_for_status()
        elements = response.json().get('elements', [])
        
        risultati = []
        for el in elements:
            t = el.get('tags', {})
            if 'name' in t:
                # Coordinate: se è una way (area), Overpass 'center' le mette in el['center']
                r_lat = el.get('lat') or el.get('center', {}).get('lat')
                r_lon = el.get('lon') or el.get('center', {}).get('lon')
                
                risultati.append({
                    'Ragione Sociale': t.get('name'),
                    'Comune': t.get('addr:city', 'N.D.'),
                    'Indirizzo': f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip() or 'N.D.',
                    'Telefono': t.get('phone', 'N.D.'),
                    'Sito Web': t.get('website', 'N.D.'),
                    'lat': r_lat,
                    'lon': r_lon
                })
        return pd.DataFrame(risultati)
    except Exception as e:
        st.error(f"Errore tecnico: {e}")
        return pd.DataFrame()

# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Business Finder Vicenza", layout="wide")
st.title("📍 Localizzatore Aziende Vicentine")

with st.sidebar:
    st.header("1. Imposta Ricerca")
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    settori = st.multiselect("Macrosettori ATECO", options=list(ATECO_TAGS.keys()), default=["A - AGRICOLTURA"])
    st.write("---")
    st.write("📌 **Istruzioni:**")
    st.write("Clicca sulla mappa a destra per scegliere il punto centrale. Apparirà il tasto per cercare.")

# Mappa interattiva per il click
st.subheader("Mappa Interattiva: Clicca dove vuoi cercare")
m = folium.Map(location=[45.547, 11.546], zoom_start=11)
map_click = st_folium(m, width="100%", height=500)

if map_click and map_click['last_clicked']:
    lat = map_click['last_clicked']['lat']
    lon = map_click['last_clicked']['lng']
    
    st.success(f"Centro impostato! Coordinate: {lat:.4f}, {lon:.4f}")
    
    if st.button("🚀 AVVIA RICERCA IN QUESTA AREA"):
        with st.spinner("Interrogazione database in corso..."):
            df = fetch_data_clean(lat, lon, raggio, settori)
            
            if not df.empty:
                st.balloons()
                st.metric("Aziende trovate", len(df))
                
                # Tabella Risultati
                st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
                
                # Download
                csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
                st.download_button("📥 Scarica Excel (CSV)", csv, "aziende_estratte.csv", "text/csv")
                
                # Mappa dei risultati
                res_map = folium.Map(location=[lat, lon], zoom_start=13)
                folium.Circle([lat, lon], radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(res_map)
                for _, row in df.iterrows():
                    folium.Marker([row['lat'], row['lon']], popup=row['Ragione Sociale']).add_to(res_map)
                st_folium(res_map, width="100%", height=500, key="result_map")
            else:
                st.warning("⚠️ Nessun dato trovato. Prova ad aumentare il raggio o cambiare punto.")
else:
    st.info("👈 Clicca sulla mappa sopra per iniziare.")
