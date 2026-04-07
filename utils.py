
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


def scrape_camerale_data(piva):
    """FASE 2: Estrazione da FatturatoItalia con Headers 'Umani'."""
    piva_clean = "".join(filter(str.isdigit, str(piva)))
    if len(piva_clean) != 11:
        return "P.IVA non valida", "N.D."
    
    # URL diretto alla ricerca di FatturatoItalia
    url = f"https://www.fatturatoitalia.it/ricerca?q={piva_clean}"
    
    try:
        # Creiamo una sessione per gestire i cookie automaticamente
        session = requests.Session()
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'it-IT,it;q=0.9,en;q=0.8',
            'Referer': 'https://www.google.it/',
            'Connection': 'keep-alive'
        }

        # Aspetta un tempo variabile (3-5 sec) per non sembrare un robot
        time.sleep(3)
        
        # Facciamo la richiesta ignorando gli errori SSL (verify=False)
        res = session.get(url, headers=headers, timeout=15, verify=False)
        
        if res.status_code != 200:
            return f"Blocco {res.status_code}", "N.D."

        soup = BeautifulSoup(res.text, 'html.parser')

        # Se il sito non ci manda direttamente alla scheda, cerchiamo il primo link aziendale
        if "/azienda/" not in res.url:
            link = soup.find('a', href=re.compile(r'/azienda/'))
            if link:
                full_link = "https://www.fatturatoitalia.it" + link['href']
                time.sleep(2)
                res = session.get(full_link, headers=headers, timeout=15, verify=False)
                soup = BeautifulSoup(res.text, 'html.parser')

        testo = soup.get_text(separator='|', strip=True)

        # Estrazione dati con Regex flessibile
        fatt_match = re.search(r'Fatturato[:\s|]*€?\s*([\d.,]+)', testo, re.I)
        dip_match = re.search(r'Dipendenti[:\s|]*(\d+)', testo, re.I)

        f_val = f"€ {fatt_match.group(1)}" if fatt_match else "N.D."
        d_val = dip_match.group(1) if dip_match else "N.D."

        return f_val, d_val

    except Exception as e:
        # Se fallisce ancora, riportiamo il tipo di errore per debuggare
        return "Bloccato", "N.D."
