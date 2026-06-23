"""
Fractional Kelly Position Sizing
==================================
Implements optimal position sizing based on Kelly Criterion (1956),
adapted for energy commodity trading with professional risk controls.

Key Principles:
    - Full Kelly maximizes geometric growth rate but is too aggressive
    - Fractional Kelly (1/4 to 1/2) significantly reduces drawdowns
      while sacrificing only ~20% of theoretical optimal growth
    - Combined with volatility targeting for portfolio-level risk control
    - ATR-based stop distance directly feeds into sizing

References:
    - Kelly, J.L. (1956). "A New Interpretation of Information Rate"
    - Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting,
      and the Stock Market"
"""
from __future__ import annotations

import math
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def kelly_fraction(
    prob_win: float,
    risk_reward_ratio: float,
) -> float:
    """
    Calculate the full Kelly fraction.

    f* = (b * p - q) / b

    Where:
        b = risk_reward_ratio (reward / risk)
        p = probability of winning
        q = 1 - p (probability of losing)

    Args:
        prob_win: Estimated probability of the trade being profitable (0-1).
        risk_reward_ratio: Ratio of expected reward to risk (target / stop).

    Returns:
        Full Kelly fraction (can be negative = don't trade).
    """
    if risk_reward_ratio <= 0 or prob_win <= 0 or prob_win >= 1:
        return 0.0

    b = risk_reward_ratio
    p = prob_win
    q = 1.0 - p

    f = (b * p - q) / b
    return f


def fractional_kelly_position_size(
    prob_win: float,
    risk_reward_ratio: float,
    portfolio_equity: float,
    atr: float,
    contract_multiplier: float = 1000.0,
    stop_atr_multiple: float = 2.0,
    kelly_fraction_pct: float = 0.25,
    max_risk_per_trade_pct: float = 0.01,
    max_position_pct: float = 0.03,
    regime_stability: float = 1.0,
    vol_scalar: float = 1.0,
) -> Dict:
    """
    Calculate position size using Fractional Kelly with risk controls.

    The sizing is computed in three layers:
        1. Kelly Layer: Fractional Kelly based on probability and R:R
        2. Risk Budget Layer: Max % of equity at risk per trade
        3. Volatility Layer: Scale down in high-vol environments

    Args:
        prob_win: Estimated probability of winning (0.0 to 1.0).
        risk_reward_ratio: Reward/risk ratio from target and stop.
        portfolio_equity: Current total portfolio equity in $.
        atr: Current ATR (in price points).
        contract_multiplier: Dollar value per point per contract (e.g., 1000 for CL).
        stop_atr_multiple: Stop loss distance as multiple of ATR.
        kelly_fraction_pct: Fraction of full Kelly to use (0.25 = quarter Kelly).
        max_risk_per_trade_pct: Maximum equity % risked per trade (hard cap).
        max_position_pct: Maximum position as % of equity (notional cap).
        regime_stability: Regime stability score (0-1, higher = more stable).
        vol_scalar: Volatility regime scalar (< 1 in high vol).

    Returns:
        Dict with sizing details and all intermediate calculations.
    """
    # ── Layer 1: Kelly Fraction ──────────────────────────────────────────
    full_kelly = kelly_fraction(prob_win, risk_reward_ratio)

    # Apply fractional Kelly
    adjusted_kelly = full_kelly * kelly_fraction_pct

    # Apply regime stability modifier (reduce size in transitions)
    stability_modifier = max(0.3, min(1.0, regime_stability))
    adjusted_kelly *= stability_modifier

    # Apply volatility scalar
    adjusted_kelly *= vol_scalar

    # Floor at zero (don't trade if Kelly is negative)
    if adjusted_kelly <= 0:
        return _no_position("Kelly fraction is negative or zero", full_kelly, adjusted_kelly)

    # ── Layer 2: Risk Budget (max $ at risk) ─────────────────────────────
    max_risk_dollars = portfolio_equity * max_risk_per_trade_pct
    stop_distance_points = atr * stop_atr_multiple
    risk_per_contract = stop_distance_points * contract_multiplier

    if risk_per_contract <= 0:
        return _no_position("Risk per contract is zero", full_kelly, adjusted_kelly)

    contracts_from_risk = max_risk_dollars / risk_per_contract

    # ── Layer 3: Kelly-sized contracts ───────────────────────────────────
    # Kelly suggests risking `adjusted_kelly` fraction of equity
    kelly_risk_dollars = portfolio_equity * adjusted_kelly
    contracts_from_kelly = kelly_risk_dollars / risk_per_contract

    # Take the minimum of Kelly-sized and risk-budgeted
    contracts = min(contracts_from_kelly, contracts_from_risk)

    # Apply notional cap
    current_price_approx = atr * 20  # rough price estimate from ATR
    notional_per_contract = current_price_approx * contract_multiplier
    max_contracts_notional = (portfolio_equity * max_position_pct) / notional_per_contract if notional_per_contract > 0 else contracts

    contracts = min(contracts, max_contracts_notional)

    # Floor at 1 contract minimum if Kelly says trade
    contracts = max(1, int(contracts))

    # ── Compute final risk metrics ───────────────────────────────────────
    actual_risk_dollars = contracts * risk_per_contract
    actual_risk_pct = actual_risk_dollars / portfolio_equity if portfolio_equity > 0 else 0
    position_pct = (contracts * notional_per_contract) / portfolio_equity if portfolio_equity > 0 else 0

    return {
        "contracts": contracts,
        "position_size_pct": round(position_pct, 6),
        "risk_per_trade_pct": round(actual_risk_pct, 6),
        "risk_per_trade_dollars": round(actual_risk_dollars, 2),
        "stop_distance_points": round(stop_distance_points, 4),
        "risk_per_contract": round(risk_per_contract, 2),
        # Kelly details
        "full_kelly_fraction": round(full_kelly, 6),
        "adjusted_kelly_fraction": round(adjusted_kelly, 6),
        "kelly_fraction_used": kelly_fraction_pct,
        # Modifiers
        "regime_stability_modifier": round(stability_modifier, 4),
        "vol_scalar": round(vol_scalar, 4),
        # Constraints applied
        "limited_by": _identify_binding_constraint(
            contracts_from_kelly, contracts_from_risk, max_contracts_notional
        ),
    }


