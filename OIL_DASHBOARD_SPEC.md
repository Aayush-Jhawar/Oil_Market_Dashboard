# Oil Market Dashboard — Full Upgrade Specification
**For Claude Code / VS Code Agentic Build**
**Version 2.0 | May 2026**

---

## 0. Purpose of This Document

This spec merges the best of two dashboards:

- **Your dashboard** (`DASHBOARD_OVERVIEW.md`): React + Vite + FastAPI, strong tab structure, crack-spread analytics, EIA anchors, composite signal engine, Zustand store.
- **Reference dashboard** (`ravish28-oil-trading-desk.hf.space`): Superior data breadth (WebSocket push, Bollinger Bands, EWMA covariance matrix, CFTC COT, STEO global balance, paper trading book, dual-engine sentiment with FinBERT, AIS tanker tracking, NOAA storm watch, TradingView embedded charts, 5-year seasonal range, calendar spread matrix, analyst watch, Kalman pair filter).

**Goal:** Adopt the reference dashboard's best features and architecture into your existing React + FastAPI codebase, producing a trader-grade analytics console with a polished dark UI.

Claude Code should read this spec top-to-bottom and implement each section in order. Every section lists exact files to create or modify, the data contract, and the UI requirement.

---

## 1. Architecture Changes

### 1.1 Switch from Polling to WebSocket Push

**Current:** Frontend calls REST endpoints every few seconds via Axios.
**Target:** Backend pushes a unified JSON snapshot every 2 seconds over a WebSocket. REST endpoints remain for deep-linking and one-shot fetches.

**Backend — `backend/main.py`**

Add a simulation/refresh loop:

```python
TICK_SECONDS = 2.0
PRICE_EVERY_TICKS = 30       # 60s
CURVE_EVERY_TICKS = 30       # 60s
EIA_EVERY_TICKS = 900        # 30 min
CFTC_EVERY_TICKS = 900       # 30 min
NEWS_EVERY_TICKS = 8         # 16s
SENTIMENT_EVERY_TICKS = 8    # 16s
STEO_EVERY_TICKS = 1800      # 60 min
SEASONALITY_EVERY_TICKS = 10800  # 6h
STORMS_EVERY_TICKS = 300     # 10 min
```

Implement `build_snapshot()` returning a single dict with keys:
`ts, tick, header, price, bb, spread, futures, cracks, covmatrix, fundamentals, signals, fiveyear, news, news_sentiment, analyst_news, cot, steo, seasonality, paper, tankers, storms`

Add WebSocket endpoint:
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # on connect: send snapshot immediately
    # then push every tick
    # handle client ping keepalive
    # auto-reconnect handled client-side
