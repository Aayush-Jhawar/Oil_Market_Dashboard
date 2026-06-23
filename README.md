---
title: Oil Market Dashboard
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

<div align="center">

# 🛢️ Oil Market Dashboard

**A professional-grade, real-time energy trading analytics platform**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://reactjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![License](https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge)](LICENSE)

*Live prices · Crack spreads · Forward curves · Backtesting · Paper trading · EIA fundamentals*

</div>

---

## 📸 Overview

The Oil Market Dashboard is a trader-facing analytics console that surfaces **live commodity prices, spread analytics, macro context, and quantitative signals** for energy market participants. It covers 5 core products — WTI, Brent, RBOB, Heating Oil, and Gasoil — across multiple analytical dimensions.

```
Live WebSocket prices ─► Signal Engine ─► React Dashboard
         │                                       │
High-Frequency DB                      7 Interactive Tabs
         │                                       │
  Parquet Datasets                   Forward Curve · Spreads
         │                              EIA Anchors · News
    Yahoo Finance                    Backtest · Paper Trading
    EIA OpenData                        Portfolio Analytics
    CFTC Positioning
```

---

## ✨ Features

| Module | Description |
|--------|-------------|
| 📊 **Live Prices** | Real-time WebSocket prices for WTI, Brent, RBOB, HO, GO, DXY, SPX, VIX |
| 📈 **Crack Spreads** | Live 3-2-1, 5-3-2, Gasoil crack, and FRAC spread calculations |
| 🌊 **Forward Curve** | Full M1–M12 curve structure with backwardation/contango regime detection |
| 📰 **News & Sentiment** | NLP-ranked energy headlines with sentiment trend analytics |
| 🏛️ **EIA Fundamentals** | Weekly crude stocks, Cushing hub, refinery utilization vs. 5-year anchors |
| 📉 **Backtesting** | Strategy backtesting engine with multi-factor signal evaluation |
| 💼 **Paper Trading** | Simulated live paper trading with PnL tracking |
| 🔮 **Signal Engine** | Composite signals: EMA, ATR, Bollinger Bands, realized volatility, regime |
| 🌍 **Macro Context** | DXY, 10Y yield, VIX, gold, CFTC positioning, Baker Hughes rig count |

---

## 🏗️ Architecture

```
Oil_Market_Dashboard/
│
├── backend/                        # FastAPI backend
│   ├── main.py                     # API routes & WebSocket server
│   ├── signal_calc.py              # Technical signal calculations
│   ├── ws_snapshot.py              # WebSocket snapshot broadcaster
│   ├── database.py / models.py     # SQLAlchemy + SQLite persistence
│   ├── paper.py                    # Paper trading engine
│   │
│   ├── services/
│   │   ├── price_fetcher.py        # Live price feed (Yahoo Finance)
│   │   ├── spread_analyzer.py      # Crack spread & fly calculations
│   │   ├── forward_curve.py        # M1-M12 curve construction
│   │   ├── eia_fetcher.py          # EIA OpenData weekly series
│   │   ├── macro_fetcher.py        # Macro data (CFTC, rigs, DXY)
│   │   ├── news_fetcher.py         # RSS news ingestion + NLP
│   │   ├── data_loader.py          # Parquet → SQLite pipeline
│   │   ├── dataset_engine.py       # High-frequency data engine
│   │   ├── curve_analytics.py      # Curve shape & regime analytics
│   │   ├── multi_factor_engine.py  # Factor-based signal combination
│   │   └── backtest/               # Backtest engine & metrics
│   │
│   ├── scripts/                    # Data ingestion scripts
│   └── worker/                     # Background task workers
│
├── frontend/                       # React + Vite frontend
│   └── src/
│       ├── App.tsx                 # Root app + data fetching
│       ├── components/             # Shared UI components
│       ├── tabs/                   # 7 dashboard tabs
│       ├── store/                  # Zustand state management
│       └── types/                  # TypeScript type definitions
│
├── Data/                           # High-frequency Parquet datasets (Git LFS)
│   ├── CL_data.parquet             # WTI 1-min contract data (126MB)
│   ├── LCO_data.parquet            # Brent 1-min contract data (138MB)
│   ├── HO_data.parquet             # Heating Oil 1-min data (101MB)
│   ├── LGO_data.parquet            # Gasoil 1-min data (104MB)
│   └── wtcl_lco_outrights_1min.parquet  # WTI-Brent spread (63MB)
│
└── DB/                             # Pre-populated SQLite snapshots
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- **Node.js 20+**
- **Git LFS** (for downloading Parquet datasets)

### 1. Clone with LFS data
```bash
git lfs install
git clone https://github.com/Aayush-Jhawar/Oil_Market_Dashboard.git
cd Oil_Market_Dashboard
```

### 2. Backend setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

Create a `.env` file in the project root:
```env
EIA_API_KEY=your_key_here        # https://www.eia.gov/opendata/
```

Start the backend:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> [!NOTE]
> **First run only:** On first startup, the backend will automatically build `energy.db` from the Parquet datasets. This takes **5–10 minutes** and only happens once. Every subsequent start is instant.

### 3. Frontend setup
```bash
cd frontend
npm install
npm run dev
```

### 4. Open the dashboard
| Service | URL |
|---------|-----|
| 🖥️ Dashboard | http://localhost:5173 |
| ⚙️ API Server | http://localhost:8000 |
| 📚 API Docs | http://localhost:8000/docs |

---

## 📡 API Reference

<details>
<summary><strong>Price Endpoints</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/prices/all` | All live commodity prices |
| `GET` | `/api/prices/{symbol}` | Single symbol price |
| `GET` | `/api/prices/{symbol}/historical?period=1mo` | Historical OHLCV data |
| `GET` | `/api/prices/instruments` | List of supported symbols |

