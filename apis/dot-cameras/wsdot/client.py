"""
WSDOT Highway Camera Client
============================
Reverse-engineered client for Washington State DOT camera system.

Endpoints discovered:
  - REST API (requires AccessCode): https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc/
  - RSS feed (no auth): https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/rss.aspx
  - KML feed (no auth): https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/kml.aspx
  - Images (no auth): https://images.wsdot.wa.gov/{region}/{route}vc{milepost_hundredths}.jpg

Image URL Pattern:
  https://images.wsdot.wa.gov/{region}/{route_3digit}vc{milepost_5digit}.jpg
  e.g. https://images.wsdot.wa.gov/sc/090vc05200.jpg
       region=sc, route=090 (I-90), milepost=052.00

Region codes:
  er  = Eastern Region
  nc  = North Central Region
  nw  = Northwest Region (includes I-5 through Seattle)
  ol  = Olympic Region
  os  = Olympic/SW
  sc  = South Central Region (includes I-90 Snoqualmie Pass)
  sw  = Southwest Region
  wsf = Washington State Ferries
  rweather = Road Weather cameras
  spokane  = Spokane area cameras
  airports = Airport cameras
  traffic  = Generic traffic cameras

WSDOT API registration: https://www.wsdot.wa.gov/Traffic/api/
"""

import re
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Iterator
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CameraLocation:
    description: str = ""
    direction: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    milepost: Optional[float] = None
    road_name: str = ""


@dataclass
class Camera:
    camera_id: int = 0
    title: str = ""
    description: str = ""
    region: str = ""
    image_url: str = ""
    image_width: int = 0
    image_height: int = 0
    is_active: bool = True
    camera_owner: str = "WSDOT"
    owner_url: str = ""
    sort_order: int = 0
    display_latitude: Optional[float] = None
    display_longitude: Optional[float] = None
    location: Optional[CameraLocation] = None
    last_updated: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @property
    def route(self) -> Optional[str]:
        """Infer route from image URL if possible."""
        if not self.image_url:
            return None
        fn = self.image_url.split('/')[-1]
        m = re.match(r'^(\d{3})vc', fn, re.IGNORECASE)
        if m:
            r = int(m.group(1))
            if r == 5:
                return "I-5"
            elif r == 90:
                return "I-90"
            elif r == 82:
                return "I-82"
            else:
                return f"SR-{r}"
        return None

    @property
    def milepost_from_url(self) -> Optional[float]:
        """Infer milepost from image URL if possible."""
        if not self.image_url:
            return None
        fn = self.image_url.split('/')[-1]
        m = re.match(r'^\d{3}vc(\d{5})', fn, re.IGNORECASE)
        if m:
            return int(m.group(1)) / 100.0
        return None


@dataclass
class PassCondition:
    pass_id: int = 0
    name: str = ""
    road_condition: str = ""
    weather_condition: str = ""
    temperature_f: Optional[int] = None
    elevation_ft: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    travel_advisory_active: bool = False
    restriction_one_text: str = ""
    restriction_one_direction: str = ""
    restriction_two_text: str = ""
    restriction_two_direction: str = ""
    date_updated: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Base HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WSDOTCamClient/1.0)",
    "Accept": "application/json, text/xml, */*",
}


def _http_get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers=_DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_text(url: str, timeout: int = 15) -> str:
    return _http_get(url, timeout).decode("utf-8", errors="replace")


def _http_get_json(url: str, timeout: int = 15):
    return json.loads(_http_get_text(url, timeout))


# ─────────────────────────────────────────────────────────────────────────────
# No-Auth RSS / KML parsers
# ─────────────────────────────────────────────────────────────────────────────

RSS_URL = "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/rss.aspx"
KML_URL = "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/kml.aspx"


