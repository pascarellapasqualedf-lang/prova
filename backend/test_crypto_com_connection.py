import asyncio
import sys
import os

# Aggiungi la directory radice del progetto al PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from servizi.gestore_piattaforme import inizializza_piattaforma

async def test_crypto_com_connection():
    print("Tentativo di test della connessione a Crypto.com...")
    try:
        # Assicurati che 'cryptocom' sia attiva e configurata in config.json
        piattaforma = inizializza_piattaforma('cryptocom')
        await piattaforma.load_markets()
        balance = await piattaforma.fetch_balance()
        print("Connessione a Crypto.com riuscita!")
        print("Saldo (parziale):", balance['total'])
        await piattaforma.close()
    except Exception as e:
        print(f"Errore durante il test della connessione a Crypto.com: {e}")
        print("Assicurati che 'cryptocom' sia configurata correttamente in config.json e che le API Key siano valide.")

if __name__ == "__main__":
    asyncio.run(test_crypto_com_connection())
