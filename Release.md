## Versione 1.20.4 (18 Novembre 2025)

Questa versione re-introduce la strategia di trading più aggressiva e opportunistica delle precedenti versioni di successo, combinandola con la stabilità e le correzioni tecniche implementate nelle versioni più recenti.

### ✨ Miglioramenti Strategici

-   **Ritorno alla Strategia Aggressiva/Opportunistica:** La configurazione del bot è stata aggiornata per replicare i parametri di trading delle versioni 1.11-1.13, che avevano dimostrato una redditività costante:
    -   **Aumento del Rischio per Operazione:** `percentuale_rischio_per_operazione` è stata aumentata dal 4% al **10%**. Questo consente al bot di aprire posizioni di dimensione maggiore, amplificando i potenziali guadagni (e perdite).
    -   **Selezione Dinamica degli Asset Attiva:** `selezione_asset_dinamica` è stata riattivata. Il bot ora cerca attivamente nuove opportunità di trading nel mercato basandosi sul momentum, estendendo la sua operatività oltre la sola lista di asset preferiti.
    -   **Take Profit Interno Disattivato:** `percentuale_take_profit` è stato impostato a `0`. Il bot ora lascerà correre i profitti sulle posizioni aperte, vendendo solo in base ai segnali dell'IA, replicando il comportamento che permetteva di cavalcare i trend per guadagni maggiori.

-   **Miglioramento Gestione Take Profit:** La logica interna di take profit nel codice è stata resa condizionale; ora si attiva solo se `percentuale_take_profit` è impostato a un valore > 0, consentendo di disabilitarlo tramite configurazione senza modificare il codice.

### ⚙️ Miglioramenti Tecnici

-   **Output Pulito per Riavvio Memoria:** La procedura di riavvio automatico del backend per superamento del limite di memoria ora si spegne in modo più pulito, eliminando i `Traceback` di errore nel log e rendendo l'output più leggibile.

---

## Versione 1.20.3 (18 Novembre 2025)

Questa versione introduce una serie di correzioni critiche per migliorare la stabilità del backend, l'affidabilità della logica di trading e l'accuratezza del calcolo dei profitti.

### 🐛 Correzioni di Bug Critici

-   **Risolto Problema di Capitale in Calo (Vendita "Dust"):**
    -   Corretto un bug fondamentale nella logica di vendita che non garantiva la liquidazione completa di una posizione. A causa di arrotondamenti e commissioni, piccole quantità di asset ("polvere" o "dust") rimanevano nel portafoglio, falsando il calcolo del profitto/perdita e causando un'erosione apparente del capitale.
    -   La funzione `esegui_vendita` è stata potenziata con una modalità `vendi_tutto` che assicura la vendita dell'intero saldo dell'asset e la chiusura forzata della posizione, garantendo un calcolo P/L corretto.

-   **Risolto Errore `InvalidOrder` per Precisione:**
    -   La logica di vendita è stata resa più robusta. Prima di inviare un ordine, il sistema ora "pulisce" la quantità da vendere per rispettare le regole di precisione e di step-size imposte dall'exchange (es. vendere 1.1 e non 1.15).
    -   Aggiunto un controllo per cui, se la quantità da vendere è "polvere" non commerciabile (inferiore alla precisione minima), la vendita viene annullata con un avviso invece di generare un errore.

-   **Risolto Errore `InsufficientFunds` a Cascata:**
    -   Corretto un bug nel ciclo di acquisto per cui il bot tentava di aprire più posizioni di fila usando un valore di budget non aggiornato, causando una cascata di errori "Fondi Insufficienti".
    -   Il calcolo del budget liquido viene ora aggiornato prima di ogni singolo tentativo di acquisto, rendendo la logica di spesa più realistica e precisa.

### ⚙️ Miglioramenti Tecnici

-   **Architettura di Riavvio Robusta:**
    -   Il meccanismo di riavvio per superamento della memoria è stato riprogettato. Invece di un riavvio interno, il backend ora termina con un codice speciale.
    -   Lo script `run_backend.py` è stato trasformato in un "supervisore" che rileva questo codice e gestisce il riavvio del processo, prevenendo problemi di "Address already in use" e aumentando la stabilità generale.

