#!/usr/bin/env python3
"""
MassDOT / Mass511 Traffic API Client
=====================================
A production-quality Python client for the Massachusetts Department of
Transportation (MassDOT) traffic information system, available at
https://www.mass511.com.

The system is built on CastleRock Associates' CARS platform and exposes a
GraphQL API at https://www.mass511.com/api/graphql.  No API key or
authentication is required for read-only access to public traffic data.

Key capabilities
----------------
* List traffic cameras with live JPEG snapshot URLs
* Fetch map features (events, cameras, signs) by bounding box
* Look up individual event / camera / rest-area details
* Search all items along a named route (e.g. "I-90", "US-6")
* List electronic (VMS/DMS) signs and bridge-height signs
* Retrieve service notifications / banners

Usage (CLI)
-----------
    python massdot_client.py cameras --bbox "42.2,42.5,-71.5,-70.9"
    python massdot_client.py events --layer roadReports
    python massdot_client.py route I-90
    python massdot_client.py camera 10257
    python massdot_client.py event MA-2426211456467036
    python massdot_client.py signs --bbox "42.2,42.5,-71.5,-70.9"
    python massdot_client.py notifications

Author: reverse-engineered from mass511.com JavaScript bundle (v3.19.14)
Date: 2026-03-27
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPHQL_ENDPOINT = "https://www.mass511.com/api/graphql"
CAMERA_IMAGE_BASE = "https://public.carsprogram.org/cameras/MA/"

# All known layer slugs (extracted from the app JS bundle).
# Pass one or more of these to map-feature queries.
LAYER_SLUGS = {
    # --- Incidents / events ---
    "roadReports":              "Road Reports (crashes, closures, etc.)",
    "constructionReports":      "Construction / Roadwork",
    "towingProhibitedReports":  "Towing Prohibited Reports",
    "truckersReports":          "Truckers Reports",
    "weatherWarningsAreaEvents": "Weather Warning Areas",
    "winterDriving":            "Winter Driving Conditions",
    "future":                   "Future / Scheduled Construction",
    "wazeReports":              "Waze Crowd-Sourced Reports",
    # --- Cameras ---
    "normalCameras":            "Standard Roadside Cameras",
    "hotCameras":               "Hot / Featured Cameras",
    "plowCameras":              "Snow Plow Cameras",
    # --- Signs ---
    "electronicSigns":          "Electronic Signs (VMS / DMS)",
    "electronicSignsInactive":  "Inactive Electronic Signs",
    "postedWeightSigns":        "Posted Weight Signs",
    "bridgeHeights":            "Bridge Height Signs",
    # --- Traffic / conditions ---
    "trafficSpeeds":            "Traffic Speed Conditions",
    "roadConditions":           "Road Surface Conditions",
    "regionalRoadConditions":   "Regional Road Conditions",
    # --- Infrastructure ---
    "restAreas":                "Rest Areas",
    "mileMarkers":              "Mile Markers",
    "weighStations":            "Weigh Stations",
    "ferryReports":             "Ferry Service Reports",
    # --- Vehicles ---
    "potholeTruckLocations":    "Pothole Truck Locations",
    "fuelingStations":          "EV / Fueling Stations",
    # --- Restrictions ---
    "heightRestrictions":       "Height Restrictions",
    "widthRestrictions":        "Width Restrictions",
    "weightRestrictions":       "Weight Restrictions",
    "lengthRestrictions":       "Length Restrictions",
    "speedRestrictions":        "Speed Restrictions",
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 15  # seconds

# ---------------------------------------------------------------------------
# Dataclasses – public API types
# ---------------------------------------------------------------------------

@dataclass
class BoundingBox:
    """Geographic bounding box (WGS-84)."""
    south: float
    north: float
    west: float
    east: float

    @classmethod
    def from_list(cls, coords: List[float]) -> "BoundingBox":
        """Build from a 4-element list [west, south, east, north]."""
        return cls(south=coords[1], north=coords[3], west=coords[0], east=coords[2])

    @classmethod
    def from_ma_statewide(cls) -> "BoundingBox":
        """Return a bounding box that covers all of Massachusetts."""
        return cls(south=41.2, north=42.9, west=-73.5, east=-69.8)

    @classmethod
    def parse(cls, s: str) -> "BoundingBox":
        """Parse a comma-separated string 'south,north,west,east'."""
        parts = [float(p.strip()) for p in s.split(",")]
        if len(parts) != 4:
            raise ValueError("BoundingBox string must be 'south,north,west,east'")
        return cls(south=parts[0], north=parts[1], west=parts[2], east=parts[3])


@dataclass
class Timestamp:
    """A UTC timestamp plus a named timezone string."""
    timestamp_ms: int
    timezone: str

    @property
    def datetime_utc(self) -> datetime:
        """Return a timezone-aware UTC datetime."""
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)

    def isoformat(self) -> str:
        return self.datetime_utc.isoformat()


@dataclass
class CameraView:
    """A single image / video source for a traffic camera."""
    uri: str
    url: str                   # Live JPEG snapshot URL
    category: str              # Usually "VIDEO" (JPEG snapshots) or "IMAGE"
    title: Optional[str] = None

    @property
    def image_url(self) -> str:
        """Direct URL to the live camera JPEG snapshot."""
        return self.url


@dataclass
class Camera:
    """A MassDOT roadside traffic camera."""
    uri: str                   # e.g. "camera/10257"
    camera_id: str             # Numeric ID portion of uri
    title: str
    bbox: BoundingBox
    active: bool
    icon: Optional[str] = None
    color: Optional[str] = None
    agency_name: Optional[str] = None
    last_updated: Optional[Timestamp] = None
    primary_linear_ref: Optional[float] = None
    secondary_linear_ref: Optional[float] = None
    views: List[CameraView] = field(default_factory=list)

    @property
    def latitude(self) -> float:
        return (self.bbox.south + self.bbox.north) / 2

    @property
    def longitude(self) -> float:
        return (self.bbox.west + self.bbox.east) / 2

    @property
    def snapshot_url(self) -> Optional[str]:
        """URL of the first available live camera snapshot."""
        return self.views[0].url if self.views else None


@dataclass
class Event:
    """A traffic event (crash, roadwork, closure, weather warning, etc.)."""
    uri: str                   # e.g. "event/MA-2426211456467036"
    event_id: str
    title: str
    bbox: BoundingBox
    priority: Optional[int] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_waze_event: Optional[bool] = None
    last_updated: Optional[Timestamp] = None
    begin_time: Optional[Timestamp] = None
    primary_linear_ref: Optional[float] = None
    agency_name: Optional[str] = None
    agency_url: Optional[str] = None

    @property
    def latitude(self) -> float:
        return (self.bbox.south + self.bbox.north) / 2

    @property
    def longitude(self) -> float:
        return (self.bbox.west + self.bbox.east) / 2


@dataclass
class Sign:
    """An electronic or height-restriction road sign."""
    uri: str
    title: str
    tooltip: Optional[str]
    bbox: BoundingBox
    sign_display_type: Optional[str] = None  # "BRIDGE_HEIGHT", "OVERLAY_TPIM", etc.

    @property
    def latitude(self) -> float:
        return (self.bbox.south + self.bbox.north) / 2

    @property
    def longitude(self) -> float:
        return (self.bbox.west + self.bbox.east) / 2


@dataclass
class RestArea:
    """A Massachusetts highway rest area or service plaza."""
    uri: str
    title: str
    bbox: BoundingBox
    status: Optional[str] = None
    description: Optional[str] = None
    is_private: Optional[bool] = None

    @property
    def latitude(self) -> float:
        return (self.bbox.south + self.bbox.north) / 2

    @property
    def longitude(self) -> float:
        return (self.bbox.west + self.bbox.east) / 2


@dataclass
class MapFeature:
    """Generic map feature returned from mapFeaturesQuery before type-specific parsing."""
    uri: str
    title: str
    tooltip: Optional[str]
    bbox: BoundingBox
    typename: str             # GraphQL __typename: "Camera", "Event", "Sign", etc.
    priority: Optional[int] = None
    active: Optional[bool] = None
    sign_display_type: Optional[str] = None
    views: List[CameraView] = field(default_factory=list)


@dataclass
class Notification:
    """A system-wide notification or banner displayed in the app."""
    uri: str
    title: str
    description: Optional[str]
    icon: Optional[str]
    type: Optional[str]
    last_updated: Optional[Timestamp] = None
    audio_url: Optional[str] = None


@dataclass
class RouteSearchResult:
    """Results from searching along a named route."""
    route_id: str
    geometry_encoded: Optional[str]   # Google encoded polyline
    events: List[Event] = field(default_factory=list)
    camera_views: List[CameraView] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Low-level GraphQL helpers
# ---------------------------------------------------------------------------

def _graphql_request(
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    Execute a GraphQL request against the Mass511 public endpoint.

    Parameters
    ----------
    query:
        GraphQL query string.
    variables:
        Optional variable bindings.
    timeout:
        Request timeout in seconds.

    Returns
    -------
    The ``data`` portion of the GraphQL response as a dict.

    Raises
    ------
    RuntimeError
        If the HTTP request fails or the server returns ``errors``.
    """
    payload: Dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        GRAPHQL_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from GraphQL endpoint: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc

    result = json.loads(raw)

    if "errors" in result and "data" not in result:
        msgs = "; ".join(e.get("message", "unknown") for e in result["errors"])
        raise RuntimeError(f"GraphQL errors: {msgs}")

    # Some queries return partial errors alongside data – surface them as warnings
    # but still return the data.
    return result.get("data", {})


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_bbox(raw: Optional[List[float]]) -> BoundingBox:
    if not raw or len(raw) < 4:
        return BoundingBox(0.0, 0.0, 0.0, 0.0)
    return BoundingBox(south=raw[1], north=raw[3], west=raw[0], east=raw[2])


