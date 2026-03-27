"""
Nebraska Department of Transportation (NDOT/NDOR) Traffic Camera API Client
============================================================================

Reverse-engineered from https://511.nebraska.gov (version 3.19.8)

The site uses two primary APIs:
  1. REST API at https://netg.carsprogram.org  (Castle Rock ITS / CARSProgram)
  2. GraphQL API at https://511.nebraska.gov/api/graphql

No authentication or API keys are required for public data access.
Camera images are served from https://dot511.nebraska.gov/images/

Usage:
    client = NDORClient()

    # Get all cameras (REST)
    cameras = client.get_cameras()

    # Get single camera detail
    cam = client.get_camera(5)

    # Search cameras by route
    i80_cams = client.get_cameras_by_route("I-80")

    # Get map features via GraphQL
    features = client.get_map_features(
        north=41.5, south=40.8, east=-96.0, west=-97.5,
        layer_slugs=["normalCameras"]
    )

    # Get variable message signs
    signs = client.get_signs()

    # Download a camera image
    img = client.download_image("https://dot511.nebraska.gov/images/vid-004080257-00.jpg")
    with open("camera.jpg", "wb") as f:
        f.write(img)
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REST_BASE = "https://netg.carsprogram.org"
_GQL_URL = "https://511.nebraska.gov/api/graphql"
_IMAGE_CDN = "https://dot511.nebraska.gov/images"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Origin": "https://511.nebraska.gov",
    "Referer": "https://511.nebraska.gov/",
    "Accept": "application/json, */*",
}

# Layer slugs discovered from the JS bundle (f2p enum)
# Used as ``layerSlugs`` values in the GraphQL MapFeatures query.
LAYER_SLUGS = {
    # Cameras
    "NORMAL_CAMERA": "normalCameras",
    "HOT_CAMERA": "hotCameras",          # severe weather cameras
    "PLOW_CAMERA": "plowCameras",
    # Events / incidents
    "CONSTRUCTION": "constructionReports",
    "ROAD_REPORTS": "roadReports",
    "CLOSURES": "roadClosures",
    "WINTER_DRIVING": "winterDriving",
    "FLOOD_REPORTS": "floodReports",
    "WAZE_REPORTS": "wazeReports",
    "WEATHER_WARNINGS": "weatherWarningsAreaEvents",
    "METRO_TRAFFIC": "metroTrafficMap",
    "TRUCKERS_REPORTS": "truckersReports",
    # Infrastructure
    "REST_AREAS": "restAreas",
    "SIGNS_ACTIVE": "electronicSigns",
    "SIGNS_INACTIVE": "electronicSignsInactive",
    "TRAFFIC_SPEED": "trafficSpeeds",
    "RWIS_NORMAL": "stationsNormal",     # Road Weather Information System
    "RWIS_ALERT": "stationsAlert",
    "PLOW_LOCATION": "plowLocations",
    "FUELING_STATIONS": "fuelingStations",
    "OVERSIZE_LOADS": "oversizeLoads",
    "BRIDGE_HEIGHTS": "bridgeHeights",
    "POSTED_BRIDGES": "postedBridges",
    "MILE_MARKERS": "mileMarkers",
    "WEATHER_RADAR": "weatherRadar",
    # Nebraska bounding box (approx)
    # west=-104.06, south=40.00, east=-95.31, north=43.00
}

# Nebraska approximate bounding box
NE_BOUNDS = {
    "west": -104.06,
    "south": 40.00,
    "east": -95.31,
    "north": 43.00,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CameraLocation:
    """Geographic location metadata for a camera."""
    latitude: float
    longitude: float
    route_id: Optional[str] = None
    linear_reference: Optional[float] = None
    city_reference: Optional[str] = None
    fips: Optional[int] = None
    local_road: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "CameraLocation":
        return cls(
            latitude=d.get("latitude", 0.0),
            longitude=d.get("longitude", 0.0),
            route_id=d.get("routeId"),
            linear_reference=d.get("linearReference"),
            city_reference=d.get("cityReference"),
            fips=d.get("fips"),
            local_road=d.get("localRoad", False),
        )


@dataclass
class CameraView:
    """A single image/video view from a camera."""
    name: str
    type: str           # "STILL_IMAGE" | "WMP"
    url: str
    video_preview_url: Optional[str] = None
    image_timestamp: Optional[int] = None  # epoch ms

    @classmethod
    def from_dict(cls, d: dict) -> "CameraView":
        return cls(
            name=d.get("name", ""),
            type=d.get("type", "STILL_IMAGE"),
            url=d.get("url", ""),
            video_preview_url=d.get("videoPreviewUrl"),
            image_timestamp=d.get("imageTimestamp"),
        )

    @property
    def image_url(self) -> str:
        """Return the best available image URL."""
        return self.url or self.video_preview_url or ""

    @property
    def is_still_image(self) -> bool:
        return self.type == "STILL_IMAGE"

    @property
    def is_video(self) -> bool:
        return self.type == "WMP"


@dataclass
class Camera:
    """A traffic surveillance camera."""
    id: int
    name: str
    public: bool
    last_updated: int           # epoch ms
    location: CameraLocation
    views: list[CameraView] = field(default_factory=list)
    camera_owner: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            public=d.get("public", True),
            last_updated=d.get("lastUpdated", 0),
            location=CameraLocation.from_dict(d.get("location", {})),
            views=[CameraView.from_dict(v) for v in d.get("views", [])],
            camera_owner=d.get("cameraOwner", {}).get("name") if d.get("cameraOwner") else None,
        )

    @property
    def last_updated_ts(self) -> float:
        """Unix timestamp (seconds)."""
        return self.last_updated / 1000

    @property
    def image_urls(self) -> list[str]:
        """All still image URLs for this camera."""
        return [v.url for v in self.views if v.url]

    def __repr__(self) -> str:
        return (
            f"Camera(id={self.id}, name={self.name!r}, "
            f"route={self.location.route_id!r}, views={len(self.views)})"
        )


@dataclass
class SignLocation:
    """Location metadata for a variable message sign."""
    latitude: float
    longitude: float
    route_id: Optional[str] = None
    linear_reference: Optional[float] = None
    city_reference: Optional[str] = None
    location_description: Optional[str] = None
    sign_facing_direction: Optional[str] = None
    fips: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "SignLocation":
        return cls(
            latitude=d.get("latitude", 0.0),
            longitude=d.get("longitude", 0.0),
            route_id=d.get("routeId"),
            linear_reference=d.get("linearReference"),
            city_reference=d.get("cityReference"),
            location_description=d.get("locationDescription"),
            sign_facing_direction=d.get("signFacingDirection"),
            fips=d.get("fips"),
        )


@dataclass
class SignPage:
    """A single phase/page on a variable message sign."""
    lines: list[str]
    justification: str = "CENTER"
    has_image: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "SignPage":
        return cls(
            lines=d.get("lines", []),
            justification=d.get("justification", "CENTER"),
            has_image=d.get("hasImage", False),
        )

    def as_text(self) -> str:
        return " / ".join(self.lines)


@dataclass
class Sign:
    """A variable message sign (VMS / DMS)."""
    id: str
    name: str
    status: str          # e.g. "DISPLAYING_MESSAGE", "BLANK"
    agency_id: str
    agency_name: str
    last_updated: int    # epoch ms
    location: SignLocation
    pages: list[SignPage] = field(default_factory=list)
    id_for_display: Optional[str] = None
    max_lines_per_page: int = 3
    max_chars_per_line: int = 16

    @classmethod
    def from_dict(cls, d: dict) -> "Sign":
        display = d.get("display", {})
        raw_pages = display.get("pages", [])
        props = d.get("properties", {})
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            status=d.get("status", ""),
            agency_id=d.get("agencyId", ""),
            agency_name=d.get("agencyName", ""),
            last_updated=d.get("lastUpdated", 0),
            location=SignLocation.from_dict(d.get("location", {})),
            pages=[SignPage.from_dict(p) for p in raw_pages],
            id_for_display=d.get("idForDisplay"),
            max_lines_per_page=props.get("maxLinesPerPage", 3),
            max_chars_per_line=props.get("maxCharactersPerLine", 16),
        )

    @property
    def current_message(self) -> str:
        """Return all pages concatenated with ' | '."""
        if not self.pages:
            return ""
        return " | ".join(p.as_text() for p in self.pages if p.lines)

    @property
    def is_displaying(self) -> bool:
        return self.status == "DISPLAYING_MESSAGE"

    def __repr__(self) -> str:
        return (
            f"Sign(id={self.id_for_display!r}, route={self.location.route_id!r}, "
            f"msg={self.current_message!r})"
        )


@dataclass
class MapFeature:
    """A feature returned from the GraphQL MapFeatures query."""
    uri: str
    title: str
    typename: str
    bbox: Optional[list[float]] = None
    # Camera-specific
    active: Optional[bool] = None
    view_urls: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "MapFeature":
        views = d.get("views") or []
        urls = [v.get("url", "") for v in views if v.get("url")]
        return cls(
            uri=d.get("uri", ""),
            title=d.get("title", ""),
            typename=d.get("__typename", ""),
            bbox=d.get("bbox"),
            active=d.get("active"),
            view_urls=urls,
        )

    def __repr__(self) -> str:
        return f"MapFeature(uri={self.uri!r}, title={self.title!r}, type={self.typename!r})"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class NDORError(Exception):
    """Raised when an API call fails."""


def _http_get(url: str, headers: Optional[dict] = None, timeout: int = 20) -> bytes:
    """Perform a GET request and return the raw bytes."""
    req_headers = {**_DEFAULT_HEADERS}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise NDORError(f"HTTP {exc.code} for {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise NDORError(f"Network error for {url}: {exc.reason}") from exc


def _http_post_json(url: str, payload: dict, timeout: int = 20) -> dict:
    """POST JSON to *url* and parse the JSON response."""
    body = json.dumps(payload).encode("utf-8")
    req_headers = {
        **_DEFAULT_HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:400]
        raise NDORError(
            f"HTTP {exc.code} for {url}: {exc.reason}. Body: {body_text}"
        ) from exc
    except urllib.error.URLError as exc:
        raise NDORError(f"Network error for {url}: {exc.reason}") from exc


def _rest_get(path: str, timeout: int = 20) -> Any:
    """GET from the REST base URL and parse JSON."""
    url = f"{_REST_BASE}/{path.lstrip('/')}"
    raw = _http_get(url, timeout=timeout)
    return json.loads(raw)


def _graphql(query: str, variables: Optional[dict] = None, timeout: int = 20) -> dict:
    """Execute a GraphQL query against the Nebraska 511 endpoint."""
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    data = _http_post_json(_GQL_URL, payload, timeout=timeout)
    if "errors" in data and data["errors"] and "data" not in data:
        msgs = "; ".join(e.get("message", str(e)) for e in data["errors"])
        raise NDORError(f"GraphQL error: {msgs}")
    return data


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class NDORClient:
    """
    Client for the Nebraska 511 (NDOT/NDOR) traffic information system.

    Provides access to:
      - Traffic cameras (352 statewide)
      - Variable message signs / DMS (414 statewide)
      - Map features via GraphQL (cameras, events, signs, weather, plows...)
      - Raw image download for camera stills

    No authentication or API keys are required.

    Example::

        client = NDORClient()
        cameras = client.get_cameras()
        print(f"Found {len(cameras)} cameras")

        i80 = client.get_cameras_by_route("I-80")
        for cam in i80[:3]:
            print(cam, cam.image_urls)
    """

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # REST: Cameras
    # ------------------------------------------------------------------

    def get_cameras(self) -> list[Camera]:
        """
        Return all 352 public traffic cameras in Nebraska.

        REST endpoint: GET /cameras_v1/api/cameras

        Each camera includes location (lat/lon, route, mile marker) and a list
        of views with image URLs.
        """
        data = _rest_get("cameras_v1/api/cameras", timeout=self.timeout)
        return [Camera.from_dict(d) for d in data]

    def get_camera(self, camera_id: int) -> Camera:
        """
        Return details for a single camera by its integer ID.

        REST endpoint: GET /cameras_v1/api/cameras/{id}

        Args:
            camera_id: Integer camera ID (e.g. 5)
        """
        data = _rest_get(f"cameras_v1/api/cameras/{camera_id}", timeout=self.timeout)
        return Camera.from_dict(data)

    def get_cameras_by_route(self, route_id: str) -> list[Camera]:
        """
        Filter all cameras by route ID (e.g. "I-80", "US 30", "NE 2").

        This performs a full camera list fetch and filters client-side.
        Route IDs are case-sensitive.

        Common routes: I-80, I-180, I-480, I-680, US 20, US 30, US 77,
                       NE 2, NE 7, NE 50, NE 71, NE 92, ...
        """
        cameras = self.get_cameras()
        return [c for c in cameras if c.location.route_id == route_id]

    def get_cameras_by_bounds(
        self,
        north: float,
        south: float,
        east: float,
        west: float,
    ) -> list[Camera]:
        """
        Filter cameras within a geographic bounding box.

        This performs a full camera list fetch and filters client-side.

        Args:
            north: Northern latitude bound
            south: Southern latitude bound
            east:  Eastern longitude bound
            west:  Western longitude bound
        """
        cameras = self.get_cameras()
        return [
            c
            for c in cameras
            if south <= c.location.latitude <= north
            and west <= c.location.longitude <= east
        ]

    # ------------------------------------------------------------------
    # REST: Signs (Variable Message Signs / DMS)
    # ------------------------------------------------------------------

    def get_signs(self) -> list[Sign]:
        """
        Return all 414 variable message signs (DMS/VMS) in Nebraska.

        REST endpoint: GET /signs_v1/api/signs

        Each sign includes its current displayed message, location, and
        display properties.
        """
        data = _rest_get("signs_v1/api/signs", timeout=self.timeout)
        return [Sign.from_dict(d) for d in data]

    def get_sign(self, sign_id: str) -> Sign:
        """
        Return a single sign by its string ID.

        Sign IDs have the format ``"nebraskasigns*D5-80-14 EB VSA"``.

        REST endpoint: GET /signs_v1/api/signs/{id}
        """
        encoded = urllib.parse.quote(sign_id, safe="")
        data = _rest_get(f"signs_v1/api/signs/{encoded}", timeout=self.timeout)
        return Sign.from_dict(data)

    def get_active_signs(self) -> list[Sign]:
        """Return only signs that are currently displaying a message."""
        return [s for s in self.get_signs() if s.is_displaying]

    def get_signs_by_route(self, route_id: str) -> list[Sign]:
        """
        Filter all signs by route ID (e.g. "I-80").

        Performs a full sign list fetch and filters client-side.
        """
        return [s for s in self.get_signs() if s.location.route_id == route_id]

    # ------------------------------------------------------------------
    # GraphQL: Map Features
    # ------------------------------------------------------------------

    def get_map_features(
        self,
        north: float,
        south: float,
        east: float,
        west: float,
        zoom: int = 8,
        layer_slugs: Optional[list[str]] = None,
    ) -> list[MapFeature]:
        """
        Fetch map features from the GraphQL API for a geographic bounding box.

        This is the primary data source used by the 511 web app to populate
        the map.  Features can include cameras, events, signs, weather
        stations, etc.

        Args:
            north: Northern latitude bound
            south: Southern latitude bound
            east:  Eastern longitude bound (negative for Nebraska)
            west:  Western longitude bound (negative for Nebraska)
            zoom:  Map zoom level; lower zoom = more clustering.
                   Use zoom >= 8 to get individual features.
            layer_slugs: Which data layers to include.  Defaults to
                         ``["normalCameras"]``.  See ``LAYER_SLUGS`` for all
                         available values.

        Returns:
            List of :class:`MapFeature` objects.

        Example::

            features = client.get_map_features(
                north=41.5, south=40.8, east=-96.0, west=-97.5,
                layer_slugs=["normalCameras", "constructionReports"]
            )
        """
        if layer_slugs is None:
            layer_slugs = ["normalCameras"]

        # NOTE: inline fragments (... on Camera { active }) trigger a server-side
        # 400 for some field combinations; the base query below is stable.
        query = """
