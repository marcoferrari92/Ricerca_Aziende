import streamlit as st
import requests
import re
import pandas as pd
import time
import googlemaps
from bs4 import BeautifulSoup
import urllib3
import json
from openai import OpenAI
from urllib.parse import urljoin

# Disabilita avvisi SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. RICERCA GOOGLE MAPS ---
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
        if count >= max_results: 
            break
        try:
            response = gmaps.places_nearby(location=(lat, lon), radius=raggio_m, keyword=kw)
            
            while True:
                results = response.get('results', [])
                for place in results:
                    if count >= max_results: 
                        break
                    
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
                        'P.IVA (Crawler)': 'N.D.',
                        'Email (Crawler)': 'N.D.',
                        'P.IVA (AI)': 'N.D.',
                        'Fatturato (AI)': 'N.D.',
                        'Dipendenti (AI)': 'N.D.',
                        'Nota/Fonte (AI)': 'N.D.',
                        'lat': details.get('geometry', {}).get('location', {}).get('lat'),
                        'lon': details.get('geometry', {}).get('location', {}).get('lng'),
                        'testo_raw': ''
                    })
                    count += 1
                
                token = response.get('next_page_token')
                if not token or count >= max_results: 
                    break
                time.sleep(2) 
                response = gmaps.places_nearby(page_token=token)
        except Exception:
            continue
            
    if not ris:
        return pd.DataFrame()
    return pd.DataFrame(ris).drop_duplicates(subset=['Ragione Sociale'])

# --- 2. VALIDAZIONE E CRAWLING ---
def is_valid_piva(piva):
    if not piva or len(piva) != 11 or not piva.isdigit():
        return False
    s = sum(int(piva[i]) for i in range(0, 10, 2))
    for i in range(1, 10, 2):
        temp = int(piva[i]) * 2
        s += temp if temp <= 9 else temp - 9
    check = (10 - s % 10) % 10
    return check == int(piva[-1])

def cerca_piva(testo):
    if not testo: 
        return None
    piva_pattern = r'(?i)(?:P\.?\s*IVA|VAT|Partita\s*IVA|P\s*I|C\.F\.|CF)[:\s-]{1,6}(\d{11})\b'
    matches = re.findall(piva_pattern, testo)
    for m in matches:
        if is_valid_piva(m):
            return m
    return None

def scrape_sito_aziendale(url):
    if not url or url == 'N.D.':
        return "Non trovata", "Non trovata", ""

    if not url.startswith('http'):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    visited = set()
    to_visit = [url]
    piva_f, email_f = "Non trovata", "Non trovata"
    testo_per_ai = ""

    while to_visit and len(visited) < 5:
        current = to_visit.pop(0)
        if current in visited: 
            continue
        visited.add(current)

        try:
            res = requests.get(current, headers=headers, timeout=8, verify=False)
            if res.status_code != 200: 
                continue
            
            html = res.text
            soup = BeautifulSoup(html, 'html.parser')

            # Ricerca nei Meta Tag
            if piva_f == "Non trovata":
                meta_content = " ".join([tag.get('content', '') for tag in soup.find_all('meta')])
                found = cerca_piva(meta_content)
                if found: 
                    piva_f = found

            # Pulizia HTML
            for el in soup(["script", "style", "nav", "header"]): 
                el.decompose()

            text = soup.get_text(separator=' ', strip=True)
            if len(testo_per_ai) < 6000:
                testo_per_ai += f" [URL: {current}] " + text

            # Ricerca P.IVA nel testo
            if piva_f == "Non trovata":
                piva_f = cerca_piva(text) or "Non trovata"

            # Ricerca Email
            if email_f == "Non trovata":
                em = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                if em: 
                    email_f = em.group(0).lower()

            # Link interni
            for link in soup.find_all('a', href=True):
                href = link['href']
                full = urljoin(url, href)
                if any(k in full.lower() for k in ['contatti', 'contact', 'about', 'chi-siamo', 'legal', 'privacy']):
                    if full not in visited:
                        to_visit.append(full)

            if piva_f != "Non trovata" and email_f != "Non trovata":
                break
        except:
            continue

    return piva_f, email_f, testo_per_ai[:6000]

# --- 3. ANALISI AI ---
def chiedi_a_openai(nome_azienda, piva_crawler, sito, indirizzo, testo_sito, api_key_openai):
    if not api_key_openai:
        return "N.D.", "N.D.", "N.D.", "Manca Key"

    client = OpenAI(api_key=api_key_openai)
    
    prompt = f"""
    Sei un investigatore economico esperto in aziende italiane.
    Trova i dati fiscali per: {nome_azienda}
    Sede: {indirizzo}
    Sito: {sito}

    TESTO ESTRATTO DAL SITO:
    ---
    {testo_sito[:4000]}
    ---

    ISTRUZIONI TASSATIVE:
    1. PARTITA IVA: Verifica '{piva_crawler}'. Se è N.D., estraila dal testo (11 cifre).
    2. FATTURATO E DIPENDENTI: Cerca dati recenti o fornisci una stima basata sulla tua conoscenza.
    3. JSON: Rispondi solo in formato JSON.

    Rispondi in JSON: {{"fatturato": "...", "dipendenti": "...", "piva": "...", "fonte": "..."}}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": "Sei un assistente esperto in dati camerali. Rispondi solo in JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            temperature=0.2
        )
        
        data = json.loads(response.choices[0].message.content)
        
        raw_piva = str(data.get("piva", "N.D."))
        piva_solo_numeri = "".join(filter(str.isdigit, raw_piva))
        
        # Validazione incrociata
        if is_valid_piva(piva_solo_numeri):
            piva_finale = piva_solo_numeri
        elif piva_crawler != "Non trovata" and is_valid_piva(piva_crawler):
            piva_finale = piva_crawler
        else:
            piva_finale = "N.D. (Invalida)"

        return (
            str(data.get("fatturato", "N.D.")), 
            str(data.get("dipendenti", "N.D.")), 
            piva_finale, 
            str(data.get("fonte", "Analisi AI"))
        )
    except Exception as e:
        return "Errore AI", "N.D.", "N.D.", str(e)
