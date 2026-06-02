import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_ZONES = [
    "ROTTERDAM",
    "SINGAPORE",
    "FUJAIRAH",
    "CUSHING",
    "LOOP",
]


def _load_zone_names() -> list[str]:
    zones = []
    for key in [
        "AIS_BOX_ROTTERDAM",
        "AIS_BOX_SINGAPORE",
        "AIS_BOX_FUJAIRAH",
        "AIS_BOX_CUSHING",
        "AIS_BOX_LOOP",
    ]:
        if os.getenv(key):
            zones.append(key.replace("AIS_BOX_", ""))

    return zones or DEFAULT_ZONES


def fetch_tanker_positions() -> dict:
    """Return AIS tanker positions, or placeholder offline state if unauthenticated."""
    api_key = os.getenv("AISSTREAM_KEY")
    zones = []
    zone_names = _load_zone_names()

    for zone_name in zone_names:
        zones.append({
            "zone": zone_name,
            "confirmed_tankers": 0,
            "total_vessels": 0,
            "vessels": [],
        })

    if not api_key:
        return {
            "status": "offline",
            "message": "AISSTREAM_KEY missing; AIS tanker watch disabled.",
            "zones": zones,
            "timestamp": datetime.now().isoformat(),
        }

    # Placeholder implementation until AIS websocket integration is added
    return {
        "status": "online",
        "message": "AIS key configured; real-time tanker tracking will be enabled once the AIS client is implemented.",
        "zones": zones,
        "timestamp": datetime.now().isoformat(),
    }
