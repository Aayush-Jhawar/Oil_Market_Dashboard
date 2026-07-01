"""
Event-impact table: one qualifying row per supply disruption.

Gate (Step 0): event must have a node match AND either
  - severity >= outage, OR
  - |primary_t0_move| >= threshold (2% crude, $1.50 arb/crack)
This prevents wind/RIN/macro noise from producing disruption rows.

Schema (Step 1): event_date (not publish date), baseline = last tradable
close BEFORE event, T+0 = first tradable close ON/AFTER event date.
T+20 stored but EXCLUDED from magnitude_class / fired computation.

Backfill (Step 2): all 20 hand-curated events, point-in-time EIA prices.
  Wrong-direction events (Ever Given) → fired=False, LOW, confound_note.
  Anticipated events (OPEC) → anticipated=1 for separate base-rate bucket.

Negative class (Step 3):
  (a) Null events — catalogued events that don't clear the gate/threshold
      → inserted with magnitude_class='none', fired=False.
  (b) Unexplained moves — EIA moves >= threshold with no coded event ±2 days
      → stored in unexplained_moves table as FPR denominator.

Maintenance job (Step 4): daily scheduled pass that writes back T+1/T+5/T+20
for auto-appended live events once dates are old enough to have outcomes.
Recomputes fired/magnitude_class on updated rows.
"""

import bisect
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "event_impact.db"

# ── Basin assignment ──────────────────────────────────────────────────────────
# Atlantic: EIA has HO/WTI data → crack/arb cells measured
# MiddleEast_Dubai, Asia, Russia_Urals: products modeled (no live Dubai/gasoil)

BASIN_MAP: Dict[str, str] = {
    "hormuz":           "MiddleEast_Dubai",
    "bab_el_mandeb":    "MiddleEast_Dubai",
    "ghawar_abqaiq":    "MiddleEast_Dubai",
    "basra":            "MiddleEast_Dubai",
    "malacca":          "Asia",
    "jamnagar":         "Asia",
    "singapore_jurong": "Asia",
    "ulsan":            "Asia",
    "suez":             "Atlantic",
    "north_sea":        "Atlantic",
    "rotterdam_ara":    "Atlantic",
    "usgc_padd3":       "Atlantic",
    "permian":          "Atlantic",
    "russia_siberia":   "Russia_Urals",
    "bosphorus":        "Russia_Urals",
}

# These basins lack live Dubai/gasoil price feeds; crack/arb cells are modeled
MODELED_PRODUCT_BASINS = frozenset({"Asia", "Russia_Urals", "MiddleEast_Dubai"})

# Events known to be anticipated (scheduled/signaled before the market open)
ANTICIPATED_EVENT_IDS = frozenset({
    "opec_cuts_2016",
    "saudi_cuts_2023",
    "iran_sanctions_2018",
    "bosphorus_delays_2022",
})

