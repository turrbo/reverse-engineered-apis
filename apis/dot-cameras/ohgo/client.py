#!/usr/bin/env python3
"""
ohgo_client.py — Python client for the OHGO / ODOT Public Traffic API
======================================================================

The Ohio Department of Transportation (ODOT) operates the OHGO traffic
information platform at https://www.ohgo.com.  This module wraps the
officially documented REST API at https://publicapi.ohgo.com/api/v1.

API Version : v1  (OpenAPI 3.0.4, confirmed 2026-03-27)
Base URL    : https://publicapi.ohgo.com
Auth        : Bearer token  OR  ``?api-key=<key>`` query parameter

Registration for a free API key:
    https://publicapi.ohgo.com/accounts/registration

Official documentation:
    https://publicapi.ohgo.com/docs/v1/resources
    https://publicapi.ohgo.com/docs/v1/swagger/index.html

Usage (library)::

    from ohgo_client import OHGOClient
    client = OHGOClient(api_key="YOUR_KEY")
    result = client.get_cameras(region="cleveland")
    for cam in result.results:
        print(cam.location, cam.camera_views[0].small_url)

Usage (CLI)::

    python ohgo_client.py --api-key YOUR_KEY cameras --region cleveland
    python ohgo_client.py --api-key YOUR_KEY incidents --page-all
    python ohgo_client.py --api-key YOUR_KEY weather --hazards-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://publicapi.ohgo.com"
API_V1 = f"{BASE_URL}/api/v1"

#: Valid region names accepted by the ``region`` filter.
VALID_REGIONS = [
    "akron",
    "central-ohio",
    "cincinnati",
    "cleveland",
    "columbus",
    "dayton",
    "ne-ohio",
    "nw-ohio",
    "se-ohio",
    "sw-ohio",
    "toledo",
]

#: Valid sign-type values for the digital-signs endpoint.
VALID_SIGN_TYPES = [
    "dms",           # alias: message-board
    "message-board",
    "ddms",          # alias: travel-time
    "travel-time",
    "sign-queue",    # alias: slow-traffic
    "slow-traffic",
    "vsl",           # alias: variable-speed-limit
    "variable-speed-limit",
    "tp",            # alias: truck-parking
    "truck-parking",
]

# ---------------------------------------------------------------------------
# Primitive dataclasses — mirrors the OpenAPI component schemas exactly
# ---------------------------------------------------------------------------


@dataclass
class Link:
    """Hypermedia link embedded in every OHGO resource.

    ``rel`` is one of ``"self"``, ``"documentation"``, or ``"redirect"``.
    ``method`` defaults to ``GET`` when absent.
    """

    href: str
    rel: str
    method: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Link":
        return cls(
            href=d["href"],
            rel=d["rel"],
            method=d.get("method"),
        )


@dataclass
class QueryParam:
    """A filter parameter echoed back in the API result envelope.

    Accepted filters appear in ``accecptedFilters`` (the API spells it with
    the double-c typo); rejected (invalid) filters appear in
    ``rejectedFilters``.
    """

    key: str
    value: str
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QueryParam":
        return cls(
            key=d["key"],
            value=d["value"],
            error=d.get("error"),
        )


# ---------------------------------------------------------------------------
# Camera dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CameraView:
    """A single physical camera device at a camera site.

    ``direction`` may be a compass direction (N, S, E, W, NE, …) or
    ``"PTZ"`` meaning the camera is pan-tilt-zoom and has no fixed heading.

    Both ``small_url`` and ``large_url`` point to JPEG snapshots that the
    CDN refreshes every 5 seconds.
    """

    direction: str
    small_url: str
    large_url: str
    main_route: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CameraView":
        return cls(
            direction=d["direction"],
            small_url=d["smallUrl"],
            large_url=d["largeUrl"],
            main_route=d["mainRoute"],
        )


@dataclass
class Camera:
    """An ODOT-monitored camera site.

    A single site may host multiple physical cameras (``camera_views``).
    Images are JPEG snapshots updated every 5 seconds via CDN.
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    camera_views: List[CameraView]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Camera":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            camera_views=[CameraView.from_dict(v) for v in d.get("cameraViews", [])],
        )


# ---------------------------------------------------------------------------
# Construction dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ConstructionWorkZone:
    """Geographic extent of a single construction work zone."""

    start_location: Optional[List[float]] = None   # [longitude, latitude]
    end_location: Optional[List[float]] = None     # [longitude, latitude]
    polyline: Optional[List[List[float]]] = None   # [[lon, lat], ...]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConstructionWorkZone":
        return cls(
            start_location=d.get("startLocation"),
            end_location=d.get("endLocation"),
            polyline=d.get("polyline"),
        )


@dataclass
class ConstructionDetourRoute:
    """A single road segment that forms part of a construction detour."""

    road_name: Optional[str] = None
    start_location: Optional[List[float]] = None
    end_location: Optional[List[float]] = None
    polyline: Optional[List[List[float]]] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConstructionDetourRoute":
        return cls(
            road_name=d.get("roadName"),
            start_location=d.get("startLocation"),
            end_location=d.get("endLocation"),
            polyline=d.get("polyline"),
        )


