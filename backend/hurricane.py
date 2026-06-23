"""Live Atlantic hurricane tracking via NOAA NHC.

Pulls active storm positions / intensity / forecast from the public NOAA
National Hurricane Center JSON feed and overlays each storm onto known
Gulf-of-Mexico oil assets (refineries + offshore production) to produce an
oil-market-actionable risk readout.

Why this matters for oil:
- US Gulf produces ~15% of US crude and houses ~45% of US refining capacity
- A major storm shuts in crude production (bullish crude) and damages
  refineries (bearish crude, bullish products — refineries can't process)
- Markets typically price storm risk 3-5 days BEFORE landfall using the
  NHC forecast cone, then unwind quickly after the storm passes
- NHC data is fully public — Bloomberg/Reuters use the same source

Atlantic hurricane season: 1 Jun – 30 Nov. Outside this window the feed
is normally empty; the panel renders "no active storms"."""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import httpx

NHC_CURRENT_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"

# Major US Gulf Coast refineries — (name, kbpd capacity, lat, lon)
# Capacities from EIA refinery survey, Jan 2025. These 13 plants account
# for ~90% of US Gulf Coast (PADD 3) refining capacity, which is itself
# ~52% of total US refining capacity.
GULF_REFINERIES: List[Tuple[str, int, float, float]] = [
    ("Motiva Port Arthur, TX",       630, 29.85, -93.97),
    ("Marathon Galveston Bay, TX",   593, 29.38, -94.92),
    ("ExxonMobil Baytown, TX",       561, 29.74, -95.01),
    ("ExxonMobil Beaumont, TX",      366, 30.07, -94.10),
    ("Citgo Lake Charles, LA",       425, 30.22, -93.27),
    ("Phillips66 Lake Charles, LA",  260, 30.20, -93.30),
    ("ExxonMobil Baton Rouge, LA",   522, 30.50, -91.19),
    ("Marathon Garyville, LA",       597, 30.06, -90.62),
    ("Valero St. Charles, LA",       340, 29.99, -90.41),
    ("Shell Norco, LA",              240, 30.00, -90.42),
    ("Chevron Pascagoula, MS",       330, 30.36, -88.50),
    ("Phillips66 Sweeny, TX",        265, 29.05, -95.70),
    ("LyondellBasell Houston, TX",   264, 29.73, -95.20),
]
GULF_TOTAL_CAPACITY = sum(c for _, c, _, _ in GULF_REFINERIES)

# Federal Gulf-of-Mexico OCS production zone — Mississippi Canyon area.
# Storm passing through this box typically forces precautionary
# shut-ins of platforms (BSEE issues daily shut-in reports during).
GOM_PRODUCTION_BBOX = (25.5, -94.5, 30.0, -88.0)   # (S, W, N, E)
GOM_PRODUCTION_CENTER = (28.0, -89.0)
GOM_PRODUCTION_KBPD = 1700        # baseline federal-OCS production

# Hurricane-force winds extend 50-100 nm from the eye, tropical-storm-force
# winds 100-200 nm. We use 150 nm as the "asset at risk" threshold — close
# enough that operators precautionarily shut down even if landfall misses.
RISK_RADIUS_NM = 150


def _classify_intensity(wind_kt: float) -> str:
    """Saffir-Simpson category from sustained wind in knots."""
    if wind_kt >= 137: return "Cat 5"
    if wind_kt >= 113: return "Cat 4"
    if wind_kt >= 96:  return "Cat 3"
    if wind_kt >= 83:  return "Cat 2"
    if wind_kt >= 64:  return "Cat 1"
    if wind_kt >= 34:  return "TS"
    return "TD"


