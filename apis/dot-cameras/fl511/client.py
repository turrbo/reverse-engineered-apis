#!/usr/bin/env python3
"""
FL511 Florida Traffic Camera & Events Client
=============================================
Reverse-engineered Python client for the Florida Department of Transportation (FDOT)
FL511 real-time traffic information system.

No API key required. Operates entirely on public endpoints.

Platform: IBI Group ASP.NET MVC (same framework as 511wi.gov, 511ny.org, etc.)
Backend CCTV system: DIVAS (Digital Integrated Video Archiving System) by TransCore

Reverse-engineered from live production site at https://fl511.com
Last verified: 2026-03-27

Key endpoints discovered:
  GET  /map/mapIcons/Cameras           -> 4,700+ camera locations (map icon data)
  GET  /map/data/Cameras/{id}          -> full camera detail including video URL
  GET  /map/Cctv/{imageId}             -> live JPEG snapshot (no auth required)
  POST /list/GetData/{layer}           -> paginated event list (DataTables format)
  GET  /map/data/{layer}/{id}          -> full event/POI detail
  GET  /map/mapIcons/{layer}           -> all map icons for a layer
  GET  /tooltip/{layer}/{id}           -> HTML tooltip for any map object

Video streaming:
  HLS streams at https://dis-se{N}.divas.cloud:8200/chan-{sourceId}_h/index.m3u8
  require authentication (HTTP 401 without valid session from DIVAS portal).
  Static JPEG snapshots via /map/Cctv/{id} are freely accessible.

Traffic speed tiles (Bing-style XYZ tiles):
  GET https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}

ArcGIS open data (FDOT public feature services):
  https://services1.arcgis.com/O1JpcwDW8sjYuddV/ArcGIS/rest/services/

Usage::

    from fl511_client import FL511Client

    client = FL511Client()

    # Get all cameras in Florida (4,700+)
    cameras = client.get_all_cameras()
    print(len(cameras), "cameras")

    # Filter by county area
    miami_cams = client.get_cameras_by_area("MDC")   # Miami-Dade

    # Get live incidents
    incidents = client.get_events("Incidents")
    for inc in incidents:
        print(inc.roadway, inc.severity, inc.description[:60])

    # Get traffic congestion points
    congestion = client.get_events("Congestion")

    # Get drawbridge status
    bridges = client.get_events("Bridge")
    for b in bridges:
        print(b.name, b.status)

    # Get truck parking availability
    parking = client.get_events("Parking")

    # Get dynamic message signs
    signs = client.get_events("MessageSigns")
    for s in signs:
        print(s.name, s.message)

CLI::

    python fl511_client.py --cameras
    python fl511_client.py --cameras --area MDC
    python fl511_client.py --events Incidents
    python fl511_client.py --events Construction
    python fl511_client.py --events MessageSigns
    python fl511_client.py --events Parking
    python fl511_client.py --events Bridge
    python fl511_client.py --camera-detail 1
    python fl511_client.py --snapshot 1 --output cam1.jpg
    python fl511_client.py --list-areas
    python fl511_client.py --json --cameras
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://fl511.com"
DEFAULT_TIMEOUT = 30

# FDOT DIVAS system districts mapped to their IBI area codes.
# These area codes are used as the areaId parameter when filtering cameras.
# Source: reverse-engineered by sampling /map/data/Cameras/{id} for each camera.
AREAS: Dict[str, str] = {
    "ALA": "Alachua County (District 2)",
    "BC": "Broward County (BCTD / District 4)",
    "BRE": "Brevard County (District 5)",
    "CIT": "Citrus County (Turnpike SG C)",
    "CLA": "Clay County (Turnpike SG C / District 2)",
    "COLL": "Collier County (District 1)",
    "COLU": "Columbia County (District 2)",
    "DUV": "Duval County / Jacksonville (District 2)",
    "ESC": "Escambia County (District 3)",
    "FLA": "Flagler County (District 5)",
    "GAD": "Gadsden County (District 3)",
    "HAM": "Hamilton County (District 2)",
    "HIL": "Hillsborough County / Tampa (District 7)",
    "HLS": "Hillsborough / HART District 6",
    "IR": "Indian River County (Turnpike SG C)",
    "JAC": "Jackson County (District 3)",
    "JEF": "Jefferson County (District 3)",
    "LEE": "Lee County (District 1)",
    "LEO": "Leon County (District 3)",
    "MAD": "Madison County (District 2)",
    "MAN": "Manatee County (District 7)",
    "MAR": "Martin County (Turnpike SG C)",
    "MARI": "Marion County (District 5)",
    "MC": "Monroe County / Florida Keys (District 6)",
    "MDC": "Miami-Dade County (District 6)",
    "NAS": "Nassau County (District 2)",
    "OKA": "Okaloosa County (District 3)",
    "ORA": "Orange County / CFX (District 5 / CFX)",
    "OSC": "Osceola County (District 5)",
    "PAS": "Pasco County (District 7)",
    "PBC": "Palm Beach County (District 4)",
    "PALM": "Palm Beach County alt (District 4)",
    "PIN": "Pinellas County (District 7)",
    "POL": "Polk County (District 1)",
    "SAR": "Sarasota County (District 1)",
    "SEM": "Seminole County (Turnpike SG C)",
    "SJO": "St. Johns County (District 2)",
    "SUM": "Sumter County (Turnpike SG C)",
    "SUW": "Suwannee County (District 2)",
    "VOL": "Volusia County (District 5)",
    "WAL": "Walton County (District 3)",
    "WAS": "Washington County (District 3)",
}

# Available event layers with human-readable names
EVENT_LAYERS: Dict[str, str] = {
    "Incidents": "Traffic Incidents & Accidents",
    "Construction": "Construction Zones",
    "Closures": "Road Closures",
    "SpecialEvents": "Special Events",
    "Congestion": "Traffic Congestion / Queues",
    "DisabledVehicles": "Disabled / Stalled Vehicles",
    "RoadConditionIncident": "Road Condition Incidents",
    "MessageSigns": "Dynamic Message Signs (DMS)",
    "Bridge": "Drawbridge Status",
    "Parking": "Truck Parking Availability",
    "RailCrossing": "Railroad Crossings",
    "WeatherEvents": "Weather Alerts",
    "WeatherForecast": "Weather Forecast Zones",
    "WeatherIncidents": "Weather Incidents",
    "HeliosWeatherAlerts": "Helios Weather Alerts",
}

# FDOT Districts
DISTRICTS: Dict[str, str] = {
    "FL-D01": "District 1 (Southwest FL: Sarasota, Charlotte, Lee, Collier, Hendry, Glades, DeSoto, Hardee, Highlands, Polk)",
    "FL-D02": "District 2 (Northeast FL: Alachua, Baker, Bradford, Columbia, Dixie, Duval, Flagler, Gilchrist, Hamilton, Lafayette, Levy, Madison, Nassau, Putnam, St. Johns, Suwannee, Taylor, Union, Volusia)",
    "FL-D03": "District 3 (Northwest FL / Panhandle: Bay, Calhoun, Escambia, Franklin, Gadsden, Gulf, Holmes, Jackson, Jefferson, Leon, Liberty, Okaloosa, Santa Rosa, Wakulla, Walton, Washington)",
    "FL-D04": "District 4 (Southeast FL: Broward, Indian River, Martin, Okeechobee, Palm Beach, St. Lucie)",
    "FL-D05": "District 5 (Central FL: Brevard, Citrus, Flagler, Hernando, Lake, Marion, Orange, Osceola, Seminole, Sumter, Volusia)",
    "FL-D06": "District 6 (Southeast Extreme: Miami-Dade, Monroe)",
    "FL-D07": "District 7 (Tampa Bay: Hillsborough, Manatee, Pasco, Pinellas, Sarasota)",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CameraImage:
    """A single camera view record as returned by /map/data/Cameras/{id}."""

    image_id: int
    """Database ID used in /map/Cctv/{image_id} snapshot URL."""

    camera_site_id: int
    """Camera site ID (same as the parent camera's id)."""

    description: str
    """Source system identifier / internal name."""

    image_url: str
    """Relative path for live JPEG snapshot. Append to BASE_URL."""

    video_url: str
    """Full HLS .m3u8 stream URL. Requires DIVAS auth (returns 401 if direct)."""

    video_type: str
    """MIME type, e.g. 'application/x-mpegURL'."""

    video_disabled: bool
    """True if the video stream is administratively disabled."""

    blocked: bool
    """True if the camera feed is blocked."""

    @property
    def snapshot_url(self) -> str:
        """Absolute URL for the live JPEG snapshot image. No auth required."""
        return f"{BASE_URL}{self.image_url}"

    @property
    def has_video(self) -> bool:
        """True if a non-empty video URL is present and not disabled."""
        return bool(self.video_url) and not self.video_disabled


@dataclass
class Camera:
    """
    A FL511 traffic camera.

    Camera data is sourced from the DIVAS (Digital Integrated Video Archiving
    System) platform operated by TransCore on behalf of FDOT districts and
    partner agencies.

    The /map/mapIcons/Cameras endpoint returns ~4,700 cameras with location
    data only. Detailed records (including image/video URLs) come from
    /map/data/Cameras/{id}.
    """

    camera_id: int
    """Unique numeric camera site ID."""

    source_id: str
    """Internal DIVAS channel ID. Embedded in HLS stream URL."""

    source: str
    """Source system label, e.g. 'DIVAS-District 1', 'DIVAS-CFX'."""

    area_id: str
    """County/area code, e.g. 'MDC' for Miami-Dade. See AREAS dict."""

    roadway: str
    """Highway or road name, e.g. 'I-95', 'SR-836'."""

    direction: int
    """Direction code: 1=N, 2=E, 3=S, 4=W, 0=unknown."""

    location: str
    """Human-readable location description."""

    latitude: float
    """Decimal degrees latitude (WGS-84)."""

    longitude: float
    """Decimal degrees longitude (WGS-84)."""

    images: List[CameraImage] = field(default_factory=list)
    """One image record per camera view (usually one, occasionally multiple)."""

    video_enabled: Optional[bool] = None
    """From map icon expando: True if camera has a live video stream."""

    @property
    def direction_name(self) -> str:
        """Human-readable cardinal direction."""
        return {1: "Northbound", 2: "Eastbound", 3: "Southbound", 4: "Westbound"}.get(
            self.direction, "Unknown"
        )

    @property
    def primary_image(self) -> Optional[CameraImage]:
        """The first (primary) camera image record."""
        return self.images[0] if self.images else None

    @property
    def snapshot_url(self) -> Optional[str]:
        """Direct URL to the live JPEG snapshot. No auth required."""
        img = self.primary_image
        return img.snapshot_url if img else None

    @property
    def stream_url(self) -> Optional[str]:
        """HLS .m3u8 stream URL. Note: DIVAS requires portal session auth."""
        img = self.primary_image
        return img.video_url if img and img.has_video else None

    @property
    def has_video(self) -> bool:
        """True if any image record has a non-empty, non-disabled video URL."""
        return any(img.has_video for img in self.images)

    @property
    def area_name(self) -> str:
        """Expanded area description from the AREAS lookup table."""
        return AREAS.get(self.area_id, self.area_id)

    def distance_to(self, lat: float, lon: float) -> float:
        """Haversine distance in miles to a given lat/lon."""
        r = 3958.8  # Earth radius in miles
        phi1, phi2 = math.radians(self.latitude), math.radians(lat)
        dphi = math.radians(lat - self.latitude)
        dlam = math.radians(lon - self.longitude)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass
class TrafficEvent:
    """
    A traffic event from the FL511 event system.

    Covers: Incidents, Construction, Closures, SpecialEvents, Congestion,
    DisabledVehicles, RoadConditionIncident.
    """

    event_id: int
    """Unique event ID."""

    layer: str
    """Layer name: 'Incidents', 'Construction', 'Closures', etc."""

    event_type: str
    """ATIS event type, e.g. 'accidentsAndIncidents', 'roadwork'."""

    event_subtype: str
    """Sub-type, e.g. 'ScheduledRoadWork', 'DisabledVehicle'."""

    roadway: str
    """Road name, e.g. 'I-95'."""

    direction: str
    """Direction text, e.g. 'Northbound', 'Both Directions'."""

    description: str
    """Full human-readable description including lane status."""

    comment: str
    """Operational comment from managing agency."""

    severity: str
    """Severity: 'Minor', 'Moderate', 'Major', 'Severe'."""

    is_full_closure: bool
    """True if roadway is fully closed."""

    latitude: float
    """Decimal degrees latitude."""

    longitude: float
    """Decimal degrees longitude."""

    area_id: str
    """County/area code."""

    dot_district: str
    """FDOT district label, e.g. 'District 1'."""

    region: str
    """Region label, e.g. 'Southwest', 'Southeast', 'Central', 'Northeast',
    'Panhandle', 'Tampa Bay'."""

    county: str
    """County name."""

    start_date: str
    """ISO 8601 start date-time string."""

    last_updated: str
    """ISO 8601 last-updated date-time string."""

    end_date: Optional[str] = None
    """ISO 8601 end date-time or None if open-ended."""

    lane_description: str = ""
    """Lane impact summary, e.g. '2 Lanes Closed'."""

    detour_description: str = ""
    """Structured detour instructions (JSON string or empty)."""

    source: str = ""
    """Source system, e.g. 'ERS'."""

    camera_ids: str = ""
    """Comma-separated camera site IDs near this event."""


@dataclass
class MessageSign:
    """A Dynamic Message Sign (DMS / VMS) from the FDOT highway network."""

    sign_id: int
    """Unique sign ID."""

    source_id: str
    """Source system identifier, e.g. 'BCTD-156'."""

    name: str
    """Sign location name."""

    roadway: str
    """Road name."""

    direction: str
    """Direction code, e.g. 'e', 'w', 'n', 's'."""

    area_id: str
    """County/area code."""

    county: str
    """County name."""

    region: str
    """Region name."""

    status: str
    """Sign operational status: 'on' or 'off'."""

    message: str
    """Current displayed message text (may contain NTCIP markup codes)."""

    message_line2: str
    """Second phase / page of the sign message."""

    message_line3: str
    """Third phase / page of the sign message."""

    latitude: float
    """Decimal degrees latitude."""

    longitude: float
    """Decimal degrees longitude."""

    last_updated: str
    """ISO 8601 last-communication timestamp."""

    @property
    def display_message(self) -> str:
        """
        Clean multi-line display message.

        Strips NTCIP bracket markup codes (e.g. ``[pt30o0]``, ``[jp3]``) and
        HTML ``<br/>`` tags, collapses whitespace, and joins sign phases with
        a pipe separator.
        """
        import re
        raw = " / ".join(filter(None, [self.message, self.message_line2, self.message_line3]))
        # Strip HTML line breaks
        raw = re.sub(r'<br\s*/?>', ' ', raw, flags=re.IGNORECASE)
        # Remove NTCIP phase/page codes: [ptXXoX], [jpX], [jlX], [fnt], etc.
        raw = re.sub(r'\[nl\]', ' ', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\[np\]', ' | ', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\[[^\]]*\]', '', raw)
        return ' '.join(raw.split()).strip()


@dataclass
class Bridge:
    """A drawbridge status record."""

    bridge_id: int
    """Unique bridge ID."""

    name: str
    """Bridge name."""

    roadway: str
    """Road crossing the bridge."""

    location: str
    """Waterway or cross-street."""

    county: str
    """County name."""

    status: str
    """Current status: 'Bridge Up' (open to marine traffic) or 'Bridge Down'."""

    direction: str
    """Direction code."""

    network: str
    """Managing agency network name."""

    last_updated: str
    """ISO 8601 last-updated timestamp."""

    last_notification_time: str
    """Unix timestamp (string) of last status notification."""

    @property
    def is_open_to_boats(self) -> bool:
        """True if the bridge is currently raised for marine traffic."""
        return "up" in self.status.lower()


@dataclass
class ParkingFacility:
    """Truck parking availability at a FDOT-monitored facility."""

    facility_id: int
    """Unique facility ID."""

    name: str
    """Facility name."""

    roadway: str
    """Roadway name."""

    direction: str
    """Roadway direction."""

    total_spaces: int
    """Total monitored parking spaces."""

    available_spaces: int
    """Currently available spaces."""

    last_updated: str
    """ISO 8601 last-updated timestamp."""

    @property
    def occupancy_pct(self) -> float:
        """Occupancy as a percentage (0–100)."""
        if self.total_spaces == 0:
            return 0.0
        return 100.0 * (self.total_spaces - self.available_spaces) / self.total_spaces

    @property
    def is_full(self) -> bool:
        """True if no spaces are available."""
        return self.available_spaces == 0


@dataclass
class WeatherAlert:
    """A National Weather Service alert displayed on the FL511 map."""

    alert_id: str
    """Alert identifier (may be NWS zone code or numeric ID)."""

    latitude: float
    """Decimal degrees latitude of the alert centroid."""

    longitude: float
    """Decimal degrees longitude of the alert centroid."""

    title: str = ""
    """Alert headline."""

    body: str = ""
    """Alert text body."""

    issued_at: str = ""
    """Date/time string when alert was issued."""


@dataclass
class WeatherForecastZone:
    """A NWS forecast zone shown on the FL511 weather layer."""

    zone_id: str
    """NWS zone code, e.g. 'FLZ010'."""

    latitude: float
    """Zone centroid latitude."""

    longitude: float
    """Zone centroid longitude."""


# ---------------------------------------------------------------------------
# Session / HTTP helpers
# ---------------------------------------------------------------------------

class FL511Session:
    """
    Manages a stateful HTTP session against fl511.com.

    The site uses ASP.NET cookie-based sessions. A session cookie is obtained
    automatically by visiting the homepage on first use.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj)
        )
        self._session_ready = False

    def _ensure_session(self) -> None:
        """Fetch the homepage to obtain a session-id cookie."""
        if self._session_ready:
            return
        req = urllib.request.Request(
            BASE_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FL511Client/1.0)"},
        )
        try:
            resp = self._opener.open(req, timeout=self.timeout)
            resp.read()
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize FL511 session: {exc}") from exc
        self._session_ready = True

    def _cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self._cj)

    def _make_headers(self, accept_json: bool = True) -> Dict[str, str]:
        self._ensure_session()
        h: Dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (compatible; FL511Client/1.0)",
            "Referer": BASE_URL + "/",
            "Cookie": self._cookie_header(),
        }
        if accept_json:
            h["Accept"] = "application/json, text/javascript, */*; q=0.01"
            h["X-Requested-With"] = "XMLHttpRequest"
        return h

    def get(self, path: str) -> bytes:
        """Perform a GET request and return raw bytes (decompressed if gzip)."""
        self._ensure_session()
        req = urllib.request.Request(
            BASE_URL + path, headers=self._make_headers()
        )
        try:
            resp = self._opener.open(req, timeout=self.timeout)
            raw = resp.read()
            # Handle gzip Content-Encoding (server may compress even without Accept-Encoding)
            ce = resp.headers.get("Content-Encoding", "")
            if ce == "gzip" or (len(raw) >= 2 and raw[:2] == b"\x1f\x8b"):
                import gzip as _gzip
                try:
                    raw = _gzip.decompress(raw)
                except Exception:
                    pass  # Not actually gzip, return as-is
            return raw
        except urllib.error.HTTPError as exc:
            raise FL511Error(f"HTTP {exc.code} on GET {path}") from exc
        except Exception as exc:
            raise FL511Error(f"Request failed on GET {path}: {exc}") from exc

    def get_json(self, path: str) -> object:
        """Perform a GET request and parse the JSON response."""
        raw = self.get(path)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FL511Error(f"JSON parse error on GET {path}: {exc}") from exc

    def post_form(self, path: str, data: Dict[str, str]) -> object:
        """POST application/x-www-form-urlencoded data and return parsed JSON."""
        self._ensure_session()
        body = urllib.parse.urlencode(data).encode()
        headers = self._make_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(
            BASE_URL + path, data=body, headers=headers, method="POST"
        )
        try:
            resp = self._opener.open(req, timeout=self.timeout)
            raw = resp.read()
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise FL511Error(f"HTTP {exc.code} on POST {path}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FL511Error(f"JSON parse error on POST {path}: {exc}") from exc
        except Exception as exc:
            raise FL511Error(f"Request failed on POST {path}: {exc}") from exc

    def get_bytes(self, path: str) -> bytes:
        """Perform a GET request and return raw bytes (for binary content like images)."""
        return self.get(path)


class FL511Error(Exception):
    """Base exception for all FL511Client errors."""


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class FL511Client:
    """
    Python client for the Florida Department of Transportation FL511 system.

    Reverse-engineered from https://fl511.com — no API key required.

    The client uses the same IBI Group ASP.NET MVC API endpoints that power
    the FL511 web map. An HTTP session is maintained automatically.

    Examples::

        client = FL511Client()

        # All ~4,700 cameras statewide (location data, fast)
        cameras = client.get_all_cameras()

        # Cameras with full detail (slower - one request per camera)
        detail = client.get_camera_detail(cameras[0].camera_id)
        print(detail.snapshot_url)

        # Cameras near a location
        nearby = client.get_cameras_near(25.775, -80.208, radius_miles=5)

        # Cameras by county/area
        miami = client.get_cameras_by_area("MDC")

        # Live incidents
        incidents = client.get_events("Incidents")

        # All event layer types
        for layer in client.list_event_layers():
            events = client.get_events(layer)
            print(f"{layer}: {len(events)}")

        # Download a JPEG snapshot
        jpeg_bytes = client.get_snapshot(camera_id=1)
        with open("cam.jpg", "wb") as f:
            f.write(jpeg_bytes)
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """
        Initialize the FL511 client.

        Args:
            timeout: HTTP request timeout in seconds.
        """
        self._session = FL511Session(timeout=timeout)

    # ------------------------------------------------------------------
    # Camera methods
    # ------------------------------------------------------------------

    def get_all_cameras(self) -> List[Camera]:
        """
        Return all ~4,700+ traffic cameras in Florida.

        This is the fast path: uses ``/map/mapIcons/Cameras`` which returns
        camera IDs and GPS coordinates in a single request. Image/video URL
        data is **not** included; use :meth:`get_camera_detail` for that.

        Returns:
            List of :class:`Camera` objects with ``camera_id``, ``latitude``,
            ``longitude``, and ``video_enabled`` populated.

        Example::

            cameras = client.get_all_cameras()
            live = [c for c in cameras if c.video_enabled]
            print(f"{len(live)} cameras with video out of {len(cameras)} total")
        """
        data = self._session.get_json("/map/mapIcons/Cameras")
        cameras: List[Camera] = []
        for item in data.get("item2", []):
            expando = item.get("expando", {})
            loc = item.get("location", [0.0, 0.0])
            cam = Camera(
                camera_id=int(item["itemId"]),
                source_id="",
                source="",
                area_id="",
                roadway="",
                direction=0,
                location="",
                latitude=float(loc[0]) if isinstance(loc, list) else 0.0,
                longitude=float(loc[1]) if isinstance(loc, list) else 0.0,
                images=[],
                video_enabled=expando.get("videoEnabled"),
            )
            cameras.append(cam)
        return cameras

    def get_camera_detail(self, camera_id: int) -> Camera:
        """
        Return full detail for a single camera, including image and video URLs.

        Fetches ``/map/data/Cameras/{camera_id}``.

        Args:
            camera_id: The numeric camera site ID.

        Returns:
            :class:`Camera` with all fields populated including
            :attr:`Camera.images` (snapshot URL + HLS stream URL).

        Raises:
            FL511Error: If the camera ID is not found or request fails.

        Example::

            cam = client.get_camera_detail(1)
            print(cam.location, cam.snapshot_url)
        """
        data = self._session.get_json(f"/map/data/Cameras/{camera_id}")
        return self._parse_camera_detail(data)

    def get_cameras_by_area(self, area_id: str) -> List[Camera]:
        """
        Return cameras for a specific county/area code.

        Uses ``/Camera/GetUserCameras?areaId={area_id}``. Returns full camera
        detail including image and video URLs.

        Args:
            area_id: County/area code, e.g. ``'MDC'`` (Miami-Dade),
                ``'HIL'`` (Hillsborough/Tampa), ``'PBC'`` (Palm Beach).
                See :data:`AREAS` for all valid codes.

        Returns:
            List of :class:`Camera` objects with full detail.

        Example::

            tampa_cams = client.get_cameras_by_area("HIL")
            for cam in tampa_cams:
                print(cam.roadway, cam.location, cam.snapshot_url)
        """
        path = f"/Camera/GetUserCameras?areaId={urllib.parse.quote(area_id)}"
        data = self._session.get_json(path)
        cameras: List[Camera] = []
        seen_ids: set = set()
        for item in data.get("data", []):
            cam_id = item.get("id")
            if cam_id in seen_ids:
                continue
            seen_ids.add(cam_id)
            cam = self._parse_camera_detail(item)
            cameras.append(cam)
        return cameras

    def iter_all_camera_details(
        self,
        camera_ids: Optional[List[int]] = None,
        delay: float = 0.05,
    ) -> Iterator[Camera]:
        """
        Yield full camera detail for all (or specified) cameras.

        This makes one HTTP request per camera. For all 4,700+ cameras this
        will take several minutes. Use ``delay`` to be a polite client.

        Args:
            camera_ids: Optional list of specific camera IDs to fetch. If
                ``None``, fetches all cameras from :meth:`get_all_cameras`.
            delay: Seconds to sleep between requests (default 0.05).

        Yields:
            :class:`Camera` objects with full detail.

        Example::

            # Get all cameras with HLS video streams
            for cam in client.iter_all_camera_details():
                if cam.has_video:
                    print(cam.camera_id, cam.stream_url)
        """
        if camera_ids is None:
            stubs = self.get_all_cameras()
            camera_ids = [c.camera_id for c in stubs]

        for cid in camera_ids:
            try:
                yield self.get_camera_detail(cid)
            except FL511Error:
                continue
            if delay > 0:
                time.sleep(delay)

    def get_cameras_near(
        self,
        lat: float,
        lon: float,
        radius_miles: float = 5.0,
        with_detail: bool = True,
    ) -> List[Tuple[float, Camera]]:
        """
        Find cameras within a given radius of a GPS coordinate.

        Args:
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.
            radius_miles: Search radius in miles (default 5.0).
            with_detail: If True, fetch full camera detail for each match
                (slower but includes snapshot/stream URLs).

        Returns:
            List of ``(distance_miles, Camera)`` tuples sorted by distance.

        Example::

            nearby = client.get_cameras_near(25.775, -80.208, radius_miles=3.0)
            for dist, cam in nearby:
                print(f"{dist:.1f} mi - {cam.location} {cam.snapshot_url}")
        """
        stubs = self.get_all_cameras()
        candidates = []
        for cam in stubs:
            d = cam.distance_to(lat, lon)
            if d <= radius_miles:
                candidates.append((d, cam))
        candidates.sort(key=lambda x: x[0])

        if not with_detail:
            return candidates

        result = []
        for d, stub in candidates:
            try:
                detail = self.get_camera_detail(stub.camera_id)
                result.append((d, detail))
            except FL511Error:
                result.append((d, stub))
        return result

    def get_snapshot(self, camera_id: int) -> bytes:
        """
        Download the current JPEG snapshot image for a camera.

        Uses ``/map/Cctv/{camera_id}``. Returns the raw JPEG bytes.
        The camera_id here is the image record ID (same as the camera site ID
        in most cases).

        Args:
            camera_id: The camera/image site ID.

        Returns:
            Raw JPEG image bytes.

        Example::

            jpeg = client.get_snapshot(1)
            with open("camera_1.jpg", "wb") as f:
                f.write(jpeg)
        """
        return self._session.get_bytes(f"/map/Cctv/{camera_id}")

    # ------------------------------------------------------------------
    # Event methods
    # ------------------------------------------------------------------

    def get_events(
        self,
        layer: str,
        page_size: int = 1000,
    ) -> List[object]:
        """
        Retrieve all events for a given layer.

        Uses ``POST /list/GetData/{layer}`` with DataTables pagination.

        Args:
            layer: Layer name. Must be one of the keys in :data:`EVENT_LAYERS`.
                Common values: ``'Incidents'``, ``'Construction'``,
                ``'Closures'``, ``'Congestion'``, ``'DisabledVehicles'``,
                ``'MessageSigns'``, ``'Bridge'``, ``'Parking'``,
                ``'RailCrossing'``, ``'WeatherEvents'``.
            page_size: Max records per page (default 1000, which covers all
                current FL511 data in one request).

        Returns:
            Typed list — :class:`TrafficEvent`, :class:`MessageSign`,
            :class:`Bridge`, :class:`ParkingFacility`, or dict for other layers.

        Raises:
            FL511Error: If the layer name is invalid or request fails.

        Example::

            incidents = client.get_events("Incidents")
            for inc in incidents:
                print(inc.roadway, inc.severity, inc.county)

            signs = client.get_events("MessageSigns")
            for sign in signs:
                if sign.status == "on":
                    print(sign.name, sign.display_message)
        """
        if layer not in EVENT_LAYERS:
            valid = ", ".join(sorted(EVENT_LAYERS.keys()))
            raise FL511Error(f"Unknown layer '{layer}'. Valid layers: {valid}")

        all_records = []
        start = 0
        while True:
            data = self._session.post_form(
                f"/list/GetData/{layer}",
                {"draw": "1", "start": str(start), "length": str(page_size)},
            )
            records = data.get("data", [])
            all_records.extend(records)
            total = data.get("recordsTotal", 0)
            start += len(records)
            if start >= total or not records:
                break

        return [self._parse_event_record(layer, r) for r in all_records]

    def get_event_detail(self, layer: str, event_id: int) -> dict:
        """
        Return the full detailed record for a specific event.

        Uses ``GET /map/data/{layer}/{event_id}`` which returns richer data
        than the list endpoint, including polyline geometry and detour routes.

        Args:
            layer: Layer name, e.g. ``'Incidents'``.
            event_id: The event ID number.

        Returns:
            Raw dict with full event fields including ``latitude``,
            ``longitude``, ``latLng.geography.wellKnownText``,
            ``detourPolyline``, ``lanes``, ``cameraIds``, etc.

        Example::

            detail = client.get_event_detail("Incidents", 389236)
            print(detail["latitude"], detail["longitude"])
            print(detail.get("detourPolyline", "no detour"))
        """
        return self._session.get_json(f"/map/data/{layer}/{event_id}")

    def get_weather_alerts(self) -> List[WeatherAlert]:
        """
        Return current NWS weather alerts displayed on the FL511 map.

        Uses ``/map/mapIcons/WeatherEvents``.

        Returns:
            List of :class:`WeatherAlert` objects.
        """
        data = self._session.get_json("/map/mapIcons/WeatherEvents")
        alerts = []
        for item in data.get("item2", []):
            loc = item.get("location", [0.0, 0.0])
            alerts.append(
                WeatherAlert(
                    alert_id=str(item.get("itemId", "")),
                    latitude=float(loc[0]) if isinstance(loc, list) else 0.0,
                    longitude=float(loc[1]) if isinstance(loc, list) else 0.0,
                )
            )
        return alerts

    def get_weather_forecast_zones(self) -> List[WeatherForecastZone]:
        """
        Return NWS weather forecast zones shown on the FL511 map.

        Uses ``/map/mapIcons/WeatherForecast``.

        Returns:
            List of :class:`WeatherForecastZone` objects with zone IDs and
            coordinates.
        """
        data = self._session.get_json("/map/mapIcons/WeatherForecast")
        zones = []
        for item in data.get("item2", []):
            loc = item.get("location", [0.0, 0.0])
            zones.append(
                WeatherForecastZone(
                    zone_id=str(item.get("itemId", "")),
                    latitude=float(loc[0]) if isinstance(loc, list) else 0.0,
                    longitude=float(loc[1]) if isinstance(loc, list) else 0.0,
                )
            )
        return zones

    # ------------------------------------------------------------------
    # Info / utility methods
    # ------------------------------------------------------------------

    def list_areas(self) -> Dict[str, str]:
        """
        Return the known area code -> description mapping.

        Returns:
            Dict mapping area codes (e.g. ``'MDC'``) to descriptions.
        """
        return dict(AREAS)

    def list_event_layers(self) -> Dict[str, str]:
        """
        Return available event layer names and descriptions.

        Returns:
            Dict mapping layer names to human-readable descriptions.
        """
        return dict(EVENT_LAYERS)

    def list_districts(self) -> Dict[str, str]:
        """
        Return FDOT district codes and county coverage descriptions.

        Returns:
            Dict mapping district IDs to descriptions.
        """
        return dict(DISTRICTS)

    def get_traffic_speed_tile_url(self) -> str:
        """
        Return the XYZ tile URL template for real-time traffic speed tiles.

        The tiles are served by IBI Group's tile server and show road speeds
        as color-coded overlays (green/yellow/red).

        Returns:
            URL template string with ``{x}``, ``{y}``, ``{z}`` placeholders.
        """
        return "https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}"

    def get_weather_radar_tile_url(self) -> str:
        """
        Return the XYZ tile URL template for NEXRAD weather radar tiles.

        Returns:
            URL template string with ``{x}``, ``{y}``, ``{z}`` placeholders.
        """
        return f"{BASE_URL}/map/weatherRadar/{{x}}/{{y}}/{{z}}"

    def get_fdot_arcgis_detour_geojson(self, detour_type: str = "Detour") -> dict:
        """
        Fetch FDOT emergency detour route GeoJSON from ArcGIS Online.

        These are publicly available FDOT feature services that FL511 uses
        for the Emergency Roadway System (ERS) layer.

        Args:
            detour_type: ``'Detour'`` or ``'Closed'``.

        Returns:
            GeoJSON FeatureCollection dict.

        Example::

            geojson = client.get_fdot_arcgis_detour_geojson()
            for feat in geojson["features"]:
                coords = feat["geometry"]["coordinates"]
                print(f"Detour route with {len(coords)} points")
        """
        base = (
            "https://services1.arcgis.com/O1JpcwDW8sjYuddV/ArcGIS/rest/services/"
            "FDOT_Emergency_Detour_Routes_Public_View/FeatureServer/0/query"
        )
        params = urllib.parse.urlencode(
            {
                "where": f"Detour='{detour_type}'",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "pgeojson",
                "returnExceededLimitFeatures": "true",
            }
        )
        url = f"{base}?{params}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; FL511Client/1.0)"}
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self._session.timeout)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise FL511Error(f"ArcGIS request failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Private parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_camera_detail(data: dict) -> Camera:
        """Parse a camera detail dict from /map/data/Cameras/{id} or GetUserCameras."""
        lat, lon = 0.0, 0.0
        latlng = data.get("latLng", {})
        if latlng:
            geo = latlng.get("geography", {})
            wkt = geo.get("wellKnownText", "")
            # Format: "POINT (lon lat)"
            if wkt.startswith("POINT"):
                coords = wkt.replace("POINT", "").strip(" ()")
                parts = coords.split()
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
        # Override with explicit lat/lon if present (from list endpoints)
        if "latitude" in data:
            lat = float(data["latitude"])
        if "longitude" in data:
            lon = float(data["longitude"])

        images = []
        for img in data.get("images", []):
            images.append(
                CameraImage(
                    image_id=int(img.get("id", 0)),
                    camera_site_id=int(img.get("cameraSiteId", 0)),
                    description=img.get("description", ""),
                    image_url=img.get("imageUrl", ""),
                    video_url=img.get("videoUrl", ""),
                    video_type=img.get("videoType", ""),
                    video_disabled=bool(img.get("videoDisabled", False)),
                    blocked=bool(img.get("blocked", False)),
                )
            )

        return Camera(
            camera_id=int(data.get("id", 0)),
            source_id=str(data.get("sourceId", "")),
            source=str(data.get("source", "")),
            area_id=str(data.get("areaId", "")),
            roadway=str(data.get("roadway", "")),
            direction=int(data.get("direction", 0)),
            location=str(data.get("location", "")),
            latitude=lat,
            longitude=lon,
            images=images,
        )

    @staticmethod
    def _parse_event_record(layer: str, rec: dict) -> object:
        """Parse an event record from /list/GetData/{layer}."""
        if layer == "MessageSigns":
            lat, lon = 0.0, 0.0
            latlng = rec.get("latLng", {})
            if latlng:
                geo = latlng.get("geography", {})
                wkt = geo.get("wellKnownText", "")
                if wkt.startswith("POINT"):
                    coords = wkt.replace("POINT", "").strip(" ()")
                    parts = coords.split()
                    if len(parts) >= 2:
                        lon, lat = float(parts[0]), float(parts[1])
            return MessageSign(
                sign_id=int(rec.get("id", 0)),
                source_id=str(rec.get("sourceId", "")),
                name=str(rec.get("name", "")),
                roadway=str(rec.get("roadwayName", "")),
                direction=str(rec.get("direction", "")),
                area_id=str(rec.get("area_AreaId", rec.get("area", ""))),
                county=str(rec.get("county", "")),
                region=str(rec.get("region", "")),
                status=str(rec.get("status", "")),
                message=str(rec.get("message", "")),
                message_line2=str(rec.get("message2", "")),
                message_line3=str(rec.get("message3", "")),
                latitude=lat,
                longitude=lon,
                last_updated=str(rec.get("lastUpdated", "")),
            )

        if layer == "Bridge":
            return Bridge(
                bridge_id=int(rec.get("DT_RowId", 0)),
                name=str(rec.get("name", rec.get("filterAndOrderProperty1", ""))),
                roadway=str(rec.get("roadway", rec.get("filterAndOrderProperty3", ""))),
                location=str(rec.get("location", rec.get("filterAndOrderProperty2", ""))),
                county=str(rec.get("county", rec.get("filterAndOrderProperty4", ""))),
                status=str(rec.get("status", rec.get("filterAndOrderProperty5", ""))),
                direction=str(rec.get("direction", rec.get("filterAndOrderProperty6", ""))),
                network=str(rec.get("networkName", "")),
                last_updated=str(rec.get("lastUpdated", "")),
                last_notification_time=str(rec.get("lastNotificationTime", "")),
            )

        if layer == "Parking":
            return ParkingFacility(
                facility_id=int(rec.get("DT_RowId", 0)),
                name=str(rec.get("deviceLocationName", rec.get("filterAndOrderProperty1", ""))),
                roadway=str(rec.get("roadwayName", rec.get("filterAndOrderProperty2", ""))),
                direction=str(rec.get("roadwayDirection", "")),
                total_spaces=int(rec.get("totalParkingSpaces", 0) or 0),
                available_spaces=int(rec.get("availableParkingSpaces", 0) or 0),
                last_updated=str(rec.get("lastUpdated", "")),
            )

        # Default: traffic events (Incidents, Construction, Closures, etc.)
        return TrafficEvent(
            event_id=int(rec.get("id", rec.get("DT_RowId", 0))),
            layer=layer,
            event_type=str(rec.get("type", layer)),
            event_subtype=str(rec.get("eventSubType", "")),
            roadway=str(rec.get("roadwayName", "")),
            direction=str(rec.get("direction", "")),
            description=str(rec.get("description", "")),
            comment=str(rec.get("comment", "")),
            severity=str(rec.get("severity", "")),
            is_full_closure=bool(rec.get("isFullClosure", False)),
            latitude=0.0,
            longitude=0.0,
            area_id="",
            dot_district=str(rec.get("dotDistrict", "")),
            region=str(rec.get("region", "")),
            county=str(rec.get("county", "")),
            start_date=str(rec.get("startDate", "")),
            last_updated=str(rec.get("lastUpdated", "")),
            end_date=rec.get("endDate"),
            lane_description=str(rec.get("laneDescription", "")),
            detour_description=str(rec.get("detourDescription", "") or ""),
            source=str(rec.get("source", "")),
            camera_ids=str(rec.get("cameras", "") or ""),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:  # noqa: C901
    """Command-line interface for the FL511 client."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FL511 Florida Traffic Camera & Events Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all cameras statewide
  python fl511_client.py --cameras

  # List cameras in Miami-Dade
  python fl511_client.py --cameras --area MDC

  # Show cameras near Tampa International Airport
  python fl511_client.py --cameras-near 27.975 -82.533 --radius 3

  # Download snapshot from camera 1
  python fl511_client.py --snapshot 1 --output cam1.jpg

  # Get full detail for camera 1 (with video URL)
  python fl511_client.py --camera-detail 1

  # Get all traffic incidents
  python fl511_client.py --events Incidents

  # Get all construction zones
  python fl511_client.py --events Construction

  # Get dynamic message sign content
  python fl511_client.py --events MessageSigns

  # Get drawbridge status
  python fl511_client.py --events Bridge

  # Get truck parking availability
  python fl511_client.py --events Parking

  # Get weather alerts
  python fl511_client.py --events WeatherEvents

  # List all area codes
  python fl511_client.py --list-areas

  # Output JSON
  python fl511_client.py --cameras --json
""",
    )
    parser.add_argument("--cameras", action="store_true", help="List all cameras")
    parser.add_argument("--area", help="Filter cameras by area code (e.g. MDC, HIL, PBC)")
    parser.add_argument("--camera-detail", type=int, metavar="ID",
                        help="Show full detail for camera ID")
    parser.add_argument("--cameras-near", nargs=2, type=float, metavar=("LAT", "LON"),
                        help="Find cameras near a lat/lon")
    parser.add_argument("--radius", type=float, default=5.0,
                        help="Radius in miles for --cameras-near (default 5.0)")
    parser.add_argument("--snapshot", type=int, metavar="ID",
                        help="Download JPEG snapshot for camera ID")
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Output file path for --snapshot")
    parser.add_argument("--events", metavar="LAYER",
                        help="Fetch events for a layer (e.g. Incidents, Construction, "
                             "MessageSigns, Bridge, Parking)")
    parser.add_argument("--event-detail", nargs=2, metavar=("LAYER", "ID"),
                        help="Show full detail for a specific event")
    parser.add_argument("--list-areas", action="store_true",
                        help="List all area codes")
    parser.add_argument("--list-layers", action="store_true",
                        help="List all available event layers")
    parser.add_argument("--detour-routes", action="store_true",
                        help="Fetch FDOT ERS detour routes (ArcGIS GeoJSON)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--limit", type=int, help="Limit number of results")
    parser.add_argument("--timeout", type=int, default=30,
                        help="Request timeout in seconds (default 30)")
    args = parser.parse_args()

    client = FL511Client(timeout=args.timeout)

    def _print_json(obj):
        import dataclasses
        def default(o):
            if dataclasses.is_dataclass(o):
                return dataclasses.asdict(o)
            return str(o)
        print(json.dumps(obj, default=default, indent=2, ensure_ascii=False))

    if args.list_areas:
        if args.json:
            _print_json(client.list_areas())
        else:
            print(f"{'Code':<8} Description")
            print("-" * 70)
            for code, desc in sorted(client.list_areas().items()):
                print(f"{code:<8} {desc}")
        return

    if args.list_layers:
        if args.json:
            _print_json(client.list_event_layers())
        else:
            print(f"{'Layer':<28} Description")
            print("-" * 70)
            for layer, desc in client.list_event_layers().items():
                print(f"{layer:<28} {desc}")
        return

    if args.snapshot is not None:
        jpeg = client.get_snapshot(args.snapshot)
        out = args.output or f"fl511_cam_{args.snapshot}.jpg"
        with open(out, "wb") as fh:
            fh.write(jpeg)
        print(f"Saved {len(jpeg):,} bytes to {out}")
        return

    if args.camera_detail is not None:
        cam = client.get_camera_detail(args.camera_detail)
        if args.json:
            import dataclasses
            _print_json(dataclasses.asdict(cam))
        else:
            print(f"Camera {cam.camera_id}")
            print(f"  Location:    {cam.location}")
            print(f"  Roadway:     {cam.roadway} {cam.direction_name}")
            print(f"  Area:        {cam.area_id} ({cam.area_name})")
            print(f"  Source:      {cam.source}")
            print(f"  GPS:         {cam.latitude:.6f}, {cam.longitude:.6f}")
            print(f"  Snapshot:    {cam.snapshot_url or 'N/A'}")
            if cam.images:
                for img in cam.images:
                    print(f"  Stream URL:  {img.video_url or 'N/A'}")
                    print(f"  Video auth:  {'required (DIVAS)' if img.video_url else 'N/A'}")
        return

    if args.cameras_near:
        lat, lon = args.cameras_near
        results = client.get_cameras_near(lat, lon, radius_miles=args.radius, with_detail=True)
        results = results[: args.limit] if args.limit else results
        if args.json:
            import dataclasses
            _print_json([{"distance_miles": round(d, 2), "camera": dataclasses.asdict(c)}
                         for d, c in results])
        else:
            print(f"Cameras within {args.radius} miles of ({lat}, {lon}):")
            print(f"{'ID':<6} {'Dist':>6}  {'Roadway':<20} {'Location'}")
            print("-" * 80)
            for dist, cam in results:
                print(f"{cam.camera_id:<6} {dist:>5.1f}mi  {cam.roadway:<20} {cam.location[:40]}")
        return

    if args.cameras:
        if args.area:
            cameras = client.get_cameras_by_area(args.area)
        else:
            cameras = client.get_all_cameras()
        cameras = cameras[: args.limit] if args.limit else cameras
        if args.json:
            import dataclasses
            _print_json([dataclasses.asdict(c) for c in cameras])
        else:
            print(f"{'ID':<6} {'Lat':>10} {'Lon':>11} {'Video':<6} {'Area':<6} {'Roadway':<20} Location")
            print("-" * 100)
            for cam in cameras:
                vid = "YES" if cam.video_enabled or cam.has_video else "no"
                print(f"{cam.camera_id:<6} {cam.latitude:>10.5f} {cam.longitude:>11.5f} "
                      f"{vid:<6} {cam.area_id:<6} {cam.roadway[:20]:<20} {cam.location[:40]}")
            print(f"\nTotal: {len(cameras)} cameras")
        return

    if args.events:
        layer = args.events
        events = client.get_events(layer)
        events = events[: args.limit] if args.limit else events
        if args.json:
            import dataclasses
            def default(o):
                if dataclasses.is_dataclass(o):
                    return dataclasses.asdict(o)
                return str(o)
            print(json.dumps(events, default=default, indent=2, ensure_ascii=False))
        else:
            print(f"--- {layer} ({len(events)} records) ---")
            for evt in events:
                if isinstance(evt, TrafficEvent):
                    print(f"  [{evt.severity}] {evt.roadway} {evt.direction} | {evt.county} | {evt.event_subtype}")
                    if evt.description:
                        desc = evt.description.split("<")[0].strip()
                        print(f"    {desc[:100]}")
                elif isinstance(evt, MessageSign):
                    print(f"  [{evt.status.upper()}] {evt.roadway} {evt.direction.upper()} | {evt.county}")
                    if evt.status == "on":
                        print(f"    MSG: {evt.display_message[:80]}")
                elif isinstance(evt, Bridge):
                    status = "RAISED" if evt.is_open_to_boats else "down"
                    print(f"  [{status}] {evt.name} | {evt.county} | {evt.roadway}")
                elif isinstance(evt, ParkingFacility):
                    avail = f"{evt.available_spaces}/{evt.total_spaces}"
                    pct = f"{evt.occupancy_pct:.0f}% full"
                    print(f"  {evt.name} | {evt.roadway} {evt.direction} | Spaces: {avail} ({pct})")
                else:
                    print(f"  {evt}")
        return

    if args.event_detail:
        layer, eid = args.event_detail[0], int(args.event_detail[1])
        detail = client.get_event_detail(layer, eid)
        if args.json:
            _print_json(detail)
        else:
            for k, v in detail.items():
                if v is not None and v != "" and v != {} and v != "{}":
                    print(f"  {k}: {str(v)[:120]}")
        return

    if args.detour_routes:
        geojson = client.get_fdot_arcgis_detour_geojson()
        if args.json:
            _print_json(geojson)
        else:
            features = geojson.get("features", [])
            print(f"FDOT ERS Detour Routes: {len(features)} features")
            for feat in features[:10]:
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                print(f"  type={geom.get('type')} points={len(coords)}")
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
