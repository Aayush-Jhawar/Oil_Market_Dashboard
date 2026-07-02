"""Live forward-prediction logging + actual-outcome backfill (optional).

The Model Analytics tab's realized accuracy comes from the walk-forward OOS
predictions (already labelled). This module is for tracking *live* forward
performance over time: log today's prediction, then fill its actual once the
horizon elapses. Intended for a scheduler (APScheduler) or manual/local runs;
NOT required for the core dashboard. Rows are namespaced (model_version=MODEL_NS,
id prefix `mfa_v1_live_`) so they never collide with the legacy prediction rows.

    python -m ml.backfill                 # log today's live preds + backfill actuals
    python -m ml.backfill --backfill-only
"""
from __future__ import annotations

import argparse
import logging
import sqlite3

from ml.paths import SYMBOLS, HORIZONS, MODEL_NS, ensure_prediction_importable
from ml.inference import predict_prob
from ml.data import load_price_history

logger = logging.getLogger(__name__)
_LIVE_PREFIX = f"{MODEL_NS}_live_"


def _db_path() -> str:
    ensure_prediction_importable()
    from database import DB_PATH
    return DB_PATH


def log_live_prediction(symbol: str, horizon: str) -> bool:
    """Persist today's live prediction (actual left NULL until the horizon passes)."""
    pred = predict_prob(symbol, horizon)
    if not pred:
        return False
    as_of = pred["as_of"]
    p_up = pred["p_up"]
    row_id = f"{_LIVE_PREFIX}{symbol}_{horizon}_{as_of}"
    try:
        con = sqlite3.connect(_db_path(), timeout=30)
        con.execute("""
            INSERT OR REPLACE INTO predictions
            (id, symbol, date, horizon_days, target, prediction_value,
             prediction_label, confidence, model_version)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (row_id, symbol, as_of, HORIZONS[horizon], "direction", p_up,
              "UP" if p_up >= 0.5 else "DOWN", abs(p_up - 0.5) * 2.0, MODEL_NS))
        con.commit(); con.close()
        return True
    except Exception as e:
        logger.warning("log_live_prediction(%s/%s) failed: %s", symbol, horizon, e)
        return False


def backfill_actuals(symbol: str) -> int:
    """Fill actual_label / is_correct / actual_value for matured live rows of a symbol."""
    price = load_price_history(symbol)
    if price.empty:
        return 0
    closes = price["close"]
    dates = [str(d.date()) for d in price.index]
    idx_of = {d: i for i, d in enumerate(dates)}

    filled = 0
    try:
        con = sqlite3.connect(_db_path(), timeout=30)
        cur = con.cursor()
        rows = cur.execute(
            "SELECT id, date, horizon_days, prediction_label FROM predictions "
            "WHERE model_version=? AND symbol=? AND actual_label IS NULL",
            (MODEL_NS, symbol),
        ).fetchall()
        for row_id, d, hz, pred_label in rows:
            i = idx_of.get(str(d)[:10])
            if i is None or i + int(hz) >= len(closes):
                continue  # horizon hasn't elapsed yet
            cur_px = float(closes.iloc[i])
            fut_px = float(closes.iloc[i + int(hz)])
            if cur_px <= 0:
                continue
            ret = (fut_px - cur_px) / cur_px
            actual_label = "UP" if ret > 0 else "DOWN"
            is_correct = 1 if actual_label == pred_label else 0
            cur.execute(
                "UPDATE predictions SET actual_value=?, actual_label=?, is_correct=? WHERE id=?",
                (round(ret, 6), actual_label, is_correct, row_id),
            )
            filled += 1
        con.commit(); con.close()
    except Exception as e:
        logger.warning("backfill_actuals(%s) failed: %s", symbol, e)
    return filled


def main():
    ap = argparse.ArgumentParser(description="Log live predictions + backfill actuals.")
    ap.add_argument("--backfill-only", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    if not args.backfill_only:
        logged = sum(log_live_prediction(s, h) for s in SYMBOLS for h in HORIZONS)
        print(f"Logged {logged} live predictions.")
    total = sum(backfill_actuals(s) for s in SYMBOLS)
    print(f"Backfilled actuals for {total} matured rows.")


if __name__ == "__main__":
    main()
