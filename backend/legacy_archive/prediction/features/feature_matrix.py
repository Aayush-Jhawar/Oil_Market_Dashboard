"""
Feature Matrix Builder
========================
Assembles all individual feature calculators into a single point-in-time
feature matrix. This is the central feature pipeline that prevents
look-ahead bias by ensuring every feature at time t uses only data
available at market close of day t.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from prediction.features.curve_features import (
    compute_curve_features,
    compute_curve_features_from_history,
)
from prediction.features.fundamental_features import (
    compute_fundamental_features,
    compute_fundamental_features_from_history,
)
from prediction.features.technical_features import (
    compute_technical_features,
    compute_technical_features_from_history,
)
from prediction.features.macro_features import (
    compute_macro_features,
    compute_macro_features_from_history,
)
from prediction.features.seasonal_features import (
    compute_seasonal_features,
    compute_seasonal_features_from_history,
)

logger = logging.getLogger(__name__)


def build_daily_feature_vector(
    date_str: str,
    curve_prices: Optional[Dict[str, float]] = None,
    prev_curves: Optional[List[Dict[str, float]]] = None,
    closes: Optional[List[float]] = None,
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    eia_data: Optional[Dict] = None,
    cftc_data: Optional[Dict] = None,
    macro_data: Optional[Dict] = None,
    regime_label: Optional[str] = None,
    regime_severity: Optional[float] = None,
    regime_age_days: Optional[int] = None,
    news_sentiment: float = 0.0,
) -> Dict[str, float]:
    """
    Build a complete feature vector for a single trading day.

    This is used for real-time daily predictions. All inputs must be
    point-in-time: only data available at market close of `date_str`.

    Returns:
        Dict of feature_name -> value (flat dictionary).
    """
    features: Dict[str, float] = {}

    # ── Curve features ────────────────────────────────────────────────────
    if curve_prices:
        curve_feats = compute_curve_features(curve_prices, prev_curves)
        features.update(curve_feats)

    # ── Technical features ────────────────────────────────────────────────
    if closes and len(closes) >= 21:
        tech_feats = compute_technical_features(closes, highs, lows)
        features.update(tech_feats)

    # ── Fundamental features ──────────────────────────────────────────────
    fund_feats = compute_fundamental_features(eia_data, cftc_data)
    features.update(fund_feats)

    # ── Macro features ────────────────────────────────────────────────────
    macro_feats = compute_macro_features(macro_data)
    features.update(macro_feats)

    # ── Seasonal features ─────────────────────────────────────────────────
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        seasonal_feats = compute_seasonal_features(dt)
        features.update(seasonal_feats)
    except Exception as e:
        logger.debug(f"Could not compute seasonal features for {date_str}: {e}")

    # ── Regime features ───────────────────────────────────────────────────
    if regime_label is not None:
        regime_map = {"CONTANGO": 0, "NEUTRAL": 1, "BACKWARDATION": 2}
        features["regime_label_encoded"] = float(regime_map.get(regime_label, 1))
    if regime_severity is not None:
        features["regime_severity"] = regime_severity
    if regime_age_days is not None:
        features["regime_age_days"] = float(regime_age_days)
        
    features["news_sentiment"] = news_sentiment

    return features


def build_historical_feature_matrix(
    price_history: pd.DataFrame,
    curve_history: Optional[pd.DataFrame] = None,
    eia_history: Optional[pd.DataFrame] = None,
    cftc_history: Optional[pd.DataFrame] = None,
    macro_history: Optional[pd.DataFrame] = None,
    regime_history: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Build a complete feature matrix from historical data.

    This is the offline pipeline used for training. All feature computations
    use only backward-looking information (no look-ahead bias).

    Args:
        price_history: DataFrame with date index, columns: open, high, low, close, volume.
        curve_history: DataFrame with date index, columns: M1, M2, ..., M12.
        eia_history: DataFrame with date index, weekly EIA data.
        cftc_history: DataFrame with date index, weekly CFTC data.
        macro_history: DataFrame with date index, columns: dxy, vix, us_10y_yield, spx.
        regime_history: DataFrame with date index, columns: regime_label, regime_severity.

    Returns:
        Complete feature matrix DataFrame indexed by date.
    """
    if price_history is None or price_history.empty:
        logger.error("price_history is required for feature matrix construction")
        return pd.DataFrame()

    dates = price_history.index
    feature_dfs = []

    # ── Technical features ────────────────────────────────────────────────
    logger.info("Computing technical features...")
    tech_df = compute_technical_features_from_history(price_history)
    if not tech_df.empty:
        feature_dfs.append(tech_df)

    # ── Curve features ────────────────────────────────────────────────────
    if curve_history is not None and not curve_history.empty:
        logger.info("Computing curve features...")
        curve_df = compute_curve_features_from_history(curve_history)
        if not curve_df.empty:
            # Align to price dates
            curve_df = curve_df.reindex(dates, method="ffill")
            feature_dfs.append(curve_df)

    # ── Fundamental features ──────────────────────────────────────────────
    if eia_history is not None or cftc_history is not None:
        logger.info("Computing fundamental features...")
        fund_df = compute_fundamental_features_from_history(
            eia_history, cftc_history, dates
        )
        if not fund_df.empty:
            feature_dfs.append(fund_df)

    # ── Macro features ────────────────────────────────────────────────────
    if macro_history is not None and not macro_history.empty:
        logger.info("Computing macro features...")
        macro_df = compute_macro_features_from_history(macro_history, dates)
        if not macro_df.empty:
            feature_dfs.append(macro_df)

    # ── Seasonal features ─────────────────────────────────────────────────
    logger.info("Computing seasonal features...")
    seasonal_df = compute_seasonal_features_from_history(dates)
    if not seasonal_df.empty:
        feature_dfs.append(seasonal_df)

    # ── Regime features ───────────────────────────────────────────────────
    if regime_history is not None and not regime_history.empty:
        logger.info("Adding regime features...")
        regime_df = regime_history.copy()
        if "regime_label" in regime_df.columns:
            regime_map = {"CONTANGO": 0, "NEUTRAL": 1, "BACKWARDATION": 2}
            regime_df["regime_label_encoded"] = regime_df["regime_label"].map(regime_map).fillna(1)
        regime_df = regime_df.reindex(dates, method="ffill")
        feature_dfs.append(regime_df[["regime_label_encoded", "regime_severity"]].dropna(how="all"))

    # ── Combine all features ──────────────────────────────────────────────
    if not feature_dfs:
        return pd.DataFrame()

    combined = pd.concat(feature_dfs, axis=1)
    # Remove duplicate columns
    combined = combined.loc[:, ~combined.columns.duplicated()]

    # Mock historical sentiment (0.0) since true history is unavailable
    if "news_sentiment" not in combined.columns:
        combined["news_sentiment"] = 0.0

    logger.info(f"Feature matrix: {combined.shape[0]} rows × {combined.shape[1]} columns")
    return combined