### 🧹 Manutenzione

-   **Allineamento Versioni:** La versione del backend (in `config.json`) e del frontend (in `package.json`) sono state allineate a `1.20.3`.

---
## Versione 1.20.2 (17 Novembre 2025)

### ✨ Nuove Funzionalità

- **Sistema di Monitoraggio Memoria e Riavvio Automatico:**
  - È stato introdotto un nuovo sistema di monitoraggio proattivo per controllare l'utilizzo della memoria RAM da parte del backend.
  - Se l'applicazione supera una soglia di memoria critica definita nel file `config.json` (sezione `monitoraggio_sistema`), il sistema si arresterà automaticamente.
  - Se eseguito tramite un gestore di servizi come `systemd`, questo meccanismo permette un riavvio automatico, garantendo maggiore stabilità e prevenendo crash dovuti a un consumo eccessivo di memoria.
  - La configurazione di default prevede una soglia di 2GB e un controllo ogni 10 minuti.

### ⚙️ Miglioramenti Tecnici

- Aggiunta della dipendenza `psutil` per l'analisi delle risorse di sistema.
- Integrazione della logica di monitoraggio come un task asincrono in background all'avvio dell'applicazione.
---
## Versione 1.20.1 (13/11/2025)                                                                               
- Questa versione risolve un bug critico che impediva la corretta registrazione delle operazioni di "Take Profit".
### 🐛 Correzioni di Bug
- **Fix Storico Take Profit Vuoto:** Risolto un bug nel ciclo di trading principale (`ai_trading_loop`) dove un blocco di codice duplicato causava la gestione errata delle vendite per Take Profit. La logica di vendita veniva eseguita due volte: la prima correttamente, ma la seconda in modo
---
## Versione 1.20.0 (13/11/2025)

Questa versione affronta un problema di stabilità critico che causava l'arresto anomalo del backend a causa di una perdita di memoria (memory leak).

### 🐛 Correzioni di Bug Critici

-   **Correzione Perdita di Memoria (Memory Leak):** Risolto un grave problema di perdita di memoria che portava il sistema operativo a terminare forzatamente il processo del backend (`Out of memory: Killed process`). L'analisi ha rivelato che la creazione continua di nuove connessioni all'exchange (`ccxt`) in ogni ciclo consumava progressivamente tutta la RAM disponibile.
-   **Introduzione Gestore di Istanze Centralizzato:** Per risolvere il problema alla radice, è stato creato un nuovo modulo `servizi/instance_manager.py`. Questo componente agisce come un "singleton", creando **una sola istanza di connessione per ogni piattaforma** e riutilizzandola per tutte le operazioni. Questo approccio previene la creazione di migliaia di connessioni usa-e-getta, garantendo un uso della memoria stabile e predicibile.
-   **Refactoring Completo della Gestione Connessioni:** Tutti i moduli del backend (`main.py`, `gestore_operazioni.py`, `market_data_service.py`, ecc.) sono stati modificati per utilizzare il nuovo `instance_manager` invece di creare connessioni in modo autonomo. La logica di chiusura delle connessioni è stata centralizzata e viene ora gestita solo allo spegnimento dell'applicazione, eliminando il rischio di connessioni non chiuse.

### ✨ Miglioramenti

-   **Stabilità a Lungo Termine:** Grazie a queste modifiche, la stabilità del backend è notevolmente migliorata, passando da poche ore a oltre 12 ore di funzionamento continuo senza crash. Sebbene sia stato risolto il problema principale, il monitoraggio continuerà per identificare eventuali perdite di memoria secondarie.

---

## Versione 1.19.0 (16/10/2025)

Questa versione introduce nuove funzionalità per il monitoraggio delle performance e aumenta la flessibilità della configurazione del bot, oltre a risolvere bug critici legati alla stabilità e all'accuratezza dei dati.

### ✨ Funzionalità e Miglioramenti

