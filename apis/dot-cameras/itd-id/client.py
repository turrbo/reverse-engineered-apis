"""
Idaho Transportation Department (ITD) / Idaho 511 Traffic Camera System Client

Reverse-engineered from https://511.idaho.gov by analyzing:
 - JavaScript bundles (listCctv, datatables, map511, myCctv)
 - Network requests to /List/GetData/{typeId}
 - Static developer API at /api/v2/get/*
 - WZDx (Work Zone Data Exchange) public API

Authentication:
 - Public endpoints: camera images, WZDx feed – no auth required
 - List/data endpoints: require session cookies + CSRF token obtained by
   visiting any page on 511.idaho.gov (no account needed)
 - Developer API (/api/v2/get/*): requires a registered developer key
   obtainable at https://511.idaho.gov/developers/doc

Usage:
    from itd_client import ITDClient

    client = ITDClient()
    cameras = client.get_cameras()
    for cam in cameras:
        print(cam.roadway, cam.direction, cam.location)
        img = client.get_camera_image(cam.images[0].image_id)
        with open(f"cam_{cam.camera_id}.png", "wb") as f:
            f.write(img)

    events = client.get_events()
    weather = client.get_weather_stations()
    wzdx = client.get_wzdx()

Stdlib-only – requires: urllib, json, http.cookiejar, dataclasses, re, time
"""

import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


BASE_URL = "https://511.idaho.gov"

# Rate-limit: the developer API throttles to 10 req / 60 s.
# The list/data endpoint has no documented limit but we stay polite.
DEFAULT_PAGE_SIZE = 100   # max columns length the server accepts
REQUEST_DELAY = 0.3       # seconds between paginated calls


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CameraImage:
    """One view / image associated with a camera site."""
    image_id: int
    camera_site_id: int
    sort_order: int
    description: str
    image_url: str            # e.g. "/map/Cctv/1238"  → full: BASE_URL + image_url
    image_type: int           # 0 = still, 1 = video stream
    refresh_rate_ms: int      # milliseconds between automatic refreshes (0 = unknown)
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool
    language: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CameraImage":
        return cls(
            image_id=d.get("id", 0),
            camera_site_id=d.get("cameraSiteId", 0),
            sort_order=d.get("sortOrder", 0),
            description=d.get("description", ""),
            image_url=d.get("imageUrl", ""),
            image_type=d.get("imageType", 0),
            refresh_rate_ms=d.get("refreshRateMs", 0),
            is_video_auth_required=d.get("isVideoAuthRequired", False),
            video_disabled=d.get("videoDisabled", False),
            disabled=d.get("disabled", False),
            blocked=d.get("blocked", False),
            language=d.get("language", "en"),
        )


@dataclass
class Camera:
    """A camera site (physical location) that may have multiple image views."""
    camera_id: int
    source_id: str
    source: str               # e.g. "ITDNET", "ACHD"
    roadway: str
    direction: str
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    sort_order: int
    images: List[CameraImage] = field(default_factory=list)
    state: str = ""
    county: str = ""
    region: str = ""
    visible: bool = True
    tooltip_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Camera":
        # Parse lat/lng from WKT: "POINT (-116.281 43.605)"
        lat, lng = None, None
        try:
            wkt = (d.get("latLng") or {}).get("geography", {}).get("wellKnownText", "")
            m = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", wkt)
            if m:
                lng = float(m.group(1))
                lat = float(m.group(2))
        except (TypeError, ValueError):
            pass

        images = [CameraImage.from_dict(img) for img in d.get("images", [])]

        return cls(
            camera_id=d.get("id", 0),
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            roadway=d.get("roadway", ""),
            direction=d.get("direction", ""),
            location=d.get("location", ""),
            latitude=lat,
            longitude=lng,
            sort_order=d.get("sortOrder", 0),
            images=images,
            state=d.get("state") or "",
            county=d.get("county") or "",
            region=d.get("region") or "",
            visible=d.get("visible", True),
            tooltip_url=d.get("tooltipUrl", ""),
            raw=d,
        )


