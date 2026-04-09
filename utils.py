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

def is_valid_piva(piva):
    """Algoritmo di Luhn per validare la P.IVA."""
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
    """
    Naviga il sito, estrae P.IVA ed Email usando regex e 
    restituisce il testo completo per l'analisi successiva dell'AI.
    """
    if not url or url == 'N.D.':
        return "Non trovata", "Non trovata", ""
    
    if not url.startswith('http'): 
        url = 'http://' + url
    
    # Header simulato per apparire come un browser reale (evita blocchi 403)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    }
    
    # Pagine dove solitamente si trovano i dati legali
    suffixes = ["", "/contatti", "/chi-siamo", "/privacy-policy", "/note-legali"]
    
    piva_f, email_f = "Non trovata", "Non trovata"
    testo_per_ai = ""
    
    # Regex migliorata: cattura 11 cifre ignorando IT o P.IVA davanti
    piva_pattern = r'(?i:IT|P\.IVA|P\.I\.)?\s*(\d{11})'

    for sfx in suffixes:
        try:
            full_url = url.rstrip('/') + sfx
            res = requests.get(full_url, headers=headers, timeout=8, verify=False)
            
            if res.status_code != 200: 
                continue
                
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # Rimuoviamo elementi inutili per pulire il testo
            for element in soup(["script", "style", "nav", "header"]):
                element.decompose()
                
            # Prendiamo il testo pulito
            testo_pagina = soup.get_text(separator=' ', strip=True)
            
            # Accumuliamo il testo per darlo in pasto all'AI (limitiamo a 5000 caratteri totali)
            if len(testo_per_ai) < 5000:
                testo_per_ai += f" [URL: {sfx}] " + testo_pagina
            
            # --- RICERCA P.IVA ---
            if piva_f == "Non trovata":
                matches = re.findall(piva_pattern, testo_pagina)
                for m in matches:
                    # m è il gruppo (\d{11}), quindi solo i numeri
                    if is_valid_piva(m):
                        piva_f = m
                        break
            
            # --- RICERCA EMAIL ---
            if email_f == "Non trovata":
                em_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo_pagina)
                if em_match:
                    email_f = em_match.group(0).lower()

            # Se abbiamo trovato tutto nella prima pagina, possiamo fermarci
            if piva_f != "Non trovata" and email_f != "Non trovata": 
                break
                
        except Exception:
            continue
            
    # Restituiamo 3 valori: P.IVA, Email e il Testo per l'AI
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
    Sei un analista finanziario con accesso a strumenti di ricerca real-time. 
    L'obiettivo è trovare i dati ufficiali dell'azienda: {nome_azienda}
    Sede Legale/Indirizzo: {indirizzo}
    Sito Web di riferimento: {sito}
    P.IVA trovata dal crawler (da verificare): {piva_crawler}

    TESTO ESTRATTO DAL SITO:
    ---
    {testo_sito[:4000]}
    ---

    ISTRUZIONI:
    1. Trova la PARTITA IVA ufficiale di 11 cifre. Cerca nel testo del sito (footer, privacy policy).
    2. Se la P.IVA del crawler è valida e presente nel testo, confermala.
    3. Trova il fatturato 2023 o 2024 e il numero di dipendenti. 
    4. Se i dati finanziari non sono nel testo, usa la tua conoscenza interna per fornire una stima verosimile.
    5. La P.IVA deve essere solo numerica (senza 'IT').

    Rispondi esclusivamente in formato JSON:
    {{
      "fatturato": "...", 
      "dipendenti": "...", 
      "piva": "...", 
      "fonte": "..."
    }}
    Se non trovi nulla, usa 'N.D.'.
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
