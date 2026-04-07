import streamlit as st
import requests
import pandas as pd

# Dizionario ATECO -> OpenStreetMap (Invariato)
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

def fetch_data_multi(zona, macrosettori_scelti):
    url = "http://overpass-api.de/api/interpreter"
    
    # Raccogliamo TUTTI i tag di TUTTI i macrosettori selezionati
    tutti_i_tag = []
    for ms in macrosettori_scelti:
        tutti_i_tag.extend(ATECO_MAP[ms])
    
    # Creiamo la Regex OR (es: "farm|industrial|hotel")
    regex_query = "|".join(set(tutti_i_tag)) # set() rimuove eventuali duplicati
    
    query = f"""
    [out:json][timeout:120];
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
                    'LAT': lat, 'LON': lon,
                    'Categoria': t.get('office', t.get('industrial', t.get('shop', 'Altro')))
                })
        return pd.DataFrame(risultati)
    except Exception as e:
        st.error(f"Errore nella ricerca: {e}")
        return pd.DataFrame()

# --- UI STREAMLIT ---
st.set_page_config(page_title="Business Finder Pro", layout="wide")
st.title("🏢 Business Finder Multi-ATECO")

with st.sidebar:
    st.header("🔍 Filtri")
    zona = st.text_input("Località", "Vicenza")
    
    # QUI IL CAMBIO: st.multiselect invece di selectbox
    macrosettori_scelti = st.multiselect(
        "Seleziona uno o più Macrosettori ATECO",
        options=list(ATECO_MAP.keys()),
        default=["A - AGRICOLTURA, SILVICOLTURA E PESCA"] # Opzione predefinita
    )
    
    cerca = st.button("🚀 Avvia Ricerca Combinata")

if cerca:
    if not macrosettori_scelti:
        st.warning("Seleziona almeno un settore!")
    else:
        with st.spinner("Ricerca in corso su più settori..."):
            df = fetch_data_multi(zona, macrosettori_scelti)
            
            if not df.empty:
                st.success(f"Trovate {len(df)} aziende totali.")
                
                # Mappa interattiva
                st.map(df.dropna(subset=['LAT', 'LON']), latitude='LAT', longitude='LON')
                
                # Tabella dati
                st.dataframe(df.drop(columns=['LAT', 'LON']), use_container_width=True)
                
                # CSV Download
                csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
                st.download_button("📥 Scarica Risultati (CSV)", csv, f"export_{zona}.csv", "text/csv")
            else:
                st.error("Nessun risultato trovato per questa combinazione.")
