"""
ACLED (Armed Conflict Location & Event Data) node-risk overlay.

Fetches conflict events from ACLED API and geo-matches them to the
15 critical oil supply-chain nodes within calibrated radius thresholds.

Non-commercial use only per ACLED license.
  Registration: https://developer.acleddata.com
  Required env vars: ACLED_KEY, ACLED_EMAIL

Public surface:
  get_acled_events(days=30)     — cached geo-matched events near our nodes
  get_node_risk_overlay()       — per-node {risk_level, recent_acled_count, latest_event_date}
"""

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from services.oil_nodes import NODE_BY_ID, NODE_DEFINITIONS

logger = logging.getLogger(__name__)

ACLED_URL     = "https://api.acleddata.com/acled/read"
ACLED_TIMEOUT = (5.0, 20.0)

# (lat, lon, radius_km) — radius tuned to each node's geographic footprint
NODE_COORDS: Dict[str, Tuple[float, float, float]] = {
    "hormuz":          (26.5,   56.5,  350.0),   # entire Persian Gulf
    "malacca":         ( 1.3,  103.8,  250.0),
    "suez":            (30.0,   32.5,  150.0),
    "bab_el_mandeb":   (12.6,   43.5,  500.0),   # Houthi range extends to Red Sea
    "bosphorus":       (41.1,   29.0,  200.0),
    "ghawar_abqaiq":   (25.9,   49.7,  350.0),   # Eastern Province
    "permian":         (31.8, -102.0,  600.0),   # West Texas basin
    "russia_siberia":  (60.0,   70.0, 1000.0),   # broad Siberia footprint
    "north_sea":       (57.0,    2.5,  450.0),
    "basra":           (30.5,   47.8,  250.0),   # southern Iraq
    "usgc_padd3":      (29.8,  -94.0,  600.0),
    "jamnagar":        (22.5,   70.1,  200.0),
    "rotterdam_ara":   (51.9,    4.4,  200.0),
    "singapore_jurong":( 1.3,  103.7,  150.0),
    "ulsan":           (35.5,  129.4,  150.0),
}

_acled_cache: Optional[Tuple[List[Dict], datetime]] = None
_ACLED_TTL = 3600


# ── geo ───────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


def _geo_match(lat: float, lon: float) -> Optional[Tuple[str, float]]:
    """Return (node_id, distance_km) for the closest node whose radius contains (lat, lon)."""
    best_id, best_dist = None, float("inf")
    for node_id, (nlat, nlon, radius) in NODE_COORDS.items():
        d = _haversine_km(lat, lon, nlat, nlon)
        if d <= radius and d < best_dist:
            best_id, best_dist = node_id, d
    if best_id:
        return best_id, best_dist
    return None


# ── API ───────────────────────────────────────────────────────────────────────

def fetch_acled_events(days: int = 30) -> List[Dict]:
    """
    Query ACLED for violence/explosion events; geo-match to our 15 nodes.
    Returns only matched events (events near none of our nodes are dropped).
    """
    api_key = os.getenv("ACLED_KEY")
    email   = os.getenv("ACLED_EMAIL")
    if not api_key or not email:
        return []

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "key":              api_key,
        "email":            email,
        "event_date":       f"{start.strftime('%Y-%m-%d')}|{end.strftime('%Y-%m-%d')}",
        "event_date_where": "BETWEEN",
        "event_type":       "Explosions/Remote violence|Battles|Riots",
        "limit":            1000,
        "format":           "json",
    }
    try:
        resp = requests.get(ACLED_URL, params=params, timeout=ACLED_TIMEOUT)
        resp.raise_for_status()
        raw = resp.json().get("data", [])
    except Exception as e:
        logger.warning(f"ACLED fetch failed: {e}")
        return []

    result: List[Dict] = []
    for ev in raw:
        try:
            lat = float(ev.get("latitude") or 0)
            lon = float(ev.get("longitude") or 0)
        except (TypeError, ValueError):
            continue
        if lat == 0 and lon == 0:
            continue

        match = _geo_match(lat, lon)
        if match is None:
            continue

        node_id, dist_km = match
        node = NODE_BY_ID.get(node_id, {})

        result.append({
            "event_id":          ev.get("event_id_cnty"),
            "event_date":        ev.get("event_date"),
            "event_type":        ev.get("event_type"),
            "sub_event_type":    ev.get("sub_event_type"),
            "actor1":            ev.get("actor1"),
            "country":           ev.get("country"),
            "location":          ev.get("location"),
            "latitude":          lat,
            "longitude":         lon,
            "notes":             ev.get("notes", "")[:300],
            "fatalities":        int(ev.get("fatalities") or 0),
            "matched_node_id":   node_id,
            "matched_node_name": node.get("name"),
            "matched_node_type": node.get("type"),
            "distance_km":       round(dist_km, 0),
            "source":            "ACLED",
        })

    result.sort(key=lambda x: x.get("event_date", ""), reverse=True)
    logger.info("ACLED: %d geo-matched events (of %d fetched)", len(result), len(raw))
    return result


def get_acled_events(days: int = 30, force: bool = False) -> List[Dict]:
    """Cached wrapper around fetch_acled_events."""
    global _acled_cache
    if not force and _acled_cache:
        events, ts = _acled_cache
        if (datetime.now(timezone.utc) - ts).total_seconds() < _ACLED_TTL:
            return events
    events = fetch_acled_events(days=days)
    _acled_cache = (events, datetime.now(timezone.utc))
    return events


def get_node_risk_overlay(acled_events: Optional[List[Dict]] = None) -> Dict[str, Dict]:
    """
    Aggregate per-node risk from ACLED events.
    Returns {node_id: {risk_level, recent_acled_count, latest_event_date, source}}
    """
    if acled_events is None:
        acled_events = get_acled_events()

    counts: Dict[str, List[Dict]] = {}
    for ev in acled_events:
        nid = ev.get("matched_node_id")
        if nid:
            counts.setdefault(nid, []).append(ev)

    result: Dict[str, Dict] = {}
    for node in NODE_DEFINITIONS:
        nid  = node["id"]
        evs  = counts.get(nid, [])
        n    = len(evs)
        latest = max((e.get("event_date", "") for e in evs), default=None) if evs else None

        if n >= 10:
            risk = "HIGH"
        elif n >= 3:
            risk = "MEDIUM"
        elif n >= 1:
            risk = "LOW"
        else:
            risk = "NONE"

        result[nid] = {
            "node_id":           nid,
            "risk_level":        risk,
            "recent_acled_count":n,
            "latest_event_date": latest,
            "source":            "ACLED",
        }

    return result
