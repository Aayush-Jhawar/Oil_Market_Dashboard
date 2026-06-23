"""
Ornstein-Uhlenbeck Spread Analytics
======================================
Implements OU-based mean-reversion analytics for spread trading:

1. OU Parameter Estimation (θ, μ, σ) via AR(1) regression
2. Half-life computation: t_half = ln(2) / θ
3. Optimal entry/exit threshold scaling based on reversion speed
4. ADF/Engle-Granger cointegration gate

References:
    - Leung & Li, "Optimal Mean Reversion Trading" (2016)
    - Engle & Granger, "Co-integration and Error Correction" (1987)
    - arbitragelab (Hudson & Thames) reference implementation
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def estimate_ou_parameters(spread_series: List[float]) -> Dict:
    """
    Estimate Ornstein-Uhlenbeck parameters from a spread time series
    using AR(1) regression: S(t) = α + β * S(t-1) + ε

    The OU process: dS = θ(μ - S)dt + σ dW

    Mapping:
        θ = -ln(β) / Δt   (mean-reversion speed)
        μ = α / (1 - β)    (long-term mean)
        σ = std(ε) * sqrt(-2 * ln(β) / (1 - β²))
        half_life = ln(2) / θ

    Args:
        spread_series: List of spread values (at least 30 observations).

    Returns:
        Dict with ou_theta, ou_mu, ou_sigma, half_life, and diagnostics.
    """
    if len(spread_series) < 30:
        return {"error": "Need at least 30 observations for OU estimation"}

    y = np.array(spread_series, dtype=np.float64)

    # AR(1) regression: y[t] = alpha + beta * y[t-1] + epsilon
    y_t = y[1:]
    y_lag = y[:-1]

    n = len(y_t)
    x_mean = np.mean(y_lag)
    y_mean = np.mean(y_t)

    # OLS for beta and alpha
    numerator = np.sum((y_lag - x_mean) * (y_t - y_mean))
    denominator = np.sum((y_lag - x_mean) ** 2)

    if denominator == 0:
        return {"error": "Zero variance in spread series"}

    beta = numerator / denominator
    alpha = y_mean - beta * x_mean

    # Residuals
    residuals = y_t - (alpha + beta * y_lag)
    sigma_resid = float(np.std(residuals))

    # Check for mean-reversion (beta must be < 1 for stationarity)
    if beta >= 1.0:
        return {
            "ou_theta": 0.0,
            "ou_mu": float(np.mean(y)),
            "ou_sigma": sigma_resid,
            "half_life": float("inf"),
            "beta": float(beta),
            "alpha": float(alpha),
            "is_mean_reverting": False,
            "error": "Series is not mean-reverting (beta >= 1.0)",
        }

    if beta <= 0:
        # Over-differenced or very fast reversion (unusual)
        beta = max(beta, 0.001)

    # OU parameters (assuming dt = 1)
    theta = -math.log(beta)  # mean-reversion speed
    mu = alpha / (1.0 - beta)  # long-term mean
    half_life = math.log(2) / theta if theta > 0 else float("inf")

    # OU volatility
    beta_sq = beta ** 2
    if beta_sq < 1.0:
        sigma_ou = sigma_resid * math.sqrt(-2.0 * math.log(beta) / (1.0 - beta_sq))
    else:
        sigma_ou = sigma_resid

    return {
        "ou_theta": round(theta, 6),
        "ou_mu": round(mu, 4),
        "ou_sigma": round(sigma_ou, 6),
        "half_life": round(half_life, 2),
        "beta": round(float(beta), 6),
        "alpha": round(float(alpha), 6),
        "sigma_residual": round(sigma_resid, 6),
        "is_mean_reverting": beta < 1.0 and half_life < 100,
        "n_observations": n,
    }


def compute_optimal_ou_thresholds(
    theta: float,
    sigma: float,
    transaction_cost: float = 0.0,
    risk_aversion: float = 1.0,
) -> Dict:
    """
    Compute near-optimal entry/exit thresholds for an OU process
    using the analytical approximation from Leung & Li (2016).

    For a risk-neutral trader with zero transaction costs, the optimal
    entry is at ±σ/√(2θ) and exit at the mean.

    For practical use, thresholds are scaled by transaction costs and
    risk aversion.

    Args:
        theta: Mean-reversion speed.
        sigma: OU volatility.
        transaction_cost: Round-trip cost in spread points.
        risk_aversion: Risk aversion parameter (higher = wider thresholds).

    Returns:
        Dict with entry_threshold, exit_threshold (in Z-score units).
    """
    if theta <= 0 or sigma <= 0:
        return {
            "entry_zscore": 2.0,  # fallback
            "exit_zscore": 0.5,
            "method": "fallback_fixed",
        }

    # Stationary standard deviation of the OU process
    stationary_std = sigma / math.sqrt(2 * theta)

    if stationary_std <= 0:
        return {
            "entry_zscore": 2.0,
            "exit_zscore": 0.5,
            "method": "fallback_fixed",
        }

    # Optimal entry (in units of stationary std)
    # Base entry: ~1.0 std from mean for fast reversion, wider for slow
    # Adjusted for transaction costs: must exceed costs
    base_entry = 1.0 + risk_aversion * 0.5

    # Transaction cost adjustment: need at least 2x costs of edge
    if stationary_std > 0:
        cost_adjustment = (transaction_cost * 2.0) / stationary_std
    else:
        cost_adjustment = 0.0

    entry_zscore = max(1.5, base_entry + cost_adjustment)

    # Optimal exit: typically at ~0.5 std or when half the entry is recovered
    exit_zscore = max(0.0, entry_zscore * 0.25)

    # Scale by reversion speed: fast reversion → tighter thresholds
    half_life = math.log(2) / theta
    if half_life < 5:
        # Very fast reversion: tighter entry, quicker exit
        entry_zscore *= 0.8
        exit_zscore *= 0.5
    elif half_life > 20:
        # Slow reversion: wider entry, more patient exit
        entry_zscore *= 1.2
        exit_zscore *= 1.5

    return {
        "entry_zscore": round(entry_zscore, 3),
        "exit_zscore": round(exit_zscore, 3),
        "stationary_std": round(stationary_std, 4),
        "half_life": round(half_life, 2),
        "method": "ou_optimal",
    }


def adf_test(spread_series: List[float], max_lag: Optional[int] = None) -> Dict:
    """
    Augmented Dickey-Fuller test for stationarity.

    Tests H0: series has a unit root (non-stationary)
    vs H1: series is stationary (mean-reverting).

    Uses the ADF regression: ΔS(t) = α + γ·S(t-1) + Σ β_i·ΔS(t-i) + ε

    If γ < 0 and statistically significant, reject H0 → series is stationary.

    Args:
        spread_series: Time series of spread values.
        max_lag: Maximum number of lags for the ADF regression.
                 Default: int(12 * (n/100)^0.25) per Schwert (1989).

    Returns:
        Dict with adf_statistic, p_value_approx, is_stationary, and lags.
    """
    y = np.array(spread_series, dtype=np.float64)
    n = len(y)

    if n < 20:
        return {
            "adf_statistic": 0.0,
            "p_value_approx": 1.0,
            "is_stationary": False,
            "error": "Need at least 20 observations",
        }

    # Determine max lag
    if max_lag is None:
        max_lag = int(12 * (n / 100) ** 0.25)
    max_lag = min(max_lag, n // 3)

    # First differences
    dy = np.diff(y)
    y_lag = y[:-1]

    # Find optimal lag using BIC
    best_bic = float("inf")
    best_lag = 0
    best_gamma = 0.0
    best_se = 1.0

    for lag in range(0, max_lag + 1):
        if lag + 1 >= len(dy):
            break

        # Build regression matrix
        # ΔS(t) = α + γ·S(t-1) + Σ β_i·ΔS(t-i) + ε
        start = lag
        y_dep = dy[start:]
        n_obs = len(y_dep)

        if n_obs < 10:
            break

        # Regressors: constant, y(t-1), lagged differences
        X = np.ones((n_obs, 2 + lag))
        X[:, 1] = y_lag[start: start + n_obs]

        for i in range(lag):
            if start - i - 1 >= 0:
                X[:, 2 + i] = dy[start - i - 1: start - i - 1 + n_obs]

        # OLS
        try:
            XtX_inv = np.linalg.inv(X.T @ X)
            betas = XtX_inv @ X.T @ y_dep
            residuals = y_dep - X @ betas
            sigma_sq = np.sum(residuals ** 2) / (n_obs - X.shape[1])

            # BIC
            bic = n_obs * np.log(sigma_sq) + X.shape[1] * np.log(n_obs)

            if bic < best_bic:
                best_bic = bic
                best_lag = lag
                best_gamma = betas[1]
                # Standard error of gamma
                best_se = float(np.sqrt(sigma_sq * XtX_inv[1, 1]))
        except np.linalg.LinAlgError:
            continue

    if best_se <= 0:
        best_se = 1e-10

    adf_stat = best_gamma / best_se

    # Approximate p-value using MacKinnon critical values (constant, no trend)
    # Critical values for n > 250:
    # 1%: -3.43, 5%: -2.86, 10%: -2.57
    if adf_stat < -3.43:
        p_approx = 0.01
    elif adf_stat < -2.86:
        p_approx = 0.05
    elif adf_stat < -2.57:
        p_approx = 0.10
    elif adf_stat < -1.94:
        p_approx = 0.30
    elif adf_stat < -1.62:
        p_approx = 0.50
    else:
        p_approx = 0.90

    return {
        "adf_statistic": round(float(adf_stat), 4),
        "p_value_approx": p_approx,
        "is_stationary": p_approx < 0.10,
        "optimal_lag": best_lag,
        "gamma": round(float(best_gamma), 6),
        "n_observations": n,
        "critical_values": {"1%": -3.43, "5%": -2.86, "10%": -2.57},
    }


def spread_trading_analytics(
    hist_spreads: List[float],
    current_spread: float,
    transaction_cost_pts: float = 0.027,
    max_holding_periods: int = 500,
) -> Dict:
    """
    Full spread trading analytics combining OU estimation, ADF testing,
    optimal thresholds, and trade viability assessment.

    This is designed to be called from generate_spread_signal() as a
    pre-trade gate and threshold optimizer.

    Args:
        hist_spreads: Historical spread values (most recent last).
        current_spread: Current spread level.
        transaction_cost_pts: Round-trip transaction cost in spread points.
        max_holding_periods: Maximum holding period in periods.

    Returns:
        Dict with OU params, ADF results, optimal thresholds, and viability.
    """
    result = {
        "is_viable": False,
        "veto_reason": None,
    }

    # 1. ADF stationarity test
    adf_result = adf_test(hist_spreads)
    result["adf"] = adf_result

    if not adf_result.get("is_stationary", False):
        result["veto_reason"] = (
            f"Spread is not stationary (ADF p={adf_result.get('p_value_approx', 1.0):.2f}). "
            f"Cointegration not confirmed."
        )
        # Still compute OU params for informational purposes
        ou_result = estimate_ou_parameters(hist_spreads)
        result["ou"] = ou_result
        return result

    # 2. OU parameter estimation
    ou_result = estimate_ou_parameters(hist_spreads)
    result["ou"] = ou_result

    if ou_result.get("error"):
        result["veto_reason"] = f"OU estimation failed: {ou_result['error']}"
        return result

    if not ou_result.get("is_mean_reverting", False):
        result["veto_reason"] = "OU model indicates no mean reversion"
        return result

    half_life = ou_result.get("half_life", float("inf"))

    # 3. Half-life viability check
    if half_life > max_holding_periods:
        result["veto_reason"] = (
            f"Half-life ({half_life:.1f} periods) exceeds max holding period "
            f"({max_holding_periods} periods)"
        )
        return result

    if half_life < 2:
        result["veto_reason"] = (
            f"Half-life too short ({half_life:.1f} periods) — likely noise, not signal"
        )
        return result

    # 4. Compute optimal thresholds
    thresholds = compute_optimal_ou_thresholds(
        theta=ou_result["ou_theta"],
        sigma=ou_result["ou_sigma"],
        transaction_cost=transaction_cost_pts,
    )
    result["thresholds"] = thresholds

    # 5. Current Z-score relative to OU mean
    ou_mu = ou_result["ou_mu"]
    stationary_std = thresholds.get("stationary_std", 1.0)
    if stationary_std > 0:
        current_zscore = (current_spread - ou_mu) / stationary_std
    else:
        current_zscore = 0.0
    result["current_zscore"] = round(current_zscore, 4)

    # 6. Trade viability
    result["is_viable"] = True
    result["veto_reason"] = None

    return result
