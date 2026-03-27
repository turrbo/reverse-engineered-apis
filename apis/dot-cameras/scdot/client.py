"""
511SC / SCDOT Traffic Information Client
=========================================
Python client for the South Carolina Department of Transportation (SCDOT)
511SC traveler information system, powered by the Iteris ATIS platform.

All endpoints are public and unauthenticated. No API key is required.

Data Sources
------------
- CDN GeoJSON feeds: https://sc.cdn.iteris-atis.com/geojson/icons/metadata/
- Aggregator API:    https://aggregator.iteris-atis.com/aggregator/services/layers/
- News API:          https://aggregator.iteris-sc511.net/aggregator/services/news/
- Snapshot CDN:      https://scdotsnap.us-east-1.skyvdn.com/thumbs/<name>.flv.png
- HLS streams:       https://s18.us-east-1.skyvdn.com:443/rtplive/<name>/playlist.m3u8

Usage
-----
    python scdot_client.py                    # Run the CLI demo
    python scdot_client.py --cameras          # List all cameras
    python scdot_client.py --incidents        # Show active incidents
    python scdot_client.py --dms              # Show dynamic message signs
    python scdot_client.py --rest-areas       # Show rest areas
    python scdot_client.py --evac-points      # Show evacuation points
    python scdot_client.py --news             # Show travel alerts/news
    python scdot_client.py --camera 50001     # Single camera info
    python scdot_client.py --jurisdiction "Columbia"  # Filter by jurisdiction
    python scdot_client.py --save-snapshot 50001 camera.png  # Download snapshot

Author: Reverse-engineered from https://www.511sc.org (Iteris ATIS v1.2.6)
License: Public domain — these are publicly-funded government data feeds.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------

CDN_BASE = "https://sc.cdn.iteris-atis.com/geojson/icons/metadata"
AGGREGATOR_BASE = "https://aggregator.iteris-atis.com/aggregator/services/layers/group/scdot/current"
NEWS_BASE = "https://aggregator.iteris-sc511.net/aggregator/services/news/group/scdot/current"
SNAPSHOT_CDN = "https://scdotsnap.us-east-1.skyvdn.com/thumbs"
HLS_BASE = "https://s18.us-east-1.skyvdn.com:443/rtplive"
RTSP_BASE = "rtsp://s18.us-east-1.skyvdn.com:554/rtplive"
RTMP_BASE = "rtmp://s18.us-east-1.skyvdn.com:1935/rtplive"

# Mapbox public token (embedded in site JS — read-only map rendering only)
MAPBOX_TOKEN = "<MAPBOX_PUBLIC_TOKEN>"

DEFAULT_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """
    A South Carolina DOT traffic camera.

    Streams are served by SkyVDN (CDN partner).
    The ``image_url`` endpoint serves a live JPEG/PNG snapshot updated
    approximately every 10 seconds.  The ``ios_url`` / ``https_url`` endpoints
    serve HLS (M3U8) playlists suitable for any HLS-capable player.
    """
    id: str                     # UUID, e.g. "e71ff390-d2a0-11e6-8996-0123456789ab"
    name: str                   # Numeric label, e.g. "50001"
    description: str            # Human-readable location, e.g. "US 501 N @ 16th Ave"
    route: str                  # Road, e.g. "US 501"
    direction: str              # NB / SB / EB / WB / Median
    mrm: Optional[float]        # Mile reference marker
    jurisdiction: str           # City/region, e.g. "Myrtle Beach"
    latitude: float
    longitude: float
    active: bool                # Is the camera currently operational?
    problem_stream: bool        # True if the stream is known to be degraded

    # Stream URLs
    image_url: str              # Static snapshot PNG (live, ~10s refresh)
    https_url: str              # HLS playlist (HTTPS) — best for web/mobile
    ios_url: str                # HLS playlist (iOS/Safari)
    rtsp_url: str               # RTSP stream — VLC, FFmpeg
    rtmp_url: str               # RTMP stream — legacy players
    preroll_url: str            # Pre-roll HLS segment
    clsps_url: str              # Custom SkyVDN protocol

    @property
    def snapshot_url(self) -> str:
        """Direct URL to the live camera snapshot image."""
        return f"{SNAPSHOT_CDN}/{self.name}.flv.png"

    @property
    def hls_url(self) -> str:
        """HLS M3U8 playlist URL (preferred for most players)."""
        return f"{HLS_BASE}/{self.name}/playlist.m3u8"

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "route": self.route,
            "direction": self.direction,
            "mrm": self.mrm,
            "jurisdiction": self.jurisdiction,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "active": self.active,
            "problem_stream": self.problem_stream,
            "image_url": self.image_url,
            "https_url": self.https_url,
            "ios_url": self.ios_url,
            "rtsp_url": self.rtsp_url,
            "rtmp_url": self.rtmp_url,
            "hls_url": self.hls_url,
            "snapshot_url": self.snapshot_url,
        }


@dataclass
class Incident:
    """
    A traffic incident (crash, hazard, road work, etc.) on a South Carolina highway.
    """
    event_id: str               # e.g. "event_1119833"
    name: str                   # Internal ID, e.g. "D6-032726-08"
    route: str                  # e.g. "I-95"
    direction: str              # N / S / E / W
    mrm: Optional[str]          # Mile reference marker string
    headline: str               # Incident type, e.g. "Crash"
    road_type: str              # e.g. "Interstates/Freeways"
    cross_street: str           # Reference intersection
    location_description: str   # Full location text
    icon: str                   # Map icon type, e.g. "event"
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "route": self.route,
            "direction": self.direction,
            "mrm": self.mrm,
            "headline": self.headline,
            "road_type": self.road_type,
            "cross_street": self.cross_street,
            "location_description": self.location_description,
            "icon": self.icon,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class DynamicMessageSign:
    """
    A Dynamic Message Sign (DMS) or Variable Speed Limit (VSL) sign.
    These are overhead highway signs that display real-time messages.
    """
    event_id: str               # e.g. "dms_DMS_101"
    dms_name: str               # Sign identifier number
    route: str                  # e.g. "I-95"
    direction: str              # N / S / E / W
    mrm: str                    # Mile reference or "unavailable"
    location_description: str
    road_type: str
    cross_street: str
    icon: str                   # "dms" or "vsl"
    county: str
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "dms_name": self.dms_name,
            "route": self.route,
            "direction": self.direction,
            "mrm": self.mrm,
            "location_description": self.location_description,
            "road_type": self.road_type,
            "cross_street": self.cross_street,
            "icon": self.icon,
            "county": self.county,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class TrafficCongestion:
    """
    A congestion / slow-traffic event segment.
    """
    event_id: str
    route: str
    direction: str
    cross_street: str
    location_description: str
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "route": self.route,
            "direction": self.direction,
            "cross_street": self.cross_street,
            "location_description": self.location_description,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class RestArea:
    """
    A South Carolina DOT rest area or welcome center.
    """
    m_uuid: int                 # Internal unique ID
    facility_type: str          # "Rest Area" or "Welcome Center"
    title: str                  # Full descriptive name
    route: str
    direction: str
    mrm: str
    location: str               # City/town
    description: str            # Parking capacity info
    status: str                 # "open" / "closed"
    seasonal: str               # "year-round" or season
    amenities: List[str]        # ["restroom", "picnic", "vending", ...]
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "m_uuid": self.m_uuid,
            "facility_type": self.facility_type,
            "title": self.title,
            "route": self.route,
            "direction": self.direction,
            "mrm": self.mrm,
            "location": self.location,
            "description": self.description,
            "status": self.status,
            "seasonal": self.seasonal,
            "amenities": self.amenities,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class EvacuationPoint:
    """
    A hurricane evacuation point / shelter location.
    """
    m_uuid: int
    facility_type: str          # "Evacuation Point"
    content_id: int
    title: str
    message: str                # Evacuation instructions
    description: str            # Detailed route info
    latitude: float
    longitude: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "m_uuid": self.m_uuid,
            "facility_type": self.facility_type,
            "content_id": self.content_id,
            "title": self.title,
            "message": self.message,
            "description": self.description,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass
class NewsItem:
    """
    A travel alert, general information item, or special event notice.
    """
    category: str               # "travel_alerts" | "general_information" | "high_priority" | "special_events"
    content: Dict[str, Any]     # Raw item content (structure varies by type)

    def to_dict(self) -> Dict[str, Any]:
        return {"category": self.category, "content": self.content}


@dataclass
class NewsResponse:
    """
    The full news/alerts response from the aggregator API.
    """
    general_information: List[Dict[str, Any]] = field(default_factory=list)
    travel_alerts: List[Dict[str, Any]] = field(default_factory=list)
    high_priority: List[Dict[str, Any]] = field(default_factory=list)
    special_events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def all_items(self) -> List[NewsItem]:
        """Return all news items across all categories."""
        items: List[NewsItem] = []
        for cat, entries in [
            ("general_information", self.general_information),
            ("travel_alerts", self.travel_alerts),
            ("high_priority", self.high_priority),
            ("special_events", self.special_events),
        ]:
            for entry in entries:
                items.append(NewsItem(category=cat, content=entry))
        return items

    @property
    def is_empty(self) -> bool:
        return not any([
            self.general_information,
            self.travel_alerts,
            self.high_priority,
            self.special_events,
        ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "general_information": self.general_information,
            "travel_alerts": self.travel_alerts,
            "high_priority": self.high_priority,
            "special_events": self.special_events,
        }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """
    Fetch a URL and parse the JSON response body.

    Parameters
    ----------
    url:
        Full URL to GET.
    timeout:
        Socket timeout in seconds.

    Returns
    -------
    Parsed JSON object (dict, list, etc.).

    Raises
    ------
    urllib.error.HTTPError
        If the server returns a non-2xx status.
    urllib.error.URLError
        If the connection fails (DNS, network, etc.).
    json.JSONDecodeError
        If the body is not valid JSON.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "511SC-Python-Client/1.0 (public traffic data)",
            "Accept": "application/json, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return json.loads(body)


