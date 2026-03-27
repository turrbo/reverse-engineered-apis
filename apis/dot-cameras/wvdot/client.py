"""
WVDOT Traffic Camera API Client
West Virginia Department of Transportation - 511WV System
https://www.wv511.org

Reverse engineered from the 511WV web application.
Uses stdlib only: urllib, json, html, re, xml.etree.ElementTree, dataclasses.

Discovered endpoints:
  - GET /wsvc/gmap.asmx/buildCamerasJSONjs      → JS file with camera_data JSON variable
  - GET /wsvc/gmap.asmx/buildEventsKMLc          → KML: construction/planned events
  - GET /wsvc/gmap.asmx/buildEventsKMLi_Filtered → KML: incidents (filtered by CategoryIDs)
  - GET /wsvc/gmap.asmx/buildEventsKMLs          → KML: special events
  - GET /wsvc/gmap.asmx/buildDMSKML              → KML: dynamic message signs (isActive=0|1)
  - GET /wsvc/gmap.asmx/buildWeatherKML          → KML: county weather forecasts
  - GET /wsvc/gmap.asmx/buildWeatherAlertsKML    → KML: weather alerts
  - GET /wsvc/gmap.asmx/buildWinterRCPolysKML    → KML: winter road conditions polygons
  - GET /wsvc/gmap.asmx/buildRwisKML             → KML: RWIS (road weather info stations)
  - GET /wsvc/gmap.asmx/buildFacilitiesFilteredKML?TypesCSV=RA → KML: rest areas
  - GET /wsvc/gmap.asmx/buildFacilitiesFilteredKML?TypesCSV=IC → KML: welcome/info centers
  - GET /wsvc/gmap.asmx/buildParkRideKML         → KML: park & ride lots
  - GET /wsvc/gmap.asmx/buildTruckWeighStationsKML   → KML: weigh stations
  - GET /wsvc/gmap.asmx/buildTruckParkingStationsKML → KML: truck parking
  - GET /wsvc/gmap.asmx/buildTruckRunawayRampsKML    → KML: runaway truck ramps
  - GET /wsvc/gmap.asmx/buildTruckSteepGradesKML     → KML: steep grades
  - GET /wsvc/gmap.asmx/buildTollBoothsKML       → KML: toll booths
  - GET /wsvc/gmap.asmx/buildPlannedEventsActiveKML  → KML: currently active planned events
  - GET /wsvc/gmap.asmx/buildPlannedEventsFutureKML  → KML: future planned events
  - GET /wsvc/gmap.asmx/buildRoutePolysClosedKML     → KML: closed road polygons
  - GET /wsvc/gmap.asmx/buildRoutePolysRestrictionsKML → KML: restriction polygons
  - GET /wsvc/gmap.asmx/GetWazeAlertsByTypesGeoJSON  → GeoJSON: Waze crowd-source alerts
  - GET /wsvc/gmap.asmx/GetAltFuelStationsByEvConnectorTypesGeoJSON → GeoJSON: EV charging
  - GET /flowplayeri.aspx?CAMID={id}             → HTML player page (reveals HLS stream URL)
  - HLS stream: https://vtc1.roadsummary.com/rtplive/{CAM_ID}/playlist.m3u8

Auth: None required for data endpoints. All public.
Cache-busting: nocache= query param (use current timestamp or date string).
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


BASE_URL = "https://www.wv511.org"
STREAM_BASE_URL = "https://vtc1.roadsummary.com/rtplive"

# KML namespace used in all 511WV KML documents
KML_NS = "{https://www.opengis.net/kml/2.2}"

# Default User-Agent to identify requests
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; WVDOT-PythonClient/1.0; "
    "+https://github.com/example/wvdot_client)"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """A single traffic camera on the 511WV system."""
    cam_id: str          # e.g. "CAM117"
    origin: str          # internal database key
    title: str           # road name, e.g. "I-81"
    description_raw: str # HTML-encoded description from the JSON payload
    lat: float
    lng: float
    icon: str            # icon style: "icon_feed", "icon_dead", "icon_gens", etc.
    ev_radius: Optional[float]

    # Derived (populated by from_dict)
    location_label: str = ""   # human text, e.g. "[BER]I-81 @ 0.5"
    is_streaming: bool = True  # True when STREAMING:1 comment present

    @property
    def hls_url(self) -> str:
        """HLS (m3u8) stream URL for this camera."""
        return f"{STREAM_BASE_URL}/{self.cam_id}/playlist.m3u8"

    @property
    def player_url(self) -> str:
        """URL of the embedded HTML5 player page."""
        return f"{BASE_URL}/flowplayeri.aspx?CAMID={self.cam_id}"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Camera":
        desc_decoded = html.unescape(d.get("description", ""))

        # Extract the human-readable location label from the camDescription div
        label_m = re.search(
            r'<div id="camDescription">(.*?)</div>', desc_decoded, re.DOTALL
        )
        if label_m:
            # Strip inner HTML tags
            location_label = re.sub(r"<[^>]+>", "", label_m.group(1)).strip()
        else:
            location_label = d.get("title", "")

        streaming = "STREAMING:1" in desc_decoded

        return cls(
            cam_id=d["md5"],
            origin=d.get("origin", ""),
            title=d.get("title", ""),
            description_raw=d.get("description", ""),
            lat=float(d.get("start_lat", 0)),
            lng=float(d.get("start_lng", 0)),
            icon=d.get("icon", ""),
            ev_radius=d.get("ev_radius"),
            location_label=location_label,
            is_streaming=streaming,
        )

    def __repr__(self) -> str:
        return (
            f"Camera(id={self.cam_id!r}, title={self.title!r}, "
            f"location={self.location_label!r}, lat={self.lat}, lng={self.lng}, "
            f"streaming={self.is_streaming})"
        )


@dataclass
class KmlPlacemark:
    """Generic placemark parsed from any KML endpoint."""
    placemark_id: str
    name: str
    description: str
    lat: float
    lng: float
    style_url: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"KmlPlacemark(id={self.placemark_id!r}, name={self.name!r}, "
            f"lat={self.lat}, lng={self.lng})"
        )


@dataclass
class GeoJsonFeature:
    """A single feature from a GeoJSON FeatureCollection."""
    feature_id: Optional[str]
    geometry_type: str
    coordinates: Any
    properties: Dict[str, Any]

    def __repr__(self) -> str:
        name = self.properties.get("name") or self.properties.get("title") or self.feature_id
        return f"GeoJsonFeature(id={self.feature_id!r}, name={name!r})"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> bytes:
    """Perform a GET request and return raw bytes. Raises on HTTP errors."""
    req_headers = {"User-Agent": DEFAULT_UA}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"URL error fetching {url}: {exc.reason}") from exc


def _nocache() -> str:
    """Return a cache-busting string (current UTC timestamp as integer)."""
    return str(int(time.time()))


# ---------------------------------------------------------------------------
# Camera functions
# ---------------------------------------------------------------------------

def _parse_cameras_js(js_text: str) -> Dict[str, List[Camera]]:
    """
    Parse the JavaScript response from /wsvc/gmap.asmx/buildCamerasJSONjs.

    The response embeds two JS variable assignments:
        var camera_data = { "count": N, "cams": [...] };
        var camera_data_ptc = { "count": N, "cams": [...] };

    Returns a dict with keys "cameras" and "cameras_ptc".
    """
    result: Dict[str, List[Camera]] = {"cameras": [], "cameras_ptc": []}

    for var_name, key in [("camera_data", "cameras"), ("camera_data_ptc", "cameras_ptc")]:
        pattern = f"var {var_name} = "
        idx = js_text.find(pattern)
        if idx < 0:
            continue
        start = idx + len(pattern)
        # Walk matching braces to find the end of the JSON object
        depth = 0
        end = start
        for i, ch in enumerate(js_text[start:]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
        try:
            data = json.loads(js_text[start:end])
            result[key] = [Camera.from_dict(c) for c in data.get("cams", [])]
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # leave empty on parse failure

    return result


def get_cameras(timeout: int = 30) -> List[Camera]:
    """
    Fetch all WVDOT traffic cameras.

    Calls GET /wsvc/gmap.asmx/buildCamerasJSONjs which returns a JavaScript
    file containing two JSON variable assignments (camera_data and
    camera_data_ptc). Both sets are merged and returned.

    Returns:
        List of Camera objects sorted by cam_id.
    """
    url = f"{BASE_URL}/wsvc/gmap.asmx/buildCamerasJSONjs"
    raw = _get(url, timeout=timeout)
    js_text = raw.decode("utf-8", errors="replace")
    parsed = _parse_cameras_js(js_text)
    all_cams = parsed["cameras"] + parsed["cameras_ptc"]
    return sorted(all_cams, key=lambda c: c.cam_id)


def get_camera_stream_url(cam_id: str, timeout: int = 15) -> Optional[str]:
    """
    Fetch the camera player page and extract the live HLS stream URL.

    The player page at /flowplayeri.aspx?CAMID={cam_id} embeds:
        hls.loadSource('https://vtc1.roadsummary.com/rtplive/{CAM_ID}/playlist.m3u8');

    This function confirms the URL by fetching the player page and parsing it.
    If the player page can't be fetched, it returns the canonical URL pattern
    anyway (constructed without a network call).

    Args:
        cam_id: Camera identifier, e.g. "CAM117".
        timeout: HTTP timeout in seconds.

    Returns:
        HLS m3u8 URL string, or None if the camera is not streaming.
    """
    url = f"{BASE_URL}/flowplayeri.aspx?CAMID={cam_id}"
    try:
        raw = _get(url, timeout=timeout)
        page = raw.decode("utf-8", errors="replace")
        m = re.search(r"hls\.loadSource\('([^']+)'\)", page)
        if m:
            return m.group(1)
        # Fallback: check <source> tag
        m2 = re.search(r'<source[^>]+src="([^"]+playlist\.m3u8[^"]*)"', page)
        if m2:
            return m2.group(1)
    except RuntimeError:
        pass
    # Return canonical URL pattern even if page fetch failed
    return f"{STREAM_BASE_URL}/{cam_id}/playlist.m3u8"


# ---------------------------------------------------------------------------
# KML parsing
# ---------------------------------------------------------------------------

def _parse_kml(kml_bytes: bytes) -> List[KmlPlacemark]:
    """
    Parse a KML document and return a list of KmlPlacemark objects.

    Handles the KML namespace used by 511WV:
        https://www.opengis.net/kml/2.2
    """
    try:
        root = ET.fromstring(kml_bytes)
    except ET.ParseError:
        # Some responses embed HTML before the XML; try to strip it
        text = kml_bytes.decode("utf-8", errors="replace")
        xml_start = text.find("<?xml")
        if xml_start > 0:
            try:
                root = ET.fromstring(text[xml_start:].encode("utf-8"))
            except ET.ParseError:
                return []
        else:
            return []

    ns = KML_NS
    placemarks = []

    for pm in root.iter(f"{ns}Placemark"):
        pm_id = pm.get("id", "")
        name_el = pm.find(f"{ns}name")
        desc_el = pm.find(f"{ns}description")
        style_el = pm.find(f"{ns}styleUrl")
        coords_el = pm.find(f".//{ns}coordinates")

        name = (name_el.text or "").strip() if name_el is not None else ""
        description = (desc_el.text or "").strip() if desc_el is not None else ""
        style_url = (style_el.text or "").strip() if style_el is not None else ""

        lat, lng = 0.0, 0.0
        if coords_el is not None and coords_el.text:
            parts = coords_el.text.strip().split(",")
            if len(parts) >= 2:
                try:
                    lng = float(parts[0])
                    lat = float(parts[1])
                except ValueError:
                    pass

        # Extract ExtendedData key/value pairs
        extra: Dict[str, str] = {}
        for data_el in pm.findall(f".//{ns}Data"):
            k = data_el.get("name", "")
            v_el = data_el.find(f"{ns}value")
            v = (v_el.text or "").strip() if v_el is not None else ""
            if k:
                extra[k] = v

        placemarks.append(KmlPlacemark(
            placemark_id=pm_id,
            name=name,
            description=description,
            lat=lat,
            lng=lng,
            style_url=style_url,
            extra=extra,
        ))

    return placemarks


# ---------------------------------------------------------------------------
# KML endpoint functions
# ---------------------------------------------------------------------------

def _fetch_kml(path: str, extra_params: Optional[Dict[str, str]] = None,
               timeout: int = 30) -> List[KmlPlacemark]:
    """Internal helper to fetch and parse a KML endpoint."""
    params: Dict[str, str] = {"nocache": _nocache()}
    if extra_params:
        params.update(extra_params)
    qs = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{path}?{qs}"
    raw = _get(url, timeout=timeout)
    return _parse_kml(raw)


def get_construction_events(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch current construction and planned events (construction category).

    Endpoint: GET /wsvc/gmap.asmx/buildEventsKMLc
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildEventsKMLc", timeout=timeout)


def get_incident_events(category_ids: str = "", timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch traffic incidents, optionally filtered by category IDs.

    Endpoint: GET /wsvc/gmap.asmx/buildEventsKMLi_Filtered?CategoryIDs={ids}

    Args:
        category_ids: Comma-separated category ID string. Pass empty string
                      to retrieve all incident categories.
    """
    return _fetch_kml(
        "/wsvc/gmap.asmx/buildEventsKMLi_Filtered",
        extra_params={"CategoryIDs": category_ids},
        timeout=timeout,
    )


