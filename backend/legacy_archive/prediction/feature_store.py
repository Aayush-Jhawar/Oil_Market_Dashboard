"""
Feature Store — SQLAlchemy models and query utilities for the prediction engine.
================================================================================
Stores computed features, regime labels, predictions, and trade recommendations
in SQLite alongside the existing dashboard database.
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import Column, Float, String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Base, SessionLocal, engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLAlchemy Models
# ---------------------------------------------------------------------------

class FeatureSnapshot(Base):
    """Daily feature vector for a single date + symbol."""
    __tablename__ = "prediction_features"

    id = Column(String, primary_key=True, index=True)             # "{symbol}_{date}"
    symbol = Column(String, index=True)
    date = Column(String, index=True)                             # YYYY-MM-DD
    features_json = Column(Text)                                  # JSON blob of all features
    regime_label = Column(String, nullable=True)                  # CONTANGO / BACKWARDATION / NEUTRAL
    regime_severity = Column(Float, nullable=True)                # 0.0–1.0
    created_at = Column(DateTime, server_default=func.now())


class RegimeHistory(Base):
    """Historical regime classification record."""
    __tablename__ = "prediction_regimes"

    id = Column(String, primary_key=True, index=True)             # "{symbol}_{date}"
    symbol = Column(String, index=True)
    date = Column(String, index=True)
    regime_label = Column(String)                                 # CONTANGO / BACKWARDATION / NEUTRAL
    regime_severity = Column(Float)
    probabilities_json = Column(Text, nullable=True)              # JSON: { "CONTANGO": 0.1, "BACKWARDATION": ... }
    transitions_json = Column(Text, nullable=True)                # JSON: { "CONTANGO": 0.2, "BACKWARDATION": ... }
    regime_age_days = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    similar_periods_json = Column(Text, nullable=True)            # JSON: list of dicts with similar dates and historical returns
    created_at = Column(DateTime, server_default=func.now())


class Prediction(Base):
    """Model prediction record."""
    __tablename__ = "predictions"

    id = Column(String, primary_key=True, index=True)             # "{symbol}_{date}_{horizon}_{target}"
    symbol = Column(String, index=True)
    date = Column(String, index=True)                             # Date prediction was made
    horizon_days = Column(Integer)                                # 1, 5, or 21
    target = Column(String)                                       # "direction", "return", "spread", etc.
    prediction_value = Column(Float)                              # Predicted value or probability
    prediction_label = Column(String, nullable=True)              # "UP" / "DOWN" / "NEUTRAL"
    confidence = Column(Float, nullable=True)
    ci_lower = Column(Float, nullable=True)                       # 95% confidence interval
    ci_upper = Column(Float, nullable=True)
    model_version = Column(String, nullable=True)
    actual_value = Column(Float, nullable=True)                   # Filled in after horizon passes
    actual_label = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class TradeRecommendation(Base):
    """Generated trade recommendation."""
    __tablename__ = "trade_recommendations"

    id = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    date = Column(String, index=True)
    direction = Column(String)                                    # LONG / SHORT / NO_TRADE
    conviction = Column(String)                                   # HIGH / MEDIUM / LOW
    instrument = Column(String)                                   # "WTI M1", "WTI M1-M2 Calendar"
    trade_type = Column(String, nullable=True)                    # OUTRIGHT / SPREAD / FLY
    entry_low = Column(Float, nullable=True)
    entry_high = Column(Float, nullable=True)
    target_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    risk_reward_ratio = Column(Float, nullable=True)
    position_size_pct = Column(Float, nullable=True)
    max_holding_days = Column(Integer, nullable=True)
    current_spread = Column(Float, nullable=True)
    target_spread = Column(Float, nullable=True)
    stop_spread = Column(Float, nullable=True)
    expected_change = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    explanation_json = Column(Text, nullable=True)                # JSON blob of explanation
    regime_label = Column(String, nullable=True)
    regime_severity = Column(Float, nullable=True)
    # Outcome tracking
    exit_price = Column(Float, nullable=True)
    exit_date = Column(String, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    outcome = Column(String, nullable=True)                       # WIN / LOSS / SCRATCH / OPEN
    created_at = Column(DateTime, server_default=func.now())


class ModelMetadata(Base):
    """Trained model metadata and performance tracking."""
    __tablename__ = "model_metadata"

    id = Column(String, primary_key=True, index=True)
    model_name = Column(String, index=True)
    model_version = Column(String)
    trained_at = Column(DateTime)
    training_end_date = Column(String)                            # Latest date in training set
    n_training_samples = Column(Integer)
    n_features = Column(Integer)
    hyperparameters_json = Column(Text, nullable=True)
    # Walk-forward metrics
    wf_accuracy = Column(Float, nullable=True)
    wf_precision_high_conf = Column(Float, nullable=True)
    wf_sharpe = Column(Float, nullable=True)
    wf_brier_score = Column(Float, nullable=True)
    # Feature importance
    top_features_json = Column(Text, nullable=True)               # Top 20 features + importance
    regime_metrics_json = Column(Text, nullable=True)             # Per-regime performance
    created_at = Column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Query utilities
# ---------------------------------------------------------------------------

def get_feature_snapshots(
    symbol: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Load feature snapshots for a symbol and date range into a DataFrame."""
    import json
    db = SessionLocal()
    try:
        rows = (
            db.query(FeatureSnapshot)
            .filter(
                FeatureSnapshot.symbol == symbol,
                FeatureSnapshot.date >= start_date,
                FeatureSnapshot.date <= end_date,
            )
            .order_by(FeatureSnapshot.date)
            .all()
        )
        if not rows:
            return pd.DataFrame()

        records = []
        for r in rows:
            feat = json.loads(r.features_json) if r.features_json else {}
            feat["date"] = r.date
            feat["regime_label"] = r.regime_label
            feat["regime_severity"] = r.regime_severity
            records.append(feat)

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        return df
    finally:
        db.close()


