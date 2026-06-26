"""
EIA Event Study Engine.

Fetches ~20 years of daily spot prices from EIA OpenData API
(WTI = RWTC, Brent = RBRTE, Heating Oil NY Harbor = EER_EPD2F_PF4_Y35NY_DPG)
and runs event studies for each catalogued disruption.

Methodology:
  • Baseline  = T-1 (last trading day BEFORE event date)
  • T+0       = first trading day ON or AFTER event date (captures weekend gaps)
  • T+1, T+5, T+20  = subsequent trading days
  • WTI/Brent: % change from baseline
  • Arb       = (Brent − WTI) change, in $/bbl
  • Crack     = (HO $/gal × 42 − WTI) change, in $/bbl  (distillate proxy)
  • Headline  = peak of {T+0, T+1, T+5} — T+20 shown but excluded from headline
  • Confidence: sign-agreement based, not sample-size based
  • Structural prior fallback when n=0 or analogs contradict direction
"""

import os
import json
import bisect
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from services.event_catalog import DISRUPTION_EVENTS
from services.oil_nodes import NODE_BY_ID, NODE_DEFINITIONS

logger = logging.getLogger(__name__)

# ── EIA API constants ────────────────────────────────────────────────────────
EIA_BASE = "https://api.eia.gov/v2"
SPOT_ROUTE = f"{EIA_BASE}/petroleum/pri/spt/data/"
# Fallback: v2/seriesid endpoint with frequency=daily
SPOT_SERIES_IDS = {
    "wti":   "PET.RWTC.D",
    "brent": "PET.RBRTE.D",
    "ho":    "PET.EER_EPD2F_PF4_Y35NY_DPG.D",
}
SPOT_SERIES_CODES = {        # short codes used in the route-based endpoint
    "wti":   "RWTC",
    "brent": "RBRTE",
    "ho":    "EER_EPD2F_PF4_Y35NY_DPG",
}
SERIES_CODE_TO_KEY = {v: k for k, v in SPOT_SERIES_CODES.items()}

CACHE_FILE = Path(__file__).parent / "disruption_price_cache.json"
CACHE_MAX_AGE_HOURS = 24

# Base elasticity constants (applied at criticality = 100 / severity = outage)
BASE_ELASTICITY_CRUDE_PCT = 5.0
BASE_ELASTICITY_ARB_USD   = 2.0
BASE_ELASTICITY_CRACK_USD = 3.0


# ── EIA price fetching ───────────────────────────────────────────────────────

def _fetch_via_route(api_key: str) -> Dict[str, Dict[str, float]]:
    """Primary: petroleum/pri/spt/data/ with three series facets in one call."""
    params = [
        ("api_key", api_key),
        ("frequency", "daily"),
        ("data[0]", "value"),
        ("facets[series][]", "RWTC"),
        ("facets[series][]", "RBRTE"),
        ("facets[series][]", "EER_EPD2F_PF4_Y35NY_DPG"),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("length", 5000),
        ("offset", 0),
    ]
    try:
        resp = requests.get(SPOT_ROUTE, params=params, timeout=(5.0, 45.0))
        resp.raise_for_status()
        data = resp.json().get("response", {}).get("data", [])
        result: Dict[str, Dict[str, float]] = {}
        for row in data:
            period = row.get("period")
            series = row.get("series")
            value  = row.get("value")
            if not period or not series or value is None:
                continue
            key = SERIES_CODE_TO_KEY.get(series)
            if not key:
                continue
            result.setdefault(period, {})[key] = float(value)
        logger.info(f"EIA route fetch: {len(result)} trading days")
        return result
    except Exception as e:
        logger.warning(f"EIA route-based fetch failed: {e}; trying seriesid fallback")
        return {}


def _fetch_via_seriesid(api_key: str) -> Dict[str, Dict[str, float]]:
    """Fallback: fetch each series individually via /seriesid/{id}."""
    result: Dict[str, Dict[str, float]] = {}
    for key, series_id in SPOT_SERIES_IDS.items():
        try:
            url = f"{EIA_BASE}/seriesid/{series_id}"
            params = {"api_key": api_key, "frequency": "daily", "length": 5000}
            resp = requests.get(url, params=params, timeout=(5.0, 30.0))
            resp.raise_for_status()
            rows = resp.json().get("response", {}).get("data", [])
            for row in rows:
                period = row.get("period")
                value  = row.get("value")
                if period and value is not None:
                    result.setdefault(period, {})[key] = float(value)
        except Exception as e:
            logger.warning(f"EIA seriesid fetch for {key} failed: {e}")
    logger.info(f"EIA seriesid fallback: {len(result)} trading days")
    return result


