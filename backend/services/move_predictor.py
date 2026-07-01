"""
Stage 4 — Move predictor (jump-diffusion Monte Carlo).

Turn the Stage-3 analog neighbourhood into a calibrated forward distribution per
contract. The forward move is decomposed:

    horizon_move = NEWS_JUMP  +  BASELINE_DIFFUSION

  - BASELINE_DIFFUSION: ambient market noise from the contract's OWN return
    history (point-in-time, window ends the day before the event). Fat tails via a
    2-regime Gaussian mixture fit by EM — GMM is legitimate HERE (full price
    history, hundreds of points), and only here. Diffusion over h days = sum of h
    daily draws.
  - NEWS_JUMP: the event-conditional shock, bootstrapped (similarity-weighted
    resample + small kernel jitter) from the Stage-3 analog neighbourhood's
    realized moves. NEVER a GMM on a handful of analogs. Severity-scaled to the
    query (scare ×0.5 / outage ×1.0 / sustained ×1.6).

Simulate ~N paths, read percentile bands at T+1/T+5/T+20, plus path stats
(max adverse/favourable excursion proxy, P(touch ±X%)), P(up), expected move,
n_analogs, driving analogs, a priced-in flag, and a calibration confidence badge.

Zero-analog nodes (Malacca / Jamnagar) fall back to a LABELLED structural-prior
distribution — never an empty box.
"""

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from services.calibration_harness import (
    CONTRACTS, HORIZONS, _col, _is_measured, predict_struct_vol,
)
from services.analog_retrieval import (
    retrieve_analogs, DEFAULT_WEIGHTS, DEFAULT_K, SIMILARITY_FLOOR,
)

SEV_MULT = {"scare": 0.5, "outage": 1.0, "sustained": 1.6}
_PCT_CONTRACTS = frozenset({"wti", "brent"})
DEFAULT_PATHS = 3000
_TOUCH_LEVEL = 5.0   # ±5% (pct contracts) / ±$5 (spreads) for P(touch)


# ── Baseline diffusion: 2-regime Gaussian mixture (EM) ───────────────────────

def _daily_series(prices: Dict, sorted_dates: List[str], event_date: str,
                  contract: str, window: int = 250) -> np.ndarray:
    """Point-in-time daily changes for a contract (window ends day before event)."""
    import bisect
    idx = bisect.bisect_left(sorted_dates, event_date)
    win = sorted_dates[max(0, idx - window):idx]
    vals = []
    for i in range(1, len(win)):
        a = prices.get(win[i - 1], {})
        b = prices.get(win[i], {})
        if contract == "wti" and a.get("wti") and b.get("wti"):
            vals.append((b["wti"] - a["wti"]) / a["wti"] * 100)
        elif contract == "brent" and a.get("brent") and b.get("brent"):
            vals.append((b["brent"] - a["brent"]) / a["brent"] * 100)
        elif contract == "arb" and all(a.get(k) and b.get(k) for k in ("wti", "brent")):
            vals.append((b["brent"] - b["wti"]) - (a["brent"] - a["wti"]))
        elif contract == "distillate_crack" and all(a.get(k) and b.get(k) for k in ("ho", "wti")):
            vals.append((b["ho"] * 42 - b["wti"]) - (a["ho"] * 42 - a["wti"]))
    return np.asarray(vals, dtype=float)


def _fit_gmm2(x: np.ndarray, iters: int = 50) -> Optional[Dict]:
    """Minimal 2-component 1-D Gaussian mixture via EM. Falls back to 1 Gaussian."""
    x = x[np.isfinite(x)]
    if x.size < 20:
        return None
    # init: split at median
    med = np.median(x)
    mu = np.array([x[x <= med].mean(), x[x > med].mean()])
    sd = np.array([max(x[x <= med].std(), 1e-3), max(x[x > med].std(), 1e-3)])
    w = np.array([0.5, 0.5])
    for _ in range(iters):
        # E-step
        p0 = w[0] * _npdf(x, mu[0], sd[0])
        p1 = w[1] * _npdf(x, mu[1], sd[1])
        tot = p0 + p1 + 1e-300
        r0, r1 = p0 / tot, p1 / tot
        # M-step
        n0, n1 = r0.sum(), r1.sum()
        if n0 < 1 or n1 < 1:
            break
        mu = np.array([(r0 * x).sum() / n0, (r1 * x).sum() / n1])
        sd = np.array([
            max(math.sqrt((r0 * (x - mu[0]) ** 2).sum() / n0), 1e-3),
            max(math.sqrt((r1 * (x - mu[1]) ** 2).sum() / n1), 1e-3),
        ])
        w = np.array([n0 / x.size, n1 / x.size])
    return {"w": w, "mu": mu, "sd": sd}