def _parse_timestamp(raw: Optional[Dict]) -> Optional[Timestamp]:
    if not raw:
        return None
    return Timestamp(timestamp_ms=raw["timestamp"], timezone=raw["timezone"])


def _parse_camera_views(raw_views: Optional[List[Dict]], title: str = "") -> List[CameraView]:
    if not raw_views:
        return []
    views = []
    for v in raw_views:
        url = v.get("url", "")
        if url:
            views.append(CameraView(
                uri=v.get("uri", ""),
                url=url,
                category=v.get("category", "VIDEO"),
                title=title,
            ))
    return views


def _parse_camera_from_query(raw: Dict) -> Camera:
    cam = raw.get("camera") or {}
    uri = cam.get("uri", "")
    bbox = _parse_bbox(cam.get("bbox"))
    last_upd = _parse_timestamp(cam.get("lastUpdated"))
    loc = cam.get("location") or {}
    agency = cam.get("agencyAttribution") or {}
    views = _parse_camera_views(cam.get("views"), cam.get("title", ""))
    return Camera(
        uri=uri,
        camera_id=uri.split("/")[-1],
        title=cam.get("title", ""),
        bbox=bbox,
        active=cam.get("active", False),
        icon=cam.get("icon"),
        color=cam.get("color"),
        agency_name=agency.get("agencyName"),
        last_updated=last_upd,
        primary_linear_ref=loc.get("primaryLinearReference"),
        secondary_linear_ref=loc.get("secondaryLinearReference"),
        views=views,
    )


