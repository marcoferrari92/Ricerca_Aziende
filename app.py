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


# --- 2. FUNZIONE DI RICERCA AZIENDE SULLE MAPPE ---
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


def scrape_sito_aziendale(url):
    """FASE 1: Cerca P.IVA ed Email sul sito ufficiale."""
    if not url or url == 'N.D.': return "N.D.", "N.D.", "N.D."
    if not url.startswith('http'): url = 'http://' + url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        testo = soup.get_text()
        
        piva = re.search(r'\b\d{11}\b', testo)
        email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
        # Tentativo di trovare fatturato se scritto esplicitamente nel sito (es. "Fatturato 2024: ...")
        fatt = re.search(r'Fatturato[:\s]*([\d.,]+\s*(?:€|euro|milioni|mln))', testo, re.I)
        
        return (piva.group(0) if piva else "N.D.", 
                email.group(0) if email else "N.D.",
                fatt.group(1) if fatt else "N.D.")
    except: return "Errore", "N.D.", "N.D."

def scrape_portale_camerale(piva):
    """FASE 2: Cerca dati ufficiali di bilancio (Versione Potenziata)."""
    if piva in ["N.D.", "Errore", "Non trovata"] or len(piva) != 11:
        return "N.D.", "N.D."
    
    # Proviamo ReportAziende che è solitamente più leggibile
    url = f"https://www.reportaziende.it/ricerca?q={piva}"
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Language': 'it-IT,it;q=0.9'
        }
        time.sleep(1.5) # Aumentato il delay per sicurezza
        res = requests.get(url, headers=headers, timeout=10)
        
        # Usiamo BeautifulSoup per isolare il testo "pulito"
        soup = BeautifulSoup(res.text, 'html.parser')
        testo = soup.get_text(separator=' ').strip()

        # Regex migliorata: cerca la parola fatturato e cattura i numeri/simboli successivi
        # Gestisce: "Fatturato € 1.234.567", "Fatturato 2024: 10mln", ecc.
        fatt_pattern = r'fatturato\s*(?:\d{4})?[:\s-]*([€\d.,\s]+(?:milioni|mila|mln|k|euro|€)?)'
        dip_pattern = r'dipendenti[:\s-]*(\d+)'

        fatt_match = re.search(fatt_pattern, testo, re.IGNORECASE)
        dip_match = re.search(dip_pattern, testo, re.IGNORECASE)

        # Pulizia del risultato per togliere spazi inutili
        fatturato = fatt_match.group(1).strip() if fatt_match else "Controlla link"
        dipendenti = dip_match.group(1).strip() if dip_match else "N.D."

        # Se il fatturato estratto è troppo corto (es. solo un simbolo), resettiamo
        if len(fatturato) < 2: fatturato = "Vedi online"

        return fatturato, dipendenti
    except Exception as e:
        return f"Errore: {str(e)[:10]}", "Errore"

# --- 3. INTERFACCIA ---

if 'results' not in st.session_state: st.session_state.results = pd.DataFrame()
if 'pos' not in st.session_state: st.session_state.pos = {'lat': 45.547, 'lon': 11.545}

st.title("🏭 Business Intelligence Pro")

with st.sidebar:
    raggio = st.slider("Raggio (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori", list(ATECO_MAP.keys()))
    if st.button("Reset"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# Sezione 1: Mappa e Ricerca
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
st_folium(m, width="100%", height=300)

if st.button("🚀 1. TROVA AZIENDE NELL'AREA", use_container_width=True):
    st.session_state.results = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
    st.rerun()

# Sezione 2: Elaborazione Dati
if not st.session_state.results.empty:
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🌐 2. SCANSIONA SITI (P.IVA + EMAIL)", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
            for i, row in df.iterrows():
                p, e, f = scrape_sito_aziendale(row['Sito Web'])
                df.at[i, 'Partita IVA'] = p
                if row['Email'] == 'N.D.': df.at[i, 'Email'] = e
                df.at[i, 'Fatturato (da sito)'] = f
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()
            
    with col2:
        # Il secondo pulsante funziona solo se abbiamo trovato almeno una P.IVA
        if st.button("📊 3. RICERCA CAMERALE (BILANCI)", use_container_width=True):
            df = st.session_state.results.copy()
            bar = st.progress(0)
            for i, row in df.iterrows():
                f_c, d = scrape_portale_camerale(row['Partita IVA'])
                df.at[i, 'Fatturato (Camerale)'] = f_c
                df.at[i, 'Dipendenti'] = d
                bar.progress((i + 1) / len(df))
            st.session_state.results = df
            st.rerun()

    # Download
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 SCARICA DATABASE CSV", csv, "aziende_bi_veneto.csv", "text/csv")
