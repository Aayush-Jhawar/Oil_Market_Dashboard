"""
Stage 2 — Walk-forward calibration harness.

The only thing that proves any predictor works, and the tuner for Stage 3.

For every measured event in event_impact (source_tag='history', ordered by date),
predict its forward move using ONLY data that predates it, then check whether the
realized T+1/T+5/T+20 move fell inside the predictor's 50% / 80% bands.

Zero look-ahead is enforced two ways:
  - the analog/prior set for event i is strictly events[:i] (earlier dates only),
  - point-in-time vol uses price history ending the trading day BEFORE the event.
The event is never in its own prior set.

Outputs:
  - coverage table: per (predictor, contract, horizon) nominal 50/80 vs empirical,
  - PIT histogram: probability-integral-transform of realized values; a calibrated
    predictor's PIT is uniform on [0,1].

T+20 is computed but flagged excluded_from_headline (macro drift confounds it).

Two baseline predictors are scored side by side:
  1. base_rate  — empirical bands from prior same-bucket events (node→type→channel
                  backoff). Abstains when <2 priors. The benchmark Stage 3 must beat.
  2. struct_vol — structural prior as the center, point-in-time EWMA-free vol as the
                  band width (normal approx). Never abstains; covers thin nodes.

run_harness(predictors=...) accepts an arbitrary {name: callable}, so Stage 3's
analog predictor and Stage 4's Monte-Carlo predictor plug straight in.
"""

import bisect
import math
import statistics
from typing import Callable, Dict, List, Optional

from services.event_impact_db import MODELED_PRODUCT_BASINS

# Horizons scored. T+20 kept but excluded from the headline (macro drift).
HORIZONS: Dict[str, int] = {"t1": 1, "t5": 5, "t20": 20}
HEADLINE_HORIZONS = ("t1", "t5")
CONTRACTS = ("wti", "brent", "arb", "distillate_crack")

# Map a contract to its structural-prior key and its DB column stem.
_PRIOR_KEY = {
    "wti": "wti_pct", "brent": "brent_pct",
    "arb": "arb_usd", "distillate_crack": "crack_usd",
}
# Contracts quoted in % (crude flats) vs $ (spreads) — drives the vol calc.
_PCT_CONTRACTS = frozenset({"wti", "brent"})

# z-multipliers for symmetric normal bands
_Z = {"50": 0.6744897501960817, "80": 1.2815515594457831}


# ── Column / measurement helpers ──────────────────────────────────────────────

def _col(contract: str, htag: str) -> str:
    return f"{contract}_{htag}"


def _is_measured(contract: str, basin: Optional[str]) -> bool:
    """
    WTI/Brent flats are always measured. Arb/crack are measured only in basins
    with live EIA product data (Atlantic); elsewhere they are modeled and must
    NOT count toward measured calibration (spec invariant 2).
    """
    if contract in ("wti", "brent"):
        return True
    return basin not in MODELED_PRODUCT_BASINS


# ── Quantile / CDF helpers ────────────────────────────────────────────────────

