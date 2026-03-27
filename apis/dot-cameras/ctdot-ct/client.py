#!/usr/bin/env python3
"""
CTDOT / CT Travel Smart Traffic Camera & Incident Client
=========================================================
Reverse-engineered client for the Connecticut Department of Transportation
traffic information system at https://www.ctroads.org (CT Travel Smart).

All endpoints were discovered by analysing the JavaScript bundles served at:
  - /bundles/map
  - /bundles/map511
  - /bundles/511GoogleMapComp
  - /bundles/listCctv
  - /bundles/datatables
  - /scripts/jsresources/map/map

No API key is required for public read endpoints.
Camera images are served through AWS CloudFront (content-type: image/jpeg).

Author: Claude Code (reverse-engineered 2026-03-27)
Python: 3.8+ stdlib only (urllib, json, gzip, dataclasses, datetime)
"""

from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.ctroads.org"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.ctroads.org/",
}

# Layer IDs used throughout the site's JavaScript
LAYER_CAMERAS = "Cameras"
LAYER_INCIDENTS = "Incidents"
LAYER_CLOSURES = "Closures"
LAYER_CONSTRUCTION = "Construction"
LAYER_CONGESTION = "Congestion"
LAYER_TRANSIT_INCIDENTS = "TransitIncidents"
LAYER_TRANSIT_CONSTRUCTION = "TransitConstruction"
LAYER_MESSAGE_SIGNS = "MessageSigns"
LAYER_WEATHER_ALERTS = "WeatherAlerts"
LAYER_WEATHER_INCIDENTS = "WeatherIncidents"
LAYER_WEATHER_FORECAST = "WeatherForecast"

ALL_INCIDENT_LAYERS = (
    LAYER_INCIDENTS,
    LAYER_CLOSURES,
    LAYER_CONSTRUCTION,
    LAYER_CONGESTION,
)

# Roadway identifiers seen in camera data
HIGHWAY_I84 = "I-84"
HIGHWAY_I91 = "I-91"
HIGHWAY_I95 = "I-95"
HIGHWAY_I291 = "I-291"
HIGHWAY_I395 = "I-395"
HIGHWAY_I691 = "I-691"
HIGHWAY_MERRITT = "RT 15"  # Merritt Parkway / Route 15
HIGHWAY_RT2 = "RT 2"
HIGHWAY_RT8 = "RT 8"
HIGHWAY_RT9 = "RT 9"

CAMERA_REFRESH_MS = 10_000  # 10 seconds – site's default refresh rate


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class CameraImage:
    """A single image/stream associated with a traffic camera."""
    id: int
    camera_site_id: int
    description: str
    image_url: str
    """Relative URL such as /map/Cctv/{id}. Prepend BASE_URL for full URL."""
    refresh_rate_ms: int
    video_url: Optional[str]
    video_type: Optional[str]
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool

    @property
    def full_image_url(self) -> str:
        """Absolute URL for the JPEG camera snapshot."""
        return BASE_URL + self.image_url

    @property
    def cache_bust_url(self) -> str:
        """Snapshot URL with a cache-busting timestamp (matches browser behaviour)."""
        return f"{BASE_URL}{self.image_url}?t={int(time.time())}"

    @classmethod
    def from_dict(cls, d: dict) -> "CameraImage":
        return cls(
            id=d["id"],
            camera_site_id=d["cameraSiteId"],
            description=d.get("description") or "",
            image_url=d["imageUrl"],
            refresh_rate_ms=d.get("refreshRateMs", CAMERA_REFRESH_MS),
            video_url=d.get("videoUrl"),
            video_type=d.get("videoType"),
            is_video_auth_required=bool(d.get("isVideoAuthRequired", False)),
            video_disabled=bool(d.get("videoDisabled", False)),
            disabled=bool(d.get("disabled", False)),
            blocked=bool(d.get("blocked", False)),
        )