@dataclass
class TrafficEvent:
    """A traffic event: incident, closure, construction, etc."""
    event_id: int
    event_type: str           # e.g. "Incidents", "Closures", "Construction"
    layer_name: str
    roadway: str
    direction: str
    description: str
    source: str
    source_id: str
    event_sub_type: str
    start_date: str
    end_date: Optional[str]
    last_updated: str
    is_full_closure: bool
    severity: str
    location_description: str
    lane_description: str
    county: str
    region: str
    state: str
    show_on_map: bool
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrafficEvent":
        return cls(
            event_id=d.get("id", 0),
            event_type=d.get("type", ""),
            layer_name=d.get("layerName", ""),
            roadway=d.get("roadwayName", ""),
            direction=d.get("direction", ""),
            description=d.get("description", ""),
            source=d.get("source", ""),
            source_id=d.get("sourceId", ""),
            event_sub_type=d.get("eventSubType", ""),
            start_date=d.get("startDate", ""),
            end_date=d.get("endDate"),
            last_updated=d.get("lastUpdated", ""),
            is_full_closure=d.get("isFullClosure", False),
            severity=d.get("severity", ""),
            location_description=d.get("locationDescription", ""),
            lane_description=d.get("laneDescription", ""),
            county=d.get("county") or "",
            region=d.get("region") or "",
            state=d.get("state") or "",
            show_on_map=d.get("showOnMap", True),
            raw=d,
        )


@dataclass
class WeatherStation:
    """A roadside weather information system (RWIS) station."""
    station_id: int
    name: str
    roadway: str
    status: str
    last_updated: str
    air_temperature: Optional[str]
    surface_temperature: Optional[str]
    wind_speed_average: Optional[str]
    wind_speed_gust: Optional[str]
    wind_direction_average: Optional[str]
    precipitation: Optional[str]
    pavement_condition: Optional[str]
    visibility: Optional[str]
    relative_humidity: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WeatherStation":
        return cls(
            station_id=d.get("id") or int(d.get("DT_RowId", 0)),
            name=d.get("name", ""),
            roadway=d.get("roadway", ""),
            status=d.get("status", ""),
            last_updated=d.get("lastUpdated", ""),
            air_temperature=d.get("airTemperature"),
            surface_temperature=d.get("surfaceTemperature"),
            wind_speed_average=d.get("windSpeedAverage"),
            wind_speed_gust=d.get("windSpeedGust"),
            wind_direction_average=d.get("windDirectionAverage"),
            precipitation=d.get("precipitation"),
            pavement_condition=d.get("pavementCondition"),
            visibility=d.get("visibility"),
            relative_humidity=d.get("relativeHumidity"),
            raw=d,
        )


@dataclass
class MessageSign:
    """A Variable Message Sign (VMS / DMS)."""
    sign_id: int
    name: str
    roadway: str
    direction: str
    description: str
    message: str
    message2: str
    status: str
    last_updated: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MessageSign":
        return cls(
            sign_id=int(d.get("DT_RowId", 0)),
            name=d.get("name", ""),
            roadway=d.get("roadwayName", ""),
            direction=d.get("direction", ""),
            description=d.get("description", ""),
            message=d.get("message", ""),
            message2=d.get("message2", ""),
            status=d.get("status", ""),
            last_updated=d.get("lastUpdated", ""),
            raw=d,
        )


