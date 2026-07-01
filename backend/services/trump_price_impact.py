"""
Trump-post → multi-product price-impact study (trained on 1-minute futures data).

A war/escalation post (strike, sanctions, missile) lifts the WHOLE oil complex;
a calm/de-escalation post (deal, ceasefire, "prices coming down") drags it. So we
measure the move across all four front-month products — WTI (CL), Brent (LCO),
distillate (HO), gasoil (LGO) — after each oil-relevant Trump Truth-Social post,
at T+1 / T+2 / T+5 TRADING DAYS (close-to-close).

Why daily, not intraday: the ICE legs (Brent/gasoil) have unreliable 1-minute
timestamps — single-minute WTI-Brent move correlation is ~0, while daily
close-to-close is 0.84+. Daily anchoring is the honest, cross-product-comparable
measure (and matches the disruption engine's T+1/T+5 horizons).

Two lenses:
  - STANCE  : escalation / calm / neutral  → "does war vs calm news move everything?"
  - TOPIC   : iran / russia / drill / opec / tariff / …  → finer attribution.

Each cell carries the median move, P(up), and a z-test of the directional bias vs
a coin-flip (p<.01 / p<.05 / ns). The per-(stance|topic, product) distribution IS
the trained model: a new post → classify → that distribution. Base rate, not a
price oracle. Everything is point-in-time against the front-month outright.
"""

import math
import os
import re
import sqlite3
from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRUMP_DB = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "Dashboard_v3", "DB", "trump_posts.db")

# product → data sources, in preference order:
#   daily    : committed compact daily-close parquet (Data/*_front_month.parquet, ~25KB) —
#              the canonical, versioned artifact the study actually uses.
#   npz      : local minute-bar cache (Data/*_front_month.npz) — resamples to the same daily series.
#   parquet  : the multi-hundred-MB raw source (Git LFS), used only to rebuild the compact forms.
PRODUCTS: Dict[str, Dict[str, str]] = {
    "wti":        {"daily": "cl_front_month.parquet",         "npz": "cl_front_month.npz",         "parquet": "CL_data.parquet"},
    "brent":      {"daily": "brent_front_month.parquet",      "npz": "brent_front_month.npz",      "parquet": "LCO_data.parquet"},
    "distillate": {"daily": "distillate_front_month.parquet", "npz": "distillate_front_month.npz", "parquet": "HO_data.parquet"},
    "gasoil":     {"daily": "gasoil_front_month.parquet",     "npz": "gasoil_front_month.npz",     "parquet": "LGO_data.parquet"},
}
TRUMP_POSTS_PARQUET = os.path.join(_ROOT, "Data", "trump_posts.parquet")
PRODUCT_LABEL = {"wti": "WTI", "brent": "Brent", "distillate": "Distillate (HO)", "gasoil": "Gasoil"}

HORIZONS = {"t1d": 1, "t2d": 2, "t5d": 5}   # trading days (close-to-close)

# ── Topic taxonomy (first match wins) ─────────────────────────────────────────
TOPICS: List = [
    ("prices_down", ["prices down", "price down", "lower price", "come down", "coming down",
                     "cut their prices", "too high", "rip off", "gouging", "bring down",
                     "gas prices", "gasoline"]),
    ("drill",       ["drill", "drilling", "energy independence", "liquid gold", "frack",
                     "energy dominance", "oil production"]),
    ("opec",        ["opec", "saudi", "production cut", "production increase"]),
    ("iran",        ["iran", "iranian", "nuclear deal", "strait of hormuz", "tehran"]),
    ("russia",      ["russia", "ukraine", "putin", "nord stream", "moscow"]),
    ("venezuela",   ["venezuela", "maduro"]),
    ("mideast_war", ["israel", "hormuz", "red sea", "houthi", "yemen", "gaza",
                     "hezbollah", "lebanon", "persian gulf", "gulf of oman"]),
    ("tariff",      ["tariff", "price cap", "export ban", "trade war"]),
    ("energy_other",["oil", "crude", "wti", "brent", "barrel", "pipeline", "refinery",
                     "lng", "natural gas", "fuel", "energy", "spr", "strategic petroleum"]),
]

