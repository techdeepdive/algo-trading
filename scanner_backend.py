import sqlite3

def cleanup_old_csvs():
    import glob, os
    # Clean up Tradehull's buggy windows-path files on Linux
    for f in glob.glob('*all_instrument*.csv'):
        try: os.remove(f)
        except: pass
    for f in glob.glob('Dependencies/*all_instrument*.csv'):
        try: os.remove(f)
        except: pass

import threading
import time
from datetime import datetime, timezone, timedelta
import pandas as pd
import requests
import os
from Dhan_Tradehull import Tradehull
from telegram_listener import start_telegram_listener, stop_telegram_listener, send_alert_with_buttons
import logging

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scanner_backend")

DB_FILE = "algo_lab.db"
SCAN_INTERVAL_SECONDS = 300  # 5 minutes

# Watchlists
NIFTY_SYMBOLS = [
    "RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK", "SBIN", 
    "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK", "HINDUNILVR", 
    "ASIANPAINT", "BAJFINANCE", "MARUTI", "SUNPHARMA", "TITAN", 
    "TATASTEEL", "ULTRACEMCO", "NTPC", "POWERGRID", "TECHM",
    "APOLLOHOSP", "BEL", "BPCL", "CIPLA", "GRASIM", "HCLTECH",
    "HEROMOTOCO", "HINDALCO", "INDUSINDBK"
]

BANKNIFTY_SYMBOLS = [
    "HDFCBANK", "ICICIBANK", "AXISBANK", "SBIN", "KOTAKBANK", 
    "INDUSINDBK", "BANKBARODA", "AUBANK", "FEDERALBNK", "IDFCFIRSTB", "PNB", "BANDHANBNK"
]

MCX_SYMBOLS = ["CRUDEOIL", "GOLD", "SILVER", "NATURALGAS", "COPPER", "ZINC", "ALUMINIUM", "LEAD"]

