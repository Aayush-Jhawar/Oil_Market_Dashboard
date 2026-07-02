"""Shared constants + import-path helper for the fresh ML harness.

The reused feature builders live under ``backend/legacy_archive/prediction`` and
import each other as ``prediction.features.*``. That only resolves when
``backend/legacy_archive`` is on ``sys.path`` (exactly what
``legacy_archive/prediction/feature_store.py`` does at import time). Call
``ensure_prediction_importable()`` before importing any ``prediction.*`` module.
"""
from __future__ import annotations

import os
import sys

# .../backend/ml/paths.py -> _ML_DIR = .../backend/ml ; _BACKEND = .../backend
_ML_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_ML_DIR)
_LEGACY = os.path.join(_BACKEND, "legacy_archive")

ARTIFACT_DIR = os.path.join(_ML_DIR, "artifacts")

# The five outright commodities the composite gauge cycles through.
SYMBOLS = ["WTI", "Brent", "RBOB", "HO", "GO"]

# Forward-looking horizons (trading days). Keys are the labels used everywhere
# (artifact filenames, API query params, DB rows).
HORIZONS = {"1d": 1, "5d": 5, "21d": 21}
DEFAULT_HORIZON = "5d"

# Candidate model keys (see models.py). Order is display order.
CANDIDATES = ["lightgbm", "logreg", "momentum"]

# Namespace stamped onto rows this harness writes into the shared energy.db
# tables (model_metadata / predictions), so they stay separable from the stale
# legacy prediction rows and can be queried / re-trained without collision.
MODEL_NS = "mfa_v1"  # multi-factor-analytics v1

# Deterministic seed used across every candidate + split.
RANDOM_SEED = 42


def ensure_prediction_importable() -> None:
    """Put ``backend`` and ``backend/legacy_archive`` on ``sys.path`` so the
    reused ``prediction.features.*`` builders import cleanly from any entrypoint."""
    for p in (_BACKEND, _LEGACY):
        if p not in sys.path:
            sys.path.insert(0, p)


def artifact_path(name: str) -> str:
    """Absolute path inside the artifacts dir; creates the dir on first use."""
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    return os.path.join(ARTIFACT_DIR, name)


def model_artifact_name(symbol: str, horizon: str) -> str:
    return f"{symbol}_{horizon}.joblib"


def oos_artifact_name(symbol: str, horizon: str) -> str:
    return f"oos_{symbol}_{horizon}.parquet"


MANIFEST_NAME = "manifest.json"
