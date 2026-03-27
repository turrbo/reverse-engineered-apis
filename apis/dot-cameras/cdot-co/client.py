#!/usr/bin/env python3
"""
CDOT (Colorado Department of Transportation) Traffic Data Client
================================================================
A production-quality Python client for the COtrip / CDOT public traffic
information APIs, reverse-engineered from https://maps.cotrip.org.

Architecture
------------
COtrip uses two tiers of API:

1. **REST APIs** at ``https://cotg.carsprogram.org``
   Microservices named ``<service>_v<n>/api/<resource>`` that return raw JSON
   arrays. No authentication required. These feed the map in near-real-time.

   Confirmed working endpoints:
   - /cameras_v1/api/cameras          — 1 000+ traffic cameras
   - /signs_v1/api/signs              — 200+ variable message signs (VMS/DMS)
   - /rwis_v1/api/stations            — 135 Road/Weather Information System stations
   - /rest-areas_v1/api/restAreas     — 45 rest areas & welcome centers
   - /avl_v2/api/plows                — 50+ snowplow GPS tracks (AVL)

2. **GraphQL BFF** at ``https://maps.cotrip.org/api/graphql``
   A Backend-for-Frontend proxy that aggregates the microservices. The primary
   query for map data is ``mapFeaturesQuery`` which accepts a bounding box,
   zoom level, and a list of ``layerSlugs``. Returns GeoJSON-style features.

   Valid layerSlugs (confirmed by JS reverse engineering):
   - roadReports          — active traffic incidents/crashes
   - roadWork             — active construction zones
   - roadClosures         — current road closures
   - future               — planned/future construction
   - winterDriving        — road condition reports
   - chainLaws            — chain/traction law requirements
   - chainStations        — chain check/brake check stations
   - mountainPasses       — mountain pass conditions
   - weatherWarnings      — NWS weather alerts on roads
   - wazeReports          — crowd-sourced Waze incidents
   - restrictions         — oversize/overweight restrictions
   - weighStations        — weigh station locations
   - truckRamps           — runaway truck ramp locations
   - truckStopsPortsEntry — truck stop and port-of-entry locations
   - expressLanes         — express lane locations
   - scenicByways         — scenic byway markers

   CMS queries (no bounding box needed):
   - cmsMessagesQuery     — active travel alerts / safety announcements
   - notificationsQuery   — system notifications

Camera Media
------------
Each camera record includes ``views[]`` with:
- ``url``            — HLS (.m3u8) live stream at publicstreamer2.cotrip.org
- ``videoPreviewUrl`` — JPEG snapshot at cocam.carsprogram.org

CDN for camera snapshots:
  ``https://cocam.carsprogram.org/Snapshots/<CAMERA_ID>.flv.png``

Google Maps API key (public, browser-restricted):
  AIzaSyAg3mTV0MQ-_91ZzNVV-qgsfGW28IQn8pY

Usage
-----
::

    # As a library:
    from cdot_client import CDOTClient

    client = CDOTClient()
    cameras = client.get_cameras()
    events  = client.get_events(layer_slug="roadReports")
    passes  = client.get_mountain_passes()

    # As a CLI tool:
    python cdot_client.py cameras
    python cdot_client.py events --layer roadReports
    python cdot_client.py events --layer chainLaws --statewide
    python cdot_client.py mountain-passes
    python cdot_client.py weather-stations
    python cdot_client.py rest-areas
    python cdot_client.py signs
    python cdot_client.py plows
    python cdot_client.py alerts
    python cdot_client.py summary
"""

from __future__ import annotations

import json
import sys
import time
import argparse
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REST_BASE = "https://cotg.carsprogram.org"
_GQL_URL   = "https://maps.cotrip.org/api/graphql"

# Colorado state bounding box (WGS-84)
_CO_BBOX = {"north": 41.00, "south": 36.99, "east": -102.04, "west": -109.06}

# Valid layerSlugs for mapFeaturesQuery
LAYER_SLUGS = {
    "roadReports":          "Active traffic incidents and crashes",
    "roadWork":             "Active construction zones",
    "roadClosures":         "Current road closures",
    "future":               "Planned / upcoming construction",
    "winterDriving":        "Road condition / winter driving reports",
    "chainLaws":            "Chain and traction law requirements",
    "chainStations":        "Chain check and brake check stations",
    "mountainPasses":       "Mountain pass conditions",
    "weatherWarnings":      "NWS weather alerts affecting roads",
    "wazeReports":          "Crowd-sourced Waze incident reports",
    "restrictions":         "Oversize / overweight restrictions",
    "weighStations":        "Weigh station locations",
    "truckRamps":           "Runaway truck ramp locations",
    "truckStopsPortsEntry": "Truck stops and ports of entry",
    "expressLanes":         "Express lane features",
    "scenicByways":         "Scenic byway markers",
}

_USER_AGENT = (
    "Mozilla/5.0 (compatible; cdot-python-client/1.0; "
    "+https://github.com/your-repo/cdot-client)"
)