def _quantile(sorted_vals: List[float], p: float) -> float:
    """Linear-interpolated quantile of a pre-sorted list."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def _normal_cdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.5
    return 0.5 * (1.0 + math.erf((x - mu) / (sigma * math.sqrt(2.0))))


def _empirical_cdf(sample: List[float], x: float) -> float:
    """Fraction of sample <= x (mid-rank to avoid 0/1 pile-up on small n)."""
    n = len(sample)
    below = sum(1 for v in sample if v < x)
    equal = sum(1 for v in sample if v == x)
    return (below + 0.5 * equal) / n if n else 0.5


# ── Point-in-time volatility (band width for struct_vol) ─────────────────────

def _pit_vol(prices: Dict, sorted_dates: List[str], event_date: str,
             window: int = 60) -> Optional[Dict[str, float]]:
    """
    Daily vol per contract over the `window` trading days ending the day BEFORE
    the event. % stdev for crude flats, $ stdev of daily spread changes for
    arb/crack. Returns None if too little pre-event history.
    """
    idx = bisect.bisect_left(sorted_dates, event_date)  # first date >= event
    win = sorted_dates[max(0, idx - window):idx]        # strictly pre-event
    if len(win) < 10:
        return None

    wti_r, brent_r, arb_d, crack_d = [], [], [], []
    for i in range(1, len(win)):
        a = prices.get(win[i - 1], {})
        b = prices.get(win[i], {})
        if a.get("wti") and b.get("wti"):
            wti_r.append((b["wti"] - a["wti"]) / a["wti"] * 100)
        if a.get("brent") and b.get("brent"):
            brent_r.append((b["brent"] - a["brent"]) / a["brent"] * 100)
        if a.get("brent") and a.get("wti") and b.get("brent") and b.get("wti"):
            arb_d.append((b["brent"] - b["wti"]) - (a["brent"] - a["wti"]))
        if a.get("ho") and a.get("wti") and b.get("ho") and b.get("wti"):
            crack_d.append((b["ho"] * 42 - b["wti"]) - (a["ho"] * 42 - a["wti"]))

    def _sd(xs: List[float]) -> Optional[float]:
        return statistics.pstdev(xs) if len(xs) >= 5 else None

    return {
        "wti": _sd(wti_r), "brent": _sd(brent_r),
        "arb": _sd(arb_d), "distillate_crack": _sd(crack_d),
    }


# ── Band constructors ─────────────────────────────────────────────────────────

def _empirical_band(sample: List[float]) -> Dict:
    s = sorted(sample)
    return {
        "kind": "empirical", "n": len(s), "sample": s,
        "median": _quantile(s, 0.50),
        "lo50": _quantile(s, 0.25), "hi50": _quantile(s, 0.75),
        "lo80": _quantile(s, 0.10), "hi80": _quantile(s, 0.90),
    }


def _normal_band(center: float, sigma: float) -> Dict:
    return {
        "kind": "normal", "center": center, "sigma": sigma,
        "median": center,
        "lo50": center - _Z["50"] * sigma, "hi50": center + _Z["50"] * sigma,
        "lo80": center - _Z["80"] * sigma, "hi80": center + _Z["80"] * sigma,
    }


def _pit(band: Dict, realized: float) -> float:
    if band["kind"] == "empirical":
        return _empirical_cdf(band["sample"], realized)
    return _normal_cdf(realized, band["center"], band["sigma"])


# ── Predictor 1: empirical base-rate bucket (with backoff) ────────────────────

def _node_type(node_id: Optional[str]) -> Optional[str]:
    from services.oil_nodes import NODE_BY_ID
    return (NODE_BY_ID.get(node_id) or {}).get("type") if node_id else None


def _bucket_sample(target: Dict, priors: List[Dict],
                   contract: str, col: str) -> List[float]:
    """
    Gather prior realized values for `col` using a backoff chain, stopping at the
    first level that yields >=2 measured priors:
      (node_id, channel, severity) → (node_type, channel, severity)
      → (channel, severity) → (channel)
    """
    t_node = target.get("node_id")
    t_type = _node_type(t_node)
    t_chan = target.get("channel")
    t_sev  = target.get("severity")

    def collect(pred) -> List[float]:
        out = []
        for p in priors:
            if not pred(p):
                continue
            v = p.get(col)
            if v is not None and _is_measured(contract, p.get("basin")):
                out.append(v)
        return out

    levels = [
        lambda p: p.get("node_id") == t_node and p.get("channel") == t_chan and p.get("severity") == t_sev,
        lambda p: _node_type(p.get("node_id")) == t_type and p.get("channel") == t_chan and p.get("severity") == t_sev,
        lambda p: p.get("channel") == t_chan and p.get("severity") == t_sev,
        lambda p: p.get("channel") == t_chan,
    ]
    for lvl in levels:
        s = collect(lvl)
        if len(s) >= 2:
            return s
    return []


def predict_base_rate(target: Dict, priors: List[Dict],
                      prices: Dict, sorted_dates: List[str]) -> Dict:
    out: Dict = {}
    for contract in CONTRACTS:
        for htag in HORIZONS:
            col = _col(contract, htag)
            sample = _bucket_sample(target, priors, contract, col)
            if len(sample) >= 2:
                out[(contract, htag)] = _empirical_band(sample)
    return out


# ── Predictor 2: structural prior + point-in-time vol ─────────────────────────

def predict_struct_vol(target: Dict, priors: List[Dict],
                       prices: Dict, sorted_dates: List[str]) -> Dict:
    from services.oil_nodes import NODE_BY_ID
    from services.eia_event_engine import compute_structural_prior

    node = NODE_BY_ID.get(target.get("node_id"))
    if not node:
        return {}
    prior = compute_structural_prior(
        node,
        severity=target.get("severity") or "outage",
        restored=bool(target.get("restored")),
        channel=target.get("channel") or "production",
    ) or {}
    vol = _pit_vol(prices, sorted_dates, target["event_date"])
    if not vol:
        return {}

    out: Dict = {}
    for contract in CONTRACTS:
        center = prior.get(_PRIOR_KEY[contract])
        sd_daily = vol.get(contract)
        if center is None or sd_daily is None or sd_daily <= 0:
            continue
        for htag, h in HORIZONS.items():
            out[(contract, htag)] = _normal_band(center, sd_daily * math.sqrt(h))
    return out


DEFAULT_PREDICTORS: Dict[str, Callable] = {
    "base_rate": predict_base_rate,
    "struct_vol": predict_struct_vol,
}


# ── Event loader ──────────────────────────────────────────────────────────────

def _load_history_events() -> List[Dict]:
    from services.event_impact_db import get_conn, init_db
    init_db()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM event_impact
            WHERE source_tag = 'history' AND node_id IS NOT NULL
            ORDER BY event_date ASC, event_id ASC
        """).fetchall()
    return [dict(r) for r in rows]


