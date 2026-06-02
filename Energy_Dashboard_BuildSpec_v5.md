# ENERGY MARKET DASHBOARD — Build Specification v5.0
### For Claude Code | Docker Deployment | React + TypeScript + FastAPI

---

## OVERVIEW & PHILOSOPHY

This dashboard is the daily start screen for an oil macro trader who has read and internalized the full supply chain — upstream, midstream, downstream, inventory, geopolitics. The guiding principle from that book applies directly here: **price signals emerge from bottlenecks anywhere in the chain, not just headline supply/demand**. The dashboard must reflect this layered reality.

### What Changed from v4 (Key Decisions)

| v4 Approach | v5 Decision | Reason |
|---|---|---|
| 8 tabs including separate Correlation tab | **5 tabs** — correlation matrix integrated into Overview | Correlation is context, not a destination. Analysts glance at it, not dwell on it |
| Positioning tab (CFTC) as standalone | **CFTC integrated into Overview + Inventory tab** | COT data is a sizing modifier, not a primary view |
| Twitter/X intelligence feed | **Removed** | Requires paid API ($100+/mo), unreliable access, and RSS + NLP pipeline covers the same signal at zero cost |
| Covariance matrix standalone | **Integrated as compact rolling-beta + correlation strip in Overview** | Same information, 1/10th the real estate |
| Fair value regression with manual R² display | **Simplified to 3-factor score with confidence band** | Multi-factor OLS with a noisy China proxy was showing LOW MODEL CONFIDENCE 40% of the time — useless in practice |
| Freight (BDTI/TD3C) in Price tab | **Moved to Inventory & Supply tab** | Freight is a midstream/supply signal, not a price chart signal |

### 5 Tabs

1. **Overview** — The daily start screen. Everything that matters in one view.
2. **Prices & Spreads** — Charts, EMAs, Bollinger Bands, crack spreads, curve shape.
3. **Inventory & Supply** — EIA suite, Baker Hughes, OPEC compliance, spare capacity, freight.
4. **Seasonality** — Forward curve, calendar spreads, heatmap, demand trackers.
5. **News & Macro** — NLP feed, geopolitical heatmap, macro indicators, China module.

---

## TECH STACK

### Frontend
| Layer | Technology | Version |
|---|---|---|
| Framework | React + TypeScript | React 18, TS 5 |
| Build | Vite | v5 |
| Styling | Tailwind CSS | v3 |
| Charts | Recharts (primary) | v2 |
| Heavy charts | lightweight-charts (TradingView) | v4 — WTI intraday only |
| State | Zustand | v4 |
| Data fetching | TanStack Query | v5 |
| NLP | Hugging Face Inference API | ProsusAI/finbert |

### Backend
| Layer | Technology |
|---|---|
| API framework | FastAPI (Python 3.11) |
| Scheduler | APScheduler |
| Database | SQLite (dev) → TimescaleDB (prod) |
| Price data | Yahoo Finance chart API microservice (free, 15-min delay) → swap for broker WS |
| ORM | SQLAlchemy |

### Infrastructure
| Component | Spec |
|---|---|
| Container | Docker Compose (frontend + backend + db as 3 services) |
| Frontend port | 3000 |
| Backend port | 8000 |
| DB port | 5432 (TimescaleDB) or SQLite file mount |
| Reverse proxy | Nginx (optional, production only) |

---

## DOCKER SETUP

### `docker-compose.yml` (root of project)

