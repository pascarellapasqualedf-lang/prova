# Autore: Pascarella Pasquale Gerardo
# Versione: Centralizzata in config.json

import json
import os
import asyncio
import logging
import time
import ccxt
from ccxt import TRUNCATE
from logging.handlers import TimedRotatingFileHandler
from typing import Optional # Aggiunto
from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError
from datetime import datetime, timedelta # Aggiunto per la logica di cooldown

# Variabili globali per lo stato del bot AI
ai_trading_active = False
ai_trading_task = None # Useremo un task asyncio invece di un thread

# Lista di attesa per asset venduti di recente (coppia, timestamp)
asset_venduti_di_recente = []


# Modelli Pydantic per la validazione della configurazione
class ImpostazioniGenerali(BaseModel):
    budget_totale_usd: float
    percentuale_rischio_per_operazione: float
    modalita_automatica_attiva: bool
    modalita_reale_attiva: bool
    intervallo_aggiornamento_secondi: int
    intervallo_aggiornamento_dashboard_secondi: Optional[int] = 120
    min_buy_notional_usd: float # Aggiunto
    min_sell_notional_usd: float # Aggiunto

class LoggingConfig(BaseModel):
    percorso_file_log: str
    livello_log: str

class MarketsConfig(BaseModel):
    spot: bool
    futures: Optional[bool] = None
    delivery: Optional[bool] = None

class PlatformOptions(BaseModel):
    defaultType: str
    quote_currency: str
    markets: MarketsConfig
    recvWindow: Optional[int] = None

class PiattaformaConfig(BaseModel):
    attiva: bool
    api_key: str
    api_secret: str
    options: PlatformOptions

class Piattaforme(BaseModel):
    _comment: Optional[str] = None
    coinbase: PiattaformaConfig
    binance: PiattaformaConfig
    cryptocom: PiattaformaConfig

class ParametriIA(BaseModel):
    cripto_preferite: list[str]
    target_profitto_settimanale_percentuale: float
    stop_loss_percentuale: float
    percentuale_take_profit: Optional[float] = None # Aggiunto
    orario_reset_cooldown: Optional[str] = "06:00"
    attiva_cooldown_dopo_vendita: Optional[bool] = True

class GestioneRischioDinamico(BaseModel):
    attiva: bool
    moltiplicatore_confidenza_media: float
    moltiplicatore_confidenza_alta: float

class SelezioneAssetDinamica(BaseModel):
    attiva: bool
    numero_asset_da_considerare: int
    ignora_preferiti_con_dinamica: Optional[bool] = False

class TrailingStopLoss(BaseModel):
    attiva: bool
    percentuale_distanza: float

class AnalisiMultiTimeframe(BaseModel):
    attiva: bool
    timeframes: list[str]
    pesi: list[float]

class Tassazione(BaseModel):
    percentuale_tasse: float

class ParametriIndicatori(BaseModel):
    sma_periodo: int
    rsi_periodo: int
    macd_periodo_veloce: int
    macd_periodo_lento: int
    macd_periodo_segnale: int
    bollinger_periodo: int
    bollinger_deviazioni_std: int
    adx_periodo: int

class ConfigModel(BaseModel):
    _comment_autore: str
    versione_config: str
    impostazioni_generali: ImpostazioniGenerali
    logging: LoggingConfig
    piattaforme: Piattaforme
    parametri_ia: ParametriIA
    gestione_rischio_dinamico: GestioneRischioDinamico
    selezione_asset_dinamica: SelezioneAssetDinamica
    trailing_stop_loss: TrailingStopLoss
    analisi_multi_timeframe: AnalisiMultiTimeframe
    tassazione: Tassazione
    parametri_indicatori: ParametriIndicatori

# Modello Pydantic per le operazioni manuali
class OperazioneManuale(BaseModel):
    piattaforma: str
    simbolo: str
    quantita: float
    prezzo: float
    tipo_ordine: str = 'market' # Aggiunto il tipo di ordine

from .core.cervello_ia import analizza_mercato_e_genera_segnale, ottimizza_portafoglio_simulato, suggerisci_strategie_di_mercato
from .core.gestore_operazioni import gestore_globale_portafoglio
from .core.prezzi_cache import aggiorna_prezzi_cache, get_prezzo_cache, get_prezzo_eur_cache
from .core.database import recupera_dati_ohlcv_da_db, create_tables, get_blacklisted_pairs_set, add_to_blacklist, get_blacklist_details, remove_from_blacklist, recupera_operazioni_db, salva_evento_db, recupera_eventi_db, crea_notifica, recupera_notifiche, segna_notifiche_come_lette


from .servizi.instance_manager import get_platform_instance, close_all_instances
from .servizi.gestore_piattaforme import recupera_ordini_aperti

from .core.cache_manager import get_dashboard_cache, set_dashboard_cache
from .servizi.market_data_service import aggiorna_e_salva_dati_ohlcv
from .core.gestore_configurazione import carica_configurazione

# Carica la configurazione per ottenere la versione del software
config = carica_configurazione()
software_version = config.get("versione_config", "0.0.0")

app = FastAPI(
    title="Trade AI Backend",
    description="API per la gestione del bot di trading automatico.",
    version=software_version
)

def setup_logging():
    """Configura il sistema di logging basandosi su config.json."""
    from .core.gestore_configurazione import carica_configurazione
    # Importa LOG_PATH dal gestore centralizzato
    from .core.path_manager import LOG_PATH
    try:
        config = carica_configurazione()
        log_config = config.get('logging', {})
        log_level_str = log_config.get('livello_log', 'INFO').upper()
        # Usa il percorso corretto da path_manager
        log_path = LOG_PATH / "backend.log"

        log_level = getattr(logging, log_level_str, logging.INFO)
        
        # Assicura che la directory del log esista (già fatto da path_manager, ma ridondante per sicurezza)
        log_path.parent.mkdir(exist_ok=True)

        # Configura il logger principale
        logger = logging.getLogger()
        logger.setLevel(log_level)
        
        # Rimuovi i gestori esistenti per evitare duplicazioni
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Formattatore
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Gestore per la console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level) # Aggiunto per robustezza
        logger.addHandler(console_handler)

        # Gestore per file con rotazione temporale
        file_handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1, backupCount=7)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level) # Aggiunto per robustezza
        logger.addHandler(file_handler)
        
        logging.info(f"Logging configurato. Livello: {log_level_str}, Percorso: {log_path}")

    except Exception as e:
        # Fallback a una configurazione di base se tutto il resto fallisce
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.error(f"Errore durante la configurazione del logging: {e}. Uso la configurazione di base.")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.25.128:5174", # Nuovo IP del frontend
        "http://192.168.48.137:5174",  # URL del tuo frontend
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "app://.", # Per Electron
        "null" # Per alcuni contesti file://
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def market_data_update_loop():
    """
    Ciclo in background che aggiorna periodicamente i dati OHLCV per le coppie monitorate.
    Esegue gli aggiornamenti in parallelo ma con concorrenza limitata per non sovraccaricare le API.
    """
    await asyncio.sleep(15)
    logging.info("Avvio del loop di aggiornamento periodico dei dati di mercato...")

    # Limita la concorrenza per evitare di essere bannati o di ricevere timeout dall'exchange
    semaphore = asyncio.Semaphore(5)

    while True:
        try:
            from .core.gestore_configurazione import carica_configurazione
            config = carica_configurazione()
            
            piattaforme_attive = [p for p, conf in config['piattaforme'].items() if p != '_comment' and conf['attiva']]
            simboli_da_monitorare = config['parametri_ia']['cripto_preferite']
            intervallo_aggiornamento_dati_mercato_secondi = config.get('impostazioni_generali', {}).get('intervallo_aggiornamento_dati_mercato_secondi', 3600)

            logging.info(f"Inizio ciclo di aggiornamento dati di mercato per {len(piattaforme_attive)} piattaforme e {len(simboli_da_monitorare)} simboli.")

            async def wrapped_update(piattaforma, coppia, timeframe, limit):
                async with semaphore:
                    return await aggiorna_e_salva_dati_ohlcv(piattaforma, coppia, timeframe, limit)

            tasks = []
            for piattaforma in piattaforme_attive:
                quote_currency = config['piattaforme'][piattaforma]['options']['quote_currency']
                for simbolo in simboli_da_monitorare:
                    coppia = f"{simbolo}/{quote_currency}"
                    timeframes = ['1h', '4h', '1d']
                    for timeframe in timeframes:
                        task = wrapped_update(piattaforma, coppia, timeframe, limit=200)
                        tasks.append(task)
            
            logging.info(f"Avvio di {len(tasks)} task di aggiornamento con concorrenza limitata (max 5)...")
            risultati = await asyncio.gather(*tasks, return_exceptions=True)

            error_count = 0
            for risultato in risultati:
                if isinstance(risultato, Exception):
                    logging.error(f"Errore in un task di aggiornamento: {risultato}")
                    error_count += 1

            if error_count > 0:
                logging.warning(f"{error_count}/{len(tasks)} task di aggiornamento falliti.")

            logging.info(f"Ciclo di aggiornamento dati di mercato completato. Prossimo aggiornamento tra {intervallo_aggiornamento_dati_mercato_secondi} secondi.")
            await asyncio.sleep(intervallo_aggiornamento_dati_mercato_secondi)

        except Exception as e:
            logging.error(f"Errore grave nel loop di aggiornamento dati di mercato: {e}", exc_info=True)
            await asyncio.sleep(300)


