"""
RainViewer API Client - Reverse Engineered
==========================================

Comprehensive Python client for RainViewer's internal and public APIs.

APIs discovered via JavaScript source analysis of:
  - https://www.rainviewer.com/map.html
  - https://www.rainviewer.com/vue/interactions/js/277.js
  - https://www.rainviewer.com/vue/interactions/js/327.js

Authentication Flow:
  1. GET https://api.rainviewer.com/site/auth/session
     -> Returns session ID in X-Rv-Sid header and sid cookie
  2. POST https://api.rainviewer.com/site/auth/api-key
     -> With x-rv-sid header -> Returns temporary API key (X-RV-Token)
     -> API key expires in ~2 hours (expiresAt field), session lasts ~2 hours (okUntil)

All authenticated requests require:
  - Header: X-RV-Token: <api_key>
  - Header: x-rv-sid: <session_id>
"""

import json
import time
import gzip
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, Any, List, Tuple, Union
from dataclasses import dataclass, field


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

API_BASE = "https://api.rainviewer.com"
TILECACHE_HOST = "https://tilecache.rainviewer.com"
CDN_HOST = "https://cdn.rainviewer.com"
MAPS_HOST = "https://maps.rainviewer.com"

# Public (no-auth) endpoint
PUBLIC_WEATHER_MAPS_URL = f"{API_BASE}/public/weather-maps.json"

# Color schemes for radar tiles (tilecache PNG format)
COLOR_SCHEMES = {
    0: "Original",
    1: "Universal Blue",
    2: "TITAN",
    3: "TWC",
    4: "Meteored",
    5: "NEXRAD Level III",
    6: "Rainbow @ SELEX-SI",
    7: "Dark Sky",
    8: "Infrared Satellite (for satellite tiles only)",
}

# Map style themes
MAP_STYLES = {
    "m2": "Light (default)",
    "m2_dark": "Dark",
    "m2_satellite": "Satellite",
}

# Tile size options
TILE_SIZES = [256, 512]

# Layer types
LAYER_TYPES = {
    "radar": "Weather radar precipitation",
    "sat": "Infrared satellite",
    "sat-rad": "Combined satellite + radar",
}

# Token expiry buffer in seconds (refresh 5 min before expiry)
TOKEN_EXPIRY_BUFFER = 300


# ─────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────

@dataclass
class RadarFrame:
    """A single radar or satellite frame."""
    time: int           # Unix timestamp
    path: str           # Tile path prefix (e.g. /v2/radar/abc123)
    frame_type: str = "radar"  # "radar" or "sat"

    def get_tile_url(
        self,
        z: int,
        x: int,
        y: int,
        size: int = 256,
        color: int = 4,
        smooth: int = 1,
        snow: int = 0,
        host: str = TILECACHE_HOST,
        fmt: str = "png",
    ) -> str:
        """
        Build a tile map image URL.

        Tilecache (PNG) format:
          {host}{path}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png
          e.g. https://tilecache.rainviewer.com/v2/radar/abc123/256/3/4/3/4/1_0.png

        CDN (WebP) format:
          {host}{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp
          e.g. https://cdn.rainviewer.com/v2/radar/abc123/512/3/4/3/255/1_1_0.webp

        Args:
            z: Zoom level (0-14)
            x: Tile X coordinate
            y: Tile Y coordinate
            size: Tile size in pixels (256 or 512)
            color: Color scheme index 0-8 (see COLOR_SCHEMES)
                   Use 255 for CDN/WebP tiles (full opacity)
            smooth: Smoothing (1=on, 0=off) - reduces pixelation
            snow: Snow coloring (1=on, 0=off) - shows snow in white/blue
            host: Tile host (TILECACHE_HOST for PNG, CDN_HOST for WebP)
            fmt: Image format ("png" or "webp")

        Returns:
            Full tile URL string.
        """
        if fmt == "webp":
            # CDN WebP format: path/size/z/x/y/255/smooth_1_snow_0.webp
            return f"{CDN_HOST}{self.path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp"
        else:
            # Tilecache PNG format: path/size/z/x/y/color/smooth_snow.png
            return f"{TILECACHE_HOST}{self.path}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png"

    def get_timestamp_str(self) -> str:
        """Return human-readable UTC timestamp string."""
        import datetime
        dt = datetime.datetime.utcfromtimestamp(self.time)
        return dt.strftime("%Y-%m-%d %H:%M UTC")


@dataclass
class WeatherAlert:
    """A severe weather alert."""
    id: str
    kind: str           # e.g. "Met"
    severity: str       # "Minor", "Moderate", "Severe", "Extreme"
    category: str       # e.g. "Flood", "Wind", "Tornado"
    alert_type: str     # e.g. "Coastal Flood Statement"
    certainty: str      # "Possible", "Likely", "Observed"
    urgency: str        # "Immediate", "Expected", "Future"
    event: str          # Event name
    starts: int         # Unix timestamp
    ends: int           # Unix timestamp
    title: str
    description: str
    instruction: str
    area: List[Dict]    # List of affected areas with polygons
    source: Dict        # Data source info
    raw: Dict = field(default_factory=dict)  # Full raw response


@dataclass
class StormTrack:
    """A tropical storm / hurricane track."""
    name: str
    category: str       # e.g. "H4", "TS" (Tropical Storm), "TD" (Tropical Depression)
    current: Dict       # Current position, wind speed, movement
    track: List[Dict]   # Historical track points
    forecast: List[Dict]  # Forecast positions
    cone: List[Dict]    # Forecast cone uncertainty


@dataclass
class RadarStation:
    """Individual radar station metadata."""
    id: str
    country: str
    state: str
    location: str
    status: int
    latitude: float
    longitude: float
    range_km: int
    image_id: str
    is_pro: bool
    last_updated: Optional[int]
    frequency: Optional[int]
    is_offline: bool


