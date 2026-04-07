import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium

# --- 1. MAPPATURA TAG (COMPLETA) ---
ATECO_MAP = {
    "A - AGRICOLTURA, SILVICOLTURA E PESCA": [
        "['landuse'='farmyard']", "['industrial'='agriculture']", "['shop'='farm']", 
        "['craft'='winery']", "['amenity'='winery']", "['landuse'='vineyard']", 
        "['agriculture'='horticulture']", "['animal_breeding'~'.*']", "['forestry'='yes']"
    ],
    "B - ATTIVITA' ESTRATTIVE": [
        "['landuse'='quarry']", "['industrial'='mine']", "['mine'='stone']", 
        "['industrial'='stone_cutter']", "['natural'='sand']"
    ],
    "C - ATTIVITA' MANIFATTURIERE": [
        "['industrial'='factory']", "['building'='industrial']", "['man_made'='works']",
        "['industrial'='tannery']", "['industrial'='leather']", "['industrial'='goldsmith']", 
        "['shop'='jewelry']", "['industrial'='furniture']", "['industrial'='textile']"
    ],
    "D - ENERGIA ELETTRICA, GAS, VAPORE": [
        "['power'='plant']", "['substation'='yes']", "['industrial'='energy']", "['power'='generator']"
    ],
    "E - ACQUA E RIFIUTI": [
        "['man_made'='water_works']", "['amenity'='waste_disposal']", "['landuse'='landfill']", "['amenity'='recycling']"
    ],
    "F - COSTRUZIONI": [
        "['office'='builder']", "['craft'='carpenter']", "['office'='construction']", 
        "['craft'='stonemason']", "['building'='construction']"
    ],
    "G - COMMERCIO ALL'INGROSSO E AL DETTAGLIO": [
        "['shop'='supermarket']", "['shop'='wholesale']", "['shop'='retail']", 
        "['shop'='warehouse']", "['shop'='trade']", "['shop'='department_store']"
    ],
    "H - TRASPORTO E MAGAZZINAGGIO": [
        "['industrial'='logistics']", "['building'='warehouse']", "['amenity'='bus_station']", 
        "['public_transport'='station']", "['amenity'='ferry_terminal']"
    ],
    "I - SERVIZI DI ALLOGGIO E RISTORAZIONE": [
        "['amenity'='restaurant']", "['amenity'='cafe']", "['tourism'='hotel']", 
        "['tourism'='agriturismo']", "['amenity'='pub']", "['tourism'='guest_house']"
    ],
    "J - ATTIVITA' EDITORIALI E MEDIA": [
        "['office'='newspaper']", "['office'='publisher']", "['amenity'='studio']", "['office'='advertising_agency']"
    ],
    "K - INFORMATICA E TELECOMUNICAZIONI": [
        "['office'='it']", "['office'='telecommunication']", "['telecom'='data_center']", "['office'='software']"
    ],
    "L - ATTIVITA' FINANZIARIE E ASSICURATIVE": [
        "['amenity'='bank']", "['office'='insurance']", "['amenity'='atm']", "['office'='financial']"
    ],
    "M - ATTIVITA' IMMOBILIARI": [
        "['office'='estate_agent']", "['office'='real_estate']"
    ],
    "N - ATTIVITA' PROFESSIONALI E SCIENTIFICHE": [
        "['office'='lawyer']", "['office'='accountant']", "['office'='architect']", 
        "['office'='research']", "['office'='consulting']"
    ],
    "O - ATTIVITA' AMMINISTRATIVE E SUPPORTO": [
        "['office'='government']", "['amenity'='townhall']", "['office'='employment_agency']"
    ],
    "P - ASSICURAZIONE SOCIALE OBBLIGATORIA": [
        "['office'='government']", "['amenity'='public_service']"
    ],
    "Q - ISTRUZIONE E FORMAZIONE": [
        "['amenity'='school']", "['amenity'='university']", "['amenity'='kindergarten']", "['amenity'='college']"
    ],
    "R - SALUTE E ASSISTENZA SOCIALE": [
        "['amenity'='hospital']", "['amenity'='doctors']", "['amenity'='pharmacy']", "['amenity'='social_facility']"
    ],
    "S - ATTIVITA' ARTISTICHE E SPORTIVE": [
        "['leisure'='sports_centre']", "['amenity'='cinema']", "['amenity'='theatre']", "['leisure'='stadium']", "['leisure'='fitness_centre']"
    ],
    "T - ALTRE ATTIVITA' DI SERVIZI": [
        "['shop'='hairdresser']", "['amenity'='grave_yard']", "['office'='association']", "['shop'='dry_cleaning']"
    ],
    "U - ATTIVITA' DI FAMIGLIE (Domestici)": [
        "['office'='employment_agency']"
    ],
    "V - ORGANIZZAZIONI EXTRATERRITORIALI": [
        "['office'='ngo']", "['amenity'='embassy']"
    ]
}

