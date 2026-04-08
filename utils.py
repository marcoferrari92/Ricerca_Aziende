import streamlit as st
import requests
import re
import pandas as pd
import time   
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
            
        try:
            response = gmaps.places_nearby(
                location=(lat, lon),
                radius=raggio_m,
                keyword=kw
            )
        except Exception as e:
            st.error(f"❌ ERRORE CRITICO GOOGLE: {e}")
            st.stop() 

        while True:
            results = response.get('results', [])
            
            for place in results:
                if count_aziende >= max_results:
                    break
                
                try:
                    # Inseriti business_status e types nei fields
                    details = gmaps.place(
                        place['place_id'], 
                        fields=['name', 'formatted_address', 'website', 'geometry', 'business_status', 'types'],
                        language='it'
                    )['result']
                    
                    # 1. Mapping dello stato
                    status_raw = details.get('business_status', 'N.D.')
                    status_ita = {
                        'OPERATIONAL': 'Attiva',
                        'CLOSED_TEMPORARILY': 'Chiusa Temporaneamente',
                        'CLOSED_PERMANENTLY': 'Chiusa Definitivamente'
                    }.get(status_raw, status_raw)

                    # 2. Pulizia categorie (prendiamo le prime 3 per non allungare troppo la colonna)
                    types_list = details.get('types', [])
                    categorie = ", ".join(types_list[:3]) if types_list else "N.D."

                    ris.append({
                        'Ragione Sociale': details.get('name', 'N.D.'),
                        'Stato': status_ita,
                        'Categorie': categorie, # <--- NUOVA COLONNA
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



from openai import OpenAI
import json

def chiedi_a_openai(nome_azienda, piva, sito, api_key_openai):
    """
    Usa OpenAI per incrociare i dati e trovare bilancio e dipendenti.
    """
    if not api_key_openai:
        return "Manca API Key", "N.D.", "Configura la chiave OpenAI"

    client = OpenAI(api_key=api_key_openai)
    
    # Prompt ottimizzato per estrazione dati business
    prompt = f"""
    Sei un analista finanziario esperto. 
    Trova il fatturato più recente (anno 2023 o 2024) e il numero di dipendenti per:
    Ragione Sociale: {nome_azienda}
    Partita IVA: {piva}
    Sito Web: {sito}

    Rispondi ESCLUSIVAMENTE con un oggetto JSON con queste chiavi:
    "fatturato": (stringa con valore e valuta, es: "1.5 Mln €"),
    "dipendenti": (stringa con il numero o range, es: "10-20"),
    "fonte": (breve descrizione della fonte trovata)

    Se i dati non sono disponibili, scrivi "N.D.".
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Modello veloce ed economico, ottimo per questo compito
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" } # Forza OpenAI a rispondere in JSON
        )
        
        # Parsing della risposta
        risposta_json = json.loads(response.choices[0].message.content)
        
        fatturato = risposta_json.get("fatturato", "N.D.")
        dipendenti = risposta_json.get("dipendenti", "N.D.")
        fonte = risposta_json.get("fonte", "N.D.")
        
        return fatturato, dipendenti, f"Dati AI: {fonte}"

    except Exception as e:
        return "Errore AI", "N.D.", str(e)
