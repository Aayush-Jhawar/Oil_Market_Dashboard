import sqlite3
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

print("="*100)
print("Forward Testing High-Frequency Z-Score Strategy on 15-Min Live DB")
print("(REAL DOLLARS: $1,000 Multiplier, $40 Slippage, Lowered Thresholds)")
print("="*100)

db_path = r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\DB\bars_15min_latest.db'
conn = sqlite3.connect(db_path)

tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)['name'].tolist()
month_map = {'F':1, 'G':2, 'H':3, 'J':4, 'K':5, 'M':6, 'N':7, 'Q':8, 'U':9, 'V':10, 'X':11, 'Z':12}

def parse_contract(table_name):
    parts = table_name.split('_')
    if len(parts) != 2: return None
    prefix, code = parts
    if len(code) != 3: return None
    month_char = code[0]
    year_str = code[1:]
    if month_char not in month_map: return None
    try:
        year = int(year_str)
        month = month_map[month_char]
        return (prefix, year, month, table_name)
    except:
        return None

cl_tables = []
co_tables = []
for t in tables:
    parsed = parse_contract(t)
    if parsed:
        if parsed[0] == 'CL':
            cl_tables.append(parsed)
        elif parsed[0] == 'CO':
            co_tables.append(parsed)

cl_tables.sort(key=lambda x: (x[1], x[2]))
co_tables.sort(key=lambda x: (x[1], x[2]))

wti_m = {}
for i, t in enumerate(cl_tables):
    if i + 1 > 12:
        break
    df = pd.read_sql(f"SELECT timestamp, close FROM {t[3]}", conn, parse_dates=['timestamp']).set_index('timestamp')
    df = df[~df.index.duplicated(keep='first')]
    wti_m[i+1] = df['close']

brent_m = {}
for i, t in enumerate(co_tables):
    if i + 1 > 12:
        break
    df = pd.read_sql(f"SELECT timestamp, close FROM {t[3]}", conn, parse_dates=['timestamp']).set_index('timestamp')
    df = df[~df.index.duplicated(keep='first')]
    brent_m[i+1] = df['close']

conn.close()

wti_idx = None
for s in wti_m.values():
    if wti_idx is None: wti_idx = s.index
    else: wti_idx = wti_idx.intersection(s.index)

for k in wti_m.keys():
    wti_m[k] = wti_m[k].loc[wti_idx]

brent_idx = None
for s in brent_m.values():
    if brent_idx is None: brent_idx = s.index
    else: brent_idx = brent_idx.intersection(s.index)

for k in brent_m.keys():
    brent_m[k] = brent_m[k].loc[brent_idx]

def get_regime(m1, m6, thresh_back, thresh_cont):
    ry = ((m1 - m6) / m1) * (365 / 150) * 100
    conds = [
        (ry > thresh_back), (ry <= thresh_back) & (ry > 5.0),
        (ry <= 5.0) & (ry >= -5.0), (ry < -5.0) & (ry >= thresh_cont), (ry < thresh_cont)
    ]
    return np.select(conds, ['Ext_Back', 'Back', 'Neutral', 'Cont', 'Ext_Cont'], default='Neutral')

wti_regime = get_regime(wti_m[1], wti_m[6], 21.25, -30.00) if 6 in wti_m else np.full(len(wti_idx), 'Neutral')
brent_regime = get_regime(brent_m[1], brent_m[6], 18.43, -30.00) if 6 in brent_m else np.full(len(brent_idx), 'Neutral')

results = []
WINDOW = 20
SLIPPAGE_POINTS = 0.04 # 4 ticks
CONTRACT_MULTIPLIER = 1000

