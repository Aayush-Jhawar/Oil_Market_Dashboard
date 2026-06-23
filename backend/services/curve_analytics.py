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
