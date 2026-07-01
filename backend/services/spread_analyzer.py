"""
Spread Analysis and Anomaly Detection for Energy Markets
Calculates inter-commodity spreads, historical comparisons, and detects anomalies
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import statistics
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)


class SpreadCalculator:
    """Calculate and analyze energy market spreads"""

    # Common spreads in oil markets
    SPREAD_DEFINITIONS = {
        # Crude spreads
        "BRENT-WTI": {
            "formula": "Brent - WTI",
            "components": [("Brent", 1), ("WTI", -1)],
            "unit": "USD/bbl",
            "description": "Brent-WTI spread",
            "importance": 0.95
        },
        "DUBAI-WTI": {
            "formula": "DUBAICRUDE - WTI",
            "components": [("DUBAICRUDE", 1), ("WTI", -1)],
            "unit": "USD/bbl",
            "description": "Dubai-WTI spread",
            "importance": 0.85
        },
        
        # Crack spreads (refinery margins in USD/bbl)
        "3-2-1CRACK": {
            "formula": "(2*RBOB + 1*HO)/3 - Brent",
            "components": [("RBOB", 2.0/3.0), ("HO", 1.0/3.0), ("Brent", -1.0)],
            "unit": "USD/bbl",
            "description": "3-2-1 Crack Spread (Brent basis)",
            "importance": 0.98
        },

        "WTI-CRACK": {
            "formula": "0.42*RBOB + 0.58*HO - WTI",
            "components": [("RBOB", 0.42), ("HO", 0.58), ("WTI", -1.0)],
            "unit": "USD/bbl",
            "description": "WTI Crack Spread",
            "importance": 0.92,
        },
        
        # Product spreads
        "GASCRACK": {
            "formula": "RBOB - WTI",
            "components": [("RBOB", 1.0), ("WTI", -1.0)],
            "unit": "USD/bbl",
            "description": "Gasoline Crack",
            "importance": 0.90
        },
        "DIESELCRACK": {
            "formula": "HO - WTI",
            "components": [("HO", 1.0), ("WTI", -1.0)],
            "unit": "USD/bbl",
            "description": "Diesel Crack",
            "importance": 0.90
        },
        "GASOILCRACK": {
            "formula": "GO - Brent",
            "components": [("GO", 1.0), ("Brent", -1.0)],
            "unit": "USD/bbl",
            "description": "Gasoil Crack (ICE gasoil vs Brent — European diesel margin)",
            "importance": 0.88
        },
        "FRAC": {
            "formula": "HO/HH ratio",
            "components": [("HO", 1), ("HH", 1)],
            "type": "ratio",
            "unit": "ratio",
            "description": "Heating Oil / Natural Gas Ratio",
            "importance": 0.75
        },
    }

    def __init__(self, history_length: int = 252):
        """Initialize with history buffer (default 1 year of trading days)"""
        self.history = deque(maxlen=history_length)
        self.price_history = {}

    def add_price_data(self, prices: Dict[str, float], timestamp: datetime = None):
        """Add current prices to history"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.history.append({
            "timestamp": timestamp,
            "prices": prices.copy()
        })
        
        # Track individual prices
        for symbol, price in prices.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=252)
            self.price_history[symbol].append((timestamp, price))

    def calculate_spread(
        self, spread_name: str, prices: Dict[str, float]
    ) -> Optional[float]:
        """Calculate a single spread from current prices"""
        if spread_name not in self.SPREAD_DEFINITIONS:
            logger.error(f"Unknown spread: {spread_name}")
            return None
        
        definition = self.SPREAD_DEFINITIONS[spread_name]
        spread_type = definition.get("type", "linear")
        
        if spread_type == "ratio":
            # Assume exact 2 components for ratio: A / B
            comp1_sym = definition["components"][0][0]
            comp2_sym = definition["components"][1][0]
            
            p1 = prices.get(comp1_sym)
            p1 = p1.get("close") if isinstance(p1, dict) else p1
            p2 = prices.get(comp2_sym)
            p2 = p2.get("close") if isinstance(p2, dict) else p2
            
            if p1 is None or p2 is None or p2 == 0:
                return None
                
            spread_value = p1 / p2
        else:
            spread_value = 0.0
            for symbol, weight in definition["components"]:
                price_entry = prices.get(symbol)
                if price_entry is None:
                    logger.debug(f"Missing price for {symbol} in spread {spread_name}")
                    return None
                price = price_entry.get("close") if isinstance(price_entry, dict) else price_entry
                if price is None:
                    logger.debug(f"Missing close price for {symbol} in spread {spread_name}")
                    return None
                spread_value += price * weight
            
            # Apply multiplier if defined (e.g., for crack spreads)
            if "multiplier" in definition:
                spread_value *= definition["multiplier"]
        
        return spread_value

    def calculate_all_spreads(self, prices: Dict[str, Dict]) -> Dict[str, Dict]:
        """Calculate all spreads and their statistics"""
        spreads = {}
        
        # Pull Kalman Z-Scores from trade_recommendations
        kalman_zscores = {}
        try:
            import sqlite3
            import json
            import os
            db_path = os.path.join(os.path.dirname(__file__), "..", "energy.db")
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT symbol, explanation_json FROM trade_recommendations WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC"
                )
                rows = cursor.fetchall()
                for row in rows:
                    sym, explanation = row
                    if sym not in kalman_zscores and explanation:
                        try:
                            exp_data = json.loads(explanation)
                            if "rationale" in exp_data and "Z-Score:" in exp_data["rationale"]:
                                z_str = exp_data["rationale"].split("Z-Score:")[1].split()[0]
                                kalman_zscores[sym] = float(z_str)
                        except Exception:
                            pass
                conn.close()
        except Exception as e:
            logger.error(f"Error pulling Kalman z-scores: {e}")
            
        for spread_name in self.SPREAD_DEFINITIONS:
            value = self.calculate_spread(spread_name, prices)
            
            if value is None:
                continue
            
            # Get historical data for this spread
            hist_values = self._get_spread_history(spread_name)
            
            if not hist_values:
                stats = {
                    "value": value,
                    "mean_5d": value,
                    "mean_30d": value,
                    "mean_252d": value,
                    "std_5d": 0.0,
                    "std_30d": 0.0,
                    "zscore_5d": 0.0,
                    "zscore_30d": 0.0,
                    "min_5d": value,
                    "max_5d": value,
                    "percentile_5d": 50,
                }
            else:
                stats = self._calculate_statistics(value, hist_values, spread_name)
                
            # Overwrite naive Z-score with Kalman Filter Z-score if available
            if spread_name in kalman_zscores:
                stats["zscore_5d"] = kalman_zscores[spread_name]
            elif spread_name == "GASCRACK" and "GASCRACK" in kalman_zscores:
                 stats["zscore_5d"] = kalman_zscores["GASCRACK"]
            
            spreads[spread_name] = stats
        
        return spreads

    def _get_spread_history(self, spread_name: str) -> List[float]:
        """Get historical values for a spread"""
        values = []
        
        for entry in self.history:
            value = self.calculate_spread(spread_name, entry["prices"])
            if value is not None:
                values.append(value)
        
        return values

    def _calculate_statistics(
        self, current_value: float, hist_values: List[float], spread_name: str
    ) -> Dict:
        """Calculate statistical measures for a spread"""
        stats = {"value": current_value}
        
        # Various period calculations
        periods = {"5d": 5, "30d": 30, "252d": 252}
        
        for period_name, period_len in periods.items():
            recent = hist_values[-period_len:] if len(hist_values) >= period_len else hist_values
            
            if recent:
                mean = statistics.mean(recent)
                std = statistics.stdev(recent) if len(recent) > 1 else 0.0
                
                stats[f"mean_{period_name}"] = mean
                stats[f"std_{period_name}"] = std
                
                # Z-score: (value - mean) / std
                if std > 1e-6:
                    zscore = (current_value - mean) / std
                else:
                    zscore = 0.0
                
                stats[f"zscore_{period_name}"] = zscore
                stats[f"min_{period_name}"] = min(recent)
                stats[f"max_{period_name}"] = max(recent)
                
                # Percentile rank
                count_below = sum(1 for v in recent if v <= current_value)
                percentile = (count_below / len(recent)) * 100
                stats[f"percentile_{period_name}"] = percentile
        
        return stats

    def detect_anomalies(self, spreads: Dict[str, Dict]) -> List[Dict]:
        """Detect anomalies in spreads based on z-scores"""
        anomalies = []
        
        for spread_name, stats in spreads.items():
            # Check 5-day z-score for sharp moves
            zscore_5d = stats.get("zscore_5d", 0)
            zscore_30d = stats.get("zscore_30d", 0)
            
            # Anomaly if > 2 standard deviations from mean
            if abs(zscore_5d) > 2.0:
                severity = "critical" if abs(zscore_5d) > 3.0 else "warning"
                direction = "unusually high" if zscore_5d > 0 else "unusually low"
                
                anomalies.append({
                    "spread": spread_name,
                    "type": "volatility_spike",
                    "severity": severity,
                    "message": f"{spread_name} is {direction} ({zscore_5d:.2f}σ from 5-day mean)",
                    "value": stats["value"],
                    "zscore_5d": zscore_5d,
                    "zscore_30d": zscore_30d,
                    "mean_5d": stats.get("mean_5d"),
                    "timestamp": datetime.now().isoformat()
                })
            
            # Check for divergence between 5d and 30d trends
            if abs(zscore_5d) > 1.5 and abs(zscore_30d) < 0.5:
                anomalies.append({
                    "spread": spread_name,
                    "type": "trend_divergence",
                    "severity": "warning",
                    "message": f"{spread_name} showing short-term move, not confirmed by longer-term trend",
                    "value": stats["value"],
                    "zscore_5d": zscore_5d,
                    "zscore_30d": zscore_30d,
                    "timestamp": datetime.now().isoformat()
                })
        
        return sorted(anomalies, key=lambda x: abs(x["zscore_5d"]), reverse=True)


