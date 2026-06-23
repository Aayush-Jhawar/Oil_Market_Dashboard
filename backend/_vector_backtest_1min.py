import pandas as pd
import numpy as np
import json

def get_data():
    df = pd.read_csv(
        r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\CL_outrights_1min_t.csv',
        usecols=['timestamp', 'c1||weighted_mid', 'c2||weighted_mid', 'c3||weighted_mid', 'c4||weighted_mid'],
        skiprows=[1], # Skip the second row if it's meta
    )
    # The first row is the header. The second row might be meta. Wait, usecols and skiprows=1 might be enough.
    return df

df = pd.read_csv(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\CL_outrights_1min_t.csv', skiprows=[0])
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
df = df.set_index('timestamp')

m1 = df['c1||weighted_mid'].astype(float)
m2 = df['c2||weighted_mid'].astype(float)
m3 = df['c3||weighted_mid'].astype(float)
m4 = df['c4||weighted_mid'].astype(float)

# Forward fill small gaps
m1 = m1.ffill()
m2 = m2.ffill()
m3 = m3.ffill()
m4 = m4.ffill()

instruments = {
    "Spread M1-M2": m1 - m2,
    "Fly M1-M2-M3": m1 - 2*m2 + m3,
    "DFly M1-M2-M3-M4": m1 - 3*m2 + 3*m3 - m4,
    "Outright M1": m1
}

results = []

for name, series in instruments.items():
    s = series.to_frame("close").dropna()
    s["open"] = s["close"].shift(1).fillna(s["close"])
    
    # 1. Bollinger Band Mean Reversion
    ma = s["close"].rolling(100).mean() # 100-min rolling for 1min data
    std = s["close"].rolling(100).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    
    sig_bb = pd.Series(0, index=s.index)
    sig_bb[s["close"] < lower] = 1
    sig_bb[s["close"] > upper] = -1
    sig_bb[((s["close"] >= ma) & (s["close"].shift(1) < ma)) | ((s["close"] <= ma) & (s["close"].shift(1) > ma))] = 0
    sig_bb = sig_bb.replace(0, np.nan).ffill().fillna(0)
    
    # 2. EMA Crossover (9/21 minutes)
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
        pos = sig.shift(1).fillna(0)
        ret = s["close"].diff()
        pnl = pos * ret
        
        # Split into periods
        # Historical: until 2023-12-31
        # Stress (2022 H1)
        # Fwd: 2024 onwards
        
        def calc_metrics(pnl_sub, pos_sub, ret_sub):
            t_starts = pos_sub.diff().fillna(0) != 0
            t_ids = t_starts.cumsum()
            period_trades = (pos_sub * ret_sub).groupby(t_ids).sum()
            period_trades = period_trades[period_trades != 0]
            
            if len(period_trades) == 0:
                return {"accuracy": 0.0, "pf": 0.0, "max_dd": 0.0, "wl": 0.0}
            
            wins = period_trades[period_trades > 0]
            losses = period_trades[period_trades < 0]
            acc = len(wins) / len(period_trades) * 100
            pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
            wl = (len(wins) / len(losses)) if len(losses) > 0 else float('inf')
            
            cum = pnl_sub.cumsum()
            peak = cum.cummax()
            dd = peak - cum
            max_dd = dd.max()
            
            return {"accuracy": acc, "pf": pf, "max_dd": max_dd, "wl": wl}
            
        mh = calc_metrics(pnl.loc[:"2023-12-31"], pos.loc[:"2023-12-31"], ret.loc[:"2023-12-31"])
        ms = calc_metrics(pnl.loc["2022-02-01":"2022-06-30"], pos.loc["2022-02-01":"2022-06-30"], ret.loc["2022-02-01":"2022-06-30"])
        mf = calc_metrics(pnl.loc["2024-01-01":], pos.loc["2024-01-01":], ret.loc["2024-01-01":])
        
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
