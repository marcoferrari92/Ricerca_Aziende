import streamlit as st
import requests
import re
import pandas as pd
import time
import googlemaps
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def is_valid_piva(piva):
    """Algoritmo di Luhn per validare la P.IVA."""
    if not piva or len(piva) != 11 or not piva.isdigit():
        return False
    s = 0
    for i in range(11):
        n = int(piva[i])
        if i % 2 == 1:
            n *= 2
            if n > 9: n -= 9
        s += n
    return s % 10 == 0

def scrape_sito_aziendale(url):
    """Cerca P.IVA ed Email navigando le pagine comuni del sito."""
    if not url or url == 'N.D.':
        return "N.D.", "N.D."
    if not url.startswith('http'): url = 'http://' + url
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    suffixes = ["", "/contatti", "/chi-siamo", "/privacy-policy", "/contacts", "/about", "/home"]
    piva_f, email_f = "Non trovata", "Non trovata"
    piva_pattern = r'(?:IT|P\.IVA|P\.I\.)?\s?(\d{11})'

    for sfx in suffixes:
        try:
            res = requests.get(url.rstrip('/') + sfx, headers=headers, timeout=5, verify=False)
            if res.status_code != 200: continue
            soup = BeautifulSoup(res.text, 'html.parser')
            testo = soup.get_text(separator=' ')
            
            if piva_f == "Non trovata":
                matches = re.findall(piva_pattern, testo)
                for m in matches:
                    if is_valid_piva(m):
                        piva_f = m
                        break
            
            if email_f == "Non trovata":
                em_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
                if em_match:
                    email_f = em_match.group(0).lower()

            if piva_f != "Non trovata" and email_f != "Non trovata": break
        except: continue
    return piva_f, email_f

def scrape_camerale_data(piva):
    """Placeholder per dati fatturato/dipendenti."""
    # Nota: L'estrazione di questi dati richiede API specifiche (es. Atoka, OpenCorporates) 
    # o scraping complesso di siti di business directory.
    return "N.D. (Richiede API)", "N.D."

@st.cache_data(show_spinner=False)
def fetch_data_google(lat, lon, raggio_km, keywords_list, api_key, max_results=50):
    try:
        gmaps = googlemaps.Client(key=api_key)
    except Exception as e:
        st.error(f"Errore connessione Google: {e}")
        return pd.DataFrame()

    ris = []
    raggio_m = int(raggio_km * 1000)
    count = 0

    for kw in keywords_list:
        if count >= max_results: break
        try:
            # Ricerca iniziale
            response = gmaps.places_nearby(location=(lat, lon), radius=raggio_m, keyword=kw)
            
            while True:
                results = response.get('results', [])
                for place in results:
                    if count >= max_results: break
                    
                    # Dettagli singoli
                    details = gmaps.place(
                        place['place_id'], 
                        fields=['name', 'formatted_address', 'website', 'geometry', 'business_status'],
                        language='it'
                    ).get('result', {})
                    
                    s_raw = details.get('business_status', 'N.D.')
                    s_ita = {'OPERATIONAL': 'Attiva', 'CLOSED_TEMPORARILY': 'Chiusa Temp.'}.get(s_raw, 'N.D.')
                    
                    ris.append({
                        'Ragione Sociale': details.get('name', 'N.D.'),
                        'Stato': s_ita,
                        'Sito Web': details.get('website', 'N.D.'),
                        'Indirizzo': details.get('formatted_address', 'N.D.'),
                        'Partita IVA': 'N.D.',
                        'Email': 'N.D.',
                        'Fatturato': 'N.D.',
                        'Dipendenti': 'N.D.',
                        'lat': details.get('geometry', {}).get('location', {}).get('lat'),
                        'lon': details.get('geometry', {}).get('location', {}).get('lng')
                    })
                    count += 1
                
                token = response.get('next_page_token')
                if not token or count >= max_results: break
                time.sleep(2) 
                response = gmaps.places_nearby(page_token=token)
        except Exception as e:
            continue
            
    return pd.DataFrame(ris).drop_duplicates(subset=['Ragione Sociale']) if ris else pd.DataFrame()




