import streamlit as st
import requests
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="ATECO Map Finder", layout="wide")

# MAPPATURA ATECO (Versione Integrale)
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
    "K - TELECOMUNICAZIONI E INFORMATICA": ["office=it", "telecoms", "office=telecommunication", "data_center"],
    "N - ATTIVITA' PROFESSIONALI, SCIENTIFICHE E TECNICHE": ["office=lawyer", "office=architect", "office=accountant", "office=research"],
    "S - ARTE, SPORT E DIVERTIMENTO": ["stadium", "gym", "museum", "theatre", "cinema", "sports_centre"]
}

def fetch_data_radius(lat, lon, raggio_km, settori):
    url = "https://overpass-api.de/api/interpreter"
    tutti_tag = []
    for s in settori:
        tutti_tag.extend(ATECO_MAP[s])
    regex = "|".join(set(tutti_tag))
    raggio_m = raggio_km * 1000
    
    query = f"""
    [out:json][timeout:120];
    (
      nwr["shop"~"{regex}"](around:{raggio_m},{lat},{lon});
      nwr["craft"~"{regex}"](around:{raggio_m},{lat},{lon});
      nwr["industrial"~"{regex}"](around:{raggio_m},{lat},{lon});
      nwr["amenity"~"{regex}"](around:{raggio_m},{lat},{lon});
      nwr["office"~"{regex}"](around:{raggio_m},{lat},{lon});
    );
    out center;
    """
    try:
        resp = requests.get(url, params={'data': query}, timeout=130)
        elements = resp.json().get('elements', [])
        risultati = []
        for el in elements:
            t = el.get('tags', {})
            if 'name' in t:
                risultati.append({
                    'Ragione Sociale': t.get('name'),
                    'Comune': t.get('addr:city', 'N.D.'),
                    'Indirizzo': t.get('addr:street', 'N.D.'),
                    'lat': el.get('lat') or el.get('center', {}).get('lat'),
                    'lon': el.get('lon') or el.get('center', {}).get('lon'),
                    'Tipo': t.get('industrial', t.get('shop', t.get('office', 'Altro')))
                })
        return pd.DataFrame(risultati)
    except:
        return pd.DataFrame()

# --- UI APP ---
st.title("📍 ATECO Radius Picker")
st.markdown("1. Seleziona i settori. 2. Regola il raggio. 3. **Clicca sulla mappa** per posizionare il centro. 4. Avvia ricerca.")

# Sidebar
with st.sidebar:
    st.header("⚙️ Impostazioni")
    raggio_km = st.slider("Raggio di ricerca (KM)", 1, 30, 5)
    settori_scelti = st.multiselect("Settori ATECO", options=list(ATECO_MAP.keys()), default=[list(ATECO_MAP.keys())[0]])
    st.info("Dopo aver cliccato sulla mappa, apparirà il tasto per scaricare i dati.")

# Inizializzazione mappa centrata su Vicenza
m = folium.Map(location=[45.547, 11.546], zoom_start=11)

# Gestione del click sulla mappa
# Se l'utente clicca, memorizziamo le coordinate
map_data = st_folium(m, width=1000, height=500)

selected_lat = None
selected_lon = None

if map_data and map_data['last_clicked']:
    selected_lat = map_data['last_clicked']['lat']
    selected_lon = map_data['last_clicked']['lng']
    
    # Mostriamo visivamente dove l'utente ha cliccato con un cerchio
    st.write(f"✅ Centro impostato: **{selected_lat:.4f}, {selected_lon:.4f}**")
    
    # Bottone di ricerca che appare solo dopo il click
    if st.button(f"🚀 CERCA AZIENDE ENTRO {raggio_km}KM DA QUI"):
        with st.spinner("Estrazione dati in corso..."):
            df = fetch_data_radius(selected_lat, selected_lon, raggio_km, settori_scelti)
            
            if not df.empty:
                st.success(f"Trovate {len(df)} aziende!")
                
                # Visualizzazione risultati
                st.dataframe(df.drop(columns=['lat', 'lon']), use_container_width=True)
                
                csv = df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
                st.download_button("📥 Scarica CSV", csv, "aziende_selezionate.csv", "text/csv")
                
                # Mappa dei risultati finale
                res_map = folium.Map(location=[selected_lat, selected_lon], zoom_start=12)
                folium.Circle([selected_lat, selected_lon], radius=raggio_km*1000, color="red", fill=True).add_to(res_map)
                for _, row in df.iterrows():
                    folium.Marker([row['lat'], row['lon']], popup=row['Ragione Sociale']).add_to(res_map)
                st_folium(res_map, width=1000, height=500, key="result_map")
            else:
                st.warning("Nessuna azienda trovata in quest'area.")
else:
    st.warning("👈 Clicca su un punto della mappa qui sopra per scegliere il centro della ricerca.")
