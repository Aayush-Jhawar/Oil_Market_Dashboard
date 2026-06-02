# Oil Market Dashboard Overview

## Purpose
This project is a real-time energy trading dashboard built with a React + Vite frontend and a FastAPI backend.
It displays energy market prices, spread analytics, sentiment and news, macro/EIA fundamentals, and derived signals for traders and analysts.

## Architecture
- Frontend: `frontend/`
  - React + Vite application
  - Zustand store for dashboard state
  - Axios for API communication
  - Recharts for charts and sparklines
- Backend: `backend/`
  - FastAPI service
  - Data fetchers for prices, news, EIA, macro, CFTC, and rigs
  - Signal calculator logic in `backend/signal_calc.py`
  - SQLite / SQLAlchemy persistence through `backend/database.py` if used

## Main Dashboard Flow
- The frontend loads once and requests core dashboard data from the backend.
- The backend gathers market prices, news, macro data, and analytic signals.
- The frontend stores data in the dashboard store and renders it into the selected tab.
- The alert and spreads panels refresh automatically in the browser every few seconds.

## Dashboard Header and Top Strip
- Fixed header bar showing:
  - current regime: `BULLISH`, `BEARISH`, or `NEUTRAL`
  - current volatility regime
  - price pills for key products: `WTI`, `RBOB`, `HO`, `BRENT`, `GO`, `DXY`
  - composite score bar with a normalized gauge
- Page title updated to: **Oil Market Dashboard**
- Top content area now has padding so the fixed header does not cut off the page.

## Tabs and What They Show

### Overview
The `Overview` tab is the main summary panel. It includes:
- Market state panel and enhanced signals panel
- Composite score and sentiment gauge
- Volatility regime and annualized volatility
- Suggested position sizing based on signal and volatility
- Snapshot cards for core products: `WTI`, `RBOB`, `HO`, `Brent`
  - current price, change, high/low, sparkline history
- A short alerts & signals feed
- Correlation analytics for energy symbols

### Prices
The `Prices` tab focuses on spot price action and crack spreads:
- Bar chart of current prices for core products
- Top price mover cards for `WTI`, `RBOB`, `HO`, `Brent`, `GO`
- Line chart visualizing price distribution
- Candlestick charts for recent history of `WTI`, `Brent`, `RBOB`, and `HO`
- Crack spread cards for:
  - `3:2:1 Crack Spread`
  - `5:3:2 Crack Spread`
  - `1:1 Gasoil Crack` (`GASCRACK` / `DIESELCRACK`)

### Market Structure
The `Market` tab provides broader structure analytics:
- Forward curve shape and M1–M12 spread
- Correlation and beta analytics between energy products
- CFTC positioning summary for managed money and open interest
- Crack spread health and downstream refining margin context
- EIA fundamentals snapshot for crude stocks, Cushing hub, refinery utilization, and US crude production
- Market sentiment and risk summary

### Forward / Seasonality
The `Forward` tab is a seasonality and curve-focused view:
- Forward curve chart for monthly contract prices
- M1-M12 spread and other short-term curve spreads (M1-M2, M2-M3, M3-M4)
- Placeholder for extended seasonality range analysis

### Spreads
The `Spreads` tab highlights the most important spread relationships:
- Active alerts from the backend
- Key spread cards for:
  - `BRENT-WTI`
  - `3-2-1CRACK`
  - `GASCRACK`
  - `DIESELCRACK`
  - `DUBAI-WTI`
  - `FRAC`
- Each spread includes current value, 5-day average, z-score, and relative move vs recent average
- This page refreshes spreads and alerts automatically every 5 seconds

### News
The `News` tab surfaces sentiment-driven news and macro commentary:
- Priority news bulletin with sentiment score badges
- Geopolitical risk heatmap for major oil-producing regions
- Macro indicator panel (DXY, 10Y yield, SPX, PMI readings)
- China demand module and risk signals

### EIA Anchors
The `EIA Anchors` tab shows weekly EIA anchor series data:
- Weekly EIA values are compared against their 5-year seasonal averages
- Each item displays current value, 5-year average, delta vs anchor, and timestamp
- This is a fundamentals anchoring view for crude stocks, refinery utilization, SPR level, imports/exports, and more

