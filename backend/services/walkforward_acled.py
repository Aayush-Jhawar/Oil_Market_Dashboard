"""
Walk-forward back-test of grouped ACLED escalation episodes vs realized prices.

For every ACLED escalation episode from `start_date` onward, predict its forward
move using ONLY data that predates it (catalog events + earlier ACLED episodes),
then compare the prediction to what crude (WTI) and the distillate crack ACTUALLY
did at T+1 / T+5. Zero look-ahead — the prior pool for episode i is strictly the
events dated before it.

This is the empirical proof the engine asks for: does the grouped-event predictor,
trained only on the past, bracket what really happened to the contracts we trade?

Reports, per (contract × horizon) and per episode:
  - predicted median + 80% band  vs  realized
  - inside_80 / inside_50  (band coverage)
  - direction_correct       (sign of predicted median == sign of realized)
  - MAE of the median

Focus contracts: WTI flat (crude) and distillate crack (HO×42 − WTI).
"""

from typing import Dict, List

from services.calibration_harness import _col
from services.move_predictor import predict_montecarlo

WF_CONTRACTS = ("wti", "distillate_crack")   # crude + distillate
WF_HORIZONS  = ("t1", "t5")
CONTRACT_LABEL = {"wti": "WTI (crude) %", "distillate_crack": "Distillate crack $"}


def _load_history() -> List[Dict]:
    from services.event_impact_db import get_conn, init_db
    init_db()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM event_impact
            WHERE source_tag = 'history' AND node_id IS NOT NULL
            ORDER BY event_date ASC, event_id ASC
        """).fetchall()
    return [dict(r) for r in rows]


def walk_forward(start_date: str = "2021-01-01", n_paths: int = 2500) -> Dict:
    """Walk-forward over ACLED episodes >= start_date; predicted vs realized."""
    from services.eia_event_engine import get_price_series
    prices = get_price_series()
    sorted_dates = sorted(prices.keys())
    events = _load_history()

    episodes: List[Dict] = []
    for i, target in enumerate(events):
        if (target.get("source_domain") or "") != "ACLED":
            continue
        if target["event_date"] < start_date:
            continue
        priors = events[:i]                       # strictly earlier → no leakage
        try:
            bands = predict_montecarlo(target, priors, prices, sorted_dates, n_paths=n_paths)
        except Exception:
            bands = {}

        cells: Dict[str, Dict] = {}
        for contract in WF_CONTRACTS:
            for htag in WF_HORIZONS:
                band = bands.get((contract, htag))
                actual = target.get(_col(contract, htag))
                if band is None or actual is None:
                    continue
                med = band["median"]
                dir_ok = None
                if med != 0 and actual != 0:
                    dir_ok = (med > 0) == (actual > 0)
                cells[f"{contract}_{htag}"] = {
                    "pred_median": round(med, 2),
                    "band_80": [round(band["lo80"], 2), round(band["hi80"], 2)],
                    "actual": round(actual, 2),
                    "inside_80": band["lo80"] <= actual <= band["hi80"],
                    "inside_50": band["lo50"] <= actual <= band["hi50"],
                    "dir_ok": dir_ok,
                }

        episodes.append({
            "event_id":   target["event_id"],
            "event_date": target["event_date"],
            "node_id":    target["node_id"],
            "channel":    target["channel"],
            "severity":   target["severity"],
            "n_prior":    len(priors),
            "cells":      cells,
        })

    # ── Aggregate per contract × horizon ─────────────────────────────────────
    agg: Dict[str, Dict] = {}
    for contract in WF_CONTRACTS:
        for htag in WF_HORIZONS:
            key = f"{contract}_{htag}"
            vals = [e["cells"][key] for e in episodes if key in e["cells"]]
            n = len(vals)
            if not n:
                continue
            dir_vals = [v["dir_ok"] for v in vals if v["dir_ok"] is not None]
            agg[key] = {
                "contract":   contract,
                "horizon":    htag,
                "n":          n,
                "coverage_80": round(sum(v["inside_80"] for v in vals) / n, 3),
                "coverage_50": round(sum(v["inside_50"] for v in vals) / n, 3),
                "direction_accuracy": round(sum(dir_vals) / len(dir_vals), 3) if dir_vals else None,
                "median_abs_error": round(sum(abs(v["pred_median"] - v["actual"]) for v in vals) / n, 2),
            }

    return {
        "start_date":  start_date,
        "n_episodes":  len(episodes),
        "contracts":   list(WF_CONTRACTS),
        "horizons":    list(WF_HORIZONS),
        "aggregate":   agg,
        "episodes":    episodes,
        "note": ("Walk-forward, zero look-ahead: each ACLED episode predicted from "
                 "only prior catalog + ACLED events. coverage_80 target 0.80, "
                 "coverage_50 target 0.50; direction_accuracy = sign match."),
    }
