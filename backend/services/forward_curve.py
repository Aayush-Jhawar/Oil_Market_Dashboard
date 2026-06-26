"""
forward_curve.py — WTI futures forward-curve fetcher
=====================================================
Builds a 12-month WTI term-structure by fetching the next 12 consecutive
expiry-month contract tickers from Yahoo Finance.

Yahoo Finance WTI ticker format:  CL{month_code}{2-digit-year}.NYM
Month codes:  F=Jan G=Feb H=Mar J=Apr K=May M=Jun N=Jul Q=Aug U=Sep V=Oct X=Nov Z=Dec

The helper is intentionally standalone (no circular imports) and caches its
result for CACHE_TTL seconds so repeated WebSocket ticks are cheap.
"""
from __future__ import annotations

import logging
import math
import time
import threading
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import yfinance as yf
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
_MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

CACHE_TTL = 120          # seconds between full re-fetches
MAX_MONTHS = 12          # M1 through M12
FETCH_TIMEOUT = 8        # seconds per yfinance call
MAX_CURVE_WORKERS = 4    # cap concurrent contract-month fetches (pool/rate-limit safety)

# Shared browser-like session with a sized connection pool so concurrent
# contract-month fetches don't trigger urllib3 "Connection pool is full" warnings.
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
})
_ADAPTER = requests.adapters.HTTPAdapter(
    pool_connections=MAX_CURVE_WORKERS * 2,
    pool_maxsize=MAX_CURVE_WORKERS * 4,
    max_retries=0,
)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_cache_ts: Dict[str, float] = {}
_cache_data: Dict[str, List[Dict]] = {}          # {symbol: [{month, label, ticker, price, change_pct}, ...]}
_cache_meta: Dict[str, Dict] = {}                # {symbol: {structure, m1_m12_spread, fetched_at, ...}}


# ---------------------------------------------------------------------------
# Ticker helpers
# ---------------------------------------------------------------------------
def _contract_ticker(symbol: str, year: int, month: int) -> str:
    """Return the Yahoo Finance ticker for a specific contract month."""
    if symbol == "GO":
        return "SKIP"
        
    code = _MONTH_CODES[month]
    yy = str(year)[-2:]
    
    prefixes = {
        "WTI": "CL",
        "Brent": "BZ",
        "RBOB": "RB",
        "HO": "HO",
        "NG": "NG",
        "HH": "NG",
    }
    prefix = prefixes.get(symbol, "CL")
    
    # For NYMEX products
    if symbol in ["WTI", "RBOB", "HO", "NG", "HH"]:
        return f"{prefix}{code}{yy}.NYM"
    else:
        # ICE or others, try without .NYM
        return f"{prefix}{code}{yy}"

def _next_n_contract_months(symbol: str = "WTI", n: int = MAX_MONTHS) -> List[Tuple[int, int, str]]:
    """
    Return the next *n* contract months as (year, month, ticker).

    Contracts expire on the 3rd business day before the 25th of the
    month prior to delivery.  For UI display purposes, we simply advance
    forward from the current calendar month and skip none (the front month
    is treated as the month after *today* to avoid expired tickers).
    """
    today = date.today()
    results: List[Tuple[int, int, str]] = []
    y, m = today.year, today.month
    
    # Contracts expire the month prior to delivery. 
    # If today is in month M, M's contract has already expired.
    # The front contract is M+1 (if day < 20) or M+2 (if day >= 20).
    m += 1
    if today.day >= 20:
        m += 1
        
    if m > 12:
        m -= 12
        y += 1
        if m > 12: # Handle the case where today is late Dec (m=14 -> 2)
            m -= 12
            y += 1
            
    for _ in range(n):
        ticker = _contract_ticker(symbol, y, m)
        results.append((y, m, ticker))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return results


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------
def _fetch_last_price(ticker_symbol: str) -> Optional[float]:
    """Return the most recent close price for *ticker_symbol*, or None."""
    try:
        t = yf.Ticker(ticker_symbol, session=_SESSION)
        # 5d with 15m resolution gives us the freshest intraday print
        hist = t.history(period="5d", interval="15m", actions=False)
        if hist is None or hist.empty:
            hist = t.history(period="5d", interval="1d", actions=False)
        if hist is None or hist.empty:
            return None
        close_col = hist.get("Close", hist.get("close"))
        if close_col is None:
            return None
        closes = close_col.dropna()
        if closes.empty:
            return None
        val = float(closes.iloc[-1])
        return val if not math.isnan(val) else None
    except Exception as exc:
        logger.debug(f"forward_curve: {ticker_symbol} → {exc}")
        return None


