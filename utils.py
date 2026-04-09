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


def style_piva_comparison(row):
    """
    Funzione per colorare la cella in base al match tra Crawler e AI.
    """
    piva_crawler = str(row.get('Partita IVA', '')).strip()
    # Supponiamo che la colonna dell'AI si chiami 'PIVA AI'
    piva_ai = str(row.get('PIVA AI', '')).strip()
    
    # Se sono uguali e valide
    if piva_crawler == piva_ai and piva_crawler not in ['N.D.', 'Non trovata', '']:
        return ['background-color: #d4edda; color: #155724'] * len(row) # Verde
    # Se sono diverse o non trovate
    else:
        return ['background-color: #f8d7da; color: #721c24'] * len(row) # Rosso


from openai import OpenAI
import json

def ricerca_dati_ai(ragione_sociale, indirizzo, sito_web, piva_trovata, api_key):
    """
    Usa l'AI per validare la P.IVA e cercare di dedurre fatturato/dipendenti
    basandosi sulla conoscenza del modello e sui dati forniti.
    """
    if not api_key:
        return "N.D.", "N.D.", piva_trovata

    client = OpenAI(api_key=api_key)
    
    prompt = f"""
    Sei un analista finanziario. Dati i seguenti parametri di un'azienda italiana:
    - Ragione Sociale: {ragione_sociale}
    - Indirizzo: {indirizzo}
    - Sito Web: {sito_web}
    - P.IVA rilevata: {piva_trovata}

    Il tuo compito è:
    1. Confermare se la P.IVA è corretta per questa azienda.
    2. Fornire una stima del fatturato annuo (ultimo dato disponibile).
    3. Fornire il numero approssimativo di dipendenti.

    Rispondi ESCLUSIVAMENTE in formato JSON con queste chiavi:
    "piva_confermata", "fatturato", "dipendenti", "nota_affidabilita".
    Se non conosci i dati, scrivi "N.D.".
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Più economico per elaborazioni massive
            messages=[{"role": "system", "content": "Rispondi solo in JSON."},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        
        dati = json.loads(response.choices[0].message.content)
        return (
            dati.get("fatturato", "N.D."),
            dati.get("dipendenti", "N.D."),
            dati.get("piva_confermata", piva_trovata)
        )
    except Exception as e:
        return "Errore AI", "Errore AI", piva_trovata


