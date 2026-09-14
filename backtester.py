"""Backtesting engine — runs various strategies on historical CSV data.

Supports multiple strategies, Long-Only trades, and Pyramiding based on Capital.
"""

import pandas as pd

def run_backtest(df, strategy_name="EMA_WPR", timeframe="DAY", 
                 ema_fast=5, ema_mid=15, ema_slow=50, wpr_period=70, rsi_period=14, bb_period=20, oi_spike_pct=10,
                 stop_loss_pct=2.0, target_pct=4.0, trailing_stop_pct=0.0, slippage_pct=0.1,
                 initial_capital=100000.0, quantity_per_trade=1):
    """Run backtest on a DataFrame with OHLCV data.
    
    Returns dict with summary stats, trade log, and equity curve.
    """
    if df is None or len(df) < 50:
        return {"status": "error", "message": f"Need at least 50 candles, got {len(df) if df is not None else 0}"}

    df = df.copy()
    
    # Standardize datetime format for entry/exit logs
    if 'timestamp' in df.columns:
        # Convert to datetime and then to string format for consistency
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    elif 'start_Time' in df.columns:
        df['timestamp'] = pd.to_datetime(df['start_Time'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
    elif 'date' in df.columns:
        df['timestamp'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')
        
    # Pre-compute indicators based on strategy
    if strategy_name == "EMA_WPR" or strategy_name == "EMA_SIMPLE":
        df['EMA_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
        df['EMA_mid']  = df['close'].ewm(span=ema_mid, adjust=False).mean()
        if strategy_name == "EMA_WPR":
            df['EMA_slow'] = df['close'].ewm(span=ema_slow, adjust=False).mean()
            hh = df['high'].rolling(wpr_period).max()
            ll = df['low'].rolling(wpr_period).min()
            df['WPR'] = (hh - df['close']) / (hh - ll) * -100
            
    elif strategy_name == "RSI_MR":
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
    elif strategy_name == "MACD_TF":
        fast_ema = df['close'].ewm(span=ema_fast, adjust=False).mean()
        slow_ema = df['close'].ewm(span=ema_mid, adjust=False).mean()
        df['MACD'] = fast_ema - slow_ema
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
    elif strategy_name == "BB_BREAKOUT":
        df['BB_mid'] = df['close'].rolling(window=bb_period).mean()
        df['BB_std'] = df['close'].rolling(window=bb_period).std()
        df['BB_upper'] = df['BB_mid'] + (2 * df['BB_std'])
        df['BB_lower'] = df['BB_mid'] - (2 * df['BB_std'])
        
    elif strategy_name == "OI_BREAKOUT":
        if 'oi' in df.columns or 'open_interest' in df.columns:
            oi_col = 'oi' if 'oi' in df.columns else 'open_interest'
            # Calculate % change in OI
            df['OI_pct_change'] = df[oi_col].pct_change() * 100
        else:
            return {"status": "error", "message": "OI (Open Interest) data is missing in the CSV for this strategy."}

    trades = []
    equity_curve_pnl = [0.0]  # Tracks cumulative total P&L in %
    
    available_capital = float(initial_capital)
    active_positions = [] # List of dictionaries

    # Use a generic starting index to ensure all indicators are warmed up
    start_idx = max([ema_fast, ema_mid, ema_slow, wpr_period, rsi_period, bb_period, 50]) + 1
    if start_idx >= len(df):
         return {"status": "error", "message": f"Not enough data. Need at least {start_idx} candles."}

    for i in range(start_idx, len(df) - 1):
        rc = df.iloc[i]      # current candle
        pc = df.iloc[i - 1]  # previous candle
        
        long_indicator_exit = False
        bullish_entry = False

        # --- Strategy Logic (LONG ONLY) ---
        if strategy_name == "EMA_WPR":
            bullish_entry = (
                (pc['EMA_fast'] <= pc['EMA_mid'] and rc['EMA_fast'] > rc['EMA_mid'])
                and (rc['close'] > rc['EMA_slow'])
                and (rc['WPR'] > -50)
            )
            long_indicator_exit = (rc['EMA_fast'] < rc['EMA_slow'])
            
        elif strategy_name == "EMA_SIMPLE":
            bullish_entry = (pc['EMA_fast'] <= pc['EMA_mid'] and rc['EMA_fast'] > rc['EMA_mid'])
            long_indicator_exit = (pc['EMA_fast'] >= pc['EMA_mid'] and rc['EMA_fast'] < rc['EMA_mid'])
            
        elif strategy_name == "RSI_MR":
            bullish_entry = (pc['RSI'] >= 30 and rc['RSI'] < 30)
            long_indicator_exit = (rc['RSI'] > 50)
            
        elif strategy_name == "MACD_TF":
            bullish_entry = (pc['MACD'] <= pc['Signal_Line'] and rc['MACD'] > rc['Signal_Line'])
            long_indicator_exit = (pc['MACD'] >= pc['Signal_Line'] and rc['MACD'] < rc['Signal_Line'])
            
        elif strategy_name == "BB_BREAKOUT":
            bullish_entry = (pc['close'] <= pc['BB_upper'] and rc['close'] > rc['BB_upper'])
            long_indicator_exit = (rc['close'] < rc['BB_mid'])
            
        elif strategy_name == "OI_BREAKOUT":
            # OI Spike AND Price Breakout (close > previous high)
            oi_spike = rc.get('OI_pct_change', 0) > oi_spike_pct
            price_breakout = rc['close'] > pc['high']
            bullish_entry = oi_spike and price_breakout
            # Exit if price drops below previous candle's low
            long_indicator_exit = rc['close'] < pc['low']

        # --- Execution Logic ---
        next_open = float(df.iloc[i + 1]['open'])
        next_ts = str(df.iloc[i + 1]['timestamp']) if 'timestamp' in df.columns else str(i + 1)
        
        # 1. Check for Exits on all active positions
        remaining_positions = []
        for pos in active_positions:
            if rc['high'] > pos["highest_high"]:
                pos["highest_high"] = rc['high']
                
            sl_price = pos["entry_price"] * (1 - stop_loss_pct / 100.0)
            tp_price = pos["entry_price"] * (1 + target_pct / 100.0)
            ts_price = pos["highest_high"] * (1 - trailing_stop_pct / 100.0) if trailing_stop_pct > 0 else 0
            
            exit_price = None
            exit_reason = None
            
            if long_indicator_exit:
                exit_price = next_open
                exit_reason = 'INDICATOR'
            elif rc['low'] <= sl_price:
                exit_price = min(sl_price, rc['open']) # use worst price
                exit_reason = 'SL'
            elif rc['high'] >= tp_price:
                exit_price = max(tp_price, rc['open'])
                exit_reason = 'TARGET'
            elif trailing_stop_pct > 0 and rc['low'] <= ts_price:
                exit_price = min(ts_price, rc['open'])
                exit_reason = 'TRAILING'
                
            if exit_reason:
                # Apply slippage (selling lower)
                exit_price = exit_price * (1 - slippage_pct / 100.0)
                
                pnl_abs = (exit_price - pos["entry_price"]) * pos["quantity"]
                pnl_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
                
                # Release capital and add PnL
                available_capital += pos["capital_used"] + pnl_abs
                
                trades.append({
                    "entry_date": pos["entry_date"],
                    "exit_date": next_ts if 'INDICATOR' in exit_reason else (str(rc['timestamp']) if 'timestamp' in df.columns else str(i)),
                    "entry_price": round(pos["entry_price"], 2),
                    "exit_price": round(exit_price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "quantity": pos["quantity"],
                    "capital_used": round(pos["capital_used"], 2),
                    "exit_reason": exit_reason,
                    "bars_held": i - pos["entry_idx"]
                })
                
                # Record total cumulative account PnL % based on initial capital
                account_pnl_pct = ((available_capital - initial_capital) / initial_capital) * 100
                equity_curve_pnl.append(round(account_pnl_pct, 2))
            else:
                remaining_positions.append(pos)
                
        active_positions = remaining_positions

        # 2. Check for New Entries
        if bullish_entry:
            # Apply slippage (buying higher)
            entry_price = next_open * (1 + slippage_pct / 100.0)
            required_capital = entry_price * quantity_per_trade
            if available_capital >= required_capital:
                available_capital -= required_capital
                active_positions.append({
                    "entry_price": entry_price,
                    "entry_date": next_ts,
                    "entry_idx": i + 1,
                    "quantity": quantity_per_trade,
                    "capital_used": required_capital,
                    "highest_high": entry_price
                })

    # Close any open positions at the end of data
    for pos in active_positions:
        rc = df.iloc[-1]
        exit_price = float(rc['close']) * (1 - slippage_pct / 100.0)
        
        pnl_abs = (exit_price - pos["entry_price"]) * pos["quantity"]
        pnl_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
        
        available_capital += pos["capital_used"] + pnl_abs
        
        trades.append({
            "entry_date": pos["entry_date"],
            "exit_date": str(rc['timestamp']) if 'timestamp' in df.columns else str(len(df)-1) + " (forced)",
            "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(exit_price, 2),
            "pnl_pct": round(pnl_pct, 2),
            "quantity": pos["quantity"],
            "capital_used": round(pos["capital_used"], 2),
            "exit_reason": "FORCED (L)",
            "bars_held": len(df) - 1 - pos["entry_idx"]
        })
        
        account_pnl_pct = ((available_capital - initial_capital) / initial_capital) * 100
        equity_curve_pnl.append(round(account_pnl_pct, 2))

    # Calculate summary metrics
    total_trades = len(trades)
    if total_trades > 0:
        winning = sum(1 for t in trades if t["pnl_pct"] > 0)
        win_rate = round(winning / total_trades * 100, 1)
        total_pnl = round(equity_curve_pnl[-1], 2)
        avg_bars = round(sum(t["bars_held"] for t in trades) / total_trades, 1)
        
        peak = 0
        max_dd = 0
        for eq in equity_curve_pnl:
            if eq > peak:
                peak = eq
            dd = eq - peak
            if dd < max_dd:
                max_dd = dd
        
        max_drawdown = round(max_dd, 2)
    else:
        win_rate = 0.0
        total_pnl = 0.0
        max_drawdown = 0.0
        avg_bars = 0.0

    return {
        "status": "success",
        "summary": {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_pnl_pct": total_pnl,
            "max_drawdown_pct": max_drawdown,
            "avg_bars_held": avg_bars,
            "final_capital": round(available_capital, 2)
        },
        "trades": trades,
        "equity_curve": equity_curve_pnl
    }
