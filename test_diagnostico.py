
import asyncio
import json
import logging
import sys
from pathlib import Path
import ccxt.async_support as ccxt

# --- Configurazione del Logging ---
log_file = 'diagnostics.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),
        logging.StreamHandler()
    ]
)

logging.info("--- INIZIO TEST DIAGNOSTICO ---")

# --- 1. Test dei Percorsi ---
logging.info("--- 1. Analisi Percorsi ---")
try:
    is_frozen = getattr(sys, 'frozen', False)
    logging.info(f"L'applicazione è compilata (frozen): {is_frozen}")

    if is_frozen:
        percorso_base = Path(sys.executable).parent
        logging.info(f"Percorso base calcolato (da sys.executable): {percorso_base}")
    else:
        percorso_base = Path(__file__).parent
        logging.info(f"Percorso base calcolato (da __file__): {percorso_base}")

    percorso_config = percorso_base / "config.json"
    logging.info(f"Percorso completo previsto per config.json: {percorso_config}")
    logging.info(f"Il file config.json esiste in quel percorso? {percorso_config.exists()}")
except Exception as e:
    logging.error(f"Errore durante l'analisi dei percorsi: {e}", exc_info=True)


# --- 2. Test Caricamento Configurazione ---
logging.info("--- 2. Caricamento config.json ---")
config = None
try:
    with open(percorso_config, 'r') as f:
        config = json.load(f)
    logging.info("File config.json caricato con successo.")
    # Per sicurezza, non loggare le chiavi API complete
    if config and 'piattaforme' in config and 'binance' in config['piattaforme']:
        binance_config_safe = config['piattaforme']['binance'].copy()
        if 'api_key' in binance_config_safe:
            binance_config_safe['api_key'] = f"{binance_config_safe['api_key'][:4]}..."
        if 'api_secret' in binance_config_safe:
            binance_config_safe['api_secret'] = "..."
        logging.debug(f"Configurazione Binance caricata (chiavi oscurate): {json.dumps(binance_config_safe, indent=2)}")
    else:
        logging.warning("Sezione 'binance' non trovata nella configurazione.")
except FileNotFoundError:
    logging.error(f"ERRORE CRITICO: Impossibile trovare il file config.json in {percorso_config}", exc_info=True)
except Exception as e:
    logging.error(f"ERRORE CRITICO: Impossibile leggere o parsare il file config.json: {e}", exc_info=True)


# --- 3. Test Inizializzazione CCXT ---
async def run_tests():
    if not config:
        logging.error("Test di rete saltati perché la configurazione non è stata caricata.")
        return

    logging.info("--- 3. Preparazione Inizializzazione CCXT ---")
    ccxt_config_spot = {}
    try:
        config_piattaforma = config['piattaforme']['binance']
        
        ccxt_config_spot = {
            'apiKey': config_piattaforma['api_key'],
            'secret': config_piattaforma['api_secret'],
            'enableRateLimit': True,
        }

        default_options = {'defaultType': 'spot'}
        if 'options' in config_piattaforma:
            logging.info(f"Trovate opzioni personalizzate in config.json: {config_piattaforma['options']}")
            default_options.update(config_piattaforma['options'])
        
        ccxt_config_spot['options'] = default_options

        logging.info(f"Configurazione finale che verrà passata a CCXT (per test SPOT): {ccxt_config_spot}")

    except Exception as e:
        logging.error(f"Errore durante la preparazione della configurazione CCXT: {e}", exc_info=True)
        return

    # --- 4. Test di Connettività ---
    logging.info("--- 4. Inizio Test di Connettività ---")
    
    # Test SPOT
    logging.info("--- 4a. Test Connessione SPOT ---")
    exchange_spot = None
    try:
        exchange_spot = ccxt.binance(ccxt_config_spot)
        ticker = await exchange_spot.fetch_ticker('BTC/USDT')
        logging.info(f"SUCCESS! Connessione a Binance SPOT riuscita. Prezzo BTC/USDT: {ticker['last']}")
    except Exception as e:
        logging.error(f"FALLIMENTO! Impossibile connettersi a Binance SPOT: {e}", exc_info=True)
    finally:
        if exchange_spot:
            await exchange_spot.close()

    # Test FUTURES (per replicare l'errore)
    logging.info("--- 4b. Test Connessione FUTURES (previsto fallimento) ---")
    exchange_futures = None
    try:
        # Creiamo una nuova config forzando il tipo 'future'
        ccxt_config_futures = ccxt_config_spot.copy()
        ccxt_config_futures['options'] = {'defaultType': 'future'}
        
        logging.info(f"Configurazione usata per il test FUTURES: {ccxt_config_futures}")
        
        exchange_futures = ccxt.binance(ccxt_config_futures)
        await exchange_futures.load_markets()
        logging.info("SUCCESS! Connessione a Binance FUTURES riuscita (inaspettato).")
    except Exception as e:
        logging.error(f"FALLIMENTO (PREVISTO): Impossibile connettersi a Binance FUTURES. Questo è l'errore che stiamo cercando di replicare. Dettagli: {e}", exc_info=True)
    finally:
        if exchange_futures:
            await exchange_futures.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
    logging.info("--- FINE TEST DIAGNOSTICO ---")
