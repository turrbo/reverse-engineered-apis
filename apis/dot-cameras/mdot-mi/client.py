#!/usr/bin/env python3
"""
Michigan Department of Transportation (MDOT) MiDrive Traffic API Client
========================================================================

A production-quality Python client for the MDOT MiDrive traffic information system.
Uses only the Python standard library (urllib, json, dataclasses).

Reverse-engineered from: https://mdotjboss.state.mi.us/MiDrive/map

Discovered Endpoints
--------------------
BASE_URL = "https://mdotjboss.state.mi.us/MiDrive"

  Cameras:
    GET /camera/AllForMap/                         -> list[CameraMarker]
    GET /camera/getCameraInformation/{id}          -> CameraDetail
    GET /camera/getCameraInformationByRoute/{route}---{type} -> list[CameraDetail]
    POST /camera/favoriteCameras/                  -> list[CameraDetail]  (body: cameraIds=1,2,3)
    GET /camera/reportCamera/{id}                  -> (POST only, used for reporting issues)

  Incidents:
    GET /incidents/AllForMap/                      -> list[IncidentMarker]
    GET /incidents/AllForPage                      -> list[IncidentPage]

  Construction:
    GET /construction/AllForMap/                   -> list[ConstructionZone]
    GET /construction/getConstructionInformation/{id} -> [html_detail, title]

  Parking (Truck):
    GET /parking/getMapParking/                    -> list[ParkingMarker]
    GET /parking/getParkingInfoMap/{id}            -> [html_detail, title]
    GET /parking/getParkingInfoMap/showAllParkings -> dict{key: html_detail}

  Dynamic Message Signs (DMS):
    GET /dms/AllForMap                             -> list[DMSMarker]
    GET /dms/getDMSInfo/{id}                       -> [html_message, title]

  Toll Bridges:
    GET /tollBridges/allForMap/                    -> list[TollBridgeMarker]
    GET /tollBridges/tollBridgeMessage/{id}        -> [html_detail]

  Snowplows / Maintenance Vehicles:
    GET /plows/AllForMap/                          -> list[PlowMarker]   (seasonal)

  Geocoding / Cities:
    GET /map/getGeocodeLatLon/{city_or_zip}        -> GeocodeResult
    GET /cities/                                   -> list[City]

Camera Image CDN Patterns
-------------------------
  RWIS (Road Weather Info System) cameras:
    https://mdotjboss.state.mi.us/docs/drive/camfiles/rwis/{id}.jpg?random={timestamp}

  SEM TOC cameras (Detroit metro area):
    https://micamerasimages.net/thumbs/semtoc_cam_{NNN}.flv.jpg?item=1

  Grand Rapids area cameras:
    https://micamerasimages.net/thumbs/grand_cam_{NNN}.flv.jpg?item=1

Auth / Security
---------------
  - No authentication required for any read endpoints
  - No API keys discovered
  - Standard session cookies (JSESSIONID) set automatically but not required
  - All endpoints are unauthenticated public JSON REST APIs
  - Google Analytics UA-18590017-1 / G-1041L79PWV tracking (ignored in client)

Notes
-----
  - Traffic speed layer uses ESRI ArcGIS: https://utility.arcgis.com/usrsvcs/appservices/
    2y1TxWC4UaePZylO/rest/services/World/Traffic/MapServer  (requires ArcGIS token)
  - Construction icon codes: 1=Total Closure (Red), 2=Lane Closure (Orange),
    3=Special Event (Blue), 4=Future Closure (Green)
  - Camera image links are only returned by getCameraInformation (not AllForMap)
  - Incident data refreshes every 60-90 seconds on the live map
  - Plows endpoint returns empty outside winter season
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://mdotjboss.state.mi.us/MiDrive"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://mdotjboss.state.mi.us/MiDrive/map",
}

# Construction zone icon codes (as returned by the API)
CONSTRUCTION_ICON_TOTAL_CLOSURE = 1   # Red
CONSTRUCTION_ICON_LANE_CLOSURE = 2    # Orange
CONSTRUCTION_ICON_SPECIAL_EVENT = 3   # Blue
CONSTRUCTION_ICON_FUTURE_CLOSURE = 4  # Green

CONSTRUCTION_ICON_LABELS = {
    1: "Total Closure",
    2: "Lane Closure",
    3: "Special Event",
    4: "Future Closure",
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CameraMarker:
    """
    Lightweight camera record returned by /camera/AllForMap/.

    Use :meth:`MiDriveClient.get_camera` to retrieve the full detail
    including the live image URL.
    """

    id: int
    title: str
    latitude: float
    longitude: float
    icon: str = ""
    link: Optional[str] = None
    weather_text: Optional[str] = None
    weather_id: int = 0
    orientation: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CameraMarker":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=d.get("icon", ""),
            link=d.get("link"),
            weather_text=d.get("weatherText"),
            weather_id=d.get("weatherId", 0),
            orientation=d.get("orientation"),
        )


@dataclass
class CameraDetail:
    """
    Full camera record returned by /camera/getCameraInformation/{id}.

    The ``link`` field contains the live JPEG/image URL suitable for
    direct embedding or downloading.

    Camera image CDN patterns discovered:
      - RWIS: ``https://mdotjboss.state.mi.us/docs/drive/camfiles/rwis/{id}.jpg?random={ts}``
      - SEM TOC (Detroit): ``https://micamerasimages.net/thumbs/semtoc_cam_NNN.flv.jpg?item=1``
      - Grand Rapids: ``https://micamerasimages.net/thumbs/grand_cam_NNN.flv.jpg?item=1``
    """

    id: int
    title: str
    latitude: float
    longitude: float
    link: Optional[str] = None
    icon: str = ""
    weather_text: Optional[str] = None
    weather_id: int = 0
    orientation: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CameraDetail":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            link=d.get("link"),
            icon=d.get("icon", ""),
            weather_text=d.get("weatherText"),
            weather_id=d.get("weatherId", 0),
            orientation=d.get("orientation"),
        )

    def image_url(self, bust_cache: bool = True) -> Optional[str]:
        """
        Return the live image URL for this camera.

        For RWIS cameras the URL already contains a ``?random=`` parameter.
        For micamerasimages.net cameras an ``?item=1`` parameter is present.

        Args:
            bust_cache: If True, append/replace the cache-busting parameter
                        with the current Unix timestamp (milliseconds) for
                        RWIS cameras. Has no effect on micamerasimages.net
                        URLs which use a different cache-busting scheme.

        Returns:
            The image URL string, or ``None`` if no image is available
            (e.g. offline / grey camera icon).
        """
        if not self.link:
            return None
        if bust_cache and "mdotjboss.state.mi.us" in self.link:
            base = self.link.split("?")[0]
            return f"{base}?random={int(time.time() * 1000)}"
        return self.link


@dataclass
class IncidentMarker:
    """
    Incident record from /incidents/AllForMap/ – minimal map pin data.
    The ``message`` field contains HTML-formatted detail text.
    """

    id: int
    title: str
    latitude: float
    longitude: float
    icon: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IncidentMarker":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=d.get("icon", ""),
            message=d.get("message", ""),
        )


@dataclass
class IncidentPage:
    """
    Incident record from /incidents/AllForPage – richer sidebar panel data.
    The ``incident_text`` field contains HTML-formatted full detail text.
    """

    incident_id: int
    incident_title: str
    latitude: float
    longitude: float
    icon_url: str = ""
    incident_text: str = ""
    goto_link: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IncidentPage":
        return cls(
            incident_id=d["incidentId"],
            incident_title=d["incidentTitle"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon_url=d.get("iconURL", ""),
            incident_text=d.get("incidentText", ""),
            goto_link=d.get("gotoLink", ""),
        )


@dataclass
class ConstructionZone:
    """
    Construction zone / road closure from /construction/AllForMap/.

    ``icon`` is an integer code:
      1 = Total Closure (Red), 2 = Lane Closure (Orange),
      3 = Special Event (Blue), 4 = Future Closure (Green).

    ``coordinate_points`` is a list of [lon, lat] pairs forming the
    polyline geometry of the closure along the road.
    """

    id: str
    title: str
    latitude: float
    longitude: float
    icon: int = 2
    active: bool = True
    coordinate_points: list[list[float]] = field(default_factory=list)

    @property
    def closure_type(self) -> str:
        """Human-readable closure type label."""
        return CONSTRUCTION_ICON_LABELS.get(self.icon, f"Unknown ({self.icon})")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConstructionZone":
        return cls(
            id=str(d["id"]),
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=int(d.get("icon") or 2),
            active=bool(d.get("active", True)),
            coordinate_points=d.get("coordinatePoints", []),
        )


@dataclass
class ParkingMarker:
    """
    Truck parking location from /parking/getMapParking/.
    Use :meth:`MiDriveClient.get_parking_detail` for space availability.
    """

    id: int
    title: str
    latitude: float
    longitude: float
    icon: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParkingMarker":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=d.get("icon", ""),
        )


@dataclass
class DMSMarker:
    """
    Dynamic Message Sign (highway overhead sign) from /dms/AllForMap.
    Use :meth:`MiDriveClient.get_dms_info` to read current message text.
    """

    id: int
    title: str
    latitude: float
    longitude: float
    icon: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DMSMarker":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=d.get("icon", ""),
        )


@dataclass
class DMSInfo:
    """
    Current message displayed on a Dynamic Message Sign.
    Both ``message_html`` and ``title`` are returned by the API as
    a two-element list ``[html_message, title]``.
    """

    id: int
    title: str
    message_html: str
    timestamp: Optional[str] = None  # parsed from dmstimeStamp div when present

    @classmethod
    def from_api(cls, dms_id: int, data: list) -> "DMSInfo":
        """
        Parse the raw API list ``[html_message, title]`` returned by
        /dms/getDMSInfo/{id}.
        """
        html = data[0] if len(data) > 0 else ""
        title = data[1] if len(data) > 1 else ""
        # Try to extract timestamp if present in the HTML
        ts: Optional[str] = None
        if "dmstimeStamp" in html:
            import re
            m = re.search(r"<div class='dmstimeStamp'>(.*?)</div>", html)
            if m:
                ts = m.group(1).strip()
        return cls(id=dms_id, title=title, message_html=html, timestamp=ts)

    def message_text(self) -> str:
        """
        Strip HTML tags and return the plain-text version of the sign message.
        """
        import re
        text = re.sub(r"<[^>]+>", "\n", self.message_html)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines)


@dataclass
class TollBridgeMarker:
    """
    Toll bridge / international border crossing from /tollBridges/allForMap/.
    """

    id: int
    title: str
    latitude: float
    longitude: float
    icon: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TollBridgeMarker":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=d.get("icon", ""),
        )


@dataclass
class PlowMarker:
    """
    Snowplow / maintenance vehicle from /plows/AllForMap/.
    This endpoint returns an empty list outside of winter season.
    """

    id: int
    title: str
    latitude: float
    longitude: float
    icon: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlowMarker":
        return cls(
            id=d["id"],
            title=d["title"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            icon=d.get("icon", ""),
        )


@dataclass
class GeocodeResult:
    """
    Result from /map/getGeocodeLatLon/{query}.
    Powered by Bing Maps geocoding.
    """

    latitude: float
    longitude: float
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    match_quality: Optional[str] = None
    match_method: Optional[str] = None
    match_note: Optional[str] = None
    match_source: Optional[str] = None
    address: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GeocodeResult":
        return cls(
            latitude=d["latitude"],
            longitude=d["longitude"],
            city=d.get("city"),
            state=d.get("state"),
            zip_code=d.get("zipCode"),
            match_quality=d.get("matchQuality"),
            match_method=d.get("matchMethod"),
            match_note=d.get("matchNote"),
            match_source=d.get("matchSource"),
            address=d.get("address"),
        )


@dataclass
class City:
    """Michigan city from /cities/."""

    city_cd: int
    city_name: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "City":
        pk = d.get("pk", {})
        return cls(
            city_cd=pk.get("cityCd", 0),
            city_name=pk.get("cityName", ""),
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MiDriveError(Exception):
    """Base exception for all MiDrive API errors."""


class MiDriveHTTPError(MiDriveError):
    """Raised when the API returns a non-2xx HTTP status code."""

    def __init__(self, url: str, code: int, reason: str) -> None:
        self.url = url
        self.code = code
        self.reason = reason
        super().__init__(f"HTTP {code} {reason} for {url}")


class MiDriveConnectionError(MiDriveError):
    """Raised when a network connection error occurs."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class MiDriveClient:
    """
    Client for the MDOT MiDrive traffic information system.

    All methods perform a single synchronous HTTP GET (or POST) request and
    return parsed dataclass objects. No authentication is required.

    Example usage::

        client = MiDriveClient()

        # List all traffic cameras in Michigan
        cameras = client.list_cameras()
        print(f"{len(cameras)} cameras found")

        # Get live image URL for a specific camera
        detail = client.get_camera(cameras[0].id)
        print(f"Image: {detail.image_url()}")

        # Get current incidents
        incidents = client.list_incidents()
        for inc in incidents:
            print(inc.title, inc.latitude, inc.longitude)

        # Get all construction zones
        zones = client.list_construction()
        total_closures = [z for z in zones if z.icon == 1]

        # Get current DMS message
        signs = client.list_dms()
        info = client.get_dms_info(signs[0].id)
        print(info.message_text())

    Args:
        base_url: Base URL for the MiDrive API. Defaults to the live system.
        timeout: Socket timeout in seconds for all requests. Default: 30.
        headers: Additional HTTP headers merged with defaults.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers: dict[str, str] = {**DEFAULT_HEADERS}
        if headers:
            self._headers.update(headers)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        path: str,
        method: str = "GET",
        data: Optional[dict[str, str]] = None,
    ) -> Any:
        """
        Execute an HTTP request and return the parsed JSON body.

        Args:
            path: URL path relative to ``base_url`` (must start with ``/``).
            method: HTTP method, ``"GET"`` or ``"POST"``.
            data: Optional form data dict for POST requests.

        Returns:
            Parsed JSON value (list, dict, str, int, etc.)

        Raises:
            MiDriveHTTPError: On non-2xx HTTP responses.
            MiDriveConnectionError: On network errors.
            MiDriveError: On JSON decode failures.
        """
        url = self.base_url + path
        body: Optional[bytes] = None
        if data and method == "POST":
            body = urllib.parse.urlencode(data).encode("utf-8")

        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self._headers.items():
            req.add_header(k, v)
        if body:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise MiDriveHTTPError(url, exc.code, exc.reason) from exc
        except urllib.error.URLError as exc:
            raise MiDriveConnectionError(f"Connection error for {url}: {exc.reason}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MiDriveError(f"Invalid JSON from {url}: {exc}") from exc

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def list_cameras(self) -> list[CameraMarker]:
        """
        Return all traffic camera map pins for Michigan.

        Calls ``GET /camera/AllForMap/``.

        Note: The ``link`` field on each marker is always ``None`` in this
        response. Use :meth:`get_camera` to retrieve the live image URL.

        Returns:
            List of :class:`CameraMarker` objects (~785 cameras state-wide).
        """
        data = self._request("/camera/AllForMap/")
        return [CameraMarker.from_dict(d) for d in data]

    def get_camera(self, camera_id: int) -> CameraDetail:
        """
        Return full detail for a single camera including its live image URL.

        Calls ``GET /camera/getCameraInformation/{id}``.

        Args:
            camera_id: The integer camera ID (from :meth:`list_cameras`).

        Returns:
            :class:`CameraDetail` with ``link`` populated when available.
        """
        data = self._request(f"/camera/getCameraInformation/{camera_id}")
        return CameraDetail.from_dict(data)

    def get_cameras_by_route(self, route: str, route_type: str = "I") -> list[CameraDetail]:
        """
        Return cameras along a specific Michigan freeway/route.

        Calls ``GET /camera/getCameraInformationByRoute/{route}---{type}``.

        The route parameter is combined with the route type using ``---``
        as a separator (three dashes), e.g. ``"I-75---I"`` for Interstate 75.

        Args:
            route: Route designation, e.g. ``"I-75"``, ``"US-23"``, ``"M-59"``.
            route_type: Route type suffix. Common values: ``"I"`` (Interstate),
                        ``"US"`` (US Highway), ``"M"`` (Michigan State Highway).

        Returns:
            List of :class:`CameraDetail` objects for cameras along the route.
        """
        combined = f"{route}---{route_type}"
        data = self._request(f"/camera/getCameraInformationByRoute/{combined}")
        if not data:
            return []
        return [CameraDetail.from_dict(d) for d in data]

    def get_favorite_cameras(self, camera_ids: list[int]) -> list[CameraDetail]:
        """
        Return details for a specific list of camera IDs (favorite cameras).

        Calls ``POST /camera/favoriteCameras/`` with form body ``cameraIds=1,2,3``.

        Args:
            camera_ids: List of integer camera IDs.

        Returns:
            List of :class:`CameraDetail` objects.
        """
        ids_str = ",".join(str(i) for i in camera_ids)
        data = self._request(
            "/camera/favoriteCameras/",
            method="POST",
            data={"cameraIds": ids_str},
        )
        if not data:
            return []
        return [CameraDetail.from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Incident endpoints
    # ------------------------------------------------------------------

    def list_incidents_map(self) -> list[IncidentMarker]:
        """
        Return all active traffic incidents as map pin objects.

        Calls ``GET /incidents/AllForMap/``.

        The ``message`` field contains HTML-formatted detail text.
        Refreshes approximately every 90 seconds on the live map.

        Returns:
            List of :class:`IncidentMarker` objects.
        """
        data = self._request("/incidents/AllForMap/")
        return [IncidentMarker.from_dict(d) for d in data]

    def list_incidents(self) -> list[IncidentPage]:
        """
        Return all active traffic incidents with richer sidebar panel data.

        Calls ``GET /incidents/AllForPage``.

        Preferred over :meth:`list_incidents_map` when full incident details
        are needed (includes ``incidentText`` HTML). Refreshes every 60 seconds
        on the live map.

        Returns:
            List of :class:`IncidentPage` objects.
        """
        data = self._request("/incidents/AllForPage")
        return [IncidentPage.from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Construction endpoints
    # ------------------------------------------------------------------

    def list_construction(self) -> list[ConstructionZone]:
        """
        Return all active road construction zones and closures state-wide.

        Calls ``GET /construction/AllForMap/``.

        Each zone includes polyline geometry (``coordinate_points``) for
        rendering the closure on a map, plus an icon code indicating type:
          - 1 = Total Closure (red)
          - 2 = Lane Closure (orange)
          - 3 = Special Event (blue)
          - 4 = Future Closure (green)

        Returns:
            List of :class:`ConstructionZone` objects (~300-500 zones).
        """
        data = self._request("/construction/AllForMap/")
        return [ConstructionZone.from_dict(d) for d in data]

    def get_construction_detail(self, zone_id: str) -> tuple[str, str]:
        """
        Return detailed description for a single construction zone.

        Calls ``GET /construction/getConstructionInformation/{id}``.

        Args:
            zone_id: The construction zone ID string (e.g. ``"ETX-3268"``).

        Returns:
            Tuple of ``(html_detail, title)`` where ``html_detail`` contains
            start/end dates, detour routes, and full description.
        """
        data = self._request(f"/construction/getConstructionInformation/{zone_id}")
        html = data[0] if len(data) > 0 else ""
        title = data[1] if len(data) > 1 else ""
        return html, title

    # ------------------------------------------------------------------
    # Parking endpoints
    # ------------------------------------------------------------------

    def list_parking(self) -> list[ParkingMarker]:
        """
        Return all truck parking locations on Michigan freeways.

        Calls ``GET /parking/getMapParking/``.

        Returns:
            List of :class:`ParkingMarker` objects with current status
            encoded in the ``title`` field (e.g. ``"I-94 @ Parma - Available"``).
        """
        data = self._request("/parking/getMapParking/")
        return [ParkingMarker.from_dict(d) for d in data]

    def get_parking_detail(self, parking_id: int) -> tuple[str, str]:
        """
        Return detailed information for a specific truck parking location.

        Calls ``GET /parking/getParkingInfoMap/{id}``.

        Args:
            parking_id: The parking location integer ID.

        Returns:
            Tuple of ``(html_detail, title)`` where ``html_detail`` includes
            open spaces, total spaces, route, location, and last update time.
        """
        data = self._request(f"/parking/getParkingInfoMap/{parking_id}")
        html = data[0] if len(data) > 0 else ""
        title = data[1] if len(data) > 1 else ""
        return html, title

    def get_all_parking_details(self) -> dict[str, str]:
        """
        Return detailed information for all truck parking locations at once.

        Calls ``GET /parking/getParkingInfoMap/showAllParkings``.

        Returns:
            Dict mapping a location key (``"{lat} - {lon} - {title}"``) to
            an HTML detail string containing current space availability.
        """
        data = self._request("/parking/getParkingInfoMap/showAllParkings")
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # DMS (Dynamic Message Signs)
    # ------------------------------------------------------------------

    def list_dms(self) -> list[DMSMarker]:
        """
        Return all Dynamic Message Sign (overhead highway sign) locations.

        Calls ``GET /dms/AllForMap``.

        Returns:
            List of :class:`DMSMarker` objects (~487 signs state-wide).
        """
        data = self._request("/dms/AllForMap")
        return [DMSMarker.from_dict(d) for d in data]

    def get_dms_info(self, dms_id: int) -> DMSInfo:
        """
        Return the current message displayed on a specific DMS sign.

        Calls ``GET /dms/getDMSInfo/{id}``.

        Args:
            dms_id: The DMS integer ID (from :meth:`list_dms`).

        Returns:
            :class:`DMSInfo` with ``message_html`` and optional ``timestamp``.
            Use :meth:`DMSInfo.message_text` for plain-text version.
        """
        data = self._request(f"/dms/getDMSInfo/{dms_id}")
        return DMSInfo.from_api(dms_id, data)

    # ------------------------------------------------------------------
    # Toll bridges
    # ------------------------------------------------------------------

    def list_toll_bridges(self) -> list[TollBridgeMarker]:
        """
        Return all toll bridges and international border crossings.

        Calls ``GET /tollBridges/allForMap/``.

        Michigan international crossings include:
        Blue Water Bridge (Port Huron), Ambassador Bridge (Detroit),
        Detroit-Windsor Tunnel, Sault Ste. Marie International Bridge,
        and Mackinac Bridge (state toll).

        Returns:
            List of :class:`TollBridgeMarker` objects.
        """
        data = self._request("/tollBridges/allForMap/")
        return [TollBridgeMarker.from_dict(d) for d in data]

    def get_toll_bridge_message(self, bridge_id: int) -> str:
        """
        Return HTML detail for a toll bridge (ownership, website link, etc.).

        Calls ``GET /tollBridges/tollBridgeMessage/{id}``.

        Args:
            bridge_id: The toll bridge integer ID.

        Returns:
            HTML string with bridge ownership and website information.
        """
        data = self._request(f"/tollBridges/tollBridgeMessage/{bridge_id}")
        return data[0] if data else ""

    # ------------------------------------------------------------------
    # Snowplows / Maintenance Vehicles
    # ------------------------------------------------------------------

    def list_plows(self) -> list[PlowMarker]:
        """
        Return current snowplow / maintenance vehicle positions.

        Calls ``GET /plows/AllForMap/``.

        Note: This endpoint returns an empty list outside winter season.
        The live map auto-refreshes plows every 90 seconds.

        Returns:
            List of :class:`PlowMarker` objects (empty off-season).
        """
        data = self._request("/plows/AllForMap/")
        if not data or not isinstance(data, list):
            return []
        return [PlowMarker.from_dict(d) for d in data]

    # ------------------------------------------------------------------
    # Geocoding / Cities
    # ------------------------------------------------------------------

    def geocode(self, query: str) -> GeocodeResult:
        """
        Geocode a Michigan city name or zip code to lat/lon coordinates.

        Calls ``GET /map/getGeocodeLatLon/{query}``.

        Powered by Bing Maps geocoding, constrained to Michigan.

        Args:
            query: City name (e.g. ``"Detroit"``) or zip code (e.g. ``"48226"``).

        Returns:
            :class:`GeocodeResult` with latitude/longitude and match metadata.
        """
        encoded = urllib.parse.quote(str(query), safe="")
        data = self._request(f"/map/getGeocodeLatLon/{encoded}")
        return GeocodeResult.from_dict(data)

    def list_cities(self) -> list[City]:
        """
        Return all Michigan city names used by the MiDrive autocomplete.

        Calls ``GET /cities/``.

        Returns:
            List of :class:`City` objects (~533 Michigan cities).
        """
        data = self._request("/cities/")
        return [City.from_dict(d) for d in data]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance in kilometres between two points
    using the Haversine formula.

    Args:
        lat1, lon1: Coordinates of the first point (decimal degrees).
        lat2, lon2: Coordinates of the second point (decimal degrees).

    Returns:
        Distance in kilometres.
    """
    import math

    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_cameras(
    cameras: list[CameraMarker],
    lat: float,
    lon: float,
    max_results: int = 5,
    max_km: float = 50.0,
) -> list[tuple[float, CameraMarker]]:
    """
    Find the nearest cameras to a given lat/lon coordinate.

    Args:
        cameras: List of :class:`CameraMarker` objects (from :meth:`MiDriveClient.list_cameras`).
        lat: Target latitude.
        lon: Target longitude.
        max_results: Maximum number of cameras to return.
        max_km: Maximum search radius in kilometres.

    Returns:
        List of ``(distance_km, camera)`` tuples sorted by distance ascending.
    """
    distances = []
    for cam in cameras:
        dist = haversine_distance(lat, lon, cam.latitude, cam.longitude)
        if dist <= max_km:
            distances.append((dist, cam))
    distances.sort(key=lambda x: x[0])
    return distances[:max_results]


