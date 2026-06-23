"""
Training Pipeline
===================
Offline training script for the prediction engine.
Pulls historical data, builds feature matrix, fits regime HMM,
and trains the ensemble models.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
import pandas as pd

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from prediction.features.feature_matrix import build_historical_feature_matrix, add_target_variables
from prediction.regime.regime_engine import RegimeEngine
from prediction.models.ensemble import ModelEnsemble
from prediction.feature_store import ModelMetadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def load_price_history(symbol: str) -> pd.DataFrame:
    """Load raw 1-minute data directly from CSV files for training."""
    from services.data_loader import load_full_1min_history
    try:
        df = load_full_1min_history(symbol)
        return df
    except Exception as e:
        logger.error(f"Error loading price history: {e}")
        return pd.DataFrame()


def train_pipeline(symbol: str = "WTI", horizon_periods: int = 60):
    """Run full training pipeline."""
    logger.info(f"Starting training pipeline for {symbol} (horizon {horizon_periods} periods)")

    # 1. Load Data
    logger.info("Loading historical 1-minute price data...")
    price_df = load_price_history(symbol)
    if price_df.empty:
        logger.error(f"No 1-minute price history found for {symbol}")
        return
    logger.info(f"Loaded {len(price_df)} raw 1-minute rows for {symbol}")

    # ── Sub-sample to 15-minute bars for training efficiency ──────────────
    # This reduces 1.8M rows → ~120k rows, cutting feature-matrix build time
    # from 60+ minutes to ~4 minutes while preserving intraday signal quality.
    logger.info("Sub-sampling to 15-minute bars...")
    price_df = price_df.iloc[::15].copy()
    logger.info(f"After 15-min sampling: {len(price_df)} rows")

    # In MVP, we might only have price data and no full history of curve/EIA/CFTC yet
    # We will build features from whatever is available
    logger.info("Building feature matrix...")
    from prediction.features.feature_store_service import FeatureStoreService
    
    # We set use_pca=False by default as requested in Phase 4C unless collinearity becomes an issue
    feature_store = FeatureStoreService(use_pca=False)
    
    raw_feature_matrix, feature_matrix = feature_store.fit_transform_historical(
        price_history=price_df,
        curve_history=None,   # To be loaded in full version
        eia_history=None,     # To be loaded in full version
        cftc_history=None,    # To be loaded in full version
        macro_history=None,   # To be loaded in full version
    )
    
    # Save transformers immediately so daily_runner can use them
    feature_store.save()

    if feature_matrix.empty:
        logger.error("Feature matrix is empty")
        return

    # Add targets
    is_spread = "SPREAD" in symbol or "FLY" in symbol or "CRACK" in symbol
    df = add_target_variables(feature_matrix, price_df, {f"{horizon_periods}p": horizon_periods}, is_spread=is_spread)
    target_dir_col = f"target_direction_{horizon_periods}p"
    target_ret_col = f"target_return_{horizon_periods}p"
    df = df.dropna(subset=[target_dir_col, target_ret_col])

    if len(df) < 100:
        logger.error(f"Not enough data for training: {len(df)} rows after removing NaN targets")
        return

    # Extract targets for Similarity Engine and Models
    y_dir = df[target_dir_col]
    y_ret = df[target_ret_col]

    # 2. Fit Regime Engine
    logger.info("Fitting Regime Engine (HMM + Similarity)...")
    regime_engine = RegimeEngine()
    regime_engine.fit(df, y_ret)
    regime_engine.save_all()

    # Get historical labels (using raw features for correct dollar-spread thresholds)
    logger.info("Classifying historical regimes...")
    regime_history = regime_engine.classify_history(raw_feature_matrix)
    df["regime_label"] = regime_history["regime_label"]
    df = df.dropna(subset=["regime_label"])

    # 3. Fit Ensemble Models
    logger.info("Fitting Ensemble Models...")
    ensemble = ModelEnsemble(horizon=horizon_periods, symbol=symbol)
    
    X = df.drop(columns=[target_dir_col, target_ret_col, "regime_label"])
    
    metrics = ensemble.fit(X, y_dir, y_ret, df["regime_label"])
    ensemble.save_all()

    # 4. Save Metadata
    logger.info("Saving model metadata...")
    db = SessionLocal()
    try:
        import json
        version = datetime.now().strftime("%Y%m%d_%H%M")
        
        # Save global direction metadata
        meta = ModelMetadata(
            id=f"{symbol}_global_direction_{horizon_periods}p_{version}",
            model_name=f"{symbol}_global_direction_{horizon_periods}p",
            model_version=version,
            trained_at=datetime.now(),
            training_end_date=str(df.index[-1].date()),
            n_training_samples=len(X),
            n_features=X.shape[1],
            top_features_json=json.dumps(ensemble.global_model.get_feature_importance()),
        )
        db.merge(meta)
        db.commit()
    except Exception as e:
        logger.error(f"Error saving metadata: {e}")
        db.rollback()
    finally:
        db.close()

    logger.info(f"Training pipeline for {symbol} completed successfully.")

if __name__ == "__main__":
    symbols_to_train = [
        "WTI", "Brent", "HO", "GO",
        "3-2-1CRACK", "GASCRACK", "DIESELCRACK", 
        "WTI_FLY", "BRENT_FLY"
    ]
    for sym in symbols_to_train:
        train_pipeline(sym, horizon_periods=60)
