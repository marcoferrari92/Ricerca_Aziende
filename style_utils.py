import pandas as pd

def applica_stile_tabella(df):
    """
    Ordina le colonne e applica i colori: 
    Verde (Google), Giallo (Crawler), Blu (AI).
    """
    # 1. Definizione dell'ordine richiesto
    ordine_richiesto = [
        'Ragione Sociale', 'Stato', 'Indirizzo', 'Sito Web',           # GOOGLE (Verdi)
        'Email (Crawler)', 'P.IVA (Crawler)',                         # CRAWLER (Gialle)
        'P.IVA (AI)', 'Fatturato (AI)', 'Dipendenti (AI)',            # AI (Blu)
        'ATECO (AI)', 'Ragione Sociale (AI)', 'Indirizzo (AI)', 'Nota/Fonte (AI)'
    ]
    
    # Prende solo le colonne che esistono effettivamente nel DF
    colonne_finali = [c for c in ordine_richiesto if c in df.columns]
    
    # Riordina il DataFrame
    df_ordinato = df[colonne_finali]

    # 2. Funzione interna per i colori
    def get_column_colors(col):
        name = col.name
        # Logica Colore VERDE (Google Maps - Colonne base senza tag)
        if name in ['Ragione Sociale', 'Stato', 'Indirizzo', 'Sito Web']:
            bg_color = '#d4edda' # Verde salvia chiaro
        
        # Logica Colore GIALLO (Crawler)
        elif '(Crawler)' in name:
            bg_color = '#fff3cd' # Giallo paglierino
            
        # Logica Colore BLU (AI)
        elif '(AI)' in name:
            bg_color = '#d1ecf1' # Blu carta da zucchero
            
        else:
            bg_color = ''
            
        return [f'background-color: {bg_color}; color: black' for _ in col]

    # Restituisce l'oggetto "Styler" di Pandas
    return df_ordinato.style.apply(get_column_colors, axis=0)
