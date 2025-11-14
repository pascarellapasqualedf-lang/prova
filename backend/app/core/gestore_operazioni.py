# Autore: Pascarella Pasquale Gerardo
# Versione: 1.0.0

import uuid
import ccxt.async_support as ccxt # Importa ccxt per operazioni reali
import json
import logging
from ..core.gestore_configurazione import carica_configurazione

from datetime import datetime # Aggiunto
from ..modelli.portafoglio import Portafoglio
from ..modelli.operazione import Operazione
from ..modelli.posizioni import PosizioneAperta # Aggiunto
from ..core.database import salva_operazione_db, recupera_operazioni_db, salva_evento_db, crea_notifica # Aggiunto crea_notifica
from ..core.gestore_configurazione import carica_configurazione # Aggiunto per risolvere NameError
from ..servizi.instance_manager import get_platform_instance # Importa il nuovo gestore di istanze

class GestorePortafoglio:
    """
    Gestisce lo stato e le operazioni di un portafoglio di trading.
    Lo stato viene inizializzato vuoto e poi popolato dalla riconciliazione con l'exchange.
    """
    def __init__(self):
        config = carica_configurazione()
        budget_iniziale = config['impostazioni_generali']['budget_totale_usd']
        operazioni_raw = recupera_operazioni_db()
        storico_operazioni = [Operazione(**op) for op in operazioni_raw]
        self.portafoglio = Portafoglio(
            budget_usd_iniziale=budget_iniziale,
            budget_usd_corrente=budget_iniziale, # Verrà sovrascritto dalla riconciliazione
            storico_operazioni=storico_operazioni
        )
        self.storico_valore_portafoglio = []
        logging.info("GestorePortafoglio inizializzato. In attesa di riconciliazione.")

    async def esegui_acquisto(self, piattaforma_id: str, coppia: str, quantita_da_comprare: float, prezzo: float, tipo_ordine: str = 'market', stop_loss_price: float = None):
        config = carica_configurazione()
        modalita_reale = config['impostazioni_generali']['modalita_reale_attiva']
        simbolo_base, simbolo_quotazione = coppia.split('/')
        controvalore = quantita_da_comprare * prezzo
        commissioni_usd = 0.0
        profitto_perdita_operazione = 0.0
        quantita_eseguita = 0.0
        prezzo_medio = 0.0
        take_profit_price = None

        if modalita_reale:
            logging.info(f"Esecuzione ACQUISTO REALE ({tipo_ordine.upper()}) di {quantita_da_comprare} {coppia} su {piattaforma_id}...")
            min_notional_from_config = config['impostazioni_generali']['min_buy_notional_usd']
            if controvalore < (min_notional_from_config - 0.0001):
                raise ValueError(f"Valore nozionale dell'ordine ({controvalore:.4f}) inferiore al minimo richiesto di {min_notional_from_config}")

            try:
                piattaforma_reale = get_platform_instance(piattaforma_id)
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
                crea_notifica(titolo=f"Acquisto Eseguito: {coppia}", messaggio=f"Acquistati {quantita_eseguita:.6f} di {simbolo_base} al prezzo di {prezzo_medio:.2f} USD.")

                trailing_sl_config = config.get('trailing_stop_loss', {})
                if trailing_sl_config.get('attiva') and quantita_eseguita > 0:
                    if stop_loss_price and stop_loss_price > 0:
                        logging.info(f"Piazzando ordine STOP LOSS STATICO per {quantita_eseguita} {coppia} a {stop_loss_price}...")
                        try:
                            params = {'stopPrice': stop_loss_price}
                            stop_loss_order = await piattaforma_reale.create_order(coppia, 'stop_loss', 'sell', quantita_eseguita, price=None, params=params)
                            salva_evento_db("PIAZZA_STOP_LOSS", piattaforma=piattaforma_id, coppia=coppia, dettagli=f"ID: {stop_loss_order['id']}")
                        except Exception as sl_error:
                            logging.warning(f"Errore durante il piazzamento dell'ordine stop loss statico: {sl_error}")
                
                percentuale_take_profit = config.get('parametri_ia', {}).get('percentuale_take_profit')
                if percentuale_take_profit and percentuale_take_profit > 0 and quantita_eseguita > 0:
                    take_profit_price = prezzo_medio * (1 + percentuale_take_profit / 100)
                    logging.info(f"Obiettivo Take Profit calcolato per {coppia}: {take_profit_price:.4f}")

            except ccxt.InsufficientFunds as e:
                logging.warning(f"Fondi insufficienti su {piattaforma_id} per {coppia}. Dettagli: {e}")
                raise e # Rilancia l'eccezione specifica per essere gestita nel loop principale

        else:
            quantita_eseguita = quantita_da_comprare
            prezzo_medio = prezzo

        self.portafoglio.budget_usd_corrente -= (quantita_eseguita * prezzo_medio) + commissioni_usd
        self.portafoglio.asset[simbolo_base] = self.portafoglio.asset.get(simbolo_base, 0) + quantita_eseguita
        tipo_operazione = f'acquisto_{"reale" if modalita_reale else "simulato"}_{tipo_ordine}'
        nuova_operazione = Operazione(id_operazione=str(uuid.uuid4()), piattaforma=piattaforma_id, coppia=coppia, tipo=tipo_operazione, quantita=quantita_eseguita, prezzo=prezzo_medio, controvalore_usd=(quantita_eseguita * prezzo_medio), commissioni_usd=commissioni_usd, profitto_perdita_operazione=profitto_perdita_operazione)
        salva_operazione_db(nuova_operazione, motivo_vendita=None)

        if simbolo_base in self.portafoglio.posizioni_aperte:
            pos = self.portafoglio.posizioni_aperte[simbolo_base]
            nuova_quantita_totale = pos.quantita + quantita_eseguita
            nuovo_prezzo_medio = ((pos.quantita * pos.prezzo_medio_acquisto) + (quantita_eseguita * prezzo_medio)) / nuova_quantita_totale
            pos.quantita = nuova_quantita_totale
            pos.prezzo_medio_acquisto = nuovo_prezzo_medio
            pos.commissioni_totali_acquisto += commissioni_usd
        else:
            self.portafoglio.posizioni_aperte[simbolo_base] = PosizioneAperta(coppia=coppia, quantita=quantita_eseguita, prezzo_medio_acquisto=prezzo_medio, commissioni_totali_acquisto=commissioni_usd, take_profit_price=take_profit_price)
        return nuova_operazione

    async def esegui_vendita(self, piattaforma_id: str, coppia: str, quantita_da_vendere: float, prezzo: float, tipo_ordine: str = 'market', motivo: str = 'SEGNALE_IA'):
        config = carica_configurazione()
        modalita_reale = config['impostazioni_generali']['modalita_reale_attiva']
        simbolo_base, simbolo_quotazione = coppia.split('/')
        controvalore = quantita_da_vendere * prezzo
        commissioni_usd = 0.0
        profitto_perdita_operazione = 0.0
        quantita_eseguita = 0.0
        prezzo_medio = 0.0

        if modalita_reale:
            try:
                piattaforma_reale = get_platform_instance(piattaforma_id)
                order = await piattaforma_reale.create_market_sell_order(coppia, quantita_da_vendere)
                quantita_eseguita = order['filled']
                prezzo_medio = order['average'] if order['average'] is not None else prezzo
                if 'fees' in order and isinstance(order['fees'], list):
                    for fee in order['fees']:
                        if 'cost' in fee and isinstance(fee['cost'], (int, float)):
                            commissioni_usd += fee['cost']
                
                # Calcola il profitto PRIMA di inviare la notifica
                if simbolo_base in self.portafoglio.posizioni_aperte:
                    pos = self.portafoglio.posizioni_aperte[simbolo_base]
                    costo_acquisto = pos.prezzo_medio_acquisto * quantita_eseguita
                    ricavo_vendita = (quantita_eseguita * prezzo_medio) - commissioni_usd
                    profitto_perdita_operazione = ricavo_vendita - costo_acquisto
                    logging.info(f"Calcolo P/L per {coppia}: Ricavo={ricavo_vendita:.2f}, Costo={costo_acquisto:.2f}, P/L={profitto_perdita_operazione:.2f}")
                else:
                    profitto_perdita_operazione = (quantita_eseguita * prezzo_medio) - commissioni_usd # Non si può calcolare il P/L reale senza posizione

                logging.info(f"VENDITA REALE completata: {quantita_eseguita} {coppia} a {prezzo_medio}. Commissioni: {commissioni_usd}")
                crea_notifica(
                    titolo=f"Vendita Eseguita: {coppia}",
                    messaggio=f"Venduti {quantita_eseguita:.6f} di {simbolo_base} a {prezzo_medio:.2f}. P/L: {profitto_perdita_operazione:.2f} USD"
                )
            except Exception as e:
                logging.error(f"Errore durante l'esecuzione della vendita reale per {coppia}: {e}", exc_info=True)
                # Non rilanciare l'eccezione per non bloccare l'aggiornamento dello stato sottostante
                # ma assicurati che la quantità eseguita sia zero se l'ordine fallisce.
                quantita_eseguita = 0
                prezzo_medio = prezzo # Fallback al prezzo di mercato stimato
                profitto_perdita_operazione = 0

        else:
            quantita_eseguita = quantita_da_vendere
            prezzo_medio = prezzo

        if simbolo_base in self.portafoglio.posizioni_aperte:
            pos = self.portafoglio.posizioni_aperte[simbolo_base]
            costo_acquisto_proporzionale = (quantita_eseguita / pos.quantita) * (pos.quantita * pos.prezzo_medio_acquisto + pos.commissioni_totali_acquisto)
            profitto_perdita_operazione = (quantita_eseguita * prezzo_medio) - commissioni_usd - costo_acquisto_proporzionale
            
            # Calcola la percentuale di profitto/perdita
            if costo_acquisto_proporzionale > 0:
                percentuale_profitto_perdita = (profitto_perdita_operazione / costo_acquisto_proporzionale) * 100
            else:
                percentuale_profitto_perdita = 0.0

            pos.quantita -= quantita_eseguita
            if pos.quantita <= 1e-9:
                del self.portafoglio.posizioni_aperte[simbolo_base]
        else:
            profitto_perdita_operazione = (quantita_eseguita * prezzo_medio) - commissioni_usd
            percentuale_profitto_perdita = 0.0 # Non possiamo calcolare la percentuale senza un costo di acquisto

        self.portafoglio.profitto_perdita_totale_usd += profitto_perdita_operazione
        self.portafoglio.budget_usd_corrente += (quantita_eseguita * prezzo_medio) - commissioni_usd
        self.portafoglio.asset[simbolo_base] -= quantita_eseguita

        tipo_operazione = f'vendita_{"reale" if modalita_reale else "simulata"}_{tipo_ordine}'
        nuova_operazione = Operazione(id_operazione=str(uuid.uuid4()), piattaforma=piattaforma_id, coppia=coppia, tipo=tipo_operazione, quantita=quantita_eseguita, prezzo=prezzo_medio, controvalore_usd=(quantita_eseguita * prezzo_medio), commissioni_usd=commissioni_usd, profitto_perdita_operazione=profitto_perdita_operazione, percentuale_profitto_perdita=percentuale_profitto_perdita)
        salva_operazione_db(nuova_operazione, motivo_vendita=motivo)
        return nuova_operazione

    def ottieni_stato_portafoglio(self):
        return self.portafoglio

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
        from .prezzi_cache import aggiorna_prezzi_cache, get_prezzo_cache
        config = carica_configurazione()
        piattaforme_config = config['piattaforme']
        liquid_stablecoin_balance = 0.0
        reconciled_assets = {}
        all_assets_to_fetch_price = set()
        stablecoins = ['USDT', 'BUSD', 'USDC', 'DAI', 'EUR']
        logging.info("--- Inizio Riconciliazione Saldi con Exchange ---")
        for nome_piattaforma, conf_piattaforma in piattaforme_config.items():
            if not conf_piattaforma.get('attiva') or nome_piattaforma == '_comment':
                continue
            try:
                piattaforma_ccxt = get_platform_instance(nome_piattaforma)
                balance = await piattaforma_ccxt.fetch_balance()
                all_balances = balance.get('total', {}) # Usiamo il saldo totale (free + used)
                logging.debug(f"Saldi totali da {nome_piattaforma}: {all_balances}")
                for asset, amount in all_balances.items():
                    if amount > 0:
                        if asset.upper() in stablecoins:
                            liquid_stablecoin_balance += amount
                        else:
                            reconciled_assets[asset] = reconciled_assets.get(asset, 0) + amount
                            all_assets_to_fetch_price.add(asset)
            except Exception as e:
                logging.error(f"Impossibile riconciliare i saldi con {nome_piattaforma}: {e}")

        logging.info(f"Stablecoin liquide totali: {liquid_stablecoin_balance:.2f} USD")

        if all_assets_to_fetch_price:
            try:
                first_active_platform_name = next((p for p, conf in piattaforme_config.items() if p != '_comment' and conf.get('attiva')), None)
                quote_currency_for_cache = "USDT"
                if first_active_platform_name:
                    first_active_platform_conf = piattaforme_config.get(first_active_platform_name)
                    quote_currency_for_cache = first_active_platform_conf.get('options', {}).get('quote_currency', 'USDT')
                    piattaforma_cache = get_platform_instance(first_active_platform_name)
                    await aggiorna_prezzi_cache(piattaforma_cache, list(all_assets_to_fetch_price), quote_currency_for_cache)
            except Exception as e:
                logging.error(f"Errore durante l'aggiornamento prezzi per riconciliazione: {e}")

        crypto_assets_value_usd = 0.0
        for asset, quantita in reconciled_assets.items():
            prezzo = get_prezzo_cache(asset, quote_currency_for_cache)
            if prezzo is not None:
                valore_asset = quantita * prezzo
                crypto_assets_value_usd += valore_asset
                logging.info(f"  - Asset: {asset}, Quantità: {quantita}, Prezzo: {prezzo:.4f}, Valore: {valore_asset:.2f} USD")
            else:
                logging.warning(f"Prezzo per {asset} non disponibile. L'asset non sarà incluso nel valore totale del portafoglio.")

        total_reconciled_value_usd = liquid_stablecoin_balance + crypto_assets_value_usd

        self.portafoglio.asset = reconciled_assets
        self.portafoglio.budget_usd_corrente = total_reconciled_value_usd
        
        if self.portafoglio.budget_usd_iniziale == 0 or self.portafoglio.budget_usd_iniziale == config['impostazioni_generali']['budget_totale_usd']:
            self.portafoglio.budget_usd_iniziale = total_reconciled_value_usd
            logging.info(f"Budget INIZIALE del portafoglio impostato a: {total_reconciled_value_usd:.2f} USD")

        logging.info(f"Valore Totale Riconciliato: {total_reconciled_value_usd:.2f} USD")
        logging.info(f"--- Fine Riconciliazione Saldi ---")

gestore_globale_portafoglio = GestorePortafoglio()