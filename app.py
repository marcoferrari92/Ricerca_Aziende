import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from googlesearch import search
from bs4 import BeautifulSoup
import time

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

# --- 3. MOTORE ANALISI IA (NEWS SCRAPER & SUMMARIZER) ---
def analizza_sicurezza_ia(nome_azienda):
    # Query specifica su ANSA e testate locali
    query = f'site:ansa.it OR site:ilgiornaledivicenza.it "{nome_azienda}" "sicurezza sul lavoro" OR "infortunio" OR "ispettorato"'
    try:
        links = list(search(query, num_results=2, lang="it"))
        if not links:
            return "✅ Nessuna criticità rilevata nelle testate monitorate (ANSA/Locale).", "green"

        testo_news = ""
        for url in links[:2]:
            res = requests.get(url, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            testo_news += " ".join([p.get_text() for p in soup.find_all('p')[:3]])

        # Simulazione del riassunto IA (In un caso reale qui chiameresti le API del modello)
        if "infortunio" in testo_news.lower() or "incidente" in testo_news.lower():
            return f"⚠️ ALERT: Trovate notizie critiche su {nome_azienda}. Possibili incidenti o ispezioni rilevate. Verificare link: {links[0]}", "red"
        else:
            return f"ℹ️ INFO: L'azienda appare in notizie riguardanti protocolli o certificazioni di sicurezza. Link: {links[0]}", "orange"
    except:
        return "⚠️ Servizio news momentaneamente non disponibile.", "gray"

# --- 4. INTERFACCIA UTENTE ---
st.title("🛡️ Business Intelligence & Safety Monitor")

if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

with st.sidebar:
    st.header("⚙️ Configurazione")
    raggio = st.slider("Raggio Scansione (KM)", 1, 30, 5)
    scelte = st.multiselect("Macrosettori ATECO", list(ATECO_MAP.keys()), default=["A - AGRICOLTURA, SILVICOLTURA E PESCA"])
    st.divider()
    if st.button("🗑️ Pulisci Tutto"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# MAPPA INTERATTIVA
st.subheader("📍 Seleziona l'area di analisi")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], popup=row['Ragione Sociale']).add_to(m)

map_data = st_folium(m, width="100%", height=400, key="main_map")

if map_data and map_data['last_clicked']:
    nl, nn = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
    if abs(nl - st.session_state.pos['lat']) > 0.001:
        st.session_state.pos = {'lat': nl, 'lon': nn}
        st.rerun()

# PULSANTE SCANSIONE
if st.button("🚀 AVVIA SCANSIONE AZIENDALE", use_container_width=True):
    with st.spinner("Interrogazione database cartografici..."):
        res = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
        if not res.empty:
            st.session_state.results = res
            st.rerun()
        else:
            st.warning("Nessuna azienda trovata in quest'area.")

# VISUALIZZAZIONE DATI E ANALISI IA
if not st.session_state.results.empty:
    st.divider()
    st.subheader("📋 Database Aziende Rilevate")
    cols = ['Ragione Sociale', 'Comune', 'CAP', 'Indirizzo', 'Attività', 'Sito Web', 'Email', 'LinkedIn', 'Proprietà', 'Brand']
    st.dataframe(st.session_state.results[cols], use_container_width=True)

    st.divider()
    st.subheader("🤖 AI Safety Insight (ANSA/News Monitor)")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        azienda_target = st.selectbox("Seleziona un'azienda per il Report Sicurezza", st.session_state.results['Ragione Sociale'])
    with col2:
        st.write(" ") # Spazio estetico
        btn_ia = st.button("🔍 GENERA REPORT SICUREZZA IA")

    if btn_ia:
        with st.spinner(f"L'IA sta analizzando la reputazione di {azienda_target}..."):
            report, colore = analizza_sicurezza_ia(azienda_target)
            if colore == "green": st.success(report)
            elif colore == "orange": st.info(report)
            elif colore == "red": st.error(report)
            else: st.write(report)

    # Download CSV
    csv = st.session_state.results[cols].to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database (CSV)", csv, "intelligence_aziendale.csv", "text/csv")