</details>

<details>
<summary><strong>Signal & Analytics Endpoints</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/signals/composite` | Composite regime and score |
| `GET` | `/api/signals/enhanced` | EMA, ATR, Bollinger, breakout signals |
| `GET` | `/api/spreads/all` | All crack spreads and flies |
| `GET` | `/api/analytics/forward-curve` | Full M1–M12 forward curve |
| `GET` | `/api/analytics/correlations` | Cross-product correlation matrix |

</details>

<details>
<summary><strong>Fundamentals & Data Endpoints</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/eia/weekly` | EIA weekly inventory report |
| `GET` | `/api/eia/weekly-anchor` | EIA vs. 5-year seasonal anchor |
| `GET` | `/api/rigs/latest` | Baker Hughes rig count |
| `GET` | `/api/cftc/latest` | CFTC managed-money positioning |
| `GET` | `/api/macro/all` | DXY, yields, VIX, gold, SPX |
| `GET` | `/api/news/enhanced` | NLP-ranked news with sentiment |

</details>

<details>
<summary><strong>WebSocket Feeds</strong></summary>

| Protocol | Endpoint | Description |
|----------|----------|-------------|
| `WS` | `ws://localhost:8000/ws/snapshot` | Full live dashboard snapshot |

</details>

---

## 📊 Dashboard Tabs

| Tab | What it shows |
|-----|---------------|
| **Overview** | Regime, signals, composite score, 5-product snapshot cards, volatility |
| **Prices** | Live candlesticks, price movers, crack spread cards, OHLCV charts |
| **Market Structure** | Forward curve, calendar spreads, CFTC positioning, spread health |
| **News & Macro** | NLP news feed, geopolitical heatmap, DXY/yield/VIX/PMI |
| **EIA Anchors** | Weekly EIA vs. 5-year anchors, crude stocks, SPR, refinery utilization |
| **Backtest** | Multi-factor strategy backtest with PnL charts and performance metrics |
| **Portfolio** | Paper trading journal, open positions, PnL attribution |

---

## 🔧 Technology Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) — async API framework
- [SQLAlchemy](https://sqlalchemy.org/) + SQLite — persistence layer
- [Pandas](https://pandas.pydata.org/) + [PyArrow](https://arrow.apache.org/docs/python/) — high-frequency data processing
- [Polars](https://pola.rs/) — blazing-fast dataset queries
- [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/) — background task queue

**Frontend**
- [React 18](https://reactjs.org/) + [TypeScript](https://typescriptlang.org/) — UI framework
- [Vite](https://vitejs.dev/) — build tooling
- [Zustand](https://zustand-demo.pmnd.rs/) — lightweight state management
- [Recharts](https://recharts.org/) — charting library
- [TailwindCSS](https://tailwindcss.com/) — utility-first styling

**Data**
- Yahoo Finance chart API — live price feed
- EIA OpenData API — U.S. energy fundamentals
- CFTC public data — commitment of traders positioning
- Baker Hughes — weekly rig count
- RSS feeds — energy news ingestion

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Parquet files missing after clone | Run `git lfs pull` to download datasets |
| Backend can't start | Run `pip install -r backend/requirements.txt` in your virtual environment |
| Prices show `—` | Yahoo Finance may be rate-limiting; wait 60s and refresh |
| Frontend shows blank | Ensure `VITE_API_BASE=http://localhost:8000` is set in `frontend/.env` |
| `uvicorn` not found | Activate the virtual environment first: `.venv\Scripts\activate` |

---

<div align="center">

**Built for energy market traders and analysts.**

</div>