query MapFeatures($input: MapFeaturesArgs!) {
    mapFeaturesQuery(input: $input) {
        mapFeatures {
            bbox
            title
            uri
            __typename
        }
        error {
            message
            type
        }
    }
}
"""
        variables = {
            "input": {
                "north": north,
                "south": south,
                "east": east,
                "west": west,
                "zoom": zoom,
                "layerSlugs": layer_slugs,
            }
        }
        resp = _graphql(query, variables, timeout=self.timeout)
        mfq = (resp.get("data") or {}).get("mapFeaturesQuery") or {}
        error = mfq.get("error")
        if error:
            raise NDORError(f"MapFeatures error: {error}")
        features = mfq.get("mapFeatures") or []
        return [MapFeature.from_dict(f) for f in features]

    def get_statewide_cameras_gql(self) -> list[MapFeature]:
        """
        Return all camera features statewide via the GraphQL API.

        Equivalent to calling :meth:`get_map_features` with Nebraska bounding
        box and the ``normalCameras`` + ``hotCameras`` layers.
        """
        return self.get_map_features(
            north=NE_BOUNDS["north"],
            south=NE_BOUNDS["south"],
            east=NE_BOUNDS["east"],
            west=NE_BOUNDS["west"],
            zoom=8,
            layer_slugs=["normalCameras", "hotCameras"],
        )

    def get_camera_detail_gql(self, camera_id: str) -> dict:
        """
        Fetch detailed info for a single camera via GraphQL.

        Args:
            camera_id: Numeric camera ID as string (e.g. ``"5"``)

        Returns:
            Raw dict from the ``cameraQuery`` GraphQL response.
        """
        query = """
