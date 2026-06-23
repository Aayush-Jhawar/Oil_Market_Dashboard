"""
Unified Indicator Library for Backtesting
==========================================
Wraps all technical indicators into a standardized interface.
Each indicator returns a Signal enum for consistent strategy composition.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd


class Signal(str, Enum):
    """Standardized trade signal."""
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    HOLD = "HOLD"


@dataclass
class IndicatorResult:
    """Container for an indicator's output."""
    signal: Signal
    value: float         # primary indicator value (e.g., z-score, RSI)
    metadata: Dict       # extra details for the trade journal


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------
def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> Dict[str, pd.Series]:
    """Compute Bollinger Bands."""
    ma = series.rolling(window=period, min_periods=period).mean()
    sd = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = ma + num_std * sd
    lower = ma - num_std * sd
    pct_b = (series - lower) / (upper - lower).replace(0, np.nan)
    bandwidth = (upper - lower) / ma.replace(0, np.nan)
    return {"upper": upper, "middle": ma, "lower": lower, "pct_b": pct_b, "bandwidth": bandwidth}


def bb_signal(
    price: float,
    bb: Dict[str, pd.Series],
    idx: int,
    current_position: str = "FLAT",
) -> IndicatorResult:
    """Generate signal from Bollinger Band position."""
    upper = bb["upper"].iloc[idx]
    lower = bb["lower"].iloc[idx]
    middle = bb["middle"].iloc[idx]

    if pd.isna(upper) or pd.isna(lower):
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "BB", "reason": "warming_up"})

    pct_b = bb["pct_b"].iloc[idx]

    if current_position == "FLAT":
        if price <= lower:
            return IndicatorResult(Signal.LONG, float(pct_b), {"indicator": "BB", "reason": "below_lower_band", "upper": float(upper), "lower": float(lower)})
        elif price >= upper:
            return IndicatorResult(Signal.SHORT, float(pct_b), {"indicator": "BB", "reason": "above_upper_band", "upper": float(upper), "lower": float(lower)})
    elif current_position == "LONG":
        if price >= middle:
            return IndicatorResult(Signal.EXIT_LONG, float(pct_b), {"indicator": "BB", "reason": "revert_to_mean"})
    elif current_position == "SHORT":
        if price <= middle:
            return IndicatorResult(Signal.EXIT_SHORT, float(pct_b), {"indicator": "BB", "reason": "revert_to_mean"})

    return IndicatorResult(Signal.HOLD, float(pct_b) if not pd.isna(pct_b) else 0.0, {"indicator": "BB"})


# ---------------------------------------------------------------------------
# Exponential Moving Average Crossover
# ---------------------------------------------------------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    """EMA using pandas ewm for accuracy."""
    return series.ewm(span=period, adjust=False).mean()


def ema_crossover_signal(
    fast_ema: pd.Series,
    slow_ema: pd.Series,
    idx: int,
    current_position: str = "FLAT",
) -> IndicatorResult:
    """EMA crossover: fast > slow = bullish."""
    if idx < 1:
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "EMA_CROSS"})

    fast_now = fast_ema.iloc[idx]
    slow_now = slow_ema.iloc[idx]
    fast_prev = fast_ema.iloc[idx - 1]
    slow_prev = slow_ema.iloc[idx - 1]

    if pd.isna(fast_now) or pd.isna(slow_now) or pd.isna(fast_prev) or pd.isna(slow_prev):
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "EMA_CROSS", "reason": "warming_up"})

    diff_pct = (fast_now - slow_now) / slow_now * 100 if slow_now != 0 else 0.0

    # Bullish crossover
    if fast_prev <= slow_prev and fast_now > slow_now:
        if current_position == "SHORT":
            return IndicatorResult(Signal.EXIT_SHORT, diff_pct, {"indicator": "EMA_CROSS", "reason": "bullish_crossover"})
        return IndicatorResult(Signal.LONG, diff_pct, {"indicator": "EMA_CROSS", "reason": "bullish_crossover"})

    # Bearish crossover
    if fast_prev >= slow_prev and fast_now < slow_now:
        if current_position == "LONG":
            return IndicatorResult(Signal.EXIT_LONG, diff_pct, {"indicator": "EMA_CROSS", "reason": "bearish_crossover"})
        return IndicatorResult(Signal.SHORT, diff_pct, {"indicator": "EMA_CROSS", "reason": "bearish_crossover"})

    return IndicatorResult(Signal.HOLD, diff_pct, {"indicator": "EMA_CROSS"})


