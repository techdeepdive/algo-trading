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
                    {"text": "🟢 BUY LIMIT", "callback_data": f"BUY_{symbol}_{ltp}"},
                    {"text": "🔴 SELL LIMIT", "callback_data": f"SELL_{symbol}_{ltp}"}
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

def telegram_polling_loop(client_id, dhan_pin, dhan_totp, tg_bot, tg_chat):
    global _tg_running
    offset = 0
    
    # Init Tradehull instance for telegram orders
    tsl = None
    try:
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp)
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
                    if len(parts) == 3:
                        action = parts[0]
                        symbol = parts[1]
                        ltp = float(parts[2])
                        
                        qty = 1 # Default qty
                        
                        requests.post(f"https://api.telegram.org/bot{tg_bot}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": f"⚙️ Executing {action} on {symbol} at {ltp} via AlgoScan..."
                        })
                        
                        logger.info(f"Executing Telegram Order: {action} on {symbol} at {ltp}")
                        try:
                            # Fire raw limit order using Tradehull Token
                            payload = {
                                "dhanClientId": client_id,
                                "transactionType": action,
                                "exchangeSegment": "NSE_EQ",
                                "productType": "INTRADAY",
                                "orderType": "LIMIT",
                                "validity": "DAY",
                                "securityId": str(tsl._resolve_security_id(symbol, "NSE")),
                                "quantity": qty,
                                "disclosedQuantity": 0,
                                "price": ltp,
                                "triggerPrice": 0.0,
                                "afterMarketOrder": False
                            }
                            headers = {
                                "Content-Type": "application/json",
                                "access-token": tsl.token_id
                            }
                            order_resp = requests.post("https://api.dhan.co/v2/orders", json=payload, headers=headers)
                            o_data = order_resp.json()
                            
                            if order_resp.status_code == 200 and o_data.get('orderStatus') != 'REJECTED':
                                txt = f"✅ {action} Order Placed for {symbol}!\nOrder ID: {o_data.get('orderId', 'N/A')}"
                            else:
                                txt = f"❌ Order Failed: {o_data.get('remarks', o_data.get('errorMessage', 'Unknown'))}"
                            logger.info(txt)
                                
                            requests.post(f"https://api.telegram.org/bot{tg_bot}/editMessageText", json={
                                "chat_id": chat_id,
                                "message_id": msg_id,
                                "text": cb["message"]["text"] + f"\n\n{txt}"
                            })
                        except Exception as e:
                            requests.post(f"https://api.telegram.org/bot{tg_bot}/sendMessage", json={
                                "chat_id": chat_id,
                                "text": f"❌ Error placing trade: {str(e)}"
                            })
                            
        except Exception as e:
            time.sleep(2)

def start_telegram_listener(client_id, dhan_pin, dhan_totp, tg_bot, tg_chat):
    global _tg_thread, _tg_running
    if _tg_running or not tg_bot or not tg_chat:
        return
        
    _tg_running = True
    _tg_thread = threading.Thread(target=telegram_polling_loop, args=(client_id, dhan_pin, dhan_totp, tg_bot, tg_chat))
    _tg_thread.daemon = True
    _tg_thread.start()
    
def stop_telegram_listener():
    global _tg_running
    _tg_running = False
