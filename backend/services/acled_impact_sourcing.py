"""
Stage 1a (completion) — ACLED → event-impact sourcing.

The hard part of putting ACLED into the base-rate engine is NOT fetching — it is
that ACLED conflict data is dense and CONTINUOUS (tens of thousands of events near
a single node), while the impact DB needs DISTINCT EPISODES (spec invariant 8:
"report distinct episodes, not just event counts — clustered extremes inflate n").

Gap-based segmentation fails here: Yemen's unbroken 2015→2025 war has no 21-day
lull, so it collapses into one artefact-dated mega-row — not the discrete Red Sea
ESCALATION we care about. So this module detects ESCALATIONS instead:
  1. read the full node-near ACLED history (direct DB read, no 5000-row news cap),
  2. bin events per node by month and compute that node's OWN baseline activity,
  3. flag SPIKE months where activity jumps well above the node's baseline, and
     merge consecutive spike months into an escalation episode dated at its onset,
  4. keep only SIGNIFICANT episodes (fatality / count thresholds),
  5. compute point-in-time EIA returns at onset, apply the SAME relevance gate as
     the catalog, write tagged source_domain='ACLED' + id 'acled_<node>_<onset>',
  6. DEDUPE vs the curated catalog (same node, onset within 30 days) so an episode
     the catalog already has (Abqaiq, Houthi Red Sea) is not double-counted.

The result is a bounded set of distinct escalation episodes that deepen the analog
pool without swamping the 20 curated events — and stay identifiable/removable.
"""

import logging
import math
import os
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Significance: an episode must clear ONE of these to count as a disruption
MIN_PEAK_FATALITIES  = 10
MIN_TOTAL_FATALITIES = 30
MIN_EVENTS           = 8
CATALOG_DEDUP_DAYS   = 30
SPIKE_FACTOR         = 2.0   # a month is "elevated" if count >= baseline*F + pad
SPIKE_PAD            = 3


def _days_between(a: str, b: str) -> int:
    return abs((datetime.strptime(a[:10], "%Y-%m-%d") - datetime.strptime(b[:10], "%Y-%m-%d")).days)