-   **Nuova Pagina "Storico Take Profit":** Aggiunta una nuova sezione nel frontend per visualizzare unicamente le operazioni di vendita che sono state attivate dal raggiungimento dell'obiettivo di "Take Profit", permettendo un'analisi più chiara delle strategie di guadagno.
-   **Logica di Selezione Asset Ibrida:** Introdotta una nuova opzione `ignora_preferiti_con_dinamica`. Se disattivata, il bot analizzerà un elenco unificato che include sia gli asset trovati dinamicamente dall'IA sia quelli presenti nella lista `cripto_preferite`, combinando le due strategie.
-   **Cooldown di Riacquisto Configurabile:** La funzionalità di cooldown dopo una vendita è ora opzionale tramite il nuovo flag `attiva_cooldown_dopo_vendita` nel file di configurazione.

### 🐛 Correzioni di Bug Critici

-   **Correzione Calcolo Valore Portafoglio:** Risolto un bug fondamentale nella funzione di riconciliazione (`reconcile_balances_with_exchange`) che calcolava in modo errato il valore totale del portafoglio, causando discrepanze significative tra il valore reale e quello mostrato nel frontend. Ora il valore corrente e iniziale del portafoglio riflettono accuratamente la somma di tutte le stablecoin e degli asset valorizzati.
-   **Risoluzione Errori di Avvio del Backend:**
    -   Corretto un `ImportError` (dipendenza circolare) separando le variabili di stato globali in un nuovo file `app/core/app_state.py`.
    -   Corretto un `AttributeError` relativo a una chiamata a una funzione inesistente (`_registra_valore_portafoglio`) durante lo startup.
-   **Risoluzione Errori di Serializzazione e Tipo:**
    -   Corretto un `TypeError: Object of type datetime is not JSON serializable` che impediva il salvataggio dello stato del portafoglio.
    -   Corretto un `TypeError` nelle funzioni `get_analisi_operazioni` e `calcola_report_performance` che si verificava a causa di una gestione errata dei tipi di dato.
-   **Gestione Connessioni di Rete:** Migliorata la gestione delle connessioni `ccxt` per prevenire errori di `Unclosed client session` durante il riavvio del server.

---

## Versione 1.17.0 (08/10/2025)

Questa versione introduce importanti miglioramenti alla logica di trading e alla gestione del rischio, rendendo il bot più flessibile, sicuro e configurabile. Sono state inoltre aggiunte nuove funzionalità e corretti diversi bug.

### ✨ Funzionalità e Miglioramenti

-   **Logica di Take Profit Interna:** Implementata una nuova strategia di "Take Profit". Invece di piazzare un ordine di vendita rigido sull'exchange, il bot ora monitora internamente un obiettivo di prezzo. Questo permette di vendere l'asset sia al raggiungimento del profitto desiderato, sia in anticipo se l'IA rileva un'inversione di tendenza.
-   **Cooldown di Riacquisto Parametrizzato:** Introdotto un periodo di "cooldown" per gli asset venduti. Un asset venduto non verrà riacquistato fino all'orario di reset del giorno successivo, prevenendo riacquisti immediati e impulsivi. L'orario di reset è ora configurabile.
-   **Interruttore Unico per Stop Loss:** Il flag `trailing_stop_loss` ora agisce come un interruttore generale per tutti i meccanismi di stop loss (sia statici che trailing), rendendo la configurazione più chiara e intuitiva.
-   **Tooltip Esplicativi nel Frontend:** Aggiunti tooltip informativi a tutte le opzioni nella pagina di configurazione della dashboard React, migliorando significativamente l'usabilità e la comprensione di ogni parametro.

### 🐛 Correzioni di Bug

-   **Bug Selezione Asset Dinamica:** Risolto un bug critico per cui il bot acquistava asset non autorizzati anche quando la selezione dinamica era disattivata. Ora il bot rispetta rigorosamente la lista `cripto_preferite`.
-   **Errori di Sintassi e Indentazione (Backend):** Corretti numerosi errori di sintassi e indentazione in Python che impedivano l'avvio del backend.

---

## Versione 1.16.0 (07/10/2025)

Questa versione migliora la tracciabilità e la visibilità sul comportamento del bot estendendo il sistema di registrazione degli eventi e corregge un bug critico nella logica di riconciliazione del portafoglio.