def strip_html(html: str) -> str:
    """
    Remove HTML tags and collapse whitespace from an HTML string.

    Args:
        html: HTML string to clean.

    Returns:
        Plain text string with tags removed.
    """
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# CLI Demo
# ---------------------------------------------------------------------------


def _cli_summary(client: MiDriveClient) -> None:
    """Print a live system summary to stdout."""
    print("=" * 60)
    print("  MDOT MiDrive - Live System Summary")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 60)

    # Cameras
    cameras = client.list_cameras()
    print(f"\n[CAMERAS]  {len(cameras)} total cameras state-wide")
    # Sample first camera with full detail
    if cameras:
        detail = client.get_camera(cameras[0].id)
        print(f"  Sample: {detail.title} ({detail.latitude}, {detail.longitude})")
        print(f"  Image URL: {detail.image_url() or '(offline)'}")

    # Incidents
    incidents = client.list_incidents()
    print(f"\n[INCIDENTS]  {len(incidents)} active incidents")
    for inc in incidents[:3]:
        print(f"  - {inc.incident_title} ({inc.latitude:.4f}, {inc.longitude:.4f})")

    # Construction
    zones = client.list_construction()
    active = [z for z in zones if z.active]
    total_closures = [z for z in active if z.icon == 1]
    lane_closures = [z for z in active if z.icon == 2]
    future_closures = [z for z in zones if z.icon == 4]
    print(f"\n[CONSTRUCTION]  {len(zones)} zones total")
    print(f"  Active: {len(active)}  |  Total closures: {len(total_closures)}  |  Lane closures: {len(lane_closures)}  |  Future: {len(future_closures)}")
    if active:
        print(f"  Sample: {active[0].title} -> {active[0].closure_type}")

    # DMS Signs
    signs = client.list_dms()
    print(f"\n[DMS SIGNS]  {len(signs)} dynamic message signs")
    if signs:
        info = client.get_dms_info(signs[0].id)
        print(f"  {info.title}:")
        msg_lines = info.message_text().splitlines()
        for line in msg_lines[:4]:
            print(f"    {line}")

    # Parking
    parking = client.list_parking()
    print(f"\n[TRUCK PARKING]  {len(parking)} locations")
    for lot in parking[:3]:
        print(f"  - {lot.title}")

    # Toll Bridges
    bridges = client.list_toll_bridges()
    print(f"\n[TOLL BRIDGES]  {len(bridges)} crossings")
    for b in bridges:
        print(f"  - {b.title}")

    print("\n" + "=" * 60)