def _parse_event_from_query(raw: Dict) -> Event:
    ev = raw.get("event") or {}
    uri = ev.get("uri", "")
    bbox = _parse_bbox(ev.get("bbox"))
    loc = ev.get("location") or {}
    agency = ev.get("agencyAttribution") or {}
    return Event(
        uri=uri,
        event_id=uri.split("/")[-1],
        title=ev.get("title", ""),
        bbox=bbox,
        priority=ev.get("priority"),
        description=ev.get("description"),
        icon=ev.get("icon"),
        color=ev.get("color"),
        is_waze_event=ev.get("isWazeEvent"),
        last_updated=_parse_timestamp(ev.get("lastUpdated")),
        begin_time=_parse_timestamp(ev.get("beginTime")),
        primary_linear_ref=loc.get("primaryLinearReference"),
        agency_name=agency.get("agencyName"),
        agency_url=agency.get("agencyURL"),
    )


def _parse_map_feature(raw: Dict) -> MapFeature:
    typename = raw.get("__typename", "Unknown")
    views = _parse_camera_views(raw.get("views"), raw.get("title", ""))
    return MapFeature(
        uri=raw.get("uri", ""),
        title=raw.get("title", ""),
        tooltip=raw.get("tooltip"),
        bbox=_parse_bbox(raw.get("bbox")),
        typename=typename,
        priority=raw.get("priority"),
        active=raw.get("active"),
        sign_display_type=raw.get("signDisplayType"),
        views=views,
    )


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def get_map_features(
    bbox: BoundingBox,
    layer_slugs: List[str],
    zoom: int = 12,
) -> List[MapFeature]:
    """
    Fetch map features (cameras, events, signs, etc.) within a bounding box.

    This is the primary "map view" query – it returns lightweight feature
    objects suitable for display on a map.  Use the more specific ``get_camera``
    / ``get_event`` functions to retrieve full details about individual items.

    Parameters
    ----------
    bbox:
        Geographic bounding box.
    layer_slugs:
        One or more layer slug strings (see ``LAYER_SLUGS``).  Each slug is
        queried separately and results are merged.
    zoom:
        Map zoom level (1–20).  Some layers (e.g. cameras) only return data
        at zoom ≥ 10.

    Returns
    -------
    List of ``MapFeature`` objects.
    """
    query = """
    query MapFeatures($input: MapFeaturesArgs!) {
        mapFeaturesQuery(input: $input) {
            mapFeatures {
                bbox
                title
                tooltip
                uri
                __typename
                ... on Cluster { maxZoom }
                ... on Sign { signDisplayType }
                ... on Event { priority }
                ... on Camera {
                    active
                    views(limit: 5) {
                        uri
                        ... on CameraView { url }
                        category
                    }
                }
            }
            error { message type }
        }
    }
    """
    all_features: List[MapFeature] = []
    for slug in layer_slugs:
        variables = {
            "input": {
                "north": bbox.north,
                "south": bbox.south,
                "east": bbox.east,
                "west": bbox.west,
                "zoom": zoom,
                "layerSlugs": [slug],
            }
        }
        data = _graphql_request(query, variables)
        raw_features = (
            data.get("mapFeaturesQuery", {}).get("mapFeatures") or []
        )
        all_features.extend(_parse_map_feature(f) for f in raw_features)
    return all_features


