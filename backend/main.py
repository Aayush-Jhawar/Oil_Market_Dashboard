from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import asyncio
import json
import statistics
from typing import List, Set
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import PriceData, InventoryData, NewsItem, Alert, SpreadAnalysis
from services.price_fetcher import PriceFetcher
from services.news_fetcher import NewsFetcher
from services.eia_fetcher import EIAFetcher
from services.macro_fetcher import MacroFetcher, RigCountFetcher, CFTCFetcher
from services.sentiment_analyzer import SentimentAnalyzer
from services.spread_analyzer import SpreadCalculator, AnomalyDetector
from signal_calc import SignalCalculator
from ws_snapshot import register_router as register_ws_snapshot
from hurricane import fetch_active_storms
from ais import fetch_tanker_positions
from datetime import datetime, timedelta
import logging
import os
from cot import fetch_cot_history
from steo import fetch_steo_balance
from seasonality import fetch_seasonality
from sentiment import analyze_news_items

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Energy Dashboard API",
    description="Real-time energy market dashboard API",
    version="6.0",
)

# register the simulated snapshot router if present
try:
    register_ws_snapshot(app)
except Exception:
    pass

# Initialize global spread calculator
spread_calculator = SpreadCalculator(history_length=252)


# Simple WebSocket manager to broadcast price and signal updates
class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except KeyError:
            pass

    async def broadcast(self, message: dict):
        text = json.dumps(message, default=str)
        to_remove = []
        for ws in list(self.active_connections):
            try:
                await ws.send_text(text)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(ws)


# module-level manager and background task handles
ws_manager = WebSocketManager()
_background_tasks = []


async def _price_publisher():
    loop = asyncio.get_event_loop()
    while True:
        try:
            prices = await loop.run_in_executor(None, PriceFetcher.fetch_all_prices)
            message = {"type": "prices", "data": prices, "timestamp": datetime.now().isoformat()}
            await ws_manager.broadcast(message)
        except Exception as e:
            logger.warning(f"Price publisher error: {e}")
        await asyncio.sleep(5)


async def _signals_publisher():
    loop = asyncio.get_event_loop()
    while True:
        try:
            # reuse logic from /api/signals/composite
            prices = await loop.run_in_executor(None, PriceFetcher.fetch_all_prices)
            news = await loop.run_in_executor(None, NewsFetcher.fetch_all_news)

            wti_hist = await loop.run_in_executor(None, PriceFetcher.fetch_historical, "WTI", "3mo")
            wti_prices = [float(h["close"]) for h in (wti_hist or [])]

            ema20 = SignalCalculator.calculate_ema(wti_prices, 20) if wti_prices else 0
            ema50 = SignalCalculator.calculate_ema(wti_prices, 50) if wti_prices else 0
            ema_trend = SignalCalculator.calculate_ema_trend(ema20, ema50)

            news_sentiment = NewsFetcher.calculate_sentiment_trend(news)

            cftc_z_score = 0.5
            eia_surprise = 0.2
            seasonality = 0.1

            composite = SignalCalculator.calculate_composite_score(
                ema_trend, news_sentiment, cftc_z_score, eia_surprise, seasonality
            )

            vol = SignalCalculator.calculate_realized_volatility(wti_prices)
            vol_regime = SignalCalculator.get_vol_regime(vol)

            payload = {
                "type": "signals",
                "data": {**composite, "volatility_pct": round(vol, 1), "vol_regime": vol_regime},
                "timestamp": datetime.now().isoformat(),
            }
            await ws_manager.broadcast(payload)
        except Exception as e:
            logger.warning(f"Signals publisher error: {e}")
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start_background_publishers():
    # start background publishers
    _background_tasks.append(asyncio.create_task(_price_publisher()))
    _background_tasks.append(asyncio.create_task(_signals_publisher()))


@app.on_event("shutdown")
async def _stop_background_publishers():
    for t in _background_tasks:
        t.cancel()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static frontend files if available
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")


