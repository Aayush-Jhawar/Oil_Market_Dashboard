import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging
from collections import defaultdict
import os
import re
from services.sentiment_analyzer import SentimentAnalyzer

# 3-layer stale news defense patterns
URL_DATE_MAX_AGE_DAYS = 14
_URL_DATE_RE = re.compile(r"/(20\d{2})[/\-_](\d{1,2})(?:[/\-_](\d{1,2}))?")
_HEADLINE_YEAR_RE = re.compile(r"\b(20\d{2})\b")

logger = logging.getLogger(__name__)


class NewsFetcher:
    """Fetch and analyze energy news from multiple premium sources with sentiment scoring"""

    # Premium and high-quality energy news sources
    RSS_SOURCES = [
        {
            "url": "https://feeds.reuters.com/reuters/businessNews",
            "weight": 1.0,
            "name": "Reuters",
            "category": "premium"
        },
        {
            "url": "https://oilprice.com/rss/main",
            "weight": 0.95,
            "name": "OilPrice",
            "category": "energy"
        },
        {
            "url": "https://www.rigzone.com/news/rss/rigzone_news.aspx",
            "weight": 0.90,
            "name": "Rigzone",
            "category": "energy"
        },
        {
            "url": "https://www.opec.org/opec_web/en/press_room/rss.htm",
            "weight": 0.99,
            "name": "OPEC",
            "category": "official"
        },
        {
            "url": "https://www.bloomberg.com/feed/podcast/etf-report.xml",
            "weight": 0.95,
            "name": "Bloomberg",
            "category": "premium"
        },
        {
            "url": "https://feeds.bloomberg.com/markets/news/rss/commodities.rss",
            "weight": 0.95,
            "name": "Bloomberg Commodities",
            "category": "premium"
        },
        {
            "url": "https://feeds.cnbc.com/id/100003114/device/rss/rss.html",
            "weight": 0.90,
            "name": "CNBC Energy",
            "category": "premium"
        },
        {
            "url": "https://www.worldoil.com/news/rss.xml",
            "weight": 0.85,
            "name": "World Oil",
            "category": "energy"
        }
    ]

    GEOPOLITICAL_ENTITIES = {
        "Saudi Arabia": 1.0,
        "Strait of Hormuz": 1.0,
        "OPEC": 0.95,
        "Russia": 0.95,
        "Iran": 0.95,
        "Iraq": 0.85,
        "UAE": 0.85,
        "Libya": 0.80,
        "Nigeria": 0.75,
        "Venezuela": 0.75,
        "SPR": 0.70,
        "US Gulf Coast": 0.70,
        "Houston": 0.65,
        "China": 0.70,
        "India": 0.65,
        "Europe": 0.60,
    }

    @staticmethod
    def score_sentiment_legacy(text: str) -> float:
        """
        Legacy sentiment scoring (now using enhanced analyzer)
        Kept for backward compatibility
        """
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_complete(text)
        return result["combined_score"]

    @staticmethod
    def extract_entities(text: str) -> List[str]:
        """Extract geopolitical entities from text"""
        return SentimentAnalyzer.extract_entities(text)

    @staticmethod
    def _url_is_recent(url: str) -> bool:
        """Return False when the URL path encodes a date older than URL_DATE_MAX_AGE_DAYS."""
        if not url:
            return True
        m = _URL_DATE_RE.search(url)
        if not m:
            return True
        try:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3)) if m.group(3) else 15
            url_date = datetime(year, month, max(1, min(28, day)))
        except (ValueError, TypeError):
            return True
        cutoff = datetime.now() - timedelta(days=URL_DATE_MAX_AGE_DAYS)
        return url_date >= cutoff

    @staticmethod
    def _headline_year_is_current(headline: str) -> bool:
        """Require explicit year in headline to be current or previous year."""
        if not headline:
            return True
        years = [int(y) for y in _HEADLINE_YEAR_RE.findall(headline)]
        if not years:
            return True
        current_year = datetime.now().year
        return max(years) >= current_year - 1

    @staticmethod
    def fetch_rss_source(source: Dict, max_articles: int = 15) -> List[Dict]:
        """Fetch articles from a single RSS source with timeout"""
        articles = []
        try:
            feed = feedparser.parse(source["url"])
            
            if not feed.entries:
                logger.warning(f"No entries from {source['name']}")
                return articles
            
            for entry in feed.entries[:max_articles]:
                try:
                    # Extract article details
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    url = entry.get("link", "")
                    
                    if not title:
                        continue
                    
                    # Parse date
                    published_at = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published_at = datetime(*entry.published_parsed[:6])
                        except:
                            published_at = datetime.now()
                    else:
                        published_at = datetime.now()
                    
                    # Adapt live news to the 2026 simulation environment
                    try:
                        published_at = published_at.replace(year=datetime.now().year)
                    except ValueError:
                        pass
                    
                    # Run complete sentiment analysis
                    sentiment_data = SentimentAnalyzer.analyze_complete(summary, title)
                    
                    # Create article record
                    article = {
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "source": source["name"],
                        "source_category": source["category"],
                        "published_at": published_at.isoformat(),
                        "fetched_at": datetime.now().isoformat(),
                        "sentiment_score": sentiment_data["combined_score"],
                        "sentiment_label": sentiment_data["label"],
                        "vader_score": sentiment_data["vader_score"],
                        "finbert_score": sentiment_data["finbert_score"],
                        "relevance_score": sentiment_data["relevance_score"],
                        "entities": sentiment_data["entities"],
                        "keyword_count": sentiment_data["keyword_count"],
                        "source_weight": source["weight"],
                        "weighted_sentiment": sentiment_data["combined_score"] * source["weight"],
                    }
                    articles.append(article)
                    
                except Exception as e:
                    logger.debug(f"Error processing entry from {source['name']}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error fetching from {source['name']}: {e}")
        
        return articles

    @staticmethod
    def fetch_all_news(max_articles_per_source: int = 15) -> List[Dict]:
        """
        Fetch all news from all sources using parallel execution
        Returns sorted by recency and relevance
        """
        all_articles = []
        
        # Fetch from sources in parallel
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(
                    NewsFetcher.fetch_rss_source, source, max_articles_per_source
                ): source["name"]
                for source in NewsFetcher.RSS_SOURCES
            }
            
            for future in futures:
                try:
                    articles = future.result(timeout=15)
                    all_articles.extend(articles)
                except FuturesTimeoutError:
                    logger.warning(f"Timeout fetching from {futures[future]}")
                except Exception as e:
                    logger.error(f"Error fetching from {futures[future]}: {e}")
        
        # Sort by relevance_score * recency
        now = datetime.now()
        for article in all_articles:
            published = datetime.fromisoformat(article["published_at"])
            hours_old = (now - published).total_seconds() / 3600
            recency_score = max(0, 1 - (hours_old / 168))  # Decay over 1 week
            article["score"] = article["relevance_score"] * 0.7 + recency_score * 0.3
        
        # Sort by score descending, then by published date
        all_articles.sort(
            key=lambda x: (x.get("score", 0), x["published_at"]),
            reverse=True
        )
        
        return all_articles[:50]  # Return top 50 most relevant

    @staticmethod
    def get_sentiment_summary() -> Dict:
        """Get overall market sentiment from recent news"""
        articles = NewsFetcher.fetch_all_news(max_articles_per_source=5)
        
        if not articles:
            return {
                "overall_sentiment": "neutral",
                "bullish_ratio": 0.5,
                "article_count": 0,
                "dominant_entities": [],
                "timestamp": datetime.now().isoformat()
            }
        
        bullish = sum(1 for a in articles if a["sentiment_label"] == "positive")
        bearish = sum(1 for a in articles if a["sentiment_label"] == "negative")
        neutral = sum(1 for a in articles if a["sentiment_label"] == "neutral")
        total = len(articles)
        
        # Aggregate entities
        entity_counts = defaultdict(float)
        for article in articles:
            for entity in article.get("entities", []):
                entity_counts[entity] += article.get("relevance_score", 0.5)
        
        top_entities = sorted(
            entity_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]
        
        if bullish + bearish > 0:
            bullish_ratio = bullish / (bullish + bearish)
        else:
            bullish_ratio = 0.5
        
        if bullish_ratio > 0.6:
            overall = "bullish"
        elif bullish_ratio < 0.4:
            overall = "bearish"
        else:
            overall = "neutral"
        
        return {
            "overall_sentiment": overall,
            "bullish_ratio": float(bullish_ratio),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "article_count": total,
            "dominant_entities": [e[0] for e in top_entities],
            "top_articles": articles[:5],
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def calculate_sentiment_trend(articles: List[Dict], decay_factor: float = 0.95) -> float:
        """
        Calculate exponentially-decayed sentiment trend
        Recent articles weighted more heavily than older ones
        """
        if not articles:
            return 0.0
        
        now = datetime.now()
        weighted_sum = 0.0
        total_weight = 0.0
        
        for article in articles:
            try:
                published = datetime.fromisoformat(article.get("published_at", now.isoformat()))
                hours_old = (now - published).total_seconds() / 3600
                
                # Exponential decay of weight based on age
                weight = (decay_factor ** (hours_old / 24))  # Decay per day
                
                sentiment = article.get("sentiment_score", 0)
                weighted_sum += sentiment * weight
                total_weight += weight
            except Exception as e:
                logger.debug(f"Error processing article for trend: {e}")
                continue
        
        if total_weight > 0:
            raw_sentiment = weighted_sum / total_weight
            # Dampen sentiment if there are very few articles
            if len(articles) < 3:
                # E.g., 1 article -> dampen by 0.33, 2 articles -> 0.66
                dampening_factor = len(articles) / 3.0
                return raw_sentiment * dampening_factor
            return raw_sentiment
        else:
            return 0.0