# Per-event confound notes (macro/structural confounders that taint direction)
CONFOUND_NOTES_MAP: Dict[str, str] = {
    "suez_2021": (
        "COVID macro recovery rally (Mar-2021 equity surge) coincided — "
        "crude reaction muted vs structural prior"
    ),
    "russia_invasion_2022": (
        "Simultaneous inflation shock and equity rout confound the 1-2Mb/d volume signal"
    ),
    "hurricane_rita_2005": (
        "Market still processing Katrina; incremental price signal muted"
    ),
    "libya_blockade_2020": (
        "No node match in 15-node list (Libya not catalogued); "
        "structural prior applied — Brent-led"
    ),
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS event_impact (
            event_id              TEXT PRIMARY KEY,
            event_date            TEXT NOT NULL,
            detected_at           TEXT,
            headline              TEXT NOT NULL,
            url                   TEXT,
            source_domain         TEXT,
            n_sources             INTEGER DEFAULT 1,
            source_scale          TEXT    DEFAULT 'local',
            node_id               TEXT,
            basin                 TEXT,
            region_geo            TEXT,
            channel               TEXT,
            severity              TEXT,
            restored              INTEGER DEFAULT 0,
            anticipated           INTEGER DEFAULT 0,
            most_exposed_contract TEXT,
            baseline_ref          TEXT,
            wti_t0   REAL, wti_t1   REAL, wti_t5   REAL, wti_t20   REAL,
            brent_t0 REAL, brent_t1 REAL, brent_t5 REAL, brent_t20 REAL,
            arb_t0   REAL, arb_t1   REAL, arb_t5   REAL, arb_t20   REAL,
            distillate_crack_t0 REAL, distillate_crack_t1 REAL,
            distillate_crack_t5 REAL, distillate_crack_t20 REAL,
            magnitude_class       TEXT    DEFAULT 'none',
            fired                 INTEGER DEFAULT 0,
            direction_agreement   INTEGER DEFAULT 0,
            source_tag            TEXT    NOT NULL DEFAULT 'prior',
            confidence            TEXT    DEFAULT 'STRUCTURAL',
            confound_note         TEXT,
            created_at            TEXT,
            updated_at            TEXT
        )
        """)
        # Unexplained moves: large EIA moves with no coded disruption event nearby
        conn.execute("""
        CREATE TABLE IF NOT EXISTS unexplained_moves (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            move_date  TEXT NOT NULL UNIQUE,
            basin      TEXT,
            wti_pct    REAL,
            brent_pct  REAL,
            arb_usd    REAL,
            crack_usd  REAL,
            notes      TEXT,
            created_at TEXT
        )
        """)
        conn.commit()


# ── Gate ──────────────────────────────────────────────────────────────────────

def _surge_threshold(contract: str) -> float:
    """Surge/crash threshold: 2% for crude flat, $1.50 for arb/crack spreads."""
    return 1.5 if ("arb" in contract or "crack" in contract) else 2.0


def _primary_move(horizon: Optional[Dict], contract: str) -> Optional[float]:
    """Extract the contract-relevant move from a horizon returns dict."""
    if not horizon:
        return None
    if "wti_flat" in contract:
        return horizon.get("wti_pct")
    if "brent_flat" in contract:
        return horizon.get("brent_pct")
    if "arb" in contract:
        return horizon.get("arb_usd")
    if "crack" in contract or "distillate" in contract or "gasoline" in contract:
        return horizon.get("crack_usd")
    return horizon.get("brent_pct") or horizon.get("wti_pct")


def passes_gate(
    node_id: Optional[str],
    severity: str,
    t0: Optional[Dict] = None,
    most_exposed_contract: str = "brent_flat",
) -> bool:
    """
    True if the event qualifies for a disruption row.
    Wind/RIN/solar headlines: node_id is None → never qualify.
    """
    if not node_id:
        return False
    if severity in ("outage", "sustained"):
        return True
    if t0:
        move = _primary_move(t0, most_exposed_contract)
        if move is not None and abs(move) >= _surge_threshold(most_exposed_contract):
            return True
    return False


# ── Magnitude / fired computation ─────────────────────────────────────────────

def _classify_magnitude_and_fired(
    t0: Optional[Dict],
    t1: Optional[Dict],
    t5: Optional[Dict],
    most_exposed: str,
    structural_prior: Optional[Dict],
) -> Tuple[str, bool, bool]:
    """
    Returns (magnitude_class, direction_agreement, fired).
    T+20 excluded per spec (macro drift confounds).
    magnitude_class: 'surge' | 'crash' | 'none'
    direction_agreement: realized sign == structural prior sign
    fired: magnitude_class != 'none' AND direction_agreement
    """
    threshold = _surge_threshold(most_exposed)
    moves = [
        _primary_move(h, most_exposed)
        for h in (t0, t1, t5)
        if h
    ]
    moves = [m for m in moves if m is not None]

    if not moves:
        return "none", False, False

    peak = max(moves, key=abs)
    if abs(peak) < threshold:
        return "none", False, False

    mag_class = "surge" if peak > 0 else "crash"

    dir_agree = False
    if structural_prior:
        prior_val = _primary_move(structural_prior, most_exposed)
        if prior_val is not None:
            dir_agree = (peak * prior_val) > 0

    fired = (mag_class != "none") and dir_agree
    return mag_class, dir_agree, fired


# ── DB write helpers ──────────────────────────────────────────────────────────

def _h(d: Optional[Dict], key: str) -> Optional[float]:
    """Safe float getter from a returns dict."""
    if not d:
        return None
    v = d.get(key)
    return round(float(v), 4) if v is not None else None


def upsert_event(row: Dict) -> None:
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO event_impact (
            event_id, event_date, detected_at, headline, url, source_domain,
            n_sources, source_scale, node_id, basin, region_geo, channel,
            severity, restored, anticipated, most_exposed_contract, baseline_ref,
            wti_t0,   wti_t1,   wti_t5,   wti_t20,
            brent_t0, brent_t1, brent_t5, brent_t20,
            arb_t0,   arb_t1,   arb_t5,   arb_t20,
            distillate_crack_t0, distillate_crack_t1,
            distillate_crack_t5, distillate_crack_t20,
            magnitude_class, fired, direction_agreement,
            source_tag, confidence, confound_note,
            created_at, updated_at
        ) VALUES (
            :event_id, :event_date, :detected_at, :headline, :url, :source_domain,
            :n_sources, :source_scale, :node_id, :basin, :region_geo, :channel,
            :severity, :restored, :anticipated, :most_exposed_contract, :baseline_ref,
            :wti_t0,   :wti_t1,   :wti_t5,   :wti_t20,
            :brent_t0, :brent_t1, :brent_t5, :brent_t20,
            :arb_t0,   :arb_t1,   :arb_t5,   :arb_t20,
            :distillate_crack_t0, :distillate_crack_t1,
            :distillate_crack_t5, :distillate_crack_t20,
            :magnitude_class, :fired, :direction_agreement,
            :source_tag, :confidence, :confound_note,
            :created_at, :updated_at
        )""", row)
        conn.commit()


