import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import re
from bs4 import BeautifulSoup
import time
from mapping import ATECO_MAP  # Import dal tuo file esterno

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor")

# --- 2. FUNZIONI DI SCRAPING E UTILITY ---

def scrape_azienda_info(url):
    """Fase 1: Estrae P.IVA ed Email dal sito ufficiale dell'azienda."""
    if not url or url == 'N.D.':
        return "N.D.", "N.D."
    if not url.startswith('http'):
        url = 'http://' + url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(response.text, 'html.parser')
        testo = soup.get_text()

        # Regex per Partita IVA (11 cifre)
        piva_match = re.search(r'\b\d{11}\b', testo)
        piva = piva_match.group(0) if piva_match else "Non trovata"

        # Regex per Email
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
        email = email_match.group(0) if email_match else "Non trovata"

        return piva, email
    except:
        return "Errore Sito", "N.D."

def scrape_camerale_data(piva):
    """Fase 2: Cerca Fatturato e Dipendenti su portale pubblico usando la P.IVA."""
    if not piva or piva in ["Non trovata", "Errore Sito", "N.D."] or len(piva) != 11:
        return "N.D.", "N.D."
    
    # URL di ricerca basato su P.IVA
    search_url = f"https://www.reportaziende.it/ricerca?q={piva}"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # Piccola pausa per evitare blocchi IP
        time.sleep(0.5)
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        testo = soup.get_text()

        # Regex flessibili per catturare i dati dal testo della pagina
        fatt_pattern = r'Fatturato[:\s]*([\d.,]+\s*(?:€|euro|milioni|mln))'
        dip_pattern = r'Dipendenti[:\s]*(\d+)'

        fatt_match = re.search(fatt_pattern, testo, re.IGNORECASE)
        dip_match = re.search(dip_pattern, testo, re.IGNORECASE)

        fatturato = fatt_match.group(1) if fatt_match else "Vedi online"
        dipendenti = dip_match.group(1) if dip_match else "N.D."

        return fatturato, dipendenti
    except:
        return "N.D.", "N.D."

# --- 3. FUNZIONE DI RICERCA (Inalterata come richiesto) ---
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
                lat_res = e.get('lat')
                lon_res = e.get('lon')
                
                if lat_res is None and 'center' in e:
                    lat_res = e['center'].get('lat')
                    lon_res = e['center'].get('lon')

                if lat_res and lon_res:
                    nome = t.get('name', 'N.D.').strip()
                    comune = t.get('addr:city', 'N.D.')
                    cap = t.get('addr:postcode', 'N.D.')
                    via = t.get('addr:street', '')
                    civico = t.get('addr:housenumber', '')
                    indirizzo_completo = f"{via} {civico}".strip() or "N.D."
                    
                    attivita_raw = (t.get('office') or t.get('industrial') or 
                                   t.get('shop') or t.get('craft') or 
                                   t.get('amenity') or 'Azienda')
                    attivita_pulita = attivita_raw.replace('_', ' ').title()
                    
                    sito = t.get('website') or t.get('contact:website') or 'N.D.'
                    email = t.get('email') or t.get('contact:email') or 'N.D.'
                    linkedin = t.get('contact:linkedin') or t.get('linkedin') or 'N.D.'
                    
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
                        'Partita IVA': 'N.D.',
                        'Fatturato': 'N.D.',
                        'Dipendenti': 'N.D.',
                        'lat': lat_res,
                        'lon': lon_res
                    })
        return pd.DataFrame(ris)
    except:
        return pd.DataFrame()

# --- 4. GESTIONE STATO ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

# --- 5. INTERFACCIA UTENTE ---
st.title("🏭 Business Data Extractor")
st.markdown("Trova aziende sulla mappa e arricchisci i dati con **P.IVA**, **Email**, **Fatturato** e **Dipendenti**.")

with st.sidebar:
    st.header("⚙️ Filtri Ricerca")
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali", list(ATECO_MAP.keys()))
    
    if st.button("🗑️ Reset Database"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

st.subheader("1. Seleziona area e scansiona")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="100%", height=400, key="map_bi")

if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if abs(new_lat - st.session_state.pos['lat']) > 0.0001:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

if st.button("🚀 TROVA AZIENDE NELL'AREA", use_container_width=True):
    if not scelte:
        st.warning("Seleziona almeno un settore dalla barra laterale!")
    else:
        with st.spinner("Scansione OpenStreetMap in corso..."):
            df = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
            st.session_state.results = df
            st.rerun()

# --- 6. RISULTATI E SCRAPING AVANZATO ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Aziende Trovate")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)

    st.subheader("3. Arricchimento Profondo (Web Crawler)")
    st.info("Questo processo cercherà la P.IVA sui siti aziendali e userà quel dato per recuperare il bilancio (Fatturato/Dipendenti).")
    
    if st.button("🔍 ESTRAI DATI COMPLETI (P.IVA + BILANCIO)", use_container_width=True):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status_msg = st.empty()
        
        count = len(df_work)
        for i, row in df_work.iterrows():
            if row['Sito Web'] != 'N.D.':
                status_msg.text(f"Analisi: {row['Ragione Sociale']}...")
                
                # Step 1: P.IVA dal sito ufficiale
                piva, email_web = scrape_azienda_info(row['Sito Web'])
                df_work.at[i, 'Partita IVA'] = piva
                if row['Email'] == 'N.D.':
                    df_work.at[i, 'Email'] = email_web
                
                # Step 2: Fatturato e Dipendenti tramite P.IVA
                if piva != "Non trovata" and piva != "Errore Sito":
                    fatt, dip = scrape_camerale_data(piva)
                    df_work.at[i, 'Fatturato'] = fatt
                    df_work.at[i, 'Dipendenti'] = dip
            
            progress_bar.progress((i + 1) / count)
        
        st.session_state.results = df_work
        status_msg.success("✅ Arricchimento completato con successo!")
        st.rerun()

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database Finale (CSV)", csv, "database_aziende.csv", "text/csv")
