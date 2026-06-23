from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple
import pandas as pd

from prediction.features.feature_matrix import build_daily_feature_vector, build_historical_feature_matrix
from prediction.features.transformations import FeatureTransformer

logger = logging.getLogger(__name__)

class FeatureStoreService:
    """
    Centralized service for building, transforming, and retrieving features.
    Ensures that transformations (Scaling/Imputation/PCA) are strictly fit
    on training data to prevent look-ahead bias, and seamlessly applied during
    live daily inference.
    """

    def __init__(self, use_pca: bool = False):
        self.transformer = FeatureTransformer(use_pca=use_pca)

    def fit_transform_historical(self, 
                                 price_history: pd.DataFrame,
                                 curve_history: Optional[pd.DataFrame] = None,
                                 eia_history: Optional[pd.DataFrame] = None,
                                 cftc_history: Optional[pd.DataFrame] = None,
                                 macro_history: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Builds the raw historical feature matrix and fits the transformer.
        Returns (raw_df, transformed_df).
        """
        raw_df = build_historical_feature_matrix(
            price_history=price_history,
            curve_history=curve_history,
            eia_history=eia_history,
            cftc_history=cftc_history,
            macro_history=macro_history
        )
        
        if raw_df.empty:
            return raw_df, raw_df
            
        # Fit and transform
        self.transformer.fit(raw_df)
        transformed_df = self.transformer.transform(raw_df)
        
        return raw_df, transformed_df

    def transform_historical(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform a raw feature matrix using a pre-fitted transformer.
        (Used during walk-forward validation for test sets).
        """
        return self.transformer.transform(raw_df)

    def build_and_transform_daily(self,
                                  date_str: str,
                                  curve_prices: Optional[Dict[str, float]] = None,
                                  prev_curves: Optional[list] = None,
                                  closes: Optional[list] = None,
                                  highs: Optional[list] = None,
                                  lows: Optional[list] = None,
                                  eia_data: Optional[Dict] = None,
                                  cftc_data: Optional[Dict] = None,
                                  macro_data: Optional[Dict] = None,
                                  regime_label: Optional[str] = None,
                                  regime_severity: Optional[float] = None,
                                  regime_age_days: Optional[int] = None) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Build the daily feature vector and transform it using the fitted scaler/imputer.
        Returns: (raw_features, transformed_features)
        """
        raw_features = build_daily_feature_vector(
            date_str=date_str,
            curve_prices=curve_prices,
            prev_curves=prev_curves,
            closes=closes,
            highs=highs,
            lows=lows,
            eia_data=eia_data,
            cftc_data=cftc_data,
            macro_data=macro_data,
            regime_label=regime_label,
            regime_severity=regime_severity,
            regime_age_days=regime_age_days
        )
        
        # Transform the single vector
        transformed_features = self.transformer.transform_dict(raw_features)
        return raw_features, transformed_features

    def save(self):
        """Save the fitted transformers."""
        self.transformer.save()

    def load(self) -> bool:
        """Load pre-fitted transformers for daily inference."""
        return self.transformer.load()

    def apply_adaptive_weights(self, features: Dict[str, float], regime_label: str) -> Dict[str, float]:
        """
        Dynamically scale the importance of feature blocks based on the prevailing regime.
        This provides Adaptive Multi-Factor Weights by adjusting feature magnitudes.
        """
        if not features or not regime_label:
            return features
            
        scaled_features = features.copy()
        
        # Define factor blocks
        curve_features = ["m1_m2_spread", "m1_m12_spread", "fly_1_6_11", "front_carry", "roll_yield"]
        tech_features = ["rsi_14", "macd", "bbands_width", "stoch_k", "stoch_d"]
        macro_features = ["dxy_return", "sp500_return", "us10y_yield"]
        
        if regime_label in ["EXTREME_BACKWARDATION", "BACKWARDATION"]:
            # In severe backwardation, physical tightness drives price. Boost curve signals.
            for col in curve_features:
                if col in scaled_features:
                    scaled_features[col] *= 1.5
            for col in tech_features:
                if col in scaled_features:
                    scaled_features[col] *= 0.8  # Mean-reversion fails in strong trends
                    
        elif regime_label in ["EXTREME_CONTANGO", "CONTANGO"]:
            # In contango, oversupply makes market sensitive to macro and mean-reversion.
            for col in tech_features:
                if col in scaled_features:
                    scaled_features[col] *= 1.3
            for col in macro_features:
                if col in scaled_features:
                    scaled_features[col] *= 1.2
                    
        return scaled_features

