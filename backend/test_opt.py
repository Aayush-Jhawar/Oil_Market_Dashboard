import sys
import os
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backtesting.engine import run_backtest
from backtesting.strategies import STRATEGIES

async def optimize_zscore():
    for entry_z in [1.5, 3.0]:
        exit_z = 0.5
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

        actual_params = STRATEGIES["zscore_mean_reversion"].params
        trades = result.get("overview", {}).get("total_trades", 0)
        pnl = result.get("overview", {}).get("total_pnl", 0)
        print(f"entry_z={entry_z} actual_params={actual_params} trades={trades} PnL={pnl}")

if __name__ == "__main__":
    asyncio.run(optimize_zscore())
