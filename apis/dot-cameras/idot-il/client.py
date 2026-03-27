"""
IDOT (Illinois Department of Transportation) Traffic & Conditions API Client
============================================================================

Python client (stdlib only) for the Getting Around Illinois system at
https://www.gettingaroundillinois.com

All data is sourced from public ArcGIS FeatureServer endpoints hosted by IDOT on
Esri's ArcGIS Online (org ID: aIrBD8yn1TDTEXoz). No authentication is required.

Live camera snapshot images are served from https://cctv.travelmidwest.com/snapshots/
Dynamic message sign images are served from https://travelmidwest.com/messageSign

Example usage:
    python3 idot_client.py                  # Run the built-in demo
    python3 idot_client.py cameras          # List cameras (paginated)
    python3 idot_client.py incidents        # Active road incidents
    python3 idot_client.py construction     # Active construction zones
    python3 idot_client.py winter           # Winter road conditions
    python3 idot_client.py rwis             # Weather station readings
    python3 idot_client.py dms              # Dynamic message signs
    python3 idot_client.py rest_areas       # Rest area status
    python3 idot_client.py ferries          # Waterway ferry status
    python3 idot_client.py closures         # Road closure events
"""

from __future__ import annotations

import json
import sys
import time
import argparse
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Iterator, Optional


# ---------------------------------------------------------------------------
# Base URL constants
# ---------------------------------------------------------------------------

_ARCGIS_BASE = (
    "https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services"
)
_CCTV_BASE = "https://cctv.travelmidwest.com/snapshots"
_DMS_IMAGE_BASE = "https://travelmidwest.com/messageSign"

# Mapping of service name -> feature server path
_SERVICES: dict[str, str] = {
    "cameras":       "TrafficCamerasTM_Public/FeatureServer/0",
    "incidents":     "Illinois_Roadway_Incidents/FeatureServer/0",
    "construction":  "Road_Construction_Public/FeatureServer/2",
    "winter":        "Wrc_Maintenance_Section_Road_Condition/FeatureServer/0",
    "rwis":          "RWIS/FeatureServer/0",
    "dms":           "DynamicMessaging/FeatureServer/0",
    "rest_areas":    "IL_Rest_Areas/FeatureServer/0",
    "ferries":       "Waterway_Ferries/FeatureServer/0",
    "closures":      "ClosureIncidents/FeatureServer/0",
    "closure_extents": "ClosureIncidentExtents/FeatureServer/0",
    "flooding":      "RegularlyFloodedRoadsForPublicUse/FeatureServer/0",
    "trouble_spots": "Winter_Trouble_Spots1/FeatureServer/0",
    "em_incidents":  "Travel_Midwest_Unplanned_Events/FeatureServer/0",
}

DEFAULT_PAGE_SIZE = 1000
DEFAULT_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """A traffic camera with snapshot URL and location metadata.

    The ``snapshot_url`` field points to a JPEG image that is refreshed
    approximately every 2 minutes at ``cctv.travelmidwest.com``.
    The ``view_url`` field opens the camera in the Travel Midwest viewer.
    """

    object_id: int
    camera_id: str
    """Unique camera identifier extracted from ``img_path``, e.g. ``IL-IDOTD1-camera_100``."""
    location: str
    direction: str
    latitude: float
    longitude: float
    snapshot_url: str
    view_url: str
    warning_age: bool
    too_old: bool
    age_minutes: int

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "Camera":
        """Construct a Camera from an ArcGIS feature dict."""
        a = feat["attributes"]
        img_path: str = a.get("ImgPath", "")
        # Parse camera_id from query param: ...?id=IL-IDOTD1-camera_100&direction=N
        parsed = urllib.parse.urlparse(img_path)
        qs = urllib.parse.parse_qs(parsed.query)
        camera_id = qs.get("id", [""])[0]
        return cls(
            object_id=a.get("OBJECTID", 0),
            camera_id=camera_id,
            location=a.get("CameraLocation", ""),
            direction=a.get("CameraDirection", ""),
            latitude=float(a.get("y", 0) or 0),
            longitude=float(a.get("x", 0) or 0),
            snapshot_url=a.get("SnapShot", ""),
            view_url=img_path,
            warning_age=bool(a.get("WarningAge", False)),
            too_old=bool(a.get("TooOld", False)),
            age_minutes=int(a.get("AgeInMinutes", 0) or 0),
        )


