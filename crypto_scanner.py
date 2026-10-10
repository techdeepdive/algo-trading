import os
import time
import json
import pytz
import hmac
import hashlib
import threading
import sqlite3
import pandas as pd
import requests
import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('crypto_scanner')

CRYPTO_SYMBOLS = ["BTC", "ETH", "SOL", "HYPE", "ZEC", "TAO", "ONDO", "LINK", "NEAR", "DOGE", "BNB", "AVAX", "LTC", "ENA", "ARB", "WLD", "ADA", "DOT", "AXS", "SUI", "TLM", "ICP", "VIRTUAL", "SHIB", "PEPE", "OM", "UNI", "XRP", "TRX", "SAND", "ETHFI"]
API_URL = "https://api.india.delta.exchange"
DB_NAME = "crypto_lab.db"

_scanner_running = False
_crypto_state = []

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS crypto_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            trade_type TEXT,
            entry_time TEXT,
            entry_price REAL,
            current_price REAL,
            stop_loss REAL,
            target REAL,
            status TEXT,
            pnl REAL,
            exit_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

def delta_request(method, endpoint, api_key, api_secret, payload=''):
    try:
        server_time = int(time.time())
        timestamp = str(server_time)
        sig_payload = method + timestamp + endpoint + payload
        signature = hmac.new(api_secret.encode('utf-8'), sig_payload.encode('utf-8'), hashlib.sha256).hexdigest()
        headers = {
            'api-key': api_key,
            'timestamp': timestamp,
            'signature': signature,
            'Content-Type': 'application/json'
        }
        url = API_URL + endpoint
        if method == 'GET':
            res = requests.get(url, headers=headers, timeout=10)
        else:
            res = requests.post(url, headers=headers, data=payload, timeout=10)
        return res
    except Exception as e:
        logger.error(f"Delta API Request error: {e}")
        return None

def fetch_ohlc(symbol):
    # Delta Exchange requires resolution in strings: "60" for 1 hour.
    # We fetch last 100 candles.
    end_time = int(time.time())
    start_time = end_time - (100 * 60 * 60)
    url = f"{API_URL}/v2/history/candles?symbol={symbol}USD&resolution=15m&start={start_time}&end={end_time}"
    try:
        res = requests.get(url, timeout=10)
        data = res.json()
        if data.get('success') and data.get('result'):
            df = pd.DataFrame(data['result'])
            df.rename(columns={'time': 'datetime'}, inplace=True)
            df['datetime'] = pd.to_datetime(df['datetime'], unit='s')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
    except Exception as e:
        logger.error(f"Failed to fetch OHLC for {symbol}: {e}")
    return None

