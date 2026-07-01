"""
ACLED (Armed Conflict Location & Event Data) — persistent scraper + node-risk overlay.

Architecture mirrors gdelt_fetcher: background job builds a local SQLite DB by
scraping target countries one at a time (forward + backward pass). The overlay
endpoint reads from local DB (fast, no API dependency) and falls back to live API
when the DB is empty.

Auth: OAuth 2.0 (email + password → Bearer token, 24h validity, auto-refreshed).
  Register free at https://acleddata.com/user/register
  Required env vars: ACLED_EMAIL, ACLED_PASSWORD

Background job: scrape_one_cycle()
  — called by APScheduler every 15 min.
  — picks the next country from TARGET_COUNTRIES in rotation.
  — forward pass: latest_fetched_end → now for that country.
  — backward pass: extends one 30-day window further into the past.
  — stops at MAX_BACKFILL_DAYS (5 years) per country.

Storage: %LOCALAPPDATA%/Dashboard_v3/DB/acled_events.db (outside OneDrive).

Public surface:
  scrape_one_cycle()         — APScheduler hook
  get_stored_events(days)    — read from DB, geo-match to nodes
  get_acled_events(days)     — cached wrapper (DB → live API fallback)
  get_node_risk_overlay()    — per-node risk summary
  get_scrape_status()        — monitoring helper
"""

import logging
import math
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests

from services.oil_nodes import NODE_BY_ID, NODE_DEFINITIONS

logger = logging.getLogger(__name__)

ACLED_API_URL  = "https://acleddata.com/api/acled/read"
ACLED_OAUTH_URL= "https://acleddata.com/oauth/token"
ACLED_TIMEOUT  = (5.0, 20.0)
SCRAPE_RATE_DELAY = 2.0      # seconds between API requests
MAX_BACKFILL_DAYS = 5 * 365  # 5 years per country

# ── OAuth token cache ─────────────────────────────────────────────────────────

_token_cache: Dict = {}   # {"access_token": ..., "expires_at": datetime}

def _get_token() -> Optional[str]:
    """
    Return a valid Bearer token, fetching or refreshing as needed.
    Returns None if credentials are not configured.
    """
    email    = os.getenv("ACLED_EMAIL")
    password = os.getenv("ACLED_PASSWORD")
    if not email or not password:
        return None

    # Return cached token if still valid (with 5-min margin)
    if _token_cache.get("access_token"):
        expires_at = _token_cache.get("expires_at")
        if expires_at and datetime.now(timezone.utc) < expires_at - timedelta(minutes=5):
            return _token_cache["access_token"]

    try:
        resp = requests.post(
            ACLED_OAUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "username":   email,
                "password":   password,
                "grant_type": "password",
                "client_id":  "acled",
                "scope":      "authenticated",
            },
            timeout=(5.0, 15.0),
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 86400))
        _token_cache["access_token"] = token
        _token_cache["expires_at"]   = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        logger.info("ACLED: OAuth token obtained (valid %d s)", expires_in)
        return token
    except Exception as e:
        logger.warning("ACLED OAuth token fetch failed: %s", e)
        return None

_local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
ACLED_DB_PATH = os.environ.get(
    "ACLED_DB_PATH",
    os.path.join(_local, "Dashboard_v3", "DB", "acled_events.db"),
)

# Countries that contain or are near our 15 oil-supply nodes
TARGET_COUNTRIES = [
    # Hormuz / Persian Gulf
    "Iran", "United Arab Emirates", "Oman", "Bahrain", "Qatar", "Kuwait",
    # Bab el-Mandeb / Red Sea
    "Yemen", "Djibouti", "Eritrea", "Somalia",
    # Suez
    "Egypt",
    # Bosphorus
    "Turkey",
    # Ghawar / Abqaiq / Basra
    "Saudi Arabia", "Iraq",
    # Malacca
    "Malaysia", "Singapore", "Indonesia",
    # Permian / USGC
    "United States",
    # Russia Siberia
    "Russia",
    # North Sea
    "United Kingdom", "Norway",
    # Rotterdam / ARA
    "Netherlands", "Belgium",
    # Jamnagar
    "India",
    # Ulsan
    "South Korea",
]

