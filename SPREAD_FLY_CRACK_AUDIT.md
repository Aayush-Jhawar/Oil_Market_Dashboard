# Spread, Fly & Crack Prediction Pipeline Audit

**Date:** 2026-06-09
**Auditor:** Antigravity AI

## 1. Executive Summary
The prediction pipeline for Calendar Spreads, Butterflies, and Cracks is fundamentally disconnected and relies on critically flawed synthetic historical data generation. While real-time calculations in the frontend API are accurate, the AI models are not receiving valid historical curves, and the daily runner entirely skips spread processing.

## 2. End-to-End Investigation

### Data Source
*   **Cracks:** Calculated correctly in `PriceFetcher._fetch_crack_spread_historical` using outrights (e.g., 3-2-1 Crack derived from Brent, RBOB, HO).
*   **Spreads & Flies (Real-Time):** Calculated correctly in `services/curve_analytics.py` using actual live M1-M12 curve points fetched from Yahoo Finance.
*   **Spreads & Flies (Historical):** **CRITICAL FAILURE.** `PriceFetcher._fetch_cal_spread_historical` and `_fetch_fly_historical` do NOT fetch actual historical curve data. Instead, they synthesize M2 as a 21-day lagging rolling average of M1 (`M2 = df["close"].rolling(21).mean().shift(21)`). This destroys all term-structure reality.

### Feature Engineering
*   Because the historical data is synthetic for spreads and flies, the feature store computes technical indicators on fictitious spread movements.
*   The target variable generation in `train.py` calculates expected returns on these synthetic spreads, making the models mathematically invalid.

### Prediction Models
*   **Training:** `train.py` can technically run for spread symbols (passing `is_spread=True`), but because it uses synthetic price history, the resulting `ModelEnsemble` is meaningless.
*   **Execution:** `daily_runner.py` hardcodes `symbols = ["WTI", "Brent", "RBOB", "HO", "NG"]`. **Spreads, flies, and cracks are completely excluded from the daily AI pipeline.**
*   **Intraday Execution:** `intraday_runner.py` attempts to run for symbols like `3-2-1CRACK` and `WTI_FLY`, but feeds them through the synthetic data fetcher and an untrained ensemble.

### Database
*   No predictions or trade recommendations are stored for spreads or flies because `daily_runner.py` skips them. 

### API
*   `/api/analytics/structure` returns real-time spreads and flies accurately but hardcodes `z_scores` and `percentiles` to `None` because the historical DB lacks valid curve history.

### Frontend
*   `MarketStructureTab.tsx` correctly renders the real-time curve and spread matrix but cannot render historical context or AI forecasts for spreads since the API provides none.

## 3. Pipeline Break Points
1.  **Synthetic Historical Fetcher:** `PriceFetcher` fakes historical M2/M3 instead of fetching historical curve data.
2.  **Daily Runner Exclusion:** `daily_runner.py` ignores all spread symbols.
3.  **Untrained Ensemble:** No spread-specific models are built or validated on real curve structure.

## 4. Required Fixes
1.  **True Curve History:** Implement a robust historical forward-curve fetcher or integrate a proper data source for historical M2-M12 contracts.
2.  **Pipeline Inclusion:** Add `M1-M2`, `M1-M3`, `1-2-3 Fly`, `3-2-1 Crack`, etc., to the `daily_runner.py` execution list.
3.  **Specific Target Generation:** Modify `signal_generator.py` to correctly map spread widen/narrow forecasts into actionable trades.
