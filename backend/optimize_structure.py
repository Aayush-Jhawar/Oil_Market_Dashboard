import sys
import os
import asyncio
import copy

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backtesting.engine import run_backtest
from backtesting.strategies import STRATEGIES

async def optimize_for_structure(struct_name, include_spreads, include_flies, include_dflies):
    print(f"\n--- Optimizing Z-Score for {struct_name} ---")
    print(f"{'Entry Z':<10} {'Exit Z':<10} {'Total PnL ($)':<15} {'Win Rate (%)':<15} {'Trades':<10}")
    
    best_pnl = -float('inf')
    best_params = None
    pristine_params = copy.deepcopy(STRATEGIES["zscore_mean_reversion"].params)

    for entry_z in [1.5, 2.0, 2.5, 3.0]:
        for exit_z in [0.0, 0.5, 1.0]:
            STRATEGIES["zscore_mean_reversion"].params = copy.deepcopy(pristine_params)
            
            result = run_backtest(
                strategies=["zscore_mean_reversion"],
                combination_mode="independent",
                products=["CL"],
                include_spreads=include_spreads,
                include_flies=include_flies,
                include_dflies=include_dflies,
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

            print(f"{entry_z:<10} {exit_z:<10} ${pnl:<14,.2f} {win_rate:<14.2f} {trades:<9}")

            if pnl > best_pnl:
                best_pnl = pnl
                best_params = (entry_z, exit_z)

    print(f">> BEST FOR {struct_name}: Entry={best_params[0]}, Exit={best_params[1]} (PnL: ${best_pnl:,.2f})")
    return best_params

async def main():
    await optimize_for_structure("SPREADS", True, False, False)
    await optimize_for_structure("FLIES", False, True, False)
    await optimize_for_structure("DOUBLE FLIES", False, False, True)

if __name__ == "__main__":
    asyncio.run(main())
