"""
tdot_client.py — Tennessee DOT (TDOT) SmartWay Traffic Data Client
==================================================================
A production-quality Python client for the TDOT SmartWay public API.
Zero external dependencies — uses only the Python standard library.

Reverse-engineered from https://smartway.tn.gov (Angular app, version 20251212.2_master).
Config discovered at: https://smartway.tn.gov/assets/config/config.prod.json

API Base URL : https://www.tdot.tn.gov/opendata/api/public/
Auth         : Static API key sent in "ApiKey" request header.
               Key embedded in public web app config (no registration required).
CDN Thumbs   : https://tnsnapshots.com/thumbs/{stream_id}.flv.png
HLS Streams  : https://mcleansfs{1-5}.us-east-1.skyvdn.com:443/rtplive/{stream_id}/playlist.m3u8
RTMP Streams : rtmp://mcleansfs{1-5}.us-east-1.skyvdn.com:1935/rtplive/{stream_id}
RTSP Streams : rtsp://mcleansfs{1-5}.us-east-1.skyvdn.com:554/rtplive/{stream_id}

Discovered Endpoints
--------------------
GET  /RoadwayCameras               — 666 live traffic cameras (thumbnail + HLS/RTMP/RTSP)
GET  /RoadwayCameras/{id}          — Single camera by numeric ID
GET  /RoadwayIncidents             — Active traffic incidents (crashes, congestion, closures)
GET  /RoadwayOperations            — Active construction / roadway operations
GET  /RoadwaySevereImpact          — Severe-impact events (bridge closures, major disruptions)
GET  /RoadwayWeather               — Active weather-related roadway events
GET  /RoadwayMessageSigns          — Dynamic Message Sign (DMS) current display text
GET  /RestAreas                    — Rest area status (open/closed, events, location)
GET  /RoadwaySpecialEvents         — Special events affecting traffic (may return 204)
GET  /SmartWayBanner               — System-wide banner/alert message

ArcGIS REST Services (no API key required)
------------------------------------------
GET  https://spatial.tdot.tn.gov/ArcGIS/rest/services/WAZE/Waze_Smartway/MapServer/0/query
     — Waze crowd-sourced incident data overlaid on SmartWay
GET  https://services2.arcgis.com/nf3p7v7Zy4fTOh6M/arcgis/rest/services/
         Administrative_Boundaries_Prod_Data/FeatureServer/7/query
     — Tennessee county boundary polygons (95 counties)

Usage
-----
    from tdot_client import TDOTClient

    client = TDOTClient()

    # List all active cameras
    cameras = client.get_cameras()
    print(f"{len(cameras)} cameras")
    print(cameras[0].title, cameras[0].thumbnail_url)

    # Get a single camera
    cam = client.get_camera(3165)
    print(cam.hls_url)

    # Live incidents
    for inc in client.get_incidents():
        print(inc.description)

    # Message signs with active messages
    for sign in client.get_message_signs():
        if sign.message:
            print(sign.title, ":", sign.message_lines)

CLI
---
    python tdot_client.py cameras [--route ROUTE] [--jurisdiction CITY]
    python tdot_client.py camera  <id>
    python tdot_client.py incidents
    python tdot_client.py construction
    python tdot_client.py severe
    python tdot_client.py weather
    python tdot_client.py signs    [--active]
    python tdot_client.py restareas
    python tdot_client.py banner
    python tdot_client.py demo
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = "https://www.tdot.tn.gov/opendata/api/public/"
API_KEY = "8d3b7a82635d476795c09b2c41facc60"
GOOGLE_MAPS_API_KEY = "AIzaSyDQzQD27wKmM8DNPAmZ0qXf8XCrJA0qB4s"

# ArcGIS services (no auth required)
WAZE_URL = (
    "https://spatial.tdot.tn.gov/ArcGIS/rest/services/WAZE/Waze_Smartway"
    "/MapServer/0/query?where=1%3D1&returnGeometry=true&outFields=%2a&f=json"
)
COUNTY_POLYGON_URL = (
    "https://services2.arcgis.com/nf3p7v7Zy4fTOh6M/arcgis/rest/services/"
    "Administrative_Boundaries_Prod_Data/FeatureServer/7/"
)

# CDN patterns
THUMBNAIL_CDN = "https://tnsnapshots.com/thumbs/{stream_id}.flv.png"
HLS_CDN_TEMPLATE = "https://mcleansfs{node}.us-east-1.skyvdn.com:443/rtplive/{stream_id}/playlist.m3u8"
RTMP_CDN_TEMPLATE = "rtmp://mcleansfs{node}.us-east-1.skyvdn.com:1935/rtplive/{stream_id}"
RTSP_CDN_TEMPLATE = "rtsp://mcleansfs{node}.us-east-1.skyvdn.com:554/rtplive/{stream_id}"

DEFAULT_TIMEOUT = 20  # seconds


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Coordinate:
    """A single lat/lng coordinate pair."""

    lat: float
    lng: float

    @classmethod
    def from_dict(cls, d: dict) -> "Coordinate":
        return cls(lat=float(d["lat"]), lng=float(d["lng"]))

    def __str__(self) -> str:
        return f"({self.lat:.6f}, {self.lng:.6f})"


@dataclass
class Location:
    """
    Geometry wrapper used in roadway events and cameras.

    Attributes:
        type_:       Geometry type string — "Point" or "point".
        coordinates: List of coordinate dicts (usually one point for cameras,
                     may be a polyline sequence for events).
        mid_point:   Pre-computed midpoint used on the map; may be None.
        route_line:  Polyline defining the affected segment; may be empty.
        opposite_impact_route_line: Opposite-direction polyline; may be empty.
        region:      TDOT region number (1–4).
        county_id:   Numeric county ID; may be None.
        county_name: Human-readable county name; may be None.
    """

    type_: str
    coordinates: list[Coordinate]
    mid_point: Optional[Coordinate] = None
    route_line: list[list[Coordinate]] = field(default_factory=list)
    opposite_impact_route_line: list[list[Coordinate]] = field(default_factory=list)
    region: Optional[int] = None
    county_id: Optional[int] = None
    county_name: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Location":
        coords = [Coordinate.from_dict(c) for c in d.get("coordinates", [])]
        mp_raw = d.get("midPoint")
        mid = Coordinate.from_dict(mp_raw) if mp_raw else None

        route_line = [
            [Coordinate.from_dict(pt) for pt in segment]
            for segment in d.get("routeLine", [])
        ]
        opp_line = [
            [Coordinate.from_dict(pt) for pt in segment]
            for segment in d.get("oppositeImpactRouteLine", [])
        ]

        return cls(
            type_=d.get("type", ""),
            coordinates=coords,
            mid_point=mid,
            route_line=route_line,
            opposite_impact_route_line=opp_line,
            region=d.get("region"),
            county_id=d.get("countyId"),
            county_name=d.get("countyName"),
        )

    @property
    def point(self) -> Optional[Coordinate]:
        """Returns the primary coordinate (first in list, or mid_point)."""
        if self.coordinates:
            return self.coordinates[0]
        return self.mid_point


@dataclass
class Camera:
    """
    A TDOT SmartWay traffic camera.

    Attributes:
        id:            Numeric camera ID (use with /RoadwayCameras/{id}).
        title:         Human-readable name, e.g. "I-40/75 @ West Hills".
        description:   Usually same as title; may contain extra detail.
        thumbnail_url: Direct URL to a static PNG snapshot (~120 KB).
                       Pattern: https://tnsnapshots.com/thumbs/{stream_id}.flv.png
                       Refreshes server-side — always fetch with cache-busting headers.
        hls_url:       HTTPS HLS playlist (.m3u8) for live video.
                       Served on port 443 by SkyVDN CDN.
                       Compatible with ffmpeg, vlc, hls.js, video.js.
        http_video_url: HTTP variant of HLS URL (same content, different scheme).
        rtmp_url:      RTMP stream URL for legacy Flash / OBS ingestion.
        rtsp_url:      RTSP stream URL for VLC, ONVIF-compatible clients.
        clsp_url:      CLSP (low-latency) URL; may be null.
        clsps_url:     Secure CLSP URL; may be null.
        active:        "true" / "false" string from API; use is_active property.
        jurisdiction:  One of: "Knoxville", "Nashville", "Memphis", "Chattanooga".
        route:         Route identifier e.g. "I-40", "I-24", "Briley Pkwy".
        mile_marker:   String mile marker value at camera location; may be empty.
        lat:           Decimal degrees latitude (WGS84).
        lng:           Decimal degrees longitude (WGS84).
        location:      Full Location object with coordinate list.
    """

    id: int
    title: str
    description: str
    thumbnail_url: Optional[str]
    hls_url: Optional[str]
    http_video_url: Optional[str]
    rtmp_url: Optional[str]
    rtsp_url: Optional[str]
    clsp_url: Optional[str]
    clsps_url: Optional[str]
    active: str
    jurisdiction: Optional[str]
    route: Optional[str]
    mile_marker: Optional[str]
    lat: float
    lng: float
    location: Optional[Location]

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        loc_raw = d.get("location")
        loc = Location.from_dict(loc_raw) if loc_raw else None
        return cls(
            id=int(d["id"]),
            title=d.get("title", ""),
            description=d.get("description", ""),
            thumbnail_url=d.get("thumbnailUrl"),
            hls_url=d.get("httpsVideoUrl"),
            http_video_url=d.get("httpVideoUrl"),
            rtmp_url=d.get("rtmpVideoUrl"),
            rtsp_url=d.get("rtspVideoUrl"),
            clsp_url=d.get("clspUrl"),
            clsps_url=d.get("clspsUrl"),
            active=d.get("active", "false"),
            jurisdiction=d.get("jurisdiction"),
            route=d.get("route"),
            mile_marker=d.get("mileMarker"),
            lat=float(d.get("lat", 0)),
            lng=float(d.get("lng", 0)),
            location=loc,
        )

    @property
    def is_active(self) -> bool:
        """True when the camera feed is marked active by TDOT."""
        return self.active.lower() == "true"

    @property
    def stream_id(self) -> Optional[str]:
        """
        Extract the stream identifier from the HLS URL.
        Example: "R1_010" from
        "https://mcleansfs1.../rtplive/R1_010/playlist.m3u8"
        """
        if not self.hls_url:
            return None
        parts = self.hls_url.rstrip("/").split("/")
        # Structure: .../rtplive/{stream_id}/playlist.m3u8
        try:
            idx = parts.index("rtplive")
            return parts[idx + 1]
        except (ValueError, IndexError):
            return None

    def __str__(self) -> str:
        active_str = "active" if self.is_active else "inactive"
        return (
            f"Camera({self.id}) [{active_str}] "
            f"{self.title!r} | {self.jurisdiction} | "
            f"{self.route} MM{self.mile_marker} | "
            f"({self.lat:.4f}, {self.lng:.4f})"
        )


@dataclass
class RoadwayEvent:
    """
    A roadway event — used for incidents, construction, weather, and severe impacts.

    Attributes:
        id:                     Unique numeric event ID.
        status:                 "Confirmed" or "Unconfirmed".
        event_type_id:          Numeric type code.
        event_type_name:        Human-readable type: "Incident", "Operations",
                                "Weather", "Construction", etc.
        event_subtype_id:       Numeric subtype code.
        event_subtype_desc:     Human-readable subtype: "Crash", "Congestion",
                                "Bridge Work", "Weather", etc.
        description:            Full narrative description from TDOT operators.
        current_activity:       Operator notes on current status; may be None.
        locations:              List of Location objects defining geometry.
        beginning_date:         ISO-8601 datetime string when event started.
        ending_date:            ISO-8601 datetime string; None if ongoing.
        revised_date:           ISO-8601 datetime of last update.
        has_closure:            True if lanes are closed.
        impact_description:     Primary direction impact summary.
        opposite_impact_desc:   Opposite direction impact summary; may be empty.
        direction_description:  Affected direction string e.g. "Northbound".
        diversion_description:  Any detour routing text; may be empty.
        day_of_week:            Day of week string; may be None.
        mile_marker:            String mile marker; may be None.
        is_severe:              True for severe-impact events.
        wide_area:              True if the event spans a wide geographic area.
        thp_reported:           True if reported by Tennessee Highway Patrol.
        primary_event_id:       Parent event ID for linked events; may be None.
        parent_id:              Parent container ID; may be None.
    """

    id: int
    status: str
    event_type_id: int
    event_type_name: str
    event_subtype_id: int
    event_subtype_desc: str
    description: str
    current_activity: Optional[str]
    locations: list[Location]
    beginning_date: Optional[str]
    ending_date: Optional[str]
    revised_date: Optional[str]
    has_closure: bool
    impact_description: str
    opposite_impact_desc: str
    direction_description: str
    diversion_description: str
    day_of_week: Optional[str]
    mile_marker: Optional[str]
    is_severe: bool
    wide_area: bool
    thp_reported: bool
    primary_event_id: Optional[int]
    parent_id: Optional[int]

    @classmethod
    def from_dict(cls, d: dict) -> "RoadwayEvent":
        locs = [Location.from_dict(loc) for loc in d.get("locations", [])]
        return cls(
            id=int(d["id"]),
            status=d.get("status", ""),
            event_type_id=int(d.get("eventTypeId", 0)),
            event_type_name=d.get("eventTypeName", ""),
            event_subtype_id=int(d.get("eventSubTypeId", 0)),
            event_subtype_desc=d.get("eventSubTypeDescription", ""),
            description=d.get("description", ""),
            current_activity=d.get("currentActivity"),
            locations=locs,
            beginning_date=d.get("beginningDate"),
            ending_date=d.get("endingDate"),
            revised_date=d.get("revisedDate"),
            has_closure=bool(d.get("hasClosure", False)),
            impact_description=d.get("impactDescription", ""),
            opposite_impact_desc=d.get("oppositeImpactDescription", ""),
            direction_description=d.get("directionDescription", ""),
            diversion_description=d.get("diversionDescription", ""),
            day_of_week=d.get("dayOfWeek"),
            mile_marker=d.get("mileMarker"),
            is_severe=bool(d.get("isSevere", False)),
            wide_area=bool(d.get("wideArea", False)),
            thp_reported=bool(d.get("thpReported", False)),
            primary_event_id=d.get("primaryEventId"),
            parent_id=d.get("parentId"),
        )

    @property
    def primary_location(self) -> Optional[Location]:
        """First location in the locations list, or None."""
        return self.locations[0] if self.locations else None

    def __str__(self) -> str:
        closure = " [CLOSURE]" if self.has_closure else ""
        return (
            f"Event({self.id}){closure} "
            f"{self.event_type_name}/{self.event_subtype_desc} | "
            f"{self.status} | {self.description[:80]}"
        )


@dataclass
class MessageSign:
    """
    A Dynamic Message Sign (DMS) showing current display content.

    Attributes:
        id:       String sign ID (numeric string, e.g. "1108").
        title:    Location description e.g. "(30)I-40EB W/O Rockwood Mntn".
        message:  Raw pipe-delimited message string e.g. "HEAVY CONGESTION|AT MM 387|EXPECT DELAYS".
                  Empty string when the sign is blank.
        region:   TDOT region (1–4).
        route:    Full route name e.g. "Interstate 40".
        location: Location geometry.
        graphic:  Optional graphic data; currently always null.
    """

    id: str
    title: str
    message: str
    region: int
    route: str
    location: Optional[Location]
    graphic: Optional[object]

    @classmethod
    def from_dict(cls, d: dict) -> "MessageSign":
        loc_raw = d.get("location")
        loc = Location.from_dict(loc_raw) if loc_raw else None
        return cls(
            id=str(d["id"]),
            title=d.get("title", ""),
            message=d.get("message", ""),
            region=int(d.get("region", 0)),
            route=d.get("route", ""),
            location=loc,
            graphic=d.get("graphic"),
        )

    @property
    def message_lines(self) -> list[str]:
        """Split pipe-delimited message into individual display lines."""
        if not self.message:
            return []
        return self.message.split("|")

    @property
    def is_blank(self) -> bool:
        """True when the sign has no active message."""
        return not self.message

    def __str__(self) -> str:
        content = " / ".join(self.message_lines) if self.message else "(blank)"
        return f"Sign({self.id}) {self.route!r} — {self.title} — {content}"


@dataclass
class RestArea:
    """
    A Tennessee highway rest area or welcome center.

    Attributes:
        id:             Numeric rest area ID.
        display_name:   Human-readable name e.g. "Rest Area on I-24 EB at MM 160".
        is_open:        True when the facility is open.
        county:         County name; may be None.
        region:         TDOT region (1–4).
        route:          Full route name e.g. "Interstate 24".
        type_:          Facility type: "Rest Stop" or "Welcome Center".
        mile:           Milepost number.
        lat:            Latitude (WGS84).
        lng:            Longitude (WGS84).
        beg_log_mile:   Beginning log mile.
        section_id:     Internal section identifier; may be None.
        events:         List of event dicts currently affecting this rest area.
        planned_closure: Planned closure information; may be None.
    """

    id: int
    display_name: str
    is_open: bool
    county: Optional[str]
    region: int
    route: str
    type_: str
    mile: float
    lat: float
    lng: float
    beg_log_mile: float
    section_id: Optional[str]
    events: list[dict]
    planned_closure: Optional[dict]

    @classmethod
    def from_dict(cls, d: dict) -> "RestArea":
        return cls(
            id=int(d["id"]),
            display_name=d.get("displayName", ""),
            is_open=bool(d.get("isOpen", False)),
            county=d.get("county"),
            region=int(d.get("region", 0)),
            route=d.get("route", ""),
            type_=d.get("type", ""),
            mile=float(d.get("mile", 0)),
            lat=float(d.get("lat", 0)),
            lng=float(d.get("lng", 0)),
            beg_log_mile=float(d.get("begLogMile", 0)),
            section_id=d.get("sectionId"),
            events=d.get("events", []),
            planned_closure=d.get("plannedClosure"),
        )

    def __str__(self) -> str:
        status = "OPEN" if self.is_open else "CLOSED"
        return f"RestArea({self.id}) [{status}] {self.display_name}"


@dataclass
class BannerMessage:
    """System-wide banner/alert message shown on the SmartWay website."""

    message: str

    @classmethod
    def from_dict(cls, d: dict) -> "BannerMessage":
        return cls(message=d.get("message", ""))

    @property
    def is_active(self) -> bool:
        """True when there is a non-empty message to display."""
        return bool(self.message.strip())

    def __str__(self) -> str:
        return f"Banner: {self.message!r}" if self.is_active else "Banner: (no active message)"


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------

def _fetch(url: str, headers: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT) -> Optional[bytes]:
    """
    Make a GET request and return raw bytes, or None on 204 No Content.

    Raises:
        urllib.error.HTTPError: for 4xx/5xx responses.
        urllib.error.URLError:  for network-level failures.
    """
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status == 204:
            return None
        return resp.read()


def _fetch_json(url: str, headers: Optional[dict] = None, timeout: int = DEFAULT_TIMEOUT):
    """Fetch JSON from *url* and parse it. Returns None if endpoint returns 204."""
    raw = _fetch(url, headers=headers, timeout=timeout)
    if raw is None:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class TDOTClient:
    """
    Client for the TDOT SmartWay public API.

    All methods perform a live HTTP request each time they are called.
    For polling use cases, implement caching at the call site.

    The API refreshes at the following approximate intervals (as observed
    from the SmartWay Angular app background monitor):
        Cameras        : every refresh interval (~60 s)
        Incidents      : every refresh interval
        Construction   : every refresh interval
        Weather        : every refresh interval
        Message Signs  : every refresh interval

    Parameters
    ----------
    api_base_url : str
        Override the default API base URL.
    api_key : str
        Override the default API key.
    timeout : int
        Request timeout in seconds. Default 20.
    """

    def __init__(
        self,
        api_base_url: str = API_BASE_URL,
        api_key: str = API_KEY,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._base = api_base_url.rstrip("/") + "/"
        self._headers = {"ApiKey": api_key}
        self._timeout = timeout

    def _get(self, endpoint: str):
        """Fetch *endpoint* relative to the base URL and return parsed JSON or None."""
        url = self._base + endpoint.lstrip("/")
        return _fetch_json(url, headers=self._headers, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        route: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        active_only: bool = True,
    ) -> list[Camera]:
        """
        Return all traffic cameras, optionally filtered.

        The API returns 666 cameras across Tennessee (Knoxville, Nashville,
        Memphis, Chattanooga).  Each camera provides a static thumbnail image
        plus HLS/RTMP/RTSP live video stream URLs.

        Parameters
        ----------
        route : str, optional
            Filter by route prefix, e.g. "I-40" or "I-24". Case-insensitive.
        jurisdiction : str, optional
            Filter by city: "Knoxville", "Nashville", "Memphis", "Chattanooga".
            Case-insensitive.
        active_only : bool
            When True (default) return only cameras with active=true.

        Returns
        -------
        list[Camera]
            Sorted by jurisdiction then title.

        Example
        -------
        >>> client = TDOTClient()
        >>> nashville_i40 = client.get_cameras(route="I-40", jurisdiction="Nashville")
        >>> print(nashville_i40[0].hls_url)
        """
        raw = self._get("RoadwayCameras")
        if not raw:
            return []
        cameras = [Camera.from_dict(c) for c in raw]
        if active_only:
            cameras = [c for c in cameras if c.is_active]
        if route:
            cameras = [c for c in cameras if c.route and route.upper() in c.route.upper()]
        if jurisdiction:
            cameras = [
                c for c in cameras
                if c.jurisdiction and jurisdiction.lower() in c.jurisdiction.lower()
            ]
        return sorted(cameras, key=lambda c: (c.jurisdiction or "", c.title))

    def get_camera(self, camera_id: int) -> Optional[Camera]:
        """
        Return a single camera by its numeric ID.

        Parameters
        ----------
        camera_id : int
            The camera ``id`` field value (e.g. 3165).

        Returns
        -------
        Camera or None
            None when the camera ID does not exist.

        Example
        -------
        >>> cam = TDOTClient().get_camera(3165)
        >>> print(cam.thumbnail_url)
        """
        raw = self._get(f"RoadwayCameras/{camera_id}")
        if not raw:
            return None
        return Camera.from_dict(raw)

    def get_thumbnail(self, camera: Camera) -> Optional[bytes]:
        """
        Download the current snapshot image for *camera* as raw PNG bytes.

        The thumbnail CDN (tnsnapshots.com) serves live-updated snapshots.
        Images are typically ~120 KB PNG files at 640×480 or similar resolution.

        Parameters
        ----------
        camera : Camera
            A Camera instance with a non-None thumbnail_url.

        Returns
        -------
        bytes or None
            Raw PNG image bytes, or None if the URL is unavailable.

        Example
        -------
        >>> cam = TDOTClient().get_camera(3165)
        >>> with open("snapshot.png", "wb") as f:
        ...     f.write(TDOTClient().get_thumbnail(cam))
        """
        if not camera.thumbnail_url:
            return None
        return _fetch(camera.thumbnail_url, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------

    def get_incidents(self) -> list[RoadwayEvent]:
        """
        Return all active traffic incidents.

        Includes crashes, congestion, lane blockages, and special event impacts.
        Events with ``thp_reported=True`` were reported by the Tennessee Highway Patrol.

        Returns
        -------
        list[RoadwayEvent]
            Active incidents, typically 5–30 items.

        Example
        -------
        >>> for inc in TDOTClient().get_incidents():
        ...     print(inc.event_subtype_desc, "—", inc.description[:60])
        """
        raw = self._get("RoadwayIncidents")
        if not raw:
            return []
        return [RoadwayEvent.from_dict(e) for e in raw]

    # ------------------------------------------------------------------
    # Construction / Roadway Operations
    # ------------------------------------------------------------------

    def get_construction(self) -> list[RoadwayEvent]:
        """
        Return active construction and roadway operations events.

        Covers lane reductions, flagging operations, bridge work, and other
        scheduled roadway maintenance. Typically 50–100 active projects.

        Returns
        -------
        list[RoadwayEvent]

        Example
        -------
        >>> for op in TDOTClient().get_construction():
        ...     if op.has_closure:
        ...         print("[CLOSED]", op.description[:80])
        """
        raw = self._get("RoadwayOperations")
        if not raw:
            return []
        return [RoadwayEvent.from_dict(e) for e in raw]

    # ------------------------------------------------------------------
    # Severe Impacts
    # ------------------------------------------------------------------

    def get_severe_impacts(self) -> list[RoadwayEvent]:
        """
        Return events classified as severe impact.

        These are high-priority events such as bridge closures, major crashes,
        or extended full-road closures. Typically 0–5 items at any given time.

        Returns
        -------
        list[RoadwayEvent]

        Example
        -------
        >>> for ev in TDOTClient().get_severe_impacts():
        ...     print("[SEVERE]", ev.event_subtype_desc, ev.description[:80])
        """
        raw = self._get("RoadwaySevereImpact")
        if not raw:
            return []
        return [RoadwayEvent.from_dict(e) for e in raw]

    # ------------------------------------------------------------------
    # Weather Events
    # ------------------------------------------------------------------

    def get_weather_events(self) -> list[RoadwayEvent]:
        """
        Return active weather-related roadway events.

        Covers fog, ice, flooding, debris on roadway, and weather-related
        closures. May return empty list during clear conditions (HTTP 204).

        Returns
        -------
        list[RoadwayEvent]

        Example
        -------
        >>> for ev in TDOTClient().get_weather_events():
        ...     print(ev.event_subtype_desc, "—", ev.description[:60])
        """
        raw = self._get("RoadwayWeather")
        if not raw:
            return []
        return [RoadwayEvent.from_dict(e) for e in raw]

    # ------------------------------------------------------------------
    # Special Events
    # ------------------------------------------------------------------

    def get_special_events(self) -> list[RoadwayEvent]:
        """
        Return roadway special events (concerts, sporting events, etc.).

        May return an empty list (HTTP 204) when no special events are active.

        Returns
        -------
        list[RoadwayEvent]
        """
        raw = self._get("RoadwaySpecialEvents")
        if not raw:
            return []
        return [RoadwayEvent.from_dict(e) for e in raw]

    # ------------------------------------------------------------------
    # Message Signs (DMS)
    # ------------------------------------------------------------------

    def get_message_signs(self, active_only: bool = False) -> list[MessageSign]:
        """
        Return all Dynamic Message Signs (DMS) and their current display text.

        Tennessee operates 243 DMS across the state highway network. Signs
        with an empty ``message`` field are currently blank. Signs with
        messages use pipe (``|``) as a line separator.

        Parameters
        ----------
        active_only : bool
            When True, return only signs currently displaying a message.

        Returns
        -------
        list[MessageSign]
            243 signs total; subset when active_only=True.

        Example
        -------
        >>> for sign in TDOTClient().get_message_signs(active_only=True):
        ...     print(sign.title, ":", sign.message_lines)
        """
        raw = self._get("RoadwayMessageSigns")
        if not raw:
            return []
        signs = [MessageSign.from_dict(s) for s in raw]
        if active_only:
            signs = [s for s in signs if not s.is_blank]
        return signs

    # ------------------------------------------------------------------
    # Rest Areas
    # ------------------------------------------------------------------

    def get_rest_areas(self, open_only: bool = False) -> list[RestArea]:
        """
        Return all Tennessee highway rest areas and welcome centers.

        Tennessee has 35 rest areas/welcome centers along its Interstate
        and limited-access highway system.

        Parameters
        ----------
        open_only : bool
            When True, return only currently open facilities.

        Returns
        -------
        list[RestArea]

        Example
        -------
        >>> for ra in TDOTClient().get_rest_areas(open_only=True):
        ...     print(ra.display_name, ra.route)
        """
        raw = self._get("RestAreas")
        if not raw:
            return []
        areas = [RestArea.from_dict(r) for r in raw]
        if open_only:
            areas = [a for a in areas if a.is_open]
        return areas

    # ------------------------------------------------------------------
    # Banner Message
    # ------------------------------------------------------------------

    def get_banner(self) -> Optional[BannerMessage]:
        """
        Return the current system-wide SmartWay banner message, if any.

        TDOT uses this to broadcast statewide alerts, major event warnings,
        or emergency information across the SmartWay website.

        Returns
        -------
        BannerMessage or None
            None if the endpoint fails; a BannerMessage with empty string
            when no alert is active.

        Example
        -------
        >>> banner = TDOTClient().get_banner()
        >>> if banner and banner.is_active:
        ...     print("ALERT:", banner.message)
        """
        raw = self._get("SmartWayBanner")
        if not raw:
            return None
        items = raw if isinstance(raw, list) else [raw]
        if not items:
            return None
        return BannerMessage.from_dict(items[0])

    # ------------------------------------------------------------------
    # ArcGIS / Supplemental Endpoints
    # ------------------------------------------------------------------

    def get_waze_alerts(self) -> list[dict]:
        """
        Return Waze crowd-sourced incident data overlaid on the SmartWay map.

        This calls the TDOT ArcGIS REST service that proxies Waze data.
        No API key required. Returns raw ArcGIS feature dicts.

        Returns
        -------
        list[dict]
            Each dict has ``attributes`` (Waze alert fields) and optionally
            ``geometry`` (point coordinates).

        Example
        -------
        >>> alerts = TDOTClient().get_waze_alerts()
        >>> for a in alerts:
        ...     print(a["attributes"].get("type"), a["attributes"].get("subtype"))
        """
        raw = _fetch_json(WAZE_URL, timeout=self._timeout)
        if not raw:
            return []
        return raw.get("features", [])

    def get_county_polygons(
        self,
        county_name: Optional[str] = None,
        geometry_precision: int = 4,
    ) -> dict:
        """
        Return Tennessee county boundary GeoJSON-compatible data from ArcGIS.

        Used by the SmartWay map to highlight county boundaries.

        Parameters
        ----------
        county_name : str, optional
            Filter to a specific county, e.g. "Davidson" or "Shelby".
            When None, returns all 95 counties.
        geometry_precision : int
            Decimal precision for coordinate values. Default 4.

        Returns
        -------
        dict
            Raw ArcGIS JSON response with ``features`` list and ``fields`` metadata.

        Example
        -------
        >>> result = TDOTClient().get_county_polygons(county_name="Davidson")
        >>> print(len(result["features"]), "features")
        """
        params: dict = {
            "returnGeometry": "true",
            "geometryPrecision": str(geometry_precision),
            "outSR": "4326",
            "outFields": "*",
            "f": "json",
        }
        if county_name:
            params["where"] = f"CTNAME='{county_name}'"
        else:
            params["where"] = "1=1"

        query_string = urllib.parse.urlencode(params)
        url = f"{COUNTY_POLYGON_URL}query?{query_string}"
        raw = _fetch_json(url, timeout=self._timeout)
        return raw or {}

    # ------------------------------------------------------------------
    # Convenience / Aggregation
    # ------------------------------------------------------------------

    def get_all_events(self) -> dict[str, list[RoadwayEvent]]:
        """
        Fetch all event types in a single call and return a categorised dict.

        Returns
        -------
        dict with keys:
            "incidents"    : list[RoadwayEvent]
            "construction" : list[RoadwayEvent]
            "severe"       : list[RoadwayEvent]
            "weather"      : list[RoadwayEvent]
            "special"      : list[RoadwayEvent]

        Example
        -------
        >>> events = TDOTClient().get_all_events()
        >>> print(f"{len(events['incidents'])} incidents, "
        ...       f"{len(events['construction'])} construction zones")
        """
        return {
            "incidents": self.get_incidents(),
            "construction": self.get_construction(),
            "severe": self.get_severe_impacts(),
            "weather": self.get_weather_events(),
            "special": self.get_special_events(),
        }

    def search_cameras(self, query: str) -> list[Camera]:
        """
        Search cameras by title, description, route, or jurisdiction.

        Parameters
        ----------
        query : str
            Case-insensitive substring to match against camera text fields.

        Returns
        -------
        list[Camera]

        Example
        -------
        >>> cams = TDOTClient().search_cameras("downtown Nashville")
        """
        q = query.lower()
        return [
            c for c in self.get_cameras(active_only=False)
            if q in (c.title or "").lower()
            or q in (c.description or "").lower()
            or q in (c.route or "").lower()
            or q in (c.jurisdiction or "").lower()
        ]


# ---------------------------------------------------------------------------
# Command-Line Interface
# ---------------------------------------------------------------------------

def _print_cameras(cameras: list[Camera], verbose: bool = False) -> None:
    print(f"\n{'='*70}")
    print(f"  TDOT Traffic Cameras  ({len(cameras)} results)")
    print(f"{'='*70}")
    for c in cameras:
        status = "ACTIVE  " if c.is_active else "INACTIVE"
        print(
            f"[{status}] ID:{c.id:<6} {c.jurisdiction or '?':12} "
            f"{(c.route or '?'):15} MM:{(c.mile_marker or '?'):8} "
            f"{c.title}"
        )
        if verbose:
            print(f"         Thumb  : {c.thumbnail_url}")
            print(f"         HLS    : {c.hls_url}")
            print(f"         RTSP   : {c.rtsp_url}")
            print()


def _print_events(events: list[RoadwayEvent], label: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {label}  ({len(events)} active)")
    print(f"{'='*70}")
    for e in events:
        closure = " [CLOSURE]" if e.has_closure else ""
        severe = " [SEVERE]" if e.is_severe else ""
        loc = e.primary_location
        county = f" | {loc.county_name}" if loc and loc.county_name else ""
        print(f"[{e.event_type_name:12}]{closure}{severe}{county}")
        print(f"  {e.event_subtype_desc} — {e.description[:100]}")
        if e.current_activity:
            print(f"  Activity: {e.current_activity[:100]}")
        print()


def _print_signs(signs: list[MessageSign]) -> None:
    print(f"\n{'='*70}")
    print(f"  Dynamic Message Signs  ({len(signs)} results)")
    print(f"{'='*70}")
    for s in signs:
        content = " | ".join(s.message_lines) if s.message else "(blank)"
        print(f"Sign {s.id:>5}  {s.route:20}  {s.title}")
        if s.message:
            print(f"         >> {content}")


def _print_rest_areas(areas: list[RestArea]) -> None:
    print(f"\n{'='*70}")
    print(f"  Rest Areas  ({len(areas)} results)")
    print(f"{'='*70}")
    for a in areas:
        status = "OPEN  " if a.is_open else "CLOSED"
        print(f"[{status}] ID:{a.id:<4} MM:{a.mile:<6.0f} {a.route:25} {a.display_name}")


def _run_demo(client: TDOTClient) -> None:
    """Run a comprehensive demo showing all API endpoints."""
    print("\n" + "="*70)
    print("  TDOT SmartWay API — Live Demo")
    print("="*70)

    # Banner
    banner = client.get_banner()
    print(f"\nBanner: {banner}")

    # Camera summary
    cameras = client.get_cameras()
    by_jur: dict[str, int] = {}
    for c in cameras:
        jur = c.jurisdiction or "Unknown"
        by_jur[jur] = by_jur.get(jur, 0) + 1
    print(f"\nCameras: {len(cameras)} active")
    for jur, count in sorted(by_jur.items()):
        print(f"  {jur:15}: {count} cameras")

    # Show first camera detail
    if cameras:
        c = cameras[0]
        print(f"\nSample camera:\n  {c}")
        print(f"  Thumbnail : {c.thumbnail_url}")
        print(f"  HLS       : {c.hls_url}")
        print(f"  RTMP      : {c.rtmp_url}")
        print(f"  RTSP      : {c.rtsp_url}")
        print(f"  Stream ID : {c.stream_id}")

    # Events summary
    events = client.get_all_events()
    print(f"\nLive Events:")
    for key, ev_list in events.items():
        print(f"  {key:15}: {len(ev_list)}")

    # Show first incident
    if events["incidents"]:
        ev = events["incidents"][0]
        print(f"\nSample incident:\n  {ev}")
        if ev.primary_location:
            pt = ev.primary_location.point
            if pt:
                print(f"  Location: {pt}")

    # Message signs
    active_signs = client.get_message_signs(active_only=True)
    print(f"\nMessage Signs: {len(active_signs)} with active messages")
    for sign in active_signs[:3]:
        print(f"  {sign}")

    # Rest areas
    open_areas = client.get_rest_areas(open_only=True)
    print(f"\nRest Areas: {len(open_areas)} open")
    for area in open_areas[:3]:
        print(f"  {area}")

    print("\nDemo complete.")


def main() -> None:
    """Entry point for the CLI."""
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    command = args[0].lower()
    client = TDOTClient()

    try:
        if command == "cameras":
            route = None
            jurisdiction = None
            verbose = False
            i = 1
            while i < len(args):
                if args[i] == "--route" and i + 1 < len(args):
                    route = args[i + 1]
                    i += 2
                elif args[i] == "--jurisdiction" and i + 1 < len(args):
                    jurisdiction = args[i + 1]
                    i += 2
                elif args[i] == "--verbose":
                    verbose = True
                    i += 1
                else:
                    i += 1
            cams = client.get_cameras(route=route, jurisdiction=jurisdiction)
            _print_cameras(cams, verbose=verbose)

        elif command == "camera":
            if len(args) < 2:
                print("Usage: tdot_client.py camera <id>")
                sys.exit(1)
            cam = client.get_camera(int(args[1]))
            if cam:
                print(cam)
                print(f"  Thumbnail : {cam.thumbnail_url}")
                print(f"  HLS       : {cam.hls_url}")
                print(f"  RTMP      : {cam.rtmp_url}")
                print(f"  RTSP      : {cam.rtsp_url}")
                print(f"  CLSPS     : {cam.clsps_url}")
                print(f"  Stream ID : {cam.stream_id}")
            else:
                print(f"Camera {args[1]} not found.")

        elif command == "incidents":
            _print_events(client.get_incidents(), "Active Incidents")

        elif command == "construction":
            _print_events(client.get_construction(), "Construction / Operations")

        elif command == "severe":
            _print_events(client.get_severe_impacts(), "Severe Impact Events")

        elif command == "weather":
            _print_events(client.get_weather_events(), "Weather Events")

        elif command == "signs":
            active_only = "--active" in args
            _print_signs(client.get_message_signs(active_only=active_only))

        elif command == "restareas":
            _print_rest_areas(client.get_rest_areas())

        elif command == "banner":
            print(client.get_banner())

        elif command == "demo":
            _run_demo(client)

        elif command == "search":
            if len(args) < 2:
                print("Usage: tdot_client.py search <query>")
                sys.exit(1)
            q = " ".join(args[1:])
            _print_cameras(client.search_cameras(q), verbose=True)

        else:
            print(f"Unknown command: {command!r}")
            print("Commands: cameras, camera, incidents, construction, severe,")
            print("          weather, signs, restareas, banner, demo, search")
            sys.exit(1)

    except urllib.error.HTTPError as exc:
        print(f"HTTP Error {exc.code}: {exc.reason} — {exc.url}")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
