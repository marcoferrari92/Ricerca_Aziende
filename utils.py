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
    """
    Estrae P.IVA ed Email esplorando Home e sottopagine.
    Ottimizzato per siti industriali (settore C.25).
    """
    if not url or url == 'N.D.':
        return "N.D.", "N.D."
    
    if not url.startswith('http'):
        url = 'http://' + url

    # Headers potenziati per evitare blocchi "Bot Detection"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.com/'
    }

    # Ordine di ricerca logico per aziende italiane
    suffixes = ["", "/contatti", "/chi-siamo", "/privacy-policy", "/legal-notices"]
    
    piva_final = "Non trovata"
    email_final = "Non trovata"

    # REGEX UNIVERSALE: 
    # Cerca stringhe che somigliano a una P.IVA precedute da etichette comuni
    # Gestisce: P.I. 00262380249, Partita IVA: 00262380249, IT00262380249, ecc.
    piva_pattern = r'(?:IT|P\.IVA|P\.I\.|C\.F\.|IVA)?\s?(\d{2,3}[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{2})'

    for suffix in suffixes:
        try:
            full_url = url.rstrip('/') + suffix
            response = requests.get(full_url, headers=headers, timeout=8, verify=False)
            
            if response.status_code != 200:
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Pulizia profonda: togliamo navigazione e codici che creano falsi positivi
            for element in soup(["script", "style", "nav", "header", "footer_links"]):
                element.decompose()
            
            # Prendiamo il testo pulito
            testo = " ".join(soup.get_text().split())

            # 1. Ricerca P.IVA
            if piva_final == "Non trovata":
                matches = re.findall(piva_pattern, testo)
                for m in matches:
                    # Rimuoviamo ogni carattere non numerico per il controllo finale
                    cifre = "".join(filter(str.isdigit, m))
                    if len(cifre) == 11:
                        piva_final = cifre
                        break # Trovata, usciamo dal loop dei match

            # 2. Ricerca Email
            if email_final == "Non trovata":
                email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
                if email_match:
                    # Evitiamo di prendere email di webmaster o grafici se possibile
                    temp_email = email_match.group(0).lower()
                    if "webmaster" not in temp_email and "pixel" not in temp_email:
                        email_final = temp_email

            # Se abbiamo trovato entrambi i dati core, interrompiamo la scansione delle sottopagine
            if piva_final != "Non trovata" and email_final != "Non trovata":
                break
                
        except Exception:
            continue

    return piva_final, email_final



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
