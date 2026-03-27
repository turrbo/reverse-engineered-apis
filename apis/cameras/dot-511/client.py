"""
DOT 511 Unified Camera Client
==============================
A unified Python client for accessing highway traffic camera systems across
multiple US states using the Iteris/RITIS platform REST API.

Supported states:
  - New York (511ny.org)
  - Wisconsin (511wi.gov)
  - Pennsylvania (511pa.com)
  - Alaska (511.alaska.gov)
  - Utah (udottraffic.utah.gov)
  - Minnesota (511mn.org)
  - Virginia (511va.org)
  - Iowa (511ia.org)

API Pattern:
  All states share the same underlying Iteris/RITIS platform with two API generations:
    - v1 (legacy, NY only): GET /api/getcameras?key={key}&format=json
    - v2 (current):         GET /api/v2/get/cameras?key={key}&format=json

Authentication:
  - Developer API key required for all states
  - Register at each state's /my511/register or /developers/help page
  - Key passed as query parameter: ?key={your_api_key}
  - Rate limit: 10 requests per 60 seconds (per state)

Response Formats:
  v1 (New York legacy): JSON array with fields:
    ID, Name, RoadwayName, DirectionOfTravel, Latitude, Longitude,
    Url (detail page), VideoUrl (HLS .m3u8 or MJPEG), Disabled, Blocked

  v2 (all states): JSON array with fields:
    Id, Source, SourceId, Roadway, Direction, Latitude, Longitude,
    Location, SortOrder, Views (array of camera view objects)

  Each view in Views contains:
    Url (HLS .m3u8 stream URL), Status, Description

HLS Stream Patterns:
  New York:   https://s{N}.nysdot.skyvdn.com:443/rtplive/{CAM_ID}/playlist.m3u8
  Wisconsin:  https://cctv1.dot.wi.gov:443/rtplive/{CAM_ID}/playlist.m3u8
  Other:      Varies, included in Views[].Url field

Usage:
  client = DOT511Client()

  # List all cameras in a state
  cameras = client.get_cameras("ny", api_key="YOUR_NY_KEY")

  # Get just the stream URL for a camera
  stream = client.get_camera_stream_url("ny", "Skyline-10012", api_key="YOUR_NY_KEY")

  # Filter by roadway
  i90_cams = client.get_cameras("ny", api_key="...", roadway="I-90")

  # Pre-configure keys
  client = DOT511Client(api_keys={"ny": "KEY1", "wi": "KEY2"})
  cameras = client.get_cameras("wi")
"""

import time
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode
from dataclasses import dataclass, field

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import urllib.request
    import urllib.error
    import json as _json
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State Configuration
# ---------------------------------------------------------------------------

