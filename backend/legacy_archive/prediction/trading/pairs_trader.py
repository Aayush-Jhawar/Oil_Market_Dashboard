import numpy as np
import logging
from collections import deque
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

class KalmanFilterPairs:
    """
    Online Kalman Filter for statistical arbitrage (pairs trading).
    Dynamically estimates the hedge ratio (beta) between two co-integrated assets.
    """
    def __init__(self, 
                 window: int = 20, 
                 entry_z: float = 1.2, 
                 exit_z: float = 0.0,
                 V_e: float = 1e-3, 
                 V_w: float = 1e-5,
                 max_half_life: float = 10.0):
        """
        :param window: Lookback window for Bollinger Bands (mean/std of spread)
        :param entry_z: Z-score threshold to enter a trade
        :param exit_z: Z-score threshold to exit a trade
        :param V_e: Measurement noise variance (tunes how much we trust the new price observation)
        :param V_w: Process noise variance (tunes how fast beta can change)
        :param max_half_life: Maximum allowed Ornstein-Uhlenbeck half-life to enter trade (periods)
        """
        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.max_half_life = max_half_life
        
        # Kalman Filter Parameters
        self.V_e = V_e  # Measurement noise covariance
        self.V_w = V_w  # State covariance (how fast beta drifts)
        
        # State variables
        self.beta = 1.0   # Initial guess for hedge ratio (y = beta * x)
        self.P = 1.0      # Initial estimation error covariance
        
        # History for Bollinger Bands
        self.spread_history = deque(maxlen=window)
        
        # State tracking for exits
        self.current_position = "FLAT"  # 'LONG', 'SHORT', 'FLAT'
        
    def calculate_ou_halflife(self) -> float:
        """
        Calculates the Ornstein-Uhlenbeck (OU) mean reversion half-life
        using an autoregressive linear regression on the spread history.
        Returns the half-life in periods.
        """
        if len(self.spread_history) < 5:
            return float('inf')
            
        spreads = np.array(self.spread_history)
        y = spreads[1:] - spreads[:-1]  # Change in spread (dy)
        x = spreads[:-1]                # Previous spread (y_{t-1})
        
        # OLS regression: y = a + b*x
        # We only care about the slope (b)
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        
        # Avoid division by zero if spread is constant
        denom = np.sum((x - x_mean)**2)
        if denom < 1e-8:
            return float('inf')
            
        b = np.sum((x - x_mean) * (y - y_mean)) / denom
        
        # Theta is mean reversion speed
        theta = -b
        
        # If theta <= 0, the spread is a random walk or diverging (not mean-reverting)
        if theta <= 1e-8:
            return float('inf')
            
        # Calculate half-life
        half_life = np.log(2) / theta
        return half_life
        
    def update(self, price_x: float, price_y: float) -> Tuple[float, float, str, str]:
        """
        Updates the Kalman filter with new prices and generates a trading signal.
        
        :param price_x: Price of independent variable (Asset X)
        :param price_y: Price of dependent variable (Asset Y)
        :return: (beta, spread, signal, rationale)
        """
        if price_x is None or price_y is None or price_x == 0:
            return self.beta, 0.0, "NO_TRADE", "Missing or invalid price data."
            
        # 1. Prediction Step
        beta_pred = self.beta
        P_pred = self.P + self.V_w
        
        # 2. Update Step (Measurement)
        # Measurement error (Innovation)
        e_t = price_y - (beta_pred * price_x)
        
        # Innovation Variance
        S_t = (price_x ** 2) * P_pred + self.V_e
        
        # Kalman Gain
        K_t = (P_pred * price_x) / S_t
        
        # Updated State (Beta)
        self.beta = beta_pred + K_t * e_t
        
        # Updated Covariance
        self.P = (1 - K_t * price_x) * P_pred
        
        # 3. Calculate spread for trading
        # Actual spread using the newly updated beta
        spread = price_y - (self.beta * price_x)
        self.spread_history.append(spread)
        
        # 4. Generate Signal (Bollinger Bands logic)
        signal = "NO_TRADE"
        rationale = f"Spread: {spread:.4f}, Beta: {self.beta:.4f}"
        
        if len(self.spread_history) < self.window:
            return self.beta, spread, signal, "Warming up BB window."
            
        # Calculate Rolling Mean and Std Dev
        spread_arr = np.array(self.spread_history)
        mean_spread = np.mean(spread_arr)
        std_spread = np.std(spread_arr)
        
        if std_spread < 1e-6:
            return self.beta, spread, signal, "Volatility too low."
            
        # Calculate Z-Score
        z_score = (spread - mean_spread) / std_spread
        rationale = f"Spread Z-Score: {z_score:.2f} (Beta: {self.beta:.4f})"
        
        # Trading Logic (Mean Reversion)
        if self.current_position == "FLAT":
            if z_score > self.entry_z or z_score < -self.entry_z:
                # OU Half-Life Check
                hl = self.calculate_ou_halflife()
                rationale += f" (OU HL: {hl:.1f})"
                
                if hl > self.max_half_life:
                    signal = "NO_TRADE"
                    rationale += " -> VETO (Half-Life > Max)"
                else:
                    if z_score > self.entry_z:
                        # Spread is too high -> Short Y, Long X (Short Spread)
                        signal = "SHORT_SPREAD"
                        self.current_position = "SHORT"
                        rationale += " -> Entry SHORT (Z > Entry)"
                    elif z_score < -self.entry_z:
                        # Spread is too low -> Long Y, Short X (Long Spread)
                        signal = "LONG_SPREAD"
                        self.current_position = "LONG"
                        rationale += " -> Entry LONG (Z < -Entry)"
                
        elif self.current_position == "LONG":
            if z_score >= self.exit_z:
                # Reverted to mean
                signal = "EXIT_LONG"
                self.current_position = "FLAT"
                rationale += " -> Exit LONG (Mean Reversion)"
            else:
                signal = "HOLD_LONG"
                
        elif self.current_position == "SHORT":
            if z_score <= -self.exit_z:
                # Reverted to mean
                signal = "EXIT_SHORT"
                self.current_position = "FLAT"
                rationale += " -> Exit SHORT (Mean Reversion)"
            else:
                signal = "HOLD_SHORT"
                
        return self.beta, spread, signal, rationale

