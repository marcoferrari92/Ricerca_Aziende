
import requests
import re
import pandas as pd
import random
import urllib3
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
    url = f"https://www.reportaziende.it/ricerca?q={piva_clean}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    print(f"\n--- DEBUG: Provo a collegarmi a {url} ---")

    try:
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        
        # 1. STAMPA IL CODICE DI RISPOSTA (200=OK, 403=BLOCCATO)
        print(f"STATUS CODE: {res.status_code}")

        # 2. STAMPA COSA VEDE IL BOT (I primi 1000 caratteri)
        print("CONTENUTO HTML (PRIMI 1000 CARATTERI):")
        print(res.text[:1000])
        print("--- FINE DEBUG ---\n")

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Logica di estrazione (quella che avevi già)
        testo = soup.get_text(separator='|', strip=True)
        fatt_match = re.search(r'Fatturato.*?([\d.]{7,15})', testo, re.I)
        fatturato = f"€ {fatt_match.group(1)}" if fatt_match else "N.D."
        
        dip_match = re.search(r'Dipendenti\|(da\s*\d+\s*a\s*\d+|\d+)', testo, re.I)
        dipendenti = dip_match.group(1) if dip_match else "N.D."

        return fatturato, dipendenti

    except Exception as e:
        # Se c'è un errore, stampiamolo!
        print(f"ERRORE CRITICO: {str(e)}")
        return "Errore Lettura", "N.D."
