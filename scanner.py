import os
from Dhan_Tradehull import Tradehull


def compute_signals(df, ema_fast=5, ema_mid=15, ema_slow=50, wpr_period=70):
    """Compute EMA crossover + Williams %R signals on a DataFrame.
    
    Returns the DataFrame with indicator columns added, plus the signal string
    ('BULLISH', 'BEARISH', or 'NEUTRAL') and the last row's indicator values.
    """
    if df is None or len(df) < max(ema_slow, wpr_period):
        return None, "NEUTRAL", {}

    df['EMA_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
    df['EMA_mid']  = df['close'].ewm(span=ema_mid, adjust=False).mean()
    df['EMA_slow'] = df['close'].ewm(span=ema_slow, adjust=False).mean()
    hh, ll = df['high'].rolling(wpr_period).max(), df['low'].rolling(wpr_period).min()
    df['WPR'] = (hh - df['close']) / (hh - ll) * -100

    rc, pc = df.iloc[-1], df.iloc[-2]

    bullish = (
        (pc['EMA_fast'] <= pc['EMA_mid'] and rc['EMA_fast'] > rc['EMA_mid'])
        and (rc['close'] > rc['EMA_slow'])
        and (rc['WPR'] > -50)
    )
    bearish = (
        (pc['EMA_fast'] >= pc['EMA_mid'] and rc['EMA_fast'] < rc['EMA_mid'])
        and (rc['close'] < rc['EMA_slow'])
        and (rc['WPR'] < -50)
    )

    signal = "BULLISH" if bullish else "BEARISH" if bearish else "NEUTRAL"
    indicators = {
        "ema_fast": round(float(rc['EMA_fast']), 2),
        "ema_mid":  round(float(rc['EMA_mid']), 2),
        "ema_slow": round(float(rc['EMA_slow']), 2),
        "wpr":      round(float(rc['WPR']), 2),
    }
    return df, signal, indicators


def run_scan(client_id, access_token, tg_bot=None, tg_chat=None):
    if not client_id or not access_token:
        return {"status": "error", "message": "Missing credentials"}
        
    try:
        tsl = Tradehull(client_id, access_token, mode="access_token")
    except Exception as e:
        return {"status": "error", "message": str(e)}

    startup_msg = "Telegram not configured. Add Telegram Token and Chat ID to get startup balance alerts."
    # Send startup message if Telegram is configured
    if tg_bot and tg_chat:
        try:
            balance = tsl.get_balance()
            pos_df = tsl.get_positions()
            
            open_pos, closed_pos = 0, 0
            if pos_df is not None and not pos_df.empty and 'positionType' in pos_df.columns:
                open_pos = len(pos_df[pos_df['positionType'] == 'OPEN'])
                closed_pos = len(pos_df[pos_df['positionType'] == 'CLOSED'])
                
            startup_msg = f"Scanner Connected! Balance: ₹{balance} | Positions: {open_pos} Open, {closed_pos} Closed"
            tsl.send_telegram_alert(startup_msg, tg_chat, tg_bot)
        except Exception as e:
            startup_msg = f"Failed to retrieve balance/positions from Dhan: {str(e)}"
            print(f"Failed to send startup message: {e}")

    symbols = [("RELIANCE", "NSE"), ("TCS", "NSE"), ("CRUDEOIL", "MCX"), ("GOLD", "MCX")]
    results = []

    for sym, exc in symbols:
        tf = "60" if exc == "MCX" else "DAY"
        try:
            df = tsl.get_historical_data(tradingsymbol=sym, exchange=exc, timeframe=tf)
        except Exception as e:
            results.append({"symbol": sym, "status": "ERROR", "message": str(e)})
            continue
            
        df, signal, ind = compute_signals(df)
        if df is None:
            results.append({"symbol": sym, "status": "ERROR", "message": "Not enough data"})
            continue
                 
        if signal in ["BULLISH", "BEARISH"] and tg_bot and tg_chat:
            rc = df.iloc[-1]
            msg = f"🚨 {signal} 🚨\nSym: {sym}\nClose: {rc['close']}\n5EMA: {ind['ema_fast']}\n15EMA: {ind['ema_mid']}\n50EMA: {ind['ema_slow']}\nWPR70: {ind['wpr']}"
            try:
                tsl.send_telegram_alert(msg, tg_chat, tg_bot)
            except Exception as e:
                print(f"Telegram alert failed: {e}")
                
        results.append({
            "symbol": sym,
            "ltp": round(float(df.iloc[-1]['close']), 2),
            "ema5": ind["ema_fast"],
            "ema15": ind["ema_mid"],
            "ema50": ind["ema_slow"],
            "wpr70": ind["wpr"],
            "signal": signal,
            "status": "SUCCESS"
        })
        
    return {"status": "success", "startup_msg": startup_msg, "results": results}
