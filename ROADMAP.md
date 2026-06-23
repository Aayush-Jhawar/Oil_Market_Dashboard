# Oil Market Dashboard — Implementation Roadmap

This document outlines a phased plan to implement the v2.0 spec (`OIL_DASHBOARD_SPEC.md`) and to track progress across sessions.

Phases (high level)

2. Phase 1 — Core indicators & data modules (safe, offline-first)
   - Implement `backend/indicators.py` (EMA, BB, ATR, realized vol, ewma cov, kalman filter).
   - Add unit tests for indicators (small, deterministic inputs).

3. Phase 2 — Snapshot & WebSocket (simulated)
   - Add `backend/ws_snapshot.py` with `build_snapshot_simulated()` and a `/ws` endpoint.
   - Keep REST endpoints; add a toggle to enable simulated snapshot mode.
   - Frontend: add snapshot types and a `dashboardStore` that connects to `/ws` and writes `snapshot` into Zustand.

4. Phase 3 — Core backend modules
   - Implement `cot.py`, `steo.py`, `seasonality.py`, `sentiment.py` (VADER first), `paper.py` (simple simulated book).
   - Expose REST endpoints for each.

5. Phase 4 — Frontend panels (incremental delivery)
   - Wire Overview and Prices to use snapshot data.
   - Add BollingerBands, COT panel, FiveYearRange, Covariance matrix basic UI.
   - Add PanelSkeleton and simulated/fallback UI states.

6. Phase 5 — Integrations & optional modules
   - AIS (gate behind key), NOAA storms, FinBERT (optional preload), TradingView lazy widgets.

7. Phase 6 — Testing, performance, and release
   - Automated tests, `npm run build` validation, WS reconnect tests, prod build and Docker compose updates.
   - Confirmed frontend production build passes and backend Python syntax is valid.
   - Core API smoke tests return 200 for primary endpoints; full live-data integration requires configured `EIA_API_KEY`, `HF_API_KEY`, and working Yahoo Finance chart API connectivity.

Estimates (rough)
- Phase 0: 1–2 hours
- Phase 1: 4–8 hours
- Phase 2: 4–6 hours
- Phase 3: 12–24 hours (varies by external API keys)
- Phase 4: 12–32 hours
- Phase 5: 8–24 hours
- Phase 6: 4–8 hours

How to resume
- Update `PROGRESS.md` after any work chunk.
- Each code commit should reference the phase and the `ROADMAP.md` task(s).

---
Keep this file under version control and update estimates/status as work progresses.
