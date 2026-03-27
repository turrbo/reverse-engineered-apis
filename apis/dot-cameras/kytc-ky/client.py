"""
KYTC Traffic Camera & Incident Client
=====================================
Reverse-engineered from https://goky.ky.gov (GoKY - Kentucky Transportation Cabinet)

Data sources:
  1. ArcGIS FeatureServer  - Statewide KYTC traffic cameras (255 cameras)
  2. ArcGIS FeatureServer  - Fayette County (Lexington) cameras (108 cameras, Trimarc)
  3. Firebase Firestore     - Real-time traffic feed (incidents, speed, DMS, work zones, weather)

No authentication required - all endpoints are public.

Stdlib only: urllib, json, dataclasses, typing, datetime, enum
"""

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum


# ---------------------------------------------------------------------------
# Configuration (extracted from goky.ky.gov/index.js)
# ---------------------------------------------------------------------------

ARCGIS_KYTC_URL = (
    "https://services2.arcgis.com/CcI36Pduqd0OR4W9/ArcGIS/rest/services/"
    "trafficCamerasCur_Prd/FeatureServer/0/query"
)

ARCGIS_FAYETTE_URL = (
    "https://services1.arcgis.com/Mg7DLdfYcSWIaDnu/ArcGIS/rest/services/"
    "Traffic_Camera_Locations_Public_view/FeatureServer/0/query"
)

# Firebase project ID (from JS bundle)
FIREBASE_PROJECT = "kytc-goky"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/"
    "databases/(default)/documents"
)

# ObjectSpectrum RWIS weather camera viewer (embedded token from JS bundle)
RWIS_TOKEN = "c35886bf-9b98-4be0-b2ec-7781fdf1d90d"
RWIS_BASE_URL = (
    f"https://api.objectspectrum.com/apps/vue/report:latest"
    f"?token={RWIS_TOKEN}&timezone=America/New_York&scope=vue_kdt1&camera_key="
)

# Google Maps API key (from goky.ky.gov HTML, same as Firebase apiKey)
GOOGLE_MAPS_KEY = "AIzaSyDQEp-IWOnOoZtAH0SnMPfZnEMToDmMNcQ"

DEFAULT_TIMEOUT = 30
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; KYTCClient/1.0)"


# ---------------------------------------------------------------------------
# Feed / Event type enumeration
# ---------------------------------------------------------------------------

class FeedType(str, Enum):
    """All feed/event types in the GoKY realtime Firestore collection."""
    CRASH        = "crsh"      # KYTC/TRIMARC crash incidents
    HAZARD       = "hzrd"      # Road hazard alerts
    WORKZONE     = "wkzn"      # Active work zones
    WEATHER      = "wthr"      # Weather alerts
    SPEED        = "spd"       # Traffic speed data (HERE)
    RWIS         = "rwis"      # Roadway Weather Information Station
    WZ_CRASH     = "wzcrsh"    # Waze-reported crash
    WZ_TRAFFIC   = "wztrfc"    # Waze traffic jam
    WZ_HAZARD    = "wzhzrd"    # Waze hazard
    WZ_WORKZONE  = "wzwk"      # Waze work zone
    DMS          = "dms"       # Dynamic Message Sign (electronic road sign)
    CAMERA       = "camera"    # Traffic camera (static, loaded from ArcGIS)
    SNOW_ICE     = "snic"      # Snow & ice operations
    FERRY        = "fry"       # Ferry status
    TRUCK_PARK   = "trkprk"    # Truck parking availability
    REST_AREA    = "rsta"      # Rest area status
    WEIGH_STATION = "wstn"     # Weigh station
    DISTRICT_OFFICE = "dsto"   # KYTC district office
    DRV_LICENSE  = "rglo"      # Regional driver license office
    FAYETTE      = "fayette"   # Fayette County camera source tag


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TrafficCamera:
    """A KYTC or Fayette County traffic camera."""
    source: str                    # "kytc" or "fayette"
    description: str               # Human-readable location description
    snapshot_url: str              # Direct URL to JPEG snapshot image
    latitude: float
    longitude: float
    name: Optional[str] = None     # CCTV ID (e.g. "CCTV05039")
    county: Optional[str] = None
    highway: Optional[str] = None
    milemarker: Optional[float] = None
    direction: Optional[str] = None
    status: Optional[str] = None   # "Online", "Offline", None
    state: Optional[str] = None
    district: Optional[int] = None
    update_ts: Optional[datetime] = None

    @property
    def is_online(self) -> bool:
        return self.status != "Offline"

    def __repr__(self) -> str:
        return (
            f"TrafficCamera(name={self.name!r}, description={self.description!r}, "
            f"county={self.county!r}, status={self.status!r})"
        )


