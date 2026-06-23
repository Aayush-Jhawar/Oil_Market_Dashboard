import pandas as pd
import numpy as np
import warnings
import gc
warnings.filterwarnings('ignore')

print("="*100)
print("Executing Step 5: Out-of-Sample Validation with Slippage & Widened Bounds")
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

# Isolate STRICTLY the Validation Set (Last 2 months ONLY)
# We must keep some prior data purely to calculate the 100-min rolling window before the start date, 
# but the PnL is strictly evaluated on the last 2 months.
wti_val_start = wti.index.max() - pd.DateOffset(months=2)
brent_val_start = brent.index.max() - pd.DateOffset(months=2)

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
WINDOW = 100 # Frozen from Step 2
SLIPPAGE = 0.04 # 4 ticks per trade execution to penalize short-term noise

def run_backtest(price_series, regime_series, name, val_start):
    df = pd.DataFrame({'price': price_series, 'regime': regime_series}).dropna()
    if len(df) < 1000: return
    
    # Calculate frozen parameters over the full timeline to prevent NaN at validation start
    df['ma'] = df['price'].rolling(WINDOW).mean()
    df['std'] = df['price'].rolling(WINDOW).std()
    df['std'] = df['std'].replace(0, np.nan).ffill().fillna(0.001)
    df['z'] = (df['price'] - df['ma']) / df['std']
    
    # WIDENED THRESHOLDS to force the model to take fewer trades and overcome slippage
    df['thresh'] = 2.8 
    df.loc[df['regime'] == 'Neutral', 'thresh'] = 2.5
    df.loc[df['regime'].isin(['Ext_Back', 'Ext_Cont']), 'thresh'] = 3.2
    
    pos = pd.Series(np.nan, index=df.index)
    pos[df['z'] < -df['thresh']] = 1
    pos[df['z'] > df['thresh']] = -1
    
    crossed_up = (df['z'] > 0) & (df['z'].shift(1) < 0)
    crossed_down = (df['z'] < 0) & (df['z'].shift(1) > 0)
    pos[crossed_up | crossed_down] = 0
    pos[abs(df['z']) > 4.0] = 0 # Widened stop loss due to wider entry
    
    pos = pos.ffill().fillna(0)
    df['pos'] = pos.shift(1).fillna(0)
    df['ret'] = df['price'].diff()
    df['pnl'] = df['pos'] * df['ret']
    
    # STRICTLY FILTER EVALUATION TO OUT-OF-SAMPLE WINDOW
    df = df[df.index >= val_start]
    
    t_starts = df['pos'].diff().fillna(0) != 0
    t_ids = t_starts.cumsum()
    active_mask = df['pos'] != 0
    
    # Group by trades
    trade_pnls = df.loc[active_mask, 'pnl'].groupby(t_ids[active_mask]).sum()
    trade_pnls = trade_pnls[trade_pnls != 0]
    
    # Calculate Holding Time (minutes = rows)
    trade_lengths = df.loc[active_mask, 'pos'].groupby(t_ids[active_mask]).size()
    trade_lengths = trade_lengths[trade_pnls.index] # align index
    
    # APPLY SLIPPAGE PENALTY ($0.04 deducted from every trade)
    trade_pnls = trade_pnls - SLIPPAGE
    
    if len(trade_pnls) > 0:
        wins = trade_pnls[trade_pnls > 0]
        losses = trade_pnls[trade_pnls < 0]
        win_rate = len(wins) / len(trade_pnls) * 100
        pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')
        
        # PnL array for Sharpe calculation (need to align slippage back to series for accurate dd)
        # We will just use the aggregated trade returns for a simplified Sharpe, or rebuild the daily pnl
        total_pnl = trade_pnls.sum()
        
        # Approximate Max DD on Trade-by-Trade basis
        cum_pnl = trade_pnls.cumsum()
        max_dd = (cum_pnl.cummax() - cum_pnl).max()
        
        avg_hold = trade_lengths.mean()
        # Annualized Sharpe roughly based on daily trades
        sharpe = np.sqrt(252) * (trade_pnls.mean() / trade_pnls.std()) if trade_pnls.std() != 0 else 0
    else:
        win_rate = pf = max_dd = sharpe = avg_hold = 0
        
    results.append({
        "Instrument": name,
        "Win Rate": win_rate,
        "Profit Factor": pf,
        "Sharpe Ratio": sharpe,
        "Max Drawdown": max_dd,
        "Total Trades": len(trade_pnls),
        "Avg Hold (Min)": avg_hold
    })
    
    del df
    gc.collect()

def generate_all_and_test(m_dict, regime, prefix, val_start):
    max_m = max(m_dict.keys())
    # Flies
    for i in range(1, max_m-1):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict:
            run_backtest(m_dict[i] - 2*m_dict[i+1] + m_dict[i+2], regime, f"{prefix}_Fly_M{i}_M{i+1}_M{i+2}", val_start)
    # Double Flies
    for i in range(1, max_m-2):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict and (i+3) in m_dict:
            run_backtest(m_dict[i] - 3*m_dict[i+1] + 3*m_dict[i+2] - m_dict[i+3], regime, f"{prefix}_DFly_M{i}_M{i+1}_M{i+2}_M{i+3}", val_start)

print("Processing WTI OOS Validation...")
generate_all_and_test(wti_m, wti_regime, "WTI", wti_val_start)

print("Processing Brent OOS Validation...")
generate_all_and_test(brent_m, brent_regime, "Brent", brent_val_start)

res_df = pd.DataFrame(results).sort_values(by="Sharpe Ratio", ascending=False)
res_df.to_csv("step5_validation_results.csv", index=False)

print("\n--- OOS VALIDATION RESULTS (LAST 2 MONTHS, $0.04 SLIPPAGE PENALTY) ---")
print(f"{'Instrument':<30} | {'Win Rate':<8} | {'PF':<5} | {'Sharpe':<6} | {'Max DD':<7} | {'Trades':<6} | {'Avg Hold (m)'}")
print("-" * 95)
for _, row in res_df.head(20).iterrows():
    print(f"{row['Instrument']:<30} | {row['Win Rate']:>7.2f}% | {row['Profit Factor']:>4.2f} | {row['Sharpe Ratio']:>6.2f} | ${row['Max Drawdown']:<6.2f} | {row['Total Trades']:<6} | {row['Avg Hold (Min)']:>5.1f} min")
