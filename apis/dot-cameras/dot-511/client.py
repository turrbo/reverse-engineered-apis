"""
DOT 511 Unified Traffic Camera & Events Client
===============================================
A unified Python client for accessing highway traffic camera systems and
traffic events across 8 US states.

Reverse-engineered from live production APIs - NO API KEY REQUIRED.

Supported States and Platforms:
  Platform 1 – IBI Group ASP.NET MVC (cookie-based session, public endpoints):
    WI  Wisconsin     https://511wi.gov
    NY  New York      https://511ny.org
    PA  Pennsylvania  https://www.511pa.com
    AK  Alaska        https://511.alaska.gov
    UT  Utah          https://udottraffic.utah.gov

  Platform 2 – Castle Rock ITS CARS (RESTful microservices):
    MN  Minnesota     https://mntg.carsprogram.org
    IA  Iowa          https://iatg.carsprogram.org

  Platform 3 – Iteris TTRIP (requires browser session auth):
    VA  Virginia      https://511.vdot.virginia.gov  [LIMITED SUPPORT - see notes]

API Endpoints (Platform 1 – IBI Group):
  Cameras:  GET  {base_url}/Camera/GetUserCameras
            → {data: [{id, sourceId, source, roadway, direction, location,
                       latLng: {geography: {wellKnownText: "POINT(lon lat)"}},
                       images: [{id, cameraSiteId, imageUrl, videoUrl, videoType}]}],
               myCameras: false}

  Events:   POST {base_url}/list/GetData/{layerName}
            Body: draw=1&length=100&start=0  (DataTables pagination)
            Layer names: Incidents, Construction, Closures, SpecialEvents,
                         IncidentClosures, ConstructionClosures, WeatherClosures
            → {data: [{id, type, roadwayName, description, direction,
                       county, startDate, cameras: [...]}], recordsTotal, ...}

  Preview:  GET  {base_url}/map/Cctv/{imageId}   → JPEG image

API Endpoints (Platform 2 – CARS):
  Cameras:  GET  https://{state}tg.carsprogram.org/cameras_v1/api/cameras
            → [{id, public, name, lastUpdated,
                location: {fips, latitude, longitude, routeId, cityReference},
                cameraOwner: {name},
                views: [{name, type, url, videoPreviewUrl}]}]

  Events:   GET  https://{state}tg.carsprogram.org/events_v1/api/eventMapFeaturesAndReports
            Query params: bbox=minLon,minLat,maxLon,maxLat (optional)
            → GeoJSON FeatureCollection with event properties

  RWIS:     GET  https://{state}tg.carsprogram.org/rwis_v1/api/stations
            GET  https://{state}tg.carsprogram.org/rwis_v1/api/stationReports

  Preview:  https://public.carsprogram.org/cameras/{STATE_CODE}/{camId}  → JPEG image

HLS Stream Patterns:
  WI:  https://cctv1.dot.wi.gov:443/rtplive/{sourceId}/playlist.m3u8
  NY:  https://s52.nysdot.skyvdn.com:443/rtplive/{sourceId}/playlist.m3u8
  PA:  https://pa-se2.arcadis-ivds.com:8200/chan-{id}/index.m3u8  (auth required)
  MN:  https://video.dot.state.mn.us/public/{sourceId}.stream/playlist.m3u8
  IA:  per views[].url in camera record

Virginia Notes:
  VA uses the Iteris TTRIP platform. Camera data is served through an authenticated
  Node.js proxy (https://511.vdot.virginia.gov/services/) that forwards requests to
  https://data.511-atis-ttrip-prod.iteriscloud.com/. The proxy requires a valid browser
  session. This client provides best-effort support by attempting unauthenticated calls;
  a session_cookies dict can be passed to work with an active browser session.

Usage:
  from dot_511_client import DOT511Client

  client = DOT511Client()

  # List all cameras (no API key needed)
  cameras = client.get_cameras("wi")
  cameras = client.get_cameras("mn")

  # Get cameras with HLS streams only
  streams = client.get_cameras("ny", with_stream_only=True)

  # Get traffic incidents
  events = client.get_events("wi")

  # Get Minnesota road weather stations
  rwis = client.get_rwis_stations("mn")

  # Get all stream URLs as flat list
  urls = client.get_all_stream_urls("wi")
"""

import json
import time
import logging
import math
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlencode, urlparse
from dataclasses import dataclass, field

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform constants
# ---------------------------------------------------------------------------

PLATFORM_IBI = "ibi"        # IBI Group ASP.NET MVC  (WI, NY, PA, AK, UT)
PLATFORM_CARS = "cars"      # Castle Rock ITS CARS   (MN, IA)
PLATFORM_TTRIP = "ttrip"    # Iteris TTRIP           (VA)

# IBI platform event layer names (discovered from WI map JS bundle)
IBI_EVENT_LAYERS = [
    "Incidents",
    "Construction",
    "Closures",
    "SpecialEvents",
    "IncidentClosures",
    "ConstructionClosures",
    "WeatherClosures",
]

# ---------------------------------------------------------------------------
# State Configuration
# ---------------------------------------------------------------------------

