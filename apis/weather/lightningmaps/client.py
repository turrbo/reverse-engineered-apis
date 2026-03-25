"""
LightningMaps / Blitzortung API Client
=======================================
Reverse-engineered Python client for LightningMaps.org and Blitzortung.org APIs.

Discovered endpoints:
  - WebSocket (real-time): wss://live.lightningmaps.org/ and wss://live2.lightningmaps.org/
  - XHR fallback (real-time): https://live.lightningmaps.org/l/ and https://live2.lightningmaps.org/l/
  - Stations JSON: https://www.lightningmaps.org/blitzortung/{region}/index.php?stations_json
  - Lightning tiles: https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&t={type}
  - Archive tiles: https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&from=...&to=...
  - Map tiles: https://map.lightningmaps.org/{style}/{z}/{x}/{y}.png
  - Radar tiles: https://map.lightningmaps.org/radar/{z}/{x}/{y}.png
  - Archive map images: https://images.lightningmaps.org/blitzortung/{region}/index.php?map=...&date=...
  - Mini map images: https://images.lightningmaps.org/blitzortung/{region}/index.php?map={id}
  - Mini animations: https://images.lightningmaps.org/blitzortung/{region}/index.php?animation={id}
  - Country borders: https://www.lightningmaps.org/geo.json
  - Signal graphs: https://images.lightningmaps.org/blitzortung/{region}/index.php?bo_graph&...

IMPORTANT NOTICE:
  Lightning data is copyright by Blitzortung.org contributors. This data is intended for
  entertainment/educational purposes only. Commercial usage is forbidden.
  Contact: info@blitzortung.org

Usage:
    # Real-time WebSocket streaming
    client = LightningMapsClient()
    for stroke in client.stream_realtime():
        print(stroke)

    # XHR polling (fallback)
    client = LightningMapsClient()
    strokes = client.poll_realtime()

    # Get stations
    stations = client.get_stations('europe')

    # Get archive map image
    img_bytes = client.get_archive_map_image('europe', '20260324')
"""

import json
import time
import ssl
import threading
import logging
from datetime import datetime, timezone
from typing import Generator, Optional, Callable, Dict, List, Any, Tuple
from urllib.parse import urlencode

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False

try:
    import websocket
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIGHTNINGMAPS_DOMAIN = "lightningmaps.org"

# WebSocket servers (load-balanced, both equivalent)
WS_SERVERS = [
    "wss://live.lightningmaps.org/",
    "wss://live2.lightningmaps.org/",
]

# XHR fallback servers
XHR_SERVERS = [
    "https://live.lightningmaps.org/l/",
    "https://live2.lightningmaps.org/l/",
]

# Region -> path mapping for stations and image APIs
REGIONS = {
    "europe": "europe",
    "america": "america",
    "oceania": "oceania",
}

# Tiles server
TILES_BASE = "https://tiles.lightningmaps.org/"

# Map tiles server
MAP_BASE = "https://map.lightningmaps.org"

# Image/archive server
IMAGES_BASE = "https://images.lightningmaps.org/blitzortung"

# Stations JSON base
STATIONS_BASE = "https://www.lightningmaps.org/blitzortung"

# Geo JSON (country borders)
GEO_JSON_URL = "https://www.lightningmaps.org/geo.json"

# Lightning tile types
TILE_TYPE_1H = 5     # Last ~1 hour (default)
TILE_TYPE_24H = 6    # Last ~24 hours

# Data source bitmask values (used in 'a' parameter for subscription filter)
# NOTE: These are bitmask values for the 'a' field in WebSocket/XHR requests.
# The 'src' field in each stroke dict is a separate integer value (1, 2, etc.)
# that represents the computing server / data pipeline that processed the stroke.
SRC_BLITZORTUNG = 2   # Official Blitzortung.org data (blue on map)
SRC_LIGHTNINGMAPS = 4  # LightningMaps.org experimental data (yellow on map)
SRC_TESTING = 8        # Testing/experimental data

# Stroke 'src' field values (as seen in actual server responses)
# src=1 and src=2 both appear in WebSocket batches when a=6
# The 'flags' dict in the batch message maps src_id -> some status value
STROKE_SRC_NAMES = {
    1: "LM",   # LightningMaps.org source
    2: "BO",   # Blitzortung.org source
    4: "LM4",  # LightningMaps.org alt source
}

# Protocol version
PROTOCOL_VERSION = 24

# WebSocket challenge: response = (k * 3604) % 7081 * timestamp_ms / 100
WS_CHALLENGE_MULT = 3604
WS_CHALLENGE_MOD = 7081

# Default headers to mimic browser
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Origin": "https://www.lightningmaps.org",
    "Referer": "https://www.lightningmaps.org/",
}


# ---------------------------------------------------------------------------
# Data classes (plain dicts used for simplicity, see field docs below)
# ---------------------------------------------------------------------------