_DEFAULT_TIMEOUT = 20  # seconds
_STATEWIDE_ZOOM  = 5   # zoom level for statewide queries
_REGIONAL_ZOOM   = 10  # zoom level for regional queries


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Location:
    """Geographic location with optional route reference."""
    latitude: float
    longitude: float
    route_id: Optional[str] = None
    linear_reference: Optional[float] = None
    city_reference: Optional[str] = None
    direction: Optional[str] = None
    fips: Optional[int] = None
    local_road: Optional[bool] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Location":
        if not d:
            return cls(latitude=0.0, longitude=0.0)
        return cls(
            latitude=float(d.get("latitude") or d.get("routeLatitude") or 0),
            longitude=float(d.get("longitude") or d.get("routeLongitude") or 0),
            route_id=d.get("routeId") or d.get("routeDesignator"),
            linear_reference=d.get("linearReference"),
            city_reference=d.get("cityReference"),
            direction=d.get("signFacingDirection") or d.get("directionOfTravel"),
            fips=d.get("fips"),
            local_road=d.get("localRoad"),
        )


@dataclass
class CameraView:
    """A single viewpoint for a traffic camera."""
    name: str
    view_type: str          # e.g. "WMP" (Windows Media Player / HLS)
    stream_url: str         # HLS .m3u8 live stream URL
    snapshot_url: str       # Static JPEG preview URL
    image_timestamp: Optional[int] = None  # Unix ms

    @property
    def snapshot_age_seconds(self) -> Optional[float]:
        """Seconds since the last snapshot was captured, or None."""
        if self.image_timestamp is None:
            return None
        now_ms = int(time.time() * 1000)
        return (now_ms - self.image_timestamp) / 1000.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CameraView":
        return cls(
            name=d.get("name", ""),
            view_type=d.get("type", ""),
            stream_url=d.get("url", ""),
            snapshot_url=d.get("videoPreviewUrl", ""),
            image_timestamp=d.get("imageTimestamp"),
        )


@dataclass
class Camera:
    """Traffic camera with one or more viewpoints."""
    id: int
    name: str
    location: Location
    views: list[CameraView]
    active: bool = True
    public: bool = True
    owner: Optional[str] = None
    last_updated: Optional[int] = None  # Unix ms

    @property
    def primary_snapshot_url(self) -> str:
        """URL of the first available snapshot image."""
        return self.views[0].snapshot_url if self.views else ""

    @property
    def primary_stream_url(self) -> str:
        """URL of the first available HLS live stream."""
        return self.views[0].stream_url if self.views else ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Camera":
        owner_info = d.get("cameraOwner") or {}
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            location=Location.from_dict(d.get("location") or {}),
            views=[CameraView.from_dict(v) for v in (d.get("views") or [])],
            active=d.get("active", True),
            public=d.get("public", True),
            owner=owner_info.get("name"),
            last_updated=d.get("lastUpdated"),
        )


@dataclass
class Sign:
    """Variable Message Sign / Dynamic Message Sign (VMS/DMS)."""
    id: str
    name: str
    status: str
    location: Location
    display_lines: list[list[str]] = field(default_factory=list)
    agency_id: Optional[str] = None
    agency_name: Optional[str] = None
    sign_type: Optional[str] = None
    last_updated: Optional[int] = None

    @property
    def current_message(self) -> str:
        """Return all page lines joined as a readable string."""
        parts = []
        for page in self.display_lines:
            parts.append(" / ".join(line for line in page if line))
        return " | ".join(p for p in parts if p)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Sign":
        display = d.get("display") or {}
        pages   = display.get("pages") or []
        lines   = [p.get("lines") or [] for p in pages]
        props   = d.get("properties") or {}
        return cls(
            id=str(d.get("id", d.get("idForDisplay", ""))),
            name=d.get("name", ""),
            status=d.get("status", ""),
            location=Location.from_dict(d.get("location") or {}),
            display_lines=lines,
            agency_id=d.get("agencyId"),
            agency_name=d.get("agencyName"),
            sign_type=props.get("signType"),
            last_updated=d.get("lastUpdated"),
        )


@dataclass
class WeatherStation:
    """Road Weather Information System (RWIS) station."""
    id: int
    name: str
    station_identifier: str
    location: Location
    top_fields: list[str] = field(default_factory=list)
    timezone_id: str = "America/Denver"
    last_updated: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WeatherStation":
        return cls(
            id=d.get("id", 0),
            name=d.get("name", ""),
            station_identifier=d.get("stationIdentifier", ""),
            location=Location.from_dict(d.get("location") or {}),
            top_fields=d.get("topFields") or [],
            timezone_id=d.get("timezoneId", "America/Denver"),
            last_updated=d.get("lastUpdated"),
        )