@dataclass
class Camera:
    """A CTDOT traffic camera with location, roadway, and image information."""
    id: int
    source_id: str
    source: str
    """Data provider – always 'TRAFFICLAND' for CTDOT cameras."""
    type: str
    roadway: str
    direction: str
    location: str
    """Human-readable location description, e.g. 'CAM 1 Vernon I-84 WB Exit 64'."""
    latitude: float
    longitude: float
    city: str
    county: Optional[str]
    region: Optional[str]
    state: str
    sort_id_display: str
    """Route number and mile-marker string, e.g. '84 - 72.8174'."""
    images: List[CameraImage] = field(default_factory=list)
    created: Optional[str] = None
    last_updated: Optional[str] = None

    @property
    def primary_image(self) -> Optional[CameraImage]:
        """Return the first (primary) image for this camera, or None."""
        return self.images[0] if self.images else None

    @property
    def snapshot_url(self) -> Optional[str]:
        """Absolute JPEG snapshot URL for the primary image."""
        if self.primary_image:
            return self.primary_image.full_image_url
        return None

    @classmethod
    def from_list_dict(cls, d: dict) -> "Camera":
        """Parse a camera record as returned by POST /List/GetData/Cameras."""
        lat_lng = d.get("latLng", {})
        # Coordinates are embedded in WKT: "POINT (-72.501513 41.823175)"
        lat, lon = 0.0, 0.0
        geography = lat_lng.get("geography", {})
        wkt = geography.get("wellKnownText", "")
        if wkt.startswith("POINT"):
            try:
                coords = wkt.replace("POINT", "").strip().strip("()").split()
                lon, lat = float(coords[0]), float(coords[1])
            except (IndexError, ValueError):
                pass

        images = [CameraImage.from_dict(img) for img in d.get("images", [])]
        return cls(
            id=d["id"],
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            type=d.get("type", ""),
            roadway=d.get("roadway", ""),
            direction=d.get("direction", ""),
            location=d.get("location", ""),
            latitude=lat,
            longitude=lon,
            city=d.get("city", ""),
            county=d.get("county"),
            region=d.get("region"),
            state=d.get("state", ""),
            sort_id_display=d.get("sortIdDisplay", ""),
            images=images,
            created=d.get("created"),
            last_updated=d.get("lastUpdated"),
        )

    @classmethod
    def from_icon_dict(cls, d: dict) -> "Camera":
        """Parse a minimal camera record from GET /map/mapIcons/Cameras."""
        loc = d.get("location", [0.0, 0.0])
        return cls(
            id=int(d["itemId"]),
            source_id="",
            source="",
            type="",
            roadway="",
            direction="",
            location=d.get("title", ""),
            latitude=float(loc[0]) if len(loc) > 1 else 0.0,
            longitude=float(loc[1]) if len(loc) > 1 else 0.0,
            city="",
            county=None,
            region=None,
            state="Connecticut",
            sort_id_display="",
            images=[],
        )


@dataclass
class MapIcon:
    """A generic map icon entry (camera, event, sign, etc.)."""
    item_id: str
    latitude: float
    longitude: float
    title: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "MapIcon":
        loc = d.get("location", [0.0, 0.0])
        return cls(
            item_id=str(d["itemId"]),
            latitude=float(loc[0]) if len(loc) > 1 else 0.0,
            longitude=float(loc[1]) if len(loc) > 1 else 0.0,
            title=d.get("title", ""),
        )


@dataclass
class TrafficEvent:
    """A traffic event (incident, closure, congestion delay, construction)."""
    id: int
    type: str
    """E.g. 'Delays', 'Closure', 'Construction', 'Incident'."""
    layer_name: str
    """Layer ID such as 'Congestion', 'Incidents', 'Closures', 'Construction'."""
    roadway_name: str
    description: str
    source_id: str
    source: str
    event_sub_type: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    last_updated: Optional[str]
    is_full_closure: bool
    severity: str
    direction: str
    location_description: Optional[str]
    lane_description: Optional[str]
    detour_description: Optional[str]
    region: Optional[str]
    state: str
    show_on_map: bool
    estimated_duration: Optional[str]

    @classmethod
    def from_dict(cls, d: dict) -> "TrafficEvent":
        return cls(
            id=d["id"],
            type=d.get("type", ""),
            layer_name=d.get("layerName", ""),
            roadway_name=d.get("roadwayName", ""),
            description=d.get("description", ""),
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            event_sub_type=d.get("eventSubType"),
            start_date=d.get("startDate"),
            end_date=d.get("endDate"),
            last_updated=d.get("lastUpdated"),
            is_full_closure=bool(d.get("isFullClosure", False)),
            severity=d.get("severity", "unknown"),
            direction=d.get("direction", ""),
            location_description=d.get("locationDescription"),
            lane_description=d.get("laneDescription"),
            detour_description=d.get("detourDescription"),
            region=d.get("region"),
            state=d.get("state", "Connecticut"),
            show_on_map=bool(d.get("showOnMap", True)),
            estimated_duration=d.get("estimatedDuration"),
        )


@dataclass
class MessageSign:
    """A variable message sign (VMS/DMS) on the highway network."""
    id: int
    roadway_name: str
    direction: str
    name: str
    area: str
    description: str
    message: str
    """Primary message – may contain HTML <br/> tags."""
    message2: str
    message3: str
    status: str
    last_updated: Optional[str]

    @property
    def message_text(self) -> str:
        """Plain-text version of the primary message (strips <br/> tags)."""
        return self.message.replace("<br/>", "\n").replace("<br>", "\n").strip()

    @classmethod
    def from_dict(cls, d: dict) -> "MessageSign":
        return cls(
            id=int(d["DT_RowId"]),
            roadway_name=d.get("roadwayName", ""),
            direction=d.get("direction", ""),
            name=d.get("name", ""),
            area=d.get("area", "N/A"),
            description=d.get("description", ""),
            message=d.get("message", ""),
            message2=d.get("message2", ""),
            message3=d.get("message3", ""),
            status=d.get("status", "OK"),
            last_updated=d.get("lastUpdated"),
        )


