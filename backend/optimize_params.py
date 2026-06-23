import sys
import os
import asyncio
import copy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backtesting.engine import run_backtest
from backtesting.strategies import STRATEGIES

async def optimize_zscore():
    print("Starting Z-Score Parameter Optimization...")
    print(f"{'Entry Z':<10} {'Exit Z':<10} {'Total PnL ($)':<15} {'Win Rate (%)':<15} {'Trades':<10} {'Sharpe':<10}")
    print("-" * 75)

    best_pnl = -float('inf')
    best_params = None
    
    # Take a pristine copy to avoid cumulative modification if any
    pristine_params = copy.deepcopy(STRATEGIES["zscore_mean_reversion"].params)

    for entry_z in [1.5, 2.0, 2.5, 3.0]:
        for exit_z in [0.0, 0.5, 1.0]:
            # Reset before run
            STRATEGIES["zscore_mean_reversion"].params = copy.deepcopy(pristine_params)
            
            result = run_backtest(
                strategies=["zscore_mean_reversion"],
                combination_mode="independent",
                products=["CL"],
                include_spreads=True,
                include_flies=True,
                include_dflies=False,
                include_outrights=False,
                initial_capital=1000000,
                lots_per_trade=1,
                db_dir=os.path.join(os.path.dirname(__file__), "..", "DB"),
                strategy_params={"zscore_mean_reversion": {"entry_z": entry_z, "exit_z": exit_z}}
            )

            overview = result.get("overview", {})
            pnl = overview.get("total_pnl", 0.0)
            win_rate = overview.get("win_rate", 0.0)
            trades = overview.get("total_trades", 0)
            sharpe = overview.get("sharpe_ratio", 0.0)

            print(f"{entry_z:<10} {exit_z:<10} ${pnl:<14,.2f} {win_rate:<14.2f} {trades:<9} {sharpe:<10.2f}")

            if pnl > best_pnl:
                best_pnl = pnl
                best_params = (entry_z, exit_z)

    print("-" * 75)
    print(f"Best Parameters: Entry Z = {best_params[0]}, Exit Z = {best_params[1]}")
    print(f"Maximized Profit: ${best_pnl:,.2f}")

if __name__ == "__main__":
    asyncio.run(optimize_zscore())