@dataclass
class Incident:
    """An active Illinois roadway incident (accident, debris, etc.)."""

    object_id: int
    incident_type: str
    criticality: str
    description: str
    verified: bool
    road_closed: bool
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    origin: str
    status: str
    full_closure: bool

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "Incident":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            incident_type=a.get("TRAFFIC_ITEM_TYPE_DESC", ""),
            criticality=a.get("CRITICALITY_DESC", ""),
            description=(
                a.get("TRAFFIC_ITEM_DESCRIPTION") or
                a.get("TRAFFIC_ITEM_DESCRIPTION_NO_EX") or ""
            ),
            verified=str(a.get("VERIFIED", "")).lower() == "true",
            road_closed=str(a.get("ROAD_CLOSED", "")).lower() == "true",
            start_time=_ms_to_datetime(a.get("START_TIME")),
            end_time=_ms_to_datetime(a.get("END_TIME")),
            origin=a.get("ORIGIN", ""),
            status=a.get("Status", ""),
            full_closure=str(a.get("FullClosure", "")).lower() == "true",
        )


@dataclass
class ConstructionZone:
    """An active or upcoming road construction zone."""

    object_id: int
    zone_id: str
    contractor: str
    district: str
    county: str
    near_town: str
    route: str
    location: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    construction_type: str
    lanes_closed: str
    suggestion: str
    traffic_alert: str
    status: str
    impact: str
    contract_value: str

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "ConstructionZone":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            zone_id=a.get("ID", ""),
            contractor=a.get("Contractor", ""),
            district=a.get("District", ""),
            county=a.get("County", ""),
            near_town=a.get("NearTown", ""),
            route=a.get("Route", ""),
            location=a.get("Location", ""),
            start_date=_ms_to_datetime(a.get("StartDate")),
            end_date=_ms_to_datetime(a.get("EndDate")),
            construction_type=a.get("ConstructionType", ""),
            lanes_closed=a.get("LanesRampsClosed", ""),
            suggestion=a.get("SuggestionToMotorist", ""),
            traffic_alert=a.get("TrafficAlert", ""),
            status=a.get("Status", ""),
            impact=a.get("ImpactOnTravel", ""),
            contract_value=a.get("ContractValue", ""),
        )


@dataclass
class WinterRoadCondition:
    """Winter road condition for a maintenance section."""

    object_id: int
    district: str
    section_name: str
    county: str
    route_code: str
    condition: str
    """One of: Clear, Wet, Slush, Packed Snow, Ice, etc."""
    wrc_id: int
    display_order: int

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "WinterRoadCondition":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            district=str(a.get("DIST", "")),
            section_name=a.get("WrcMntSectionName", ""),
            county=a.get("COUNTY_NAM", ""),
            route_code=a.get("STR_STATECODE", ""),
            condition=a.get("Condition", ""),
            wrc_id=int(a.get("WrcID", 0) or 0),
            display_order=int(a.get("DisplayOrder", 0) or 0),
        )


@dataclass
class RWISStation:
    """Roadway Weather Information System (RWIS) station reading.

    These are physical weather stations on Illinois roads reporting
    temperature, wind, precipitation, and pavement conditions.
    """

    object_id: int
    station_id: str
    display_name: str
    latitude: float
    longitude: float
    temp_f: int
    """Air temperature in Fahrenheit."""
    dew_point_f: int
    wind_speed_mph: int
    wind_gusts_mph: int
    wind_direction_deg: int
    relative_humidity_pct: int
    surface_condition: str
    surface_temp: str
    precip_type: int
    precip_intensity: int
    precip_yes_no: int
    precipitation_level: str
    observation_time: Optional[datetime]

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "RWISStation":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            station_id=a.get("StationID", ""),
            display_name=a.get("Displayname", ""),
            latitude=float(a.get("Latitude", 0) or 0),
            longitude=float(a.get("Longitude", 0) or 0),
            temp_f=int(a.get("Temperature", 0) or 0),
            dew_point_f=int(a.get("DewPoint", 0) or 0),
            wind_speed_mph=int(a.get("WindSpeed", 0) or 0),
            wind_gusts_mph=int(a.get("WindGusts", 0) or 0),
            wind_direction_deg=int(a.get("WindDirection", 0) or 0),
            relative_humidity_pct=int(a.get("RelativeHumidity", 0) or 0),
            surface_condition=a.get("SurfaceCondition", "") or "",
            surface_temp=str(a.get("SurfaceTemp", "") or ""),
            precip_type=int(a.get("PrecipType", 0) or 0),
            precip_intensity=int(a.get("PrecipIntensity", 0) or 0),
            precip_yes_no=int(a.get("PrecipYesNo", 0) or 0),
            precipitation_level=a.get("PrecipitationLevel", "") or "",
            observation_time=_ms_to_datetime(a.get("ObsDateTime_Local")),
        )