### ✨ Funzionalità e Miglioramenti

-   **Estensione Tracciamento Eventi:** Il sistema ora registra una gamma più ampia di eventi nel database, fornendo una visione più completa delle decisioni del bot:
    -   **Segnali MANTIENI:** Viene registrato un evento ogni volta che l'IA analizza un asset ma decide di non operare.
    -   **Piazzamento Stop Loss:** La creazione di un ordine `STOP_LOSS` dopo un acquisto viene ora tracciata come un evento specifico.
    -   **Errori di Analisi:** Eventuali errori che si verificano durante l'analisi di una coppia vengono registrati, aiutando a identificare problemi con i dati o con le API.

### 🐛 Correzioni di Bug

-   **Correzione Riconciliazione Portafoglio:** Risolto un bug critico nella funzione `reconcile_balances_with_exchange` che impostava il budget corrente al solo valore delle stablecoin, ignorando gli altri asset. Ora il valore totale del portafoglio viene calcolato e assegnato correttamente all'avvio.
-   **Correzione Bug di Compilazione (Flutter & React):** Risolti numerosi errori di compilazione e runtime emersi durante lo sviluppo, rendendo le applicazioni più stabili.

---

## Versione 1.15.0 (04/10/2025)

Questa versione migliora la tracciabilità e la visibilità sul comportamento del bot estendendo il sistema di registrazione degli eventi.

### ✨ Funzionalità e Miglioramenti

-   **Estensione Tracciamento Eventi:** Il sistema ora registra una gamma più ampia di eventi nel database, fornendo una visione più completa delle decisioni del bot:
    -   **Segnali MANTIENI:** Viene registrato un evento ogni volta che l'IA analizza un asset ma decide di non operare.
    -   **Piazzamento Stop Loss:** La creazione di un ordine `STOP_LOSS` dopo un acquisto viene ora tracciata come un evento specifico.
    -   **Errori di Analisi:** Eventuali errori che si verificano durante l'analisi di una coppia vengono registrati, aiutando a identificare problemi con i dati o con le API.

### 🐛 Correzioni di Bug

-   **Correzione Bug di Compilazione (Flutter):** Risolti gli errori di compilazione nell'app Flutter relativi a importazioni mancanti e sintassi errata, rendendo l'app nuovamente avviabile e funzionante.

---

## Versione 1.14.0 (04/10/2025)

Questa versione consolida la stabilità del backend e migliora significativamente l'esperienza utente del frontend, risolvendo diversi bug e riorganizzando l'interfaccia per una maggiore chiarezza.

### ✨ Funzionalità e Miglioramenti

-   **Allineamento App Flutter:** Aggiornata l'app Flutter per rispecchiare la nuova struttura della dashboard web.
    -   **Navigazione a Menu:** Implementato un menu laterale (`Drawer`) con sottomenu a tendina (`ExpansionTile`), sostituendo la vecchia `TabBar`.
    -   **Implementazione Schermate:** Create e implementate le schermate per "Storico Operazioni", "Performance" e "Suggerimento IA", recuperando i dati dal backend.
    -   **Creazione Modelli e Servizi:** Aggiunti i modelli Dart e le funzioni di servizio necessarie per le nuove schermate.
-   **Correzione Bug di Compilazione (Flutter):** Risolti numerosi errori di compilazione in Flutter, inclusi problemi di escaping delle stringhe e importazioni mancanti.
-   **Correzione Bug di Compilazione (React):** Risolti errori di `TypeScript` (`TS6133` e `TS2532`) relativi a importazioni non utilizzate e potenziali oggetti `undefined`.
-   **Fix Ottimizzazione Portafoglio:** Risolto l'errore `JSON.parse: unexpected end of data` migliorando la robustezza della funzione `ottimizza_portafoglio_simulato` nel backend.

### 🐛 Correzioni di Bug