## Backend Data Sources

### Price Data
- `backend/services/price_fetcher.py` uses direct Yahoo Finance chart API requests with browser-like headers to fetch live contract prices.
- Supported symbols include:
  - `WTI` (`CL=F`), `Brent` (`BZ=F`), `RBOB` (`RB=F`), `HO` (`HO=F`), `GO` (`B0=F`)
  - `HH` (`NG=F`), `DXY` (`DX-Y.NYB`), `SPX` (`^GSPC`), `TNX` (`^TNX`), `VIX` (`^VIX`), `GC` (`GC=F`), `USO`, `UNG`
- Derived symbols are computed in code:
  - `DUBAICRUDE`, `WCS-WTI`, crack spreads, and others
- Historical data is fetched with fallback synthetic history if live data is unavailable

### News & Sentiment
- `backend/services/news_fetcher.py` scrapes or fetches RSS sources
- Sentiment is calculated by `NewsFetcher.calculate_sentiment_trend`
- Sources include Reuters, OPEC, CNBC Energy, Bloomberg, World Oil, and more
- Some sentiment engines may log warnings if API keys are not set

### EIA and Macro Data
- `backend/services/eia_fetcher.py` pulls EIA series data and calculates weekly anchors
- Macro data comes from `backend/services/macro_fetcher.py`
  - Rig counts
  - CFTC positioning
  - Other macro series used by the dashboard

### Signal & Analytics Calculations
- `backend/signal_calc.py` performs technical calculations:
  - EMA, ATR, Bollinger Bands
  - Composite score
  - Crack spread calculations
  - Realized volatility and regime classification
  - Correlation and beta analytics
- These analytics power the `signals` and `enhanced` endpoints

## API Endpoints Used by the Frontend
The dashboard uses backend routes including:
- `/api/prices/all` — latest product prices
- `/api/prices/instruments` — supported symbol list
- `/api/prices/{symbol}` — one symbol price fetch
- `/api/prices/{symbol}/historical` — historical series for charting
- `/api/signals/composite` — composite signal and regime
- `/api/signals/enhanced` — enhanced market state analytics
- `/api/analytics/forward-curve` — forward curve pricing
- `/api/analytics/correlations` — correlations matrix and betas
- `/api/spreads/all` — spread analytics across several energy relationships
- `/api/alerts/active` — active market alerts
- `/api/news/enhanced` — news feed and sentiment data
- `/api/eia/weekly` and `/api/eia/weekly-anchor` — EIA fundamentals and anchor comparisons
- `/api/rigs/latest` — latest rig counts
- `/api/cftc/latest` — CFTC managed-money positioning

## Behavior Notes
- The dashboard is intended to update automatically but not show a refresh banner.
- The alerts/spreads components refresh automatically every few seconds.
- The app uses fallback/mock data when primary live data sources fail to keep the UI responsive.
- The top fixed header is padded to avoid overlaying page content.

## File Locations
- Frontend main app: `frontend/src/App.tsx`
- Alert strip: `frontend/src/components/AlertStrip.tsx`
- Spreads panel: `frontend/src/components/SpreadsPanel.tsx`
- Tabs:
  - `frontend/src/tabs/OverviewTab.tsx`
  - `frontend/src/tabs/PricesTab.tsx`
  - `frontend/src/tabs/MarketStructureTab.tsx`
  - `frontend/src/tabs/SeasonalityTab.tsx`
  - `frontend/src/tabs/NewsTab.tsx`
  - `frontend/src/tabs/AnchorDataTab.tsx`
- Backend routes: `backend/main.py`
- Backend services: `backend/services/price_fetcher.py`, `backend/services/news_fetcher.py`, `backend/services/eia_fetcher.py`, `backend/services/macro_fetcher.py`

## Summary
This dashboard is a trader-facing oil market analytics console:
- real-time prices
- crack/spread analytics
- signal and volatility regimes
- EIA and macro fundamentals
- sentiment-driven news and alerts
- forward curve and seasonality analysis

It is built to be a single-page monitoring application that presents both raw market data and derived trading analytics for quick decision support.