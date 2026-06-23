"""
Technical Feature Calculator
==============================
Computes price-derived technical features: momentum, trend, volatility,
mean-reversion indicators. Extends the existing SignalCalculator with
additional features needed for the prediction engine.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_technical_features(
    closes: List[float],
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
) -> Dict[str, float]:
    """
    Compute technical features from price history.

    Args:
        closes: List of daily close prices (oldest first).
        highs: List of daily high prices.
        lows: List of daily low prices.

    Returns:
        Dict of feature_name -> value.
    """
    features: Dict[str, float] = {}

    if not closes or len(closes) < 21:
        return features

    arr = np.array(closes, dtype=float)
    n = len(arr)

    # ── Momentum ──────────────────────────────────────────────────────────
    if n > 5:
        features["roc_5d"] = (arr[-1] - arr[-6]) / arr[-6] * 100
    if n > 21:
        features["roc_21d"] = (arr[-1] - arr[-22]) / arr[-22] * 100

    # RSI(14)
    if n > 15:
        features["rsi_14"] = _rsi(arr, 14)

    # MACD histogram normalized by price
    if n > 35:
        macd_val, signal_val, hist_val = _macd(arr)
        if hist_val is not None and arr[-1] != 0:
            features["macd_histogram_norm"] = hist_val / arr[-1] * 100

    # ── Trend ─────────────────────────────────────────────────────────────
    if n > 50:
        ema20 = _ema(arr, 20)
        ema50 = _ema(arr, 50)
        if ema20 is not None and ema50 is not None and ema50 != 0:
            features["ema_20_50_diff_pct"] = (ema20 - ema50) / ema50 * 100

    # ADX(14)
    if highs is not None and lows is not None and n > 28:
        adx = _adx(np.array(highs), np.array(lows), arr, 14)
        if adx is not None:
            features["adx_14"] = adx

    # ── Oscillators (require high/low) ────────────────────────────────────
    if highs is not None and lows is not None:
        harr = np.array(highs, dtype=float)
        larr = np.array(lows, dtype=float)

        # Williams %R(14) — bounded [-100, 0]
        if n >= 14:
            wr = _williams_r(harr, larr, arr, 14)
            if wr is not None:
                features["williams_r_14"] = wr

        # CCI(20) — commodity channel index
        if n >= 20:
            cci = _cci(harr, larr, arr, 20)
            if cci is not None:
                features["cci_20"] = cci

        # Stochastic K(14) and D(3)
        if n >= 14:
            stoch_k, stoch_d = _stochastic(harr, larr, arr, 14, 3)
            if stoch_k is not None:
                features["stoch_k_14"] = stoch_k
            if stoch_d is not None:
                features["stoch_d_3"] = stoch_d

    # ── Volatility ────────────────────────────────────────────────────────
    if n > 20:
        features["realized_vol_20d"] = _realized_vol(arr, 20)
    if n > 60:
        features["realized_vol_60d"] = _realized_vol(arr, 60)
    if "realized_vol_20d" in features and "realized_vol_60d" in features:
        rv60 = features["realized_vol_60d"]
        if rv60 > 0:
            features["vol_ratio_20_60"] = features["realized_vol_20d"] / rv60

    # ATR as % of price
    if highs is not None and lows is not None and n > 14:
        atr = _atr(np.array(highs), np.array(lows), arr, 14)
        if atr is not None and arr[-1] != 0:
            features["atr_pct"] = atr / arr[-1] * 100

    # Bollinger Bands
    if n > 20:
        bb_width, bb_pct_b = _bollinger(arr, 20, 2.0)
        if bb_width is not None:
            features["bb_width"] = bb_width
        if bb_pct_b is not None:
            features["bb_pct_b"] = bb_pct_b

    # ── Mean Reversion ────────────────────────────────────────────────────
    if n > 20:
        features["price_zscore_20d"] = _zscore(arr, 20)
    if n > 60:
        features["price_zscore_60d"] = _zscore(arr, 60)

    # Autocorrelation of returns
    if n > 25:
        log_rets = np.diff(np.log(np.where(arr > 0, arr, 1e-8)))
        features["autocorr_1d"] = _autocorr(log_rets, lag=1, window=20)
        features["autocorr_5d"] = _autocorr(log_rets, lag=5, window=20)

    # Distance from 52-week high
    if n > 252:
        high_52w = np.max(arr[-252:])
        if high_52w != 0:
            features["dist_from_52w_high"] = (arr[-1] - high_52w) / high_52w
    elif n > 21:
        high_all = np.max(arr)
        if high_all != 0:
            features["dist_from_52w_high"] = (arr[-1] - high_all) / high_all

    return features


def compute_technical_features_from_history(
    df: pd.DataFrame,
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
) -> pd.DataFrame:
    """
    Compute technical features for a full price history DataFrame.

    Args:
        df: DataFrame with date index and close/high/low columns.

    Returns:
        DataFrame with technical features indexed by date.
    """
    if df.empty or close_col not in df.columns:
        return pd.DataFrame()

    closes = df[close_col].values.astype(float)
    highs = df[high_col].values.astype(float) if high_col in df.columns else None
    lows = df[low_col].values.astype(float) if low_col in df.columns else None
    n = len(closes)

    results: Dict[str, np.ndarray] = {}

    # ── Momentum ──────────────────────────────────────────────────────────
    results["roc_5d"] = _rolling_roc(closes, 5)
    results["roc_21d"] = _rolling_roc(closes, 21)
    results["rsi_14"] = _rolling_rsi(closes, 14)

    # MACD histogram normalized
    macd_hist = _rolling_macd_hist(closes)
    results["macd_histogram_norm"] = np.where(
        closes != 0, macd_hist / closes * 100, 0.0
    )

    # ── Trend ─────────────────────────────────────────────────────────────
    ema20 = _rolling_ema(closes, 20)
    ema50 = _rolling_ema(closes, 50)
    results["ema_20_50_diff_pct"] = np.where(
        ema50 != 0, (ema20 - ema50) / ema50 * 100, 0.0
    )

    if highs is not None and lows is not None:
        results["adx_14"] = _rolling_adx(highs, lows, closes, 14)

    # ── Oscillators (require high/low) ────────────────────────────────────
    if highs is not None and lows is not None:
        results["williams_r_14"] = _rolling_williams_r(highs, lows, closes, 14)
        results["cci_20"]        = _rolling_cci(highs, lows, closes, 20)
        stoch_k, stoch_d        = _rolling_stochastic(highs, lows, closes, 14, 3)
        results["stoch_k_14"]   = stoch_k
        results["stoch_d_3"]    = stoch_d

    # ── Volatility ────────────────────────────────────────────────────────
    results["realized_vol_20d"] = _rolling_vol(closes, 20)
    results["realized_vol_60d"] = _rolling_vol(closes, 60)
    rv60 = results["realized_vol_60d"].copy()
    rv60[rv60 == 0] = np.nan
    results["vol_ratio_20_60"] = results["realized_vol_20d"] / rv60

    if highs is not None and lows is not None:
        results["atr_pct"] = _rolling_atr_pct(highs, lows, closes, 14)

    bb_w, bb_b = _rolling_bollinger(closes, 20, 2.0)
    results["bb_width"] = bb_w
    results["bb_pct_b"] = bb_b

    # ── Mean Reversion (return-based z-score, NOT raw price z-score) ──────
    # Using log-returns avoids non-stationarity of raw price levels
    log_rets = np.diff(np.log(np.where(closes > 0, closes, 1e-8)), prepend=np.nan)
    results["return_zscore_20d"] = _rolling_zscore(log_rets, 20)
    results["return_zscore_60d"] = _rolling_zscore(log_rets, 60)
    
    # Autocorrelation of returns
    results["autocorr_1d"] = _rolling_autocorr(log_rets, lag=1, window=20)
    results["autocorr_5d"] = _rolling_autocorr(log_rets, lag=5, window=20)

    # Distance from rolling max
    results["dist_from_52w_high"] = _rolling_dist_from_high(closes, 252)

    # Build DataFrame
    feat_df = pd.DataFrame(results, index=df.index)
    return feat_df


# ---------------------------------------------------------------------------
# Internal calculation helpers (vectorized where possible)
# ---------------------------------------------------------------------------

def _ema(arr: np.ndarray, period: int) -> Optional[float]:
    """Single EMA value at the end of the array."""
    if len(arr) < period:
        return None
    k = 2.0 / (period + 1)
    ema = np.mean(arr[:period])
    for val in arr[period:]:
        ema = val * k + ema * (1 - k)
    return float(ema)


def _rolling_ema(arr: np.ndarray, period: int) -> np.ndarray:
    """Full EMA series."""
    n = len(arr)
    result = np.full(n, np.nan)
    if n < period:
        return result
    k = 2.0 / (period + 1)
    ema = np.mean(arr[:period])
    result[period - 1] = ema
    for i in range(period, n):
        ema = arr[i] * k + ema * (1 - k)
        result[i] = ema
    return result


def _rsi(arr: np.ndarray, period: int = 14) -> float:
    """RSI at end of array."""
    if len(arr) < period + 1:
        return 50.0
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _rolling_rsi(arr: np.ndarray, period: int = 14) -> np.ndarray:
    """Full RSI series."""
    n = len(arr)
    result = np.full(n, np.nan)
    if n < period + 1:
        return result
    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        result[period] = 100.0
    else:
        result[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            result[i + 1] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return result


def _macd(arr: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD at end of array. Returns (macd_line, signal_line, histogram)."""
    if len(arr) < slow + signal:
        return None, None, None
    ema_fast = _ema(arr, fast)
    ema_slow = _ema(arr, slow)
    if ema_fast is None or ema_slow is None:
        return None, None, None
    macd_line = ema_fast - ema_slow

    # Compute full MACD series for signal line
    ema_f = _rolling_ema(arr, fast)
    ema_s = _rolling_ema(arr, slow)
    macd_series = ema_f - ema_s
    valid = macd_series[~np.isnan(macd_series)]
    if len(valid) < signal:
        return macd_line, None, None
    signal_val = _ema(valid, signal)
    histogram = macd_line - signal_val if signal_val is not None else None
    return macd_line, signal_val, histogram