```

**Frontend — `frontend/src/store/dashboardStore.ts`**

Replace Axios polling with a WebSocket client:

```typescript
// Connect to ws://{host}/ws
// On message: parse JSON → setSnapshot(data)
// Auto-reconnect: 2s → 4s → 8s → 16s (capped)
// Send "ping" keepalive every 15s
```

Snapshot flows into Zustand store. All tab components subscribe to relevant slices.

---

## 2. New Backend Modules to Add

### 2.1 `backend/indicators.py`
Technical indicators library used by signal_calc and the new panels:
- `bollinger_bands(prices, period=20, std=2)` → `{upper, middle, lower, bandwidth, %b}`
- `ema(prices, period)` → series
- `atr(high, low, close, period=14)` → series
- `realized_vol(returns, window=20)` → annualized σ
- `ewma_cov_matrix(returns_df, lam=0.94)` → DataFrame (RiskMetrics convention)
- `correlation_matrix(returns_df, window=90)` → DataFrame
- `kalman_pair_filter(y, x)` → `{beta, spread, z_score}` (2-state: level + slope)

### 2.2 `backend/steo.py`
EIA Short-Term Energy Outlook — global supply/demand balance:
- Series: `PAPR_WORLD, PATC_WORLD, PAPR_OPEC, PAPR_NONOPEC, PATC_OECD, PATC_NON_OECD`
- Returns: `{world_supply_mbpd, world_demand_mbpd, implied_balance_mbpd, opec_supply, nonopec_supply, oecd_demand, non_oecd_demand, fwd_6m_avg, fwd_12m_avg, is_forecast: [bool per month]}`
- Cadence: 60 min
- Graceful fail: return `None` (panel hides)

### 2.3 `backend/cot.py`
CFTC Commitments of Traders — NYMEX WTI:
- Source: Socrata `gpe5-46if` Disaggregated COT
- Returns: `{mm_long, mm_short, mm_net, mm_net_wow, producer_long, producer_short, producer_net, open_interest, report_date}`
- Cadence: 30 min

### 2.4 `backend/sentiment.py`
Dual-engine news sentiment:
- VADER: always available, synchronous, per-headline
- FinBERT (`ProsusAI/finbert`): async, transformer-based, runs after VADER
- Per news item: `{headline, source, published, vader_score, finbert_label, finbert_score, composite_sentiment}`
- Composite: 0.4×VADER + 0.6×FinBERT when FinBERT available, else VADER only
- Expose `/api/news/finbert-status` → `{loaded: bool, model: str}`

### 2.5 `backend/hurricane.py`
NOAA NHC storm tracking:
- Source: `https://www.nhc.noaa.gov/CurrentStorms.json`
- Overlay: 13 US Gulf refineries (name, lat, lon, capacity_mbpd) + OCS offshore zone
- Logic: flag refinery as "at-risk" if storm centre within 150 nm
- Returns: `{storms: [{name, category, lat, lon, wind_kt, at_risk_refineries}], total_at_risk_capacity_mbpd, season_active: bool}`
- Cadence: 10 min

### 2.6 `backend/ais.py`
AIS tanker tracking via aisstream.io WebSocket:
- Ship types 80–89 (tankers) only
- 5 bounding boxes (tight petroleum terminal coordinates):
  - Rotterdam (Maasvlakte petroleum terminal)
  - Singapore (Jurong Island terminal)
  - Fujairah (UAE terminal anchorage)
  - Cushing OK (Cushing pipeline hub — river traffic proxy)
  - US Gulf LOOP (Louisiana Offshore Oil Port)
- Returns per zone: `{zone, confirmed_tankers, total_vessels, vessels: [{mmsi, name, lat, lon, speed, heading}]}`
- Cadence: continuous WebSocket push
- Graceful fail: panel shows "AIS offline" banner

### 2.7 `backend/paper.py`
Virtual paper trading book — $100k starting equity:
- Auto-trades when composite signal crosses ±threshold
- Tracks: equity curve, open positions (symbol, direction, entry, current P&L), closed trades (entry/exit/P&L/duration)
- Metrics: total return %, win rate, realized P&L, unrealized P&L, Sharpe (annualized), max drawdown
- Persist state to `paper_state.json` between restarts
- Returns: full book state on every snapshot

### 2.8 `backend/seasonality.py`
5-year refinery utilization seasonality:
- Pull 5 years of weekly EIA utilization (`PET.WPULEUS3.W`)
- Compute week-of-year average and ±1σ band
- Compare current week to norm → `deviation_sigma`
- Returns: `{weeks: [{week_num, norm_pct, current_pct, sigma_dev}], current_week, current_vs_norm_pct}`
- Cadence: 6h

---

## 3. New & Upgraded Frontend Panels

All panels use the existing dark theme CSS variables. New panels follow the same `<article class="panel">` pattern.

### 3.1 Bollinger Bands Panel (NEW)
**File:** `frontend/src/components/BollingerBandsChart.tsx`

- Line chart: upper band (red/orange), middle SMA (white), lower band (blue), price (yellow)
- Shows: current %b, bandwidth, "squeeze" indicator when bandwidth < 20th percentile
- Data key: `snapshot.bb` → `{upper[], middle[], lower[], price[], timestamps[], bandwidth, pct_b, squeeze: bool}`

