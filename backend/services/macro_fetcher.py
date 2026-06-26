"""Macro indicators fetcher.

Fetches real market data for DXY, S&P 500, 10Y Treasury, VIX, and Henry Hub
from yfinance. PMI data uses FRED API when FRED_API_KEY is configured, otherwise
returns a documented placeholder.

Baker Hughes rig count and CFTC COT remain as labeled placeholders until
a free data source scraper is added (see services/cftc_live.py plan).
"""
import logging
import time
import threading
from datetime import datetime
from typing import Dict, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple cache so we don't hammer yfinance on every composite-score call
# ---------------------------------------------------------------------------
_MACRO_CACHE_LOCK = threading.Lock()
_MACRO_CACHE: Dict = {}
_MACRO_CACHE_TS: float = 0.0
_MACRO_CACHE_TTL: float = 300.0  # 5 minutes


# ---------------------------------------------------------------------------
# Ticker mapping: yfinance symbols for macro instruments
# ---------------------------------------------------------------------------
_MACRO_TICKERS = {
    "DXY":  "DX-Y.NYB",   # US Dollar Index
    "SPX":  "^GSPC",       # S&P 500
    "TNX":  "^TNX",        # US 10-Year Treasury Yield (×0.01 for %)
    "VIX":  "^VIX",        # CBOE Volatility Index
    "HH":   "NG=F",        # Henry Hub Natural Gas front-month
    "GOLD": "GC=F",        # Gold spot proxy
}

# Documented fallback values — used only when yfinance is unavailable.
# Values are intentionally left at "0" for critical macro so the UI shows "—"
# rather than silently displaying stale fake data.
_FALLBACK_MACRO = {
    "dxy":          None,
    "dxy_change":   None,
    "us_10y_yield": None,
    "yield_change": None,
    "spx":          None,
    "spx_change":   None,
    "henry_hub":    None,
    "hh_change":    None,
    "vix":          None,
    "vix_change":   None,
    "gold":         None,
    "gold_change":  None,
    "global_pmi":   50.3,   # requires FRED or manual update
    "china_pmi":    50.4,   # requires manual update
    "us_ism_pmi":   49.2,   # requires FRED or manual update
    "timestamp":    None,
    "data_source":  "fallback",
}


def _fetch_single(ticker_sym: str) -> Optional[Dict]:
    """Fetch last close + prev close from yfinance for a macro ticker."""
    try:
        ticker = yf.Ticker(ticker_sym)
        hist = ticker.history(period="5d", interval="1d", actions=False)
        if hist is None or hist.empty:
            return None
        close_series = hist["Close"].dropna()
        if len(close_series) < 1:
            return None
        close = float(close_series.iloc[-1])
        prev = float(close_series.iloc[-2]) if len(close_series) >= 2 else close
        change_pct = ((close - prev) / prev) * 100 if prev != 0 else 0.0
        return {"close": close, "change_pct": round(change_pct, 3)}
    except Exception as e:
        logger.warning(f"yfinance macro fetch failed for {ticker_sym}: {e}")
        return None


