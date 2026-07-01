"""
Stage 1a — Coverage table (the historical-foundation audit).

Purpose: BEFORE any ACLED query runs, document — for every catalogued event and
every one of the 15 nodes — whether the event is a *conflict* event (ACLED can
structurally see it) AND whether ACLED was *covering that region on that date*.
This surfaces the silent holes (US/North-Sea pre-2020, Middle-East pre-2016,
non-conflict weather/accident/decision events ACLED can never see, and the
pre-2006 EIA price gap) so they never become silently-empty queries.

Sourcing policy this table enforces (per the build spec):
  - EIA          → prices (already wired, 2006-07-26 → present).
  - ACLED        → CONFLICT events only (attacks, seizures, blockades, war),
                   and only within each region's ACLED coverage window, and only
                   for the event types our scraper actually pulls.
  - Curated catalog → everything ACLED cannot see (weather, accident, strike,
                   cyber, sanction, OPEC decision, pre-coverage conflict).

Nothing here calls a network. It joins three static sources:
  event_catalog.DISRUPTION_EVENTS  ×  ACLED coverage windows  ×  EIA price bound,
then cross-checks against what actually landed in event_impact.db.
"""

from datetime import date
from typing import Dict, List, Optional

# ── EIA price availability boundary (confirmed from the live price cache) ──────
# get_price_series() returns 2006-07-26 → present. Anything earlier has no
# measured reaction and can only carry a structural prior.
EIA_PRICE_START = "2006-07-26"

# ── ACLED historical coverage-start by country ────────────────────────────────
# These are ACLED's published *historical* coverage-start years for the regions
# that contain our nodes. They are encoded here as the gate for "could ACLED
# have an event on this date?". FLAGGED to_confirm against ACLED's current
# coverage documentation before being treated as authoritative (spec invariant 6).
#
# region groupings (ACLED's own): Africa 1997 · Middle East 2016 (Yemen 2015) ·
# SE Asia 2010 · South Asia 2016 · East Asia 2018 · Caucasus/Central Asia/Russia
# 2018 · Europe 2020 · United States Jan-2020.
ACLED_COVERAGE_START: Dict[str, str] = {
    # Africa — ACLED's oldest coverage
    "Egypt":          "1997-01-01",
    "Libya":          "1997-01-01",
    "Djibouti":       "1997-01-01",
    "Eritrea":        "1997-01-01",
    "Somalia":        "1997-01-01",
    # Middle East
    "Yemen":          "2015-01-01",
    "Iran":           "2016-01-01",
    "Iraq":           "2016-01-01",
    "Saudi Arabia":   "2016-01-01",
    "United Arab Emirates": "2016-01-01",
    "Oman":           "2016-01-01",
    "Bahrain":        "2016-01-01",
    "Qatar":          "2016-01-01",
    "Kuwait":         "2016-01-01",
    "Turkey":         "2016-01-01",
    # South / Southeast Asia
    "Malaysia":       "2010-01-01",
    "Singapore":      "2010-01-01",
    "Indonesia":      "2010-01-01",
    "India":          "2016-01-01",
    # East Asia
    "South Korea":    "2018-01-01",
    # Caucasus / Central Asia / Russia
    "Russia":         "2018-01-01",
    "Ukraine":        "2018-01-01",
    "Kazakhstan":     "2018-01-01",
    # Europe + US (latest to come online)
    "United Kingdom": "2020-01-01",
    "Norway":         "2020-01-01",
    "Netherlands":    "2020-01-01",
    "Belgium":        "2020-01-01",
    "France":         "2020-01-01",
    "United States":  "2020-01-01",
}

# Our scraper (_fetch_window) only pulls these ACLED event_types. Anything that
# is a Protest / Riot / Violence-against-civilians is NOT captured even where
# ACLED covers it — a second filter beyond the conflict/region gate.
SCRAPED_ACLED_EVENT_TYPES = (
    "Explosions/Remote violence",
    "Battles",
    "Strategic developments",
)