def add_target_variables(
    feature_matrix: pd.DataFrame,
    price_history: pd.DataFrame,
    horizons: Dict[str, int] = None,
    close_col: str = "close",
    is_spread: bool = False,
) -> pd.DataFrame:
    """
    Add target variables (future returns) to the feature matrix.

    Targets are computed by looking FORWARD — they represent the
    actual future outcome and are used ONLY during training.
    During inference, these columns will be NaN.

    Args:
        feature_matrix: Feature matrix from build_historical_feature_matrix.
        price_history: Price DataFrame with close column.
        horizons: Dict of horizon_name -> days, e.g. {"1d": 1, "5d": 5, "21d": 21}
        is_spread: If True, target return is absolute price change.

    Returns:
        Feature matrix with additional target columns.
    """
    if horizons is None:
        horizons = {"1d": 1, "5d": 5, "21d": 21}

    closes = price_history[close_col] if close_col in price_history.columns else None
    if closes is None:
        return feature_matrix

    df = feature_matrix.copy()

    for name, days in horizons.items():
        # Future return
        future_close = closes.shift(-days)
        if is_spread:
            ret = future_close - closes
        else:
            ret = (future_close - closes) / closes
            
        df[f"target_return_{name}"] = ret

        # Direction (binary: 1 = up, 0 = down)
        df[f"target_direction_{name}"] = (ret > 0).astype(float)

    return df
