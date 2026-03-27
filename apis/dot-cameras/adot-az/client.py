#!/usr/bin/env python3
"""
ADOT AZ511 Traffic Information Client
======================================
A Python client for the Arizona Department of Transportation (ADOT) AZ511
traveler information system at https://www.az511.gov.

All endpoints were reverse-engineered from the public web application's
JavaScript bundles and XHR/fetch network calls. No API key is required.

Usage (CLI):
    python3 adot_client.py cameras            # List all cameras
    python3 adot_client.py camera 646         # Get camera detail + images
    python3 adot_client.py incidents          # List active incidents
    python3 adot_client.py construction       # List construction zones
    python3 adot_client.py closures           # List road closures
    python3 adot_client.py weather-events     # List weather alerts
    python3 adot_client.py weather-forecast AZZ006  # Zone forecast
    python3 adot_client.py signs              # Dynamic message signs
    python3 adot_client.py rest-areas         # Rest area status
    python3 adot_client.py crossings          # Border crossing wait times
    python3 adot_client.py special-events     # Special events
    python3 adot_client.py truck-restrictions # Truck restrictions
    python3 adot_client.py save-image 682 /tmp/cam.jpg  # Download camera image

Author: Reverse-engineered from https://www.az511.gov (March 2026)
License: Public domain / educational use
"""

from __future__ import annotations

import gzip
import json
import sys
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.az511.gov"

#: Layer names accepted by ``/map/mapIcons/{layer}`` and ``/map/data/{layer}/{id}``
LAYERS = [
    "Cameras",
    "Incidents",
    "Construction",
    "Closures",
    "MessageSigns",
    "WeatherEvents",
    "WeatherForecast",
    "RestAreas",
    "RestAreaClosed",
    "SpecialEvents",
    "TruckRestrictions",
    "MajorCrossings",
    "TrafficSpeeds",
]

#: Google Maps API key embedded in the AZ511 page (public, domain-restricted)
GOOGLE_MAPS_KEY = "AIzaSyDnJ06hvlt5T38t1P4mir61a1wdYTZ3Wdw"

#: Camera image refresh rate (milliseconds) as configured by the site
CAMERA_REFRESH_MS = 30_000

#: Traffic tile CDN (IBI511 / TravelIQ)  –  requires ``Referer: https://www.az511.gov/``
TRAFFIC_TILE_URL = "https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}"

#: Weather-radar overlay tile (served by AZ511 proxy, returns ``Imagedate`` header)
WEATHER_RADAR_TILE_URL = BASE_URL + "/map/weatherRadar/{x}/{y}/{z}?frame={frame}"

#: Milepost WMS overlay tile
MILEPOST_TILE_URL = BASE_URL + "/map/mapWMS/MileMarkers/{x}/{y}/{z}"

#: Default HTTP timeout (seconds)
DEFAULT_TIMEOUT = 20

#: Default headers that mimic a browser and avoid 405/403 errors on tile endpoints
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": BASE_URL + "/",
}


# ---------------------------------------------------------------------------
# Shared geo helpers
# ---------------------------------------------------------------------------


@dataclass
class LatLng:
    """Geographic coordinate pair."""

    lat: float
    lng: float

    def __str__(self) -> str:
        return f"{self.lat:.6f}, {self.lng:.6f}"


def _parse_latlng(raw: Optional[Dict]) -> Optional[LatLng]:
    """Parse ``latLng.geography.wellKnownText`` or fall back to top-level lat/lng."""
    if not raw:
        return None
    geo = raw.get("geography", {})
    wkt = geo.get("wellKnownText", "")
    # "POINT (-112.134 33.462)"
    if wkt.startswith("POINT"):
        try:
            coords = wkt[wkt.index("(") + 1 : wkt.index(")")].split()
            return LatLng(lat=float(coords[1]), lng=float(coords[0]))
        except (ValueError, IndexError):
            pass
    return None


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CameraImage:
    """A single viewpoint / snapshot source for a camera site."""

    id: int
    camera_site_id: int
    sort_order: int
    description: str
    image_url: str  # relative path, e.g. "/map/Cctv/682"
    image_type: int  # 0 = JPEG still; other values may indicate video
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool

    @property
    def full_image_url(self) -> str:
        """Absolute URL for the live camera JPEG."""
        return BASE_URL + self.image_url

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CameraImage":
        return cls(
            id=d["id"],
            camera_site_id=d["cameraSiteId"],
            sort_order=d.get("sortOrder", 0),
            description=d.get("description", ""),
            image_url=d.get("imageUrl", ""),
            image_type=d.get("imageType", 0),
            is_video_auth_required=d.get("isVideoAuthRequired", False),
            video_disabled=d.get("videoDisabled", False),
            disabled=d.get("disabled", False),
            blocked=d.get("blocked", False),
        )


