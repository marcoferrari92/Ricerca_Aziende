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

def cerca_tutti_candidati_piva(testo):
    if not testo: return []
    
    # Regex aggiornata con il nuovo tag C.F. che hai chiesto
    # Cerca stringhe di 11 cifre precedute da tag comuni
    pattern = r'(?i)(?:P\.?\s*IVA|VAT|Partita\s*IVA|P\s*I|C\.F\.|CF|Codice\s*Fiscale)[:\s/-]{1,6}(\d{11})\b'
    
    # Trova tutti i match, non solo il primo
    matches = re.findall(pattern, testo)
    
    # Restituiamo la lista pulita (senza duplicati)
    return list(set(matches))

# --- VALIDAZIONE P.IVA (Algoritmo di Luhn) ---
def is_valid_piva(piva):
    if not piva or len(piva) != 11 or not piva.isdigit():
        return False
    s = sum(int(piva[i]) for i in range(0, 10, 2))
    for i in range(1, 10, 2):
        temp = int(piva[i]) * 2
        s += temp if temp <= 9 else temp - 9
    check = (10 - s % 10) % 10
    return check == int(piva[-1])

# --- FUNZIONE DI ESTRAZIONE CORE ---
def cerca_piva(testo):
    if not testo: 
        return None
    
    # Regex potenziata: 
    # - (?i) rende tutto case-insensitive
    # - Cerca P.IVA, VAT, Partita IVA, P.I, CF, C.F., Codice Fiscale
    # - Gestisce spazi, punti e simboli come / o : tra il tag e il numero
    piva_pattern = r'(?i)(?:P\.?\s*IVA|VAT|Partita\s*IVA|P\s*I|C\.F\.|CF|Codice\s*Fiscale)[:\s/-]{1,6}(\d{11})\b'
    
    matches = re.findall(piva_pattern, testo)
    
    for m in matches:
        if is_valid_piva(m):
            return m
            
    return None

def scrape_sito_aziendale(url, ragione_sociale=""):
    if not url or url == 'N.D.':
        return "Non trovata", "Non trovata", "", "Nessun dato"

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
    
    # --- LOGICA DEBUG: LISTA NUMERI TROVATI ---
    log_numeri_trovati = []

    def estrai_e_logga_numeri(sorgente, url_corrente):
        """Funzione interna per loggare ogni sequenza di 11 cifre trovata"""
        # Cerca tutte le sequenze di 11 cifre nel testo
        candidati = re.findall(r'\b\d{11}\b', sorgente)
        for c in candidati:
            validita = "✅ (Valida)" if is_valid_piva(c) else "❌ (Luhn Fallito)"
            entry = f"[{url_corrente}] Trovato: {c} {validita}"
            if entry not in log_numeri_trovati:
                log_numeri_trovati.append(entry)

    while to_visit and len(visited) < 5:
        current = to_visit.pop(0)
        if current in visited: continue
        visited.add(current)

        try:
            res = requests.get(current, headers=headers, timeout=8, verify=False)
            if res.status_code != 200: continue
            
            html = res.text
            # Logghiamo tutti i numeri di 11 cifre trovati nell'HTML grezzo
            estrai_e_logga_numeri(html, current)
            
            soup = BeautifulSoup(html, 'html.parser')

            # 1. CERCA NEI META TAG
            if piva_f == "Non trovata":
                meta_content = " ".join([tag.get('content', '') for tag in soup.find_all('meta')])
                found = cerca_piva(meta_content)
                if found: piva_f = found

            # Pulizia per estrazione testo
            for el in soup(["script", "style", "nav", "header"]): 
                el.decompose()

            text = soup.get_text(separator=' ', strip=True)
            if len(testo_per_ai) < 6000:
                testo_per_ai += f" [URL: {current}] " + text

            # 2. CERCA NEL TESTO PULITO
            if piva_f == "Non trovata":
                piva_f = cerca_piva(text) or "Non trovata"

            # 3. CERCA EMAIL
            if email_f == "Non trovata":
                em = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                if em: email_f = em.group(0).lower()

            # 4. RACCOLTA LINK
            for link in soup.find_all('a', href=True):
                href = link['href']
                full = urljoin(url, href)
                if any(k in full.lower() for k in ['contatti', 'contact', 'about', 'chi-siamo', 'legal', 'privacy', 'note-legali']):
                    if full not in visited:
                        to_visit.append(full)

            if piva_f != "Non trovata" and email_f != "Non trovata":
                break

        except Exception as e:
            log_numeri_trovati.append(f"Errore su {current}: {str(e)}")
            continue

    # --- FALLBACK SELENIUM ---
    if piva_f == "Non trovata":
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2) 
            
            page_source = driver.page_source
            estrai_e_logga_numeri(page_source, "Selenium-Scroll")
            
            piva_f = cerca_piva(page_source) or "Non trovata"
            driver.quit()
        except Exception as e:
            log_numeri_trovati.append(f"Errore Selenium: {str(e)}")

    # Prepariamo la stringa finale del log di debug
    debug_log = "\n".join(log_numeri_trovati) if log_numeri_trovati else "Nessun numero di 11 cifre individuato."

    # Ritorna 4 valori invece di 3
    return piva_f, email_f, testo_per_ai[:6000], debug_log


