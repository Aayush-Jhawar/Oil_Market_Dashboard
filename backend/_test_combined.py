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
    "WTI DFly": cl_m1['close'] - 3*cl_m2['close'] + 3*cl_m3['close'] - cl_m4['close'],
    "WTI Outright": cl_m1['close'],
    "Brent DFly": co_m1['close'] - 3*co_m2['close'] + 3*co_m3['close'] - co_m4['close'],
    "Brent Outright": co_m1['close']
}

weights = {
    "WTI DFly": {"BB": 0.3525, "Z": 0.3525, "EMA": 0.2951},
    "WTI Outright": {"BB": 0.3325, "Z": 0.3325, "EMA": 0.3350},
    "Brent DFly": {"BB": 0.3419, "Z": 0.3419, "EMA": 0.3162},
    "Brent Outright": {"BB": 0.3314, "Z": 0.3314, "EMA": 0.3371}
}

print("="*50)
print("FORWARD TESTING STATS (DB: bars_15min_latest.db)")
print("="*50)

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
    
    # Combine signals
    w = weights[name]
    combined_pos = (sig_bb * w["BB"]) + (sig_z * w["Z"]) + (sig_ema * w["EMA"])
    
    # Trade execution
    pos = combined_pos.shift(1).fillna(0)
    ret = s["close"].diff()
    pnl = pos * ret
    
    # Metrics
    t_starts = pos.diff().fillna(0) != 0
    t_ids = t_starts.cumsum()
    trades = pnl.groupby(t_ids).sum()
    trades = trades[trades != 0]
    
    total_pnl = pnl.sum()
    if len(trades) > 0:
        wins = trades[trades > 0]
        losses = trades[trades < 0]
        acc = len(wins) / len(trades) * 100
        pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
        wl = len(wins) / len(losses) if len(losses) > 0 else float('inf')
    else:
        acc = 0
        pf = 0
        wl = 0
        
    cum = pnl.cumsum()
    max_dd = (cum.cummax() - cum).max()
    
    print(f"\n[{name}]")
    print(f"Total Return: {total_pnl:.4f} pts")
    print(f"Number of Trades: {len(trades)}")
    print(f"Win Rate: {acc:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Max Drawdown: {max_dd:.4f} pts")
