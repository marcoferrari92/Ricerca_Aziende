import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib3

# Disabilita avvisi SSL per evitare log fastidiosi
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import dei moduli locali
# Assicurati che utils.py contenga fetch_data_google, scrape_sito_aziendale, chiedi_a_openai
from mapping import ATECO_MAP 
from utils import fetch_data_google, scrape_sito_aziendale, chiedi_a_openai

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(layout="wide", page_title="Business Data Extractor Pro", page_icon="🏭")

# --- INIZIALIZZAZIONE SESSION STATE ---
if 'pos' not in st.session_state:
    st.session_state.pos = {'lat': 45.4642, 'lon': 9.1900} 
if 'results' not in st.session_state:
    st.session_state.results = pd.DataFrame()
if 'crawler_log' not in st.session_state:
    st.session_state.crawler_log = ""

# --- SIDEBAR: CONFIGURAZIONE ---
with st.sidebar:
    st.header("🔑 Accesso API")
    user_api_key = st.text_input("Google API Key", type="password")
    openai_api_key = st.text_input("OpenAI API Key", type="password", help="Per P.IVA, Fatturato e Dipendenti")
    
    st.divider()
    st.header("⚙️ Parametri")
    raggio = st.slider("Raggio Scansione (KM)", 1, 50, 5)
    scelte = st.multiselect("Settori (ATECO)", options=list(ATECO_MAP.keys()))
    max_test = st.number_input("Limite Risultati", 5, 500, 20) 

    if st.button("🗑️ Svuota Database", use_container_width=True):
        st.session_state.results = pd.DataFrame()
        st.rerun()

# --- LAYOUT PRINCIPALE ---
st.title("🏭 Business Data Extractor")

col_map, col_ctrl = st.columns([2, 1])

with col_map:
    st.subheader("1. Area di Ricerca")
    m = folium.Map(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], zoom_start=12)
    folium.Circle(location=[st.session_state.pos['lat'], st.session_state.pos['lon']], radius=raggio * 1000, color="#31333F", fill=True, opacity=0.1).add_to(m)

    if not st.session_state.results.empty:
        for _, row in st.session_state.results.iterrows():
            if pd.notnull(row['lat']) and pd.notnull(row['lon']):
                folium.Marker([row['lat'], row['lon']], tooltip=row['Ragione Sociale']).add_to(m)

    map_res = st_folium(m, width="100%", height=450, key="main_map")

    if map_res and map_res['last_clicked']:
        nl, nn = map_res['last_clicked']['lat'], map_res['last_clicked']['lng']
        st.session_state.pos = {'lat': nl, 'lon': nn}
        st.rerun()

with col_ctrl:
    st.subheader("2. Comandi Ricerca")
    st.info(f"📍 Centro: {st.session_state.pos['lat']:.4f}, {st.session_state.pos['lon']:.4f}")
    if st.button("🚀 AVVIA RICERCA GOOGLE", use_container_width=True, type="primary"):
        if not user_api_key: 
            st.error("Inserisci la Google API Key")
        elif not scelte: 
            st.warning("Seleziona un settore")
        else:
            keywords = []
            for s in scelte: 
                keywords.extend(ATECO_MAP.get(s, [s]))
            with st.status("Ricerca su Google Maps...") as status:
                df = fetch_data_google(st.session_state.pos['lat'], st.session_state.pos['lon'], raggio, keywords, user_api_key, max_results=max_test)
                
                # Inizializziamo le colonne vuote per evitare errori di visualizzazione
                cols_to_add = ['P.IVA (Crawler)', 'Email (Crawler)', 'P.IVA (AI)', 'Fatturato (AI)', 'Dipendenti (AI)', 'Nota/Fonte (AI)']
                for col in cols_to_add:
                    df[col] = "N.D."
                
                st.session_state.results = df
                status.update(label=f"Trovate {len(df)} aziende!", state="complete")
            st.rerun()

