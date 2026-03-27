"""
ALDOT / ALGO Traffic API Client
================================
Reverse-engineered Python client for the Alabama Department of Transportation
(ALDOT) traffic camera and travel information system, served via algotraffic.com.

API Base: https://api.algotraffic.com
Versions: v3.0 (legacy), v4.0 (current, recommended)
Authentication: None required for public read endpoints.

Reverse-engineering sources:
  - https://algotraffic.com/static/js/main.js  (React SPA bundle)
  - NetworkManager class, endpoint mapping objects Nr/Or/Ur/_r
  - OIDC discovery: https://authentication.algotraffic.com/.well-known/openid-configuration

Usage:
    from aldot_client import ALDOTClient

    client = ALDOTClient()

    # List all cameras
    cameras = client.get_cameras()
    for cam in cameras:
        print(cam.id, cam.location.city, cam.snapshot_url)

    # Filter by county
    mobile_cams = client.get_cameras(county="Mobile")

    # Get live snapshot image bytes
    jpeg_bytes = client.get_camera_snapshot(1845)

    # Traffic events
    events = client.get_traffic_events(active=True)

    # Travel times
    times = client.get_travel_times()

    # Message signs
    signs = client.get_message_signs()

    # Weather alerts
    alerts = client.get_weather_alerts()

    # Rest-area / facilities
    facilities = client.get_facilities()

    # Service-assistance patrols (SAP routes)
    patrols = client.get_service_assistance_patrols()

stdlib only -- no third-party dependencies required.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.algotraffic.com"
DEFAULT_API_VERSION = "v4.0"

# Endpoint path names (mirrored from the JS bundle's Nr/Ur/_r objects)
_ENDPOINTS: Dict[str, str] = {
    "cameras": "Cameras",
    "traffic_events": "TrafficEvents",
    "travel_times": "TravelTimes",
    "message_signs": "MessageSigns",
    "ferries": "Ferries",
    "weather_alerts": "WeatherAlerts",
    "facilities": "Facilities",
    "service_assistance_patrols": "ServiceAssistancePatrols",
    "zones": "Zones",
    "alea_alerts": "AleaAlerts",
    "aldot_messages": "AldotMessages",
    "cities": "Cities",
    "counties": "Counties",
    "places": "Places",
    "forecasts": "Forecasts",
    "traveler_information_systems": "TravelerInformationSystems",
}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://algotraffic.com",
    "Referer": "https://algotraffic.com/",
}


# ---------------------------------------------------------------------------
# Data-class models
# ---------------------------------------------------------------------------


@dataclass
class StateRoadway:
    name: str
    type: str
    route_number: Optional[int] = None
    special_type: Optional[str] = None


@dataclass
class RoadwayPoint:
    direction: str
    latitude: float
    longitude: float


@dataclass
class Location:
    latitude: float
    longitude: float
    city: Optional[str] = None
    county: Optional[str] = None
    display_route_designator: Optional[str] = None
    route_designator: Optional[str] = None
    route_designator_type: Optional[str] = None
    display_cross_street: Optional[str] = None
    cross_street: Optional[str] = None
    cross_street_type: Optional[str] = None
    direction: Optional[str] = None
    linear_reference: Optional[float] = None
    state_roadways: List[StateRoadway] = field(default_factory=list)
    nearest_roadway_points: List[RoadwayPoint] = field(default_factory=list)
    intersecting_state_roadways: List[StateRoadway] = field(default_factory=list)


@dataclass
class PlaybackUrls:
    hls: Optional[str] = None
    dash: Optional[str] = None


@dataclass
class Camera:
    id: int
    location: Location
    responsible_region: Optional[str] = None
    playback_urls: Optional[PlaybackUrls] = None
    access_level: Optional[str] = None
    map_layer: Optional[str] = None
    perm_link: Optional[str] = None
    snapshot_url: Optional[str] = None
    map_image_url: Optional[str] = None
    # Legacy v3.0 field (before playbackUrls split into hls/dash)
    hls_url: Optional[str] = None


@dataclass
class Color:
    red: int
    green: int
    blue: int
    alpha: float
    hex: str


@dataclass
class SignStyle:
    type: str
    background_color: Optional[Color] = None
    glyph_color: Optional[Color] = None


@dataclass
class LaneInfo:
    state: str
    type: str
    placement: int


@dataclass
class LaneDirection:
    direction: str
    lanes: List[LaneInfo] = field(default_factory=list)


@dataclass
class LineStyle:
    stroke_color: Optional[Color] = None
    fill_color: Optional[Color] = None
    line_width: int = 2


@dataclass
class TrafficEvent:
    id: int
    responsible_region: Optional[str] = None
    severity: Optional[str] = None
    type: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    last_updated_at: Optional[str] = None
    active: bool = False
    title: Optional[str] = None
    sub_title: Optional[str] = None
    short_sub_title: Optional[str] = None
    description: Optional[str] = None
    start_location: Optional[Location] = None
    end_location: Optional[Location] = None
    lane_directions: List[LaneDirection] = field(default_factory=list)
    sign_style: Optional[SignStyle] = None
    map_layer: Optional[str] = None
    perm_link: Optional[str] = None
    map_image_url: Optional[str] = None


@dataclass
class TravelTimeEndpoint:
    name: Optional[str] = None
    display_place_name: Optional[str] = None
    display_intersecting_place_name: Optional[str] = None
    city: Optional[str] = None
    direction: Optional[str] = None
    state_roadways: List[StateRoadway] = field(default_factory=list)
    intersecting_state_roadways: List[StateRoadway] = field(default_factory=list)


@dataclass
class TravelTime:
    id: int
    origin: Optional[TravelTimeEndpoint] = None
    destination: Optional[TravelTimeEndpoint] = None
    last_updated: Optional[str] = None
    expires_at: Optional[str] = None
    estimated_time_minutes: Optional[int] = None
    average_speed_mph: Optional[float] = None
    total_distance_miles: Optional[float] = None
    name: Optional[str] = None
    congestion_level: Optional[str] = None


@dataclass
class SignLine:
    alignment: Optional[str] = None
    flash_on_seconds: Optional[float] = None
    flash_off_seconds: Optional[float] = None
    text: Optional[str] = None


@dataclass
class SignPage:
    page_on_seconds: Optional[float] = None
    page_off_seconds: Optional[float] = None
    alignment: Optional[str] = None
    lines: List[SignLine] = field(default_factory=list)


@dataclass
class MessageSign:
    id: int
    location: Optional[Location] = None
    responsible_region: Optional[str] = None
    height_pixels: Optional[int] = None
    width_pixels: Optional[int] = None
    character_height_pixels: Optional[int] = None
    character_width_pixels: Optional[int] = None
    beacon_type: Optional[str] = None
    beacon_on: bool = False
    pages: List[SignPage] = field(default_factory=list)
    map_layer: Optional[str] = None
    perm_link: Optional[str] = None
    map_image_url: Optional[str] = None


@dataclass
class WeatherZone:
    id: str
    name: str
    description: Optional[str] = None
    area: Optional[str] = None
    type: Optional[str] = None


@dataclass
class WeatherAlert:
    id: str
    name: Optional[str] = None
    headline: Optional[str] = None
    description: Optional[str] = None
    instruction: Optional[str] = None
    sender: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    certainty: Optional[str] = None
    response: Optional[str] = None
    message_type: Optional[str] = None
    sent: Optional[str] = None
    effective: Optional[str] = None
    onset: Optional[str] = None
    expiration: Optional[str] = None
    end: Optional[str] = None
    affected_areas: List[WeatherZone] = field(default_factory=list)
    fill_color: Optional[Color] = None
    stroke_color: Optional[Color] = None
    type: Optional[str] = None


@dataclass
class Facility:
    id: int
    name: Optional[str] = None
    code: Optional[str] = None
    open: bool = True
    type: Optional[str] = None
    location: Optional[Location] = None


@dataclass
class PatrolRoute:
    direction: Optional[str] = None
    start_location: Optional[Location] = None
    end_location: Optional[Location] = None


@dataclass
class ServiceAssistancePatrol:
    id: int
    region: Optional[str] = None
    title: Optional[str] = None
    sub_title: Optional[str] = None
    description: Optional[str] = None
    phone_number: Optional[str] = None
    routes: List[PatrolRoute] = field(default_factory=list)
    map_layer: Optional[str] = None
    map_image_url: Optional[str] = None


@dataclass
class AleaAlertImage:
    url: str


@dataclass
class AleaAlert:
    id: int
    type: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    publish_date: Optional[str] = None
    images: List[AleaAlertImage] = field(default_factory=list)


@dataclass
class Zone:
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    area: Optional[str] = None
    type: Optional[str] = None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_color(d: Optional[Dict]) -> Optional[Color]:
    if not d:
        return None
    return Color(
        red=d.get("red", 0),
        green=d.get("green", 0),
        blue=d.get("blue", 0),
        alpha=d.get("alpha", 1.0),
        hex=d.get("hex", ""),
    )


def _parse_state_roadways(lst: Optional[List]) -> List[StateRoadway]:
    if not lst:
        return []
    return [
        StateRoadway(
            name=r.get("name", ""),
            type=r.get("type", ""),
            route_number=r.get("routeNumber"),
            special_type=r.get("specialType"),
        )
        for r in lst
    ]


def _parse_roadway_points(lst: Optional[List]) -> List[RoadwayPoint]:
    if not lst:
        return []
    return [
        RoadwayPoint(
            direction=p.get("direction", ""),
            latitude=p.get("latitude", 0.0),
            longitude=p.get("longitude", 0.0),
        )
        for p in lst
    ]


def _parse_location(d: Optional[Dict]) -> Optional[Location]:
    if not d:
        return None
    return Location(
        latitude=d.get("latitude", 0.0),
        longitude=d.get("longitude", 0.0),
        city=d.get("city"),
        county=d.get("county"),
        display_route_designator=d.get("displayRouteDesignator"),
        route_designator=d.get("routeDesignator"),
        route_designator_type=d.get("routeDesignatorType"),
        display_cross_street=d.get("displayCrossStreet"),
        cross_street=d.get("crossStreet"),
        cross_street_type=d.get("crossStreetType"),
        direction=d.get("direction"),
        linear_reference=d.get("linearReference"),
        state_roadways=_parse_state_roadways(d.get("stateRoadways")),
        nearest_roadway_points=_parse_roadway_points(d.get("nearestRoadwayPoints")),
        intersecting_state_roadways=_parse_state_roadways(
            d.get("intersectingStateRoadways")
        ),
    )


def _parse_camera(d: Dict) -> Camera:
    pu = d.get("playbackUrls") or {}
    return Camera(
        id=d["id"],
        location=_parse_location(d.get("location")) or Location(0.0, 0.0),
        responsible_region=d.get("responsibleRegion"),
        playback_urls=PlaybackUrls(
            hls=pu.get("hls") or d.get("hlsUrl"),
            dash=pu.get("dash"),
        ),
        access_level=d.get("accessLevel"),
        map_layer=d.get("mapLayer"),
        perm_link=d.get("permLink"),
        snapshot_url=d.get("snapshotImageUrl") or d.get("imageUrl"),
        map_image_url=d.get("mapImageUrl"),
        hls_url=d.get("hlsUrl"),
    )


def _parse_traffic_event(d: Dict) -> TrafficEvent:
    sign = d.get("signStyle")
    lane_dirs = []
    for ld in d.get("laneDirections", []):
        lanes = [
            LaneInfo(
                state=ln.get("state", ""),
                type=ln.get("type", ""),
                placement=ln.get("placement", 0),
            )
            for ln in ld.get("lanes", [])
        ]
        lane_dirs.append(LaneDirection(direction=ld.get("direction", ""), lanes=lanes))
    return TrafficEvent(
        id=d["id"],
        responsible_region=d.get("responsibleRegion"),
        severity=d.get("severity"),
        type=d.get("type"),
        start=d.get("start"),
        end=d.get("end"),
        last_updated_at=d.get("lastUpdatedAt"),
        active=d.get("active", False),
        title=d.get("title"),
        sub_title=d.get("subTitle"),
        short_sub_title=d.get("shortSubTitle"),
        description=d.get("description"),
        start_location=_parse_location(d.get("startLocation")),
        end_location=_parse_location(d.get("endLocation")),
        lane_directions=lane_dirs,
        sign_style=(
            SignStyle(
                type=sign.get("type", ""),
                background_color=_parse_color(sign.get("backgroundColor")),
                glyph_color=_parse_color(sign.get("glyphColor")),
            )
            if sign
            else None
        ),
        map_layer=d.get("mapLayer"),
        perm_link=d.get("permLink"),
        map_image_url=d.get("mapImageUrl"),
    )


def _parse_tt_endpoint(d: Optional[Dict]) -> Optional[TravelTimeEndpoint]:
    if not d:
        return None
    return TravelTimeEndpoint(
        name=d.get("name"),
        display_place_name=d.get("displayPlaceName"),
        display_intersecting_place_name=d.get("displayIntersectingPlaceName"),
        city=d.get("city"),
        direction=d.get("direction"),
        state_roadways=_parse_state_roadways(d.get("stateRoadways")),
        intersecting_state_roadways=_parse_state_roadways(
            d.get("intersectingStateRoadways")
        ),
    )


def _parse_travel_time(d: Dict) -> TravelTime:
    return TravelTime(
        id=d["id"],
        origin=_parse_tt_endpoint(d.get("origin")),
        destination=_parse_tt_endpoint(d.get("destination")),
        last_updated=d.get("lastUpdated"),
        expires_at=d.get("expiresAt"),
        estimated_time_minutes=d.get("estimatedTimeMinutes"),
        average_speed_mph=d.get("averageSpeedMph"),
        total_distance_miles=d.get("totalDistanceMiles"),
        name=d.get("name"),
        congestion_level=d.get("congestionLevel"),
    )


def _parse_sign_page(d: Dict) -> SignPage:
    lines = [
        SignLine(
            alignment=ln.get("alignment"),
            flash_on_seconds=ln.get("flashOnSeconds"),
            flash_off_seconds=ln.get("flashOffSeconds"),
            text=ln.get("text"),
        )
        for ln in d.get("lines", [])
    ]
    return SignPage(
        page_on_seconds=d.get("pageOnSeconds"),
        page_off_seconds=d.get("pageOffSeconds"),
        alignment=d.get("alignment"),
        lines=lines,
    )


def _parse_message_sign(d: Dict) -> MessageSign:
    return MessageSign(
        id=d["id"],
        location=_parse_location(d.get("location")),
        responsible_region=d.get("responsibleRegion"),
        height_pixels=d.get("heightPixels"),
        width_pixels=d.get("widthPixels"),
        character_height_pixels=d.get("characterHeightPixels"),
        character_width_pixels=d.get("characterWidthPixels"),
        beacon_type=d.get("beaconType"),
        beacon_on=d.get("beaconOn", False),
        pages=[_parse_sign_page(p) for p in d.get("pages", [])],
        map_layer=d.get("mapLayer"),
        perm_link=d.get("permLink"),
        map_image_url=d.get("mapImageUrl"),
    )


def _parse_weather_zone(d: Dict) -> WeatherZone:
    return WeatherZone(
        id=d["id"],
        name=d.get("name", ""),
        description=d.get("description"),
        area=d.get("area"),
        type=d.get("type"),
    )


def _parse_weather_alert(d: Dict) -> WeatherAlert:
    return WeatherAlert(
        id=d["id"],
        name=d.get("name"),
        headline=d.get("headline"),
        description=d.get("description"),
        instruction=d.get("instruction"),
        sender=d.get("sender"),
        severity=d.get("severity"),
        urgency=d.get("urgency"),
        certainty=d.get("certainty"),
        response=d.get("response"),
        message_type=d.get("messageType"),
        sent=d.get("sent"),
        effective=d.get("effective"),
        onset=d.get("onset"),
        expiration=d.get("expiration"),
        end=d.get("end"),
        affected_areas=[_parse_weather_zone(z) for z in d.get("affectedAreas", [])],
        fill_color=_parse_color(d.get("fillColor")),
        stroke_color=_parse_color(d.get("strokeColor")),
        type=d.get("type"),
    )


def _parse_facility(d: Dict) -> Facility:
    return Facility(
        id=d["id"],
        name=d.get("name"),
        code=d.get("code"),
        open=d.get("open", True),
        type=d.get("type"),
        location=_parse_location(d.get("location")),
    )


def _parse_patrol(d: Dict) -> ServiceAssistancePatrol:
    routes = []
    for r in d.get("routes", []):
        routes.append(
            PatrolRoute(
                direction=r.get("direction"),
                start_location=_parse_location(r.get("startLocation")),
                end_location=_parse_location(r.get("endLocation")),
            )
        )
    return ServiceAssistancePatrol(
        id=d["id"],
        region=d.get("region"),
        title=d.get("title"),
        sub_title=d.get("subTitle"),
        description=d.get("description"),
        phone_number=d.get("phoneNumber"),
        routes=routes,
        map_layer=d.get("mapLayer"),
        map_image_url=d.get("mapImageUrl"),
    )


def _parse_alea_alert(d: Dict) -> AleaAlert:
    return AleaAlert(
        id=d["id"],
        type=d.get("type"),
        url=d.get("url"),
        title=d.get("title"),
        text=d.get("text"),
        publish_date=d.get("publishDate"),
        images=[AleaAlertImage(url=img["url"]) for img in d.get("images", [])],
    )


def _parse_zone(d: Dict) -> Zone:
    return Zone(
        id=d["id"],
        name=d.get("name"),
        description=d.get("description"),
        area=d.get("area"),
        type=d.get("type"),
    )


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class ALDOTError(Exception):
    """Raised when the ALDOT API returns an unexpected response."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ALDOTClient:
    """
    Synchronous client for the ALGO Traffic / ALDOT API.

    All endpoints are public and require no authentication.
    Pagination is not required -- the API returns full result sets.

    Parameters
    ----------
    api_version : str
        API version string, e.g. "v4.0" (default) or "v3.0".
    timeout : int
        HTTP timeout in seconds (default 30).
    extra_headers : dict
        Optional extra headers to include on every request.
    """

    def __init__(
        self,
        api_version: str = DEFAULT_API_VERSION,
        timeout: int = 30,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.api_version = api_version
        self.timeout = timeout
        self._headers = {**_DEFAULT_HEADERS, **(extra_headers or {})}
        self._base = f"{BASE_URL}/{api_version}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, endpoint_key: str, resource_id: Any = None, sub: str = "") -> str:
        path = _ENDPOINTS.get(endpoint_key, endpoint_key)
        url = f"{self._base}/{path}"
        if resource_id is not None:
            url += f"/{urllib.parse.quote(str(resource_id), safe='')}"
        if sub:
            url += f"/{sub}"
        return url

    def _request(
        self,
        url: str,
        params: Optional[Dict[str, str]] = None,
        accept: str = "application/json",
    ) -> Any:
        """
        Perform a GET request and return parsed JSON (or raw bytes for images).
        """
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                url = f"{url}?{qs}"
        headers = {**self._headers, "Accept": accept}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                ct = resp.getheader("Content-Type", "")
                if "json" in ct or accept == "application/json":
                    if not raw:
                        return None
                    return json.loads(raw)
                return raw
        except urllib.error.HTTPError as exc:
            raise ALDOTError(
                f"HTTP {exc.code} from {url}: {exc.reason}", status_code=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            raise ALDOTError(f"Network error fetching {url}: {exc.reason}") from exc

    def _get_list(
        self, endpoint_key: str, params: Optional[Dict] = None
    ) -> List[Dict]:
        data = self._request(self._url(endpoint_key), params=params)
        if data is None:
            return []
        if isinstance(data, list):
            return data
        # Some endpoints wrap in {items: [...]} or similar -- handle gracefully
        if isinstance(data, dict):
            for key in ("items", "data", "results"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        county: Optional[str] = None,
        city: Optional[str] = None,
        region: Optional[str] = None,
        route_designator: Optional[str] = None,
    ) -> List[Camera]:
        """
        Fetch all public traffic cameras.

        Parameters
        ----------
        county : str, optional
            Filter by county name (e.g. "Jefferson", "Mobile").
        city : str, optional
            Filter by city name (e.g. "Birmingham").
        region : str, optional
            Filter by ALDOT responsible region
            ("Southwest", "Southeast", "EastCentral", "WestCentral", "North").
        route_designator : str, optional
            Filter by route designator (e.g. "I-65"). Note: as of v4.0 this
            parameter returns all cameras (server-side filter may be no-op).

        Returns
        -------
        List[Camera]
        """
        params: Dict[str, Any] = {}
        if county:
            params["county"] = county
        if city:
            params["city"] = city
        if region:
            params["region"] = region
        if route_designator:
            params["routeDesignator"] = route_designator
        raw = self._get_list("cameras", params or None)
        return [_parse_camera(d) for d in raw]

    def get_camera(self, camera_id: int) -> Camera:
        """
        Fetch a single camera by its integer ID.

        Parameters
        ----------
        camera_id : int
            Camera numeric identifier.

        Returns
        -------
        Camera
        """
        data = self._request(self._url("cameras", camera_id))
        return _parse_camera(data)

    def get_camera_snapshot(self, camera_id: int, scale: str = "1x") -> bytes:
        """
        Download the latest JPEG snapshot for a camera.

        Parameters
        ----------
        camera_id : int
            Camera numeric identifier.
        scale : str
            Image scale hint: "1x" (default) or "2x".

        Returns
        -------
        bytes
            Raw JPEG image data.
        """
        # The snapshot URL uses the bare version (v4) without the .0
        ver = self.api_version.split(".")[0]  # "v4.0" -> "v4"
        url = f"{BASE_URL}/{ver}/Cameras/{camera_id}/snapshot.jpg"
        return self._request(url, accept="image/jpeg")  # type: ignore[return-value]

    def get_camera_map_image(self, camera_id: int, scale: str = "1x") -> bytes:
        """
        Download the static map thumbnail image for a camera location.

        Returns
        -------
        bytes
            Raw JPEG image data.
        """
        ver = self.api_version.split(".")[0]
        url = f"{BASE_URL}/{ver}/Cameras/{camera_id}/map@{scale}.jpg"
        return self._request(url, accept="image/jpeg")  # type: ignore[return-value]

    def get_cameras_near_event(self, event_id: int) -> List[Camera]:
        """
        Fetch cameras associated with a specific traffic event.

        Parameters
        ----------
        event_id : int
            TrafficEvent numeric identifier.

        Returns
        -------
        List[Camera]
        """
        data = self._request(self._url("traffic_events", event_id, sub="Cameras"))
        if not data:
            return []
        if isinstance(data, list):
            return [_parse_camera(d) for d in data]
        return []

    # ------------------------------------------------------------------
    # Traffic Events
    # ------------------------------------------------------------------

    def get_traffic_events(
        self,
        active: Optional[bool] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[TrafficEvent]:
        """
        Fetch all traffic events (roadwork, crashes, incidents, road conditions).

        Parameters
        ----------
        active : bool, optional
            If True, return only currently active events.
        event_type : str, optional
            Filter by event type. Known values:
            "Roadwork", "Crash", "Incident", "RoadCondition", "RegionalEvent".
        severity : str, optional
            Filter by severity. Known values:
            "MinorDelay", "ModerateDelay", "MajorDelay", "Unknown".

        Returns
        -------
        List[TrafficEvent]
        """
        params: Dict[str, Any] = {}
        if active is not None:
            params["active"] = str(active).lower()
        if event_type:
            params["type"] = event_type
        if severity:
            params["severity"] = severity
        raw = self._get_list("traffic_events", params or None)
        return [_parse_traffic_event(d) for d in raw]

    def get_traffic_event(self, event_id: int) -> TrafficEvent:
        """
        Fetch a single traffic event by its integer ID.

        Returns
        -------
        TrafficEvent
        """
        data = self._request(self._url("traffic_events", event_id))
        return _parse_traffic_event(data)

    # ------------------------------------------------------------------
    # Travel Times
    # ------------------------------------------------------------------

    def get_travel_times(self) -> List[TravelTime]:
        """
        Fetch all current travel time readings (loop-detector segments).

        Returns
        -------
        List[TravelTime]
        """
        raw = self._get_list("travel_times")
        return [_parse_travel_time(d) for d in raw]

    # ------------------------------------------------------------------
    # Dynamic Message Signs
    # ------------------------------------------------------------------

    def get_message_signs(self) -> List[MessageSign]:
        """
        Fetch all dynamic message sign (DMS) boards with their current messages.

        Returns
        -------
        List[MessageSign]
        """
        raw = self._get_list("message_signs")
        return [_parse_message_sign(d) for d in raw]

    def get_message_sign(self, sign_id: int) -> MessageSign:
        """
        Fetch a single dynamic message sign by ID.

        Returns
        -------
        MessageSign
        """
        data = self._request(self._url("message_signs", sign_id))
        return _parse_message_sign(data)

    # ------------------------------------------------------------------
    # Weather Alerts
    # ------------------------------------------------------------------

    def get_weather_alerts(self) -> List[WeatherAlert]:
        """
        Fetch all active NWS weather alerts affecting Alabama.

        Returns
        -------
        List[WeatherAlert]
        """
        raw = self._get_list("weather_alerts")
        return [_parse_weather_alert(d) for d in raw]

    # ------------------------------------------------------------------
    # Facilities (Rest Areas)
    # ------------------------------------------------------------------

    def get_facilities(
        self, facility_type: Optional[str] = None
    ) -> List[Facility]:
        """
        Fetch ALDOT facilities (rest areas, welcome centers, etc.).

        Parameters
        ----------
        facility_type : str, optional
            Filter by type, e.g. "RestArea", "WelcomeCenter".

        Returns
        -------
        List[Facility]
        """
        params = {"type": facility_type} if facility_type else None
        raw = self._get_list("facilities", params)
        return [_parse_facility(d) for d in raw]

    # ------------------------------------------------------------------
    # Service Assistance Patrols
    # ------------------------------------------------------------------

    def get_service_assistance_patrols(self) -> List[ServiceAssistancePatrol]:
        """
        Fetch Alabama Service Assistance Patrol (ASAP) coverage regions.

        Returns
        -------
        List[ServiceAssistancePatrol]
        """
        raw = self._get_list("service_assistance_patrols")
        return [_parse_patrol(d) for d in raw]

    # ------------------------------------------------------------------
    # ALEA Alerts (Missing persons, Amber/Silver/Blue alerts)
    # ------------------------------------------------------------------

    def get_alea_alerts(self) -> List[AleaAlert]:
        """
        Fetch active ALEA (Alabama Law Enforcement Agency) public safety alerts.
        These include Amber, Silver, Blue, and Missing Child alerts.

        Returns
        -------
        List[AleaAlert]
        """
        raw = self._get_list("alea_alerts")
        return [_parse_alea_alert(d) for d in raw]

    # ------------------------------------------------------------------
    # Ferries
    # ------------------------------------------------------------------

    def get_ferries(self) -> List[Dict]:
        """
        Fetch Alabama river ferry status and wait times.

        Returns raw dicts since this endpoint has few users.

        Returns
        -------
        List[dict]
        """
        return self._get_list("ferries")

    # ------------------------------------------------------------------
    # Geographic lookups
    # ------------------------------------------------------------------

    def get_zones(self) -> List[Zone]:
        """
        Fetch all NWS weather zones covering Alabama.

        Returns
        -------
        List[Zone]
        """
        raw = self._get_list("zones")
        return [_parse_zone(d) for d in raw]

    def get_cities(self) -> List[Dict]:
        """
        Fetch the list of Alabama cities tracked by the system.

        Returns
        -------
        List[dict]  Each dict has keys: id, name
        """
        return self._get_list("cities")

    def get_counties(self) -> List[Dict]:
        """
        Fetch all Alabama counties.

        Returns
        -------
        List[dict]  Each dict has keys: id, name
        """
        return self._get_list("counties")

    # ------------------------------------------------------------------
    # Low-level raw access
    # ------------------------------------------------------------------

    def raw_get(
        self,
        path: str,
        params: Optional[Dict[str, str]] = None,
        accept: str = "application/json",
    ) -> Any:
        """
        Make a raw GET request to any API path.

        Parameters
        ----------
        path : str
            URL path relative to the base API URL and version,
            e.g. "Cameras/1845" or "TrafficEvents?active=true".
        params : dict, optional
            Query string parameters.
        accept : str
            Accept header value.

        Returns
        -------
        Parsed JSON (list or dict) or raw bytes for image responses.
        """
        url = f"{self._base}/{path.lstrip('/')}"
        return self._request(url, params=params, accept=accept)


# ---------------------------------------------------------------------------
# CLI / quick demo
# ---------------------------------------------------------------------------


def _demo():
    """Quick sanity check -- prints summary stats for each endpoint."""
    import sys

    client = ALDOTClient()

    print("=== ALDOT / ALGO Traffic API Demo ===\n")

    try:
        cameras = client.get_cameras()
        print(f"Cameras:                {len(cameras):>5}  (total public cameras)")
        if cameras:
            c = cameras[0]
            print(
                f"  Example: #{c.id}  {c.location.city or '?'}, "
                f"{c.location.display_route_designator or '?'}  "
                f"@ {c.location.display_cross_street or '?'}"
            )
    except ALDOTError as e:
        print(f"Cameras: ERROR {e}")

    try:
        events = client.get_traffic_events()
        active = [e for e in events if e.active]
        print(f"Traffic Events:         {len(events):>5}  ({len(active)} active)")
        types = {}
        for ev in events:
            types[ev.type] = types.get(ev.type, 0) + 1
        for t, n in sorted(types.items()):
            print(f"  {t or 'Unknown'}: {n}")
    except ALDOTError as e:
        print(f"Traffic Events: ERROR {e}")

    try:
        times = client.get_travel_times()
        print(f"Travel Times:           {len(times):>5}")
        if times:
            t = times[0]
            print(
                f"  Example: {t.name or 'unnamed'} – "
                f"{t.estimated_time_minutes} min  ({t.congestion_level})"
            )
    except ALDOTError as e:
        print(f"Travel Times: ERROR {e}")

    try:
        signs = client.get_message_signs()
        print(f"Dynamic Message Signs:  {len(signs):>5}")
    except ALDOTError as e:
        print(f"Message Signs: ERROR {e}")

    try:
        alerts = client.get_weather_alerts()
        print(f"Weather Alerts:         {len(alerts):>5}")
        for a in alerts[:3]:
            print(f"  [{a.severity}] {a.name}")
    except ALDOTError as e:
        print(f"Weather Alerts: ERROR {e}")

    try:
        facilities = client.get_facilities()
        print(f"Facilities:             {len(facilities):>5}")
    except ALDOTError as e:
        print(f"Facilities: ERROR {e}")

    try:
        patrols = client.get_service_assistance_patrols()
        print(f"ASAP Coverage Regions:  {len(patrols):>5}")
    except ALDOTError as e:
        print(f"ASAP Patrols: ERROR {e}")

    try:
        alea = client.get_alea_alerts()
        print(f"ALEA Alerts:            {len(alea):>5}")
        for a in alea[:2]:
            print(f"  [{a.type}] {a.title}")
    except ALDOTError as e:
        print(f"ALEA Alerts: ERROR {e}")

    try:
        ferries = client.get_ferries()
        print(f"Ferries:                {len(ferries):>5}")
    except ALDOTError as e:
        print(f"Ferries: ERROR {e}")

    # Snapshot test
    print("\n--- Snapshot test for camera #1845 ---")
    try:
        jpeg = client.get_camera_snapshot(1845)
        print(f"Snapshot bytes: {len(jpeg)}  magic={jpeg[:4].hex()}")
        assert jpeg[:2] == b"\xff\xd8", "Not a valid JPEG"
        print("JPEG signature: OK")
    except ALDOTError as e:
        print(f"Snapshot: ERROR {e}")

    print("\nDone.")


if __name__ == "__main__":
    _demo()
