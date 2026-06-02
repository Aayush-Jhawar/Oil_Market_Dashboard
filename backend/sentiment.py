"""Simple sentiment module using TextBlob as a fallback for VADER.

Exposes `analyze_news_items` which accepts a list of headlines and returns
per-item polarity and a small aggregate.
"""
from __future__ import annotations

from textblob import TextBlob
from typing import List, Dict, Any


def analyze_news_items(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    results = []
    total = 0.0
    for it in items:
        text = it.get("headline") or it.get("title") or ""
        tb = TextBlob(text)
        polarity = round(tb.sentiment.polarity, 4)
        total += polarity
        results.append({"headline": text, "vader_score": polarity, "finbert_label": None, "finbert_score": None, "composite_sentiment": polarity})

    overall = total / len(items) if items else 0.0
    return {"overall": overall, "items": results, "finbert_loaded": False}
