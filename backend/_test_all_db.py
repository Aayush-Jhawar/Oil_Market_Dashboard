import sqlite3
import pandas as pd
import numpy as np

conn = sqlite3.connect(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\DB\bars_15min_latest.db')

# WTI contracts
cl_m1 = pd.read_sql("SELECT timestamp, close FROM CL_N26", conn, parse_dates=['timestamp']).set_index('timestamp')
cl_m2 = pd.read_sql("SELECT timestamp, close FROM CL_Q26", conn, parse_dates=['timestamp']).set_index('timestamp')
cl_m3 = pd.read_sql("SELECT timestamp, close FROM CL_U26", conn, parse_dates=['timestamp']).set_index('timestamp')
cl_m4 = pd.read_sql("SELECT timestamp, close FROM CL_V26", conn, parse_dates=['timestamp']).set_index('timestamp')

# Brent contracts
co_m1 = pd.read_sql("SELECT timestamp, close FROM CO_Q26", conn, parse_dates=['timestamp']).set_index('timestamp')
co_m2 = pd.read_sql("SELECT timestamp, close FROM CO_U26", conn, parse_dates=['timestamp']).set_index('timestamp')
co_m3 = pd.read_sql("SELECT timestamp, close FROM CO_V26", conn, parse_dates=['timestamp']).set_index('timestamp')
co_m4 = pd.read_sql("SELECT timestamp, close FROM CO_X26", conn, parse_dates=['timestamp']).set_index('timestamp')

conn.close()

dfs = {
    "WTI Spread M1-M2": cl_m1['close'] - cl_m2['close'],
    "WTI Fly M1-M2-M3": cl_m1['close'] - 2*cl_m2['close'] + cl_m3['close'],
    "WTI DFly M1-M2-M3-M4": cl_m1['close'] - 3*cl_m2['close'] + 3*cl_m3['close'] - cl_m4['close'],
    
    "Brent Spread M1-M2": co_m1['close'] - co_m2['close'],
    "Brent Fly M1-M2-M3": co_m1['close'] - 2*co_m2['close'] + co_m3['close'],
    "Brent DFly M1-M2-M3-M4": co_m1['close'] - 3*co_m2['close'] + 3*co_m3['close'] - co_m4['close']
}

weights = {
    "WTI Spread M1-M2": {"BB": 0.3525, "Z": 0.3525, "EMA": 0.2951},
    "WTI Fly M1-M2-M3": {"BB": 0.3525, "Z": 0.3525, "EMA": 0.2951},
    "WTI DFly M1-M2-M3-M4": {"BB": 0.3525, "Z": 0.3525, "EMA": 0.2951},
    
    "Brent Spread M1-M2": {"BB": 0.3419, "Z": 0.3419, "EMA": 0.3162},
    "Brent Fly M1-M2-M3": {"BB": 0.3419, "Z": 0.3419, "EMA": 0.3162},
    "Brent DFly M1-M2-M3-M4": {"BB": 0.3419, "Z": 0.3419, "EMA": 0.3162}
}

print("="*80)
print(f"{'Structure':<30} | {'Strategy':<15} | {'Win Rate':<10} | {'PF':<6} | {'Trades':<6}")
print("="*80)

def compute_stats(pnl):
    t_starts = pnl.shift(1).fillna(0) != pnl
    t_ids = (pnl != 0).cumsum()  # Simplified trade extraction based on non-zero pnl
    # Actually, we need to track positions
    return 0

results = []

for name, s in dfs.items():
    s = s.dropna().to_frame("close")
    
    # BB
    ma = s["close"].rolling(20).mean()
    std = s["close"].rolling(20).std()
    sig_bb = pd.Series(0, index=s.index)
    sig_bb[s["close"] < (ma - 2*std)] = 1
    sig_bb[s["close"] > (ma + 2*std)] = -1
    sig_bb = sig_bb.replace(0, np.nan).ffill().fillna(0)
    
    # Z-Score
    z = (s["close"] - ma) / std
    sig_z = pd.Series(0, index=s.index)
    sig_z[z < -2] = 1
    sig_z[z > 2] = -1
    sig_z = sig_z.replace(0, np.nan).ffill().fillna(0)
    
    # EMA Cross
    ema_fast = s["close"].ewm(span=9).mean()
    ema_slow = s["close"].ewm(span=21).mean()
    sig_ema = pd.Series(0, index=s.index)
    sig_ema[ema_fast > ema_slow] = 1
    sig_ema[ema_fast < ema_slow] = -1
    
    w = weights[name]
    sig_combined = (sig_bb * w["BB"]) + (sig_z * w["Z"]) + (sig_ema * w["EMA"])
    
    signals = {
        "BB Only": sig_bb,
        "Z-Score Only": sig_z,
        "EMA Only": sig_ema,
        "ML Combined": sig_combined
    }
    
    for strat_name, sig in signals.items():
        pos = sig.shift(1).fillna(0)
        ret = s["close"].diff()
        pnl = pos * ret
        
        t_starts = pos.diff().fillna(0) != 0
        t_ids = t_starts.cumsum()
        trades = pnl.groupby(t_ids).sum()
        trades = trades[trades != 0]
        
        if len(trades) > 0:
            wins = trades[trades > 0]
            losses = trades[trades < 0]
            acc = len(wins) / len(trades) * 100
            pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
        else:
            acc = 0
            pf = 0
            
        print(f"{name:<30} | {strat_name:<15} | {acc:>8.2f}% | {pf:>6.2f} | {len(trades):>6}")

print("="*80)
