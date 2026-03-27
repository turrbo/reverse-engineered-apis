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




# =============================================================================



# =============================================================================
# TRAFFIC FLOW
# =============================================================================

@dataclass
class FlowReading:
    """A single traffic flow sensor reading."""
    flow_data_id: int = 0
    flow_station_id: str = ""
    region: str = ""
    station_name: str = ""
    highway: str = ""
    milepost: float = 0.0
    direction: str = ""
    lane_count: int = 0
    occupancy: float = 0.0
    speed: float = 0.0
    flow_reading_value: float = 0.0  # vehicles per hour
    time_updated: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_traffic_flow_rss(
    highway: str = "",
    region_code: str = "",
    timeout: int = 15,
) -> List[FlowReading]:
    """
    Fetch traffic flow readings from the WSDOT public RSS feed.

    RSS endpoint (no auth required):
      https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/rss.aspx
      Optional params: StateRoute, Region
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/rss.aspx"
    params: Dict[str, str] = {}
    if highway:
        params["StateRoute"] = highway
    if region_code:
        params["Region"] = region_code
    url = base + ("?" + urllib.parse.urlencode(params) if params else "")

    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    ns = {"media": "http://search.yahoo.com/mrss/"}
    readings: List[FlowReading] = []

    for item in root.iter("item"):
        r = FlowReading()
        title_el = item.find("title")
        if title_el is not None and title_el.text:
            r.station_name = title_el.text.strip()

        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            desc = desc_el.text
            m = re.search(r"FlowStationID[:\s]+([^\s<,]+)", desc, re.I)
            if m:
                r.flow_station_id = m.group(1).strip()
            m = re.search(r"Region[:\s]+([^\s<,]+)", desc, re.I)
            if m:
                r.region = m.group(1).strip()
            m = re.search(r"Highway[:\s]+([^\s<,]+)", desc, re.I)
            if m:
                r.highway = m.group(1).strip()
            m = re.search(r"Milepost[:\s]+([\d.]+)", desc, re.I)
            if m:
                r.milepost = float(m.group(1))
            m = re.search(r"Direction[:\s]+([^\s<,]+)", desc, re.I)
            if m:
                r.direction = m.group(1).strip()
            m = re.search(r"Speed[:\s]+([\d.]+)", desc, re.I)
            if m:
                r.speed = float(m.group(1))
            m = re.search(r"Flow[:\s]+([\d.]+)", desc, re.I)
            if m:
                r.flow_reading_value = float(m.group(1))
            m = re.search(r"Occupancy[:\s]+([\d.]+)", desc, re.I)
            if m:
                r.occupancy = float(m.group(1))

        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            r.time_updated = pub_el.text.strip()

        readings.append(r)

    return readings


def get_traffic_flow(
    access_code: str,
    state_route: str = "",
    region_code: str = "",
    timeout: int = 15,
) -> List[FlowReading]:
    """
    Fetch traffic flow data from WSDOT REST API (requires AccessCode).

    REST endpoint:
      GET https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/TrafficFlowREST.svc/GetTrafficFlowsAsJson
      Params: AccessCode, StateRoute (optional), Region (optional)

    Returns a list of FlowReading objects.
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/TrafficFlowREST.svc/GetTrafficFlowsAsJson"
    params: Dict[str, str] = {"AccessCode": access_code}
    if state_route:
        params["StateRoute"] = state_route
    if region_code:
        params["Region"] = region_code
    url = base + "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    readings: List[FlowReading] = []
    for item in (data or []):
        r = FlowReading()
        r.flow_data_id = item.get("FlowDataID", 0) or 0
        r.flow_station_id = str(item.get("FlowStationID", "") or "")
        r.region = item.get("Region", "") or ""
        r.station_name = item.get("StationName", "") or ""
        r.highway = item.get("FlowStationLocation", {}).get("RoadName", "") or ""
        r.milepost = float(item.get("FlowStationLocation", {}).get("Milepost", 0) or 0)
        r.direction = item.get("FlowStationLocation", {}).get("Direction", "") or ""
        r.lane_count = int(item.get("LaneCount", 0) or 0)
        r.occupancy = float(item.get("Occupancy", 0) or 0)
        r.speed = float(item.get("Speed", 0) or 0)
        r.flow_reading_value = float(item.get("FlowReadingValue", 0) or 0)
        raw_ts = item.get("Time", "") or ""
        r.time_updated = _parse_wsdot_date(raw_ts)
        loc = item.get("FlowStationLocation", {}) or {}
        r.latitude = _to_float(loc.get("Latitude"))
        r.longitude = _to_float(loc.get("Longitude"))
        readings.append(r)

    return readings


# =============================================================================
# TRAVEL TIMES
# =============================================================================

@dataclass
class TravelTimeRoute:
    """A single WSDOT travel-time route entry."""
    travel_time_id: int = 0
    name: str = ""
    description: str = ""
    average_time: int = 0       # minutes
    current_time: int = 0       # minutes
    distance: float = 0.0       # miles
    time_updated: str = ""
    start_point_name: str = ""
    end_point_name: str = ""
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def delay_minutes(self) -> int:
        """Returns how many minutes current time exceeds average."""
        return max(0, self.current_time - self.average_time)


def fetch_travel_times_rss(timeout: int = 15) -> List[TravelTimeRoute]:
    """
    Fetch travel times from WSDOT public RSS feed (no auth required).

    RSS endpoint:
      https://www.wsdot.wa.gov/Traffic/api/TravelTimes/rss.aspx
    """
    url = "https://www.wsdot.wa.gov/Traffic/api/TravelTimes/rss.aspx"
    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    routes: List[TravelTimeRoute] = []

    for item in root.iter("item"):
        r = TravelTimeRoute()
        title_el = item.find("title")
        if title_el is not None and title_el.text:
            r.name = title_el.text.strip()

        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            desc = desc_el.text
            m = re.search(r"TravelTimeID[:\s]+([\d]+)", desc, re.I)
            if m:
                r.travel_time_id = int(m.group(1))
            m = re.search(r"AverageTime[:\s]+([\d]+)", desc, re.I)
            if m:
                r.average_time = int(m.group(1))
            m = re.search(r"CurrentTime[:\s]+([\d]+)", desc, re.I)
            if m:
                r.current_time = int(m.group(1))
            m = re.search(r"Distance[:\s]+([\d.]+)", desc, re.I)
            if m:
                r.distance = float(m.group(1))
            m = re.search(r"Description[:\s]+([^<]+)", desc, re.I)
            if m:
                r.description = m.group(1).strip()

        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            r.time_updated = pub_el.text.strip()

        routes.append(r)

    return routes


