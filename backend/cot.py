"""CFTC Commitments of Traders (COT) minimal fetcher.

Provides a small, dependency-light interface returning simulated COT data
when upstream is not configured.
"""
from __future__ import annotations

import datetime
from typing import Dict, Any


def fetch_cot_history() -> Dict[str, Any]:
    now = datetime.date.today()
    history_12w = []
    for i in range(12):
        d = now - datetime.timedelta(weeks=(11 - i))
        history_12w.append({"date": d.isoformat(), "mm_net": 0})

    return {
        "mm_long": 0,
        "mm_short": 0,
        "mm_net": 0,
        "mm_net_wow": 0,
        "producer_long": 0,
        "producer_short": 0,
        "producer_net": 0,
        "open_interest": 0,
        "report_date": now.isoformat(),
        "history_12w": history_12w,
    }
