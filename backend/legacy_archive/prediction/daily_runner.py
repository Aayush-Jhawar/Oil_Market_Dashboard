"""
Daily Prediction Runner
========================
Execution script that runs daily. It:
1. Pulls the latest live data from all sources
2. Builds the point-in-time feature vector
3. Classifies current regime
4. Generates predictions using the ensemble models
5. Creates trade recommendations
6. Saves everything to the feature store
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Dict, Optional

import numpy as np

# Import fetchers from existing backend services
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prediction.features.feature_store_service import FeatureStoreService
from prediction.regime.regime_engine import RegimeEngine
from prediction.models.ensemble import ModelEnsemble
from prediction.trading.signal_generator import generate_trade_signal, generate_spread_signal, _no_trade
from prediction.explain.shap_explainer import explain_prediction
from prediction.feature_store import (
    Base as PredictionBase,
    save_feature_snapshot,
    save_regime_record,
    save_prediction,
    save_trade_recommendation,
)

from services.price_fetcher import PriceFetcher
from services.forward_curve import fetch_forward_curve
from services.macro_fetcher import MacroFetcher, CFTCFetcher
from services.eia_fetcher import EIAFetcher

from database import engine
PredictionBase.metadata.create_all(bind=engine)

logger = logging.getLogger(__name__)


def run_daily_pipeline(symbols: list = None, horizon_days: int = 5) -> Optional[Dict]:
    """
    Run the daily prediction pipeline for multiple symbols.
    """
    if symbols is None:
        symbols = [
            "WTI", "Brent", "RBOB", "HO", "GO", "NG", 
            "WTI_CAL_SPREAD", "BRENT_CAL_SPREAD", 
            "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY",
            "3-2-1CRACK", "GASCRACK", "DIESELCRACK", "WTI-Brent"
        ]
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"Running daily pipeline for {symbols} on {today_str}")

    results = {}
    
    # 1. Fetch Global Data (Curve, Macro, Fundamentals) once to share
    logger.info("Fetching global market data (Curve, Macro, Fundamentals)...")
    try:
        curve_points, _ = fetch_forward_curve()
        curve_prices = {p["month"]: p["price"] for p in curve_points}
        macro_data = MacroFetcher.fetch_all_macro()
        
        eia_data = None
        cftc_raw = None
        if os.getenv("EIA_API_KEY"):
            try:
                eia_data = EIAFetcher.fetch_all_eia_data()
            except Exception:
                pass
        try:
            cftc_raw = CFTCFetcher.fetch_latest()
        except Exception:
            cftc_raw = None
    except Exception as e:
        logger.error(f"Failed to fetch global market data: {e}")
        return None

    # Load models once
    feature_store = FeatureStoreService()
    if not feature_store.load():
        logger.warning("FeatureTransformer not found. Run training pipeline first to fit scalers.")
        
    regime_engine = RegimeEngine()
    regime_engine.load_all()

    # Process each symbol
    for symbol in symbols:
        try:
            base_symbol = symbol
            if "BRENT" in symbol.upper(): base_symbol = "Brent"
            elif "RBOB" in symbol.upper(): base_symbol = "RBOB"
            elif "HO" in symbol.upper(): base_symbol = "HO"
            elif "GO" in symbol.upper(): base_symbol = "GO"
            elif "WTI" in symbol.upper() or "CRACK" in symbol.upper(): base_symbol = "WTI"
            
            ensemble = ModelEnsemble(horizon=horizon_days, symbol=base_symbol)
            ensemble.load_all()
            
            logger.info(f"--- Processing Daily Pipeline for {symbol} ---")
            
            # Fetch historical prices for this symbol
            hist = PriceFetcher.fetch_historical(symbol, "3mo") or []
            if not hist:
                logger.warning(f"No history for {symbol}, skipping.")
                continue
                
            closes = [float(h["close"]) for h in hist]
            highs = [float(h["high"]) for h in hist]
            lows = [float(h["low"]) for h in hist]
            current_price = closes[-1] if closes else 0.0
            
            cftc_sym_data = {"WTI": cftc_raw.get("WTI")} if cftc_raw and "WTI" in cftc_raw else None
            # Only WTI is in the CFTC map for now
            
            # 2. Build feature vector
            logger.info(f"[{symbol}] Building feature vector...")
            raw_features, features = feature_store.build_and_transform_daily(
                date_str=today_str,
                curve_prices=curve_prices,
                closes=closes,
                highs=highs,
                lows=lows,
                eia_data=eia_data,
                cftc_data=cftc_sym_data,
                macro_data=macro_data,
            )

            # 3. Classify Regime
            logger.info(f"[{symbol}] Classifying regime...")
            regime_state = regime_engine.classify(raw_features)

            # 4. Generate Predictions
            logger.info(f"[{symbol}] Generating ensemble prediction...")
            if not ensemble.is_fitted:
                forecast = {
                    "ensemble_prob": 0.5,
                    "prediction_label": "NEUTRAL",
                    "confidence": 0.0,
                    "expected_return": 0.0,
                    "horizon_days": horizon_days,
                    "components": {}
                }
            else:
                forecast = ensemble.predict(
                    features=features,
                    regime_label=regime_state.regime_label,
                    regime_age_days=regime_state.regime_age_days
                )
                
            forecast["target"] = "direction"
            forecast["model_version"] = "ensemble_v1"

            # 5. Explain Prediction
            explanation = {}
            if ensemble.is_fitted:
                explanation = explain_prediction(
                    ensemble, features, regime_state.regime_label
                )

            # 6. Generate Trade Signal
            logger.info(f"[{symbol}] Generating Trade Signal...")
            from prediction.features.technical_features import _realized_vol
            vol = _realized_vol(np.array(closes), 20) if len(closes) > 20 else 25.0
            
            is_spread = "SPREAD" in symbol or "FLY" in symbol or "CRACK" in symbol or "-" in symbol
            
            if is_spread:
                trade = generate_spread_signal(
                    spread_forecast=forecast,
                    current_spread=current_price,
                    regime_state=regime_state.to_dict(),
                    symbol=symbol,
                    hist_spreads=closes,
                    is_intraday=False,
                    atr=raw_features.get("atr_14", 0.0) if raw_features is not None else 0.0,
                    realized_vol=raw_features.get("realized_vol_30d", 0.0) if raw_features is not None else 0.0
                )
                if trade is None:
                    trade = _no_trade("No spread opportunity", forecast.get("ensemble_prob", 0.5), forecast.get("confidence", 0.0))
                    trade["trade_type"] = "SPREAD"
                else:
                    trade["trade_score"] = min(100.0, (trade.get("confidence", 0) * 100) + (abs(trade.get("expected_change", 0)) * 10))
                    trade["explanation"] = {"action": trade["direction"], "reason": trade["rationale"]}
            else:
                trade = generate_trade_signal(
                    symbol=symbol,
                    forecast=forecast,
                    regime_state=regime_state.to_dict(),
                    current_price=current_price,
                    features=raw_features,
                )
            
            if "error" not in explanation and explanation:
                trade["explanation"]["shap_bullish"] = explanation.get("bullish_factors", [])
                trade["explanation"]["shap_bearish"] = explanation.get("bearish_factors", [])

            # 7. Save to Database
            logger.info(f"[{symbol}] Saving pipeline results to database...")
            try:
                save_feature_snapshot(
                    symbol=symbol,
                    dt=today_str,
                    features=features,
                    regime_label=regime_state.regime_label,
                    regime_severity=regime_state.severity
                )
                
                print(f"[{symbol}] saving regime_data:", regime_state.to_dict())
                save_regime_record(
                    symbol=symbol,
                    dt=today_str,
                    regime_data=regime_state.to_dict()
                )
                
                save_prediction(
                    symbol=symbol,
                    dt=today_str,
                    pred_data=forecast
                )
                
                save_trade_recommendation(
                    symbol=symbol,
                    dt=today_str,
                    trade_data=trade
                )
            except Exception as e:
                logger.error(f"[{symbol}] Failed to save to database: {e}")

            results[symbol] = {
                "trade_signal": trade,
                "regime_state": regime_state.to_dict(),
                "forecast": forecast
            }
            logger.info(f"[{symbol}] Pipeline complete. Trade: {trade['direction']}")
            
        except Exception as e:
            logger.error(f"[{symbol}] Failed processing daily pipeline: {e}")

    return results

if __name__ == "__main__":
    import json
    res = run_daily_pipeline()
    print(json.dumps({k: v["trade_signal"]["direction"] for k,v in res.items()} if res else {}, indent=2))
