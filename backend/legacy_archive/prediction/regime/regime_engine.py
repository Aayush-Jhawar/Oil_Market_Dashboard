"""
Regime Engine — Hybrid Ensemble Classifier
=============================================
Combines rule-based classification (economic intuition) with HMM
(probabilistic state inference) to produce a robust regime determination.

Decision logic:
    - If HMM agrees with rules at >70% confidence → use both
    - If HMM disagrees but at >85% confidence → use HMM (data overrides rules)
    - If max HMM prob < 50% → TRANSITION_ZONE flag
    - Rule-based classification is always available as fallback
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from prediction.regime.rule_classifier import (
    classify_regime,
    classify_regime_from_features,
    RegimeClassification,
)
from prediction.regime.hmm_classifier import HMMRegimeClassifier

logger = logging.getLogger(__name__)


@dataclass
class RegimeState:
    """Complete regime state output."""
    regime_label: str           # CONTANGO / BACKWARDATION / NEUTRAL
    severity: float             # 0.0–1.0
    confidence: float           # 0.0–1.0 overall confidence
    method: str                 # "rule_only", "hmm_only", "hybrid"
    is_transition: bool         # True if in transition zone

    # Probabilities
    hmm_probabilities: Dict[str, float] = field(default_factory=dict)
    transition_probabilities: Dict[str, float] = field(default_factory=dict)
    
    # Regime age
    regime_age_days: int = 0

    # Similarity Engine Results
    similar_periods: List[Dict] = field(default_factory=list)

    # Explanation
    drivers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "regime_label": self.regime_label,
            "severity": self.severity,
            "confidence": self.confidence,
            "method": self.method,
            "is_transition": self.is_transition,
            "hmm_probabilities": self.hmm_probabilities,
            "transition_probabilities": self.transition_probabilities,
            "similar_periods": self.similar_periods,
            "regime_age_days": self.regime_age_days,
            "drivers": self.drivers,
        }


class RegimeEngine:
    """
    Hybrid regime detection engine combining rules and HMM.
    """

    def __init__(self):
        from prediction.regime.similarity import RegimeSimilarityEngine
        
        self.hmm = HMMRegimeClassifier()
        self.similarity = RegimeSimilarityEngine()
        self._prev_regime: Optional[str] = None
        self._regime_age: int = 0

    def fit(self, feature_matrix: pd.DataFrame, returns_series: Optional[pd.Series] = None) -> bool:
        """Train HMM and Similarity components."""
        hmm_ok = self.hmm.fit(feature_matrix)
        sim_ok = False
        if returns_series is not None:
            sim_ok = self.similarity.fit(feature_matrix, returns_series)
        return hmm_ok and sim_ok

    def load_hmm(self, filepath: Optional[str] = None) -> bool:
        """Load a pre-trained HMM."""
        return self.hmm.load(filepath)

    def save_hmm(self, filepath: Optional[str] = None):
        """Save the trained HMM."""
        self.hmm.save(filepath)

    def load_all(self) -> bool:
        """Load all regime engine components (HMM and Similarity)."""
        hmm_ok = self.load_hmm()
        sim_ok = self.similarity.load()
        return hmm_ok or sim_ok

    def save_all(self):
        """Save all regime engine components."""
        self.save_hmm()
        self.similarity.save()

    def classify(
        self,
        features: Dict[str, float],
        use_hmm: bool = True,
    ) -> RegimeState:
        """
        Classify the current regime using hybrid ensemble.

        Args:
            features: Feature dict with curve features (m1_m2_spread, etc.)
            use_hmm: Whether to use HMM (False = rule-based only)

        Returns:
            RegimeState with classification and probabilities.
        """
        # ── Step 1: Rule-based classification ─────────────────────────────
        rule_result = classify_regime_from_features(features)

        # ── Step 2: HMM classification ────────────────────────────────────
        hmm_result = None
        if use_hmm and self.hmm.is_fitted:
            hmm_result = self.hmm.predict(features)

        # ── Step 3: Ensemble decision ─────────────────────────────────────
        if hmm_result is None:
            # HMM not available — rule-based only
            final_label = rule_result.label
            final_severity = rule_result.severity
            confidence = min(0.7, rule_result.severity + 0.3)  # rules cap at 70% confidence
            method = "rule_only"
            is_transition = False
            hmm_probs = {
                "extreme_backwardation": 0.10,
                "backwardation": 0.20,
                "neutral": 0.40,
                "contango": 0.20,
                "extreme_contango": 0.10,
            }
            trans_probs = {
                "extreme_backwardation": 0.10,
                "backwardation": 0.20,
                "neutral": 0.40,
                "contango": 0.20,
                "extreme_contango": 0.10,
            }
            drivers = rule_result.drivers.copy()
        else:
            hmm_label = hmm_result.get("hmm_most_likely", "NEUTRAL")
            hmm_conf = hmm_result.get("hmm_confidence", 0.33)
            hmm_probs = hmm_result.get("probabilities", {})
            trans_probs = hmm_result.get("transitions", {})
            drivers = rule_result.drivers.copy()

            if hmm_label == rule_result.label and hmm_conf > 0.7:
                # Agreement with high confidence
                final_label = rule_result.label
                final_severity = max(rule_result.severity, hmm_conf * rule_result.severity)
                confidence = min(0.95, hmm_conf * 0.5 + rule_result.severity * 0.5)
                method = "hybrid"
                is_transition = False
                drivers.append(
                    f"HMM confirms {hmm_label} with {hmm_conf:.0%} confidence"
                )

            elif hmm_conf > 0.85 and hmm_label != rule_result.label:
                # HMM strongly disagrees — data overrides rules
                final_label = hmm_label
                final_severity = rule_result.severity * 0.5  # reduce severity on disagreement
                confidence = hmm_conf * 0.7  # discount confidence on disagreement
                method = "hmm_override"
                is_transition = True  # disagreement suggests transition
                drivers.append(
                    f"HMM overrides rules: {hmm_label} at {hmm_conf:.0%} vs "
                    f"rules={rule_result.label}"
                )

            elif max(hmm_probs.values()) < 0.5:
                # Low HMM confidence — transition zone
                final_label = rule_result.label  # use rules as anchor
                final_severity = rule_result.severity * 0.6
                confidence = max(hmm_probs.values()) * 0.5
                method = "hybrid"
                is_transition = True
                drivers.append(
                    f"Transition zone: HMM probs {hmm_probs}, max={max(hmm_probs.values()):.2f}"
                )

            else:
                # Mild disagreement or moderate HMM confidence
                final_label = rule_result.label  # rules as default
                final_severity = rule_result.severity
                confidence = min(0.7, hmm_conf * 0.3 + rule_result.severity * 0.4)
                method = "hybrid"
                is_transition = hmm_label != rule_result.label
                if is_transition:
                    drivers.append(
                        f"HMM suggests {hmm_label} ({hmm_conf:.0%}) vs "
                        f"rules={rule_result.label}"
                    )

        # ── Step 4: Track regime age ──────────────────────────────────────
        if final_label == self._prev_regime:
            self._regime_age += 1
        else:
            self._regime_age = 1
        self._prev_regime = final_label

        # ── Step 5: Similarity Search ─────────────────────────────────────
        similar_periods = self.similarity.find_similar_periods(features) if self.similarity.is_fitted else []

        return RegimeState(
            regime_label=final_label,
            severity=round(final_severity, 3),
            confidence=round(confidence, 3),
            method=method,
            is_transition=is_transition,
            hmm_probabilities=hmm_probs,
            transition_probabilities=trans_probs,
            regime_age_days=self._regime_age,
            similar_periods=similar_periods,
            drivers=drivers,
        )

    def classify_history(
        self,
        feature_matrix: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Classify regimes for the full history.

        Returns DataFrame with regime labels, severity, and age aligned to input index.
        """
        results = []

        prev_label = None
        age = 0

        for dt, row in feature_matrix.iterrows():
            features = row.to_dict()
            rule_result = classify_regime_from_features(features)

            label = rule_result.label
            severity = rule_result.severity

            if label == prev_label:
                age += 1
            else:
                age = 1
            prev_label = label

            results.append({
                "date": dt,
                "regime_label": label,
                "regime_severity": severity,
                "regime_age_days": age,
            })

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        # Overlay HMM if fitted
        if self.hmm.is_fitted:
            hmm_df = self.hmm.predict_history(feature_matrix)
            if not hmm_df.empty:
                df["hmm_regime"] = hmm_df["regime_label"]
                df["hmm_regime_age"] = hmm_df["regime_age_days"]

        return df