@dataclass
class AuthState:
    """Authentication state."""
    api_key: Optional[str] = None
    api_key_expires_at: int = 0
    session_id: Optional[str] = None
    session_ok_until: int = 0


# ─────────────────────────────────────────────
# Core HTTP client
# ─────────────────────────────────────────────

class RainViewerHTTPClient:
    """
    Low-level HTTP client with automatic session and API key management.

    The auth flow:
      1. GET /site/auth/session  -> get sid from X-Rv-Sid header
      2. POST /site/auth/api-key (with x-rv-sid header) -> get apiKey
      3. All /site/* requests need: X-RV-Token + x-rv-sid headers
    """

    def __init__(self, auto_auth: bool = True):
        """
        Initialize the HTTP client.

        Args:
            auto_auth: If True, automatically obtain and refresh auth tokens.
        """
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )
        self._auth = AuthState()
        self._auto_auth = auto_auth
        self._max_retries = 2

    def _get_auth_headers(self) -> Dict[str, str]:
        """Return authentication headers."""
        headers = {}
        if self._auth.api_key:
            headers["X-RV-Token"] = self._auth.api_key
        if self._auth.session_id:
            headers["x-rv-sid"] = self._auth.session_id
        return headers

    def _is_api_key_valid(self) -> bool:
        """Check if current API key is still valid."""
        if not self._auth.api_key:
            return False
        return (self._auth.api_key_expires_at - TOKEN_EXPIRY_BUFFER) > time.time()

    def _is_session_valid(self) -> bool:
        """Check if current session is still valid."""
        if not self._auth.session_id:
            return False
        if self._auth.session_ok_until == 0:
            return True  # okUntil=0 means no expiry
        return self._auth.session_ok_until > time.time()

    def _create_session(self) -> None:
        """Create a new session by calling /site/auth/session."""
        req = urllib.request.Request(f"{API_BASE}/site/auth/session")
        with self._opener.open(req) as resp:
            body = json.loads(resp.read())
            # Session ID is in X-Rv-Sid header
            sid = resp.headers.get("X-Rv-Sid")
            if sid:
                self._auth.session_id = sid
            elif body.get("data", {}).get("sid"):
                self._auth.session_id = body["data"]["sid"]

            ok_until = body.get("data", {}).get("okUntil", 0)
            if ok_until and ok_until > 0:
                self._auth.session_ok_until = ok_until * 1000  # convert ms to s
            else:
                self._auth.session_ok_until = 0

    def _get_api_key(self) -> None:
        """Obtain an API key from /site/auth/api-key."""
        if not self._is_session_valid():
            self._create_session()

        headers = {
            "Content-Type": "application/json",
        }
        if self._auth.session_id:
            headers["x-rv-sid"] = self._auth.session_id

        req = urllib.request.Request(
            f"{API_BASE}/site/auth/api-key",
            method="POST",
            data=b"{}",
            headers=headers,
        )
        with self._opener.open(req) as resp:
            body = json.loads(resp.read())

        if body.get("code") == 100204:
            # No session - recreate session and retry
            self._create_session()
            headers["x-rv-sid"] = self._auth.session_id
            req = urllib.request.Request(
                f"{API_BASE}/site/auth/api-key",
                method="POST",
                data=b"{}",
                headers=headers,
            )
            with self._opener.open(req) as resp:
                body = json.loads(resp.read())

        data = body.get("data", {})
        api_key = data.get("apiKey") or data.get("api_key")
        expires_at = data.get("expiresAt") or data.get("expires_at", 0)
        ok_until = data.get("okUntil", 0)

        if not api_key:
            raise RuntimeError(f"Failed to get API key: {body}")

        self._auth.api_key = api_key
        if expires_at and expires_at > 0:
            self._auth.api_key_expires_at = expires_at
        else:
            self._auth.api_key_expires_at = int(time.time()) + 7200  # 2 hour default

        if ok_until and ok_until > 0:
            self._auth.session_ok_until = ok_until

    def ensure_auth(self) -> None:
        """Ensure valid auth tokens exist, refreshing if needed."""
        if not self._is_api_key_valid():
            self._get_api_key()

    def request_json(
        self,
        path: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        body: Optional[bytes] = None,
        extra_headers: Optional[Dict] = None,
        authenticated: bool = True,
    ) -> Dict[str, Any]:
        """
        Make an authenticated JSON API request.

        Args:
            path: API path (e.g. "/site/maps")
            method: HTTP method
            params: Query parameters dict
            body: Request body bytes
            extra_headers: Additional headers
            authenticated: Whether to include auth headers

        Returns:
            Parsed JSON response dict.

        Raises:
            RuntimeError: On API error responses.
            urllib.error.HTTPError: On HTTP errors.
        """
        if authenticated and self._auto_auth:
            self.ensure_auth()

        url = f"{API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        headers = {}
        if authenticated:
            headers.update(self._get_auth_headers())
        if extra_headers:
            headers.update(extra_headers)
        if body:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, method=method, data=body, headers=headers)

        for attempt in range(self._max_retries + 1):
            try:
                with self._opener.open(req) as resp:
                    response_body = json.loads(resp.read())

                code = response_body.get("code")
                if code is None:
                    return response_body  # Public API without code wrapper
                if code == 0:
                    return response_body.get("data", response_body)

                # Handle auth errors
                if code == 100206 and attempt < self._max_retries:
                    # Token invalid - clear and retry
                    self._auth.api_key = None
                    self._auth.api_key_expires_at = 0
                    self.ensure_auth()
                    headers.update(self._get_auth_headers())
                    req = urllib.request.Request(url, method=method, data=body, headers=headers)
                    continue
                elif code == 100204 and attempt < self._max_retries:
                    # Session expired - recreate session + key
                    self._auth.api_key = None
                    self._auth.session_id = None
                    self._auth.session_ok_until = 0
                    self.ensure_auth()
                    headers.update(self._get_auth_headers())
                    req = urllib.request.Request(url, method=method, data=body, headers=headers)
                    continue

                raise RuntimeError(
                    f"API error {code}: {response_body.get('message', 'Unknown error')}"
                )

            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and attempt < self._max_retries:
                    self._auth.api_key = None
                    self._auth.api_key_expires_at = 0
                    self.ensure_auth()
                    headers.update(self._get_auth_headers())
                    req = urllib.request.Request(url, method=method, data=body, headers=headers)
                    continue
                raise

        raise RuntimeError("Max retries exceeded")

    def request_binary(
        self,
        url: str,
        authenticated: bool = False,
    ) -> Tuple[bytes, str]:
        """
        Fetch binary data (tile images).

        Args:
            url: Full URL to fetch
            authenticated: Whether to include auth headers

        Returns:
            Tuple of (data_bytes, content_type)
        """
        headers = {}
        if authenticated and self._auto_auth:
            self.ensure_auth()
            headers.update(self._get_auth_headers())

        req = urllib.request.Request(url, headers=headers)
        with self._opener.open(req) as resp:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            data = resp.read()

        # Decompress gzip if needed
        if "gzip" in content_type.lower():
            try:
                data = gzip.decompress(data)
            except Exception:
                pass

        return data, content_type


