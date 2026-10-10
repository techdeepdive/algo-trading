import os
import glob
import pandas as pd
import requests
import feedparser
from bs4 import BeautifulSoup
from google import genai
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from scanner import run_scan
from backtester import run_backtest
from Dhan_Tradehull import Tradehull
from hedging_backtester import get_strategy_payoff, run_hedging_backtest, run_hedging_backtest_from_csv

# Load .env for local development (Render injects env vars directly)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__, static_folder='frontend/dist', static_url_path='/')
PORT = int(os.environ.get("PORT", 5001))


DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# ---- Cached instrument data ------------------------------------------------
_symbol_cache = None

def _load_symbols():
    """Load symbol list from the Tradehull instrument CSV in Dependencies/."""
    global _symbol_cache
    if _symbol_cache is not None:
        return _symbol_cache

    dep_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dependencies")
    csvs = glob.glob(os.path.join(dep_dir, "all_instrument*.csv"))
    if not csvs:
        return []

    # Use the most recent instrument file
    csv_path = sorted(csvs)[-1]
    df = pd.read_csv(csv_path, low_memory=False)

    symbols = []

    # INDEX instruments
    idx = df[df['SEM_INSTRUMENT_NAME'] == 'INDEX']
    for _, row in idx.iterrows():
        sym = str(row['SEM_TRADING_SYMBOL']).strip()
        if sym and sym != 'nan':
            symbols.append({"symbol": sym, "exchange": "INDEX"})

    # MCX commodity futures
    mcx = df[(df['SEM_EXM_EXCH_ID'] == 'MCX') & (df['SEM_INSTRUMENT_NAME'].isin(['FUTCOM', 'FUTIDX']))]
    mcx_names = set()
    for _, row in mcx.iterrows():
        name = str(row.get('SM_SYMBOL_NAME', '')).strip()
        if name and name != 'nan' and name not in mcx_names:
            mcx_names.add(name)
            symbols.append({"symbol": name, "exchange": "MCX"})

    # NSE equity
    nse = df[(df['SEM_EXM_EXCH_ID'] == 'NSE') & (df['SEM_INSTRUMENT_NAME'] == 'EQUITY')]
    nse_syms = set()
    for _, row in nse.iterrows():
        sym = str(row['SEM_TRADING_SYMBOL']).strip()
        if sym and sym != 'nan' and sym not in nse_syms:
            nse_syms.add(sym)
            symbols.append({"symbol": sym, "exchange": "NSE"})

    # BSE-only equity
    bse = df[(df['SEM_EXM_EXCH_ID'] == 'BSE') & (df['SEM_INSTRUMENT_NAME'] == 'EQUITY')]
    for _, row in bse.iterrows():
        sym = str(row['SEM_TRADING_SYMBOL']).strip()
        if sym and sym != 'nan' and sym not in nse_syms:
            symbols.append({"symbol": sym, "exchange": "BSE"})

    symbols.sort(key=lambda x: x["symbol"])
    _symbol_cache = symbols
    return symbols


def _detect_exchange(symbol):
    """Auto-detect exchange for a given symbol from the instrument file."""
    symbols = _load_symbols()
    for s in symbols:
        if s["symbol"] == symbol:
            return s["exchange"]
    return "NSE"  # default fallback


# ---- Routes ----------------------------------------------------------------

@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/scan", methods=["POST"])
def scan():
    data = request.json
    
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    tg_bot = data.get("tg_bot")
    tg_chat = data.get("tg_chat")
    
    if not client_id or (not access_token and (not dhan_pin or not dhan_totp)):
        return jsonify({"status": "error", "message": "Client ID and Access Token are required."}), 400
        
    result = run_scan(client_id, access_token, tg_bot, tg_chat)
    
    if result.get("status") == "error":
        return jsonify(result), 400
        
    return jsonify(result)


@app.route("/symbols")
def symbols():
    q = request.args.get("q", "").strip().upper()
    syms = _load_symbols()
    if q:
        prefix = [s for s in syms if s["symbol"].startswith(q)]
        if len(prefix) < 50:
            contains = [s for s in syms if q in s["symbol"] and not s["symbol"].startswith(q)]
            prefix.extend(contains[:50 - len(prefix)])
        syms = prefix[:50]
    else:
        syms = syms[:50]
    return jsonify({"symbols": syms})


