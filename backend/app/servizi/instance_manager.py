# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import ccxt.async_support as ccxt
import logging

# Dizionario globale per mantenere le istanze delle piattaforme condivise
_platform_instances = {}

def get_platform_instance(nome_piattaforma: str):
    """
    Restituisce un'istanza condivisa della piattaforma, creandola se non esiste.
    Questo previene la creazione di centinaia di connessioni e risolve i memory leak.
    """
    from ..core.gestore_configurazione import carica_configurazione

    if nome_piattaforma not in _platform_instances:
        logging.info(f"Creazione di una nuova istanza CONDIVISA per la piattaforma: {nome_piattaforma}")
        config = carica_configurazione()
        config_piattaforma = config['piattaforme'][nome_piattaforma]

        ccxt_config = {
            'apiKey': config_piattaforma['api_key'],
            'secret': config_piattaforma['api_secret'],
            'enableRateLimit': True,
            'adjustForTimeDifference': True,
            'timeout': 30000,
        }

        if 'options' in config_piattaforma:
            user_options = config_piattaforma['options'].copy()
            if 'markets' in user_options:
                # Assicura che vengano passati solo i mercati attivati
                user_options['markets'] = {market: enabled for market, enabled in user_options['markets'].items() if enabled}
            ccxt_config['options'] = user_options

        piattaforma_classe = getattr(ccxt, nome_piattaforma)
        _platform_instances[nome_piattaforma] = piattaforma_classe(ccxt_config)
    
    return _platform_instances[nome_piattaforma]

async def close_all_instances():
    """
    Chiude tutte le istanze di piattaforma condivise aperte.
    Da chiamare solo allo shutdown dell'applicazione.
    """
    logging.info(f"Chiusura di {len(_platform_instances)} istanze di piattaforma condivise...")
    for nome_piattaforma, istanza in list(_platform_instances.items()):
        try:
            await istanza.close()
            logging.info(f"Istanza per {nome_piattaforma} chiusa con successo.")
            del _platform_instances[nome_piattaforma]
        except Exception as e:
            logging.warning(f"Errore durante la chiusura dell'istanza per {nome_piattaforma}: {e}")
    _platform_instances.clear()
    logging.info("Tutte le istanze di piattaforma sono state chiuse.")