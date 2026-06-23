from __future__ import annotations

import logging
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from sklearn.neighbors import NearestNeighbors
from prediction.config import HMM_CONFIG

logger = logging.getLogger(__name__)

class RegimeSimilarityEngine:
    """
    Engine to find historical periods with similar market regimes/features
    using K-Nearest Neighbors (KNN) or Dynamic Time Warping (DTW) approximations.
    """

    def __init__(self, n_neighbors: int = 5):
        self.n_neighbors = n_neighbors
        self.knn = NearestNeighbors(n_neighbors=n_neighbors, metric="euclidean")
        self.is_fitted = False
        self.historical_dates = []
        self.historical_returns = {}
        self.feature_cols = HMM_CONFIG["observation_features"]
        self.scaler_mean = None
        self.scaler_std = None

    def fit(self, feature_matrix: pd.DataFrame, returns_series: pd.Series) -> bool:
        """
        Fit the similarity engine on historical features.

        Args:
            feature_matrix: DataFrame containing at least the observation features.
            returns_series: Series containing forward returns (aligned with feature_matrix).
        """
        available_cols = [c for c in self.feature_cols if c in feature_matrix.columns]
        if len(available_cols) < 2:
            logger.error("Not enough features to fit similarity engine.")
            return False

        obs_df = feature_matrix[available_cols].dropna()
        if len(obs_df) < self.n_neighbors:
            logger.warning("Not enough history to fit similarity engine.")
            return False

        # Scale features
        X = obs_df.values.astype(float)
        self.scaler_mean = np.mean(X, axis=0)
        self.scaler_std = np.std(X, axis=0)
        self.scaler_std[self.scaler_std == 0] = 1.0
        X_scaled = (X - self.scaler_mean) / self.scaler_std

        # Fit KNN
        self.knn.fit(X_scaled)
        self.historical_dates = list(obs_df.index)
        
        # Map dates to future returns
        for date in self.historical_dates:
            if date in returns_series.index:
                self.historical_returns[str(date)] = float(returns_series.loc[date])

        self.is_fitted = True
        logger.info(f"Regime Similarity Engine fitted with {len(X)} historical periods.")
        return True

    def find_similar_periods(self, current_features: Dict[str, float]) -> List[Dict]:
        """
        Find the most similar historical periods for a given feature vector.

        Returns:
            List of dicts: [{"date": YYYY-MM-DD, "distance": float, "return": float}]
        """
        if not self.is_fitted:
            return []

        available_cols = [c for c in self.feature_cols if c in current_features]
        if len(available_cols) < 2:
            return []

        # Build and scale current observation
        obs = np.array([[current_features.get(c, 0.0) for c in available_cols]])
        obs_scaled = (obs - self.scaler_mean[:len(available_cols)]) / self.scaler_std[:len(available_cols)]

        # Find neighbors
        distances, indices = self.knn.kneighbors(obs_scaled)
        
        similar_periods = []
        for dist, idx in zip(distances[0], indices[0]):
            hist_date_ts = self.historical_dates[idx]
            # Convert pandas Timestamp to string if necessary
            if hasattr(hist_date_ts, "strftime"):
                date_str = hist_date_ts.strftime("%Y-%m-%d")
            else:
                date_str = str(hist_date_ts)
                
            future_return = self.historical_returns.get(str(hist_date_ts), 0.0)
            
            similar_periods.append({
                "date": date_str,
                "distance": round(float(dist), 4),
                "historical_return": round(future_return, 4)
            })

        return similar_periods

    def save(self, filepath: Optional[str] = None):
        """Save the fitted Similarity engine to disk."""
        import os, pickle
        from prediction.config import MODEL_DIR
        
        if filepath is None:
            filepath = os.path.join(MODEL_DIR, "similarity_engine.pkl")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        state = {
            "knn": self.knn,
            "historical_dates": self.historical_dates,
            "historical_returns": self.historical_returns,
            "scaler_mean": self.scaler_mean,
            "scaler_std": self.scaler_std,
            "is_fitted": self.is_fitted,
        }
        with open(filepath, "wb") as f:
            pickle.dump(state, f)
        logger.info(f"Similarity engine saved to {filepath}")

    def load(self, filepath: Optional[str] = None) -> bool:
        """Load a fitted Similarity engine from disk."""
        import os, pickle
        from prediction.config import MODEL_DIR
        
        if filepath is None:
            filepath = os.path.join(MODEL_DIR, "similarity_engine.pkl")
        if not os.path.exists(filepath):
            logger.warning(f"Similarity engine file not found: {filepath}")
            return False
        try:
            with open(filepath, "rb") as f:
                state = pickle.load(f)
            self.knn = state["knn"]
            self.historical_dates = state["historical_dates"]
            self.historical_returns = state["historical_returns"]
            self.scaler_mean = state["scaler_mean"]
            self.scaler_std = state["scaler_std"]
            self.is_fitted = state.get("is_fitted", True)
            logger.info(f"Similarity engine loaded from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error loading similarity engine: {e}")
            return False
