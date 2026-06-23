"""
SHAP Explainer
================
Uses SHAP (SHapley Additive exPlanations) to explain individual predictions
from the LightGBM models. Quantifies exactly how much each feature
contributed to the final probability/return forecast.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    logger.warning("shap not installed — explainability will be disabled")

from prediction.models.ensemble import ModelEnsemble


def explain_prediction(
    ensemble: ModelEnsemble,
    features: Dict[str, float],
    regime_label: str,
    top_n: int = 5,
) -> Dict:
    """
    Explain a single prediction using TreeExplainer.

    Returns the top N bullish features (pushing prediction UP) and
    top N bearish features (pushing prediction DOWN) from the model
    that was primarily used for this regime.
    """
    if not SHAP_AVAILABLE:
        return {"error": "shap not installed"}

    # Determine which model to explain
    # We explain the regime model if fitted, otherwise the global model
    model_obj = None
    if regime_label in ensemble.regime_models:
        rm = ensemble.regime_models[regime_label]
        if rm.is_fitted and rm.model is not None:
            model_obj = rm
    
    if model_obj is None:
        model_obj = ensemble.global_model
        
    if not model_obj.is_fitted or model_obj.model is None:
        return {"error": "Model not fitted"}

    try:
        # Convert features to a DataFrame with exactly the features the model expects
        feature_names = model_obj.feature_names
        X = pd.DataFrame([features])
        missing = set(feature_names) - set(X.columns)
        for col in missing:
            X[col] = np.nan
        X = X[feature_names]

        # Initialize explainer (using lightgbm Booster)
        explainer = shap.TreeExplainer(model_obj.model)
        shap_values = explainer.shap_values(X)

        # LightGBM binary classification returns a list for shap_values [class_0, class_1] in older versions,
        # or a single array (margin) in newer versions.
        # For objective='binary', raw margin is log-odds.
        if isinstance(shap_values, list):
            sv = shap_values[1][0]  # Take class 1 (UP)
        else:
            sv = shap_values[0]     # Margin

        # Pair features with their SHAP values and original values
        contributions = []
        for i, feat_name in enumerate(feature_names):
            val = float(sv[i])
            feat_val = float(X.iloc[0, i])
            if not np.isnan(val) and val != 0:
                contributions.append({
                    "feature": feat_name,
                    "contribution": val,
                    "value": feat_val
                })

        # Sort contributions
        bullish = sorted([c for c in contributions if c["contribution"] > 0], key=lambda x: x["contribution"], reverse=True)
        bearish = sorted([c for c in contributions if c["contribution"] < 0], key=lambda x: x["contribution"])

        return {
            "model_explained": model_obj.name,
            "base_value": float(explainer.expected_value[1] if isinstance(explainer.expected_value, list) else explainer.expected_value),
            "bullish_factors": bullish[:top_n],
            "bearish_factors": bearish[:top_n],
        }

    except Exception as e:
        logger.error(f"Error generating SHAP explanation: {e}")
        return {"error": str(e)}