def _load_cache() -> Optional[Dict]:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, "r") as f:
            obj = json.load(f)
        cached_at = datetime.fromisoformat(obj.get("cached_at", "2000-01-01"))
        if (datetime.now() - cached_at).total_seconds() < CACHE_MAX_AGE_HOURS * 3600:
            return obj.get("prices")
    except Exception:
        pass
    return None


def _save_cache(prices: Dict) -> None:
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"cached_at": datetime.now().isoformat(), "prices": prices}, f)
    except Exception as e:
        logger.warning(f"Could not save price cache: {e}")


def get_price_series() -> Dict[str, Dict[str, float]]:
    """
    Return {date_str: {wti, brent, ho}} from cache or EIA API.
    Uses per-series fetch (5000 rows each = ~20 years) as primary because the
    route-based multi-facet call only returns 5000 TOTAL rows across all series,
    which yields only ~6 years of daily data — insufficient for the event catalog.
    """
    cached = _load_cache()
    if cached:
        return cached
    api_key = os.getenv("EIA_API_KEY")
    if not api_key:
        logger.error("EIA_API_KEY not set; event study unavailable")
        return {}
    # Primary: per-series (full history per series)
    prices = _fetch_via_seriesid(api_key)
    if not prices:
        # Fallback: single multi-facet call (shorter history but 1 request)
        prices = _fetch_via_route(api_key)
    if prices:
        _save_cache(prices)
    return prices


# ── Trading-day helpers ──────────────────────────────────────────────────────

def _sorted_dates(prices: Dict) -> List[str]:
    return sorted(prices.keys())


def _find_nearest(sorted_dates: List[str], target: str, direction: int) -> Optional[str]:
    """
    direction =  1: first trading day ON or AFTER target (T+0)
    direction = -1: last trading day BEFORE target (T-1 baseline)
    """
    idx = bisect.bisect_left(sorted_dates, target)
    if direction == 1:
        return sorted_dates[idx] if idx < len(sorted_dates) else None
    else:
        return sorted_dates[idx - 1] if idx > 0 else None


def _nth_from(sorted_dates: List[str], anchor: str, n: int) -> Optional[str]:
    """Return the n-th trading day after anchor (n=0 is anchor itself)."""
    try:
        idx = sorted_dates.index(anchor)
        i2 = idx + n
        return sorted_dates[i2] if 0 <= i2 < len(sorted_dates) else None
    except ValueError:
        return None


# ── Event study ──────────────────────────────────────────────────────────────

def _returns_at_horizon(
    prices: Dict, sorted_dates: List[str],
    t0: str, n: int,
    wti_base: float, brent_base: float,
    arb_base: float, crack_base: Optional[float],
) -> Dict:
    td = _nth_from(sorted_dates, t0, n)
    if not td:
        return {}
    p = prices.get(td, {})
    wti   = p.get("wti")
    brent = p.get("brent")
    ho    = p.get("ho")
    out: Dict = {}
    if wti and wti_base:
        out["wti_pct"] = round((wti - wti_base) / wti_base * 100, 2)
    if brent and brent_base:
        out["brent_pct"] = round((brent - brent_base) / brent_base * 100, 2)
    if brent and wti:
        out["arb_usd"] = round((brent - wti) - arb_base, 2)
    if ho and wti:
        crack = ho * 42 - wti
        out["crack_usd"] = round(crack - crack_base, 2) if crack_base is not None else None
    return out


def compute_event_returns(event: Dict, prices: Dict, sorted_dates: List[str]) -> Optional[Dict]:
    """Compute T+0..T+20 returns for a single catalogued event."""
    event_date = event["date"]
    tm1 = _find_nearest(sorted_dates, event_date, direction=-1)
    t0  = _find_nearest(sorted_dates, event_date, direction=1)
    if not tm1 or not t0:
        return None
    baseline = prices.get(tm1, {})
    wti_base   = baseline.get("wti")
    brent_base = baseline.get("brent")
    ho_base    = baseline.get("ho")
    if wti_base is None or brent_base is None:
        return None
    arb_base   = brent_base - wti_base
    crack_base = (ho_base * 42 - wti_base) if ho_base else None

    kwargs = dict(prices=prices, sorted_dates=sorted_dates, t0=t0,
                  wti_base=wti_base, brent_base=brent_base,
                  arb_base=arb_base, crack_base=crack_base)

    return {
        "event_id":    event["event_id"],
        "node_id":     event.get("node_id"),
        "channel":     event.get("channel"),
        "severity":    event.get("severity"),
        "restored":    event.get("restored", False),
        "n_sources":   event.get("n_sources", 1),
        "source_scale":event.get("source_scale", "international"),
        "t_minus1":    tm1,
        "t0_date":     t0,
        "t0":  _returns_at_horizon(**kwargs, n=0),
        "t1":  _returns_at_horizon(**kwargs, n=1),
        "t5":  _returns_at_horizon(**kwargs, n=5),
        "t20": _returns_at_horizon(**kwargs, n=20),
    }