query Camera($cameraId: ID!) {
    cameraQuery(cameraId: $cameraId) {
        camera {
            uri
            title
            active
            bbox
            icon
            lastUpdated {
                timestamp
                timezone
            }
            views(limit: 10) {
                uri
                category
            }
        }
        error {
            type
        }
    }
}
"""
        resp = _graphql(query, {"cameraId": str(camera_id)}, timeout=self.timeout)
        data = (resp.get("data") or {}).get("cameraQuery") or {}
        if data.get("error"):
            raise NDORError(f"Camera not found: {camera_id!r}")
        return data.get("camera") or {}

    def get_event_detail_gql(self, event_id: str) -> dict:
        """
        Fetch detailed info for a traffic event/incident via GraphQL.

        Args:
            event_id: Event URI or numeric ID (e.g. ``"event/12345"`` or
                      ``"12345"``)

        Returns:
            Raw dict from the ``eventQuery`` GraphQL response.
        """
        query = """
query Event($eventId: ID!, $layerSlugs: [String!]!) {
    eventQuery(eventId: $eventId, layerSlugs: $layerSlugs) {
        event {
            uri
            title
            description
            bbox
            icon
            color
            lastUpdated { timestamp timezone }
            beginTime { timestamp timezone }
            priority
            active
            verified
            isWazeEvent
        }
        error {
            type
        }
    }
}
"""
        variables = {
            "eventId": str(event_id),
            "layerSlugs": [
                "constructionReports",
                "roadReports",
                "roadClosures",
                "winterDriving",
                "floodReports",
                "metroTrafficMap",
            ],
        }
        resp = _graphql(query, variables, timeout=self.timeout)
        data = (resp.get("data") or {}).get("eventQuery") or {}
        if data.get("error"):
            raise NDORError(f"Event not found: {event_id!r}")
        return data.get("event") or {}

    def get_rest_area_detail_gql(self, rest_area_id: str) -> dict:
        """
        Fetch detailed info for a rest area via GraphQL.

        Args:
            rest_area_id: Rest area URI or numeric ID.

        Returns:
            Raw dict from the ``restAreaQuery`` GraphQL response.
        """
        query = """
