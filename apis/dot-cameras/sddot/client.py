"""
SDDOT Traffic Camera Client
============================
Python client for the South Dakota Department of Transportation (SDDOT)
traffic camera and road conditions system at https://www.sd511.org

API infrastructure: Iteris ATIS (Advanced Traffic Information System)
CDN base: https://sd.cdn.iteris-atis.com/
Aggregator: https://aggregator.iteris-atis.com/

No authentication required for read-only public data.
Uses Python stdlib only (urllib, json, dataclasses).

Reverse-engineered from sd511.org JavaScript bundles and network traffic.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_CDN_URL = "https://sd.cdn.iteris-atis.com/"
AGGREGATOR_BASE = "https://aggregator.iteris-atis.com"
NEWS_AGGREGATOR = "https://aggregator.iteris-sd511.net"

GEOJSON_ENDPOINTS: Dict[str, str] = {
    "cameras":        BASE_CDN_URL + "geojson/icons/metadata/icons.cameras.geojson",
    "rwis":           BASE_CDN_URL + "geojson/icons/metadata/icons.rwis.geojson",
    "road_work":      BASE_CDN_URL + "geojson/icons/metadata/icons.road-work.geojson",
    "incidents":      BASE_CDN_URL + "geojson/icons/metadata/icons.incidents-accidents.geojson",
    "restrictions":   BASE_CDN_URL + "geojson/icons/metadata/icons.restriction.geojson",
    "disturbances":   BASE_CDN_URL + "geojson/icons/metadata/icons.disturbances.geojson",
    "disasters":      BASE_CDN_URL + "geojson/icons/metadata/icons.disasters.geojson",
    "obstructions":   BASE_CDN_URL + "geojson/icons/metadata/icons.obstructions.geojson",
    "scheduled_events": BASE_CDN_URL + "geojson/icons/metadata/icons.scheduled-events.geojson",
    "jurisdictions":  BASE_CDN_URL + "geojson/icons/metadata/active_jurisdictions.geojson",
}

LAYER_ENDPOINTS: Dict[str, str] = {
    "rest_areas":        AGGREGATOR_BASE + "/aggregator/services/layers/group/sddot/current/?layer_type=rest_area",
    "ports_of_entry":    AGGREGATOR_BASE + "/aggregator/services/layers/group/sddot/current/?layer_type=Weight%20Stations%2FPorts%20of%20Entry",
    "neighboring_511":   AGGREGATOR_BASE + "/aggregator/services/layers/group/sddot/current/?layer_type=neighboring_state_511",
    "elements":          AGGREGATOR_BASE + "/aggregator/services/elements/group/sddot/current/",
    "news":              NEWS_AGGREGATOR  + "/aggregator/services/news/group/sddot/current/",
}

# Camera image URL template:  BASE_CDN_URL + "camera_images/{location_id}/{camera_id}/latest.jpg"
CAMERA_IMAGE_URL = BASE_CDN_URL + "camera_images/{location_id}/{camera_id}/latest.jpg"

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sd511.org/",
    "Accept": "application/json, text/plain, */*",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CameraView:
    """A single camera view (one physical camera lens/direction)."""
    id: str
    name: str
    description: str
    image_url: str
    update_time: int  # Unix timestamp

    @property
    def update_dt(self) -> str:
        """Return ISO-8601 formatted update time."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.update_time))


@dataclass
class CameraLocation:
    """
    A camera location (physical installation site) that may host
    one or more individual camera views (lenses).
    """
    id: str                    # e.g. "CSDATY"
    name: str                  # e.g. "Watertown North"
    route: str                 # e.g. "I-29"
    mile_marker: str           # e.g. "179"
    longitude: float
    latitude: float
    cameras: List[CameraView] = field(default_factory=list)

    @property
    def coordinates(self) -> Tuple[float, float]:
        return (self.longitude, self.latitude)

    def get_image_url(self, camera_index: int = 0) -> Optional[str]:
        """Return the image URL for a given camera view index."""
        if camera_index < len(self.cameras):
            return self.cameras[camera_index].image_url
        return None


