"""
Seasonal Feature Calculator
=============================
Computes time-based cyclical features:
- Month/week/day-of-week (sin/cos encoding for cyclical continuity)
- EIA report day (Wednesday)
- Roll period proximity
- Seasonal demand patterns (driving season, winter heating)
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, date, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# WTI futures typically expire on the 3rd business day before the 25th
# of the month preceding delivery. Approximate roll period = last 5
# business days before expiry.
_APPROX_EXPIRY_DAY = 20  # Approximate calendar day of expiry


def compute_seasonal_features(
    dt: date,
    days_to_expiry: Optional[int] = None,
) -> Dict[str, float]:
    """
    Compute seasonal/calendar features for a single date.

    Args:
        dt: Date to compute features for.
        days_to_expiry: Business days to front-month contract expiry.
                        If None, estimated from calendar.

    Returns:
        Dict of feature_name -> value.
    """
    features: Dict[str, float] = {}

    month = dt.month
    week = dt.isocalendar()[1]
    dow = dt.weekday()  # 0=Monday, 6=Sunday

    # ── Cyclical encodings ────────────────────────────────────────────────
    # Sin/cos encoding preserves cyclical continuity (Dec→Jan, Fri→Mon)
    features["month_sin"] = math.sin(2 * math.pi * month / 12)
    features["month_cos"] = math.cos(2 * math.pi * month / 12)
    features["week_sin"] = math.sin(2 * math.pi * week / 52)
    features["week_cos"] = math.cos(2 * math.pi * week / 52)
    features["dow_sin"] = math.sin(2 * math.pi * dow / 5)  # 5 trading days
    features["dow_cos"] = math.cos(2 * math.pi * dow / 5)

    # ── Event flags ───────────────────────────────────────────────────────
    # EIA weekly petroleum report releases on Wednesday
    features["is_eia_report_day"] = 1.0 if dow == 2 else 0.0

    # Roll period: approximately last 5 business days before expiry
    if days_to_expiry is not None:
        features["days_to_expiry"] = float(days_to_expiry)
        features["is_roll_period"] = 1.0 if days_to_expiry <= 5 else 0.0
    else:
        # Estimate: if current day > 15th and we're in the month before
        # delivery, we're likely in roll period
        est_dte = max(0, _APPROX_EXPIRY_DAY - dt.day)
        if dt.day > _APPROX_EXPIRY_DAY:
            # Already past this month's expiry — next month
            est_dte = 20 + (30 - dt.day)  # rough estimate
        features["days_to_expiry"] = float(est_dte)
        features["is_roll_period"] = 1.0 if est_dte <= 5 else 0.0

    # ── Seasonal demand patterns ──────────────────────────────────────────
    # US driving season: Memorial Day (late May) to Labor Day (early Sep)
    features["is_driving_season"] = 1.0 if 5 <= month <= 9 else 0.0

    # Winter heating season: November to March
    features["is_winter_heating"] = 1.0 if month in (11, 12, 1, 2, 3) else 0.0

    # Refinery turnaround season: typically Mar-Apr and Sep-Oct
    features["is_turnaround_season"] = 1.0 if month in (3, 4, 9, 10) else 0.0

    return features


def compute_seasonal_features_from_history(
    dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    Compute seasonal features for a full date range.

    Args:
        dates: DatetimeIndex of trading dates.

    Returns:
        DataFrame with seasonal features indexed by date.
    """
    if dates is None or len(dates) == 0:
        return pd.DataFrame()

    records = []
    for dt in dates:
        d = dt.date() if hasattr(dt, "date") else dt
        feats = compute_seasonal_features(d)
        feats["date"] = dt
        records.append(feats)

    df = pd.DataFrame(records)
    df = df.set_index("date")
    return df