def compute_vol_scalar(
    realized_vol: Optional[float] = None,
    vix: Optional[float] = None,
) -> float:
    """
    Compute a volatility scalar for position sizing.

    Reduces position size in high-volatility environments.
    Uses realized vol primarily, VIX as fallback.

    Returns:
        Scalar in [0.3, 1.0]
    """
    vol = realized_vol
    if vol is None and vix is not None:
        # Convert VIX to approximate realized vol
        vol = vix / 100.0 * math.sqrt(252)

    if vol is None:
        return 1.0

    # Convert to annualized % if needed
    if vol < 1.0:
        vol *= 100  # assume it was in decimal

    # Tiered scaling
    if vol > 50:
        return 0.3
    elif vol > 40:
        return 0.5
    elif vol > 30:
        return 0.65
    elif vol > 25:
        return 0.8
    elif vol > 20:
        return 0.9
    else:
        return 1.0


def _no_position(reason: str, full_kelly: float, adjusted_kelly: float) -> Dict:
    """Return a zero-position result."""
    return {
        "contracts": 0,
        "position_size_pct": 0.0,
        "risk_per_trade_pct": 0.0,
        "risk_per_trade_dollars": 0.0,
        "stop_distance_points": 0.0,
        "risk_per_contract": 0.0,
        "full_kelly_fraction": round(full_kelly, 6),
        "adjusted_kelly_fraction": round(adjusted_kelly, 6),
        "kelly_fraction_used": 0.0,
        "regime_stability_modifier": 0.0,
        "vol_scalar": 0.0,
        "limited_by": reason,
    }


def _identify_binding_constraint(
    kelly_contracts: float,
    risk_contracts: float,
    notional_contracts: float,
) -> str:
    """Identify which constraint limited the position size."""
    min_val = min(kelly_contracts, risk_contracts, notional_contracts)
    if min_val == kelly_contracts:
        return "kelly"
    elif min_val == risk_contracts:
        return "risk_budget"
    else:
        return "notional_cap"