# ── Matrix aggregation ───────────────────────────────────────────────────────

def _vals(returns: List[Dict], horizon: str, key: str) -> List[Optional[float]]:
    return [r[horizon].get(key) for r in returns if horizon in r and r[horizon].get(key) is not None]


def _mean(v: List) -> Optional[float]:
    clean = [x for x in v if x is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _rng(v: List) -> Optional[Tuple[float, float]]:
    clean = [x for x in v if x is not None]
    return (round(min(clean), 2), round(max(clean), 2)) if len(clean) >= 2 else None


def _sign_agreement(vals: List, structural_sign: float) -> float:
    clean = [x for x in vals if x is not None]
    if not clean:
        return 0.0
    agrees = sum(1 for v in clean if (v * structural_sign) > 0)
    return round(agrees / len(clean), 2)


def _agg_horizon(returns: List[Dict], h: str) -> Dict:
    return {
        "wti_pct":    _mean(_vals(returns, h, "wti_pct")),
        "brent_pct":  _mean(_vals(returns, h, "brent_pct")),
        "arb_usd":    _mean(_vals(returns, h, "arb_usd")),
        "crack_usd":  _mean(_vals(returns, h, "crack_usd")),
        "wti_range":  _rng(_vals(returns, h, "wti_pct")),
        "brent_range":_rng(_vals(returns, h, "brent_pct")),
    }


def _compute_node_matrix(node_id: str, all_returns: List[Dict], channel: Optional[str] = None) -> Dict:
    subset = [r for r in all_returns if r.get("node_id") == node_id]
    if channel:
        subset = [r for r in subset if r.get("channel") == channel]
    if not subset:
        return {"count": 0, "source": "prior"}

    node = NODE_BY_ID.get(node_id, {})
    structural_sign = -1.0 if node.get("type") == "refining_hub" else 1.0
    t0_wti = _vals(subset, "t0", "wti_pct")
    sign_ag = _sign_agreement(t0_wti, structural_sign)
    n = len(subset)

    if n >= 2 and sign_ag >= 0.67:
        confidence = "HIGH"
    elif n == 1 and sign_ag >= 0.5:
        confidence = "MEDIUM"
    elif sign_ag < 0.33:
        confidence = "LOW"
    else:
        confidence = "MEDIUM"

    t0a = _agg_horizon(subset, "t0")
    t1a = _agg_horizon(subset, "t1")
    t5a = _agg_horizon(subset, "t5")
    # Headline horizon: largest absolute WTI move in {T+0, T+1, T+5}
    mags = [
        ("t0", abs(t0a.get("wti_pct") or 0)),
        ("t1", abs(t1a.get("wti_pct") or 0)),
        ("t5", abs(t5a.get("wti_pct") or 0)),
    ]
    headline_h = max(mags, key=lambda x: x[1])[0]

    return {
        "count": n,
        "source": "history",
        "confidence": confidence,
        "sign_agreement": sign_ag,
        "headline_horizon": headline_h,
        "t0":  t0a,
        "t1":  t1a,
        "t5":  t5a,
        "t20": _agg_horizon(subset, "t20"),
    }


# ── Structural prior ─────────────────────────────────────────────────────────

def compute_structural_prior(
    node: Dict, severity: str = "outage", restored: bool = False, channel: str = "production"
) -> Dict:
    """
    Direction × base-elasticity × criticality/100 × severity-multiplier.
    Sign-flip for refinery nodes: crude bearish, crack bullish.
    Transport vs production sign is identical for crude (both remove supply);
    for refineries the distinction is: inbound-transport-hit → crude softens
    locally even if crack still rises.
    """
    crit  = node.get("criticality", 20) / 100.0
    ntype = node.get("type", "production_hub")
    exp   = node.get("product_exposure", {})
    sev_m = {"scare": 0.5, "outage": 1.0, "sustained": 1.6}.get(severity, 1.0)
    sign  = -1 if restored else 1

    crude_sign = -1 if ntype == "refining_hub" else 1
    crack_sign = 1   # cracks always tighten when supply is disrupted

    wti_pct   = round(crude_sign * BASE_ELASTICITY_CRUDE_PCT * crit * sev_m * sign, 2)
    brent_pct = round(crude_sign * BASE_ELASTICITY_CRUDE_PCT * 1.2 * crit * sev_m * sign, 2)
    arb_usd   = round((exp.get("arb_usd", BASE_ELASTICITY_ARB_USD)) * crit * sev_m * sign, 2)

    crack_mult = 1.5 if ntype == "refining_hub" else 0.8
    crack_usd  = round(crack_sign * BASE_ELASTICITY_CRACK_USD * crack_mult * crit * sev_m * sign, 2)

    return {
        "wti_pct":   wti_pct,
        "brent_pct": brent_pct,
        "arb_usd":   arb_usd,
        "crack_usd": crack_usd,
        "source":    "structural_prior",
    }


# ── Full matrix computation ──────────────────────────────────────────────────

_matrix_cache: Optional[Dict] = None
_matrix_cache_time: Optional[datetime] = None
_MATRIX_TTL = 3600  # 1 hour


def get_full_impact_matrix(force: bool = False) -> Dict:
    """
    Compute and cache the complete node × contract impact matrix.
    Returns computed node entries, all event returns, and metadata.
    """
    global _matrix_cache, _matrix_cache_time
    if not force and _matrix_cache and _matrix_cache_time:
        if (datetime.now() - _matrix_cache_time).total_seconds() < _MATRIX_TTL:
            return _matrix_cache

    prices = get_price_series()
    sorted_dates = _sorted_dates(prices)

    # Compute returns for each catalogued event
    all_returns: List[Dict] = []
    event_details: List[Dict] = []
    for ev in DISRUPTION_EVENTS:
        ret = compute_event_returns(ev, prices, sorted_dates)
        if ret:
            all_returns.append(ret)
            event_details.append({**ev, **{k: v for k, v in ret.items() if k.startswith("t")}})

    # Aggregate by node
    nodes_out: Dict[str, Dict] = {}
    for node in NODE_DEFINITIONS:
        nid = node["id"]
        hist = _compute_node_matrix(nid, all_returns)

        # Per-channel breakdown
        by_channel: Dict = {}
        for ch in node.get("channels", []):
            ch_m = _compute_node_matrix(nid, all_returns, channel=ch)
            if ch_m.get("count", 0) > 0:
                by_channel[ch] = ch_m

        prior = compute_structural_prior(node)

        # Decide headline: history wins if n≥1 and sign-agreement not LOW
        if hist.get("count", 0) == 0:
            headline_src = "prior"
            headline     = prior
            confidence   = "STRUCTURAL"
        elif hist.get("confidence") == "LOW":
            headline_src = "prior"
            headline     = prior
            confidence   = "LOW"
        else:
            headline_src = "history"
            headline     = hist
            confidence   = hist.get("confidence", "MEDIUM")

        nodes_out[nid] = {
            "node":          node,
            "history_matrix":hist,
            "prior":         prior,
            "by_channel":    by_channel,
            "headline_source":headline_src,
            "headline":      headline,
            "confidence":    confidence,
            "analog_count":  hist.get("count", 0),
            "analogs":       [r for r in event_details if r.get("node_id") == nid],
        }

    _matrix_cache = {
        "nodes":              nodes_out,
        "all_event_returns":  all_returns,
        "price_date_range":   [sorted_dates[0] if sorted_dates else None,
                               sorted_dates[-1] if sorted_dates else None],
        "computed_at":        datetime.now().isoformat(),
        "events_computed":    len(all_returns),
        "has_price_data":     bool(prices),
    }
    _matrix_cache_time = datetime.now()
    return _matrix_cache


def apply_severity_scaling(
    impact: Dict, severity: str, restored: bool
) -> Dict:
    """Scale an impact dict by severity and flip sign if restored."""
    sev_m = {"scare": 0.5, "outage": 1.0, "sustained": 1.6}.get(severity, 1.0)
    flip  = -1 if restored else 1
    out: Dict = {}
    for k, v in impact.items():
        if isinstance(v, (int, float)) and v is not None:
            out[k] = round(v * sev_m * flip, 2)
        else:
            out[k] = v
    return out
