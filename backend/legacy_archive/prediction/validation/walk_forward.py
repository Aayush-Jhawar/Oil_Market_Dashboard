"""
Walk-Forward Validation Framework
===================================
Evaluates the prediction engine through rigorous out-of-sample backtesting
using an expanding or rolling window. Prevents data leakage by ensuring
features, regime classifications, and models at time t only use data
available prior to t.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from prediction.config import VALIDATION_CONFIG
from prediction.features.feature_matrix import add_target_variables
from prediction.regime.regime_engine import RegimeEngine
from prediction.models.ensemble import ModelEnsemble
from services.backtest.engine import BacktestEngine

logger = logging.getLogger(__name__)


def run_walk_forward_validation(
    feature_matrix: pd.DataFrame,
    price_history: pd.DataFrame,
    horizon_days: int = 5,
    expanding: bool = True,
    symbol: str = "WTI",
) -> Dict:
    """
    Run walk-forward validation for the ensemble model or spread model.

    Args:
        raw_feature_matrix: DataFrame containing unscaled features.
        feature_matrix: DataFrame containing transformed features.
        price_history: DataFrame containing close prices for computing targets.
        horizon_days: Forecast horizon.
        expanding: If True, training window expands; if False, rolling window.
        symbol: The asset or spread symbol.

    Returns:
        Dict with evaluation metrics and out-of-sample predictions DataFrame.
    """
    logger.info(f"Starting walk-forward validation (horizon={horizon_days}d)")

    if len(feature_matrix) < VALIDATION_CONFIG["min_train_days"] + VALIDATION_CONFIG["test_window_days"]:
        return {"error": "Insufficient data for walk-forward validation"}

    # Add targets
    logger.info("Adding target variables for training...")
    is_spread = "SPREAD" in symbol or "FLY" in symbol or "CRACK" in symbol
    df = add_target_variables(feature_matrix, price_history, {f"{horizon_days}d": horizon_days}, is_spread=is_spread)
    target_dir_col = f"target_direction_{horizon_days}d"
    target_ret_col = f"target_return_{horizon_days}d"

    # Drop rows without target (e.g., the last `horizon_days` rows)
    df = df.dropna(subset=[target_dir_col, target_ret_col])
    
    # feature_matrix is already raw (unscaled) because scaling was moved to the walk-forward loop
    raw_feature_matrix = feature_matrix
    
    # Also need corresponding raw data aligned with df
    raw_df = raw_feature_matrix.loc[df.index]

    # Hold out final reserve for true OOS (not part of walk-forward)
    reserve = VALIDATION_CONFIG["oos_reserve_days"]
    wf_df = df.iloc[:-reserve] if reserve > 0 else df
    wf_raw_df = raw_df.iloc[:-reserve] if reserve > 0 else raw_df

    total_len = len(wf_df)
    train_len = int(total_len * 0.6)
    val_len = int(total_len * 0.2)
    test_len = total_len - train_len - val_len
    
    logger.info(f"Forward Testing 60/20/20 Split: Train={train_len}, Val={val_len}, Test={test_len}")

    train_data_unscaled = wf_raw_df.iloc[:train_len]
    val_data_unscaled = wf_raw_df.iloc[train_len: train_len + val_len]
    test_data_unscaled = wf_raw_df.iloc[train_len + val_len:]
    
    # Feature Transformations
    from prediction.features.transformations import FeatureTransformer
    transformer = FeatureTransformer(use_pca=False)
    
    X_train_raw = train_data_unscaled.drop(columns=[target_dir_col, target_ret_col], errors='ignore')
    X_val_raw = val_data_unscaled.drop(columns=[target_dir_col, target_ret_col], errors='ignore')
    X_test_raw = test_data_unscaled.drop(columns=[target_dir_col, target_ret_col], errors='ignore')
    
    transformer.fit(X_train_raw)
    X_train_transformed = transformer.transform(X_train_raw)
    X_val_transformed = transformer.transform(X_val_raw)
    X_test_transformed = transformer.transform(X_test_raw)
    
    train_targets = wf_df.iloc[:train_len]
    val_targets = wf_df.iloc[train_len: train_len + val_len]
    test_targets = wf_df.iloc[train_len + val_len:]

    train_data = pd.concat([X_train_transformed, train_targets[[target_dir_col, target_ret_col]]], axis=1)
    val_data = pd.concat([X_val_transformed, val_targets[[target_dir_col, target_ret_col]]], axis=1)
    test_data = pd.concat([X_test_transformed, test_targets[[target_dir_col, target_ret_col]]], axis=1)

    # 1. Fit Regime Engine (5 Regimes)
    logger.debug("Fitting 5-Regime engine...")
    regime_engine = RegimeEngine()
    regime_engine.fit(train_data.drop(columns=[target_dir_col, target_ret_col]), train_data[target_ret_col])
    
    train_regimes = regime_engine.classify_history(train_data_unscaled)
    test_regimes = regime_engine.classify_history(test_data_unscaled)

    train_data = train_data.copy()
    test_data = test_data.copy()
    train_data["regime_label"] = train_regimes["regime_label"]
    test_data["regime_label"] = test_regimes["regime_label"]
    test_data["regime_age_days"] = test_regimes["regime_age_days"]

    train_data = train_data.dropna(subset=["regime_label"])

    # 2. Fit Models with Custom Sample Weights
    logger.debug("Fitting models...")
    is_spread = "SPREAD" in symbol or "FLY" in symbol or "CRACK" in symbol or "-" in symbol
    
    X_train = train_data.drop(columns=[target_dir_col, target_ret_col, "regime_label"])
    y_dir = train_data[target_dir_col]
    y_ret = train_data[target_ret_col]

    import numpy as np
    weights = np.ones(len(X_train))
    if is_spread:
        if "FLY" in symbol:
            weights = np.linspace(0.5, 1.5, len(X_train))
        elif "CRACK" in symbol:
            weights = np.ones(len(X_train))
        else:
            weights = np.linspace(0.7, 1.3, len(X_train))
    else:
        weights = np.linspace(0.9, 1.1, len(X_train))

    if is_spread:
        from prediction.models.spread_model import SpreadModel
        model = SpreadModel(horizon=horizon_days)
        model.fit(X_train, y_ret, sample_weight=weights)
    else:
        model = ModelEnsemble(horizon=horizon_days)
        model.fit(X_train, y_dir, y_ret, train_data["regime_label"], sample_weight=weights)

    # 3. Predict on Test Set
    logger.debug("Generating out-of-sample predictions on 20% test set...")
    all_predictions = []
    for dt, row in test_data.iterrows():
        features = row.drop(labels=[target_dir_col, target_ret_col, "regime_label", "regime_age_days"]).to_dict()
        reg_label = row["regime_label"]
        reg_age = row["regime_age_days"]
        
        if is_spread:
            pred = model.predict_single(features)
            pred["ensemble_prob"] = 0.5
        else:
            pred = model.predict(features, regime_label=reg_label, regime_age_days=reg_age)  # type: ignore
        
        actual_dir = row[target_dir_col]
        actual_ret = row[target_ret_col]

        all_predictions.append({
            "date": dt,
            "regime_label": reg_label,
            "ensemble_prob": pred.get("ensemble_prob", 0.5),
            "prediction_label": pred["prediction_label"],
            "confidence": pred["confidence"],
            "expected_return": pred.get("expected_return", pred.get("prediction_value", 0.0)),
            "actual_direction": actual_dir,
            "actual_return": actual_ret,
            "is_correct": (pred["prediction_label"] in ["UP", "WIDEN"] and actual_dir == 1) or \
                          (pred["prediction_label"] in ["DOWN", "NARROW"] and actual_dir == 0)
        })

    # Evaluate results
    if not all_predictions:
        return {"error": "No predictions generated"}

    preds_df = pd.DataFrame(all_predictions).set_index("date")
    
    # Metrics
    total = len(preds_df)
    traded = preds_df[preds_df["prediction_label"] != "NEUTRAL"]
    high_conf = preds_df[preds_df["confidence"] >= 0.6]
    
    metrics = {
        "total_days": total,
        "traded_days": len(traded),
        "trade_frequency": round(len(traded) / total, 4),
        "overall_accuracy": round(traded["is_correct"].mean(), 4) if not traded.empty else 0.0,
        "high_conf_accuracy": round(high_conf["is_correct"].mean(), 4) if not high_conf.empty else 0.0,
    }

    # Per-regime accuracy
    regime_metrics = {}
    for regime, group in traded.groupby("regime_label"):
        regime_metrics[regime] = {
            "count": len(group),
            "accuracy": round(group["is_correct"].mean(), 4)
        }
    metrics["regime_breakdown"] = regime_metrics

    logger.info(f"Walk-forward validation complete. Accuracy: {metrics['overall_accuracy']:.2%}")
    
    # Run historical simulation on OOS predictions
    logger.info("Piping out-of-sample predictions to BacktestEngine...")
    engine = BacktestEngine(
        initial_capital=1_000_000.0,
        transaction_cost_per_trade=2.0,
        slippage_per_trade=10.0,
        contract_multipliers={symbol: 1000.0} # default multiplier
    )
    backtest_results = engine.run({symbol: preds_df}, {symbol: price_history})
    
    return {
        "metrics": metrics, 
        "predictions": preds_df,
        "backtest": backtest_results
    }
