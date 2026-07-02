"""Model-driven composite score.

Turns a trained directional probability into the [-100, +100] gauge value the
frontend already consumes, blended with the existing technical score and a
carefully-bounded news-sentiment overlay. Returns the SAME dict shape the
Overview card reads (composite_score / regime / signal / confidence /
factor_scores / sub_scores / weights) plus a few `model_*` keys, so nothing
downstream breaks — the number just becomes meaningful instead of ~0.

Why this fixes "stuck at 0-3": the legacy multi-factor score averages
trend-following against mean-reversion factors that cancel out. Here the
headline is anchored on the model's directional edge; the technical score is
demoted to a 25% adjustment (and still exposed as the factor breakdown), so it
informs but can no longer cancel the signal to zero.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Blend weights (model-anchored). News is a bounded overlay, not a driver.
W_MODEL = 0.65
W_TECH = 0.25
W_NEWS = 0.10                 # 0.10 * (news*100) -> at most +/-10 net
DEADBAND_EDGE = 0.04          # |p-0.5| below this -> NEUTRAL signal + damp
HIGH_CONF_EDGE = 0.12         # news may not flip a signal this confident
NEWS_STALE_START_H = 24.0     # begin decaying the overlay after 24h
NEWS_STALE_ZERO_H = 72.0      # fully decayed (weight 0) by 72h


def _clamp(v: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _news_component(news_sentiment: Optional[float], age_hours: Optional[float]) -> float:
    """Bounded, staleness-decayed news contribution in [-100, 100] (pre-weight).

    Edge cases: None/NaN/no-articles -> 0. Values clamped to [-1, 1]. Older than
    24h decays linearly to 0 by 72h. The W_NEWS weight then caps the net effect
    at +/-10.
    """
    if news_sentiment is None:
        return 0.0
    try:
        s = float(news_sentiment)
    except (TypeError, ValueError):
        return 0.0
    if s != s:  # NaN
        return 0.0
    s = max(-1.0, min(1.0, s))
    if age_hours is not None and age_hours > NEWS_STALE_START_H:
        if age_hours >= NEWS_STALE_ZERO_H:
            return 0.0
        decay = 1.0 - (age_hours - NEWS_STALE_START_H) / (NEWS_STALE_ZERO_H - NEWS_STALE_START_H)
        s *= max(0.0, decay)
    return s * 100.0


def _signal_from_score(score: float) -> str:
    if score > 40:
        return "STRONG_BUY"
    if score > 15:
        return "BUY"
    if score < -40:
        return "STRONG_SELL"
    if score < -15:
        return "SELL"
    return "NEUTRAL"


def get_composite(
    symbol: str,
    horizon: str = "5d",
    tech_result: Optional[Dict] = None,
    news_sentiment: Optional[float] = None,
    news_age_hours: Optional[float] = None,
) -> Optional[Dict]:
    """Model-driven composite for one symbol. Returns None if the ML module
    isn't importable (caller then keeps its legacy path)."""
    try:
        from ml.inference import predict_prob
    except Exception as e:  # ml package missing/broken -> let caller fall back
        logger.debug("composite_score: ml.inference unavailable: %s", e)
        return None

    tech_result = tech_result or {}
    tech_score = float(tech_result.get("composite_score", 0.0) or 0.0)
    news_raw = _news_component(news_sentiment, news_age_hours)

    pred = predict_prob(symbol, horizon)

    # ── No model for this symbol/horizon: preserve contract, keep tech score ──
    if pred is None:
        out = dict(tech_result)
        out.update({
            "composite_score": round(tech_score, 1),
            "model_prob": None, "model_score": None, "tech_score": round(tech_score, 1),
            "news_component": round(W_NEWS * news_raw, 2),
            "model_name": None, "model_horizon": horizon, "model_oos_accuracy": None,
            "model_available": False,
        })
        return out

    p = pred["p_up"]
    edge = p - 0.5
    model_score = _clamp(edge * 200.0)

    base = W_MODEL * model_score + W_TECH * tech_score
    news_contrib = W_NEWS * news_raw
    composite = base + news_contrib

    # High-confidence guard: news may nudge but never flip a confident model call.
    if abs(edge) >= HIGH_CONF_EDGE and model_score != 0 and _sign(composite) != _sign(model_score):
        composite = base

    composite = _clamp(composite)

    # Dead-band: near-coin-flip edge -> force NEUTRAL and damp toward zero.
    in_deadband = abs(edge) < DEADBAND_EDGE
    if in_deadband:
        composite *= 0.5

    signal = "NEUTRAL" if in_deadband else _signal_from_score(composite)
    regime = "BULLISH" if composite > 20 else "BEARISH" if composite < -20 else "NEUTRAL"
    confidence = max(0.0, min(1.0, abs(edge) * 2.0))

    out = dict(tech_result)  # carry factor_scores / sub_scores / weights / regime_type
    out.update({
        "composite_score": round(composite, 1),
        "regime": regime,
        "signal": signal,
        "confidence": round(confidence, 3),
        "model_prob": round(p, 4),
        "model_score": round(model_score, 1),
        "tech_score": round(tech_score, 1),
        "news_component": round(news_contrib, 2),
        "model_name": pred["model_name"],
        "model_horizon": horizon,
        "model_oos_accuracy": pred["oos_accuracy"],
        "model_underperforms": pred["underperforms"],
        "model_available": True,
    })
    return out
