import sys
import os
import json
import logging
from pathlib import Path
import pandas as pd
import numpy as np
import datetime
import argparse
from itertools import product

# Add backend directory to path
backend_dir = Path(__file__).parent / "backend"
sys.path.append(str(backend_dir))

from services.price_fetcher import PriceFetcher
from prediction.trading.pairs_trader import KalmanFilterPairs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

def run_single_backtest(pair_name: str, df: pd.DataFrame, entry_z: float, V_w: float, max_half_life: float, initial_capital: float = 1_000_000.0):
    engine = KalmanFilterPairs(entry_z=entry_z, V_w=V_w, max_half_life=max_half_life)
    
    capital = initial_capital
    position = 0 # 0=FLAT, 1=LONG SPREAD, -1=SHORT SPREAD
    entry_spread_cost = 0.0
    beta = 1.0
    shares = 0.0
    
    trade_log = []
    equity_curve = []
    trade_capital = initial_capital * 0.95
    
    for _, row in df.iterrows():
        date = row['date']
        px = row['close_x']
        py = row['close_y']
        
        current_beta, current_spread, signal, rationale = engine.update(px, py)
        
        if position != 0:
            mtm_spread = py - beta * px
            unrealized_pnl = shares * (mtm_spread - entry_spread_cost) if position == 1 else shares * (entry_spread_cost - mtm_spread)
            current_equity = capital + unrealized_pnl
        else:
            current_equity = capital
            
        equity_curve.append({"date": date, "equity": current_equity})
        
        if signal == "LONG_SPREAD" and position == 0:
            position = 1
            beta = current_beta
            entry_spread_cost = py - beta * px
            shares = trade_capital / (py + beta * px) if (py + beta * px) != 0 else 0
            
        elif signal == "SHORT_SPREAD" and position == 0:
            position = -1
            beta = current_beta
            entry_spread_cost = py - beta * px
            shares = trade_capital / (py + beta * px) if (py + beta * px) != 0 else 0
            
        elif signal in ["EXIT_LONG", "EXIT_SHORT"] and position != 0:
            mtm_spread = py - beta * px
            realized_pnl = shares * (mtm_spread - entry_spread_cost) if position == 1 else shares * (entry_spread_cost - mtm_spread)
            capital += realized_pnl
            
            trade_log.append({
                "exit_date": date,
                "pnl": realized_pnl
            })
            position = 0
            
    if not trade_log:
        return None
        
    df_trades = pd.DataFrame(trade_log)
    win_rate = (df_trades['pnl'] > 0).mean()
    
    df_eq = pd.DataFrame(equity_curve).set_index("date")
    daily_returns = df_eq['equity'].pct_change().dropna()
    
    ann_return = daily_returns.mean() * 252
    ann_vol = daily_returns.std() * np.sqrt(252)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0
    
    metrics = {
        "entry_z": entry_z,
        "V_w": V_w,
        "max_half_life": max_half_life,
        "total_return": (capital - initial_capital) / initial_capital,
        "sharpe_ratio": sharpe,
        "win_rate": win_rate,
        "trade_count": len(trade_log)
    }
    return metrics

def run_optimization(pair_name: str, asset_x: str, asset_y: str):
    logger.info(f"Fetching historical data for {asset_x} and {asset_y}...")
    
    data_x = PriceFetcher.fetch_historical(asset_x, period="10y")
    data_y = PriceFetcher.fetch_historical(asset_y, period="10y")
    
    if not data_x or not data_y:
        logger.error("Missing historical data")
        return
        
    df_x = pd.DataFrame(data_x)
    df_y = pd.DataFrame(data_y)
    df_x['date'] = pd.to_datetime(df_x['timestamp'])
    df_y['date'] = pd.to_datetime(df_y['timestamp'])
    df = pd.merge(df_x, df_y, on='date', suffixes=('_x', '_y')).sort_values('date')
    
    # Grid Search Space
    entry_z_grid = [1.2, 1.5, 1.8, 2.0]
    vw_grid = [1e-3, 1e-4, 1e-5]
    hl_grid = [10.0, 30.0, 60.0]
    
    results = []
    
    logger.info("Starting Grid Search...")
    for ez, vw, hl in product(entry_z_grid, vw_grid, hl_grid):
        metrics = run_single_backtest(pair_name, df, ez, vw, hl)
        if metrics:
            logger.info(f"Params (Z={ez}, V_w={vw}, HL={hl}) -> Trades: {metrics['trade_count']}, Sharpe: {metrics['sharpe_ratio']:.2f}")
            results.append(metrics)
            
    if results:
        res_df = pd.DataFrame(results).sort_values("sharpe_ratio", ascending=False)
        print("\n=== TOP 5 OPTIMIZED PARAMETER SETS ===")
        print(res_df.head(5).to_string())
        
        best = res_df.iloc[0]
        logger.info(f"Optimal parameters found: Entry Z={best['entry_z']}, V_w={best['V_w']}, Max HL={best['max_half_life']}")
    else:
        logger.warning("No profitable parameter sets found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimize", action="store_true", help="Run parameter sweep")
    args = parser.parse_args()
    
    if args.optimize:
        run_optimization("WTI-Brent", "WTI", "Brent")
    else:
        # Default run just prints help because the user should use --optimize
        print("Run with --optimize to perform grid search parameter sweeping.")