@dataclass
class WeatherStation:
    """A CTDOT weather forecast station location."""
    item_id: str
    latitude: float
    longitude: float
    title: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "WeatherStation":
        loc = d.get("location", [0.0, 0.0])
        return cls(
            item_id=str(d["itemId"]),
            latitude=float(loc[0]) if len(loc) > 1 else 0.0,
            longitude=float(loc[1]) if len(loc) > 1 else 0.0,
            title=d.get("title", ""),
        )


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------

class CTDOTError(Exception):
    """Raised for HTTP or JSON errors from the CTDOT API."""


def _http(
    url: str,
    method: str = "GET",
    form_data: Optional[dict] = None,
    json_data: Optional[dict] = None,
    timeout: int = 30,
) -> bytes:
    """
    Perform an HTTP request and return the raw (decoded) response body.

    Handles gzip-compressed responses transparently.

    Args:
        url:        Full URL to request.
        method:     HTTP method ('GET' or 'POST').
        form_data:  Optional dict to encode as application/x-www-form-urlencoded.
        json_data:  Optional dict to encode as application/json body.
        timeout:    Request timeout in seconds.

    Returns:
        Raw response bytes (gzip-decompressed if needed).

    Raises:
        CTDOTError: On HTTP errors or network failures.
    """
    headers = dict(DEFAULT_HEADERS)
    body: Optional[bytes] = None

    if form_data is not None:
        body = urllib.parse.urlencode(form_data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_data is not None:
        body = json.dumps(json_data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.info().get("Content-Encoding", "")
            if enc == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw
    except urllib.error.HTTPError as exc:
        raise CTDOTError(
            f"HTTP {exc.code} for {url}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise CTDOTError(f"Network error for {url}: {exc.reason}") from exc


def _get_json(url: str, timeout: int = 30) -> dict:
    """GET a URL and parse JSON response."""
    raw = _http(url, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CTDOTError(f"Invalid JSON from {url}: {exc}") from exc


def _post_json(url: str, form_data: dict, timeout: int = 30) -> dict:
    """POST form-encoded data and parse JSON response."""
    raw = _http(url, method="POST", form_data=form_data, timeout=timeout)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CTDOTError(f"Invalid JSON from {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Endpoint Wrappers
# ---------------------------------------------------------------------------

class CTDOTClient:
    """
    Client for the CT Travel Smart / CTDOT traffic information API.

    All public methods are stateless and make fresh HTTP requests. There is no
    session, cookie, or authentication required for the public read endpoints.

    Example::

        client = CTDOTClient()

        # List all I-95 cameras
        for cam in client.get_cameras(roadway="I-95"):
            print(cam.id, cam.location, cam.snapshot_url)

        # Current traffic events
        for event in client.get_traffic_events():
            print(event.severity, event.roadway_name, event.description)

        # Message signs
        for sign in client.get_message_signs():
            print(sign.name, sign.message_text)
    """

    def __init__(self, base_url: str = BASE_URL, timeout: int = 30):
        """
        Initialise the client.

        Args:
            base_url: Override the default base URL (useful for testing).
            timeout:  HTTP request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return self.base_url + path

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def get_camera_icons(self) -> List[MapIcon]:
        """
        Return lightweight map-icon entries for all 347 CT traffic cameras.

        Endpoint: GET /map/mapIcons/Cameras

        Each entry contains only the camera ID and coordinates. Use
        :meth:`get_cameras` for full metadata including image URLs.

        Returns:
            List of :class:`MapIcon` objects.
        """
        data = _get_json(self._url("/map/mapIcons/Cameras"), self.timeout)
        return [MapIcon.from_dict(d) for d in data.get("item2", [])]

    def get_cameras(
        self,
        roadway: Optional[str] = None,
        city: Optional[str] = None,
        direction: Optional[str] = None,
        page_size: int = 100,
    ) -> List[Camera]:
        """
        Return full camera records, optionally filtered by roadway/city/direction.

        Endpoint: POST /List/GetData/Cameras  (DataTables server-side pagination)

        All 347 cameras are retrieved through automatic pagination. The server
        limits each page to 100 records regardless of the requested length.

        Args:
            roadway:    Filter by roadway string, e.g. ``"I-95"`` or ``"I-84"``.
                        Substring match (case-insensitive).
            city:       Filter by city name, substring match.
            direction:  Filter by direction, e.g. ``"Northbound"`` or ``"SB"``.
            page_size:  Records per request (default 100; server caps at 100).

        Returns:
            List of :class:`Camera` objects sorted by sort_order.

        Example::

            # All I-95 cameras
            i95 = client.get_cameras(roadway="I-95")

            # Merritt Parkway cameras (Route 15)
            merritt = client.get_cameras(roadway="RT 15")
        """
        all_cameras: List[Camera] = []
        start = 0
        url = self._url("/List/GetData/Cameras")

        while True:
            form = {"draw": 1, "start": start, "length": page_size}
            data = _post_json(url, form_data=form, timeout=self.timeout)
            batch = data.get("data", [])
            all_cameras.extend(Camera.from_list_dict(d) for d in batch)
            start += len(batch)
            if len(batch) < page_size or start >= data.get("recordsTotal", 0):
                break

        # Apply optional client-side filters
        result = all_cameras
        if roadway:
            rw_lower = roadway.lower()
            result = [c for c in result if rw_lower in c.roadway.lower()]
        if city:
            city_lower = city.lower()
            result = [c for c in result if city_lower in c.city.lower()]
        if direction:
            dir_lower = direction.lower()
            result = [c for c in result if dir_lower in c.direction.lower()]

        return result

    def get_camera(self, camera_id: int) -> Optional[Camera]:
        """
        Return a single camera by ID, or None if not found.

        Internally retrieves all cameras and filters; the API has no single-item
        endpoint for full camera metadata.

        Args:
            camera_id: Integer camera site ID.

        Returns:
            :class:`Camera` or None.
        """
        for cam in self.get_cameras():
            if cam.id == camera_id:
                return cam
        return None

    def get_camera_latlon(self, camera_id: int) -> Optional[tuple]:
        """
        Return ``(latitude, longitude)`` for a single camera.

        Endpoint: POST /Camera/GetLatLng?id={camera_id}

        This is the fast lightweight endpoint used by the map when centering
        on a specific camera.

        Args:
            camera_id: Integer camera site ID.

        Returns:
            Tuple ``(lat, lon)`` or None if the camera is not found.
        """
        url = self._url(f"/Camera/GetLatLng?id={camera_id}")
        data = _post_json(url, form_data={}, timeout=self.timeout)
        if data and data.get("latitude") is not None:
            return (float(data["latitude"]), float(data["longitude"]))
        return None

    def get_camera_snapshot(self, camera_id: int) -> bytes:
        """
        Download the current JPEG snapshot for a camera.

        Endpoint: GET /map/Cctv/{camera_id}

        Images are served from AWS CloudFront via the CTDOT backend.
        The site refreshes images every 10 seconds (CAMERA_REFRESH_MS).

        Args:
            camera_id: Integer camera site ID.

        Returns:
            JPEG image bytes. May be empty (b'') if the camera is offline.

        Example::

            jpeg = client.get_camera_snapshot(536)
            with open("i95_cam.jpg", "wb") as f:
                f.write(jpeg)
        """
        url = self._url(f"/map/Cctv/{camera_id}")
        return _http(url, timeout=self.timeout)

    def iter_camera_snapshots(
        self,
        camera_ids: List[int],
        interval_s: float = 10.0,
        count: int = 0,
    ) -> Iterator[tuple]:
        """
        Yield ``(camera_id, timestamp, jpeg_bytes)`` on a fixed interval.

        Args:
            camera_ids: List of camera IDs to poll.
            interval_s: Seconds between refresh rounds (default 10, matching
                        the site's CAMERA_REFRESH_MS = 10000).
            count:      Total snapshots to yield per camera (0 = infinite).

        Yields:
            Tuples of ``(camera_id: int, timestamp: float, jpeg: bytes)``.
        """
        fetched = 0
        while count == 0 or fetched < count * len(camera_ids):
            round_start = time.monotonic()
            for cid in camera_ids:
                try:
                    jpeg = self.get_camera_snapshot(cid)
                    yield cid, time.time(), jpeg
                    fetched += 1
                except CTDOTError:
                    pass
            elapsed = time.monotonic() - round_start
            sleep_s = max(0.0, interval_s - elapsed)
            if sleep_s > 0:
                time.sleep(sleep_s)

    # ------------------------------------------------------------------
    # Traffic events
    # ------------------------------------------------------------------

    def get_event_icons(self, layer: str) -> List[MapIcon]:
        """
        Return lightweight map-icon entries for a given event layer.

        Endpoint: GET /map/mapIcons/{layer}

        Args:
            layer: One of the LAYER_* constants, e.g. ``LAYER_INCIDENTS``.

        Returns:
            List of :class:`MapIcon` objects.
        """
        data = _get_json(self._url(f"/map/mapIcons/{layer}"), self.timeout)
        return [MapIcon.from_dict(d) for d in data.get("item2", [])]

    def get_traffic_events(
        self,
        roadway: Optional[str] = None,
        event_type: Optional[str] = None,
        layer: Optional[str] = None,
    ) -> List[TrafficEvent]:
        """
        Return all current traffic events (incidents, delays, closures, etc.).

        Endpoint: POST /List/GetData/traffic

        The ``traffic`` endpoint aggregates all event layers into a single
        response. Active delays (Congestion layer) are the most frequently
        populated.

        Args:
            roadway:    Optional roadway substring filter, e.g. ``"I-95"``.
            event_type: Optional event type filter, e.g. ``"Delays"``,
                        ``"Closure"``, ``"Construction"``.
            layer:      Optional layer name filter, e.g. ``"Congestion"``.

        Returns:
            List of :class:`TrafficEvent` objects.

        Example::

            for evt in client.get_traffic_events(roadway="I-95"):
                print(evt.severity, evt.description)
        """
        url = self._url("/List/GetData/traffic")
        form = {"draw": 1, "start": 0, "length": 500}
        data = _post_json(url, form_data=form, timeout=self.timeout)
        events = [TrafficEvent.from_dict(d) for d in data.get("data", [])]

        if roadway:
            rw_lower = roadway.lower()
            events = [e for e in events if rw_lower in e.roadway_name.lower()]
        if event_type:
            et_lower = event_type.lower()
            events = [e for e in events if et_lower in e.type.lower()]
        if layer:
            lay_lower = layer.lower()
            events = [e for e in events if lay_lower in e.layer_name.lower()]

        return events

    def get_incidents(self, roadway: Optional[str] = None) -> List[TrafficEvent]:
        """Return only incident-type events (excludes delays/construction)."""
        return self.get_traffic_events(roadway=roadway, layer=LAYER_INCIDENTS)

    def get_congestion(self, roadway: Optional[str] = None) -> List[TrafficEvent]:
        """Return congestion/delay events."""
        return self.get_traffic_events(roadway=roadway, layer=LAYER_CONGESTION)

    def get_construction(self, roadway: Optional[str] = None) -> List[TrafficEvent]:
        """Return active construction events."""
        events_icons = self.get_event_icons(LAYER_CONSTRUCTION)
        # Try the list endpoint first; fall back to icon count only
        url = self._url("/List/GetData/Construction")
        try:
            form = {"draw": 1, "start": 0, "length": 500}
            data = _post_json(url, form_data=form, timeout=self.timeout)
            events = [TrafficEvent.from_dict(d) for d in data.get("data", [])]
        except CTDOTError:
            # Fall back to aggregated traffic endpoint
            events = self.get_traffic_events(roadway=roadway, layer=LAYER_CONSTRUCTION)

        if roadway:
            rw_lower = roadway.lower()
            events = [e for e in events if rw_lower in e.roadway_name.lower()]
        return events

    def get_closures(self, roadway: Optional[str] = None) -> List[TrafficEvent]:
        """Return road closure events."""
        return self.get_traffic_events(roadway=roadway, layer=LAYER_CLOSURES)

    # ------------------------------------------------------------------
    # Message signs
    # ------------------------------------------------------------------

    def get_message_sign_icons(self) -> List[MapIcon]:
        """
        Return map-icon locations for all variable message signs.

        Endpoint: GET /map/mapIcons/MessageSigns
        """
        data = _get_json(self._url("/map/mapIcons/MessageSigns"), self.timeout)
        return [MapIcon.from_dict(d) for d in data.get("item2", [])]

    def get_message_signs(
        self,
        roadway: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> List[MessageSign]:
        """
        Return current messages shown on all variable message signs.

        Endpoint: POST /List/GetData/MessageSigns

        Args:
            roadway:   Optional roadway filter, e.g. ``"I-84"``.
            direction: Optional direction filter, e.g. ``"Eastbound"``.

        Returns:
            List of :class:`MessageSign` objects.

        Example::

            for sign in client.get_message_signs(roadway="I-95"):
                print(sign.name)
                print(sign.message_text)
        """
        all_signs: List[MessageSign] = []
        start = 0
        page_size = 100
        url = self._url("/List/GetData/MessageSigns")

        while True:
            form = {"draw": 1, "start": start, "length": page_size}
            data = _post_json(url, form_data=form, timeout=self.timeout)
            batch = data.get("data", [])
            all_signs.extend(MessageSign.from_dict(d) for d in batch)
            start += len(batch)
            if len(batch) < page_size or start >= data.get("recordsTotal", 0):
                break

        if roadway:
            rw_lower = roadway.lower()
            all_signs = [s for s in all_signs if rw_lower in s.roadway_name.lower()]
        if direction:
            dir_lower = direction.lower()
            all_signs = [s for s in all_signs if dir_lower in s.direction.lower()]

        return all_signs

    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------

    def get_weather_forecast_locations(self) -> List[WeatherStation]:
        """
        Return the locations of CTDOT weather forecast stations.

        Endpoint: GET /map/mapIcons/WeatherForecast

        Use :meth:`get_tooltip_html` with layer ``LAYER_WEATHER_FORECAST``
        and a station ID to retrieve the actual forecast HTML.

        Returns:
            List of :class:`WeatherStation` objects.
        """
        data = _get_json(
            self._url("/map/mapIcons/WeatherForecast"), self.timeout
        )
        return [WeatherStation.from_dict(d) for d in data.get("item2", [])]

    # ------------------------------------------------------------------
    # Generic tooltip / detail HTML
    # ------------------------------------------------------------------

    def get_tooltip_html(
        self, layer: str, item_id: str, lang: str = "en"
    ) -> str:
        """
        Return the HTML tooltip fragment for any map layer item.

        Endpoint: GET /tooltip/{layer}/{item_id}?lang={lang}

        This is the same endpoint the map page calls when the user clicks on
        a camera, event, message sign, or weather icon.

        Args:
            layer:   Layer name, e.g. ``"Cameras"``, ``"Congestion"``,
                     ``"MessageSigns"``, ``"WeatherForecast"``.
            item_id: The item's string ID (camera ID, event ID, etc.).
            lang:    Language code (default ``"en"``).

        Returns:
            HTML string containing the tooltip content.

        Example::

            html = client.get_tooltip_html("Cameras", "536")
            # Contains camera title, description, and <img> tag
        """
        url = self._url(
            f"/tooltip/{layer}/{urllib.parse.quote(str(item_id))}?lang={lang}"
        )
        raw = _http(url, timeout=self.timeout)
        return raw.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Traffic tiles
    # ------------------------------------------------------------------

    def get_traffic_tile_url(self, x: int, y: int, z: int) -> str:
        """
        Return the URL for a traffic speed map tile.

        Endpoint: https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}

        Tiles use the standard XYZ slippy-map tile addressing scheme.

        Args:
            x, y: Tile coordinates.
            z:    Zoom level.

        Returns:
            Full URL string.
        """
        return (
            f"https://tiles.ibi511.com/Geoservice/GetTrafficTile"
            f"?x={x}&y={y}&z={z}"
        )

    def download_traffic_tile(self, x: int, y: int, z: int) -> bytes:
        """
        Download a traffic speed overlay tile (PNG).

        Args:
            x, y: Tile coordinates.
            z:    Zoom level.

        Returns:
            PNG image bytes.
        """
        url = self.get_traffic_tile_url(x, y, z)
        return _http(url, timeout=self.timeout)

    # ------------------------------------------------------------------
    # Convenience: named highway helpers
    # ------------------------------------------------------------------

    def get_i95_cameras(self) -> List[Camera]:
        """Return all cameras on Interstate 95."""
        return self.get_cameras(roadway=HIGHWAY_I95)

    def get_i84_cameras(self) -> List[Camera]:
        """Return all cameras on Interstate 84."""
        return self.get_cameras(roadway=HIGHWAY_I84)

    def get_i91_cameras(self) -> List[Camera]:
        """Return all cameras on Interstate 91."""
        return self.get_cameras(roadway=HIGHWAY_I91)

    def get_merritt_cameras(self) -> List[Camera]:
        """Return cameras on the Merritt Parkway (Route 15)."""
        return self.get_cameras(roadway=HIGHWAY_MERRITT)

    def get_i95_events(self) -> List[TrafficEvent]:
        """Return current traffic events on Interstate 95."""
        return self.get_traffic_events(roadway=HIGHWAY_I95)

    def get_i84_events(self) -> List[TrafficEvent]:
        """Return current traffic events on Interstate 84."""
        return self.get_traffic_events(roadway=HIGHWAY_I84)


# ---------------------------------------------------------------------------
# CLI Demo
# ---------------------------------------------------------------------------

def _print_separator(title: str = "", width: int = 72) -> None:
    if title:
        print(f"\n{'=' * width}")
        print(f"  {title}")
        print(f"{'=' * width}")
    else:
        print("-" * width)


def demo() -> None:
    """Run a live CLI demonstration of the CTDOT client."""
    client = CTDOTClient()

    # ------------------------------------------------------------------ #
    # 1. Camera count and highway summary
    # ------------------------------------------------------------------ #
    _print_separator("CTDOT Camera Inventory")
    print("Fetching all cameras...")
    all_cameras = client.get_cameras()
    print(f"Total cameras: {len(all_cameras)}")

    roadways: dict[str, int] = {}
    for cam in all_cameras:
        rw = cam.roadway.split()[0] if cam.roadway else "Unknown"
        roadways[rw] = roadways.get(rw, 0) + 1
    for rw, cnt in sorted(roadways.items()):
        print(f"  {rw:<20} {cnt:>4} cameras")

    # ------------------------------------------------------------------ #
    # 2. I-95 cameras (first 5)
    # ------------------------------------------------------------------ #
    _print_separator("I-95 Cameras (first 5)")
    i95_cams = client.get_i95_cameras()
    print(f"Total I-95 cameras: {len(i95_cams)}")
    for cam in i95_cams[:5]:
        print(f"  [{cam.id:4d}] {cam.location}")
        print(f"         {cam.direction} | {cam.city}")
        print(f"         snapshot: {cam.snapshot_url}")

    # ------------------------------------------------------------------ #
    # 3. Merritt Parkway cameras
    # ------------------------------------------------------------------ #
    _print_separator("Merritt Parkway (RT 15) Cameras")
    merritt = client.get_merritt_cameras()
    print(f"Total Merritt cameras: {len(merritt)}")
    for cam in merritt:
        print(f"  [{cam.id:4d}] {cam.location}")

    # ------------------------------------------------------------------ #
    # 4. I-84 cameras (first 5)
    # ------------------------------------------------------------------ #
    _print_separator("I-84 Cameras (first 5)")
    i84_cams = client.get_i84_cameras()
    print(f"Total I-84 cameras: {len(i84_cams)}")
    for cam in i84_cams[:5]:
        print(f"  [{cam.id:4d}] {cam.location} | {cam.direction}")

    # ------------------------------------------------------------------ #
    # 5. Current traffic events
    # ------------------------------------------------------------------ #
    _print_separator("Current Traffic Events")
    events = client.get_traffic_events()
    print(f"Active events: {len(events)}")
    for evt in events[:10]:
        print(f"  [{evt.id}] {evt.type} on {evt.roadway_name} ({evt.direction})")
        print(f"    Severity: {evt.severity} | Layer: {evt.layer_name}")
        desc = evt.description[:100] + "..." if len(evt.description) > 100 else evt.description
        print(f"    {desc}")

    # ------------------------------------------------------------------ #
    # 6. I-95 congestion
    # ------------------------------------------------------------------ #
    _print_separator("I-95 Congestion Events")
    i95_congestion = client.get_congestion(roadway="I-95")
    print(f"I-95 congestion events: {len(i95_congestion)}")
    for evt in i95_congestion:
        print(f"  {evt.roadway_name} {evt.direction}: {evt.event_sub_type}")
        print(f"    {evt.description[:80]}")

    # ------------------------------------------------------------------ #
    # 7. Variable message signs
    # ------------------------------------------------------------------ #
    _print_separator("Variable Message Signs (first 8)")
    signs = client.get_message_signs()
    print(f"Total signs: {len(signs)}")
    for sign in signs[:8]:
        msg = sign.message_text.replace("\n", " | ")
        print(f"  {sign.name:<40} [{sign.status}]")
        print(f"    {msg}")

    # ------------------------------------------------------------------ #
    # 8. I-84 message signs
    # ------------------------------------------------------------------ #
    _print_separator("I-84 Variable Message Signs")
    i84_signs = client.get_message_signs(roadway="I-84")
    print(f"I-84 signs: {len(i84_signs)}")
    for sign in i84_signs[:5]:
        print(f"  {sign.name} ({sign.direction}): {sign.message_text[:60]}")

    # ------------------------------------------------------------------ #
    # 9. Weather forecast locations
    # ------------------------------------------------------------------ #
    _print_separator("Weather Forecast Stations")
    wx_locs = client.get_weather_forecast_locations()
    print(f"Stations: {len(wx_locs)}")
    for loc in wx_locs[:4]:
        print(f"  ID={loc.item_id} at ({loc.latitude:.4f}, {loc.longitude:.4f})")

    # ------------------------------------------------------------------ #
    # 10. Single camera snapshot download
    # ------------------------------------------------------------------ #
    _print_separator("Camera Snapshot Download Demo")
    if i95_cams:
        cam = i95_cams[0]
        print(f"Downloading snapshot for: {cam.location}")
        print(f"  URL: {cam.snapshot_url}")
        try:
            jpeg = client.get_camera_snapshot(cam.id)
            size_kb = len(jpeg) / 1024
            if jpeg:
                print(f"  Downloaded: {size_kb:.1f} KB (JPEG)")
            else:
                print("  Camera offline (0 bytes returned)")
        except CTDOTError as exc:
            print(f"  Error: {exc}")

    _print_separator()
    print("\nDemo complete.")
    print()
    print("Key API endpoints:")
    print(f"  Cameras list:     POST {BASE_URL}/List/GetData/Cameras")
    print(f"  Camera snapshot:  GET  {BASE_URL}/map/Cctv/{{id}}")
    print(f"  Camera icons:     GET  {BASE_URL}/map/mapIcons/Cameras")
    print(f"  Traffic events:   POST {BASE_URL}/List/GetData/traffic")
    print(f"  Message signs:    POST {BASE_URL}/List/GetData/MessageSigns")
    print(f"  Weather forecast: GET  {BASE_URL}/map/mapIcons/WeatherForecast")
    print(f"  Tooltip HTML:     GET  {BASE_URL}/tooltip/{{layer}}/{{id}}?lang=en")
    print(f"  Traffic tiles:    GET  https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={{x}}&y={{y}}&z={{z}}")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="CTDOT / CT Travel Smart traffic camera and incident client"
    )
    sub = parser.add_subparsers(dest="cmd")

    p_cameras = sub.add_parser("cameras", help="List traffic cameras")
    p_cameras.add_argument("--roadway", help="Filter by roadway, e.g. I-95")
    p_cameras.add_argument("--city", help="Filter by city name")
    p_cameras.add_argument("--json", action="store_true", help="Output JSON")

    p_events = sub.add_parser("events", help="List traffic events")
    p_events.add_argument("--roadway", help="Filter by roadway")
    p_events.add_argument("--json", action="store_true", help="Output JSON")

    p_signs = sub.add_parser("signs", help="List variable message signs")
    p_signs.add_argument("--roadway", help="Filter by roadway")
    p_signs.add_argument("--json", action="store_true", help="Output JSON")

    p_snap = sub.add_parser("snapshot", help="Download camera snapshot")
    p_snap.add_argument("camera_id", type=int, help="Camera ID")
    p_snap.add_argument("--output", "-o", default=None, help="Output file (default: {id}.jpg)")

    sub.add_parser("demo", help="Run full live demo")

    args = parser.parse_args()
    client = CTDOTClient()

    if args.cmd == "cameras":
        cameras = client.get_cameras(roadway=args.roadway, city=args.city)
        if getattr(args, "json", False):
            out = []
            for c in cameras:
                out.append({
                    "id": c.id,
                    "roadway": c.roadway,
                    "direction": c.direction,
                    "location": c.location,
                    "city": c.city,
                    "latitude": c.latitude,
                    "longitude": c.longitude,
                    "snapshot_url": c.snapshot_url,
                    "source": c.source,
                })
            print(json.dumps(out, indent=2))
        else:
            print(f"{'ID':<6} {'Roadway':<25} {'Direction':<15} Location")
            print("-" * 80)
            for c in cameras:
                print(f"{c.id:<6} {c.roadway:<25} {c.direction:<15} {c.location}")
            print(f"\nTotal: {len(cameras)}")

    elif args.cmd == "events":
        events = client.get_traffic_events(roadway=args.roadway)
        if getattr(args, "json", False):
            out = []
            for e in events:
                out.append({
                    "id": e.id,
                    "type": e.type,
                    "layer": e.layer_name,
                    "roadway": e.roadway_name,
                    "direction": e.direction,
                    "severity": e.severity,
                    "description": e.description,
                    "last_updated": e.last_updated,
                })
            print(json.dumps(out, indent=2))
        else:
            for e in events:
                print(f"[{e.id}] {e.type} | {e.roadway_name} {e.direction} | {e.severity}")
                print(f"  {e.description[:100]}")
            print(f"\nTotal: {len(events)}")

    elif args.cmd == "signs":
        signs = client.get_message_signs(roadway=args.roadway)
        if getattr(args, "json", False):
            out = []
            for s in signs:
                out.append({
                    "id": s.id,
                    "name": s.name,
                    "roadway": s.roadway_name,
                    "direction": s.direction,
                    "message": s.message_text,
                    "status": s.status,
                    "last_updated": s.last_updated,
                })
            print(json.dumps(out, indent=2))
        else:
            for s in signs:
                print(f"[{s.id}] {s.name} ({s.direction})")
                print(f"  {s.message_text.replace(chr(10), ' | ')}")
            print(f"\nTotal: {len(signs)}")

    elif args.cmd == "snapshot":
        cid = args.camera_id
        out_path = args.output or f"{cid}.jpg"
        print(f"Downloading snapshot for camera {cid}...")
        jpeg = client.get_camera_snapshot(cid)
        if jpeg:
            with open(out_path, "wb") as fh:
                fh.write(jpeg)
            print(f"Saved {len(jpeg)} bytes to {out_path}")
        else:
            print("Camera returned empty image (offline or blocked).")

    elif args.cmd == "demo" or args.cmd is None:
        demo()

    else:
        parser.print_help()