# ── Backfill from hand-curated catalog ───────────────────────────────────────

def backfill_catalog(force: bool = False) -> Dict:
    """
    Step 2: Compute T+0..T+20 for all 20 DISRUPTION_EVENTS using EIA price
    series, apply the gate, and write rows.

    - All events are inserted (gate failures → magnitude_class='none',
      fired=False → these are the null-event negative class).
    - Event-date alignment: T-1 = last close BEFORE event, T+0 = first
      close ON/AFTER event date (captures weekend gaps like Abqaiq).
    - T+20 stored but excluded from magnitude_class/fired.
    - Wrong-direction moves (Ever Given) → fired=False, LOW, confound_note set.
    """
    init_db()

    from services.event_catalog import DISRUPTION_EVENTS
    from services.eia_event_engine import (
        get_price_series,
        compute_event_returns,
        compute_structural_prior,
    )
    from services.oil_nodes import NODE_BY_ID
    from services.disruption_classifier import _most_exposed_contract

    prices = get_price_series()
    sorted_dates = sorted(prices.keys())
    now_iso = datetime.now().isoformat()

    counts = {
        "inserted": 0,
        "null_events": 0,   # gate failures → negative class (a)
        "no_price": 0,
        "errors": 0,
    }

    existing_ids: set = set()
    if not force:
        with get_conn() as conn:
            existing_ids = {r[0] for r in conn.execute(
                "SELECT event_id FROM event_impact"
            ).fetchall()}

    for ev in DISRUPTION_EVENTS:
        eid = ev["event_id"]
        if not force and eid in existing_ids:
            continue

        try:
            node_id  = ev.get("node_id")
            severity = ev.get("severity", "scare")
            channel  = ev.get("channel", "production")
            # All catalog events are dated at the disruption ONSET, not a reopening.
            # The catalog's "restored" flag means "eventually resolved" (metadata),
            # NOT that the headline is about a restoration event. Using restored=True
            # would flip the structural prior to bearish and produce spurious
            # direction-agreement for events like Ever Given (crude fell on macro,
            # not because a closure ended). Always treat as disruption onset here.
            restored = False
            node     = NODE_BY_ID.get(node_id, {}) if node_id else {}
            most_exp = (
                _most_exposed_contract(node, channel, False)
                if node else "brent_flat"
            )
            basin       = BASIN_MAP.get(node_id, "Atlantic") if node_id else None
            anticipated = 1 if eid in ANTICIPATED_EVENT_IDS else 0

            prior = (
                compute_structural_prior(
                    node, severity=severity, restored=False, channel=channel
                )
                if node else None
            )

            # Compute T+0..T+20 returns using point-in-time EIA data
            ret = compute_event_returns(ev, prices, sorted_dates) if prices else None
            t0  = ret.get("t0",  {}) if ret else {}
            t1  = ret.get("t1",  {}) if ret else {}
            t5  = ret.get("t5",  {}) if ret else {}
            t20 = ret.get("t20", {}) if ret else {}

            has_price  = bool(ret and t0)
            source_tag = "history" if has_price else "prior"

            if not has_price:
                counts["no_price"] += 1

            qualifies = passes_gate(node_id, severity, t0 or None, most_exp)
            confound  = CONFOUND_NOTES_MAP.get(eid)

            if not qualifies:
                # Insert as null-event (negative class a): magnitude_class='none'
                counts["null_events"] += 1
                upsert_event({
                    "event_id": eid, "event_date": ev["date"],
                    "detected_at": now_iso,
                    "headline": ev.get("title", eid), "url": None,
                    "source_domain": "disruption_catalog",
                    "n_sources": ev.get("n_sources", 1),
                    "source_scale": ev.get("source_scale", "national"),
                    "node_id": node_id, "basin": basin,
                    "region_geo": ev.get("location", ev.get("region", "")),
                    "channel": channel, "severity": severity,
                    "restored": 1 if restored else 0,
                    "anticipated": anticipated,
                    "most_exposed_contract": most_exp,
                    "baseline_ref": ret.get("t_minus1") if ret else None,
                    "wti_t0":   _h(t0, "wti_pct"),   "wti_t1":   _h(t1, "wti_pct"),
                    "wti_t5":   _h(t5, "wti_pct"),   "wti_t20":  _h(t20, "wti_pct"),
                    "brent_t0": _h(t0, "brent_pct"), "brent_t1": _h(t1, "brent_pct"),
                    "brent_t5": _h(t5, "brent_pct"), "brent_t20":_h(t20, "brent_pct"),
                    "arb_t0":   _h(t0, "arb_usd"),   "arb_t1":   _h(t1, "arb_usd"),
                    "arb_t5":   _h(t5, "arb_usd"),   "arb_t20":  _h(t20, "arb_usd"),
                    "distillate_crack_t0": _h(t0, "crack_usd"),
                    "distillate_crack_t1": _h(t1, "crack_usd"),
                    "distillate_crack_t5": _h(t5, "crack_usd"),
                    "distillate_crack_t20":_h(t20, "crack_usd"),
                    "magnitude_class": "none", "fired": 0, "direction_agreement": 0,
                    "source_tag": source_tag, "confidence": "LOW",
                    "confound_note": confound,
                    "created_at": now_iso, "updated_at": now_iso,
                })
                continue

            # Qualifying event: compute magnitude and fired
            mag, dir_agree, fired = _classify_magnitude_and_fired(
                t0 or None, t1 or None, t5 or None, most_exp, prior
            )

            # Confidence from sign agreement + data availability
            if not has_price:
                confidence = "STRUCTURAL"
            elif fired:
                confidence = "HIGH"
            elif mag != "none":
                confidence = "MEDIUM"
            else:
                confidence = "LOW"

            # Ever Given / COVID-era: wrong-direction move → LOW, fired=False, note set
            if not dir_agree and has_price and mag != "none":
                fired      = False
                confidence = "LOW"
                if not confound:
                    confound = "Realized direction opposite to structural prior — not counted in hit rate"

            upsert_event({
                "event_id": eid, "event_date": ev["date"],
                "detected_at": now_iso,
                "headline": ev.get("title", eid), "url": None,
                "source_domain": "disruption_catalog",
                "n_sources": ev.get("n_sources", 1),
                "source_scale": ev.get("source_scale", "national"),
                "node_id": node_id, "basin": basin,
                "region_geo": ev.get("location", ev.get("region", "")),
                "channel": channel, "severity": severity,
                "restored": 1 if restored else 0,
                "anticipated": anticipated,
                "most_exposed_contract": most_exp,
                "baseline_ref": ret.get("t_minus1") if ret else None,
                "wti_t0":   _h(t0, "wti_pct"),   "wti_t1":   _h(t1, "wti_pct"),
                "wti_t5":   _h(t5, "wti_pct"),   "wti_t20":  _h(t20, "wti_pct"),
                "brent_t0": _h(t0, "brent_pct"), "brent_t1": _h(t1, "brent_pct"),
                "brent_t5": _h(t5, "brent_pct"), "brent_t20":_h(t20, "brent_pct"),
                "arb_t0":   _h(t0, "arb_usd"),   "arb_t1":   _h(t1, "arb_usd"),
                "arb_t5":   _h(t5, "arb_usd"),   "arb_t20":  _h(t20, "arb_usd"),
                "distillate_crack_t0": _h(t0, "crack_usd"),
                "distillate_crack_t1": _h(t1, "crack_usd"),
                "distillate_crack_t5": _h(t5, "crack_usd"),
                "distillate_crack_t20":_h(t20, "crack_usd"),
                "magnitude_class": mag,
                "fired": 1 if fired else 0,
                "direction_agreement": 1 if dir_agree else 0,
                "source_tag": source_tag,
                "confidence": confidence,
                "confound_note": confound,
                "created_at": now_iso, "updated_at": now_iso,
            })
            counts["inserted"] += 1

        except Exception as exc:
            logger.error("Backfill error for %s: %s", eid, exc)
            counts["errors"] += 1

    logger.info("Catalog backfill complete: %s", counts)
    return counts


