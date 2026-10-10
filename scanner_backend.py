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
import numpy as np
import requests
import os
from Dhan_Tradehull import Tradehull
from telegram_listener import start_telegram_listener, stop_telegram_listener, send_alert_with_buttons
import logging

IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scanner_backend")

from google import genai

logging.getLogger("google_genai.models").setLevel(logging.ERROR)
import time

def get_gemini_batch_summary(trades, gemini_key):
    if not gemini_key or not trades:
        return ""
    
    trades_text = "\n".join([f"- {t['signal']} {t['symbol']} at {t['ltp']}, SL: {t['sl']:.2f}, Target: {t['tgt']:.2f}" for t in trades])
    prompt = f"Give a very short 2-3 sentence overall market analysis and news summary for these trade setups:\n{trades_text}"
    client = genai.Client(api_key=gemini_key)
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
            )
            return "\n\n🤖 AI Batch Summary: " + response.text.strip()
        except Exception as e:
            if '503' in str(e) or '429' in str(e):
                logger.warning(f"Gemini API rate limit/overload (attempt {attempt+1}/3)... sleeping 3s")
                time.sleep(3)
            else:
                logger.error(f"Gemini API error: {e}")
                break
    return ""

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
            spread_type TEXT,
            leg1_symbol TEXT,
            leg2_symbol TEXT,
            lot_size INTEGER,
            entry_time TEXT,
            spot_entry REAL,
            leg1_entry_price REAL,
            leg2_entry_price REAL,
            net_premium_entry REAL,
            stop_loss REAL,
            target REAL,
            status TEXT,
            pnl REAL,
            exit_time TEXT,
            exit_spot REAL,
            leg1_exit_price REAL,
            leg2_exit_price REAL,
            net_premium_exit REAL
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

def get_spread_legs(symbol, ltp, signal):
    try:
        df = pd.read_csv('api-scrip-master.csv', low_memory=False)
        opt_type = 'PE' if signal == 'LONG' else 'CE'
        
        opts = df[
            (df['SEM_EXCH_INSTRUMENT_TYPE'] == 'OP') & 
            (df['SEM_TRADING_SYMBOL'].str.startswith(f'{symbol}-')) & 
            (df['SEM_OPTION_TYPE'] == opt_type) & 
            (df['SEM_EXPIRY_FLAG'] == 'M')
        ].copy()
        
        if opts.empty: return None, None, 1
            
        opts['SEM_EXPIRY_DATE'] = pd.to_datetime(opts['SEM_EXPIRY_DATE'])
        today = datetime.now()
        
        future_opts = opts[opts['SEM_EXPIRY_DATE'] >= today]
        expiries = sorted(future_opts['SEM_EXPIRY_DATE'].dt.date.unique())
        
        if not expiries: return None, None, 1
            
        target_expiry = expiries[0]
        if (target_expiry - today.date()).days <= 14 and len(expiries) > 1:
            target_expiry = expiries[1]
            
        target_opts = future_opts[future_opts['SEM_EXPIRY_DATE'].dt.date == target_expiry]
        strikes = sorted(target_opts['SEM_STRIKE_PRICE'].unique())
        if not strikes: return None, None, 1
        
        atm_idx = np.abs(np.array(strikes) - ltp).argmin()
        
        if signal == 'LONG':
            leg1_strike = strikes[atm_idx]
            leg2_idx = max(0, atm_idx - 2)
            leg2_strike = strikes[leg2_idx]
        else:
            leg1_strike = strikes[atm_idx]
            leg2_idx = min(len(strikes)-1, atm_idx + 2)
            leg2_strike = strikes[leg2_idx]
            
        leg1_row = target_opts[target_opts['SEM_STRIKE_PRICE'] == leg1_strike].iloc[0]
        leg2_row = target_opts[target_opts['SEM_STRIKE_PRICE'] == leg2_strike].iloc[0]
        
        return leg1_row['SEM_CUSTOM_SYMBOL'], leg2_row['SEM_CUSTOM_SYMBOL'], int(leg1_row['SEM_LOT_UNITS'])
    except Exception as e:
        logger.error(f"Error finding spread legs for {symbol}: {e}")
        return None, None, 1

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


