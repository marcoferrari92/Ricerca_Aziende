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

# --- 3. MOTORE ANALISI IA MULTI-FONTE (ANSA + LOCALI) ---
def analizza_sicurezza_ia_multi(nome_azienda):
    # Definiamo i domini su cui cercare
    fonti = [
        "site:ansa.it", 
        "site:ilgiornaledivicenza.it", 
        "site:ilgazzettino.it", 
        "site:corrieredelveneto.corriere.it",
        "site:vicenzatoday.it",
        "site:www.vicenzatoday.it"
    ]
    
    # Query: (Fonti) + "Nome Azienda" + (Keywords Sicurezza)
    query = f'({" OR ".join(fonti)}) "{nome_azienda}" "sicurezza sul lavoro" OR "infortunio" OR "ispettorato" OR "spisal"'
    
    try:
        # Cerchiamo i primi 3 link più rilevanti tra tutte le fonti
        links = list(search(query, num_results=3, lang="it"))
        
        if not links:
            return "✅ Nessuna segnalazione critica trovata su testate nazionali o locali (Vicenza/Veneto).", "green"

        testo_aggregato = ""
        for url in links[:2]:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'} # Per evitare blocchi immediati
                res = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(res.text, 'html.parser')
                # Estraiamo i primi paragrafi significativi
                testo_aggregato += " ".join([p.get_text() for p in soup.find_all('p')[:3]])
            except: continue

        # Analisi del sentiment/contenuto (Simulazione IA)
        keywords_alert = ["infortunio", "incidente", "mortale", "grave", "caduta", "spisal", "sequestro", "indagine"]
        testo_lower = testo_aggregato.lower()
        
        if any(key in testo_lower for key in keywords_alert):
            return f"⚠️ ALERT SICUREZZA RILEVATO: Sono presenti articoli su testate locali/nazionali riguardanti incidenti o ispezioni. Fonte principale: {links[0]}", "red"
        elif "certificazione" in testo_lower or "formazione" in testo_lower:
            return f"ℹ️ INFO POSITIVA: L'azienda appare in articoli riguardanti formazione o nuovi protocolli di sicurezza. Fonte: {links[0]}", "orange"
        else:
            return f"🧐 NOTIZIA GENERICA: Trovata menzione dell'azienda in contesti legati alla sicurezza. Verificare dettaglio qui: {links[0]}", "blue"
            
    except Exception as e:
        return f"⚠️ Errore durante il monitoraggio news: {str(e)}", "gray"

# --- 4. INTERFACCIA STREAMLIT ---
st.title("🏢 Intelligence Aziendale Veneto")
st.markdown("Monitoraggio geografico ATECO con analisi reputazionale su **ANSA** e **Giornali Locali**.")

if 'pos' not in st.session_state: st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state: st.session_state.results = pd.DataFrame()

# Sidebar
with st.sidebar:
    st.header("⚙️ Parametri Scansione")
    raggio = st.slider("Raggio (KM)", 1, 30, 5)
    scelte = st.multiselect("Settori ATECO", list(ATECO_MAP.keys()))
    if st.button("🗑️ Reset Dati"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# Mappa
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="#3186cc", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

st_folium(m, width="100%", height=400, key="main_map")

# Pulsante Ricerca
if st.button("🚀 SCANSIONA AREA SELEZIONATA", use_container_width=True):
    with st.spinner("Analisi cartografica in corso..."):
        res = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
        if not res.empty:
            st.session_state.results = res
            st.rerun()
        else: st.warning("Nessuna azienda trovata. Clicca su un'altra zona della mappa.")

# Risultati e Analisi IA
if not st.session_state.results.empty:
    st.divider()
    st.subheader("📋 Aziende Rilevate")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)

    st.divider()
    st.subheader("🤖 Analisi Sicurezza IA (ANSA + Giornali Locali)")
    target = st.selectbox("Seleziona l'azienda da analizzare:", st.session_state.results['Ragione Sociale'])
    
    if st.button("🔍 GENERA REPORT REPUTAZIONALE"):
        with st.spinner(f"L'IA sta consultando l'archivio storico di ANSA, Giornale di Vicenza e Gazzettino per {target}..."):
            report, colore = analizza_sicurezza_ia_multi(target)
            if colore == "red": st.error(report)
            elif colore == "orange": st.warning(report)
            elif colore == "green": st.success(report)
            else: st.info(report)

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database CSV", csv, "export_vicenza.csv", "text/csv")