def _haversine_nm(lat1: float, lon1: float,
                  lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    r_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r_nm * math.asin(math.sqrt(a))


async def _fetch_current_storms() -> Optional[List[Dict]]:
    """Pull active storms from NOAA NHC CurrentStorms.json."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(NHC_CURRENT_URL, headers={
                "User-Agent": "Mozilla/5.0 (compatible; OilDeskDashboard/1.0)",
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    return data.get("activeStorms", []) or []


def _is_atlantic(storm: Dict) -> bool:
    """Atlantic basin storms have id starting with 'AL'; eastern Pacific
    storms ('EP') don't affect US Gulf oil assets so we drop them."""
    sid = str(storm.get("id", "") or storm.get("binNumber", "") or "")
    return sid.upper().startswith(("AL", "AT"))


def _enrich_storm(s: Dict) -> Optional[Dict]:
    """Compute oil-impact metadata for a single NHC storm record."""
    try:
        lat = float(s.get("latitudeNumeric"))
        lon = float(s.get("longitudeNumeric"))
    except (TypeError, ValueError):
        return None
    try:
        wind = float(s.get("intensity", 0) or 0)
    except (TypeError, ValueError):
        wind = 0.0
    try:
        pressure = float(s.get("pressure")) if s.get("pressure") else None
    except (TypeError, ValueError):
        pressure = None

    category = _classify_intensity(wind)

    # find nearest refinery + sum capacity within risk radius
    nearest_dist = None
    nearest_name = None
    capacity_at_risk = 0
    refineries_at_risk: List[Dict] = []
    for name, cap, rlat, rlon in GULF_REFINERIES:
        d = _haversine_nm(lat, lon, rlat, rlon)
        if nearest_dist is None or d < nearest_dist:
            nearest_dist = d
            nearest_name = name
        if d <= RISK_RADIUS_NM:
            capacity_at_risk += cap
            refineries_at_risk.append({
                "name": name, "distance_nm": round(d),
                "capacity_kbpd": cap,
            })
    refineries_at_risk.sort(key=lambda r: r["distance_nm"])

    # Offshore-production risk: storm inside the OCS bbox OR within
    # 200 nm of its centroid → assume full GoM shut-in precaution.
    in_gom_box = (GOM_PRODUCTION_BBOX[0] <= lat <= GOM_PRODUCTION_BBOX[2]
                  and GOM_PRODUCTION_BBOX[1] <= lon <= GOM_PRODUCTION_BBOX[3])
    gom_dist = _haversine_nm(lat, lon, *GOM_PRODUCTION_CENTER)
    if in_gom_box:
        production_at_risk = GOM_PRODUCTION_KBPD
    elif gom_dist < 200:
        production_at_risk = int(GOM_PRODUCTION_KBPD * 0.5)
    else:
        production_at_risk = 0

    cap_pct = round(100 * capacity_at_risk / GULF_TOTAL_CAPACITY, 1) \
        if GULF_TOTAL_CAPACITY else 0.0

    # Bullish/bearish hint — refineries shut hurts CRUDE demand (bearish
    # WTI) and squeezes PRODUCTS (bullish RBOB/HO cracks). Offshore
    # production shut-ins are unambiguously bullish for crude.
    if production_at_risk > 0 and capacity_at_risk < 500:
        tag, hint = "CRUDE BULLISH", (
            "Offshore production shut-in risk — bullish crude, "
            "neutral/slightly bullish products.")
    elif capacity_at_risk >= 1000:
        tag, hint = "PRODUCTS BULLISH", (
            f"~{cap_pct}% of US Gulf refining within 150 nm — "
            "bullish RBOB/HO cracks, bearish crude (refinery shut → "
            "no demand for feedstock).")
    elif capacity_at_risk > 0 or production_at_risk > 0:
        tag, hint = "WATCH", (
            "Limited oil-asset exposure — monitor track refinements.")
    else:
        nm = round(nearest_dist) if nearest_dist is not None else "?"
        tag, hint = "MONITOR", (
            f"No immediate oil-asset risk (nearest refinery {nm} nm away).")

    return {
        "id": s.get("id"),
        "name": s.get("name") or "Unnamed",
        "classification_raw": s.get("classification"),
        "category": category,
        "lat": round(lat, 2),
        "lon": round(lon, 2),
        "intensity_kt": wind,
        "pressure_mb": pressure,
        "movement_dir_deg": s.get("movementDir"),
        "movement_speed_kt": s.get("movementSpeed"),
        "last_update": s.get("lastUpdate"),
        "public_advisory_url": (
            (s.get("publicAdvisory") or {}).get("url")),
        "oil_impact": {
            "nearest_refinery": nearest_name,
            "nearest_distance_nm": round(nearest_dist)
                if nearest_dist is not None else None,
            "refineries_at_risk": refineries_at_risk,
            "refining_capacity_at_risk_kbpd": capacity_at_risk,
            "refining_capacity_at_risk_pct": cap_pct,
            "production_at_risk_kbpd": production_at_risk,
            "in_gom_box": in_gom_box,
            "gom_centroid_distance_nm": round(gom_dist),
            "tag": tag,
            "hint": hint,
        },
    }


class StormTracker:
    """Caches the latest enriched NHC storm list."""

    def __init__(self) -> None:
        self.storms: List[Dict] = []
        self.last_fetch: Optional[float] = None
        self.source = "pending first fetch"
        self.error: Optional[str] = None

    async def refresh(self) -> int:
        raw = await _fetch_current_storms()
        if raw is None:
            self.error = "NHC fetch failed"
            self.source = "NHC fetch failed (last good cached)"
            return 0
        self.error = None
        self.last_fetch = time.time()
        enriched: List[Dict] = []
        for s in raw:
            e = _enrich_storm(s)
            if e is not None:
                enriched.append(e)
        self.storms = enriched
        self.source = "NOAA NHC CurrentStorms.json"
        return len(self.storms)

    def snapshot(self) -> Dict:
        if not self.storms:
            overall_tag = "CLEAR"
            overall_status = "no active storms"
        else:
            tags = [s["oil_impact"]["tag"] for s in self.storms
                    if s.get("oil_impact")]
            if "PRODUCTS BULLISH" in tags or "CRUDE BULLISH" in tags:
                overall_tag = "GOM_THREAT"
                overall_status = "active threat to Gulf oil assets"
            elif "WATCH" in tags:
                overall_tag = "WATCH"
                overall_status = "storm near oil assets — monitoring"
            else:
                overall_tag = "DISTANT"
                overall_status = (f"{len(self.storms)} active "
                                  "storm(s), distant from oil assets")
        return {
            "storms": self.storms,
            "count": len(self.storms),
            "overall_tag": overall_tag,
            "overall_status": overall_status,
            "last_fetch": self.last_fetch,
            "source": self.source,
            "error": self.error,
            "gulf_total_capacity_kbpd": GULF_TOTAL_CAPACITY,
            "gulf_production_baseline_kbpd": GOM_PRODUCTION_KBPD,
            "n_refineries_tracked": len(GULF_REFINERIES),
            "risk_radius_nm": RISK_RADIUS_NM,
        }
