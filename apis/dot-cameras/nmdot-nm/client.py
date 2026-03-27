"""
NMDOT Traffic Camera & Road Conditions Client
==============================================
Reverse-engineered client for the New Mexico Department of Transportation (NMDOT)
traffic information system at https://nmroads.com

No third-party dependencies required — uses Python stdlib only (urllib, json).

Two backend services:
  - servicev5.nmroads.com/RealMapWAR/  (Java/Tomcat, JSONP endpoints)
  - lambdav5.nmroads.com/              (Node.js Lambda proxy, JSON endpoints)

Author: Reverse-engineered from nmroads.com JS bundles
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERVICE_V5_BASE = "https://servicev5.nmroads.com/RealMapWAR/"
LAMBDA_V5_BASE = "https://lambdav5.nmroads.com/"
SNAPSHOT_BASE = "http://ss.nmroads.com/snapshots/"
CAMERA_IMAGE_URL = SERVICE_V5_BASE + "GetCameraImage"
VIDEO_SERVER = "rtmp://video.nmroads.com/nmroads"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Origin": "https://nmroads.com",
    "Referer": "https://nmroads.com/",
}

# Event type IDs used by the system
EVENT_TYPES = {
    5: "Closure",
    6: "Crash",
    7: "Alert",
    8: "Lane Closure",
    9: "Roadwork",
    13: "Fair Driving Conditions",
    14: "Weather Advisory",
    16: "Difficult Driving Conditions",
    17: "Severe Driving Conditions",
    18: "Special Event",
    19: "Construction Closure",
    20: "Seasonal Closure",
    21: "Traffic Signal Power Failure",
}

# Default set of event types shown in public view
PUBLIC_EVENT_TYPES = list(EVENT_TYPES.keys())

# Districts (1-6 plus statewide=0)
DISTRICTS = {
    0: "Statewide",
    1: "District 1 (Gallup)",
    2: "District 2 (Las Cruces)",
    3: "District 3 (Albuquerque)",
    4: "District 4 (Tucumcari)",
    5: "District 5 (Santa Fe)",
    6: "District 6 (Alamogordo)",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """Represents a single traffic camera."""
    name: str
    title: str
    lat: float
    lon: float
    grouping: str
    district: int
    camera_type: str          # "iDome", "Pelco Spectra", "RWIS2", ""
    enabled: bool
    stream: bool
    mobile: bool
    sort_order: int
    snapshot_file: str        # Direct URL to latest JPEG snapshot
    sdp_file_high_res: str    # RTMP stream name (high res)
    sdp_file_med_res: str
    sdp_file_low_res: str
    video_server: str
    resolution: str           # e.g. "D1"
    message: str
    demo: Optional[bool]

    @property
    def snapshot_url(self) -> str:
        """Direct URL to the live snapshot JPEG."""
        return self.snapshot_file

    @property
    def stream_url(self) -> str:
        """RTMP stream URL (requires an RTMP-capable player)."""
        if self.sdp_file_high_res:
            return f"{self.video_server}/{self.sdp_file_high_res}"
        return ""

    @property
    def is_rwis(self) -> bool:
        """True if this is a Road Weather Information System camera."""
        return self.camera_type in ("RWIS", "RWIS2")

    def image_url(self, ts: int = 0) -> str:
        """
        URL to fetch the camera image via the RealMapWAR service.

        Parameters
        ----------
        ts : int
            Timestamp cache-buster (use 0 or current Unix millis).
        """
        params = urllib.parse.urlencode({"cameraName": self.name, "ts": ts})
        return f"{CAMERA_IMAGE_URL}?{params}"

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        return cls(
            name=d.get("name", ""),
            title=d.get("title", ""),
            lat=float(d.get("lat", 0)),
            lon=float(d.get("lon", 0)),
            grouping=d.get("grouping", ""),
            district=int(d.get("district", 0)),
            camera_type=d.get("cameraType", ""),
            enabled=bool(d.get("enabled", False)),
            stream=bool(d.get("stream", False)),
            mobile=bool(d.get("mobile", False)),
            sort_order=int(d.get("sortOrder", 0)),
            snapshot_file=d.get("snapshotFile", ""),
            sdp_file_high_res=d.get("sdpFileHighRes", ""),
            sdp_file_med_res=d.get("sdpFileMedRes", ""),
            sdp_file_low_res=d.get("sdpFileLowRes", ""),
            video_server=d.get("videoServer", VIDEO_SERVER),
            resolution=d.get("resolution", ""),
            message=d.get("message", ""),
            demo=d.get("demo"),
        )

    def __repr__(self) -> str:
        return (
            f"Camera(name={self.name!r}, title={self.title!r}, "
            f"lat={self.lat}, lon={self.lon}, type={self.camera_type!r})"
        )


@dataclass
class TrafficEvent:
    """Represents a road condition / traffic event."""
    guid: str
    event_type: int
    title: str
    description: str
    route_name: str
    route_number: str
    district: int
    county_name: str
    state_name: str
    latitude: float           # Web Mercator Y (EPSG:3857)
    longitude: float          # Web Mercator X (EPSG:3857)
    geometry_type: str        # "point" | "polyline" | "polygon"
    entered_date: str
    update_date: str
    expiration_date: str
    delete_date: str
    patrol_yard: str

    @property
    def event_type_name(self) -> str:
        return EVENT_TYPES.get(self.event_type, f"Unknown ({self.event_type})")

    @property
    def lat_wgs84(self) -> float:
        """
        Convert Web Mercator Y to WGS-84 latitude (approximate).
        The raw lat/lon fields are in EPSG:3857 (Web Mercator) metres.
        """
        import math
        y = self.latitude
        lat_rad = 2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2
        return math.degrees(lat_rad)

    @property
    def lon_wgs84(self) -> float:
        """Convert Web Mercator X to WGS-84 longitude."""
        return self.longitude / 6378137.0 * (180 / 3.14159265358979)

    @classmethod
    def from_dict(cls, d: dict) -> "TrafficEvent":
        return cls(
            guid=d.get("GUID", ""),
            event_type=int(d.get("eventType", 0)),
            title=d.get("title", ""),
            description=d.get("description", ""),
            route_name=d.get("routeName", ""),
            route_number=d.get("routeNumber", ""),
            district=int(d.get("district", 0)),
            county_name=d.get("countyName", ""),
            state_name=d.get("stateName", "") or "",
            latitude=float(d.get("latitude", 0)),
            longitude=float(d.get("longitude", 0)),
            geometry_type=d.get("geometryType", "point"),
            entered_date=d.get("enteredDate", ""),
            update_date=d.get("updateDate", ""),
            expiration_date=d.get("expirationDate", ""),
            delete_date=d.get("deleteDate", ""),
            patrol_yard=d.get("patrolYard", "") or "",
        )

    def __repr__(self) -> str:
        return (
            f"TrafficEvent(type={self.event_type_name!r}, "
            f"title={self.title[:60]!r})"
        )


@dataclass
class SnowPlow:
    """Represents a tracked snow plow / fleet vehicle."""
    device_id: str
    latitude: float
    longitude: float
    bearing: int
    speed: float              # km/h
    is_driving: bool
    is_communicating: bool
    date_time: str
    duration: str             # "HH:MM:SS" since last state change
    groups: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "SnowPlow":
        groups = [g.get("id", "") for g in d.get("groups", [])]
        return cls(
            device_id=d.get("device", {}).get("id", ""),
            latitude=float(d.get("latitude", 0)),
            longitude=float(d.get("longitude", 0)),
            bearing=int(d.get("bearing", 0)),
            speed=float(d.get("speed", 0)),
            is_driving=bool(d.get("isDriving", False)),
            is_communicating=bool(d.get("isDeviceCommunicating", False)),
            date_time=d.get("dateTime", ""),
            duration=d.get("currentStateDuration", ""),
            groups=groups,
        )

    def __repr__(self) -> str:
        status = "moving" if self.is_driving else "stationary"
        return (
            f"SnowPlow(id={self.device_id!r}, "
            f"lat={self.latitude:.4f}, lon={self.longitude:.4f}, "
            f"{status}, {self.speed}km/h)"
        )


@dataclass
class SplashMessage:
    """System-wide splash / alert message (may be disabled)."""
    enabled: bool
    splash_text: str
    splash_timestamp: str
    click_url: Optional[str]
    image_url: Optional[str]

    @classmethod
    def from_dict(cls, d: dict) -> "SplashMessage":
        return cls(
            enabled=d.get("enabled") == "1",
            splash_text=d.get("splashText", ""),
            splash_timestamp=d.get("splashTimestamp", ""),
            click_url=d.get("splashClickURL"),
            image_url=d.get("splashImageURL"),
        )


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> bytes:
    """Perform a GET request and return raw bytes."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _jsonp_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> Any:
    """
    Fetch a JSONP endpoint and return the parsed Python object.

    The server wraps responses as:  callback_name(JSON_PAYLOAD);
    This function strips the wrapper and parses the payload.
    """
    cb = "_cb"
    p = dict(params or {})
    p["callback"] = cb
    raw = _http_get(url, p, timeout).decode("utf-8", errors="replace")
    # Strip JSONP wrapper:  _cb({...});
    m = re.match(r"^[^(]+\((.*)\);?\s*$", raw, re.DOTALL)
    if not m:
        raise ValueError(f"Unexpected JSONP response from {url}: {raw[:200]}")
    return json.loads(m.group(1))


