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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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




import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time

# --- VALIDAZIONE P.IVA (Algoritmo di Luhn) ---
def is_valid_piva(piva_raw):
    # Rimuove IT, spazi, punti, trattini e tiene SOLO i numeri
    piva = "".join(filter(str.isdigit, str(piva_raw)))
    
    # Se dopo la pulizia non abbiamo esattamente 11 cifre, non è una P.IVA
    if not piva or len(piva) != 11:
        return False
        
    # Algoritmo di Luhn sulle 11 cifre rimaste
    s = sum(int(piva[i]) for i in range(0, 10, 2))
    for i in range(1, 10, 2):
        temp = int(piva[i]) * 2
        s += temp if temp <= 9 else temp - 9
    check = (10 - s % 10) % 10
    
    return check == int(piva[-1])

def scrape_sito_aziendale(url, ragione_sociale=""):
    if not url or url == 'N.D.':
        return "Non trovata", "Non trovata", "", "Sito non disponibile"

    if not url.startswith('http'):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    visited = set()
    to_visit = [url]
    piva_f, email_f = "Non trovata", "Non trovata"
    testo_per_ai = ""
    log_debug = []

    # --- FUNZIONE DI RICERCA AGGRESSIVA AGGIORNATA ---
    def estrai_piva_ovunque(sorgente):
        """Estrae sequenze di 11 cifre e le restituisce PULITE (senza IT)"""
        # 1. Cerca sequenze numeriche pure di 11 cifre
        candidati = re.findall(r'\b\d{11}\b', sorgente)
        
        # 2. Cerca sequenze che iniziano con IT (es. IT12345678901)
        candidati_it = re.findall(r'(?i)\bIT\s*(\d{11})\b', sorgente)
        candidati += candidati_it
        
        # 3. Cerca numeri con spazi (es. 012 345 678 90 o IT 012 345 678 90)
        candidati_spazi = re.findall(r'(?i)\b(?:IT\s*)?(?:\d\s*){11}\b', sorgente)
        candidati += ["".join(filter(str.isdigit, c)) for c in candidati_spazi]

        for c in set(candidati):
            # Pulizia finale di sicurezza: tiene solo le cifre
            solo_cifre = "".join(filter(str.isdigit, c))
            if is_valid_piva(solo_cifre):
                # RESTITUISCE SOLO LE 11 CIFRE (Senza IT)
                return solo_cifre
        return None

    while to_visit and len(visited) < 5:
        current = to_visit.pop(0)
        if current in visited: continue
        visited.add(current)

        try:
            res = requests.get(current, headers=headers, timeout=8, verify=False)
            if res.status_code != 200: continue
            
            html = res.text
            
            # 1. TENTATIVO IMMEDIATO SU HTML GREZZO
            if piva_f == "Non trovata":
                found = estrai_piva_ovunque(html)
                if found:
                    piva_f = found
                    log_debug.append(f"[{current}] P.IVA trovata nell'HTML grezzo: {found}")

            soup = BeautifulSoup(html, 'html.parser')

            # 2. TENTATIVO NEI META TAG
            if piva_f == "Non trovata":
                meta_content = " ".join([tag.get('content', '') for tag in soup.find_all('meta')])
                found = estrai_piva_ovunque(meta_content)
                if found:
                    piva_f = found
                    log_debug.append(f"[{current}] P.IVA trovata nei Meta Tag: {found}")

            # Estrazione testo per AI ed Email
            text_full = soup.get_text(separator=' ', strip=True)
            if len(testo_per_ai) < 6000:
                testo_per_ai += f" [URL: {current}] " + text_full

            if email_f == "Non trovata": # Corretto da "Non votata"
                em = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_full)
                if em: email_f = em.group(0).lower()

            # 2.5 CERCA NEL TESTO PULITO
            if piva_f == "Non trovata":
                found = estrai_piva_ovunque(text_full)
                if found:
                    piva_f = found
                    log_debug.append(f"[{current}] P.IVA trovata nel testo visibile: {found}")

            # Raccolta Link
            for link in soup.find_all('a', href=True):
                href = link['href']
                full = urljoin(url, href)
                if any(k in full.lower() for k in ['contatti', 'contact', 'about', 'chi-siamo', 'legal', 'privacy', 'info']):
                    if full not in visited:
                        to_visit.append(full)

            if piva_f != "Non trovata" and email_f != "Non trovata":
                break

        except Exception as e:
            log_debug.append(f"Errore su {current}: {str(e)}")
            continue

    # --- 3. FALLBACK SELENIUM ---
    if piva_f == "Non trovata":
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options = Options()
            options.add_argument("--headless")
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            import time
            time.sleep(3) 
            
            source = driver.page_source
            found = estrai_piva_ovunque(source)
            if found:
                piva_f = found
                log_debug.append(f"[Selenium] Trovata dopo rendering: {found}")
            driver.quit()
        except:
            pass

    debug_final = "\n".join(log_debug) if log_debug else "Nessuna P.IVA valida trovata nelle pagine scansionate."
    return piva_f, email_f, testo_per_ai[:6000], debug_final



def cerca_info_finanziarie_per_nome(ragione_sociale, indirizzo=""):
    query_string = f"{ragione_sociale} fatturato"
    query_url = f"https://www.google.com/search?q={query_string}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        res = requests.get(query_url, headers=headers, timeout=10)
        if res.status_code != 200:
            return "Errore", "Errore", f"ERRORE HTTP {res.status_code}: Google ha bloccato il bot."

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Estraiamo il testo pulendo i tag inutili per il debug
        for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
            script_or_style.decompose()

        # Testo normalizzato (rimuove doppi spazi e tab)
        testo_completo = " ".join(soup.get_text(separator=' ').split())

        # Le tue Regex attuali
        regex_fatturato = r'(?i)(?:Fatturato|€)\s*[:\s-]{0,3}([\d\.]+)\s?(?:€|euro|milioni|mln)?'
        regex_dipendenti = r'(?i)(?:Dipendenti|personale)\s*[:\s-]{0,3}(\d+)'

        fatt_match = re.search(regex_fatturato, testo_completo)
        dip_match = re.search(regex_dipendenti, testo_completo)

        val_fatt = fatt_match.group(1) if fatt_match else "N.D."
        val_dip = dip_match.group(1) if dip_match else "N.D."
        
        if val_fatt != "N.D." and "€" not in val_fatt:
            val_fatt = f"€ {val_fatt}"

        # RESTITUIAMO 2000 CARATTERI: i primi 500 sono spesso inutili, il succo è dopo
        return val_fatt, val_dip, testo_completo[:2000]

    except Exception as e:
        return "Errore", "Errore", f"ECCEZIONE: {str(e)}"