@dataclass
class Camera:
    """A camera site that may have one or more viewpoint images."""

    id: int
    source_id: str
    source: str
    type: str
    roadway: str
    location: str
    direction: int
    lat: float
    lng: float
    images: List[CameraImage] = field(default_factory=list)
    created: Optional[str] = None
    last_updated: Optional[str] = None
    area_id: Optional[str] = None

    @property
    def primary_image_url(self) -> Optional[str]:
        """Absolute URL for the primary camera snapshot."""
        if self.images:
            return self.images[0].full_image_url
        return None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Camera":
        latlng = _parse_latlng(d.get("latLng"))
        lat = latlng.lat if latlng else d.get("latitude", 0.0)
        lng = latlng.lng if latlng else d.get("longitude", 0.0)
        images = [CameraImage.from_dict(i) for i in d.get("images", [])]
        return cls(
            id=d["id"],
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            type=d.get("type", ""),
            roadway=d.get("roadway", ""),
            location=d.get("location", ""),
            direction=d.get("direction", 0),
            lat=lat,
            lng=lng,
            images=images,
            created=d.get("created"),
            last_updated=d.get("lastUpdated"),
            area_id=d.get("areaId"),
        )


@dataclass
class TrafficEvent:
    """
    A road event: incident, construction, closure, special event, or weather.

    Covers the unified schema returned by ``/map/data/{layer}/{id}``.
    """

    id: int
    source: str
    source_id: str
    description: str
    event_type: str  # e.g. "accidentsAndIncidents", "roadwork", "closures"
    event_sub_type: str
    atis_type: str
    roadway: str
    direction: str
    severity: str
    is_full_closure: bool
    lat: float
    lng: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    last_updated: Optional[str] = None
    location_description: Optional[str] = None
    lane_description: Optional[str] = None
    polyline: Optional[str] = None  # encoded Google Maps polyline
    camera_ids: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrafficEvent":
        latlng = _parse_latlng(d.get("latLng"))
        lat = latlng.lat if latlng else d.get("latitude", 0.0)
        lng = latlng.lng if latlng else d.get("longitude", 0.0)
        return cls(
            id=d["id"],
            source=d.get("source", ""),
            source_id=d.get("sourceId", ""),
            description=d.get("description", ""),
            event_type=d.get("eventType") or d.get("atisType") or "",
            event_sub_type=d.get("eventSubType", ""),
            atis_type=d.get("atisType", ""),
            roadway=d.get("roadway", ""),
            direction=d.get("direction", ""),
            severity=d.get("severity", ""),
            is_full_closure=d.get("isFullClosure", False),
            lat=lat,
            lng=lng,
            start_date=d.get("startDate"),
            end_date=d.get("endDate"),
            last_updated=d.get("lastUpdated"),
            location_description=d.get("locationDescription"),
            lane_description=d.get("laneDescription"),
            polyline=d.get("polyline"),
            camera_ids=d.get("cameraIds") or None,
        )


