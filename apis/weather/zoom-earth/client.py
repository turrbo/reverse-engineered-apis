"""
Zoom Earth API Client
======================
Reverse-engineered client for the hidden/internal APIs of https://zoom.earth

Discovered by analyzing the minified JavaScript bundle at:
  https://zoom.earth/assets/js/app.d4802fd1.js

The JS uses a custom obfuscation scheme: ROT-13 applied to base64-encoded strings.

IMPORTANT:
  - All API endpoints are undocumented and may change without notice.
  - Tile endpoints at tiles.zoom.earth require a valid Referer header.
  - The weather API requires a time-based Request-Signature header.
  - This client is for educational/research purposes only.
"""

from __future__ import annotations

import base64
import json
import random
import time
from datetime import datetime, timezone
from typing import Any
import urllib.request
import urllib.error
from urllib.parse import urlencode


# ---------------------------------------------------------------------------
# Base URLs (decoded from obfuscated JS strings using ROT-13 + base64)
# ---------------------------------------------------------------------------

BASE_SITE    = "https://zoom.earth"        # Main site (data API)
BASE_TILES   = "https://tiles.zoom.earth"  # Tile server
BASE_API     = "https://api.zoom.earth"    # Weather API
BASE_ACCOUNT = "https://account.zoom.earth"  # Account/auth API

# ---------------------------------------------------------------------------
# Data API endpoints  (https://zoom.earth/data/...)
# ---------------------------------------------------------------------------
EP_TIME          = "/data/time/"
EP_VERSION       = "/data/version/"
EP_FIRES         = "/data/fires/"
EP_STORMS        = "/data/storms/"
EP_GEOCODE       = "/data/geocode/"
EP_SEARCH        = "/data/search/"
EP_PLACES        = "/data/places/"
EP_NOTIFICATIONS = "/data/notifications/"
EP_OUTAGES       = "/data/outages/"
EP_LOG           = "/data/log/"
EP_PING          = "/data/ping/"
EP_PUSH          = "/data/push/"

# Tile "times" JSON endpoints (https://tiles.zoom.earth/times/...)
EP_TIMES_GEOCOLOR = "/times/geocolor.json"
EP_TIMES_RADAR    = "/times/radar.json"
EP_TIMES_GFS      = "/times/gfs.json"
EP_TIMES_ICON     = "/times/icon.json"

# Tile URL templates (https://tiles.zoom.earth/...)
TILE_GEOCOLOR    = "/geocolor/{satellite}/{date}/{z}/{y}/{x}.jpg"
TILE_BLUEMARBLE  = "/static/bluemarble/{month}/{z}/{y}/{x}.jpg"
TILE_FILL        = "/static/fill/{version}/1x/webp/{z}/{y}/{x}.webp"
TILE_LAND        = "/static/land/{version}/1x/webp/{z}/{y}/{x}.webp"
TILE_LINE        = "/static/line/{version}/1x/webp/{z}/{y}/{x}.webp"
TILE_RADAR       = "/radar/reflectivity/{date}/{hash}/{z}/{y}/{x}.webp"
TILE_RADAR_COV   = "/radar/coverage/{z}/{y}/{x}.webp"
TILE_HEAT        = "/proxy/heat/{date}/{extent}.jpg"
TILE_FORECAST    = "/{model}/{version}/{layer}/webp/{level}/{run_date}/f{fhour}/{z}/{y}/{x}.webp"

# Weather API endpoint
EP_WEATHER = "/weather/"

# Satellite IDs (xs enum from JS)
SATELLITE_GOES_WEST   = "goes-west"    # GOES-18, 135°W, Western Americas + Pacific
SATELLITE_GOES_EAST   = "goes-east"    # GOES-16, 75.2°W, Eastern Americas + Atlantic
SATELLITE_MTG_ZERO    = "mtg-zero"     # MTG-I1 (Meteosat Third Gen), 9.5°E
SATELLITE_MSG_ZERO    = "msg-zero"     # Meteosat-11, 9.5°E, Europe/Africa
SATELLITE_MSG_IODC    = "msg-iodc"     # Meteosat-8, 41.5°E, Indian Ocean
SATELLITE_HIMAWARI    = "himawari"     # Himawari-9, 140.7°E, Asia/Pacific
SATELLITE_GEO_KOMPSAT = "geo-kompsat" # GK-2A, 128.2°E, East Asia

