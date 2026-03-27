#!/usr/bin/env python3
"""
TxDOT / DriveTexas Traffic Camera & Road Conditions API Client
==============================================================

Reverse-engineered from https://drivetexas.org (React/Redux app backed by MapLarge).

Architecture
------------
DriveTexas uses MapLarge (https://dtx-e-cdn.maplarge.com) as its geospatial data
platform.  All traffic data is served through a single generic endpoint:

    GET https://dtx-e-cdn.maplarge.com/Api/ProcessDirect?request=<JSON>

The ``request`` query parameter is a URL-encoded JSON object with this shape::

    {
        "action": "table/query",
        "query": {
            "sqlselect": ["field1", "field2", ...],   # or ["*"]
            "table":     "appgeo/<TABLE_NAME>",
            "take":      500,
            "start":     0,
            "where":     ["field==\"value\""]          # optional filter
        }
    }

The response is JSON::

    {
        "success": true,
        "data": {
            "data": {                        # columnar arrays (one list per field)
                "field1": [...],
                "field2": [...]
            },
            "totals": {"Records": 3410},     # total matching rows
            "tablename": "appgeo/cameraPoint/..."
        }
    }

The API is publicly accessible with no API key required.  Requests must include
``Origin: https://drivetexas.org`` and ``Referer: https://drivetexas.org/``
headers to pass CORS/origin checks.

Discovered Tables
-----------------
- ``cameraPoint``          – 3,410 live traffic cameras (HLS streams + RTSP)
- ``conditionsPoint``      – 664  current road conditions / incidents
- ``conditionsLine``       – 659  current road condition line segments
- ``futureConditionsPoint``– 296  planned future conditions (scheduled work)
- ``futureConditionsLine`` – 296  planned future condition line segments
- ``floodPoint``           – Flood gauge sensor readings (0 when inactive)
- ``contraflow_dissolve``  – 10   contraflow/evacuation route segments
- ``evaculanes``           – 6    evacuation lane assignments

Additional endpoints
--------------------
- Config JSON: ``GET https://storage.googleapis.com/drivetexas/info.json``
  Returns site metadata: active splash screen, redirect flags, modal notices.

Camera Stream URLs
------------------
Each camera record exposes multiple stream formats:

- ``httpsurl``   – HLS playlist (.m3u8) over HTTPS, e.g.:
  ``https://s70.us-east-1.skyvdn.com:443/rtplive/<CAM_ID>/playlist.m3u8``
- ``iosurl``     – Same HLS URL (iOS-optimised alias)
- ``rtspurl``    – RTSP stream, e.g.: ``rtsp://s70.us-east-1.skyvdn.com:554/rtplive/<CAM_ID>``
- ``rtmpurl``    – RTMP stream, e.g.: ``rtmp://s70.us-east-1.skyvdn.com:1935/rtplive/<CAM_ID>``
- ``clspsurl``   – SkyVDN CLSPS proprietary protocol
- ``prerollurl`` – HLS pre-roll / buffered segment URL
- ``imageurl``   – Snapshot PNG (internal URL; replace ``localhost`` with the
  static host if building a proxy — the app stores these internally and serves
  them via the MapLarge grid/UTFGrid layer at zoom >= 10)

Usage
-----
::

    from txdot_client import TxDOTClient

    client = TxDOTClient()

    # List all cameras in Houston
    cameras = client.get_cameras(jurisdiction="Houston", take=20)
    for cam in cameras:
        print(cam.name, cam.description, cam.hls_url)

    # Get current road conditions
    conditions = client.get_conditions(take=50)
    for cond in conditions:
        print(cond.route, cond.description)

CLI
---
Run as a module::

    python txdot_client.py cameras --jurisdiction Dallas --take 10
    python txdot_client.py conditions --take 20
    python txdot_client.py info
    python txdot_client.py stats

"""

from __future__ import annotations

import json
import sys
import argparse
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field, fields as dc_fields
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "https://dtx-e-cdn.maplarge.com/Api/ProcessDirect"
_ACCOUNT = "appgeo"
_ORIGIN = "https://drivetexas.org"
_INFO_URL = "https://storage.googleapis.com/drivetexas/info.json"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# MapLarge table names
TABLE_CAMERAS = "cameraPoint"
TABLE_CONDITIONS = "conditionsPoint"
TABLE_CONDITIONS_LINE = "conditionsLine"
TABLE_FUTURE_CONDITIONS = "futureConditionsPoint"
TABLE_FUTURE_CONDITIONS_LINE = "futureConditionsLine"
TABLE_FLOOD = "floodPoint"
TABLE_CONTRAFLOW = "contraflow_dissolve"
TABLE_EVACULATION_LANES = "evaculanes"