# --- 2. FUNZIONE DI RICERCA ---
def fetch_data(lat, lon, raggio_km, macrosettori):
    url = "https://overpass-api.de/api/interpreter"
    raggio_m = int(raggio_km * 1000)
    filtri = ""
    for ms in macrosettori:
        for t in ATECO_MAP.get(ms, []):
            filtri += f"nwr{t}(around:{raggio_m},{lat},{lon});\n"
    
    query = f"[out:json][timeout:90];({filtri});out tags center;"
    try:
        r = requests.get(url, params={'data': query}, timeout=100)
        elements = r.json().get('elements', [])
        ris = []
        for e in elements:
            t = e.get('tags', {})
            if 'name' in t:
                # Estrazione e formattazione parametri richiesti
                nome = t.get('name')
                comune = f"{t.get('addr:city', 'N.D.')}"
                cap = f"{t.get('addr:postcode', 'N.D.')}"
                indirizzo = f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip() or "N.D."
                attivita = f"{t.get('industrial', t.get('shop', t.get('amenity', t.get('craft', 'Azienda')))).replace('_', ' ').title()}"
                sito = f"{t.get('website', 'N.D.')}"
                email = f"{t.get('email', 'N.D.')}"
                linkedin = f"{t.get('contact:linkedin', t.get('linkedin', 'N.D.'))}"
                operatore = f"{t.get('operator', 'N.D.')}"
                brand = f"{t.get('brand', 'N.D.')}"
                
                ris.append({
                    'Ragione Sociale': nome,
                    'Comune': comune,
                    'CAP': cap,
                    'Indirizzo': indirizzo,
                    'Attività': attivita,
                    'Sito Web': sito,
                    'Email': email,
                    'LinkedIn': linkedin,
                    'Proprietà': operatore,
                    'Brand': brand,
                    'lat': e.get('lat') or e.get('center', {}).get('lat'),
                    'lon': e.get('lon') or e.get('center', {}).get('lon')
                })
        return pd.DataFrame(ris)
    except:
        return pd.DataFrame()

# --- 3. GESTIONE STATO ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- 4. INTERFACCIA ---
st.set_page_config(layout="wide")
st.title("🏢 Business Finder Professionale")

with st.sidebar:
    st.header("Parametri")
    raggio = st.slider("Raggio (KM)", 1, 30, 5)
    scelte = st.multiselect("Settori ATECO", list(ATECO_MAP.keys()), default=[list(ATECO_MAP.keys())[0]])
    
    st.divider()
    # Tasto Reset per pulire tutto
    if st.button("🗑️ Pulisci e Ricomincia"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- 5. LA MAPPA (UNICA E DINAMICA) ---
st.subheader("📍 1. Seleziona il punto sulla mappa | 2. Clicca 'Avvia Ricerca'")

# Creiamo la mappa base
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)

# Disegniamo il cerchio di scansione
folium.Circle(
    location=[st.session_state.pos['lat'], st.session_state.pos['lon']],
    radius=raggio * 1000, color="blue", fill=True, opacity=0.2
).add_to(m)

# Se ci sono risultati, aggiungiamo i marker dei risultati
if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker(
            [row['lat'], row['lon']], 
            popup=row['Ragione Sociale'],
            icon=folium.Icon(color='red', icon='briefcase')
        ).add_to(m)

# Visualizziamo la mappa
map_data = st_folium(m, width="100%", height=500, key="main_map")

# Se l'utente clicca, aggiorniamo la posizione e puliamo i vecchi risultati
if map_data and map_data['last_clicked']:
    nl, nn = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
    if abs(nl - st.session_state.pos['lat']) > 0.0001: # Evita loop infiniti
        st.session_state.pos = {'lat': nl, 'lon': nn}
        st.session_state.results = pd.DataFrame() # Reset risultati al cambio zona
        st.rerun()

# --- 6. AZIONE DI RICERCA ---
st.write(f"Coordinate selezionate: **{st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}**")

if st.button("🚀 AVVIA RICERCA ORA", use_container_width=True):
    with st.spinner("Scansione database..."):
        res = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
        if not res.empty:
            st.session_state.results = res
            st.rerun() # Ricarica per mostrare i puntini sulla mappa
        else:
            st.warning("Nessun risultato trovato in quest'area.")

# --- 7. TABELLA DATI ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("📋 Database Risultati")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)
    
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica CSV", csv, "export.csv", "text/csv")