### 3.2 EWMA Spread Covariance Matrix (NEW)
**File:** `frontend/src/components/CovarianceMatrix.tsx`

- Heatmap grid: energy symbols on both axes (WTI, Brent, RBOB, HO, BRENT-WTI, 3-2-1 crack, GASCRACK, DIESELCRACK, DXY)
- Color scale: red = high positive covariance (concentrated risk), green = negative (diversifying)
- Show diagonal (variance = vol²) in bold
- Tooltip on hover: `{cov_value, correlation, pair}`
- Subtitle: "EWMA λ=0.94 — recent observations weighted ~6× heavier than 30 days ago"
- Data key: `snapshot.covmatrix`

### 3.3 5-Year Seasonal Range (NEW)
**File:** `frontend/src/components/FiveYearRange.tsx`

- Bar or ribbon chart: current WTI price vs 5-year same-week min/max/median
- Show percentile rank: "Currently at 67th percentile of 5-year range"
- Data key: `snapshot.fiveyear` → `{current, min_5y, max_5y, median_5y, pct_rank, symbol}`

### 3.4 STEO Global Oil Balance (NEW)
**File:** `frontend/src/components/STEOBalance.tsx`

- Grouped bar chart: world supply vs world demand per month
- Line overlay: implied balance (supply − demand, M bpd)
- Solid bars = historical, hatched/lighter bars = STEO forecast
- Show: OPEC supply, Non-OPEC supply, OECD demand, Non-OECD demand as sub-labels
- Fwd 6M avg balance and 12M avg balance pills
- Panel hidden if `snapshot.steo === null`
- Explanatory note: "Supply > demand → surplus → stocks build → bearish"

### 3.5 CFTC Commitment of Traders (UPGRADE)
**File:** `frontend/src/components/COTPanel.tsx`

Current implementation only shows basic positioning. Upgrade to match reference:
- Managed Money net (long − short), with WoW change arrow
- Producer/Commercial net (the "smart money" hedge)
- Open interest total
- Bar chart: MM long, MM short, Producer long, Producer short side-by-side
- Historical MM net line chart (last 12 weeks)
- Report date badge: "As of [date], published Friday"
- Data key: `snapshot.cot`

### 3.6 TradingView Embedded Charts (NEW)
**File:** `frontend/src/components/TradingViewWidget.tsx`

Add a "Pro Tools" tab with 6 TradingView iframe widgets (theme=dark, autosize=true):
- T1: WTI Crude → `TVC:USOIL`
- T2: Brent Crude → `TVC:UKOIL`
- T3: WTI-Brent Spread → `TVC:USOIL−TVC:UKOIL`
- T4: RBOB proxy → `AMEX:UGA`
- T5: Heating Oil proxy → `AMEX:UHN`
- T6: Natural Gas → `TVC:NGAS`

Widget config:
```javascript
{
  "symbol": "TVC:USOIL",
  "interval": "5",
  "theme": "dark",
  "style": "1",
  "locale": "en",
  "toolbar_bg": "#0d1117",
  "enable_publishing": false,
  "hide_top_toolbar": false,
  "save_image": false,
  "container_id": "tv_chart_wti"
}
```

### 3.7 Calendar Spread Matrix (NEW)
**File:** `frontend/src/components/CalendarSpreadMatrix.tsx`

- Grid: rows = M1..M11, cols = M2..M12
- Cell value: price[col] − price[row] in $/bbl
- Green = positive (contango), red = negative (backwardation)
- Diagonal = consecutive spread (M1-M2, M2-M3, etc.)
- Auto-refresh every 3 min
- Tooltip: "M3 − M1 = +$0.42/bbl (contango)"
- Data key: `snapshot.futures.curve_matrix`

### 3.8 Spread Covariance Matrix — Calendar Spreads (NEW)
**File:** `frontend/src/components/SpreadCovMatrix.tsx`

