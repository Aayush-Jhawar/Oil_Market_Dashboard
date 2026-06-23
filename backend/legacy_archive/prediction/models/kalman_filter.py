import numpy as np
from typing import List

class KalmanSpreadTracker:
    def __init__(self, q: float = 1e-4, r: float = 1e-2, initial_state: float = 0.0):
        """
        1D Kalman Filter for tracking the dynamic mean of a spread.
        q: Process noise covariance (drift variance of the mean)
        r: Measurement noise covariance (observed spread volatility)
        """
        self.q = q
        self.r = r
        self.x = initial_state  # State estimate (dynamic spread mean)
        self.p = 1.0            # Estimate covariance

    def step(self, z: float) -> float:
        """
        Process a single measurement z (the current spread).
        Updates the internal state and returns the Kalman Z-Score for this measurement.
        """
        # Time Update (Prediction)
        x_pred = self.x
        p_pred = self.p + self.q

        # Measurement Update (Correction)
        innovation = z - x_pred
        innovation_var = p_pred + self.r
        kalman_gain = p_pred / innovation_var

        # Update state
        self.x = x_pred + kalman_gain * innovation
        self.p = (1 - kalman_gain) * p_pred

        # The Kalman Z-Score is the forecast error scaled by its standard deviation
        z_score = innovation / np.sqrt(innovation_var) if innovation_var > 0 else 0.0
        return z_score
        
    def fit_history(self, history: List[float]) -> float:
        """
        Burn in the filter with historical data and return the final Z-Score.
        Dynamically adjusts Q and R based on historical variance.
        """
        if not history:
            return 0.0
            
        # Initialize state to the first element to avoid massive initial shock
        self.x = history[0]
        
        # Estimate R dynamically from historical variance if history is long enough
        if len(history) > 10:
            hist_var = np.var(history)
            if hist_var > 0:
                self.r = hist_var
                # Assume drift variance is 1% of measurement variance
                # This makes it robust to noise but responsive to structural breaks
                self.q = hist_var * 0.01
                
        # Burn in filter over historical data
        for z in history[:-1]:
            self.step(z)
            
        # Process the final data point and return the final current Z-Score
        return self.step(history[-1])
