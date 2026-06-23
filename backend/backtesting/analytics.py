"""
Performance Analytics
======================
Computes equity curves, drawdown analysis, daily P&L aggregation,
trade bifurcation, and strategy-level statistics from a list of trades.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np


class BacktestAnalytics:
    """Compute performance metrics from a list of trade dicts."""

    def __init__(self, trades: List[Dict], initial_capital: float = 1_000_000.0):
        self.trades = sorted(trades, key=lambda t: t.get("entry_timestamp", ""))
        self.initial_capital = initial_capital

    def summary(self) -> Dict:
        """Full performance summary."""
        if not self.trades:
            return self._empty_summary()

        return {
            "overview": self._overview_metrics(),
            "equity_curve": self._equity_curve(),
            "drawdown": self._drawdown_analysis(),
            "daily_pnl": self._daily_pnl(),
            "trade_bifurcation": self._trade_bifurcation(),
            "by_structure": self._by_structure(),
            "by_strategy": self._by_strategy(),
            "trade_count": len(self.trades),
            "initial_capital": self.initial_capital,
        }

    # ------------------------------------------------------------------
    # Core Metrics
    # ------------------------------------------------------------------
    def _overview_metrics(self) -> Dict:
        pnls = [t["pnl_dollars"] for t in self.trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        win_rate = len(winners) / len(pnls) if pnls else 0.0
        avg_win = np.mean(winners) if winners else 0.0
        avg_loss = np.mean(losers) if losers else 0.0
        profit_factor = abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0 else float("inf")
        expectancy = np.mean(pnls) if pnls else 0.0

        # Sharpe / Sortino from trade returns
        returns = [t["pnl_dollars"] / self.initial_capital for t in self.trades]
        sharpe = self._sharpe_ratio(returns)
        sortino = self._sortino_ratio(returns)

        # Max consecutive wins/losses
        max_consec_wins, max_consec_losses = self._max_consecutive(pnls)

        # Holding time
        holding_minutes = [t.get("holding_minutes", 0) for t in self.trades]
        avg_hold = np.mean(holding_minutes) if holding_minutes else 0.0

        return {
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_pnl / self.initial_capital * 100, 4),
            "win_rate": round(win_rate * 100, 2),
            "total_trades": len(pnls),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "avg_win": round(float(avg_win), 2),
            "avg_loss": round(float(avg_loss), 2),
            "largest_win": round(max(pnls), 2) if pnls else 0.0,
            "largest_loss": round(min(pnls), 2) if pnls else 0.0,
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "INF",
            "expectancy": round(float(expectancy), 2),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "avg_holding_minutes": round(float(avg_hold), 1),
        }

    # ------------------------------------------------------------------
    # Equity Curve
    # ------------------------------------------------------------------
    def _equity_curve(self) -> List[Dict]:
        curve = [{"timestamp": "", "equity": self.initial_capital, "trade_num": 0}]
        equity = self.initial_capital
        for i, t in enumerate(self.trades, 1):
            equity += t["pnl_dollars"]
            curve.append({
                "timestamp": t.get("exit_timestamp", ""),
                "equity": round(equity, 2),
                "trade_num": i,
            })
        return curve

    # ------------------------------------------------------------------
    # Drawdown Analysis
    # ------------------------------------------------------------------
    def _drawdown_analysis(self) -> Dict:
        equity = self.initial_capital
        peak = equity
        max_dd = 0.0
        max_dd_pct = 0.0
        dd_start = ""
        max_dd_start = ""
        max_dd_end = ""
        current_dd_duration = 0

        drawdown_series = []

        for t in self.trades:
            equity += t["pnl_dollars"]
            if equity > peak:
                peak = equity
                current_dd_duration = 0
                dd_start = t.get("exit_timestamp", "")
            else:
                current_dd_duration += 1

            dd = peak - equity
            dd_pct = dd / peak * 100 if peak > 0 else 0.0
            drawdown_series.append({
                "timestamp": t.get("exit_timestamp", ""),
                "drawdown": round(dd, 2),
                "drawdown_pct": round(dd_pct, 4),
            })

            if dd > max_dd:
                max_dd = dd
                max_dd_pct = dd_pct
                max_dd_start = dd_start
                max_dd_end = t.get("exit_timestamp", "")

        return {
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 4),
            "max_dd_start": max_dd_start,
            "max_dd_end": max_dd_end,
            "drawdown_series": drawdown_series,
        }

    # ------------------------------------------------------------------
    # Daily P&L
    # ------------------------------------------------------------------
    def _daily_pnl(self) -> List[Dict]:
        daily = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})

        for t in self.trades:
            ts = t.get("exit_timestamp", t.get("entry_timestamp", ""))
            day = ts[:10] if ts else "unknown"
            daily[day]["pnl"] += t["pnl_dollars"]
            daily[day]["trades"] += 1
            if t["pnl_dollars"] > 0:
                daily[day]["wins"] += 1
            else:
                daily[day]["losses"] += 1

        result = []
        for day in sorted(daily.keys()):
            d = daily[day]
            result.append({
                "date": day,
                "pnl": round(d["pnl"], 2),
                "trades": d["trades"],
                "wins": d["wins"],
                "losses": d["losses"],
                "win_rate": round(d["wins"] / d["trades"] * 100, 1) if d["trades"] > 0 else 0.0,
            })
        return result

    # ------------------------------------------------------------------
    # Trade Bifurcation (avg profit per winning vs avg loss per losing, per day)
    # ------------------------------------------------------------------
    def _trade_bifurcation(self) -> List[Dict]:
        daily_wins = defaultdict(list)
        daily_losses = defaultdict(list)

        for t in self.trades:
            ts = t.get("exit_timestamp", t.get("entry_timestamp", ""))
            day = ts[:10] if ts else "unknown"
            if t["pnl_dollars"] > 0:
                daily_wins[day].append(t["pnl_dollars"])
            else:
                daily_losses[day].append(t["pnl_dollars"])

        all_days = sorted(set(list(daily_wins.keys()) + list(daily_losses.keys())))
        result = []
        for day in all_days:
            wins = daily_wins.get(day, [])
            losses = daily_losses.get(day, [])
            result.append({
                "date": day,
                "avg_profit_per_winning_trade": round(float(np.mean(wins)), 2) if wins else 0.0,
                "avg_loss_per_losing_trade": round(float(np.mean(losses)), 2) if losses else 0.0,
                "winning_trade_count": len(wins),
                "losing_trade_count": len(losses),
                "net_pnl": round(sum(wins) + sum(losses), 2),
            })
        return result

    # ------------------------------------------------------------------
    # By Structure (Spread / Fly / Outright)
    # ------------------------------------------------------------------
    def _by_structure(self) -> Dict:
        groups = defaultdict(list)
        for t in self.trades:
            key = t.get("structure_type", "UNKNOWN")
            groups[key].append(t["pnl_dollars"])

        result = {}
        for key, pnls in groups.items():
            winners = [p for p in pnls if p > 0]
            losers = [p for p in pnls if p <= 0]
            result[key] = {
                "total_trades": len(pnls),
                "total_pnl": round(sum(pnls), 2),
                "win_rate": round(len(winners) / len(pnls) * 100, 2) if pnls else 0.0,
                "avg_win": round(float(np.mean(winners)), 2) if winners else 0.0,
                "avg_loss": round(float(np.mean(losers)), 2) if losers else 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # By Strategy
    # ------------------------------------------------------------------
    def _by_strategy(self) -> Dict:
        groups = defaultdict(list)
        for t in self.trades:
            key = t.get("strategy_name", "UNKNOWN")
            groups[key].append(t["pnl_dollars"])

        result = {}
        for key, pnls in groups.items():
            winners = [p for p in pnls if p > 0]
            losers = [p for p in pnls if p <= 0]
            result[key] = {
                "total_trades": len(pnls),
                "total_pnl": round(sum(pnls), 2),
                "win_rate": round(len(winners) / len(pnls) * 100, 2) if pnls else 0.0,
                "avg_win": round(float(np.mean(winners)), 2) if winners else 0.0,
                "avg_loss": round(float(np.mean(losers)), 2) if losers else 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _sharpe_ratio(returns: List[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns)
        excess = arr - risk_free
        std = np.std(excess, ddof=1)
        if std == 0:
            return 0.0
        # Annualize assuming ~26 trades per year (intraday)
        return float(np.mean(excess) / std * math.sqrt(252))

    @staticmethod
    def _sortino_ratio(returns: List[float], risk_free: float = 0.0) -> float:
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns)
        excess = arr - risk_free
        downside = excess[excess < 0]
        if len(downside) == 0:
            return float("inf")
        downside_std = np.std(downside, ddof=1)
        if downside_std == 0:
            return 0.0
        return float(np.mean(excess) / downside_std * math.sqrt(252))

    @staticmethod
    def _max_consecutive(pnls: List[float]) -> Tuple[int, int]:
        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0
        for p in pnls:
            if p > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
        return max_wins, max_losses

    def _empty_summary(self) -> Dict:
        return {
            "overview": {
                "total_pnl": 0.0, "total_return_pct": 0.0, "win_rate": 0.0,
                "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
                "avg_win": 0.0, "avg_loss": 0.0, "largest_win": 0.0,
                "largest_loss": 0.0, "profit_factor": 0.0, "expectancy": 0.0,
                "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
                "max_consecutive_wins": 0, "max_consecutive_losses": 0,
                "avg_holding_minutes": 0.0,
            },
            "equity_curve": [],
            "drawdown": {"max_drawdown": 0.0, "max_drawdown_pct": 0.0, "drawdown_series": []},
            "daily_pnl": [],
            "trade_bifurcation": [],
            "by_structure": {},
            "by_strategy": {},
            "trade_count": 0,
            "initial_capital": self.initial_capital,
        }
