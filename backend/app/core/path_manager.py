# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import sys
import os
from pathlib import Path

def get_application_path() -> Path:
    """
    Restituisce il percorso della directory principale dell'applicazione.
    Funziona sia in modalità sviluppo (come script .py) sia come eseguibile compilato.
    """
    if getattr(sys, 'frozen', False):
        # Se l'applicazione è "congelata" (es. con PyInstaller)
        return Path(os.path.dirname(sys.executable))
    else:
        # Altrimenti, siamo in modalità sviluppo
        return Path(os.path.dirname(__file__)).parent.parent.parent

# Percorso radice dell'applicazione
APP_PATH = get_application_path()

# Percorsi principali
CONFIG_PATH = APP_PATH / "config.json"
DATA_PATH = APP_PATH / "data"
LOG_PATH = APP_PATH / "log"

# Assicurati che le directory DATA e LOG esistano
DATA_PATH.mkdir(exist_ok=True)
LOG_PATH.mkdir(exist_ok=True)

# Percorsi specifici dei file
PORTFOLIO_STATE_FILE = DATA_PATH / "portfolio_state.json"
LOG_FILE = LOG_PATH / "backend.log"