@dataclass
class MessageSign:
    """A dynamic message sign (DMS) / variable message sign (VMS)."""

    id: int
    source: str
    source_id: str
    name: str
    description: str
    status: str
    roadway_name: str
    direction: str
    messages: str  # raw multi-line sign text
    lat: float
    lng: float
    last_comm: Optional[str] = None
    last_update: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MessageSign":
        latlng = _parse_latlng(d.get("latLng"))
        lat = latlng.lat if latlng else 0.0
        lng = latlng.lng if latlng else 0.0
        return cls(
            id=d["id"],
            source=d.get("source", ""),
            source_id=d.get("sourceId", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            status=d.get("status", ""),
            roadway_name=d.get("roadwayName", ""),
            direction=d.get("direction", ""),
            messages=d.get("messages", ""),
            lat=lat,
            lng=lng,
            last_comm=d.get("lastComm"),
            last_update=d.get("lastUpdate"),
        )


@dataclass
class WeatherEvent:
    """A weather advisory / alert polygon (NWS-sourced)."""

    id: int
    severity: str
    lat: float
    lng: float
    comment: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    last_updated: Optional[str] = None
    # GeoJSON polygon Well-Known Text (WKT) if available
    geom_wkt: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WeatherEvent":
        latlng = _parse_latlng(d.get("latLng"))
        lat = latlng.lat if latlng else d.get("latitude", 0.0)
        lng = latlng.lng if latlng else d.get("longitude", 0.0)
        comment_obj = d.get("eventComment") or {}
        desc_obj = d.get("eventDescription") or {}
        geom = d.get("geom")
        geom_wkt = None
        if geom and isinstance(geom, dict):
            geom_wkt = (geom.get("geography") or {}).get("wellKnownText")
        return cls(
            id=d["id"],
            severity=d.get("severity", ""),
            lat=lat,
            lng=lng,
            comment=comment_obj.get("text") if comment_obj else None,
            description=desc_obj.get("text") if desc_obj else None,
            start_date=d.get("startDate"),
            end_date=d.get("endDate"),
            last_updated=d.get("lastUpdated"),
            geom_wkt=geom_wkt,
        )


@dataclass
class WeatherForecastPeriod:
    """A single forecast period (e.g. "Today", "Tonight", "Saturday")."""

    number: str
    name: str
    start_time: str
    end_time: str
    is_day_time: bool
    temperature: int
    wind_speed: str
    wind_direction: str
    icon: str  # NWS icon URL
    short_forecast: str
    detailed_forecast: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WeatherForecastPeriod":
        f = d.get("forecast", {})
        return cls(
            number=str(f.get("number", "")),
            name=f.get("name", ""),
            start_time=f.get("startTime", ""),
            end_time=f.get("endTime", ""),
            is_day_time=str(f.get("isDayTime", "false")).lower() == "true",
            temperature=int(f.get("temperature") or 0),
            wind_speed=f.get("windSpeed", ""),
            wind_direction=f.get("windDirection", ""),
            icon=f.get("icon", ""),
            short_forecast=f.get("shortForecast", ""),
            detailed_forecast=f.get("detailedForecast", ""),
        )


@dataclass
class WeatherForecastZone:
    """A National Weather Service forecast zone with multiple periods."""

    zone_id: str
    location_name: str
    lat: float
    lng: float
    grid_id: str
    grid_x: int
    grid_y: int
    periods: List[WeatherForecastPeriod] = field(default_factory=list)
    last_updated: Optional[str] = None

    @classmethod
    def from_list(cls, items: List[Dict[str, Any]]) -> "WeatherForecastZone":
        if not items:
            raise ValueError("Empty forecast list")
        loc = items[0].get("location", {})
        periods = [WeatherForecastPeriod.from_dict(i) for i in items]
        return cls(
            zone_id=loc.get("locationId", ""),
            location_name=loc.get("locationName", ""),
            lat=loc.get("latitude", 0.0),
            lng=loc.get("longitude", 0.0),
            grid_id=loc.get("gridId", ""),
            grid_x=loc.get("gridX", 0),
            grid_y=loc.get("gridY", 0),
            periods=periods,
            last_updated=items[0].get("lastUpdated"),
        )


@dataclass
class RestArea:
    """A highway rest area with amenity information."""

    id: int
    source: str
    source_id: str
    lat: float
    lng: float
    name: str = ""
    location: str = ""
    city: str = ""
    has_restroom: bool = False
    has_ramada: bool = False
    has_vending: bool = False
    is_open: bool = True
    last_updated: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RestArea":
        latlng = _parse_latlng(d.get("latLng"))
        lat = latlng.lat if latlng else 0.0
        lng = latlng.lng if latlng else 0.0
        props = {p["name"]: p.get("value", "") for p in d.get("properties", [])}
        return cls(
            id=d["id"],
            source=d.get("source", ""),
            source_id=d.get("sourceId", ""),
            lat=lat,
            lng=lng,
            name=props.get("LongName", d.get("filterAndOrderProperty1", "")),
            location=props.get("Location", ""),
            city=props.get("City", ""),
            has_restroom=props.get("Restroom", "N").strip().upper() == "Y",
            has_ramada=props.get("Ramada", "N").strip().upper() == "Y",
            has_vending=props.get("VendingMachine", "N").strip().upper() == "Y",
            is_open=True,
            last_updated=d.get("lastUpdated"),
        )


@dataclass
class BorderCrossing:
    """A US–Mexico border crossing with lane wait information."""

    id: int
    source: str
    source_id: str
    lat: float
    lng: float
    name: str = ""
    hours: str = ""
    date_of_operation: str = ""
    commercial_max_lanes: str = ""
    passenger_max_lanes: str = ""
    pedestrian_max_lanes: str = ""
    commercial_delay: str = ""
    passenger_delay: str = ""
    pedestrian_delay: str = ""
    last_updated: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BorderCrossing":
        latlng = _parse_latlng(d.get("latLng"))
        lat = latlng.lat if latlng else 0.0
        lng = latlng.lng if latlng else 0.0
        props = {p["name"]: p.get("value", "") for p in d.get("properties", [])}
        return cls(
            id=d["id"],
            source=d.get("source", ""),
            source_id=d.get("sourceId", ""),
            lat=lat,
            lng=lng,
            name=props.get("Name", ""),
            hours=props.get("HoursOfOperation", ""),
            date_of_operation=props.get("DateOfOperation", ""),
            commercial_max_lanes=props.get("CommercialMaxLanes", ""),
            passenger_max_lanes=props.get("PassengerMaxLanes", ""),
            pedestrian_max_lanes=props.get("PedestrianMaxLanes", ""),
            commercial_delay=props.get("CommercialStandardRouteStatus", ""),
            passenger_delay=props.get("PassengerStandardRouteStatus", ""),
            pedestrian_delay=props.get("PedestrianRouteStatus", ""),
            last_updated=d.get("lastUpdated"),
        )


@dataclass
class MapMarker:
    """
    Lightweight map marker returned by ``/map/mapIcons/{layer}``.

    Use this for fast spatial queries (just lat/lng + item ID).
    Fetch the full detail via ``ADOT511Client.get_detail(layer, item_id)``.
    """

    item_id: str
    lat: float
    lng: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MapMarker":
        loc = d.get("location", [0.0, 0.0])
        return cls(
            item_id=str(d["itemId"]),
            lat=float(loc[0]) if loc else 0.0,
            lng=float(loc[1]) if loc else 0.0,
        )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    """
    Perform an HTTP GET and return the raw response body.

    Handles gzip decompression automatically.  Adds browser-like headers
    including ``Referer`` so the IBI511 tile CDN and Lambda@Edge proxy
    honour the request.

    Raises:
        urllib.error.HTTPError: on 4xx / 5xx responses
        urllib.error.URLError:  on network failures
    """
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body


def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """Fetch URL and parse JSON response."""
    body = _http_get(url, timeout)
    return json.loads(body)


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class ADOT511Client:
    """
    Client for the Arizona Department of Transportation AZ511 traveler
    information system.

    All methods return strongly-typed dataclasses built from the raw JSON
    responses.  No authentication is required for any read-only operation.

    Example::

        client = ADOT511Client()

        # All cameras in Arizona
        cameras = client.list_cameras()
        for cam in cameras[:5]:
            print(cam.roadway, cam.location, cam.primary_image_url)

        # Specific camera detail with all image views
        cam = client.get_camera(646)
        for img in cam.images:
            print(img.description, img.full_image_url)

        # Active incidents
        for incident in client.list_incidents():
            print(incident.roadway, incident.severity, incident.description[:60])

        # I-10 corridor cameras
        i10_cams = client.cameras_by_corridor("I-10")

        # Download a camera snapshot
        client.save_camera_image(682, "/tmp/cam_682.jpg")
    """

    BASE_URL = BASE_URL

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """
        Initialise the client.

        Args:
            timeout: HTTP request timeout in seconds (default 20).
        """
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_map_icons(self, layer: str) -> List[MapMarker]:
        """
        Fetch lightweight marker list for *layer*.

        Endpoint: ``GET /map/mapIcons/{layer}``

        Response schema::

            {
              "item1": { <default icon config> },
              "item2": [
                { "itemId": "635", "location": [35.17, -114.56], "icon": {...}, "title": "" },
                ...
              ]
            }

        Args:
            layer: One of :data:`LAYERS`.

        Returns:
            List of :class:`MapMarker` objects.
        """
        url = f"{self.BASE_URL}/map/mapIcons/{layer}"
        data = _fetch_json(url, self.timeout)
        return [MapMarker.from_dict(item) for item in data.get("item2", [])]

    def get_detail(self, layer: str, item_id: str | int) -> Dict[str, Any]:
        """
        Fetch raw detail JSON for any item.

        Endpoint: ``GET /map/data/{layer}/{item_id}``

        This is the lowest-level accessor; prefer the typed methods below.

        Args:
            layer: One of :data:`LAYERS`.
            item_id: Numeric or string identifier returned by map icons.

        Returns:
            Parsed JSON dict.
        """
        url = f"{self.BASE_URL}/map/data/{layer}/{item_id}"
        return _fetch_json(url, self.timeout)

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def list_camera_markers(self) -> List[MapMarker]:
        """
        Return lightweight markers for all 600+ cameras.

        Fast call (~1 request).  Use :meth:`get_camera` for full detail.

        Returns:
            List of :class:`MapMarker` with ``item_id``, ``lat``, ``lng``.
        """
        return self._get_map_icons("Cameras")

    def list_cameras(self, max_cameras: Optional[int] = None,
                     delay: float = 0.05) -> List[Camera]:
        """
        Fetch full detail for every camera (604 as of March 2026).

        .. warning::
            This makes one HTTP request per camera site.  With ~600 cameras
            and ``delay=0.05`` it takes roughly 30–60 seconds.  Consider
            :meth:`list_camera_markers` for spatial queries and then fetching
            individual cameras on demand.

        Args:
            max_cameras: Limit the number of cameras fetched (``None`` = all).
            delay: Seconds to sleep between requests.

        Returns:
            List of fully populated :class:`Camera` objects.
        """
        markers = self.list_camera_markers()
        if max_cameras is not None:
            markers = markers[:max_cameras]
        cameras: List[Camera] = []
        for m in markers:
            try:
                cam = self.get_camera(m.item_id)
                cameras.append(cam)
            except Exception:
                pass
            if delay:
                time.sleep(delay)
        return cameras

    def get_camera(self, camera_site_id: str | int) -> Camera:
        """
        Fetch full detail for a single camera site.

        Endpoint: ``GET /map/data/Cameras/{camera_site_id}``

        Args:
            camera_site_id: The numeric camera site ID (e.g. 635, 646).

        Returns:
            :class:`Camera` with :attr:`Camera.images` populated.
        """
        data = self.get_detail("Cameras", camera_site_id)
        return Camera.from_dict(data)

    def cameras_by_corridor(self, corridor: str) -> List[Camera]:
        """
        Return cameras whose roadway name contains *corridor*.

        This performs a full scan of all camera markers (1 request) then
        fetches detailed records only for matching cameras.

        Args:
            corridor: Partial roadway name, e.g. ``"I-10"``, ``"I-17"``,
                ``"I-40"``, ``"US-60"``.

        Returns:
            List of :class:`Camera` objects on the specified corridor.

        Example::

            client.cameras_by_corridor("I-40")  # All I-40 cameras
        """
        # First pass: get all markers (lat/lng only)
        markers = self.list_camera_markers()
        matched: List[Camera] = []
        for m in markers:
            try:
                cam = self.get_camera(m.item_id)
                if corridor.upper() in cam.roadway.upper():
                    matched.append(cam)
            except Exception:
                pass
            time.sleep(0.05)
        return matched

    def get_camera_image(self, cctv_image_id: str | int) -> bytes:
        """
        Download a live camera snapshot as raw JPEG bytes.

        Endpoint: ``GET /map/Cctv/{cctv_image_id}``

        The image is served via CloudFront with ``cache-control: max-age=30``,
        so frames update every 30 seconds.  Use :attr:`CameraImage.id` (not
        :attr:`CameraImage.camera_site_id`) as the argument.

        Args:
            cctv_image_id: The image ID from :class:`CameraImage` (e.g. 682).

        Returns:
            Raw JPEG bytes.
        """
        url = f"{self.BASE_URL}/map/Cctv/{cctv_image_id}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def save_camera_image(self, cctv_image_id: str | int,
                          path: str) -> str:
        """
        Download a camera snapshot and write it to *path*.

        Args:
            cctv_image_id: The CCTV image ID (from :class:`CameraImage`).
            path: Destination file path (will be overwritten if exists).

        Returns:
            Absolute path to the saved file.
        """
        data = self.get_camera_image(cctv_image_id)
        with open(path, "wb") as fh:
            fh.write(data)
        return os.path.abspath(path)

    # ------------------------------------------------------------------
    # Traffic events (incidents, construction, closures, special events)
    # ------------------------------------------------------------------

    def _list_events(self, layer: str) -> List[TrafficEvent]:
        """Shared helper for all event-type layers."""
        markers = self._get_map_icons(layer)
        events: List[TrafficEvent] = []
        for m in markers:
            try:
                data = self.get_detail(layer, m.item_id)
                events.append(TrafficEvent.from_dict(data))
            except Exception:
                pass
            time.sleep(0.03)
        return events

    def list_incidents(self) -> List[TrafficEvent]:
        """
        Return all active traffic incidents statewide.

        Endpoint: ``GET /map/mapIcons/Incidents``  +
                  ``GET /map/data/Incidents/{id}``

        Incident subtypes include: ``Potholes``, ``Accident``,
        ``Road Debris``, ``Stalled Vehicle``, etc.

        Returns:
            List of :class:`TrafficEvent` with ``event_type="accidentsAndIncidents"``.
        """
        return self._list_events("Incidents")

    def list_construction(self) -> List[TrafficEvent]:
        """
        Return all active construction zones statewide.

        Construction subtypes include: ``Road widening``, ``Resurfacing``,
        ``Bridge work``, ``Lane reduction``, etc.

        Returns:
            List of :class:`TrafficEvent` with ``event_type="roadwork"``.
        """
        return self._list_events("Construction")

    def list_closures(self) -> List[TrafficEvent]:
        """
        Return all active road closures statewide.

        Closure subtypes include: ``exitclosed``, ``Full Closure``,
        ``On-ramp closed``, etc.

        Returns:
            List of :class:`TrafficEvent` with ``event_type="closures"``.
        """
        return self._list_events("Closures")

    def list_special_events(self) -> List[TrafficEvent]:
        """
        Return all active special events (festivals, sporting events, etc.).

        Returns:
            List of :class:`TrafficEvent` with ``event_type="specialEvents"``.
        """
        return self._list_events("SpecialEvents")

    def list_truck_restrictions(self) -> List[TrafficEvent]:
        """
        Return all active truck restrictions and weight/size limits.

        The full restriction details (width, height, weight limits) are in
        the raw ``properties`` list – access via :meth:`get_detail`.

        Returns:
            List of :class:`TrafficEvent`.
        """
        return self._list_events("TruckRestrictions")

    # ------------------------------------------------------------------
    # Dynamic message signs
    # ------------------------------------------------------------------

    def list_message_signs(self) -> List[MessageSign]:
        """
        Return all dynamic message signs (DMS/VMS) statewide.

        Each sign includes the current multi-line message text.

        Endpoint: ``GET /map/mapIcons/MessageSigns``  +
                  ``GET /map/data/MessageSigns/{id}``

        Returns:
            List of :class:`MessageSign`.
        """
        markers = self._get_map_icons("MessageSigns")
        signs: List[MessageSign] = []
        for m in markers:
            try:
                data = self.get_detail("MessageSigns", m.item_id)
                signs.append(MessageSign.from_dict(data))
            except Exception:
                pass
            time.sleep(0.03)
        return signs

    def get_message_sign(self, sign_id: str | int) -> MessageSign:
        """
        Fetch a single dynamic message sign by ID.

        Args:
            sign_id: Numeric sign ID (e.g. 6891 for "I-10 EB @ 35th Ave").

        Returns:
            :class:`MessageSign`.
        """
        data = self.get_detail("MessageSigns", sign_id)
        return MessageSign.from_dict(data)

    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------

    def list_weather_events(self) -> List[WeatherEvent]:
        """
        Return all active NWS weather alerts/advisories in Arizona.

        Alerts include wind advisories, dust storm warnings, flash flood
        watches, winter weather advisories, etc.

        Endpoint: ``GET /map/mapIcons/WeatherEvents``  +
                  ``GET /map/data/WeatherEvents/{id}``

        Returns:
            List of :class:`WeatherEvent`.
        """
        markers = self._get_map_icons("WeatherEvents")
        events: List[WeatherEvent] = []
        for m in markers:
            try:
                data = self.get_detail("WeatherEvents", m.item_id)
                events.append(WeatherEvent.from_dict(data))
            except Exception:
                pass
            time.sleep(0.03)
        return events

    def list_weather_forecast_zones(self) -> List[MapMarker]:
        """
        Return all NWS weather forecast zone markers.

        Zone IDs follow the NWS pattern ``AZZ###`` (e.g. ``AZZ006`` for
        Coconino County).  Use :meth:`get_weather_forecast` to fetch the
        7-day forecast for a specific zone.

        Returns:
            List of :class:`MapMarker`.
        """
        return self._get_map_icons("WeatherForecast")

    def get_weather_forecast(self, zone_id: str) -> WeatherForecastZone:
        """
        Fetch the 7-day NWS forecast for a specific zone.

        Endpoint: ``GET /map/data/WeatherForecast/{zone_id}``

        Response is a list of forecast periods (today, tonight, Saturday…).
        Data is sourced from api.weather.gov NWS forecast grids.

        Args:
            zone_id: NWS zone identifier, e.g. ``"AZZ006"`` (Coconino County),
                ``"AZZ023"`` (Maricopa County), ``"AZZ028"`` (Pima County).

        Returns:
            :class:`WeatherForecastZone` with ``periods`` list.
        """
        url = f"{self.BASE_URL}/map/data/WeatherForecast/{zone_id}"
        items = _fetch_json(url, self.timeout)
        if not isinstance(items, list):
            raise ValueError(f"Unexpected response for zone {zone_id!r}: {type(items)}")
        return WeatherForecastZone.from_list(items)

    def get_weather_radar_tile(self, x: int, y: int, z: int,
                               frame: int = 0) -> Tuple[bytes, str]:
        """
        Download a single weather-radar map tile.

        Endpoint: ``GET /map/weatherRadar/{z}/{x}/{y}?frame={frame}``

        Returns a transparent PNG overlay tile.  The ``Imagedate`` response
        header contains the UTC timestamp of the radar scan; it is returned
        as the second element of the tuple.

        Args:
            x: Tile column (Google/OSM tile coordinate).
            y: Tile row.
            z: Zoom level.
            frame: Animation frame index (0 = most recent, 1 = previous, …).

        Returns:
            ``(png_bytes, image_date_iso_str)`` tuple.
        """
        url = f"{self.BASE_URL}/map/weatherRadar/{z}/{x}/{y}?frame={frame}"
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            image_date = resp.headers.get("Imagedate", "")
            body = resp.read()
        return body, image_date

    def get_traffic_tile(self, x: int, y: int, z: int) -> bytes:
        """
        Download a traffic-speed overlay PNG tile from the IBI511/TravelIQ CDN.

        Endpoint: ``GET https://tiles.ibi511.com/Geoservice/GetTrafficTile?x=…``

        Requires ``Referer: https://www.az511.gov/`` header (already set).
        Tiles are cached for 60 seconds.

        Args:
            x: Tile column.
            y: Tile row.
            z: Zoom level.

        Returns:
            Raw PNG bytes.
        """
        url = TRAFFIC_TILE_URL.format(x=x, y=y, z=z)
        return _http_get(url, self.timeout)

    # ------------------------------------------------------------------
    # Rest areas
    # ------------------------------------------------------------------

    def list_rest_areas(self, include_closed: bool = True) -> List[RestArea]:
        """
        Return rest area facility information for all Arizona rest areas.

        Endpoint: ``GET /map/mapIcons/RestAreas``  +
                  ``GET /map/data/RestAreas/{id}``

        Args:
            include_closed: If ``True`` (default) also fetch from the
                ``RestAreaClosed`` layer.

        Returns:
            List of :class:`RestArea`.
        """
        markers = self._get_map_icons("RestAreas")
        if include_closed:
            try:
                markers += self._get_map_icons("RestAreaClosed")
            except Exception:
                pass
        areas: List[RestArea] = []
        for m in markers:
            try:
                layer = "RestAreas"
                data = self.get_detail(layer, m.item_id)
                ra = RestArea.from_dict(data)
                areas.append(ra)
            except Exception:
                pass
            time.sleep(0.03)
        return areas

    # ------------------------------------------------------------------
    # Border crossings
    # ------------------------------------------------------------------

    def list_border_crossings(self) -> List[BorderCrossing]:
        """
        Return US–Mexico border crossing wait times.

        Data is sourced from US Customs and Border Protection (CBP).
        Each crossing includes current passenger, commercial, and pedestrian
        lane delay status.

        Endpoint: ``GET /map/mapIcons/MajorCrossings``  +
                  ``GET /map/data/MajorCrossings/{id}``

        Returns:
            List of :class:`BorderCrossing`.
        """
        markers = self._get_map_icons("MajorCrossings")
        crossings: List[BorderCrossing] = []
        for m in markers:
            try:
                data = self.get_detail("MajorCrossings", m.item_id)
                crossings.append(BorderCrossing.from_dict(data))
            except Exception:
                pass
            time.sleep(0.03)
        return crossings

    # ------------------------------------------------------------------
    # Polyline / shape data
    # ------------------------------------------------------------------

    def get_event_polyline(self, layer: str, item_id: str | int) -> Optional[str]:
        """
        Return the encoded Google Maps polyline for an event (if available).

        Polylines are available for layers: ``Construction``, ``Incidents``,
        ``Closures``, ``SpecialEvents``, ``TruckRestrictions``.

        Args:
            layer: One of the polyline-capable layers.
            item_id: Event ID.

        Returns:
            Encoded polyline string, or ``None`` if not available.
        """
        data = self.get_detail(layer, item_id)
        return data.get("polyline")

    # ------------------------------------------------------------------
    # Tile URL builders (for use with mapping libraries)
    # ------------------------------------------------------------------

    @staticmethod
    def traffic_tile_url_template() -> str:
        """
        Return the traffic speed tile URL template for use with mapping libs.

        Requires ``Referer: https://www.az511.gov/`` in tile requests.

        Returns:
            Template string with ``{x}``, ``{y}``, ``{z}`` placeholders.
        """
        return TRAFFIC_TILE_URL

    @staticmethod
    def weather_radar_tile_url_template(frame: int = 0) -> str:
        """
        Return the weather radar tile URL template.

        Args:
            frame: Animation frame (0 = most recent radar scan).

        Returns:
            Template string with ``{x}``, ``{y}``, ``{z}`` placeholders.
        """
        return WEATHER_RADAR_TILE_URL.replace("{frame}", str(frame))

    @staticmethod
    def milepost_tile_url_template() -> str:
        """
        Return the milepost WMS tile URL template.

        Returns:
            Template string with ``{x}``, ``{y}``, ``{z}`` placeholders.
        """
        return MILEPOST_TILE_URL


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