def _npdf(x, mu, sd):
    return np.exp(-0.5 * ((x - mu) / sd) ** 2) / (sd * math.sqrt(2 * math.pi))


def _sample_diffusion(gmm: Optional[Dict], rng, n: int, h: int,
                      fallback_sd: float) -> np.ndarray:
    """Sum of h daily draws from the mixture (random-walk diffusion over h days)."""
    if gmm is None:
        daily = rng.normal(0.0, fallback_sd, size=(n, h))
    else:
        comp = (rng.random((n, h)) > gmm["w"][0]).astype(int)
        mu = gmm["mu"][comp]
        sd = gmm["sd"][comp]
        daily = rng.normal(mu, sd)
    # centre the diffusion at zero (the jump carries the drift, not ambient trend)
    daily = daily - daily.mean(axis=1, keepdims=True) if h > 1 else daily
    return daily.sum(axis=1)


# ── News jump: bootstrap the analog neighbourhood ────────────────────────────

def _sample_jump(values: np.ndarray, weights: np.ndarray, rng, n: int) -> np.ndarray:
    """Similarity-weighted resample with kernel jitter (avoids few-analog discreteness)."""
    p = weights / weights.sum()
    idx = rng.choice(len(values), size=n, p=p)
    draw = values[idx]
    # kernel bandwidth ~ Silverman on the weighted sample, floored
    spread = values.std() if values.size > 1 else abs(values).mean()
    bw = max(0.25 * spread, 0.15)
    return draw + rng.normal(0.0, bw, size=n)


# ── Core predictor ────────────────────────────────────────────────────────────

def _mc_bands(samples: np.ndarray) -> Dict:
    qs = np.percentile(samples, [10, 25, 50, 75, 90])
    return {
        "kind": "mc", "samples": samples,
        "median": round(float(qs[2]), 2),
        "lo50": float(qs[1]), "hi50": float(qs[3]),
        "lo80": float(qs[0]), "hi80": float(qs[4]),
    }


def predict_montecarlo(target: Dict, priors: List[Dict],
                       prices: Dict, sorted_dates: List[str],
                       weights: Optional[Dict] = None,
                       k: int = DEFAULT_K, floor: float = SIMILARITY_FLOOR,
                       n_paths: int = DEFAULT_PATHS,
                       seed: int = 12345) -> Dict:
    """Harness-compatible jump-diffusion predictor."""
    weights = weights or DEFAULT_WEIGHTS
    analogs = retrieve_analogs(target, priors, weights, k)
    rng = np.random.default_rng(seed)

    q_mult = SEV_MULT.get(target.get("severity"), 1.0)
    best_sim = analogs[0]["similarity"] if analogs else 0.0

    # Zero / weak neighbourhood → labelled structural-prior distribution
    if not analogs or best_sim < floor:
        return predict_struct_vol(target, priors, prices, sorted_dates)

    out: Dict = {}
    for contract in CONTRACTS:
        gmm = _fit_gmm2(_daily_series(prices, sorted_dates,
                                      target["event_date"], contract))
        fallback_sd = 1.0
        for htag, h in HORIZONS.items():
            col = _col(contract, htag)
            vals, wts = [], []
            for a in analogs:
                v = a.get(col)
                if v is None or not _is_measured(contract, a.get("basin")):
                    continue
                a_mult = SEV_MULT.get(a.get("severity"), 1.0)
                vals.append(v * (q_mult / a_mult))      # severity-scale to query
                wts.append(a["similarity"])
            if len(vals) < 2:
                continue
            jump = _sample_jump(np.asarray(vals), np.asarray(wts), rng, n_paths)
            diff = _sample_diffusion(gmm, rng, n_paths, h, fallback_sd)
            out[(contract, htag)] = _mc_bands(jump + diff)
    return out


