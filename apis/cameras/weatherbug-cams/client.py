"""
WeatherBug Camera API Client
============================
Reverse-engineered from https://www.weatherbug.com/cameras/

Architecture
------------
WeatherBug runs a microservices API infrastructure under the *.pulse.weatherbug.net
domain namespace, accessed via HMAC-SHA256 signed requests.

Authentication
--------------
All requests to the Pulse API require three query parameters appended to each request:
  - authid    : Client identifier embedded in the page JS (WBWebV3 for the web client)
  - timestamp : Unix timestamp in seconds (integer)
  - hash      : HMAC-SHA256 of a canonical request string, base64-encoded

Canonical string format (the message signed):
  METHOD\n
  /path\n
  body_or_empty_string\n
  timestamp
  [\nSORTED_PARAM_KEY\nSORTED_PARAM_VALUE\n...]

Parameters are sorted case-insensitively. The HMAC uses the Pulse.Secret as the key.

Credentials (web client, embedded in page HTML):
  Pulse.ID     : WBWebV3
  Pulse.Secret : 48f00e3e43804ffd98a112f45fc299a5

Service Base URLs (from window._config.BaseURLs)
-------------------------------------------------
  Cameras      : https://web-cam.pulse.weatherbug.net
  Traffic Cams : https://web-trffc.pulse.weatherbug.net
  Observations : https://web-obs.pulse.weatherbug.net
  Forecasts    : https://web-for.pulse.weatherbug.net
  Locations    : https://web-loc.pulse.weatherbug.net
  AQI          : https://web-aqi.pulse.weatherbug.net
  Pollen       : https://web-plln.pulse.weatherbug.net
  Maps/GIV     : https://web-maps.pulse.weatherbug.net
  Maps API CDN : https://web-maps.api.weatherbug.net  (tile raster CDN)
  Alerts       : https://web-alert.pulse.weatherbug.net
  Lightning    : https://web-lx.pulse.weatherbug.net
  Hurricane    : https://web-hur.pulse.weatherbug.net
  UV Index     : https://web-uv.pulse.weatherbug.net
  SnowSki      : https://web-snwski.pulse.weatherbug.net
  Lifestyle    : https://web-life.pulse.weatherbug.net

Camera Image CDN (no auth required)
------------------------------------
  Base  : https://cameras-cam.cdn.weatherbug.net
  URL   : https://cameras-cam.cdn.weatherbug.net/{STATION_ID}/{YYYY}/{MM}/{DD}/{MMDDYYHHmm}_{size}.jpg
  Sizes : _l (large/full ~150KB), _t (thumbnail ~7KB), _s (small ~16KB)
  Example: https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/032720261259_l.jpg

Traffic Camera Image CDN (proxied, no additional auth required beyond the token in URL)
  Trafficland CDN: https://ie.trafficland.com/v2.0/{id}/{size}?system=weatherbug-web&pubtoken={token}
  Cached proxy   : https://cmn-trffc.pulse.weatherbug.net/media/trffc/v2/img/{size}?system=weatherbug-web&id={id}&key={token}
  Sizes: huge, full, half

Map Tile CDN
  Template : https://{subdomain}web-maps.api.weatherbug.net/{layerId}/{z}/{x}/{y}.png
  Subdomains: a, b, c, d  (from GivDomains)
  Layer IDs: Radar.Global, GlobalSatellite, lxflash-radar-consumer-web, Contour.Observed.Pollen.Blur,
             nws-alerts, en-alerts, Contour.Observed.Temperature, lxflash-consumer, etc.

Discovered Endpoints
--------------------
GET /data/cameras/v2/CameraList
  Base : web-cam.pulse.weatherbug.net
  Params: la (latitude), lo (longitude), r (radius miles), ns (max stations), ii (include images bool int),
          verbose

GET /data/cameras/v2/CameraAnimations
  Base : web-cam.pulse.weatherbug.net
  Params: ci (camera/station ID), itl (include timelapse history, int 0/1)

GET /data/traffic/v2
  Base : web-trffc.pulse.weatherbug.net
  Params: location ({lat},{lon}), locationType (latitudelongitude), radius (int, meters),
          maxCount, verbose

GET /data/observations/v4/current
  Base : web-obs.pulse.weatherbug.net
  Params: location ({lat},{lon}), locationtype (latitudelongitude), units (int: 1=imperial, 2=metric),
          verbose

GET /data/forecasts/v2/daily
  Base : web-for.pulse.weatherbug.net
  Params: location ({lat},{lon}), locationtype (latitudelongitude), units (int 1/2), verbose

GET /data/forecasts/v2/hourly
  Base : web-for.pulse.weatherbug.net
  Params: location ({lat},{lon}), locationtype (latitudelongitude), units (int 1/2), verbose

GET /data/locations/v3/location
  Base : web-loc.pulse.weatherbug.net
  Params: searchString (city name, zip code, or partial city), maxResults (int), verbose

GET /data/locations/v3/bySlugName
  Base : web-loc.pulse.weatherbug.net
  Params: slugname (e.g. "new-york-ny-10001"), verbose

GET /data/locations/v3/closestCity
  Base : web-loc.pulse.weatherbug.net
  Params: location ({lat},{lon}), locationtype (latitudelongitude), verbose

GET /data/locations/v1/CityByCityId
  Base : web-loc.pulse.weatherbug.net
  Params: cityId (e.g. "US36N0028"), verbose

GET /data/lifestyle/pollen/v1/forecast
  Base : web-plln.pulse.weatherbug.net
  Params: latitude, longitude, verbose

GET /giv/layers/v1
  Base : web-maps.pulse.weatherbug.net
  Params: ViewedLocationLatitude, ViewedLocationLongitude

GET /giv/presentation/legenddata
  Base : web-maps.pulse.weatherbug.net
  Params: lid (layer id), ViewedLocationLatitude, ViewedLocationLongitude

Usage
-----
    client = WeatherBugClient()

    # Search for cameras near New York City
    cameras = client.get_weather_cameras_by_coords(40.71, -74.01, radius_miles=100)
    for cam in cameras:
        print(cam['name'], cam['id'])
        detail = client.get_camera_detail(cam['id'], include_timelapse=True)
        print(detail['Image'])  # latest image URL

    # Search by zip code
    loc = client.search_location("10001")[0]
    cameras = client.get_weather_cameras_by_coords(loc['Latitude'], loc['Longitude'])

    # Traffic cameras
    traffic = client.get_traffic_cameras(40.71, -74.01, radius_meters=10000)
    for cam in traffic:
        print(cam['name'], cam['largeImageUrl'])

    # Current weather at location
    obs = client.get_current_observations(40.71, -74.01)
    print(obs['observation']['temperature'], obs['observation']['iconDescription'])

    # Daily forecast
    forecast = client.get_daily_forecast(40.71, -74.01)

    # Map layers available
    layers = client.get_map_layers(40.71, -74.01)
    for layer in layers:
        print(layer['l'], '->', layer['id'])
        tile_url = client.get_map_tile_url(layer['id'], z=5, x=8, y=12)
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import base64
import time
import re
from typing import Optional, Union
from urllib.parse import urlencode, urljoin

try:
    import requests
    from requests import Session, Response
except ImportError:
    raise ImportError("requests is required: pip install requests")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Credentials embedded in page JS at https://www.weatherbug.com
# (window._config.Pulse)
DEFAULT_AUTH_ID = "WBWebV3"
DEFAULT_SECRET  = "48f00e3e43804ffd98a112f45fc299a5"

# Service base URLs (from window._config.BaseURLs)
CAMERAS_BASE    = "https://web-cam.pulse.weatherbug.net"
TRAFFIC_BASE    = "https://web-trffc.pulse.weatherbug.net"
OBS_BASE        = "https://web-obs.pulse.weatherbug.net"
FORECAST_BASE   = "https://web-for.pulse.weatherbug.net"
LOCATIONS_BASE  = "https://web-loc.pulse.weatherbug.net"
AQI_BASE        = "https://web-aqi.pulse.weatherbug.net"
POLLEN_BASE     = "https://web-plln.pulse.weatherbug.net"
MAPS_BASE       = "https://web-maps.pulse.weatherbug.net"
ALERTS_BASE     = "https://web-alert.pulse.weatherbug.net"
LIGHTNING_BASE  = "https://web-lx.pulse.weatherbug.net"
HURRICANE_BASE  = "https://web-hur.pulse.weatherbug.net"
UV_BASE         = "https://web-uv.pulse.weatherbug.net"
SNOWSKI_BASE    = "https://web-snwski.pulse.weatherbug.net"

# Camera image CDN (public, no auth required)
CAM_IMAGE_CDN   = "https://cameras-cam.cdn.weatherbug.net"

# Map tile CDN (sub-domains: a, b, c, d)
MAPS_TILE_CDN   = "https://{sub}web-maps.api.weatherbug.net"
MAPS_SUBDOMAINS = ["a", "b", "c", "d"]

# Icon CDN
ICON_CDN        = "https://legacyicons-con.cdn.weatherbug.net"


# ---------------------------------------------------------------------------
# HMAC helper
# ---------------------------------------------------------------------------

def _compute_hmac(
    method: str,
    path: str,
    params: dict,
    secret: str,
    auth_id: str,
    body: str = "",
    timestamp: Optional[int] = None,
) -> dict:
    """
    Compute WeatherBug Pulse HMAC signature.

    Implements the PulseHmac.getHashedURL algorithm found in main.js (module 8349):

        message = METHOD\\n/path\\nbody\\ntimestamp[\\nPARAM_KEY\\nPARAM_VALUE...]

    Parameters are sorted case-insensitively. Body defaults to empty string.
    Returns dict with keys: hash, authid, timestamp.
    """
    if timestamp is None:
        timestamp = int(time.time())

    method = method.upper()
    if not path.startswith("/"):
        path = "/" + path

    # Sort params alphabetically (case-insensitive), skip None values
    param_parts: list[str] = []
    if params:
        sorted_keys = sorted(params.keys(), key=lambda k: k.upper())
        for k in sorted_keys:
            if params[k] is not None:
                param_parts.append(f"{k}\n{params[k]}")

    message = f"{method}\n{path}\n{body or ''}\n{timestamp}"
    if param_parts:
        message += "\n" + "\n".join(param_parts)

    raw = _hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    )
    hash_b64 = base64.b64encode(raw.digest()).decode("utf-8")

    return {"hash": hash_b64, "authid": auth_id, "timestamp": timestamp}


# ---------------------------------------------------------------------------
# Camera CDN helpers
# ---------------------------------------------------------------------------

def build_camera_image_url(
    station_id: str,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    size: str = "l",
) -> str:
    """
    Build a direct CDN URL for a WeatherBug weather camera image.

    CDN pattern (no auth required):
        https://cameras-cam.cdn.weatherbug.net/{STATION}/{YYYY}/{MM}/{DD}/{MMDDYYHHmm}_{size}.jpg

    Sizes:
        'l' - large (full resolution, ~150 KB)
        't' - thumbnail (~7 KB)
        's' - small (~16 KB)

    Example:
        build_camera_image_url("YRKPS", 2026, 3, 27, 12, 59)
        => "https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/032720261259_l.jpg"
    """
    timestamp_part = f"{month:02d}{day:02d}{year % 100:02d}{hour:02d}{minute:02d}"
    return (
        f"{CAM_IMAGE_CDN}/{station_id}/"
        f"{year}/{month:02d}/{day:02d}/"
        f"{timestamp_part}_{size}.jpg"
    )


def build_map_tile_url(layer_id: str, z: int, x: int, y: int, subdomain: str = "a") -> str:
    """
    Build a WeatherBug GIV map tile URL.

    Format: https://{sub}web-maps.api.weatherbug.net/{layerId}/{z}/{x}/{y}.png
    Subdomains: a, b, c, d

    Known layer IDs (from /giv/layers/v1):
        Radar.Global              - Global radar
        lxflash-radar-consumer-web - Storm tracker (lightning + radar)
        GlobalSatellite           - IR satellite
        Contour.Observed.Pollen.Blur - Pollen
        nws-alerts                - NWS alerts
        en-alerts                 - Earth Networks dangerous thunderstorm alerts
        lxflash-consumer          - Lightning only
        Contour.Observed.DailyRain - Precipitation
        Contour.Observed.Temperature - Temperature
        Observed.Temperature      - Local temperature stations
        Contour.Observed.Pressure.SeaLevel - Pressure
        Contour.Observed.Temperature.HeatIndex - Heat index
        Contour.Observed.WindChill - Wind chill
        Contour.Observed.Humidity - Humidity
        Contour.Observed.Wind     - Wind speed
    """
    base = MAPS_TILE_CDN.format(sub=subdomain)
    return f"{base}/{layer_id}/{z}/{x}/{y}.png"


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class WeatherBugClient:
    """
    Python client for the WeatherBug Pulse API.

    Provides access to:
    - Weather cameras (list by location, get image URLs and timelapse)
    - Traffic cameras (list by location, get image URLs)
    - Location search (by name, zip code, coordinates, or slug)
    - Current weather observations
    - Daily and hourly forecasts
    - Pollen data
    - Map tile layers (radar, satellite, pollen, etc.)

    Authentication is handled automatically via HMAC-SHA256 signing.
    The default credentials are the publicly embedded web client keys.
    """

    def __init__(
        self,
        auth_id: str = DEFAULT_AUTH_ID,
        secret: str = DEFAULT_SECRET,
        timeout: int = 15,
        session: Optional[Session] = None,
    ):
        """
        Initialize the WeatherBug client.

        Parameters
        ----------
        auth_id  : Pulse auth ID (default: WBWebV3 - the embedded web client ID)
        secret   : Pulse HMAC secret (default: embedded web client secret)
        timeout  : HTTP request timeout in seconds
        session  : Optional existing requests.Session to reuse
        """
        self.auth_id = auth_id
        self.secret  = secret
        self.timeout = timeout
        self.session = session or Session()

        # Set default headers to match browser requests
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.weatherbug.com",
            "Referer": "https://www.weatherbug.com/",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        base_url: str,
        path: str,
        params: Optional[dict] = None,
        signed: bool = True,
    ) -> dict:
        """
        Perform a signed (or unsigned) GET request to a Pulse service.

        Raises requests.HTTPError on non-2xx status codes.
        """
        params = {k: v for k, v in (params or {}).items() if v is not None}

        if signed:
            sig = _compute_hmac(
                "GET", path, params, self.secret, self.auth_id
            )
            params = {**params, **sig}

        url = base_url.rstrip("/") + "/" + path.lstrip("/")
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Location search
    # ------------------------------------------------------------------

    def search_location(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict]:
        """
        Search for locations by city name, zip/postal code, or partial string.

        Parameters
        ----------
        query       : Search string (e.g. "Denver", "10001", "New York")
        max_results : Maximum number of results to return (default 10)

        Returns
        -------
        List of location dicts with keys:
            CityId, CityName, TerritoryName, TerritoryAbbr, CountryIso2Code,
            Latitude, Longitude, PostalCode, SlugName, DisplayCompositeName

        Example
        -------
            results = client.search_location("Denver")
            lat, lon = results[0]['Latitude'], results[0]['Longitude']
        """
        data = self._get(
            LOCATIONS_BASE,
            "/data/locations/v3/location",
            {"searchString": query, "maxResults": max_results, "verbose": "true"},
        )
        if isinstance(data, list):
            return data
        return data.get("Result") or []

    def get_location_by_slug(self, slug_name: str) -> dict:
        """
        Look up a location by its WeatherBug slug name.

        Slug format: "{city}-{state-abbr}-{zip}"  e.g. "new-york-ny-10001"

        Parameters
        ----------
        slug_name : WeatherBug location slug

        Returns
        -------
        Location dict with Latitude, Longitude, CityId, etc.
        """
        return self._get(
            LOCATIONS_BASE,
            "/data/locations/v3/bySlugName",
            {"slugname": slug_name, "verbose": "true"},
        )

    def get_closest_city(
        self,
        lat: float,
        lon: float,
    ) -> dict:
        """
        Find the closest city to given coordinates.

        Parameters
        ----------
        lat : Latitude
        lon : Longitude

        Returns
        -------
        Location dict with CityId, CityName, SlugName, Latitude, Longitude, PostalCode, etc.

        Example
        -------
            city = client.get_closest_city(40.71, -74.01)
            print(city['DisplayCompositeName'])  # "New York City, New York"
        """
        return self._get(
            LOCATIONS_BASE,
            "/data/locations/v3/closestCity",
            {
                "location": f"{lat},{lon}",
                "locationtype": "latitudelongitude",
                "verbose": "true",
            },
        )

    def get_city_by_id(self, city_id: str) -> dict:
        """
        Fetch city details by WeatherBug city ID (e.g. "US36N0028").

        Parameters
        ----------
        city_id : WeatherBug city identifier

        Returns
        -------
        Location dict including SlugName, AqiId, ForecastZoneId, etc.
        """
        data = self._get(
            LOCATIONS_BASE,
            "/data/locations/v1/CityByCityId",
            {"cityId": city_id, "verbose": "true"},
        )
        return data.get("Result") or data

    # ------------------------------------------------------------------
    # Weather cameras
    # ------------------------------------------------------------------

    def get_weather_cameras_by_coords(
        self,
        lat: float,
        lon: float,
        radius_miles: int = 100,
        max_stations: int = 20,
        include_images: bool = False,
    ) -> list[dict]:
        """
        List weather cameras within a radius of the given coordinates.

        Parameters
        ----------
        lat           : Latitude of center point
        lon           : Longitude of center point
        radius_miles  : Search radius in miles (max ~3963, default 100)
        max_stations  : Maximum number of cameras to return (default 20)
        include_images: If True, include image URLs in results (default False)

        Returns
        -------
        List of camera dicts with keys:
            id       - Station ID (used to fetch images)
            name     - Camera display name
            lat      - Latitude
            lng      - Longitude
            city     - City name
            state    - State/territory name
            isHD     - Whether the camera supports HD images
            distance - Distance from search center in miles
            image    - Latest image URL (if include_images=True, else None)
            thumbnail- Thumbnail URL (if include_images=True, else None)
            images   - List of recent image URLs (if include_images=True)

        Example
        -------
            cams = client.get_weather_cameras_by_coords(40.71, -74.01, radius_miles=100)
            for cam in cams:
                print(f"{cam['name']} ({cam['id']}) - {cam['distance']:.1f} mi")
        """
        params: dict = {
            "la": lat,
            "lo": lon,
            "r": radius_miles,
            "ns": max_stations,
            "verbose": "true",
        }
        if include_images:
            params["ii"] = 1

        data = self._get(CAMERAS_BASE, "/data/cameras/v2/CameraList", params)
        return data.get("Result") or []

    def get_weather_cameras_by_zip(
        self,
        zip_code: str,
        radius_miles: int = 100,
        max_stations: int = 20,
    ) -> list[dict]:
        """
        List weather cameras near a ZIP/postal code.

        Internally resolves the ZIP to coordinates, then calls
        get_weather_cameras_by_coords().

        Parameters
        ----------
        zip_code     : US ZIP code or international postal code
        radius_miles : Search radius in miles (default 100)
        max_stations : Maximum cameras to return (default 20)

        Returns
        -------
        List of camera dicts (same structure as get_weather_cameras_by_coords)

        Example
        -------
            cams = client.get_weather_cameras_by_zip("90210")
        """
        results = self.search_location(zip_code, max_results=1)
        if not results:
            raise ValueError(f"Could not resolve ZIP code: {zip_code}")
        loc = results[0]
        return self.get_weather_cameras_by_coords(
            loc["Latitude"],
            loc["Longitude"],
            radius_miles=radius_miles,
            max_stations=max_stations,
        )

    def get_camera_detail(
        self,
        camera_id: str,
        include_timelapse: bool = False,
    ) -> dict:
        """
        Fetch details and image URLs for a specific weather camera.

        Parameters
        ----------
        camera_id         : WeatherBug station ID (e.g. "YRKPS")
        include_timelapse : If True, fetch ~24h of historical image URLs

        Returns
        -------
        Camera detail dict with keys:
            Id        - Station ID
            Name      - Camera display name
            City      - City
            State     - State
            Lat       - Latitude
            Lng       - Longitude
            IsHD      - HD support flag
            Image     - Latest image URL (large, _l suffix)
            Thumbnail - Latest thumbnail URL (_t suffix)
            Images    - List of historical image URLs (if include_timelapse=True)

        Image URL pattern:
            https://cameras-cam.cdn.weatherbug.net/{ID}/{YYYY}/{MM}/{DD}/{MMDDYYHHmm}_{size}.jpg
            Sizes: _l (large), _t (thumbnail), _s (small)

        Example
        -------
            detail = client.get_camera_detail("YRKPS", include_timelapse=True)
            print(detail['Image'])  # https://cameras-cam.cdn.weatherbug.net/YRKPS/...
            for frame in detail['Images']:
                print(frame)  # 24h timelapse frames
        """
        params: dict = {"ci": camera_id}
        if include_timelapse:
            params["itl"] = 1

        data = self._get(CAMERAS_BASE, "/data/cameras/v2/CameraAnimations", params)
        return data.get("Result") or data

    def get_latest_camera_image_url(
        self,
        camera_id: str,
        size: str = "l",
    ) -> str:
        """
        Get the URL of the latest image for a weather camera.

        Parameters
        ----------
        camera_id : WeatherBug station ID
        size      : Image size - 'l' (large), 't' (thumbnail), 's' (small)

        Returns
        -------
        Direct CDN URL string (no authentication required to access the image)

        Example
        -------
            url = client.get_latest_camera_image_url("YRKPS")
            # => "https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/..."
        """
        detail = self.get_camera_detail(camera_id, include_timelapse=False)
        if not detail:
            raise ValueError(f"Camera not found: {camera_id}")
        img = detail.get("Image") or detail.get("Thumbnail")
        if not img:
            raise ValueError(f"No image URL available for camera: {camera_id}")

        # Swap the size suffix if a different size is requested
        if size != "l":
            img = re.sub(r"_[lts]\.jpg$", f"_{size}.jpg", img)
        return img

    # ------------------------------------------------------------------
    # Traffic cameras
    # ------------------------------------------------------------------

    def get_traffic_cameras(
        self,
        lat: float,
        lon: float,
        radius_meters: int = 16000,
        max_count: int = 20,
    ) -> list[dict]:
        """
        List traffic cameras within a radius of the given coordinates.

        Traffic camera imagery is sourced from Trafficland (ie.trafficland.com)
        via WeatherBug's proxy.

        Parameters
        ----------
        lat           : Latitude of center point
        lon           : Longitude of center point
        radius_meters : Search radius in meters (default 16000 ≈ 10 miles)
        max_count     : Maximum number of cameras to return (default 20)

        Returns
        -------
        List of traffic camera dicts with keys:
            cameraId        - Numeric traffic camera ID
            name            - Camera name / location description
            latitude        - Camera latitude
            longitude       - Camera longitude
            distance        - Distance from search center (miles)
            providerName    - Traffic data provider (e.g. "New York City DOT")
            hasStreamingVideo - Whether live video is available
            orientation     - Camera orientation (e.g. "NORTH", "UNKNOWN")
            disabled        - Whether camera is currently offline
            smallImageUrl   - Small image (direct Trafficland URL)
            largeImageUrl   - Large/full image URL (direct Trafficland URL)
            jumboImageUrl   - Jumbo/huge image URL (direct Trafficland URL)
            smallImageUrlCache  - WeatherBug-cached small image
            largeImageUrlCache  - WeatherBug-cached large image
            jumboImageUrlCache  - WeatherBug-cached jumbo image

        Trafficland URL pattern:
            https://ie.trafficland.com/v2.0/{id}/{size}?system=weatherbug-web&pubtoken={token}&refreshRate=30000
            Sizes: half (small), full (large), huge (jumbo)

        WeatherBug proxy URL pattern:
            https://cmn-trffc.pulse.weatherbug.net/media/trffc/v2/img/{size}?system=weatherbug-web&id={id}&key={token}&rate=30000
            Sizes: small, large, jumbo

        Example
        -------
            cams = client.get_traffic_cameras(40.71, -74.01, radius_meters=5000)
            for cam in cams:
                print(cam['name'], cam['largeImageUrl'])
        """
        data = self._get(
            TRAFFIC_BASE,
            "/data/traffic/v2",
            {
                "location": f"{lat},{lon}",
                "locationType": "latitudelongitude",
                "radius": radius_meters,
                "maxCount": max_count,
                "verbose": "true",
            },
        )
        result = data.get("result") or data.get("Result") or {}
        return result.get("cameras") or []

    def get_traffic_cameras_by_zip(
        self,
        zip_code: str,
        radius_meters: int = 16000,
        max_count: int = 20,
    ) -> list[dict]:
        """
        List traffic cameras near a ZIP/postal code.

        Parameters
        ----------
        zip_code      : US ZIP code or postal code
        radius_meters : Search radius in meters (default 16000 ≈ 10 miles)
        max_count     : Maximum cameras to return (default 20)

        Returns
        -------
        List of traffic camera dicts (same structure as get_traffic_cameras)
        """
        results = self.search_location(zip_code, max_results=1)
        if not results:
            raise ValueError(f"Could not resolve ZIP code: {zip_code}")
        loc = results[0]
        return self.get_traffic_cameras(
            loc["Latitude"],
            loc["Longitude"],
            radius_meters=radius_meters,
            max_count=max_count,
        )

    # ------------------------------------------------------------------
    # Weather observations
    # ------------------------------------------------------------------

    def get_current_observations(
        self,
        lat: float,
        lon: float,
        units: int = 1,
    ) -> dict:
        """
        Get current weather observations for a location.

        Parameters
        ----------
        lat   : Latitude
        lon   : Longitude
        units : Unit system - 1 = Imperial (°F, mph, inches), 2 = Metric (°C, km/h, mm)

        Returns
        -------
        Dict with keys:
            observation - Current conditions dict including:
                temperature, humidity, windSpeed, windDirection,
                dewPoint, pressureSeaLevel, visibility, feelsLike,
                rainDaily, snowDaily, iconCode, iconDescription,
                observationTimeUtcStr, stationId, providerId
            highLow - Today's high/low values
            station - Station metadata (name, lat, lon, elevation)

        Example
        -------
            obs = client.get_current_observations(40.71, -74.01)
            print(f"{obs['observation']['temperature']}°F, {obs['observation']['iconDescription']}")
        """
        return self._get(
            OBS_BASE,
            "/data/observations/v4/current",
            {
                "location": f"{lat},{lon}",
                "locationtype": "latitudelongitude",
                "units": units,
                "verbose": "true",
            },
        )

    # ------------------------------------------------------------------
    # Forecasts
    # ------------------------------------------------------------------

    def get_daily_forecast(
        self,
        lat: float,
        lon: float,
        units: int = 1,
    ) -> dict:
        """
        Get the 10-day daily weather forecast for a location.

        Parameters
        ----------
        lat   : Latitude
        lon   : Longitude
        units : Unit system - 1 = Imperial, 2 = Metric

        Returns
        -------
        Dict with keys:
            forecastCreatedUtcStr - When forecast was generated
            location              - WeatherBug city ID
            locationType          - "city"
            dailyForecastPeriods  - List of daily period dicts, each with:
                forecastDateLocalStr, iconCode, temperature, isNightTimePeriod,
                summaryDescription, detailedDescription, precipProbability

        Example
        -------
            forecast = client.get_daily_forecast(40.71, -74.01)
            for day in forecast['dailyForecastPeriods'][:5]:
                print(day['forecastDateLocalStr'][:10], day['temperature'], day['summaryDescription'])
        """
        return self._get(
            FORECAST_BASE,
            "/data/forecasts/v2/daily",
            {
                "location": f"{lat},{lon}",
                "locationtype": "latitudelongitude",
                "units": units,
                "verbose": "true",
            },
        )

    def get_hourly_forecast(
        self,
        lat: float,
        lon: float,
        units: int = 1,
    ) -> dict:
        """
        Get the hourly weather forecast for a location.

        Parameters
        ----------
        lat   : Latitude
        lon   : Longitude
        units : Unit system - 1 = Imperial, 2 = Metric

        Returns
        -------
        Dict with keys:
            hourlyForecastPeriod - List of hourly period dicts, each with:
                forecastDateLocalStr, forecastDateUtcStr,
                temperature, feelsLike, dewPoint, iconCode, description,
                windSpeed, windDirectionDegrees, relativeHumidity,
                precipProbability, precipCode, precipRate, snowRate,
                cloudCoverPercent, thunderstormProbability, surfacePressure

        Example
        -------
            forecast = client.get_hourly_forecast(40.71, -74.01)
            for hour in forecast['hourlyForecastPeriod'][:6]:
                print(hour['forecastDateLocalStr'], hour['temperature'], hour['description'])
        """
        return self._get(
            FORECAST_BASE,
            "/data/forecasts/v2/hourly",
            {
                "location": f"{lat},{lon}",
                "locationtype": "latitudelongitude",
                "units": units,
                "verbose": "true",
            },
        )

    # ------------------------------------------------------------------
    # Pollen
    # ------------------------------------------------------------------

    def get_pollen_forecast(
        self,
        lat: float,
        lon: float,
    ) -> dict:
        """
        Get the pollen forecast for a location.

        Parameters
        ----------
        lat : Latitude
        lon : Longitude

        Returns
        -------
        Dict with keys:
            result - Pollen data including:
                pollenIndex   - Numeric pollen index (0-12)
                cityName      - City name
                state         - State abbreviation
                techDiscussion - Detailed pollen narrative
                techDiscussionToday - Today's pollen explanation

        Example
        -------
            pollen = client.get_pollen_forecast(40.71, -74.01)
            print(pollen['result']['pollenIndex'], pollen['result']['techDiscussion'])
        """
        return self._get(
            POLLEN_BASE,
            "/data/lifestyle/pollen/v1/forecast",
            {"latitude": lat, "longitude": lon, "verbose": "true"},
        )

    # ------------------------------------------------------------------
    # Map layers
    # ------------------------------------------------------------------

    def get_map_layers(
        self,
        lat: float,
        lon: float,
    ) -> list[dict]:
        """
        Get the list of available map overlay layers for a location.

        Parameters
        ----------
        lat : Latitude (used to determine regionally available layers)
        lon : Longitude

        Returns
        -------
        List of layer dicts with keys:
            id   - Layer identifier (used to build tile URLs)
            l    - Human-readable layer label
            vid  - Video/layer type identifier
            df   - Data format (e.g. "raster")
            al   - Default opacity
            minz - Minimum zoom level
            maxz - Maximum zoom level
            b    - Bounding box (e, n, s, w)
            d    - Layer description

        To build a tile URL for a layer:
            tile_url = client.build_tile_url(layer['id'], z=5, x=8, y=12)

        Known layer IDs include:
            Radar.Global, GlobalSatellite, lxflash-radar-consumer-web,
            Contour.Observed.Pollen.Blur, nws-alerts, en-alerts,
            lxflash-consumer, Contour.Observed.DailyRain,
            Contour.Observed.Temperature, Contour.Observed.Humidity,
            Contour.Observed.WindChill, Contour.Observed.Pressure.SeaLevel

        Example
        -------
            layers = client.get_map_layers(40.71, -74.01)
            for layer in layers:
                tile_url = client.build_tile_url(layer['id'], z=5, x=8, y=12)
                print(f"{layer['l']}: {tile_url}")
        """
        data = self._get(
            MAPS_BASE,
            "/giv/layers/v1",
            {
                "ViewedLocationLatitude": lat,
                "ViewedLocationLongitude": lon,
            },
        )
        result = data.get("r") or data.get("Result") or {}
        return result.get("ls") or []

    def build_tile_url(
        self,
        layer_id: str,
        z: int,
        x: int,
        y: int,
        subdomain: str = "a",
    ) -> str:
        """
        Build a WeatherBug GIV map tile URL.

        Tile URLs follow the standard XYZ tile format with load-balanced subdomains:
            https://{sub}web-maps.api.weatherbug.net/{layerId}/{z}/{x}/{y}.png
        Where {sub} is one of: a, b, c, d

        Parameters
        ----------
        layer_id  : Layer identifier (e.g. "Radar.Global")
        z         : Zoom level (0-18)
        x         : Tile X coordinate
        y         : Tile Y coordinate
        subdomain : Load balancer subdomain - one of 'a', 'b', 'c', 'd'

        Returns
        -------
        Full tile URL string (PNG image, no auth required)

        Example
        -------
            url = client.build_tile_url("Radar.Global", z=5, x=8, y=12)
            # => "https://aweb-maps.api.weatherbug.net/Radar.Global/5/8/12.png"
        """
        return build_map_tile_url(layer_id, z, x, y, subdomain)

    def get_map_legend(
        self,
        lat: float,
        lon: float,
        layer_id: str,
    ) -> dict:
        """
        Get the legend data for a specific map layer.

        Parameters
        ----------
        lat      : Latitude (location context for the legend)
        lon      : Longitude
        layer_id : Layer identifier (e.g. "radar")

        Returns
        -------
        Legend data dict (structure varies by layer)
        """
        data = self._get(
            MAPS_BASE,
            "/giv/presentation/legenddata",
            {
                "lid": layer_id,
                "ViewedLocationLatitude": lat,
                "ViewedLocationLongitude": lon,
            },
        )
        return data.get("r") or data.get("Result") or data

    # ------------------------------------------------------------------
    # Convenience / search methods
    # ------------------------------------------------------------------

    def find_cameras_near(
        self,
        location: str,
        radius_miles: int = 100,
        max_stations: int = 20,
        camera_type: str = "weather",
    ) -> list[dict]:
        """
        Find cameras (weather or traffic) near a location string.

        This is a convenience wrapper that accepts city names, zip codes,
        or "lat,lon" strings and routes to the appropriate camera API.

        Parameters
        ----------
        location    : Location as city name ("Denver"), ZIP ("80203"),
                      or coordinate pair ("40.71,-74.01")
        radius_miles: Search radius in miles (for weather cameras, default 100)
        max_stations: Maximum results (default 20)
        camera_type : "weather" or "traffic" (default "weather")

        Returns
        -------
        List of camera dicts

        Example
        -------
            cams = client.find_cameras_near("Denver, CO", radius_miles=50)
            cams = client.find_cameras_near("80203", camera_type="traffic")
            cams = client.find_cameras_near("40.71,-74.01")
        """
        # Parse as coordinates if it looks like "lat,lon"
        coord_match = re.match(
            r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", location
        )
        if coord_match:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
        else:
            results = self.search_location(location, max_results=1)
            if not results:
                raise ValueError(f"Location not found: {location!r}")
            lat = results[0]["Latitude"]
            lon = results[0]["Longitude"]

        if camera_type == "traffic":
            radius_meters = int(radius_miles * 1609.34)
            return self.get_traffic_cameras(lat, lon, radius_meters=radius_meters, max_count=max_stations)
        else:
            return self.get_weather_cameras_by_coords(lat, lon, radius_miles=radius_miles, max_stations=max_stations)

    def get_camera_with_weather(
        self,
        camera_id: str,
        include_timelapse: bool = False,
    ) -> dict:
        """
        Get a weather camera's images alongside current weather conditions
        at its location.

        Parameters
        ----------
        camera_id         : WeatherBug station ID (e.g. "YRKPS")
        include_timelapse : Whether to include historical frames (default False)

        Returns
        -------
        Dict with keys:
            camera      - Camera detail dict (from get_camera_detail)
            observation - Current weather observation at camera location
            forecast    - Current day's forecast

        Example
        -------
            data = client.get_camera_with_weather("YRKPS")
            print(data['camera']['Name'])
            print(data['observation']['observation']['temperature'])
        """
        camera = self.get_camera_detail(camera_id, include_timelapse=include_timelapse)
        lat = camera.get("Lat") or camera.get("lat", 0)
        lon = camera.get("Lng") or camera.get("lng", 0)

        obs = None
        forecast = None

        if lat and lon:
            try:
                obs = self.get_current_observations(lat, lon)
            except Exception:
                pass
            try:
                forecast = self.get_daily_forecast(lat, lon)
            except Exception:
                pass

        return {
            "camera": camera,
            "observation": obs,
            "forecast": forecast,
        }


# ---------------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------------

def get_icon_url(
    icon_code: int,
    icon_set: str = "forecast",
    icon_size: str = "svglarge",
) -> str:
    """
    Build a WeatherBug weather icon URL.

    Parameters
    ----------
    icon_code : Numeric weather icon code (e.g. 30 for "Sunny")
    icon_set  : Icon set name (default "forecast")
    icon_size : Icon size (default "svglarge"; also: "svgsmall", "32x32", "64x64")

    Returns
    -------
    URL string to the icon SVG/image

    Notes
    -----
    The icons endpoint uses a special token "99999999-9999-9999-9999-999999999999"
    which appears to be the public/anonymous access token.
    """
    params = urlencode({
        "iconset": icon_set,
        "iconSize": icon_size,
        "iconCode": icon_code,
        "token": "99999999-9999-9999-9999-999999999999",
    })
    return f"{ICON_CDN}/resources/v1/resource/IconByCodeV1?{params}"


# ---------------------------------------------------------------------------
# Example / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    client = WeatherBugClient()

    print("=" * 60)
    print("WeatherBug Camera API - Demo")
    print("=" * 60)

    # 1. Location search
    print("\n[1] Searching for 'Denver, CO'...")
    locs = client.search_location("Denver, CO", max_results=1)
    if locs:
        loc = locs[0]
        print(f"  Found: {loc['DisplayCompositeName']} ({loc['Latitude']}, {loc['Longitude']})")
        lat, lon = loc["Latitude"], loc["Longitude"]
    else:
        lat, lon = 39.7392, -104.9903

    # 2. Weather cameras
    print(f"\n[2] Weather cameras within 150 miles of ({lat}, {lon})...")
    cams = client.get_weather_cameras_by_coords(lat, lon, radius_miles=150, max_stations=5)
    print(f"  Found {len(cams)} cameras")
    for cam in cams[:3]:
        print(f"  - {cam['name']} ({cam['id']}) in {cam.get('city', 'N/A')}, "
              f"{cam.get('state', 'N/A')} - {cam.get('distance', 0):.1f} mi")

    # 3. Camera detail with timelapse
    if cams:
        first_cam = cams[0]
        print(f"\n[3] Fetching detail for {first_cam['name']} ({first_cam['id']})...")
        detail = client.get_camera_detail(first_cam["id"], include_timelapse=False)
        if detail.get("Image"):
            print(f"  Latest image: {detail['Image']}")
        if detail.get("Thumbnail"):
            print(f"  Thumbnail:    {detail['Thumbnail']}")

    # 4. Traffic cameras
    print(f"\n[4] Traffic cameras within 5km of ({lat}, {lon})...")
    traffic = client.get_traffic_cameras(lat, lon, radius_meters=5000, max_count=3)
    print(f"  Found {len(traffic)} traffic cameras")
    for cam in traffic[:3]:
        print(f"  - {cam['name']} (provider: {cam.get('providerName', 'N/A')})")

    # 5. Current observations
    print(f"\n[5] Current weather at ({lat}, {lon})...")
    obs = client.get_current_observations(lat, lon)
    o = obs.get("observation", {})
    print(f"  Temp: {o.get('temperature')}°F, "
          f"Humidity: {o.get('humidity')}%, "
          f"Wind: {o.get('windSpeed')} mph, "
          f"Conditions: {o.get('iconDescription')}")

    # 6. Daily forecast
    print(f"\n[6] 3-day forecast for ({lat}, {lon})...")
    fc = client.get_daily_forecast(lat, lon)
    for day in (fc.get("dailyForecastPeriods") or [])[:3]:
        date = day.get("forecastDateLocalStr", "")[:10]
        print(f"  {date}: {day.get('temperature')}°F - {day.get('summaryDescription', '')[:60]}")

    # 7. Map layers
    print(f"\n[7] Available map layers...")
    layers = client.get_map_layers(lat, lon)
    print(f"  Found {len(layers)} layers:")
    for layer in layers[:5]:
        tile_url = client.build_tile_url(layer["id"], z=5, x=8, y=12)
        print(f"  - {layer['l']} ({layer['id']})")
        print(f"    Tile URL: {tile_url}")

    # 8. CDN URL patterns
    print("\n[8] Camera CDN URL patterns:")
    print(f"  Large:     {CAM_IMAGE_CDN}/{{STATION_ID}}/{{YYYY}}/{{MM}}/{{DD}}/{{MMDDYYHHmm}}_l.jpg")
    print(f"  Thumbnail: {CAM_IMAGE_CDN}/{{STATION_ID}}/{{YYYY}}/{{MM}}/{{DD}}/{{MMDDYYHHmm}}_t.jpg")
    print(f"  Small:     {CAM_IMAGE_CDN}/{{STATION_ID}}/{{YYYY}}/{{MM}}/{{DD}}/{{MMDDYYHHmm}}_s.jpg")
    print()
    print("Demo complete.")
