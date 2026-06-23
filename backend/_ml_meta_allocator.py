import pandas as pd
import numpy as np
import json
from sklearn.ensemble import RandomForestRegressor
from scipy.special import softmax
import gc
import warnings
warnings.filterwarnings('ignore')

COMMODITIES = {
    "WTI": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\CL_outrights_1min_t.csv",
    "Brent": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\LCO_data.csv",
    "HeatingOil": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\HO_data.csv",
    "Gasoil": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\LGO_data.csv",
}

results = []

for symbol, path in COMMODITIES.items():
    print(f"Processing {symbol}...")
    try:
        # The first row is usually meta, the second is the actual header
        df = pd.read_csv(
            path,
            header=1,
            nrows=100000 
        )
        
        # Determine timestamp column name (could be 'timestamp' or 'date')
        ts_col = [c for c in df.columns if 'timestamp' in c.lower() or 'date' in c.lower()][0]
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        df = df.set_index(ts_col)
        
        df = df.resample('5min').last().dropna(how='all')
        
        # Dynamically find the mid columns
        c1_col = [c for c in df.columns if 'c1' in c and 'mid' in c][0]
        c2_col = [c for c in df.columns if 'c2' in c and 'mid' in c][0]
        c3_col = [c for c in df.columns if 'c3' in c and 'mid' in c][0]
        c4_col = [c for c in df.columns if 'c4' in c and 'mid' in c][0]
        
        m1 = df[c1_col].astype(float).ffill()
        m2 = df[c2_col].astype(float).ffill()
        m3 = df[c3_col].astype(float).ffill()
        m4 = df[c4_col].astype(float).ffill()
        
        instruments = {
            "DFly M1-M2-M3-M4": m1 - 3*m2 + 3*m3 - m4,
            "Outright M1": m1
        }
        
        for name, series in instruments.items():
            s = series.to_frame("close").dropna()
            
            # --- FEATURE ENGINEERING (FACTORS) ---
            s["vol_1h"] = s["close"].rolling(12).std()
            s["vol_24h"] = s["close"].rolling(288).std()
            s["roc_1h"] = s["close"].pct_change(12)
            ema12 = s["close"].ewm(span=12).mean()
            ema26 = s["close"].ewm(span=26).mean()
            s["macd"] = ema12 - ema26
            s["spread_level"] = m1 - m2
            
            # --- STRATEGY SIGNALS ---
            ma = s["close"].rolling(20).mean()
            std = s["close"].rolling(20).std()
            sig_bb = pd.Series(0, index=s.index)
            sig_bb[s["close"] < (ma - 2*std)] = 1
            sig_bb[s["close"] > (ma + 2*std)] = -1
            sig_bb = sig_bb.replace(0, np.nan).ffill().fillna(0)
            
            z = (s["close"] - ma) / std
            sig_z = pd.Series(0, index=s.index)
            sig_z[z < -2] = 1
            sig_z[z > 2] = -1
            sig_z = sig_z.replace(0, np.nan).ffill().fillna(0)
            
            ema_fast = s["close"].ewm(span=9).mean()
            ema_slow = s["close"].ewm(span=21).mean()
            sig_ema = pd.Series(0, index=s.index)
            sig_ema[ema_fast > ema_slow] = 1
            sig_ema[ema_fast < ema_slow] = -1
            
            ret = s["close"].diff().shift(-1)
            
            s["target_BB"] = (sig_bb * ret).rolling(12).sum().shift(-12)
            s["target_Z"] = (sig_z * ret).rolling(12).sum().shift(-12)
            s["target_EMA"] = (sig_ema * ret).rolling(12).sum().shift(-12)
            
            s = s.dropna()
            if len(s) < 1000:
                continue
                
            features = ["vol_1h", "vol_24h", "roc_1h", "macd", "spread_level"]
            targets = ["target_BB", "target_Z", "target_EMA"]
            
            X = s[features].replace([np.inf, -np.inf], np.nan).fillna(0)
            Y = s[targets].fillna(0)
            
            split_idx = int(len(s) * 0.8)
            X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
            Y_train, Y_test = Y.iloc[:split_idx], Y.iloc[split_idx:]
            
            model = RandomForestRegressor(n_estimators=10, max_depth=5, random_state=42, n_jobs=-1)
            model.fit(X_train, Y_train)
            
            preds = model.predict(X_test)
            weights = softmax(preds, axis=1)
            avg_weights = weights.mean(axis=0)
            
            results.append({
                "Commodity": symbol,
                "Structure": name,
                "Avg_Weight_BB": round(float(avg_weights[0]) * 100, 2),
                "Avg_Weight_Z": round(float(avg_weights[1]) * 100, 2),
                "Avg_Weight_EMA": round(float(avg_weights[2]) * 100, 2),
                "Feature_Importance": dict(zip(features, [round(f, 3) for f in model.feature_importances_]))
            })
            
        del df
        gc.collect()
        
    except Exception as e:
        print(f"Error on {symbol}: {str(e)}")

with open("_ml_weights.json", "w") as f:
    json.dump(results, f, indent=2)

print("ML Allocation Complete!")
