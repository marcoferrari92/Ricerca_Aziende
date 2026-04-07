import streamlit as st
import requests
import pandas as pd
import time

# 1. MAPPATURA INTEGRALE ATECO -> OPENSTREETMAP TAGS
ATECO_MAP = {
    "A - AGRICOLTURA, SILVICOLTURA E PESCA": ["farm", "farmyard", "greenhouse", "forestry", "vineyard", "aquaculture"],
    "B - ATTIVITA' ESTRATTIVE": ["quarry", "mine", "oil_well"],
    "C - ATTIVITA' MANIFATTURIERE": ["industrial", "factory", "works", "winery", "brewery", "sawmill"],
    "D - FORNITURA DI ENERGIA ELETTRICA, GAS, VAPORE": ["power_plant", "substation", "gas_works"],
    "E - ACQUA E GESTIONE RIFIUTI": ["water_works", "wastewater_plant", "landfill", "recycling"],
    "F - COSTRUZIONI": ["construction", "quarry"],
    "G - COMMERCIO ALL'INGROSSO E AL DETTAGLIO": ["shop", "retail", "wholesale", "supermarket", "warehouse"],
    "H - TRASPORTO E MAGAZZINAGGIO": ["logistics", "warehouse", "depot", "transport", "freight_forwarder"],
    "I - ATTIVITA' DEI SERVIZI DI ALLOGGIO E RISTORAZIONE": ["hotel", "restaurant", "cafe", "guest_house", "pub", "bar"],
    "J - ATTIVITA' EDITORIALI E MEDIA": ["office=newspaper", "studio", "office=publisher"],
    "K - TELECOMUNICAZIONI E INFORMATICA": ["office=it", "telecoms", "office=telecommunication", "data_center"],
    "L - ATTIVITA' FINANZIARIE E ASSICURATIVE": ["bank", "office=insurance", "office=financial", "atm"],
    "M - ATTIVITA' IMMOBILIARI": ["office=estate_agent", "real_estate"],
    "N - ATTIVITA' PROFESSIONALI, SCIENTIFICHE E TECNICHE": ["office=lawyer", "office=architect", "office=accountant", "office=research"],
    "O - ATTIVITA' AMMINISTRATIVE E DI SUPPORTO": ["office=government", "townhall", "office=employment_agency"],
    "P - ASSICURAZIONE SOCIALE OBBLIGATORIA": ["office=government", "public_service"],
    "Q - ISTRUZIONE E FORMAZIONE": ["school", "university", "college", "kindergarten"],
    "R - ATTIVITA' PER LA SALUTE E ASSISTENZA SOCIALE": ["hospital", "doctors", "clinic", "dentist", "social_facility"],
    "S - ATTIVITA' ARTISTICHE, SPORTIVE E DIVERTIMENTO": ["stadium", "gym", "museum", "theatre", "cinema", "sports_centre"],
    "T - ALTRE ATTIVITA' DI SERVIZI": ["hairdresser", "dry_cleaning", "funeral_hall", "office=association"],
    "V - ATTIVITA' DI ORGANIZZAZIONI EXTRATERRITORIALI": ["embassy", "office=ngo"]
}

# 2. TRASFORMA INDIRIZZO IN COORDINATE (Geocoding)
def get_lat_lon(indirizzo):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": indirizzo, "format": "json", "limit": 1}
    headers = {"User-Agent": "AtecoRadiusFinder/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers).json()
        if response:
            return float(response[0]["lat"]), float(response[0]["lon"])
    except:
        return None, None
    return None, None

# 3. RICERCA CIRCOLARE (AROUND)
def fetch_data_radius(lat, lon, raggio_km, settori):
    # Endpoint di riserva Kumi Systems (più veloce)
    url = "https://overpass.kumi.systems/api/interpreter"
    
    # Unione dei tag dei settori scelti
    tutti_tag = []
    for s in settori:
        tutti_tag.extend(ATECO_MAP[s])
    regex = "|".join(set(tutti_tag))
    
    raggio_metri = raggio_km * 1000
    
    # Query con filtro around
    query = f"""
    [out:json][timeout:120];
    (
      nwr["shop"~"{regex}"](around:{raggio_metri},{lat},{lon});
      nwr["craft"~"{regex}"](around:{raggio_metri},{lat},{lon});
      nwr["industrial"~"{regex}"](around:{raggio_metri},{lat},{lon});
      nwr["amenity"~"{regex}"](around:{raggio_metri},{lat},{lon});
      nwr["landuse"~"{regex}"](around:{raggio_metri},{lat},{lon});
      nwr["office"~"{regex}"](around:{raggio_metri},{lat},{lon});
    );
    out center;
    """
    try:
        resp = requests.get(url, params={'data': query}, timeout=130)
        data = resp.json()
        risultati = []
        for el in data.get('elements', []):
            t = el.get('tags', {})
            if 'name' in t:
                # Coordinate del risultato
                r_lat = el.get('lat') or el.get('center', {}).get('lat')
                r_lon = el.get('lon') or el.get('center', {}).get('lon')
                risultati.append({
                    'Ragione Sociale': t.get('name'),
                    'Comune': t.get('addr:city', 'N.D.'),
                    'Indirizzo': f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip() or 'N.D.',
                    'Sito Web': t.get('website', 'N.D.'),
                    'Telefono': t.get('phone', 'N.D.'),
                    'lat': r_lat, 'lon': r_lon,
                    'Tipo': t.get('industrial', t.get('shop', t.get('office', 'Settore Primario')))
                })
        return pd.DataFrame(risultati)
    except:
        return pd.DataFrame()

# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="ATECO Radius Finder", layout="wide")

st.title("📍 ATECO Radius Finder")
st.markdown("Trova aziende di specifici settori entro un raggio chilometrico da un punto scelto.")

with st.sidebar:
    st.header("⚙️ Configura Ricerca")
    punto_origine = st.text_input("Punto di origine (es: Vicenza, Via Roma 1)", "Vicenza")
    raggio_km = st.slider("Raggio di ricerca (KM)", 1, 50, 5)
    
    settori_scelti = st.multiselect(
        "Macrosettori ATECO",
        options=list(ATECO_MAP.keys()),
        default=["A - AGRICOLTURA, SILVICOLTURA E PESCA"]
    )
    
    st.divider()
    avvia = st.button("🚀 AVVIA RICERCA", use_container_width=True)

if avvia:
    if not settori_scelti:
        st.error("Seleziona almeno un settore ATECO!")
    else:
        with st.spinner("Geolocalizzazione in corso..."):
            lat_orig, lon_orig = get_lat_lon(punto_origine)
            
            if lat_orig:
                st.info(f"Ricerca avviata attorno a: {punto_origine} ({lat_orig}, {lon_orig})")
                
                df_finale = fetch_data_radius(lat_orig, lon_orig, raggio_km, settori_scelti)
                
                if not df_finale.empty:
                    st.success(f"Trovate {len(df_finale)} aziende nel raggio di {raggio_km} km.")
                    
                    # Layout Mappa e Tabella
                    st.map(df_finale[['lat', 'lon']])
                    
                    st.subheader("📋 Dettaglio Aziende")
                    st.dataframe(df_finale.drop(columns=['lat', 'lon']), use_container_width=True)
                    
                    # Download
                    csv = df_finale.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
                    st.download_button("📥 Scarica Database (CSV)", csv, "aziende_raggio.csv", "text/csv")
                else:
                    st.warning("Nessuna azienda trovata con questi criteri in questo raggio.")
            else:
                st.error("❌ Impossibile trovare l'indirizzo inserito. Prova a scrivere meglio il nome del comune.")
