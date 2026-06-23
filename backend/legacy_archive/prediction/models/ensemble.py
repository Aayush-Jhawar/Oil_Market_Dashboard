"""
Model Ensemble
================
Blends global and regime-specific models based on regime stability.

Architecture:
    Model A: Global model (all data, regime as feature)
    Model B: Regime-specific model (filtered data)
    Ensemble: Blend based on regime stability factor

The ensemble weight shifts toward the regime-specific model when
the regime has been stable (same label for 20+ days), and toward
the global model during transitions.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from prediction.models.dl_model import DeepLearningModel

logger = logging.getLogger(__name__)


class ModelEnsemble:
    """
    Ensemble of global and regime-specific direction models.
    """

    def __init__(self, horizon: int = 5, symbol: str = "WTI"):
        self.horizon = horizon
        self.symbol = symbol

        # Global model (trained on all data)
        self.global_model = DeepLearningModel(
            horizon=horizon, model_type="direction", name=f"{symbol}_global"
        )

        # Return model
        self.return_model = DeepLearningModel(
            horizon=horizon, model_type="return", name=f"{symbol}_global_return"
        )

        # Regime-specific models
        self.regime_models: Dict[str, DeepLearningModel] = {}
        for regime in [
            "EXTREME_BACKWARDATION",
            "BACKWARDATION",
            "NEUTRAL",
            "CONTANGO",
            "EXTREME_CONTANGO",
        ]:
            self.regime_models[regime] = DeepLearningModel(
                horizon=horizon,
                model_type="direction",
                name=f"{symbol}_regime_{regime.lower()}",
            )

        # Kronos Foundation Model
        from prediction.models.kronos_model import KronosModel
        self.kronos_model = KronosModel(horizon=horizon, symbol=symbol)

        self.is_fitted = False

    def fit(
        self,
        X: pd.DataFrame,
        y_direction: pd.Series,
        y_return: pd.Series,
        regime_labels: pd.Series,
        sample_weight: Optional[np.ndarray] = None,
        tune: bool = False,
    ) -> Dict:
        """
        Train all ensemble components.

        Args:
            X: Feature matrix.
            y_direction: Binary direction target.
            y_return: Continuous return target.
            regime_labels: Regime label for each row.

        Returns:
            Training metrics for all models.
        """
        metrics = {}

        # ── Global model ──────────────────────────────────────────────────
        logger.info("Training global direction model...")
        m = self.global_model.fit(X, y_direction, sample_weight=sample_weight, tune=tune)
        metrics["global_direction"] = m

        logger.info("Training global return model...")
        m = self.return_model.fit(X, y_return, sample_weight=sample_weight)
        metrics["global_return"] = m

        for regime, model in self.regime_models.items():
            mask = regime_labels == regime
            X_regime = X.loc[mask]
            y_regime = y_direction.loc[mask]
            w_regime = sample_weight[mask.values] if sample_weight is not None else None

            if len(X_regime) < 100:
                logger.warning(
                    f"Insufficient data for {regime} model "
                    f"({len(X_regime)} samples < 100). Skipping."
                )
                metrics[f"regime_{regime.lower()}"] = {"skipped": True, "n_samples": len(X_regime)}
                continue

            logger.info(f"Training {regime} direction model ({len(X_regime)} samples)...")
            m = model.fit(X_regime, y_regime, sample_weight=w_regime, tune=tune)
            metrics[f"regime_{regime.lower()}"] = m

        self.is_fitted = True
        return metrics

    def predict(
        self,
        features: Dict[str, float],
        regime_label: str = "NEUTRAL",
        regime_age_days: int = 0,
    ) -> Dict:
        """
        Generate ensemble prediction for a single observation.

        Blending weights:
            - Regime stable 30+ days: 40% global, 60% regime
            - Regime stable 10-30 days: 50% global, 50% regime
            - Regime changed < 10 days: 70% global, 30% regime
            - Transition zone: 80% global, 20% regime

        Returns:
            Dict with ensemble prediction, component predictions, and weights.
        """
        # Global prediction
        global_pred = self.global_model.predict_single(features)
        return_pred = self.return_model.predict_single(features)

        # Regime-specific prediction
        regime_model = self.regime_models.get(regime_label)
        if regime_model is not None and regime_model.is_fitted:
            regime_pred = regime_model.predict_single(features)
        else:
            regime_pred = global_pred  # fallback to global

        # ── Forecast Realism Audit & Bounds ───────────────────────────────
        # Determine annualized and period historical volatility from features if available
        # Default to a safe fallback (e.g. 30% annualized)
        ann_vol = features.get("realized_vol_20d", 0.30)
        # Volatility scales with sqrt of time (horizon_days / 252)
        horizon_vol = ann_vol * np.sqrt(self.horizon / 252)
        
        # Max reasonable move is ~2.5 standard deviations (99% confidence interval)
        max_move_pct = horizon_vol * 2.5 * 100
        
        # Base LightGBM Return Prediction
        lgbm_expected_ret_pct = return_pred["prediction_value"] * 100
        
        # Kronos Foundation Model Prediction
        # Pass a dummy recent_closes list for now since it requires integration with price history
        kronos_pred = self.kronos_model.predict_single(features, recent_closes=[])
        kronos_expected_ret_pct = kronos_pred["expected_return"] * 100
        
        # Blending ML (70%) with Foundation Model (30%)
        if self.kronos_model.is_fitted:
            expected_ret_pct = (lgbm_expected_ret_pct * 0.70) + (kronos_expected_ret_pct * 0.30)
        else:
            expected_ret_pct = lgbm_expected_ret_pct
            
        is_unrealistic = False
        
        if abs(expected_ret_pct) > max_move_pct:
            is_unrealistic = True
            # Cap the expected return at the realistic boundary
            expected_ret_pct = max_move_pct if expected_ret_pct > 0 else -max_move_pct

        # ── Compute blending weights (Stability-Dependent Soft Blending) ────
        # Uses regime model stability and training data sufficiency to determine
        # the blend ratio. This replaces both the old naive 50/50 and the
        # overcorrected 100%/0% split.
        if regime_model is not None and regime_model.is_fitted:
            # Determine data sufficiency of the regime model
            regime_n_samples = getattr(regime_model, '_n_training_samples', 500)
            data_sufficient = regime_n_samples >= 300

            if data_sufficient and regime_age_days >= 30:
                # Regime stable 30+ days with sufficient data: heavily favor regime
                w_global, w_regime = 0.15, 0.85
            elif data_sufficient and regime_age_days >= 10:
                # Regime stable 10-30 days: balanced blend
                w_global, w_regime = 0.30, 0.70
            elif regime_age_days < 10:
                # Recent regime change or transition: lean on global for stability
                w_global, w_regime = 0.60, 0.40
            else:
                # Insufficient regime training data: lean on global
                w_global, w_regime = 0.50, 0.50
        else:
            # Fallback to global only if we don't have a regime model at all
            w_global, w_regime = 1.0, 0.0

        # ── Blend direction probability ───────────────────────────────────
        global_prob = global_pred["prediction_value"]
        regime_prob = regime_pred["prediction_value"]
        ensemble_prob = w_global * global_prob + w_regime * regime_prob

        # Direction label
        if ensemble_prob > 0.55:
            label = "UP"
        elif ensemble_prob < 0.45:
            label = "DOWN"
        else:
            label = "NEUTRAL"

        # Confidence: based on probability distance from 0.5 + model agreement
        prob_distance = abs(ensemble_prob - 0.5) * 2
        # Since we use 100% regime model now, agreement with global is less relevant for the score,
        # but we can keep the confidence metric scaled.
        confidence = round(prob_distance, 4)

        return {
            "ensemble_prob": round(ensemble_prob, 4),
            "prediction_label": label,
            "confidence": confidence,
            "expected_return": round(expected_ret_pct, 4),
            "is_unrealistic_flag": is_unrealistic,
            "max_realistic_move_pct": round(max_move_pct, 4),
            "horizon_days": self.horizon,
            "components": {
                "global_prob": round(global_prob, 4),
                "regime_prob": round(regime_prob, 4),
                "w_global": w_global,
                "w_regime": w_regime,
                "regime_model_used": regime_label,
                "regime_age_days": regime_age_days,
            },
        }

    def get_feature_importance(self, regime: Optional[str] = None) -> List[Tuple[str, float]]:
        """Get feature importance from the relevant model."""
        if regime and regime in self.regime_models:
            model = self.regime_models[regime]
            if model.is_fitted:
                return model.get_feature_importance()
        return self.global_model.get_feature_importance()

    def save_all(self):
        """Save all models."""
        self.global_model.save()
        self.return_model.save()
        for model in self.regime_models.values():
            if model.is_fitted:
                model.save()

    def load_all(self) -> bool:
        """Load all models. Returns True if at least the global model loaded."""
        success = self.global_model.load()
        self.return_model.load()
        for model in self.regime_models.values():
            model.load()
        self.kronos_model.load()
        self.is_fitted = success
        return success
