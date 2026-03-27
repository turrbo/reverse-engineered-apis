#!/usr/bin/env python3
"""
NJDOT 511NJ Traffic Camera and Incident API Client
===================================================

A production-quality Python client (stdlib only) for the New Jersey Department of
Transportation 511NJ traffic information system at https://511nj.org.

Reverse-engineered from the 511NJ Angular SPA (main-3EVECEGS.js, camera-popup.component-5F3WZGKD.js).

Architecture notes
------------------
511NJ is an Angular 17+ SPA served from https://511nj.org (Azure CDN, HTTP/2).
All data API endpoints are relative POST/GET paths on the same origin.

Public endpoints (no auth required):
  GET  /client/getReloadVersion           Returns current app version
  GET  /assets/configs/application.json   Map/layer configuration

Authenticated endpoints (Bearer token required via /account/login):
  POST /client/get/event                  All active traffic events/incidents
  POST /client/category/get              Event category list
  POST /client/appsetting/get            App settings (encrypted, server-side)
  POST /client/basemap/get               Base map provider config
  POST /client/getStateBoundary          NJ GeoJSON state boundary
  POST /client/getTripGeom               Trip route geometry
  POST /client/getAirportRegion          Airport parking regions (EWR/JFK/LGA)
  POST /client/travellink/getLinks       Travel time link data
  POST /client/weatherwidget/getWidgetData  Weather widget data
  POST /client/dashboard/getDefaultConfiguration  Default dashboard layout
  POST /client/trafficMap/getHlsToken    HLS streaming token for a camera (body: {id: <cameraId>})
  GET  /client/getReloadVersion          App reload/version check
  POST /admin/manage/admincctvcamere/getGridData   All cameras (admin only)

Camera streaming architecture
------------------------------
Cameras are referenced by integer IDs and have different stream types:

  camera_type == "hls_skyline"
      POST /client/trafficMap/getHlsToken  {id: <cameraId>}
      Response: {hlsToken, duration, token, username, type, cameraId, camerURL, thruwayStatus}
      The token is used with an HLS player (hls.js) to load the M3U8 stream.

  camera_type == "image_skyline"
      Direct image URL is stored in camera.cameraMainDetail[0].url
      Append ?rnd=<random> to bust the CDN cache on refresh.

  camera_type == "imageproxy"
      Image is proxied via: <apiBase>/TrafficLand/getImageFromUrl?Url=<camera.url>
      (TrafficLand is a commercial video management platform.)

  camera_type == "TL_Image"  (TrafficLand)
      GET /master/camera/getTrafficlaneFullURL?id=<camera.webId>
      Response: {fullUrl, isTrafficLandDown, errorMsg, tokenTimeoutSecond}
      fullUrl is the JPEG still-refresh URL; append &rnd=<random> on each poll.

Camera data model (from cameraMainDetail array):
  camera_id          int
  camera_type        str  ("hls_skyline" | "image_skyline" | "imageproxy" | "TL_Image")
  camera_use_flag    str  ("Y" / "N")
  image_refresh_rate int  (seconds)
  priority           int
  url                str  (raw camera URL or HLS playlist URL)
  web_id             int  (TrafficLand webId, if applicable)

Event data model (from /client/get/event):
  eventId            int
  name               str
  categoryId         int  (1=Incident, 2=Construction, 3=Special, 4=Weather, 5=Detour, 6=Congestion)
  sortOrder          int
  state              str  ("NJ")
  lastUpdateDate     str  (ISO datetime)
  iconFile           str  (icon filename, e.g. "incident.svg")
  latitude           float
  longitude          float
  ... (additional fields returned by server)

Authentication
--------------
The API uses Bearer token authentication. Tokens are obtained via POST /account/login
with AES-encrypted credentials (key "lIo3M)_83,ALC0Wz", IV ".%A}8Qvqm23jYVc9", CBC/PKCS7).
The token is placed in Authorization: Token <accessToken> header.
Some endpoints with sensitive responses have their request body AES-encrypted by the
Angular HTTP interceptor before sending.

Note: This client demonstrates the *unauthenticated* public endpoints and documents
the full authenticated API surface. To use authenticated endpoints, supply a valid
access token obtained from /account/login.

Usage
-----
    python3 njdot_client.py                   # Run the CLI demo
    python3 njdot_client.py --all             # Fetch all available public data
    python3 njdot_client.py --version         # Print app version only

    # As a library:
    from njdot_client import NJDOTClient
    client = NJDOTClient()
    version = client.get_reload_version()
    config  = client.get_app_config()

Dependencies: Python 3.8+ (stdlib only — urllib, json, dataclasses, argparse)
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://511nj.org"
APP_CONFIG_URL = f"{BASE_URL}/assets/configs/application.json"
DEFAULT_TIMEOUT = 15  # seconds
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Event category mapping
EVENT_CATEGORIES: Dict[int, str] = {
    1: "Incident",
    2: "Construction",
    3: "Special Event",
    4: "Weather",
    5: "Detour",
    6: "Congestion",
    7: "Scheduled Construction",
    8: "Scheduled Special Event",
}

# Camera type constants
CAMERA_TYPE_HLS = "hls_skyline"
CAMERA_TYPE_IMAGE = "image_skyline"
CAMERA_TYPE_IMAGEPROXY = "imageproxy"
CAMERA_TYPE_TRAFFICLAND = "TL_Image"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AppVersion:
    """Application reload version response."""
    id: int
    key: str
    value: str
    description: str
    config_mode: str
    parent_key: str

    @classmethod
    def from_dict(cls, d: dict) -> "AppVersion":
        return cls(
            id=d.get("id", 0),
            key=d.get("key", ""),
            value=d.get("value", "").strip('"'),
            description=d.get("description", ""),
            config_mode=d.get("configMode", ""),
            parent_key=d.get("parentKey", ""),
        )


@dataclass
class MapSettings:
    """Map configuration from application.json."""
    min_zoom: int
    max_zoom: int
    max_extent: List[float]
    center_lon_lat: List[float]
    default_zoom: float
    event_zoom: int
    event_blink_interval_ms: int

    @classmethod
    def from_dict(cls, d: dict) -> "MapSettings":
        return cls(
            min_zoom=d.get("minZoomLevel", 6),
            max_zoom=d.get("maxZoomLevel", 18),
            max_extent=d.get("maxExtent", []),
            center_lon_lat=d.get("centerLonLat", [-74.728565, 40.08453865579841]),
            default_zoom=d.get("defaultZoom", 7.6),
            event_zoom=d.get("EventZoom", 14),
            event_blink_interval_ms=d.get("EventBlinkInterval", 1000),
        )


@dataclass
class AppConfig:
    """
    Application configuration parsed from /assets/configs/application.json.

    This is the public map/layer configuration. The server-side settings
    (apiUrl, encryption keys, etc.) are loaded separately via /client/appsetting/get
    and require authentication.
    """
    refresh_interval_ms: int
    refresh_tile_specific_ms: int
    rc_string: str
    tt_not_avail_string: str
    page_id: Dict[str, int]
    map_settings: MapSettings
    layers: Dict[str, Any]
    camera_popup: Dict[str, Any]
    event_popup: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        return cls(
            refresh_interval_ms=d.get("NextRefreshInMilliSeconds", 120000),
            refresh_tile_specific_ms=d.get("NextRefreshInMilliSecondsTileSpecific", 30000),
            rc_string=d.get("RCString", "RC"),
            tt_not_avail_string=d.get("TTNotAvailString", "Unavail."),
            page_id=d.get("pageId", {}),
            map_settings=MapSettings.from_dict(d.get("mapSettings", {})),
            layers=d.get("layers", {}),
            camera_popup=d.get("cameraPopup", {}),
            event_popup=d.get("eventPopup", {}),
            raw=d,
        )


@dataclass
class CameraDetail:
    """
    One record from the cameraMainDetail array attached to a camera.
    This contains the stream type and URL for displaying the camera.
    """
    camera_id: int
    camera_type: str
    camera_use_flag: str
    image_refresh_rate: int
    priority: int
    url: str
    web_id: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "CameraDetail":
        return cls(
            camera_id=d.get("camera_id", d.get("cameraId", 0)),
            camera_type=d.get("camera_type", d.get("cameraType", "")),
            camera_use_flag=d.get("camera_use_flag", d.get("cameraUseFlag", "")),
            image_refresh_rate=d.get("image_refresh_rate", d.get("imageRefreshRate", 0)),
            priority=d.get("priority", 0),
            url=d.get("url", ""),
            web_id=d.get("web_id", d.get("webId", None)),
        )

    @property
    def is_active(self) -> bool:
        """Whether this camera feed is marked as active/usable."""
        return self.camera_use_flag.upper() in ("Y", "YES", "1", "TRUE", "ACTIVE")

    @property
    def stream_type(self) -> str:
        """Normalized stream type string."""
        return self.camera_type.lower()

    def get_direct_image_url(self, api_base: str = BASE_URL) -> Optional[str]:
        """
        Return a URL that yields a JPEG still image, or None if the stream
        type does not support direct still image access without a token.

        For hls_skyline cameras, use NJDOTClient.get_hls_token() instead.
        For TL_Image cameras, use NJDOTClient.get_trafficland_url() instead.
        """
        t = self.stream_type
        if t == CAMERA_TYPE_IMAGE.lower() and self.url:
            # Append cache-busting parameter
            return f"{self.url}?rnd={int(time.time())}"
        if t == CAMERA_TYPE_IMAGEPROXY.lower() and self.url:
            return f"{api_base}/TrafficLand/getImageFromUrl?Url={self.url}?rnd={int(time.time())}"
        return None


@dataclass
class Camera:
    """
    Traffic camera record returned by /admin/manage/admincctvcamere/getGridData
    (admin) or the camera tile system.

    Fields align with the NJ DOT CCTV database structure.
    """
    id: int
    name: str
    latitude: str
    longitude: str
    icon_file: str
    stop_camera_flag: bool
    tour_id: int
    tour_name: str
    camera_main_detail: List[CameraDetail]
    device_description: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        details = [
            CameraDetail.from_dict(cd)
            for cd in (d.get("cameraMainDetail") or [])
        ]
        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            latitude=str(d.get("latitude", "")),
            longitude=str(d.get("longitude", "")),
            icon_file=d.get("iconFile", ""),
            stop_camera_flag=bool(d.get("stopCameraFlag", False)),
            tour_id=d.get("tourId", 0),
            tour_name=d.get("tourName", ""),
            camera_main_detail=details,
            device_description=d.get("deviceDescription"),
            raw=d,
        )

    @property
    def primary_detail(self) -> Optional[CameraDetail]:
        """Return the first (highest priority) camera detail record, if any."""
        if self.camera_main_detail:
            return self.camera_main_detail[0]
        return None

    @property
    def is_operational(self) -> bool:
        """Whether the camera is not flagged as stopped."""
        return not self.stop_camera_flag

    @property
    def lat(self) -> Optional[float]:
        """Numeric latitude, or None if not set."""
        try:
            return float(self.latitude)
        except (ValueError, TypeError):
            return None

    @property
    def lon(self) -> Optional[float]:
        """Numeric longitude, or None if not set."""
        try:
            return float(self.longitude)
        except (ValueError, TypeError):
            return None


@dataclass
class Event:
    """
    Traffic event/incident returned by POST /client/get/event.
    Covers incidents, construction, weather, detours, congestion, etc.
    """
    event_id: int
    name: str
    category_id: int
    sort_order: int
    state: str
    last_update_date: str
    icon_file: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    is_schedule_event: bool = False
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            event_id=d.get("eventId", 0),
            name=d.get("name", ""),
            category_id=d.get("categoryId", 0),
            sort_order=d.get("sortOrder", 0),
            state=d.get("state", ""),
            last_update_date=d.get("lastUpdateDate", ""),
            icon_file=d.get("iconFile", ""),
            latitude=_to_float(d.get("latitude")),
            longitude=_to_float(d.get("longitude")),
            description=d.get("description"),
            is_schedule_event=bool(d.get("isScheduleEvent", False)),
            raw=d,
        )

    @property
    def category_name(self) -> str:
        """Human-readable event category."""
        return EVENT_CATEGORIES.get(self.category_id, f"Category {self.category_id}")


@dataclass
class HLSToken:
    """
    Response from POST /client/trafficMap/getHlsToken.
    Used to authenticate an HLS camera stream.
    """
    hls_token: str
    duration: int
    token: str
    username: str
    stream_type: str
    camera_id: int
    camera_url: str
    thruway_status: str

    @classmethod
    def from_dict(cls, d: dict) -> "HLSToken":
        return cls(
            hls_token=d.get("hlsToken", ""),
            duration=d.get("duration", 0),
            token=d.get("token", ""),
            username=d.get("username", ""),
            stream_type=d.get("type", ""),
            camera_id=d.get("cameraId", 0),
            camera_url=d.get("camerURL", ""),
            thruway_status=d.get("thruwayStatus", ""),
        )


@dataclass
class TrafficLandURL:
    """
    Response from GET /master/camera/getTrafficlaneFullURL?id=<webId>.
    Returns the authenticated TrafficLand still-image URL.
    """
    full_url: str
    is_down: bool
    error_msg: str
    token_timeout_seconds: int

    @classmethod
    def from_dict(cls, d: dict) -> "TrafficLandURL":
        return cls(
            full_url=d.get("fullUrl", ""),
            is_down=bool(d.get("isTrafficLandDown", False)),
            error_msg=d.get("errorMsg", ""),
            token_timeout_seconds=int(d.get("tokenTimeoutSecond", 0) or 0),
        )


@dataclass
class TravelLink:
    """A travel time link (road segment with travel-time data)."""
    id: int
    name: str
    normal_time: Optional[int] = None
    current_time: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "TravelLink":
        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            normal_time=d.get("normalTime") or d.get("normal_time"),
            current_time=d.get("currentTime") or d.get("current_time"),
            raw=d,
        )


@dataclass
class APIResponse:
    """
    Generic wrapper for the 511NJ API envelope.

    All endpoints return JSON in the form::

        {
          "errorId": "",
          "exceptions": null,
          "data": <payload>,
          "status": 200
        }

    A ``status`` of 401 means the endpoint requires authentication.
    """
    error_id: str
    exceptions: Any
    data: Any
    status: int

    @classmethod
    def from_dict(cls, d: dict) -> "APIResponse":
        return cls(
            error_id=d.get("errorId", ""),
            exceptions=d.get("exceptions"),
            data=d.get("data"),
            status=d.get("status", 0),
        )

    @property
    def ok(self) -> bool:
        return self.status == 200

    @property
    def requires_auth(self) -> bool:
        return self.status == 401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(v: Any) -> Optional[float]:
    """Coerce a value to float, returning None on failure."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _make_ssl_context() -> ssl.SSLContext:
    """Return a permissive SSL context that verifies certificates."""
    ctx = ssl.create_default_context()
    return ctx


