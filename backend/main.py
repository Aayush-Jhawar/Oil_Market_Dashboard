# Paper trading state repaired — all trade caps removed
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import asyncio
import json
import statistics
from typing import List, Set
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import PriceData, InventoryData, NewsItem
from services.price_fetcher import PriceFetcher

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.news_fetcher import NewsFetcher
from services.eia_fetcher import EIAFetcher
from services.macro_fetcher import MacroFetcher, RigCountFetcher, CFTCFetcher
from services.sentiment_analyzer import SentimentAnalyzer
from services.spread_analyzer import SpreadCalculator, AnomalyDetector

# Initialize components
news_fetcher = NewsFetcher()
macro_fetcher = MacroFetcher()
eia_fetcher = EIAFetcher()
cftc_fetcher = CFTCFetcher()
from signal_calc import SignalCalculator
from services.multi_factor_engine import compute_multi_factor_score, calculate_relative_strength
from services.composite_score import get_composite as get_model_composite
from ws_snapshot import register_router as register_ws_snapshot

# Base commodities that have a trained ML model driving the composite score.
_MODEL_SYMBOLS = {"WTI", "Brent", "RBOB", "HO", "GO"}
from hurricane import StormTracker
from ais import TankerTracker
from datetime import datetime, timedelta
import logging
from cot import fetch_cot
from steo import fetch_steo
from seasonality import fetch_seasonality
from sentiment import analyze_news_items, warm_finbert
from paper import paper_book
from indicators import ewma_cov_matrix
import pandas as pd

# Initialize logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

# Suppress httpx INFO logs which expose API keys in URLs
logging.getLogger("httpx").setLevel(logging.WARNING)

# Create database tables
Base.metadata.create_all(bind=engine)

# Core FastAPI App
# Hot reload trigger

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

# Model Analytics endpoints (/api/models/*) for the composite-score models.
try:
    from ml.api import router as models_router
    app.include_router(models_router)
except Exception as _mr_err:
    logger.warning(f"model analytics router not mounted: {_mr_err}")

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing FinBERT in the background...")
    warm_finbert()

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


# module-level manager and background tasks
ws_manager = WebSocketManager()
_background_tasks = []
_latest_intraday = {}

# global data structures for ported modules
global_tankers = TankerTracker()
global_storms = StormTracker()
global_cot = None
global_steo = None


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
    from services.regime_classifier import regime_classifier
    from services.zscore_strategy import zscore_strategy
    from services.forward_curve import get_curve_as_dict
    while True:
        try:
            prices = await loop.run_in_executor(None, PriceFetcher.fetch_all_prices)
            news = await loop.run_in_executor(None, NewsFetcher.fetch_all_news)
            macro = await loop.run_in_executor(None, MacroFetcher.fetch_all_macro)
            news_sentiment = NewsFetcher.calculate_sentiment_trend(news)
            
            # Compute regimes for base symbols
            regime_info_map = {}
            for base in ["WTI", "Brent", "HO", "GO"]:
                try:
                    # get_curve_as_dict makes blocking yfinance/DB calls — run it in the
                    # threadpool so it never stalls the asyncio event loop.
                    curve = await loop.run_in_executor(None, get_curve_as_dict, base)
                    numeric_curve = {int(k[1:]): v for k, v in curve.items() if k.startswith("M") and k[1:].isdigit()}
                    regime_info_map[base] = regime_classifier.classify(base, numeric_curve)
                except Exception:
                    pass
            
            by_symbol = {}
            all_target_symbols = ["WTI", "Brent", "RBOB", "HO", "GO", "3-2-1CRACK", "GASCRACK", "DIESELCRACK", "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY", "WTI-Brent", "DUB-WTI"]

            for sym in all_target_symbols:
                hist = await loop.run_in_executor(None, PriceFetcher.fetch_historical, sym, "3mo")
                closes = [float(h["close"]) for h in (hist or [])] if hist else []

                # Full multi-factor composite (same engine the REST /api/signals/composite
                # endpoint uses) so the WebSocket snapshot carries real composite_score,
                # factor_scores and volatility — not a z-score proxy with empty factors.
                mf = {}
                if hist and len(hist) >= 20:
                    mf = await loop.run_in_executor(
                        None, compute_multi_factor_score, sym, hist, macro, None, None
                    )

                vol = mf.get("annual_vol_pct")
                if vol is None:
                    vol = SignalCalculator.calculate_realized_volatility(closes) if closes else 0.0

                sub = dict(mf.get("sub_scores", {}) or {})
                sub["news_sentiment"] = round(news_sentiment, 3)

                by_symbol[sym] = {
                    "composite_score": mf.get("composite_score", 0.0),
                    "regime": mf.get("regime", "NEUTRAL"),
                    "regime_type": mf.get("regime_type", "UNKNOWN"),
                    "signal": mf.get("signal", "NEUTRAL"),
                    "confidence": mf.get("confidence", 0.0),
                    "sub_scores": sub,
                    "weights": mf.get("factor_weights", {}),
                    "volatility_pct": round(vol, 1),
                    "vol_regime": SignalCalculator.get_vol_regime(vol),
                    "factor_scores": mf.get("factor_scores", {}),
                }

                # Anchor the headline on the trained directional model for the
                # base commodities (5d horizon) so the composite stops cancelling
                # to ~0. The technical `mf` result is retained as the factor
                # breakdown + a 25% adjustment inside get_model_composite. Falls
                # back to the tech score untouched if no model / import fails.
                if sym in _MODEL_SYMBOLS:
                    try:
                        merged = await loop.run_in_executor(
                            None, get_model_composite, sym, "5d", by_symbol[sym], news_sentiment
                        )
                        if merged:
                            by_symbol[sym] = merged
                    except Exception as _mc_err:
                        logger.debug(f"model composite skipped for {sym}: {_mc_err}")

            wti_res = by_symbol.get("WTI", {})

            # Format _latest_intraday to mock the old structure for the UI
            ui_predictions = {}
            for sym, data in by_symbol.items():
                cs = data.get("composite_score", 0.0)
                
                # Extract structural curve regime (e.g. BACKWARDATION, CONTANGO)
                # Defaults to "Neutral" if missing.
                curve_info = regime_info_map.get(sym, {})
                if not curve_info and sym in ["RBOB", "HO"]:
                    curve_info = regime_info_map.get("WTI", {})
                curve_structure = curve_info.get("regime", "Neutral").upper()
                
                ui_predictions[sym] = {
                    "regime_state": {"regime_label": data["regime"], "severity": data["regime_type"]},
                    "curve_structure": curve_structure,
                    "trade_signal": {
                        "direction": data["signal"],
                        "confidence": data.get("confidence", 0.0),
                        # composite_score is in [-100, +100]; map to a 0-100 trade score
                        "trade_score": 50 + (cs / 2.0),
                        "factor_scores": data.get("factor_scores", {}),
                    }
                }

            global _latest_intraday
            _latest_intraday.update(ui_predictions)

            payload = {
                "type": "signals",
                "data": {
                    "composite_score": wti_res.get("composite_score", 0.0),
                    "regime": wti_res.get("regime", "NEUTRAL"),
                    "regime_type": wti_res.get("regime_type", "UNKNOWN"),
                    "signal": wti_res.get("signal", "NEUTRAL"),
                    "ai_predictions": _latest_intraday,
                    "sub_scores": wti_res.get("sub_scores", {}),
                    "weights": wti_res.get("weights", {}),
                    "volatility_pct": wti_res.get("volatility_pct", 0.0),
                    "vol_regime": wti_res.get("vol_regime", "NORMAL"),
                    "factor_scores": wti_res.get("factor_scores", {}),
                    "by_symbol": by_symbol,
                },
                "timestamp": datetime.now().isoformat(),
            }
            await ws_manager.broadcast(payload)
        except Exception as e:
            logger.warning(f"Signals publisher error: {e}")
        await asyncio.sleep(60)


async def _warmup_cache():
    loop = asyncio.get_event_loop()
    try:
        logger.info("Starting cache warm-up...")
        await loop.run_in_executor(None, PriceFetcher.fetch_all_prices)
        
        def warmup_spreads():
            symbols = ["WTI", "Brent", "RBOB", "HO", "DUBAICRUDE", "HH"]
            histories = {}
            for sym in symbols:
                hist = PriceFetcher.fetch_historical(sym, "1mo")
                if hist:
                    histories[sym] = {item["timestamp"]: float(item["close"]) for item in hist}
            
            if histories.get("WTI"):
                for date in sorted(histories["WTI"].keys()):
                    prices_for_date = {}
                    for sym, hist in histories.items():
                        if date in hist:
                            prices_for_date[sym] = {"close": hist[date]}
                    try:
                        dt = datetime.fromisoformat(date[:10])
                        spread_calculator.add_price_data(prices_for_date, dt)
                    except Exception:
                        pass

        await loop.run_in_executor(None, warmup_spreads)

        # Pre-warm the composite signal cache so the first browser load hits
        # the cache (~0.02s) instead of computing cold (~8s).
        try:
            await loop.run_in_executor(None, get_composite_signal)
            logger.info("Composite signal cache pre-warmed.")
        except Exception as ce:
            logger.warning(f"Composite cache pre-warm failed: {ce}")

        logger.info("Cache warm-up complete.")
    except Exception as e:
        logger.error(f"Cache warm-up failed: {e}")


async def _paper_trading_publisher():
    """Background task: drive the paper book from the live 15-minute candle DB.

    The Z-Score strategy was validated in the research journals on 15-minute bars
    with a 20-bar rolling window. We replay the candles in `DB/bars_15min_latest.db`
    (the same data the backtest/journals used) through the audited strategy each
    cycle, so the paper book reflects exactly the trades the strategy takes on the
    real candles that have been received. The engine treats the DB as a LIVE,
    append-only feed: executed trades are frozen and only candles newer than the
    persisted high-water mark generate new trades on the next cycle. Drawdown is
    monotonic and is never recomputed away.
    """
    loop = asyncio.get_event_loop()
    from services.bars15_paper_engine import run_replay

    # Local, non-synced DB dir (see config.BARS15_DB_DIR) — never the OneDrive DB/.
    db_dir = os.environ.get("BARS15_DB_DIR") or os.path.join(os.path.dirname(__file__), "..", "DB")
    starting_equity = paper_book.starting_equity

    while True:
        try:
            state = await loop.run_in_executor(None, run_replay, db_dir, starting_equity)
            if state:
                # apply_replay overwrites the strategy ledger + persists paper_state.json.
                # regime_classifier.classify (inside run_replay) persists regime_state.json.
                await loop.run_in_executor(None, paper_book.apply_replay, state)
                logger.info(
                    "Paper replay: %d candles across %d instruments -> %d closed trades, "
                    "%d open, ticks %.1f (last bar %s)",
                    state.get("bars_processed", 0), state.get("instruments_traded", 0),
                    len(state.get("closed_trades", [])), len(state.get("open_positions", [])),
                    state.get("total_pnl_ticks", 0.0), state.get("last_bar_ts"),
                )
            else:
                logger.warning("Paper replay: no usable 15-min candle data found in %s", db_dir)
        except Exception as e:
            logger.warning(f"Paper trading publisher error: {e}")
        # Re-run on a 1-minute cadence to match the DB sync cadence.
        await asyncio.sleep(60)