```yaml
version: '3.9'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - EIA_API_KEY=${EIA_API_KEY}
      - HF_API_KEY=${HF_API_KEY}
      - DATABASE_URL=sqlite:///./energy.db
    volumes:
      - ./backend:/app
      - energy_db:/app/data
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_BASE=http://localhost:8000
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  energy_db:
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### `frontend/Dockerfile`

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

---

## DESIGN SYSTEM

### Visual Aesthetic: "Trading Terminal Refined"

The aesthetic is institutional dark — the feel of a Bloomberg terminal redesigned with 2025 design sensibility. Dense information, zero decoration, every pixel earns its place. Think S&P Platts Dimensions Pro meets a bespoke quant desk tool.

**Color palette (CSS variables)**:
```css
:root {
  --bg-primary: #080E18;      /* Near-black navy — deepest layer */
  --bg-secondary: #0D1829;    /* Card backgrounds */
  --bg-tertiary: #111F35;     /* Nested panels, table rows */
  --border: #1E3050;          /* Subtle borders */
  --border-bright: #2A4570;   /* Active/hover borders */

  --text-primary: #E8EEF7;    /* Primary text — warm white */
  --text-secondary: #8BA3C7;  /* Labels, metadata */
  --text-muted: #4A6A96;      /* Timestamps, de-emphasis */

  --accent-blue: #3B82F6;     /* Primary accent — EMA lines, active states */
  --accent-cyan: #06B6D4;     /* Secondary accent — Brent, ICE products */

  --bull: #10B981;            /* Bullish green */
  --bull-dim: #064E3B;        /* Bullish background */
  --bear: #EF4444;            /* Bearish red */
  --bear-dim: #450A0A;        /* Bearish background */
  --neutral: #6B7280;         /* Neutral grey */
  --amber: #F59E0B;           /* Warning / elevated */
  --amber-dim: #451A03;       /* Warning background */

  --header-bg: #050B14;       /* Header — darker than everything */
}
```

**Typography**:
- Display / headers: `'DM Mono'` (Google Fonts) — monospaced, terminal feel, but refined
- Body / labels: `'Inter'` — clean legibility at small sizes
- Prices (large numbers): `'Bebas Neue'` or `'DM Mono'` — numerical impact

**Layout rules**:
- Header: `48px` fixed height, always on top
- Tab bar: `44px` below header
- Content area: fills remaining viewport, scrollable per-tab
- Cards: `border-radius: 6px`, `border: 1px solid var(--border)`, `background: var(--bg-secondary)`
- Grid: 12-column grid system, cards snap to 3/4/6/12 column widths
- Spacing: 8px base unit. Padding within cards: 16px. Gap between cards: 12px.

**Micro-interactions**:
- Price updates: 400ms flash animation (green flash for up, red flash for down) on value change
- Stale data badge: pulsing amber dot in corner of affected widget
- Badge pill: `border-radius: 999px`, all-caps, `font-size: 10px`, `letter-spacing: 0.08em`
- Tab active: bottom border 2px `var(--accent-blue)`, text `var(--text-primary)`
- Tab hover: background `var(--bg-tertiary)`

---

## FILE STRUCTURE

```
energy-dashboard/
├── docker-compose.yml
├── .env.example
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── store/
│       │   └── useStore.ts              # Zustand: prices, signals, alerts, settings
│       ├── hooks/
│       │   ├── usePrices.ts             # 30s polling — all 5 products + DXY, SPX, HH
│       │   ├── useEIA.ts                # Wednesday refresh — all 10 EIA series
│       │   ├── useRigCount.ts           # Friday refresh — Baker Hughes
│       │   ├── useCFTC.ts               # Friday refresh — COT report
│       │   ├── useNews.ts               # 60s polling — NLP-ranked bulletin
│       │   ├── useMacro.ts              # Mixed cadence — yields, PMI, China data
│       │   └── useSignals.ts            # 5-min polling — composite score
│       ├── components/
│       │   ├── Header/
│       │   │   ├── HeaderBar.tsx        # Fixed top bar
│       │   │   ├── PricePill.tsx        # Single product price + delta
│       │   │   ├── RegimeBadge.tsx      # BULL/BEAR/NEUTRAL pill
│       │   │   └── AlertTicker.tsx      # Scrolling top alert
│       │   ├── shared/
│       │   │   ├── Card.tsx             # Base card wrapper
│       │   │   ├── Badge.tsx            # Coloured pill badge
│       │   │   ├── StaleBadge.tsx       # Pulsing amber stale indicator
│       │   │   ├── SignalTag.tsx        # [L] [C] [Lg] tag
│       │   │   ├── Gauge.tsx            # Semicircular dial component
│       │   │   └── SparkBar.tsx         # Tiny bar chart for sub-scores
│       │   └── charts/
│       │       ├── PriceChart.tsx       # Recharts line chart with EMA overlays
│       │       ├── WTITVChart.tsx       # TradingView lightweight-charts (WTI only)
│       │       ├── CrackChart.tsx       # Crack spread chart with annotations
│       │       ├── CalendarSpreadChart.tsx
│       │       └── HeatmapGrid.tsx      # Seasonality heatmap
│       ├── tabs/
│       │   ├── OverviewTab.tsx          # Tab 1 — daily start screen
│       │   ├── PricesTab.tsx            # Tab 2 — charts and spreads
│       │   ├── InventoryTab.tsx         # Tab 3 — EIA, rigs, OPEC, freight
│       │   ├── SeasonalityTab.tsx       # Tab 4 — curve, calendar spreads, heatmap
│       │   └── NewsTab.tsx              # Tab 5 — NLP feed, geopolitics, macro
│       ├── lib/
│       │   ├── signals.ts               # Composite score engine (pure functions)
│       │   ├── crack.ts                 # 3:2:1 and Brent-GO crack calculations
│       │   ├── spreads.ts               # Calendar spread and Brent-WTI spread
│       │   ├── seasonality.ts           # Historical week range, heatmap data
│       │   ├── stale.ts                 # Stale data detection per source cadence
│       │   ├── correlation.ts           # Pearson correlation + rolling beta
│       │   └── formatting.ts            # Price formatters, unit converters
│       └── types/
│           └── index.ts                 # All TypeScript interfaces
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                          # FastAPI entry point
    ├── database.py                      # SQLAlchemy setup
    ├── scheduler.py                     # APScheduler jobs
    ├── routers/
    │   ├── prices.py                    # /api/prices/{symbol}
    │   ├── eia.py                       # /api/eia/weekly
    │   ├── rigs.py                      # /api/rigs/latest
    │   ├── cftc.py                      # /api/cftc/latest
    │   ├── news.py                      # /api/news/bulletin + /api/news/sentiment
    │   ├── macro.py                     # /api/macro/all
    │   ├── signals.py                   # /api/signals/composite
    │   └── spreads.py                   # /api/spreads/calendar
    ├── services/
    │   ├── price_fetcher.py             # Yahoo Finance chart API polling
    │   ├── eia_fetcher.py               # EIA Open Data API
    │   ├── rig_fetcher.py               # Baker Hughes Excel parser
    │   ├── cftc_fetcher.py              # CFTC CSV parser
    │   ├── news_fetcher.py              # RSS ingestion + FinBERT scoring
    │   └── macro_fetcher.py             # FRED, Yahoo for macro series
    └── models/
        ├── price.py
        ├── inventory.py
        └── news.py