# Node geo-coordinates: (lat, lon, radius_km)
NODE_COORDS: Dict[str, Tuple[float, float, float]] = {
    "hormuz":           (26.5,   56.5,  350.0),
    "malacca":          ( 1.3,  103.8,  250.0),
    "suez":             (30.0,   32.5,  150.0),
    "bab_el_mandeb":    (12.6,   43.5,  500.0),
    "bosphorus":        (41.1,   29.0,  200.0),
    "ghawar_abqaiq":    (25.9,   49.7,  350.0),
    "permian":          (31.8, -102.0,  600.0),
    "russia_siberia":   (60.0,   70.0, 1000.0),
    "north_sea":        (57.0,    2.5,  450.0),
    "basra":            (30.5,   47.8,  250.0),
    "usgc_padd3":       (29.8,  -94.0,  600.0),
    "jamnagar":         (22.5,   70.1,  200.0),
    "rotterdam_ara":    (51.9,    4.4,  200.0),
    "singapore_jurong": ( 1.3,  103.7,  150.0),
    "ulsan":            (35.5,  129.4,  150.0),
}


# ── SQLite persistence ────────────────────────────────────────────────────────

def ensure_acled_db() -> None:
    os.makedirs(os.path.dirname(ACLED_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(ACLED_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id        TEXT PRIMARY KEY,
            event_date      TEXT,
            event_type      TEXT,
            sub_event_type  TEXT,
            disorder_type   TEXT,
            actor1          TEXT,
            actor2          TEXT,
            country         TEXT,
            admin1          TEXT,
            location        TEXT,
            latitude        REAL,
            longitude       REAL,
            fatalities      INTEGER DEFAULT 0,
            notes           TEXT,
            source          TEXT,
            source_scale    TEXT,
            fetched_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ev_date    ON events(event_date);
        CREATE INDEX IF NOT EXISTS idx_ev_country ON events(country);
        CREATE TABLE IF NOT EXISTS scrape_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.close()


def _get_state(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM scrape_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def _set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO scrape_state (key,value) VALUES (?,?)", (key, value))


def _insert_batch(conn: sqlite3.Connection, events: List[Dict], fetched_at: str) -> int:
    if not events:
        return 0
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO events "
        "(event_id,event_date,event_type,sub_event_type,disorder_type,"
        "actor1,actor2,country,admin1,location,latitude,longitude,"
        "fatalities,notes,source,source_scale,fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                ev.get("event_id_cnty") or f"{ev.get('country','')}_{ev.get('event_date','')}_{ev.get('latitude',0)}",
                ev.get("event_date"),
                ev.get("event_type"),
                ev.get("sub_event_type"),
                ev.get("disorder_type"),
                ev.get("actor1"),
                ev.get("actor2"),
                ev.get("country"),
                ev.get("admin1"),
                ev.get("location"),
                _safe_float(ev.get("latitude")),
                _safe_float(ev.get("longitude")),
                int(ev.get("fatalities") or 0),
                (ev.get("notes") or "")[:500],
                ev.get("source"),
                ev.get("source_scale"),
                fetched_at,
            )
            for ev in events
        ],
    )
    conn.commit()
    return conn.total_changes - before


def _safe_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── ACLED API ─────────────────────────────────────────────────────────────────

def _fetch_window(country: str, start_dt: datetime, end_dt: datetime) -> List[Dict]:
    """Fetch violence/battle/explosion events for one country in a date window."""
    token = _get_token()
    if not token:
        return []
    params = {
        "country":          country,
        "event_date":       f"{start_dt.strftime('%Y-%m-%d')}|{end_dt.strftime('%Y-%m-%d')}",
        "event_date_where": "BETWEEN",
        "event_type":       "Explosions/Remote violence|Battles|Strategic developments",
        "limit":            5000,
        "_format":          "json",
    }
    try:
        resp = requests.get(
            ACLED_API_URL, params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=ACLED_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("data") or []
    except Exception as e:
        logger.warning("ACLED fetch failed (%s %s→%s): %s",
                       country, start_dt.date(), end_dt.date(), e)
        return []


# ── Main scrape cycle (called by scheduler) ───────────────────────────────────

def scrape_one_cycle() -> Dict:
    """
    One scheduler tick. Picks the next country from TARGET_COUNTRIES in rotation.
    Forward pass: latest_fetched_end → now.
    Backward pass: extends 30 days further into history (stops at MAX_BACKFILL_DAYS).

    Returns {country, new_events, forward_new, backward_new}.
    """
    ensure_acled_db()
    conn = sqlite3.connect(ACLED_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    total_new = 0

    try:
        # Pick next country via round-robin pointer
        idx_str  = _get_state(conn, "country_idx", "0")
        idx      = int(idx_str) % len(TARGET_COUNTRIES)
        country  = TARGET_COUNTRIES[idx]
        next_idx = (idx + 1) % len(TARGET_COUNTRIES)
        _set_state(conn, "country_idx", str(next_idx))
        conn.commit()

        fwd_key = f"latest_end_{country}"
        bwd_key = f"oldest_start_{country}"

        # ── forward pass ──────────────────────────────────────────────────────
        latest_str = _get_state(conn, fwd_key)
        if latest_str:
            try:
                fwd_start = datetime.fromisoformat(latest_str)
                if fwd_start.tzinfo is None:
                    fwd_start = fwd_start.replace(tzinfo=timezone.utc)
            except Exception:
                fwd_start = now - timedelta(days=30)
            fwd_start = max(fwd_start, now - timedelta(days=30))
        else:
            fwd_start = now - timedelta(days=30)

        raw = _fetch_window(country, fwd_start, now)
        fwd_new = _insert_batch(conn, raw, fetched_at)
        total_new += fwd_new
        _set_state(conn, fwd_key, now.isoformat())
        conn.commit()

        time.sleep(SCRAPE_RATE_DELAY)

        # ── backward pass ─────────────────────────────────────────────────────
        cutoff = now - timedelta(days=MAX_BACKFILL_DAYS)
        oldest_str = _get_state(conn, bwd_key)
        if oldest_str:
            try:
                window_end = datetime.fromisoformat(oldest_str)
                if window_end.tzinfo is None:
                    window_end = window_end.replace(tzinfo=timezone.utc)
            except Exception:
                window_end = fwd_start
        else:
            window_end = fwd_start

        bwd_new = 0
        if window_end > cutoff:
            window_start = max(window_end - timedelta(days=30), cutoff)
            raw = _fetch_window(country, window_start, window_end)
            bwd_new = _insert_batch(conn, raw, fetched_at)
            total_new += bwd_new
            _set_state(conn, bwd_key, window_start.isoformat())
            conn.commit()

        logger.info(
            "ACLED cycle: %s → +%d events (fwd=%d bwd=%d)",
            country, total_new, fwd_new, bwd_new,
        )
        return {"country": country, "new_events": total_new,
                "forward_new": fwd_new, "backward_new": bwd_new}

    except Exception as e:
        logger.error("ACLED scrape_one_cycle error: %s", e)
        return {"country": "?", "new_events": 0, "error": str(e)}
    finally:
        conn.close()


# ── Geo helpers ───────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2)
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


def _geo_match(lat: float, lon: float) -> Optional[Tuple[str, float]]:
    """Return (node_id, distance_km) for the nearest node whose radius contains (lat, lon)."""
    best_id, best_dist = None, float("inf")
    for node_id, (nlat, nlon, radius) in NODE_COORDS.items():
        d = _haversine_km(lat, lon, nlat, nlon)
        if d <= radius and d < best_dist:
            best_id, best_dist = node_id, d
    return (best_id, best_dist) if best_id else None


# ── Read API ──────────────────────────────────────────────────────────────────

def get_stored_events(days: int = 30) -> List[Dict]:
    """
    Read geo-matched events from local DB for the most recent `days` days of
    AVAILABLE data. Returns only events within radius of one of our 15 nodes.

    The window is anchored to the latest event actually in the DB, not the wall
    clock: ACLED data lags the calendar by months, and in some environments the
    system clock runs ahead of ACLED's coverage end. Anchoring to MAX(event_date)
    means "the last N days of data we have" — so a fresh deployment shows truly
    recent events while a stale-data / clock-skewed one still surfaces its newest.
    """
    try:
        ensure_acled_db()
        conn   = sqlite3.connect(f"file:{ACLED_DB_PATH}?mode=ro", uri=True, timeout=5)
        latest_row = conn.execute("SELECT MAX(event_date) FROM events").fetchone()
        data_latest = latest_row[0] if latest_row and latest_row[0] else None
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # anchor = the newest data point, but never beyond today
        anchor = min(now_str, data_latest) if data_latest else now_str
        cutoff = (datetime.strptime(anchor, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
        rows   = conn.execute(
            "SELECT event_id, event_date, event_type, sub_event_type, disorder_type, "
            "actor1, actor2, country, admin1, location, latitude, longitude, fatalities, notes "
            "FROM events WHERE event_date >= ? ORDER BY event_date DESC LIMIT 5000",
            (cutoff,),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning("ACLED DB read failed: %s", e)
        return []

    result: List[Dict] = []
    for r in rows:
        lat = r[10]
        lon = r[11]
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue
        match = _geo_match(lat, lon)
        if match is None:
            continue
        node_id, dist_km = match
        node = NODE_BY_ID.get(node_id, {})
        result.append({
            "event_id":          r[0],
            "event_date":        r[1],
            "event_type":        r[2],
            "sub_event_type":    r[3],
            "actor1":            r[5],
            "country":           r[7],
            "location":          r[9],
            "latitude":          lat,
            "longitude":         lon,
            "notes":             (r[13] or "")[:300],
            "fatalities":        r[12] or 0,
            "matched_node_id":   node_id,
            "matched_node_name": node.get("name"),
            "matched_node_type": node.get("type"),
            "distance_km":       round(dist_km, 0),
            "source":            "ACLED",
        })

    result.sort(key=lambda x: x.get("event_date", ""), reverse=True)
    return result


def _fetch_live_fallback(days: int = 30) -> List[Dict]:
    """Live API fetch — used when local DB is empty."""
    token = _get_token()
    if not token:
        return []

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "event_date":       f"{start.strftime('%Y-%m-%d')}|{end.strftime('%Y-%m-%d')}",
        "event_date_where": "BETWEEN",
        "event_type":       "Explosions/Remote violence|Battles|Strategic developments",
        "limit":            1000,
        "_format":          "json",
    }
    try:
        resp = requests.get(
            ACLED_API_URL, params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=ACLED_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json().get("data", [])
    except Exception as e:
        logger.warning("ACLED live fallback failed: %s", e)
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
        if not match:
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
            "notes":             (ev.get("notes") or "")[:300],
            "fatalities":        int(ev.get("fatalities") or 0),
            "matched_node_id":   node_id,
            "matched_node_name": node.get("name"),
            "matched_node_type": node.get("type"),
            "distance_km":       round(dist_km, 0),
            "source":            "ACLED",
        })
    result.sort(key=lambda x: x.get("event_date", ""), reverse=True)
    return result


_acled_cache: Optional[Tuple[List[Dict], datetime]] = None
_ACLED_TTL = 3600  # 1 hour


def get_acled_events(days: int = 30, force: bool = False) -> List[Dict]:
    """
    Cached wrapper. DB-first → live API fallback.
    Cache is refreshed every hour or when `force=True`.
    """
    global _acled_cache
    if not force and _acled_cache:
        events, ts = _acled_cache
        if (datetime.now(timezone.utc) - ts).total_seconds() < _ACLED_TTL:
            return events

    events = get_stored_events(days=days)
    if not events:
        events = _fetch_live_fallback(days=days)

    _acled_cache = (events, datetime.now(timezone.utc))
    return events


def get_node_risk_overlay(acled_events: Optional[List[Dict]] = None) -> Dict[str, Dict]:
    """Aggregate per-node risk from ACLED events."""
    if acled_events is None:
        acled_events = get_acled_events()

    counts: Dict[str, List[Dict]] = {}
    for ev in acled_events:
        nid = ev.get("matched_node_id")
        if nid:
            counts.setdefault(nid, []).append(ev)

    result: Dict[str, Dict] = {}
    for node in NODE_DEFINITIONS:
        nid    = node["id"]
        evs    = counts.get(nid, [])
        n      = len(evs)
        latest = max((e.get("event_date", "") for e in evs), default=None) if evs else None
        risk   = "HIGH" if n >= 10 else "MEDIUM" if n >= 3 else "LOW" if n >= 1 else "NONE"
        result[nid] = {
            "node_id":           nid,
            "risk_level":        risk,
            "recent_acled_count":n,
            "latest_event_date": latest,
            "source":            "ACLED",
        }
    return result


def get_scrape_status() -> Dict:
    """Return scrape progress for the monitoring endpoint."""
    try:
        conn   = sqlite3.connect(f"file:{ACLED_DB_PATH}?mode=ro", uri=True, timeout=3)
        total  = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        oldest = conn.execute("SELECT MIN(event_date) FROM events").fetchone()[0] or "—"
        latest = conn.execute("SELECT MAX(event_date) FROM events").fetchone()[0] or "—"
        countries = conn.execute("SELECT COUNT(DISTINCT country) FROM events").fetchone()[0]
        conn.close()
        return {
            "total_events":  total,
            "oldest_event":  oldest,
            "latest_event":  latest,
            "countries":     countries,
            "db_path":       ACLED_DB_PATH,
        }
    except Exception:
        return {"total_events": 0, "oldest_event": "—", "latest_event": "—", "countries": 0}
