"""
Prediction Engine Configuration
================================
Central configuration for regime thresholds, model hyperparameters,
feature definitions, and operational settings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

# ---------------------------------------------------------------------------
# Regime thresholds (calibrated to ~2010–2025 WTI data)
# ---------------------------------------------------------------------------
REGIME_THRESHOLDS = {
    "extreme_backwardation": {
        "m1_m12_spread_threshold": -5.0,   # $/bbl — deep front premium
        "m1_m2_spread_threshold":  -0.80,  # $/bbl — strong front premium
    },
    "backwardation": {
        "m1_m12_spread_threshold": -2.0,   # $/bbl — moderate front premium
        "m1_m2_spread_threshold":  -0.30,  # $/bbl — front month premium
    },
    "contango": {
        "m1_m12_spread_threshold":  2.0,
        "m1_m2_spread_threshold":   0.30,
    },
    "extreme_contango": {
        "m1_m12_spread_threshold":  5.0,   # $/bbl — deep front discount
        "m1_m2_spread_threshold":   0.80,  # $/bbl — strong front discount
    },
    "severity_normalizer": 10.0,  # spread at which severity = 1.0
}

# ---------------------------------------------------------------------------
# HMM configuration
# ---------------------------------------------------------------------------
HMM_CONFIG = {
    "n_regimes": 5,
    "covariance_type": "full",
    "n_iter": 300,
    "random_state": 42,
    "observation_features": [
        "m1_m2_spread",
        "m1_m12_spread",
        "fly_1_6_11",
        "front_carry_annualized",
        "realized_vol_20d",
    ],
    "min_training_days": 252,  # 1 year minimum (adjusted to allow shorter histories like crack spreads)
}

# ---------------------------------------------------------------------------
# Model hyperparameters
# ---------------------------------------------------------------------------
LGBM_DIRECTION_PARAMS = {
    "objective": "binary",
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "min_child_samples": 30,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "verbose": -1,
    "n_jobs": -1,
}

LGBM_DIRECTION_GRID = {
    "learning_rate": [0.01, 0.05],
    "num_leaves": [15, 31],
    "max_depth": [3, 5],
    "feature_fraction": [0.6, 0.8],
}


LGBM_REGRESSION_PARAMS = {
    "objective": "huber",
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.02,
    "subsample": 0.75,
    "colsample_bytree": 0.6,
    "min_child_samples": 50,
    "reg_alpha": 0.5,
    "reg_lambda": 2.0,
    "random_state": 42,
    "verbose": -1,
    "n_jobs": -1,
}

# ---------------------------------------------------------------------------
# Forecast horizons (trading days)
# ---------------------------------------------------------------------------
FORECAST_HORIZONS = {
    "short": 1,
    "medium": 5,
    "long": 21,
}

# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------
VALIDATION_CONFIG = {
    "test_window_days": 21,      # ~1 month per window
    "min_train_days": 504,       # ~2 years minimum training
    "oos_reserve_days": 42,      # ~2 months held out
    "expanding_window": True,    # expanding vs. rolling
}

# ---------------------------------------------------------------------------
# Trading signal thresholds
# ---------------------------------------------------------------------------
SIGNAL_THRESHOLDS = {
    "high_confidence_prob": 0.62,
    "min_trade_prob": 0.55,
    "min_confidence": 0.30,
    "max_position_pct": 0.03,
    "default_position_pct": 0.015,
    "risk_reward_min": 1.5,
}

# ---------------------------------------------------------------------------
# Retraining schedule
# ---------------------------------------------------------------------------
RETRAIN_CONFIG = {
    "full_retrain_interval_days": 7,   # Weekly full retrain
    "recalibrate_interval_days": 1,    # Daily recalibration
    "min_new_observations": 5,         # Minimum new data points to trigger retrain
}

# ---------------------------------------------------------------------------
# Feature lists by category
# ---------------------------------------------------------------------------
CURVE_FEATURES = [
    "m1_m2_spread", "m1_m3_spread", "m1_m6_spread", "m1_m12_spread",
    "m6_m12_spread", "fly_1_3_5", "fly_3_6_9", "fly_1_6_11",
    "front_carry_annualized", "back_carry_annualized",
    "m1_m12_spread_1d_chg", "m1_m12_spread_5d_chg",
    "m1_m2_spread_1d_chg", "m1_m2_spread_5d_chg",
]

FUNDAMENTAL_FEATURES = [
    "crude_inv_vs_5yr", "crude_inv_wow_change",
    "gasoline_inv_vs_5yr", "distillate_inv_vs_5yr",
    "total_product_inv_vs_5yr",
    "mm_net_long_zscore_52w", "mm_net_wow_change",
    "mm_long_short_ratio", "news_sentiment",
]

TECHNICAL_FEATURES = [
    # Momentum
    "roc_5d",
    "roc_21d",
    "rsi_14",
    "macd_histogram_norm",
    
    # Trend
    "ema_20_50_diff_pct",
    "adx_14",
    
    # Oscillators
    "williams_r_14",
    "cci_20",
    "stoch_k_14",
    "stoch_d_3",

    # Volatility
    "realized_vol_20d",
    "realized_vol_60d",
    "vol_ratio_20_60",
    "atr_pct",
    "bb_width",
    "bb_pct_b",
    
    # Mean Reversion
    "price_zscore_20d",
    "price_zscore_60d",
    "dist_from_52w_high",
]

MACRO_FEATURES = [
    "dxy_level", "dxy_5d_roc",
    "us_10y_yield", "us_10y_5d_chg",
    "vix", "vix_5d_chg",
    "spx_5d_roc",
]

SEASONAL_FEATURES = [
    "month_sin", "month_cos", "week_sin", "week_cos",
    "dow_sin", "dow_cos",
    "is_eia_report_day", "is_roll_period",
    "is_driving_season", "is_winter_heating",
    "days_to_expiry",
]

REGIME_FEATURES = [
    "regime_label_encoded",
    "regime_severity",
    "regime_age_days",
]

ALL_FEATURES = (
    CURVE_FEATURES + FUNDAMENTAL_FEATURES + TECHNICAL_FEATURES +
    MACRO_FEATURES + SEASONAL_FEATURES + REGIME_FEATURES
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data")
MODEL_DIR = os.path.join(BASE_DIR, "prediction", "saved_models")
os.makedirs(MODEL_DIR, exist_ok=True)