def get_travel_times(
    access_code: str,
    travel_time_id: int = 0,
    timeout: int = 15,
) -> List[TravelTimeRoute]:
    """
    Fetch travel time routes from WSDOT REST API (requires AccessCode).

    REST endpoints:
      GET .../GetTravelTimesAsJson?AccessCode={code}
      GET .../GetTravelTimeAsJson?AccessCode={code}&TravelTimeID={id}
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/TravelTimes/TravelTimesREST.svc"
    if travel_time_id:
        endpoint = f"{base}/GetTravelTimeAsJson"
        params = {"AccessCode": access_code, "TravelTimeID": travel_time_id}
    else:
        endpoint = f"{base}/GetTravelTimesAsJson"
        params = {"AccessCode": access_code}

    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    if isinstance(data, dict):
        data = [data]

    routes: List[TravelTimeRoute] = []
    for item in (data or []):
        r = TravelTimeRoute()
        r.travel_time_id = int(item.get("TravelTimeID", 0) or 0)
        r.name = item.get("Name", "") or ""
        r.description = item.get("Description", "") or ""
        r.average_time = int(item.get("AverageTime", 0) or 0)
        r.current_time = int(item.get("CurrentTime", 0) or 0)
        r.distance = float(item.get("Distance", 0) or 0)
        r.time_updated = _parse_wsdot_date(item.get("TimeUpdated", "") or "")
        sp = item.get("StartPoint", {}) or {}
        r.start_point_name = sp.get("Description", "") or ""
        r.start_latitude = _to_float(sp.get("Latitude"))
        r.start_longitude = _to_float(sp.get("Longitude"))
        ep = item.get("EndPoint", {}) or {}
        r.end_point_name = ep.get("Description", "") or ""
        r.end_latitude = _to_float(ep.get("Latitude"))
        r.end_longitude = _to_float(ep.get("Longitude"))
        routes.append(r)

    return routes


# =============================================================================
# HIGHWAY ALERTS
# =============================================================================

@dataclass
class HighwayAlert:
    """A WSDOT highway alert / road closure / incident."""
    alert_id: int = 0
    headline: str = ""
    event_category: str = ""
    event_status: str = ""
    start_road_name: str = ""
    start_direction: str = ""
    start_milepost: float = 0.0
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    end_road_name: str = ""
    end_milepost: float = 0.0
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    last_updated: str = ""
    start_time: str = ""
    end_time: str = ""
    priority: str = ""
    extended_description: str = ""
    region: str = ""
    county: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_closure(self) -> bool:
        return "close" in self.event_category.lower() or "closure" in self.headline.lower()


def fetch_highway_alerts_rss(
    state_route: str = "",
    region_code: str = "",
    county: str = "",
    start_severity: str = "",
    timeout: int = 15,
) -> List[HighwayAlert]:
    """
    Fetch highway alerts from WSDOT public RSS feed (no auth required).

    RSS endpoint:
      https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/rss.aspx
      Optional params: StateRoute, Region, County, StartSeverity
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/rss.aspx"
    params: Dict[str, str] = {}
    if state_route:
        params["StateRoute"] = state_route
    if region_code:
        params["Region"] = region_code
    if county:
        params["County"] = county
    if start_severity:
        params["StartSeverity"] = start_severity
    url = base + ("?" + urllib.parse.urlencode(params) if params else "")

    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    alerts: List[HighwayAlert] = []

    for item in root.iter("item"):
        a = HighwayAlert()
        title_el = item.find("title")
        if title_el is not None and title_el.text:
            a.headline = title_el.text.strip()

        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            desc = desc_el.text
            m = re.search(r"AlertID[:\s]+([\d]+)", desc, re.I)
            if m:
                a.alert_id = int(m.group(1))
            m = re.search(r"EventCategory[:\s]+([^<,]+)", desc, re.I)
            if m:
                a.event_category = m.group(1).strip()
            m = re.search(r"EventStatus[:\s]+([^<,]+)", desc, re.I)
            if m:
                a.event_status = m.group(1).strip()
            m = re.search(r"Region[:\s]+([^<,]+)", desc, re.I)
            if m:
                a.region = m.group(1).strip()
            m = re.search(r"County[:\s]+([^<,]+)", desc, re.I)
            if m:
                a.county = m.group(1).strip()
            m = re.search(r"Priority[:\s]+([^<,]+)", desc, re.I)
            if m:
                a.priority = m.group(1).strip()

        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            a.last_updated = pub_el.text.strip()

        alerts.append(a)

    return alerts


