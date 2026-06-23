import sqlite3
import pandas as pd
import numpy as np
import warnings
import yfinance as yf

warnings.filterwarnings('ignore')

print("="*100)
print("Forward Testing High-Frequency Z-Score Strategy on 15-Min Live DB")
print("WITH MACRO DXY & VIX REGIME FILTERS")
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

# FETCH MACRO DATA
print("Fetching ^VIX and DX-Y.NYB for Macro Filter...")
macro_period = "7d"
vix_hist = yf.Ticker("^VIX").history(period=macro_period, interval="15m")
dxy_hist = yf.Ticker("DX-Y.NYB").history(period=macro_period, interval="15m")

if not vix_hist.empty and not dxy_hist.empty:
    vix_hist.index = vix_hist.index.tz_localize(None)
    dxy_hist.index = dxy_hist.index.tz_localize(None)
    
    macro_df = pd.DataFrame(index=vix_hist.index)
    macro_df['vix'] = vix_hist['Close']
    macro_df['dxy'] = dxy_hist['Close']
    
    # Calculate 4-hour Moving Average for trends (16 periods of 15m)
    macro_df['vix_ma'] = macro_df['vix'].rolling(16).mean()
    macro_df['dxy_ma'] = macro_df['dxy'].rolling(16).mean()
    
    macro_df['vix_bullish'] = macro_df['vix'] > macro_df['vix_ma']
    macro_df['dxy_bullish'] = macro_df['dxy'] > macro_df['dxy_ma']
    
    # Align to energy indices (WTI and Brent) using forward fill for gaps
    wti_macro = macro_df.reindex(wti_idx, method='ffill').bfill()
    brent_macro = macro_df.reindex(brent_idx, method='ffill').bfill()
    print("Macro data loaded successfully.\n")
else:
    print("WARNING: Could not fetch macro data. Test will run without macro filters.\n")
    wti_macro = pd.DataFrame(index=wti_idx)
    brent_macro = pd.DataFrame(index=brent_idx)
    for col in ['vix_bullish', 'dxy_bullish']:
        wti_macro[col] = False
        brent_macro[col] = False

results_baseline = []
results_macro = []
WINDOW = 20
SLIPPAGE_POINTS = 0.04 # 4 ticks
CONTRACT_MULTIPLIER = 1000

def run_backtest(price_series, name, macro_filters, results_list, use_macro_filter=False):
    df = pd.DataFrame({'price': price_series}).dropna()
    df = df.join(macro_filters)
    if len(df) < WINDOW: return
    
    df['ma'] = df['price'].rolling(WINDOW).mean()
    df['std'] = df['price'].rolling(WINDOW).std().replace(0, np.nan).ffill().fillna(0.001)
    df['z'] = (df['price'] - df['ma']) / df['std']
    
    df['thresh'] = 1.5 
    
    pos = pd.Series(np.nan, index=df.index)
    
    # Baseline Entry logic
    long_cond = df['z'] < -df['thresh']
    short_cond = df['z'] > df['thresh']
    
    # Apply Macro Filter
    if use_macro_filter:
        # Risk-Off Regime (DXY up, VIX up) -> Bearish for oil -> Block Longs
        risk_off = df['vix_bullish'] & df['dxy_bullish']
        # Risk-On Regime (DXY down, VIX down) -> Bullish for oil -> Block Shorts
        risk_on = (~df['vix_bullish']) & (~df['dxy_bullish'])
        
        long_cond = long_cond & (~risk_off)
        short_cond = short_cond & (~risk_on)
        
    pos[long_cond] = 1
    pos[short_cond] = -1
    
    # Exit logic
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
        
        if name == "WTI-Brent_Spread" and use_macro_filter:
            with open("wti_brent_trade_log.md", "w") as f:
                f.write("# WTI-Brent Walk Forward Trade Log (Macro Filtered)\n\n")
                f.write("| Entry Time | Exit Time | Direction | Return ($) | Cumulative PnL ($) |\n")
                f.write("| :--- | :--- | :--- | :--- | :--- |\n")
                
                # Get the actual trade instances
                active_df = df.loc[active_mask]
                trade_groups = active_df.groupby(t_ids[active_mask])
                for idx, (t_id, grp) in enumerate(trade_groups):
                    entry_time = grp.index[0]
                    exit_time = grp.index[-1]
                    direction = "LONG" if grp['pos'].iloc[0] == 1 else "SHORT"
                    pnl_raw = grp['pnl_raw'].sum()
                    pnl_dol = (pnl_raw - SLIPPAGE_POINTS) * CONTRACT_MULTIPLIER
                    cum = cum_pnl.iloc[idx]
                    f.write(f"| {entry_time} | {exit_time} | {direction} | ${pnl_dol:,.2f} | ${cum:,.2f} |\n")
                    
    else:
        win_rate = pf = max_dd = sharpe = expectancy = 0
        
    results_list.append({
        "Instrument": name,
        "Win Rate": win_rate,
        "Profit Factor": pf,
        "Sharpe Ratio": sharpe,
        "Max Drawdown ($)": max_dd,
        "Total Trades": len(trade_pnls_dollars),
        "Total Return ($)": trade_pnls_dollars.sum(),
        "Expectancy ($)": expectancy
    })

