import asyncio
import logging
import sqlite3
from ..core.database import get_db_connection
from .gestore_piattaforme import inizializza_piattaforma

async def aggiorna_e_salva_dati_ohlcv(nome_piattaforma: str, simbolo: str, timeframe: str, limit: int = 100):
    """
    Recupera i dati OHLCV da una piattaforma e li salva nel database.
    """
    piattaforma = None
    conn = None
    try:
        logging.info(f"Inizio aggiornamento OHLCV per {simbolo} su {nome_piattaforma} ({timeframe})...")
        
        # 1. Inizializza la piattaforma
        piattaforma = inizializza_piattaforma(nome_piattaforma)
        
        # 2. Recupera i dati OHLCV
        # ccxt restituisce una lista di liste: [timestamp, open, high, low, close, volume]
        ohlcv_data = await piattaforma.fetch_ohlcv(simbolo.upper(), timeframe, limit=limit)
        
        if not ohlcv_data:
            logging.warning(f"Nessun dato OHLCV ricevuto per {simbolo} su {nome_piattaforma}.")
            return

        # 3. Connessione al database
        conn = get_db_connection()
        if not conn:
            logging.error("Impossibile connettersi al database per salvare i dati OHLCV.")
            return
            
        cursor = conn.cursor()
        
        # 4. Prepara i dati per l'inserimento
        dati_da_inserire = []
        for candela in ohlcv_data:
            # Converte il timestamp da millisecondi a secondi
            timestamp_sec = candela[0] // 1000
            dati_da_inserire.append((
                nome_piattaforma,
                simbolo.upper(),
                timeframe,
                timestamp_sec,
                candela[1], # open
                candela[2], # high
                candela[3], # low
                candela[4], # close
                candela[5]  # volume
            ))
            
        # 5. Inserisci i dati nel database
        # L'uso di INSERT OR IGNORE previene l'inserimento di duplicati 
        # basandosi sul vincolo UNIQUE(exchange, symbol, timeframe, timestamp) definito nella tabella.
        cursor.executemany("""
            INSERT OR IGNORE INTO candlesticks (exchange, symbol, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, dati_da_inserire)
        
        conn.commit()
        
        logging.info(f"Salvati {cursor.rowcount} nuovi punti dati OHLCV per {simbolo} su {nome_piattaforma}.")

    except Exception as e:
        logging.error(f"Errore durante l'aggiornamento dei dati OHLCV per {simbolo}: {e}", exc_info=True)
    finally:
        # 6. Chiudi le connessioni
        if conn:
            conn.close()
        if piattaforma:
            await piattaforma.close()

async def main():
    """
    Funzione principale per testare il servizio di aggiornamento dati.
    """
    # Assicura che le tabelle del database esistano prima di procedere.
    from ..core.database import create_tables
    create_tables()
    logging.info("Verifica tabelle del database completata.")

    # Carica la configurazione per ottenere le piattaforme e i simboli da monitorare
    from ..core.gestore_configurazione import carica_configurazione
    config = carica_configurazione()
    
    piattaforme_attive = [p for p, conf in config['piattaforme'].items() if p != '_comment' and conf['attiva']]
    simboli_da_monitorare = config['parametri_ia']['cripto_preferite']
    
    # Esegui i task in modo sequenziale per ridurre il carico sulla rete e sull'API
    logging.info("Avvio dell'aggiornamento dei dati di mercato in modo sequenziale...")
    for piattaforma in piattaforme_attive:
        for simbolo in simboli_da_monitorare:
            coppia = f"{simbolo}/{config['piattaforme'][piattaforma]['options']['quote_currency']}"
            timeframes = ['1h', '4h', '1d']
            for timeframe in timeframes:
                # Aggiungiamo un ritardo per essere più gentili con l'API
                await asyncio.sleep(1) 
                await aggiorna_e_salva_dati_ohlcv(piattaforma, coppia, timeframe, 200)
    
    logging.info("Aggiornamento sequenziale dei dati di mercato completato.")


if __name__ == '__main__':
    # Configura un logging di base per il test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Per eseguire questo script direttamente, dobbiamo gestire il path di importazione
    import sys
    import os
    # Aggiungi la directory radice del progetto (TradeAI_V3) al path di sistema
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

    asyncio.run(main())
