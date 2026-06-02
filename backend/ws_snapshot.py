"""Simulated snapshot builder and WebSocket route registration.

This module provides a simple `/ws` WebSocket router that sends a
minimal dashboard snapshot every `TICK_SECONDS`. Import and include
the `router` from `backend.main` or call `register_router(app)`.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import time
from typing import Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

TICK_SECONDS = 2.0

router = APIRouter()


def build_snapshot_simulated(tick: int = 0) -> Dict[str, Any]:
    now = datetime.datetime.utcnow().isoformat() + "Z"
    header = {
        "regime": "NEUTRAL",
        "vol_regime": "NORMAL",
        "composite_score": 0,
        "prices": {"WTI": {"price": 75.0 + (tick % 5), "change": 0.1, "change_pct": 0.13}}
    }
    snapshot = {
        "ts": now,
        "tick": tick,
        "sources": {"price_fetcher": {"last_updated": now, "ok": True}},
        "header": header,
        "price": {
            "symbols": ["WTI"],
            "data": {"WTI": {"price": 75.0 + (tick % 5), "change": 0.1, "change_pct": 0.13, "high": 76, "low": 74, "sparkline": [74,75,76]}}
        },
        "bb": {"symbol": "WTI", "upper": [], "middle": [], "lower": [], "price": [], "timestamps": [], "bandwidth": 0.02, "pct_b": 0.5, "squeeze": False},
        "signals": {"composite_score": 0, "regime": "NEUTRAL", "vol_annualized": 0},
        "news": [],
        "news_sentiment": {"overall": 0, "finbert_loaded": False, "breakdown": {"bullish": 0, "bearish": 0, "neutral": 0}},
        "cot": {"mm_long": 0, "mm_short": 0, "mm_net": 0, "open_interest": 0, "report_date": now, "history_12w": []},
        "steo": None,
        "seasonality": None,
        "paper": {"equity": 100000, "total_return_pct": 0, "realized_pnl": 0, "unrealized_pnl": 0, "open_positions": [], "closed_trades": [], "equity_curve": [100000]},
        "tankers": None,
        "storms": {"storms": [], "total_at_risk_capacity_mbpd": 0, "season_active": False},
    }
    return snapshot


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    tick = 0
    try:
        while True:
            snapshot = build_snapshot_simulated(tick=tick)
            await websocket.send_text(json.dumps(snapshot))
            tick += 1
            await asyncio.sleep(TICK_SECONDS)
    except WebSocketDisconnect:
        return


def register_router(app):
    """Helper to include the router into the FastAPI app."""
    app.include_router(router)