@dataclass
class RestArea:
    """Rest area or welcome center."""
    id: int
    title: str
    route_designator: str
    direction: Optional[str]
    is_open: bool
    latitude: float
    longitude: float
    nearby_city: Optional[str] = None
    amenities: list[str] = field(default_factory=list)
    status_message: Optional[str] = None
    last_update: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RestArea":
        amenities = [a.get("label", "") for a in (d.get("amenities") or [])]
        return cls(
            id=d.get("id", 0),
            title=d.get("title", ""),
            route_designator=d.get("routeDesignator", ""),
            direction=d.get("directionOfTravel"),
            is_open=d.get("isOpen", True),
            latitude=float(d.get("displayLatitude") or d.get("routeLatitude") or 0),
            longitude=float(d.get("displayLongitude") or d.get("routeLongitude") or 0),
            nearby_city=d.get("nearbyCity"),
            amenities=[a for a in amenities if a],
            status_message=d.get("statusMessage"),
            last_update=d.get("lastUpdate"),
        )


@dataclass
class PlowStatus:
    """Single timestamped position/status reading for a snowplow."""
    timestamp: int  # Unix ms
    latitude: float
    longitude: float
    route_designator: Optional[str] = None
    linear_reference: Optional[float] = None
    heading: Optional[str] = None
    nearby_description: Optional[str] = None
    total_truck_count: Optional[int] = None
    plow_icon: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlowStatus":
        return cls(
            timestamp=d.get("timestamp", 0),
            latitude=float(d.get("latitude", 0)),
            longitude=float(d.get("longitude", 0)),
            route_designator=d.get("routeDesignator"),
            linear_reference=d.get("linearReference"),
            heading=d.get("headingString"),
            nearby_description=d.get("nearbyPointsDescription"),
            total_truck_count=d.get("totalTruckCount"),
            plow_icon=d.get("plowIconName"),
        )


@dataclass
class Plow:
    """Snowplow vehicle with GPS track history."""
    id: str
    statuses: list[PlowStatus] = field(default_factory=list)

    @property
    def latest_status(self) -> Optional[PlowStatus]:
        """Most recent reported status."""
        return self.statuses[0] if self.statuses else None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Plow":
        return cls(
            id=d.get("id", ""),
            statuses=[PlowStatus.from_dict(s) for s in (d.get("statuses") or [])],
        )


@dataclass
class MapFeature:
    """
    A map feature returned by the GraphQL mapFeaturesQuery.

    This is the generic container for events, clusters, custom markers,
    and other entities returned by the GraphQL BFF.
    """
    uri: str                    # Unique resource identifier, e.g. "event/CDOT-12345NB"
    title: str
    typename: str               # GraphQL __typename: Event, Cluster, Custom, Sign, etc.
    bbox: list[float]           # [west, south, east, north] or [lon, lat, lon, lat]
    features: list[dict[str, Any]] = field(default_factory=list)  # GeoJSON features
    tooltip: Optional[str] = None
    priority: Optional[int] = None  # For Event typename

    @property
    def resource_type(self) -> str:
        """Return the type portion of the URI (e.g. 'event', 'mountainPasses')."""
        parts = self.uri.split("/")
        return parts[0] if parts else ""

    @property
    def resource_id(self) -> str:
        """Return the ID portion of the URI."""
        parts = self.uri.split("/")
        return parts[1] if len(parts) > 1 else ""

    @property
    def centroid(self) -> tuple[float, float]:
        """Return (latitude, longitude) centroid from bbox."""
        if len(self.bbox) == 4:
            lon = (self.bbox[0] + self.bbox[2]) / 2
            lat = (self.bbox[1] + self.bbox[3]) / 2
            return lat, lon
        return 0.0, 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MapFeature":
        return cls(
            uri=d.get("uri", ""),
            title=d.get("title", ""),
            typename=d.get("__typename", ""),
            bbox=d.get("bbox") or [],
            features=d.get("features") or [],
            tooltip=d.get("tooltip"),
            priority=d.get("priority"),
        )


@dataclass
class TravelAlert:
    """CMS travel alert / system announcement."""
    uri: str
    title: str
    content: Optional[str] = None
    priority: Optional[str] = None
    message_type: Optional[str] = None
    display_locations: Optional[list[str]] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TravelAlert":
        return cls(
            uri=d.get("uri", ""),
            title=d.get("title", ""),
            content=d.get("content"),
            priority=d.get("priority"),
            message_type=d.get("messageType"),
            display_locations=d.get("displayLocations"),
        )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class CDOTAPIError(Exception):
    """Raised when an API request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _http_get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> Any:
    """Perform an HTTP GET and return parsed JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise CDOTAPIError(
            f"GET {url} returned HTTP {exc.code}: {body}", exc.code
        ) from exc
    except urllib.error.URLError as exc:
        raise CDOTAPIError(f"GET {url} network error: {exc.reason}") from exc


