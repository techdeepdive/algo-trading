import pandas as pd
import numpy as np
from datetime import datetime

# Dictionary of strategies and their leg offsets from ATM.
# Format: (OptionType, OffsetFromATM, Buy/Sell, QtyMultiplier)
# Offset > 0 means OTM for both CE and PE. Offset < 0 means ITM. Offset = 0 means ATM.
# Note: For CE, ATM+1 means a higher strike. For PE, ATM+1 means a lower strike.
STRATEGIES = {
    "Long Straddle": [
        ("CALL", 0, "BUY", 1),
        ("PUT", 0, "BUY", 1)
    ],
    "Short Straddle": [
        ("CALL", 0, "SELL", 1),
        ("PUT", 0, "SELL", 1)
    ],
    "Long Strangle": [
        ("CALL", 2, "BUY", 1),  # ATM + 2 strikes OTM
        ("PUT", 2, "BUY", 1)    # ATM - 2 strikes OTM
    ],
    "Short Strangle": [
        ("CALL", 2, "SELL", 1),
        ("PUT", 2, "SELL", 1)
    ],
    "Long Iron Condor": [
        # Sell an OTM Strangle, Buy a further OTM Strangle to cap risk
        ("CALL", 2, "SELL", 1),
        ("PUT", 2, "SELL", 1),
        ("CALL", 4, "BUY", 1),
        ("PUT", 4, "BUY", 1)
    ],
    "Short Iron Condor": [
        ("CALL", 2, "BUY", 1),
        ("PUT", 2, "BUY", 1),
        ("CALL", 4, "SELL", 1),
        ("PUT", 4, "SELL", 1)
    ],
    "Long Butterfly (Call)": [
        ("CALL", 0, "BUY", 1),   # Buy ATM
        ("CALL", 2, "SELL", 2),  # Sell 2x OTM
        ("CALL", 4, "BUY", 1)    # Buy further OTM
    ],
    "Bull Call Spread": [
        ("CALL", 0, "BUY", 1),
        ("CALL", 2, "SELL", 1)
    ],
    "Bear Put Spread": [
        ("PUT", 0, "BUY", 1),
        ("PUT", 2, "SELL", 1)
    ]
}

