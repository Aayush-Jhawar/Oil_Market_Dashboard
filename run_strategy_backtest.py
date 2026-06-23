"""
Strategy Backtest Runner (CLI)
================================
Standalone CLI to run backtests without the full server.

Usage:
    python run_strategy_backtest.py --strategy zscore_mean_reversion
    python run_strategy_backtest.py --strategy bb_mean_reversion --products CL --spreads-only
    python run_strategy_backtest.py --strategy composite --instruments CL_M1M2 CO_M1M2
    python run_strategy_backtest.py --list-strategies
"""
import sys
import os
import json
import logging
import argparse
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from backtesting.engine import run_backtest, BacktestConfig, BacktestEngine
from backtesting.strategies import STRATEGIES
from backtesting.analytics import BacktestAnalytics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def list_strategies():
    """Print available strategies."""
    print("\n" + "=" * 70)
    print("  AVAILABLE STRATEGIES")
    print("=" * 70)
    for key, cfg in STRATEGIES.items():
        print(f"\n  {key}")
        print(f"    Name:   {cfg.name}")
        print(f"    Type:   {cfg.strategy_type.value}")
        print(f"    Desc:   {cfg.description}")
        params_str = ", ".join(f"{k}={v}" for k, v in cfg.params.items())
        print(f"    Params: {params_str}")
    print("\n" + "=" * 70 + "\n")


