# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

from pydantic import BaseModel, Field
from datetime import datetime

class PosizioneAperta(BaseModel):
    """
    Rappresenta una posizione di trading aperta per un asset specifico.
    """
    coppia: str
    quantita: float
    prezzo_medio_acquisto: float
    timestamp_apertura: datetime = Field(default_factory=datetime.now)
    commissioni_totali_acquisto: float = 0.0
    take_profit_price: float | None = None # Aggiunto per il take profit