def _fetch_binary(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """
    Fetch a URL and return the raw response bytes (e.g. for images).

    Parameters
    ----------
    url:
        Full URL to GET.
    timeout:
        Socket timeout in seconds.

    Returns
    -------
    Raw response bytes.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "511SC-Python-Client/1.0 (public traffic data)",
            "Accept": "image/*, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


# ---------------------------------------------------------------------------
# Parsers — GeoJSON feature → dataclass
# ---------------------------------------------------------------------------

def _parse_camera(feature: Dict[str, Any]) -> Camera:
    """Parse a single GeoJSON camera feature into a Camera dataclass."""
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    lon, lat = float(coords[0]), float(coords[1])

    mrm_raw = props.get("mrm")
    try:
        mrm = float(mrm_raw) if mrm_raw is not None else None
    except (TypeError, ValueError):
        mrm = None

    return Camera(
        id=props.get("id", ""),
        name=str(props.get("name", "")),
        description=props.get("description", ""),
        route=props.get("route", ""),
        direction=props.get("direction", ""),
        mrm=mrm,
        jurisdiction=props.get("jurisdiction", ""),
        latitude=lat,
        longitude=lon,
        active=bool(props.get("active", True)),
        problem_stream=bool(props.get("problem_stream", False)),
        image_url=props.get("image_url", ""),
        https_url=props.get("https_url", ""),
        ios_url=props.get("ios_url", ""),
        rtsp_url=props.get("rtsp_url", ""),
        rtmp_url=props.get("rtmp_url", ""),
        preroll_url=props.get("preroll_url", ""),
        clsps_url=props.get("clsps_url", ""),
    )


def _parse_incident(feature: Dict[str, Any]) -> Incident:
    """Parse a single GeoJSON incident feature into an Incident dataclass."""
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    lon, lat = float(coords[0]), float(coords[1])

    return Incident(
        event_id=props.get("event_id", feature.get("id", "")),
        name=props.get("name", ""),
        route=props.get("route", ""),
        direction=props.get("dir", ""),
        mrm=props.get("mrm"),
        headline=props.get("headline", ""),
        road_type=props.get("road_type", ""),
        cross_street=props.get("cross_street", ""),
        location_description=props.get("location_description", ""),
        icon=props.get("icon", ""),
        latitude=lat,
        longitude=lon,
    )


def _parse_dms(feature: Dict[str, Any]) -> DynamicMessageSign:
    """Parse a single GeoJSON DMS feature into a DynamicMessageSign dataclass."""
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    lon, lat = float(coords[0]), float(coords[1])

    return DynamicMessageSign(
        event_id=props.get("event_id", feature.get("id", "")),
        dms_name=str(props.get("DMS_name", "")),
        route=props.get("route", ""),
        direction=props.get("dir", ""),
        mrm=str(props.get("mrm", "")),
        location_description=props.get("location_description", ""),
        road_type=props.get("road_type", ""),
        cross_street=props.get("cross_street", ""),
        icon=props.get("icon", "dms"),
        county=props.get("county", ""),
        latitude=lat,
        longitude=lon,
    )


def _parse_congestion(feature: Dict[str, Any]) -> TrafficCongestion:
    """Parse a single GeoJSON congestion feature into a TrafficCongestion dataclass."""
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    lon, lat = float(coords[0]), float(coords[1])

    return TrafficCongestion(
        event_id=props.get("event_id", feature.get("id", "")),
        route=props.get("route", ""),
        direction=props.get("dir", ""),
        cross_street=props.get("cross_street", ""),
        location_description=props.get("location_description", ""),
        latitude=lat,
        longitude=lon,
    )


def _parse_rest_area(feature: Dict[str, Any]) -> RestArea:
    """Parse a single aggregator rest area/welcome center feature."""
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    lon, lat = float(coords[0]), float(coords[1])

    amenities_raw = props.get("amenities", [])
    if isinstance(amenities_raw, list):
        amenities = [str(a) for a in amenities_raw]
    else:
        amenities = []

    return RestArea(
        m_uuid=int(props.get("m_uuid", 0)),
        facility_type=props.get("facility_type", ""),
        title=props.get("title", ""),
        route=props.get("route", ""),
        direction=props.get("dir", ""),
        mrm=str(props.get("mrm", "")),
        location=props.get("location", ""),
        description=props.get("description", ""),
        status=props.get("status", ""),
        seasonal=props.get("seasonal", ""),
        amenities=amenities,
        latitude=lat,
        longitude=lon,
    )


def _parse_evac_point(feature: Dict[str, Any]) -> EvacuationPoint:
    """Parse a single aggregator evacuation point feature."""
    props = feature.get("properties", {})
    coords = feature["geometry"]["coordinates"]
    lon, lat = float(coords[0]), float(coords[1])

    return EvacuationPoint(
        m_uuid=int(props.get("m_uuid", 0)),
        facility_type=props.get("facility_type", "Evacuation Point"),
        content_id=int(props.get("content_id", 0)),
        title=props.get("title", ""),
        message=props.get("message", ""),
        description=props.get("description", ""),
        latitude=lat,
        longitude=lon,
    )


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class SCDOTClient:
    """
    Client for the South Carolina DOT 511SC traveler information system.

    All methods make live HTTP requests to the public Iteris ATIS endpoints
    that power https://www.511sc.org.  No authentication is required.

    Example
    -------
    ::

        client = SCDOTClient()

        # Get all cameras
        cameras = client.get_cameras()
        for cam in cameras:
            print(cam.name, cam.description, cam.snapshot_url)

        # Filter by jurisdiction
        columbia_cams = client.get_cameras(jurisdiction="Columbia")

        # Get a single camera by name
        cam = client.get_camera("50001")
        print(cam.hls_url)

        # Download a snapshot
        png_bytes = client.download_snapshot("50001")
        with open("camera.png", "wb") as f:
            f.write(png_bytes)

        # Get active incidents
        incidents = client.get_incidents()
        for inc in incidents:
            print(f"{inc.route} {inc.direction}: {inc.headline} — {inc.location_description}")

        # Get rest areas
        rest_areas = client.get_rest_areas()

        # Get news/alerts
        news = client.get_news()
        print(f"Travel alerts: {len(news.travel_alerts)}")
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """
        Parameters
        ----------
        timeout:
            HTTP request timeout in seconds (default 30).
        """
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Camera methods
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        active_only: bool = False,
        jurisdiction: Optional[str] = None,
        route: Optional[str] = None,
    ) -> List[Camera]:
        """
        Fetch all traffic cameras in South Carolina.

        Parameters
        ----------
        active_only:
            If True, only return cameras where ``active == True``.
        jurisdiction:
            Case-insensitive filter by jurisdiction name, e.g. "Columbia",
            "Myrtle Beach", "Charleston", "Greenville", "Rock Hill", "Florence",
            "Charleston Beaches".
        route:
            Case-insensitive filter by route, e.g. "I-95", "US 501", "I-26".

        Returns
        -------
        List of Camera dataclasses, sorted by jurisdiction then camera name.
        """
        url = f"{CDN_BASE}/icons.cameras.geojson"
        data = _fetch_json(url, self.timeout)
        cameras: List[Camera] = []
        for feature in data.get("features", []):
            try:
                cam = _parse_camera(feature)
            except (KeyError, TypeError, ValueError):
                continue  # Skip malformed entries
            if active_only and not cam.active:
                continue
            if jurisdiction and cam.jurisdiction.lower() != jurisdiction.lower():
                continue
            if route and route.lower() not in cam.route.lower():
                continue
            cameras.append(cam)
        cameras.sort(key=lambda c: (c.jurisdiction, c.name))
        return cameras

    def get_camera(self, name: str) -> Optional[Camera]:
        """
        Fetch a single camera by its numeric name/ID (e.g. "50001").

        Parameters
        ----------
        name:
            Camera name string (the 5-digit numeric label).

        Returns
        -------
        Camera dataclass, or None if not found.
        """
        cameras = self.get_cameras()
        for cam in cameras:
            if cam.name == str(name):
                return cam
        return None

    def get_camera_by_id(self, camera_id: str) -> Optional[Camera]:
        """
        Fetch a single camera by its UUID.

        Parameters
        ----------
        camera_id:
            UUID string, e.g. "e71ff390-d2a0-11e6-8996-0123456789ab".

        Returns
        -------
        Camera dataclass, or None if not found.
        """
        cameras = self.get_cameras()
        for cam in cameras:
            if cam.id == camera_id:
                return cam
        return None

    def download_snapshot(self, camera_name: str) -> bytes:
        """
        Download the live snapshot image for a camera.

        The snapshot CDN refreshes approximately every 10 seconds.
        Images are served as PNG from ``scdotsnap.us-east-1.skyvdn.com``.

        Parameters
        ----------
        camera_name:
            Camera name string, e.g. "50001".

        Returns
        -------
        Raw PNG image bytes.

        Raises
        ------
        urllib.error.HTTPError
            If the camera doesn't exist or the snapshot is unavailable.
        """
        url = f"{SNAPSHOT_CDN}/{camera_name}.flv.png"
        return _fetch_binary(url, self.timeout)

    def get_jurisdictions(self) -> List[str]:
        """
        Return a sorted list of all unique jurisdiction names.

        Returns
        -------
        List of jurisdiction name strings.
        """
        cameras = self.get_cameras()
        return sorted({cam.jurisdiction for cam in cameras if cam.jurisdiction})

    # ------------------------------------------------------------------
    # Incident methods
    # ------------------------------------------------------------------

    def get_incidents(
        self,
        route: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> List[Incident]:
        """
        Fetch all active traffic incidents (crashes, hazards, road work).

        Data is sourced from the Iteris ATIS incident feed and is typically
        updated in real time by SCDOT traffic management centers.

        Parameters
        ----------
        route:
            Case-insensitive filter by route name, e.g. "I-95", "I-26".
        direction:
            Filter by travel direction: "N", "S", "E", "W".

        Returns
        -------
        List of Incident dataclasses.
        """
        url = f"{CDN_BASE}/icons.incident.geojson"
        data = _fetch_json(url, self.timeout)
        incidents: List[Incident] = []
        for feature in data.get("features", []):
            try:
                inc = _parse_incident(feature)
            except (KeyError, TypeError, ValueError):
                continue
            if route and route.lower() not in inc.route.lower():
                continue
            if direction and inc.direction.upper() != direction.upper():
                continue
            incidents.append(inc)
        return incidents

    # ------------------------------------------------------------------
    # DMS / Variable Speed Limit methods
    # ------------------------------------------------------------------

    def get_dynamic_message_signs(
        self,
        icon_type: Optional[str] = None,
    ) -> List[DynamicMessageSign]:
        """
        Fetch all Dynamic Message Signs (DMS) and Variable Speed Limit (VSL) signs.

        Parameters
        ----------
        icon_type:
            Filter by sign type: "dms" for message signs, "vsl" for speed signs.

        Returns
        -------
        List of DynamicMessageSign dataclasses.
        """
        url = f"{CDN_BASE}/icons.dms.geojson"
        data = _fetch_json(url, self.timeout)
        signs: List[DynamicMessageSign] = []
        for feature in data.get("features", []):
            try:
                sign = _parse_dms(feature)
            except (KeyError, TypeError, ValueError):
                continue
            if icon_type and sign.icon.lower() != icon_type.lower():
                continue
            signs.append(sign)
        return signs

    # ------------------------------------------------------------------
    # Congestion / slow traffic methods
    # ------------------------------------------------------------------

    def get_congestion(
        self,
        route: Optional[str] = None,
    ) -> List[TrafficCongestion]:
        """
        Fetch current traffic congestion / slow-traffic zones.

        Parameters
        ----------
        route:
            Case-insensitive filter by route name.

        Returns
        -------
        List of TrafficCongestion dataclasses.
        """
        url = f"{CDN_BASE}/icons.congestion.geojson"
        data = _fetch_json(url, self.timeout)
        events: List[TrafficCongestion] = []
        for feature in data.get("features", []):
            try:
                evt = _parse_congestion(feature)
            except (KeyError, TypeError, ValueError):
                continue
            if route and route.lower() not in evt.route.lower():
                continue
            events.append(evt)
        return events

    # ------------------------------------------------------------------
    # Rest areas and welcome centers
    # ------------------------------------------------------------------

    def get_rest_areas(
        self,
        include_welcome_centers: bool = True,
        open_only: bool = False,
        route: Optional[str] = None,
    ) -> List[RestArea]:
        """
        Fetch all South Carolina rest areas and welcome centers.

        Parameters
        ----------
        include_welcome_centers:
            If False, filter out welcome centers and return only rest areas.
        open_only:
            If True, only return facilities with ``status == "open"``.
        route:
            Case-insensitive filter by route, e.g. "I-20", "I-95".

        Returns
        -------
        List of RestArea dataclasses.
        """
        url = f"{AGGREGATOR_BASE}/?layer_type=rest_area"
        data = _fetch_json(url, self.timeout)
        areas: List[RestArea] = []
        for feature in data.get("features", []):
            try:
                area = _parse_rest_area(feature)
            except (KeyError, TypeError, ValueError):
                continue
            if not include_welcome_centers and area.facility_type == "Welcome Center":
                continue
            if open_only and area.status.lower() != "open":
                continue
            if route and route.lower() not in area.route.lower():
                continue
            areas.append(area)
        areas.sort(key=lambda a: (a.route, a.mrm))
        return areas

    # ------------------------------------------------------------------
    # Evacuation points
    # ------------------------------------------------------------------

    def get_evacuation_points(self) -> List[EvacuationPoint]:
        """
        Fetch hurricane evacuation points / shelter locations.

        These are activated during hurricane events and represent SCDOT-designated
        shelters and staging areas for coastal evacuation zones.

        Returns
        -------
        List of EvacuationPoint dataclasses.
        """
        url = f"{AGGREGATOR_BASE}/?layer_type=evacuation_point"
        data = _fetch_json(url, self.timeout)
        points: List[EvacuationPoint] = []
        for feature in data.get("features", []):
            try:
                point = _parse_evac_point(feature)
            except (KeyError, TypeError, ValueError):
                continue
            points.append(point)
        return points

    # ------------------------------------------------------------------
    # News and travel alerts
    # ------------------------------------------------------------------

    def get_news(self) -> NewsResponse:
        """
        Fetch current travel news, alerts, and special events from SCDOT.

        The response is categorized into four buckets:

        - ``travel_alerts``: Active road-condition advisories
        - ``general_information``: Standard informational notices
        - ``high_priority``: Urgent notices (major closures, emergencies)
        - ``special_events``: Planned events affecting traffic

        Returns
        -------
        NewsResponse dataclass containing categorized lists.
        """
        data = _fetch_json(NEWS_BASE, self.timeout)
        return NewsResponse(
            general_information=data.get("general_information", []),
            travel_alerts=data.get("travel_alerts", []),
            high_priority=data.get("high_priority", []),
            special_events=data.get("special_events", []),
        )

    # ------------------------------------------------------------------
    # Special events
    # ------------------------------------------------------------------

    def get_special_events(self) -> List[Dict[str, Any]]:
        """
        Fetch special events (concerts, games, road closures for events).

        Returns
        -------
        List of raw feature dicts from the aggregator API.
        """
        url = f"{AGGREGATOR_BASE}/?layer_type=special_event"
        data = _fetch_json(url, self.timeout)
        return data.get("features", [])

    # ------------------------------------------------------------------
    # NWS weather reports
    # ------------------------------------------------------------------

    def get_nws_reports(self) -> Dict[str, Any]:
        """
        Fetch National Weather Service (NWS) weather reports overlay.

        Returns the raw GeoJSON FeatureCollection from the SCDOT CDN.
        Weather data is sourced from NWS and cached on the Iteris CDN.

        Returns
        -------
        Raw GeoJSON dict (may be an empty FeatureCollection when no alerts active).
        """
        url = "https://sc.cdn.iteris-atis.com/geojson/nws_report.json"
        return _fetch_json(url, self.timeout)

    # ------------------------------------------------------------------
    # Convenience / summary methods
    # ------------------------------------------------------------------

    def get_all_data(self) -> Dict[str, Any]:
        """
        Fetch all available data in a single call (multiple HTTP requests).

        Returns
        -------
        Dictionary with keys: cameras, incidents, dms, congestion,
        rest_areas, evacuation_points, news.
        """
        return {
            "cameras": [c.to_dict() for c in self.get_cameras()],
            "incidents": [i.to_dict() for i in self.get_incidents()],
            "dms": [d.to_dict() for d in self.get_dynamic_message_signs()],
            "congestion": [c.to_dict() for c in self.get_congestion()],
            "rest_areas": [r.to_dict() for r in self.get_rest_areas()],
            "evacuation_points": [e.to_dict() for e in self.get_evacuation_points()],
            "news": self.get_news().to_dict(),
        }

    def get_stream_urls(self, camera_name: str) -> Dict[str, str]:
        """
        Return all available streaming URLs for a camera by name.

        Parameters
        ----------
        camera_name:
            Camera name, e.g. "50001".

        Returns
        -------
        Dictionary with stream type keys: snapshot, hls, rtsp, rtmp, preroll.

        Raises
        ------
        ValueError
            If the camera name is not found.
        """
        cam = self.get_camera(camera_name)
        if cam is None:
            raise ValueError(f"Camera '{camera_name}' not found")
        return {
            "snapshot": cam.snapshot_url,
            "hls": cam.hls_url,
            "https_url": cam.https_url,
            "ios_url": cam.ios_url,
            "rtsp": cam.rtsp_url,
            "rtmp": cam.rtmp_url,
            "preroll": cam.preroll_url,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_cameras(cameras: List[Camera]) -> None:
    if not cameras:
        print("No cameras found.")
        return
    print(f"\n{'='*70}")
    print(f"  TRAFFIC CAMERAS  ({len(cameras)} total)")
    print(f"{'='*70}")
    for cam in cameras:
        status = "ACTIVE" if cam.active else "OFFLINE"
        problem = " [STREAM ISSUE]" if cam.problem_stream else ""
        print(f"\n  [{status}]{problem}")
        print(f"  Name:         {cam.name}")
        print(f"  Location:     {cam.description}")
        print(f"  Route:        {cam.route} {cam.direction}  |  MRM: {cam.mrm}")
        print(f"  Jurisdiction: {cam.jurisdiction}")
        print(f"  Snapshot:     {cam.snapshot_url}")
        print(f"  HLS Stream:   {cam.hls_url}")


def _print_incidents(incidents: List[Incident]) -> None:
    if not incidents:
        print("No active incidents.")
        return
    print(f"\n{'='*70}")
    print(f"  ACTIVE INCIDENTS  ({len(incidents)} total)")
    print(f"{'='*70}")
    for inc in incidents:
        print(f"\n  [{inc.headline.upper()}]")
        print(f"  Event ID:   {inc.event_id}")
        print(f"  Route:      {inc.route} {inc.direction}  |  MRM: {inc.mrm}")
        print(f"  Location:   {inc.location_description}")
        print(f"  Road Type:  {inc.road_type}")
        print(f"  Coords:     {inc.latitude:.5f}, {inc.longitude:.5f}")


def _print_dms(signs: List[DynamicMessageSign]) -> None:
    if not signs:
        print("No dynamic message signs found.")
        return
    print(f"\n{'='*70}")
    print(f"  DYNAMIC MESSAGE SIGNS  ({len(signs)} total)")
    print(f"{'='*70}")
    for sign in signs:
        print(f"\n  Sign #{sign.dms_name}  [{sign.icon.upper()}]")
        print(f"  Route:      {sign.route} {sign.direction}  |  MRM: {sign.mrm}")
        print(f"  Location:   {sign.location_description}")
        print(f"  County:     {sign.county or 'N/A'}")


def _print_rest_areas(areas: List[RestArea]) -> None:
    if not areas:
        print("No rest areas found.")
        return
    print(f"\n{'='*70}")
    print(f"  REST AREAS & WELCOME CENTERS  ({len(areas)} total)")
    print(f"{'='*70}")
    for area in areas:
        print(f"\n  {area.title}")
        print(f"  Type:       {area.facility_type}")
        print(f"  Route:      {area.route} {area.direction}  |  MRM: {area.mrm}")
        print(f"  Location:   {area.location}")
        print(f"  Status:     {area.status.upper()}  ({area.seasonal})")
        print(f"  Amenities:  {', '.join(area.amenities) if area.amenities else 'N/A'}")
        if area.description:
            print(f"  Info:       {area.description}")


def _print_evac_points(points: List[EvacuationPoint]) -> None:
    if not points:
        print("No evacuation points found (none currently active).")
        return
    print(f"\n{'='*70}")
    print(f"  EVACUATION POINTS  ({len(points)} total)")
    print(f"{'='*70}")
    for pt in points:
        print(f"\n  ID: {pt.m_uuid}  |  Content ID: {pt.content_id}")
        print(f"  Title:      {pt.title or 'N/A'}")
        print(f"  Message:    {pt.message or 'N/A'}")
        print(f"  Coords:     {pt.latitude:.5f}, {pt.longitude:.5f}")
        if pt.description:
            print(f"  Details:    {pt.description}")


def _print_news(news: NewsResponse) -> None:
    if news.is_empty:
        print("No active travel alerts or news items.")
        return
    print(f"\n{'='*70}")
    print(f"  TRAVEL ALERTS & NEWS")
    print(f"{'='*70}")
    for cat, items in [
        ("HIGH PRIORITY", news.high_priority),
        ("TRAVEL ALERTS", news.travel_alerts),
        ("GENERAL INFORMATION", news.general_information),
        ("SPECIAL EVENTS", news.special_events),
    ]:
        if items:
            print(f"\n  [{cat}] ({len(items)} items)")
            for item in items:
                print(f"    {json.dumps(item, indent=2)}")


def main() -> None:
    """Command-line interface for the 511SC SCDOT client."""
    parser = argparse.ArgumentParser(
        prog="scdot_client",
        description="South Carolina DOT 511SC traffic information client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scdot_client.py                        # Full status demo
  python scdot_client.py --cameras              # All cameras
  python scdot_client.py --cameras --active     # Active cameras only
  python scdot_client.py --jurisdiction Columbia # Filter by city
  python scdot_client.py --camera 50001         # Single camera detail
  python scdot_client.py --incidents            # Active incidents
  python scdot_client.py --dms                  # Dynamic message signs
  python scdot_client.py --rest-areas           # Rest areas
  python scdot_client.py --evac-points          # Evacuation points
  python scdot_client.py --news                 # Travel alerts
  python scdot_client.py --save-snapshot 50001 cam.png  # Save camera image
  python scdot_client.py --json                 # All data as JSON
        """,
    )
    parser.add_argument("--cameras", action="store_true", help="List all cameras")
    parser.add_argument("--active", action="store_true", help="Active cameras only (use with --cameras)")
    parser.add_argument("--jurisdiction", type=str, help="Filter by jurisdiction name")
    parser.add_argument("--route", type=str, help="Filter by route (e.g. I-95)")
    parser.add_argument("--camera", type=str, metavar="NAME", help="Show single camera by name")
    parser.add_argument("--incidents", action="store_true", help="Show active incidents")
    parser.add_argument("--dms", action="store_true", help="Show dynamic message signs")
    parser.add_argument("--congestion", action="store_true", help="Show congestion events")
    parser.add_argument("--rest-areas", action="store_true", help="Show rest areas")
    parser.add_argument("--evac-points", action="store_true", help="Show evacuation points")
    parser.add_argument("--news", action="store_true", help="Show travel alerts and news")
    parser.add_argument("--save-snapshot", nargs=2, metavar=("CAMERA_NAME", "OUTPUT_FILE"),
                        help="Download camera snapshot to file")
    parser.add_argument("--json", action="store_true", help="Output all data as JSON")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds")
    args = parser.parse_args()

    client = SCDOTClient(timeout=args.timeout)

    if args.save_snapshot:
        cam_name, out_file = args.save_snapshot
        print(f"Downloading snapshot for camera {cam_name}...")
        try:
            data = client.download_snapshot(cam_name)
            with open(out_file, "wb") as f:
                f.write(data)
            print(f"Saved {len(data):,} bytes to {out_file}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.json:
        print(json.dumps(client.get_all_data(), indent=2))
        return

    if args.camera:
        cam = client.get_camera(args.camera)
        if cam:
            _print_cameras([cam])
        else:
            print(f"Camera '{args.camera}' not found.")
        return

    ran_any = False

    if args.cameras:
        ran_any = True
        cameras = client.get_cameras(
            active_only=args.active,
            jurisdiction=args.jurisdiction,
            route=args.route,
        )
        _print_cameras(cameras)

    if args.incidents:
        ran_any = True
        _print_incidents(client.get_incidents(route=args.route))

    if args.dms:
        ran_any = True
        _print_dms(client.get_dynamic_message_signs())

    if args.congestion:
        ran_any = True
        for evt in client.get_congestion(route=args.route):
            print(f"{evt.event_id}: {evt.route} {evt.direction} — {evt.location_description}")

    if args.rest_areas:
        ran_any = True
        _print_rest_areas(client.get_rest_areas(route=args.route))

    if args.evac_points:
        ran_any = True
        _print_evac_points(client.get_evacuation_points())

    if args.news:
        ran_any = True
        _print_news(client.get_news())

    if not ran_any:
        # Default demo: print a summary of all feeds
        print("\n" + "="*70)
        print("  511SC SCDOT LIVE TRAFFIC SUMMARY")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)

        print("\nFetching cameras...")
        cameras = client.get_cameras()
        active = [c for c in cameras if c.active]
        jurisdictions = {c.jurisdiction for c in cameras}
        print(f"  Total cameras:  {len(cameras)}")
        print(f"  Active cameras: {len(active)}")
        print(f"  Problem streams: {sum(1 for c in cameras if c.problem_stream)}")
        print(f"  Jurisdictions:  {', '.join(sorted(jurisdictions))}")

        print("\nFetching incidents...")
        incidents = client.get_incidents()
        print(f"  Active incidents: {len(incidents)}")
        for inc in incidents[:5]:
            print(f"    {inc.route} {inc.direction}: {inc.headline} @ {inc.location_description}")

        print("\nFetching dynamic message signs...")
        signs = client.get_dynamic_message_signs()
        dms_signs = [s for s in signs if s.icon == "dms"]
        vsl_signs = [s for s in signs if s.icon == "vsl"]
        print(f"  DMS signs:  {len(dms_signs)}")
        print(f"  VSL signs:  {len(vsl_signs)}")

        print("\nFetching congestion events...")
        congestion = client.get_congestion()
        print(f"  Congestion zones: {len(congestion)}")

        print("\nFetching rest areas...")
        rest_areas = client.get_rest_areas()
        open_areas = [a for a in rest_areas if a.status.lower() == "open"]
        print(f"  Total facilities: {len(rest_areas)}")
        print(f"  Open:  {len(open_areas)}")

        print("\nFetching evacuation points...")
        evac = client.get_evacuation_points()
        print(f"  Evacuation points: {len(evac)}")

        print("\nFetching travel alerts/news...")
        news = client.get_news()
        if news.is_empty:
            print("  No active alerts.")
        else:
            print(f"  High priority:       {len(news.high_priority)}")
            print(f"  Travel alerts:       {len(news.travel_alerts)}")
            print(f"  General information: {len(news.general_information)}")
            print(f"  Special events:      {len(news.special_events)}")

        print("\n\nSample camera stream URLs (camera 50001 — US 501 N @ Myrtle Beach):")
        try:
            urls = client.get_stream_urls("50001")
            for k, v in urls.items():
                print(f"  {k:<12}: {v}")
        except ValueError as e:
            print(f"  {e}")

        print("\nDone. Run with --help for more options.")


if __name__ == "__main__":
    main()
