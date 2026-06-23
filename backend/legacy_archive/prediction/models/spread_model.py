"""
LightGBM Spread Model
===========================
Regressor predicting the continuous change (return) of a given spread
(e.g., Crack Spread, Calendar Spread) over a given horizon.

Architecture:
    - LightGBM continuous regressor
    - Predicts the exact magnitude of the spread change
"""
from __future__ import annotations

import logging
import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try importing lightgbm
try:
    import lightgbm as lgb
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False
    logger.warning("lightgbm not installed — prediction models will be disabled")

from prediction.config import LGBM_REGRESSION_PARAMS, MODEL_DIR

class SpreadModel:
    """
    LightGBM-based spread regression model.

    Predicts the expected return/magnitude change of a spread.
    """

    def __init__(
        self,
        horizon: int = 5,
        name: str = "crack_spread",
    ):
        """
        Args:
            horizon: Forecast horizon in trading days (1, 5, or 21).
            name: Model identifier.
        """
        self.horizon = horizon
        self.name = name
        self.model_type = "spread_return"
        self.model = None
        self.feature_names: List[str] = []
        self.is_fitted = False
        self.training_metrics: Dict = {}

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[Tuple[pd.DataFrame, pd.Series]] = None,
    ) -> Dict:
        """
        Train the regressor model.

        Args:
            X: Feature matrix.
            y: Target continuous vector.
            sample_weight: Optional weights.
            eval_set: Optional (X_val, y_val) for early stopping.
        """
        if not LGBM_AVAILABLE:
            logger.error("lightgbm not available")
            return {"error": "lightgbm not installed"}

        # Drop rows with NaN target
        mask = ~y.isna()
        X_clean = X.loc[mask].copy()
        y_clean = y.loc[mask].copy()
        weights = sample_weight[mask.values] if sample_weight is not None else None

        if len(X_clean) < 100:
            logger.error(f"Insufficient training data: {len(X_clean)} samples")
            return {"error": f"Insufficient data: {len(X_clean)} samples"}

        X_clean = X_clean.replace([np.inf, -np.inf], np.nan)
        self.feature_names = list(X_clean.columns)

        params = LGBM_REGRESSION_PARAMS.copy()

        train_data = lgb.Dataset(
            X_clean, label=y_clean,
            weight=weights,
            feature_name=self.feature_names,
            free_raw_data=False,
        )

        valid_sets = [train_data]
        valid_names = ["train"]
        callbacks = [lgb.log_evaluation(period=50)]

        if eval_set is not None:
            X_val, y_val = eval_set
            val_mask = ~y_val.isna()
            X_val = X_val.loc[val_mask].replace([np.inf, -np.inf], np.nan)
            y_val = y_val.loc[val_mask]
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
            valid_sets.append(val_data)
            valid_names.append("valid")
            callbacks.append(lgb.early_stopping(stopping_rounds=30, verbose=True))

        logger.info(
            f"Training {self.name} regressor (horizon={self.horizon}d) "
            f"on {len(X_clean)} samples, {len(self.feature_names)} features"
        )

        n_estimators = params.pop("n_estimators", 300)
        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=n_estimators,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=callbacks,
        )

        self.is_fitted = True

        importance = self.model.feature_importance(importance_type="gain")
        feat_importance = sorted(
            zip(self.feature_names, importance),
            key=lambda x: x[1],
            reverse=True,
        )

        train_preds = self.model.predict(X_clean)
        rmse = float(np.sqrt(np.mean((train_preds - y_clean.values) ** 2)))
        mae = float(np.mean(np.abs(train_preds - y_clean.values)))
        
        self.training_metrics = {
            "train_rmse": round(rmse, 6),
            "train_mae": round(mae, 6),
            "n_samples": len(X_clean),
            "n_features": len(self.feature_names),
            "n_trees": self.model.num_trees(),
            "top_features": feat_importance[:15],
        }

        logger.info(f"Training complete. Metrics: {self.training_metrics}")
        return self.training_metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if not self.is_fitted or self.model is None:
            logger.error(f"Model {self.name} not fitted")
            return np.full(len(X), 0.0)

        X_pred = X.replace([np.inf, -np.inf], np.nan)

        missing = set(self.feature_names) - set(X_pred.columns)
        for col in missing:
            X_pred[col] = np.nan
        X_pred = X_pred[self.feature_names]

        return self.model.predict(X_pred)

    def predict_single(self, features: Dict[str, float]) -> Dict:
        X = pd.DataFrame([features])
        preds = self.predict(X)
        pred_val = float(preds[0])

        # Strict execution heuristic for the backtester:
        # Prevent "money losing machine" churn
        transaction_cost_pt = 0.0135
        legs = 4 if "FLY" in self.name else 3 if "CRACK" in self.name else 2
        
        # ── Dynamic VIX Volatility Scaling ─────────────────────────────────────
        vix = features.get("vix", 20.0)
        vix_scalar = 1.0
        if vix > 25.0:
            vix_scalar = 1.5
        elif vix < 15.0:
            vix_scalar = 0.8
            
        min_expected_change = transaction_cost_pt * legs * 3.0 * vix_scalar

        if abs(pred_val) < min_expected_change:
            label = "NEUTRAL"
        else:
            label = "WIDEN" if pred_val > 0 else "NARROW"
        
        # dynamic confidence scaling (magnitude of expected move)
        expected_move_thresh = 0.02 if "FLY" in self.name else 0.05
        confidence = min(1.0, abs(pred_val) / expected_move_thresh) 

        return {
            "prediction_value": round(pred_val, 6),
            "prediction_label": label,
            "confidence": round(confidence, 4),
            "horizon_days": self.horizon,
            "target": self.model_type,
            "model_version": self.name,
        }

    def save(self, filepath: Optional[str] = None):
        if filepath is None:
            filepath = os.path.join(
                MODEL_DIR,
                f"{self.name}_{self.model_type}_{self.horizon}d.pkl"
            )
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        state = {
            "model": self.model,
            "feature_names": self.feature_names,
            "horizon": self.horizon,
            "model_type": self.model_type,
            "name": self.name,
            "is_fitted": self.is_fitted,
            "training_metrics": self.training_metrics,
        }
        with open(filepath, "wb") as f:
            pickle.dump(state, f)
        logger.info(f"Model saved to {filepath}")

    def load(self, filepath: Optional[str] = None) -> bool:
        if filepath is None:
            filepath = os.path.join(
                MODEL_DIR,
                f"{self.name}_{self.model_type}_{self.horizon}d.pkl"
            )
        if not os.path.exists(filepath):
            return False
        try:
            with open(filepath, "rb") as f:
                state = pickle.load(f)
            self.model = state["model"]
            self.feature_names = state["feature_names"]
            self.horizon = state["horizon"]
            self.model_type = state["model_type"]
            self.name = state["name"]
            self.is_fitted = state.get("is_fitted", True)
            self.training_metrics = state.get("training_metrics", {})
            logger.info(f"Model loaded from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