```

---

## PERSISTENT HEADER BAR

**Height**: 48px. **Position**: `fixed`, `top: 0`, `z-index: 1000`. **Background**: `var(--header-bg)`.

Left to right layout:

```
[BULL/BEAR] [HIGH-VOL] | WTI $XX.XX ▲0.3% | RBOB XXX.X ▲0.2% | HO XXX.X | BRENT $XX.XX (+1.2) | GO $XXX | DXY 104.2 ▼0.1% | ████░░ +42 | ⚑ OPEC+ compliance 89% — IEA flags Iraq overproduction ›
```

| Element | Content | Refresh | Behaviour |
|---|---|---|---|
| Regime badge | BULLISH / BEARISH / NEUTRAL | 5 min | Green/Red/Grey pill. Click → composite breakdown modal |
| Vol regime | LOW / ELEVATED / HIGH-VOL | Daily | Cyan/Amber/Red. Tooltip shows annualised vol % |
| WTI | $ + Δ1d% + arrow | 30s | Flash on change |
| RBOB | ¢/gal + Δ1d% | 30s | Flash |
| HO | ¢/gal + Δ1d% | 30s | Flash |
| Brent | $ + (CL-Brent spread) | 30s | Spread in brackets, e.g. `(+1.4)` |
| GO | $/mt + Δ1d% | 30s | Flash |
| DXY | Level + Δ1d% | 30s | Red flash if │Δ│ > 0.5% |
| Composite bar | −100→+100 mini fill bar + number | 5 min | Thin progress bar |
| Alert ticker | Top-priority NLP headline | Continuous | Marquee if long. Click → News tab |

---

## TAB 1 — OVERVIEW

*The daily start screen. Target: complete market picture in under 10 seconds.*

### Section 1.1: Composite Signal Row (3 cards, full width)

**Card A — Composite Score Gauge**
- Semi-circular dial, −100 to +100. Needle + number displayed large.
- Below dial: horizontal decomposition bar showing each sub-score contribution:
  - EMA Trend (40%) | News Sentiment (20%) | CFTC Positioning (20%) | EIA Surprise (10%) | Seasonality (10%)
- Each segment clickable → tooltip showing sub-score current value, what it means, and its contribution to total.
- Colour: green if > +30, red if < −30, amber otherwise.

**Card B — Volatility Regime Panel**
- Current regime badge (large): LOW / ELEVATED / HIGH-VOL
- 20-day realized vol (annualised %) displayed as large number
- Sparkline of 90-day vol history, shaded into tertiles
- Current regime governs Bollinger Band width app-wide (2σ → 3σ in HIGH-VOL)
- Position sizing modifiers shown: `Base × Vol scalar = Adjusted` with the scalar highlighted

**Card C — Position Sizing Output**
- Analyst inputs base contract size in Settings (persisted to localStorage).
- Widget shows: `Suggested: X contracts`
- Formula shown: `Base (10) × Score scalar (0.42) × Vol scalar (0.75) = 3 contracts`
- Active modifiers listed as pills: CROWDED LONG × 0.5 | HIGH-VOL × 0.75
- LOW MODEL CONFIDENCE modifier (−25%) activates when fair value R² < 0.55

### Section 1.2: Five-Product Snapshot Grid

Two groups: **WTI Group** (WTI, RBOB, HO) and **Brent Group** (Brent, GO).

Each product card contains:
- Product name + exchange badge (CME or ICE) — top left
- Live price (large, `Bebas Neue` font) + Δ1d% + directional arrow — center
- 5-day change % | 20-day realized vol % — secondary row
- EMA signal: `ABOVE 20` / `BELOW 20` / `EMA CROSS` — colour-coded badge
- Bollinger position: `UPPER BAND` / `LOWER BAND` / `MIDDLE` / `SQUEEZE ALERT`
- Product-specific spread:
  - WTI: CL-Brent spread value
  - RBOB: 3:2:1 crack value ($/bbl)
  - HO: Distillate stocks vs 5-yr avg (% above/below)
  - Brent: CL-Brent spread (same as WTI, inverse perspective)
  - GO: Brent-GO crack ($/bbl)
- STALE DATA badge if data > 2 min during market hours
- **No sparklines** — full charts are in Tab 2. Numbers only.

### Section 1.3: High-Priority Alert Feed

Scrollable table. Only HIGH and MEDIUM severity alerts. Columns: `TIME | ALERT | CONDITION | ACTION`.

| Alert | Severity | Trigger | Recommended Action |
|---|---|---|---|
| Large EIA surprise | HIGH | Draw/build > 2× consensus | Check Cushing backwardation confirmation |
| Crack spread collapse | HIGH | 3:2:1 < $12/bbl for 5+ sessions | Run-cut risk — reduce longs |
| Geopolitical disruption | HIGH | NLP flags disruption > 0.5 mbd | Cross-check spare capacity before acting |
| Backwardation signal | HIGH | M1-M2 > +$1.50/bbl | Physical tightness — long per sizing |
| CFTC extreme positioning | MEDIUM | Net MM in top/bottom 10% of 52wk | Apply 0.5× size modifier |
| DXY sharp move | MEDIUM | Δ > ±0.7% | Expect crude reaction in 1–3 sessions |
| Bollinger Squeeze | MEDIUM | Band width in bottom 10% of 90-day | Vol expansion imminent — await EMA direction |
| Rig count major drop | MEDIUM | WoW change > −20 | Bullish supply signal 6–9 months forward |
| OPEC meeting T−7 | MEDIUM | Calendar trigger | Review IEA compliance, read OPEC SG statement |

### Section 1.4: Compact Analytics Strip (3 panels in one row)

**Panel A — Rolling Correlation Heatmap (compact)**
Instead of a full 5×5 matrix, show a **6-cell strip** of the most tradeable pairs:
- WTI/Brent | WTI/RBOB | WTI/HO | Brent/GO | WTI/DXY | WTI/SPX
- Each cell: pair name + 30-day Pearson r + colour (green ≥ 0.8, amber 0.6–0.8, red < 0.6)
- DECOUPLING badge when RBOB/WTI or GO/Brent drops below 0.6 (crack is moving independently)
- Window toggle: 30D / 60D / 90D

**Panel B — Rolling Beta Strip**
- RBOB β to WTI | HO β to WTI | GO β to Brent
- 90-day rolling regression. Current beta as large number. Sparkline of 90-day beta history.
- β > 1.0 badge: product moving more than crude = demand/supply at product level is dominant = crack trade timing signal.

**Panel C — Macro Context Tiles (read-only)**
Compact strip: DXY level + 30-day correlation + DRIVING/DECOUPLED | 10Y Yield + trend | SPX Δ1d | Henry Hub | Global PMI + above/below 50 | China Caixin PMI

---

## TAB 2 — PRICES & SPREADS

### Section 2.1: Live Price Charts (5 products)

Row of 5 chart cards. WTI uses `lightweight-charts` (TradingView) for tick-level intraday. Others use `Recharts LineChart`.

Each chart:
- Time window toggle: **1D / 5D / 1M**. Default: 1D.
- **EMA-20** (blue line) + **EMA-50** (orange line). Crossover points marked with ▲▼ triangle icons.
- **Adaptive Bollinger Bands**: ±2σ normal, ±3σ in HIGH-VOL regime. Upper/lower bands shaded 15% opacity.
- **Band Width Indicator**: thin bar below chart. When bottom 10% of 90-day range: `SQUEEZE ALERT` badge.
- Y-axis in native product units. X-axis in local time.
- STALE DATA overlay if data > 2 min during hours.

### Section 2.2: Spread Widgets (4 charts)

**CL-Brent Spread**
- WTI minus Brent, $/bbl. 6-month line chart.
- Horizontal annotations: `0` (parity, grey dash), `−3` (typical Brent premium, blue), `−5` (global tightness, amber).
- Interpretation guide shown as tooltip: `> −2: US exports competitive | < −5: global supply tight, Brent premium reflects disruption risk`
- Current value badge top-right.

**3:2:1 Crack Spread (WTI)**
- Formula: `(2×RBOB + 1×ULSD − 3×WTI) ÷ 3` in $/bbl.
- 12-month chart with Bollinger Bands applied.
- Horizontal annotations: `$10` (run-cut warning, red), `$20` (normal, grey), `$30` (exceptional, green).
- Flash alert widget below: shows count of consecutive sessions below $12 (activates at 5).
- Interpretation: `< $12: refiners cutting runs, crude demand falls | > $30: refiners running max, crude demand pull`

**Brent-GO Crack Spread**
- Gas Oil minus Brent, $/bbl (unit-converted from $/mt: divide by 7.45).
- Same layout as 3:2:1. Normal range $15–25/bbl.
- **Unit conversion note displayed on chart**: `GO $/mt ÷ 7.45 = $/bbl equivalent`

**RBOB-HO Spread**
- RBOB minus HO, $/bbl equivalent. 6-month chart.
- Seasonal annotation bands: `Q2 — RBOB typically premium (driving season)` | `Q4 — HO typically premium (heating season)`.
- Use to time relative product positioning.

### Section 2.3: Fair Value Estimate

Card showing:
- **Spot vs Fair Value** with PREMIUM/DISCOUNT badge and $ amount
- **Confidence band**: `Fair value: $78.20 ± $3.10`
- **Model R²**: shown as a small number. If < 0.55: `LOW MODEL CONFIDENCE` badge in amber, number greyed
- **3-factor model** (simplified from v4 for reliability):
  - Factor 1: EIA inventory deviation from 5-yr avg (OECD proxy)
  - Factor 2: DXY level (FX driver)
  - Factor 3: CFTC net MM positioning (positioning premium/discount)
- Recalculated daily. Training data: 5 years weekly observations (enough for stable coefficients; 10yr includes structural breaks)
- **What changed vs v4**: Removed China demand proxy and OPEC compliance rate from regression. Both are imprecise inputs that added noise. They remain in the dashboard as contextual signals (News/Macro tab), but not in the price model.

---

## TAB 3 — INVENTORY & SUPPLY

### Section 3.1: EIA Weekly Petroleum Status

All series update Wednesday 10:30 ET. Each widget: current value | WoW change | vs 5-yr avg | STALE badge if not refreshed.

**Source**: EIA Open Data API — `https://api.eia.gov/v2/` (free API key at eia.gov).