@dataclass
class AtmosphericReading:
    """Weather observation from a RWIS station."""
    observation_time: int          # Unix timestamp
    air_temperature: Optional[float]     # Deg F
    dewpoint_temperature: Optional[float]
    relative_humidity: Optional[float]   # Percent
    wind_speed: Optional[float]          # MPH
    wind_gust: Optional[float]           # MPH
    wind_direction: Optional[str]        # Compass (e.g. "NW")
    precip_rate: Optional[float]         # inches/hour
    precip_accumulated: Optional[float]  # inches
    precip_type: Optional[str]
    precip_intensity: Optional[str]


@dataclass
class SurfaceReading:
    """Road surface observation from a RWIS station."""
    observation_time: int
    elevation: Optional[float]           # Feet
    surface_temperature: Optional[float] # Deg F
    surface_condition: Optional[str]
    friction: Optional[float]


@dataclass
class RWISStation:
    """
    Road Weather Information System (RWIS) station with atmospheric
    and road surface sensor data.  These stations also have cameras.
    """
    id: str                    # e.g. "CSD3FK"
    name: str                  # e.g. "Three Forks"
    description: str           # Route description, e.g. "US-16"
    mile_marker: str
    longitude: float
    latitude: float
    cameras: List[CameraView] = field(default_factory=list)
    atmos: List[AtmosphericReading] = field(default_factory=list)
    surface: List[SurfaceReading] = field(default_factory=list)

    @property
    def latest_atmos(self) -> Optional[AtmosphericReading]:
        return self.atmos[0] if self.atmos else None

    @property
    def latest_surface(self) -> Optional[SurfaceReading]:
        return self.surface[0] if self.surface else None


@dataclass
class TrafficEvent:
    """
    A traffic event: road work, restriction, incident, disturbance, etc.
    """
    id: str
    event_id: str
    event_type: str            # "road_work", "restriction", "incident", etc.
    route: str
    direction: str
    headline: str
    location_description: str
    report: str
    mile_marker: str
    start_time: int            # Unix timestamp
    end_time: Optional[int]    # Unix timestamp; None if open-ended
    longitude: float
    latitude: float
    url: Optional[str] = None
    label: Optional[str] = None


@dataclass
class RestArea:
    """A South Dakota highway rest area."""
    id: str
    title: str
    description: str
    route: str
    direction: str
    mile_marker: str
    status: str               # "open" / "closed"
    longitude: float
    latitude: float
    amenities: List[str] = field(default_factory=list)
    image_url: Optional[str] = None
    seasonal: Optional[str] = None


@dataclass
class NewsAlert:
    """A travel alert or announcement from the SDDOT news aggregator."""
    category: str              # "travel_alerts", "high_priority", etc.
    title: Optional[str]
    message: Optional[str]
    url: Optional[str]
    position: Optional[int]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 20) -> Any:
    """
    Perform an HTTP GET request and return parsed JSON.

    Parameters
    ----------
    url : str
        Full URL to fetch.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    Parsed JSON (dict or list).

    Raises
    ------
    urllib.error.HTTPError
        On non-200 HTTP responses.
    urllib.error.URLError
        On network/connection errors.
    json.JSONDecodeError
        If the response body is not valid JSON.
    """
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw)


def _fetch_geojson(endpoint_key: str, timeout: int = 20) -> List[Dict]:
    """
    Fetch a GeoJSON endpoint and return the list of features.

    Parameters
    ----------
    endpoint_key : str
        One of the keys in GEOJSON_ENDPOINTS.
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    list of GeoJSON feature dicts.
    """
    url = GEOJSON_ENDPOINTS[endpoint_key]
    data = _fetch_json(url, timeout=timeout)
    return data.get("features", [])


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_camera_view(raw: Dict) -> CameraView:
    return CameraView(
        id=str(raw.get("id", "")),
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        image_url=raw.get("image", ""),
        update_time=int(raw.get("updateTime") or 0),
    )