# ---------------------------------------------------------------------------
# RSI (Relative Strength Index)
# ---------------------------------------------------------------------------
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def rsi_signal(
    rsi_series: pd.Series,
    idx: int,
    overbought: float = 70.0,
    oversold: float = 30.0,
    current_position: str = "FLAT",
) -> IndicatorResult:
    """RSI overbought/oversold signal."""
    val = rsi_series.iloc[idx]
    if pd.isna(val):
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "RSI"})

    if current_position == "FLAT":
        if val < oversold:
            return IndicatorResult(Signal.LONG, float(val), {"indicator": "RSI", "reason": "oversold"})
        elif val > overbought:
            return IndicatorResult(Signal.SHORT, float(val), {"indicator": "RSI", "reason": "overbought"})
    elif current_position == "LONG":
        if val > overbought:
            return IndicatorResult(Signal.EXIT_LONG, float(val), {"indicator": "RSI", "reason": "overbought_exit"})
    elif current_position == "SHORT":
        if val < oversold:
            return IndicatorResult(Signal.EXIT_SHORT, float(val), {"indicator": "RSI", "reason": "oversold_exit"})

    return IndicatorResult(Signal.HOLD, float(val), {"indicator": "RSI"})


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------
def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Dict[str, pd.Series]:
    """Compute MACD line, signal line, and histogram."""
    fast_ema = series.ewm(span=fast, adjust=False).mean()
    slow_ema = series.ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def macd_signal(
    macd_data: Dict[str, pd.Series],
    idx: int,
    current_position: str = "FLAT",
) -> IndicatorResult:
    """MACD histogram zero-cross signal."""
    if idx < 1:
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "MACD"})

    hist_now = macd_data["histogram"].iloc[idx]
    hist_prev = macd_data["histogram"].iloc[idx - 1]

    if pd.isna(hist_now) or pd.isna(hist_prev):
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "MACD"})

    # Bullish histogram cross (negative -> positive)
    if hist_prev <= 0 and hist_now > 0:
        if current_position == "SHORT":
            return IndicatorResult(Signal.EXIT_SHORT, float(hist_now), {"indicator": "MACD", "reason": "bullish_histogram_cross"})
        return IndicatorResult(Signal.LONG, float(hist_now), {"indicator": "MACD", "reason": "bullish_histogram_cross"})

    # Bearish histogram cross (positive -> negative)
    if hist_prev >= 0 and hist_now < 0:
        if current_position == "LONG":
            return IndicatorResult(Signal.EXIT_LONG, float(hist_now), {"indicator": "MACD", "reason": "bearish_histogram_cross"})
        return IndicatorResult(Signal.SHORT, float(hist_now), {"indicator": "MACD", "reason": "bearish_histogram_cross"})

    return IndicatorResult(Signal.HOLD, float(hist_now), {"indicator": "MACD"})


# ---------------------------------------------------------------------------
# Mean Reversion Z-Score
# ---------------------------------------------------------------------------
def rolling_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """Rolling Z-Score for mean reversion."""
    rolling_mean = series.rolling(window=window, min_periods=window).mean()
    rolling_std = series.rolling(window=window, min_periods=window).std(ddof=0)
    return (series - rolling_mean) / rolling_std.replace(0, np.nan)


def zscore_signal(
    zscore_series: pd.Series,
    idx: int,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    current_position: str = "FLAT",
) -> IndicatorResult:
    """Z-Score mean reversion signal."""
    z = zscore_series.iloc[idx]
    if pd.isna(z):
        return IndicatorResult(Signal.HOLD, 0.0, {"indicator": "ZSCORE"})

    if current_position == "FLAT":
        if z < -entry_z:
            return IndicatorResult(Signal.LONG, float(z), {"indicator": "ZSCORE", "reason": f"extreme_low_z={z:.2f}"})
        elif z > entry_z:
            return IndicatorResult(Signal.SHORT, float(z), {"indicator": "ZSCORE", "reason": f"extreme_high_z={z:.2f}"})
    elif current_position == "LONG":
        if z >= -exit_z:
            return IndicatorResult(Signal.EXIT_LONG, float(z), {"indicator": "ZSCORE", "reason": "mean_reversion"})
    elif current_position == "SHORT":
        if z <= exit_z:
            return IndicatorResult(Signal.EXIT_SHORT, float(z), {"indicator": "ZSCORE", "reason": "mean_reversion"})

    return IndicatorResult(Signal.HOLD, float(z), {"indicator": "ZSCORE"})


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------
def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


# ---------------------------------------------------------------------------
# Kalman Filter Spread Tracker
# ---------------------------------------------------------------------------
class KalmanSpreadFilter:
    """Simple 1-state Kalman filter to estimate dynamic mean of a spread series."""

    def __init__(self, q: float = 1e-5, r: float = 1e-2):
        self.q = q  # process noise
        self.r = r  # measurement noise
        self.x = None  # state estimate
        self.p = 1.0   # error covariance

    def update(self, z: float) -> Tuple[float, float]:
        """Update with new observation. Returns (estimated_mean, innovation)."""
        if self.x is None:
            self.x = z
            return z, 0.0

        # Predict
        x_pred = self.x
        p_pred = self.p + self.q

        # Update
        k = p_pred / (p_pred + self.r)
        innovation = z - x_pred
        self.x = x_pred + k * innovation
        self.p = (1 - k) * p_pred

        return self.x, innovation

    def fit_series(self, series: pd.Series) -> pd.Series:
        """Fit over an entire series, return z-score of innovations."""
        innovations = []
        for val in series:
            if pd.isna(val):
                innovations.append(np.nan)
                continue
            _, inn = self.update(float(val))
            innovations.append(inn)

        inn_series = pd.Series(innovations, index=series.index)
        # Rolling std of innovations for normalization
        inn_std = inn_series.rolling(window=20, min_periods=5).std(ddof=0)
        z = inn_series / inn_std.replace(0, np.nan)
        return z