@dataclass
class ConstructionDetour:
    """A full detour associated with a construction event."""

    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    detour_routes: List[ConstructionDetourRoute] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConstructionDetour":
        return cls(
            name=d.get("name"),
            description=d.get("description"),
            start_date=d.get("startDate"),
            end_date=d.get("endDate"),
            detour_routes=[
                ConstructionDetourRoute.from_dict(r)
                for r in (d.get("detourRoutes") or [])
            ],
        )


@dataclass
class Construction:
    """An ODOT-tracked construction event.

    ``category`` is either ``"Planned"`` or ``"Unplanned"``.
    ``status`` is ``"Open"``, ``"Restricted"``, or ``"Closed"``.
    ``district`` is an ODOT district identifier (e.g. ``"District 12"``).
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    category: str
    direction: str
    district: str
    route_name: str
    status: str
    start_date: Optional[str]
    end_date: Optional[str]
    work_zones: List[ConstructionWorkZone] = field(default_factory=list)
    detours: List[ConstructionDetour] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Construction":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            category=d["category"],
            direction=d["direction"],
            district=d["district"],
            route_name=d["routeName"],
            status=d["status"],
            start_date=d.get("startDate"),
            end_date=d.get("endDate"),
            work_zones=[
                ConstructionWorkZone.from_dict(z)
                for z in (d.get("workZones") or [])
            ],
            detours=[
                ConstructionDetour.from_dict(dt)
                for dt in (d.get("detours") or [])
            ],
        )


# ---------------------------------------------------------------------------
# Incident dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RoadClosureDetails:
    """Geometry describing a road closure associated with an incident."""

    closure_start_location: Optional[List[float]] = None
    closure_end_location: Optional[List[float]] = None
    polyline: Optional[List[List[float]]] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RoadClosureDetails":
        return cls(
            closure_start_location=d.get("closureStartLocation"),
            closure_end_location=d.get("closureEndLocation"),
            polyline=d.get("polyline"),
        )


@dataclass
class Incident:
    """An ODOT-tracked traffic incident.

    Incidents include accidents, weather-related events, and other
    occurrences that impact traffic flow.

    ``category`` describes the incident type (e.g. ``"Accident"``,
    ``"Weather"``, ``"Hazard"``).
    ``road_status`` is ``"Open"``, ``"Closed"``, or ``"Partial Closure"``.
    ``road_closure_details`` is present only when the road is closed or
    partially closed.
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    category: str
    direction: str
    route_name: str
    road_status: str
    road_closure_details: Optional[RoadClosureDetails] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Incident":
        rcd = d.get("roadClosureDetails")
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            category=d["category"],
            direction=d["direction"],
            route_name=d["routeName"],
            road_status=d["roadStatus"],
            road_closure_details=RoadClosureDetails.from_dict(rcd) if rcd else None,
        )


# ---------------------------------------------------------------------------
# Dangerous Slowdown dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DangerousSlowdown:
    """A location where traffic speed has dropped dangerously below normal.

    ``normal_mph`` is the typical (baseline) speed at this location.
    ``current_mph`` is the real-time measured speed.
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    normal_mph: int
    current_mph: int
    route_name: str
    direction: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DangerousSlowdown":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            normal_mph=d["normalMPH"],
            current_mph=d["currentMPH"],
            route_name=d["routeName"],
            direction=d["direction"],
        )


# ---------------------------------------------------------------------------
# Digital Sign dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DigitalSign:
    """An ODOT-monitored dynamic message sign (DMS) or similar device.

    ``sign_type_name`` values include ``"Travel Times"``,
    ``"Message Board"``, ``"Slow Traffic"``, ``"Variable Speed Limit"``,
    and ``"Truck Parking"``.

    ``messages`` is the list of text lines currently displayed.
    ``image_urls`` contains JPEG images of sign faces (when available).
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    sign_type_name: str
    messages: List[str]
    image_urls: List[str]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DigitalSign":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            sign_type_name=d["signTypeName"],
            messages=d.get("messages", []),
            image_urls=d.get("imageUrls", []),
        )


# ---------------------------------------------------------------------------
# Travel Delay dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TravelDelay:
    """Travel time and delay metrics for a monitored road segment.

    ``travel_time`` is the current estimated travel time in minutes.
    ``delay_time`` is the extra delay (above normal) in minutes.
    ``current_avg_speed`` and ``normal_avg_speed`` are in mph.
    ``start_mile_marker`` / ``end_mile_marker`` bound the segment.
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    direction: str
    route_name: str
    travel_time: float
    delay_time: float
    start_mile_marker: float
    end_mile_marker: float
    current_avg_speed: float
    normal_avg_speed: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TravelDelay":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            direction=d["direction"],
            route_name=d["routeName"],
            travel_time=d["travelTime"],
            delay_time=d["delayTime"],
            start_mile_marker=d["startMileMarker"],
            end_mile_marker=d["endMileMarker"],
            current_avg_speed=d["currentAvgSpeed"],
            normal_avg_speed=d["normalAvgSpeed"],
        )


# ---------------------------------------------------------------------------
# Truck Parking dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TruckParking:
    """An ODOT-monitored commercial vehicle parking location.

    ``capacity`` and ``reported_available`` are strings (the API returns
    them as strings, e.g. ``"47"`` or ``"unknown"``).
    ``open`` indicates whether the facility is currently operational.
    ``last_reported`` is the ISO-8601 timestamp of the last space count.
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    capacity: Optional[str] = None
    reported_available: Optional[str] = None
    open: bool = False
    last_reported: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TruckParking":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d.get("location"),
            description=d.get("description"),
            address=d.get("address"),
            capacity=d.get("capacity"),
            reported_available=d.get("reportedAvailable"),
            open=bool(d.get("open", False)),
            last_reported=d.get("lastReported"),
        )


