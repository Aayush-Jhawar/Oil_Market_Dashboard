import sqlite3
import pandas as pd
import numpy as np
import json

def get_data():
    conn = sqlite3.connect('energy.db')
    df = pd.read_sql(
        "SELECT timestamp, m1, m2, m3, m4 FROM historical_term_structure WHERE symbol='WTI' ORDER BY timestamp",
        conn, parse_dates=["timestamp"]
    ).set_index("timestamp").resample("1h").last().dropna()
    conn.close()
    return df

df = get_data()

# Define instruments
instruments = {
    "Spread M1-M2": df["m1"] - df["m2"],
    "Fly M1-M2-M3": df["m1"] - 2*df["m2"] + df["m3"],
    "DFly M1-M2-M3-M4": df["m1"] - 3*df["m2"] + 3*df["m3"] - df["m4"],
    "Outright M1": df["m1"]
}

results = []

for name, series in instruments.items():
    s = series.to_frame("close")
    s["open"] = s["close"].shift(1).fillna(s["close"])
    s["high"] = s[["open", "close"]].max(axis=1)
    s["low"] = s[["open", "close"]].min(axis=1)
    
    # 1. Bollinger Band Mean Reversion
    ma = s["close"].rolling(20).mean()
    std = s["close"].rolling(20).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    
    sig_bb = pd.Series(0, index=s.index)
    sig_bb[s["close"] < lower] = 1
    sig_bb[s["close"] > upper] = -1
    sig_bb[((s["close"] >= ma) & (s["close"].shift(1) < ma)) | ((s["close"] <= ma) & (s["close"].shift(1) > ma))] = 0
    sig_bb = sig_bb.replace(0, np.nan).ffill().fillna(0)
    
    # 2. EMA Crossover (9/21)
    ema9 = s["close"].ewm(span=9).mean()
    ema21 = s["close"].ewm(span=21).mean()
    sig_ema = pd.Series(0, index=s.index)
    sig_ema[ema9 > ema21] = 1
    sig_ema[ema9 < ema21] = -1
    
    # 3. Z-Score Mean Reversion
    z = (s["close"] - ma) / std
    sig_z = pd.Series(0, index=s.index)
    sig_z[z < -2] = 1
    sig_z[z > 2] = -1
    sig_z[z.abs() < 0.5] = 0
    sig_z = sig_z.replace(0, np.nan).ffill().fillna(0)
    
    strategies = {
        "BB Mean Reversion": sig_bb,
        "EMA Crossover": sig_ema,
        "Z-Score MR": sig_z
    }
    
    for strat_name, sig in strategies.items():
        # Shift signal by 1 so we trade on next open
        pos = sig.shift(1).fillna(0)
        
        # Calculate bar returns (open to next open for simplicity, or just close to close)
        ret = s["close"].diff()
        
        # Trade PnL
        pnl = pos * ret
        
        # Find individual trades to compute win rate
        trade_starts = pos.diff().fillna(0) != 0
        trade_ids = trade_starts.cumsum()
        
        trades = pnl.groupby(trade_ids).sum()
        trades = trades[trades != 0]  # Filter out flat periods
        
        # Split into periods
        # Historical: 2021-01-04 to 2026-03-22
        # Stress: 2022-02-01 to 2022-06-30
        # Forward: 2026-03-22 onwards
        
        def calc_metrics(period_pnl, period_trades):
            if len(period_trades) == 0:
                return {"accuracy": 0.0, "pf": 0.0, "max_dd": 0.0, "wl": 0.0}
            
            wins = period_trades[period_trades > 0]
            losses = period_trades[period_trades < 0]
            acc = len(wins) / len(period_trades) * 100
            pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
            wl = (len(wins) / len(losses)) if len(losses) > 0 else float('inf')
            
            # Max DD
            cum = period_pnl.cumsum()
            peak = cum.cummax()
            dd = peak - cum
            max_dd = dd.max()
            
            return {"accuracy": acc, "pf": pf, "max_dd": max_dd, "wl": wl}
        
        # Pnl series
        pnl_hist = pnl.loc["2021-01-04":"2026-03-21"]
        pnl_stress = pnl.loc["2022-02-01":"2022-06-30"]
        pnl_fwd = pnl.loc["2026-03-22":]
        
        # Trades
        # Recompute trades per period to be accurate
        def extract_trades(pos_series, ret_series):
            t_starts = pos_series.diff().fillna(0) != 0
            t_ids = t_starts.cumsum()
            trds = (pos_series * ret_series).groupby(t_ids).sum()
            return trds[trds != 0]
            
        tr_hist = extract_trades(pos.loc["2021-01-04":"2026-03-21"], ret.loc["2021-01-04":"2026-03-21"])
        tr_stress = extract_trades(pos.loc["2022-02-01":"2022-06-30"], ret.loc["2022-02-01":"2022-06-30"])
        tr_fwd = extract_trades(pos.loc["2026-03-22":], ret.loc["2026-03-22":])
        
        mh = calc_metrics(pnl_hist, tr_hist)
        ms = calc_metrics(pnl_stress, tr_stress)
        mf = calc_metrics(pnl_fwd, tr_fwd)
        
        results.append({
            "Strategy": strat_name,
            "Market Structure": name,
            "Hist_Acc": mh["accuracy"],
            "Fwd_Acc": mf["accuracy"],
            "PF": mh["pf"],
            "Max_DD_Hist": mh["max_dd"],
            "Max_DD_COVID": ms["max_dd"],
            "WL": mh["wl"]
        })

print(json.dumps(results, indent=2))