def describe_stroke(stroke: Dict[str, Any]) -> str:
    """
    Stroke dict fields:
      time   (int)   - Unix timestamp in milliseconds (nanosecond precision)
      lat    (float) - Latitude in decimal degrees
      lon    (float) - Longitude in decimal degrees
      src    (int)   - Data source: 2=Blitzortung, 4=LightningMaps experimental
      srv    (int)   - Server ID that processed the stroke
      id     (int)   - Unique stroke ID within its source
      del    (int)   - Detection delay in milliseconds (time to compute location)
      dev    (int)   - Deviation / accuracy estimate in meters
      sta    (dict)  - Station participation map: {station_id: status_bitmask}
                       (only present when stations=True in WebSocket request)
                       status: bit 0=assigned, bit 1=calc used, bit 6=special
      alt    (float) - Altitude (may be absent)
    """
    ts = datetime.fromtimestamp(stroke["time"] / 1000, tz=timezone.utc)
    return (
        f"[{ts.strftime('%H:%M:%S.%f')} UTC] "
        f"lat={stroke.get('lat'):.4f} lon={stroke.get('lon'):.4f} "
        f"src={stroke.get('src')} dev={stroke.get('dev')}m "
        f"del={stroke.get('del')}ms id={stroke.get('id')}"
    )


# ---------------------------------------------------------------------------
# HTTP helper (works with requests or urllib)
# ---------------------------------------------------------------------------

def _get(url: str, params: Optional[Dict] = None, timeout: int = 15,
         stream: bool = False) -> bytes:
    """HTTP GET using requests if available, otherwise urllib."""
    if params:
        url = url + "?" + urlencode(params)
    if HAS_REQUESTS:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout,
                            stream=stream)
        resp.raise_for_status()
        return resp.content
    else:
        import urllib.request
        req = urllib.request.Request(url)
        for k, v in DEFAULT_HEADERS.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()


# ---------------------------------------------------------------------------
# WebSocket client (real-time streaming)
# ---------------------------------------------------------------------------