@app.on_event("startup")
async def _start_background_publishers():
    # Load and resample files in /Data directory into sqlite database
    try:
        from services.data_loader import populate_database_pipeline
        populate_database_pipeline()
    except Exception as e:
        logger.error(f"Error populating database with /Data: {e}")

    # Seed the spread calculator's daily history so /api/spreads/all returns real
    # 5d/30d means, std and z-scores instead of mean==value / 0.00σ for every
    # spread. _warmup_cache does its blocking yfinance/DB fetches inside a thread
    # executor, so running it as a background task does not block startup; the
    # KEY SPREADS panel fills in its deltas a few seconds after boot.
    _background_tasks.append(asyncio.create_task(_warmup_cache()))

    # start background publishers
    _background_tasks.append(asyncio.create_task(_price_publisher()))
    _background_tasks.append(asyncio.create_task(_signals_publisher()))
    _background_tasks.append(asyncio.create_task(_paper_trading_publisher()))

    # mtime cache: skip I-drive snapshots that haven't changed since last merge.
    # Keyed by full source path → float mtime. Lives in the closure so it
    # persists across sync runs for the lifetime of the process.
    _synced_mtimes: dict = {}

    def _run_db_sync_blocking():
        import sqlite3 as _sqlite3
        import os
        import glob as _glob
        source_dir = r"I:\Public\Summer Interns Energy\DB"
        # Merge ALL bars_15min_*.db snapshots so history accumulates locally
        # even when each I-drive snapshot only contains a short recent window.
        candidates = sorted(_glob.glob(os.path.join(source_dir, "bars_15min_????????.db")))
        if not candidates:
            logger.warning("DB sync: no bars_15min_*.db found on I drive, skipping")
            return
        dest_db = os.environ.get("BARS15_DB_PATH") or os.path.join(os.path.dirname(__file__), "..", "DB", "bars_15min_latest.db")
        # WAL + a bounded busy_timeout so this merge never blocks the price/curve
        # readers of bars_15min_latest.db (forward_curve / bars15 paper engine) and
        # never waits indefinitely on a lock. We commit once per source snapshot so
        # the write lock is held in short bursts instead of for the whole job — a
        # long single transaction here is what previously wedged /api/prices/all.
        dest_conn = _sqlite3.connect(dest_db, timeout=10)
        total_inserted = 0
        latest = {}
        try:
            dest_conn.execute("PRAGMA journal_mode=WAL")
            dest_conn.execute("PRAGMA busy_timeout=10000")
            for src_db in candidates:
                src_conn = None
                temp_db = None
                try:
                    import shutil
                    import tempfile

                    # Skip files whose mtime hasn't changed since the last successful
                    # merge — avoids re-copying every historical snapshot over SMB
                    # each cycle, which is the main source of sync lag.
                    try:
                        _cur_mtime = os.path.getmtime(src_db)
                    except Exception:
                        _cur_mtime = None
                    if _cur_mtime is not None and _synced_mtimes.get(src_db) == _cur_mtime:
                        continue

                    # Copy ONLY the main .db from the I drive to local temp. We do
                    # NOT copy the -wal/-shm sidecars, and this is deliberate:
                    #   * On the live source the -wal is held with a byte-range lock
                    #     (Windows error 33). The old code copied the sidecars inside
                    #     the same try-block, so that lock raised and the `continue`
                    #     skipped the ENTIRE snapshot — which is why the local DB
                    #     froze (e.g. stuck at 00:00 while the source had 01:00).
                    #   * SQLite also cannot replay a WAL read-only over the SMB
                    #     network share (it needs -shm shared memory; opening the
                    #     source ro/backup yields "file is not a database").
                    # The source auto-checkpoints into its main .db, so the copied
                    # main file carries everything up to the last checkpoint, and
                    # INSERT OR IGNORE folds in the new rows each cycle. Worst case
                    # we trail the source's un-checkpointed WAL tail by one
                    # checkpoint interval instead of being frozen indefinitely.
                    temp_dir = tempfile.gettempdir()
                    base_name = os.path.basename(src_db)
                    temp_db = os.path.join(temp_dir, base_name)

                    # Remove stale sidecars so the temp copy always starts clean.
                    for _ext in ("-wal", "-shm"):
                        try:
                            if os.path.exists(temp_db + _ext):
                                os.remove(temp_db + _ext)
                        except Exception:
                            pass

                    try:
                        shutil.copy2(src_db, temp_db)
                    except Exception as copy_err:
                        logger.warning(f"DB sync: copy failed for {src_db} - {copy_err}")
                        continue
                    # Cache mtime now that the copy succeeded; historical files with
                    # unchanged mtime will be skipped on the next cycle.
                    if _cur_mtime is not None:
                        _synced_mtimes[src_db] = _cur_mtime

                    # Best-effort WAL copy: the WAL file holds un-checkpointed rows
                    # (often 1-3 hours of live data). The -shm is always byte-range
                    # locked on Windows so we skip it — SQLite creates its own when
                    # opening the temp copy. If the WAL copy fails we fall back to
                    # main-db-only (immutable=1); if it succeeds we use mode=ro so
                    # SQLite replays it automatically.
                    _wal_copied = False
                    try:
                        shutil.copy2(src_db + "-wal", temp_db + "-wal")
                        _wal_copied = True
                    except Exception:
                        pass
                    _open_uri = f"file:{temp_db}?mode=ro" if _wal_copied else f"file:{temp_db}?immutable=1"

                    src_conn = _sqlite3.connect(_open_uri, uri=True, timeout=10)
                    tables = [t[0] for t in src_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()]
                    before = dest_conn.total_changes
                    skipped = []
                    for tbl in tables:
                        # Merge each table independently and commit per table, so a
                        # corrupt table in the source ("database disk image is
                        # malformed") only skips that table instead of aborting the
                        # whole snapshot — the readable contract tables still import.
                        try:
                            ddl = src_conn.execute(
                                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                            ).fetchone()
                            if ddl and ddl[0]:
                                dest_conn.execute(ddl[0].replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
                                dest_conn.execute(
                                    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{tbl}_ts ON {tbl}(timestamp)"
                                )
                            rows = src_conn.execute(
                                f"SELECT timestamp, open, high, low, close, volume FROM {tbl}"
                            ).fetchall()
                            dest_conn.executemany(
                                f"INSERT OR IGNORE INTO {tbl} (timestamp, open, high, low, close, volume) VALUES (?,?,?,?,?,?)",
                                rows,
                            )
                            dest_conn.commit()  # persist this table; release the lock
                        except Exception as te:
                            try:
                                dest_conn.rollback()
                            except Exception:
                                pass
                            skipped.append(tbl)
                    if skipped:
                        logger.warning(
                            f"DB sync: {os.path.basename(src_db)} — skipped {len(skipped)} unreadable table(s): {', '.join(skipped[:8])}"
                            + (" ..." if len(skipped) > 8 else "")
                        )
                    total_inserted += max(0, dest_conn.total_changes - before)
                except Exception as e:
                    logger.error(f"DB sync: failed merging {src_db}: {e}")
                    try:
                        dest_conn.rollback()
                    except Exception:
                        pass
                finally:
                    if src_conn is not None:
                        src_conn.close()
                    if temp_db:
                        for ext in ["", "-wal", "-shm"]:
                            try:
                                if os.path.exists(temp_db + ext):
                                    os.remove(temp_db + ext)
                            except Exception:
                                pass
            # Freshness readout — the latest WTI/Brent 15-min bar now in the local DB.
            for _pfx, _name in (("CL", "WTI"), ("CO", "Brent")):
                try:
                    _tabs = [r[0] for r in dest_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (_pfx + "_%",)
                    ).fetchall()]
                    latest[_name] = max(
                        (dest_conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()[0] or "" for t in _tabs),
                        default="",
                    )
                except Exception:
                    pass
        finally:
            dest_conn.close()
        logger.info(
            f"DB sync: {len(candidates)} snapshot(s), +{total_inserted} new row(s); "
            f"latest WTI={latest.get('WTI') or '?'} Brent={latest.get('Brent') or '?'}"
        )

    async def _trigger_db_sync():
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _run_db_sync_blocking)

    async def _trigger_gdelt_scrape():
        from services.gdelt_fetcher import scrape_one_cycle
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, scrape_one_cycle)

    # Initialize APScheduler for precision background cron tasks
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_trigger_db_sync, "interval", minutes=1, id="db_sync_pipeline", next_run_time=datetime.now())
    # GDELT: every 2 min; staggered 30 s after startup so it doesn't race the
    # db-sync on boot. Each cycle: ~15 s of requests (10 queries × 1.5 s) plus
    # the backward-pass window advancing one day further into history.
    scheduler.add_job(
        _trigger_gdelt_scrape, "interval", minutes=2, id="gdelt_scrape",
        next_run_time=datetime.now() + timedelta(seconds=30),
    )

    async def _trigger_impact_maintenance():
        """Daily: fill null T+1/T+5/T+20 for maturing auto-appended events."""
        from services.event_impact_db import run_maintenance
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, run_maintenance)

    async def _trigger_impact_backfill():
        """One-shot at startup: seed event_impact from the catalog + ACLED episodes."""
        from services.event_impact_db import backfill_catalog, load_unexplained_moves, init_db
        loop = asyncio.get_running_loop()
        def _run():
            init_db()
            backfill_catalog(force=False)
            load_unexplained_moves()
            # Deepen the analog pool with distinct ACLED escalation episodes
            # (no-op until the ACLED DB has data; idempotent thereafter).
            try:
                from services.acled_impact_sourcing import backfill_acled_to_impact
                backfill_acled_to_impact(dry_run=False)
            except Exception as _ae:
                logger.debug("ACLED impact sourcing skipped: %s", _ae)
        await loop.run_in_executor(None, _run)

    async def _trigger_acled_scrape():
        """Every 15 min: advance ACLED scraper one country forward + backward."""
        from services.acled_fetcher import scrape_one_cycle
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, scrape_one_cycle)

    async def _trigger_silent_classify():
        """
        Every 30 min: drain unclassified GDELT articles → classify (keyword path,
        no LLM) → auto-append qualifying events to event_impact DB.

        Uses keyword-only classification to keep cost/latency low at scale.
        LLM classification remains available only on the user-facing /api/disruption/news.
        """
        from services.gdelt_fetcher import (
            get_unclassified_articles, mark_classified, cluster_articles,
        )
        from services.event_impact_db import auto_append_from_classifier
        import hashlib

        def _run_classify_batch():
            raw = get_unclassified_articles(limit=300)
            if not raw:
                return 0, 0

            # Cluster to deduplicate same-event coverage before classifying
            clusters = cluster_articles(raw, similarity_threshold=0.30, time_window_hours=48.0)

            # Keyword-only classifier (import _build_keyword_result internals via classify)
            from services.disruption_classifier import classify_feed_item, _lower, _build_keyword_result
            from services.eia_event_engine import get_full_impact_matrix
            matrix = get_full_impact_matrix()

            appended = 0
            processed_urls = [a["url"] for a in raw]

            for item in clusters:
                try:
                    text_lower = _lower(item.get("title", "") + " " + item.get("domain", ""))
                    cls = _build_keyword_result(text_lower, matrix)
                except Exception:
                    continue

                node_id  = cls.get("node_id")
                severity = cls.get("severity", "scare")
                if node_id and severity in ("outage", "sustained"):
                    raw_id = (item.get("url") or item.get("title", ""))[:200]
                    eid    = "live_" + hashlib.sha1(raw_id.encode()).hexdigest()[:12]
                    try:
                        inserted = auto_append_from_classifier(
                            event_id      = eid,
                            headline      = item.get("title", ""),
                            classification = cls,
                            url           = item.get("url", ""),
                            source_domain = item.get("domain", ""),
                            n_sources     = item.get("n_sources", 1),
                            source_scale  = "national",
                        )
                        if inserted:
                            appended += 1
                    except Exception:
                        pass

            mark_classified(processed_urls)
            return len(raw), appended

        loop = asyncio.get_running_loop()
        try:
            n_raw, n_appended = await loop.run_in_executor(None, _run_classify_batch)
            if n_raw:
                logger.info(
                    "Silent classify: processed %d articles → %d events appended to impact DB",
                    n_raw, n_appended,
                )
        except Exception as e:
            logger.debug("Silent classify error: %s", e)

    # Run the catalog backfill 60 s after startup (after EIA price cache warms)
    scheduler.add_job(
        _trigger_impact_backfill, "date",
        run_date=datetime.now() + timedelta(seconds=60),
        id="impact_backfill_startup",
    )
    # Daily maintenance: fill maturing T+1/T+5/T+20 horizons
    scheduler.add_job(
        _trigger_impact_maintenance, "interval", hours=24,
        id="impact_maintenance",
        next_run_time=datetime.now() + timedelta(minutes=5),
    )
    # Silent classify-and-append: drains unclassified GDELT backlog every 30 min
    scheduler.add_job(
        _trigger_silent_classify, "interval", minutes=30,
        id="silent_classify",
        next_run_time=datetime.now() + timedelta(minutes=3),
    )
    # ACLED: one country per 15-min cycle, forward + 30-day backward pass
    # 24 countries × 15 min = full rotation every 6 hours; 5-year backfill per country
    scheduler.add_job(
        _trigger_acled_scrape, "interval", minutes=15,
        id="acled_scrape",
        next_run_time=datetime.now() + timedelta(minutes=7),
    )
    scheduler.start()
    app.state.scheduler = scheduler

    # start ported dsa trackers
    _background_tasks.append(asyncio.create_task(global_tankers.run(os.getenv("AISSTREAM_KEY", "") or os.getenv("AIS_API_KEY", ""))))
    
    async def _refresh_storms():
        while True:
            try:
                await global_storms.refresh()
            except Exception as e:
                logger.error(f"Error refreshing storms: {e}")
            await asyncio.sleep(300)
    _background_tasks.append(asyncio.create_task(_refresh_storms()))

    async def _refresh_cot():
        global global_cot
        while True:
            try:
                data = await fetch_cot()
                if data: global_cot = data
            except Exception as e:
                logger.error(f"Error refreshing COT: {e}")
            await asyncio.sleep(900)
    _background_tasks.append(asyncio.create_task(_refresh_cot()))

    async def _refresh_steo():
        global global_steo
        while True:
            try:
                data = await fetch_steo(os.getenv("EIA_API_KEY", ""))
                if data: global_steo = data
            except Exception as e:
                logger.error(f"Error refreshing STEO: {e}")
            await asyncio.sleep(1800)
    _background_tasks.append(asyncio.create_task(_refresh_steo()))