query RestArea($restAreaId: ID!) {
    restAreaQuery(restAreaId: $restAreaId) {
        restArea {
            uri
            title
            lastUpdated { timestamp timezone }
            description
            status
            statusMessage
            bbox
            icon
            restAreaAmenities {
                icon
                label
            }
        }
        error {
            type
        }
    }
}
"""
        resp = _graphql(query, {"restAreaId": str(rest_area_id)}, timeout=self.timeout)
        data = (resp.get("data") or {}).get("restAreaQuery") or {}
        if data.get("error"):
            raise NDORError(f"Rest area not found: {rest_area_id!r}")
        return data.get("restArea") or {}

    # ------------------------------------------------------------------
    # Image download
    # ------------------------------------------------------------------

    def download_image(self, url: str) -> bytes:
        """
        Download a camera image and return raw bytes.

        Camera still images are served from:
            ``https://dot511.nebraska.gov/images/``

        URL format: ``vid-{district}{route}{milepost}-{view}.jpg``
        Example:    ``vid-004080257-00.jpg``

        Args:
            url: Full image URL (from ``CameraView.url``)

        Returns:
            Raw JPEG bytes.
        """
        return _http_get(url, timeout=self.timeout)

    # ------------------------------------------------------------------
    # CMS / configuration
    # ------------------------------------------------------------------

    def get_cms_configurations(self) -> dict:
        """
        Fetch CMS configuration data (site settings, feature flags, etc).

        REST endpoint: GET /cms_v1/api/cms/configurations
        """
        return _rest_get("cms_v1/api/cms/configurations", timeout=self.timeout)

    def get_notifications_gql(self) -> list[dict]:
        """
        Fetch site-wide notification banners via GraphQL.

        Returns a list of notification dicts with keys:
        ``uri``, ``title``, ``description``, ``icon``, ``lastUpdated``
        """
        query = """
