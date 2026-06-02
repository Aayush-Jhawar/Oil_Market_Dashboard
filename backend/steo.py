"""Minimal STEO balance fetcher (simulated).

Returns a small structure matching the spec but with placeholder values.
"""
from __future__ import annotations

from typing import Dict, Any
import datetime


def fetch_steo_balance() -> Dict[str, Any] | None:
    # For now return a simple simulated series (monthly for next 12 months)
    months = []
    world_supply = []
    world_demand = []
    implied_balance = []
    is_forecast = []
    today = datetime.date.today()
    for i in range(12):
        m = (today.replace(day=1) + datetime.timedelta(days=30 * i)).strftime('%Y-%m')
        months.append(m)
        world_supply.append(100.0)  # mbpd
        world_demand.append(99.5)
        implied_balance.append(0.5)
        is_forecast.append(i >= 0)

    return {
        "months": months,
        "world_supply": world_supply,
        "world_demand": world_demand,
        "implied_balance": implied_balance,
        "opec_supply": [30.0] * 12,
        "nonopec_supply": [70.0] * 12,
        "oecd_demand": [50.0] * 12,
        "non_oecd_demand": [50.0] * 12,
        "is_forecast": is_forecast,
        "fwd_6m_avg": sum(implied_balance[:6]) / 6,
        "fwd_12m_avg": sum(implied_balance) / 12,
    }
