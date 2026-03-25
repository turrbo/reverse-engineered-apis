"""
Ventusky API Client
===================
Reverse-engineered Python client for the internal/hidden APIs of Ventusky
(https://www.ventusky.com).

Discovered by analysing:
  - The main page HTML (MapOptions configuration object)
  - The main JavaScript bundle: https://static.ventusky.com/media/script-en.js
  - Live network traffic inspection
  - Verified endpoint probing with HTTP HEAD/GET requests

All base URLs discovered from DNS-prefetch hints in the page:
  https://data.ventusky.com      — weather tile / JSON data
  https://static.ventusky.com    — static map tiles and assets
  https://map.ventusky.com       — high-zoom OSM-style map tiles (zoom 13+)
  https://api.ventusky.com       — REST API (hurricanes)
  https://webcams.ventusky.com   — live webcam data
  https://www.ventusky.com       — search + location helpers
  https://users.ventusky.com     — user account info (requires auth cookie)

Usage example
-------------
    from ventusky_client import VentuskyClient
    from datetime import datetime, timezone

    client = VentuskyClient()

    # Search for a city
    results = client.search_city("London")
    print(results)

    # Get nearest locations to a coordinate
    locations = client.get_nearest_locations(lat=51.5074, lon=-0.1278)
    print(locations)

    # Download a weather tile image
    t = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)
    img_bytes = client.get_weather_tile(
        model="gfs",
        layer="teplota_2_m",       # 2 m temperature
        dt=t,
    )
    with open("temperature.jpg", "wb") as f:
        f.write(img_bytes)

    # Get pressure systems JSON (high / low centres)
    pressure = client.get_pressure_systems(model="gfs", dt=t)
    print(pressure)

    # Get weather fronts JSON
    fronts = client.get_weather_fronts(model="gfs", dt=t)
    print(fronts)

    # Get nearest webcams
    cams = client.get_nearest_webcams(lat=40.7128, lon=-74.006, count=5)
    print(cams)

    # Download a webcam thumbnail
    cam_id = cams[0]["id"]
    thumb = client.get_webcam_thumbnail(cam_id)
    with open("webcam.jpg", "wb") as f:
        f.write(thumb)
"""

import datetime
import urllib.request
import urllib.parse
import json
from typing import Any, Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Constants discovered from JavaScript source
# ---------------------------------------------------------------------------

DATA_BASE = "https://data.ventusky.com"
STATIC_BASE = "https://static.ventusky.com"
MAP_BASE = "https://map.ventusky.com"
API_BASE = "https://api.ventusky.com"
WEBCAM_BASE = "https://webcams.ventusky.com"
WWW_BASE = "https://www.ventusky.com"
USERS_BASE = "https://users.ventusky.com"

# Weather forecast models available on Ventusky
# Source: variable `ha` in the minified JS bundle
MODELS = [
    "icon",           # DWD ICON global
    "gfs",            # NOAA GFS global
    "ecmwf",          # ECMWF (historical archive)
    "ecmwf-mres",     # ECMWF medium-resolution (operational)
    "ecmwf-hres",     # ECMWF high-resolution (operational)
    "kma_um",         # Korea KMA Unified Model
    "gem",            # CMC GEM (Canada)
    "icon_eu",        # DWD ICON-EU (European)
    "icon_de",        # DWD ICON-D2 (Germany, high-res)
    "icon_ch",        # MeteoSwiss ICON-CH
    "harmonie_eu",    # Harmonie (multiple European services)
    "harmonie_car",   # Harmonie Caribbean
    "worad_hres",     # World Radar high-res composite
    "worad",          # World Radar composite
    "eurad",          # EU Radar
    "eurad_hres",     # EU Radar high-res
    "usrad",          # US Radar
    "earad",          # East Asia Radar
    "ukmo",           # UK Met Office global
    "ukmo_uk",        # UK Met Office UK high-res
    "hrrr",           # NOAA HRRR (US high-res)
    "nam_us",         # NOAA NAM US
    "nam_hawai",      # NOAA NAM Hawaii
    "nbm",            # NOAA National Blend of Models
    "aladin",         # Aladin (France/Czech)
    "arome",          # Arome (France)
    "meps",           # MetCoOp MEPS (Nordic)
    "goes",           # GOES satellite (global)
    "goes16",         # GOES-16 (Americas)
    "meteosat_hd",    # Meteosat high-def
    "meteosat",       # Meteosat
    "himawari",       # Himawari (Asia-Pacific)
    "silam",          # SILAM air quality (global)
    "silam_eu",       # SILAM air quality (Europe)
    "cams",           # Copernicus CAMS air quality
    "smoc",           # SMOC ocean currents
    "rtofs",          # RTOFS ocean (US)
    "stofs",          # STOFS storm surge
    "stofs_us",       # STOFS US
    "mfwam",          # MF-WAM ocean waves
    "wavewatch_no",   # WaveWatch3 (Norway)
    "wavewatch-no",   # alias
]