def list_cameras(
    bbox: BoundingBox,
    zoom: int = 14,
    include_hot: bool = False,
) -> List[MapFeature]:
    """
    List all traffic cameras within a bounding box.

    Returns lightweight ``MapFeature`` objects that include the camera URI
    and a live snapshot URL via the ``views`` list.  Call ``get_camera`` with
    the ID to get full metadata.

    Parameters
    ----------
    bbox:
        Geographic bounding box.
    zoom:
        Map zoom level.  Cameras cluster below ~zoom 10; use ≥ 12 for
        individual camera markers.
    include_hot:
        Also include "hot" / featured cameras layer.
    """
    slugs = ["normalCameras"]
    if include_hot:
        slugs.append("hotCameras")
    return get_map_features(bbox, slugs, zoom=zoom)


def list_events(
    bbox: BoundingBox,
    layer_slugs: Optional[List[str]] = None,
    zoom: int = 8,
) -> List[MapFeature]:
    """
    List traffic events (crashes, construction, closures) within a bounding box.

    Parameters
    ----------
    bbox:
        Geographic bounding box.
    layer_slugs:
        Event layer slugs to query.  Defaults to ``["roadReports",
        "constructionReports", "truckersReports"]``.
    zoom:
        Map zoom level.
    """
    if layer_slugs is None:
        layer_slugs = ["roadReports", "constructionReports", "truckersReports"]
    return get_map_features(bbox, layer_slugs, zoom=zoom)


