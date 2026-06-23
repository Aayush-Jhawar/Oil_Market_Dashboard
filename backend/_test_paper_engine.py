import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import time
import unittest.mock as mock

# Reset state
import os
if os.path.exists("paper_state.json"): os.remove("paper_state.json")
if os.path.exists("regime_state.json"): os.remove("regime_state.json")

import paper
from services.regime_classifier import regime_classifier
from services.zscore_strategy import zscore_strategy
from paper import paper_book

print("="*80)
print("Running Paper Engine Regression Test (Live DB Data)")
print("="*80)

db_path = r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\DB\bars_15min_latest.db'
conn = sqlite3.connect(db_path)

# Load WTI outrights
wti_dfs = {}
for m in range(1, 13):
    table = f"CL_M{m}" # Fake table name, we need to find actual tables
    pass

# Wait, we know from previous scripts that the tables are CL_N26, CL_Q26 etc.
# We can use the logic from _forward_test_db_zscore.py
cl_tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'CL_%'", conn)['name'].tolist()
lco_tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'LCO_%'", conn)['name'].tolist()

def parse_contract(t):
    parts = t.split('_')
    month_code = parts[1][0]
    year_str = parts[1][1:]
    year = int(year_str) if year_str.isdigit() else 99
    
    month_map = {'F':1,'G':2,'H':3,'J':4,'K':5,'M':6,'N':7,'Q':8,'U':9,'V':10,'X':11,'Z':12}
    month = month_map.get(month_code.upper(), 99)
    return (parts[0], year, month, t)

cl_tables = sorted([parse_contract(t) for t in cl_tables], key=lambda x: (x[1], x[2]))
lco_tables = sorted([parse_contract(t) for t in lco_tables], key=lambda x: (x[1], x[2]))

wti_m = {}
for i, t_info in enumerate(cl_tables[:12]):
    df = pd.read_sql(f"SELECT timestamp, close FROM {t_info[3]}", conn, parse_dates=['timestamp']).set_index('timestamp')
    wti_m[i+1] = df

brent_m = {}
for i, t_info in enumerate(lco_tables[:12]):
    df = pd.read_sql(f"SELECT timestamp, close FROM {t_info[3]}", conn, parse_dates=['timestamp']).set_index('timestamp')
    brent_m[i+1] = df

wti_idx = None
for i in range(1, 13):
    if i in wti_m:
        if wti_idx is None: wti_idx = wti_m[i].index
        else: wti_idx = wti_idx.intersection(wti_m[i].index)

for i in range(1, 13):
    if i in brent_m:
        wti_idx = wti_idx.intersection(brent_m[i].index)

print(f"Total synchronized 15-min bars: {len(wti_idx)}")

wti_aligned = {m: df.loc[wti_idx]['close'] for m, df in wti_m.items()}
brent_aligned = {m: df.loc[wti_idx]['close'] for m, df in brent_m.items()}

# Mock forward curve
def mock_get_curve(base):
    res = {}
    if base == "WTI":
        for m in range(1, 13):
            if m in wti_aligned: res[f"M{m}"] = wti_aligned[m].iloc[mock_idx]
    elif base == "Brent":
        for m in range(1, 13):
            if m in brent_aligned: res[f"M{m}"] = brent_aligned[m].iloc[mock_idx]
    return res

paper.get_curve_as_dict = mock_get_curve

# Run simulation
for mock_idx in range(len(wti_idx)):
    ts = wti_idx[mock_idx]
    ts_float = ts.timestamp()
    
    current_prices = {}
    
    # Base outrights
    if 1 in wti_aligned: current_prices["WTI"] = wti_aligned[1].iloc[mock_idx]
    if 1 in brent_aligned: current_prices["Brent"] = brent_aligned[1].iloc[mock_idx]
    
    # Construct validated instruments dynamically
    for base, data in [("WTI", wti_aligned), ("BRENT", brent_aligned)]:
        for m1 in range(1, 13):
            for d in range(1, 4):
                m2 = m1 + d
                m3 = m1 + 2*d
                m4 = m1 + 3*d
                if m4 <= 12 and m1 in data and m2 in data and m3 in data and m4 in data:
                    sym = f"{base}_DFLY_{m1}_{m2}_{m3}_{m4}"
                    val = data[m1].iloc[mock_idx] - 3*data[m2].iloc[mock_idx] + 3*data[m3].iloc[mock_idx] - data[m4].iloc[mock_idx]
                    current_prices[sym] = val
    
    # Process tick
    paper_book.process_tick(current_prices, signals={}, current_time=ts_float)

state = paper_book.get_state()
print(f"Final Equity: ${state['equity']:.2f}")
print(f"Total Trades: {len(state['closed_trades'])}")
print(f"Win Rate: {state['win_rate']:.2f}%")

if len(state['closed_trades']) > 0:
    wins = sum(1 for t in state['closed_trades'] if t['P&L'] > 0)
    print(f"Win Rate directly calculated: {wins/len(state['closed_trades'])*100:.2f}%")
    
print("\nFirst 5 trades:")
for t in state['closed_trades'][:5]:
    print(f"{t['Symbol']} | {t['Side']} | PnL: ${t['P&L']:.2f} | Slippage: ${t['Slippage']:.2f} | Regime: {t['Regime']}")