# ---------------------------------------------------------------------------
# Weather Sensor Site dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AtmosphericSensor:
    """Atmospheric weather sensor readings.

    All temperature fields are in Fahrenheit; speeds are in mph;
    ``visibility`` is in miles; ``pressure`` is in millibars.
    """

    air_temperature: float
    dewpoint_temperature: float
    humidity: float
    average_wind_speed: float
    maximum_wind_speed: float
    wind_direction: str
    pressure: float
    precipitation: str
    precipitation_rate: float
    precipitation_accumulation: float
    precipitation_intensity: str
    visibility: float
    last_update: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AtmosphericSensor":
        return cls(
            air_temperature=d["airTemperature"],
            dewpoint_temperature=d["dewpointTemperature"],
            humidity=d["humidity"],
            average_wind_speed=d["averageWindSpeed"],
            maximum_wind_speed=d["maximumWindSpeed"],
            wind_direction=d["windDirection"],
            pressure=d["pressure"],
            precipitation=d["precipitation"],
            precipitation_rate=d["precipitationRate"],
            precipitation_accumulation=d["precipitationAccumulation"],
            precipitation_intensity=d["precipitationintensity"],
            visibility=d["visibility"],
            last_update=d["lastUpdate"],
        )


@dataclass
class SurfaceSensor:
    """Pavement / sub-pavement temperature sensor readings.

    All temperature fields are in Fahrenheit.
    """

    name: str
    status: str
    surface_temperature: float
    sub_surface_temperature: float
    last_update: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SurfaceSensor":
        return cls(
            name=d["name"],
            status=d["status"],
            surface_temperature=d["surfaceTemperature"],
            sub_surface_temperature=d["subSurfaceTemperature"],
            last_update=d["lastUpdate"],
        )


@dataclass
class WeatherSensorSite:
    """An ODOT roadside weather information system (RWIS) station.

    ``severe`` is ``True`` when hazardous conditions are detected.
    ``condition`` describes the hazard (e.g. ``"snow"``, ``"ice"``,
    ``"high wind"``) when ``severe`` is ``True``.
    ``average_air_temperature`` is a Fahrenheit string averaged across all
    atmospheric sensors at the site.
    """

    links: List[Link]
    id: str
    latitude: float
    longitude: float
    location: str
    description: str
    average_air_temperature: str
    atmospheric_sensors: List[AtmosphericSensor]
    surface_sensors: List[SurfaceSensor]
    severe: bool = False
    condition: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WeatherSensorSite":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            id=d["id"],
            latitude=d["latitude"],
            longitude=d["longitude"],
            location=d["location"],
            description=d["description"],
            average_air_temperature=d["averageAirTemperature"],
            atmospheric_sensors=[
                AtmosphericSensor.from_dict(s) for s in d.get("atmosphericSensors", [])
            ],
            surface_sensors=[
                SurfaceSensor.from_dict(s) for s in d.get("surfaceSensors", [])
            ],
            severe=bool(d.get("severe", False)),
            condition=d.get("condition"),
        )


# ---------------------------------------------------------------------------
# API result envelope
# ---------------------------------------------------------------------------


@dataclass
class ApiResult:
    """Wrapper returned by every list endpoint.

    ``results`` is a list of the typed resource objects.
    ``total_result_count`` reflects the full dataset size (before paging).
    ``current_result_count`` reflects how many records are in this page.
    ``total_page_count`` is the number of pages available at the requested
    page size (default 500).
    ``accepted_filters`` / ``rejected_filters`` echo the query parameters
    that were applied or rejected by the server.
    ``last_updated`` is an ISO-8601 datetime string.
    """

    links: List[Link]
    last_updated: str
    total_page_count: int
    total_result_count: int
    current_result_count: int
    results: list
    accepted_filters: List[QueryParam] = field(default_factory=list)
    rejected_filters: List[QueryParam] = field(default_factory=list)


@dataclass
class ErrorResult:
    """Error payload returned by the API on non-2xx responses."""

    links: List[Link]
    error_description: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ErrorResult":
        return cls(
            links=[Link.from_dict(lk) for lk in d.get("links", [])],
            error_description=d.get("errorDescription", "Unknown error"),
        )


# ---------------------------------------------------------------------------
# WZDx Work Zones (GeoJSON, spec v4.2)
# ---------------------------------------------------------------------------


@dataclass
class WZDxDataSource:
    """Feed data source metadata."""

    data_source_id: Optional[str] = None
    organization_name: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WZDxDataSource":
        return cls(
            data_source_id=d.get("dataSourceId"),
            organization_name=d.get("organizationName"),
        )


