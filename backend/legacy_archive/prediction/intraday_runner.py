"""
Intraday Inference Runner
==========================
Designed to run every 5 minutes during market hours.
Avoids fetching heavy macro/CFTC data that doesn't change intraday.
Updates OHLCV, moving averages, technical indicators, and generates an updated signal.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from services.price_fetcher import PriceFetcher
from prediction.feature_store import get_feature_snapshots, get_recent_trade_recommendations
from prediction.features.feature_store_service import FeatureStoreService
from prediction.regime.regime_engine import RegimeEngine
from prediction.models.ensemble import ModelEnsemble
from prediction.trading.signal_generator import generate_trade_signal
from services.forward_curve import fetch_forward_curve
from sentiment import warm_finbert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

# Global cache to prevent reloading from disk every 5 minutes
_CACHE = {
    "feature_store": None,
    "regime_engine": None,
    "ensemble_models": {},
    "pairs_engine": None
}

KALMAN_PAIRS = {
    "WTI-Brent": ("WTI", "Brent"),
    "RBOB-HO": ("RBOB", "HO"),
    "GASCRACK": ("WTI", "RBOB"),
    "DIESELCRACK": ("WTI", "HO"),
    "DUB-WTI": ("DUBAICRUDE", "WTI")
}

def load_models():
    """Load models from disk if not already in memory."""
    if _CACHE["feature_store"] is None:
        fs = FeatureStoreService()
        if fs.load():
            _CACHE["feature_store"] = fs
        else:
            logger.error("Failed to load FeatureStoreService.")

    if _CACHE["regime_engine"] is None:
        re = RegimeEngine()
        if re.load_all():
            _CACHE["regime_engine"] = re
        else:
            logger.error("Failed to load RegimeEngine.")

    if _CACHE.get("pairs_engine") is None:
        from prediction.trading.pairs_trader import PairsTradingEngine
        _CACHE["pairs_engine"] = PairsTradingEngine()

    # Ensemble models are now loaded on-demand in the loop, per base_symbol
    pass


def run_intraday_pipeline(symbols: list = None):
    """
    Execute the intraday prediction pipeline for multiple symbols.
    """
    if symbols is None:
        symbols = [
            "WTI", "Brent", "RBOB", "HO", "GO", "NG", 
            "3-2-1CRACK", "GASCRACK", "DIESELCRACK", 
            "WTI_DFLY", "BRENT_DFLY", "RBOB_DFLY", "HO_DFLY",
            "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY",
            "WTI_CAL_SPREAD", "BRENT_CAL_SPREAD", "WTI-Brent", "DUB-WTI"
        ]
        # Dynamically add all equidistant flies up to M12
        for prefix in ["WTI", "BRENT", "RBOB", "HO"]:
            for distance in range(1, 6):
                for m1 in range(1, 13):
                    m2 = m1 + distance
                    m3 = m1 + 2 * distance
                    if m3 <= 12:
                        symbols.append(f"{prefix}_FLY_{m1}_{m2}_{m3}")
            for distance in range(1, 4):
                for m1 in range(1, 13):
                    m2 = m1 + distance
                    m3 = m1 + 2 * distance
                    m4 = m1 + 3 * distance
                    if m4 <= 12:
                        symbols.append(f"{prefix}_DFLY_{m1}_{m2}_{m3}_{m4}")
        
    logger.info(f"--- Starting INTRADAY Pipeline for {symbols} ---")
    
    # Pre-fetch models to avoid reloading
    warm_finbert()
    load_models()
    feature_store = _CACHE["feature_store"]
    regime_engine = _CACHE["regime_engine"]
    pairs_engine = _CACHE["pairs_engine"]

    if not all([feature_store, regime_engine]):
        logger.error("Missing core models in cache. Aborting.")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = {}

    for symbol in symbols:
        try:
            logger.info(f"Processing {symbol}...")
            # 1. Fetch live 5-minute data
            intraday_data = PriceFetcher.fetch_intraday(symbol, limit=200)
            if not intraday_data:
                logger.warning(f"No intraday data found for {symbol}. Skipping.")
                continue

            hist_data = PriceFetcher.fetch_historical(symbol, period="1y")
            if not hist_data:
                logger.warning(f"No historical context found for {symbol}. Skipping.")
                continue
                
            closes = [day["close"] for day in hist_data]
            highs = [day["high"] for day in hist_data]
            lows = [day["low"] for day in hist_data]
            
            latest_intraday = intraday_data[-1]
            closes[-1] = latest_intraday["close"]
            highs[-1] = max(highs[-1], latest_intraday["high"])
            lows[-1] = min(lows[-1], latest_intraday["low"])

            # Fetch curve for the specific symbol
            base_symbol = symbol
            if "BRENT" in symbol.upper(): base_symbol = "Brent"
            elif "RBOB" in symbol.upper(): base_symbol = "RBOB"
            elif "HO" in symbol.upper(): base_symbol = "HO"
            elif "GO" in symbol.upper(): base_symbol = "GO"
            elif "WTI" in symbol.upper() or "CRACK" in symbol.upper(): base_symbol = "WTI"
            
            # Load ensemble model on-demand
            if base_symbol not in _CACHE["ensemble_models"]:
                em = ModelEnsemble(horizon=5, symbol=base_symbol)
                loaded = em.load_all()
                if not loaded:
                    logger.warning(f"No trained model found for {base_symbol} (horizon=5). Falling back to WTI model.")
                    em_fallback = ModelEnsemble(horizon=5, symbol="WTI")
                    em_fallback.load_all()
                    _CACHE["ensemble_models"][base_symbol] = em_fallback
                else:
                    _CACHE["ensemble_models"][base_symbol] = em
            ensemble = _CACHE["ensemble_models"][base_symbol]
            
            logger.info(f"Fetching {base_symbol} curve for regime proxy...")
            
            from config import USE_YFINANCE
            if base_symbol == "Brent":
                # Priority 2d fix: Always use local dataset for M1-M12 to fix regime mapping,
                # then override M1 with live yfinance data if available
                from services.data_loader import get_intraday_curve
                curve_prices = get_intraday_curve(base_symbol)
                
                if USE_YFINANCE:
                    yf_curve, _ = fetch_forward_curve(base_symbol)
                    if yf_curve and len(yf_curve) > 0:
                        curve_prices["M1"] = yf_curve[0]["price"]
                        
                # Degenerate curve check
                if curve_prices and len(curve_prices) > 1:
                    m2_to_m12 = [curve_prices.get(f"M{i}") for i in range(2, 13)]
                    if len(set(x for x in m2_to_m12 if x is not None)) <= 1:
                        logger.warning(f"Degenerate forward curve detected for {base_symbol}. All back months have the same price.")
            else:
                if USE_YFINANCE:
                    curve_points, _ = fetch_forward_curve(base_symbol)
                    curve_prices = {p["month"]: p["price"] for p in curve_points} if curve_points else {}
                else:
                    from services.data_loader import get_intraday_curve
                    curve_prices = get_intraday_curve(base_symbol)
                    
                # Fallback if empty
                if not curve_prices and USE_YFINANCE:
                    from services.data_loader import get_intraday_curve
                    curve_prices = get_intraday_curve(base_symbol)
                    logger.info(f"Fell back to local dataset curve for {base_symbol}")

            # 2. Build Features
            raw_features, features = feature_store.build_and_transform_daily(
                date_str=now_str,
                curve_prices=curve_prices,
                closes=closes,
                highs=highs,
                lows=lows,
            )

            # Fetch live news sentiment and inject into features
            try:
                from services.news_fetcher import NewsFetcher
                news = NewsFetcher.fetch_all_news()
                # (Removed hardcoded bearish news event)
                sentiment = NewsFetcher.calculate_sentiment_trend(news)
                if features is not None:
                    features["news_sentiment"] = sentiment
                if raw_features is not None:
                    raw_features["news_sentiment"] = sentiment
                logger.info(f"Injected news sentiment: {sentiment}")
            except Exception as e:
                logger.error(f"Error fetching intraday news sentiment: {e}")

            # 3. Classify Regime (using RAW dollar spreads)
            regime_state = regime_engine.classify(raw_features)

            # 3.5 Apply Adaptive Multi-Factor Weights
            if features is not None:
                features = feature_store.apply_adaptive_weights(features, regime_state.regime_label)

            # 4. Generate Predictions
            pred_result = ensemble.predict(
                features=features,
                regime_label=regime_state.regime_label,
                regime_age_days=regime_state.regime_age_days
            )

            # 5. Generate Trade Signal
            is_spread = "SPREAD" in symbol or "FLY" in symbol or "CRACK" in symbol or "-" in symbol
            try:
                recent_trades = get_recent_trade_recommendations(symbol, n_days=20)
            except Exception as e:
                logger.error(f"Error fetching recent trades: {e}")
                recent_trades = []
            
            if symbol in KALMAN_PAIRS:
                asset_x, asset_y = KALMAN_PAIRS[symbol]
                intraday_x = PriceFetcher.fetch_intraday(asset_x, limit=30)
                intraday_y = PriceFetcher.fetch_intraday(asset_y, limit=30)
                if intraday_x and intraday_y and len(intraday_x) == len(intraday_y):
                    pair_res = None
                    for tick_x, tick_y in zip(intraday_x, intraday_y):
                        px = tick_x["close"]
                        py = tick_y["close"]
                        pair_res = pairs_engine.process_pair(symbol, px, py)
                        
                    # Calculate conviction based on z-score
                    z_score = abs(pair_res.get("z_score", 0.0))
                    conviction = "LOW"
                    if z_score > 3.0: conviction = "HIGH"
                    elif z_score > 2.0: conviction = "MEDIUM"
                    
                    # Also map signal to standard frontend expected format if NO_TRADE
                    frontend_signal = pair_res["signal"]
                    if frontend_signal.startswith("HOLD") or frontend_signal.startswith("EXIT"):
                        frontend_signal = "NO_TRADE"
                    elif frontend_signal == "LONG_SPREAD": frontend_signal = "LONG"
                    elif frontend_signal == "SHORT_SPREAD": frontend_signal = "SHORT"
                    
                    current_spread = pair_res.get("spread", py - pair_res.get("beta", 1.0) * px)
                    # If z_score is 1.24, then expected change is to revert to 0. So expected_change = -current_spread (roughly, if mean=0). 
                    # To be safe, we just say expected_change is positive if LONG, negative if SHORT
                    expected_dir = 1 if frontend_signal == "LONG" else -1
                    est_std = abs(current_spread / pair_res.get("z_score", 1.0)) if pair_res.get("z_score", 0) != 0 else 0.5
                    
                    trade_signal = {
                        "direction": frontend_signal,
                        "conviction": conviction,
                        "confidence": 1.0,
                        "trade_score": pair_res.get("z_score", 0.0),
                        "trade_type": "SPREAD",
                        "current_spread": current_spread,
                        "target_spread": current_spread + (est_std * 1.5 * expected_dir) if frontend_signal != "NO_TRADE" else 0.0,
                        "stop_spread": current_spread - (est_std * 0.5 * expected_dir) if frontend_signal != "NO_TRADE" else 0.0,
                        "expected_change": (est_std * 1.5 * expected_dir) if frontend_signal != "NO_TRADE" else 0.0,
                        "explanation": {"rationale": pair_res.get("rationale", ""), "beta": pair_res.get("beta", 1.0)}
                    }
                else:
                    from prediction.trading.signal_generator import _no_trade
                    trade_signal = _no_trade("Missing or mismatched data for Kalman pair", 0.5, 0.0, 0.0)
            elif is_spread:
                from prediction.trading.signal_generator import generate_spread_signal
                # Provide required kwargs for generate_spread_signal
                trade_signal = generate_spread_signal(
                    spread_forecast=pred_result,
                    current_spread=latest_intraday["close"],
                    regime_state=regime_state.to_dict(),
                    symbol=symbol,
                    hist_spreads=closes,
                    is_intraday=True,
                    atr=features.get("atr_14", 0.0) if features is not None else 0.0,
                    realized_vol=features.get("realized_vol_30d", 0.0) if features is not None else 0.0
                )
                if not trade_signal:
                    from prediction.trading.signal_generator import _no_trade
                    trade_signal = _no_trade("No active spread signal", pred_result.get("ensemble_prob", 0.5), pred_result.get("confidence", 0.0), 0.0)
            else:
                trade_signal = generate_trade_signal(
                    symbol=symbol,
                    current_price=latest_intraday["close"],
                    forecast=pred_result,
                    regime_state=regime_state.to_dict(),
                    features=raw_features,
                    recent_trades=recent_trades,
                    is_intraday=True
                )
            
            trade_signal["updated_at"] = now_str
            trade_signal["is_intraday"] = True

            logger.info(f"[{symbol}] Intraday Signal: {trade_signal.get('direction')} (Score: {trade_signal.get('trade_score', 'N/A')})")

            # Save to Database so that REST endpoints (like /api/prediction/forecast) see the updated intraday signal
            try:
                from prediction.feature_store import save_trade_recommendation, save_prediction, save_regime_record
                save_trade_recommendation(symbol, now_str, trade_signal)
                save_prediction(symbol, now_str, pred_result)
                save_regime_record(symbol, now_str, regime_state.to_dict())
            except Exception as db_err:
                logger.error(f"[{symbol}] Failed to save intraday signal to DB: {db_err}")

            results[symbol] = {
                "trade_signal": trade_signal,
                "regime_state": regime_state.to_dict(),
                "raw_features": raw_features
            }
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    return results

if __name__ == "__main__":
    import json
    res = run_intraday_pipeline()
    print(json.dumps({k: v["trade_signal"]["direction"] for k,v in res.items()}, indent=2))
