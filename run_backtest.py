import sys
import os
import json
import logging
import datetime
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent / "backend"
sys.path.append(str(backend_dir))

from prediction.validation.multi_asset_backtest import run_multi_asset_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def main():
    symbols = ["WTI", "Brent", "HO"]
    # Run backtest
    results = run_multi_asset_backtest(
        symbols=symbols,
        initial_capital=1_000_000.0,
        horizon_days=5,
        expanding=True
    )
    
    if "error" in results:
        print(f"Backtest failed: {results['error']}")
        return

    # Process metrics to be JSON serializable
    metrics = results.get("metrics", {})
    trade_log = results.get("trade_log", [])
    equity_curve = results.get("equity_curve", [])

    # Write to a JSON file for analysis
    output_data = {
        "metrics": metrics,
        "trade_count": len(trade_log),
        "final_equity": equity_curve[-1]["equity"] if equity_curve else 1000000.0
    }

    # Custom serialization for datetime objects
    def default_serializer(obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if hasattr(obj, "item"):  # numpy types
            return obj.item()
        return str(obj)

    with open("backtest_results.json", "w") as f:
        json.dump(output_data, f, indent=4, default=default_serializer)

    print("Backtest completed successfully. Results saved to backtest_results.json")

if __name__ == "__main__":
    main()