def list_signs(
    bbox: BoundingBox,
    zoom: int = 12,
) -> List[MapFeature]:
    """
    List electronic and bridge-height signs within a bounding box.

    Parameters
    ----------
    bbox:
        Geographic bounding box.
    zoom:
        Map zoom level.
    """
    return get_map_features(bbox, ["electronicSigns"], zoom=zoom)


def list_rest_areas(
    bbox: Optional[BoundingBox] = None,
    zoom: int = 8,
) -> List[MapFeature]:
    """
    List Massachusetts highway rest areas.

    Parameters
    ----------
    bbox:
        Optional bounding box (defaults to statewide MA).
    zoom:
        Map zoom level.
    """
    if bbox is None:
        bbox = BoundingBox.from_ma_statewide()
    return get_map_features(bbox, ["restAreas"], zoom=zoom)


def get_camera(camera_id: str) -> Camera:
    """
    Retrieve full details for a single traffic camera.

    Parameters
    ----------
    camera_id:
        Numeric camera ID (e.g. ``"10257"``) or full URI
        (e.g. ``"camera/10257"``).

    Returns
    -------
    ``Camera`` dataclass with metadata and live snapshot URLs.
    """
    cid = camera_id.split("/")[-1]  # strip "camera/" prefix if present

    query = """
    query CameraDetail($cameraId: ID!) {
        cameraQuery(cameraId: $cameraId) {
            camera {
                uri
                color
                title
                bbox
                icon
                active
                agencyAttribution { agencyName }
                lastUpdated { timestamp timezone }
                location {
                    primaryLinearReference
                    secondaryLinearReference
                }
                views(limit: 20) {
                    uri
                    category
                    ... on CameraView { url }
                }
            }
        }
    }
    """
    data = _graphql_request(query, {"cameraId": cid})
    cam_data = data.get("cameraQuery") or {}
    return _parse_camera_from_query(cam_data)


def get_event(event_id: str, layer_slugs: Optional[List[str]] = None) -> Event:
    """
    Retrieve full details for a single traffic event.

    Parameters
    ----------
    event_id:
        Event ID (e.g. ``"MA-2426211456467036"``) or full URI
        (e.g. ``"event/MA-2426211456467036"``).
    layer_slugs:
        Layer slugs to pass with the query.  Defaults to a broad set of
        event layers.

    Returns
    -------
    ``Event`` dataclass with description, priority, timestamps, and geometry.
    """
    eid = event_id.split("/")[-1]

    if layer_slugs is None:
        layer_slugs = [
            "roadReports",
            "constructionReports",
            "towingProhibitedReports",
            "truckersReports",
            "weatherWarningsAreaEvents",
            "future",
        ]

    query = """
    query EventDetail($eventId: ID!, $layerSlugs: [String!]!) {
        eventQuery(eventId: $eventId, layerSlugs: $layerSlugs) {
            event {
                uri
                title
                description
                bbox
                location { primaryLinearReference secondaryLinearReference }
                icon
                color
                lastUpdated { timestamp timezone }
                beginTime { timestamp timezone }
                isWazeEvent
                priority
                agencyAttribution { agencyName agencyURL }
            }
        }
    }
    """
    data = _graphql_request(query, {"eventId": eid, "layerSlugs": layer_slugs})
    ev_data = data.get("eventQuery") or {}
    return _parse_event_from_query(ev_data)