def save_feature_snapshot(
    symbol: str,
    dt: str,
    features: Dict[str, float],
    regime_label: Optional[str] = None,
    regime_severity: Optional[float] = None,
) -> None:
    """Persist a single feature snapshot."""
    import json
    db = SessionLocal()
    try:
        snap = FeatureSnapshot(
            id=f"{symbol}_{dt}",
            symbol=symbol,
            date=dt,
            features_json=json.dumps(features, default=str),
            regime_label=regime_label,
            regime_severity=regime_severity,
        )
        db.merge(snap)
        db.commit()
    except Exception as e:
        logger.error(f"Error saving feature snapshot: {e}")
        db.rollback()
    finally:
        db.close()


def save_regime_record(symbol: str, dt: str, regime_data: Dict) -> None:
    """Persist a regime classification record."""
    db = SessionLocal()
    try:
        import json
        rec = RegimeHistory(
            id=f"{symbol}_{dt}",
            symbol=symbol,
            date=dt,
            regime_label=regime_data.get("regime_label", "NEUTRAL"),
            regime_severity=regime_data.get("severity", 0.0),
            probabilities_json=json.dumps(regime_data.get("hmm_probabilities", {})),
            transitions_json=json.dumps(regime_data.get("transition_probabilities", {})),
            similar_periods_json=json.dumps(regime_data.get("similar_periods", [])),
            regime_age_days=regime_data.get("regime_age_days"),
            confidence=regime_data.get("confidence"),
        )
        db.merge(rec)
        db.commit()
    except Exception as e:
        logger.error(f"Error saving regime record: {e}")
        db.rollback()
    finally:
        db.close()


def save_prediction(symbol: str, dt: str, pred_data: Dict) -> None:
    """Persist a prediction record."""
    db = SessionLocal()
    try:
        horizon = pred_data.get("horizon_days", 5)
        target = pred_data.get("target", "direction")
        rec = Prediction(
            id=f"{symbol}_{dt}_{horizon}_{target}",
            symbol=symbol,
            date=dt,
            horizon_days=horizon,
            target=target,
            prediction_value=pred_data.get("prediction_value"),
            prediction_label=pred_data.get("prediction_label"),
            confidence=pred_data.get("confidence"),
            ci_lower=pred_data.get("ci_lower"),
            ci_upper=pred_data.get("ci_upper"),
            model_version=pred_data.get("model_version"),
        )
        db.merge(rec)
        db.commit()
    except Exception as e:
        logger.error(f"Error saving prediction: {e}")
        db.rollback()
    finally:
        db.close()


