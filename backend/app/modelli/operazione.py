# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class Operazione(BaseModel):
    """
    Rappresenta una singola operazione di trading (acquisto o vendita).
    """
    id_operazione: str
    timestamp: datetime = Field(default_factory=datetime.now)
    piattaforma: str
    coppia: str
    tipo: Literal['acquisto', 'vendita', 'acquisto_simulato', 'vendita_simulata', 'acquisto_reale_market', 'acquisto_reale_limit', 'vendita_reale_market', 'vendita_reale_limit', 'acquisto_simulato_market', 'acquisto_simulato_limit', 'vendita_simulata_market', 'vendita_simulata_limit']
    quantita: float
    prezzo: float
    controvalore_usd: float
    commissioni_usd: float
    profitto_perdita_operazione: float = 0.0 # Nuovo campo per tracciare profitto/perdita di questa operazione