class AnomalyDetector:
    """Detect anomalies across price, volume, and other metrics"""

    @staticmethod
    def detect_volume_spike(
        current_volume: float, hist_volumes: List[float], multiplier: float = 1.5
    ) -> Tuple[bool, str]:
        """Detect if current volume is unusually high"""
        if not hist_volumes or len(hist_volumes) < 5:
            return False, ""
        
        avg_volume = statistics.mean(hist_volumes[-20:])
        
        if current_volume > avg_volume * multiplier:
            pct_above = ((current_volume / avg_volume) - 1) * 100
            return True, f"Volume {pct_above:.1f}% above average"
        
        return False, ""

    @staticmethod
    def detect_price_gap(
        current_price: float, prev_close: float, threshold_pct: float = 3.0
    ) -> Tuple[bool, str]:
        """Detect gap moves in price"""
        if prev_close == 0:
            return False, ""
        
        gap_pct = abs((current_price - prev_close) / prev_close) * 100
        
        if gap_pct > threshold_pct:
            direction = "up" if current_price > prev_close else "down"
            return True, f"Gap {direction} {gap_pct:.2f}%"
        
        return False, ""

    @staticmethod
    def detect_volatility_spike(
        returns: List[float], current_return: float, threshold_std: float = 2.0
    ) -> Tuple[bool, str]:
        """Detect if volatility has spiked"""
        if not returns or len(returns) < 10:
            return False, ""
        
        std_dev = statistics.stdev(returns[-10:])
        mean_return = statistics.mean(returns[-10:])
        
        if std_dev > 0:
            zscore = abs((current_return - mean_return) / std_dev)
            if zscore > threshold_std:
                return True, f"Volatility spike: {zscore:.2f}σ move"
        
        return False, ""

    @staticmethod
    def detect_correlation_breakdown(
        prices_a: List[float], prices_b: List[float], lookback: int = 20
    ) -> Tuple[bool, str]:
        """Detect if historically correlated pairs are decoupling"""
        if len(prices_a) < lookback or len(prices_b) < lookback:
            return False, ""
        
        recent_a = prices_a[-lookback:]
        recent_b = prices_b[-lookback:]
        
        # Calculate correlation
        try:
            correlation = np.corrcoef(recent_a, recent_b)[0, 1]
            
            # If correlation suddenly dropped from historical levels
            if correlation < 0.5:
                return True, f"Pair correlation breakdown: {correlation:.2f}"
        except:
            pass
        
        return False, ""