def search_route(
    route_id: str,
    layer_slugs: Optional[List[str]] = None,
) -> RouteSearchResult:
    """
    Retrieve all events and cameras along a named route.

    Parameters
    ----------
    route_id:
        Route identifier in the form used by Mass511 (e.g. ``"I-90"``,
        ``"US-6"``, ``"RT-128"``).  Case-sensitive.
    layer_slugs:
        Optional list of layer slugs to include.  Defaults to road reports,
        construction, and normal cameras.

    Returns
    -------
    ``RouteSearchResult`` with geometry (encoded polyline), events list,
    and camera view list.
    """
    if layer_slugs is None:
        layer_slugs = ["roadReports", "constructionReports", "normalCameras"]

    query = """
    query SearchRoute($routeId: String!, $layerSlugs: [String!]!) {
        searchRoadwayGeometryQuery(routeId: $routeId, layerSlugs: $layerSlugs) {
            geometry
            results {
                uri
                title
                __typename
            }
            cameraViews {
                uri
                url
                title
                category
            }
            error { message type }
        }
    }
    """
    data = _graphql_request(query, {"routeId": route_id, "layerSlugs": layer_slugs})
    rq = data.get("searchRoadwayGeometryQuery") or {}

    raw_results = rq.get("results") or []
    raw_views = rq.get("cameraViews") or []
    error_obj = rq.get("error")
    geometry = rq.get("geometry")
    geometry_encoded: Optional[str] = None
    if isinstance(geometry, dict):
        geometry_encoded = geometry.get("coordinates")

    events: List[Event] = []
    for r in raw_results:
        uri = r.get("uri", "")
        if uri.startswith("event/"):
            events.append(Event(
                uri=uri,
                event_id=uri.split("/")[-1],
                title=r.get("title", ""),
                bbox=BoundingBox(0, 0, 0, 0),
            ))

    camera_views: List[CameraView] = []
    for v in raw_views:
        url = v.get("url", "")
        if url:
            camera_views.append(CameraView(
                uri=v.get("uri", ""),
                url=url,
                category=v.get("category", "VIDEO"),
                title=v.get("title", ""),
            ))

    err_msg: Optional[str] = None
    if error_obj:
        err_msg = error_obj.get("message")

    return RouteSearchResult(
        route_id=route_id,
        geometry_encoded=geometry_encoded,
        events=events,
        camera_views=camera_views,
        error=err_msg,
    )


def get_notifications() -> List[Notification]:
    """
    Retrieve current system-wide notifications and banners.

    Returns
    -------
    List of ``Notification`` objects (may be empty when no alerts are active).
    """
    query = """
    query {
        notificationsQuery {
            notifications {
                uri
                title
                description
                icon
                type
                lastUpdated { timestamp timezone }
                audioURL
            }
            error { message type }
        }
    }
    """
    data = _graphql_request(query)
    raw = data.get("notificationsQuery", {}).get("notifications") or []
    return [
        Notification(
            uri=n.get("uri", ""),
            title=n.get("title", ""),
            description=n.get("description"),
            icon=n.get("icon"),
            type=n.get("type"),
            last_updated=_parse_timestamp(n.get("lastUpdated")),
            audio_url=n.get("audioURL"),
        )
        for n in raw
    ]


def search_by_bounds(
    bbox: BoundingBox,
    layer_slugs: Optional[List[str]] = None,
    zoom: int = 12,
) -> Tuple[List[MapFeature], List[CameraView]]:
    """
    Combined search: return map features AND camera view list for a bbox.

    Parameters
    ----------
    bbox:
        Geographic bounding box.
    layer_slugs:
        Layer slugs to query.  Defaults to road reports, construction, and
        cameras.
    zoom:
        Map zoom level.

    Returns
    -------
    Tuple of (list of MapFeature, list of CameraView).
    """
    if layer_slugs is None:
        layer_slugs = ["roadReports", "constructionReports", "normalCameras"]
    features = get_map_features(bbox, layer_slugs, zoom=zoom)
    camera_views = [
        view
        for feat in features
        if feat.typename == "Camera"
        for view in feat.views
    ]
    return features, camera_views


# ---------------------------------------------------------------------------
# Convenience / formatting helpers
# ---------------------------------------------------------------------------

def _truncate(s: Optional[str], maxlen: int = 100) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    return s[:maxlen] + "…" if len(s) > maxlen else s


def format_camera(cam: Camera, verbose: bool = False) -> str:
    """Return a human-readable summary of a camera."""
    lines = [
        f"Camera {cam.camera_id}: {cam.title}",
        f"  Status: {'ACTIVE' if cam.active else 'INACTIVE'}",
        f"  Location: {cam.latitude:.5f}, {cam.longitude:.5f}",
    ]
    if cam.agency_name:
        lines.append(f"  Agency: {cam.agency_name}")
    if cam.last_updated:
        lines.append(f"  Last updated: {cam.last_updated.isoformat()}")
    if cam.primary_linear_ref is not None:
        lines.append(f"  Mile marker: {cam.primary_linear_ref:.2f}")
    for i, v in enumerate(cam.views):
        lines.append(f"  View {i + 1}: {v.url}")
    if verbose:
        lines.append(f"  URI: {cam.uri}")
        if cam.icon:
            lines.append(f"  Icon: {cam.icon}")
    return "\n".join(lines)


