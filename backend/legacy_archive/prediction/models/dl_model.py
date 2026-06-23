"""
Machine Learning Model (LightGBM)
===========================
Replaces PyTorch MLP with a powerful LightGBM model based on academic papers
highlighting its superior performance for tabular financial forecasting.
Optimized for predicting market direction and return magnitude.
"""
from __future__ import annotations

import logging
import lightgbm as lgb
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import joblib
from pathlib import Path

logger = logging.getLogger(__name__)

class DeepLearningModel:
    """
    LightGBM-based model for direction and return forecasting.
    Kept the class name 'DeepLearningModel' to avoid breaking imports, 
    but the implementation is mathematically sound LightGBM.
    """

    def __init__(
        self,
        horizon: int = 5,
        model_type: str = "direction",
        name: str = "global",
    ):
        self.horizon = horizon
        self.model_type = model_type  # "direction" or "return"
        self.name = name
        self.model = None
        self.base_model = None
        self.feature_names: List[str] = []
        self.is_fitted = False

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        eval_set: Optional[Tuple[pd.DataFrame, pd.Series]] = None,
        tune: bool = False,
    ) -> Dict:
        mask = ~y.isna()
        X_clean = X.loc[mask].copy()
        y_clean = y.loc[mask].copy()
        weights = sample_weight[mask.values] if sample_weight is not None else np.ones(len(y_clean))

        if len(X_clean) < 50:
            logger.error(f"Insufficient training data: {len(X_clean)} samples")
            return {"error": f"Insufficient data: {len(X_clean)} samples"}

        X_clean = X_clean.replace([np.inf, -np.inf], np.nan).fillna(0)
        self.feature_names = list(X_clean.columns)

        is_class = self.model_type == "direction"
        
        if is_class:
            base_model = lgb.LGBMClassifier(
                n_estimators=150,
                learning_rate=0.05,
                max_depth=5,
                num_leaves=15,
                subsample=0.8,
                colsample_bytree=0.8,
                class_weight='balanced',
                random_state=42,
                n_jobs=-1
            )
            base_model.fit(X_clean, y_clean, sample_weight=weights)
            self.base_model = base_model
            
            from sklearn.calibration import CalibratedClassifierCV
            from prediction.validation.purged_cv import generate_purged_walk_forward_splits
            
            # Use Purged Walk-Forward CV for proper out-of-sample calibration to prevent time-series data leakage
            cv_splits = generate_purged_walk_forward_splits(
                n_samples=len(X_clean),
                min_train_size=max(100, int(len(X_clean) * 0.5)),
                test_size=max(50, int(len(X_clean) * 0.1)),
                horizon_periods=self.horizon,
                embargo_periods=self.horizon,
                expanding=True
            )
            
            if not cv_splits:
                # Fallback if extremely small dataset
                self.model = CalibratedClassifierCV(estimator=base_model, method='isotonic', cv="prefit")
            else:
                self.model = CalibratedClassifierCV(estimator=base_model, method='isotonic', cv=cv_splits)
                
            self.model.fit(X_clean, y_clean, sample_weight=weights)
        else:
            self.model = lgb.LGBMRegressor(
                n_estimators=150,
                learning_rate=0.05,
                max_depth=5,
                num_leaves=15,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1
            )
            self.model.fit(X_clean, y_clean, sample_weight=weights)
            self.base_model = self.model

        self.is_fitted = True
        self._n_training_samples = len(X_clean)
        return {"n_samples": len(X_clean)}

    def predict_single(self, features: Dict[str, float]) -> Dict:
        if not self.is_fitted or self.model is None:
            if self.model_type == "direction":
                return {"prediction_label": "NEUTRAL", "prediction_value": 0.5, "confidence": 0.0}
            return {"prediction_value": 0.0}

        x_arr = np.array([features.get(f, 0.0) for f in self.feature_names], dtype=np.float32)
        X_df = pd.DataFrame([x_arr], columns=self.feature_names)

        if self.model_type == "direction":
            prob = self.model.predict_proba(X_df)[0][1]
            confidence = abs(prob - 0.5) * 2.0 
            if prob > 0.55:
                label = "UP"
            elif prob < 0.45:
                label = "DOWN"
            else:
                label = "NEUTRAL"
            return {
                "prediction_label": label,
                "prediction_value": prob,
                "confidence": confidence,
            }
        else:
            out = self.model.predict(X_df)[0]
            return {"prediction_value": float(out)}
            
    def get_feature_importance(self, use_shap: bool = True) -> List[Tuple[str, float]]:
        """
        Get feature importance using SHAP TreeExplainer (preferred) or
        fallback to LightGBM gain-based importance.

        SHAP provides unbiased, theoretically grounded importance values
        while LightGBM's built-in importance is known to be biased toward
        high-cardinality and correlated features.

        Reference: Lundberg & Lee, NeurIPS 2017.
        """
        if not self.is_fitted or self.base_model is None:
            return []

        if use_shap:
            try:
                import shap
                explainer = shap.TreeExplainer(self.base_model)
                # Use a sample of training data if available, else use zeros
                X_background = pd.DataFrame(
                    [np.zeros(len(self.feature_names))],
                    columns=self.feature_names,
                )
                shap_values = explainer.shap_values(X_background)

                # For classification, shap_values may be a list [class_0, class_1]
                if isinstance(shap_values, list):
                    importances = np.abs(shap_values[1]).mean(axis=0)
                else:
                    importances = np.abs(shap_values).mean(axis=0)

                total = np.sum(importances)
                if total > 0:
                    importances = importances / total

                feat_imp = list(zip(self.feature_names, importances))
                feat_imp.sort(key=lambda x: x[1], reverse=True)
                return feat_imp[:15]

            except ImportError:
                logger.warning("shap not installed; falling back to gain-based importance")
            except Exception as e:
                logger.warning(f"SHAP computation failed: {e}; falling back to gain-based")

        # Fallback: LightGBM gain-based (known to be biased)
        importances = self.base_model.feature_importances_
        total = np.sum(importances)
        if total > 0:
            importances = importances / total
        
        feat_imp = list(zip(self.feature_names, importances))
        feat_imp.sort(key=lambda x: x[1], reverse=True)
        return feat_imp[:15]

    def explain_prediction(self, features: Dict[str, float]) -> Dict:
        """
        Generate SHAP-based explanation for a single prediction.

        Returns per-feature SHAP values showing each feature's contribution
        to the prediction, enabling trade justification and debugging.
        """
        if not self.is_fitted or self.base_model is None:
            return {"error": "Model not fitted"}

        try:
            import shap

            x_arr = np.array([features.get(f, 0.0) for f in self.feature_names], dtype=np.float32)
            X_df = pd.DataFrame([x_arr], columns=self.feature_names)

            explainer = shap.TreeExplainer(self.base_model)
            shap_values = explainer.shap_values(X_df)

            # For classification, take class 1 (UP) SHAP values
            if isinstance(shap_values, list):
                sv = shap_values[1][0]
            else:
                sv = shap_values[0]

            # Sort by absolute contribution
            contributions = sorted(
                zip(self.feature_names, sv),
                key=lambda x: abs(x[1]),
                reverse=True,
            )

            return {
                "top_drivers": [
                    {"feature": name, "shap_value": round(float(val), 6)}
                    for name, val in contributions[:10]
                ],
                "base_value": round(float(explainer.expected_value[1])
                    if isinstance(explainer.expected_value, list)
                    else float(explainer.expected_value), 6),
            }

        except ImportError:
            return {"error": "shap library not installed"}
        except Exception as e:
            return {"error": f"SHAP explanation failed: {str(e)}"}

    def _get_path(self) -> Path:
        base_dir = Path(__file__).parent.parent / "saved_models"
        base_dir.mkdir(exist_ok=True, parents=True)
        # Try both suffix conventions: Nd (daily) and Np (1-min periods)
        path_p = base_dir / f"{self.name}_{self.model_type}_{self.horizon}p.pkl"
        path_d = base_dir / f"{self.name}_{self.model_type}_{self.horizon}d.pkl"
        # During LOAD: prefer 'p' suffix (newer 1-min models), fall back to 'd'
        if path_p.exists():
            return path_p
        return path_d

    def save(self):
        if not self.is_fitted:
            return
        path = self._get_path()
        state = {
            "feature_names": self.feature_names,
            "model": self.model,
            "base_model": self.base_model
        }
        joblib.dump(state, path)

    def load(self) -> bool:
        path = self._get_path()
        if not path.exists():
            return False
        try:
            state = joblib.load(path)
            self.feature_names = state["feature_names"]
            self.model = state["model"]
            self.base_model = state.get("base_model", self.model)
            self.is_fitted = True
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Error loading {self.name} from {path}: {e}")
            return False