# Forecast model IDs (gs enum from JS)
MODEL_GFS  = "gfs"   # NOAA GFS, ~22 km resolution
MODEL_ICON = "icon"  # DWD ICON, ~13 km resolution

# Model version (all currently "v1")
MODEL_VERSION = "v1"

# Forecast layer IDs (vi enum from JS) and their altitude levels (bi enum from JS)
LAYERS = {
    "precipitation":      "surface",    # mm/hr rain + snow
    "wind-speed":         "10m",        # m/s at 10m above ground
    "wind-gusts":         "surface",    # m/s
    "temperature":        "2m",         # °C at 2m above ground
    "temperature-feel":   "2m",         # °C feels-like
    "temperature-wet-bulb": "2m",       # °C wet bulb
    "humidity":           "2m",         # %
    "dew-point":          "2m",         # °C
    "pressure":           "msl",        # hPa mean sea level
}

# Blue marble month names (gi array in JS)
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]

# ---------------------------------------------------------------------------
# Internal utility functions (mirroring JS helper functions)
# ---------------------------------------------------------------------------

def _rot13(text: str) -> str:
    """Apply ROT-13 cipher (used for URL obfuscation in the JS bundle)."""
    result = []
    for c in text:
        if c.isalpha():
            s = ord(c)
            i = (s & 31) - 1
            shifted = s - i + (i + 13) % 26
            result.append(chr(shifted))
        else:
            result.append(c)
    return "".join(result)


def _djb2_hex(text: str) -> str:
    """DJB2 hash, returned as 8-char lowercase hex (bn function in JS)."""
    h = 5381
    for c in text:
        h = ((h << 5) + h + ord(c)) & 0xFFFFFFFF
    return format(h, "08x")


def _format_tile_date(dt: datetime, step_minutes: int = 10) -> str:
    """
    Format a UTC datetime into the tile URL date component.
    Equivalent to Hh(date, step_minutes) in JS.

    Returns: 'YYYY-MM-DD/HHMM'  (minutes rounded down to step_minutes)
    """
    rounded_min = (dt.minute // step_minutes) * step_minutes
    adjusted = dt.replace(minute=rounded_min, second=0, microsecond=0,
                          tzinfo=timezone.utc)
    return adjusted.strftime("%Y-%m-%d") + "/" + adjusted.strftime("%H%M")


def _format_date(dt: datetime) -> str:
    """Format a UTC datetime as 'YYYY-MM-DD' (Bh function in JS)."""
    return dt.strftime("%Y-%m-%d")


def _make_request_signature(lon: float, lat: float) -> str:
    """
    Generate a time-based Request-Signature header value for the weather API.

    The algorithm (reverse-engineered from JS):
      1. Round lon/lat to 3 decimal places.
      2. Compute a DJB2 hash of "lon~lat~timestamp_ms".
      3. Construct: hash8 + "." + timestamp_ms_hex12 + "." + rand_byte_hex2
      4. Base64-encode the string, then ROT-13 the base64 result.
    """
    r = round(lon, 3)
    o = round(lat, 3)
    ts_ms = int(time.time() * 1000)

    sig_hash = _djb2_hex(f"{r}~{o}~{ts_ms}")
    hex_ts = format(ts_ms, "012x")
    hex_rand = format(int(256 * random.random()), "02x")

    m = f"{sig_hash}.{hex_ts}.{hex_rand}"
    return _rot13(base64.b64encode(m.encode()).decode())


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://zoom.earth/",
    "Origin": "https://zoom.earth",
    "Accept": "*/*",
}