class LightningWebSocketClient:
    """
    Real-time lightning strike streaming via WebSocket.

    The server uses a challenge-response mechanism on connection:
      1. Server sends: {"cid":..., "con":..., "port":..., "time":..., "k": CHALLENGE_VALUE}
      2. Client responds: {"k": (challenge_k * 3604) % 7081 * unix_ms / 100}
      3. Server begins sending stroke batches

    Each stroke batch message:
      {
        "time":    1234567890,          # server-side Unix timestamp
        "flags":   {"2": 2},            # bitmask flags per source
        "strokes": [                    # list of stroke objects
          {
            "time": 1234567890123,      # Unix ms timestamp
            "lat":  51.5,               # latitude
            "lon":  -0.1,               # longitude
            "src":  2,                  # source (2=Blitzortung, 4=LightningMaps)
            "srv":  1,                  # server id
            "id":   12345678,           # stroke id
            "del":  1750,               # detection delay ms
            "dev":  2500,               # accuracy estimate meters
            "sta":  {"1": 1, "2": 0}   # station map (only if s=True in request)
          },
          ...
        ]
      }
    """

    def __init__(
        self,
        server_url: str = WS_SERVERS[0],
        src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
        request_stations: bool = False,
        zoom: int = 5,
        bounds: Optional[Tuple[float, float, float, float]] = None,
        reconnect: bool = True,
        reconnect_delay: float = 3.0,
    ):
        """
        Initialize the WebSocket client.

        Args:
            server_url: WebSocket server URL (default: wss://live.lightningmaps.org/)
            src_mask: Bitmask of data sources to receive:
                      SRC_BLITZORTUNG (2), SRC_LIGHTNINGMAPS (4), or both (6)
            request_stations: If True, each stroke includes participating station IDs
            zoom: Map zoom level (affects which strokes are returned)
            bounds: Optional (north_lat, east_lon, south_lat, west_lon) bounding box
                    for filtering. If None, gets global data.
            reconnect: Auto-reconnect on disconnect
            reconnect_delay: Seconds to wait before reconnecting
        """
        self.server_url = server_url
        self.src_mask = src_mask
        self.request_stations = request_stations
        self.zoom = zoom
        self.bounds = bounds or (85.0, 180.0, -85.0, -180.0)  # global
        self.reconnect = reconnect
        self.reconnect_delay = reconnect_delay

        self._ws: Optional[websocket.WebSocketApp] = None
        self._running = False
        self._loop_count = 0
        self._last_ids: Dict[int, int] = {}  # src -> last_id seen
        self._on_stroke_cb: Optional[Callable[[Dict], None]] = None
        self._on_batch_cb: Optional[Callable[[Dict], None]] = None
        self._connected = threading.Event()
        self._strokes_queue: List[Dict] = []

    def _build_request_msg(self, reason: str = "A") -> str:
        """Build the JSON request message to send to server."""
        north, east, south, west = self.bounds
        msg = {
            "v": PROTOCOL_VERSION,
            "i": self._last_ids,
            "s": self.request_stations,
            "x": 0,
            "w": 0,
            "tx": 0,
            "tw": 0,
            "a": self.src_mask,
            "z": self.zoom,
            "b": True,
            "h": "",
            "l": self._loop_count,
            "t": int(time.time()),
            "from_lightningmaps_org": True,
            "p": [
                round(north * 10) / 10,
                round(east * 10) / 10,
                round(south * 10) / 10,
                round(west * 10) / 10,
            ],
        }
        return json.dumps(msg)

    def _handle_challenge(self, ws: Any, k_value: float) -> None:
        """Respond to server challenge."""
        response_k = (k_value * WS_CHALLENGE_MULT) % WS_CHALLENGE_MOD * (time.time() * 1000) / 100
        ws.send(json.dumps({"k": response_k}))

    def _on_open(self, ws: Any) -> None:
        logger.debug("WebSocket connected to %s", self.server_url)
        ws.send(self._build_request_msg("A"))

    def _on_message(self, ws: Any, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse WS message: %s", e)
            return

        # Challenge message
        if "k" in msg:
            self._handle_challenge(ws, msg["k"])
            # Also send the data request after responding to challenge
            ws.send(self._build_request_msg())
            return

        # Stroke batch
        if "strokes" in msg:
            self._connected.set()
            strokes = msg.get("strokes", [])
            self._loop_count += 1

            # Update last-seen IDs per source
            for s in strokes:
                src = s.get("src")
                sid = s.get("id")
                if src is not None and sid is not None:
                    if src not in self._last_ids or sid > self._last_ids[src]:
                        self._last_ids[src] = sid

            self._strokes_queue.extend(strokes)

            if self._on_batch_cb:
                self._on_batch_cb(msg)
            if self._on_stroke_cb:
                for stroke in strokes:
                    self._on_stroke_cb(stroke)

        # Time-only heartbeat (no data, just server clock)
        elif "time" in msg and len(msg) == 1:
            logger.debug("WS heartbeat at server_time=%s", msg["time"])

    def _on_error(self, ws: Any, error: Any) -> None:
        logger.warning("WebSocket error: %s", error)

    def _on_close(self, ws: Any, code: Any, msg: Any) -> None:
        logger.info("WebSocket closed: code=%s msg=%s", code, msg)
        self._connected.clear()
        if self._running and self.reconnect:
            logger.info("Reconnecting in %.1fs...", self.reconnect_delay)
            time.sleep(self.reconnect_delay)
            self._connect()

    def _connect(self) -> None:
        if not HAS_WEBSOCKET:
            raise ImportError(
                "websocket-client not installed. Run: pip install websocket-client"
            )
        self._ws = websocket.WebSocketApp(
            self.server_url,
            header={"Origin": "https://www.lightningmaps.org"},
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def start(
        self,
        on_stroke: Optional[Callable[[Dict], None]] = None,
        on_batch: Optional[Callable[[Dict], None]] = None,
        daemon: bool = True,
    ) -> threading.Thread:
        """
        Start WebSocket connection in a background thread.

        Args:
            on_stroke: Callback called for each individual stroke dict
            on_batch:  Callback called for each full batch message
            daemon:    If True, thread exits when main thread exits

        Returns:
            The background thread (already started)
        """
        self._on_stroke_cb = on_stroke
        self._on_batch_cb = on_batch
        self._running = True
        t = threading.Thread(target=self._connect, daemon=daemon)
        t.start()
        return t

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def stream(
        self,
        max_strokes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict, None, None]:
        """
        Generator that yields individual stroke dicts in real time.

        Args:
            max_strokes: Stop after yielding this many strokes
            timeout: Stop after this many seconds (None = run forever)

        Yields:
            Stroke dicts with keys: time, lat, lon, src, srv, id, del, dev, [sta]
        """
        if not HAS_WEBSOCKET:
            raise ImportError(
                "websocket-client not installed. Run: pip install websocket-client"
            )
        self._running = True
        self._strokes_queue = []

        t = self.start(daemon=True)
        start_time = time.time()
        count = 0

        try:
            while self._running:
                if timeout and (time.time() - start_time) > timeout:
                    break
                if max_strokes and count >= max_strokes:
                    break

                if self._strokes_queue:
                    stroke = self._strokes_queue.pop(0)
                    count += 1
                    yield stroke
                else:
                    time.sleep(0.05)
        finally:
            self.stop()

    def wait_connected(self, timeout: float = 15.0) -> bool:
        """Block until first batch of data is received. Returns True if connected."""
        return self._connected.wait(timeout=timeout)


# ---------------------------------------------------------------------------
# XHR polling client (fallback when WebSocket is unavailable)
# ---------------------------------------------------------------------------

class LightningXHRClient:
    """
    Real-time lightning data via HTTP long-polling (XHR fallback).

    The server returns a JSON object:
      {
        "w":   500,         # wait milliseconds before next request (when data received)
        "o":   5000,        # wait ms when no new data (out-of-bounds)
        "s":   2409624,     # sequence number to use in next request (l= param)
        "d":   [...],       # array of stroke objects
        "t":   1234567890,  # server timestamp
        "x":   true,        # data available flag
        "copyright": "...", # copyright notice
      }

    XHR endpoint: GET https://live.lightningmaps.org/l/
    Parameters:
      v    (int)    - Protocol version (currently 24)
      l    (int)    - Last sequence number seen (0 for first request)
      i    (int)    - Source bitmask (4=LightningMaps, 2=Blitzortung, 6=both)
      s    (flag)   - Include station data if present
      m    (flag)   - Mobile mode if present
      e    (int)    - Error count (optional)
    """

    def __init__(
        self,
        server_url: str = XHR_SERVERS[0],
        src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
        include_stations: bool = False,
    ):
        self.server_url = server_url
        self.src_mask = src_mask
        self.include_stations = include_stations
        self._last_seq = 0

    def _build_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "v": PROTOCOL_VERSION,
            "l": self._last_seq,
            "i": self.src_mask,
        }
        if self.include_stations:
            params["s"] = ""
        return params

    def poll(self) -> Dict[str, Any]:
        """
        Perform a single poll request.

        Returns:
            Response dict containing:
              - 'd': list of stroke dicts (may be empty)
              - 's': new sequence number
              - 'w': milliseconds to wait before next poll (when data)
              - 'o': milliseconds to wait when no new data
              - 'copyright': copyright notice
        """
        url = self.server_url
        params = self._build_params()
        raw = _get(url, params=params)
        data = json.loads(raw)
        if "s" in data:
            self._last_seq = data["s"]
        return data

    def stream(
        self,
        max_strokes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict, None, None]:
        """
        Generator that yields stroke dicts by polling the XHR endpoint.

        Automatically adjusts poll interval based on server hints (w/o fields).

        Args:
            max_strokes: Stop after yielding this many strokes
            timeout: Stop after this many seconds (None = run forever)

        Yields:
            Stroke dicts
        """
        count = 0
        start_time = time.time()

        while True:
            if timeout and (time.time() - start_time) > timeout:
                break
            if max_strokes and count >= max_strokes:
                break

            try:
                data = self.poll()
                strokes = data.get("d", [])
                wait_ms = data.get("w", 500) if strokes else data.get("o", 5000)
                wait_sec = max(0.1, wait_ms / 1000)

                for stroke in strokes:
                    if max_strokes and count >= max_strokes:
                        return
                    count += 1
                    yield stroke

                time.sleep(wait_sec)

            except Exception as e:
                logger.warning("XHR poll error: %s", e)
                time.sleep(5)


# ---------------------------------------------------------------------------
# Main client (combines all APIs)
# ---------------------------------------------------------------------------

class LightningMapsClient:
    """
    High-level client for all LightningMaps.org / Blitzortung.org APIs.

    Covers:
      1. Real-time WebSocket streaming (primary)
      2. Real-time XHR polling (fallback)
      3. Station metadata (JSON)
      4. Map tile images (lightning strike density tiles)
      5. Archive tile images (historical lightning tiles with time range)
      6. Archive map images (pre-rendered regional maps by date)
      7. Mini-map images and animations
      8. Signal waveform graphs
      9. Country border GeoJSON
    """

    def __init__(self, prefer_websocket: bool = True):
        """
        Args:
            prefer_websocket: If True and websocket-client is installed,
                              use WebSocket for real-time data. Otherwise fall back to XHR.
        """
        self.prefer_websocket = prefer_websocket and HAS_WEBSOCKET

    # -----------------------------------------------------------------------
    # 1. Real-time WebSocket streaming
    # -----------------------------------------------------------------------

    def stream_realtime(
        self,
        server: str = WS_SERVERS[0],
        src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
        request_stations: bool = False,
        zoom: int = 5,
        bounds: Optional[Tuple[float, float, float, float]] = None,
        max_strokes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict, None, None]:
        """
        Stream real-time lightning strikes via WebSocket.

        Args:
            server: WebSocket server URL
            src_mask: Which data sources to include (SRC_BLITZORTUNG=2, SRC_LIGHTNINGMAPS=4)
            request_stations: Include participating station IDs in each stroke
            zoom: Map zoom level (2-15). Higher zoom may return more detail.
            bounds: Bounding box as (north_lat, east_lon, south_lat, west_lon).
                    The server uses this for priority but typically returns global data.
            max_strokes: Yield at most this many strokes
            timeout: Stop after this many seconds

        Yields:
            Dict with keys:
              time  (int)   - Unix timestamp milliseconds
              lat   (float) - Latitude
              lon   (float) - Longitude
              src   (int)   - Source: 2=Blitzortung, 4=LightningMaps
              srv   (int)   - Server ID
              id    (int)   - Stroke ID
              del   (int)   - Detection delay ms
              dev   (int)   - Accuracy estimate meters
              sta   (dict)  - Station participation (optional, if request_stations=True)
        """
        ws_client = LightningWebSocketClient(
            server_url=server,
            src_mask=src_mask,
            request_stations=request_stations,
            zoom=zoom,
            bounds=bounds,
        )
        yield from ws_client.stream(max_strokes=max_strokes, timeout=timeout)

    def stream_realtime_background(
        self,
        on_stroke: Callable[[Dict], None],
        server: str = WS_SERVERS[0],
        src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
        request_stations: bool = False,
    ) -> LightningWebSocketClient:
        """
        Start background WebSocket streaming with a callback.

        Args:
            on_stroke: Called for each stroke dict received
            server: WebSocket server URL
            src_mask: Data source bitmask
            request_stations: Include station data

        Returns:
            The LightningWebSocketClient instance (call .stop() to disconnect)
        """
        ws_client = LightningWebSocketClient(
            server_url=server,
            src_mask=src_mask,
            request_stations=request_stations,
        )
        ws_client.start(on_stroke=on_stroke)
        return ws_client

    # -----------------------------------------------------------------------
    # 2. Real-time XHR polling
    # -----------------------------------------------------------------------

    def poll_realtime(
        self,
        server: str = XHR_SERVERS[0],
        src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
    ) -> Dict[str, Any]:
        """
        Perform a single XHR poll for the latest strokes.

        Args:
            server: XHR server URL
            src_mask: Data source bitmask

        Returns:
            Response dict:
              'd'  (list) - Stroke dicts (empty if no new data)
              's'  (int)  - Sequence number for next request
              'w'  (int)  - Suggested next poll delay ms (when data received)
              'o'  (int)  - Suggested next poll delay ms (when no data)
              'copyright' (str) - Copyright notice
        """
        xhr_client = LightningXHRClient(server_url=server, src_mask=src_mask)
        return xhr_client.poll()

    def stream_realtime_xhr(
        self,
        server: str = XHR_SERVERS[0],
        src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
        max_strokes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict, None, None]:
        """
        Stream real-time lightning strikes via XHR polling (no WebSocket needed).

        Args:
            server: XHR server URL
            src_mask: Data source bitmask
            max_strokes: Stop after this many strokes
            timeout: Stop after this many seconds

        Yields:
            Stroke dicts
        """
        xhr_client = LightningXHRClient(server_url=server, src_mask=src_mask)
        yield from xhr_client.stream(max_strokes=max_strokes, timeout=timeout)

    # -----------------------------------------------------------------------
    # 3. Station metadata
    # -----------------------------------------------------------------------

    def get_stations(self, region: str = "europe") -> Dict[str, Any]:
        """
        Retrieve all detector stations for a region.

        Args:
            region: One of 'europe', 'america', 'oceania'

        Returns:
            Dict with keys:
              'user' (str) - Empty string (or username if logged in)
              'stations' (dict) - Station ID -> station info:
                  '0'  (float) - Latitude
                  '1'  (float) - Longitude
                  'a'  (str)   - Altitude in meters
                  'c'  (str)   - City/location name
                  'C'  (str)   - Country name
                  's'  (str)   - Status ('0'=online, '10'=online, 'D'=offline, '30'=partial)
        """
        region_path = REGIONS.get(region, region)
        url = f"{STATIONS_BASE}/{region_path}/index.php"
        raw = _get(url, params={"stations_json": ""})
        return json.loads(raw)

    def get_all_stations(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieve stations from all regions, merged into a single dict.

        Returns:
            Dict mapping station_id -> station info (with added 'region' key)
        """
        all_stations = {}
        for region in REGIONS:
            data = self.get_stations(region)
            for sid, info in data.get("stations", {}).items():
                info["region"] = region
                all_stations[sid] = info
        return all_stations

    # -----------------------------------------------------------------------
    # 4. Lightning strike density tiles
    # -----------------------------------------------------------------------

    def get_lightning_tile(
        self,
        x: int,
        y: int,
        z: int,
        tile_type: int = TILE_TYPE_1H,
        size: int = 256,
    ) -> bytes:
        """
        Get a PNG tile with rendered lightning strike density overlay.

        Tile coordinates follow standard XYZ Web Mercator scheme.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            z: Zoom level (2-16)
            tile_type: TILE_TYPE_1H (5) = last hour, TILE_TYPE_24H (6) = last 24h
            size: Tile size in pixels (256 or 512)

        Returns:
            PNG image bytes

        Example URL: https://tiles.lightningmaps.org/?x=8&y=10&z=5&s=256&t=5
        """
        params = {"x": x, "y": y, "z": z, "s": size, "t": tile_type}
        return _get(TILES_BASE, params=params)

    def get_lightning_counter_tile(
        self,
        x: int,
        y: int,
        z: int,
        tile_types: str = "5",
        size: int = 256,
    ) -> bytes:
        """
        Get a PNG tile showing lightning count numbers per area.

        Args:
            x, y, z: Tile coordinates
            tile_types: Comma-separated tile type values (e.g., "5,6" for 1h+24h)
            size: Tile size in pixels

        Returns:
            PNG image bytes

        Example URL: https://tiles.lightningmaps.org/?x=8&y=10&z=5&s=256&count=5,6
        """
        params = {"x": x, "y": y, "z": z, "s": size, "count": tile_types}
        return _get(TILES_BASE, params=params)

    # -----------------------------------------------------------------------
    # 5. Archive lightning tiles (historical, with time range)
    # -----------------------------------------------------------------------

    def get_archive_tile(
        self,
        x: int,
        y: int,
        z: int,
        from_time: datetime,
        to_time: datetime,
        size: int = 256,
    ) -> bytes:
        """
        Get a PNG tile showing historical lightning strikes for a time range.

        Args:
            x, y, z: Tile coordinates
            from_time: Start of time range (UTC)
            to_time: End of time range (UTC)
            size: Tile size in pixels

        Returns:
            PNG image bytes

        Example URL:
            https://tiles.lightningmaps.org/?x=8&y=10&z=5&s=256
            &from=2026-03-24T00:00:00.000Z&to=2026-03-24T23:59:59.000Z
        """
        params = {
            "x": x, "y": y, "z": z, "s": size,
            "from": from_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "to": to_time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        return _get(TILES_BASE, params=params)

    # -----------------------------------------------------------------------
    # 6. Map background tiles
    # -----------------------------------------------------------------------

    def get_map_tile(
        self,
        x: int,
        y: int,
        z: int,
        style: str = "carto",
    ) -> bytes:
        """
        Get a background map tile (no lightning data).

        Args:
            x, y, z: Tile coordinates
            style: One of:
              'carto'           - OpenStreetMap Carto style (default)
              'carto-nolabels' - OSM without labels
              'terrain'         - Terrain / relief style
              'trans'           - Transparent/simple roads
              'eox_s2cloudless_2022' - Sentinel-2 satellite imagery

        Returns:
            PNG image bytes

        Example URL: https://map.lightningmaps.org/carto/5/16/11.png
        """
        url = f"{MAP_BASE}/{style}/{z}/{x}/{y}.png"
        return _get(url)

    def get_radar_tile(self, x: int, y: int, z: int) -> bytes:
        """
        Get a NEXRAD rain radar tile (US only).

        Args:
            x, y, z: Tile coordinates (valid bounds: lat 0-90, lon -180 to -20)

        Returns:
            PNG image bytes

        Example URL: https://map.lightningmaps.org/radar/5/9/12.png
        """
        url = f"{MAP_BASE}/radar/{z}/{x}/{y}.png"
        return _get(url)

    # -----------------------------------------------------------------------
    # 7. Archive map images (pre-rendered regional images by date)
    # -----------------------------------------------------------------------

    def get_archive_map_image(
        self,
        region: str = "europe",
        date: str = None,
        map_id: Any = 0,
        hour_from: int = 0,
        hour_range: int = 24,
    ) -> bytes:
        """
        Get a pre-rendered archive map image (PNG) for a specific date.

        Args:
            region: 'europe', 'america', or 'oceania'
            date: Date string in YYYYMMDD format (e.g., '20260324').
                  Defaults to yesterday.
            map_id: Map area selection. For Europe:
                    0='Europe', 6='Western Europe',
                    'de2'='Germany', 'france'='France', 'uk'='UK', etc.
                    For America: 0 or 'usa_mini'
                    For Oceania: 0 or 'oceania_mini'
            hour_from: Start hour (0, 6, 12, or 18)
            hour_range: Hours to show (6, 12, 18, 24, ...)

        Returns:
            PNG image bytes

        Example URL:
            https://images.lightningmaps.org/blitzortung/europe/index.php?map=0&date=20260324
        """
        if date is None:
            from datetime import timedelta
            date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")
        region_path = REGIONS.get(region, region)
        url = f"{IMAGES_BASE}/{region_path}/index.php"
        params: Dict[str, Any] = {"map": map_id, "date": date}
        if hour_from != 0:
            params["hour_from"] = hour_from
        if hour_range != 24:
            params["hour_range"] = hour_range
        return _get(url, params=params)

    def get_archive_animation(
        self,
        region: str = "europe",
        date: str = None,
        map_id: Any = 0,
        hour_from: int = 0,
        hour_range: int = 24,
    ) -> bytes:
        """
        Get an animated GIF of archived lightning for a date range.

        Args:
            region: 'europe', 'america', or 'oceania'
            date: Date string in YYYYMMDD format. Defaults to yesterday.
            map_id: Map area selection (same as get_archive_map_image)
            hour_from: Start hour (0, 6, 12, or 18)
            hour_range: Duration in hours (6, 12, 18, 24, ...)

        Returns:
            Animated GIF bytes (may be large, 100KB-10MB)

        Example URL:
            https://images.lightningmaps.org/blitzortung/europe/index.php
            ?animation=0&date=20260324&hour_from=0&hour_range=6
        """
        if date is None:
            from datetime import timedelta
            date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")
        region_path = REGIONS.get(region, region)
        url = f"{IMAGES_BASE}/{region_path}/index.php"
        params: Dict[str, Any] = {
            "animation": map_id,
            "date": date,
            "hour_from": hour_from,
            "hour_range": hour_range,
        }
        return _get(url, params=params, timeout=60)

    # -----------------------------------------------------------------------
    # 8. Mini-map images and animations (sidebar thumbnails)
    # -----------------------------------------------------------------------

    def get_mini_map(
        self,
        region: str = "eu",
        animated: bool = False,
    ) -> bytes:
        """
        Get a small thumbnail map image/animation (used in sidebar).

        Args:
            region: One of:
              'eu' - Europe (map ID 5)
              'de' - Germany (map ID 1, with radar)
              'us' - USA (map ID 'usa_mini')
              'oc' - Oceania (map ID 'oceania_mini')
            animated: If True, return animated GIF; if False, return static JPEG

        Returns:
            Image bytes (JPEG for static, GIF for animated)

        Example URLs:
            https://images.lightningmaps.org/blitzortung/europe/index.php?map=5
            https://images.lightningmaps.org/blitzortung/europe/index.php?animation=5
        """
        region_map = {
            "eu": ("europe", "5"),
            "de": ("europe", "1"),
            "us": ("america", "usa_mini"),
            "oc": ("oceania", "oceania_mini"),
        }
        region_path, map_id = region_map.get(region, ("europe", "5"))
        url = f"{IMAGES_BASE}/{region_path}/index.php"

        # Add timestamp to bypass cache (round to 5-minute intervals)
        t = int(time.time() / 300)
        param_key = "animation" if animated else "map"
        params = {param_key: map_id, "t": t}
        return _get(url, params=params, timeout=30)

    # -----------------------------------------------------------------------
    # 9. Signal waveform graphs
    # -----------------------------------------------------------------------

    def get_signal_graph(
        self,
        region: str = "europe",
        station_id: int = None,
        strike_time: str = None,
        dist_meters: int = None,
        graph_type: str = "time",
        size_multiplier: int = 1,
    ) -> bytes:
        """
        Get the signal waveform graph for a specific lightning strike at a station.

        Args:
            region: 'europe', 'america', or 'oceania'
            station_id: Station ID (from stations JSON)
            strike_time: Strike time as ISO-like string, e.g. '2026-03-25 02:34:40.694347488'
            dist_meters: Distance from station to strike in meters (from strikes list page)
            graph_type: Type of graph:
              'time'     - Time domain signal waveform (default)
              'spectrum' - Frequency spectrum  (add ?bo_spectrum)
              'xy'       - X/Y scatter plot    (add ?bo_xy)
            size_multiplier: 1 for thumbnail, 3 for full size

        Returns:
            PNG image bytes

        Example URL:
            https://images.lightningmaps.org/blitzortung/europe/index.php
            ?bo_graph&bo_station_id=49775&bo_dist=403604
            &bo_time=2026-03-25+02%3A34%3A40.694347488&lang=en
        """
        region_path = REGIONS.get(region, region)
        url = f"{IMAGES_BASE}/{region_path}/index.php"
        params: Dict[str, Any] = {
            "bo_graph": "",
            "bo_station_id": station_id,
            "bo_dist": dist_meters,
            "bo_time": strike_time,
            "lang": "en",
        }
        if graph_type == "spectrum":
            params["bo_spectrum"] = ""
        elif graph_type == "xy":
            params["bo_xy"] = ""
        if size_multiplier != 1:
            params["bo_size"] = size_multiplier
        return _get(url, params=params)

    # -----------------------------------------------------------------------
    # 10. Country border GeoJSON
    # -----------------------------------------------------------------------

    def get_country_borders(self) -> Dict[str, Any]:
        """
        Get world country borders as GeoJSON FeatureCollection.

        Returns:
            GeoJSON dict with 'type': 'FeatureCollection' and 'features' list.
            Each feature has properties: name, sovereignt, admin, etc.

        Example URL: https://www.lightningmaps.org/geo.json
        """
        raw = _get(GEO_JSON_URL, timeout=30)
        return json.loads(raw)

    # -----------------------------------------------------------------------
    # Utility: Convert tile coordinates
    # -----------------------------------------------------------------------

    @staticmethod
    def latlon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
        """
        Convert latitude/longitude to tile X/Y coordinates at a given zoom level.

        Args:
            lat: Latitude in decimal degrees (-85.051 to 85.051)
            lon: Longitude in decimal degrees (-180 to 180)
            zoom: Zoom level (0-15)

        Returns:
            Tuple of (tile_x, tile_y)
        """
        import math
        n = 2 ** zoom
        tile_x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        tile_y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return tile_x, tile_y

    @staticmethod
    def tile_to_latlon(x: int, y: int, zoom: int) -> Tuple[float, float]:
        """
        Convert tile coordinates to the NW corner latitude/longitude.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            zoom: Zoom level

        Returns:
            Tuple of (latitude, longitude) for the NW corner
        """
        import math
        n = 2 ** zoom
        lon = x / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        lat = math.degrees(lat_rad)
        return lat, lon


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def stream_lightning(
    seconds: int = 60,
    src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> Generator[Dict, None, None]:
    """
    Simple function to stream lightning strikes for a given duration.

    Args:
        seconds: How long to stream
        src_mask: Data source bitmask (SRC_BLITZORTUNG=2, SRC_LIGHTNINGMAPS=4)
        bounds: Optional (north, east, south, west) bounding box

    Yields:
        Stroke dicts
    """
    client = LightningMapsClient()
    if HAS_WEBSOCKET:
        yield from client.stream_realtime(timeout=float(seconds),
                                           src_mask=src_mask, bounds=bounds)
    else:
        yield from client.stream_realtime_xhr(timeout=float(seconds),
                                               src_mask=src_mask)


def get_recent_strokes(
    n: int = 100,
    src_mask: int = SRC_BLITZORTUNG | SRC_LIGHTNINGMAPS,
) -> List[Dict]:
    """
    Get up to N recent lightning strikes using the fastest available method.

    Args:
        n: Number of strokes to collect
        src_mask: Data source bitmask

    Returns:
        List of stroke dicts
    """
    client = LightningMapsClient()
    if HAS_WEBSOCKET:
        strokes = []
        for stroke in client.stream_realtime(max_strokes=n, src_mask=src_mask, timeout=30):
            strokes.append(stroke)
        return strokes
    else:
        data = client.poll_realtime(src_mask=src_mask)
        return data.get("d", [])[:n]


# ---------------------------------------------------------------------------
# CLI / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="LightningMaps API Client - Stream real-time lightning data"
    )
    parser.add_argument("--duration", type=int, default=30,
                        help="Streaming duration in seconds (default: 30)")
    parser.add_argument("--method", choices=["ws", "xhr"], default="ws",
                        help="Data method: ws=WebSocket, xhr=HTTP polling (default: ws)")
    parser.add_argument("--region", default=None,
                        help="Filter region: europe, america, oceania")
    parser.add_argument("--stations", action="store_true",
                        help="Request station participation data")
    parser.add_argument("--src", type=int, default=6,
                        help="Source bitmask: 2=Blitzortung, 4=LightningMaps, 6=both (default: 6)")
    parser.add_argument("--info", action="store_true",
                        help="Show station info for a region")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    client = LightningMapsClient()

    if args.info:
        region = args.region or "europe"
        print(f"Fetching stations for {region}...")
        data = client.get_stations(region)
        stations = data.get("stations", {})
        online = {k: v for k, v in stations.items() if v.get("s") not in ("D",)}
        print(f"Total stations: {len(stations)}, Online: {len(online)}")
        for sid, info in list(stations.items())[:10]:
            status = "online" if info.get("s") not in ("D",) else "offline"
            print(f"  [{sid}] {info.get('c', 'Unknown')}, {info.get('C', '')} "
                  f"({info.get('0')}, {info.get('1')}) alt={info.get('a')}m [{status}]")
        sys.exit(0)

    print(f"Streaming lightning strikes for {args.duration}s "
          f"(method={args.method}, src={args.src})...")
    print("-" * 70)

    count = 0
    try:
        if args.method == "ws":
            if not HAS_WEBSOCKET:
                print("ERROR: websocket-client not installed. Run: pip install websocket-client")
                print("Falling back to XHR...")
                gen = client.stream_realtime_xhr(timeout=float(args.duration), src_mask=args.src)
            else:
                gen = client.stream_realtime(
                    timeout=float(args.duration),
                    src_mask=args.src,
                    request_stations=args.stations,
                )
        else:
            gen = client.stream_realtime_xhr(timeout=float(args.duration), src_mask=args.src)

        for stroke in gen:
            count += 1
            # XHR responses have lat/lon as strings; WebSocket has them as floats
            lat = float(stroke.get('lat', 0))
            lon = float(stroke.get('lon', 0))
            t_val = stroke.get("time", 0)
            # XHR 'time' may be a negative offset; skip if invalid
            try:
                ts = datetime.fromtimestamp(t_val / 1000, tz=timezone.utc)
                ts_str = ts.strftime('%H:%M:%S.%f')[:-3]
            except (OSError, ValueError):
                ts_str = f"t={t_val}"
            src_name = STROKE_SRC_NAMES.get(stroke.get("src", 0), f"s{stroke.get('src')}")
            dev = stroke.get('dev', 0) or 0
            del_ms = stroke.get('del', 0) or 0
            print(f"[{count:4d}] {ts_str} UTC "
                  f"lat={lat:8.4f} lon={lon:9.4f} "
                  f"src={src_name} dev={dev:5d}m "
                  f"del={del_ms:4d}ms")
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")

    print("-" * 70)
    print(f"Total strokes received: {count}")
    print(f"Rate: {count / args.duration:.1f} strokes/second")
