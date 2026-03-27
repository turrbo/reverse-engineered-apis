"""
MoDOT (Missouri Department of Transportation) Traffic Information Client
========================================================================

A production-quality Python client for the MoDOT Traveler Information System
(traveler.modot.org). Built using Python stdlib only (urllib, json, dataclasses).

Reverse-engineered from:
  - https://traveler.modot.org/map/
  - https://traveler.modot.org/map/js/site.js
  - https://traveler.modot.org/map/js/config.json

All endpoints are public, unauthenticated JSON feeds served over HTTPS.

Author: Reverse-engineered 2026-03-27
License: Public Domain (data from MoDOT, a public agency)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Constants & base URLs
# ---------------------------------------------------------------------------

BASE_URL = "https://traveler.modot.org"

# Feed endpoints (JSON, refreshed every ~60 seconds by the live map)
FEED_CAMERAS_STREAMING   = f"{BASE_URL}/timconfig/feed/desktop/StreamingCams2.json"
FEED_MESSAGES            = f"{BASE_URL}/timconfig/feed/desktop/message.v2.json"
FEED_LINES               = f"{BASE_URL}/timconfig/feed/desktop/LinesV1.json"
FEED_MESSAGE_BOARDS      = f"{BASE_URL}/timconfig/feed/desktop/MsgBrdV1.json"
FEED_ROAD_CONDITIONS     = f"{BASE_URL}/timconfig/feed/desktop/RcCondV1.json"
FEED_ROAD_COND_GEOMETRY  = f"{BASE_URL}/timconfig/feed/desktop/RcGeomV1.json"
FEED_BYPASS_PAVEMENT     = f"{BASE_URL}/timconfig/feed/desktop/BPRV1.json"
FEED_CAMERAS_SNAPSHOT    = f"{BASE_URL}/map/js/snapshot.json"

# TIS service REST endpoints
TISVC_MARKER_FROM_LATLON  = f"{BASE_URL}/tisvc/api/Tms/MarkerFromLatLon2"   # ?lat=&lon=&dpp=
TISVC_LATLON_FROM_MARKER  = f"{BASE_URL}/tisvc/api/Tms/LatLonFromMarker"    # ?twid=&mkr=
TISVC_GET_GEOMETRY        = f"{BASE_URL}/tisvc/api/Tms/GetGeometry"         # ?type=&id=

# Weather radar PNG tiles (10 frames, index 0-9; 9 = most recent)
RADAR_TILE_URL_TEMPLATE   = f"{BASE_URL}/timconfig/wxugradr{{index}}.png"

# CDN streaming server pattern
# Cameras are served from: https://sfs0N-traveler.modot.mo.gov/rtplive/MODOT_CAM_NNN/playlist.m3u8
STREAMING_CDN_HOSTS = ["sfs01", "sfs02", "sfs03", "sfs04", "sfs07"]

# Snapshot JPEG pattern
SNAPSHOT_IMAGE_URL_PREFIX = f"{BASE_URL}/traffic_camera_snapshots"

# MoDOT District codes
DISTRICTS = {
    "NW": "Northwest",
    "NE": "Northeast",
    "KC": "Kansas City",
    "CD": "Central",
    "SL": "St. Louis",
    "SW": "Southwest",
    "SE": "Southeast",
    "ALL": "All Districts",
}

# Major Type (MT) codes used in message.v2.json
MAJOR_TYPES = {
    "WZ": "Work Zone",
    "TI": "Traffic Impact / Incident",
    "CL": "Commuter Lot",
}

# Level of Impact (LOI) codes
LEVEL_OF_IMPACT = {
    "CLOSED":          "Road Closed",
    "HIGH":            "Expect Delays",
    "MEDIUM":          "Possible Delays",
    "FUTURE":          "Future Work Zone",
    "EXPECT DELAYS":   "Expect Delays",
    "POSSIBLE DELAYS": "Possible Delays",
    "CL":              "Commuter Lot",
}

DEFAULT_USER_AGENT = (
    "MoDOT-Python-Client/1.0 "
    "(github.com/example/modot-client; for research/public-data use)"
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Coordinates:
    """Geographic point in WGS-84 (EPSG:4326)."""
    longitude: float
    latitude: float

    def __str__(self) -> str:
        return f"({self.latitude:.6f}, {self.longitude:.6f})"


@dataclass
class StreamingCamera:
    """
    A live traffic camera that provides an HLS (HTTP Live Streaming) video feed.

    The ``stream_url`` is an Apple HLS master playlist (``.m3u8``). It can be
    played with VLC, ffplay, or any HLS-capable player::

        vlc "https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8"

    Fields
    ------
    location : str
        Human-readable description, e.g. "141 AT BIG BEND, MM 17.5"
    coordinates : Coordinates
        WGS-84 longitude/latitude of the camera.
    stream_url : str
        HLS master playlist URL.  Always ends in ``/playlist.m3u8``.
    camera_id : str or None
        Extracted camera ID such as ``"MODOT_CAM_209"``.
    cdn_host : str or None
        CDN server prefix, e.g. ``"sfs02"``.
    rtmp_url : str or None
        Legacy RTMP stream URL (usually null in live data).
    """
    location: str
    coordinates: Coordinates
    stream_url: str
    camera_id: Optional[str] = None
    cdn_host: Optional[str] = None
    rtmp_url: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "StreamingCamera":
        stream_url = data.get("html", "")
        # Parse camera ID and CDN host from the URL
        camera_id = None
        cdn_host = None
        if stream_url:
            # URL pattern: https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8
            parts = stream_url.split("/")
            for part in parts:
                if part.startswith("MODOT_CAM_"):
                    camera_id = part
                    break
            host = stream_url.split("//")[-1].split("/")[0]  # e.g. sfs02-traveler.modot.mo.gov
            cdn_host = host.split("-")[0]  # e.g. sfs02

        return cls(
            location=data.get("location", ""),
            coordinates=Coordinates(
                longitude=float(data.get("x", 0)),
                latitude=float(data.get("y", 0)),
            ),
            stream_url=stream_url,
            camera_id=camera_id,
            cdn_host=cdn_host,
            rtmp_url=data.get("rtmp"),
        )

    def chunklist_url(self) -> Optional[str]:
        """
        Fetch the HLS master playlist and return the first chunklist URL.

        Returns None if the stream is unreachable or malformed.
        """
        try:
            req = urllib.request.Request(
                self.stream_url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            base = self.stream_url.rsplit("/", 1)[0]
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    if line.startswith("http"):
                        return line
                    return f"{base}/{line}"
        except Exception:
            return None
        return None


@dataclass
class SnapshotCamera:
    """
    A traffic camera that provides periodic JPEG snapshot images.

    The snapshot URL is a static JPEG refreshed by the server (typically
    every 1-5 minutes). Append ``?t=<unix_timestamp>`` to bust the cache.

    Fields
    ------
    id : int
        Numeric camera identifier.
    caption : str
        Human-readable label, e.g. ``"I-44 @ Rolla Highway Patrol"``.
    coordinates : Coordinates
        WGS-84 coordinates.
    image_path : str
        Relative URL path on traveler.modot.org.
    image_url : str
        Fully-qualified JPEG URL.
    """
    id: int
    caption: str
    coordinates: Coordinates
    image_path: str
    image_url: str

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotCamera":
        path = data.get("url", "")
        return cls(
            id=int(data.get("id", 0)),
            caption=data.get("caption", ""),
            coordinates=Coordinates(
                longitude=float(data.get("location", {}).get("x", 0)),
                latitude=float(data.get("location", {}).get("y", 0)),
            ),
            image_path=path,
            image_url=f"{BASE_URL}{path}",
        )

    def fresh_url(self) -> str:
        """Return image URL with a cache-busting timestamp parameter."""
        return f"{self.image_url}?t={int(time.time())}"


@dataclass
class TrafficEvent:
    """
    A traffic event (work zone, incident, or commuter lot notice).

    Sourced from ``message.v2.json``.  Each event has a geographic point,
    a major type code, a minor sub-type, and a level of impact.

    Fields
    ------
    oid : int
        Object ID (unique within a single feed snapshot).
    major_type : str
        One of ``"WZ"`` (Work Zone), ``"TI"`` (Traffic Impact/Incident),
        ``"CL"`` (Commuter Lot).
    minor_subtype : str
        Finer classification, e.g. ``"WZ"``, ``"PLANNED"``, ``"IMPACT"``.
    level_of_impact : str
        One of ``"CLOSED"``, ``"HIGH"``, ``"MEDIUM"``, ``"FUTURE"``, etc.
    coordinates : Coordinates
        Point location of the event.
    message_html : str
        Full HTML description of the event.
    message_short : str
        Compact HTML description (one sentence).
    message_label : str
        Short road/location label, e.g. ``"MO 291 N JACKSON"``.
    """
    oid: int
    major_type: str
    minor_subtype: str
    level_of_impact: str
    coordinates: Coordinates
    message_html: str
    message_short: str
    message_label: str

    @property
    def major_type_label(self) -> str:
        return MAJOR_TYPES.get(self.major_type, self.major_type)

    @property
    def impact_label(self) -> str:
        return LEVEL_OF_IMPACT.get(self.level_of_impact, self.level_of_impact)

    @classmethod
    def from_dict(cls, data: dict) -> "TrafficEvent":
        geom = data.get("GEOM", {})
        return cls(
            oid=int(data.get("OID", 0)),
            major_type=data.get("MT", ""),
            minor_subtype=data.get("MST", ""),
            level_of_impact=data.get("LOI", ""),
            coordinates=Coordinates(
                longitude=float(geom.get("x", 0)),
                latitude=float(geom.get("y", 0)),
            ),
            message_html=data.get("MSG", ""),
            message_short=data.get("MSGS", ""),
            message_label=data.get("MSGL", ""),
        )


@dataclass
class EventLine:
    """
    A polyline geometry associated with a traffic event (work zone or incident).

    Sourced from ``LinesV1.json``.  The ``paths`` field contains one or more
    lists of ``[longitude, latitude]`` coordinate pairs.

    Fields
    ------
    major_type : str
        ``"WZ"``, ``"TI"``, or ``"CL"``.
    minor_subtype : str
        Sub-classification.
    level_of_impact : str
        Severity code.
    paths : list of list of [float, float]
        Polyline vertices as ``[[lon, lat], ...]``.
    """
    major_type: str
    minor_subtype: str
    level_of_impact: str
    paths: List[List[List[float]]]

    @classmethod
    def from_dict(cls, data: dict) -> "EventLine":
        geom = data.get("GEOM", {})
        return cls(
            major_type=data.get("MT", ""),
            minor_subtype=data.get("MST", ""),
            level_of_impact=data.get("LOI", ""),
            paths=geom.get("paths", []),
        )


@dataclass
class MessageBoard:
    """
    A variable message sign (VMS / dynamic message sign) with current display text.

    Sourced from ``MsgBrdV1.json``.

    Fields
    ------
    message : str
        Text currently shown on the sign (may contain ``<br />`` tags).
    device : str
        Sign identifier/location description.
    posted : str or None
        Posted timestamp string (may be null).
    coordinates : Coordinates
        Sign location.
    image_url : str
        URL to an animated GIF or PNG showing the sign face.
    """
    message: str
    device: str
    posted: Optional[str]
    coordinates: Coordinates
    image_url: str

    @classmethod
    def from_dict(cls, data: dict) -> "MessageBoard":
        return cls(
            message=data.get("msg", ""),
            device=data.get("dev", ""),
            posted=data.get("pst"),
            coordinates=Coordinates(
                longitude=float(data.get("x", 0)),
                latitude=float(data.get("y", 0)),
            ),
            image_url=data.get("imageurl", ""),
        )


@dataclass
class MileMarkerResult:
    """
    Result from a reverse-geocode of lat/lon to a highway mile marker.

    From ``/tisvc/api/Tms/MarkerFromLatLon2``.
    """
    travelway_id: int
    sign_text: str
    latitude: float
    longitude: float

    @classmethod
    def from_dict(cls, data: dict) -> "MileMarkerResult":
        return cls(
            travelway_id=int(data.get("TravelwayId", 0)),
            sign_text=data.get("SignText", ""),
            latitude=float(data.get("Latitude", 0)),
            longitude=float(data.get("Longitude", 0)),
        )


@dataclass
class LatLonResult:
    """
    Result from resolving a travelway + mile marker to coordinates.

    From ``/tisvc/api/Tms/LatLonFromMarker``.
    """
    travelway_id: int
    sign_text: str
    latitude: float
    longitude: float

    @classmethod
    def from_dict(cls, data: dict) -> "LatLonResult":
        return cls(
            travelway_id=int(data.get("TravelwayId", 0)),
            sign_text=data.get("SignText", ""),
            latitude=float(data.get("Latitude", 0)),
            longitude=float(data.get("Longitude", 0)),
        )


@dataclass
class RadarFrame:
    """
    One frame of the weather radar overlay (PNG image, georeferenced).

    MoDOT provides 10 radar frames (indices 0-9) composited over Missouri.
    Index 9 is always the most recent.

    The image covers the bounding box::

        xmin=-98.4375, ymin=31.82, xmax=-87.1875, ymax=43.07 (WGS-84)

    Fields
    ------
    index : int
        Frame index 0-9 (9 = newest).
    url : str
        Cacheable URL.  Append ``?t=<timestamp>`` to force a fresh fetch.
    """
    index: int
    url: str

    def fresh_url(self) -> str:
        """Return radar URL with a cache-busting timestamp parameter."""
        return f"{self.url}?t={int(time.time())}"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 30, retries: int = 3) -> object:
    """
    Fetch a URL and return the parsed JSON body.

    Parameters
    ----------
    url : str
        Full URL to fetch.
    timeout : int
        Per-attempt timeout in seconds.
    retries : int
        Number of retry attempts on transient errors (5xx, connection errors).

    Returns
    -------
    object
        Parsed JSON (dict, list, etc.).

    Raises
    ------
    urllib.error.HTTPError
        On 4xx responses (not retried).
    RuntimeError
        If all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise  # client errors are not retried
            last_exc = exc
        except Exception as exc:  # network errors
            last_exc = exc
        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # exponential back-off: 1s, 2s
    raise RuntimeError(
        f"Failed to fetch {url!r} after {retries} attempts: {last_exc}"
    )


