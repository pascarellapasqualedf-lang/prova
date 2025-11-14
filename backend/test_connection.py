import sys
print(f"Esecuzione con Python versione: {sys.version}")

import asyncio
import ccxt.async_support as ccxt
import os
import json
import traceback

async def test_ohlcv_fetch():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Errore: File di configurazione non trovato a {config_path}")
        return
    except json.JSONDecodeError:
        print(f"Errore: Impossibile leggere il file di configurazione. Controlla la sintassi JSON.")
        return

    platform_name = 'binance' # O 'cryptocom' se preferisci testare quella
    symbol = 'BTC/USDT'
    timeframe = '1h'
    limit = 5

    exchange = None
    try:
        platform_config = config['piattaforme'][platform_name]
        if not platform_config.get('attiva'):
            print(f"Errore: La piattaforma '{platform_name}' non è attiva nel config.json.")
            return

        exchange_class = getattr(ccxt, platform_name)
        
        ccxt_options = {
            'apiKey': platform_config['api_key'],
            'secret': platform_config['api_secret'],
            'enableRateLimit': True,
            'adjustForTimeDifference': True,
            'options': {
                'defaultType': platform_config['options'].get('defaultType', 'spot'),
            },
        }
        
        if platform_name == 'binance':
            markets = platform_config.get('options', {}).get('markets', {})
            ccxt_options['urls'] = {
                'api': {
                    'public': 'https://api.binance.com/api/v3',
                    'private': 'https://api.binance.com/api/v3',
                    'web': 'https://www.binance.com',
                    'sapi': 'https://api.binance.com/sapi/v1',
                }
            }
            if markets.get('futures'):
                ccxt_options['urls']['api']['fapi'] = 'https://fapi.binance.com/fapi/v1'
            if markets.get('delivery'):
                ccxt_options['urls']['api']['dapi'] = 'https://dapi.binance.com/dapi/v1'


        exchange = exchange_class(ccxt_options)

        print(f"Tentativo di recupero OHLCV per {symbol} su {platform_name} ({timeframe})...")
        ohlcv_data = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

        if ohlcv_data:
            print(f"Recupero OHLCV riuscito per {symbol}:")
            for entry in ohlcv_data:
                print(f"  Timestamp: {entry[0]}, Open: {entry[1]}, High: {entry[2]}, Low: {entry[3]}, Close: {entry[4]}, Volume: {entry[5]}")
        else:
            print(f"Nessun dato OHLCV recuperato per {symbol}.")

    except Exception as e:
        print(f"Errore durante il test di recupero OHLCV: {e}")
        print(traceback.format_exc())
        print("Assicurati che le API keys siano corrette e che il tuo IP sia whitelisted sull'exchange (se richiesto).")
    finally:
        if exchange and hasattr(exchange, 'close'):
            await exchange.close()

if __name__ == "__main__":
    asyncio.run(test_ohlcv_fetch())
