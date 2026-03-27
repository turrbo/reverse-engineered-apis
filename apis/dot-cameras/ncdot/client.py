#!/usr/bin/env python3
"""
NCDOT (North Carolina Department of Transportation) Traffic API Client
=======================================================================

Reverse-engineered client for the DriveNC / NCDOT traffic information system.
Provides access to live traffic cameras, incidents, road conditions, county
conditions, rest areas, ferry routes, and more.

Base API:  https://eapps.ncdot.gov/services/traffic-prod/v1
Source:    https://drivenc.gov  (DriveNC interactive map)
Discovered: 2026-03-27

No authentication required — all endpoints are public REST/JSON APIs.

Usage (CLI):
    python ncdot_client.py cameras
    python ncdot_client.py cameras --county 32
    python ncdot_client.py incidents
    python ncdot_client.py incidents --filter ROUTE --value I-40
    python ncdot_client.py incident 766338
    python ncdot_client.py counties
    python ncdot_client.py county 32
    python ncdot_client.py regions
    python ncdot_client.py roads
    python ncdot_client.py rest-areas
    python ncdot_client.py incident-groups
    python ncdot_client.py ferry-routes
    python ncdot_client.py incident-summary
    python ncdot_client.py camera-image 5 --save /tmp/cam5.jpg

Usage (Python):
    from ncdot_client import NCDOTClient

    client = NCDOTClient()
    cameras = client.list_cameras()
    detail  = client.get_camera(5)
    img     = client.get_camera_image(5)  # bytes
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://eapps.ncdot.gov/services/traffic-prod/v1"
ARCGIS_FERRY_URL = (
    "https://services.arcgis.com/NuWFvHYDMVmmxMeM/arcgis/rest/services"
    "/NCDOT_FerryRoutes/FeatureServer/0/query"
    "?f=json&cacheHint=true&resultOffset=0&resultRecordCount=9999"
    "&where=1%3D1&outFields=*&returnGeometry=true&outSR=4326"
)

DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)

# Valid values discovered from API error messages and JS source
INCIDENT_FILTER_TYPES_SEARCH = (
    "COUNTY",
    "REGION",
    "ROUTE",
    "ROADCLOSURE",
    "EVENTS",
    "CONDITION",
    "INCIDENTTYPE",
)

INCIDENT_FILTER_TYPES_COUNT = (
    "COUNTY",
    "PROJECT",
    "REGION",
    "ROUTE",
)

ROAD_CLOSURE_CONDITIONS = [
    "Road Closed",
    "Road Closed with Detour",
    "Road Impassable",
    "Permanent Road Closure",
    "Local Traffic Only",
    "Ramp Closed",
    "Ferry Closed",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CameraLocation:
    """Minimal camera record returned by the /cameras/ list endpoint."""

    id: int
    latitude: float
    longitude: float


@dataclass
class Camera:
    """
    Full camera record returned by /cameras/{id}.

    Attributes:
        id:            Camera identifier (integer, stable).
        location_name: Human-readable location string, e.g. "I-40 Exit 270 - US 15-501".
        display_name:  Optional alternate display name (often empty string).
        mile_marker:   Decimal mile-post on the associated road.
        road_id:       Foreign key into the /traffic/roads list.
        county_id:     Foreign key into the /counties/conditions list.
        latitude:      WGS-84 latitude.
        longitude:     WGS-84 longitude.
        image_url:     Absolute URL to the live JPEG snapshot.
        is_dot_camera: True if this is an official NCDOT-operated camera.
        status:        Operational status string, typically "OK" or "OFFLINE".
    """

    id: int
    location_name: str
    display_name: str
    mile_marker: float
    road_id: int
    county_id: int
    latitude: float
    longitude: float
    image_url: str
    is_dot_camera: bool
    status: str

    @property
    def image_filename(self) -> str:
        """Extract the filename component from image_url."""
        idx = self.image_url.find("filename=")
        if idx == -1:
            return ""
        return self.image_url[idx + len("filename="):]

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        return cls(
            id=d["id"],
            location_name=d.get("locationName", ""),
            display_name=d.get("displayName", ""),
            mile_marker=float(d.get("mileMarker", 0)),
            road_id=d.get("roadId", 0),
            county_id=d.get("countyId", 0),
            latitude=float(d.get("latitude", 0)),
            longitude=float(d.get("longitude", 0)),
            image_url=d.get("imageURL", ""),
            is_dot_camera=bool(d.get("isDOTCamera", False)),
            status=d.get("status", ""),
        )


@dataclass
class Coordinates:
    """Geographic coordinate pair (WGS-84)."""

    latitude: float
    longitude: float


@dataclass
class Road:
    """
    Road record from /traffic/roads.

    Attributes:
        id:       Internal road ID used in incident filter queries.
        name:     Road name, e.g. "I-40" or "NC-12".
        counties: Comma-separated list of county names the road passes through.
    """

    id: int
    name: str
    counties: str

    @property
    def county_list(self) -> List[str]:
        """Split the counties field into a Python list."""
        return [c.strip() for c in self.counties.split(",") if c.strip()]

    @classmethod
    def from_dict(cls, d: dict) -> "Road":
        return cls(id=d["id"], name=d["name"], counties=d.get("counties", ""))


@dataclass
class County:
    """
    A single item in the /counties/conditions list.

    Attributes:
        id:              County identifier (1-100, matches NC county numbering).
        name:            County name, e.g. "Wake".
        regions:         Comma-separated region IDs this county belongs to.
        road_conditions: Dict with keys "interstate", "primary", "secondary".
        status:          Overall report status, e.g. "Clear" or "No Report".
        last_updated:    ISO-8601 timestamp of the last condition update.
    """

    id: int
    name: str
    regions: str
    road_conditions: Dict[str, str]
    status: str
    last_updated: str

    @classmethod
    def from_dict(cls, d: dict) -> "County":
        return cls(
            id=d["id"],
            name=d["name"],
            regions=d.get("regions", ""),
            road_conditions=d.get("roadConditions", {}),
            status=d.get("status", ""),
            last_updated=d.get("lastUpdated", ""),
        )


@dataclass
class Region:
    """
    A geographic region grouping multiple counties.

    Regions available:
        1 = Triangle          2 = Triad
        3 = Rural Piedmont    4 = Metrolina
        5 = Eastern Mountains 6 = Western Mountains
        7 = Asheville Vicinity
        8 = Northern Coastal  9 = Southern Coastal
    """

    id: int
    name: str
    counties: List[Dict[str, object]]  # list of {"id": int, "name": str}

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        return cls(id=d["id"], name=d["name"], counties=d.get("counties", []))


@dataclass
class IncidentSummary:
    """
    Lightweight incident record returned by /traffic/incidents (map pins).

    Attributes:
        id:           Unique incident identifier.
        event_id:     Event grouping ID (usually 1 for standalone incidents).
        latitude:     WGS-84 latitude.
        longitude:    WGS-84 longitude.
        type:         Incident type string, e.g. "Vehicle Crash", "Construction".
        start:        ISO-8601 UTC start time.
        severity:     1 (low) to 3 (high).
        last_update:  ISO-8601 UTC last-updated time.
        road:         Road prefix: "I ", "NC", "US", "SR", etc.
        polyline:     JSON-encoded GeoJSON LineString or empty string.
    """

    id: int
    event_id: int
    latitude: float
    longitude: float
    type: str
    start: str
    severity: int
    last_update: str
    road: str
    polyline: str

    @classmethod
    def from_dict(cls, d: dict) -> "IncidentSummary":
        return cls(
            id=d["id"],
            event_id=d.get("eventId", 0),
            latitude=float(d.get("lat", 0)),
            longitude=float(d.get("long", 0)),
            type=d.get("type", ""),
            start=d.get("start", ""),
            severity=int(d.get("sev", 0)),
            last_update=d.get("lastUpdate", ""),
            road=d.get("road", ""),
            polyline=d.get("polyline", ""),
        )


@dataclass
class IncidentDetail:
    """
    Full incident record returned by /incidents/{id}.

    Attributes:
        id:                 Unique incident identifier.
        start:              ISO-8601 UTC start time.
        end:                ISO-8601 UTC expected end time.
        road_name:          Road name, e.g. "I-77".
        road_common_name:   Common road name (often empty).
        road_suffix:        Road suffix (often empty).
        city:               Nearest city name.
        direction:          Travel direction of impact ("N", "S", "E", "W", etc.).
        location:           Human-readable location description.
        county_id:          County identifier.
        county_name:        County name.
        latitude:           WGS-84 latitude.
        longitude:          WGS-84 longitude.
        reason:             Free-text reason/description of the incident.
        condition:          Impact condition, e.g. "Lane Closed", "Road Closed".
        severity:           1 (low) to 3 (high).
        is_detour:          Whether a detour is active.
        detour:             Detour description (often empty).
        lanes_closed:       Number of lanes currently closed.
        lanes_total:        Total number of lanes on the affected segment.
        incident_type:      Incident type string.
        work_zone_speed:    Work zone speed limit (0 if none).
        concurrent:         List of concurrent incident IDs (usually empty list).
    """

    id: int
    start: str
    end: str
    road_name: str
    road_common_name: str
    road_suffix: str
    city: str
    direction: str
    location: str
    county_id: int
    county_name: str
    latitude: float
    longitude: float
    reason: str
    condition: str
    severity: int
    is_detour: bool
    detour: str
    lanes_closed: int
    lanes_total: int
    incident_type: str
    work_zone_speed: int
    concurrent: List[int]

    @classmethod
    def from_dict(cls, d: dict) -> "IncidentDetail":
        road = d.get("road", {})
        county = d.get("county", {})
        coords = d.get("coords", {})
        cross_road = d.get("crossRoad", {})
        return cls(
            id=d["id"],
            start=d.get("start", ""),
            end=d.get("end", ""),
            road_name=road.get("name", ""),
            road_common_name=road.get("commonName", ""),
            road_suffix=road.get("suffix", ""),
            city=d.get("city", ""),
            direction=d.get("direction", ""),
            location=d.get("location", ""),
            county_id=county.get("id", 0),
            county_name=county.get("name", ""),
            latitude=float(coords.get("latitude", 0)),
            longitude=float(coords.get("longitude", 0)),
            reason=d.get("reason", ""),
            condition=d.get("condition", ""),
            severity=int(d.get("severity", 0)),
            is_detour=bool(d.get("isDetour", False)),
            detour=d.get("detour", ""),
            lanes_closed=int(d.get("lanesClosed", 0)),
            lanes_total=int(d.get("lanesTotal", 0)),
            incident_type=d.get("incidentType", ""),
            work_zone_speed=int(d.get("workZoneSpeedLimit", 0)),
            concurrent=d.get("concurrentIncidents", []),
        )


@dataclass
class IncidentSearchResult:
    """
    Paginated incident record returned by /incidents/filters.

    Attributes:
        id:                   Incident identifier.
        common_name:          Common name of the road or location.
        condition:            Impact condition string.
        incident_type:        Incident type string.
        severity:             1-3 severity rating.
        location:             Human-readable location description.
        county_name:          County name.
        start:                ISO-8601 UTC start time.
        end:                  ISO-8601 UTC end time.
        road:                 Road designation, e.g. "I-40" or "SR-2153".
        suffix:               Road suffix (often empty).
        latitude:             WGS-84 latitude.
        longitude:            WGS-84 longitude.
        event_id:             Event grouping identifier.
        event_name:           Event name (often "None").
        public_name:          Public-facing name (often empty).
        construction_dt:      Construction schedule text.
    """

    id: int
    common_name: str
    condition: str
    incident_type: str
    severity: int
    location: str
    county_name: str
    start: str
    end: str
    road: str
    suffix: str
    latitude: float
    longitude: float
    event_id: int
    event_name: str
    public_name: str
    construction_dt: str

    @classmethod
    def from_dict(cls, d: dict) -> "IncidentSearchResult":
        coords = d.get("coords", {})
        return cls(
            id=d["id"],
            common_name=d.get("commonName", ""),
            condition=d.get("condition", ""),
            incident_type=d.get("incidentType", ""),
            severity=int(d.get("severity", 0)),
            location=d.get("location", ""),
            county_name=d.get("countyName", ""),
            start=d.get("start", ""),
            end=d.get("end", ""),
            road=d.get("road", ""),
            suffix=d.get("suffix", ""),
            latitude=float(coords.get("latitude", 0)),
            longitude=float(coords.get("longitude", 0)),
            event_id=int(d.get("eventId", 0)),
            event_name=d.get("eventName", ""),
            public_name=d.get("publicName", ""),
            construction_dt=d.get("constructionDateTime", ""),
        )


@dataclass
class IncidentActiveSummary:
    """
    Response from /incidents?active=true — counts and ID lists only.

    Attributes:
        active_count:       Total active incident count.
        active_ids:         List of all active incident IDs.
        road_closed_ids:    Subset of IDs with road closure conditions.
        lane_closed_ids:    Subset of IDs with lane closure conditions.
    """

    active_count: int
    active_ids: List[int]
    road_closed_ids: List[int]
    lane_closed_ids: List[int]

    @classmethod
    def from_dict(cls, d: dict) -> "IncidentActiveSummary":
        return cls(
            active_count=int(d.get("activeIncidentCount", 0)),
            active_ids=d.get("activeIncidents", []),
            road_closed_ids=d.get("roadClosedIncidents", []),
            lane_closed_ids=d.get("laneClosedIncidents", []),
        )


@dataclass
class IncidentGroup:
    """
    Incident type grouping from /incidents/groups.

    Attributes:
        group:  Group label, e.g. "Road Work", "Other Incidents".
        types:  List of incident type strings in this group.
    """

    group: str
    id: str
    types: List[str]

    @classmethod
    def from_dict(cls, d: dict) -> "IncidentGroup":
        group = d.get("group", "")
        gid = group.lower().replace(" ", "-")
        return cls(group=group, id=gid, types=sorted(d.get("types", [])))


@dataclass
class Parking:
    """Parking capacity for a rest area."""

    car: int
    car_trailer: int
    truck: int

    @classmethod
    def from_dict(cls, d: dict) -> "Parking":
        return cls(
            car=int(d.get("car", 0)),
            car_trailer=int(d.get("carTrailer", 0)),
            truck=int(d.get("truck", 0)),
        )


@dataclass
class RestArea:
    """
    Rest area / welcome center from /restarealocations.

    Attributes:
        id:              Rest area identifier.
        name:            Location name, e.g. "Camden County US 17".
        title:           Display title.
        type:            "Rest Area", "Visitor Center", or "Welcome Center".
        status:          "closed" if temporarily or permanently closed.
        seasonal:        Seasonal operation note (e.g. "Open April 1 – Oct 31").
        phone:           Contact phone number.
        county:          County name.
        locale:          City or locale (optional).
        description:     Driving directions description.
        route:           Highway designation.
        bound:           Travel direction ("N", "S", "E", "W", "Median").
        mile_marker:     Mile post number (optional).
        division:        NCDOT division number.
        latitude:        WGS-84 latitude.
        longitude:       WGS-84 longitude.
        accommodations:  List of amenity strings.
        parking:         Parking capacity object.
        image_url:       URL to facility photo.
        information:     Historical/descriptive text.
        sustainable:     True if environmentally certified.
    """

    id: int
    name: str
    title: str
    type: str
    status: str
    seasonal: str
    phone: str
    county: str
    locale: str
    description: str
    route: str
    bound: str
    mile_marker: str
    division: int
    latitude: float
    longitude: float
    accommodations: List[str]
    parking: Optional[Parking]
    image_url: str
    information: str
    sustainable: bool

    @classmethod
    def from_dict(cls, d: dict) -> "RestArea":
        geo = d.get("geo", {})
        parking_data = d.get("parking")
        return cls(
            id=int(d.get("id", 0)),
            name=d.get("name", ""),
            title=d.get("title", ""),
            type=d.get("type", ""),
            status=d.get("status", ""),
            seasonal=d.get("seasonal", ""),
            phone=d.get("phone", ""),
            county=d.get("county", ""),
            locale=d.get("locale", ""),
            description=d.get("description", ""),
            route=d.get("route", ""),
            bound=d.get("bound", ""),
            mile_marker=str(d.get("mileMarker", "")),
            division=int(d.get("division", 0)),
            latitude=float(geo.get("lat", 0)) if geo else 0.0,
            longitude=float(geo.get("long", 0)) if geo else 0.0,
            accommodations=d.get("accommodations", []),
            parking=Parking.from_dict(parking_data) if parking_data else None,
            image_url=d.get("image", ""),
            information=d.get("information", ""),
            sustainable=bool(d.get("sustainable", False)),
        )


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


class HTTPError(Exception):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, url: str, status: int, body: str = "") -> None:
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")


class NCDOTError(Exception):
    """General NCDOT client error."""


def _fetch(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    raw: bool = False,
) -> object:
    """
    Perform a GET request and return the parsed JSON body (or raw bytes).

    Args:
        url:     Absolute URL to fetch.
        timeout: Socket timeout in seconds.
        raw:     If True, return the raw response bytes instead of parsed JSON.

    Returns:
        Parsed JSON object (dict or list) or raw bytes.

    Raises:
        HTTPError:    On non-2xx HTTP status codes.
        NCDOTError:   On connection errors or JSON decode failures.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json, */*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if raw:
                return body
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise NCDOTError(f"JSON decode error for {url}: {exc}") from exc
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise HTTPError(url, exc.code, body_text) from exc
    except urllib.error.URLError as exc:
        raise NCDOTError(f"Connection error for {url}: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class NCDOTClient:
    """
    Client for the NCDOT/DriveNC public traffic information API.

    All methods return typed dataclass instances. No authentication is required.

    Args:
        base_url: Override the API base URL (default: production endpoint).
        timeout:  Per-request socket timeout in seconds.

    Example::

        client = NCDOTClient()

        # List all 779 cameras
        cameras = client.list_cameras()

        # Get full details for camera 5
        cam = client.get_camera(5)
        print(cam.location_name, cam.image_url)

        # Download the live JPEG snapshot
        img_bytes = client.get_camera_image(5)
        with open("cam5.jpg", "wb") as f:
            f.write(img_bytes)

        # Get all active incidents (summary pins)
        incidents = client.list_incidents()

        # Get detailed incident record
        detail = client.get_incident(766338)
        print(detail.reason, detail.condition)

        # Search incidents by route
        results = client.search_incidents(filter_type="ROUTE", filter_value="I-40")
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _get(self, path: str, raw: bool = False) -> object:
        """Build URL from path and call _fetch."""
        url = f"{self._base}{path}"
        return _fetch(url, timeout=self._timeout, raw=raw)

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def list_cameras(self) -> List[CameraLocation]:
        """
        Return the minimal list of all cameras (id + coordinates).

        Endpoint: GET /cameras/

        Returns:
            List of CameraLocation objects sorted by ID.

        Note:
            The list endpoint returns only id/lat/lon. Use get_camera(id)
            for full details including the live image URL.
        """
        data = self._get("/cameras/")
        return [CameraLocation(
            id=d["id"],
            latitude=float(d["latitude"]),
            longitude=float(d["longitude"]),
        ) for d in data]

    def get_camera(self, camera_id: int) -> Camera:
        """
        Return full details for a single camera including its live image URL.

        Endpoint: GET /cameras/{id}

        Args:
            camera_id: The integer camera ID (from list_cameras()).

        Returns:
            Camera dataclass with location, road, county, image URL, and status.

        Raises:
            HTTPError: If camera_id is not found (404).
        """
        data = self._get(f"/cameras/{camera_id}")
        return Camera.from_dict(data)

    def get_camera_image(self, camera_id: int) -> bytes:
        """
        Download the live JPEG snapshot for a camera.

        Fetches the camera detail first to obtain the image URL, then downloads
        the binary image data.

        Args:
            camera_id: The integer camera ID.

        Returns:
            Raw JPEG image bytes. Write to a .jpg file directly.

        Raises:
            HTTPError:   If camera is not found or image is unavailable.
            NCDOTError:  On connection failures.
        """
        cam = self.get_camera(camera_id)
        if not cam.image_url:
            raise NCDOTError(f"Camera {camera_id} has no image URL")
        return _fetch(cam.image_url, timeout=self._timeout, raw=True)

    def get_camera_image_by_filename(self, filename: str) -> bytes:
        """
        Download a camera image directly by filename (e.g. "I40_US15-501.jpg").

        Endpoint: GET /cameras/images?filename={filename}

        Args:
            filename: The JPEG filename from a Camera.image_filename property.

        Returns:
            Raw JPEG image bytes.
        """
        url = f"{self._base}/cameras/images?filename={filename}"
        return _fetch(url, timeout=self._timeout, raw=True)

    def list_cameras_for_county(self, county_id: int) -> List[Camera]:
        """
        Return full camera details for all cameras in a given county.

        This is a convenience method that fetches all cameras and filters by
        county_id. For large queries, consider caching list_cameras() first.

        Args:
            county_id: The county identifier (1-100).

        Returns:
            List of Camera objects in the specified county.
        """
        all_cams = self.list_cameras()
        result = []
        for loc in all_cams:
            try:
                cam = self.get_camera(loc.id)
                if cam.county_id == county_id:
                    result.append(cam)
                    time.sleep(0.05)  # gentle rate-limiting
            except HTTPError:
                continue
        return result

    # ------------------------------------------------------------------
    # Incident endpoints
    # ------------------------------------------------------------------

    def list_incidents(self) -> List[IncidentSummary]:
        """
        Return the live incident map-pin list (lightweight records).

        Endpoint: GET /traffic/incidents

        This endpoint powers the main DriveNC map and is updated continuously.
        It returns ~350-650 incidents statewide with minimal fields suitable
        for map pin rendering.

        Returns:
            List of IncidentSummary objects. Severity 3 = highest impact.
        """
        data = self._get("/traffic/incidents")
        return [IncidentSummary.from_dict(d) for d in data]

    def get_incident(self, incident_id: int) -> IncidentDetail:
        """
        Return full details for a single incident.

        Endpoint: GET /incidents/{id}

        Args:
            incident_id: The integer incident ID (from list_incidents() or
                         search_incidents()).

        Returns:
            IncidentDetail with full location, reason, lane impact, and timing.

        Raises:
            HTTPError: If incident_id is not found (404).
        """
        data = self._get(f"/incidents/{incident_id}")
        return IncidentDetail.from_dict(data)

    def get_active_incident_summary(self) -> IncidentActiveSummary:
        """
        Return a count summary and lists of active incident IDs.

        Endpoint: GET /incidents?active=true

        Returns an IncidentActiveSummary with total count plus separate lists
        of road-closed and lane-closed incident IDs. This is the fastest way
        to check whether the network is impacted without downloading all records.

        Returns:
            IncidentActiveSummary with active count and ID lists.
        """
        data = self._get("/incidents?active=true")
        return IncidentActiveSummary.from_dict(data)

    def search_incidents(
        self,
        filter_type: str = "REGION",
        filter_value: str = "1",
        page_size: int = 100,
        page_number: int = 1,
        order_by: str = "Start",
        order: str = "desc",
    ) -> List[IncidentSearchResult]:
        """
        Search/filter incidents with pagination support.

        Endpoint: GET /incidents/filters?pageSize={n}&pageNumber={n}&...

        Args:
            filter_type:  One of COUNTY, REGION, ROUTE, ROADCLOSURE, EVENTS,
                          CONDITION, INCIDENTTYPE.
            filter_value: Value matching the filter_type:
                          - COUNTY: county id (e.g. "60" for Mecklenburg)
                          - REGION: region id (e.g. "1" for Triangle)
                          - ROUTE: road name (e.g. "I-40")
                          - ROADCLOSURE: "true" or "false"
                          - CONDITION: e.g. "Road Closed"
                          - INCIDENTTYPE: e.g. "Construction"
            page_size:    Results per page (max observed: 9999).
            page_number:  1-indexed page number.
            order_by:     Sort field (e.g. "Start", "County").
            order:        "asc" or "desc".

        Returns:
            List of IncidentSearchResult objects.

        Example::

            # All road closures statewide
            closures = client.search_incidents(
                filter_type="ROADCLOSURE", filter_value="true")

            # I-40 incidents sorted by start time descending
            i40 = client.search_incidents(
                filter_type="ROUTE", filter_value="I-40")
        """
        path = (
            f"/incidents/filters"
            f"?pageSize={page_size}"
            f"&pageNumber={page_number}"
            f"&orderBy={order_by}"
            f"&order={order}"
            f"&filterType={filter_type}"
            f"&filterValue={filter_value}"
        )
        data = self._get(path)
        if isinstance(data, list):
            return [IncidentSearchResult.from_dict(d) for d in data]
        return []

    def count_incidents(
        self,
        filter_type: str = "REGION",
        filter_value: str = "1",
    ) -> int:
        """
        Return the count of incidents matching a filter without fetching records.

        Endpoint: GET /incidents/filters/count?filterType={t}&filterValue={v}

        Args:
            filter_type:  One of COUNTY, PROJECT, REGION, ROUTE.
            filter_value: Value matching the filter_type.

        Returns:
            Integer count of matching incidents.
        """
        path = (
            f"/incidents/filters/count"
            f"?filterType={filter_type}"
            f"&filterValue={filter_value}"
        )
        data = self._get(path)
        if isinstance(data, int):
            return data
        return int(data) if data else 0

    def list_incident_groups(self) -> List[IncidentGroup]:
        """
        Return incident type groupings and all incident type strings.

        Endpoint: GET /incidents/groups

        This endpoint returns the taxonomy of incident types organized into
        groups: "Other Incidents", "Road Work", and "Truck Closures".

        Returns:
            List of IncidentGroup objects with group names and type lists.
        """
        data = self._get("/incidents/groups")
        return [IncidentGroup.from_dict(d) for d in data]

    def list_road_closures(self) -> List[IncidentSearchResult]:
        """
        Return all incidents with road-closure conditions (convenience method).

        Fetches the full statewide incident list filtered to these conditions:
        "Road Closed", "Road Closed with Detour", "Road Impassable",
        "Permanent Road Closure", "Local Traffic Only", "Ramp Closed",
        "Ferry Closed".

        Returns:
            List of IncidentSearchResult objects representing road closures.
        """
        return self.search_incidents(
            filter_type="ROADCLOSURE",
            filter_value="true",
            page_size=9999,
        )

    # ------------------------------------------------------------------
    # County/Region/Road endpoints
    # ------------------------------------------------------------------

    def list_counties(self) -> List[County]:
        """
        Return road conditions for all 100 NC counties.

        Endpoint: GET /counties/conditions

        Returns:
            List of County objects with road condition status and last-updated
            timestamps. Conditions are "Clear", "Snow/Ice", or "N/A".
        """
        data = self._get("/counties/conditions")
        return [County.from_dict(d) for d in data]

    def get_county(self, county_id: int) -> County:
        """
        Return road conditions for a single county.

        Endpoint: GET /counties/{id}/conditions

        Args:
            county_id: Integer county ID (1-100).

        Returns:
            County object with current road condition data.
        """
        data = self._get(f"/counties/{county_id}/conditions")
        return County.from_dict(data)

    def list_regions(self) -> List[Region]:
        """
        Return all geographic regions with their constituent counties.

        Endpoint: GET /traffic/regions

        Regions group counties into 9 geographic areas used for filtering
        traffic information (Triangle, Triad, Metrolina, etc.).

        Returns:
            List of Region objects.
        """
        data = self._get("/traffic/regions")
        return [Region.from_dict(d) for d in data]

    def list_roads(self) -> List[Road]:
        """
        Return all 342 monitored roads with their county associations.

        Endpoint: GET /traffic/roads

        Returns:
            List of Road objects. The id field is used as filter_value when
            calling search_incidents() with filter_type="ROUTE" ... but note
            the road name string (e.g. "I-40") works more reliably.
        """
        data = self._get("/traffic/roads")
        return [Road.from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Rest area endpoint
    # ------------------------------------------------------------------

    def list_rest_areas(self) -> List[RestArea]:
        """
        Return all NC rest areas, welcome centers, and visitor centers.

        Endpoint: GET /restarealocations

        Returns:
            List of RestArea objects including location, amenities, parking
            capacity, seasonal status, and facility photo URL.
        """
        data = self._get("/restarealocations")
        return [RestArea.from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Ferry routes (ArcGIS)
    # ------------------------------------------------------------------

    def list_ferry_routes(self) -> List[dict]:
        """
        Return NC ferry route GeoJSON features from ArcGIS.

        Endpoint: ArcGIS FeatureServer (NCDOT_FerryRoutes service)

        Returns:
            List of raw GeoJSON feature dicts (geometry + attributes).
            The exact attribute schema depends on the ArcGIS service version.
            Common fields include route name, operator, and geometry.

        Note:
            This endpoint calls the ArcGIS REST API directly and may be
            slower than the main NCDOT endpoints.
        """
        data = _fetch(ARCGIS_FERRY_URL, timeout=self._timeout)
        if isinstance(data, dict) and "features" in data:
            return data["features"]
        return []

    # ------------------------------------------------------------------
    # Traffic events
    # ------------------------------------------------------------------

    def list_traffic_events(self) -> List[dict]:
        """
        Return current traffic events (special events, incidents).

        Endpoint: GET /traffic/events

        Returns:
            List of event dicts (structure varies; currently often returns
            an empty list when no special events are active).
        """
        data = self._get("/traffic/events")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Active incidents report (Excel download)
    # ------------------------------------------------------------------

    def download_incidents_report(self) -> bytes:
        """
        Download the full active incidents report as an Excel (.xlsx) file.

        Endpoint: GET /activeincidentsreport

        Returns:
            Raw .xlsx file bytes. Write directly to a .xlsx file.

        Example::

            xlsx = client.download_incidents_report()
            with open("incidents.xlsx", "wb") as f:
                f.write(xlsx)
        """
        url = f"{self._base}/activeincidentsreport"
        return _fetch(url, timeout=60, raw=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_incident_summary(inc: IncidentSummary) -> str:
    sev_stars = "*" * inc.severity
    return (
        f"  [{inc.id}] {inc.type} | {inc.road} | "
        f"sev={sev_stars} | {inc.start[:10]} | "
        f"({inc.latitude:.4f}, {inc.longitude:.4f})"
    )


def _format_incident_detail(d: IncidentDetail) -> str:
    return "\n".join([
        f"  ID:         {d.id}",
        f"  Road:       {d.road_name}",
        f"  Location:   {d.location}",
        f"  City:       {d.city}",
        f"  County:     {d.county_name}",
        f"  Direction:  {d.direction}",
        f"  Type:       {d.incident_type}",
        f"  Condition:  {d.condition}",
        f"  Severity:   {d.severity}/3",
        f"  Lanes:      {d.lanes_closed}/{d.lanes_total} closed",
        f"  Detour:     {'Yes' if d.is_detour else 'No'}",
        f"  Start:      {d.start}",
        f"  End:        {d.end}",
        f"  Reason:     {d.reason}",
        f"  Coords:     {d.latitude:.6f}, {d.longitude:.6f}",
    ])


def _format_search_result(r: IncidentSearchResult) -> str:
    return (
        f"  [{r.id}] {r.road} | {r.condition} | {r.incident_type} | "
        f"sev={r.severity} | {r.county_name} | {r.location}"
    )


def _format_camera(cam: Camera) -> str:
    return "\n".join([
        f"  ID:          {cam.id}",
        f"  Name:        {cam.location_name}",
        f"  Mile Marker: {cam.mile_marker}",
        f"  County ID:   {cam.county_id}",
        f"  Road ID:     {cam.road_id}",
        f"  Status:      {cam.status}",
        f"  DOT Camera:  {cam.is_dot_camera}",
        f"  Coords:      {cam.latitude:.6f}, {cam.longitude:.6f}",
        f"  Image URL:   {cam.image_url}",
    ])


def main() -> None:
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="NCDOT Traffic API Client — DriveNC.gov reverse-engineered API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  cameras              List all camera IDs and coordinates
  camera ID            Show full details for a single camera
  camera-image ID      Download camera snapshot (use --save to write to file)
  incidents            List live incident map pins
  incident ID          Show full details for a single incident
  incident-summary     Show active incident counts (quick overview)
  search-incidents     Search/filter incidents (use --filter and --value)
  incident-groups      List incident type taxonomy
  counties             List all county road conditions
  county ID            Show conditions for a single county
  regions              List geographic regions
  roads                List monitored roads
  rest-areas           List rest areas and welcome centers
  ferry-routes         List ferry route GeoJSON features
  traffic-events       List current special traffic events

Examples:
  python ncdot_client.py cameras
  python ncdot_client.py camera 5
  python ncdot_client.py camera-image 5 --save /tmp/cam5.jpg
  python ncdot_client.py incidents
  python ncdot_client.py incident 766338
  python ncdot_client.py search-incidents --filter ROUTE --value I-40
  python ncdot_client.py search-incidents --filter ROADCLOSURE --value true
  python ncdot_client.py search-incidents --filter REGION --value 1
  python ncdot_client.py counties
  python ncdot_client.py county 32
  python ncdot_client.py rest-areas
""",
    )

    parser.add_argument("command", help="Command to run")
    parser.add_argument("id", nargs="?", type=str, help="Resource ID")
    parser.add_argument(
        "--base-url", default=BASE_URL, help=f"API base URL (default: {BASE_URL})"
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT, help="Request timeout seconds"
    )
    parser.add_argument(
        "--filter",
        dest="filter_type",
        default="REGION",
        help="Filter type for search-incidents: COUNTY, REGION, ROUTE, ROADCLOSURE, CONDITION, INCIDENTTYPE",
    )
    parser.add_argument(
        "--value",
        dest="filter_value",
        default="1",
        help="Filter value for search-incidents",
    )
    parser.add_argument(
        "--page-size", type=int, default=50, help="Page size for paginated results"
    )
    parser.add_argument(
        "--page", type=int, default=1, help="Page number for paginated results"
    )
    parser.add_argument(
        "--save", help="File path to save binary output (camera images, xlsx)"
    )
    parser.add_argument(
        "--county", type=int, help="Filter camera list by county ID"
    )

    args = parser.parse_args()
    client = NCDOTClient(base_url=args.base_url, timeout=args.timeout)

    cmd = args.command.lower().replace("_", "-")

    try:
        if cmd == "cameras":
            cameras = client.list_cameras()
            if args.county:
                # Filter by county — needs full fetch per camera
                print(f"Fetching cameras for county {args.county}... (this may take a moment)")
                full = client.list_cameras_for_county(args.county)
                print(f"\n{len(full)} cameras in county {args.county}:")
                for cam in full:
                    print(_format_camera(cam))
                    print()
            else:
                print(f"Total cameras: {len(cameras)}")
                print("Sample (first 10):")
                for cam in cameras[:10]:
                    print(f"  ID={cam.id:5d}  ({cam.latitude:.5f}, {cam.longitude:.5f})")

        elif cmd == "camera":
            if not args.id:
                print("ERROR: camera command requires an ID", file=sys.stderr)
                sys.exit(1)
            cam = client.get_camera(int(args.id))
            print(f"Camera {cam.id}:")
            print(_format_camera(cam))

        elif cmd == "camera-image":
            if not args.id:
                print("ERROR: camera-image command requires an ID", file=sys.stderr)
                sys.exit(1)
            print(f"Downloading image for camera {args.id}...")
            img = client.get_camera_image(int(args.id))
            if args.save:
                with open(args.save, "wb") as f:
                    f.write(img)
                print(f"Saved {len(img):,} bytes to {args.save}")
            else:
                print(f"Downloaded {len(img):,} bytes (JPEG image)")
                print("Use --save /path/to/file.jpg to write to disk")

        elif cmd == "incidents":
            incidents = client.list_incidents()
            sev3 = [i for i in incidents if i.severity == 3]
            sev2 = [i for i in incidents if i.severity == 2]
            sev1 = [i for i in incidents if i.severity == 1]
            print(f"Total active incidents: {len(incidents)}")
            print(f"  Severity 3 (high):   {len(sev3)}")
            print(f"  Severity 2 (medium): {len(sev2)}")
            print(f"  Severity 1 (low):    {len(sev1)}")
            print("\nSeverity 3 incidents (showing up to 10):")
            for inc in sev3[:10]:
                print(_format_incident_summary(inc))

        elif cmd == "incident":
            if not args.id:
                print("ERROR: incident command requires an ID", file=sys.stderr)
                sys.exit(1)
            detail = client.get_incident(int(args.id))
            print(f"Incident {detail.id}:")
            print(_format_incident_detail(detail))

        elif cmd == "incident-summary":
            summary = client.get_active_incident_summary()
            print(f"Active incidents:  {summary.active_count}")
            print(f"Road closures:     {len(summary.road_closed_ids)}")
            print(f"Lane closures:     {len(summary.lane_closed_ids)}")

        elif cmd in ("search-incidents", "search"):
            results = client.search_incidents(
                filter_type=args.filter_type.upper(),
                filter_value=args.filter_value,
                page_size=args.page_size,
                page_number=args.page,
            )
            print(
                f"Incidents ({args.filter_type}={args.filter_value}): "
                f"{len(results)} results"
            )
            for r in results[:20]:
                print(_format_search_result(r))
            if len(results) > 20:
                print(f"  ... and {len(results) - 20} more")

        elif cmd == "incident-groups":
            groups = client.list_incident_groups()
            for g in groups:
                print(f"\n{g.group} ({g.id}):")
                for t in g.types:
                    print(f"  - {t}")

        elif cmd == "counties":
            counties = client.list_counties()
            print(f"Total counties: {len(counties)}")
            active = [c for c in counties if c.status != "No Report"]
            print(f"With active reports: {len(active)}")
            print("\nAll county conditions (first 20):")
            for c in counties[:20]:
                rc = c.road_conditions
                print(
                    f"  [{c.id:3d}] {c.name:<20s} | "
                    f"Interstate:{rc.get('interstate','N/A'):5s} | "
                    f"Primary:{rc.get('primary','N/A'):5s} | "
                    f"Status:{c.status}"
                )

        elif cmd == "county":
            if not args.id:
                print("ERROR: county command requires an ID", file=sys.stderr)
                sys.exit(1)
            c = client.get_county(int(args.id))
            rc = c.road_conditions
            print(f"County {c.id}: {c.name}")
            print(f"  Regions:     {c.regions}")
            print(f"  Interstate:  {rc.get('interstate', 'N/A')}")
            print(f"  Primary:     {rc.get('primary', 'N/A')}")
            print(f"  Secondary:   {rc.get('secondary', 'N/A')}")
            print(f"  Status:      {c.status}")
            print(f"  Updated:     {c.last_updated}")

        elif cmd == "regions":
            regions = client.list_regions()
            print(f"Total regions: {len(regions)}")
            for r in regions:
                county_names = ", ".join(c["name"] for c in r.counties[:4])
                if len(r.counties) > 4:
                    county_names += f" ... (+{len(r.counties) - 4} more)"
                print(f"  [{r.id}] {r.name}: {county_names}")

        elif cmd == "roads":
            roads = client.list_roads()
            print(f"Total roads: {len(roads)}")
            print("\nSample (first 15):")
            for road in roads[:15]:
                print(f"  [{road.id:4d}] {road.name:<12s} -> {road.counties[:60]}")

        elif cmd == "rest-areas":
            areas = client.list_rest_areas()
            print(f"Total rest areas/centers: {len(areas)}")
            open_areas = [a for a in areas if a.status != "closed"]
            print(f"Open facilities: {len(open_areas)}")
            print("\nSample facilities:")
            for a in areas[:8]:
                status_str = f" [{a.status.upper()}]" if a.status == "closed" else ""
                print(f"  [{a.id:2d}] {a.name}{status_str}")
                print(f"       Type: {a.type} | Route: {a.route} | County: {a.county}")
                if a.accommodations:
                    print(f"       Amenities: {', '.join(a.accommodations[:4])}")
                print()

        elif cmd == "ferry-routes":
            routes = client.list_ferry_routes()
            print(f"Ferry routes: {len(routes)} features")
            for r in routes[:5]:
                attrs = r.get("attributes", {})
                geom = r.get("geometry", {})
                print(f"  Attributes: {attrs}")
                if geom:
                    coords = geom.get("paths", [[]])[0]
                    print(f"  Path points: {len(coords)}")
                print()

        elif cmd == "traffic-events":
            events = client.list_traffic_events()
            print(f"Traffic events: {len(events)}")
            for e in events[:10]:
                print(f"  {e}")

        elif cmd == "download-report":
            print("Downloading active incidents Excel report...")
            xlsx = client.download_incidents_report()
            path = args.save or "incidents.xlsx"
            with open(path, "wb") as f:
                f.write(xlsx)
            print(f"Saved {len(xlsx):,} bytes to {path}")

        else:
            print(f"Unknown command: {cmd}", file=sys.stderr)
            parser.print_help()
            sys.exit(1)

    except HTTPError as exc:
        print(f"HTTP Error {exc.status}: {exc.body[:200]}", file=sys.stderr)
        sys.exit(1)
    except NCDOTError as exc:
        print(f"NCDOT Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