def _rolling_macd_hist(arr: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> np.ndarray:
    """Full MACD histogram series."""
    n = len(arr)
    result = np.full(n, 0.0)
    ema_f = _rolling_ema(arr, fast)
    ema_s = _rolling_ema(arr, slow)
    macd_line = ema_f - ema_s
    # Signal line = EMA of MACD line
    valid_start = slow - 1
    if valid_start >= n:
        return result
    macd_valid = macd_line[valid_start:]
    sig_ema = _rolling_ema(macd_valid, signal)
    full_signal = np.full(n, np.nan)
    full_signal[valid_start:] = sig_ema
    hist = macd_line - full_signal
    result = np.where(np.isnan(hist), 0.0, hist)
    return result


def _rolling_roc(arr: np.ndarray, period: int) -> np.ndarray:
    """Rolling Rate of Change."""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(period, n):
        if arr[i - period] != 0:
            result[i] = (arr[i] - arr[i - period]) / arr[i - period] * 100
    return result


def _realized_vol(arr: np.ndarray, window: int = 20) -> float:
    """Annualized realized volatility."""
    if len(arr) < window + 1:
        return 0.0
    recent = arr[-window:]
    returns = np.diff(recent) / recent[:-1]
    return float(np.std(returns) * math.sqrt(252) * 100)


def _rolling_vol(arr: np.ndarray, window: int = 20) -> np.ndarray:
    """Rolling annualized realized volatility."""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(window, n):
        segment = arr[i - window: i + 1]
        rets = np.diff(segment) / segment[:-1]
        result[i] = np.std(rets) * math.sqrt(252) * 100
    return result


def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> Optional[float]:
    """ADX at end of array."""
    n = len(closes)
    if n < 2 * period:
        return None
    dm_plus = np.zeros(n - 1)
    dm_minus = np.zeros(n - 1)
    tr = np.zeros(n - 1)
    for i in range(n - 1):
        up = highs[i + 1] - highs[i]
        down = lows[i] - lows[i + 1]
        dm_plus[i] = up if up > down and up > 0 else 0
        dm_minus[i] = down if down > up and down > 0 else 0
        tr[i] = max(highs[i + 1] - lows[i + 1], abs(highs[i + 1] - closes[i]), abs(lows[i + 1] - closes[i]))

    atr_val = np.sum(tr[:period])
    adm_p = np.sum(dm_plus[:period])
    adm_m = np.sum(dm_minus[:period])
    dx_vals = []
    for i in range(period, len(tr)):
        atr_val = atr_val - atr_val / period + tr[i]
        adm_p = adm_p - adm_p / period + dm_plus[i]
        adm_m = adm_m - adm_m / period + dm_minus[i]
        di_p = 100 * adm_p / atr_val if atr_val else 0
        di_m = 100 * adm_m / atr_val if atr_val else 0
        dx = 100 * abs(di_p - di_m) / (di_p + di_m) if (di_p + di_m) else 0
        dx_vals.append(dx)
    if not dx_vals:
        return None
    adx_val = np.mean(dx_vals[-period:])
    return float(adx_val)


def _rolling_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """O(N) rolling ADX using Wilder smoothing — replaces the O(N²) naive loop."""
    n = len(closes)
    result = np.full(n, np.nan)
    if n < 2 * period + 1:
        return result

    # Compute true range and directional movements for all bars at once
    up = np.diff(highs, prepend=highs[0])
    down = -(np.diff(lows, prepend=lows[0]))
    prev_close = np.concatenate(([closes[0]], closes[:-1]))
    tr = np.maximum(np.maximum(highs - lows, np.abs(highs - prev_close)), np.abs(lows - prev_close))
    dm_plus  = np.where((up > down) & (up > 0), up, 0.0)
    dm_minus = np.where((down > up) & (down > 0), down, 0.0)

    # Wilder smoothing — O(N) incremental
    atr_w   = np.full(n, np.nan)
    admp_w  = np.full(n, np.nan)
    admm_w  = np.full(n, np.nan)
    atr_w[period - 1]  = np.sum(tr[:period])
    admp_w[period - 1] = np.sum(dm_plus[:period])
    admm_w[period - 1] = np.sum(dm_minus[:period])
    for i in range(period, n):
        atr_w[i]  = atr_w[i - 1]  - atr_w[i - 1]  / period + tr[i]
        admp_w[i] = admp_w[i - 1] - admp_w[i - 1] / period + dm_plus[i]
        admm_w[i] = admm_w[i - 1] - admm_w[i - 1] / period + dm_minus[i]

    with np.errstate(divide='ignore', invalid='ignore'):
        di_plus  = 100.0 * admp_w / atr_w
        di_minus = 100.0 * admm_w / atr_w
        di_sum   = di_plus + di_minus
        dx = np.where(di_sum > 0, 100.0 * np.abs(di_plus - di_minus) / di_sum, 0.0)

    # Smooth DX to get ADX using Wilder averaging
    adx_arr = np.full(n, np.nan)
    first_valid = 2 * period - 1
    if first_valid >= n:
        return result
    adx_arr[first_valid] = np.nanmean(dx[period - 1:first_valid + 1])
    for i in range(first_valid + 1, n):
        adx_arr[i] = (adx_arr[i - 1] * (period - 1) + dx[i]) / period

    result = adx_arr
    return result


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> Optional[float]:
    """ATR at end of array."""
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n - 1)
    for i in range(n - 1):
        tr[i] = max(highs[i + 1] - lows[i + 1], abs(highs[i + 1] - closes[i]), abs(lows[i + 1] - closes[i]))
    atr_val = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr_val = (atr_val * (period - 1) + tr[i]) / period
    return float(atr_val)