# Layer file identifiers mapped from layer display names
# Source: `qa` array in the minified JS bundle (layer config)
# These are the `file` values used in tile URLs.
LAYER_FILES = {
    # Temperature layers (id -> file name used in URL)
    "temperature-water":        "teplota_voda",
    "temperature-5cm":          "teplota_surface",
    "temperature-2m":           "teplota_2_m",
    "temperature-anomaly-2m":   "teplota_odchylka_2_m",
    "temperature-950hpa":       "teplota_95000_pa",
    "temperature-925hpa":       "teplota_92500_pa",
    "temperature-900hpa":       "teplota_90000_pa",
    "temperature-850hpa":       "teplota_85000_pa",
    "temperature-800hpa":       "teplota_80000_pa",
    "temperature-750hpa":       "teplota_75000_pa",
    "temperature-700hpa":       "teplota_70000_pa",
    "temperature-650hpa":       "teplota_65000_pa",
    "temperature-600hpa":       "teplota_60000_pa",
    "temperature-500hpa":       "teplota_50000_pa",
    "temperature-300hpa":       "teplota_30000_pa",
    "temperature-200hpa":       "teplota_20000_pa",
    "temperature-10hpa":        "teplota_1000_pa",
    "freezing":                 "nulova_izoterma",
    "feels-like":               "teplota_pocit",

    # Precipitation
    "rain-1h":                  "srazky_1h",
    "rain-3h":                  "srazky_3h",
    "rain-ac":                  "srazky_ac",       # accumulation
    "precipitation-anomaly":    "srazky_odchylka",

    # Radar / Satellite
    "radar":                    "srazky_dbz",
    "radar-type":               "srazky_type_dbz",
    "satellite":                "rgba",

    # Clouds
    "clouds-total":             "oblacnost",
    "clouds-fog":               "srazky_type_1h",
    "clouds-low":               "oblacnost_low",
    "clouds-middle":            "oblacnost_middle",
    "clouds-high":              "oblacnost_high",
    "cloud-base":               "cloud_base",
    "visibility":               "visibility",

    # Wind (u and v components; tile URL uses the u-component filename)
    "wind-10m":                 "vitr_u_10_m",    # v = vitr_v_10_m
    "wind-100m":                "vitr_u_100_m",
    "wind-250m":                "vitr_u_250_m",
    "wind-950hpa":              "vitr_u_95000_pa",
    "wind-925hpa":              "vitr_u_92500_pa",
    "wind-900hpa":              "vitr_u_90000_pa",
    "wind-850hpa":              "vitr_u_85000_pa",
    "wind-800hpa":              "vitr_u_80000_pa",
    "wind-750hpa":              "vitr_u_75000_pa",
    "wind-700hpa":              "vitr_u_70000_pa",
    "wind-650hpa":              "vitr_u_65000_pa",
    "wind-600hpa":              "vitr_u_60000_pa",
    "wind-500hpa":              "vitr_u_50000_pa",
    "wind-300hpa":              "vitr_u_30000_pa",
    "wind-200hpa":              "vitr_u_20000_pa",
    "wind-10hpa":               "vitr_u_1000_pa",

    # Wind gusts
    "gust":                     "vitr_naraz",
    "gust-ac":                  "vitr_naraz_ac",

    # Pressure / geopotential
    "pressure":                 "tlak",
    "geopotential-850hpa":      "gph_850",
    "geopotential-500hpa":      "gph_500",
    "geopotential-300hpa":      "gph_300",

    # Storm indices
    "cape":                     "cape",
    "cape-shear":               "cape_shear",
    "shear":                    "shear",
    "hail-probability":         "hail_probability",
    "cin":                      "cin",
    "li":                       "li",
    "helicity":                 "helicity",

    # Humidity / dew point
    "humidity-2m":              "vlhkost",
    "humidity-900hpa":          "vlhkost_90000_pa",
    "humidity-850hpa":          "vlhkost_85000_pa",
    "humidity-700hpa":          "vlhkost_70000_pa",
    "dew":                      "dew_point",

    # Sea / ocean
    "wave":                     "swh",        # significant wave height total
    "wind-wave":                "shww",       # significant wind-wave height
    "wind-wave-period":         "mpww",       # mean wind-wave period
    "swell":                    "shts",       # swell height
    "swell-period":             "mpts",       # swell period
    "currents":                 "proud_u",    # v = proud_v
    "tide-currents":            "tide_proud_u",
    "tide":                     "tide",
    "tide-surge":               "tide_surge",

    # Snow
    "snow":                     "snih",
    "snow-new-ac":              "novy_snih_ac",

    # Air quality
    "pm25":                     "pm25",
    "pm10":                     "pm10",
    "no2":                      "no2",
    "so2":                      "so2",
    "o3":                       "o3",
    "dust":                     "dust",
    "co":                       "co",
    "aqi":                      "aqi",
    "uv":                       "uv",
}

