import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

# --- 1. MAPPATURA INTEGRALE E PRECISA ---
# Ho unito i tuoi tag agricoli con i tag tecnici degli altri settori
ATECO_MAP = {
    "A - AGRICOLTURA, SILVICOLTURA E PESCA": ["['landuse'='farmyard']", "['industrial'='agriculture']", "['shop'='farm']", "['craft'='winery']", "['landuse'='vineyard']", "['forestry'='yes']"],
    "B - ATTIVITA' ESTRATTIVE": ["['landuse'='quarry']", "['industrial'='mine']", "['industrial'='stone_cutter']"],
    "C - ATTIVITA' MANIFATTURIERE": ["['industrial'='factory']", "['building'='industrial']", "['craft'='sawmill']", "['man_made'='works']", "['industrial'='tannery']"],
    "D - ENERGIA E GAS": ["['power'='plant']", "['substation'='yes']"],
    "E - ACQUA E RIFIUTI": ["['amenity'='waste_disposal']", "['man_made'='water_works']"],
    "F - COSTRUZIONI": ["['office'='builder']", "['craft'='carpenter']", "['industrial'='construction']"],
    "G - COMMERCIO ALL'INGROSSO E DETTAGLIO": ["['shop'='supermarket']", "['shop'='wholesale']", "['shop'='retail']", "['shop'='department_store']"],
    "H - TRASPORTO E MAGAZZINAGGIO": ["['amenity'='bus_station']", "['industrial'='logistics']", "['building'='warehouse']"],
    "I - ALLOGGIO E RISTORAZIONE": ["['amenity'='restaurant']", "['amenity'='cafe']", "['tourism'='hotel']", "['tourism'='guest_house']", "['amenity'='pub']"],
    "K - INFORMATICA E TELECOMUNICAZIONI": ["['office'='it']", "['office'='telecommunication']", "['telecom'='data_center']"],
    "L - FINANZA E ASSICURAZIONI": ["['amenity'='bank']", "['office'='insurance']"],
    "M - IMMOBILIARI": ["['office'='estate_agent']"],
    "N - PROFESSIONALI E SCIENTIFICHE": ["['office'='lawyer']", "['office'='architect']", "['office'='accountant']", "['office'='research']"],
    "Q - ISTRUZIONE": ["['amenity'='school']", "['amenity'='university']"],
    "R - SALUTE": ["['amenity'='hospital']", "['amenity'='doctors']", "['amenity'='pharmacy']"],
    "S - SPORT E DIVERTIMENTO": ["['leisure'='sports_centre']", "['amenity'='cinema']", "['amenity'='theatre']"]
}

# --- 2. MOTORE DI RICERCA ---
def fetch_data_overpass(lat, lon, raggio_km, macrosettori_scelti):
    url = "https://overpass-api.de/api/interpreter"
    raggio_m = int(raggio_km * 1000)
    
    filtri_query = ""
    for ms in macrosettori_scelti:
        tag_list = ATECO_MAP.get(ms, [])
        for t in tag_list:
            filtri_query += f"nwr{t}(around:{raggio_m},{lat},{lon});\n"

    query = f"""
    [out:json][timeout:120];
    (
      {filtri_query}
    );
    out tags center;
    """
    
    try:
        r = requests.get(url, params={'data': query}, timeout=130)
        elements = r.json().get('elements', [])
        risultati = []
        for e in elements:
            t = e.get('tags', {})
            if 'name' in t:
                # Estrazione coordinate (punto o centro area)
                e_lat = e.get('lat') or e.get('center', {}).get('lat')
                e_lon = e.get('lon') or e.get('center', {}).get('lon')
                
                risultati.append({
                    'Ragione Sociale': t.get('name'),
                    'Comune': t.get('addr:city', 'N.D.'),
                    'Indirizzo': f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip() or 'N.D.',
                    'Tipologia': t.get('description', t.get('farmyard:type', t.get('industrial', 'Azienda'))),
                    'Sito Web': t.get('website', 'N.D.'),
                    'Telefono': t.get('phone', 'N.D.'),
                    'Produzione': t.get('produce', 'N.D.'),
                    'lat': e_lat,
                    'lon': e_lon
                })
        return pd.DataFrame(risultati)
    except:
        return pd.DataFrame()

# --- 3. INTERFACCIA STREAMLIT ---
st.set_page_config(layout="wide", page_title="Business Finder ATECO")
st.title("🏢 Business Finder ATECO con Mappa")

if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545} # Default Vicenza

with st.sidebar:
    st.header("⚙️ Configura Ricerca")
    raggio = st.slider("Raggio di ricerca (KM)", 1, 30, 10)
    scelte = st.multiselect("Seleziona Macrosettori ATECO", list(ATECO_MAP.keys()), default=["A - AGRICOLTURA, SILVICOLTURA E PESCA"])
    st.write("---")
    st.info("📌 Clicca sulla mappa per impostare il centro della scansione.")

# --- 4. MAPPA PER SELEZIONE PUNTO ---
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=11)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="blue", fill=True, opacity=0.2).add_to(m)
folium.Marker([st.session_state.pos['lat'], st.session_state.pos['lon']], tooltip="Punto di scansione").add_to(m)

map_input = st_folium(m, width="100%", height=400)

# Aggiornamento posizione al click
if map_input and map_input['last_clicked']:
    nl, nn = map_input['last_clicked']['lat'], map_input['last_clicked']['lng']
    if nl != st.session_state.pos['lat']:
        st.session_state.pos = {'lat': nl, 'lon': nn}
        st.rerun()

# --- 5. AZIONE E RISULTATI ---
if st.button(f"🚀 SCANSIONA AREA ENTRO {raggio} KM", use_container_width=True):
    with st.spinner("Estrazione dati in corso..."):
        df = fetch_data_overpass(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
        
        if not df.empty:
            st.success(f"Trovate {len(df)} aziende!")
            
            # MAPPA DEI RISULTATI
            st.subheader("📍 Localizzazione sulla Mappa")
            res_map = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
            for _, row in df.iterrows():
                folium.Marker(
                    [row['lat'], row['lon']], 
                    popup=f"<b>{row['Ragione Sociale']}</b><br>{row['Produzione']}",
                    icon=folium.Icon(color='red', icon='briefcase')
                ).add_to(res_map)
            st_folium(res_map, width="100%", height=450, key="results")

            # TABELLA DETTAGLIATA
            st.subheader("📋 Database Aziendale")
            st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
            
            # DOWNLOAD
            csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
            st.download_button("📥 Scarica Database (CSV)", csv, "database_export.csv", "text/csv")
        else:
            st.warning("Nessun dato trovato. Prova a cambiare zona o aumentare il raggio.")
