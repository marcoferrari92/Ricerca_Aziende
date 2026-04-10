import pandas as pd

import pandas as pd

def applica_stile_tabella(df):
    """
    Ordina le colonne e applica i colori: 
    Verde (Google), Giallo (Crawler), Blu (AI).
    """
    # 1. Definizione dell'ordine richiesto (AGGIORNATO)
    ordine_richiesto = [
        'Ragione Sociale', 'Stato', 'Nazione', 'Provincia', 'Comune', 'CAP', 'Indirizzo', 'Sito Web', # GOOGLE (Verdi)
        'Email (Crawler)', 'P.IVA (Crawler)',                                                        # CRAWLER (Gialle)
        'P.IVA (AI)', 'Fatturato (AI)', 'Dipendenti (AI)',                                           # AI (Blu)
        'ATECO (AI)', 'Ragione Sociale (AI)', 'Indirizzo (AI)', 'Nota/Fonte (AI)', 'testo_raw'
    ]
    
    # Prende solo le colonne che esistono effettivamente nel DF per evitare crash
    colonne_presenti = [c for c in ordine_richiesto if c in df.columns]
    
    # Riordina il DataFrame
    df_ordinato = df[colonne_presenti]

    # 2. Funzione interna per i colori
    def get_column_colors(col):
        name = col.name
        
        # Logica Colore VERDE (Google Maps - Dati base strutturati e non)
        colonne_google = [
            'Ragione Sociale', 'Stato', 'Nazione', 'Provincia', 
            'Comune', 'CAP', 'Indirizzo', 'Sito Web'
        ]
        
        if name in colonne_google:
            bg_color = '#d4edda' # Verde salvia chiaro
        
        # Logica Colore GIALLO (Crawler)
        elif '(Crawler)' in name:
            bg_color = '#fff3cd' # Giallo paglierino
            
        # Logica Colore BLU (AI)
        elif '(AI)' in name:
            bg_color = '#d1ecf1' # Blu carta da zucchero
            
        elif name == 'testo_raw':
            bg_color = '#f8f9fa' # Grigio chiarissimo per il debug
            
        else:
            bg_color = ''
            
        return [f'background-color: {bg_color}; color: black' for _ in col]

    # Restituisce l'oggetto "Styler" di Pandas
    return df_ordinato.style.apply(get_column_colors, axis=0)
