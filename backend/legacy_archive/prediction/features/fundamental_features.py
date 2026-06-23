"""
Fundamental Feature Calculator
================================
Computes features from EIA inventories, CFTC COT positioning,
refinery utilization, and SPR data.

All features use point-in-time alignment: weekly data is forward-filled
from its release date (Wednesday for EIA, Friday for CFTC).
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_fundamental_features(
    eia_data: Optional[Dict] = None,
    cftc_data: Optional[Dict] = None,
    eia_history: Optional[pd.DataFrame] = None,
    cftc_history: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """
    Compute fundamental features from latest available data.

    Args:
        eia_data: Latest EIA snapshot dict with keys like:
            crude_level: {current_value, wow_change, five_year_avg}
            gasoline_level: {current_value, wow_change, five_year_avg}
            distillate_level: {current_value, wow_change, five_year_avg}
        cftc_data: Latest CFTC snapshot dict:
            WTI: {mm_long, mm_short, mm_net_long, ...}
        eia_history: DataFrame of historical EIA values for z-scoring
        cftc_history: DataFrame of historical CFTC values for z-scoring

    Returns:
        Dict of feature_name -> value
    """
    features: Dict[str, float] = {}

    # ── EIA Inventory Features ────────────────────────────────────────────
    if eia_data:
        # Crude inventories
        crude = eia_data.get("crude_level") or eia_data.get("crude_inventory") or {}
        current = crude.get("current_value")
        five_yr = crude.get("five_year_avg")
        wow = crude.get("wow_change")

        if current is not None and five_yr is not None and five_yr != 0:
            features["crude_inv_vs_5yr"] = (current - five_yr) / five_yr
        if wow is not None:
            features["crude_inv_wow_change"] = wow

        # Gasoline inventories
        gasoline = eia_data.get("gasoline_level") or eia_data.get("gasoline_inventory") or {}
        gas_current = gasoline.get("current_value")
        gas_five_yr = gasoline.get("five_year_avg")
        gas_wow = gasoline.get("wow_change")

        if gas_current is not None and gas_five_yr is not None and gas_five_yr != 0:
            features["gasoline_inv_vs_5yr"] = (gas_current - gas_five_yr) / gas_five_yr
        if gas_wow is not None:
            features["gasoline_inv_wow_change"] = gas_wow

        # Distillate inventories
        distillate = eia_data.get("distillate_level") or eia_data.get("distillate_inventory") or {}
        dist_current = distillate.get("current_value")
        dist_five_yr = distillate.get("five_year_avg")

        if dist_current is not None and dist_five_yr is not None and dist_five_yr != 0:
            features["distillate_inv_vs_5yr"] = (dist_current - dist_five_yr) / dist_five_yr

        # Total product supply
        total_current = sum(
            x.get("current_value", 0) or 0
            for x in [crude, gasoline, distillate]
        )
        total_five_yr = sum(
            x.get("five_year_avg", 0) or 0
            for x in [crude, gasoline, distillate]
        )
        if total_five_yr != 0 and total_current != 0:
            features["total_product_inv_vs_5yr"] = (total_current - total_five_yr) / total_five_yr

        # Refinery utilization
        refinery = eia_data.get("refinery_util") or {}
        util = refinery.get("current_value")
        if util is not None:
            features["refinery_utilization"] = util

        # SPR
        spr = eia_data.get("spr_level") or {}
        spr_val = spr.get("current_value")
        spr_wow = spr.get("wow_change")
        if spr_val is not None:
            features["spr_level"] = spr_val
        if spr_wow is not None:
            features["spr_weekly_change"] = spr_wow

    # ── CFTC Positioning Features ─────────────────────────────────────────
    if cftc_data:
        wti_cftc = cftc_data.get("WTI") or cftc_data.get("wti") or {}
        mm_net = wti_cftc.get("mm_net_long")
        mm_long = wti_cftc.get("mm_long")
        mm_short = wti_cftc.get("mm_short")

        if mm_net is not None:
            features["mm_net_long"] = mm_net

            # Z-score requires history
            if cftc_history is not None and "mm_net_long" in cftc_history.columns:
                net_series = cftc_history["mm_net_long"].dropna()
                if len(net_series) >= 52:
                    mean_52w = net_series.iloc[-52:].mean()
                    std_52w = net_series.iloc[-52:].std()
                    if std_52w > 0:
                        features["mm_net_long_zscore_52w"] = (mm_net - mean_52w) / std_52w

        if mm_net is not None and len(features) > 0:
            # Week-on-week change (if history available)
            if cftc_history is not None and "mm_net_long" in cftc_history.columns:
                net_series = cftc_history["mm_net_long"].dropna()
                if len(net_series) >= 2:
                    features["mm_net_wow_change"] = mm_net - net_series.iloc[-2]

        if mm_long is not None and mm_short is not None and mm_short > 0:
            features["mm_long_short_ratio"] = mm_long / mm_short

    return features


def compute_fundamental_features_from_history(
    eia_history: pd.DataFrame,
    cftc_history: Optional[pd.DataFrame] = None,
    price_dates: Optional[pd.DatetimeIndex] = None,
) -> pd.DataFrame:
    """
    Compute fundamental features aligned to daily trading dates.

    Weekly data (EIA released Wednesday, CFTC released Friday) is
    forward-filled to daily frequency using point-in-time alignment:
    the value available on day T is the most recent release BEFORE T.

    Args:
        eia_history: DataFrame with columns: date, crude_level, gasoline_level,
                     distillate_level, crude_wow, etc. Weekly frequency.
        cftc_history: DataFrame with columns: date, mm_net_long, mm_long,
                      mm_short, etc. Weekly frequency.
        price_dates: DatetimeIndex of daily trading dates to align to.

    Returns:
        DataFrame with fundamental features at daily frequency.
    """
    if price_dates is None or len(price_dates) == 0:
        return pd.DataFrame()

    daily_index = price_dates
    features_df = pd.DataFrame(index=daily_index)

    # ── EIA features (forward-fill from Wednesday) ────────────────────────
    if eia_history is not None and not eia_history.empty:
        eia = eia_history.copy()
        if "date" in eia.columns:
            eia["date"] = pd.to_datetime(eia["date"])
            eia = eia.set_index("date")
        eia = eia.sort_index()

        # Compute vs 5-year average using rolling 260-week window
        for col in ["crude_level", "gasoline_level", "distillate_level"]:
            if col in eia.columns:
                series = eia[col].dropna()
                five_yr_avg = series.rolling(window=260, min_periods=52).mean()
                vs_5yr_col = col.replace("_level", "_inv_vs_5yr")
                eia[vs_5yr_col] = (series - five_yr_avg) / five_yr_avg.replace(0, np.nan)

        if "crude_level" in eia.columns:
            eia["crude_inv_wow_change"] = eia["crude_level"].diff()

        # Reindex to daily and forward-fill
        eia_daily = eia.reindex(daily_index, method="ffill")

        for col in eia_daily.columns:
            if col in [
                "crude_inv_vs_5yr", "crude_inv_wow_change",
                "gasoline_inv_vs_5yr", "distillate_inv_vs_5yr",
                "total_product_inv_vs_5yr",
                "refinery_utilization", "spr_level", "spr_weekly_change",
            ]:
                features_df[col] = eia_daily[col]

    # ── CFTC features (forward-fill from Friday) ─────────────────────────
    if cftc_history is not None and not cftc_history.empty:
        cftc = cftc_history.copy()
        if "date" in cftc.columns:
            cftc["date"] = pd.to_datetime(cftc["date"])
            cftc = cftc.set_index("date")
        cftc = cftc.sort_index()

        if "mm_net_long" in cftc.columns:
            net = cftc["mm_net_long"]
            # Z-score vs 52-week rolling
            mean_52w = net.rolling(window=52, min_periods=26).mean()
            std_52w = net.rolling(window=52, min_periods=26).std()
            cftc["mm_net_long_zscore_52w"] = (net - mean_52w) / std_52w.replace(0, np.nan)
            cftc["mm_net_wow_change"] = net.diff()

        if "mm_long" in cftc.columns and "mm_short" in cftc.columns:
            cftc["mm_long_short_ratio"] = (
                cftc["mm_long"] / cftc["mm_short"].replace(0, np.nan)
            )

        cftc_daily = cftc.reindex(daily_index, method="ffill")
        for col in [
            "mm_net_long_zscore_52w", "mm_net_wow_change",
            "mm_long_short_ratio",
        ]:
            if col in cftc_daily.columns:
                features_df[col] = cftc_daily[col]

    return features_df