query Notifications {
    notificationsQuery {
        notifications {
            uri
            title
            description
            icon
            iconAlt
            borderColor
            lastUpdated {
                timestamp
                timezone
            }
        }
    }
}
"""
        resp = _graphql(query, timeout=self.timeout)
        return (
            (resp.get("data") or {})
            .get("notificationsQuery", {})
            .get("notifications", [])
        )

    # ------------------------------------------------------------------
    # Utility / summary helpers
    # ------------------------------------------------------------------

    def camera_summary(self) -> dict:
        """
        Return a summary dict with counts grouped by route, view type, etc.

        Returns::

            {
                "total": 352,
                "routes": {"I-80": 87, "US 30": 15, ...},
                "view_types": {"STILL_IMAGE": 351, "WMP": 1},
                "owners": {"NDOR": 352},
            }
        """
        cameras = self.get_cameras()
        routes: dict[str, int] = {}
        view_types: dict[str, int] = {}
        owners: dict[str, int] = {}

        for cam in cameras:
            r = cam.location.route_id or "Unknown"
            routes[r] = routes.get(r, 0) + 1
            o = cam.camera_owner or "Unknown"
            owners[o] = owners.get(o, 0) + 1
            for v in cam.views:
                vt = v.type
                view_types[vt] = view_types.get(vt, 0) + 1

        return {
            "total": len(cameras),
            "routes": dict(sorted(routes.items(), key=lambda x: -x[1])),
            "view_types": view_types,
            "owners": owners,
        }

    def sign_summary(self) -> dict:
        """
        Return a summary dict of sign statistics.

        Returns::

            {
                "total": 414,
                "displaying": 310,
                "blank": 104,
                "routes": {"I-80": 62, ...},
            }
        """
        signs = self.get_signs()
        displaying = sum(1 for s in signs if s.is_displaying)
        routes: dict[str, int] = {}
        for s in signs:
            r = s.location.route_id or "Unknown"
            routes[r] = routes.get(r, 0) + 1

        return {
            "total": len(signs),
            "displaying": displaying,
            "blank": len(signs) - displaying,
            "routes": dict(sorted(routes.items(), key=lambda x: -x[1])),
        }


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------


def _demo() -> None:
    """Quick demo / smoke test that exercises the main API methods."""
    print("Nebraska 511 NDOR API Client - Live Test")
    print("=" * 50)

    client = NDORClient(timeout=30)

    # --- Cameras (REST) ---
    print("\n[1] Fetching all cameras via REST API...")
    cameras = client.get_cameras()
    print(f"    Total cameras: {len(cameras)}")
    sample = cameras[0]
    print(f"    Sample: {sample}")
    print(f"    Location: {sample.location.city_reference} ({sample.location.route_id})")
    print(f"    Image URL: {sample.image_urls[0] if sample.image_urls else 'N/A'}")
    last_upd = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(sample.last_updated_ts))
    print(f"    Last updated: {last_upd}")

    # --- Filter by route ---
    print("\n[2] Cameras on I-80...")
    i80 = client.get_cameras_by_route("I-80")
    print(f"    I-80 cameras: {len(i80)}")
    for c in i80[:3]:
        print(f"      {c.name:40s}  {c.location.city_reference}")

    # --- Single camera ---
    print("\n[3] Single camera detail (ID=5)...")
    cam5 = client.get_camera(5)
    print(f"    {cam5}")
    for v in cam5.views:
        print(f"      View: {v.name!r}  type={v.type}  url={v.url}")

    # --- Signs (REST) ---
    print("\n[4] Fetching all signs via REST API...")
    signs = client.get_signs()
    print(f"    Total signs: {len(signs)}")
    active = [s for s in signs if s.is_displaying]
    print(f"    Currently displaying: {len(active)}")
    if active:
        s0 = active[0]
        print(f"    Sample sign: {s0}")

    # --- GraphQL map features ---
    print("\n[5] GraphQL MapFeatures - cameras around Lincoln NE...")
    features = client.get_map_features(
        north=41.0, south=40.7, east=-96.5, west=-97.0,
        zoom=10,
        layer_slugs=["normalCameras"],
    )
    print(f"    Features returned: {len(features)}")
    for f in features[:3]:
        print(f"      {f}")

    # --- Camera detail via GraphQL ---
    print("\n[6] GraphQL Camera detail (ID=5)...")
    cam_gql = client.get_camera_detail_gql("5")
    print(f"    uri={cam_gql.get('uri')} title={cam_gql.get('title')} active={cam_gql.get('active')}")

    # --- Summary stats ---
    print("\n[7] Camera summary...")
    summary = client.camera_summary()
    print(f"    Total: {summary['total']}")
    print(f"    View types: {summary['view_types']}")
    top5 = list(summary["routes"].items())[:5]
    print(f"    Top routes: {top5}")

    print("\n[8] Sign summary...")
    ss = client.sign_summary()
    print(f"    Total: {ss['total']}, displaying: {ss['displaying']}, blank: {ss['blank']}")
    top5s = list(ss["routes"].items())[:5]
    print(f"    Top routes: {top5s}")

    print("\nAll tests passed!")


if __name__ == "__main__":
    _demo()
