"""Live inference: load a trained model and produce a directional probability
for the latest trading day. Models + the latest feature vector are cached with
a short TTL so the 5-second snapshot publisher doesn't rebuild features every
tick (daily features barely move intraday).
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional

from ml.paths import DEFAULT_HORIZON
from ml.store import load_model_artifact, load_manifest
from ml.data import latest_feature_row

logger = logging.getLogger(__name__)

_ARTIFACTS: Dict[tuple, dict] = {}     # (symbol,horizon) -> artifact (models never change until retrain)
_PRED_CACHE: Dict[tuple, tuple] = {}   # (symbol,horizon) -> (ts, result)
_MANIFEST_CACHE: dict = {"ts": 0.0, "data": None}
_PRED_TTL = 300.0                      # seconds
_MANIFEST_TTL = 300.0


def _artifact(symbol: str, horizon: str) -> Optional[dict]:
    key = (symbol, horizon)
    if key not in _ARTIFACTS:
        _ARTIFACTS[key] = load_model_artifact(symbol, horizon)
    return _ARTIFACTS[key]


def _manifest() -> Optional[dict]:
    now = time.time()
    if _MANIFEST_CACHE["data"] is None or now - _MANIFEST_CACHE["ts"] > _MANIFEST_TTL:
        _MANIFEST_CACHE["data"] = load_manifest()
        _MANIFEST_CACHE["ts"] = now
    return _MANIFEST_CACHE["data"]


def _oos_accuracy(symbol: str, horizon: str) -> Optional[float]:
    man = _manifest()
    if not man:
        return None
    for e in man.get("models", []):
        if e["symbol"] == symbol and e["horizon"] == horizon:
            best = e["candidates"].get(e["best_model"], {})
            return best.get("accuracy")
    return None


def _underperforms(symbol: str, horizon: str) -> bool:
    man = _manifest()
    if not man:
        return False
    for e in man.get("models", []):
        if e["symbol"] == symbol and e["horizon"] == horizon:
            return bool(e.get("underperforms_random"))
    return False


def predict_prob(symbol: str, horizon: str = DEFAULT_HORIZON) -> Optional[Dict]:
    """Return {p_up, model_name, horizon, as_of, oos_accuracy, underperforms} or None
    when no model artifact exists for (symbol, horizon)."""
    key = (symbol, horizon)
    now = time.time()
    cached = _PRED_CACHE.get(key)
    if cached and now - cached[0] < _PRED_TTL:
        return cached[1]

    art = _artifact(symbol, horizon)
    if not art:
        return None
    try:
        row, as_of = latest_feature_row(symbol)
        if row is None or row.empty:
            return None
        # Align to the exact training feature set (order + membership).
        X = row.reindex(art["feature_names"]).fillna(0.0).to_frame().T
        p_up = float(art["model"].predict_proba(X)[:, 1][0])
    except Exception as e:
        logger.warning("predict_prob(%s/%s) failed: %s", symbol, horizon, e)
        return None

    result = {
        "p_up": p_up,
        "model_name": art.get("best_name"),
        "horizon": horizon,
        "as_of": as_of,
        "oos_accuracy": _oos_accuracy(symbol, horizon),
        "underperforms": _underperforms(symbol, horizon),
    }
    _PRED_CACHE[key] = (now, result)
    return result


def clear_caches() -> None:
    """Drop cached models/predictions (call after retraining)."""
    _ARTIFACTS.clear()
    _PRED_CACHE.clear()
    _MANIFEST_CACHE.update({"ts": 0.0, "data": None})