_scanner_thread = None
_scanner_running = False
_scanner_status = "STOPPED"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            trade_type TEXT,
            option_symbol TEXT,
            entry_time TEXT,
            spot_entry REAL,
            premium_entry REAL,
            stop_loss REAL,
            target REAL,
            status TEXT,
            pnl REAL,
            exit_time TEXT,
            exit_premium REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_state (
            symbol TEXT PRIMARY KEY,
            ltp REAL,
            wpr REAL,
            ema_fast REAL,
            ema_mid REAL,
            signal TEXT,
            last_updated TEXT
        )
    ''')
    conn.commit()
    conn.close()

def compute_signals(df, strategy_name='WPR_CROSS_EMA'):
    if df is None or len(df) < 20:
        return "NEUTRAL", {}

    signal = "NEUTRAL"
    indicators = {}
    
    if strategy_name == 'WPR_CROSS_EMA':
        ema_fast = 5
        ema_mid = 15
        wpr_period = 70
        
        df['EMA_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
        df['EMA_mid']  = df['close'].ewm(span=ema_mid, adjust=False).mean()
        hh = df['high'].rolling(wpr_period).max()
        ll = df['low'].rolling(wpr_period).min()
        df['WPR'] = (hh - df['close']) / (hh - ll) * -100

        rc = df.iloc[-1]

        # Simple concurrent check on the CURRENT candle:
        # LONG:  WPR is currently oversold (< -70) AND EMA fast is above EMA mid
        # SHORT: WPR is currently overbought (> -20) AND EMA fast is below EMA mid
        bullish = (rc['WPR'] < -70) and (rc['EMA_fast'] > rc['EMA_mid'])
        bearish = (rc['WPR'] > -20) and (rc['EMA_fast'] < rc['EMA_mid'])

        signal = "LONG" if bullish else "SHORT" if bearish else "NEUTRAL"
        indicators = {
            "ema_fast": float(rc['EMA_fast']),
            "ema_mid":  float(rc['EMA_mid']),
            "wpr":      float(rc['WPR']),
        }
        
    elif strategy_name == 'RSI_MR':
        # RSI Mean Reversion
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        rc = df.iloc[-1]
        pc = df.iloc[-2]
        
        bullish = pc['RSI'] < 30 and rc['RSI'] >= 30
        bearish = pc['RSI'] > 70 and rc['RSI'] <= 70
        
        signal = "LONG" if bullish else "SHORT" if bearish else "NEUTRAL"
        indicators = {
            "wpr": float(rc['RSI']), # Using WPR column to show RSI in UI
            "ema_fast": 0.0,
            "ema_mid": 0.0
        }
        
    elif strategy_name == 'BB_BREAKOUT':
        # Bollinger Bands Breakout
        df['SMA'] = df['close'].rolling(window=20).mean()
        df['STD'] = df['close'].rolling(window=20).std()
        df['Upper'] = df['SMA'] + (df['STD'] * 2)
        df['Lower'] = df['SMA'] - (df['STD'] * 2)
        
        rc = df.iloc[-1]
        pc = df.iloc[-2]
        
        bullish = pc['close'] <= pc['Upper'] and rc['close'] > rc['Upper']
        bearish = pc['close'] >= pc['Lower'] and rc['close'] < rc['Lower']
        
        signal = "LONG" if bullish else "SHORT" if bearish else "NEUTRAL"
        indicators = {
            "wpr": float(rc['close']), # Using wpr to show close price
            "ema_fast": float(rc['Upper']),
            "ema_mid": float(rc['Lower'])
        }
        
    elif strategy_name == 'OI_BREAKOUT':
        signal = "NEUTRAL" # OI not available in standard historical data
        indicators = {"wpr": 0, "ema_fast": 0, "ema_mid": 0}

    return signal, indicators

def run_screener(client_id, access_token, dhan_pin=None, dhan_totp=None, strategy_name='WPR_CROSS_EMA', watchlists=None, custom_symbols=None):
    if watchlists is None:
        watchlists = ['nifty50']
    
    symbols_to_scan = set()
    if 'nifty50' in watchlists:
        symbols_to_scan.update(NIFTY_SYMBOLS)
    if 'banknifty' in watchlists:
        symbols_to_scan.update(BANKNIFTY_SYMBOLS)
    if 'mcx' in watchlists:
        symbols_to_scan.update(MCX_SYMBOLS)
        
    if custom_symbols:
        custom_list = [s.strip().upper() for s in custom_symbols.split(',') if s.strip()]
        symbols_to_scan.update(custom_list)
        
    symbols_to_scan = list(symbols_to_scan)
    results = []

    try:
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
    except Exception as e:
        logger.error(f"Failed to init Tradehull for screener: {e}")
        return {"status": "error", "message": f"Dhan Login Failed: {e}"}

    for symbol in symbols_to_scan:
        try:
            exchange = "MCX" if symbol in MCX_SYMBOLS else "NSE"
            df = tsl.get_historical_data(tradingsymbol=symbol, exchange=exchange, timeframe="15")
            if df is None or df.empty:
                continue
                
            ltp = float(df.iloc[-1]['close'])
            signal, ind = compute_signals(df, strategy_name)
            
            results.append({
                "symbol": symbol,
                "ltp": ltp,
                "wpr": ind.get('wpr', 0),
                "ema_fast": ind.get('ema_fast', 0),
                "ema_mid": ind.get('ema_mid', 0),
                "signal": signal,
                "last_updated": datetime.now(IST).isoformat()
            })
        except Exception as e:
            logger.error(f"Screener Error processing {symbol}: {e}")

    return {"status": "success", "data": results}


def scanner_loop(client_id, access_token, dhan_pin=None, dhan_totp=None, tg_bot=None, tg_chat=None, strategy_name='WPR_CROSS_EMA', watchlists=None, custom_symbols=None):
    global _scanner_running
    
    if watchlists is None:
        watchlists = ['nifty50']
    
    symbols_to_scan = set()
    if 'nifty50' in watchlists:
        symbols_to_scan.update(NIFTY_SYMBOLS)
    if 'banknifty' in watchlists:
        symbols_to_scan.update(BANKNIFTY_SYMBOLS)
    if 'mcx' in watchlists:
        symbols_to_scan.update(MCX_SYMBOLS)
        
    if custom_symbols:
        custom_list = [s.strip().upper() for s in custom_symbols.split(',') if s.strip()]
        symbols_to_scan.update(custom_list)
        
    symbols_to_scan = list(symbols_to_scan)
    
    # Pre-download the instrument master to bypass Render/Cloudflare blocking default Python User-Agents
    csv_file = 'api-scrip-master.csv'
    if True: # Always force download daily
        logger.info(f"Downloading {csv_file} with custom User-Agent...")
        try:
            url = 'https://images.dhan.co/api-data/api-scrip-master.csv'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            with open(csv_file, 'wb') as f:
                f.write(response.content)
            logger.info("Successfully downloaded instrument master.")
        except Exception as e:
            logger.error(f"Failed to download instrument master: {e}")

    try:
        cleanup_old_csvs()
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
    except Exception as e:
        logger.error(f"Failed to init Tradehull: {e}")
        _scanner_running = False
        return

    class TokenErrorInterceptor(logging.Handler):
        def __init__(self):
            super().__init__()
            self.token_expired = False
        def emit(self, record):
            if 'DH-901' in str(record.getMessage()) or 'expired' in str(record.getMessage()).lower():
                self.token_expired = True

    interceptor = TokenErrorInterceptor()
    logging.getLogger().addHandler(interceptor)

    global _scanner_status
    while _scanner_running:
        now = datetime.now(IST)
        if now.hour < 8 or (now.hour == 8 and now.minute < 30):
            _scanner_status = "PAUSED"
            logger.info("Market is closed. Pausing scan sweep until 8:30 AM IST.")
            time.sleep(60)
            continue
            
        _scanner_status = "RUNNING"
        logger.info("Starting scan sweep...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        for symbol in symbols_to_scan:
            if not _scanner_running:
                break
                
            try:
                exchange = "MCX" if symbol in MCX_SYMBOLS else "NSE"
                df = tsl.get_historical_data(tradingsymbol=symbol, exchange=exchange, timeframe="15")
                if df is None or df.empty:
                    if interceptor.token_expired:
                        raise Exception("DH-901: Token expired detected via logging interceptor")
                    continue
                    
                ltp = float(df.iloc[-1]['close'])
                signal, ind = compute_signals(df, strategy_name)
                
                # Update Scan State
                cursor.execute('''
                    INSERT OR REPLACE INTO scan_state (symbol, ltp, wpr, ema_fast, ema_mid, signal, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (symbol, ltp, ind.get('wpr', 0), ind.get('ema_fast', 0), ind.get('ema_mid', 0), signal, datetime.now(IST).isoformat()))
                conn.commit()

                # Check existing open trades
                cursor.execute("SELECT id, trade_type, spot_entry, premium_entry, stop_loss, target FROM paper_trades WHERE symbol=? AND status='OPEN'", (symbol,))
                open_trades = cursor.fetchall()
                
                for t_id, t_type, spot_entry, qty, sl, tgt in open_trades:
                    # In this equity mode, premium_entry = qty
                    current_value = ltp * qty
                    entry_value = spot_entry * qty
                    
                    if t_type == "LONG":
                        pnl = current_value - entry_value
                    else:
                        pnl = entry_value - current_value
                        
                    status = 'OPEN'
                    if (t_type == "LONG" and ltp <= sl) or (t_type == "SHORT" and ltp >= sl):
                        status = 'CLOSED_SL'
                    elif (t_type == "LONG" and ltp >= tgt) or (t_type == "SHORT" and ltp <= tgt):
                        status = 'CLOSED_TARGET'
                        
                    cursor.execute('''
                        UPDATE paper_trades 
                        SET pnl=?, status=?, exit_time=?, exit_premium=? 
                        WHERE id=?
                    ''', (pnl, status, datetime.now(IST).isoformat() if status != 'OPEN' else None, ltp if status != 'OPEN' else None, t_id))
                    conn.commit()
                    
                    if status != 'OPEN' and tg_bot and tg_chat:
                        try:
                            msg = f"PAPER EXIT: {symbol} {t_type} {status}. PNL: ₹{pnl:.2f}. Exit Price: {ltp}"
                            send_alert_with_buttons(bot_token=tg_bot, chat_id=tg_chat, text=msg, symbol=symbol, ltp=ltp)
                        except: pass

                # Open new trades
                if signal in ["LONG", "SHORT"]:
                    cursor.execute("SELECT id FROM paper_trades WHERE symbol=? AND status='OPEN'", (symbol,))
                    if not cursor.fetchone():
                        qty = max(1, int(10000 / ltp))
                        opt_sym = f"{symbol} EQ"
                        
                        # 3% SL, 3% Target
                        if signal == "LONG":
                            sl = ltp * 0.97
                            tgt = ltp * 1.03
                        else:
                            sl = ltp * 1.03
                            tgt = ltp * 0.97
                        
                        cursor.execute('''
                            INSERT INTO paper_trades (symbol, trade_type, option_symbol, entry_time, spot_entry, premium_entry, stop_loss, target, status, pnl)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 0.0)
                        ''', (symbol, signal, opt_sym, datetime.now(IST).isoformat(), ltp, qty, sl, tgt))
                        conn.commit()
                        
                        if tg_bot and tg_chat:
                            try:
                                msg = f"PAPER ENTRY: {signal} {qty} {symbol} at {ltp}. SL: {sl:.2f}, TGT: {tgt:.2f}"
                                send_alert_with_buttons(bot_token=tg_bot, chat_id=tg_chat, text=msg, symbol=symbol, ltp=ltp)
                            except: pass

            except Exception as e:
                err_str = str(e)
                logger.error(f"Error processing {symbol}: {err_str}")
                if 'DH-901' in err_str or 'expired' in err_str.lower():
                    interceptor.token_expired = False
                    if dhan_pin and dhan_totp:
                        logger.info("Access token expired. Regenerating...")
                        try:
                            new_tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp)
                            tsl = Tradehull(client_id, new_tsl.token_id, mode="access_token")
                            
                            stop_telegram_listener()
                            time.sleep(2)
                            start_telegram_listener(client_id, new_tsl.token_id, None, None, tg_bot, tg_chat)
                            
                            logger.info("Successfully refreshed access token and restarted components.")
                            break # Break inner loop, restart sweep
                        except Exception as token_err:
                            logger.error(f"Failed to auto-refresh token: {token_err}")
                            _scanner_status = "ERROR: Token Expired"
                            _scanner_running = False
                            break
                    else:
                        _scanner_status = "ERROR: Token Expired"
                        _scanner_running = False
                        break
                
            time.sleep(1)

        conn.close()
        logger.info("Sweep complete. Sleeping...")
        
        for _ in range(SCAN_INTERVAL_SECONDS):
            if not _scanner_running:
                break
            time.sleep(1)

