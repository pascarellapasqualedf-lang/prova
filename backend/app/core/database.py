import sqlite3
import os
import logging
import sys
from datetime import datetime



# --- Logica per percorso dinamico del Database ---
def get_base_path():
    """Restituisce il percorso base corretto sia in modalità sorgente che compilata."""
    if getattr(sys, 'frozen', False):
        # Se eseguito come bundle (es. PyInstaller), il percorso base è la directory dell'eseguibile
        return os.path.dirname(sys.executable)
    else:
        # Se eseguito come script normale, calcola il percorso risalendo la struttura
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Il percorso del file DB sarà nella cartella 'data' relativa al percorso base
DB_FILE = os.path.join(get_base_path(), 'data', 'tradeai.db')

def get_db_connection():
    """Crea e restituisce una connessione al database SQLite."""
    conn = None
    try:
        # Assicura che la directory del database esista
        db_dir = os.path.dirname(DB_FILE)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logging.info(f"Directory del database creata in: {db_dir}")
            
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        logging.error(f"Errore durante la connessione al database: {e}")
    return conn

def create_tables():
    """Crea le tabelle del database se non esistono già."""
    conn = get_db_connection()
    if conn is None:
        logging.error("Impossibile creare le tabelle: connessione al database non riuscita.")
        return

    try:
        cursor = conn.cursor()

        # Tabella per i dati delle candele (OHLCV)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS candlesticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume REAL NOT NULL,
            UNIQUE(exchange, symbol, timeframe, timestamp)
        );
        """)
        logging.info("Tabella 'candlesticks' creata o già esistente.")

        # Tabella per lo storico del portafoglio
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL UNIQUE,
            total_balance_usd REAL NOT NULL,
            asset_balances TEXT NOT NULL -- JSON con i saldi degli asset
        );
        """)
        logging.info("Tabella 'portfolio_history' creata o già esistente.")

        # Tabella per le operazioni (trades)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            order_id TEXT UNIQUE NOT NULL,
            timestamp INTEGER NOT NULL,
            type TEXT NOT NULL, -- 'buy' or 'sell'
            price REAL NOT NULL,
            amount REAL NOT NULL,
            fee REAL
        );
        """)
        logging.info("Tabella 'trades' creata o già esistente.")

        # Tabella per le coppie in blacklist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS blacklist_coppie (
            coppia TEXT PRIMARY KEY,
            motivo_errore TEXT,
            data_inserimento TEXT NOT NULL
        );
        """)
        logging.info("Tabella 'blacklist_coppie' creata o già esistente.")

        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante la creazione delle tabelle: {e}")
    finally:
        if conn:
            conn.close()

def recupera_dati_ohlcv_da_db(exchange: str, symbol: str, timeframe: str, limit: int):
    """
    Recupera i dati OHLCV dal database locale.
    """
    conn = get_db_connection()
    if not conn:
        logging.error("Impossibile recuperare i dati OHLCV: connessione al database non riuscita.")
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume 
            FROM candlesticks 
            WHERE exchange = ? AND symbol = ? AND timeframe = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (exchange, symbol, timeframe, limit))
        
        rows = cursor.fetchall()
        return rows[::-1]
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero dei dati OHLCV dal DB: {e}")
        return []
    finally:
        if conn:
            conn.close()

def add_to_blacklist(coppia: str, motivo: str):
    """Aggiunge o aggiorna una coppia nella tabella di blacklist."""
    conn = get_db_connection()
    if not conn:
        logging.error(f"Impossibile aggiungere {coppia} alla blacklist: connessione DB fallita.")
        return

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO blacklist_coppie (coppia, motivo_errore, data_inserimento)
            VALUES (?, ?, ?)
            ON CONFLICT(coppia) DO UPDATE SET
            motivo_errore = excluded.motivo_errore,
            data_inserimento = excluded.data_inserimento;
        """, (coppia, motivo, datetime.now().isoformat()))
        conn.commit()
        logging.info(f"Coppia {coppia} aggiunta/aggiornata nella blacklist.")
    except sqlite3.Error as e:
        logging.error(f"Errore durante l'aggiunta di {coppia} alla blacklist: {e}")
    finally:
        if conn:
            conn.close()

def get_blacklisted_pairs_set() -> set:
    """Recupera tutte le coppie dalla blacklist e le restituisce come un set per un controllo rapido."""
    conn = get_db_connection()
    if not conn:
        logging.error("Impossibile recuperare la blacklist: connessione DB fallita.")
        return set()

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT coppia FROM blacklist_coppie")
        rows = cursor.fetchall()
        return {row[0] for row in rows}
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero della blacklist dal DB: {e}")
        return set()
    finally:
        if conn:
            conn.close()

def get_blacklist_details() -> list:
    """Recupera i dettagli di tutte le coppie dalla blacklist per l'API."""
    conn = get_db_connection()
    if not conn:
        logging.error("Impossibile recuperare i dettagli della blacklist: connessione DB fallita.")
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT coppia, motivo_errore, data_inserimento FROM blacklist_coppie ORDER BY data_inserimento DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero dei dettagli della blacklist: {e}")
        return []
    finally:
        if conn:
            conn.close()

def remove_from_blacklist(coppia: str) -> bool:
    """Rimuove una coppia dalla tabella di blacklist."""
    conn = get_db_connection()
    if not conn:
        logging.error(f"Impossibile rimuovere {coppia} dalla blacklist: connessione DB fallita.")
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blacklist_coppie WHERE coppia = ?", (coppia,))
        conn.commit()
        if cursor.rowcount > 0:
            logging.info(f"Coppia {coppia} rimossa dalla blacklist.")
            return True
        else:
            logging.warning(f"Coppia {coppia} non trovata nella blacklist.")
            return False
    except sqlite3.Error as e:
        logging.error(f"Errore durante la rimozione di {coppia} dalla blacklist: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    logging.info("Inizializzazione del database...")
    create_tables()
    logging.info("Inizializzazione del database completata.")