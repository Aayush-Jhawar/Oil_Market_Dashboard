"""
GDELT DOC 2.0 API — persistent backwards scraper with SQLite storage.

Scraping strategy
-----------------
Each scheduler cycle (every ~2 min) does two things:

  Forward pass  — fetch latest_fetched_end → now for all queries,
                  so the live feed stays within 2 minutes of real-time.

  Backward pass — extend one 24-hour window further into the past for
                  all queries, building history one day per cycle.
                  Stops at MAX_BACKFILL_DAYS (90 d).

Rate limiting
-------------
GDELT DOC 2.0 is a public API with ~100 req/min per IP.
We sleep SCRAPE_RATE_DELAY (1.5 s) between every request, so a full
cycle (5 queries forward + 5 queries backward) takes ~15 s — well
under the limit even at peak throughput.

Persistence
-----------
Articles are stored in a local SQLite DB at
  %LOCALAPPDATA%/Dashboard_v3/DB/gdelt_articles.db
(outside OneDrive to avoid WAL byte-range locking; same reasoning as
the bars-15min DB).

Public surface
--------------
  scrape_one_cycle()    — called by the APScheduler job in main.py
  get_stored_feed()     — called by /api/disruption/news
  get_scrape_status()   — monitoring endpoint helper
  get_cached_feed()     — legacy shim; prefers DB, falls back to live API

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
  mode=artlist, format=json — no API key required
"""

import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

import requests

logger = logging.getLogger(__name__)

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_TIMEOUT = (3.0, 15.0)
SCRAPE_RATE_DELAY = 1.5   # seconds between every API request
MAX_BACKFILL_DAYS = 90    # stop backwards scrape here

_local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
GDELT_DB_PATH = os.environ.get(
    "GDELT_DB_PATH",
    os.path.join(_local, "Dashboard_v3", "DB", "gdelt_articles.db"),
)

OIL_QUERIES = [
    "oil crude petroleum supply disruption opec",
    "tanker shipping strait chokepoint blockade",
    "refinery outage pipeline attack hurricane",
    "saudi arabia russia iran iraq oil production",
    "energy security crude price shock sanctions",
]

