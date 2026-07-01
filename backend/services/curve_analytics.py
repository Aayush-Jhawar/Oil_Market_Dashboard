import logging
from typing import Dict, List, Optional
import numpy as np

from services.forward_curve import fetch_forward_curve

logger = logging.getLogger(__name__)

def get_market_structure_analytics(symbol: str) -> Dict:
    """
    Returns full curve data, calculated spreads, flies, and Z-scores for the given symbol.
    """
    # 1. Fetch curve
    curve_points, meta = fetch_forward_curve(symbol)
    
    # Map points by month index
    prices = {int(p["month"].replace("M", "")): p["price"] for p in curve_points}
    
    def safe_diff(m_front, m_back):
        if m_front in prices and m_back in prices:
            return round(prices[m_front] - prices[m_back], 3)
        return None
        
    def safe_fly(m1, m2, m3):
        if m1 in prices and m2 in prices and m3 in prices:
            return round(prices[m1] - 2 * prices[m2] + prices[m3], 3)
        return None

    def safe_dfly(m1, m2, m3, m4):
        if m1 in prices and m2 in prices and m3 in prices and m4 in prices:
            return round(prices[m1] - 3 * prices[m2] + 3 * prices[m3] - prices[m4], 3)
        return None

    # 2. Calculate spreads
    spreads = {
        "m1_m2": safe_diff(1, 2),
        "m1_m3": safe_diff(1, 3),
        "m1_m6": safe_diff(1, 6),
        "m1_m12": safe_diff(1, 12),
    }

    # 3. Calculate flies dynamically (equidistant up to M12)
    flies = {}
    
    # Standard Flies (3 legs)
    for distance in range(1, 6):  # distance between legs: 1 to 5
        for m1 in range(1, 13):
            m2 = m1 + distance
            m3 = m1 + 2 * distance
            # Strict M12 hard cap and partial instrument prevention
            if m3 <= 12:
                if m1 in prices and m2 in prices and m3 in prices:
                    fly_name = f"fly_{m1}_{m2}_{m3}"
                    val = safe_fly(m1, m2, m3)
                    if val is not None:
                        flies[fly_name] = val
                else:
                    logger.warning(f"Skipping partial Fly {symbol} M{m1}-M{m2}-M{m3}: Missing data legs.")
                    
    # Double Flies (4 legs)
    for distance in range(1, 4):  # distance between legs: 1 to 3
        for m1 in range(1, 13):
            m2 = m1 + distance
            m3 = m1 + 2 * distance
            m4 = m1 + 3 * distance
            # Strict M12 hard cap and partial instrument prevention
            if m4 <= 12:
                if m1 in prices and m2 in prices and m3 in prices and m4 in prices:
                    dfly_name = f"dfly_{m1}_{m2}_{m3}_{m4}"
                    val = safe_dfly(m1, m2, m3, m4)
                    if val is not None:
                        flies[dfly_name] = val
                else:
                    logger.warning(f"Skipping partial Double Fly {symbol} M{m1}-M{m2}-M{m3}-M{m4}: Missing data legs.")

    # TODO: Add historical percentiles and Z-scores from DB once available.
    # For now, returning None for z_scores to prevent UI errors.
    z_scores = {k: None for k in list(spreads.keys()) + list(flies.keys())}
    percentiles = {k: None for k in list(spreads.keys()) + list(flies.keys())}

    return {
        "symbol": symbol,
        "curve": curve_points,
        "meta": meta,
        "spreads": spreads,
        "flies": flies,
        "z_scores": z_scores,
        "percentiles": percentiles
    }


def get_custom_structure(symbol: str, legs: List[int]) -> Dict:
    """User-selected calendar spread (2 legs) or butterfly (3 legs) for curve
    analysis. Current value comes from the LIVE forward curve; the z-score /
    percentile / history come from the term-structure DB.

    legs are month indices, e.g. [2, 5] → M2-M5 spread, [2, 4, 6] → M2-M4-M6 fly.
    """
    legs = [int(x) for x in legs]
    n = len(legs)
    if n not in (2, 3):
        raise ValueError("legs must have 2 (spread) or 3 (butterfly) months")
    if any(m < 1 or m > 12 for m in legs):
        raise ValueError("months must be between 1 and 12")
    weights = [1, -1] if n == 2 else [1, -2, 1]
    stype = "spread" if n == 2 else "fly"

    # Live current value from the forward curve
    curve_points, meta = fetch_forward_curve(symbol)
    prices = {int(p["month"].replace("M", "")): p["price"] for p in curve_points}
    current = None
    if all(m in prices for m in legs):
        current = round(sum(w * prices[m] for w, m in zip(weights, legs)), 4)

    # Historical distribution from the term-structure DB (daily EOD curve)
    from services.price_fetcher import PriceFetcher
    df = PriceFetcher._query_historical_term_structure(symbol, days=1500)
    hist: List[Dict] = []
    stats = {"mean": None, "std": None, "zscore": None,
             "percentile": None, "min": None, "max": None}
    if df is not None:
        cols = [f"m{m}" for m in legs]
        if all(c in df.columns for c in cols):
            s = sum(w * df[c] for w, c in zip(weights, cols)).dropna()
            if len(s) > 5:
                arr = s.to_numpy(dtype=float)
                mean, std = float(np.mean(arr)), float(np.std(arr))
                cur = current if current is not None else float(arr[-1])
                stats = {
                    "mean": round(mean, 4),
                    "std": round(std, 4),
                    "zscore": round((cur - mean) / std, 2) if std > 0 else 0.0,
                    "percentile": round(float((arr < cur).mean() * 100), 1),
                    "min": round(float(arr.min()), 4),
                    "max": round(float(arr.max()), 4),
                }
                pairs = [{"date": str(d)[:10], "value": round(float(v), 4)}
                         for d, v in zip(s.index, arr)]
                # Downsample to ~400 points for a light chart payload
                step = max(1, len(pairs) // 400)
                hist = pairs[::step]

    return {
        "symbol": symbol,
        "legs": legs,
        "type": stype,
        "label": "-".join(f"M{m}" for m in legs),
        "current": current,
        "history": hist,
        "meta": meta,
        **stats,
    }
