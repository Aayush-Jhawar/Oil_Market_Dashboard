"""
Curve Feature Calculator
=========================
Computes features derived from the futures term structure:
- Calendar spreads (M1-M2, M1-M6, M1-M12, etc.)
- Butterfly / fly values
- Carry (roll return)
- Nelson-Siegel decomposition (Level, Slope, Curvature)
- Spread dynamics (changes over 1d, 5d)
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_curve_features(
    curve_prices: Dict[str, float],
    prev_curves: Optional[List[Dict[str, float]]] = None,
) -> Dict[str, float]:
    """
    Compute curve shape features from M1–M12 settlement prices.

    Args:
        curve_prices: Dict of {"M1": price, "M2": price, ..., "M12": price}
        prev_curves: List of previous day curve dicts (most recent first)
                     for computing changes. Need at least 5 for 5d changes.

    Returns:
        Dict of feature_name -> value.
    """
    features: Dict[str, float] = {}

    # Extract prices; use None for missing months
    prices = {}
    for i in range(1, 13):
        key = f"M{i}"
        prices[i] = curve_prices.get(key)

    m1 = prices.get(1)
    m2 = prices.get(2)
    m3 = prices.get(3)
    m5 = prices.get(5)
    m6 = prices.get(6)
    m9 = prices.get(9)
    m11 = prices.get(11)
    m12 = prices.get(12)

    # ── Calendar spreads ──────────────────────────────────────────────────
    if m1 is not None and m2 is not None:
        features["m1_m2_spread"] = m1 - m2
    if m1 is not None and m3 is not None:
        features["m1_m3_spread"] = m1 - m3
    if m1 is not None and m6 is not None:
        features["m1_m6_spread"] = m1 - m6
    if m1 is not None and m12 is not None:
        features["m1_m12_spread"] = m1 - m12
    if m6 is not None and m12 is not None:
        features["m6_m12_spread"] = m6 - m12

    # ── Butterfly / fly values ────────────────────────────────────────────
    if m1 is not None and m3 is not None and m5 is not None:
        features["fly_1_3_5"] = m1 - 2 * m3 + m5
    if m3 is not None and m6 is not None and m9 is not None:
        features["fly_3_6_9"] = m3 - 2 * m6 + m9
    if m1 is not None and m6 is not None and m11 is not None:
        features["fly_1_6_11"] = m1 - 2 * m6 + m11

    # ── Carry (annualized roll return) ────────────────────────────────────
    if m1 is not None and m2 is not None and m1 != 0:
        features["front_carry_annualized"] = (m1 - m2) / m1 * 12 * 100
    if m6 is not None and m12 is not None and m6 != 0:
        features["back_carry_annualized"] = (m6 - m12) / m6 * 2 * 100

    # ── Nelson-Siegel decomposition ───────────────────────────────────────
    ns = _nelson_siegel_fit(prices)
    if ns is not None:
        features["ns_level"] = ns[0]
        features["ns_slope"] = ns[1]
        features["ns_curvature"] = ns[2]

    # ── Spread dynamics (changes and ECT) ─────────────────────────────────
    if prev_curves:
        # ECT (Error Correction Term): Spread deviation from long-term mean
        # Requires enough history (e.g., 60 days) to compute rolling mean
        if len(prev_curves) >= 60:
            hist_spreads = []
            for prev in prev_curves[:60]:
                if prev.get("M1") is not None and prev.get("M12") is not None:
                    hist_spreads.append(prev.get("M1") - prev.get("M12"))
            
            if len(hist_spreads) >= 20: # At least 20 valid points to be meaningful
                rolling_mean = sum(hist_spreads) / len(hist_spreads)
                cur_spread = features.get("m1_m12_spread")
                if cur_spread is not None:
                    features["m1_m12_ect"] = cur_spread - rolling_mean

        for lag, suffix in [(0, "1d"), (4, "5d")]:
            if lag < len(prev_curves):
                prev = prev_curves[lag]
                prev_m1 = prev.get("M1")
                prev_m2 = prev.get("M2")
                prev_m12 = prev.get("M12")

                if prev_m1 is not None and prev_m12 is not None:
                    prev_spread = prev_m1 - prev_m12
                    cur_spread = features.get("m1_m12_spread")
                    if cur_spread is not None:
                        features[f"m1_m12_spread_{suffix}_chg"] = cur_spread - prev_spread

                if prev_m1 is not None and prev_m2 is not None:
                    prev_front = prev_m1 - prev_m2
                    cur_front = features.get("m1_m2_spread")
                    if cur_front is not None:
                        features[f"m1_m2_spread_{suffix}_chg"] = cur_front - prev_front

    return features


def compute_curve_features_from_history(
    daily_curves: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute curve features for an entire history of daily curve data.

    Args:
        daily_curves: DataFrame with columns M1, M2, ..., M12 and a DatetimeIndex.

    Returns:
        DataFrame with curve features indexed by date.
    """
    all_features = []

    for i, (dt, row) in enumerate(daily_curves.iterrows()):
        curve = {f"M{j}": row.get(f"M{j}") for j in range(1, 13)}

        # Build prev_curves list (most recent first)
        prev_curves = []
        for lag in range(1, 6):
            if i - lag >= 0:
                prev_row = daily_curves.iloc[i - lag]
                prev_curves.append({f"M{j}": prev_row.get(f"M{j}") for j in range(1, 13)})

        feats = compute_curve_features(curve, prev_curves)
        feats["date"] = dt
        all_features.append(feats)

    if not all_features:
        return pd.DataFrame()

    df = pd.DataFrame(all_features)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