-   **Fix Pagina Vuota "Storico Operazioni":** Risoluzione degli errori `No QueryClient set` e `ReferenceError` nel frontend, garantendo il corretto caricamento e visualizzazione della pagina.
-   **Fix "Ottimizzazione Portafoglio":** Risoluzione dell'errore `JSON.parse: unexpected end of data` e miglioramento della robustezza della funzione `ottimizza_portafoglio_simulato` nel backend, assicurando risposte JSON valide.
-   **Gestione Errori di Timeout:** Aumentato il tempo di timeout per le chiamate API all'exchange e migliorata la gestione degli errori per prevenire crash all'avvio.
-   **Errori di Fondi Insufficienti:** La nuova logica di vendita risolve la causa principale degli errori `InsufficientFunds`.
-   **Logging Semplificato:** Gli errori di fondi insufficienti ora producono un messaggio di log chiaro e sintetico invece di una traccia completa.
-   **Correzioni Multiple Backend:** Risolti diversi errori di `NameError` e `SyntaxError` emersi nel backend durante lo sviluppo, rendendo l'applicazione più stabile.
-   **Correzioni Multiple Frontend:** Risolti errori di compilazione (`TS6133`) e runtime (`TypeError`) nel frontend.

### 🧹 Pulizia del Codice

-   **Rimozione Campo Inutilizzato:** Il campo "Percentuale Prelievo Massimo" è stato rimosso dall'interfaccia, dal backend e dai file di configurazione in quanto non utilizzato.
-   **Rimozione Duplicato "Storico Operazioni":** La sezione duplicata dello storico operazioni è stata rimossa dal componente `Portafoglio` nella Dashboard.

---

## Versione 1.13.0 (03/10/2025)

Questa versione introduce una significativa ristrutturazione del backend per migliorare l'affidabilità e la tracciabilità, insieme a importanti miglioramenti dell'interfaccia utente per una maggiore usabilità.

### ✨ Funzionalità e Miglioramenti

-   **Persistenza dello Storico su Database:** Lo storico delle operazioni non è più salvato su un fragile file JSON, ma in una tabella dedicata `operazioni` nel database SQLite. Questo risolve il problema dello storico vuoto e garantisce la persistenza dei dati.
-   **Tracciabilità degli Eventi:** È stata introdotta una nuova tabella `eventi` nel database per registrare azioni non transazionali del bot (es. annullamento di ordini). Questo aumenta notevolmente la visibilità sul comportamento e sulle decisioni dell'IA.
-   **Logica di Vendita Migliorata:** Il bot ora è in grado di annullare ordini aperti (es. `STOP_LOSS`) prima di eseguire un nuovo ordine di vendita sullo stesso asset. Questo lo rende più reattivo alle condizioni di mercato e previene errori di fondi insufficienti.
-   **Riorganizzazione Menu Dashboard:** L'interfaccia della dashboard è stata pulita e riorganizzata. I link di navigazione sono ora raggruppati in menu a tendina logici (`Portafoglio`, `Analisi`, `Impostazioni`), migliorando l'ordine e l'usabilità.

### 🐛 Correzioni di Bug

-   **Gestione Errori di Timeout:** Aumentato il tempo di timeout per le chiamate API all'exchange e migliorata la gestione degli errori per prevenire crash all'avvio.
-   **Errori di Fondi Insufficienti:** La nuova logica di vendita risolve la causa principale degli errori `InsufficientFunds`.
-   **Logging Semplificato:** Gli errori di fondi insufficienti ora producono un messaggio di log chiaro e sintetico invece di una traccia completa.
-   **Correzioni Multiple:** Risolti diversi errori di `NameError`, `SyntaxError` e `TypeError` emersi durante lo sviluppo, rendendo l'applicazione più stabile.

### 🧹 Pulizia del Codice

-   **Rimozione Campo Inutilizzato:** Il campo "Percentuale Prelievo Massimo" è stato rimosso dall'interfaccia, dal backend e dai file di configurazione in quanto non utilizzato.

---

## Versione 1.12.0 (30/09/2025)

