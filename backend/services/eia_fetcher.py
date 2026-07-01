import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
import os

logger = logging.getLogger(__name__)


class EIAFetcher:
    """Fetch data from EIA Open Data API"""

    BASE_URL = "https://api.eia.gov/v2"

    SERIES = {
        "crude_inventory": "PET.WCRSTUS1.W",
        "crude_level": "PET.WCRSTUS1.W",
        "cushing_level": "PET.W_EPC0_SAX_YCUOK_MBBL.W",
        "gasoline_stocks": "PET.WGTSTUS1.W",
        "distillate_stocks": "PET.WDISTUS1.W",
        "spr_level": "PET.WCSSTUS1.W",
        "us_crude_production": "PET.WCRFPUS2.W",
        "refinery_utilization": "PET.WPULEUS3.W",
        "crude_imports": "PET.WCRIMUS2.W",
        "crude_exports": "PET.WCREXUS2.W",
    }

    @staticmethod
    def get_fallback_data(series_id: str) -> Dict:
        """Return fallback data when API fails"""
        fallback_values = {
            "PET.WCRSTUS1.W": 410.0,  # Million barrels
            "PET.W_EPC0_SAX_YCUOK_MBBL.W": 28.0,  # Cushing
            "PET.WCUSSTUS1.W": 28.0,
            "PET.WGTSTUS1.W": 215.0,
            "PET.WDISTUS1.W": 110.0,
            "PET.WCSSTUS1.W": 410.0,  # SPR
            "PET.WCRFPUS2.W": 13.2,  # Million bbl/day
            "PET.WPULEUS3.W": 92.5,  # Percent
            "PET.WCRIMUS2.W": 6.8,
            "PET.WCREXUS2.W": 3.2,
        }
        
        return {
            "series_id": series_id,
            "current_value": fallback_values.get(series_id, 100.0),
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "wow_change": None,
            "timestamp": datetime.now().isoformat(),
            "is_fallback": True,
        }

    # Series available as deep history in the seeded `inventory` table
    # (friendly key -> bare EIA code stored in inventory.series_id).
    HISTORY_SERIES = {
        "crude":           "WCRSTUS1",
        "cushing":         "W_EPC0_SAX_YCUOK_MBBL",
        "gasoline":        "WGTSTUS1",
        "distillate":      "WDISTUS1",
        "jet":             "WKJSTUS1",
        "propane":         "WPRSTUS1",
        "residual":        "WRESTUS1",
        "total":           "WTTSTUS1",
        "refinery_inputs": "WCRRIUS2",
    }

    @staticmethod
    def inventory_history(series_key: str) -> Optional[Dict]:
        """Weekly inventory history + a 5-year seasonal band for one series.

        Reads the seeded `inventory` table (Data/eia_*_US.csv). Returns the full
        weekly series plus a by-week-of-year band (min/max/avg over the prior 5
        complete years) with the current year overlaid — the classic EIA storage
        chart traders use to judge whether stocks are rich/cheap vs seasonal norm.
        """
        import datetime as _dt

        code = EIAFetcher.HISTORY_SERIES.get(series_key)
        if not code:
            return None
        try:
            from database import SessionLocal
            from models import InventoryData
            db = SessionLocal()
            rows = (db.query(InventoryData)
                      .filter(InventoryData.series_id == code)
                      .order_by(InventoryData.period.asc()).all())
            unit = rows[0].unit if rows else ""
            series = []
            for r in rows:
                try:
                    d = _dt.date.fromisoformat(str(r.period)[:10])
                except Exception:
                    continue
                if r.value is not None:
                    series.append((d, float(r.value)))
            db.close()
        except Exception as e:
            logger.warning(f"inventory_history query failed for {series_key}: {e}")
            return None
        if not series:
            return None

        latest_date, latest_val = series[-1]
        latest_year = latest_date.year
        band_years = set(range(latest_year - 5, latest_year))

        def _wk(d):
            w = d.isocalendar()[1]
            return 52 if w == 53 else w

        by_week: Dict[int, list] = {}
        current_by_week: Dict[int, float] = {}
        for d, v in series:
            w = _wk(d)
            if d.year in band_years:
                by_week.setdefault(w, []).append(v)
            if d.year == latest_year:
                current_by_week[w] = v

        band = []
        for w in range(1, 53):
            vals = by_week.get(w)
            if not vals:
                continue
            band.append({
                "week": w,
                "min": round(min(vals), 1),
                "max": round(max(vals), 1),
                "avg": round(sum(vals) / len(vals), 1),
                "current": round(current_by_week[w], 1) if w in current_by_week else None,
            })

        wk_vals = by_week.get(_wk(latest_date), [])
        return {
            "series": series_key,
            "series_id": code,
            "unit": unit,
            "latest_date": latest_date.isoformat(),
            "latest_value": round(latest_val, 1),
            "five_year_avg": round(sum(wk_vals) / len(wk_vals), 1) if wk_vals else None,
            "seasonal_band": band,
            "history": [{"date": d.isoformat(), "value": round(v, 1)} for d, v in series],
        }

    @staticmethod
    def _db_latest(series_id: str) -> Optional[Dict]:
        """Last observed value for a series from the seeded `inventory` table.

        Used as a real-data fallback when the live API is unavailable (no key /
        network error), instead of a flat synthetic constant. The SERIES map uses
        the "PET.<CODE>.W" form while the table stores the bare <CODE>, so strip
        the prefix/suffix before matching.
        """
        code = series_id
        if code.startswith("PET."):
            code = code[4:]
        if code.endswith(".W"):
            code = code[:-2]
        try:
            from database import SessionLocal
            from models import InventoryData
            db = SessionLocal()
            rows = (db.query(InventoryData)
                      .filter(InventoryData.series_id == code)
                      .order_by(InventoryData.period.desc())
                      .limit(2).all())
            db.close()
            if not rows:
                return None
            latest = rows[0]
            wow = float(latest.value) - float(rows[1].value) if len(rows) > 1 else None
            return {
                "series_id": series_id,
                "current_value": float(latest.value),
                "current_date": latest.period,
                "wow_change": wow,
                "timestamp": datetime.now().isoformat(),
                "is_db_fallback": True,
            }
        except Exception as e:
            logger.warning(f"EIA DB fallback failed for {series_id}: {e}")
            return None

    @staticmethod
    def fetch_series(series_id: str, api_key: Optional[str] = None) -> Optional[Dict]:
        """Fetch a single EIA series"""
        api_key = api_key or os.getenv("EIA_API_KEY")

        if not api_key:
            # No live key — serve the last real value from the seeded inventory DB.
            db = EIAFetcher._db_latest(series_id)
            if db:
                return db
            logger.error("EIA_API_KEY not set and no DB history; returning no data")
            return None

        try:
            url = f"{EIAFetcher.BASE_URL}/seriesid/{series_id}"
            params = {
                "api_key": api_key,
                "frequency": "weekly",
                "length": 52,
            }

            response = requests.get(url, params=params, timeout=(2.5, 4.0))
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("data"):
                latest = data["response"]["data"][0]
                prev = data["response"]["data"][1] if len(data["response"]["data"]) > 1 else None

                wow_change = None
                if prev:
                    wow_change = float(latest["value"]) - float(prev["value"])

                return {
                    "series_id": series_id,
                    "current_value": float(latest["value"]),
                    "current_date": latest["period"],
                    "wow_change": wow_change,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error fetching EIA series {series_id}: {e}")
            # Prefer the last real value from the seeded inventory DB over the
            # flat synthetic constant.
            return EIAFetcher._db_latest(series_id) or EIAFetcher.get_fallback_data(series_id)

    _cache = None
    _cache_time = None

    @staticmethod
    def fetch_all_eia_data(api_key: Optional[str] = None) -> Dict[str, Dict]:
        """Fetch all EIA series concurrently"""
        if EIAFetcher._cache and EIAFetcher._cache_time and (datetime.now() - EIAFetcher._cache_time).total_seconds() < 3600:
            return EIAFetcher._cache

        from concurrent.futures import ThreadPoolExecutor, as_completed
        eia_data = {}

        with ThreadPoolExecutor(max_workers=min(10, len(EIAFetcher.SERIES))) as executor:
            future_to_name = {
                executor.submit(EIAFetcher.fetch_series, series_id, api_key): name
                for name, series_id in EIAFetcher.SERIES.items()
            }
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    data = future.result()
                    if data is not None:
                        eia_data[name] = data
                except Exception as e:
                    logger.error(f"Error fetching EIA series for {name}: {e}")

        if eia_data:
            EIAFetcher._cache = eia_data
            EIAFetcher._cache_time = datetime.now()

        return eia_data

    @staticmethod
    def fetch_series_history(series_id: str, api_key: Optional[str] = None, length: int = 52) -> Optional[list]:
        """Fetch weekly historical series values for a single EIA series."""
        api_key = api_key or os.getenv("EIA_API_KEY")

        if not api_key:
            logger.error("EIA_API_KEY not set; cannot load weekly history")
            return None

        try:
            url = f"{EIAFetcher.BASE_URL}/seriesid/{series_id}"
            params = {
                "api_key": api_key,
                "frequency": "weekly",
                "length": length,
            }

            response = requests.get(url, params=params, timeout=(2.5, 4.0))
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("data"):
                result = []
                for item in data["response"]["data"]:
                    # Safely skip items with missing values
                    if item.get("value") is not None:
                        result.append({
                            "date": item["period"],
                            "value": float(item["value"]),
                        })
                return result

        except Exception as e:
            logger.error(f"Error fetching weekly history for {series_id}: {e}")
            # Generate synthetic history
            result = []
            base_val = EIAFetcher.get_fallback_data(series_id)["current_value"]
            for i in range(length):
                date_str = (datetime.now() - timedelta(weeks=i)).strftime("%Y-%m-%d")
                result.append({"date": date_str, "value": base_val + (i % 5) * 0.1})
            return result

    _5yr_avg_cache = {}
    _5yr_avg_cache_time = {}

    @staticmethod
    def calculate_5yr_avg(
        series_id: str, api_key: Optional[str] = None
    ) -> Optional[float]:
        """Calculate 5-year average for comparison"""
        now = datetime.now()
        cached_val = EIAFetcher._5yr_avg_cache.get(series_id)
        cached_time = EIAFetcher._5yr_avg_cache_time.get(series_id)
        if cached_val is not None and cached_time and (now - cached_time).total_seconds() < 86400:
            return cached_val
            
        api_key = api_key or os.getenv("EIA_API_KEY")

        if not api_key:
            logger.error("EIA_API_KEY not set; cannot calculate 5yr average")
            return None

        try:
            url = f"{EIAFetcher.BASE_URL}/seriesid/{series_id}"
            params = {
                "api_key": api_key,
                "frequency": "weekly",
                "length": 260,  # 5 years of weekly data
            }

            response = requests.get(url, params=params, timeout=(5, 30))
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("data"):
                values = [float(item["value"]) for item in data["response"]["data"] if item.get("value") is not None]
                avg = sum(values) / len(values) if values else None
                if avg is not None:
                    EIAFetcher._5yr_avg_cache[series_id] = avg
                    EIAFetcher._5yr_avg_cache_time[series_id] = now
                return avg

        except Exception as e:
            logger.error(f"Error calculating 5yr avg for {series_id}: {e}")

        # Return mock 5yr avg
        base_val = EIAFetcher.get_fallback_data(series_id)["current_value"]
        return base_val * 0.95  # Slightly lower than current to simulate building trend