def _cli_cameras(client: MiDriveClient, args: list[str]) -> None:
    """List cameras, optionally near a city."""
    cameras = client.list_cameras()
    if "--near" in args:
        idx = args.index("--near")
        city = args[idx + 1] if idx + 1 < len(args) else "Detroit"
        geo = client.geocode(city)
        print(f"Cameras near {city} ({geo.latitude:.4f}, {geo.longitude:.4f}):")
        nearest = find_nearest_cameras(cameras, geo.latitude, geo.longitude, max_results=10)
        for dist, cam in nearest:
            print(f"  [{cam.id}] {cam.title:40s}  {dist:.1f} km")
    else:
        limit = 20
        print(f"First {limit} cameras (of {len(cameras)} total):")
        for cam in cameras[:limit]:
            print(f"  [{cam.id}] {cam.title}")


def _cli_incidents(client: MiDriveClient) -> None:
    """List current traffic incidents."""
    incidents = client.list_incidents()
    if not incidents:
        print("No active incidents.")
        return
    print(f"{len(incidents)} active traffic incidents:")
    for inc in incidents:
        text = strip_html(inc.incident_text)
        print(f"\n  [{inc.incident_id}] {inc.incident_title}")
        print(f"       Location: ({inc.latitude:.4f}, {inc.longitude:.4f})")
        print(f"       {text[:200]}")