- Sample covariance (not EWMA, Bessel-corrected) of consecutive calendar spreads
- M1-M2 through M11-M12 on both axes
- Diagonal = spread variance (= spread vol²)
- Off-diagonal typically negative (adjacent spreads anti-correlate → fly trade has HIGHER variance than sum of legs)
- Color: red = positive co-move (concentrated risk), green = negative (butterfly hedge)
- Note: "Adjacent spreads share a common month, so they're typically anti-correlated — the hidden risk in fly structures"

### 3.9 Dual-Sentiment News Feed (UPGRADE)
**File:** `frontend/src/tabs/NewsTab.tsx`

Upgrade the existing news feed:
- Per headline: VADER score badge + FinBERT label badge (`Bullish / Bearish / Neutral` in green/red/grey)
- FinBERT loading spinner with "FinBERT: loading model…" status pill
- Composite sentiment bar across all headlines (−1 to +1)
- Source badges: Reuters, OilPrice, CNBC Energy, Bloomberg, Hellenic Shipping
- Filter chips: All | Bullish | Bearish | Geopolitical

### 3.10 Analyst Watch (NEW)
**File:** `frontend/src/components/AnalystWatch.tsx`

- 3 Google News RSS searches (configurable analyst names: Amrita Sen, Helima Croft, Saad Rahim)
- Each analyst: latest headline, publication time, VADER sentiment score
- Sub-label: "Using Google News mentions as free Twitter/X proxy"
- Data key: `snapshot.analyst_news`

### 3.11 Refinery Seasonality Chart (NEW)
**File:** `frontend/src/components/SeasonalityChart.tsx`

- Line chart: current year's weekly EIA utilization vs 5-year week-of-year average
- ±1σ band shaded around the 5-year norm
- Deviation badge: "−2.3σ below seasonal norm → bullish product cracks"
- Annotation: "Heavy turnaround underway when dipping below norm in weeks 9–16 (spring) or 36–44 (fall)"
- Data key: `snapshot.seasonality`

### 3.12 Paper Trading Performance Panel (NEW)
**File:** `frontend/src/components/PaperTrading.tsx`

- Header pills: Account Equity | Total Return % | Realized P&L | Unrealized P&L | Win Rate | Sharpe
- Open positions table: Symbol | Direction | Entry | Current | P&L | Duration
- Closed trades table (last 10): Entry | Exit | P&L | Duration | Signal
- Equity curve line chart
- Label: "Virtual $100k — auto-trades dashboard signals"
- Data key: `snapshot.paper`

### 3.13 Storm Watch Panel (NEW)
**File:** `frontend/src/components/StormWatch.tsx`

- Map or table view of active Atlantic/Gulf storms
- Per storm: name, category (1–5 or TD/TS), wind speed kt, position
- At-risk refinery list: name, capacity, distance from storm
- Total at-risk refining capacity (M bpd) in red pill
- "No active storms" empty state with season dates (Jun 1 – Nov 30)
- Note: "Markets typically price storm risk 3–5 days before landfall"
- Data key: `snapshot.storms`

### 3.14 AIS Tanker Watch (NEW)
**File:** `frontend/src/components/TankerWatch.tsx`

- 5-zone layout: Rotterdam | Singapore | Fujairah | Cushing | US Gulf LOOP
- Per zone: confirmed tanker count (type 80–89), total vessels in box
- Vessel list (scrollable): MMSI, name, speed kt, heading
- Status indicator: "AIS live" (green) or "AIS offline" (grey)
- Disclaimer: "Free tier — terrestrial coverage ~40 mi from shore. Zero = coverage gap, not absence of ships."
- Data key: `snapshot.tankers`

### 3.15 Kalman Pair Filter — WTI/DXY (NEW)
**File:** `frontend/src/components/KalmanFilter.tsx`