# Camera field names exposed by the cameraPoint table
_CAMERA_FIELDS = [
    "name",
    "description",
    "jurisdiction",
    "route",
    "direction",
    "mrm",
    "active",
    "problemstream",
    "lastUpdated",
    "id",
    "imageurl",
    "httpsurl",
    "iosurl",
    "rtspurl",
    "rtmpurl",
    "rtmpurl",
    "clspsurl",
    "prerollurl",
    "deviceid",
    "distance",
]

# Condition field names
_CONDITION_FIELDS = [
    "HCRSCONDID",
    "RTENM",
    "RDWAYNM",
    "CONDDSCR",
    "CONDSTARTTS",
    "CONDENDTS",
    "CNSTRNTTYPECD",
    "TRVLDRCTCD",
    "TXDOTCOUNTYNBR",
    "FROMDISPMS",
    "TODISPMS",
    "FROMRMKRNBR",
    "TORMKRNBR",
    "CONDLMTFROMDSCR",
    "CONDLMTTODSCR",
    "CNSTRNTDETOURFLAG",
    "CNSTRNTDELAYFLAG",
    "CNSTRNTMETROFLAG",
    "lastUpdated",
    "sort",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """A single TxDOT traffic camera.

    Attributes
    ----------
    name:
        Unique camera identifier, e.g. ``TX_FTW_085``.
    description:
        Human-readable location label, e.g. ``FM1709 @ Brock``.
    jurisdiction:
        TxDOT district / city, e.g. ``Houston``, ``Dallas``, ``Austin``.
    route:
        Primary road this camera monitors, e.g. ``IH0035``, ``FM1709``.
    direction:
        Cardinal direction of travel being monitored (``East``, ``North``, etc.).
    mrm:
        Milepost reference marker.
    active:
        ``1`` if stream is active, ``0`` if offline.
    problem_stream:
        Non-zero indicates a known streaming problem.
    last_updated:
        Epoch millisecond timestamp of last data refresh.
    camera_id:
        Internal numeric ID.
    image_url:
        Static thumbnail URL (internal ``localhost`` host — replace for proxy use).
    hls_url:
        HLS (.m3u8) stream URL — playable by VLC, ffmpeg, Safari, HLS.js, etc.
    ios_url:
        iOS-compatible HLS URL (usually identical to ``hls_url``).
    rtsp_url:
        RTSP stream URL for IP camera software (port 554).
    rtmp_url:
        RTMP stream URL for streaming encoders (port 1935).
    clsps_url:
        SkyVDN CLSPS proprietary protocol URL.
    preroll_url:
        HLS pre-roll / buffer segment URL.
    device_id:
        Hardware device identifier.
    distance:
        Distance annotation (often empty).
    """

    name: str = ""
    description: str = ""
    jurisdiction: str = ""
    route: str = ""
    direction: str = ""
    mrm: float = 0.0
    active: int = 1
    problem_stream: int = 0
    last_updated: int = 0
    camera_id: int = 0
    image_url: str = ""
    hls_url: str = ""
    ios_url: str = ""
    rtsp_url: str = ""
    rtmp_url: str = ""
    clsps_url: str = ""
    preroll_url: str = ""
    device_id: int = 0
    distance: str = ""

    @property
    def is_active(self) -> bool:
        """Return True when the camera stream is currently active."""
        return bool(self.active) and not bool(self.problem_stream)

    @property
    def last_updated_dt(self) -> Optional[datetime]:
        """Return last_updated as a UTC datetime, or None if zero."""
        if not self.last_updated:
            return None
        return datetime.fromtimestamp(self.last_updated / 1000, tz=timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation of this camera."""
        return {f.name: getattr(self, f.name) for f in dc_fields(self)}


@dataclass
class RoadCondition:
    """A current or future road condition / incident segment.

    Attributes
    ----------
    condition_id:
        Internal HCRS condition identifier.
    route:
        Route name, e.g. ``IH0035``, ``US0077``, ``FM2818``.
    roadway_name:
        Human-readable roadway name.
    description:
        Full condition narrative text (may contain HTML).
    start_ts:
        Condition start time as epoch milliseconds.
    end_ts:
        Condition end time as epoch milliseconds (0 = no end date).
    condition_type:
        Type code — ``C`` construction, ``A`` accident, ``D`` damage, etc.
    travel_direction:
        ``EW`` (east-west), ``NS`` (north-south).
    county_nbr:
        TxDOT county number.
    from_milepost:
        Start milepost (decimal miles).
    to_milepost:
        End milepost (decimal miles).
    from_marker:
        Reference marker at start.
    to_marker:
        Reference marker at end.
    from_description:
        Human-readable start location.
    to_description:
        Human-readable end location.
    detour_flag:
        Non-zero if detour information is available.
    delay_flag:
        Non-zero if motorist delays are expected.
    metro_flag:
        Non-zero if condition is in a metro area.
    last_updated:
        Epoch millisecond timestamp of last data refresh.
    sort_order:
        Display sort order (higher = more severe).
    """

    condition_id: str = ""
    route: str = ""
    roadway_name: str = ""
    description: str = ""
    start_ts: int = 0
    end_ts: int = 0
    condition_type: str = ""
    travel_direction: str = ""
    county_nbr: int = 0
    from_milepost: float = 0.0
    to_milepost: float = 0.0
    from_marker: str = ""
    to_marker: str = ""
    from_description: str = ""
    to_description: str = ""
    detour_flag: int = 0
    delay_flag: int = 0
    metro_flag: int = 0
    last_updated: int = 0
    sort_order: int = 0

    # Human-readable condition type labels
    _TYPE_LABELS: Dict[str, str] = field(default_factory=lambda: {
        "C": "Construction",
        "A": "Accident",
        "D": "Damage",
        "I": "Ice/Snow",
        "F": "Flooding",
        "O": "Other",
        "L": "Closure",
    }, repr=False, compare=False)

    @property
    def condition_type_label(self) -> str:
        """Human-readable condition type string."""
        return self._TYPE_LABELS.get(self.condition_type, self.condition_type)

    @property
    def start_dt(self) -> Optional[datetime]:
        """Return start_ts as UTC datetime, or None if unset."""
        if not self.start_ts:
            return None
        return datetime.fromtimestamp(self.start_ts / 1000, tz=timezone.utc)

    @property
    def end_dt(self) -> Optional[datetime]:
        """Return end_ts as UTC datetime, or None if unset."""
        if not self.end_ts:
            return None
        return datetime.fromtimestamp(self.end_ts / 1000, tz=timezone.utc)

    @property
    def expects_delays(self) -> bool:
        """True if motorist delays are expected."""
        return bool(self.delay_flag)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary representation of this condition."""
        return {f.name: getattr(self, f.name) for f in dc_fields(self)
                if f.name != "_TYPE_LABELS"}


@dataclass
class SiteInfo:
    """DriveTexas site configuration and status.

    Attributes
    ----------
    working:
        Whether the site/data is operational.
    splash_screen:
        Current alert or splash screen message (may be empty).
    showing:
        Display mode flag (3 = normal operation).
    deactivated:
        List of deactivated features.
    date:
        Configuration publish date as epoch milliseconds.
    modal:
        Whether a modal notice should be shown.
    redirect:
        Redirect instruction if the site is being redirected.
    """

    working: bool = True
    splash_screen: str = ""
    showing: int = 3
    deactivated: List[str] = field(default_factory=list)
    date: int = 0
    modal: bool = False
    redirect: Optional[str] = None

    @property
    def date_dt(self) -> Optional[datetime]:
        """Return config publish date as UTC datetime, or None if unset."""
        if not self.date:
            return None
        return datetime.fromtimestamp(self.date / 1000, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Core API transport
# ---------------------------------------------------------------------------

class MapLargeError(Exception):
    """Raised when the MapLarge API returns an error."""


def _http_get(url: str, timeout: int = 30) -> bytes:
    """Perform an HTTP GET with appropriate browser-like headers.

    Parameters
    ----------
    url:
        Full URL to fetch.
    timeout:
        Request timeout in seconds.

    Returns
    -------
    bytes
        Raw response body.

    Raises
    ------
    MapLargeError
        On HTTP errors or network failures.
    """
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": _ORIGIN,
            "Referer": _ORIGIN + "/",
            "User-Agent": _USER_AGENT,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        raise MapLargeError(
            f"HTTP {exc.code} from {url}: {exc.reason}  body={body!r}"
        ) from exc
    except urllib.error.URLError as exc:
        raise MapLargeError(f"Network error fetching {url}: {exc.reason}") from exc


def _maplarge_query(
    table: str,
    fields: List[str],
    *,
    take: int = 500,
    start: int = 0,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Execute a MapLarge ``table/query`` action.

    Parameters
    ----------
    table:
        Table name within the ``appgeo`` account, e.g. ``cameraPoint``.
    fields:
        List of field names to return.  Use ``["*"]`` for all fields.
    take:
        Maximum number of rows to return (max 500 per call).
    start:
        Zero-based row offset for pagination.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    dict
        Parsed JSON response from the API.

    Raises
    ------
    MapLargeError
        If the API indicates a failure (``success == false``).

    Notes
    -----
    Server-side ``where`` filtering is not supported by this public API
    endpoint (all filter expressions cause HTTP 500).  Filtering is
    performed client-side after fetching data pages.
    """
    query_obj: Dict[str, Any] = {
        "action": "table/query",
        "query": {
            "sqlselect": fields,
            "start": start,
            "table": f"{_ACCOUNT}/{table}",
            "take": take,
        },
    }
    params = urllib.parse.urlencode(
        {"request": json.dumps(query_obj, separators=(",", ":"))},
    )
    url = f"{_BASE_URL}?{params}"
    raw = _http_get(url, timeout=timeout)
    resp = json.loads(raw)

    if not resp.get("success"):
        errors = resp.get("errors", [])
        raise MapLargeError(f"MapLarge query failed: {errors}")

    return resp


def _columnar_to_rows(data: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """Convert MapLarge columnar response (dict of lists) to a list of dicts.

    MapLarge returns data as parallel arrays keyed by field name::

        {"name": ["cam1", "cam2"], "route": ["IH35", "US290"]}

    This function transposes it into a list of row dicts::

        [{"name": "cam1", "route": "IH35"}, {"name": "cam2", "route": "US290"}]

    Parameters
    ----------
    data:
        The ``data["data"]`` inner dict from a MapLarge response.

    Returns
    -------
    list[dict]
        One dict per record.
    """
    if not data:
        return []
    keys = list(data.keys())
    if not keys:
        return []
    length = len(data[keys[0]])
    return [{k: data[k][i] if i < len(data[k]) else None for k in keys}
            for i in range(length)]


# ---------------------------------------------------------------------------
# Domain builders
# ---------------------------------------------------------------------------

def _row_to_camera(row: Dict[str, Any]) -> Camera:
    """Build a :class:`Camera` dataclass from a MapLarge row dict."""
    return Camera(
        name=row.get("name") or "",
        description=row.get("description") or "",
        jurisdiction=row.get("jurisdiction") or "",
        route=row.get("route") or "",
        direction=row.get("direction") or "",
        mrm=float(row.get("mrm") or 0),
        active=int(row.get("active") or 0),
        problem_stream=int(row.get("problemstream") or 0),
        last_updated=int(row.get("lastUpdated") or 0),
        camera_id=int(row.get("id") or 0),
        image_url=row.get("imageurl") or "",
        hls_url=row.get("httpsurl") or "",
        ios_url=row.get("iosurl") or "",
        rtsp_url=row.get("rtspurl") or "",
        rtmp_url=row.get("rtmpurl") or "",
        clsps_url=row.get("clspsurl") or "",
        preroll_url=row.get("prerollurl") or "",
        device_id=int(row.get("deviceid") or 0),
        distance=row.get("distance") or "",
    )


def _row_to_condition(row: Dict[str, Any]) -> RoadCondition:
    """Build a :class:`RoadCondition` dataclass from a MapLarge row dict."""
    return RoadCondition(
        condition_id=str(row.get("HCRSCONDID") or ""),
        route=row.get("RTENM") or "",
        roadway_name=row.get("RDWAYNM") or "",
        description=row.get("CONDDSCR") or "",
        start_ts=int(row.get("CONDSTARTTS") or 0),
        end_ts=int(row.get("CONDENDTS") or 0),
        condition_type=row.get("CNSTRNTTYPECD") or "",
        travel_direction=row.get("TRVLDRCTCD") or "",
        county_nbr=int(row.get("TXDOTCOUNTYNBR") or 0),
        from_milepost=float(row.get("FROMDISPMS") or 0),
        to_milepost=float(row.get("TODISPMS") or 0),
        from_marker=str(row.get("FROMRMKRNBR") or ""),
        to_marker=str(row.get("TORMKRNBR") or ""),
        from_description=row.get("CONDLMTFROMDSCR") or "",
        to_description=row.get("CONDLMTTODSCR") or "",
        detour_flag=int(row.get("CNSTRNTDETOURFLAG") or 0),
        delay_flag=int(row.get("CNSTRNTDELAYFLAG") or 0),
        metro_flag=int(row.get("CNSTRNTMETROFLAG") or 0),
        last_updated=int(row.get("lastUpdated") or 0),
        sort_order=int(row.get("sort") or 0),
    )


# ---------------------------------------------------------------------------
# High-level client
# ---------------------------------------------------------------------------

class TxDOTClient:
    """High-level client for the TxDOT / DriveTexas traffic data API.

    All data originates from the MapLarge geospatial platform instance
    deployed at ``dtx-e-cdn.maplarge.com`` by AppGeo on behalf of TxDOT.

    **Important — filtering note**: The public MapLarge endpoint does not
    support server-side ``where`` clause filtering (all filter expressions
    return HTTP 500).  Methods that accept filter parameters (``jurisdiction``,
    ``route``, ``active_only``, etc.) fetch full pages from the API and apply
    filters client-side in Python.  For large filtered sets (e.g. all cameras
    in one district) this may require fetching multiple 500-record pages, which
    is handled transparently by :meth:`iter_cameras` and :meth:`iter_conditions`.

    Parameters
    ----------
    timeout:
        Default HTTP request timeout in seconds.

    Examples
    --------
    >>> client = TxDOTClient()
    >>> cameras = client.get_cameras(jurisdiction="Austin", take=10)
    >>> for cam in cameras:
    ...     print(cam.name, cam.hls_url)

    >>> conditions = client.get_conditions(route="IH0035", take=20)
    >>> for cond in conditions:
    ...     print(cond.route, cond.condition_type_label, cond.description[:80])
    """

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Camera methods
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        *,
        jurisdiction: Optional[str] = None,
        route: Optional[str] = None,
        active_only: bool = False,
        take: int = 500,
        start: int = 0,
    ) -> List[Camera]:
        """Return a list of traffic cameras.

        Filters are applied client-side.  For filtered results, the method
        fetches pages until ``take`` matching cameras are found (or all
        records are exhausted).  For unfiltered requests, a single API call
        is made.

        Parameters
        ----------
        jurisdiction:
            Filter by TxDOT district city, e.g. ``"Houston"``, ``"Dallas"``,
            ``"Austin"``, ``"Ft Worth"``, ``"San Antonio"``, ``"El Paso"``,
            ``"Beaumont"``, ``"Corpus Christi"``, ``"Odessa"``.
        route:
            Filter by route name, e.g. ``"IH0035"``, ``"US0290"``.
        active_only:
            When True, exclude cameras with ``active == 0``.
        take:
            Maximum number of cameras to return.
        start:
            Zero-based logical offset (applied after client-side filtering).

        Returns
        -------
        list[Camera]
        """
        has_filter = bool(jurisdiction or route or active_only)
        if not has_filter:
            # Fast path — single API call, no client-side filtering needed.
            resp = _maplarge_query(
                TABLE_CAMERAS,
                _CAMERA_FIELDS,
                take=min(take, 500),
                start=start,
                timeout=self.timeout,
            )
            rows = _columnar_to_rows(resp.get("data", {}).get("data", {}))
            return [_row_to_camera(r) for r in rows]

        # Slow path — page through all records and filter client-side.
        results: List[Camera] = []
        skipped = 0
        for cam in self._iter_all_cameras():
            if not self._camera_matches(cam, jurisdiction, route, active_only):
                continue
            if skipped < start:
                skipped += 1
                continue
            results.append(cam)
            if len(results) >= take:
                break
        return results

    def iter_cameras(
        self,
        *,
        jurisdiction: Optional[str] = None,
        route: Optional[str] = None,
        active_only: bool = False,
        page_size: int = 500,
    ) -> Iterator[Camera]:
        """Iterate over all matching cameras, handling pagination automatically.

        Parameters
        ----------
        jurisdiction:
            Filter by TxDOT district city.
        route:
            Filter by route name.
        active_only:
            When True, exclude offline cameras.
        page_size:
            Number of cameras to fetch per API call (max 500).

        Yields
        ------
        Camera
        """
        has_filter = bool(jurisdiction or route or active_only)
        for cam in self._iter_all_cameras(page_size=page_size):
            if has_filter and not self._camera_matches(
                cam, jurisdiction, route, active_only
            ):
                continue
            yield cam

    def _iter_all_cameras(self, page_size: int = 500) -> Iterator[Camera]:
        """Internal: yield every camera record, paginating the API."""
        api_start = 0
        while True:
            resp = _maplarge_query(
                TABLE_CAMERAS,
                _CAMERA_FIELDS,
                take=min(page_size, 500),
                start=api_start,
                timeout=self.timeout,
            )
            data_block = resp.get("data", {})
            rows = _columnar_to_rows(data_block.get("data", {}))
            if not rows:
                break
            for r in rows:
                yield _row_to_camera(r)
            total = data_block.get("totals", {}).get("Records", 0)
            api_start += len(rows)
            if api_start >= total:
                break

    @staticmethod
    def _camera_matches(
        cam: Camera,
        jurisdiction: Optional[str],
        route: Optional[str],
        active_only: bool,
    ) -> bool:
        """Return True if the camera matches all supplied filters."""
        if jurisdiction and cam.jurisdiction.lower() != jurisdiction.lower():
            return False
        if route and cam.route.upper() != route.upper():
            return False
        if active_only and not cam.is_active:
            return False
        return True

    def get_camera_count(
        self,
        *,
        jurisdiction: Optional[str] = None,
        route: Optional[str] = None,
        active_only: bool = False,
    ) -> int:
        """Return the total number of cameras matching the given filters.

        For unfiltered count this is a single lightweight API call.
        For filtered counts the method pages through all records and counts
        client-side.

        Parameters
        ----------
        jurisdiction:
            Filter by TxDOT district city.
        route:
            Filter by route name.
        active_only:
            When True, only count active cameras.

        Returns
        -------
        int
        """
        has_filter = bool(jurisdiction or route or active_only)
        if not has_filter:
            resp = _maplarge_query(
                TABLE_CAMERAS, ["name"], take=1, start=0, timeout=self.timeout,
            )
            return resp.get("data", {}).get("totals", {}).get("Records", 0)

        return sum(
            1 for _ in self.iter_cameras(
                jurisdiction=jurisdiction,
                route=route,
                active_only=active_only,
            )
        )

    def get_jurisdictions(self) -> List[str]:
        """Return a sorted list of all TxDOT districts (camera jurisdictions).

        Returns
        -------
        list[str]
            e.g. ``['Abilene', 'Austin', 'Beaumont', ...]``
        """
        # Fetch all jurisdiction values in one pass (3500 covers all cameras)
        all_j: set[str] = set()
        api_start = 0
        while True:
            resp = _maplarge_query(
                TABLE_CAMERAS, ["jurisdiction"],
                take=500, start=api_start, timeout=self.timeout,
            )
            data = resp.get("data", {})
            vals = data.get("data", {}).get("jurisdiction", [])
            all_j.update(v for v in vals if v)
            total = data.get("totals", {}).get("Records", 0)
            api_start += len(vals)
            if api_start >= total or not vals:
                break
        return sorted(all_j)

    # ------------------------------------------------------------------
    # Road conditions methods
    # ------------------------------------------------------------------

    def get_conditions(
        self,
        *,
        route: Optional[str] = None,
        condition_type: Optional[str] = None,
        future: bool = False,
        take: int = 500,
        start: int = 0,
    ) -> List[RoadCondition]:
        """Return current (or future) road conditions.

        Filters are applied client-side after fetching data pages.

        Parameters
        ----------
        route:
            Filter by route, e.g. ``"IH0035"``.
        condition_type:
            Filter by type code.  Common values:

            - ``"C"`` – Construction
            - ``"A"`` – Accident
            - ``"D"`` – Damage (road damage)
            - ``"I"`` – Ice / Snow
            - ``"F"`` – Flooding
            - ``"L"`` – Closure
            - ``"O"`` – Other
        future:
            When True, query planned future conditions instead of current ones.
        take:
            Maximum number of records to return.
        start:
            Zero-based logical offset (applied after client-side filtering).

        Returns
        -------
        list[RoadCondition]
        """
        has_filter = bool(route or condition_type)
        if not has_filter:
            table = TABLE_FUTURE_CONDITIONS if future else TABLE_CONDITIONS
            resp = _maplarge_query(
                table,
                _CONDITION_FIELDS,
                take=min(take, 500),
                start=start,
                timeout=self.timeout,
            )
            rows = _columnar_to_rows(resp.get("data", {}).get("data", {}))
            return [_row_to_condition(r) for r in rows]

        results: List[RoadCondition] = []
        skipped = 0
        for cond in self._iter_all_conditions(future=future):
            if not self._condition_matches(cond, route, condition_type):
                continue
            if skipped < start:
                skipped += 1
                continue
            results.append(cond)
            if len(results) >= take:
                break
        return results

    def iter_conditions(
        self,
        *,
        route: Optional[str] = None,
        condition_type: Optional[str] = None,
        future: bool = False,
        page_size: int = 500,
    ) -> Iterator[RoadCondition]:
        """Iterate over all matching conditions, paginating automatically.

        Parameters
        ----------
        route:
            Filter by route name.
        condition_type:
            Filter by condition type code (see :meth:`get_conditions`).
        future:
            When True, iterate over planned future conditions.
        page_size:
            Records per API call (max 500).

        Yields
        ------
        RoadCondition
        """
        has_filter = bool(route or condition_type)
        for cond in self._iter_all_conditions(future=future, page_size=page_size):
            if has_filter and not self._condition_matches(cond, route, condition_type):
                continue
            yield cond

    def _iter_all_conditions(
        self, future: bool = False, page_size: int = 500,
    ) -> Iterator[RoadCondition]:
        """Internal: yield every condition record, paginating the API."""
        table = TABLE_FUTURE_CONDITIONS if future else TABLE_CONDITIONS
        api_start = 0
        while True:
            resp = _maplarge_query(
                table, _CONDITION_FIELDS,
                take=min(page_size, 500), start=api_start,
                timeout=self.timeout,
            )
            data_block = resp.get("data", {})
            rows = _columnar_to_rows(data_block.get("data", {}))
            if not rows:
                break
            for r in rows:
                yield _row_to_condition(r)
            total = data_block.get("totals", {}).get("Records", 0)
            api_start += len(rows)
            if api_start >= total:
                break

    @staticmethod
    def _condition_matches(
        cond: RoadCondition,
        route: Optional[str],
        condition_type: Optional[str],
    ) -> bool:
        """Return True if the condition matches all supplied filters."""
        if route and cond.route.upper() != route.upper():
            return False
        if condition_type and cond.condition_type.upper() != condition_type.upper():
            return False
        return True

    # ------------------------------------------------------------------
    # Site info
    # ------------------------------------------------------------------

    def get_site_info(self) -> SiteInfo:
        """Fetch the DriveTexas site configuration and status.

        This queries the GCS-hosted config file that the React app reads on
        startup to determine redirect rules, active splash screens, and the
        ``working`` flag.

        Returns
        -------
        SiteInfo
        """
        raw = _http_get(_INFO_URL, timeout=self.timeout)
        data = json.loads(raw)
        return SiteInfo(
            working=bool(data.get("working", True)),
            splash_screen=data.get("splashscreen") or "",
            showing=int(data.get("showing") or 3),
            deactivated=list(data.get("deactivated") or []),
            date=int(data.get("date") or 0),
            modal=bool(data.get("modal", False)),
            redirect=data.get("redirect"),
        )

    # ------------------------------------------------------------------
    # Raw query access
    # ------------------------------------------------------------------

    def raw_query(
        self,
        table: str,
        fields: List[str],
        *,
        take: int = 100,
        start: int = 0,
    ) -> Dict[str, Any]:
        """Execute an arbitrary MapLarge query and return the raw response.

        This gives direct access to any table in the ``appgeo`` account.
        Use it to explore tables not wrapped by higher-level methods.

        Parameters
        ----------
        table:
            Table name, e.g. ``"cameraPoint"``, ``"conditionsLine"``,
            ``"floodPoint"``, ``"contraflow_dissolve"``.
        fields:
            List of field names to return.  Use ``["*"]`` for all fields.
        take:
            Maximum rows to return.
        start:
            Zero-based row offset.

        Returns
        -------
        dict
            Full API response dict (``success``, ``data``, ``errors``, etc.).
        """
        return _maplarge_query(
            table,
            fields,
            take=take,
            start=start,
            timeout=self.timeout,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_cameras(args: argparse.Namespace) -> None:
    """Handle ``cameras`` subcommand."""
    client = TxDOTClient(timeout=args.timeout)
    cameras = client.get_cameras(
        jurisdiction=args.jurisdiction,
        route=args.route,
        active_only=args.active,
        take=args.take,
    )
    if args.json:
        print(json.dumps([c.to_dict() for c in cameras], indent=2, default=str))
        return

    print(f"{'Name':<20} {'Jurisdiction':<16} {'Route':<10} {'Active':<8} {'Description'}")
    print("-" * 100)
    for cam in cameras:
        active_str = "YES" if cam.is_active else "no"
        desc = cam.description[:45]
        print(f"{cam.name:<20} {cam.jurisdiction:<16} {cam.route:<10} {active_str:<8} {desc}")
    print(f"\nShowing {len(cameras)} cameras.")


def _cmd_conditions(args: argparse.Namespace) -> None:
    """Handle ``conditions`` subcommand."""
    client = TxDOTClient(timeout=args.timeout)
    conditions = client.get_conditions(
        route=args.route,
        condition_type=args.condition_type,
        future=args.future,
        take=args.take,
    )
    label = "Future Conditions" if args.future else "Current Conditions"
    if args.json:
        print(json.dumps([c.to_dict() for c in conditions], indent=2, default=str))
        return

    print(f"{'Route':<12} {'Type':<16} {'Direction':<12} {'Description'}")
    print("-" * 90)
    for cond in conditions:
        desc = cond.description.replace("<br/>", " ").replace("<br>", " ").strip()[:55]
        print(f"{cond.route:<12} {cond.condition_type_label:<16} {cond.travel_direction:<12} {desc}")
    print(f"\n{label}: {len(conditions)} records.")


def _cmd_info(args: argparse.Namespace) -> None:
    """Handle ``info`` subcommand."""
    client = TxDOTClient(timeout=args.timeout)
    info = client.get_site_info()
    if args.json:
        print(json.dumps({
            "working": info.working,
            "splash_screen": info.splash_screen,
            "showing": info.showing,
            "deactivated": info.deactivated,
            "date": info.date,
            "date_utc": info.date_dt.isoformat() if info.date_dt else None,
            "modal": info.modal,
            "redirect": info.redirect,
        }, indent=2))
        return
    print(f"Site working : {info.working}")
    print(f"Config date  : {info.date_dt or 'unknown'}")
    print(f"Showing mode : {info.showing}")
    print(f"Modal active : {info.modal}")
    if info.splash_screen:
        print(f"Splash screen: {info.splash_screen[:200]}")
    if info.deactivated:
        print(f"Deactivated  : {info.deactivated}")
    if info.redirect:
        print(f"Redirect     : {info.redirect}")


def _cmd_stats(args: argparse.Namespace) -> None:
    """Handle ``stats`` subcommand."""
    client = TxDOTClient(timeout=args.timeout)
    print("Fetching statistics…")

    jurisdictions = client.get_jurisdictions()
    total = client.get_camera_count()

    print(f"\nTotal cameras     : {total}")
    print(f"Districts         : {len(jurisdictions)}")
    print(f"\nCameras by district:")
    for j in jurisdictions:
        count = client.get_camera_count(jurisdiction=j)
        print(f"  {j:<22} {count}")

    # Conditions summary
    curr = client.get_conditions(take=1)
    resp_curr = client.raw_query(TABLE_CONDITIONS, ["RTENM"], take=1)
    total_curr = resp_curr.get("data", {}).get("totals", {}).get("Records", 0)

    resp_fut = client.raw_query(TABLE_FUTURE_CONDITIONS, ["RTENM"], take=1)
    total_fut = resp_fut.get("data", {}).get("totals", {}).get("Records", 0)

    print(f"\nCurrent conditions : {total_curr}")
    print(f"Future conditions  : {total_fut}")


def _cmd_stream(args: argparse.Namespace) -> None:
    """Handle ``stream`` subcommand — print the HLS URL for a camera by name."""
    client = TxDOTClient(timeout=args.timeout)
    resp = client.raw_query(
        TABLE_CAMERAS,
        ["name", "description", "jurisdiction", "httpsurl", "rtspurl", "active"],
        take=1,
        where=[f'name=="{args.camera_name}"'],
    )
    rows = _columnar_to_rows(resp.get("data", {}).get("data", {}))
    if not rows:
        print(f"Camera not found: {args.camera_name}", file=sys.stderr)
        sys.exit(1)
    cam = _row_to_camera(rows[0])
    if args.json:
        print(json.dumps(cam.to_dict(), indent=2, default=str))
        return
    print(f"Camera   : {cam.name}")
    print(f"Location : {cam.description}")
    print(f"District : {cam.jurisdiction}")
    print(f"Active   : {'YES' if cam.is_active else 'NO'}")
    print(f"HLS URL  : {cam.hls_url}")
    print(f"RTSP URL : {cam.rtsp_url}")
    print(f"RTMP URL : {cam.rtmp_url}")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="txdot_client",
        description="TxDOT / DriveTexas traffic camera & road conditions API client.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--timeout", type=int, default=30, metavar="SECS",
        help="HTTP request timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # cameras
    p_cam = subparsers.add_parser("cameras", help="List traffic cameras.")
    p_cam.add_argument("--jurisdiction", "-j", metavar="CITY",
                       help="Filter by district city (e.g. Houston, Dallas).")
    p_cam.add_argument("--route", "-r", metavar="ROUTE",
                       help="Filter by route (e.g. IH0035, US0290).")
    p_cam.add_argument("--active", action="store_true",
                       help="Only show active cameras.")
    p_cam.add_argument("--take", "-n", type=int, default=20,
                       help="Maximum results (default: 20).")

    # conditions
    p_cond = subparsers.add_parser("conditions", help="List road conditions.")
    p_cond.add_argument("--route", "-r", metavar="ROUTE",
                        help="Filter by route (e.g. IH0035).")
    p_cond.add_argument("--type", "-t", dest="condition_type", metavar="TYPE",
                        help="Filter by type code (C=construction, A=accident, L=closure).")
    p_cond.add_argument("--future", "-f", action="store_true",
                        help="Show planned future conditions instead of current.")
    p_cond.add_argument("--take", "-n", type=int, default=20,
                        help="Maximum results (default: 20).")

    # info
    subparsers.add_parser("info", help="Show DriveTexas site status.")

    # stats
    subparsers.add_parser("stats", help="Show system-wide statistics.")

    # stream
    p_stream = subparsers.add_parser("stream", help="Get stream URL for a camera.")
    p_stream.add_argument("camera_name", metavar="CAMERA_NAME",
                          help="Camera identifier, e.g. TX_FTW_085.")

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    try:
        dispatch = {
            "cameras": _cmd_cameras,
            "conditions": _cmd_conditions,
            "info": _cmd_info,
            "stats": _cmd_stats,
            "stream": _cmd_stream,
        }
        dispatch[args.command](args)
    except MapLargeError as exc:
        print(f"API Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
