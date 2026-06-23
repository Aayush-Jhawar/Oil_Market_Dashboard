import logging
import pandas as pd
from typing import Dict, List

from prediction.validation.walk_forward import run_walk_forward_validation
from services.backtest.engine import BacktestEngine
from prediction.features.feature_store_service import FeatureStoreService

logger = logging.getLogger(__name__)

def run_multi_asset_backtest(
    symbols: List[str] = ["WTI", "Brent"],
    initial_capital: float = 1_000_000.0,
    horizon_days: int = 5,
    expanding: bool = True
) -> Dict:
    """
    Run a multi-asset walk-forward backtest.
    """
    predictions_dict = {}
    price_dict = {}
    
    fss = FeatureStoreService()
    
    # Run single-asset walk forward for each symbol to get predictions
    for sym in symbols:
        logger.info(f"Generating walk-forward predictions for {sym}...")
        try:
            # 1. Fetch historical price data
            from services.price_fetcher import PriceFetcher
            from prediction.features.feature_matrix import build_historical_feature_matrix
            
            hist_data = PriceFetcher.fetch_historical(sym, "10y")
            if not hist_data:
                logger.warning(f"No historical data found for {sym}. Skipping.")
                continue
                
            prices_df = pd.DataFrame(hist_data)
            if "timestamp" in prices_df.columns:
                prices_df["date"] = pd.to_datetime(prices_df["timestamp"])
                prices_df.set_index("date", inplace=True)
            elif "date" in prices_df.columns:
                prices_df["date"] = pd.to_datetime(prices_df["date"])
                prices_df.set_index("date", inplace=True)
                
            # 2. Build feature matrix
            feature_matrix = build_historical_feature_matrix(prices_df)
            
            # 3. Run walk-forward validation
            preds = run_walk_forward_validation(feature_matrix, prices_df, horizon_days=horizon_days, expanding=expanding)
            
            if "error" in preds:
                logger.warning(f"Walk-forward failed for {sym}: {preds['error']}")
                continue
                
            predictions_dict[sym] = preds["predictions"]
            price_dict[sym] = prices_df
            
        except Exception as e:
            logger.error(f"Error processing {sym}: {e}")
            
    if not predictions_dict:
        return {"error": "No predictions generated for any asset"}
        
    engine = BacktestEngine(initial_capital=initial_capital)
    results = engine.run(predictions_dict, price_dict)
    
    return results