@app.route("/historical", methods=["POST"])
def historical():
    data = request.json
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    symbol = data.get("symbol", "").strip()
    from_date = data.get("from_date", "").strip()
    to_date = data.get("to_date", "").strip()
    timeframe = data.get("timeframe", "DAY").strip()
    
    asset_type = data.get("asset_type", "equity")
    expiry_flag = data.get("expiry_flag", "WEEK")
    expiry_code = int(data.get("expiry_code", 1))
    strike = data.get("strike", "ATM")
    option_type = data.get("option_type", "CALL")

    if not client_id or (not access_token and (not dhan_pin or not dhan_totp)):
        return jsonify({"status": "error", "message": "Client ID and Access Token are required."}), 400
    if not symbol:
        return jsonify({"status": "error", "message": "Symbol is required."}), 400

    exchange_override = data.get("exchange")  # Optional manual override from UI
    exchange = exchange_override if exchange_override else _detect_exchange(symbol)

    try:
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    try:
        if asset_type == "options":
            # For options, Tradehull uses integer timeframes for minutes (1, 5, 15, 60, DAY)
            tf_int = timeframe if timeframe == "DAY" else int(timeframe)
            
            # Parse strike range
            strikes_to_fetch = [strike]
            if "_" in strike:
                # e.g. ATM_1 means ATM-1, ATM, ATM+1
                offset = int(strike.split("_")[1])
                strikes_to_fetch = ["ATM"]
                for i in range(1, offset + 1):
                    strikes_to_fetch.append(f"ATM+{i}")
                    strikes_to_fetch.append(f"ATM-{i}")

            total_rows = 0
            filenames = []
            columns = []
            
            for s in strikes_to_fetch:
                try:
                    df = tsl.get_expired_option_data(
                        tradingsymbol=symbol, 
                        exchange="NSE" if exchange == "NSE" else "INDEX",
                        interval=tf_int,
                        expiry_flag=expiry_flag,
                        expiry_code=expiry_code,
                        strike=s,
                        option_type=option_type,
                        from_date=from_date,
                        to_date=to_date
                    )
                    
                    if df is not None and len(df) > 0:
                        s_clean = s.replace("+", "_PLUS_").replace("-", "_MINUS_")
                        filename = f"{symbol}_{s_clean}_{option_type}_{expiry_flag}_{timeframe}_{from_date}_{to_date}.csv"
                        filepath = os.path.join(DOWNLOADS_DIR, filename)
                        df.to_csv(filepath, index=False)
                        
                        total_rows += len(df)
                        filenames.append(filename)
                        columns = list(df.columns)
                except Exception as inner_e:
                    print(f"[historical] Error fetching strike {s} — skipping.")
                    continue
            
            if len(filenames) == 0:
                return jsonify({"status": "error", "message": "No data returned for any strike in the range."}), 400

            return jsonify({
                "status": "success",
                "filename": ", ".join(filenames),
                "rows": total_rows,
                "columns": columns,
                "exchange": exchange,
            })

        else:
            if from_date and to_date:
                df = tsl.get_long_term_historical_data(
                    tradingsymbol=symbol, exchange=exchange, timeframe=timeframe,
                    from_date=from_date, to_date=to_date
                )
            else:
                df = tsl.get_historical_data(
                    tradingsymbol=symbol, exchange=exchange, timeframe=timeframe
                )
            date_suffix = f"_{from_date}_{to_date}" if from_date and to_date else ""
            filename = f"{symbol}_{exchange}_{timeframe}{date_suffix}.csv"
            
            if df is None or len(df) == 0:
                return jsonify({"status": "error", "message": "No data returned for this symbol/date range."}), 400

            filepath = os.path.join(DOWNLOADS_DIR, filename)
            df.to_csv(filepath, index=False)

            return jsonify({
                "status": "success",
                "filename": filename,
                "rows": len(df),
                "columns": list(df.columns),
                "exchange": exchange,
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400






@app.route("/downloads")
def downloads():
    files = []
    if os.path.isdir(DOWNLOADS_DIR):
        for f in sorted(os.listdir(DOWNLOADS_DIR)):
            if f.endswith(".csv"):
                fpath = os.path.join(DOWNLOADS_DIR, f)
                size_kb = round(os.path.getsize(fpath) / 1024, 1)
                files.append({"filename": f, "size_kb": size_kb})
    return jsonify({"files": files})


@app.route("/downloads/<filename>")
def download_file(filename):
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)


@app.route("/simulate_hedging", methods=["POST"])
def simulate_hedging():
    data = request.json
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    symbol = data.get("symbol")
    strategy = data.get("strategy")
    exchange = data.get("exchange", "INDEX")

    try:
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
        result = get_strategy_payoff(tsl, symbol, exchange, strategy)
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/backtest_hedging", methods=["POST"])
def backtest_hedging():
    # Support both JSON (API data) and FormData (CSV upload)
    if request.is_json:
        data = request.json
    else:
        data = request.form

    strategy = data.get("strategy")
    slippage = float(data.get("slippage", 0.0))
    capital = float(data.get("capital", 100000))
    qty_multiplier = int(data.get("qty_multiplier", 1))
    sl_pct = float(data.get("sl_pct", 0.0))
    tp_pct = float(data.get("tp_pct", 0.0))

    try:
        # Check if individual leg files were uploaded
        if "file_leg1" in request.files and request.files["file_leg1"].filename:
            dataframes = []
            leg_idx = 1
            while f"file_leg{leg_idx}" in request.files and request.files[f"file_leg{leg_idx}"].filename:
                file = request.files[f"file_leg{leg_idx}"]
                df_leg = pd.read_csv(file)
                
                # Find datetime col
                dt_col = None
                for col in ['start_Time', 'datetime', 'Date', 'date', 'time', 'Timestamp', 'timestamp']:
                    if col in df_leg.columns:
                        dt_col = col
                        break
                if not dt_col:
                    raise ValueError(f"CSV for Leg {leg_idx} missing a valid datetime column.")
                
                # Find price col
                price_col = None
                for col in ['close', 'Close', 'price', 'LTP']:
                    if col in df_leg.columns:
                        price_col = col
                        break
                if not price_col:
                    raise ValueError(f"CSV for Leg {leg_idx} missing a valid price column (e.g. 'close').")
                
                # Standardize
                cols_to_keep = [dt_col, price_col]
                rename_dict = {price_col: f'leg{leg_idx}'}
                for opt_col in ['iv', 'spot', 'strike']:
                    if opt_col in df_leg.columns:
                        cols_to_keep.append(opt_col)
                        rename_dict[opt_col] = f'{opt_col}_{leg_idx-1}' # 0-indexed for backtester
                        
                df_leg = df_leg[cols_to_keep].rename(columns=rename_dict)
                df_leg[dt_col] = pd.to_datetime(df_leg[dt_col])
                
                dataframes.append(df_leg)
                leg_idx += 1
                
            # Merge all legs on datetime
            merged_df = dataframes[0]
            dt_col_name = merged_df.columns[0] # The datetime column name
            for df_leg in dataframes[1:]:
                dt_col_next = df_leg.columns[0]
                # Ensure same column name for merge
                df_leg = df_leg.rename(columns={dt_col_next: dt_col_name})
                merged_df = pd.merge(merged_df, df_leg, on=dt_col_name, how='inner')
                
            if merged_df.empty:
                raise ValueError("No overlapping timestamps found across the uploaded CSV files.")
                
            result = run_hedging_backtest_from_csv(merged_df, strategy, slippage, capital, qty_multiplier, sl_pct, tp_pct)

        elif "csv_file" in request.files and request.files["csv_file"].filename:
            file = request.files["csv_file"]
            df = pd.read_csv(file)
            result = run_hedging_backtest_from_csv(df, strategy, slippage, capital, qty_multiplier, sl_pct, tp_pct)
        else:
            client_id = data.get("client_id")
            dhan_pin = data.get("dhan_pin")
            dhan_totp = data.get("dhan_totp")
            access_token = data.get("access_token")
            symbol = data.get("symbol")
            expiry_flag = data.get("expiry_flag", "WEEK")
            from_date = data.get("from_date")
            to_date = data.get("to_date")
            timeframe = data.get("timeframe", "15")
            exchange = data.get("exchange", "INDEX")

            tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
            result = run_hedging_backtest(tsl, symbol, exchange, strategy, expiry_flag, from_date, to_date, timeframe, slippage, capital, qty_multiplier, sl_pct, tp_pct)
            
        return jsonify({"status": "success", "data": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/download_leg_csv", methods=["POST"])
def download_leg_csv():
    data = request.json
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    symbol = data.get("symbol")
    strategy = data.get("strategy")
    leg_index = int(data.get("leg_index"))
    expiry_flag = data.get("expiry_flag", "WEEK")
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    timeframe = data.get("timeframe", "15")
    exchange = data.get("exchange", "INDEX")

    try:
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
        from hedging_backtester import STRATEGIES
        if strategy not in STRATEGIES:
            return jsonify({"status": "error", "message": "Invalid strategy"}), 400
        
        legs = STRATEGIES[strategy]
        if leg_index < 0 or leg_index >= len(legs):
            return jsonify({"status": "error", "message": "Invalid leg index"}), 400
            
        opt_type, offset, action, qty = legs[leg_index]
        if offset == 0:
            strike_str = "ATM"
        else:
            strike_str = f"ATM+{offset}" if opt_type == "CALL" else f"ATM-{offset}"
            
        tf_int = int(timeframe.split()[0])
        
        df = tsl.get_expired_option_data(
            tradingsymbol=symbol, 
            exchange=exchange,
            interval=tf_int,
            expiry_flag=expiry_flag,
            expiry_code=1,
            strike=strike_str,
            option_type=opt_type,
            from_date=from_date,
            to_date=to_date
        )
        
        if df is None or df.empty:
            return jsonify({"status": "error", "message": f"No data returned for Leg {leg_index+1} ({opt_type} {strike_str})"}), 404
            
        csv_data = df.to_csv(index=False)
        filename = f"{symbol}_{strategy.replace(' ', '_')}_Leg{leg_index+1}_{opt_type}_{strike_str}_{from_date}_to_{to_date}.csv"
        
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/backtest", methods=["POST"])
def backtest():
    strategy_name = request.form.get("strategy_name", "EMA_WPR")
    ema_fast = int(request.form.get("ema_fast", 5))
    ema_mid = int(request.form.get("ema_mid", 15))
    ema_slow = int(request.form.get("ema_slow", 50))
    wpr_period = int(request.form.get("wpr_period", 70))
    rsi_period = int(request.form.get("rsi_period", 14))
    bb_period = int(request.form.get("bb_period", 20))
    oi_spike_pct = float(request.form.get("oi_spike_pct", 10.0))
    
    initial_capital = float(request.form.get("initial_capital", 100000.0))
    quantity_per_trade = int(request.form.get("quantity_per_trade", 1))

    df = None
    symbol = None

    if "csv_file" in request.files and request.files["csv_file"].filename:
        file = request.files["csv_file"]
        try:
            df = pd.read_csv(file)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Failed to read CSV: {e}"}), 400

    elif request.form.get("csv_filename"):
        filename = request.form.get("csv_filename")
        symbol = filename.split('_')[0] if '_' in filename else filename.split('.')[0]
        filepath = os.path.join(DOWNLOADS_DIR, filename)
        if not os.path.isfile(filepath):
            return jsonify({"status": "error", "message": f"File not found: {filename}"}), 400
        try:
            df = pd.read_csv(filepath)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Failed to read CSV: {e}"}), 400

    if df is None:
        return jsonify({"status": "error", "message": "No CSV provided. Upload a file or select from downloads."}), 400

    required = {"open", "high", "low", "close"}
    if not required.issubset(set(df.columns)):
        return jsonify({"status": "error", "message": f"CSV must have columns: {required}. Found: {list(df.columns)}"}), 400

    stop_loss_pct = float(request.form.get("stop_loss_pct", 2.0))
    target_pct = float(request.form.get("target_pct", 4.0))
    trailing_stop_pct = float(request.form.get("trailing_stop_pct", 0.0))
    timeframe = request.form.get("timeframe", "DAY")
    slippage_pct = float(request.form.get("slippage_pct", 0.1))
    trade_direction = request.form.get("trade_direction", "BOTH")

    result = run_backtest(
        df, 
        strategy_name=strategy_name,
        timeframe=timeframe,
        ema_fast=ema_fast, 
        ema_mid=ema_mid, 
        ema_slow=ema_slow, 
        wpr_period=wpr_period,
        rsi_period=rsi_period,
        bb_period=bb_period,
        oi_spike_pct=oi_spike_pct,
        stop_loss_pct=stop_loss_pct,
        target_pct=target_pct,
        trailing_stop_pct=trailing_stop_pct,
        slippage_pct=slippage_pct,
        initial_capital=initial_capital,
        quantity_per_trade=quantity_per_trade,
        trade_direction=trade_direction
    )
    if symbol:
        result["symbol"] = symbol

    return jsonify(result)

@app.route("/api/news", methods=["POST"])
def api_news():
    data = request.json
    gemini_key = data.get("gemini_key")
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    
    if not gemini_key:
        return jsonify({"status": "error", "message": "Gemini API Key is required for News sentiment."}), 400
        
    try:
        client = genai.Client(api_key=gemini_key)
        # Using gemini-2.5-flash as default for the new API
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to init Gemini: {e}"}), 400
        
    tsl = None
    if client_id and (access_token or (dhan_pin and dhan_totp)):
        try:
            tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
        except:
            pass

    # Top Nifty stocks for demonstration
    stocks = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "ICICIBANK"]
    
    # We will use Yahoo Finance RSS feeds
    results = []
    
    for symbol in stocks:
        feed_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}.NS&region=IN&lang=en-IN"
        try:
            feed = feedparser.parse(feed_url)
            
            headlines = []
            for entry in feed.entries[:3]:
                # Extract clean text from description
                soup = BeautifulSoup(entry.summary, "html.parser")
                text = soup.get_text(strip=True)
                headlines.append(f"{entry.title}: {text}")
                
            combined_news = "\\n".join(headlines)
            
            if not combined_news:
                sentiment_analysis = "No recent news available."
                indicator = "NEUTRAL"
            else:
                prompt = f"Analyze the following recent news for {symbol}:\\n{combined_news}\\n\\nBased purely on this news, provide a strict ONE WORD indicator (BULLISH, BEARISH, or NEUTRAL) followed by a | character, and then a 1-sentence justification."
                
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=prompt
                    )
                    ai_res = response.text
                    parts = ai_res.split('|')
                    if len(parts) >= 2:
                        indicator = parts[0].strip().upper()
                        sentiment_analysis = parts[1].strip()
                    else:
                        indicator = "NEUTRAL"
                        sentiment_analysis = ai_res.strip()
                except Exception as e:
                    indicator = "ERROR"
                    sentiment_analysis = f"Gemini API Error: {str(e)}"
            
            ltp = 0.0
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS", headers=headers, timeout=3)
                if res.status_code == 200:
                    ltp = float(res.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])
            except:
                pass
                
            results.append({
                "symbol": symbol,
                "ltp": ltp,
                "indicator": indicator,
                "sentiment": sentiment_analysis,
                "headlines": [h.split(':')[0] for h in headlines] # Just titles for UI
            })
            
        except Exception as e:
            results.append({
                "symbol": symbol,
                "ltp": 0.0,
                "indicator": "ERROR",
                "sentiment": str(e),
                "headlines": []
            })
            
    return jsonify({"status": "success", "news": results})