def fetch_cameras_from_rss() -> List[Camera]:
    """
    Fetch all cameras from the public RSS feed (no AccessCode required).
    Returns a list of Camera objects with id, title, image_url, last_updated.
    Coordinates are NOT available in RSS; use fetch_cameras_from_kml() for those.
    """
    raw = _http_get_text(RSS_URL)
    root = ET.fromstring(raw)
    ns = {"a10": "http://www.w3.org/2005/Atom"}
    channel = root.find("channel")
    cameras: List[Camera] = []

    for item in channel.findall("item"):
        guid_el = item.find("guid")
        link_el = item.find("link")
        title_el = item.find("title")
        updated_el = item.find("a10:updated", ns)

        cam = Camera(
            camera_id=int(guid_el.text) if guid_el is not None else 0,
            title=title_el.text if title_el is not None else "",
            image_url=link_el.text if link_el is not None else "",
            last_updated=updated_el.text if updated_el is not None else "",
        )
        # Infer region from image URL
        if cam.image_url:
            parts = cam.image_url.replace("https://images.wsdot.wa.gov/", "").split("/")
            if parts:
                cam.region = parts[0].lower()
        cameras.append(cam)

    return cameras


def fetch_cameras_from_kml() -> List[Camera]:
    """
    Fetch all cameras from the public KML feed (no AccessCode required).
    Returns Camera objects with id, title, image_url, latitude, longitude, region.

    KML includes geographic coordinates but not milepost or road name separately.
    Region codes: ER, NC, NW, OL, OS, SC, SW, WA
    """
    raw = _http_get_text(KML_URL)
    # KML namespace
    kml_ns = "http://www.opengis.net/kml/2.2"

    root = ET.fromstring(raw)
    cameras: List[Camera] = []

    for folder in root.iter(f"{{{kml_ns}}}Folder"):
        name_el = folder.find(f"{{{kml_ns}}}name")
        region = name_el.text.strip() if name_el is not None else ""

        for placemark in folder.findall(f"{{{kml_ns}}}Placemark"):
            pm_id = placemark.get("id", "ID 0").replace("ID ", "")
            name_el = placemark.find(f"{{{kml_ns}}}name")
            desc_el = placemark.find(f"{{{kml_ns}}}description")
            coords_el = placemark.find(f".//{{{kml_ns}}}coordinates")

            title = ""
            if name_el is not None and name_el.text:
                title = name_el.text.strip()

            # Extract image URL from CDATA description
            image_url = ""
            if desc_el is not None and desc_el.text:
                m = re.search(r'src="([^"]+)"', desc_el.text)
                if m:
                    image_url = m.group(1)

            lat = lon = None
            if coords_el is not None and coords_el.text:
                parts = coords_el.text.strip().split(",")
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                    except ValueError:
                        pass

            cam = Camera(
                camera_id=int(pm_id) if pm_id.isdigit() else 0,
                title=title,
                image_url=image_url,
                region=region,
                display_latitude=lat,
                display_longitude=lon,
                location=CameraLocation(
                    latitude=lat,
                    longitude=lon,
                ),
            )
            cameras.append(cam)

    return cameras


def fetch_all_cameras_merged() -> List[Camera]:
    """
    Merge KML (has coordinates) with RSS (has last_updated).
    Returns the richest possible camera data without requiring an AccessCode.
    """
    kml_cams = {c.camera_id: c for c in fetch_cameras_from_kml()}
    rss_cams = {c.camera_id: c for c in fetch_cameras_from_rss()}

    merged = []
    all_ids = set(kml_cams.keys()) | set(rss_cams.keys())
    for cam_id in all_ids:
        if cam_id in kml_cams:
            cam = kml_cams[cam_id]
            if cam_id in rss_cams:
                cam.last_updated = rss_cams[cam_id].last_updated
        else:
            cam = rss_cams[cam_id]
        merged.append(cam)

    merged.sort(key=lambda c: c.camera_id)
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Authenticated REST API client
# ─────────────────────────────────────────────────────────────────────────────

BASE_REST = "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc"
BASE_PASS = "https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/MountainPassConditionsREST.svc"