def _parse_camera_location(feature: Dict) -> CameraLocation:
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [0.0, 0.0])
    cameras = [_parse_camera_view(c) for c in props.get("cameras", [])]
    return CameraLocation(
        id=str(feature.get("id", "")),
        name=props.get("name", ""),
        route=props.get("route", ""),
        mile_marker=str(props.get("mrm", "")),
        longitude=float(coords[0]),
        latitude=float(coords[1]),
        cameras=cameras,
    )


def _parse_atmos(raw: Dict) -> AtmosphericReading:
    def _val(d: Dict) -> Any:
        return d.get("value") if isinstance(d, dict) else None

    obs_raw = raw.get("observation_time", {})
    obs_time = int(_val(obs_raw) or 0)

    return AtmosphericReading(
        observation_time=obs_time,
        air_temperature=_val(raw.get("air_temperature", {})),
        dewpoint_temperature=_val(raw.get("dewpoint_temperature", {})),
        relative_humidity=_val(raw.get("relative_humidity", {})),
        wind_speed=_val(raw.get("wind_speed", {})),
        wind_gust=_val(raw.get("wind_gust", {})),
        wind_direction=_val(raw.get("wind_direction", {})),
        precip_rate=_val(raw.get("precip_rate", {})),
        precip_accumulated=_val(raw.get("precip_accumulated", {})),
        precip_type=_val(raw.get("precip_type", {})),
        precip_intensity=_val(raw.get("precip_intensity", {})),
    )


def _parse_surface(raw: Dict) -> SurfaceReading:
    def _val(d: Dict) -> Any:
        return d.get("value") if isinstance(d, dict) else None

    obs_raw = raw.get("observation_time", {})
    obs_time = int(_val(obs_raw) or 0)

    elev = _val(raw.get("elevation", {}))
    return SurfaceReading(
        observation_time=obs_time,
        elevation=float(elev) if elev is not None else None,
        surface_temperature=_val(raw.get("surface_temperature", {})),
        surface_condition=_val(raw.get("surface_condition", {})),
        friction=_val(raw.get("friction", {})),
    )


def _parse_rwis_station(feature: Dict) -> RWISStation:
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [0.0, 0.0])
    cameras = [_parse_camera_view(c) for c in props.get("cameras", [])]
    atmos = [_parse_atmos(a) for a in props.get("atmos", [])]
    surface = [_parse_surface(s) for s in props.get("surface", [])]
    return RWISStation(
        id=str(feature.get("id", "")),
        name=props.get("name", ""),
        description=props.get("description", ""),
        mile_marker=str(props.get("mrm", "")),
        longitude=float(coords[0]),
        latitude=float(coords[1]),
        cameras=cameras,
        atmos=atmos,
        surface=surface,
    )


def _parse_traffic_event(feature: Dict, event_type: str) -> TrafficEvent:
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [0.0, 0.0])
    end_raw = props.get("end_time")
    return TrafficEvent(
        id=str(feature.get("id", "")),
        event_id=str(props.get("event_id", "")),
        event_type=event_type,
        route=props.get("route", ""),
        direction=props.get("dir", ""),
        headline=props.get("headline", ""),
        location_description=props.get("location_description", ""),
        report=props.get("report", ""),
        mile_marker=str(props.get("mrm", "")),
        start_time=int(props.get("start_time") or 0),
        end_time=int(end_raw) if end_raw else None,
        longitude=float(coords[0]),
        latitude=float(coords[1]),
        url=props.get("url"),
        label=props.get("label"),
    )