def get_highway_alerts(
    access_code: str,
    state_route: str = "",
    region_code: str = "",
    county: str = "",
    start_severity: str = "",
    alert_id: int = 0,
    timeout: int = 15,
) -> List[HighwayAlert]:
    """
    Fetch highway alerts from WSDOT REST API (requires AccessCode).

    REST endpoints:
      GET .../GetAlertsAsJson?AccessCode={code}
      GET .../GetAlertAsJson?AccessCode={code}&AlertID={id}
      Optional filters: StateRoute, Region, County, StartSeverity
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/HighwayAlertsREST.svc"
    if alert_id:
        endpoint = f"{base}/GetAlertAsJson"
        params: Dict[str, object] = {"AccessCode": access_code, "AlertID": alert_id}
    else:
        endpoint = f"{base}/GetAlertsAsJson"
        params = {"AccessCode": access_code}
        if state_route:
            params["StateRoute"] = state_route
        if region_code:
            params["Region"] = region_code
        if county:
            params["County"] = county
        if start_severity:
            params["StartSeverity"] = start_severity

    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    if isinstance(data, dict):
        data = [data]

    alerts: List[HighwayAlert] = []
    for item in (data or []):
        a = HighwayAlert()
        a.alert_id = int(item.get("AlertID", 0) or 0)
        a.headline = item.get("HeadlineDescription", "") or ""
        a.event_category = item.get("EventCategory", "") or ""
        a.event_status = item.get("EventStatus", "") or ""
        a.priority = item.get("Priority", "") or ""
        a.region = item.get("Region", "") or ""
        a.county = item.get("County", "") or ""
        a.extended_description = item.get("ExtendedDescription", "") or ""
        a.last_updated = _parse_wsdot_date(item.get("LastUpdatedTime", "") or "")
        a.start_time = _parse_wsdot_date(item.get("StartTime", "") or "")
        a.end_time = _parse_wsdot_date(item.get("EndTime", "") or "")
        sp = item.get("StartRoadwayLocation", {}) or {}
        a.start_road_name = sp.get("RoadName", "") or ""
        a.start_direction = sp.get("Direction", "") or ""
        a.start_milepost = float(sp.get("MilePost", 0) or 0)
        a.start_latitude = _to_float(sp.get("Latitude"))
        a.start_longitude = _to_float(sp.get("Longitude"))
        ep = item.get("EndRoadwayLocation", {}) or {}
        a.end_road_name = ep.get("RoadName", "") or ""
        a.end_milepost = float(ep.get("MilePost", 0) or 0)
        a.end_latitude = _to_float(ep.get("Latitude"))
        a.end_longitude = _to_float(ep.get("Longitude"))
        alerts.append(a)

    return alerts


def get_active_road_closures(access_code: str = "", timeout: int = 15) -> List[HighwayAlert]:
    """
    Convenience: return only active road closure alerts.
    Uses RSS feed if no access_code provided, REST API otherwise.
    """
    if access_code:
        alerts = get_highway_alerts(access_code, timeout=timeout)
    else:
        alerts = fetch_highway_alerts_rss(timeout=timeout)
    return [a for a in alerts if a.is_closure and a.event_status.lower() == "active"]


# =============================================================================
# WEATHER STATIONS
# =============================================================================

@dataclass
class WeatherReading:
    """A single weather observation from a WSDOT road weather station."""
    station_id: int = 0
    station_name: str = ""
    road_name: str = ""
    milepost: float = 0.0
    region: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    temperature: Optional[float] = None          # Fahrenheit
    road_temperature: Optional[float] = None     # Fahrenheit
    surface_condition: str = ""
    visibility: Optional[float] = None          # miles
    wind_speed: Optional[float] = None          # mph
    wind_direction: str = ""
    precipitation_type: str = ""
    time_updated: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_weather_stations_rss(
    region_code: str = "",
    timeout: int = 15,
) -> List[WeatherReading]:
    """
    Fetch road weather station readings from WSDOT public RSS feed (no auth).

    RSS endpoint:
      https://www.wsdot.wa.gov/Traffic/api/WeatherStation/rss.aspx
      Optional params: Region
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/WeatherStation/rss.aspx"
    params: Dict[str, str] = {}
    if region_code:
        params["Region"] = region_code
    url = base + ("?" + urllib.parse.urlencode(params) if params else "")

    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()

    root = ET.fromstring(raw)
    stations: List[WeatherReading] = []

    for item in root.iter("item"):
        w = WeatherReading()
        title_el = item.find("title")
        if title_el is not None and title_el.text:
            w.station_name = title_el.text.strip()

        desc_el = item.find("description")
        if desc_el is not None and desc_el.text:
            desc = desc_el.text
            m = re.search(r"StationID[:\s]+([\d]+)", desc, re.I)
            if m:
                w.station_id = int(m.group(1))
            m = re.search(r"Region[:\s]+([^\s<,]+)", desc, re.I)
            if m:
                w.region = m.group(1).strip()
            m = re.search(r"RoadName[:\s]+([^<,]+)", desc, re.I)
            if m:
                w.road_name = m.group(1).strip()
            m = re.search(r"Milepost[:\s]+([\d.]+)", desc, re.I)
            if m:
                w.milepost = float(m.group(1))
            m = re.search(r"Temperature[:\s]+([-\d.]+)", desc, re.I)
            if m:
                w.temperature = float(m.group(1))
            m = re.search(r"RoadTemperature[:\s]+([-\d.]+)", desc, re.I)
            if m:
                w.road_temperature = float(m.group(1))
            m = re.search(r"WindSpeed[:\s]+([\d.]+)", desc, re.I)
            if m:
                w.wind_speed = float(m.group(1))
            m = re.search(r"WindDirection[:\s]+([^<,]+)", desc, re.I)
            if m:
                w.wind_direction = m.group(1).strip()
            m = re.search(r"Visibility[:\s]+([\d.]+)", desc, re.I)
            if m:
                w.visibility = float(m.group(1))
            m = re.search(r"SurfaceCondition[:\s]+([^<,]+)", desc, re.I)
            if m:
                w.surface_condition = m.group(1).strip()
            m = re.search(r"PrecipitationType[:\s]+([^<,]+)", desc, re.I)
            if m:
                w.precipitation_type = m.group(1).strip()

        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            w.time_updated = pub_el.text.strip()

        stations.append(w)

    return stations


def get_weather_stations(
    access_code: str,
    station_id: int = 0,
    region_code: str = "",
    timeout: int = 15,
) -> List[WeatherReading]:
    """
    Fetch road weather station data from WSDOT REST API (requires AccessCode).

    REST endpoints:
      GET .../GetCurrentWeatherInformationAsJson?AccessCode={code}
      GET .../GetCurrentStationWeatherInformationAsJson?AccessCode={code}&StationID={id}
    """
    base = "https://www.wsdot.wa.gov/Traffic/api/WeatherStation/WeatherStationREST.svc"
    if station_id:
        endpoint = f"{base}/GetCurrentStationWeatherInformationAsJson"
        params: Dict[str, object] = {"AccessCode": access_code, "StationID": station_id}
    else:
        endpoint = f"{base}/GetCurrentWeatherInformationAsJson"
        params = {"AccessCode": access_code}
        if region_code:
            params["Region"] = region_code

    url = endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    if isinstance(data, dict):
        data = [data]

    stations: List[WeatherReading] = []
    for item in (data or []):
        w = WeatherReading()
        w.station_id = int(item.get("StationID", 0) or 0)
        w.station_name = item.get("StationName", "") or ""
        w.region = item.get("Region", "") or ""
        w.time_updated = _parse_wsdot_date(item.get("ReadingTime", "") or "")
        loc = item.get("StationLocation", {}) or {}
        w.road_name = loc.get("RoadName", "") or ""
        w.milepost = float(loc.get("MilePost", 0) or 0)
        w.latitude = _to_float(loc.get("Latitude"))
        w.longitude = _to_float(loc.get("Longitude"))
        # Weather readings may be nested in Readings list
        readings = item.get("Readings", []) or []
        for reading in readings:
            sensor = reading.get("SensorType", "") or ""
            value = reading.get("Data", {}) or {}
            if "AirTemp" in sensor:
                w.temperature = _to_float(value.get("TemperatureInFahrenheit"))
            elif "SurfaceTemp" in sensor or "RoadSurface" in sensor:
                w.road_temperature = _to_float(value.get("TemperatureInFahrenheit"))
                w.surface_condition = value.get("SurfaceCondition", "") or ""
            elif "Wind" in sensor:
                w.wind_speed = _to_float(value.get("SpeedInMPH"))
                w.wind_direction = value.get("Direction", "") or ""
            elif "Precip" in sensor:
                w.precipitation_type = value.get("PrecipitationType", "") or ""
        stations.append(w)

    return stations