def _parse_camera_from_json(data: dict) -> Camera:
    loc_data = data.get("CameraLocation") or {}
    location = CameraLocation(
        description=loc_data.get("Description") or "",
        direction=loc_data.get("Direction") or "",
        latitude=loc_data.get("Latitude"),
        longitude=loc_data.get("Longitude"),
        milepost=loc_data.get("MilePost"),
        road_name=loc_data.get("RoadName") or "",
    )
    return Camera(
        camera_id=data.get("CameraID", 0),
        title=data.get("Title") or "",
        description=data.get("Description") or "",
        region=data.get("Region") or "",
        image_url=data.get("ImageURL") or "",
        image_width=data.get("ImageWidth") or 0,
        image_height=data.get("ImageHeight") or 0,
        is_active=data.get("IsActive", True),
        camera_owner=data.get("CameraOwner") or "WSDOT",
        owner_url=data.get("OwnerURL") or "",
        sort_order=data.get("SortOrder") or 0,
        display_latitude=data.get("DisplayLatitude"),
        display_longitude=data.get("DisplayLongitude"),
        location=location,
    )


def _parse_pass_condition(data: dict) -> PassCondition:
    r1 = data.get("RestrictionOne") or {}
    r2 = data.get("RestrictionTwo") or {}
    return PassCondition(
        pass_id=data.get("MountainPassId", 0),
        name=data.get("MountainPassName") or "",
        road_condition=data.get("RoadCondition") or "",
        weather_condition=data.get("WeatherCondition") or "",
        temperature_f=data.get("TemperatureInFahrenheit"),
        elevation_ft=data.get("ElevationInFeet"),
        latitude=data.get("Latitude"),
        longitude=data.get("Longitude"),
        travel_advisory_active=data.get("TravelAdvisoryActive", False),
        restriction_one_text=r1.get("RestrictionText") or "",
        restriction_one_direction=r1.get("TravelDirection") or "",
        restriction_two_text=r2.get("RestrictionText") or "",
        restriction_two_direction=r2.get("TravelDirection") or "",
        date_updated=data.get("DateUpdated") or "",
    )


