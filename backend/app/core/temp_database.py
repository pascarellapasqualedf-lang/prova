import sqlite3
import os
import logging
import sys
from datetime import datetime

# --- Logica per percorso dinamico del Database ---
def get_base_path():
    """Restituisce il percorso base corretto sia in modalità sorgente che compilata."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_FILE = os.path.join(get_base_path(), 'data', 'tradeai.db')

def get_db_connection():
    """Crea e restituisce una connessione al database SQLite."""
    conn = None
    try:
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
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS operazioni (
            id_operazione TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            piattaforma TEXT NOT NULL,
            coppia TEXT NOT NULL,
            tipo TEXT NOT NULL,
            quantita REAL NOT NULL,
            prezzo REAL NOT NULL,
            controvalore_usd REAL NOT NULL,
            commissioni_usd REAL NOT NULL,
            profitto_perdita_operazione REAL NOT NULL,
            motivo_vendita TEXT
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventi (
            id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            tipo_evento TEXT NOT NULL,
            piattaforma TEXT,
            coppia TEXT,
            dettagli TEXT
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS blacklist_coppie (
            coppia TEXT PRIMARY KEY,
            motivo_errore TEXT,
            data_inserimento TEXT NOT NULL
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifiche (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            titolo TEXT NOT NULL,
            messaggio TEXT NOT NULL,
            letta INTEGER NOT NULL DEFAULT 0
        );
        """)
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante la creazione delle tabelle: {e}")
    finally:
        if conn:
            conn.close()

def salva_evento_db(tipo_evento: str, piattaforma: str = None, coppia: str = None, dettagli: str = None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO eventi (timestamp, tipo_evento, piattaforma, coppia, dettagli) VALUES (?, ?, ?, ?, ?)", (datetime.now().isoformat(), tipo_evento, piattaforma, coppia, dettagli))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante il salvataggio dell'evento '{tipo_evento}': {e}")
    finally:
        if conn:
            conn.close()

def salva_operazione_db(operazione, motivo_vendita: str = None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO operazioni (id_operazione, timestamp, piattaforma, coppia, tipo, quantita, prezzo, controvalore_usd, commissioni_usd, profitto_perdita_operazione, motivo_vendita) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (operazione.id_operazione, operazione.timestamp.isoformat(), operazione.piattaforma, operazione.coppia, operazione.tipo, operazione.quantita, operazione.prezzo, operazione.controvalore_usd, operazione.commissioni_usd, operazione.profitto_perdita_operazione, motivo_vendita))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante il salvataggio dell'operazione {operazione.id_operazione}: {e}")
    finally:
        if conn:
            conn.close()

def recupera_operazioni_db(limit: int = 100) -> list:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM operazioni ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero delle operazioni: {e}")
        return []
    finally:
        if conn:
            conn.close()

def recupera_eventi_db(limit: int = 100) -> list:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM eventi ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero degli eventi: {e}")
        return []
    finally:
        if conn:
            conn.close()

def add_to_blacklist(coppia: str, motivo: str):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO blacklist_coppie (coppia, motivo_errore, data_inserimento) VALUES (?, ?, ?)", (coppia, motivo, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante l'aggiunta alla blacklist: {e}")
    finally:
        if conn:
            conn.close()

def get_blacklisted_pairs_set() -> set:
    conn = get_db_connection()
    if not conn:
        return set()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT coppia FROM blacklist_coppie")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero della blacklist: {e}")
        return set()
    finally:
        if conn:
            conn.close()

def get_blacklist_details() -> list:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM blacklist_coppie ORDER BY data_inserimento DESC")
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero dei dettagli della blacklist: {e}")
        return []
    finally:
        if conn:
            conn.close()

def remove_from_blacklist(coppia: str) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blacklist_coppie WHERE coppia = ?", (coppia,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logging.error(f"Errore durante la rimozione dalla blacklist: {e}")
        return False
    finally:
        if conn:
            conn.close()

def crea_notifica(titolo: str, messaggio: str):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notifiche (timestamp, titolo, messaggio) VALUES (?, ?, ?)", (datetime.now().isoformat(), titolo, messaggio))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante la creazione della notifica: {e}")
    finally:
        if conn:
            conn.close()

def recupera_notifiche(solo_non_lette: bool = False, limit: int = 20) -> list:
    conn = get_db_connection()
    if not conn:
        return []
    try:
        query = "SELECT * FROM notifiche"
        if solo_non_lette:
            query += " WHERE letta = 0"
        query += " ORDER BY timestamp DESC LIMIT ?"
        cursor = conn.cursor()
        cursor.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"Errore durante il recupero delle notifiche: {e}")
        return []
    finally:
        if conn:
            conn.close()

def segna_notifiche_come_lette():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifiche SET letta = 1 WHERE letta = 0")
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Errore durante l'aggiornamento delle notifiche: {e}")
    finally:
        if conn:
            conn.close()

create_tables()
