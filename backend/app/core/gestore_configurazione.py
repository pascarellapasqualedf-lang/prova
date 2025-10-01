# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import json
from .path_manager import CONFIG_PATH

def carica_configurazione():
    """
    Carica la configurazione usando il percorso centralizzato da path_manager.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"File di configurazione non trovato in: {CONFIG_PATH}")
    
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
    
    return config

# Esempio di come usarlo (può essere rimosso)
if __name__ == "__main__":
    configurazione = carica_configurazione()
    print("Configurazione caricata con successo:")
    print(configurazione)
