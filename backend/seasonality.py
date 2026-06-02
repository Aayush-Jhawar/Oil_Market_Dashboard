"""Seasonality fetcher for refinery utilization (simulated).

Provides week-of-year stats and a current comparison.
"""
from __future__ import annotations

import datetime
from typing import Dict, Any


def fetch_seasonality() -> Dict[str, Any] | None:
    # Return 52 weeks with simple synthetic norm and current value
    weeks = []
    today = datetime.date.today()
    current_week = today.isocalendar()[1]
    for w in range(1, 53):
        norm = 85.0  # percent
        current = norm + (0 if w != current_week else 0)
        sigma_dev = 0.0
        weeks.append({"week_num": w, "norm_pct": norm, "current_pct": current, "sigma_dev": sigma_dev})

    return {
        "weeks": weeks,
        "current_week": current_week,
        "current_vs_norm_pct": weeks[current_week - 1]["current_pct"] - weeks[current_week - 1]["norm_pct"],
        "deviation_sigma": 0.0,
    }
