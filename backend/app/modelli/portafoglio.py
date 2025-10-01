# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

from pydantic import BaseModel, Field
from typing import Dict, List
from .operazione import Operazione
from .posizioni import PosizioneAperta # Aggiunto

class Portafoglio(BaseModel):
    """
    Rappresenta lo stato del portafoglio di trading.
    """
    budget_usd_iniziale: float
    budget_usd_corrente: float
    asset: Dict[str, float] = Field(default_factory=dict) # Es. {"BTC": 0.5, "ETH": 10}
    storico_operazioni: List[Operazione] = Field(default_factory=list)
    posizioni_aperte: Dict[str, PosizioneAperta] = Field(default_factory=dict) # Nuovo campo per le posizioni aperte
    profitto_perdita_totale_usd: float = 0.0

    def calcola_valore_totale(self, prezzi_correnti: Dict[str, float]) -> float:
        """
        Calcola il valore totale del portafoglio in USD.
        """
        valore_asset = sum(quantita * prezzi_correnti.get(simbolo, 0) for simbolo, quantita in self.asset.items())
        return self.budget_usd_corrente + valore_asset