@dataclass
class MountainPass:
    """A mountain pass with road condition information."""
    pass_id: int
    name: str
    location: str
    roadway: str
    elevation: str
    grade: str
    milepost: str
    last_updated: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MountainPass":
        return cls(
            pass_id=int(d.get("DT_RowId", 0)),
            name=d.get("name", ""),
            location=d.get("location", ""),
            roadway=d.get("roadway", ""),
            elevation=d.get("elevation", ""),
            grade=d.get("grade", ""),
            milepost=d.get("milepost", ""),
            last_updated=d.get("lastUpdated", ""),
            raw=d,
        )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class _Session:
    """
    Manages the HTTP session for 511.idaho.gov.

    Most data endpoints require:
      1. A session-id cookie (HttpOnly, set on any page load)
      2. A __RequestVerificationToken cookie (HttpOnly)
      3. The *same* token value sent as a request header called
         'RequestVerificationToken'

    No account login is needed.  A single GET to the homepage populates
    everything.  Token lifetime appears to be per-session (no explicit expiry).
    """

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )
        self._csrf_token: Optional[str] = None
        self._initialized = False

    def ensure_initialized(self):
        if not self._initialized:
            self._bootstrap()

    def _bootstrap(self):
        """Load the /cctv page to acquire session cookies and CSRF token."""
        req = urllib.request.Request(
            f"{BASE_URL}/cctv",
            headers={"User-Agent": self.USER_AGENT},
        )
        with self._opener.open(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # The form contains a __RequestVerificationToken hidden input whose
        # value is the same token required in the request header.
        m = re.search(
            r'name="__RequestVerificationToken"[^>]+value="([^"]+)"', html
        )
        if m:
            self._csrf_token = m.group(1)
        else:
            # Fall back to cookie value (set in addition to the form field)
            for c in self._jar:
                if c.name == "__RequestVerificationToken":
                    self._csrf_token = c.value
                    break

        self._initialized = True

    @property
    def csrf_token(self) -> str:
        self.ensure_initialized()
        return self._csrf_token or ""

    def _cookie_header(self) -> str:
        return "; ".join(
            f"{c.name}={c.value}" for c in self._jar if c.value
        )

    def get(self, url: str, *, accept: str = "application/json") -> bytes:
        """Perform a GET with session cookies + CSRF header."""
        self.ensure_initialized()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": accept,
                "X-Requested-With": "XMLHttpRequest",
                "RequestVerificationToken": self.csrf_token,
                "Cookie": self._cookie_header(),
                "Referer": f"{BASE_URL}/cctv",
            },
        )
        with self._opener.open(req, timeout=20) as resp:
            return resp.read()

    def get_json(self, url: str) -> Any:
        raw = self.get(url)
        return json.loads(raw.decode("utf-8"))

    def get_binary(self, url: str) -> bytes:
        return self.get(url, accept="image/*, */*")


# ---------------------------------------------------------------------------
# DataTables query builder
# ---------------------------------------------------------------------------

def _build_dt_query(
    columns: List[Dict],
    start: int = 0,
    length: int = DEFAULT_PAGE_SIZE,
    search: str = "",
) -> str:
    """
    Build the JSON query string expected by /List/GetData/{typeId}.

    The server receives:
        ?query=<JSON>&lang=en

    The JSON mirrors the DataTables server-side protocol, but with some
    fields stripped (draw, search.regex, column.title, column.orderable,
    column.searchable → renamed to 's') as done by the site's JS.
    """
    cols_out = []
    for col in columns:
        entry: Dict[str, Any] = {
            "name": col["name"],
        }
        if col.get("data") != col.get("name"):
            entry["data"] = col.get("data", col["name"])
        if col.get("search_value"):
            entry["search"] = {"value": col["search_value"]}
        # searchable becomes 's' (the JS renames it before sending)
        if col.get("searchable", False):
            entry["s"] = True
        cols_out.append(entry)

    order = [{"column": i, "dir": "asc"} for i in range(min(2, len(columns)))]

    payload = {
        "columns": cols_out,
        "order": order,
        "start": start,
        "length": length,
        "search": {"value": search},
    }
    return json.dumps(payload)


