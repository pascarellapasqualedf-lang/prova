import subprocess
import time
import sys

# Codice di uscita speciale che l'app userà per segnalare
# la necessità di un riavvio a causa della memoria.
RESTART_EXIT_CODE = 3

def run_server():
    """
    Avvia il server uvicorn come un sottoprocesso.
    """
    # Comando per avviare uvicorn. Assicurati che 'uvicorn' sia nel tuo PATH
    # o fornisci il percorso completo.
    command = [
        "uvicorn",
        "backend.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    ]
    
    print(f"Avvio del server con il comando: {' '.join(command)}")
    
    # Avvia il sottoprocesso
    process = subprocess.Popen(command)
    return process

def main():
    """
    Funzione principale che gestisce il ciclo di avvio e monitoraggio del server.
    Riavvia il server se termina con un codice di uscita diverso da 0.
    """
    while True:
        server_process = run_server()
        server_process.wait()  # Attendi che il processo del server termini

        # Codice 0 indica una chiusura pulita e intenzionale.
        # Qualsiasi altro codice (es. 1 per errori generici, o codici da segnali)
        # indica una terminazione inaspettata o un riavvio richiesto.
        if server_process.returncode != 0:
            print(f"Server terminato con codice {server_process.returncode}. Riavvio tra 5 secondi...")
            time.sleep(5)
            continue  # Il ciclo while ripartirà, riavviando il server
        else:
            print("Server terminato con codice 0 (uscita pulita). Il supervisore si arresta.")
            break # Esce dal ciclo se la terminazione è pulita

if __name__ == "__main__":
    main()