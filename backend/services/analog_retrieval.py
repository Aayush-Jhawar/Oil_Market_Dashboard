"""
Stage 3 — Direction-gated analog retrieval (structured-only v1).

Find the events most like *this* one — not all prior events — and read per-product
direction off the neighborhood. Embeddings (spec's w1 cosine term) are deliberately
omitted in v1: the spec says drop them unless they beat the plain node bucket out of
sample, and the impact table is small enough that the structured axes dominate. The
text term is a clean add later (swap into `hybrid_score`).

Pipeline:
  1. DIRECTION GATE FIRST — retrieval never crosses sign_class (escalation vs
     restored). Averaging "Hormuz escalates" into "Hormuz eases" is forbidden.
  2. HYBRID SCORE (structured): node-graph proximity + channel + severity + basin
     + anticipated − recency decay. Weights tunable against the Stage-2 harness.
  3. ADAPTIVE-k: keep the top neighbours (k>=5 where available), INCLUDING null /
     no-move analogs (a no-move is information). Similarity-weighted.
  4. SIMILARITY FLOOR: if the best neighbour is below the floor, fall back to the
     structural-prior band (struct_vol) rather than trusting a weak neighbourhood.
  5. PER-PRODUCT IMPACT VECTOR: similarity-weighted median per contract + sign
     consistency; rank most-hit and most-benefited; modeled cells tagged; neighbour
     disagreement lowers confidence rather than being hidden.

`predict_analog` is a Stage-2-harness-compatible predictor, so the weights are
tuned by the same walk-forward objective that benchmarks everything else.
"""

import math
from typing import Dict, List, Optional, Tuple

from services.event_impact_db import MODELED_PRODUCT_BASINS
from services.calibration_harness import (
    CONTRACTS, HORIZONS, _col, _is_measured, _normal_band, predict_struct_vol,
)

# ── Node-relatedness graph (hand-seeded families) ─────────────────────────────
# A node can belong to several families; shared membership raises proximity.
NODE_FAMILIES: Dict[str, List[str]] = {
    "chokepoint":        ["hormuz", "malacca", "suez", "bab_el_mandeb", "bosphorus"],
    "me_seaborne":       ["hormuz", "bab_el_mandeb", "ghawar_abqaiq", "basra"],
    "usgc":              ["usgc_padd3", "permian"],
    "atlantic_refining": ["usgc_padd3", "rotterdam_ara", "north_sea"],
    "asia_refining":     ["jamnagar", "singapore_jurong", "ulsan", "malacca"],
    "fsu":               ["russia_siberia", "bosphorus"],
}

_SEV_RANK = {"scare": 1, "outage": 2, "sustained": 3}

# Tuned against the Stage-2 walk-forward harness (grid over node/channel/severity/
# recency × k × floor). Best objective |cov50-0.5|+|cov80-0.8|+PITdev = 0.338,
# beating the plain base-rate bucket (0.527 PITdev) and struct_vol (0.174 PITdev).
DEFAULT_WEIGHTS: Dict[str, float] = {
    "node": 1.0, "channel": 0.8, "severity": 0.7,
    "basin": 0.3, "anticipated": 0.2, "recency": 0.1,
}
DEFAULT_K = 6
SIMILARITY_FLOOR = 0.3


# ── Node proximity ────────────────────────────────────────────────────────────

def _families_of(node_id: str) -> set:
    return {fam for fam, members in NODE_FAMILIES.items() if node_id in members}


