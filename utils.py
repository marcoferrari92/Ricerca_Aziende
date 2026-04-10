import streamlit as st
import requests
import re
import pandas as pd
import time
import random
import googlemaps
from bs4 import BeautifulSoup
import urllib3
import json              
from openai import OpenAI

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# GOOGLE 
# In utils.py
import googlemaps
import pandas as pd
import time

import googlemaps
import pandas as pd
import time

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
            response = gmaps.places_nearby(location=(lat, lon), radius=raggio_m, keyword=kw)
            
            while True:
                results = response.get('results', [])
                for place in results:
                    if count >= max_results: break
                    
                    # Dettagli singoli - CHIEDIAMO ANCHE address_components per il Comune
                    details = gmaps.place(
                        place['place_id'], 
                        fields=['name', 'formatted_address', 'website', 'geometry', 'business_status', 'address_components'],
                        language='it'
                    ).get('result', {})
                    
                    # ESTRAZIONE MINIMA PER IL COMUNE (Serve per la tua ricerca AI)
                    componenti = details.get('address_components', [])
                    comune, nazione, prov, cap = "N.D.", "N.D.", "N.D.", "N.D."
                    for c in componenti:
                        t = c.get('types', [])
                        if 'locality' in t: comune = c['long_name']
                        elif 'country' in t: nazione = c['long_name']
                        elif 'administrative_area_level_2' in t: prov = c['short_name']
                        elif 'postal_code' in t: cap = c['long_name']
                    
                    s_raw = details.get('business_status', 'N.D.')
                    s_ita = {'OPERATIONAL': 'Attiva', 'CLOSED_TEMPORARILY': 'Chiusa Temp.'}.get(s_raw, 'N.D.')
                    
                    # CREIAMO IL DIZIONARIO CON TUTTE LE COLONNE CHE L'APP SI ASPETTA
                    ris.append({
                        'Ragione Sociale': details.get('name', 'N.D.'),
                        'Stato': s_ita,
                        'Nazione': nazione,
                        'Provincia': prov,
                        'Comune': comune,
                        'CAP': cap,
                        'Indirizzo': details.get('formatted_address', 'N.D.'), # INDIRIZZO COMPLETO
                        'Sito Web': details.get('website', 'N.D.'),
                        'Email (Crawler)': 'N.D.',
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


# --- 4. RICERCA ONLINE (DuckDuckGo Lite) ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0'})

import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urlparse, parse_qs

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0'
})

def cerca_testo_online(ragione_sociale, comune):
    #nome_pulito = " ".join(ragione_sociale.split()[:4])
    query = f"{ragione_sociale} {comune} fatturato numero dipendenti".replace(" ", "+")
    url = f"https://lite.duckduckgo.com/lite/?q={query}"
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'}

    try:
        time.sleep(random.uniform(6, 12)) 
        res = session.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return f"Errore {res.status_code}"

        soup = BeautifulSoup(res.text, "html.parser")
        risultati_testo = []
        
        links = soup.find_all('a', class_='result-link')
        snippets = soup.find_all('td', class_='result-snippet')

        for link, snippet in zip(links, snippets):
            raw_href = link.get('href', '')
            
            # --- LOGICA PER ESTRARRE IL SITO REALE ---
            # DuckDuckGo Lite usa spesso /l/?kh=...&uddg=URL_REALE
            if "/l/?" in raw_href:
                parsed_query = parse_qs(urlparse(raw_href).query)
                real_url = parsed_query.get('uddg', [raw_href])[0]
                dominio = urlparse(real_url).netloc.replace("www.", "")
            else:
                dominio = urlparse(raw_href).netloc.replace("www.", "")
            
            if not dominio: dominio = "Sito non identificato"
            
            testo_snippet = snippet.get_text(strip=True)
            risultati_testo.append(f"[{dominio.upper()}] {testo_snippet}")

        return " | ".join(risultati_testo) if risultati_testo else "Nessun risultato."

    except Exception as e:
        return f"Eccezione tecnica: {str(e)}"


# --- 5. ESTRAZIONE AI ---
import json
import re
from openai import OpenAI

def estrai_con_ai(testo, api_key):
    client = OpenAI(api_key=api_key)
    
    prompt = f"""
    Analizza il testo e recupera i dati. 
    
    REGOLE RIGIDE DI FORMATTAZIONE:
    1. SE MANCANO DATI: Usa sempre "N.D.", non usare puntini, spazi o "non specificato".
    2. FATTURATO: Converti sempre in formato decimale italiano con simbolo Euro (es. 1.300.000 €). 
       Se trovi "1.3 M €" scrivi "1.300.000 €". Se trovi un range, scrivi "300.000 - 600.000 €".
       Se presente, indica l'anno a cui fa riferimento il fatturato tra parentesi (es. "1.300.000 € (2023)").
    3. DIPENDENTI: Solo numeri o range (es. "5" o "2-5").
    4. FONTI: Identifica il dominio dal tag [DOMINIO.IT].
    5. ATECO: Scrivi solo il numero nel formato XX.XX.XX (es. 25.99.99). Se non hai tutte le cifre indica solo quelle trovate ma mantieni la formattazione.

    TESTO: \"\"\"{testo}\"\"\"
    
    JSON:
    {{
        "fatturato": {{ "valore": "...", "fonte": "..." }},
        "dipendenti": {{ "valore": "...", "fonte": "..." }},
        "ateco": "...",
        "ragione_sociale": "...",
        "indirizzo": "...",
        "partita_iva": "..."
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={ "type": "json_object" }
        )
        dati = json.loads(response.choices[0].message.content)
        
        # Pulizia post-estrazione per sicurezza
        def clean_nd(val):
            if not val or val.lower() in ["none", "null", "non specificato", "...", "nan"]:
                return "N.D."
            return str(val).strip()

        f_val = clean_nd(dati.get("fatturato", {}).get("valore"))
        f_src = clean_nd(dati.get("fatturato", {}).get("fonte"))
        d_val = clean_nd(dati.get("dipendenti", {}).get("valore"))
        d_src = clean_nd(dati.get("dipendenti", {}).get("fonte"))
        
        piva = clean_nd(dati.get("partita_iva"))
        ateco = clean_nd(dati.get("ateco"))
        rag_soc = clean_nd(dati.get("ragione_sociale"))
        ind = clean_nd(dati.get("indirizzo"))
        
        info_extra = f"FATT da: {f_src.upper()} | DIP da: {d_src.upper()} | PIVA: {piva}"
        
        return f_val, d_val, piva, ind, ateco, rag_soc, info_extra, testo

    except Exception as e:
        return "Errore AI", "Errore AI", "Errore AI", "Errore AI", "Errore AI", "Errore AI", f"AI Error: {str(e)}", testo


def cerca_info_finanziarie_per_nome(ragione_sociale, api_key):
    """
    IMPORTANTE: Questa funzione DEVE chiamarsi così per app.py
    """
    testo_grezzo = cerca_testo_online(ragione_sociale)
    if not testo_grezzo or "Errore" in testo_grezzo:
        return "N.D.", "N.D.", "N.D.", "N.D.", "N.D.", "N.D.", "Ricerca fallita", testo_grezzo
    return estrai_con_ai(testo_grezzo, api_key)

