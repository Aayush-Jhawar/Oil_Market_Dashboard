"""
HMM Regime Classifier
=======================
Gaussian Hidden Markov Model for probabilistic regime detection.
Uses curve-derived observations to identify latent market states
and compute transition probabilities.

Why HMM:
- Oil regimes are latent states — you observe symptoms (spreads, vol) not the regime
- HMMs model regime persistence (high self-transition probability)
- They output probability distributions over states, not point labels
- Transition matrix gives P(regime_t+1 | regime_t) directly
"""
from __future__ import annotations

import logging
import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try to import hmmlearn; gracefully degrade if not available
try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False
    logger.warning("hmmlearn not installed — HMM regime detection will be disabled")

from prediction.config import HMM_CONFIG, MODEL_DIR


# Label mapping: HMM states → regime labels
# After fitting, we identify which state corresponds to which regime
# by examining the emission means (sorted by spread level)
_REGIME_LABELS = [
    "EXTREME_BACKWARDATION",
    "BACKWARDATION",
    "NEUTRAL",
    "CONTANGO",
    "EXTREME_CONTANGO",
]


class HMMRegimeClassifier:
    """
    Gaussian HMM-based regime classifier for oil markets.

    Observations:
        [m1_m2_spread, m1_m12_spread, fly_1_6_11, front_carry, realized_vol]

    States:
        3 latent states mapped to CONTANGO / NEUTRAL / BACKWARDATION
        based on emission means after fitting.
    """

    def __init__(self, n_regimes: int = 5):
        self.n_regimes = n_regimes
        self.model: Optional[GaussianHMM] = None
        self.state_to_label: Dict[int, str] = {}
        self.observation_cols = HMM_CONFIG["observation_features"]
        self.is_fitted = False
        self.scaler_mean: Optional[np.ndarray] = None
        self.scaler_std: Optional[np.ndarray] = None
        self.pca = None

    def fit(self, feature_matrix: pd.DataFrame) -> bool:
        """
        Fit the HMM on historical features.

        Args:
            feature_matrix: DataFrame with at least the observation columns.

        Returns:
            True if fitting succeeded.
        """
        if not HMM_AVAILABLE:
            logger.error("hmmlearn not available — cannot fit HMM")
            return False

        # Extract observation features
        available_cols = [c for c in self.observation_cols if c in feature_matrix.columns]
        if len(available_cols) < 1:
            logger.error(f"No HMM observation features found in matrix. Available: {list(feature_matrix.columns)}")
            return False
        if len(available_cols) < 2:
            logger.warning(f"Only {len(available_cols)} HMM feature(s) found ({available_cols}); HMM will use vol-only regime classification.")

        # Crucial: update the class observation_cols to ONLY the ones we actually trained on!
        # This prevents dimensionality mismatch during prediction if live data has more features than offline data.
        self.observation_cols = available_cols

        obs_df = feature_matrix[available_cols].dropna()
        if len(obs_df) < HMM_CONFIG["min_training_days"]:
            logger.error(
                f"Need at least {HMM_CONFIG['min_training_days']} observations; "
                f"have {len(obs_df)}"
            )
            return False

        logger.info(f"Fitting HMM with {len(obs_df)} observations, {len(available_cols)} features")

        # Standardize observations
        X = obs_df.values.astype(float)
        self.scaler_mean = np.mean(X, axis=0)
        self.scaler_std = np.std(X, axis=0)
        self.scaler_std[self.scaler_std == 0] = 1.0
        X_scaled = (X - self.scaler_mean) / self.scaler_std

        # Apply PCA
        from sklearn.decomposition import PCA
        n_components = min(3, X_scaled.shape[1])
        self.pca = PCA(n_components=n_components, random_state=42)
        X_pca = self.pca.fit_transform(X_scaled)

        # Fit HMM
        try:
            self.model = GaussianHMM(
                n_components=self.n_regimes,
                covariance_type=HMM_CONFIG["covariance_type"],
                n_iter=HMM_CONFIG["n_iter"],
                random_state=HMM_CONFIG["random_state"],
            )
            self.model.fit(X_pca)
            self.is_fitted = True
        except Exception as e:
            logger.error(f"HMM fitting failed: {e}")
            return False

        # Map states to regime labels based on emission means
        self._map_states_to_labels(available_cols)

        logger.info(f"HMM fitted. State mapping: {self.state_to_label}")
        logger.info(f"Transition matrix:\n{np.round(self.model.transmat_, 3)}")

        return True

    def _map_states_to_labels(self, available_cols: List[str]):
        """
        Map HMM states to regime labels by examining the emission means.

        The key insight: in backwardation, M1-M12 spread is negative (front premium),
        and in contango it's positive (front discount). We use the mean of the
        m1_m12_spread or m1_m2_spread emission to assign labels.
        """
        if self.model is None:
            return

        # Find the column index for m1_m12_spread or m1_m2_spread
        spread_col_idx = None
        for i, col in enumerate(available_cols):
            if col == "m1_m12_spread":
                spread_col_idx = i
                break
        if spread_col_idx is None:
            for i, col in enumerate(available_cols):
                if col == "m1_m2_spread":
                    spread_col_idx = i
                    break

        if spread_col_idx is None:
            # Fallback: use first column
            spread_col_idx = 0
            logger.warning("No spread column found; using first observation for state mapping")

        # Get the mean of the spread observation for each state
        # Note: means are in PCA space, so we need to inverse_transform to scaled space, then un-scale
        means_pca = self.model.means_
        means_scaled = self.pca.inverse_transform(means_pca)
        means_scaled_col = means_scaled[:, spread_col_idx]
        means_original = means_scaled_col * self.scaler_std[spread_col_idx] + self.scaler_mean[spread_col_idx]

        # Sort: most negative mean = backwardation, most positive = contango
        sorted_indices = np.argsort(means_original)

        # Map: sorted from most negative (extreme backwardation) to most positive (extreme contango)
        # M1-M12 < 0 means front premium = backwardation
        n = len(sorted_indices)
        if n >= 5:
            self.state_to_label = {
                int(sorted_indices[0]): "EXTREME_BACKWARDATION",
                int(sorted_indices[1]): "BACKWARDATION",
                int(sorted_indices[2]): "NEUTRAL",
                int(sorted_indices[3]): "CONTANGO",
                int(sorted_indices[4]): "EXTREME_CONTANGO",
            }
        elif n == 4:
            self.state_to_label = {
                int(sorted_indices[0]): "EXTREME_BACKWARDATION",
                int(sorted_indices[1]): "BACKWARDATION",
                int(sorted_indices[2]): "CONTANGO",
                int(sorted_indices[3]): "EXTREME_CONTANGO",
            }
        else:
            self.state_to_label = {
                int(sorted_indices[0]): "BACKWARDATION",
                int(sorted_indices[1]): "NEUTRAL",
                int(sorted_indices[min(2, n - 1)]): "CONTANGO",
            }

    def predict(self, feature_vector: Dict[str, float]) -> Dict:
        """
        Predict regime probabilities for a single observation.

        Args:
            feature_vector: Dict with observation feature values.

        Returns:
            Dict with regime probabilities and most likely state.
        """
        if not self.is_fitted or self.model is None:
            return self._default_result()

        # Build observation vector
        available_cols = [c for c in self.observation_cols if c in feature_vector]
        if len(available_cols) < 2:
            return self._default_result()

        obs = np.array([[feature_vector.get(c, 0.0) for c in available_cols]])

        # Scale and PCA
        scaler_mean = self.scaler_mean[:len(available_cols)]
        scaler_std = self.scaler_std[:len(available_cols)]
        obs_scaled = (obs - scaler_mean) / scaler_std
        obs_pca = self.pca.transform(obs_scaled)

        try:
            # Get log-likelihood of each state and posteriors
            log_probs, posteriors = self.model.score_samples(obs_pca)

            # posteriors shape: (1, n_regimes) — probability of each state
            if isinstance(posteriors, np.ndarray) and posteriors.ndim == 2:
                probs = posteriors[0]
            else:
                probs = np.ones(self.n_regimes) / self.n_regimes
        except Exception:
            # Fallback: use predict_proba if available, otherwise decode
            try:
                states = self.model.predict(obs_scaled)
                probs = np.zeros(self.n_regimes)
                probs[states[0]] = 1.0
            except Exception as e:
                logger.debug(f"HMM prediction failed: {e}")
                return self._default_result()

        # Map to labeled probabilities
        probabilities = {}
        transitions = {}
        
        result = {
            "probabilities": probabilities,
            "transitions": transitions,
            "hmm_most_likely": "NEUTRAL",
            "hmm_confidence": 0.0,
        }

        max_prob = 0.0
        max_label = "NEUTRAL"
        for state_idx, label in self.state_to_label.items():
            if state_idx < len(probs):
                prob = float(probs[state_idx])
                probabilities[label] = round(prob, 4)
                if prob > max_prob:
                    max_prob = prob
                    max_label = label

        result["hmm_most_likely"] = max_label
        result["hmm_confidence"] = round(max_prob, 4)

        # Transition probabilities (from current most-likely state)
        most_likely_state = max(self.state_to_label.keys(), key=lambda s: probs[s] if s < len(probs) else 0)
        trans_probs = self.model.transmat_[most_likely_state]
        for state_idx, label in self.state_to_label.items():
            if state_idx < len(trans_probs):
                transitions[label] = round(float(trans_probs[state_idx]), 4)

        return result

    def predict_history(self, feature_matrix: pd.DataFrame) -> pd.DataFrame:
        """
        Decode regime states for the full history using Viterbi algorithm.

        Returns DataFrame with regime labels and probabilities aligned to input index.
        """
        if not self.is_fitted or self.model is None:
            return pd.DataFrame()

        available_cols = [c for c in self.observation_cols if c in feature_matrix.columns]
        if len(available_cols) < 2:
            return pd.DataFrame()

        obs_df = feature_matrix[available_cols].copy()
        # Forward-fill NaN within the observation matrix
        obs_df = obs_df.ffill().fillna(0)

        X = obs_df.values.astype(float)
        scaler_mean = self.scaler_mean[:len(available_cols)]
        scaler_std = self.scaler_std[:len(available_cols)]
        X_scaled = (X - scaler_mean) / scaler_std
        X_pca = self.pca.transform(X_scaled)

        try:
            # Viterbi decoding
            _, state_sequence = self.model.decode(X_pca)
        except Exception as e:
            logger.error(f"HMM decoding failed: {e}")
            return pd.DataFrame()

        # Map state indices to labels
        labels = [self.state_to_label.get(s, "NEUTRAL") for s in state_sequence]

        result = pd.DataFrame(
            {"regime_label": labels, "hmm_state": state_sequence},
            index=obs_df.index,
        )

        # Compute regime age (consecutive days in same regime)
        age = np.ones(len(labels), dtype=int)
        for i in range(1, len(labels)):
            if labels[i] == labels[i - 1]:
                age[i] = age[i - 1] + 1
            else:
                age[i] = 1
        result["regime_age_days"] = age

        return result

    def save(self, filepath: Optional[str] = None):
        """Save the fitted HMM to disk."""
        if filepath is None:
            filepath = os.path.join(MODEL_DIR, "hmm_regime.pkl")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        state = {
            "model": self.model,
            "state_to_label": self.state_to_label,
            "scaler_mean": self.scaler_mean,
            "scaler_std": self.scaler_std,
            "observation_cols": self.observation_cols,
            "is_fitted": self.is_fitted,
            "pca": self.pca,
        }
        with open(filepath, "wb") as f:
            pickle.dump(state, f)
        logger.info(f"HMM model saved to {filepath}")

    def load(self, filepath: Optional[str] = None) -> bool:
        """Load a fitted HMM from disk."""
        if filepath is None:
            filepath = os.path.join(MODEL_DIR, "hmm_regime.pkl")
        if not os.path.exists(filepath):
            logger.warning(f"HMM model file not found: {filepath}")
            return False
        try:
            with open(filepath, "rb") as f:
                state = pickle.load(f)
            self.model = state["model"]
            self.state_to_label = state["state_to_label"]
            self.scaler_mean = state["scaler_mean"]
            self.scaler_std = state["scaler_std"]
            self.observation_cols = state.get("observation_cols", self.observation_cols)
            self.is_fitted = state.get("is_fitted", True)
            self.pca = state.get("pca", None)
            logger.info(f"HMM model loaded from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error loading HMM model: {e}")
            return False

    @staticmethod
    def _default_result() -> Dict:
        return {
            "probabilities": {
                "EXTREME_BACKWARDATION": 0.10,
                "BACKWARDATION": 0.20,
                "NEUTRAL": 0.40,
                "CONTANGO": 0.20,
                "EXTREME_CONTANGO": 0.10,
            },
            "transitions": {
                "EXTREME_BACKWARDATION": 0.10,
                "BACKWARDATION": 0.20,
                "NEUTRAL": 0.40,
                "CONTANGO": 0.20,
                "EXTREME_CONTANGO": 0.10,
            },
            "hmm_most_likely": "NEUTRAL",
            "hmm_confidence": 0.40,
        }