# ── Stance taxonomy (war/supply-risk vs calm/de-escalation) ───────────────────
# Tight, unambiguous war vs peace terms (broad words like "deal"/"threat"/"sanction"
# polluted the buckets, so they're out).
_ESCALATION = ["strike", "struck", "airstrike", "attack", "missile", "drone", "bomb",
               "bombing", "war ", "warship", "military", "invade", "invasion",
               "blockade", "seized", "naval", "retaliat", "escalat", "hostilit",
               "sanction", "embargo", "shut down", "wipe out"]
_CALM = ["ceasefire", "cease-fire", "truce", "peace deal", "peace agreement", "treaty",
         "peace treaty", "peace", "de-escalat", "deescalat", "armistice", "stand down",
         "agreement signed", "deal is done"]


# ── "Important oil/energy" gate ───────────────────────────────────────────────
# A post qualifies if it EITHER (a) names a direct oil/gas/energy lever, OR
# (b) is oil-relevant GEOPOLITICS — a war/peace/conflict event term paired with an
# oil-producing/transit actor or region. Pure domestic political noise (polls,
# endorsements, immigration, "trade war with Canada") is excluded.
_IMPORTANT_OIL = [
    "oil", "crude", "gasoline", "gas price", "gas prices", "gas pump", "at the pump",
    "price of gas", "price of oil", "diesel", "jet fuel", "fuel price", "fuel prices",
    "opec", "drill", "drilling", "drilled", "frack", "fracking", "refinery", "refineries",
    "barrel", "barrels", "wti", "brent", "west texas", "lng", "natural gas", "nat gas",
    "strategic petroleum", "spr", "energy independence", "energy dominance", "energy price",
    "energy prices", "energy policy", "energy cost", "energy costs", "energy secretary",
    "energy department", "liquid gold", "keystone", "nord stream", "dakota access",
    "oil and gas", "oil & gas", "offshore drill", "pipeline",
]
# Geopolitical EVENT terms (war / peace / kinetic / sanctions)
_GEO_EVENT = [
    "war", "peace", "treaty", "ceasefire", "cease-fire", "truce", "armistice",
    "peace deal", "peace agreement", "invasion", "invade", "strike", "struck",
    "airstrike", "attack", "missile", "drone", "bomb", "bombing", "military",
    "troops", "nuclear", "sanction", "embargo", "blockade", "conflict", "warship",
    "retaliat", "hostilit", "ceasefire deal", "de-escalat", "deescalat",
]
# Oil-producing / transit actors & regions
_OIL_REGION = [
    "iran", "iranian", "russia", "russian", "ukraine", "saudi", "venezuela", "israel",
    "opec", "hormuz", "red sea", "middle east", "persian gulf", "gulf of oman",
    "houthi", "yemen", "iraq", "libya", "nigeria", "kuwait", "qatar", "uae",
    "emirates", "strait", "tehran", "moscow", "putin", "hezbollah", "gaza", "lebanon",
]
_IMPORTANT_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _IMPORTANT_OIL) + r")\b", re.I)
_GEO_EVENT_RE  = re.compile(r"\b(" + "|".join(re.escape(k) for k in _GEO_EVENT) + r")\b", re.I)
_OIL_REGION_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _OIL_REGION) + r")\b", re.I)


def is_important_oil(text: str) -> bool:
    """True for direct oil/energy posts OR oil-relevant geopolitics (war/peace in
    an oil-producing/transit region)."""
    t = text or ""
    if _IMPORTANT_RE.search(t):
        return True
    return bool(_GEO_EVENT_RE.search(t) and _OIL_REGION_RE.search(t))


def classify_topic(text: str) -> Optional[str]:
    low = text.lower()
    for topic, kws in TOPICS:
        if any(k in low for k in kws):
            return topic
    return None


def classify_stance(text: str) -> str:
    low = text.lower()
    e = sum(low.count(k) for k in _ESCALATION)
    c = sum(low.count(k) for k in _CALM)
    if e > c:
        return "escalation"
    if c > e:
        return "calm"
    return "neutral"


# ── Price series (per product, numpy-only) ────────────────────────────────────