| Widget | EIA Series ID | Chart Type | Key Annotation | Signal Type |
|---|---|---|---|---|
| Crude inventory (weekly change) | PET.WCRSTUS1.W | Bar (WoW change) | 5-yr avg overlay + surprise vs consensus | [C] |
| Crude stock level (5-yr range) | PET.WCRSTUS1.W | Line in min/max band | Lower half = bullish; upper half = bearish | [C/Lg] |
| Cushing hub level | PET.WCUSSTUS1.W | Line + level badge | Very low → backwardation flag | [C] |
| Gasoline stocks | PET.WGTSTUS1.W | Bar + 5-yr band | Draw = demand proxy bullish | [C] |
| Distillate stocks | PET.WDISTUS1.W | Bar + 5-yr band | Q4 critical; low = HO + GO bullish | [C] |
| SPR level | PET.WCSSTUS1.W | Line + direction | Releases suppress price; refills support | [Lg] |
| US crude production | PET.WCRFPUS2.W | Line vs rig-model forecast | 6–9mo lag comparison | [Lg] |
| Refinery utilization | PET.WPULEUS2.W | Gauge dial + seasonal avg | > 90% = demand pull; < 85% = run-cut risk | [C] |
| Crude imports | PET.WCRIMUS2.W | Bar chart weekly | Rising = US refiner demand for foreign grades | [C] |
| Crude exports | PET.WCREXUS2.W | Bar chart weekly | High exports → Cushing draws expected | [C] |

**Inventory surprise widget**: Show consensus estimate (from Bloomberg/Reuters poll data if available, else prior 4-week average as proxy) vs actual. Large green number for draw surprise, red for build surprise.

**Days of forward demand cover**: `Total OECD commercial stocks ÷ daily demand`. Key thresholds: `< 54 days = historically associated with Brent > $90` | `56–62 days = normal` | `> 66 days = oversupplied`. Shown as a gauge.

### Section 3.2: Baker Hughes Rig Count

- Source: Baker Hughes `rigcount.bakerhughes.com` — free Excel download, Fridays 13:00 ET. Parse with openpyxl.
- Display: Total US oil rigs + Permian Basin sub-count (most important — ~45% US output).
- WoW change + YoY change.
- 52-week trend line. Annotated: `implied 6-month production change = +/− X kbd` based on rig productivity lag model.
- **Rig-count to production rule** (from book):
  - `> 600 active rigs` → shale growing 300–500 kbd/yr
  - `400–600 rigs` → roughly flat (treadmill)
  - `< 350 rigs` → production declining within 6 months
- Alert: WoW change > −20 → MEDIUM alert fires.

### Section 3.3: Global Spare Capacity

- Sources: OPEC MOMR (monthly, ~12th–14th) and IEA OMR (monthly, ~11th–13th).
- Show OPEC estimate and IEA estimate **side by side**. If divergence > 0.5 mbd: `AGENCY DIVERGENCE` flag.
- Gauge dial with threshold bands:
  - `> 4 mbd` = GREEN — comfortable, geopolitical premium suppressed
  - `2–4 mbd` = AMBER — moderate risk, disruptions cause noticeable moves
  - `1–2 mbd` = ORANGE — vulnerable, outsized reactions likely
  - `< 1 mbd` = RED — critical, structural risk premium
- Show date of last MOMR and OMR used.
- **Rationale from book**: Spare capacity is the denominator that converts news into price. A 0.5 mbd Nigeria disruption in a 4.5 mbd spare world is noise; same disruption at 1.5 mbd spare is a crisis. This widget gives the analyst that context instantly.

### Section 3.4: OPEC Production Compliance Tracker

- Official quota per member (from OPEC press releases) vs IEA secondary-source estimated actual.
- Compliance rate = actual ÷ target. OVER-PRODUCING / COMPLIANT / UNDER-PRODUCING badge per member.
- **Both figures must show** — OPEC self-reporting is unreliable. IEA cross-check is authoritative.
- Headline compliance rate shown prominently (weighted average).
- **OPEC event countdown**: if next meeting ≤ 7 days, display `T−X DAYS TO OPEC` banner in orange at top of this section and in the header.

### Section 3.5: Freight Rates (Midstream Signal)

**Why freight is in this tab, not Price tab**: Freight is a midstream/supply signal. It tells you the cost of moving crude between regions, which affects which crudes refiners buy and where arbitrages close. It belongs next to inventory and supply data.

