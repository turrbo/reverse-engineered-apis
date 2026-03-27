#!/usr/bin/env python3
"""
Maryland CHART Traffic API Client
==================================
A production-quality Python client for the Maryland Coordinated Highways Action
Response Team (CHART) public traffic data APIs operated by the Maryland State
Highway Administration (SHA).

No external dependencies are required — only Python 3.8+ standard library.

API Base: https://chartexp1.sha.maryland.gov/CHARTExportClientService/
Portal:   https://www.chart.maryland.gov

Usage (CLI):
    python mdot_md_client.py cameras
    python mdot_md_client.py incidents
    python mdot_md_client.py closures
    python mdot_md_client.py dms
    python mdot_md_client.py speeds
    python mdot_md_client.py weather
    python mdot_md_client.py snow
    python mdot_md_client.py wzdx
    python mdot_md_client.py messages

Usage (library):
    from mdot_md_client import CHARTClient

    client = CHARTClient()
    cameras = client.get_cameras()
    for cam in cameras:
        print(cam.description, cam.video_url)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXPORT_BASE = "https://chartexp1.sha.maryland.gov/CHARTExportClientService"
_CHART_BASE = "https://chart.maryland.gov"
_WZDX_URL = "https://filter.ritis.org/wzdx_v4.1/mdot.geojson"

_DEFAULT_TIMEOUT = 30  # seconds
_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "mdot-md-client/1.0 (Python urllib; public traffic data)",
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _ts_to_dt(ms: Optional[int]) -> Optional[datetime]:
    """Convert a millisecond UNIX timestamp to a UTC-aware datetime, or None."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _fetch_json(url: str, timeout: int = _DEFAULT_TIMEOUT) -> Any:
    """
    Perform an HTTP GET request and parse the response body as JSON.

    Parameters
    ----------
    url:
        Fully-qualified URL to fetch.
    timeout:
        Socket timeout in seconds.

    Returns
    -------
    Any
        Parsed JSON value (usually dict or list).

    Raises
    ------
    urllib.error.URLError
        If the network request fails.
    ValueError
        If the response body cannot be parsed as JSON.
    """
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _fetch_geojson(url: str, timeout: int = _DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Fetch a GeoJSON FeatureCollection from *url*."""
    req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _unwrap(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract the ``data`` list from a standard CHART API envelope.

    The CHART Export Service always wraps results like::

        {
          "error": null,
          "data": [...],
          "success": true,
          "warnings": [],
          "totalCount": N
        }

    Raises ``RuntimeError`` if ``success`` is false or ``error`` is non-null.
    """
    if not payload.get("success", True):
        raise RuntimeError(
            f"CHART API returned an error: {payload.get('error')}"
        )
    if payload.get("error"):
        raise RuntimeError(f"CHART API error: {payload['error']}")
    return payload.get("data", [])


# ---------------------------------------------------------------------------
# Dataclasses — typed representations of API responses
# ---------------------------------------------------------------------------


@dataclass
class Camera:
    """A traffic surveillance camera on the Maryland road network."""

    id: str
    """Opaque unique identifier used in stream/thumbnail URLs."""

    name: str
    """Short location code or landmark name."""

    description: str
    """Human-readable location description, e.g. "I-95 NB at Exit 43"."""

    lat: float
    """WGS-84 latitude."""

    lon: float
    """WGS-84 longitude."""

    cctv_ip: str
    """Hostname of the streaming server, e.g. ``strmr5.sha.maryland.gov``."""

    route_prefix: str
    """Route type prefix: IS (Interstate), US (US Route), MD (State Route), etc."""

    route_number: int
    """Numeric route identifier."""

    mile_post: Optional[float]
    """Approximate highway mile-post, if available."""

    op_status: str
    """Operational status: ``OK``, ``COMM_FAILURE``, ``COMM_MARGINAL``."""

    comm_mode: str
    """Communication mode: ``ONLINE``, ``OFFLINE``, ``MAINT_MODE``."""

    camera_categories: List[str]
    """Geographic/regional grouping labels, e.g. ``["Wash. DC"]``."""

    video_url: str
    """
    CHART web portal video page URL.

    Format: ``https://chart.maryland.gov/Video/GetVideo/{id}``
    """

    thumbnail_url: str
    """
    JPEG snapshot URL updated every ~10 seconds via SignalR push.

    Format: ``https://chart.maryland.gov/thumbnails/{id}.jpg``
    """

    stream_url: str
    """
    HLS (HTTP Live Streaming) playlist URL served directly from the CCTV server.

    Format: ``https://{cctv_ip}/rtplive/{id}/playlist.m3u8``

    Use an HLS-capable player (VLC, ffplay, hls.js) to view this stream.
    """

    last_cached: Optional[datetime]
    """UTC timestamp of the last data cache refresh."""

    @property
    def is_online(self) -> bool:
        """Return ``True`` if the camera is reachable and operational."""
        return self.op_status == "OK" and self.comm_mode == "ONLINE"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Camera":
        """Construct a :class:`Camera` from a raw API response dictionary."""
        cam_id = d.get("id", "")
        cctv_ip = d.get("cctvIp", "")
        return cls(
            id=cam_id,
            name=d.get("name", ""),
            description=d.get("description", ""),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            cctv_ip=cctv_ip,
            route_prefix=d.get("routePrefix", ""),
            route_number=int(d.get("routeNumber", 0) or 0),
            mile_post=d.get("milePost"),
            op_status=d.get("opStatus", ""),
            comm_mode=d.get("commMode", ""),
            camera_categories=list(d.get("cameraCategories") or []),
            video_url=(
                d.get("publicVideoURL")
                or f"{_CHART_BASE}/Video/GetVideo/{cam_id}"
            ),
            thumbnail_url=f"{_CHART_BASE}/thumbnails/{cam_id}.jpg",
            stream_url=(
                f"https://{cctv_ip}/rtplive/{cam_id}/playlist.m3u8"
                if cctv_ip
                else ""
            ),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class Lane:
    """Status of a single lane within an incident or closure."""

    lane_type: str
    """``Traffic Lane``, ``Shoulder``, ``Ramp``, etc."""

    lane_description: str
    """Lane identifier, e.g. ``L1``, ``L2``."""

    lane_direction: str
    """Cardinal or relative direction: ``north``, ``east``, ``inner``, etc."""

    lane_status: str
    """``open``, ``closed``, ``partially_closed``."""

    lane_traffic_flow_direction: str
    """``primary`` or ``contraflow``."""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Lane":
        return cls(
            lane_type=d.get("laneType", ""),
            lane_description=d.get("laneDescription", ""),
            lane_direction=d.get("laneDirection", ""),
            lane_status=d.get("laneStatus", ""),
            lane_traffic_flow_direction=d.get("laneTrafficFlowDirection", ""),
        )


@dataclass
class Incident:
    """A traffic incident or event disrupting normal road flow."""

    id: str
    """Unique incident identifier."""

    name: str
    """Short headline, e.g. "Incident @ I-95 INNER LOOP AT EXIT 15A"."""

    description: str
    """Detailed description of the incident."""

    incident_type: str
    """
    Category label: ``Debris In Roadway``, ``Personal Injury``,
    ``Disabled Vehicle``, ``Police Activity``, etc.
    """

    type_code: int
    """Numeric incident type code used internally."""

    lat: float
    """WGS-84 latitude."""

    lon: float
    """WGS-84 longitude."""

    county: str
    """Maryland county where the incident occurred."""

    direction: str
    """Affected travel direction: ``North``, ``South``, ``East``, ``West``, etc."""

    source: str
    """Reporting entity, e.g. ``State Police``, ``CHART``."""

    op_center: str
    """Operations center code, e.g. ``SOC``, ``BSOC``."""

    closed: bool
    """Whether the incident has been cleared/closed."""

    traffic_alert: bool
    """Whether a public traffic alert has been issued."""

    traffic_alert_msg: str
    """Text of the traffic alert message, if any."""

    lanes_status: str
    """Human-readable lane closure summary."""

    lanes: List[Lane]
    """Per-lane status details."""

    participant_on_scene: bool
    """Whether a CHART or responding unit is on scene."""

    vehicles: str
    """Vehicle count description."""

    start_time: Optional[datetime]
    """UTC datetime when the incident was first reported."""

    create_time: Optional[datetime]
    """UTC datetime when the record was created in the system."""

    last_cached: Optional[datetime]
    """UTC timestamp of the last data cache refresh."""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Incident":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            incident_type=d.get("incidentType", ""),
            type_code=int(d.get("type", 0) or 0),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            county=d.get("county", ""),
            direction=d.get("direction", ""),
            source=d.get("source", ""),
            op_center=d.get("opCenter", ""),
            closed=bool(d.get("closed", False)),
            traffic_alert=bool(d.get("trafficAlert", False)),
            traffic_alert_msg=d.get("trafficAlertTextMsg", "") or "",
            lanes_status=d.get("lanesStatus", "") or "",
            lanes=[Lane.from_dict(ln) for ln in (d.get("lanes") or [])],
            participant_on_scene=bool(d.get("participantOnScene", False)),
            vehicles=d.get("vehicles", "") or "",
            start_time=_ts_to_dt(d.get("startDateTime")),
            create_time=_ts_to_dt(d.get("createTime")),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class Closure:
    """An active or planned road closure (work zone / maintenance)."""

    id: str
    """Unique closure identifier (hex string)."""

    name: str
    """Short headline description of the closure."""

    description: str
    """Full closure description."""

    tracking_number: str
    """Internal permit/work-order tracking number, e.g. ``D1-N-WO-2025-1067``."""

    direction: str
    """Affected travel direction."""

    county: str
    """Maryland county."""

    planned: bool
    """``True`` for pre-scheduled work zones; ``False`` for emergency closures."""

    source: str
    """Data source, e.g. ``Lane Closure Permits``."""

    op_center: str
    """Operations center code."""

    lanes_closed: str
    """Summary of closed lanes."""

    lanes_status: str
    """Current lane status string."""

    lanes: List[Lane]
    """Per-lane status details."""

    lat: float
    """WGS-84 latitude of closure midpoint."""

    lon: float
    """WGS-84 longitude of closure midpoint."""

    start_time: Optional[datetime]
    """UTC datetime when the closure started."""

    create_time: Optional[datetime]
    """UTC datetime when the record was created."""

    last_cached: Optional[datetime]
    """UTC timestamp of the last data cache refresh."""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Closure":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            tracking_number=d.get("trackingNumber", "") or "",
            direction=d.get("direction", ""),
            county=d.get("county", ""),
            planned=bool(d.get("planned", False)),
            source=d.get("source", ""),
            op_center=d.get("opCenter", ""),
            lanes_closed=d.get("lanesClosed", "") or "",
            lanes_status=d.get("lanesStatus", "") or "",
            lanes=[Lane.from_dict(ln) for ln in (d.get("lanes") or [])],
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            start_time=_ts_to_dt(d.get("startDateTime")),
            create_time=_ts_to_dt(d.get("createTime")),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class SpeedZone:
    """Directional speed reading from a traffic speed sensor."""

    speed: int
    """Measured speed in MPH."""

    bearing: int
    """Compass bearing in degrees (0–360)."""

    direction: str
    """Cardinal or loop direction: ``NORTH``, ``SOUTH``, ``INNER_LOOP``, etc."""


@dataclass
class SpeedSensor:
    """A traffic speed sensor (TSS) monitoring station."""

    id: str
    """Unique sensor identifier."""

    name: str
    """Sensor name/code, e.g. ``S315017``."""

    description: str
    """Location description, e.g. ``"I-495 NB @ MD 190"``."""

    lat: float
    """WGS-84 latitude."""

    lon: float
    """WGS-84 longitude."""

    speed: float
    """Aggregate speed reading (0.0 if not applicable)."""

    direction: str
    """Primary direction indicator."""

    rotation: Optional[float]
    """Sensor rotation angle in degrees."""

    zones: List[SpeedZone]
    """Directional speed readings, one per monitored lane group."""

    op_status: str
    """``OK``, ``COMM_FAILURE``, ``HARDWARE_FAILURE``."""

    comm_mode: str
    """``ONLINE``, ``OFFLINE``, ``MAINT_MODE``."""

    owning_org: str
    """Owning organisation: ``SHA`` or ``MDTA``."""

    range_only: bool
    """``True`` if this sensor only detects presence (no speed)."""

    last_update: Optional[datetime]
    """UTC datetime of the last sensor data update."""

    last_cached: Optional[datetime]
    """UTC timestamp of the last data cache refresh."""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SpeedSensor":
        zones = [
            SpeedZone(
                speed=int(z.get("speed", 0) or 0),
                bearing=int(z.get("bearing", 0) or 0),
                direction=z.get("direction", ""),
            )
            for z in (d.get("zones") or [])
        ]
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            speed=float(d.get("speed", 0.0) or 0.0),
            direction=d.get("direction", ""),
            rotation=d.get("rotation"),
            zones=zones,
            op_status=d.get("opStatus", ""),
            comm_mode=d.get("commMode", ""),
            owning_org=d.get("owningOrg", ""),
            range_only=bool(d.get("rangeOnly", False)),
            last_update=_ts_to_dt(d.get("lastUpdateTime")),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class DynamicMessageSign:
    """A Dynamic Message Sign (DMS) / Variable Message Sign (VMS) on Maryland roads."""

    id: str
    """Unique sign identifier."""

    name: str
    """Sign name/ID code, e.g. ``8829``."""

    description: str
    """Physical location, e.g. ``"I-95 South, past Ex 80 MD 543, prior to MD 136 at MM 79.5"``."""

    lat: float
    """WGS-84 latitude."""

    lon: float
    """WGS-84 longitude."""

    msg_plain: str
    """Plain-text version of the sign message."""

    msg_multi: str
    """
    NTCIP MULTI-coded message string.

    MULTI codes used by CHART:
      - ``[nl]``        — new line
      - ``[np]``        — new page
      - ``[pt25o0]``    — page time 2.5 s, off time 0 s
      - ``[pt30o0]``    — page time 3.0 s
      - ``[jl3]``       — left justification
      - ``[fo]``        — font tag
    """

    msg_html: str
    """HTML table representation of the sign face."""

    op_status: str
    """``OK``, ``HARDWARE_FAILURE``, ``COMM_FAILURE``, ``HARDWARE_WARNING``."""

    comm_mode: str
    """``ONLINE``, ``OFFLINE``, ``MAINT_MODE``."""

    has_beacons: bool
    """Whether the sign has flashing beacon lights."""

    beacons_enabled: bool
    """Whether the beacons are currently active."""

    last_cached: Optional[datetime]
    """UTC timestamp of the last data cache refresh."""

    @property
    def is_active(self) -> bool:
        """Return ``True`` if the sign is operational with a non-blank message."""
        return self.op_status == "OK" and bool(self.msg_plain.strip())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DynamicMessageSign":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            msg_plain=d.get("msgPlain", "") or "",
            msg_multi=d.get("msgMulti", "") or "",
            msg_html=d.get("msgHTML", "") or "",
            op_status=d.get("opStatus", ""),
            comm_mode=d.get("commMode", ""),
            has_beacons=bool(d.get("hasBeacons", False)),
            beacons_enabled=bool(d.get("beaconsEnabled", False)),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class WeatherStation:
    """
    A Road Weather Information System (RWIS) / Environmental Sensor Station.

    These stations report atmospheric and pavement conditions used to manage
    winter operations and driver advisories.
    """

    id: str
    """Unique station identifier."""

    name: str
    """Station name, e.g. ``"MD 20 at MD 21"``."""

    description: str
    """Location description."""

    lat: float
    """WGS-84 latitude."""

    lon: float
    """WGS-84 longitude."""

    air_temp: str
    """Air temperature string with units, e.g. ``"48F"``."""

    dew_point: str
    """Dew point temperature string, e.g. ``"36F"``."""

    relative_humidity: str
    """Relative humidity percentage string, e.g. ``"63%"``."""

    wind_description: str
    """Wind speed and direction string, e.g. ``"NE 7 MPH"``."""

    gust_speed: str
    """Wind gust speed string, e.g. ``"15 MPH"``."""

    precip_type: str
    """Precipitation type: ``"None"``, ``"Rain"``, ``"Snow"``, ``"Freezing Rain"``, etc."""

    pavement_temp: str
    """Pavement temperature range string, e.g. ``"58F to 58F"``."""

    full_rwis: bool
    """
    ``True`` if this is a full RWIS station (multiple sensors).
    ``False`` indicates a limited / single-sensor installation.
    """

    last_update: Optional[datetime]
    """UTC datetime of the last sensor reading."""

    last_cached: Optional[datetime]
    """UTC timestamp of the last data cache refresh."""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WeatherStation":
        return cls(
            id=str(d.get("id", "")),
            name=d.get("name", ""),
            description=d.get("description", ""),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            air_temp=d.get("airTemp", "") or "",
            dew_point=d.get("dewPoint", "") or "",
            relative_humidity=d.get("relativeHumidity", "") or "",
            wind_description=d.get("windDescription", "") or "",
            gust_speed=d.get("gustSpeed", "") or "",
            precip_type=d.get("precipitationType", "") or "",
            pavement_temp=d.get("pavementTemp", "") or "",
            full_rwis=bool(d.get("fullRWIS", False)),
            last_update=_ts_to_dt(d.get("lastUpdate")),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class SnowEmergency:
    """A declared snow emergency in a Maryland county."""

    id: str
    name: str
    description: str
    county: str
    lat: float
    lon: float
    active: bool
    start_time: Optional[datetime]
    last_cached: Optional[datetime]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SnowEmergency":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            county=d.get("county", ""),
            lat=float(d.get("lat", 0.0)),
            lon=float(d.get("lon", 0.0)),
            active=bool(d.get("active", True)),
            start_time=_ts_to_dt(d.get("startDateTime")),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


@dataclass
class SystemMessage:
    """A system-wide message displayed on the CHART portal."""

    id: str
    name: str
    message_text: str
    """HTML-formatted message body."""

    ordinal: int
    """Display sort order."""

    active: bool
    disable_rollup: bool
    message_date: Optional[datetime]
    last_cached: Optional[datetime]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SystemMessage":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            message_text=d.get("messageText", "") or "",
            ordinal=int(d.get("ordinal", 0) or 0),
            active=bool(d.get("active", True)),
            disable_rollup=bool(d.get("disableRollup", False)),
            message_date=_ts_to_dt(d.get("messageDate")),
            last_cached=_ts_to_dt(d.get("lastCachedDataUpdateTime")),
        )


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------


class CHARTClient:
    """
    Client for the Maryland CHART (Coordinated Highways Action Response Team)
    public traffic data API.

    All data is publicly accessible — no API key or authentication is required.
    Data is refreshed by the CHART backend on a ~60-second cycle for most feeds.

    Parameters
    ----------
    timeout:
        HTTP socket timeout in seconds. Default is 30.

    Examples
    --------
    >>> client = CHARTClient()
    >>> cameras = client.get_cameras()
    >>> online = [c for c in cameras if c.is_online]
    >>> print(f"{len(online)} cameras online out of {len(cameras)} total")
    """

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Camera feeds
    # ------------------------------------------------------------------

    def get_cameras(self) -> List[Camera]:
        """
        Retrieve all traffic cameras on the Maryland road network.

        Returns a list of :class:`Camera` objects with location, stream URL,
        thumbnail URL, and operational status.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getCameraMapDataJSON.do

        Returns
        -------
        List[Camera]
            All cameras; currently ~400+ statewide.

        Notes
        -----
        Stream URLs follow the pattern::

            https://{cctv_ip}/rtplive/{camera_id}/playlist.m3u8

        The CCTV servers are named ``strmr{N}.sha.maryland.gov``.
        Thumbnails are served at::

            https://chart.maryland.gov/thumbnails/{camera_id}.jpg

        Thumbnail images are pushed via SignalR when new frames arrive,
        typically every 10–30 seconds per camera.
        """
        url = f"{_EXPORT_BASE}/getCameraMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [Camera.from_dict(r) for r in records]

    def get_cameras_by_route(
        self, route_prefix: str, route_number: int
    ) -> List[Camera]:
        """
        Filter cameras to a specific highway route.

        Parameters
        ----------
        route_prefix:
            Route type: ``"IS"`` (Interstate), ``"US"`` (US Route),
            ``"MD"`` (Maryland State Route).
        route_number:
            Numeric route number, e.g. ``95``, ``50``, ``270``.

        Returns
        -------
        List[Camera]
            Cameras on the requested route, sorted by mile post.

        Examples
        --------
        >>> client = CHARTClient()
        >>> i95_cams = client.get_cameras_by_route("IS", 95)
        """
        cameras = self.get_cameras()
        filtered = [
            c
            for c in cameras
            if c.route_prefix.upper() == route_prefix.upper()
            and c.route_number == route_number
        ]
        return sorted(
            filtered,
            key=lambda c: (c.mile_post is None, c.mile_post or 0),
        )

    def get_cameras_by_region(self, region: str) -> List[Camera]:
        """
        Filter cameras to a named geographic region.

        Parameters
        ----------
        region:
            Region label (case-insensitive substring match). Common values:
            ``"Wash. DC"``, ``"Baltimore"``, ``"Annapolis"``,
            ``"Eastern Shore"``, ``"Western MD"``, ``"Southern MD"``.

        Returns
        -------
        List[Camera]
        """
        region_lower = region.lower()
        cameras = self.get_cameras()
        return [
            c
            for c in cameras
            if any(region_lower in cat.lower() for cat in c.camera_categories)
        ]

    # ------------------------------------------------------------------
    # Incident feeds
    # ------------------------------------------------------------------

    def get_incidents(self) -> List[Incident]:
        """
        Retrieve all active traffic incidents (non-closure events).

        Includes debris, disabled vehicles, accidents, police activity,
        flooding, and other real-time roadway events.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getEventMapDataJSON.do

        Returns
        -------
        List[Incident]
        """
        url = f"{_EXPORT_BASE}/getEventMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [Incident.from_dict(r) for r in records]

    def get_closures(self) -> List[Closure]:
        """
        Retrieve all active and planned road closures (work zones).

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getActiveClosureMapDataJSON.do

        Returns
        -------
        List[Closure]
        """
        url = f"{_EXPORT_BASE}/getActiveClosureMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [Closure.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Speed sensors
    # ------------------------------------------------------------------

    def get_speed_sensors(self) -> List[SpeedSensor]:
        """
        Retrieve all Traffic Speed Sensor (TSS) stations.

        Each station reports speeds per directional lane group.
        Data is collected by both SHA and MDTA.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getTSSMapDataJSON.do

        Returns
        -------
        List[SpeedSensor]
        """
        url = f"{_EXPORT_BASE}/getTSSMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [SpeedSensor.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Dynamic Message Signs
    # ------------------------------------------------------------------

    def get_message_signs(self) -> List[DynamicMessageSign]:
        """
        Retrieve all Dynamic Message Signs (DMS / VMS) on Maryland roads.

        Signs display travel times, lane closures, weather alerts, Amber
        Alerts, and general public messages. Messages are encoded in both
        NTCIP MULTI format and plain text.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getDMSMapDataJSON.do

        Returns
        -------
        List[DynamicMessageSign]
        """
        url = f"{_EXPORT_BASE}/getDMSMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [DynamicMessageSign.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Weather stations
    # ------------------------------------------------------------------

    def get_weather_stations(self) -> List[WeatherStation]:
        """
        Retrieve Road Weather Information System (RWIS) station data.

        Stations report air temperature, dew point, humidity, wind speed,
        precipitation type, and pavement temperature.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getRWISMapDataJSON.do

        Returns
        -------
        List[WeatherStation]
            All ~130+ RWIS stations statewide.
        """
        url = f"{_EXPORT_BASE}/getRWISMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [WeatherStation.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Snow emergency plans
    # ------------------------------------------------------------------

    def get_snow_emergencies(self) -> List[SnowEmergency]:
        """
        Retrieve active and recently lifted snow emergency plans by county.

        During winter weather events, counties may declare snow emergencies
        that restrict parking and activate emergency snow routes.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getSEPMapDataJSON.do

        Returns
        -------
        List[SnowEmergency]
            Empty list when no emergencies are active.
        """
        url = f"{_EXPORT_BASE}/getSEPMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [SnowEmergency.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Road conditions (IPS)
    # ------------------------------------------------------------------

    def get_road_conditions(self) -> List[Dict[str, Any]]:
        """
        Retrieve weather-related road conditions reported by maintenance shops.

        Returns raw dictionaries because this feed is only populated during
        active winter weather events and the schema varies by condition type.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getIPSMapDataJSON.do

        Returns
        -------
        List[Dict[str, Any]]
            Raw condition records; empty list outside winter events.
        """
        url = f"{_EXPORT_BASE}/getIPSMapDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        return _unwrap(payload)

    # ------------------------------------------------------------------
    # Work Zone Data Exchange (WZDx GeoJSON)
    # ------------------------------------------------------------------

    def get_wzdx(self) -> Dict[str, Any]:
        """
        Retrieve the Maryland DOT WZDx v4.1 GeoJSON work-zone feed.

        This feed is published by MDOT and aggregated by the RITIS (Regional
        Integrated Transportation Information System) WZDx filter service.
        It is compliant with the USDOT Work Zone Data Exchange specification.

        Feed URL
        --------
        https://filter.ritis.org/wzdx_v4.1/mdot.geojson

        Returns
        -------
        Dict[str, Any]
            A GeoJSON ``FeatureCollection``.  Each feature represents a work
            zone with geometry (``LineString`` or ``MultiPoint``), properties
            including ``road_names``, ``direction``, ``vehicle_impact``,
            ``start_date``, ``end_date``, and per-lane status arrays.

        Notes
        -----
        The feed license is CC0 1.0 (public domain).
        Update frequency is approximately every 60 seconds.
        """
        return _fetch_geojson(_WZDX_URL, self.timeout)

    # ------------------------------------------------------------------
    # System messages
    # ------------------------------------------------------------------

    def get_system_messages(self) -> List[SystemMessage]:
        """
        Retrieve active system-wide messages displayed on the CHART portal.

        These messages announce scheduled maintenance windows, service
        outages, and other operational notices.

        Endpoint
        --------
        GET https://chartexp1.sha.maryland.gov/CHARTExportClientService/getWebMessagesDataJSON.do

        Returns
        -------
        List[SystemMessage]
        """
        url = f"{_EXPORT_BASE}/getWebMessagesDataJSON.do"
        payload = _fetch_json(url, self.timeout)
        records = _unwrap(payload)
        return [SystemMessage.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Convenience aggregation
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """
        Fetch a high-level summary of current Maryland traffic conditions.

        Makes parallel sequential requests to all primary endpoints and
        returns counts and highlights.  Useful for dashboards.

        Returns
        -------
        Dict[str, Any]
            Dictionary with keys:
            ``cameras_total``, ``cameras_online``,
            ``incidents_total``, ``incidents_with_alert``,
            ``closures_total``, ``closures_planned``,
            ``dms_total``, ``dms_active``,
            ``speed_sensors_total``, ``speed_sensors_online``,
            ``weather_stations_total``,
            ``snow_emergencies_total``,
            ``fetched_at``.
        """
        cameras = self.get_cameras()
        incidents = self.get_incidents()
        closures = self.get_closures()
        signs = self.get_message_signs()
        sensors = self.get_speed_sensors()
        weather = self.get_weather_stations()
        snow = self.get_snow_emergencies()

        return {
            "cameras_total": len(cameras),
            "cameras_online": sum(1 for c in cameras if c.is_online),
            "incidents_total": len(incidents),
            "incidents_with_alert": sum(1 for i in incidents if i.traffic_alert),
            "closures_total": len(closures),
            "closures_planned": sum(1 for c in closures if c.planned),
            "dms_total": len(signs),
            "dms_active": sum(1 for s in signs if s.is_active),
            "speed_sensors_total": len(sensors),
            "speed_sensors_online": sum(
                1 for s in sensors if s.comm_mode == "ONLINE"
            ),
            "weather_stations_total": len(weather),
            "snow_emergencies_total": len(snow),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------


def _print_cameras(client: CHARTClient) -> None:
    cameras = client.get_cameras()
    online = [c for c in cameras if c.is_online]
    print(f"\n=== Traffic Cameras ({len(cameras)} total, {len(online)} online) ===")
    for cam in cameras[:10]:
        status = "ONLINE" if cam.is_online else f"OFFLINE [{cam.op_status}]"
        print(f"  [{status}] {cam.description}")
        print(f"           Thumbnail: {cam.thumbnail_url}")
        print(f"           Stream:    {cam.stream_url}")
    if len(cameras) > 10:
        print(f"  ... and {len(cameras) - 10} more cameras")


def _print_incidents(client: CHARTClient) -> None:
    incidents = client.get_incidents()
    print(f"\n=== Active Incidents ({len(incidents)} total) ===")
    if not incidents:
        print("  No incidents reported.")
        return
    for inc in incidents[:10]:
        alert_flag = " [ALERT]" if inc.traffic_alert else ""
        print(f"  {inc.incident_type}{alert_flag}")
        print(f"    Location: {inc.county} County — {inc.direction}")
        print(f"    Details:  {inc.name}")
        if inc.lanes_status:
            print(f"    Lanes:    {inc.lanes_status}")
    if len(incidents) > 10:
        print(f"  ... and {len(incidents) - 10} more incidents")


def _print_closures(client: CHARTClient) -> None:
    closures = client.get_closures()
    print(f"\n=== Active Closures ({len(closures)} total) ===")
    if not closures:
        print("  No closures reported.")
        return
    for cl in closures[:10]:
        kind = "Planned" if cl.planned else "Emergency"
        print(f"  [{kind}] {cl.name}")
        print(f"    County:    {cl.county} — {cl.direction}")
        print(f"    Lanes:     {cl.lanes_closed}")
        if cl.tracking_number:
            print(f"    Tracking:  {cl.tracking_number}")
    if len(closures) > 10:
        print(f"  ... and {len(closures) - 10} more closures")


def _print_dms(client: CHARTClient) -> None:
    signs = client.get_message_signs()
    active = [s for s in signs if s.is_active]
    print(f"\n=== Dynamic Message Signs ({len(signs)} total, {len(active)} with active message) ===")
    for sign in active[:10]:
        print(f"  [{sign.name}] {sign.description}")
        print(f"    Message: {sign.msg_plain}")
    if len(active) > 10:
        print(f"  ... and {len(active) - 10} more active signs")


def _print_speeds(client: CHARTClient) -> None:
    sensors = client.get_speed_sensors()
    online = [s for s in sensors if s.comm_mode == "ONLINE"]
    print(f"\n=== Speed Sensors ({len(sensors)} total, {len(online)} online) ===")
    # Show a sample of sensors with speed readings
    with_speed = [s for s in online if s.zones][:10]
    for sensor in with_speed:
        speeds = ", ".join(
            f"{z.direction} {z.speed} MPH" for z in sensor.zones
        )
        print(f"  {sensor.description}: {speeds}")
    if not with_speed:
        print("  No speed data available right now.")


def _print_weather(client: CHARTClient) -> None:
    stations = client.get_weather_stations()
    print(f"\n=== Weather Stations ({len(stations)} total) ===")
    for stn in stations[:10]:
        print(f"  {stn.name}")
        print(
            f"    Air: {stn.air_temp}  Wind: {stn.wind_description}  "
            f"Precip: {stn.precip_type}  Pavement: {stn.pavement_temp}"
        )
    if len(stations) > 10:
        print(f"  ... and {len(stations) - 10} more stations")


def _print_snow(client: CHARTClient) -> None:
    emergencies = client.get_snow_emergencies()
    print(f"\n=== Snow Emergencies ({len(emergencies)} active) ===")
    if not emergencies:
        print("  No snow emergencies currently declared.")
    for em in emergencies:
        print(f"  {em.county} County — {em.name}")


def _print_wzdx(client: CHARTClient) -> None:
    geojson = client.get_wzdx()
    features = geojson.get("features", [])
    print(f"\n=== WZDx Work Zones ({len(features)} features) ===")
    for feat in features[:5]:
        props = feat.get("properties", {})
        road = ", ".join(props.get("road_names") or [])
        direction = props.get("direction", "")
        impact = props.get("vehicle_impact", "")
        print(f"  {road} {direction} — {impact}")
    if len(features) > 5:
        print(f"  ... and {len(features) - 5} more work zones")


def _print_messages(client: CHARTClient) -> None:
    messages = client.get_system_messages()
    print(f"\n=== System Messages ({len(messages)}) ===")
    if not messages:
        print("  No active system messages.")
    for msg in messages:
        print(f"  [{msg.id[:8]}...] (ordinal={msg.ordinal})")
        # Strip basic HTML tags for terminal display
        text = msg.message_text.replace("<p>", "").replace("</p>", "").strip()
        print(f"  {text}")


_COMMAND_MAP = {
    "cameras": _print_cameras,
    "incidents": _print_incidents,
    "closures": _print_closures,
    "dms": _print_dms,
    "speeds": _print_speeds,
    "weather": _print_weather,
    "snow": _print_snow,
    "wzdx": _print_wzdx,
    "messages": _print_messages,
}


def main() -> None:
    """Entry point for the CLI demo."""
    commands = list(_COMMAND_MAP.keys())
    usage = (
        f"Usage: python {sys.argv[0]} <command>\n"
        f"Commands: {', '.join(commands)}\n\n"
        "Examples:\n"
        f"  python {sys.argv[0]} cameras\n"
        f"  python {sys.argv[0]} incidents\n"
        f"  python {sys.argv[0]} dms\n"
    )

    if len(sys.argv) < 2 or sys.argv[1] not in _COMMAND_MAP:
        print(usage)
        # Default: print the full summary
        print("Running summary of all data feeds...\n")
        client = CHARTClient()
        try:
            summary = client.get_summary()
        except (urllib.error.URLError, ValueError, RuntimeError) as exc:
            print(f"Error fetching summary: {exc}", file=sys.stderr)
            sys.exit(1)
        print("Maryland CHART — Live Traffic Summary")
        print("=" * 42)
        for key, val in summary.items():
            label = key.replace("_", " ").title()
            print(f"  {label:<32} {val}")
        return

    client = CHARTClient()
    cmd = sys.argv[1]
    try:
        _COMMAND_MAP[cmd](client)
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, RuntimeError) as exc:
        print(f"Data error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