STATE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "wi": {
        "name": "Wisconsin",
        "platform": PLATFORM_IBI,
        "base_url": "https://511wi.gov",
        "cars_state_code": None,
        "hls_pattern": "https://cctv1.dot.wi.gov:443/rtplive/{source_id}/playlist.m3u8",
        "notes": "IBI Group ASP.NET. HLS streams at cctv1.dot.wi.gov.",
    },
    "ny": {
        "name": "New York",
        "platform": PLATFORM_IBI,
        "base_url": "https://511ny.org",
        "cars_state_code": None,
        "hls_pattern": "https://s52.nysdot.skyvdn.com:443/rtplive/{source_id}/playlist.m3u8",
        "notes": "IBI Group ASP.NET. NY streams via nysdot.skyvdn.com (servers s51-s58).",
    },
    "pa": {
        "name": "Pennsylvania",
        "platform": PLATFORM_IBI,
        "base_url": "https://www.511pa.com",
        "cars_state_code": None,
        "hls_pattern": "https://pa-se2.arcadis-ivds.com:8200/chan-{source_id}/index.m3u8",
        "notes": "IBI Group ASP.NET. PA streams require isVideoAuthRequired token.",
    },
    "ak": {
        "name": "Alaska",
        "platform": PLATFORM_IBI,
        "base_url": "https://511.alaska.gov",
        "cars_state_code": None,
        "hls_pattern": None,
        "notes": "IBI Group ASP.NET. AK mostly RWIS-type static image cameras.",
    },
    "ut": {
        "name": "Utah",
        "platform": PLATFORM_IBI,
        "base_url": "https://udottraffic.utah.gov",
        "cars_state_code": None,
        "hls_pattern": None,
        "notes": "IBI Group ASP.NET. UDOT Traffic portal.",
    },
    "mn": {
        "name": "Minnesota",
        "platform": PLATFORM_CARS,
        "base_url": "https://mntg.carsprogram.org",
        "cars_state_code": "MN",
        "hls_pattern": "https://video.dot.state.mn.us/public/{source_id}.stream/playlist.m3u8",
        "notes": "Castle Rock ITS CARS microservices. OpenAPI at /cameras_v1/openapi.",
    },
    "ia": {
        "name": "Iowa",
        "platform": PLATFORM_CARS,
        "base_url": "https://iatg.carsprogram.org",
        "cars_state_code": "IA",
        "hls_pattern": None,
        "notes": "Castle Rock ITS CARS microservices. OpenAPI at /cameras_v1/openapi.",
    },
    "va": {
        "name": "Virginia",
        "platform": PLATFORM_TTRIP,
        "base_url": "https://511.vdot.virginia.gov",
        "cars_state_code": None,
        "hls_pattern": None,
        "notes": (
            "Iteris TTRIP Angular SPA. Camera data proxied through "
            "https://511.vdot.virginia.gov/services/ → "
            "https://data.511-atis-ttrip-prod.iteriscloud.com/. "
            "Requires authenticated browser session. Pass session_cookies to client."
        ),
    },
}

