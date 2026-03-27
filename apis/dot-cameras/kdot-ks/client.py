"""
KDOT Traffic Camera & Road Conditions Client
Kansas Department of Transportation (KanDrive) - https://www.kandrive.gov
Reverse engineered from https://www.kandrive.gov v3.19.10 JS bundles.

Backend: Castle Rock ITS (castlerockits.com) / CARS platform
Primary API host: https://kstg.carsprogram.org  (g variable in JS bundles)
Custom layers host: https://public.carsprogram.org/ks/prod  (m variable)
Camera snapshots: https://kscam.carsprogram.org

No authentication is required for public endpoints.
Uses only Python stdlib: urllib, json, dataclasses, typing.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Iterator, List, Optional
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = "https://kstg.carsprogram.org"
SNAPSHOT_BASE = "https://kscam.carsprogram.org"
PUBLIC_LAYERS_BASE = "https://public.carsprogram.org/ks/prod"
ARCGIS_ROAD_CONDITIONS = (
    "https://services.arcgis.com/8lRhdTsQyJpO52F1/ArcGIS/rest/services/"
    "Midwest_Winter_Road_Conditions_View/FeatureServer/0/query"
)

_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.kandrive.gov",
    "Referer": "https://www.kandrive.gov/",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

_DEFAULT_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CameraLocation:
    fips: int
    latitude: float
    longitude: float
    route_id: str
    linear_reference: float
    local_road: bool
    city_reference: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "CameraLocation":
        return cls(
            fips=d.get("fips", 0),
            latitude=d["latitude"],
            longitude=d["longitude"],
            route_id=d.get("routeId", ""),
            linear_reference=d.get("linearReference", 0.0),
            local_road=d.get("localRoad", False),
            city_reference=d.get("cityReference"),
        )


@dataclass
class CameraView:
    """A single camera feed (still image or HLS video stream)."""
    name: str
    view_type: str          # "STILL_IMAGE" or "WMP" (Wowza Media Player / HLS)
    url: str                # JPEG URL for STILL_IMAGE; .m3u8 playlist for WMP
    video_preview_url: Optional[str]  # JPEG snapshot for WMP cameras
    image_timestamp: Optional[int]    # Unix milliseconds

    @classmethod
    def from_dict(cls, d: dict) -> "CameraView":
        return cls(
            name=d.get("name", ""),
            view_type=d.get("type", ""),
            url=d.get("url", ""),
            video_preview_url=d.get("videoPreviewUrl"),
            image_timestamp=d.get("imageTimestamp"),
        )

    @property
    def is_streaming(self) -> bool:
        """True if this view provides an HLS video stream."""
        return self.view_type == "WMP"

    @property
    def snapshot_url(self) -> Optional[str]:
        """Best URL for a static JPEG snapshot."""
        if self.view_type == "STILL_IMAGE":
            return self.url
        return self.video_preview_url

    @property
    def updated_at(self) -> Optional[datetime]:
        if self.image_timestamp is None:
            return None
        return datetime.fromtimestamp(self.image_timestamp / 1000, tz=timezone.utc)


@dataclass
class Camera:
    camera_id: int
    name: str
    public: bool
    active: bool
    last_updated: int          # Unix milliseconds
    location: CameraLocation
    owner_name: str
    views: List[CameraView] = field(default_factory=list)
    co_located_weather_station_id: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Camera":
        loc = CameraLocation.from_dict(d["location"])
        views = [CameraView.from_dict(v) for v in d.get("views", [])]
        return cls(
            camera_id=d["id"],
            name=d.get("name", ""),
            public=d.get("public", True),
            active=d.get("active", True),
            last_updated=d.get("lastUpdated", 0),
            location=loc,
            owner_name=d.get("cameraOwner", {}).get("name", ""),
            views=views,
            co_located_weather_station_id=d.get("coLocatedWeatherStationId"),
        )

    @property
    def updated_at(self) -> datetime:
        return datetime.fromtimestamp(self.last_updated / 1000, tz=timezone.utc)

    @property
    def primary_snapshot_url(self) -> Optional[str]:
        for v in self.views:
            url = v.snapshot_url
            if url:
                return url
        return None

    @property
    def hls_stream_url(self) -> Optional[str]:
        for v in self.views:
            if v.is_streaming:
                return v.url
        return None


@dataclass
class SignPage:
    lines: List[str]
    justification: str
    has_image: bool

    @classmethod
    def from_dict(cls, d: dict) -> "SignPage":
        return cls(
            lines=d.get("lines", []),
            justification=d.get("justification", "CENTER"),
            has_image=d.get("hasImage", False),
        )

    def text(self) -> str:
        return " | ".join(self.lines)


@dataclass
class SignLocation:
    latitude: float
    longitude: float
    route_id: str
    linear_reference: float
    sign_facing_direction: str
    location_description: str
    city_reference: Optional[str] = None
    fips: int = 20

    @classmethod
    def from_dict(cls, d: dict) -> "SignLocation":
        return cls(
            latitude=d.get("latitude", 0.0),
            longitude=d.get("longitude", 0.0),
            route_id=d.get("routeId", ""),
            linear_reference=d.get("linearReference", 0.0),
            sign_facing_direction=d.get("signFacingDirection", ""),
            location_description=d.get("locationDescription", ""),
            city_reference=d.get("cityReference"),
            fips=d.get("fips", 20),
        )


@dataclass
class Sign:
    sign_id: str               # e.g. "kansassigns*179"
    name: str
    status: str                # "DISPLAYING_MESSAGE", "BLANK", "ERROR_OR_FAILURE"
    agency_id: str             # "kansassigns" or "kcscout"
    agency_name: str
    id_for_display: str
    last_updated: int
    location: SignLocation
    pages: List[SignPage] = field(default_factory=list)
    sign_type: str = ""        # "VMS_FULL", "VMS_IMAGE"
    max_lines_per_page: int = 3
    max_chars_per_line: int = 16

    @classmethod
    def from_dict(cls, d: dict) -> "Sign":
        location = SignLocation.from_dict(d.get("location", {}))
        pages = [SignPage.from_dict(p) for p in d.get("display", {}).get("pages", [])]
        props = d.get("properties", {})
        return cls(
            sign_id=d["id"],
            name=d.get("name", ""),
            status=d.get("status", ""),
            agency_id=d.get("agencyId", ""),
            agency_name=d.get("agencyName", ""),
            id_for_display=d.get("idForDisplay", ""),
            last_updated=d.get("lastUpdated", 0),
            location=location,
            pages=pages,
            sign_type=props.get("signType", ""),
            max_lines_per_page=props.get("maxLinesPerPage", 3),
            max_chars_per_line=props.get("maxCharactersPerLine", 16),
        )

    @property
    def updated_at(self) -> datetime:
        return datetime.fromtimestamp(self.last_updated / 1000, tz=timezone.utc)

    @property
    def current_message(self) -> str:
        """All pages joined with ' / '."""
        return " / ".join(p.text() for p in self.pages) if self.pages else ""

    @property
    def is_blank(self) -> bool:
        return self.status == "BLANK"

    @property
    def is_displaying(self) -> bool:
        return self.status == "DISPLAYING_MESSAGE"


@dataclass
class PlowStatus:
    timestamp: int
    latitude: float
    longitude: float
    route_designator: str
    vehicle_name: str
    heading_string: str
    plow_icon_name: str
    nearby_points_description: str
    linear_reference: float
    timezone_id: str
    total_truck_count: int

    @classmethod
    def from_dict(cls, d: dict) -> "PlowStatus":
        return cls(
            timestamp=d.get("timestamp", 0),
            latitude=d.get("latitude", 0.0),
            longitude=d.get("longitude", 0.0),
            route_designator=d.get("routeDesignator", ""),
            vehicle_name=d.get("vehicleName", ""),
            heading_string=d.get("headingString", ""),
            plow_icon_name=d.get("plowIconName", ""),
            nearby_points_description=d.get("nearbyPointsDescription", ""),
            linear_reference=d.get("linearReference", 0.0),
            timezone_id=d.get("timezoneId", "America/Chicago"),
            total_truck_count=d.get("totalTruckCount", 0),
        )

    @property
    def recorded_at(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc)


@dataclass
class Plow:
    plow_id: str
    statuses: List[PlowStatus] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Plow":
        statuses = [PlowStatus.from_dict(s) for s in d.get("statuses", [])]
        return cls(plow_id=d["id"], statuses=statuses)

    @property
    def latest_status(self) -> Optional[PlowStatus]:
        if not self.statuses:
            return None
        return max(self.statuses, key=lambda s: s.timestamp)


@dataclass
class RoadConditionFeature:
    """A road segment from the ArcGIS winter road conditions feed."""
    object_id: int
    route_name: str
    segment_id: str
    headline: str
    description: str
    road_condition: int        # Numeric code
    status: str
    report_updated: Optional[int]  # Unix ms
    source: str
    shape_length_m: float

    @classmethod
    def from_dict(cls, d: dict) -> "RoadConditionFeature":
        attrs = d.get("attributes", d)
        return cls(
            object_id=attrs.get("OBJECTID", 0),
            route_name=attrs.get("ROUTE_NAME", ""),
            segment_id=attrs.get("SEGMENT_ID", ""),
            headline=attrs.get("HEADLINE", ""),
            description=attrs.get("DESCRIPTION", ""),
            road_condition=attrs.get("ROAD_CONDITION", 0),
            status=attrs.get("STATUS", ""),
            report_updated=attrs.get("REPORT_UPDATED"),
            source=attrs.get("SOURCE", ""),
            shape_length_m=attrs.get("SHAPE__Length_2", 0.0),
        )

    CONDITION_LABELS = {
        0: "Unknown",
        1: "Normal / Dry",
        2: "Wet",
        3: "Snow / Ice Covered",
        4: "Partially Covered",
        5: "Completely Covered",
        6: "Impassable",
        7: "Not Advised",
    }

    @property
    def condition_label(self) -> str:
        return self.CONDITION_LABELS.get(self.road_condition, f"Code {self.road_condition}")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> dict | list:
    """Perform a GET request and return parsed JSON."""
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc.reason}") from exc


def _build_url(base: str, path: str, params: Optional[dict] = None) -> str:
    url = base.rstrip("/") + "/" + path.lstrip("/")
    if params:
        query = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v is not None
        )
        if query:
            url = f"{url}?{query}"
    return url


# Import urllib.parse which is needed for _build_url
import urllib.parse


# ---------------------------------------------------------------------------
# Camera API  — /cameras_v1/api
# ---------------------------------------------------------------------------

class CameraClient:
    """
    Client for the KDOT traffic camera REST API.

    Base URL: https://kstg.carsprogram.org/cameras_v1/api
    """

    BASE = f"{API_BASE}/cameras_v1/api"

    def list_cameras(
        self,
        route_id: Optional[str] = None,
        active_only: bool = False,
    ) -> List[Camera]:
        """
        Return all public cameras.

        Args:
            route_id: Optional route filter (e.g. "I-70", "KS 39", "US 281").
                      Filtering is done client-side since the API returns the
                      full list regardless of the query parameter.
            active_only: If True, return only cameras with active=True.

        Returns:
            List of Camera dataclass instances.
        """
        data = _get(f"{self.BASE}/cameras")
        cameras = [Camera.from_dict(c) for c in data]

        if route_id:
            route_id_upper = route_id.upper()
            cameras = [
                c for c in cameras
                if c.location.route_id.upper() == route_id_upper
            ]

        if active_only:
            cameras = [c for c in cameras if c.active]

        return cameras

    def get_camera(self, camera_id: int) -> Camera:
        """
        Fetch a single camera by its numeric ID.

        Args:
            camera_id: Integer camera ID (e.g. 2048).
        """
        data = _get(f"{self.BASE}/cameras/{camera_id}")
        return Camera.from_dict(data)

    def iter_snapshots(
        self,
        cameras: Optional[List[Camera]] = None,
        active_only: bool = True,
    ) -> Iterator[tuple[Camera, str]]:
        """
        Yield (camera, snapshot_url) tuples for all cameras that have
        a snapshot available.

        Args:
            cameras: Pre-fetched list; if None, fetches all cameras.
            active_only: Skip inactive cameras.
        """
        if cameras is None:
            cameras = self.list_cameras(active_only=active_only)
        for cam in cameras:
            url = cam.primary_snapshot_url
            if url:
                yield cam, url

    def download_snapshot(
        self,
        camera: Camera,
        dest_path: str,
        view_index: int = 0,
    ) -> str:
        """
        Download a camera snapshot JPEG to a file.

        Args:
            camera: Camera instance.
            dest_path: Local file path to write the JPEG.
            view_index: Which view to use (default 0 = first).

        Returns:
            The destination path.
        """
        if view_index >= len(camera.views):
            raise ValueError(f"Camera {camera.camera_id} has no view at index {view_index}")

        view = camera.views[view_index]
        snap_url = view.snapshot_url
        if not snap_url:
            raise ValueError(f"Camera {camera.camera_id} view {view_index} has no snapshot URL")

        req = urllib.request.Request(snap_url, headers=_DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            with open(dest_path, "wb") as fh:
                fh.write(resp.read())
        return dest_path

    def cameras_by_owner(
        self, cameras: Optional[List[Camera]] = None
    ) -> dict[str, List[Camera]]:
        """
        Group cameras by their owner agency.

        Returns:
            Dict mapping owner name -> list of cameras.
        """
        if cameras is None:
            cameras = self.list_cameras()
        result: dict[str, List[Camera]] = {}
        for cam in cameras:
            result.setdefault(cam.owner_name, []).append(cam)
        return result

    def cameras_near(
        self,
        lat: float,
        lon: float,
        radius_miles: float = 5.0,
        cameras: Optional[List[Camera]] = None,
    ) -> List[tuple[float, Camera]]:
        """
        Return cameras sorted by distance from a point.

        Args:
            lat, lon: Center coordinate.
            radius_miles: Maximum distance filter (approximate, Euclidean).
            cameras: Pre-fetched list; if None, fetches all cameras.

        Returns:
            List of (distance_miles_approx, Camera) sorted ascending.
        """
        import math

        if cameras is None:
            cameras = self.list_cameras(active_only=True)

        # Quick Euclidean approximation (good enough for short distances in Kansas)
        lat_deg_per_mile = 1 / 69.0
        lon_deg_per_mile = 1 / (69.0 * math.cos(math.radians(lat)))

        results = []
        for cam in cameras:
            dlat = (cam.location.latitude - lat) / lat_deg_per_mile
            dlon = (cam.location.longitude - lon) / lon_deg_per_mile
            dist = math.sqrt(dlat ** 2 + dlon ** 2)
            if dist <= radius_miles:
                results.append((dist, cam))

        results.sort(key=lambda x: x[0])
        return results


# ---------------------------------------------------------------------------
# Signs API  — /signs_v1/api
# ---------------------------------------------------------------------------

class SignClient:
    """
    Client for the KDOT Variable Message Signs (VMS) API.

    Base URL: https://kstg.carsprogram.org/signs_v1/api
    """

    BASE = f"{API_BASE}/signs_v1/api"

    def list_signs(
        self,
        route_id: Optional[str] = None,
        displaying_only: bool = False,
    ) -> List[Sign]:
        """
        Return all variable message signs.

        Args:
            route_id: Optional route filter (client-side, e.g. "I-70").
            displaying_only: If True, return only signs currently displaying a message.
        """
        data = _get(f"{self.BASE}/signs")
        signs = [Sign.from_dict(s) for s in data]

        if route_id:
            route_id_upper = route_id.upper()
            signs = [
                s for s in signs
                if s.location.route_id.upper() == route_id_upper
            ]

        if displaying_only:
            signs = [s for s in signs if s.is_displaying]

        return signs

    def get_sign(self, sign_id: str) -> Sign:
        """
        Fetch a single sign by its composite ID.

        Args:
            sign_id: String ID in format "kansassigns*179" or "kcscout*5".
        """
        encoded = urllib.parse.quote(sign_id, safe="*")
        data = _get(f"{self.BASE}/signs/{encoded}")
        return Sign.from_dict(data)

    def active_messages(self) -> List[Sign]:
        """Return all signs that are currently displaying messages."""
        return self.list_signs(displaying_only=True)


# ---------------------------------------------------------------------------
# Plow Tracker API  — /avl_v2/api
# ---------------------------------------------------------------------------

class PlowClient:
    """
    Client for the KDOT snowplow / AVL (Automatic Vehicle Location) API.

    Base URL: https://kstg.carsprogram.org/avl_v2/api
    Note: The API returns recent historical position records (breadcrumb trail),
    not just the latest position.
    """

    BASE = f"{API_BASE}/avl_v2/api"

    def list_plows(self) -> List[Plow]:
        """Return all tracked plow vehicles with recent position history."""
        data = _get(f"{self.BASE}/plows")
        return [Plow.from_dict(p) for p in data]

    def get_plow(self, plow_id: str) -> Plow:
        """
        Fetch position history for a single plow.

        Args:
            plow_id: String vehicle ID (e.g. "2683061").
        """
        data = _get(f"{self.BASE}/plows/{plow_id}")
        return Plow.from_dict(data)

    def latest_positions(self) -> List[tuple[Plow, PlowStatus]]:
        """
        Return (plow, latest_status) for each plow that has status records.
        Sorted by recorded_at descending.
        """
        plows = self.list_plows()
        result = []
        for plow in plows:
            status = plow.latest_status
            if status:
                result.append((plow, status))
        result.sort(key=lambda x: x[1].timestamp, reverse=True)
        return result


# ---------------------------------------------------------------------------
# Road Conditions  — ArcGIS FeatureServer (Midwest Winter Road Conditions)
# ---------------------------------------------------------------------------

class RoadConditionsClient:
    """
    Client for the ArcGIS-hosted Midwest Winter Road Conditions layer.

    This layer is shared across multiple Midwest DOTs. The FIPS filter
    restricts results to Kansas (FIPS=20).

    Source: https://services.arcgis.com/8lRhdTsQyJpO52F1/ArcGIS/rest/services/
            Midwest_Winter_Road_Conditions_View/FeatureServer/0/query
    """

    URL = ARCGIS_ROAD_CONDITIONS

    def get_conditions(
        self,
        state_fips: int = 20,
        where_extra: str = "",
        max_records: int = 2000,
    ) -> List[RoadConditionFeature]:
        """
        Fetch road condition segments.

        Args:
            state_fips: State FIPS code (20 = Kansas).
            where_extra: Additional SQL WHERE clause fragment (ANDed in).
            max_records: Maximum feature count to return.

        Returns:
            List of RoadConditionFeature instances.
        """
        where = f"1=1"
        if where_extra:
            where = f"{where} AND ({where_extra})"

        params = {
            "where": where,
            "outFields": "*",
            "f": "json",
            "resultRecordCount": str(max_records),
        }
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = f"{self.URL}?{query}"

        data = _get(url)
        features = data.get("features", [])
        return [RoadConditionFeature.from_dict(f) for f in features]

    def get_kansas_conditions(self) -> List[RoadConditionFeature]:
        """Convenience method: fetch all Kansas road condition segments."""
        return self.get_conditions(state_fips=20)

    def conditions_by_route(
        self, features: Optional[List[RoadConditionFeature]] = None
    ) -> dict[str, List[RoadConditionFeature]]:
        """
        Group road condition features by route name.

        Args:
            features: Pre-fetched list; fetches Kansas conditions if None.
        """
        if features is None:
            features = self.get_kansas_conditions()
        result: dict[str, List[RoadConditionFeature]] = {}
        for feat in features:
            result.setdefault(feat.route_name, []).append(feat)
        return result


# ---------------------------------------------------------------------------
# WZDx Work Zone Data  — /carsapi_v1/api/wzdx
# ---------------------------------------------------------------------------

class WorkZoneClient:
    """
    Client for the KDOT WZDx (Work Zone Data Exchange) feed.

    The feed provides standardized GeoJSON-based work zone information
    conforming to the FHWA WZDx specification.

    Endpoint: https://kscars.kandrive.gov/carsapi_v1/api/wzdx
    (redirected from https://ks.carsprogram.org/carsapi_v1/api/wzdx)
    """

    URL = "https://kscars.kandrive.gov/carsapi_v1/api/wzdx"

    def get_work_zones(self) -> dict:
        """
        Fetch the raw WZDx GeoJSON feed.

        Returns the full WZDx FeatureCollection dict with:
        - type: "FeatureCollection"
        - road_event_feed_info: Feed metadata
        - features: List of GeoJSON Features each with a road_event

        The road_event properties follow the WZDx specification:
        https://github.com/usdot-jpo-ode/wzdx
        """
        return _get(self.URL)

    def list_work_zone_features(self) -> List[dict]:
        """
        Return just the features array from the WZDx feed.

        Each feature is a GeoJSON Feature with properties following
        the WZDx road_event schema.
        """
        data = self.get_work_zones()
        return data.get("features", [])


# ---------------------------------------------------------------------------
# Composite "KanDriveClient" facade
# ---------------------------------------------------------------------------

class KanDriveClient:
    """
    High-level facade aggregating all KDOT KanDrive API services.

    Usage:
        client = KanDriveClient()
        cameras = client.cameras.list_cameras(route_id="I-70", active_only=True)
        signs = client.signs.active_messages()
        plows = client.plows.latest_positions()
        conditions = client.road_conditions.get_kansas_conditions()
        work_zones = client.work_zones.list_work_zone_features()
    """

    def __init__(self) -> None:
        self.cameras = CameraClient()
        self.signs = SignClient()
        self.plows = PlowClient()
        self.road_conditions = RoadConditionsClient()
        self.work_zones = WorkZoneClient()

    # ------------------------------------------------------------------
    # Convenience one-liners
    # ------------------------------------------------------------------

    def get_camera_snapshot_url(self, camera_id: int) -> Optional[str]:
        """Return the snapshot URL for a camera ID, or None."""
        cam = self.cameras.get_camera(camera_id)
        return cam.primary_snapshot_url

    def corridor_summary(self, route_id: str) -> dict:
        """
        Build a quick summary dict for a given route corridor.

        Returns a dict with keys: route_id, cameras, signs, conditions
        """
        cameras = self.cameras.list_cameras(route_id=route_id, active_only=True)
        signs = self.signs.list_signs(route_id=route_id, displaying_only=True)
        conditions = self.road_conditions.conditions_by_route().get(route_id, [])

        return {
            "route_id": route_id,
            "cameras": {
                "total": len(cameras),
                "streaming": sum(1 for c in cameras if c.hls_stream_url),
                "still_image": sum(1 for c in cameras if not c.hls_stream_url),
            },
            "signs": {
                "total": len(signs),
                "messages": [s.current_message for s in signs],
            },
            "road_conditions": {
                "segments": len(conditions),
                "conditions": list({c.condition_label for c in conditions}),
            },
        }


# ---------------------------------------------------------------------------
# Demo / self-test
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Run a quick live smoke-test against the real API."""
    print("=" * 60)
    print("KDOT KanDrive API — Live Demo")
    print("=" * 60)

    client = KanDriveClient()

    # --- Cameras -----------------------------------------------------------
    print("\n[1] Cameras")
    print("-" * 40)
    all_cameras = client.cameras.list_cameras()
    print(f"  Total cameras: {len(all_cameras)}")

    active = [c for c in all_cameras if c.active]
    streaming = [c for c in active if c.hls_stream_url]
    still = [c for c in active if not c.hls_stream_url]
    print(f"  Active: {len(active)}")
    print(f"  Streaming (HLS/WMP): {len(streaming)}")
    print(f"  Still image: {len(still)}")

    i70 = client.cameras.list_cameras(route_id="I-70", active_only=True)
    print(f"\n  I-70 active cameras: {len(i70)}")
    for cam in i70[:3]:
        snap = cam.primary_snapshot_url or "N/A"
        print(f"    [{cam.camera_id}] {cam.name}")
        print(f"       Owner: {cam.owner_name}")
        print(f"       Snapshot: {snap}")
        if cam.hls_stream_url:
            print(f"       HLS:  {cam.hls_stream_url}")

    # Example: single camera lookup
    cam_detail = client.cameras.get_camera(2048)
    print(f"\n  Camera 2048: {cam_detail.name}")
    print(f"    Location: {cam_detail.location.latitude:.4f}, {cam_detail.location.longitude:.4f}")
    print(f"    Updated: {cam_detail.updated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    for v in cam_detail.views:
        print(f"    View [{v.view_type}]: {v.url[:80]}")

    # Owners breakdown
    by_owner = client.cameras.cameras_by_owner(all_cameras)
    print(f"\n  Camera owners:")
    for owner, cams in sorted(by_owner.items(), key=lambda x: -len(x[1])):
        print(f"    {owner}: {len(cams)}")

    # --- Signs -------------------------------------------------------------
    print("\n[2] Variable Message Signs")
    print("-" * 40)
    all_signs = client.signs.list_signs()
    displaying = [s for s in all_signs if s.is_displaying]
    blank = [s for s in all_signs if s.is_blank]
    print(f"  Total signs: {len(all_signs)}")
    print(f"  Displaying message: {len(displaying)}")
    print(f"  Blank: {len(blank)}")

    i70_signs = client.signs.list_signs(route_id="I-70", displaying_only=True)
    print(f"\n  I-70 signs with active messages: {len(i70_signs)}")
    for sign in i70_signs[:5]:
        print(f"    [{sign.sign_id}] {sign.name}")
        print(f"       Message: {sign.current_message}")

    # --- Plows -------------------------------------------------------------
    print("\n[3] Snowplow Fleet")
    print("-" * 40)
    latest = client.plows.latest_positions()
    if not latest:
        print("  No plow data available (off-season or no active plows)")
    else:
        total_fleet = latest[0][1].total_truck_count if latest else 0
        print(f"  Plows reporting: {len(latest)}")
        print(f"  Total fleet size: {total_fleet}")
        for plow, status in latest[:3]:
            ts = status.recorded_at.strftime("%Y-%m-%d %H:%M UTC")
            print(f"    [{plow.plow_id}] {status.route_designator} — {status.heading_string}")
            print(f"       Near: {status.nearby_points_description}")
            print(f"       At: {ts}")

    # --- Road Conditions ---------------------------------------------------
    print("\n[4] Winter Road Conditions (ArcGIS)")
    print("-" * 40)
    try:
        conditions = client.road_conditions.get_kansas_conditions()
        print(f"  Kansas segments: {len(conditions)}")
        by_cond: dict[str, int] = {}
        for c in conditions:
            by_cond[c.condition_label] = by_cond.get(c.condition_label, 0) + 1
        for label, count in sorted(by_cond.items(), key=lambda x: -x[1]):
            print(f"    {label}: {count} segments")
    except Exception as exc:
        print(f"  Error fetching conditions: {exc}")

    # --- Corridor Summary --------------------------------------------------
    print("\n[5] I-70 Corridor Summary")
    print("-" * 40)
    summary = client.corridor_summary("I-70")
    print(f"  Cameras: {summary['cameras']['total']} active")
    print(f"    Streaming: {summary['cameras']['streaming']}")
    print(f"    Still image: {summary['cameras']['still_image']}")
    print(f"  Signs with messages: {summary['signs']['total']}")
    if summary["signs"]["messages"]:
        for msg in summary["signs"]["messages"][:3]:
            print(f"    - {msg}")

    print("\nDemo complete.")


if __name__ == "__main__":
    _demo()