def _rolling_atr_pct(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Rolling ATR as % of price."""
    n = len(closes)
    result = np.full(n, np.nan)
    if n < period + 1:
        return result
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr_val = np.mean(tr[:period])
    result[period - 1] = atr_val / closes[period - 1] * 100 if closes[period - 1] != 0 else 0
    for i in range(period, n):
        atr_val = (atr_val * (period - 1) + tr[i]) / period
        result[i] = atr_val / closes[i] * 100 if closes[i] != 0 else 0
    return result


def _zscore(arr: np.ndarray, window: int = 20) -> float:
    """Price z-score at end of array."""
    if len(arr) < window:
        return 0.0
    recent = arr[-window:]
    mean = np.mean(recent)
    std = np.std(recent)
    if std == 0:
        return 0.0
    return float((arr[-1] - mean) / std)


def _rolling_zscore(arr: np.ndarray, window: int = 20) -> np.ndarray:
    """Rolling price z-score."""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(window - 1, n):
        segment = arr[i - window + 1: i + 1]
        mean = np.mean(segment)
        std = np.std(segment)
        if std > 0:
            result[i] = (arr[i] - mean) / std
        else:
            result[i] = 0.0
    return result


def _autocorr(arr: np.ndarray, lag: int = 1, window: int = 20) -> float:
    """Autocorrelation at end of array."""
    if len(arr) < window:
        return 0.0
    segment = arr[-window:]
    x = segment[:-lag]
    y = segment[lag:]
    if len(x) > 1 and np.var(x) > 0 and np.var(y) > 0:
        return float(np.corrcoef(x, y)[0, 1])
    return 0.0


def _rolling_autocorr(arr: np.ndarray, lag: int = 1, window: int = 20) -> np.ndarray:
    """Rolling autocorrelation."""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(window - 1, n):
        segment = arr[i - window + 1: i + 1]
        x = segment[:-lag]
        y = segment[lag:]
        if len(x) > 1 and np.var(x) > 0 and np.var(y) > 0:
            result[i] = np.corrcoef(x, y)[0, 1]
        else:
            result[i] = 0.0
    return result

def _bollinger(arr: np.ndarray, period: int = 20, sigma: float = 2.0):
    """Bollinger band width and %B at end of array."""
    if len(arr) < period:
        return None, None
    recent = arr[-period:]
    sma = np.mean(recent)
    std = np.std(recent)
    upper = sma + sigma * std
    lower = sma - sigma * std
    width = upper - lower
    pct_b = (arr[-1] - lower) / width if width > 0 else 0.5
    return float(width), float(pct_b)


def _rolling_bollinger(arr: np.ndarray, period: int = 20, sigma: float = 2.0):
    """Rolling Bollinger width and %B."""
    n = len(arr)
    width = np.full(n, np.nan)
    pct_b = np.full(n, np.nan)
    for i in range(period - 1, n):
        segment = arr[i - period + 1: i + 1]
        sma = np.mean(segment)
        std = np.std(segment)
        u = sma + sigma * std
        l = sma - sigma * std
        w = u - l
        width[i] = w
        pct_b[i] = (arr[i] - l) / w if w > 0 else 0.5
    return width, pct_b


def _rolling_dist_from_high(arr: np.ndarray, window: int = 252) -> np.ndarray:
    """Rolling distance from N-day high."""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(min(window, 21) - 1, n):
        lookback = min(i + 1, window)
        high = np.max(arr[i - lookback + 1: i + 1])
        if high != 0:
            result[i] = (arr[i] - high) / high
    return result


# ---------------------------------------------------------------------------
# Oscillator helpers — Williams %R, CCI, Stochastic
# ---------------------------------------------------------------------------

def _williams_r(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
) -> Optional[float]:
    """Williams %R at end of array. Range: [-100, 0]."""
    n = len(closes)
    if n < period:
        return None
    h = np.max(highs[-period:])
    l = np.min(lows[-period:])
    if h == l:
        return -50.0
    return float((h - closes[-1]) / (h - l) * -100.0)


def _rolling_williams_r(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
) -> np.ndarray:
    """Full Williams %R series."""
    n = len(closes)
    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        h = np.max(highs[i - period + 1: i + 1])
        l = np.min(lows[i - period + 1: i + 1])
        if h != l:
            result[i] = (h - closes[i]) / (h - l) * -100.0
        else:
            result[i] = -50.0
    return result


def _cci(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 20
) -> Optional[float]:
    """Commodity Channel Index at end of array."""
    n = len(closes)
    if n < period:
        return None
    typical = (highs[-period:] + lows[-period:] + closes[-period:]) / 3.0
    sma = np.mean(typical)
    mean_dev = np.mean(np.abs(typical - sma))
    if mean_dev == 0:
        return 0.0
    return float((typical[-1] - sma) / (0.015 * mean_dev))


def _rolling_cci(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 20
) -> np.ndarray:
    """Full CCI series."""
    n = len(closes)
    result = np.full(n, np.nan)
    typical = (highs + lows + closes) / 3.0
    for i in range(period - 1, n):
        seg = typical[i - period + 1: i + 1]
        sma = np.mean(seg)
        mean_dev = np.mean(np.abs(seg - sma))
        if mean_dev > 0:
            result[i] = (typical[i] - sma) / (0.015 * mean_dev)
        else:
            result[i] = 0.0
    return result


def _stochastic(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    k_period: int = 14, d_period: int = 3
):
    """Stochastic K and D at end of array. Range: [0, 100]."""
    n = len(closes)
    # Need enough data to compute D (requires d_period K values)
    if n < k_period + d_period - 1:
        return None, None

    # Compute last d_period K values
    k_vals = []
    for offset in range(d_period - 1, -1, -1):
        idx = n - 1 - offset
        if idx < k_period - 1:
            k_vals.append(50.0)
            continue
        h = np.max(highs[idx - k_period + 1: idx + 1])
        l = np.min(lows[idx - k_period + 1: idx + 1])
        k = (closes[idx] - l) / (h - l) * 100.0 if h != l else 50.0
        k_vals.append(float(k))

    stoch_k = k_vals[-1]
    stoch_d = float(np.mean(k_vals))
    return stoch_k, stoch_d


def _rolling_stochastic(
    highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
    k_period: int = 14, d_period: int = 3
):
    """Full Stochastic K and D series."""
    n = len(closes)
    k_arr = np.full(n, np.nan)
    d_arr = np.full(n, np.nan)

    # Compute K
    for i in range(k_period - 1, n):
        h = np.max(highs[i - k_period + 1: i + 1])
        l = np.min(lows[i - k_period + 1: i + 1])
        if h != l:
            k_arr[i] = (closes[i] - l) / (h - l) * 100.0
        else:
            k_arr[i] = 50.0

    # Smooth K to get D (simple moving average)
    for i in range(k_period + d_period - 2, n):
        seg = k_arr[i - d_period + 1: i + 1]
        if not np.any(np.isnan(seg)):
            d_arr[i] = np.mean(seg)

    return k_arr, d_arr
