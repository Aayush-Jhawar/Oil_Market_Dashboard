"""
Macro Feature Calculator
=========================
Computes macro-economic features: DXY, interest rates, VIX, equity indices.
All features use same-day close alignment.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_macro_features(
    macro_data: Optional[Dict] = None,
    macro_history: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """
    Compute macro features from latest macro data snapshot.

    Args:
        macro_data: Latest macro data dict with keys:
            dxy, dxy_change, vix, spx_change, us_10y_yield, etc.
        macro_history: DataFrame of historical macro values for computing
                       rate-of-change features.

    Returns:
        Dict of feature_name -> value.
    """
    features: Dict[str, float] = {}

    if not macro_data:
        return features

    # DXY
    dxy = macro_data.get("dxy")
    dxy_chg = macro_data.get("dxy_change")
    if dxy is not None:
        features["dxy_level"] = float(dxy)
    if dxy_chg is not None:
        features["dxy_1d_chg"] = float(dxy_chg)

    # Compute 5d DXY ROC from history
    if macro_history is not None and "dxy" in macro_history.columns:
        dxy_series = macro_history["dxy"].dropna()
        if len(dxy_series) >= 6 and dxy is not None:
            prev_5d = dxy_series.iloc[-6]
            if prev_5d != 0:
                features["dxy_5d_roc"] = (dxy - prev_5d) / prev_5d * 100

    # US 10Y yield
    us10y = macro_data.get("us_10y_yield") or macro_data.get("us10y")
    if us10y is not None:
        features["us_10y_yield"] = float(us10y)

    if macro_history is not None and "us_10y_yield" in macro_history.columns:
        yield_series = macro_history["us_10y_yield"].dropna()
        if len(yield_series) >= 6 and us10y is not None:
            features["us_10y_5d_chg"] = us10y - yield_series.iloc[-6]

    # VIX
    vix = macro_data.get("vix")
    if vix is not None:
        features["vix"] = float(vix)

    if macro_history is not None and "vix" in macro_history.columns:
        vix_series = macro_history["vix"].dropna()
        if len(vix_series) >= 6 and vix is not None:
            features["vix_5d_chg"] = vix - vix_series.iloc[-6]

    # SPX
    spx_chg = macro_data.get("spx_change")
    if spx_chg is not None:
        features["spx_1d_chg"] = float(spx_chg)

    if macro_history is not None and "spx" in macro_history.columns:
        spx_series = macro_history["spx"].dropna()
        if len(spx_series) >= 6:
            cur = spx_series.iloc[-1]
            prev = spx_series.iloc[-6]
            if prev != 0:
                features["spx_5d_roc"] = (cur - prev) / prev * 100

    return features


def compute_macro_features_from_history(
    macro_history: pd.DataFrame,
    price_dates: Optional[pd.DatetimeIndex] = None,
) -> pd.DataFrame:
    """
    Compute macro features for a full history, aligned to trading dates.

    Args:
        macro_history: DataFrame with columns dxy, vix, us_10y_yield, spx, etc.
                       and DatetimeIndex.
        price_dates: DatetimeIndex of daily trading dates for alignment.

    Returns:
        DataFrame with macro features at daily frequency.
    """
    if macro_history is None or macro_history.empty:
        return pd.DataFrame()

    df = macro_history.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    df = df.sort_index()

    features_df = pd.DataFrame(index=df.index)

    # DXY
    if "dxy" in df.columns:
        features_df["dxy_level"] = df["dxy"]
        features_df["dxy_1d_chg"] = df["dxy"].diff()
        if len(df) > 5:
            features_df["dxy_5d_roc"] = df["dxy"].pct_change(5) * 100

    # 10Y yield
    if "us_10y_yield" in df.columns:
        features_df["us_10y_yield"] = df["us_10y_yield"]
        features_df["us_10y_5d_chg"] = df["us_10y_yield"].diff(5)

    # VIX
    if "vix" in df.columns:
        features_df["vix"] = df["vix"]
        features_df["vix_5d_chg"] = df["vix"].diff(5)

    # SPX
    if "spx" in df.columns:
        features_df["spx_1d_chg"] = df["spx"].pct_change() * 100
        features_df["spx_5d_roc"] = df["spx"].pct_change(5) * 100

    # Reindex to price dates if provided
    if price_dates is not None and len(price_dates) > 0:
        features_df = features_df.reindex(price_dates, method="ffill")

    return features_df