@dataclass
class GeoPoint:
    latitude: float
    longitude: float

    def __repr__(self) -> str:
        return f"GeoPoint({self.latitude:.6f}, {self.longitude:.6f})"


@dataclass
class RealtimeEvent:
    """A real-time traffic event from Firestore (incident, speed, DMS, etc.)."""
    doc_id: str
    event_type: str               # FeedType value string (e.g. "crsh", "spd")
    county: Optional[str]
    location: Optional[GeoPoint]
    display: Dict[str, Any]       # Flat dict with display fields
    source: Dict[str, Any]        # Flat dict with source/raw data fields
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def feed_type(self) -> Optional[FeedType]:
        try:
            return FeedType(self.event_type)
        except ValueError:
            return None

    @property
    def route(self) -> Optional[str]:
        return self.display.get("Route")

    @property
    def mile_point(self) -> Optional[float]:
        mp = self.display.get("Mile_Point")
        if mp is None:
            return None
        try:
            return float(mp)
        except (TypeError, ValueError):
            return None

    @property
    def road_name(self) -> Optional[str]:
        return self.display.get("Road_Name")

    @property
    def description(self) -> Optional[str]:
        return self.source.get("description")

    @property
    def source_id(self) -> Optional[str]:
        return self.source.get("id")

    @property
    def published(self) -> Optional[datetime]:
        ts = self.source.get("published")
        if ts:
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        return None

    def __repr__(self) -> str:
        return (
            f"RealtimeEvent(type={self.event_type!r}, county={self.county!r}, "
            f"route={self.route!r}, mile_point={self.mile_point}, "
            f"road_name={self.road_name!r})"
        )


# ---------------------------------------------------------------------------
# Firestore value deserializer
# ---------------------------------------------------------------------------

def _deserialize_firestore_value(value: Dict[str, Any]) -> Any:
    """Convert a Firestore REST API typed value to a Python native type."""
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "nullValue" in value:
        return None
    if "timestampValue" in value:
        return value["timestampValue"]  # keep as ISO string
    if "geoPointValue" in value:
        gp = value["geoPointValue"]
        return GeoPoint(
            latitude=float(gp.get("latitude", 0)),
            longitude=float(gp.get("longitude", 0)),
        )
    if "mapValue" in value:
        return _deserialize_firestore_fields(value["mapValue"].get("fields", {}))
    if "arrayValue" in value:
        return [
            _deserialize_firestore_value(v)
            for v in value["arrayValue"].get("values", [])
        ]
    return value  # fallback: return raw


def _deserialize_firestore_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Firestore fields map to a plain Python dict."""
    return {k: _deserialize_firestore_value(v) for k, v in fields.items()}


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _fetch(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """
    Fetch a URL and return parsed JSON.
    Raises urllib.error.URLError or json.JSONDecodeError on failure.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw)