@lru_cache(maxsize=8)
def _series(product: str):
    """Daily close (last 1-min bar of each UTC day) for the front-month product.

    Reads the committed compact daily parquet when present (already one point per
    day, so the resample below is a passthrough); falls back to the local minute
    npz, then to the raw LFS parquet. Resampling kills unreliable intraday ICE
    timestamps. Returns (day_array datetime64[ns], close_array).
    """
    daily = os.path.join(_ROOT, "Data", PRODUCTS[product]["daily"])
    npz = os.path.join(_ROOT, "Data", PRODUCTS[product]["npz"])
    if os.path.exists(daily):
        df = pd.read_parquet(daily)
        ts, px = df["ts"].to_numpy(dtype=np.int64), df["px"].to_numpy(dtype=float)
    elif os.path.exists(npz):
        z = np.load(npz)
        ts, px = z["ts"].astype(np.int64), z["px"].astype(float)
    else:
        df = pd.read_parquet(os.path.join(_ROOT, "Data", PRODUCTS[product]["parquet"]),
                             columns=["timestamp", "c1||weighted_mid"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.dropna(subset=["c1||weighted_mid"]).sort_values("timestamp")
        ts = df["timestamp"].values.astype("datetime64[ns]").astype(np.int64)
        px = df["c1||weighted_mid"].to_numpy(dtype=float)
    s = pd.Series(px, index=pd.to_datetime(ts).normalize()).groupby(level=0).last()
    return s.index.values.astype("datetime64[ns]"), s.to_numpy(dtype=float)


def rebuild_npz() -> List[str]:
    """Re-extract every product's front month from its parquet into a compact npz."""
    out = []
    for prod, paths in PRODUCTS.items():
        df = pd.read_parquet(os.path.join(_ROOT, "Data", paths["parquet"]),
                             columns=["timestamp", "c1||weighted_mid"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.dropna(subset=["c1||weighted_mid"]).sort_values("timestamp")
        ts = df["timestamp"].values.astype("datetime64[ns]").astype(np.int64)
        px = df["c1||weighted_mid"].to_numpy(dtype=float)
        path = os.path.join(_ROOT, "Data", paths["npz"])
        np.savez_compressed(path, ts=ts, px=px)
        out.append(path)
    return out


def rebuild_daily_parquet() -> List[str]:
    """Rebuild the committed compact daily-close parquet from each raw LFS source.

    This is the versioned artifact `_series` reads (Data/*_front_month.parquet,
    ~25KB each): one close per UTC day, so the study renders from the repo without
    the minute npz or the multi-hundred-MB raw parquet.
    """
    out = []
    for prod, paths in PRODUCTS.items():
        npz = os.path.join(_ROOT, "Data", paths["npz"])
        if os.path.exists(npz):
            z = np.load(npz)
            ts, px = z["ts"].astype(np.int64), z["px"].astype(float)
        else:
            src = pd.read_parquet(os.path.join(_ROOT, "Data", paths["parquet"]),
                                  columns=["timestamp", "c1||weighted_mid"])
            src["timestamp"] = pd.to_datetime(src["timestamp"], utc=True)
            src = src.dropna(subset=["c1||weighted_mid"]).sort_values("timestamp")
            ts = src["timestamp"].values.astype("datetime64[ns]").astype(np.int64)
            px = src["c1||weighted_mid"].to_numpy(dtype=float)
        s = pd.Series(px, index=pd.to_datetime(ts).normalize()).groupby(level=0).last()
        df = pd.DataFrame({"ts": s.index.values.astype("datetime64[ns]").astype(np.int64),
                           "px": s.to_numpy(dtype=float)})
        path = os.path.join(_ROOT, "Data", paths["daily"])
        df.to_parquet(path, compression="zstd", index=False)
        out.append(path)
    return out


def _move(product: str, ts_ns: int, ndays: int) -> Optional[float]:
    """Close-to-close % move: pre-tweet close → close `ndays` trading days later."""
    days, px = _series(product)
    tdate = np.datetime64(pd.Timestamp(ts_ns).normalize(), "ns")
    a = int(np.searchsorted(days, tdate, side="left"))        # first trading day >= tweet
    base_i = a - 1                                            # close just before the tweet
    tgt_i = a - 1 + ndays                                     # n trading days after baseline
    if base_i < 0 or tgt_i >= len(px):
        return None
    base = px[base_i]
    if base <= 0:
        return None
    return round((px[tgt_i] - base) / base * 100, 3)


# ── Posts ─────────────────────────────────────────────────────────────────────

def _load_posts(oil_only: bool = True) -> List[Dict]:
    """Load posts, re-filtering to IMPORTANT oil/energy ones via is_important_oil
    on the stored text (stricter than the scraper's broad oil_relevant flag — no
    re-scrape needed)."""
    # pre-filter on the scraper flag (cheap), then apply the strict gate in Python.
    # Prefer the live local DB; fall back to the committed posts parquet.
    if os.path.exists(TRUMP_DB):
        conn = sqlite3.connect(f"file:{TRUMP_DB}?mode=ro", uri=True, timeout=10)
        rows = conn.execute(
            "SELECT status_id, created_utc, text FROM posts "
            "WHERE oil_relevant = 1 ORDER BY created_utc"
        ).fetchall()
        conn.close()
    elif os.path.exists(TRUMP_POSTS_PARQUET):
        dfp = pd.read_parquet(TRUMP_POSTS_PARQUET)
        dfp = dfp[dfp["oil_relevant"] == 1].sort_values("created_utc")
        rows = list(dfp[["status_id", "created_utc", "text"]].itertuples(index=False, name=None))
    else:
        return []
    out = [{"status_id": r[0], "created_utc": r[1], "text": r[2]} for r in rows]
    if oil_only:
        out = [p for p in out if is_important_oil(p["text"])]
    return out


def _agg(vals: List[float]) -> Dict:
    a = np.array([v for v in vals if v is not None], dtype=float)
    if a.size == 0:
        return {"n": 0}
    n = int(a.size)
    p_up = float((a > 0).mean())
    z = (p_up - 0.5) / math.sqrt(0.25 / n) if n else 0.0      # bias vs coin-flip
    signif = "p<.01" if abs(z) > 2.576 else "p<.05" if abs(z) > 1.96 else "ns"
    return {
        "n": n,
        "median": round(float(np.median(a)), 3),
        "p_up": round(p_up, 3),
        "abs_median": round(float(np.median(np.abs(a))), 3),
        "z": round(z, 2),
        "signif": signif,
    }


def _new_bucket() -> Dict[str, Dict[str, List[float]]]:
    return {p: {h: [] for h in HORIZONS} for p in PRODUCTS}


def _agg_bucket(bucket: Dict[str, Dict[str, List[float]]]) -> Dict[str, Dict[str, Dict]]:
    return {p: {h: _agg(bucket[p][h]) for h in HORIZONS} for p in PRODUCTS}


# ── Study ─────────────────────────────────────────────────────────────────────

def run_study(oil_only: bool = True) -> Dict:
    posts = _load_posts(oil_only=oil_only)
    overall = _new_bucket()
    by_topic: Dict[str, Dict] = {}
    by_stance: Dict[str, Dict] = {}
    scored: List[Dict] = []

    for p in posts:
        try:
            ts_ns = int(pd.Timestamp(p["created_utc"], tz="UTC").value)
        except Exception:
            continue
        topic = classify_topic(p["text"]) or "energy_other"
        stance = classify_stance(p["text"])
        tb = by_topic.setdefault(topic, _new_bucket())
        sb = by_stance.setdefault(stance, _new_bucket())
        moves: Dict[str, Dict[str, Optional[float]]] = {}
        any_move = False
        for prod in PRODUCTS:
            moves[prod] = {}
            for h, mins in HORIZONS.items():
                mv = _move(prod, ts_ns, mins)
                moves[prod][h] = mv
                if mv is not None:
                    overall[prod][h].append(mv)
                    tb[prod][h].append(mv)
                    sb[prod][h].append(mv)
                    any_move = True
        if any_move:
            scored.append({"status_id": p["status_id"], "created_utc": p["created_utc"],
                           "topic": topic, "stance": stance, "moves": moves,
                           "text": p["text"][:160]})

    return {
        "n_posts_scored": len(scored),
        "products": list(PRODUCTS),
        "product_labels": PRODUCT_LABEL,
        "horizons": HORIZONS,
        "overall":  _agg_bucket(overall),
        "by_topic":  {t: _agg_bucket(b) for t, b in sorted(by_topic.items())},
        "by_stance": {s: _agg_bucket(b) for s, b in by_stance.items()},
        "posts": scored,
    }


def predict_impact(text: str) -> Dict:
    """Trained prediction for a NEW post: its stance + topic → per-product stats."""
    study = run_study(oil_only=True)
    topic = classify_topic(text) or "energy_other"
    stance = classify_stance(text)
    return {
        "topic": topic, "stance": stance,
        "by_stance": study["by_stance"].get(stance, {}),
        "by_topic":  study["by_topic"].get(topic, {}),
        "note": "Per-(stance|topic, product) empirical move after Trump posts of this kind. Base rate.",
    }