# ── Auto-append from live classifier output ───────────────────────────────────

def auto_append_from_classifier(
    event_id: str,
    headline: str,
    classification: Dict,
    url: str = "",
    source_domain: str = "",
    n_sources: int = 1,
    source_scale: str = "national",
    anticipated: bool = False,
) -> bool:
    """
    Write a qualifying live event with null T+0..T+20 columns.
    The daily maintenance job fills the T cols as market dates mature.

    Returns True if inserted, False if gated out or already present.
    """
    init_db()
    node_id   = classification.get("node_id")
    severity  = classification.get("severity", "scare")
    channel   = classification.get("channel", "production")
    restored  = bool(classification.get("restored", False))
    most_exp  = classification.get("most_exposed_contract", "brent_flat")
    confidence = classification.get("confidence", "LOW")
    basin     = BASIN_MAP.get(node_id, "Atlantic") if node_id else None

    if not passes_gate(node_id, severity):
        return False

    with get_conn() as conn:
        if conn.execute(
            "SELECT 1 FROM event_impact WHERE event_id = ?", (event_id,)
        ).fetchone():
            return False

    now_iso = datetime.now().isoformat()
    today   = datetime.now().strftime("%Y-%m-%d")

    upsert_event({
        "event_id": event_id, "event_date": today,
        "detected_at": now_iso,
        "headline": headline[:512], "url": url,
        "source_domain": source_domain,
        "n_sources": n_sources, "source_scale": source_scale,
        "node_id": node_id, "basin": basin,
        "region_geo": classification.get("region", ""),
        "channel": channel, "severity": severity,
        "restored": 1 if restored else 0,
        "anticipated": 1 if anticipated else 0,
        "most_exposed_contract": most_exp,
        "baseline_ref": None,
        # T cols start null; maintenance job fills them
        "wti_t0": None, "wti_t1": None, "wti_t5": None, "wti_t20": None,
        "brent_t0": None, "brent_t1": None, "brent_t5": None, "brent_t20": None,
        "arb_t0": None, "arb_t1": None, "arb_t5": None, "arb_t20": None,
        "distillate_crack_t0": None, "distillate_crack_t1": None,
        "distillate_crack_t5": None, "distillate_crack_t20": None,
        "magnitude_class": "none", "fired": 0, "direction_agreement": 0,
        "source_tag": "prior",
        "confidence": confidence,
        "confound_note": None,
        "created_at": now_iso, "updated_at": now_iso,
    })
    logger.info("Auto-appended event %s (node=%s sev=%s)", event_id, node_id, severity)
    return True


