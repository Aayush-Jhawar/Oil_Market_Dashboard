---
title: Energy Dashboard
emoji: 📊
colorFrom: indigo
colorTo: blue
sdk: docker
pinned: true
---

# Energy Dashboard v5.0

**A real-time energy market analysis dashboard for crude oil traders.**

Built with React + TypeScript + FastAPI, and designed to surface live commodity signals, macro context, and trading analytics for 5 core products: WTI, Brent, RBOB, HO, and GO.

## Quick Start

### Prerequisites
- Node.js 20+ (for frontend local development)
- Python 3.11+ (for backend local development)

### Setup

1. Copy environment vars:
`ash
cp .env.example .env
`
2. Edit .env and add your API keys:
- EIA_API_KEY from https://www.eia.gov/opendata/
- HF_API_KEY from https://huggingface.co/settings/tokens (optional)


### Local development

**Backend**
`ash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate   # macOS / Linux
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m py_compile main.py hurricane.py ais.py services/sentiment_analyzer.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
`

**Frontend**
`ash
cd frontend
npm install
npm run dev
`

### Open in browser
- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API docs: http://localhost:8000/docs

## What’s New in This Version

- Live WebSocket updates for prices and signals
- Enhanced analytics endpoint: /api/signals/enhanced
- More advanced indicators: EMA20/50, ATR14, Bollinger, realized volatility
- Better trader-facing dashboard panels with market state and signal heatmap
- Consolidated analytics for oil and downstream products

## Dashboard Tabs

### Overview
- Composite score and regime view
- Live volatility regime
- Suggested position sizing
- 5-product live price snapshot
- Market state summary with contango/backwardation and inventory change
- Enhanced signal panel for trend, ATR, Bollinger, and breakout status

### Prices & Spreads
- Live price bar and line charts
- Candlestick views for WTI, Brent, RBOB, HO
- Crack spread panels for refining margin signals

### Inventory & Supply
- Weekly EIA inventory and supply series
- Baker Hughes rig count
- Macro supply/demand context with EIA surprises

### Seasonality
- Forward curve and calendar spread structure
- Seasonal heatmap and demand cycle context

### News & Macro
- Top NLP-ranked news headlines
- Sentiment trend analytics
- Core macro indicators including DXY, 10Y yield, PMI

## API Endpoints

### Prices
- GET /api/prices/all
- GET /api/prices/{symbol}
- GET /api/prices/{symbol}/historical?period=1mo

### Signals
- GET /api/signals/composite
- GET /api/signals/enhanced

### Analytics
- GET /api/spreads/crack
- GET /api/spreads/calendar

### Data Sources
- GET /api/eia/weekly
- GET /api/rigs/latest
- GET /api/cftc/latest
- GET /api/news/bulletin
- GET /api/news/sentiment/trend
- GET /api/macro/all

### Live Updates
- ws://localhost:8000/ws/prices
- ws://localhost:8000/ws/signals

## Project Structure

`
Dashboard_v2/
├── backend/
│   ├── main.py
│   ├── signal_calc.py
│   ├── database.py
│   ├── models.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── services/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   ├── tabs/
│   │   ├── store/
│   │   └── types/
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── Energy_Dashboard_BuildSpec_v5.md
`

## Technical Summary

- React + Zustand + Vite frontend
- FastAPI backend with price fetchers and analytics services
- Live WebSocket channels for price and signal broadcasting
- Enhanced signals with EMA, ATR, Bollinger, and breakout labels
- EIA, CFTC, rig count, macro, and news data integrated into the dashboard

## Troubleshooting

- If npm is missing, install Node.js 20+ from https://nodejs.org
- If fastapi is missing, install backend requirements in the Python venv with `python -m pip install -r backend/requirements.txt`
- If frontend cannot connect, ensure `VITE_API_BASE=http://localhost:8000` in `frontend/.env`
- If prices fail, verify network connectivity and that the backend can reach Yahoo Finance's chart API endpoints
- If the backend returns empty quote data or 429/Too Many Requests, the local environment may be hitting Yahoo Finance rate limits; retry after a short wait or test from a different network

## License

Built per specification v5.0 for trader/analyst use.

---