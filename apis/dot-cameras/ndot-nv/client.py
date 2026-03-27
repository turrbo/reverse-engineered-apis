#!/usr/bin/env python3
"""
NDOT Nevada 511 / NVRoads Traffic Camera & Road Conditions Client
=================================================================

Reverse-engineered client for the Nevada Department of Transportation (NDOT)
traffic information system at https://www.nvroads.com (Nevada 511).

This module exposes every publicly accessible data feed discovered through
static analysis of the site's JavaScript bundles and live network traffic:

  - Camera listing, image snapshots, and HLS video stream URLs
  - Traffic events: incidents, construction, closures, oversized loads,
    future roadwork, special events
  - Road conditions (primary + secondary surface states)
  - Message signs (DMS / VSLS)
  - Weather stations (RWIS — temperature, wind, pavement condition, etc.)
  - Rest areas and truck parking facilities
  - Visitor/tourist locations
  - Tooltip detail pages (HTML fragments served by the same API)

Authentication
--------------
No API key, OAuth token, or registration is required.  All endpoints used
here are the same ones the public-facing website calls from the browser.  A
standard ``User-Agent`` header is sufficient.

Usage
-----
>>> client = NVRoadsClient()
>>> cameras = client.list_cameras(search="I-15", region="Las Vegas")
>>> for cam in cameras:
...     print(cam.roadway, cam.snapshot_url)

CLI
---
Run directly for a live demo::

    python ndot_nv_client.py [--demo] [--cameras] [--events] [--conditions]
                              [--search TERM] [--region REGION]
                              [--save-image ID] [--json]
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.nvroads.com"

#: All recognised list-type identifiers accepted by /List/GetData/{type}
LIST_TYPE_CAMERAS = "Cameras"
LIST_TYPE_TRAFFIC = "traffic"          # umbrella: incidents + closures
LIST_TYPE_CONSTRUCTION = "construction"
LIST_TYPE_CLOSURES = "Closures"
LIST_TYPE_INCIDENTS = "Incidents"
LIST_TYPE_OVERSIZED = "OversizedLoads"
LIST_TYPE_FUTURE_ROADWORK = "FutureRoadwork"
LIST_TYPE_SPECIAL_EVENTS = "SpecialEvents"
LIST_TYPE_WEATHER_STATIONS = "WeatherStations"
LIST_TYPE_ROAD_CONDITIONS = "RoadConditions"
LIST_TYPE_MESSAGE_SIGNS = "MessageSigns"
LIST_TYPE_REST_AREAS = "RestAreas"
LIST_TYPE_TRUCK_PARKING = "TruckParking"
LIST_TYPE_VISITOR = "VisitorLocations"

#: Camera snapshot (JPEG) endpoint — append camera site ID
CCTV_IMAGE_URL = BASE_URL + "/map/Cctv/{id}"

#: Get the HLS playlist URL for a given image/camera ID
VIDEO_URL_ENDPOINT = BASE_URL + "/Camera/GetVideoUrl?imageId={id}"

#: HTML tooltip fragment for any layer item
TOOLTIP_URL = BASE_URL + "/tooltip/{layer_type}/{id}?lang=en&noCss=true"

#: Agency logo endpoint (rarely needed, included for completeness)
AGENCY_LOGO_URL = BASE_URL + "/NoSession/GetCctvAgencyImage?agencyId={id}"

#: KML feed for "nearby 511" POI
NEARBY_KML_URL = BASE_URL + "/NoSession/GetKml?name=Nearby511"

#: Google Maps API key discovered in map bundles (public, rate-limited)
GOOGLE_MAPS_API_KEY = "AIzaSyBS3OuSbmXi_b7d0Rkue7GaZW_4upHg9x4"

#: HLS CDN hostnames used by NDOT's video streaming infrastructure
#  Pattern: d{1-3}wse{1-4}.its.nv.gov:443
HLS_CDN_PATTERN = r"https://d\d+wse\d+\.its\.nv\.gov:443/"

#: Camera image cache-control (60 seconds as set by CloudFront headers)
IMAGE_REFRESH_SECONDS = 60

#: Default page size when fetching lists
DEFAULT_PAGE_SIZE = 100

#: Nevada bounding box (lon_min, lat_min, lon_max, lat_max)
NEVADA_BBOX = (-120.006, 35.001, -114.039, 42.002)

#: Map bounds as returned by map init options
MAP_BOUNDS = {
    "sw": {"lat": 35.360186, "lon": -119.914112},
    "ne": {"lat": 41.988415, "lon": -114.062522},
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NVRoadsClient/1.0; "
        "+https://github.com/user/nvroads-client)"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _parse_wkt_point(wkt: Optional[str]) -> Optional[Tuple[float, float]]:
    """Parse a WKT ``POINT (lon lat)`` string into ``(latitude, longitude)``.

    Returns ``None`` if parsing fails.
    """
    if not wkt:
        return None
    m = re.match(r"POINT\s*\(([0-9.+-]+)\s+([0-9.+-]+)\)", wkt)
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon


def _http_get(url: str, timeout: int = 15) -> bytes:
    """Perform a simple HTTP GET with default headers and return raw bytes."""
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_json(url: str, timeout: int = 15) -> Any:
    """GET a URL and parse the response body as JSON."""
    raw = _http_get(url, timeout=timeout)
    return json.loads(raw.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CameraImage:
    """A single view (image/video pair) associated with a camera site.

    One camera *site* may have multiple views (e.g. north-facing vs
    south-facing).  Each view has its own ``id`` which is used for both the
    snapshot JPEG and the HLS playlist URL.
    """

    id: int
    """Numeric image / camera-view ID used in image and video URL paths."""

    camera_site_id: int
    """Parent camera site ID."""

    sort_order: int
    """Display order among views on the same site (0 = primary)."""

    description: str
    """Human-readable label, e.g. ``"I-15 NB @ Cheyenne"``."""

    image_url: str
    """Absolute URL to the current JPEG snapshot."""

    video_url: Optional[str]
    """HLS playlist URL (``*.m3u8``) or ``None`` if not available."""

    video_type: Optional[str]
    """MIME type, typically ``"application/x-mpegURL"``."""

    is_video_auth_required: bool
    """Whether the HLS stream requires additional authentication."""

    video_disabled: bool
    """Whether video is administratively disabled for this view."""

    blocked: bool
    """Whether the image is blocked at the source (privacy / technical)."""

    disabled: bool
    """Whether this view is currently inactive."""


@dataclass
class Camera:
    """A traffic camera site with one or more views (images/videos).

    Coordinates are stored as ``(latitude, longitude)`` WGS-84 decimal
    degrees.  Both ``lat`` and ``lon`` are ``None`` for cameras whose
    location has not been recorded.
    """

    id: int
    """Unique camera site identifier."""

    roadway: str
    """Intersection or roadway description, e.g. ``"I-15 & Flamingo Rd"``."""

    direction: str
    """Camera orientation, e.g. ``"Northbound"`` or ``"Unknown"``."""

    location: str
    """Verbose location label (may duplicate ``roadway``)."""

    region: Optional[str]
    """NDOT district / metro area, e.g. ``"Las Vegas"``, ``"Reno"``."""

    state: Optional[str]
    """State (always ``"Nevada"`` for Nevada 511 cameras)."""

    lat: Optional[float]
    """WGS-84 latitude in decimal degrees."""

    lon: Optional[float]
    """WGS-84 longitude in decimal degrees."""

    images: List[CameraImage]
    """Ordered list of views for this site (primary view is index 0)."""

    source: Optional[str]
    """Data source identifier, e.g. ``"USER"`` or ``"Cameleon"``."""

    source_id: Optional[str]
    """Upstream system identifier."""

    created: Optional[str]
    """ISO-8601 creation timestamp."""

    last_updated: Optional[str]
    """ISO-8601 timestamp of most recent edit."""

    tooltip_url: str = ""
    """Relative URL to the HTML tooltip fragment."""

    @property
    def snapshot_url(self) -> Optional[str]:
        """URL to the primary JPEG snapshot (first image, or ``None``)."""
        return self.images[0].image_url if self.images else None

    @property
    def primary_video_url(self) -> Optional[str]:
        """HLS stream URL for the primary view, or ``None``."""
        return self.images[0].video_url if self.images else None

    @property
    def has_video(self) -> bool:
        """``True`` if at least one view has a live HLS stream."""
        return any(img.video_url for img in self.images)


@dataclass
class TrafficEvent:
    """A traffic event — incident, construction, closure, etc.

    This dataclass is used for all event list types (``traffic``,
    ``construction``, ``Closures``, ``Incidents``, ``OversizedLoads``,
    ``FutureRoadwork``, ``SpecialEvents``).
    """

    id: int
    """Numeric event ID."""

    type: str
    """Event category, e.g. ``"Closures"``, ``"Construction"``, ``"Incidents"``."""

    layer_name: str
    """Map layer identifier matching the ``type`` value."""

    roadway_name: str
    """Affected roadway, e.g. ``"I-80 EB"``."""

    description: str
    """Full HTML description including lane status, comments, etc."""

    source: str
    """Data source, e.g. ``"ERS"`` (Event Reporting System)."""

    source_id: str
    """Upstream event identifier."""

    event_sub_type: Optional[str]
    """Sub-classification, e.g. ``"bridgeConstruction"``."""

    start_date: Optional[str]
    """Formatted start date/time string."""

    end_date: Optional[str]
    """Formatted anticipated end date/time string (may be ``None``)."""

    last_updated: Optional[str]
    """Formatted last-update timestamp."""

    is_full_closure: bool
    """``True`` if all lanes are blocked."""

    severity: str
    """Severity label: ``"Minor"``, ``"Major"``, ``"None"``, etc."""

    direction: str
    """Travel direction, e.g. ``"West"``, ``"Unknown"``."""

    location_description: Optional[str]
    """Verbose location label."""

    lane_description: Optional[str]
    """Lane status, e.g. ``"All Ramps Closed"``."""

    region: Optional[str]
    """NDOT district / metro area."""

    state: Optional[str]
    """State."""

    show_on_map: bool = True
    """Whether this event is displayed on the public map."""

    comment: Optional[str] = None
    """Internal comment from the event management system."""

    tooltip_url: str = ""
    """Relative URL to the HTML tooltip fragment."""

    # Restriction fields (used for oversized loads)
    width_restriction: Optional[str] = None
    height_restriction: Optional[str] = None
    length_restriction: Optional[str] = None
    weight_restriction: Optional[str] = None


@dataclass
class RoadCondition:
    """Surface condition report for a road segment."""

    id: int
    """Numeric condition record ID."""

    area: str
    """District / metro area."""

    roadway: str
    """Highway / street name."""

    description: str
    """Segment description, e.g. ``"From Summit Ridge Dr to Greg St"``."""

    primary_condition: str
    """Main surface condition: ``"Dry"``, ``"Wet"``, ``"Snowy"``,
    ``"Icy"``, ``"No Report"``, etc."""

    secondary_conditions: List[str]
    """Additional conditions list (may be empty)."""

    stale: bool
    """``True`` if the report has not been refreshed recently."""

    last_updated: Optional[str]
    """Formatted last-update timestamp."""


@dataclass
class WeatherStation:
    """Road-weather information system (RWIS) station."""

    id: int
    """Numeric RWIS station ID."""

    name: str
    """Station name, e.g. ``"US-50 Cave Rock Trailer South"``."""

    organization: Optional[str]
    """Operating organisation, e.g. ``"NV-ATMS-RWIS"``."""

    air_temperature: Optional[str]
    """Air temperature with units, e.g. ``"53.5 °F"``."""

    surface_temperature: Optional[str]
    """Pavement surface temperature (numeric string, °F)."""

    wind_speed_avg: Optional[str]
    """Average wind speed (mph)."""

    wind_speed_gust: Optional[str]
    """Wind gust speed (mph)."""

    wind_direction: Optional[str]
    """Compass direction, e.g. ``"NE"``."""

    relative_humidity: Optional[str]
    """Relative humidity with percent sign."""

    dew_point: Optional[str]
    """Dew-point temperature with units."""

    precipitation: Optional[str]
    """Precipitation type: ``"None"``, ``"Rain"``, ``"SnowSlight"``, etc."""

    precipitation_rate: Optional[str]
    """Precipitation rate (numeric string)."""

    pavement_condition: Optional[str]
    """Pavement state: ``"Dry"``, ``"Wet"``, ``"Ice"``, etc."""

    visibility: Optional[str]
    """Visibility in miles (numeric string)."""

    atmospheric_pressure: Optional[str]
    """Atmospheric pressure in inHg (numeric string)."""

    status: Optional[str]
    """Station operational status, e.g. ``"Ok"``."""

    region: Optional[str]
    """NDOT district."""

    state: Optional[str]
    """State."""

    county: Optional[str]
    """County."""

    last_updated: Optional[str]
    """Formatted last-update timestamp."""

    tooltip_url: str = ""
    """Relative URL to the HTML tooltip fragment."""


@dataclass
class MessageSign:
    """Dynamic message sign / variable speed limit sign (DMS / VSLS)."""

    id: int
    """Numeric sign ID."""

    name: str
    """Sign name / identifier, e.g. ``"I-15 SB @ N OF BONAZA RD - C"``."""

    roadway_name: str
    """Roadway where the sign is located."""

    direction: str
    """Travel direction covered, e.g. ``"Southbound"``."""

    area: Optional[str]
    """District / metro area."""

    message: str
    """Primary message line currently displayed (empty if blank)."""

    message2: str
    """Secondary message line."""

    message3: str
    """Tertiary message line."""

    status: str
    """Sign operational status, e.g. ``"on"``, ``"off"``."""

    last_updated: Optional[str]
    """Formatted last-update timestamp."""

    tooltip_url: str = ""
    """Relative URL to the HTML tooltip fragment."""


@dataclass
class POILocation:
    """Generic point-of-interest (rest area, truck parking, visitor centre)."""

    id: int
    """Numeric POI ID."""

    name: str
    """Facility name."""

    area: Optional[str]
    """Geographic area code or district."""

    organization: Optional[str]
    """Operating organisation."""

    region: Optional[str]
    """NDOT district / metro area."""

    filter_props: Dict[str, Optional[str]] = field(default_factory=dict)
    """Extra filterable/display properties (``filterAndOrderProperty1``–``10``)."""

    last_updated: Optional[str] = None
    """Formatted last-update timestamp."""

    tooltip_url: str = ""
    """Relative URL to the HTML tooltip fragment."""


@dataclass
class ListResponse:
    """Paginated response wrapper for any ``/List/GetData/`` call."""

    records_total: int
    """Total number of matching records (before pagination)."""

    records_filtered: int
    """Records after server-side filtering."""

    data: List[Any]
    """Page of decoded dataclass objects."""

    draw: int = 0
    """Echo of the DataTables ``draw`` counter."""


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


def _parse_camera_image(raw: Dict[str, Any]) -> CameraImage:
    base = BASE_URL
    raw_img_url = raw.get("imageUrl", "")
    img_url = (base + raw_img_url) if raw_img_url.startswith("/") else raw_img_url
    return CameraImage(
        id=raw.get("id", 0),
        camera_site_id=raw.get("cameraSiteId", 0),
        sort_order=raw.get("sortOrder", 0),
        description=raw.get("description") or "",
        image_url=img_url,
        video_url=raw.get("videoUrl") or None,
        video_type=raw.get("videoType") or None,
        is_video_auth_required=bool(raw.get("isVideoAuthRequired", False)),
        video_disabled=bool(raw.get("videoDisabled", False)),
        blocked=bool(raw.get("blocked", False)),
        disabled=bool(raw.get("disabled", False)),
    )


def _parse_camera(raw: Dict[str, Any]) -> Camera:
    lat_lon = _parse_wkt_point(
        (raw.get("latLng") or {})
        .get("geography", {})
        .get("wellKnownText")
    )
    lat = lat_lon[0] if lat_lon else None
    lon = lat_lon[1] if lat_lon else None
    images = [_parse_camera_image(img) for img in raw.get("images") or []]
    return Camera(
        id=raw.get("id", 0),
        roadway=raw.get("roadway") or "",
        direction=raw.get("direction") or "Unknown",
        location=raw.get("location") or "",
        region=raw.get("region"),
        state=raw.get("state"),
        lat=lat,
        lon=lon,
        images=images,
        source=raw.get("source"),
        source_id=raw.get("sourceId"),
        created=raw.get("created"),
        last_updated=raw.get("lastUpdated"),
        tooltip_url=raw.get("tooltipUrl") or "",
    )


def _parse_event(raw: Dict[str, Any]) -> TrafficEvent:
    return TrafficEvent(
        id=raw.get("id", 0),
        type=raw.get("type") or "",
        layer_name=raw.get("layerName") or "",
        roadway_name=raw.get("roadwayName") or "",
        description=raw.get("description") or "",
        source=raw.get("source") or "",
        source_id=raw.get("sourceId") or "",
        event_sub_type=raw.get("eventSubType"),
        start_date=raw.get("startDate"),
        end_date=raw.get("endDate"),
        last_updated=raw.get("lastUpdated"),
        is_full_closure=bool(raw.get("isFullClosure", False)),
        severity=raw.get("severity") or "None",
        direction=raw.get("direction") or "Unknown",
        location_description=raw.get("locationDescription"),
        lane_description=raw.get("laneDescription"),
        region=raw.get("region"),
        state=raw.get("state"),
        show_on_map=bool(raw.get("showOnMap", True)),
        comment=raw.get("comment"),
        tooltip_url=raw.get("tooltipUrl") or "",
        width_restriction=raw.get("widthRestriction"),
        height_restriction=raw.get("heightRestriction"),
        length_restriction=raw.get("lengthRestriction"),
        weight_restriction=raw.get("weightRestriction"),
    )


def _parse_road_condition(raw: Dict[str, Any]) -> RoadCondition:
    secondary = raw.get("secondaryConditions") or []
    return RoadCondition(
        id=raw.get("id", 0),
        area=raw.get("area") or "",
        roadway=raw.get("roadway") or "",
        description=raw.get("description") or "",
        primary_condition=raw.get("primaryCondition") or "No Report",
        secondary_conditions=list(secondary),
        stale=bool(raw.get("stale", False)),
        last_updated=raw.get("lastUpdated"),
    )


def _parse_weather_station(raw: Dict[str, Any]) -> WeatherStation:
    return WeatherStation(
        id=int(raw.get("DT_RowId", 0)),
        name=raw.get("name") or raw.get("filterAndOrderProperty1") or "",
        organization=raw.get("organization"),
        air_temperature=raw.get("airTemperature"),
        surface_temperature=raw.get("surfaceTemperature"),
        wind_speed_avg=raw.get("windSpeedAverage"),
        wind_speed_gust=raw.get("windSpeedGust"),
        wind_direction=raw.get("windDirectionAverage"),
        relative_humidity=raw.get("relativeHumidity"),
        dew_point=raw.get("dewPoint"),
        precipitation=raw.get("precipitation") or raw.get("rain"),
        precipitation_rate=raw.get("precipitationRate"),
        pavement_condition=raw.get("pavementCondition"),
        visibility=raw.get("visibility"),
        atmospheric_pressure=raw.get("atmosphericPressure"),
        status=raw.get("status"),
        region=raw.get("region"),
        state=raw.get("state"),
        county=raw.get("county"),
        last_updated=raw.get("lastUpdated"),
        tooltip_url=raw.get("tooltipUrl") or "",
    )


def _parse_message_sign(raw: Dict[str, Any]) -> MessageSign:
    return MessageSign(
        id=int(raw.get("DT_RowId", 0)),
        name=raw.get("name") or "",
        roadway_name=raw.get("roadwayName") or "",
        direction=raw.get("direction") or "Unknown",
        area=raw.get("area"),
        message=raw.get("message") or "",
        message2=raw.get("message2") or "",
        message3=raw.get("message3") or "",
        status=raw.get("status") or "unknown",
        last_updated=raw.get("lastUpdated"),
        tooltip_url=raw.get("tooltipUrl") or "",
    )


def _parse_poi(raw: Dict[str, Any]) -> POILocation:
    fp = {
        k: raw.get(k)
        for k in raw
        if k.startswith("filterAndOrderProperty")
    }
    return POILocation(
        id=int(raw.get("DT_RowId", 0)),
        name=(
            raw.get("filterAndOrderProperty1")
            or raw.get("filterAndOrderProperty2")
            or ""
        ),
        area=raw.get("area"),
        organization=raw.get("organization"),
        region=raw.get("region"),
        filter_props=fp,
        last_updated=raw.get("lastUpdated"),
        tooltip_url=raw.get("tooltipUrl") or "",
    )


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------


class NVRoadsClient:
    """Python client for the Nevada 511 / NVRoads traffic information API.

    All HTTP calls are synchronous and use only the Python standard library
    (``urllib``, ``json``).  No third-party dependencies are required.

    Parameters
    ----------
    timeout:
        Socket timeout in seconds for all HTTP requests.  Default: ``15``.
    base_url:
        Override the base URL (useful for testing against a proxy).

    Examples
    --------
    >>> client = NVRoadsClient()

    List all cameras in the Las Vegas corridor::

        cameras = client.list_cameras(region="Las Vegas")

    Get cameras on I-15 with live video::

        for cam in client.list_cameras(search="I-15"):
            if cam.has_video:
                print(cam.roadway, cam.primary_video_url)

    Get current traffic events on I-80::

        events = client.list_events(search="I-80")

    Download the latest snapshot for camera 4746::

        jpeg_bytes = client.get_camera_image(4746)
        with open("camera_4746.jpg", "wb") as f:
            f.write(jpeg_bytes)
    """

    def __init__(
        self,
        timeout: int = 15,
        base_url: str = BASE_URL,
    ) -> None:
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _build_query_url(
        self,
        list_type: str,
        columns: Optional[List[Dict[str, Any]]] = None,
        search: Optional[str] = None,
        column_filters: Optional[Dict[str, str]] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
        order: Optional[List[Dict[str, Any]]] = None,
        lang: str = "en",
    ) -> str:
        """Build the full GET URL for a ``/List/GetData/`` request.

        The site uses DataTables server-side processing.  The ``query``
        parameter is a JSON-encoded DataTables request object, and ``lang``
        is the UI language code.

        Parameters
        ----------
        list_type:
            The data category, e.g. ``"Cameras"``, ``"traffic"``.
        columns:
            DataTables column descriptor list.  If ``None``, an empty list
            is used, which returns all server-side fields.
        search:
            Global search string applied across all searchable columns.
        column_filters:
            Per-column search values keyed by column ``name``.
        start:
            Pagination offset (0-based).
        length:
            Page size (max 100 enforced server-side; use pagination for more).
        order:
            DataTables order list, e.g. ``[{"column": 0, "dir": "asc"}]``.
        lang:
            Language code.  Only ``"en"`` is active on nvroads.com.
        """
        cols: List[Dict[str, Any]] = columns or []

        # Apply per-column search values
        if column_filters:
            existing = {c.get("name"): i for i, c in enumerate(cols)}
            for col_name, col_val in column_filters.items():
                if col_name in existing:
                    cols[existing[col_name]]["search"] = {
                        "value": col_val,
                        "regex": False,
                    }
                else:
                    cols.append({
                        "name": col_name,
                        "searchable": True,
                        "search": {"value": col_val, "regex": False},
                    })

        query_obj: Dict[str, Any] = {
            "columns": cols,
            "order": order or [{"column": 0, "dir": "asc"}],
            "start": start,
            "length": length,
            "search": {"value": search or "", "regex": False},
        }
        params = urllib.parse.urlencode({
            "query": json.dumps(query_obj, separators=(",", ":")),
            "lang": lang,
        })
        return f"{self.base_url}/List/GetData/{list_type}?{params}"

    def _get_list(
        self,
        list_type: str,
        parser,
        search: Optional[str] = None,
        column_filters: Optional[Dict[str, str]] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> ListResponse:
        """Fetch a page of list data and parse each row with ``parser``."""
        url = self._build_query_url(
            list_type,
            search=search,
            column_filters=column_filters,
            start=start,
            length=length,
        )
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.load(resp)

        rows = [parser(row) for row in (payload.get("data") or [])]
        return ListResponse(
            records_total=payload.get("recordsTotal", 0),
            records_filtered=payload.get("recordsFiltered", 0),
            data=rows,
            draw=payload.get("draw", 0),
        )

    def _get_all_pages(
        self,
        list_type: str,
        parser,
        search: Optional[str] = None,
        column_filters: Optional[Dict[str, str]] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> List[Any]:
        """Paginate through all results for a list type, returning a flat list.

        This method automatically fetches additional pages until all records
        have been retrieved.

        .. warning::

            The server enforces a maximum of 100 rows per request.  Very large
            data sets (e.g. all 643 cameras) will require multiple round-trips.
        """
        result: List[Any] = []
        start = 0
        while True:
            page = self._get_list(
                list_type,
                parser,
                search=search,
                column_filters=column_filters,
                start=start,
                length=min(page_size, 100),
            )
            result.extend(page.data)
            start += len(page.data)
            if start >= page.records_filtered or not page.data:
                break
        return result

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def list_cameras(
        self,
        search: Optional[str] = None,
        region: Optional[str] = None,
        roadway: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[Camera]:
        """Return a list of traffic cameras.

        Parameters
        ----------
        search:
            Full-text search across all searchable fields (roadway name,
            description, region, etc.).
        region:
            Filter by NDOT district.  Known values: ``"Las Vegas"``,
            ``"Reno"``, ``"Elko"``, ``"Carson City"``, ``"Ely"``.
        roadway:
            Filter by roadway name substring, e.g. ``"I-15"``, ``"I-80"``,
            ``"US-93"``.
        start:
            Pagination start offset.
        length:
            Number of records to return (max 100 per request).

        Returns
        -------
        list[Camera]
            Parsed camera objects sorted by sort_order then roadway.

        Examples
        --------
        >>> client = NVRoadsClient()
        >>> i15_cams = client.list_cameras(search="I-15", region="Las Vegas")
        >>> for cam in i15_cams[:3]:
        ...     print(cam.id, cam.roadway, cam.lat, cam.lon)
        """
        col_filters: Dict[str, str] = {}
        if region:
            col_filters["region"] = region
        if roadway:
            col_filters["roadway"] = roadway

        resp = self._get_list(
            LIST_TYPE_CAMERAS,
            _parse_camera,
            search=search,
            column_filters=col_filters or None,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    def list_cameras_all(
        self,
        search: Optional[str] = None,
        region: Optional[str] = None,
        roadway: Optional[str] = None,
    ) -> List[Camera]:
        """Return *all* cameras matching the given filters (handles pagination).

        For the full Nevada camera fleet this makes ~7 requests (643 cameras
        at 100 per page).
        """
        col_filters: Dict[str, str] = {}
        if region:
            col_filters["region"] = region
        if roadway:
            col_filters["roadway"] = roadway
        return self._get_all_pages(
            LIST_TYPE_CAMERAS,
            _parse_camera,
            search=search,
            column_filters=col_filters or None,
        )  # type: ignore[return-value]

    def get_camera_image(self, camera_id: int) -> bytes:
        """Download the current JPEG snapshot for a camera.

        The image is served from CloudFront with a 60-second cache-control
        header — polling more frequently than once per minute will usually
        return the same cached frame.

        Parameters
        ----------
        camera_id:
            The numeric camera site ID (``Camera.id``).

        Returns
        -------
        bytes
            Raw JPEG image data.

        Examples
        --------
        >>> data = client.get_camera_image(4746)
        >>> with open("snapshot.jpg", "wb") as f: f.write(data)
        """
        url = f"{self.base_url}/map/Cctv/{camera_id}"
        req = urllib.request.Request(url, headers={
            **DEFAULT_HEADERS,
            "Accept": "image/jpeg,image/*",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def get_camera_video_url(self, image_id: int) -> Optional[str]:
        """Resolve the HLS playlist URL for a given camera image/view ID.

        This endpoint returns either a plain string (the direct HLS URL) or a
        JSON object when the URL requires additional construction.  The client
        handles both cases.

        Parameters
        ----------
        image_id:
            The numeric image/view ID (``CameraImage.id``).

        Returns
        -------
        str or None
            The resolved HLS ``*.m3u8`` playlist URL, or ``None`` on failure.

        Examples
        --------
        >>> url = client.get_camera_video_url(2)
        >>> print(url)
        https://d2wse2.its.nv.gov:443/.../playlist.m3u8
        """
        api_url = f"{self.base_url}/Camera/GetVideoUrl?imageId={image_id}"
        req = urllib.request.Request(api_url, headers=DEFAULT_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace").strip()
            # Response is a JSON string (quoted URL) or JSON object
            parsed = json.loads(raw)
            if isinstance(parsed, str):
                return parsed
            if isinstance(parsed, dict):
                # Partial URL: needs a POST to resources.CameraVideoUrl
                # (currently empty on nvroads.com — direct URL is always used)
                return parsed.get("url") or None
            return None
        except Exception:
            return None

    def get_tooltip(self, layer_type: str, item_id: int) -> str:
        """Return the HTML tooltip fragment for any map layer item.

        Parameters
        ----------
        layer_type:
            Layer identifier, e.g. ``"Cameras"``, ``"Construction"``,
            ``"WeatherStations"``, ``"MessageSigns"``.
        item_id:
            Numeric item ID.

        Returns
        -------
        str
            Raw HTML string (Bootstrap-styled table fragment).
        """
        url = (
            f"{self.base_url}/tooltip/{layer_type}/{item_id}"
            "?lang=en&noCss=true"
        )
        req = urllib.request.Request(url, headers={
            **DEFAULT_HEADERS,
            "Accept": "text/html,*/*",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Traffic events
    # ------------------------------------------------------------------

    def list_events(
        self,
        event_type: str = LIST_TYPE_TRAFFIC,
        search: Optional[str] = None,
        region: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[TrafficEvent]:
        """Return a list of traffic events.

        Parameters
        ----------
        event_type:
            Which event category to query.  Use one of the module-level
            ``LIST_TYPE_*`` constants:

            - ``LIST_TYPE_TRAFFIC`` (``"traffic"``) — all active events
            - ``LIST_TYPE_CONSTRUCTION`` — road-work / maintenance
            - ``LIST_TYPE_CLOSURES`` — full/partial closures
            - ``LIST_TYPE_INCIDENTS`` — accidents / hazards
            - ``LIST_TYPE_OVERSIZED`` — oversized load permits
            - ``LIST_TYPE_FUTURE_ROADWORK`` — planned future work
            - ``LIST_TYPE_SPECIAL_EVENTS`` — special events

        search:
            Full-text search across roadway, description, etc.
        region:
            Restrict to a specific NDOT district.
        start / length:
            Pagination parameters.

        Examples
        --------
        >>> incidents = client.list_events(LIST_TYPE_INCIDENTS)
        >>> closures_i80 = client.list_events(
        ...     LIST_TYPE_CLOSURES, search="I-80"
        ... )
        """
        col_filters: Dict[str, str] = {}
        if region:
            col_filters["region"] = region
        resp = self._get_list(
            event_type,
            _parse_event,
            search=search,
            column_filters=col_filters or None,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    def list_all_active_events(
        self,
        search: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[TrafficEvent]:
        """Return *all* currently active events (incidents + closures + construction).

        This queries the umbrella ``"traffic"`` endpoint which includes all
        active event types in a single result set.
        """
        return self._get_all_pages(
            LIST_TYPE_TRAFFIC,
            _parse_event,
            search=search,
            column_filters={"region": region} if region else None,
        )  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Road conditions
    # ------------------------------------------------------------------

    def list_road_conditions(
        self,
        search: Optional[str] = None,
        area: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[RoadCondition]:
        """Return road surface condition reports.

        Parameters
        ----------
        search:
            Full-text search across roadway names and descriptions.
        area:
            Filter by area/district, e.g. ``"Reno"``, ``"Las Vegas"``.
        start / length:
            Pagination parameters.

        Returns
        -------
        list[RoadCondition]
            Surface condition objects (434 Nevada segments are available).

        Examples
        --------
        >>> conditions = client.list_road_conditions(search="I-80")
        >>> for rc in conditions:
        ...     if rc.primary_condition != "No Report":
        ...         print(rc.roadway, rc.primary_condition)
        """
        col_filters: Dict[str, str] = {}
        if area:
            col_filters["area"] = area
        resp = self._get_list(
            LIST_TYPE_ROAD_CONDITIONS,
            _parse_road_condition,
            search=search,
            column_filters=col_filters or None,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Weather stations (RWIS)
    # ------------------------------------------------------------------

    def list_weather_stations(
        self,
        search: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[WeatherStation]:
        """Return road-weather information system (RWIS) station data.

        Parameters
        ----------
        search:
            Full-text search across station names and locations.
        start / length:
            Pagination parameters.

        Returns
        -------
        list[WeatherStation]
            Weather station objects with live atmospheric readings.
            There are 126 active RWIS stations in Nevada.

        Examples
        --------
        >>> stations = client.list_weather_stations(search="US-50")
        >>> for ws in stations:
        ...     print(ws.name, ws.air_temperature, ws.pavement_condition)
        """
        resp = self._get_list(
            LIST_TYPE_WEATHER_STATIONS,
            _parse_weather_station,
            search=search,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Message signs (DMS/VSLS)
    # ------------------------------------------------------------------

    def list_message_signs(
        self,
        search: Optional[str] = None,
        area: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[MessageSign]:
        """Return dynamic message sign (DMS) current display content.

        Parameters
        ----------
        search:
            Full-text search across sign name, roadway, and message.
        area:
            Filter by area, e.g. ``"Las Vegas"``, ``"Reno"``.
        start / length:
            Pagination parameters.

        Returns
        -------
        list[MessageSign]
            382 signs total; many show blank messages when no advisory is
            active.

        Examples
        --------
        >>> signs = client.list_message_signs(search="I-15", area="Las Vegas")
        >>> for s in signs:
        ...     if s.message:
        ...         print(s.name, "|", s.message)
        """
        col_filters: Dict[str, str] = {}
        if area:
            col_filters["area"] = area
        resp = self._get_list(
            LIST_TYPE_MESSAGE_SIGNS,
            _parse_message_sign,
            search=search,
            column_filters=col_filters or None,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Points of interest
    # ------------------------------------------------------------------

    def list_rest_areas(
        self,
        search: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[POILocation]:
        """Return Nevada highway rest area facilities (35 locations)."""
        resp = self._get_list(
            LIST_TYPE_REST_AREAS,
            _parse_poi,
            search=search,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    def list_truck_parking(
        self,
        search: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[POILocation]:
        """Return commercial truck parking locations (56 facilities)."""
        resp = self._get_list(
            LIST_TYPE_TRUCK_PARKING,
            _parse_poi,
            search=search,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    def list_visitor_locations(
        self,
        search: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[POILocation]:
        """Return visitor / tourist information center locations."""
        resp = self._get_list(
            LIST_TYPE_VISITOR,
            _parse_poi,
            search=search,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    def list_oversized_loads(
        self,
        search: Optional[str] = None,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
    ) -> List[TrafficEvent]:
        """Return oversized/overweight load permit events."""
        resp = self._get_list(
            LIST_TYPE_OVERSIZED,
            _parse_event,
            search=search,
            start=start,
            length=length,
        )
        return resp.data  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Count helpers
    # ------------------------------------------------------------------

    def count_cameras(self) -> int:
        """Return the total number of cameras in the system."""
        url = self._build_query_url(LIST_TYPE_CAMERAS, length=1)
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp).get("recordsTotal", 0)

    def count_events(self, event_type: str = LIST_TYPE_TRAFFIC) -> int:
        """Return the total number of active events of the given type."""
        url = self._build_query_url(event_type, length=1)
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp).get("recordsTotal", 0)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _print_separator(title: str = "") -> None:
    width = 70
    if title:
        pad = (width - len(title) - 2) // 2
        print("\n" + "=" * pad + " " + title + " " + "=" * pad)
    else:
        print("\n" + "=" * width)


def _demo_cameras(client: NVRoadsClient, search: Optional[str] = None) -> None:
    _print_separator("CAMERAS")
    query = search or "I-15"
    cameras = client.list_cameras(search=query, length=10)
    print(f"Search '{query}' — showing first {len(cameras)} cameras:\n")
    for cam in cameras:
        coord = ""
        if cam.lat and cam.lon:
            coord = f"  [{cam.lat:.4f}, {cam.lon:.4f}]"
        print(f"  [{cam.id:5d}] {cam.roadway:<45} {cam.region or '':12}{coord}")
        if cam.images:
            img = cam.images[0]
            print(f"          Snapshot : {img.image_url}")
            if img.video_url:
                print(f"          HLS video: {img.video_url[:70]}...")
        print()


def _demo_events(client: NVRoadsClient, search: Optional[str] = None) -> None:
    _print_separator("TRAFFIC EVENTS")
    query = search or ""
    events = client.list_events(LIST_TYPE_TRAFFIC, search=query, length=5)
    total = client.count_events(LIST_TYPE_TRAFFIC)
    print(f"Active traffic events (total: {total}) — showing {len(events)}:\n")
    for ev in events:
        closure_flag = " [CLOSURE]" if ev.is_full_closure else ""
        print(f"  [{ev.id:6d}] {ev.type:<18} {ev.roadway_name:<25}{closure_flag}")
        print(f"          Severity: {ev.severity}  |  Direction: {ev.direction}")
        # Strip HTML tags from description for CLI display
        desc = re.sub(r"<[^>]+>", " ", ev.description)
        desc = re.sub(r"\s+", " ", desc).strip()[:100]
        print(f"          Desc: {desc}")
        print()


def _demo_conditions(client: NVRoadsClient, search: Optional[str] = None) -> None:
    _print_separator("ROAD CONDITIONS")
    query = search or "I-80"
    conditions = client.list_road_conditions(search=query, length=8)
    print(f"Road conditions for '{query}' — {len(conditions)} segments:\n")
    for rc in conditions:
        stale_flag = " (STALE)" if rc.stale else ""
        print(f"  {rc.roadway:<40} {rc.primary_condition:<20}{stale_flag}")
        if rc.secondary_conditions:
            print(f"    Secondary: {', '.join(rc.secondary_conditions)}")
    print()


def _demo_weather(client: NVRoadsClient) -> None:
    _print_separator("WEATHER STATIONS (RWIS)")
    stations = client.list_weather_stations(length=5)
    total = 126
    print(f"RWIS stations (total ~{total}) — showing first {len(stations)}:\n")
    for ws in stations:
        print(f"  [{ws.id:6d}] {ws.name:<45} Status: {ws.status}")
        print(f"          Air temp: {ws.air_temperature}  |  "
              f"Pavement: {ws.pavement_condition}  |  "
              f"Wind: {ws.wind_direction}@{ws.wind_speed_avg} mph")
        print(f"          Precip: {ws.precipitation}  |  "
              f"Visibility: {ws.visibility} mi")
        print()


def _demo_message_signs(client: NVRoadsClient) -> None:
    _print_separator("MESSAGE SIGNS (DMS)")
    signs = client.list_message_signs(length=5)
    total = client.count_events(LIST_TYPE_MESSAGE_SIGNS)
    active = [s for s in signs if s.message.strip()]
    print(f"DMS signs (total: {total}) — showing first {len(signs)} "
          f"({len(active)} with active messages):\n")
    for s in signs:
        print(f"  [{s.id:6d}] {s.name:<45} Status: {s.status}")
        if s.message:
            print(f"          Line 1: {s.message}")
        if s.message2:
            print(f"          Line 2: {s.message2}")
        print()


def _demo_save_image(client: NVRoadsClient, camera_id: int) -> None:
    _print_separator(f"SNAPSHOT — camera {camera_id}")
    print(f"Downloading JPEG snapshot for camera ID {camera_id}...")
    img_bytes = client.get_camera_image(camera_id)
    filename = f"camera_{camera_id}_{int(time.time())}.jpg"
    with open(filename, "wb") as f:
        f.write(img_bytes)
    print(f"Saved {len(img_bytes):,} bytes to {filename}")

    video_url = client.get_camera_video_url(camera_id)
    if video_url:
        print(f"HLS video URL (m3u8): {video_url}")
    else:
        print("No HLS video stream available for this camera.")


def _print_usage() -> None:
    print(__doc__)
    print("Usage: python ndot_nv_client.py [OPTIONS]\n")
    print("Options:")
    print("  --demo             Run full live API demonstration (default)")
    print("  --cameras          Show camera listing demo")
    print("  --events           Show traffic events demo")
    print("  --conditions       Show road conditions demo")
    print("  --weather          Show RWIS weather stations demo")
    print("  --signs            Show DMS message signs demo")
    print("  --search TERM      Apply search term to camera/event/condition demos")
    print("  --region REGION    Filter cameras by region (e.g. 'Las Vegas')")
    print("  --save-image ID    Download and save a camera snapshot to disk")
    print("  --json             Print all results as JSON instead of formatted text")
    print("  --help             Show this help")


def main(argv: Optional[List[str]] = None) -> int:
    """Command-line entry point for the NVRoads client demo."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Nevada 511 (NVRoads) Traffic Data CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--demo", action="store_true", default=True,
                        help="Run full demo (default)")
    parser.add_argument("--cameras", action="store_true")
    parser.add_argument("--events", action="store_true")
    parser.add_argument("--conditions", action="store_true")
    parser.add_argument("--weather", action="store_true")
    parser.add_argument("--signs", action="store_true")
    parser.add_argument("--search", metavar="TERM", default=None)
    parser.add_argument("--region", metavar="REGION", default=None)
    parser.add_argument("--save-image", metavar="ID", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=int, default=15)

    args = parser.parse_args(argv)
    explicit = any([
        args.cameras, args.events, args.conditions,
        args.weather, args.signs, args.save_image is not None,
    ])

    client = NVRoadsClient(timeout=args.timeout)

    print("=" * 70)
    print("  Nevada 511 / NVRoads Traffic Data Client — Live Demo")
    print("  Target: https://www.nvroads.com")
    print("=" * 70)

    if args.json:
        # JSON output mode — collect everything and dump
        result: Dict[str, Any] = {}
        if not explicit or args.cameras:
            cams = client.list_cameras(search=args.search, region=args.region, length=10)
            result["cameras"] = [
                {
                    "id": c.id, "roadway": c.roadway, "region": c.region,
                    "lat": c.lat, "lon": c.lon,
                    "snapshot_url": c.snapshot_url,
                    "video_url": c.primary_video_url,
                    "has_video": c.has_video,
                }
                for c in cams
            ]
        if not explicit or args.events:
            events = client.list_events(length=10)
            result["events"] = [
                {
                    "id": e.id, "type": e.type, "roadway": e.roadway_name,
                    "is_full_closure": e.is_full_closure,
                    "severity": e.severity, "region": e.region,
                }
                for e in events
            ]
        if not explicit or args.conditions:
            conds = client.list_road_conditions(search=args.search, length=10)
            result["road_conditions"] = [
                {
                    "id": rc.id, "roadway": rc.roadway,
                    "primary_condition": rc.primary_condition,
                    "stale": rc.stale,
                }
                for rc in conds
            ]
        print(json.dumps(result, indent=2))
        return 0

    try:
        if not explicit or args.cameras:
            _demo_cameras(client, search=args.search)
        if not explicit or args.events:
            _demo_events(client, search=args.search)
        if not explicit or args.conditions:
            _demo_conditions(client, search=args.search)
        if not explicit or args.weather:
            _demo_weather(client)
        if not explicit or args.signs:
            _demo_message_signs(client)
        if args.save_image is not None:
            _demo_save_image(client, args.save_image)

        _print_separator()
        # Summary counts
        print("\nSystem snapshot (live record counts):")
        counts = {
            "Cameras": client.count_cameras(),
            "Active Events": client.count_events(LIST_TYPE_TRAFFIC),
            "Construction": client.count_events(LIST_TYPE_CONSTRUCTION),
            "Closures": client.count_events(LIST_TYPE_CLOSURES),
            "Incidents": client.count_events(LIST_TYPE_INCIDENTS),
        }
        for k, v in counts.items():
            print(f"  {k:<22}: {v:,}")
        print()

    except urllib.error.URLError as exc:
        print(f"\nNetwork error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