- 2-state Kalman filter tracking β (hedge ratio) and spread z-score between WTI and DXY
- Line chart: rolling β over 90 days, spread z-score
- Signal: if |z| > 2.0 → "Mean reversion signal: WTI/DXY spread stretched"
- Data key: `snapshot.signals` (add `kalman_wti_dxy` key)

---

## 4. Tab Structure Overhaul

### Current Tabs → New Tabs

| Current Tab | Action |
|---|---|
| Overview | Keep, add composite sentiment + 5Y range card |
| Prices | Keep, add Bollinger Bands chart |
| Market Structure | Keep, upgrade COT, add EWMA covmatrix, STEO |
| Forward / Seasonality | Rename to "Curve & Seasonality", add calendar spread matrix, spread covmatrix, seasonality chart |
| Spreads | Keep, add Kalman filter panel |
| News | Upgrade with dual sentiment |
| EIA Anchors | Keep as-is |
| **Pro Tools** (NEW) | TradingView widgets × 6, analyst watch, storm watch, tanker watch, paper trading |

**File:** `frontend/src/App.tsx`

Add "Pro Tools" tab button. Tab state managed in Zustand store. Pro Tools tab lazy-loads TradingView iframes on first activation.

---

## 5. UI / Design System Upgrades

### 5.1 Fixed Header Upgrade
**File:** `frontend/src/components/Header.tsx`

Add to the existing fixed header strip:
- WebSocket connection indicator: pulsing green dot when live, grey when reconnecting
- Tick counter (updates every 2s when connected)
- `FinBERT: ✓` status badge when transformer model is loaded
- Last update timestamp per data source (hover tooltip on price pill → "Updated 43s ago")

### 5.2 Color System
Keep the existing dark theme. Add:
```css
--color-bb-upper: #f97316;    /* Bollinger upper */
--color-bb-lower: #3b82f6;    /* Bollinger lower */
--color-cov-hot: #ef4444;     /* high covariance cell */
--color-cov-cold: #22c55e;    /* negative covariance cell */
--color-steo-supply: #60a5fa; /* STEO supply bars */
--color-steo-demand: #f59e0b; /* STEO demand bars */
--color-steo-balance-pos: #22c55e;
--color-steo-balance-neg: #ef4444;
--color-forecast-opacity: 0.45; /* hatched forecast bars */
```

### 5.3 Panel Loading States
Every panel must show a skeleton/shimmer while data is null:
```tsx
if (!data) return <PanelSkeleton rows={4} />;
```

### 5.4 Dashed Border for Simulated Data
Any panel using synthetic/fallback data must show a dashed border and a badge:
```tsx
<div className={`panel ${isFallback ? 'panel--simulated' : ''}`}>
  {isFallback && <span className="badge badge--sim">SIMULATED</span>}
```

---

## 6. Data Contract — Unified Snapshot

Full TypeScript interface for the WebSocket snapshot:

```typescript
interface DashboardSnapshot {
  ts: string;           // ISO timestamp
  tick: number;
  sources: Record<string, { last_updated: string; ok: boolean }>;

  header: {
    regime: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    vol_regime: 'HIGH' | 'NORMAL' | 'LOW';
    composite_score: number;     // −100 to +100
    prices: Record<string, { price: number; change: number; change_pct: number }>;
  };

  price: {
    symbols: string[];
    data: Record<string, {
      price: number; change: number; change_pct: number;
      high: number; low: number; sparkline: number[];
    }>;
  };

  bb: {
    symbol: string;
    upper: number[]; middle: number[]; lower: number[];
    price: number[]; timestamps: string[];
    bandwidth: number; pct_b: number; squeeze: boolean;
  };

  spread: Record<string, {
    value: number; avg_5d: number; z_score: number; rel_move: number;
  }>;

  futures: {
    curve: Record<string, number>;     // M1..M12 → price
    curve_matrix: number[][];          // 12×12 spread matrix
    m1_m12_spread: number;
    structure: 'CONTANGO' | 'BACKWARDATION' | 'FLAT';
  };

  cracks: Record<string, {
    value: number; z_score: number; avg_90d: number;
  }>;

  covmatrix: {
    symbols: string[];
    matrix: number[][];  // EWMA λ=0.94 covariance
    correlation: number[][];
  };

  fundamentals: {
    crude_stocks_mmbbl: number;
    cushing_mmbbl: number;
    refinery_util_pct: number;
    us_crude_prod_mbpd: number;
    rig_count: number;
    spr_level_mmbbl: number;
  };

  signals: {
    composite_score: number;
    regime: string;
    vol_annualized: number;
    position_sizing_pct: number;
    signals: Array<{
      name: string; value: number; signal: string; weight: number;
    }>;
    kalman_wti_dxy: { beta: number; spread: number; z_score: number };
  };

  fiveyear: {
    symbol: string;
    current: number;
    min_5y: number; max_5y: number; median_5y: number;
    pct_rank: number;
  };

  news: Array<{
    headline: string; source: string; published: string; url: string;
    vader_score: number;
    finbert_label: 'bullish' | 'bearish' | 'neutral' | null;
    finbert_score: number | null;
    composite_sentiment: number;
    region_tags: string[];
  }>;

  news_sentiment: {
    overall: number;
    finbert_loaded: boolean;
    breakdown: { bullish: number; bearish: number; neutral: number };
  };

  analyst_news: Array<{
    analyst: string;
    headline: string;
    published: string;
    url: string;
    vader_score: number;
  }>;

  cot: {
    mm_long: number; mm_short: number; mm_net: number; mm_net_wow: number;
    producer_long: number; producer_short: number; producer_net: number;
    open_interest: number;
    report_date: string;
    history_12w: Array<{ date: string; mm_net: number }>;
  };

  steo: {
    months: string[];
    world_supply: number[];
    world_demand: number[];
    implied_balance: number[];
    opec_supply: number[];
    nonopec_supply: number[];
    oecd_demand: number[];
    non_oecd_demand: number[];
    is_forecast: boolean[];
    fwd_6m_avg: number;
    fwd_12m_avg: number;
  } | null;

  seasonality: {
    weeks: Array<{
      week_num: number;
      norm_pct: number;
      current_pct: number | null;
      sigma_dev: number | null;
    }>;
    current_week: number;
    current_vs_norm_pct: number;
    deviation_sigma: number;
  };

  paper: {
    equity: number;
    total_return_pct: number;
    realized_pnl: number;
    unrealized_pnl: number;
    win_rate: number;
    sharpe: number;
    max_drawdown: number;
    open_positions: Array<{
      symbol: string; direction: 'LONG' | 'SHORT';
      entry_price: number; current_price: number; pnl: number; duration_h: number;
    }>;
    closed_trades: Array<{
      symbol: string; direction: string;
      entry: number; exit: number; pnl: number; duration_h: number; signal: string;
    }>;
    equity_curve: number[];
  };

  tankers: Array<{
    zone: string;
    confirmed_tankers: number;
    total_vessels: number;
    vessels: Array<{
      mmsi: string; name: string; lat: number; lon: number;
      speed: number; heading: number;
    }>;
  }> | null;

  storms: {
    storms: Array<{
      name: string; category: string; lat: number; lon: number; wind_kt: number;
      at_risk_refineries: Array<{ name: string; capacity_mbpd: number; distance_nm: number }>;
    }>;
    total_at_risk_capacity_mbpd: number;
    season_active: boolean;
  };
}
```

---

## 7. API Endpoints to Add / Keep

### Keep (REST — existing)
```
GET /api/prices/all
GET /api/prices/{symbol}
GET /api/prices/{symbol}/historical
GET /api/signals/composite
GET /api/signals/enhanced
GET /api/analytics/forward-curve
GET /api/analytics/correlations
GET /api/spreads/all
GET /api/alerts/active
GET /api/news/enhanced
GET /api/eia/weekly
GET /api/eia/weekly-anchor
GET /api/rigs/latest
GET /api/cftc/latest
```

