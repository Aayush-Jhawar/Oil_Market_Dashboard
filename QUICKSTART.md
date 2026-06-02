# QUICK START GUIDE

## 30-Second Setup

1. **Get API Keys** (free)
   - EIA: https://www.eia.gov/opendata/ → register, copy API key
   - Hugging Face: https://huggingface.co/settings/tokens → create token

2. **Configure Environment**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and paste your keys.

3. **Local (no Docker) quick start** — recommended for development
   - Use Python 3.11 or 3.12 (the project is tested on 3.11)
   - Install backend deps:
   ```bash
   cd backend
   python -m pip install -r requirements.txt
   ```
   - Start backend (run from repo root):
   ```bash
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
   ```
   - Start frontend (in a separate terminal):
   ```bash
   cd frontend
   npm install
   npm run dev -- --host 127.0.0.1 --port 5173
   ```

4. **Access Dashboard**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## What You Get

| Tab | What It Shows |
|---|---|
| **Overview** | Composite signal, vol regime, position sizing, 5-product snapshot, alerts |
| **Prices & Spreads** | Live charts, crack spreads, fair value estimates |
| **Inventory & Supply** | EIA data, rig count, spare capacity, freight rates |
| **Seasonality** | Forward curve, calendar spreads, 5-year ranges |
| **News & Macro** | NLP news feed, geopolitical heatmap, macro indicators |

## Header Bar at a Glance

```
[BULLISH] [HIGH-VOL] | WTI $82.41 ▲0.4% | RBOB 249.3¢ ▲0.2% | ... | ████░░ +42
```

- **BULLISH/BEARISH** pill: Composite signal direction
- **HIGH-VOL** pill: Volatility regime (LOW/ELEVATED/HIGH-VOL)
- **Price pills**: All 5 products + DXY, updates every 30s
- **Score bar**: −100 to +100 visual indicator

## Settings (Click ⚙️)

- **Base Contract Size**: Used in position sizing (default 10)
- **BULL/BEAR Threshold**: When to trigger regime (default ±30)
- **API Keys**: Store your EIA and HF keys securely

## Key Signals

| Signal | What It Means |
|---|---|
| **BULLISH** (composite > +30) | Net long bias across 5 factors |
| **BEARISH** (composite < −30) | Net short bias |
| **HIGH-VOL** regime | Apply ×0.75 position sizing |
| **Backwardation** (M1 > M2) | Physical tightness, upside risk |
| **Large EIA Draw** | Bullish inventory surprise |

## Data Refresh Cadences

| Data | Updates Every |
|---|---|
| Prices | 30 seconds |
| Signals | 5 minutes |
| News | 60 seconds |
| EIA/Rigs/CFTC | Wednesday/Friday (manual) |

## Troubleshooting

### Backend won't start?
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
```

### Frontend can't reach backend?
```bash
curl http://localhost:8000/health
# Should return: {"status": "ok", ...}
```

### No price data?
- Check backend price fetcher connectivity to Yahoo Finance chart API; verify your network can reach `query1.finance.yahoo.com`.
- Check EIA key is valid (test in API docs at /docs)

## File Structure at a Glance

```
├── frontend/src/
│   ├── tabs/              ← 5 main dashboard screens
│   ├── components/        ← Header, Cards, Settings
│   ├── store/             ← Global data store
│   └── types/             ← TypeScript interfaces
│
├── backend/
│   ├── main.py            ← All API routes
│   ├── signal_calc.py     ← Composite score engine
│   └── services/          ← Data fetchers
```

## What's Pre-Built

✅ All 5 tabs with live data binding  
✅ Composite signal calculation engine  
✅ EIA API integration (all 10 series)  
✅ News feed with FinBERT sentiment  
✅ Crack spread calculations  
✅ Correlation & beta matrix  
✅ Settings persistence  
✅ Stale data detection  

## What Needs Charts

These are placeholder components ready for chart libraries:
- Recharts for RBOB/HO/Brent/GO price charts
- lightweight-charts for WTI intraday tick data
- Crack spread and seasonality heatmaps

## Common Questions

**Q: Can I use real market data instead of Yahoo Finance API?**  
A: Yes! Replace `PriceFetcher` in `backend/services/price_fetcher.py` with broker WebSocket integration (Interactive Brokers, Alpaca, etc.)

**Q: Where do I add my own alerts?**  
A: Edit `OverviewTab.tsx` → Alert Feed section. Wire to composite signals in `main.py`.

**Q: How do I customize the color scheme?**  
A: Edit CSS variables in `frontend/src/index.css` and Tailwind config in `tailwind.config.ts`.

**Q: Can I deploy to production?**  
A: Yes! Use TimescaleDB instead of SQLite, enable Nginx reverse proxy, and configure SSL certificates.

---

**Ready to trade? Start the backend and frontend locally and open http://localhost:3000**