@dataclass
class WZDxFeedInfo:
    """Metadata header for a WZDx GeoJSON feed."""

    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    data_sources: List[WZDxDataSource] = field(default_factory=list)
    license: Optional[str] = None
    publisher: Optional[str] = None
    update_frequency: Optional[int] = None  # seconds
    version: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WZDxFeedInfo":
        return cls(
            contact_name=d.get("contactName"),
            contact_email=d.get("contactEmail"),
            data_sources=[
                WZDxDataSource.from_dict(s) for s in (d.get("dataSources") or [])
            ],
            license=d.get("license"),
            publisher=d.get("publisher"),
            update_frequency=d.get("updateFrequency"),
            version=d.get("version"),
        )


@dataclass
class WZDxCoreDetails:
    """Core attributes shared by all WZDx road event types."""

    data_source_id: str
    description: str
    direction: str
    event_type: str
    name: str
    road_names: List[str]
    update_date: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WZDxCoreDetails":
        return cls(
            data_source_id=d["dataSourceId"],
            description=d["description"],
            direction=d["direction"],
            event_type=d["eventType"],
            name=d["name"],
            road_names=d.get("roadNames", []),
            update_date=d["updateDate"],
        )


@dataclass
class WZDxProperties:
    """Properties block of a WZDx GeoJSON Feature (v4.2)."""

    core_details: WZDxCoreDetails
    start_date: str
    end_date: str
    location_method: str
    vehicle_impact: str
    is_start_date_verified: bool
    is_end_date_verified: bool
    is_start_position_verified: bool
    is_end_position_verified: bool
    beginning_accuracy: str
    ending_accuracy: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WZDxProperties":
        return cls(
            core_details=WZDxCoreDetails.from_dict(d["coreDetails"]),
            start_date=d["startDate"],
            end_date=d["endDate"],
            location_method=d["locationMethod"],
            vehicle_impact=d["vehicleImpact"],
            is_start_date_verified=d["isStartDateVerified"],
            is_end_date_verified=d["isEndDateVerified"],
            is_start_position_verified=d["isStartPositionVerified"],
            is_end_position_verified=d["isEndPositionVerified"],
            beginning_accuracy=d["beginningAccuracy"],
            ending_accuracy=d["endingAccuracy"],
        )


@dataclass
class WZDxGeometry:
    """GeoJSON geometry (LineString or MultiPoint) for a road event."""

    type: str                        # "LineString" or "MultiPoint"
    coordinates: List[List[float]]   # [[lon, lat], ...]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WZDxGeometry":
        return cls(type=d["type"], coordinates=d["coordinates"])


@dataclass
class WZDxFeature:
    """A GeoJSON Feature representing a single WZDx road event."""

    id: str
    type: str  # always "Feature"
    properties: WZDxProperties
    geometry: WZDxGeometry

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WZDxFeature":
        return cls(
            id=d["id"],
            type=d["type"],
            properties=WZDxProperties.from_dict(d["properties"]),
            geometry=WZDxGeometry.from_dict(d["geometry"]),
        )


@dataclass
class WorkZoneFeed:
    """The complete WZDx v4.2 GeoJSON FeatureCollection.

    Returned by ``GET /api/work-zones/wzdx/4.2``.  This feed is large
    (typically hundreds of features) and is not paged.
    """

    type: str
    feed_info: WZDxFeedInfo
    features: List[WZDxFeature]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkZoneFeed":
        return cls(
            type=d["type"],
            feed_info=WZDxFeedInfo.from_dict(d["feedInfo"]),
            features=[WZDxFeature.from_dict(f) for f in d.get("features", [])],
        )


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


