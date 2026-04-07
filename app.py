import streamlit as st
import requests
import pandas as pd

# MAPPATURA INTEGRALE ATECO -> OPENSTREETMAP
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

def fetch_data(zona, lista_tag):
    url = "http://overpass-api.de/api/interpreter"
    regex_query = "|".join(lista_tag)
    query = f"""
    [out:json][timeout:90];
    area["name"="{zona}"]["admin_level"~"4|6|8"]->.searchArea;
    (
      nwr["shop"~"{regex_query}"](area.searchArea);
      nwr["craft"~"{regex_query}"](area.searchArea);
      nwr["industrial"~"{regex_query}"](area.searchArea);
      nwr["amenity"~"{regex_query}"](area.searchArea);
      nwr["landuse"~"{regex_query}"](area.searchArea);
      nwr["office"~"{regex_query}"](area.searchArea);
    );
    out center;
    """
    try:
        response = requests.get(url, params={'data': query})
        elements = response.json().get('elements', [])
        risultati = []
        for el in elements:
            t = el.get('tags', {})
            if 'name' in t:
                lat = el.get('lat') or el.get('center', {}).get('lat')
                lon = el.get('lon') or el.get('center', {}).get('lon')
                risultati.append({
                    'Ragione Sociale': t.get('name'),
                    'Comune': t.get('addr:city', 'N.D.'),
                    'Indirizzo': f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip(),
                    'Sito Web': t.get('website', 'N.D.'),
                    'Telefono': t.get('phone', 'N.D.'),
                    'LAT': lat, 'LON': lon
                })
        return pd.DataFrame(risultati)
    except:
        return pd.DataFrame()

# UI Streamlit
st.set_page_config(page_title="Business Finder ATECO", layout="wide")
st.title("🏢 Business Finder: Settori ATECO & Mappe")

zona = st.sidebar.text_input("Località (es: Vicenza)", "Vicenza")
ateco_key = st.sidebar.selectbox("Macrosettore ATECO", list(ATECO_MAP.keys()))

if st.sidebar.button("🚀 Avvia Ricerca"):
    df = fetch_data(zona, ATECO_MAP[ateco_key])
    if not df.empty:
        st.metric("Aziende trovate", len(df))
        st.map(df.dropna(subset=['LAT', 'LON']), latitude='LAT', longitude='LON')
        st.dataframe(df.drop(columns=['LAT', 'LON']), use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Scarica CSV", csv, "export.csv", "text/csv")
    else:
        st.warning("Nessun risultato trovato.")
