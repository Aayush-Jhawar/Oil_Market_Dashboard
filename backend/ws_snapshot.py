"""Simulated snapshot builder and WebSocket route registration.

This module provides a simple `/ws` WebSocket router that sends a
dashboard snapshot every `TICK_SECONDS`. On each tick it computes
real Bollinger Bands and EMA from the actual WTI price history
(via PriceFetcher), falling back to synthetic data if unavailable.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import time
from typing import Dict, Any, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

TICK_SECONDS = 5.0

router = APIRouter()

# ─── Real BB computation ───────────────────────────────────────────────────

def _build_real_bb() -> Dict[str, Any]:
    """Try to compute real Bollinger Bands from WTI 3-month history."""
    try:
        from services.price_fetcher import PriceFetcher
        from indicators import bollinger_bands, ema
        import pandas as pd

        hist = PriceFetcher.fetch_historical("WTI", "3mo") or []
        if len(hist) < 20:
            return {}

        # Use last 90 points max for performance
        hist = hist[-90:]
        closes = pd.Series([float(h["close"]) for h in hist])
        timestamps = [h["timestamp"][:10] for h in hist]  # YYYY-MM-DD

        bb = bollinger_bands(closes, period=20, std=2.0)
        ema50 = ema(closes, period=50)

        upper = [round(v, 2) if v == v else None for v in bb["upper"].tolist()]
        lower = [round(v, 2) if v == v else None for v in bb["lower"].tolist()]
        middle = [round(v, 2) if v == v else None for v in bb["middle"].tolist()]
        price = [round(v, 2) if v == v else None for v in closes.tolist()]

        last_price = closes.iloc[-1]
        last_upper = bb["upper"].iloc[-1]
        last_lower = bb["lower"].iloc[-1]
        last_middle = bb["middle"].iloc[-1]
        last_bw = float(bb["bandwidth"].iloc[-1])
        last_pct_b = float(bb["pct_b"].iloc[-1]) if bb["pct_b"].iloc[-1] == bb["pct_b"].iloc[-1] else 0.5

        # Squeeze: bandwidth < 20th-percentile of its own history
        bw_series = bb["bandwidth"].dropna()
        squeeze = bool(last_bw < float(bw_series.quantile(0.20))) if len(bw_series) > 5 else False

        return {
            "symbol": "WTI",
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "price": price,
            "timestamps": timestamps,
            "bandwidth": round(last_bw, 4),
            "pct_b": round(last_pct_b, 4),
            "squeeze": squeeze,
            "ema50": round(float(ema50.iloc[-1]), 2),
            "current_price": round(float(last_price), 2),
            "current_upper": round(float(last_upper), 2),
            "current_lower": round(float(last_lower), 2),
            "current_middle": round(float(last_middle), 2),
        }
    except Exception as e:
        return {}


def _build_real_paper() -> Dict[str, Any]:
    """Return real paper trading book state."""
    try:
        from paper import paper_book
        return paper_book.get_state()
    except Exception:
        return {}


def _build_real_seasonality() -> Dict[str, Any]:
    """Return computed seasonality data."""
    try:
        from seasonality import fetch_seasonality
        return fetch_seasonality()
    except Exception:
        return {}


def _build_real_multi_factor() -> Dict[str, Any]:
    """Return computed multi-factor score for all key symbols."""
    try:
        from services.multi_factor_engine import compute_multi_factor_score
        from services.price_fetcher import PriceFetcher
        
        results = {}
        for sym in ["WTI", "Brent", "RBOB", "HO"]:
            hist = PriceFetcher.fetch_historical(sym, "3mo") or []
            if len(hist) < 20:
                continue
            mf = compute_multi_factor_score(sym, hist)
            results[sym] = mf
            
        return results
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error building multi_factor: {e}")
        return {}


# ─── Cached data (refreshed every N ticks) ────────────────────────────────

_cache: Dict[str, Any] = {}
_cache_tick = -1
BB_CACHE_TICKS = 6      # refresh BB every ~30s  (6 × 5s ticks)
SLOW_CACHE_TICKS = 12   # refresh paper/seasonality every ~60s
PRICE_CACHE_TICKS = 12  # refresh all prices every ~60s
CURVE_CACHE_TICKS = 60  # refresh forward curve every ~5 min

# Symbols to include in the price strip
# Symbols pushed live in the header price strip. DXY and GO must be included
# here or they only ever load once from the REST /api/prices/all call and show
# "—" in the top strip whenever that initial load is delayed or fails.
PRICE_STRIP_SYMBOLS = ["WTI", "RBOB", "HO", "Brent", "GO", "DXY"]


def _build_real_prices() -> Dict[str, Any]:
    """Fetch current prices for the strip symbols via PriceFetcher."""
    try:
        from services.price_fetcher import PriceFetcher
        all_prices = PriceFetcher.fetch_all_prices()
        result: Dict[str, Any] = {}
        for sym in PRICE_STRIP_SYMBOLS:
            p = all_prices.get(sym)
            if p:
                result[sym] = {
                    "price":      p.get("close", 0.0),
                    "open":       p.get("open", 0.0),
                    "high":       p.get("high", 0.0),
                    "low":        p.get("low", 0.0),
                    "change_pct": p.get("change_pct", 0.0),
                    "change":     0.0,
                    "volume":     p.get("volume", 0),
                }
            else:
                # Use default fallback so the strip never shows '—'
                d = PriceFetcher.DEFAULT_PRICES.get(sym, {})
                result[sym] = {
                    "price":      d.get("close", 0.0),
                    "open":       d.get("open", 0.0),
                    "high":       d.get("high", 0.0),
                    "low":        d.get("low", 0.0),
                    "change_pct": d.get("change_pct", 0.0),
                    "change":     0.0,
                    "volume":     0,
                }
        return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"_build_real_prices failed: {e}")
        return {}


def _build_real_forward_curve() -> Dict[str, Any]:
    """Fetch WTI M1-M12 forward curve via the forward_curve service."""
    try:
        from services.forward_curve import fetch_forward_curve
        curve_points, meta = fetch_forward_curve()
        if not curve_points:
            return {}
        # curve dict: {M1: price, M2: price, ...} for snapshot.futures.curve
        curve_dict = {p["month"]: p["price"] for p in curve_points}
        # detailed list for snapshot.futures.points
        return {
            "curve":        curve_dict,
            "points":       curve_points,
            "structure":    meta.get("structure", "UNKNOWN"),
            "m1_m12_spread": meta.get("m1_m12_spread"),
            "m1_price":     meta.get("m1_price"),
            "m12_price":    meta.get("m12_price"),
            "fetched_at":   meta.get("fetched_at"),
            "ok":           meta.get("ok", False),
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"_build_real_forward_curve failed: {e}")
        return {}


def build_snapshot(tick: int = 0) -> Dict[str, Any]:
    global _cache, _cache_tick

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

    # Refresh BB data
    if tick % BB_CACHE_TICKS == 0 or "bb" not in _cache:
        real_bb = _build_real_bb()
        _cache["bb"] = real_bb if real_bb else _synthetic_bb(tick)

    # Refresh all product prices
    if tick % PRICE_CACHE_TICKS == 0 or "prices" not in _cache:
        real_prices = _build_real_prices()
        _cache["prices"] = real_prices if real_prices else {}

    # Refresh forward curve (expensive — every ~5 min)
    if tick % CURVE_CACHE_TICKS == 0 or "futures" not in _cache:
        curve_data = _build_real_forward_curve()
        _cache["futures"] = curve_data if curve_data else {}

    # Refresh slow data
    if tick % SLOW_CACHE_TICKS == 0 or "paper" not in _cache:
        paper = _build_real_paper()
        _cache["paper"] = paper if paper else _synthetic_paper()
        season = _build_real_seasonality()
        _cache["seasonality"] = season if season else _synthetic_seasonality()
        mf = _build_real_multi_factor()
        _cache["multi_factor"] = mf if mf else {}

    bb = _cache.get("bb", _synthetic_bb(tick))
    prices_map = _cache.get("prices", {})
    futures_data = _cache.get("futures", {})
    paper = _cache.get("paper", _synthetic_paper())
    seasonality = _cache.get("seasonality", _synthetic_seasonality())
    mf = _cache.get("multi_factor", {})

    mf_wti = mf.get("WTI", {})

    # Compute composite score signal hint (Default to WTI)
    if "composite_score" in mf_wti:
        composite_score = mf_wti["composite_score"]
        regime = mf_wti.get("regime", "NEUTRAL")
    else:
        pct_b = bb.get("pct_b", 0.5)
        composite_score = round((pct_b - 0.5) * 100, 1)  # −50 to +50 range
        regime = "BULLISH" if pct_b > 0.6 else "BEARISH" if pct_b < 0.4 else "NEUTRAL"

    # Inject AI Prediction data if available
    regimes = {}          # per-symbol curve structure labels for header
    curve_structures = {} # separate from directional regime
    
    try:
        from main import _latest_intraday
        
        # Get WTI AI predictions for composite score override
        latest = _latest_intraday.get("WTI", {})
        if "trade_signal" in latest and "trade_score" in latest["trade_signal"]:
            score = latest["trade_signal"].get("trade_score", 50)
            if score is not None:
                composite_score = float(score) - 50.0
                # Derive directional regime from trade score, NOT from curve structure
                if composite_score > 20:
                    regime = "BULLISH"
                elif composite_score < -20:
                    regime = "BEARISH"
                else:
                    regime = "NEUTRAL"
                    
        # Map all symbols — regime_label here is CURVE STRUCTURE (Backwardation/Contango)
        for sym, data in _latest_intraday.items():
            if isinstance(data, dict):
                curve_label = data.get("curve_structure", "INITIALIZING")
                if curve_label == "UNKNOWN" and "regime_state" in data:
                    curve_label = "INITIALIZING"
                regimes[sym] = curve_label
                curve_structures[sym] = curve_label
    except ImportError:
        pass

    # Build `signals_by_symbol` payload
    signals_by_symbol = {}
    for sym, sym_mf in mf.items():
        signals_by_symbol[sym] = {
            "composite_score": sym_mf.get("composite_score", 0),
            "regime": sym_mf.get("regime", "NEUTRAL"),
            "regime_type": sym_mf.get("regime_type", "RANGING"),
            "signal": sym_mf.get("signal", "NEUTRAL"),
            "confidence": sym_mf.get("confidence", 0),
            "vol_annualized": sym_mf.get("annual_vol_pct", 0),
            "vol_regime": "ELEVATED" if bb.get("squeeze") else "NORMAL",
            "factor_scores": sym_mf.get("factor_scores", {}),
            "sub_scores": sym_mf.get("sub_scores", {}),
            "weights": sym_mf.get("weights", {}),
        }
        
        # Override with AI trade score if available
        try:
            from main import _latest_intraday
            latest_sym = _latest_intraday.get(sym, {})
            if "trade_signal" in latest_sym and "trade_score" in latest_sym["trade_signal"]:
                score = latest_sym["trade_signal"].get("trade_score")
                if score is not None:
                    cs = float(score) - 50.0
                    signals_by_symbol[sym]["composite_score"] = cs
                    if cs > 20:
                        signals_by_symbol[sym]["regime"] = "BULLISH"
                    elif cs < -20:
                        signals_by_symbol[sym]["regime"] = "BEARISH"
                    else:
                        signals_by_symbol[sym]["regime"] = "NEUTRAL"
        except ImportError:
            pass

    snapshot = {
        "ts": now,
        "tick": tick,
        "sources": {"price_fetcher": {"last_updated": now, "ok": True}},
        "header": {
            "regime": regime,
            "regimes": regimes,
            "vol_regime": "ELEVATED" if bb.get("squeeze") else "NORMAL",
            "composite_score": composite_score,
            "prices": {
                sym: {"price": v["price"], "change": v.get("change", 0.0), "change_pct": v.get("change_pct", 0.0)}
                for sym, v in prices_map.items()
            } if prices_map else {
                "WTI": {"price": bb.get("current_price", 75.0), "change": 0.0, "change_pct": 0.0}
            },
        },
        "price": {
            "symbols": list(prices_map.keys()) if prices_map else ["WTI"],
            "data": prices_map if prices_map else {
                "WTI": {
                    "price":      bb.get("current_price", 75.0),
                    "change":     0.0,
                    "change_pct": 0.0,
                    "high":       bb.get("current_upper", 77.0),
                    "low":        bb.get("current_lower", 73.0),
                    "sparkline":  (bb.get("price") or [75.0])[-10:],
                }
            },
        },
        "bb": bb,
        "futures": futures_data if futures_data else {},
        "covmatrix": {
            "symbols": ["WTI", "Brent", "RBOB", "HO"],
            "correlation": [
                [1.0,    0.918,  0.774,  0.869],
                [0.918,  1.0,    0.841,  0.861],
                [0.774,  0.841,  1.0,    0.835],
                [0.869,  0.861,  0.835,  1.0  ],
            ],
        },
        "signals": signals_by_symbol.get("WTI", {
            "composite_score": composite_score,
            "regime": regime,
            "regime_type": "RANGING",
            "signal": "NEUTRAL",
            "confidence": 0,
            "vol_annualized": 0,
            "vol_regime": "ELEVATED" if bb.get("squeeze") else "NORMAL",
            "factor_scores": {},
            "sub_scores": {},
            "weights": {}
        }),
        "signals_by_symbol": signals_by_symbol,
        "news": [],
        "news_sentiment": {
            "overall": 0,
            "finbert_loaded": __import__('sentiment').finbert_ready() if hasattr(__import__('sentiment'), 'finbert_ready') else False,
            "breakdown": {"bullish": 0, "bearish": 0, "neutral": 0},
        },

        "cot": {
            "mm_long": 0, "mm_short": 0, "mm_net": 0,
            "open_interest": 0,
            "report_date": now,
            "history_12w": [],
        },
        "steo": None,
        "seasonality": seasonality,
        "paper": paper,
        "tankers": None,
        "storms": {
            "storms": [],
            "total_at_risk_capacity_mbpd": 0,
            "season_active": False,
        },
    }
    return snapshot


# ─── Synthetic fallbacks ──────────────────────────────────────────────────

def _synthetic_bb(tick: int) -> Dict[str, Any]:
    base = 75.0 + (tick % 5) * 0.1
    n = 30
    prices = [round(base + (i - n // 2) * 0.15, 2) for i in range(n)]
    timestamps = [f"D{i+1}" for i in range(n)]
    upper = [round(p + 2.0, 2) for p in prices]
    lower = [round(p - 2.0, 2) for p in prices]
    middle = prices[:]
    return {
        "symbol": "WTI",
        "upper": upper, "middle": middle, "lower": lower, "price": prices,
        "timestamps": timestamps,
        "bandwidth": 0.053, "pct_b": 0.5, "squeeze": False,
        "current_price": prices[-1],
        "current_upper": upper[-1], "current_lower": lower[-1],
        "current_middle": middle[-1],
    }


def _synthetic_paper() -> Dict[str, Any]:
    return {
        "equity": 100000.0, "total_return_pct": 0.0,
        "realized_pnl": 0.0, "unrealized_pnl": 0.0,
        "win_rate": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
        "open_positions": [], "closed_trades": [],
        "equity_curve": [100000.0],
    }


def _synthetic_seasonality() -> Dict[str, Any]:
    import math, datetime as dt
    today = dt.date.today()
    current_week = today.isocalendar()[1]
    weeks = []
    for w in range(1, 53):
        theta = 2 * math.pi * (w - 1) / 52
        norm = round(88.5 + 5.0 * math.sin(theta - math.pi / 3), 1)
        sigma = round(1.8 + 0.8 * abs(math.sin(2 * theta)), 2)
        current = round(norm + (1.2 if w <= current_week else 0), 1)
        weeks.append({"week_num": w, "norm_pct": norm, "sigma_dev": sigma,
                       "current_pct": current, "is_current_week": w == current_week})
    cw = weeks[current_week - 1]
    delta = cw["current_pct"] - cw["norm_pct"]
    return {
        "weeks": weeks,
        "current_week": current_week,
        "current_vs_norm_pct": round(delta, 2),
        "deviation_sigma": round(delta / cw["sigma_dev"], 2) if cw["sigma_dev"] else 0.0,
    }


# ─── WebSocket endpoint ────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    tick = 0
    loop = asyncio.get_event_loop()
    try:
        while True:
            snapshot = await loop.run_in_executor(None, build_snapshot, tick)
            await websocket.send_text(json.dumps(snapshot, default=str))
            tick += 1
            await asyncio.sleep(TICK_SECONDS)
    except WebSocketDisconnect:
        return


def register_router(app):
    """Helper to include the router into the FastAPI app."""
    app.include_router(router)
