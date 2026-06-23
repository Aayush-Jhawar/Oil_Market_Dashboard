"""
Backtesting Engine
===================
Orchestrates the full backtesting pipeline:
1. Load 15-min bar data from DB/*.db files
2. Construct spreads and flies from individual legs
3. Run strategy signal generation bar-by-bar
4. Simulate trades with stop-loss, take-profit, and slippage
5. Record every trade to the TradeJournal
6. Produce BacktestResult with full analytics
"""
from __future__ import annotations

import glob
import json
import logging
import sqlite3
import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backtesting.indicators import Signal, atr as compute_atr
from backtesting.strategies import StrategyConfig, StrategyRunner, STRATEGIES
from backtesting.trade_journal import Trade, TradeJournal
from backtesting.analytics import BacktestAnalytics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract month code ordering (CME/ICE month codes)
# ---------------------------------------------------------------------------
MONTH_ORDER = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}


def _tenor_sort_key(table_name: str) -> Tuple[int, int]:
    """Sort key to order contracts by expiry. e.g., CL_N26 -> (2026, 7)."""
    parts = table_name.split("_")
    if len(parts) < 2:
        return (9999, 99)
    tenor = parts[1]  # e.g., "N26"
    month_code = tenor[0]
    year_suffix = tenor[1:]
    try:
        year = 2000 + int(year_suffix)
    except ValueError:
        year = 9999
    month = MONTH_ORDER.get(month_code, 99)
    return (year, month)


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------
class DataLoader:
    """Load 15-min bar data from SQLite DB files."""

    def __init__(self, db_dir: str = "DB"):
        self.db_dir = Path(db_dir)

    def discover_db_files(self) -> List[Path]:
        """Find bars_15min_latest.db files."""
        pattern = str(self.db_dir / "bars_15min_latest.db")
        files = sorted(glob.glob(pattern))
        return [Path(f) for f in files]

    def load_all_data(self, product_filter: str = "") -> Dict[str, pd.DataFrame]:
        """
        Load all tables from all DB files into a dict of DataFrames.
        Keys are table names like 'CL_N26'.
        """
        all_data: Dict[str, List[pd.DataFrame]] = {}

        for db_path in self.discover_db_files():
            try:
                conn = sqlite3.connect(str(db_path))
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()

                for (table_name,) in tables:
                    if product_filter and not table_name.startswith(product_filter):
                        continue
                    try:
                        df = pd.read_sql(
                            f'SELECT * FROM "{table_name}" ORDER BY timestamp',
                            conn, parse_dates=["timestamp"],
                        )
                        df = df.set_index("timestamp")
                        if table_name not in all_data:
                            all_data[table_name] = []
                        all_data[table_name].append(df)
                    except Exception as e:
                        logger.warning(f"Failed to load {table_name} from {db_path}: {e}")

                conn.close()
            except Exception as e:
                logger.error(f"Failed to open {db_path}: {e}")

        # Concatenate multi-day data
        result = {}
        for name, dfs in all_data.items():
            combined = pd.concat(dfs).sort_index()
            combined = combined[~combined.index.duplicated(keep="first")]
            result[name] = combined

        return result

    def get_sorted_contracts(self, data: Dict[str, pd.DataFrame], product: str = "CL") -> List[str]:
        """Get contract names sorted by expiry for a given product."""
        contracts = [k for k in data.keys() if k.startswith(f"{product}_")]
        return sorted(contracts, key=_tenor_sort_key)


