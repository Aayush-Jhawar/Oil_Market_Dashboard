import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prediction.features.feature_matrix import build_historical_feature_matrix, add_target_variables
from prediction.features.feature_store_service import FeatureStoreService
from prediction.models.ensemble import ModelEnsemble
from prediction.regime.regime_engine import RegimeEngine
from services.price_fetcher import PriceFetcher

def plot_fair_value():
    symbols_to_plot = ['WTI_CAL_SPREAD', 'WTI_FLY', '3-2-1CRACK']
    out_dir = r"C:\Users\aayush.jhawar\.gemini\antigravity-ide\brain\62b11e16-9b19-4bd1-bd36-cf0ba8e5f55c"
    
    for sym in symbols_to_plot:
        try:
            print(f"Generating plot for {sym}...")
            hist_data = PriceFetcher.fetch_historical(sym, period="3y")
            if not hist_data or len(hist_data) < 50:
                print(f"Not enough data for {sym}")
                continue
                
            df = pd.DataFrame(hist_data)
            df = df.rename(columns={"timestamp": "date"})
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df["date"] = pd.to_datetime(df["date"])
            df = df.drop_duplicates(subset=["date"], keep="last").set_index("date")
            
            # Use FeatureStoreService for features
            feature_store = FeatureStoreService(use_pca=False)
            raw_feat, feature_matrix = feature_store.fit_transform_historical(df, None, None, None, None)
            
            if feature_matrix.empty:
                continue
                
            horizon = 5
            is_spread = "SPREAD" in sym or "FLY" in sym or "CRACK" in sym
            df_feat = add_target_variables(feature_matrix, df, {f"{horizon}d": horizon}, is_spread=is_spread)
            
            test_size = int(len(df_feat) * 0.2)
            if test_size < 10:
                continue
                
            df_test = df_feat.iloc[-test_size:].copy()
            df_prices = df.loc[df_test.index]
            
            ensemble = ModelEnsemble(horizon=horizon, symbol=sym)
            ensemble.load_all()
            regime_engine = RegimeEngine()
            regime_engine.load_all()
            
            regimes = regime_engine.classify_history(raw_feat.loc[df_test.index])
            df_test["regime_label"] = regimes["regime_label"]
            
            dates = []
            actuals = []
            fair_values = []
            probs = []
            
            for date, row in df_test.iterrows():
                feats_dict = row.drop(["regime_label"]).to_dict()
                pred = ensemble.predict(feats_dict, row["regime_label"])
                
                # 'expected_return' is in percent, we need to convert back to dollars for plotting.
                # Actually, our target return for spreads might be dollar difference, 
                # let's look at how add_target_variables did it:
                # For spreads, it's df["close"].shift(-h) - df["close"]
                # So expected_return is already in dollar terms if `is_spread=True`.
                # Let's verify this... wait, ModelEnsemble might assume it's percent, but 
                # train.py just passes whatever add_target_variables returns.
                # Let's plot `price + predicted_change` as Fair Value.
                
                # In ensemble.predict, if it multiplied by 100 assuming percent, we need to divide by 100.
                # Let's just use the raw global pred for safety if needed, but expected_return is fine.
                raw_pred = ensemble.return_model.predict_single(feats_dict)["prediction_value"]
                
                actual_price = df_prices.loc[date, "close"]
                fair_val = actual_price + raw_pred
                
                dates.append(date)
                actuals.append(actual_price)
                fair_values.append(fair_val)
                probs.append(pred.get("ensemble_prob", 0.5))
                
            plt.figure(figsize=(12, 6))
            plt.plot(dates, actuals, label='Actual Spread Price', color='blue', alpha=0.7)
            plt.plot(dates, fair_values, label='LightGBM Fair Value (+5d Expected)', color='orange', linestyle='--', alpha=0.8)
            plt.title(f"{sym}: Actual vs Model Fair Value (Out of Sample)")
            plt.xlabel("Date")
            plt.ylabel("Price / Spread Value ($)")
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            # Save plot
            file_name = f"{sym}_fair_value.png"
            plt.savefig(os.path.join(out_dir, file_name))
            plt.close()
            print(f"Saved plot for {sym} to {file_name}")
            
        except Exception as e:
            print(f"Error plotting {sym}: {e}")

if __name__ == "__main__":
    plot_fair_value()