- **Centralizzazione Versione**: Il numero di versione del software è ora centralizzato nel file `config.json` e letto dinamicamente da backend, dashboard web e app mobile.
- **Fix Sistema di Logging**: Risolto un bug critico che impediva la corretta impostazione del livello di log. Sostituiti tutti i `print` di debug con chiamate al logger standard per un output pulito e controllabile.
- **Fix Blacklist**: Corretta la logica di popolamento automatico della blacklist. Risolti i problemi di visualizzazione dei dati sia sull'interfaccia web che sull'app mobile.
- **Miglioramento Configurazione**: Suddiviso il "nozionale minimo" in due valori distinti per acquisto e vendita, rendendoli configurabili dal pannello web.
- **Bug Fixing**: Corretti numerosi errori di compilazione e runtime su frontend web (TypeScript) e mobile (Flutter) emersi durante lo sviluppo.

---

## Versione [1.11.0] - 2025-09-29

Questa versione si concentra sulla risoluzione di bug critici legati alla gestione del rischio e sul miglioramento della prudenza del modulo di intelligenza artificiale.

### 🐛 Correzioni di Bug Critici

-   **Gestione Stop Loss Ripristinata:** È stato corretto un bug critico nel file `core/gestore_operazioni.py` che impediva il corretto funzionamento degli ordini di stop loss. La logica è stata invertita per dare priorità allo stop loss statico calcolato dall'IA, garantendo che ogni operazione sia sempre protetta dal limite di perdita configurato (es. 3%).
-   **Calcolo Dimensione Operazione Corretto:** È stato risolto un bug nel file `main.py` per cui la dimensione di ogni operazione era fissata a un valore minimo (15$), ignorando la percentuale di rischio impostata nel file di configurazione. Ora la dimensione di ogni trade viene calcolata dinamicamente in base al valore totale del portafoglio e alla `percentuale_rischio_per_operazione` definita dall'utente (es. 10%).

### ✨ Miglioramenti

-   **Selezione Asset più Prudente:** È stata introdotta una nuova regola di sicurezza nel "cervello" dell'IA (`core/cervello_ia.py`). Il sistema ora scarta automaticamente i suggerimenti per nuovi asset che hanno registrato una crescita eccessiva e potenzialmente insostenibile (superiore al +100% in 7 giorni). Questo riduce il rischio di investire al picco di bolle speculative.

---


# Documentazione Progetto TradeAI V3

Questo documento descrive l'architettura generale e la logica di funzionamento del bot di trading automatico TradeAI V3.

---

## 1. Architettura Generale

Il progetto segue un'architettura **client-server** moderna e disaccoppiata, composta da:

-   **Un Backend Centrale (Python/FastAPI):** Il cuore del sistema. Gestisce tutta la logica di trading, l'analisi di mercato, la comunicazione con gli exchange e l'esposizione dei dati tramite API REST.
-   **Molteplici Frontend:** Diverse interfacce utente che comunicano con il backend per visualizzare i dati e permettere l'interazione umana.
    -   **Web Dashboard (React):** L'interfaccia principale, accessibile via browser.
    -   **Applicazione Desktop (Electron):** Un'applicazione nativa per Windows/macOS/Linux che "impacchetta" la Web Dashboard per un'esperienza integrata.
    -   **Applicazione Mobile (Flutter):** Un'app per iOS e Android per il monitoraggio del portafoglio in mobilità.

---

## 2. Funzionamento del Backend

Il backend, situato in `backend/app`, è dove risiede tutta l'intelligenza e la logica operativa.

### Componenti Chiave:

-   **API Server (`main.py`):**
    -   Basato sul framework **FastAPI**, agisce come punto di ingresso principale per tutte le comunicazioni.
    -   Espone **endpoint API** per avviare/fermare il bot, recuperare lo stato del portafoglio, visualizzare i dati storici, testare le connessioni e modificare la configurazione.
    -   Orchestra il ciclo di vita dell'applicazione, avviando il loop di trading automatico (`ai_trading_loop`).

