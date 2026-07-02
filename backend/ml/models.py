"""Candidate models for the horse-race. Each exposes the sklearn-style
``fit(X, y)`` / ``predict_proba(X)[:, 1]`` contract so the harness treats them
uniformly. Kept deliberately light — daily samples are small (~1.6-2.3k rows).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.paths import RANDOM_SEED

# Slightly shallower than the legacy LGBM_DIRECTION_PARAMS (config.py:57) to
# curb overfitting on the small daily sample; n_jobs=1 for reproducibility.
LGBM_PARAMS = {
    "objective": "binary",
    "n_estimators": 200,
    "num_leaves": 15,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "min_child_samples": 30,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": RANDOM_SEED,
    "verbose": -1,
    "n_jobs": 1,
}

MOMENTUM_COL = "roc_21d"


class MomentumBaseline:
    """A one-feature logistic on trailing 21-day ROC — the "can the model even
    beat plain momentum?" floor. Calibrated (not just sign) so its Brier score
    is comparable to the other candidates."""

    def __init__(self, col: str = MOMENTUM_COL):
        self.col = col
        self._lr = None
        self._fallback = 0.5

    def fit(self, X: pd.DataFrame, y):
        from sklearn.linear_model import LogisticRegression

        y = np.asarray(y)
        if self.col not in X.columns or len(np.unique(y)) < 2:
            self._fallback = float(np.mean(y)) if len(y) else 0.5
            self._lr = None
            return self
        self._lr = LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)
        self._lr.fit(X[[self.col]].values, y)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        n = len(X)
        if self._lr is None or self.col not in X.columns:
            p = np.full(n, self._fallback, dtype=float)
        else:
            p = self._lr.predict_proba(X[[self.col]].values)[:, 1]
        return np.column_stack([1.0 - p, p])


def make_candidate(name: str):
    """Fresh, unfitted instance of one candidate by key."""
    if name == "lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(**LGBM_PARAMS)
    if name == "logreg":
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import LogisticRegression
        return Pipeline([
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(max_iter=1000, C=0.5, random_state=RANDOM_SEED)),
        ])
    if name == "momentum":
        return MomentumBaseline()
    raise ValueError(f"unknown candidate: {name}")


def feature_importances(model, feature_names) -> dict:
    """Native gain-style importances (no shap dependency). Returns {feat: weight}
    normalized to sum 1, or {} when unavailable."""
    imp = None
    if hasattr(model, "feature_importances_"):          # LGBMClassifier
        imp = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "named_steps") and "lr" in getattr(model, "named_steps", {}):
        imp = np.abs(model.named_steps["lr"].coef_.ravel())  # logistic |coef|
    if imp is None or imp.sum() <= 0 or len(imp) != len(feature_names):
        return {}
    imp = imp / imp.sum()
    return {f: round(float(w), 4) for f, w in zip(feature_names, imp)}
