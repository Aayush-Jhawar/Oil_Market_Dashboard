import logging
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class RegimeClassifier:
    THRESHOLDS = {
        "WTI": {"extreme_back": 21.25, "extreme_cont": -30.00},
        "Brent": {"extreme_back": 18.43, "extreme_cont": -30.00},
        "HO": {"extreme_back": 30.73, "extreme_cont": -30.00},
        "GO": {"extreme_back": 32.32, "extreme_cont": -30.00},
    }

    # Neutral dead-band on the annualized M1-M6 roll yield (%). Above → Backwardation,
    # below the negative → Contango, in between → Neutral (flat).
    BACKWARDATION_YIELD = 2.0
    CONTANGO_YIELD = -2.0

    # Canonical UPPERCASE curve-structure vocabulary shared across the dashboard
    # (forward_curve.meta.structure, snapshot.futures.structure, /api/signals/enhanced
    # market_state.curve, and the frontend badges).
    _STRUCTURE_MAP = {
        "Extreme_Backwardation": "EXTREME_BACKWARDATION",
        "Backwardation":         "BACKWARDATION",
        "Neutral":               "FLAT",
        "Contango":              "CONTANGO",
        "Extreme_Contango":      "EXTREME_CONTANGO",
    }

    def __init__(self, state_file: str = "regime_state.json"):
        self.state_file = state_file
        # State: { symbol: { "current_regime": str, "bars_in_new_regime": int, "candidate_regime": str, "last_transition": dict } }
        self.state: Dict[str, Dict[str, Any]] = {}
        self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
            except Exception as e:
                logger.error(f"Error loading regime state: {e}")

    def save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.error(f"Error saving regime state: {e}")

    def _get_annualized_roll_yield(self, m_front_price: float, m_back_price: float, days_between: int) -> float:
        if m_front_price == 0 or days_between == 0:
            return 0.0
        return ((m_front_price - m_back_price) / m_front_price) * (365 / days_between) * 100

    @staticmethod
    def _base(symbol: str) -> str:
        """Normalize a symbol/instrument to its base commodity key."""
        base = symbol.split("_")[0]
        return "Brent" if base.upper() == "BRENT" else base

    def _raw_category(self, symbol: str, prices: Dict[int, float]) -> str:
        """Instantaneous curve-structure category from the annualized M1-M6 roll
        yield. Pure/read-only — never mutates state. Falls back to the last known
        regime (or 'Neutral') when the curve lacks the M1/M6 legs."""
        base_sym = self._base(symbol)
        m1 = prices.get(1)
        m6 = prices.get(6)
        if m1 is None or m6 is None:
            return self.state.get(base_sym, {}).get("current_regime", "Neutral")

        # M1-M6 spans ~150 days between expiries.
        yield_1_6 = self._get_annualized_roll_yield(m1, m6, 150)
        thresh = self.THRESHOLDS.get(base_sym, {"extreme_back": 20.0, "extreme_cont": -30.0})

        if yield_1_6 > thresh["extreme_back"]:
            return "Extreme_Backwardation"
        if yield_1_6 < thresh["extreme_cont"]:
            return "Extreme_Contango"
        if yield_1_6 > self.BACKWARDATION_YIELD:
            return "Backwardation"
        if yield_1_6 < self.CONTANGO_YIELD:
            return "Contango"
        return "Neutral"

    def classify(self, symbol: str, prices: Dict[int, float]) -> Dict[str, Any]:
        """
        prices is a dict mapping month index (1, 2, 6, 12) to price.

        Stateful: advances the 4-bar hysteresis machine and persists regime_state.json.
        Call this ONLY from the periodic publishers — display/REST paths must use the
        read-only structure_for()/current_regime() accessors instead.
        """
        base_sym = self._base(symbol)

        m1 = prices.get(1)
        m2 = prices.get(2)
        m6 = prices.get(6)

        if m1 is None or m6 is None:
            return self._fallback_regime(base_sym)

        # M1-M6 ~150 days, M1-M2 ~30 days between expiries.
        yield_1_6 = self._get_annualized_roll_yield(m1, m6, 150)
        raw_regime = self._raw_category(symbol, prices)

        # Check disagreement with M1-M2 (sign check)
        disagree = False
        if m2 is not None:
            yield_1_2 = self._get_annualized_roll_yield(m1, m2, 30)
            if (yield_1_6 > 0 and yield_1_2 < 0) or (yield_1_6 < 0 and yield_1_2 > 0):
                disagree = True

        return self._update_state(base_sym, raw_regime, disagree, yield_1_6)

    @classmethod
    def to_structure(cls, regime_label: Optional[str]) -> str:
        """Normalize an internal Title_Case regime label to the canonical UPPERCASE
        curve-structure vocabulary used across the dashboard. Empty/None → 'UNKNOWN'."""
        if not regime_label or regime_label == "INITIALIZING":
            return "UNKNOWN"
        return cls._STRUCTURE_MAP.get(regime_label, regime_label.upper())

    def current_regime(self, symbol: str) -> Optional[str]:
        """Persisted (hysteresis-smoothed) Title_Case regime for the symbol, or None."""
        return self.state.get(self._base(symbol), {}).get("current_regime")

    def structure_for(self, symbol: str, prices: Dict[int, float]) -> str:
        """Single source of truth for a symbol's curve-structure label (UPPERCASE
        display form). Prefers the persisted, hysteresis-smoothed regime advanced by
        the periodic publishers; falls back to an instantaneous, read-only M1-M6
        classification when no state exists yet. NEVER mutates/persists state, so it is
        safe to call from display / REST / websocket-snapshot paths."""
        label = self.current_regime(symbol)
        if not label:
            label = self._raw_category(symbol, prices)
        return self.to_structure(label)

    def _fallback_regime(self, symbol: str) -> Dict[str, Any]:
        s = self.state.get(symbol, {"current_regime": "Neutral"})
        return {
            "regime": s["current_regime"],
            "confidence": "Low",
            "roll_yield": 0.0,
            "blocked": (s["current_regime"] == "Extreme_Contango")
        }

    def _update_state(self, symbol: str, raw_regime: str, disagree: bool, roll_yield: float) -> Dict[str, Any]:
        if symbol not in self.state:
            self.state[symbol] = {
                "current_regime": raw_regime,
                "bars_in_new_regime": 0,
                "candidate_regime": raw_regime,
                "last_transition": None
            }
        
        s = self.state[symbol]
        
        confidence = "High" if not disagree else "Transition"
        
        if disagree:
            # Hold current regime label
            candidate = s["current_regime"]
            s["bars_in_new_regime"] = 0
            s["candidate_regime"] = candidate
        else:
            if raw_regime != s["current_regime"]:
                if raw_regime == s["candidate_regime"]:
                    s["bars_in_new_regime"] += 1
                else:
                    s["candidate_regime"] = raw_regime
                    s["bars_in_new_regime"] = 1
                    
                if s["bars_in_new_regime"] >= 4:
                    # Execute transition
                    old_regime = s["current_regime"]
                    s["current_regime"] = raw_regime
                    s["last_transition"] = {
                        "timestamp": datetime.now().isoformat(),
                        "commodity": symbol,
                        "old_regime": old_regime,
                        "new_regime": raw_regime,
                        "roll_yield": round(roll_yield, 2)
                    }
                    logger.info(f"REGIME TRANSITION: {symbol} moved from {old_regime} to {raw_regime} at yield {roll_yield:.2f}%")
            else:
                s["bars_in_new_regime"] = 0
                s["candidate_regime"] = raw_regime
                
        self.save_state()
        
        is_blocked = (s["current_regime"] == "Extreme_Contango")
        
        return {
            "regime": s["current_regime"],
            "confidence": confidence,
            "roll_yield": round(roll_yield, 2),
            "blocked": is_blocked
        }

# Global Singleton
regime_classifier = RegimeClassifier()