def scanner_loop(client_id, access_token, dhan_pin=None, dhan_totp=None, tg_bot=None, tg_chat=None, gemini_key=None, strategy_name='WPR_CROSS_EMA', watchlists=None, custom_symbols=None):
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
        if not hasattr(tsl, 'Dhan'):
            raise Exception("Tradehull initialization failed silently due to invalid credentials or OTP.")
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
        
        is_weekend = now.weekday() >= 5
        is_night = now.hour < 8 or (now.hour == 8 and now.minute < 30)
        
        if is_weekend or is_night:
            _scanner_status = "PAUSED"
            logger.info("Market is closed (weekend or night). Pausing scan sweep.")
            time.sleep(60)
            continue
            
        _scanner_status = "RUNNING"
        logger.info("Starting scan sweep...")
        sweep_trades = []
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
                cursor.execute("SELECT id, trade_type, spread_type, spot_entry, leg1_symbol, leg2_symbol, lot_size, leg1_entry_price, leg2_entry_price, net_premium_entry, stop_loss, target FROM paper_trades WHERE symbol=? AND status='OPEN'", (symbol,))
                open_trades = cursor.fetchall()
                
                for t_id, t_type, spread_type, spot_entry, leg1_sym, leg2_sym, lot_size, leg1_entry, leg2_entry, net_entry, sl, tgt in open_trades:
                    try:
                        opt_ltps = tsl.get_ltp_data(names=[leg1_sym, leg2_sym])
                        leg1_ltp = opt_ltps.get(leg1_sym, leg1_entry)
                        leg2_ltp = opt_ltps.get(leg2_sym, leg2_entry)
                    except:
                        leg1_ltp, leg2_ltp = leg1_entry, leg2_entry
                        
                    net_current = leg1_ltp - leg2_ltp
                    
                    # Credit spread: PNL = (net_entry - net_current) * lot_size
                    pnl = (net_entry - net_current) * lot_size
                        
                    status = 'OPEN'
                    if (t_type == "LONG" and ltp <= sl) or (t_type == "SHORT" and ltp >= sl):
                        status = 'CLOSED_SL'
                    elif (t_type == "LONG" and ltp >= tgt) or (t_type == "SHORT" and ltp <= tgt):
                        status = 'CLOSED_TARGET'
                        
                    cursor.execute('''
                        UPDATE paper_trades 
                        SET pnl=?, status=?, exit_time=?, exit_spot=?, leg1_exit_price=?, leg2_exit_price=?, net_premium_exit=?
                        WHERE id=?
                    ''', (pnl, status, datetime.now(IST).isoformat() if status != 'OPEN' else None, ltp if status != 'OPEN' else None, leg1_ltp if status != 'OPEN' else None, leg2_ltp if status != 'OPEN' else None, net_current if status != 'OPEN' else None, t_id))
                    conn.commit()
                    
                    if status != 'OPEN' and tg_bot and tg_chat:
                        try:
                            msg = f"PAPER EXIT: {symbol} {spread_type} {status}.\nSpot Exit: {ltp:.2f}\nTotal PNL: ₹{pnl:.2f}\nLeg1 {leg1_sym} Exit: {leg1_ltp}\nLeg2 {leg2_sym} Exit: {leg2_ltp}"
                            send_alert_with_buttons(bot_token=tg_bot, chat_id=tg_chat, text=msg, symbol=symbol, ltp=ltp)
                        except: pass

                # Open new trades
                if signal in ["LONG", "SHORT"]:
                    cursor.execute("SELECT id FROM paper_trades WHERE symbol=? AND status='OPEN'", (symbol,))
                    if not cursor.fetchone():
                        leg1_sym, leg2_sym, lot_size = get_spread_legs(symbol, ltp, signal)
                        if not leg1_sym:
                            logger.error(f"Could not find options spread for {symbol}. Skipping.")
                            continue
                            
                        try:
                            opt_ltps = tsl.get_ltp_data(names=[leg1_sym, leg2_sym])
                            leg1_entry = opt_ltps.get(leg1_sym, 0)
                            leg2_entry = opt_ltps.get(leg2_sym, 0)
                            net_entry = leg1_entry - leg2_entry
                        except:
                            leg1_entry, leg2_entry, net_entry = 0, 0, 0
                        
                        spread_type = "BULL_PUT_SPREAD" if signal == "LONG" else "BEAR_CALL_SPREAD"
                        
                        # 3% SL, 3% Target on underlying
                        if signal == "LONG":
                            sl = ltp * 0.97
                            tgt = ltp * 1.03
                        else:
                            sl = ltp * 1.03
                            tgt = ltp * 0.97
                        
                        cursor.execute('''
                            INSERT INTO paper_trades (symbol, trade_type, spread_type, leg1_symbol, leg2_symbol, lot_size, entry_time, spot_entry, leg1_entry_price, leg2_entry_price, net_premium_entry, stop_loss, target, status, pnl)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 0.0)
                        ''', (symbol, signal, spread_type, leg1_sym, leg2_sym, lot_size, datetime.now(IST).isoformat(), ltp, leg1_entry, leg2_entry, net_entry, sl, tgt))
                        conn.commit()
                        trade_id = cursor.lastrowid
                        
                        if tg_bot and tg_chat:
                            try:
                                msg = f"PAPER ENTRY: {symbol} {spread_type} at Spot {ltp:.2f}\nSELL Leg: {leg1_sym} at {leg1_entry:.2f}\nBUY Leg: {leg2_sym} at {leg2_entry:.2f}\nNet Premium: {net_entry:.2f} | Lot Size: {lot_size}\nSpot Target: {tgt:.2f} | Spot SL: {sl:.2f}"
                                
                                # We pass trade_id as ltp here so telegram_listener can capture it. 
                                # The callback_data max length is 64. "BUY_{symbol}_{trade_id}" will fit.
                                send_alert_with_buttons(bot_token=tg_bot, chat_id=tg_chat, text=msg, symbol=symbol, ltp=float(trade_id))
                            except Exception as e:
                                logger.error(f"Error sending TG alert: {e}")
                                
                        sweep_trades.append({
                            "symbol": symbol, "signal": signal, "ltp": ltp, "sl": sl, "tgt": tgt
                        })

            except Exception as e:
                err_str = str(e)
                logger.error(f"Error processing {symbol}: {err_str}")
                if 'DH-901' in err_str or 'expired' in err_str.lower() or 'instrument_df' in err_str:
                    interceptor.token_expired = False
                    if dhan_pin and dhan_totp:
                        logger.info("Access token expired or Tradehull broken. Regenerating...")
                        try:
                            new_tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp)
                            if not hasattr(new_tsl, 'Dhan'):
                                raise Exception("Failed to regenerate Tradehull: Invalid TOTP or credentials.")
                            tsl = Tradehull(client_id, new_tsl.token_id, mode="access_token")
                            if not hasattr(tsl, 'Dhan'):
                                raise Exception("Failed to initialize Tradehull with new token.")
                            
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

        if sweep_trades and tg_bot and tg_chat and gemini_key:
            try:
                batch_summary = get_gemini_batch_summary(sweep_trades, gemini_key)
                if batch_summary:
                    url = f"https://api.telegram.org/bot{tg_bot}/sendMessage"
                    requests.post(url, json={"chat_id": tg_chat, "text": batch_summary}, timeout=10)
            except Exception as e:
                logger.error(f"Failed to send batch TG summary: {e}")

        conn.close()
        logger.info("Sweep complete. Sleeping...")
        
        for _ in range(SCAN_INTERVAL_SECONDS):
            if not _scanner_running:
                break
            time.sleep(1)

def start_scanner(client_id, access_token, dhan_pin=None, dhan_totp=None, tg_bot=None, tg_chat=None, gemini_key=None, strategy_name='WPR_CROSS_EMA', watchlists=None, custom_symbols=None):
    global _scanner_thread, _scanner_running, _scanner_status
    if _scanner_running:
        return {"status": "success", "message": "Scanner already running"}
        
    if dhan_pin and dhan_totp:
        try:
            tsl_temp = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp)
            if not hasattr(tsl_temp, 'Dhan'):
                raise Exception("Invalid credentials or OTP")
            access_token = tsl_temp.token_id
        except Exception as e:
            return {"status": "error", "message": f"Login failed: {str(e)}"}

    init_db()
    _scanner_running = True
    _scanner_status = "RUNNING"
    _scanner_thread = threading.Thread(target=scanner_loop, args=(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat, gemini_key, strategy_name, watchlists, custom_symbols))
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
