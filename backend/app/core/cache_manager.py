# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import time

# Dizionario in-memory per la cache dei dati della dashboard.
# Struttura: {"data": <dati_calcolati>, "last_updated": <timestamp>}
dashboard_cache = {
    "data": None,
    "last_updated": 0
}

def get_dashboard_cache():
    """Restituisce il contenuto della cache della dashboard."""
    return dashboard_cache

def set_dashboard_cache(data):
    """Aggiorna la cache della dashboard con nuovi dati."""
    global dashboard_cache
    dashboard_cache["data"] = data
    dashboard_cache["last_updated"] = time.time()
