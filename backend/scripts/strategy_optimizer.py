import sqlite3
import pandas as pd
import numpy as np
import datetime
from pathlib import Path
import os
import json

DB_PATH = Path(__file__).parent.parent / 'energy.db'

def get_data():
    conn = sqlite3.connect(DB_PATH)
    # Load WTI data for demonstration of optimization, sorting by timestamp
    query = """
        SELECT timestamp, m1, m2, m3, m4, m5, m6 
        FROM historical_term_structure 
        WHERE symbol = 'WTI'
        ORDER BY timestamp ASC
    """
    df = pd.read_sql_query(query, conn, parse_dates=['timestamp'])
    conn.close()
    df.set_index('timestamp', inplace=True)
    return df

def calculate_metrics(returns):
    if len(returns) == 0:
        return {'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0, 'drawdown': 0.0}
    
    trades = returns[returns != 0]
    num_trades = len(trades)
    if num_trades == 0:
        return {'trades': 0, 'win_rate': 0.0, 'pf': 0.0, 'sharpe': 0.0, 'drawdown': 0.0}
        
    wins = trades[trades > 0]
    losses = trades[trades <= 0]
    
    win_rate = len(wins) / num_trades
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    pf = gross_profit / gross_loss if gross_loss != 0 else float('inf')
    
    # Simple sharpe (annualized, assuming minute data, ~252*24*60 min/yr)
    mean_ret = trades.mean()
    std_ret = trades.std()
    sharpe = (mean_ret / std_ret) * np.sqrt(252*24*60) if std_ret != 0 else 0.0
    
    cum_returns = returns.cumsum()
    rolling_max = cum_returns.cummax()
    drawdown = rolling_max - cum_returns
    max_dd = drawdown.max()
    
    return {
        'trades': num_trades,
        'win_rate': win_rate,
        'pf': pf,
        'sharpe': sharpe,
        'drawdown': max_dd
    }

def run_optimization():
    print("Loading data...")
    df = get_data()
    print(f"Loaded {len(df)} rows.")
    
    # Ensure no duplicate index
    df = df[~df.index.duplicated(keep='first')]
    
    # Split Train / Holdout (last 2 months)
    cutoff_date = df.index[-1] - pd.DateOffset(months=2)
    train_df = df[df.index <= cutoff_date].copy()
    test_df = df[df.index > cutoff_date].copy()
    
    print(f"Train size: {len(train_df)}, Test size: {len(test_df)}")
    
    # We will simulate a Fly strategy (1-2-3)
    # Fly = m1 - 2*m2 + m3
    train_df['fly'] = train_df['m1'] - 2*train_df['m2'] + train_df['m3']
    test_df['fly'] = test_df['m1'] - 2*test_df['m2'] + test_df['m3']
    
    train_df['fly_mean'] = train_df['fly'].rolling(window=60*24).mean() # 1 day rolling
    train_df['fly_std'] = train_df['fly'].rolling(window=60*24).std()
    train_df['zscore'] = (train_df['fly'] - train_df['fly_mean']) / train_df['fly_std']
    
    test_df['fly_mean'] = test_df['fly'].rolling(window=60*24).mean()
    test_df['fly_std'] = test_df['fly'].rolling(window=60*24).std()
    test_df['zscore'] = (test_df['fly'] - test_df['fly_mean']) / test_df['fly_std']
    
    # Calculate returns of the fly itself
    train_df['fly_return'] = train_df['fly'].diff().shift(-1)
    test_df['fly_return'] = test_df['fly'].diff().shift(-1)
    
    thresholds = [1.0, 1.5, 2.0, 2.5, 3.0]
    best_sharpe = -1
    best_thresh = None
    best_metrics = None
    
    print("Optimizing on Train set...")
    results = []
    for th in thresholds:
        # Signal: if zscore > th, short the fly (expect mean reversion)
        # Signal: if zscore < -th, buy the fly
        signal = np.where(train_df['zscore'] > th, -1, 
                 np.where(train_df['zscore'] < -th, 1, 0))
        
        returns = signal * train_df['fly_return']
        returns = returns.fillna(0)
        metrics = calculate_metrics(returns)
        metrics['threshold'] = th
        results.append(metrics)
        
        if metrics['sharpe'] > best_sharpe:
            best_sharpe = metrics['sharpe']
            best_thresh = th
            best_metrics = metrics
            
    print(f"Optimal Threshold: {best_thresh} with Sharpe: {best_sharpe:.2f}")
    
    print("Evaluating on Holdout set...")
    signal_test = np.where(test_df['zscore'] > best_thresh, -1, 
                  np.where(test_df['zscore'] < -best_thresh, 1, 0))
    test_returns = signal_test * test_df['fly_return']
    test_returns = test_returns.fillna(0)
    test_metrics = calculate_metrics(test_returns)
    print(f"Holdout Metrics: {test_metrics}")
    
    # Save results to JSON for generating markdown
    out = {
        'train_results': results,
        'best_threshold': best_thresh,
        'best_train_metrics': best_metrics,
        'test_metrics': test_metrics
    }
    
    with open('optimization_results.json', 'w') as f:
        json.dump(out, f, indent=4)
        
    print("Done. Saved optimization_results.json")

if __name__ == '__main__':
    run_optimization()