@dataclass
class DynamicMessageSign:
    """An overhead Dynamic Message Sign (DMS) and its current message.

    ``image_url`` retrieves a rendered image of the sign.
    The base URL is ``https://travelmidwest.com/messageSign?id=<sign_id>``.
    """

    object_id: int
    sign_id: str
    road_name: str
    direction: str
    location: str
    mile_marker: float
    latitude: float
    longitude: float
    message_line1: str
    message_line2: str
    message_line3: str
    image_url: str
    status: str
    timestamp: Optional[datetime]

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "DynamicMessageSign":
        a = feat["attributes"]
        sign_id = a.get("id", "")
        img_path = a.get("img_url", "")
        # img_url is relative like /messageSign?id=...
        # Construct absolute URL
        if img_path.startswith("/"):
            image_url = "https://travelmidwest.com" + img_path
        else:
            image_url = img_path
        return cls(
            object_id=a.get("ObjectId", 0),
            sign_id=sign_id,
            road_name=a.get("road_name", ""),
            direction=a.get("direction", ""),
            location=a.get("location", ""),
            mile_marker=float(a.get("mile_marker", 0) or 0),
            latitude=float(a.get("y", 0) or 0),
            longitude=float(a.get("x", 0) or 0),
            message_line1=a.get("message1", "") or "",
            message_line2=a.get("message2", "") or "",
            message_line3=a.get("message3", "") or "",
            image_url=image_url,
            status=a.get("status", ""),
            timestamp=_ms_to_datetime(a.get("timestamp")),
        )


@dataclass
class RestArea:
    """An Illinois rest area or welcome center along state highways."""

    object_id: int
    area_id: int
    name: str
    route: str
    location: str
    district: int
    latitude: float
    longitude: float
    status: str
    """Open, Closed, or Under Construction."""
    is_welcome_center: bool
    has_vending: bool
    has_weather_info: bool
    has_assisted_restroom: bool
    allows_semis: bool
    tty_station: bool

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "RestArea":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            area_id=int(a.get("id", 0) or 0),
            name=a.get("name", ""),
            route=a.get("route", ""),
            location=a.get("location", ""),
            district=int(a.get("district", 0) or 0),
            latitude=float(a.get("latitude", 0) or 0),
            longitude=float(a.get("longitude", 0) or 0),
            status=a.get("status", ""),
            is_welcome_center=a.get("center", "N").upper() == "Y",
            has_vending=a.get("vending", "N").upper() == "Y",
            has_weather_info=a.get("wthr_info", "N").upper() == "Y",
            has_assisted_restroom=a.get("assist_rr", "N").upper() == "Y",
            allows_semis=a.get("allow_semi", "N").upper() == "Y",
            tty_station=a.get("td_station", "N").upper() == "Y",
        )


@dataclass
class WaterwayFerry:
    """An Illinois waterway ferry crossing."""

    object_id: int
    name: str
    description: str
    status: str

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "WaterwayFerry":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            name=a.get("NAME", ""),
            description=a.get("DESCRIPTION", ""),
            status=a.get("Status", ""),
        )


@dataclass
class RoadClosure:
    """A road closure event (planned or emergency)."""

    object_id: int
    closure_id: str
    location: str
    near_town: str
    county: str
    closure_type: str
    direction: str
    street_name: str
    construction_type: str
    detour_route: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "RoadClosure":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            closure_id=a.get("ID", ""),
            location=a.get("Location", ""),
            near_town=a.get("NearTown", ""),
            county=a.get("County", ""),
            closure_type=a.get("ClosureType", ""),
            direction=a.get("Direction", ""),
            street_name=a.get("St_Name", ""),
            construction_type=a.get("ConstructionType", ""),
            detour_route=a.get("DetourRoute", ""),
            start_date=_ms_to_datetime(a.get("StartDate")),
            end_date=_ms_to_datetime(a.get("EndDate")),
        )