**TD3C VLCC Freight** (Arabian Gulf → China):
- Worldscale and $/mt. 30-day rolling chart + 20-day MA.
- Source: Baltic Exchange via investing.com or broker API.
- Interpretation: `High TD3C = Asian refiners bidding hard for Middle East crude = bullish demand signal | Elevated TD3C = arb cost narrows, inter-regional trades close`

**BDTI (Baltic Dirty Tanker Index)**:
- Broader inter-regional crude flow cost. 30-day chart + 20-day MA.
- Source: investing.com/indices/baltic-dirty-tanker.
- `BDTI spike = rerouting event (e.g. Houthi/Red Sea) = check freight vs prior 30-day avg`

### Section 3.6: CFTC COT Positioning (Integrated Here)

*In v4 this was a separate tab. In v5 it integrates here as a supply-side context panel.*

- Data source: CFTC free download `cftc.gov`. Updated Fridays 15:30 ET, covers prior Tuesday.
- Show for WTI, RBOB, HO as 3 side-by-side mini panels.
- Each panel: horizontal bar of Managed Money net long/short. 52-week range as shaded background.
- `CROWDED LONG` (red) when in top 10% of 52-week range — contrarian signal, apply 0.5× size modifier.
- `CROWDED SHORT` (green inverse) when bottom 10%.
- Producer/Merchant hedger positioning: heavy producer shorts at current price = E&P companies locking in → forward supply ceiling signal.

---

## TAB 4 — SEASONALITY

### Section 4.1: Forward Curve Shape (M1–M12)

Full-width line chart. WTI M1–M12 + Brent M1–M12 on same chart.

- Daily update from CME/ICE settlement prices.
- Annotation: `CONTANGO` (downward slope = oversupplied, storage incentivised) vs `BACKWARDATION` (upward slope = physical tightness, no storage incentive).
- `CURVE SHAPE` badge based on slope of M1-M3:
  - M1 > M2 > M3: `BACKWARDATION` (green)
  - M1 < M2 < M3: `CONTANGO` (red)
  - Mixed: `FLAT` (grey)
- Annotation line: "Full carry cost ≈ $1.5–3/bbl/month — contango beyond this level triggers storage builds"
- **Rationale from book**: The forward curve shape is not a forecast — it is the market's current best estimate of fair value at each delivery date. Backwardation signals physical scarcity and no storage incentive.

### Section 4.2: Calendar Spread Charts (M1-M2, M2-M3, M3-M4)

Three side-by-side charts, 90-day history. Zero-reference line dashed in grey.

Signal logic (show as badge beneath all three charts):
- All three positive: `STRUCTURAL TIGHTNESS` (highest-conviction long signal) — green banner
- All three deeply negative (< −$0.50): `INVENTORY BUILD` (bearish) — red banner
- Mixed: `MIXED CURVE` — grey

Each chart shows:
- Current spread value (large badge)
- Zero-line annotation
- M1-M2 specific: flag when crosses zero from negative to positive (bullish flip)

**Rationale from book**: Time spreads move more in response to physical signals than outright prices. A spike in M1-M2 into backwardation intraday = physical player urgently needs prompt barrels.

### Section 4.3: Five-Year Historical Week Range

For each of 5 products: show current ISO week's min, max, and 5-yr average from prior 5 years vs today's price.

- Data: FRED `DCOILWTICO` for WTI; Yahoo Finance chart/historical API for others.
- Display as a range bar with today's price as a dot overlay.
- `BELOW 5-YR MIN` badge in green when today's price is cheaper than it has been at this time of year in any of the past 5 years.
- `ABOVE 5-YR MAX` badge in red.

**Trade rule (from book — IMPORTANT)**:
> Show this disclaimer as a tooltip: "This is a context signal only. Markets can stay structurally cheap for extended periods (see 2015–2016 shale oversupply). Use this alongside M1-M2 spread: price below 5-yr minimum + M1-M2 flipping to backwardation = high-conviction entry. Price below minimum alone = insufficient."

### Section 4.4: Seasonality Heatmap

12 columns (Jan–Dec) × 10 rows (10 most recent calendar years). Each cell = average monthly return for that product in that month-year.

- Colour scale: green (positive) → white (zero) → red (negative), proportional to magnitude.
- Bottom row: 10-year monthly average return.
- Current month highlighted with bright border.
- Product selector dropdown: default WTI, switchable to any of 5 products.
- **Note**: This is the [Lg] lagging signal — seasonal tendencies are real but not guarantees. Use to set directional bias, not as an entry trigger.

### Section 4.5: Seasonal Demand Trackers

**Driving Season (Q2 — RBOB signal)**:
- Countdown timer: days to Memorial Day (last Mon of May) and Labor Day (first Mon of Sep).
- Gasoline stock draw rate vs 5-yr seasonal average for current week.
- `BULLISH RBOB WINDOW` badge active May–Aug.
- Source: EIA gasoline stocks.

**Heating Season (Q4 — HO + GO signal)**:
- Countdown: days to peak HDD period (typically Jan–Feb).
- Heating Degree Days (HDD) vs 5-yr average (NOAA data).
- Distillate draw rate vs seasonal norm.
- `BULLISH HO/GO WINDOW` badge Oct–Feb.

**Refinery Maintenance Windows**:
- Two annotated bands on utilization charts:
  - Spring: Feb–Mar (utilisation dips 3–5%)
  - Fall: Sep–Oct
- During these windows: expect crude builds + product draws simultaneously (counter-intuitive to normal).
- `SPRING TURNAROUND` / `FALL TURNAROUND` badge with explanation tooltip.

---

## TAB 5 — NEWS & MACRO

### Section 5.1: Priority News Bulletin

Scrollable feed, top 10 NLP-ranked items.

**Data pipeline**:
1. RSS ingestion via `feedparser` (Python) from 4 sources (below)
2. FinBERT sentiment scoring via Hugging Face Inference API (`ProsusAI/finbert`)
3. Geopolitical entity detection (regex + small NER model)
4. Priority score: `sentiment_magnitude × entity_weight × source_weight`
5. Stored in DB, frontend polls every 60 seconds.

**RSS Sources**:
- Reuters business news: `https://feeds.reuters.com/reuters/businessNews`
- OilPrice.com: `https://oilprice.com/rss/main`
- Rigzone: `https://www.rigzone.com/news/rss/rigzone_news.aspx`
- OPEC press room: `https://www.opec.org/opec_web/en/press_room/rss.htm`