def get_special_events(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch special events (sporting events, concerts, etc.).

    Endpoint: GET /wsvc/gmap.asmx/buildEventsKMLs
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildEventsKMLs", timeout=timeout)


def get_active_planned_events(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch planned events that are currently active.

    Endpoint: GET /wsvc/gmap.asmx/buildPlannedEventsActiveKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildPlannedEventsActiveKML", timeout=timeout)


def get_future_planned_events(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch planned events scheduled for the future.

    Endpoint: GET /wsvc/gmap.asmx/buildPlannedEventsFutureKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildPlannedEventsFutureKML", timeout=timeout)


def get_dms_signs(active_only: bool = True, timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch Dynamic Message Signs (electronic highway signs).

    Endpoint: GET /wsvc/gmap.asmx/buildDMSKML?isActive=1

    Args:
        active_only: If True, return only signs currently displaying a message.
                     If False, return all signs including blank/inactive ones.
    """
    return _fetch_kml(
        "/wsvc/gmap.asmx/buildDMSKML",
        extra_params={"isActive": "1" if active_only else "0"},
        timeout=timeout,
    )


def get_weather_forecasts(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch county-level weather forecasts.

    Endpoint: GET /wsvc/gmap.asmx/buildWeatherKML

    Each placemark represents one WV county. The description contains an
    HTML table with 7-day forecast icons and temperatures sourced from
    api.weather.gov.
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildWeatherKML", timeout=timeout)


def get_weather_alerts(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch active NWS weather alerts for West Virginia.

    Endpoint: GET /wsvc/gmap.asmx/buildWeatherAlertsKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildWeatherAlertsKML", timeout=timeout)


def get_winter_road_conditions(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch winter road condition polygon data.

    Endpoint: GET /wsvc/gmap.asmx/buildWinterRCPolysKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildWinterRCPolysKML", timeout=timeout)


def get_rwis_stations(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch Road Weather Information System (RWIS) station data.

    RWIS stations report pavement temperature, air temperature, wind speed,
    and other environmental conditions.

    Endpoint: GET /wsvc/gmap.asmx/buildRwisKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildRwisKML", timeout=timeout)


def get_rest_areas(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch rest area locations.

    Endpoint: GET /wsvc/gmap.asmx/buildFacilitiesFilteredKML?TypesCSV=RA
    """
    return _fetch_kml(
        "/wsvc/gmap.asmx/buildFacilitiesFilteredKML",
        extra_params={"TypesCSV": "RA"},
        timeout=timeout,
    )


def get_welcome_centers(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch welcome center / visitor information center locations.

    Endpoint: GET /wsvc/gmap.asmx/buildFacilitiesFilteredKML?TypesCSV=IC
    """
    return _fetch_kml(
        "/wsvc/gmap.asmx/buildFacilitiesFilteredKML",
        extra_params={"TypesCSV": "IC"},
        timeout=timeout,
    )


def get_park_and_ride(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch park & ride lot locations.

    Endpoint: GET /wsvc/gmap.asmx/buildParkRideKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildParkRideKML", timeout=timeout)


def get_toll_booths(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch toll booth locations.

    Endpoint: GET /wsvc/gmap.asmx/buildTollBoothsKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildTollBoothsKML", timeout=timeout)


def get_weigh_stations(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch truck weigh station locations.

    Endpoint: GET /wsvc/gmap.asmx/buildTruckWeighStationsKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildTruckWeighStationsKML", timeout=timeout)


def get_truck_parking(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch truck parking station locations.

    Endpoint: GET /wsvc/gmap.asmx/buildTruckParkingStationsKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildTruckParkingStationsKML", timeout=timeout)


def get_runaway_truck_ramps(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch runaway truck ramp locations.

    Endpoint: GET /wsvc/gmap.asmx/buildTruckRunawayRampsKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildTruckRunawayRampsKML", timeout=timeout)


def get_steep_grades(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch steep grade locations (commercial vehicle warnings).

    Endpoint: GET /wsvc/gmap.asmx/buildTruckSteepGradesKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildTruckSteepGradesKML", timeout=timeout)


def get_road_closures(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch road closure polygon data.

    Endpoint: GET /wsvc/gmap.asmx/buildRoutePolysClosedKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildRoutePolysClosedKML", timeout=timeout)


def get_road_restrictions(timeout: int = 30) -> List[KmlPlacemark]:
    """
    Fetch road restriction polygon data (weight limits, height limits, etc.).

    Endpoint: GET /wsvc/gmap.asmx/buildRoutePolysRestrictionsKML
    """
    return _fetch_kml("/wsvc/gmap.asmx/buildRoutePolysRestrictionsKML", timeout=timeout)


# ---------------------------------------------------------------------------
# GeoJSON endpoint functions
# ---------------------------------------------------------------------------

def _parse_geojson_features(raw: bytes) -> List[GeoJsonFeature]:
    """Parse a GeoJSON FeatureCollection into a list of GeoJsonFeature objects."""
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []

    features = []
    for f in data.get("features", []):
        geom = f.get("geometry") or {}
        features.append(GeoJsonFeature(
            feature_id=f.get("id"),
            geometry_type=geom.get("type", ""),
            coordinates=geom.get("coordinates"),
            properties=f.get("properties") or {},
        ))
    return features


def get_waze_alerts(types_bitmask: int = 65535, timeout: int = 30) -> List[GeoJsonFeature]:
    """
    Fetch Waze crowd-sourced traffic alerts as GeoJSON features.

    Endpoint: GET /wsvc/gmap.asmx/GetWazeAlertsByTypesGeoJSON?WazeTypesBitmask={mask}

    Args:
        types_bitmask: Bitmask controlling which alert types to include.
                       65535 (0xFFFF) returns all types.
    """
    url = (
        f"{BASE_URL}/wsvc/gmap.asmx/GetWazeAlertsByTypesGeoJSON"
        f"?WazeTypesBitmask={types_bitmask}"
    )
    raw = _get(url, timeout=timeout)
    return _parse_geojson_features(raw)


def get_ev_charging_stations(connector_bitmask: int = 255, timeout: int = 30) -> List[GeoJsonFeature]:
    """
    Fetch Electric Vehicle (EV) charging station locations as GeoJSON features.

    Endpoint: GET /wsvc/gmap.asmx/GetAltFuelStationsByEvConnectorTypesGeoJSON?ConnectorTypesBitmask={mask}

    Args:
        connector_bitmask: Bitmask of EV connector types to include.
                           255 (0xFF) returns all connector types.
    """
    url = (
        f"{BASE_URL}/wsvc/gmap.asmx/GetAltFuelStationsByEvConnectorTypesGeoJSON"
        f"?ConnectorTypesBitmask={connector_bitmask}"
    )
    raw = _get(url, timeout=timeout)
    return _parse_geojson_features(raw)


# ---------------------------------------------------------------------------
# High-level convenience client class
# ---------------------------------------------------------------------------

class WVDOTClient:
    """
    High-level client for the 511WV (WVDOT) traffic data API.

    Usage::

        client = WVDOTClient()

        # List all cameras
        cameras = client.cameras()
        for cam in cameras[:5]:
            print(cam)

        # Get HLS stream URL for a camera
        url = client.camera_stream_url("CAM117")
        print(url)

        # Get active construction events
        events = client.construction_events()
        for ev in events:
            print(ev.name, ev.description[:80])

        # Get weather forecasts by county
        forecasts = client.weather_forecasts()
        for f in forecasts[:3]:
            print(f.name)

    All methods accept an optional ``timeout`` keyword argument (seconds).
    """

    def __init__(self, timeout: int = 30):
        self.default_timeout = timeout

    def cameras(self) -> List[Camera]:
        """Return all traffic cameras (sorted by cam_id)."""
        return get_cameras(timeout=self.default_timeout)

    def camera_stream_url(self, cam_id: str) -> Optional[str]:
        """Return the HLS stream URL for a camera, confirmed from the player page."""
        return get_camera_stream_url(cam_id, timeout=self.default_timeout)

    def construction_events(self) -> List[KmlPlacemark]:
        """Return active construction events."""
        return get_construction_events(timeout=self.default_timeout)

    def incident_events(self, category_ids: str = "") -> List[KmlPlacemark]:
        """Return traffic incidents, optionally filtered."""
        return get_incident_events(category_ids, timeout=self.default_timeout)

    def special_events(self) -> List[KmlPlacemark]:
        """Return special events."""
        return get_special_events(timeout=self.default_timeout)

    def active_planned_events(self) -> List[KmlPlacemark]:
        """Return currently active planned events."""
        return get_active_planned_events(timeout=self.default_timeout)

    def future_planned_events(self) -> List[KmlPlacemark]:
        """Return future planned events."""
        return get_future_planned_events(timeout=self.default_timeout)

    def dms_signs(self, active_only: bool = True) -> List[KmlPlacemark]:
        """Return dynamic message signs."""
        return get_dms_signs(active_only, timeout=self.default_timeout)

    def weather_forecasts(self) -> List[KmlPlacemark]:
        """Return county-level 7-day weather forecasts."""
        return get_weather_forecasts(timeout=self.default_timeout)

    def weather_alerts(self) -> List[KmlPlacemark]:
        """Return active NWS weather alerts."""
        return get_weather_alerts(timeout=self.default_timeout)

    def winter_road_conditions(self) -> List[KmlPlacemark]:
        """Return winter road condition data."""
        return get_winter_road_conditions(timeout=self.default_timeout)

    def rwis_stations(self) -> List[KmlPlacemark]:
        """Return RWIS road weather station data."""
        return get_rwis_stations(timeout=self.default_timeout)

    def rest_areas(self) -> List[KmlPlacemark]:
        """Return rest area locations."""
        return get_rest_areas(timeout=self.default_timeout)

    def welcome_centers(self) -> List[KmlPlacemark]:
        """Return welcome center locations."""
        return get_welcome_centers(timeout=self.default_timeout)

    def park_and_ride(self) -> List[KmlPlacemark]:
        """Return park & ride lot locations."""
        return get_park_and_ride(timeout=self.default_timeout)

    def toll_booths(self) -> List[KmlPlacemark]:
        """Return toll booth locations."""
        return get_toll_booths(timeout=self.default_timeout)

    def weigh_stations(self) -> List[KmlPlacemark]:
        """Return truck weigh station locations."""
        return get_weigh_stations(timeout=self.default_timeout)

    def truck_parking(self) -> List[KmlPlacemark]:
        """Return truck parking locations."""
        return get_truck_parking(timeout=self.default_timeout)

    def runaway_truck_ramps(self) -> List[KmlPlacemark]:
        """Return runaway truck ramp locations."""
        return get_runaway_truck_ramps(timeout=self.default_timeout)

    def steep_grades(self) -> List[KmlPlacemark]:
        """Return steep grade locations."""
        return get_steep_grades(timeout=self.default_timeout)

    def road_closures(self) -> List[KmlPlacemark]:
        """Return road closure areas."""
        return get_road_closures(timeout=self.default_timeout)

    def road_restrictions(self) -> List[KmlPlacemark]:
        """Return road restriction areas."""
        return get_road_restrictions(timeout=self.default_timeout)

    def waze_alerts(self, types_bitmask: int = 65535) -> List[GeoJsonFeature]:
        """Return Waze crowd-sourced alerts."""
        return get_waze_alerts(types_bitmask, timeout=self.default_timeout)

    def ev_charging_stations(self, connector_bitmask: int = 255) -> List[GeoJsonFeature]:
        """Return EV charging station locations."""
        return get_ev_charging_stations(connector_bitmask, timeout=self.default_timeout)


# ---------------------------------------------------------------------------
# CLI / smoke test
# ---------------------------------------------------------------------------

def _run_smoke_test() -> None:
    """Quick smoke test that exercises the major endpoints."""
    client = WVDOTClient(timeout=20)

    print("=" * 60)
    print("WVDOT 511WV API Smoke Test")
    print("=" * 60)

    # --- Cameras ---
    print("\n[1] Traffic Cameras")
    cams = client.cameras()
    print(f"  Total cameras found: {len(cams)}")
    if cams:
        for cam in cams[:3]:
            print(f"  {cam}")
        # Show stream URL for the first camera
        first = cams[0]
        stream = client.camera_stream_url(first.cam_id)
        print(f"\n  HLS stream for {first.cam_id}: {stream}")

    # --- Construction events ---
    print("\n[2] Construction Events")
    events = client.construction_events()
    print(f"  Total events: {len(events)}")
    for ev in events[:3]:
        print(f"  {ev.name} — {ev.description[:80]}...")

    # --- DMS Signs ---
    print("\n[3] Active DMS Signs")
    signs = client.dms_signs(active_only=True)
    print(f"  Active signs: {len(signs)}")
    for s in signs[:3]:
        print(f"  {s}")

    # --- Weather ---
    print("\n[4] County Weather Forecasts")
    wx = client.weather_forecasts()
    print(f"  Counties with forecasts: {len(wx)}")
    for w in wx[:3]:
        print(f"  {w.name} ({w.lat:.4f}, {w.lng:.4f})")

    # --- Weather alerts ---
    print("\n[5] Weather Alerts")
    alerts = client.weather_alerts()
    print(f"  Active alerts: {len(alerts)}")

    # --- Rest areas ---
    print("\n[6] Rest Areas")
    ras = client.rest_areas()
    print(f"  Rest areas: {len(ras)}")
    for r in ras[:3]:
        print(f"  {r}")

    # --- Waze alerts ---
    print("\n[7] Waze Alerts (GeoJSON)")
    waze = client.waze_alerts()
    print(f"  Waze alert features: {len(waze)}")
    for w in waze[:3]:
        print(f"  {w}")

    print("\n" + "=" * 60)
    print("Smoke test complete.")
    print("=" * 60)


if __name__ == "__main__":
    _run_smoke_test()