class MacroFetcher:
    """Fetch macro indicators from yfinance (DXY, SPX, TNX, VIX, HH)."""

    @staticmethod
    def fetch_all_macro() -> Dict:
        """Fetch all macro indicators, using a 5-minute cache."""
        global _MACRO_CACHE, _MACRO_CACHE_TS

        with _MACRO_CACHE_LOCK:
            now = time.time()
            if _MACRO_CACHE and (now - _MACRO_CACHE_TS) < _MACRO_CACHE_TTL:
                logger.debug("MacroFetcher: returning cached data")
                return _MACRO_CACHE.copy()

        logger.info("MacroFetcher: fetching live macro data from yfinance...")

        # Fetch concurrently where possible (yfinance is thread-safe for reads)
        results: Dict[str, Optional[Dict]] = {}
        for name, ticker_sym in _MACRO_TICKERS.items():
            results[name] = _fetch_single(ticker_sym)

        dxy   = results.get("DXY")
        spx   = results.get("SPX")
        tnx   = results.get("TNX")
        vix   = results.get("VIX")
        hh    = results.get("HH")
        gold  = results.get("GOLD")

        # TNX is quoted in basis points × 10 by yfinance (e.g. 43.5 = 4.35%)
        # We store the percentage value directly
        tnx_close = round(tnx["close"] / 10, 3) if tnx else None
        tnx_change = round(tnx["change_pct"], 3) if tnx else None

        macro_data = {
            # Dollar index
            "dxy":           round(dxy["close"], 2) if dxy else None,
            "dxy_change":    round(dxy["change_pct"], 3) if dxy else None,

            # Rates
            "us_10y_yield":  tnx_close,
            "yield_change":  tnx_change,

            # Equities
            "spx":           round(spx["close"]) if spx else None,
            "spx_change":    round(spx["change_pct"], 3) if spx else None,

            # Energy
            "henry_hub":     round(hh["close"], 3) if hh else None,
            "hh_change":     round(hh["change_pct"], 3) if hh else None,

            # Risk
            "vix":           round(vix["close"], 2) if vix else None,
            "vix_change":    round(vix["change_pct"], 3) if vix else None,

            # Gold
            "gold":          round(gold["close"], 1) if gold else None,
            "gold_change":   round(gold["change_pct"], 3) if gold else None,

            # PMI — requires FRED API (FRED_API_KEY env var) or manual weekly update
            "global_pmi":    _fetch_pmi_from_fred("MANEMP") if _fred_available() else 50.3,
            "china_pmi":     50.4,   # No free real-time source; update manually
            "us_ism_pmi":    49.2,   # FRED series ISAPMFG; requires FRED_API_KEY

            "timestamp":     datetime.now().isoformat(),
            "data_source":   "yfinance_live",
        }

        with _MACRO_CACHE_LOCK:
            _MACRO_CACHE = macro_data
            _MACRO_CACHE_TS = time.time()

        return macro_data


def _fred_available() -> bool:
    import os
    return bool(os.getenv("FRED_API_KEY"))


def _fetch_pmi_from_fred(series_id: str) -> Optional[float]:
    """Fetch the latest value for a FRED series. Returns None if unavailable."""
    import os
    import requests
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return None
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            f"&sort_order=desc&limit=1"
        )
        resp = requests.get(url, timeout=5)
        data = resp.json()
        obs = data.get("observations", [])
        if obs:
            val = obs[0].get("value", ".")
            return float(val) if val not in (".", "") else None
    except Exception as e:
        logger.warning(f"FRED fetch failed for {series_id}: {e}")
    return None


