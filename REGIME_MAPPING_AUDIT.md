# Regime Mapping Audit

## Overview
This audit traces the lifecycle of regime classifications from the prediction model to the UI, identifying exactly why "UNKNOWN" appears in the frontend and outlining the exact logic fixes applied to resolve it.

## Lifecycle Trace

### 1. Regime Model & Prediction Service
**Component:** `backend/prediction/regime/regime_engine.py` -> `backend/prediction/intraday_runner.py`
**Behavior:** 
- The `run_intraday_pipeline` triggers every 5 minutes. It extracts live prices and features and calls `regime_engine.classify(raw_features)`.
- It saves `regime_state` mapping into a global variable `_latest_intraday` inside `backend/main.py`.
**Status:** ✅ Valid. The model produces valid regime classifications (e.g. `BULLISH`, `BEARISH`, `NEUTRAL`).

### 2. API Response (Websocket)
**Component:** `backend/ws_snapshot.py`
**Behavior:**
- The websocket loop fetches the regime mapping directly from `main._latest_intraday`.
- If a symbol has not yet been processed (e.g., during the first 5 minutes of server startup, or if a data fetch failed), `_latest_intraday` does not contain the symbol.
- Previously, the fallback was hardcoded as: `regimes[sym] = data["regime_state"].get("regime_label", "UNKNOWN")`
**Status:** ❌ Flawed Fallback. Fallbacks used "UNKNOWN", silently obfuscating initialization states versus actual classification failures.

### 3. Database Layer
**Component:** `backend/main.py` -> `daily_runner.py`
**Behavior:**
- Historical regime states are written to the database once a day (via the daily pipeline). The intraday pipeline skips DB writing to stay lightweight.
- Thus, the DB holds the last known valid state, but the live snapshot mechanism wasn't attempting to read it upon startup.
**Status:** ⚠️ Incomplete Integration. The system should load the last known DB state on initialization instead of defaulting to empty dicts.

### 4. UI Component & Frontend Fallback Logic
**Component:** `frontend/src/components/Header/HeaderBar.tsx`, `MarketStatePanel.tsx`
**Behavior:**
- `const regimeStr = assetRegime ? assetRegime.replace('_', ' ') : 'UNKNOWN';`
- If the WebSocket `snapshot.header.regimes` object was missing an asset, the frontend immediately rendered "UNKNOWN".
**Status:** ❌ Poor UX. "UNKNOWN" is unacceptable in production displays. It should read "INITIALIZING" or display a loading skeleton if data is still fetching.

## Root Cause Analysis
1. **Server Restart Delay:** On backend reboot, `_latest_intraday` is `{}`. The background job takes up to 5 minutes to trigger, run the ML models, and populate the regime state.
2. **Missing Symbol Edge Case:** If `PriceFetcher` fails to fetch live data (e.g. `$CLM26.NYM` delisting errors), the `run_intraday_pipeline` skips that symbol entirely, ensuring it never enters the `_latest_intraday` map.
3. **Hardcoded Fallbacks:** Both the backend (`ws_snapshot.py`) and frontend (`HeaderBar.tsx`) actively masked missing data with the string `"UNKNOWN"`.

## Remediation Plan
1. **Backend:** Update `ws_snapshot.py` and `backend/main.py` to change `"UNKNOWN"` to `"INITIALIZING"`. Add explicit diagnostic logging.
2. **Frontend:** Update React components to render a loading spinner or an explicit "INITIALIZING" tag when a regime is unavailable, ensuring the user understands it is a pending network operation rather than a failed prediction.
