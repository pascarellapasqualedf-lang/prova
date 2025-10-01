# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import ccxt
import json

class GestorePiattaforme:
    def __init__(self, config_path: str = 'config.json'):
        self.config_path = config_path
        self.piattaforme_attive = {}
        self._carica_configurazione()

    def _carica_configurazione(self):
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            self.config_piattaforme = config.get('piattaforme', {})
            print(f"Debug: Tipo di self.config_piattaforme: {type(self.config_piattaforme)}")
            print(f"Debug: Contenuto di self.config_piattaforme: {self.config_piattaforme}")
            self._inizializza_piattaforme()
        except FileNotFoundError:
            print(f"Errore: File di configurazione non trovato a {self.config_path}")
        except json.JSONDecodeError:
            print(f"Errore: Impossibile decodificare il file JSON a {self.config_path}")

    def _inizializza_piattaforme(self):
        for id_piattaforma, dati_piattaforma in self.config_piattaforme.items():
            print(f"Debug: Inizializzazione piattaforma {id_piattaforma}")
            print(f"Debug: Tipo di dati_piattaforma: {type(dati_piattaforma)}")
            print(f"Debug: Contenuto di dati_piattaforma: {dati_piattaforma}")
            # Ignora le voci che non sono dizionari (come i commenti)
            if not isinstance(dati_piattaforma, dict):
                print(f"Debug: Saltando la voce {id_piattaforma} perch non  un dizionario di configurazione.")
                continue

            if dati_piattaforma.get('attiva', False):
                try:
                    exchange_class = getattr(ccxt, id_piattaforma)
                    exchange = exchange_class({
                        'apiKey': dati_piattaforma.get('api_key'),
                        'secret': dati_piattaforma.get('api_secret'),
                        'enableRateLimit': True,
                    })
                    self.piattaforme_attive[id_piattaforma] = exchange
                    print(f"Piattaforma {id_piattaforma} inizializzata con successo.")
                except AttributeError:
                    print(f"Errore: Piattaforma {id_piattaforma} non supportata da ccxt.")
                except Exception as e:
                    print(f"Errore durante l'inizializzazione di {id_piattaforma}: {e}")

    async def get_exchange(self, exchange_id: str):
        """
        Restituisce un'istanza della piattaforma di scambio se attiva.
        """
        exchange = self.piattaforme_attive.get(exchange_id)
        if not exchange:
            print(f"Piattaforma {exchange_id} non attiva o non inizializzata.")
        return exchange
