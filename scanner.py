import os
from Dhan_Tradehull import Tradehull

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
            
        if df is None or len(df) < 70:
            results.append({"symbol": sym, "status": "ERROR", "message": "Not enough data"})
            continue
        
        df['EMA_5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['EMA_15'] = df['close'].ewm(span=15, adjust=False).mean()
        df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
        hh, ll = df['high'].rolling(70).max(), df['low'].rolling(70).min()
        df['WPR_70'] = (hh - df['close']) / (hh - ll) * -100
        
        rc, pc = df.iloc[-1], df.iloc[-2]
        
        bullish = (pc['EMA_5'] <= pc['EMA_15'] and rc['EMA_5'] > rc['EMA_15']) and (rc['close'] > rc['EMA_50']) and (rc['WPR_70'] > -50)
        bearish = (pc['EMA_5'] >= pc['EMA_15'] and rc['EMA_5'] < rc['EMA_15']) and (rc['close'] < rc['EMA_50']) and (rc['WPR_70'] < -50)
        
        signal = "BULLISH" if bullish else "BEARISH" if bearish else "NEUTRAL"
                 
        if signal in ["BULLISH", "BEARISH"] and tg_bot and tg_chat:
            msg = f"🚨 {signal} 🚨\nSym: {sym}\nClose: {rc['close']}\n5EMA: {rc['EMA_5']:.2f}\n15EMA: {rc['EMA_15']:.2f}\n50EMA: {rc['EMA_50']:.2f}\nWPR70: {rc['WPR_70']:.2f}"
            try:
                tsl.send_telegram_alert(msg, tg_chat, tg_bot)
            except Exception as e:
                print(f"Telegram alert failed: {e}")
                
        results.append({
            "symbol": sym,
            "ltp": round(float(rc['close']), 2),
            "ema5": round(float(rc['EMA_5']), 2),
            "ema15": round(float(rc['EMA_15']), 2),
            "ema50": round(float(rc['EMA_50']), 2),
            "wpr70": round(float(rc['WPR_70']), 2),
            "signal": signal,
            "status": "SUCCESS"
        })
        
    return {"status": "success", "startup_msg": startup_msg, "results": results}
