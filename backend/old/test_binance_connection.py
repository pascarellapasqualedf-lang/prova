# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import asyncio
import ccxt.async_support as ccxt
import os
import json

# Percorso al file config.json (assumendo che sia nella root del progetto)
CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')

async def test_binance_connection():
    print("Tentativo di test della connessione a Binance...")
    
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Errore: File di configurazione non trovato a {CONFIG_FILE_PATH}")
        return
    except json.JSONDecodeError:
        print(f"Errore: Impossibile leggere il file di configurazione. Controlla la sintassi JSON a {CONFIG_FILE_PATH}")
        return

    binance_config = config.get('piattaforme', {}).get('binance', {})

    if not binance_config.get('attiva', False):
        print("Binance non è attiva nel file di configurazione. Abilitala per testare.")
        return

    api_key = binance_config.get('api_key')
    api_secret = binance_config.get('api_secret')

    if not api_key or api_key == "LA_TUA_API_KEY_BINANCE" or not api_secret or api_secret == "IL_TUO_API_SECRET_BINANCE":
        print("Errore: API Key o API Secret di Binance non configurati correttamente nel config.json.")
        return

    exchange = None
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {
                'defaultType': 'spot',
            },
            'enableRateLimit': True,
        })

        # Test di connessione: carica i mercati e ottieni l'ora del server
        await exchange.load_markets()
        server_time = await exchange.fetch_time()
        
        print(f"Connessione a Binance riuscita! Ora del server: {server_time}")
        print("Mercati caricati con successo.")

    except ccxt.AuthenticationError as e:
        print(f"Errore di autenticazione con Binance: {e}. Controlla le tue API Key e Secret.")
    except ccxt.NetworkError as e:
        print(f"Errore di rete con Binance: {e}. Controlla la tua connessione internet.")
    except Exception as e:
        print(f"Errore generico durante il test di Binance: {e}")
    finally:
        if exchange:
            await exchange.close()

if __name__ == '__main__':
    asyncio.run(test_binance_connection())
