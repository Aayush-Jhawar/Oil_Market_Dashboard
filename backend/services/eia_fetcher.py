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
        "cushing_level": "PET.WCUSSTUS1.W",
        "gasoline_stocks": "PET.WGTSTUS1.W",
        "distillate_stocks": "PET.WDISTUS1.W",
        "spr_level": "PET.WCSSTUS1.W",
        "us_crude_production": "PET.WCRFPUS2.W",
        "refinery_utilization": "PET.WPULEUS2.W",
        "crude_imports": "PET.WCRIMUS2.W",
        "crude_exports": "PET.WCREXUS2.W",
    }

    @staticmethod
    def get_fallback_data(series_id: str) -> Dict:
        """Return fallback data when API fails"""
        fallback_values = {
            "PET.WCRSTUS1.W": 410.0,  # Million barrels
            "PET.WCUSSTUS1.W": 28.0,
            "PET.WGTSTUS1.W": 215.0,
            "PET.WDISTUS1.W": 110.0,
            "PET.WCSSTUS1.W": 410.0,  # SPR
            "PET.WCRFPUS2.W": 13.2,  # Million bbl/day
            "PET.WPULEUS2.W": 92.5,  # Percent
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

    @staticmethod
    def fetch_series(series_id: str, api_key: Optional[str] = None) -> Optional[Dict]:
        """Fetch a single EIA series"""
        api_key = api_key or os.getenv("EIA_API_KEY")

        if not api_key:
            logger.error("EIA_API_KEY not set; returning no data (no fallback)")
            return None

        try:
            url = f"{EIAFetcher.BASE_URL}/seriesid/{series_id}"
            params = {
                "api_key": api_key,
                "frequency": "weekly",
                "length": 52,
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("data"):
                latest = data["response"]["data"][0]
                prev = data["response"]["data"][1] if len(data["response"]["data"]) > 1 else None

                wow_change = None
                if prev:
                    wow_change = float(latest[0]) - float(prev[0])

                return {
                    "series_id": series_id,
                    "current_value": float(latest[0]),
                    "current_date": latest[1],
                    "wow_change": wow_change,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error fetching EIA series {series_id}: {e}")
            return None

    @staticmethod
    def fetch_all_eia_data(api_key: Optional[str] = None) -> Dict[str, Dict]:
        """Fetch all EIA series"""
        eia_data = {}

        for name, series_id in EIAFetcher.SERIES.items():
            data = EIAFetcher.fetch_series(series_id, api_key)
            # Only include series where we successfully fetched data
            if data is not None:
                eia_data[name] = data

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

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("data"):
                result = []
                for item in data["response"]["data"]:
                    result.append({
                        "date": item[1],
                        "value": float(item[0]),
                    })
                return result

        except Exception as e:
            logger.error(f"Error fetching weekly history for {series_id}: {e}")
            return None

    @staticmethod
    def calculate_5yr_avg(
        series_id: str, api_key: Optional[str] = None
    ) -> Optional[float]:
        """Calculate 5-year average for comparison"""
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

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("response", {}).get("data"):
                values = [float(item[0]) for item in data["response"]["data"]]
                return sum(values) / len(values) if values else None

        except Exception as e:
            logger.error(f"Error calculating 5yr avg for {series_id}: {e}")

        return None