# ── Per-event ACLED classification ────────────────────────────────────────────
# class: "conflict"     → kinetic event ACLED structurally sees (our scraped types)
#        "borderline"   → arguably Strategic-developments but unexecuted/ambiguous
#        "non_conflict" → weather / accident / strike / cyber / sanction / decision
#                         ACLED can never source this; curated catalog only.
# country is the event's *actual* location country (may differ from the node's
# home country, e.g. Kashagan→Kazakhstan, French strikes→France, Libya→Libya).
EVENT_ACLED_CLASS: Dict[str, Dict[str, str]] = {
    "abqaiq_2019":            {"class": "conflict",     "country": "Saudi Arabia",  "acled_type": "Explosions/Remote violence", "reason": "Drone & cruise-missile strike on Abqaiq processing"},
    "gulf_oman_2019":         {"class": "conflict",     "country": "Oman",          "acled_type": "Explosions/Remote violence", "reason": "Limpet-mine attacks on tankers in Gulf of Oman"},
    "houthi_red_sea_2023":    {"class": "conflict",     "country": "Yemen",         "acled_type": "Explosions/Remote violence", "reason": "Houthi missile/drone attacks on shipping"},
    "russia_invasion_2022":   {"class": "conflict",     "country": "Russia",        "acled_type": "Battles",                    "reason": "Full-scale invasion of Ukraine"},
    "libya_blockade_2020":    {"class": "conflict",     "country": "Libya",         "acled_type": "Strategic developments",     "reason": "Militia blockade of NOC export terminals"},
    "iran_hormuz_threat_2012":{"class": "borderline",   "country": "Iran",          "acled_type": "Strategic developments",     "reason": "Verbal closure threat — unexecuted; also pre-ME-coverage"},
    "suez_2021":              {"class": "non_conflict", "country": "Egypt",         "acled_type": "",                            "reason": "Ever Given grounding — accident, not violence"},
    "forties_2017":           {"class": "non_conflict", "country": "United Kingdom","acled_type": "",                            "reason": "Pipeline crack — infrastructure failure"},
    "uri_2021":               {"class": "non_conflict", "country": "United States", "acled_type": "",                            "reason": "Winter Storm Uri — natural disaster"},
    "harvey_2017":            {"class": "non_conflict", "country": "United States", "acled_type": "",                            "reason": "Hurricane Harvey — natural disaster"},
    "katrina_2005":           {"class": "non_conflict", "country": "United States", "acled_type": "",                            "reason": "Hurricane Katrina — natural disaster"},
    "hurricane_rita_2005":    {"class": "non_conflict", "country": "United States", "acled_type": "",                            "reason": "Hurricane Rita — natural disaster"},
    "colonial_2021":          {"class": "non_conflict", "country": "United States", "acled_type": "",                            "reason": "Ransomware — cyber, not in ACLED"},
    "french_strikes_2022":    {"class": "non_conflict", "country": "France",        "acled_type": "",                            "reason": "Labor strike — ACLED Protests cat, not scraped"},
    "iran_sanctions_2018":    {"class": "non_conflict", "country": "Iran",          "acled_type": "",                            "reason": "JCPOA exit — sanction/policy, no kinetic event"},
    "saudi_cuts_2023":        {"class": "non_conflict", "country": "Saudi Arabia",  "acled_type": "",                            "reason": "OPEC+ production decision"},
    "opec_cuts_2016":         {"class": "non_conflict", "country": "Saudi Arabia",  "acled_type": "",                            "reason": "OPEC Vienna production decision"},
    "bosphorus_delays_2022":  {"class": "non_conflict", "country": "Turkey",        "acled_type": "",                            "reason": "Insurance/regulatory tanker delays"},
    "kashagan_2013":          {"class": "non_conflict", "country": "Kazakhstan",    "acled_type": "",                            "reason": "H2S pipeline corrosion — equipment failure"},
    "north_sea_elgin_2012":   {"class": "non_conflict", "country": "United Kingdom","acled_type": "",                            "reason": "Elgin gas leak — safety shutdown"},
}


def _covered_on(country: str, event_date: str) -> Optional[bool]:
    """True if ACLED covered `country` on `event_date`; None if country unknown."""
    start = ACLED_COVERAGE_START.get(country)
    if start is None:
        return None
    return event_date >= start


def _impact_db_index() -> Dict[str, Dict]:
    """Map event_id → {source_tag, magnitude_class, fired, has_price} from the DB."""
    try:
        from services.event_impact_db import get_conn, init_db
        init_db()
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT event_id, source_tag, magnitude_class, fired, wti_t0 "
                "FROM event_impact"
            ).fetchall()
        return {
            r["event_id"]: {
                "source_tag":      r["source_tag"],
                "magnitude_class": r["magnitude_class"],
                "fired":           bool(r["fired"]),
                "has_price":       r["wti_t0"] is not None,
            }
            for r in rows
        }
    except Exception:
        return {}