# ---------------------------------------------------------------------------
# Core HTTP client
# ---------------------------------------------------------------------------


class NJDOTClient:
    """
    Python client for the 511NJ traffic information API.

    All public-facing (no-auth) endpoints are exposed as methods.
    Authenticated endpoints are documented but require a valid token.

    Parameters
    ----------
    base_url:
        Base URL of the 511NJ API (default: ``https://511nj.org``).
    auth_token:
        Bearer access token from ``/account/login``. Required for data endpoints.
        Pass ``None`` (default) to use only public endpoints.
    timeout:
        HTTP request timeout in seconds (default: 15).
    user_agent:
        User-Agent header string.

    Examples
    --------
    >>> client = NJDOTClient()
    >>> version = client.get_reload_version()
    >>> print(version.value)
    '91'

    >>> config = client.get_app_config()
    >>> print(config.map_settings.center_lon_lat)
    [-74.728565, 40.08453865579841]
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        auth_token: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self.user_agent = user_agent
        self._ssl_ctx = _make_ssl_context()

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build common request headers."""
        h: Dict[str, str] = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        if self.auth_token:
            h["Authorization"] = f"Token {self.auth_token}"
        if extra:
            h.update(extra)
        return h

    def _get(self, path: str) -> Any:
        """
        Execute a GET request and return the parsed JSON body.

        Raises
        ------
        urllib.error.HTTPError
            On 4xx/5xx responses that are not handled as JSON.
        urllib.error.URLError
            On network-level failures.
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=self.timeout) as resp:
            raw = resp.read()
            return json.loads(raw)

    def _post(self, path: str, body: Any = None) -> Any:
        """
        Execute a POST request with a JSON body and return the parsed JSON response.

        Parameters
        ----------
        path:
            API path relative to ``base_url`` (e.g. ``/client/get/event``).
        body:
            Python object to JSON-serialise as the request body.
            Pass ``None`` to send a null JSON body.

        Returns
        -------
        Any
            Parsed JSON response.
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        encoded = json.dumps(body).encode("utf-8") if body is not None else b"null"
        headers = self._headers({"Content-Type": "application/json"})
        req = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=self.timeout) as resp:
            raw = resp.read()
            return json.loads(raw)

    # ------------------------------------------------------------------
    # Public endpoints (no authentication required)
    # ------------------------------------------------------------------

    def get_reload_version(self) -> AppVersion:
        """
        GET /client/getReloadVersion

        Returns the application reload version. This is the only data endpoint
        that does not require authentication.

        Returns
        -------
        AppVersion
            The current application version record.

        Examples
        --------
        >>> v = client.get_reload_version()
        >>> print(v.value)
        '91'
        """
        data = self._get("/client/getReloadVersion")
        resp = APIResponse.from_dict(data)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status}: {resp.data}")
        return AppVersion.from_dict(resp.data)

    def get_app_config(self) -> AppConfig:
        """
        GET /assets/configs/application.json

        Returns the static application configuration that drives the map UI.
        This includes:
        - Map center coordinates and zoom levels for New Jersey
        - Layer definitions (cameras, events, speed, parking, etc.)
        - Refresh intervals (events: 120 s, tiles: 30 s)
        - Camera popup configuration

        Returns
        -------
        AppConfig
            Parsed application configuration.
        """
        data = self._get("/assets/configs/application.json")
        return AppConfig.from_dict(data)

    # ------------------------------------------------------------------
    # Authenticated data endpoints
    # ------------------------------------------------------------------
    # These endpoints require a valid Bearer token from /account/login.
    # They are documented with full request/response structure for
    # completeness and for use when credentials are available.

    def get_events(self, include_scheduled: bool = True) -> List[Event]:
        """
        POST /client/get/event  (requires auth)

        Returns all active traffic events including incidents, construction,
        special events, weather, detours, and congestion.

        This is the primary live-traffic feed for the 511NJ system and covers
        all of New Jersey including NJ Turnpike, Garden State Parkway, and
        state routes.

        Parameters
        ----------
        include_scheduled:
            Whether to include scheduled future events (default: True).

        Returns
        -------
        list[Event]
            Active traffic events sorted by category and last-update time.

        Raises
        ------
        RuntimeError
            If the API returns status 401 (auth required) or another error.

        Request body
        ------------
        ``{"isScheduleEvent": true}``

        Response shape
        --------------
        ::

            [
              {
                "eventId": 12345,
                "name": "Accident - I-95 NB at Exit 8",
                "categoryId": 1,
                "sortOrder": 10,
                "state": "NJ",
                "lastUpdateDate": "2026-03-27T14:30:00",
                "iconFile": "incident.svg",
                "latitude": 40.1234,
                "longitude": -74.5678,
                ...
              },
              ...
            ]
        """
        if not self.auth_token:
            raise RuntimeError(
                "Authentication required for /client/get/event. "
                "Provide auth_token when creating NJDOTClient."
            )
        body = {"isScheduleEvent": include_scheduled}
        raw = self._post("/client/get/event", body)
        # The response may be a direct array (not wrapped) or a wrapped object
        if isinstance(raw, list):
            return [Event.from_dict(e) for e in raw]
        resp = APIResponse.from_dict(raw)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status}: {resp.data}")
        return [Event.from_dict(e) for e in (resp.data or [])]

    def get_hls_token(self, camera_id: int) -> HLSToken:
        """
        POST /client/trafficMap/getHlsToken  (requires auth)

        Fetches an HLS streaming token for a camera of type ``hls_skyline``
        or ``hls`` (Skyline Networks cameras used by NJDOT).

        The returned ``camera_url`` is an HLS (.m3u8) manifest URL. Use a
        CORS-capable HLS player (e.g. hls.js) to play it.

        Parameters
        ----------
        camera_id:
            The integer camera ID.

        Returns
        -------
        HLSToken
            Token data including the stream URL.

        Request body
        ------------
        ``{"id": <camera_id>}``

        Response shape
        --------------
        ::

            {
              "hlsToken": "eyJ...",
              "duration": 3600,
              "token": "abc123",
              "username": "viewer",
              "type": "hls_skyline",
              "cameraId": 42,
              "camerURL": "https://skyline.example.com/live/cam42.m3u8",
              "thruwayStatus": ""
            }
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/trafficMap/getHlsToken.")
        raw = self._post("/client/trafficMap/getHlsToken", {"id": camera_id})
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return HLSToken.from_dict(resp.data or {})
        return HLSToken.from_dict(raw if isinstance(raw, dict) else {})

    def get_trafficland_url(self, web_id: int) -> TrafficLandURL:
        """
        GET /master/camera/getTrafficlaneFullURL  (requires auth)

        Fetches a signed still-image URL for a TrafficLand (TL_Image) camera.
        These are typically NJ Turnpike Authority cameras managed by the
        TrafficLand video management platform.

        Parameters
        ----------
        web_id:
            The TrafficLand webId stored in ``CameraDetail.web_id``.

        Returns
        -------
        TrafficLandURL
            Signed image URL and token expiry information.

        Query string
        ------------
        ``?id=<web_id>``

        Response shape
        --------------
        ::

            {
              "fullUrl": "https://cdn.trafficland.com/cam123/still.jpg?token=...",
              "isTrafficLandDown": false,
              "errorMsg": "",
              "tokenTimeoutSecond": 300
            }
        """
        raw = self._get(f"/master/camera/getTrafficlaneFullURL?id={web_id}")
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return TrafficLandURL.from_dict(resp.data or {})
        return TrafficLandURL.from_dict(raw if isinstance(raw, dict) else {})

    def get_travel_links(self) -> List[TravelLink]:
        """
        POST /client/travellink/getLinks  (requires auth)

        Returns travel-time data for monitored road segments.
        Covers major NJ corridors including NJ Turnpike, Garden State Parkway,
        and arterial routes.

        Returns
        -------
        list[TravelLink]
            Travel-time link records.

        Request body
        ------------
        (empty / null)

        Response shape
        --------------
        ::

            [
              {
                "id": 101,
                "name": "NJ Turnpike NB Exit 8 to Exit 9",
                "normalTime": 12,
                "currentTime": 18
              },
              ...
            ]
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/travellink/getLinks.")
        raw = self._post("/client/travellink/getLinks", None)
        if isinstance(raw, list):
            return [TravelLink.from_dict(t) for t in raw]
        resp = APIResponse.from_dict(raw)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status}: {resp.data}")
        return [TravelLink.from_dict(t) for t in (resp.data or [])]

    def get_state_boundary(self, params: Optional[dict] = None) -> dict:
        """
        POST /client/getStateBoundary  (requires auth)

        Returns GeoJSON geometry for the New Jersey state boundary.
        Used by the map layer to display the state outline.

        Parameters
        ----------
        params:
            Optional filter parameters (consult server schema).

        Returns
        -------
        dict
            GeoJSON or boundary data from the server.
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/getStateBoundary.")
        raw = self._post("/client/getStateBoundary", params or {})
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return resp.data or {}
        return raw

    def get_cameras_admin(self) -> List[Camera]:
        """
        POST /admin/manage/admincctvcamere/getGridData  (admin auth required)

        Returns all cameras in the system with full detail including stream URLs.
        Requires an administrator-level access token.

        Returns
        -------
        list[Camera]
            All CCTV cameras with name, coordinates, and stream detail.

        Response shape
        --------------
        ::

            [
              {
                "id": 42,
                "name": "I-295 NB at CR 656",
                "latitude": "39.9234",
                "longitude": "-75.0123",
                "iconFile": "cctv-green.png",
                "stopCameraFlag": false,
                "tourId": 3,
                "tourName": "NJDOT Main Tour",
                "cameraMainDetail": [
                  {
                    "camera_id": 42,
                    "camera_type": "hls_skyline",
                    "camera_use_flag": "Y",
                    "image_refresh_rate": 0,
                    "priority": 1,
                    "url": "https://skyline.njdot.gov/live/cam42.m3u8",
                    "web_id": null
                  }
                ],
                "deviceDescription": null
              },
              ...
            ]
        """
        if not self.auth_token:
            raise RuntimeError(
                "Admin authentication required for /admin/manage/admincctvcamere/getGridData."
            )
        raw = self._post("/admin/manage/admincctvcamere/getGridData", {})
        if isinstance(raw, list):
            return [Camera.from_dict(c) for c in raw]
        resp = APIResponse.from_dict(raw)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status}: {resp.data}")
        return [Camera.from_dict(c) for c in (resp.data or [])]

    def get_app_settings(self) -> dict:
        """
        POST /client/appsetting/get  (requires auth)

        Returns server-side application settings. Values are stored encrypted
        in the database and decrypted by the server before responding.

        Key settings include:
        - ``apiUrl``         Backend API base URL
        - ``baseMapURL``     Basemap tile service URL
        - ``role``           User role
        - ``switchToElfsight``  Feature flags
        - ``maxCamerasAllowsInCameraTile``  Max cameras per tile widget

        Returns
        -------
        dict
            Parsed settings key-value map.
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/appsetting/get.")
        raw = self._post("/client/appsetting/get", None)
        resp = APIResponse.from_dict(raw)
        if not resp.ok:
            raise RuntimeError(f"API error {resp.status}: {resp.data}")
        return resp.data or {}

    def get_dashboard_config(self) -> dict:
        """
        POST /client/dashboard/getDefaultConfiguration  (requires auth)

        Returns the default dashboard tile layout configuration.

        Returns
        -------
        dict
            Dashboard configuration data.
        """
        if not self.auth_token:
            raise RuntimeError(
                "Authentication required for /client/dashboard/getDefaultConfiguration."
            )
        raw = self._post("/client/dashboard/getDefaultConfiguration", {})
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return resp.data or {}
        return raw

    def get_weather_widget(self, params: Optional[dict] = None) -> dict:
        """
        POST /client/weatherwidget/getWidgetData  (requires auth)

        Returns weather widget data for the map display.

        Parameters
        ----------
        params:
            Optional filter parameters.

        Returns
        -------
        dict
            Weather widget data.
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/weatherwidget/getWidgetData.")
        raw = self._post("/client/weatherwidget/getWidgetData", params)
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return resp.data or {}
        return raw

    def get_airport_regions(self) -> dict:
        """
        POST /client/getAirportRegion  (requires auth)

        Returns geographic regions for NJ-area airports (EWR, JFK, LGA).
        Used for the parking availability display.

        Returns
        -------
        dict
            Airport region geometries and parking data.
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/getAirportRegion.")
        raw = self._post("/client/getAirportRegion", {})
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return resp.data or {}
        return raw

    def get_trip_geometry(self, params: Optional[dict] = None) -> dict:
        """
        POST /client/getTripGeom  (requires auth)

        Returns geometric route data for popular travel links.

        Parameters
        ----------
        params:
            Optional route filter parameters.

        Returns
        -------
        dict
            Trip geometry (GeoJSON linestring data).
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/getTripGeom.")
        raw = self._post("/client/getTripGeom", params or {})
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return resp.data or {}
        return raw

    def get_event_popup(self, event_id: int) -> dict:
        """
        POST /client/get/getEventPopupData  (requires auth)

        Fetches the detailed popup data for a single traffic event.

        Parameters
        ----------
        event_id:
            The integer event ID from the events list.

        Returns
        -------
        dict
            Event detail fields for the map popup panel.
        """
        if not self.auth_token:
            raise RuntimeError("Authentication required for /client/get/getEventPopupData.")
        raw = self._post("/client/get/getEventPopupData", {"eventId": event_id})
        if isinstance(raw, dict) and "status" in raw:
            resp = APIResponse.from_dict(raw)
            if not resp.ok:
                raise RuntimeError(f"API error {resp.status}: {resp.data}")
            return resp.data or {}
        return raw

    # ------------------------------------------------------------------
    # Convenience / CDN helpers
    # ------------------------------------------------------------------

    def get_camera_image_url(
        self,
        camera: Camera,
        cache_bust: bool = True,
    ) -> Optional[str]:
        """
        Derive the best available still-image URL for a camera, without
        making additional API calls.

        Works for ``image_skyline`` and ``imageproxy`` cameras only.
        For ``hls_skyline`` cameras, call ``get_hls_token()``.
        For ``TL_Image`` cameras, call ``get_trafficland_url()``.

        Parameters
        ----------
        camera:
            The camera object.
        cache_bust:
            Append a ``?rnd=<epoch>`` query parameter (default: True).

        Returns
        -------
        str or None
            A URL string, or ``None`` if not derivable without an API call.
        """
        detail = camera.primary_detail
        if not detail:
            return None
        return detail.get_direct_image_url(self.base_url)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------


def _print_divider(title: str) -> None:
    width = 72
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def _print_json(obj: Any, indent: int = 2) -> None:
    """Print a dataclass or dict as pretty JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        print(json.dumps(asdict(obj), indent=indent, default=str))
    else:
        print(json.dumps(obj, indent=indent, default=str))