def _graphql(query: str, variables: Optional[dict[str, Any]] = None,
             timeout: int = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Execute a GraphQL POST against the COtrip BFF and return the data dict."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _GQL_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_str = exc.read().decode("utf-8", errors="replace")[:300]
        raise CDOTAPIError(
            f"GraphQL POST returned HTTP {exc.code}: {body_str}", exc.code
        ) from exc
    except urllib.error.URLError as exc:
        raise CDOTAPIError(f"GraphQL network error: {exc.reason}") from exc

    if "errors" in result and result["errors"]:
        msgs = "; ".join(e.get("message", "") for e in result["errors"])
        raise CDOTAPIError(f"GraphQL errors: {msgs}")

    return result.get("data") or {}


# ---------------------------------------------------------------------------
# GraphQL query strings
# ---------------------------------------------------------------------------

_GQL_MAP_FEATURES = """
query MapFeatures($input: MapFeaturesArgs!, $plowType: String) {
    mapFeaturesQuery(input: $input) {
        mapFeatures {
            bbox
            title
            tooltip
            uri
            features {
                id
                geometry
                properties
                type
            }
            ... on Event {
                priority
            }
            __typename
        }
    }
}
"""

_GQL_CMS_MESSAGES = """
query CmsMessages {
    cmsMessagesQuery {
        cmsMessages {
            uri
            title
            content
            priority
            messageType
            displayLocations
        }
        error { type }
    }
}
"""

_GQL_NOTIFICATIONS = """
query Notifications {
    notificationsQuery {
        notifications {
            uri
            title
            description
            type
            lastUpdated { timestamp timezone }
        }
        error { type }
    }
}
"""

_GQL_CMS_DASHBOARDS = """
query CmsDashboards {
    cmsDashboardsQuery {
        cmsDashboards {
            id
            title
            icon
            bounds { west south east north }
            layers
        }
    }
}
"""

_GQL_PREDEFINED_ROUTES = """
query {
    allPredefinedRoutesQuery {
        name
        sortOrder
        popular
        bbox
    }
}
"""


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class CDOTClient:
    """
    Client for the Colorado Department of Transportation (CDOT) public
    traffic information APIs served by the COtrip platform.

    All methods raise :class:`CDOTAPIError` on network or API failures.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds (default 20).
    """

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT):
        self.timeout = timeout

    # ------------------------------------------------------------------
    # REST endpoints (cotg.carsprogram.org)
    # ------------------------------------------------------------------

    def get_cameras(self, active_only: bool = False) -> list[Camera]:
        """
        Return all traffic cameras in Colorado.

        Parameters
        ----------
        active_only:
            If True, filter out cameras with ``active=False``.

        Returns
        -------
        list[Camera]
            1 000+ camera objects with location, owner, and view URLs.

        Examples
        --------
        ::

            cameras = client.get_cameras(active_only=True)
            for cam in cameras[:5]:
                print(cam.name, cam.primary_snapshot_url)
        """
        url = f"{_REST_BASE}/cameras_v1/api/cameras"
        raw = _http_get(url, self.timeout)
        cameras = [Camera.from_dict(d) for d in raw]
        if active_only:
            cameras = [c for c in cameras if c.active]
        return cameras

    def get_signs(self, displaying_only: bool = False) -> list[Sign]:
        """
        Return all Variable Message Signs (VMS/DMS) across Colorado.

        Parameters
        ----------
        displaying_only:
            If True, return only signs with status ``DISPLAYING_MESSAGE``.

        Returns
        -------
        list[Sign]
            ~200 sign objects with display content and location.

        Examples
        --------
        ::

            signs = client.get_signs(displaying_only=True)
            for s in signs:
                if s.current_message:
                    print(f"{s.name}: {s.current_message}")
        """
        url = f"{_REST_BASE}/signs_v1/api/signs"
        raw = _http_get(url, self.timeout)
        signs = [Sign.from_dict(d) for d in raw]
        if displaying_only:
            signs = [s for s in signs if s.status == "DISPLAYING_MESSAGE"]
        return signs

    def get_weather_stations(self) -> list[WeatherStation]:
        """
        Return all RWIS (Road Weather Information System) stations.

        Returns
        -------
        list[WeatherStation]
            ~135 weather stations with location and sensor field names.

        Notes
        -----
        This endpoint returns station metadata. Sensor readings (temperature,
        pavement status, visibility, etc.) are available via the GraphQL
        ``weatherStationQuery`` (requires individual station ID).
        """
        url = f"{_REST_BASE}/rwis_v1/api/stations"
        raw = _http_get(url, self.timeout)
        return [WeatherStation.from_dict(d) for d in raw]

    def get_rest_areas(self, open_only: bool = False) -> list[RestArea]:
        """
        Return all rest areas and welcome centers.

        Parameters
        ----------
        open_only:
            If True, return only areas where ``isOpen=True``.

        Returns
        -------
        list[RestArea]
            ~45 rest areas with amenities and status.
        """
        url = f"{_REST_BASE}/rest-areas_v1/api/restAreas"
        raw = _http_get(url, self.timeout)
        areas = [RestArea.from_dict(d) for d in raw]
        if open_only:
            areas = [a for a in areas if a.is_open]
        return areas

    def get_plows(self) -> list[Plow]:
        """
        Return active snowplow vehicles with GPS track history.

        Returns
        -------
        list[Plow]
            50+ plow objects, each with a list of recent position/status
            readings (``statuses``). The first status is the most recent.

        Notes
        -----
        This is the AVL (Automatic Vehicle Location) feed. Updated frequently
        during winter operations.
        """
        url = f"{_REST_BASE}/avl_v2/api/plows"
        raw = _http_get(url, self.timeout)
        return [Plow.from_dict(d) for d in raw]

    # ------------------------------------------------------------------
    # GraphQL endpoints (maps.cotrip.org/api/graphql)
    # ------------------------------------------------------------------

    def get_events(
        self,
        layer_slug: str = "roadReports",
        *,
        north: float = _CO_BBOX["north"],
        south: float = _CO_BBOX["south"],
        east:  float = _CO_BBOX["east"],
        west:  float = _CO_BBOX["west"],
        zoom:  int   = _STATEWIDE_ZOOM,
    ) -> list[MapFeature]:
        """
        Return map features for a given layer slug within a bounding box.

        This is the primary method for fetching traffic events, road conditions,
        closures, mountain pass status, and other incident types.

        Parameters
        ----------
        layer_slug:
            One of the :data:`LAYER_SLUGS` keys (default ``"roadReports"``).
        north, south, east, west:
            Bounding box in decimal degrees (WGS-84). Defaults to Colorado.
        zoom:
            Map zoom level (integer). Affects clustering behaviour. Use 5–8
            for statewide queries, 10–15 for regional / street-level detail.

        Returns
        -------
        list[MapFeature]
            Features with ``__typename`` of ``Event``, ``Custom``, or
            ``Cluster``. Cluster features aggregate nearby items at low zoom.

        Raises
        ------
        CDOTAPIError
            If the layer slug is invalid or the server returns an error.

        Examples
        --------
        ::

            # Statewide road closures
            closures = client.get_events("roadClosures")

            # Denver-area construction at higher zoom
            construction = client.get_events(
                "roadWork",
                north=40.0, south=39.5, east=-104.5, west=-105.5,
                zoom=10
            )
        """
        variables = {
            "input": {
                "north": north,
                "south": south,
                "east":  east,
                "west":  west,
                "zoom":  zoom,
                "layerSlugs": [layer_slug],
            },
            "plowType": "snow-plow-camera",
        }
        data = _graphql(_GQL_MAP_FEATURES, variables, self.timeout)
        raw_features = (
            data.get("mapFeaturesQuery") or {}
        ).get("mapFeatures") or []
        return [MapFeature.from_dict(f) for f in raw_features]

    def get_road_closures(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """Convenience wrapper: return active road closures statewide."""
        return self.get_events("roadClosures", **bbox_kwargs)

    def get_chain_laws(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """Convenience wrapper: return chain/traction law segments."""
        return self.get_events("chainLaws", **bbox_kwargs)

    def get_mountain_passes(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """
        Return mountain pass condition markers statewide.

        Returns
        -------
        list[MapFeature]
            ~46 pass locations. Each feature's ``uri`` is of the form
            ``mountainPasses/mountainPass-<ID>``. Fetch full pass details
            via :meth:`get_map_feature_detail` if needed.

        Examples
        --------
        ::

            passes = client.get_mountain_passes()
            for p in passes:
                lat, lon = p.centroid
                print(f"{p.title:40}  {lat:.4f},{lon:.4f}")
        """
        return self.get_events("mountainPasses", **bbox_kwargs)

    def get_construction(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """Convenience wrapper: return active construction zones."""
        return self.get_events("roadWork", **bbox_kwargs)

    def get_incidents(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """Convenience wrapper: return traffic incidents (crashes, hazards)."""
        return self.get_events("roadReports", **bbox_kwargs)

    def get_winter_driving(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """Convenience wrapper: return road condition / winter driving reports."""
        return self.get_events("winterDriving", **bbox_kwargs)

    def get_weather_warnings(self, **bbox_kwargs: Any) -> list[MapFeature]:
        """Convenience wrapper: return NWS weather alerts on roads."""
        return self.get_events("weatherWarnings", **bbox_kwargs)

    def get_travel_alerts(self) -> list[TravelAlert]:
        """
        Return active CMS travel alerts and safety announcements.

        These are manually authored messages from CDOT staff, such as
        statewide travel advisories, holiday warnings, and major closures.

        Returns
        -------
        list[TravelAlert]
            Currently active travel alerts (typically 3–15 messages).

        Examples
        --------
        ::

            for alert in client.get_travel_alerts():
                print(f"[{alert.priority}] {alert.title}")
        """
        data = _graphql(_GQL_CMS_MESSAGES, timeout=self.timeout)
        raw = (data.get("cmsMessagesQuery") or {}).get("cmsMessages") or []
        return [TravelAlert.from_dict(d) for d in raw]

    def get_predefined_routes(self) -> list[dict[str, Any]]:
        """
        Return CDOT predefined route definitions (named routes / corridors).

        Returns
        -------
        list[dict]
            Each dict has ``name``, ``sortOrder``, ``popular``, and ``bbox``.
        """
        data = _graphql(_GQL_PREDEFINED_ROUTES, timeout=self.timeout)
        return (data.get("allPredefinedRoutesQuery") or [])

    def get_all_events(self, **bbox_kwargs: Any) -> dict[str, list[MapFeature]]:
        """
        Fetch map features for all traffic-related layer slugs in one call.

        Makes one GraphQL request per layer. Use bounding box kwargs to
        restrict the query area (same as :meth:`get_events`).

        Returns
        -------
        dict[str, list[MapFeature]]
            Keys are layer slug strings; values are feature lists.

        Examples
        --------
        ::

            all_data = client.get_all_events(zoom=6)
            for slug, features in all_data.items():
                print(f"{slug}: {len(features)} features")
        """
        slugs = [
            "roadReports", "roadWork", "roadClosures", "winterDriving",
            "chainLaws", "mountainPasses", "weatherWarnings", "restrictions",
        ]
        result = {}
        for slug in slugs:
            try:
                result[slug] = self.get_events(slug, **bbox_kwargs)
            except CDOTAPIError:
                result[slug] = []
        return result

    # ------------------------------------------------------------------
    # Utility / convenience methods
    # ------------------------------------------------------------------

    def search_cameras_by_route(self, route_id: str) -> list[Camera]:
        """
        Return cameras associated with a specific route (e.g. 'I-70').

        Parameters
        ----------
        route_id:
            Route identifier string. Partial match, case-insensitive.
            Examples: ``"I-70"``, ``"US-6"``, ``"CO-9"``.

        Returns
        -------
        list[Camera]
            Cameras whose name or route_id contains the search string.
        """
        route_lower = route_id.lower()
        cameras = self.get_cameras()
        return [
            c for c in cameras
            if route_lower in c.name.lower()
            or (c.location.route_id or "").lower() == route_lower
        ]

    def get_i70_cameras(self) -> list[Camera]:
        """Return cameras along the I-70 mountain corridor."""
        return self.search_cameras_by_route("I-70")

    def get_mountain_pass_cameras(self) -> list[Camera]:
        """
        Return cameras near well-known Colorado mountain passes.

        Filters cameras by name matching common pass names.
        """
        pass_keywords = [
            "loveland", "eisenhower", "vail", "glenwood", "monarch",
            "la veta", "rabbit ears", "berthoud", "red mountain",
            "independence", "tennessee", "wolf creek", "million dollar",
            "cameron", "kenosha", "hoosier", "guanella", "slumgullion",
            "poncha", "marshall", "cochetopa",
        ]
        cameras = self.get_cameras(active_only=True)
        result = []
        for cam in cameras:
            name_lower = cam.name.lower()
            if any(kw in name_lower for kw in pass_keywords):
                result.append(cam)
        return result

    def get_camera_snapshot(self, camera: Camera) -> Optional[bytes]:
        """
        Download the current snapshot image for a camera.

        Parameters
        ----------
        camera:
            A :class:`Camera` object obtained from :meth:`get_cameras`.

        Returns
        -------
        bytes or None
            Raw JPEG/PNG image bytes, or ``None`` if no snapshot is available.

        Raises
        ------
        CDOTAPIError
            On network errors.
        """
        url = camera.primary_snapshot_url
        if not url:
            return None
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise CDOTAPIError(
                f"Snapshot download failed for {url}: HTTP {exc.code}", exc.code
            ) from exc
        except urllib.error.URLError as exc:
            raise CDOTAPIError(
                f"Snapshot download network error for {url}: {exc.reason}"
            ) from exc

    def statewide_summary(self) -> dict[str, Any]:
        """
        Build a quick summary of current Colorado traffic conditions.

        Returns
        -------
        dict
            Contains counts and samples of active events, closures,
            chain laws, and system status. Suitable for dashboards.

        Examples
        --------
        ::

            summary = client.statewide_summary()
            print(f"Active incidents: {summary['incidents']}")
            print(f"Road closures:    {summary['closures']}")
            print(f"Mountain passes:  {summary['mountain_passes']}")
        """
        summary: dict[str, Any] = {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "cameras_total": 0,
            "cameras_active": 0,
            "signs_displaying": 0,
            "signs_total": 0,
            "plows_active": 0,
            "weather_stations": 0,
            "rest_areas_open": 0,
            "rest_areas_total": 0,
            "incidents": 0,
            "construction": 0,
            "closures": 0,
            "chain_laws": 0,
            "winter_driving": 0,
            "mountain_passes": 0,
            "travel_alerts": 0,
            "errors": [],
        }

        # REST endpoints
        try:
            cameras = self.get_cameras()
            summary["cameras_total"]  = len(cameras)
            summary["cameras_active"] = sum(1 for c in cameras if c.active)
        except CDOTAPIError as e:
            summary["errors"].append(f"cameras: {e}")

        try:
            signs = self.get_signs()
            summary["signs_total"]      = len(signs)
            summary["signs_displaying"] = sum(
                1 for s in signs if s.status == "DISPLAYING_MESSAGE"
            )
        except CDOTAPIError as e:
            summary["errors"].append(f"signs: {e}")

        try:
            plows = self.get_plows()
            summary["plows_active"] = len(plows)
        except CDOTAPIError as e:
            summary["errors"].append(f"plows: {e}")

        try:
            stations = self.get_weather_stations()
            summary["weather_stations"] = len(stations)
        except CDOTAPIError as e:
            summary["errors"].append(f"weather_stations: {e}")

        try:
            areas = self.get_rest_areas()
            summary["rest_areas_total"] = len(areas)
            summary["rest_areas_open"]  = sum(1 for a in areas if a.is_open)
        except CDOTAPIError as e:
            summary["errors"].append(f"rest_areas: {e}")

        # GraphQL / event layers
        event_map = {
            "incidents":      "roadReports",
            "construction":   "roadWork",
            "closures":       "roadClosures",
            "chain_laws":     "chainLaws",
            "winter_driving": "winterDriving",
            "mountain_passes": "mountainPasses",
        }
        for key, slug in event_map.items():
            try:
                features = self.get_events(slug)
                summary[key] = len(features)
            except CDOTAPIError as e:
                summary["errors"].append(f"{slug}: {e}")

        try:
            alerts = self.get_travel_alerts()
            summary["travel_alerts"] = len(alerts)
        except CDOTAPIError as e:
            summary["errors"].append(f"travel_alerts: {e}")

        return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_cameras(cameras: list[Camera], limit: int = 10) -> None:
    print(f"\nTraffic Cameras ({len(cameras)} total, showing {min(limit, len(cameras))}):\n")
    print(f"  {'ID':>6}  {'Active':6}  {'Owner':20}  {'Name'}")
    print("  " + "-" * 80)
    for cam in cameras[:limit]:
        owner = (cam.owner or "")[:20]
        print(f"  {cam.id:>6}  {'Yes' if cam.active else 'No':6}  {owner:20}  {cam.name}")
        if cam.primary_snapshot_url:
            print(f"          Snapshot: {cam.primary_snapshot_url}")


def _print_features(features: list[MapFeature], label: str, limit: int = 20) -> None:
    print(f"\n{label} ({len(features)} total, showing {min(limit, len(features))}):\n")
    if not features:
        print("  (none)")
        return
    for feat in features[:limit]:
        lat, lon = feat.centroid
        tag = f"[{feat.typename}]"
        print(f"  {tag:10}  {feat.title}")
        print(f"             URI: {feat.uri}   lat={lat:.4f},lon={lon:.4f}")
        if feat.tooltip and feat.tooltip != feat.title:
            print(f"             {feat.tooltip}")


def _print_signs(signs: list[Sign], limit: int = 20) -> None:
    print(f"\nElectronic Signs ({len(signs)} total, showing {min(limit, len(signs))}):\n")
    for s in signs[:limit]:
        msg = s.current_message or "(blank)"
        print(f"  [{s.status[:20]:20}]  {s.name}")
        if msg != "(blank)":
            print(f"    Message: {msg}")


def _print_weather_stations(stations: list[WeatherStation], limit: int = 15) -> None:
    print(f"\nRWIS Weather Stations ({len(stations)} total, showing {min(limit, len(stations))}):\n")
    for st in stations[:limit]:
        print(f"  {st.id:>4}  {st.name}")
        print(f"        Route: {st.location.route_id or 'N/A'}   "
              f"lat={st.location.latitude:.4f},lon={st.location.longitude:.4f}")
        print(f"        Sensors: {', '.join(st.top_fields[:4])}")


def _print_rest_areas(areas: list[RestArea], limit: int = 15) -> None:
    print(f"\nRest Areas ({len(areas)} total, showing {min(limit, len(areas))}):\n")
    for a in areas[:limit]:
        status = "OPEN" if a.is_open else "CLOSED"
        direction = a.direction or "?"
        print(f"  [{status:6}]  {a.route_designator} {direction}  —  {a.title}")
        if a.nearby_city:
            print(f"           Near: {a.nearby_city}")
        if a.amenities:
            print(f"           Amenities: {', '.join(a.amenities[:5])}")


def _print_plows(plows: list[Plow], limit: int = 10) -> None:
    print(f"\nSnowplow Tracker ({len(plows)} active, showing {min(limit, len(plows))}):\n")
    for p in plows[:limit]:
        s = p.latest_status
        if s:
            print(f"  Vehicle {p.id:6}  {s.route_designator or 'N/A':8}  "
                  f"lat={s.latitude:.4f},lon={s.longitude:.4f}  "
                  f"heading={s.heading or 'N/A'}")
            if s.nearby_description:
                print(f"             {s.nearby_description}")


def _print_alerts(alerts: list[TravelAlert]) -> None:
    print(f"\nCDOT Travel Alerts ({len(alerts)}):\n")
    for a in alerts:
        pri = a.priority or "N/A"
        print(f"  [{pri:10}]  {a.title}")
        if a.content:
            print(f"    {a.content[:120]}...")


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nColorado Traffic Conditions Summary")
    print("=" * 40)
    print(f"  As of:              {summary['as_of']}")
    print()
    print(f"  Cameras (active):   {summary['cameras_active']:4} / {summary['cameras_total']}")
    print(f"  Signs (displaying): {summary['signs_displaying']:4} / {summary['signs_total']}")
    print(f"  Snowplows active:   {summary['plows_active']:4}")
    print(f"  Weather stations:   {summary['weather_stations']:4}")
    print(f"  Rest areas (open):  {summary['rest_areas_open']:4} / {summary['rest_areas_total']}")
    print()
    print(f"  Traffic incidents:  {summary['incidents']:4}")
    print(f"  Construction zones: {summary['construction']:4}")
    print(f"  Road closures:      {summary['closures']:4}")
    print(f"  Chain laws active:  {summary['chain_laws']:4}")
    print(f"  Winter driving:     {summary['winter_driving']:4}")
    print(f"  Mountain passes:    {summary['mountain_passes']:4}")
    print(f"  Travel alerts:      {summary['travel_alerts']:4}")
    if summary["errors"]:
        print()
        print("  Errors:")
        for err in summary["errors"]:
            print(f"    - {err}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdot_client",
        description="CDOT / COtrip traffic data CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  cameras          List traffic cameras
  signs            List variable message signs
  weather-stations List RWIS weather stations
  rest-areas       List rest areas and welcome centers
  plows            List active snowplow vehicles
  events           List map events for a layer (see --layer)
  mountain-passes  List mountain pass conditions
  alerts           List CDOT travel alerts
  summary          Print statewide conditions summary

Layer slugs (use with 'events' command):
""" + "\n".join(
            f"  {slug:25}  {desc}"
            for slug, desc in LAYER_SLUGS.items()
        ),
    )
    parser.add_argument("command", choices=[
        "cameras", "signs", "weather-stations", "rest-areas", "plows",
        "events", "mountain-passes", "alerts", "summary",
    ])
    parser.add_argument(
        "--layer", "-l",
        default="roadReports",
        metavar="SLUG",
        help="Layer slug for the 'events' command (default: roadReports)",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        metavar="N",
        help="Maximum results to display (default: 20)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Filter to active cameras / open rest areas only",
    )
    parser.add_argument(
        "--statewide",
        action="store_true",
        default=True,
        help="Use Colorado statewide bounding box (default)",
    )
    parser.add_argument(
        "--north", type=float, default=_CO_BBOX["north"],
        help="Bounding box north (default: Colorado)")
    parser.add_argument(
        "--south", type=float, default=_CO_BBOX["south"],
        help="Bounding box south (default: Colorado)")
    parser.add_argument(
        "--east", type=float, default=_CO_BBOX["east"],
        help="Bounding box east (default: Colorado)")
    parser.add_argument(
        "--west", type=float, default=_CO_BBOX["west"],
        help="Bounding box west (default: Colorado)")
    parser.add_argument(
        "--zoom", "-z",
        type=int,
        default=_STATEWIDE_ZOOM,
        help=f"Map zoom level for event queries (default: {_STATEWIDE_ZOOM})",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=_DEFAULT_TIMEOUT,
        help=f"HTTP timeout in seconds (default: {_DEFAULT_TIMEOUT})",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = _build_parser()
    args   = parser.parse_args(argv)
    client = CDOTClient(timeout=args.timeout)

    bbox_kwargs = dict(
        north=args.north,
        south=args.south,
        east=args.east,
        west=args.west,
        zoom=args.zoom,
    )

    try:
        if args.command == "cameras":
            data = client.get_cameras(active_only=args.active_only)
            if args.json:
                print(json.dumps([asdict(c) for c in data], indent=2))
            else:
                _print_cameras(data, args.limit)

        elif args.command == "signs":
            data = client.get_signs(displaying_only=args.active_only)
            if args.json:
                print(json.dumps([asdict(s) for s in data], indent=2))
            else:
                _print_signs(data, args.limit)

        elif args.command == "weather-stations":
            data = client.get_weather_stations()
            if args.json:
                print(json.dumps([asdict(s) for s in data], indent=2))
            else:
                _print_weather_stations(data, args.limit)

        elif args.command == "rest-areas":
            data = client.get_rest_areas(open_only=args.active_only)
            if args.json:
                print(json.dumps([asdict(a) for a in data], indent=2))
            else:
                _print_rest_areas(data, args.limit)

        elif args.command == "plows":
            data = client.get_plows()
            if args.json:
                print(json.dumps([asdict(p) for p in data], indent=2))
            else:
                _print_plows(data, args.limit)

        elif args.command == "events":
            if args.layer not in LAYER_SLUGS:
                print(
                    f"Unknown layer '{args.layer}'. Valid slugs:\n"
                    + "\n".join(f"  {s}" for s in LAYER_SLUGS),
                    file=sys.stderr,
                )
                return 1
            data = client.get_events(args.layer, **bbox_kwargs)
            if args.json:
                print(json.dumps([asdict(f) for f in data], indent=2))
            else:
                label = LAYER_SLUGS.get(args.layer, args.layer)
                _print_features(data, label, args.limit)

        elif args.command == "mountain-passes":
            data = client.get_mountain_passes(**bbox_kwargs)
            if args.json:
                print(json.dumps([asdict(f) for f in data], indent=2))
            else:
                _print_features(data, "Mountain Passes", args.limit)

        elif args.command == "alerts":
            data = client.get_travel_alerts()
            if args.json:
                print(json.dumps([asdict(a) for a in data], indent=2))
            else:
                _print_alerts(data)

        elif args.command == "summary":
            summary = client.statewide_summary()
            if args.json:
                print(json.dumps(summary, indent=2))
            else:
                _print_summary(summary)

    except CDOTAPIError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
