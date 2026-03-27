#!/usr/bin/env python3
"""
gdot_client.py - Georgia Department of Transportation (GDOT) 511GA Traffic API Client

Reverse-engineered from https://511ga.org — the official GDOT traffic information portal.
Uses only Python standard library (urllib, json, dataclasses, http.cookiejar).

Discovered endpoints:
  - /map/mapIcons/{layer}          Lightweight geo-index (all IDs + lat/lng)
  - /List/GetData/{type}           Paginated detail records (DataTables POST)
  - /tooltip/{layer}/{id}          HTML tooltip for a single item
  - /map/Cctv/{cctv_id}            Live JPEG snapshot (camera image)
  - /Camera/GetVideoUrl?imageId=   Signed HLS stream URL (JWT, ~2 min TTL)
  - /Alert/GetUpdatedAlerts        Road-closure / construction alerts JSON
  - /Alert/GetEmergencyAlert       Emergency alert banner JSON
  - tiles.ibi511.com traffic tiles Traffic-speed tile service (XYZ tiles)

Auth model:
  - Session cookie (session-id) obtained automatically on first GET to any page.
  - No login required for public read-only data.
  - Video streams require a short-lived JWT that is issued by /Camera/GetVideoUrl.
    The stream server (sfs-msc-pub-*.navigator.dot.ga.gov) validates the token.

Map layers:
  Cameras, Construction, ConstructionClosures, ElectricVehicleCharger,
  ExpressLanes, IncidentClosures, Incidents, MessageSigns, PortOfEntry,
  RestAreas, SpecialEvents, Waze, WazeHazards, WazeIncidents, WazeReports,
  WazeTraffic, WeatherEvents, WeatherForecast

List types (for /List/GetData/{type}):
  cameras, construction, closures, incidents, messagesigns, specialevents,
  weatherevents, traffic  (traffic = all event types combined)

Usage:
  python gdot_client.py --help
  python gdot_client.py cameras --limit 5
  python gdot_client.py incidents
  python gdot_client.py messagesigns --county Fulton
  python gdot_client.py alerts
  python gdot_client.py camera-image 18549 /tmp/cam.jpg
  python gdot_client.py camera-video-url 18549
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from typing import Any, Iterator, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://511ga.org"
STREAM_MANAGER_BASE = "https://stream-manager.navigator.dot.ga.gov/1.0"
STREAM_MANAGER_API_KEY = "6MIN2CWetWLlyDNXrLBPHtmfifxvfLM7"  # public, in JS bundle

# Map layers available via /map/mapIcons/{layer}
MAP_LAYERS = [
    "Cameras",
    "Construction",
    "ConstructionClosures",
    "ElectricVehicleCharger",
    "ExpressLanes",
    "IncidentClosures",
    "Incidents",
    "MessageSigns",
    "PortOfEntry",
    "RestAreas",
    "SpecialEvents",
    "Waze",
    "WazeHazards",
    "WazeIncidents",
    "WazeReports",
    "WazeTraffic",
    "WeatherEvents",
    "WeatherForecast",
]

# List types available via /List/GetData/{type}
LIST_TYPES = [
    "cameras",
    "construction",
    "closures",
    "incidents",
    "messagesigns",
    "specialevents",
    "weatherevents",
    "traffic",
]

DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CameraImage:
    """A single camera image/stream associated with a camera site."""

    id: int
    camera_site_id: int
    description: str
    image_url: str
    video_url: Optional[str]
    video_type: Optional[str]
    is_video_auth_required: bool
    video_disabled: bool

    @property
    def full_image_url(self) -> str:
        """Absolute URL for the live JPEG snapshot."""
        return f"{BASE_URL}{self.image_url}"

    @classmethod
    def from_dict(cls, d: dict) -> "CameraImage":
        return cls(
            id=d["id"],
            camera_site_id=d.get("cameraSiteId", 0),
            description=d.get("description", ""),
            image_url=d.get("imageUrl", ""),
            video_url=d.get("videoUrl"),
            video_type=d.get("videoType"),
            is_video_auth_required=bool(d.get("isVideoAuthRequired", False)),
            video_disabled=bool(d.get("videoDisabled", False)),
        )


@dataclass
class LatLng:
    """Geographic coordinate pair."""

    lat: float
    lng: float

    @classmethod
    def from_wkt(cls, wkt: str) -> Optional["LatLng"]:
        """Parse from WKT POINT(-lng lat) format used by the API."""
        m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", wkt)
        if m:
            return cls(lat=float(m.group(2)), lng=float(m.group(1)))
        return None

    @classmethod
    def from_raw_latlng(cls, d: Optional[dict]) -> Optional["LatLng"]:
        if not d:
            return None
        geo = d.get("geography", {})
        wkt = geo.get("wellKnownText", "")
        return cls.from_wkt(wkt) if wkt else None


@dataclass
class Camera:
    """A GDOT traffic camera site with one or more image feeds."""

    id: int
    source_id: str
    source: str
    roadway: str
    direction: str
    location: str
    state: str
    county: Optional[str]
    city: Optional[str]
    region: Optional[str]
    lat_lng: Optional[LatLng]
    images: list[CameraImage]
    camera_name: Optional[str]  # SKYLINE camera name (e.g. "BARR-CCTV-0003")

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        images = [CameraImage.from_dict(img) for img in d.get("images", [])]
        lat_lng = LatLng.from_raw_latlng(d.get("latLng"))
        json_data = d.get("jsonData") or {}
        camera_name = json_data.get("name") or json_data.get("Name")
        return cls(
            id=d.get("id", 0) or int(d.get("DT_RowId", 0)),
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            roadway=d.get("roadway") or d.get("roadwayName", ""),
            direction=str(d.get("direction", "")),
            location=d.get("location", ""),
            state=d.get("state", ""),
            county=d.get("county"),
            city=d.get("city"),
            region=d.get("region"),
            lat_lng=lat_lng,
            images=images,
            camera_name=camera_name,
        )

    @property
    def hls_url(self) -> Optional[str]:
        """Primary HLS stream URL (requires auth token to play)."""
        for img in self.images:
            if img.video_url and not img.video_disabled:
                return img.video_url
        return None

    @property
    def snapshot_url(self) -> Optional[str]:
        """Absolute URL of the live JPEG snapshot (no auth required)."""
        for img in self.images:
            return img.full_image_url
        return None


@dataclass
class TrafficEvent:
    """A traffic event: incident, construction, closure, or special event."""

    id: int
    type: str
    layer_name: str
    roadway_name: str
    description: str
    source_id: str
    source: str
    event_sub_type: Optional[str]
    start_date: str
    end_date: Optional[str]
    last_updated: str
    is_full_closure: bool
    severity: Optional[str]
    direction: Optional[str]
    lane_description: Optional[str]
    county: Optional[str]
    region: Optional[str]
    state: str
    cameras: list[Camera]

    @classmethod
    def from_dict(cls, d: dict) -> "TrafficEvent":
        raw_cams = d.get("cameras", [])
        cameras = []
        for c in raw_cams:
            try:
                cameras.append(Camera.from_dict(c))
            except Exception:
                pass
        return cls(
            id=d.get("id", 0) or int(d.get("DT_RowId", 0)),
            type=d.get("type", ""),
            layer_name=d.get("layerName", ""),
            roadway_name=d.get("roadwayName", ""),
            description=d.get("description", ""),
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            event_sub_type=d.get("eventSubType"),
            start_date=d.get("startDate", ""),
            end_date=d.get("endDate"),
            last_updated=d.get("lastUpdated", ""),
            is_full_closure=bool(d.get("isFullClosure", False)),
            severity=d.get("severity"),
            direction=d.get("direction"),
            lane_description=d.get("laneDescription"),
            county=d.get("county"),
            region=d.get("region"),
            state=d.get("state", ""),
            cameras=cameras,
        )


@dataclass
class MessageSign:
    """A Dynamic Message Sign (DMS) with current message text."""

    id: str
    roadway_name: str
    direction: str
    name: str
    area: str
    description: str
    message: str
    message2: str
    message3: str
    status: str
    last_updated: str

    @classmethod
    def from_dict(cls, d: dict) -> "MessageSign":
        return cls(
            id=d.get("DT_RowId", ""),
            roadway_name=d.get("roadwayName", ""),
            direction=d.get("direction", ""),
            name=d.get("name", ""),
            area=d.get("area", ""),
            description=d.get("description", ""),
            message=d.get("message", ""),
            message2=d.get("message2", ""),
            message3=d.get("message3", ""),
            status=d.get("status", ""),
            last_updated=d.get("lastUpdated", ""),
        )

    @property
    def full_message(self) -> str:
        """All message phases joined, HTML stripped."""
        parts = [self.message, self.message2, self.message3]
        joined = " | ".join(p for p in parts if p)
        # Strip HTML tags
        return re.sub(r"<[^>]+>", " ", joined).strip()


@dataclass
class AlertMessage:
    """A single road-condition or construction alert message."""

    message: str
    additional_text: str
    regions: list[str]
    high_importance: bool

    @classmethod
    def from_dict(cls, d: dict) -> "AlertMessage":
        lang1 = d.get("messages", {}).get("messageLang1", {})
        return cls(
            message=lang1.get("message", ""),
            additional_text=lang1.get("additionalText", ""),
            regions=d.get("regions", []),
            high_importance=bool(d.get("highImportance", False)),
        )


@dataclass
class MapIcon:
    """Lightweight map icon record — just ID, lat/lng, and title."""

    item_id: str
    lat: float
    lng: float
    title: str

    @classmethod
    def from_dict(cls, d: dict) -> "MapIcon":
        loc = d.get("location", [0.0, 0.0])
        return cls(
            item_id=d.get("itemId", ""),
            lat=loc[0] if len(loc) > 0 else 0.0,
            lng=loc[1] if len(loc) > 1 else 0.0,
            title=d.get("title", ""),
        )


# ---------------------------------------------------------------------------
# HTTP session helper
# ---------------------------------------------------------------------------


class SessionManager:
    """
    Manages a persistent HTTP session with cookie handling.

    The 511GA server issues session cookies on first contact. Subsequent
    requests must carry those cookies or they get redirected to the home page.
    """

    def __init__(self, base_url: str = BASE_URL, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cookie_jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )
        self._session_initialized = False

    def _init_session(self) -> None:
        """Perform initial GET to obtain session cookies."""
        if self._session_initialized:
            return
        req = urllib.request.Request(
            self.base_url + "/map",
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with self._opener.open(req, timeout=self.timeout):
                pass
        except Exception:
            pass
        self._session_initialized = True

    @staticmethod
    def _decompress(data: bytes, headers: Any) -> bytes:
        """Decompress gzip response body if Content-Encoding indicates it."""
        encoding = ""
        try:
            encoding = headers.get("Content-Encoding", "")
        except Exception:
            pass
        if encoding == "gzip" or (len(data) > 1 and data[:2] == b"\x1f\x8b"):
            try:
                return gzip.decompress(data)
            except Exception:
                pass
        return data

    def get(self, path: str, params: Optional[dict] = None) -> bytes:
        """
        HTTP GET request.

        Args:
            path: Absolute URL or path relative to BASE_URL.
            params: Optional query string parameters.

        Returns:
            Raw (decompressed) response bytes.
        """
        self._init_session()
        url = path if path.startswith("http") else self.base_url + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/html, */*",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with self._opener.open(req, timeout=self.timeout) as resp:
            raw = resp.read()
            return self._decompress(raw, resp.headers)

    def post(
        self,
        path: str,
        data: dict,
        content_type: str = "application/x-www-form-urlencoded",
    ) -> bytes:
        """
        HTTP POST request.

        Args:
            path: Path relative to BASE_URL.
            data: Form data dictionary.
            content_type: Content-Type header.

        Returns:
            Raw response bytes.
        """
        self._init_session()
        url = self.base_url + path
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": content_type,
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with self._opener.open(req, timeout=self.timeout) as resp:
            raw = resp.read()
            return self._decompress(raw, resp.headers)

    def get_json(self, path: str, params: Optional[dict] = None) -> Any:
        """GET and parse JSON response."""
        return json.loads(self.get(path, params))

    def post_json(self, path: str, data: dict) -> Any:
        """POST and parse JSON response."""
        return json.loads(self.post(path, data))


# ---------------------------------------------------------------------------
# Main API client
# ---------------------------------------------------------------------------


class GDOTClient:
    """
    Client for the 511GA (Georgia DOT) traffic information API.

    All methods return typed dataclass instances. Pagination is handled
    automatically by the ``iter_*`` generator methods.

    Example::

        client = GDOTClient()

        # Get all cameras in Fulton County
        for cam in client.iter_cameras():
            if cam.county == "Fulton":
                print(cam.location, cam.snapshot_url)

        # List active incidents
        for event in client.iter_traffic_events(event_type="incidents"):
            print(event.description)

        # Download a camera snapshot
        img_bytes = client.get_camera_snapshot(18549)
        with open("cam.jpg", "wb") as f:
            f.write(img_bytes)

        # Get signed HLS stream URL (valid ~2 minutes)
        url = client.get_camera_video_url(18549)
        print(url)  # Use with ffplay, VLC, etc.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the GDOT API client.

        Args:
            timeout: HTTP request timeout in seconds. Default 20.
        """
        self._session = SessionManager(BASE_URL, timeout=timeout)

    # ------------------------------------------------------------------
    # Camera methods
    # ------------------------------------------------------------------

    def get_camera_map_icons(self) -> list[MapIcon]:
        """
        Return lightweight geo-index of all cameras (ID + lat/lng only).

        This is the fastest way to get a complete list of camera locations.
        Returns 3865+ items as of 2026-03.

        Returns:
            List of MapIcon objects with item_id, lat, lng.
        """
        data = self._session.get_json("/map/mapIcons/Cameras")
        return [MapIcon.from_dict(item) for item in data.get("item2", [])]

    def get_cameras(
        self, start: int = 0, length: int = DEFAULT_PAGE_SIZE
    ) -> tuple[int, list[Camera]]:
        """
        Fetch one page of cameras with full detail records.

        Args:
            start: Zero-based record offset for pagination.
            length: Number of records per page (max ~100 reliably).

        Returns:
            Tuple of (total_records, cameras_this_page).
        """
        raw = self._session.post_json(
            "/List/GetData/cameras",
            {
                "draw": 1,
                "start": start,
                "length": length,
                "order[0][column]": 0,
                "order[0][dir]": "asc",
            },
        )
        total = raw.get("recordsTotal", 0)
        cameras = [Camera.from_dict(d) for d in raw.get("data", [])]
        return total, cameras

    def iter_cameras(
        self, page_size: int = DEFAULT_PAGE_SIZE
    ) -> Iterator[Camera]:
        """
        Yield all cameras, automatically paginating.

        Args:
            page_size: Records per HTTP request. Default 100.

        Yields:
            Camera objects one at a time.
        """
        start = 0
        while True:
            total, cameras = self.get_cameras(start=start, length=page_size)
            if not cameras:
                break
            yield from cameras
            start += len(cameras)
            if start >= total:
                break

    def get_camera_snapshot(self, cctv_image_id: int) -> bytes:
        """
        Download the current live JPEG snapshot for a camera.

        The image is refreshed on the server approximately every 60 seconds.
        No authentication is required.

        Args:
            cctv_image_id: The numeric CCTV image ID (e.g. 18549).
                           Found in Camera.images[n].id.

        Returns:
            Raw JPEG bytes.
        """
        return self._session.get(f"/map/Cctv/{cctv_image_id}")

    def get_camera_video_url(self, cctv_image_id: int) -> str:
        """
        Obtain a signed HLS stream URL for a camera.

        The URL contains a JWT token valid for approximately 2 minutes.
        Use with a player that supports HLS (ffplay, VLC, mpv, etc.).

        Args:
            cctv_image_id: The numeric CCTV image ID (e.g. 18549).
                           Found in Camera.images[n].id.

        Returns:
            HTTPS HLS playlist URL with embedded JWT token.
        """
        raw = self._session.get(f"/Camera/GetVideoUrl?imageId={cctv_image_id}")
        url = raw.decode("utf-8").strip().strip('"')
        return url

    # ------------------------------------------------------------------
    # Traffic event methods
    # ------------------------------------------------------------------

    def get_traffic_events(
        self,
        event_type: str = "traffic",
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[int, list[TrafficEvent]]:
        """
        Fetch one page of traffic events.

        Args:
            event_type: One of the LIST_TYPES values. Use "traffic" for all
                        combined types, or a specific type like "incidents",
                        "construction", "specialevents", "messagesigns".
            start: Zero-based offset for pagination.
            length: Records per page.

        Returns:
            Tuple of (total_records, events_this_page).
        """
        raw = self._session.post_json(
            f"/List/GetData/{event_type}",
            {
                "draw": 1,
                "start": start,
                "length": length,
                "order[0][column]": 0,
                "order[0][dir]": "asc",
            },
        )
        total = raw.get("recordsTotal", 0)
        events = [TrafficEvent.from_dict(d) for d in raw.get("data", [])]
        return total, events

    def iter_traffic_events(
        self,
        event_type: str = "traffic",
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Iterator[TrafficEvent]:
        """
        Yield all traffic events, automatically paginating.

        Args:
            event_type: See get_traffic_events() for valid types.
            page_size: Records per HTTP request.

        Yields:
            TrafficEvent objects one at a time.
        """
        start = 0
        while True:
            total, events = self.get_traffic_events(
                event_type=event_type, start=start, length=page_size
            )
            if not events:
                break
            yield from events
            start += len(events)
            if start >= total:
                break

    # ------------------------------------------------------------------
    # Message Signs
    # ------------------------------------------------------------------

    def get_message_signs(
        self, start: int = 0, length: int = DEFAULT_PAGE_SIZE
    ) -> tuple[int, list[MessageSign]]:
        """
        Fetch one page of Dynamic Message Sign (DMS) records.

        Args:
            start: Zero-based offset.
            length: Records per page.

        Returns:
            Tuple of (total_records, signs_this_page).
        """
        raw = self._session.post_json(
            "/List/GetData/messagesigns",
            {
                "draw": 1,
                "start": start,
                "length": length,
                "order[0][column]": 0,
                "order[0][dir]": "asc",
            },
        )
        total = raw.get("recordsTotal", 0)
        signs = [MessageSign.from_dict(d) for d in raw.get("data", [])]
        return total, signs

    def iter_message_signs(
        self, page_size: int = DEFAULT_PAGE_SIZE
    ) -> Iterator[MessageSign]:
        """
        Yield all message signs, automatically paginating.

        Args:
            page_size: Records per HTTP request.

        Yields:
            MessageSign objects one at a time.
        """
        start = 0
        while True:
            total, signs = self.get_message_signs(start=start, length=page_size)
            if not signs:
                break
            yield from signs
            start += len(signs)
            if start >= total:
                break

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def get_alerts(self) -> list[AlertMessage]:
        """
        Fetch current road-condition and construction advisory alerts.

        These are the banner alerts shown at the top of the 511GA website.
        Typically includes lane closures, construction windows, and major events.

        Returns:
            List of AlertMessage objects, most recent first.
        """
        raw = self._session.get_json("/Alert/GetUpdatedAlerts?lang=en")
        return [AlertMessage.from_dict(a) for a in raw.get("alerts", [])]

    def get_emergency_alert(self) -> Optional[str]:
        """
        Fetch the emergency alert banner content, if active.

        Returns:
            HTML string with emergency alert content, or None if no active alert.
        """
        raw = self._session.get_json("/Alert/GetEmergencyAlert?lang=en")
        content = raw.get("content", "")
        return content if content else None

    # ------------------------------------------------------------------
    # Map icon geo-index methods (all layers)
    # ------------------------------------------------------------------

    def get_map_icons(self, layer: str) -> list[MapIcon]:
        """
        Return lightweight geo-index for any map layer.

        The map icon index contains only IDs and coordinates — use
        get_tooltip() for full details on individual items.

        Args:
            layer: One of the MAP_LAYERS strings (case-sensitive).

        Returns:
            List of MapIcon objects.

        Example::
            signs = client.get_map_icons("MessageSigns")
            incidents = client.get_map_icons("Incidents")
        """
        data = self._session.get_json(f"/map/mapIcons/{layer}")
        return [MapIcon.from_dict(item) for item in data.get("item2", [])]

    def get_tooltip(self, layer: str, item_id: str) -> str:
        """
        Fetch HTML tooltip detail for a single map item.

        Args:
            layer: Layer name, e.g. "Cameras", "Incidents", "MessageSigns".
            item_id: The itemId from MapIcon.item_id.

        Returns:
            Raw HTML string with formatted tooltip content.
        """
        raw = self._session.get(f"/tooltip/{layer}/{item_id}?lang=en")
        return raw.decode("utf-8")

    # ------------------------------------------------------------------
    # Traffic tile URL builder
    # ------------------------------------------------------------------

    @staticmethod
    def traffic_tile_url(x: int, y: int, z: int) -> str:
        """
        Build a URL for a traffic-speed map tile.

        Tile server: tiles.ibi511.com (third-party provider for GDOT).
        Tiles use XYZ (slippy map) coordinate scheme, Web Mercator projection.

        Args:
            x: Tile X coordinate.
            y: Tile Y coordinate.
            z: Zoom level.

        Returns:
            HTTPS URL for the PNG traffic tile.
        """
        return (
            f"https://tiles.ibi511.com/Geoservice/GetTrafficTile"
            f"?x={x}&y={y}&z={z}"
        )

    # ------------------------------------------------------------------
    # Convenience / search helpers
    # ------------------------------------------------------------------

    def search_cameras(
        self,
        roadway: Optional[str] = None,
        county: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> list[Camera]:
        """
        Search cameras by roadway, county, and/or direction.

        This fetches all cameras (multiple requests) and filters client-side.
        For large result sets, use iter_cameras() directly.

        Args:
            roadway: Partial roadway name match (case-insensitive), e.g. "I-285".
            county: County name match (case-insensitive), e.g. "Fulton".
            direction: Direction string, e.g. "Northbound", "N".

        Returns:
            List of matching Camera objects.
        """
        results = []
        for cam in self.iter_cameras():
            if roadway and roadway.lower() not in cam.roadway.lower():
                continue
            if county and cam.county and county.lower() not in cam.county.lower():
                continue
            if county and not cam.county:
                continue
            if direction and direction.lower() not in cam.direction.lower():
                continue
            results.append(cam)
        return results

    def search_events(
        self,
        event_type: str = "traffic",
        county: Optional[str] = None,
        roadway: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[TrafficEvent]:
        """
        Search traffic events by county, roadway, and/or severity.

        Args:
            event_type: Type to query. See LIST_TYPES.
            county: County name, case-insensitive partial match.
            roadway: Roadway name, case-insensitive partial match.
            severity: "minor", "major", or "critical".

        Returns:
            List of matching TrafficEvent objects.
        """
        results = []
        for ev in self.iter_traffic_events(event_type=event_type):
            if county and (not ev.county or county.lower() not in ev.county.lower()):
                continue
            if roadway and roadway.lower() not in ev.roadway_name.lower():
                continue
            if severity and (not ev.severity or severity.lower() != ev.severity.lower()):
                continue
            results.append(ev)
        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_json(obj: Any) -> None:
    """Print an object as formatted JSON."""
    def default(o: Any) -> Any:
        if hasattr(o, "__dict__"):
            return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    print(json.dumps(obj, indent=2, default=default))


def cmd_cameras(client: GDOTClient, args: argparse.Namespace) -> None:
    """List cameras."""
    print(f"Fetching cameras (limit={args.limit})...", file=sys.stderr)
    cameras: list[Camera] = []
    for cam in client.iter_cameras():
        if args.county and (not cam.county or args.county.lower() not in cam.county.lower()):
            continue
        if args.roadway and args.roadway.lower() not in cam.roadway.lower():
            continue
        cameras.append(cam)
        if len(cameras) >= args.limit:
            break

    print(f"Showing {len(cameras)} cameras:", file=sys.stderr)
    for cam in cameras:
        print(f"  [{cam.id}] {cam.location}")
        print(f"       Road: {cam.roadway} {cam.direction}")
        if cam.county:
            print(f"       County: {cam.county}")
        if cam.snapshot_url:
            print(f"       Snapshot: {cam.snapshot_url}")
        if cam.hls_url:
            print(f"       HLS: {cam.hls_url}")
        if cam.camera_name:
            print(f"       Camera name: {cam.camera_name}")


def cmd_incidents(client: GDOTClient, args: argparse.Namespace) -> None:
    """List traffic incidents."""
    print(f"Fetching incidents...", file=sys.stderr)
    events: list[TrafficEvent] = []
    for ev in client.iter_traffic_events(event_type="incidents"):
        if args.county and (not ev.county or args.county.lower() not in ev.county.lower()):
            continue
        events.append(ev)
        if len(events) >= args.limit:
            break

    print(f"Active incidents ({len(events)} shown):", file=sys.stderr)
    for ev in events:
        print(f"\n  [{ev.id}] {ev.type} on {ev.roadway_name}")
        print(f"   {ev.description}")
        print(f"   Severity: {ev.severity or 'N/A'}")
        print(f"   Started: {ev.start_date}")
        if ev.lane_description:
            print(f"   Lanes: {ev.lane_description}")
        if ev.county:
            print(f"   County: {ev.county}")


def cmd_construction(client: GDOTClient, args: argparse.Namespace) -> None:
    """List construction events."""
    print("Fetching construction events...", file=sys.stderr)
    events: list[TrafficEvent] = []
    for ev in client.iter_traffic_events(event_type="construction"):
        if args.county and (not ev.county or args.county.lower() not in ev.county.lower()):
            continue
        events.append(ev)
        if len(events) >= args.limit:
            break

    print(f"Construction events ({len(events)} shown):", file=sys.stderr)
    for ev in events:
        print(f"\n  [{ev.id}] {ev.roadway_name}")
        print(f"   {ev.description}")
        print(f"   Severity: {ev.severity or 'N/A'}")
        print(f"   {ev.start_date} -> {ev.end_date or 'TBD'}")
        if ev.county:
            print(f"   County: {ev.county}")


def cmd_messagesigns(client: GDOTClient, args: argparse.Namespace) -> None:
    """List Dynamic Message Signs."""
    print("Fetching message signs...", file=sys.stderr)
    signs: list[MessageSign] = []
    for sign in client.iter_message_signs():
        if args.roadway and args.roadway.lower() not in sign.roadway_name.lower():
            continue
        signs.append(sign)
        if len(signs) >= args.limit:
            break

    print(f"Message signs ({len(signs)} shown):", file=sys.stderr)
    for sign in signs:
        msg = sign.full_message
        if msg:
            print(f"\n  [{sign.id}] {sign.description}")
            print(f"   Road: {sign.roadway_name} {sign.direction}")
            print(f"   Message: {msg}")
            print(f"   Updated: {sign.last_updated}")


def cmd_alerts(client: GDOTClient, args: argparse.Namespace) -> None:
    """List current road alerts."""
    print("Fetching alerts...", file=sys.stderr)
    alerts = client.get_alerts()
    emergency = client.get_emergency_alert()

    if emergency:
        print(f"\n=== EMERGENCY ALERT ===")
        print(re.sub(r"<[^>]+>", "", emergency).strip())

    print(f"\n{len(alerts)} road alert(s):")
    for i, alert in enumerate(alerts, 1):
        print(f"\n  [{i}] {alert.message}")
        if args.verbose:
            text = re.sub(r"<[^>]+>", " ", alert.additional_text).strip()
            text = re.sub(r"\s+", " ", text)
            print(f"   Detail: {text[:500]}")
        print(f"   Priority: {'HIGH' if alert.high_importance else 'Normal'}")


def cmd_camera_image(client: GDOTClient, args: argparse.Namespace) -> None:
    """Download a camera snapshot image."""
    cctv_id = int(args.cctv_id)
    output_path = args.output
    print(f"Downloading camera snapshot {cctv_id}...", file=sys.stderr)
    data = client.get_camera_snapshot(cctv_id)
    with open(output_path, "wb") as f:
        f.write(data)
    print(f"Saved {len(data):,} bytes to {output_path}")


def cmd_camera_video_url(client: GDOTClient, args: argparse.Namespace) -> None:
    """Get a signed HLS stream URL."""
    cctv_id = int(args.cctv_id)
    print(f"Getting video URL for CCTV image {cctv_id}...", file=sys.stderr)
    url = client.get_camera_video_url(cctv_id)
    print(url)


def cmd_map_icons(client: GDOTClient, args: argparse.Namespace) -> None:
    """Get map icon geo-index for a layer."""
    layer = args.layer
    print(f"Fetching map icons for layer: {layer}", file=sys.stderr)
    icons = client.get_map_icons(layer)
    print(f"  {len(icons)} items:")
    for icon in icons[: args.limit]:
        print(f"  [{icon.item_id}] lat={icon.lat:.5f} lng={icon.lng:.5f} {icon.title}")


def cmd_demo(client: GDOTClient, args: argparse.Namespace) -> None:
    """Run a comprehensive demo of the API."""
    print("=" * 60)
    print("511GA GDOT API Demo")
    print("=" * 60)

    # Cameras
    print("\n--- Camera Map Icons (lightweight index) ---")
    icons = client.get_camera_map_icons()
    print(f"Total cameras in Georgia: {len(icons)}")
    print(f"Sample: {icons[0].item_id} @ ({icons[0].lat:.4f}, {icons[0].lng:.4f})")

    # Camera details (page 1)
    print("\n--- Camera Details (first 3) ---")
    _, cameras = client.get_cameras(start=0, length=3)
    for cam in cameras:
        print(f"  {cam.location}")
        print(f"    Road: {cam.roadway} {cam.direction}")
        print(f"    Snapshot: {cam.snapshot_url}")
        if cam.camera_name:
            print(f"    Camera Name: {cam.camera_name}")
        if cam.hls_url:
            print(f"    HLS (auth req'd): {cam.hls_url[:60]}...")

    # Message signs
    print("\n--- Message Signs (first 5 with content) ---")
    count = 0
    for sign in client.iter_message_signs():
        msg = sign.full_message
        if msg and count < 5:
            print(f"  {sign.description}")
            print(f"    [{sign.roadway_name} {sign.direction}] {msg}")
            count += 1
    if count == 0:
        print("  (no active messages)")

    # Incidents
    print("\n--- Active Incidents ---")
    _, incidents = client.get_traffic_events(event_type="incidents", length=5)
    if incidents:
        for ev in incidents[:5]:
            print(f"  {ev.type}: {ev.roadway_name}")
            print(f"    {ev.description[:100]}")
    else:
        print("  (no active incidents)")

    # Alerts
    print("\n--- Road Alerts ---")
    alerts = client.get_alerts()
    print(f"  {len(alerts)} active alert(s)")
    for alert in alerts[:2]:
        print(f"  - {alert.message}")

    # Traffic tile URL
    print("\n--- Traffic Speed Tile URL (example) ---")
    tile_url = GDOTClient.traffic_tile_url(x=1188, y=1583, z=12)
    print(f"  {tile_url}")

    print("\n--- Available Map Layers ---")
    for layer in MAP_LAYERS:
        print(f"  {layer}")

    print("\nDemo complete.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="511GA GDOT Traffic API Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # cameras
    p_cameras = subparsers.add_parser("cameras", help="List traffic cameras")
    p_cameras.add_argument("--limit", type=int, default=20, help="Max results")
    p_cameras.add_argument("--county", help="Filter by county name")
    p_cameras.add_argument("--roadway", help="Filter by roadway (e.g. I-285)")
    p_cameras.set_defaults(func=cmd_cameras)

    # incidents
    p_inc = subparsers.add_parser("incidents", help="List active incidents")
    p_inc.add_argument("--limit", type=int, default=20)
    p_inc.add_argument("--county", help="Filter by county")
    p_inc.set_defaults(func=cmd_incidents)

    # construction
    p_con = subparsers.add_parser("construction", help="List construction events")
    p_con.add_argument("--limit", type=int, default=20)
    p_con.add_argument("--county", help="Filter by county")
    p_con.set_defaults(func=cmd_construction)

    # messagesigns
    p_dms = subparsers.add_parser("messagesigns", help="List Dynamic Message Signs")
    p_dms.add_argument("--limit", type=int, default=20)
    p_dms.add_argument("--roadway", help="Filter by roadway")
    p_dms.set_defaults(func=cmd_messagesigns)

    # alerts
    p_alert = subparsers.add_parser("alerts", help="List current road alerts")
    p_alert.add_argument("--verbose", "-v", action="store_true")
    p_alert.set_defaults(func=cmd_alerts)

    # camera-image
    p_img = subparsers.add_parser("camera-image", help="Download camera snapshot")
    p_img.add_argument("cctv_id", help="CCTV image ID (from Camera.images[n].id)")
    p_img.add_argument("output", help="Output file path (.jpg)")
    p_img.set_defaults(func=cmd_camera_image)

    # camera-video-url
    p_vid = subparsers.add_parser("camera-video-url", help="Get signed HLS URL")
    p_vid.add_argument("cctv_id", help="CCTV image ID")
    p_vid.set_defaults(func=cmd_camera_video_url)

    # map-icons
    p_map = subparsers.add_parser("map-icons", help="Get map icon geo-index")
    p_map.add_argument(
        "layer",
        choices=MAP_LAYERS,
        help="Layer name",
    )
    p_map.add_argument("--limit", type=int, default=20)
    p_map.set_defaults(func=cmd_map_icons)

    # demo
    p_demo = subparsers.add_parser("demo", help="Run full API demo")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    client = GDOTClient(timeout=args.timeout)
    try:
        args.func(client, args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
