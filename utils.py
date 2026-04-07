
import requests
import re
import pandas as pd
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
    """FASE 2: Estrazione da FatturatoItalia.it tramite Partita IVA."""
    piva_clean = "".join(filter(str.isdigit, str(piva)))
    if len(piva_clean) != 11:
        return "P.IVA non valida", "N.D."
    
    # FatturatoItalia permette la ricerca diretta tramite questo pattern di URL
    url = f"https://www.fatturatoitalia.it/ricerca?q={piva_clean}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept-Language': 'it-IT,it;q=0.9'
        }
        
        # Pausa di sicurezza
        time.sleep(2)
        res = requests.get(url, headers=headers, timeout=12, verify=False)
        
        if res.status_code != 200:
            return "Sito Non Disponibile", "N.D."

        soup = BeautifulSoup(res.text, 'html.parser')

        # Se il sito mostra una lista di risultati, prendiamo il primo
        if "risultati" in res.text.lower() or "/azienda/" not in res.url:
            link = soup.find('a', href=re.compile(r'/azienda/'))
            if link:
                full_link = "https://www.fatturatoitalia.it" + link['href'] if not link['href'].startswith('http') else link['href']
                time.sleep(1)
                res = requests.get(full_link, headers=headers, timeout=12, verify=False)
                soup = BeautifulSoup(res.text, 'html.parser')

        testo = soup.get_text(separator='|', strip=True)

        # Regex specifica per FatturatoItalia
        # Cercano i pattern: "Fatturato: € 1.234.567" e "Dipendenti: 50"
        fatt_match = re.search(r'Fatturato[:\s|]*€?\s*([\d.,]+)', testo, re.I)
        dip_match = re.search(r'Dipendenti[:\s|]*(\d+)', testo, re.I)

        f_val = f"€ {fatt_match.group(1)}" if fatt_match else "N.D."
        d_val = dip_match.group(1) if dip_match else "N.D."

        return f_val, d_val

    except Exception:
        return "Errore Connessione", "N.D."
