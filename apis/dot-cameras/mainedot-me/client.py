"""
MaineDOT / New England 511 Traffic Camera Client
=================================================
Reverse-engineered client for the New England 511 traffic information system
(https://newengland511.org), which serves Maine DOT (MaineDOT) camera data.

API base: https://newengland511.org
No authentication required for public endpoints.
All data is served via server-side DataTables (GET /List/GetData/{typeId})
and map-icon endpoints (GET /map/mapIcons/{layer}).

Stdlib only: urllib, json, dataclasses, typing
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Iterator, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://newengland511.org"

# Camera image refresh rate (ms) as reported by the API
DEFAULT_REFRESH_MS = 10_000

# DataTable page size cap enforced by the server
MAX_PAGE_SIZE = 100

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Known "typeId" friendly names used by /List/GetData/{typeId}
LIST_TYPE_CAMERAS = "Cameras"
LIST_TYPE_TRAFFIC = "traffic"
LIST_TYPE_CONSTRUCTION = "construction"
LIST_TYPE_MESSAGE_SIGNS = "MessageSigns"
LIST_TYPE_TRAVEL_TIMES = "TravelTimes"

# Known /map/mapIcons/{layer} layer names
MAP_LAYER_CAMERAS = "Cameras"
MAP_LAYER_INCIDENTS = "Incidents"
MAP_LAYER_CONSTRUCTION = "Construction"
MAP_LAYER_MESSAGE_SIGNS = "MessageSigns"
MAP_LAYER_WEATHER_STATIONS = "WeatherStations"
MAP_LAYER_WEATHER_EVENTS = "WeatherEvents"
MAP_LAYER_FERRY_TERMINALS = "FerryTerminals"
MAP_LAYER_TRUCK_RESTRICTIONS = "TruckRestrictions"
MAP_LAYER_TRAVEL_TIMES = "Wta"  # WTA = Weighted Travel Average

# State names used in the column-search filter
STATE_MAINE = "Maine"
STATE_NEW_HAMPSHIRE = "New Hampshire"
STATE_VERMONT = "Vermont"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class CameraImage:
    """A single image/video stream attached to a camera site."""
    id: int
    camera_site_id: int
    sort_order: int
    image_url: str          # relative path, e.g. /map/Cctv/2188
    image_type: int         # 1 = still JPEG
    refresh_rate_ms: int
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool

    @property
    def full_image_url(self) -> str:
        """Absolute URL to the live camera JPEG."""
        return BASE_URL + self.image_url

    @classmethod
    def from_dict(cls, d: dict) -> "CameraImage":
        return cls(
            id=d["id"],
            camera_site_id=d["cameraSiteId"],
            sort_order=d.get("sortOrder", 0),
            image_url=d.get("imageUrl", ""),
            image_type=d.get("imageType", 1),
            refresh_rate_ms=d.get("refreshRateMs", DEFAULT_REFRESH_MS),
            is_video_auth_required=d.get("isVideoAuthRequired", False),
            video_disabled=d.get("videoDisabled", False),
            disabled=d.get("disabled", False),
            blocked=d.get("blocked", False),
        )


@dataclass
class Camera:
    """A traffic camera site, which may have one or more images."""
    id: int
    dt_row_id: str
    source_id: str
    source: str                   # e.g. "Maine"
    state: Optional[str]
    county: Optional[str]
    city: Optional[str]
    region: Optional[str]
    roadway: str
    direction: str
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    images: List[CameraImage]
    tooltip_url: str
    last_updated: Optional[str]
    visible: bool
    agency_id: Optional[str]
    agency_logo_enabled: bool

    @property
    def thumbnail_url(self) -> Optional[str]:
        """Absolute URL of the first (primary) camera image."""
        if self.images:
            return self.images[0].full_image_url
        return None

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        # Extract lat/lon from WKT "POINT (lon lat)" inside geography object
        lat, lon = None, None
        lat_lng = d.get("latLng") or {}
        geo = lat_lng.get("geography") or {}
        wkt = geo.get("wellKnownText", "")
        if wkt.startswith("POINT"):
            try:
                # format: POINT (-73.199637 44.449335)  => lon lat
                coords = wkt.replace("POINT (", "").replace(")", "").split()
                lon = float(coords[0])
                lat = float(coords[1])
            except (IndexError, ValueError):
                pass

        images = [CameraImage.from_dict(img) for img in d.get("images", [])]
        return cls(
            id=d["id"],
            dt_row_id=d.get("DT_RowId", str(d["id"])),
            source_id=d.get("sourceId", ""),
            source=d.get("source", ""),
            state=d.get("state"),
            county=d.get("county"),
            city=d.get("city"),
            region=d.get("region"),
            roadway=d.get("roadway", ""),
            direction=d.get("direction", ""),
            location=d.get("location", ""),
            latitude=lat,
            longitude=lon,
            images=images,
            tooltip_url=BASE_URL + d.get("tooltipUrl", "").replace("{lang}", "en"),
            last_updated=d.get("lastUpdated"),
            visible=d.get("visible", True),
            agency_id=d.get("agencyId"),
            agency_logo_enabled=d.get("agencyLogoEnabled", False),
        )


@dataclass
class MapIcon:
    """Lightweight camera/POI entry from the map icon layer endpoint."""
    item_id: str
    latitude: float
    longitude: float
    title: str

    @classmethod
    def from_dict(cls, d: dict) -> "MapIcon":
        loc = d.get("location", [0, 0])
        return cls(
            item_id=d["itemId"],
            latitude=loc[0],
            longitude=loc[1],
            title=d.get("title", ""),
        )


@dataclass
class TrafficEvent:
    """An incident, roadwork, or construction event."""
    id: Any
    dt_row_id: str
    description: str
    state: Optional[str]
    county: Optional[str]
    roadway: Optional[str]
    direction: Optional[str]
    location: Optional[str]
    event_type: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    @classmethod
    def from_dict(cls, d: dict) -> "TrafficEvent":
        lat, lon = None, None
        lat_lng = d.get("latLng") or {}
        geo = lat_lng.get("geography") or {}
        wkt = geo.get("wellKnownText", "")
        if wkt.startswith("POINT"):
            try:
                coords = wkt.replace("POINT (", "").replace(")", "").split()
                lon = float(coords[0])
                lat = float(coords[1])
            except (IndexError, ValueError):
                pass
        return cls(
            id=d.get("id"),
            dt_row_id=d.get("DT_RowId", str(d.get("id", ""))),
            description=d.get("description", ""),
            state=d.get("state"),
            county=d.get("county"),
            roadway=d.get("roadway"),
            direction=d.get("direction"),
            location=d.get("location"),
            event_type=d.get("type") or d.get("eventType"),
            start_date=d.get("startDate") or d.get("created"),
            end_date=d.get("endDate"),
            latitude=lat,
            longitude=lon,
        )


@dataclass
class MessageSign:
    """A dynamic message sign (DMS) showing real-time text."""
    id: Any
    dt_row_id: str
    location: Optional[str]
    roadway: Optional[str]
    direction: Optional[str]
    state: Optional[str]
    message1: Optional[str]
    message2: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    @classmethod
    def from_dict(cls, d: dict) -> "MessageSign":
        lat, lon = None, None
        lat_lng = d.get("latLng") or {}
        geo = lat_lng.get("geography") or {}
        wkt = geo.get("wellKnownText", "")
        if wkt.startswith("POINT"):
            try:
                coords = wkt.replace("POINT (", "").replace(")", "").split()
                lon = float(coords[0])
                lat = float(coords[1])
            except (IndexError, ValueError):
                pass
        return cls(
            id=d.get("id"),
            dt_row_id=d.get("DT_RowId", str(d.get("id", ""))),
            location=d.get("location"),
            roadway=d.get("roadway"),
            direction=d.get("direction"),
            state=d.get("state"),
            message1=d.get("message"),
            message2=d.get("message2"),
            latitude=lat,
            longitude=lon,
        )


@dataclass
class ListPage:
    """A paginated result page from /List/GetData/."""
    draw: int
    records_total: int
    records_filtered: int
    data: List[dict]

    @classmethod
    def from_dict(cls, d: dict) -> "ListPage":
        return cls(
            draw=d.get("draw", 0),
            records_total=d.get("recordsTotal", 0),
            records_filtered=d.get("recordsFiltered", 0),
            data=d.get("data", []),
        )


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 20) -> bytes:
    """
    Perform a simple GET request and return raw bytes.
    Raises urllib.error.HTTPError / URLError on failure.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url: str, timeout: int = 20) -> Any:
    raw = _get(url, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# Core query builder
# ---------------------------------------------------------------------------

def _build_list_query(
    start: int = 0,
    length: int = 100,
    state_filter: Optional[str] = None,
    roadway_filter: Optional[str] = None,
    global_search: str = "",
    draw: int = 1,
    extra_columns: Optional[List[dict]] = None,
) -> str:
    """
    Build the JSON query string expected by /List/GetData/{typeId}?query=...

    The server uses server-side DataTables protocol (GET, query param).
    Column-level search is the correct way to filter by state.
    Max 100 records per page (server-enforced).
    """
    columns = [
        {
            "data": "sortOrder",
            "name": "sortOrder",
            "searchable": False,
            "orderable": True,
        },
        {
            "data": "state",
            "name": "state",
            "searchable": True,
            "orderable": True,
            "search": {"value": state_filter or "", "regex": False},
        },
        {
            "data": "roadway",
            "name": "roadway",
            "searchable": True,
            "orderable": True,
            "search": {"value": roadway_filter or "", "regex": False},
        },
        {
            "data": "location",
            "name": "location",
            "searchable": False,
            "orderable": False,
        },
    ]
    if extra_columns:
        columns.extend(extra_columns)

    query = {
        "draw": draw,
        "columns": columns,
        "order": [
            {"column": 1, "dir": "asc"},
            {"column": 0, "dir": "asc"},
        ],
        "start": start,
        "length": min(length, MAX_PAGE_SIZE),
        "search": {"value": global_search, "regex": False},
    }
    return json.dumps(query, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class NewEngland511Client:
    """
    Python client for the New England 511 traffic information system.

    Covers: Maine, New Hampshire, Vermont.
    No API key or login required for public data.

    Usage
    -----
    >>> client = NewEngland511Client()
    >>> cameras = client.get_maine_cameras()
    >>> for cam in cameras:
    ...     print(cam.location, cam.thumbnail_url)
    """

    def __init__(self, base_url: str = BASE_URL, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Low-level list endpoint
    # ------------------------------------------------------------------

    def _fetch_list_page(
        self,
        type_id: str,
        start: int = 0,
        length: int = 100,
        state_filter: Optional[str] = None,
        roadway_filter: Optional[str] = None,
        global_search: str = "",
        draw: int = 1,
    ) -> ListPage:
        """Fetch one page from /List/GetData/{type_id}."""
        q = _build_list_query(
            start=start,
            length=length,
            state_filter=state_filter,
            roadway_filter=roadway_filter,
            global_search=global_search,
            draw=draw,
        )
        params = urllib.parse.urlencode({"query": q, "lang": "en"})
        url = f"{self.base_url}/List/GetData/{type_id}?{params}"
        data = _get_json(url, timeout=self.timeout)
        return ListPage.from_dict(data)

    def _iter_all_pages(
        self,
        type_id: str,
        state_filter: Optional[str] = None,
        roadway_filter: Optional[str] = None,
        global_search: str = "",
        page_size: int = 100,
        delay: float = 0.0,
    ) -> Iterator[dict]:
        """
        Iterate over every record across all pages for a given list type.
        Handles server-enforced 100-record-per-page limit automatically.
        """
        start = 0
        draw = 1
        total = None

        while True:
            page = self._fetch_list_page(
                type_id=type_id,
                start=start,
                length=page_size,
                state_filter=state_filter,
                roadway_filter=roadway_filter,
                global_search=global_search,
                draw=draw,
            )
            if total is None:
                total = page.records_filtered

            for record in page.data:
                yield record

            start += len(page.data)
            draw += 1

            if not page.data or start >= total:
                break

            if delay > 0:
                time.sleep(delay)

    # ------------------------------------------------------------------
    # Map icon (lightweight) endpoint
    # ------------------------------------------------------------------

    def get_map_icons(self, layer: str) -> List[MapIcon]:
        """
        Fetch all map icon positions for a given layer.

        Returns lightweight MapIcon objects (id + lat/lon only).
        Use this for a fast overview; call get_cameras() for full detail.

        Parameters
        ----------
        layer : str
            One of the MAP_LAYER_* constants, e.g. MAP_LAYER_CAMERAS.
        """
        url = f"{self.base_url}/map/mapIcons/{layer}"
        data = _get_json(url, timeout=self.timeout)
        return [MapIcon.from_dict(item) for item in data.get("item2", [])]

    def get_camera_map_icons(self) -> List[MapIcon]:
        """Return lightweight camera positions for all regions."""
        return self.get_map_icons(MAP_LAYER_CAMERAS)

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        state: Optional[str] = None,
        roadway: Optional[str] = None,
        page_size: int = 100,
        delay: float = 0.25,
    ) -> List[Camera]:
        """
        Fetch all traffic cameras, optionally filtered by state or roadway.

        Parameters
        ----------
        state : str, optional
            State name filter. Use STATE_* constants:
            STATE_MAINE, STATE_NEW_HAMPSHIRE, STATE_VERMONT
        roadway : str, optional
            Roadway/route filter (e.g. "I-95", "US-1").
        page_size : int
            Records per request (max 100).
        delay : float
            Seconds to wait between paginated requests.

        Returns
        -------
        List[Camera]
            All matching cameras, fully populated with image URLs.
        """
        records = list(
            self._iter_all_pages(
                type_id=LIST_TYPE_CAMERAS,
                state_filter=state,
                roadway_filter=roadway,
                page_size=page_size,
                delay=delay,
            )
        )
        return [Camera.from_dict(r) for r in records]

    def get_maine_cameras(self, roadway: Optional[str] = None) -> List[Camera]:
        """Convenience method: fetch all Maine DOT traffic cameras."""
        return self.get_cameras(state=STATE_MAINE, roadway=roadway)

    def get_camera_by_id(self, camera_id: int) -> Optional[Camera]:
        """
        Fetch a single camera site by its numeric ID using the tooltip endpoint.

        The tooltip endpoint returns HTML; this method delegates to get_cameras()
        with a global search on the id if the list lookup is preferred.

        For a quicker approach, use get_cameras() and filter by id locally.
        """
        cameras = self.get_cameras()
        for cam in cameras:
            if cam.id == camera_id:
                return cam
        return None

    def get_camera_image_bytes(self, camera_image: CameraImage) -> Optional[bytes]:
        """
        Download the current JPEG snapshot for a camera image.

        Returns raw bytes (JPEG), or None if the image is blocked/unavailable.
        The server sets Cache-Control: max-age=10, so images refresh ~every 10 s.
        """
        if camera_image.blocked or camera_image.disabled:
            return None
        try:
            return _get(camera_image.full_image_url, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 403):
                return None
            raise

    def save_camera_image(
        self, camera_image: CameraImage, path: str
    ) -> bool:
        """
        Download and save a camera snapshot to a file.

        Parameters
        ----------
        camera_image : CameraImage
        path : str  Destination file path (e.g. "camera_950.jpg")

        Returns
        -------
        bool  True if image was saved, False if unavailable.
        """
        data = self.get_camera_image_bytes(camera_image)
        if data:
            with open(path, "wb") as fh:
                fh.write(data)
            return True
        return False

    # ------------------------------------------------------------------
    # Traffic events
    # ------------------------------------------------------------------

    def get_traffic_events(
        self,
        state: Optional[str] = None,
        page_size: int = 100,
        delay: float = 0.25,
    ) -> List[TrafficEvent]:
        """
        Fetch current traffic incidents (accidents, closures, etc.).

        Parameters
        ----------
        state : str, optional
            State name filter (e.g. STATE_MAINE).
        """
        records = list(
            self._iter_all_pages(
                type_id=LIST_TYPE_TRAFFIC,
                state_filter=state,
                page_size=page_size,
                delay=delay,
            )
        )
        return [TrafficEvent.from_dict(r) for r in records]

    def get_maine_traffic_events(self) -> List[TrafficEvent]:
        """Convenience: fetch current Maine traffic incidents."""
        return self.get_traffic_events(state=STATE_MAINE)

    def get_construction_events(
        self,
        state: Optional[str] = None,
        page_size: int = 100,
        delay: float = 0.25,
    ) -> List[TrafficEvent]:
        """Fetch active road construction / roadwork events."""
        records = list(
            self._iter_all_pages(
                type_id=LIST_TYPE_CONSTRUCTION,
                state_filter=state,
                page_size=page_size,
                delay=delay,
            )
        )
        return [TrafficEvent.from_dict(r) for r in records]

    # ------------------------------------------------------------------
    # Message signs
    # ------------------------------------------------------------------

    def get_message_signs(
        self,
        state: Optional[str] = None,
        page_size: int = 100,
        delay: float = 0.25,
    ) -> List[MessageSign]:
        """
        Fetch dynamic message sign (DMS) data.

        Parameters
        ----------
        state : str, optional
            State name filter.
        """
        records = list(
            self._iter_all_pages(
                type_id=LIST_TYPE_MESSAGE_SIGNS,
                state_filter=state,
                page_size=page_size,
                delay=delay,
            )
        )
        return [MessageSign.from_dict(r) for r in records]

    def get_maine_message_signs(self) -> List[MessageSign]:
        """Convenience: fetch Maine dynamic message signs."""
        return self.get_message_signs(state=STATE_MAINE)

    # ------------------------------------------------------------------
    # Tooltip / popup HTML
    # ------------------------------------------------------------------

    def get_tooltip_html(self, layer: str, item_id: int) -> str:
        """
        Fetch the raw HTML tooltip used in the web map popup.

        Parameters
        ----------
        layer : str  Layer name, e.g. "Cameras", "Incidents".
        item_id : int  Numeric item ID.

        Returns
        -------
        str  Raw HTML string.
        """
        url = f"{self.base_url}/tooltip/{layer}/{item_id}?lang=en&noCss=true"
        return _get(url, timeout=self.timeout).decode("utf-8")

    def get_camera_tooltip_html(self, camera_id: int) -> str:
        """Fetch the camera popup HTML (includes current image)."""
        return self.get_tooltip_html("Cameras", camera_id)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_all_states(self) -> List[str]:
        """
        Return the distinct state names available in the camera database.

        Fetches one full page and collects unique state values.
        """
        records = list(
            self._iter_all_pages(
                type_id=LIST_TYPE_CAMERAS,
                page_size=100,
            )
        )
        return sorted({r.get("state") for r in records if r.get("state")})


# ---------------------------------------------------------------------------
# CLI / demo
# ---------------------------------------------------------------------------

def _print_cameras(cameras: List[Camera], limit: int = 10) -> None:
    print(f"\n{'='*70}")
    print(f"Found {len(cameras)} camera(s)  (showing first {min(limit, len(cameras))})")
    print(f"{'='*70}")
    for cam in cameras[:limit]:
        print(f"\n  ID       : {cam.id}")
        print(f"  Location : {cam.location}")
        print(f"  Roadway  : {cam.roadway}  ({cam.direction})")
        print(f"  State    : {cam.state} / {cam.city or cam.county or cam.region or 'N/A'}")
        print(f"  Images   : {len(cam.images)}")
        for img in cam.images:
            status = "BLOCKED" if img.blocked else ("DISABLED" if img.disabled else "OK")
            print(f"    [{status}] {img.full_image_url}  (refresh {img.refresh_rate_ms}ms)")
        print(f"  Updated  : {cam.last_updated or 'N/A'}")


def _print_events(events: List[TrafficEvent], limit: int = 10) -> None:
    print(f"\n{'='*70}")
    print(f"Found {len(events)} event(s)  (showing first {min(limit, len(events))})")
    print(f"{'='*70}")
    for ev in events[:limit]:
        print(f"\n  ID       : {ev.id}")
        print(f"  Type     : {ev.event_type or 'Incident'}")
        print(f"  State    : {ev.state}")
        print(f"  Location : {ev.location or ev.roadway or 'N/A'}")
        desc = (ev.description or "")[:120]
        print(f"  Desc     : {desc}")


def main():
    """Demonstrate all major API capabilities against live endpoints."""
    import sys

    client = NewEngland511Client()

    print("\n" + "#" * 70)
    print("#  New England 511 / MaineDOT Client — Live Endpoint Test")
    print("#" * 70)

    # 1. Map icons (fast, lightweight)
    print("\n[1] Fetching camera map icons (all regions)...")
    try:
        icons = client.get_camera_map_icons()
        print(f"    Total cameras in system : {len(icons)}")
        if icons:
            sample = icons[0]
            print(f"    Sample icon             : id={sample.item_id} lat={sample.latitude:.4f} lon={sample.longitude:.4f}")
    except Exception as exc:
        print(f"    ERROR: {exc}")

    # 2. All Maine cameras
    print("\n[2] Fetching all Maine traffic cameras (paginated)...")
    try:
        me_cams = client.get_maine_cameras()
        _print_cameras(me_cams, limit=5)
    except Exception as exc:
        print(f"    ERROR: {exc}")
        me_cams = []

    # 3. Maine cameras on I-95 specifically
    print("\n[3] Maine I-95 cameras only...")
    try:
        i95 = client.get_cameras(state=STATE_MAINE, roadway="I-95")
        print(f"    I-95 cameras: {len(i95)}")
        for cam in i95[:3]:
            print(f"      {cam.location:<40s}  {cam.direction}")
            for img in cam.images:
                print(f"        Image: {img.full_image_url}")
    except Exception as exc:
        print(f"    ERROR: {exc}")

    # 4. Camera image download test
    print("\n[4] Testing camera image download...")
    try:
        if me_cams:
            test_cam = next((c for c in me_cams if c.images and not c.images[0].blocked), None)
            if test_cam:
                img = test_cam.images[0]
                raw = client.get_camera_image_bytes(img)
                size = len(raw) if raw else 0
                print(f"    Camera  : {test_cam.location}")
                print(f"    URL     : {img.full_image_url}")
                print(f"    Bytes   : {size}  ({'OK' if size > 0 else 'empty/offline'})")
            else:
                print("    No unblocked cameras found")
    except Exception as exc:
        print(f"    ERROR: {exc}")

    # 5. Maine traffic events
    print("\n[5] Fetching Maine traffic events...")
    try:
        events = client.get_maine_traffic_events()
        _print_events(events, limit=3)
    except Exception as exc:
        print(f"    ERROR: {exc}")

    # 6. Maine message signs
    print("\n[6] Fetching Maine dynamic message signs...")
    try:
        signs = client.get_maine_message_signs()
        print(f"\n    Found {len(signs)} Maine message sign(s)")
        for sign in signs[:3]:
            print(f"      {sign.location or 'N/A':<40s} | {sign.message1 or ''}")
    except Exception as exc:
        print(f"    ERROR: {exc}")

    # 7. Available states
    print("\n[7] Querying available states...")
    try:
        states = client.get_all_states()
        print(f"    States: {states}")
    except Exception as exc:
        print(f"    ERROR: {exc}")

    print("\n" + "#" * 70)
    print("#  All tests complete.")
    print("#" * 70 + "\n")


if __name__ == "__main__":
    main()
