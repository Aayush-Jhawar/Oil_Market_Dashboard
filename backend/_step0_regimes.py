import pandas as pd
import numpy as np
import sqlite3
import warnings
import json
warnings.filterwarnings('ignore')

FILES = {
    "WTI": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\CL_outrights_1min_t.csv",
    "Brent": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\LCO_data.csv",
    "HeatingOil": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\HO_data.csv",
    "Gasoil": r"C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data\LGO_data.csv"
}

results_table = []

def calc_roll_yield(m1, mn, days):
    return ((m1 - mn) / m1) * (365 / days) * 100

print("="*100)
print("Executing Step 0: Regime Classification Framework (NATIVE 1-MIN DATA, NO DOWNSAMPLING)")
print("="*100)

for symbol, path in FILES.items():
    print(f"Processing {symbol} natively...")
    try:
        # Load native 1-min data (only necessary columns to save RAM)
        df = pd.read_csv(path, header=1, usecols=lambda c: c in [
            'timestamp', 'date', 'c1||weighted_mid', 'c2||weighted_mid', 
            'c6||weighted_mid', 'c12||weighted_mid'
        ])
        
        ts_col = 'timestamp' if 'timestamp' in df.columns else 'date'
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
        df = df.set_index(ts_col).sort_index()
        
        # REMOVED DOWNSAMPLING
        # REMOVED FORWARD FILLING
        # Treating breaks in data as breaks (if NaN, calculation yields NaN)
        
        m1 = df['c1||weighted_mid'].astype(float)
        m2 = df['c2||weighted_mid'].astype(float)
        m6 = df['c6||weighted_mid'].astype(float)
        if 'c12||weighted_mid' in df.columns:
            m12 = df['c12||weighted_mid'].astype(float)
        else:
            m12 = np.nan
        
        # Calculate Roll Yields
        df['M1_M6_RY'] = calc_roll_yield(m1, m6, 150)
        df['M1_M2_RY'] = calc_roll_yield(m1, m2, 30)
        df['M1_M12_RY'] = calc_roll_yield(m1, m12, 330) if 'c12||weighted_mid' in df.columns else np.nan
        
        # Drop rows where we can't calculate primary regime (M1-M6)
        df = df.dropna(subset=['M1_M6_RY'])
        
        # Split Train and Validation (Last 2 months)
        if not df.empty:
            end_date = df.index.max()
            val_start = end_date - pd.DateOffset(months=2)
            
            train = df[df.index < val_start]
            val = df[df.index >= val_start]
            
            # Calibration strictly on Training Set
            train_pos = train[train['M1_M6_RY'] > 0]['M1_M6_RY']
            train_neg = train[train['M1_M6_RY'] < 0]['M1_M6_RY']
            
            ext_back_bound = train_pos.quantile(0.90) if not train_pos.empty else 30.0
            ext_cont_bound = train_neg.quantile(0.10) if not train_neg.empty else -30.0
            
            # Fallbacks if distribution is too tight
            if ext_back_bound < 5.0: ext_back_bound = 30.0
            if ext_cont_bound > -5.0: ext_cont_bound = -30.0
            
            print(f"  {symbol} Thresholds -> Ext Back: >{ext_back_bound:.2f}%, Ext Cont: <{ext_cont_bound:.2f}%")
            
            # Assign Regimes based on M1-M6 primary
            conditions = [
                (df['M1_M6_RY'] > ext_back_bound),
                (df['M1_M6_RY'] <= ext_back_bound) & (df['M1_M6_RY'] > 5.0),
                (df['M1_M6_RY'] <= 5.0) & (df['M1_M6_RY'] >= -5.0),
                (df['M1_M6_RY'] < -5.0) & (df['M1_M6_RY'] >= ext_cont_bound),
                (df['M1_M6_RY'] < ext_cont_bound)
            ]
            choices = ['Extreme Backwardation', 'Backwardation', 'Neutral', 'Contango', 'Extreme Contango']
            df['Regime'] = np.select(conditions, choices, default='Neutral')
            
            pcts = df['Regime'].value_counts(normalize=True) * 100
            
            # Calculate Current Regime from DB
            db_regime = "N/A"
            try:
                conn = sqlite3.connect(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\DB\bars_15min_latest.db')
                if symbol == "WTI":
                    t1, t6 = "CL_N26", "CL_Z26" 
                elif symbol == "Brent":
                    t1, t6 = "CO_Q26", "CO_Z26"
                else:
                    t1, t6 = None, None
                    
                if t1 and t6:
                    db_m1 = pd.read_sql(f"SELECT close FROM {t1} ORDER BY timestamp DESC LIMIT 1", conn).iloc[0,0]
                    db_m6 = pd.read_sql(f"SELECT close FROM {t6} ORDER BY timestamp DESC LIMIT 1", conn).iloc[0,0]
                    db_ry = calc_roll_yield(db_m1, db_m6, 150)
                    
                    if db_ry > ext_back_bound: db_regime = "Extreme Backwardation"
                    elif db_ry > 5.0: db_regime = "Backwardation"
                    elif db_ry >= -5.0: db_regime = "Neutral"
                    elif db_ry >= ext_cont_bound: db_regime = "Contango"
                    else: db_regime = "Extreme Contango"
                conn.close()
            except Exception as e:
                pass
            
            results_table.append({
                "Commodity": symbol,
                "Ext_Back": pcts.get("Extreme Backwardation", 0.0),
                "Back": pcts.get("Backwardation", 0.0),
                "Neutral": pcts.get("Neutral", 0.0),
                "Cont": pcts.get("Contango", 0.0),
                "Ext_Cont": pcts.get("Extreme Contango", 0.0),
                "Current_DB": db_regime
            })
            
    except Exception as e:
        print(f"Failed {symbol}: {e}")

print("\n--- REGIME DISTRIBUTION TABLE (NATIVE 1-MIN DATA) ---")
print(f"{'Commodity':<12} | {'% Ext Back':<10} | {'% Back':<8} | {'% Neutral':<10} | {'% Cont':<8} | {'% Ext Cont':<12} | {'Current DB'}")
print("-" * 90)
for r in results_table:
    print(f"{r['Commodity']:<12} | {r['Ext_Back']:>9.1f}% | {r['Back']:>7.1f}% | {r['Neutral']:>9.1f}% | {r['Cont']:>7.1f}% | {r['Ext_Cont']:>11.1f}% | {r['Current_DB']}")

with open('regime_table_1min.json', 'w') as f:
    json.dump(results_table, f)
