"""Live AIS tanker tracking via aisstream.io WebSocket.

Subscribes to PositionReport + ShipStaticData messages inside bounding boxes
around the world's major oil-shipping hubs. Counts vessels currently in each
zone, split between anchored vs underway — the anchored count at hubs like
Singapore / Fujairah is a real-world proxy for floating storage / port
congestion that physical oil traders watch.

Free aisstream.io tier covers terrestrial receivers (~40 mi from shore).
That's enough for port congestion but won't see open-ocean floating storage
or mid-Atlantic transit traffic — that needs paid Kpler / Vortexa.

AIS ship type codes (ITU-R M.1371):
  70-79  cargo
  80-89  tanker (oil / chemical / gas / hazmat carriers)
  90-99  other"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Dict, Optional, Tuple

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except Exception:                              # pragma: no cover
    websockets = None
    ConnectionClosed = Exception   # type: ignore

AIS_WS_URL = "wss://stream.aisstream.io/v0/stream"

TANKER_TYPE_LO = 80
TANKER_TYPE_HI = 89

# AIS navigational status codes considered "stationary" — anchored, moored,
# or aground. A tanker sitting at one of these for hours at a major hub is
# either waiting to discharge (port congestion) or being used as floating
# storage. Both are bullish-supply-side signals.
ANCHORED_STATUSES = {1, 5, 6}

# Drop vessel records older than this. Tankers move slowly, so a 90-min
# stale window catches everything currently parked in a zone without
# showing ghosts from old position reports.
STALE_AFTER_SECONDS = 90 * 60

# Major oil-shipping zones — (south_lat, west_lon, north_lat, east_lon).
# Boxes are TIGHT around the actual petroleum terminals + anchorage zones,
# NOT around the broad metropolitan area. Earlier wide boxes caught all
# container/ferry/fishing traffic too, producing ~3000 vessels for
# Rotterdam (impossible — real Rotterdam tanker activity is ~50-150 ships).
# Coordinates verified from port-authority charts (Maasvlakte, Houston
# Ship Channel, Singapore EOPL anchorage, Fujairah outer anchorage).
ZONES: Dict[str, Tuple[float, float, float, float]] = {
    # Houston Ship Channel + Galveston Bay anchorage + offshore lightering
    "Houston/Galveston": (29.00, -95.10, 29.85, -94.50),
    # LOOP single-buoy mooring, ~22mi offshore Grand Isle LA (small area)
    "LOOP (US Gulf)":    (28.80, -90.10, 28.95, -89.95),
    # Rotterdam: Maasvlakte/Europoort/Botlek/Pernis petroleum cluster +
    # offshore tanker anchorage zone, EXCLUDING Antwerp + North Sea transit
    "Rotterdam/ARA":     (51.85, 3.50, 52.30, 4.50),
    # Singapore Eastern + Western Outer Port Limits tanker anchorages
    "Singapore/Malacca": (1.10, 103.55, 1.45, 104.25),
    # Fujairah Outer Anchorage (one of world's largest bunkering/storage hubs)
    "Fujairah":          (25.05, 56.35, 25.40, 56.75),
    # Curacao/Aruba/Venezuela coast — refining + crude export terminals
    "Caribbean (Vz/Cu)": (11.70, -70.40, 12.20, -68.75),
    # Saldanha Bay crude terminal (South Africa) + offshore mooring
    "Saldanha Bay":      (-33.10, 17.85, -32.95, 18.10),
}


def _zone_of(lat: float, lon: float) -> Optional[str]:
    for name, (s, w, n, e) in ZONES.items():
        if s <= lat <= n and w <= lon <= e:
            return name
    return None


class TankerTracker:
    """Long-running WebSocket consumer + rolling vessel buffer."""

    def __init__(self) -> None:
        self.vessels: Dict[int, Dict] = {}     # MMSI -> latest position record
        self.types: Dict[int, int] = {}        # MMSI -> ship_type (tankers only)
        self.status = "pending first connection"
        self.connected_since: Optional[float] = None
        self.messages_seen = 0
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    # ----- network loop ---------------------------------------------------
    async def run(self, api_key: str) -> None:
        """Keep a WS connection open, reconnecting with exponential backoff."""
        if not api_key:
            self.status = "disabled (no AIS_API_KEY set)"
            return
        if websockets is None:
            self.status = "disabled (websockets lib not installed)"
            return

        sub = {
            "APIKey": api_key,
            "BoundingBoxes": [[[s, w], [n, e]]
                              for (s, w, n, e) in ZONES.values()],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }
        backoff = 4
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                        AIS_WS_URL, ping_interval=30,
                        close_timeout=5) as ws:
                    self.connected_since = time.time()
                    self.status = "live (aisstream.io)"
                    await ws.send(json.dumps(sub))
                    backoff = 4
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        with contextlib.suppress(Exception):
                            self._handle(json.loads(raw))
            except ConnectionClosed:
                self.status = "reconnecting (ws closed)"
            except Exception as ex:
                self.status = f"reconnecting ({type(ex).__name__})"
            self.connected_since = None
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                break                          # stop() called during sleep
            except asyncio.TimeoutError:
                pass
            backoff = min(60, backoff * 2)
        self.status = "stopped"

    # ----- message handling ----------------------------------------------
    def _handle(self, msg: dict) -> None:
        self.messages_seen += 1
        mtype = msg.get("MessageType")
        meta = msg.get("MetaData") or {}
        mmsi = meta.get("MMSI")
        if not isinstance(mmsi, int):
            return
        body = msg.get("Message") or {}
        if mtype == "ShipStaticData":
            sd = body.get("ShipStaticData") or {}
            st = sd.get("Type")
            if isinstance(st, int) and TANKER_TYPE_LO <= st <= TANKER_TYPE_HI:
                self.types[mmsi] = st
            return
        if mtype != "PositionReport":
            return
        pr = body.get("PositionReport") or {}
        lat = pr.get("Latitude")
        lon = pr.get("Longitude")
        if lat is None:
            lat = meta.get("latitude")
        if lon is None:
            lon = meta.get("longitude")
        if lat is None or lon is None:
            return
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            return
        zone = _zone_of(lat_f, lon_f)
        if zone is None:
            return
        nav = pr.get("NavigationalStatus")
        self.vessels[mmsi] = {
            "zone": zone,
            "lat": lat_f,
            "lon": lon_f,
            "anchored": nav in ANCHORED_STATUSES,
            "nav": nav,
            "name": (meta.get("ShipName") or "").strip(),
            "sog": pr.get("Sog"),
            "ts": time.time(),
        }

    # ----- snapshot for the dashboard ------------------------------------
    def _purge_stale(self) -> None:
        cutoff = time.time() - STALE_AFTER_SECONDS
        for mmsi, v in list(self.vessels.items()):
            if v["ts"] < cutoff:
                del self.vessels[mmsi]

    def snapshot(self) -> Dict:
        """Per-zone tanker tallies suitable for direct JSON serialisation."""
        self._purge_stale()
        zones: Dict[str, Dict] = {
            name: {"total": 0, "anchored": 0, "underway": 0,
                   "confirmed_tankers": 0, "unknown_type": 0,
                   "samples": []}
            for name in ZONES
        }
        for mmsi, v in self.vessels.items():
            z = zones[v["zone"]]
            z["total"] += 1
            if v["anchored"]:
                z["anchored"] += 1
            else:
                z["underway"] += 1
            if mmsi in self.types:
                z["confirmed_tankers"] += 1
            else:
                z["unknown_type"] += 1
            if len(z["samples"]) < 5:
                z["samples"].append({
                    "name": v["name"] or f"MMSI {mmsi}",
                    "anchored": v["anchored"],
                    "sog": (round(float(v["sog"]), 1)
                            if v.get("sog") is not None else None),
                    "lat": round(v["lat"], 3),
                    "lon": round(v["lon"], 3),
                    "ts": round(v["ts"]),
                })
        totals = {
            "vessels_in_zones": len(self.vessels),
            "tanker_types_known": len(self.types),
            "messages_seen": self.messages_seen,
        }
        return {
            "status": self.status,
            "connected_since": self.connected_since,
            "totals": totals,
            "zones": zones,
        }
