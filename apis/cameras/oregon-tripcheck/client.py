"""
Oregon TripCheck API Client
============================
Reverse-engineered client for Oregon ODOT's TripCheck traveler information system.

All endpoints were discovered by analysing:
  - https://tripcheck.com/ (map page JavaScript)
  - /Scripts/map/roadconditions.min.js  (layer/data-source registry)
  - /Scripts/map/templates/*.min.js     (field schemas and UI templates)
  - /Scripts/map/data/*.js              (live EsriJSON data feeds)
  - /DynamicReports/Report/Cameras/0   (camera report HTML — confirmed image URL pattern)

Base URL : https://tripcheck.com
Data feeds: https://tripcheck.com/Scripts/map/data/<name>.js
Images    : https://tripcheck.com/RoadCams/cams/<filename>
LDI images: https://tripcheck.com/RoadCams/cams/camsLDI/<filename>
Video     : http://ie.trafficland.com/v1.0/<webid>/{half|full}?system=oregondot&pubtoken=<token>

All data feeds return EsriJSON (FeatureSet) and are cached for varying intervals:
  - Cameras inventory    : 86400 s (24 h)
  - Road/weather reports : 900 s   (15 min)
  - RWIS stations        : 120 s   (2 min)
  - Events / incidents   : 120 s   (2 min)
  - Travel times         : 120 s   (2 min)
  - Alerts               : 120 s   (2 min)
  - Parking              : 120 s   (2 min)

UNIQUE FEATURE — RWIS + Camera Co-location
-------------------------------------------
Oregon TripCheck is uniquely valuable because RWIS automated weather stations are
co-located along the same highway corridors as ODOT road cameras. This means you can:
  1. Fetch all cameras (cctvinventory.js) — 1120+ cameras statewide
  2. Fetch all RWIS stations (RWIS.js) — 221+ automated weather stations
  3. Match each RWIS station to nearby cameras using haversine distance

Use ``client.get_cameras_near_rwis()`` or ``client.get_rwis_with_nearby_cameras()``
to get pre-computed co-location pairs.

Official ODOT API (subscription required)
------------------------------------------
ODOT also offers a formal API via Azure API Management at:
  Portal  : https://apiportal.odot.state.or.us/
  Gateway : https://api.odot.state.or.us/
  Key     : Ocp-Apim-Subscription-Key header (sign up at portal above)

The official API returns XML or JSON and requires a free subscription key.
The unofficial data feeds at /Scripts/map/data/*.js work without any key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://tripcheck.com"

# All discovered data-feed endpoints (relative to BASE_URL)
ENDPOINTS: Dict[str, str] = {
    # --- Camera ---
    "cameras":            "/Scripts/map/data/cctvinventory.js",
    "camera_video":       "/Scripts/map/data/TrafficVideo.js",

    # --- Road & Weather ---
    "road_weather":       "/Scripts/map/data/rw.js",
    "rwis":               "/Scripts/map/data/RWIS.js",
    "rw_trucking":        "/Scripts/map/data/RWTrucking.js",

    # --- Events / Incidents ---
    "events_points":      "/Scripts/map/data/EVENT.js",
    "events_lines":       "/Scripts/map/data/EVENTLine.js",
    "incidents_points":   "/Scripts/map/data/INCD.js",
    "incidents_lines":    "/Scripts/map/data/INCDLine.js",

    # --- Closures / CIE (Critical Incident Events) ---
    "cie_endpoints":      "/Scripts/map/data/CieEndPoint.js",
    "cie_lines":          "/Scripts/map/data/CieLine.js",

    # --- Local Travel Events (TLE / municipalities) ---
    "tle_points":         "/Scripts/map/data/Tlev2-Points.js",
    "tle_lines":          "/Scripts/map/data/Tlev2-Lines.js",

    # --- Travel Time ---
    "travel_times":       "/Scripts/map/data/traveltime.js",

    # --- Trucking / CVR link data ---
    "cvr_links":          "/Scripts/map/data/LINK.js",

    # --- Alerts (polygonal) ---
    "alerts":             "/Scripts/map/data/ALRT.js",

    # --- Parking ---
    "parking":            "/Scripts/map/data/mfparking.js",

    # --- Waze integration ---
    "waze_alerts":        "/Scripts/map/data/wazeAlerts.js",
    "waze_jams":          "/Scripts/map/data/wazeJams.js",

    # --- Bridge lifts ---
    "bridge_lifts":       "/Scripts/map/data/multBridge.js",
}

# Camera image URL templates
CAMERA_IMAGE_URL     = "https://tripcheck.com/RoadCams/cams/{filename}"
CAMERA_LDI_IMAGE_URL = "https://tripcheck.com/RoadCams/cams/camsLDI/{filename}"

# Video stream URL template (TrafficLand CDN)
# full = 352×240  |  half = 176×120
VIDEO_FULL_URL = "http://ie.trafficland.com/v1.0/{webid}/full?system=oregondot&pubtoken={pubtoken}&refreshRate={refreshRate}"
VIDEO_HALF_URL = "http://ie.trafficland.com/v1.0/{webid}/half?system=oregondot&pubtoken={pubtoken}&refreshRate={refreshRate}"

# ---------------------------------------------------------------------------
# Lightweight data containers
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    camera_id: int
    published_image_id: int
    filename: str
    icon_type: int
    latitude: float
    longitude: float
    route: str
    title: str
    video_id: int
    # geometry in EPSG:3857 (Web Mercator)
    x: float = 0.0
    y: float = 0.0

    @property
    def image_url(self) -> str:
        return CAMERA_IMAGE_URL.format(filename=self.filename)

    @property
    def ldi_image_url(self) -> str:
        """Last Daylight Image URL (only valid during LDI window hours)."""
        return CAMERA_LDI_IMAGE_URL.format(filename=self.filename)

    @property
    def has_video(self) -> bool:
        return self.video_id > 0


@dataclass
class CameraVideo:
    webid: int
    name: str
    orientation: str
    city_code: str
    provider: str
    longitude: float
    latitude: float
    zip_code: str
    full_image_url: str
    half_image_url: str


@dataclass
class RwisStation:
    """Road Weather Information System automated station."""
    station_id: int          # roadWeatherReportID
    station_code: str
    update_time: str
    alt_tag_text: str
    location_name: str
    tripcheck_name: str
    latitude: float
    longitude: float
    icon_type: int
    # Weather readings (may be empty strings if no data)
    curr_temp: str
    dew_point: str
    humidity: str
    precip: str
    rain_1hr: str
    visibility: str
    wind_direction: str
    wind_speed: str
    wind_speed_gust: str
    road_temp: str


@dataclass
class RoadWeatherReport:
    """Crew-submitted road/weather report (updated ~5×/day or on change)."""
    report_id: int
    icon_type: int
    active_report: str
    active_snow_zone_count: int
    chain_restriction_code: int
    chain_restriction_desc: str
    chain_restriction_start_mp: Optional[float]
    chain_restriction_end_mp: Optional[float]
    commercial_restriction_code: int
    commercial_restriction_desc: str
    further_text: str
    link_id: str
    link_name: str
    link_start_mp: Optional[float]
    link_end_mp: Optional[float]
    location_name: str
    pavement_condition_code: int
    pavement_condition_desc: str
    rain_1hr: Optional[float]
    snowfall: Optional[float]
    snow_depth: Optional[float]
    temp_curr: Optional[float]
    temp_high: Optional[float]
    temp_low: Optional[float]
    weather_condition_desc: str
    entry_time: str
    expiration_time: str
    snow_zones: List[Dict] = field(default_factory=list)
    latitude: float = 0.0
    longitude: float = 0.0


@dataclass
class Incident:
    incident_id: int
    tocs_incident_id: Optional[int]
    type: str                   # "EVENT" | "INCD"
    last_updated: str
    start_time: str
    location_name: str
    route: str
    event_type_id: str
    event_type_name: str
    event_sub_type_id: int
    event_sub_type_name: str
    category_id: str
    category_desc: str
    severity_id: int
    severity_desc: str
    icon_type: int
    begin_mp: Optional[float]
    begin_marker: str
    end_mp: Optional[float]
    end_marker: str
    start_latitude: float
    start_longitude: float
    end_latitude: Optional[float]
    end_longitude: Optional[float]
    comments: str
    public_contact: str
    info_url: str
    lanes_affected: List[Dict] = field(default_factory=list)


@dataclass
class TravelTimeRoute:
    route_id: int
    destination: str
    min_route_time: Optional[int]
    travel_time: int            # minutes; -1 = N/A
    delay: int                  # minutes; -1 = N/A
    failure_msg: str
    timestamp: str


@dataclass
class TravelTimePoint:
    origin_id: int
    location_name: str
    icon_type: int
    latitude: float
    longitude: float
    routes: List[TravelTimeRoute] = field(default_factory=list)


@dataclass
class Alert:
    alert_id: int
    update_time: str
    start_time: str
    est_clear_time: str
    actual_clear_time: str
    alert_type: str
    priority: int
    source_id: int
    area_affected: str
    title: str
    header: str
    message_text: str
    further_info_url: str
    tripcheck_only: str
    entry_time: str
    # bounding polygon rings in EPSG:3857
    geometry_rings: List = field(default_factory=list)


@dataclass
class ParkingLot:
    icon_type: int
    location_name: str
    percent_full: int
    percent_full_message: str
    update_time: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class BridgeLift:
    name: str
    is_up: str
    last_updated: str
    schedule: str
    icon_type: int
    x: float = 0.0
    y: float = 0.0


@dataclass
class WazeAlert:
    alert_id: int
    publish_date: str
    report_date: str
    type_id: int
    event_type: str
    subtype_id: int
    event_subtype: str
    latitude: float
    longitude: float
    is_odot: int
    street: str
    city: str
    description: str
    icon_type: int


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class TripCheckClient:
    """
    Python client for Oregon TripCheck traveler information APIs.

    All data endpoints return EsriJSON (FeatureSet).  They are plain HTTP GET
    requests — no authentication, no API key required.

    Cache behaviour
    ---------------
    The client optionally caches responses in memory for the interval that
    TripCheck itself uses (set ``use_cache=True``).  By default caching is
    disabled so every call fetches fresh data.

    Usage
    -----
    >>> from oregon_tripcheck_client import TripCheckClient
    >>> client = TripCheckClient()
    >>> cameras = client.get_cameras()
    >>> print(cameras[0].image_url)
    >>> rwis = client.get_rwis_stations()
    >>> rw = client.get_road_weather()
    >>> events = client.get_events()
    >>> tt = client.get_travel_times()
    >>> alerts = client.get_alerts()
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TripCheckPythonClient/1.0; "
            "+https://github.com/example/tripcheck-client)"
        ),
        "Referer": "https://tripcheck.com/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    # Cache TTL mirrors TripCheck's own refresh intervals
    CACHE_TTL: Dict[str, int] = {
        "cameras":          86400,
        "camera_video":     86400,
        "road_weather":       900,
        "rwis":               120,
        "rw_trucking":        900,
        "events_points":      120,
        "events_lines":       120,
        "incidents_points":   120,
        "incidents_lines":    120,
        "cie_endpoints":      120,
        "cie_lines":          120,
        "tle_points":         120,
        "tle_lines":          120,
        "travel_times":       120,
        "cvr_links":          120,
        "alerts":             120,
        "parking":            120,
        "waze_alerts":        120,
        "waze_jams":          120,
        "bridge_lifts":       120,
    }

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = 30,
        use_cache: bool = False,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.use_cache = use_cache
        self._session = session or requests.Session()
        self._session.headers.update(self.DEFAULT_HEADERS)
        self._cache: Dict[str, Any] = {}
        self._cache_ts: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self, endpoint_key: str) -> Dict:
        """Fetch a named endpoint, optionally from in-memory cache."""
        url = self.base_url + ENDPOINTS[endpoint_key]
        if self.use_cache:
            ttl = self.CACHE_TTL.get(endpoint_key, 120)
            ts = self._cache_ts.get(endpoint_key, 0)
            if endpoint_key in self._cache and (time.time() - ts) < ttl:
                return self._cache[endpoint_key]

        # TripCheck appends ?dt=<timestamp> to bust browser caches on JS files
        response = self._session.get(
            url,
            params={"dt": int(time.time() * 1000)},
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            # TrafficVideo.js contains bare octal-looking ZIP codes like 04105
            # that are not valid JSON integers.  Fix them by quoting all
            # "zipCode": <bare-number> occurrences before parsing.
            import re as _re
            text = _re.sub(r'"zipCode"\s*:\s*(\d+)', r'"zipCode": "\1"', response.text)
            import json as _json
            data = _json.loads(text)

        if self.use_cache:
            self._cache[endpoint_key] = data
            self._cache_ts[endpoint_key] = time.time()
        return data

    @staticmethod
    def _features(data: Dict) -> List[Dict]:
        return data.get("features", [])

    @staticmethod
    def _attrs(feature: Dict) -> Dict:
        return feature.get("attributes", {})

    @staticmethod
    def _geom(feature: Dict) -> Dict:
        return feature.get("geometry", {})

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(self) -> List[Camera]:
        """
        Return all ODOT road cameras.

        Endpoint  : GET /Scripts/map/data/cctvinventory.js
        Cache TTL : 24 h
        Fields    : cameraId, publishedImageId, filename, iconType,
                    latitude, longitude, route, title, videoId
        """
        data = self._fetch("cameras")
        cameras: List[Camera] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            cameras.append(Camera(
                camera_id           = a.get("cameraId", 0),
                published_image_id  = a.get("publishedImageId", 0),
                filename            = a.get("filename", ""),
                icon_type           = a.get("iconType", 0),
                latitude            = a.get("latitude", 0.0),
                longitude           = a.get("longitude", 0.0),
                route               = a.get("route", "").strip(),
                title               = a.get("title", ""),
                video_id            = a.get("videoId", 0),
                x                   = g.get("x", 0.0),
                y                   = g.get("y", 0.0),
            ))
        return cameras

    def get_camera_image_url(self, camera: Camera, bust_cache: bool = True) -> str:
        """Return a ready-to-use URL for the camera's current snapshot."""
        url = camera.image_url
        if bust_cache:
            url += f"?rand={int(time.time() * 1000)}"
        return url

    def get_camera_ldi_url(self, camera: Camera, bust_cache: bool = True) -> str:
        """Return the Last Daylight Image URL for a camera."""
        url = camera.ldi_image_url
        if bust_cache:
            url += f"?rand={int(time.time() * 1000)}"
        return url

    def download_camera_image(self, camera: Camera) -> bytes:
        """Download and return the raw JPEG bytes for a camera snapshot."""
        url = self.get_camera_image_url(camera, bust_cache=True)
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content

    def get_camera_videos(self) -> List[CameraVideo]:
        """
        Return all cameras that have live streaming video (TrafficLand CDN).

        Endpoint  : GET /Scripts/map/data/TrafficVideo.js
        Cache TTL : 24 h
        Fields    : webid, name, orientation, cityCode, provider,
                    location{longitude, latitude, zipCode},
                    halfimage (URL), fullimage (URL)

        The pubtoken in each URL is per-camera and pre-computed by TripCheck.
        """
        data = self._fetch("camera_video")
        videos: List[CameraVideo] = []
        for cam in data.get("cameras", []):
            loc = cam.get("location", {})
            videos.append(CameraVideo(
                webid          = cam.get("webid", 0),
                name           = cam.get("name", ""),
                orientation    = cam.get("orientation", ""),
                city_code      = cam.get("cityCode", ""),
                provider       = cam.get("provider", ""),
                longitude      = loc.get("longitude", 0.0),
                latitude       = loc.get("latitude", 0.0),
                zip_code       = str(loc.get("zipCode", "")),
                full_image_url = cam.get("fullimage", ""),
                half_image_url = cam.get("halfimage", ""),
            ))
        return videos

    # ------------------------------------------------------------------
    # RWIS – Automated Road & Weather Stations
    # ------------------------------------------------------------------

    def get_rwis_stations(self) -> List[RwisStation]:
        """
        Return all RWIS (Road Weather Information System) automated stations.

        Endpoint  : GET /Scripts/map/data/RWIS.js
        Cache TTL : 2 min
        Key fields: roadWeatherReportID, station-code, updateTime,
                    currTemp, dewPoint, humidity, precip, rain1hr,
                    visibility, windDirection, windSpeed, windSpeedGust,
                    roadTemp (road surface temperature)

        Data is considered stale if updateTime is > 1 h old (TripCheck rule).
        """
        data = self._fetch("rwis")
        stations: List[RwisStation] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            stations.append(RwisStation(
                station_id      = a.get("roadWeatherReportID", 0),
                station_code    = a.get("station-code", ""),
                update_time     = a.get("updateTime", ""),
                alt_tag_text    = a.get("altTagText", ""),
                location_name   = a.get("locationName", ""),
                tripcheck_name  = a.get("tripcheckName", ""),
                latitude        = a.get("latitude", 0.0),
                longitude       = a.get("longitude", 0.0),
                icon_type       = a.get("iconType", 0),
                curr_temp       = a.get("currTemp", ""),
                dew_point       = a.get("dewPoint", ""),
                humidity        = a.get("humidity", ""),
                precip          = a.get("precip", ""),
                rain_1hr        = a.get("rain1hr", ""),
                visibility      = a.get("visibility", ""),
                wind_direction  = a.get("windDirection", ""),
                wind_speed      = a.get("windSpeed", ""),
                wind_speed_gust = a.get("windSpeedGust", ""),
                road_temp       = a.get("roadTemp", ""),
            ))
        return stations

    # ------------------------------------------------------------------
    # Road & Weather reports (crew-submitted)
    # ------------------------------------------------------------------

    def get_road_weather(self) -> List[RoadWeatherReport]:
        """
        Return crew-submitted road and weather condition reports.

        Endpoint  : GET /Scripts/map/data/rw.js
        Cache TTL : 15 min
        Key fields: chain restrictions, commercial restrictions, pavement
                    condition, weather condition, temperatures, snowfall,
                    snow depth, precipitation, snow zones

        Reports expire at expirationTime.  TripCheck hides them after
        that timestamp.  iconType values:
          8  = Road Closed
          11 = Severe Weather Hazard
          12 = Weather Warning
          13 = Carry Chains or Traction Tires (Snow Zone)
          14 = Weather Station (informational)
        """
        data = self._fetch("road_weather")
        reports: List[RoadWeatherReport] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            reports.append(RoadWeatherReport(
                report_id                    = a.get("id", 0),
                icon_type                    = a.get("iconType", 0),
                active_report                = a.get("activeReport", ""),
                active_snow_zone_count       = a.get("activeSnowZoneCount", 0),
                chain_restriction_code       = a.get("chainRestrictionCode", 0),
                chain_restriction_desc       = a.get("chainRestrictionDesc", ""),
                chain_restriction_start_mp   = a.get("chainRestrictionStartMP"),
                chain_restriction_end_mp     = a.get("chainRestrictionEndMP"),
                commercial_restriction_code  = a.get("commercialRestrictionCode", 0),
                commercial_restriction_desc  = a.get("commercialRestrictionDesc", ""),
                further_text                 = a.get("furtherText", ""),
                link_id                      = a.get("linkId", ""),
                link_name                    = a.get("linkName", ""),
                link_start_mp                = a.get("linkStartMP"),
                link_end_mp                  = a.get("linkEndMP"),
                location_name                = a.get("locationName", ""),
                pavement_condition_code      = a.get("pavementConditionCode", 0),
                pavement_condition_desc      = a.get("pavementConditionDesc", ""),
                rain_1hr                     = a.get("rain1hr"),
                snowfall                     = a.get("snowfall"),
                snow_depth                   = a.get("snowDepth"),
                temp_curr                    = a.get("tempCurr"),
                temp_high                    = a.get("tempHigh"),
                temp_low                     = a.get("tempLow"),
                weather_condition_desc       = a.get("weatherConditionDesc", ""),
                entry_time                   = a.get("entryTime", ""),
                expiration_time              = a.get("expirationTime", ""),
                snow_zones                   = a.get("snowZones", []),
                latitude                     = a.get("latitude", 0.0),
                longitude                    = a.get("longitude", 0.0),
            ))
        return reports

    def get_chain_restrictions(self) -> List[RoadWeatherReport]:
        """Filter road-weather reports to those with active chain restrictions."""
        return [r for r in self.get_road_weather() if r.chain_restriction_code > 0]

    def get_road_closures(self) -> List[RoadWeatherReport]:
        """Filter road-weather reports for road closures (iconType == 8)."""
        return [r for r in self.get_road_weather() if r.icon_type == 8]

    # ------------------------------------------------------------------
    # Road & Weather – Trucking
    # ------------------------------------------------------------------

    def get_trucking_restrictions(self) -> List[Dict]:
        """
        Return commercial-vehicle restriction reports.

        Endpoint  : GET /Scripts/map/data/RWTrucking.js
        Cache TTL : 15 min
        Fields    : same schema as road_weather but type=="TRK" and
                    includes commercialRestrictionCode/Desc.
        """
        data = self._fetch("rw_trucking")
        return self._features(data)

    # ------------------------------------------------------------------
    # Events & Incidents
    # ------------------------------------------------------------------

    def get_events(self, include_lines: bool = False) -> List[Incident]:
        """
        Return construction and planned events (ODOT).

        Endpoint (points) : GET /Scripts/map/data/EVENT.js
        Endpoint (lines)  : GET /Scripts/map/data/EVENTLine.js
        Cache TTL         : 2 min
        Key fields        : incidentId, type, eventTypeName,
                            eventSubTypeName, odotCategoryDescript,
                            odotSeverityDescript, beginMP/endMP,
                            comments, lanesAffected[]
        """
        return self._parse_incidents("events_points")

    def get_incidents(self) -> List[Incident]:
        """
        Return active traffic incidents (crashes, hazards, etc.).

        Endpoint  : GET /Scripts/map/data/INCD.js
        Cache TTL : 2 min
        """
        return self._parse_incidents("incidents_points")

    def get_cie_events(self) -> List[Incident]:
        """
        Return Critical Incident Events (CIE) endpoint points.

        Endpoint  : GET /Scripts/map/data/CieEndPoint.js
        Cache TTL : 2 min
        """
        return self._parse_incidents("cie_endpoints")

    def _parse_incidents(self, endpoint_key: str) -> List[Incident]:
        data = self._fetch(endpoint_key)
        incidents: List[Incident] = []
        for f in self._features(data):
            a = self._attrs(f)
            incidents.append(Incident(
                incident_id       = a.get("incidentId", 0),
                tocs_incident_id  = a.get("tocsIncidentId"),
                type              = a.get("type", ""),
                last_updated      = a.get("lastUpdated", ""),
                start_time        = a.get("startTime", ""),
                location_name     = a.get("locationName", ""),
                route             = a.get("route", "").strip(),
                event_type_id     = a.get("eventTypeId", ""),
                event_type_name   = a.get("eventTypeName", ""),
                event_sub_type_id = a.get("eventSubTypeId", 0),
                event_sub_type_name = a.get("eventSubTypeName", ""),
                category_id       = a.get("odotCategoryID", ""),
                category_desc     = a.get("odotCategoryDescript", ""),
                severity_id       = a.get("odotSeverityID", 0),
                severity_desc     = a.get("odotSeverityDescript", ""),
                icon_type         = a.get("iconType", 0),
                begin_mp          = a.get("beginMP"),
                begin_marker      = a.get("beginMarker", ""),
                end_mp            = a.get("endMP"),
                end_marker        = a.get("endMarker", ""),
                start_latitude    = a.get("startLatitude", 0.0),
                start_longitude   = a.get("startLongitude", 0.0),
                end_latitude      = a.get("endLatitude"),
                end_longitude     = a.get("endLongitude"),
                comments          = a.get("comments", ""),
                public_contact    = a.get("publicContact", ""),
                info_url          = a.get("infoUrl", ""),
                lanes_affected    = a.get("lanesAffected", []),
            ))
        return incidents

    # ------------------------------------------------------------------
    # Local Travel Events (TLE – municipalities)
    # ------------------------------------------------------------------

    def get_local_events(self) -> List[Dict]:
        """
        Return local travel events posted by municipalities.

        Endpoint  : GET /Scripts/map/data/Tlev2-Points.js
        Cache TTL : 2 min
        Key fields: eventId, typeName, impactId, impactName,
                    locationDescription, isBidirectional, headline,
                    comments, contactName, contactOrganization,
                    contactPhone, lastUpdate
        """
        data = self._fetch("tle_points")
        return self._features(data)

    # ------------------------------------------------------------------
    # Travel Times
    # ------------------------------------------------------------------

    def get_travel_times(self) -> List[TravelTimePoint]:
        """
        Return Portland-area real-time travel time segments.

        Endpoint  : GET /Scripts/map/data/traveltime.js
        Cache TTL : 2 min
        Structure : Each point has an origin location and a list of
                    route dests with travelTime (minutes), delay, and
                    minRouteTime (baseline).

        iconType == 25 for all travel time points.
        """
        data = self._fetch("travel_times")
        points: List[TravelTimePoint] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            routes = []
            for r in a.get("routes", []):
                routes.append(TravelTimeRoute(
                    route_id       = r.get("id", 0),
                    destination    = r.get("routeDest", ""),
                    min_route_time = r.get("minRouteTime"),
                    travel_time    = r.get("travelTime", -1),
                    delay          = r.get("delay", -1),
                    failure_msg    = r.get("failureMsg", ""),
                    timestamp      = r.get("dt", ""),
                ))
            points.append(TravelTimePoint(
                origin_id     = a.get("origId", 0),
                location_name = a.get("locationName", ""),
                icon_type     = a.get("iconType", 25),
                latitude      = a.get("latitude", 0.0),
                longitude     = a.get("longitude", 0.0),
                routes        = routes,
            ))
        return points

    # ------------------------------------------------------------------
    # Alerts (polygon, statewide)
    # ------------------------------------------------------------------

    def get_alerts(self) -> List[Alert]:
        """
        Return statewide travel alerts (closures, hazards, special events).

        Endpoint  : GET /Scripts/map/data/ALRT.js
        Cache TTL : 2 min
        alertType values:
          ALRTINCD  = Incident-based alert
          ALRTWTH   = Weather alert
          ALRTCONS  = Construction alert
          ALRTEVENT = Special event
        """
        data = self._fetch("alerts")
        alerts: List[Alert] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            alerts.append(Alert(
                alert_id         = a.get("alertId", 0),
                update_time      = a.get("updateTime", ""),
                start_time       = a.get("startTime", ""),
                est_clear_time   = a.get("estClearTime", ""),
                actual_clear_time= a.get("actualClearTime", ""),
                alert_type       = a.get("alertType", ""),
                priority         = a.get("priority", 0),
                source_id        = a.get("sourceId", 0),
                area_affected    = a.get("areaAffected", ""),
                title            = a.get("title", ""),
                header           = a.get("header", ""),
                message_text     = a.get("messageText", ""),
                further_info_url = a.get("furtherInfoURL", ""),
                tripcheck_only   = a.get("tripcheckOnly", ""),
                entry_time       = a.get("entryTime", ""),
                geometry_rings   = g.get("rings", []),
            ))
        return alerts

    # ------------------------------------------------------------------
    # Parking
    # ------------------------------------------------------------------

    def get_parking(self) -> List[ParkingLot]:
        """
        Return parking lot occupancy (currently only Multnomah Falls).

        Endpoint  : GET /Scripts/map/data/mfparking.js
        Cache TTL : 2 min
        Fields    : locationName, percentFull, percentFullMessage, updateTime
        iconType  : 19 = available  |  28 = full
        """
        data = self._fetch("parking")
        lots: List[ParkingLot] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            lots.append(ParkingLot(
                icon_type            = int(a.get("iconType", 0)),
                location_name        = a.get("locationName", ""),
                percent_full         = a.get("percentFull", 0),
                percent_full_message = a.get("percentFullMessage", ""),
                update_time          = a.get("updateTime", ""),
                x                    = g.get("x", 0.0),
                y                    = g.get("y", 0.0),
            ))
        return lots

    # ------------------------------------------------------------------
    # Bridge Lifts
    # ------------------------------------------------------------------

    def get_bridge_lifts(self) -> List[BridgeLift]:
        """
        Return Multnomah-area moveable bridge lift schedules/status.

        Endpoint  : GET /Scripts/map/data/multBridge.js
        Cache TTL : 2 min
        Fields    : name, isUp, lastUpdated, schedule
        iconType  : 26 = bridge up (in progress)  |  27 = bridge down (scheduled)
        """
        data = self._fetch("bridge_lifts")
        lifts: List[BridgeLift] = []
        for f in self._features(data):
            a = self._attrs(f)
            g = self._geom(f)
            lifts.append(BridgeLift(
                icon_type    = a.get("iconType", 0),
                name         = a.get("name", ""),
                is_up        = a.get("isUp", ""),
                last_updated = a.get("lastUpdated", ""),
                schedule     = a.get("schedule", ""),
                x            = g.get("x", 0.0),
                y            = g.get("y", 0.0),
            ))
        return lifts

    # ------------------------------------------------------------------
    # Waze integration
    # ------------------------------------------------------------------

    def get_waze_alerts(self) -> List[WazeAlert]:
        """
        Return crowd-sourced Waze point alerts visible on the TripCheck map.

        Endpoint  : GET /Scripts/map/data/wazeAlerts.js
        Cache TTL : 2 min
        typeId    : 1=Crash, 2=Hazard, 3=Road Closed, 4=Traffic Jam
        iconType  : 20=construction, 21=weather hazard, 22=traffic jam,
                    23=accident, 24=road closure
        """
        data = self._fetch("waze_alerts")
        wa: List[WazeAlert] = []
        for f in self._features(data):
            a = self._attrs(f)
            wa.append(WazeAlert(
                alert_id      = a.get("id", 0),
                publish_date  = a.get("publishDate", ""),
                report_date   = a.get("reportDate", ""),
                type_id       = a.get("typeId", 0),
                event_type    = a.get("eventType", ""),
                subtype_id    = a.get("subtypeId", 0),
                event_subtype = a.get("eventSubtype", ""),
                latitude      = a.get("latitude", 0.0),
                longitude     = a.get("longitude", 0.0),
                is_odot       = a.get("isOdot", 0),
                street        = a.get("street", ""),
                city          = a.get("city", ""),
                description   = a.get("description", ""),
                icon_type     = a.get("iconType", 0),
            ))
        return wa

    def get_waze_jams(self) -> List[Dict]:
        """
        Return crowd-sourced Waze traffic-jam polyline segments.

        Endpoint  : GET /Scripts/map/data/wazeJams.js
        Cache TTL : 2 min
        Key field : cngstLvl (congestion level 0-5)
        """
        data = self._fetch("waze_jams")
        return self._features(data)

    # ------------------------------------------------------------------
    # RWIS + Camera co-location  (the unique TripCheck advantage)
    # ------------------------------------------------------------------

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Return great-circle distance in km between two WGS-84 points."""
        import math
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def get_cameras_near_rwis(
        self,
        max_distance_km: float = 1.0,
    ) -> List[Dict]:
        """
        Return a list of dicts pairing each RWIS station with nearby cameras.

        This is TripCheck's unique selling point: automated weather readings
        from RWIS stations co-located with road cameras on the same highway
        segments, allowing a single data pull to show both a camera snapshot
        and current weather conditions.

        Args:
            max_distance_km: Maximum distance (km) between RWIS station and
                             camera to be considered co-located. Default 1 km.

        Returns:
            List of dicts with keys:
              - "rwis": RwisStation
              - "cameras": list of Camera objects within max_distance_km
              - "nearest_camera": closest Camera (or None)
              - "nearest_km": distance to nearest camera

        Example::
            pairs = client.get_cameras_near_rwis(max_distance_km=2.0)
            for pair in pairs:
                ws = pair["rwis"]
                if pair["nearest_camera"]:
                    cam = pair["nearest_camera"]
                    print(f"{ws.tripcheck_name}: {ws.curr_temp} road={ws.road_temp}")
                    print(f"  Camera: {cam.title}  {cam.image_url}")
        """
        stations = self.get_rwis_stations()
        cameras = self.get_cameras()

        results = []
        for ws in stations:
            nearby = []
            nearest_cam = None
            nearest_dist = float("inf")
            for cam in cameras:
                d = self._haversine_km(ws.latitude, ws.longitude, cam.latitude, cam.longitude)
                if d <= max_distance_km:
                    nearby.append(cam)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_cam = cam
            results.append({
                "rwis": ws,
                "cameras": nearby,
                "nearest_camera": nearest_cam,
                "nearest_km": round(nearest_dist, 3),
            })
        return results

    def get_rwis_with_nearby_cameras(
        self,
        max_distance_km: float = 1.0,
    ) -> List[Dict]:
        """
        Alias for get_cameras_near_rwis() — returns only RWIS stations
        that have at least one camera within max_distance_km.

        Useful for building a weather-station + camera dashboard.
        """
        return [
            pair for pair in self.get_cameras_near_rwis(max_distance_km)
            if pair["cameras"]
        ]

    def get_highway_snapshot(
        self,
        route: str,
        max_distance_km: float = 2.0,
    ) -> List[Dict]:
        """
        Return all cameras AND RWIS stations on a given highway route,
        with weather co-location.

        Args:
            route: Highway route code, e.g. "I-84", "US26", "OR217"
            max_distance_km: Co-location radius in km

        Returns:
            List of dicts each with:
              - "camera": Camera
              - "rwis": nearest RwisStation within max_distance_km (or None)
              - "rwis_km": distance to nearest RWIS in km

        Example::
            for item in client.get_highway_snapshot("I-84"):
                cam = item["camera"]
                ws = item["rwis"]
                weather = f"{ws.curr_temp} wind={ws.wind_speed}" if ws else "no RWIS nearby"
                print(f"{cam.title}: {weather}  {cam.image_url}")
        """
        cameras = [
            c for c in self.get_cameras()
            if route.strip().lower() in c.route.strip().lower()
        ]
        stations = self.get_rwis_stations()

        results = []
        for cam in cameras:
            nearest_ws = None
            nearest_dist = float("inf")
            for ws in stations:
                d = self._haversine_km(cam.latitude, cam.longitude, ws.latitude, ws.longitude)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_ws = ws
            results.append({
                "camera": cam,
                "rwis": nearest_ws if nearest_dist <= max_distance_km else None,
                "rwis_km": round(nearest_dist, 3),
            })
        return results

    # ------------------------------------------------------------------
    # Raw feed access
    # ------------------------------------------------------------------

    def get_raw(self, endpoint_key: str) -> Dict:
        """
        Return the raw EsriJSON dict for any named endpoint.

        Valid keys: see ENDPOINTS dict at module level.
        """
        if endpoint_key not in ENDPOINTS:
            raise ValueError(
                f"Unknown endpoint '{endpoint_key}'. "
                f"Valid keys: {list(ENDPOINTS.keys())}"
            )
        return self._fetch(endpoint_key)

    def flush_cache(self) -> None:
        """Clear all cached responses."""
        self._cache.clear()
        self._cache_ts.clear()


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def get_all_cameras() -> List[Camera]:
    """Quick one-liner: return all cameras."""
    return TripCheckClient().get_cameras()


def get_active_chain_restrictions() -> List[RoadWeatherReport]:
    """Quick one-liner: return reports with active chain/traction requirements."""
    return TripCheckClient().get_chain_restrictions()


def get_road_closures() -> List[RoadWeatherReport]:
    """Quick one-liner: return road closure reports."""
    return TripCheckClient().get_road_closures()


def get_active_alerts() -> List[Alert]:
    """Quick one-liner: return statewide alerts."""
    return TripCheckClient().get_alerts()


def get_rwis_camera_pairs(max_distance_km: float = 1.0) -> List[Dict]:
    """
    Quick one-liner: return RWIS stations that have a nearby camera.

    Each dict has keys: rwis (RwisStation), cameras (List[Camera]),
    nearest_camera (Camera|None), nearest_km (float).
    """
    return TripCheckClient(use_cache=True).get_rwis_with_nearby_cameras(max_distance_km)


def get_highway_conditions(route: str) -> List[Dict]:
    """
    Quick one-liner: return all cameras on a route with co-located weather data.

    Example: get_highway_conditions("I-84")
    """
    return TripCheckClient(use_cache=True).get_highway_snapshot(route)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    client = TripCheckClient(use_cache=True)

    print("=== Oregon TripCheck API Demo ===\n")

    # --- Cameras ---
    cameras = client.get_cameras()
    print(f"Cameras: {len(cameras)} total")
    if cameras:
        c = cameras[0]
        print(f"  First : {c.title}")
        print(f"  Route : {c.route}")
        print(f"  Image : {c.image_url}")
        print(f"  LDI   : {c.ldi_image_url}")
        print(f"  Video : {'yes (id=' + str(c.video_id) + ')' if c.has_video else 'no'}")

    # --- RWIS ---
    rwis = client.get_rwis_stations()
    print(f"\nRWIS stations: {len(rwis)}")
    if rwis:
        r = rwis[0]
        print(f"  Station : {r.tripcheck_name}")
        print(f"  Temp    : {r.curr_temp}")
        print(f"  Road T  : {r.road_temp}")
        print(f"  Wind    : {r.wind_speed} {r.wind_direction}")
        print(f"  Updated : {r.update_time}")

    # --- Road/weather ---
    rw = client.get_road_weather()
    print(f"\nRoad/weather reports: {len(rw)}")
    chains = client.get_chain_restrictions()
    closures = client.get_road_closures()
    print(f"  Chain/traction requirements : {len(chains)}")
    print(f"  Road closures               : {len(closures)}")
    for cr in chains[:3]:
        print(f"    [{cr.link_name}] MP {cr.link_start_mp}-{cr.link_end_mp}: {cr.chain_restriction_desc}")

    # --- Events / Incidents ---
    events = client.get_events()
    incidents = client.get_incidents()
    print(f"\nConstruction events : {len(events)}")
    print(f"Active incidents    : {len(incidents)}")

    # --- Travel times ---
    tt = client.get_travel_times()
    print(f"\nTravel time points: {len(tt)}")
    if tt:
        p = tt[0]
        print(f"  Origin: {p.location_name}")
        for route in p.routes[:2]:
            if route.travel_time > 0:
                print(f"    -> {route.destination}: {route.travel_time} min (delay: {route.delay} min)")

    # --- Alerts ---
    alerts = client.get_alerts()
    print(f"\nActive alerts: {len(alerts)}")
    for a in alerts[:3]:
        print(f"  [{a.alert_type}] {a.title}: {a.area_affected}")

    # --- Parking ---
    parking = client.get_parking()
    print(f"\nParking lots: {len(parking)}")
    for lot in parking:
        print(f"  {lot.location_name}: {lot.percent_full_message}")

    # --- Waze ---
    waze = client.get_waze_alerts()
    print(f"\nWaze alerts: {len(waze)}")
    jams = client.get_waze_jams()
    print(f"Waze traffic jams: {len(jams)}")

    # --- Videos ---
    videos = client.get_camera_videos()
    print(f"\nLive-stream cameras: {len(videos)}")
    if videos:
        v = videos[0]
        print(f"  Name    : {v.name}")
        print(f"  Full URL: {v.full_image_url}")

    # --- RWIS + Camera co-location (unique TripCheck advantage) ---
    pairs = client.get_rwis_with_nearby_cameras(max_distance_km=1.0)
    print(f"\nRWIS stations with a camera within 1 km: {len(pairs)}")
    for pair in pairs[:3]:
        ws = pair["rwis"]
        cam = pair["nearest_camera"]
        print(f"  RWIS: {ws.tripcheck_name}  temp={ws.curr_temp}  road={ws.road_temp}  wind={ws.wind_speed}")
        print(f"    -> Camera: {cam.title}  ({pair['nearest_km']} km away)")
        print(f"       {cam.image_url}")

    # --- I-84 highway snapshot ---
    i84 = client.get_highway_snapshot("I-84", max_distance_km=2.0)
    print(f"\nI-84 cameras: {len(i84)}")
    cams_with_weather = [x for x in i84 if x["rwis"]]
    print(f"  {len(cams_with_weather)} have an RWIS station within 2 km")
    for item in cams_with_weather[:2]:
        cam = item["camera"]
        ws = item["rwis"]
        print(f"  {cam.title}: {ws.curr_temp} road={ws.road_temp} wind={ws.wind_speed} ({item['rwis_km']} km)")
        print(f"    {cam.image_url}")