# ── Negative class: unexplained large moves (Step 3b) ────────────────────────

def load_unexplained_moves() -> int:
    """
    Scan EIA daily price series for moves >= threshold that have NO coded
    disruption event within ±2 trading days.
    These are the false-positive denominator for the base-rate computation.
    Returns count of new rows inserted.
    """
    init_db()
    from services.eia_event_engine import get_price_series

    prices = get_price_series()
    if not prices:
        return 0

    sorted_dates = sorted(prices.keys())

    with get_conn() as conn:
        coded_dates: set = {
            r[0]
            for r in conn.execute(
                "SELECT event_date FROM event_impact WHERE node_id IS NOT NULL"
            ).fetchall()
        }

    def _min_dist(d: str) -> int:
        try:
            di = sorted_dates.index(d)
        except ValueError:
            return 999
        min_d = 999
        for cd in coded_dates:
            try:
                ci = sorted_dates.index(cd)
                dist = abs(di - ci)
                if dist < min_d:
                    min_d = dist
            except ValueError:
                pass
        return min_d

    inserted = 0
    now_iso  = datetime.now().isoformat()

    for i in range(1, len(sorted_dates)):
        date = sorted_dates[i]
        prev = sorted_dates[i - 1]
        p    = prices.get(date, {})
        pb   = prices.get(prev, {})

        wti_pct = brent_pct = arb_usd = crack_usd = None

        if p.get("wti") and pb.get("wti") and pb["wti"]:
            wti_pct   = (p["wti"]   - pb["wti"])   / pb["wti"]   * 100
        if p.get("brent") and pb.get("brent") and pb["brent"]:
            brent_pct = (p["brent"] - pb["brent"]) / pb["brent"] * 100
        if p.get("brent") and p.get("wti") and pb.get("brent") and pb.get("wti"):
            arb_usd   = (p["brent"] - p["wti"]) - (pb["brent"] - pb["wti"])
        if p.get("ho") and p.get("wti") and pb.get("ho") and pb.get("wti"):
            crack_usd = (p["ho"] * 42 - p["wti"]) - (pb["ho"] * 42 - pb["wti"])

        is_big = (
            (wti_pct   is not None and abs(wti_pct)   >= 2.0) or
            (brent_pct is not None and abs(brent_pct) >= 2.0) or
            (arb_usd   is not None and abs(arb_usd)   >= 1.5) or
            (crack_usd is not None and abs(crack_usd) >= 1.5)
        )
        if not is_big:
            continue
        if _min_dist(date) <= 2:
            continue   # within ±2 days of a coded event → don't double-count

        try:
            with get_conn() as conn:
                conn.execute("""
                INSERT OR IGNORE INTO unexplained_moves
                    (move_date, basin, wti_pct, brent_pct, arb_usd,
                     crack_usd, notes, created_at)
                VALUES (?, NULL, ?, ?, ?, ?, 'no_coded_event', ?)
                """, (date, wti_pct, brent_pct, arb_usd, crack_usd, now_iso))
                conn.commit()
            inserted += 1
        except Exception as exc:
            logger.debug("unexplained_move insert %s: %s", date, exc)

    logger.info("Unexplained moves: %d new rows", inserted)
    return inserted


