"""Technical indicators used by the dashboard.

Keep implementations small and dependency-light (numpy, pandas).
This module is the canonical place for EMA, Bollinger, ATR, EWMA cov, etc.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponentially-weighted moving average (alpha smoothing).

    Calculated recursively starting from the SMA of the first `period` elements.
    """
    if len(series) < period:
        return pd.Series(index=series.index, dtype=float)
    
    k = 2 / (period + 1)
    ema_vals = [float('nan')] * (period - 1)
    
    current_ema = series.iloc[:period].mean()
    ema_vals.append(current_ema)
    
    for val in series.iloc[period:]:
        current_ema = float(val) * k + current_ema * (1 - k)
        ema_vals.append(current_ema)
        
    return pd.Series(ema_vals, index=series.index)


def bollinger_bands(prices: pd.Series, period: int = 20, std: float = 2.0) -> Dict[str, pd.Series]:
    ma = prices.rolling(window=period).mean()
    sd = prices.rolling(window=period).std(ddof=0)
    upper = ma + std * sd
    lower = ma - std * sd
    bandwidth = (upper - lower) / ma.replace(0, np.nan)
    pct_b = (prices - lower) / (upper - lower).replace(0, np.nan)
    return {
        "upper": upper,
        "middle": ma,
        "lower": lower,
        "bandwidth": bandwidth,
        "pct_b": pct_b,
    }


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    high = high.astype(float)
    low = low.astype(float)
    close = close.astype(float)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def realized_vol(returns: pd.Series, window: int = 20, annualize: int = 252) -> pd.Series:
    """Simple realized vol: rolling std of returns * sqrt(annualize)
    `returns` expected as decimal returns (not percent)
    """
    rv = returns.rolling(window=window, min_periods=1).std(ddof=0) * math.sqrt(annualize)
    return rv


def ewma_cov_matrix(returns_df: pd.DataFrame, lam: float = 0.94) -> pd.DataFrame:
    """EWMA covariance using RiskMetrics-style decay.

    returns_df: columns are symbols, index is datetime; values are returns.
    """
    # initialize with sample covariance of first rows
    returns_df = returns_df.dropna(how="all")
    if returns_df.empty:
        return pd.DataFrame()

    # start from sample cov of the first row window (up to 30 observations)
    cov = returns_df.iloc[:max(1, min(len(returns_df), 30))].cov()
    for i in range(len(returns_df)):
        r = returns_df.iloc[i].values.reshape(-1, 1)
        outer = r @ r.T
        cov = lam * cov + (1 - lam) * pd.DataFrame(outer, index=returns_df.columns, columns=returns_df.columns)
    return cov


def correlation_matrix(returns_df: pd.DataFrame, window: int = 90) -> pd.DataFrame:
    return returns_df.rolling(window=window, min_periods=1).corr()


def kalman_pair_filter(y: pd.Series, x: pd.Series) -> Dict[str, float]:
    """Lightweight fallback: compute OLS hedge ratio, spread and z-score.

    This is a placeholder for a full Kalman filter; returns a simple beta,
    spread series last value and z-score.
    """
    df = pd.concat([y, x], axis=1).dropna()
    if df.shape[0] < 2:
        return {"beta": float('nan'), "spread": float('nan'), "z_score": float('nan')}
    yv = df.iloc[:, 0]
    xv = df.iloc[:, 1]
    beta = np.polyfit(xv, yv, 1)[0]
    spread = yv - beta * xv
    spread_last = float(spread.iloc[-1])
    
    # 20-period rolling mean and standard deviation for the z-score to avoid lookahead bias
    rolling_mean = spread.rolling(window=20, min_periods=1).mean()
    rolling_std = spread.rolling(window=20, min_periods=1).std(ddof=0)
    rolling_std_clean = rolling_std.apply(lambda val: val if val > 0 else 1.0)
    z = (spread - rolling_mean) / rolling_std_clean
    z_last = float(z.iloc[-1])
    return {"beta": float(beta), "spread": spread_last, "z_score": z_last}


if __name__ == "__main__":
    # Quick smoke test
    s = pd.Series([i + np.random.randn() * 0.1 for i in range(100)])
    bb = bollinger_bands(s)
    print("BB middle tail:", bb["middle"].tail(3).to_list())
