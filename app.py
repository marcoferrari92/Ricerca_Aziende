import streamlit as st
import requests
import pandas as pd
import time

# 1. MAPPATURA INTEGRALE ATECO -> OPENSTREETMAP TAGS
# Traduzione dei settori burocratici in tag cartografici reali
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

# 2. FUNZIONE PER TROVARE LE COORDINATE DEL PUNTO DI PARTENZA
def get_lat_lon(indirizzo):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": indirizzo, "format": "json", "limit": 1}
    headers = {"User-Agent": "BusinessRadiusFinder/1.1"}
    try:
        response = requests.get(url, params=params, headers=headers).json()
        if response:
            return float(response[0]["lat"]), float(response[0]["lon"])
    except Exception as e:
        return None, None
    return None, None

# 3. FUNZIONE DI RICERCA CIRCOLARE (AROUND)
def fetch_data_radius(lat, lon, raggio_km, settori):
    # Endpoint ufficiale con timeout esteso
    url = "https://overpass-api.de/api/interpreter"
    
    # Prepariamo i tag per la query
    tutti_tag = []
    for s in settori:
        tutti_tag.extend(ATECO_MAP[s])
    regex = "|".join(set(tutti_tag))
    
    raggio_metri = raggio_km * 1000
    
    # Query potente: cerca in tutti i contenitori di dati OSM (NWR)
    query = f"""
    [out:json][timeout:180];
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
        resp = requests.get(url, params={'data': query}, timeout=190)
        data = resp.json()
        risultati = []
        for el in data.get('elements', []):
            t = el.get('tags', {})
            # Prendiamo solo elementi che hanno un nome e coordinate valide
            if 'name' in t:
                r_lat = el.get('lat') or el.get('center', {}).get('lat')
                r_lon = el.get('lon') or el.get('center', {}).get('lon')
                if r_lat and r_lon:
                    risultati.append({
                        'Ragione Sociale': t.get('name'),
                        'Comune': t.get('addr:city', 'N.D.'),
                        'Indirizzo': f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip() or 'N.D.',
                        'Sito Web': t.get('website', 'N.D.'),
                        'Telefono': t.get('phone', 'N.D.'),
                        'lat': r_lat, 
                        'lon': r_lon,
                        'Settore OSM': t.get('industrial', t.get('shop', t.get('office', t.get('amenity', 'Altro'))))
                    })
        
        df = pd.DataFrame(risultati)
        if not df.empty:
            # Pulizia duplicati (stessa azienda mappata due volte)
            df = df.drop_duplicates(subset=['Ragione Sociale', 'lat', 'lon'])
        return df
    except Exception as e:
        st.error(f"Errore tecnico durante la scansione: {e}")
        return pd.DataFrame()

# --- 4. INTERFACCIA UTENTE STREAMLIT ---
st.set_page_config(page_title="ATECO Radius Finder", layout="wide", page_icon="📍")

st.title("📍 ATECO Radius Finder")
st.markdown("Cerca aziende per macrosettore ATECO entro un raggio specifico da un indirizzo.")

with st.sidebar:
    st.header("⚙️ Filtri di Ricerca")
    punto_origine = st.text_input("Centro Ricerca (Città o Via)", "Vicenza, Italia")
    raggio_km = st.slider("Raggio di ricerca (KM)", 1, 50, 10)
    
    settori_scelti = st.multiselect(
        "Seleziona Macrosettori ATECO",
        options=list(ATECO_MAP.keys()),
        default=["A - AGRICOLTURA, SILVICOLTURA E PESCA"]
    )
    
    st.divider()
    avvia = st.button("🚀 AVVIA RICERCA", use_container_width=True)
    st.caption("Nota: Raggi ampi (>20km) e molti settori possono richiedere più tempo.")

if avvia:
    if not settori_scelti:
        st.error("Seleziona almeno un settore!")
    else:
        with st.spinner("Geolocalizzazione punto di origine..."):
            lat_orig, lon_orig = get_lat_lon(punto_origine)
            
            if lat_orig and lon_orig:
                st.success(f"Centro trovato! Ricerca entro {raggio_km} km da {punto_origine}")
                
                # Chiamata al motore di ricerca
                df_finale = fetch_data_radius(lat_orig, lon_orig, raggio_km, settori_scelti)
                
                if not df_finale.empty:
                    st.metric("Aziende individuate", len(df_finale))
                    
                    # Layout Mappa e Tabella
                    col_map, col_data = st.columns([2, 1])
                    
                    with col_map:
                        st.subheader("📍 Mappa")
                        # Visualizziamo i risultati
                        st.map(df_finale[['lat', 'lon']])
                    
                    with col_data:
                        st.subheader("📊 Distribuzione")
                        st.bar_chart(df_finale['Settore OSM'].value_counts())
                    
                    st.divider()
                    st.subheader("📋 Elenco Dettagliato")
                    st.dataframe(df_finale.drop(columns=['lat', 'lon']), use_container_width=True)
                    
                    # Download CSV
                    csv = df_finale.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
                    st.download_button(
                        label="📥 Scarica Database (CSV)",
                        data=csv,
                        file_name=f"aziende_raggio_{raggio_km}km.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("⚠️ Nessuna azienda trovata nel raggio scelto. Prova ad aumentare i KM o cambiare settore.")
            else:
                st.error("❌ Impossibile trovare la località inserita. Prova a scrivere il nome completo (es. 'Vicenza, Italia').")

st.caption("Dati estratti da OpenStreetMap (CC-BY-SA). L'app scansiona le attività censite sulla mappa mondiale.")