**Entity importance weights** (for priority ranking):
- Saudi Arabia, Strait of Hormuz, OPEC: 1.0
- Russia, Iran: 0.95
- Iraq, UAE: 0.85
- Libya, Nigeria, Venezuela: 0.75
- SPR, US Gulf Coast: 0.70

**Source authority weights**:
- Reuters: 1.0 | Bloomberg: 0.95 | S&P Global Platts: 0.95
- OilPrice.com: 0.75 | Rigzone: 0.70

Each item displays:
`HEADLINE | SOURCE | TIME | SENTIMENT SCORE −1→+1 (coloured badge) | REGION TAG | KEYWORD TAGS`

OPEC and `SUPPLY DISRUPTION` items pinned to top regardless of score.

### Section 5.2: Sentiment Trend Line

- 5-day rolling average of all news sentiment scores.
- Exponential decay: `decay_factor = 0.85 per day` (recent articles weighted more heavily).
- 30-day chart.
- `SENTIMENT DIVERGENCE` badge when sentiment falling while price holding (early warning).
- Contributes 20% to composite score.

### Section 5.3: Geopolitical Risk Heatmap

8 producing regions as traffic-light cards in a 4×2 grid:
Saudi Arabia | Russia | Iran | Iraq | Libya | Nigeria | Venezuela | US Gulf Coast

Each card:
- Region name + flag emoji
- Risk level: `GREEN` / `AMBER` / `RED`
- Latest relevant headline (from NLP feed)
- Estimated supply disruption risk in mbd
- **Global spare capacity shown on same card** (pulled from Section 3.3)

Risk level logic:
- RED: NLP flagged disruption risk > 0.5 mbd in last 24 hours
- AMBER: 0.1–0.5 mbd flagged
- GREEN: otherwise

**Critical — spare capacity context**: The spare capacity figure MUST appear on every card. This is the single most important contextual fix vs generic dashboards. A RED card at 4.5 mbd spare is not a trade trigger. A RED card at 1.5 mbd spare is.

**Geopolitical risk premium fade pattern** (shown as tooltip on each card):
> "Geopolitical spikes typically fade 50–80% within 30 days as rerouting/replacement supply is identified. Buy the spike only if supply is genuinely disrupted AND spare capacity is insufficient to absorb it."

### Section 5.4: Core Macro Indicators

| Indicator | Source | Refresh | Signal |
|---|---|---|---|
| DXY Index | Yahoo `DX-Y.NYB` | 30s | 30-day WTI correlation + DRIVING/DECOUPLED badge |
| US 10Y Yield | Yahoo `^TNX` | 30s | Level + Δ1d + UP/DOWN trend badge |
| S&P 500 | Yahoo `^GSPC` | 30s | Level + Δ1d% + 30-day WTI correlation |
| Henry Hub | Yahoo `NG=F` | 30s | $/MMBtu + Δ1d% |
| Global PMI | Manual entry / FRED | Monthly | Latest reading + above/below 50 badge + month label |
| China Caixin PMI | Manual entry / FRED | Monthly | Latest + vs NBS PMI divergence if > 2pt |
| China NBS PMI | Manual entry | Monthly | Badge only |
| US ISM Manufacturing | FRED `NAPM` | Monthly | Latest + new orders sub-index |

**DXY Correlation Panel**: When 30-day WTI-DXY Pearson r < −0.6: show `DXY DRIVING` badge (FX is primary price driver; watch Fed). When near zero: `DECOUPLED` badge (geopolitical/supply factors overriding dollar).

### Section 5.5: China Demand Module

**Why this module is essential (from book)**:
> "When Chinese imports significantly exceed estimated refinery runs plus exports, the missing barrels are assumed to be going into SPR or strategic storage. This represents real demand that does not appear in OECD stocks."

Display:
- China crude import proxy: monthly import volume (GACC customs data, sourced from FRED or manual update) vs NBS refinery throughput estimate.
- Gap calculation: `Imports − Refinery runs = ±X mbd`. Positive = `SPR BUILD` signal (invisible demand). Negative = `INVENTORY RELEASE` (hidden supply).
- Economic composite tile: Industrial Production YoY% | Retail Sales YoY% | Fixed Asset Investment YoY% (most crude-intensive).
- Source: NBS China. Monthly cadence, manual update or API if available.

### Section 5.6: Refinery News Feed (OPEC Meeting Tracker integrated)

**OPEC Meeting Tracker** (pinned card at top of this section):
- Next OPEC/OPEC+ meeting date + `T−X days` countdown
- Official production target per member + IEA secondary-source estimated actual
- Compliance rate (IEA-verified). `COMPLIANT` / `NON-COMPLIANT` per member.
- Overall compliance rate prominently displayed.
- Warning label: "OPEC self-reporting is unreliable. IEA cross-check regularly finds compliance 10–20% below official figures. Always use IEA-verified figure."

**Refinery News Feed**:
- OilPrice.com RSS filtered for refinery/outage keywords.
- Each item: headline + timestamp + affected region + affected product tag.
- NLP-scored sentiment for product impact.
- If refinery outage flagged: bullish for that product, note next to EIA utilisation rate for that region.

---

## DATA ARCHITECTURE

### Backend API Endpoints

| Endpoint | Method | Returns | Refresh Logic | Failure Behaviour |
|---|---|---|---|---|
| `GET /api/prices/{symbol}` | GET | OHLCV + derived signals | 30s poll | Return last + STALE flag |
| `GET /api/eia/weekly` | GET | All 10 EIA series as JSON | Wed 10:30 ET scheduler | Return last week + STALE |
| `GET /api/rigs/latest` | GET | Total + Permian, WoW change | Fri 13:00 ET scheduler | Return prior week + STALE |
| `GET /api/cftc/latest` | GET | MM net, Producer net, OI | Fri 15:30 ET scheduler | Return prior week + STALE |
| `GET /api/news/bulletin` | GET | Top 10 NLP-scored items | 60s poll | Return cached + timestamp |
| `GET /api/news/sentiment/trend` | GET | 5-day rolling sentiment array | With each news poll | Return last computed |
| `GET /api/spreads/calendar` | GET | M1-M4 WTI prices + spreads | Daily from CME settlements | Return prior day + STALE |
| `GET /api/macro/all` | GET | DXY, 10Y, SPX, HH, PMIs | 30s live; monthly for PMIs | Per-series stale flags |
| `GET /api/signals/composite` | GET | Composite score + sub-scores | Every 5 minutes | Return last computed |

### Composite Score Calculation

**File**: `src/lib/signals.ts` — pure TypeScript functions.

