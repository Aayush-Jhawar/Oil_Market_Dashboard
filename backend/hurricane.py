import logging
import math
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

NHC_CURRENT_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
REFINERY_ASSETS = [
    {"name": "Phillips 66 Lake Charles", "lat": 30.2230, "lon": -93.2512, "capacity_mbpd": 0.34},
    {"name": "ExxonMobil Beaumont", "lat": 29.9025, "lon": -94.0208, "capacity_mbpd": 0.56},
    {"name": "Valero Port Arthur", "lat": 29.8394, "lon": -93.9356, "capacity_mbpd": 0.30},
    {"name": "Chevron Pascagoula", "lat": 30.3450, "lon": -88.5229, "capacity_mbpd": 0.33},
    {"name": "Motiva Norco", "lat": 29.9490, "lon": -90.2164, "capacity_mbpd": 0.24},
]


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in nautical miles."""
    radius_km = 6371.0
    nm_per_km = 0.539957
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius_km * c * nm_per_km


def _parse_storm_entry(entry: dict) -> dict:
    name = entry.get("stormName") or entry.get("name") or entry.get("storm_id") or entry.get("id") or "unknown"
    lat = None
    lon = None
    wind = None
    category = entry.get("category") or entry.get("type") or "unknown"

    if "lat" in entry and "lon" in entry:
        lat = float(entry["lat"])
        lon = float(entry["lon"])
    elif "latitude" in entry and "longitude" in entry:
        lat = float(entry["latitude"])
        lon = float(entry["longitude"])
    elif "position" in entry and isinstance(entry["position"], dict):
        lat = float(entry["position"].get("lat", 0.0))
        lon = float(entry["position"].get("lon", 0.0))
    elif "geometry" in entry and isinstance(entry["geometry"], dict):
        coords = entry["geometry"].get("coordinates")
        if coords and len(coords) >= 2:
            lon = float(coords[0])
            lat = float(coords[1])

    if "wind_kt" in entry:
        wind = float(entry["wind_kt"])
    elif "windSpeed" in entry:
        wind = float(entry["windSpeed"])
    elif "maxWindKts" in entry:
        wind = float(entry["maxWindKts"])

    if lat is None or lon is None:
        return None

    return {
        "name": name,
        "category": category,
        "lat": lat,
        "lon": lon,
        "wind_kt": wind if wind is not None else 0,
    }


def _normalize_data(payload: dict) -> list:
    if not payload:
        return []

    if isinstance(payload, list):
        return payload

    if "storms" in payload and isinstance(payload["storms"], list):
        return payload["storms"]

    if "activeStorms" in payload and isinstance(payload["activeStorms"], list):
        return payload["activeStorms"]

    if "cyclones" in payload and isinstance(payload["cyclones"], list):
        return payload["cyclones"]

    if "features" in payload and isinstance(payload["features"], list):
        items = []
        for feature in payload["features"]:
            if isinstance(feature, dict):
                props = feature.get("properties", {})
                geom = feature.get("geometry", {})
                if geom and isinstance(geom, dict) and "coordinates" in geom:
                    props["geometry"] = geom
                items.append(props)
        return items

    if "data" in payload and isinstance(payload["data"], list):
        return payload["data"]

    if "storm" in payload:
        return [payload["storm"]]

    return [payload]


def fetch_active_storms() -> dict:
    """Fetch active tropical storms from NOAA NHC and evaluate refinery risk."""
    try:
        response = requests.get(NHC_CURRENT_STORMS_URL, timeout=15)
        response.raise_for_status()
        data = response.json()

        raw_storms = _normalize_data(data)
        storms = []
        total_capacity = 0.0

        for entry in raw_storms:
            parsed = _parse_storm_entry(entry)
            if not parsed:
                continue

            at_risk = []
            for refinery in REFINERY_ASSETS:
                distance_nm = round(_haversine_nm(parsed["lat"], parsed["lon"], refinery["lat"], refinery["lon"]), 1)
                if distance_nm <= 150:
                    at_risk.append({
                        "name": refinery["name"],
                        "capacity_mbpd": refinery["capacity_mbpd"],
                        "distance_nm": distance_nm,
                    })
                    total_capacity += refinery["capacity_mbpd"]

            storms.append({
                **parsed,
                "at_risk_refineries": at_risk,
            })

        season_active = datetime.utcnow().month in range(6, 12 + 1)
        return {
            "source": NHC_CURRENT_STORMS_URL,
            "storms": storms,
            "total_at_risk_capacity_mbpd": round(total_capacity, 2),
            "season_active": season_active,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error fetching storms: {e}")
        return {
            "source": NHC_CURRENT_STORMS_URL,
            "storms": [],
            "total_at_risk_capacity_mbpd": 0.0,
            "season_active": datetime.utcnow().month in range(6, 12 + 1),
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