def save_trade_recommendation(symbol: str, dt: str, trade_data: Dict) -> None:
    """Persist a trade recommendation."""
    import json
    db = SessionLocal()
    try:
        rec = TradeRecommendation(
            id=f"{symbol}_{dt}_{trade_data.get('instrument', 'M1')}",
            symbol=symbol,
            date=dt,
            direction=trade_data.get("direction", "NO_TRADE"),
            conviction=trade_data.get("conviction", "LOW"),
            instrument=trade_data.get("instrument", f"{symbol} M1"),
            trade_type=trade_data.get("trade_type"),
            entry_low=trade_data.get("entry_low"),
            entry_high=trade_data.get("entry_high"),
            target_price=trade_data.get("target_price"),
            stop_loss=trade_data.get("stop_loss"),
            risk_reward_ratio=trade_data.get("risk_reward_ratio"),
            position_size_pct=trade_data.get("position_size_pct"),
            max_holding_days=trade_data.get("max_holding_days"),
            current_spread=trade_data.get("current_spread"),
            target_spread=trade_data.get("target_spread"),
            stop_spread=trade_data.get("stop_spread"),
            expected_change=trade_data.get("expected_change"),
            confidence=trade_data.get("confidence"),
            explanation_json=json.dumps(trade_data.get("explanation", {}), default=str),
            regime_label=trade_data.get("regime_label"),
            regime_severity=trade_data.get("regime_severity"),
        )
        db.merge(rec)
        db.commit()
    except Exception as e:
        logger.error(f"Error saving trade recommendation: {e}")
        db.rollback()
    finally:
        db.close()


def get_recent_predictions(
    symbol: str,
    n_days: int = 30,
    target: Optional[str] = None,
) -> List[Dict]:
    """Get recent predictions with actual outcomes where available."""
    db = SessionLocal()
    try:
        q = (
            db.query(Prediction)
            .filter(Prediction.symbol == symbol)
            .order_by(Prediction.date.desc())
        )
        if target:
            q = q.filter(Prediction.target == target)
        rows = q.limit(n_days).all()
        return [
            {
                "date": r.date,
                "horizon_days": r.horizon_days,
                "target": r.target,
                "prediction_value": r.prediction_value,
                "prediction_label": r.prediction_label,
                "confidence": r.confidence,
                "actual_value": r.actual_value,
                "actual_label": r.actual_label,
                "is_correct": r.is_correct,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_recent_trade_recommendations(
    symbol: str = None,
    n_days: int = 30,
) -> List[Dict]:
    """Get recent trade recommendations."""
    import json
    db = SessionLocal()
    try:
        q = db.query(TradeRecommendation).order_by(TradeRecommendation.date.desc())
        if symbol:
            q = q.filter(TradeRecommendation.symbol == symbol)
        rows = q.limit(n_days).all()
        results = []
        for r in rows:
            explanation = {}
            if r.explanation_json:
                try:
                    explanation = json.loads(r.explanation_json)
                except Exception:
                    pass
            results.append({
                "date": r.date,
                "symbol": r.symbol,
                "direction": r.direction,
                "conviction": r.conviction,
                "instrument": r.instrument,
                "trade_type": r.trade_type,
                "entry_low": r.entry_low,
                "entry_high": r.entry_high,
                "target_price": r.target_price,
                "stop_loss": r.stop_loss,
                "risk_reward_ratio": r.risk_reward_ratio,
                "position_size_pct": r.position_size_pct,
                "max_holding_days": r.max_holding_days,
                "current_spread": r.current_spread,
                "target_spread": r.target_spread,
                "stop_spread": r.stop_spread,
                "expected_change": r.expected_change,
                "confidence": r.confidence,
                "explanation": explanation,
                "regime_label": r.regime_label,
                "regime_severity": r.regime_severity,
                "outcome": r.outcome,
                "pnl_pct": r.pnl_pct,
            })
        return results
    finally:
        db.close()
