"""
Live financial-headline sources — the GDELT replacement layer.

GDELT was removed (unreliable, rolling-window only). These RSS sources are all
reachable and oil/market relevant, and each headline is run through the same
classifier as ACLED so a market-moving item (Iran, Hormuz, OPEC, sanctions) lands
on a node and becomes forecast-capable:

  - FinancialJuice  — real-time financial-wire headlines
  - OilPrice        — oil-market trade press (already oil-scoped)
  - Reuters/Google  — trusted crude/OPEC headlines via Google-News RSS
  - Trump posts     — Truth Social via trumpstruth.org RSS (tariffs, Iran, OPEC,
                      "drill baby drill" — frequently move crude)

Headline + URL + metadata only (no full text). Each item is returned in the same
shape as gdelt_fetcher/eia_rss_fetcher so the news endpoint mixes them freely.
"""

import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Dict, List
from urllib.parse import urlparse

import requests

from services.eia_rss_fetcher import _OIL_KEYWORDS

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (compatible; OilDeskBot/1.0)"}
_TIMEOUT = (5.0, 12.0)

# Trump posts are mostly non-market noise. Keep only ones naming a STRONG, oil-
# specific lever (in the lede). Weak geopolitical terms (iran, tariff, sanction)
# are deliberately excluded here — they match too many political posts, and the
# oil-relevant version of that news is already covered by Reuters/FinancialJuice.
_TRUMP_KEYWORDS = frozenset({
    "oil", "crude", "gasoline", "gas price", "gas prices", "diesel", "fuel price",
    "opec", "drill", "drilling", "refinery", "barrel", "wti", "brent",
    "lng", "natural gas", "strategic petroleum", "spr", "pipeline", "energy",
    "embargo", "price cap", "export ban", "nord stream", "drill baby",
    "energy independence", "oil price", "oil prices",
})
# word-boundary matcher so "spr" doesn't match "spring", "oil" not "boiling"
_TRUMP_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _TRUMP_KEYWORDS) + r")\b", re.I)
_TRUMP_LEDE = 180   # only look at the post's opening — buried mentions don't count

SOURCES = [
    {"tag": "FinancialJuice", "url": "https://www.financialjuice.com/feed.ashx?xml=RSS", "filter": "oil"},
    {"tag": "OilPrice",       "url": "https://oilprice.com/rss/main",                    "filter": "none"},
    {"tag": "Wire",           "url": "https://news.google.com/rss/search?q=crude+oil+OR+OPEC+OR+brent+when:2d&hl=en-US&gl=US&ceid=US:en", "filter": "oil", "google_news": True},
    {"tag": "Trump",          "url": "https://trumpstruth.org/feed",                     "filter": "trump"},
]

# Google-News search returns mixed publishers (and some junk like "AAA Gas Prices").
# Only items from these established financial/energy outlets are kept — each item is
# then labelled with its REAL publisher, not a generic "Reuters".
TRUSTED_PUBLISHERS = (
    "reuters", "bloomberg", "wall street journal", "wsj", "financial times",
    "new york times", "cnbc", "fortune", "barron", "marketwatch", "forbes",
    "associated press", "the economist", "axios", "politico", "the hill",
    "s&p global", "platts", "argus media", "rigzone", "oilprice", "hart energy",
    "world oil", "upstream", "energy intelligence", "hellenic shipping", "gcaptain",
    "nikkei", "bbc", "the guardian", "al jazeera", "npr", "stonex", "ing think",
    "goldman", "jpmorgan", "j.p. morgan", "morgan stanley", "kpler", "vortexa",
    "opec", "the iea", "u.s. energy information", "investing.com", "yahoo finance",
    "business insider", "cnn", "abc news", "cbs news", "the telegraph",
)