def _parse_rest_area(feature: Dict) -> RestArea:
    props = feature.get("properties", {})
    coords = feature.get("geometry", {}).get("coordinates", [0.0, 0.0])
    return RestArea(
        id=str(feature.get("id", "")),
        title=props.get("title", ""),
        description=props.get("description", ""),
        route=props.get("route", ""),
        direction=props.get("dir", ""),
        mile_marker=str(props.get("mrm", "")),
        status=props.get("status", "unknown"),
        longitude=float(coords[0]),
        latitude=float(coords[1]),
        amenities=props.get("amenities", []),
        image_url=props.get("image_url"),
        seasonal=props.get("seasonal"),
    )


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class SDDOTClient:
    """
    Client for the South Dakota Department of Transportation traffic
    information system (sd511.org).

    All methods make live HTTP requests to the public CDN and aggregator
    endpoints.  No authentication is required.

    Example
    -------
    >>> client = SDDOTClient()
    >>> cameras = client.get_cameras()
    >>> print(f"{len(cameras)} camera locations found")
    >>> for loc in cameras[:3]:
    ...     print(loc.name, loc.route, "—", len(loc.cameras), "views")
    ...     print("  Image:", loc.get_image_url())
    """

    def __init__(self, timeout: int = 20):
        """
        Parameters
        ----------
        timeout : int
            Default HTTP request timeout in seconds.
        """
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(self) -> List[CameraLocation]:
        """
        Return all CCTV camera locations across South Dakota highways.

        Each location may host multiple individual camera views (lenses),
        each with its own still image URL.

        Returns
        -------
        list of CameraLocation
        """
        features = _fetch_geojson("cameras", timeout=self.timeout)
        return [_parse_camera_location(f) for f in features]

    def get_camera_image_url(self, location_id: str, camera_id: str) -> str:
        """
        Build the direct URL for a camera still image.

        The image is a JPEG hosted on the Iteris CDN and refreshes
        automatically every few minutes.

        Parameters
        ----------
        location_id : str
            The location ID (e.g. "CSDATY").
        camera_id : str
            The camera view ID within that location (e.g. "0", "1").

        Returns
        -------
        str : direct image URL
        """
        return CAMERA_IMAGE_URL.format(
            location_id=location_id,
            camera_id=camera_id,
        )

    def download_camera_image(
        self,
        location_id: str,
        camera_id: str,
        save_path: str,
    ) -> str:
        """
        Download the latest still image for a specific camera view.

        Parameters
        ----------
        location_id : str
            The location ID (e.g. "CSDATY").
        camera_id : str
            The camera view ID (e.g. "0").
        save_path : str
            Local filesystem path where the JPEG will be written.

        Returns
        -------
        str : the save_path used.
        """
        url = self.get_camera_image_url(location_id, camera_id)
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = resp.read()
        with open(save_path, "wb") as fh:
            fh.write(data)
        return save_path

    # ------------------------------------------------------------------
    # RWIS (Road Weather Information System)
    # ------------------------------------------------------------------

    def get_rwis_stations(self) -> List[RWISStation]:
        """
        Return all RWIS weather stations with current atmospheric
        and road-surface sensor readings plus any attached cameras.

        Returns
        -------
        list of RWISStation
        """
        features = _fetch_geojson("rwis", timeout=self.timeout)
        return [_parse_rwis_station(f) for f in features]

    # ------------------------------------------------------------------
    # Traffic Events
    # ------------------------------------------------------------------

    def get_road_work(self) -> List[TrafficEvent]:
        """
        Return all active road construction / maintenance events.

        Returns
        -------
        list of TrafficEvent  (event_type == "road_work")
        """
        features = _fetch_geojson("road_work", timeout=self.timeout)
        return [_parse_traffic_event(f, "road_work") for f in features]

    def get_incidents(self) -> List[TrafficEvent]:
        """
        Return active traffic incidents (crashes, stalled vehicles, etc.).

        Returns
        -------
        list of TrafficEvent  (event_type == "incident")
        """
        features = _fetch_geojson("incidents", timeout=self.timeout)
        return [_parse_traffic_event(f, "incident") for f in features]

    def get_restrictions(self) -> List[TrafficEvent]:
        """
        Return active travel restrictions (weight limits, width limits, etc.).

        Returns
        -------
        list of TrafficEvent  (event_type == "restriction")
        """
        features = _fetch_geojson("restrictions", timeout=self.timeout)
        return [_parse_traffic_event(f, "restriction") for f in features]

    def get_disturbances(self) -> List[TrafficEvent]:
        """
        Return active road disturbances.

        Returns
        -------
        list of TrafficEvent  (event_type == "disturbance")
        """
        features = _fetch_geojson("disturbances", timeout=self.timeout)
        return [_parse_traffic_event(f, "disturbance") for f in features]

    def get_disasters(self) -> List[TrafficEvent]:
        """
        Return active disaster-related events (flooding, fires near roads, etc.).

        Returns
        -------
        list of TrafficEvent  (event_type == "disaster")
        """
        features = _fetch_geojson("disasters", timeout=self.timeout)
        return [_parse_traffic_event(f, "disaster") for f in features]

    def get_obstructions(self) -> List[TrafficEvent]:
        """
        Return active roadway obstructions.

        Returns
        -------
        list of TrafficEvent  (event_type == "obstruction")
        """
        features = _fetch_geojson("obstructions", timeout=self.timeout)
        return [_parse_traffic_event(f, "obstruction") for f in features]

    def get_scheduled_events(self) -> List[TrafficEvent]:
        """
        Return upcoming scheduled events that may affect traffic.

        Returns
        -------
        list of TrafficEvent  (event_type == "scheduled_event")
        """
        features = _fetch_geojson("scheduled_events", timeout=self.timeout)
        return [_parse_traffic_event(f, "scheduled_event") for f in features]

    def get_all_events(self) -> List[TrafficEvent]:
        """
        Return all traffic events across every event category.

        Returns
        -------
        list of TrafficEvent (mixed event_type values)
        """
        events: List[TrafficEvent] = []
        event_map = {
            "road_work":      "road_work",
            "incidents":      "incident",
            "restrictions":   "restriction",
            "disturbances":   "disturbance",
            "disasters":      "disaster",
            "obstructions":   "obstruction",
            "scheduled_events": "scheduled_event",
        }
        for key, etype in event_map.items():
            try:
                features = _fetch_geojson(key, timeout=self.timeout)
                events.extend(_parse_traffic_event(f, etype) for f in features)
            except Exception:
                pass
        return events

    # ------------------------------------------------------------------
    # Rest Areas
    # ------------------------------------------------------------------

    def get_rest_areas(self) -> List[RestArea]:
        """
        Return all South Dakota highway rest areas with status and amenities.

        Returns
        -------
        list of RestArea
        """
        url = LAYER_ENDPOINTS["rest_areas"]
        data = _fetch_json(url, timeout=self.timeout)
        features = data.get("features", [])
        return [_parse_rest_area(f) for f in features]

    # ------------------------------------------------------------------
    # Ports of Entry / Weigh Stations
    # ------------------------------------------------------------------

    def get_ports_of_entry(self) -> List[Dict]:
        """
        Return raw GeoJSON features for weigh stations / ports of entry.

        Returns
        -------
        list of raw feature dicts (use .get("properties") for data)
        """
        url = LAYER_ENDPOINTS["ports_of_entry"]
        data = _fetch_json(url, timeout=self.timeout)
        return data.get("features", [])

    # ------------------------------------------------------------------
    # Travel Alerts / News
    # ------------------------------------------------------------------

    def get_news_alerts(self) -> Dict[str, List[NewsAlert]]:
        """
        Return current SDDOT travel alerts grouped by category.

        Categories in the response dict:
          - "general_information"
          - "travel_alerts"
          - "high_priority"
          - "special_events"

        Returns
        -------
        dict mapping category name to list of NewsAlert objects.
        """
        url = LAYER_ENDPOINTS["news"]
        data = _fetch_json(url, timeout=self.timeout)
        result: Dict[str, List[NewsAlert]] = {}

        for category, items in data.items():
            if not isinstance(items, list):
                continue
            alerts: List[NewsAlert] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                alerts.append(NewsAlert(
                    category=category,
                    title=item.get("title") or item.get("header"),
                    message=item.get("message"),
                    url=item.get("url"),
                    position=item.get("position"),
                ))
            result[category] = alerts

        return result

    # ------------------------------------------------------------------
    # Site Elements / Links (dashboard content)
    # ------------------------------------------------------------------

    def get_site_elements(self) -> List[Dict]:
        """
        Return raw site elements / dashboard link content from the
        ATIS aggregator.  These are informational cards shown on the
        sd511.org sidebar (employment links, SDDOT resources, etc.).

        Returns
        -------
        list of raw element dicts
        """
        url = LAYER_ENDPOINTS["elements"]
        data = _fetch_json(url, timeout=self.timeout)
        if isinstance(data, list):
            return data
        return []

    # ------------------------------------------------------------------
    # Convenience / Filtering helpers
    # ------------------------------------------------------------------

    def filter_cameras_by_route(
        self, cameras: List[CameraLocation], route: str
    ) -> List[CameraLocation]:
        """
        Filter camera locations to those on a specific route.

        Parameters
        ----------
        cameras : list of CameraLocation
        route : str
            Route name to filter by (e.g. "I-90", "US-14", "SD-79").
            Matching is case-insensitive.

        Returns
        -------
        list of CameraLocation
        """
        route_upper = route.upper()
        return [c for c in cameras if c.route.upper() == route_upper]

    def filter_events_by_route(
        self, events: List[TrafficEvent], route: str
    ) -> List[TrafficEvent]:
        """
        Filter traffic events to those on a specific route.

        Parameters
        ----------
        events : list of TrafficEvent
        route : str
            Route name (e.g. "I-29").

        Returns
        -------
        list of TrafficEvent
        """
        route_upper = route.upper()
        return [e for e in events if e.route.upper() == route_upper]

    def get_nearest_cameras(
        self,
        lat: float,
        lon: float,
        cameras: Optional[List[CameraLocation]] = None,
        limit: int = 5,
    ) -> List[Tuple[float, CameraLocation]]:
        """
        Return the nearest camera locations to a given coordinate,
        sorted by distance (ascending).

        Parameters
        ----------
        lat : float
            Latitude (decimal degrees).
        lon : float
            Longitude (decimal degrees).
        cameras : list of CameraLocation, optional
            Pre-fetched camera list.  If None, fetches fresh data.
        limit : int
            Maximum number of results to return.

        Returns
        -------
        list of (distance_km, CameraLocation) tuples
        """
        if cameras is None:
            cameras = self.get_cameras()

        def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            import math
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(math.radians(lat1))
                * math.cos(math.radians(lat2))
                * math.sin(dlon / 2) ** 2
            )
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        scored = [
            (_haversine(lat, lon, c.latitude, c.longitude), c)
            for c in cameras
        ]
        scored.sort(key=lambda x: x[0])
        return scored[:limit]

    def get_route_summary(
        self, route: str
    ) -> Dict[str, Any]:
        """
        Return a summary of cameras and active events for a given route.

        Parameters
        ----------
        route : str
            Route identifier (e.g. "I-90", "US-83").

        Returns
        -------
        dict with keys: "route", "cameras", "road_work", "restrictions",
                        "incidents", "disasters"
        """
        all_cams = self.get_cameras()
        all_events = self.get_all_events()

        return {
            "route": route,
            "cameras": self.filter_cameras_by_route(all_cams, route),
            "road_work": [
                e for e in all_events
                if e.route.upper() == route.upper()
                and e.event_type == "road_work"
            ],
            "restrictions": [
                e for e in all_events
                if e.route.upper() == route.upper()
                and e.event_type == "restriction"
            ],
            "incidents": [
                e for e in all_events
                if e.route.upper() == route.upper()
                and e.event_type == "incident"
            ],
            "disasters": [
                e for e in all_events
                if e.route.upper() == route.upper()
                and e.event_type == "disaster"
            ],
        }


