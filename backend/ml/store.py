"""Persistence for the harness.

Primary store = small git-tracked files under ``backend/ml/artifacts/`` (fast,
ships to the Space, no risk of locking the 2 GB OneDrive ``energy.db``):
  - ``{symbol}_{horizon}.joblib``   selected model + feature_names + metadata
  - ``oos_{symbol}_{horizon}.parquet``  raw out-of-sample predictions (w/ actuals)
  - ``manifest.json``               leaderboard + per-candidate metrics + best series

Secondary (best-effort) mirror of the 15-row leaderboard into the existing
``model_metadata`` table, so the schema stays consistent with the legacy design.
Any DB failure is swallowed — the files remain the source of truth.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Dict, List, Optional

import joblib
import pandas as pd

from ml.paths import (
    ARTIFACT_DIR, MANIFEST_NAME, MODEL_NS, artifact_path,
    ensure_prediction_importable, model_artifact_name, oos_artifact_name,
)

logger = logging.getLogger(__name__)

# Series stored only for the winning candidate (keeps manifest lean).
_BEST_ONLY_KEYS = ("calibration", "precision_by_confidence", "hit_rate_over_time",
                   "equity_curve", "top_features")
# Scalar metrics stored for every candidate.
_SCALAR_KEYS = ("accuracy", "base_rate", "precision_high_conf", "high_conf_n",
                "brier", "win_rate", "n_bets", "total_return", "n_oos")


def save_model_artifact(symbol, horizon, model, feature_names, best_name,
                        training_end_date, trained_at) -> str:
    path = artifact_path(model_artifact_name(symbol, horizon))
    joblib.dump({
        "model": model,
        "feature_names": list(feature_names),
        "best_name": best_name,
        "symbol": symbol,
        "horizon": horizon,
        "training_end_date": training_end_date,
        "trained_at": trained_at,
    }, path)
    return path


def save_oos(symbol, horizon, oos_df: pd.DataFrame) -> str:
    path = artifact_path(oos_artifact_name(symbol, horizon))
    df = oos_df.copy()
    df["pred_dir"] = (df["p_up"] >= 0.5).astype(int)
    df["correct"] = (df["pred_dir"] == df["actual_dir"]).astype(int)
    df.to_parquet(path)
    return path


def build_manifest_entry(symbol, horizon, results: Dict, best_name, underperforms,
                         n_samples, n_features, training_end_date) -> Dict:
    candidates = {}
    for name, m in results.items():
        candidates[name] = {k: m.get(k) for k in _SCALAR_KEYS}
    best_series = {k: results[best_name].get(k) for k in _BEST_ONLY_KEYS}
    return {
        "symbol": symbol,
        "horizon": horizon,
        "best_model": best_name,
        "underperforms_random": bool(underperforms),
        "n_training_samples": int(n_samples),
        "n_features": int(n_features),
        "training_end_date": training_end_date,
        "candidates": candidates,
        **best_series,
    }


def write_manifest(entries: List[Dict], generated_at: str) -> str:
    path = artifact_path(MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": generated_at, "models": entries}, f, indent=2, default=str)
    return path


# ── Readers (used by endpoints + inference) ──────────────────────────────────

def load_manifest() -> Optional[Dict]:
    path = os.path.join(ARTIFACT_DIR, MANIFEST_NAME)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_model_artifact(symbol, horizon) -> Optional[Dict]:
    path = os.path.join(ARTIFACT_DIR, model_artifact_name(symbol, horizon))
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def load_oos(symbol, horizon) -> Optional[pd.DataFrame]:
    path = os.path.join(ARTIFACT_DIR, oos_artifact_name(symbol, horizon))
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        # e.g. on a deploy where *.parquet is an unresolved Git-LFS pointer.
        # The manifest-based charts still work; only the raw OOS table is lost.
        logger.warning("load_oos(%s/%s) unreadable (LFS pointer?): %s", symbol, horizon, e)
        return None


# ── Best-effort DB mirror ────────────────────────────────────────────────────

def mirror_to_model_metadata(entry: Dict, trained_at: str, hyperparams: Dict) -> None:
    """Upsert one leaderboard row into energy.db:model_metadata. Best-effort."""
    ensure_prediction_importable()
    try:
        from database import DB_PATH
        best = entry["candidates"][entry["best_model"]]
        row_id = f"{MODEL_NS}_{entry['symbol']}_{entry['horizon']}"
        regime_blob = json.dumps({
            "candidates": entry["candidates"],
            "calibration": entry.get("calibration"),
            "precision_by_confidence": entry.get("precision_by_confidence"),
            "hit_rate_over_time": entry.get("hit_rate_over_time"),
            "equity_curve": entry.get("equity_curve"),
            "underperforms_random": entry["underperforms_random"],
        }, default=str)
        con = sqlite3.connect(DB_PATH, timeout=30)
        try:
            con.execute("""
                INSERT OR REPLACE INTO model_metadata
                (id, model_name, model_version, trained_at, training_end_date,
                 n_training_samples, n_features, hyperparameters_json,
                 wf_accuracy, wf_precision_high_conf, wf_sharpe, wf_brier_score,
                 top_features_json, regime_metrics_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row_id,
                f"{entry['symbol']}_{entry['horizon']}_{entry['best_model']}",
                MODEL_NS, trained_at, entry["training_end_date"],
                entry["n_training_samples"], entry["n_features"], json.dumps(hyperparams, default=str),
                best.get("accuracy"), best.get("precision_high_conf"),
                best.get("win_rate"), best.get("brier"),
                json.dumps(entry.get("top_features", {}), default=str), regime_blob,
            ))
            con.commit()
        finally:
            con.close()
    except Exception as e:  # never fail training on a DB hiccup
        logger.warning("mirror_to_model_metadata(%s/%s) skipped: %s",
                       entry.get("symbol"), entry.get("horizon"), e)
