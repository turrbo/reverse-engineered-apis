"""
Windy.com Internal & Public API Python Client

Reverse-engineered from Windy.com v49.1.1 (JS bundle analysis and network interception).

Discovered API infrastructure:
  - https://node.windy.com       - Main backend API (weather data, services, radar)
  - https://ims.windy.com        - Image map server (weather tile images)
  - https://tiles.windy.com      - Map tiles (geographic tiles)
  - https://api.windy.com        - Public developer API (requires API key)
  - https://account.windy.com    - Account management
  - https://sat.windy.com        - Satellite imagery
  - https://rdr.windy.com        - Radar data
  - https://img.windy.com        - Static images / user avatars

Authentication:
  - Internal endpoints (node.windy.com): Use Accept header with binary format token.
    Some endpoints are publicly accessible without auth.
    Authenticated calls use: Authorization: Bearer {userToken}
    Map tiles use: ?token2={userToken}
  - Public API (api.windy.com): Requires x-windy-api-key header or ?key= param.
    Get a key at https://api.windy.com/keys

Usage:
    # Public API (requires key from https://api.windy.com/keys)
    client = WindyPublicAPIClient(api_key="your_api_key")
    forecast = client.get_point_forecast(lat=50.4, lon=14.3, model="gfs",
                                          levels=["surface"], parameters=["temp", "wind"])

    # Internal API (no key required for most endpoints)
    client = WindyInternalClient()
    location = client.get_location()
    elevation = client.get_elevation(lat=50.0, lon=14.0)
    minifest = client.get_forecast_minifest("ecmwf-hres")

Version: 49.1.1 (reverse-engineered)
JS Bundle hash: indeb7f
"""

import requests
import time
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from urllib.parse import urlencode


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NODE_BASE = "https://node.windy.com"
IMS_BASE = "https://ims.windy.com"
TILES_BASE = "https://tiles.windy.com"
API_BASE = "https://api.windy.com"
SAT_BASE = "https://sat.windy.com"
ACCOUNT_BASE = "https://account.windy.com"

# Internal API version constants discovered in JS bundle
WINDY_VERSION = "49.1.1"
LABELS_VERSION = "v1.7"
TILES_VERSION = "v10.0"

# Custom Accept header used by the Windy web app for internal API calls
# Format: "application/json binary/gladad$ind{hash}" where hash is the build hash
WINDY_ACCEPT_HEADER = "application/json binary/gladad$indeb7f"

# Available forecast models (from JS bundle analysis)
FORECAST_MODELS = {
    # Global models
    "ecmwf-hres": "ECMWF High Resolution (premium)",
    "ecmwf-wam": "ECMWF Wave Model (premium)",
    "gfs": "NOAA GFS Global",
    "gfs-wave": "NOAA GFS Wave Model",
    "icon": "DWD ICON Global (deprecated, use icon-global)",
    "icon-global": "DWD ICON Global",
    "icon-eu": "DWD ICON Europe",
    "icon-d2": "DWD ICON-D2 (high-res Germany)",
    "icon-ewam": "DWD ICON-EWAM Wave Model",
    # Regional models
    "nam-conus": "NOAA NAM Continental US",
    "nam-hawaii": "NOAA NAM Hawaii",
    "nam-alaska": "NOAA NAM Alaska",
    "arome": "Meteo-France AROME (global)",
    "arome-france": "Meteo-France AROME France",
    "arome-antilles": "Meteo-France AROME Antilles",
    "arome-reunion": "Meteo-France AROME Reunion",
    "nems": "NEMS",
    # Special
    "cams": "Copernicus CAMS Air Quality",
    "camsEu": "Copernicus CAMS Europe Air Quality",
}

# Public API model names (different from internal names)
PUBLIC_API_MODELS = [
    "arome",      # -> arome-france internally
    "iconEu",     # -> icon-eu internally
    "gfs",
    "gfsWave",    # -> gfs-wave internally
    "namConus",   # -> nam-conus internally
    "namHawaii",  # -> nam-hawaii internally
    "namAlaska",  # -> nam-alaska internally
    "cams",       # Air quality
]

# Pressure levels available for forecasts
FORECAST_LEVELS = [
    "surface",
    "1000h", "950h", "925h", "900h", "850h", "800h",
    "700h", "600h", "500h", "400h", "300h", "200h", "150h",
]

# Weather parameters (from official API docs)
FORECAST_PARAMETERS = {
    "temp": "Air temperature at level",
    "dewpoint": "Dew point temperature at level",
    "precip": "Precipitation accumulation (past 3h, surface only)",
    "snowPrecip": "Snowfall accumulation (past 3h, surface only)",
    "convPrecip": "Convective precipitation (past 3h, surface only)",
    "wind": "Wind speed/direction (returns wind_u and wind_v vectors)",
    "windGust": "Wind gust speed (surface only)",
    "cape": "Convective Available Potential Energy (surface)",
    "ptype": "Precipitation type (0=none,1=rain,3=freezing rain,5=snow,7=mix,8=ice pellets)",
    "lclouds": "Low cloud coverage (>800hPa)",
    "mclouds": "Medium cloud coverage (450-800hPa)",
    "hclouds": "High cloud coverage (<450hPa)",
    "rh": "Relative humidity at level",
    "gh": "Geopotential height at level",
    "pressure": "Air pressure at surface",
    "waves": "Wave height, period, direction (wave models only)",
    "windWaves": "Wind wave height, period, direction (wave models only)",
    "swell1": "Primary swell height, period, direction (wave models only)",
    "swell2": "Secondary swell height, period, direction (wave models only)",
    "so2sm": "Sulfur dioxide (CAMS models only)",
    "dustsm": "Dust particles (CAMS models only)",
    "cosc": "Carbon monoxide concentration (CAMS models only)",
}


