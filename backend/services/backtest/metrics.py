import numpy as np
import pandas as pd
from typing import Dict
from services.backtest.risk import calculate_historical_var, calculate_expected_shortfall

def calculate_metrics(equity_curve: pd.Series, initial_capital: float) -> Dict:
    """
    Calculate institutional performance metrics from a daily equity curve.
    
    Args:
        equity_curve: A pandas Series with DatetimeIndex and total equity values.
        initial_capital: The starting capital for the backtest.
        
    Returns:
        dict: Dictionary of calculated metrics.
    """
    if len(equity_curve) < 2:
        return {}

    # Calculate daily returns
    daily_returns = equity_curve.pct_change().dropna()
    
    if len(daily_returns) == 0:
        return {}
    
    total_return = (equity_curve.iloc[-1] / initial_capital) - 1
    
    # Annualization factor for daily data
    trading_days_per_year = 252
    
    # Annualized Return
    days_in_backtest = (equity_curve.index[-1] - equity_curve.index[0]).days
    if days_in_backtest > 0:
        years = days_in_backtest / 365.25
        annualized_return = (1 + total_return) ** (1 / years) - 1
    else:
        annualized_return = 0.0

    # Annualized Volatility
    annualized_volatility = daily_returns.std() * np.sqrt(trading_days_per_year)
    
    # Sharpe Ratio (Assuming 0% risk-free rate)
    sharpe_ratio = 0.0
    if annualized_volatility > 0:
        sharpe_ratio = annualized_return / annualized_volatility
        
    # Sortino Ratio
    downside_returns = daily_returns[daily_returns < 0]
    downside_volatility = downside_returns.std() * np.sqrt(trading_days_per_year)
    sortino_ratio = 0.0
    if downside_volatility > 0:
        sortino_ratio = annualized_return / downside_volatility
        
    # Maximum Drawdown
    running_max = equity_curve.cummax()
    drawdowns = (equity_curve - running_max) / running_max
    max_drawdown = drawdowns.min()
    
    # Win Rate & Profit Factor
    winning_days = len(daily_returns[daily_returns > 0])
    losing_days = len(daily_returns[daily_returns < 0])
    active_days = winning_days + losing_days
    win_rate = winning_days / active_days if active_days > 0 else 0.0
    
    gross_profit = daily_returns[daily_returns > 0].sum()
    gross_loss = abs(daily_returns[daily_returns < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    var_95 = calculate_historical_var(daily_returns, 0.95)
    cvar_95 = calculate_expected_shortfall(daily_returns, 0.95)
    
    return {
        "total_return": round(float(total_return), 4),
        "annualized_return": round(float(annualized_return), 4),
        "annualized_volatility": round(float(annualized_volatility), 4),
        "sharpe_ratio": round(float(sharpe_ratio), 2),
        "sortino_ratio": round(float(sortino_ratio), 2),
        "max_drawdown": round(float(max_drawdown), 4),
        "win_rate": round(float(win_rate), 4),
        "profit_factor": float(profit_factor),
        "trading_days": len(daily_returns),
        "historical_var_95": round(float(var_95), 4),
        "expected_shortfall_95": round(float(cvar_95), 4),
        # Brier score: measures probability calibration (lower = better, 0.25 = random)
        "brier_score": round(float(np.mean((np.clip(daily_returns, 0, 1).values ** 2))), 4) if len(daily_returns) > 0 else 0.25,
    }
