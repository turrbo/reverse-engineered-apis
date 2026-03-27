"""
indot_client.py — INDOT TrafficWise (511in.org) Python Client
=============================================================

Reverse-engineered client for the Indiana Department of Transportation (INDOT)
TrafficWise traffic monitoring system at https://511in.org (formerly trafficwise.org /
indot.carsprogram.org).

The site exposes a GraphQL API at https://511in.org/api/graphql that is the single
source of truth for:
  - Traffic cameras (live JPEG snapshots and HLS/FLV streams)
  - Traffic incidents, crashes, closures
  - Construction events
  - Snowplow / AVL vehicle tracking
  - Electronic / DMS signs
  - RWIS weather stations and road conditions
  - Rest areas
  - Travel-time delays

No authentication or API key is required for read-only data access.

Architecture
------------
The frontend is a React/Redux SPA that communicates exclusively through a GraphQL
proxy at ``/api/graphql``.  The proxy itself fans requests out to a set of
microservices hosted on ``https://intg.carsprogram.org`` (the production CARS
platform back-end shared across many US state 511 systems):

  * cameras_v1        — camera metadata
  * events_v1         — incidents, construction, closures
  * avl_v2            — snowplow / AVL vehicle tracking
  * signs_v1          — DMS / electronic signs
  * rwis_v1           — road weather information systems
  * rest-areas_v1     — rest area status
  * traveltimes_v1    — travel-time delays
  * locations_v1      — geocoding / route search

Camera images are served from a public CDN:
  ``https://public.carsprogram.org/cameras/IN/{camera_filename}.flv.png``

Usage
-----
Run directly as a CLI demo::

    python indot_client.py

Or use programmatically::

    from indot_client import INDOTClient

    client = INDOTClient()

    # List cameras in the Indianapolis area
    cameras = client.get_cameras_in_bounds(39.65, 39.95, -86.30, -86.00, zoom=12)
    for cam in cameras:
        print(cam.title, cam.image_url)

    # Statewide incidents
    incidents = client.get_incidents()
    for inc in incidents:
        print(inc.title, inc.priority)

    # Snowplow tracking
    plows = client.get_plows()
    for plow in plows:
        print(plow.title, plow.location_description)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPHQL_URL = "https://511in.org/api/graphql"

#: Bounding box for the entire state of Indiana (west, south, east, north)
INDIANA_BBOX: Tuple[float, float, float, float] = (-88.10, 37.77, -84.78, 41.77)

# Layer slugs discovered from the JavaScript bundle (shared-*.js)
LAYER_CAMERAS = "normalCameras"          # Regular roadside cameras
LAYER_HOT_CAMERAS = "hotCameras"         # High-priority / featured cameras
LAYER_PLOW_CAMERAS = "plowCameras"       # Cameras mounted on snowplows
LAYER_PLOW_LOCATIONS = "plowLocations"   # Snowplow GPS positions
LAYER_INCIDENTS = "incidents"            # Crashes, stalls, hazards
LAYER_CONSTRUCTION = "construction"      # Active construction zones
LAYER_ROADWORK = "roadwork"              # Scheduled roadwork
LAYER_CLOSURES = "closures"             # Full road closures
LAYER_SIGNS_ACTIVE = "electronicSigns"   # DMS signs with current messages
LAYER_SIGNS_INACTIVE = "electronicSignsInactive"
LAYER_RWIS_NORMAL = "stationsNormal"     # RWIS weather stations (normal)
LAYER_RWIS_ALERT = "stationsAlert"       # RWIS weather stations (alert)
LAYER_TRAFFIC_SPEEDS = "trafficSpeeds"   # Traffic speed / flow data
LAYER_REST_AREAS = "restAreas"           # Rest area status
LAYER_WEATHER_RADAR = "weatherRadar"     # Precipitation radar overlay
LAYER_WINTER_DRIVING = "winterDriving"   # Winter driving conditions
LAYER_FLOODING = "flooding"              # Flood events

# Camera image CDN pattern
CDN_CAMERA_BASE = "https://public.carsprogram.org/cameras/IN/"

DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BBox:
    """Geographic bounding box: [west, south, east, north]."""

    west: float
    south: float
    east: float
    north: float

    @classmethod
    def from_list(cls, bbox: List[float]) -> "BBox":
        """Construct from the ``[west, south, east, north]`` list returned by the API."""
        return cls(west=bbox[0], south=bbox[1], east=bbox[2], north=bbox[3])

    @property
    def center(self) -> Tuple[float, float]:
        """Return (longitude, latitude) centroid."""
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"BBox(west={self.west:.5f}, south={self.south:.5f}, "
            f"east={self.east:.5f}, north={self.north:.5f})"
        )


@dataclass
class CameraView:
    """A single view (angle / image) associated with a camera or plow."""

    uri: str
    category: str  # e.g. "VIDEO", "STILL_IMAGE"
    url: str  # Direct URL to current JPEG snapshot or placeholder SVG
    sources: List[Dict[str, str]] = field(default_factory=list)
    # Each source dict has keys: "type" (e.g. "application/x-mpegURL") and "src"

    @property
    def is_live(self) -> bool:
        """Return True if the URL points to a live CDN image (not a placeholder)."""
        return self.url.startswith("http") and self.url.endswith(".png")

    @property
    def hls_url(self) -> Optional[str]:
        """Return HLS stream URL if available in sources, else None."""
        for src in self.sources:
            if "mpegURL" in src.get("type", "") or src.get("src", "").endswith(".m3u8"):
                return src["src"]
        return None

    @property
    def flv_url(self) -> Optional[str]:
        """Return FLV/RTMP stream URL if available in sources, else None."""
        for src in self.sources:
            if "flv" in src.get("type", "").lower() or src.get("src", "").endswith(".flv"):
                return src["src"]
        return None


@dataclass
class Camera:
    """A traffic camera on the INDOT road network."""

    uri: str                          # e.g. "camera/18493"
    title: str                        # e.g. "I-70: 1-070-087-5-1 ARLINGTON AVE"
    bbox: BBox
    active: bool = True
    icon: Optional[str] = None
    color: Optional[str] = None
    views: List[CameraView] = field(default_factory=list)
    last_updated: Optional[str] = None  # ISO timestamp string

    @property
    def camera_id(self) -> str:
        """Extract the numeric camera ID from the URI."""
        return self.uri.split("/")[-1]

    @property
    def image_url(self) -> Optional[str]:
        """Return the URL of the first live snapshot image, or None."""
        for v in self.views:
            if v.is_live:
                return v.url
        return None

    @property
    def coordinates(self) -> Tuple[float, float]:
        """Return (longitude, latitude) of camera location."""
        return self.bbox.center


@dataclass
class GeoFeature:
    """A single GeoJSON feature (point, line, or polygon)."""

    feature_id: str
    geometry: Dict[str, Any]  # GeoJSON geometry object
    properties: Dict[str, Any] = field(default_factory=dict)
    feature_type: str = "Feature"


@dataclass
class TrafficEvent:
    """A traffic incident, construction event, or road closure."""

    uri: str           # e.g. "event/CARSx-404897" or "event/incars-178274"
    title: str
    typename: str      # "Event"
    bbox: BBox
    tooltip: Optional[str] = None
    priority: Optional[int] = None
    # Priority scale: 1 = critical/blocking, 3 = urgent, 5 = routine
    features: List[GeoFeature] = field(default_factory=list)

    @property
    def event_id(self) -> str:
        return self.uri.split("/")[-1]

    @property
    def is_critical(self) -> bool:
        return self.priority is not None and self.priority <= 1

    @property
    def coordinates(self) -> Optional[Tuple[float, float]]:
        for f in self.features:
            geom = f.geometry
            if geom.get("type") == "Point":
                coords = geom.get("coordinates", [])
                if len(coords) >= 2:
                    return (coords[0], coords[1])
        return None


@dataclass
class Plow:
    """A snowplow or AVL-tracked maintenance vehicle."""

    uri: str           # e.g. "avl/64189"
    title: str         # e.g. "US 31: Plow Truck - 64189"
    typename: str      # "Plow"
    bbox: BBox
    tooltip: Optional[str] = None
    plow_type: Optional[str] = None
    active_material_phrase: Optional[str] = None  # e.g. "Applying Salt"
    heading: Optional[float] = None               # degrees (0=N, 90=E, etc.)
    location_description: Optional[str] = None
    views: List[CameraView] = field(default_factory=list)
    last_updated: Optional[str] = None
    features: List[GeoFeature] = field(default_factory=list)

    @property
    def plow_id(self) -> str:
        return self.uri.split("/")[-1]

    @property
    def coordinates(self) -> Tuple[float, float]:
        return self.bbox.center


@dataclass
class Sign:
    """An electronic / dynamic message sign (DMS)."""

    uri: str           # e.g. "electronic-sign/indianasigns*1545"
    title: str         # e.g. "I-465 EB Mile 7.6"
    typename: str      # "Sign"
    bbox: BBox
    tooltip: Optional[str] = None
    sign_display_type: Optional[str] = None
    # e.g. "OVERLAY_TRAVEL_TIME", "TEXT_ONLY", "IMAGE_ONLY"

    @property
    def sign_id(self) -> str:
        return self.uri.split("/")[-1]

    @property
    def coordinates(self) -> Tuple[float, float]:
        return self.bbox.center


@dataclass
class WeatherStation:
    """A Road Weather Information System (RWIS) station."""

    uri: str           # e.g. "weather-station/1"
    title: str         # e.g. "I-64 / 72.0 Birdseye"
    typename: str      # "Station"
    bbox: BBox
    tooltip: Optional[str] = None

    @property
    def station_id(self) -> str:
        return self.uri.split("/")[-1]

    @property
    def coordinates(self) -> Tuple[float, float]:
        return self.bbox.center


@dataclass
class PredefinedArea:
    """A named geographic area (city or region) used for quick navigation."""

    name: str
    bbox: BBox
    sort_order: int = 0
    popular: bool = False


@dataclass
class PredefinedRoute:
    """A named highway route used for quick navigation."""

    name: str
    bbox: BBox
    sort_order: int = 0
    popular: bool = False


@dataclass
class Cluster:
    """A map cluster aggregating multiple nearby features at low zoom levels."""

    uri: str
    title: str           # e.g. "Show 20 cameras"
    bbox: BBox
    max_zoom: Optional[int] = None


# ---------------------------------------------------------------------------
# GraphQL query strings
# ---------------------------------------------------------------------------

_GQL_MAP_FEATURES = """
query MapFeatures($input: MapFeaturesArgs!, $plowType: String) {
    mapFeaturesQuery(input: $input) {
        mapFeatures {
            bbox
            title
            tooltip
            uri
            __typename
            features {
                id
                geometry
                properties
                type
            }
            ... on Cluster {
                maxZoom
            }
            ... on Sign {
                signDisplayType
            }
            ... on Event {
                priority
            }
            ... on Camera {
                active
                views(limit: 5) {
                    uri
                    category
                    __typename
                    ... on CameraView {
                        url
                        sources {
                            type
                            src
                        }
                    }
                }
            }
            ... on Plow {
                views(limit: 3, plowType: $plowType) {
                    uri
                    category
                    __typename
                    ... on PlowCameraView {
                        url
                    }
                }
            }
        }
        error {
            message
            type
        }
    }
}
"""

_GQL_PREDEFINED_AREAS_AND_ROUTES = """
query {
    allPredefinedAreasQuery {
        name
        sortOrder
        popular
        bbox
    }
    allPredefinedRoutesQuery {
        name
        sortOrder
        popular
        bbox
    }
}
"""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class INDOTClient:
    """
    Python client for the INDOT TrafficWise 511in.org API.

    All network calls use the stdlib ``urllib`` only; no third-party packages
    are required.

    Parameters
    ----------
    graphql_url:
        Override the default GraphQL endpoint.  Useful for local testing or
        if INDOT migrates the endpoint.
    timeout:
        HTTP request timeout in seconds (default 30).
    user_agent:
        HTTP User-Agent string to send with each request.

    Examples
    --------
    >>> client = INDOTClient()
    >>> areas = client.get_predefined_areas()
    >>> print(areas[0].name)
    Indianapolis
    """

    def __init__(
        self,
        graphql_url: str = GRAPHQL_URL,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.graphql_url = graphql_url
        self.timeout = timeout
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _post_graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL POST request and return the parsed JSON response.

        Parameters
        ----------
        query:
            GraphQL query or mutation string.
        variables:
            Optional variables dictionary.

        Returns
        -------
        dict
            The ``data`` key of the GraphQL response.

        Raises
        ------
        urllib.error.HTTPError
            For non-2xx HTTP responses.
        ValueError
            If the GraphQL response contains ``errors``.
        """
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.graphql_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://511in.org",
                "Referer": "https://511in.org/",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8")

        result = json.loads(body)

        if "errors" in result:
            messages = "; ".join(e.get("message", str(e)) for e in result["errors"])
            raise ValueError(f"GraphQL error: {messages}")

        return result.get("data", {})

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_bbox(raw: Any) -> BBox:
        """Parse a raw ``[west, south, east, north]`` list into a BBox."""
        if isinstance(raw, list) and len(raw) == 4:
            return BBox.from_list([float(v) for v in raw])
        return BBox(0.0, 0.0, 0.0, 0.0)

    @staticmethod
    def _parse_geo_features(raw_list: Optional[List[Dict]]) -> List[GeoFeature]:
        """Parse a list of raw GeoJSON feature dicts."""
        if not raw_list:
            return []
        result = []
        for f in raw_list:
            result.append(
                GeoFeature(
                    feature_id=str(f.get("id", "")),
                    geometry=f.get("geometry") or {},
                    properties=f.get("properties") or {},
                    feature_type=f.get("type", "Feature"),
                )
            )
        return result

    @staticmethod
    def _parse_camera_views(raw_list: Optional[List[Dict]]) -> List[CameraView]:
        """Parse a list of raw view dicts from the GraphQL Camera type."""
        if not raw_list:
            return []
        result = []
        for v in raw_list:
            result.append(
                CameraView(
                    uri=v.get("uri", ""),
                    category=v.get("category", ""),
                    url=v.get("url", ""),
                    sources=v.get("sources") or [],
                )
            )
        return result

    def _parse_map_feature(self, raw: Dict[str, Any]) -> Any:
        """
        Dispatch a raw mapFeature dict to the appropriate dataclass.

        Returns one of: Camera, TrafficEvent, Plow, Sign, WeatherStation, Cluster,
        or a plain dict for unrecognised types.
        """
        typename = raw.get("__typename", "")
        bbox = self._parse_bbox(raw.get("bbox", [0, 0, 0, 0]))
        uri = raw.get("uri", "")
        title = raw.get("title", "")
        tooltip = raw.get("tooltip")
        features = self._parse_geo_features(raw.get("features"))

        if typename == "Camera":
            return Camera(
                uri=uri,
                title=title,
                bbox=bbox,
                active=raw.get("active", True),
                icon=raw.get("icon"),
                color=raw.get("color"),
                views=self._parse_camera_views(raw.get("views")),
            )
        elif typename == "Event":
            return TrafficEvent(
                uri=uri,
                title=title,
                typename=typename,
                bbox=bbox,
                tooltip=tooltip,
                priority=raw.get("priority"),
                features=features,
            )
        elif typename == "Plow":
            raw_views = raw.get("views") or []
            plow_views = []
            for v in raw_views:
                plow_views.append(
                    CameraView(
                        uri=v.get("uri", ""),
                        category=v.get("category", ""),
                        url=v.get("url", ""),
                    )
                )
            return Plow(
                uri=uri,
                title=title,
                typename=typename,
                bbox=bbox,
                tooltip=tooltip,
                views=plow_views,
                features=features,
            )
        elif typename == "Sign":
            return Sign(
                uri=uri,
                title=title,
                typename=typename,
                bbox=bbox,
                tooltip=tooltip,
                sign_display_type=raw.get("signDisplayType"),
            )
        elif typename == "Station":
            return WeatherStation(
                uri=uri,
                title=title,
                typename=typename,
                bbox=bbox,
                tooltip=tooltip,
            )
        elif typename == "Cluster":
            return Cluster(
                uri=uri,
                title=title,
                bbox=bbox,
                max_zoom=raw.get("maxZoom"),
            )
        else:
            return raw  # Return raw dict for unknown types

    # ------------------------------------------------------------------
    # Public API: map feature queries
    # ------------------------------------------------------------------

    def get_map_features(
        self,
        south: float,
        north: float,
        west: float,
        east: float,
        layer_slugs: List[str],
        zoom: int = 10,
        plow_type: str = LAYER_PLOW_CAMERAS,
    ) -> List[Any]:
        """
        Fetch all map features (cameras, incidents, plows, signs, etc.) within
        a geographic bounding box for the specified layer(s).

        The API processes each layer slug independently and merges results.
        At low zoom levels the API may return Cluster objects instead of
        individual features.

        Parameters
        ----------
        south, north, west, east:
            Bounding box coordinates in decimal degrees.
        layer_slugs:
            One or more layer slug strings (see LAYER_* constants).
        zoom:
            Map zoom level (0–22).  Values below ~9 may return clusters.
        plow_type:
            Layer slug used to select plow-camera view type when plows are
            included.  Defaults to ``LAYER_PLOW_CAMERAS``.

        Returns
        -------
        list
            Mixed list of Camera, TrafficEvent, Plow, Sign, WeatherStation,
            and Cluster objects.

        Examples
        --------
        >>> client = INDOTClient()
        >>> features = client.get_map_features(39.65, 39.95, -86.30, -86.00,
        ...                                    layer_slugs=["normalCameras"], zoom=12)
        """
        all_features: List[Any] = []

        # The application issues one request per layer slug to avoid server-side
        # fan-out timeouts; we replicate that behaviour here.
        for slug in layer_slugs:
            variables = {
                "input": {
                    "north": north,
                    "south": south,
                    "east": east,
                    "west": west,
                    "zoom": zoom,
                    "layerSlugs": [slug],
                },
                "plowType": plow_type,
            }
            data = self._post_graphql(_GQL_MAP_FEATURES, variables)
            raw_features = (
                data.get("mapFeaturesQuery", {}).get("mapFeatures") or []
            )
            for raw in raw_features:
                all_features.append(self._parse_map_feature(raw))

        return all_features

    def get_cameras_in_bounds(
        self,
        south: float,
        north: float,
        west: float,
        east: float,
        zoom: int = 12,
        include_hot: bool = True,
    ) -> List[Camera]:
        """
        Return all Camera objects within the specified bounding box.

        Automatically requests both ``normalCameras`` and (optionally)
        ``hotCameras`` layers and filters the results to Camera instances only,
        skipping any Cluster objects that appear at low zoom levels.

        Parameters
        ----------
        south, north, west, east:
            Bounding box in decimal degrees.
        zoom:
            Map zoom level.  Use >= 12 to avoid clusters.
        include_hot:
            If True (default), also fetch high-priority camera layer.

        Returns
        -------
        list[Camera]

        Examples
        --------
        >>> cameras = client.get_cameras_in_bounds(39.65, 39.95, -86.30, -86.00)
        >>> print(cameras[0].image_url)
        https://public.carsprogram.org/cameras/IN/INDOT_187_...flv.png
        """
        slugs = [LAYER_CAMERAS]
        if include_hot:
            slugs.append(LAYER_HOT_CAMERAS)

        features = self.get_map_features(south, north, west, east, slugs, zoom)
        return [f for f in features if isinstance(f, Camera)]

    def get_cameras_statewide(self, zoom: int = 9) -> List[Any]:
        """
        Return cameras (or clusters) for all of Indiana.

        At zoom=9 the API returns clusters rather than individual cameras.
        Use zoom>=12 over a smaller bounding box to get individual cameras.

        Parameters
        ----------
        zoom:
            Map zoom level.

        Returns
        -------
        list
            Mix of Camera and Cluster objects.
        """
        w, s, e, n = INDIANA_BBOX
        return self.get_cameras_in_bounds(s, n, w, e, zoom=zoom)

    def get_incidents(
        self,
        south: Optional[float] = None,
        north: Optional[float] = None,
        west: Optional[float] = None,
        east: Optional[float] = None,
        zoom: int = 7,
        include_construction: bool = True,
        include_closures: bool = True,
    ) -> List[TrafficEvent]:
        """
        Return active traffic incidents across Indiana (or a sub-region).

        Parameters
        ----------
        south, north, west, east:
            Optional bounding box.  Defaults to the full Indiana extent.
        zoom:
            Map zoom level (lower values return more aggregated results).
        include_construction:
            If True, also fetch construction/roadwork events.
        include_closures:
            If True, also fetch road closure events.

        Returns
        -------
        list[TrafficEvent]
        """
        if south is None:
            w, s, e, n = INDIANA_BBOX
        else:
            s, n, w, e = south, north, west, east  # type: ignore[assignment]

        slugs = [LAYER_INCIDENTS]
        if include_construction:
            slugs.append(LAYER_CONSTRUCTION)
        if include_closures:
            slugs.append(LAYER_CLOSURES)

        features = self.get_map_features(s, n, w, e, slugs, zoom)
        return [f for f in features if isinstance(f, TrafficEvent)]

    def get_construction(
        self,
        south: Optional[float] = None,
        north: Optional[float] = None,
        west: Optional[float] = None,
        east: Optional[float] = None,
        zoom: int = 7,
    ) -> List[TrafficEvent]:
        """
        Return active construction zones across Indiana (or a sub-region).

        Parameters
        ----------
        south, north, west, east:
            Optional bounding box.  Defaults to the full Indiana state extent.
        zoom:
            Map zoom level.

        Returns
        -------
        list[TrafficEvent]
        """
        if south is None:
            w, s, e, n = INDIANA_BBOX
        else:
            s, n, w, e = south, north, west, east  # type: ignore[assignment]

        features = self.get_map_features(s, n, w, e, [LAYER_CONSTRUCTION, LAYER_ROADWORK], zoom)
        return [f for f in features if isinstance(f, TrafficEvent)]

    def get_plows(
        self,
        south: Optional[float] = None,
        north: Optional[float] = None,
        west: Optional[float] = None,
        east: Optional[float] = None,
        zoom: int = 7,
        include_cameras: bool = True,
    ) -> List[Plow]:
        """
        Return active snowplow / maintenance vehicle positions.

        INDOT tracks its snowplow fleet using Automatic Vehicle Location (AVL)
        transponders.  Each Plow object includes GPS coordinates, vehicle ID,
        the road it is on, and optionally a camera image if the vehicle is
        equipped with a plow camera.

        Parameters
        ----------
        south, north, west, east:
            Optional bounding box.  Defaults to all of Indiana.
        zoom:
            Map zoom level.
        include_cameras:
            If True, also request plow-camera imagery layer.

        Returns
        -------
        list[Plow]

        Notes
        -----
        Plow camera images are served from:
        ``https://intg.carsprogram.org/avl_v2/api/images``
        This endpoint is not directly accessible without an internal auth token;
        plow camera URLs come through the GraphQL API views field.
        """
        if south is None:
            w, s, e, n = INDIANA_BBOX
        else:
            s, n, w, e = south, north, west, east  # type: ignore[assignment]

        slugs = [LAYER_PLOW_LOCATIONS]
        if include_cameras:
            slugs.append(LAYER_PLOW_CAMERAS)

        features = self.get_map_features(
            s, n, w, e, [LAYER_PLOW_LOCATIONS], zoom, plow_type=LAYER_PLOW_CAMERAS
        )
        return [f for f in features if isinstance(f, Plow)]

    def get_signs(
        self,
        south: Optional[float] = None,
        north: Optional[float] = None,
        west: Optional[float] = None,
        east: Optional[float] = None,
        zoom: int = 10,
    ) -> List[Sign]:
        """
        Return active electronic / DMS signs and their current messages.

        Parameters
        ----------
        south, north, west, east:
            Optional bounding box.  Defaults to all of Indiana.
        zoom:
            Map zoom level.

        Returns
        -------
        list[Sign]
        """
        if south is None:
            w, s, e, n = INDIANA_BBOX
        else:
            s, n, w, e = south, north, west, east  # type: ignore[assignment]

        features = self.get_map_features(s, n, w, e, [LAYER_SIGNS_ACTIVE], zoom)
        return [f for f in features if isinstance(f, Sign)]

    def get_weather_stations(
        self,
        south: Optional[float] = None,
        north: Optional[float] = None,
        west: Optional[float] = None,
        east: Optional[float] = None,
        zoom: int = 7,
        alerts_only: bool = False,
    ) -> List[WeatherStation]:
        """
        Return RWIS road weather information system stations.

        Parameters
        ----------
        south, north, west, east:
            Optional bounding box.  Defaults to all of Indiana.
        zoom:
            Map zoom level.
        alerts_only:
            If True, only return stations that are in an alert state.

        Returns
        -------
        list[WeatherStation]
        """
        if south is None:
            w, s, e, n = INDIANA_BBOX
        else:
            s, n, w, e = south, north, west, east  # type: ignore[assignment]

        if alerts_only:
            slugs = [LAYER_RWIS_ALERT]
        else:
            slugs = [LAYER_RWIS_NORMAL, LAYER_RWIS_ALERT]

        features = self.get_map_features(s, n, w, e, slugs, zoom)
        return [f for f in features if isinstance(f, WeatherStation)]

    # ------------------------------------------------------------------
    # Public API: reference data queries
    # ------------------------------------------------------------------

    def get_predefined_areas(self) -> List[PredefinedArea]:
        """
        Return the list of named geographic areas used for quick search.

        Returns
        -------
        list[PredefinedArea]
            Sorted by sort_order.  Includes major Indiana cities.

        Examples
        --------
        >>> areas = client.get_predefined_areas()
        >>> [a.name for a in areas]
        ['Indianapolis', 'Gary', 'Fort Wayne', 'Evansville', 'South Bend', 'New Albany']
        """
        data = self._post_graphql(_GQL_PREDEFINED_AREAS_AND_ROUTES)
        raw_areas = data.get("allPredefinedAreasQuery") or []
        result = []
        for a in raw_areas:
            result.append(
                PredefinedArea(
                    name=a["name"],
                    bbox=self._parse_bbox(a.get("bbox", [0, 0, 0, 0])),
                    sort_order=a.get("sortOrder", 0),
                    popular=a.get("popular", False),
                )
            )
        result.sort(key=lambda x: x.sort_order)
        return result

    def get_predefined_routes(self) -> List[PredefinedRoute]:
        """
        Return the list of named highway routes used for quick search.

        Returns
        -------
        list[PredefinedRoute]
            Sorted by sort_order.  Includes all major Indiana interstates and
            US highways.

        Examples
        --------
        >>> routes = client.get_predefined_routes()
        >>> [r.name for r in routes[:5]]
        ['I-65', 'I-69', 'I-70', 'I-74', 'I-80']
        """
        data = self._post_graphql(_GQL_PREDEFINED_AREAS_AND_ROUTES)
        raw_routes = data.get("allPredefinedRoutesQuery") or []
        result = []
        for r in raw_routes:
            result.append(
                PredefinedRoute(
                    name=r["name"],
                    bbox=self._parse_bbox(r.get("bbox", [0, 0, 0, 0])),
                    sort_order=r.get("sortOrder", 0),
                    popular=r.get("popular", False),
                )
            )
        result.sort(key=lambda x: x.sort_order)
        return result

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_cameras_for_area(self, area_name: str, zoom: int = 12) -> List[Camera]:
        """
        Fetch cameras within a named predefined area (e.g. "Indianapolis").

        Performs a look-up of the area bounding box and then calls
        ``get_cameras_in_bounds``.

        Parameters
        ----------
        area_name:
            Case-insensitive area name (e.g. "indianapolis", "Fort Wayne").
        zoom:
            Map zoom level for the camera query.

        Returns
        -------
        list[Camera]

        Raises
        ------
        ValueError
            If no predefined area with that name is found.
        """
        areas = self.get_predefined_areas()
        match = next(
            (a for a in areas if a.name.lower() == area_name.lower()), None
        )
        if match is None:
            available = [a.name for a in areas]
            raise ValueError(
                f"Area '{area_name}' not found.  Available areas: {available}"
            )
        bbox = match.bbox
        return self.get_cameras_in_bounds(
            bbox.south, bbox.north, bbox.west, bbox.east, zoom=zoom
        )

    def get_cameras_for_route(
        self, route_name: str, zoom: int = 9
    ) -> List[Any]:
        """
        Fetch cameras (or clusters) along a named highway route.

        Parameters
        ----------
        route_name:
            Route name exactly as returned by ``get_predefined_routes()``,
            e.g. "I-65", "I-70", "US-31".
        zoom:
            Map zoom level.  Use >= 12 for individual cameras; lower values
            return Cluster aggregates.

        Returns
        -------
        list
            Mix of Camera and Cluster objects.

        Raises
        ------
        ValueError
            If no predefined route with that name is found.
        """
        routes = self.get_predefined_routes()
        match = next(
            (r for r in routes if r.name.lower() == route_name.lower()), None
        )
        if match is None:
            available = [r.name for r in routes]
            raise ValueError(
                f"Route '{route_name}' not found.  Available routes: {available}"
            )
        bbox = match.bbox
        return self.get_cameras_in_bounds(
            bbox.south, bbox.north, bbox.west, bbox.east, zoom=zoom
        )

    def download_camera_image(self, camera: Camera) -> Optional[bytes]:
        """
        Download the current snapshot image for a camera.

        Parameters
        ----------
        camera:
            A Camera object from any of the get_cameras_* methods.

        Returns
        -------
        bytes or None
            Raw PNG/JPEG image bytes, or None if no live image URL is available.

        Examples
        --------
        >>> cameras = client.get_cameras_in_bounds(39.65, 39.95, -86.30, -86.00)
        >>> img = client.download_camera_image(cameras[0])
        >>> with open("camera.png", "wb") as f:
        ...     f.write(img)
        """
        url = camera.image_url
        if url is None:
            return None
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.URLError:
            return None


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    """
    Command-line demonstration of the INDOT TrafficWise client.

    Prints a summary of statewide and Indianapolis-area traffic data
    to standard output.
    """
    client = INDOTClient()

    # ---------------------------------------------------------------
    # 1. Named areas and routes
    # ---------------------------------------------------------------
    _print_section("Predefined Areas")
    try:
        areas = client.get_predefined_areas()
        for a in areas:
            lon, lat = a.bbox.center
            print(f"  {a.name:20s} center=({lon:.4f}, {lat:.4f})")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    _print_section("Predefined Routes (first 10)")
    try:
        routes = client.get_predefined_routes()
        for r in routes[:10]:
            print(f"  {r.name:15s} bbox=W:{r.bbox.west:.3f} S:{r.bbox.south:.3f} "
                  f"E:{r.bbox.east:.3f} N:{r.bbox.north:.3f}")
        print(f"  ... and {max(0, len(routes)-10)} more routes")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # ---------------------------------------------------------------
    # 2. Statewide incidents
    # ---------------------------------------------------------------
    _print_section("Active Incidents (statewide)")
    try:
        incidents = client.get_incidents()
        if not incidents:
            print("  No active incidents.")
        for inc in incidents[:10]:
            coords = inc.coordinates
            coord_str = f"({coords[0]:.4f}, {coords[1]:.4f})" if coords else "n/a"
            pri = inc.priority or "?"
            print(f"  [P{pri}] {inc.title}")
            print(f"         {inc.uri}  coords={coord_str}")
        if len(incidents) > 10:
            print(f"  ... and {len(incidents)-10} more incidents")
        print(f"\n  Total: {len(incidents)} incidents")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # ---------------------------------------------------------------
    # 3. Active construction
    # ---------------------------------------------------------------
    _print_section("Active Construction (statewide)")
    try:
        construction = client.get_construction()
        if not construction:
            print("  No active construction events.")
        for ev in construction[:5]:
            print(f"  {ev.title}")
            print(f"    {ev.uri}")
        if len(construction) > 5:
            print(f"  ... and {len(construction)-5} more")
        print(f"\n  Total: {len(construction)} construction events")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # ---------------------------------------------------------------
    # 4. Cameras — Indianapolis area
    # ---------------------------------------------------------------
    _print_section("Traffic Cameras — Indianapolis Area (zoom=9)")
    try:
        # Indianapolis area bounding box
        cameras = client.get_cameras_in_bounds(
            south=39.59878, north=40.02495,
            west=-86.47613, east=-85.83893,
            zoom=9,
        )
        cam_count = sum(1 for c in cameras if isinstance(c, Camera))
        cluster_count = sum(1 for c in cameras if isinstance(c, Cluster))
        print(f"  Retrieved {cam_count} individual cameras and {cluster_count} clusters")

        real_cams = [c for c in cameras if isinstance(c, Camera)]
        for cam in real_cams[:5]:
            lon, lat = cam.coordinates
            print(f"\n  Camera: {cam.title}")
            print(f"    URI:    {cam.uri}  active={cam.active}")
            print(f"    Coords: ({lon:.5f}, {lat:.5f})")
            if cam.image_url:
                print(f"    Image:  {cam.image_url}")
            for v in cam.views:
                if v.hls_url:
                    print(f"    HLS:    {v.hls_url}")

        clusters = [c for c in cameras if isinstance(c, Cluster)]
        if clusters:
            print("\n  Clusters (zoom in to expand):")
            for cl in clusters[:5]:
                print(f"    {cl.title}  uri={cl.uri}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # ---------------------------------------------------------------
    # 5. Snowplow tracking
    # ---------------------------------------------------------------
    _print_section("Snowplow / AVL Vehicle Tracking (statewide)")
    try:
        plows = client.get_plows()
        if not plows:
            print("  No active plows tracked (may be off-season).")
        else:
            for p in plows[:5]:
                lon, lat = p.coordinates
                material = p.active_material_phrase or "n/a"
                print(f"  {p.title}")
                print(f"    URI:      {p.uri}")
                print(f"    Coords:   ({lon:.5f}, {lat:.5f})")
                print(f"    Material: {material}")
                if p.views:
                    print(f"    Cam URL:  {p.views[0].url}")
            if len(plows) > 5:
                print(f"  ... and {len(plows)-5} more plows")
            print(f"\n  Total: {len(plows)} plows tracked")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # ---------------------------------------------------------------
    # 6. Electronic signs
    # ---------------------------------------------------------------
    _print_section("Electronic Signs — Indianapolis Area")
    try:
        signs = client.get_signs(
            south=39.59878, north=40.02495,
            west=-86.47613, east=-85.83893,
            zoom=10,
        )
        if not signs:
            print("  No active signs found.")
        for s in signs[:5]:
            lon, lat = s.coordinates
            print(f"  {s.title}")
            print(f"    URI:  {s.uri}")
            print(f"    Type: {s.sign_display_type}  coords=({lon:.5f}, {lat:.5f})")
        print(f"\n  Total: {len(signs)} signs")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # ---------------------------------------------------------------
    # 7. RWIS weather stations
    # ---------------------------------------------------------------
    _print_section("RWIS Road Weather Stations (statewide)")
    try:
        stations = client.get_weather_stations()
        if not stations:
            print("  No RWIS stations found.")
        for s in stations[:5]:
            lon, lat = s.coordinates
            print(f"  {s.title}  ({lon:.4f}, {lat:.4f})")
        print(f"\n  Total: {len(stations)} weather stations")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n" + "=" * 60)
    print("  Demo complete.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