-   **Il Cervello IA (`core/cervello_ia.py`):**
    -   È il modulo decisionale. Utilizza una combinazione di analisi tecnica e strategie di momentum.
    -   **`analizza_mercato_e_genera_segnale`**: Analizza un singolo asset su più timeframe (es. 1h, 4h, 1g) usando indicatori tecnici come **SMA, RSI e MACD**. Assegna un punteggio di acquisto e di vendita e, se la soglia di confidenza viene superata, genera un segnale (`COMPRA`, `VENDI`, `MANTIENI`). In caso di acquisto, calcola anche il **prezzo di stop loss** a cui vendere per limitare le perdite.
    -   **`suggerisci_strategie_di_mercato`**: Scansiona l'intero mercato (es. le top 150 coin per volume) per identificare nuove opportunità. Valuta gli asset basandosi su un **punteggio di momentum** (performance a 7 e 30 giorni) e sull'RSI. Include una **regola di sicurezza** per scartare automaticamente asset con crescite anomale e rischiose (es. >100% in 7 giorni).

-   **Il Braccio Operativo (`core/gestore_operazioni.py`):**
    -   Agisce come intermediario tra la logica del bot e gli exchange di criptovalute, utilizzando la libreria `ccxt`.
    -   **`esegui_acquisto` / `esegui_vendita`**: Riceve gli ordini dal loop principale e li esegue concretamente sulla piattaforma (es. Binance).
    -   **Gestione Stop Loss**: Dopo un acquisto, è responsabile per il piazzamento immediato dell'**ordine di stop loss** sull'exchange, usando il prezzo calcolato dal "cervello". Questa è una funzione critica per la gestione del rischio.

-   **Gestione Stato e Configurazione:**
    -   **`config.json`**: File centrale che contiene tutte le impostazioni personalizzabili: chiavi API, budget, percentuali di rischio, strategie da attivare, ecc.
    -   **`data/portfolio_state.json`**: Un file JSON che funge da "database" semplice per salvare lo stato del portafoglio (budget corrente, quantità di ogni asset posseduto) e lo storico delle operazioni, garantendo la persistenza dei dati tra un riavvio e l'altro.

### Flusso Logico del Trading Automatico:

1.  All'avvio, il server API carica la configurazione e avvia il ciclo `ai_trading_loop` in `main.py`.
2.  Il ciclo determina quali asset analizzare, unendo quelli già posseduti con i nuovi suggerimenti dell'IA.
3.  Per ogni asset, invoca il "cervello" (`analizza_mercato_e_genera_segnale`) per ottenere un segnale.
4.  Se il segnale è **`COMPRA`**:
    a. Il loop calcola la **dimensione dell'operazione** in base al valore totale del portafoglio e alla `percentuale_rischio_per_operazione` impostata nel config.
    b. Chiama `esegui_acquisto` nel "braccio operativo".
    c. Il gestore operazioni piazza l'ordine di acquisto e, subito dopo, l'ordine di **stop loss** per proteggere la posizione.
5.  Se il segnale è **`VENDI`**, il loop chiama `esegui_vendita` per chiudere la posizione.
6.  Il ciclo attende per un intervallo di tempo configurabile (es. 5 minuti) e poi ricomincia.

---

## 3. Funzionamento dei Frontend

Tutti i frontend sono "client stupidi": la loro responsabilità principale è quella di presentare i dati forniti dal backend in modo chiaro e intuitivo.

-   **Dashboard Web (`frontend/dashboard`):**
    -   Realizzata con **React** e **Vite**, offre un'esperienza utente moderna e reattiva.
    -   Utilizza **Material-UI** per i componenti grafici e **Recharts/Lightweight Charts** per visualizzare i grafici dei prezzi e l'andamento del portafoglio.
    -   Comunica con il backend tramite chiamate API (con `axios`) per aggiornare dinamicamente le informazioni mostrate.

-   **Applicazione Desktop (`frontend/desktop`):**
    -   È basata su **Electron**. Essenzialmente, è un browser minimale che carica e visualizza la Dashboard Web come se fosse un'applicazione nativa, rendendola più comoda da usare.

-   **Applicazione Mobile (`frontend/tradeai_mobile_app`):**
    -   Sviluppata con **Flutter**, garantisce un'esperienza nativa e performante su iOS e Android.
    -   Implementa le schermate essenziali per il monitoraggio del portafoglio, la visualizzazione dei grafici e lo stato del bot, consumando gli stessi endpoint API del backend.

---



*Le versioni precedenti non sono documentate in questo file in quanto non è disponibile uno storico delle modifiche.*