```typescript
// Sub-scores each return a value from -1 to +1

// 1. EMA Trend (40%)
// EMA-20 > EMA-50 → +1 (bullish), EMA-20 < EMA-50 → -1 (bearish), cross → ±0.5
// Average across all 5 products

// 2. News Sentiment (20%)
// 5-day exponentially-decayed rolling average of FinBERT scores
// decay_factor = 0.85 per day

// 3. CFTC Positioning (20%)
// Net MM position as Z-score within 52-week range
// INVERTED: extreme long → -1 (contrarian bearish), extreme short → +1 (contrarian bullish)

// 4. EIA Inventory Surprise (10%)
// (Expected change − Actual change) ÷ |Expected change|
// Positive = draw bigger than expected = bullish. Capped at ±1.

// 5. Seasonality (10%)
// Current week's 10-year average return for WTI
// Positive historical average → positive contribution. Capped at ±1.

// Final: composite = Σ(weight × sub_score) × 100
// > +30 → BULLISH | < -30 → BEARISH | else NEUTRAL
```

### Stale Data Logic

**File**: `src/lib/stale.ts`. Each widget checks its own data timestamp against its expected cadence.

| Source | Staleness Threshold |
|---|---|
| Prices (all 5 products) | 2 min during market hours (09:00–20:00 ET Mon–Fri); no stale outside hours |
| EIA weekly series | 8 days |
| Baker Hughes rig count | 8 days |
| CFTC COT report | 8 days |
| News bulletin | 2 hours |
| OPEC/IEA spare capacity | 35 days |
| Correlation matrix | 26 hours |
| Fair value model | 26 hours |
| PMI data | 35 days |

### Key Calculations in `crack.ts`

```typescript
// 3:2:1 Crack Spread ($/bbl)
// RBOB in ¢/gal, ULSD in ¢/gal, WTI in $/bbl
function calc321Crack(rbob_cpg: number, ulsd_cpg: number, wti: number): number {
  const rbob_bbl = rbob_cpg * 42 / 100;
  const ulsd_bbl = ulsd_cpg * 42 / 100;
  return (2 * rbob_bbl + 1 * ulsd_bbl - 3 * wti) / 3;
}

// Brent-GO Crack Spread ($/bbl)
// GO in $/mt, Brent in $/bbl
// 1 MT gasoil ≈ 7.45 barrels (0.845 kg/L density)
function calcBrentGOCrack(go_per_mt: number, brent: number): number {
  const go_per_bbl = go_per_mt / 7.45;
  return go_per_bbl - brent;
}
```

---

## SETTINGS PANEL

Accessible via gear icon in header. Right-side overlay panel. Persisted to localStorage.

| Setting | Details |
|---|---|
| Base contract size | Integer. Used in position sizing widget on Overview tab |
| Composite threshold | BULL/BEAR threshold (default ±30). Allows calibration |
| Vol regime overrides | Option to manually set regime if auto-detect is lagging |
| EIA API key | Input field. Stored in localStorage (user-side). |
| HF API key | Hugging Face API key for FinBERT |
| Market hours timezone | Default: ET. Affects STALE badge logic |
| Theme | Dark (default). Light mode optional but not prioritised |

---

## DATA SOURCES SUMMARY

| Category | Source | API / URL | Cost | Notes |
|---|---|---|---|---|
| Price data (delayed) | Yahoo Finance chart API | HTTP API | Free | 15-min delay. Tickers: CL=F, RB=F, HO=F, BZ=F, DX-Y.NYB, ^GSPC, NG=F, ^TNX |
| Price data (live) | Interactive Brokers TWS / Alpaca | Broker WebSocket | Broker account | Swap in when available; Yahoo Finance chart API is sufficient for daily tactical use |
| EIA inventory data | EIA Open Data API | api.eia.gov/v2/ | Free | API key required (free registration). Weekly, Wed 10:30 ET |
| Rig count | Baker Hughes | rigcount.bakerhughes.com | Free | Excel download, Fridays 13:00 ET. Parse with openpyxl |
| CFTC COT data | CFTC | cftc.gov/MarketReports | Free | CSV download, Fridays 15:30 ET |
| News RSS | Reuters, OilPrice, Rigzone, OPEC | Public RSS URLs listed above | Free | feedparser ingestion |
| NLP sentiment | Hugging Face Inference API | ProsusAI/finbert | Free tier (rate limits) | Upgrade to paid for production load |
| Macro series | FRED | api.stlouisfed.org | Free | DXY, 10Y yield, ISM PMI, others |
| PMI data | Manual update | — | Free | S&P Global Caixin PMI, NBS PMI — enter monthly |
| OPEC compliance | Manual / OPEC MOMR PDF | opec.org | Free | Monthly; extract from PDF or manual input |
| Spare capacity | Manual / OPEC MOMR + IEA OMR | opec.org / iea.org | Free | Monthly update |
| China customs imports | FRED or NBS (manual) | — | Free | Monthly; approximation acceptable |
| Freight rates | Investing.com scrape | investing.com | Free (scrape) | TD3C, BDTI. Or Baltic Exchange API if licensed |

---

## IMPLEMENTATION NOTES FOR CLAUDE CODE

### On Yahoo symbol support
- WTI: `CL=F` | RBOB: `RB=F` | HO: `HO=F` | Brent: `BZ=F`
- DXY: `DX-Y.NYB` | SPX: `^GSPC` | Henry Hub: `NG=F` | 10Y: `^TNX`
- For calendar spreads M2-M4: Yahoo does not provide deferred contract data. Use CME free settlement data or approximate with Yahoo using the next contract month tickers when available.

### On EIA API
- Endpoint format: `https://api.eia.gov/v2/seriesid/{SERIES_ID}?api_key={KEY}&frequency=weekly&length=52`
- All series IDs are listed in Section 3.1 above.

### On Baker Hughes Excel
- URL: `https://rigcount.bakerhughes.com/static-files/7dcea28f-8c08-4e16-ba68-7d8299d34a73` — this changes periodically.
- Preferred approach: scrape the page for the current download link on each scheduler run.
- Parse with openpyxl. Target sheet: "US" tab. Column: "Oil" for oil-directed rigs.

### On FinBERT
```python
import requests

def score_sentiment(text: str, hf_api_key: str) -> float:
    API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"
    headers = {"Authorization": f"Bearer {hf_api_key}"}
    response = requests.post(API_URL, headers=headers, json={"inputs": text})
    data = response.json()[0]
    scores = {item['label']: item['score'] for item in data}
    return scores.get('positive', 0) - scores.get('negative', 0)
```

