import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prediction.features.feature_matrix import build_historical_feature_matrix, add_target_variables
from prediction.features.feature_store_service import FeatureStoreService
from prediction.models.ensemble import ModelEnsemble
from prediction.regime.regime_engine import RegimeEngine
from database import engine

def run_backtest():
    symbols = [
        "WTI", "Brent", "RBOB", "HO", "GO", "NG", 
        "3-2-1CRACK", "GASCRACK", "DIESELCRACK", 
        "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY",
        "WTI_CAL_SPREAD", "BRENT_CAL_SPREAD", "WTI-Brent"
    ]
    
    results = []
    
    for sym in symbols:
        try:
            print(f"Running backtest for {sym}...")
            from services.price_fetcher import PriceFetcher
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
                
            # Add target variable (5 days horizon)
            horizon = 5
            is_spread = "SPREAD" in sym or "FLY" in sym or "CRACK" in sym
            df_feat = add_target_variables(feature_matrix, df, {f"{horizon}d": horizon}, is_spread=is_spread)
            
            # Out of sample split (last 20%)
            test_size = int(len(df_feat) * 0.2)
            if test_size < 10:
                continue
                
            df_test = df_feat.iloc[-test_size:].copy()
            y_ret = df_test[f"target_return_{horizon}d"]
            
            # Load models
            ensemble = ModelEnsemble(horizon=horizon, symbol=sym)
            ensemble.load_all()
            regime_engine = RegimeEngine()
            regime_engine.load_all()
            
            # Predict regimes and directions
            regimes = regime_engine.classify_history(raw_feat.loc[df_test.index])
            df_test["regime_label"] = regimes["regime_label"]
            
            pnl_series = []
            
            for date, row in df_test.iterrows():
                if pd.isna(y_ret.loc[date]):
                    pnl_series.append(0)
                    continue
                    
                feats_dict = row.drop(["regime_label"]).to_dict()
                pred = ensemble.predict(feats_dict, row["regime_label"])
                prob = pred.get("ensemble_prob", 0.5)
                
                # Simple logic akin to signal_generator
                # Assuming base threshold 0.6
                if prob > 0.6:
                    pos = 1
                elif prob < 0.4:
                    pos = -1
                else:
                    pos = 0
                    
                # Forward return for next horizon
                ret = y_ret.loc[date]
                pnl = pos * ret
                pnl_series.append(pnl)
                
            pnl_series = pd.Series(pnl_series)
            total_pnl = pnl_series.sum() * 100 # % return
            win_rate = (pnl_series[pnl_series != 0] > 0).mean() * 100 if sum(pnl_series != 0) > 0 else 0
            
            daily_returns = pnl_series / horizon # approximate daily
            sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() > 0 else 0
            
            results.append({
                "Symbol": sym,
                "WinRate": round(win_rate, 2),
                "Sharpe": round(sharpe, 2),
                "TotalPnL_Pct": round(total_pnl, 2),
                "Trades": sum(pnl_series != 0)
            })
            
        except Exception as e:
            print(f"Error processing {sym}: {e}")
            
    res_df = pd.DataFrame(results)
    print("\n--- BACKTEST RESULTS ---")
    print(res_df.to_string())
    
    # Save to JSON
    out_file = os.path.join(os.path.dirname(__file__), "backtest_results.json")
    res_df.to_json(out_file, orient="records")
    print(f"\nResults saved to {out_file}")

if __name__ == "__main__":
    run_backtest()