# =============================================================================
# MOUNTAIN PASS CONDITIONS (Structured)
# =============================================================================

@dataclass
class MountainPassReport:
    """Detailed mountain pass condition report from WSDOT."""
    mountain_pass_id: int = 0
    mountain_pass_name: str = ""
    weather_condition: str = ""
    road_condition: str = ""
    temperature: Optional[float] = None    # Fahrenheit
    elevation: int = 0                     # feet
    travel_advisory_active: bool = False
    seasonal_closure: bool = False
    restriction_one: str = ""             # e.g. "Chains required"
    restriction_two: str = ""
    traction_advisory: bool = False
    date_updated: str = ""
    cameras: List[str] = field(default_factory=list)   # image URLs
    forecast: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


MOUNTAIN_PASS_INFO = {
    1: {"name": "Snoqualmie Pass", "route": "I-90", "milepost": 52.0,
        "lat": 47.4237, "lon": -121.4099, "elevation": 3022},
    2: {"name": "Stevens Pass",    "route": "US-2", "milepost": 64.4,
        "lat": 47.7479, "lon": -121.0875, "elevation": 4061},
    3: {"name": "White Pass",      "route": "US-12", "milepost": 150.9,
        "lat": 46.6387, "lon": -121.3921, "elevation": 4500},
    4: {"name": "Blewett Pass",    "route": "US-97", "milepost": 174.0,
        "lat": 47.5426, "lon": -120.5776, "elevation": 4102},
    5: {"name": "Sherman Pass",    "route": "SR-20", "milepost": 335.0,
        "lat": 48.6043, "lon": -118.4601, "elevation": 5575},
    6: {"name": "Loup Loup Pass",  "route": "SR-20", "milepost": 232.0,
        "lat": 48.3868, "lon": -119.8994, "elevation": 4020},
    7: {"name": "Cayuse Pass",     "route": "SR-410", "milepost": 61.0,
        "lat": 46.8734, "lon": -121.5287, "elevation": 4694},
    8: {"name": "Chinook Pass",    "route": "SR-410", "milepost": 52.0,
        "lat": 46.8745, "lon": -121.5231, "elevation": 5430},
    9: {"name": "North Cascades (US-20)", "route": "SR-20", "milepost": 170.0,
        "lat": 48.5126, "lon": -120.6726, "elevation": 5477},
}


