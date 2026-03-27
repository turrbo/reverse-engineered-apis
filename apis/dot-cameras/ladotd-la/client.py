#!/usr/bin/env python3
"""
Louisiana Department of Transportation & Development (LaDOTD) 511LA Traffic API Client.

Reverse-engineered from https://www.511la.org — the official Louisiana statewide
511 traveler information system operated by LADOTD / IBI Group.

This module provides a pure-stdlib Python client (no third-party dependencies) for
every publicly accessible data feed exposed by 511la.org, including:

  - Traffic cameras (336 statewide) with JPEG snapshots and HLS video streams
  - Incidents, construction, and road closures
  - Variable Message Signs (DMS) with current messages
  - Movable bridge open/closed status
  - Ferry terminal status and schedule
  - Highway rest area amenities
  - Weather events, NWS zone forecasts, and weather radar tile URL
  - Waze-sourced crowd-reported incidents and closures
  - Geographic layers: traffic speed tiles, KMZ parish/district boundaries
  - Route planning helpers (geocoding along the network, route geometry)

Discovered API surface
----------------------
Base URL: https://www.511la.org

Map layer data (marker positions + item IDs):
  GET /map/mapIcons/{layerId}
  → JSON {"item1": <default_icon>, "item2": [{itemId, location:[lat,lon], ...}, ...]}
  layerIds: Cameras, Incidents, Construction, Closures, ClosuresPolyline, SpecialEvents,
            WeatherReports, WeatherIncidents, WeatherClosures, WeatherEvents,
            WeatherForecast, MessageSigns, Bridge, FerryTerminals, RestAreas,
            Waze, WazeIncidents, WazeClosures

List/table data (rich structured records):
  GET /List/GetData/{layerId}?query=<JSON>&lang=en
  → DataTables server-side JSON {"draw", "recordsTotal", "recordsFiltered", "data":[...]}
  layerIds (confirmed): Cameras, Incidents, Construction, Closures, SpecialEvents,
                        MessageSigns, Bridge, FerryTerminals, RestAreas,
                        WazeIncidents, WazeClosures

Camera snapshot image:
  GET /map/Cctv/{imageId}
  → image/jpeg (10-second max-age, served via CloudFront)
  Refresh rate: 10 000 ms (10 seconds) per resources.CameraRefreshRateMs

Camera HLS video stream:
  data-videourl attribute from List/GetData/Cameras → images[].videoUrl
  Served from three regional LADOTD streaming servers:
    https://ITSStreamingBR.dotd.la.gov/public/{stream-id}.streams/playlist.m3u8
    https://ITSStreamingBR2.dotd.la.gov/public/{stream-id}.streams/playlist.m3u8
    https://ITSStreamingNO.dotd.la.gov/public/{stream-id}.streams/playlist.m3u8
  Stream name prefixes (regional codes): br, laf, lkc, mnr, shr, hou, nor, ns

Camera video URL lookup:
  GET /Camera/GetVideoUrl?imageId={id}
  → JSON string (the m3u8 URL)

Tooltip/detail HTML:
  GET /tooltip/{layerId}/{itemId}?lang=en
  → HTML fragment suitable for modal/sidebar display

Unique filter values (camera-focused):
  GET /List/UniqueColumnValuesForCctv/{layerId}
  → JSON {"state": [...], "region": [...], "roadway": [...], ...}

Route network geocoding:
  GET /api/route/getlocations?latitude={lat}&longitude={lon}&zoom={z}
  → JSON array of road-segment objects with name, linkId, direction, travelTimeDisplay

Geographic layers (KMZ):
  GET https://511la.org/Content/LU/KML/Parish.kmz
  GET https://511la.org/Content/LU/KML/District.kmz

Traffic speed tiles (XYZ):
  https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}

Google Maps API key (public, embedded in page):
  AIzaSyAqkBAboYbLsHyVVa7K1lHZSQBdyWTHcFw  (key belongs to LADOTD/IBI; use sparingly)

Authentication: None required for any read endpoint. Session-based login (/My511/Login)
only gates personalised "My Cameras" / "My Routes" features.

Usage (CLI demo)
----------------
  python3 ladotd_client.py cameras           # list cameras with video streams
  python3 ladotd_client.py incidents         # active incidents
  python3 ladotd_client.py construction      # active construction events
  python3 ladotd_client.py closures          # active closures
  python3 ladotd_client.py signs             # variable message signs
  python3 ladotd_client.py bridges           # movable bridge status
  python3 ladotd_client.py ferries           # ferry terminal status
  python3 ladotd_client.py restareas         # highway rest areas
  python3 ladotd_client.py waze              # Waze crowd-reported incidents
  python3 ladotd_client.py weather           # weather events on map
  python3 ladotd_client.py forecast          # NWS zone forecast locations
  python3 ladotd_client.py snapshot <id>     # save camera snapshot to PNG
  python3 ladotd_client.py geocode <lat> <lon>  # road names at coordinate

Author: Reverse-engineered from public 511la.org JavaScript bundles
Date: 2026-03-27
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.511la.org"

#: Camera snapshot image base URL — append /{imageId}
CAMERA_IMAGE_URL = f"{BASE_URL}/map/Cctv"

#: Streaming CDN hostnames operated by LADOTD/ITS
STREAMING_HOSTS = [
    "ITSStreamingBR.dotd.la.gov",   # Baton Rouge 1 (br-cam-*)
    "ITSStreamingBR2.dotd.la.gov",  # Baton Rouge 2 (shr-cam-*, laf-cam-*, lkc-cam-*, mnr-cam-*)
    "ITSStreamingNO.dotd.la.gov",   # New Orleans (nor-cam-*, hou-cam-*, ns-cam-*)
]

#: All known map layer IDs
LAYER_IDS = [
    "Cameras",
    "Incidents",
    "Construction",
    "Closures",
    "ClosuresPolyline",
    "SpecialEvents",
    "WeatherReports",
    "WeatherIncidents",
    "WeatherClosures",
    "WeatherEvents",
    "WeatherForecast",
    "MessageSigns",
    "Bridge",
    "FerryTerminals",
    "RestAreas",
    "Waze",
    "WazeIncidents",
    "WazeClosures",
]

#: Layer IDs that support List/GetData (structured records, server-side DataTable)
LIST_LAYER_IDS = [
    "Cameras",
    "Incidents",
    "Construction",
    "Closures",
    "SpecialEvents",
    "MessageSigns",
    "Bridge",
    "FerryTerminals",
    "RestAreas",
    "WazeIncidents",
    "WazeClosures",
]

#: Default page size for list requests
DEFAULT_PAGE_SIZE = 500

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TIMEOUT = 20  # seconds


# ---------------------------------------------------------------------------
# Dataclasses (response models)
# ---------------------------------------------------------------------------

@dataclass
class CameraImage:
    """A single view/lens belonging to a camera site.

    One camera *site* may have multiple images (different zoom levels or
    directions of view). Each image may have an optional HLS video stream.
    """
    id: int
    camera_site_id: int
    sort_order: int
    description: str
    image_url: str          # relative: /map/Cctv/{id}
    image_type: int
    video_url: Optional[str]     # absolute HLS m3u8 URL or None
    video_type: Optional[str]    # "application/x-mpegURL" or None
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool

    @property
    def snapshot_url(self) -> str:
        """Absolute URL for the JPEG snapshot image."""
        return BASE_URL + self.image_url

    @property
    def has_video(self) -> bool:
        """True when a live HLS stream is available and not disabled."""
        return bool(
            self.video_url
            and not self.video_disabled
            and not self.disabled
            and not self.blocked
        )


@dataclass
class Camera:
    """A traffic camera site — typically a physical gantry with one or more lenses."""

    id: int
    source_id: str          # agency-internal ID (e.g. "100")
    source: str             # data provider, e.g. "LADOTD"
    location: str           # human-readable location, e.g. "I-20 at I-220 Off Ramp"
    roadway: str            # e.g. "I-20"
    direction: str          # cardinal direction or "Unknown"
    latitude: float
    longitude: float
    images: List[CameraImage] = field(default_factory=list)
    region: Optional[str] = None
    state: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None
    dot_district: Optional[str] = None
    nickname: Optional[str] = None
    last_updated: Optional[str] = None

    @property
    def primary_image(self) -> Optional[CameraImage]:
        """Return the first (primary) image for this camera site, or None."""
        return self.images[0] if self.images else None

    @property
    def has_video(self) -> bool:
        """True if at least one image has an active video stream."""
        return any(img.has_video for img in self.images)


@dataclass
class TrafficEvent:
    """An active traffic event: incident, construction, closure, or special event."""

    id: int
    layer_name: str         # e.g. "Incidents", "Construction"
    event_sub_type: Optional[str]   # e.g. "stalledvehicle", "laneblockage"
    roadway_name: str
    description: str
    source: str             # "ERS", "LADOTD", etc.
    source_id: str
    severity: Optional[str]        # "Minor", "Moderate", "Major", "Unknown"
    direction: Optional[str]
    location_description: Optional[str]
    lane_description: Optional[str]
    detour_description: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    last_updated: Optional[str]
    is_full_closure: bool = False
    show_on_map: bool = True
    # Restrictions
    width_restriction: Optional[str] = None
    height_restriction: Optional[str] = None
    weight_restriction: Optional[str] = None


@dataclass
class MessageSign:
    """A Dynamic Message Sign (DMS / Variable Message Sign)."""

    row_id: str             # e.g. "DOTD--10017"
    name: str
    roadway_name: str
    direction: str
    area: str
    description: str
    message: str            # may contain HTML <br/> tags
    message2: str
    message3: str
    status: str             # "on", "off", "error", etc.
    last_updated: Optional[str] = None

    @property
    def full_message(self) -> str:
        """Concatenated plain-text message, newline-separated, HTML tags stripped."""
        parts = [self.message, self.message2, self.message3]
        combined = " | ".join(p for p in parts if p and p.strip())
        return re.sub(r"<[^>]+>", " ", combined).strip()


@dataclass
class MovableBridge:
    """Status of a movable (bascule/swing/lift) bridge."""

    id: int
    name: str           # filterAndOrderProperty1
    current_status: str # filterAndOrderProperty2 ("Open", "Closed", etc.)
    normal_status: str  # filterAndOrderProperty3
    district: str       # filterAndOrderProperty4
    parish: Optional[str]
    schedule: Optional[str]
    notes: Optional[str]
    bridge_type: Optional[str]
    phone: Optional[str]
    county: Optional[str]
    last_updated: Optional[str] = None


@dataclass
class FerryTerminal:
    """Status of a LADOTD ferry crossing."""

    id: int
    name: str           # filterAndOrderProperty1
    from_location: str
    to_location: str
    status: str         # e.g. "In service (normal operating hours)"
    additional_information: Optional[str]
    organization: str
    county: Optional[str]
    last_updated: Optional[str] = None


@dataclass
class RestArea:
    """A highway rest area / welcome center."""

    id: int
    name: str
    roadway: str
    direction: str
    location: Optional[str]
    truck_parking: Optional[str]
    all_parking: Optional[str]
    security: Optional[str]
    last_updated: Optional[str] = None


@dataclass
class MapMarker:
    """Lightweight representation of a map icon position (from /map/mapIcons endpoint)."""

    item_id: str
    latitude: float
    longitude: float
    layer_id: str = ""
    title: str = ""


@dataclass
class RouteLocation:
    """A road segment returned by the network geocoder."""

    link_id: str
    name: str
    name_direction: str
    is_forward: bool
    latitude: float
    longitude: float
    travel_time_display: str


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

class _Http:
    """Minimal HTTP helper — only stdlib urllib, supports gzip decompression."""

    @staticmethod
    def get(url: str, params: Optional[Dict[str, str]] = None) -> bytes:
        """Perform a GET request and return raw (decompressed) bytes.

        Args:
            url:    Absolute URL to fetch.
            params: Optional dict of query-string parameters (will be URL-encoded).

        Returns:
            Decompressed response body as bytes.

        Raises:
            urllib.error.HTTPError: on 4xx/5xx responses.
            urllib.error.URLError:  on network-level errors.
        """
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "gzip",
                "Accept": "application/json, text/html, */*",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            ce = resp.headers.get("Content-Encoding", "")

        if "gzip" in ce or (len(raw) >= 2 and raw[:2] == b"\x1f\x8b"):
            raw = gzip.decompress(raw)

        return raw

    @classmethod
    def get_json(cls, url: str, params: Optional[Dict[str, str]] = None) -> Any:
        """Fetch a URL and JSON-decode the response."""
        raw = cls.get(url, params)
        return json.loads(raw.decode("utf-8", errors="replace"))

    @classmethod
    def get_text(cls, url: str, params: Optional[Dict[str, str]] = None) -> str:
        """Fetch a URL and return decoded text."""
        raw = cls.get(url, params)
        return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class LaDOTDClient:
    """Client for the Louisiana 511 (511la.org) traffic information API.

    All methods are synchronous and use the Python standard library only.
    No API key or authentication is required.

    Example::

        client = LaDOTDClient()

        # List all traffic cameras
        cameras = client.get_cameras()
        print(f"Found {len(cameras)} cameras")

        # Show cameras that have live video
        video_cams = [c for c in cameras if c.has_video]
        for cam in video_cams[:5]:
            img = cam.primary_image
            print(cam.location, "→", img.video_url)

        # Get active incidents
        incidents = client.get_incidents()
        for inc in incidents:
            print(inc.roadway_name, inc.severity, inc.description[:80])

        # Download a camera snapshot
        img_bytes = client.get_camera_snapshot(1)
        with open("cam1.jpg", "wb") as f:
            f.write(img_bytes)
    """

    def __init__(self, base_url: str = BASE_URL, timeout: int = TIMEOUT) -> None:
        """Initialise the client.

        Args:
            base_url: Override the base URL (default: https://www.511la.org).
            timeout:  HTTP request timeout in seconds (default: 20).
        """
        self._base = base_url.rstrip("/")
        self._http = _Http
        # Monkey-patch global timeout (simple approach for stdlib urlopen)
        global TIMEOUT
        TIMEOUT = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return self._base + path

    def _build_dt_query(
        self,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
        search_value: str = "",
        order_col: int = 0,
        order_dir: str = "asc",
    ) -> str:
        """Build a DataTables server-side query JSON string.

        The /List/GetData/{layer} endpoint expects a ``query`` parameter
        containing a JSON-serialised DataTables request object.
        """
        payload: Dict[str, Any] = {
            "draw": 1,
            "columns": [],
            "order": [{"column": order_col, "dir": order_dir}],
            "start": start,
            "length": min(length, 1000),  # server caps at 1000
            "search": {"value": search_value, "regex": False},
        }
        return json.dumps(payload, separators=(",", ":"))

    def _get_list_data(
        self,
        layer_id: str,
        start: int = 0,
        length: int = DEFAULT_PAGE_SIZE,
        search_value: str = "",
    ) -> Dict[str, Any]:
        """Fetch paginated structured data from /List/GetData/{layerId}.

        Args:
            layer_id:     One of LIST_LAYER_IDS.
            start:        Pagination offset (0-based).
            length:       Number of records to return (max 1000).
            search_value: Free-text search filter applied server-side.

        Returns:
            Parsed JSON response dict with keys:
            ``draw``, ``recordsTotal``, ``recordsFiltered``, ``data``.
        """
        query = self._build_dt_query(start=start, length=length, search_value=search_value)
        url = self._url(f"/List/GetData/{layer_id}")
        return self._http.get_json(url, params={"query": query, "lang": "en"})

    def _get_list_data_all(
        self, layer_id: str, search_value: str = ""
    ) -> List[Dict[str, Any]]:
        """Fetch **all** records from a list endpoint, handling pagination.

        Issues multiple requests if ``recordsTotal > length`` up to a safety
        cap of 10 pages (10 000 records) to avoid runaway loops.
        """
        all_records: List[Dict[str, Any]] = []
        page_size = DEFAULT_PAGE_SIZE
        start = 0
        max_pages = 10

        for _ in range(max_pages):
            resp = self._get_list_data(layer_id, start=start, length=page_size,
                                       search_value=search_value)
            batch = resp.get("data", [])
            all_records.extend(batch)
            total = resp.get("recordsTotal", 0)

            if len(all_records) >= total or len(batch) < page_size:
                break
            start += page_size

        return all_records

    @staticmethod
    def _parse_lat_lon(lat_lng: Any) -> Tuple[float, float]:
        """Extract (lat, lon) from the WKT geography field.

        The API encodes coordinates as a WKT ``POINT (lon lat)`` string inside
        a nested ``geography`` / ``wellKnownText`` object.

        Falls back to (0.0, 0.0) if the field is missing or malformed.
        """
        if not lat_lng:
            return 0.0, 0.0
        geography = lat_lng.get("geography", {})
        wkt = geography.get("wellKnownText", "")
        m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", wkt)
        if m:
            lon, lat = float(m.group(1)), float(m.group(2))
            return lat, lon
        return 0.0, 0.0

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        roadway: str = "",
        region: str = "",
        search: str = "",
    ) -> List[Camera]:
        """Return all traffic cameras (up to 336 statewide).

        Args:
            roadway: Optional roadway filter (e.g. "I-10").  Matched server-side.
            region:  Optional region filter (e.g. "Southeast").
            search:  Free-text search across all fields.

        Returns:
            List of :class:`Camera` objects.

        Example::

            client = LaDOTDClient()
            cams = client.get_cameras(roadway="I-10")
            for c in cams:
                print(c.id, c.location)
        """
        search_value = search or roadway or region
        records = self._get_list_data_all("Cameras", search_value=search_value)
        cameras: List[Camera] = []
        for r in records:
            lat, lon = self._parse_lat_lon(r.get("latLng"))
            images = [
                CameraImage(
                    id=img.get("id", 0),
                    camera_site_id=img.get("cameraSiteId", 0),
                    sort_order=img.get("sortOrder", 0),
                    description=img.get("description", ""),
                    image_url=img.get("imageUrl", ""),
                    image_type=img.get("imageType", 0),
                    video_url=img.get("videoUrl"),
                    video_type=img.get("videoType"),
                    is_video_auth_required=bool(img.get("isVideoAuthRequired", False)),
                    video_disabled=bool(img.get("videoDisabled", False)),
                    disabled=bool(img.get("disabled", False)),
                    blocked=bool(img.get("blocked", False)),
                )
                for img in r.get("images", [])
            ]
            cameras.append(Camera(
                id=r.get("id", int(r.get("DT_RowId", 0))),
                source_id=r.get("sourceId", ""),
                source=r.get("source", ""),
                location=r.get("location", ""),
                roadway=r.get("roadway", ""),
                direction=r.get("direction", ""),
                latitude=lat,
                longitude=lon,
                images=images,
                region=r.get("region"),
                state=r.get("state"),
                county=r.get("county"),
                city=r.get("city"),
                dot_district=r.get("dotDistrict"),
                nickname=r.get("nickname"),
                last_updated=r.get("lastUpdated"),
            ))
        return cameras

    def get_camera_snapshot(self, image_id: int) -> bytes:
        """Download the current JPEG snapshot for a camera image.

        Snapshots are refreshed every 10 seconds by LADOTD and served from
        CloudFront (max-age=10).

        Args:
            image_id: The numeric image ID (``CameraImage.id``).

        Returns:
            Raw JPEG bytes.

        Raises:
            urllib.error.HTTPError: if the camera is offline (returns empty body).

        Example::

            client = LaDOTDClient()
            cameras = client.get_cameras()
            img_id = cameras[0].primary_image.id
            jpeg = client.get_camera_snapshot(img_id)
            with open(f"camera_{img_id}.jpg", "wb") as f:
                f.write(jpeg)
        """
        url = f"{CAMERA_IMAGE_URL}/{image_id}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()

    def get_camera_video_url(self, image_id: int) -> str:
        """Retrieve the HLS playlist URL for a camera image.

        This wraps the ``/Camera/GetVideoUrl?imageId={id}`` endpoint which
        returns a JSON-encoded string (the m3u8 URL).

        Args:
            image_id: The numeric image ID (``CameraImage.id``).

        Returns:
            Absolute HLS playlist URL, e.g.
            ``https://ITSStreamingBR2.dotd.la.gov/public/shr-cam-030.streams/playlist.m3u8``

        Example::

            url = client.get_camera_video_url(1)
            print("HLS stream:", url)
        """
        url = self._url(f"/Camera/GetVideoUrl?imageId={image_id}")
        raw = self._http.get_json(url)
        return str(raw)

    def get_camera_filter_values(self) -> Dict[str, List[str]]:
        """Return available filter values for the camera list.

        Useful for populating search drop-downs.

        Returns:
            Dict with keys such as ``state``, ``region``, ``roadway``, ``county``.
        """
        url = self._url("/List/UniqueColumnValuesForCctv/Cameras")
        return self._http.get_json(url)

    # ------------------------------------------------------------------
    # Traffic events (incidents, construction, closures, special events)
    # ------------------------------------------------------------------

    def _get_events(
        self, layer_id: str, search: str = ""
    ) -> List[TrafficEvent]:
        """Generic helper to retrieve traffic event records.

        Args:
            layer_id: One of "Incidents", "Construction", "Closures", "SpecialEvents",
                      "WazeIncidents", "WazeClosures".
            search:   Optional free-text search.

        Returns:
            List of :class:`TrafficEvent` objects.
        """
        records = self._get_list_data_all(layer_id, search_value=search)
        events: List[TrafficEvent] = []
        for r in records:
            events.append(TrafficEvent(
                id=r.get("id", int(r.get("DT_RowId", "0") or "0")),
                layer_name=r.get("layerName", layer_id),
                event_sub_type=r.get("eventSubType"),
                roadway_name=r.get("roadwayName", ""),
                description=r.get("description", ""),
                source=r.get("source", ""),
                source_id=r.get("sourceId", ""),
                severity=r.get("severity"),
                direction=r.get("direction"),
                location_description=r.get("locationDescription"),
                lane_description=r.get("laneDescription"),
                detour_description=r.get("detourDescription"),
                start_date=r.get("startDate"),
                end_date=r.get("endDate"),
                last_updated=r.get("lastUpdated"),
                is_full_closure=bool(r.get("isFullClosure", False)),
                show_on_map=bool(r.get("showOnMap", True)),
                width_restriction=r.get("widthRestriction"),
                height_restriction=r.get("heightRestriction"),
                weight_restriction=r.get("weightRestriction"),
            ))
        return events

    def get_incidents(self, search: str = "") -> List[TrafficEvent]:
        """Return active traffic incidents (crashes, stalled vehicles, etc.).

        Args:
            search: Optional free-text filter.

        Returns:
            List of :class:`TrafficEvent` objects with ``layer_name == "Incidents"``.
        """
        return self._get_events("Incidents", search=search)

    def get_construction(self, search: str = "") -> List[TrafficEvent]:
        """Return active construction events.

        Args:
            search: Optional free-text filter.

        Returns:
            List of :class:`TrafficEvent` objects.
        """
        return self._get_events("Construction", search=search)

    def get_closures(self, search: str = "") -> List[TrafficEvent]:
        """Return active road closures.

        Args:
            search: Optional free-text filter.

        Returns:
            List of :class:`TrafficEvent` objects.
        """
        return self._get_events("Closures", search=search)

    def get_special_events(self, search: str = "") -> List[TrafficEvent]:
        """Return active special events (concerts, sporting events, etc.).

        Args:
            search: Optional free-text filter.

        Returns:
            List of :class:`TrafficEvent` objects.
        """
        return self._get_events("SpecialEvents", search=search)

    def get_waze_incidents(self, search: str = "") -> List[TrafficEvent]:
        """Return Waze crowd-reported incidents.

        Args:
            search: Optional free-text filter.

        Returns:
            List of :class:`TrafficEvent` objects with source "Waze".
        """
        return self._get_events("WazeIncidents", search=search)

    def get_waze_closures(self, search: str = "") -> List[TrafficEvent]:
        """Return Waze crowd-reported closures.

        Args:
            search: Optional free-text filter.

        Returns:
            List of :class:`TrafficEvent` objects.
        """
        return self._get_events("WazeClosures", search=search)

    # ------------------------------------------------------------------
    # Variable Message Signs
    # ------------------------------------------------------------------

    def get_message_signs(self, roadway: str = "") -> List[MessageSign]:
        """Return current Dynamic Message Sign (DMS) messages (59 statewide).

        Args:
            roadway: Optional roadway filter, e.g. "I-10".

        Returns:
            List of :class:`MessageSign` objects.

        Example::

            signs = client.get_message_signs(roadway="I-10")
            for s in signs:
                print(s.name, "→", s.full_message)
        """
        records = self._get_list_data_all("MessageSigns", search_value=roadway)
        signs: List[MessageSign] = []
        for r in records:
            signs.append(MessageSign(
                row_id=r.get("DT_RowId", ""),
                name=r.get("name", ""),
                roadway_name=r.get("roadwayName", ""),
                direction=r.get("direction", ""),
                area=r.get("area", ""),
                description=r.get("description", ""),
                message=r.get("message", ""),
                message2=r.get("message2", "") or "",
                message3=r.get("message3", "") or "",
                status=r.get("status", ""),
                last_updated=r.get("lastUpdated"),
            ))
        return signs

    # ------------------------------------------------------------------
    # Movable bridges
    # ------------------------------------------------------------------

    def get_bridges(self) -> List[MovableBridge]:
        """Return current open/closed status of all movable bridges (100 statewide).

        Returns:
            List of :class:`MovableBridge` objects.

        Note:
            The API uses generic ``filterAndOrderProperty{1-10}`` fields; the
            mapping applied here matches the LADOTD field order observed in
            live data as of 2026-03.
        """
        records = self._get_list_data_all("Bridge")
        bridges: List[MovableBridge] = []
        for r in records:
            bridges.append(MovableBridge(
                id=int(r.get("DT_RowId", 0)),
                name=r.get("filterAndOrderProperty1", ""),
                current_status=r.get("filterAndOrderProperty2", ""),
                normal_status=r.get("filterAndOrderProperty3", ""),
                district=r.get("filterAndOrderProperty4", ""),
                parish=r.get("parish"),
                schedule=r.get("schedule"),
                notes=r.get("notes"),
                bridge_type=r.get("bridgeType"),
                phone=r.get("phone"),
                county=r.get("county"),
                last_updated=r.get("lastUpdated"),
            ))
        return bridges

    # ------------------------------------------------------------------
    # Ferry terminals
    # ------------------------------------------------------------------

    def get_ferries(self) -> List[FerryTerminal]:
        """Return current status of ferry terminals (5 active crossings).

        Returns:
            List of :class:`FerryTerminal` objects.
        """
        records = self._get_list_data_all("FerryTerminals")
        ferries: List[FerryTerminal] = []
        for r in records:
            ferries.append(FerryTerminal(
                id=int(r.get("DT_RowId", 0)),
                name=r.get("filterAndOrderProperty1", ""),
                from_location=r.get("from", ""),
                to_location=r.get("to", ""),
                status=r.get("status", ""),
                additional_information=r.get("additionalInformation"),
                organization=r.get("organization", ""),
                county=r.get("county"),
                last_updated=r.get("lastUpdated"),
            ))
        return ferries

    # ------------------------------------------------------------------
    # Rest areas
    # ------------------------------------------------------------------

    def get_rest_areas(self) -> List[RestArea]:
        """Return information for highway rest areas and welcome centers.

        Returns:
            List of :class:`RestArea` objects.
        """
        records = self._get_list_data_all("RestAreas")
        areas: List[RestArea] = []
        for r in records:
            areas.append(RestArea(
                id=int(r.get("DT_RowId", 0)),
                name=r.get("name", r.get("filterAndOrderProperty1", "")),
                roadway=r.get("roadway", r.get("filterAndOrderProperty1", "")),
                direction=r.get("direction", r.get("filterAndOrderProperty2", "")),
                location=r.get("location"),
                truck_parking=r.get("truckParking", r.get("filterAndOrderProperty4")),
                all_parking=r.get("allParking", r.get("filterAndOrderProperty5")),
                security=r.get("security", r.get("filterAndOrderProperty3")),
                last_updated=r.get("lastUpdated"),
            ))
        return areas

    # ------------------------------------------------------------------
    # Map marker positions (lightweight — no full records)
    # ------------------------------------------------------------------

    def get_map_markers(self, layer_id: str) -> List[MapMarker]:
        """Return map marker positions for a given layer.

        This endpoint is fast but returns only IDs and coordinates — use
        the ``/List/GetData/`` or ``/tooltip/`` endpoints for full details.

        Args:
            layer_id: Any value from :data:`LAYER_IDS`.

        Returns:
            List of :class:`MapMarker` objects.

        Example::

            markers = client.get_map_markers("Incidents")
            for m in markers:
                print(f"  #{m.item_id} at ({m.latitude:.4f}, {m.longitude:.4f})")
        """
        url = self._url(f"/map/mapIcons/{layer_id}")
        data = self._http.get_json(url)
        markers: List[MapMarker] = []
        for item in data.get("item2", []):
            loc = item.get("location", [0.0, 0.0])
            markers.append(MapMarker(
                item_id=str(item.get("itemId", "")),
                latitude=float(loc[0]) if len(loc) > 0 else 0.0,
                longitude=float(loc[1]) if len(loc) > 1 else 0.0,
                layer_id=layer_id,
                title=item.get("title", ""),
            ))
        return markers

    # ------------------------------------------------------------------
    # Tooltip / detail HTML
    # ------------------------------------------------------------------

    def get_tooltip(self, layer_id: str, item_id: str) -> str:
        """Return the HTML tooltip/detail fragment for a map item.

        This is the same content rendered in the pop-up when a user clicks
        a marker on the 511la.org interactive map.

        Args:
            layer_id: e.g. "Cameras", "Incidents", "MessageSigns".
            item_id:  The numeric or string ID of the item (from :class:`MapMarker`
                      or the DT_RowId field in list data).

        Returns:
            HTML string fragment.
        """
        url = self._url(f"/tooltip/{layer_id}/{item_id}")
        return self._http.get_text(url, params={"lang": "en"})

    # ------------------------------------------------------------------
    # Route / geocoding helpers
    # ------------------------------------------------------------------

    def geocode_road(
        self,
        latitude: float,
        longitude: float,
        zoom: int = 16,
    ) -> List[RouteLocation]:
        """Return road segment names at a given coordinate.

        Uses the 511 route-planning network to identify road segments near
        a lat/lon point — useful for geocoding "what road is this?" queries.

        Args:
            latitude:  WGS-84 decimal latitude.
            longitude: WGS-84 decimal longitude.
            zoom:      Map zoom level hint (default 16); higher = more detail.

        Returns:
            List of :class:`RouteLocation` objects ordered by distance.

        Example::

            roads = client.geocode_road(29.9511, -90.0715)   # French Quarter, NOLA
            for r in roads:
                print(r.name_direction, r.travel_time_display)
        """
        url = self._url(
            f"/api/route/getlocations"
            f"?latitude={latitude}&longitude={longitude}&zoom={zoom}"
        )
        data = self._http.get_json(url)
        locations: List[RouteLocation] = []
        for item in data:
            pt = item.get("point", {})
            locations.append(RouteLocation(
                link_id=item.get("linkId", ""),
                name=item.get("name", ""),
                name_direction=item.get("nameDirection", ""),
                is_forward=bool(item.get("isForward", True)),
                latitude=float(pt.get("latitude", 0.0)),
                longitude=float(pt.get("longitude", 0.0)),
                travel_time_display=item.get("travelTimeDisplay", ""),
            ))
        return locations

    # ------------------------------------------------------------------
    # Weather layer
    # ------------------------------------------------------------------

    def get_weather_forecast_locations(self) -> List[MapMarker]:
        """Return NWS zone forecast location markers.

        Returns location markers for the ~7 NWS forecast zones covering
        Louisiana. Use :meth:`get_tooltip` with ``layer_id="WeatherForecast"``
        and the returned ``item_id`` (an NWS zone code like "LAZ001") to get
        the full multi-day forecast HTML.

        Returns:
            List of :class:`MapMarker` objects.
        """
        return self.get_map_markers("WeatherForecast")

    def get_weather_events(self) -> List[MapMarker]:
        """Return weather event (polygon) markers on the map.

        Returns:
            List of :class:`MapMarker` objects.
        """
        return self.get_map_markers("WeatherEvents")

    def get_traffic_speed_tile_url(self) -> str:
        """Return the XYZ tile URL template for traffic speed overlay.

        The returned URL uses ``{x}``, ``{y}``, ``{z}`` placeholders
        compatible with Leaflet, MapboxGL, Google Maps, etc.

        Returns:
            Tile URL template string.
        """
        return "https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}"

    # ------------------------------------------------------------------
    # KMZ geographic layers
    # ------------------------------------------------------------------

    def get_parish_kmz_url(self) -> str:
        """Return the URL for the Louisiana parish boundary KMZ file."""
        return f"{self._base}/Content/LU/KML/Parish.kmz"

    def get_district_kmz_url(self) -> str:
        """Return the URL for the LADOTD engineering district KMZ file."""
        return f"{self._base}/Content/LU/KML/District.kmz"

    # ------------------------------------------------------------------
    # Convenience: all active events
    # ------------------------------------------------------------------

    def get_all_events(self) -> List[TrafficEvent]:
        """Return all active traffic events (incidents + construction + closures).

        Returns:
            Combined and sorted list of :class:`TrafficEvent` objects.
        """
        results: List[TrafficEvent] = []
        for layer in ("Incidents", "Construction", "Closures", "SpecialEvents"):
            try:
                results.extend(self._get_events(layer))
            except urllib.error.HTTPError:
                pass  # layer may be empty or temporarily unavailable
        return results

    def get_streaming_servers(self) -> List[str]:
        """Return the list of known LADOTD ITS streaming server hostnames.

        These WOWZA-based servers serve HLS (m3u8) streams for cameras
        region-wide.  All streams follow the pattern::

            https://{hostname}/public/{region-cam-NNN}.streams/playlist.m3u8

        Returns:
            List of hostname strings.
        """
        return list(STREAMING_HOSTS)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _print_cameras(client: LaDOTDClient, args: List[str]) -> None:
    print("Fetching cameras...")
    cams = client.get_cameras()
    with_video = [c for c in cams if c.has_video]
    print(f"  Total cameras : {len(cams)}")
    print(f"  With HLS video: {len(with_video)}")
    print()
    print("Sample cameras (first 10):")
    for c in cams[:10]:
        vid = ""
        if c.primary_image and c.primary_image.video_url:
            vid = f" [HLS: {c.primary_image.video_url}]"
        print(f"  [{c.id:>3}] {c.roadway:<10}  {c.location:<50}{vid}")


def _print_events(client: LaDOTDClient, layer: str) -> None:
    method_map = {
        "incidents": client.get_incidents,
        "construction": client.get_construction,
        "closures": client.get_closures,
        "waze": client.get_waze_incidents,
    }
    fn = method_map.get(layer, client.get_incidents)
    print(f"Fetching {layer}...")
    events = fn()
    print(f"  Total: {len(events)}")
    for e in events[:15]:
        sev = f"[{e.severity}] " if e.severity else ""
        print(f"  #{e.id:>7} {sev}{e.roadway_name:<10} {e.description[:70]}")


def _print_signs(client: LaDOTDClient) -> None:
    print("Fetching variable message signs...")
    signs = client.get_message_signs()
    print(f"  Total: {len(signs)}")
    for s in signs[:15]:
        print(f"  {s.name:<40} [{s.status}]  {s.full_message[:60]}")


def _print_bridges(client: LaDOTDClient) -> None:
    print("Fetching movable bridge status...")
    bridges = client.get_bridges()
    print(f"  Total: {len(bridges)}")
    for b in bridges[:15]:
        print(f"  {b.name:<30} {b.current_status:<10} {b.parish or '':>20}  {b.schedule or ''}")


def _print_ferries(client: LaDOTDClient) -> None:
    print("Fetching ferry terminal status...")
    ferries = client.get_ferries()
    print(f"  Total: {len(ferries)}")
    for f in ferries:
        print(f"  {f.name:<40} {f.status}")
        if f.additional_information:
            print(f"    → {f.additional_information}")


def _print_rest_areas(client: LaDOTDClient) -> None:
    print("Fetching rest areas...")
    areas = client.get_rest_areas()
    print(f"  Total: {len(areas)}")
    for a in areas:
        print(f"  [{a.id}] {a.name} — {a.direction}")


def _print_weather(client: LaDOTDClient, mode: str) -> None:
    if mode == "forecast":
        markers = client.get_weather_forecast_locations()
        print(f"NWS forecast zones ({len(markers)} zones):")
        for m in markers:
            print(f"  Zone {m.item_id:>8}  ({m.latitude:.4f}, {m.longitude:.4f})")
    else:
        markers = client.get_map_markers("WeatherEvents")
        print(f"Weather events on map ({len(markers)} items):")
        for m in markers[:10]:
            print(f"  #{m.item_id} at ({m.latitude:.4f}, {m.longitude:.4f})")


def _save_snapshot(client: LaDOTDClient, image_id: int) -> None:
    print(f"Downloading snapshot for image ID {image_id}...")
    data = client.get_camera_snapshot(image_id)
    out = f"camera_{image_id}.jpg"
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"  Saved {len(data)} bytes → {out}")


def _geocode(client: LaDOTDClient, lat: float, lon: float) -> None:
    print(f"Road segments at ({lat}, {lon}):")
    locs = client.geocode_road(lat, lon)
    for loc in locs:
        print(f"  {loc.name_direction:<40} [{loc.link_id}]")


def main() -> None:
    """Command-line entry point for the 511LA client demo."""
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()
    client = LaDOTDClient()

    try:
        if cmd == "cameras":
            _print_cameras(client, args[1:])
        elif cmd in ("incidents", "construction", "closures", "waze"):
            _print_events(client, cmd)
        elif cmd == "signs":
            _print_signs(client)
        elif cmd == "bridges":
            _print_bridges(client)
        elif cmd == "ferries":
            _print_ferries(client)
        elif cmd == "restareas":
            _print_rest_areas(client)
        elif cmd == "weather":
            _print_weather(client, "events")
        elif cmd == "forecast":
            _print_weather(client, "forecast")
        elif cmd == "snapshot":
            if len(args) < 2:
                print("Usage: snapshot <image_id>")
                sys.exit(1)
            _save_snapshot(client, int(args[1]))
        elif cmd == "geocode":
            if len(args) < 3:
                print("Usage: geocode <lat> <lon>")
                sys.exit(1)
            _geocode(client, float(args[1]), float(args[2]))
        else:
            print(f"Unknown command: {cmd}")
            print("Run with no arguments to see usage.")
            sys.exit(1)
    except urllib.error.HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