# ---------------------------------------------------------------------------
# Spread & Fly Constructor
# ---------------------------------------------------------------------------
class SpreadConstructor:
    """Build spread and fly price series from individual contract legs."""

    @staticmethod
    def build_spread(
        leg1_df: pd.DataFrame,
        leg2_df: pd.DataFrame,
        leg1_name: str,
        leg2_name: str,
    ) -> pd.DataFrame:
        """
        Build a spread: Spread = Leg1 - Leg2 (front minus back).
        Returns a DataFrame with OHLCV columns for the spread.
        """
        common_idx = leg1_df.index.intersection(leg2_df.index)
        if common_idx.empty:
            return pd.DataFrame()

        spread = pd.DataFrame(index=common_idx)
        spread["open"] = leg1_df.loc[common_idx, "open"] - leg2_df.loc[common_idx, "open"]
        spread["high"] = leg1_df.loc[common_idx, "high"] - leg2_df.loc[common_idx, "low"]   # max spread
        spread["low"] = leg1_df.loc[common_idx, "low"] - leg2_df.loc[common_idx, "high"]    # min spread
        spread["close"] = leg1_df.loc[common_idx, "close"] - leg2_df.loc[common_idx, "close"]
        spread["volume"] = (leg1_df.loc[common_idx, "volume"] + leg2_df.loc[common_idx, "volume"]) / 2
        spread.attrs["instrument"] = f"{leg1_name}-{leg2_name}"
        spread.attrs["structure_type"] = "SPREAD"
        spread.attrs["legs"] = [leg1_name, leg2_name]
        return spread

    @staticmethod
    def build_fly(
        leg1_df: pd.DataFrame,
        leg2_df: pd.DataFrame,
        leg3_df: pd.DataFrame,
        leg1_name: str,
        leg2_name: str,
        leg3_name: str,
    ) -> pd.DataFrame:
        """
        Build a butterfly: Fly = Leg1 - 2*Leg2 + Leg3.
        """
        common_idx = leg1_df.index.intersection(leg2_df.index).intersection(leg3_df.index)
        if common_idx.empty:
            return pd.DataFrame()

        fly = pd.DataFrame(index=common_idx)
        fly["open"] = leg1_df.loc[common_idx, "open"] - 2 * leg2_df.loc[common_idx, "open"] + leg3_df.loc[common_idx, "open"]
        fly["high"] = leg1_df.loc[common_idx, "high"] - 2 * leg2_df.loc[common_idx, "low"] + leg3_df.loc[common_idx, "high"]
        fly["low"] = leg1_df.loc[common_idx, "low"] - 2 * leg2_df.loc[common_idx, "high"] + leg3_df.loc[common_idx, "low"]
        fly["close"] = leg1_df.loc[common_idx, "close"] - 2 * leg2_df.loc[common_idx, "close"] + leg3_df.loc[common_idx, "close"]
        fly["volume"] = (
            leg1_df.loc[common_idx, "volume"] +
            leg2_df.loc[common_idx, "volume"] +
            leg3_df.loc[common_idx, "volume"]
        ) / 3
        fly.attrs["instrument"] = f"{leg1_name}-2x{leg2_name}+{leg3_name}"
        fly.attrs["structure_type"] = "FLY"
        fly.attrs["legs"] = [leg1_name, leg2_name, leg3_name]
        return fly

    @staticmethod
    def build_all_spreads(
        data: Dict[str, pd.DataFrame],
        product: str,
        sorted_contracts: List[str],
    ) -> Dict[str, pd.DataFrame]:
        """Build all adjacent and selected spreads for a product."""
        spreads = {}
        n = len(sorted_contracts)

        for i in range(n):
            for j in range(i + 1, n):
                if j < 12:  # Liquidity restriction (max M12)
                    c1 = sorted_contracts[i]
                    c2 = sorted_contracts[j]
                    gap = j - i  # M1M2 = gap 1, M1M3 = gap 2, etc.
                    spread_label = f"M{i+1}M{j+1}"
                    key = f"{product}_{spread_label}"

                    df = SpreadConstructor.build_spread(data[c1], data[c2], c1, c2)
                    if not df.empty:
                        df.attrs["spread_spec"] = spread_label
                        df.attrs["product"] = product
                        spreads[key] = df

        return spreads

    @staticmethod
    def build_all_flies(
        data: Dict[str, pd.DataFrame],
        product: str,
        sorted_contracts: List[str],
    ) -> Dict[str, pd.DataFrame]:
        """Build all possible fly combinations for a product."""
        flies = {}
        n = len(sorted_contracts)

        for i in range(n):
            for j in range(i + 1, n):
                k = 2 * j - i
                if k < n and k < 12:  # Equidistant rule and Liquidity restriction (max M12)
                    c1 = sorted_contracts[i]
                    c2 = sorted_contracts[j]
                    c3 = sorted_contracts[k]
                    fly_label = f"M{i+1}M{j+1}M{k+1}"
                    key = f"{product}_FLY_{fly_label}"

                    df = SpreadConstructor.build_fly(
                        data[c1], data[c2], data[c3], c1, c2, c3,
                    )
                    if not df.empty:
                        df.attrs["fly_spec"] = fly_label
                        df.attrs["product"] = product
                        flies[key] = df

        return flies

    @staticmethod
    def build_double_fly(
        leg1_df: pd.DataFrame,
        leg2_df: pd.DataFrame,
        leg3_df: pd.DataFrame,
        leg4_df: pd.DataFrame,
        leg1_name: str,
        leg2_name: str,
        leg3_name: str,
        leg4_name: str,
    ) -> pd.DataFrame:
        """
        Build a double butterfly: DF = Leg1 - 3*Leg2 + 3*Leg3 - Leg4.
        """
        common_idx = leg1_df.index.intersection(leg2_df.index).intersection(leg3_df.index).intersection(leg4_df.index)
        if common_idx.empty:
            return pd.DataFrame()

        df = pd.DataFrame(index=common_idx)
        df["open"] = leg1_df.loc[common_idx, "open"] - 3 * leg2_df.loc[common_idx, "open"] + 3 * leg3_df.loc[common_idx, "open"] - leg4_df.loc[common_idx, "open"]
        df["high"] = leg1_df.loc[common_idx, "high"] - 3 * leg2_df.loc[common_idx, "low"] + 3 * leg3_df.loc[common_idx, "high"] - leg4_df.loc[common_idx, "low"]
        df["low"] = leg1_df.loc[common_idx, "low"] - 3 * leg2_df.loc[common_idx, "high"] + 3 * leg3_df.loc[common_idx, "low"] - leg4_df.loc[common_idx, "high"]
        df["close"] = leg1_df.loc[common_idx, "close"] - 3 * leg2_df.loc[common_idx, "close"] + 3 * leg3_df.loc[common_idx, "close"] - leg4_df.loc[common_idx, "close"]
        df["volume"] = (
            leg1_df.loc[common_idx, "volume"] +
            leg2_df.loc[common_idx, "volume"] +
            leg3_df.loc[common_idx, "volume"] +
            leg4_df.loc[common_idx, "volume"]
        ) / 4
        df.attrs["instrument"] = f"{leg1_name}-3x{leg2_name}+3x{leg3_name}-{leg4_name}"
        df.attrs["structure_type"] = "DFLY"
        df.attrs["legs"] = [leg1_name, leg2_name, leg3_name, leg4_name]
        return df

    @staticmethod
    def build_all_double_flies(
        data: Dict[str, pd.DataFrame],
        product: str,
        sorted_contracts: List[str],
    ) -> Dict[str, pd.DataFrame]:
        """Build all possible double fly combinations for a product."""
        dflies = {}
        n = len(sorted_contracts)

        for i in range(n):
            for j in range(i + 1, n):
                gap = j - i
                k = j + gap
                l = k + gap
                if l < n and l < 12:  # Equidistant rule and Liquidity restriction
                    c1 = sorted_contracts[i]
                    c2 = sorted_contracts[j]
                    c3 = sorted_contracts[k]
                    c4 = sorted_contracts[l]
                    df_label = f"M{i+1}M{j+1}M{k+1}M{l+1}"
                    key = f"{product}_DFLY_{df_label}"

                    df = SpreadConstructor.build_double_fly(
                        data[c1], data[c2], data[c3], data[c4], c1, c2, c3, c4,
                    )
                    if not df.empty:
                        df.attrs["fly_spec"] = df_label
                        df.attrs["product"] = product
                        dflies[key] = df

        return dflies


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------
@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    strategy_names: List[str] = field(default_factory=lambda: ["zscore_mean_reversion"])
    combination_mode: str = "independent"  # consensus, independent, split
    instruments: List[str] = field(default_factory=lambda: ["CL_M1M2"])
    products: List[str] = field(default_factory=lambda: ["CL", "CO"])
    include_spreads: bool = True
    include_flies: bool = True
    include_dflies: bool = False
    include_outrights: bool = False
    initial_capital: float = 1_000_000.0
    lots_per_trade: int = 1               # Number of lots per signal
    contract_multiplier: float = 1000.0   # CL = 1000 bbl
    tick_size: float = 0.01               # 1 tick = $0.01
    slippage_ticks: int = 1               # Default slippage of 1 tick (overrides slippage_pct)
    stop_loss_atr_mult: float = 2.0       # stop = 2x ATR
    take_profit_atr_mult: float = 3.0     # target = 3x ATR
    max_holding_bars: int = 50            # max bars before forced exit (~12.5 hours for 15m bars)
    strategy_params: Dict = field(default_factory=dict)
    db_dir: str = "DB"


