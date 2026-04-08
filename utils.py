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


def is_valid_piva(piva):
    """Valida la Partita IVA italiana usando l'algoritmo di Luhn."""
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

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Referer': 'https://www.google.com/'
    }

    suffixes = ["", "/contatti", "/contacts","/about", "/chi-siamo", "/privacy-policy"]
    piva_final, email_final = "Non trovata", "Non trovata"
    
    # Regex ultra-flessibile: prende gruppi di numeri separati da quasi tutto
    piva_pattern = r'(?:IT|P\.?IVA|P\.?I\.?|C\.?F\.?|IVA)?\s?(\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d[\s.-]?\d)'

    for suffix in suffixes:
        try:
            res = requests.get(url.rstrip('/') + suffix, headers=headers, timeout=7, verify=False)
            if res.status_code != 200: continue
            
            soup = BeautifulSoup(res.text, 'html.parser')
            for tag in soup(["script", "style", "nav", "header"]): tag.decompose()
            
            # Cerchiamo sia nel testo che negli attributi (a volte è nei link)
            testo = soup.get_text(separator=' ')
            
            # 1. Ricerca P.IVA con Validazione
            if piva_final == "Non trovata":
                matches = re.findall(piva_pattern, testo)
                for m in matches:
                    cifre = "".join(filter(str.isdigit, m))
                    if len(cifre) == 11 and is_valid_piva(cifre):
                        piva_final = cifre
                        break
            
            # 2. Ricerca Email (escludendo falsi positivi comuni)
            if email_final == "Non trovata":
                emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
                for em in emails:
                    em_low = em.lower()
                    if not any(x in em_low for x in ["example", "email", "webmaster", "pec"]):
                        email_final = em_low
                        break

            if piva_final != "Non trovata" and email_final != "Non trovata": break
        except: continue

    return piva_final, email_final



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




def scrape_camerale_data(piva):
    """
    Strategia Fallback: Se il sito diretto dà 404, interroga Google.
    Spesso il dato è già nello 'snippet' di ricerca.
    """
    if not piva or len(piva) != 11:
        return "N.D.", "N.D.", "P.IVA non valida"
    
    # User-Agent più moderno per sembrare un browser reale
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8',
        'Referer': 'https://www.google.it/'
    }

    # Tentiamo la ricerca tramite Google per bypassare il blocco diretto
    # Cerchiamo la P.IVA specificamente su reportaziende o ufficiovisto
    search_url = f"https://www.google.com/search?q=site:reportaziende.it+{piva}"
    
    # Attesa casuale anti-ban (fondamentale)
    time.sleep(random.uniform(2.5, 4.5))

    try:
        res = requests.get(search_url, headers=headers, timeout=12)
        
        if res.status_code != 200:
            return f"Errore Google {res.status_code}", "N.D.", "Google ha bloccato la richiesta."

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Rimuoviamo la spazzatura di Google (script, stili, etc.)
        for tag in soup(["script", "style", "header", "footer"]):
            tag.decompose()
            
        testo_google = soup.get_text(separator=' ', strip=True)

        fatturato = "N.D."
        dipendenti = "N.D."

        # Cerchiamo il fatturato nello snippet di Google
        # Pattern: cerca la parola fatturato e poi una cifra con punti/virgole
        fatt_match = re.search(r'fatturato.*?([\d\.,]+)\s?(?:Euro|€|milioni)?', testo_google, re.IGNORECASE)
        if fatt_match:
            valore = fatt_match.group(1).strip('., ')
            if len(valore.replace('.', '')) > 4: # Evitiamo numeri troppo corti (civici, date)
                fatturato = valore + " €"

        # Cerchiamo i dipendenti
        dip_match = re.search(r'(?:dipendenti|addetti).*?(\d+)', testo_google, re.IGNORECASE)
        if dip_match:
            dipendenti = dip_match.group(1)

        # Se non troviamo nulla, mostriamo il testo per debug
        info_debug = f"Fonte: Google Snippet\n\n{testo_google[:1500]}"
        
        return fatturato, dipendenti, info_debug

    except Exception as e:
        return "Errore tecnico", "N.D.", str(e)