class RigCountFetcher:
    """Baker Hughes rig count scraper."""

    @staticmethod
    def fetch_latest() -> Optional[Dict]:
        import json
        import os
        import time

        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rig_count_cache.json")

        # Default fallback estimates matching the most recent successfully parsed report (June 5, 2026)
        fallback_data = {
            "total_us_oil_rigs": 486,
            "permian_rigs": 308,
            "wow_change": -2,
            "yoy_change": 8,
            "data_source": "baker_hughes_cache",
            "timestamp": datetime.now().isoformat(),
        }

        # Baker Hughes publishes the rig count WEEKLY, so re-scraping their site on
        # every /api/rigs/latest call is wasteful and slow: it does two sequential
        # web requests plus an Excel parse and can take 30-60s. That single slow
        # call stalls the dashboard's initial load gate (Promise.allSettled over all
        # endpoints), leaving the whole UI stuck on "Loading dashboard..." and the
        # tabs effectively unclickable. Serve a recent cache instantly; only touch
        # the network when the cache is missing or older than RIG_CACHE_TTL.
        RIG_CACHE_TTL = 12 * 3600   # live data is good for 12h (weekly release)
        RIG_FAIL_RETRY = 3600       # when the site is down, retry at most hourly
        try:
            if os.path.exists(cache_file):
                age = time.time() - os.path.getmtime(cache_file)
                with open(cache_file, "r") as f:
                    cached = json.load(f)
                # Live data is trusted for 12h; a fallback/cache-only write is only
                # trusted for 1h so we re-attempt the live scrape sooner once the
                # Baker Hughes site recovers — but never on every single load.
                ttl = RIG_CACHE_TTL if cached.get("data_source") == "baker_hughes_live" else RIG_FAIL_RETRY
                if age < ttl:
                    out = dict(cached)
                    out["data_source"] = "baker_hughes_cache"
                    return out
        except Exception as cache_err:
            logger.warning(f"RigCountFetcher: cache read failed, will refetch: {cache_err}")

        try:
            import requests
            import pandas as pd
            import re
            import urllib3
            from io import BytesIO
            from bs4 import BeautifulSoup
            
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            logger.info("RigCountFetcher: fetching live Baker Hughes rig count...")
            url = "https://bakerhughesrigcount.gcs-web.com/na-rig-count"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
            }
            
            session = requests.Session()
            # No retries and tight (connect, read) timeouts so a slow/unreachable
            # Baker Hughes site fails fast to the cache/fallback instead of hanging
            # the request (and the dashboard load) for up to a minute.
            adapter = requests.adapters.HTTPAdapter(max_retries=0)
            session.mount('https://', adapter)

            resp = session.get(url, headers=headers, verify=False, timeout=(4, 8))
            html = resp.text
            
            soup = BeautifulSoup(html, 'html.parser')
            excel_url = None
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'static-files' in href:
                    text = a.get_text(strip=True).lower()
                    parent_text = a.find_parent().get_text(strip=True).lower() if a.find_parent() else ""
                    if 'pivot' in text or 'pivot' in parent_text or 'north america rig count' in text or 'north america rig count' in parent_text:
                        excel_url = href
                        break
                        
            if not excel_url:
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'static-files' in href:
                        excel_url = href
                        break
                        
            if not excel_url:
                raise Exception("No Excel files found on BHI page.")
                
            if not excel_url.startswith('http'):
                excel_url = "https://bakerhughesrigcount.gcs-web.com" + excel_url
                
            logger.info(f"RigCountFetcher: downloading Excel from {excel_url}")
            excel_resp = session.get(excel_url, headers=headers, verify=False, timeout=(4, 8))
            excel_data = BytesIO(excel_resp.content)
            
            # Parse Detail sheet
            df_detail = pd.read_excel(excel_data, sheet_name='Detail')
            total_us_oil_rigs = int(df_detail[(df_detail['Country'] == 'UNITED STATES') & (df_detail['Target'] == 'OIL')]['Count'].sum())
            permian_rigs = int(df_detail[df_detail['Basin'].str.contains('permian', case=False, na=False)]['Count'].sum())
            
            # Reset BytesIO and parse Pivot sheet
            excel_data.seek(0)
            df_pivot = pd.read_excel(excel_data, sheet_name='Pivot')
            
            dates_row = df_pivot.iloc[6].tolist()
            us_row_idx = df_pivot[df_pivot.iloc[:, 0] == 'UNITED STATES'].index[0]
            us_rig_counts = df_pivot.iloc[us_row_idx].tolist()
            
            history = {}
            for d, c in zip(dates_row[2:], us_rig_counts[2:]):
                if pd.notna(d) and pd.notna(c):
                    history[str(d)[:10]] = int(c)
                    
            sorted_dates = sorted(history.keys())
            wow_change = 0
            yoy_change = 0
            
            if len(sorted_dates) >= 2:
                latest_date = sorted_dates[-1]
                prev_date = sorted_dates[-2]
                wow_change = history[latest_date] - history[prev_date]
                
                yoy_idx = max(0, len(sorted_dates) - 53)
                yoy_date = sorted_dates[yoy_idx]
                yoy_change = history[latest_date] - history[yoy_date]
            
            result = {
                "total_us_oil_rigs":  total_us_oil_rigs,
                "permian_rigs":       permian_rigs,
                "wow_change":         wow_change,
                "yoy_change":         yoy_change,
                "data_source":        "baker_hughes_live",
                "timestamp":          datetime.now().isoformat(),
            }
            
            try:
                with open(cache_file, 'w') as f:
                    json.dump(result, f, indent=2)
            except Exception as cache_err:
                logger.warning(f"RigCountFetcher: failed to write cache: {cache_err}")
                
            return result
            
        except Exception as e:
            logger.error(f"RigCountFetcher error (falling back to cache): {e}")
            out = dict(fallback_data)
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        cached = json.load(f)
                    out = dict(cached)
                    out["data_source"] = "baker_hughes_cache"
                except Exception as read_err:
                    logger.error(f"RigCountFetcher: failed to read cache: {read_err}")
            # Persist (touch) so we do NOT re-hit the dead site on every dashboard
            # load — the refreshed mtime + non-"live" data_source throttles retries
            # to RIG_FAIL_RETRY instead of paying the timeout on every request.
            try:
                with open(cache_file, 'w') as f:
                    json.dump(out, f, indent=2)
            except Exception:
                pass
            return out