# ─────────────────────────────────────────────
# Public API (no authentication)
# ─────────────────────────────────────────────

class RainViewerPublicAPI:
    """
    Public RainViewer API - No authentication required.

    Base URL: https://api.rainviewer.com/public/
    Tile URL: https://tilecache.rainviewer.com/v2/radar/{hash}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png

    This is the "official" documented public API:
    https://www.rainviewer.com/api.html
    """

    def __init__(self, http_client: Optional[RainViewerHTTPClient] = None):
        self._http = http_client or RainViewerHTTPClient(auto_auth=False)

    def get_weather_maps(self) -> Dict[str, Any]:
        """
        Get current radar and satellite frame paths.

        Endpoint: GET https://api.rainviewer.com/public/weather-maps.json

        Returns:
            {
                "version": "2.0",
                "generated": <unix_timestamp>,
                "host": "https://tilecache.rainviewer.com",
                "radar": {
                    "past": [{"time": <timestamp>, "path": "/v2/radar/<hash>"}, ...],
                    "nowcast": [...]  # Short-term forecast frames
                },
                "satellite": {
                    "infrared": [{"time": <timestamp>, "path": "/v2/satellite/<hash>"}, ...]
                }
            }

        Notes:
            - past: Last ~13 frames (about 2 hours of data, updates every 10 min)
            - nowcast: Precipitation forecast for next ~30 min (when available)
            - satellite.infrared: Usually empty; use /site/maps for satellite data
        """
        req = urllib.request.Request(PUBLIC_WEATHER_MAPS_URL)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def get_radar_frames(self) -> List[RadarFrame]:
        """
        Get list of available radar frames (past + nowcast).

        Returns:
            List of RadarFrame objects, ordered oldest to newest.
        """
        data = self.get_weather_maps()
        frames = []
        for item in data.get("radar", {}).get("past", []):
            frames.append(RadarFrame(time=item["time"], path=item["path"], frame_type="radar"))
        for item in data.get("radar", {}).get("nowcast", []):
            frames.append(RadarFrame(time=item["time"], path=item["path"], frame_type="radar"))
        return frames

    def get_tile_url(
        self,
        path: str,
        z: int,
        x: int,
        y: int,
        size: int = 256,
        color: int = 4,
        smooth: int = 1,
        snow: int = 0,
        fmt: str = "png",
    ) -> str:
        """
        Build a radar/satellite tile URL.

        Tilecache PNG format (public, most compatible):
          https://tilecache.rainviewer.com{path}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png

        CDN WebP format (higher quality, smaller size):
          https://cdn.rainviewer.com{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp

        Args:
            path: Frame path from weather-maps.json (e.g. "/v2/radar/abc123")
            z: Zoom level (0-14)
            x: Tile X coordinate
            y: Tile Y coordinate
            size: Tile size (256 or 512 pixels)
            color: Color scheme (0-8, see COLOR_SCHEMES dict)
            smooth: Smoothing filter (1=on, 0=off)
            snow: Snow mode - show snow as blue/white (1=on, 0=off)
            fmt: "png" (tilecache) or "webp" (CDN)

        Returns:
            Full URL string for the tile.
        """
        if fmt == "webp":
            return f"{CDN_HOST}{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp"
        return f"{TILECACHE_HOST}{path}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png"

    def download_tile(
        self,
        path: str,
        z: int,
        x: int,
        y: int,
        size: int = 256,
        color: int = 4,
        smooth: int = 1,
        snow: int = 0,
        fmt: str = "png",
    ) -> Tuple[bytes, str]:
        """
        Download a radar/satellite tile image.

        Returns:
            Tuple of (image_bytes, content_type)
        """
        url = self.get_tile_url(path, z, x, y, size, color, smooth, snow, fmt)
        return self._http.request_binary(url, authenticated=False)

    def get_map_style_url(self, style: str = "m2") -> str:
        """
        Get MapLibre GL style JSON URL.

        Args:
            style: One of "m2" (light), "m2_dark" (dark), "m2_satellite" (satellite)

        Returns:
            URL to the MapLibre style JSON.
        """
        return f"{MAPS_HOST}/styles/{style}/style.json"

    def get_map_style(self, style: str = "m2") -> Dict[str, Any]:
        """
        Fetch MapLibre GL style JSON for rendering base maps.

        The style includes:
        - Vector tile sources (maps.rainviewer.com/data/v3/{z}/{x}/{y}.pbf)
        - Layer definitions (roads, water, terrain, labels)
        - Font/glyph URLs
        - Sprite sheet URL

        Args:
            style: Map style ("m2", "m2_dark", "m2_satellite")

        Returns:
            MapLibre GL style specification dict.
        """
        url = self.get_map_style_url(style)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())