_COMMANDS = [
    "cameras", "camera", "incidents", "construction", "closures",
    "weather-events", "weather-forecast", "signs", "sign",
    "rest-areas", "crossings", "special-events", "truck-restrictions",
    "save-image", "tile-urls",
]

_HELP = f"""
AZ511 ADOT Traffic Client - CLI Demo
=====================================
Usage:
  python3 adot_client.py <command> [args...]

Commands:
  cameras                       List all camera markers (fast, no detail)
  camera <id>                   Show full detail for camera site
  incidents                     List all active incidents
  construction                  List all active construction zones
  closures                      List all road closures
  weather-events                List all active weather alerts
  weather-forecast <zone_id>    Show 7-day forecast (e.g. AZZ006, AZZ023)
  signs                         List all dynamic message signs
  sign <id>                     Show a specific message sign
  rest-areas                    List rest areas
  crossings                     List border crossings
  special-events                List special events
  truck-restrictions            List truck restrictions
  save-image <cctv_id> <path>   Download camera image to file
  tile-urls                     Print tile URL templates

Examples:
  python3 adot_client.py cameras
  python3 adot_client.py camera 646
  python3 adot_client.py weather-forecast AZZ006
  python3 adot_client.py save-image 682 /tmp/cam.jpg
  python3 adot_client.py incidents | head -40
"""