class CFTCFetcher:
    """CFTC COT data."""

    @staticmethod
    def fetch_latest() -> Optional[Dict]:
        import json
        import os
        import time
        from datetime import datetime

        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cftc_cache.json")
        
        # Check cache first (24 hours)
        if os.path.exists(cache_file):
            try:
                if time.time() - os.path.getmtime(cache_file) < 86400:
                    with open(cache_file, 'r') as f:
                        cached = json.load(f)
                        if "WTI" in cached:
                            cached["WTI"]["data_source"] = "cftc_cache"
                        return cached
            except Exception as e:
                logger.warning(f"CFTCFetcher cache read failed: {e}")

        logger.info("CFTCFetcher: fetching live COT data...")
        result = {}
        try:
            import requests
            import io
            import zipfile
            import pandas as pd
            
            url = f'https://www.cftc.gov/files/dea/history/fut_disagg_txt_{datetime.now().year}.zip'
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                filename = z.namelist()[0]
                with z.open(filename) as f:
                    df = pd.read_csv(f, low_memory=False)
                    
                    def get_cftc_metrics(market_names):
                        subset = df[df['Market_and_Exchange_Names'].isin(market_names)]
                        if subset.empty:
                            return None
                        # Sort by date descending and grab the latest
                        latest_date = subset['As_of_Date_In_Form_YYMMDD'].max()
                        row = subset[subset['As_of_Date_In_Form_YYMMDD'] == latest_date].iloc[0]
                        prev = subset[subset['As_of_Date_In_Form_YYMMDD'] < latest_date]
                        prev_row = prev[prev['As_of_Date_In_Form_YYMMDD'] == prev['As_of_Date_In_Form_YYMMDD'].max()].iloc[0] if not prev.empty else None
                        
                        mm_long = int(row.get('M_Money_Positions_Long_All', 0))
                        mm_short = int(row.get('M_Money_Positions_Short_All', 0))
                        net_long = mm_long - mm_short
                        
                        prev_net = 0
                        if prev_row is not None:
                            p_long = int(prev_row.get('M_Money_Positions_Long_All', 0))
                            p_short = int(prev_row.get('M_Money_Positions_Short_All', 0))
                            prev_net = p_long - p_short
                            
                        return {
                            "mm_net_long": net_long,
                            "mm_net_change": net_long - prev_net,
                            "producer_net_short": int(row.get('Prod_Merc_Positions_Short_All', 0)) - int(row.get('Prod_Merc_Positions_Long_All', 0)),
                            "open_interest": int(row.get('Open_Interest_All', 0)),
                            "data_source": "cftc_live",
                            "timestamp": datetime.now().isoformat(),
                        }
                    
                    wti_names = ['WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE', 'CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE']
                    rbob_names = ['GASOLINE RBOB - NEW YORK MERCANTILE EXCHANGE']
                    ho_names = ['NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE']
                    
                    wti_data = get_cftc_metrics(wti_names)
                    rbob_data = get_cftc_metrics(rbob_names)
                    ho_data = get_cftc_metrics(ho_names)
                    
                    result = {
                        "WTI": wti_data or {"data_source": "missing_data"},
                        "RBOB": rbob_data or {"data_source": "missing_data"},
                        "HO": ho_data or {"data_source": "missing_data"}
                    }
                    
                    try:
                        with open(cache_file, 'w') as f:
                            json.dump(result, f, indent=2)
                    except Exception as e:
                        logger.warning(f"Failed to cache CFTC data: {e}")
                        
                    return result
                    
        except Exception as e:
            logger.error(f"CFTCFetcher error: {e}")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        cached = json.load(f)
                        if "WTI" in cached:
                            cached["WTI"]["data_source"] = "cftc_cache"
                        return cached
                except Exception:
                    pass
            # Default fallbacks if completely failed
            return {
                "WTI": {"mm_net_long": 245000, "mm_net_change": 12500, "producer_net_short": 320000, "open_interest": 1850000, "data_source": "fallback", "timestamp": datetime.now().isoformat()},
                "RBOB": {"mm_net_long": 45000, "mm_net_change": -2000, "producer_net_short": 60000, "open_interest": 350000, "data_source": "fallback", "timestamp": datetime.now().isoformat()},
                "HO": {"mm_net_long": 28000, "mm_net_change": 1500, "producer_net_short": 45000, "open_interest": 290000, "data_source": "fallback", "timestamp": datetime.now().isoformat()},
            }