class WSDOTCameraClient:
    """
    Full-featured WSDOT camera client.

    Without AccessCode: uses RSS/KML feeds (1658 cameras, no milepost filtering).
    With AccessCode:    uses REST API (all fields, filtering by route/region/milepost).

    Register for free at: https://www.wsdot.wa.gov/Traffic/api/
    """

    # Known mountain pass IDs (from WSDOT documentation / community research)
    MOUNTAIN_PASS_IDS = {
        "snoqualmie": 1,      # Snoqualmie Pass  (I-90, elev 3022 ft)
        "stevens":    2,      # Stevens Pass     (US-2, elev 4061 ft)
        "white":      3,      # White Pass       (US-12, elev 4500 ft)
        "cayuse":     4,      # Cayuse Pass      (SR-123, elev 4694 ft)
        "chinook":    5,      # Chinook Pass     (SR-410, elev 5430 ft)
        "blewett":    6,      # Blewett Pass     (US-97, elev 4102 ft)
        "manastash":  7,      # Manastash Ridge  (SR-10)
        "ryegrass":   8,      # Ryegrass Summit  (I-90)
        "satus":      9,      # Satus Pass       (US-97)
        "sherman":    10,     # Sherman Pass     (SR-20)
        "north_cascades": 11, # North Cascades Hwy (SR-20, seasonal closure)
        "loup_loup":  12,     # Loup Loup Pass   (SR-20)
        "wauconda":   13,     # Wauconda Summit  (SR-20)
    }

    # WSDOT region codes and human names
    REGIONS = {
        "ER": "Eastern Region",
        "NC": "North Central Region",
        "NW": "Northwest Region",
        "OL": "Olympic Region",
        "OS": "Olympic/SW Region",
        "SC": "South Central Region",
        "SW": "Southwest Region",
        "WA": "Airport Cameras",
    }

    def __init__(self, access_code: Optional[str] = None):
        """
        Args:
            access_code: WSDOT Traveler API access code (optional).
                         Without it, only RSS/KML endpoints are available.
                         Register free at https://www.wsdot.wa.gov/Traffic/api/
        """
        self.access_code = access_code
        self._camera_cache: Optional[List[Camera]] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 120  # seconds

    # ── No-auth methods ───────────────────────────────────────────────────────

    def get_all_cameras_public(self, use_cache: bool = True) -> List[Camera]:
        """
        Get all cameras using the public RSS+KML feeds (no AccessCode needed).
        Data is cached for 2 minutes by default.
        Returns 1658 cameras with title, image_url, lat/lon, region, last_updated.
        """
        now = time.time()
        if use_cache and self._camera_cache and (now - self._cache_time) < self._cache_ttl:
            return self._camera_cache
        cameras = fetch_all_cameras_merged()
        self._camera_cache = cameras
        self._cache_time = now
        return cameras

    def search_cameras_public(
        self,
        title_contains: Optional[str] = None,
        region: Optional[str] = None,
        route_keyword: Optional[str] = None,
        min_lat: Optional[float] = None,
        max_lat: Optional[float] = None,
        min_lon: Optional[float] = None,
        max_lon: Optional[float] = None,
    ) -> List[Camera]:
        """
        Filter cameras from public feed by various criteria.

        Args:
            title_contains: Substring match on camera title (case-insensitive)
            region: Region code, e.g. "NW", "NC", "SC", "ER", "SW", "OL"
            route_keyword: Route keyword, e.g. "I-90", "US 2", "SR 20"
            min_lat/max_lat/min_lon/max_lon: Bounding box filter
        """
        cams = self.get_all_cameras_public()
        if title_contains:
            tc = title_contains.lower()
            cams = [c for c in cams if tc in c.title.lower()]
        if region:
            ru = region.upper()
            cams = [c for c in cams if c.region.upper() == ru]
        if route_keyword:
            rk = route_keyword.lower()
            cams = [c for c in cams if rk in c.title.lower()]
        if min_lat is not None:
            cams = [c for c in cams if c.display_latitude is not None and c.display_latitude >= min_lat]
        if max_lat is not None:
            cams = [c for c in cams if c.display_latitude is not None and c.display_latitude <= max_lat]
        if min_lon is not None:
            cams = [c for c in cams if c.display_longitude is not None and c.display_longitude >= min_lon]
        if max_lon is not None:
            cams = [c for c in cams if c.display_longitude is not None and c.display_longitude <= max_lon]
        return cams

    def get_snoqualmie_pass_cameras(self) -> List[Camera]:
        """I-90 cameras near Snoqualmie Pass (MP ~45–62)."""
        return self.search_cameras_public(
            title_contains="I-90",
            min_lat=47.3,
            max_lat=47.5,
            min_lon=-121.8,
            max_lon=-121.3,
        )

    def get_stevens_pass_cameras(self) -> List[Camera]:
        """US-2 cameras near Stevens Pass (MP ~55–75)."""
        return self.search_cameras_public(
            route_keyword="US 2",
            min_lat=47.7,
            max_lat=47.85,
            min_lon=-121.2,
            max_lon=-120.8,
        )

    def get_north_cascades_cameras(self) -> List[Camera]:
        """SR-20 North Cascades Highway cameras (NC region)."""
        return self.search_cameras_public(region="NC")

    def get_ferry_cameras(self) -> List[Camera]:
        """Washington State Ferry terminal cameras."""
        cams = self.get_all_cameras_public()
        return [c for c in cams if "/wsf/" in c.image_url.lower() or "WSF" in c.title]

    def get_cameras_by_bbox(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> List[Camera]:
        """Get all cameras within a geographic bounding box."""
        return self.search_cameras_public(
            min_lat=min_lat, max_lat=max_lat,
            min_lon=min_lon, max_lon=max_lon,
        )

    # ── Authenticated REST API methods ────────────────────────────────────────

    def _require_access_code(self):
        if not self.access_code:
            raise ValueError(
                "An AccessCode is required for this method. "
                "Register for free at https://www.wsdot.wa.gov/Traffic/api/"
            )

    def _rest_url(self, endpoint: str, **params) -> str:
        params["AccessCode"] = self.access_code
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return f"{BASE_REST}/{endpoint}?{qs}"

    def get_all_cameras(self) -> List[Camera]:
        """
        [Requires AccessCode] Fetch all cameras via REST API.
        Returns full Camera objects including milepost, road name, dimensions.
        """
        self._require_access_code()
        url = self._rest_url("GetCamerasAsJson")
        data = _http_get_json(url)
        return [_parse_camera_from_json(d) for d in data]

    def get_camera(self, camera_id: int) -> Camera:
        """[Requires AccessCode] Fetch a single camera by ID."""
        self._require_access_code()
        url = self._rest_url("GetCameraAsJson", CameraID=camera_id)
        data = _http_get_json(url)
        return _parse_camera_from_json(data)

    def search_cameras(
        self,
        state_route: Optional[str] = None,
        region: Optional[str] = None,
        starting_milepost: Optional[float] = None,
        ending_milepost: Optional[float] = None,
    ) -> List[Camera]:
        """
        [Requires AccessCode] Search cameras by route, region, and milepost range.

        Args:
            state_route: 3-digit zero-padded route number, e.g. "090" for I-90,
                         "002" for US-2, "020" for SR-20, "005" for I-5
            region: Region code: ER, NC, NW, OL, OS, SC, SW
            starting_milepost: Start of milepost range (decimal)
            ending_milepost: End of milepost range (decimal)

        Examples:
            # All I-90 cameras
            client.search_cameras(state_route="090")

            # I-90 Snoqualmie Pass area (MP 45-62)
            client.search_cameras(state_route="090", starting_milepost=45.0, ending_milepost=62.0)

            # All NW region cameras
            client.search_cameras(region="NW")
        """
        self._require_access_code()
        url = self._rest_url(
            "SearchCamerasAsJson",
            StateRoute=state_route,
            Region=region,
            StartingMilepost=starting_milepost,
            EndingMilepost=ending_milepost,
        )
        data = _http_get_json(url)
        return [_parse_camera_from_json(d) for d in data]

    # ── Mountain Pass Conditions ──────────────────────────────────────────────

    def _pass_url(self, endpoint: str, **params) -> str:
        params["AccessCode"] = self.access_code
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return f"{BASE_PASS}/{endpoint}?{qs}"

    def get_all_pass_conditions(self) -> List[PassCondition]:
        """[Requires AccessCode] Get conditions for all mountain passes."""
        self._require_access_code()
        url = self._pass_url("GetMountainPassConditionsAsJson")
        data = _http_get_json(url)
        return [_parse_pass_condition(d) for d in data]

    def get_pass_condition(self, pass_id: int) -> PassCondition:
        """[Requires AccessCode] Get conditions for a specific mountain pass."""
        self._require_access_code()
        url = self._pass_url("GetMountainPassConditionAsJon", PassConditionID=pass_id)
        data = _http_get_json(url)
        return _parse_pass_condition(data)

    # ── Image fetching ────────────────────────────────────────────────────────

    def fetch_camera_image(self, camera: Camera) -> Optional[bytes]:
        """
        Download the current JPEG image for a camera.
        Images at images.wsdot.wa.gov are publicly accessible (no auth needed).
        Returns raw JPEG bytes, or None on failure.
        """
        if not camera.image_url:
            return None
        try:
            return _http_get(camera.image_url)
        except Exception:
            return None

    def iter_camera_images(
        self,
        cameras: List[Camera],
        delay_seconds: float = 0.5,
    ) -> Iterator[tuple]:
        """
        Iterate over cameras yielding (camera, image_bytes_or_none) tuples.
        Adds a small delay between requests to be polite to WSDOT servers.
        """
        for cam in cameras:
            img = self.fetch_camera_image(cam)
            yield (cam, img)
            if delay_seconds > 0:
                time.sleep(delay_seconds)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def build_image_url(
        self,
        region: str,
        route_number: int,
        milepost: float,
    ) -> str:
        """
        Build a camera image URL from known components.

        Args:
            region: Lowercase region code, e.g. "sc", "nw", "nc", "er", "sw", "ol"
            route_number: Integer route number, e.g. 90 (I-90), 5 (I-5), 2 (US-2)
            milepost: Decimal milepost, e.g. 52.0

        Returns:
            URL like https://images.wsdot.wa.gov/sc/090vc05200.jpg

        Note: This only works for cameras following the standard naming pattern.
              Airport, ferry, and some other cameras use different filenames.
        """
        route_str = f"{route_number:03d}"
        mp_str = f"{int(milepost * 100):05d}"
        return f"https://images.wsdot.wa.gov/{region.lower()}/{route_str}vc{mp_str}.jpg"

    def cameras_to_geojson(self, cameras: List[Camera]) -> dict:
        """Convert a list of cameras to a GeoJSON FeatureCollection."""
        features = []
        for cam in cameras:
            lat = cam.display_latitude or (cam.location.latitude if cam.location else None)
            lon = cam.display_longitude or (cam.location.longitude if cam.location else None)
            if lat is None or lon is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat],
                },
                "properties": {
                    "id": cam.camera_id,
                    "title": cam.title,
                    "region": cam.region,
                    "image_url": cam.image_url,
                    "route": cam.route,
                    "milepost": cam.milepost_from_url,
                    "last_updated": cam.last_updated,
                    "is_active": cam.is_active,
                },
            })
        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def cameras_to_csv_rows(self, cameras: List[Camera]) -> List[List[str]]:
        """Convert cameras to CSV-ready rows (first row is header)."""
        headers = [
            "camera_id", "title", "region", "image_url",
            "latitude", "longitude", "route", "milepost", "last_updated",
        ]
        rows = [headers]
        for cam in cameras:
            lat = cam.display_latitude or (cam.location.latitude if cam.location else "")
            lon = cam.display_longitude or (cam.location.longitude if cam.location else "")
            rows.append([
                str(cam.camera_id),
                cam.title,
                cam.region,
                cam.image_url,
                str(lat) if lat is not None else "",
                str(lon) if lon is not None else "",
                cam.route or "",
                str(cam.milepost_from_url or ""),
                cam.last_updated,
            ])
        return rows


