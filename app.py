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

# 2. FUNZIONE DI RICERCA POTENZIATA
def fetch_data_multi(zona, macrosettori_scelti):
    # Endpoint più stabile e veloce
    url = "https://overpass.kumi.systems/api/interpreter"
    
    # Raccogliamo i tag senza duplicati
    tutti_i_tag = []
    for ms in macrosettori_scelti:
        tutti_i_tag.extend(ATECO_MAP[ms])
    regex_query = "|".join(set(tutti_i_tag))
    
    # Query con timeout esteso e istruzioni chiare
    query = f"""
    [out:json][timeout:180];
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
        response = requests.get(url, params={'data': query}, timeout=190)
        
        if response.status_code == 429:
            st.error("⚠️ Troppe richieste al server. Attendi un minuto.")
            return pd.DataFrame()
        
        # Tentativo di decodifica JSON con gestione errore "line 1 column 1"
        try:
            data = response.json()
        except ValueError:
            st.error("❌ Il server ha restituito un errore di traffico. Riprova tra poco o riduci i settori selezionati.")
            return pd.DataFrame()

        elements = data.get('elements', [])
        risultati = []
        for el in elements:
            t = el.get('tags', {})
            if 'name' in t:
                lat = el.get('lat') or el.get('center', {}).get('lat')
                lon = el.get('lon') or el.get('center', {}).get('lon')
                risultati.append({
                    'Ragione Sociale': t.get('name'),
                    'Comune': t.get('addr:city', 'N.D.'),
                    'Indirizzo': f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip() or 'N.D.',
                    'Sito Web': t.get('website', 'N.D.'),
                    'Telefono': t.get('phone', 'N.D.'),
                    'LAT': lat, 'LON': lon,
                    'Categoria OSM': t.get('office', t.get('industrial', t.get('shop', 'Altro')))
                })
        return pd.DataFrame(risultati)
    
    except requests.exceptions.Timeout:
        st.error("⏳ La ricerca ha richiesto troppo tempo. Prova a selezionare meno settori.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"⚠️ Errore imprevisto: {e}")
        return pd.DataFrame()

# 3. INTERFACCIA STREAMLIT
st.set_page_config(page_title="Business Finder Pro", layout="wide", page_icon="🏢")

st.title("🏢 Business Finder Multi-ATECO")
st.markdown("Cerca aziende filtrando per uno o più macrosettori ATECO ufficiali.")

with st.sidebar:
    st.header("🔍 Parametri")
    zona = st.text_input("Località (Città o Provincia)", "Vicenza")
    
    macrosettori_scelti = st.multiselect(
        "Seleziona Macrosettori ATECO",
        options=list(ATECO_MAP.keys()),
        default=["A - AGRICOLTURA, SILVICOLTURA E PESCA"]
    )
    
    st.divider()
    cerca = st.button("🚀 AVVIA RICERCA", use_container_width=True)
    st.caption("Nota: Selezionare troppi settori insieme può rallentare il server.")

if cerca:
    if not macrosettori_scelti:
        st.warning("Seleziona almeno un settore prima di iniziare.")
    else:
        with st.spinner(f"Ricerca in corso a {zona}..."):
            # Piccola attesa di sicurezza per non sovraccaricare l'IP
            time.sleep(1)
            df = fetch_data_multi(zona, macrosettori_scelti)
            
            if not df.empty:
                st.balloons()
                st.success(f"✅ Trovate {len(df)} aziende!")
                
                # Mappa e Tabella
                tab1, tab2 = st.tabs(["📍 Mappa Localizzazione", "📋 Elenco Dati"])
                
                with tab1:
                    st.map(df.dropna(subset=['LAT', 'LON']), latitude='LAT', longitude='LON')
                
                with tab2:
                    st.dataframe(df.drop(columns=['LAT', 'LON']), use_container_width=True)
                
                # Download CSV
                csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
                st.download_button(
                    label="📥 Scarica Database (CSV)",
                    data=csv,
                    file_name=f"export_{zona}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Nessun dato trovato o errore di connessione. Prova a cambiare zona o ridurre i settori.")
