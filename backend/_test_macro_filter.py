import sqlite3
import pandas as pd
import numpy as np
import warnings
import yfinance as yf

warnings.filterwarnings('ignore')

print("="*100)
print("Forward Testing High-Frequency Z-Score Strategy with Macro Filters")
print("(REAL DOLLARS: $1,000 Multiplier, $40 Slippage)")
print("="*100)

db_path = r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\DB\bars_15min_latest.db'
conn = sqlite3.connect(db_path)

# Download Macro
macro = yf.download(['DX-Y.NYB', '^VIX'], period='1mo', interval='15m')
if len(macro.columns.levels) > 1:
    dxy_close = macro['Close']['DX-Y.NYB']
    vix_close = macro['Close']['^VIX']
else:
    dxy_close = macro['Close'] # Just in case single ticker behavior

dxy_series = dxy_close.rename("DXY").tz_localize(None)
vix_series = vix_close.rename("VIX").tz_localize(None)

macro_df = pd.concat([dxy_series, vix_series], axis=1).ffill()
macro_df['DXY_1d_return'] = macro_df['DXY'].pct_change(periods=4*24) # approx 1 day of 15m bars
macro_df['VIX_1d_return'] = macro_df['VIX'].pct_change(periods=4*24)

# We will just test WTI front month (CL_N26 or CL_M26)
tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'CL_%'", conn)['name'].tolist()

def parse_contract(t):
    suffix = t.split('_')[1]
    months = {'F':1, 'G':2, 'H':3, 'J':4, 'K':5, 'M':6, 'N':7, 'Q':8, 'U':9, 'V':10, 'X':11, 'Z':12}
    try:
        return (int(suffix[1:]), months.get(suffix[0], 99))
    except:
        return (99, 99)
        
tables.sort(key=parse_contract)
front_month = tables[0]

print(f"Testing on {front_month}...")
df = pd.read_sql(f"SELECT timestamp, close FROM {front_month}", conn, parse_dates=['timestamp']).set_index('timestamp')
df = df[~df.index.duplicated(keep='first')]

# Join with macro
df = df.join(macro_df, how='left')
df['DXY_1d_return'] = df['DXY_1d_return'].ffill()
df['VIX_1d_return'] = df['VIX_1d_return'].ffill()

WINDOW = 20
SLIPPAGE_POINTS = 0.04
CONTRACT_MULTIPLIER = 1000

def run_strategy(df, apply_macro=False):
    d = df.copy().dropna(subset=['close'])
    d['ma'] = d['close'].rolling(WINDOW).mean()
    d['std'] = d['close'].rolling(WINDOW).std().replace(0, np.nan).ffill().fillna(0.001)
    d['z'] = (d['close'] - d['ma']) / d['std']
    
    thresh = 1.5
    pos = pd.Series(np.nan, index=d.index)
    
    # Baseline Z-Score (Mean Reversion)
    buy_sig = d['z'] < -thresh
    sell_sig = d['z'] > thresh
    
    if apply_macro:
        # If DXY is strong (up > 0%), don't buy Oil
        buy_sig = buy_sig & (d['DXY_1d_return'] <= 0)
        # If DXY is weak (down < 0%), don't short Oil
        sell_sig = sell_sig & (d['DXY_1d_return'] >= 0)
        
        # If VIX is spiking (up > 2%), don't buy Oil (risk off)
        buy_sig = buy_sig & (d['VIX_1d_return'] <= 0.02)
    
    pos[buy_sig] = 1
    pos[sell_sig] = -1
    
    crossed_up = (d['z'] > 0) & (d['z'].shift(1) < 0)
    crossed_down = (d['z'] < 0) & (d['z'].shift(1) > 0)
    pos[crossed_up | crossed_down] = 0
    pos[abs(d['z']) > 3.0] = 0
    
    pos = pos.ffill().fillna(0)
    d['pos'] = pos.shift(1).fillna(0)
    d['ret'] = d['close'].diff()
    d['pnl_raw'] = d['pos'] * d['ret']
    
    t_starts = d['pos'].diff().fillna(0) != 0
    t_ids = t_starts.cumsum()
    active_mask = d['pos'] != 0
    
    trade_pnls_raw = d.loc[active_mask, 'pnl_raw'].groupby(t_ids[active_mask]).sum()
    trade_pnls_raw = trade_pnls_raw[trade_pnls_raw != 0]
    trade_pnls_dollars = (trade_pnls_raw - SLIPPAGE_POINTS) * CONTRACT_MULTIPLIER
    
    if len(trade_pnls_dollars) > 0:
        wins = trade_pnls_dollars[trade_pnls_dollars > 0]
        losses = trade_pnls_dollars[trade_pnls_dollars < 0]
        win_rate = len(wins) / len(trade_pnls_dollars) * 100
        pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')
        total = trade_pnls_dollars.sum()
    else:
        win_rate = pf = total = 0
        
    return len(trade_pnls_dollars), win_rate, pf, total

# Test 1: Baseline
baseline_trades, baseline_wr, baseline_pf, baseline_pnl = run_strategy(df, apply_macro=False)

# Test 2: With Macro Filter
macro_trades, macro_wr, macro_pf, macro_pnl = run_strategy(df, apply_macro=True)

print(f"{'Strategy':<20} | {'Trades':<8} | {'Win Rate':<10} | {'Profit Factor':<15} | {'Total PnL':<10}")
print("-" * 75)
print(f"{'Baseline Z-Score':<20} | {baseline_trades:<8} | {baseline_wr:<9.2f}% | {baseline_pf:<15.2f} | ${baseline_pnl:<9.2f}")
print(f"{'With DXY/VIX Filter':<20} | {macro_trades:<8} | {macro_wr:<9.2f}% | {macro_pf:<15.2f} | ${macro_pnl:<9.2f}")

if macro_pnl > baseline_pnl:
    print("\nResult: Macro filters improved the overall PnL!")
else:
    print("\nResult: Macro filters reduced the PnL or had no positive effect.")

conn.close()
