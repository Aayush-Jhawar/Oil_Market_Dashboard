import numpy as np
import pandas as pd

def calculate_historical_var(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """
    Calculate Historical Value at Risk (VaR) at a given confidence level.
    Returns the VaR as a positive percentage (e.g., 0.02 means 2% VaR).
    """
    if len(returns) == 0:
        return 0.0
    
    # Sort returns from worst to best
    sorted_returns = np.sort(returns.dropna())
    
    # Find the index for the given confidence level
    # e.g., 95% confidence means we look at the 5th percentile worst returns
    index = int((1.0 - confidence_level) * len(sorted_returns))
    
    # Return as positive number representing the loss
    return abs(float(sorted_returns[index])) if index < len(sorted_returns) else 0.0

def calculate_expected_shortfall(returns: pd.Series, confidence_level: float = 0.95) -> float:
    """
    Calculate Expected Shortfall (Conditional VaR) at a given confidence level.
    Returns the CVaR as a positive percentage representing the average loss beyond VaR.
    """
    if len(returns) == 0:
        return 0.0
        
    sorted_returns = np.sort(returns.dropna())
    index = int((1.0 - confidence_level) * len(sorted_returns))
    
    # Take all returns worse than or equal to the VaR threshold
    tail_losses = sorted_returns[:index+1]
    
    if len(tail_losses) == 0:
        return 0.0
        
    # Expected shortfall is the mean of these tail losses
    return abs(float(np.mean(tail_losses)))
