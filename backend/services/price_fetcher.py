import logging
import math
import time
import threading
import os
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf
import requests

# Import environment configuration
try:
    from config import USE_YFINANCE, LOG_DATA_FETCHER_WARNINGS, CACHE_DURATION_SECONDS
except ImportError:
    USE_YFINANCE = True
    LOG_DATA_FETCHER_WARNINGS = True
    CACHE_DURATION_SECONDS = 300

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-memory price cache & Cooldown logic
# ---------------------------------------------------------------------------
_ALL_PRICES_CACHE: Tuple[float, Dict[str, dict]] = (0.0, {})
_CACHE_TTL = CACHE_DURATION_SECONDS  # seconds

# Thread-safe in-memory cache for last known prices and cooldowns
_CACHE_LOCK = threading.Lock()
_LAST_KNOWN_PRICES: Dict[str, dict] = {}
_SYMBOL_COOLDOWN: Dict[str, float] = {}  # symbol -> expiration timestamp (time.time())

# Cap concurrent outbound fetches. yfinance opens connections to a small number
# of Yahoo hosts; keeping the worker count at or below the connection-pool size
# avoids urllib3 "Connection pool is full" churn and Yahoo rate-limiting.
_MAX_FETCH_WORKERS = 4

# Shared requests session with browser-like User-Agent header. We mount an adapter
# with a connection pool large enough for our concurrency so urllib3 stops logging
# "Connection pool is full, discarding connection".
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
})
_ADAPTER = requests.adapters.HTTPAdapter(
    pool_connections=_MAX_FETCH_WORKERS * 2,
    pool_maxsize=_MAX_FETCH_WORKERS * 4,
    max_retries=0,
)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)


_DXY_DIAGNOSTICS = {
    "status": "PENDING",
    "last_attempt": None,
    "last_success": None,
    "response_code": None,
    "response_snippet": None,
    "exception_trace": None,
    "credentials_present": False,
    "outbound_internet": "Unknown",
    "cors_behavior": "Unknown",
    "rate_limits": "Unknown",
}