@app.on_event("startup")
async def startup_event():
    """
    Gestisce gli eventi di avvio dell'applicazione.
    Avvia i processi in background (bot AI, aggiornamento cache dashboard).
    """
    # Crea le tabelle del database se non esistono. DEVE essere una delle prime cose fatte.
    create_tables()
    
    setup_logging()
    logging.info("Avvio dell'applicazione Trade AI...")
    
    try:
        # Riconcilia i saldi con le piattaforme reali all'avvio
        await gestore_globale_portafoglio.reconcile_balances_with_exchange()

        # Avvia il loop di aggiornamento della cache della dashboard
        asyncio.create_task(dashboard_update_loop())
        logging.info("Loop di aggiornamento cache dashboard avviato.")

        # Avvia il loop di aggiornamento dei dati di mercato
        asyncio.create_task(market_data_update_loop())
        logging.info("Loop di aggiornamento dati di mercato avviato.")

        from .core.gestore_configurazione import carica_configurazione
        config = carica_configurazione()
        if config['impostazioni_generali']['modalita_automatica_attiva']:
            logging.info("Modalità automatica attiva all'avvio. Avvio il bot AI...")
            await start_ai_trading()

    except Exception as e:
        logging.error(f"Errore durante l'evento di startup: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """Alla chiusura dell'applicazione, ferma il ciclo di trading e chiude tutte le connessioni."""
    global ai_trading_active, ai_trading_task
    if ai_trading_active and ai_trading_task:
        ai_trading_active = False
        ai_trading_task.cancel()
        try:
            await ai_trading_task
        except asyncio.CancelledError:
            pass # Il task è stato cancellato, è normale
        logging.info("AI Trading disattivato alla chiusura.")

    # Chiudi tutte le istanze di piattaforma condivise
    await close_all_instances()

@app.get("/", tags=["Generale"])
async def root():
    """
    Endpoint principale per verificare lo stato del server.
    """
    return {"messaggio": "Benvenuto nel backend di Trade AI!"}


@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    """
    Endpoint silente per gestire la richiesta automatica del favicon da parte dei browser.
    Restituisce uno status 204 No Content per evitare errori 404 nei log.
    """
    return Response(status_code=204)


@app.get("/test_connessione/{nome_piattaforma}", tags=["Piattaforme"])
async def test_connessione_piattaforma(nome_piattaforma: str):
    """
    Testa la connessione a una piattaforma e restituisce il saldo totale.
    """
    from .core.gestore_configurazione import carica_configurazione # Importa qui per evitare dipendenze circolari o carichi inutili
    try:
        config = carica_configurazione()
        piattaforma_config = config['piattaforme'].get(nome_piattaforma.lower())
        if not piattaforma_config:
            raise HTTPException(status_code=404, detail=f"Configurazione per la piattaforma {nome_piattaforma} non trovata.")
        
        quote_currency = piattaforma_config.get('options', {}).get('quote_currency', 'USDT')

        piattaforma = get_platform_instance(nome_piattaforma.lower())
        await piattaforma.load_markets()
        saldo = await piattaforma.fetch_balance()

        total_usd_estimated = 0.0
        stablecoins = ['USDT', 'BUSD', 'USDC', 'DAI'] # Aggiungi altre stablecoin se necessario
        assets_to_fetch_price = set() # Inizializza come un set vuoto

        # Combina saldi free e used per calcolare il totale
        all_balances = {}
        for asset, amount in saldo.get('free', {}).items():
            all_balances[asset] = all_balances.get(asset, 0.0) + float(amount)
        for asset, amount in saldo.get('used', {}).items():
            all_balances[asset] = all_balances.get(asset, 0.0) + float(amount)

        for asset, amount in all_balances.items():
            if amount <= 0: # Salta asset con quantità zero o negativa
                continue

            if asset in stablecoins: # Se è una stablecoin, aggiungi direttamente il valore
                total_usd_estimated += amount
            else:
                # Prova a ottenere il prezzo dalla cache
                price = get_prezzo_cache(asset, quote_currency) # Passa quote_currency
                if price is None:
                    # Se non in cache o scaduto, aggiungi alla lista per il recupero
                    assets_to_fetch_price.add(asset)
                else:
                    total_usd_estimated += all_balances[asset] * price

        # Recupera i prezzi mancanti in parallelo e aggiorna la cache
        if assets_to_fetch_price:
            await aggiorna_prezzi_cache(piattaforma, list(assets_to_fetch_price), quote_currency) # Passa quote_currency
            # Ricalcola il totale USD con i prezzi aggiornati dalla cache
            total_usd_estimated = 0.0
            for asset, amount in all_balances.items():
                if amount <= 0: continue
                if asset in stablecoins:
                    total_usd_estimated += amount
                else:
                    price = get_prezzo_cache(asset, quote_currency) # Passa quote_currency
                    if price is not None:
                        total_usd_estimated += all_balances[asset] * price
                    else:
                        logging.warning(f"Prezzo per {asset} non disponibile dopo l'aggiornamento cache.")

        logging.debug(f"Calcolato total_usd_estimated per {nome_piattaforma}: {total_usd_estimated}") # Nuovo debug

        # Filtra i saldi a zero (già fatto sopra, ma per coerenza con la struttura)
        filtered_free = {asset: amount for asset, amount in saldo.get('free', {}).items() if float(amount) > 0}
        filtered_used = {asset: amount for asset, amount in saldo.get('used', {}).items() if float(amount) > 0}

        return {
            "piattaforma": nome_piattaforma,
            "status": "Connessione riuscita",
            "dati_saldo": {
                "total_usd_estimated": total_usd_estimated,
                "free": filtered_free,
                "used": filtered_used,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante la connessione a {nome_piattaforma}: {str(e)}")


@app.get("/suggerimento_ia/{nome_piattaforma}/{coppia:path}", tags=["Intelligenza Artificiale"])
async def ottieni_suggerimento_ia(nome_piattaforma: str, coppia: str):
    """
    Esegue l'analisi di mercato per una data coppia e restituisce un segnale di trading.
    """
    from .core.gestore_configurazione import carica_configurazione
    piattaforma_ccxt = None # Initialize to None
    try:
        config = carica_configurazione()
        modalita_reale = config.get('impostazioni_generali', {}).get('modalita_reale_attiva', False)
        
        # Inizializza la piattaforma
        piattaforma_ccxt = get_platform_instance(nome_piattaforma.lower())
        await piattaforma_ccxt.load_markets() # Carica i mercati

        suggerimento = await analizza_mercato_e_genera_segnale(piattaforma_ccxt, coppia.upper())
        
        # Aggiungi la modalità al suggerimento
        suggerimento['modalita_reale'] = modalita_reale

        # FIX DIFENSIVO: Assicura che 'dettagli_analisi' esista sempre prima di inviare al frontend.
        if 'dettagli_analisi' not in suggerimento:
            suggerimento['dettagli_analisi'] = {}
        
        return suggerimento
    except Exception as e:
        logging.error(f"Errore durante l'analisi IA per {nome_piattaforma}/{coppia}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore durante l'analisi IA: {str(e)}")



@app.get("/ottimizzazione_portafoglio", tags=["Intelligenza Artificiale"])
async def get_ottimizzazione_portafoglio():
    """
    Esegue una simulazione di ottimizzazione del portafoglio e restituisce suggerimenti.
    """
    try:
        suggerimenti = ottimizza_portafoglio_simulato()
        logging.debug(f"Suggerimenti ottimizzazione portafoglio: {suggerimenti}")
        return suggerimenti
    except Exception as e:
        logging.error(f"Errore durante l'ottimizzazione del portafoglio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno durante l'ottimizzazione del portafoglio: {str(e)}")


@app.post("/simula_operazione_ia/{nome_piattaforma}/{coppia:path}", tags=["Simulazione"])
async def simula_operazione_ia(nome_piattaforma: str, coppia: str):
    """
    Ottiene un segnale dall'IA e simula l'operazione corrispondente sul portafoglio virtuale.
    """
    piattaforma_ccxt = None # Initialize to None
    try:
        # Inizializza la piattaforma
        piattaforma_ccxt = get_platform_instance(nome_piattaforma.lower())
        await piattaforma_ccxt.load_markets() # Carica i mercati

        suggerimento = await analizza_mercato_e_genera_segnale(piattaforma_ccxt, coppia.upper())
        segnale = suggerimento.get("segnale")
        prezzo = suggerimento.get("ultimo_prezzo")

        if segnale == "COMPRA":
            # Logica di esempio: compra per un valore di 100 USD
            quantita = 100 / prezzo
            await gestore_globale_portafoglio.esegui_acquisto(nome_piattaforma.lower(), coppia.upper(), quantita, prezzo)
            messaggio = f"Eseguito acquisto virtuale di {quantita:.6f} {coppia.split('/')[0]}."
        elif segnale == "VENDI":
            # Logica di esempio: vendi il 10% di quello che possiedi
            simbolo_base = coppia.upper().split('/')[0]
            quantita_posseduta = gestore_globale_portafoglio.portafoglio.asset.get(simbolo_base, 0)
            if quantita_posseduta > 0:
                quantita = quantita_posseduta * 0.10
                await gestore_globale_portafoglio.esegui_vendita(nome_piattaforma.lower(), coppia.upper(), quantita, prezzo)
                messaggio = f"Eseguita vendita virtuale di {quantita:.6f} {simbolo_base}."
            else:
                messaggio = "Segnale di vendita ricevuto, ma non si possiede l'asset."
        else: # MANTIENI o altro
            messaggio = "Il segnale dell'IA è di mantenere la posizione. Nessuna operazione eseguita."

        return {
            "messaggio": messaggio,
            "suggerimento_ia": suggerimento,
            "stato_portafoglio_aggiornato": gestore_globale_portafoglio.ottieni_stato_portafoglio()
        }
    except Exception as e:
        logging.error(f"Errore durante la simulazione per {nome_piattaforma}/{coppia}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore durante la simulazione: {str(e)}")


@app.get("/stato_portafoglio", tags=["Simulazione"])
async def ottieni_stato_portafoglio():
    """
    Restituisce lo stato attuale del portafoglio virtuale.
    """
    return gestore_globale_portafoglio.ottieni_stato_portafoglio()

# --- Logica di Caching per la Dashboard ---

async def calcola_e_aggiorna_cache_dashboard():
    """
    Esegue il calcolo intensivo per i dati della dashboard e aggiorna la cache.
    Questa è la logica estratta dall'endpoint originale.
    """
    logging.info("Inizio calcolo e aggiornamento cache dashboard...")
    piattaforma_ccxt = None # Initialize here
    try:
        portafoglio_attuale = gestore_globale_portafoglio.ottieni_stato_portafoglio()
        asset_con_segnali = {}

        from .core.gestore_configurazione import carica_configurazione
        config = carica_configurazione()
        piattaforme_config = config['piattaforme']

        piattaforma_default = None
        quote_currency = "USDT"
        for nome, conf in piattaforme_config.items():
            if nome != '_comment' and conf.get('attiva'):
                piattaforma_default = nome
                quote_currency = conf.get('options', {}).get('quote_currency', 'USDT')
                break

        if not piattaforma_default:
            logging.warning("Nessuna piattaforma attiva trovata per calcolo cache dashboard.")
            return

        piattaforma_ccxt = get_platform_instance(piattaforma_default)
        try:
            await piattaforma_ccxt.load_markets() # Load markets once
        except ccxt.RequestTimeout as e:
            logging.warning(f"Timeout durante il caricamento dei mercati per {piattaforma_default} in cache dashboard: {e}. Il calcolo verrà riprovato al prossimo ciclo.")
            # Chiudi la connessione e esci per evitare ulteriori errori
            if piattaforma_ccxt:
                await piattaforma_ccxt.close()
            return

        assets_to_update_cache = [
            asset for asset in portafoglio_attuale.asset.keys()
            if asset.upper() not in ['USDT', 'BUSD', 'USDC', 'DAI', 'EUR']
        ]

        if assets_to_update_cache:
            try:
                await aggiorna_prezzi_cache(piattaforma_ccxt, assets_to_update_cache, quote_currency)
            except Exception as e:
                logging.warning(f"Errore aggiornamento cache prezzi per dashboard ({piattaforma_default}): {e}")

        tasks = []
        assets_da_analizzare = []
        for asset, quantita in portafoglio_attuale.asset.items():
            if asset.upper() in ['USDT', 'BUSD', 'USDC', 'DAI', 'EUR']:
                asset_con_segnali[asset] = {"quantita": quantita, "segnale": "STABLECOIN", "valore_in_controvaluta": quantita, "controvaluta": asset.upper()}
            elif asset in config['parametri_ia']['cripto_preferite']:
                coppia = f"{asset}/{quote_currency}"
                assets_da_analizzare.append(asset)
                tasks.append(analizza_mercato_e_genera_segnale(piattaforma_ccxt, coppia))

        if tasks:
            try:
                risultati_analisi = await asyncio.gather(*tasks, return_exceptions=True)
                for i, asset in enumerate(assets_da_analizzare):
                    risultato = risultati_analisi[i]
                    quantita = portafoglio_attuale.asset[asset]
                    prezzo_asset = get_prezzo_cache(asset, quote_currency)
                    valore_calcolato = quantita * prezzo_asset if prezzo_asset else 0.0
                    
                    dettagli_analisi = {} # Initialize
                    if isinstance(risultato, Exception):
                        logging.warning(f"Errore nel recupero segnale AI per {asset} in cache dashboard: {type(risultato).__name__}: {risultato}")
                        segnale = "ERRORE"
                        # If it's an exception, we can't call .get() on it.
                        # We should provide a default or skip further processing for this result.
                        # For now, we'll just set segnale to "ERRORE" and continue.
                    else:
                        segnale = risultato.get("segnale", "MANTIENI")
                        dettagli_analisi = risultato.get("dettagli_analisi", {}) # Get details if not an exception
                    
                    asset_con_segnali[asset] = {
                        "quantita": quantita,
                        "segnale": segnale,
                        "valore_in_controvaluta": valore_calcolato,
                        "controvaluta": quote_currency,
                        "dettagli_analisi": dettagli_analisi # Add details here
                    }

            except Exception as e:
                logging.error(f"Errore durante l'esecuzione parallela delle analisi AI per cache dashboard: {e}")

        for asset, quantita in portafoglio_attuale.asset.items():
            if asset not in asset_con_segnali:
                prezzo_asset = get_prezzo_cache(asset, quote_currency)
                segnale = "PREZZO N/D" if prezzo_asset is None else "NON MONITORATO"
                valore_calcolato = quantita * prezzo_asset if prezzo_asset else 0.0
                asset_con_segnali[asset] = {"quantita": quantita, "segnale": segnale, "valore_in_controvaluta": valore_calcolato, "controvaluta": quote_currency}

        portafoglio_con_segnali_dict = {
            **portafoglio_attuale.dict(),
            "asset_con_segnali": asset_con_segnali
        }
        
        set_dashboard_cache(portafoglio_con_segnali_dict)
        logging.info("Cache dashboard aggiornata con successo.")

    except Exception as e:
        logging.error(f"Errore grave durante il calcolo della cache dashboard: {e}", exc_info=True)



async def dashboard_update_loop():
    """
    Ciclo principale che aggiorna periodicamente la cache della dashboard.
    """
    while True:
        try:
            from .core.gestore_configurazione import carica_configurazione
            config = carica_configurazione()
            intervallo = config.get('impostazioni_generali', {}).get('intervallo_aggiornamento_dashboard_secondi', 120)
            
            await calcola_e_aggiorna_cache_dashboard()
            
            logging.info(f"Dashboard cache loop: in attesa per {intervallo} secondi.")
            await asyncio.sleep(intervallo)
        except Exception as e:
            logging.error(f"Errore nel loop di aggiornamento della cache dashboard: {e}", exc_info=True)
            # Aspetta un po' prima di riprovare in caso di errore grave
            await asyncio.sleep(60)


@app.get("/stato_portafoglio_con_segnali", tags=["Simulazione"])
async def ottieni_stato_portafoglio_con_segnali():
    """
    Restituisce lo stato del portafoglio dalla cache.
    I dati vengono aggiornati in background.
    """
    cached_data = get_dashboard_cache()
    if cached_data.get("data") is None:
        # Se la cache è vuota (es. all'avvio), possiamo restituire un placeholder
        # o avviare un calcolo immediato la prima volta.
        # Per ora, restituiamo un messaggio che invita ad attendere.
        logging.info("Richiesta a /stato_portafoglio_con_segnali, ma la cache è ancora vuota.")
        raise HTTPException(
            status_code=202, # Accepted
            detail="Dati della dashboard in fase di calcolo. Riprova tra un momento."
        )
    
    # Aggiungiamo il timestamp dell'ultimo aggiornamento per trasparenza
    response_data = {**cached_data["data"], "last_updated_timestamp": cached_data["last_updated"]}
    logging.debug(f"Dati inviati per /stato_portafoglio_con_segnali: {response_data}")
    return response_data

@app.get("/storico_valore_portafoglio", tags=["Simulazione"])
async def ottieni_storico_valore_portafoglio():
    """
    Restituisce lo storico del valore del portafoglio nel tempo.
    """
    return gestore_globale_portafoglio.ottieni_storico_valore_portafoglio()

@app.get("/performance_report", tags=["Simulazione"])
async def ottieni_performance_report():
    """
    Restituisce il report delle performance del portafoglio.
    """
    return gestore_globale_portafoglio.calcola_report_performance()

@app.get("/analisi_operazioni", tags=["Simulazione"])
async def ottieni_analisi_operazioni():
    """
    Restituisce i dati aggregati delle operazioni per grafici.
    """
    return gestore_globale_portafoglio.get_analisi_operazioni()

@app.get("/posizioni_aperte", tags=["Simulazione"])
async def ottieni_posizioni_aperte():
    """
    Restituisce le posizioni di trading attualmente aperte.
    """
    return gestore_globale_portafoglio.portafoglio.posizioni_aperte

@app.get("/storico_operazioni_reali", tags=["Simulazione"])
async def ottieni_storico_operazioni_reali():
    """
    Restituisce lo storico delle operazioni reali recuperandole dal database.
    """
    try:
        # Recupera tutte le operazioni dal DB e poi filtra in memoria
        operazioni_dal_db = recupera_operazioni_db(limit=500) # Aumenta il limite se necessario
        logging.debug(f"Operazioni recuperate dal DB (prima del filtro): {operazioni_dal_db}")
        operazioni_reali = [op for op in operazioni_dal_db if "_reale" in op['tipo']]
        return operazioni_reali
    except Exception as e:
        logging.error(f"Errore durante il recupero dello storico operazioni reali dal DB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore nel recupero dello storico operazioni.")
        
@app.get("/storico_take_profit", tags=["Simulazione"])
async def ottieni_storico_take_profit():
    """
    Restituisce lo storico delle operazioni chiuse per Take Profit.
    """
    try:
        operazioni_dal_db = recupera_operazioni_db(limit=1000)
        operazioni_tp = [op for op in operazioni_dal_db if op.get('motivo_vendita') == 'TAKE_PROFIT']
        return operazioni_tp
    except Exception as e:
        logging.error(f"Errore durante il recupero dello storico take profit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore nel recupero dello storico take profit.")

@app.get("/analisi_profitto_storico", tags=["Simulazione"])
async def ottieni_analisi_profitto_storico():
    """
    Restituisce le percentuali di profitto/perdita (minima, media, massima) dalle operazioni di vendita.
    """
    try:
        operazioni_dal_db = recupera_operazioni_db(limit=10000) # Recupera un numero sufficiente di operazioni
        percentuali = []
        for op in operazioni_dal_db:
            # Assicurati che op sia un dizionario e che contenga le chiavi necessarie
            if isinstance(op, dict) and op.get('tipo', '').startswith('vendita'):
                profitto = op.get('profitto_perdita_operazione', 0)
                controvalore = op.get('controvalore_usd', 0)
                costo_operazione = controvalore - profitto
                if costo_operazione > 0:
                    percentuale = (profitto / costo_operazione) * 100
                    percentuali.append(percentuale)

        if not percentuali:
            return {"min": 0.0, "avg": 0.0, "max": 0.0}

        return {
            "min": min(percentuali),
            "avg": sum(percentuali) / len(percentuali),
            "max": max(percentuali)
        }
    except Exception as e:
        logging.error(f"Errore durante il recupero dell'analisi profitto storico: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore nel recupero dell'analisi profitto storico.")

@app.get("/analisi_profitto_storico", tags=["Simulazione"])
async def ottieni_analisi_profitto_storico():
    """
    Restituisce le percentuali di profitto/perdita (minima, media, massima) dalle operazioni di vendita.
    """
    try:
        operazioni_dal_db = recupera_operazioni_db(limit=10000) # Recupera un numero sufficiente di operazioni
        percentuali = []
        for op in operazioni_dal_db:
            if op.get('tipo', '').startswith('vendita') and op.get( 'percentuale_profitto_perdita') is not None:
                percentuali.append(op['percentuale_profitto_perdita'])

        if not percentuali:
            return {"min": 0.0, "avg": 0.0, "max": 0.0}

        return {
            "min": min(percentuali),
            "avg": sum(percentuali) / len(percentuali),
            "max": max(percentuali)
        }
    except Exception as e:
        logging.error(f"Errore durante il recupero dell'analisi profitto storico: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore nel recupero dell'analisi profitto storico.")

@app.get("/ohlcv/{nome_piattaforma}/{coppia:path}/{timeframe}", tags=["Dati di Mercato"])
async def get_ohlcv_data(nome_piattaforma: str, coppia: str, timeframe: str, limit: int = 100):
    """
    Recupera i dati OHLCV (Open, High, Low, Close, Volume) dal database locale.
    Se i dati non sono presenti, avvia un aggiornamento in background.
    """
    try:
        logging.info(f"Richiesta OHLCV per {coppia} ({timeframe}). Inizio ricerca nel DB.")
        start_time = time.time()

        # Recupera i dati dal database
        ohlcv_from_db = recupera_dati_ohlcv_da_db(
            exchange=nome_piattaforma.lower(),
            symbol=coppia.upper(),
            timeframe=timeframe,
            limit=limit
        )
        
        db_time = time.time() - start_time
        logging.info(f"Query DB completata in {db_time:.4f} secondi. Trovate {len(ohlcv_from_db)} righe.")

        # Formatta i dati per essere consumabili dal frontend
        formatted_ohlcv = []
        if ohlcv_from_db:
            for row in ohlcv_from_db:
                formatted_ohlcv.append({
                    "time": row["timestamp"], # Il timestamp è già in secondi
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                })
        
        # Se non ci sono dati nel DB, la UI mostrerà un messaggio vuoto.
        # Il processo in background popolerà i dati al prossimo ciclo.
        if not formatted_ohlcv:
            logging.warning(f"Nessun dato OHLCV trovato nel DB per {coppia} ({timeframe}). I dati verranno popolati dal processo in background.")

        total_time = time.time() - start_time
        logging.info(f"Risposta OHLCV per {coppia} ({timeframe}) inviata in {total_time:.4f} secondi.")
        return formatted_ohlcv
    except Exception as e:
        logging.error(f"Errore nel recupero dati OHLCV dal DB per {coppia} su {nome_piattaforma}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Errore nel recupero dati OHLCV dal database: {str(e)}"}
        )
 
from .core.gestore_configurazione import carica_configurazione

@app.get("/config", tags=["Configurazione"])
async def get_config():
    """
    Restituisce il contenuto del file config.json.
    """
    try:
        config_data = carica_configurazione()
        return config_data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File di configurazione non trovato.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore sconosciuto durante il recupero della configurazione: {str(e)}")

@app.post("/config", tags=["Configurazione"])
async def save_config(config_data: ConfigModel):
    """
    Salva il contenuto del file config.json.
    """
    # Importa CONFIG_PATH dal gestore centralizzato
    from .core.path_manager import CONFIG_PATH
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data.dict(), f, indent=2)
        return {"messaggio": "Configurazione salvata con successo!"}
    except ValidationError as e:
        print(f"Pydantic Validation Error: {e.errors()}") # Log the validation errors
        raise HTTPException(status_code=422, detail=e.errors()) # Return 422 Unprocessable Entity with details
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante il salvataggio della configurazione: {str(e)}")


# --- Endpoints per la Gestione della Blacklist ---

@app.get("/blacklist", tags=["Blacklist"])
async def get_blacklist_endpoint():
    """
    Restituisce un elenco di tutte le coppie attualmente in blacklist.
    """
    try:
        blacklist_details = get_blacklist_details()
        return blacklist_details
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nel recupero della blacklist: {str(e)}")

@app.delete("/blacklist/{coppia:path}", tags=["Blacklist"])
async def remove_from_blacklist_endpoint(coppia: str = Path(..., title="La coppia da rimuovere", description="Es. BTC/USDT")):
    """
    Rimuove una coppia specificata dalla blacklist.
    """
    try:
        # La coppia arriva URL-encoded, es. BTC%2FUSDT. FastAPI la decodifica automaticamente.
        success = remove_from_blacklist(coppia)
        if success:
            return {"messaggio": f"Coppia {coppia} rimossa con successo dalla blacklist."}
        else:
            raise HTTPException(status_code=404, detail=f"Coppia {coppia} non trovata nella blacklist.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante la rimozione dalla blacklist: {str(e)}")

@app.get("/eventi", tags=["Eventi"])
async def get_eventi_endpoint(limit: int = 100):
    """
    Restituisce una lista degli ultimi eventi di sistema registrati.
    """
    try:
        eventi = recupera_eventi_db(limit=limit)
        return eventi
    except Exception as e:
        logging.error(f"Errore durante il recupero degli eventi dal DB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore nel recupero degli eventi.")

@app.get("/notifiche", tags=["Notifiche"])
async def get_notifiche_endpoint(solo_non_lette: bool = False, limit: int = 20):
    """
    Restituisce una lista delle ultime notifiche.
    """
    try:
        notifiche = recupera_notifiche(solo_non_lette=solo_non_lette, limit=limit)
        return notifiche
    except Exception as e:
        logging.error(f"Errore durante il recupero delle notifiche: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore nel recupero delle notifiche.")

@app.post("/notifiche/segna_come_lette", tags=["Notifiche"])
async def segna_notifiche_lette_endpoint():
    """
    Segna tutte le notifiche come lette.
    """
    try:
        segna_notifiche_come_lette()
        return {"messaggio": "Notifiche segnate come lette."}
    except Exception as e:
        logging.error(f"Errore durante l'aggiornamento delle notifiche: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Errore durante l'aggiornamento delle notifiche.")


# --- Logica del Bot AI Automatico ---

async def ai_trading_loop():
    """
    Ciclo principale del bot AI che esegue operazioni automatiche.
    Implementa una logica di blacklist per escludere coppie non permesse.
    """
    global ai_trading_active
    from .core.gestore_configurazione import carica_configurazione

    while ai_trading_active:
        try:
            config = carica_configurazione()
            intervallo = config['impostazioni_generali']['intervallo_aggiornamento_secondi']
            piattaforme_config = config['piattaforme']
            blacklist = get_blacklisted_pairs_set()  # Carica la blacklist all'inizio di ogni ciclo principale
            logging.info(f"Blacklist caricata con {len(blacklist)} coppie.")

            for nome_piattaforma, conf_piattaforma in piattaforme_config.items():
                if not conf_piattaforma.get('attiva') or nome_piattaforma == '_comment':
                    continue

                piattaforma_ccxt = None
                try:
                    piattaforma_ccxt = get_platform_instance(nome_piattaforma)
                    if not piattaforma_ccxt.markets:
                        await piattaforma_ccxt.load_markets()
                except Exception as e:
                    logging.warning(f"Impossibile inizializzare la piattaforma {nome_piattaforma}: {e}")
                    continue

                # --- Logica di selezione e filtro asset ---
                quote_currency = conf_piattaforma.get('options', {}).get('quote_currency', 'USDT')
                selezione_dinamica_config = config.get('selezione_asset_dinamica', {})

                # 1. Inizia con gli asset già posseduti (escluse stablecoin)
                asset_posseduti = {asset for asset in gestore_globale_portafoglio.portafoglio.asset.keys() if asset.upper() not in ['USDT', 'USDC', 'BUSD', 'DAI', 'EUR']}
                assets_da_analizzare = set(asset_posseduti)

                # 2. Aggiungi asset dalla selezione dinamica (se attiva)
                if selezione_dinamica_config.get('attiva'):
                    try:
                        suggerimenti_mercato = await suggerisci_strategie_di_mercato(nome_piattaforma, output_n=selezione_dinamica_config.get('numero_asset_da_considerare', 5))
                        assets_suggeriti = {s['simbolo'].split('/')[0] for s in suggerimenti_mercato}
                        assets_da_analizzare.update(assets_suggeriti)
                        logging.info(f"Selezione dinamica: Aggiunti {len(assets_suggeriti)} asset suggeriti.")

                        # 3. Aggiungi i preferiti solo se la modalità ibrida è attiva
                        if not selezione_dinamica_config.get('ignora_preferiti_con_dinamica', False):
                            assets_da_analizzare.update(config['parametri_ia']['cripto_preferite'])
                            logging.info("Modalità ibrida: Aggiunti asset preferiti alla lista di analisi.")

                    except Exception as e:
                        logging.error(f"AI: Errore durante la selezione dinamica: {e}. Eseguo fallback sulla lista statica.")
                        assets_da_analizzare.update(config['parametri_ia']['cripto_preferite'])
                else:
                    # 4. Se la selezione dinamica è disattivata, aggiungi solo i preferiti
                    assets_da_analizzare.update(config['parametri_ia']['cripto_preferite'])
                    logging.info("Selezione dinamica disattivata. Uso solo asset preferiti e posseduti.")
                
                # 5. Filtra l'intera lista finale per la blacklist
                assets_finali = sorted([asset for asset in assets_da_analizzare if f"{asset}/{quote_currency}" not in blacklist])
                logging.info(f"AI: Analisi su {len(assets_finali)} asset unificati e filtrati: {assets_finali}")
                
                if not assets_finali:
                    #if piattaforma_ccxt: await piattaforma_ccxt.close()
                    continue

                await aggiorna_prezzi_cache(piattaforma_ccxt, assets_finali, quote_currency)

                for asset in assets_finali:
                    coppia = f"{asset}/{quote_currency}"
                    try:
                        # --- LOGICA TAKE PROFIT INTERNO ---
                        posizione_aperta = gestore_globale_portafoglio.portafoglio.posizioni_aperte.get(asset)
                        prezzo_attuale = get_prezzo_cache(asset, quote_currency)
                        segnale_forzato = None

                        if posizione_aperta and posizione_aperta.take_profit_price and prezzo_attuale:
                            logging.info(f"AI: Monitorando {coppia}. Prezzo attuale: {prezzo_attuale:.4f}, Take Profit: {posizione_aperta.take_profit_price:.4f}")
                            if prezzo_attuale >= posizione_aperta.take_profit_price:
                                logging.info(f"AI: Obiettivo Take Profit raggiunto per {coppia} a {prezzo_attuale:.4f}. Forzo la VENDITA.")
                                segnale_forzato = "VENDI"
                        # --- FINE LOGICA TAKE PROFIT ---

                        if segnale_forzato:
                            suggerimento = {"segnale": segnale_forzato, "ultimo_prezzo": prezzo_attuale}
                        else:
                            logging.info(f"AI: Analizzando {coppia} su {nome_piattaforma}...")
                            suggerimento = await analizza_mercato_e_genera_segnale(piattaforma_ccxt, coppia)
                        
                        segnale = suggerimento.get("segnale")
                        prezzo = suggerimento.get("ultimo_prezzo")

                        if segnale == "COMPRA" and prezzo:
                            # --- CONTROLLO LISTA DI ATTESA ---
                            cooldown_config = config.get('parametri_ia', {})
                            if cooldown_config.get('attiva_cooldown_dopo_vendita', True):
                                orario_reset_str = cooldown_config.get('orario_reset_cooldown', "06:00")
                                ora_reset, minuto_reset = map(int, orario_reset_str.split(':'))
                                now = datetime.now()
                                
                                asset_in_cooldown = False
                                for i in range(len(asset_venduti_di_recente) - 1, -1, -1):
                                    coppia_venduta, timestamp_vendita = asset_venduti_di_recente[i]
                                    data_vendita = datetime.fromtimestamp(timestamp_vendita)
                                    
                                    reset_time_oggi = now.replace(hour=ora_reset, minute=minuto_reset, second=0, microsecond=0)
                                    if now >= reset_time_oggi:
                                        prossimo_reset = reset_time_oggi + timedelta(days=1)
                                    else:
                                        prossimo_reset = reset_time_oggi

                                    ultimo_reset_passato = prossimo_reset - timedelta(days=1)
                                    if data_vendita < ultimo_reset_passato:
                                        asset_venduti_di_recente.pop(i)
                                        continue

                                    if coppia_venduta == coppia:
                                        asset_in_cooldown = True
                                        break

                                if asset_in_cooldown:
                                    logging.info(f"AI: Segnale COMPRA per {coppia} ignorato perché è in cooldown fino alle {orario_reset_str} di domani.")
                                    continue
                            # --- FINE CONTROLLO ---

                            # --- CONTROLLO SELEZIONE ASSET ---
                            if not selezione_dinamica_config.get('attiva') and asset not in config['parametri_ia']['cripto_preferite']:
                                logging.info(f"AI: Segnale COMPRA per {asset} ignorato perché la selezione dinamica è disattivata e l'asset non è nelle preferite.")
                                continue
                            # --- FINE CONTROLLO ---
                            
                            # --- Logica di Gestione Rischio e Calcolo Dimensione Operazione ---
                            impostazioni_generali = config['impostazioni_generali']
                            percentuale_rischio = impostazioni_generali['percentuale_rischio_per_operazione']
                            min_buy_notional = impostazioni_generali['min_buy_notional_usd']

                            # Calcola il valore totale del portafoglio (liquidi + asset)
                            valore_liquidi = gestore_globale_portafoglio.portafoglio.budget_usd_corrente
                            valore_asset = 0
                            for asset_name, quantita in gestore_globale_portafoglio.portafoglio.asset.items():
                                if quantita > 0:
                                    asset_price = get_prezzo_cache(asset_name, quote_currency)
                                    if asset_price:
                                        valore_asset += quantita * asset_price
                            valore_totale_portafoglio = valore_liquidi + valore_asset

                            # Calcola la dimensione dell'operazione basata sul rischio
                            notional_da_rischiare = valore_totale_portafoglio * (percentuale_rischio / 100)

                            # Assicura che la dimensione non sia inferiore al minimo richiesto
                            final_notional = max(notional_da_rischiare, min_buy_notional)

                            # Verifica se c'è abbastanza budget per l'operazione
                            if valore_liquidi < final_notional:
                                logging.warning(f"AI: Budget insufficiente ({valore_liquidi:.2f} USD) per aprire una nuova operazione da {final_notional:.2f} USD. Salto.")
                                continue

                            quantita_da_comprare = final_notional / prezzo

                            # --- CONTROLLO E ADEGUAMENTO QUANTITÀ MINIMA ---
                            market_info = piattaforma_ccxt.markets.get(coppia)
                            min_amount = market_info.get('limits', {}).get('amount', {}).get('min')

                            if min_amount and quantita_da_comprare < min_amount:
                                logging.warning(f"AI: Quantità calcolata ({quantita_da_comprare:.8f}) per {coppia} è inferiore al minimo di {min_amount}. Adeguo al minimo.")
                                quantita_da_comprare = min_amount
                                # Ricalcola il nozionale finale con la nuova quantità
                                final_notional = quantita_da_comprare * prezzo

                            # Verifica di nuovo il budget dopo l'adeguamento
                            if valore_liquidi < final_notional:
                                logging.warning(f"AI: Budget insufficiente ({valore_liquidi:.2f} USD) per l'acquisto della quantità minima di {final_notional:.2f} USD. Salto.")
                                continue
                            # --- FINE CONTROLLO QUANTITÀ MINIMA ---

                            logging.info(f"AI: Calcolata dimensione operazione: {final_notional:.2f} USD ({quantita_da_comprare:.6f} {asset}) basata su rischio del {percentuale_rischio}% su un portafoglio di {valore_totale_portafoglio:.2f} USD.")
                            # --- Fine Logica di Gestione Rischio ---

                            
                            logging.info(f"AI: Eseguendo acquisto di {quantita_da_comprare:.6f} {asset}...")
                            nuova_operazione = await gestore_globale_portafoglio.esegui_acquisto(
                                nome_piattaforma, coppia, quantita_da_comprare, prezzo,
                                stop_loss_price=suggerimento.get('stop_loss_price')
                            )
                            if nuova_operazione:
                                pos = gestore_globale_portafoglio.portafoglio.posizioni_aperte.get(asset)
                                if pos and pos.take_profit_price:
                                    logging.info(f"AI: Asset {coppia} acquistato. Take Profit calcolato: {pos.take_profit_price:.4f}")

                        elif segnale == "VENDI" and prezzo:
                            quantita_posseduta = gestore_globale_portafoglio.portafoglio.asset.get(asset, 0)
                            if quantita_posseduta > 0:
                                # --- CONTROLLO E ADEGUAMENTO QUANTITÀ MINIMA E PRECISIONE PER LA VENDITA ---
                                market_info = piattaforma_ccxt.markets.get(coppia)
                                min_amount = market_info.get('limits', {}).get('amount',{}).get('min')
                                amount_precision = market_info.get('limits', {}).get('amount',{}).get('precision')
                                quantita_da_vendere = quantita_posseduta

                                if amount_precision is not None:
                                    # Arrotonda la quantità alla precisione corretta
                                    from ccxt import TRUNCATE # Importa TRUNCATE qui
                                    quantita_da_vendere = piattaforma_ccxt.decimal_to_precision(quantita_da_vendere, TRUNCATE, amount_precision)
                                    quantita_da_vendere = float(quantita_da_vendere)

                                if min_amount and quantita_da_vendere < min_amount:
                                    logging.warning(f"AI: Quantità da vendere ({quantita_da_vendere:.8f}) per {coppia} è inferiore al minimo di {min_amount}. Salto la vendita.")
                                    continue
                                # --- FINE CONTROLLO QUANTITÀ MINIMA E PRECISIONE ---
                                motivo_vendita = 'TAKE_PROFIT' if segnale_forzato else 'SEGNALE_IA'
                                logging.info(f"AI: Eseguendo vendita ({motivo_vendita}) di {quantita_da_vendere:.6f} {asset}...")
                                await gestore_globale_portafoglio.esegui_vendita(nome_piattaforma, coppia, quantita_da_vendere, prezzo, motivo=motivo_vendita)
                                asset_venduti_di_recente.append((coppia, time.time()))
                                # --- NUOVA LOGICA: Annulla ordini esistenti prima di vendere ---
                                try:
                                    ordini_aperti = await piattaforma_ccxt.fetch_open_orders(coppia)
                                    if ordini_aperti:
                                        logging.info(f"AI: Trovati {len(ordini_aperti)} ordini aperti per {coppia}. Annullamento in corso prima della vendita...")
                                        for ordine in ordini_aperti:
                                            await piattaforma_ccxt.cancel_order(ordine['id'], coppia)
                                            logging.info(f"AI: Annullato ordine precedente {ordine['id']} per {coppia}.")
                                            # Registra l'evento nel DB
                                            dettagli_evento = f"Annullato ordine {ordine['type']} ID: {ordine['id']} per segnale di VENDITA."
                                            salva_evento_db("ANNULLA_ORDINE", piattaforma=nome_piattaforma, coppia=coppia, dettagli=dettagli_evento)
                                        # Attendi un istante per dare tempo all'exchange di processare la cancellazione
                                        await asyncio.sleep(1) 
                                except Exception as cancel_e:
                                    logging.error(f"AI: Errore durante l'annullamento degli ordini per {coppia}: {cancel_e}. La vendita potrebbe fallire.")
                                # --- FINE NUOVA LOGICA ---

                                impostazioni_generali = config['impostazioni_generali']
                                min_sell_notional = impostazioni_generali.get('min_sell_notional_usd', 0) # Usa .get per sicurezza
                                valore_vendita = quantita_posseduta * prezzo

                                if valore_vendita < min_sell_notional:
                                    logging.info(f"AI: Vendita di {asset} saltata. Il valore ({valore_vendita:.2f} USD) è inferiore alla soglia minima di vendita ({min_sell_notional:.2f} USD).")
                                    continue

                                # ... (logica vendita profittevole)
                                quantita_da_vendere = quantita_posseduta
                                logging.info(f"AI: Eseguendo vendita di {quantita_da_vendere:.6f} {asset} (valore: {valore_vendita:.2f} USD)...")
                                await gestore_globale_portafoglio.esegui_vendita(nome_piattaforma, coppia, quantita_da_vendere, prezzo)
                                # Aggiungi l'asset alla lista di attesa
                                asset_venduti_di_recente.append((coppia, time.time()))
                        else: # Segnale MANTIENI
                            dettagli_evento = f"Segnale MANTIENI per {coppia}. Prezzo: {prezzo:.4f}"
                            salva_evento_db("SEGNALE_MANTIENI", piattaforma=nome_piattaforma, coppia=coppia, dettagli=dettagli_evento)

                    except ccxt.InsufficientFunds as e:
                        logging.warning(f"AI: Fondi insufficienti per operazione su {coppia}.Dettagli: {e}")

                    except ccxt.InvalidOrder as e:
                        if 'precision' in str(e).lower() or 'amount' in str(e).lower():
                            logging.warning(f"AI: Ordine per {coppia} non valido a causa dei limiti dell'exchange. Dettagli: {e}")
                        else:
                            logging.error(f"AI: Ordine non valido per {coppia}: {e}")
                    except ccxt.InsufficientFunds as e:
                        logging.warning(f"AI: Fondi insufficienti per operazione su {coppia}.Dettagli: {e}")
                    except ValueError as e:
                        logging.error(f"AI: Errore di valore non previsto durante l'analisi di {coppia}: {e}")
     
                    except ccxt.ExchangeError as e:
                        error_str = str(e).lower()
                        if "-2010" in error_str or "not permitted" in error_str or "not supported" in error_str or "non è supportata" in error_str:
                            logging.warning(f"AI: La coppia {coppia} non è permessa su {nome_piattaforma}. AGGIUNGO ALLA BLACKLIST.")
                            add_to_blacklist(coppia, motivo=str(e))
                            blacklist.add(coppia) # Aggiorna la blacklist in memoria per il ciclo corrente
                        else:
                            logging.error(f"AI: Errore di scambio non gestito per {coppia}: {e}")
                        dettagli_evento = f"Errore durante l'analisi di {coppia}: {str(e)}"
                        salva_evento_db("ERRORE_ANALISI", piattaforma=nome_piattaforma, coppia=coppia, dettagli=dettagli_evento)

                #if piattaforma_ccxt: await piattaforma_ccxt.close()

            await asyncio.sleep(intervallo)

        except Exception as e:
            logging.error(f"Errore grave nel ciclo di trading AI: {e}", exc_info=True)
            await asyncio.sleep(60)

@app.get("/ai_status", tags=["Controllo AI"])
async def get_ai_status():
    """
    Restituisce lo stato attuale del bot AI (attivo/inattivo).
    """
    global ai_trading_active
    return {"status": "attivo" if ai_trading_active else "inattivo"}

@app.post("/ai_start", tags=["Controllo AI"])
async def start_ai_trading():
    """
    Avvia il bot AI per il trading automatico.
    """
    global ai_trading_active, ai_trading_task
    if not ai_trading_active:
        ai_trading_active = True
        ai_trading_task = asyncio.create_task(ai_trading_loop()) # Avvia il ciclo di trading come un task asyncio
        return {"messaggio": "Bot AI avviato con successo!", "status": "attivo"}
    return {"messaggio": "Bot AI già attivo.", "status": "attivo"}

@app.post("/ai_stop", tags=["Controllo AI"])
async def stop_ai_trading():
    """
    Ferma il bot AI per il trading automatico.
    """
    global ai_trading_active, ai_trading_task
    if ai_trading_active:
        ai_trading_active = False
        if ai_trading_task:
            ai_trading_task.cancel()
            try:
                await ai_trading_task # Attendi che il task termini la cancellazione
            except asyncio.CancelledError:
                pass # La cancellazione è prevista
        return {"messaggio": "Bot AI fermato con successo!", "status": "inattivo"}
    return {"messaggio": "Bot AI già inattivo.", "status": "inattivo"}

@app.post("/operazione_manuale/acquisto", tags=["Operazioni Manuali"])
async def acquisto_manuale(operazione: OperazioneManuale):
    """
    Esegue un acquisto manuale sul portafoglio virtuale.
    """
    try:
        await gestore_globale_portafoglio.esegui_acquisto(
            operazione.piattaforma.lower(),
            operazione.simbolo.upper(),
            operazione.quantita,
            operazione.prezzo,
            operazione.tipo_ordine # Passa il tipo di ordine
        )
        return {"messaggio": f"Acquisto manuale di {operazione.quantita} {operazione.simbolo} su {operazione.piattaforma} eseguito con successo.", 
                "stato_portafoglio_aggiornato": gestore_globale_portafoglio.ottieni_stato_portafoglio()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'acquisto manuale: {str(e)}")

@app.post("/operazione_manuale/vendita", tags=["Operazioni Manuali"])
async def vendita_manuale(operazione: OperazioneManuale):
    """
    Esegue una vendita manuale sul portafoglio virtuale.
    """
    try:
        await gestore_globale_portafoglio.esegui_vendita(
            operazione.piattaforma.lower(),
            operazione.simbolo.upper(),
            operazione.quantita,
            operazione.prezzo,
            operazione.tipo_ordine # Passa il tipo di ordine
        )
        return {"messaggio": f"Vendita manuale di {operazione.quantita} {operazione.simbolo} su {operazione.piattaforma} eseguita con successo.",
                "stato_portafoglio_aggiornato": gestore_globale_portafoglio.ottieni_stato_portafoglio()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante la vendita manuale: {str(e)}")

@app.get("/ordini_aperti/{nome_piattaforma}", tags=["Piattaforme"])
async def get_ordini_aperti(nome_piattaforma: str, simbolo: str = None):
    """
    Recupera e restituisce gli ordini aperti per una data piattaforma e simbolo.
    """
    try:
        ordini = await recupera_ordini_aperti(nome_piattaforma.lower(), simbolo.upper() if simbolo else None)
        return ordini
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante il recupero degli ordini aperti: {str(e)}")

@app.delete("/ordini_aperti/{nome_piattaforma}/{id_ordine}", tags=["Piattaforme"])
async def annulla_ordine(nome_piattaforma: str, id_ordine: str, simbolo: str = None):
    """
    Annulla un ordine specifico su una piattaforma.
    """
    piattaforma_ccxt = None
    try:
        piattaforma_ccxt = get_platform_instance(nome_piattaforma.lower())
        await piattaforma_ccxt.cancel_order(id_ordine, simbolo)
        dettagli_evento = f"Annullato manualmente ordine ID: {id_ordine}"
        salva_evento_db("ANNULLA_ORDINE_MANUALE", piattaforma=nome_piattaforma, coppia=simbolo, dettagli=dettagli_evento)
        return {"messaggio": f"Ordine {id_ordine} annullato con successo."}
    except ccxt.OrderNotFound:
        raise HTTPException(status_code=404, detail=f"Ordine {id_ordine} non trovato.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'annullamento dell'ordine: {str(e)}")


@app.get("/strategie_di_mercato", tags=["Intelligenza Artificiale"])
async def get_strategie_di_mercato():
    """
    Analizza il mercato e restituisce una lista di asset promettenti basati sul momentum.
    """
    from .core.gestore_configurazione import carica_configurazione
    try:
        # Trova la prima piattaforma attiva per l'analisi
        config = carica_configurazione()
        piattaforma_attiva = None
        for nome, conf in config.get('piattaforme', {}).items():
            if nome != '_comment' and conf.get('attiva'):
                piattaforma_attiva = nome
                break
        
        if not piattaforma_attiva:
            raise HTTPException(status_code=400, detail="Nessuna piattaforma attiva trovata nella configurazione.")

        suggerimenti = await suggerisci_strategie_di_mercato(piattaforma_attiva)
        return suggerimenti
    except Exception as e:
        logging.error(f"Errore durante la generazione delle strategie di mercato: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Errore interno durante la generazione delle strategie: {str(e)}")
