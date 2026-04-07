import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import re
from bs4 import BeautifulSoup
import time

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Intelligence Veneto")

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
        # Assicurati che ris = [] sia definito PRIMA del ciclo for
        ris = [] 
        
        for e in elements:
            t = e.get('tags', {})
            
            # Filtro: procediamo solo se l'elemento ha un nome
            if 'name' in t:
                # 1. Estrazione Coordinate (Fondamentale)
                # Overpass restituisce 'lat' per i nodi e 'center' per vie/aree
                lat_res = e.get('lat')
                lon_res = e.get('lon')
                
                if lat_res is None and 'center' in e:
                    lat_res = e['center'].get('lat')
                    lon_res = e['center'].get('lon')

                # 2. Se abbiamo le coordinate, estraiamo i dati
                if lat_res and lon_res:
                    # Pulizia stringhe e valori di default
                    nome = t.get('name', 'N.D.').strip()
                    comune = t.get('addr:city', 'N.D.')
                    cap = t.get('addr:postcode', 'N.D.')
                    
                    # Formattazione Indirizzo
                    via = t.get('addr:street', '')
                    civico = t.get('addr:housenumber', '')
                    indirizzo_completo = f"{via} {civico}".strip() or "N.D."
                    
                    # Identificazione Attività (Cascata di tag)
                    attivita_raw = (t.get('office') or t.get('industrial') or 
                                   t.get('shop') or t.get('craft') or 
                                   t.get('amenity') or 'Azienda')
                    attivita_pulita = attivita_raw.replace('_', ' ').title()
                    
                    # Contatti e Social
                    sito = t.get('website') or t.get('contact:website') or 'N.D.'
                    email = t.get('email') or t.get('contact:email') or 'N.D.'
                    linkedin = t.get('contact:linkedin') or t.get('linkedin') or 'N.D.'
                    
                    # 3. Riempimento della lista
                    ris.append({
                        'Ragione Sociale': nome,
                        'Comune': comune,
                        'CAP': cap,
                        'Indirizzo': indirizzo_completo,
                        'Attività': attivita_pulita,
                        'Sito Web': sito,
                        'Email': email,
                        'LinkedIn': linkedin,
                        'Proprietà': t.get('operator', 'N.D.'),
                        'Brand': t.get('brand', 'N.D.'),
                        'lat': lat_res,
                        'lon': lon_res
                    })
        return pd.DataFrame(ris)
    except:
        return pd.DataFrame()



# --- 3. GESTIONE STATO ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

def scrape_azienda_info(url):
    """Visita il sito web per estrarre P.IVA ed Email."""
    if not url or url == 'N.D.':
        return "N.D.", "N.D."
    
    if not url.startswith('http'):
        url = 'http://' + url
        
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(response.text, 'html.parser')
        testo = soup.get_text()

        # Regex per Partita IVA (11 cifre consecutive, spesso precedute da IT o P.IVA)
        piva_match = re.search(r'\b\d{11}\b', testo)
        piva = piva_match.group(0) if piva_match else "Non trovata"

        # Regex per Email
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
        email = email_match.group(0) if email_match else "Non trovata"

        return piva, email
    except:
        return "Errore Sito", "Errore Sito"

# --- 3. LOGICA INTERFACCIA ---

st.title("🏭 Business Data Extractor")
st.markdown("Trova aziende sulla mappa e scarica **Partita IVA** ed **Email** direttamente dai loro siti web.")

if 'pos' not in st.session_state: st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state: st.session_state.results = pd.DataFrame()

with st.sidebar:
    st.header("⚙️ Filtri Ricerca")
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali", list(ATECO_MAP.keys()))
    
    if st.button("🗑️ Reset"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- 4. MAPPA INTERATTIVA ---
st.subheader("1. Seleziona area e scansiona")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="100%", height=400, key="map_bi")

if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if new_lat != st.session_state.pos['lat']:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

if st.button("🚀 TROVA AZIENDE", use_container_width=True):
    if not scelte:
        st.warning("Seleziona almeno un settore!")
    else:
        with st.spinner("Ricerca in corso..."):
            df = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
            st.session_state.results = df
            st.rerun()

# --- 5. RISULTATI E SCRAPING ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Risultati")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)

    st.subheader("3. Arricchimento Dati (Web Crawler)")
    st.info("Questa funzione visiterà ogni sito web trovato per cercare la Partita IVA e l'Email ufficiale.")
    
    if st.button("🔍 ESTRAI P.IVA ED EMAIL DAI SITI WEB", use_container_width=True):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status = st.empty()
        
        count = len(df_work)
        for i, row in df_work.iterrows():
            if row['Sito Web'] != 'N.D.':
                status.text(f"Analisi sito: {row['Sito Web']}...")
                piva, email_web = scrape_azienda_info(row['Sito Web'])
                df_work.at[i, 'Partita IVA'] = piva
                if row['Email'] == 'N.D.':
                    df_work.at[i, 'Email'] = email_web
            
            progress_bar.progress((i + 1) / count)
        
        st.session_state.results = df_work
        status.success("✅ Arricchimento completato!")
        st.rerun()

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database Finale (CSV)", csv, "aziende_vicenza_full.csv", "text/csv")