# Pretty, short names for the messy publisher strings Google News returns.
_PUB_FIX = {
    "wsj": "WSJ", "the wall street journal": "WSJ", "bloomberg": "Bloomberg",
    "the new york times": "NYT", "oilprice": "OilPrice", "yahoo finance": "Yahoo Finance",
    "business insider": "Business Insider", "ing think": "ING", "s&p global": "S&P Global",
    "financial times": "FT", "the economist": "The Economist", "cnbc": "CNBC",
    "reuters": "Reuters",
}


def _publisher_of(item) -> str:
    el = item.find("{*}source")
    return (el.text or "").strip() if el is not None else ""


def _is_trusted(publisher: str) -> bool:
    low = publisher.lower()
    return any(t in low for t in TRUSTED_PUBLISHERS)


def _clean_publisher(publisher: str) -> str:
    low = publisher.lower()
    for k, v in _PUB_FIX.items():
        if k in low:
            return v
    name = re.split(r"\s*[|–]\s*", publisher)[0].strip()      # drop "| OilPrice.com" tails
    return name.replace(".com", "").strip() or publisher


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _pubdate(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        return raw


def _relevant(title: str, desc: str, mode: str) -> bool:
    if mode == "none":
        return True
    if mode == "trump":
        # important = direct oil/energy lever OR oil-relevant geopolitics (war /
        # peace treaty in an oil-producing/transit region). Shared with the Trump
        # price-impact study so the feed and the model agree on what counts.
        try:
            from services.trump_price_impact import is_important_oil
            return is_important_oil(title)
        except Exception:
            return bool(_TRUMP_RE.search(title[:_TRUMP_LEDE]))
    low = (title + " " + desc).lower()
    return any(k in low for k in _OIL_KEYWORDS)


def _fetch_one(src: Dict, max_items: int) -> List[Dict]:
    try:
        resp = requests.get(src["url"], headers=_UA, timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        logger.warning("headline source %s failed: %s", src["tag"], e)
        return []

    google_news = src.get("google_news", False)
    out: List[Dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link")  or "").strip()
        pub   = (item.findtext("pubDate") or "").strip()
        desc  = (item.findtext("description") or "").strip()
        if not title:
            continue

        tag = src["tag"]
        if google_news:
            publisher = _publisher_of(item)
            if not _is_trusted(publisher):          # drop junk / untrusted publishers
                continue
            if "oilprice" in publisher.lower():     # already a dedicated source → skip dup
                continue
            # Google News titles are "Headline - Publisher" → strip the suffix
            if publisher and title.endswith(" - " + publisher):
                title = title[: -(len(publisher) + 3)].strip()
            elif " - " in title:
                title = title.rsplit(" - ", 1)[0].strip()
            tag = _clean_publisher(publisher) or "Wire"

        if not _relevant(title, desc, src["filter"]):
            continue
        out.append({
            "url":           link or src["url"],
            "title":         (f"[{tag}] " + title) if tag == "Trump" else title,
            "domain":        _domain(link) or tag.lower(),
            "seendate":      _pubdate(pub) if pub else "",
            "language":      "English",
            "sourcecountry": "",
            "source":        tag,
            "n_sources":     1,
            "domains":       [_domain(link)] if link else [],
            "is_multi_source": False,
            "description":   desc[:250] if desc else "",
            "publisher":     (_publisher_of(item) if google_news else tag),
        })
        if len(out) >= max_items:
            break
    logger.info("headline source %s: %d items", src["tag"], len(out))
    return out


def fetch_headlines(max_per_source: int = 12) -> List[Dict]:
    """Fetch + oil-filter all live headline sources; dedup by lowercased title."""
    seen: set = set()
    merged: List[Dict] = []
    for src in SOURCES:
        for it in _fetch_one(src, max_per_source):
            key = it["title"].lower().split("] ", 1)[-1][:80]
            if key in seen:
                continue
            seen.add(key)
            merged.append(it)
    merged.sort(key=lambda x: x.get("seendate", ""), reverse=True)
    return merged
