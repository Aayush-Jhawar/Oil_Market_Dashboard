import pandas as pd
import numpy as np
import warnings
import gc
warnings.filterwarnings('ignore')

print("="*100)
print("Executing Steps 3 & 4: High-Frequency 1-Min Backtest (ALL INSTRUMENTS)")
print("="*100)

cols_wti = ['timestamp', 'date'] + [f'c{i}||weighted_mid' for i in range(1, 13)]
cols_brent = ['timestamp', 'date'] + [f'c{i}||weighted_mid' for i in range(1, 13)]

print("Loading 1-Minute Tick Data natively...")
wti = pd.read_csv(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\CL_outrights_1min_t.csv', header=1, usecols=lambda x: x in cols_wti)
brent = pd.read_csv(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\LCO_data.csv', header=1, usecols=lambda x: x in cols_brent)

for df in [wti, brent]:
    ts_col = 'timestamp' if 'timestamp' in df.columns else 'date'
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df.set_index(ts_col, inplace=True)
    df.sort_index(inplace=True)

# Isolate Training Set (Exclude last 2 months)
wti = wti[wti.index < (wti.index.max() - pd.DateOffset(months=2))]
brent = brent[brent.index < (brent.index.max() - pd.DateOffset(months=2))]

def extract_months(df):
    m = {}
    for i in range(1, 13):
        col = f'c{i}||weighted_mid'
        if col in df.columns: m[i] = df[col]
    return m

wti_m = extract_months(wti)
brent_m = extract_months(brent)

def get_regime(m1, m6, thresh_back, thresh_cont):
    ry = ((m1 - m6) / m1) * (365 / 150) * 100
    conds = [
        (ry > thresh_back), (ry <= thresh_back) & (ry > 5.0),
        (ry <= 5.0) & (ry >= -5.0), (ry < -5.0) & (ry >= thresh_cont), (ry < thresh_cont)
    ]
    return np.select(conds, ['Ext_Back', 'Back', 'Neutral', 'Cont', 'Ext_Cont'], default='Neutral')

wti_regime = get_regime(wti_m[1], wti_m[6], 21.25, -30.00) if 6 in wti_m else np.full(len(wti), 'Neutral')
brent_regime = get_regime(brent_m[1], brent_m[6], 18.43, -30.00) if 6 in brent_m else np.full(len(brent), 'Neutral')

results = []
WINDOW = 100 # Approx 100 minutes (2x Half-Life of ~50 mins)

def run_backtest(price_series, regime_series, name):
    df = pd.DataFrame({'price': price_series, 'regime': regime_series}).dropna()
    if len(df) < 1000: return
    
    df['ma'] = df['price'].rolling(WINDOW).mean()
    df['std'] = df['price'].rolling(WINDOW).std()
    
    # Forward fill std to handle 0 variance patches, replace 0 with small number
    df['std'] = df['std'].replace(0, np.nan).ffill().fillna(0.001)
    df['z'] = (df['price'] - df['ma']) / df['std']
    
    df['thresh'] = 2.0
    df.loc[df['regime'] == 'Neutral', 'thresh'] = 1.8
    df.loc[df['regime'].isin(['Ext_Back', 'Ext_Cont']), 'thresh'] = 2.5
    
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
    df['pnl'] = df['pos'] * df['ret']
    
    t_starts = df['pos'].diff().fillna(0) != 0
    t_ids = t_starts.cumsum()
    active_mask = df['pos'] != 0
    trades = df.loc[active_mask, 'pnl'].groupby(t_ids[active_mask]).sum()
    trades = trades[trades != 0]
    
    if len(trades) > 0:
        wins = trades[trades > 0]
        losses = trades[trades < 0]
        win_rate = len(wins) / len(trades) * 100
        pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')
        
        cum_pnl = df['pnl'].cumsum()
        max_dd = (cum_pnl.cummax() - cum_pnl).max()
        sharpe = np.sqrt(252*24*60) * (df['pnl'].mean() / df['pnl'].std()) if df['pnl'].std() != 0 else 0
    else:
        win_rate = pf = max_dd = sharpe = 0
        
    results.append({
        "Instrument": name,
        "Win Rate": win_rate,
        "Profit Factor": pf,
        "Sharpe Ratio": sharpe,
        "Max Drawdown": max_dd,
        "Total Trades": len(trades)
    })
    
    # Memory cleanup
    del df
    gc.collect()

def generate_all_and_test(m_dict, regime, prefix):
    max_m = max(m_dict.keys())
    # Spreads
    for i in range(1, max_m):
        if i in m_dict and (i+1) in m_dict:
            run_backtest(m_dict[i] - m_dict[i+1], regime, f"{prefix}_Spread_M{i}_M{i+1}")
    # Flies
    for i in range(1, max_m-1):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict:
            run_backtest(m_dict[i] - 2*m_dict[i+1] + m_dict[i+2], regime, f"{prefix}_Fly_M{i}_M{i+1}_M{i+2}")
    # Double Flies
    for i in range(1, max_m-2):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict and (i+3) in m_dict:
            run_backtest(m_dict[i] - 3*m_dict[i+1] + 3*m_dict[i+2] - m_dict[i+3], regime, f"{prefix}_DFly_M{i}_M{i+1}_M{i+2}_M{i+3}")

print("Processing WTI Instruments sequentially...")
generate_all_and_test(wti_m, wti_regime, "WTI")

print("Processing Brent Instruments sequentially...")
generate_all_and_test(brent_m, brent_regime, "Brent")

res_df = pd.DataFrame(results).sort_values(by="Sharpe Ratio", ascending=False)
res_df.to_csv("step34_backtest_all.csv", index=False)

print("\n--- TOP 30 BACKTEST RESULTS (TRAINING PERIOD - 1 MIN DATA) ---")
print(f"{'Instrument':<30} | {'Win Rate':<10} | {'PF':<6} | {'Sharpe':<8} | {'Max DD':<8} | {'Trades'}")
print("-" * 80)
for _, row in res_df.head(30).iterrows():
    print(f"{row['Instrument']:<30} | {row['Win Rate']:>8.2f}% | {row['Profit Factor']:>4.2f} | {row['Sharpe Ratio']:>6.2f} | ${row['Max Drawdown']:<7.2f} | {row['Total Trades']}")