def generate_all_and_test(m_dict, macro_data, prefix):
    if not m_dict: return
    max_m = max(m_dict.keys())
    for i in range(1, max_m-1):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict:
            price = m_dict[i] - 2*m_dict[i+1] + m_dict[i+2]
            name = f"{prefix}_Fly_M{i}_M{i+1}_M{i+2}"
            run_backtest(price, name, macro_data, results_baseline, False)
            run_backtest(price, name, macro_data, results_macro, True)
            
    for i in range(1, max_m-2):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict and (i+3) in m_dict:
            price = m_dict[i] - 3*m_dict[i+1] + 3*m_dict[i+2] - m_dict[i+3]
            name = f"{prefix}_DFly_M{i}_M{i+1}_M{i+2}_M{i+3}"
            run_backtest(price, name, macro_data, results_baseline, False)
            run_backtest(price, name, macro_data, results_macro, True)

generate_all_and_test(wti_m, wti_macro, "WTI")
generate_all_and_test(brent_m, brent_macro, "Brent")

if 1 in wti_m and 1 in brent_m:
    price_spread = wti_m[1] - brent_m[1]
    name_spread = "WTI-Brent_Spread"
    run_backtest(price_spread, name_spread, wti_macro, results_baseline, False)
    run_backtest(price_spread, name_spread, wti_macro, results_macro, True)

res_base = pd.DataFrame(results_baseline)
res_macro = pd.DataFrame(results_macro)

print("\n=== AGGREGATE PERFORMANCE COMPARISON ===")
print("BASELINE (Z-Score Only):")
if not res_base.empty:
    print(f"Total Return: ${res_base['Total Return ($)'].sum():,.2f}")
    print(f"Total Trades: {res_base['Total Trades'].sum()}")
    print(f"Avg Win Rate: {res_base['Win Rate'].mean():.2f}%")
    print(f"Avg Profit Factor: {res_base['Profit Factor'].replace(float('inf'), np.nan).mean():.2f}")
else:
    print("No valid baseline data.")

print("\nMACRO FILTERED (Z-Score + DXY/VIX Trend):")
if not res_macro.empty:
    print(f"Total Return: ${res_macro['Total Return ($)'].sum():,.2f}")
    print(f"Total Trades: {res_macro['Total Trades'].sum()}")
    print(f"Avg Win Rate: {res_macro['Win Rate'].mean():.2f}%")
    print(f"Avg Profit Factor: {res_macro['Profit Factor'].replace(float('inf'), np.nan).mean():.2f}")
else:
    print("No valid macro data.")

print("\nDetailed Comparison saved to db_macro_comparison.csv")
res_macro['Strategy'] = 'Macro_Filtered'
res_base['Strategy'] = 'Baseline'
merged = pd.concat([res_base, res_macro])
merged.to_csv("db_macro_comparison.csv", index=False)
