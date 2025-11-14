# Autore: Pascarella Pasquale Gerardo
# Versione: 1.6.1

import ccxt.async_support as ccxt
from ccxt.base.errors import NotSupported
from ..core.gestore_configurazione import carica_configurazione
import logging
import traceback


def inizializza_piattaforma(nome_piattaforma: str):
    """
    Inizializza e restituisce un'istanza della piattaforma di scambio specificata usando ccxt.

    Args:
        nome_piattaforma: Il nome della piattaforma (es. 'binance', 'coinbase').

    Returns:
        Un'istanza di ccxt.Exchange pronta per l'uso.

    Raises:
        ValueError: Se la piattaforma non è configurata o non è supportata da ccxt.
    """
    config = carica_configurazione()
    
    if nome_piattaforma not in config['piattaforme']:
        raise ValueError(f"Piattaforma '{nome_piattaforma}' non trovata nel file di configurazione.")

    config_piattaforma = config['piattaforme'][nome_piattaforma]

    if not config_piattaforma.get('attiva', False):
        raise ValueError(f"Piattaforma '{nome_piattaforma}' non è attiva nella configurazione.")

    if not hasattr(ccxt, nome_piattaforma):
        raise ValueError(f"Piattaforma '{nome_piattaforma}' non è supportata dalla libreria ccxt.")

    piattaforma_classe = getattr(ccxt, nome_piattaforma)
    
    # Costruzione dinamica delle opzioni per CCXT
    ccxt_config = {
        'apiKey': config_piattaforma['api_key'],
        'secret': config_piattaforma['api_secret'],
        'enableRateLimit': True,
        'adjustForTimeDifference': True,
        'timeout': 30000,  # Aggiunto timeout di 30 secondi
    }

    # Aggiungi il blocco 'options' direttamente dalla configurazione dell'utente.
    if 'options' in config_piattaforma:
        # Filtra i mercati per includere solo quelli attivati (impostati su True)
        user_options = config_piattaforma['options'].copy()
        if 'markets' in user_options:
            user_options['markets'] = {market: enabled for market, enabled in user_options['markets'].items() if enabled}
        ccxt_config['options'] = user_options

    piattaforma = piattaforma_classe(ccxt_config)
    # Aggiungi la piattaforma alla lista delle connessioni aperte
    from ..core.app_state import open_connections
    open_connections.append(piattaforma)
    return piattaforma

async def recupera_ordini_aperti(nome_piattaforma: str, simbolo: str = None):
    """
    Recupera gli ordini aperti da una piattaforma di scambio.

    Args:
        nome_piattaforma: Il nome della piattaforma.
        simbolo: Il simbolo di trading per cui recuperare gli ordini (es. 'BTC/USDT').
                 Se None, recupera per tutti i simboli.

    Returns:
        Una lista di ordini aperti.
    """
    istanza = None
    try:
        print(f"[DEBUG] Inizializzazione piattaforma {nome_piattaforma}...")
        istanza = inizializza_piattaforma(nome_piattaforma)
        print(f"[DEBUG] Piattaforma {nome_piattaforma} inizializzata. has[fetchOpenOrders]: {istanza.has.get('fetchOpenOrders')}")

        if istanza.has['fetchOpenOrders']:
            print(f"[DEBUG] Chiamata a fetchOpenOrders per {nome_piattaforma} con simbolo {simbolo}...")
            original_warn_setting = None
            if simbolo is None and istanza.options.get('warnOnFetchOpenOrdersWithoutSymbol', True):
                original_warn_setting = istanza.options.get('warnOnFetchOpenOrdersWithoutSymbol')
                istanza.options['warnOnFetchOpenOrdersWithoutSymbol'] = False # Sopprimi il warning per questa chiamata

            ordini = await istanza.fetchOpenOrders(simbolo)
            
            if original_warn_setting is not None:
                istanza.options['warnOnFetchOpenOrdersWithoutSymbol'] = original_warn_setting # Ripristina l'impostazione originale

            print(f"[DEBUG] fetchOpenOrders completato. Trovati {len(ordini)} ordini.")
            return ordini
        else:
            print(f"[DEBUG] La piattaforma {nome_piattaforma} non supporta fetchOpenOrders.")
            raise NotSupported(f"La piattaforma '{nome_piattaforma}' non supporta il recupero degli ordini aperti.")
    except Exception:
        logging.error(f"Errore in recupera_ordini_aperti per {nome_piattaforma}:\n{traceback.format_exc()}")
        raise # Rilancia l'eccezione dopo averla loggata
    finally:
        if istanza and hasattr(istanza, 'close'):
            print(f"[DEBUG] Chiusura istanza piattaforma {nome_piattaforma}.")
            await istanza.close()

async def cancella_ordine(nome_piattaforma: str, order_id: str, simbolo: str = None):
    """
    Annulla un ordine specifico su una piattaforma di scambio.

    Args:
        nome_piattaforma: Il nome della piattaforma.
        order_id: L'ID dell'ordine da annullare.
        simbolo: Il simbolo di trading dell'ordine (opzionale, ma consigliato per alcuni exchange).

    Returns:
        Un dizionario con lo stato dell'annullamento.
    """
    istanza = None
    try:
        istanza = inizializza_piattaforma(nome_piattaforma)
        if istanza.has['cancelOrder']:
            response = await istanza.cancel_order(order_id, simbolo)
            logging.info(f"Ordine {order_id} su {nome_piattaforma} annullato con successo.")
            return {"status": "successo", "order_id": order_id, "response": response}
        else:
            raise NotSupported(f"La piattaforma '{nome_piattaforma}' non supporta l'annullamento degli ordini.")
    except Exception as e:
        logging.error(f"Errore durante l'annullamento dell'ordine {order_id} su {nome_piattaforma}: {e}")
        raise # Rilancia l'eccezione
    finally:
        if istanza and hasattr(istanza, 'close'):
            await istanza.close()