TRUSTED_DOMAINS = {
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "ap.org",
    "oilprice.com", "rigzone.com", "platts.com", "argusmedia.com",
    "energyintel.com", "worldoil.com", "offshore-mag.com",
    "eia.gov", "opec.org", "iea.org", "cnn.com", "bbc.com",
    "aljazeera.com", "thenationalnews.com", "arabnews.com",
    "lloydslist.com", "tradewindsnews.com",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_seendate(raw: str) -> str:
    """Convert GDELT seendate '20240115T120000Z' → ISO '2024-01-15T12:00:00+00:00'."""
    try:
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return raw


def _is_english(item: Dict) -> bool:
    return item.get("language", "").lower() in ("english", "en", "")


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _build_article(raw: Dict) -> Optional[Dict]:
    url   = raw.get("url", "")
    title = raw.get("title", "").strip()
    if not url or not title or not _is_english(raw):
        return None
    return {
        "url":           url,
        "title":         title,
        "domain":        _domain(url),
        "seendate":      _parse_seendate(raw.get("seendate", "")),
        "language":      raw.get("language", "English"),
        "sourcecountry": raw.get("sourcecountry", ""),
        "source":        "GDELT",
    }


# ── SQLite persistence ────────────────────────────────────────────────────────

def ensure_gdelt_db() -> None:
    os.makedirs(os.path.dirname(GDELT_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(GDELT_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            url           TEXT PRIMARY KEY,
            title         TEXT,
            domain        TEXT,
            seendate      TEXT,
            language      TEXT,
            sourcecountry TEXT,
            source        TEXT DEFAULT 'GDELT',
            fetched_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_art_seendate ON articles(seendate);
        CREATE TABLE IF NOT EXISTS scrape_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    # Migration: add classified_at if this is an existing DB without it
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN classified_at TEXT")
        conn.commit()
        logger.debug("GDELT DB: added classified_at column")
    except Exception:
        pass  # column already exists
    conn.close()


def get_unclassified_articles(limit: int = 300) -> List[Dict]:
    """
    Return up to `limit` articles that haven't been classified yet
    (classified_at IS NULL), oldest-first so historical backlog drains first.
    """
    try:
        ensure_gdelt_db()
        conn = sqlite3.connect(f"file:{GDELT_DB_PATH}?mode=ro", uri=True, timeout=5)
        rows = conn.execute(
            "SELECT url, title, domain, seendate, language, sourcecountry "
            "FROM articles "
            "WHERE classified_at IS NULL "
            "ORDER BY seendate ASC "
            "LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {
                "url":           r[0],
                "title":         r[1],
                "domain":        r[2],
                "seendate":      r[3],
                "language":      r[4] or "English",
                "sourcecountry": r[5] or "",
                "source":        "GDELT",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("get_unclassified_articles failed: %s", e)
        return []


def mark_classified(urls: List[str]) -> None:
    """Mark articles as classified (set classified_at = now)."""
    if not urls:
        return
    try:
        conn = sqlite3.connect(GDELT_DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        ts = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            "UPDATE articles SET classified_at=? WHERE url=?",
            [(ts, u) for u in urls],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("mark_classified failed: %s", e)


def _get_state(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM scrape_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def _set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO scrape_state (key, value) VALUES (?,?)", (key, value)
    )


def _insert_batch(conn: sqlite3.Connection, articles: List[Dict], fetched_at: str) -> int:
    if not articles:
        return 0
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO articles "
        "(url,title,domain,seendate,language,sourcecountry,source,fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                a["url"], a["title"], a["domain"], a["seendate"],
                a.get("language", ""), a.get("sourcecountry", ""),
                "GDELT", fetched_at,
            )
            for a in articles
        ],
    )
    conn.commit()
    return conn.total_changes - before


# ── GDELT API ─────────────────────────────────────────────────────────────────

def fetch_window(start_dt: datetime, end_dt: datetime, query_idx: int = 0) -> List[Dict]:
    """
    Fetch up to 250 articles for an explicit UTC time window.
    Uses startdatetime/enddatetime so we can scrape any historical range.
    """
    query = OIL_QUERIES[query_idx % len(OIL_QUERIES)]
    params = {
        "query":         query,
        "mode":          "artlist",
        "maxrecords":    250,
        "format":        "json",
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime":   end_dt.strftime("%Y%m%d%H%M%S"),
        "sort":          "date",
    }
    try:
        resp = requests.get(GDELT_DOC_URL, params=params, timeout=GDELT_TIMEOUT)
        resp.raise_for_status()
        raw = resp.json().get("articles") or []
        return [a for a in (_build_article(r) for r in raw) if a]
    except Exception as e:
        logger.warning(
            f"GDELT window fetch failed "
            f"({query!r} {start_dt.date()}→{end_dt.date()}): {e}"
        )
        return []


# ── Main scrape cycle (called by scheduler) ───────────────────────────────────

def scrape_one_cycle() -> int:
    """
    One scheduler tick. Runs in a thread executor (blocking is fine).

    Forward pass  — latest_fetched_end → now, all 5 queries.
    Backward pass — one 24 h window going back from oldest_scraped_start,
                    all 5 queries, with SCRAPE_RATE_DELAY between each.

    Returns the number of new rows inserted this cycle.
    """
    ensure_gdelt_db()
    conn = sqlite3.connect(GDELT_DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()
    total_new = 0

    try:
        # ── forward pass ──────────────────────────────────────────────────────
        latest_end_str = _get_state(conn, "latest_fetched_end")
        if latest_end_str:
            try:
                fwd_start = datetime.fromisoformat(latest_end_str)
                if fwd_start.tzinfo is None:
                    fwd_start = fwd_start.replace(tzinfo=timezone.utc)
            except Exception:
                fwd_start = now - timedelta(hours=2)
            # Cap at 2 h back so a stale cursor doesn't fetch months of data
            fwd_start = max(fwd_start, now - timedelta(hours=2))
        else:
            fwd_start = now - timedelta(hours=2)

        for qi in range(len(OIL_QUERIES)):
            articles = fetch_window(fwd_start, now, query_idx=qi)
            total_new += _insert_batch(conn, articles, fetched_at)
            if qi < len(OIL_QUERIES) - 1:
                time.sleep(SCRAPE_RATE_DELAY)

        _set_state(conn, "latest_fetched_end", now.isoformat())
        conn.commit()

        # ── backward pass ─────────────────────────────────────────────────────
        cutoff = now - timedelta(days=MAX_BACKFILL_DAYS)
        oldest_str = _get_state(conn, "oldest_scraped_start")

        if oldest_str:
            try:
                window_end = datetime.fromisoformat(oldest_str)
                if window_end.tzinfo is None:
                    window_end = window_end.replace(tzinfo=timezone.utc)
            except Exception:
                window_end = fwd_start
        else:
            # First ever backward pass starts just before the forward window
            window_end = fwd_start

        if window_end <= cutoff:
            logger.debug("GDELT backfill complete — reached %d-day limit", MAX_BACKFILL_DAYS)
            return total_new

        window_start = max(window_end - timedelta(hours=24), cutoff)

        time.sleep(SCRAPE_RATE_DELAY)
        for qi in range(len(OIL_QUERIES)):
            articles = fetch_window(window_start, window_end, query_idx=qi)
            total_new += _insert_batch(conn, articles, fetched_at)
            if qi < len(OIL_QUERIES) - 1:
                time.sleep(SCRAPE_RATE_DELAY)

        _set_state(conn, "oldest_scraped_start", window_start.isoformat())
        conn.commit()

        logger.info(
            "GDELT cycle: +%d new articles | backfill window %s → %s",
            total_new,
            window_start.date(),
            window_end.date(),
        )
        return total_new

    except Exception as e:
        logger.error("GDELT scrape_one_cycle error: %s", e)
        return total_new
    finally:
        conn.close()


# ── Read API ──────────────────────────────────────────────────────────────────

def _timespan_to_min_date(timespan: str) -> str:
    now = datetime.now(timezone.utc)
    ts = timespan.lower().strip()
    try:
        if ts.endswith("d"):
            cutoff = now - timedelta(days=int(ts[:-1]))
        elif ts.endswith("h"):
            cutoff = now - timedelta(hours=int(ts[:-1]))
        elif ts.endswith("min"):
            cutoff = now - timedelta(minutes=int(ts[:-3]))
        else:
            cutoff = now - timedelta(days=3)
    except ValueError:
        cutoff = now - timedelta(days=3)
    return cutoff.isoformat()


def get_stored_feed(timespan: str = "3d", total: int = 60) -> List[Dict]:
    """Read from local SQLite DB, newest-first, within the given timespan."""
    try:
        ensure_gdelt_db()
        min_date = _timespan_to_min_date(timespan)
        conn = sqlite3.connect(
            f"file:{GDELT_DB_PATH}?mode=ro", uri=True, timeout=5
        )
        rows = conn.execute(
            "SELECT url,title,domain,seendate,language,sourcecountry "
            "FROM articles WHERE seendate >= ? "
            "ORDER BY seendate DESC LIMIT ?",
            (min_date, total),
        ).fetchall()
        conn.close()
        return [
            {
                "url":           r[0],
                "title":         r[1],
                "domain":        r[2],
                "seendate":      r[3],
                "language":      r[4],
                "sourcecountry": r[5],
                "source":        "GDELT",
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("GDELT DB read failed: %s", e)
        return []


def get_scrape_status() -> Dict:
    """Return scrape progress for a monitoring endpoint."""
    try:
        conn = sqlite3.connect(
            f"file:{GDELT_DB_PATH}?mode=ro", uri=True, timeout=5
        )
        count   = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        oldest  = _get_state(conn, "oldest_scraped_start") or "—"
        latest  = _get_state(conn, "latest_fetched_end") or "—"
        conn.close()
        return {
            "total_articles":  count,
            "oldest_scraped":  oldest,
            "latest_fetched":  latest,
            "db_path":         GDELT_DB_PATH,
        }
    except Exception:
        return {"total_articles": 0, "oldest_scraped": "—", "latest_fetched": "—"}


# ── Legacy shim — used by /api/disruption/news ────────────────────────────────

def fetch_gdelt_articles(
    timespan: str = "3d",
    max_records: int = 50,
    query_idx: int = 0,
) -> List[Dict]:
    """Single live-API fetch (no DB). Kept for compatibility."""
    query = OIL_QUERIES[query_idx % len(OIL_QUERIES)]
    params = {
        "query":      query,
        "mode":       "artlist",
        "maxrecords": min(max_records, 250),
        "format":     "json",
        "timespan":   timespan,
        "sort":       "hybridrel",
    }
    try:
        resp = requests.get(GDELT_DOC_URL, params=params, timeout=GDELT_TIMEOUT)
        resp.raise_for_status()
        raw = resp.json().get("articles") or []
        return [a for a in (_build_article(r) for r in raw) if a]
    except Exception as e:
        logger.warning("GDELT fetch failed (query=%r): %s", query, e)
        return []


def fetch_multi_query(timespan: str = "3d", total: int = 60) -> List[Dict]:
    seen: set = set()
    combined: List[Dict] = []
    per_query = max(20, total // len(OIL_QUERIES))
    for idx in range(len(OIL_QUERIES)):
        for item in fetch_gdelt_articles(timespan=timespan, max_records=per_query, query_idx=idx):
            if item["url"] not in seen:
                seen.add(item["url"])
                combined.append(item)
        if len(combined) >= total:
            break
    combined.sort(key=lambda x: x.get("seendate", ""), reverse=True)
    return combined[:total]


def get_cached_feed(timespan: str = "3d", total: int = 40) -> List[Dict]:
    """Return from local DB if populated, else fall back to live API."""
    stored = get_stored_feed(timespan=timespan, total=total)
    if stored:
        return stored
    return fetch_multi_query(timespan=timespan, total=total)


# ── Article clustering ────────────────────────────────────────────────────────

_CLUSTER_STOP: Set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "of", "is", "are", "and",
    "or", "for", "as", "oil", "market", "price", "energy", "gas", "crude",
    "new", "says", "amid", "after", "with", "from", "by", "up", "its",
}


def _title_tokens(title: str) -> frozenset:
    words = re.sub(r"[^a-z0-9\s]", " ", title.lower()).split()
    return frozenset(w for w in words if w and w not in _CLUSTER_STOP and len(w) > 2)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_articles(
    articles: List[Dict],
    similarity_threshold: float = 0.30,
    time_window_hours: float = 24.0,
) -> List[Dict]:
    """
    Group articles about the same real-world event into clusters.
    Each cluster becomes one item with n_sources = number of unique sources.

    Articles must already be sorted newest-first (as returned by get_stored_feed).
    The representative headline is the article with the highest-trust domain
    (falls back to the first in the cluster if none match TRUSTED_DOMAINS).
    """
    clusters: List[Dict] = []   # [{rep, members, n_sources, domains}]

    for art in articles:
        tokens   = _title_tokens(art.get("title", ""))
        art_url  = art.get("url", "")
        art_dom  = art.get("domain", "")
        try:
            art_dt = datetime.fromisoformat(art["seendate"])
            if art_dt.tzinfo is None:
                art_dt = art_dt.replace(tzinfo=timezone.utc)
        except Exception:
            art_dt = None

        placed = False
        for cluster in clusters:
            rep    = cluster["representative"]
            r_toks = cluster["rep_tokens"]

            # Time-window gate: skip if more than `time_window_hours` apart
            if art_dt:
                try:
                    rep_dt = datetime.fromisoformat(rep["seendate"])
                    if rep_dt.tzinfo is None:
                        rep_dt = rep_dt.replace(tzinfo=timezone.utc)
                    if abs((art_dt - rep_dt).total_seconds()) > time_window_hours * 3600:
                        continue
                except Exception:
                    pass

            if _jaccard(tokens, r_toks) >= similarity_threshold:
                # Add to existing cluster
                if art_url not in cluster["seen_urls"]:
                    cluster["n_sources"] += 1
                    cluster["domains"].add(art_dom)
                    cluster["seen_urls"].add(art_url)
                    cluster["members"].append(art)
                    # Prefer trusted-domain article as representative
                    if art_dom in TRUSTED_DOMAINS and rep.get("domain") not in TRUSTED_DOMAINS:
                        cluster["representative"] = art
                        cluster["rep_tokens"] = tokens
                placed = True
                break

        if not placed:
            clusters.append({
                "representative": art,
                "rep_tokens":     tokens,
                "members":        [art],
                "n_sources":      1,
                "domains":        {art_dom},
                "seen_urls":      {art_url},
            })

    result: List[Dict] = []
    for cl in clusters:
        rep = dict(cl["representative"])
        rep["n_sources"]      = cl["n_sources"]
        rep["domains"]        = sorted(cl["domains"])
        rep["is_multi_source"] = cl["n_sources"] >= 2
        result.append(rep)

    return result
