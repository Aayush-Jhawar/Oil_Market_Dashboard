import os
import sys
import json
import logging
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.price_fetcher import PriceFetcher
from services.forward_curve import fetch_forward_curve
from services.macro_fetcher import MacroFetcher
from prediction.features.feature_store_service import FeatureStoreService
from prediction.validation.walk_forward import run_walk_forward_validation

logging.basicConfig(level=logging.ERROR)

def run_for_symbol(symbol: str, feature_store: FeatureStoreService, macro_data: dict, curve_prices: dict):
    print(f"Running accuracy test for {symbol}...")
    try:
        hist = PriceFetcher.fetch_historical(symbol, period="3y")
        if not hist or len(hist) < 200:
            return {"error": "Not enough historical data"}
            
        closes = [float(h["close"]) for h in hist]
        highs = [float(h["high"]) for h in hist]
        lows = [float(h["low"]) for h in hist]
        dates = [h["timestamp"] for h in hist]
        
        # Build features for each day iteratively or in bulk.
        # FeatureStore expects to be built daily, so we can mock the daily build loop
        # or just use build_and_transform_daily which does it for one day.
        # Wait, build_and_transform_daily is slow for 3 years.
        # The correct way to build history is via feature_matrix.py
        
        from prediction.features.feature_matrix import build_historical_feature_matrix
        df_hist = pd.DataFrame(hist)
        df_hist['date'] = pd.to_datetime(df_hist['timestamp'])
        df_hist = df_hist.set_index('date')
        
        is_spread = "SPREAD" in symbol or "FLY" in symbol or "CRACK" in symbol or "-" in symbol
        
        base_asset = symbol.split("_")[0]
        if base_asset.upper() == "BRENT": base_asset = "Brent"
        elif "CRACK" in symbol or base_asset == "WTI": base_asset = "WTI"
        elif "RBOB" in symbol: base_asset = "RBOB"
        elif "HO" in symbol: base_asset = "HO"
        
        curve_history = PriceFetcher._query_historical_term_structure(base_asset, 2000)
        if curve_history is not None:
            curve_history = curve_history.rename(columns={f"m{i}": f"M{i}" for i in range(1, 13)})
        
        raw_features = build_historical_feature_matrix(
            price_history=df_hist,
            curve_history=curve_history,
            macro_history=None,
            eia_history=None,
            cftc_history=None,
        )
        
        # Drop NaN features
        raw_features = raw_features.dropna(axis=1, thresh=len(raw_features) * 0.8)
        
        results = run_walk_forward_validation(
            feature_matrix=raw_features,
            price_history=df_hist,
            horizon_days=5,
            symbol=symbol
        )
        
        if "error" in results:
            return results
            
        metrics = results["metrics"]
        return metrics
        
    except Exception as e:
        return {"error": str(e)}

def main():
    symbols = ["WTI", "Brent", "RBOB", "HO", "WTI_CAL_SPREAD", "BRENT_CAL_SPREAD", "WTI_FLY", "3-2-1CRACK", "WTI-Brent"]
    
    fs = FeatureStoreService()
    macro = MacroFetcher.fetch_all_macro()
    curve_pts, _ = fetch_forward_curve()
    curve_prices = {p["month"]: p["price"] for p in curve_pts} if curve_pts else {}
    
    report = {}
    for sym in symbols:
        res = run_for_symbol(sym, fs, macro, curve_prices)
        report[sym] = res
        
    print("\n--- JSON_REPORT_START ---")
    print(json.dumps(report, indent=2))
    print("--- JSON_REPORT_END ---")

if __name__ == "__main__":
    main()