def start_scanner(client_id, access_token, dhan_pin=None, dhan_totp=None, tg_bot=None, tg_chat=None, strategy_name='WPR_CROSS_EMA', watchlists=None, custom_symbols=None):
    global _scanner_thread, _scanner_running, _scanner_status
    if _scanner_running:
        return {"status": "success", "message": "Scanner already running"}
        
    if dhan_pin and dhan_totp:
        try:
            tsl_temp = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp)
            access_token = tsl_temp.token_id
        except Exception as e:
            return {"status": "error", "message": f"Login failed: {str(e)}"}

    init_db()
    _scanner_running = True
    _scanner_status = "RUNNING"
    _scanner_thread = threading.Thread(target=scanner_loop, args=(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat, strategy_name, watchlists, custom_symbols))
    _scanner_thread.daemon = True
    _scanner_thread.start()
    
    start_telegram_listener(client_id, access_token, None, None, tg_bot, tg_chat)
    
    return {"status": "success", "message": "Scanner started"}

def stop_scanner():
    global _scanner_running, _scanner_status
    _scanner_running = False
    _scanner_status = "STOPPED"
    stop_telegram_listener()
    return {"status": "success", "message": "Scanner stopping"}

def get_dashboard_state():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM scan_state")
        scan_state = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT t.*, s.ltp as current_price 
            FROM paper_trades t
            LEFT JOIN scan_state s ON t.symbol = s.symbol
            ORDER BY t.id DESC LIMIT 100
        ''')
        trades = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        return {
            "status": "success",
            "is_running": _scanner_running,
            "engine_status": _scanner_status if _scanner_running else "STOPPED",
            "scan_state": scan_state,
            "trades": trades
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