@app.on_event("shutdown")
async def _stop_background_publishers():
    for t in _background_tasks:
        t.cancel()
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# (Static mount moved to the bottom of the file)


# ==================== PRICE ENDPOINTS ====================
@app.get("/api/prices/all")
def get_all_prices():
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


# ==================== FORWARD CURVE ENDPOINT ====================
# NOTE: The canonical /api/analytics/forward-curve handler is `get_forward_curve_symbol`
# defined further below. A second handler that previously lived here used `await`
# inside a non-async `def` (a SyntaxError that prevented the whole module from
# importing) and returned a response shape the frontend does not consume. It has
# been removed; the route is served by get_forward_curve_symbol().


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


@app.get("/api/prices/{symbol}/intraday")
def get_intraday_prices_endpoint(symbol: str, limit: int = 390):
    """Recent intraday/spot session bars for a symbol. WTI/Brent come from the
    live 15-min candle DB; RBOB/HO/NG from yfinance 5-min; others fall back to the
    latest available session. Used by the Prices tab spot chart."""
    try:
        data = PriceFetcher.fetch_intraday(symbol, limit=limit)
        if not data:
            raise HTTPException(status_code=404, detail=f"No intraday data for {symbol}")
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching intraday prices for {symbol}: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/prices/{symbol}/historical")
def get_historical_prices(symbol: str, period: str = "1mo", resolution: str = "1d"):
    """Get historical prices for a symbol"""
    try:
        if resolution == "1min":
            from services.data_loader import get_intraday_prices
            data = get_intraday_prices(symbol)
        else:
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
def get_eia_data():
    """Get latest EIA weekly data"""
    try:
        if not os.getenv("EIA_API_KEY"):
            # Provide mock data if key is missing
            mock_data = {
                "crude_level": {"current_value": 430.0, "wow_change": -1.2},
                "cushing_level": {"current_value": 28.0, "wow_change": -0.3},
                "refinery_utilization": {"current_value": 92.5, "wow_change": 0.4},
                "us_crude_production": {"current_value": 13.2, "wow_change": 0.1},
                "gasoline_level": {"current_value": 220.0, "wow_change": 0.5},
                "distillate_level": {"current_value": 115.0, "wow_change": -0.3},
            }
            return {"status": "success", "data": mock_data, "timestamp": datetime.now().isoformat(), "mocked": True}

        eia_data = EIAFetcher.fetch_all_eia_data()
        return {"status": "success", "data": eia_data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching EIA data: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/eia/weekly-anchor')
def get_eia_weekly_anchor():
    """Get weekly EIA anchor data relative to 5-year averages."""
    try:
        if not os.getenv("EIA_API_KEY"):
            mock_anchor = {
                "crude_level": {
                    "current_value": 430000,
                    "wow_change": -1200,
                    "five_year_avg": 425000,
                    "deviation_from_5yr_pct": 1.17
                }
            }
            return {"status": "success", "data": mock_anchor, "timestamp": datetime.now().isoformat(), "mocked": True}

        current_data = EIAFetcher.fetch_all_eia_data()
        anchor_data = {}

        # Fetch 5yr averages concurrently
        averages = {}
        with ThreadPoolExecutor(max_workers=min(3, len(EIAFetcher.SERIES))) as executor:
            future_to_name = {
                executor.submit(EIAFetcher.calculate_5yr_avg, series_id): name
                for name, series_id in EIAFetcher.SERIES.items()
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    averages[name] = future.result()
                except Exception as e:
                    logger.error(f"Error calculating 5yr average for {name}: {e}")
                    averages[name] = None

        for name, series_id in EIAFetcher.SERIES.items():
            current = current_data.get(name, {})
            avg_5yr = averages.get(name)
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


@app.get("/api/eia/history")
def get_eia_history(series: str = "crude"):
    """Weekly inventory history + 5-year seasonal band for one EIA series.

    Served from the local seeded `inventory` table (Data/eia_*_US.csv), so it
    needs no API key and covers 2020→present. `series` is one of:
    crude, cushing, gasoline, distillate, jet, propane, residual, total,
    refinery_inputs.
    """
    try:
        data = EIAFetcher.inventory_history(series)
        if not data:
            return JSONResponse(status_code=404, content={
                "status": "error",
                "message": f"no seeded history for series '{series}'",
                "available": list(EIAFetcher.HISTORY_SERIES.keys()),
            })
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching EIA history: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/macro/history")
def get_macro_history(indicator: str = "DXY", days: int = 750):
    """Daily macro history (DXY / TNX / VIX / GOLD) from the seeded
    macro_indicators table (Data/macro_daily). For overlaying vs oil."""
    try:
        data = MacroFetcher.indicator_history(indicator.upper(), days=days)
        if not data:
            return JSONResponse(status_code=404, content={
                "status": "error",
                "message": f"no seeded history for indicator '{indicator}'",
                "available": ["DXY", "TNX", "VIX", "GOLD"],
            })
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching macro history: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== RIG COUNT ENDPOINTS ====================
@app.get("/api/rigs/latest")
def get_latest_rig_count():
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
def get_latest_cftc():
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
# ==================== MACRO ENDPOINTS ====================
@app.get("/api/macro/all")
def get_all_macro():
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
# Short-lived cache for the composite endpoint. It is expensive (history +
# multi-factor for 17 symbols) and its inputs only move on the ~60s signal
# cadence, so caching the response for a few seconds makes dashboard reloads and
# polls instant without serving anything staler than the WebSocket already does.
_COMPOSITE_CACHE: dict = {"ts": 0.0, "resp": None}
_COMPOSITE_TTL = 30.0  # seconds


@app.get("/api/signals/composite")
def get_composite_signal():
    """Get composite trading signal — uses multi-factor engine for WTI."""
    import time as _time
    now_ts = _time.time()
    cached_resp = _COMPOSITE_CACHE.get("resp")
    if cached_resp is not None and (now_ts - _COMPOSITE_CACHE.get("ts", 0.0)) < _COMPOSITE_TTL:
        return cached_resp
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_prices = executor.submit(PriceFetcher.fetch_all_prices)
            future_news   = executor.submit(NewsFetcher.fetch_all_news)
            future_macro  = executor.submit(MacroFetcher.fetch_all_macro)
            prices = future_prices.result()
            news   = future_news.result()
            macro  = future_macro.result()

        wti_hist = PriceFetcher.fetch_historical("WTI", "3mo")
        if not wti_hist:
            logger.error("WTI historical data not available.")
            return JSONResponse(status_code=503, content={"status": "error", "message": "WTI historical data not available"})

        wti_prices = [float(h["close"]) for h in wti_hist]

        # ── Fetch real factor inputs ─────────────────────────────────────────
        # EIA: use weekly anchor data to derive inventory surprise
        eia_anchor = None
        try:
            if os.getenv("EIA_API_KEY"):
                eia_raw = EIAFetcher.fetch_all_eia_data()
                # Build anchor-style dict for multi-factor engine
                crude = eia_raw.get("crude_level", {})
                eia_anchor = {
                    "crude_inventory": {
                        "current_value": crude.get("current_value"),
                        "wow_change":    crude.get("wow_change"),
                        "five_year_avg": None,  # calculated separately
                    }
                }
        except Exception as eia_err:
            logger.warning(f"EIA data fetch error in composite: {eia_err}")

        # Seasonality: use the deviation_sigma from the seasonality endpoint as a factor
        try:
            from seasonality import fetch_seasonality
            seas_data = fetch_seasonality()
            # deviation_sigma: positive = above seasonal norm = bearish (more supply)
            seas_score = -seas_data.get("deviation_sigma", 0.0) / 3.0  # ±3 sigma → ±1
        except Exception:
            seas_score = 0.0

        # CFTC: use real data if live (currently placeholder returning None)
        cftc_data = None
        try:
            cftc_raw = CFTCFetcher.fetch_latest()
            # Only use if non-None values present
            wti_cftc = cftc_raw.get("WTI", {}) if cftc_raw else {}
            if wti_cftc.get("mm_net_long") is not None:
                cftc_data = cftc_raw
        except Exception:
            pass

        # ── Multi-factor composite ───────────────────────────────────────────
        news_sentiment = NewsFetcher.calculate_sentiment_trend(news)
        mf_result = compute_multi_factor_score(
            symbol="WTI",
            candles=wti_hist,
            macro=macro,
            eia_data=eia_anchor,
            cftc_data=cftc_data,
        )

        # Inject news sentiment into sub_scores
        sub = mf_result.get("sub_scores", {})
        sub["news_sentiment"] = round(news_sentiment, 3)
        # Recalculate composite adding news (15% weight)
        news_contribution = news_sentiment * 0.15
        adjusted_score = round(mf_result["composite_score"] * 0.85 + news_contribution * 100, 1)

        # Classic technical indicators for display
        vol = SignalCalculator.calculate_realized_volatility(wti_prices)
        vol_regime = SignalCalculator.get_vol_regime(vol)
        ema20 = SignalCalculator.calculate_ema(wti_prices, 20)
        ema50 = SignalCalculator.calculate_ema(wti_prices, 50)
        boll  = SignalCalculator.calculate_bollinger_bands(wti_prices, period=20, sigma=2.0) if len(wti_prices) >= 20 else {}
        atr   = SignalCalculator.calculate_atr(wti_hist, 14)
        rsi   = SignalCalculator.calculate_rsi(wti_prices, 14)
        macd  = SignalCalculator.calculate_macd(wti_prices)
        roc   = SignalCalculator.calculate_momentum_roc(wti_prices, 14)
        zscore = SignalCalculator.calculate_price_zscore(wti_prices, 20)

        import numpy as np
        from legacy_archive.prediction.features.technical_features import _williams_r, _cci, _stochastic
        prices_arr = np.array(wti_prices)
        highs_arr = np.array([float(h["high"]) for h in wti_hist])
        lows_arr = np.array([float(h["low"]) for h in wti_hist])
        will_r = _williams_r(highs_arr, lows_arr, prices_arr)
        cci = _cci(highs_arr, lows_arr, prices_arr)
        stoch = _stochastic(highs_arr, lows_arr, prices_arr)

        wti_ai = _latest_intraday.get("WTI", {})
        
        by_symbol = {}
        all_target_symbols = [
            "WTI", "Brent", "RBOB", "HO", 
            "3-2-1CRACK", "GASCRACK", "DIESELCRACK", 
            "WTI_DFLY", "BRENT_DFLY", "RBOB_DFLY", "HO_DFLY", 
            "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY", 
            "WTI-Brent", "DUB-WTI"
        ]
        
        # WTI uses the multi-factor result already computed above (with the news
        # adjustment), so build it inline.
        by_symbol["WTI"] = {
            "composite_score": adjusted_score,
            "regime": wti_ai.get("regime_state", {}).get("regime_label", "BULLISH" if adjusted_score > 30 else "BEARISH" if adjusted_score < -30 else "NEUTRAL"),
            "regime_type": wti_ai.get("regime_state", {}).get("severity", mf_result.get("regime_type", "UNKNOWN")),
            "signal": wti_ai.get("trade_signal", {}).get("direction", mf_result.get("signal", "NEUTRAL")),
            "sub_scores": sub,
            "weights": mf_result.get("factor_weights", {}),
            "volatility_pct": round(vol, 1),
            "vol_regime": vol_regime,
            "factor_scores": mf_result.get("factor_scores", {}),
        }

        # The other 16 symbols are independent (each = one history fetch + one
        # multi-factor computation). This loop was the bulk of the endpoint's ~18s
        # latency when run sequentially; fan it out across a threadpool so the wall
        # time collapses to roughly the slowest single symbol. Each worker is
        # self-contained and swallows its own errors so one bad symbol cannot 500
        # the whole endpoint.
        def _compute_symbol(sym):
            try:
                hist = PriceFetcher.fetch_historical(sym, "3mo")
                prices_list = [float(h["close"]) for h in (hist or [])] if hist else []
                sym_mf = compute_multi_factor_score(
                    symbol=sym, candles=hist or [], macro=macro, eia_data=None, cftc_data=None,
                ) if hist else {}
                sym_vol = SignalCalculator.calculate_realized_volatility(prices_list) if prices_list else 0.0
                sym_vol_regime = SignalCalculator.get_vol_regime(sym_vol) if prices_list else "NORMAL"
                sym_sub = sym_mf.get("sub_scores", {})
                sym_sub["news_sentiment"] = round(news_sentiment, 3)
                sym_ai = _latest_intraday.get(sym, {})
                return sym, {
                    "composite_score": sym_mf.get("composite_score", 0.0),
                    "regime": sym_ai.get("regime_state", {}).get("regime_label", sym_mf.get("regime", "NEUTRAL")),
                    "regime_type": sym_ai.get("regime_state", {}).get("severity", sym_mf.get("regime_type", "UNKNOWN")),
                    "signal": sym_ai.get("trade_signal", {}).get("direction", sym_mf.get("signal", "NEUTRAL")),
                    "sub_scores": sym_sub,
                    "weights": sym_mf.get("factor_weights", {}),
                    "volatility_pct": round(sym_vol, 1),
                    "vol_regime": sym_vol_regime,
                    "factor_scores": sym_mf.get("factor_scores", {}),
                }
            except Exception as sym_err:
                logger.warning(f"composite: failed to compute {sym}: {sym_err}")
                return sym, {}

        other_symbols = [s for s in all_target_symbols if s != "WTI"]
        with ThreadPoolExecutor(max_workers=min(8, len(other_symbols))) as executor:
            for sym, data in executor.map(_compute_symbol, other_symbols):
                by_symbol[sym] = data
        
        result = {
            "status": "success",
            "data": {
                "composite_score":  adjusted_score,
                "regime":           wti_ai.get("regime_state", {}).get("regime_label", "BULLISH" if adjusted_score > 30 else "BEARISH" if adjusted_score < -30 else "NEUTRAL"),
                "regime_type":      wti_ai.get("regime_state", {}).get("severity", mf_result.get("regime_type", "UNKNOWN")),
                "signal":           mf_result.get("signal", "NEUTRAL"),
                "confidence":       mf_result.get("confidence", 0.0),
                "sub_scores":       sub,
                "factor_scores":    mf_result.get("factor_scores", {}),
                "weights":          mf_result.get("factor_weights", {}),
                # Technical indicators
                "volatility_pct":   round(vol, 1),
                "vol_regime":       vol_regime,
                "annual_vol_pct":   mf_result.get("annual_vol_pct"),
                "adx":              mf_result.get("adx"),
                "ema_20":           round(ema20, 4) if ema20 is not None else None,
                "ema_50":           round(ema50, 4) if ema50 is not None else None,
                "ema_trend":        "BULLISH" if ema20 and ema50 and ema20 > ema50 else "BEARISH" if ema20 and ema50 and ema20 < ema50 else "NEUTRAL",
                "bollinger_position": boll.get("position"),
                "bollinger_width":  boll.get("width"),
                "atr_14":           round(atr[-1], 4) if atr else None,
                "rsi_14":           rsi,
                "macd":             macd,
                "roc_14":           roc,
                "price_zscore_20d": zscore,
                "williams_r":       will_r,
                "cci":              cci,
                "stochastic_k":     stoch.get("k") if isinstance(stoch, dict) else None,
                "stochastic_d":     stoch.get("d") if isinstance(stoch, dict) else None,
                "bb_zscore":        wti_ai.get("trade_signal", {}).get("bb_zscore"),
                "ect_zscore":       wti_ai.get("trade_signal", {}).get("ect_zscore"),
                "exit_signal":      wti_ai.get("trade_signal", {}).get("exit_signal"),
                "seas_factor":      round(seas_score, 4),
                "timestamp":        datetime.now().isoformat(),
                "data_quality":     "multi_factor_live",
                "by_symbol":        by_symbol,
            },
        }
        _COMPOSITE_CACHE["resp"] = result
        _COMPOSITE_CACHE["ts"] = now_ts
        return result
    except Exception as e:
        logger.error(f"Error calculating composite signal: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get('/api/signals/enhanced')
def get_enhanced_signals():
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

            import numpy as np
            from legacy_archive.prediction.features.technical_features import _williams_r, _cci, _stochastic
            prices_arr = np.array(closes)
            highs_arr = np.array([float(h["high"]) for h in hist])
            lows_arr = np.array([float(h["low"]) for h in hist])
            will_r = _williams_r(highs_arr, lows_arr, prices_arr)
            cci_val = _cci(highs_arr, lows_arr, prices_arr)
            stoch = _stochastic(highs_arr, lows_arr, prices_arr)

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
                "williams_r": will_r,
                "cci": cci_val,
                "stochastic_k": stoch.get("k") if isinstance(stoch, dict) else None,
                "stochastic_d": stoch.get("d") if isinstance(stoch, dict) else None,
                "ai_bb_zscore": _latest_intraday.get(symbol, {}).get("trade_signal", {}).get("bb_zscore"),
                "ai_ect_zscore": _latest_intraday.get(symbol, {}).get("trade_signal", {}).get("ect_zscore"),
                "ai_exit_signal": _latest_intraday.get(symbol, {}).get("trade_signal", {}).get("exit_signal"),
                "breakout": breakout,
                "signal_label": signal_label,
                "volatility_pct": SignalCalculator.calculate_realized_volatility(closes) if closes else 0.0,
            })

        wti_price = prices.get("WTI", {}).get("close")
        brent_price = prices.get("Brent", {}).get("close")
        
        # Curve structure + M1-M12 spread from the canonical forward-curve service.
        # Standardized on the M1-M6 roll-yield regime — the same label the header pills
        # and the Term Structure panel show (no more synthetic/hardcoded spread).
        try:
            from services.forward_curve import fetch_forward_curve
            _, _wti_meta = fetch_forward_curve("WTI")
            m1_m12_spread = _wti_meta.get("m1_m12_spread")
            curve_label = _wti_meta.get("structure", "UNKNOWN")
        except Exception:
            m1_m12_spread = None
            curve_label = "UNKNOWN"

        cracks = SignalCalculator.calculate_crack_spreads(
            rbob=float(prices.get("RBOB", {}).get("close", 0)),
            ulsd=float(prices.get("HO", {}).get("close", 0)),
            wti=float(prices.get("WTI", {}).get("close", 0)),
            brent=float(prices.get("Brent", {}).get("close", 0)),
            go_per_mt=float(prices.get("GO", {}).get("close", 0)) if prices.get("GO") else None,
        )

        market_state = {
            "curve": curve_label,
            "m1_m12_spread": m1_m12_spread,
            "inventory_wow": eia_data.get("crude_level", {}).get("wow_change") if eia_data else 0.0,
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
def get_forward_curve_symbol(symbol: str = "WTI"):
    """Get forward curve — uses real M1-M12 data from Yahoo Finance."""
    try:
        from services.forward_curve import fetch_forward_curve
        curve_points, meta = fetch_forward_curve(symbol)
        
        if not curve_points:
            # Fallback if Yahoo Finance fetch fails
            logger.info(f"forward-curve: YF fetch failed for {symbol}, returning empty curve")
            return {
                "status": "success",
                "data": {
                    "forward_curve":  [],
                    "m1_m12_spread": 0.0,
                    "curve_shape":   "UNKNOWN",
                    "data_source":   "error",
                    "timestamp":     datetime.now().isoformat(),
                },
            }

        # Format for frontend
        curve = [
            {
                "month": p["month"],
                "price": p["price"],
                "spread": round(p["price"] - curve_points[0]["price"], 2)
            }
            for p in curve_points
        ]

        return {
            "status": "success",
            "data": {
                "forward_curve":  curve,
                "m1_m12_spread": meta.get("m1_m12_spread", 0.0),
                "curve_shape":   meta.get("structure", "UNKNOWN"),
                "data_source":   "yfinance",
                "timestamp":     datetime.now().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Error generating forward curve: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


@app.get("/api/analytics/correlations")
def get_correlation_matrix():
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
            },
        }
    except Exception as e:
        logger.error(f"Error calculating correlations: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ==================== SPREAD ANALYSIS ENDPOINTS ====================
# ==================== ALERTS ENDPOINTS ====================
# ==================== ENHANCED NEWS ENDPOINTS ====================
@app.get("/api/news/enhanced")
def get_enhanced_news():
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
        data = global_storms.snapshot()
        if not data:
            data = [
                {
                    "id": "mock_storm_1",
                    "name": "Hurricane Test",
                    "category": 3,
                    "lat": 25.5,
                    "lon": -90.1,
                    "wind_mph": 120,
                    "status": "Active (Mock)"
                }
            ]
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error in storms endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/tankers/positions')
async def api_get_tanker_positions():
    """Return AIS tanker zone snapshots or offline status if key missing."""
    try:
        data = global_tankers.snapshot()
        if not data:
            data = {
                "Gulf Coast (PADD 3)": {"vessels": 45, "status": "Mocked Data"},
                "Houston Ship Channel": {"vessels": 12, "status": "Mocked Data"},
                "Louisiana Offshore (LOOP)": {"vessels": 5, "status": "Mocked Data"}
            }
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error in tankers endpoint: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== SPREADS ENDPOINTS ====================
# ==================== CRACK SPREADS ENDPOINTS ====================
# ==================== PREDICTION ENGINE ENDPOINTS ====================
@app.get('/api/prediction/regime')
async def get_current_regime(symbol: str = 'WTI'):
    """Get the current classified regime state."""
    try:
        from main import _latest_intraday
        if symbol in _latest_intraday and "regime_state" in _latest_intraday[symbol]:
            rs = _latest_intraday[symbol]["regime_state"]
            
            # Map string severity to float if necessary
            sev_val = rs.get("severity", 0.5)
            if isinstance(sev_val, str):
                if "EXTREME" in sev_val:
                    sev_val = 0.9
                elif "STRONG" in sev_val:
                    sev_val = 0.7
                else:
                    sev_val = 0.5
                    
            return {"status": "success", "data": {
                "regime_label": rs.get("regime_label", "NEUTRAL"),
                "severity": sev_val,
                "regime_age_days": rs.get("regime_age_days", 5),
                "hmm_prob_extreme_backwardation": rs.get("hmm_probabilities", {}).get("EXTREME_BACKWARDATION", None),
                "hmm_prob_backwardation": rs.get("hmm_probabilities", {}).get("BACKWARDATION", None),
                "hmm_prob_neutral": rs.get("hmm_probabilities", {}).get("NEUTRAL", None),
                "hmm_prob_contango": rs.get("hmm_probabilities", {}).get("CONTANGO", None),
                "hmm_prob_extreme_contango": rs.get("hmm_probabilities", {}).get("EXTREME_CONTANGO", None),
                "date": datetime.now().isoformat(),
            }}
        return {"status": "success", "data": None, "message": "No regime data found in memory"}
    except Exception as e:
        logger.error(f"Error fetching regime: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/prediction/forecast')
async def get_daily_forecast(symbol: str = 'WTI'):
    """Get the latest model forecast and trade recommendation."""
    try:
        from main import _latest_intraday
        if symbol in _latest_intraday:
            data = _latest_intraday[symbol]
            tsig = data.get("trade_signal", {})
            direction = tsig.get("direction", "NEUTRAL")
            confidence = tsig.get("confidence", 0.5)
            trade_score = tsig.get("trade_score", 50.0)
            
            conviction = "LOW"
            if confidence > 0.8 or abs(trade_score - 50) > 30:
                conviction = "HIGH"
            elif confidence > 0.6 or abs(trade_score - 50) > 15:
                conviction = "MEDIUM"
                
            prediction_label = "NEUTRAL"
            if direction in ["LONG", "BUY_SPREAD", "BUY", "STRONG_BUY"]: prediction_label = "UP"
            elif direction in ["SHORT", "SELL_SPREAD", "SELL", "STRONG_SELL"]: prediction_label = "DOWN"
            
            factor_scores = tsig.get("factor_scores", {})
            shap_bullish = [{"feature": k, "contribution": v} for k, v in factor_scores.items() if v > 0]
            shap_bearish = [{"feature": k, "contribution": abs(v)} for k, v in factor_scores.items() if v < 0]
            
            shap_bullish.sort(key=lambda x: x["contribution"], reverse=True)
            shap_bearish.sort(key=lambda x: x["contribution"], reverse=True)
            # Calculate dynamic targets based on current price
            try:
                from services.price_fetcher import PriceFetcher
                hist = PriceFetcher.fetch_historical(symbol, "5d")
                current_price = float(hist[-1]["close"]) if hist else 70.0
            except:
                current_price = 70.0

            if prediction_label == "UP":
                target_price = current_price * 1.025
                stop_loss = current_price * 0.985
                entry_low = current_price * 0.995
                entry_high = current_price * 1.005
            elif prediction_label == "DOWN":
                target_price = current_price * 0.975
                stop_loss = current_price * 1.015
                entry_low = current_price * 0.995
                entry_high = current_price * 1.005
            else:
                target_price = current_price
                stop_loss = current_price
                entry_low = current_price
                entry_high = current_price
                
            return {
                "status": "success", 
                "data": {
                    "forecast": {
                        "date": datetime.now().isoformat(),
                        "prediction_label": prediction_label,
                        "confidence": confidence,
                        "horizon_days": 5,
                        "expected_return": 2.5 if prediction_label == "UP" else -2.5 if prediction_label == "DOWN" else 0.0,
                    },
                    "trade": {
                        "direction": direction,
                        "trade_type": "OUTRIGHT",
                        "conviction": conviction,
                        "trade_score": trade_score,
                        "target_price": target_price,
                        "stop_loss": stop_loss,
                        "entry_low": entry_low,
                        "entry_high": entry_high,
                        "position_size_lots": 10 if conviction == "HIGH" else 5,
                        "explanation": {
                            "action": direction,
                            "primary_drivers": ["Live Multi-Factor Composite"],
                            "risk_factors": ["Macro volatility", "Mean reversion failure"],
                            "rationale": f"Composite Score: {round((trade_score - 50) * 2, 1)}. Threshold for conviction is 15.",
                            "shap_bullish": shap_bullish,
                            "shap_bearish": shap_bearish
                        }
                    }
                }
            }
        return {"status": "success", "data": {"forecast": None, "trade": None}}
    except Exception as e:
        logger.error(f"Error fetching forecast: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get('/api/prediction/trades/all')
async def get_all_recent_trades():
    """Get the latest trade recommendation from the live Z-Score engine."""
    try:
        from main import _latest_intraday
        results = []
        for sym, data in _latest_intraday.items():
            tsig = data.get("trade_signal", {})
            regime = data.get("regime_state", {})
            
            # Reconstruct the TradeRecommendation schema for the UI
            direction = tsig.get("direction", "NO_TRADE")
            trade_score = tsig.get("trade_score", 50.0)
            z_score = (trade_score - 50) / 10.0
            
            rationale = f"Strict Z-Score Regime Bounds. Current Z-Score: {z_score:.2f} | Regime: {regime.get('regime_label', 'Neutral')}"
            if direction == "NO_TRADE" or direction == "NEUTRAL":
                direction = "NO_TRADE"
                rationale = "No trade recommended. Z-Score within bounds."
                
            results.append({
                "symbol": sym,
                "direction": direction,
                "confidence": tsig.get("confidence", 0.0),
                "trade_score": trade_score,
                "trade_type": "SPREAD" if "_" in sym or "-" in sym or "CRACK" in sym else "OUTRIGHT",
                "explanation": {
                    "action": direction,
                    "rationale": rationale
                }
            })
            
        results.sort(key=lambda x: abs(x.get("trade_score", 50) - 50), reverse=True)
        return {"status": "success", "data": results}
    except Exception as e:
        logger.error(f"Error fetching all trades: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== PAPER TRADING ENDPOINT ====================
@app.get('/api/paper/state')
def get_paper_state(recent: int = 0):
    """Return current paper trading book state.

    Args:
        recent: If > 0, only include the last N closed_trades in the response
                (stats like total_trades and win_rate still reflect ALL trades).
                Use recent=10 for lightweight overview polling.
    """
    try:
        state = paper_book.get_state()
        if recent > 0:
            state = {**state, "closed_trades": state["closed_trades"][-recent:]}
        return {"status": "success", "data": state, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching paper state: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/paper/positions')
def get_paper_positions():
    """Return the currently open paper-trading positions."""
    try:
        state = paper_book.get_state()
        return {
            "status": "success",
            "data": state.get("open_positions", []),
            "count": len(state.get("open_positions", [])),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching paper positions: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get('/api/paper/trades')
def get_paper_trades(limit: int = 200):
    """Return the closed paper-trading trade journal (most recent last)."""
    try:
        state = paper_book.get_state()
        trades = state.get("closed_trades", [])
        if limit and limit > 0:
            trades = trades[-limit:]
        return {
            "status": "success",
            "data": trades,
            "count": len(trades),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching paper trades: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post('/api/paper/close/{symbol}')
def close_paper_position(symbol: str):
    """Manually close a paper trading position."""
    try:
        import time
        paper_book.close_position_by_symbol(symbol, "Manual Close", time.time())
        return {"status": "success", "message": f"Closed position for {symbol}"}
    except Exception as e:
        logger.error(f"Error closing paper position for {symbol}: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post('/api/paper/trade')
def execute_manual_trade(payload: dict):
    """Manually execute a trade in the paper trading book."""
    try:
        symbol = payload.get("symbol")
        direction = payload.get("direction")
        if not symbol or not direction:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Missing symbol or direction"})

        # Get optional overrides
        units = payload.get("units")
        units = float(units) if units else None
        
        stop_loss = payload.get("stop_loss")
        stop_loss = float(stop_loss) if stop_loss else None
        
        take_profit = payload.get("take_profit")
        take_profit = float(take_profit) if take_profit else None

        # Get current price
        from services.price_fetcher import PriceFetcher
        price_data = PriceFetcher.fetch_symbol(symbol)
        if not price_data:
            return JSONResponse(status_code=400, content={"status": "error", "message": f"Could not fetch price for {symbol}"})
        
        current_price = price_data.get("close", 0.0)

        import time
        signal_val = 1.0 if direction == "LONG" else -1.0
        paper_book.open_position(
            symbol, direction, current_price, signal_val, time.time(),
            custom_units=units, custom_sl=stop_loss, custom_tp=take_profit,
            is_manual=True
        )
        paper_book.save_state()

        return {"status": "success", "message": f"Executed manual {direction} on {symbol} at {current_price}"}
    except Exception as e:
        logger.error(f"Error executing manual trade: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== MULTI-FACTOR SIGNALS ENDPOINT ====================
# ==================== COVMATRIX ENDPOINT ====================
# ==================== BACKTEST ENDPOINTS ====================
from pydantic import BaseModel

class BacktestRequest(BaseModel):
    symbol: str = "WTI"
    initial_capital: float = 1000000.0
    transaction_cost: float = 2.0
    slippage: float = 10.0
    horizon_days: int = 5

@app.get("/api/v1/risk/portfolio")
def get_portfolio_risk():
    """Portfolio risk for the paper book, measured in TICKS (no capital/equity).

    VaR / Expected Shortfall are computed from the empirical distribution of
    per-trade tick P&L rather than from an equity-return series.
    """
    try:
        from paper import paper_book
        import numpy as np

        state = paper_book.get_state()
        trade_pnls = [float(t.get("pnl", 0.0)) for t in state.get("closed_trades", [])]

        if len(trade_pnls) >= 2:
            arr = np.array(trade_pnls, dtype=float)
            var_95 = float(-np.percentile(arr, 5))    # 5th-percentile loss in ticks
            var_99 = float(-np.percentile(arr, 1))
            tail = arr[arr <= -var_95] if var_95 > 0 else arr[arr < 0]
            cvar_95 = float(-tail.mean()) if tail.size else 0.0
        else:
            var_95 = var_99 = cvar_95 = 0.0

        return {
            "status": "success",
            "data": {
                "total_pnl_ticks": state["total_pnl_ticks"],
                "realized_pnl_ticks": state["realized_pnl_ticks"],
                "unrealized_pnl_ticks": state["unrealized_pnl_ticks"],
                "win_rate": state["win_rate"],
                "max_drawdown_ticks": state["max_drawdown_ticks"],
                "open_count": state["open_count"],
                "max_concurrent": state["max_concurrent"],
                "open_positions": state["open_positions"],
                "var_95_ticks": round(var_95, 1),
                "var_99_ticks": round(var_99, 1),
                "expected_shortfall_95_ticks": round(cvar_95, 1),
            }
        }
    except Exception as e:
        logger.error(f"Error computing portfolio risk: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ==================== BACKTESTING ENDPOINTS ====================
@app.get("/api/backtest/strategies")
async def get_backtest_strategies():
    """List all available backtesting strategies."""
    try:
        from backtesting.strategies import STRATEGIES
        strategies = {k: v.to_dict() for k, v in STRATEGIES.items()}
        return {"status": "success", "data": strategies, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/backtest/run")
async def run_backtest_endpoint(payload: dict):
    """Run a backtest with configurable parameters."""
    try:
        from backtesting.engine import run_backtest as _run_bt
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: _run_bt(
            strategies=payload.get("strategies", ["zscore_mean_reversion"]),
            combination_mode=payload.get("combination_mode", "independent"),
            instruments=payload.get("instruments"),
            products=payload.get("products", ["CL", "CO"]),
            initial_capital=float(payload.get("initial_capital", 1_000_000.0)),
            lots_per_trade=int(payload.get("lots_per_trade", 1)),
            slippage_ticks=payload.get("slippage_ticks", 1),
            db_dir=payload.get("db_dir", os.path.join(os.path.dirname(__file__), "..", "DB")),
            strategy_params=payload.get("strategy_params"),
            include_spreads=payload.get("include_spreads", True),
            include_flies=payload.get("include_flies", True),
            include_dflies=payload.get("include_dflies", False),
            include_outrights=payload.get("include_outrights", False),
        ))
        return {"status": "success", "data": results, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error running backtest: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/backtest/journal")
def get_backtest_journal(
    backtest_id: str = None,
    instrument: str = None,
    strategy: str = None,
    limit: int = 500,
):
    """Fetch trade journal entries with optional filters."""
    try:
        from backtesting.trade_journal import TradeJournal
        journal = TradeJournal()
        trades = journal.get_trades(backtest_id=backtest_id, instrument=instrument, strategy=strategy, limit=limit)
        return {"status": "success", "data": trades, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error fetching journal: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== HEALTH CHECK ====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)



@app.get('/api/analytics/structure')
def get_market_structure(symbol: str = 'WTI'):
    try:
        from services.curve_analytics import get_market_structure_analytics
        data = get_market_structure_analytics(symbol)
        return {'status': 'success', 'data': data}
    except Exception as e:
        return JSONResponse(status_code=500, content={'status': 'error', 'message': str(e)})

@app.get('/api/analytics/curve-structure')
def get_curve_structure(symbol: str = 'WTI', legs: str = '1,2'):
    """Custom calendar spread (2 legs) or butterfly (3 legs) for curve analysis.
    `legs` is a comma list of month indices, e.g. legs=2,5 or legs=2,4,6.
    Returns the live value plus historical z-score / percentile / series."""
    try:
        from services.curve_analytics import get_custom_structure
        leg_list = [int(x) for x in legs.split(',') if x.strip()]
        data = get_custom_structure(symbol, leg_list)
        return {'status': 'success', 'data': data}
    except ValueError as ve:
        return JSONResponse(status_code=400, content={'status': 'error', 'message': str(ve)})
    except Exception as e:
        logger.error(f"curve-structure error: {e}")
        return JSONResponse(status_code=500, content={'status': 'error', 'message': str(e)})


@app.get('/api/analytics/indicators')
def get_indicators(symbol: str = 'WTI', period: str = '3mo', ema_periods: str = '20,50', atr_period: int = 14):
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
            ema_list[f'ema_{p}'] = [round(x, 4) if x is not None else None for x in series]

        atr_series = SignalCalculator.calculate_atr(hist, atr_period)
        # atr_series can also contain None values for the initial period padding
        atr_series = [round(x, 4) if x is not None else None for x in atr_series]

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

@app.get("/api/spreads/all")
def get_all_spreads():
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
def get_spread(spread_name: str):
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


@app.get("/api/alerts/active")
def get_active_alerts(db: Session = Depends(get_db)):
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

# ==================== DISRUPTION INTELLIGENCE ENDPOINTS ====================

@app.get("/api/disruption/matrix")
def get_disruption_matrix():
    """
    Full node × contract impact matrix, computed from EIA daily spot event studies.
    Returns all 15 nodes with history matrix, structural prior, confidence, and analog list.
    """
    try:
        from services.eia_event_engine import get_full_impact_matrix
        data = get_full_impact_matrix()
        return {"status": "success", "data": data, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Disruption matrix error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/nodes")
def get_disruption_nodes():
    """
    Summarised view of all 15 nodes: criticality, analog count, headline impact,
    confidence badge, region, and channel flags. Used to populate the node grid.
    """
    try:
        from services.eia_event_engine import get_full_impact_matrix
        from services.oil_nodes import NODE_DEFINITIONS
        matrix = get_full_impact_matrix()
        nodes_out = []
        for node in NODE_DEFINITIONS:
            nid   = node["id"]
            entry = matrix.get("nodes", {}).get(nid, {})
            headline = entry.get("headline", {})
            # headline may be a history matrix dict or a prior dict
            if isinstance(headline, dict) and "t0" in headline:
                t0 = headline.get("t0", {})
            else:
                t0 = headline
            nodes_out.append({
                "id":            nid,
                "name":          node["name"],
                "type":          node["type"],
                "throughput_mbd":node["throughput_mbd"],
                "criticality":   node["criticality"],
                "region":        node["region"],
                "channels":      node["channels"],
                "product_exposure": node["product_exposure"],
                "analog_count":  entry.get("analog_count", 0),
                "confidence":    entry.get("confidence", "STRUCTURAL"),
                "headline_source":entry.get("headline_source", "prior"),
                "wti_pct_t0":    t0.get("wti_pct"),
                "brent_pct_t0":  t0.get("brent_pct"),
                "arb_usd_t0":    t0.get("arb_usd"),
                "crack_usd_t0":  t0.get("crack_usd"),
                "notes":         node.get("notes", ""),
            })
        return {"status": "success", "data": nodes_out, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Disruption nodes error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/node/{node_id}")
def get_disruption_node_detail(node_id: str):
    """
    Full detail for one node: T+0..T+20 matrix split by channel, all analogues,
    structural prior, confidence metrics.
    """
    try:
        from services.eia_event_engine import get_full_impact_matrix
        from services.oil_nodes import NODE_BY_ID
        matrix = get_full_impact_matrix()
        node   = NODE_BY_ID.get(node_id)
        if not node:
            return JSONResponse(status_code=404, content={"status": "error", "message": "Unknown node"})
        entry  = matrix.get("nodes", {}).get(node_id, {})
        return {"status": "success", "data": {**node, **entry}, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Node detail error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/catalog")
def get_disruption_catalog():
    """
    Full ACLED-style event catalog: 20 real disruptions with node, channel,
    severity, source triangulation metadata, and computed T+0..T+20 returns.
    """
    try:
        from services.eia_event_engine import get_full_impact_matrix
        from services.event_catalog import DISRUPTION_EVENTS
        matrix = get_full_impact_matrix()
        all_returns = {r["event_id"]: r for r in matrix.get("all_event_returns", [])}
        enriched = []
        for ev in DISRUPTION_EVENTS:
            ret = all_returns.get(ev["event_id"], {})
            enriched.append({**ev, "computed": {k: v for k, v in ret.items() if k.startswith("t")}})
        return {"status": "success", "data": enriched, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Catalog error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ── ACLED event → EventCluster converter (used by get_disruption_news) ───────

_ACLED_CONTRACT_MAP = {
    ("chokepoint",     "transport"):  ("brent_flat",       "Brent Flat"),
    ("production_hub", "production"): ("brent_flat",       "Brent Flat"),
    ("production_hub", "transport"):  ("brent_flat",       "Brent Flat"),
    ("refining_hub",   "production"): ("gasoline_crack",   "Gasoline Crack (RBOB-WTI)"),
    ("refining_hub",   "transport"):  ("distillate_crack", "Distillate Crack (HO-WTI)"),
}
_ACLED_WTI_NODES = {"permian", "usgc_padd3"}


def _acled_event_to_cluster(ev: dict) -> dict:
    """Convert a geo-matched ACLED event to the same shape as an enriched GDELT cluster."""
    from services.oil_nodes import NODE_BY_ID
    from services.eia_event_engine import compute_structural_prior

    node_id   = ev.get("matched_node_id", "")
    node      = NODE_BY_ID.get(node_id, {})
    node_type = node.get("type") or ev.get("matched_node_type") or "chokepoint"

    event_type_raw = ev.get("event_type") or ""
    event_lower    = event_type_raw.lower()
    fatalities     = int(ev.get("fatalities") or 0)
    if "battle" in event_lower or fatalities > 10:
        severity = "sustained"
    elif "explosion" in event_lower or "remote violence" in event_lower:
        severity = "outage"
    else:
        severity = "scare"

    channel = "transport" if node_type == "chokepoint" else "production"

    if node_id in _ACLED_WTI_NODES:
        most_exp, most_label = "wti_flat", "WTI Flat"
    else:
        most_exp, most_label = _ACLED_CONTRACT_MAP.get(
            (node_type, channel), ("brent_flat", "Brent Flat")
        )

    prior = compute_structural_prior(node, severity=severity, restored=False, channel=channel)

    dist    = int(ev.get("distance_km") or 0)
    fat_str = f" {fatalities} fatalities." if fatalities > 0 else ""
    why     = (
        f"{event_type_raw} {dist} km from "
        f"{ev.get('matched_node_name') or node.get('name') or node_id}.{fat_str}"
    )

    event_date = ev.get("event_date") or ""
    seendate   = event_date + "T00:00:00+00:00" if event_date and "T" not in event_date else event_date

    return {
        "url":             f"https://acleddata.com/acled/#{ev.get('event_id', '')}",
        "title":           f"[ACLED] {event_type_raw}: {ev.get('location', '')}, {ev.get('country', '')}",
        "domain":          "acleddata.com",
        "seendate":        seendate,
        "language":        "English",
        "sourcecountry":   ev.get("country", ""),
        "source":          "ACLED",
        "n_sources":       1,
        "domains":         ["acleddata.com"],
        "is_multi_source": False,
        "actor1":          ev.get("actor1", ""),
        "fatalities":      fatalities,
        "classification": {
            "node_id":               node_id,
            "node_name":             node.get("name") or ev.get("matched_node_name"),
            "node_type":             node_type,
            "channel":               channel,
            "region":                ev.get("country", ""),
            "severity":              severity,
            "restored":              False,
            "most_exposed_contract": most_exp,
            "most_exposed_label":    most_label,
            "confidence":            "STRUCTURAL",
            "source_tag":            "PRIOR",
            "reasoning":             (ev.get("notes") or "")[:200],
            "why_it_matters":        why,
            "impact": {
                "wti_pct":   prior.get("wti_pct"),
                "brent_pct": prior.get("brent_pct"),
                "arb_usd":   prior.get("arb_usd"),
                "crack_usd": prior.get("crack_usd"),
            },
            "structural_prior": prior,
            "analogs": [],
        },
    }


@app.get("/api/disruption/news")
def get_disruption_news(timespan: str = "3d", total: int = 50):
    """
    Oil-energy disruption feed. ACLED conflict events are the PRIMARY source
    (GDELT removed — its DOC API was unreliable and rolling-window only). EIA
    Today-in-Energy RSS is an oil-filtered supplement. Each item carries a
    classification (node/channel/severity/most-exposed contract/structural prior)
    and is expandable into a calibrated forecast on the front end.
    """
    try:
        from services.disruption_classifier import classify_feed_item

        # ── 1. ACLED — primary source ────────────────────────────────────────
        acled_events: list = []
        node_risks: dict   = {}
        acled_clusters: list = []
        try:
            from services.acled_fetcher import get_acled_events, get_node_risk_overlay
            acled_events = get_acled_events(days=30)
            node_risks   = get_node_risk_overlay(acled_events)
            for ev in acled_events[:60]:
                try:
                    acled_clusters.append(_acled_event_to_cluster(ev))
                except Exception as _ce:
                    logger.debug("ACLED cluster conversion failed: %s", _ce)

            # Dedup: one item per (node_id, date) — keep worst severity
            _SEV_RANK = {"sustained": 3, "outage": 2, "scare": 1}
            _acled_by_key: dict = {}
            for _c in acled_clusters:
                _cls = _c.get("classification") or {}
                _key = (_cls.get("node_id", ""), (_c.get("seendate") or "")[:10])
                _ex  = _acled_by_key.get(_key)
                if not _ex:
                    _acled_by_key[_key] = _c
                else:
                    _ex_sev  = _SEV_RANK.get((_ex.get("classification") or {}).get("severity", "scare"), 1)
                    _new_sev = _SEV_RANK.get(_cls.get("severity", "scare"), 1)
                    if _new_sev > _ex_sev or (
                        _new_sev == _ex_sev and _c.get("fatalities", 0) > _ex.get("fatalities", 0)
                    ):
                        _acled_by_key[_key] = _c
            acled_clusters = sorted(
                _acled_by_key.values(),
                key=lambda x: x.get("seendate", ""), reverse=True,
            )
        except Exception as e:
            logger.debug("ACLED fetch skipped: %s", e)

        feed_source = "acled_db" if acled_clusters else "empty"

        # ── 2. Live financial headlines (FinancialJuice / OilPrice / Reuters /
        #       Trump) — the GDELT replacement layer. Classify each so market-
        #       moving items (Iran, Hormuz, OPEC) land on a node + get a forecast.
        live_items: list = []
        headline_n = 0
        try:
            from services.headline_sources import fetch_headlines
            for item in fetch_headlines(max_per_source=12):
                cls = {}
                try:
                    cls = classify_feed_item(item)
                except Exception:
                    pass
                live_items.append({**item, "classification": cls or {}})
                headline_n += 1
        except Exception as _he:
            logger.debug("headline sources skipped: %s", _he)

        # ── 3. EIA RSS — oil-filtered supplement ─────────────────────────────
        eia_n = 0
        try:
            from services.eia_rss_fetcher import fetch_eia_rss
            for item in fetch_eia_rss(max_items=15):
                cls = {}
                try:
                    cls = classify_feed_item(item)
                except Exception:
                    pass
                live_items.append({**item, "classification": cls or {}})
                eia_n += 1
        except Exception:
            pass

        if acled_clusters and (headline_n or eia_n):
            feed_source = "acled_live"
        elif headline_n or eia_n:
            feed_source = "headlines"

        # Compose: NEWEST FIRST across everything. Live headlines (current) lead;
        # the mid-2025 ACLED data sinks to where its date falls. Reserve up to a
        # quarter of the slots for ACLED so the forecast-capable conflict cards
        # survive the slice, then sort the whole set newest-first for display.
        live_items.sort(key=lambda x: x.get("seendate", ""), reverse=True)
        reserve  = min(len(acled_clusters), max(0, total // 4))
        combined = list(acled_clusters[:reserve]) + live_items[:max(0, total - reserve)]
        combined.sort(key=lambda x: x.get("seendate", ""), reverse=True)
        enriched = combined[:total]

        # ── 3. Feed status metadata ──────────────────────────────────────────
        scrape_status = {}
        try:
            from services.acled_fetcher import get_scrape_status
            scrape_status = get_scrape_status()
        except Exception:
            pass

        source_labels = {
            "acled_db":   "ACLED conflict database",
            "acled_live": "ACLED + live headlines (FinancialJuice · OilPrice · Reuters · Trump)",
            "headlines":  "Live headlines (FinancialJuice · OilPrice · Reuters · Trump · EIA)",
            "eia_rss":    "EIA Today in Energy RSS",
            "empty":      "No feed available",
        }
        feed_status = {
            "source":        feed_source,
            "acled_count":   len(acled_clusters),
            "headline_count": headline_n,
            "acled_total":   scrape_status.get("total_articles", 0),
            "last_scrape":   scrape_status.get("latest_fetched"),
            "message":       f"{len(enriched)} items · {source_labels.get(feed_source, feed_source)}",
        }

        # ── 4. Per-node live signal — fold the CURRENT feed onto the 15 nodes ──
        # Each node gets: how many current items mention it, the latest headline,
        # the worst severity seen, and the expected move (mean of classified
        # impacts). This is what drives the "updated by news" node grid.
        _SEV_RANK = {"sustained": 3, "outage": 2, "scare": 1}
        node_signals: dict = {}
        for _item in enriched:
            _cls = _item.get("classification") or {}
            _nid = _cls.get("node_id")
            if not _nid:
                continue
            _sig = node_signals.setdefault(_nid, {
                "node_id": _nid, "news_count": 0, "latest_headline": None,
                "latest_date": "", "worst_severity": None, "most_exposed_label": None,
                "_wti": [], "_brent": [], "_crack": [],
            })
            _sig["news_count"] += 1
            _sd = _item.get("seendate") or ""
            if _sd > _sig["latest_date"]:
                _sig["latest_date"] = _sd
                _sig["latest_headline"] = (_item.get("title") or "")[:140]
                _sig["most_exposed_label"] = _cls.get("most_exposed_label")
            _sev = _cls.get("severity")
            if _sev and (_sig["worst_severity"] is None or
                         _SEV_RANK.get(_sev, 0) > _SEV_RANK.get(_sig["worst_severity"], 0)):
                _sig["worst_severity"] = _sev
            _imp = _cls.get("impact") or {}
            if _imp.get("wti_pct")   is not None: _sig["_wti"].append(_imp["wti_pct"])
            if _imp.get("brent_pct") is not None: _sig["_brent"].append(_imp["brent_pct"])
            if _imp.get("crack_usd") is not None: _sig["_crack"].append(_imp["crack_usd"])
        for _sig in node_signals.values():
            _sig["exp_wti_pct"]   = round(sum(_sig["_wti"]) / len(_sig["_wti"]), 2) if _sig["_wti"] else None
            _sig["exp_brent_pct"] = round(sum(_sig["_brent"]) / len(_sig["_brent"]), 2) if _sig["_brent"] else None
            _sig["exp_crack_usd"] = round(sum(_sig["_crack"]) / len(_sig["_crack"]), 2) if _sig["_crack"] else None
            for _k in ("_wti", "_brent", "_crack"):
                _sig.pop(_k, None)

        return {
            "status":       "success",
            "data":         enriched,
            "acled_events": acled_events[:50],
            "node_risks":   node_risks,
            "node_signals": node_signals,
            "feed_status":  feed_status,
            "count":        len(enriched),
            "timestamp":    datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Disruption news error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/status")
def get_disruption_status():
    """Scrape health + DB stats for the news feed monitor."""
    try:
        from services.gdelt_fetcher import get_scrape_status as gdelt_status
        from services.acled_fetcher import get_scrape_status as acled_status
        gdelt  = gdelt_status()
        acled  = acled_status()
        acled_avail = bool(
            __import__("os").getenv("ACLED_EMAIL") and __import__("os").getenv("ACLED_PASSWORD")
        )
        # GDELT classified/unclassified counts
        unclassified_count = 0
        try:
            import sqlite3 as _sq
            from services.gdelt_fetcher import GDELT_DB_PATH
            _c = _sq.connect(f"file:{GDELT_DB_PATH}?mode=ro", uri=True, timeout=3)
            unclassified_count = _c.execute(
                "SELECT COUNT(*) FROM articles WHERE classified_at IS NULL"
            ).fetchone()[0]
            _c.close()
        except Exception:
            pass
        impact_stats = {}
        try:
            from services.event_impact_db import get_db_stats
            impact_stats = get_db_stats()
        except Exception:
            pass
        return {
            "status":       "success",
            "gdelt":        gdelt,
            "acled":        {**acled, "available": acled_avail},
            "dataset": {
                "gdelt_total_scraped":  gdelt.get("total_articles", 0),
                "gdelt_unclassified":   unclassified_count,
                "gdelt_classified":     gdelt.get("total_articles", 0) - unclassified_count,
                "acled_total_events":   acled.get("total_events", 0),
                "acled_countries":      acled.get("countries", 0),
                "acled_oldest":         acled.get("oldest_event"),
                "impact_events":        impact_stats.get("total_events", 0),
                "fired_events":         impact_stats.get("fired", 0),
                "pending_outcomes":     impact_stats.get("pending_outcomes", 0),
                "unexplained_moves":    impact_stats.get("unexplained_moves", 0),
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/disruption/classify")
async def classify_disruption_text(payload: dict):
    """
    Classify a free-text headline or typed news item.
    Returns: node, channel, region, severity, restored, mostExposedContract,
    confidence, expected impact, historical analogs, structural prior.
    """
    try:
        from services.disruption_classifier import classify
        text = payload.get("text", "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"status": "error", "message": "text required"})
        result = await asyncio.get_event_loop().run_in_executor(None, classify, text)
        return {"status": "success", "data": result, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Classify error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ==================== EVENT IMPACT TABLE ENDPOINTS ====================

@app.get("/api/disruption/impact/events")
def get_impact_events(
    node_id: str = None,
    basin: str = None,
    only_fired: bool = False,
    include_null: bool = True,
    limit: int = 200,
):
    """
    All rows in the event_impact table, newest first.
    source_tag='history'  → EIA-measured returns exist.
    source_tag='prior'    → structural prior only; T cols may be null.
    magnitude_class='none' → event did not clear the surge/crash threshold
                             (these ARE the null-event negative class).
    """
    try:
        from services.event_impact_db import get_all_events
        data = get_all_events(
            node_id=node_id,
            basin=basin,
            only_fired=only_fired,
            include_null_events=include_null,
            limit=limit,
        )
        return {
            "status":    "success",
            "data":      data,
            "count":     len(data),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("impact/events error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/impact/base-rates")
def get_base_rates(group_by: str = "node_id", min_n: int = 1):
    """
    Step 5 base-rate view grouped by (node_id|basin, channel, severity, anticipated).

    Returns for each group:
      median & IQR move per contract per horizon (T+0, T+1, T+5)
      hit_rate  = n_fired / n_measured  (measured rows only)
      false_positive_rate = unexplained_moves / all_threshold_moves
      n_measured vs n_modeled (shown separately, never mixed)
      products_modeled flag for Asia/MiddleEast/Russia crack+arb cells

    Honesty: API never returns a single predicted price — always a distribution.
    Modeled cells (crack/arb for non-Atlantic basins) are marked and excluded
    from measured base rates.
    """
    try:
        from services.base_rates import compute_base_rates
        if group_by not in ("node_id", "basin"):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "group_by must be 'node_id' or 'basin'"},
            )
        data = compute_base_rates(group_by=group_by, min_n=min_n)
        return {
            "status":    "success",
            "data":      data,
            "count":     len(data),
            "group_by":  group_by,
            "note": (
                "hit_rate is computed on source_tag='history' rows only. "
                "products_modeled=true means crack/arb cells use HO-WTI proxy "
                "and are excluded from the measured base rate."
            ),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("base-rates error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.post("/api/disruption/impact/backfill")
def trigger_backfill(force: bool = False):
    """
    Admin: re-run the catalog backfill.
    force=true overwrites existing rows (use when EIA price cache is refreshed).
    Returns: {inserted, null_events, no_price, errors}.

    Backfill rules:
    - event_date alignment: T-1 = last close BEFORE event, T+0 = ON/AFTER
    - point-in-time EIA prices only (no revised series)
    - T+20 stored but excluded from fired/magnitude_class
    - Wrong-direction moves → fired=False, LOW confidence, confound_note set
    - Anticipated events (OPEC) get anticipated=1 for separate base-rate bucket
    """
    try:
        from services.event_impact_db import backfill_catalog, load_unexplained_moves, init_db
        init_db()
        counts       = backfill_catalog(force=force)
        unexplained  = load_unexplained_moves()
        acled = {}
        try:
            from services.acled_impact_sourcing import backfill_acled_to_impact
            acled = backfill_acled_to_impact(dry_run=False).get("counts", {})
        except Exception as _ae:
            logger.debug("ACLED impact sourcing skipped: %s", _ae)
        return {
            "status":             "success",
            "backfill":           counts,
            "acled_episodes":     acled,
            "unexplained_moves":  unexplained,
            "timestamp":          datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("backfill error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/impact/status")
def get_impact_status():
    """
    DB health: row counts, pending outcomes, unexplained-move count.
    Use to verify the gate is working (null_events should be > 0,
    pending_outcomes fills as maintenance job runs).
    """
    try:
        from services.event_impact_db import get_db_stats
        stats = get_db_stats()
        return {"status": "success", "data": stats, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/coverage")
def get_coverage_table():
    """
    Stage 1a coverage audit. For every catalogued event and every node, document
    whether ACLED can structurally source it (conflict event + region covered on
    the event date + scraped event type + node match) or whether it must come
    from the curated catalog / structural prior.

    Surfaces the holes BEFORE they become silently-empty queries:
      - non-conflict events ACLED can never see (weather/accident/strike/cyber/
        sanction/OPEC decision),
      - regional coverage gaps (US/North-Sea pre-2020, Middle-East pre-2016),
      - the pre-2006 EIA price boundary (Katrina/Rita have no measured reaction).

    ACLED coverage-start dates are ACLED's published regional windows and are
    flagged to_confirm against the current ACLED coverage documentation.
    """
    try:
        from services.coverage_table import build_coverage_table, node_coverage_matrix
        table = build_coverage_table()
        return {
            "status":        "success",
            "events":        table["rows"],
            "summary":       table["summary"],
            "node_matrix":   node_coverage_matrix(),
            "count":         len(table["rows"]),
            "timestamp":     datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("coverage table error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/calibration")
def get_calibration():
    """
    Stage 2 walk-forward calibration harness. For every measured event, predicts
    its forward move from ONLY prior data and checks whether realized T+1/T+5/T+20
    fell inside the 50% / 80% bands. Zero look-ahead (priors are strictly earlier
    events; vol windows end the day before the event).

    Scores two baselines side by side:
      - base_rate  : empirical bands from prior same-bucket events (abstains <2 priors)
      - struct_vol : structural prior centre + point-in-time vol band width

    Returns per-predictor coverage table (nominal 50/80 vs empirical) and a PIT
    histogram (uniform = calibrated). These are the benchmarks Stage 3's analog
    retrieval and Stage 4's Monte-Carlo predictor must beat.
    """
    try:
        from services.calibration_harness import (
            run_harness, predict_base_rate, predict_struct_vol,
        )
        # analog + montecarlo live in modules that import the harness, so register
        # them here (lazy) to avoid an import cycle. This gives the full four-way
        # progression over HTTP, not just the two baselines.
        predictors = {
            "base_rate":  predict_base_rate,
            "struct_vol": predict_struct_vol,
        }
        try:
            from services.analog_retrieval import predict_analog
            predictors["analog"] = predict_analog
        except Exception:
            pass
        try:
            from services.move_predictor import predict_montecarlo
            predictors["montecarlo"] = predict_montecarlo
        except Exception:
            pass
        return {
            "status":    "success",
            "data":      run_harness(predictors=predictors),
            "note": (
                "Calibration improves down the stack: base_rate → struct_vol → "
                "analog → montecarlo. Under-coverage means bands too narrow; the "
                "MC jump term supplies the missing width. uniform_deviation: "
                "0=calibrated, ~0.5=worst."
            ),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("calibration harness error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/analog")
def get_analog(node_id: str, channel: str = "transport",
               severity: str = "outage", restored: bool = False,
               k: int = 6):
    """
    Stage 3 direction-gated analog retrieval. For a hypothetical new event
    (node_id + channel + severity), retrieve the most analogous prior events and
    read the per-product impact direction off the neighbourhood.

    Returns the similarity-weighted per-contract median + sign-consistency, the
    most-hit / most-benefited contracts, and the 3-4 driving analogs. The
    direction gate refuses to cross sign_class (escalation vs restored). If the
    best neighbour is below the similarity floor, confidence drops to STRUCTURAL.

    Weights are tuned against the Stage-2 harness; arb/crack cells outside the
    Atlantic basin are tagged modeled and excluded from the measured read.
    """
    try:
        from services.analog_retrieval import retrieve_for_query
        query = {"node_id": node_id, "channel": channel,
                 "severity": severity, "restored": restored}
        data = retrieve_for_query(query, k=k)
        return {"status": "success", "data": data,
                "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error("analog retrieval error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/walkforward")
def get_walkforward(start_date: str = "2021-01-01", n_paths: int = 2500):
    """
    Walk-forward back-test of grouped ACLED escalation episodes vs realized crude
    (WTI) and distillate-crack moves. Each episode from `start_date` is predicted
    using ONLY prior data (catalog + earlier ACLED episodes) — zero look-ahead —
    and the prediction's 80%/50% bands and direction are scored against what the
    contracts actually did at T+1/T+5.

    This is the empirical proof the grouped-event predictor brackets reality.
    Distillate crack is measured only in Atlantic-basin episodes (Dubai/gasoil
    are modeled elsewhere), so its n is smaller than crude's.
    """
    try:
        from services.walkforward_acled import walk_forward
        return {"status": "success", "data": walk_forward(start_date=start_date, n_paths=n_paths),
                "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error("walkforward error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/trump")
def get_trump(limit: int = 30):
    """
    Trump-post → WTI price-impact panel. Returns the TRAINED model (how the
    front-month WTI moved after his oil-relevant posts, overall and per topic,
    measured on 1-minute CL data 2021→2026) plus the most recent posts with their
    topic and the model's predicted intraday move.

    The per-topic median/IQR/P(up) is a base rate, not a price target.
    """
    try:
        from services.trump_price_impact import run_study
        s = run_study(oil_only=True)
        recent = []
        for p in reversed(s["posts"][-limit:]):
            recent.append({
                "status_id": p["status_id"], "created_utc": p["created_utc"],
                "topic": p["topic"], "stance": p["stance"], "text": p["text"],
                "realized": p["moves"],
                "predicted_stance": s["by_stance"].get(p["stance"], {}),
            })
        return {
            "status": "success",
            "model": {
                "n_posts_scored": s["n_posts_scored"],
                "products":       s["products"],
                "product_labels": s["product_labels"],
                "horizons":       s["horizons"],
                "overall":        s["overall"],
                "by_stance":      s["by_stance"],
                "by_topic":       s["by_topic"],
            },
            "recent": recent,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("trump impact error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/disruption/forecast")
def get_forecast(node_id: str, channel: str = "transport",
                 severity: str = "outage", restored: bool = False,
                 n_paths: int = 3000, k: int = 6):
    """
    Stage 4 jump-diffusion Monte-Carlo forward distribution for a hypothetical new
    event. Combines a news jump (block-bootstrapped from the Stage-3 analog
    neighbourhood, severity-scaled) with baseline diffusion (2-regime GMM on the
    contract's own point-in-time return history).

    Returns per-contract percentile bands at T+1/5/20, P(up), expected move,
    P(touch ±5%/$5), the driving analogs, and a confidence badge. Zero/weak
    neighbourhoods fall back to a labelled structural-prior distribution.

    This is a calibrated scenario distribution, never a deterministic price
    forecast. Validated on the Stage-2 harness (50/80% bands cover at target).
    """
    try:
        from services.move_predictor import forward_distribution
        query = {"node_id": node_id, "channel": channel,
                 "severity": severity, "restored": restored}
        data = forward_distribution(query, n_paths=n_paths, k=k)
        return {"status": "success", "data": data,
                "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error("forecast error: %s", e)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
if os.path.isdir(frontend_path):
    from fastapi.responses import FileResponse
    
    # Mount the assets directory specifically
    assets_path = os.path.join(frontend_path, "assets")
    if os.path.isdir(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    
    # Catch-all route to serve React app and handle client-side routing
    @app.get("/{catchall:path}")
    async def serve_react_app(catchall: str):
        # Prevent accessing files outside frontend_path
        file_path = os.path.abspath(os.path.join(frontend_path, catchall))
        if not file_path.startswith(os.path.abspath(frontend_path)):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
            
        if catchall and os.path.isfile(file_path):
            return FileResponse(file_path)
            
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
            
        return JSONResponse(status_code=404, content={"detail": "Frontend not built"})