def _fmt_event(e: TrafficEvent) -> str:
    lines = [
        f"  ID:         {e.id}",
        f"  Roadway:    {e.roadway}  ({e.direction})",
        f"  Type:       {e.event_type} / {e.event_sub_type}",
        f"  Severity:   {e.severity}",
        f"  FullClose:  {e.is_full_closure}",
        f"  Lat/Lng:    {e.lat:.5f}, {e.lng:.5f}",
        f"  Start:      {e.start_date}",
        f"  End:        {e.end_date}",
        f"  Updated:    {e.last_updated}",
        f"  Desc:       {e.description[:120]}",
    ]
    if e.location_description:
        lines.append(f"  At:         {e.location_description}")
    if e.lane_description:
        lines.append(f"  Lanes:      {e.lane_description}")
    return "\n".join(lines)


def main(argv: List[str] = sys.argv[1:]) -> int:  # noqa: B006
    if not argv or argv[0] in ("-h", "--help"):
        print(_HELP)
        return 0

    cmd = argv[0]
    args = argv[1:]
    client = ADOT511Client()

    # ---- cameras ----
    if cmd == "cameras":
        markers = client.list_camera_markers()
        print(f"Total cameras: {len(markers)}")
        for m in markers[:25]:
            print(f"  id={m.item_id:>5}  lat={m.lat:.5f}  lng={m.lng:.6f}")
        if len(markers) > 25:
            print(f"  ... and {len(markers) - 25} more")
        return 0

    if cmd == "camera":
        if not args:
            print("Usage: camera <site_id>", file=sys.stderr)
            return 1
        cam = client.get_camera(args[0])
        print(f"Camera site {cam.id}: {cam.location}")
        print(f"  Roadway:  {cam.roadway}")
        print(f"  Source:   {cam.source} ({cam.source_id})")
        print(f"  Lat/Lng:  {cam.lat:.6f}, {cam.lng:.6f}")
        print(f"  Updated:  {cam.last_updated}")
        print(f"  Images ({len(cam.images)}):")
        for img in cam.images:
            flag = "[DISABLED]" if img.disabled or img.blocked else ""
            print(f"    id={img.id}  {img.description}")
            print(f"         URL: {img.full_image_url} {flag}")
        return 0

    # ---- incidents ----
    if cmd == "incidents":
        events = client.list_incidents()
        print(f"Active incidents: {len(events)}")
        for e in events[:10]:
            print(_fmt_event(e))
            print()
        if len(events) > 10:
            print(f"... and {len(events)-10} more")
        return 0

    # ---- construction ----
    if cmd == "construction":
        events = client.list_construction()
        print(f"Active construction zones: {len(events)}")
        for e in events[:10]:
            print(_fmt_event(e))
            print()
        return 0

    # ---- closures ----
    if cmd == "closures":
        events = client.list_closures()
        print(f"Active closures: {len(events)}")
        for e in events[:10]:
            print(_fmt_event(e))
            print()
        return 0

    # ---- weather-events ----
    if cmd == "weather-events":
        events = client.list_weather_events()
        print(f"Active weather alerts: {len(events)}")
        for e in events[:10]:
            print(f"  ID={e.id}  severity={e.severity}  lat={e.lat:.4f}  lng={e.lng:.4f}")
            if e.comment:
                print(f"  Comment: {e.comment[:120]}")
            if e.description:
                print(f"  Detail:  {e.description[:200]}")
            print()
        return 0

    # ---- weather-forecast ----
    if cmd == "weather-forecast":
        if not args:
            print("Usage: weather-forecast <zone_id>  (e.g. AZZ006)", file=sys.stderr)
            return 1
        zone = client.get_weather_forecast(args[0])
        print(f"Forecast for {zone.zone_id} – {zone.location_name}")
        print(f"  Grid: {zone.grid_id} ({zone.grid_x}, {zone.grid_y})")
        print(f"  Updated: {zone.last_updated}")
        print()
        for p in zone.periods[:6]:
            day_night = "Day  " if p.is_day_time else "Night"
            print(f"  [{day_night}] {p.name:<16} {p.temperature:>3}°F  "
                  f"Wind: {p.wind_speed:>10} {p.wind_direction:<3}  "
                  f"{p.short_forecast}")
        return 0

    # ---- signs ----
    if cmd == "signs":
        signs = client.list_message_signs()
        print(f"Dynamic message signs: {len(signs)}")
        for s in signs[:15]:
            print(f"  [{s.id}] {s.name}  ({s.roadway_name} {s.direction})")
            if s.messages:
                for line in s.messages.strip().split("\n")[:3]:
                    print(f"         {line}")
        return 0

    if cmd == "sign":
        if not args:
            print("Usage: sign <id>", file=sys.stderr)
            return 1
        s = client.get_message_sign(args[0])
        print(f"Sign {s.id}: {s.name}")
        print(f"  Road:    {s.roadway_name} {s.direction}")
        print(f"  Status:  {s.status}")
        print(f"  Updated: {s.last_update}")
        print(f"  Message:\n{s.messages}")
        return 0

    # ---- rest-areas ----
    if cmd == "rest-areas":
        areas = client.list_rest_areas()
        print(f"Rest areas: {len(areas)}")
        for a in areas[:15]:
            amenities = " | ".join(filter(None, [
                "Restroom" if a.has_restroom else "",
                "Ramada" if a.has_ramada else "",
                "Vending" if a.has_vending else "",
            ]))
            print(f"  [{a.id}] {a.name}")
            print(f"         {a.location}, {a.city}")
            print(f"         Amenities: {amenities or 'none listed'}")
        return 0

    # ---- crossings ----
    if cmd == "crossings":
        crossings = client.list_border_crossings()
        print(f"Border crossings: {len(crossings)}")
        for c in crossings:
            print(f"  [{c.id}] {c.name}")
            print(f"         Hours: {c.hours}")
            print(f"         Passenger delay: {c.passenger_delay or 'N/A'}")
            print(f"         Commercial delay: {c.commercial_delay or 'N/A'}")
        return 0

    # ---- special-events ----
    if cmd == "special-events":
        events = client.list_special_events()
        print(f"Special events: {len(events)}")
        for e in events[:10]:
            print(_fmt_event(e))
            print()
        return 0

    # ---- truck-restrictions ----
    if cmd == "truck-restrictions":
        events = client.list_truck_restrictions()
        print(f"Truck restrictions: {len(events)}")
        for e in events[:10]:
            print(_fmt_event(e))
            print()
        return 0

    # ---- save-image ----
    if cmd == "save-image":
        if len(args) < 2:
            print("Usage: save-image <cctv_id> <output_path>", file=sys.stderr)
            return 1
        path = client.save_camera_image(args[0], args[1])
        print(f"Saved camera image to: {path}")
        return 0

    # ---- tile-urls ----
    if cmd == "tile-urls":
        print("Traffic speed tiles (IBI511/TravelIQ CDN):")
        print(f"  {client.traffic_tile_url_template()}")
        print("  NOTE: requires header  Referer: https://www.az511.gov/")
        print()
        print("Weather radar overlay tile (frame=0 = most recent):")
        print(f"  {client.weather_radar_tile_url_template(0)}")
        print()
        print("Milepost WMS overlay tile:")
        print(f"  {client.milepost_tile_url_template()}")
        return 0

    print(f"Unknown command: {cmd!r}\n{_HELP}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
