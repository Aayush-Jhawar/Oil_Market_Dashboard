"""Multi-Factor Signal Engine for Energy Commodities.

Replaces the simplistic single-factor composite score (EMA binary + fake inputs)
with a professional 12-factor normalized model combining:

  TREND FACTORS (40% default)
    1. trend_ema       — EMA20/50 crossover + slope magnitude
    2. trend_macd      — MACD histogram, normalized by price
    3. trend_adx       — ADX directional strength (not a direction signal)

  VOLATILITY / BAND FACTORS (20% default)
    4. bb_pct_b        — Bollinger %B: where price sits within the band
    5. atr_pct         — ATR as % of price (vol regime sizing input)

  MEAN REVERSION FACTORS (15% default)
    6. mean_rev_zscore — Price z-score vs 20D rolling mean (inverted)
    7. rsi_normalized  — RSI(14) normalized to [-1, +1]: >70 → bearish, <30 → bullish

  MOMENTUM FACTORS (15% default)
    8. momentum_roc    — 14-day Rate of Change, z-scored over 60-day window

  MACRO FACTORS (10% default)
    9. macro_dxy       — DXY direction (inverted: strong dollar = bearish oil)
   10. macro_risk      — Equity risk proxy: SPX direction, VIX inverse

  FUNDAMENTAL FACTORS (included in composite when data available)
   11. fundamentals_eia   — EIA weekly inventory surprise vs 5yr avg
   12. fundamentals_cftc  — CFTC COT z-score (contrarian: extreme long = bearish)

REGIME DETECTION
  Markets are classified as TRENDING, RANGING, or HIGH_VOL based on ADX and
  realized volatility. Weights are dynamically adjusted per regime.

All factor scores are normalized to [-1.0, +1.0] before weighting.
The final composite score is in [-100, +100].
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

from signal_calc import SignalCalculator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default factor weights (must sum to 1.0)
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: Dict[str, float] = {
    "trend_ema":         0.15,
    "trend_macd":        0.10,
    "trend_adx":         0.05,
    "bb_pct_b":          0.08,
    "atr_pct":           0.00,
    "mean_rev_zscore":   0.08,
    "rsi_normalized":    0.08,
    "momentum_roc":      0.08,
    "macro_dxy":         0.07,
    "macro_risk":        0.06,
    "fundamentals_eia":  0.05,
    "fundamentals_cftc": 0.05,
    "ai_prediction":     0.15,
}

# Regime-specific weight overrides
REGIME_WEIGHTS: Dict[str, Dict[str, float]] = {
    "TRENDING": {
        "trend_ema":         0.20,
        "trend_macd":        0.15,
        "trend_adx":         0.05,
        "bb_pct_b":          0.05,
        "atr_pct":           0.00,
        "mean_rev_zscore":   0.05,
        "rsi_normalized":    0.05,
        "momentum_roc":      0.10,
        "macro_dxy":         0.06,
        "macro_risk":        0.04,
        "fundamentals_eia":  0.05,
        "fundamentals_cftc": 0.05,
        "ai_prediction":     0.15,
    },
    "RANGING": {
        "trend_ema":         0.10,
        "trend_macd":        0.08,
        "trend_adx":         0.02,
        "bb_pct_b":          0.10,
        "atr_pct":           0.00,
        "mean_rev_zscore":   0.15,
        "rsi_normalized":    0.15,
        "momentum_roc":      0.05,
        "macro_dxy":         0.06,
        "macro_risk":        0.04,
        "fundamentals_eia":  0.05,
        "fundamentals_cftc": 0.05,
        "ai_prediction":     0.15,
    },
    "HIGH_VOL": {
        "trend_ema":         0.10,
        "trend_macd":        0.08,
        "trend_adx":         0.05,
        "bb_pct_b":          0.08,
        "atr_pct":           0.00,
        "mean_rev_zscore":   0.10,
        "rsi_normalized":    0.10,
        "momentum_roc":      0.08,
        "macro_dxy":         0.08,
        "macro_risk":        0.08,
        "fundamentals_eia":  0.05,
        "fundamentals_cftc": 0.05,
        "ai_prediction":     0.15,
    },
}


# ---------------------------------------------------------------------------
# Individual factor calculators (all return scores in [-1.0, +1.0])
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _safe_div(num: float, denom: float, fallback: float = 0.0) -> float:
    return num / denom if denom != 0 else fallback


def factor_trend_ema(prices: List[float]) -> Optional[float]:
    """EMA20/50 crossover + slope of EMA20."""
    if len(prices) < 51:
        return None
    ema20_series = SignalCalculator.ema_series(prices, 20)
    ema50_series = SignalCalculator.ema_series(prices, 50)
    ema20 = ema20_series[-1]
    ema50 = ema50_series[-1]
    if ema20 is None or ema50 is None:
        return None

    direction = 1.0 if ema20 > ema50 else -1.0
    diff_pct = _safe_div(ema20 - ema50, ema50) * 100   # e.g. +2.5%
    magnitude = _clamp(diff_pct / 5.0, -0.5, 0.5)     # ±5% diff → full score

    # EMA20 slope: compare last 5 ema20 values
    slope = 0.0
    if len(ema20_series) >= 5 and ema20_series[-5] is not None:
        slope_raw = ema20 - ema20_series[-5]
        slope_pct = _safe_div(slope_raw, ema20_series[-5]) * 100
        slope = _clamp(slope_pct / 2.0, -0.5, 0.5)

    return _clamp(direction * 0.5 + magnitude * 0.3 + slope * 0.2)


def factor_trend_macd(prices: List[float]) -> Optional[float]:
    """MACD histogram normalized by price."""
    macd_res = SignalCalculator.calculate_macd(prices)
    histogram = macd_res.get("histogram")
    if histogram is None:
        return None

    price_ref = prices[-1] if prices[-1] != 0 else 1.0
    normalized = histogram / price_ref * 500   # scale: 0.2% of price → score 1.0
    return _clamp(normalized)


def factor_adx(candles: List[Dict]) -> Tuple[float, str]:
    """ADX directional strength.

    Returns (adx_value, trend_type) where trend_type is:
      'TRENDING' if ADX > 25, 'RANGING' otherwise.
    ADX itself is not a directional score — it's used for regime detection.
    """
    if len(candles) < 28:
        return 0.0, "RANGING"

    highs  = [float(c.get("high", 0)) for c in candles]
    lows   = [float(c.get("low", 0)) for c in candles]
    closes = [float(c.get("close", 0)) for c in candles]

    period = 14
    dm_plus_list, dm_minus_list, tr_list = [], [], []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        dm_plus_list.append(up if up > down and up > 0 else 0)
        dm_minus_list.append(down if down > up and down > 0 else 0)
        h, l, pc = highs[i], lows[i], closes[i - 1]
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))

    if len(tr_list) < period:
        return 0.0, "RANGING"

    atr = sum(tr_list[:period])
    adm_plus = sum(dm_plus_list[:period])
    adm_minus = sum(dm_minus_list[:period])

    dx_series = []
    for i in range(period, len(tr_list)):
        atr = atr - atr / period + tr_list[i]
        adm_plus = adm_plus - adm_plus / period + dm_plus_list[i]
        adm_minus = adm_minus - adm_minus / period + dm_minus_list[i]
        di_plus  = 100 * adm_plus / atr if atr else 0
        di_minus = 100 * adm_minus / atr if atr else 0
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) else 0
        dx_series.append(dx)

    if not dx_series:
        return 0.0, "RANGING"

    adx = sum(dx_series[-14:]) / min(14, len(dx_series))
    regime = "TRENDING" if adx > 25 else "RANGING"
    return round(adx, 1), regime


def factor_bb_pct_b(prices: List[float], period: int = 20) -> Optional[float]:
    """Bollinger %B normalized to [-1, +1]."""
    bb = SignalCalculator.calculate_bollinger_bands(prices, period)
    if not bb or "lower" not in bb or "width" not in bb:
        return None
    lower = bb["lower"]
    band_width = bb["width"]
    if band_width == 0:
        return None
    pct_b = (prices[-1] - lower) / band_width   # 0 to 1 (can exceed)
    # Map: pct_b=1.0 → -1.0 (extended), pct_b=0.0 → +1.0 (oversold)
    score = 1.0 - 2.0 * pct_b
    return _clamp(score)


def factor_atr_pct(candles: List[Dict], period: int = 14) -> Optional[float]:
    """ATR as percentage of price. Used for vol regime sizing, not directional."""
    atrs = SignalCalculator.calculate_atr(candles, period)
    if not atrs or atrs[-1] is None:
        return None
    price = float(candles[-1].get("close", 1))
    return round(atrs[-1] / price * 100, 3) if price else 0.0


def factor_mean_rev_zscore(prices: List[float], window: int = 20) -> Optional[float]:
    """Price z-score vs rolling 20D mean, inverted for directional signal."""
    z = SignalCalculator.calculate_price_zscore(prices, window)
    if z is None:
        return None
    # Invert: high z → bearish
    score = -z / 3.0   # 3-sigma → full score
    return _clamp(score)


def factor_rsi_normalized(prices: List[float], period: int = 14) -> Optional[float]:
    """RSI(14) normalized to [-1, +1]."""
    rsi = SignalCalculator.calculate_rsi(prices, period)
    if rsi is None:
        return None
    # Normalize: 70→-1, 50→0, 30→+1
    score = (50.0 - rsi) / 20.0   # ±20 RSI units → ±1 score
    return _clamp(score)


def factor_momentum_roc(prices: List[float], period: int = 14, norm_window: int = 60) -> Optional[float]:
    """14-day Rate of Change, z-scored over a 60-day window."""
    roc_series = []
    # Calculate ROC over the rolling window to build the series for z-scoring
    for i in range(len(prices)):
        roc = SignalCalculator.calculate_momentum_roc(prices[:i+1], period)
        if roc is not None:
            roc_series.append(roc)

    if len(roc_series) < 2:
        return None

    window = roc_series[-norm_window:]
    mean = sum(window) / len(window)
    std = (sum((r - mean) ** 2 for r in window) / len(window)) ** 0.5
    if std == 0:
        return None
    latest_roc = roc_series[-1]
    z = (latest_roc - mean) / std
    return _clamp(z / 2.0)   # ±2 sigma → full score


def factor_macro_dxy(dxy_change_pct: Optional[float]) -> Optional[float]:
    """DXY direction — inverted. Strong dollar is bearish for oil."""
    if dxy_change_pct is None:
        return None
    return _clamp(-dxy_change_pct / 1.0 * 0.8)   # ±1% daily move → ±0.8


def factor_macro_risk(spx_change_pct: Optional[float], vix: Optional[float]) -> Optional[float]:
    """Equity risk appetite proxy for crude oil."""
    if spx_change_pct is None and vix is None:
        return None

    spx_score = 0.0
    if spx_change_pct is not None:
        spx_score = _clamp(spx_change_pct / 2.0)  # ±2% SPX → ±1 score

    vix_score = 0.0
    if vix is not None:
        # VIX > 25: bearish, < 15: bullish neutral, 15-25: between
        vix_score = _clamp((20.0 - vix) / 10.0)   # 10 VIX → +1, 30 VIX → -1

    if spx_change_pct is None:
        return vix_score
    if vix is None:
        return spx_score
    return _clamp(0.6 * spx_score + 0.4 * vix_score)


def factor_eia_surprise(eia_data: Optional[Dict]) -> Optional[float]:
    """EIA weekly inventory surprise vs 5-year average."""
    if not eia_data:
        return None
    crude = eia_data.get("crude_inventory") or eia_data.get("crude_level") or {}
    current = crude.get("current_value")
    five_yr = crude.get("five_year_avg")
    wow = crude.get("wow_change")

    if current is None or five_yr is None:
        if wow is not None:
            return _clamp(-wow / 5.0)  # -5mb WoW draw → +1 score
        return None

    delta_vs_5yr = current - five_yr   # positive = above 5yr avg = bearish
    return _clamp(-delta_vs_5yr / 30.0)   # 30mb above 5yr → full bearish


def factor_cftc_contrarian(cftc_data: Optional[Dict], symbol: str) -> Optional[float]:
    """CFTC Managed Money positioning proxy."""
    if not cftc_data or symbol not in cftc_data:
        return None
    
    mm_net = cftc_data[symbol].get("mm_net")
    open_interest = cftc_data[symbol].get("open_interest")
    
    if mm_net is None or not open_interest:
        return None
    # Historical WTI MM net long range: roughly -50k to +500k
    # Normalize: center at 225k midpoint, ±275k = full score
    normalized = (mm_net - 225000) / 275000
    return _clamp(-normalized)   # inverted: high = bearish


# ---------------------------------------------------------------------------
# Regime Detection
# ---------------------------------------------------------------------------

def detect_regime(
    candles: List[Dict],
    annual_vol_pct: float,
) -> str:
    """Classify market regime using ADX + realized volatility.

    Returns: 'TRENDING', 'RANGING', or 'HIGH_VOL'
    """
    if annual_vol_pct > 40:
        return "HIGH_VOL"
    _, adx_regime = factor_adx(candles)
    return adx_regime   # 'TRENDING' or 'RANGING'


# ---------------------------------------------------------------------------
# Relative Strength Ranking
# ---------------------------------------------------------------------------

def calculate_relative_strength(symbol_prices: Dict[str, List[float]], period: int = 20) -> Dict[str, float]:
    """Rank commodities by recent momentum (period-day return).

    Returns normalized score in [-1, +1] for each symbol.
    """
    if not symbol_prices:
        return {}
    returns = {}
    for sym, prices in symbol_prices.items():
        if len(prices) >= period + 1:
            base = prices[-period - 1]
            if base != 0:
                returns[sym] = (prices[-1] - base) / base * 100
    if not returns:
        return {sym: 0.0 for sym in symbol_prices}
    vals = list(returns.values())
    mean = sum(vals) / len(vals)
    std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
    if std == 0:
        return {sym: 0.0 for sym in returns}
    return {sym: _clamp((r - mean) / std) for sym, r in returns.items()}


# ---------------------------------------------------------------------------
# Main composite calculator
# ---------------------------------------------------------------------------

def compute_multi_factor_score(
    symbol: str,
    candles: List[Dict],
    macro: Optional[Dict] = None,
    eia_data: Optional[Dict] = None,
    cftc_data: Optional[Dict] = None,
    custom_weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """Compute the full multi-factor composite score for a symbol.

    Args:
        symbol: e.g. 'WTI'
        candles: list of {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
        macro: output of MacroFetcher.fetch_all_macro()
        eia_data: output of EIAFetcher (weekly anchor data)
        cftc_data: output of CFTCFetcher.fetch_latest()
        custom_weights: optional override of factor weights (must sum to 1.0)

    Returns dict with composite_score, regime, factor_scores, factor_weights, etc.
    """
    if not candles or len(candles) < 20:
        return {
            "symbol": symbol,
            "composite_score": 0.0,
            "regime": "UNKNOWN",
            "regime_type": "UNKNOWN",
            "factor_scores": {},
            "factor_weights": DEFAULT_WEIGHTS.copy(),
            "signal": "NEUTRAL",
            "confidence": 0.0,
            "error": "Insufficient historical data (need ≥20 candles)",
        }

    prices = [float(c.get("close", 0)) for c in candles]

    # ── Volatility ──────────────────────────────────────────────────────────
    recent = prices[-20:]
    returns_20d = [(recent[i] - recent[i-1]) / recent[i-1] for i in range(1, len(recent)) if recent[i-1] != 0]
    variance = sum(r ** 2 for r in returns_20d) / len(returns_20d) if returns_20d else 0
    annual_vol_pct = (variance ** 0.5) * (252 ** 0.5) * 100

    # ── Regime ──────────────────────────────────────────────────────────────
    regime_type = detect_regime(candles, annual_vol_pct)

    # ── AI Prediction ────────────────────────────────────────────────────────
    ai_val = None
    try:
        from legacy_archive.prediction.feature_store import get_recent_predictions
        preds = get_recent_predictions(symbol, n_days=1)
        if preds:
            latest = preds[0]
            label = latest.get("prediction_label", "NEUTRAL")
            conf = latest.get("confidence", 0.0)
            if label in ("UP", "LONG", "BULLISH"):
                ai_val = float(conf)
            elif label in ("DOWN", "SHORT", "BEARISH"):
                ai_val = -float(conf)
    except Exception as e:
        logger.error(f"Failed to fetch AI prediction: {e}")

    # ── Factor scores ────────────────────────────────────────────────────────
    adx_val, _ = factor_adx(candles)
    atr_pct_val = factor_atr_pct(candles)

    raw_scores = {
        "trend_ema":         factor_trend_ema(prices),
        "trend_macd":        factor_trend_macd(prices),
        "trend_adx":         0.0,
        "bb_pct_b":          factor_bb_pct_b(prices),
        "atr_pct":           0.0,
        "mean_rev_zscore":   factor_mean_rev_zscore(prices),
        "rsi_normalized":    factor_rsi_normalized(prices),
        "momentum_roc":      factor_momentum_roc(prices),
        "macro_dxy":         factor_macro_dxy(macro.get("dxy_change") if macro else None),
        "macro_risk":        factor_macro_risk(
                                macro.get("spx_change") if macro else None,
                                macro.get("vix") if macro else None,
                             ),
        "fundamentals_eia":  factor_eia_surprise(eia_data),
        "fundamentals_cftc": factor_cftc_contrarian(cftc_data, symbol),
        "ai_prediction":     ai_val,
    }

    import math
    factor_scores: Dict[str, float] = {}
    for k, v in raw_scores.items():
        if v is not None and not math.isnan(v):
            factor_scores[k] = float(v)

    # ── Weights ─────────────────────────────────────────────────────────────
    if custom_weights:
        base_weights = custom_weights
    else:
        base_weights = REGIME_WEIGHTS.get(regime_type, DEFAULT_WEIGHTS)

    # Normalize weights so they sum to 1.0 ONLY for valid factors
    active_factors = {k: v for k, v in base_weights.items() if v > 0 and k in factor_scores}
    total_weight = sum(active_factors.values())
    if total_weight == 0:
        normalized_weights = {k: 1.0 / len(active_factors) for k in active_factors} if active_factors else {}
    else:
        normalized_weights = {k: v / total_weight for k, v in active_factors.items()}

    # ── Composite score ──────────────────────────────────────────────────────
    composite_raw = sum(
        factor_scores[k] * w
        for k, w in normalized_weights.items()
    ) if normalized_weights else 0.0
    
    composite_score = round(composite_raw * 100, 1)   # scale to [-100, +100]

    # ── Signal label + confidence ─────────────────────────────────────────────
    if composite_score > 40:
        signal = "STRONG_BUY"
    elif composite_score > 15:
        signal = "BUY"
    elif composite_score < -40:
        signal = "STRONG_SELL"
    elif composite_score < -15:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    # Confidence: agreement across factors
    scores_list = [v for k, v in factor_scores.items() if k in active_factors and active_factors[k] > 0]
    if scores_list:
        agreement = sum(1 for s in scores_list if (s > 0) == (composite_score > 0)) / len(scores_list)
        confidence = round(agreement, 2)
    else:
        confidence = 0.0

    return {
        "symbol":           symbol,
        "composite_score":  composite_score,
        "regime":           "BULLISH" if composite_score > 20 else "BEARISH" if composite_score < -20 else "NEUTRAL",
        "regime_type":      regime_type,
        "adx":              adx_val,
        "annual_vol_pct":   round(annual_vol_pct, 1),
        "atr_pct":          atr_pct_val,
        "factor_scores":    {k: round(v, 4) for k, v in factor_scores.items()},
        "factor_weights":   normalized_weights,
        "signal":           signal,
        "confidence":       confidence,
        # Legacy sub_scores for backward compat with existing frontend
        "sub_scores": {
            "ema_trend":         round(factor_scores.get("trend_ema", 0.0), 3),
            "news_sentiment":    0.0,   # added by caller when news data available
            "cftc_positioning":  round(factor_scores.get("fundamentals_cftc", 0.0), 3),
            "eia_surprise":      round(factor_scores.get("fundamentals_eia", 0.0), 3),
            "seasonality":       0.0,
        },
        "weights": normalized_weights,
    }
