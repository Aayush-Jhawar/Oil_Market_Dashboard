"""
Predefined Trading Strategies
===============================
Each strategy combines one or more indicators and defines entry/exit logic.
Strategies are composable — the engine can run any strategy against any instrument.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

import pandas as pd

from backtesting.indicators import (
    Signal, IndicatorResult,
    bollinger_bands, bb_signal,
    ema, ema_crossover_signal,
    rsi, rsi_signal,
    macd, macd_signal,
    rolling_zscore, zscore_signal,
    atr,
    KalmanSpreadFilter,
)


class StrategyType(str, Enum):
    BB_MEAN_REVERSION = "bb_mean_reversion"
    EMA_CROSSOVER = "ema_crossover"
    RSI_EXTREME = "rsi_extreme"
    MACD_MOMENTUM = "macd_momentum"
    ZSCORE_MEAN_REVERSION = "zscore_mean_reversion"
    KALMAN_SPREAD = "kalman_spread"
    COMPOSITE = "composite"


@dataclass
class StrategyConfig:
    """Configuration for a trading strategy."""
    name: str
    strategy_type: StrategyType
    params: Dict = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "params": self.params,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Default strategy configurations
# ---------------------------------------------------------------------------
STRATEGIES: Dict[str, StrategyConfig] = {
    "bb_mean_reversion": StrategyConfig(
        name="Bollinger Band Mean Reversion",
        strategy_type=StrategyType.BB_MEAN_REVERSION,
        params={"period": 20, "num_std": 2.0},
        description="Enter when price touches Bollinger Band, exit at middle band. Best for range-bound spreads.",
    ),
    "ema_crossover_9_21": StrategyConfig(
        name="EMA Crossover (9/21)",
        strategy_type=StrategyType.EMA_CROSSOVER,
        params={"fast_period": 9, "slow_period": 21},
        description="Fast EMA(9) crossing slow EMA(21). Trend-following on spreads/outrights.",
    ),
    "ema_crossover_5_13": StrategyConfig(
        name="EMA Crossover (5/13)",
        strategy_type=StrategyType.EMA_CROSSOVER,
        params={"fast_period": 5, "slow_period": 13},
        description="Aggressive short-term EMA crossover. Good for intraday momentum.",
    ),
    "rsi_extreme": StrategyConfig(
        name="RSI Extreme",
        strategy_type=StrategyType.RSI_EXTREME,
        params={"period": 14, "overbought": 70.0, "oversold": 30.0},
        description="Buy at RSI < 30 (oversold), sell at RSI > 70 (overbought).",
    ),
    "macd_momentum": StrategyConfig(
        name="MACD Momentum",
        strategy_type=StrategyType.MACD_MOMENTUM,
        params={"fast": 12, "slow": 26, "signal_period": 9},
        description="MACD histogram zero-cross for momentum entries.",
    ),
    "zscore_mean_reversion": StrategyConfig(
        name="Z-Score Mean Reversion",
        strategy_type=StrategyType.ZSCORE_MEAN_REVERSION,
        params={
            "window": 20,
            "SPREAD": {"entry_z": 2.0, "exit_z": 1.0},
            "FLY": {"entry_z": 2.0, "exit_z": 0.0},
            "DFLY": {"entry_z": 2.0, "exit_z": 0.5},
            # fallback
            "entry_z": 2.0, "exit_z": 0.5
        },
        description="Dynamic mean reversion. Defaults optimized per structure.",
    ),
    "kalman_spread": StrategyConfig(
        name="Kalman Filter Spread",
        strategy_type=StrategyType.KALMAN_SPREAD,
        params={"q": 1e-5, "r": 1e-2, "entry_z": 2.0, "exit_z": 0.5},
        description="Dynamic Kalman filter mean estimation with Z-score entries.",
    ),
    "composite": StrategyConfig(
        name="Composite (BB + Z-Score + EMA)",
        strategy_type=StrategyType.COMPOSITE,
        params={
            "bb_period": 20, "bb_std": 2.0,
            "zscore_window": 20, "zscore_entry": 2.0, "zscore_exit": 0.5,
            "ema_fast": 9, "ema_slow": 21,
            "required_confirmations": 2,
        },
        description="Requires 2 of 3 indicators to agree for entry. Most conservative.",
    ),
}


class StrategyRunner:
    """
    Runs a strategy against a price series and generates signals per bar.
    """

    def __init__(self, config: StrategyConfig, structure_type: str = "OUTRIGHT"):
        self.config = config
        self.current_position = "FLAT"  # FLAT, LONG, SHORT
        self._precomputed = {}
        self.structure_type = structure_type

    def precompute(self, df: pd.DataFrame, price_col: str = "close"):
        """Precompute all indicator series needed by this strategy."""
        series = df[price_col].astype(float)
        p = self.config.params
        st = self.config.strategy_type

        if st == StrategyType.BB_MEAN_REVERSION:
            self._precomputed["bb"] = bollinger_bands(series, p.get("period", 20), p.get("num_std", 2.0))

        elif st == StrategyType.EMA_CROSSOVER:
            self._precomputed["fast_ema"] = ema(series, p.get("fast_period", 9))
            self._precomputed["slow_ema"] = ema(series, p.get("slow_period", 21))

        elif st == StrategyType.RSI_EXTREME:
            self._precomputed["rsi"] = rsi(series, p.get("period", 14))

        elif st == StrategyType.MACD_MOMENTUM:
            self._precomputed["macd"] = macd(series, p.get("fast", 12), p.get("slow", 26), p.get("signal_period", 9))

        elif st == StrategyType.ZSCORE_MEAN_REVERSION:
            self._precomputed["zscore"] = rolling_zscore(series, p.get("window", 20))

        elif st == StrategyType.KALMAN_SPREAD:
            kf = KalmanSpreadFilter(q=p.get("q", 1e-5), r=p.get("r", 1e-2))
            self._precomputed["kalman_z"] = kf.fit_series(series)

        elif st == StrategyType.COMPOSITE:
            self._precomputed["bb"] = bollinger_bands(series, p.get("bb_period", 20), p.get("bb_std", 2.0))
            self._precomputed["zscore"] = rolling_zscore(series, p.get("zscore_window", 20))
            self._precomputed["fast_ema"] = ema(series, p.get("ema_fast", 9))
            self._precomputed["slow_ema"] = ema(series, p.get("ema_slow", 21))

        # ATR (always computed if OHLC available)
        if "high" in df.columns and "low" in df.columns:
            self._precomputed["atr"] = atr(df["high"].astype(float), df["low"].astype(float), series)

    def evaluate(self, idx: int, price: float) -> IndicatorResult:
        """Evaluate the strategy at bar index `idx`. Returns signal."""
        st = self.config.strategy_type
        p = self.config.params

        if st == StrategyType.BB_MEAN_REVERSION:
            result = bb_signal(price, self._precomputed["bb"], idx, self.current_position)

        elif st == StrategyType.EMA_CROSSOVER:
            result = ema_crossover_signal(
                self._precomputed["fast_ema"],
                self._precomputed["slow_ema"],
                idx, self.current_position,
            )

        elif st == StrategyType.RSI_EXTREME:
            result = rsi_signal(
                self._precomputed["rsi"], idx,
                p.get("overbought", 70.0), p.get("oversold", 30.0),
                self.current_position,
            )

        elif st == StrategyType.MACD_MOMENTUM:
            result = macd_signal(self._precomputed["macd"], idx, self.current_position)

        elif st == StrategyType.ZSCORE_MEAN_REVERSION:
            p_struct = p.get(self.structure_type, {})
            if not isinstance(p_struct, dict):
                p_struct = {}
            
            entry_z = p_struct.get("entry_z", p.get("entry_z", 2.0))
            exit_z = p_struct.get("exit_z", p.get("exit_z", 0.5))

            result = zscore_signal(
                self._precomputed["zscore"], idx,
                entry_z, exit_z,
                self.current_position,
            )

        elif st == StrategyType.KALMAN_SPREAD:
            result = zscore_signal(
                self._precomputed["kalman_z"], idx,
                p.get("entry_z", 2.0), p.get("exit_z", 0.5),
                self.current_position,
            )
            result.metadata["indicator"] = "KALMAN"

        elif st == StrategyType.COMPOSITE:
            result = self._composite_evaluate(idx, price)

        else:
            result = IndicatorResult(Signal.HOLD, 0.0, {"indicator": "UNKNOWN"})

        # Update position state
        if result.signal == Signal.LONG:
            self.current_position = "LONG"
        elif result.signal == Signal.SHORT:
            self.current_position = "SHORT"
        elif result.signal in (Signal.EXIT_LONG, Signal.EXIT_SHORT):
            self.current_position = "FLAT"

        return result

    def _composite_evaluate(self, idx: int, price: float) -> IndicatorResult:
        """Composite strategy: requires N confirmations."""
        p = self.config.params
        required = p.get("required_confirmations", 2)

        signals = []

        # BB
        bb_res = bb_signal(price, self._precomputed["bb"], idx, self.current_position)
        signals.append(bb_res)

        # Z-Score
        z_res = zscore_signal(
            self._precomputed["zscore"], idx,
            p.get("zscore_entry", 2.0), p.get("zscore_exit", 0.5),
            self.current_position,
        )
        signals.append(z_res)

        # EMA
        ema_res = ema_crossover_signal(
            self._precomputed["fast_ema"],
            self._precomputed["slow_ema"],
            idx, self.current_position,
        )
        signals.append(ema_res)

        # Count directional votes
        long_votes = sum(1 for s in signals if s.signal == Signal.LONG)
        short_votes = sum(1 for s in signals if s.signal == Signal.SHORT)
        exit_long_votes = sum(1 for s in signals if s.signal == Signal.EXIT_LONG)
        exit_short_votes = sum(1 for s in signals if s.signal == Signal.EXIT_SHORT)

        triggers = [s.metadata.get("indicator", "?") for s in signals if s.signal != Signal.HOLD]
        meta = {"indicator": "COMPOSITE", "triggers": triggers, "votes": {"long": long_votes, "short": short_votes}}

        if self.current_position == "FLAT":
            if long_votes >= required:
                return IndicatorResult(Signal.LONG, float(long_votes), meta)
            elif short_votes >= required:
                return IndicatorResult(Signal.SHORT, float(short_votes), meta)
        elif self.current_position == "LONG":
            if exit_long_votes >= 1 or short_votes >= required:
                return IndicatorResult(Signal.EXIT_LONG, 0.0, meta)
        elif self.current_position == "SHORT":
            if exit_short_votes >= 1 or long_votes >= required:
                return IndicatorResult(Signal.EXIT_SHORT, 0.0, meta)

        return IndicatorResult(Signal.HOLD, 0.0, meta)

    def reset(self):
        """Reset strategy state for a new run."""
        self.current_position = "FLAT"
        self._precomputed = {}