from scanner_backend import start_scanner, stop_scanner, get_scanner_state, get_paper_trades
from crypto_scanner import start_crypto_scanner, stop_crypto_scanner, delta_request, DB_NAME as CRYPTO_DB
from scanner_backend import start_scanner, stop_scanner, get_dashboard_state, run_screener

@app.route("/api/algoscan/screen", methods=["POST"])
def api_algoscan_screen():
    data = request.json
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    strategy_name = data.get("strategy_name", "WPR_CROSS_EMA")
    watchlists = data.get("watchlists", ["nifty50"])
    custom_symbols = data.get("custom_symbols", "")
    if not client_id or (not access_token and (not dhan_pin or not dhan_totp)):
        return jsonify({"status": "error", "message": "Dhan credentials required"}), 400
    res = run_screener(client_id, access_token, dhan_pin, dhan_totp, strategy_name, watchlists, custom_symbols)
    return jsonify(res)

@app.route("/api/algoscan/start", methods=["POST"])
def api_algoscan_start():
    data = request.json
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    tg_bot = data.get("tg_bot")
    tg_chat = data.get("tg_chat")
    gemini_key = data.get("gemini_key")
    strategy_name = data.get("strategy_name", "WPR_CROSS_EMA")
    watchlists = data.get("watchlists", ["nifty50"])
    custom_symbols = data.get("custom_symbols", "")
    if not client_id or (not access_token and (not dhan_pin or not dhan_totp)):
        return jsonify({"status": "error", "message": "Dhan credentials required"}), 400
    res = start_scanner(client_id, access_token, dhan_pin, dhan_totp, tg_bot, tg_chat, gemini_key, strategy_name, watchlists, custom_symbols)
    return jsonify(res)