def _cli_construction(client: MiDriveClient) -> None:
    """List active construction zones."""
    zones = client.list_construction()
    active = [z for z in zones if z.active]
    print(f"{len(active)} active construction zones (of {len(zones)} total):")
    for z in sorted(active, key=lambda x: x.icon)[:20]:
        print(f"  [{z.id}] {z.title:50s}  {z.closure_type}")


def _cli_dms(client: MiDriveClient, args: list[str]) -> None:
    """Show current DMS sign messages."""
    signs = client.list_dms()
    limit = 5
    if "--all" in args:
        limit = len(signs)
    print(f"Dynamic Message Signs (showing {limit} of {len(signs)}):")
    for sign in signs[:limit]:
        info = client.get_dms_info(sign.id)
        print(f"\n  [{sign.id}] {sign.title}")
        if info.timestamp:
            print(f"       Updated: {info.timestamp}")
        for line in info.message_text().splitlines()[:5]:
            print(f"       {line}")


def _cli_camera_detail(client: MiDriveClient, camera_id: int) -> None:
    """Show full detail for a specific camera."""
    detail = client.get_camera(camera_id)
    print(f"Camera #{detail.id}: {detail.title}")
    print(f"  Location:    ({detail.latitude}, {detail.longitude})")
    print(f"  Orientation: {detail.orientation or 'N/A'}")
    print(f"  Image URL:   {detail.image_url() or '(offline)'}")
    if detail.weather_text:
        print(f"  Weather:     {detail.weather_text}")