def _get(url: str, params: dict | None = None,
         extra_headers: dict | None = None,
         timeout: int = 15) -> Any:
    """Perform a GET request and return parsed JSON (or raw bytes)."""
    if params:
        url += "?" + urlencode(params)
    req = urllib.request.Request(url)
    for k, v in DEFAULT_HEADERS.items():
        req.add_header(k, v)
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read()
    ct = resp.headers.get("Content-Type", "")
    if "json" in ct:
        return json.loads(data)
    return data


def _post(url: str, body: dict,
          extra_headers: dict | None = None,
          timeout: int = 15) -> Any:
    """Perform a POST request with JSON body and return parsed JSON."""
    req = urllib.request.Request(url, method="POST")
    for k, v in DEFAULT_HEADERS.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    if extra_headers:
        for k, v in extra_headers.items():
            req.add_header(k, v)
    req.data = json.dumps(body).encode()
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ZoomEarthClient:
    """
    Client for the reverse-engineered Zoom Earth internal APIs.

    Example usage::

        client = ZoomEarthClient()

        # Get available satellite image times
        times = client.get_geocolor_times()
        goes_west_times = times["goes-west"]  # list of Unix timestamps

        # Download a satellite tile (zoom 5, tile x=10, y=12)
        tile_bytes = client.get_geocolor_tile(
            satellite="goes-west",
            timestamp=goes_west_times[-1],
            z=5, y=12, x=10
        )
        with open("tile.jpg", "wb") as f:
            f.write(tile_bytes)

        # Get weather forecast for New York City
        weather = client.get_weather(lon=-74.006, lat=40.7128)
        for hour in weather["hourly"]["hours"][:3]:
            print(hour)
    """

    # ------------------------------------------------------------------
    # Server time / version
    # ------------------------------------------------------------------

    def get_server_time(self) -> dict:
        """
        GET https://zoom.earth/data/time/
        Returns the current server Unix timestamp.

        Response: {"time": 1774406256}
        """
        return _get(BASE_SITE + EP_TIME)

    def get_version(self) -> dict:
        """
        GET https://zoom.earth/data/version/
        Returns the current application version hash.

        Response: {"app": "d4802fd1"}
        """
        return _get(BASE_SITE + EP_VERSION)

    # ------------------------------------------------------------------
    # Tile availability (times JSON files)
    # ------------------------------------------------------------------

    def get_geocolor_times(self) -> dict:
        """
        GET https://tiles.zoom.earth/times/geocolor.json
        Returns available satellite image timestamps per satellite.

        Response structure::

            {
              "goes-west":   [unix_ts, unix_ts, ...],  # 10-min intervals
              "goes-east":   [...],
              "mtg-zero":    [...],
              "msg-zero":    [...],
              "msg-iodc":    [...],
              "himawari":    [...]
            }
        """
        return _get(BASE_TILES + EP_TIMES_GEOCOLOR)

    def get_radar_times(self) -> dict:
        """
        GET https://tiles.zoom.earth/times/radar.json
        Returns available radar timestamps and metadata.

        Response structure::

            {
              "reflectivity": {"1774147200": "8f2891eb", ...},  # ts -> tile hash
              "coverage":     {"1773774900": "6bd55917"},
              "areas":        [[lon, lat, ...], ...],
              "attributions": [...]
            }
        """
        return _get(BASE_TILES + EP_TIMES_RADAR)

    def get_forecast_times(self, model: str = MODEL_GFS) -> dict:
        """
        GET https://tiles.zoom.earth/times/{model}.json
        Returns available forecast run times per layer.

        Args:
            model: "gfs" or "icon"

        Response structure::

            {
              "precipitation": {"surface": {"run_ts": [forecast_hours], ...}},
              "wind-speed":    {"10m":     {...}},
              "temperature":   {"2m":      {...}},
              ...
            }
        """
        return _get(BASE_TILES + f"/times/{model}.json")

    # ------------------------------------------------------------------
    # Satellite image tiles
    # ------------------------------------------------------------------

    def get_geocolor_tile(self, satellite: str, timestamp: int,
                          z: int, y: int, x: int,
                          step_minutes: int = 10) -> bytes:
        """
        GET https://tiles.zoom.earth/geocolor/{satellite}/{date}/{z}/{y}/{x}.jpg

        Download a geocolor (true-color) satellite imagery tile.

        Args:
            satellite:     Satellite ID string (use SATELLITE_* constants).
                           "goes-west" | "goes-east" | "mtg-zero" | "msg-zero"
                           "msg-iodc" | "himawari" | "geo-kompsat"
            timestamp:     Unix timestamp (seconds) from get_geocolor_times().
            z:             Zoom level (0-7 for most satellites).
            y:             Tile Y coordinate (TMS scheme, y=0 at top).
            x:             Tile X coordinate.
            step_minutes:  Time rounding step in minutes (default 10).

        Returns:
            Raw JPEG bytes.

        Example tile URL:
            https://tiles.zoom.earth/geocolor/goes-west/2026-03-25/0220/4/6/4.jpg
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        date_str = _format_tile_date(dt, step_minutes)
        url = BASE_TILES + TILE_GEOCOLOR.format(
            satellite=satellite, date=date_str, z=z, y=y, x=x
        )
        return _get(url)

    def get_bluemarble_tile(self, month: int, z: int, y: int, x: int) -> bytes:
        """
        GET https://tiles.zoom.earth/static/bluemarble/{month}/{z}/{y}/{x}.jpg

        Download a NASA Blue Marble static background tile.

        Args:
            month: Month as 0-based integer (0=Jan, 11=Dec).
            z, y, x: Tile coordinates.

        Returns:
            Raw JPEG bytes.
        """
        month_str = MONTHS[month % 12]
        url = BASE_TILES + TILE_BLUEMARBLE.format(
            month=month_str, z=z, y=y, x=x
        )
        return _get(url)

    def get_land_tile(self, version: str, z: int, y: int, x: int,
                      scale: int = 1) -> bytes:
        """
        GET https://tiles.zoom.earth/static/land/{version}/{scale}x/webp/{z}/{y}/{x}.webp

        Download a land/terrain background tile (WebP).

        Args:
            version: Tile version string from get_version() or known config.
            z, y, x: Tile coordinates.
            scale:   Pixel ratio (1 or 2 for HiDPI).

        Returns:
            Raw WebP bytes.
        """
        url = BASE_TILES + f"/static/land/{version}/{scale}x/webp/{z}/{y}/{x}.webp"
        return _get(url)

    # ------------------------------------------------------------------
    # Radar tiles
    # ------------------------------------------------------------------

    def get_radar_tile(self, timestamp: int, tile_hash: str,
                       z: int, y: int, x: int) -> bytes:
        """
        GET https://tiles.zoom.earth/radar/reflectivity/{date}/{hash}/{z}/{y}/{x}.webp

        Download a radar reflectivity tile.

        Args:
            timestamp:  Unix timestamp (seconds) from get_radar_times()["reflectivity"].
            tile_hash:  Hash string from get_radar_times()["reflectivity"][str(timestamp)].
            z, y, x:    Tile coordinates.

        Returns:
            Raw PNG/WebP bytes.

        Example:
            radar_data = client.get_radar_times()
            ts = list(radar_data["reflectivity"].keys())[-1]
            h  = radar_data["reflectivity"][ts]
            tile = client.get_radar_tile(int(ts), h, z=5, y=10, x=12)
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        date_str = _format_tile_date(dt, step_minutes=5)
        url = BASE_TILES + TILE_RADAR.format(
            date=date_str, hash=tile_hash, z=z, y=y, x=x
        )
        return _get(url)

    def get_radar_coverage_tile(self, z: int, y: int, x: int) -> bytes:
        """
        GET https://tiles.zoom.earth/radar/coverage/{z}/{y}/{x}.webp

        Download a radar coverage area tile (static overlay).

        Returns:
            Raw WebP bytes.
        """
        url = BASE_TILES + TILE_RADAR_COV.format(z=z, y=y, x=x)
        return _get(url)

    # ------------------------------------------------------------------
    # Forecast model tiles
    # ------------------------------------------------------------------

    def get_forecast_tile(self, model: str, layer: str,
                          run_timestamp: int, forecast_hour: int,
                          z: int, y: int, x: int) -> bytes:
        """
        GET https://tiles.zoom.earth/{model}/v1/{layer}/webp/{level}/{run_date}/f{fhour}/{z}/{y}/{x}.webp

        Download a forecast model tile.

        Args:
            model:           "gfs" or "icon"
            layer:           Layer name (use keys from LAYERS dict):
                             "precipitation" | "wind-speed" | "wind-gusts"
                             "temperature" | "temperature-feel" | "temperature-wet-bulb"
                             "humidity" | "dew-point" | "pressure"
            run_timestamp:   Unix timestamp (seconds) of the model run from
                             get_forecast_times()[layer][level].keys()
            forecast_hour:   Forecast hour offset (e.g. 0, 1, 2, ..., 240).
            z, y, x:         Tile coordinates.

        Returns:
            Raw WebP bytes.

        Example:
            times = client.get_forecast_times("gfs")
            layer = "temperature"
            level = LAYERS[layer]  # "2m"
            runs = times[layer][level]
            run_ts = list(runs.keys())[-1]
            fhours = runs[run_ts]
            tile = client.get_forecast_tile("gfs", layer, int(run_ts), fhours[0], 5, 10, 12)
        """
        level = LAYERS.get(layer, "surface")
        dt = datetime.fromtimestamp(run_timestamp, tz=timezone.utc)
        run_date_str = _format_tile_date(dt, step_minutes=60)
        fhour_str = str(forecast_hour).zfill(3)
        url = BASE_TILES + TILE_FORECAST.format(
            model=model,
            version=MODEL_VERSION,
            layer=layer,
            level=level,
            run_date=run_date_str,
            fhour=fhour_str,
            z=z, y=y, x=x,
        )
        return _get(url)

    # ------------------------------------------------------------------
    # Weather API
    # ------------------------------------------------------------------

    def get_weather(self, lon: float, lat: float,
                    model: str = MODEL_GFS,
                    daily: bool = False) -> dict:
        """
        POST https://api.zoom.earth/weather/

        Get hourly or daily weather forecast for a location.

        Requires a time-based Request-Signature header (auto-generated).

        Args:
            lon:    Longitude (decimal degrees).
            lat:    Latitude (decimal degrees).
            model:  Forecast model: "gfs" or "icon". Used for hourly mode.
            daily:  If True, request daily summary; otherwise hourly.

        Returns (hourly mode)::

            {
              "metadata": {"longitude": -74.006, "latitude": 40.713,
                           "timeZone": "America/New_York"},
              "hourly": {
                "model": "gfs",
                "modelVersion": "v1",
                "sunrise": ["2026-03-25T10:30Z", ...],
                "sunset":  ["2026-03-25T23:05Z", ...],
                "hours": [
                  {
                    "date": "2026-03-25T01:00Z",
                    "cloud": 100,          # % cloud cover
                    "rain": 0,             # mm precipitation (rain)
                    "snow": 0,             # mm precipitation (snow)
                    "windSpeed": 5.49,     # m/s
                    "windDirection": 197,  # degrees from north
                    "windGusts": 8.43,     # m/s
                    "temperature": 6.26,   # °C
                    "temperatureFeel": 2.76, # °C apparent temperature
                    "temperatureWetBulb": 1.4, # °C wet-bulb temp
                    "humidity": 44.66,     # %
                    "dewPoint": -5.03,     # °C
                    "pressure": 1028.4     # hPa mean sea level
                  },
                  ...
                ]
              }
            }
        """
        sig = _make_request_signature(lon, lat)
        body: dict[str, Any] = {
            "longitude": round(lon, 3),
            "latitude":  round(lat, 3),
            "timeZone":  True,
        }
        if daily:
            body["daily"] = {
                "days": [
                    "condition", "windSpeed", "windDirection", "windGusts",
                    "temperature", "temperatureFeel", "temperatureWetBulb",
                    "humidity", "dewPoint", "pressure",
                ],
                "conditions": [],
            }
        else:
            body["hourly"] = {
                "hours": [
                    "cloud", "rain", "snow",
                    "windSpeed", "windDirection", "windGusts",
                    "temperature", "temperatureFeel", "temperatureWetBulb",
                    "humidity", "dewPoint", "pressure",
                ],
                "sunrise": True,
                "sunset":  True,
                "model":   model,
                "modelVersion": MODEL_VERSION,
            }
        return _post(
            BASE_API + EP_WEATHER,
            body,
            extra_headers={"Request-Signature": sig},
        )

    # ------------------------------------------------------------------
    # Fire / Heat data
    # ------------------------------------------------------------------

    def get_fires(self) -> list[dict]:
        """
        GET https://zoom.earth/data/fires/latest.json
        Returns active wildfire and prescribed burn locations.

        Response: list of fire objects::

            [
              {
                "id":          "us-ak-nenana-ridge-prescribed-burn",
                "name":        "Nenana Ridge Prescribed Burn",
                "coordinate":  [-148.69, 64.653617],  # [lon, lat]
                "admin":       "Yukon-Koyukuk County, Alaska, United States",
                "countryCode": "US",
                "type":        "PB",   # PB=Prescribed Burn, WF=Wildfire, etc.
                "date":        "2026-03-24T18:12Z"
              },
              ...
            ]
        """
        return _get(BASE_SITE + EP_FIRES + "latest.json")

    # ------------------------------------------------------------------
    # Storm / Tropical cyclone data
    # ------------------------------------------------------------------

    def get_storms(self, date: str | None = None,
                   date_to: str | None = None) -> dict:
        """
        GET https://zoom.earth/data/storms/?date=YYYY-MM-DD[&to=YYYY-MM-DD]
        Returns active storm IDs for the given date range.

        Args:
            date:    Date string "YYYY-MM-DD" (defaults to today if None).
            date_to: Optional end date for a range query.

        Response::

            {
              "storms":       ["narelle-2026", ...],  # active cyclone IDs
              "disturbances": []                       # potential developments
            }
        """
        params: dict[str, str] = {}
        if date:
            params["date"] = date
        if date_to:
            params["to"] = date_to
        return _get(BASE_SITE + EP_STORMS, params or None)

    def get_storm_details(self, storm_id: str) -> dict:
        """
        GET https://zoom.earth/data/storms/?id=STORM_ID
        Returns detailed information about a specific tropical storm.

        Args:
            storm_id: Storm ID string (e.g. "narelle-2026").

        Response structure (example)::

            {
              "id":          "narelle-2026",
              "name":        "Narelle",
              "title":       "Cyclone Narelle",
              "description": "Tropical Cyclone",
              "season":      "2026",
              "type":        "Cyclone",
              "max":         { ... },   # peak intensity info
              "track":       [...]      # list of track positions
            }
        """
        return _get(BASE_SITE + EP_STORMS, {"id": storm_id})

    # ------------------------------------------------------------------
    # Geocode / Location search
    # ------------------------------------------------------------------

    def geocode(self, query: str) -> dict:
        """
        GET https://zoom.earth/data/geocode/?q=QUERY
        Forward geocode a place name to coordinates.

        NOTE: This endpoint appears to return a default location when the
        query is not recognized. Use for approximate lookups only.

        Args:
            query: Place name string (e.g. "New York", "London").

        Response: {"lon": -74.0, "lat": 40.7}
        """
        return _get(BASE_SITE + EP_GEOCODE, {"q": query})

    # ------------------------------------------------------------------
    # Outages / System status
    # ------------------------------------------------------------------

    def get_outages(self) -> dict:
        """
        GET https://zoom.earth/data/outages/
        Returns current service outage messages.

        Response::

            {
              "outages": [
                {
                  "id":      "mtg-zero",
                  "message": "There is an outage ...",
                  "url":     "#map=satellite-hd"
                }
              ],
              "radar": "disabled" | null
            }
        """
        return _get(BASE_SITE + EP_OUTAGES)

    def get_notifications(self) -> list:
        """
        GET https://zoom.earth/data/notifications/
        Returns in-app notification messages.

        Response: [] (empty list when no notifications)
        """
        return _get(BASE_SITE + EP_NOTIFICATIONS)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_latest_geocolor_tile(self, satellite: str,
                                 z: int, y: int, x: int) -> bytes:
        """
        Download the most recent geocolor satellite tile for the given satellite.

        Convenience wrapper that automatically fetches the latest timestamp.

        Args:
            satellite: Satellite ID (use SATELLITE_* constants).
            z, y, x:   Tile coordinates.

        Returns:
            Raw JPEG bytes.
        """
        times = self.get_geocolor_times()
        available = times.get(satellite, [])
        if not available:
            raise ValueError(f"No times available for satellite: {satellite}")
        latest_ts = available[-1]
        return self.get_geocolor_tile(satellite, latest_ts, z, y, x)

    def get_latest_radar_tile(self, z: int, y: int, x: int) -> bytes:
        """
        Download the most recent radar reflectivity tile.

        Convenience wrapper that automatically fetches the latest timestamp.

        Args:
            z, y, x: Tile coordinates.

        Returns:
            Raw PNG/WebP bytes.
        """
        radar_data = self.get_radar_times()
        reflectivity = radar_data.get("reflectivity", {})
        if not reflectivity:
            raise ValueError("No radar reflectivity data available")
        latest_ts_str = sorted(reflectivity.keys(), key=int)[-1]
        tile_hash = reflectivity[latest_ts_str]
        return self.get_radar_tile(int(latest_ts_str), tile_hash, z, y, x)

    def get_latest_forecast_tile(self, model: str, layer: str,
                                 forecast_hour: int,
                                 z: int, y: int, x: int) -> bytes:
        """
        Download a forecast tile from the most recent model run.

        Args:
            model:         "gfs" or "icon"
            layer:         Layer name (e.g. "temperature", "wind-speed").
            forecast_hour: Forecast hour offset from the run time.
            z, y, x:       Tile coordinates.

        Returns:
            Raw WebP bytes.
        """
        times = self.get_forecast_times(model)
        level = LAYERS.get(layer, "surface")
        layer_times = times.get(layer, {}).get(level, {})
        if not layer_times:
            raise ValueError(f"No times available for {model}/{layer}/{level}")
        latest_run_ts = max(layer_times.keys(), key=int)
        available_hours = layer_times[latest_run_ts]
        if forecast_hour not in available_hours:
            forecast_hour = available_hours[0]
        return self.get_forecast_tile(
            model, layer, int(latest_run_ts), forecast_hour, z, y, x
        )

    def tile_url(self, satellite: str, timestamp: int,
                 z: int, y: int, x: int) -> str:
        """
        Build (but do not fetch) a geocolor tile URL.

        Useful for passing to mapping libraries like OpenLayers or Leaflet.

        Args:
            satellite: Satellite ID.
            timestamp: Unix timestamp (seconds).
            z, y, x:   Tile coordinates.

        Returns:
            Full URL string.
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        date_str = _format_tile_date(dt, 10)
        return BASE_TILES + TILE_GEOCOLOR.format(
            satellite=satellite, date=date_str, z=z, y=y, x=x
        )


# ---------------------------------------------------------------------------
# Tile coordinate helpers
# ---------------------------------------------------------------------------

def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """
    Convert a latitude/longitude to tile coordinates (x, y) at a given zoom level.

    Uses the standard Web Mercator (EPSG:3857) tile scheme where:
      - Tile (0, 0) is at the top-left (NW corner).
      - x increases eastward.
      - y increases southward.
      - The zoom level determines the number of tiles: 2^zoom * 2^zoom.

    Args:
        lat:  Latitude in decimal degrees (-90 to 90).
        lon:  Longitude in decimal degrees (-180 to 180).
        zoom: Zoom level (0-9 for satellite tiles).

    Returns:
        (x, y) tuple of integer tile coordinates.
    """
    import math
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
            / 2.0 * n)
    return x, y


def tile_to_lat_lon(x: int, y: int, zoom: int) -> tuple[float, float]:
    """
    Convert tile coordinates to the NW corner latitude/longitude.

    Args:
        x, y: Tile coordinates.
        zoom: Zoom level.

    Returns:
        (lat, lon) of the NW corner of the tile.
    """
    import math
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


# ---------------------------------------------------------------------------
# Demo / quick test
# ---------------------------------------------------------------------------

def _demo():
    """Run a quick demonstration of the API client."""
    client = ZoomEarthClient()

    print("=" * 60)
    print("Zoom Earth API Client - Demo")
    print("=" * 60)

    # Server time
    print("\n[1] Server time:")
    t = client.get_server_time()
    print(f"    Unix timestamp: {t['time']}  "
          f"({datetime.fromtimestamp(t['time'], tz=timezone.utc).isoformat()})")

    # Geocolor times
    print("\n[2] Geocolor satellite times (latest per satellite):")
    times = client.get_geocolor_times()
    for sat, ts_list in times.items():
        if ts_list:
            latest = ts_list[-1]
            dt = datetime.fromtimestamp(latest, tz=timezone.utc)
            print(f"    {sat:20s}: {len(ts_list):4d} frames, "
                  f"latest = {dt.strftime('%Y-%m-%d %H:%M')} UTC")

    # Radar times
    print("\n[3] Radar times:")
    radar = client.get_radar_times()
    refl = radar.get("reflectivity", {})
    if refl:
        keys = sorted(refl.keys(), key=int)
        print(f"    {len(keys)} reflectivity frames, "
              f"latest = {datetime.fromtimestamp(int(keys[-1]), tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")

    # Forecast times
    print("\n[4] GFS forecast runs (temperature/2m):")
    gfs_times = client.get_forecast_times("gfs")
    temp_runs = gfs_times.get("temperature", {}).get("2m", {})
    for run_ts_str in list(temp_runs.keys())[-3:]:
        dt = datetime.fromtimestamp(int(run_ts_str), tz=timezone.utc)
        hours = temp_runs[run_ts_str]
        print(f"    Run {dt.strftime('%Y-%m-%d %H:%M')} UTC  "
              f"-> {len(hours)} forecast hours")

    # Weather forecast
    print("\n[5] Weather forecast for New York City (40.71°N, -74.01°W):")
    weather = client.get_weather(lon=-74.006, lat=40.7128, model="gfs")
    meta = weather.get("metadata", {})
    print(f"    Time zone: {meta.get('timeZone')}")
    hourly = weather.get("hourly", {}).get("hours", [])
    for h in hourly[:3]:
        print(f"    {h['date']}  T={h['temperature']:.1f}°C  "
              f"Wind={h['windSpeed']:.1f} m/s  "
              f"Humidity={h['humidity']:.0f}%")

    # Fires
    print("\n[6] Active fires / burns:")
    fires = client.get_fires()
    print(f"    Total active fires: {len(fires)}")
    fire_types = {}
    for f in fires:
        t2 = f.get("type", "?")
        fire_types[t2] = fire_types.get(t2, 0) + 1
    for t2, cnt in sorted(fire_types.items()):
        print(f"    Type={t2}: {cnt}")

    # Storms
    print("\n[7] Active storms today:")
    storms = client.get_storms()
    print(f"    {storms}")

    # Outages
    print("\n[8] Service outages:")
    outages = client.get_outages()
    for o in outages.get("outages", []):
        print(f"    [{o['id']}] {o['message'][:80]}...")
    if outages.get("radar"):
        print(f"    Radar status: {outages['radar']}")

    # Tile URL example
    print("\n[9] Sample tile URLs:")
    if times.get("goes-west"):
        ts = times["goes-west"][-1]
        for z, y, x in [(3, 3, 2), (5, 12, 9), (7, 50, 38)]:
            url = client.tile_url("goes-west", ts, z, y, x)
            print(f"    z={z}: {url}")

    print("\n[Done]")


if __name__ == "__main__":
    _demo()