class OHGOAPIError(Exception):
    """Raised when the OHGO API returns a non-success response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


def _build_url(path: str, params: Dict[str, Any]) -> str:
    """Construct a full URL with query string, dropping ``None`` values."""
    filtered = {k: str(v) for k, v in params.items() if v is not None}
    if filtered:
        return f"{path}?{urllib.parse.urlencode(filtered)}"
    return path


def _request(
    url: str,
    headers: Dict[str, str],
    timeout: int = 30,
) -> Dict[str, Any]:
    """Perform a GET request and return parsed JSON.

    Raises:
        OHGOAPIError: on HTTP 4xx / 5xx responses.
        urllib.error.URLError: on network-level failures.
    """
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            err = json.loads(body)
            msg = err.get("errorDescription", body.decode("utf-8", errors="replace"))
        except Exception:
            msg = body.decode("utf-8", errors="replace")
        raise OHGOAPIError(exc.code, msg) from exc


# ---------------------------------------------------------------------------
# Result parsers
# ---------------------------------------------------------------------------


def _parse_result(raw: Dict[str, Any], item_cls: type) -> ApiResult:
    """Deserialise a standard paginated API result envelope."""
    return ApiResult(
        links=[Link.from_dict(lk) for lk in raw.get("links", [])],
        last_updated=raw.get("lastUpdated", ""),
        total_page_count=raw.get("totalPageCount", 0),
        total_result_count=raw.get("totalResultCount", 0),
        current_result_count=raw.get("currentResultCount", 0),
        results=[item_cls.from_dict(item) for item in raw.get("results", [])],
        accepted_filters=[
            QueryParam.from_dict(p) for p in (raw.get("accecptedFilters") or [])
        ],
        rejected_filters=[
            QueryParam.from_dict(p) for p in (raw.get("rejectedFilters") or [])
        ],
    )


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class OHGOClient:
    """Client for the OHGO / ODOT Public Traffic REST API.

    Obtain a free API key by registering at:
        https://publicapi.ohgo.com/accounts/registration

    The key can also be provided via the environment variable
    ``OHGO_API_KEY`` as a convenience for scripts and containers.

    Args:
        api_key: Your OHGO API key.  If omitted the ``OHGO_API_KEY``
            environment variable is used.
        timeout: HTTP request timeout in seconds (default 30).
        base_url: Override the API base URL (useful for testing).

    Example::

        client = OHGOClient(api_key="abc123")
        cameras = client.get_cameras(region="columbus", page_size=10)
        for cam in cameras.results:
            print(cam.location)
            for view in cam.camera_views:
                print("  ", view.direction, view.large_url)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 30,
        base_url: str = BASE_URL,
    ) -> None:
        key = api_key or os.environ.get("OHGO_API_KEY", "")
        if not key:
            raise ValueError(
                "An OHGO API key is required.  Pass api_key= or set the "
                "OHGO_API_KEY environment variable.  Register at "
                "https://publicapi.ohgo.com/accounts/registration"
            )
        self._headers = {
            "Authorization": f"APIKEY {key}",
            "Accept": "application/json",
        }
        self._timeout = timeout
        self._v1 = f"{base_url}/api/v1"
        self._base = base_url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GET request and return parsed JSON."""
        url = _build_url(path, params or {})
        return _request(url, self._headers, self._timeout)

    def _common_params(
        self,
        region: Optional[str],
        radius: Optional[str],
        map_bounds_sw: Optional[str],
        map_bounds_ne: Optional[str],
        page_size: Optional[int],
        page: Optional[int],
        page_all: Optional[bool],
    ) -> Dict[str, Any]:
        """Build the shared filter parameters accepted by every endpoint."""
        params: Dict[str, Any] = {}
        if region:
            params["region"] = region
        if radius:
            params["radius"] = radius
        if map_bounds_sw:
            params["map-bounds-sw"] = map_bounds_sw
        if map_bounds_ne:
            params["map-bounds-ne"] = map_bounds_ne
        if page_size is not None:
            params["page-size"] = page_size
        if page is not None:
            params["page"] = page
        if page_all:
            params["page-all"] = "true"
        return params

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_cameras(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
    ) -> ApiResult:
        """Return a paginated list of ODOT traffic cameras.

        ``camera_views`` on each camera contain the live JPEG image URLs
        (updated every 5 seconds by the CDN).

        Args:
            region: Comma-separated region names.  Valid values:
                ``akron``, ``central-ohio``, ``cincinnati``, ``cleveland``,
                ``columbus``, ``dayton``, ``ne-ohio``, ``nw-ohio``,
                ``se-ohio``, ``sw-ohio``, ``toledo``.
            radius: ``"lat,lon,miles"`` — returns cameras within that
                radius of the given point.
            map_bounds_sw: South-west corner of a bounding box as
                ``"lat,lon"`` (must be paired with ``map_bounds_ne``).
            map_bounds_ne: North-east corner of a bounding box as
                ``"lat,lon"`` (must be paired with ``map_bounds_sw``).
            page_size: Maximum records per page (default 500).
            page: Zero-based page index.
            page_all: When ``True``, ignore paging and return all results.

        Returns:
            :class:`ApiResult` with ``results`` typed as :class:`Camera`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        raw = self._get(f"{self._v1}/cameras", params)
        return _parse_result(raw, Camera)

    def get_camera(self, camera_id: str) -> ApiResult:
        """Return a single camera (or multiple if IDs are comma-separated).

        Args:
            camera_id: A single camera ID or a comma-separated list of IDs.

        Returns:
            :class:`ApiResult` with ``results`` typed as :class:`Camera`.
        """
        raw = self._get(f"{self._v1}/cameras/{camera_id}")
        return _parse_result(raw, Camera)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def get_construction(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
        include_future: Optional[str] = None,
        future_only: Optional[str] = None,
    ) -> ApiResult:
        """Return active (and optionally future) construction events.

        By default only current construction is returned.  Use
        ``include_future`` or ``future_only`` to extend the date window.

        Args:
            region: Comma-separated region filter.
            radius: ``"lat,lon,miles"`` bounding radius.
            map_bounds_sw: South-west bounding box corner ``"lat,lon"``.
            map_bounds_ne: North-east bounding box corner ``"lat,lon"``.
            page_size: Maximum records per page.
            page: Zero-based page index.
            page_all: Return all results ignoring pagination.
            include_future: Include current + future construction up to
                this date (``"yyyy-MM-dd"``).
            future_only: Return only future construction up to this date
                (``"yyyy-MM-dd"``); excludes today's active events.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`Construction`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        if include_future:
            params["include-future"] = include_future
        if future_only:
            params["future-only"] = future_only
        raw = self._get(f"{self._v1}/construction", params)
        return _parse_result(raw, Construction)

    def get_construction_by_id(self, construction_id: str) -> ApiResult:
        """Return a specific construction record by ID.

        Args:
            construction_id: Single ID or comma-separated list.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`Construction`.
        """
        raw = self._get(f"{self._v1}/construction/{construction_id}")
        return _parse_result(raw, Construction)

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------

    def get_incidents(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
    ) -> ApiResult:
        """Return active traffic incidents.

        Incidents include accidents, weather events, hazards, and any
        other occurrence that impacts traffic flow.

        Returns:
            :class:`ApiResult` with ``results`` typed as :class:`Incident`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        raw = self._get(f"{self._v1}/incidents", params)
        return _parse_result(raw, Incident)

    def get_incident(self, incident_id: str) -> ApiResult:
        """Return a specific incident by ID.

        Returns:
            :class:`ApiResult` with ``results`` typed as :class:`Incident`.
        """
        raw = self._get(f"{self._v1}/incidents/{incident_id}")
        return _parse_result(raw, Incident)

    # ------------------------------------------------------------------
    # Dangerous Slowdowns
    # ------------------------------------------------------------------

    def get_dangerous_slowdowns(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
    ) -> ApiResult:
        """Return current dangerous slowdown alerts.

        A dangerous slowdown is flagged when the measured speed drops
        significantly below the historical normal speed at that location.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`DangerousSlowdown`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        raw = self._get(f"{self._v1}/dangerous-slowdowns", params)
        return _parse_result(raw, DangerousSlowdown)

    def get_dangerous_slowdown(self, slowdown_id: str) -> ApiResult:
        """Return a specific dangerous slowdown by ID.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`DangerousSlowdown`.
        """
        raw = self._get(f"{self._v1}/dangerous-slowdowns/{slowdown_id}")
        return _parse_result(raw, DangerousSlowdown)

    # ------------------------------------------------------------------
    # Digital Signs
    # ------------------------------------------------------------------

    def get_digital_signs(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
        sign_type: Optional[str] = None,
    ) -> ApiResult:
        """Return dynamic message signs and their current messages.

        Args:
            sign_type: Comma-separated sign types to filter.  Valid values
                (aliases accepted): ``dms`` / ``message-board``,
                ``ddms`` / ``travel-time``,
                ``sign-queue`` / ``slow-traffic``,
                ``vsl`` / ``variable-speed-limit``,
                ``tp`` / ``truck-parking``.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`DigitalSign`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        if sign_type:
            params["sign-type"] = sign_type
        raw = self._get(f"{self._v1}/digital-signs", params)
        return _parse_result(raw, DigitalSign)

    def get_digital_sign(self, sign_id: str) -> ApiResult:
        """Return a specific digital sign by ID.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`DigitalSign`.
        """
        raw = self._get(f"{self._v1}/digital-signs/{sign_id}")
        return _parse_result(raw, DigitalSign)

    # ------------------------------------------------------------------
    # Travel Delays
    # ------------------------------------------------------------------

    def get_travel_delays(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
    ) -> ApiResult:
        """Return travel time and delay data for monitored road segments.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`TravelDelay`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        raw = self._get(f"{self._v1}/travel-delays", params)
        return _parse_result(raw, TravelDelay)

    def get_travel_delay(self, delay_id: str) -> ApiResult:
        """Return a specific travel delay record by ID.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`TravelDelay`.
        """
        raw = self._get(f"{self._v1}/travel-delays/{delay_id}")
        return _parse_result(raw, TravelDelay)

    # ------------------------------------------------------------------
    # Truck Parking
    # ------------------------------------------------------------------

    def get_truck_parking(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
    ) -> ApiResult:
        """Return commercial vehicle parking locations and occupancy.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`TruckParking`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        raw = self._get(f"{self._v1}/truck-parking", params)
        return _parse_result(raw, TruckParking)

    def get_truck_parking_by_id(self, parking_id: str) -> ApiResult:
        """Return a specific truck parking location by ID.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`TruckParking`.
        """
        raw = self._get(f"{self._v1}/truck-parking/{parking_id}")
        return _parse_result(raw, TruckParking)

    # ------------------------------------------------------------------
    # Weather Sensor Sites
    # ------------------------------------------------------------------

    def get_weather_sensor_sites(
        self,
        region: Optional[str] = None,
        radius: Optional[str] = None,
        map_bounds_sw: Optional[str] = None,
        map_bounds_ne: Optional[str] = None,
        page_size: Optional[int] = None,
        page: Optional[int] = None,
        page_all: Optional[bool] = None,
        hazards_only: Optional[bool] = None,
    ) -> ApiResult:
        """Return roadside weather information system (RWIS) stations.

        Args:
            hazards_only: When ``True``, return only sites that are
                currently reporting hazardous conditions (rain, snow, ice,
                high wind, low visibility).

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`WeatherSensorSite`.
        """
        params = self._common_params(
            region, radius, map_bounds_sw, map_bounds_ne, page_size, page, page_all
        )
        if hazards_only:
            params["hazards-only"] = "true"
        raw = self._get(f"{self._v1}/weather-sensor-sites", params)
        return _parse_result(raw, WeatherSensorSite)

    def get_weather_sensor_site(self, site_id: str) -> ApiResult:
        """Return a specific weather sensor site by ID.

        Returns:
            :class:`ApiResult` with ``results`` typed as
            :class:`WeatherSensorSite`.
        """
        raw = self._get(f"{self._v1}/weather-sensor-sites/{site_id}")
        return _parse_result(raw, WeatherSensorSite)

    # ------------------------------------------------------------------
    # Work Zones (WZDx 4.2)
    # ------------------------------------------------------------------

    def get_work_zones(self) -> WorkZoneFeed:
        """Return the full WZDx v4.2 GeoJSON work zone feed.

        This endpoint returns the complete active work zone dataset for
        Ohio as a GeoJSON FeatureCollection conforming to the Work Zone
        Data Exchange (WZDx) specification version 4.2.  The response
        can be large (hundreds of features) and is not paginated.

        Returns:
            :class:`WorkZoneFeed` containing ``features`` (GeoJSON) and
            ``feed_info`` metadata.
        """
        raw = self._get(f"{self._base}/api/work-zones/wzdx/4.2")
        return WorkZoneFeed.from_dict(raw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_table(rows: list, headers: List[str], widths: List[int]) -> None:
    """Print a simple fixed-width table to stdout."""
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "  ".join("-" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        cells = [str(c)[:w] for c, w in zip(row, widths)]
        print(fmt.format(*cells))


def _cmd_cameras(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_cameras(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
    )
    print(f"Cameras  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for cam in result.results:
        views = cam.camera_views
        url = views[0].small_url if views else ""
        rows.append((cam.id, cam.location[:40], len(views), url[:55]))
    _print_table(rows, ["ID", "Location", "Views", "First image URL"], [20, 42, 6, 57])


def _cmd_incidents(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_incidents(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
    )
    print(f"Incidents  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for inc in result.results:
        rows.append((
            inc.id[:18],
            inc.category[:18],
            inc.road_status[:12],
            inc.route_name[:12],
            inc.location[:40],
        ))
    _print_table(
        rows,
        ["ID", "Category", "Road Status", "Route", "Location"],
        [20, 20, 14, 14, 42],
    )


def _cmd_construction(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_construction(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
        include_future=args.include_future,
        future_only=args.future_only,
    )
    print(f"Construction  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for c in result.results:
        rows.append((
            c.id[:18],
            c.status[:10],
            c.category[:10],
            c.route_name[:12],
            c.location[:40],
        ))
    _print_table(
        rows,
        ["ID", "Status", "Category", "Route", "Location"],
        [20, 12, 12, 14, 42],
    )


def _cmd_weather(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_weather_sensor_sites(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
        hazards_only=args.hazards_only,
    )
    print(f"Weather Sensor Sites  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for site in result.results:
        rows.append((
            site.id[:18],
            site.average_air_temperature[:6],
            "YES" if site.severe else "",
            (site.condition or "")[:14],
            site.location[:44],
        ))
    _print_table(
        rows,
        ["ID", "Temp°F", "Hazard", "Condition", "Location"],
        [20, 8, 7, 16, 46],
    )


def _cmd_slowdowns(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_dangerous_slowdowns(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
    )
    print(f"Dangerous Slowdowns  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for s in result.results:
        rows.append((
            s.id[:18],
            s.route_name[:12],
            s.direction[:6],
            s.normal_mph,
            s.current_mph,
            s.location[:40],
        ))
    _print_table(
        rows,
        ["ID", "Route", "Dir", "Normal", "Current", "Location"],
        [20, 14, 8, 7, 8, 42],
    )


def _cmd_signs(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_digital_signs(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
        sign_type=args.sign_type,
    )
    print(f"Digital Signs  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for sign in result.results:
        msgs = " | ".join(sign.messages)
        rows.append((
            sign.id[:18],
            sign.sign_type_name[:20],
            sign.location[:30],
            msgs[:48],
        ))
    _print_table(
        rows,
        ["ID", "Type", "Location", "Messages"],
        [20, 22, 32, 50],
    )


def _cmd_delays(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_travel_delays(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
    )
    print(f"Travel Delays  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for d in result.results:
        rows.append((
            d.id[:18],
            d.route_name[:12],
            d.direction[:6],
            f"{d.current_avg_speed:.0f}",
            f"{d.normal_avg_speed:.0f}",
            f"{d.delay_time:.1f}",
            d.location[:38],
        ))
    _print_table(
        rows,
        ["ID", "Route", "Dir", "Cur mph", "Nor mph", "Delay m", "Location"],
        [20, 14, 8, 8, 8, 8, 40],
    )


def _cmd_parking(client: OHGOClient, args: argparse.Namespace) -> None:
    result = client.get_truck_parking(
        region=args.region,
        radius=args.radius,
        page_size=args.page_size,
        page=args.page,
        page_all=args.page_all,
    )
    print(f"Truck Parking  |  total={result.total_result_count}  "
          f"page={result.current_result_count}  "
          f"updated={result.last_updated}")
    print()
    rows = []
    for p in result.results:
        rows.append((
            p.id[:18],
            "OPEN" if p.open else "CLOSED",
            (p.capacity or "?")[:6],
            (p.reported_available or "?")[:6],
            (p.location or "")[:40],
        ))
    _print_table(
        rows,
        ["ID", "Status", "Cap", "Avail", "Location"],
        [20, 8, 8, 8, 42],
    )


def _cmd_workzones(client: OHGOClient, _args: argparse.Namespace) -> None:
    feed = client.get_work_zones()
    fi = feed.feed_info
    print(f"Work Zones (WZDx {fi.version})  |  features={len(feed.features)}  "
          f"publisher={fi.publisher}  update_freq={fi.update_frequency}s")
    print()
    rows = []
    for feat in feed.features[:50]:  # cap display at 50
        cd = feat.properties.core_details
        rows.append((
            feat.id[:18],
            cd.event_type[:16],
            cd.direction[:6],
            feat.properties.start_date[:19],
            ", ".join(cd.road_names)[:30],
        ))
    _print_table(
        rows,
        ["ID", "Event Type", "Dir", "Start Date", "Roads"],
        [20, 18, 8, 21, 32],
    )
    if len(feed.features) > 50:
        print(f"  ... and {len(feed.features) - 50} more features")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ohgo_client",
        description="OHGO / ODOT Traffic API command-line client.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List cameras in Cleveland:
  python ohgo_client.py --api-key KEY cameras --region cleveland

  # Incidents across all of NE Ohio:
  python ohgo_client.py --api-key KEY incidents --region ne-ohio --page-all

  # Active construction statewide (first 20):
  python ohgo_client.py --api-key KEY construction --page-size 20

  # Construction including future events through end of April:
  python ohgo_client.py --api-key KEY construction --include-future 2026-04-30

  # Weather sites with hazardous conditions only:
  python ohgo_client.py --api-key KEY weather --hazards-only

  # Cameras within 5 miles of downtown Columbus (39.96, -82.99):
  python ohgo_client.py --api-key KEY cameras --radius 39.9612,-82.9988,5

  # Travel-time digital signs in Columbus:
  python ohgo_client.py --api-key KEY signs --region columbus --sign-type travel-time

  # All work zones (WZDx 4.2 GeoJSON feed):
  python ohgo_client.py --api-key KEY work-zones

  # API key from environment variable:
  export OHGO_API_KEY=your_key_here
  python ohgo_client.py cameras --region toledo
""",
    )

    parser.add_argument(
        "--api-key",
        metavar="KEY",
        default=None,
        help="OHGO API key (or set OHGO_API_KEY env var).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        metavar="SECS",
        help="HTTP timeout in seconds (default: 30).",
    )

    sub = parser.add_subparsers(dest="command", required=True, title="commands")

    # Shared filter arguments
    def _add_filters(p: argparse.ArgumentParser, *, construction: bool = False) -> None:
        p.add_argument("--region", metavar="REGION",
                       help=f"Comma-separated regions: {', '.join(VALID_REGIONS)}")
        p.add_argument("--radius", metavar="LAT,LON,MILES",
                       help='Search radius, e.g. "39.96,-82.99,5"')
        p.add_argument("--page-size", type=int, metavar="N",
                       help="Max records per page (default 500).")
        p.add_argument("--page", type=int, metavar="N",
                       help="Zero-based page index.")
        p.add_argument("--page-all", action="store_true",
                       help="Return all results ignoring pagination.")
        if construction:
            p.add_argument("--include-future", metavar="YYYY-MM-DD",
                           help="Include future construction up to this date.")
            p.add_argument("--future-only", metavar="YYYY-MM-DD",
                           help="Return only future construction up to this date.")

    # cameras
    p_cam = sub.add_parser("cameras", help="List traffic cameras.")
    _add_filters(p_cam)
    p_cam.set_defaults(func=_cmd_cameras)

    # incidents
    p_inc = sub.add_parser("incidents", help="List traffic incidents.")
    _add_filters(p_inc)
    p_inc.set_defaults(func=_cmd_incidents)

    # construction
    p_con = sub.add_parser("construction", help="List construction zones.")
    _add_filters(p_con, construction=True)
    p_con.set_defaults(func=_cmd_construction)

    # weather
    p_wx = sub.add_parser("weather", help="List weather sensor sites (RWIS).")
    _add_filters(p_wx)
    p_wx.add_argument("--hazards-only", action="store_true",
                      help="Return only sites with active hazardous conditions.")
    p_wx.set_defaults(func=_cmd_weather)

    # slowdowns
    p_sl = sub.add_parser("slowdowns", help="List dangerous slowdowns.")
    _add_filters(p_sl)
    p_sl.set_defaults(func=_cmd_slowdowns)

    # signs
    p_sg = sub.add_parser("signs", help="List digital message signs.")
    _add_filters(p_sg)
    p_sg.add_argument(
        "--sign-type",
        metavar="TYPE",
        help=(
            "Comma-separated sign types to filter: "
            "dms/message-board, ddms/travel-time, "
            "sign-queue/slow-traffic, vsl/variable-speed-limit, "
            "tp/truck-parking."
        ),
    )
    p_sg.set_defaults(func=_cmd_signs)

    # delays
    p_dl = sub.add_parser("delays", help="List travel delays.")
    _add_filters(p_dl)
    p_dl.set_defaults(func=_cmd_delays)

    # parking
    p_pk = sub.add_parser("parking", help="List truck parking locations.")
    _add_filters(p_pk)
    p_pk.set_defaults(func=_cmd_parking)

    # work-zones
    p_wz = sub.add_parser("work-zones", help="Fetch WZDx 4.2 work zone GeoJSON feed.")
    p_wz.set_defaults(func=_cmd_workzones)

    return parser


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        client = OHGOClient(api_key=args.api_key, timeout=args.timeout)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        args.func(client, args)
    except OHGOAPIError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