def _json_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> Any:
    """Fetch a plain JSON endpoint and return the parsed object."""
    raw = _http_get(url, params, timeout).decode("utf-8", errors="replace")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class NMDOTClient:
    """
    Client for the NMDOT nmroads.com traffic information system.

    All public methods are read-only. No authentication is required for
    the public data surfaces exposed by this client.

    Usage
    -----
    >>> client = NMDOTClient()
    >>> cameras = client.get_cameras()
    >>> for cam in cameras[:3]:
    ...     print(cam.title, cam.snapshot_url)
    ...
    >>> events = client.get_events()
    >>> for evt in events:
    ...     print(evt.event_type_name, evt.title[:60])
    """

    def __init__(
        self,
        service_base: str = SERVICE_V5_BASE,
        lambda_base: str = LAMBDA_V5_BASE,
        timeout: int = 30,
    ) -> None:
        self.service_base = service_base.rstrip("/") + "/"
        self.lambda_base = lambda_base.rstrip("/") + "/"
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(self) -> List[Camera]:
        """
        Fetch the full list of traffic cameras.

        Returns 183+ Camera objects with metadata including location,
        snapshot URL, stream info, and camera type.

        Endpoint: GET /RealMapWAR/GetCameraInfo (JSONP)
        """
        url = self.service_base + "GetCameraInfo"
        data = _jsonp_get(url, timeout=self.timeout)
        raw_list = data.get("cameraInfo", [])
        return [Camera.from_dict(c) for c in raw_list]

    def get_camera(self, name: str) -> Optional[Camera]:
        """
        Look up a single camera by its unique name (e.g. 'I-25@La_Bajada_Lower').

        Returns None if not found.
        """
        cameras = self.get_cameras()
        name_lower = name.lower()
        for cam in cameras:
            if cam.name.lower() == name_lower:
                return cam
        return None

    def download_camera_image(self, camera: Camera, ts: int = 0) -> bytes:
        """
        Download the current JPEG snapshot for a camera.

        Parameters
        ----------
        camera : Camera
            The camera to fetch.
        ts : int
            Cache-buster timestamp (milliseconds). Use 0 to allow caching,
            or pass int(time.time() * 1000) to force a fresh image.

        Returns
        -------
        bytes
            Raw JPEG image data.

        Endpoint: GET /RealMapWAR/GetCameraImage?cameraName=...&ts=...
        """
        url = self.service_base + "GetCameraImage"
        return _http_get(url, {"cameraName": camera.name, "ts": ts}, self.timeout)

    def download_snapshot(self, camera: Camera) -> bytes:
        """
        Download the camera snapshot directly from the snapshot CDN
        (ss.nmroads.com). This bypasses the RealMapWAR service.

        Returns raw JPEG bytes.
        """
        return _http_get(camera.snapshot_file, timeout=self.timeout)

    def get_camera_timestamp(self, camera: Camera) -> Optional[datetime]:
        """
        Fetch the timestamp of the camera's most recent image.

        Returns a datetime or None if unavailable.

        Endpoint: GET /RealMapWAR/GetCachedObject?key=<name>Time (JSONP)
        """
        url = self.service_base + "GetCachedObject"
        try:
            ts_ms = _jsonp_get(url, {"key": camera.name + "Time"}, self.timeout)
            if isinstance(ts_ms, (int, float)):
                return datetime.fromtimestamp(ts_ms / 1000.0)
        except Exception:
            pass
        return None

    def search_cameras(
        self,
        query: str = "",
        district: Optional[int] = None,
        grouping: Optional[str] = None,
        camera_type: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[Camera]:
        """
        Filter cameras by various criteria.

        Parameters
        ----------
        query : str
            Case-insensitive substring match against camera name or title.
        district : int, optional
            Filter to a specific district (0-6).
        grouping : str, optional
            Filter to a geographic grouping (e.g. 'Albuquerque Area').
        camera_type : str, optional
            Filter by camera type ('iDome', 'RWIS2', 'Pelco Spectra').
        enabled_only : bool
            If True (default), only return enabled cameras.

        Returns
        -------
        List[Camera]
        """
        cameras = self.get_cameras()
        results = []
        query_lower = query.lower()
        for cam in cameras:
            if enabled_only and not cam.enabled:
                continue
            if query and query_lower not in cam.name.lower() and query_lower not in cam.title.lower():
                continue
            if district is not None and cam.district != district:
                continue
            if grouping and cam.grouping.lower() != grouping.lower():
                continue
            if camera_type and cam.camera_type.lower() != camera_type.lower():
                continue
            results.append(cam)
        return results

    # ------------------------------------------------------------------
    # Traffic events / road conditions
    # ------------------------------------------------------------------

    def get_events(
        self,
        event_types: Optional[List[int]] = None,
        return_data: str = "basic",
    ) -> List[TrafficEvent]:
        """
        Fetch active road condition events.

        Parameters
        ----------
        event_types : list of int, optional
            Event type IDs to include. Defaults to all public types.
            See EVENT_TYPES constant for the full mapping.
        return_data : str
            "basic" (default) returns all metadata fields.
            "geometry" returns GUID + geometryAsJSON (polylines/polygons).

        Returns
        -------
        List[TrafficEvent]

        Endpoint: GET /RealMapWAR/GetEventsJSON (JSONP)
        """
        if event_types is None:
            event_types = PUBLIC_EVENT_TYPES
        url = self.service_base + "GetEventsJSON"
        params = {
            "eventType": ",".join(str(t) for t in event_types),
            "returnData": return_data,
        }
        data = _jsonp_get(url, params, self.timeout)
        raw_list = data.get("events", []) or []
        if return_data == "geometry":
            return raw_list  # Return raw dicts with geometryAsJSON
        return [TrafficEvent.from_dict(e) for e in raw_list]

    def get_events_timestamp(self) -> int:
        """
        Fetch the current events data version timestamp.

        Use this for polling: if the returned value changes since your last
        call, new event data is available.

        Returns
        -------
        int
            Monotonically increasing integer version counter.

        Endpoint: GET /RealMapWAR/GetEventsTimestamp (JSONP)
        """
        url = self.service_base + "GetEventsTimestamp"
        data = _jsonp_get(url, timeout=self.timeout)
        return int(data.get("result", 0))

    def get_events_by_type(self, event_type: int) -> List[TrafficEvent]:
        """Fetch events of a single type. See EVENT_TYPES for valid IDs."""
        return self.get_events(event_types=[event_type])

    def get_closures(self) -> List[TrafficEvent]:
        """Fetch active road closures (event type 5)."""
        return self.get_events_by_type(5)

    def get_crashes(self) -> List[TrafficEvent]:
        """Fetch active crash events (event type 6)."""
        return self.get_events_by_type(6)

    def get_roadwork(self) -> List[TrafficEvent]:
        """Fetch active roadwork events (event type 9)."""
        return self.get_events_by_type(9)

    def get_weather_advisories(self) -> List[TrafficEvent]:
        """Fetch active weather advisory events (event type 14)."""
        return self.get_events_by_type(14)

    def get_severe_conditions(self) -> List[TrafficEvent]:
        """Fetch severe driving conditions (event type 17)."""
        return self.get_events_by_type(17)

    # ------------------------------------------------------------------
    # Snow plows / fleet vehicles
    # ------------------------------------------------------------------

    def get_snow_plows(self) -> List[SnowPlow]:
        """
        Fetch current locations of tracked NMDOT fleet vehicles (snow plows,
        help trucks, etc.).

        Returns
        -------
        List[SnowPlow]

        Endpoint: GET /RealMapWAR/GetCachedObject?key=snowPlowLocations (JSONP)
        """
        url = self.service_base + "GetCachedObject"
        data = _jsonp_get(url, {"key": "snowPlowLocations"}, self.timeout)
        if not isinstance(data, list):
            return []
        return [SnowPlow.from_dict(v) for v in data]

    # ------------------------------------------------------------------
    # Splash / system message
    # ------------------------------------------------------------------

    def get_splash_message(self) -> SplashMessage:
        """
        Fetch the system-wide splash message (if any is active).

        Endpoint: GET /RealMapWAR/GetSplashMessage (JSONP)
        """
        url = self.service_base + "GetSplashMessage"
        data = _jsonp_get(url, timeout=self.timeout)
        return SplashMessage.from_dict(data)

    # ------------------------------------------------------------------
    # Generic cached object (advanced)
    # ------------------------------------------------------------------

    def get_cached_object(self, key: str) -> Any:
        """
        Fetch any cached data object by key from the RealMapWAR service.

        Known keys include:
          - "snowPlowLocations"    — snow plow/fleet vehicle positions
          - "<cameraName>Time"     — image capture timestamp for a camera

        Endpoint: GET /RealMapWAR/GetCachedObject?key=... (JSONP)
        """
        url = self.service_base + "GetCachedObject"
        return _jsonp_get(url, {"key": key}, self.timeout)

    # ------------------------------------------------------------------
    # Service health
    # ------------------------------------------------------------------

    def health_check(self) -> dict:
        """
        Check the health of the Lambda proxy service.

        Endpoint: GET https://lambdav5.nmroads.com/Health (JSON)
        """
        url = self.lambda_base + "Health"
        return _json_get(url, timeout=self.timeout)

    # ------------------------------------------------------------------
    # Convenience / utility
    # ------------------------------------------------------------------

    def list_groupings(self) -> List[str]:
        """Return all unique camera geographic groupings."""
        cameras = self.get_cameras()
        return sorted(set(c.grouping for c in cameras if c.grouping))

    def list_camera_types(self) -> List[str]:
        """Return all unique camera types found in the system."""
        cameras = self.get_cameras()
        return sorted(set(c.camera_type for c in cameras if c.camera_type))

    def cameras_by_grouping(self) -> dict:
        """
        Return cameras organised as {grouping: [Camera, ...]} dict.
        """
        cameras = self.get_cameras()
        result: dict = {}
        for cam in cameras:
            result.setdefault(cam.grouping, []).append(cam)
        return result

    def cameras_by_district(self) -> dict:
        """
        Return cameras organised as {district_id: [Camera, ...]} dict.
        """
        cameras = self.get_cameras()
        result: dict = {}
        for cam in cameras:
            result.setdefault(cam.district, []).append(cam)
        return result


# ---------------------------------------------------------------------------
# CLI / quick test
# ---------------------------------------------------------------------------

def _pretty_print_cameras(cameras: List[Camera], limit: int = 5) -> None:
    print(f"\n{'='*60}")
    print(f"  CAMERAS  ({len(cameras)} total, showing first {min(limit, len(cameras))})")
    print(f"{'='*60}")
    for cam in cameras[:limit]:
        print(f"  [{cam.district}] {cam.title}")
        print(f"       name     : {cam.name}")
        print(f"       type     : {cam.camera_type or '(unknown)'}")
        print(f"       grouping : {cam.grouping}")
        print(f"       enabled  : {cam.enabled}  stream: {cam.stream}")
        print(f"       snapshot : {cam.snapshot_url}")
        print()


def _pretty_print_events(events: List[TrafficEvent], limit: int = 5) -> None:
    print(f"\n{'='*60}")
    print(f"  EVENTS  ({len(events)} total, showing first {min(limit, len(events))})")
    print(f"{'='*60}")
    for evt in events[:limit]:
        print(f"  [{evt.event_type_name}]  {evt.title[:70]}")
        print(f"       GUID     : {evt.guid}")
        print(f"       Route    : {evt.route_name} {evt.route_number}")
        print(f"       District : {evt.district}  County: {evt.county_name}")
        print(f"       Updated  : {evt.update_date}")
        print()


def _pretty_print_plows(plows: List[SnowPlow], limit: int = 5) -> None:
    print(f"\n{'='*60}")
    print(f"  SNOW PLOWS  ({len(plows)} total, showing first {min(limit, len(plows))})")
    print(f"{'='*60}")
    for plow in plows[:limit]:
        status = "DRIVING" if plow.is_driving else "stopped"
        comms = "online" if plow.is_communicating else "offline"
        print(f"  Device {plow.device_id:>6s} | {status:>7s} | {plow.speed:>5.0f} km/h | {comms}")
        print(f"           lat={plow.latitude:.5f}  lon={plow.longitude:.5f}")
        print(f"           bearing={plow.bearing}°  since {plow.duration}")
        print()


def run_demo() -> None:
    """Run a live demonstration of all client features."""
    print("NMDOT Traffic Camera System - Python Client Demo")
    print("=" * 60)

    client = NMDOTClient(timeout=30)

    # 1. Health check
    print("\n[1] Service health check")
    try:
        health = client.health_check()
        print(f"    Status  : {health.get('status')}")
        print(f"    Message : {health.get('message')}")
        print(f"    Version : {health.get('version')}")
    except Exception as ex:
        print(f"    Health check failed: {ex}")

    # 2. Splash message
    print("\n[2] System splash message")
    try:
        splash = client.get_splash_message()
        print(f"    Enabled : {splash.enabled}")
        if splash.enabled:
            print(f"    Text    : {splash.splash_text}")
        else:
            print(f"    (no active splash message, last set {splash.splash_timestamp})")
    except Exception as ex:
        print(f"    Error: {ex}")

    # 3. Camera list
    print("\n[3] Camera list")
    try:
        cameras = client.get_cameras()
        _pretty_print_cameras(cameras, limit=3)
        print(f"    Groupings    : {client.list_groupings()}")
        print(f"    Camera types : {client.list_camera_types()}")
    except Exception as ex:
        print(f"    Error: {ex}")

    # 4. Download a camera image
    print("\n[4] Download camera image (I-25@La_Bajada_Lower)")
    try:
        cam = client.get_camera("I-25@La_Bajada_Lower")
        if cam:
            ts = client.get_camera_timestamp(cam)
            print(f"    Camera      : {cam.title}")
            print(f"    Last image  : {ts}")
            img = client.download_camera_image(cam)
            print(f"    Image size  : {len(img)} bytes (JPEG)")
        else:
            print("    Camera not found")
    except Exception as ex:
        print(f"    Error: {ex}")

    # 5. Events
    print("\n[5] Road condition events")
    try:
        events = client.get_events()
        _pretty_print_events(events, limit=3)
        ts = client.get_events_timestamp()
        print(f"    Events timestamp (version): {ts}")
    except Exception as ex:
        print(f"    Error: {ex}")

    # 6. Filtered events
    print("\n[6] Active closures and crashes")
    try:
        closures = client.get_closures()
        crashes = client.get_crashes()
        print(f"    Closures : {len(closures)}")
        for c in closures[:2]:
            print(f"      - {c.title[:70]}")
        print(f"    Crashes  : {len(crashes)}")
        for c in crashes[:2]:
            print(f"      - {c.title[:70]}")
    except Exception as ex:
        print(f"    Error: {ex}")

    # 7. Snow plows
    print("\n[7] Snow plow / fleet vehicle locations")
    try:
        plows = client.get_snow_plows()
        _pretty_print_plows(plows, limit=3)
        active = [p for p in plows if p.is_driving]
        print(f"    Total vehicles    : {len(plows)}")
        print(f"    Currently moving  : {len(active)}")
    except Exception as ex:
        print(f"    Error: {ex}")

    # 8. Camera search
    print("\n[8] Camera search (I-25 corridor)")
    try:
        i25_cams = client.search_cameras(query="I-25")
        print(f"    Found {len(i25_cams)} cameras matching 'I-25'")
        for cam in i25_cams[:4]:
            print(f"      {cam.name:30s}  {cam.title}")
    except Exception as ex:
        print(f"    Error: {ex}")

    print("\n" + "=" * 60)
    print("Demo complete.")


if __name__ == "__main__":
    run_demo()