class ConsensusRunner:
    """Wrapper that runs multiple StrategyRunners and returns signals based on consensus."""
    def __init__(self, runners: List[StrategyRunner], structure_type: str = "OUTRIGHT"):
        self.runners = runners
        self.current_position = "FLAT"
        self._structure_type = structure_type

    @property
    def structure_type(self) -> str:
        return self._structure_type

    @structure_type.setter
    def structure_type(self, value: str):
        self._structure_type = value
        for r in self.runners:
            r.structure_type = value

    def precompute(self, df: pd.DataFrame, price_col: str):
        for r in self.runners:
            r.precompute(df, price_col)

    def evaluate(self, idx: int, current_price: float):
        # We need to return an object with a .signal and .value property
        # analogous to IndicatorResult.
        results = [r.evaluate(idx, current_price) for r in self.runners]
        signals = [res.signal for res in results]

        # If any wants to exit, we exit
        if any(s in (Signal.EXIT_LONG, Signal.EXIT_SHORT) for s in signals):
            from backtesting.indicators import IndicatorResult
            return IndicatorResult(signal=Signal.EXIT_LONG, value=current_price, metadata={"indicator": "consensus_exit"})

        # To enter, all must agree
        if all(s == Signal.LONG for s in signals):
            consensus = Signal.LONG
        elif all(s == Signal.SHORT for s in signals):
            consensus = Signal.SHORT
        else:
            consensus = Signal.HOLD

        from backtesting.indicators import IndicatorResult
        return IndicatorResult(
            signal=consensus,
            value=current_price,
            metadata={"indicator": "consensus", "agreed": len(self.runners)}
        )