def build_coverage_table() -> Dict:
    """
    Join catalog × ACLED coverage × EIA price bound × impact-DB state.
    Returns per-event rows plus a summary of the holes.
    """
    from services.event_catalog import DISRUPTION_EVENTS

    db_index = _impact_db_index()
    rows: List[Dict] = []

    for ev in DISRUPTION_EVENTS:
        eid        = ev["event_id"]
        ev_date    = ev["date"]
        node_id    = ev.get("node_id")
        meta       = EVENT_ACLED_CLASS.get(eid, {})
        klass      = meta.get("class", "non_conflict")
        country    = meta.get("country", "")
        acled_type = meta.get("acled_type", "")

        is_conflict   = klass == "conflict"
        region_cov    = _covered_on(country, ev_date)
        type_scraped  = acled_type in SCRAPED_ACLED_EVENT_TYPES
        has_price     = ev_date >= EIA_PRICE_START

        # ACLED can actually source this iff: conflict-class AND region covered on
        # the date AND the event type is one our scraper pulls AND it maps to a node.
        acled_sourceable = bool(
            is_conflict and region_cov and type_scraped and node_id
        )

        # Why it is / isn't ACLED-sourceable (one honest sentence)
        if acled_sourceable:
            why = "ACLED-sourceable: conflict event in covered region/date with a node match"
        elif klass == "non_conflict":
            why = f"Catalog-only: {meta.get('reason', 'non-conflict event ACLED cannot see')}"
        elif klass == "borderline":
            why = f"Catalog-only (borderline): {meta.get('reason', '')}"
        elif node_id is None:
            why = "Conflict event but no node match (outside the 15-node list)"
        elif region_cov is False:
            why = f"Conflict event but ACLED did not cover {country} until {ACLED_COVERAGE_START.get(country)}"
        elif region_cov is None:
            why = f"Conflict event but {country!r} has no recorded ACLED coverage-start"
        else:
            why = "Conflict event but event type not in scraped ACLED categories"

        db = db_index.get(eid, {})
        rows.append({
            "event_id":          eid,
            "title":             ev.get("title", eid),
            "event_date":        ev_date,
            "node_id":           node_id,
            "country":           country,
            "acled_class":       klass,
            "acled_event_type":  acled_type or None,
            "is_conflict_event": is_conflict,
            "acled_region_covered_on_date": region_cov,
            "acled_coverage_start": ACLED_COVERAGE_START.get(country),
            "acled_sourceable":  acled_sourceable,
            "primary_source":    "ACLED" if acled_sourceable else "curated_catalog",
            "has_eia_price":     has_price,
            "in_impact_db":      eid in db_index,
            "impact_source_tag": db.get("source_tag"),
            "impact_has_price":  db.get("has_price"),
            "fired":             db.get("fired"),
            "why":               why,
        })

    rows.sort(key=lambda r: r["event_date"])

    # ── Summary / holes ───────────────────────────────────────────────────────
    n = len(rows)
    conflict_rows   = [r for r in rows if r["is_conflict_event"]]
    sourceable      = [r for r in rows if r["acled_sourceable"]]
    catalog_only    = [r for r in rows if not r["acled_sourceable"]]
    no_price        = [r for r in rows if not r["has_eia_price"]]
    conflict_holes  = [
        r for r in conflict_rows
        if not r["acled_sourceable"]
    ]
    not_in_db       = [r for r in rows if not r["in_impact_db"]]

    summary = {
        "total_events":            n,
        "conflict_events":         len(conflict_rows),
        "acled_sourceable":        len(sourceable),
        "catalog_only":            len(catalog_only),
        "no_eia_price":            [r["event_id"] for r in no_price],
        "conflict_but_unsourceable": [
            {"event_id": r["event_id"], "reason": r["why"]} for r in conflict_holes
        ],
        "not_in_impact_db":        [r["event_id"] for r in not_in_db],
        "eia_price_start":         EIA_PRICE_START,
        "coverage_note": (
            "ACLED coverage-start dates are ACLED's published regional windows "
            "and are flagged to_confirm against the current ACLED coverage doc."
        ),
    }

    return {"rows": rows, "summary": summary}


def node_coverage_matrix() -> List[Dict]:
    """
    Per-node sourcing summary: does ACLED's region/window give this node any
    sourceable conflict history, or is it curated-catalog / structural-prior only?
    """
    from services.oil_nodes import NODE_DEFINITIONS
    from services.acled_fetcher import TARGET_COUNTRIES  # noqa: F401 (intent doc)

    table = build_coverage_table()["rows"]
    by_node: Dict[str, List[Dict]] = {}
    for r in table:
        if r["node_id"]:
            by_node.setdefault(r["node_id"], []).append(r)

    # node → representative ACLED country (for coverage-window display)
    NODE_COUNTRY = {
        "hormuz": "Iran", "malacca": "Malaysia", "suez": "Egypt",
        "bab_el_mandeb": "Yemen", "bosphorus": "Turkey",
        "ghawar_abqaiq": "Saudi Arabia", "permian": "United States",
        "russia_siberia": "Russia", "north_sea": "United Kingdom",
        "basra": "Iraq", "usgc_padd3": "United States", "jamnagar": "India",
        "rotterdam_ara": "Netherlands", "singapore_jurong": "Singapore",
        "ulsan": "South Korea",
    }

    out: List[Dict] = []
    for node in NODE_DEFINITIONS:
        nid     = node["id"]
        evs     = by_node.get(nid, [])
        country = NODE_COUNTRY.get(nid, "")
        sourceable = [e for e in evs if e["acled_sourceable"]]
        out.append({
            "node_id":             nid,
            "name":                node["name"],
            "type":                node["type"],
            "acled_country":       country,
            "acled_coverage_start": ACLED_COVERAGE_START.get(country),
            "catalog_events":      len(evs),
            "acled_sourceable_events": len(sourceable),
            "sourcing": (
                "ACLED + catalog" if sourceable
                else "catalog / structural-prior only"
            ),
        })
    return out