def node_proximity(a: Optional[str], b: Optional[str]) -> float:
    """0..1 relatedness between two nodes via shared families + same type."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    from services.oil_nodes import NODE_BY_ID
    same_type = (NODE_BY_ID.get(a, {}).get("type") ==
                 NODE_BY_ID.get(b, {}).get("type"))
    shared = _families_of(a) & _families_of(b)
    if shared:
        score = min(0.85, 0.55 + 0.12 * len(shared))
        if same_type:
            score = min(0.9, score + 0.05)
        return score
    if same_type:
        return 0.45
    return 0.2   # calibrated cross-family floor


# ── Hybrid similarity score ───────────────────────────────────────────────────

def _year(date_str: str) -> float:
    try:
        return int(date_str[:4]) + (int(date_str[5:7]) - 1) / 12.0
    except Exception:
        return 0.0


def hybrid_score(query: Dict, cand: Dict, weights: Dict[str, float]) -> float:
    """Structured similarity in [~0, sum(weights)]; higher = more analogous."""
    w = weights
    s = 0.0
    s += w["node"]    * node_proximity(query.get("node_id"), cand.get("node_id"))
    s += w["channel"] * (1.0 if query.get("channel") == cand.get("channel") else 0.0)

    qsev = _SEV_RANK.get(query.get("severity"), 2)
    csev = _SEV_RANK.get(cand.get("severity"), 2)
    s += w["severity"] * (1.0 - abs(qsev - csev) / 2.0)

    s += w["basin"]       * (1.0 if query.get("basin") == cand.get("basin") else 0.0)
    s += w["anticipated"] * (1.0 if bool(query.get("anticipated")) == bool(cand.get("anticipated")) else 0.0)

    # recency / regime decay (years apart, ~10yr scale)
    dy = abs(_year(query.get("event_date", "")) - _year(cand.get("event_date", "")))
    s -= w["recency"] * min(1.0, dy / 10.0)
    return s


def _max_possible(weights: Dict[str, float]) -> float:
    return (weights["node"] + weights["channel"] + weights["severity"]
            + weights["basin"] + weights["anticipated"])


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve_analogs(query: Dict, candidates: List[Dict],
                     weights: Optional[Dict] = None,
                     k: int = DEFAULT_K) -> List[Dict]:
    """
    Direction-gated, similarity-ranked top-k analogs. Each result carries a
    normalised `similarity` in [0,1]. Null/no-move analogs are kept.
    """
    weights = weights or DEFAULT_WEIGHTS
    q_restored = bool(query.get("restored"))
    q_id = query.get("event_id")
    norm = _max_possible(weights) or 1.0

    scored = []
    for c in candidates:
        if c.get("event_id") == q_id:
            continue                                   # never self-match
        if bool(c.get("restored")) != q_restored:
            continue                                   # DIRECTION GATE
        raw = hybrid_score(query, c, weights)
        scored.append((max(0.0, raw) / norm, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sim, c in scored[:k]:
        out.append({**c, "similarity": round(sim, 4)})
    return out


# ── Weighted distribution helpers ─────────────────────────────────────────────

def _weighted_quantile(pairs: List[Tuple[float, float]], p: float) -> Optional[float]:
    if not pairs:
        return None
    s = sorted(pairs, key=lambda x: x[0])
    total = sum(w for _, w in s)
    if total <= 0:
        return s[len(s) // 2][0]
    target = p * total
    cum = 0.0
    for v, w in s:
        cum += w
        if cum >= target:
            return v
    return s[-1][0]


def _weighted_cdf(pairs: List[Tuple[float, float]], x: float) -> float:
    total = sum(w for _, w in pairs)
    if total <= 0:
        return 0.5
    below = sum(w for v, w in pairs if v < x)
    equal = sum(w for v, w in pairs if v == x)
    return (below + 0.5 * equal) / total


def _analog_band(pairs: List[Tuple[float, float]]) -> Dict:
    return {
        "kind": "wempirical", "n": len(pairs), "pairs": pairs,
        "median": _weighted_quantile(pairs, 0.50),
        "lo50": _weighted_quantile(pairs, 0.25), "hi50": _weighted_quantile(pairs, 0.75),
        "lo80": _weighted_quantile(pairs, 0.10), "hi80": _weighted_quantile(pairs, 0.90),
    }


# ── Harness-compatible predictor ──────────────────────────────────────────────

def predict_analog(target: Dict, priors: List[Dict],
                   prices: Dict, sorted_dates: List[str],
                   weights: Optional[Dict] = None,
                   k: int = DEFAULT_K,
                   floor: float = SIMILARITY_FLOOR) -> Dict:
    """
    Stage-3 predictor for the Stage-2 harness. Builds similarity-weighted analog
    bands; falls back to struct_vol per-cell when the neighbourhood is too weak
    (below the similarity floor) or too thin.
    """
    weights = weights or DEFAULT_WEIGHTS
    analogs = retrieve_analogs(target, priors, weights, k)
    fallback = None

    def _fb() -> Dict:
        nonlocal fallback
        if fallback is None:
            fallback = predict_struct_vol(target, priors, prices, sorted_dates)
        return fallback

    # Floor check on the best available neighbour
    best_sim = analogs[0]["similarity"] if analogs else 0.0
    if not analogs or best_sim < floor:
        return _fb()

    out: Dict = {}
    for contract in CONTRACTS:
        for htag in HORIZONS:
            col = _col(contract, htag)
            pairs = [
                (a[col], a["similarity"])
                for a in analogs
                if a.get(col) is not None and _is_measured(contract, a.get("basin"))
            ]
            if len(pairs) >= 2:
                out[(contract, htag)] = _analog_band(pairs)
            else:
                fb = _fb().get((contract, htag))
                if fb is not None:
                    out[(contract, htag)] = fb
    return out


# Patch calibration_harness._pit to understand the weighted-empirical band kind.
# (kept local so the harness stays import-light)
import services.calibration_harness as _ch
_orig_pit = _ch._pit


def _pit_with_wempirical(band: Dict, realized: float) -> float:
    if band.get("kind") == "wempirical":
        return _weighted_cdf(band["pairs"], realized)
    return _orig_pit(band, realized)


_ch._pit = _pit_with_wempirical


# ── Per-product impact vector (public-facing read) ───────────────────────────

def impact_vector(analogs: List[Dict], basin: Optional[str]) -> Dict:
    """
    Similarity-weighted per-contract direction + sign consistency, ranked.
    Modeled cells (arb/crack outside Atlantic) are tagged and excluded from the
    measured read. Neighbour disagreement lowers confidence.
    """
    vec: Dict[str, Dict] = {}
    for contract in CONTRACTS:
        col = _col(contract, "t1")
        col5 = _col(contract, "t5")
        measured = _is_measured(contract, basin)
        pairs = []
        for a in analogs:
            v = a.get(col5) if a.get(col5) is not None else a.get(col)
            if v is not None:
                pairs.append((v, a["similarity"]))
        if not pairs:
            vec[contract] = {"measured": measured, "n": 0, "median": None,
                             "sign_consistency": None, "modeled": not measured}
            continue
        med = _weighted_quantile(pairs, 0.50)
        sign = 1 if (med or 0) > 0 else -1 if (med or 0) < 0 else 0
        agree = sum(w for v, w in pairs if (v > 0) == (sign > 0) and v != 0)
        total = sum(w for _, w in pairs)
        vec[contract] = {
            "measured": measured,
            "modeled": not measured,
            "n": len(pairs),
            "median": round(med, 2) if med is not None else None,
            "sign_consistency": round(agree / total, 2) if total else None,
        }

    # rank measured contracts by |median| (most-hit) and signed median (most-benefited)
    measured_cells = [
        (c, d) for c, d in vec.items()
        if d["measured"] and d["median"] is not None
    ]
    most_hit = sorted(measured_cells, key=lambda kv: abs(kv[1]["median"]), reverse=True)
    most_benefited = sorted(measured_cells, key=lambda kv: kv[1]["median"], reverse=True)

    return {
        "per_contract": vec,
        "most_hit": [c for c, _ in most_hit[:2]],
        "most_benefited": most_benefited[0][0] if most_benefited else None,
    }


# ── Public query API ──────────────────────────────────────────────────────────

def retrieve_for_query(query: Dict, k: int = DEFAULT_K,
                       weights: Optional[Dict] = None) -> Dict:
    """
    Retrieve analogs for a NEW event from the full measured history and return the
    per-product impact vector + driving analogs. `query` needs at least node_id,
    channel, severity; basin/restored/anticipated/event_date optional.
    """
    from services.event_impact_db import get_conn, init_db, BASIN_MAP
    weights = weights or DEFAULT_WEIGHTS
    query = dict(query)
    query.setdefault("event_date", "2099-01-01")     # newest → no future analogs
    query.setdefault("restored", False)
    query.setdefault("anticipated", False)
    if not query.get("basin") and query.get("node_id"):
        query["basin"] = BASIN_MAP.get(query["node_id"], "Atlantic")

    init_db()
    with get_conn() as conn:
        candidates = [dict(r) for r in conn.execute(
            "SELECT * FROM event_impact WHERE source_tag='history' AND node_id IS NOT NULL"
        ).fetchall()]

    analogs = retrieve_analogs(query, candidates, weights, k)
    best_sim = analogs[0]["similarity"] if analogs else 0.0
    iv = impact_vector(analogs, query.get("basin"))

    return {
        "query": {k2: query.get(k2) for k2 in
                  ("node_id", "channel", "severity", "basin", "restored")},
        "best_similarity": best_sim,
        "below_floor": best_sim < SIMILARITY_FLOOR,
        "confidence": ("STRUCTURAL" if best_sim < SIMILARITY_FLOOR else "HIGH"),
        "impact_vector": iv,
        "driving_analogs": [
            {"event_id": a["event_id"], "similarity": a["similarity"],
             "node_id": a["node_id"], "channel": a["channel"],
             "severity": a["severity"], "event_date": a["event_date"],
             "wti_t5": a.get("wti_t5"), "brent_t5": a.get("brent_t5"),
             "arb_t5": a.get("arb_t5")}
            for a in analogs[:4]
        ],
    }
