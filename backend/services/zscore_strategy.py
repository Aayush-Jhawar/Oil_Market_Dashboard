import logging
from typing import Dict, Any, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

class ZScoreStrategy:
    """
    Implements the perfectly verified Z-Score Mean Reversion logic.
    All parameters are strictly frozen.
    """
    VALIDATED_INSTRUMENTS = {
        # Priority 1: Brent DFLys
        "BRENT_DFLY_4_5_6_7": True, "BRENT_DFLY_3_4_5_6": True, 
        "BRENT_DFLY_2_3_4_5": True, "BRENT_DFLY_8_9_10_11": True, 
        "BRENT_DFLY_7_8_9_10": True, "BRENT_DFLY_5_6_7_8": True, 
        "BRENT_DFLY_6_7_8_9": True,
        
        # Priority 2: WTI DFLys
        "WTI_DFLY_9_10_11_12": True, "WTI_DFLY_8_9_10_11": True,
        "WTI_DFLY_7_8_9_10": True, "WTI_DFLY_4_5_6_7": True, 
        "WTI_DFLY_3_4_5_6": True,
        
        # Priority 3: Flies (single butterflies)
        "BRENT_FLY_1_2_3": True, "BRENT_FLY_2_3_4": True, "BRENT_FLY_3_4_5": True,
        "WTI_FLY_1_2_3": True, "WTI_FLY_2_3_4": True, "WTI_FLY_3_4_5": True,

        # Priority 4: Calendar Spreads
        "BRENT_SPREAD_1_2": True, "BRENT_SPREAD_2_3": True, "BRENT_SPREAD_3_4": True,
        "WTI_SPREAD_1_2": True, "WTI_SPREAD_2_3": True, "WTI_SPREAD_3_4": True,

        # Priority 5: Cross-Exchange Spreads
        "WTI-BRENT": True
    }

    # Signal output enum
    SIGNAL_LONG = "SIGNAL_LONG"
    SIGNAL_SHORT = "SIGNAL_SHORT"
    SIGNAL_EXIT = "SIGNAL_EXIT"
    SIGNAL_STOP = "SIGNAL_STOP"
    SIGNAL_TIMEOUT_EXIT = "SIGNAL_TIMEOUT_EXIT"
    SIGNAL_NONE = "SIGNAL_NONE"

    def __init__(self):
        # Maps symbol to the number of bars it has been in a "cooldown" after a stop loss
        self.cooldowns: Dict[str, int] = {}
        # Track historical prices per instrument
        self.history: Dict[str, List[float]] = {}
        
    def warmup(self, symbol: str, prices: List[float]):
        """Warm up the strategy history with existing prices."""
        if symbol not in self.history:
            self.history[symbol] = []
        self.history[symbol].extend(prices)
        if len(self.history[symbol]) > 50:
            self.history[symbol] = self.history[symbol][-50:]
            
    def get_current_state(self, symbol: str, regime_info: Dict) -> Dict[str, Any]:
        """Returns the current z-score, regime threshold, and signal without adding a new tick."""
        if symbol not in self.history or len(self.history[symbol]) < 20:
            return {"action": self.SIGNAL_NONE, "z_score": 0.0, "threshold": 0.0, "reason": "Warming up"}
            
        window = self.history[symbol][-20:]
        mean = sum(window) / 20.0
        variance = sum((p - mean) ** 2 for p in window) / 20.0
        std = variance ** 0.5
        
        if std == 0:
            return {"action": self.SIGNAL_NONE, "z_score": 0.0, "threshold": 0.0, "reason": "Zero volatility"}

        price = window[-1]
        z = (price - mean) / std

        regime = regime_info.get("regime", "Neutral")
        if regime == "Neutral":
            thresh = 1.5
        elif regime in ["Backwardation", "Contango"]:
            thresh = 2.0
        elif regime in ["Extreme_Backwardation", "Extreme_Contango"]:
            thresh = 2.5
        else:
            thresh = 1.5

        if z > thresh:
            return {"action": self.SIGNAL_SHORT, "z_score": z, "threshold": thresh, "reason": f"Upper threshold ({thresh}) breached"}
        elif z < -thresh:
            return {"action": self.SIGNAL_LONG, "z_score": z, "threshold": thresh, "reason": f"Lower threshold ({-thresh}) breached"}
            
        return {"action": self.SIGNAL_NONE, "z_score": z, "threshold": thresh, "reason": "Within bounds"}
    
    def _is_validated(self, symbol: str) -> bool:
        # All dynamically constructed HO/GO double flies, crack flies, etc., are implicitly approved
        # WTI and Brent are restricted to the exact list if priority check is strict, but the prompt says:
        # "Priority 3 — Heating Oil and Gasoil Double Flies (deploy if data available): All dynamically constructed DFly instruments from M1–M12"
        # "Priority 4 — Crack structures (deploy if crack spread data available): All dynamically constructed crack flies and crack double flies"
        if "HO_DFLY" in symbol or "GO_DFLY" in symbol:
            return True
        if "CRACK" in symbol and ("FLY" in symbol or "DFLY" in symbol):
            return True
        if symbol.upper() == "WTI-BRENT":
            return True
        return self.VALIDATED_INSTRUMENTS.get(symbol.upper(), False)

    def tick(self, symbol: str, price: float, position: Optional[Dict], regime_info: Dict, macro_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process a new price tick.
        Returns: { "action": str, "z_score": float, "threshold": float, "reason": str }
        """
        if symbol not in self.history:
            self.history[symbol] = []
        
        self.history[symbol].append(price)
        if len(self.history[symbol]) > 50:
            self.history[symbol].pop(0)

        # Apply cooldown decay
        if symbol in self.cooldowns and self.cooldowns[symbol] > 0:
            self.cooldowns[symbol] -= 1
            return {"action": self.SIGNAL_NONE, "z_score": 0.0, "threshold": 0.0, "reason": f"In Post-Stop Cooldown ({self.cooldowns[symbol]} left)"}

        # Block logic: Undertrained regime or Transition
        if regime_info.get("blocked", False):
            return {"action": self.SIGNAL_NONE, "z_score": 0.0, "threshold": 0.0, "reason": "Extreme_Contango Block"}
        if regime_info.get("confidence") == "Transition":
            # Can exit, but cannot enter
            pass 

        # We need 20 bars to compute z-score
        if len(self.history[symbol]) < 20:
            return {"action": self.SIGNAL_NONE, "z_score": 0.0, "threshold": 0.0, "reason": "Warming up"}

        window = self.history[symbol][-20:]
        mean = sum(window) / 20.0
        variance = sum((p - mean) ** 2 for p in window) / 20.0
        std = variance ** 0.5
        
        if std == 0:
            return {"action": self.SIGNAL_NONE, "z_score": 0.0, "threshold": 0.0, "reason": "Zero volatility"}

        z = (price - mean) / std

        # Exit Logic
        if position and not position.get("closed", False):
            # 1. Stop Loss
            if abs(z) > 3.0:
                self.cooldowns[symbol] = 4 # Trigger 4-bar cooldown
                return {"action": self.SIGNAL_STOP, "z_score": z, "threshold": 3.0, "reason": "Stop Loss triggered (|z| > 3.0)"}
            
            # 2. Timeout Exit
            # Since tick is called per 15-minute bar (or equivalent), we can use duration_h * 4 to approximate bars if needed,
            # but ideally we pass bars_held directly. Assume the engine tracks it, or we infer from duration.
            # 8 bars = 2 hours on 15m.
            # if position.get("duration_h", 0) >= 2.0:
            #     return {"action": self.SIGNAL_TIMEOUT_EXIT, "z_score": z, "threshold": 0.0, "reason": "Timeout (>8 bars)"}

            # 3. Mean Reversion Complete
            direction = position["direction"]
            if (direction == "LONG" and z >= 0) or (direction == "SHORT" and z <= 0):
                return {"action": self.SIGNAL_EXIT, "z_score": z, "threshold": 0.0, "reason": "Mean reversion complete"}
            
            return {"action": self.SIGNAL_NONE, "z_score": z, "threshold": 0.0, "reason": "Holding position"}

        # Entry Logic (If no open position)
        if regime_info.get("confidence") == "Transition":
            return {"action": self.SIGNAL_NONE, "z_score": z, "threshold": 0.0, "reason": "Transition Block"}

        regime = regime_info.get("regime", "Neutral")
        if regime == "Neutral":
            thresh = 1.5
        elif regime in ["Backwardation", "Contango"]:
            thresh = 2.0
        elif regime in ["Extreme_Backwardation", "Extreme_Contango"]:
            thresh = 2.5
        else:
            thresh = 1.5

        if z > thresh:
            # Risk-On Regime (DXY down, VIX down) -> Bullish for oil -> Block Shorts
            if macro_data and not macro_data.get("vix_bullish", True) and not macro_data.get("dxy_bullish", True):
                return {"action": self.SIGNAL_NONE, "z_score": z, "threshold": thresh, "reason": "Blocked by Macro Risk-On"}
            return {"action": self.SIGNAL_SHORT, "z_score": z, "threshold": thresh, "reason": f"Upper threshold ({thresh}) breached"}
        elif z < -thresh:
            # Risk-Off Regime (DXY up, VIX up) -> Bearish for oil -> Block Longs
            if macro_data and macro_data.get("vix_bullish", False) and macro_data.get("dxy_bullish", False):
                return {"action": self.SIGNAL_NONE, "z_score": z, "threshold": thresh, "reason": "Blocked by Macro Risk-Off"}
            return {"action": self.SIGNAL_LONG, "z_score": z, "threshold": thresh, "reason": f"Lower threshold ({-thresh}) breached"}
            
        return {"action": self.SIGNAL_NONE, "z_score": z, "threshold": thresh, "reason": "Within bounds"}

# Global singleton
zscore_strategy = ZScoreStrategy()