def run_backtest(price_series, regime_series, name):
    df = pd.DataFrame({'price': price_series, 'regime': regime_series}).dropna()
    if len(df) < WINDOW: return
    
    df['ma'] = df['price'].rolling(WINDOW).mean()
    df['std'] = df['price'].rolling(WINDOW).std().replace(0, np.nan).ffill().fillna(0.001)
    df['z'] = (df['price'] - df['ma']) / df['std']
    
    df['thresh'] = 1.5 
    
    pos = pd.Series(np.nan, index=df.index)
    pos[df['z'] < -df['thresh']] = 1
    pos[df['z'] > df['thresh']] = -1
    
    crossed_up = (df['z'] > 0) & (df['z'].shift(1) < 0)
    crossed_down = (df['z'] < 0) & (df['z'].shift(1) > 0)
    pos[crossed_up | crossed_down] = 0
    pos[abs(df['z']) > 3.0] = 0
    
    pos = pos.ffill().fillna(0)
    df['pos'] = pos.shift(1).fillna(0)
    df['ret'] = df['price'].diff()
    df['pnl_raw'] = df['pos'] * df['ret']
    
    t_starts = df['pos'].diff().fillna(0) != 0
    t_ids = t_starts.cumsum()
    active_mask = df['pos'] != 0
    
    trade_pnls_raw = df.loc[active_mask, 'pnl_raw'].groupby(t_ids[active_mask]).sum()
    trade_pnls_raw = trade_pnls_raw[trade_pnls_raw != 0]
    
    # Apply Real Dollars Math
    trade_pnls_dollars = (trade_pnls_raw - SLIPPAGE_POINTS) * CONTRACT_MULTIPLIER
    
    if len(trade_pnls_dollars) > 0:
        wins = trade_pnls_dollars[trade_pnls_dollars > 0]
        losses = trade_pnls_dollars[trade_pnls_dollars < 0]
        win_rate = len(wins) / len(trade_pnls_dollars) * 100
        pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')
        
        cum_pnl = trade_pnls_dollars.cumsum()
        max_dd = (cum_pnl.cummax() - cum_pnl).max()
        sharpe = np.sqrt(252 * 24 * 4) * (trade_pnls_dollars.mean() / trade_pnls_dollars.std()) if trade_pnls_dollars.std() != 0 else 0
        expectancy = trade_pnls_dollars.mean()
    else:
        win_rate = pf = max_dd = sharpe = expectancy = 0
        
    results.append({
        "Instrument": name,
        "Win Rate": win_rate,
        "Profit Factor": pf,
        "Sharpe Ratio": sharpe,
        "Max Drawdown ($)": max_dd,
        "Total Trades": len(trade_pnls_dollars),
        "Total Return ($)": trade_pnls_dollars.sum(),
        "Expectancy ($)": expectancy
    })

def generate_all_and_test(m_dict, regime, prefix):
    if not m_dict: return
    max_m = max(m_dict.keys())
    for i in range(1, max_m-1):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict:
            run_backtest(m_dict[i] - 2*m_dict[i+1] + m_dict[i+2], regime, f"{prefix}_Fly_M{i}_M{i+1}_M{i+2}")
    for i in range(1, max_m-2):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict and (i+3) in m_dict:
            run_backtest(m_dict[i] - 3*m_dict[i+1] + 3*m_dict[i+2] - m_dict[i+3], regime, f"{prefix}_DFly_M{i}_M{i+1}_M{i+2}_M{i+3}")

print("Processing WTI 15-Min Live Forward Test...")
generate_all_and_test(wti_m, wti_regime, "WTI")

print("Processing Brent 15-Min Live Forward Test...")
generate_all_and_test(brent_m, brent_regime, "Brent")

res_df = pd.DataFrame(results)
if len(res_df) > 0:
    res_df = res_df.sort_values(by="Total Return ($)", ascending=False)
    res_df.to_csv("db_15min_forward_test_dollars.csv", index=False)

    print("\n--- OOS DB FORWARD TEST (15-MIN BARS, $1,000 MULT, $40 SLIPPAGE) ---")
    print(f"{'Instrument':<30} | {'Win Rate':<8} | {'PF':<5} | {'Max DD ($)':<10} | {'Trades':<6} | {'Expectancy ($)':<14} | {'Total PnL ($)'}")
    print("-" * 115)
    for _, row in res_df.head(20).iterrows():
        print(f"{row['Instrument']:<30} | {row['Win Rate']:>7.2f}% | {row['Profit Factor']:>4.2f} | ${row['Max Drawdown ($)']:<9.2f} | {row['Total Trades']:<6} | ${row['Expectancy ($)']:<13.2f} | ${row['Total Return ($)']:>6.2f}")
else:
    print("No valid data or trades generated.")