def get_strategy_payoff(tsl, symbol, exchange, strategy_name, num_strikes=20):
    """
    Simulates the payoff for a given strategy based on the current option chain.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    res = tsl.get_option_chain(Underlying=symbol, exchange=exchange, expiry=0, num_strikes=num_strikes)
    if res is None:
        raise ValueError("Could not fetch option chain. The market might be closed, or the symbol is invalid.")
    atm, chain = res
    if chain is None or chain.empty:
        raise ValueError("Option chain data is empty.")

    # Sort chain by Strike Price
    chain = chain.sort_values("Strike Price").reset_index(drop=True)
    
    atm_idx = chain[chain['Strike Price'] == atm].index
    if len(atm_idx) == 0:
        raise ValueError(f"ATM strike {atm} not found in the fetched chain.")
    atm_idx = atm_idx[0]

    legs = STRATEGIES[strategy_name]
    positions = []
    total_premium_paid = 0
    total_premium_received = 0

    for opt_type, offset, action, qty in legs:
        # Determine the strike index in the sorted chain
        if opt_type == "CALL":
            idx = atm_idx + offset
        else:
            idx = atm_idx - offset  # For PE, positive offset (OTM) means a lower strike
            
        if idx < 0 or idx >= len(chain):
            raise ValueError(f"Required strike offset {offset} is out of bounds for the fetched chain. Need more strikes.")
            
        strike = chain.loc[idx, 'Strike Price']
        ltp_col = "CE LTP" if opt_type == "CALL" else "PE LTP"
        ltp = chain.loc[idx, ltp_col]
        
        if pd.isna(ltp) or ltp <= 0:
            raise ValueError(f"Invalid LTP for {opt_type} at strike {strike}.")

        positions.append({
            "strike": strike,
            "type": opt_type,
            "action": action,
            "qty": qty,
            "price": float(ltp)
        })

        if action == "BUY":
            total_premium_paid += (ltp * qty)
        else:
            total_premium_received += (ltp * qty)

    # Generate Payoff Data Points
    # We will simulate the underlying price moving +/- (num_strikes/2) strikes
    strike_diff = chain.iloc[1]['Strike Price'] - chain.iloc[0]['Strike Price'] if len(chain) > 1 else 100
    min_price = atm - (strike_diff * (num_strikes // 2))
    max_price = atm + (strike_diff * (num_strikes // 2))
    
    sim_prices = np.linspace(min_price, max_price, 50)
    payoff_curve = []

    for p in sim_prices:
        net_pnl = 0
        for pos in positions:
            if pos["type"] == "CALL":
                # Call intrinsic value at expiry
                intrinsic = max(0, p - pos["strike"])
            else:
                # Put intrinsic value at expiry
                intrinsic = max(0, pos["strike"] - p)
                
            if pos["action"] == "BUY":
                pnl = (intrinsic - pos["price"]) * pos["qty"]
            else:
                pnl = (pos["price"] - intrinsic) * pos["qty"]
                
            net_pnl += pnl
            
        payoff_curve.append({
            "underlying_price": round(p, 2),
            "pnl": round(net_pnl, 2)
        })

    max_profit = max([x["pnl"] for x in payoff_curve])
    max_loss = min([x["pnl"] for x in payoff_curve])

    return {
        "atm": atm,
        "positions": positions,
        "payoff_curve": payoff_curve,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "net_premium": round(total_premium_received - total_premium_paid, 2)
    }


def run_hedging_backtest(tsl, symbol, exchange, strategy_name, expiry_flag, from_date, to_date, timeframe="15", slippage_pct=0.0, capital=100000, qty_multiplier=1, sl_pct=0, tp_pct=0):
    """
    Backtests a multi-leg strategy.
    Note: For a robust implementation over months, we'd iterate week by week, finding the ATM strike on Friday,
    fetching the 4 legs, simulating till Thursday, then moving to the next week.
    Due to API rate limits and time, this MVP backtester runs on a single expiry period defined by from_date to to_date.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_name}")
        
    tf_int = timeframe if timeframe == "DAY" else int(timeframe)
    legs = STRATEGIES[strategy_name]
    
    # In a full backtest, we would fetch historical spot data first to find the ATM strike at from_date.
    # Since Tradehull's get_expired_option_data handles "ATM", "ATM+1" relative to the underlying automatically 
    # per expiry, we can just use those strings!
    
    dataframes = []
    leg_details = []
    
    for i, (opt_type, offset, action, qty) in enumerate(legs):
        # Format strike for Tradehull: "ATM", "ATM+1", "ATM-1", etc.
        # Note: Tradehull expects "ATM+2" for CE OTM, and "ATM-2" for PE OTM.
        if offset == 0:
            strike_str = "ATM"
        else:
            if opt_type == "CALL":
                strike_str = f"ATM+{offset}"
            else:
                # For PE, OTM means lower strike. Tradehull uses ATM- offset for lower strikes.
                strike_str = f"ATM-{offset}"
                
        try:
            df = tsl.get_expired_option_data(
                tradingsymbol=symbol, 
                exchange=exchange,
                interval=tf_int,
                expiry_flag=expiry_flag,
                expiry_code=1, # Near expiry
                strike=strike_str,
                option_type=opt_type,
                from_date=from_date,
                to_date=to_date
            )
            
            if df is None or df.empty:
                raise ValueError(f"No data for leg {opt_type} {strike_str}")
                
            # Determine the time column name
            dt_col = 'datetime' if 'datetime' in df.columns else 'start_Time'
            
            try:
                df = df[[dt_col, 'close', 'iv', 'spot', 'strike']]
            except KeyError:
                # Fallback if iv/spot/strike not available
                try:
                    df = df[[dt_col, 'close']]
                    df['iv'] = 0
                    df['spot'] = 0
                    df['strike'] = 0
                except KeyError:
                    raise ValueError(f"Error fetching data for leg {i+1} ({opt_type} {strike_str}): missing time or close column.")
                
            df = df.rename(columns={'close': f'price_{i}', dt_col: 'start_Time', 'iv': f'iv_{i}', 'spot': f'spot_{i}', 'strike': f'strike_{i}'})
            df['start_Time'] = pd.to_datetime(df['start_Time'])
            
            dataframes.append(df)
            leg_details.append({"type": opt_type, "action": action, "qty": qty * qty_multiplier, "strike_str": strike_str})
            
        except Exception as e:
            raise ValueError(f"Error fetching data for leg {i+1} ({opt_type} {strike_str}): {str(e)}")
            
    # Merge all leg DataFrames on timestamp
    merged_df = dataframes[0]
    for df in dataframes[1:]:
        merged_df = pd.merge(merged_df, df, on='start_Time', how='inner')
        
    if merged_df.empty:
        raise ValueError("No overlapping timestamps found across all strategy legs.")
        
    merged_df = merged_df.sort_values('start_Time').reset_index(drop=True)
    
    # Calculate net portfolio value over time
    equity_curve = []
    
    # Entry prices at the first timestamp
    entry_prices = {}
    for i in range(len(legs)):
        row0 = merged_df.iloc[0]
        p = row0[f'price_{i}']
        if leg_details[i]["action"] == "BUY":
            p = p * (1 + (slippage_pct / 100))
        else:
            p = p * (1 - (slippage_pct / 100))
        entry_prices[i] = p
        
        leg_details[i]["entry_price"] = round(p, 2)
        leg_details[i]["entry_time"] = row0['start_Time'].strftime("%Y-%m-%d %H:%M")
        leg_details[i]["capital_used"] = round(p * leg_details[i]["qty"], 2)
        
        try:
            S = float(row0[f'spot_{i}'])
            K = float(row0[f'strike_{i}'])
            iv = float(row0[f'iv_{i}'])
            leg_details[i]["spot_entry"] = S
            leg_details[i]["strike_val"] = K
            leg_details[i]["iv"] = round(iv, 2)
        except (ValueError, KeyError, TypeError):
            leg_details[i]["spot_entry"] = 0
            leg_details[i]["strike_val"] = 0
            leg_details[i]["iv"] = 0
        
    peak_capital = capital
    max_drawdown = 0
    current_capital = capital
    exit_idx = len(merged_df) - 1

    # Calculate PNL at each timestamp
    for idx, row in merged_df.iterrows():
        net_pnl = 0
        for i in range(len(legs)):
            current_p = row[f'price_{i}']
            entry_p = entry_prices[i]
            qty = leg_details[i]["qty"]
            
            if leg_details[i]["action"] == "BUY":
                pnl = (current_p - entry_p) * qty
            else:
                pnl = (entry_p - current_p) * qty
                
            net_pnl += pnl
            
        current_capital = capital + net_pnl
        if current_capital > peak_capital:
            peak_capital = current_capital
            
        dd = (peak_capital - current_capital) / peak_capital * 100 if peak_capital > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd
            
        equity_curve.append({
            "step": row['start_Time'].strftime("%Y-%m-%d %H:%M"),
            "return": round(net_pnl, 2)
        })
        
        # Check SL/TP
        if sl_pct > 0 and net_pnl <= - (capital * (sl_pct / 100)):
            exit_idx = idx
            break
        if tp_pct > 0 and net_pnl >= (capital * (tp_pct / 100)):
            exit_idx = idx
            break
            
    # Final trade log summary
    final_pnl = equity_curve[-1]["return"]
    
    # Apply exit slippage to final PNL
    exit_slippage_cost = 0
    for i in range(len(legs)):
        final_p = merged_df.iloc[exit_idx][f'price_{i}']
        if leg_details[i]["action"] == "BUY":
            final_p_slip = final_p * (1 - (slippage_pct / 100))
            slip_diff = final_p - final_p_slip
        else:
            final_p_slip = final_p * (1 + (slippage_pct / 100))
            slip_diff = final_p_slip - final_p
            
        qty = leg_details[i]["qty"]
        exit_slippage_cost += (slip_diff * qty)
        
        leg_details[i]["exit_price"] = round(final_p_slip, 2)
        leg_details[i]["exit_time"] = merged_df.iloc[exit_idx]['start_Time'].strftime("%Y-%m-%d %H:%M")
        
        if leg_details[i]["action"] == "BUY":
            leg_details[i]["pnl"] = round((leg_details[i]["exit_price"] - leg_details[i]["entry_price"]) * qty, 2)
        else:
            leg_details[i]["pnl"] = round((leg_details[i]["entry_price"] - leg_details[i]["exit_price"]) * qty, 2)
        
    final_pnl -= exit_slippage_cost
    equity_curve[-1]["return"] = round(final_pnl, 2)
    current_capital = capital + final_pnl

    return {
        "legs": leg_details,
        "entry_time": merged_df.iloc[0]['start_Time'].strftime("%Y-%m-%d %H:%M"),
        "exit_time": merged_df.iloc[exit_idx]['start_Time'].strftime("%Y-%m-%d %H:%M"),
        "total_pnl": round(final_pnl, 2),
        "equity_curve": equity_curve,
        "metrics": {
            "initial_capital": capital,
            "final_capital": round(current_capital, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "total_trades": 1
        }
    }


def run_hedging_backtest_from_csv(df, strategy_name, slippage_pct, capital=100000, qty_multiplier=1, sl_pct=0, tp_pct=0):
    """
    Backtests a multi-leg strategy using an uploaded CSV file.
    The CSV must contain a 'datetime' (or 'start_Time'/'Date') column,
    and columns named 'leg1', 'leg2', 'leg3', 'leg4' corresponding to the strategy legs.
    Optionally reads 'spot', 'iv_1', etc. for Greeks if available (but typically local CSVs won't have it).
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    legs = STRATEGIES[strategy_name]
    num_legs = len(legs)

    # Standardize datetime column
    dt_col = None
    for col in ['start_Time', 'datetime', 'Date', 'date', 'time', 'Timestamp', 'timestamp']:
        if col in df.columns:
            dt_col = col
            break
            
    if not dt_col:
        raise ValueError("CSV must contain a datetime column (e.g., 'start_Time' or 'datetime').")

    df[dt_col] = pd.to_datetime(df[dt_col])
    df = df.sort_values(dt_col).reset_index(drop=True)

    # Verify required leg columns exist
    for i in range(num_legs):
        leg_col = f'leg{i+1}'
        if leg_col not in df.columns:
            raise ValueError(f"CSV is missing column '{leg_col}' required for strategy {strategy_name} (needs {num_legs} legs).")

    leg_details = []
    for i, (opt_type, offset, action, qty) in enumerate(legs):
        leg_details.append({
            "type": opt_type, 
            "action": action, 
            "qty": qty * qty_multiplier, 
            "strike_str": f"Uploaded Leg {i+1}",
            "strike_val": 0 # Unknown in generic CSV
        })

    equity_curve = []
    
    # Entry prices at the first timestamp
    entry_prices = {}
    for i in range(num_legs):
        p = df.iloc[0][f'leg{i+1}']
        if leg_details[i]["action"] == "BUY":
            p = p * (1 + (slippage_pct / 100))
        else:
            p = p * (1 - (slippage_pct / 100))
        entry_prices[i] = p
        leg_details[i]["entry_price"] = round(p, 2)
        leg_details[i]["entry_time"] = df.iloc[0][dt_col].strftime("%Y-%m-%d %H:%M")
        leg_details[i]["capital_used"] = round(p * leg_details[i]["qty"], 2)
        
        try:
            S = float(df.iloc[0][f'spot_{i}'])
            K = float(df.iloc[0][f'strike_{i}'])
            iv = float(df.iloc[0][f'iv_{i}'])
            leg_details[i]["spot_entry"] = S
            leg_details[i]["strike_val"] = K
            leg_details[i]["iv"] = round(iv, 2)
        except (ValueError, KeyError, TypeError):
            leg_details[i]["spot_entry"] = 0 
            leg_details[i]["strike_val"] = 0
            leg_details[i]["iv"] = 0

    peak_capital = capital
    max_drawdown = 0
    current_capital = capital
    
    exit_idx = len(df) - 1
    
    # Calculate PNL at each timestamp
    for idx, row in df.iterrows():
        net_pnl = 0
        for i in range(num_legs):
            current_p = row[f'leg{i+1}']
            entry_p = entry_prices[i]
            qty = leg_details[i]["qty"]
            
            if leg_details[i]["action"] == "BUY":
                pnl = (current_p - entry_p) * qty
            else:
                pnl = (entry_p - current_p) * qty
                
            net_pnl += pnl
            
        current_capital = capital + net_pnl
        if current_capital > peak_capital:
            peak_capital = current_capital
            
        dd = (peak_capital - current_capital) / peak_capital * 100 if peak_capital > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd
            
        equity_curve.append({
            "step": row[dt_col].strftime("%Y-%m-%d %H:%M"),
            "return": round(net_pnl, 2)
        })
        
        # Check SL/TP
        if sl_pct > 0 and net_pnl <= - (capital * (sl_pct / 100)):
            exit_idx = idx
            break
        if tp_pct > 0 and net_pnl >= (capital * (tp_pct / 100)):
            exit_idx = idx
            break

    # Final trade log summary
    final_pnl = equity_curve[-1]["return"]
    
    # Apply exit slippage to final PNL
    exit_slippage_cost = 0
    for i in range(num_legs):
        final_p = df.iloc[exit_idx][f'leg{i+1}']
        if leg_details[i]["action"] == "BUY":
            # Selling to exit
            final_p_slip = final_p * (1 - (slippage_pct / 100))
            slip_diff = final_p - final_p_slip
        else:
            # Buying to exit
            final_p_slip = final_p * (1 + (slippage_pct / 100))
            slip_diff = final_p_slip - final_p
            
        qty = leg_details[i]["qty"]
        exit_slippage_cost += (slip_diff * qty)
        
        leg_details[i]["exit_price"] = round(final_p_slip, 2)
        leg_details[i]["exit_time"] = df.iloc[exit_idx][dt_col].strftime("%Y-%m-%d %H:%M")
        
        if leg_details[i]["action"] == "BUY":
            leg_details[i]["pnl"] = round((leg_details[i]["exit_price"] - leg_details[i]["entry_price"]) * qty, 2)
        else:
            leg_details[i]["pnl"] = round((leg_details[i]["entry_price"] - leg_details[i]["exit_price"]) * qty, 2)
        
    final_pnl -= exit_slippage_cost
    equity_curve[-1]["return"] = round(final_pnl, 2)
    current_capital = capital + final_pnl

    return {
        "legs": leg_details,
        "entry_time": df.iloc[0][dt_col].strftime("%Y-%m-%d %H:%M"),
        "exit_time": df.iloc[exit_idx][dt_col].strftime("%Y-%m-%d %H:%M"),
        "total_pnl": round(final_pnl, 2),
        "equity_curve": equity_curve,
        "metrics": {
            "initial_capital": capital,
            "final_capital": round(current_capital, 2),
            "max_drawdown_pct": round(max_drawdown, 2),
            "total_trades": 1
        }
    }
