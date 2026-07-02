"""FastAPI router for the Model Analytics tab + the gauge's horizon toggle.

Reads the harness outputs (manifest.json + OOS parquet) and serves live scores.
Mounted by main.py via ``app.include_router(models_router)``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from ml.paths import DEFAULT_HORIZON, HORIZONS, SYMBOLS
from ml.store import load_manifest, load_oos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


def _find_entry(manifest, symbol, horizon):
    for e in (manifest or {}).get("models", []):
        if e["symbol"] == symbol and e["horizon"] == horizon:
            return e
    return None


@router.get("/leaderboard")
def leaderboard():
    """Best model per (symbol, horizon) with headline metrics."""
    man = load_manifest()
    if not man:
        return {"status": "unavailable", "data": [], "message": "No trained models yet. Run: python -m ml.train"}
    rows = []
    for e in man.get("models", []):
        best = e["candidates"].get(e["best_model"], {})
        rows.append({
            "symbol": e["symbol"],
            "horizon": e["horizon"],
            "best_model": e["best_model"],
            "accuracy": best.get("accuracy"),
            "base_rate": best.get("base_rate"),
            "precision_high_conf": best.get("precision_high_conf"),
            "brier": best.get("brier"),
            "win_rate": best.get("win_rate"),
            "n_bets": best.get("n_bets"),
            "n_oos": best.get("n_oos"),
            "n_training_samples": e.get("n_training_samples"),
            "training_end_date": e.get("training_end_date"),
            "underperforms_random": e.get("underperforms_random"),
        })
    return {"status": "success", "data": rows, "generated_at": man.get("generated_at")}


@router.get("/{symbol}/metrics")
def metrics(symbol: str, horizon: str = DEFAULT_HORIZON):
    """Per-candidate scalars + winner's calibration / precision-by-confidence / top features."""
    man = load_manifest()
    e = _find_entry(man, symbol, horizon)
    if not e:
        return {"status": "unavailable", "data": None}
    return {"status": "success", "data": {
        "symbol": symbol,
        "horizon": horizon,
        "best_model": e["best_model"],
        "underperforms_random": e.get("underperforms_random"),
        "n_training_samples": e.get("n_training_samples"),
        "n_features": e.get("n_features"),
        "training_end_date": e.get("training_end_date"),
        "candidates": e.get("candidates", {}),
        "calibration": e.get("calibration"),
        "precision_by_confidence": e.get("precision_by_confidence"),
        "top_features": e.get("top_features", {}),
    }}


@router.get("/{symbol}/history")
def history(symbol: str, horizon: str = DEFAULT_HORIZON):
    """Winner's hit-rate-over-time + equity curve + raw OOS predictions."""
    man = load_manifest()
    e = _find_entry(man, symbol, horizon)
    if not e:
        return {"status": "unavailable", "data": None}
    preds = []
    oos = load_oos(symbol, horizon)
    if oos is not None and not oos.empty:
        df = oos.reset_index()
        date_col = "date" if "date" in df.columns else df.columns[0]
        for _, r in df.iterrows():
            preds.append({
                "date": str(r[date_col])[:10],
                "p_up": round(float(r["p_up"]), 4),
                "pred_dir": int(r.get("pred_dir", 1 if r["p_up"] >= 0.5 else 0)),
                "actual_dir": int(r["actual_dir"]),
                "correct": int(r.get("correct", int((r["p_up"] >= 0.5) == bool(r["actual_dir"])))),
                "fwd_ret": round(float(r["fwd_ret"]), 5),
            })
    return {"status": "success", "data": {
        "symbol": symbol,
        "horizon": horizon,
        "best_model": e["best_model"],
        "hit_rate_over_time": e.get("hit_rate_over_time", []),
        "equity_curve": e.get("equity_curve", []),
        "predictions": preds,
    }}


@router.get("/{symbol}/score")
def score(symbol: str, horizon: str = DEFAULT_HORIZON):
    """Live model-driven composite for one (symbol, horizon) — drives the gauge's
    horizon toggle. Blends the technical score exactly like the snapshot path."""
    if horizon not in HORIZONS:
        return {"status": "error", "data": None, "message": f"bad horizon {horizon}"}
    tech = {}
    try:
        from services.price_fetcher import PriceFetcher
        from services.multi_factor_engine import compute_multi_factor_score
        hist = PriceFetcher.fetch_historical(symbol, "3mo") or []
        if len(hist) >= 20:
            tech = compute_multi_factor_score(symbol, hist)
    except Exception as e:
        logger.debug("score(%s): tech compute failed: %s", symbol, e)

    from services.composite_score import get_composite
    comp = get_composite(symbol, horizon, tech_result=tech)
    if comp is None:
        return {"status": "unavailable", "data": None}
    return {"status": "success", "data": {
        "symbol": symbol,
        "horizon": horizon,
        "composite_score": comp.get("composite_score"),
        "regime": comp.get("regime"),
        "signal": comp.get("signal"),
        "confidence": comp.get("confidence"),
        "model_prob": comp.get("model_prob"),
        "model_score": comp.get("model_score"),
        "tech_score": comp.get("tech_score"),
        "model_name": comp.get("model_name"),
        "model_oos_accuracy": comp.get("model_oos_accuracy"),
        "model_underperforms": comp.get("model_underperforms"),
        "model_available": comp.get("model_available"),
    }}
