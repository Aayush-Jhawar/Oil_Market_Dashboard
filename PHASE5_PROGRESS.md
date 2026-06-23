# Phase 5: Architecture Overhaul & Production Hardening

## Overview
Phase 5 focused on hardening the prediction pipeline for live trading. This included removing environment-specific compiled dependencies (C++ build tools), fixing critical data-leakage bugs in the walk-forward validation framework, and introducing a high-frequency Intraday Trading Engine.

## Critical Bug Fixes

### 1. Market Regime Fallback (HMM Dependency Removal)
*   **Issue:** The `hmmlearn` package failed to install on the deployment server due to missing C++ compilers. This caused the HMM model to fallback to a stub that always outputted `NEUTRAL`. Additionally, the Rule-based classifier was incorrectly attempting to apply dollar-spread thresholds against standardized (scaled) features.
*   **Resolution:** 
    1. Redesigned the `RuleBasedRegimeClassifier` thresholds to correctly identify Backwardation (Positive M1-M12 spread) and Contango.
    2. Modified `FeatureStoreService` to pass raw, unscaled dollar spreads to the Regime Engine, allowing it to correctly identify `EXTREME_BACKWARDATION` (+17.57/bbl) on the live data feed.

### 2. Walk-Forward Look-Ahead Bias
*   **Issue:** `walk_forward.py` was scaling its feature matrix (`fit_transform`) across the entire historical dataset *before* performing the sliding window backtest. This allowed future data points to influence the historical mean and variance of the scaling parameters.
*   **Resolution:** Moved the `FeatureTransformer` strictly inside the walk-forward loop. The scaler is now dynamically `fit` purely on the expanding/rolling training window and `transform` is cleanly applied to the out-of-sample test window.

### 3. Missing Volatility/ATR Default
*   **Issue:** When missing historical closes caused `realized_vol_20d` to be `NaN`, the signal generator defaulted to an aggressive 25% volatility assumption for Stop Loss / Target placements.
*   **Resolution:** Built dynamic ATR fallback logic that queries the recent features matrix to reconstruct missing volatility profiles accurately.

## New Architecture Components

### 1. Intraday Trading Runner (`intraday_runner.py`)
*   **Purpose:** 5-minute polling loop to execute AI inference during live market hours without getting rate-limited by slow macro/fundamentals endpoints.
*   **Features:**
    *   Queries `yf.Ticker` for 5-minute interval OHLCV data.
    *   Merges 5-minute prints with daily historical closes to maintain moving averages (200d MA, MACD, etc.).
    *   Caches the heavy `ModelEnsemble`, `FeatureStoreService`, and `RegimeEngine` into memory to eliminate disk-IO bottlenecks during the 5-minute crons.
*   **Integration:** Attached directly to the FastAPI ASGI loop via `apscheduler.schedulers.asyncio.AsyncIOScheduler`, running asynchronously every 5 minutes in the background.

### 2. Paper Trading Engine AI Scoring
*   **Purpose:** The raw Machine Learning probability matrix needed a robust business-logic overlay to prevent execution during low-confidence transitions or kinked curve structures.
*   **Features:**
    *   Implemented `AI Trade Score` (0-100 scale).
    *   Combines Forecast Strength (30%), Model Confidence (20%), Regime Alignment (20%), Factor Agreement (15%), and Similarity Search (15%).
    *   Strict Veto logic: Any generated trade with a score `< 60.0` is overridden to `NO_TRADE`.

## Next Steps
The backend is now heavily optimized for live Intraday Inference. Next steps focus on routing the output of the Intraday Runner directly via WebSockets to the React frontend to display live countdowns until the next inference batch.