def print_summary(results: dict):
    """Pretty-print backtest results."""
    if "error" in results:
        print(f"\n❌ Backtest failed: {results['error']}")
        return

    overview = results.get("overview", {})
    config = results.get("config", {})

    print("\n" + "=" * 70)
    print(f"  BACKTEST RESULTS - {config.get('strategy', 'Unknown')}")
    print(f"  Backtest ID: {results.get('backtest_id', 'N/A')}")
    print("=" * 70)

    print(f"\n  [PERFORMANCE SUMMARY]")
    print(f"  {'-' * 50}")
    print(f"  Total P&L:          ${overview.get('total_pnl', 0):>12,.2f}")
    print(f"  Total Return:       {overview.get('total_return_pct', 0):>12.4f}%")
    print(f"  Win Rate:           {overview.get('win_rate', 0):>12.2f}%")
    print(f"  Total Trades:       {overview.get('total_trades', 0):>12d}")
    print(f"  Winning Trades:     {overview.get('winning_trades', 0):>12d}")
    print(f"  Losing Trades:      {overview.get('losing_trades', 0):>12d}")
    print(f"  Avg Win:            ${overview.get('avg_win', 0):>12,.2f}")
    print(f"  Avg Loss:           ${overview.get('avg_loss', 0):>12,.2f}")
    print(f"  Largest Win:        ${overview.get('largest_win', 0):>12,.2f}")
    print(f"  Largest Loss:       ${overview.get('largest_loss', 0):>12,.2f}")
    print(f"  Profit Factor:      {overview.get('profit_factor', 0):>12}")
    print(f"  Expectancy:         ${overview.get('expectancy', 0):>12,.2f}")
    print(f"  Sharpe Ratio:       {overview.get('sharpe_ratio', 0):>12.4f}")
    print(f"  Sortino Ratio:      {overview.get('sortino_ratio', 0):>12.4f}")
    print(f"  Max Consec Wins:    {overview.get('max_consecutive_wins', 0):>12d}")
    print(f"  Max Consec Losses:  {overview.get('max_consecutive_losses', 0):>12d}")
    print(f"  Avg Hold (min):     {overview.get('avg_holding_minutes', 0):>12.1f}")

    # Drawdown
    dd = results.get("drawdown", {})
    print(f"\n  [DRAWDOWN]")
    print(f"  {'-' * 50}")
    print(f"  Max Drawdown:       ${dd.get('max_drawdown', 0):>12,.2f}")
    print(f"  Max Drawdown %:     {dd.get('max_drawdown_pct', 0):>12.4f}%")

    # By Structure
    by_struct = results.get("by_structure", {})
    if by_struct:
        print(f"\n  [BY STRUCTURE]")
        print(f"  {'-' * 50}")
        for struct, stats in by_struct.items():
            print(f"  {struct:15s}  Trades={stats['total_trades']:3d}  "
                  f"WR={stats['win_rate']:5.1f}%  "
                  f"P&L=${stats['total_pnl']:>10,.2f}")

    # Daily P&L
    daily = results.get("daily_pnl", [])
    if daily:
        print(f"\n  [DAILY P&L]")
        print(f"  {'-' * 50}")
        for d in daily:
            sign = "+" if d["pnl"] >= 0 else "-"
            print(f"  {sign} {d['date']}  P&L=${d['pnl']:>10,.2f}  "
                  f"Trades={d['trades']:2d}  W/L={d['wins']}/{d['losses']}")

    # Trade Bifurcation
    bif = results.get("trade_bifurcation", [])
    if bif:
        print(f"\n  [TRADE BIFURCATION - Avg Win vs Avg Loss per Day]")
        print(f"  {'-' * 50}")
        for b in bif:
            print(f"  {b['date']}  AvgWin=${b['avg_profit_per_winning_trade']:>8,.2f} "
                  f"({b['winning_trade_count']}W)  "
                  f"AvgLoss=${b['avg_loss_per_losing_trade']:>8,.2f} "
                  f"({b['losing_trade_count']}L)  "
                  f"Net=${b['net_pnl']:>8,.2f}")

    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Energy Spread/Fly/Outright Backtesting Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--strategy", type=str, default="zscore_mean_reversion",
                        help="Strategy name (use --list-strategies to see options)")
    parser.add_argument("--list-strategies", action="store_true",
                        help="List all available strategies and exit")
    parser.add_argument("--instruments", nargs="+", default=None,
                        help="Specific instruments to backtest (e.g., CL_M1M2 CO_FLY_M1M2M3)")
    parser.add_argument("--products", nargs="+", default=["CL", "CO"],
                        help="Products to include")
    parser.add_argument("--capital", type=float, default=1_000_000.0,
                        help="Initial capital")
    parser.add_argument("--slippage", type=int, default=1, help="Slippage in ticks (default: 1)")
    parser.add_argument("--db-dir", type=str, default="DB",
                        help="Path to DB directory with bars_15min_latest.db file")
    parser.add_argument("--spreads-only", action="store_true",
                        help="Only trade spreads (no flies/outrights)")
    parser.add_argument("--flies-only", action="store_true",
                        help="Only trade flies (no spreads/outrights)")
    parser.add_argument("--outrights", action="store_true",
                        help="Include outright contracts")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to JSON file")

    args = parser.parse_args()

    if args.list_strategies:
        list_strategies()
        return

    include_spreads = True
    include_flies = True
    include_outrights = args.outrights

    if args.spreads_only:
        include_flies = False
        include_outrights = False
    elif args.flies_only:
        include_spreads = False
        include_outrights = False

    print(f"\n>> Running backtest: strategy={args.strategy}, products={args.products}")
    print(f"   Capital=${args.capital:,.0f}, Slippage={args.slippage} ticks")
    print(f"   Spreads={include_spreads}, Flies={include_flies}, Outrights={include_outrights}")

    results = run_backtest(
        strategy_name=args.strategy,
        instruments=args.instruments,
        products=args.products,
        initial_capital=args.capital,
        slippage_ticks=args.slippage,
        db_dir=args.db_dir,
        include_spreads=include_spreads,
        include_flies=include_flies,
        include_outrights=include_outrights,
    )

    print_summary(results)

    # Save to file
    if args.output or "error" not in results:
        output_path = args.output or "strategy_backtest_results.json"
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f">> Results saved to {output_path}")


if __name__ == "__main__":
    main()