@dataclass
class UnplannedEvent:
    """A Travel Midwest unplanned (emergency) traffic event."""

    object_id: int
    event_id: str
    description: str
    location: str
    status: str
    full_closure: bool
    emergency_vehicle_present: bool
    source: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    duration: str

    @classmethod
    def from_feature(cls, feat: dict[str, Any]) -> "UnplannedEvent":
        a = feat["attributes"]
        return cls(
            object_id=a.get("OBJECTID", 0),
            event_id=a.get("id", ""),
            description=a.get("Description", ""),
            location=a.get("Location", ""),
            status=a.get("Status", ""),
            full_closure=str(a.get("FullClosure", "")).lower() == "true",
            emergency_vehicle_present=str(
                a.get("EmergencyVehiclePresent", "")
            ).lower() == "true",
            source=a.get("Source", ""),
            start_date=_ms_to_datetime(a.get("StartDate")),
            end_date=_ms_to_datetime(a.get("EndDate")),
            duration=a.get("Duration", ""),
        )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _ms_to_datetime(ms: Any) -> Optional[datetime]:
    """Convert an ArcGIS epoch-milliseconds timestamp to a UTC datetime.

    Returns None if the value is None, zero, or cannot be parsed.
    """
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _build_query_url(
    service_path: str,
    where: str = "1=1",
    out_fields: str = "*",
    result_offset: int = 0,
    result_count: int = DEFAULT_PAGE_SIZE,
    extra_params: Optional[dict[str, str]] = None,
) -> str:
    """Build an ArcGIS FeatureServer query URL."""
    params: dict[str, str] = {
        "where": where,
        "outFields": out_fields,
        "f": "json",
        "resultRecordCount": str(result_count),
        "resultOffset": str(result_offset),
    }
    if extra_params:
        params.update(extra_params)
    qs = urllib.parse.urlencode(params)
    return f"{_ARCGIS_BASE}/{service_path}/query?{qs}"


def _fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Fetch a URL and parse the response as JSON.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
        json.JSONDecodeError: If the response body is not valid JSON.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "IDOTClient/1.0 (Python urllib; public data)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def _get_count(service_path: str, where: str = "1=1") -> int:
    """Return the total feature count for a given where clause."""
    url = _build_query_url(
        service_path,
        where=where,
        out_fields="OBJECTID",
        result_count=0,
        extra_params={"returnCountOnly": "true"},
    )
    data = _fetch_json(url)
    return int(data.get("count", 0))


def _paginate(
    service_path: str,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = DEFAULT_PAGE_SIZE,
    max_records: int = 0,
    extra_params: Optional[dict[str, str]] = None,
) -> Iterator[dict[str, Any]]:
    """Yield raw ArcGIS feature dicts with automatic pagination.

    Args:
        service_path: Relative path like ``TrafficCamerasTM_Public/FeatureServer/0``.
        where: SQL-style WHERE clause string. Defaults to ``1=1`` (all records).
        out_fields: Comma-separated field names or ``*`` for all.
        page_size: Records per page request. Maximum 1000 per ArcGIS limit.
        max_records: Stop after yielding this many records (0 = no limit).
        extra_params: Additional query parameters to append.

    Yields:
        Individual ArcGIS feature dicts with ``attributes`` and ``geometry`` keys.
    """
    offset = 0
    total_yielded = 0
    while True:
        url = _build_query_url(
            service_path,
            where=where,
            out_fields=out_fields,
            result_offset=offset,
            result_count=page_size,
            extra_params=extra_params,
        )
        data = _fetch_json(url)
        features = data.get("features", [])
        if not features:
            break
        for feat in features:
            yield feat
            total_yielded += 1
            if max_records and total_yielded >= max_records:
                return
        if len(features) < page_size:
            break
        offset += page_size


# ---------------------------------------------------------------------------
# IDOTClient
# ---------------------------------------------------------------------------

