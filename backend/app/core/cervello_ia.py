# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import ccxt
import pandas as pd
import random
import asyncio
import logging
from ..servizi.gestore_piattaforme import inizializza_piattaforma
from .gestore_configurazione import carica_configurazione
from .prezzi_cache import get_prezzo_cache
from .database import get_blacklisted_pairs_set


# --- Funzioni di Analisi Tecnica ---

def calcola_sma(dati: pd.DataFrame, periodo: int = 20) -> pd.Series:
    """
    Calcola la Media Mobile Semplice (SMA).
    """
    return dati['close'].rolling(window=periodo).mean()

def calcola_rsi(dati: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """
    Calcola l'Indice di Forza Relativa (RSI).
    """
    delta = dati['close'].diff()
    guadagno = (delta.where(delta > 0, 0)).rolling(window=periodo).mean()
    perdita = (-delta.where(delta < 0, 0)).rolling(window=periodo).mean()
    
    rs = guadagno / perdita
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calcola_macd(dati: pd.DataFrame, periodo_veloce: int = 12, periodo_lento: int = 26, periodo_segnale: int = 9):
    """
    Calcola il Moving Average Convergence Divergence (MACD).
    """
    ema_veloce = dati['close'].ewm(span=periodo_veloce, adjust=False).mean()
    ema_lenta = dati['close'].ewm(span=periodo_lento, adjust=False).mean()
    macd_line = ema_veloce - ema_lenta
    signal_line = macd_line.ewm(span=periodo_segnale, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calcola_bollinger_bands(dati: pd.DataFrame, periodo: int = 20, deviazioni_std: int = 2):
    """
    Calcola le Bande di Bollinger.
    """
    sma = dati['close'].rolling(window=periodo).mean()
    std = dati['close'].rolling(window=periodo).std()
    upper_band = sma + (std * deviazioni_std)
    lower_band = sma - (std * deviazioni_std)
    return upper_band, sma, lower_band

def calcola_adx(dati: pd.DataFrame, periodo: int = 14):
    """
    Calcola l'Average Directional Index (ADX).
    """
    # True Range (TR)
    tr1 = dati['high'] - dati['low']
    tr2 = abs(dati['high'] - dati['close'].shift(1))
    tr3 = abs(dati['low'] - dati['close'].shift(1))
    tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)

    # Directional Movement (DM)
    plus_dm = dati['high'].diff()
    minus_dm = dati['low'].diff() * -1

    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # Correzione per quando il low corrente è maggiore del low precedente
    # e l'high corrente è minore dell'high precedente
    idx = (plus_dm > minus_dm)
    plus_dm[~idx] = 0
    minus_dm[idx] = 0

    # Average True Range (ATR)
    atr = tr.ewm(span=periodo, adjust=False).mean()

    # Smoothed Directional Movement
    plus_di = (plus_dm.ewm(span=periodo, adjust=False).mean() / atr) * 100
    minus_di = (minus_dm.ewm(span=periodo, adjust=False).mean() / atr) * 100

    # DX
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100

    # ADX
    adx = dx.ewm(span=periodo, adjust=False).mean()

    return adx, plus_di, minus_di

# --- Funzione di Simulazione Decisione RL ---
def simula_decisione_rl() -> dict:
    """
    Simula la decisione di un agente di Apprendimento per Rinforzo (RL).
    In un'implementazione reale, qui si caricherebbe un modello RL addestrato.
    """
    decisioni = ["RL_COMPRA", "RL_VENDI", "RL_MANTIENI"]
    decisione_scelta = random.choice(decisioni)

    motivazioni = {
        "RL_COMPRA": "L'agente RL suggerisce un acquisto basandosi sulla massimizzazione della ricompensa a lungo termine.",
        "RL_VENDI": "L'agente RL suggerisce una vendita basandosi sulla minimizzazione della perdita o massimizzazione del profitto.",
        "RL_MANTIENI": "L'agente RL suggerisce di mantenere la posizione, in attesa di condizioni migliori."
    }
    return {
        "decisione_rl": decisione_scelta,
        "motivazione_rl": motivazioni[decisione_scelta]
    }

# --- Funzione di Riconoscimento Pattern Grafici Semplificata ---
def riconosci_pattern_grafico(df: pd.DataFrame) -> dict:
    """
    Riconosce pattern grafici semplici basati sulle ultime candele.
    Questa è una simulazione/placeholder per un'analisi più complessa.
    """
    if len(df) < 2: # Necessita di almeno 2 candele per alcuni pattern
        return {"pattern": "NESSUN_PATTERN", "motivazione_pattern": "Dati insufficienti per il riconoscimento pattern."}

    ultima_candela = df.iloc[-1]
    penultima_candela = df.iloc[-2]

    # Doji: Open e Close sono molto vicini
    if abs(ultima_candela['open'] - ultima_candela['close']) < (ultima_candela['high'] - ultima_candela['low']) * 0.1:
        return {"pattern": "DOJI", "motivazione_pattern": "Pattern Doji: indica indecisione del mercato."}

    # Hammer / Hanging Man (corpo piccolo, ombra inferiore lunga)
    body_size = abs(ultima_candela['open'] - ultima_candela['close'])
    lower_wick = min(ultima_candela['open'], ultima_candela['close']) - ultima_candela['low']
    upper_wick = ultima_candela['high'] - max(ultima_candela['open'], ultima_candela['close'])

    if body_size < (ultima_candela['high'] - ultima_candela['low']) * 0.3 and lower_wick > 2 * body_size and upper_wick < body_size:
        if ultima_candela['close'] > ultima_candela['open']: # Bullish Hammer
            return {"pattern": "HAMMER_RIALZISTA", "motivazione_pattern": "Pattern Hammer Rialzista: potenziale inversione rialzista."}
        else: # Bearish Hanging Man
            return {"pattern": "HANGING_MAN_RIBASSISTA", "motivazione_pattern": "Pattern Hanging Man Ribassista: potenziale inversione ribassista."}

    # Bullish Engulfing: Corpo verde che ingloba completamente il corpo rosso precedente
    if (ultima_candela['close'] > ultima_candela['open'] and penultima_candela['close'] < penultima_candela['open'] and
        ultima_candela['close'] > penultima_candela['open'] and ultima_candela['open'] < penultima_candela['close']):
        return {"pattern": "ENGULFING_RIALZISTA", "motivazione_pattern": "Pattern Engulfing Rialzista: forte segnale di inversione rialzista."}

    # Bearish Engulfing: Corpo rosso che ingloba completamente il corpo verde precedente
    if (ultima_candela['close'] < ultima_candela['open'] and penultima_candela['close'] > penultima_candela['open'] and
        ultima_candela['close'] < penultima_candela['open'] and ultima_candela['open'] > penultima_candela['close']):
        return {"pattern": "ENGULFING_RIBASSISTA", "motivazione_pattern": "Pattern Engulfing Ribassista: forte segnale di inversione ribassista."}

    return {"pattern": "NESSUN_PATTERN", "motivazione_pattern": "Nessun pattern grafico riconoscibile."}

# --- Funzione di Previsione Serie Temporali Semplificata ---
def prevedi_movimento_futuro(df: pd.DataFrame) -> dict:
    """
    Prevede il movimento futuro del prezzo basandosi su una logica semplificata.
    Questa è una simulazione/placeholder per un modello ML più complesso (es. LSTM/ARIMA).
    """
    if len(df) < 5: # Necessita di almeno 5 candele per una tendenza minima
        return {"previsione": "INCERTO", "motivazione_previsione": "Dati insufficienti per la previsione."}

    # Calcola la media degli ultimi 3 prezzi di chiusura e la confronta con la media dei 3 precedenti
    ultimi_3_prezzi = df['close'].iloc[-3:].mean()
    precedenti_3_prezzi = df['close'].iloc[-6:-3].mean()

    if ultimi_3_prezzi > precedenti_3_prezzi * 1.005: # Aumento significativo (0.5%)
        return {"previsione": "UP", "motivazione_previsione": "Prezzo in aumento nelle ultime candele."}
    elif ultimi_3_prezzi < precedenti_3_prezzi * 0.995: # Diminuzione significativa (0.5%)
        return {"previsione": "DOWN", "motivazione_previsione": "Prezzo in diminuzione nelle ultime candele."}
    else:
        return {"previsione": "SIDEWAYS", "motivazione_previsione": "Prezzo relativamente stabile nelle ultime candele."}

# --- Funzione di Simulazione Sentiment ---
def simula_sentiment(coppia: str) -> dict:
    """
    Simula l'analisi del sentiment per una data coppia.
    In un'implementazione reale, qui si integrerebbe con API di notizie/social media.
    """
    sentiments = ["POSITIVO", "NEGATIVO", "NEUTRO"]
    sentiment_scelto = random.choice(sentiments)

    motivazioni = {
        "POSITIVO": "Notizie positive e aumento dell'interesse sui social media.",
        "NEGATIVO": "Notizie negative e calo del sentiment sui social media.",
        "NEUTRO": "Sentiment di mercato stabile, senza notizie rilevanti."
    }
    return {
        "sentiment": sentiment_scelto,
        "motivazione_sentiment": motivazioni[sentiment_scelto]
    }

# --- Logica Principale del Cervello AI ---

async def analizza_mercato_e_genera_segnale(piattaforma: ccxt.Exchange, coppia: str, timeframe: str = '1h'):
    """
    Funzione principale che orchestra l'analisi e genera un segnale di trading.
    Refactoring per supportare analisi multi-timeframe resilienti.
    """
    config = carica_configurazione()

    try:
        # La piattaforma dovrebbe già essere inizializzata e i mercati caricati dal chiamante.
        # Questo controllo è difensivo.
        if not piattaforma.markets:
            await piattaforma.load_markets()
        if coppia not in piattaforma.markets:
            raise ccxt.BadSymbol(f"La coppia '{coppia}' non è supportata da {piattaforma.id}.")

        mta_config = config.get('analisi_multi_timeframe', {})
        timeframes_da_analizzare = [timeframe] # Default a singolo timeframe
        pesi_config = [1.0]

        if mta_config.get('attiva'):
            if len(mta_config.get('timeframes', [])) == len(mta_config.get('pesi', [])):
                timeframes_da_analizzare = mta_config['timeframes']
                pesi_config = mta_config['pesi']
                logging.info(f"Analisi Multi-Timeframe attiva per {coppia} su {timeframes_da_analizzare} con pesi {pesi_config}")
            else:
                logging.warning("Configurazione Multi-Timeframe non valida (timeframes e pesi non corrispondono). Eseguo analisi su singolo timeframe.")

        tasks = [analizza_singolo_timeframe(piattaforma, coppia, tf) for tf in timeframes_da_analizzare]
        risultati_timeframe = await asyncio.gather(*tasks)

        # --- Logica di gestione fallimenti e riponderazione ---
        risultati_validi = []
        pesi_validi = []
        dettagli_analisi_combinati = {}

        for i, risultato in enumerate(risultati_timeframe):
            if risultato and risultato['punteggio_acquisto'] is not None:
                risultati_validi.append(risultato)
                pesi_validi.append(pesi_config[i])
                dettagli_analisi_combinati[timeframes_da_analizzare[i]] = risultato['dettagli_analisi']

        if not risultati_validi:
            return {"segnale": "ATTESA", "motivazione": "Nessun dato valido ricevuto dai timeframe analizzati.", "dati_reali": False}

        punteggio_acquisto_pesato = 0.0
        punteggio_vendita_pesato = 0.0
        somma_pesi_validi = sum(pesi_validi)

        for i, risultato in enumerate(risultati_validi):
            punteggio_acquisto_pesato += risultato['punteggio_acquisto'] * pesi_validi[i]
            punteggio_vendita_pesato += risultato['punteggio_vendita'] * pesi_validi[i]

        if somma_pesi_validi > 0:
            punteggio_acquisto_pesato /= somma_pesi_validi
            punteggio_vendita_pesato /= somma_pesi_validi
        # --- Fine Logica di Riponderazione ---

        risultato_principale = risultati_validi[0]
        ultimo_prezzo = risultato_principale['ultimo_prezzo']

        segnale = "MANTIENI"
        if punteggio_acquisto_pesato > punteggio_vendita_pesato + 0.5: # Soglia di robustezza
            segnale = "COMPRA"
        elif punteggio_vendita_pesato > punteggio_acquisto_pesato + 0.5:
            segnale = "VENDI"

        motivazione = f"Punteggio Pesato Normalizzato - Acquisto: {punteggio_acquisto_pesato:.2f} vs Vendita: {punteggio_vendita_pesato:.2f} (su pesi totali {somma_pesi_validi:.2f})"

        stop_loss_price = None
        if segnale == "COMPRA":
            stop_loss_percentuale = config.get('parametri_ia', {}).get('stop_loss_percentuale')
            if stop_loss_percentuale is not None:
                stop_loss_price = ultimo_prezzo * (1 - stop_loss_percentuale / 100)

        logging.debug(f"Dettagli analisi combinati: {dettagli_analisi_combinati}")
        return {
            "coppia": coppia,
            "segnale": segnale,
            "ultimo_prezzo": float(ultimo_prezzo),
            "stop_loss_price": float(stop_loss_price) if stop_loss_price is not None else None,
            "punteggio_acquisto": punteggio_acquisto_pesato,
            "punteggio_vendita": punteggio_vendita_pesato,
            "dettagli_analisi": dettagli_analisi_combinati,
            "motivazione": motivazione,
            "dati_reali": True
        }

    except Exception as e:
        logging.error(f"ERRORE CRITICO in analizza_mercato_e_genera_segnale: {e}", exc_info=True)
        raise e

async def analizza_singolo_timeframe(piattaforma, coppia, timeframe):
    """Funzione helper per analizzare un singolo timeframe e restituire i punteggi."""
    try:
        config = carica_configurazione()
        params = config['parametri_indicatori']
        dati_ohlcv = await piattaforma.fetch_ohlcv(coppia, timeframe, limit=100)

        if not dati_ohlcv or len(dati_ohlcv) < params['sma_periodo']: # Controllo base
            return None

        df = pd.DataFrame(dati_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calcolo indicatori
        sma = calcola_sma(df, params['sma_periodo'])
        rsi = calcola_rsi(df, params['rsi_periodo'])
        macd_line, signal_line, _ = calcola_macd(df, params['macd_periodo_veloce'], params['macd_periodo_lento'], params['macd_periodo_segnale'])

        ultimo_prezzo = df['close'].iloc[-1]
        dettagli_analisi = {
            "rsi_14": rsi.iloc[-1],
            "sma_20": sma.iloc[-1],
            "macd_line": macd_line.iloc[-1],
            "signal_line": signal_line.iloc[-1],
        }

        if any(pd.isna(v) for v in dettagli_analisi.values()):
            return None

        punteggio_acquisto = 0
        punteggio_vendita = 0
        if dettagli_analisi["sma_20"] and ultimo_prezzo > dettagli_analisi["sma_20"]: punteggio_acquisto += 1
        if dettagli_analisi["sma_20"] and ultimo_prezzo < dettagli_analisi["sma_20"]: punteggio_vendita += 1
        if dettagli_analisi["rsi_14"] and dettagli_analisi["rsi_14"] < 30: punteggio_acquisto += 1
        if dettagli_analisi["rsi_14"] and dettagli_analisi["rsi_14"] > 70: punteggio_vendita += 1
        if dettagli_analisi["macd_line"] and dettagli_analisi["signal_line"] and dettagli_analisi["macd_line"] > dettagli_analisi["signal_line"]: punteggio_acquisto += 1
        if dettagli_analisi["macd_line"] and dettagli_analisi["signal_line"] and dettagli_analisi["macd_line"] < dettagli_analisi["signal_line"]: punteggio_vendita += 1

        return {
            "ultimo_prezzo": ultimo_prezzo,
            "punteggio_acquisto": punteggio_acquisto,
            "punteggio_vendita": punteggio_vendita,
            "dettagli_analisi": {k: (float(v) if pd.notna(v) else None) for k, v in dettagli_analisi.items()}
        }
    except ccxt.ExchangeError as e:
        # Rilancia l'eccezione specifica dell'exchange per essere gestita dal chiamante (es. per la blacklist)
        logging.warning(f"Errore Exchange per {coppia} ({timeframe}): {e}. L'eccezione verrà propagata.")
        raise e
    except Exception as e:
        # Gestisce altri errori (es. calcoli, dati insufficienti) senza bloccare tutto
        logging.info(f"Dati per timeframe {timeframe} su {coppia} non disponibili o insufficienti. Salto. Dettagli: {e}")
        return None

# --- Logica di Ottimizzazione del Portafoglio (Simulata) ---

def ottimizza_portafoglio_simulato() -> dict:
    """
    Analizza la composizione attuale del portafoglio e la confronta con un modello
    target per generare suggerimenti di ribilanciamento.
    """
    from .gestore_operazioni import gestore_globale_portafoglio
    from .gestore_configurazione import carica_configurazione # Importa per caricare la configurazione

    config = carica_configurazione()
    piattaforme_config = config['piattaforme']
    first_active_platform_name = next((p for p, conf in piattaforme_config.items() if p != '_comment' and conf.get('attiva')), None)
    
    quote_currency = "USDT" # Fallback di sicurezza
    if first_active_platform_name:
        first_active_platform_conf = piattaforme_config.get(first_active_platform_name)
        quote_currency = first_active_platform_conf.get('options', {}).get('quote_currency', 'USDT')

    TARGET_IDEALE = {
        "BTC": 0.40,
        "ETH": 0.30,
        "STABLECOIN": 0.30
    }
    STABLECOINS = ['USDT', 'USDC', 'BUSD', 'DAI'] # Stablecoins da considerare
    TOLLERANZA = 0.05 # 5%

    portafoglio = gestore_globale_portafoglio.portafoglio
    valori_asset_usd = {}
    valore_totale_usd = 0.0

    for asset, quantita in portafoglio.asset.items():
        if quantita <= 0:
            continue
        
        prezzo = 0
        if asset.upper() in STABLECOINS: # Usa .upper() per consistenza
            prezzo = 1.0
        else:
            prezzo_cached = get_prezzo_cache(asset, quote_currency) # Passa quote_currency
            if prezzo_cached is not None:
                prezzo = prezzo_cached
            else:
                continue

        valore = quantita * prezzo
        valori_asset_usd[asset] = valore
        valore_totale_usd += valore

    if valore_totale_usd == 0:
        return {
            "suggerimenti": ["Il portafoglio è vuoto o non valutabile."],
            "composizione_attuale": {"BTC": 0, "ETH": 0, "STABLECOIN": 0, "ALTRI": 0},
            "composizione_target": TARGET_IDEALE
        }

    composizione_attuale = {
        "BTC": valori_asset_usd.get("BTC", 0) / valore_totale_usd,
        "ETH": valori_asset_usd.get("ETH", 0) / valore_totale_usd,
        "STABLECOIN": sum(v for k, v in valori_asset_usd.items() if k.upper() in STABLECOINS) / valore_totale_usd,
        "ALTRI": sum(v for k, v in valori_asset_usd.items() if k.upper() not in ["BTC", "ETH"] + [s.upper() for s in STABLECOINS]) / valore_totale_usd
    }

    suggerimenti = []
    
    for asset, percentuale_target in TARGET_IDEALE.items():
        percentuale_attuale = composizione_attuale.get(asset, 0) # Usa .get per sicurezza
        differenza = percentuale_target - percentuale_attuale
        
        if abs(differenza) > TOLLERANZA:
            if differenza > 0:
                suggerimenti.append(f"Aumentare esposizione su {asset}. Target: {percentuale_target:.0%}, Attuale: {percentuale_attuale:.0%}.")
            else:
                suggerimenti.append(f"Ridurre esposizione su {asset}. Target: {percentuale_target:.0%}, Attuale: {percentuale_attuale:.0%}.")

    if composizione_attuale.get("ALTRI", 0) > TOLLERANZA:
        suggerimenti.append(f"Considerare di ridurre l'esposizione su altri altcoin (Attuale: {composizione_attuale['ALTRI']:.0%}).")

    if not suggerimenti:
        suggerimenti.append("Il portafoglio è ben bilanciato secondo il modello target.")

    response_data = {
        "suggerimenti": suggerimenti,
        "composizione_attuale": {k: round(v, 4) for k, v in composizione_attuale.items()},
        "composizione_target": TARGET_IDEALE
    }
    logging.debug(f"Output ottimizzazione portafoglio: {response_data}")
    return response_data

# --- Nuova Logica per Strategie di Mercato ---

async def suggerisci_strategie_di_mercato(nome_piattaforma: str, top_n: int = 150, output_n: int = 5):
    """
    Analizza l'intero mercato per identificare gli asset con il più forte momentum positivo,
    escludendo le coppie presenti nella blacklist.
    """
    logging.info(f"Avvio analisi strategie di mercato per {nome_piattaforma}...")
    piattaforma = None
    try:
        piattaforma = inizializza_piattaforma(nome_piattaforma)
        blacklist = get_blacklisted_pairs_set()
        logging.info(f"Strategie di mercato: blacklist caricata con {len(blacklist)} coppie.")

        if not piattaforma.markets:
            await piattaforma.load_markets()

        quote_currencies = ['USDT', 'USDC']
        tickers = await piattaforma.fetch_tickers()
        
        if not tickers:
            logging.warning("Impossibile recuperare i tickers dalla piattaforma.")
            return []

        top_symbols = []
        num_per_quote = top_n // len(quote_currencies)

        for qc in quote_currencies:
            qc_tickers = {
                symbol: ticker for symbol, ticker in tickers.items()
                if symbol.endswith(f'/{qc}') and ticker.get('quoteVolume')
            }
            sorted_qc_tickers = sorted(qc_tickers.items(), key=lambda item: item[1]['quoteVolume'], reverse=True)
            top_symbols.extend([symbol for symbol, ticker in sorted_qc_tickers[:num_per_quote]])
        
        logging.info(f"Selezionati {len(top_symbols)} simboli per l'analisi preliminare.")

        # Filtra i simboli usando la blacklist
        simboli_filtrati = [s for s in top_symbols if s not in blacklist]
        logging.info(f"Rimossi {len(top_symbols) - len(simboli_filtrati)} simboli dalla blacklist. Si procede con {len(simboli_filtrati)} simboli.")

        tasks = [analizza_singolo_asset(piattaforma, symbol) for symbol in simboli_filtrati]
        risultati_analisi = await asyncio.gather(*tasks)

        risultati_validi = [res for res in risultati_analisi if res]

        # Filtro di sicurezza per asset con crescita eccessiva
        limite_crescita_7d = 1.0  # Corrisponde a +100%
        risultati_filtrati_per_rischio = []
        for res in risultati_validi:
            if res['performance_7d'] < limite_crescita_7d:
                risultati_filtrati_per_rischio.append(res)
            else:
                logging.info(f"Asset {res['simbolo']} scartato a causa di una crescita eccessiva e rischiosa (+{res['performance_7d']:.1%} in 7 giorni).")

        risultati_ordinati = sorted(risultati_filtrati_per_rischio, key=lambda x: x['punteggio_momentum'], reverse=True)

        suggerimenti_finali = []
        for suggerimento in risultati_ordinati[:output_n]:
            perf_7d = suggerimento['performance_7d']
            profitto_mensile_teorico = ((1 + perf_7d) ** (30/7)) - 1
            suggerimento['proiezioni'] = {
                'mensile_percentuale': round(profitto_mensile_teorico * 100, 2),
                'nota': "Le proiezioni sono estrapolazioni teoriche."
            }
            suggerimenti_finali.append(suggerimento)

        logging.info(f"Analisi completata. Trovati {len(suggerimenti_finali)} suggerimenti validi.")
        return suggerimenti_finali

    except Exception as e:
        logging.error(f"Errore grave in suggerisci_strategie_di_mercato: {e}", exc_info=True)
        return []
    finally:
        if piattaforma:
            await piattaforma.close()


async def analizza_singolo_asset(piattaforma, simbolo: str):
    """
    Funzione helper per analizzare un singolo asset e calcolare il suo punteggio.
    """
    try:
        # Usa '1d' per dati giornalieri, che sono più stabili per l'analisi di momentum
        ohlcv = await piattaforma.fetch_ohlcv(simbolo, '1d', limit=90)
        if len(ohlcv) < 31: # Richiede almeno 31 giorni per calcolare performance a 30gg e RSI
            logging.warning(f"Dati insufficienti per {simbolo} ({len(ohlcv)} candele). Salto.")
            return None

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calcolo performance
        prezzo_attuale = df['close'].iloc[-1]
        prezzo_7d_fa = df['close'].iloc[-8] # -1 è oggi, -8 è 7 giorni fa
        prezzo_30d_fa = df['close'].iloc[-31]
        
        perf_7d = (prezzo_attuale - prezzo_7d_fa) / prezzo_7d_fa
        perf_30d = (prezzo_attuale - prezzo_30d_fa) / prezzo_30d_fa

        # Calcolo RSI
        rsi = calcola_rsi(df, periodo=14).iloc[-1]
        if pd.isna(rsi):
            return None

        # Calcolo Punteggio Momentum
        # Ponderazione: 60% performance 7gg, 20% performance 30gg, 20% RSI
        # Normalizziamo l'RSI in un range 0-1 per il punteggio
        punteggio_momentum = (perf_7d * 0.6) + (perf_30d * 0.2) + ((rsi / 100) * 0.2)

        return {
            'simbolo': simbolo,
            'ultimo_prezzo': prezzo_attuale,
            'punteggio_momentum': punteggio_momentum,
            'performance_7d': perf_7d,
            'performance_30d': perf_30d,
            'rsi_14d': rsi
        }
    except Exception as e:
        logging.debug(f"Impossibile analizzare il simbolo {simbolo}: {e}")
        return None