STATE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "ny": {
        "name": "New York",
        "base_url": "https://511ny.org",
        "api_version": "v1",       # NY uses legacy v1 endpoint
        "cameras_endpoint": "/api/getcameras",
        "developer_page": "https://511ny.org/developers/help",
        "register_url": "https://511ny.org/my511/register",
        "hls_host_pattern": "https://s{N}.nysdot.skyvdn.com:443/rtplive/{cam_id}/playlist.m3u8",
        "notes": "v1 API; VideoUrl field contains direct HLS .m3u8 URL or MJPEG URL",
    },
    "wi": {
        "name": "Wisconsin",
        "base_url": "https://511wi.gov",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://www.511wi.gov/developers/doc",
        "register_url": "https://www.511wi.gov/my511/register",
        "hls_host_pattern": "https://cctv1.dot.wi.gov:443/rtplive/{cam_id}/playlist.m3u8",
        "notes": "v2 API; HLS streams at cctv1.dot.wi.gov",
    },
    "pa": {
        "name": "Pennsylvania",
        "base_url": "https://511pa.com",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://www.511pa.com/developers/doc",
        "register_url": "https://www.511pa.com/my511/register",
        "hls_host_pattern": None,
        "notes": "v2 API; stream URLs provided in Views[].Url",
    },
    "ak": {
        "name": "Alaska",
        "base_url": "https://511.alaska.gov",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://511.alaska.gov/developers/doc",
        "register_url": "https://511.alaska.gov/my511/register",
        "hls_host_pattern": None,
        "notes": "v2 API; stream URLs provided in Views[].Url",
    },
    "ut": {
        "name": "Utah",
        "base_url": "https://www.udottraffic.utah.gov",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://udottraffic.utah.gov/developers/doc",
        "register_url": "https://udottraffic.utah.gov/my511/register",
        "hls_host_pattern": None,
        "notes": "v2 API; UDOT Traffic portal",
    },
    "mn": {
        "name": "Minnesota",
        "base_url": "https://www.511mn.org",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://www.511mn.org/developers/doc",
        "register_url": "https://www.511mn.org/my511/register",
        "hls_host_pattern": None,
        "notes": "v2 API; MnDOT Traffic portal",
    },
    "va": {
        "name": "Virginia",
        "base_url": "https://www.511va.org",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://www.511va.org/developers/doc",
        "register_url": "https://www.511va.org/my511/register",
        "hls_host_pattern": None,
        "notes": "v2 API; uses bot-protection JWT challenge on unauthenticated requests",
    },
    "ia": {
        "name": "Iowa",
        "base_url": "https://511ia.org",
        "api_version": "v2",
        "cameras_endpoint": "/api/v2/get/cameras",
        "developer_page": "https://511ia.org/developers/doc",
        "register_url": "https://511ia.org/my511/register",
        "hls_host_pattern": None,
        "notes": "v2 API; Iowa DOT / Iowa State Patrol",
    },
}

