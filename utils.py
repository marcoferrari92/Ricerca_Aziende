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




import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- VALIDAZIONE P.IVA ---
def is_valid_piva(piva):
    if len(piva) != 11 or not piva.isdigit():
        return False
    
    s = sum(int(piva[i]) for i in range(0, 10, 2))
    s += sum((int(piva[i]) * 2 - 9) if int(piva[i]) * 2 > 9 else int(piva[i]) * 2 for i in range(1, 10, 2))
    
    check = (10 - s % 10) % 10
    return check == int(piva[-1])


def scrape_sito_aziendale(url):

    if not url or url == 'N.D.':
        return "Non trovata", "Non trovata", ""

    if not url.startswith('http'):
        url = 'http://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7'
    }

    visited = set()
    to_visit = [url]

    piva_f, email_f = "Non trovata", "Non trovata"
    testo_per_ai = ""

    # Regex più robusta
    #piva_pattern = r'(?:P\.?\s*IVA|VAT|Partita\s*IVA)[^\d]{0,15}(\d{11})'
    piva_pattern = r'(?i)(?:P\.?\s*IVA|VAT|P\s*I|CF|C\.F\.)[:\s-]{1,5}(\d{11})\b'
    
    # --- FUNZIONE DI ESTRAZIONE ---
    def cerca_piva(testo):
        matches = re.findall(piva_pattern, testo, re.IGNORECASE)
        for m in matches:
            if is_valid_piva(m):
                return m
        return None

    while to_visit and len(visited) < 5:
        current = to_visit.pop(0)
        visited.add(current)

        try:
            res = requests.get(current, headers=headers, timeout=6)
            if res.status_code != 200:
                continue

            html = res.text
            soup = BeautifulSoup(html, 'html.parser')

            for el in soup(["script", "style"]):
                el.decompose()

            text = soup.get_text(separator=' ', strip=True)

            # --- TESTO PER AI ---
            if len(testo_per_ai) < 5000:
                testo_per_ai += f" [URL: {current}] " + text

            # =========================
            # 🔍 1. CERCA SU TESTO PULITO
            # =========================
            if piva_f == "Non trovata":
                found = cerca_piva(text)
                if found:
                    piva_f = found

            # =========================
            # 🔍 2. CERCA SU HTML RAW (HEADER HACK)
            # =========================
            if piva_f == "Non trovata":
                found = cerca_piva(html)
                if found:
                    piva_f = found

            # =========================
            # 🔍 4. CERCA SOLO FOOTER
            # =========================
            if piva_f == "Non trovata":
                footer = soup.find('footer')
                if footer:
                    footer_text = footer.get_text(" ", strip=True)
                    found = cerca_piva(footer_text)
                    if found:
                        piva_f = found
                        
            # =========================
            # 📧 EMAIL
            # =========================
            if email_f == "Non trovata":
                em = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
                if em:
                    email_f = em.group(0).lower()

            # =========================
            # 🔗 LINK INTERNI
            # =========================
            for link in soup.find_all('a', href=True):
                href = link['href']
                full = urljoin(url, href)

                if any(k in full.lower() for k in [
                    'contatti', 'contact', 'about', 'chi-siamo',
                    'privacy', 'legal', 'impressum', '/home'
                ]):
                    if full not in visited:
                        to_visit.append(full)

            if piva_f != "Non trovata" and email_f != "Non trovata":
                break

        except:
            continue

    # =========================
    # 🚀 FALLBACK SELENIUM (SOLO SE NON TROVATA)
    # =========================
    if piva_f == "Non trovata":
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            import time

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")

            driver = webdriver.Chrome(options=options)
            driver.get(url)
            time.sleep(3)

            html = driver.page_source
            driver.quit()

            found = cerca_piva(html)
            if found:
                piva_f = found

        except:
            pass

    return piva_f, email_f, testo_per_ai[:6000]





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