def _fetch_prev_close(ticker_symbol: str) -> Optional[float]:
    """Return the second-to-last close (for change_pct), or None."""
    try:
        t = yf.Ticker(ticker_symbol, session=_SESSION)
        hist = t.history(period="5d", interval="1d", actions=False)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna() if "Close" in hist.columns else hist["close"].dropna()
        if len(closes) < 2:
            return None
        return float(closes.iloc[-2])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _curve_from_candle_db(symbol: str) -> List[Dict]:
    """Build the M1..M14 forward curve for WTI/Brent from the live 15-min candle
    DB, where every contract month is its own CL_*/CO_* table. This keeps the
    curve (and the spreads/flies derived from it) in lockstep with the latest
    synced candles. Returns [] if the DB/symbol is unavailable."""
    try:
        import sqlite3
        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.environ.get("BARS15_DB_PATH") or os.path.join(base_dir, "DB", "bars_15min_latest.db")
        prefix = "CL" if symbol == "WTI" else ("CO" if symbol in ("Brent", "BRN") else None)
        if not prefix or not os.path.exists(db_path):
            return []
        months = {'F': 1, 'G': 2, 'H': 3, 'J': 4, 'K': 5, 'M': 6,
                  'N': 7, 'Q': 8, 'U': 9, 'V': 10, 'X': 11, 'Z': 12}

        def _key(t):
            s = t.split('_')[1]
            try:
                return (int(s[1:]), months.get(s[0], 99))
            except Exception:
                return (99, 99)

        # Bounded busy_timeout so the price/curve hot path degrades to [] rather
        # than blocking if a writer (db-sync merge) momentarily holds the lock.
        conn = sqlite3.connect(db_path, timeout=3)
        conn.execute("PRAGMA busy_timeout=3000")
        tabs = sorted(
            (t[0] for t in conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()),
            key=_key,
        )
        
        # Find global max timestamp to determine active M1
        table_max_ts = {}
        global_max = ""
        for t in tabs:
            row = conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()
            if row and row[0]:
                ts = row[0]
                table_max_ts[t] = ts
                if ts > global_max:
                    global_max = ts
                    
        active_index = 0
        if global_max:
            from datetime import datetime, timedelta
            try:
                clean_max = global_max.replace("T", " ")[:19]
                max_dt = datetime.strptime(clean_max, "%Y-%m-%d %H:%M:%S")
                cutoff_str = (max_dt - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
            except:
                cutoff_str = global_max

            for i, t in enumerate(tabs):
                ts = table_max_ts.get(t, "")
                clean_ts = ts.replace("T", " ")[:19]
                if clean_ts >= cutoff_str:
                    active_index = i
                    break
                    
        points = []
        active_tabs = tabs[active_index:active_index + 14]
        for i, t in enumerate(active_tabs):
            row = conn.execute(f"SELECT close FROM {t} ORDER BY timestamp DESC LIMIT 1").fetchone()
            if row and row[0]:
                points.append({"month": f"M{i + 1}", "label": t.split('_')[1],
                               "ticker": t, "price": round(float(row[0]), 4), "change_pct": 0.0})
        conn.close()
        return points
    except Exception as e:
        logger.error(f"Error building {symbol} curve from candle DB: {e}")
        return []


def fetch_forward_curve(symbol: str = "WTI", force: bool = False) -> Tuple[List[Dict], Dict]:
    """
    Return (curve_points, meta) for the M1–M12 forward curve of the given symbol.

    curve_points — list of dicts:
        { month: "M1", label: "Jun-25", ticker: "CLM25.NYM",
          price: 78.42, change_pct: -0.31 }

    meta — summary dict:
        { structure: "BACKWARDATION"|"CONTANGO"|"FLAT",
          m1_m12_spread: -1.24,
          m1_price: 78.42,
          m12_price: 77.18,
          fetched_at: "2025-06-05T...",
          ok: True }
    """
    global _cache_ts, _cache_data, _cache_meta

    now = time.time()
    with _CACHE_LOCK:
        ts = _cache_ts.get(symbol, 0.0)
        cached_data = _cache_data.get(symbol, [])
        cached_meta = _cache_meta.get(symbol, {})
        if not force and cached_data and (now - ts) < CACHE_TTL:
            return list(cached_data), dict(cached_meta)

    contract_months = _next_n_contract_months(symbol, MAX_MONTHS)
    curve_points: List[Dict] = []

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_month_data(idx: int, year: int, month: int, ticker: str) -> Optional[Dict]:
        if symbol in ["WTI", "Brent", "BRN"]:
            return None

        label = f"{_MONTH_NAMES[month]}-{str(year)[-2:]}"
        mkey = f"M{idx + 1}"

        price = _fetch_last_price(ticker)
        if price is None:
            # Try the generic front-month ticker as ultimate fallback for M1
            if idx == 0:
                fallback_tickers = {
                    "WTI": "CL=F",
                    "Brent": "BZ=F",
                    "RBOB": "RB=F",
                    "HO": "HO=F",
                    "NG": "NG=F",
                    "HH": "NG=F"
                }
                fallback = fallback_tickers.get(symbol, "CL=F")
                price = _fetch_last_price(fallback)
            if price is None:
                logger.debug(f"forward_curve: no price for {ticker} ({mkey}); skipping")
                return None

        prev = _fetch_prev_close(ticker)

        # Apply canonical scaling for products
        if symbol in ("RBOB", "HO"):
            price *= 42.0
            if prev is not None:
                prev *= 42.0

        change_pct = round(((price - prev) / prev) * 100, 3) if prev and prev != 0 else 0.0

        return {
            "idx": idx,
            "month": mkey,
            "label": label,
            "ticker": ticker,
            "price": round(price, 4),
            "change_pct": change_pct,
        }

    results = []
    with ThreadPoolExecutor(max_workers=MAX_CURVE_WORKERS) as executor:
        futures = [
            executor.submit(_fetch_month_data, idx, year, month, ticker)
            for idx, (year, month, ticker) in enumerate(contract_months)
        ]
        for future in as_completed(futures):
            res = future.result()
            if res is not None:
                results.append(res)
                
    # Sort results back into their original M1-M12 order
    results.sort(key=lambda x: x.pop("idx"))
    curve_points = results

    # WTI/Brent: build the curve straight from the live candle DB term structure.
    if symbol in ["WTI", "Brent", "BRN"]:
        candle_curve = _curve_from_candle_db(symbol)
        if candle_curve:
            curve_points = candle_curve

    # Fallback extrapolation: DB-only symbols, failed yfinance, or empty candle DB.
    if (symbol in ["WTI", "Brent", "BRN"] and not curve_points) or len(curve_points) <= 1:
        try:
            import sqlite3
            import os
            db_path = os.path.join(os.path.dirname(__file__), '..', 'energy.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            sym_query = "WTI" if symbol == "WTI" else "Brent"
            row = conn.execute(f"SELECT * FROM historical_term_structure WHERE symbol='{sym_query}' ORDER BY timestamp DESC LIMIT 1").fetchone()
            if row:
                m1_price = curve_points[0]["price"] if curve_points else row["m1"]
                curve_points = []
                for i in range(1, MAX_MONTHS + 1):
                    mkey = f"M{i}"
                    val = row[f"m{i}"]
                    if val is not None:
                        # Align with the current M1 price if it changed recently
                        aligned_val = val
                        if row["m1"] and m1_price:
                            aligned_val = m1_price - (row["m1"] - val)
                        curve_points.append({
                            "month": mkey,
                            "label": f"DB-M{i}",
                            "ticker": f"{sym_query.upper()}_DB_{mkey}",
                            "price": round(aligned_val, 4),
                            "change_pct": 0.0
                        })
        except Exception as e:
            logger.error(f"Error fetching {symbol} curve from DB: {e}")

    # Build meta
    m1_price = curve_points[0]["price"] if curve_points else None
    m12_price = curve_points[-1]["price"] if len(curve_points) >= 12 else (
        curve_points[-1]["price"] if curve_points else None
    )
    spread = round(m12_price - m1_price, 4) if m1_price and m12_price else None

    if spread is None:
        structure = "UNKNOWN"
    elif spread < -0.05:
        structure = "BACKWARDATION"
    elif spread > 0.05:
        structure = "CONTANGO"
    else:
        structure = "FLAT"

    meta = {
        "structure": structure,
        "m1_m12_spread": spread,
        "m1_price": m1_price,
        "m12_price": m12_price,
        "months_fetched": len(curve_points),
        "fetched_at": datetime.now().isoformat(),
        "ok": len(curve_points) >= 2,
    }

    with _CACHE_LOCK:
        _cache_ts[symbol] = time.time()
        _cache_data[symbol] = curve_points
        _cache_meta[symbol] = meta

    logger.info(
        f"forward_curve: fetched {len(curve_points)} months for {symbol} | "
        f"{structure} | M1={m1_price} M12={m12_price} spread={spread}"
    )
    return curve_points, meta


def get_curve_as_dict(symbol: str = "WTI") -> Dict[str, float]:
    """Return {M1: price, M2: price, ...} — used by the WebSocket snapshot."""
    points, _ = fetch_forward_curve(symbol)
    return {p["month"]: p["price"] for p in points}


def get_butterfly(symbol: str = "WTI", m3_idx: int = 2, m6_idx: int = 5, m9_idx: int = 8) -> Optional[float]:
    """Compute the M3-2*M6+M9 butterfly value from the cached curve."""
    points, _ = fetch_forward_curve(symbol)
    prices = [p["price"] for p in points]
    if len(prices) <= m9_idx:
        return None
    return round(prices[m3_idx] - 2 * prices[m6_idx] + prices[m9_idx], 4)
