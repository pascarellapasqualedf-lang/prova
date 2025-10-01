# Autore: Pascarella Pasquale Gerardo
# Versione: Centralizzata in config.json

import json
import os
import asyncio
import logging
import time
import ccxt
from logging.handlers import TimedRotatingFileHandler
from typing import Optional # Aggiunto
from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

# Variabile globale per controllare lo stato del bot AI
ai_trading_active = False
ai_trading_task = None # Useremo un task asyncio invece di un thread

# Modelli Pydantic per la validazione della configurazione
class ImpostazioniGenerali(BaseModel):
    budget_totale_usd: float
    percentuale_rischio_per_operazione: float
    modalita_automatica_attiva: bool
    modalita_reale_attiva: bool
    intervallo_aggiornamento_secondi: int
    intervallo_aggiornamento_dashboard_secondi: Optional[int] = 120
    percentuale_prelievo_massimo: Optional[float] = None
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

class GestioneRischioDinamico(BaseModel):
    attiva: bool
    moltiplicatore_confidenza_media: float
    moltiplicatore_confidenza_alta: float

class SelezioneAssetDinamica(BaseModel):
    attiva: bool
    numero_asset_da_considerare: int

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

from .servizi.gestore_piattaforme import inizializza_piattaforma, recupera_ordini_aperti
from .core.cervello_ia import analizza_mercato_e_genera_segnale, ottimizza_portafoglio_simulato, suggerisci_strategie_di_mercato
from .core.gestore_operazioni import gestore_globale_portafoglio
from .core.prezzi_cache import aggiorna_prezzi_cache, get_prezzo_cache, get_prezzo_eur_cache
from .core.database import recupera_dati_ohlcv_da_db, create_tables, get_blacklisted_pairs_set, add_to_blacklist, get_blacklist_details, remove_from_blacklist
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
        
        # Registra il valore iniziale del portafoglio dopo l'avvio
        await gestore_globale_portafoglio._registra_valore_portafoglio()

    except Exception as e:
        logging.error(f"Errore durante l'evento di startup: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """
    Gestisce gli eventi di spegnimento dell'applicazione.
    Ferma il bot AI se è attivo e salva lo stato.
    """
    global ai_trading_active, ai_trading_task
    try:
        if ai_trading_active and ai_trading_task:
            print("Arresto del bot AI...")
            ai_trading_active = False
            ai_trading_task.cancel()
            try:
                await ai_trading_task # Attendi che il task termini la cancellazione
            except asyncio.CancelledError:
                print("Bot AI arrestato con successo.")
        # Salva lo stato del portafoglio alla chiusura
        gestore_globale_portafoglio.save_state()
    except Exception as e:
        logging.error(f"Errore durante l'evento di shutdown: {e}")

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

        piattaforma = inizializza_piattaforma(nome_piattaforma.lower())
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
    finally:
        if 'piattaforma' in locals() and piattaforma:
            await piattaforma.close()


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
        piattaforma_ccxt = inizializza_piattaforma(nome_piattaforma.lower())
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
    finally:
        if piattaforma_ccxt:
            await piattaforma_ccxt.close() # Chiudi la connessione


@app.get("/ottimizzazione_portafoglio", tags=["Intelligenza Artificiale"])
async def get_ottimizzazione_portafoglio():
    """
    Esegue una simulazione di ottimizzazione del portafoglio e restituisce suggerimenti.
    """
    try:
        suggerimenti = ottimizza_portafoglio_simulato()
        return suggerimenti
    except Exception as e:
        logging.error(f"Errore durante l'ottimizzazione del portafoglio: {e}")
        raise HTTPException(status_code=500, detail=f"Errore interno durante l'ottimizzazione del portafoglio: {str(e)}")


@app.post("/simula_operazione_ia/{nome_piattaforma}/{coppia:path}", tags=["Simulazione"])
async def simula_operazione_ia(nome_piattaforma: str, coppia: str):
    """
    Ottiene un segnale dall'IA e simula l'operazione corrispondente sul portafoglio virtuale.
    """
    piattaforma_ccxt = None # Initialize to None
    try:
        # Inizializza la piattaforma
        piattaforma_ccxt = inizializza_piattaforma(nome_piattaforma.lower())
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
    finally:
        if piattaforma_ccxt:
            await piattaforma_ccxt.close() # Chiudi la connessione

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

        piattaforma_ccxt = inizializza_piattaforma(piattaforma_default)
        await piattaforma_ccxt.load_markets() # Load markets once

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
    finally:
        if piattaforma_ccxt:
            await piattaforma_ccxt.close()


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
    Restituisce lo storico delle operazioni reali.
    """
    operazioni_reali = [op for op in gestore_globale_portafoglio.portafoglio.storico_operazioni if "_reale" in op.tipo]
    return operazioni_reali

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
                    piattaforma_ccxt = inizializza_piattaforma(nome_piattaforma)
                    if not piattaforma_ccxt.markets:
                        await piattaforma_ccxt.load_markets()
                except Exception as e:
                    logging.warning(f"Impossibile inizializzare la piattaforma {nome_piattaforma}: {e}")
                    continue

                # --- Logica di selezione e filtro asset ---
                quote_currency = conf_piattaforma.get('options', {}).get('quote_currency', 'USDT')
                assets_suggeriti_filtrati = []
                selezione_dinamica_config = config.get('selezione_asset_dinamica', {})
                
                if selezione_dinamica_config.get('attiva'):
                    try:
                        suggerimenti_mercato = await suggerisci_strategie_di_mercato(
                            nome_piattaforma,
                            output_n=selezione_dinamica_config.get('numero_asset_da_considerare', 5)
                        )
                        assets_da_analizzare_suggeriti = [s['simbolo'].split('/')[0] for s in suggerimenti_mercato]
                        
                        # Filtra i suggerimenti dinamici
                        assets_suggeriti_filtrati = [
                            asset for asset in assets_da_analizzare_suggeriti 
                            if f"{asset}/{quote_currency}" not in blacklist
                        ]
                        
                        # --- LOGICA DI FALLBACK ---
                        if not assets_suggeriti_filtrati:
                            logging.warning("AI: Nessun suggerimento dinamico valido dopo il filtro blacklist. Eseguo fallback sulla lista statica.")
                            static_fallback_assets = config['parametri_ia']['cripto_preferite']
                            assets_suggeriti_filtrati = [
                                asset for asset in static_fallback_assets
                                if f"{asset}/{quote_currency}" not in blacklist
                            ]
                        # --- FINE LOGICA DI FALLBACK ---

                    except Exception as e:
                        logging.error(f"AI: Errore durante la selezione dinamica: {e}. Eseguo fallback sulla lista statica.")
                        static_fallback_assets = config['parametri_ia']['cripto_preferite']
                        assets_suggeriti_filtrati = [
                            asset for asset in static_fallback_assets
                            if f"{asset}/{quote_currency}" not in blacklist
                        ]
                else:
                    # La selezione dinamica non è attiva, usa la lista statica e filtrala
                    static_assets = config['parametri_ia']['cripto_preferite']
                    assets_suggeriti_filtrati = [
                        asset for asset in static_assets
                        if f"{asset}/{quote_currency}" not in blacklist
                    ]

                # Unisci gli asset suggeriti (dinamici o di fallback) con quelli posseduti
                asset_posseduti = list(gestore_globale_portafoglio.portafoglio.asset.keys())
                asset_posseduti_filtrati = [
                    asset for asset in asset_posseduti
                    if asset.upper() not in ['USDT', 'USDC', 'BUSD', 'DAI', 'EUR'] and f"{asset}/{quote_currency}" not in blacklist
                ]
                
                assets_da_analizzare = sorted(list(set(assets_suggeriti_filtrati + asset_posseduti_filtrati)))
                logging.info(f"AI: Analisi su {len(assets_da_analizzare)} asset unificati e filtrati.")
                
                if not assets_da_analizzare:
                    if piattaforma_ccxt: await piattaforma_ccxt.close()
                    continue

                await aggiorna_prezzi_cache(piattaforma_ccxt, assets_da_analizzare, quote_currency)

                for asset in assets_da_analizzare:
                    coppia = f"{asset}/{quote_currency}"
                    try:
                        logging.info(f"AI: Analizzando {coppia} su {nome_piattaforma}...")
                        suggerimento = await analizza_mercato_e_genera_segnale(piattaforma_ccxt, coppia)
                        segnale = suggerimento.get("segnale")
                        prezzo = suggerimento.get("ultimo_prezzo")

                        if segnale == "COMPRA" and prezzo:
                            if selezione_dinamica_config.get('attiva') and asset not in assets_suggeriti_filtrati:
                                logging.info(f"AI: Segnale COMPRA per {asset} ignorato (non in lista suggerita).")
                                continue
                            
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
                            logging.info(f"AI: Calcolata dimensione operazione: {final_notional:.2f} USD ({quantita_da_comprare:.6f} {asset}) basata su rischio del {percentuale_rischio}% su un portafoglio di {valore_totale_portafoglio:.2f} USD.")
                            # --- Fine Logica di Gestione Rischio ---

                            
                            logging.info(f"AI: Eseguendo acquisto di {quantita_da_comprare:.6f} {asset}...")
                            await gestore_globale_portafoglio.esegui_acquisto(
                                nome_piattaforma, coppia, quantita_da_comprare, prezzo,
                                stop_loss_price=suggerimento.get('stop_loss_price')
                            )

                        elif segnale == "VENDI" and prezzo:
                            quantita_posseduta = gestore_globale_portafoglio.portafoglio.asset.get(asset, 0)
                            if quantita_posseduta > 0:
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

                    except ccxt.ExchangeError as e:
                        error_str = str(e).lower()
                        if "-2010" in error_str or "not permitted" in error_str or "not supported" in error_str or "non è supportata" in error_str:
                            logging.warning(f"AI: La coppia {coppia} non è permessa su {nome_piattaforma}. AGGIUNGO ALLA BLACKLIST.")
                            add_to_blacklist(coppia, motivo=str(e))
                            blacklist.add(coppia) # Aggiorna la blacklist in memoria per il ciclo corrente
                        else:
                            logging.error(f"AI: Errore di scambio non gestito per {coppia}: {e}")
                    except Exception as e:
                        logging.error(f"AI: Errore non previsto durante l'analisi di {coppia}: {e}", exc_info=True)

                if piattaforma_ccxt:
                    await piattaforma_ccxt.close()

            await gestore_globale_portafoglio._registra_valore_portafoglio()
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
