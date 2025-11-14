# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from gestore_piattaforme import GestorePiattaforme
from cervello_ia import CervelloIA
from gestore_operazioni import GestoreOperazioni

app = FastAPI()
print("FastAPI app initialized. Adding CORS middleware...") # Debug print

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("CORS middleware added.") # Debug print

# Inizializzazione dei gestori e del cervello IA
# Assicurati che il percorso di config.json sia corretto rispetto a dove viene eseguito main.py
gestore_piattaforme = GestorePiattaforme(config_path='C:/Users/AAVV/PPG/TradeAI_v3/config.json')
cervello_ia = CervelloIA(gestore_piattaforme)
gestore_operazioni = GestoreOperazioni(gestore_piattaforme)

# Carica il budget iniziale dal config.json
try:
    with open('C:/Users/AAVV/PPG/TradeAI_v3/config.json', 'r') as f:
        config_data = json.load(f)
    initial_budget_usd = config_data.get("impostazioni_generali", {}).get("budget_totale_usd", 1000.0)
except (FileNotFoundError, json.JSONDecodeError):
    initial_budget_usd = 1000.0 # Valore di fallback

@app.get("/stato_portafoglio")
async def get_stato_portafoglio():
    """
    Endpoint per recuperare lo stato attuale del portafoglio (dati mock per ora).
    """
    mock_data = {
        "budget_usd_iniziale": initial_budget_usd,
        "budget_usd_corrente": initial_budget_usd, # Per ora, uguale all'iniziale
        "asset": {
            "USD": initial_budget_usd,
        },
        "storico_operazioni": [],
        "profitto_perdita_totale_usd": 0.0
    }
    return mock_data

@app.get("/test_connessione/{exchange_id}")
async def test_connessione(exchange_id: str):
    """
    Endpoint per testare la connessione a una piattaforma di scambio e recuperare i saldi.
    """
    exchange = await gestore_piattaforme.get_exchange(exchange_id)
    if not exchange:
        raise HTTPException(status_code=404, detail=f"Piattaforma {exchange_id} non trovata o non attiva.")
    try:
        balance = await exchange.fetch_balance()
        return {"status": "success", "exchange": exchange_id, "balance": balance['total']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante il recupero del saldo per {exchange_id}: {e}")

@app.get("/get_trading_signal/{exchange_id}/{symbol}")
async def get_trading_signal(exchange_id: str, symbol: str, timeframe: str = '1d', limit: int = 100):
    """
    Endpoint per ottenere un segnale di trading per un dato simbolo su una piattaforma.
    """
    ohlcv_data = await cervello_ia.get_ohlcv_data(exchange_id, symbol, timeframe, limit)
    if not ohlcv_data:
        raise HTTPException(status_code=500, detail="Impossibile recuperare i dati OHLCV.")

    analyzed_data = await cervello_ia.analyze_data(ohlcv_data)
    if analyzed_data is None:
        raise HTTPException(status_code=500, detail="Impossibile analizzare i dati.")

    signal = await cervello_ia.generate_signals(analyzed_data)
    return {"symbol": symbol, "signal": signal, "exchange": exchange_id}

@app.post("/execute_order/{exchange_id}/{symbol}")
async def execute_order(exchange_id: str, symbol: str, type: str, side: str, amount: float, price: float = None):
    """
    Endpoint per eseguire un ordine di trading.
    """
    order_result = await gestore_operazioni.esegui_ordine(exchange_id, symbol, type, side, amount, price)
    if order_result:
        return {"status": "success", "order": order_result}
    else:
        raise HTTPException(status_code=500, detail="Errore durante l'esecuzione dell'ordine.")

@app.post("/simulate_order/{symbol}")
async def simulate_order(symbol: str, type: str, side: str, amount: float, price: float = None):
    """
    Endpoint per simulare un ordine di trading.
    """
    simulation_result = await gestore_operazioni.simula_ordine(symbol, type, side, amount, price)
    return {"status": "success", "simulation": simulation_result}
