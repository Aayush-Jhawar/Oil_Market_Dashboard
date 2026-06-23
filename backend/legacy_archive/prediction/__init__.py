"""
Phase 2: Regime-Aware Oil Market Prediction Engine
===================================================
Institutional-grade forecasting system that classifies futures curve regimes,
generates regime-conditioned forecasts, and produces explainable trade
recommendations.

Modules:
    features/    — Feature engineering (curve, fundamental, technical, macro, seasonal)
    regime/      — Regime detection (rule-based + HMM hybrid)
    models/      — Forecasting models (LightGBM, ensemble)
    trading/     — Signal generation, confidence, risk management
    explain/     — SHAP-based model explainability
    validation/  — Walk-forward validation framework
"""
__version__ = "0.1.0"
