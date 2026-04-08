import streamlit as st
import requests
import re
import pandas as pd
import random
import urllib3
import googlemaps
from bs4 import BeautifulSoup
from mapping import ATECO_MAP

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
    piva_clean = "".join(filter(str.isdigit, str(piva)))
    url = f"https://www.fatturatoitalia.it/ricerca?q={piva_clean}"
    
    # Headers estremamente realistici
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Ch-Ua': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Upgrade-Insecure-Requests': '1'
    }

    try:
        # Usiamo una sessione per gestire i cookie (fondamentale per FatturatoItalia)
        session = requests.Session()
        # Facciamo una prima chiamata alla home per prendere i cookie
        session.get("https://www.fatturatoitalia.it/", headers=headers, timeout=10, verify=False)
        
        # Ora facciamo la ricerca vera
        res = session.get(url, headers=headers, timeout=15, verify=False)
        
        # Restituiamo il testo per vedere cosa succede
        return res.text[:5000], "DEBUG"

    except Exception as e:
        return f"ERRORE FISICO: {str(e)}", "N.D."



@st.cache_data(show_spinner=False)
@st.cache_data(show_spinner=False)
def fetch_data_google(lat, lon, raggio_km, keywords_list, api_key, max_results=50):
    gmaps = googlemaps.Client(key=api_key)
    ris = []
    raggio_m = int(raggio_km * 1000)
    count_aziende = 0

    for kw in keywords_list:
        if count_aziende >= max_results:
            break
            
        # --- BLOCCO CORRETTO PER GESTIRE L'ERRORE ---
        try:
            response = gmaps.places_nearby(
                location=(lat, lon),
                radius=raggio_m,
                keyword=kw
            )
        except Exception as e:
            # USIAMO st.stop() PER BLOCCARE TUTTO E LEGGERE L'ERRORE
            st.error(f"❌ ERRORE CRITICO GOOGLE: {e}")
            st.info("L'esecuzione è stata bloccata per permetterti di leggere l'errore sopra.")
            st.stop() # <--- Fondamentale per il debug
        # --------------------------------------------

        while True:
            # Ora 'response' esiste sicuramente se siamo qui
            results = response.get('results', [])
            
            for place in results:
                if count_aziende >= max_results:
                    break
                
                try:
                    details = gmaps.place(
                        place['place_id'], 
                        fields=['name', 'formatted_address', 'website', 'geometry'],
                        language='it'
                    )['result']
                    
                    ris.append({
                        'Ragione Sociale': details.get('name', 'N.D.'),
                        'Sito Web': details.get('website', 'N.D.'),
                        'Indirizzo': details.get('formatted_address', 'N.D.'),
                        'lat': details['geometry']['location']['lat'],
                        'lon': details['geometry']['location']['lng'],
                        'Partita IVA': 'N.D.',
                        'Fatturato': 'N.D.',
                        'Dipendenti': 'N.D.'
                    })
                    count_aziende += 1
                except:
                    continue

            token = response.get('next_page_token')
            if not token or count_aziende >= max_results:
                break
                
            time.sleep(2)
            try:
                response = gmaps.places_nearby(page_token=token)
            except:
                break
            
    return pd.DataFrame(ris).drop_duplicates(subset=['Ragione Sociale']) if ris else pd.DataFrame()