class PriceFetcher:
    """Fetch price data from Yahoo Finance with comprehensive symbol coverage"""

    # Comprehensive symbol mapping including all oil benchmarks and derivatives
    SYMBOLS = {
        # Crude Oil Benchmarks
        "WTI": "CL=F",           # WTI Crude
        "Brent": "BZ=F",         # Brent Crude
        "DUBAICRUDE": None,       # Dubai Crude proxy (derived when available)
        
        # Refined Products
        "RBOB": "RB=F",          # RBOB Gasoline
        "HO": "HO=F",            # Heating Oil
        "GO": "G0=F",            # ICE Gasoil (London, denominated in $/MT)

        # Crack Spreads (calculated from components)
        "3-2-1CRACK": None,      # Calculated: 3*Brent - 2*RBOB - 1*HO

        "GASCRACK": None,        # Calculated: RBOB - WTI
        "DIESELCRACK": None,     # Calculated: HO - WTI
        "FRAC": None,            # Calculated: HO - HH
        "WCS-WTI": None,         # Derived differential proxy
        
        # Natural Gas
        "HH": "NG=F",            # Henry Hub Natural Gas
        "NG": "NG=F",            # Natural Gas Alias

        # Currencies & Macro
        "DXY": "DX-Y.NYB",       # US Dollar Index
        "SPX": "^GSPC",          # S&P 500
        "TNX": "^TNX",           # 10Y Treasury Yield
        "VIX": "^VIX",           # Volatility Index
        "GC": "GC=F",            # Gold
        "USO": "USO",            # Crude ETF liquidity proxy
        "UNG": "UNG",            # Natural gas ETF proxy
    }

    DEFAULT_PRICES = {
        "WTI": {"symbol": "WTI", "open": 80.0, "high": 81.0, "low": 78.5, "close": 80.2, "volume": 0, "change_pct": 0.0},
        "Brent": {"symbol": "Brent", "open": 83.0, "high": 84.0, "low": 82.0, "close": 83.5, "volume": 0, "change_pct": 0.0},
        "RBOB": {"symbol": "RBOB", "open": 84.0, "high": 86.1, "low": 81.9, "close": 85.05, "volume": 0, "change_pct": 0.0},
        "HO": {"symbol": "HO", "open": 96.6, "high": 98.7, "low": 94.5, "close": 97.44, "volume": 0, "change_pct": 0.0},
        "JET": {"symbol": "JET", "open": 155.0, "high": 158.0, "low": 152.0, "close": 156.5, "volume": 0, "change_pct": 0.0},
        # NOTE: GO (ICE Gasoil) intentionally has NO static fallback. Yahoo no
        # longer serves a working gasoil ticker (G0=F / QS=F return empty), so a
        # hardcoded close here would surface as a fake, frozen $705 price in the
        # top bar. With no entry, _get_fallback_price returns None and the GO pill
        # renders "—" (no data) instead of a fabricated number. Wire a real gasoil
        # feed here if one becomes available.
        "HH": {"symbol": "HH", "open": 3.4, "high": 3.5, "low": 3.3, "close": 3.41, "volume": 0, "change_pct": 0.0},
        "NG": {"symbol": "NG", "open": 3.4, "high": 3.5, "low": 3.3, "close": 3.41, "volume": 0, "change_pct": 0.0},
        "DXY": {"symbol": "DXY", "open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 0, "change_pct": 0.0},
        "SPX": {"symbol": "SPX", "open": 5900.0, "high": 5910.0, "low": 5880.0, "close": 5892.0, "volume": 0, "change_pct": 0.0},
        "TNX": {"symbol": "TNX", "open": 4.3, "high": 4.35, "low": 4.25, "close": 4.31, "volume": 0, "change_pct": 0.0},
        "VIX": {"symbol": "VIX", "open": 16.0, "high": 16.8, "low": 15.6, "close": 16.4, "volume": 0, "change_pct": 0.0},
        "GC": {"symbol": "GC", "open": 2250.0, "high": 2270.0, "low": 2235.0, "close": 2260.0, "volume": 0, "change_pct": 0.0},
        "USO": {"symbol": "USO", "open": 72.0, "high": 73.0, "low": 71.2, "close": 72.5, "volume": 0, "change_pct": 0.0},
        "UNG": {"symbol": "UNG", "open": 14.0, "high": 14.2, "low": 13.8, "close": 14.0, "volume": 0, "change_pct": 0.0},
    }

    @staticmethod
    def _get_fallback_price(symbol: str, now: Optional[str] = None) -> Optional[Dict]:
        """Return fallback price data for a symbol."""
        if now is None:
            now = datetime.now().isoformat()

        if symbol in PriceFetcher.DEFAULT_PRICES:
            fallback = PriceFetcher.DEFAULT_PRICES[symbol].copy()
            fallback["timestamp"] = now
            return fallback

        if symbol in ("DUBAICRUDE", "WCS-WTI"):
            derived = PriceFetcher.fetch_derived_symbol(symbol)
            if derived:
                derived["timestamp"] = now
                return derived

        return None

    @staticmethod
    def _upsert_daily_price(symbol: str, price_data: dict):
        try:
            from database import SessionLocal
            from models import PriceHistory
            from sqlalchemy.exc import IntegrityError
            db = SessionLocal()
            ts_str = price_data.get("timestamp")
            if not ts_str:
                return
            date_str = ts_str[:10]
            
            record = db.query(PriceHistory).filter(PriceHistory.symbol == symbol, PriceHistory.date == date_str).first()
            if record:
                record.close = price_data["close"]
                record.high = max(record.high or price_data["close"], price_data["high"])
                record.low = min(record.low or price_data["close"], price_data["low"])
                record.volume = max(record.volume or 0.0, price_data["volume"])
            else:
                record = PriceHistory(
                    id=f"{symbol}_{date_str}",
                    symbol=symbol,
                    open=price_data["open"],
                    high=price_data["high"],
                    low=price_data["low"],
                    close=price_data["close"],
                    volume=price_data["volume"],
                    date=date_str,
                    timestamp=datetime.strptime(date_str, "%Y-%m-%d")
                )
                db.add(record)
            try:
                db.commit()
            except IntegrityError:
                # Concurrent publisher inserted the same id first — fold this
                # tick into the existing row instead of erroring out.
                db.rollback()
                existing = db.query(PriceHistory).filter(PriceHistory.id == f"{symbol}_{date_str}").first()
                if existing:
                    existing.close = price_data["close"]
                    existing.high = max(existing.high or price_data["close"], price_data["high"])
                    existing.low = min(existing.low or price_data["close"], price_data["low"])
                    existing.volume = max(existing.volume or 0.0, price_data["volume"])
                    db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Error upserting daily price for {symbol}: {e}")

    @staticmethod
    def _fetch_from_db(symbol: str) -> Optional[Dict]:
        try:
            from database import SessionLocal
            from models import PriceHistory
            db = SessionLocal()
            records = db.query(PriceHistory).filter(PriceHistory.symbol == symbol).order_by(PriceHistory.date.desc()).limit(2).all()
            db.close()
            if records:
                latest = records[0]
                change_pct = 0.0
                if len(records) > 1 and records[1].close:
                    change_pct = ((latest.close - records[1].close) / records[1].close) * 100
                return {
                    "symbol": symbol,
                    "open": latest.open,
                    "high": latest.high,
                    "low": latest.low,
                    "close": latest.close,
                    "volume": latest.volume,
                    "change_pct": change_pct,
                    "timestamp": datetime.strptime(latest.date, '%Y-%m-%d').isoformat()
                }
        except Exception as db_err:
            logger.error(f"Error fetching {symbol} from db: {db_err}")
        return None

    @staticmethod
    def _fetch_live_db_price(symbol: str) -> Optional[Dict]:
        try:
            import sqlite3
            import os
            from datetime import datetime
            
            # Locate the bars_15min_latest.db file (local, non-synced — see config)
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.environ.get("BARS15_DB_PATH") or os.path.join(base_dir, "DB", "bars_15min_latest.db")

            if not os.path.exists(db_path):
                return None
                
            prefix = ""
            if symbol == "WTI":
                prefix = "CL"
            elif symbol == "Brent":
                prefix = "CO"
            else:
                return None
                
            conn = sqlite3.connect(db_path)
            tables = [t[0] for t in conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()]
            
            # Sort tables to find the front month contract
            def parse_contract(t):
                # t is like CL_N26
                suffix = t.split('_')[1]
                month_code = suffix[0]
                year_str = suffix[1:]
                months = {'F':1, 'G':2, 'H':3, 'J':4, 'K':5, 'M':6, 'N':7, 'Q':8, 'U':9, 'V':10, 'X':11, 'Z':12}
                return (int(year_str), months.get(month_code, 99))
            
            tables.sort(key=parse_contract)
            
            # Find the global max timestamp across all tables.
            # Exclude tables whose MAX(timestamp) is more than 1 day in the
            # future — those have corrupt/far-dated rows (e.g. CO_Q27) that
            # would skew the cutoff and cause all near-term contracts to fail.
            from datetime import datetime, timedelta
            _now_ceil = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            table_max_ts = {}
            global_max = ""
            for t in tables:
                row = conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()
                if row and row[0]:
                    ts = row[0].replace("T", " ")[:19]
                    if ts > _now_ceil:
                        continue  # corrupt far-future timestamp — skip
                    table_max_ts[t] = row[0]
                    if row[0] > global_max:
                        global_max = row[0]

            latest_row = None
            latest_table = ""

            if global_max:
                try:
                    clean_max = global_max.replace("T", " ")[:19]
                    max_dt = datetime.strptime(clean_max, "%Y-%m-%d %H:%M:%S")
                    cutoff_str = (max_dt - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    cutoff_str = global_max

                for t in tables:
                    ts = table_max_ts.get(t, "")
                    clean_ts = ts.replace("T", " ")[:19]
                    if clean_ts >= cutoff_str:
                        row = conn.execute(f"SELECT timestamp, open, high, low, close, volume FROM {t} ORDER BY timestamp DESC LIMIT 1").fetchone()
                        if row:
                            latest_row = row
                            latest_table = t
                            break  # Found the active front-most contract with recent data
                    
            conn.close()
            
            if latest_row:
                change_pct = 0.0
                if latest_table:
                    conn = sqlite3.connect(db_path)
                    prev_rows = conn.execute(f"SELECT close FROM {latest_table} ORDER BY timestamp DESC LIMIT 2").fetchall()
                    conn.close()
                    if len(prev_rows) > 1 and prev_rows[1][0] and prev_rows[1][0] != 0:
                        change_pct = ((latest_row[4] - prev_rows[1][0]) / prev_rows[1][0]) * 100

                ts_iso = latest_row[0]
                if " " in ts_iso:
                    ts_iso = ts_iso.replace(" ", "T")
                
                return {
                    "symbol": symbol,
                    "open": float(latest_row[1]),
                    "high": float(latest_row[2]),
                    "low": float(latest_row[3]),
                    "close": float(latest_row[4]),
                    "volume": float(latest_row[5]) if latest_row[5] else 0.0,
                    "change_pct": change_pct,
                    "timestamp": ts_iso,
                }
        except Exception as e:
            logger.error(f"Error fetching live db price for {symbol}: {e}")
        return None

    @staticmethod
    def fetch_symbol(symbol: str, period: str = "1d") -> Optional[Dict]:
        """
        Fetch OHLCV data for a symbol
        period: '1d', '5d', '1mo', '3mo'
        """
        # WTI and Brent are DB-only by design — never hit yfinance. Use the live
        # 15-min candle DB, then the stored daily row, then a static fallback.
        if symbol in ("WTI", "Brent"):
            live_price = PriceFetcher._fetch_live_db_price(symbol)
            if live_price:
                PriceFetcher._upsert_daily_price(symbol, live_price)
                return live_price
            db_price = PriceFetcher._fetch_from_db(symbol)
            if db_price:
                return db_price
            return PriceFetcher._get_fallback_price(symbol)

        # Try fetching from yfinance first for real-time prices
        try:
            ticker_symbol = PriceFetcher.SYMBOLS.get(symbol)
            if ticker_symbol is not None:
                price = PriceFetcher._fetch_price_from_ticker(symbol, ticker_symbol)
                if price:
                    # Upsert daily record to database
                    PriceFetcher._upsert_daily_price(symbol, price)
                    return price
            else:
                derived = PriceFetcher.fetch_derived_symbol(symbol)
                if derived:
                    return derived
        except Exception as e:
            logger.error(f"Error fetching {symbol} from yfinance/derived: {e}")

        # Fallback to local database if yfinance is rate-limited or offline
        db_price = PriceFetcher._fetch_from_db(symbol)
        if db_price:
            return db_price

        # Default fallback
        return PriceFetcher._get_fallback_price(symbol)

    @staticmethod
    def fetch_derived_symbol(symbol: str, prices: Optional[Dict[str, Dict]] = None) -> Optional[Dict]:
        """Generate a derived quote for non-standard symbols."""
        if prices is None:
            prices = PriceFetcher.fetch_all_prices()
        now = datetime.now().isoformat()

        if symbol == "DUBAICRUDE":
            wti = prices.get("WTI")
            brent = prices.get("Brent")
            if wti and brent:
                close = (wti["close"] + brent["close"]) / 2.0
                return {
                    "symbol": symbol,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 0,
                    "change_pct": 0.0,
                    "timestamp": now,
                }

        if symbol == "WCS-WTI":
            wti = prices.get("WTI")
            if wti:
                close = max(wti["close"] - 5.0, 0.0)
                return {
                    "symbol": symbol,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 0,
                    "change_pct": 0.0,
                    "timestamp": now,
                }

        return None


    @staticmethod
    def _fetch_price_from_ticker(symbol: str, ticker_symbol: str, session: Optional[requests.Session] = None) -> Optional[Dict]:
        is_dxy = (symbol == "DXY")
        
        # Check cooldown
        now_ts = time.time()
        with _CACHE_LOCK:
            cooldown_expiry = _SYMBOL_COOLDOWN.get(symbol, 0.0)
            if now_ts < cooldown_expiry:
                fallback_val = _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.info(f"Symbol {symbol} ({ticker_symbol}) is on fetch cooldown. Returning fallback price.")
                return fallback_val

        if is_dxy:
            _DXY_DIAGNOSTICS["last_attempt"] = datetime.now().isoformat()
            _DXY_DIAGNOSTICS["credentials_present"] = bool(os.getenv("TWELVE_DATA_KEY"))
            # Test general outbound connectivity first
            try:
                test_res = requests.get("https://www.google.com", timeout=3)
                if test_res.status_code == 200:
                    _DXY_DIAGNOSTICS["outbound_internet"] = "OK"
                else:
                    _DXY_DIAGNOSTICS["outbound_internet"] = f"Failed (HTTP {test_res.status_code})"
            except Exception as internet_err:
                _DXY_DIAGNOSTICS["outbound_internet"] = f"Error: {str(internet_err)}"

            # Detailed test fetch for Yahoo Finance
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                test_yf_url = "https://query1.finance.yahoo.com/v7/finance/chart/DX-Y.NYB?range=5d&interval=15m"
                logger.info(f"DXY Diagnostic Fetch: GET {test_yf_url}")
                yf_resp = requests.get(test_yf_url, headers=headers, timeout=5)
                _DXY_DIAGNOSTICS["response_code"] = yf_resp.status_code
                _DXY_DIAGNOSTICS["response_snippet"] = yf_resp.text[:500]
                if yf_resp.status_code == 429:
                    _DXY_DIAGNOSTICS["rate_limits"] = "Rate Limited (429)"
                elif yf_resp.status_code == 200:
                    _DXY_DIAGNOSTICS["rate_limits"] = "OK"
                else:
                    _DXY_DIAGNOSTICS["rate_limits"] = f"HTTP {yf_resp.status_code}"
            except Exception as fetch_err:
                _DXY_DIAGNOSTICS["response_code"] = None
                _DXY_DIAGNOSTICS["response_snippet"] = f"Fetch failed: {str(fetch_err)}"
                _DXY_DIAGNOSTICS["exception_trace"] = traceback.format_exc()

        if not USE_YFINANCE or symbol in ["WTI", "Brent", "BRN"]:
            if LOG_DATA_FETCHER_WARNINGS:
                logger.info(f"Skipping yfinance for {symbol} ({ticker_symbol}); disabled or local DB only")
            if is_dxy:
                _DXY_DIAGNOSTICS["status"] = "ERROR"
                _DXY_DIAGNOSTICS["exception_trace"] = "yfinance disabled (USE_YFINANCE=False)"
            return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

        try:
            # Pass our custom requests session to yfinance Ticker
            ticker = yf.Ticker(ticker_symbol, session=_SESSION)

            # Reduced to 2 retries with short backoff so the total per-symbol
            # worst-case time is ~3s instead of 15.5s, keeping within the
            # frontend's axios timeout when fetching all symbols concurrently.
            max_retries = 2
            backoff = [0.5, 1.5]
            hist = None

            for attempt in range(max_retries):
                try:
                    # Try 15-minute interval data first for more current data
                    hist = ticker.history(period="5d", interval="15m", actions=False)
                    if hist is None or getattr(hist, "empty", True):
                        # Fall back to daily data
                        hist = ticker.history(period="5d", actions=False)
                    if hist is not None and not getattr(hist, "empty", True):
                        break
                    raise ValueError("empty history result")
                except Exception as e:
                    # Put the symbol on cooldown if it failed
                    is_rate_limit = "Too Many Requests" in str(e) or "429" in str(e)
                    with _CACHE_LOCK:
                        _SYMBOL_COOLDOWN[symbol] = time.time() + 300  # 5-minute cooldown
                    
                    if is_dxy:
                        _DXY_DIAGNOSTICS["status"] = "ERROR"
                        _DXY_DIAGNOSTICS["exception_trace"] = traceback.format_exc()
                        logger.error(f"DXY yfinance fetch attempt {attempt+1} failed: {e}\n{traceback.format_exc()}")
                    if LOG_DATA_FETCHER_WARNINGS:
                        logger.warning(
                            f"yfinance fetch attempt {attempt+1}/{max_retries} for {symbol} ({ticker_symbol}): {e}. Symbol put on cooldown."
                        )
                    if attempt < max_retries - 1:
                        time.sleep(backoff[attempt])
                    else:
                        if LOG_DATA_FETCHER_WARNINGS:
                            logger.error(
                                f"yfinance: Failed to fetch {symbol} ({ticker_symbol}) after {max_retries} retries"
                            )
                        return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

            if hist is None or getattr(hist, "empty", True):
                with _CACHE_LOCK:
                    _SYMBOL_COOLDOWN[symbol] = time.time() + 300
                if is_dxy:
                    _DXY_DIAGNOSTICS["status"] = "ERROR"
                    _DXY_DIAGNOSTICS["exception_trace"] = "No yfinance history returned."
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"No yfinance history for {symbol} ({ticker_symbol}). Symbol put on cooldown.")
                return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

            if "Close" not in hist.columns:
                with _CACHE_LOCK:
                    _SYMBOL_COOLDOWN[symbol] = time.time() + 300
                if is_dxy:
                    _DXY_DIAGNOSTICS["status"] = "ERROR"
                    _DXY_DIAGNOSTICS["exception_trace"] = "Missing Close column in history."
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"Unexpected yfinance response for {symbol} ({ticker_symbol}); missing Close. Symbol put on cooldown.")
                return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

            row = hist.iloc[-1]
            if row is None or row.empty:
                with _CACHE_LOCK:
                    _SYMBOL_COOLDOWN[symbol] = time.time() + 300
                if is_dxy:
                    _DXY_DIAGNOSTICS["status"] = "ERROR"
                    _DXY_DIAGNOSTICS["exception_trace"] = "Last history row is empty."
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"No valid price row for {symbol} ({ticker_symbol}). Symbol put on cooldown.")
                return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

            close = row.get("Close")
            if close is None or (isinstance(close, float) and math.isnan(close)):
                with _CACHE_LOCK:
                    _SYMBOL_COOLDOWN[symbol] = time.time() + 300
                if is_dxy:
                    _DXY_DIAGNOSTICS["status"] = "ERROR"
                    _DXY_DIAGNOSTICS["exception_trace"] = f"Invalid close price: {close}"
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"Invalid close price for {symbol} ({ticker_symbol}). Symbol put on cooldown.")
                return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

            open_price = row.get("Open")
            high = row.get("High")
            low = row.get("Low")
            volume = row.get("Volume")

            close = float(close)
            open_price = float(open_price) if open_price is not None and not (isinstance(open_price, float) and math.isnan(open_price)) else close
            high = float(high) if high is not None and not (isinstance(high, float) and math.isnan(high)) else close
            low = float(low) if low is not None and not (isinstance(low, float) and math.isnan(low)) else close
            volume = float(volume) if volume is not None and not (isinstance(volume, float) and math.isnan(volume)) else 0.0

            # Scale RBOB and HO from $/gallon to $/barrel
            if symbol in ("RBOB", "HO"):
                close *= 42.0
                open_price *= 42.0
                high *= 42.0
                low *= 42.0
            elif symbol == "GO":
                close /= 7.45
                open_price /= 7.45
                high /= 7.45
                low /= 7.45

            prev_close = None
            if len(hist.dropna(subset=["Close"])) > 1:
                prev_close = hist.dropna(subset=["Close"]).iloc[-2].get("Close")
                prev_close = float(prev_close) if prev_close is not None else None
                
            # Scale prev_close as well so percent change doesn't spike by 4200%
            if symbol in ("RBOB", "HO") and prev_close is not None:
                prev_close *= 42.0
            elif symbol == "GO" and prev_close is not None:
                prev_close /= 7.45

            delta_pct = ((close - prev_close) / prev_close) * 100 if prev_close and prev_close != 0 else 0.0
            timestamp = row.name
            if not hasattr(timestamp, "isoformat"):
                timestamp = datetime.now()

            if is_dxy:
                _DXY_DIAGNOSTICS["status"] = "OK"
                _DXY_DIAGNOSTICS["last_success"] = datetime.now().isoformat()
                _DXY_DIAGNOSTICS["exception_trace"] = None

            res_price = {
                "symbol": symbol,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "change_pct": float(delta_pct),
                "timestamp": timestamp.isoformat(),
            }
            with _CACHE_LOCK:
                _LAST_KNOWN_PRICES[symbol] = res_price
            return res_price
        except Exception as e:
            with _CACHE_LOCK:
                _SYMBOL_COOLDOWN[symbol] = time.time() + 300
            if is_dxy:
                _DXY_DIAGNOSTICS["status"] = "ERROR"
                _DXY_DIAGNOSTICS["exception_trace"] = traceback.format_exc()
                logger.error(f"DXY Fetch error: {e}\n{traceback.format_exc()}")
            if LOG_DATA_FETCHER_WARNINGS:
                logger.error(f"yfinance fetch failed for {symbol} ({ticker_symbol}): {e}. Symbol put on cooldown.")
            return _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)

    @staticmethod
    def fetch_all_prices() -> Dict[str, Dict]:
        """Fetch all primary product prices using yfinance with concurrent requests.

        Results are cached for _CACHE_TTL seconds so repeated API calls within
        that window return instantly without hitting yfinance again.
        """
        global _ALL_PRICES_CACHE
        now = time.time()
        cache_ts, cached_prices = _ALL_PRICES_CACHE
        if cached_prices and (now - cache_ts) < _CACHE_TTL:
            logger.debug("fetch_all_prices: returning cached data")
            return cached_prices

        prices = {}
        
        symbol_to_ticker = {
            symbol: ticker for symbol, ticker in PriceFetcher.SYMBOLS.items() if ticker is not None
        }

        # Fetch concurrently (will try yfinance and fall back to SQLite database per symbol).
        # Keep workers bounded to avoid connection-pool exhaustion and Yahoo rate limits.
        with ThreadPoolExecutor(max_workers=_MAX_FETCH_WORKERS) as executor:
            future_to_symbol = {
                executor.submit(PriceFetcher.fetch_symbol, symbol): symbol
                for symbol in symbol_to_ticker
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                quote = None
                try:
                    quote = future.result(timeout=20)
                except Exception as e:
                    logger.error(f"Error in concurrent fetch for {symbol}: {e}")
                
                if quote:
                    prices[symbol] = quote
                else:
                    with _CACHE_LOCK:
                        fallback = _LAST_KNOWN_PRICES.get(symbol) or PriceFetcher._get_fallback_price(symbol)
                    if fallback:
                        prices[symbol] = fallback

        # Calculate WTI-Brent spread
        wti = prices.get("WTI")
        brent = prices.get("Brent")
        if wti and brent:
            spread_val = wti["close"] - brent["close"]
            spread_data = {
                "symbol": "WTI-Brent",
                "open": spread_val,
                "high": spread_val,
                "low": spread_val,
                "close": spread_val,
                "volume": 0.0,
                "change_pct": wti.get("change_pct", 0.0) - brent.get("change_pct", 0.0),
                "timestamp": wti["timestamp"]
            }
            prices["WTI-Brent"] = spread_data
            PriceFetcher._upsert_daily_price("WTI-Brent", spread_data)

        # Calculate 3-2-1 Crack, GASCRACK, DIESELCRACK
        rbob = prices.get("RBOB")
        ho = prices.get("HO")
        if wti and rbob and ho:
            crack_val = ((2 * rbob["close"] + 1 * ho["close"]) - 3 * wti["close"]) / 3.0
            crack_data = {
                "symbol": "3-2-1CRACK",
                "open": crack_val,
                "high": crack_val,
                "low": crack_val,
                "close": crack_val,
                "volume": 0.0,
                "change_pct": 0.0,
                "timestamp": wti["timestamp"]
            }
            prices["3-2-1CRACK"] = crack_data
            
            gascrack_val = rbob["close"] - wti["close"]
            prices["GASCRACK"] = {
                "symbol": "GASCRACK",
                "open": gascrack_val,
                "high": gascrack_val,
                "low": gascrack_val,
                "close": gascrack_val,
                "volume": 0.0,
                "change_pct": 0.0,
                "timestamp": wti["timestamp"]
            }
            
            dieselcrack_val = ho["close"] - wti["close"]
            prices["DIESELCRACK"] = {
                "symbol": "DIESELCRACK",
                "open": dieselcrack_val,
                "high": dieselcrack_val,
                "low": dieselcrack_val,
                "close": dieselcrack_val,
                "volume": 0.0,
                "change_pct": 0.0,
                "timestamp": wti["timestamp"]
            }

        # Calculate live spreads and flies from forward curve if available
        try:
            from services.curve_analytics import get_market_structure_analytics
            now_str = datetime.now().isoformat()
            
            for base_sym in ["WTI", "Brent", "RBOB", "HO"]:
                struct = get_market_structure_analytics(base_sym)
                if not struct:
                    continue
                    
                prefix = base_sym.upper()
                
                # CAL SPREAD
                if struct.get("spreads", {}).get("m1_m2") is not None:
                    val = struct["spreads"]["m1_m2"]
                    sym_name = f"{prefix}_CAL_SPREAD"
                    prices[sym_name] = {
                        "symbol": sym_name, "open": val, "high": val, "low": val, 
                        "close": val, "volume": 0.0, "change_pct": 0.0, "timestamp": now_str
                    }
                    
                # FLIES & DFLIES (Dynamic)
                flies_data = struct.get("flies", {})
                for fly_key, val in flies_data.items():
                    if val is not None:
                        # fly_key is e.g. "fly_1_2_3" or "dfly_1_2_3_4"
                        # We want WTI_FLY_1_2_3
                        parts = fly_key.split("_")
                        if parts[0] == "fly":
                            # Default WTI_FLY for 1-2-3 backward compatibility if needed, but let's be explicit
                            if fly_key == "fly_1_2_3":
                                sym_name_base = f"{prefix}_FLY"
                                prices[sym_name_base] = {
                                    "symbol": sym_name_base, "open": val, "high": val, "low": val, 
                                    "close": val, "volume": 0.0, "change_pct": 0.0, "timestamp": now_str
                                }
                            sym_name = f"{prefix}_FLY_{parts[1]}_{parts[2]}_{parts[3]}"
                        elif parts[0] == "dfly":
                            if fly_key == "dfly_1_2_3_4":
                                sym_name_base = f"{prefix}_DFLY"
                                prices[sym_name_base] = {
                                    "symbol": sym_name_base, "open": val, "high": val, "low": val, 
                                    "close": val, "volume": 0.0, "change_pct": 0.0, "timestamp": now_str
                                }
                            sym_name = f"{prefix}_DFLY_{parts[1]}_{parts[2]}_{parts[3]}_{parts[4]}"
                        else:
                            continue
                            
                        prices[sym_name] = {
                            "symbol": sym_name, "open": val, "high": val, "low": val, 
                            "close": val, "volume": 0.0, "change_pct": 0.0, "timestamp": now_str
                        }
                    
        except Exception as e:
            logger.error(f"Error computing live structural prices in fetch_all_prices: {e}")

        # Calculate derived symbols from prices that were successfully fetched
        for derived_symbol in ["DUBAICRUDE", "WCS-WTI"]:
            if derived_symbol not in prices:
                derived_price = PriceFetcher.fetch_derived_symbol(derived_symbol, prices=prices)
                if derived_price:
                    prices[derived_symbol] = derived_price

        # Calculate DUB-WTI spread
        dubai = prices.get("DUBAICRUDE")
        if dubai and wti:
            dub_wti_val = dubai["close"] - wti["close"]
            prices["DUB-WTI"] = {
                "symbol": "DUB-WTI",
                "open": dub_wti_val,
                "high": dub_wti_val,
                "low": dub_wti_val,
                "close": dub_wti_val,
                "volume": 0.0,
                "change_pct": 0.0,
                "timestamp": wti["timestamp"]
            }

        if not prices:
            logger.error("No prices were fetched from database or yfinance!")
        else:
            _ALL_PRICES_CACHE = (now, prices)

        return prices

    @staticmethod
    def _parse_period_days(period: str) -> int:
        mapping = {
            "1d": 1,
            "5d": 5,
            "1wk": 5,
            "1mo": 22,
            "3mo": 66,
            "6mo": 132,
            "1y": 252,
            "2y": 504,
            "5y": 1260,
            "max": 9999,
        }
        if period in mapping:
            return mapping[period]

        try:
            if period.endswith("d"):
                return int(period[:-1])
            if period.endswith("wk"):
                return int(period[:-2]) * 5
            if period.endswith("mo"):
                return int(period[:-2]) * 22
            if period.endswith("y"):
                return int(period[:-1]) * 252
        except Exception:
            pass

        return 20

    @staticmethod
    def _create_synthetic_history(symbol: str, close: float, days: int) -> List[Dict]:
        history = []
        base_date = datetime.now()
        for i in range(days):
            point_date = base_date - timedelta(days=(days - i - 1))
            history.append({
                "timestamp": point_date.strftime("%Y-%m-%d"),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 0.0,
            })
        return history

    @staticmethod
    def _fetch_crack_spread_historical(symbol: str, period: str) -> Optional[List[Dict]]:
        import pandas as pd

        # Gasoil crack = ICE gasoil (GO, $/bbl-equiv) − Brent. The European diesel
        # refining margin. GO & Brent now carry deep DB history, so it's fully daily.
        if symbol == "GASOILCRACK":
            go = PriceFetcher.fetch_historical("GO", period)
            brent = PriceFetcher.fetch_historical("Brent", period)
            if not (go and brent):
                return None
            dg = pd.DataFrame(go).set_index("timestamp")["close"].rename("GO")
            db_ = pd.DataFrame(brent).set_index("timestamp")["close"].rename("Brent")
            crack = pd.concat([dg, db_], axis=1).dropna()
            if crack.empty:
                return None
            spread = crack["GO"] - crack["Brent"]
            return [{"timestamp": idx, "open": float(v), "high": float(v),
                     "low": float(v), "close": float(v), "volume": 0.0}
                    for idx, v in spread.items()]

        wti = PriceFetcher.fetch_historical("WTI", period)
        rbob = PriceFetcher.fetch_historical("RBOB", period)
        ho = PriceFetcher.fetch_historical("HO", period)
        
        if not (wti and rbob and ho):
            return None
            
        import pandas as pd
        df_wti = pd.DataFrame(wti).set_index("timestamp")
        df_rbob = pd.DataFrame(rbob).set_index("timestamp")
        df_ho = pd.DataFrame(ho).set_index("timestamp")
        
        df = pd.concat([df_wti["close"].rename("WTI"), df_rbob["close"].rename("RBOB"), df_ho["close"].rename("HO")], axis=1).dropna()
        
        if df.empty:
            return None
            
        if symbol == "GASCRACK":
            crack = df["RBOB"] - df["WTI"]
        elif symbol == "DIESELCRACK":
            crack = df["HO"] - df["WTI"]
        else: # 3-2-1 Crack
            crack = ((2 * df["RBOB"] + 1 * df["HO"]) - 3 * df["WTI"]) / 3.0
        
        rows = []
        for idx, val in crack.items():
            rows.append({
                "timestamp": idx,
                "open": float(val),
                "high": float(val),
                "low": float(val),
                "close": float(val),
                "volume": 0.0
            })
            
        return rows
    import pandas as pd
    @staticmethod
    def _query_historical_term_structure(symbol: str, days: int) -> Optional[pd.DataFrame]:
        try:
            from database import SessionLocal
            import pandas as pd
            db = SessionLocal()
            engine = db.get_bind()
            
            # Since the db contains 1-min data, we get the EOD close by doing a grouped query or max timestamp per day
            # Since prices are chronological, max(timestamp) gives the last price of the day
            query = f"""
            SELECT DATE(timestamp) as date, m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12
            FROM historical_term_structure 
            WHERE symbol='{symbol}' 
            GROUP BY DATE(timestamp) 
            ORDER BY date DESC 
            LIMIT {days}
            """
            df = pd.read_sql(query, engine)
            db.close()
            if df.empty:
                return None
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date').sort_index()
            return df
        except Exception as e:
            logger.error(f"Error querying historical_term_structure for {symbol}: {e}")
            return None

    @staticmethod
    def _fetch_cal_spread_historical(symbol: str, period: str) -> Optional[List[Dict]]:
        base_asset = symbol.split("_")[0]  # e.g., WTI
        if base_asset.upper() == "BRENT":
            base_asset = "Brent"
            
        days = PriceFetcher._parse_period_days(period)
        df = PriceFetcher._query_historical_term_structure(base_asset, days)
        if df is None or df.empty or 'm1' not in df.columns or 'm2' not in df.columns:
            return None
            
        spread = df["m1"] - df["m2"]
        spread = spread.dropna()
        
        rows = []
        for idx, val in spread.items():
            rows.append({
                "timestamp": idx.strftime("%Y-%m-%d"),
                "open": float(val),
                "high": float(val),
                "low": float(val),
                "close": float(val),
                "volume": 0.0
            })
        return rows

    @staticmethod
    def _fetch_fly_historical(symbol: str, period: str) -> Optional[List[Dict]]:
        base_asset = symbol.split("_")[0]  # e.g., WTI, BRENT
        if base_asset.upper() == "BRENT":
            base_asset = "Brent"
            
        days = PriceFetcher._parse_period_days(period)
        df = PriceFetcher._query_historical_term_structure(base_asset, days)
        if df is None or df.empty:
            return None
            
        parts = symbol.split("_")
        if len(parts) >= 5 and parts[1] == "FLY":
            m1, m2, m3 = f"m{parts[2]}", f"m{parts[3]}", f"m{parts[4]}"
        else:
            m1, m2, m3 = "m1", "m2", "m3"

        if m1 not in df.columns or m2 not in df.columns or m3 not in df.columns:
            return None

        fly = df[m1] - 2 * df[m2] + df[m3]
        fly = fly.dropna()
        
        rows = []
        for idx, val in fly.items():
            rows.append({
                "timestamp": idx.strftime("%Y-%m-%d"),
                "open": float(val),
                "high": float(val),
                "low": float(val),
                "close": float(val),
                "volume": 0.0
            })
        return rows

    @staticmethod
    def _fetch_dfly_historical(symbol: str, period: str) -> Optional[List[Dict]]:
        base_asset = symbol.split("_")[0]  # e.g., WTI, BRENT
        if base_asset.upper() == "BRENT":
            base_asset = "Brent"
            
        days = PriceFetcher._parse_period_days(period)
        df = PriceFetcher._query_historical_term_structure(base_asset, days)
        if df is None or df.empty:
            return None
            
        parts = symbol.split("_")
        if len(parts) >= 6 and parts[1] == "DFLY":
            m1, m2, m3, m4 = f"m{parts[2]}", f"m{parts[3]}", f"m{parts[4]}", f"m{parts[5]}"
        else:
            m1, m2, m3, m4 = "m1", "m2", "m3", "m4"

        if m1 not in df.columns or m2 not in df.columns or m3 not in df.columns or m4 not in df.columns:
            return None

        dfly = (df[m1] - 2 * df[m2] + df[m3]) - (df[m2] - 2 * df[m3] + df[m4])
        dfly = dfly.dropna()
        
        rows = []
        for idx, val in dfly.items():
            rows.append({
                "timestamp": idx.strftime("%Y-%m-%d"),
                "open": float(val),
                "high": float(val),
                "low": float(val),
                "close": float(val),
                "volume": 0.0
            })
        return rows

    @staticmethod
    def _get_eod_from_15min_db(symbol: str) -> List[Dict]:
        try:
            import sqlite3
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.environ.get("BARS15_DB_PATH") or os.path.join(base_dir, "DB", "bars_15min_latest.db")
            if not os.path.exists(db_path):
                return []
            prefix = "CL" if symbol == "WTI" else ("CO" if symbol in ("Brent", "BRN") else None)
            if not prefix: return []
            
            conn = sqlite3.connect(db_path)
            tables = [t[0] for t in conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()]
            
            def parse_contract(t):
                suffix = t.split('_')[1]
                months = {'F':1, 'G':2, 'H':3, 'J':4, 'K':5, 'M':6, 'N':7, 'Q':8, 'U':9, 'V':10, 'X':11, 'Z':12}
                try:
                    return (int(suffix[1:]), months.get(suffix[0], 99))
                except:
                    return (99, 99)
            tables.sort(key=parse_contract)
            
            if not tables:
                return []
                
            # Find the active front-month contract by checking the max timestamp.
            # Skip tables with corrupt far-future timestamps (same guard as _fetch_live_db_price).
            from datetime import datetime, timedelta
            _now_ceil = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            table_max_ts = {}
            global_max = ""
            for t in tables:
                row = conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()
                if row and row[0]:
                    ts = row[0].replace("T", " ")[:19]
                    if ts > _now_ceil:
                        continue  # corrupt far-future timestamp — skip
                    table_max_ts[t] = row[0]
                    if row[0] > global_max:
                        global_max = row[0]

            active_index = 0
            if global_max:
                try:
                    clean_max = global_max.replace("T", " ")[:19]
                    max_dt = datetime.strptime(clean_max, "%Y-%m-%d %H:%M:%S")
                    cutoff_str = (max_dt - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    cutoff_str = global_max

                for i, t in enumerate(tables):
                    ts = table_max_ts.get(t, "")
                    clean_ts = ts.replace("T", " ")[:19]
                    if clean_ts >= cutoff_str:
                        active_index = i
                        break
                        
            front_month = tables[active_index]
            query = f"""
                SELECT DATE(timestamp) as d, 
                       (SELECT open FROM {front_month} t2 WHERE DATE(t2.timestamp) = DATE(t1.timestamp) ORDER BY t2.timestamp ASC LIMIT 1) as o,
                       MAX(high) as h,
                       MIN(low) as l,
                       (SELECT close FROM {front_month} t2 WHERE DATE(t2.timestamp) = DATE(t1.timestamp) ORDER BY t2.timestamp DESC LIMIT 1) as c,
                       SUM(volume) as v
                FROM {front_month} t1
                GROUP BY DATE(timestamp)
                ORDER BY d ASC
            """
            rows = conn.execute(query).fetchall()
            conn.close()
            
            result = []
            for r in rows:
                if r[0] >= "2026-06-12":
                    result.append({
                        "timestamp": r[0],
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": float(r[5]) if r[5] else 0.0
                    })
            return result
        except Exception as e:
            logger.error(f"Error fetching EOD from 15min DB: {e}")
            return []

    @staticmethod
    def _get_intraday_from_15min_db(symbol: str, bars: int = 180) -> List[Dict]:
        """Recent raw 15-min bars of the active front-month contract (WTI/Brent) for
        the intraday/spot chart. Same live DB as the daily EOD tail — not the stale
        Data/ parquet."""
        try:
            import sqlite3
            import os
            from datetime import datetime, timedelta
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.environ.get("BARS15_DB_PATH") or os.path.join(base_dir, "DB", "bars_15min_latest.db")
            if not os.path.exists(db_path):
                return []
            prefix = "CL" if symbol == "WTI" else ("CO" if symbol in ("Brent", "BRN") else None)
            if not prefix:
                return []
            conn = sqlite3.connect(db_path)
            tables = [t[0] for t in conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()]
            months = {'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
                      'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12}

            def parse_contract(t):
                suffix = t.split('_')[1]
                try:
                    return (int(suffix[1:]), months.get(suffix[0], 99))
                except Exception:
                    return (99, 99)

            tables.sort(key=parse_contract)
            if not tables:
                conn.close()
                return []

            _now_ceil = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            table_max_ts, global_max = {}, ""
            for t in tables:
                row = conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()
                if row and row[0]:
                    ts = row[0].replace("T", " ")[:19]
                    if ts > _now_ceil:
                        continue  # corrupt far-future timestamp
                    table_max_ts[t] = row[0]
                    if row[0] > global_max:
                        global_max = row[0]

            active_index = 0
            if global_max:
                try:
                    clean_max = global_max.replace("T", " ")[:19]
                    cutoff_str = (datetime.strptime(clean_max, "%Y-%m-%d %H:%M:%S")
                                  - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    cutoff_str = global_max
                for i, t in enumerate(tables):
                    if table_max_ts.get(t, "").replace("T", " ")[:19] >= cutoff_str:
                        active_index = i
                        break

            front = tables[active_index]
            rows = conn.execute(
                f"SELECT timestamp, open, high, low, close, volume FROM {front} "
                f"ORDER BY timestamp DESC LIMIT {int(bars)}"
            ).fetchall()
            conn.close()

            out = []
            for r in reversed(rows):
                try:
                    out.append({
                        "timestamp": str(r[0]).replace("T", " ")[:19],
                        "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
                        "close": float(r[4]), "volume": float(r[5]) if r[5] else 0.0,
                    })
                except Exception:
                    continue
            return out
        except Exception as e:
            logger.error(f"Error fetching intraday from 15min DB for {symbol}: {e}")
            return []

    @staticmethod
    def fetch_historical(symbol: str, period: str = "1mo") -> Optional[List[Dict]]:
        """Fetch historical OHLCV data from database first, then Yahoo Finance with fallback history generation."""
        if symbol in ["3-2-1CRACK", "CRACK_SPREAD", "GASCRACK", "DIESELCRACK", "GASOILCRACK"]:
            return PriceFetcher._fetch_crack_spread_historical(symbol, period)
        elif "_CAL_SPREAD" in symbol:
            return PriceFetcher._fetch_cal_spread_historical(symbol, period)
        elif "_DFLY" in symbol:
            return PriceFetcher._fetch_dfly_historical(symbol, period)
        elif "_FLY" in symbol:
            return PriceFetcher._fetch_fly_historical(symbol, period)

        if symbol in ["WTI", "Brent", "BRN"]:
            # WTI/Brent are DB-only by design — NO yfinance. History comes from
            # PriceHistory (daily, Data-folder derived) as the base layer, with
            # the 15-min candle DB providing the live EOD tail. Deduped by date.
            ph_symbol = "Brent" if symbol == "BRN" else symbol
            days = PriceFetcher._parse_period_days(period)
            by_date: Dict[str, Dict] = {}

            # 1) Base: daily history from PriceHistory.
            try:
                from database import SessionLocal
                from models import PriceHistory
                db = SessionLocal()
                ph_rows = (db.query(PriceHistory)
                             .filter(PriceHistory.symbol == ph_symbol)
                             .order_by(PriceHistory.date.desc())
                             .limit(days).all())
                db.close()
                for r in ph_rows:
                    by_date[r.date] = {"timestamp": r.date, "open": r.open, "high": r.high,
                                       "low": r.low, "close": r.close, "volume": r.volume}
            except Exception as db_err:
                logger.error(f"PriceHistory query failed for {symbol}: {db_err}")

            # 2) Live tail: EOD from the 15-min candle DB (overrides overlapping days).
            for bar in PriceFetcher._get_eod_from_15min_db(symbol):
                by_date[bar["timestamp"]] = bar

            merged = [by_date[d] for d in sorted(by_date.keys())]
            if days and len(merged) > days:
                merged = merged[-days:]
            return merged

        # Try database first
        try:
            from database import SessionLocal
            from models import PriceHistory
            db = SessionLocal()
            days = PriceFetcher._parse_period_days(period)
            results = db.query(PriceHistory).filter(PriceHistory.symbol == symbol).order_by(PriceHistory.date.desc()).limit(days).all()
            db.close()
            if results and len(results) >= min(days * 0.5, 5):
                results.reverse()
                return [
                    {
                        "timestamp": r.date,
                        "open": r.open,
                        "high": r.high,
                        "low": r.low,
                        "close": r.close,
                        "volume": r.volume
                    }
                    for r in results
                ]
        except Exception as db_err:
            logger.error(f"Error querying PriceHistory from db for {symbol}: {db_err}")
            
        if not USE_YFINANCE or symbol in ["WTI", "Brent", "BRN"]:
            if LOG_DATA_FETCHER_WARNINGS:
                logger.info(f"Skipping yfinance historical for {symbol}; disabled or local DB only")
            return None

        ticker_symbol = PriceFetcher.SYMBOLS.get(symbol)
        days = PriceFetcher._parse_period_days(period)

        # Use yfinance for historical series
        if ticker_symbol:
            try:
                # yfinance natively supports: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
                yf_period = period
                # normalize short daily ranges
                if period in ("1d", "5d"):
                    yf_period = "5d"

                ticker = yf.Ticker(ticker_symbol, session=_SESSION)
                hist = ticker.history(period=yf_period, interval="1d", actions=False)
                if hist is not None and not hist.empty:
                    rows = []
                    for idx, row in hist.iterrows():
                        try:
                            close = row.get("Close")
                            if close is None or (isinstance(close, float) and math.isnan(close)):
                                continue
                            open_p = row.get("Open") if row.get("Open") is not None and not (isinstance(row.get("Open"), float) and math.isnan(row.get("Open"))) else close
                            high = row.get("High") if row.get("High") is not None and not (isinstance(row.get("High"), float) and math.isnan(row.get("High"))) else close
                            low = row.get("Low") if row.get("Low") is not None and not (isinstance(row.get("Low"), float) and math.isnan(row.get("Low"))) else close
                            vol = row.get("Volume") if row.get("Volume") is not None and not (isinstance(row.get("Volume"), float) and math.isnan(row.get("Volume"))) else 0.0

                            open_p_val, high_val, low_val, close_val = float(open_p), float(high), float(low), float(close)

                            # Scale RBOB and HO from $/gallon to $/barrel
                            if symbol in ("RBOB", "HO"):
                                open_p_val *= 42.0
                                high_val *= 42.0
                                low_val *= 42.0
                                close_val *= 42.0

                            rows.append({
                                "timestamp": idx.strftime("%Y-%m-%d"),
                                "open": open_p_val,
                                "high": high_val,
                                "low": low_val,
                                "close": close_val,
                                "volume": float(vol),
                            })
                        except Exception:
                            continue
                    if rows:
                        return rows
            except Exception as e:
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"Error fetching historical {symbol} via yfinance: {e}")

        # Fallback for derived or when yfinance fails
        base_price = PriceFetcher._get_fallback_price(symbol)
        if base_price:
            logger.info(f"Using synthetic history for {symbol} due to yfinance failure.")
            return PriceFetcher._create_synthetic_history(symbol, base_price["close"], days)

        if LOG_DATA_FETCHER_WARNINGS:
            logger.warning(f"No historical data found for {symbol} (no fallback).")
        return None

    @staticmethod
    def fetch_intraday(symbol: str, limit: int = 500) -> Optional[List[Dict]]:
        """Fetch high-frequency intraday data (5m) from yfinance, falling back to local dataset engine."""
        # For spreads and flies, we don't have true intraday yfinance feeds yet. 
        # Fall back to returning the latest historical daily data point.
        if "CRACK" in symbol or "SPREAD" in symbol or "FLY" in symbol or "WTI-Brent" in symbol:
            hist = PriceFetcher.fetch_historical(symbol, period="1wk")
            if hist:
                return hist[-limit:]
            return None

        if symbol == "GO":
            return PriceFetcher.fetch_historical(symbol, period="1wk")

        # WTI/Brent: live 15-min bars from the candle DB (never yfinance).
        if symbol in ("WTI", "Brent", "BRN"):
            bars = PriceFetcher._get_intraday_from_15min_db(symbol, bars=max(limit, 180))
            if bars:
                return bars[-limit:]

        ticker_symbol = PriceFetcher.SYMBOLS.get(symbol)
        if ticker_symbol and USE_YFINANCE and symbol not in ["WTI", "Brent", "BRN"]:
            try:
                ticker = yf.Ticker(ticker_symbol, session=_SESSION)
                hist = ticker.history(period="5d", interval="5m", actions=False)
                if hist is not None and not hist.empty:
                    rows = []
                    for idx, row in hist.iterrows():
                        try:
                            close = row.get("Close")
                            if close is None or (isinstance(close, float) and math.isnan(close)):
                                continue
                            open_p = row.get("Open") if not math.isnan(row.get("Open")) else close
                            high = row.get("High") if not math.isnan(row.get("High")) else close
                            low = row.get("Low") if not math.isnan(row.get("Low")) else close
                            vol = row.get("Volume") if not math.isnan(row.get("Volume")) else 0.0

                            # Scale RBOB and HO from $/gallon to $/barrel for intraday too
                            if symbol in ("RBOB", "HO"):
                                close *= 42.0
                                open_p *= 42.0
                                high *= 42.0
                                low *= 42.0

                            rows.append({
                                "timestamp": idx.strftime("%Y-%m-%d %H:%M:%S"),
                                "open": float(open_p),
                                "high": float(high),
                                "low": float(low),
                                "close": float(close),
                                "volume": float(vol),
                            })
                        except Exception:
                            continue
                    if rows:
                        return rows[-limit:]
            except Exception as e:
                logger.warning(f"Error fetching intraday {symbol} via yfinance: {e}")

        # Fallback
        try:
            from services.dataset_engine import DatasetEngine
            return DatasetEngine.query_intraday_price(symbol, limit)
        except Exception as e:
            logger.error(f"Error fetching intraday fallback for {symbol}: {e}")
            return None
