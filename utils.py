
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
    """Fase 1: Estrae P.IVA ed Email pulendo i caratteri sporchi."""
    if not url or url == 'N.D.': return "N.D.", "N.D."
    if not url.startswith('http'): url = 'http://' + url
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        # verify=False ignora errori di certificato SSL (molto comune in Italia)
        res = requests.get(url, headers=headers, timeout=8, verify=False)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # separator=' ' evita che le parole si attacchino
        testo = soup.get_text(separator=' ', strip=True)

        # Cerchiamo la P.IVA: 11 cifre, ma puliamo eventuali prefissi "IT"
        piva_match = re.search(r'\b(?:IT)?(\d{11})\b', testo, re.I)
        piva = piva_match.group(1) if piva_match else "Non trovata"

        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', testo)
        email = email_match.group(0) if email_match else "N.D."

        return piva, email
    except:
        return "Errore Sito", "N.D."



def scrape_camerale_data(piva):
    """FASE 2: Estrazione da Ufficio Camerale con gestione Timeout."""
    piva_clean = "".join(filter(str.isdigit, str(piva)))
    if len(piva_clean) != 11:
        return "P.IVA non valida", "N.D."
    
    # Proviamo ad andare direttamente alla pagina dell'azienda se possibile, 
    # o usiamo la ricerca rapida
    url = f"https://www.ufficiocamerale.it/ricerca-aziende?q={piva_clean}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept-Language': 'it-IT,it;q=0.9',
            'Referer': 'https://www.google.it/'
        }
        
        # Aspetta un tempo casuale per simulare un umano (tra 3 e 5 secondi)
        import random
        time.sleep(random.uniform(3, 5))
        
        # Timeout alzato a 20 secondi per gestire i rallentamenti del server
        res = requests.get(url, headers=headers, timeout=20, verify=False)
        
        if res.status_code == 403:
            return "Accesso Negato (403)", "N.D."
            
        soup = BeautifulSoup(res.text, 'html.parser')

        # Se siamo ancora nella pagina di ricerca, proviamo a prendere il primo risultato
        if "Risultati della ricerca" in res.text or not soup.find('h1'):
            link = soup.find('a', href=re.compile(r'/azienda/'))
            if link:
                full_link = "https://www.ufficiocamerale.it" + link['href'] if not link['href'].startswith('http') else link['href']
                time.sleep(2)
                res = requests.get(full_link, headers=headers, timeout=20, verify=False)
                soup = BeautifulSoup(res.text, 'html.parser')

        # Estrazione dati basata sul testo della pagina
        testo = soup.get_text(separator='|', strip=True)

        # Regex flessibili
        fatt_match = re.search(r'Fatturato[:\s|]*€?\s*([\d.,]+)', testo, re.I)
        dip_match = re.search(r'Dipendenti[:\s|]*(\d+)', testo, re.I)

        fatturato = f"€ {fatt_match.group(1)}" if fatt_match else "N.D."
        dipendenti = dip_match.group(1) if dip_match else "N.D."

        return fatturato, dipendenti

    except requests.exceptions.Timeout:
        return "Timeout (Sito Lento)", "N.D."
    except Exception as e:
        return "Errore Connessione", "N.D."
        
    except Exception as e:
        # Questo cattura errori di connessione o timeout
        return "Errore Timeout", "N.D."
