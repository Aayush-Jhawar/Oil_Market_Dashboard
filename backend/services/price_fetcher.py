import logging
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import quote

import yfinance as yf
import requests

# Import environment configuration
try:
    from config import USE_YFINANCE, LOG_DATA_FETCHER_WARNINGS
except ImportError:
    USE_YFINANCE = True
    LOG_DATA_FETCHER_WARNINGS = True

logger = logging.getLogger(__name__)


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

        # Crack Spreads (calculated from components)
        "3-2-1CRACK": None,      # Calculated: 3*Brent - 2*RBOB - 1*HO
        "2-1-1CRACK": None,      # Calculated: 2*Brent - 1*RBOB - 1*HO
        "GASCRACK": None,        # Calculated: RBOB - WTI
        "DIESELCRACK": None,     # Calculated: HO - WTI
        "FRAC": None,            # Calculated: HO - HH
        "WCS-WTI": None,         # Derived differential proxy
        
        # Natural Gas
        "HH": "NG=F",            # Henry Hub Natural Gas

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
        "RBOB": {"symbol": "RBOB", "open": 200.0, "high": 205.0, "low": 195.0, "close": 202.5, "volume": 0, "change_pct": 0.0},
        "HO": {"symbol": "HO", "open": 230.0, "high": 235.0, "low": 225.0, "close": 232.0, "volume": 0, "change_pct": 0.0},
        "JET": {"symbol": "JET", "open": 155.0, "high": 158.0, "low": 152.0, "close": 156.5, "volume": 0, "change_pct": 0.0},
        "GO": {"symbol": "GO", "open": 700.0, "high": 710.0, "low": 690.0, "close": 705.0, "volume": 0, "change_pct": 0.0},
        "HH": {"symbol": "HH", "open": 3.4, "high": 3.5, "low": 3.3, "close": 3.41, "volume": 0, "change_pct": 0.0},
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
    def fetch_symbol(symbol: str, period: str = "1d") -> Optional[Dict]:
        """
        Fetch OHLCV data for a symbol
        period: '1d', '5d', '1mo', '3mo'
        """
        try:
            ticker_symbol = PriceFetcher.SYMBOLS.get(symbol)
            if ticker_symbol is None:
                return PriceFetcher.fetch_derived_symbol(symbol)

            price = PriceFetcher._fetch_price_from_ticker(symbol, ticker_symbol)
            if price is None:
                logger.warning(f"No data for {symbol}")
                return None
            return price
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

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
        if not USE_YFINANCE:
            if LOG_DATA_FETCHER_WARNINGS:
                logger.info(f"Skipping yfinance for {symbol} ({ticker_symbol}); using fallback data")
            return None

        try:
            ticker = yf.Ticker(ticker_symbol)

            max_retries = 3
            backoff = [1, 2, 4]
            hist = None
            for attempt in range(max_retries):
                try:
                    hist = ticker.history(period="5d", interval="15m", actions=False)
                    if hist is None or getattr(hist, "empty", True):
                        hist = ticker.history(period="5d", actions=False)
                    if hist is not None and not getattr(hist, "empty", True):
                        break
                    raise ValueError("empty history result")
                except Exception as e:
                    if LOG_DATA_FETCHER_WARNINGS:
                        logger.warning(
                            f"yfinance history fetch attempt {attempt+1}/{max_retries} failed for {symbol} ({ticker_symbol}): {e}"
                        )
                    if attempt < max_retries - 1:
                        time.sleep(backoff[attempt])
                    else:
                        if LOG_DATA_FETCHER_WARNINGS:
                            logger.error(
                                f"yfinance: giving up fetching history for {symbol} ({ticker_symbol}) after {max_retries} attempts: {e}"
                            )
                        return None

            if hist is None or getattr(hist, "empty", True):
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"No yfinance history for {symbol} ({ticker_symbol})")
                return None

            if "Close" not in hist.columns:
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"Unexpected yfinance response for {symbol} ({ticker_symbol}); missing Close")
                return None

            row = hist.iloc[-1]
            if row is None or row.empty:
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"No valid price row for {symbol} ({ticker_symbol})")
                return None

            close = row.get("Close")
            if close is None or (isinstance(close, float) and math.isnan(close)):
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"Invalid close price for {symbol} ({ticker_symbol})")
                return None

            open_price = row.get("Open")
            high = row.get("High")
            low = row.get("Low")
            volume = row.get("Volume")

            close = float(close)
            open_price = float(open_price) if open_price is not None and not (isinstance(open_price, float) and math.isnan(open_price)) else close
            high = float(high) if high is not None and not (isinstance(high, float) and math.isnan(high)) else close
            low = float(low) if low is not None and not (isinstance(low, float) and math.isnan(low)) else close
            volume = float(volume) if volume is not None and not (isinstance(volume, float) and math.isnan(volume)) else 0.0

            prev_close = None
            if len(hist.dropna(subset=["Close"])) > 1:
                prev_close = hist.dropna(subset=["Close"]).iloc[-2].get("Close")
                prev_close = float(prev_close) if prev_close is not None else None

            delta_pct = ((close - prev_close) / prev_close) * 100 if prev_close and prev_close != 0 else 0.0
            timestamp = row.name
            if not hasattr(timestamp, "isoformat"):
                timestamp = datetime.now()

            return {
                "symbol": symbol,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "change_pct": float(delta_pct),
                "timestamp": timestamp.isoformat(),
            }
        except Exception as e:
            if LOG_DATA_FETCHER_WARNINGS:
                logger.warning(f"yfinance fetch failed for {symbol} ({ticker_symbol}): {e}")
            return None

    @staticmethod
    def fetch_all_prices() -> Dict[str, Dict]:
        """Fetch all primary product prices using yfinance, with fallback to DEFAULT_PRICES."""
        symbol_to_ticker = {
            symbol: ticker for symbol, ticker in PriceFetcher.SYMBOLS.items() if ticker is not None
        }
        prices = {}

        for symbol, ticker_symbol in symbol_to_ticker.items():
            quote = PriceFetcher._fetch_price_from_ticker(symbol, ticker_symbol)
            if quote:
                prices[symbol] = quote
            else:
                # Fallback to DEFAULT_PRICES when yfinance fails or is disabled
                fallback = PriceFetcher._get_fallback_price(symbol)
                if fallback:
                    prices[symbol] = fallback

        for derived_symbol in ["DUBAICRUDE", "WCS-WTI"]:
            if derived_symbol not in prices:
                derived_price = PriceFetcher.fetch_derived_symbol(derived_symbol, prices=prices)
                if derived_price:
                    prices[derived_symbol] = derived_price

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
    def fetch_historical(symbol: str, period: str = "1mo") -> Optional[List[Dict]]:
        """Fetch historical OHLCV data from Yahoo Finance with fallback history generation."""
        
        if not USE_YFINANCE:
            if LOG_DATA_FETCHER_WARNINGS:
                logger.info(f"Skipping yfinance historical for {symbol}; using fallback")
            return None

        ticker_symbol = PriceFetcher.SYMBOLS.get(symbol)
        days = PriceFetcher._parse_period_days(period)

        # Use yfinance for historical series
        if ticker_symbol:
            try:
                yf_period = period
                # normalize short daily ranges
                if period in ("1d", "5d"):
                    yf_period = "5d"

                ticker = yf.Ticker(ticker_symbol)
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

                            rows.append({
                                "timestamp": idx.strftime("%Y-%m-%d"),
                                "open": float(open_p),
                                "high": float(high),
                                "low": float(low),
                                "close": float(close),
                                "volume": float(vol),
                            })
                        except Exception:
                            continue
                    if rows:
                        return rows
            except Exception as e:
                if LOG_DATA_FETCHER_WARNINGS:
                    logger.warning(f"Error fetching historical {symbol} via yfinance: {e}")

        # No fallback: if we couldn't fetch historical data, return None
        if LOG_DATA_FETCHER_WARNINGS:
            logger.warning(f"No historical data found for {symbol} (no fallback).")
        return None
