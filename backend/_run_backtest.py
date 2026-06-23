"""
Comprehensive Strategy Evaluation Script
=========================================
Runs all 7 strategies across WTI, Brent, HO, GO term structures.
Splits data into:
  - Historical: 2021-01-04 to 2026-03-22 (excluding last 2 months)
  - COVID Stress: 2020 proxy - use 2022 H1 (Russia-Ukraine oil shock) as a black swan analog
  - Forward Test: 2026-03-22 to 2026-05-22 (last 2 months)
Constructs spreads, flies, and dflies from term structure M1-M12.
"""
import sqlite3
import json
import math
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime

# ----- Load Term Structure Data -----
conn = sqlite3.connect('energy.db')

SYMBOLS = ["WTI", "Brent", "HO", "GO"]
CUTOFF_DATE = "2026-03-22"
STRESS_START = "2022-02-01"
STRESS_END = "2022-06-30"

all_results = {}

for symbol in SYMBOLS:
    print(f"\n{'='*60}")
    print(f"Processing {symbol}...")
    
    # Load all term structure data
    df = pd.read_sql(
        f"""SELECT timestamp, m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12 
            FROM historical_term_structure 
            WHERE symbol='{symbol}' 
            ORDER BY timestamp""",
        conn, parse_dates=["timestamp"]
    )
    
    if df.empty:
        print(f"  No data for {symbol}")
        continue
    
    df = df.set_index("timestamp")
    # Resample to 15-min bars to normalize timestamps  
    df = df.resample("15min").last().dropna(subset=["m1"])
    
    print(f"  Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    # ----- Construct Instruments from Term Structure -----
    instruments = {}
    
    # Spreads: M1-M2, M1-M3, M1-M6, M1-M12
    spread_specs = [(1,2), (1,3), (1,6), (1,12), (2,3), (3,4)]
    for m_front, m_back in spread_specs:
        col_f = f"m{m_front}"
        col_b = f"m{m_back}"
        if col_f in df.columns and col_b in df.columns:
            spread = df[[col_f, col_b]].dropna()
            if not spread.empty:
                sdf = pd.DataFrame(index=spread.index)
                sdf["close"] = spread[col_f] - spread[col_b]
                sdf["open"] = sdf["close"].shift(1).fillna(sdf["close"])
                sdf["high"] = sdf[["open", "close"]].max(axis=1)
                sdf["low"] = sdf[["open", "close"]].min(axis=1)
                sdf["volume"] = 1000
                key = f"{symbol}_M{m_front}M{m_back}"
                sdf.attrs["structure_type"] = "SPREAD"
                instruments[key] = sdf
    
    # Flies: equidistant M_x - 2*M_y + M_z
    for dist in range(1, 6):
        for m1 in range(1, 13):
            m2 = m1 + dist
            m3 = m1 + 2 * dist
            if m3 <= 12:
                c1, c2, c3 = f"m{m1}", f"m{m2}", f"m{m3}"
                if c1 in df.columns and c2 in df.columns and c3 in df.columns:
                    sub = df[[c1, c2, c3]].dropna()
                    if len(sub) > 100:
                        fdf = pd.DataFrame(index=sub.index)
                        fdf["close"] = sub[c1] - 2 * sub[c2] + sub[c3]
                        fdf["open"] = fdf["close"].shift(1).fillna(fdf["close"])
                        fdf["high"] = fdf[["open", "close"]].max(axis=1)
                        fdf["low"] = fdf[["open", "close"]].min(axis=1)
                        fdf["volume"] = 500
                        key = f"{symbol}_FLY_M{m1}M{m2}M{m3}"
                        fdf.attrs["structure_type"] = "FLY"
                        instruments[key] = fdf
    
    # DFlies: M1 - 3*M2 + 3*M3 - M4 (equidistant)
    for dist in range(1, 4):
        for m1 in range(1, 13):
            m2 = m1 + dist
            m3 = m1 + 2 * dist
            m4 = m1 + 3 * dist
            if m4 <= 12:
                c1, c2, c3, c4 = f"m{m1}", f"m{m2}", f"m{m3}", f"m{m4}"
                if all(c in df.columns for c in [c1, c2, c3, c4]):
                    sub = df[[c1, c2, c3, c4]].dropna()
                    if len(sub) > 100:
                        ddf = pd.DataFrame(index=sub.index)
                        ddf["close"] = sub[c1] - 3 * sub[c2] + 3 * sub[c3] - sub[c4]
                        ddf["open"] = ddf["close"].shift(1).fillna(ddf["close"])
                        ddf["high"] = ddf[["open", "close"]].max(axis=1)
                        ddf["low"] = ddf[["open", "close"]].min(axis=1)
                        ddf["volume"] = 250
                        key = f"{symbol}_DFLY_M{m1}M{m2}M{m3}M{m4}"
                        ddf.attrs["structure_type"] = "DFLY"
                        instruments[key] = ddf
    
    print(f"  Built {len(instruments)} instruments")
    
    # ----- Run Strategies -----
    # Import strategy components
    import sys
    sys.path.insert(0, ".")
    from backtesting.indicators import (
        bollinger_bands, bb_signal,
        ema, ema_crossover_signal,
        rsi, rsi_signal,
        macd, macd_signal,
        rolling_zscore, zscore_signal,
        atr as compute_atr,
        KalmanSpreadFilter,
        Signal
    )
    
    STRATEGIES = {
        "BB Mean Reversion": {"type": "bb", "params": {"period": 20, "num_std": 2.0}},
        "EMA Cross (9/21)": {"type": "ema", "params": {"fast": 9, "slow": 21}},
        "EMA Cross (5/13)": {"type": "ema", "params": {"fast": 5, "slow": 13}},
        "RSI Extreme": {"type": "rsi", "params": {"period": 14, "ob": 70, "os": 30}},
        "MACD Momentum": {"type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
        "Z-Score MR": {"type": "zscore", "params": {"window": 20, "entry_z": 2.0, "exit_z": 0.5}},
        "Kalman Spread": {"type": "kalman", "params": {"q": 1e-5, "r": 1e-2, "entry_z": 2.0, "exit_z": 0.5}},
    }
    
    for strat_name, strat_cfg in STRATEGIES.items():
        hist_trades = []
        fwd_trades = []
        stress_trades = []
        
        for inst_key, inst_df in instruments.items():
            if len(inst_df) < 50:
                continue
                
            series = inst_df["close"].astype(float)
            struct_type = inst_df.attrs.get("structure_type", "OUTRIGHT")
            
            # Precompute indicators
            precomp = {}
            stype = strat_cfg["type"]
            p = strat_cfg["params"]
            
            try:
                if stype == "bb":
                    precomp["bb"] = bollinger_bands(series, p["period"], p["num_std"])
                elif stype == "ema":
                    precomp["fast_ema"] = ema(series, p["fast"])
                    precomp["slow_ema"] = ema(series, p["slow"])
                elif stype == "rsi":
                    precomp["rsi"] = rsi(series, p["period"])
                elif stype == "macd":
                    precomp["macd"] = macd(series, p["fast"], p["slow"], p["signal"])
                elif stype == "zscore":
                    precomp["zscore"] = rolling_zscore(series, p["window"])
                elif stype == "kalman":
                    kf = KalmanSpreadFilter(q=p["q"], r=p["r"])
                    precomp["kalman_z"] = kf.fit_series(series)
            except Exception as e:
                continue
            
            # Compute ATR
            if "high" in inst_df.columns and "low" in inst_df.columns:
                atr_series = compute_atr(
                    inst_df["high"].astype(float), inst_df["low"].astype(float),
                    series, period=14
                )
            else:
                atr_series = None
            
            # Bar-by-bar simulation
            position = "FLAT"
            entry_price = 0.0
            entry_idx = 0
            entry_ts = ""
            direction = ""
            sl_price = 0.0
            tp_price = 0.0
            
            SL_ATR_MULT = 2.0
            TP_ATR_MULT = 3.0
            MAX_BARS = 50
            
            for i in range(1, len(inst_df)):
                prev_close = float(series.iloc[i-1])
                curr_open = float(inst_df["open"].iloc[i])
                curr_high = float(inst_df["high"].iloc[i])
                curr_low = float(inst_df["low"].iloc[i])
                curr_close = float(series.iloc[i])
                ts = str(inst_df.index[i])
                
                current_atr = float(atr_series.iloc[i-1]) if atr_series is not None and not pd.isna(atr_series.iloc[i-1]) else abs(curr_open) * 0.02
                if current_atr <= 0:
                    current_atr = abs(curr_open) * 0.02
                
                # Evaluate signal
                try:
                    if stype == "bb":
                        result = bb_signal(prev_close, precomp["bb"], i-1, position)
                    elif stype == "ema":
                        result = ema_crossover_signal(precomp["fast_ema"], precomp["slow_ema"], i-1, position)
                    elif stype == "rsi":
                        result = rsi_signal(precomp["rsi"], i-1, p["ob"], p["os"], position)
                    elif stype == "macd":
                        result = macd_signal(precomp["macd"], i-1, position)
                    elif stype == "zscore":
                        result = zscore_signal(precomp["zscore"], i-1, p["entry_z"], p["exit_z"], position)
                    elif stype == "kalman":
                        result = zscore_signal(precomp["kalman_z"], i-1, p["entry_z"], p["exit_z"], position)
                except:
                    continue
                
                # Manage active trade
                if position != "FLAT":
                    bars_held = i - entry_idx
                    
                    # Check SL
                    sl_hit = False
                    tp_hit = False
                    if direction == "LONG":
                        if curr_low <= sl_price: sl_hit = True
                        if curr_high >= tp_price: tp_hit = True
                    else:
                        if curr_high >= sl_price: sl_hit = True
                        if curr_low <= tp_price: tp_hit = True
                    
                    exit_price = None
                    exit_reason = None
                    
                    if sl_hit:
                        exit_price = sl_price
                        exit_reason = "STOP_LOSS"
                    elif tp_hit:
                        exit_price = tp_price
                        exit_reason = "TARGET"
                    elif bars_held >= MAX_BARS:
                        exit_price = curr_open
                        exit_reason = "TIME_EXIT"
                    elif result.signal in (Signal.EXIT_LONG, Signal.EXIT_SHORT):
                        exit_price = curr_open
                        exit_reason = "SIGNAL"
                    
                    if exit_price is not None:
                        if direction == "LONG":
                            pnl = exit_price - entry_price
                        else:
                            pnl = entry_price - exit_price
                        
                        trade = {
                            "instrument": inst_key,
                            "structure_type": struct_type,
                            "direction": direction,
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "pnl_points": pnl,
                            "exit_reason": exit_reason,
                            "entry_ts": entry_ts,
                            "exit_ts": ts,
                            "bars_held": bars_held,
                        }
                        
                        # Categorize by period
                        entry_date = entry_ts[:10]
                        if STRESS_START <= entry_date <= STRESS_END:
                            stress_trades.append(trade)
                        
                        if entry_date < CUTOFF_DATE:
                            hist_trades.append(trade)
                        else:
                            fwd_trades.append(trade)
                        
                        position = "FLAT"
                        continue
                
                # Open new trade
                if position == "FLAT" and result.signal in (Signal.LONG, Signal.SHORT):
                    direction = "LONG" if result.signal == Signal.LONG else "SHORT"
                    entry_price = curr_open
                    entry_idx = i
                    entry_ts = ts
                    
                    if direction == "LONG":
                        sl_price = entry_price - current_atr * SL_ATR_MULT
                        tp_price = entry_price + current_atr * TP_ATR_MULT
                        position = "LONG"
                    else:
                        sl_price = entry_price + current_atr * SL_ATR_MULT
                        tp_price = entry_price - current_atr * TP_ATR_MULT
                        position = "SHORT"
        
        # ----- Compute Metrics -----
        def compute_metrics(trades):
            if not trades:
                return {"trades": 0, "win_rate": 0, "pf": 0, "max_dd_pct": 0, "avg_rr": 0, "total_pnl": 0}
            
            pnls = [t["pnl_points"] for t in trades]
            winners = [p for p in pnls if p > 0]
            losers = [p for p in pnls if p < 0]
            
            total_pnl = sum(pnls)
            win_rate = len(winners) / len(pnls) * 100 if pnls else 0
            pf = abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0 else float('inf')
            
            # Max drawdown
            equity = 0
            peak = 0
            max_dd = 0
            for p in pnls:
                equity += p
                if equity > peak:
                    peak = equity
                dd = peak - equity
                if dd > max_dd:
                    max_dd = dd
            max_dd_pct = (max_dd / abs(peak)) * 100 if peak != 0 else 0
            
            avg_win = np.mean(winners) if winners else 0
            avg_loss = abs(np.mean(losers)) if losers else 0
            avg_rr = avg_win / avg_loss if avg_loss > 0 else float('inf')
            
            # Exit reason breakdown
            reasons = defaultdict(int)
            for t in trades:
                reasons[t["exit_reason"]] += 1
            
            return {
                "trades": len(pnls),
                "win_rate": round(win_rate, 1),
                "pf": round(pf, 2) if pf != float('inf') else "INF",
                "max_dd_pct": round(max_dd_pct, 1),
                "avg_rr": round(avg_rr, 2) if avg_rr != float('inf') else "INF",
                "total_pnl": round(total_pnl, 4),
                "exit_reasons": dict(reasons),
            }
        
        hist_m = compute_metrics(hist_trades)
        fwd_m = compute_metrics(fwd_trades)
        stress_m = compute_metrics(stress_trades)
        
        key = f"{symbol}|{strat_name}"
        all_results[key] = {
            "symbol": symbol,
            "strategy": strat_name,
            "historical": hist_m,
            "forward": fwd_m,
            "stress": stress_m,
        }
        
        if hist_m["trades"] > 0 or fwd_m["trades"] > 0:
            print(f"  {strat_name}: Hist={hist_m['trades']}t/{hist_m['win_rate']}%wr | Fwd={fwd_m['trades']}t/{fwd_m['win_rate']}%wr | Stress={stress_m['trades']}t/{stress_m['win_rate']}%wr")

conn.close()

# ----- Output JSON -----
with open("_backtest_results.json", "w") as f:
    json.dump(all_results, f, indent=2, default=str)

print(f"\n\n{'='*60}")
print(f"TOTAL STRATEGY-SYMBOL COMBINATIONS: {len(all_results)}")
print(f"Results saved to _backtest_results.json")