### Add (REST — new)
```
GET /api/steo/balance         → STEO global S/D data
GET /api/cot/history          → 12-week COT history
GET /api/seasonality          → 5-year utilization seasonality
GET /api/paper/state          → paper trading book state
GET /api/paper/reset          → POST to reset paper book
GET /api/storms/active        → NOAA storm data + refinery overlay
GET /api/tankers/positions    → AIS zone snapshots
GET /api/news/finbert-status  → {loaded, model}
GET /api/indicators/bb/{sym}  → Bollinger Bands for a symbol
GET /api/indicators/kalman    → Kalman pair filter result
```

### Add (WebSocket — new)
```
WS /ws                        → unified 2s snapshot push
```

---

## 8. Environment Variables (`.env`)

```env
# Required for full data
EIA_API_KEY=your_eia_key           # EIA v2 API (free at eia.gov)
TWELVE_DATA_KEY=your_key           # Twelve Data forex (free tier)
AISSTREAM_KEY=your_key             # aisstream.io (free tier)

# Optional — FinBERT loads from HuggingFace hub automatically
# Preload on startup: set to "true" to load at boot (adds ~30s startup)
FINBERT_PRELOAD=false

# Paper trading
PAPER_STARTING_EQUITY=100000
PAPER_SIGNAL_THRESHOLD=0.6        # composite score threshold to trigger trade
PAPER_POSITION_SIZE_PCT=0.10      # 10% of equity per trade

# AIS bounding boxes (tight petroleum terminal coords)
AIS_BOX_ROTTERDAM=51.95,4.00,51.85,4.20
AIS_BOX_SINGAPORE=1.22,103.70,1.28,104.00
AIS_BOX_FUJAIRAH=25.08,56.30,25.25,56.45
AIS_BOX_CUSHING=35.95,-96.82,36.05,-96.75
AIS_BOX_LOOP=28.85,-90.20,28.95,-90.10
```

---

## 9. Build Order for Claude Code

Implement in this exact order to avoid broken states:

1. **`backend/indicators.py`** — all math primitives (no external deps beyond numpy/pandas)
2. **`backend/cot.py`** — CFTC data (Socrata, no API key needed)
3. **`backend/steo.py`** — EIA STEO (requires EIA key)
4. **`backend/seasonality.py`** — 5-year EIA utilization (requires EIA key)
5. **`backend/sentiment.py`** — VADER + FinBERT (transformers optional dep)
6. **`backend/paper.py`** — paper trading book (pure Python, no external deps)
7. **`backend/hurricane.py`** — NOAA NHC (no API key)
8. **`backend/ais.py`** — aisstream.io WebSocket (requires key)
9. **`backend/main.py`** — wire all modules into snapshot + WebSocket loop
10. **`frontend/src/store/dashboardStore.ts`** — switch to WebSocket, update snapshot type
11. **`frontend/src/components/BollingerBandsChart.tsx`**
12. **`frontend/src/components/CovarianceMatrix.tsx`**
13. **`frontend/src/components/STEOBalance.tsx`**
14. **`frontend/src/components/FiveYearRange.tsx`**
15. **`frontend/src/components/COTPanel.tsx`** — upgrade existing
16. **`frontend/src/components/SeasonalityChart.tsx`**
17. **`frontend/src/components/PaperTrading.tsx`**
18. **`frontend/src/components/KalmanFilter.tsx`**
19. **`frontend/src/components/StormWatch.tsx`**
20. **`frontend/src/components/TankerWatch.tsx`**
21. **`frontend/src/components/AnalystWatch.tsx`**
22. **`frontend/src/components/TradingViewWidget.tsx`**
23. **`frontend/src/components/CalendarSpreadMatrix.tsx`**
24. **`frontend/src/components/SpreadCovMatrix.tsx`**
25. **`frontend/src/App.tsx`** — add "Pro Tools" tab, wire all components
26. **`frontend/src/components/Header.tsx`** — add WS indicator, FinBERT badge