@app.route("/api/algoscan/stop", methods=["POST"])
def api_algoscan_stop():
    res = stop_scanner()
    return jsonify(res)

@app.route("/api/algoscan/state", methods=["GET"])
def api_algoscan_state():
    res = get_dashboard_state()
    return jsonify(res)

@app.route("/api/algoscan/clear", methods=["POST"])
def api_algoscan_clear():
    try:
        import sqlite3
        conn = sqlite3.connect('algo_lab.db')
        c = conn.cursor()
        c.execute("DELETE FROM scan_state")
        c.execute("DELETE FROM paper_trades")
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Database cleared successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/algoscan/trade", methods=["POST"])
def api_algoscan_trade():
    data = request.json
    client_id = data.get("client_id")
    dhan_pin = data.get("dhan_pin")
    dhan_totp = data.get("dhan_totp")
    access_token = data.get("access_token")
    symbol = data.get("symbol")
    trade_type = data.get("trade_type", "LONG")
    qty = int(data.get("qty", 1))
    limit_price = float(data.get("price", 0))
    sl = float(data.get("sl", 0))
    tgt = float(data.get("tgt", 0))
    tg_bot = data.get("tg_bot")
    tg_chat = data.get("tg_chat")
    
    product_type = data.get("product_type", "MIS")
    is_amo = data.get("is_amo", False)
    
    if not client_id or (not access_token and (not dhan_pin or not dhan_totp)):
        return jsonify({"status": "error", "message": "Dhan credentials required"}), 400
        
    try:
        from Dhan_Tradehull import Tradehull
        tsl = Tradehull(client_id, mode="pin_totp", pin=dhan_pin, totp_secret=dhan_totp) if dhan_pin and dhan_totp else Tradehull(client_id, access_token, mode="access_token")
        access_token = tsl.token_id
        
        transaction_type = "BUY" if trade_type == "LONG" else "SELL"
        
        # Super Orders don't support AMO or CNC properly, so we use regular limit orders for those
        if is_amo or product_type == "CNC":
            import requests
            
            payload = {
                "dhanClientId": client_id,
                "transactionType": transaction_type,
                "exchangeSegment": "NSE_EQ",
                "productType": "CNC" if product_type == "CNC" else "INTRADAY",
                "orderType": "LIMIT",
                "validity": "DAY",
                "securityId": str(tsl._resolve_security_id(symbol, "NSE")),
                "quantity": qty,
                "disclosedQuantity": 0,
                "price": limit_price,
                "triggerPrice": 0.0,
                "afterMarketOrder": True if is_amo else False
            }
            
            if is_amo:
                payload["amoTime"] = "OPEN"
                
            headers = {
                "Content-Type": "application/json",
                "access-token": access_token
            }
            
            resp = requests.post("https://api.dhan.co/v2/orders", json=payload, headers=headers)
            try:
                resp_data = resp.json()
            except:
                resp_data = {"status": "failure", "remarks": {"error_message": resp.text}}
                
            if resp_data.get("status") == "success" or resp_data.get("orderId"):
                order_id = resp_data.get("orderId") or resp_data.get("data", {}).get("orderId", "AMO_PLACED")
                
                # Attach Forever Order (GTT OCO) if SL and TGT are provided for a Delivery (CNC) BUY
                if product_type == "CNC" and transaction_type == "BUY" and sl > 0 and tgt > 0:
                    try:
                        fid = tsl.place_forever_order(
                            tradingsymbol=symbol, exchange="NSE",
                            transaction_type="SELL", quantity=qty,
                            order_type="LIMIT", trade_type="CNC",
                            price=tgt, trigger_price=tgt,
                            order_flag="OCO",
                            quantity_1=qty, price_1=sl, trigger_price_1=sl
                        )
                        order_id = f"{order_id} + GTT:{fid}"
                    except Exception as e:
                        print(f"GTT Failed: {e}")
            else:
                error_msg = resp_data.get("remarks", {}).get("error_message", str(resp_data))
                return jsonify({"status": "error", "message": f"Order rejected: {error_msg} | Payload Sent: {str(payload)}"}), 400

                
        else:
            order_id = tsl.place_super_order(
                tradingsymbol=symbol, 
                exchange="NSE",
                transaction_type=transaction_type, 
                quantity=qty,
                order_type="LIMIT", 
                trade_type="MIS",
                price=limit_price, 
                target_price=tgt,
                stop_loss_price=sl,
                trailing_jump=0.0
            )
            
            if order_id is None or order_id == "":
                return jsonify({
                    "status": "error",
                    "message": f"Order rejected by broker. This usually happens if the market is closed, margin is insufficient, or credentials expired. Attempted: {qty} {symbol} at {limit_price}"
                }), 400

            
        msg = f"LIVE TRADE: {transaction_type} {qty} {symbol} at {limit_price}. SL: {sl}, TGT: {tgt} (Order ID: {order_id})"
        if tg_bot and tg_chat:
            try:
                tsl.send_telegram_alert(message=msg, receiver_chat_id=tg_chat, bot_token=tg_bot)
            except Exception as tg_err:
                pass # Ignore telegram errors so trade still succeeds on frontend
                
        return jsonify({
            "status": "success", 
            "message": msg,
            "order_id": order_id
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/crypto/start", methods=["POST"])
def api_start_crypto():
    data = request.json
    api_key = data.get("delta_api_key")
    api_secret = data.get("delta_api_secret")
    tg_bot = data.get("tg_bot")
    tg_chat = data.get("tg_chat")
    
    if not api_key or not api_secret:
        return jsonify({"status": "error", "message": "Delta credentials required"}), 400
        
    # Test connection
    res = delta_request('GET', '/v2/wallet/balances', api_key, api_secret)
    if res and res.status_code == 200:
        start_crypto_scanner(api_key, api_secret, tg_bot, tg_chat)
        start_telegram_listener("dummy", "dummy", None, None, tg_bot, tg_chat)
        return jsonify({"status": "success", "message": "Crypto Scanner Started!"})
    else:
        err = res.text if res else "Connection Error"
        return jsonify({"status": "error", "message": f"Delta Auth Failed: {err}"}), 400

@app.route("/api/crypto/stop", methods=["POST"])
def api_stop_crypto():
    stop_crypto_scanner()
    return jsonify({"status": "success", "message": "Crypto Scanner Stopped"})

@app.route("/api/crypto/trades", methods=["GET"])
def api_crypto_trades():
    import sqlite3
    try:
        conn = sqlite3.connect(CRYPTO_DB)
        c = conn.cursor()
        c.execute("SELECT * FROM crypto_trades ORDER BY id DESC LIMIT 50")
        columns = [description[0] for description in c.description]
        trades = [dict(zip(columns, row)) for row in c.fetchall()]
        conn.close()
        return jsonify(trades)
    except Exception as e:
        return jsonify([])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
