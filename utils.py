import streamlit as st
import requests
import re
import pandas as pd
import time
import googlemaps
from bs4 import BeautifulSoup

def is_valid_piva(piva):
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
    if not url or url == 'N.D.':
        return "N.D.", "N.D."
    if not url.startswith('http'): url = 'http://' + url
    headers = {'User-Agent': 'Mozilla/5.0...'}
    suffixes = ["", "/contatti", "/chi-siamo", "/privacy-policy"]
    piva_final, email_final = "Non trovata", "Non trovata"
    piva_pattern = r'(?:IT|P\.IVA|P\.I\.)?\s?(\d{11})'

    try:
        for suffix in suffixes:
            res = requests.get(url.rstrip('/') + suffix, headers=headers, timeout=5, verify=False)
            if res.status_code != 200: continue
            soup = BeautifulSoup(res.text, 'html.parser')
            testo = soup.get_text()
            
            if piva_final == "Non trovata":
                match = re.search(piva_pattern, testo)
                if match:
                    cifre = "".join(filter(str.isdigit, match.group(0)))
                    if is_valid_piva(cifre): piva_final = cifre
            
            if email_final == "Non trovata":
                email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
                if email_match: email_final = email_match.group(0)
            
            if piva_final != "Non trovata" and email_final != "Non trovata": break
    except: pass
    return piva_final, email_final

@st.cache_data(show_spinner=False)
def fetch_data_google(lat, lon, raggio_km, keywords_list, api_key, max_results=50):
    gmaps = googlemaps.Client(key=api_key)
    ris = []
    raggio_m = int(raggio_km * 1000)
    count_aziende = 0

    for kw in keywords_list:
        if count_aziende >= max_results: break
        try:
            response = gmaps.places_nearby(location=(lat, lon), radius=raggio_m, keyword=kw)
            while True:
                results = response.get('results', [])
                for place in results:
                    if count_aziende >= max_results: break
                    details = gmaps.place(place['place_id'], fields=['name', 'formatted_address', 'website', 'geometry'], language='it')['result']
                    
                    ris.append({
                        'Ragione Sociale': details.get('name', 'N.D.'),
                        'Sito Web': details.get('website', 'N.D.'),
                        'Indirizzo': details.get('formatted_address', 'N.D.'),
                        'Partita IVA': 'N.D.',
                        'Email': 'N.D.',
                        'Fatturato': 'N.D.',
                        'Dipendenti': 'N.D.',
                        'lat': details['geometry']['location']['lat'],
                        'lon': details['geometry']['location']['lng']
                    })
                    count_aziende += 1
                
                token = response.get('next_page_token')
                if not token or count_aziende >= max_results: break
                time.sleep(2)
                response = gmaps.places_nearby(page_token=token)
        except: continue
    return pd.DataFrame(ris)