# ==================== PRICE ENDPOINTS ====================
@app.get("/api/prices/all")
async def get_all_prices():
    """Get latest prices for all products"""
    try:
        prices = PriceFetcher.fetch_all_prices()
        return {"status": "success", "data": prices, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching prices: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/cot/history')
async def get_cot_history():
    try:
        data = fetch_cot_history()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching COT history: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/steo/balance')
async def get_steo_balance():
    try:
        data = fetch_steo_balance()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching STEO balance: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/seasonality')
async def get_seasonality():
    try:
        data = fetch_seasonality()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching seasonality: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post('/api/news/analyze')
async def post_analyze_news(payload: dict):
    try:
        items = payload.get('items', [])
        res = analyze_news_items(items)
        return {"status": "success", "data": res, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error analyzing news: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/prices/instruments')
async def get_price_instruments():
    """Get supported price symbols and instrument mappings"""
    try:
        instruments = [
            {"symbol": symbol, "ticker": PriceFetcher.SYMBOLS.get(symbol)}
            for symbol in PriceFetcher.SYMBOLS
        ]
        return {
            "status": "success",
            "data": instruments,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching instrument list: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.websocket('/ws/prices')
async def websocket_prices_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # wait for client pings/messages to detect disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket('/ws/signals')
async def websocket_signals_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/api/prices/{symbol}")
async def get_price(symbol: str):
    """Get price for a specific symbol"""
    try:
        price_data = PriceFetcher.fetch_symbol(symbol)
        if not price_data:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        return {"status": "success", "data": price_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get("/api/prices/{symbol}/historical")
async def get_historical_prices(symbol: str, period: str = "1mo"):
    """Get historical prices for a symbol"""
    try:
        data = PriceFetcher.fetch_historical(symbol, period)
        if not data:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching historical prices: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== EIA ENDPOINTS ====================
@app.get("/api/eia/weekly")
async def get_eia_data():
    """Get latest EIA weekly data"""
    try:
        if not os.getenv("EIA_API_KEY"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "EIA_API_KEY not configured"})

        eia_data = EIAFetcher.fetch_all_eia_data()
        return {"status": "success", "data": eia_data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching EIA data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/eia/weekly-history')
async def get_eia_weekly_history():
    """Get the latest 52 weeks of EIA series data."""
    try:

        if not os.getenv("EIA_API_KEY"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "EIA_API_KEY not configured"})

        history = {}
        for name, series_id in EIAFetcher.SERIES.items():
            values = EIAFetcher.fetch_series_history(series_id, length=52)
            history[name] = values or []

        return {
            "status": "success",
            "data": history,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching EIA weekly history: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/eia/weekly-anchor')
async def get_eia_weekly_anchor():
    """Get weekly EIA anchor data relative to 5-year averages."""
    try:
        if not os.getenv("EIA_API_KEY"):
            return JSONResponse(status_code=400, content={"status": "error", "message": "EIA_API_KEY not configured"})

        current_data = EIAFetcher.fetch_all_eia_data()
        anchor_data = {}

        for name, series_id in EIAFetcher.SERIES.items():
            current = current_data.get(name, {})
            avg_5yr = EIAFetcher.calculate_5yr_avg(series_id)
            anchor_data[name] = {
                "current_value": current.get("current_value"),
                "current_date": current.get("current_date"),
                "five_year_avg": avg_5yr,
                "delta_vs_5yr": None if avg_5yr is None or current.get("current_value") is None else current["current_value"] - avg_5yr,
                "timestamp": datetime.now().isoformat(),
            }

        return {
            "status": "success",
            "data": anchor_data,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching EIA weekly anchor data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== RIG COUNT ENDPOINTS ====================
@app.get("/api/rigs/latest")
async def get_latest_rig_count():
    """Get latest Baker Hughes rig count"""
    try:
        rig_data = RigCountFetcher.fetch_latest()
        return {"status": "success", "data": rig_data}
    except Exception as e:
        logger.error(f"Error fetching rig count: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== CFTC ENDPOINTS ====================
@app.get("/api/cftc/latest")
async def get_latest_cftc():
    """Get latest CFTC positioning data"""
    try:
        cftc_data = CFTCFetcher.fetch_latest()
        return {"status": "success", "data": cftc_data}
    except Exception as e:
        logger.error(f"Error fetching CFTC data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== NEWS ENDPOINTS ====================
@app.get("/api/news/bulletin")
async def get_news_bulletin():
    """Get top 10 NLP-scored news items"""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(NewsFetcher.fetch_all_news)
            try:
                news = future.result(timeout=10)
            except FuturesTimeoutError:
                logger.error("News fetch timeout")
                return JSONResponse(status_code=503, content={"status": "error", "message": "News fetch timeout"})
        
        return {"status": "success", "data": news, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get("/api/news/sentiment/trend")
async def get_sentiment_trend():
    """Get sentiment trend (5-day exponentially-decayed average)"""
    try:
        news = NewsFetcher.fetch_all_news()
        trend = NewsFetcher.calculate_sentiment_trend(news)
        return {
            "status": "success",
            "data": {
                "sentiment_trend": round(trend, 3),
                "news_count": len(news),
                "timestamp": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error calculating sentiment trend: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== MACRO ENDPOINTS ====================
@app.get("/api/macro/all")
async def get_all_macro():
    """Get all macro indicators"""
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(MacroFetcher.fetch_all_macro)
            try:
                macro_data = future.result(timeout=5)
            except FuturesTimeoutError:
                logger.error("Macro fetch timeout")
                return JSONResponse(status_code=503, content={"status": "error", "message": "Macro fetch timeout"})
        
        return {"status": "success", "data": macro_data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching macro data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== SIGNALS ENDPOINTS ====================
@app.get("/api/signals/composite")
async def get_composite_signal():
    """Get composite trading signal"""
    try:
        # Fetch required data concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_prices = executor.submit(PriceFetcher.fetch_all_prices)
            future_news = executor.submit(NewsFetcher.fetch_all_news)
            prices = future_prices.result()
            news = future_news.result()

        # Get historical prices for WTI to calculate EMA
        wti_hist = PriceFetcher.fetch_historical("WTI", "3mo")
        if not wti_hist:
            logger.error("WTI historical data not available (no fallback).")
            return JSONResponse(status_code=503, content={"status": "error", "message": "WTI historical data not available"})

        wti_prices = [float(h["close"]) for h in wti_hist]

        # Calculate sub-scores
        ema20 = SignalCalculator.calculate_ema(wti_prices, 20)
        ema50 = SignalCalculator.calculate_ema(wti_prices, 50)
        ema_trend = SignalCalculator.calculate_ema_trend(ema20, ema50)

        # News sentiment
        news_sentiment = NewsFetcher.calculate_sentiment_trend(news)

        # Placeholder CFTC Z-score (in production, calculated from actual CFTC data)
        cftc_z_score = 0.5

        # Placeholder EIA surprise
        eia_surprise = 0.2

        # Placeholder seasonality
        seasonality = 0.1

        # Calculate composite score
        composite = SignalCalculator.calculate_composite_score(
            ema_trend, news_sentiment, cftc_z_score, eia_surprise, seasonality
        )

        # Volatility regime
        vol = SignalCalculator.calculate_realized_volatility(wti_prices)
        vol_regime = SignalCalculator.get_vol_regime(vol)

        return {
                "status": "success",
                "data": {
                    **composite,
                    "volatility_pct": round(vol, 1),
                    "vol_regime": vol_regime,
                    "ema_20": round(ema20, 4) if ema20 is not None else None,
                    "ema_50": round(ema50, 4) if ema50 is not None else None,
                    "ema_trend": "BULLISH" if ema20 is not None and ema50 is not None and ema20 > ema50 else "BEARISH" if ema20 is not None and ema50 is not None and ema20 < ema50 else "NEUTRAL",
                    "bollinger_position": SignalCalculator.calculate_bollinger_bands(wti_prices, period=20, sigma=2.0).get("position") if len(wti_prices) >= 20 else None,
                    "bollinger_width": SignalCalculator.calculate_bollinger_bands(wti_prices, period=20, sigma=2.0).get("width") if len(wti_prices) >= 20 else None,
                    "atr_14": SignalCalculator.calculate_atr(wti_hist, 14)[-1] if wti_hist else None,
                    "timestamp": datetime.now().isoformat(),
                },
            }
    except Exception as e:
        logger.error(f"Error calculating composite signal: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/signals/enhanced')
async def get_enhanced_signals():
    """Get enhanced signal analytics for core energy products"""
    try:
        prices = PriceFetcher.fetch_all_prices()
        eia_data = EIAFetcher.fetch_all_eia_data()

        symbols = ["WTI", "Brent", "RBOB", "HO"]
        enhanced_list = []

        for symbol in symbols:
            hist = PriceFetcher.fetch_historical(symbol, "3mo") or []
            closes = [float(item["close"]) for item in hist]
            ema20 = SignalCalculator.calculate_ema(closes, 20)
            ema50 = SignalCalculator.calculate_ema(closes, 50)
            ema_trend = "NEUTRAL"
            if ema20 is not None and ema50 is not None:
                ema_trend = "BULLISH" if ema20 > ema50 else "BEARISH" if ema20 < ema50 else "NEUTRAL"
            ema_diff_pct = round(((ema20 - ema50) / ema50 * 100), 2) if ema20 is not None and ema50 not in (None, 0) else None
            atr_series = SignalCalculator.calculate_atr(hist, 14)
            atr14 = atr_series[-1] if atr_series else None
            boll = SignalCalculator.calculate_bollinger_bands(closes, period=20, sigma=2.0) if closes else {
                "upper": 0.0,
                "middle": 0.0,
                "lower": 0.0,
                "width": 0.0,
                "position": "middle",
            }
            current = prices.get(symbol)
            prev_close = closes[-2] if len(closes) > 1 else None
            breakout = False
            if current and boll:
                last = float(current.get("close", 0))
                upper = boll.get("upper")
                lower = boll.get("lower")
                if upper is not None and lower is not None:
                    breakout = last > upper or last < lower
            signal_label = "Neutral"
            if ema_trend == "BULLISH" and breakout and boll.get("position") == "upper":
                signal_label = "Bullish breakout"
            elif ema_trend == "BEARISH" and breakout and boll.get("position") == "lower":
                signal_label = "Bearish breakdown"
            elif ema_trend == "BULLISH":
                signal_label = "Trend bullish"
            elif ema_trend == "BEARISH":
                signal_label = "Trend bearish"
            elif breakout:
                signal_label = "Volatility breakout"

            enhanced_list.append({
                "symbol": symbol,
                "close": current.get("close") if current else None,
                "change_pct": current.get("change_pct") if current else None,
                "ema20": round(ema20, 4) if ema20 is not None else None,
                "ema50": round(ema50, 4) if ema50 is not None else None,
                "ema_trend": ema_trend,
                "ema_diff_pct": ema_diff_pct,
                "atr14": round(atr14, 4) if atr14 is not None else None,
                "bollinger": boll,
                "breakout": breakout,
                "signal_label": signal_label,
                "volatility_pct": SignalCalculator.calculate_realized_volatility(closes) if closes else 0.0,
            })

        curve_label = "UNKNOWN"
        wti_price = prices.get("WTI", {}).get("close")
        brent_price = prices.get("Brent", {}).get("close")
        if wti_price is not None and brent_price is not None:
            curve_label = "BACKWARDATION" if wti_price > brent_price else "CONTANGO"

        cracks = SignalCalculator.calculate_crack_spreads(
            rbob=float(prices.get("RBOB", {}).get("close", 0)),
            ulsd=float(prices.get("HO", {}).get("close", 0)),
            wti=float(prices.get("WTI", {}).get("close", 0)),
            brent=float(prices.get("Brent", {}).get("close", 0)),
            go_per_mt=float(prices.get("GO", {}).get("close", 0)) if prices.get("GO") else None,
        )

        market_state = {
            "curve": curve_label,
            "m1_m12_spread": round((brent_price - wti_price), 2) if wti_price is not None and brent_price is not None else None,
            "inventory_wow": eia_data.get("crude_level", {}).get("wow_change"),
            "cl_brent_spread": round((wti_price - brent_price), 2) if wti_price is not None and brent_price is not None else None,
            "crack_321": cracks.get("crack_321"),
            "crack_532": cracks.get("crack_532"),
            "vol_regime": SignalCalculator.get_vol_regime(SignalCalculator.calculate_realized_volatility([float(item["close"]) for item in PriceFetcher.fetch_historical("WTI", "3mo") or []])),
        }

        return {
            "status": "success",
            "data": {
                "symbols": enhanced_list,
                "market_state": market_state,
                "timestamp": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error calculating enhanced signals: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== ANALYTICS ENDPOINTS ====================
@app.get("/api/analytics/forward-curve")
async def get_forward_curve():
    """Get synthetic forward curve and M1-M12 spreads"""
    try:
        prices = PriceFetcher.fetch_all_prices()
        wti = prices.get("WTI", {}).get("close", 82.0)
        base = float(wti)
        curve = []
        for i in range(1, 13):
            drift = (i - 1) * 0.4
            season = ((i - 1) % 6) * 0.15
            price = round(base + drift + season - 0.2 * i, 2)
            spread = round(price - base, 2)
            curve.append({"month": f"M{i}", "price": price, "spread": spread})

        return {
            "status": "success",
            "data": {
                "forward_curve": curve,
                "m1_m12_spread": round(curve[-1]["price"] - curve[0]["price"], 2),
                "timestamp": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error generating forward curve: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/analytics/indicators')
async def get_indicators(symbol: str = 'WTI', period: str = '3mo', ema_periods: str = '20,50', atr_period: int = 14):
    """Return per-symbol indicators: EMA series, ATR series, Bollinger bands, realized vol"""
    try:
        hist = PriceFetcher.fetch_historical(symbol, period)
        if not hist:
            raise HTTPException(status_code=404, detail=f'No historical data for {symbol}')

        closes = [float(h['close']) for h in hist]
        highs = [float(h['high']) for h in hist]
        lows = [float(h['low']) for h in hist]

        ema_list = {}
        for p in [int(x) for x in ema_periods.split(',') if x.strip().isdigit()]:
            series = SignalCalculator.ema_series(closes, p)
            # align timestamps
            ema_list[f'ema_{p}'] = [round(x, 4) for x in series]

        atr_series = SignalCalculator.calculate_atr(hist, atr_period)

        boll = SignalCalculator.calculate_bollinger_bands(closes, period=20, sigma=2.0) if closes else {
            "upper": 0.0,
            "middle": 0.0,
            "lower": 0.0,
            "width": 0.0,
            "position": "middle",
        }
        vol = SignalCalculator.calculate_realized_volatility(closes)

        return {
            'status': 'success',
            'data': {
                'symbol': symbol,
                'historical': hist,
                'ema_series': ema_list,
                'atr_series': atr_series,
                'bollinger': boll,
                'realized_vol_pct': vol,
                'timestamp': datetime.now().isoformat(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error generating indicators for {symbol}: {e}')
        return JSONResponse(status_code=500, content={'status': 'error', 'message': str(e)})


@app.get("/api/analytics/correlations")
async def get_correlation_matrix():
    """Get correlation matrix and rolling beta analytics"""
    try:
        symbols = ["WTI", "Brent", "RBOB", "HO"]
        histories = {}
        monthly_returns = {}

        def calculate_beta(x: List[float], y: List[float]) -> float:
            if not x or not y:
                return 0.0
            length = min(len(x), len(y))
            x = x[-length:]
            y = y[-length:]
            mean_x = statistics.mean(x)
            mean_y = statistics.mean(y)
            cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / length
            var_x = sum((xi - mean_x) ** 2 for xi in x) / length
            return float(cov / var_x) if var_x else 0.0

        with ThreadPoolExecutor(max_workers=min(4, len(symbols))) as executor:
            future_to_symbol = {
                executor.submit(PriceFetcher.fetch_historical, symbol, "6mo"): symbol
                for symbol in symbols
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                hist = future.result() or []
                histories[symbol] = [float(item["close"]) for item in hist] if hist else []

                month_values = {}
                for item in hist:
                    month = item["timestamp"][:7]
                    month_values[month] = float(item["close"])

                sorted_months = sorted(month_values.keys())
                if len(sorted_months) > 1:
                    returns = []
                    for i in range(1, len(sorted_months)):
                        prev = month_values[sorted_months[i - 1]]
                        curr = month_values[sorted_months[i]]
                        if prev:
                            returns.append((curr - prev) / prev)
                    monthly_returns[symbol] = returns
                else:
                    monthly_returns[symbol] = []

        matrix = {}
        monthly_matrix = {}
        for symbol_a in symbols:
            matrix[symbol_a] = {}
            monthly_matrix[symbol_a] = {}
            for symbol_b in symbols:
                if symbol_a == symbol_b:
                    matrix[symbol_a][symbol_b] = 1.0
                    monthly_matrix[symbol_a][symbol_b] = 1.0
                    continue
                correlation = SignalCalculator.calculate_correlation(
                    histories[symbol_a], histories[symbol_b]
                )
                matrix[symbol_a][symbol_b] = correlation

                monthly_corr = SignalCalculator.calculate_correlation(
                    monthly_returns.get(symbol_a, []),
                    monthly_returns.get(symbol_b, [])
                )
                monthly_matrix[symbol_a][symbol_b] = monthly_corr

        rolling_beta = {
            "RBOB/WTI": calculate_beta(monthly_returns.get("WTI", []), monthly_returns.get("RBOB", [])),
            "HO/WTI": calculate_beta(monthly_returns.get("WTI", []), monthly_returns.get("HO", [])),
        }

        return {
            "status": "success",
            "data": {
                "symbols": symbols,
                "correlation_matrix": matrix,
                "monthly_correlation_matrix": monthly_matrix,
                "rolling_beta": rolling_beta,
                "timestamp": datetime.now().isoformat(),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating correlations: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== SPREAD ANALYSIS ENDPOINTS ====================
@app.get("/api/spreads/all")
async def get_all_spreads():
    """Get all calculated spreads with historical statistics"""
    try:
        prices = PriceFetcher.fetch_all_prices()
        spreads = spread_calculator.calculate_all_spreads(prices)
        return {
            "status": "success",
            "data": spreads,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error calculating spreads: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/spreads/{spread_name}")
async def get_spread(spread_name: str):
    """Get specific spread with statistics and color coding"""
    try:
        prices = PriceFetcher.fetch_all_prices()
        spread_value = spread_calculator.calculate_spread(spread_name, prices)
        
        if spread_value is None:
            raise HTTPException(status_code=404, detail=f"Spread {spread_name} not found")
        
        # Get historical data
        hist_values = spread_calculator._get_spread_history(spread_name)
        stats = spread_calculator._calculate_statistics(spread_value, hist_values, spread_name)
        
        # Determine color based on z-score
        zscore_5d = stats.get("zscore_5d", 0)
        if abs(zscore_5d) > 2.0:
            color = "critical_red" if zscore_5d > 0 else "critical_green"
        elif abs(zscore_5d) > 1.5:
            color = "warning_orange"
        else:
            color = "neutral_gray"
        
        stats["color"] = color
        
        return {
            "status": "success",
            "data": {
                "spread_name": spread_name,
                **stats
            },
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching spread {spread_name}: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== ALERTS ENDPOINTS ====================
@app.get("/api/alerts/active")
async def get_active_alerts(db: Session = Depends(get_db)):
    """Get all active unacknowledged alerts"""
    try:
        prices = PriceFetcher.fetch_all_prices()
        spreads = spread_calculator.calculate_all_spreads(prices)
        
        # Detect anomalies
        anomalies = spread_calculator.detect_anomalies(spreads)
        
        alerts = []
        for anomaly in anomalies:
            alerts.append({
                "id": f"anomaly_{anomaly['spread']}_{anomaly['type']}",
                "type": anomaly["type"],
                "severity": anomaly["severity"],
                "message": anomaly["message"],
                "symbol": anomaly.get("spread"),
                "value": anomaly.get("value"),
                "created_at": anomaly.get("timestamp"),
                "is_acknowledged": False
            })
        
        # Add price spike alerts
        for symbol, price_data in prices.items():
            if abs(price_data.get("change_pct", 0)) > 3.0:
                alerts.append({
                    "id": f"price_move_{symbol}",
                    "type": "price_spike",
                    "severity": "warning" if abs(price_data["change_pct"]) < 5.0 else "critical",
                    "message": f"{symbol} moved {price_data['change_pct']:.2f}%",
                    "symbol": symbol,
                    "value": price_data.get("change_pct"),
                    "created_at": datetime.now().isoformat(),
                    "is_acknowledged": False
                })
        
        return {
            "status": "success",
            "data": alerts,
            "count": len(alerts),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    """Acknowledge an alert"""
    try:
        # In production, persist to database
        return {
            "status": "success",
            "message": f"Alert {alert_id} acknowledged",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== ENHANCED NEWS ENDPOINTS ====================
@app.get("/api/news/enhanced")
async def get_enhanced_news():
    """Get enhanced news with full sentiment analysis"""
    try:
        news = NewsFetcher.fetch_all_news(max_articles_per_source=10)
        return {
            "status": "success",
            "data": news[:20],  # Return top 20
            "count": len(news),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching enhanced news: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/storms/active')
async def api_get_active_storms():
    """Return NOAA NHC active storms with refinery overlay."""
    try:
        data = fetch_active_storms()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error in storms endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/tankers/positions')
async def api_get_tanker_positions():
    """Return AIS tanker zone snapshots or offline status if key missing."""
    try:
        data = fetch_tanker_positions()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error in tankers endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/news/sentiment-summary")
async def get_sentiment_summary():
    """Get overall market sentiment from latest news"""
    try:
        summary = NewsFetcher.get_sentiment_summary()
        return {
            "status": "success",
            "data": summary,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching sentiment summary: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/news/finbert-status")
async def get_finbert_status():
    """Return FinBERT availability and a lightweight service check."""
    try:
        enabled = bool(os.getenv("HF_API_KEY"))
        result = {
            "enabled": enabled,
            "status": "online" if enabled else "offline",
            "message": "FinBERT configured" if enabled else "HF_API_KEY missing",
            "last_test": None,
            "timestamp": datetime.now().isoformat(),
        }
        if enabled:
            score, label = SentimentAnalyzer.analyze_finbert(
                "Energy market outlook checking FinBERT live status"
            )
            result["last_test"] = {
                "score": score,
                "label": label,
            }
        return {"status": "success", "data": result, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error checking FinBERT status: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/news/by-entity/{entity}")
async def get_news_by_entity(entity: str):
    """Get news filtered by geopolitical entity"""
    try:
        news = NewsFetcher.fetch_all_news(max_articles_per_source=15)
        filtered = [n for n in news if entity.lower() in [e.lower() for e in n.get("entities", [])]]
        return {
            "status": "success",
            "data": filtered,
            "entity": entity,
            "count": len(filtered),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching news by entity: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== SPREADS ENDPOINTS ====================
@app.get("/api/spreads/calendar")
async def get_calendar_spreads():
    """Get calendar spreads (M1-M4 data)"""
    try:
        # Placeholder implementation - in production would fetch from CME
        spreads = {
            "M1_M2": 0.35,
            "M2_M3": 0.25,
            "M3_M4": 0.15,
            "curve_shape": "BACKWARDATION",
            "timestamp": datetime.now().isoformat(),
        }
        return {"status": "success", "data": spreads}
    except Exception as e:
        logger.error(f"Error fetching calendar spreads: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== CRACK SPREADS ENDPOINTS ====================
@app.get("/api/spreads/crack")
async def get_crack_spreads():
    """Get crack spread calculations"""
    try:
        prices = PriceFetcher.fetch_all_prices()

        rbob_data = prices.get("RBOB")
        ho_data = prices.get("HO")
        wti_data = prices.get("WTI")
        brent_data = prices.get("Brent")
        go_data = prices.get("GO")

        if not (rbob_data and ho_data and wti_data and brent_data):
            raise HTTPException(status_code=503, detail="Insufficient price data for crack spread computation")

        cracks = SignalCalculator.calculate_crack_spreads(
            rbob=float(rbob_data["close"]),
            ulsd=float(ho_data["close"]),
            wti=float(wti_data["close"]),
            brent=float(brent_data["close"]),
            go_per_mt=float(go_data["close"]) if go_data else None,
        )
        return {"status": "success", "data": cracks}
    except Exception as e:
        logger.error(f"Error calculating crack spreads: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== HEALTH CHECK ====================
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
