import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import re
from bs4 import BeautifulSoup
from mapping import ATECO_MAP  # Import dal tuo file esterno

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor")

# --- 2. FUNZIONE DI RICERCA (Inalterata) ---
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
                        'lat': lat_res,
                        'lon': lon_res
                    })
        return pd.DataFrame(ris)
    except:
        return pd.DataFrame()

# --- 3. GESTIONE STATO E UTILITY ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.547, 'lon': 11.545}
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()

def scrape_camerale_data(piva):
    """Interroga un portale di dati aziendali pubblici usando la P.IVA."""
    if not piva or piva == "Non trovata" or len(piva) != 11:
        return "N.D.", "N.D."
    
    # Portale di appoggio (Esempio: ReportAziende usa la P.IVA nell'URL)
    search_url = f"https://www.reportaziende.it/ricerca?q={piva}"
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        testo = soup.get_text()

        # Regex per Fatturato (cerca cifre seguite da € o parole come 'milioni')
        # Questi pattern dipendono da come il sito scelto visualizza i dati
        fatt_pattern = r'Fatturato[:\s]*([\d.,]+\s*(?:€|euro|milioni|mln))'
        dip_pattern = r'Dipendenti[:\s]*(\d+)'

        fatt_match = re.search(fatt_pattern, testo, re.IGNORECASE)
        dip_match = re.search(dip_pattern, testo, re.IGNORECASE)

        fatturato = fatt_match.group(1) if fatt_match else "Vedi scheda"
        dipendenti = dip_match.group(1) if dip_match else "Vedi scheda"

        return fatturato, dipendenti
    except:
        return "N.D.", "N.D."

# --- Modifica nel ciclo di scraping in app.py ---
if st.button("🔍 ESTRAI DATI COMPLETI (P.IVA + BILANCIO)", use_container_width=True):
    df_work = st.session_state.results.copy()
    progress_bar = st.progress(0)
    status = st.empty()
    
    for i, row in df_work.iterrows():
        if row['Sito Web'] != 'N.D.':
            status.text(f"Analisi sito aziendale per P.IVA: {row['Ragione Sociale']}...")
            # 1. Troviamo la P.IVA dal sito ufficiale
            piva, email_web = scrape_azienda_info(row['Sito Web'])
            df_work.at[i, 'Partita IVA'] = piva
            
            # 2. Se abbiamo la P.IVA, cerchiamo il fatturato sul portale camerale
            if piva != "Non trovata":
                status.text(f"Recupero dati camerali per P.IVA {piva}...")
                fatt, dip = scrape_camerale_data(piva)
                df_work.at[i, 'Fatturato'] = fatt
                df_work.at[i, 'Dipendenti'] = dip
        
        progress_bar.progress((i + 1) / len(df_work))
    
    st.session_state.results = df_work
    st.success("✅ Database arricchito con dati di bilancio!")
    st.rerun()

# --- 4. INTERFACCIA ---
st.title("🏭 Business Data Extractor")
st.markdown("Trova aziende sulla mappa e arricchisci i dati con Partita IVA ed Email dai siti web.")

with st.sidebar:
    st.header("⚙️ Filtri Ricerca")
    raggio = st.slider("Raggio Scansione (KM)", 1, 20, 5)
    scelte = st.multiselect("Settori Aziendali", list(ATECO_MAP.keys()))
    
    if st.button("🗑️ Reset"):
        st.session_state.results = pd.DataFrame()
        st.rerun()

st.subheader("1. Seleziona area e scansiona")
m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio*1000, color="blue", fill=True, opacity=0.1).add_to(m)

if not st.session_state.results.empty:
    for _, row in st.session_state.results.iterrows():
        folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

map_res = st_folium(m, width="100%", height=400, key="map_bi")

# Spostamento centro mappa al click
if map_res and map_res['last_clicked']:
    new_lat, new_lon = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
    if abs(new_lat - st.session_state.pos['lat']) > 0.0001:
        st.session_state.pos = {'lat': new_lat, 'lon': new_lon}
        st.rerun()

if st.button("🚀 TROVA AZIENDE", use_container_width=True):
    if not scelte:
        st.warning("Seleziona almeno un settore!")
    else:
        with st.spinner("Ricerca su OpenStreetMap..."):
            df = fetch_data(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, scelte)
            st.session_state.results = df
            st.rerun()

# --- 5. RISULTATI E SCRAPING ---
if not st.session_state.results.empty:
    st.divider()
    st.subheader("2. Database Risultati")
    # Escludiamo le coordinate dalla visualizzazione tabella per pulizia
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon']), use_container_width=True)

    st.subheader("3. Arricchimento Dati (Web Crawler)")
    st.info("Estrai P.IVA ed Email visitando i siti web delle aziende in tabella.")
    
    if st.button("🔍 AVVIA SCRAPING SITI WEB", use_container_width=True):
        df_work = st.session_state.results.copy()
        progress_bar = st.progress(0)
        status = st.empty()
        
        count = len(df_work)
        for i, row in df_work.iterrows():
            if row['Sito Web'] != 'N.D.':
                status.text(f"Analisi: {row['Ragione Sociale']}...")
                piva, email_web = scrape_azienda_info(row['Sito Web'])
                df_work.at[i, 'Partita IVA'] = piva
                # Sovrascrivi Email solo se N.D.
                if row['Email'] == 'N.D.':
                    df_work.at[i, 'Email'] = email_web
            
            progress_bar.progress((i + 1) / count)
        
        st.session_state.results = df_work
        status.success("✅ Arricchimento completato!")
        st.rerun()

    # Download CSV
    csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
    st.download_button("📥 Scarica Database Finale (CSV)", csv, "aziende_export.csv", "text/csv")