---

## 10. What to Keep from Your Original Dashboard (Do NOT Overwrite)

| Component | Keep as-is | Notes |
|---|---|---|
| `signal_calc.py` | ✅ | Already has EMA, ATR, Bollinger, composite score — import into `indicators.py` |
| `price_fetcher.py` | ✅ | Yahoo Finance API fetching logic is solid |
| `news_fetcher.py` | Partially | Keep RSS scraping, add dual-sentiment engine on top |
| `eia_fetcher.py` | ✅ | EIA weekly + anchor logic is complete |
| `macro_fetcher.py` | ✅ | Keep DXY, 10Y, SPX, PMI fetching |
| `database.py` | ✅ | Keep SQLite persistence |
| Zustand store structure | Extend | Add `snapshot` slice, keep existing slices |
| Recharts charts | Keep | Use for new panels too — consistent library |
| `AlertStrip.tsx` | ✅ | Keep auto-refresh every 5s |
| `SpreadsPanel.tsx` | Upgrade | Add Kalman z-score to each spread card |
| All existing tabs | Upgrade in-place | Do not re-create from scratch |
| CSS variables / dark theme | ✅ | Extend with new color vars (Section 5.2) |

---

## 11. Features from Reference Dashboard That Are Explicitly OUT OF SCOPE

Do not implement these — they require paid data sources or are out of trader utility scope:

- BDTI Baltic freight index (Baltic Exchange paid-only) → show static placeholder if needed
- Options chain / implied vol surface (paid)
- Physical cargo flows / Kpler (paid)
- Real-time refinery outage overlay (Genscape, paid)
- Pipeline utilization (Genscape, paid)
- Satellite AIS open-ocean coverage (paid)

---

## 12. Testing Checklist (Claude Code to Verify Before Done)

- [ ] WebSocket connects and delivers snapshot within 5s of page load
- [ ] WebSocket auto-reconnects after 2s disconnect (test by killing backend)
- [ ] All panels show skeleton while data is `null`, not blank white space
- [ ] Panels with simulated/fallback data show dashed border + "SIMULATED" badge
- [ ] FinBERT status badge updates after model loads (async, can take 30s)
- [ ] Paper trading book persists across backend restart (`paper_state.json`)
- [ ] Storm Watch shows "No active storms" gracefully when NOAA returns empty
- [ ] AIS panel shows "AIS offline" gracefully when aisstream key is missing
- [ ] STEO panel is hidden (not blank) when EIA STEO endpoint returns null
- [ ] Calendar spread matrix auto-refreshes every 3 min independently
- [ ] COT shows "As of [date]" badge and warns if data is >8 days old
- [ ] TradingView widgets load only when "Pro Tools" tab is first activated (lazy)
- [ ] Header fixed bar does not overlap page content (check on mobile width)
- [ ] `npm run build` exits 0 with no TypeScript errors

---

## 13. Honest Limitations to Document in the UI

Add a "Data Sources" modal (info icon in header) that states:

- WTI/Brent prices: 15-min delayed (Yahoo Finance free API)
- EIA fundamentals: weekly data, 30-min refresh cadence
- CFTC COT: weekly data, published Fridays for prior Tuesday's positions
- STEO: monthly EIA publication (~10th of month, 18-month forecast horizon)
- AIS tankers: terrestrial coverage only (~40 mi from shore), free tier
- FinBERT sentiment: transformer model — async, may take 30s to load on cold start
- Analyst watch: Google News mentions as free Twitter/X proxy (Twitter API = $100+/mo)
- Refinery utilization seasonality: 5-year EIA historical norm, not real-time outage data

---

*End of Specification — Oil Market Dashboard v2.0*
*Generated May 2026 | Build target: React 18 + Vite + FastAPI + Python 3.12*