# ---------------------------------------------------------------------------
# MoDOT Client
# ---------------------------------------------------------------------------

class MoDOTClient:
    """
    Client for the MoDOT Traveler Information System.

    All methods make live HTTP requests.  The feeds are refreshed by MoDOT's
    servers approximately every 60 seconds.  There is no authentication,
    API key, rate-limiting header, or session requirement — these are
    public JSON feeds.

    Usage
    -----
    ::

        from modot_client import MoDOTClient

        client = MoDOTClient()

        # List all streaming cameras
        cameras = client.get_streaming_cameras()
        print(cameras[0].stream_url)

        # Filter by bounding box (Kansas City area)
        kc_cams = client.get_streaming_cameras(
            min_lat=38.4, max_lat=39.5,
            min_lon=-95.1, max_lon=-93.8
        )

        # Current traffic events
        events = client.get_traffic_events(major_type="WZ", level="CLOSED")
        for e in events:
            print(e.message_label, e.impact_label)

        # Nearest mile marker
        mm = client.get_marker_from_latlon(lat=38.627, lon=-90.199)
        print(mm.sign_text)

    Parameters
    ----------
    timeout : int
        HTTP request timeout in seconds (default: 30).
    retries : int
        Number of retry attempts on transient errors (default: 3).
    """

    def __init__(self, timeout: int = 30, retries: int = 3) -> None:
        self.timeout = timeout
        self.retries = retries

    def _get(self, url: str) -> object:
        return _fetch_json(url, timeout=self.timeout, retries=self.retries)

    # ------------------------------------------------------------------
    # Camera feeds
    # ------------------------------------------------------------------

    def get_streaming_cameras(
        self,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
        location_filter: Optional[str] = None,
    ) -> List[StreamingCamera]:
        """
        Return all streaming (HLS/live video) traffic cameras.

        Each camera provides an HLS ``.m3u8`` master playlist URL suitable
        for playback with VLC, ffmpeg, or any HLS-capable player.

        The CDN servers are:
          ``sfs01-traveler.modot.mo.gov`` through ``sfs07-traveler.modot.mo.gov``

        Stream URL pattern::

            https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8

        Parameters
        ----------
        min_lat, max_lat, min_lon, max_lon : float, optional
            Bounding box filter (WGS-84 degrees).
        location_filter : str, optional
            Case-insensitive substring match against ``camera.location``.

        Returns
        -------
        list of StreamingCamera
            Sorted alphabetically by location.

        Examples
        --------
        ::

            # All cameras
            all_cams = client.get_streaming_cameras()

            # Kansas City area
            kc_cams = client.get_streaming_cameras(
                min_lat=38.4, max_lat=39.5,
                min_lon=-95.1, max_lon=-93.8
            )

            # Cameras on I-70
            i70 = client.get_streaming_cameras(location_filter="70")
        """
        raw: list = self._get(FEED_CAMERAS_STREAMING)  # type: ignore[assignment]
        cameras = [StreamingCamera.from_dict(d) for d in raw]

        if min_lat is not None:
            cameras = [c for c in cameras if c.coordinates.latitude >= min_lat]
        if max_lat is not None:
            cameras = [c for c in cameras if c.coordinates.latitude <= max_lat]
        if min_lon is not None:
            cameras = [c for c in cameras if c.coordinates.longitude >= min_lon]
        if max_lon is not None:
            cameras = [c for c in cameras if c.coordinates.longitude <= max_lon]
        if location_filter is not None:
            flt = location_filter.upper()
            cameras = [c for c in cameras if flt in c.location.upper()]

        cameras.sort(key=lambda c: c.location)
        return cameras

    def get_snapshot_cameras(
        self,
        location_filter: Optional[str] = None,
    ) -> List[SnapshotCamera]:
        """
        Return all static-snapshot (JPEG) traffic cameras.

        These are cameras that provide periodic JPEG images rather than
        live video streams.  The JPEG is refreshed server-side every few
        minutes.  Use :meth:`SnapshotCamera.fresh_url` to add a
        cache-busting timestamp.

        Image URL pattern::

            https://traveler.modot.org/traffic_camera_snapshots/<name>/<name>.jpg

        Parameters
        ----------
        location_filter : str, optional
            Case-insensitive substring match against ``camera.caption``.

        Returns
        -------
        list of SnapshotCamera

        Examples
        --------
        ::

            snaps = client.get_snapshot_cameras()
            for c in snaps:
                print(c.caption, c.fresh_url())
        """
        raw: dict = self._get(FEED_CAMERAS_SNAPSHOT)  # type: ignore[assignment]
        cameras = [SnapshotCamera.from_dict(d) for d in raw.get("cameras", [])]

        if location_filter is not None:
            flt = location_filter.upper()
            cameras = [c for c in cameras if flt in c.caption.upper()]

        cameras.sort(key=lambda c: c.caption)
        return cameras

    # ------------------------------------------------------------------
    # Traffic events (work zones, incidents, commuter lots)
    # ------------------------------------------------------------------

    def get_traffic_events(
        self,
        major_type: Optional[str] = None,
        level: Optional[str] = None,
        location_filter: Optional[str] = None,
    ) -> List[TrafficEvent]:
        """
        Return current traffic events: work zones, incidents, commuter lots.

        Data source: ``message.v2.json`` (~60-second refresh).

        Parameters
        ----------
        major_type : str, optional
            Filter by major type code: ``"WZ"`` (work zone),
            ``"TI"`` (traffic impact/incident), ``"CL"`` (commuter lot).
        level : str, optional
            Filter by level of impact: ``"CLOSED"``, ``"HIGH"``,
            ``"MEDIUM"``, ``"FUTURE"``, ``"EXPECT DELAYS"``,
            ``"POSSIBLE DELAYS"``.
        location_filter : str, optional
            Case-insensitive substring match against the short
            road/location label (``message_label``).

        Returns
        -------
        list of TrafficEvent

        Examples
        --------
        ::

            # All road closures
            closures = client.get_traffic_events(level="CLOSED")

            # Work zones with high impact
            high_wz = client.get_traffic_events(major_type="WZ", level="HIGH")

            # Incidents on I-70
            incidents = client.get_traffic_events(
                major_type="TI", location_filter="IS 70"
            )
        """
        raw: list = self._get(FEED_MESSAGES)  # type: ignore[assignment]
        events = [TrafficEvent.from_dict(d) for d in raw]

        if major_type is not None:
            mt = major_type.upper()
            events = [e for e in events if e.major_type == mt]
        if level is not None:
            lv = level.upper()
            events = [e for e in events if e.level_of_impact == lv]
        if location_filter is not None:
            flt = location_filter.upper()
            events = [e for e in events if flt in e.message_label.upper()]

        return events

    def get_event_lines(
        self,
        major_type: Optional[str] = None,
        level: Optional[str] = None,
    ) -> List[EventLine]:
        """
        Return polyline geometries for traffic events.

        Use alongside :meth:`get_traffic_events` for GIS/mapping applications.
        Each ``EventLine`` contains a list of coordinate paths (GeoJSON-style).

        Parameters
        ----------
        major_type : str, optional
            Filter by major type (``"WZ"``, ``"TI"``, ``"CL"``).
        level : str, optional
            Filter by level of impact.

        Returns
        -------
        list of EventLine
        """
        raw: list = self._get(FEED_LINES)  # type: ignore[assignment]
        lines = [EventLine.from_dict(d) for d in raw]

        if major_type is not None:
            mt = major_type.upper()
            lines = [ln for ln in lines if ln.major_type == mt]
        if level is not None:
            lv = level.upper()
            lines = [ln for ln in lines if ln.level_of_impact == lv]

        return lines

    # ------------------------------------------------------------------
    # Dynamic message signs / variable message signs
    # ------------------------------------------------------------------

    def get_message_boards(
        self,
        message_filter: Optional[str] = None,
    ) -> List[MessageBoard]:
        """
        Return all variable message sign (VMS/DMS) current readings.

        Each board reports the text currently displayed on the sign plus
        an image URL for a rendered sign face (animated GIF/PNG, served
        by KC Scout for Kansas City region signs).

        Parameters
        ----------
        message_filter : str, optional
            Case-insensitive substring match against sign message text.

        Returns
        -------
        list of MessageBoard

        Examples
        --------
        ::

            boards = client.get_message_boards()
            for b in boards:
                if b.message:
                    print(b.device, '->', b.message.replace('<br />', ' | '))
        """
        raw: list = self._get(FEED_MESSAGE_BOARDS)  # type: ignore[assignment]
        boards = [MessageBoard.from_dict(d) for d in raw]

        if message_filter is not None:
            flt = message_filter.upper()
            boards = [b for b in boards if flt in b.message.upper()]

        return boards

    # ------------------------------------------------------------------
    # TIS geocoding services
    # ------------------------------------------------------------------

    def get_marker_from_latlon(
        self,
        lat: float,
        lon: float,
        degrees_per_pixel: float = 0.001,
    ) -> MileMarkerResult:
        """
        Reverse-geocode a lat/lon coordinate to the nearest highway mile marker.

        The ``degrees_per_pixel`` parameter controls the snap radius — smaller
        values return more precise results; larger values increase the search
        radius.  The default (``0.001``) corresponds roughly to ~100 m.

        Parameters
        ----------
        lat : float
            Latitude in decimal degrees (WGS-84).
        lon : float
            Longitude in decimal degrees (WGS-84).
        degrees_per_pixel : float
            Snap tolerance in degrees (default ``0.001``).

        Returns
        -------
        MileMarkerResult

        Examples
        --------
        ::

            # Downtown St. Louis (near Gateway Arch)
            result = client.get_marker_from_latlon(lat=38.627, lon=-90.199)
            print(result.sign_text)   # e.g. "WEST IS 64 MILE 39.8"
        """
        url = (
            f"{TISVC_MARKER_FROM_LATLON}"
            f"?lat={lat}&lon={lon}&dpp={degrees_per_pixel}"
        )
        data: dict = self._get(url)  # type: ignore[assignment]
        return MileMarkerResult.from_dict(data)

    def get_latlon_from_marker(
        self,
        travelway_id: int,
        mile_marker: float,
    ) -> LatLonResult:
        """
        Convert a travelway ID and mile marker number to lat/lon coordinates.

        Travelway IDs are Missouri's internal IDs for named roadways and
        directions of travel.  Common IDs are listed in
        ``MoDOTClient.TRAVELWAY_IDS``.

        Parameters
        ----------
        travelway_id : int
            MoDOT internal travelway identifier.
        mile_marker : float
            Mile marker number along the travelway.

        Returns
        -------
        LatLonResult

        Examples
        --------
        ::

            # I-70 Eastbound at Mile 100
            result = client.get_latlon_from_marker(travelway_id=19, mile_marker=100)
            print(result.sign_text)   # "EAST IS 70 MILE 100.0"
            print(result.latitude, result.longitude)
        """
        url = f"{TISVC_LATLON_FROM_MARKER}?twid={travelway_id}&mkr={mile_marker}"
        data: dict = self._get(url)  # type: ignore[assignment]
        return LatLonResult.from_dict(data)

    # ------------------------------------------------------------------
    # Weather radar
    # ------------------------------------------------------------------

    def get_radar_frames(self) -> List[RadarFrame]:
        """
        Return the 10 available weather radar overlay frames.

        Each frame is a georeferenced PNG image covering the area::

            xmin=-98.4375  ymin=31.82  xmax=-87.1875  ymax=43.07

        Frame index 9 is the most recent; frame 0 is the oldest.
        Frames are updated approximately every 10 minutes.

        Returns
        -------
        list of RadarFrame
            Ordered from oldest (index 0) to newest (index 9).

        Examples
        --------
        ::

            frames = client.get_radar_frames()
            latest = frames[-1]
            print(latest.fresh_url())  # URL with cache-bust timestamp
        """
        return [
            RadarFrame(
                index=i,
                url=RADAR_TILE_URL_TEMPLATE.format(index=i),
            )
            for i in range(10)
        ]

    # ------------------------------------------------------------------
    # Travelway constants
    # ------------------------------------------------------------------

    #: Common MoDOT travelway IDs for use with :meth:`get_latlon_from_marker`.
    TRAVELWAY_IDS = {
        "IS 44 E":  9,
        "IS 44 W":  10,
        "IS 55 N":  12,
        "IS 55 S":  13,
        "IS 57 N":  264,
        "IS 70 E":  19,
        "IS 70 W":  3506,
        "IS 29 N":  5865,
        "IS 29 S":  5878,
        "IS 35 N":  4984,
        "IS 35 S":  4986,
        "IS 64 E":  6372,
        "IS 64 W":  6373,
        "IS 155 N": 1105,
        "IS 155 S": 1104,
        "IS 170 E": 6163,
        "IS 170 W": 6164,
        "IS 255 N": 6512,
        "IS 255 S": 6513,
        "IS 270 E": 6135,
        "IS 270 W": 6136,
        "IS 435 N": 6039,
        "IS 435 S": 6042,
        "IS 470 E": 6037,
        "IS 470 W": 6038,
        "IS 49 N":  1036008,
        "IS 49 S":  1036007,
        "IS 635 N": 6065,
        "IS 635 S": 6064,
        "IS 670 E": 6062,
        "US 65 N":  2010,
        "US 65 S":  2009,
    }


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def cli_demo() -> None:
    """
    Command-line demonstration of the MoDOT client.

    Exercises all major API endpoints and prints a human-readable summary.
    """
    client = MoDOTClient(timeout=30, retries=3)

    # 1. Streaming cameras overview
    _print_section("Streaming Cameras (sample of 10)")
    print("Fetching from:", FEED_CAMERAS_STREAMING)
    cameras = client.get_streaming_cameras()
    print(f"Total streaming cameras: {len(cameras)}")
    cdn_dist: dict = {}
    for cam in cameras:
        if cam.cdn_host:
            cdn_dist[cam.cdn_host] = cdn_dist.get(cam.cdn_host, 0) + 1
    print("CDN server distribution:", cdn_dist)
    print()
    for cam in cameras[:10]:
        print(f"  [{cam.camera_id}] {cam.location}")
        print(f"    Coords: {cam.coordinates}")
        print(f"    Stream: {cam.stream_url}")

    # 2. Cameras near St. Louis
    _print_section("Streaming Cameras: St. Louis area (bbox)")
    stl_cams = client.get_streaming_cameras(
        min_lat=38.35, max_lat=38.96,
        min_lon=-90.89, max_lon=-90.02,
    )
    print(f"Cameras in St. Louis bbox: {len(stl_cams)}")
    for cam in stl_cams[:5]:
        print(f"  {cam.location}: {cam.stream_url}")

    # 3. Cameras on I-70
    _print_section("Streaming Cameras: I-70 filter")
    i70_cams = client.get_streaming_cameras(location_filter="70 AT")
    print(f"I-70 cameras: {len(i70_cams)}")
    for cam in i70_cams[:5]:
        print(f"  {cam.location}")

    # 4. Snapshot cameras
    _print_section("Snapshot (JPEG) Cameras")
    print("Fetching from:", FEED_CAMERAS_SNAPSHOT)
    snaps = client.get_snapshot_cameras()
    print(f"Total snapshot cameras: {len(snaps)}")
    for snap in snaps[:5]:
        print(f"  [{snap.id}] {snap.caption}")
        print(f"    Image: {snap.fresh_url()}")

    # 5. Traffic events summary
    _print_section("Traffic Events Summary")
    print("Fetching from:", FEED_MESSAGES)
    all_events = client.get_traffic_events()
    print(f"Total active events: {len(all_events)}")
    type_counts: dict = {}
    loi_counts: dict = {}
    for ev in all_events:
        type_counts[ev.major_type] = type_counts.get(ev.major_type, 0) + 1
        loi_counts[ev.level_of_impact] = loi_counts.get(ev.level_of_impact, 0) + 1
    print("By major type:", {k: f"{v} ({MAJOR_TYPES.get(k, k)})" for k, v in sorted(type_counts.items())})
    print("By level of impact:", dict(sorted(loi_counts.items())))

    # 6. Road closures
    _print_section("Road Closures (CLOSED level)")
    closures = client.get_traffic_events(level="CLOSED")
    print(f"Active road closures: {len(closures)}")
    for ev in closures[:5]:
        print(f"  [{ev.major_type_label}] {ev.message_label} - {ev.impact_label}")

    # 7. High-impact work zones
    _print_section("High-Impact Work Zones")
    high_wz = client.get_traffic_events(major_type="WZ", level="HIGH")
    print(f"High-impact work zones: {len(high_wz)}")
    for ev in high_wz[:5]:
        print(f"  {ev.message_label}")

    # 8. Event lines
    _print_section("Event Polylines")
    print("Fetching from:", FEED_LINES)
    lines = client.get_event_lines()
    print(f"Total event polylines: {len(lines)}")
    if lines:
        sample = lines[0]
        print(f"  Sample: MT={sample.major_type} LOI={sample.level_of_impact}")
        print(f"  Paths: {len(sample.paths)} path(s), {len(sample.paths[0]) if sample.paths else 0} vertices in first")

    # 9. Dynamic message signs
    _print_section("Variable Message Signs (sample of 5)")
    print("Fetching from:", FEED_MESSAGE_BOARDS)
    boards = client.get_message_boards()
    print(f"Total message boards: {len(boards)}")
    for b in boards[:5]:
        msg = b.message.replace("<br />", " | ").strip()
        print(f"  {b.device}: {msg!r}")
        print(f"    Image: {b.image_url}")

    # 10. Mile marker geocoding
    _print_section("Mile Marker Geocoding")
    print("Testing: lat=38.627, lon=-90.199 (downtown St. Louis)")
    try:
        mm = client.get_marker_from_latlon(lat=38.627, lon=-90.199)
        print(f"  Travelway ID: {mm.travelway_id}")
        print(f"  Sign text:    {mm.sign_text}")
        print(f"  Lat/Lon:      ({mm.latitude:.6f}, {mm.longitude:.6f})")
    except Exception as exc:
        print(f"  Error: {exc}")

    print("\nTesting: travelway_id=19 (I-70 East), mile_marker=100")
    try:
        ll = client.get_latlon_from_marker(travelway_id=19, mile_marker=100)
        print(f"  Sign text: {ll.sign_text}")
        print(f"  Lat/Lon:   ({ll.latitude:.6f}, {ll.longitude:.6f})")
    except Exception as exc:
        print(f"  Error: {exc}")

    # 11. Radar frames
    _print_section("Weather Radar Frames")
    frames = client.get_radar_frames()
    print(f"Radar frames available: {len(frames)}")
    for frame in frames:
        print(f"  Frame {frame.index}: {frame.fresh_url()}")

    _print_section("Demo Complete")
    print("\nAll public MoDOT API endpoints tested successfully.")
    print("No authentication, API keys, or sessions required.")
    print("Data refreshes approximately every 60 seconds.")


