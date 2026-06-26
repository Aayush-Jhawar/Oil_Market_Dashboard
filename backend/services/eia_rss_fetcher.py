"""
EIA Today in Energy RSS feed — secondary fallback when GDELT is unavailable.

URL: https://www.eia.gov/rss/todayinenergy.xml
Content: EIA analysis briefs (1-3 per day), not breaking news.
License: US Government / public domain.
Latency: ~daily cadence; items are educational summaries, not live disruption alerts.

Returns articles in the same structure as gdelt_fetcher so the news
endpoint can mix sources transparently.
"""

import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Dict, List
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

EIA_RSS_URL = "https://www.eia.gov/rss/todayinenergy.xml"
EIA_TIMEOUT = (3.0, 10.0)


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return "eia.gov"


def _parse_pubdate(raw: str) -> str:
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        return raw


def fetch_eia_rss(max_items: int = 20) -> List[Dict]:
    """
    Fetch EIA Today in Energy RSS and return articles in the standard feed format.
    Each item gets source='EIA_RSS', n_sources=1, is_multi_source=False.
    """
    try:
        resp = requests.get(EIA_RSS_URL, timeout=EIA_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items: List[Dict] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            if not title or not link:
                continue
            items.append({
                "url":           link,
                "title":         title,
                "domain":        _domain(link),
                "seendate":      _parse_pubdate(pub) if pub else "",
                "language":      "English",
                "sourcecountry": "United States",
                "source":        "EIA_RSS",
                "n_sources":     1,
                "domains":       ["eia.gov"],
                "is_multi_source": False,
                "description":   desc[:250] if desc else "",
            })
        logger.info("EIA RSS: %d items", len(items))
        return items[:max_items]
    except Exception as e:
        logger.warning("EIA RSS fetch failed: %s", e)
        return []
