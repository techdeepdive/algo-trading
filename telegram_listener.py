import json
import requests
import time
import threading
from Dhan_Tradehull import Tradehull
import logging

logger = logging.getLogger(__name__)

_tg_thread = None
_tg_running = False

def send_alert_with_buttons(bot_token, chat_id, text, symbol, ltp):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🚀 EXECUTE SPREAD (BUY LIMIT)", "callback_data": f"EXECUTE_{symbol}_{ltp}"}
                ],
                [
                    {"text": "⚪ IGNORE", "callback_data": f"IGNORE_{symbol}_{ltp}"}
                ]
            ]
        }
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send telegram button alert: {e}")

def telegram_polling_loop(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat):
    global _tg_running
    offset = 0
    
    # Init Tradehull instance for telegram orders
    tsl = None
    try:
        tsl = Tradehull(client_id, access_token, mode="access_token")
        if not hasattr(tsl, 'Dhan'):
            raise Exception("Tradehull initialization failed silently.")
            
        import os, pandas as pd
        if os.path.exists('api-scrip-master.csv'):
            tsl.instrument_df = pd.read_csv('api-scrip-master.csv', low_memory=False)
            
        df = tsl.instrument_df
        nse_eq = df[(df['SEM_EXM_EXCH_ID'] == 'NSE') & (df['SEM_SEGMENT'] == 'E')]
        nse_other = df[(df['SEM_EXM_EXCH_ID'] == 'NSE') & (df['SEM_SEGMENT'] != 'E')]
        dups = set(nse_eq['SEM_SMST_SECURITY_ID']).intersection(set(nse_other['SEM_SMST_SECURITY_ID']))
        corrupt_symbols = set(nse_eq[nse_eq['SEM_SMST_SECURITY_ID'].isin(dups)]['SEM_TRADING_SYMBOL'])
    except Exception as e:
        logger.error(f"Failed to init Tradehull for Telegram bot: {e}")
        return

    while _tg_running:
        try:
            url = f"https://api.telegram.org/bot{tg_bot}/getUpdates?offset={offset}&timeout=30"
            resp = requests.get(url, timeout=35)
            if resp.status_code != 200:
                time.sleep(2)
                continue
                
            data = resp.json()
            if not data.get("ok"):
                time.sleep(2)
                continue
                
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                
                if "callback_query" in update:
                    cb = update["callback_query"]
                    cb_id = cb["id"]
                    msg_id = cb["message"]["message_id"]
                    chat_id = cb["message"]["chat"]["id"]
                    action_data = cb["data"]
                    
                    if str(chat_id) != str(tg_chat):
                        continue
                        
                    # Acknowledge the button click so it stops loading
                    requests.post(f"https://api.telegram.org/bot{tg_bot}/answerCallbackQuery", json={"callback_query_id": cb_id})
                    
                    logger.info(f"Telegram Button Clicked: {action_data}")
                    if action_data.startswith("IGNORE"):
                        requests.post(f"https://api.telegram.org/bot{tg_bot}/editMessageText", json={
                            "chat_id": chat_id,
                            "message_id": msg_id,
                            "text": cb["message"]["text"] + "\n\n🚫 Ignored."
                        })
                        continue
                        
                    parts = action_data.split('_')
                    if len(parts) >= 3:
                        action = parts[0]
                        symbol = parts[1]
                        trade_id = int(float(parts[2]))
                        
                        requests.post(f"https://api.telegram.org/bot{tg_bot}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": f"⚙️ Executing Spread for {symbol} (Trade ID: {trade_id}) via AlgoScan..."
                        })
                        
                        logger.info(f"Executing Telegram Spread Order: {symbol} (ID: {trade_id})")
                        try:
                            import sqlite3
                            conn = sqlite3.connect("algo_lab.db")
                            cursor = conn.cursor()
                            cursor.execute("SELECT leg1_symbol, leg2_symbol, lot_size FROM paper_trades WHERE id=?", (trade_id,))
                            row = cursor.fetchone()
                            conn.close()
                            
                            if not row:
                                raise Exception(f"Trade ID {trade_id} not found in DB.")
                                
                            leg1_sym, leg2_sym, lot_size = row
                            
                            opt_ltps = tsl.get_ltp_data(names=[leg1_sym, leg2_sym])
                            leg1_ltp = opt_ltps.get(leg1_sym)
                            leg2_ltp = opt_ltps.get(leg2_sym)
                            
                            if not leg1_ltp or not leg2_ltp:
                                raise Exception(f"Could not fetch live prices for {leg1_sym} or {leg2_sym}")
                                
                            # Execute BUY Leg (Leg 2) FIRST for margin benefit
                            # Limit price slightly above LTP for instant execution
                            leg2_limit = round(leg2_ltp * 1.02, 1)
                            logger.info(f"Firing BUY Leg: {leg2_sym} at {leg2_limit}")
                            order1_id = tsl.order_placement(
                                tradingsymbol=leg2_sym,
                                exchange="NFO",
                                quantity=lot_size,
                                price=leg2_limit,
                                trigger_price=0,
                                order_type="LIMIT",
                                transaction_type="BUY",
                                trade_type="MARGIN"
                            )
                            time.sleep(1)
                            
                            # Execute SELL Leg (Leg 1) SECOND
                            # Limit price slightly below LTP for instant execution
                            leg1_limit = round(leg1_ltp * 0.98, 1)
                            logger.info(f"Firing SELL Leg: {leg1_sym} at {leg1_limit}")
                            order2_id = tsl.order_placement(
                                tradingsymbol=leg1_sym,
                                exchange="NFO",
                                quantity=lot_size,
                                price=leg1_limit,
                                trigger_price=0,
                                order_type="LIMIT",
                                transaction_type="SELL",
                                trade_type="MARGIN"
                            )
                            
                            txt = f"✅ Spread Executed for {symbol}!\nBUY Leg ({leg2_sym}): {order1_id}\nSELL Leg ({leg1_sym}): {order2_id}"
                            
                            requests.post(f"https://api.telegram.org/bot{tg_bot}/editMessageText", json={
                                "chat_id": chat_id,
                                "message_id": msg_id,
                                "text": cb["message"]["text"] + f"\n\n{txt}"
                            })
                            
                        except Exception as e:
                            logger.error(f"Failed to execute spread for {symbol}: {e}")
                            requests.post(f"https://api.telegram.org/bot{tg_bot}/editMessageText", json={
                                "chat_id": chat_id,
                                "message_id": msg_id,
                                "text": cb["message"]["text"] + f"\n\n❌ Execution Failed: {str(e)}"
                            })
                            
        except Exception as e:
            time.sleep(2)

def start_telegram_listener(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat):
    global _tg_thread, _tg_running
    if _tg_running or not tg_bot or not tg_chat:
        return
        
    _tg_running = True
    _tg_thread = threading.Thread(target=telegram_polling_loop, args=(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat))
    _tg_thread.daemon = True
    _tg_thread.start()
    
def stop_telegram_listener():
    global _tg_running
    _tg_running = False
