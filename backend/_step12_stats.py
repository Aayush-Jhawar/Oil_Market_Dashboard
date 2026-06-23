import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint
import warnings
import re
warnings.filterwarnings('ignore')

# 1. LOAD DATA
print("Loading WTI and Brent data natively...")
# We load all possible columns matching cX||weighted_mid up to c12
cols = ['timestamp', 'date'] + [f'c{i}||weighted_mid' for i in range(1, 13)]

def filter_cols(c):
    return c in cols

df_wti = pd.read_csv(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\CL_outrights_1min_t.csv', header=1, usecols=lambda x: x in cols)
df_brent = pd.read_csv(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\LCO_data.csv', header=1, usecols=lambda x: x in cols)

for df in [df_wti, df_brent]:
    ts_col = 'timestamp' if 'timestamp' in df.columns else 'date'
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df.set_index(ts_col, inplace=True)
    df.sort_index(inplace=True)

# Resample to 1-Hour purely for structural statistics (Hurst, ADF) to save CPU
wti = df_wti.resample('1h').last().dropna(subset=['c1||weighted_mid'])
brent = df_brent.resample('1h').last().dropna(subset=['c1||weighted_mid'])
del df_wti
del df_brent

# Align indices for inter-commodity spreads
idx = wti.index.intersection(brent.index)
wti = wti.loc[idx]
brent = brent.loc[idx]

# 2. INSTRUMENT CONSTRUCTION
print("Constructing All Available Instruments...")
instruments = pd.DataFrame(index=idx)

def extract_months(df):
    months = {}
    for i in range(1, 13):
        col = f'c{i}||weighted_mid'
        if col in df.columns:
            months[i] = df[col]
    return months

wti_m = extract_months(wti)
brent_m = extract_months(brent)

# Construct Spreads, Flies, Double Flies
def construct_all(m_dict, prefix):
    max_m = max(m_dict.keys())
    # Spreads
    for i in range(1, max_m):
        if i in m_dict and (i+1) in m_dict:
            instruments[f'{prefix}_Spread_M{i}_M{i+1}'] = m_dict[i] - m_dict[i+1]
    # Flies
    for i in range(1, max_m-1):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict:
            instruments[f'{prefix}_Fly_M{i}_M{i+1}_M{i+2}'] = m_dict[i] - 2*m_dict[i+1] + m_dict[i+2]
    # Double Flies
    for i in range(1, max_m-2):
        if i in m_dict and (i+1) in m_dict and (i+2) in m_dict and (i+3) in m_dict:
            instruments[f'{prefix}_DFly_M{i}_M{i+1}_M{i+2}_M{i+3}'] = m_dict[i] - 3*m_dict[i+1] + 3*m_dict[i+2] - m_dict[i+3]

construct_all(wti_m, "WTI")
construct_all(brent_m, "Brent")

# Inter-commodity Cointegration (WTI M1 vs Brent M1)
score, p_val, _ = coint(wti_m[1].dropna(), brent_m[1].dropna())
print(f"WTI/Brent M1 Cointegration p-value: {p_val:.4f}")
if p_val < 0.05:
    X = sm.add_constant(brent_m[1])
    model = sm.OLS(wti_m[1], X).fit()
    alpha, beta = model.params
    instruments['WTI_Brent_Reg_Spread'] = wti_m[1] - (beta * brent_m[1]) - alpha
    print(f"Constructed WTI-Brent Regression Spread: WTI - ({beta:.2f} * Brent) - {alpha:.2f}")

# 3. REGIME TAGGING
def roll_yield(m1, m6):
    return ((m1 - m6) / m1) * (365 / 150) * 100

wti_ry = roll_yield(wti_m[1], wti_m[6])
conditions = [
    (wti_ry > 21.25),
    (wti_ry <= 21.25) & (wti_ry > 5.0),
    (wti_ry <= 5.0) & (wti_ry >= -5.0),
    (wti_ry < -5.0) & (wti_ry >= -30.0),
    (wti_ry < -30.0)
]
choices = ['Extreme_Back', 'Back', 'Neutral', 'Contango', 'Extreme_Contango']
instruments['Regime'] = np.select(conditions, choices, default='Neutral')

# 4. STATISTICAL CHARACTERIZATION (Hurst, ADF, Half-Life)
def compute_hurst(ts):
    lags = range(2, 20)
    tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
    if len(tau) == 0 or np.any(np.isnan(tau)) or np.any(tau == 0): return np.nan
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return poly[0] * 2.0

def compute_half_life(ts):
    ts_lag = ts.shift(1).dropna()
    ts_diff = ts.diff().dropna()
    ts_idx = ts_diff.index.intersection(ts_lag.index)
    if len(ts_idx) < 10: return np.nan
    
    X = sm.add_constant(ts_lag.loc[ts_idx])
    model = sm.OLS(ts_diff.loc[ts_idx], X).fit()
    lam = model.params.iloc[1]
    if lam >= 0: return np.inf
    return -np.log(2) / lam

print("\nExecuting Step 2: Statistical Tests per Regime (Top 50 Instruments)")
results = []
regimes = ['Back', 'Neutral'] # Limit to largest regimes to ensure enough samples

# Process in chunks to give progress output
for i, col in enumerate(instruments.columns):
    if col == 'Regime': continue
    
    for r in regimes:
        sub = instruments[instruments['Regime'] == r][col].dropna()
        if len(sub) < 100: continue
        
        try:
            # ADF
            adf_stat, p_val, _, _, _, _ = adfuller(sub, maxlag=1)
            # Hurst
            H = compute_hurst(sub.values)
            # Half-life
            hl = compute_half_life(sub)
            
            results.append({
                "Instrument": col,
                "Regime": r,
                "Hurst": H,
                "ADF_p": p_val,
                "HalfLife_Hrs": hl
            })
        except Exception as e:
            pass
    
    if i % 10 == 0:
        print(f"Processed {i}/{len(instruments.columns)} instruments...")

res_df = pd.DataFrame(results)
print("\n--- STATISTICAL RANKING (Sorted by Mean Reversion / Ascending Hurst) ---")
print(f"{'Instrument':<35} | {'Regime':<10} | {'Hurst':<6} | {'ADF p-val':<10} | {'Half-Life (Hrs)':<15}")
print("-" * 85)
for _, row in res_df.sort_values("Hurst").head(30).iterrows():
    print(f"{row['Instrument']:<35} | {row['Regime']:<10} | {row['Hurst']:.3f}  | {row['ADF_p']:.4f}     | {row['HalfLife_Hrs']:.2f}")

res_df.to_csv("step12_stats_output.csv", index=False)