# ---------------------------------------------------------------------------
# Internal API Client (no key required for most endpoints)
# ---------------------------------------------------------------------------

class WindyInternalClient:
    """
    Client for Windy.com's internal backend API (node.windy.com).

    Most of these endpoints are publicly accessible without authentication.
    Some premium endpoints require a valid userToken (Bearer auth).

    All endpoint URLs were reverse-engineered from the Windy.com JS bundle
    (version 49.1.1, build hash: indeb7f).
    """

    def __init__(
        self,
        user_token: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        """
        Args:
            user_token: Optional Windy.com user token (from account login).
                        Required for premium/authenticated endpoints.
            session: Optional requests.Session to reuse connections.
        """
        self.user_token = user_token
        self.session = session or requests.Session()
        self._setup_session()

    def _setup_session(self):
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://www.windy.com",
            "Referer": "https://www.windy.com/",
            "Accept": WINDY_ACCEPT_HEADER,
        })
        if self.user_token:
            self.session.headers["Authorization"] = f"Bearer {self.user_token}"

    def _get(self, url: str, params: Optional[Dict] = None) -> Any:
        """Make a GET request and return parsed JSON."""
        params = params or {}
        params.setdefault("v", WINDY_VERSION)
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Services / Utility Endpoints
    # ------------------------------------------------------------------

    def get_location(self) -> Dict:
        """
        Get the user's inferred location based on IP address.

        Endpoint: GET /services/umisteni
        No authentication required.

        Returns:
            {
                "country": "US",
                "region": "VA",
                "eu": "0",
                "timezone": "America/New_York",
                "city": "Ashburn",
                "ll": [39.0469, -77.4903],
                "metro": 511,
                "area": 20,
                "ip": "1.2.3.4"
            }
        """
        return self._get(
            f"{NODE_BASE}/services/umisteni",
            params={"t": "index", "d": "desktop"},
        )

    def get_elevation(self, lat: float, lon: float) -> float:
        """
        Get terrain elevation at a geographic coordinate.

        Endpoint: GET /services/elevation/{lat}/{lon}
        No authentication required.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)

        Returns:
            Elevation in meters above sea level (float).
        """
        resp = self.session.get(
            f"{NODE_BASE}/services/elevation/{lat}/{lon}",
            params={"v": WINDY_VERSION},
        )
        resp.raise_for_status()
        return float(resp.text.strip())

    def get_timezone(self, lat: float, lon: float, ts: Optional[str] = None) -> Dict:
        """
        Get timezone information for a geographic coordinate.

        Endpoint: GET /services/v1/timezone/{lat}/{lon}
        No authentication required.

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            ts: ISO 8601 timestamp string (required). Determines DST offset.
                Example: "2026-03-25T00:00:00Z"

        Returns:
            {
                "TZname": "Europe/Prague",
                "TZoffset": 1,
                "TZoffsetMin": 60,
                "TZoffsetFormatted": "+01:00",
                "TZabbrev": "GMT+1",
                "TZtype": "t",
                "nowObserved": "2026-03-25T01:00:00+01:00"
            }
        """
        if ts is None:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._get(
            f"{NODE_BASE}/services/v1/timezone/{lat}/{lon}",
            params={"ts": ts},
        )

    # ------------------------------------------------------------------
    # Forecast Metadata
    # ------------------------------------------------------------------

    def get_forecast_minifest(
        self,
        model: str,
        premium: bool = False,
    ) -> Dict:
        """
        Get the forecast metadata manifest for a weather model.

        This contains the reference time (latest run), data step structure,
        and URLs for pointForecast, citytile, and imageServer endpoints.

        Endpoint: GET /metadata/v1.0/forecast/{model}/minifest.json
        No authentication required.

        Args:
            model: Forecast model identifier (e.g., "ecmwf-hres", "gfs").
                   See FORECAST_MODELS for all available models.
            premium: If True, request premium minifest (more forecast hours).

        Returns:
            {
                "dst": [[3, 3, 90], [3, 93, 144], [6, 150, 360]],  # step schedule
                "info": "2025080606",                                # model run info
                "ref": "2026-03-24T12:00:00Z",                      # reference time
                "update": "2026-03-24T19:55:45Z",                   # last update
                "v": "2.4",
                "urls": {
                    "citytile": "https://node.windy.com/citytile/v1.0/ecmwf-hres",
                    "pointForecast": "https://node.windy.com/forecast/point/ecmwf-hres/v2.9",
                    "imageServer": "https://ims.windy.com/im/v3.0/forecast/ecmwf-hres"
                }
            }

        Note:
            "dst" describes the timestep schedule:
            [[step_hours, from_hour, to_hour], ...]
            e.g., [[3, 3, 90]] means 3-hour steps from hour 3 to hour 90.
        """
        params: Dict[str, Any] = {"t": "index", "d": "desktop"}
        if premium:
            params["premium"] = "true"
        return self._get(
            f"{NODE_BASE}/metadata/v1.0/forecast/{model}/minifest.json",
            params=params,
        )

    def get_all_minifests(self) -> Dict[str, Dict]:
        """
        Fetch minifests for all major forecast models.

        Returns:
            Dict mapping model name to minifest data (errors are silently skipped).
        """
        results = {}
        for model in FORECAST_MODELS:
            try:
                results[model] = self.get_forecast_minifest(model)
            except Exception:
                pass
        return results

    # ------------------------------------------------------------------
    # Point Forecast (Internal - no key required for free models)
    # ------------------------------------------------------------------

    def get_point_forecast_now(
        self,
        model: str,
        lat: float,
        lon: float,
        ref_time: Optional[str] = None,
    ) -> Dict:
        """
        Get the current-time forecast for a specific point.

        Endpoint: GET /forecast/point/now/{model}/v1.0/{lat}/{lon}
        No authentication required for free models.

        Args:
            model: Forecast model identifier (e.g., "gfs", "ecmwf-hres").
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            ref_time: ISO 8601 reference time string. If None, latest run is used.

        Returns:
            Current weather conditions at the specified point.
        """
        lat_str = f"{lat:.4f}"
        lon_str = f"{lon:.4f}"
        params: Dict[str, Any] = {"v": WINDY_VERSION}
        if ref_time:
            params["refTime"] = ref_time
        resp = self.session.get(
            f"{NODE_BASE}/forecast/point/now/{model}/v1.0/{lat_str}/{lon_str}",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def get_point_forecast(
        self,
        model: str,
        lat: float,
        lon: float,
        ref_time: Optional[str] = None,
        step: int = 3,
        interpolate: bool = False,
        extended: bool = False,
    ) -> Dict:
        """
        Get the full point forecast for a specific location.

        Endpoint: GET /forecast/point/{model}/v2.9/{lat}/{lon}
        This endpoint requires user authentication (Bearer token) for most models,
        or use the public API (WindyPublicAPIClient) instead.

        Args:
            model: Forecast model identifier.
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            ref_time: ISO 8601 reference time. Uses latest run if None.
            step: Forecast time step in hours (3 or 1 for some models).
            interpolate: If True, interpolate values between grid points.
            extended: If True, request extended forecast range (premium).

        Returns:
            Full time-series forecast data with timestamps and parameter arrays.
        """
        lat_str = f"{lat:.4f}"
        lon_str = f"{lon:.4f}"

        # Determine version: airq models use v1.0, others use v2.9
        if model in ("cams", "camsEu"):
            version = "v1.0"
            path_type = "airq"
        else:
            version = "v2.9"
            path_type = "point"

        params: Dict[str, Any] = {"v": WINDY_VERSION}
        if ref_time:
            params["refTime"] = ref_time
        if step != 3:
            params["step"] = step
        if interpolate:
            params["interpolate"] = "true"
        if extended:
            params["extended"] = "true"

        resp = self.session.get(
            f"{NODE_BASE}/forecast/{path_type}/{model}/{version}/{lat_str}/{lon_str}",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # City Tile Forecast (Public - no auth needed)
    # ------------------------------------------------------------------

    def get_citytile_forecast(
        self,
        model: str,
        z: int,
        x: int,
        y: int,
        ref_time: str,
        step: int = 3,
        levels: Optional[str] = None,
    ) -> Dict:
        """
        Get city-level temperature forecasts for a map tile.

        Returns temperature data for cities within the specified tile,
        used for rendering city labels on the weather map.

        Endpoint: GET /citytile/v1.0/{model}/{z}/{x}/{y}
        No authentication required.

        Args:
            model: Forecast model identifier.
            z: Map zoom level
            x: Tile X coordinate (longitude)
            y: Tile Y coordinate (latitude)
            ref_time: ISO 8601 reference time string (required).
                      Get from get_forecast_minifest()["ref"].
            step: Time step in hours (3 default, 1 for high-res models).
            levels: Altitude levels string (defaults to surface).

        Returns:
            {
                "forecast": {
                    "{lat}/{lon}": [temp_ts0, temp_ts1, ...],
                    ...
                }
            }
            Temperature values are in Kelvin.

        Example:
            minifest = client.get_forecast_minifest("ecmwf-hres")
            ref_time = minifest["ref"]
            data = client.get_citytile_forecast("ecmwf-hres", 7, 66, 42, ref_time)
        """
        params: Dict[str, Any] = {
            "v": WINDY_VERSION,
            "refTime": ref_time,
            "labelsVersion": LABELS_VERSION,
            "step": step,
        }
        if levels:
            params["levels"] = levels
        return self._get(
            f"{NODE_BASE}/citytile/v1.0/{model}/{z}/{x}/{y}",
            params=params,
        )

    # ------------------------------------------------------------------
    # Radar
    # ------------------------------------------------------------------

    def get_radar_minifest(self) -> Dict:
        """
        Get radar data manifest with available tiles and timestamps.

        Endpoint: GET /radar2/composite/minifest2.json
        No authentication required.

        Returns:
            Large JSON with list of available radar tiles:
            {
                "tiles": [
                    [x, y, "lastUpdate", "startTime"],
                    ...
                ]
            }
        """
        return self._get(f"{NODE_BASE}/radar2/composite/minifest2.json")

    def get_radar_archive_minifest(self, start: str, end: str) -> Dict:
        """
        Get radar archive manifest for a time range.

        Endpoint: GET /radar2/archive/composite/minifest2.json
        Requires premium (paid) account.

        Args:
            start: Start time ISO 8601 string.
            end: End time ISO 8601 string.

        Returns:
            Archive radar manifest.
        """
        return self._get(
            f"{NODE_BASE}/radar2/archive/composite/minifest2.json",
            params={"start": start, "end": end},
        )

    def get_radar_coverage(self) -> List:
        """
        Get the list of radar stations with their coordinates and coverage radius.

        Endpoint: GET /radar2/composite/coverage.json
        No authentication required.

        Returns:
            Flat list of [lat, lon, radius_km, ...] for each radar station.
        """
        resp = self.session.get(
            f"{NODE_BASE}/radar2/composite/coverage.json",
            params={"v": WINDY_VERSION},
        )
        resp.raise_for_status()
        return resp.json()

    def get_radar_tile(
        self,
        z: int,
        x: int,
        y: int,
        timestamp: str,
    ) -> bytes:
        """
        Get a radar tile image (PNG) for a specific time and location.

        Endpoint: GET /radar2/composite/{timestamp}/{z}/{x}/{y}.png
        (URL varies - check minifest for exact tile paths)
        No authentication required.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            timestamp: ISO 8601 timestamp

        Returns:
            PNG image bytes.
        """
        resp = self.session.get(
            f"{NODE_BASE}/radar2/composite/{timestamp}/{z}/{x}/{y}.png",
            params={"v": WINDY_VERSION},
        )
        resp.raise_for_status()
        return resp.content

    # ------------------------------------------------------------------
    # Satellite
    # ------------------------------------------------------------------

    def get_satellite_info(self) -> Dict:
        """
        Get satellite imagery availability information.

        Endpoint: GET /satellite/info.json (on sat.windy.com)
        No authentication required.

        Returns:
            Available satellite products and timestamp info.
        """
        resp = self.session.get(
            f"{SAT_BASE}/satellite/info.json",
            params={"v": WINDY_VERSION},
        )
        resp.raise_for_status()
        return resp.json()

    def get_satellite_archive_info(self, start: str, end: str) -> Dict:
        """
        Get satellite archive info for a time range (premium).

        Endpoint: GET /satellite/archive/info.json
        Requires premium account.

        Args:
            start: Start time ISO 8601 string.
            end: End time ISO 8601 string.

        Returns:
            Archive satellite metadata.
        """
        resp = self.session.get(
            f"{SAT_BASE}/satellite/archive/info.json",
            params={"v": WINDY_VERSION, "start": start, "end": end},
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Map Tiles
    # ------------------------------------------------------------------

    def get_map_tile(
        self,
        z: int,
        x: int,
        y: int,
        tile_type: str = "grayland",
        version: str = "v10.0",
    ) -> bytes:
        """
        Get a base map tile (PNG) from the tiles server.

        Endpoint: GET /tiles/{version}/{tile_type}/{z}/{x}/{y}.png
        No authentication required.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            tile_type: Type of base map ("grayland" is the Windy dark-gray map).
            version: Tile version ("v10.0" current, "v9.0" older).

        Returns:
            PNG image bytes.
        """
        resp = self.session.get(
            f"{TILES_BASE}/tiles/{version}/{tile_type}/{z}/{x}/{y}.png"
        )
        resp.raise_for_status()
        return resp.content

    def get_ortho_tile(self, z: int, x: int, y: int) -> bytes:
        """
        Get an orthophoto (satellite imagery) map tile.

        Endpoint: GET /tiles/orto/v1.0/{z}/{z}-{x}-{y}.jpg
        No authentication required.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            JPEG image bytes.
        """
        resp = self.session.get(
            f"{TILES_BASE}/tiles/orto/v1.0/{z}/{z}-{x}-{y}.jpg"
        )
        resp.raise_for_status()
        return resp.content

    def get_satellite_map_tile(
        self,
        z: int,
        x: int,
        y: int,
        user_token: Optional[str] = None,
    ) -> bytes:
        """
        Get a HERE Maps satellite tile (requires user token).

        Endpoint: GET /maptile/2.1/maptile/newest/satellite.day/{z}/{x}/{y}/256/jpg
        Requires user token passed as token2 parameter.

        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            user_token: Windy user token. Falls back to instance token.

        Returns:
            JPEG image bytes.
        """
        token = user_token or self.user_token or "pending"
        resp = self.session.get(
            f"{NODE_BASE}/maptile/2.1/maptile/newest/satellite.day/{z}/{x}/{y}/256/jpg",
            params={"token2": token},
        )
        resp.raise_for_status()
        return resp.content

    # ------------------------------------------------------------------
    # Webcams (Internal - deprecated, use public API)
    # ------------------------------------------------------------------

    def get_webcam_list(
        self,
        limit: int = 50,
        offset: int = 0,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_km: Optional[float] = None,
    ) -> Dict:
        """
        Get list of webcams (internal endpoint).

        Note: This internal endpoint is largely replaced by the official
        webcams API at api.windy.com. Use WindyPublicAPIClient.get_webcams() instead.

        Endpoint: GET /webcams/v1.0/list (on node.windy.com)
        Requires user token for full access.

        Args:
            limit: Max results to return (default 50).
            offset: Pagination offset.
            lat: Center latitude for radius search.
            lon: Center longitude for radius search.
            radius_km: Search radius in km.

        Returns:
            Dict with webcam list data.
        """
        params: Dict[str, Any] = {
            "v": WINDY_VERSION,
            "limit": limit,
            "offset": offset,
        }
        if lat is not None:
            params["lat"] = lat
        if lon is not None:
            params["lon"] = lon
        if radius_km is not None:
            params["radius"] = radius_km

        resp = self.session.get(
            f"{NODE_BASE}/webcams/v1.0/list",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def get_webcam_detail(self, webcam_id: str) -> Dict:
        """
        Get detailed information about a specific webcam.

        Endpoint: GET /webcams/v1.0/detail/{webcam_id}
        No authentication required.

        Args:
            webcam_id: Webcam ID string.

        Returns:
            Dict with webcam details.
        """
        return self._get(f"{NODE_BASE}/webcams/v1.0/detail/{webcam_id}")

    def get_webcam_archive(self, webcam_id: str, start: str, end: str) -> Dict:
        """
        Get webcam archive images for a time range.

        Endpoint: GET /webcams/v2.0/archive/{webcam_id}
        Requires premium access.

        Args:
            webcam_id: Webcam ID string.
            start: Start time ISO 8601.
            end: End time ISO 8601.

        Returns:
            Archive image list.
        """
        return self._get(
            f"{NODE_BASE}/webcams/v2.0/archive/{webcam_id}",
            params={"start": start, "end": end},
        )

    # ------------------------------------------------------------------
    # Convenience Methods
    # ------------------------------------------------------------------

    def get_weather_now(self, lat: float, lon: float, model: str = "gfs") -> Dict:
        """
        Convenience method to get current weather for a location.

        Combines timezone, elevation, and now-forecast data.

        Args:
            lat: Latitude
            lon: Longitude
            model: Forecast model (default: "gfs")

        Returns:
            Dict combining timezone, elevation, and current forecast.
        """
        result: Dict[str, Any] = {"lat": lat, "lon": lon, "model": model}

        try:
            result["elevation"] = self.get_elevation(lat, lon)
        except Exception as e:
            result["elevation_error"] = str(e)

        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            result["timezone"] = self.get_timezone(lat, lon, ts)
        except Exception as e:
            result["timezone_error"] = str(e)

        try:
            minifest = self.get_forecast_minifest(model)
            result["ref_time"] = minifest.get("ref")
            result["model_update"] = minifest.get("update")
        except Exception as e:
            result["minifest_error"] = str(e)

        return result


# ---------------------------------------------------------------------------
# Public API Client (requires API key from https://api.windy.com/keys)
# ---------------------------------------------------------------------------

class WindyPublicAPIClient:
    """
    Client for the official Windy.com public developer API.

    All endpoints require an API key obtained from https://api.windy.com/keys.
    Different API products have separate keys:
    - Point Forecast API key (for weather data)
    - Webcams API key (for webcam data)
    - Map Forecast API key (for embedding maps)

    Official documentation: https://api.windy.com
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        webcams_api_key: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        """
        Args:
            api_key: Point Forecast API key.
            webcams_api_key: Webcams API key (can differ from point forecast key).
            session: Optional requests.Session for connection reuse.
        """
        self.api_key = api_key
        self.webcams_api_key = webcams_api_key or api_key
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "WindyPythonClient/1.0",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Point Forecast API (POST /api/point-forecast/v2)
    # ------------------------------------------------------------------

    def get_point_forecast(
        self,
        lat: float,
        lon: float,
        model: str,
        levels: List[str],
        parameters: List[str],
        api_key: Optional[str] = None,
    ) -> Dict:
        """
        Get weather forecast for a specific geographic point.

        Official endpoint: POST https://api.windy.com/api/point-forecast/v2
        Requires Point Forecast API key.

        Documentation: https://api.windy.com/point-forecast/docs

        Args:
            lat: Latitude (-90 to 90)
            lon: Longitude (-180 to 180)
            model: One of PUBLIC_API_MODELS:
                   "arome", "iconEu", "gfs", "gfsWave",
                   "namConus", "namHawaii", "namAlaska", "cams"
            levels: List of altitude levels from FORECAST_LEVELS.
                    e.g., ["surface"], ["surface", "850h", "500h"]
            parameters: List of weather parameters from FORECAST_PARAMETERS.
                        e.g., ["temp", "wind", "precip", "pressure"]
            api_key: Override API key for this request.

        Returns:
            {
                "ts": [1711274400000, 1711285200000, ...],  # Unix ms timestamps
                "units": {
                    "temp-surface": "K",
                    "wind_u-surface": "m*s-1",
                    "wind_v-surface": "m*s-1",
                    ...
                },
                "temp-surface": [285.2, 284.8, ...],
                "wind_u-surface": [3.2, 2.8, ...],
                "wind_v-surface": [-1.5, -2.1, ...],
                ...
            }

        Notes:
            - Timestamp values are milliseconds since Unix epoch
            - Wind is returned as U/V vector components (use math.atan2 for direction)
            - Null values indicate no data for that timestamp
            - For wave parameters, use model "gfsWave" or "iconEu"

        Example:
            client = WindyPublicAPIClient(api_key="your_key")
            data = client.get_point_forecast(
                lat=50.4, lon=14.3,
                model="gfs",
                levels=["surface"],
                parameters=["temp", "wind", "precip", "pressure"]
            )
            # Convert timestamps to datetime
            from datetime import datetime
            times = [datetime.fromtimestamp(ts/1000) for ts in data["ts"]]
            temps_celsius = [t - 273.15 for t in data["temp-surface"]]
        """
        key = api_key or self.api_key
        if not key:
            raise ValueError(
                "API key is required. Get one at https://api.windy.com/keys"
            )

        payload = {
            "lat": lat,
            "lon": lon,
            "model": model,
            "levels": levels,
            "parameters": parameters,
            "key": key,
        }

        resp = self.session.post(
            f"{API_BASE}/api/point-forecast/v2",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def get_point_forecast_multi_level(
        self,
        lat: float,
        lon: float,
        model: str = "gfs",
        api_key: Optional[str] = None,
    ) -> Dict:
        """
        Get a comprehensive forecast at multiple pressure levels.

        Fetches temperature, wind, humidity, and geopotential height
        at surface and multiple pressure levels.

        Args:
            lat: Latitude
            lon: Longitude
            model: Forecast model
            api_key: API key override

        Returns:
            Multi-level forecast data dict.
        """
        return self.get_point_forecast(
            lat=lat,
            lon=lon,
            model=model,
            levels=["surface", "850h", "700h", "500h", "300h"],
            parameters=["temp", "wind", "rh", "gh", "pressure"],
            api_key=api_key,
        )

    # ------------------------------------------------------------------
    # Webcams API v3 (GET /webcams/api/v3/...)
    # ------------------------------------------------------------------

    def get_webcams_by_bbox(
        self,
        north_lat: float,
        south_lat: float,
        east_lon: float,
        west_lon: float,
        zoom: int = 8,
        include: Optional[List[str]] = None,
        lang: str = "en",
        api_key: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get webcams within a bounding box, optimized for map display.

        Official endpoint: GET https://api.windy.com/webcams/api/v3/map/clusters
        Requires Webcams API key (x-windy-api-key header).

        Documentation: https://api.windy.com/webcams/docs

        Args:
            north_lat: North edge latitude (-90 to 90)
            south_lat: South edge latitude (-90 to 90)
            east_lon: East edge longitude (-180 to 180)
            west_lon: West edge longitude (-180 to 180)
            zoom: Map zoom level (4-18). Constrains max bounding box size:
                  zoom 4: max lat range 22.5°, max lon range 45°
                  zoom 8: max lat range ~1.4°, max lon range ~2.8°
            include: Content fields to include. Options:
                     "categories", "images", "location", "player", "urls"
            lang: Language code for localized names (default: "en")
            api_key: Override API key.

        Returns:
            List of webcam objects. Structure depends on 'include' param.

        Example:
            webcams = client.get_webcams_by_bbox(
                north_lat=51, south_lat=50, east_lon=15, west_lon=14,
                zoom=8, include=["location", "images"]
            )
        """
        key = api_key or self.webcams_api_key
        if not key:
            raise ValueError(
                "Webcams API key is required. Get one at https://api.windy.com/keys"
            )

        params: Dict[str, Any] = {
            "northLat": north_lat,
            "southLat": south_lat,
            "eastLon": east_lon,
            "westLon": west_lon,
            "zoom": zoom,
            "lang": lang,
        }
        if include:
            params["include"] = ",".join(include)

        resp = self.session.get(
            f"{API_BASE}/webcams/api/v3/map/clusters",
            params=params,
            headers={"x-windy-api-key": key},
        )
        resp.raise_for_status()
        return resp.json()

    def get_webcam_by_id(
        self,
        webcam_id: Union[str, int],
        include: Optional[List[str]] = None,
        lang: str = "en",
        api_key: Optional[str] = None,
    ) -> Dict:
        """
        Get detailed information for a specific webcam.

        Official endpoint: GET https://api.windy.com/webcams/api/v3/webcams/{webcamId}
        Requires Webcams API key.

        Args:
            webcam_id: Webcam ID (numeric or string).
            include: Content fields to include:
                     "categories", "images", "location", "player", "urls"
            lang: Language code.
            api_key: Override API key.

        Returns:
            Detailed webcam object.
        """
        key = api_key or self.webcams_api_key
        if not key:
            raise ValueError("Webcams API key required.")

        params: Dict[str, Any] = {"lang": lang}
        if include:
            params["include"] = ",".join(include)

        resp = self.session.get(
            f"{API_BASE}/webcams/api/v3/webcams/{webcam_id}",
            params=params,
            headers={"x-windy-api-key": key},
        )
        resp.raise_for_status()
        return resp.json()

    def get_webcams_nearby(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50,
        limit: int = 10,
        include: Optional[List[str]] = None,
        api_key: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get webcams near a specific geographic point.

        Uses the bounding box endpoint with a computed bounding box
        approximated from the center point and radius.

        Args:
            lat: Center latitude
            lon: Center longitude
            radius_km: Search radius in km (approximate)
            limit: Target number of results (uses zoom level adjustment)
            include: Content fields to include
            api_key: Override API key

        Returns:
            List of nearby webcam objects.
        """
        # Approximate degree offset (1 degree ≈ 111 km)
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * abs(max(0.001, abs(lat) / 90)))

        # Choose zoom level based on radius
        if radius_km <= 10:
            zoom = 12
        elif radius_km <= 25:
            zoom = 10
        elif radius_km <= 50:
            zoom = 8
        else:
            zoom = 6

        return self.get_webcams_by_bbox(
            north_lat=min(90, lat + lat_offset),
            south_lat=max(-90, lat - lat_offset),
            east_lon=min(180, lon + lon_offset),
            west_lon=max(-180, lon - lon_offset),
            zoom=zoom,
            include=include or ["location", "images"],
            api_key=api_key,
        )

    # ------------------------------------------------------------------
    # Map Forecast Embed API
    # ------------------------------------------------------------------

    def get_embed_url(
        self,
        lat: float,
        lon: float,
        zoom: int = 5,
        overlay: str = "wind",
        product: str = "ecmwf",
        level: str = "surface",
        api_key: Optional[str] = None,
    ) -> str:
        """
        Generate an embeddable Windy map URL.

        This creates a URL for embedding Windy map in iframes.
        Requires Map Forecast API key from https://api.windy.com/keys.

        Documentation: https://api.windy.com/map-forecast/docs

        Args:
            lat: Map center latitude
            lon: Map center longitude
            zoom: Map zoom level (3-18)
            overlay: Weather layer overlay:
                     "wind", "rain", "clouds", "temp", "pressure",
                     "waves", "radar", "satellite", "snow", "cape", etc.
            product: Forecast model:
                     "ecmwf", "gfs", "icon", "nam", etc.
            level: Altitude level: "surface", "850h", "500h", etc.
            api_key: Map Forecast API key.

        Returns:
            Embeddable map URL string.

        Example:
            url = client.get_embed_url(
                lat=50.4, lon=14.3, zoom=7,
                overlay="wind", product="ecmwf"
            )
            # Use in HTML: <iframe src="{url}" width="1200" height="800"></iframe>
        """
        key = api_key or self.api_key
        params = {
            "width": "1200",
            "height": "800",
            "lat": lat,
            "lon": lon,
            "zoom": zoom,
            "overlay": overlay,
            "product": product,
            "level": level,
        }
        if key:
            params["key"] = key
        return f"https://embed.windy.com/embed.html?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def kelvin_to_celsius(k: float) -> float:
    """Convert Kelvin to Celsius."""
    return k - 273.15


def wind_uv_to_speed_direction(u: float, v: float) -> tuple:
    """
    Convert wind U/V vector components to speed and meteorological direction.

    Args:
        u: Eastward wind component (m/s). Positive = wind blowing east.
        v: Northward wind component (m/s). Positive = wind blowing north.

    Returns:
        Tuple of (speed_ms, direction_degrees)
        Direction is meteorological: 0°=N, 90°=E, 180°=S, 270°=W
        (direction the wind is coming FROM)
    """
    import math
    speed = math.sqrt(u ** 2 + v ** 2)
    # Meteorological direction (where wind comes FROM)
    direction = (math.degrees(math.atan2(u, v)) + 180) % 360
    return speed, direction


def parse_forecast_timestamps(ts_ms: List[int]) -> List[datetime]:
    """
    Convert Windy millisecond timestamps to Python datetime objects.

    Args:
        ts_ms: List of Unix timestamps in milliseconds.

    Returns:
        List of timezone-aware datetime objects (UTC).
    """
    return [
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        for ts in ts_ms
    ]


def format_ref_time(dt: Optional[datetime] = None) -> str:
    """
    Format a datetime as Windy API reference time string.

    Args:
        dt: Datetime to format. If None, uses current UTC time rounded to 6h.

    Returns:
        ISO 8601 string formatted for Windy API.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    # Round to nearest 6 hours (typical model run interval)
    hour = (dt.hour // 6) * 6
    dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple:
    """
    Convert geographic coordinates to map tile coordinates.

    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)
        zoom: Zoom level

    Returns:
        Tuple of (x, y) tile coordinates.
    """
    import math
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y


# ---------------------------------------------------------------------------
# Example Usage
# ---------------------------------------------------------------------------

def example_internal_api():
    """Example usage of the internal API (no key required)."""
    print("=== Windy Internal API Examples ===\n")

    client = WindyInternalClient()

    # 1. Get location based on IP
    print("1. Getting location from IP...")
    location = client.get_location()
    print(f"   City: {location.get('city')}, {location.get('country')}")
    print(f"   Coordinates: {location.get('ll')}")
    print(f"   Timezone: {location.get('timezone')}\n")

    # 2. Get elevation for Prague
    print("2. Getting elevation for Prague (50.08, 14.42)...")
    elevation = client.get_elevation(50.08, 14.42)
    print(f"   Elevation: {elevation}m\n")

    # 3. Get timezone info
    print("3. Getting timezone for Prague...")
    tz_info = client.get_timezone(50.08, 14.42, "2026-03-25T12:00:00Z")
    print(f"   Timezone: {tz_info.get('TZname')} ({tz_info.get('TZoffsetFormatted')})\n")

    # 4. Get forecast minifest for GFS
    print("4. Getting GFS forecast minifest...")
    minifest = client.get_forecast_minifest("gfs")
    print(f"   Latest run: {minifest.get('ref')}")
    print(f"   Updated: {minifest.get('update')}")
    print(f"   Point forecast URL: {minifest.get('urls', {}).get('pointForecast')}\n")

    # 5. Get citytile forecast
    print("5. Getting citytile forecast for Prague area (zoom 7, tile 71/44)...")
    try:
        citytile = client.get_citytile_forecast(
            model="gfs",
            z=7, x=71, y=44,
            ref_time=minifest["ref"],
        )
        city_data = citytile.get("forecast", {})
        print(f"   Found {len(city_data)} cities in tile")
        if city_data:
            first_city_coords = list(city_data.keys())[0]
            temps = city_data[first_city_coords][:4]
            print(f"   Sample ({first_city_coords}): {[round(kelvin_to_celsius(t), 1) for t in temps]}°C\n")
    except Exception as e:
        print(f"   Error: {e}\n")

    # 6. Get radar coverage count
    print("6. Getting radar coverage...")
    try:
        coverage = client.get_radar_coverage()
        # Coverage is flat list of [lat, lon, radius, ...]
        num_radars = len(coverage) // 3 if isinstance(coverage, list) else 0
        print(f"   ~{num_radars} radar stations worldwide\n")
    except Exception as e:
        print(f"   Error: {e}\n")


def example_public_api(api_key: str):
    """Example usage of the public API (requires key)."""
    print("=== Windy Public API Examples ===\n")

    client = WindyPublicAPIClient(api_key=api_key)

    # 1. Get GFS forecast for New York City
    print("1. Getting GFS surface forecast for NYC (40.71, -74.01)...")
    data = client.get_point_forecast(
        lat=40.71,
        lon=-74.01,
        model="gfs",
        levels=["surface"],
        parameters=["temp", "wind", "precip", "pressure", "windGust"],
    )

    if "ts" in data:
        times = parse_forecast_timestamps(data["ts"])
        print(f"   Got {len(times)} forecast steps")
        print(f"   First time: {times[0].strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"   Last time: {times[-1].strftime('%Y-%m-%d %H:%M UTC')}")

        if "temp-surface" in data:
            temps = [
                round(kelvin_to_celsius(t), 1)
                for t in data["temp-surface"]
                if t is not None
            ]
            print(f"   Temperature range: {min(temps)}°C to {max(temps)}°C")

        if "wind_u-surface" in data and "wind_v-surface" in data:
            u_vals = data["wind_u-surface"]
            v_vals = data["wind_v-surface"]
            if u_vals and v_vals and u_vals[0] is not None:
                speed, direction = wind_uv_to_speed_direction(u_vals[0], v_vals[0])
                print(f"   Current wind: {speed:.1f} m/s from {direction:.0f}°")
        print()

    # 2. Get multi-level forecast for atmospheric sounding
    print("2. Getting multi-level GFS forecast for Paris (48.86, 2.35)...")
    ml_data = client.get_point_forecast_multi_level(lat=48.86, lon=2.35)
    if "ts" in ml_data:
        print(f"   Got {len(ml_data['ts'])} timesteps")
        available_params = [k for k in ml_data.keys() if k not in ("ts", "units", "warning")]
        print(f"   Available parameters: {', '.join(available_params[:5])}...")
    print()

    # 3. Get webcams near London
    print("3. Getting webcams near London...")
    try:
        webcams = client.get_webcams_nearby(
            lat=51.5, lon=-0.12,
            radius_km=30,
            include=["location", "images"],
        )
        print(f"   Found {len(webcams)} webcams")
        if webcams:
            cam = webcams[0]
            loc = cam.get("location", {})
            print(f"   First webcam: {cam.get('title', 'Unknown')} at "
                  f"{loc.get('city', 'Unknown')}, {loc.get('country', 'Unknown')}")
    except Exception as e:
        print(f"   Error (webcams may need separate key): {e}")
    print()

    # 4. Generate embed URL
    print("4. Generating embed URL for wind map over Europe...")
    embed_url = client.get_embed_url(
        lat=50.0, lon=15.0, zoom=5,
        overlay="wind", product="ecmwf",
    )
    print(f"   URL: {embed_url}\n")


if __name__ == "__main__":
    import sys

    # Run internal API examples (no key required)
    example_internal_api()

    # Run public API examples (requires key)
    if len(sys.argv) > 1:
        example_public_api(api_key=sys.argv[1])
    else:
        print("\n--- Public API Examples ---")
        print("Run with API key argument to test public API:")
        print("  python windy_client.py YOUR_API_KEY")
        print("Get a key at: https://api.windy.com/keys")