def _build_url(base: str, params: Dict[str, str]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


# ---------------------------------------------------------------------------
# Camera feed functions
# ---------------------------------------------------------------------------

def get_kytc_cameras(
    county: Optional[str] = None,
    state: Optional[str] = None,
    status: Optional[str] = None,
    include_geometry: bool = False,
) -> List[TrafficCamera]:
    """
    Fetch all KYTC statewide traffic cameras from ArcGIS FeatureServer.

    Available fields: id, name, status, state, district, county, highway,
    milemarker, description, direction, snapshot, latitude, longitude, updateTS

    Args:
        county:   Filter by county name (e.g. "Jefferson", "Fayette")
        state:    Filter by state (e.g. "Kentucky")
        status:   Filter by status string (e.g. "Online")
        include_geometry: If True, also request ArcGIS geometry (default False)

    Returns:
        List of TrafficCamera dataclass instances.

    Example:
        >>> cameras = get_kytc_cameras(county="Jefferson")
        >>> for cam in cameras[:3]:
        ...     print(cam.name, cam.snapshot_url)
    """
    where_parts = ["1=1"]
    if county:
        where_parts.append(f"county='{county}'")
    if state:
        where_parts.append(f"state='{state}'")
    if status:
        where_parts.append(f"status='{status}'")

    params = {
        "where": " AND ".join(where_parts),
        "outFields": "name,description,snapshot,status,state,district,county,"
                     "highway,milemarker,direction,latitude,longitude,updateTS",
        "returnGeometry": "true" if include_geometry else "false",
        "outSR": "4326",
        "f": "pjson",
    }
    url = _build_url(ARCGIS_KYTC_URL, params)
    data = _fetch(url)
    cameras = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes", {})
        ts_raw = attrs.get("updateTS")
        update_ts = None
        if ts_raw:
            try:
                update_ts = datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                pass
        cam = TrafficCamera(
            source="kytc",
            name=attrs.get("name"),
            description=attrs.get("description") or "",
            snapshot_url=attrs.get("snapshot") or "",
            status=attrs.get("status"),
            state=attrs.get("state"),
            district=attrs.get("district"),
            county=attrs.get("county"),
            highway=attrs.get("highway"),
            milemarker=attrs.get("milemarker"),
            direction=attrs.get("direction"),
            latitude=float(attrs.get("latitude") or 0),
            longitude=float(attrs.get("longitude") or 0),
            update_ts=update_ts,
        )
        cameras.append(cam)
    return cameras


def get_fayette_cameras() -> List[TrafficCamera]:
    """
    Fetch Fayette County (Lexington) traffic cameras from ArcGIS FeatureServer.
    These are operated by Trimarc and use Wowza streaming snapshots.

    Fields: location (description), still_url (snapshot), geometry (x/y)

    Returns:
        List of TrafficCamera dataclass instances with source="fayette".

    Note:
        still_url format:
          https://<streamlock-host>:1935/thumbnail?application=lexington-live
          &streamname=lex-cam-NNN.stream&fitmode=stretch&size=600x400
    """
    params = {
        "where": "1=1",
        "outFields": "location,still_url",
        "outSR": "4326",
        "f": "pjson",
    }
    url = _build_url(ARCGIS_FAYETTE_URL, params)
    data = _fetch(url)
    cameras = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        # Parse stream name from URL for a human-readable name
        still_url = attrs.get("still_url") or ""
        parsed = urllib.parse.urlparse(still_url)
        qs = urllib.parse.parse_qs(parsed.query)
        streamname = qs.get("streamname", [""])[0]
        cam_id = streamname.split(".")[0].upper() if streamname else "LEX-CAM"
        cam = TrafficCamera(
            source="fayette",
            name=cam_id,
            description=attrs.get("location") or "",
            snapshot_url=still_url,
            county="Fayette",
            latitude=float(geom.get("y") or 0),
            longitude=float(geom.get("x") or 0),
        )
        cameras.append(cam)
    return cameras


def get_all_cameras(ky_only: bool = True) -> List[TrafficCamera]:
    """
    Convenience function: fetch cameras from both KYTC and Fayette sources.

    Args:
        ky_only: If True (default), only return cameras where state=Kentucky
                 from the KYTC feed; Indiana border cameras are excluded.

    Returns:
        Combined list of TrafficCamera objects (KYTC + Fayette).
    """
    state_filter = "Kentucky" if ky_only else None
    kytc = get_kytc_cameras(state=state_filter)
    fayette = get_fayette_cameras()
    return kytc + fayette


# ---------------------------------------------------------------------------
# Firestore real-time feed functions
# ---------------------------------------------------------------------------

def _parse_realtime_doc(doc: Dict[str, Any]) -> RealtimeEvent:
    """Convert a raw Firestore REST document to a RealtimeEvent."""
    doc_id = doc["name"].split("/")[-1]
    fields = doc.get("fields", {})
    deserialized = _deserialize_firestore_fields(fields)

    event_type = deserialized.get("type", "unknown")
    county = deserialized.get("county")
    location = deserialized.get("location")  # GeoPoint or None
    display_raw = deserialized.get("display", {})
    source_raw = deserialized.get("source", {})

    # display and source are nested maps in Firestore
    display = display_raw if isinstance(display_raw, dict) else {}
    source = source_raw if isinstance(source_raw, dict) else {}

    return RealtimeEvent(
        doc_id=doc_id,
        event_type=event_type,
        county=county,
        location=location if isinstance(location, GeoPoint) else None,
        display=display,
        source=source,
        raw=deserialized,
    )


def get_realtime_feed(
    event_types: Optional[List[str]] = None,
    county: Optional[str] = None,
    page_size: int = 300,
    max_pages: int = 10,
) -> List[RealtimeEvent]:
    """
    Fetch all real-time traffic events from Firebase Firestore.

    The 'realtime' collection is publicly readable (no auth needed).
    It is updated continuously by KYTC backend services.

    Args:
        event_types: Optional list of type strings to include
                     (e.g. ["crsh", "hzrd", "wkzn"] for incidents only).
                     If None, all types are returned.
        county:      Optional county name filter (client-side).
        page_size:   Number of documents per Firestore page (max 300).
        max_pages:   Maximum number of pages to fetch (safety limit).

    Returns:
        List of RealtimeEvent dataclass instances.

    Feed type reference:
        crsh   - Crash incident
        hzrd   - Road hazard
        wkzn   - Work zone
        wthr   - Weather alert
        spd    - Traffic speed segment (HERE data)
        rwis   - Roadway weather station
        wzcrsh - Waze crash
        wztrfc - Waze traffic jam
        wzhzrd - Waze hazard
        wzwk   - Waze work zone
        dms    - Dynamic message sign
        trkprk - Truck parking
        rsta   - Rest area
        snic   - Snow & ice operations

    Example:
        >>> incidents = get_realtime_feed(event_types=["crsh", "hzrd", "wkzn"])
        >>> for e in incidents:
        ...     print(e.county, e.route, e.mile_point, e.description)
    """
    collection_url = f"{FIRESTORE_BASE}/realtime"
    events = []
    page_token = None

    for _ in range(max_pages):
        params = {"pageSize": str(page_size)}
        if page_token:
            params["pageToken"] = page_token

        url = _build_url(collection_url, params)
        data = _fetch(url)

        for doc in data.get("documents", []):
            evt = _parse_realtime_doc(doc)
            # Filter by type if requested
            if event_types and evt.event_type not in event_types:
                continue
            # Filter by county if requested
            if county and evt.county and evt.county.lower() != county.lower():
                continue
            events.append(evt)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return events


def get_incidents(county: Optional[str] = None) -> List[RealtimeEvent]:
    """
    Fetch active traffic incidents (crashes + hazards + work zones).

    Args:
        county: Optional county name filter.

    Returns:
        List of RealtimeEvent with types: crsh, hzrd, wkzn.
    """
    return get_realtime_feed(
        event_types=[FeedType.CRASH, FeedType.HAZARD, FeedType.WORKZONE],
        county=county,
    )


def get_waze_events(county: Optional[str] = None) -> List[RealtimeEvent]:
    """
    Fetch Waze-sourced traffic events.

    Args:
        county: Optional county name filter.

    Returns:
        List of RealtimeEvent with types: wzcrsh, wzhzrd, wztrfc, wzwk.
    """
    return get_realtime_feed(
        event_types=[
            FeedType.WZ_CRASH,
            FeedType.WZ_HAZARD,
            FeedType.WZ_TRAFFIC,
            FeedType.WZ_WORKZONE,
        ],
        county=county,
    )


def get_speed_data(county: Optional[str] = None) -> List[RealtimeEvent]:
    """
    Fetch real-time traffic speed segments (from HERE Technologies).

    Each event represents a road segment with current and historic speeds.
    Source_Type values: "Heavy Congestion", "Light Congestion", "Unknown", etc.

    Args:
        county: Optional county name filter.

    Returns:
        List of RealtimeEvent with type "spd".

    Display fields available on each event:
        Route           - Road identifier (e.g. "I-264")
        Road_Name       - Road segment name (e.g. "I-264 NC")
        Mile_Point      - Milepost
        Current_Speed   - Current speed (mph)
        Historic_Speed  - Typical/historic speed (mph)
        Source_Type     - Congestion level description
    """
    return get_realtime_feed(event_types=[FeedType.SPEED], county=county)


def get_dms_signs(county: Optional[str] = None) -> List[RealtimeEvent]:
    """
    Fetch Dynamic Message Sign (electronic highway sign) current messages.

    Args:
        county: Optional county name filter.

    Returns:
        List of RealtimeEvent with type "dms".

    Source fields available:
        id       - Sign ID (e.g. "KYTC.DMS11002")
        location - Human-readable location description
        message  - Current message text displayed on sign
        type     - "DMS"
    """
    return get_realtime_feed(event_types=[FeedType.DMS], county=county)


def get_rwis_stations() -> List[RealtimeEvent]:
    """
    Fetch Roadway Weather Information Station (RWIS) sensor data.

    RWIS stations report pavement and air temperatures, dew point, heat index,
    wind, and precipitation. Camera snapshots use the ObjectSpectrum viewer.

    Returns:
        List of RealtimeEvent with type "rwis".

    Display fields vary by station but may include:
        Air_Temp       - Air temperature (e.g. "47.9 F")
        Pavement_Temp  - Pavement temperature
        Dew_Point      - Dew point temperature
        Heat_Index     - Heat index

    Source fields:
        id         - Station identifier
        route      - Road route
        mile_post  - Milepost
        cameraKey  - Key for ObjectSpectrum camera viewer
        imageUrl   - Direct image URL
    """
    return get_realtime_feed(event_types=[FeedType.RWIS])


def get_truck_parking() -> List[RealtimeEvent]:
    """
    Fetch truck parking availability at rest areas along KY interstates.

    Returns:
        List of RealtimeEvent with type "trkprk".

    Source fields:
        description  - Location description
        Route        - Interstate
        Mile_Point   - Milepost
        Direction    - "N" or "S"
        open         - bool, whether parking is open
    """
    return get_realtime_feed(event_types=[FeedType.TRUCK_PARK])


# ---------------------------------------------------------------------------
# ArcGIS query helpers
# ---------------------------------------------------------------------------

def query_arcgis(
    service_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    return_geometry: bool = False,
    out_sr: int = 4326,
    result_record_count: Optional[int] = None,
    result_offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Generic ArcGIS FeatureServer query helper.

    Args:
        service_url:         Base URL to the FeatureServer/N endpoint (no /query).
        where:               SQL WHERE clause (default: 1=1 = all records).
        out_fields:          Comma-separated field list or "*" for all.
        return_geometry:     Include geometry in response.
        out_sr:              Output spatial reference WKID (default: 4326 WGS84).
        result_record_count: Limit number of records returned.
        result_offset:       Pagination offset.

    Returns:
        List of feature attribute dicts (and geometry dicts if return_geometry=True).

    Example:
        >>> features = query_arcgis(
        ...     ARCGIS_KYTC_URL.replace('/query', ''),
        ...     where="county='Fayette'",
        ...     out_fields="name,description,snapshot,county",
        ... )
    """
    params: Dict[str, str] = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
        "outSR": str(out_sr),
        "f": "pjson",
    }
    if result_record_count is not None:
        params["resultRecordCount"] = str(result_record_count)
    if result_offset:
        params["resultOffset"] = str(result_offset)

    query_url = service_url.rstrip("/") + "/query"
    url = _build_url(query_url, params)
    data = _fetch(url)
    return data.get("features", [])


# ---------------------------------------------------------------------------
# Summary / reporting utilities
# ---------------------------------------------------------------------------

def summarize_cameras(cameras: List[TrafficCamera]) -> Dict[str, Any]:
    """
    Return a summary dict of camera statistics.

    Returns:
        Dict with keys: total, online, offline, unknown_status,
                        by_county (dict), by_source (dict)
    """
    total = len(cameras)
    online = sum(1 for c in cameras if c.status == "Online")
    offline = sum(1 for c in cameras if c.status == "Offline")
    unknown = total - online - offline

    by_county: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for cam in cameras:
        county_key = cam.county or "Unknown"
        by_county[county_key] = by_county.get(county_key, 0) + 1
        by_source[cam.source] = by_source.get(cam.source, 0) + 1

    return {
        "total": total,
        "online": online,
        "offline": offline,
        "unknown_status": unknown,
        "by_county": dict(sorted(by_county.items())),
        "by_source": by_source,
    }


def summarize_feed(events: List[RealtimeEvent]) -> Dict[str, Any]:
    """
    Return a summary dict of real-time feed event statistics.

    Returns:
        Dict with keys: total, by_type (dict), by_county (dict)
    """
    by_type: Dict[str, int] = {}
    by_county: Dict[str, int] = {}
    for evt in events:
        by_type[evt.event_type] = by_type.get(evt.event_type, 0) + 1
        county_key = evt.county or "Unknown"
        by_county[county_key] = by_county.get(county_key, 0) + 1

    return {
        "total": len(events),
        "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
        "by_county": dict(sorted(by_county.items(), key=lambda x: -x[1])[:20]),
    }


# ---------------------------------------------------------------------------
# Main demo / self-test
# ---------------------------------------------------------------------------

def main():
    """
    Self-test: fetch live data from all endpoints and print a summary.
    Run with: python kytc_client.py
    """
    print("=" * 60)
    print("KYTC GoKY Traffic System - Live Data Test")
    print("=" * 60)

    # --- Camera feeds ---
    print("\n[1] KYTC Statewide Cameras (ArcGIS)")
    print("    Fetching...")
    kytc_cams = get_kytc_cameras()
    summary = summarize_cameras(kytc_cams)
    print(f"    Total cameras : {summary['total']}")
    print(f"    Online        : {summary['online']}")
    print(f"    Offline       : {summary['offline']}")
    print(f"    Unknown status: {summary['unknown_status']}")
    print(f"    Counties      : {len(summary['by_county'])}")

    # Show a couple of KY cameras
    ky = [c for c in kytc_cams if c.state == "Kentucky"]
    if ky:
        print("\n    Sample KY cameras:")
        for cam in ky[:3]:
            print(f"      {cam.name} | {cam.description} | {cam.county} County | {cam.status}")
            print(f"        Snapshot: {cam.snapshot_url}")

    print("\n[2] Fayette County (Lexington/Trimarc) Cameras (ArcGIS)")
    print("    Fetching...")
    fay_cams = get_fayette_cameras()
    print(f"    Total cameras : {len(fay_cams)}")
    if fay_cams:
        print("\n    Sample Fayette cameras:")
        for cam in fay_cams[:3]:
            print(f"      {cam.name} | {cam.description}")
            print(f"        Snapshot: {cam.snapshot_url}")

    # --- Realtime feed ---
    print("\n[3] Firebase Firestore Realtime Feed")
    print("    Fetching (all types, up to 300 docs per page)...")
    all_events = get_realtime_feed()
    feed_summary = summarize_feed(all_events)
    print(f"    Total events  : {feed_summary['total']}")
    print("    By type:")
    for t, cnt in feed_summary["by_type"].items():
        try:
            label = FeedType(t).name
        except ValueError:
            label = t
        print(f"      {t:8s} ({label:20s}): {cnt}")

    print("\n    Top counties by event count:")
    for county, cnt in list(feed_summary["by_county"].items())[:8]:
        print(f"      {county:20s}: {cnt}")

    # --- Incidents ---
    print("\n[4] Active Incidents (crashes, hazards, work zones)")
    incidents = get_incidents()
    print(f"    Total active incidents: {len(incidents)}")
    for evt in incidents[:5]:
        published = evt.published
        pub_str = published.strftime("%H:%M UTC") if published else "unknown time"
        print(
            f"      [{evt.event_type}] {evt.county} - {evt.road_name} "
            f"MP {evt.mile_point} @ {pub_str}"
        )
        if evt.description:
            print(f"        Description: {evt.description[:100]}")

    # --- DMS Signs ---
    print("\n[5] Dynamic Message Signs")
    dms_signs = get_dms_signs()
    print(f"    Total DMS signs with data: {len(dms_signs)}")
    for sign in dms_signs[:5]:
        sign_id = sign.source.get("id", "unknown")
        location = sign.source.get("location", sign.county)
        message = sign.source.get("message", "")
        print(f"      {sign_id} | {location}")
        if message:
            print(f"        Message: {message[:100]}")

    # --- Speed data sample ---
    print("\n[6] Traffic Speed Data (Jefferson County sample)")
    speed = get_speed_data(county="Jefferson")
    print(f"    Jefferson County speed segments: {len(speed)}")
    congested = [
        s for s in speed
        if "Congestion" in str(s.display.get("Source_Type", ""))
    ]
    print(f"    Congested segments: {len(congested)}")
    for seg in congested[:5]:
        curr = seg.display.get("Current_Speed", "?")
        hist = seg.display.get("Historic_Speed", "?")
        src_type = seg.display.get("Source_Type", "")
        print(
            f"      {seg.road_name} MP {seg.mile_point}: "
            f"{curr} mph (normal: {hist}) - {src_type}"
        )

    # --- RWIS ---
    print("\n[7] RWIS Weather Stations")
    rwis = get_rwis_stations()
    print(f"    Total RWIS stations: {len(rwis)}")
    for station in rwis[:3]:
        air = station.display.get("Air_Temp", "N/A")
        pave = station.display.get("Pavement_Temp", "N/A")
        station_id = station.source.get("id", station.doc_id)
        print(
            f"      {station_id} | {station.county} | "
            f"Air: {air} | Pavement: {pave}"
        )

    # --- Truck parking ---
    print("\n[8] Truck Parking Availability")
    parking = get_truck_parking()
    print(f"    Total locations: {len(parking)}")
    for p in parking:
        desc = p.source.get("description", "")
        open_status = p.source.get("open", "unknown")
        print(f"      {'OPEN' if open_status else 'CLOSED':6s} | {desc}")

    print("\n" + "=" * 60)
    print("Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
