"""Data loading + point-in-time feature assembly for the ML harness.

v1 feature set = technical + seasonal, both derived from daily OHLCV in
``energy.db:price_history`` (so they update live through the latest trading
day). Curve / EIA / CFTC / macro are intentionally excluded in v1 — that data
is frozen at 2026-05-22 and would pin most features at serve time (see plan
Phase 8). We reuse the point-in-time builders from ``legacy_archive.prediction``.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Tuple

import numpy as np
import pandas as pd

from ml.paths import ensure_prediction_importable, HORIZONS

logger = logging.getLogger(__name__)

# Minimum daily rows before features are meaningful (needs ~252 for the
# 52-week and 60d indicators to populate).
MIN_ROWS = 260


def _db_path() -> str:
    ensure_prediction_importable()
    from database import DB_PATH  # noqa: E402  (path set above)
    return DB_PATH


def load_price_history(symbol: str) -> pd.DataFrame:
    """Daily OHLCV for one symbol, date-indexed ascending, cleaned."""
    path = _db_path()
    con = sqlite3.connect("file:" + path + "?mode=ro", uri=True, timeout=30)
    try:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM price_history "
            "WHERE symbol = ? AND close IS NOT NULL ORDER BY date",
            con, params=(symbol,),
        )
    finally:
        con.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).drop_duplicates(subset=["date"], keep="last")
    df = df.set_index("date").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Fill any missing OHLC from close so the indicator math never divides by NaN.
    for c in ("open", "high", "low"):
        df[c] = df[c].fillna(df["close"])
    df["volume"] = df["volume"].fillna(0.0)
    df = df[df["close"] > 0]
    return df


def build_features(symbol: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(feature_matrix, price_history)``.

    ``feature_matrix`` is technical + seasonal features indexed by date, with no
    look-ahead (every row uses only data available at that day's close).
    """
    ensure_prediction_importable()
    from prediction.features.feature_matrix import build_historical_feature_matrix

    price = load_price_history(symbol)
    if price.empty or len(price) < MIN_ROWS:
        logger.warning("build_features(%s): only %d rows (need >= %d)", symbol, len(price), MIN_ROWS)
        return pd.DataFrame(), price
    fm = build_historical_feature_matrix(price)
    return fm, price


def _clean_features(X: pd.DataFrame) -> pd.DataFrame:
    """Numeric-only, past-only imputation (ffill then 0), inf-safe."""
    X = X.select_dtypes(include=[np.number]).copy()
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.ffill().fillna(0.0)
    return X


def build_supervised(symbol: str, horizon: str) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return ``(X, y_direction, forward_return)`` aligned + cleaned for one horizon.

    Targets are forward-looking (dropped where unrealized). Feature columns are
    numeric, imputed with past-only fills. Index is the trade date.
    """
    ensure_prediction_importable()
    from prediction.features.feature_matrix import add_target_variables

    fm, price = build_features(symbol)
    if fm.empty:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float)

    days = HORIZONS[horizon]
    witht = add_target_variables(fm, price, {horizon: days})
    dir_col, ret_col = f"target_direction_{horizon}", f"target_return_{horizon}"
    witht = witht.dropna(subset=[dir_col, ret_col])
    if witht.empty:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float)

    target_cols = [c for c in witht.columns if c.startswith("target_")]
    X = _clean_features(witht.drop(columns=target_cols))
    # Drop zero-variance columns (e.g. the historically-mocked `news_sentiment`,
    # which is a serving-time overlay, and any constant seasonal flag). A column
    # constant across all rows carries no signal and breaks scaler variance.
    X = X.loc[:, X.std(numeric_only=True) > 0]
    y_dir = witht[dir_col].astype(int)
    fwd_ret = witht[ret_col].astype(float)
    # Guard: no target column may leak into X.
    assert not any(c.startswith("target_") for c in X.columns), "target leaked into X"
    return X, y_dir, fwd_ret


def latest_feature_row(symbol: str) -> Tuple[pd.Series, str]:
    """Most-recent point-in-time feature vector for live inference + its date."""
    fm, _price = build_features(symbol)
    if fm.empty:
        return pd.Series(dtype=float), ""
    X = _clean_features(fm)
    last = X.iloc[-1]
    return last, str(X.index[-1].date())