# ── Maintenance job: fill maturing T horizons (Step 4) ───────────────────────

def run_maintenance() -> Dict:
    """
    Daily job that:
    1. Finds rows where T+1/T+5/T+20 are null and the event_date is old enough.
    2. Computes the missing returns from the EIA price series.
    3. Writes them back and recomputes fired/magnitude_class.

    T+1 available after 1 trading day, T+5 after 5, T+20 after 20.
    T+20 is stored for reference but excluded from fired computation.
    """
    init_db()
    from services.eia_event_engine import get_price_series, compute_structural_prior
    from services.oil_nodes import NODE_BY_ID

    prices = get_price_series()
    if not prices:
        return {"updated": 0, "reason": "no_price_data"}

    sorted_dates = sorted(prices.keys())
    today_idx    = len(sorted_dates) - 1

    def _nth(anchor_idx: int, n: int) -> Optional[str]:
        i = anchor_idx + n
        return sorted_dates[i] if 0 <= i < len(sorted_dates) else None

    def _rets(t0_date: str, n: int,
               bw: float, bb: float,
               ba: float, bc: Optional[float]) -> Dict:
        """Returns at horizon n from t0_date."""
        td = _nth(sorted_dates.index(t0_date), n)
        if not td:
            return {}
        p   = prices.get(td, {})
        out: Dict = {}
        if p.get("wti") and bw:
            out["wti_pct"]   = round((p["wti"]   - bw) / bw   * 100, 2)
        if p.get("brent") and bb:
            out["brent_pct"] = round((p["brent"] - bb) / bb   * 100, 2)
        if p.get("brent") and p.get("wti"):
            out["arb_usd"]   = round((p["brent"] - p["wti"]) - ba, 2)
        if p.get("ho") and p.get("wti") and bc is not None:
            out["crack_usd"] = round((p["ho"] * 42 - p["wti"]) - bc, 2)
        return out

    updated = 0

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT event_id, event_date, node_id, channel, severity,
                   restored, most_exposed_contract, source_tag,
                   wti_t0, wti_t5, wti_t20
            FROM event_impact
            WHERE source_tag IN ('prior', 'history')
              AND node_id IS NOT NULL
              AND (wti_t0 IS NULL OR wti_t5 IS NULL OR wti_t20 IS NULL)
        """).fetchall()

    for row in rows:
        eid        = row["event_id"]
        event_date = row["event_date"]

        idx = bisect.bisect_left(sorted_dates, event_date)
        if idx >= len(sorted_dates):
            continue
        t0_date  = sorted_dates[idx]
        if idx == 0:
            continue
        tm1_date = sorted_dates[idx - 1]

        baseline   = prices.get(tm1_date, {})
        base_wti   = baseline.get("wti")
        base_brent = baseline.get("brent")
        if not base_wti or not base_brent:
            continue

        base_arb   = base_brent - base_wti
        base_crack = (
            baseline["ho"] * 42 - base_wti
            if baseline.get("ho") else None
        )

        t0_idx = sorted_dates.index(t0_date)

        t0  = _rets(t0_date, 0, base_wti, base_brent, base_arb, base_crack) if today_idx >= t0_idx     else None
        t1  = _rets(t0_date, 1, base_wti, base_brent, base_arb, base_crack) if today_idx >= t0_idx + 1 else None
        t5  = _rets(t0_date, 5, base_wti, base_brent, base_arb, base_crack) if today_idx >= t0_idx + 5 else None
        t20 = _rets(t0_date,20, base_wti, base_brent, base_arb, base_crack) if today_idx >= t0_idx +20 else None

        most_exp   = row["most_exposed_contract"] or "brent_flat"
        node       = NODE_BY_ID.get(row["node_id"], {})
        prior      = compute_structural_prior(
            node,
            severity  = row["severity"]  or "outage",
            restored  = bool(row["restored"]),
            channel   = row["channel"]   or "production",
        ) if node else None

        mag, dir_agree, fired = _classify_magnitude_and_fired(
            t0 or None, t1 or None, t5 or None, most_exp, prior
        )
        src_tag = "history" if t0 else row["source_tag"]

        try:
            with get_conn() as conn:
                conn.execute("""
                UPDATE event_impact SET
                    baseline_ref = ?,
                    wti_t0   = ?,   wti_t1   = ?,   wti_t5   = ?,   wti_t20   = ?,
                    brent_t0 = ?,   brent_t1 = ?,   brent_t5 = ?,   brent_t20 = ?,
                    arb_t0   = ?,   arb_t1   = ?,   arb_t5   = ?,   arb_t20   = ?,
                    distillate_crack_t0 = ?, distillate_crack_t1 = ?,
                    distillate_crack_t5 = ?, distillate_crack_t20 = ?,
                    magnitude_class   = ?,
                    fired             = ?,
                    direction_agreement = ?,
                    source_tag        = ?,
                    updated_at        = ?
                WHERE event_id = ?
                """, (
                    tm1_date,
                    _h(t0, "wti_pct"),   _h(t1, "wti_pct"),
                    _h(t5, "wti_pct"),   _h(t20, "wti_pct"),
                    _h(t0, "brent_pct"), _h(t1, "brent_pct"),
                    _h(t5, "brent_pct"), _h(t20, "brent_pct"),
                    _h(t0, "arb_usd"),   _h(t1, "arb_usd"),
                    _h(t5, "arb_usd"),   _h(t20, "arb_usd"),
                    _h(t0, "crack_usd"), _h(t1, "crack_usd"),
                    _h(t5, "crack_usd"), _h(t20, "crack_usd"),
                    mag,
                    1 if fired else 0,
                    1 if dir_agree else 0,
                    src_tag,
                    datetime.now().isoformat(),
                    eid,
                ))
                conn.commit()
            updated += 1
        except Exception as exc:
            logger.error("Maintenance update error %s: %s", eid, exc)

    logger.info("Maintenance: updated %d rows", updated)
    return {"updated": updated}


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_all_events(
    node_id: Optional[str] = None,
    basin: Optional[str] = None,
    only_fired: bool = False,
    include_null_events: bool = True,
    limit: int = 200,
) -> List[Dict]:
    """Return event_impact rows as dicts, newest first."""
    init_db()
    clauses = []
    params: List = []

    if node_id:
        clauses.append("node_id = ?")
        params.append(node_id)
    if basin:
        clauses.append("basin = ?")
        params.append(basin)
    if only_fired:
        clauses.append("fired = 1")
    if not include_null_events:
        clauses.append("magnitude_class != 'none'")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql   = f"SELECT * FROM event_impact {where} ORDER BY event_date DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_db_stats() -> Dict:
    """Summary statistics for the event_impact DB."""
    init_db()
    with get_conn() as conn:
        total       = conn.execute("SELECT COUNT(*) FROM event_impact").fetchone()[0]
        history_n   = conn.execute(
            "SELECT COUNT(*) FROM event_impact WHERE source_tag='history'"
        ).fetchone()[0]
        fired_n     = conn.execute(
            "SELECT COUNT(*) FROM event_impact WHERE fired=1"
        ).fetchone()[0]
        null_n      = conn.execute(
            "SELECT COUNT(*) FROM event_impact WHERE magnitude_class='none'"
        ).fetchone()[0]
        pending_n   = conn.execute(
            "SELECT COUNT(*) FROM event_impact WHERE wti_t0 IS NULL AND node_id IS NOT NULL"
        ).fetchone()[0]
        unexplained = conn.execute(
            "SELECT COUNT(*) FROM unexplained_moves"
        ).fetchone()[0]
    return {
        "total_events":      total,
        "history_rows":      history_n,
        "fired":             fired_n,
        "null_events":       null_n,
        "pending_outcomes":  pending_n,
        "unexplained_moves": unexplained,
    }
