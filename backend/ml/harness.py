"""Walk-forward horse-race: evaluate every candidate out-of-sample with purged +
embargoed splits, compute honest metrics, and pick the best model per
(symbol, horizon). Reuses only the pure primitives from
``prediction.validation.purged_cv`` — none of the heavy legacy machinery.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ml.paths import CANDIDATES, HORIZONS, ensure_prediction_importable
from ml.models import make_candidate, feature_importances

logger = logging.getLogger(__name__)

TEST_SIZE = 63            # ~one quarter per OOS fold
HIGH_CONF_EDGE = 0.12     # |p-0.5| >= 0.12  ->  p>=0.62 / p<=0.38


def _purged_splits(n: int, horizon_days: int):
    ensure_prediction_importable()
    from prediction.validation.purged_cv import generate_purged_walk_forward_splits
    min_train = max(252, int(0.4 * n))
    return generate_purged_walk_forward_splits(
        n_samples=n,
        min_train_size=min_train,
        test_size=TEST_SIZE,
        horizon_periods=horizon_days,
        embargo_periods=horizon_days,
        expanding=True,
    )


def _oos_for_candidate(name, X, y_dir, fwd_ret, splits) -> Optional[pd.DataFrame]:
    """Collect pooled out-of-sample predictions for one candidate across folds."""
    rows: List[dict] = []
    for tr_idx, te_idx in splits:
        y_tr = y_dir.iloc[tr_idx]
        if y_tr.nunique() < 2:            # degenerate fold — skip
            continue
        model = make_candidate(name)
        model.fit(X.iloc[tr_idx], y_tr)
        p = model.predict_proba(X.iloc[te_idx])[:, 1]
        for j, idx in enumerate(te_idx):
            rows.append({
                "date": X.index[idx],
                "p_up": float(p[j]),
                "actual_dir": int(y_dir.iloc[idx]),
                "fwd_ret": float(fwd_ret.iloc[idx]),
            })
    if not rows:
        return None
    return pd.DataFrame(rows).set_index("date").sort_index()


def _metrics(odf: pd.DataFrame, horizon_days: int) -> Dict:
    ensure_prediction_importable()
    from prediction.validation.purged_cv import calculate_brier_score, calculate_calibration_curve

    p = odf["p_up"].values
    a = odf["actual_dir"].values
    ret = odf["fwd_ret"].values
    pred = (p >= 0.5).astype(int)
    correct = (pred == a).astype(int)

    accuracy = float(correct.mean())
    brier = round(float(calculate_brier_score(p, a)), 4)
    base_rate = float(a.mean())

    hc = np.abs(p - 0.5) >= HIGH_CONF_EDGE
    hc_n = int(hc.sum())
    precision_hc = round(float(correct[hc].mean()), 4) if hc_n > 0 else None

    # Precision-by-confidence buckets (confidence = |p-0.5|*2 in [0,1]).
    conf = np.abs(p - 0.5) * 2.0
    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0001]
    pbc = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf >= lo) & (conf < hi)
        n = int(m.sum())
        pbc.append({"bucket": f"{lo:.1f}-{min(hi,1.0):.1f}", "n": n,
                    "precision": round(float(correct[m].mean()), 4) if n else None})

    calib = calculate_calibration_curve(p, a)

    # Hit-rate over time (monthly accuracy).
    monthly = correct.copy()
    ser = pd.Series(monthly, index=odf.index)
    hit_series = ser.resample("ME").mean().dropna()
    hit_rate_over_time = [{"date": d.strftime("%Y-%m-%d"), "accuracy": round(float(v), 4)}
                          for d, v in hit_series.items()]

    # Illustrative long/flat equity on NON-overlapping bets (stride = horizon)
    # so overlapping forward returns don't inflate it. Labelled illustrative.
    stride = max(1, horizon_days)
    sub = odf.iloc[::stride]
    s_pred = (sub["p_up"].values >= 0.5).astype(int)
    s_ret = np.where(s_pred == 1, sub["fwd_ret"].values, 0.0)
    equity = np.cumprod(1.0 + s_ret)
    equity_curve = [{"date": d.strftime("%Y-%m-%d"), "equity": round(float(e), 4)}
                    for d, e in zip(sub.index, equity)]
    # Win rate of the illustrative long/flat bets we actually took (pred_up).
    taken = s_pred == 1
    n_bets = int(taken.sum())
    win_rate = round(float((sub["fwd_ret"].values[taken] > 0).mean()), 4) if n_bets else None
    total_return = round(float(equity[-1] - 1.0), 4) if len(equity) else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "base_rate": round(base_rate, 4),
        "precision_high_conf": precision_hc,
        "high_conf_n": hc_n,
        "brier": brier,
        "win_rate": win_rate,
        "n_bets": n_bets,
        "total_return": total_return,
        "n_oos": int(len(odf)),
        "precision_by_confidence": pbc,
        "calibration": calib,
        "hit_rate_over_time": hit_rate_over_time,
        "equity_curve": equity_curve,
    }


def walk_forward_eval(X: pd.DataFrame, y_dir: pd.Series, fwd_ret: pd.Series,
                      horizon_days: int) -> Optional[Dict]:
    """Return {candidate_name: {metrics..., 'oos': DataFrame}} or None."""
    n = len(X)
    splits = _purged_splits(n, horizon_days)
    if not splits:
        logger.warning("walk_forward_eval: no valid splits for n=%d horizon=%d", n, horizon_days)
        return None
    out: Dict[str, Dict] = {}
    for name in CANDIDATES:
        odf = _oos_for_candidate(name, X, y_dir, fwd_ret, splits)
        if odf is None or odf.empty:
            continue
        m = _metrics(odf, horizon_days)
        m["oos"] = odf
        out[name] = m
    return out or None


def select_best(results: Dict[str, Dict]) -> tuple[str, bool]:
    """Pick best candidate: primary = high-conf precision (>=30 samples),
    fallback = accuracy; tiebreak = lower Brier. Returns (name, underperforms_random).
    """
    def score(name: str):
        m = results[name]
        primary = (m["precision_high_conf"]
                   if (m["high_conf_n"] >= 30 and m["precision_high_conf"] is not None)
                   else m["accuracy"])
        return (primary, -m["brier"])

    best = max(results, key=score)
    m = results[best]
    underperforms = (m["accuracy"] <= 0.5 and m["brier"] >= 0.25)
    # If the "winner" is no better than random, fall back to the transparent
    # momentum baseline when it's at least as accurate.
    if underperforms and "momentum" in results and results["momentum"]["accuracy"] >= m["accuracy"]:
        best = "momentum"
    return best, underperforms