# ─────────────────────────────────────────────────────────────────────────────
# Convenience top-level functions
# ─────────────────────────────────────────────────────────────────────────────

def get_all_cameras(access_code: Optional[str] = None) -> List[Camera]:
    """
    Get all WSDOT cameras.
    Without access_code: uses public RSS/KML (1658 cameras, no milepost filtering).
    With access_code: uses REST API (full metadata, filter support).
    """
    client = WSDOTCameraClient(access_code)
    if access_code:
        return client.get_all_cameras()
    return client.get_all_cameras_public()


def get_mountain_pass_cameras() -> dict:
    """
    Get cameras grouped by mountain pass using public feed (no auth).
    Returns dict of pass_name -> List[Camera].
    """
    client = WSDOTCameraClient()
    all_cams = client.get_all_cameras_public()

    passes = {
        "snoqualmie_pass": {
            "desc": "I-90 Snoqualmie Pass",
            "cams": [c for c in all_cams if "I-90" in c.title and c.display_latitude
                     and 47.3 < c.display_latitude < 47.5
                     and c.display_longitude and -121.8 < c.display_longitude < -121.3],
        },
        "stevens_pass": {
            "desc": "US 2 Stevens Pass",
            "cams": [c for c in all_cams if "US 2" in c.title and c.display_latitude
                     and 47.7 < c.display_latitude < 47.85
                     and c.display_longitude and -121.2 < c.display_longitude < -120.8],
        },
        "north_cascades_hwy": {
            "desc": "SR-20 North Cascades Highway (NC region)",
            "cams": [c for c in all_cams if c.region.upper() == "NC"
                     and ("SR 20" in c.title or "020vc" in c.image_url.lower())],
        },
        "white_pass": {
            "desc": "US-12 White Pass",
            "cams": [c for c in all_cams if "US 12" in c.title and c.display_latitude
                     and 46.5 < c.display_latitude < 46.8],
        },
        "chinook_pass": {
            "desc": "SR-410 Chinook Pass",
            "cams": [c for c in all_cams if "SR 410" in c.title or "Chinook" in c.title],
        },
    }
    return passes