def run_demo(args: argparse.Namespace) -> None:
    """CLI entry point: demonstrate all public endpoints and document all others."""
    client = NJDOTClient(
        auth_token=args.token if hasattr(args, "token") else None,
    )

    # ------------------------------------------------------------------
    # 1. App Version (public, no auth)
    # ------------------------------------------------------------------
    _print_divider("1. Application Version  [GET /client/getReloadVersion]")
    try:
        v = client.get_reload_version()
        print(f"  Current version : {v.value}")
        print(f"  Config mode     : {v.config_mode}")
        print(f"  Description     : {v.description}")
        if args.verbose:
            _print_json(v)
    except Exception as e:
        print(f"  ERROR: {e}")

    # ------------------------------------------------------------------
    # 2. Application Config (public, no auth)
    # ------------------------------------------------------------------
    _print_divider("2. App Configuration  [GET /assets/configs/application.json]")
    try:
        cfg = client.get_app_config()
        ms = cfg.map_settings
        print(f"  NJ map centre   : lon={ms.center_lon_lat[0]}, lat={ms.center_lon_lat[1]}")
        print(f"  Zoom range      : {ms.min_zoom} – {ms.max_zoom}  (default {ms.default_zoom:.2f})")
        print(f"  Event refresh   : {cfg.refresh_interval_ms // 1000} s")
        print(f"  Tile refresh    : {cfg.refresh_tile_specific_ms // 1000} s")
        print(f"  Defined layers  : {', '.join(cfg.layers.keys())}")
        print(f"  Camera popup zoom : {cfg.camera_popup.get('zoomLevel', 'N/A')}")
        if args.verbose:
            _print_json(cfg)
    except Exception as e:
        print(f"  ERROR: {e}")

    # ------------------------------------------------------------------
    # 3. Authenticated endpoints summary
    # ------------------------------------------------------------------
    _print_divider("3. Authenticated API Endpoints (require Bearer token)")
    auth_endpoints = [
        ("POST", "/client/get/event",
         "Active incidents, construction, weather, detours, congestion"),
        ("POST", "/client/category/get",
         "Event category list"),
        ("POST", "/client/appsetting/get",
         "Server-side app settings (apiUrl, baseMapURL, etc.)"),
        ("POST", "/client/basemap/get",
         "Base map tile provider configuration"),
        ("POST", "/client/getStateBoundary",
         "NJ GeoJSON state boundary"),
        ("POST", "/client/getTripGeom",
         "Popular trip route geometries"),
        ("POST", "/client/getAirportRegion",
         "EWR / JFK / LGA airport parking regions"),
        ("POST", "/client/travellink/getLinks",
         "Travel-time data for NJ road segments"),
        ("POST", "/client/weatherwidget/getWidgetData",
         "Weather widget data for map overlay"),
        ("POST", "/client/dashboard/getDefaultConfiguration",
         "Default dashboard tile layout"),
        ("POST", "/client/trafficMap/getHlsToken",
         "HLS stream token for a camera (body: {id: <cameraId>})"),
        ("GET",  "/client/getAirportRegion",
         "Airport region (alternate)"),
        ("POST", "/client/get/getEventPopupData",
         "Detailed popup for a single event (body: {eventId: N})"),
        ("POST", "/client/camera/insertCameraErrorLog",
         "Log a camera load error (client telemetry)"),
        ("GET",  "/master/camera/getTrafficlaneFullURL",
         "Signed TrafficLand still-image URL (?id=<webId>)"),
        ("GET",  "/CCTV/getThruwayStatus",
         "NY Thruway camera status (?CameraId=<id>)"),
        ("GET",  "/api/v1/CCTV/getThruwayStatus",
         "NY Thruway camera status v1 (?Id=<id>)"),
        ("GET",  "/TrafficLand/getImageFromUrl",
         "TrafficLand image proxy (?Url=<encoded_url>)"),
    ]
    for method, path, description in auth_endpoints:
        print(f"  {method:4s}  {path:<52}  {description}")

    # ------------------------------------------------------------------
    # 4. Admin endpoints (admin token required)
    # ------------------------------------------------------------------
    _print_divider("4. Admin-Only Endpoints (admin Bearer token required)")
    admin_endpoints = [
        ("POST", "/admin/manage/admincctvcamere/getGridData",
         "All CCTV cameras with stream type and URL"),
        ("POST", "/admin/manage/admincctvcamere/savecameradata",
         "Create or update a camera record"),
        ("POST", "/admin/manage/admincctvcamere/generateCCTVReport",
         "Export camera report"),
        ("POST", "/admin/manage/sectortripmapping/getGridData",
         "Trip-to-sector mapping"),
        ("POST", "/admin/manage/travellink/getForGrid",
         "Travel links admin list"),
        ("POST", "/admin/manage/alert/getGridData",
         "System alerts management"),
        ("POST", "/admin/manage/eventtype/getForGrid",
         "Event type definitions"),
        ("POST", "/admin/manage/floodgate/getGridData",
         "Flood-gate (roadway restriction) records"),
        ("POST", "/admin/roleMenuMapping/getMenuData",
         "Role-based menu/permission map"),
        ("POST", "/admin/segment/getGridData",
         "Road segment definitions"),
        ("POST", "/admin/report/getGAReport",
         "Google Analytics usage report"),
        ("POST", "/admin/report/getPOIList",
         "Points of interest for reporting"),
        ("POST", "/admin/tool/closeincident/getGridData",
         "Manually closeable incidents"),
        ("POST", "/admin/dashboard/admindashboard/getEventStatistics",
         "Event statistics for admin dashboard"),
        ("POST", "/admin/dashboard/admindashboard/getGeneralStatistics",
         "General system statistics"),
        ("POST", "/admin/ptsprofile/profile/getGridData",
         "PTS alert profiles list"),
        ("POST", "/admin/megaproject/getRecord",
         "Mega-project (major construction) records"),
        ("POST", "/admin/files/getLists",
         "File/asset manager listing"),
    ]
    for method, path, description in admin_endpoints:
        print(f"  {method:4s}  {path:<52}  {description}")

    # ------------------------------------------------------------------
    # 5. Camera streaming architecture
    # ------------------------------------------------------------------
    _print_divider("5. Camera Stream Types and How to Access Them")
    print("""
  Camera type       How to get the stream / image
  ─────────────────────────────────────────────────────────────────────
  hls_skyline       POST /client/trafficMap/getHlsToken  {id: <cameraId>}
                    Response.camerURL → HLS .m3u8 playlist
                    Load with hls.js or a native HLS-capable player.

  image_skyline     camera.cameraMainDetail[0].url is a direct JPEG URL.
                    Append ?rnd=<epoch> to defeat CDN caching.
                    Refresh at image_refresh_rate-second intervals.

  imageproxy        Proxy via:
                    GET /TrafficLand/getImageFromUrl?Url=<encoded_cam_url>
                    The server fetches the image from a private upstream CDN.

  TL_Image          GET /master/camera/getTrafficlaneFullURL?id=<webId>
  (TrafficLand)     Response.fullUrl → signed JPEG URL (expires in
                    tokenTimeoutSecond seconds). Append &rnd=<epoch>.
                    Token refresh: repeat call before expiry.
    """)

    # ------------------------------------------------------------------
    # 6. Example: if auth_token is provided, fetch live data
    # ------------------------------------------------------------------
    if client.auth_token:
        _print_divider("6. Live Data (token provided)")

        print("\n  --- Events ---")
        try:
            events = client.get_events(include_scheduled=False)
            incidents = [e for e in events if e.category_id == 1]
            construction = [e for e in events if e.category_id == 2]
            weather = [e for e in events if e.category_id == 4]
            print(f"  Total active events : {len(events)}")
            print(f"  Incidents           : {len(incidents)}")
            print(f"  Construction zones  : {len(construction)}")
            print(f"  Weather events      : {len(weather)}")
            if events and args.verbose:
                print("  First event:")
                _print_json(events[0])
        except Exception as e:
            print(f"  ERROR: {e}")

        print("\n  --- Travel Links ---")
        try:
            links = client.get_travel_links()
            print(f"  Travel time links   : {len(links)}")
            if links:
                sample = links[0]
                norm = sample.normal_time or "N/A"
                curr = sample.current_time or "N/A"
                print(f"  Sample link         : {sample.name} — normal {norm} min / current {curr} min")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        _print_divider("6. Authenticated Endpoints")
        print(
            "  No auth token provided. To access events, cameras, and travel data:\n"
            "\n"
            "  1. Obtain a token by logging in to https://511nj.org\n"
            "     or via: POST https://511nj.org/account/login\n"
            "     Body: {\"username\": \"...\", \"password\": \"...\"}\n"
            "     (credentials are AES-encrypted before sending by the SPA)\n"
            "\n"
            "  2. Pass the token:\n"
            "     client = NJDOTClient(auth_token='<your_token>')\n"
            "\n"
            "  3. Then call:\n"
            "     events  = client.get_events()\n"
            "     cameras = client.get_cameras_admin()   # admin only\n"
            "     links   = client.get_travel_links()\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="511NJ Traffic API Client - demonstrates and documents the 511NJ API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage")[0].strip(),
    )
    parser.add_argument(
        "--token", "-t",
        metavar="TOKEN",
        default=None,
        help="Bearer access token from /account/login (optional)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full JSON for each response",
    )
    parser.add_argument(
        "--version-only",
        action="store_true",
        help="Print the app version number and exit",
    )
    args = parser.parse_args()

    if args.version_only:
        client = NJDOTClient()
        v = client.get_reload_version()
        print(v.value)
        return

    run_demo(args)


if __name__ == "__main__":
    main()