# ---------------------------------------------------------------------------
# CLI / Demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    """
    Quick demonstration of the client capabilities.
    Run with:  python sddot_client.py
    """
    client = SDDOTClient(timeout=20)

    print("=" * 65)
    print("SDDOT Traffic Camera Client — Live Data Demo")
    print("=" * 65)

    # --- Cameras ---
    print("\n[1] CCTV Camera Locations")
    print("-" * 40)
    cameras = client.get_cameras()
    print(f"  Total locations: {len(cameras)}")
    total_views = sum(len(c.cameras) for c in cameras)
    print(f"  Total individual camera views: {total_views}")

    for loc in cameras[:3]:
        print(f"\n  {loc.id} — {loc.name} ({loc.route} @ MM {loc.mile_marker})")
        print(f"    Coordinates: {loc.latitude:.5f}, {loc.longitude:.5f}")
        for view in loc.cameras:
            ts = view.update_dt
            print(f"    [{view.id}] {view.name}")
            print(f"          Image: {view.image_url}")
            print(f"          Updated: {ts}")

    # --- Route filter ---
    print("\n[2] I-90 Cameras")
    print("-" * 40)
    i90_cams = client.filter_cameras_by_route(cameras, "I-90")
    print(f"  {len(i90_cams)} locations on I-90")
    for loc in i90_cams[:2]:
        print(f"  • {loc.name} @ MM {loc.mile_marker} — {len(loc.cameras)} view(s)")

    # --- Nearest cameras ---
    print("\n[3] Cameras nearest to Rapid City, SD (44.08, -103.23)")
    print("-" * 40)
    nearest = client.get_nearest_cameras(44.08, -103.23, cameras=cameras, limit=3)
    for dist, loc in nearest:
        print(f"  {loc.name} ({loc.route}) — {dist:.1f} km away")

    # --- Road Work ---
    print("\n[4] Road Work Events")
    print("-" * 40)
    road_work = client.get_road_work()
    print(f"  Active road work events: {len(road_work)}")
    for evt in road_work[:3]:
        ts = time.strftime("%Y-%m-%d", time.gmtime(evt.start_time))
        print(f"  [{evt.route}] {evt.headline}")
        print(f"    {evt.location_description}")
        print(f"    Since: {ts}")

    # --- Restrictions ---
    print("\n[5] Travel Restrictions")
    print("-" * 40)
    restrictions = client.get_restrictions()
    print(f"  Active restrictions: {len(restrictions)}")
    for r in restrictions[:2]:
        print(f"  [{r.route}] {r.headline}")
        print(f"    {r.location_description}")

    # --- Disasters ---
    print("\n[6] Disaster Events")
    print("-" * 40)
    disasters = client.get_disasters()
    print(f"  Active disaster events: {len(disasters)}")
    for d in disasters[:2]:
        print(f"  [{d.route}] {d.headline}")

    # --- RWIS Stations ---
    print("\n[7] RWIS Road Weather Stations")
    print("-" * 40)
    rwis = client.get_rwis_stations()
    print(f"  Total RWIS stations: {len(rwis)}")
    for st in rwis[:2]:
        print(f"\n  {st.id} — {st.name} ({st.description} @ MM {st.mile_marker})")
        atm = st.latest_atmos
        surf = st.latest_surface
        if atm:
            print(f"    Air temp: {atm.air_temperature} °F")
            print(f"    Wind: {atm.wind_speed} mph {atm.wind_direction}, "
                  f"gust {atm.wind_gust} mph")
            print(f"    Humidity: {atm.relative_humidity}%")
            print(f"    Precip type: {atm.precip_type}, "
                  f"intensity: {atm.precip_intensity}")
        if surf:
            print(f"    Road surface temp: {surf.surface_temperature} °F")
            print(f"    Surface condition: {surf.surface_condition}")
        if st.cameras:
            print(f"    Cameras: {len(st.cameras)}")
            print(f"    First image: {st.cameras[0].image_url}")

    # --- Rest Areas ---
    print("\n[8] Rest Areas")
    print("-" * 40)
    rest_areas = client.get_rest_areas()
    print(f"  Total rest areas: {len(rest_areas)}")
    for ra in rest_areas[:3]:
        print(f"  {ra.title} ({ra.route} {ra.direction}) — {ra.status}")
        if ra.amenities:
            print(f"    Amenities: {', '.join(ra.amenities)}")

    # --- Travel Alerts ---
    print("\n[9] Travel News / Alerts")
    print("-" * 40)
    alerts = client.get_news_alerts()
    for cat, items in alerts.items():
        if items:
            print(f"  {cat}: {len(items)} item(s)")
            for a in items[:1]:
                print(f"    Title: {a.title}")
        else:
            print(f"  {cat}: (empty)")

    print("\n" + "=" * 65)
    print("Demo complete.")
    print("=" * 65)


if __name__ == "__main__":
    _demo()