def fetch_image(image_url: str) -> Optional[bytes]:
    """Directly fetch a camera image by URL. No auth required."""
    try:
        return _http_get(image_url)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI demo
# ─────────────────────────────────────────────────────────────────────────────

def _demo():
    """Quick demonstration of the client capabilities."""
    print("=" * 70)
    print("WSDOT Camera Client Demo")
    print("=" * 70)

    client = WSDOTCameraClient()

    print("\n[1] Fetching all cameras from public feed...")
    cameras = client.get_all_cameras_public()
    print(f"    Total cameras: {len(cameras)}")

    # Count by region
    from collections import Counter
    regions = Counter(c.region.upper() for c in cameras)
    print("    By region:")
    for r, count in sorted(regions.items()):
        name = WSDOTCameraClient.REGIONS.get(r, r)
        print(f"      {r} ({name}): {count}")

    print("\n[2] Snoqualmie Pass cameras (I-90):")
    sq_cams = client.get_snoqualmie_pass_cameras()
    for c in sorted(sq_cams, key=lambda x: x.display_latitude or 0):
        mp = c.milepost_from_url
        print(f"    ID={c.camera_id:5d} | MP {mp:5.1f} | {c.title}")
        print(f"           URL: {c.image_url}")

    print("\n[3] Stevens Pass cameras (US-2):")
    st_cams = client.get_stevens_pass_cameras()
    for c in sorted(st_cams, key=lambda x: x.display_longitude or 0, reverse=True):
        mp = c.milepost_from_url
        print(f"    ID={c.camera_id:5d} | MP {mp:5.1f} | {c.title}")
        print(f"           URL: {c.image_url}")

    print("\n[4] Ferry cameras (sample):")
    ferry = client.get_ferry_cameras()[:5]
    for c in ferry:
        print(f"    ID={c.camera_id:5d} | {c.title}")
        print(f"           URL: {c.image_url}")

    print("\n[5] Testing image download (Snoqualmie Summit):")
    # ID 1100 = I-90 at MP 52: Snoqualmie Summit
    test_cam = Camera(
        camera_id=1100,
        title="I-90 at MP 52: Snoqualmie Summit",
        image_url="https://images.wsdot.wa.gov/sc/090VC05200.jpg",
    )
    img = client.fetch_camera_image(test_cam)
    if img:
        print(f"    Downloaded {len(img):,} bytes")
        jpeg_magic = b'\xff\xd8'
        print(f"    Starts with JPEG magic: {img[:2] == jpeg_magic}")
    else:
        print("    Failed to download image")

    print("\n[6] GeoJSON export (first 5 cameras):")
    geojson = client.cameras_to_geojson(cameras[:5])
    print(f"    FeatureCollection with {len(geojson['features'])} features")
    if geojson["features"]:
        f = geojson["features"][0]
        print(f"    First: {f['properties']['title']}")
        print(f"      coords: {f['geometry']['coordinates']}")

    print("\n[7] URL pattern builder:")
    examples = [
        ("sc", 90, 52.0, "I-90 Snoqualmie Summit"),
        ("nc", 2, 64.3, "US-2 Stevens Pass West Summit"),
        ("nw", 5, 158.8, "I-5 near Seattle"),
        ("nw", 405, 0.34, "SR-405 north"),
    ]
    for region, route, mp, desc in examples:
        url = client.build_image_url(region, route, mp)
        print(f"    {desc}: {url}")

    print("\n[8] REST API endpoints (require AccessCode registration):")
    print("    Register at: https://www.wsdot.wa.gov/Traffic/api/")
    print()
    print("    GetCamerasAsJson:")
    print("      GET /HighwayCameras/HighwayCamerasREST.svc/GetCamerasAsJson?AccessCode={code}")
    print()
    print("    GetCameraAsJson:")
    print("      GET /HighwayCameras/HighwayCamerasREST.svc/GetCameraAsJson?AccessCode={code}&CameraID={id}")
    print()
    print("    SearchCamerasAsJson (filter by route, region, milepost):")
    print("      GET /HighwayCameras/HighwayCamerasREST.svc/SearchCamerasAsJson")
    print("          ?AccessCode={code}&StateRoute={route}&Region={region}")
    print("          &StartingMilepost={start}&EndingMilepost={end}")
    print()
    print("    GetMountainPassConditionsAsJson:")
    print("      GET /MountainPassConditions/MountainPassConditionsREST.svc/GetMountainPassConditionsAsJson?AccessCode={code}")

    print("\n" + "=" * 70)
    print("Demo complete.")
    print("=" * 70)


if __name__ == "__main__":
    _demo()