# Allow common aliases
STATE_ALIASES: Dict[str, str] = {
    "new_york": "ny",
    "newyork": "ny",
    "wisconsin": "wi",
    "pennsylvania": "pa",
    "alaska": "ak",
    "utah": "ut",
    "minnesota": "mn",
    "virginia": "va",
    "iowa": "ia",
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class CameraView:
    """A single view (angle/stream) associated with a camera."""
    url: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CameraView":
        return cls(
            url=d.get("Url") or d.get("url"),
            status=d.get("Status") or d.get("status"),
            description=d.get("Description") or d.get("description"),
        )


@dataclass
class Camera:
    """
    Unified camera record normalised across v1 and v2 API responses.

    For v1 (NY legacy), VideoUrl is the stream URL directly.
    For v2, stream URLs are in views[].url.
    """
    state: str
    camera_id: str
    name: str
    roadway: Optional[str] = None
    direction: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    detail_url: Optional[str] = None          # link to 511 website detail page
    video_url: Optional[str] = None           # primary stream URL (v1 direct, v2 first view)
    views: List[CameraView] = field(default_factory=list)
    disabled: bool = False
    blocked: bool = False
    source: Optional[str] = None
    source_id: Optional[str] = None
    sort_order: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None      # original API payload

    @property
    def is_active(self) -> bool:
        """True if camera is not disabled and not blocked."""
        return not self.disabled and not self.blocked

    @property
    def has_stream(self) -> bool:
        """True if at least one HLS stream URL is available."""
        if self.video_url and ("m3u8" in self.video_url or "rtplive" in self.video_url):
            return True
        return any(
            v.url and ("m3u8" in v.url or "rtplive" in v.url)
            for v in self.views
        )

    @property
    def stream_urls(self) -> List[str]:
        """All HLS/MJPEG stream URLs for this camera."""
        urls = []
        if self.video_url:
            urls.append(self.video_url)
        for v in self.views:
            if v.url and v.url not in urls:
                urls.append(v.url)
        return urls

    def __repr__(self) -> str:
        active = "active" if self.is_active else "disabled"
        stream = "stream" if self.has_stream else "no-stream"
        return f"Camera({self.state.upper()}:{self.camera_id!r} | {self.name!r} | {active} | {stream})"


def _parse_v1_camera(state: str, raw: Dict[str, Any]) -> Camera:
    """Parse a New York (v1) API camera record."""
    video_url = raw.get("VideoUrl")
    views = []
    if video_url:
        views.append(CameraView(url=video_url))
    return Camera(
        state=state,
        camera_id=str(raw.get("ID", "")),
        name=raw.get("Name", ""),
        roadway=raw.get("RoadwayName"),
        direction=raw.get("DirectionOfTravel"),
        latitude=raw.get("Latitude"),
        longitude=raw.get("Longitude"),
        detail_url=raw.get("Url"),
        video_url=video_url,
        views=views,
        disabled=bool(raw.get("Disabled", False)),
        blocked=bool(raw.get("Blocked", False)),
        raw=raw,
    )


def _parse_v2_camera(state: str, raw: Dict[str, Any]) -> Camera:
    """Parse a v2 API camera record (WI, PA, AK, UT, MN, VA, IA)."""
    views_raw = raw.get("Views") or raw.get("views") or []
    views = [CameraView.from_dict(v) for v in views_raw if isinstance(v, dict)]
    # Primary video URL = first view's URL
    video_url = views[0].url if views else None
    return Camera(
        state=state,
        camera_id=str(raw.get("Id", "")),
        name=raw.get("Location", raw.get("Roadway", "")),
        roadway=raw.get("Roadway"),
        direction=raw.get("Direction"),
        latitude=raw.get("Latitude"),
        longitude=raw.get("Longitude"),
        detail_url=None,
        video_url=video_url,
        views=views,
        disabled=False,   # v2 doesn't expose a disabled flag in the same way
        blocked=False,
        source=raw.get("Source"),
        source_id=raw.get("SourceId"),
        sort_order=raw.get("SortOrder"),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, params: Optional[Dict] = None, timeout: int = 30) -> Any:
    """
    Perform a GET request and return parsed JSON.
    Uses requests if available, falls back to urllib.
    Raises RuntimeError on HTTP errors.
    """
    if params:
        qs = urlencode(params)
        full_url = f"{url}?{qs}"
    else:
        full_url = url

    logger.debug("GET %s", full_url)

    if HAS_REQUESTS:
        resp = requests.get(
            full_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "DOT511Client/1.0 (Python)",
            },
        )
        if resp.status_code == 400:
            try:
                err = resp.json()
                raise RuntimeError(f"API error {resp.status_code}: {err}")
            except Exception:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()

    elif HAS_URLLIB:
        req = urllib.request.Request(
            full_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "DOT511Client/1.0 (Python)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return _json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code}: {body[:200]}") from e

    else:
        raise RuntimeError("No HTTP library available. Install 'requests': pip install requests")


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple per-state rate limiter: 10 calls / 60 seconds."""

    def __init__(self, max_calls: int = 10, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._timestamps: Dict[str, List[float]] = {}

    def wait_if_needed(self, state: str) -> None:
        now = time.monotonic()
        timestamps = self._timestamps.setdefault(state, [])
        # Remove timestamps outside the window
        cutoff = now - self.period
        self._timestamps[state] = [t for t in timestamps if t > cutoff]
        if len(self._timestamps[state]) >= self.max_calls:
            oldest = self._timestamps[state][0]
            sleep_for = self.period - (now - oldest) + 0.1
            if sleep_for > 0:
                logger.debug("Rate limit: sleeping %.1fs for state %s", sleep_for, state)
                time.sleep(sleep_for)
        self._timestamps[state].append(time.monotonic())


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class DOT511Client:
    """
    Unified client for DOT 511 highway camera APIs across multiple US states.

    All states use the Iteris/RITIS platform with identical API structure.
    New York uses the legacy v1 endpoint; all others use v2.

    Args:
        api_keys: Optional dict mapping state codes to API keys.
                  E.g. {"ny": "abc123", "wi": "def456"}
        rate_limit: If True (default), enforce 10 calls/60s per state.
        timeout: HTTP request timeout in seconds (default 30).

    Quick Start:
        client = DOT511Client(api_keys={"ny": "YOUR_KEY"})
        cameras = client.get_cameras("ny")
        for cam in cameras[:5]:
            print(cam)
    """

    def __init__(
        self,
        api_keys: Optional[Dict[str, str]] = None,
        rate_limit: bool = True,
        timeout: int = 30,
    ):
        self.api_keys: Dict[str, str] = api_keys or {}
        self.timeout = timeout
        self._rate_limiter = RateLimiter() if rate_limit else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_state(self, state: str) -> str:
        """Normalise state code: 'New York' -> 'ny', etc."""
        s = state.lower().strip().replace(" ", "_")
        s = STATE_ALIASES.get(s, s)
        if s not in STATE_CONFIGS:
            raise ValueError(
                f"Unknown state {state!r}. "
                f"Supported: {sorted(STATE_CONFIGS.keys())}"
            )
        return s

    def _get_api_key(self, state: str, api_key: Optional[str]) -> str:
        """Return the API key to use, with helpful error if missing."""
        key = api_key or self.api_keys.get(state)
        if not key:
            cfg = STATE_CONFIGS[state]
            raise ValueError(
                f"No API key for {cfg['name']}. "
                f"Pass api_key= or set api_keys['{state}'] at construction. "
                f"Register at: {cfg['register_url']}"
            )
        return key

    def _fetch_raw(self, state: str, api_key: str) -> List[Dict[str, Any]]:
        """Fetch raw camera list from the API."""
        cfg = STATE_CONFIGS[state]
        url = cfg["base_url"] + cfg["cameras_endpoint"]
        params: Dict[str, str] = {
            "key": api_key,
            "format": "json",
        }
        if self._rate_limiter:
            self._rate_limiter.wait_if_needed(state)
        return _http_get(url, params=params, timeout=self.timeout)

    def _parse_cameras(self, state: str, raw_list: List[Dict[str, Any]]) -> List[Camera]:
        """Parse raw API response into Camera objects."""
        cfg = STATE_CONFIGS[state]
        cameras = []
        for raw in raw_list:
            try:
                if cfg["api_version"] == "v1":
                    cam = _parse_v1_camera(state, raw)
                else:
                    cam = _parse_v2_camera(state, raw)
                cameras.append(cam)
            except Exception as e:
                logger.warning("Failed to parse camera record: %s | %s", e, raw)
        return cameras

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        state: str,
        api_key: Optional[str] = None,
        *,
        roadway: Optional[str] = None,
        direction: Optional[str] = None,
        active_only: bool = False,
        with_stream_only: bool = False,
    ) -> List[Camera]:
        """
        Retrieve all cameras for a state with optional filtering.

        Args:
            state: State code ('ny', 'wi', 'pa', 'ak', 'ut', 'mn', 'va', 'ia')
                   or full name ('New York', 'Wisconsin', etc.)
            api_key: Developer API key (overrides key set at construction).
            roadway: Filter by roadway name substring (case-insensitive).
                     E.g. 'I-90', 'US 9', 'NY 33'
            direction: Filter by direction substring (case-insensitive).
                       E.g. 'North', 'Eastbound'
            active_only: If True, exclude disabled/blocked cameras.
            with_stream_only: If True, return only cameras with HLS stream URLs.

        Returns:
            List of Camera objects.

        Example:
            cameras = client.get_cameras("ny", roadway="I-90", active_only=True)
        """
        state = self._resolve_state(state)
        key = self._get_api_key(state, api_key)
        raw_list = self._fetch_raw(state, key)
        cameras = self._parse_cameras(state, raw_list)

        if roadway:
            cameras = [
                c for c in cameras
                if c.roadway and roadway.lower() in c.roadway.lower()
            ]
        if direction:
            cameras = [
                c for c in cameras
                if c.direction and direction.lower() in c.direction.lower()
            ]
        if active_only:
            cameras = [c for c in cameras if c.is_active]
        if with_stream_only:
            cameras = [c for c in cameras if c.has_stream]

        logger.info(
            "get_cameras(%s): %d cameras returned (after filters)", state.upper(), len(cameras)
        )
        return cameras

    def get_camera_by_id(
        self,
        state: str,
        camera_id: str,
        api_key: Optional[str] = None,
    ) -> Optional[Camera]:
        """
        Find a single camera by its ID.

        Args:
            state: State code or name.
            camera_id: The camera's unique ID string.
            api_key: Developer API key.

        Returns:
            Camera object if found, None otherwise.
        """
        cameras = self.get_cameras(state, api_key=api_key)
        for cam in cameras:
            if cam.camera_id == str(camera_id):
                return cam
        return None

    def get_camera_stream_url(
        self,
        state: str,
        camera_id: str,
        api_key: Optional[str] = None,
        view_index: int = 0,
    ) -> Optional[str]:
        """
        Get the HLS stream URL for a specific camera.

        Args:
            state: State code or name.
            camera_id: The camera's unique ID string.
            api_key: Developer API key.
            view_index: For cameras with multiple views, which view to return (0-based).

        Returns:
            HLS .m3u8 stream URL string, or None if not available.

        Example:
            url = client.get_camera_stream_url("ny", "Skyline-10012", api_key="KEY")
            # Returns: "https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8"
        """
        cam = self.get_camera_by_id(state, camera_id, api_key=api_key)
        if cam is None:
            logger.warning("Camera %s not found in state %s", camera_id, state)
            return None
        urls = cam.stream_urls
        if not urls:
            return None
        if view_index < len(urls):
            return urls[view_index]
        return urls[0]

    def get_camera_image_url(
        self,
        state: str,
        camera_id: str,
        api_key: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get a still image URL for a camera, if available.

        Note: Most cameras provide HLS video streams rather than still images.
        Some cameras expose MJPEG URLs which can be used as still image sources.
        The 511 website detail page (Camera.detail_url) often shows a still preview.

        Args:
            state: State code or name.
            camera_id: Camera ID.
            api_key: Developer API key.

        Returns:
            MJPEG URL or similar still image URL, or None if only HLS available.
        """
        cam = self.get_camera_by_id(state, camera_id, api_key=api_key)
        if cam is None:
            return None
        # Check all stream URLs for MJPEG
        for url in cam.stream_urls:
            if url and any(ext in url.lower() for ext in [".jpg", ".jpeg", ".mjpg", "mjpeg", "snapshot"]):
                return url
        return None

    def get_all_stream_urls(
        self,
        state: str,
        api_key: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Get all available stream URLs for a state as a flat list.

        Args:
            state: State code or name.
            api_key: Developer API key.
            active_only: If True (default), exclude disabled cameras.

        Returns:
            List of dicts: [{"camera_id": ..., "name": ..., "stream_url": ...}, ...]

        Example:
            streams = client.get_all_stream_urls("wi")
            for s in streams[:5]:
                print(s["name"], "->", s["stream_url"])
        """
        cameras = self.get_cameras(
            state, api_key=api_key,
            active_only=active_only,
            with_stream_only=True,
        )
        result = []
        for cam in cameras:
            for url in cam.stream_urls:
                result.append({
                    "camera_id": cam.camera_id,
                    "name": cam.name,
                    "roadway": cam.roadway,
                    "direction": cam.direction,
                    "latitude": cam.latitude,
                    "longitude": cam.longitude,
                    "stream_url": url,
                })
        return result

    def get_cameras_near(
        self,
        state: str,
        lat: float,
        lon: float,
        radius_miles: float = 5.0,
        api_key: Optional[str] = None,
    ) -> List[Camera]:
        """
        Find cameras within a given radius of a coordinate.

        Args:
            state: State code or name.
            lat: Center latitude.
            lon: Center longitude.
            radius_miles: Search radius in miles (default 5.0).
            api_key: Developer API key.

        Returns:
            List of Camera objects sorted by distance (nearest first).
        """
        import math

        def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            R = 3958.8  # Earth radius in miles
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        cameras = self.get_cameras(state, api_key=api_key)
        nearby = []
        for cam in cameras:
            if cam.latitude is not None and cam.longitude is not None:
                dist = haversine_miles(lat, lon, cam.latitude, cam.longitude)
                if dist <= radius_miles:
                    nearby.append((dist, cam))
        nearby.sort(key=lambda x: x[0])
        return [cam for _, cam in nearby]

    def list_states(self) -> List[Dict[str, str]]:
        """
        Return info about all supported states.

        Returns:
            List of dicts with state metadata.
        """
        result = []
        for code, cfg in STATE_CONFIGS.items():
            result.append({
                "code": code,
                "name": cfg["name"],
                "api_version": cfg["api_version"],
                "developer_page": cfg["developer_page"],
                "register_url": cfg["register_url"],
                "notes": cfg.get("notes", ""),
            })
        return result

    def get_state_info(self, state: str) -> Dict[str, Any]:
        """Return configuration info for a specific state."""
        state = self._resolve_state(state)
        return dict(STATE_CONFIGS[state])

    # ------------------------------------------------------------------
    # HLS helpers
    # ------------------------------------------------------------------

    @staticmethod
    def construct_wi_hls_url(cam_id: str) -> str:
        """
        Construct a Wisconsin HLS stream URL from a camera ID.

        Wisconsin streams follow the pattern:
          https://cctv1.dot.wi.gov:443/rtplive/{cam_id}/playlist.m3u8

        Args:
            cam_id: Wisconsin camera source ID (from SourceId field).

        Returns:
            Full HLS playlist URL.
        """
        return f"https://cctv1.dot.wi.gov:443/rtplive/{cam_id}/playlist.m3u8"

    @staticmethod
    def construct_ny_hls_url(cam_id: str, server_num: int = 51) -> str:
        """
        Construct a New York HLS stream URL from a camera stream ID.

        NY streams follow the pattern:
          https://s{N}.nysdot.skyvdn.com:443/rtplive/{cam_id}/playlist.m3u8
        where N is typically 51, 52, 53, 58, or 7.

        Args:
            cam_id: Camera stream ID (e.g. 'R5_007').
            server_num: Streaming server number (default 51).

        Returns:
            Full HLS playlist URL.
        """
        return f"https://s{server_num}.nysdot.skyvdn.com:443/rtplive/{cam_id}/playlist.m3u8"

    @staticmethod
    def is_hls_url(url: str) -> bool:
        """Return True if the URL appears to be an HLS stream."""
        return url.endswith(".m3u8") or "playlist.m3u8" in url or "rtplive" in url

    @staticmethod
    def is_mjpeg_url(url: str) -> bool:
        """Return True if the URL appears to be an MJPEG stream."""
        return any(s in url.lower() for s in [".mjpg", "mjpeg", "video.mjpg"])


# ---------------------------------------------------------------------------
# Convenience module-level functions
# ---------------------------------------------------------------------------

_default_client: Optional[DOT511Client] = None


def _get_default_client() -> DOT511Client:
    global _default_client
    if _default_client is None:
        _default_client = DOT511Client()
    return _default_client


def get_cameras(
    state: str,
    api_key: str,
    roadway: Optional[str] = None,
    active_only: bool = False,
) -> List[Camera]:
    """Convenience function: get cameras for a state using the module-level client."""
    return _get_default_client().get_cameras(
        state, api_key=api_key, roadway=roadway, active_only=active_only
    )


def get_stream_url(state: str, camera_id: str, api_key: str) -> Optional[str]:
    """Convenience function: get HLS stream URL for a camera."""
    return _get_default_client().get_camera_stream_url(state, camera_id, api_key=api_key)


# ---------------------------------------------------------------------------
# CLI / Demo usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="DOT 511 Camera Client - list cameras and stream URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List supported states
  python dot_511_client.py --list-states

  # List cameras in New York
  python dot_511_client.py --state ny --key YOUR_NY_API_KEY

  # List active cameras on I-90 in New York
  python dot_511_client.py --state ny --key YOUR_KEY --roadway "I-90" --active-only

  # Get stream URL for a specific camera
  python dot_511_client.py --state ny --key YOUR_KEY --camera-id Skyline-10012

  # List all stream URLs for Wisconsin
  python dot_511_client.py --state wi --key YOUR_WI_KEY --streams-only
        """,
    )
    parser.add_argument("--list-states", action="store_true", help="List all supported states")
    parser.add_argument("--state", type=str, help="State code (ny, wi, pa, ak, ut, mn, va, ia)")
    parser.add_argument("--key", type=str, help="Developer API key for the selected state")
    parser.add_argument("--roadway", type=str, help="Filter by roadway name (partial match)")
    parser.add_argument("--direction", type=str, help="Filter by direction (partial match)")
    parser.add_argument("--active-only", action="store_true", help="Show only active cameras")
    parser.add_argument("--streams-only", action="store_true", help="Show only cameras with streams")
    parser.add_argument("--camera-id", type=str, help="Get info for a specific camera ID")
    parser.add_argument("--limit", type=int, default=20, help="Max cameras to display (default 20)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    client = DOT511Client()

    if args.list_states:
        print("\nSupported DOT 511 States:")
        print("-" * 70)
        for s in client.list_states():
            print(f"  {s['code']:5s} {s['name']:20s} API {s['api_version']}")
            print(f"        Developer page: {s['developer_page']}")
        print()
        sys.exit(0)

    if not args.state:
        parser.print_help()
        sys.exit(1)

    if not args.key:
        print(f"ERROR: --key required. Register at: {STATE_CONFIGS.get(args.state.lower(), {}).get('register_url', 'state 511 website')}")
        sys.exit(1)

    if args.camera_id:
        cam = client.get_camera_by_id(args.state, args.camera_id, api_key=args.key)
        if cam:
            print(f"\nCamera: {cam}")
            print(f"  ID:        {cam.camera_id}")
            print(f"  Name:      {cam.name}")
            print(f"  Roadway:   {cam.roadway}")
            print(f"  Direction: {cam.direction}")
            print(f"  Location:  ({cam.latitude}, {cam.longitude})")
            print(f"  Active:    {cam.is_active}")
            print(f"  Streams:   {cam.stream_urls}")
        else:
            print(f"Camera {args.camera_id!r} not found in {args.state.upper()}")
        sys.exit(0)

    cameras = client.get_cameras(
        args.state,
        api_key=args.key,
        roadway=args.roadway,
        direction=args.direction,
        active_only=args.active_only,
        with_stream_only=args.streams_only,
    )

    print(f"\nDOT 511 Cameras - {STATE_CONFIGS.get(client._resolve_state(args.state), {}).get('name', args.state.upper())}")
    print(f"Total: {len(cameras)} cameras (showing first {args.limit})")
    print("-" * 80)
    for cam in cameras[:args.limit]:
        stream_indicator = "[HLS]" if cam.has_stream else "[NO STREAM]"
        active_indicator = "" if cam.is_active else "[DISABLED]"
        print(f"  {cam.camera_id:30s} {stream_indicator} {active_indicator}")
        print(f"    Name:    {cam.name}")
        print(f"    Roadway: {cam.roadway}  Direction: {cam.direction}")
        if cam.stream_urls:
            print(f"    Stream:  {cam.stream_urls[0]}")
        print()