# Extend the harness PIT to understand the 'mc' band kind.
import services.calibration_harness as _ch
_prev_pit = _ch._pit


def _pit_mc(band: Dict, realized: float) -> float:
    if band.get("kind") == "mc":
        s = band["samples"]
        return float((s < realized).mean() + 0.5 * (s == realized).mean())
    return _prev_pit(band, realized)


_ch._pit = _pit_mc


# ── Public forward-distribution API ──────────────────────────────────────────

def forward_distribution(query: Dict, n_paths: int = DEFAULT_PATHS,
                         k: int = DEFAULT_K,
                         realized_since: Optional[Dict] = None) -> Dict:
    """
    Full forward distribution for a NEW event. Returns per-contract percentile
    bands at T+1/5/20, P(up), expected move, P(touch ±level), n_analogs, driving
    analogs, priced-in flag, and a confidence badge.

    realized_since: optional {contract: pct_or_usd_move_already_seen} to drive the
    priced-in flag (realized move since the event vs the expected jump).
    """
    from services.event_impact_db import get_conn, init_db, BASIN_MAP
    from services.eia_event_engine import get_price_series

    query = dict(query)
    query.setdefault("event_date", "2099-01-01")
    query.setdefault("restored", False)
    query.setdefault("anticipated", False)
    if not query.get("basin") and query.get("node_id"):
        query["basin"] = BASIN_MAP.get(query["node_id"], "Atlantic")

    prices = get_price_series()
    sorted_dates = sorted(prices.keys())
    init_db()
    with get_conn() as conn:
        priors = [dict(r) for r in conn.execute(
            "SELECT * FROM event_impact WHERE source_tag='history' AND node_id IS NOT NULL"
        ).fetchall()]

    analogs = retrieve_analogs(query, priors, DEFAULT_WEIGHTS, k)
    best_sim = analogs[0]["similarity"] if analogs else 0.0
    structural = best_sim < SIMILARITY_FLOOR or not analogs

    bands = predict_montecarlo(query, priors, prices, sorted_dates,
                               k=k, n_paths=n_paths)

    contracts_out: Dict = {}
    for contract in CONTRACTS:
        measured = _is_measured(contract, query.get("basin"))
        horizons_out = {}
        for htag in HORIZONS:
            band = bands.get((contract, htag))
            if band is None:
                continue
            s = band["samples"] if band.get("kind") == "mc" else None
            level = _TOUCH_LEVEL
            entry = {
                "median": round(band["median"], 2),
                "band_50": [round(band["lo50"], 2), round(band["hi50"], 2)],
                "band_80": [round(band["lo80"], 2), round(band["hi80"], 2)],
            }
            if s is not None:
                entry.update({
                    "p_up": round(float((s > 0).mean()), 2),
                    "expected": round(float(s.mean()), 2),
                    "p_touch_up": round(float((s >= level).mean()), 2),
                    "p_touch_dn": round(float((s <= -level).mean()), 2),
                })
            horizons_out[htag] = entry

        # priced-in flag from the T+1 expected jump vs already-realized move
        priced_in = None
        if realized_since and contract in realized_since and "t1" in horizons_out:
            exp_jump = horizons_out["t1"].get("expected")
            if exp_jump:
                priced_in = abs(realized_since[contract]) >= abs(exp_jump)

        contracts_out[contract] = {
            "measured": measured, "modeled": not measured,
            "horizons": horizons_out,
            "priced_in": priced_in,
        }

    return {
        "query": {k2: query.get(k2) for k2 in
                  ("node_id", "channel", "severity", "basin", "restored")},
        "method": "structural_prior_fallback" if structural else "jump_diffusion_mc",
        "n_paths": n_paths,
        "n_analogs": len(analogs),
        "best_similarity": best_sim,
        "confidence": ("STRUCTURAL" if structural else "HIGH"),
        "contracts": contracts_out,
        "driving_analogs": [
            {"event_id": a["event_id"], "similarity": a["similarity"],
             "node_id": a["node_id"], "severity": a["severity"],
             "wti_t5": a.get("wti_t5"), "brent_t5": a.get("brent_t5")}
            for a in analogs[:4]
        ],
        "disclaimer": ("Calibrated scenario distribution from historical analogs + "
                       "ambient diffusion — NOT a deterministic price forecast."),
    }