# --- FUNZIONE EXTRA PER FATTURATO (Ricerca Esterna Gratis) ---
def get_financial_data(piva):
    """
    Tenta di recuperare fatturato e dipendenti da aggregatori gratuiti usando la P.IVA
    """
    if piva == "Non trovata": return "N.D.", "N.D."
    
    try:
        # Esempio su ReportAziende (sito molto semplice da scansionare)
        search_url = f"https://www.reportaziende.it/ricerca?qs={piva}"
        res = requests.get(search_url, timeout=10)
        # Qui andrebbe aggiunto il parsing della tabella risultati
        # Per ora restituiamo un placeholder
        return "Da analizzare su ReportAziende", "Disponibile online"
    except:
        return "Errore ricerca", "Errore ricerca"




import json
from openai import OpenAI

def chiedi_a_openai(nome_azienda, piva_crawler, sito, indirizzo, testo_sito, api_key_openai):
    """
    Analizza i dati aziendali usando GPT-4o, incrociando la sua conoscenza 
    con il testo reale del sito web e validando la P.IVA.
    """
    if not api_key_openai:
        return "N.D.", "N.D.", "N.D.", "Manca Key"

    client = OpenAI(api_key=api_key_openai)
    
    # Prompt ottimizzato per estrazione e stima intelligente
    prompt = f"""
    Sei un investigatore economico esperto in aziende italiane (SAS, SRL, SNC).
    Trova i dati fiscali per: {nome_azienda}
    Sede: {indirizzo}
    Sito: {sito}

    ISTRUZIONI TASSATIVE:
    1. PARTITA IVA: Cerca nel testo del sito la Partita IVA o il Codice Fiscale (11 cifre). 
       Se il crawler dice '{piva_crawler}', verificalo. Se è N.D., estrailo dal testo.
    2. FATTURATO: Cerca il fatturato più recente. 
    3. NUMERO DIPENDENTI: Cerca il numero di dipendenti.
    3. NON INVENTARE: Se non trovi la P.IVA nel testo e non sei sicuro, scrivi 'N.D.', ma tenta prima una ricerca profonda basata sulla sede {indirizzo}.

    Rispondi in JSON: {{"fatturato": "...", "dipendenti": "...", "piva": "...", "fonte": "..."}}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": "Sei un assistente esperto in dati camerali e analisi di siti web aziendali."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            temperature=0.2
        )
        
        # Caricamento dati JSON
        res_content = response.choices[0].message.content
        data = json.loads(res_content)
        
        # --- LOGICA DI PULIZIA E VALIDAZIONE P.IVA ---
        raw_piva = str(data.get("piva", "N.D."))
        # Rimuove IT, spazi, punti e trattini
        piva_solo_numeri = "".join(filter(str.isdigit, raw_piva))
        
        # Validazione con la TUA funzione is_valid_piva
        if is_valid_piva(piva_solo_numeri):
            piva_finale = piva_solo_numeri
        elif piva_crawler != "Non trovata" and is_valid_piva(piva_crawler):
            # Se l'AI sbaglia ma il crawler aveva ragione, recuperiamo quella del crawler
            piva_finale = piva_crawler
        else:
            piva_finale = "N.D. (Invalida)"

        # --- ESTRAZIONE ALTRI DATI ---
        fatturato = data.get("fatturato", "N.D.")
        dipendenti = data.get("dipendenti", "N.D.")
        fonte = data.get("fonte", "Analisi AI + Web")

        return str(fatturato), str(dipendenti), piva_finale, str(fonte)

    except Exception as e:
        return "Errore AI", "N.D.", "N.D.", str(e)
