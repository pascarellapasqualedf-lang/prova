# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import uuid
import ccxt.async_support as ccxt # Importa ccxt per operazioni reali
import json
import logging
from datetime import datetime # Aggiunto
from ..modelli.portafoglio import Portafoglio
from ..modelli.operazione import Operazione
from ..modelli.posizioni import PosizioneAperta # Aggiunto
from ..core.gestore_configurazione import carica_configurazione
from ..servizi.gestore_piattaforme import inizializza_piattaforma # Importa per inizializzare piattaforme reali

class GestorePortafoglio:
    """
    Gestisce lo stato e le operazioni di un portafoglio di trading virtuale.
    """
    def __init__(self):
        self.file_stato = "data/portfolio_state.json"
        self.portafoglio = None
        self.storico_valore_portafoglio = []
        self.load_state()

    def load_state(self):
        config = carica_configurazione()
        try:
            with open(self.file_stato, 'r') as f:
                data = json.load(f)
                self.portafoglio = Portafoglio(**data['portafoglio'])
                self.storico_valore_portafoglio = data.get('storico_valore_portafoglio', [])
            logging.info(f"Stato del portafoglio caricato da {self.file_stato}.")
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logging.warning(f"File di stato '{self.file_stato}' non trovato o corrotto ({e}). Inizializzo un nuovo portafoglio.")
            budget_iniziale = config['impostazioni_generali']['budget_totale_usd']
            self.portafoglio = Portafoglio(
                budget_usd_iniziale=budget_iniziale,
                budget_usd_corrente=budget_iniziale
            )
            self.storico_valore_portafoglio = []

        # Sincronizza gli asset dal config al portafoglio
        cripto_preferite = config.get('parametri_ia', {}).get('cripto_preferite', [])
        asset_aggiunti = False
        for asset in cripto_preferite:
            if asset not in self.portafoglio.asset:
                self.portafoglio.asset[asset] = 0.0
                asset_aggiunti = True
                logging.info(f"Nuovo asset '{asset}' da config.json aggiunto al portafoglio con saldo 0.")
        
        if asset_aggiunti:
            logging.info("Il portafoglio è stato aggiornato con nuovi asset dalla configurazione.")
        
        logging.debug(f"Asset nel portafoglio dopo la sincronizzazione: {list(self.portafoglio.asset.keys())}")

    def save_state(self):
        try:
            with open(self.file_stato, 'w') as f:
                data = {
                    'portafoglio': self.portafoglio.dict(),
                    'storico_valore_portafoglio': self.storico_valore_portafoglio
                }
                json.dump(data, f, indent=4)
            logging.debug(f"Stato del portafoglio salvato con successo in {self.file_stato}.")
        except Exception as e:
            logging.error(f"Errore durante il salvataggio dello stato in {self.file_stato}: {e}")

    async def esegui_acquisto(self, piattaforma_id: str, coppia: str, quantita_da_comprare: float, prezzo: float, tipo_ordine: str = 'market', stop_loss_price: float = None):
        config = carica_configurazione()
        modalita_reale = config['impostazioni_generali']['modalita_reale_attiva']
        simbolo_base, simbolo_quotazione = coppia.split('/')
        controvalore = quantita_da_comprare * prezzo
        commissioni_usd = 0.0
        profitto_perdita_operazione = 0.0
        quantita_eseguita = 0.0
        prezzo_medio = 0.0

        if modalita_reale:
            logging.info(f"Esecuzione ACQUISTO REALE ({tipo_ordine.upper()}) di {quantita_da_comprare} {coppia} su {piattaforma_id}...")
            min_notional_from_config = config['impostazioni_generali']['min_buy_notional_usd']
            if controvalore < min_notional_from_config:
                raise ValueError(f"Valore nozionale dell'ordine ({controvalore:.4f}) inferiore al minimo richiesto di {min_notional_from_config}")

            piattaforma_reale = None
            try:
                piattaforma_reale = inizializza_piattaforma(piattaforma_id)
                order = None
                if tipo_ordine == 'market':
                    order = await piattaforma_reale.create_market_buy_order(coppia, quantita_da_comprare)
                elif tipo_ordine == 'limit':
                    if prezzo is None or prezzo <= 0:
                        raise ValueError("Prezzo limite non valido per ordine LIMIT.")
                    order = await piattaforma_reale.create_limit_buy_order(coppia, quantita_da_comprare, prezzo)
                else:
                    raise ValueError(f"Tipo di ordine non supportato: {tipo_ordine}")
                
                quantita_eseguita = order['filled']
                prezzo_medio = order['average'] if order['average'] is not None else prezzo
                if 'fees' in order and isinstance(order['fees'], list):
                    for fee in order['fees']:
                        if 'cost' in fee and isinstance(fee['cost'], (int, float)):
                            commissioni_usd += fee['cost']
                logging.info(f"ACQUISTO REALE completato: {quantita_eseguita} {coppia} a {prezzo_medio}. Commissioni: {commissioni_usd}")

                trailing_sl_config = config.get('trailing_stop_loss', {})
                if stop_loss_price and stop_loss_price > 0 and quantita_eseguita > 0:
                    logging.info(f"Piazzando ordine STOP LOSS STATICO per {quantita_eseguita} {coppia} a {stop_loss_price}...")
                    try:
                        params = {'stopPrice': stop_loss_price}
                        stop_loss_order = await piattaforma_reale.create_order(coppia, 'stop_loss', 'sell', quantita_eseguita, price=None, params=params)
                        logging.info(f"Ordine STOP LOSS STATICO piazzato con successo: ID {stop_loss_order['id']}")
                    except Exception as sl_error:
                        logging.warning(f"Errore durante il piazzamento dell'ordine stop loss statico: {sl_error}")
                elif trailing_sl_config.get('attiva') and quantita_eseguita > 0:
                    distanza_perc = trailing_sl_config.get('percentuale_distanza')
                    if distanza_perc is not None and distanza_perc > 0:
                        logging.info(f"Piazzando ordine TRAILING STOP LOSS per {quantita_eseguita} {coppia} con una distanza del {distanza_perc}%")
                        try:
                            activation_price = prezzo_medio * (1 - distanza_perc / 100)
                            params = { 'trailing': True, 'stopPrice': activation_price }
                            trailing_order = await piattaforma_reale.create_order(coppia, 'stop_loss', 'sell', quantita_eseguita, price=None, params=params)
                            logging.info(f"Ordine TRAILING STOP LOSS piazzato con successo: ID {trailing_order['id']}")
                        except Exception as tsl_error:
                            logging.warning(f"Errore durante il piazzamento dell'ordine trailing stop loss: {tsl_error}. Verificare se la piattaforma supporta questa funzione.")

            except ccxt.BadRequest as e:
                if 'NOTIONAL' in str(e):
                    logging.error(f"Acquisto per {coppia} non eseguito: valore nozionale troppo piccolo.")
                    return None
                else:
                    raise ValueError(f"Errore di richiesta (BadRequest) dall'exchange {piattaforma_id}: {e}")
            except ccxt.InsufficientFunds as e:
                raise ValueError(f"Fondi insufficienti sulla piattaforma {piattaforma_id}: {e}")
            except ccxt.NetworkError as e:
                raise ValueError(f"Errore di rete con la piattaforma {piattaforma_id}: {e}")
            except ccxt.ExchangeError as e:
                raise ValueError(f"Errore dell'exchange {piattaforma_id}: {e}")
            except Exception as e:
                raise ValueError(f"Errore sconosciuto durante l'acquisto reale su {piattaforma_id}: {e}")
            finally:
                if piattaforma_reale:
                    await piattaforma_reale.close()

        else: # Modalità simulata
            logging.info(f"Esecuzione ACQUISTO SIMULATO ({tipo_ordine.upper()}) di {quantita_da_comprare} {coppia} su {piattaforma_id}...")
            if tipo_ordine == 'limit' and (prezzo is None or prezzo <= 0):
                raise ValueError("Prezzo limite non valido per ordine LIMIT simulato.")
            if self.portafoglio.budget_usd_corrente < controvalore:
                raise ValueError("Budget insufficiente per eseguire l'acquisto simulato.")
            quantita_eseguita = quantita_da_comprare
            prezzo_medio = prezzo

        self.portafoglio.budget_usd_corrente -= (quantita_eseguita * prezzo_medio) + commissioni_usd
        self.portafoglio.asset[simbolo_base] = self.portafoglio.asset.get(simbolo_base, 0) + quantita_eseguita
        nuova_operazione = Operazione(
            id_operazione=str(uuid.uuid4()),
            piattaforma=piattaforma_id,
            coppia=coppia,
            tipo=f'acquisto_{"reale" if modalita_reale else "simulato"}_{tipo_ordine}',
            quantita=quantita_eseguita,
            prezzo=prezzo_medio,
            controvalore_usd=(quantita_eseguita * prezzo_medio),
            commissioni_usd=commissioni_usd,
            profitto_perdita_operazione=profitto_perdita_operazione
        )
        self.portafoglio.storico_operazioni.append(nuova_operazione)

        if simbolo_base in self.portafoglio.posizioni_aperte:
            pos = self.portafoglio.posizioni_aperte[simbolo_base]
            nuova_quantita_totale = pos.quantita + quantita_eseguita
            nuovo_prezzo_medio = ((pos.quantita * pos.prezzo_medio_acquisto) + (quantita_eseguita * prezzo_medio)) / nuova_quantita_totale
            pos.quantita = nuova_quantita_totale
            pos.prezzo_medio_acquisto = nuovo_prezzo_medio
            pos.commissioni_totali_acquisto += commissioni_usd
        else:
            self.portafoglio.posizioni_aperte[simbolo_base] = PosizioneAperta(
                coppia=coppia,
                quantita=quantita_eseguita,
                prezzo_medio_acquisto=prezzo_medio,
                commissioni_totali_acquisto=commissioni_usd
            )
        logging.debug(f"Posizioni aperte dopo acquisto: {self.portafoglio.posizioni_aperte}")
        return nuova_operazione

    async def esegui_vendita(self, piattaforma_id: str, coppia: str, quantita_da_vendere: float, prezzo: float, tipo_ordine: str = 'market'):
        config = carica_configurazione()
        modalita_reale = config['impostazioni_generali']['modalita_reale_attiva']
        simbolo_base, simbolo_quotazione = coppia.split('/')
        controvalore = quantita_da_vendere * prezzo
        commissioni_usd = 0.0
        profitto_perdita_operazione = 0.0
        quantita_eseguita = 0.0
        prezzo_medio = 0.0

        if modalita_reale:
            logging.info(f"Esecuzione VENDITA REALE ({tipo_ordine.upper()}) di {quantita_da_vendere} {coppia} su {piattaforma_id}...")
            min_notional_from_config = config['impostazioni_generali']['min_sell_notional_usd']
            if controvalore < min_notional_from_config:
                raise ValueError(f"Valore nozionale dell'ordine ({controvalore:.4f}) inferiore al minimo richiesto di {min_notional_from_config}")

            piattaforma_reale = None
            try:
                piattaforma_reale = inizializza_piattaforma(piattaforma_id)
                order = None
                if tipo_ordine == 'market':
                    order = await piattaforma_reale.create_market_sell_order(coppia, quantita_da_vendere)
                elif tipo_ordine == 'limit':
                    if prezzo is None or prezzo <= 0:
                        raise ValueError("Prezzo limite non valido per ordine LIMIT.")
                    order = await piattaforma_reale.create_limit_sell_order(coppia, quantita_da_vendere, prezzo)
                else:
                    raise ValueError(f"Tipo di ordine non supportato: {tipo_ordine}")
                
                quantita_eseguita = order['filled']
                prezzo_medio = order['average'] if order['average'] is not None else prezzo
                if 'fees' in order and isinstance(order['fees'], list):
                    for fee in order['fees']:
                        if 'cost' in fee and isinstance(fee['cost'], (int, float)):
                            commissioni_usd += fee['cost']
                logging.info(f"VENDITA REALE completata: {quantita_eseguita} {coppia} a {prezzo_medio}. Commissioni: {commissioni_usd}")

                if simbolo_base in self.portafoglio.posizioni_aperte:
                    pos = self.portafoglio.posizioni_aperte[simbolo_base]
                    costo_acquisto_proporzionale = (quantita_eseguita / pos.quantita) * (pos.quantita * pos.prezzo_medio_acquisto + pos.commissioni_totali_acquisto)
                    profitto_perdita_operazione = (quantita_eseguita * prezzo_medio) - commissioni_usd - costo_acquisto_proporzionale
                else:
                    profitto_perdita_operazione = (quantita_eseguita * prezzo_medio) - commissioni_usd

            except ccxt.BadRequest as e:
                if 'NOTIONAL' in str(e):
                    logging.error(f"Vendita per {coppia} non eseguita: valore nozionale troppo piccolo.")
                    return None
                else:
                    raise ValueError(f"Errore di richiesta (BadRequest) dall'exchange {piattaforma_id}: {e}")
            except ccxt.InsufficientFunds as e:
                raise ValueError(f"Fondi insufficienti sulla piattaforma {piattaforma_id}: {e}")
            except ccxt.NetworkError as e:
                raise ValueError(f"Errore di rete con la piattaforma {piattaforma_id}: {e}")
            except ccxt.ExchangeError as e:
                raise ValueError(f"Errore dell'exchange {piattaforma_id}: {e}")
            except Exception as e:
                raise ValueError(f"Errore sconosciuto durante la vendita reale su {piattaforma_id}: {e}")
            finally:
                if piattaforma_reale:
                    await piattaforma_reale.close()

        else: # Modalità simulata
            logging.info(f"Esecuzione VENDITA SIMULATA ({tipo_ordine.upper()}) di {quantita_da_vendere} {coppia} su {piattaforma_id}...")
            if tipo_ordine == 'limit' and (prezzo is None or prezzo <= 0):
                raise ValueError("Prezzo limite non valido per ordine LIMIT simulato.")
            if self.portafoglio.asset.get(simbolo_base, 0) < quantita_da_vendere:
                raise ValueError(f"Quantità di {simbolo_base} insufficiente per eseguire la vendita simulata.")
            quantita_eseguita = quantita_da_vendere
            prezzo_medio = prezzo

            if simbolo_base in self.portafoglio.posizioni_aperte:
                pos = self.portafoglio.posizioni_aperte[simbolo_base]
                costo_acquisto_proporzionale = (quantita_da_vendere / pos.quantita) * (pos.quantita * pos.prezzo_medio_acquisto + pos.commissioni_totali_acquisto)
                profitto_perdita_operazione = controvalore - costo_acquisto_proporzionale
            else:
                profitto_perdita_operazione = controvalore

        self.portafoglio.profitto_perdita_totale_usd += profitto_perdita_operazione
        self.portafoglio.budget_usd_corrente += (quantita_eseguita * prezzo_medio) - commissioni_usd
        self.portafoglio.asset[simbolo_base] -= quantita_eseguita

        nuova_operazione = Operazione(
            id_operazione=str(uuid.uuid4()),
            piattaforma=piattaforma_id,
            coppia=coppia,
            tipo=f'vendita_{"reale" if modalita_reale else "simulata"}_{tipo_ordine}',
            quantita=quantita_eseguita,
            prezzo=prezzo_medio,
            controvalore_usd=(quantita_eseguita * prezzo_medio),
            commissioni_usd=commissioni_usd,
            profitto_perdita_operazione=profitto_perdita_operazione
        )
        self.portafoglio.storico_operazioni.append(nuova_operazione)

        if simbolo_base in self.portafoglio.posizioni_aperte:
            pos = self.portafoglio.posizioni_aperte[simbolo_base]
            pos.quantita -= quantita_eseguita
            if pos.quantita <= 0.000001: # Usa una piccola soglia per evitare problemi di precisione float
                del self.portafoglio.posizioni_aperte[simbolo_base]
        logging.debug(f"Posizioni aperte dopo vendita: {self.portafoglio.posizioni_aperte}")
        return nuova_operazione

    def ottieni_stato_portafoglio(self):
        return self.portafoglio

    async def _registra_valore_portafoglio(self):
        from .prezzi_cache import get_prezzo_cache, aggiorna_prezzi_cache
        from ..servizi.gestore_piattaforme import inizializza_piattaforma
        config = carica_configurazione()
        piattaforme_config = config['piattaforme']
        first_active_platform_name = next((p for p, conf in piattaforme_config.items() if p != '_comment' and conf.get('attiva')), None)
        quote_currency = "USDT"
        if first_active_platform_name:
            first_active_platform_conf = piattaforme_config.get(first_active_platform_name)
            quote_currency = first_active_platform_conf.get('options', {}).get('quote_currency', 'USDT')

        assets_posseduti = [asset for asset, quantita in self.portafoglio.asset.items() if quantita > 0 and asset.upper() not in ['USDT', 'BUSD', 'USDC', 'DAI', 'EUR']]
        if assets_posseduti:
            try:
                if first_active_platform_name:
                    piattaforma_ccxt = inizializza_piattaforma(first_active_platform_name)
                    await aggiorna_prezzi_cache(piattaforma_ccxt, assets_posseduti, quote_currency)
                    await piattaforma_ccxt.close()
                    logging.debug(f"Cache prezzi aggiornata per: {assets_posseduti} usando {first_active_platform_name} con {quote_currency}")
                else:
                    logging.warning("Nessuna piattaforma attiva trovata per aggiornare la cache prezzi per il calcolo storico.")
            except Exception as e:
                logging.warning(f"Errore durante l'aggiornamento della cache prezzi per il calcolo storico: {e}")

        valore_totale = self.portafoglio.budget_usd_corrente
        for asset, quantita in self.portafoglio.asset.items():
            if quantita > 0:
                if asset.upper() in ['USDT', 'BUSD', 'USDC', 'DAI', 'EUR']:
                    valore_totale += quantita
                else:
                    prezzo = get_prezzo_cache(asset, quote_currency)
                    if prezzo is not None:
                        valore_asset = quantita * prezzo
                        valore_totale += valore_asset
                        logging.debug(f"Asset {asset}: Quantità={quantita}, Prezzo={prezzo}, Valore={valore_asset}")
                    else:
                        logging.warning(f"Prezzo per {asset} non disponibile in cache per calcolo storico valore. Usando 0 per questo asset.")

        self.storico_valore_portafoglio.append({
            "timestamp": datetime.now().isoformat(),
            "valore_usd": valore_totale
        })
        logging.debug(f"Valore portafoglio registrato: {valore_totale}")

    def ottieni_storico_valore_portafoglio(self):
        return self.storico_valore_portafoglio
    
    def calcola_report_performance(self):
        profitto_perdita_totale = 0.0
        operazioni_vincenti = 0
        operazioni_perdenti = 0
        for op in self.portafoglio.storico_operazioni:
            if 'vendita' in op.tipo:
                profitto_perdita_totale += op.profitto_perdita_operazione
                if op.profitto_perdita_operazione > 0:
                    operazioni_vincenti += 1
                elif op.profitto_perdita_operazione < 0:
                    operazioni_perdenti += 1
        numero_totale_operazioni = len(self.portafoglio.storico_operazioni)
        percentuale_profitto = (profitto_perdita_totale / self.portafoglio.budget_usd_iniziale) * 100 if self.portafoglio.budget_usd_iniziale > 0 else 0
        return {
            "profitto_perdita_totale_usd": profitto_perdita_totale,
            "percentuale_profitto": percentuale_profitto,
            "operazioni_vincenti": operazioni_vincenti,
            "operazioni_perdenti": operazioni_perdenti,
            "numero_totale_operazioni": numero_totale_operazioni
        }

    def get_analisi_operazioni(self):
        analisi_per_tipo = {}
        analisi_per_coppia = {}
        analisi_per_piattaforma = {}
        for op in self.portafoglio.storico_operazioni:
            analisi_per_tipo[op.tipo] = analisi_per_tipo.get(op.tipo, 0) + 1
            analisi_per_coppia[op.coppia] = analisi_per_coppia.get(op.coppia, 0) + op.controvalore_usd
            analisi_per_piattaforma[op.piattaforma] = analisi_per_piattaforma.get(op.piattaforma, 0) + op.controvalore_usd
        return {
            "operazioni_per_tipo": analisi_per_tipo,
            "controvalore_per_coppia": analisi_per_coppia,
            "controvalore_per_piattaforma": analisi_per_piattaforma,
        }

    async def reconcile_balances_with_exchange(self):
        from ..core.gestore_configurazione import carica_configurazione
        from ..servizi.gestore_piattaforme import inizializza_piattaforma
        from .prezzi_cache import aggiorna_prezzi_cache, get_prezzo_cache
        config = carica_configurazione()
        piattaforme_config = config['piattaforme']
        liquid_stablecoin_balance = 0.0
        reconciled_assets = {}
        all_assets_to_fetch_price = set()
        stablecoins = ['USDT', 'BUSD', 'USDC', 'DAI', 'EUR']
        logging.debug("Inizio riconciliazione saldi con exchange...")
        for nome_piattaforma, conf_piattaforma in piattaforme_config.items():
            if not conf_piattaforma.get('attiva') or nome_piattaforma == '_comment':
                continue
            piattaforma_ccxt = None
            try:
                piattaforma_ccxt = inizializza_piattaforma(nome_piattaforma)
                balance = await piattaforma_ccxt.fetch_balance()
                all_balances = {}
                for asset, amount in balance.get('free', {}).items():
                    all_balances[asset] = all_balances.get(asset, 0.0) + float(amount)
                for asset, amount in balance.get('used', {}).items():
                    all_balances[asset] = all_balances.get(asset, 0.0) + float(amount)
                logging.debug(f"Saldi grezzi da {nome_piattaforma}: {all_balances}\n")
                for asset, amount in all_balances.items():
                    if amount > 0:
                        if asset.upper() in stablecoins:
                            liquid_stablecoin_balance += amount
                        else:
                            reconciled_assets[asset] = reconciled_assets.get(asset, 0) + amount
                            all_assets_to_fetch_price.add(asset)
            except Exception as e:
                logging.error(f"Impossibile riconciliare i saldi con {nome_piattaforma}: {e}")
            finally:
                if piattaforma_ccxt:
                    await piattaforma_ccxt.close()
        if all_assets_to_fetch_price:
            try:
                first_active_platform_name = next((p for p, conf in piattaforme_config.items() if p != '_comment' and conf.get('attiva')), None)
                quote_currency_for_cache = "USDT"
                if first_active_platform_name:
                    first_active_platform_conf = piattaforme_config.get(first_active_platform_name)
                    quote_currency_for_cache = first_active_platform_conf.get('options', {}).get('quote_currency', 'USDT')
                if first_active_platform_name:
                    piattaforma_cache = inizializza_piattaforma(first_active_platform_name)
                    await aggiorna_prezzi_cache(piattaforma_cache, list(all_assets_to_fetch_price), quote_currency_for_cache)
                    await piattaforma_cache.close()
            except Exception as e:
                logging.error(f"Errore durante l'aggiornamento prezzi per riconciliazione: {e}")

        cripto_preferite = config.get('parametri_ia', {}).get('cripto_preferite', [])
        for asset in cripto_preferite:
            if asset not in reconciled_assets:
                reconciled_assets[asset] = 0.0
                logging.debug(f"Aggiunto asset preferito '{asset}' al portafoglio con saldo 0.")

        self.portafoglio.asset = reconciled_assets
        self.portafoglio.budget_usd_corrente = liquid_stablecoin_balance
        logging.debug(f"Riconciliazione completata. Portafoglio: Asset={self.portafoglio.asset}, Budget Corrente={self.portafoglio.budget_usd_corrente}")

gestore_globale_portafoglio = GestorePortafoglio()