def fetch_mountain_pass_conditions(
    access_code: str = "",
    pass_id: int = 0,
    timeout: int = 15,
) -> List[MountainPassReport]:
    """
    Fetch mountain pass conditions. Uses REST API if access_code provided,
    otherwise falls back to RSS feed.

    REST endpoints:
      GET .../GetMountainPassConditionsAsJson?AccessCode={code}
      GET .../GetMountainPassConditionAsJson?AccessCode={code}&PassConditionID={id}

    RSS feed (no auth):
      https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/rss.aspx
    """
    if access_code:
        base = "https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/MountainPassConditionsREST.svc"
        if pass_id:
            endpoint = f"{base}/GetMountainPassConditionAsJson"
            params: Dict[str, object] = {"AccessCode": access_code, "PassConditionID": pass_id}
        else:
            endpoint = f"{base}/GetMountainPassConditionsAsJson"
            params = {"AccessCode": access_code}

        url = endpoint + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "WSDOTClient/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

        if isinstance(data, dict):
            data = [data]

        reports: List[MountainPassReport] = []
        for item in (data or []):
            p = MountainPassReport()
            p.mountain_pass_id = int(item.get("MountainPassID", 0) or 0)
            p.mountain_pass_name = item.get("MountainPassName", "") or ""
            p.weather_condition = item.get("WeatherCondition", "") or ""
            p.road_condition = item.get("RoadCondition", "") or ""
            p.temperature = _to_float(item.get("TemperatureInFahrenheit"))
            p.elevation = int(item.get("ElevationInFeet", 0) or 0)
            p.travel_advisory_active = bool(item.get("TravelAdvisoryActive", False))
            p.seasonal_closure = bool(item.get("SeasonalClosure", False))
            p.forecast = item.get("Forecast", "") or ""
            p.date_updated = _parse_wsdot_date(item.get("DateUpdated", "") or "")
            r1 = item.get("RestrictionOne", {}) or {}
            p.restriction_one = r1.get("RestrictionText", "") or ""
            r2 = item.get("RestrictionTwo", {}) or {}
            p.restriction_two = r2.get("RestrictionText", "") or ""
            # Enrich with static pass info
            static = MOUNTAIN_PASS_INFO.get(p.mountain_pass_id, {})
            if static:
                p.latitude = static.get("lat")
                p.longitude = static.get("lon")
                if not p.elevation:
                    p.elevation = static.get("elevation", 0)
            reports.append(p)
        return reports

    else:
        # Fall back to RSS
        rss_url = "https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/rss.aspx"
        req = urllib.request.Request(rss_url, headers={"User-Agent": "WSDOTClient/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)
        reports = []
        for item in root.iter("item"):
            p = MountainPassReport()
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                p.mountain_pass_name = title_el.text.strip()

            desc_el = item.find("description")
            if desc_el is not None and desc_el.text:
                desc = desc_el.text
                m = re.search(r"MountainPassID[:\s]+([\d]+)", desc, re.I)
                if m:
                    p.mountain_pass_id = int(m.group(1))
                m = re.search(r"WeatherCondition[:\s]+([^<]+)", desc, re.I)
                if m:
                    p.weather_condition = m.group(1).strip()
                m = re.search(r"RoadCondition[:\s]+([^<]+)", desc, re.I)
                if m:
                    p.road_condition = m.group(1).strip()
                m = re.search(r"Temperature[:\s]+([-\d.]+)", desc, re.I)
                if m:
                    p.temperature = float(m.group(1))
                m = re.search(r"Elevation[:\s]+([\d]+)", desc, re.I)
                if m:
                    p.elevation = int(m.group(1))
                m = re.search(r"TravelAdvisory[:\s]+([^<,]+)", desc, re.I)
                if m:
                    p.travel_advisory_active = m.group(1).strip().lower() in ("true", "yes", "1")

            pub_el = item.find("pubDate")
            if pub_el is not None and pub_el.text:
                p.date_updated = pub_el.text.strip()

            # Enrich with static info
            static = MOUNTAIN_PASS_INFO.get(p.mountain_pass_id, {})
            if static:
                p.latitude = static.get("lat")
                p.longitude = static.get("lon")

            reports.append(p)
        return reports


def get_active_pass_closures(
    access_code: str = "",
    timeout: int = 15,
) -> List[MountainPassReport]:
    """Convenience: return only passes with seasonal or advisory closure."""
    passes = fetch_mountain_pass_conditions(access_code=access_code, timeout=timeout)
    return [p for p in passes if p.seasonal_closure or p.travel_advisory_active]


# =============================================================================
# WASHINGTON STATE FERRIES (WSF)
# =============================================================================

@dataclass
class FerryVessel:
    """A WSF ferry vessel with current position and status."""
    vessel_id: int = 0
    vessel_name: str = ""
    abbreviation: str = ""
    mmsi: int = 0
    status: str = ""
    speed: float = 0.0              # knots
    heading: int = 0                # degrees
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    in_service: bool = True
    at_dock: bool = False
    departing_terminal_id: int = 0
    departing_terminal_name: str = ""
    arriving_terminal_id: int = 0
    arriving_terminal_name: str = ""
    scheduled_departure: str = ""
    eta: str = ""
    time_updated: str = ""
    vessel_watch_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FerryTerminal:
    """A WSF ferry terminal."""
    terminal_id: int = 0
    terminal_name: str = ""
    abbreviation: str = ""
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    address: str = ""
    city: str = ""
    zip_code: str = ""
    bulletin: str = ""
    wait_time_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FerryRoute:
    """A WSF ferry route definition."""
    route_id: int = 0
    route_abbreviation: str = ""
    route_description: str = ""
    crossing_time: int = 0      # minutes
    ferry_count: int = 0
    terminal_combinations: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FerrySailing:
    """A single sailing departure from a WSF schedule."""
    sailing_date: str = ""
    depart_time: str = ""
    arrival_time: str = ""
    vessel_name: str = ""
    vessel_id: int = 0
    depart_terminal_id: int = 0
    arrive_terminal_id: int = 0
    sailing_id: int = 0
    annotations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# WSF base URLs
WSF_BASE = "https://www.wsdot.wa.gov/ferries/api"
WSF_VERSION = "latest"   # or pin to "20231101"


def _wsf_url(service: str, method: str, apiaccesscode: str = "") -> str:
    """Build a WSF API URL."""
    base = f"{WSF_BASE}/{service}/rest/{WSF_VERSION}/{method}"
    if apiaccesscode:
        sep = "&" if "?" in base else "?"
        base += f"{sep}apiaccesscode={urllib.parse.quote(apiaccesscode)}"
    return base


def _parse_wsf_date(val) -> str:
    """
    Convert WSF /Date(milliseconds-offset)/ format to ISO 8601.
    Example: '/Date(1700000000000-0800)/' -> '2023-11-14T15:33:20-08:00'
    Returns empty string if parsing fails.
    """
    if not val:
        return ""
    if isinstance(val, str):
        m = re.search(r"/Date\((\d+)([-+]\d{4})?\)/", val)
        if m:
            ms = int(m.group(1))
            offset = m.group(2) or "+0000"
            dt = datetime.utcfromtimestamp(ms / 1000.0)
            try:
                return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset[:3] + ":" + offset[3:]
            except Exception:
                return dt.isoformat() + "Z"
    return str(val)


def get_ferry_vessel_locations(
    apiaccesscode: str = "",
    timeout: int = 15,
) -> List[FerryVessel]:
    """
    Fetch real-time vessel locations from WSF Vessel Watch API.

    Endpoint (no auth required for basic data):
      GET https://www.wsdot.wa.gov/ferries/api/vessels/rest/{version}/vessellocations
    """
    url = _wsf_url("vessels", "vessellocations", apiaccesscode)
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    vessels: List[FerryVessel] = []
    for item in (data or []):
        v = FerryVessel()
        v.vessel_id = int(item.get("VesselID", 0) or 0)
        v.vessel_name = item.get("VesselName", "") or ""
        v.abbreviation = item.get("Abbreviation", "") or ""
        v.mmsi = int(item.get("Mmsi", 0) or 0)
        v.status = item.get("VesselWatchStatus", "") or ""
        v.speed = float(item.get("Speed", 0) or 0)
        v.heading = int(item.get("Heading", 0) or 0)
        v.latitude = _to_float(item.get("Latitude"))
        v.longitude = _to_float(item.get("Longitude"))
        v.in_service = bool(item.get("InService", True))
        v.at_dock = bool(item.get("AtDock", False))
        v.departing_terminal_id = int(item.get("DepartingTerminalID", 0) or 0)
        v.departing_terminal_name = item.get("DepartingTerminalName", "") or ""
        v.arriving_terminal_id = int(item.get("ArrivingTerminalID", 0) or 0)
        v.arriving_terminal_name = item.get("ArrivingTerminalName", "") or ""
        v.scheduled_departure = _parse_wsf_date(item.get("ScheduledDeparture"))
        v.eta = _parse_wsf_date(item.get("Eta"))
        v.time_updated = _parse_wsf_date(item.get("TimeStamp"))
        v.vessel_watch_url = item.get("VesselWatchShutID", "") or ""
        vessels.append(v)

    return vessels


def get_ferry_vessels(
    apiaccesscode: str = "",
    timeout: int = 15,
) -> List[FerryVessel]:
    """
    Fetch ferry vessel info/fleet list from WSF Vessels API.

    Endpoint:
      GET https://www.wsdot.wa.gov/ferries/api/vessels/rest/{version}/vesselbasics
    """
    url = _wsf_url("vessels", "vesselbasics", apiaccesscode)
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    vessels: List[FerryVessel] = []
    for item in (data or []):
        v = FerryVessel()
        v.vessel_id = int(item.get("VesselID", 0) or 0)
        v.vessel_name = item.get("VesselName", "") or ""
        v.abbreviation = item.get("Abbreviation", "") or ""
        v.mmsi = int(item.get("Mmsi", 0) or 0)
        v.in_service = bool(item.get("InService", True))
        vessels.append(v)

    return vessels


def get_ferry_terminals(
    apiaccesscode: str = "",
    timeout: int = 15,
) -> List[FerryTerminal]:
    """
    Fetch ferry terminal info from WSF Terminals API.

    Endpoint:
      GET https://www.wsdot.wa.gov/ferries/api/terminals/rest/{version}/terminalbasics
    """
    url = _wsf_url("terminals", "terminalbasics", apiaccesscode)
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    terminals: List[FerryTerminal] = []
    for item in (data or []):
        t = FerryTerminal()
        t.terminal_id = int(item.get("TerminalID", 0) or 0)
        t.terminal_name = item.get("TerminalName", "") or ""
        t.abbreviation = item.get("TerminalAbbrev", "") or ""
        t.longitude = _to_float(item.get("Longitude"))
        t.latitude = _to_float(item.get("Latitude"))
        t.address = item.get("AddressLineOne", "") or ""
        t.city = item.get("City", "") or ""
        t.zip_code = item.get("ZipCode", "") or ""
        terminals.append(t)

    return terminals


def get_ferry_routes(
    apiaccesscode: str = "",
    timeout: int = 15,
) -> List[FerryRoute]:
    """
    Fetch ferry route definitions from WSF Schedule API.

    Endpoint:
      GET https://www.wsdot.wa.gov/ferries/api/schedule/rest/{version}/valid
    """
    url = _wsf_url("schedule", "valid", apiaccesscode)
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    routes: List[FerryRoute] = []
    for item in (data or []):
        r = FerryRoute()
        r.route_id = int(item.get("RouteID", 0) or 0)
        r.route_abbreviation = item.get("RouteAbbrev", "") or ""
        r.route_description = item.get("Description", "") or ""
        r.crossing_time = int(item.get("CrossingTime", 0) or 0)
        r.ferry_count = int(item.get("FerryCount", 0) or 0)
        routes.append(r)

    return routes


def get_ferry_schedule_today(
    depart_terminal_id: int,
    arrive_terminal_id: int,
    apiaccesscode: str = "",
    date: str = "",
    timeout: int = 15,
) -> List[FerrySailing]:
    """
    Fetch today's (or specified date's) ferry sailing schedule between two terminals.

    Endpoint:
      GET https://www.wsdot.wa.gov/ferries/api/schedule/rest/{version}/scheduletoday/{dep}/{arr}/false
      Or for a specific date:
      GET .../schedule/{dep}/{arr}/{date}

    Args:
      depart_terminal_id: Departing terminal ID (see get_ferry_terminals())
      arrive_terminal_id: Arriving terminal ID
      date: Optional date string in YYYY-MM-DD format (defaults to today)
      apiaccesscode: Optional WSF API access code
    """
    if date:
        method = f"schedule/{depart_terminal_id}/{arrive_terminal_id}/{date}"
    else:
        method = f"scheduletoday/{depart_terminal_id}/{arrive_terminal_id}/false"

    url = _wsf_url("schedule", method, apiaccesscode)
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    sailings: List[FerrySailing] = []
    # Response structure: {"TerminalCombos": [{"Times": [...]}]}
    combos = data.get("TerminalCombos", []) if isinstance(data, dict) else []
    for combo in combos:
        for time_entry in (combo.get("Times", []) or []):
            s = FerrySailing()
            s.depart_terminal_id = depart_terminal_id
            s.arrive_terminal_id = arrive_terminal_id
            s.depart_time = _parse_wsf_date(time_entry.get("DepartingTime"))
            s.arrival_time = _parse_wsf_date(time_entry.get("ArrivingTime"))
            s.vessel_id = int(time_entry.get("VesselID", 0) or 0)
            s.vessel_name = time_entry.get("VesselName", "") or ""
            s.sailing_id = int(time_entry.get("SailingID", 0) or 0)
            notes = time_entry.get("Annotations", []) or []
            s.annotations = [str(n) for n in notes if n]
            sailings.append(s)

    return sailings


# Common WSF terminal IDs for convenience
WSF_TERMINALS = {
    "seattle":           1,
    "bainbridge":        3,
    "bremerton":         4,
    "kingston":          7,
    "edmonds":           8,
    "mukilteo":          9,
    "clinton":           10,
    "fauntleroy":        11,
    "vashon":            12,
    "southworth":        13,
    "pt_townsend":       14,
    "coupeville":        15,
    "anacortes":         2,
    "friday_harbor":     20,
    "orcas":             22,
    "shaw":              23,
    "lopez":             24,
}


def get_vessels_in_transit(
    apiaccesscode: str = "",
    timeout: int = 15,
) -> List[FerryVessel]:
    """Convenience: return only vessels currently underway (not at dock)."""
    vessels = get_ferry_vessel_locations(apiaccesscode=apiaccesscode, timeout=timeout)
    return [v for v in vessels if not v.at_dock and v.in_service]


# =============================================================================
# WORK ZONES (WZDx v4.2)
# =============================================================================

@dataclass
class WorkZone:
    """A highway work zone from the WZDx GeoJSON feed."""
    feature_id: str = ""
    road_name: str = ""
    direction: str = ""
    vehicle_impact: str = ""
    beginning_milepost: Optional[float] = None
    ending_milepost: Optional[float] = None
    start_date: str = ""
    end_date: str = ""
    is_start_date_verified: bool = False
    is_end_date_verified: bool = False
    description: str = ""
    status: str = ""
    restrictions: List[Dict] = field(default_factory=list)
    lane_count: int = 0
    geometry_type: str = ""
    coordinates: List = field(default_factory=list)
    speed_limit: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_active(self) -> bool:
        """Returns True if status is active."""
        return self.status.lower() in ("active", "pending")


@dataclass
class WZDxDevice:
    """A WZDx field device (arrow board, dynamic message sign, camera)."""
    feature_id: str = ""
    device_type: str = ""
    road_name: str = ""
    milepost: Optional[float] = None
    status: str = ""
    messages: List[str] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_work_zones(timeout: int = 15) -> List[WorkZone]:
    """
    Fetch active work zones from WSDOT WZDx v4.2 GeoJSON feed (no auth required).

    Endpoint:
      GET https://wzdx.wsdot.wa.gov/api/v4/wzdx

    Returns WZDx FeatureCollection items as WorkZone objects.
    """
    url = "https://wzdx.wsdot.wa.gov/api/v4/wzdx"
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    zones: List[WorkZone] = []
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        geom = feature.get("geometry", {}) or {}
        wz = WorkZone()
        wz.feature_id = feature.get("id", "") or ""
        core = props.get("core_details", {}) or {}
        wz.road_name = core.get("road_names", [""])[0] if core.get("road_names") else ""
        wz.direction = core.get("direction", "") or ""
        wz.vehicle_impact = props.get("vehicle_impact", "") or ""
        wz.beginning_milepost = _to_float(props.get("beginning_milepost"))
        wz.ending_milepost = _to_float(props.get("ending_milepost"))
        wz.start_date = props.get("start_date", "") or ""
        wz.end_date = props.get("end_date", "") or ""
        wz.is_start_date_verified = bool(props.get("is_start_date_verified", False))
        wz.is_end_date_verified = bool(props.get("is_end_date_verified", False))
        wz.description = core.get("description", "") or ""
        wz.status = props.get("event_status", props.get("work_zone_type", "")) or ""
        wz.lane_count = len(props.get("lanes", []) or [])
        wz.restrictions = props.get("restrictions", []) or []
        wz.speed_limit = _to_float(props.get("reduced_speed_limit_kph"))
        if wz.speed_limit:
            wz.speed_limit = round(wz.speed_limit * 0.621371, 1)   # kph -> mph
        wz.geometry_type = geom.get("type", "") or ""
        wz.coordinates = geom.get("coordinates", []) or []
        zones.append(wz)

    return zones


def fetch_wzdx_devices(timeout: int = 15) -> List[WZDxDevice]:
    """
    Fetch WZDx field devices (DMS, arrow boards, etc.) from WSDOT (no auth).

    Endpoint:
      GET https://wzdx.wsdot.wa.gov/api/v4/wzdxfd

    Returns WZDx FeatureCollection items as WZDxDevice objects.
    """
    url = "https://wzdx.wsdot.wa.gov/api/v4/wzdxfd"
    req = urllib.request.Request(url, headers={
        "User-Agent": "WSDOTClient/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    devices: List[WZDxDevice] = []
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        geom = feature.get("geometry", {}) or {}
        dev = WZDxDevice()
        dev.feature_id = feature.get("id", "") or ""
        core = props.get("core_details", {}) or {}
        dev.device_type = core.get("device_type", "") or ""
        road_names = core.get("road_names", []) or []
        dev.road_name = road_names[0] if road_names else ""
        dev.status = core.get("device_status", "") or ""
        dev.messages = props.get("message_display_text", []) or []
        if isinstance(dev.messages, str):
            dev.messages = [dev.messages]
        coords = geom.get("coordinates", [])
        if coords and len(coords) >= 2:
            dev.longitude = _to_float(coords[0])
            dev.latitude = _to_float(coords[1])
        devices.append(dev)

    return devices


def get_active_work_zones(
    road_name: str = "",
    timeout: int = 15,
) -> List[WorkZone]:
    """Convenience: return only active work zones, optionally filtered by road name."""
    zones = fetch_work_zones(timeout=timeout)
    result = [z for z in zones if z.is_active]
    if road_name:
        road_upper = road_name.upper()
        result = [z for z in result if road_upper in z.road_name.upper()]
    return result


# =============================================================================
# HELPER UTILITIES
# =============================================================================

def _to_float(val) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_wsdot_date(val: str) -> str:
    """
    Convert WSDOT /Date(milliseconds-offset)/ format to ISO 8601.
    Handles both WSDOT REST format and plain strings.
    """
    if not val:
        return ""
    m = re.search(r"/Date\((\d+)([-+]\d{4})?\)/", str(val))
    if m:
        ms = int(m.group(1))
        offset = m.group(2) or "+0000"
        dt = datetime.utcfromtimestamp(ms / 1000.0)
        try:
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + offset[:3] + ":" + offset[3:]
        except Exception:
            return dt.isoformat() + "Z"
    return str(val)


# =============================================================================
# WSDOT ENDPOINTS REFERENCE
# =============================================================================

WSDOT_ENDPOINTS: Dict[str, Dict] = {
    # ── Cameras ────────────────────────────────────────────────────────────
    "cameras_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetCamerasAsJson?AccessCode={code}",
            "GetCameraAsJson?AccessCode={code}&CameraID={id}",
            "SearchCamerasAsJson?AccessCode={code}&StateRoute={sr}&Region={region}",
        ],
        "format": "JSON",
        "notes": "Full metadata including coordinates, direction, owner, operating agency",
    },
    "cameras_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/rss.aspx",
        "auth": "none",
        "methods": ["GET (optional: StateRoute, Region)"],
        "format": "RSS/XML",
    },
    "cameras_kml": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/kml.aspx",
        "auth": "none",
        "methods": ["GET"],
        "format": "KML",
        "notes": "Contains GPS coordinates for all cameras",
    },
    "camera_images": {
        "url": "https://images.wsdot.wa.gov/{region}/{route3d}vc{milepost5d}.jpg",
        "auth": "none",
        "notes": "Region codes: er,nc,nw,ol,sc,sw,wsf,rweather,spokane,airports,traffic",
        "example": "https://images.wsdot.wa.gov/sc/090vc05200.jpg",
    },

    # ── Mountain Pass Conditions ────────────────────────────────────────────
    "mountain_pass_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/MountainPassConditionsREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetMountainPassConditionsAsJson?AccessCode={code}",
            "GetMountainPassConditionAsJson?AccessCode={code}&PassConditionID={id}",
        ],
        "format": "JSON",
    },
    "mountain_pass_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── Traffic Flow ────────────────────────────────────────────────────────
    "traffic_flow_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/TrafficFlowREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetTrafficFlowsAsJson?AccessCode={code}",
            "GetTrafficFlowsAsJson?AccessCode={code}&StateRoute={sr}",
            "GetTrafficFlowsAsJson?AccessCode={code}&Region={region}",
        ],
        "format": "JSON",
    },
    "traffic_flow_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/TrafficFlow/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── Travel Times ────────────────────────────────────────────────────────
    "travel_times_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/TravelTimes/TravelTimesREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetTravelTimesAsJson?AccessCode={code}",
            "GetTravelTimeAsJson?AccessCode={code}&TravelTimeID={id}",
        ],
        "format": "JSON",
    },
    "travel_times_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/TravelTimes/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── Highway Alerts ─────────────────────────────────────────────────────
    "highway_alerts_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/HighwayAlertsREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetAlertsAsJson?AccessCode={code}",
            "GetAlertAsJson?AccessCode={code}&AlertID={id}",
            "GetAlertsAsJson?AccessCode={code}&StateRoute={sr}",
            "GetAlertsAsJson?AccessCode={code}&Region={region}",
            "GetAlertsAsJson?AccessCode={code}&County={county}",
            "GetAlertsAsJson?AccessCode={code}&StartSeverity={severity}",
        ],
        "format": "JSON",
    },
    "highway_alerts_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
        "params": "StateRoute, Region, County, StartSeverity (all optional)",
    },

    # ── Weather Stations ────────────────────────────────────────────────────
    "weather_stations_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/WeatherStation/WeatherStationREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetCurrentWeatherInformationAsJson?AccessCode={code}",
            "GetCurrentStationWeatherInformationAsJson?AccessCode={code}&StationID={id}",
        ],
        "format": "JSON",
    },
    "weather_stations_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/WeatherStation/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── Commercial Vehicle Services ─────────────────────────────────────────
    "cv_restrictions_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/CVRestrictions/CVRestrictionsREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetCommercialVehicleRestrictionsAsJson?AccessCode={code}",
            "GetCommercialVehicleRestrictionAsJson?AccessCode={code}&RestrictionID={id}",
        ],
        "format": "JSON",
        "notes": "Commercial vehicle restrictions, oversize/overweight permits",
    },
    "cv_restrictions_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/CVRestrictions/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── Bridge Clearances ────────────────────────────────────────────────────
    "bridge_clearances_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/BridgeClearances/BridgeClearancesREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetBridgeClearancesAsJson?AccessCode={code}",
            "GetBridgeClearanceAsJson?AccessCode={code}&BridgeDataID={id}",
        ],
        "format": "JSON",
    },

    # ── Border Crossings ─────────────────────────────────────────────────────
    "border_crossings_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/BorderCrossings/BorderCrossingsREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetBorderCrossingsAsJson?AccessCode={code}",
        ],
        "format": "JSON",
        "notes": "Wait times at US/Canada border crossings in Washington",
    },
    "border_crossings_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/BorderCrossings/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── Toll Rates ─────────────────────────────────────────────────────────
    "toll_rates_rest": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/TollRates/TollRatesREST.svc",
        "auth": "AccessCode",
        "methods": [
            "GetTollRatesAsJson?AccessCode={code}",
        ],
        "format": "JSON",
        "notes": "Dynamic toll rates for SR-99, SR-520, I-405 express toll lanes",
    },
    "toll_rates_rss": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/TollRates/rss.aspx",
        "auth": "none",
        "format": "RSS/XML",
    },

    # ── SOAP/WSDL (all services also have SOAP interface) ───────────────────
    "cameras_wsdl": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc?wsdl",
        "auth": "AccessCode",
        "format": "SOAP/WSDL",
    },
    "mountain_pass_wsdl": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/MountainPassConditionsREST.svc?wsdl",
        "auth": "AccessCode",
        "format": "SOAP/WSDL",
    },

    # ── Washington State Ferries (WSF) ──────────────────────────────────────
    "wsf_vessel_locations": {
        "url": "https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vessellocations",
        "auth": "optional apiaccesscode param",
        "format": "JSON",
        "notes": "Real-time vessel positions, heading, speed, ETA",
    },
    "wsf_vessel_basics": {
        "url": "https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vesselbasics",
        "auth": "optional",
        "format": "JSON",
        "notes": "Fleet list with vessel specifications",
    },
    "wsf_terminals": {
        "url": "https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalbasics",
        "auth": "optional",
        "format": "JSON",
    },
    "wsf_schedule_today": {
        "url": "https://www.wsdot.wa.gov/ferries/api/schedule/rest/latest/scheduletoday/{dep}/{arr}/false",
        "auth": "optional",
        "format": "JSON",
        "notes": "Replace {dep} and {arr} with terminal IDs",
    },
    "wsf_schedule_date": {
        "url": "https://www.wsdot.wa.gov/ferries/api/schedule/rest/latest/schedule/{dep}/{arr}/{date}",
        "auth": "optional",
        "format": "JSON",
        "notes": "Date in YYYY-MM-DD format; dates use /Date(ms-offset)/ format in response",
    },
    "wsf_schedule_valid": {
        "url": "https://www.wsdot.wa.gov/ferries/api/schedule/rest/latest/valid",
        "auth": "optional",
        "format": "JSON",
        "notes": "Lists all valid route combinations",
    },
    "wsf_vessel_verbose": {
        "url": "https://www.wsdot.wa.gov/ferries/api/vessels/rest/latest/vesselverbose",
        "auth": "optional",
        "format": "JSON",
        "notes": "Full vessel details including capacity, dimensions, built year",
    },
    "wsf_terminal_waittime": {
        "url": "https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalwaittimes",
        "auth": "optional",
        "format": "JSON",
        "notes": "Current drive-up wait times at terminals",
    },
    "wsf_terminal_bulletins": {
        "url": "https://www.wsdot.wa.gov/ferries/api/terminals/rest/latest/terminalbulletins",
        "auth": "optional",
        "format": "JSON",
        "notes": "Alerts and service bulletins for each terminal",
    },

    # ── WZDx Work Zones ─────────────────────────────────────────────────────
    "wzdx_work_zones": {
        "url": "https://wzdx.wsdot.wa.gov/api/v4/wzdx",
        "auth": "none",
        "format": "GeoJSON (WZDx v4.2)",
        "notes": "Active work zones statewide; FeatureCollection of WorkZone features",
    },
    "wzdx_devices": {
        "url": "https://wzdx.wsdot.wa.gov/api/v4/wzdxfd",
        "auth": "none",
        "format": "GeoJSON (WZDx v4.2)",
        "notes": "Field devices: DMS, arrow boards, cameras in work zones",
    },

    # ── API Registration ──────────────────────────────────────────────────
    "api_registration": {
        "url": "https://www.wsdot.wa.gov/Traffic/api/",
        "auth": "free registration",
        "notes": "Register for AccessCode; also provides SOAP WSDL links for all 13 services",
    },
}


if __name__ == "__main__":
    _demo()