def _read_full_node_history() -> Dict[str, List[Dict]]:
    """Full node-near ACLED history, geo-matched, with NO 5000-row cap."""
    from services.acled_fetcher import ACLED_DB_PATH, _geo_match
    by_node: Dict[str, List[Dict]] = defaultdict(list)
    try:
        conn = sqlite3.connect(f"file:{ACLED_DB_PATH}?mode=ro", uri=True, timeout=10)
        rows = conn.execute(
            "SELECT event_date, event_type, country, latitude, longitude, fatalities "
            "FROM events WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning("ACLED full read failed: %s", e)
        return {}
    for ev_date, etype, country, lat, lon, fat in rows:
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue
        m = _geo_match(lat, lon)
        if not m:
            continue
        by_node[m[0]].append({
            "event_date": ev_date, "event_type": etype, "country": country,
            "fatalities": int(fat or 0),
        })
    return by_node


def _spike_episodes(events: List[Dict]) -> List[Dict]:
    """Detect escalation episodes as runs of months above the node's baseline."""
    if not events:
        return []
    by_month: Dict[str, List[Dict]] = defaultdict(list)
    for e in events:
        by_month[e["event_date"][:7]].append(e)
    months = sorted(by_month)
    counts = [len(by_month[m]) for m in months]
    counts_sorted = sorted(counts)
    baseline = counts_sorted[len(counts_sorted) // 2]  # median monthly count
    threshold = baseline * SPIKE_FACTOR + SPIKE_PAD

    episodes: List[Dict] = []
    run: List[str] = []

    def _flush(run_months: List[str]):
        if not run_months:
            return
        evs = [e for mth in run_months for e in by_month[mth]]
        evs.sort(key=lambda e: e["event_date"])
        fats = [e["fatalities"] for e in evs]
        peak = max(evs, key=lambda e: e["fatalities"])
        episodes.append({
            "onset": evs[0]["event_date"], "end": evs[-1]["event_date"],
            "n_events": len(evs), "total_fat": sum(fats),
            "peak_fat": max(fats) if fats else 0,
            "duration": _days_between(evs[0]["event_date"], evs[-1]["event_date"]),
            "peak_event": peak,
        })

    for m, c in zip(months, counts):
        if c >= threshold:
            run.append(m)
        else:
            _flush(run); run = []
    _flush(run)
    return episodes


def _significant(ep: Dict) -> bool:
    return (ep["peak_fat"]  >= MIN_PEAK_FATALITIES or
            ep["total_fat"] >= MIN_TOTAL_FATALITIES or
            ep["n_events"]  >= MIN_EVENTS)


def _severity(ep: Dict) -> str:
    if ep["total_fat"] >= 100 or ep["duration"] >= 90:
        return "sustained"
    if ep["total_fat"] >= 20 or ep["duration"] >= 14 or ep["n_events"] >= 20:
        return "outage"
    return "scare"


def _channel_for(node_type: str) -> str:
    return "transport" if node_type == "chokepoint" else "production"


def build_episodes() -> List[Dict]:
    """Return all significant ACLED escalation episodes per node (no DB writes)."""
    from services.oil_nodes import NODE_BY_ID

    by_node = _read_full_node_history()
    episodes: List[Dict] = []
    for nid, evs in by_node.items():
        node = NODE_BY_ID.get(nid, {})
        ntype = node.get("type", "chokepoint")
        for ep in _spike_episodes(evs):
            if not _significant(ep):
                continue
            ep["node_id"]   = nid
            ep["node_type"] = ntype
            ep["channel"]   = _channel_for(ntype)
            ep["severity"]  = _severity(ep)
            episodes.append(ep)
    episodes.sort(key=lambda e: (e["node_id"], e["onset"]))
    return episodes


def backfill_acled_to_impact(force: bool = False, dry_run: bool = False) -> Dict:
    """
    Write significant ACLED episodes into event_impact as distinct, tagged rows.
    Set dry_run=True to return the episode summary without writing.
    """
    from services.event_impact_db import (
        get_conn, init_db, upsert_event, passes_gate,
        _classify_magnitude_and_fired, _h, BASIN_MAP,
    )
    from services.eia_event_engine import (
        get_price_series, compute_event_returns, compute_structural_prior,
    )
    from services.oil_nodes import NODE_BY_ID
    from services.disruption_classifier import _most_exposed_contract
    from services.event_catalog import DISRUPTION_EVENTS

    init_db()
    episodes = build_episodes()

    # Catalog events per node (for dedup)
    catalog_by_node: Dict[str, List[str]] = {}
    for ce in DISRUPTION_EVENTS:
        if ce.get("node_id"):
            catalog_by_node.setdefault(ce["node_id"], []).append(ce["date"])

    prices = get_price_series()
    sorted_dates = sorted(prices.keys()) if prices else []
    now_iso = datetime.now().isoformat()

    counts = {"candidates": len(episodes), "written": 0, "gated_out": 0,
              "catalog_dup": 0, "no_price": 0}
    summary: List[Dict] = []

    for ep in episodes:
        nid     = ep["node_id"]
        onset   = ep["onset"]
        node    = NODE_BY_ID.get(nid, {})
        channel = ep["channel"]
        severity= ep["severity"]

        # dedup vs catalog (same node, onset within window)
        if any(_days_between(onset, d) <= CATALOG_DEDUP_DAYS
               for d in catalog_by_node.get(nid, [])):
            counts["catalog_dup"] += 1
            continue

        most_exp = _most_exposed_contract(node, channel, False) if node else "brent_flat"
        basin    = BASIN_MAP.get(nid, "Atlantic")
        prior    = compute_structural_prior(node, severity=severity,
                                             restored=False, channel=channel) if node else None

        ev_for_returns = {"event_id": f"acled_{nid}_{onset}", "date": onset,
                          "node_id": nid, "channel": channel, "severity": severity}
        ret = compute_event_returns(ev_for_returns, prices, sorted_dates) if prices else None
        t0  = ret.get("t0", {}) if ret else {}
        t1  = ret.get("t1", {}) if ret else {}
        t5  = ret.get("t5", {}) if ret else {}
        t20 = ret.get("t20", {}) if ret else {}
        has_price = bool(ret and t0)
        if not has_price:
            counts["no_price"] += 1

        if not passes_gate(nid, severity, t0 or None, most_exp):
            counts["gated_out"] += 1
            continue

        mag, dir_agree, fired = _classify_magnitude_and_fired(
            t0 or None, t1 or None, t5 or None, most_exp, prior)
        src_tag = "history" if has_price else "prior"
        confidence = "HIGH" if fired else ("MEDIUM" if mag != "none" else "LOW")

        row = {
            "event_id": f"acled_{nid}_{onset}", "event_date": onset,
            "detected_at": now_iso,
            "headline": (f"[ACLED] {ep['n_events']} conflict events near {node.get('name', nid)} "
                         f"({onset}→{ep['end']}, {ep['total_fat']} fatalities)"),
            "url": None, "source_domain": "ACLED",
            "n_sources": ep["n_events"], "source_scale": "regional",
            "node_id": nid, "basin": basin,
            "region_geo": ep["peak_event"].get("country", ""),
            "channel": channel, "severity": severity,
            "restored": 0, "anticipated": 0,
            "most_exposed_contract": most_exp,
            "baseline_ref": ret.get("t_minus1") if ret else None,
            "wti_t0":   _h(t0, "wti_pct"),   "wti_t1":   _h(t1, "wti_pct"),
            "wti_t5":   _h(t5, "wti_pct"),   "wti_t20":  _h(t20, "wti_pct"),
            "brent_t0": _h(t0, "brent_pct"), "brent_t1": _h(t1, "brent_pct"),
            "brent_t5": _h(t5, "brent_pct"), "brent_t20":_h(t20, "brent_pct"),
            "arb_t0":   _h(t0, "arb_usd"),   "arb_t1":   _h(t1, "arb_usd"),
            "arb_t5":   _h(t5, "arb_usd"),   "arb_t20":  _h(t20, "arb_usd"),
            "distillate_crack_t0": _h(t0, "crack_usd"), "distillate_crack_t1": _h(t1, "crack_usd"),
            "distillate_crack_t5": _h(t5, "crack_usd"), "distillate_crack_t20": _h(t20, "crack_usd"),
            "magnitude_class": mag, "fired": 1 if fired else 0,
            "direction_agreement": 1 if dir_agree else 0,
            "source_tag": src_tag, "confidence": confidence,
            "confound_note": None, "created_at": now_iso, "updated_at": now_iso,
        }
        summary.append({"event_id": row["event_id"], "node": nid, "onset": onset,
                        "severity": severity, "n_events": ep["n_events"],
                        "total_fat": ep["total_fat"], "wti_t0": row["wti_t0"],
                        "fired": bool(fired), "src": src_tag})
        if not dry_run:
            upsert_event(row)
        counts["written"] += 1

    counts["dry_run"] = dry_run
    return {"counts": counts, "episodes": summary}