STATE_ALIASES: Dict[str, str] = {
    "new_york": "ny", "newyork": "ny",
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
class CameraImage:
    """A single image/view record from an IBI camera."""
    image_id: Optional[int] = None
    camera_site_id: Optional[int] = None
    image_url: Optional[str] = None    # relative path e.g. /map/Cctv/988
    video_url: Optional[str] = None    # HLS .m3u8 URL
    video_type: Optional[str] = None   # e.g. "application/x-mpegURL"
    raw: Optional[Dict] = None

    @property
    def is_hls(self) -> bool:
        return bool(self.video_url and "m3u8" in self.video_url)

    @classmethod
    def from_ibi(cls, d: Dict, base_url: str) -> "CameraImage":
        img_path = d.get("imageUrl", "")
        return cls(
            image_id=d.get("id"),
            camera_site_id=d.get("cameraSiteId"),
            image_url=base_url + img_path if img_path.startswith("/") else img_path,
            video_url=d.get("videoUrl"),
            video_type=d.get("videoType"),
            raw=d,
        )


@dataclass
class CameraView:
    """A single view from a CARS camera."""
    name: Optional[str] = None
    view_type: Optional[str] = None    # e.g. "WMP"
    url: Optional[str] = None          # HLS .m3u8 URL
    preview_url: Optional[str] = None  # static JPEG preview
    raw: Optional[Dict] = None

    @property
    def is_hls(self) -> bool:
        return bool(self.url and "m3u8" in self.url)

    @classmethod
    def from_cars(cls, d: Dict) -> "CameraView":
        return cls(
            name=d.get("name"),
            view_type=d.get("type"),
            url=d.get("url"),
            preview_url=d.get("videoPreviewUrl"),
            raw=d,
        )


@dataclass
class Camera:
    """
    Unified camera record normalised across IBI and CARS platforms.

    For IBI states (WI, NY, PA, AK, UT):
      - id = camera site ID (integer as string)
      - source_id = the external source ID used in HLS URL patterns
      - images[] = CameraImage objects with direct HLS .m3u8 URLs

    For CARS states (MN, IA):
      - id = CARS camera ID (integer as string)
      - source_id = stream ID embedded in views[].url
      - views[] = CameraView objects with HLS URLs and preview images
    """
    state: str
    platform: str
    camera_id: str
    name: str
    roadway: Optional[str] = None
    direction: Optional[int] = None   # IBI: compass bearing (0-360); CARS: not present
    location: Optional[str] = None    # human-readable location description
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: Optional[str] = None      # IBI: source system name (e.g. "ATMS")
    source_id: Optional[str] = None   # IBI: sourceId used in stream URL patterns
    # IBI-specific
    images: List[CameraImage] = field(default_factory=list)
    # CARS-specific
    views: List[CameraView] = field(default_factory=list)
    last_updated: Optional[int] = None   # CARS: epoch ms
    camera_owner: Optional[str] = None   # CARS: owner name
    route_id: Optional[str] = None       # CARS: route ID
    city: Optional[str] = None           # CARS: city reference
    raw: Optional[Dict] = None

    @property
    def has_stream(self) -> bool:
        """True if at least one HLS stream URL is available."""
        for img in self.images:
            if img.is_hls:
                return True
        for view in self.views:
            if view.is_hls:
                return True
        return False

    @property
    def stream_urls(self) -> List[str]:
        """All HLS .m3u8 stream URLs for this camera."""
        urls = []
        for img in self.images:
            if img.video_url and img.video_url not in urls:
                urls.append(img.video_url)
        for view in self.views:
            if view.url and view.url not in urls:
                urls.append(view.url)
        return urls

    @property
    def preview_image_url(self) -> Optional[str]:
        """Static JPEG preview URL if available."""
        for img in self.images:
            if img.image_url:
                return img.image_url
        for view in self.views:
            if view.preview_url:
                return view.preview_url
        return None

    @property
    def primary_stream_url(self) -> Optional[str]:
        """The first available HLS stream URL."""
        urls = self.stream_urls
        return urls[0] if urls else None

    def __repr__(self) -> str:
        stream = "HLS" if self.has_stream else "no-stream"
        loc = self.location or self.roadway or "?"
        return f"Camera({self.state.upper()}:{self.camera_id} | {loc!r} | {stream})"


@dataclass
class TrafficEvent:
    """A traffic incident, construction notice, closure, or weather event."""
    state: str
    event_id: str
    event_type: Optional[str] = None
    roadway: Optional[str] = None
    description: Optional[str] = None
    direction: Optional[str] = None
    county: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    camera_ids: List[str] = field(default_factory=list)
    raw: Optional[Dict] = None

    def __repr__(self) -> str:
        return (
            f"Event({self.state.upper()}:{self.event_id} "
            f"| {self.event_type} | {self.roadway} | {self.description[:60]!r})"
        )


@dataclass
class RwisStation:
    """A Road Weather Information System (RWIS) station (CARS platform)."""
    state: str
    station_id: str
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    route_id: Optional[str] = None
    raw: Optional[Dict] = None


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

def _parse_ibi_latlon(cam_raw: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Extract lat/lon from IBI wellKnownText POINT geometry."""
    try:
        wkt = cam_raw["latLng"]["geography"]["wellKnownText"]
        # Format: "POINT (-88.05841 43.088111)"
        coords = wkt.replace("POINT (", "").replace(")", "").strip().split()
        lon, lat = float(coords[0]), float(coords[1])
        return lat, lon
    except (KeyError, TypeError, ValueError, IndexError):
        return None, None


def _parse_ibi_camera(state: str, raw: Dict, base_url: str) -> Camera:
    lat, lon = _parse_ibi_latlon(raw)
    images_raw = raw.get("images") or []
    images = [CameraImage.from_ibi(img, base_url) for img in images_raw]

    direction_val = raw.get("direction")

    return Camera(
        state=state,
        platform=PLATFORM_IBI,
        camera_id=str(raw.get("id", "")),
        name=raw.get("location", raw.get("roadway", "")),
        roadway=raw.get("roadway", "").strip(),
        direction=direction_val,
        location=raw.get("location"),
        latitude=lat,
        longitude=lon,
        source=raw.get("source"),
        source_id=str(raw.get("sourceId", "")),
        images=images,
        raw=raw,
    )


def _parse_cars_camera(state: str, raw: Dict) -> Camera:
    loc = raw.get("location") or {}
    views_raw = raw.get("views") or []
    views = [CameraView.from_cars(v) for v in views_raw]
    owner = (raw.get("cameraOwner") or {}).get("name")

    # Extract source_id from first view URL for convenience
    source_id = None
    if views and views[0].url:
        # e.g. https://video.dot.state.mn.us/public/C5013.stream/playlist.m3u8
        # source_id = "C5013"
        url = views[0].url
        parts = url.rstrip("/").split("/")
        for part in reversed(parts):
            if part and part != "playlist.m3u8":
                candidate = part.replace(".stream", "")
                if candidate:
                    source_id = candidate
                    break

    return Camera(
        state=state,
        platform=PLATFORM_CARS,
        camera_id=str(raw.get("id", "")),
        name=raw.get("name", ""),
        roadway=loc.get("routeId"),
        direction=None,
        location=raw.get("name"),
        latitude=loc.get("latitude"),
        longitude=loc.get("longitude"),
        source_id=source_id,
        views=views,
        last_updated=raw.get("lastUpdated"),
        camera_owner=owner,
        route_id=loc.get("routeId"),
        city=loc.get("cityReference"),
        raw=raw,
    )


def _parse_ibi_event(state: str, raw: Dict) -> TrafficEvent:
    """Parse a DataTables event row from IBI /list/GetData/{layer}."""
    # Camera IDs may be embedded in a cameras list
    cam_ids = []
    for c in (raw.get("cameras") or []):
        cid = c.get("id") or c.get("cameraId")
        if cid:
            cam_ids.append(str(cid))

    # Latitude/longitude may or may not be present
    lat = raw.get("latitude") or raw.get("lat")
    lon = raw.get("longitude") or raw.get("lon") or raw.get("lng")

    return TrafficEvent(
        state=state,
        event_id=str(raw.get("id", "")),
        event_type=raw.get("type") or raw.get("eventType"),
        roadway=raw.get("roadwayName") or raw.get("roadway"),
        description=raw.get("description", ""),
        direction=raw.get("direction"),
        county=raw.get("county"),
        start_date=raw.get("startDate") or raw.get("startTime"),
        end_date=raw.get("endDate") or raw.get("endTime"),
        latitude=float(lat) if lat else None,
        longitude=float(lon) if lon else None,
        camera_ids=cam_ids,
        raw=raw,
    )


def _parse_cars_event(state: str, feature: Dict) -> TrafficEvent:
    """Parse a GeoJSON Feature from CARS /events_v1/api/eventMapFeaturesAndReports."""
    props = feature.get("properties") or {}
    geo = feature.get("geometry") or {}
    coords = geo.get("coordinates")

    lat, lon = None, None
    if coords and geo.get("type") == "Point":
        lon, lat = float(coords[0]), float(coords[1])

    return TrafficEvent(
        state=state,
        event_id=str(props.get("id", feature.get("id", ""))),
        event_type=props.get("type") or props.get("eventType"),
        roadway=props.get("roadwayName") or props.get("route"),
        description=props.get("description", ""),
        direction=props.get("direction"),
        county=props.get("county"),
        start_date=props.get("startDate") or props.get("startTime"),
        end_date=props.get("endDate") or props.get("endTime"),
        latitude=lat,
        longitude=lon,
        raw=feature,
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DOT511Client/2.0; "
        "+https://github.com/dot511client)"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


def _http_get(
    url: str,
    params: Optional[Dict] = None,
    timeout: int = 30,
    cookies: Optional[Dict] = None,
    extra_headers: Optional[Dict] = None,
) -> Any:
    """GET request returning parsed JSON. Uses requests if available, else urllib."""
    headers = dict(_DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    if HAS_REQUESTS:
        resp = _requests.get(
            url,
            params=params,
            timeout=timeout,
            headers=headers,
            cookies=cookies,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json()

    elif HAS_URLLIB:
        if params:
            url = url + "?" + urlencode(params)
        req = urllib.request.Request(url, headers=headers)
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            req.add_header("Cookie", cookie_str)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from e
    else:
        raise RuntimeError("Install 'requests': pip install requests")


def _http_post_form(
    url: str,
    data: Dict,
    timeout: int = 30,
    cookies: Optional[Dict] = None,
    extra_headers: Optional[Dict] = None,
) -> Any:
    """POST application/x-www-form-urlencoded request returning parsed JSON."""
    headers = dict(_DEFAULT_HEADERS)
    headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    if extra_headers:
        headers.update(extra_headers)

    body = urlencode(data).encode("utf-8")

    if HAS_REQUESTS:
        resp = _requests.post(
            url,
            data=data,
            timeout=timeout,
            headers=headers,
            cookies=cookies,
        )
        resp.raise_for_status()
        return resp.json()

    elif HAS_URLLIB:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        if cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
            req.add_header("Cookie", cookie_str)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8")
            raise RuntimeError(f"HTTP {e.code}: {body_txt[:300]}") from e
    else:
        raise RuntimeError("Install 'requests': pip install requests")


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class DOT511Client:
    """
    Unified client for DOT 511 traffic camera systems across 8 US states.

    No API key required. All endpoints are publicly accessible.

    Supported states: wi, ny, pa, ak, ut (IBI platform), mn, ia (CARS platform)
    Limited support: va (Iteris TTRIP - requires browser session)

    Args:
        timeout:        HTTP request timeout in seconds (default 30).
        session_cookies: Optional dict of cookies for authenticated requests.
                         Required for Virginia (va) camera data.
                         E.g. {"ASP.NET_SessionId": "...", ".ASPXAUTH": "..."}

    Examples:
        client = DOT511Client()

        # Get all cameras (no auth needed)
        cams = client.get_cameras("wi")
        cams = client.get_cameras("mn")

        # Get active cameras with HLS streams
        live = client.get_cameras("ny", with_stream_only=True)
        for cam in live[:5]:
            print(cam.primary_stream_url)

        # Get traffic incidents
        incidents = client.get_events("wi", layer="Incidents")

        # Get all event types
        all_events = client.get_events("wi")

        # Get MN road weather data
        stations = client.get_rwis_stations("mn")
    """

    def __init__(
        self,
        timeout: int = 30,
        session_cookies: Optional[Dict[str, str]] = None,
    ):
        self.timeout = timeout
        self.session_cookies = session_cookies or {}

    # ------------------------------------------------------------------
    # State resolution
    # ------------------------------------------------------------------

    def _resolve_state(self, state: str) -> str:
        s = state.lower().strip().replace(" ", "_").replace("-", "_")
        s = STATE_ALIASES.get(s, s)
        if s not in STATE_CONFIGS:
            raise ValueError(
                f"Unknown state {state!r}. "
                f"Supported: {sorted(STATE_CONFIGS.keys())}"
            )
        return s

    def _cfg(self, state: str) -> Dict[str, Any]:
        return STATE_CONFIGS[state]

    # ------------------------------------------------------------------
    # Camera fetching
    # ------------------------------------------------------------------

    def _fetch_ibi_cameras(self, state: str) -> List[Camera]:
        cfg = self._cfg(state)
        url = cfg["base_url"] + "/Camera/GetUserCameras"
        logger.debug("IBI cameras: GET %s", url)
        raw = _http_get(url, timeout=self.timeout, cookies=self.session_cookies or None)
        # Response: {"data": [...], "myCameras": false}
        if isinstance(raw, dict):
            items = raw.get("data") or []
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        cameras = []
        for item in items:
            try:
                cameras.append(_parse_ibi_camera(state, item, cfg["base_url"]))
            except Exception as e:
                logger.warning("Failed to parse IBI camera: %s | %s", e, item)
        return cameras

    def _fetch_cars_cameras(self, state: str) -> List[Camera]:
        cfg = self._cfg(state)
        url = cfg["base_url"] + "/cameras_v1/api/cameras"
        logger.debug("CARS cameras: GET %s", url)
        raw = _http_get(url, timeout=self.timeout)
        if not isinstance(raw, list):
            raw = raw.get("data") or raw.get("cameras") or []
        cameras = []
        for item in raw:
            try:
                cameras.append(_parse_cars_camera(state, item))
            except Exception as e:
                logger.warning("Failed to parse CARS camera: %s | %s", e, item)
        return cameras

    def _fetch_ttrip_cameras(self, state: str) -> List[Camera]:
        """
        Attempt to fetch Virginia cameras via the Node.js proxy.
        Requires session_cookies to be set with valid browser session tokens.
        """
        cfg = self._cfg(state)
        node_base = cfg["base_url"] + "/services/"
        # VA proxy endpoint pattern (discovered from Angular bundle)
        # The proxy forwards to the TTRIP backend
        candidate_paths = [
            "getCamerasArray",
            "cameras",
            "api/cameras",
        ]
        for path in candidate_paths:
            url = node_base + path
            try:
                logger.debug("TTRIP cameras attempt: GET %s", url)
                raw = _http_get(
                    url,
                    timeout=self.timeout,
                    cookies=self.session_cookies or None,
                )
                if isinstance(raw, list) and raw:
                    cameras = []
                    for item in raw:
                        try:
                            # VA camera fields from Angular bundle:
                            # {https_url, image_url, description, direction, route}
                            lat = item.get("latitude") or item.get("lat")
                            lon = item.get("longitude") or item.get("lon") or item.get("lng")
                            views = []
                            if item.get("https_url"):
                                views.append(CameraView(
                                    url=item["https_url"],
                                    preview_url=item.get("image_url"),
                                ))
                            cam = Camera(
                                state=state,
                                platform=PLATFORM_TTRIP,
                                camera_id=str(item.get("id", item.get("cameraId", ""))),
                                name=item.get("description", item.get("name", "")),
                                roadway=item.get("route"),
                                direction=item.get("direction"),
                                location=item.get("description"),
                                latitude=float(lat) if lat else None,
                                longitude=float(lon) if lon else None,
                                views=views,
                                raw=item,
                            )
                            cameras.append(cam)
                        except Exception as e:
                            logger.warning("Failed to parse TTRIP camera: %s", e)
                    if cameras:
                        return cameras
            except Exception as e:
                logger.debug("TTRIP path %s failed: %s", path, e)

        logger.warning(
            "Virginia (TTRIP) camera fetch failed. "
            "This platform requires an authenticated browser session. "
            "Pass session_cookies={...} with valid ASP.NET session tokens obtained "
            "from an active browser session on https://511.vdot.virginia.gov/. "
            "Backend: https://data.511-atis-ttrip-prod.iteriscloud.com/"
        )
        return []

    def get_cameras(
        self,
        state: str,
        *,
        roadway: Optional[str] = None,
        direction: Optional[str] = None,
        with_stream_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[Camera]:
        """
        Retrieve all cameras for a state.

        Args:
            state:           State code ('wi', 'ny', 'pa', 'ak', 'ut', 'mn', 'ia', 'va')
                             or full name ('Wisconsin', 'New York', etc.)
            roadway:         Filter by roadway name substring (case-insensitive).
                             E.g. 'I-41', 'US 45', 'TH 5'
            direction:       For IBI states: filter by direction string (case-insensitive).
            with_stream_only: If True, return only cameras with HLS .m3u8 stream URLs.
            limit:           Maximum number of cameras to return.

        Returns:
            List of Camera objects.

        Notes:
            - No API key required for any state.
            - Virginia (va) requires session_cookies for camera data.

        Examples:
            # All Wisconsin cameras
            cams = client.get_cameras("wi")

            # Only cameras with live streams
            live = client.get_cameras("mn", with_stream_only=True)

            # Filter by highway
            i90 = client.get_cameras("ny", roadway="I-90")
        """
        state = self._resolve_state(state)
        cfg = self._cfg(state)
        platform = cfg["platform"]

        if platform == PLATFORM_IBI:
            cameras = self._fetch_ibi_cameras(state)
        elif platform == PLATFORM_CARS:
            cameras = self._fetch_cars_cameras(state)
        elif platform == PLATFORM_TTRIP:
            cameras = self._fetch_ttrip_cameras(state)
        else:
            raise ValueError(f"Unknown platform {platform!r} for state {state}")

        if roadway:
            cameras = [
                c for c in cameras
                if (c.roadway and roadway.lower() in c.roadway.lower())
                or (c.location and roadway.lower() in c.location.lower())
            ]
        if direction:
            cameras = [
                c for c in cameras
                if c.direction is not None
                and str(direction).lower() in str(c.direction).lower()
            ]
        if with_stream_only:
            cameras = [c for c in cameras if c.has_stream]
        if limit is not None:
            cameras = cameras[:limit]

        logger.info(
            "get_cameras(%s): %d cameras (platform=%s)",
            state.upper(), len(cameras), platform,
        )
        return cameras

    def get_camera_by_id(
        self,
        state: str,
        camera_id: str,
    ) -> Optional[Camera]:
        """
        Retrieve a single camera by its ID.

        Args:
            state:     State code or name.
            camera_id: Camera ID string.

        Returns:
            Camera object if found, None otherwise.
        """
        cameras = self.get_cameras(state)
        for cam in cameras:
            if cam.camera_id == str(camera_id):
                return cam
        return None

    def get_all_stream_urls(
        self,
        state: str,
        with_preview: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get all HLS stream URLs for a state as a flat list of dicts.

        Args:
            state:        State code or name.
            with_preview: If True, also include static preview image URLs.

        Returns:
            List of dicts:
              {camera_id, name, location, roadway, latitude, longitude,
               stream_url, [preview_url]}

        Example:
            for s in client.get_all_stream_urls("wi"):
                print(s["name"], "->", s["stream_url"])
        """
        cameras = self.get_cameras(state, with_stream_only=True)
        result = []
        for cam in cameras:
            for url in cam.stream_urls:
                entry: Dict[str, Any] = {
                    "camera_id": cam.camera_id,
                    "name": cam.name,
                    "location": cam.location,
                    "roadway": cam.roadway,
                    "latitude": cam.latitude,
                    "longitude": cam.longitude,
                    "stream_url": url,
                }
                if with_preview and cam.preview_image_url:
                    entry["preview_url"] = cam.preview_image_url
                result.append(entry)
        return result

    def get_cameras_near(
        self,
        state: str,
        lat: float,
        lon: float,
        radius_miles: float = 5.0,
    ) -> List[Tuple[float, Camera]]:
        """
        Find cameras within a radius of a coordinate, sorted nearest-first.

        Args:
            state:        State code or name.
            lat:          Center latitude.
            lon:          Center longitude.
            radius_miles: Search radius in miles (default 5.0).

        Returns:
            List of (distance_miles, Camera) tuples, sorted by distance.

        Example:
            nearby = client.get_cameras_near("wi", 43.0, -88.0, radius_miles=3)
            for dist, cam in nearby:
                print(f"{dist:.1f}mi - {cam}")
        """
        cameras = self.get_cameras(state)

        def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            R = 3958.8
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lon2 - lon1)
            a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        nearby = []
        for cam in cameras:
            if cam.latitude is not None and cam.longitude is not None:
                d = haversine(lat, lon, cam.latitude, cam.longitude)
                if d <= radius_miles:
                    nearby.append((d, cam))
        nearby.sort(key=lambda x: x[0])
        return nearby

    # ------------------------------------------------------------------
    # Events / Incidents
    # ------------------------------------------------------------------

    def get_events(
        self,
        state: str,
        layer: Optional[str] = None,
        page_size: int = 200,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[TrafficEvent]:
        """
        Retrieve traffic events (incidents, construction, closures, etc.).

        Args:
            state:     State code or name.
            layer:     For IBI states: event layer name. One of:
                         Incidents, Construction, Closures, SpecialEvents,
                         IncidentClosures, ConstructionClosures, WeatherClosures
                       If None, fetches ALL layers and combines results.
                       Ignored for CARS states (all events fetched together).
            page_size: Number of records per request (IBI default 200).
            bbox:      For CARS states: bounding box filter
                       (min_lon, min_lat, max_lon, max_lat).
                       If None, fetches all events statewide.

        Returns:
            List of TrafficEvent objects.

        Examples:
            # All incidents in Wisconsin
            incidents = client.get_events("wi", layer="Incidents")

            # All event types combined
            all_events = client.get_events("wi")

            # Minnesota events in a bounding box
            events = client.get_events("mn", bbox=(-94.0, 44.5, -93.0, 45.5))
        """
        state = self._resolve_state(state)
        cfg = self._cfg(state)
        platform = cfg["platform"]

        if platform == PLATFORM_IBI:
            return self._fetch_ibi_events(state, layer=layer, page_size=page_size)
        elif platform == PLATFORM_CARS:
            return self._fetch_cars_events(state, bbox=bbox)
        elif platform == PLATFORM_TTRIP:
            logger.warning(
                "Virginia (TTRIP) events require an authenticated session. "
                "Pass session_cookies with valid browser session tokens."
            )
            return self._fetch_ttrip_events(state)
        else:
            return []

    def _fetch_ibi_events(
        self,
        state: str,
        layer: Optional[str],
        page_size: int,
    ) -> List[TrafficEvent]:
        cfg = self._cfg(state)
        base_url = cfg["base_url"]
        layers_to_fetch = [layer] if layer else IBI_EVENT_LAYERS
        all_events = []

        for lyr in layers_to_fetch:
            url = f"{base_url}/list/GetData/{lyr}"
            data = {
                "draw": "1",
                "start": "0",
                "length": str(page_size),
            }
            try:
                logger.debug("IBI events: POST %s (layer=%s)", url, lyr)
                raw = _http_post_form(
                    url, data,
                    timeout=self.timeout,
                    cookies=self.session_cookies or None,
                )
                rows = raw.get("data") or []
                for row in rows:
                    try:
                        evt = _parse_ibi_event(state, row)
                        if not evt.event_type:
                            evt.event_type = lyr
                        all_events.append(evt)
                    except Exception as e:
                        logger.warning("Failed to parse IBI event row: %s", e)
            except Exception as e:
                logger.warning("IBI events layer %s failed: %s", lyr, e)

        return all_events

    def _fetch_cars_events(
        self,
        state: str,
        bbox: Optional[Tuple[float, float, float, float]],
    ) -> List[TrafficEvent]:
        cfg = self._cfg(state)
        url = cfg["base_url"] + "/events_v1/api/eventMapFeaturesAndReports"
        params: Dict[str, Any] = {}
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            params["bbox"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"

        logger.debug("CARS events: GET %s params=%s", url, params)
        try:
            raw = _http_get(url, params=params or None, timeout=self.timeout)
        except Exception as e:
            logger.warning("CARS events fetch failed: %s", e)
            return []

        # Response is a GeoJSON FeatureCollection or a list
        features = []
        if isinstance(raw, dict):
            features = raw.get("features") or []
        elif isinstance(raw, list):
            features = raw

        events = []
        for feat in features:
            try:
                events.append(_parse_cars_event(state, feat))
            except Exception as e:
                logger.warning("Failed to parse CARS event: %s", e)
        return events

    def _fetch_ttrip_events(self, state: str) -> List[TrafficEvent]:
        cfg = self._cfg(state)
        node_base = cfg["base_url"] + "/services/"
        candidate_paths = ["events", "incidents", "api/events"]
        for path in candidate_paths:
            url = node_base + path
            try:
                raw = _http_get(
                    url,
                    timeout=self.timeout,
                    cookies=self.session_cookies or None,
                )
                if isinstance(raw, (list, dict)):
                    features = raw if isinstance(raw, list) else raw.get("features", [])
                    events = []
                    for feat in features:
                        try:
                            events.append(_parse_cars_event(state, feat))
                        except Exception:
                            pass
                    if events:
                        return events
            except Exception as e:
                logger.debug("TTRIP events path %s failed: %s", path, e)
        return []

    # ------------------------------------------------------------------
    # RWIS (Road Weather Information System) - CARS only
    # ------------------------------------------------------------------

    def get_rwis_stations(self, state: str) -> List[RwisStation]:
        """
        Retrieve Road Weather Information System (RWIS) stations.

        Only available for CARS platform states (mn, ia).

        Args:
            state: State code ('mn' or 'ia').

        Returns:
            List of RwisStation objects.

        Example:
            stations = client.get_rwis_stations("mn")
            for s in stations[:5]:
                print(s.name, s.latitude, s.longitude)
        """
        state = self._resolve_state(state)
        cfg = self._cfg(state)
        if cfg["platform"] != PLATFORM_CARS:
            raise ValueError(
                f"RWIS data is only available for CARS platform states (mn, ia). "
                f"State {state!r} uses platform {cfg['platform']!r}."
            )

        url = cfg["base_url"] + "/rwis_v1/api/stations"
        logger.debug("CARS RWIS stations: GET %s", url)
        try:
            raw = _http_get(url, timeout=self.timeout)
        except Exception as e:
            logger.warning("RWIS stations fetch failed: %s", e)
            return []

        items = raw if isinstance(raw, list) else (raw.get("data") or raw.get("stations") or [])
        stations = []
        for item in items:
            loc = item.get("location") or {}
            stations.append(RwisStation(
                state=state,
                station_id=str(item.get("id", "")),
                name=item.get("name"),
                latitude=loc.get("latitude") or item.get("latitude"),
                longitude=loc.get("longitude") or item.get("longitude"),
                route_id=loc.get("routeId") or item.get("routeId"),
                raw=item,
            ))
        return stations

    def get_rwis_reports(
        self,
        state: str,
        station_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve Road Weather Information System sensor reports.

        Only available for CARS platform states (mn, ia).

        Args:
            state:      State code ('mn' or 'ia').
            station_id: Optional station ID to filter by.

        Returns:
            List of raw report dicts from the CARS API.

        Example:
            reports = client.get_rwis_reports("mn")
        """
        state = self._resolve_state(state)
        cfg = self._cfg(state)
        if cfg["platform"] != PLATFORM_CARS:
            raise ValueError(
                f"RWIS data is only available for CARS platform states (mn, ia)."
            )

        url = cfg["base_url"] + "/rwis_v1/api/stationReports"
        params: Dict[str, str] = {}
        if station_id:
            params["stationId"] = str(station_id)

        logger.debug("CARS RWIS reports: GET %s", url)
        try:
            raw = _http_get(url, params=params or None, timeout=self.timeout)
        except Exception as e:
            logger.warning("RWIS reports fetch failed: %s", e)
            return []

        if isinstance(raw, list):
            return raw
        return raw.get("data") or raw.get("reports") or []

    # ------------------------------------------------------------------
    # Utility / metadata
    # ------------------------------------------------------------------

    def list_states(self) -> List[Dict[str, Any]]:
        """
        Return metadata for all supported states.

        Returns:
            List of dicts with state info:
              {code, name, platform, base_url, notes}
        """
        return [
            {
                "code": code,
                "name": cfg["name"],
                "platform": cfg["platform"],
                "base_url": cfg["base_url"],
                "notes": cfg.get("notes", ""),
            }
            for code, cfg in STATE_CONFIGS.items()
        ]

    def get_state_info(self, state: str) -> Dict[str, Any]:
        """Return configuration info for a specific state."""
        state = self._resolve_state(state)
        return dict(STATE_CONFIGS[state])

    def get_event_layers(self, state: str) -> List[str]:
        """
        Return the list of available event layer names for an IBI state.

        Args:
            state: IBI platform state code (wi, ny, pa, ak, ut).

        Returns:
            List of layer name strings.

        Raises:
            ValueError: If state is not an IBI platform state.
        """
        state = self._resolve_state(state)
        cfg = self._cfg(state)
        if cfg["platform"] != PLATFORM_IBI:
            raise ValueError(
                f"Event layers only apply to IBI platform states. "
                f"State {state!r} uses {cfg['platform']!r}. "
                f"For CARS states use get_events() directly."
            )
        return list(IBI_EVENT_LAYERS)

    @staticmethod
    def build_preview_url(state: str, camera_id: str) -> Optional[str]:
        """
        Build a static preview image URL for a camera.

        For CARS states (mn, ia), uses the public.carsprogram.org CDN.
        For IBI states, preview URLs are in camera.images[].image_url.

        Args:
            state:     State code (lowercase).
            camera_id: Camera ID string.

        Returns:
            Preview image URL, or None for IBI states (use camera.images[].image_url).

        Example:
            url = DOT511Client.build_preview_url("mn", "C5013")
            # -> "https://public.carsprogram.org/cameras/MN/C5013"
        """
        state = state.lower().strip()
        cfg = STATE_CONFIGS.get(state)
        if not cfg:
            return None
        if cfg["platform"] == PLATFORM_CARS:
            state_code = cfg.get("cars_state_code", state.upper())
            return f"https://public.carsprogram.org/cameras/{state_code}/{camera_id}"
        return None


# ---------------------------------------------------------------------------
# Convenience module-level functions
# ---------------------------------------------------------------------------

_client: Optional[DOT511Client] = None


def _default_client() -> DOT511Client:
    global _client
    if _client is None:
        _client = DOT511Client()
    return _client


def get_cameras(
    state: str,
    roadway: Optional[str] = None,
    with_stream_only: bool = False,
) -> List[Camera]:
    """
    Convenience function: get cameras for a state using the module-level client.

    No API key required.

    Example:
        from dot_511_client import get_cameras
        cams = get_cameras("wi", with_stream_only=True)
    """
    return _default_client().get_cameras(
        state, roadway=roadway, with_stream_only=with_stream_only
    )


def get_stream_urls(state: str) -> List[Dict[str, Any]]:
    """
    Convenience function: get all HLS stream URLs for a state.

    Returns:
        List of {camera_id, name, location, stream_url, ...} dicts.

    Example:
        from dot_511_client import get_stream_urls
        for s in get_stream_urls("mn"):
            print(s["stream_url"])
    """
    return _default_client().get_all_stream_urls(state)


def get_events(state: str, layer: Optional[str] = None) -> List[TrafficEvent]:
    """
    Convenience function: get traffic events for a state.

    Args:
        state: State code.
        layer: IBI event layer (e.g. "Incidents"). None = all layers.

    Example:
        from dot_511_client import get_events
        events = get_events("wi", layer="Incidents")
    """
    return _default_client().get_events(state, layer=layer)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="DOT 511 Traffic Camera & Events Client (no API key required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Platform Information:
  IBI Group ASP.NET (WI, NY, PA, AK, UT):
    Cameras: GET {base}/Camera/GetUserCameras
    Events:  POST {base}/list/GetData/{layer}

  Castle Rock ITS CARS (MN, IA):
    Cameras: GET https://{state}tg.carsprogram.org/cameras_v1/api/cameras
    Events:  GET https://{state}tg.carsprogram.org/events_v1/api/eventMapFeaturesAndReports
    RWIS:    GET https://{state}tg.carsprogram.org/rwis_v1/api/stations

  Iteris TTRIP (VA):
    Requires authenticated browser session. Pass --cookies.

Examples:
  # List all supported states
  python dot_511_client.py --list-states

  # List cameras in Wisconsin
  python dot_511_client.py --state wi --cameras

  # List live streams only in New York
  python dot_511_client.py --state ny --cameras --streams-only

  # Filter by highway
  python dot_511_client.py --state wi --cameras --roadway "I-41"

  # Get traffic incidents in Wisconsin
  python dot_511_client.py --state wi --events --layer Incidents

  # Get all event types in Minnesota
  python dot_511_client.py --state mn --events

  # Get Minnesota RWIS weather stations
  python dot_511_client.py --state mn --rwis
        """,
    )
    parser.add_argument("--list-states", action="store_true",
                        help="List all supported states and their platforms")
    parser.add_argument("--state", type=str,
                        help="State code (wi, ny, pa, ak, ut, mn, ia, va)")
    parser.add_argument("--cameras", action="store_true",
                        help="List cameras for the state")
    parser.add_argument("--events", action="store_true",
                        help="List traffic events for the state")
    parser.add_argument("--rwis", action="store_true",
                        help="List RWIS weather stations (MN, IA only)")
    parser.add_argument("--streams-only", action="store_true",
                        help="Show only cameras with HLS stream URLs")
    parser.add_argument("--roadway", type=str,
                        help="Filter cameras by roadway name (substring)")
    parser.add_argument("--layer", type=str,
                        help="IBI event layer (Incidents, Construction, Closures, etc.)")
    parser.add_argument("--limit", type=int, default=25,
                        help="Max records to display (default 25)")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted text")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    client = DOT511Client()

    if args.list_states:
        print("\nDOT 511 Supported States")
        print("=" * 70)
        for s in client.list_states():
            print(f"  {s['code']:4s}  {s['name']:20s}  [{s['platform'].upper()}]")
            print(f"        {s['base_url']}")
            print(f"        {s['notes'][:80]}")
            print()
        sys.exit(0)

    if not args.state:
        parser.print_help()
        sys.exit(1)

    state = args.state.lower()

    if args.cameras:
        cameras = client.get_cameras(
            state,
            roadway=args.roadway,
            with_stream_only=args.streams_only,
            limit=args.limit,
        )
        if args.json:
            out = []
            for cam in cameras:
                out.append({
                    "camera_id": cam.camera_id,
                    "name": cam.name,
                    "roadway": cam.roadway,
                    "location": cam.location,
                    "latitude": cam.latitude,
                    "longitude": cam.longitude,
                    "stream_urls": cam.stream_urls,
                    "preview_url": cam.preview_image_url,
                })
            print(json.dumps(out, indent=2))
        else:
            info = client.get_state_info(state)
            print(f"\nDOT 511 Cameras — {info['name']} [{info['platform'].upper()}]")
            print(f"Showing {len(cameras)} cameras")
            print("-" * 70)
            for cam in cameras:
                stream_tag = "[HLS]" if cam.has_stream else "[NO STREAM]"
                print(f"  ID: {cam.camera_id:>8}  {stream_tag}  {cam.name}")
                if cam.roadway and cam.roadway != cam.name:
                    print(f"    Roadway:  {cam.roadway}")
                if cam.latitude:
                    print(f"    Location: {cam.latitude:.5f}, {cam.longitude:.5f}")
                for url in cam.stream_urls[:2]:
                    print(f"    Stream:   {url}")
                if cam.preview_image_url:
                    print(f"    Preview:  {cam.preview_image_url}")
                print()

    elif args.events:
        events = client.get_events(state, layer=args.layer)[:args.limit]
        if args.json:
            out = []
            for evt in events:
                out.append({
                    "event_id": evt.event_id,
                    "type": evt.event_type,
                    "roadway": evt.roadway,
                    "description": evt.description,
                    "direction": evt.direction,
                    "county": evt.county,
                    "start_date": evt.start_date,
                    "latitude": evt.latitude,
                    "longitude": evt.longitude,
                })
            print(json.dumps(out, indent=2))
        else:
            info = client.get_state_info(state)
            layer_str = args.layer or "ALL"
            print(f"\nDOT 511 Events — {info['name']} (layer={layer_str})")
            print(f"Showing {len(events)} events")
            print("-" * 70)
            for evt in events:
                print(f"  [{evt.event_type}] {evt.roadway} — {evt.description[:80]}")
                if evt.direction:
                    print(f"    Direction: {evt.direction}")
                if evt.county:
                    print(f"    County: {evt.county}")
                if evt.start_date:
                    print(f"    Start: {evt.start_date}")
                print()

    elif args.rwis:
        stations = client.get_rwis_stations(state)[:args.limit]
        if args.json:
            out = [
                {
                    "station_id": s.station_id,
                    "name": s.name,
                    "latitude": s.latitude,
                    "longitude": s.longitude,
                    "route_id": s.route_id,
                }
                for s in stations
            ]
            print(json.dumps(out, indent=2))
        else:
            info = client.get_state_info(state)
            print(f"\nDOT 511 RWIS Stations — {info['name']}")
            print(f"Showing {len(stations)} stations")
            print("-" * 70)
            for s in stations:
                print(f"  ID: {s.station_id:>8}  {s.name}")
                if s.latitude:
                    print(f"    Location: {s.latitude:.5f}, {s.longitude:.5f}")
                if s.route_id:
                    print(f"    Route:    {s.route_id}")
                print()

    else:
        print("Specify --cameras, --events, or --rwis")
        parser.print_help()
        sys.exit(1)
