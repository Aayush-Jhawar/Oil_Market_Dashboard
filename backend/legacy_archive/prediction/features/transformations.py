from __future__ import annotations

import logging
import pickle
import os
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer

from prediction.config import MODEL_DIR

logger = logging.getLogger(__name__)

class FeatureTransformer:
    """
    Stateful transformer for feature engineering.
    Handles imputation, scaling, and optional PCA.
    Must be fit ONLY on the training data to prevent look-ahead bias.
    """

    def __init__(self, use_pca: bool = False, pca_variance: float = 0.95):
        self.use_pca = use_pca
        self.pca_variance = pca_variance
        
        self.scaler = StandardScaler()
        self.imputer = SimpleImputer(strategy="median")
        self.pca = PCA(n_components=self.pca_variance) if use_pca else None
        
        self.feature_columns: List[str] = []
        self.pca_columns: List[str] = []
        self.is_fitted = False

    def fit(self, df: pd.DataFrame) -> None:
        """
        Fit the transformations on the training dataset.
        """
        # Save feature column order
        self.feature_columns = list(df.columns)
        
        # 1. Fit Imputer
        X_imputed = self.imputer.fit_transform(df.values)
        
        # 2. Fit Scaler
        X_scaled = self.scaler.fit_transform(X_imputed)
        
        # 3. Fit PCA
        if self.use_pca and self.pca is not None:
            self.pca.fit(X_scaled)
            n_components = self.pca.n_components_
            self.pca_columns = [f"pca_{i}" for i in range(n_components)]
            logger.info(f"PCA fitted: {len(self.feature_columns)} features reduced to {n_components} components (retaining {self.pca_variance*100}% variance).")

        self.is_fitted = True
        logger.info(f"FeatureTransformer fitted on {len(df)} samples, {len(self.feature_columns)} features.")

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform a dataset (train or test) using the fitted parameters.
        """
        if not self.is_fitted:
            logger.warning("FeatureTransformer is not fitted. Returning original DataFrame.")
            return df

        # Ensure column order matches training data
        missing_cols = [c for c in self.feature_columns if c not in df.columns]
        if missing_cols:
            # Add missing columns with NaN to allow imputer to handle them
            for col in missing_cols:
                df[col] = np.nan
                
        # Reorder columns
        X = df[self.feature_columns].values
        
        # 1. Impute
        X_imputed = self.imputer.transform(X)
        
        # 2. Scale
        X_scaled = self.scaler.transform(X_imputed)
        
        # 3. PCA
        if self.use_pca and self.pca is not None:
            X_pca = self.pca.transform(X_scaled)
            return pd.DataFrame(X_pca, index=df.index, columns=self.pca_columns)
        
        return pd.DataFrame(X_scaled, index=df.index, columns=self.feature_columns)

    def transform_dict(self, features: Dict[str, float]) -> Dict[str, float]:
        """
        Transform a single feature vector (used during daily live inference).
        """
        if not self.is_fitted:
            return features
            
        # Build DataFrame with 1 row to reuse logic
        df = pd.DataFrame([features])
        
        # Add any missing features that the model expects as NaNs
        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = np.nan
                
        transformed_df = self.transform(df)
        
        return transformed_df.iloc[0].to_dict()

    def save(self, filepath: Optional[str] = None) -> None:
        """Save the fitted transformer state."""
        if filepath is None:
            filepath = os.path.join(MODEL_DIR, "feature_transformer.pkl")
            
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        state = {
            "use_pca": self.use_pca,
            "pca_variance": self.pca_variance,
            "scaler": self.scaler,
            "imputer": self.imputer,
            "pca": self.pca,
            "feature_columns": self.feature_columns,
            "pca_columns": self.pca_columns,
            "is_fitted": self.is_fitted,
        }
        with open(filepath, "wb") as f:
            pickle.dump(state, f)
        logger.info(f"FeatureTransformer saved to {filepath}")

    def load(self, filepath: Optional[str] = None) -> bool:
        """Load a fitted transformer from disk."""
        if filepath is None:
            filepath = os.path.join(MODEL_DIR, "feature_transformer.pkl")
            
        if not os.path.exists(filepath):
            logger.warning(f"FeatureTransformer file not found: {filepath}")
            return False
            
        try:
            with open(filepath, "rb") as f:
                state = pickle.load(f)
            self.use_pca = state["use_pca"]
            self.pca_variance = state["pca_variance"]
            self.scaler = state["scaler"]
            self.imputer = state["imputer"]
            self.pca = state["pca"]
            self.feature_columns = state["feature_columns"]
            self.pca_columns = state["pca_columns"]
            self.is_fitted = state["is_fitted"]
            logger.info(f"FeatureTransformer loaded from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error loading FeatureTransformer: {e}")
            return False