def format_event(ev: Event, verbose: bool = False) -> str:
    """Return a human-readable summary of an event."""
    pri_map = {1: "P1-CRITICAL", 2: "P2-HIGH", 3: "P3-MODERATE", 4: "P4-LOW", 5: "P5-INFO"}
    priority_str = pri_map.get(ev.priority or 0, f"P{ev.priority}")
    lines = [
        f"Event {ev.event_id}: {ev.title}",
        f"  Priority: {priority_str}",
        f"  Location: {ev.latitude:.5f}, {ev.longitude:.5f}",
    ]
    if ev.description:
        from html.parser import HTMLParser

        class _Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self._parts: List[str] = []
            def handle_data(self, data: str):
                self._parts.append(data)
            def get_text(self) -> str:
                return " ".join(self._parts).strip()

        stripper = _Strip()
        stripper.feed(ev.description)
        desc = stripper.get_text()
        lines.append(f"  Description: {_truncate(desc, 200)}")
    if ev.last_updated:
        lines.append(f"  Last updated: {ev.last_updated.isoformat()}")
    if ev.begin_time:
        lines.append(f"  Started: {ev.begin_time.isoformat()}")
    if ev.agency_name:
        lines.append(f"  Agency: {ev.agency_name}")
    if verbose:
        lines.append(f"  URI: {ev.uri}")
        if ev.icon:
            lines.append(f"  Icon: {ev.icon}")
        if ev.color:
            lines.append(f"  Color: {ev.color}")
    return "\n".join(lines)


def format_map_feature(feat: MapFeature) -> str:
    """Return a brief one-liner summary of a map feature."""
    extra = ""
    if feat.typename == "Camera":
        snap = feat.views[0].url if feat.views else "(no snapshot)"
        status = "active" if feat.active else "inactive"
        extra = f" [{status}] → {snap}"
    elif feat.typename == "Event":
        extra = f" [priority {feat.priority}]"
    elif feat.typename == "Sign":
        extra = f" [{feat.sign_display_type}]"
    lat = (feat.bbox.south + feat.bbox.north) / 2
    lon = (feat.bbox.west + feat.bbox.east) / 2
    return f"{feat.typename} {feat.uri} ({lat:.4f}, {lon:.4f}) – {feat.title}{extra}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_cameras(args: argparse.Namespace) -> None:
    bbox = BoundingBox.parse(args.bbox) if args.bbox else BoundingBox.from_ma_statewide()
    zoom = args.zoom or 14
    print(f"Fetching cameras in bbox {bbox} at zoom {zoom}…")
    cameras = list_cameras(bbox, zoom=zoom)
    print(f"Found {len(cameras)} camera(s).\n")
    for feat in cameras:
        print(format_map_feature(feat))


def _cli_events(args: argparse.Namespace) -> None:
    bbox = BoundingBox.parse(args.bbox) if args.bbox else BoundingBox.from_ma_statewide()
    zoom = args.zoom or 8
    layer = args.layer or None
    slugs = [layer] if layer else None
    print(f"Fetching events in bbox {bbox} at zoom {zoom}…")
    events = list_events(bbox, layer_slugs=slugs, zoom=zoom)
    print(f"Found {len(events)} event(s).\n")
    for feat in events:
        print(format_map_feature(feat))


def _cli_camera(args: argparse.Namespace) -> None:
    cid = args.camera_id
    print(f"Fetching camera {cid}…")
    cam = get_camera(cid)
    print(format_camera(cam, verbose=True))


def _cli_event(args: argparse.Namespace) -> None:
    eid = args.event_id
    print(f"Fetching event {eid}…")
    ev = get_event(eid)
    print(format_event(ev, verbose=True))