# --- TABELLA RISULTATI E ARRICCHIMENTO ---
if not st.session_state.results.empty:
    st.divider()
    
    st.subheader("3. Database Risultati")
    st.dataframe(st.session_state.results.drop(columns=['lat', 'lon', 'testo_raw'], errors='ignore'), use_container_width=True)
    
    # Pulsanti di azione
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    st.write("") 
    progress_placeholder = st.empty()
    log_placeholder = st.empty()

    with btn_col1:
        if st.button("🌐 1. AVVIA CRAWLER WEB", use_container_width=True):
            df_work = st.session_state.results.copy()
            bar = progress_placeholder.progress(0)
        
            # Puliamo il log precedente all'avvio di una nuova scansione
            st.session_state.crawler_log = "🚀 **Inizio Scansione...**\n\n"
        
            # Creiamo l'expander che rimarrà visibile
            with log_placeholder.expander("🔍 Debug Estrazione Numeri (Live)", expanded=True):
                debug_area = st.empty()

                for i, (idx, row) in enumerate(df_work.iterrows()):
                    if row['Sito Web'] != 'N.D.':
                        # Riceviamo i 4 valori dalla tua funzione aggiornata
                        p_web, e_web, testo_web, debug_info = scrape_sito_aziendale(row['Sito Web'])
                    
                        df_work.at[idx, 'P.IVA (Crawler)'] = p_web
                        df_work.at[idx, 'Email (Crawler)'] = e_web
                        df_work.at[idx, 'testo_raw'] = testo_web
                    
                        # Accumuliamo il log nello session_state
                        new_entry = f"**Azienda: {row['Ragione Sociale']}**\n{debug_info}\n\n---\n"
                        st.session_state.crawler_log += new_entry
                    
                        # Mostriamo l'aggiornamento in tempo reale
                        debug_area.markdown(st.session_state.crawler_log)

                    bar.progress((i + 1) / len(df_work))

                # Aggiorniamo i risultati finali
                st.session_state.results = df_work
                st.success("✅ Crawler completato!")
                # Nota: NON chiamare st.rerun() qui se vuoi che l'expander resti aperto con i dati correnti
    
    with btn_col2:
        if st.button("🤖 2. ANALISI INTELLIGENTE AI", use_container_width=True, type="primary"):
            if not openai_api_key:
                st.error("Inserisci la OpenAI Key!")
            elif st.session_state.results.empty:
                st.warning("Esegui prima la ricerca su Google!")
            else:
                df_work = st.session_state.results.copy()
                bar = progress_placeholder.progress(0, text="Preparazione Analisi AI...")
            
                # Expander per vedere cosa sta facendo l'AI in tempo reale
                with log_placeholder.expander("🕵️ Dettagli Analisi AI (Real-time)", expanded=True):
                    log_container = st.empty()
                    history = []

                    for i, (idx, row) in enumerate(df_work.iterrows()):
                        current_name = row['Ragione Sociale']
                        bar.progress((i + 1) / len(df_work), text=f"🤖 AI analizza: {current_name}")
                    
                        fatt, dip, piva_ai, fonte = chiedi_a_openai(
                            current_name, 
                            row.get('P.IVA (Crawler)', 'Non trovata'), 
                            row.get('Sito Web', 'N.D.'), 
                            row.get('Indirizzo', 'N.D.'),
                            row.get('testo_raw', ''),
                            openai_api_key
                        )
                    
                        # Aggiornamento DataFrame
                        df_work.at[idx, 'Fatturato (AI)'] = str(fatt)
                        df_work.at[idx, 'Dipendenti (AI)'] = str(dip)
                        df_work.at[idx, 'P.IVA (AI)'] = str(piva_ai)
                        df_work.at[idx, 'Nota/Fonte (AI)'] = str(fonte)
                    
                        # Update Log visivo
                        history.append(f"✅ **{current_name}** | P.IVA: {piva_ai} | Fatt: {fatt} | Fonte: {fonte}")
                        log_container.markdown("\n\n".join(history[-5:]))

                st.session_state.results = df_work
                st.success("Analisi AI Completata!")
                st.rerun()

    with btn_col3:
        csv = st.session_state.results.to_csv(index=False, encoding='utf-8-sig').encode('utf-8')
        st.download_button("📥 SCARICA DATABASE CSV", csv, "export_aziende.csv", "text/csv", use_container_width=True)