def main() -> int:
    """
    CLI entry point.

    Usage::

        python mdot_mi_client.py summary
        python mdot_mi_client.py cameras
        python mdot_mi_client.py cameras --near Detroit
        python mdot_mi_client.py camera 1129
        python mdot_mi_client.py incidents
        python mdot_mi_client.py construction
        python mdot_mi_client.py dms
        python mdot_mi_client.py dms --all
        python mdot_mi_client.py parking
        python mdot_mi_client.py bridges

    """
    args = sys.argv[1:]
    if not args:
        print(__doc__[:800])
        print("\nUsage: python mdot_mi_client.py <command> [options]")
        print("Commands: summary, cameras, camera <id>, incidents, construction, dms, parking, bridges")
        return 0

    client = MiDriveClient()
    cmd = args[0].lower()

    try:
        if cmd == "summary":
            _cli_summary(client)
        elif cmd == "cameras":
            _cli_cameras(client, args[1:])
        elif cmd == "camera":
            if len(args) < 2:
                print("Usage: python mdot_mi_client.py camera <id>")
                return 1
            _cli_camera_detail(client, int(args[1]))
        elif cmd == "incidents":
            _cli_incidents(client)
        elif cmd == "construction":
            _cli_construction(client)
        elif cmd == "dms":
            _cli_dms(client, args[1:])
        elif cmd == "parking":
            lots = client.list_parking()
            print(f"{len(lots)} truck parking locations:")
            for lot in lots:
                print(f"  [{lot.id}] {lot.title}")
        elif cmd == "bridges":
            bridges = client.list_toll_bridges()
            print(f"{len(bridges)} toll bridges / border crossings:")
            for b in bridges:
                print(f"  [{b.id}] {b.title}  ({b.latitude:.4f}, {b.longitude:.4f})")
        elif cmd == "cities":
            cities = client.list_cities()
            print(f"{len(cities)} Michigan cities in MiDrive database")
            for c in cities[:20]:
                print(f"  {c.city_cd}: {c.city_name}")
            if len(cities) > 20:
                print(f"  ... and {len(cities) - 20} more")
        elif cmd == "geocode":
            if len(args) < 2:
                print("Usage: python mdot_mi_client.py geocode <city_or_zip>")
                return 1
            query = " ".join(args[1:])
            result = client.geocode(query)
            print(f"Geocode result for '{query}':")
            print(f"  Lat/Lon:  {result.latitude}, {result.longitude}")
            print(f"  City:     {result.city or 'N/A'}")
            print(f"  State:    {result.state or 'N/A'}")
            print(f"  Quality:  {result.match_quality or 'N/A'}")
            print(f"  Source:   {result.match_source or 'N/A'}")
        else:
            print(f"Unknown command: {cmd}")
            print("Commands: summary, cameras, camera <id>, incidents, construction, dms, parking, bridges, cities, geocode <query>")
            return 1
    except MiDriveHTTPError as exc:
        print(f"HTTP Error: {exc}", file=sys.stderr)
        return 2
    except MiDriveConnectionError as exc:
        print(f"Connection Error: {exc}", file=sys.stderr)
        return 2
    except MiDriveError as exc:
        print(f"API Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