def _cli_route(args: argparse.Namespace) -> None:
    route = args.route_id
    print(f"Searching along route {route}…")
    result = search_route(route)
    if result.error:
        print(f"Warning from API: {result.error}")
    print(f"\n{result.route_id} – {len(result.events)} event(s), {len(result.camera_views)} camera view(s)")
    if result.events:
        print("\nEvents:")
        for ev in result.events:
            print(f"  {ev.uri}: {ev.title}")
    if result.camera_views:
        print("\nCamera views:")
        for cv in result.camera_views:
            print(f"  {cv.uri}: {cv.title}")
            print(f"    Snapshot: {cv.url}")


def _cli_signs(args: argparse.Namespace) -> None:
    bbox = BoundingBox.parse(args.bbox) if args.bbox else BoundingBox.from_ma_statewide()
    zoom = args.zoom or 12
    print(f"Fetching signs in bbox {bbox} at zoom {zoom}…")
    signs = list_signs(bbox, zoom=zoom)
    print(f"Found {len(signs)} sign(s).\n")
    for feat in signs:
        print(format_map_feature(feat))


def _cli_notifications(args: argparse.Namespace) -> None:
    notifs = get_notifications()
    if not notifs:
        print("No active system notifications.")
    else:
        print(f"Active notifications ({len(notifs)}):")
        for n in notifs:
            print(f"  [{n.type}] {n.title}")
            if n.description:
                print(f"    {_truncate(n.description, 120)}")


def _cli_layers(args: argparse.Namespace) -> None:
    print("Available layer slugs:\n")
    for slug, desc in sorted(LAYER_SLUGS.items()):
        print(f"  {slug:<35} {desc}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="massdot_client",
        description="MassDOT / Mass511 traffic data client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        examples:
          python massdot_client.py cameras
          python massdot_client.py cameras --bbox "42.2,42.5,-71.5,-70.9"
          python massdot_client.py events --layer roadReports
          python massdot_client.py camera 10257
          python massdot_client.py event MA-2426211456467036
          python massdot_client.py route I-90
          python massdot_client.py signs
          python massdot_client.py notifications
          python massdot_client.py layers
        """),
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # cameras
    p_cams = sub.add_parser("cameras", help="List traffic cameras by bounding box")
    p_cams.add_argument("--bbox", help="south,north,west,east (default: all MA)")
    p_cams.add_argument("--zoom", type=int, help="Zoom level (default: 14)")
    p_cams.set_defaults(func=_cli_cameras)

    # events
    p_ev = sub.add_parser("events", help="List traffic events by bounding box")
    p_ev.add_argument("--bbox", help="south,north,west,east")
    p_ev.add_argument("--layer", help=f"Layer slug (default: roadReports+construction)")
    p_ev.add_argument("--zoom", type=int)
    p_ev.set_defaults(func=_cli_events)

    # camera detail
    p_cam = sub.add_parser("camera", help="Get details for a single camera")
    p_cam.add_argument("camera_id", help="Numeric camera ID (e.g. 10257)")
    p_cam.set_defaults(func=_cli_camera)

    # event detail
    p_evd = sub.add_parser("event", help="Get details for a single event")
    p_evd.add_argument("event_id", help="Event ID (e.g. MA-2426211456467036)")
    p_evd.set_defaults(func=_cli_event)

    # route
    p_route = sub.add_parser("route", help="Search all items along a named route")
    p_route.add_argument("route_id", help="Route ID (e.g. I-90, US-6, RT-128)")
    p_route.set_defaults(func=_cli_route)

    # signs
    p_signs = sub.add_parser("signs", help="List electronic signs")
    p_signs.add_argument("--bbox", help="south,north,west,east")
    p_signs.add_argument("--zoom", type=int)
    p_signs.set_defaults(func=_cli_signs)

    # notifications
    p_notif = sub.add_parser("notifications", help="Show system notifications / banners")
    p_notif.set_defaults(func=_cli_notifications)

    # layers
    p_layers = sub.add_parser("layers", help="Print all known layer slugs")
    p_layers.set_defaults(func=_cli_layers)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