class PairsTradingEngine:
    """
    Manages multiple KalmanFilterPairs instances for different traded spreads.
    """
    def __init__(self):
        self.filters: Dict[str, KalmanFilterPairs] = {}
        
    def get_filter(self, pair_name: str) -> KalmanFilterPairs:
        if pair_name not in self.filters:
            self.filters[pair_name] = KalmanFilterPairs()
        return self.filters[pair_name]
        
    def process_pair(self, pair_name: str, price_x: float, price_y: float) -> dict:
        """
        Process a new tick for a pair.
        Returns a dictionary with the trading signal.
        """
        kf = self.get_filter(pair_name)
        beta, spread, signal, rationale = kf.update(price_x, price_y)
        
        # Determine asset direction from spread signal
        # If LONG SPREAD -> Buy Y, Sell X
        # If SHORT SPREAD -> Sell Y, Buy X
        trade_recommendations = {}
        if signal == "LONG_SPREAD":
            trade_recommendations["Y"] = "LONG"
            trade_recommendations["X"] = "SHORT"
        elif signal == "SHORT_SPREAD":
            trade_recommendations["Y"] = "SHORT"
            trade_recommendations["X"] = "LONG"
        elif signal.startswith("EXIT"):
            trade_recommendations["Y"] = "FLAT"
            trade_recommendations["X"] = "FLAT"
            
        # Extract z_score from rationale if possible
        z_score = 0.0
        if "Z-Score:" in rationale:
            try:
                z_score = float(rationale.split("Z-Score:")[1].split()[0])
            except:
                pass
                
        return {
            "pair": pair_name,
            "signal": signal,
            "beta": beta,
            "spread": spread,
            "z_score": z_score,
            "rationale": rationale,
            "legs": trade_recommendations
        }