### On Lightweight-Charts (TradingView)
- Use for WTI intraday chart only (Tab 2, first chart).
- Install: `npm install lightweight-charts`
- Wrap in a React `useEffect` with proper cleanup to avoid memory leaks.
- Mount the chart to a `ref` div, not inline JSX.

### On CFTC data
- Download URL: `https://www.cftc.gov/dea/newcot/deahistfo.zip` (full history)
- Or current week: `https://www.cftc.gov/dea/newcot/f_disagg.txt`
- Filter for WTI (CFTC contract code: `067651`), RBOB (`111659`), HO (`022651`).

### On EMA Calculation
```typescript
// Exponential Moving Average
function calculateEMA(prices: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const ema = [prices[0]];
  for (let i = 1; i < prices.length; i++) {
    ema.push(prices[i] * k + ema[i-1] * (1 - k));
  }
  return ema;
}
```

### On Bollinger Bands
```typescript
function calculateBollingerBands(prices: number[], period: number = 20, sigma: number = 2) {
  const sma = prices.slice(-period).reduce((a, b) => a + b, 0) / period;
  const std = Math.sqrt(prices.slice(-period).reduce((a, b) => a + (b - sma) ** 2, 0) / period);
  return { upper: sma + sigma * std, middle: sma, lower: sma - sigma * std, width: 2 * sigma * std };
}
// sigma = 2 in NORMAL/ELEVATED regime, sigma = 3 in HIGH-VOL regime
```

---

## THINGS NOT TO BUILD (Cut List)

These were in v4 but are explicitly removed in v5:

| Feature Removed | Reason |
|---|---|
| Twitter/X intelligence feed | Requires $100+/mo API access. RSS + NLP covers same signal |
| Separate Correlation tab | Integrated as compact strip in Overview. Nobody lives in a correlation matrix |
| Full 5×5 Pearson matrix with time series | Replaced by 6-cell strip of tradeable pairs + rolling beta panel |
| 10-factor fair value regression | Noisy China proxy + OPEC compliance rate made model unreliable. Simplified to 3 clean factors |
| Separate Positioning tab | CFTC integrated into Inventory tab as a sizing modifier |
| EUA Carbon price | Peripheral to crude oil trading. Removed per v3.2 |
| Position history / P&L tracker | Out of scope for a market analysis dashboard |

---

## VISUAL MOCKUP — HEADER BAR

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ BULLISH  HIGH-VOL │ WTI $82.41 ▲0.4%  RBOB 249.3¢ ▲0.2%  HO 262.1¢ ▼0.1%  │               │
│  (green)  (red)   │ BRENT $83.62 (+1.21)  GO $712 ▲0.3%  DXY 104.1 ▼0.2% │ ████░░ +44   │
│                   │                                                            │               │
│ ⚑  OPEC+ compliance at 89% — IEA flags Iraq overproduction of 0.2 mbd › ›   │               │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## VISUAL MOCKUP — OVERVIEW TAB

```
[COMPOSITE SCORE GAUGE -100→+100]  [VOL REGIME — HIGH-VOL — 42% ann]  [SIZING — 3 contracts]
    EMA 40% ███░░ News 20% ██░░░        20d realized vol sparkline           Base×0.42×0.75

[WTI $82.41 ▲0.4%]  [RBOB 249.3¢ ▲0.2%]  [HO 262.1¢ ▼0.1%]  [BRENT $83.62]  [GO $712 ▲0.3%]
  CME  ABOVE20  BB:MID   CME  ABOVE20  SQUEEZE  CME  BELOW20  BB:LOW   ICE  EMA CROSS   ICE  ABOVE20
  Crack: $24.2/bbl        3:2:1: $24.2          Dist: -8% 5yr avg       +$1.21 spread    Crack: $18.1

[ALERT FEED]
09:42  ⚑ Large EIA surprise  Crude draw 4.2mb vs 1.8mb consensus  Check Cushing backwardation
09:15  ⚠ OPEC meeting T−5   Iraq compliance flagged by IEA         Review IEA MOMR

[WTI/Brent: 0.96] [WTI/RBOB: 0.91] [WTI/HO: 0.88] [Brent/GO: 0.94] [WTI/DXY: -0.71 DRIVING] [WTI/SPX: 0.31]
[RBOB β=1.12 ▲]  [HO β=0.94]  [GO β=0.97]
[DXY 104.1 DXY DRIVING] [10Y 4.31% ▲] [SPX 5,892 ▲0.3%] [HH $3.41] [PMI 51.2 EXPANDING] [Caixin 51.8]
```

---

## IMPORTANT ANALYTICAL PRINCIPLES (From the Book)

These principles should inform which signals the dashboard emphasises and how tooltips/annotations are written:

1. **Chain thinking**: Price signals emerge from bottlenecks anywhere — upstream, midstream, downstream. The dashboard covers all three layers.

2. **Spare capacity is the denominator**: Always show spare capacity alongside any geopolitical disruption estimate. A disruption without context is meaningless.

3. **Backwardation > contango for trend timing**: M1-M2 spread is a purer fundamental signal than outright price. Track it more closely than the headline.

4. **OPEC self-reporting is unreliable**: Always show IEA secondary-source figure. Never display only OPEC-reported data.

5. **Shale is the swing supply with 3–6 month lag**: Rig count changes today show up in production 3–6 months later. The dashboard shows both with the lag explicitly annotated.

6. **Seasonality is context, not trigger**: 5-year range and seasonal heatmap show where price is relative to history. They need confirmation from spread structure before trading.

7. **Capital cycle is multi-year**: FID drought in 2015–2016 → supply deficit 2021–2022. The dashboard's 52-week rig count trend and forward curve shape together tell this story.

8. **Chinese inventory is the critical unknown**: Chinese imports vs refinery runs gap = invisible demand or supply. Include in macro tab. Do not omit.

9. **Geopolitical risk premiums fade**: 50–80% of initial spike typically reverses in 30 days if supply is rerouted. Buy the spike only if disruption is genuine and spare capacity is insufficient.

10. **Stale data is worse than no data**: Every widget must show its data age. Never display stale data silently.

---

*End of Build Specification v5.0*
*For Claude Code — Docker deployment — React + TypeScript + FastAPI*
*Products covered: WTI · RBOB · ULSD/HO · Brent · Gas Oil*