# ── Harness ───────────────────────────────────────────────────────────────────

def run_harness(predictors: Optional[Dict[str, Callable]] = None,
                pit_bins: int = 10) -> Dict:
    """
    Walk-forward over the measured event history. Returns coverage table + PIT
    histogram per predictor. `predictors` lets Stage 3/4 score new candidates.
    """
    predictors = predictors or DEFAULT_PREDICTORS
    from services.eia_event_engine import get_price_series
    prices = get_price_series()
    sorted_dates = sorted(prices.keys())
    events = _load_history_events()

    # accumulators: results[name][(contract,htag)] = {in50,in80,n, pit:[...]}
    results: Dict[str, Dict] = {
        name: {} for name in predictors
    }

    for i, target in enumerate(events):
        priors = events[:i]                     # strictly earlier — no look-ahead
        for name, fn in predictors.items():
            try:
                preds = fn(target, priors, prices, sorted_dates)
            except Exception:
                preds = {}
            for (contract, htag), band in preds.items():
                realized = target.get(_col(contract, htag))
                if realized is None:
                    continue
                if not _is_measured(contract, target.get("basin")):
                    continue
                cell = results[name].setdefault(
                    (contract, htag),
                    {"n": 0, "in50": 0, "in80": 0, "pit": []},
                )
                cell["n"] += 1
                if band["lo50"] <= realized <= band["hi50"]:
                    cell["in50"] += 1
                if band["lo80"] <= realized <= band["hi80"]:
                    cell["in80"] += 1
                cell["pit"].append(round(_pit(band, realized), 4))

    # ── Build coverage table + pooled PIT histogram ──────────────────────────
    out: Dict = {"predictors": {}, "n_events": len(events),
                 "horizons": HORIZONS, "headline_horizons": list(HEADLINE_HORIZONS)}

    for name in predictors:
        coverage_rows = []
        pooled_pit: List[float] = []
        pooled_headline = {"n": 0, "in50": 0, "in80": 0}
        for (contract, htag), c in sorted(results[name].items()):
            n = c["n"]
            cov50 = round(c["in50"] / n, 3) if n else None
            cov80 = round(c["in80"] / n, 3) if n else None
            coverage_rows.append({
                "contract": contract, "horizon": htag,
                "n": n, "coverage_50": cov50, "coverage_80": cov80,
                "nominal_50": 0.50, "nominal_80": 0.80,
                "excluded_from_headline": htag not in HEADLINE_HORIZONS,
            })
            pooled_pit.extend(c["pit"])
            if htag in HEADLINE_HORIZONS:
                pooled_headline["n"] += n
                pooled_headline["in50"] += c["in50"]
                pooled_headline["in80"] += c["in80"]

        # PIT histogram (uniform if calibrated)
        hist = [0] * pit_bins
        for v in pooled_pit:
            b = min(pit_bins - 1, int(v * pit_bins))
            hist[b] += 1
        n_pit = len(pooled_pit)
        expected = n_pit / pit_bins if pit_bins else 0
        # crude uniformity deviation: mean abs (observed-expected)/expected
        pit_dev = (
            round(sum(abs(h - expected) for h in hist) / (2 * n_pit), 3)
            if n_pit else None
        )

        hn = pooled_headline["n"]
        out["predictors"][name] = {
            "coverage": coverage_rows,
            "headline": {
                "n": hn,
                "coverage_50": round(pooled_headline["in50"] / hn, 3) if hn else None,
                "coverage_80": round(pooled_headline["in80"] / hn, 3) if hn else None,
                "note": "pooled over T+1/T+5 measured cells; nominal 0.50 / 0.80",
            },
            "pit_histogram": {
                "bins": pit_bins, "counts": hist, "n": n_pit,
                "uniform_deviation": pit_dev,
                "note": "L1 deviation from uniform (0=perfectly calibrated, ~0.5=worst)",
            },
        }

    return out
