"""
Rule-Based Regime Classifier
===============================
Deterministic classification of the oil market regime using futures curve
shape metrics. This provides the "economic intuition" anchor that prevents
the HMM from drifting into non-physical states.

Five Regimes:
    EXTREME_BACKWARDATION — Deep front premium: severe physical tightness,
                            supply disruption, panic buying
    BACKWARDATION         — Front premium: physical tightness, draws,
                            strong demand
    NEUTRAL               — Flat curve: balanced market
    CONTANGO              — Front discount: oversupply, builds, weak demand
    EXTREME_CONTANGO      — Deep front discount: storage economics dominate,
                            severe oversupply (e.g. COVID-era)

Severity: Continuous [0, 1] score within each regime, measuring intensity.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


ALL_REGIMES = [
    "EXTREME_BACKWARDATION",
    "BACKWARDATION",
    "NEUTRAL",
    "CONTANGO",
    "EXTREME_CONTANGO",
]

REGIME_ENCODING = {label: i for i, label in enumerate(ALL_REGIMES)}


@dataclass
class RegimeClassification:
    """Result of rule-based regime classification."""
    label: str                    # One of ALL_REGIMES
    severity: float               # 0.0–1.0 (higher = more extreme within the regime)
    m1_m12_spread: float          # Raw input
    m1_m2_spread: float           # Raw input
    drivers: list                 # Human-readable explanation of classification


# Thresholds calibrated to ~2010–2025 WTI data
_EXTREME_BACK_M1_M12 = 5.0    # $/bbl — deep front premium
_EXTREME_BACK_M1_M2  = 0.50   # $/bbl
_BACK_M1_M12         = 2.0    # $/bbl — moderate front premium
_BACK_M1_M2          = 0.15   # $/bbl
_CONTANGO_M1_M12     = -2.0   # $/bbl
_CONTANGO_M1_M2      = -0.15  # $/bbl
_EXTREME_CONT_M1_M12 = -5.0   # $/bbl — deep front discount
_EXTREME_CONT_M1_M2  = -0.50  # $/bbl
_SEVERITY_NORMALIZER = 10.0   # spread at which within-regime severity = 1.0


def classify_regime(
    m1_m12_spread: float,
    m1_m2_spread: float,
    front_carry: Optional[float] = None,
    fly_1_6_11: Optional[float] = None,
    realized_vol: Optional[float] = None,
) -> RegimeClassification:
    """
    Classify the current market regime from curve shape metrics.

    Args:
        m1_m12_spread: M1 - M12 price difference (negative = backwardation)
        m1_m2_spread: M1 - M2 price difference
        front_carry: Annualized front carry % (optional, used for severity)
        fly_1_6_12: M1 - 2*M6 + M12 butterfly (optional, curvature signal)
        realized_vol: 20d realized volatility (optional, stress indicator)

    Returns:
        RegimeClassification with label, severity, and explanation.
    """
    drivers = []

    # ── Primary classification (ordered from most extreme to neutral) ─────
    if m1_m12_spread > _EXTREME_BACK_M1_M12:
        label = "EXTREME_BACKWARDATION"
        # Severity within extreme-backwardation: how far beyond the threshold
        base_severity = min(1.0, (m1_m12_spread - _EXTREME_BACK_M1_M12) / _SEVERITY_NORMALIZER + 0.5)
        drivers.append(
            f"Extreme backwardation: M1-M12={m1_m12_spread:+.2f}, "
            f"M1-M2={m1_m2_spread:+.2f} — severe physical tightness"
        )

    elif m1_m12_spread > _BACK_M1_M12:
        label = "BACKWARDATION"
        base_severity = min(1.0, m1_m12_spread / _EXTREME_BACK_M1_M12)
        drivers.append(
            f"Curve in backwardation: M1-M12={m1_m12_spread:+.2f}, "
            f"M1-M2={m1_m2_spread:+.2f}"
        )

    elif m1_m12_spread < _EXTREME_CONT_M1_M12:
        label = "EXTREME_CONTANGO"
        base_severity = min(1.0, (abs(m1_m12_spread) - abs(_EXTREME_CONT_M1_M12)) / _SEVERITY_NORMALIZER + 0.5)
        drivers.append(
            f"Extreme contango: M1-M12={m1_m12_spread:+.2f}, "
            f"M1-M2={m1_m2_spread:+.2f} — storage economics dominate"
        )

    elif m1_m12_spread < _CONTANGO_M1_M12:
        label = "CONTANGO"
        base_severity = min(1.0, abs(m1_m12_spread) / abs(_EXTREME_CONT_M1_M12))
        drivers.append(
            f"Curve in contango: M1-M12={m1_m12_spread:+.2f}, "
            f"M1-M2={m1_m2_spread:+.2f}"
        )

    else:
        label = "NEUTRAL"
        base_severity = min(1.0, abs(m1_m12_spread) / _BACK_M1_M12)
        drivers.append(
            f"Curve relatively flat: M1-M12={m1_m12_spread:+.2f}, "
            f"M1-M2={m1_m2_spread:+.2f}"
        )

    # ── Severity adjustments ──────────────────────────────────────────────
    severity = base_severity

    # Front carry adds conviction to backwardation/contango regimes
    if front_carry is not None:
        if label in ("BACKWARDATION", "EXTREME_BACKWARDATION") and front_carry > 5:
            severity = min(1.0, severity + 0.1)
            drivers.append(f"Strong front carry of {front_carry:.1f}% annualized")
        elif label in ("CONTANGO", "EXTREME_CONTANGO") and front_carry < -5:
            severity = min(1.0, severity + 0.1)
            drivers.append(f"Deep negative carry of {front_carry:.1f}% annualized")

    # Fly curvature adds information about curve shape
    if fly_1_6_11 is not None:
        if label in ("BACKWARDATION", "EXTREME_BACKWARDATION") and fly_1_6_11 > 1.0:
            severity = min(1.0, severity + 0.05)
            drivers.append(f"Positive curve convexity (fly={fly_1_6_11:.2f})")
        elif label in ("CONTANGO", "EXTREME_CONTANGO") and fly_1_6_11 < -1.0:
            severity = min(1.0, severity + 0.05)
            drivers.append(f"Negative curve convexity (fly={fly_1_6_11:.2f})")

    # High vol environments amplify regime severity
    if realized_vol is not None and realized_vol > 35:
        severity = min(1.0, severity + 0.1)
        drivers.append(f"Elevated volatility ({realized_vol:.0f}%) amplifying regime")

    return RegimeClassification(
        label=label,
        severity=round(severity, 3),
        m1_m12_spread=m1_m12_spread,
        m1_m2_spread=m1_m2_spread,
        drivers=drivers,
    )


def classify_regime_from_features(features: Dict[str, float]) -> RegimeClassification:
    """
    Convenience wrapper: classify regime from a feature dict.
    """
    m1_m12 = features.get("m1_m12_spread", 0.0)
    m1_m2 = features.get("m1_m2_spread", 0.0)
    carry = features.get("front_carry_annualized")
    fly = features.get("fly_1_6_12")
    vol = features.get("realized_vol_20d")

    return classify_regime(m1_m12, m1_m2, carry, fly, vol)