def compute_signals(df, ema_fast=5, ema_mid=15, ema_slow=50, wpr_period=70):
    if df is None or len(df) < max(ema_slow, wpr_period):
        return None, "NEUTRAL", {}

    df['EMA_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
    df['EMA_mid']  = df['close'].ewm(span=ema_mid, adjust=False).mean()
    df['EMA_slow'] = df['close'].ewm(span=ema_slow, adjust=False).mean()
    hh = df['high'].rolling(wpr_period).max()
    ll = df['low'].rolling(wpr_period).min()
    df['WPR'] = (hh - df['close']) / (hh - ll) * -100

    rc = df.iloc[-1]
    pc = df.iloc[-2]

    bullish = (
        (pc['EMA_fast'] <= pc['EMA_mid'] and rc['EMA_fast'] > rc['EMA_mid'])
        and (rc['close'] > rc['EMA_slow'])
        and (rc['EMA_fast'] > rc['EMA_slow'])
        and (rc['WPR'] > -50)
    )
    bearish = (
        (pc['EMA_fast'] >= pc['EMA_mid'] and rc['EMA_fast'] < rc['EMA_mid'])
        and (rc['close'] < rc['EMA_slow'])
        and (rc['EMA_fast'] < rc['EMA_slow'])
        and (rc['WPR'] < -50)
    )

    signal = "LONG" if bullish else "SHORT" if bearish else "NEUTRAL"
    return df, signal, rc

def send_telegram(msg, bot_token, chat_id, keyboard=None):
    if not bot_token or not chat_id: return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def crypto_scanner_loop(api_key, api_secret, tg_bot, tg_chat):
    global _scanner_running
    _scanner_running = True
    with open('.crypto_env', 'w') as f:
        f.write(api_key + '\n' + api_secret)

    init_db()
    
    logger.info("Crypto Scanner Started")
    send_telegram("🚀 Crypto Scanner Started (15m TF) via Delta India", tg_bot, tg_chat)
    
    while _scanner_running:
        try:
            import time
            start_sweep = time.time()
            logger.info(f"Starting crypto market sweep for {len(CRYPTO_SYMBOLS)} coins...")
            ist = pytz.timezone('Asia/Kolkata')
            scan_time = datetime.datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
            alert_batch = []
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            
            # Update open positions PNL and exit conditions
            c.execute("SELECT id, symbol, trade_type, entry_price, stop_loss, target FROM crypto_trades WHERE status='OPEN'")
            open_trades = c.fetchall()
            
            latest_prices = {}
            for t_id, sym, t_type, entry_p, sl, tgt in open_trades:
                if sym not in latest_prices:
                    df = fetch_ohlc(sym)
                    if df is not None:
                        latest_prices[sym] = df.iloc[-1]['close']
                
                ltp = latest_prices.get(sym)
                if ltp:
                    pnl_pct = (ltp - entry_p) / entry_p if t_type == 'LONG' else (entry_p - ltp) / entry_p
                    pnl_pct *= 100
                    
                    status = 'OPEN'
                    if (t_type == 'LONG' and ltp <= sl) or (t_type == 'SHORT' and ltp >= sl):
                        status = 'CLOSED_SL'
                    elif (t_type == 'LONG' and ltp >= tgt) or (t_type == 'SHORT' and ltp <= tgt):
                        status = 'CLOSED_TARGET'
                        
                    exit_time = datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S") if status != 'OPEN' else None
                    c.execute("UPDATE crypto_trades SET current_price=?, pnl=?, status=?, exit_time=? WHERE id=?", (ltp, pnl_pct, status, exit_time, t_id))
            
            conn.commit()
            
            # Scan for new signals
            current_scan_state = []
            for sym in CRYPTO_SYMBOLS:
                df = fetch_ohlc(sym)
                if df is not None:
                    df, signal, rc = compute_signals(df)
                    if df is not None:
                        current_scan_state.append({
                            "symbol": sym,
                            "ltp": rc['close'],
                            "wpr": rc['WPR'],
                            "ema_fast": rc['EMA_fast'],
                            "ema_mid": rc['EMA_mid'],
                            "ema_slow": rc['EMA_slow'],
                            "signal": signal,
                            "timestamp": datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%H:%M:%S")
                        })
                    if signal in ["LONG", "SHORT"]:
                        # Check if already open
                        c.execute("SELECT id FROM crypto_trades WHERE symbol=? AND status='OPEN'", (sym,))
                        if not c.fetchone():
                            ltp = rc['close']
                            sl = ltp * 0.97 if signal == "LONG" else ltp * 1.03
                            tgt = ltp * 1.04 if signal == "LONG" else ltp * 0.96
                            
                            c.execute("INSERT INTO crypto_trades (symbol, trade_type, entry_time, entry_price, current_price, stop_loss, target, status, pnl) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                      (sym, signal, datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S"), ltp, ltp, sl, tgt, 'OPEN', 0.0))
                            conn.commit()
                            
                            msg = f"🚨 <b>CRYPTO {signal}</b> 🚨\nSymbol: {sym}USD\nLTP: {ltp}\nTarget: {tgt:.2f} (20%)\nSL: {sl:.2f} (15%)"
                            
                            keyboard = {
                                "inline_keyboard": [
                                    [{"text": f"🚀 EXECUTE {signal} {sym}USD", "callback_data": f"CRYPTO_{sym}_{signal}_{ltp:.2f}"}]
                                ]
                            }
                            send_telegram(msg, tg_bot, tg_chat, keyboard)
                            alert_batch.append(f"{signal} {sym} at {ltp}")
                            
            conn.close()
            global _crypto_state
            
            # Inject last sweep time into the first item
            if len(current_scan_state) > 0:
                current_scan_state[0]['last_sweep'] = scan_time
                
            _crypto_state = current_scan_state
            
            # Send AI Summary
            logger.info(f"Sweep completed in {round(time.time() - start_sweep, 2)} seconds. Found {len(alert_batch)} signals.")
            if len(alert_batch) > 0:
                import os, google.generativeai as genai
                gemini_key = os.getenv("GEMINI_API_KEY")
                if gemini_key:
                    try:
                        genai.configure(api_key=gemini_key)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        prompt = "You are a professional crypto trading analyst. Summarize these trading alerts in 2-3 engaging sentences highlighting the market action: " + ", ".join(alert_batch)
                        resp = model.generate_content(prompt)
                        if resp and resp.text:
                            ai_msg = f"🤖 <b>AI Crypto Summary</b>\n\n{resp.text}"
                            send_telegram(ai_msg, tg_bot, tg_chat)
                    except Exception as e:
                        logger.error(f"Gemini API Error: {e}")
        except Exception as e:
            logger.error(f"Crypto Scanner Error: {e}")
            
        time.sleep(900) # Sleep 5 minutes between 15m scans

def start_crypto_scanner(api_key, api_secret, tg_bot, tg_chat):
    global _scanner_running
    if not _scanner_running:
        threading.Thread(target=crypto_scanner_loop, args=(api_key, api_secret, tg_bot, tg_chat), daemon=True).start()
        return True
    return False

def stop_crypto_scanner():
    global _scanner_running
    _scanner_running = False
_crypto_state = []
