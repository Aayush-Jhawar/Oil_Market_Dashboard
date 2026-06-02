"""
Enhanced Sentiment Analysis for Energy News
Combines VADER (lexicon-based) and FinBERT (transformer-based) for comprehensive sentiment detection
"""
import os
import requests
from typing import Dict, Tuple, Optional
from datetime import datetime
import logging
from textblob import TextBlob
import numpy as np

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Analyze sentiment with multiple models and relevance weighting"""

    # Energy-specific keywords and their impact on sentiment
    BEARISH_KEYWORDS = {
        "oversupply": 0.85, "decline": 0.75, "weak": 0.70, "drop": 0.80,
        "inventory surge": 0.90, "glut": 0.85, "recession": 0.80,
        "demand destruction": 0.95, "bearish": 1.0, "crash": 0.90,
        "supply increase": 0.75, "production": 0.60, "cuts fail": 0.85
    }

    BULLISH_KEYWORDS = {
        "rally": 0.85, "surge": 0.80, "strong": 0.75, "bullish": 1.0,
        "supply cut": 0.90, "OPEC+": 0.85, "deficit": 0.80,
        "demand recovery": 0.90, "supply disruption": 0.95, "geopolitical": 0.88,
        "crisis": 0.75, "refinery": 0.65, "forecast": 0.55
    }

    ENTITY_SENSITIVITY = {
        "Saudi Arabia": 1.0, "Russia": 0.95, "Iran": 0.90,
        "Strait of Hormuz": 1.0, "SPR": 0.80, "OPEC": 0.85,
        "Iraq": 0.80, "UAE": 0.85, "Venezuela": 0.75,
        "Nigeria": 0.70, "Libya": 0.80, "US": 0.70,
        "China": 0.75, "India": 0.70, "Europe": 0.70
    }

    @staticmethod
    def analyze_vader(text: str) -> Tuple[float, str]:
        """
        Use TextBlob (built on VADER) for quick sentiment analysis
        Returns: (score -1 to 1, label)
        """
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1 (negative) to 1 (positive)
            
            if polarity > 0.1:
                return polarity, "positive"
            elif polarity < -0.1:
                return polarity, "negative"
            else:
                return polarity, "neutral"
        except Exception as e:
            logger.error(f"VADER analysis error: {e}")
            return 0.0, "neutral"

    @staticmethod
    def analyze_finbert(text: str) -> Tuple[float, str]:
        """
        Use FinBERT from Hugging Face for financial sentiment
        Returns: (score -1 to 1, label)
        """
        hf_token = os.getenv("HF_API_KEY")
        if not hf_token:
            logger.warning("HF_API_KEY not set for FinBERT analysis")
            return 0.0, "neutral"

        try:
            API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"
            headers = {"Authorization": f"Bearer {hf_token}"}
            
            # Truncate to 512 tokens max for model
            truncated_text = text[:512]
            response = requests.post(
                API_URL,
                headers=headers,
                json={"inputs": truncated_text},
                timeout=10,
            )

            if response.status_code != 200:
                # Handle rate limiting and service errors gracefully
                if response.status_code in (429, 503):
                    logger.warning(f"FinBERT service rate-limited or unavailable: {response.status_code}")
                else:
                    logger.error(f"FinBERT returned status {response.status_code}: {response.text}")
                return 0.0, "neutral"

            results = response.json()
            # Hugging Face inference can return either:
            # - a list of label dicts: [{"label": "POSITIVE", "score": 0.9}, ...]
            # - or a list containing a list of dicts in some provider wrappers: [[{...}]]
            # Normalize to a flat list of {label, score}
            flat = []
            if isinstance(results, list) and results:
                if isinstance(results[0], dict) and "label" in results[0]:
                    flat = results
                elif isinstance(results[0], list):
                    # nested list
                    for item in results[0]:
                        if isinstance(item, dict) and "label" in item:
                            flat.append(item)
            elif isinstance(results, dict):
                # Some wrappers return a dict with scores
                if "scores" in results and isinstance(results["scores"], list):
                    flat = [s for s in results["scores"] if isinstance(s, dict) and "label" in s]

            if flat:
                scores = {item["label"].lower(): float(item.get("score", 0.0)) for item in flat}

                positive = scores.get("positive", 0.0)
                negative = scores.get("negative", 0.0)
                neutral = scores.get("neutral", 0.0)

                # Convert to -1 to 1 scale
                score = positive - negative

                if positive > 0.5:
                    return score, "positive"
                elif negative > 0.5:
                    return score, "negative"
                else:
                    return 0.0, "neutral"
        except requests.exceptions.Timeout:
            logger.warning("FinBERT request timeout")
        except Exception as e:
            logger.error(f"FinBERT analysis error: {e}")

        return 0.0, "neutral"

    @staticmethod
    def extract_entities(text: str) -> list:
        """Extract geopolitical and market entities from text"""
        entities = []
        text_lower = text.lower()
        
        for entity in SentimentAnalyzer.ENTITY_SENSITIVITY.keys():
            if entity.lower() in text_lower:
                entities.append(entity)
        
        return entities

    @staticmethod
    def calculate_relevance_score(
        text: str, entities: list, keywords_found: int
    ) -> float:
        """
        Calculate relevance score for energy market (0 to 1)
        Considers entity importance and keyword density
        """
        relevance = 0.0
        
        # Entity sensitivity contribution (up to 0.6)
        if entities:
            max_sensitivity = max(
                SentimentAnalyzer.ENTITY_SENSITIVITY.get(e, 0.5) for e in entities
            )
            relevance += min(0.6, max_sensitivity * len(entities) * 0.15)
        
        # Keyword density (up to 0.4)
        text_length = len(text.split())
        keyword_density = keywords_found / max(text_length, 1)
        relevance += min(0.4, keyword_density * 5)
        
        return min(1.0, relevance)

    @staticmethod
    def analyze_complete(text: str, title: str = "") -> Dict:
        """
        Complete sentiment analysis pipeline
        Combines VADER + FinBERT with energy-specific weighting
        """
        full_text = f"{title}. {text}" if title else text
        
        # Get both sentiment analyses
        vader_score, vader_label = SentimentAnalyzer.analyze_vader(full_text)
        finbert_score, finbert_label = SentimentAnalyzer.analyze_finbert(full_text)
        
        # Extract entities
        entities = SentimentAnalyzer.extract_entities(full_text)
        
        # Count energy-specific keywords
        text_lower = full_text.lower()
        bearish_count = sum(1 for kw in SentimentAnalyzer.BEARISH_KEYWORDS if kw in text_lower)
        bullish_count = sum(1 for kw in SentimentAnalyzer.BULLISH_KEYWORDS if kw in text_lower)
        total_keywords = bearish_count + bullish_count
        
        # Calculate weighted sentiment (average of VADER and FinBERT)
        combined_score = (vader_score * 0.4 + finbert_score * 0.6)
        
        # Boost for energy-specific keywords
        if total_keywords > 0:
            keyword_sentiment = (bullish_count - bearish_count) / total_keywords * 0.3
            combined_score = combined_score * 0.7 + keyword_sentiment * 0.3
        
        # Determine final label
        if combined_score > 0.15:
            final_label = "positive"
        elif combined_score < -0.15:
            final_label = "negative"
        else:
            final_label = "neutral"
        
        # Calculate relevance
        relevance = SentimentAnalyzer.calculate_relevance_score(
            full_text, entities, total_keywords
        )
        
        return {
            "vader_score": float(vader_score),
            "vader_label": vader_label,
            "finbert_score": float(finbert_score),
            "finbert_label": finbert_label,
            "combined_score": float(combined_score),
            "label": final_label,
            "relevance_score": float(relevance),
            "entities": entities,
            "keyword_count": total_keywords,
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    # Test the analyzer
    test_text = "OPEC+ announced supply cuts, boosting oil prices amid supply concerns and geopolitical tensions in the Middle East"
    result = SentimentAnalyzer.analyze_complete(test_text)
    print(result)