def main() -> None:
    """Entry point for CLI demo."""
    import argparse

    parser = argparse.ArgumentParser(
        description="MoDOT Traveler Information System - Python Client Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python modot_client.py demo              Run full API demo
  python modot_client.py cameras           List all streaming cameras
  python modot_client.py cameras --filter 70    I-70 cameras
  python modot_client.py events            List all traffic events
  python modot_client.py events --type WZ --level CLOSED
  python modot_client.py marker 38.627 -90.199
  python modot_client.py boards            Variable message signs
  python modot_client.py radar             Weather radar frame URLs
        """,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("demo", help="Run full API demonstration")

    p_cams = sub.add_parser("cameras", help="List streaming cameras")
    p_cams.add_argument("--filter", help="Location text filter")
    p_cams.add_argument("--count", type=int, default=20, help="Max to show")

    p_ev = sub.add_parser("events", help="List traffic events")
    p_ev.add_argument("--type", help="Major type: WZ, TI, CL")
    p_ev.add_argument("--level", help="Level: CLOSED, HIGH, MEDIUM, FUTURE")
    p_ev.add_argument("--filter", help="Location text filter")
    p_ev.add_argument("--count", type=int, default=20, help="Max to show")

    p_mm = sub.add_parser("marker", help="Get mile marker from lat/lon")
    p_mm.add_argument("lat", type=float, help="Latitude")
    p_mm.add_argument("lon", type=float, help="Longitude")

    sub.add_parser("boards", help="List variable message signs")
    sub.add_parser("radar", help="Get weather radar frame URLs")
    sub.add_parser("snapshots", help="List snapshot cameras")

    args = parser.parse_args()
    client = MoDOTClient()

    if args.command == "demo" or args.command is None:
        cli_demo()
        return

    if args.command == "cameras":
        cams = client.get_streaming_cameras(location_filter=args.filter)
        print(f"Streaming cameras ({len(cams)} total):")
        for c in cams[: args.count]:
            print(f"  [{c.camera_id}] {c.location}")
            print(f"    {c.stream_url}")

    elif args.command == "snapshots":
        snaps = client.get_snapshot_cameras()
        print(f"Snapshot cameras ({len(snaps)} total):")
        for s in snaps[:20]:
            print(f"  [{s.id}] {s.caption}: {s.image_url}")

    elif args.command == "events":
        events = client.get_traffic_events(
            major_type=args.type,
            level=args.level,
            location_filter=args.filter,
        )
        print(f"Traffic events ({len(events)} total):")
        for e in events[: args.count]:
            print(f"  [{e.major_type_label}] [{e.impact_label}] {e.message_label}")

    elif args.command == "marker":
        result = client.get_marker_from_latlon(lat=args.lat, lon=args.lon)
        print(f"Travelway ID: {result.travelway_id}")
        print(f"Sign text:    {result.sign_text}")
        print(f"Coordinates:  ({result.latitude:.6f}, {result.longitude:.6f})")

    elif args.command == "boards":
        boards = client.get_message_boards()
        print(f"Variable message signs ({len(boards)} total):")
        for b in boards[:20]:
            msg = b.message.replace("<br />", " | ").strip()
            print(f"  {b.device}: {msg!r}")

    elif args.command == "radar":
        frames = client.get_radar_frames()
        print("Weather radar frames (index 9 = newest):")
        for f in frames:
            print(f"  [{f.index}] {f.fresh_url()}")


if __name__ == "__main__":
    main()
