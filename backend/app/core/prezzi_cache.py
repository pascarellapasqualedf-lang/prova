# Autore: Pascarella Pasquale Gerardo
# Versione: 1.1.0

import asyncio
import time
from typing import Dict, Optional
import logging

# Dizionario per memorizzare i prezzi in cache
# Formato: { 'SIMBOLO/QUOTE': { 'prezzo': float, 'timestamp': float } }
prezzi_cache: Dict[str, Dict[str, float]] = {}

# Tempo di validità della cache in secondi
CACHE_VALIDITY_SECONDS = 60

async def aggiorna_prezzi_cache(piattaforma_ccxt: any, simboli: list[str], quote_currency: str):
    """
    Aggiorna i prezzi dei simboli specificati nella cache usando la quote_currency fornita.
    Recupera i prezzi solo se non sono in cache o se la cache è scaduta.
    """
    global prezzi_cache
    current_time = time.time()
    
    coppie_da_aggiornare = []
    for simbolo in simboli:
        coppia = f"{simbolo}/{quote_currency}"
        # Controlla se il prezzo è già in cache e se è ancora valido
        if coppia not in prezzi_cache or (current_time - prezzi_cache[coppia].get('timestamp', 0)) > CACHE_VALIDITY_SECONDS:
            coppie_da_aggiornare.append(coppia)

    if coppie_da_aggiornare:
        logging.info(f"Aggiornamento prezzi cache per: {coppie_da_aggiornare}")
        fetch_tasks = [piattaforma_ccxt.fetch_ticker(coppia) for coppia in coppie_da_aggiornare]
        
        fetched_tickers_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for i, coppia in enumerate(coppie_da_aggiornare):
            ticker_result = fetched_tickers_results[i]
            if not isinstance(ticker_result, Exception) and ticker_result and 'last' in ticker_result and ticker_result['last'] is not None:
                prezzi_cache[coppia] = {
                    'prezzo': ticker_result['last'],
                    'timestamp': current_time
                }
            else:
                logging.warning(f"ATTENZIONE: Impossibile ottenere il prezzo per {coppia}: {ticker_result}")

def get_prezzo_cache(simbolo: str, quote_currency: str) -> Optional[float]:
    """
    Restituisce il prezzo di un simbolo contro una specifica quote_currency dalla cache.
    """
    global prezzi_cache
    current_time = time.time()
    coppia = f"{simbolo}/{quote_currency}"
    
    cache_entry = prezzi_cache.get(coppia)
    if cache_entry and (current_time - cache_entry.get('timestamp', 0)) <= CACHE_VALIDITY_SECONDS:
        return cache_entry.get('prezzo')
        
    logging.debug(f"Prezzo per {coppia} non in cache o scaduto.")
    return None

def get_prezzo_eur_cache() -> Optional[float]:
    """
    Restituisce sempre None, dato che la conversione EUR è stata rimossa.
    """
    return None