# Valid isoline types for get_isolines()
ISOLINE_TYPES = [
    "pressure",
    "geopotential-300hpa",
    "geopotential-500hpa",
    "geopotential-850hpa",
    "dew",
    "temperature-2m",
    "temperature-850hpa",
    "freezing",
]

# Static tile layer names for base map
STATIC_TILE_LAYERS = {
    "land":    f"{STATIC_BASE}/tiles/v1.1/land",
    "border":  f"{STATIC_BASE}/tiles/v1.0/border",
    "cities":  f"{STATIC_BASE}/tiles/v2.2/cities",
    "cams":    f"{STATIC_BASE}/tiles/v1.0/cams",
    "osm":     f"{STATIC_BASE}/tiles/v1.0/osm_custom",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(dt: datetime.datetime) -> Dict[str, str]:
    """Return a dict of substitution values for URL templates."""
    return {
        "yyyy":       f"{dt.year:04d}",
        "MM":         f"{dt.month:02d}",
        "dd":         f"{dt.day:02d}",
        "HH":         f"{dt.hour:02d}",
        "yyyyMMdd":   f"{dt.year:04d}{dt.month:02d}{dt.day:02d}",
        "yyyyMMdd_HH": f"{dt.year:04d}{dt.month:02d}{dt.day:02d}_{dt.hour:02d}",
        "mm":         f"{dt.minute:02d}",
    }


def _get(url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
    """Perform a GET request and return raw bytes."""
    default_headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.ventusky.com/",
    }
    if headers:
        default_headers.update(headers)

    req = urllib.request.Request(url, headers=default_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _get_json(url: str) -> Any:
    """Perform a GET request and parse the JSON response."""
    raw = _get(url)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class VentuskyClient:
    """
    Python client for Ventusky's internal APIs.

    All methods accept naive or timezone-aware datetime objects.
    UTC is assumed for naive datetimes.

    Endpoints discovered:
    ─────────────────────
    1.  City / location search
        GET https://www.ventusky.com/ventusky_mesta.php
            ?q=<query>&lang=<lang>

    2.  Reverse geocode / nearest named locations
        GET https://www.ventusky.com/ventusky_location.json.php
            ?lat=<lat>&lon=<lon>&zoom=<zoom>

    3.  Weather data tiles (global, whole-world JPEG)
        GET https://data.ventusky.com/{YYYY/MM/DD}/{model}/whole_world/
            hour_{HH}/{model}_{layer}_{YYYYMMDD_HH}.jpg

    4.  Weather data tiles (regional, tiled JPEG)
        GET https://data.ventusky.com/{YYYY/MM/DD}/{model}/tilled_world/
            hour_{HH}/{model}_{layer}_{tileX}_{tileY}_{YYYYMMDD_HH}.jpg
        (used for high-resolution regional models like HRRR, ICON-DE)

    5.  Pressure system centres JSON (H/L labels)
        GET https://data.ventusky.com/{YYYY/MM/DD}/{model}/whole_world/
            hour_{HH}/{model}_pressure_low_high_{YYYYMMDD_HH}.json
        Response: {"l": [[lat, lon, hPa], ...], "h": [[lat, lon, hPa], ...]}

    6.  Weather fronts JSON
        GET https://data.ventusky.com/{YYYY}/{MM}/{DD}/{model}/whole_world/
            hour_{HH}/{model}_fronts_{YYYYMMDD_HH}.json
        Response: {"fronts": [{"type": "warm|cold|occluded|stationary",
                                "direction": "right|left",
                                "points": [[x, y], ...]}, ...]}

    7.  Isolines (isobars, isotherms) – returns PNG-encoded isoline data
        GET https://data.ventusky.com/{YYYY}/{MM}/{DD}/{model}/whole_world/
            hour_{HH}/{model}_iso_{type}_{YYYYMMDD_HH}.json
        Note: content-type is image/png despite .json extension

    8.  Hurricane/tropical storm tracks
        GET https://api.ventusky.com/v2/api.ventusky_hurricane.json.php
            ?end_time_unix=<ms>&start_time_unix=<ms>

    9.  Webcam list (all currently-active webcam IDs)
        GET https://webcams.ventusky.com/update.json

    10. Nearest webcams to a coordinate
        GET https://webcams.ventusky.com/api/api.get_nearest_camera.php
            ?lat=<lat>&lon=<lon>&count=<n>

    11. Webcam latest thumbnail
        GET https://webcams.ventusky.com/data/{idLast2}/{id}/latest_thumb.jpg

    12. Webcam historical frame
        GET https://webcams.ventusky.com/data/{idLast2}/{id}/{steps}/
            {YYYYMMDD_HHmm}.jpg

    13. Static base-map tiles  (land, borders, cities, OSM)
        GET https://static.ventusky.com/tiles/{version}/{layer}/{z}/{x}/{y}.png

    14. High-zoom OSM-style map tiles (zoom ≥ 13)
        GET https://map.ventusky.com/tiles/{z}/{x}/{y}.png?256

    15. WAQI air-quality station data (third-party, token embedded in JS)
        GET https://api.waqi.info/feed/geo:{lat};{lon}/
            ?token=904a1bc6edf77c428347f2fe54cf663bcffaec21

    16. Logged-in user info (requires ventusky_permanent cookie)
        GET https://users.ventusky.com/api/api.logged_user_info.php

    17. OSM Nominatim geocoding fallback (third-party)
        GET https://nominatim.openstreetmap.org/search
            ?q=<q>&format=json&polygon=0&addressdetails=1&limit=5
            &accept-language=<lang>
    """

    # ------------------------------------------------------------------
    # 1. City search
    # ------------------------------------------------------------------
    def search_city(
        self,
        query: str,
        lang: str = "en",
    ) -> List[Dict[str, Any]]:
        """
        Search for cities by name.

        Parameters
        ----------
        query : str
            City name or partial name.
        lang : str
            Language code for result labels (default "en").

        Returns
        -------
        list of dict, each containing:
            lat, lon, altitude, address (city, state, country, tz_name, tz_offset)

        Example
        -------
        >>> client.search_city("London")
        [{'lat': 51.5073359, 'lon': -0.12765, 'altitude': 25,
          'address': {'city': 'London', 'city_en': 'London', ...}}, ...]
        """
        url = (
            f"{WWW_BASE}/ventusky_mesta.php"
            f"?q={urllib.parse.quote(query)}&lang={lang}"
        )
        return _get_json(url)

    # ------------------------------------------------------------------
    # 2. Reverse geocode / nearest named locations
    # ------------------------------------------------------------------
    def get_nearest_locations(
        self,
        lat: float,
        lon: float,
        zoom: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Return named locations near the given coordinate.

        Parameters
        ----------
        lat, lon : float
            Latitude and longitude in decimal degrees.
        zoom : int
            Map zoom level; affects how many nearby locations are returned.

        Returns
        -------
        list of dict, each containing:
            name, ascii, url (slug for city page), distance (km), id, lat, lon

        Example
        -------
        >>> client.get_nearest_locations(lat=40.7128, lon=-74.006)
        [{'name': 'New York', 'ascii': 'New York', 'url': 'new-york',
          'distance': 0, ...}, ...]
        """
        url = (
            f"{WWW_BASE}/ventusky_location.json.php"
            f"?lat={lat}&lon={lon}&zoom={zoom}"
        )
        return _get_json(url)

    # ------------------------------------------------------------------
    # 3. Whole-world weather tile (JPEG image)
    # ------------------------------------------------------------------
    def get_weather_tile(
        self,
        model: str,
        layer: str,
        dt: datetime.datetime,
        minutes: int = 0,
    ) -> bytes:
        """
        Download a whole-world weather tile as a JPEG image.

        The image is an equirectangular (lon/lat) projection.
        For standard 1-hour models: minutes = 0.
        For sub-hourly (e.g. HRRR 10-min intervals): minutes ∈ {0,10,20,30,40,50}.

        Parameters
        ----------
        model : str
            Forecast model identifier, e.g. "gfs", "icon", "ecmwf-hres".
            See MODELS constant for the full list.
        layer : str
            Layer file identifier, e.g. "teplota_2_m", "srazky_1h".
            Use LAYER_FILES dict to map human-readable names to file IDs.
        dt : datetime.datetime
            Forecast valid time (UTC).
        minutes : int
            Sub-hourly minute offset (0, 10, 20, 30, 40, or 50).

        Returns
        -------
        bytes
            JPEG image data.

        URL template (from JS source variable kb / Ta):
            {DATA_BASE}/{yyyy/MM/dd}/{model}/whole_world/
            hour_{HH}{minutesFolder}/{model}_{layer}_{yyyyMMdd_HH}{min}.jpg

        Examples
        --------
        >>> from datetime import datetime, timezone
        >>> t = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)
        >>> img = client.get_weather_tile("gfs", "teplota_2_m", t)
        """
        fmt = _fmt(dt)
        minutes_folder = f"_{minutes:02d}" if minutes else ""
        minutes_suffix = f"_{minutes:02d}" if minutes else ""
        url = (
            f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
            f"/{model}/whole_world"
            f"/hour_{fmt['HH']}{minutes_folder}"
            f"/{model}_{layer}_{fmt['yyyyMMdd_HH']}{minutes_suffix}.jpg"
        )
        return _get(url)

    # ------------------------------------------------------------------
    # 4. Regional/tiled weather tile (JPEG)
    # ------------------------------------------------------------------
    def get_tiled_weather_tile(
        self,
        model: str,
        layer: str,
        dt: datetime.datetime,
        tile_x: int = 0,
        tile_y: int = 0,
        minutes: int = 0,
    ) -> bytes:
        """
        Download a regional weather tile (tilled_world).

        Used for high-resolution regional models (HRRR, ICON-DE, ICON-EU, etc.)
        where the data is split into multiple tiles.

        Parameters
        ----------
        model : str
            Model identifier (see MODELS).
        layer : str
            Layer file identifier (see LAYER_FILES).
        dt : datetime.datetime
            Forecast valid time (UTC).
        tile_x, tile_y : int
            Tile grid offsets (both start at 0).
        minutes : int
            Sub-hourly minute offset (0, 10, 20, 30, 40, or 50).

        Returns
        -------
        bytes
            JPEG image data.

        URL template (from JS source variable kb):
            {DATA_BASE}/{yyyy/MM/dd}/{model}/tilled_world/
            hour_{HH}{minutesFolder}/{model}_{layer}_{tileX}_{tileY}
            _{yyyyMMdd_HH}{min}.jpg
        """
        fmt = _fmt(dt)
        minutes_folder = f"_{minutes:02d}" if minutes else ""
        minutes_suffix = f"_{minutes:02d}" if minutes else ""
        url = (
            f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
            f"/{model}/tilled_world"
            f"/hour_{fmt['HH']}{minutes_folder}"
            f"/{model}_{layer}_{tile_x}_{tile_y}"
            f"_{fmt['yyyyMMdd_HH']}{minutes_suffix}.jpg"
        )
        return _get(url)

    # ------------------------------------------------------------------
    # 5. Pressure systems (H/L centres) JSON
    # ------------------------------------------------------------------
    def get_pressure_systems(
        self,
        model: str,
        dt: datetime.datetime,
        minutes: int = 0,
    ) -> Dict[str, List]:
        """
        Return high and low pressure centre positions.

        Parameters
        ----------
        model : str
            Forecast model identifier.
        dt : datetime.datetime
            Forecast valid time (UTC).
        minutes : int
            Sub-hourly minute offset.

        Returns
        -------
        dict with keys:
            "l" : list of [lat, lon, hPa] for low-pressure centres
            "h" : list of [lat, lon, hPa] for high-pressure centres

        URL template (JS source variable fb):
            {DATA_BASE}/{yyyy/MM/dd}/{model}/whole_world/
            hour_{HH}{minutesFolder}/{model}_pressure_low_high_{yyyyMMdd_HH}.json

        Example
        -------
        >>> data = client.get_pressure_systems("gfs", t)
        >>> print(data["l"][:2])   # first two lows
        [[-61.75, -58.5, 950], ...]
        """
        fmt = _fmt(dt)
        minutes_folder = f"_{minutes:02d}" if minutes else ""
        minutes_suffix = f"_{minutes:02d}" if minutes else ""
        url = (
            f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
            f"/{model}/whole_world"
            f"/hour_{fmt['HH']}{minutes_folder}"
            f"/{model}_pressure_low_high_{fmt['yyyyMMdd_HH']}{minutes_suffix}.json"
        )
        return _get_json(url)

    # ------------------------------------------------------------------
    # 6. Weather fronts JSON
    # ------------------------------------------------------------------
    def get_weather_fronts(
        self,
        model: str,
        dt: datetime.datetime,
    ) -> Dict[str, List]:
        """
        Return weather front polyline data.

        Parameters
        ----------
        model : str
            Forecast model identifier (typically "gfs" or "icon").
        dt : datetime.datetime
            Forecast valid time (UTC).

        Returns
        -------
        dict with key "fronts": list of front objects, each containing:
            type      : "warm" | "cold" | "occluded" | "stationary"
            direction : "right" | "left"
            points    : list of [x, y] coordinates (internal projection)

        URL template (JS source variable gb):
            {DATA_BASE}/{yyyy}/{MM}/{dd}/{model}/whole_world/
            hour_{HH}/{model}_fronts_{yyyyMMdd_HH}.json

        Example
        -------
        >>> fronts = client.get_weather_fronts("gfs", t)
        >>> print(len(fronts["fronts"]))   # number of fronts
        141
        """
        fmt = _fmt(dt)
        url = (
            f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
            f"/{model}/whole_world"
            f"/hour_{fmt['HH']}"
            f"/{model}_fronts_{fmt['yyyyMMdd_HH']}.json"
        )
        return _get_json(url)

    # ------------------------------------------------------------------
    # 7. Isolines (isobars, isotherms, etc.)
    # ------------------------------------------------------------------
    def get_isolines(
        self,
        model: str,
        isoline_type: str,
        dt: datetime.datetime,
    ) -> bytes:
        """
        Download isoline data.

        Despite the .json extension, the server returns PNG-encoded data
        (a custom binary format used by the Ventusky canvas renderer).

        Parameters
        ----------
        model : str
            Forecast model identifier.
        isoline_type : str
            One of: "pressure", "geopotential-300hpa", "geopotential-500hpa",
            "geopotential-850hpa", "dew", "temperature-2m",
            "temperature-850hpa", "freezing".
            See ISOLINE_TYPES constant.
        dt : datetime.datetime
            Forecast valid time (UTC).

        Returns
        -------
        bytes
            PNG-encoded isoline data (raw binary, not a standard image).

        URL template (JS source variable ib):
            {DATA_BASE}/{yyyy}/{MM}/{dd}/{model}/whole_world/
            hour_{HH}/{model}_iso_{type}_{yyyyMMdd_HH}.json
        """
        fmt = _fmt(dt)
        url = (
            f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
            f"/{model}/whole_world"
            f"/hour_{fmt['HH']}"
            f"/{model}_iso_{isoline_type}_{fmt['yyyyMMdd_HH']}.json"
        )
        return _get(url)

    # ------------------------------------------------------------------
    # 8. Hurricane / tropical storm tracks
    # ------------------------------------------------------------------
    def get_hurricane_tracks(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> Any:
        """
        Return tropical storm / hurricane track data.

        Parameters
        ----------
        start_time : datetime.datetime
            Start of time range (UTC).
        end_time : datetime.datetime
            End of time range (UTC).

        Returns
        -------
        Parsed JSON (list or dict).

        URL template (JS source variable xb):
            https://api.ventusky.com/v2/api.ventusky_hurricane.json.php
                ?end_time_unix=<ms>&start_time_unix=<ms>
        """
        def _ms(d: datetime.datetime) -> int:
            epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return int((d - epoch).total_seconds() * 1000)

        url = (
            f"{API_BASE}/v2/api.ventusky_hurricane.json.php"
            f"?end_time_unix={_ms(end_time)}"
            f"&start_time_unix={_ms(start_time)}"
        )
        return _get_json(url)

    # ------------------------------------------------------------------
    # 9. Webcam list
    # ------------------------------------------------------------------
    def get_webcam_list(self) -> Dict[str, Any]:
        """
        Return a list of all active webcam IDs and metadata.

        Returns
        -------
        dict with key "actual": list of webcam IDs (integers)

        URL: https://webcams.ventusky.com/update.json
        """
        url = f"{WEBCAM_BASE}/update.json"
        return _get_json(url)

    # ------------------------------------------------------------------
    # 10. Nearest webcams
    # ------------------------------------------------------------------
    def get_nearest_webcams(
        self,
        lat: float,
        lon: float,
        count: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Return the nearest webcams to a given location.

        Parameters
        ----------
        lat, lon : float
            Coordinate in decimal degrees.
        count : int
            Maximum number of results.

        Returns
        -------
        list of dict, each containing:
            title, id, lat, lon, source, q (quality), distance (km)

        URL template:
            https://webcams.ventusky.com/api/api.get_nearest_camera.php
                ?lat=<lat>&lon=<lon>&count=<count>
        """
        url = (
            f"{WEBCAM_BASE}/api/api.get_nearest_camera.php"
            f"?lat={lat}&lon={lon}&count={count}"
        )
        return _get_json(url)

    # ------------------------------------------------------------------
    # 11. Webcam latest thumbnail
    # ------------------------------------------------------------------
    def get_webcam_thumbnail(
        self,
        cam_id: int,
        timestamp: Optional[datetime.datetime] = None,
    ) -> bytes:
        """
        Download the latest thumbnail for a webcam.

        Parameters
        ----------
        cam_id : int
            Webcam ID (from get_nearest_webcams or get_webcam_list).
        timestamp : datetime.datetime, optional
            If provided, used as a cache-buster in the URL.
            Defaults to current UTC time.

        Returns
        -------
        bytes
            JPEG image data.

        URL template (from JS source):
            https://webcams.ventusky.com/data/{idLast2}/{id}/latest_thumb.jpg
                ?{MMddHHmm}
        """
        if timestamp is None:
            timestamp = datetime.datetime.utcnow()
        id_str = str(cam_id)
        id_last2 = id_str[-2:]
        cache_buster = timestamp.strftime("%m%d%H%M")
        url = (
            f"{WEBCAM_BASE}/data/{id_last2}/{cam_id}"
            f"/latest_thumb.jpg?{cache_buster}"
        )
        return _get(url)

    # ------------------------------------------------------------------
    # 12. Webcam historical frame
    # ------------------------------------------------------------------
    def get_webcam_frame(
        self,
        cam_id: int,
        dt: datetime.datetime,
        steps: int = 1,
    ) -> bytes:
        """
        Download a historical image frame from a webcam.

        Parameters
        ----------
        cam_id : int
            Webcam ID.
        dt : datetime.datetime
            Desired frame time.
        steps : int
            Number of steps (interval size) – Ventusky uses this to choose
            the archive folder.

        Returns
        -------
        bytes
            JPEG image data.

        URL template (from JS source):
            https://webcams.ventusky.com/data/{idLast2}/{id}/{steps}/
                {yyyyMMdd_HHmm}.jpg
        """
        id_str = str(cam_id)
        id_last2 = id_str[-2:]
        frame_time = dt.strftime("%Y%m%d_%H%M")
        url = (
            f"{WEBCAM_BASE}/data/{id_last2}/{cam_id}"
            f"/{steps}/{frame_time}.jpg"
        )
        return _get(url)

    # ------------------------------------------------------------------
    # 13. Static base-map tiles
    # ------------------------------------------------------------------
    def get_static_tile(
        self,
        layer: str,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        """
        Download a static base-map tile (land, borders, cities, OSM).

        Parameters
        ----------
        layer : str
            One of: "land", "border", "cities", "cams", "osm".
            See STATIC_TILE_LAYERS constant.
        z : int
            Zoom level.
        x, y : int
            Tile coordinates (OSM slippy-map scheme).

        Returns
        -------
        bytes
            PNG image data.

        URL: https://static.ventusky.com/tiles/{version}/{layer}/{z}/{x}/{y}.png
        """
        base = STATIC_TILE_LAYERS.get(layer)
        if base is None:
            raise ValueError(f"Unknown layer '{layer}'. Choose from {list(STATIC_TILE_LAYERS)}")
        url = f"{base}/{z}/{x}/{y}.png"
        return _get(url)

    # ------------------------------------------------------------------
    # 14. High-zoom map tiles (zoom >= 13)
    # ------------------------------------------------------------------
    def get_map_tile(self, z: int, x: int, y: int) -> bytes:
        """
        Download a high-resolution map tile (zoom ≥ 13).

        These are detailed OpenStreetMap-derived tiles served from
        map.ventusky.com, used at zoom levels 13 and above.

        Parameters
        ----------
        z : int
            Zoom level (13 or higher recommended; tested at zoom 13).
        x, y : int
            Tile coordinates (OSM slippy-map scheme).

        Returns
        -------
        bytes
            PNG image data.

        URL: https://map.ventusky.com/tiles/{z}/{x}/{y}.png?256
        """
        url = f"{MAP_BASE}/tiles/{z}/{x}/{y}.png?256"
        return _get(url)

    # ------------------------------------------------------------------
    # 15. WAQI air quality station (third-party, token embedded in Ventusky JS)
    # ------------------------------------------------------------------
    def get_waqi_aqi(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Get air quality index data for a location from the WAQI API.

        Ventusky embeds a WAQI API token in its JavaScript bundle
        (token: 904a1bc6edf77c428347f2fe54cf663bcffaec21).
        This endpoint is used when clicking on the AQI chart panel.

        Parameters
        ----------
        lat, lon : float
            Location coordinates.

        Returns
        -------
        dict
            WAQI API response with station data, AQI value, pollutant breakdown.

        URL: https://api.waqi.info/feed/geo:{lat};{lon}/?token=<token>
        """
        token = "904a1bc6edf77c428347f2fe54cf663bcffaec21"
        url = f"https://api.waqi.info/feed/geo:{lat};{lon}/?token={token}"
        return _get_json(url)

    # ------------------------------------------------------------------
    # 16. User info (requires session cookie)
    # ------------------------------------------------------------------
    def get_user_info(self, session_cookie: str) -> Dict[str, Any]:
        """
        Get the logged-in user's profile information.

        This requires a valid 'ventusky_permanent' session cookie
        obtained from https://my.ventusky.com/login/.

        Parameters
        ----------
        session_cookie : str
            Value of the 'ventusky_permanent' cookie.

        Returns
        -------
        dict
            User profile data (id, email, premium status, etc.)
            Returns empty dict if not authenticated.

        URL: https://users.ventusky.com/api/api.logged_user_info.php
        """
        url = f"{USERS_BASE}/api/api.logged_user_info.php"
        headers = {"Cookie": f"ventusky_permanent={session_cookie}"}
        raw = _get(url, headers=headers)
        return json.loads(raw or "[]")

    # ------------------------------------------------------------------
    # Utility: build a complete URL without downloading
    # ------------------------------------------------------------------
    def build_weather_tile_url(
        self,
        model: str,
        layer: str,
        dt: datetime.datetime,
        tiled: bool = False,
        tile_x: int = 0,
        tile_y: int = 0,
        minutes: int = 0,
    ) -> str:
        """
        Return the URL for a weather tile without downloading it.

        Parameters
        ----------
        model : str
            Model identifier.
        layer : str
            Layer file identifier.
        dt : datetime.datetime
            Forecast valid time (UTC).
        tiled : bool
            If True, return a tilled_world (regional) URL.
        tile_x, tile_y : int
            Tile offsets (used when tiled=True).
        minutes : int
            Sub-hourly minute offset.

        Returns
        -------
        str
            Full URL string.
        """
        fmt = _fmt(dt)
        minutes_folder = f"_{minutes:02d}" if minutes else ""
        minutes_suffix = f"_{minutes:02d}" if minutes else ""
        if tiled:
            return (
                f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
                f"/{model}/tilled_world"
                f"/hour_{fmt['HH']}{minutes_folder}"
                f"/{model}_{layer}_{tile_x}_{tile_y}"
                f"_{fmt['yyyyMMdd_HH']}{minutes_suffix}.jpg"
            )
        return (
            f"{DATA_BASE}/{fmt['yyyy']}/{fmt['MM']}/{fmt['dd']}"
            f"/{model}/whole_world"
            f"/hour_{fmt['HH']}{minutes_folder}"
            f"/{model}_{layer}_{fmt['yyyyMMdd_HH']}{minutes_suffix}.jpg"
        )


# ---------------------------------------------------------------------------
# Quick demonstration
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    client = VentuskyClient()
    now = datetime.datetime(2026, 3, 25, 0, 0, tzinfo=datetime.timezone.utc)

    print("=== Ventusky API Client Demo ===\n")

    # 1. City search
    print("1. City search for 'Tokyo':")
    try:
        results = client.search_city("Tokyo")
        for r in results[:2]:
            addr = r.get("address", {})
            city = addr.get("city") or addr.get("city_en", "?")
            country = addr.get("country", "?")
            print(f"   {city}, {country}  "
                  f"({r['lat']:.4f}, {r['lon']:.4f})")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # 2. Nearest locations
    print("2. Nearest locations to (40.71, -74.01):")
    try:
        locs = client.get_nearest_locations(40.71, -74.01)
        for loc in locs[:3]:
            print(f"   {loc['name']}  ({loc['lat']:.3f}, {loc['lon']:.3f})")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # 3. Weather tile URL
    print("3. GFS 2m temperature tile URL:")
    url = client.build_weather_tile_url("gfs", "teplota_2_m", now)
    print(f"   {url}")

    print()

    # 4. Pressure systems
    print("4. Pressure systems (first low):")
    try:
        ps = client.get_pressure_systems("gfs", now)
        if ps.get("l"):
            lat, lon, hpa = ps["l"][0]
            print(f"   Low: {lat:.2f}°N {lon:.2f}°E  {hpa} hPa")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # 5. Weather fronts
    print("5. Weather fronts:")
    try:
        fronts = client.get_weather_fronts("gfs", now)
        n = len(fronts.get("fronts", []))
        print(f"   {n} fronts returned")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # 6. Nearest webcams
    print("6. Nearest webcams to New York:")
    try:
        cams = client.get_nearest_webcams(40.7128, -74.006, count=3)
        for c in cams:
            print(f"   [{c['id']}] {c['title']}  {c['distance']:.2f} km")
    except Exception as e:
        print(f"   Error: {e}")

    print()
    print("Done.")