def _paginate_list(
    session: _Session,
    type_id: str,
    columns: List[Dict],
    max_records: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all pages from /List/GetData/{type_id}.

    Returns the combined list of raw record dicts.
    """
    results: List[Dict[str, Any]] = []
    start = 0
    total: Optional[int] = None

    while True:
        query = _build_dt_query(columns, start=start, length=DEFAULT_PAGE_SIZE)
        params = urllib.parse.urlencode({"query": query, "lang": "en"})
        url = f"{BASE_URL}/List/GetData/{type_id}?{params}"

        data = session.get_json(url)
        batch = data.get("data", [])
        results.extend(batch)

        if total is None:
            total = data.get("recordsFiltered", data.get("recordsTotal", 0))

        start += len(batch)

        if not batch:
            break
        if max_records and len(results) >= max_records:
            break
        if start >= total:
            break

        time.sleep(REQUEST_DELAY)

    return results


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class ITDClient:
    """
    Client for the Idaho 511 / Idaho Transportation Department traffic data.

    Two distinct API surfaces are covered:

    1. **Public Session API** (no account required)
       Endpoints under /List/GetData/{typeId} return paginated JSON fed to
       server-side DataTables.  A session cookie + CSRF token are obtained
       automatically on the first request.

       Available type IDs:
         Cameras          – traffic cameras (450+ sites, 1 image each typically)
         traffic          – all traffic events combined
         Incidents        – active incidents
         Closures         – road closures
         Construction     – road construction / work zones
         WeatherStations  – RWIS weather stations
         MessageSigns     – variable message signs (DMS)
         MountainPasses   – mountain pass conditions
         Advisories       – travel advisories

    2. **Developer API** (requires a registered key)
       Endpoints under /api/v2/get/{resource}?key={key}.
       Request a key at https://511.idaho.gov/developers/doc
       Rate limit: 10 requests / 60 seconds.

    3. **WZDx API** (public, no key)
       https://511.idaho.gov/api/wzdx  – GeoJSON work-zone data exchange feed.

    4. **Camera images** (public, no auth)
       https://511.idaho.gov/map/Cctv/{image_id}  → PNG image bytes.
       Default refresh interval: 60 000 ms (configurable per camera).
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Parameters
        ----------
        api_key : str, optional
            Developer API key for /api/v2/get/* endpoints.
            Obtain one at https://511.idaho.gov/developers/doc
        """
        self._session = _Session()
        self._api_key = api_key

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def get_cameras(self, max_records: Optional[int] = None) -> List[Camera]:
        """
        Return all traffic camera sites.

        Each Camera contains one or more CameraImage objects.  The image URL
        can be passed to get_camera_image() to download the current still frame.

        Parameters
        ----------
        max_records : int, optional
            Cap the number of records returned (useful for testing).

        Returns
        -------
        List[Camera]
            Sorted by sort_order then roadway name.
        """
        columns = [
            {"data": "sortOrder",  "name": "sortOrder",  "searchable": False, "orderable": True},
            {"data": "roadway",    "name": "roadway",    "searchable": True,  "orderable": True},
            {"data": "direction",  "name": "direction",  "searchable": True,  "orderable": True},
            {"data": "location",   "name": "location",   "searchable": True,  "orderable": True},
            {"data": "views",      "name": "views",      "searchable": False, "orderable": False},
        ]
        records = _paginate_list(self._session, "Cameras", columns, max_records)
        return [Camera.from_dict(r) for r in records]

    def get_camera_image(self, image_id: int) -> bytes:
        """
        Download the current still image for a camera view.

        Parameters
        ----------
        image_id : int
            The CameraImage.image_id (also the trailing segment of image_url).

        Returns
        -------
        bytes
            PNG image data.  Typically 200–800 KB.

        Notes
        -----
        This endpoint is public (no auth required).  Images are cached by
        CloudFront for up to 86 400 s but the cache-control header includes
        no-cache so a fresh request usually returns current data within the
        camera's refresh_rate_ms window.
        """
        url = f"{BASE_URL}/map/Cctv/{image_id}"
        return self._session.get_binary(url)

    def get_camera_image_url(self, image_id: int, cache_bust: bool = True) -> str:
        """
        Return the full URL for a camera image, optionally cache-busted.

        Parameters
        ----------
        image_id : int
            CameraImage.image_id.
        cache_bust : bool
            If True, append a Unix-timestamp fragment (#<ts>) so browsers
            and caches serve the latest frame (matches the JS behaviour).

        Returns
        -------
        str
        """
        url = f"{BASE_URL}/map/Cctv/{image_id}"
        if cache_bust:
            url += f"#{int(time.time())}"
        return url

    def get_camera_tooltip(self, camera_id: int, lang: str = "en") -> str:
        """
        Return the HTML tooltip content for a camera (includes image carousel
        and metadata).

        Parameters
        ----------
        camera_id : int
            Camera.camera_id.

        Returns
        -------
        str
            Raw HTML string.
        """
        url = f"{BASE_URL}/tooltip/Cameras/{camera_id}?lang={lang}&noCss=true"
        return self._session.get(url, accept="text/html").decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Traffic events
    # ------------------------------------------------------------------

    def get_events(
        self,
        event_type: str = "traffic",
        max_records: Optional[int] = None,
    ) -> List[TrafficEvent]:
        """
        Return traffic events.

        Parameters
        ----------
        event_type : str
            One of: 'traffic' (all), 'Incidents', 'Closures', 'Construction'
        max_records : int, optional

        Returns
        -------
        List[TrafficEvent]
        """
        columns = [
            {"data": "id",              "name": "id",              "searchable": True,  "orderable": True},
            {"data": "roadwayName",     "name": "roadwayName",     "searchable": True,  "orderable": True},
            {"data": "direction",       "name": "direction",       "searchable": True,  "orderable": True},
            {"data": "description",     "name": "description",     "searchable": True,  "orderable": False},
            {"data": "eventSubType",    "name": "eventSubType",    "searchable": True,  "orderable": True},
            {"data": "startDate",       "name": "startDate",       "searchable": False, "orderable": True},
            {"data": "lastUpdated",     "name": "lastUpdated",     "searchable": False, "orderable": True},
        ]
        records = _paginate_list(self._session, event_type, columns, max_records)
        return [TrafficEvent.from_dict(r) for r in records]

    def get_incidents(self, max_records: Optional[int] = None) -> List[TrafficEvent]:
        """Return active incidents only."""
        return self.get_events("Incidents", max_records)

    def get_closures(self, max_records: Optional[int] = None) -> List[TrafficEvent]:
        """Return active closures only."""
        return self.get_events("Closures", max_records)

    def get_construction(self, max_records: Optional[int] = None) -> List[TrafficEvent]:
        """Return active construction / work zones only."""
        return self.get_events("Construction", max_records)

    # ------------------------------------------------------------------
    # Weather stations
    # ------------------------------------------------------------------

    def get_weather_stations(self, max_records: Optional[int] = None) -> List[WeatherStation]:
        """
        Return all roadside weather information system (RWIS) stations.

        Returns
        -------
        List[WeatherStation]
            Includes current temperature, wind, pavement condition, etc.
        """
        columns = [
            {"data": "name",           "name": "name",           "searchable": True,  "orderable": True},
            {"data": "roadway",        "name": "roadway",        "searchable": True,  "orderable": True},
            {"data": "status",         "name": "status",         "searchable": True,  "orderable": True},
            {"data": "lastUpdated",    "name": "lastUpdated",    "searchable": False, "orderable": True},
            {"data": "airTemperature", "name": "airTemperature", "searchable": False, "orderable": True},
        ]
        records = _paginate_list(self._session, "WeatherStations", columns, max_records)
        return [WeatherStation.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Message signs
    # ------------------------------------------------------------------

    def get_message_signs(self, max_records: Optional[int] = None) -> List[MessageSign]:
        """
        Return all Variable Message Signs (VMS / DMS).

        Returns
        -------
        List[MessageSign]
            Includes current displayed message text.
        """
        columns = [
            {"data": "name",        "name": "name",        "searchable": True,  "orderable": True},
            {"data": "roadwayName", "name": "roadwayName", "searchable": True,  "orderable": True},
            {"data": "direction",   "name": "direction",   "searchable": True,  "orderable": True},
            {"data": "message",     "name": "message",     "searchable": True,  "orderable": False},
            {"data": "status",      "name": "status",      "searchable": True,  "orderable": True},
            {"data": "lastUpdated", "name": "lastUpdated", "searchable": False, "orderable": True},
        ]
        records = _paginate_list(self._session, "MessageSigns", columns, max_records)
        return [MessageSign.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Mountain passes
    # ------------------------------------------------------------------

    def get_mountain_passes(self, max_records: Optional[int] = None) -> List[MountainPass]:
        """
        Return all mountain passes with conditions.

        Returns
        -------
        List[MountainPass]
        """
        columns = [
            {"data": "name",        "name": "name",        "searchable": True,  "orderable": True},
            {"data": "roadway",     "name": "roadway",     "searchable": True,  "orderable": True},
            {"data": "lastUpdated", "name": "lastUpdated", "searchable": False, "orderable": True},
        ]
        records = _paginate_list(self._session, "MountainPasses", columns, max_records)
        return [MountainPass.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # WZDx – public, no auth needed
    # ------------------------------------------------------------------

    def get_wzdx(self) -> Dict[str, Any]:
        """
        Return the full WZDx (Work Zone Data Exchange) feed as a dict.

        This endpoint is fully public and requires no session or API key.

        Returns
        -------
        dict
            GeoJSON FeatureCollection with feed_info and features.
            Each feature contains work-zone event details including
            road names, direction, start/end dates, lane impacts, etc.

        Reference
        ---------
        https://511.idaho.gov/api/wzdx
        https://github.com/usdot-jpo-ode/wzdx
        """
        url = f"{BASE_URL}/api/wzdx"
        req = urllib.request.Request(url, headers={
            "User-Agent": _Session.USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------
    # Developer API (requires key)
    # ------------------------------------------------------------------

    def _dev_api_get(self, resource: str, fmt: str = "json") -> Any:
        """
        Call /api/v2/get/{resource}?key={key}&format={fmt}.

        Parameters
        ----------
        resource : str
            One of: cameras, roadconditions, restrictions, weatherstations,
            messagesigns, mountainpasses, events, advisories, weighstations,
            runawaytruck, restareas
        fmt : str
            'json' or 'xml'

        Raises
        ------
        ValueError
            If no API key was provided.
        urllib.error.HTTPError
            If the key is invalid (HTTP 200 with XML error body).
        """
        if not self._api_key:
            raise ValueError(
                "An API key is required for /api/v2/get/* endpoints.  "
                "Register at https://511.idaho.gov/developers/doc"
            )
        params = urllib.parse.urlencode({"key": self._api_key, "format": fmt})
        url = f"{BASE_URL}/api/v2/get/{resource}?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": _Session.USER_AGENT,
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        if raw.strip().startswith("<Error>"):
            raise ValueError(f"API error: {raw}")
        return json.loads(raw)

    def api_get_cameras(self) -> List[Dict]:
        """
        Return cameras via the developer API (/api/v2/get/cameras).

        Requires api_key.  Returns a simplified list compared to the session
        API – no image URLs, just site metadata.

        Returns
        -------
        list of dict
        """
        return self._dev_api_get("cameras")

    def api_get_events(self) -> List[Dict]:
        """Return traffic events via developer API. Requires api_key."""
        return self._dev_api_get("events")

    def api_get_road_conditions(self) -> List[Dict]:
        """Return road conditions via developer API. Requires api_key."""
        return self._dev_api_get("roadconditions")

    def api_get_restrictions(self) -> List[Dict]:
        """Return truck restrictions via developer API. Requires api_key."""
        return self._dev_api_get("restrictions")

    def api_get_weather_stations(self) -> List[Dict]:
        """Return weather stations via developer API. Requires api_key."""
        return self._dev_api_get("weatherstations")

    def api_get_message_signs(self) -> List[Dict]:
        """Return message signs via developer API. Requires api_key."""
        return self._dev_api_get("messagesigns")

    def api_get_advisories(self) -> List[Dict]:
        """Return advisories via developer API. Requires api_key."""
        return self._dev_api_get("advisories")

    # ------------------------------------------------------------------
    # Convenience / utility
    # ------------------------------------------------------------------

    def get_cameras_near(
        self,
        lat: float,
        lng: float,
        radius_km: float = 10.0,
        max_records: Optional[int] = None,
    ) -> List[Camera]:
        """
        Return cameras within ``radius_km`` kilometres of a point.

        This performs a full camera fetch and filters client-side.

        Parameters
        ----------
        lat, lng : float
            WGS-84 coordinates.
        radius_km : float
            Search radius in kilometres.
        """
        import math

        def haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (math.sin(dlat / 2) ** 2
                 + math.cos(math.radians(lat1))
                 * math.cos(math.radians(lat2))
                 * math.sin(dlon / 2) ** 2)
            return R * 2 * math.asin(math.sqrt(a))

        cameras = self.get_cameras(max_records=max_records)
        return [
            c for c in cameras
            if c.latitude is not None and c.longitude is not None
            and haversine(lat, lng, c.latitude, c.longitude) <= radius_km
        ]

    def get_cameras_on_road(self, roadway: str) -> List[Camera]:
        """
        Return cameras on a specific roadway (case-insensitive prefix match).

        Example: get_cameras_on_road("I-84")
        """
        cameras = self.get_cameras()
        rw = roadway.upper()
        return [c for c in cameras if c.roadway.upper().startswith(rw)]

    def download_camera_image(self, image_id: int, path: str) -> int:
        """
        Download a camera image and save it to ``path``.

        Returns
        -------
        int
            Number of bytes written.
        """
        data = self.get_camera_image(image_id)
        with open(path, "wb") as fh:
            fh.write(data)
        return len(data)


# ---------------------------------------------------------------------------
# CLI entry point for quick testing
# ---------------------------------------------------------------------------

def _print_table(items, attrs, headers):
    col_w = [len(h) for h in headers]
    rows = []
    for item in items:
        row = [str(getattr(item, a, "")) for a in attrs]
        rows.append(row)
        for i, v in enumerate(row):
            col_w[i] = max(col_w[i], min(len(v), 40))

    fmt = "  ".join(f"{{:<{w}.{w}}}" for w in col_w)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in col_w))
    for row in rows:
        print(fmt.format(*row))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Idaho 511 traffic data client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  cameras            List all cameras
  events             List all traffic events
  incidents          List active incidents
  closures           List active closures
  construction       List active construction
  weather            List weather stations
  signs              List message signs
  passes             List mountain passes
  wzdx               Dump WZDx feed summary
  image <image_id>   Save camera image to ./cam_<id>.png

Examples:
  python itd_client.py cameras
  python itd_client.py incidents
  python itd_client.py image 1238
        """,
    )
    parser.add_argument("command", help="Command to run")
    parser.add_argument("arg", nargs="?", help="Optional argument (e.g. image_id)")
    parser.add_argument("--key", help="Developer API key")
    parser.add_argument("-n", "--limit", type=int, default=20,
                        help="Max records to show (default: 20)")
    args = parser.parse_args()

    client = ITDClient(api_key=args.key)

    cmd = args.command.lower()

    if cmd == "cameras":
        print(f"Fetching cameras (showing first {args.limit})...")
        cams = client.get_cameras(max_records=args.limit)
        print(f"Total shown: {len(cams)}")
        _print_table(
            cams,
            ["camera_id", "roadway", "direction", "location", "source"],
            ["ID", "Roadway", "Direction", "Location", "Source"],
        )

    elif cmd in ("events", "traffic"):
        events = client.get_events("traffic", max_records=args.limit)
        print(f"Traffic events: {len(events)}")
        _print_table(
            events,
            ["event_id", "event_type", "roadway", "direction", "severity"],
            ["ID", "Type", "Roadway", "Dir", "Severity"],
        )

    elif cmd == "incidents":
        items = client.get_incidents(max_records=args.limit)
        print(f"Active incidents: {len(items)}")
        _print_table(
            items,
            ["event_id", "roadway", "direction", "event_sub_type", "lane_description"],
            ["ID", "Roadway", "Dir", "Sub-type", "Lanes"],
        )

    elif cmd == "closures":
        items = client.get_closures(max_records=args.limit)
        print(f"Active closures: {len(items)}")
        _print_table(
            items,
            ["event_id", "roadway", "direction", "location_description"],
            ["ID", "Roadway", "Dir", "Location"],
        )

    elif cmd == "construction":
        items = client.get_construction(max_records=args.limit)
        print(f"Active construction: {len(items)}")
        _print_table(
            items,
            ["event_id", "roadway", "direction", "location_description"],
            ["ID", "Roadway", "Dir", "Location"],
        )

    elif cmd in ("weather", "weatherstations"):
        items = client.get_weather_stations(max_records=args.limit)
        print(f"Weather stations: {len(items)}")
        _print_table(
            items,
            ["station_id", "name", "roadway", "air_temperature", "pavement_condition"],
            ["ID", "Name", "Roadway", "Air Temp (F)", "Pavement"],
        )

    elif cmd in ("signs", "messagesigns"):
        items = client.get_message_signs(max_records=args.limit)
        print(f"Message signs: {len(items)}")
        _print_table(
            items,
            ["sign_id", "name", "roadway", "message"],
            ["ID", "Name", "Roadway", "Message"],
        )

    elif cmd in ("passes", "mountainpasses"):
        items = client.get_mountain_passes(max_records=args.limit)
        print(f"Mountain passes: {len(items)}")
        _print_table(
            items,
            ["pass_id", "name", "roadway", "elevation", "grade"],
            ["ID", "Name", "Roadway", "Elev (ft)", "Grade %"],
        )

    elif cmd == "wzdx":
        data = client.get_wzdx()
        info = data.get("feed_info", {})
        features = data.get("features", [])
        print(f"WZDx feed")
        print(f"  Publisher   : {info.get('publisher')}")
        print(f"  Version     : {info.get('version')}")
        print(f"  Update date : {info.get('update_date')}")
        print(f"  Features    : {len(features)}")
        for feat in features[:5]:
            p = feat.get("properties", {}).get("core_details", {})
            print(f"  - {p.get('road_names')} {p.get('direction')} | {p.get('description', '')[:60]}")

    elif cmd == "image":
        if not args.arg:
            parser.error("image command requires an image_id argument")
        image_id = int(args.arg)
        path = f"cam_{image_id}.png"
        size = client.download_camera_image(image_id, path)
        print(f"Saved {size:,} bytes to {path}")

    else:
        parser.error(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