# ─────────────────────────────────────────────
# Internal/Authenticated API
# ─────────────────────────────────────────────

class RainViewerInternalAPI:
    """
    RainViewer Internal/Authenticated API.

    Base URL: https://api.rainviewer.com/site/

    Authentication:
        1. GET /site/auth/session -> X-Rv-Sid header (session ID)
        2. POST /site/auth/api-key -> data.apiKey (temporary token)
        3. All /site/* requests require X-RV-Token + x-rv-sid headers
        4. Tokens expire in ~2 hours (expiresAt field)

    This API is used by the RainViewer website and apps but is not
    officially documented for external use.
    """

    def __init__(self, http_client: Optional[RainViewerHTTPClient] = None):
        self._http = http_client or RainViewerHTTPClient(auto_auth=True)

    # ── Authentication ────────────────────────

    def get_session(self) -> Dict[str, Any]:
        """
        Create or retrieve a session.

        Endpoint: GET /site/auth/session

        Returns:
            {
                "hasSession": true,
                "okUntil": <timestamp_seconds>,  # 0 = no expiry
                "tsOkUntil": <timestamp_seconds>
            }

        The response also contains X-Rv-Sid header with session ID
        and sets a sid cookie.
        """
        req = urllib.request.Request(
            f"{API_BASE}/site/auth/session",
            headers={}
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
            sid = resp.headers.get("X-Rv-Sid")
            if sid:
                self._http._auth.session_id = sid
            return body.get("data", body)

    def get_api_key(self) -> Dict[str, Any]:
        """
        Obtain a temporary API key.

        Endpoint: POST /site/auth/api-key

        Requires: Valid session (X-Rv-Sid header)

        Returns:
            {
                "apiKey": "rv-...",         # The Bearer-like token
                "expiresAt": <timestamp>,   # When the key expires
                "okUntil": <timestamp>,     # Session validity
                "tsOkUntil": <timestamp>
            }

        Notes:
            - Keys are short-lived (~2 hours based on expiresAt)
            - The session (okUntil) may last longer
            - Error code 100204 = no session (need to call get_session first)
        """
        if not self._http._auth.session_id:
            self.get_session()

        req = urllib.request.Request(
            f"{API_BASE}/site/auth/api-key",
            method="POST",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "x-rv-sid": self._http._auth.session_id or "",
            },
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())

        data = body.get("data", {})
        api_key = data.get("apiKey")
        expires_at = data.get("expiresAt", 0)
        ok_until = data.get("okUntil", 0)

        if api_key:
            self._http._auth.api_key = api_key
            self._http._auth.api_key_expires_at = expires_at or int(time.time()) + 7200
            if ok_until:
                self._http._auth.session_ok_until = ok_until

        return data

    # ── Maps / Radar / Satellite ──────────────

    def get_maps(self) -> Dict[str, Any]:
        """
        Get authenticated radar AND satellite frame paths.

        Endpoint: GET /site/maps

        Returns:
            {
                "radar": {
                    "past": [{"time": <timestamp>, "path": "/v2/radar/<hash>"}, ...],
                    "future": []  # Reserved for forecast
                },
                "satellite": {
                    "past": [{"time": <timestamp>, "path": "/v2/satellite/<hash>"}, ...]
                }
            }

        Notes:
            - Unlike the public API, this includes satellite paths
            - Satellite tiles use CDN: https://cdn.rainviewer.com{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp
            - ~13 frames covering ~2 hours, updated every 10 minutes
            - The ?layer=radar or ?layer=sat param can be used but returns same data
        """
        return self._http.request_json("/site/maps")

    def get_radar_frames(self) -> List[RadarFrame]:
        """
        Get available radar frames from authenticated API.

        Returns:
            List of RadarFrame objects (radar type), ordered oldest to newest.
        """
        data = self.get_maps()
        frames = []
        for item in data.get("radar", {}).get("past", []):
            frames.append(RadarFrame(time=item["time"], path=item["path"], frame_type="radar"))
        return frames

    def get_satellite_frames(self) -> List[RadarFrame]:
        """
        Get available satellite (infrared) frames.

        Returns:
            List of RadarFrame objects (sat type), ordered oldest to newest.

        Notes:
            - Satellite tiles are served from CDN: cdn.rainviewer.com
            - Use the get_satellite_tile_url() method to construct URLs
        """
        data = self.get_maps()
        frames = []
        for item in data.get("satellite", {}).get("past", []):
            frames.append(RadarFrame(time=item["time"], path=item["path"], frame_type="sat"))
        return frames

    def get_satellite_tile_url(
        self,
        path: str,
        z: int,
        x: int,
        y: int,
        size: int = 512,
        smooth: int = 1,
        snow: int = 0,
    ) -> str:
        """
        Build a satellite tile URL (uses CDN with WebP format).

        Format:
          https://cdn.rainviewer.com{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp

        Args:
            path: Satellite frame path (e.g. "/v2/satellite/abc123")
            z: Zoom level (0-14)
            x: Tile X coordinate
            y: Tile Y coordinate
            size: Tile size (256 or 512)
            smooth: Smoothing (1=on, 0=off)
            snow: Snow mode (1=on, 0=off)

        Returns:
            Full CDN URL string.
        """
        return f"{CDN_HOST}{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp"

    # ── Radar Station Database ────────────────

    def get_radars_database(self) -> List[RadarStation]:
        """
        Get the full database of radar stations worldwide.

        Endpoint: GET /site/radars/database

        Returns:
            List of RadarStation objects with all 1000+ global radar stations.

        Fields per station:
            - id: Station identifier (e.g. "KABR", "AU31")
            - country: ISO 2-letter country code
            - state: State/region code
            - location: City/location name
            - status: 1=active, 0=inactive
            - latitude, longitude: Station coordinates
            - range_km: Radar range in km
            - image_id: Internal image identifier
            - is_pro: True if Pro subscription required
            - last_updated: Unix timestamp of last data update
            - frequency: Update frequency in seconds
            - is_offline: True if currently offline

        Notes:
            - 1000+ stations across 80+ countries
            - Many US radars (NEXRAD) require Pro subscription
            - Active radars: ~800 of 1016 total
        """
        data = self._http.request_json("/site/radars/database")
        stations = []
        for r in data.get("radars", []):
            stations.append(RadarStation(
                id=r["id"],
                country=r.get("country", ""),
                state=r.get("state", ""),
                location=r.get("location", ""),
                status=r.get("status", 0),
                latitude=r.get("latitude", 0.0),
                longitude=r.get("longitude", 0.0),
                range_km=r.get("range", 0),
                image_id=r.get("imageId", ""),
                is_pro=r.get("isPro", False),
                last_updated=r.get("lastUpdated"),
                frequency=r.get("frequency"),
                is_offline=r.get("isOffline", True),
            ))
        return stations

    def get_radar_products(self, radar_id: str) -> List[Dict[str, Any]]:
        """
        Get available products for a specific radar station.

        Endpoint: GET /site/radars/{radar_id}/products

        Args:
            radar_id: Radar station ID (e.g. "AU31", "KABR")

        Returns:
            List of product dicts:
            [{
                "id": "map",            # Product identifier
                "product": "BR",        # Product code (BR=Base Reflectivity, etc)
                "elevation": [],        # Elevation angles
                "boundingBox": [minLat, minLon, maxLat, maxLon],
                "formats": ["webp"],    # Available image formats
                "version": 102,
                "types": [],
                "productDisplayName": "BR - Base Reflectivity"
            }]

        Notes:
            - Pro radars return empty list unless authenticated with Pro token
            - Free radars typically have a "map" product
        """
        return self._http.request_json(f"/site/radars/{radar_id}/products")

    def get_radar_product_timestamps(
        self, radar_id: str, product_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get available timestamps for a radar product.

        Endpoint: GET /site/radars/{radar_id}/products/{product_id}

        Args:
            radar_id: Radar station ID (e.g. "AU31")
            product_id: Product ID from get_radar_products() (e.g. "map")

        Returns:
            List of available frames:
            [{"timestamp": <unix_timestamp>, "width": <pixels>, "height": <pixels>}]
        """
        return self._http.request_json(f"/site/radars/{radar_id}/products/{product_id}")

    def get_radar_product_image(
        self,
        radar_id: str,
        product_id: str,
        timestamp: int,
    ) -> Tuple[bytes, str]:
        """
        Download a radar product image for a specific timestamp.

        Endpoint: GET /site/radars/{radar_id}/products/{product_id}/{timestamp}

        Args:
            radar_id: Radar station ID
            product_id: Product ID (e.g. "map")
            timestamp: Unix timestamp from get_radar_product_timestamps()

        Returns:
            Tuple of (image_bytes, content_type)
            Content-Type is typically "image/webp"

        Notes:
            - Returns individual station radar image (not a map tile)
            - The image shows the full radar sweep area
        """
        url = f"{API_BASE}/site/radars/{radar_id}/products/{product_id}/{timestamp}"
        return self._http.request_binary(url, authenticated=True)

    # ── Weather Alerts ────────────────────────

    def get_alerts(
        self,
        bbox: Optional[str] = None,
    ) -> List[WeatherAlert]:
        """
        Get active severe weather alerts.

        Endpoint: GET /site/alerts
        Endpoint: GET /site/alerts?bbox={minLat},{minLon},{maxLat},{maxLon}

        Args:
            bbox: Optional bounding box filter as "minLat,minLon,maxLat,maxLon"
                  e.g. "25,-125,50,-65" for continental US

        Returns:
            List of WeatherAlert objects.

        Alert fields:
            - id: UUID
            - kind: "Met" (meteorological)
            - severity: "Minor", "Moderate", "Severe", "Extreme"
            - category: "Flood", "Wind", "Tornado", "Winter Storm", etc.
            - type: Specific type (e.g. "Coastal Flood Statement")
            - certainty: "Possible", "Likely", "Observed"
            - urgency: "Immediate", "Expected", "Future"
            - event: Official event name
            - starts, ends: Unix timestamps
            - title: Alert title
            - description: Full alert text
            - instruction: Safety instructions
            - area: List of affected area polygons
            - source: Data source info (provider, URL)
            - added, updated, expires: Timestamps
            - isCancelled: Whether the alert was cancelled
            - locale: Language code (e.g. "en-US")

        Notes:
            - Returns global alerts (typically ~50-100 active)
            - Use bbox to filter by geographic area
            - Query param ?area=<value> also works (same as no filter)
        """
        params = {}
        if bbox:
            params["bbox"] = bbox

        data = self._http.request_json("/site/alerts", params=params if params else None)
        alerts = []
        items = data if isinstance(data, list) else []
        for item in items:
            alerts.append(WeatherAlert(
                id=item.get("id", ""),
                kind=item.get("kind", ""),
                severity=item.get("severity", ""),
                category=item.get("category", ""),
                alert_type=item.get("type", ""),
                certainty=item.get("certainty", ""),
                urgency=item.get("urgency", ""),
                event=item.get("event", ""),
                starts=item.get("starts", 0),
                ends=item.get("ends", 0),
                title=item.get("title", ""),
                description=item.get("description", ""),
                instruction=item.get("instruction", ""),
                area=item.get("area", []),
                source=item.get("source", {}),
                raw=item,
            ))
        return alerts

    def get_alert_by_id(self, alert_id: str) -> Optional[WeatherAlert]:
        """
        Get a specific weather alert by UUID.

        Endpoint: GET /site/alerts/{alert_id}

        Args:
            alert_id: UUID of the alert

        Returns:
            WeatherAlert object or None if not found.
        """
        try:
            data = self._http.request_json(f"/site/alerts/{alert_id}")
            if not data:
                return None
            item = data if isinstance(data, dict) else {}
            return WeatherAlert(
                id=item.get("id", alert_id),
                kind=item.get("kind", ""),
                severity=item.get("severity", ""),
                category=item.get("category", ""),
                alert_type=item.get("type", ""),
                certainty=item.get("certainty", ""),
                urgency=item.get("urgency", ""),
                event=item.get("event", ""),
                starts=item.get("starts", 0),
                ends=item.get("ends", 0),
                title=item.get("title", ""),
                description=item.get("description", ""),
                instruction=item.get("instruction", ""),
                area=item.get("area", []),
                source=item.get("source", {}),
                raw=item,
            )
        except Exception:
            return None

    def get_alerts_for_area(self, area_name: str = "") -> List[WeatherAlert]:
        """
        Get alerts optionally filtered by area string (appended to path).

        The JS code uses: /site/alerts + t where t is a country/region filter.
        When t is empty, returns all global alerts.

        Endpoint: GET /site/alerts{area_suffix}
        Example:  GET /site/alerts  (all)

        Args:
            area_name: Area filter string (empty = all alerts)

        Returns:
            List of WeatherAlert objects.
        """
        path = f"/site/alerts{area_name}" if area_name else "/site/alerts"
        data = self._http.request_json(path)
        alerts = []
        items = data if isinstance(data, list) else []
        for item in items:
            alerts.append(WeatherAlert(
                id=item.get("id", ""),
                kind=item.get("kind", ""),
                severity=item.get("severity", ""),
                category=item.get("category", ""),
                alert_type=item.get("type", ""),
                certainty=item.get("certainty", ""),
                urgency=item.get("urgency", ""),
                event=item.get("event", ""),
                starts=item.get("starts", 0),
                ends=item.get("ends", 0),
                title=item.get("title", ""),
                description=item.get("description", ""),
                instruction=item.get("instruction", ""),
                area=item.get("area", []),
                source=item.get("source", {}),
                raw=item,
            ))
        return alerts

    # ── Tropical Storms / Hurricanes ──────────

    def get_active_storms(self) -> List[StormTrack]:
        """
        Get active tropical storms and hurricanes worldwide.

        Endpoint: GET /site/storms

        Returns:
            List of StormTrack objects with track, current position, and forecast.

        StormTrack fields:
            - name: Storm name (e.g. "NARELLE")
            - category: Maximum category reached (e.g. "H4", "TS", "TD")
            - current: {
                "location": {"latitude": float, "longitude": float},
                "category": "TS"|"H1"|"H2"|"H3"|"H4"|"H5",
                "movement": {"direction": <degrees>, "speed": <km/h>},
                "wind": {"speed": <km/h>}
              }
            - track: Historical positions [{"location": {...}, "category": ...}, ...]
            - forecast: Predicted future positions
            - cone: Forecast uncertainty cone

        Storm categories:
            TD  = Tropical Depression (< 63 km/h)
            TS  = Tropical Storm (63-118 km/h)
            H1  = Hurricane Cat 1 (119-153 km/h)
            H2  = Hurricane Cat 2 (154-177 km/h)
            H3  = Hurricane Cat 3 (178-208 km/h)
            H4  = Hurricane Cat 4 (209-251 km/h)
            H5  = Hurricane Cat 5 (> 252 km/h)

        Notes:
            - Returns currently active global storms
            - Query params ?country=XX or ?active=1 accepted but don't filter
        """
        data = self._http.request_json("/site/storms")
        storms = []
        items = data if isinstance(data, list) else []
        for item in items:
            storms.append(StormTrack(
                name=item.get("name", ""),
                category=item.get("category", ""),
                current=item.get("current", {}),
                track=item.get("track", []),
                forecast=item.get("forecast", []),
                cone=item.get("cone", []),
            ))
        return storms


# ─────────────────────────────────────────────
# High-level Convenience Client
# ─────────────────────────────────────────────

class RainViewerClient:
    """
    High-level RainViewer client combining public and internal APIs.

    Usage:
        client = RainViewerClient()

        # Get latest radar frames
        frames = client.get_latest_radar_frames()

        # Download a tile
        data, ct = client.download_radar_tile(frames[-1].path, z=5, x=10, y=12)

        # Get weather alerts
        alerts = client.get_alerts(bbox="25,-125,50,-65")

        # Get active storms
        storms = client.get_active_storms()
    """

    def __init__(self):
        self._http = RainViewerHTTPClient(auto_auth=True)
        self.public = RainViewerPublicAPI(http_client=self._http)
        self.internal = RainViewerInternalAPI(http_client=self._http)

    # ── Radar tiles ───────────────────────────

    def get_latest_radar_frames(
        self,
        use_authenticated: bool = True,
    ) -> List[RadarFrame]:
        """
        Get available radar frames.

        Args:
            use_authenticated: Use internal API (recommended) for more data.

        Returns:
            List of RadarFrame objects, newest last.
        """
        if use_authenticated:
            return self.internal.get_radar_frames()
        return self.public.get_radar_frames()

    def get_latest_satellite_frames(self) -> List[RadarFrame]:
        """
        Get available satellite (infrared) frames.

        Returns:
            List of RadarFrame objects with type="sat", newest last.
        """
        return self.internal.get_satellite_frames()

    def download_radar_tile(
        self,
        path: str,
        z: int,
        x: int,
        y: int,
        size: int = 256,
        color: int = 4,
        smooth: int = 1,
        snow: int = 0,
        fmt: str = "png",
    ) -> Tuple[bytes, str]:
        """
        Download a radar map tile.

        Args:
            path: Radar frame path (e.g. "/v2/radar/abc123")
            z, x, y: Tile coordinates
            size: 256 or 512
            color: Color scheme (0-8, see COLOR_SCHEMES)
            smooth: Smoothing (1=on)
            snow: Snow mode (1=on)
            fmt: "png" or "webp"

        Returns:
            (image_bytes, content_type)

        URL formats:
            PNG:  https://tilecache.rainviewer.com{path}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png
            WebP: https://cdn.rainviewer.com{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp
        """
        return self.public.download_tile(path, z, x, y, size, color, smooth, snow, fmt)

    def download_satellite_tile(
        self,
        path: str,
        z: int,
        x: int,
        y: int,
        size: int = 512,
        smooth: int = 1,
    ) -> Tuple[bytes, str]:
        """
        Download a satellite tile image.

        Args:
            path: Satellite frame path (e.g. "/v2/satellite/abc123")
            z, x, y: Tile coordinates
            size: 256 or 512
            smooth: Smoothing (1=on)

        Returns:
            (image_bytes, content_type)

        URL format:
            https://cdn.rainviewer.com{path}/{size}/{z}/{x}/{y}/255/{smooth}_1_0_0.webp
        """
        url = self.internal.get_satellite_tile_url(path, z, x, y, size, smooth)
        return self._http.request_binary(url, authenticated=False)

    # ── Weather data ──────────────────────────

    def get_alerts(
        self,
        bbox: Optional[str] = None,
    ) -> List[WeatherAlert]:
        """
        Get active severe weather alerts.

        Args:
            bbox: Optional bounding box "minLat,minLon,maxLat,maxLon"
                  Example: "25,-125,50,-65" for continental US

        Returns:
            List of WeatherAlert objects.
        """
        return self.internal.get_alerts(bbox=bbox)

    def get_active_storms(self) -> List[StormTrack]:
        """
        Get active tropical storms and hurricanes.

        Returns:
            List of StormTrack objects.
        """
        return self.internal.get_active_storms()

    def get_radar_stations(
        self,
        country: Optional[str] = None,
        active_only: bool = True,
        exclude_pro: bool = False,
    ) -> List[RadarStation]:
        """
        Get radar station database.

        Args:
            country: Optional ISO 2-letter country code filter (e.g. "US", "AU")
            active_only: If True, exclude offline stations
            exclude_pro: If True, exclude Pro-only stations

        Returns:
            List of RadarStation objects.
        """
        stations = self.internal.get_radars_database()
        if country:
            stations = [s for s in stations if s.country == country.upper()]
        if active_only:
            stations = [s for s in stations if not s.is_offline]
        if exclude_pro:
            stations = [s for s in stations if not s.is_pro]
        return stations

    # ── Map tiles ─────────────────────────────

    def get_base_map_style(self, dark: bool = False, satellite: bool = False) -> Dict:
        """
        Get MapLibre GL base map style JSON.

        Args:
            dark: Use dark theme
            satellite: Use satellite imagery base

        Returns:
            MapLibre GL style specification.
        """
        if satellite:
            return self.public.get_map_style("m2_satellite")
        if dark:
            return self.public.get_map_style("m2_dark")
        return self.public.get_map_style("m2")

    def get_coverage_layer_info(self) -> Dict[str, Any]:
        """
        Get information about radar coverage areas.

        Note: Coverage data is embedded in the map style layers.
        The map tile source for coverage polygons is at:
          https://maps.rainviewer.com/data/v3/{z}/{x}/{y}.pbf (vector tiles, zoom 0-14)

        Returns:
            Dict with tile source info.
        """
        return {
            "vector_tiles": {
                "url": "https://maps.rainviewer.com/data/v3.json",
                "tiles": ["https://maps.rainviewer.com/data/v3/{z}/{x}/{y}.pbf"],
                "minzoom": 0,
                "maxzoom": 14,
            },
            "places": {
                "url": "https://maps.rainviewer.com/data/places.json",
                "tiles": ["https://maps.rainviewer.com/data/places/{z}/{x}/{y}.pbf"],
            },
            "coastlines": {
                "url": "https://maps.rainviewer.com/data/coastlines.json",
                "tiles": ["https://maps.rainviewer.com/data/coastlines/{z}/{x}/{y}.pbf"],
            },
            "glyphs": "https://maps.rainviewer.com/fonts/{fontstack}/{range}.pbf",
            "sprites": {
                "m2": "https://maps.rainviewer.com/styles/m2/sprite",
                "m2_dark": "https://maps.rainviewer.com/styles/m2_dark/sprite",
                "m2_satellite": "https://maps.rainviewer.com/styles/m2_satellite/sprite",
            }
        }


# ─────────────────────────────────────────────
# Tile Coordinate Utilities
# ─────────────────────────────────────────────

def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    """
    Convert latitude/longitude to tile (x, y) coordinates at a given zoom level.

    Args:
        lat: Latitude in decimal degrees (-90 to 90)
        lon: Longitude in decimal degrees (-180 to 180)
        zoom: Tile zoom level (0-14)

    Returns:
        Tuple of (x, y) tile coordinates.
    """
    import math
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_lat_lon(x: int, y: int, zoom: int) -> Tuple[float, float]:
    """
    Convert tile (x, y) coordinates at a zoom level to the NW corner lat/lon.

    Args:
        x: Tile X coordinate
        y: Tile Y coordinate
        zoom: Tile zoom level

    Returns:
        Tuple of (latitude, longitude) for the NW corner of the tile.
    """
    import math
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def get_tiles_for_bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    zoom: int,
) -> List[Tuple[int, int]]:
    """
    Get all tile coordinates covering a bounding box at a zoom level.

    Args:
        min_lat, min_lon: SW corner
        max_lat, max_lon: NE corner
        zoom: Tile zoom level

    Returns:
        List of (x, y) tile coordinate tuples.
    """
    x_min, y_max = lat_lon_to_tile(min_lat, min_lon, zoom)  # SW = high y
    x_max, y_min = lat_lon_to_tile(max_lat, max_lon, zoom)  # NE = low y
    tiles = []
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            tiles.append((x, y))
    return tiles


# ─────────────────────────────────────────────
# Example Usage
# ─────────────────────────────────────────────

def example_public_api():
    """Example: Using the public API (no auth)."""
    print("=" * 60)
    print("PUBLIC API EXAMPLE (No auth required)")
    print("=" * 60)

    public = RainViewerPublicAPI()

    # Get available radar frames
    data = public.get_weather_maps()
    past = data["radar"]["past"]
    print(f"\nAvailable radar frames: {len(past)}")
    if past:
        latest = past[-1]
        print(f"Latest frame: {latest['time']} -> {latest['path']}")

        # Build tile URL for New York area (z=5, x=9, y=12)
        url_png = public.get_tile_url(latest["path"], z=5, x=9, y=12, color=4, smooth=1)
        url_webp = public.get_tile_url(latest["path"], z=5, x=9, y=12, fmt="webp")
        print(f"\nPNG tile: {url_png}")
        print(f"WebP tile: {url_webp}")

        # Download tile
        data_bytes, ct = public.download_tile(latest["path"], z=5, x=9, y=12)
        print(f"Downloaded: {len(data_bytes)} bytes ({ct})")


def example_authenticated_api():
    """Example: Using the authenticated internal API."""
    print("\n" + "=" * 60)
    print("AUTHENTICATED API EXAMPLE")
    print("=" * 60)

    client = RainViewerClient()

    # Radar frames (authenticated = more data)
    radar_frames = client.get_latest_radar_frames()
    print(f"\nRadar frames: {len(radar_frames)}")
    if radar_frames:
        latest = radar_frames[-1]
        print(f"Latest: {latest.get_timestamp_str()} -> {latest.path}")

    # Satellite frames
    sat_frames = client.get_latest_satellite_frames()
    print(f"Satellite frames: {len(sat_frames)}")
    if sat_frames:
        latest_sat = sat_frames[-1]
        url = client.internal.get_satellite_tile_url(latest_sat.path, z=3, x=4, y=3)
        print(f"Satellite tile URL: {url}")

    # Weather alerts
    print("\nFetching weather alerts...")
    alerts = client.get_alerts()
    print(f"Active alerts: {len(alerts)}")
    if alerts:
        a = alerts[0]
        print(f"  Example: [{a.severity}] {a.title[:60]}")
        print(f"  Category: {a.category}, Certainty: {a.certainty}")

    # Alerts for US
    us_alerts = client.get_alerts(bbox="25,-125,50,-65")
    print(f"US alerts (bbox): {len(us_alerts)}")

    # Active storms
    storms = client.get_active_storms()
    print(f"\nActive tropical storms: {len(storms)}")
    for storm in storms:
        cat = storm.current.get("category", "?")
        wind = storm.current.get("wind", {}).get("speed", "?")
        print(f"  {storm.name} (Cat {cat}, {wind} km/h)")

    # Radar stations
    au_stations = client.get_radar_stations(country="AU", active_only=True, exclude_pro=True)
    print(f"\nActive free Australian radars: {len(au_stations)}")
    if au_stations:
        r = au_stations[0]
        print(f"  Example: {r.id} - {r.location} ({r.latitude}, {r.longitude})")

        # Get products for this radar
        products = client.internal.get_radar_products(r.id)
        print(f"  Products: {[p.get('id') for p in products]}")

        if products:
            prod_id = products[0]["id"]
            timestamps = client.internal.get_radar_product_timestamps(r.id, prod_id)
            print(f"  Timestamps available: {len(timestamps)}")

            if timestamps:
                ts = timestamps[-1]["timestamp"]
                img_data, ct = client.internal.get_radar_product_image(r.id, prod_id, ts)
                print(f"  Latest image: {len(img_data)} bytes ({ct})")


def example_tile_calculation():
    """Example: Tile coordinate calculations."""
    print("\n" + "=" * 60)
    print("TILE COORDINATE EXAMPLE")
    print("=" * 60)

    # New York City
    lat, lon = 40.7128, -74.0060
    zoom = 8
    x, y = lat_lon_to_tile(lat, lon, zoom)
    print(f"\nNew York City ({lat}, {lon}) at zoom {zoom}:")
    print(f"  Tile: x={x}, y={y}")

    # London
    lat, lon = 51.5074, -0.1278
    x, y = lat_lon_to_tile(lat, lon, zoom)
    print(f"\nLondon ({lat}, {lon}) at zoom {zoom}:")
    print(f"  Tile: x={x}, y={y}")

    # Get tiles for continental US bounding box at zoom 5
    tiles = get_tiles_for_bbox(25, -125, 50, -65, zoom=5)
    print(f"\nTiles for continental US at zoom 5: {len(tiles)} tiles")


if __name__ == "__main__":
    example_public_api()
    example_authenticated_api()
    example_tile_calculation()