class IDOTClient:
    """Client for the Illinois Department of Transportation public data APIs.

    All methods return lists of typed dataclass instances. Data is fetched
    live from ArcGIS FeatureServer endpoints and requires no authentication.

    Args:
        timeout: HTTP request timeout in seconds (default: 30).
        page_size: Records per paginated request (max 1000, default: 1000).

    Example:
        >>> client = IDOTClient()
        >>> cameras = client.get_cameras(max_records=10)
        >>> print(cameras[0].snapshot_url)
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self.timeout = timeout
        self.page_size = page_size

    # --- Cameras ---

    def get_cameras(
        self,
        where: str = "1=1",
        max_records: int = 0,
        exclude_old: bool = False,
    ) -> list[Camera]:
        """Retrieve traffic camera records.

        There are ~3,600 camera view records in total (multiple directions
        per physical camera). Each includes a live JPEG snapshot URL.

        Args:
            where: ArcGIS SQL WHERE clause for filtering.
                   Example: ``"CameraDirection='N'"`` or
                   ``"CameraLocation LIKE '%I-90%'"``.
            max_records: Maximum records to return (0 = all).
            exclude_old: If True, exclude cameras where ``TooOld`` is True.

        Returns:
            List of Camera dataclass instances.
        """
        if exclude_old:
            if where.strip() == "1=1":
                where = "TooOld='false'"
            else:
                where = f"({where}) AND TooOld='false'"
        return [
            Camera.from_feature(f)
            for f in _paginate(
                _SERVICES["cameras"],
                where=where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    def get_camera_snapshot_url(self, camera: Camera) -> str:
        """Return the live snapshot image URL for a camera.

        The URL is already stored on the Camera object; this method
        is a convenience accessor for clarity.
        """
        return camera.snapshot_url

    def count_cameras(self, where: str = "1=1") -> int:
        """Return total camera record count matching ``where``."""
        return _get_count(_SERVICES["cameras"], where=where)

    # --- Incidents ---

    def get_incidents(
        self,
        where: str = "1=1",
        max_records: int = 0,
        incident_types: Optional[list[str]] = None,
        critical_only: bool = False,
    ) -> list[Incident]:
        """Retrieve active roadway incidents (accidents, debris, hazards).

        Args:
            where: ArcGIS SQL WHERE clause.
            max_records: Maximum records to return (0 = all).
            incident_types: Filter by incident type strings, e.g.
                            ``["ROAD_CLOSURE", "ACCIDENT"]``.
            critical_only: If True, return only ``CRITICALITY_DESC='critical'``.

        Returns:
            List of Incident dataclass instances.
        """
        filters = []
        if where.strip() != "1=1":
            filters.append(f"({where})")
        if incident_types:
            type_list = ",".join(f"'{t}'" for t in incident_types)
            filters.append(f"TRAFFIC_ITEM_TYPE_DESC IN ({type_list})")
        if critical_only:
            filters.append("CRITICALITY_DESC='critical'")
        effective_where = " AND ".join(filters) if filters else "1=1"
        return [
            Incident.from_feature(f)
            for f in _paginate(
                _SERVICES["incidents"],
                where=effective_where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    def count_incidents(self, where: str = "1=1") -> int:
        """Return total incident count matching ``where``."""
        return _get_count(_SERVICES["incidents"], where=where)

    # --- Construction ---

    def get_construction(
        self,
        where: str = "1=1",
        max_records: int = 0,
        district: Optional[str] = None,
        county: Optional[str] = None,
    ) -> list[ConstructionZone]:
        """Retrieve active road construction zones.

        Args:
            where: ArcGIS SQL WHERE clause.
            max_records: Maximum records to return (0 = all).
            district: Filter by IDOT district number string, e.g. ``"1"`` through ``"9"``.
            county: Filter by county name (uppercase), e.g. ``"COOK"``.

        Returns:
            List of ConstructionZone dataclass instances.
        """
        filters = []
        if where.strip() != "1=1":
            filters.append(f"({where})")
        if district:
            filters.append(f"District='{district}'")
        if county:
            filters.append(f"County='{county.upper()}'")
        effective_where = " AND ".join(filters) if filters else "1=1"
        return [
            ConstructionZone.from_feature(f)
            for f in _paginate(
                _SERVICES["construction"],
                where=effective_where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    def count_construction(self, where: str = "1=1") -> int:
        """Return total construction zone count."""
        return _get_count(_SERVICES["construction"], where=where)

    # --- Winter conditions ---

    def get_winter_conditions(
        self,
        where: str = "1=1",
        max_records: int = 0,
        district: Optional[str] = None,
        condition: Optional[str] = None,
    ) -> list[WinterRoadCondition]:
        """Retrieve winter road condition segments.

        Condition values include: ``Clear``, ``Wet``, ``Slush``,
        ``Packed Snow``, ``Ice``, ``Treated``, and others.

        Args:
            where: ArcGIS SQL WHERE clause.
            max_records: Maximum records to return (0 = all).
            district: Filter by district number string, e.g. ``"1"``.
            condition: Filter by exact condition string.

        Returns:
            List of WinterRoadCondition instances.
        """
        filters = []
        if where.strip() != "1=1":
            filters.append(f"({where})")
        if district:
            filters.append(f"DIST='{district}'")
        if condition:
            filters.append(f"Condition='{condition}'")
        effective_where = " AND ".join(filters) if filters else "1=1"
        return [
            WinterRoadCondition.from_feature(f)
            for f in _paginate(
                _SERVICES["winter"],
                where=effective_where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    def count_winter_conditions(self, where: str = "1=1") -> int:
        """Return total winter condition segment count."""
        return _get_count(_SERVICES["winter"], where=where)

    # --- RWIS weather stations ---

    def get_rwis_stations(
        self,
        where: str = "1=1",
        max_records: int = 0,
    ) -> list[RWISStation]:
        """Retrieve Roadway Weather Information System (RWIS) station readings.

        There are ~36 RWIS stations across Illinois. Data includes temperature,
        wind, humidity, precipitation type/intensity, and pavement condition.

        Returns:
            List of RWISStation dataclass instances with current conditions.
        """
        return [
            RWISStation.from_feature(f)
            for f in _paginate(
                _SERVICES["rwis"],
                where=where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    # --- Dynamic Message Signs ---

    def get_dynamic_message_signs(
        self,
        where: str = "1=1",
        max_records: int = 0,
        road_name: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> list[DynamicMessageSign]:
        """Retrieve Overhead Dynamic Message Sign (DMS) current messages.

        There are ~576 DMS signs, including some from neighboring states
        (Iowa) visible on the Illinois border. Each sign has up to 3
        message lines and an image URL rendering the sign.

        Args:
            where: ArcGIS SQL WHERE clause.
            max_records: Maximum records to return (0 = all).
            road_name: Filter by road name, e.g. ``"I-90"`` or ``"I-55"``.
            direction: Filter by direction, e.g. ``"NB"`` or ``"SB"``.

        Returns:
            List of DynamicMessageSign instances.
        """
        filters = []
        if where.strip() != "1=1":
            filters.append(f"({where})")
        if road_name:
            filters.append(f"road_name='{road_name}'")
        if direction:
            filters.append(f"direction='{direction}'")
        effective_where = " AND ".join(filters) if filters else "1=1"
        return [
            DynamicMessageSign.from_feature(f)
            for f in _paginate(
                _SERVICES["dms"],
                where=effective_where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    # --- Rest areas ---

    def get_rest_areas(
        self,
        where: str = "1=1",
        open_only: bool = False,
        district: Optional[int] = None,
    ) -> list[RestArea]:
        """Retrieve Illinois rest area and welcome center status.

        There are ~54 rest areas statewide. Status includes Open, Closed,
        and Under Construction.

        Args:
            where: ArcGIS SQL WHERE clause.
            open_only: If True, return only areas with ``status='Open'``.
            district: Filter by IDOT district integer (1-9).

        Returns:
            List of RestArea instances.
        """
        filters = []
        if where.strip() != "1=1":
            filters.append(f"({where})")
        if open_only:
            filters.append("status='Open'")
        if district is not None:
            filters.append(f"district={district}")
        effective_where = " AND ".join(filters) if filters else "1=1"
        return [
            RestArea.from_feature(f)
            for f in _paginate(
                _SERVICES["rest_areas"],
                where=effective_where,
                page_size=self.page_size,
            )
        ]

    # --- Waterway ferries ---

    def get_waterway_ferries(self) -> list[WaterwayFerry]:
        """Retrieve status of Illinois waterway ferry crossings.

        Three ferries operate on Illinois rivers: Cave-in-Rock (Ohio River),
        Kampsville (Illinois River), and Brussels (Illinois River).

        Returns:
            List of WaterwayFerry instances with current status.
        """
        return [
            WaterwayFerry.from_feature(f)
            for f in _paginate(_SERVICES["ferries"], page_size=100)
        ]

    # --- Road closures ---

    def get_road_closures(
        self,
        where: str = "1=1",
        max_records: int = 0,
    ) -> list[RoadClosure]:
        """Retrieve active road closure events.

        These are planned closures (construction-driven) distinct from
        emergency incidents. For emergency closures see ``get_unplanned_events``.

        Returns:
            List of RoadClosure instances.
        """
        return [
            RoadClosure.from_feature(f)
            for f in _paginate(
                _SERVICES["closures"],
                where=where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    # --- Unplanned / emergency events ---

    def get_unplanned_events(
        self,
        where: str = "1=1",
        max_records: int = 0,
    ) -> list[UnplannedEvent]:
        """Retrieve Travel Midwest unplanned (emergency) traffic events.

        These are non-construction incidents including emergency closures,
        accidents, and natural disasters affecting Illinois roadways.

        Returns:
            List of UnplannedEvent instances.
        """
        return [
            UnplannedEvent.from_feature(f)
            for f in _paginate(
                _SERVICES["em_incidents"],
                where=where,
                page_size=self.page_size,
                max_records=max_records,
            )
        ]

    # --- GeoJSON convenience ---

    def get_cameras_geojson(
        self,
        where: str = "1=1",
        max_records: int = 500,
    ) -> dict[str, Any]:
        """Return camera data as a GeoJSON FeatureCollection.

        Fetches directly from the ArcGIS GeoJSON endpoint (f=geojson).
        Suitable for use with mapping libraries like folium, leaflet, etc.

        Args:
            where: SQL filter. Defaults to all cameras.
            max_records: Maximum cameras to include (default 500).

        Returns:
            A standard GeoJSON FeatureCollection dict.
        """
        params = {
            "where": where,
            "outFields": "*",
            "f": "geojson",
            "resultRecordCount": str(max_records),
        }
        qs = urllib.parse.urlencode(params)
        url = f"{_ARCGIS_BASE}/{_SERVICES['cameras']}/query?{qs}"
        return _fetch_json(url)

    # --- Service info ---

    def get_service_counts(self) -> dict[str, int]:
        """Return feature counts for all tracked services.

        Useful for monitoring data availability and staleness.

        Returns:
            Dict mapping service name to record count.
        """
        counts = {}
        for name, path in _SERVICES.items():
            try:
                counts[name] = _get_count(path)
            except Exception:
                counts[name] = -1
        return counts


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _demo_cameras(client: IDOTClient) -> None:
    print("\n=== Traffic Cameras (first 5, any direction) ===")
    cameras = client.get_cameras(max_records=5)
    for cam in cameras:
        print(f"  [{cam.object_id}] {cam.location} ({cam.direction})")
        print(f"       Lat/Lon: {cam.latitude:.4f}, {cam.longitude:.4f}")
        print(f"       Snapshot: {cam.snapshot_url}")
        print(f"       Age: {cam.age_minutes} min | TooOld: {cam.too_old}")
    total = client.count_cameras()
    print(f"  Total cameras in system: {total}")


def _demo_incidents(client: IDOTClient) -> None:
    print("\n=== Road Incidents (first 5) ===")
    incidents = client.get_incidents(max_records=5)
    for inc in incidents:
        print(f"  [{inc.object_id}] {inc.incident_type} | {inc.criticality}")
        print(f"       Description: {inc.description[:80]}")
        print(f"       Start: {_fmt_dt(inc.start_time)} | Closed: {inc.road_closed}")
    total = client.count_incidents()
    print(f"  Total active incidents: {total}")


def _demo_construction(client: IDOTClient) -> None:
    print("\n=== Construction Zones (first 5) ===")
    zones = client.get_construction(max_records=5)
    for z in zones:
        print(f"  [{z.object_id}] District {z.district} | {z.county} County")
        print(f"       Route: {z.route} | Near: {z.near_town}")
        print(f"       Type: {z.construction_type} | Status: {z.status}")
        print(f"       {_fmt_dt(z.start_date)} to {_fmt_dt(z.end_date)}")
    total = client.count_construction()
    print(f"  Total construction zones: {total}")


def _demo_winter(client: IDOTClient) -> None:
    print("\n=== Winter Road Conditions (sample by district) ===")
    from collections import Counter
    all_cond = client.get_winter_conditions()
    by_condition: Counter = Counter(c.condition for c in all_cond)
    print(f"  Total sections: {len(all_cond)}")
    print("  Condition breakdown:")
    for cond, count in sorted(by_condition.items()):
        print(f"    {cond}: {count} sections")
    # Show a few non-clear ones if any
    non_clear = [c for c in all_cond if c.condition.lower() not in ("clear", "")]
    if non_clear:
        print("  Non-clear sections (first 3):")
        for c in non_clear[:3]:
            print(f"    Dist {c.district}: {c.section_name} -> {c.condition}")


def _demo_rwis(client: IDOTClient) -> None:
    print("\n=== RWIS Weather Stations (all) ===")
    stations = client.get_rwis_stations()
    for s in stations[:5]:
        print(f"  [{s.station_id}] {s.display_name}")
        print(f"       Temp: {s.temp_f}°F | Dew: {s.dew_point_f}°F | RH: {s.relative_humidity_pct}%")
        print(f"       Wind: {s.wind_speed_mph} mph (gusts {s.wind_gusts_mph}) from {s.wind_direction_deg}°")
        print(f"       Surface: {s.surface_condition or 'N/A'} | Precip: {s.precipitation_level or 'none'}")
        print(f"       Observed: {_fmt_dt(s.observation_time)}")
    print(f"  Total RWIS stations: {len(stations)}")


def _demo_dms(client: IDOTClient) -> None:
    print("\n=== Dynamic Message Signs (first 5) ===")
    signs = client.get_dynamic_message_signs(max_records=5)
    for s in signs:
        print(f"  [{s.sign_id}] {s.road_name} {s.direction} at {s.location}")
        for i, line in enumerate([s.message_line1, s.message_line2, s.message_line3], 1):
            if line:
                print(f"       Line {i}: {line}")
        print(f"       Image: {s.image_url}")
    total_dms = _get_count(_SERVICES["dms"])
    print(f"  Total DMS signs: {total_dms}")


def _demo_rest_areas(client: IDOTClient) -> None:
    print("\n=== Rest Areas ===")
    areas = client.get_rest_areas()
    open_areas = [a for a in areas if a.status == "Open"]
    closed_areas = [a for a in areas if a.status != "Open"]
    print(f"  Total: {len(areas)} | Open: {len(open_areas)} | Other: {len(closed_areas)}")
    for a in areas[:3]:
        print(f"  [{a.area_id}] {a.name} | {a.route}")
        print(f"       Status: {a.status} | Welcome Center: {a.is_welcome_center}")
        print(f"       Semis: {a.allows_semis} | Vending: {a.has_vending}")


def _demo_ferries(client: IDOTClient) -> None:
    print("\n=== Waterway Ferries ===")
    ferries = client.get_waterway_ferries()
    for f in ferries:
        print(f"  {f.name}: {f.status}")
        print(f"       {f.description[:100]}")


def _demo_closures(client: IDOTClient) -> None:
    print("\n=== Road Closures ===")
    closures = client.get_road_closures()
    print(f"  Total active closures: {len(closures)}")
    for c in closures[:3]:
        print(f"  [{c.closure_id}] {c.location}")
        print(f"       County: {c.county} | Type: {c.closure_type}")
        print(f"       {_fmt_dt(c.start_date)} to {_fmt_dt(c.end_date)}")


def _run_demo(client: IDOTClient) -> None:
    print("=" * 60)
    print("IDOT Getting Around Illinois - API Demo")
    print(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    _demo_cameras(client)
    _demo_incidents(client)
    _demo_construction(client)
    _demo_winter(client)
    _demo_rwis(client)
    _demo_dms(client)
    _demo_rest_areas(client)
    _demo_ferries(client)
    _demo_closures(client)
    print("\nDemo complete.")


def main() -> None:
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="IDOT Getting Around Illinois API client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="demo",
        choices=[
            "demo", "cameras", "incidents", "construction",
            "winter", "rwis", "dms", "rest_areas", "ferries",
            "closures", "counts",
        ],
        help="Data endpoint to query (default: demo)",
    )
    parser.add_argument(
        "--where",
        default="1=1",
        help="ArcGIS SQL WHERE clause for filtering",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="Maximum records to return (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    args = parser.parse_args()

    client = IDOTClient()

    if args.command == "demo":
        _run_demo(client)
        return

    if args.command == "counts":
        counts = client.get_service_counts()
        if args.json:
            print(json.dumps(counts, indent=2))
        else:
            print("\n=== Service Record Counts ===")
            for name, count in counts.items():
                print(f"  {name}: {count}")
        return

    dispatch = {
        "cameras":      lambda: client.get_cameras(where=args.where, max_records=args.max),
        "incidents":    lambda: client.get_incidents(where=args.where, max_records=args.max),
        "construction": lambda: client.get_construction(where=args.where, max_records=args.max),
        "winter":       lambda: client.get_winter_conditions(where=args.where, max_records=args.max),
        "rwis":         lambda: client.get_rwis_stations(where=args.where, max_records=args.max),
        "dms":          lambda: client.get_dynamic_message_signs(where=args.where, max_records=args.max),
        "rest_areas":   lambda: client.get_rest_areas(where=args.where),
        "ferries":      lambda: client.get_waterway_ferries(),
        "closures":     lambda: client.get_road_closures(where=args.where, max_records=args.max),
    }

    results = dispatch[args.command]()

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2, default=str))
    else:
        print(f"\n=== {args.command.upper()} ({len(results)} records) ===")
        for item in results:
            d = asdict(item)
            for k, v in d.items():
                if v not in (None, "", False, 0):
                    print(f"  {k}: {v}")
            print()


if __name__ == "__main__":
    main()