class BacktestEngine:
    """Core backtesting engine."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.backtest_id = str(uuid.uuid4())[:8]
        self.journal = TradeJournal()
        self.loader = DataLoader(config.db_dir)

    def _filter_overlapping_trades(self, trades: List[Trade]) -> List[Trade]:
        """
        Risk Manager: Filter out trades that have overlapping legs with currently active trades.
        This prevents double-dipping risk (e.g., trading a Fly when its constituent Spreads are already held).
        """
        # Sort trades strictly by entry time
        trades.sort(key=lambda t: t.entry_timestamp)
        
        filtered = []
        active_trades: List[Trade] = []
        
        for trade in trades:
            # 1. Purge closed trades from active list
            active_trades = [
                at for at in active_trades 
                if at.exit_timestamp > trade.entry_timestamp
            ]
            
            # 2. Extract legs for current trade
            try:
                current_legs = set(json.loads(trade.leg_details))
            except:
                current_legs = set()
                
            if not current_legs:
                filtered.append(trade)
                active_trades.append(trade)
                continue
                
            # 3. Check for overlaps
            has_overlap = False
            for at in active_trades:
                if at.instrument == trade.instrument:
                    has_overlap = True
                    break
                try:
                    active_legs = set(json.loads(at.leg_details))
                    if current_legs.intersection(active_legs):
                        has_overlap = True
                        break
                except:
                    pass
                    
            if not has_overlap:
                filtered.append(trade)
                active_trades.append(trade)
                
        return filtered

    def run(self) -> Dict:
        """Execute the full backtest pipeline."""
        logger.info(f"Starting backtest {self.backtest_id} with strategies={self.config.strategy_names} mode={self.config.combination_mode}")

        # 1. Load data
        all_data = self.loader.load_all_data()
        if not all_data:
            return {"error": "No data found in DB directory", "backtest_id": self.backtest_id}

        logger.info(f"Loaded {len(all_data)} contract tables")

        # 2. Build instruments
        instruments = self._build_instruments(all_data)
        if not instruments:
            return {"error": "No instruments could be constructed", "backtest_id": self.backtest_id}

        logger.info(f"Built {len(instruments)} tradeable instruments")

        # 3. Get strategy configs
        strategy_configs = []
        for s_name in self.config.strategy_names:
            base_sc = STRATEGIES.get(s_name)
            if not base_sc:
                return {"error": f"Unknown strategy: {s_name}", "backtest_id": self.backtest_id}
            
            # Deep copy to avoid mutating the global STRATEGIES dictionary across runs
            sc = copy.deepcopy(base_sc)
            
            # Override with custom params if provided
            if self.config.strategy_params and s_name in self.config.strategy_params:
                sc.params.update(self.config.strategy_params[s_name])
            strategy_configs.append(sc)

        # 4. Run strategies on each instrument
        all_trades = []
        equity = self.config.initial_capital
        mode = self.config.combination_mode

        if mode == "split" and len(strategy_configs) > 1:
            original_lots = self.config.lots_per_trade
            self.config.lots_per_trade = max(1, original_lots // len(strategy_configs))

        if mode in ("independent", "split"):
            for sc in strategy_configs:
                for inst_key, inst_df in instruments.items():
                    logger.info(f"Running {sc.name} on {inst_key} ({len(inst_df)} bars)")
                    trades, _ = self._run_on_instrument(
                        inst_key, inst_df, sc, equity,
                    )
                    all_trades.extend(trades)
        elif mode == "consensus":
            # Instantiate all standard runners and wrap them
            runners = [StrategyRunner(sc) for sc in strategy_configs]
            consensus_runner = ConsensusRunner(runners)

            for inst_key, inst_df in instruments.items():
                logger.info(f"Running consensus on {inst_key} ({len(inst_df)} bars)")
                # Pass the custom runner
                trades, _ = self._run_on_instrument(
                    inst_key, inst_df, strategy_config=None, starting_equity=equity, runner=consensus_runner
                )
                all_trades.extend(trades)

        logger.info(f"Backtest generation complete: {len(all_trades)} raw trades evaluated")

        # Risk Manager: Filter out overlapping exposures across instruments
        all_trades = self._filter_overlapping_trades(all_trades)
        logger.info(f"Risk Manager filtered down to {len(all_trades)} non-overlapping trades")

        # Record deduplicated trades to the DB
        for trade in all_trades:
            self.journal.record_trade(trade)

        # 5. Compute analytics
        trade_dicts = [t.to_dict() for t in all_trades]
        analytics = BacktestAnalytics(trade_dicts, self.config.initial_capital)
        summary = analytics.summary()
        summary["backtest_id"] = self.backtest_id
        summary["config"] = {
            "strategies": self.config.strategy_names,
            "combination_mode": self.config.combination_mode,
            "instruments": list(instruments.keys()),
            "initial_capital": self.config.initial_capital,
            "slippage_ticks": self.config.slippage_ticks,
            "contract_multiplier": self.config.contract_multiplier,
        }

        return summary

    def _build_instruments(self, all_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Build all tradeable instruments from raw contract data."""
        instruments = {}

        for product in self.config.products:
            sorted_contracts = self.loader.get_sorted_contracts(all_data, product)
            if len(sorted_contracts) < 2:
                continue

            # Outrights
            if self.config.include_outrights:
                for c in sorted_contracts:
                    instruments[c] = all_data[c]
                    instruments[c].attrs["instrument"] = c
                    instruments[c].attrs["structure_type"] = "OUTRIGHT"
                    instruments[c].attrs["product"] = product

            # Spreads
            if self.config.include_spreads:
                spreads = SpreadConstructor.build_all_spreads(all_data, product, sorted_contracts)
                instruments.update(spreads)

            # Flies
            if self.config.include_flies:
                flies = SpreadConstructor.build_all_flies(all_data, product, sorted_contracts)
                instruments.update(flies)

            # Double Flies
            if getattr(self.config, "include_dflies", False):
                dflies = SpreadConstructor.build_all_double_flies(all_data, product, sorted_contracts)
                instruments.update(dflies)

        # Filter to requested instruments if specified
        if self.config.instruments and self.config.instruments != ["all"]:
            filtered = {}
            for key in self.config.instruments:
                if key in instruments:
                    filtered[key] = instruments[key]
                else:
                    # Try partial match
                    for inst_key in instruments:
                        if key in inst_key:
                            filtered[inst_key] = instruments[inst_key]
            if filtered:
                instruments = filtered

        return instruments

    def _run_on_instrument(
        self,
        inst_key: str,
        df: pd.DataFrame,
        strategy_config: Optional[StrategyConfig] = None,
        starting_equity: float = 1_000_000.0,
        runner: Optional[Any] = None,
    ) -> Tuple[List[Trade], float]:
        """Run the strategy on a single instrument."""
        if runner is None:
            runner = StrategyRunner(strategy_config)
            runner.precompute(df, price_col="close")

        trades = []
        equity = starting_equity
        peak_equity = equity

        # Active trade tracking
        active_trade: Optional[Trade] = None
        entry_bar_idx: int = 0

        # Compute ATR if available
        atr_series = None
        if "high" in df.columns and "low" in df.columns:
            atr_series = compute_atr(
                df["high"].astype(float), df["low"].astype(float),
                df["close"].astype(float), period=14,
            )

        structure_type = df.attrs.get("structure_type", "OUTRIGHT")
        product = df.attrs.get("product", inst_key.split("_")[0])
        spread_spec = df.attrs.get("spread_spec", "")
        fly_spec = df.attrs.get("fly_spec", "")
        legs = df.attrs.get("legs", [])

        # Pre-round prices to tick size (vectorized for speed)
        tick = self.config.tick_size
        df["open"] = (df["open"] / tick).round() * tick
        df["high"] = (df["high"] / tick).round() * tick
        df["low"] = (df["low"] / tick).round() * tick
        df["close"] = (df["close"] / tick).round() * tick
        
        # Convert to numpy arrays for fast loop access
        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        timestamps = df.index.astype(str).to_numpy()

        for i in range(1, len(df)):
            # Evaluate strategy on the PREVIOUS closed bar (no lookahead)
            prev_close = float(closes[i - 1])
            result = runner.evaluate(i - 1, prev_close)

            # Execution happens at the CURRENT bar's open price
            open_price = float(opens[i])
            high_price = float(highs[i])
            low_price = float(lows[i])
            close_price = float(closes[i])
            timestamp = str(timestamps[i])
            
            # For ATR and Slippage, use open_price
            current_atr = float(atr_series.iloc[i-1]) if atr_series is not None and not pd.isna(atr_series.iloc[i-1]) else abs(open_price) * 0.02

            # --- Manage active trade ---
            if active_trade is not None:
                bars_held = i - entry_bar_idx

                # Check stop loss (intra-bar using high/low)
                if active_trade.direction == "LONG" and low_price <= active_trade.stop_loss:
                    exit_price = min(open_price, active_trade.stop_loss) # Handle gap down
                    self._close_trade(active_trade, exit_price, timestamp, "STOP_LOSS", bars_held, equity, peak_equity)
                    equity += active_trade.pnl_dollars
                    peak_equity = max(peak_equity, equity)
                    trades.append(active_trade)
                    
                    active_trade = None
                    runner.current_position = "FLAT"
                    continue

                elif active_trade.direction == "SHORT" and high_price >= active_trade.stop_loss:
                    exit_price = max(open_price, active_trade.stop_loss) # Handle gap up
                    self._close_trade(active_trade, exit_price, timestamp, "STOP_LOSS", bars_held, equity, peak_equity)
                    equity += active_trade.pnl_dollars
                    peak_equity = max(peak_equity, equity)
                    trades.append(active_trade)
                    
                    active_trade = None
                    runner.current_position = "FLAT"
                    continue

                # Check take profit (intra-bar using high/low)
                if active_trade.direction == "LONG" and high_price >= active_trade.planned_target:
                    exit_price = max(open_price, active_trade.planned_target) # Handle gap up
                    self._close_trade(active_trade, exit_price, timestamp, "TARGET", bars_held, equity, peak_equity)
                    equity += active_trade.pnl_dollars
                    peak_equity = max(peak_equity, equity)
                    trades.append(active_trade)
                    
                    active_trade = None
                    runner.current_position = "FLAT"
                    continue

                elif active_trade.direction == "SHORT" and low_price <= active_trade.planned_target:
                    exit_price = min(open_price, active_trade.planned_target) # Handle gap down
                    self._close_trade(active_trade, exit_price, timestamp, "TARGET", bars_held, equity, peak_equity)
                    equity += active_trade.pnl_dollars
                    peak_equity = max(peak_equity, equity)
                    trades.append(active_trade)
                    
                    active_trade = None
                    runner.current_position = "FLAT"
                    continue

                # Check max holding period
                if bars_held >= self.config.max_holding_bars:
                    self._close_trade(active_trade, open_price, timestamp, "TIME_EXIT", bars_held, equity, peak_equity)
                    equity += active_trade.pnl_dollars
                    peak_equity = max(peak_equity, equity)
                    trades.append(active_trade)
                    
                    active_trade = None
                    runner.current_position = "FLAT"
                    continue

                # Check signal-based exit (evaluated on previous close, execute on current open)
                if result.signal in (Signal.EXIT_LONG, Signal.EXIT_SHORT):
                    self._close_trade(active_trade, open_price, timestamp, "SIGNAL", bars_held, equity, peak_equity)
                    equity += active_trade.pnl_dollars
                    peak_equity = max(peak_equity, equity)
                    trades.append(active_trade)
                    
                    active_trade = None
                    continue

            # --- Open new trade ---
            if active_trade is None and result.signal in (Signal.LONG, Signal.SHORT):
                direction = "LONG" if result.signal == Signal.LONG else "SHORT"

                # Apply slippage in ticks
                slippage = self.config.slippage_ticks * tick
                
                if direction == "LONG":
                    entry_price = open_price + slippage
                    stop_loss = round((entry_price - current_atr * self.config.stop_loss_atr_mult) / tick) * tick
                    target = round((entry_price + current_atr * self.config.take_profit_atr_mult) / tick) * tick
                else:
                    entry_price = open_price - slippage
                    stop_loss = round((entry_price + current_atr * self.config.stop_loss_atr_mult) / tick) * tick
                    target = round((entry_price - current_atr * self.config.take_profit_atr_mult) / tick) * tick

                active_trade = Trade(
                    trade_id=str(uuid.uuid4())[:8],
                    backtest_id=self.backtest_id,
                    entry_timestamp=timestamp,
                    direction=direction,
                    instrument=inst_key,
                    product=product,
                    structure_type=structure_type,
                    fly_spec=fly_spec,
                    spread_spec=spread_spec,
                    leg_details=json.dumps(legs),
                    entry_price=round(entry_price, 6),
                    planned_target=round(target, 6),
                    stop_loss=round(stop_loss, 6),
                    slippage_cost=round(slippage * self.config.contract_multiplier, 2),
                    entry_indicator=result.metadata.get("indicator", ""),
                    entry_indicator_value=round(result.value, 4),
                    entry_metadata=json.dumps(result.metadata),
                    equity_at_entry=round(equity, 2),
                    strategy_name=strategy_config.name if strategy_config else "Consensus",
                )
                entry_bar_idx = i

        # Close any remaining open trade at end of data
        if active_trade is not None:
            price = float(closes[-1])
            timestamp = str(timestamps[-1])
            bars_held = len(df) - 1 - entry_bar_idx
            self._close_trade(active_trade, price, timestamp, "EOD", bars_held, equity, peak_equity)
            equity += active_trade.pnl_dollars
            trades.append(active_trade)
            

        return trades, equity

    def _close_trade(
        self,
        trade: Trade,
        exit_price: float,
        exit_timestamp: str,
        exit_reason: str,
        bars_held: int,
        current_equity: float,
        peak_equity: float,
    ):
        if trade.structure_type == "DFLY":
            legs = 8
        elif trade.structure_type == "FLY":
            legs = 4
        elif trade.structure_type == "SPREAD":
            legs = 2
        else:
            legs = 1

        # Apply slippage to exit per leg
        tick = self.config.tick_size
        slippage = self.config.slippage_ticks * tick * legs
        
        if trade.direction == "LONG":
            adj_exit = exit_price - slippage
        else:
            adj_exit = exit_price + slippage

        adj_exit = round(adj_exit / tick) * tick
        trade.exit_price = round(adj_exit, 4)
        trade.exit_timestamp = exit_timestamp
        trade.exit_reason = exit_reason
        trade.holding_bars = bars_held
        trade.holding_minutes = bars_held * 15  # 15-min bars

        # P&L calculation
        if trade.direction == "LONG":
            trade.pnl_points = round(adj_exit - trade.entry_price, 6)
        else:
            trade.pnl_points = round(trade.entry_price - adj_exit, 6)

        structures = self.config.lots_per_trade
        total_lots_per_side = structures * legs

        trade.pnl_dollars = round(trade.pnl_points * self.config.contract_multiplier * structures, 2)
        
        # Calculate total dollar slippage based on raw ticks (to avoid double-multiplying legs)
        base_slippage = self.config.slippage_ticks * tick
        trade.slippage_cost = round(base_slippage * 2 * self.config.contract_multiplier * total_lots_per_side, 2)

        trade.equity_at_exit = round(current_equity + trade.pnl_dollars, 2)
        trade.running_drawdown = round(peak_equity - trade.equity_at_exit, 2) if trade.equity_at_exit < peak_equity else 0.0


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------
def run_backtest(
    strategies: List[str] = ["zscore_mean_reversion"],
    combination_mode: str = "independent",
    instruments: Optional[List[str]] = None,
    products: Optional[List[str]] = None,
    initial_capital: float = 1_000_000.0,
    lots_per_trade: int = 1,
    slippage_ticks: int = 1,
    db_dir: str = "DB",
    strategy_params: Optional[Dict] = None,
    include_spreads: bool = True,
    include_flies: bool = True,
    include_dflies: bool = False,
    include_outrights: bool = False,
) -> Dict:
    """Convenience function to run a backtest."""
    config = BacktestConfig(
        strategy_names=strategies,
        combination_mode=combination_mode,
        instruments=instruments or ["all"],
        products=products or ["CL", "CO"],
        include_spreads=include_spreads,
        include_flies=include_flies,
        include_dflies=include_dflies,
        include_outrights=include_outrights,
        initial_capital=initial_capital,
        lots_per_trade=lots_per_trade,
        slippage_ticks=slippage_ticks,
        db_dir=db_dir,
        strategy_params=strategy_params or {},
    )
    engine = BacktestEngine(config)
    return engine.run()