# ---------------------------------------------------------------------------
# Nelson-Siegel fitting
# ---------------------------------------------------------------------------

def _nelson_siegel_fit(
    prices: Dict[int, Optional[float]],
    tau: float = 6.0,
) -> Optional[Tuple[float, float, float]]:
    """
    Fit Nelson-Siegel model to curve prices.

    NS(m) = β0 + β1 * [(1 - exp(-m/τ)) / (m/τ)]
                + β2 * [(1 - exp(-m/τ)) / (m/τ) - exp(-m/τ)]

    Args:
        prices: Dict of {month_number: price}, e.g. {1: 61.5, 2: 61.2, ...}
        tau: Decay parameter (months). Default 6 for oil curves.

    Returns:
        (β0_level, β1_slope, β2_curvature) or None if insufficient data.
    """
    # Build observation vectors
    maturities = []
    observed = []
    for m in sorted(prices.keys()):
        if prices[m] is not None and not math.isnan(prices[m]):
            maturities.append(m)
            observed.append(prices[m])

    if len(maturities) < 4:
        return None

    try:
        maturities = np.array(maturities, dtype=float)
        observed = np.array(observed, dtype=float)

        # Build design matrix
        x = maturities / tau
        # Avoid division by zero for m=0
        x = np.maximum(x, 1e-6)

        factor1 = (1 - np.exp(-x)) / x
        factor2 = factor1 - np.exp(-x)

        A = np.column_stack([np.ones_like(x), factor1, factor2])

        # Least-squares fit
        result = np.linalg.lstsq(A, observed, rcond=None)
        beta = result[0]

        return float(beta[0]), float(beta[1]), float(beta[2])
    except Exception as e:
        logger.debug(f"Nelson-Siegel fit failed: {e}")
        return None


def reconstruct_ns_curve(
    beta0: float, beta1: float, beta2: float,
    tau: float = 6.0,
    n_months: int = 12,
) -> List[float]:
    """Reconstruct a curve from Nelson-Siegel parameters."""
    prices = []
    for m in range(1, n_months + 1):
        x = m / tau
        f1 = (1 - math.exp(-x)) / x
        f2 = f1 - math.exp(-x)
        p = beta0 + beta1 * f1 + beta2 * f2
        prices.append(round(p, 4))
    return prices


# ---------------------------------------------------------------------------
# Cointegration / VECM Error Correction Term
# ---------------------------------------------------------------------------

def compute_cointegration_features(
    leg1_series: np.ndarray,
    leg2_series: np.ndarray,
) -> Dict[str, float]:
    """
    Compute Cointegration / Error Correction Term (ECT) features.
    leg1 = α + β * leg2 + ε
    
    Args:
        leg1_series: e.g. WTI front month array
        leg2_series: e.g. WTI second month array or Brent array
        
    Returns:
        Dict with ect_value, ect_zscore, cointegration_beta, half_life_days
    """
    result = {
        "ect_value": 0.0,
        "ect_zscore": 0.0,
        "cointegration_beta": 1.0,
        "half_life_days": 0.0
    }
    
    n = len(leg1_series)
    if n < 30 or len(leg2_series) != n:
        return result
        
    try:
        # Fit cointegrating regression: leg1 = α + β * leg2
        A = np.vstack([leg2_series, np.ones(n)]).T
        beta, alpha = np.linalg.lstsq(A, leg1_series, rcond=None)[0]
        
        result["cointegration_beta"] = float(beta)
        
        # Calculate residuals (Error Correction Term)
        residuals = leg1_series - (alpha + beta * leg2_series)
        
        ect_value = residuals[-1]
        result["ect_value"] = float(ect_value)
        
        # Calculate ECT Z-Score
        res_mean = np.mean(residuals)
        res_std = np.std(residuals)
        if res_std > 0:
            result["ect_zscore"] = float((ect_value - res_mean) / res_std)
            
        # Estimate Ornstein-Uhlenbeck half-life using AR(1) on residuals
        # res_t - res_{t-1} = θ * res_{t-1} + ε
        if n > 1:
            res_t = residuals[1:]
            res_t_1 = residuals[:-1]
            A_ar = np.vstack([res_t_1, np.ones(n-1)]).T
            theta, _ = np.linalg.lstsq(A_ar, res_t - res_t_1, rcond=None)[0]
            
            # Half-life = -ln(2) / θ
            if theta < 0:
                half_life = -math.log(2) / theta
                # Cap half-life to avoid extreme values on near-unit roots
                result["half_life_days"] = float(min(half_life, 252.0))
                
    except np.linalg.LinAlgError:
        logger.debug("SVD did not converge in compute_cointegration_features")
    except Exception as e:
        logger.debug(f"Error in compute_cointegration_features: {e}")
        
    return result
