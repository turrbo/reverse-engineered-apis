"""
Meteoblue Internal API Client
==============================
Reverse-engineered client for Meteoblue's hidden/internal APIs.

Discovered endpoints:
  1. Location Search API     - https://locationsearch.meteoblue.com/
  2. Meteogram Image API     - https://my.meteoblue.com/images/meteogram
  3. MultiModel API          - https://my.meteoblue.com/images/meteogram_multimodel
  4. Dataset Query API       - https://my.meteoblue.com/dataset/query
  5. Maps Inventory API      - https://maps-api.meteoblue.com/v1/map/inventory/filter
  6. Map Tiles API           - https://maptiles.meteoblue.com/
  7. User Favourites API     - https://www.meteoblue.com/user/favourite/
  8. Weather Archive API     - https://www.meteoblue.com/en/weather/archive/export

API Keys discovered:
  - n4UGDLso3gE6m2YI   (meteogram images - requires HMAC sig from server)
  - LYnNIfRrK2XWTtzw   (location search)
  - 5838a18e295d       (dataset query / historical data)
  - 1iw4Jq5NZK60Ig7O  (maps CDN tiles)

NOTE: The meteogram image API requires a time-limited HMAC signature generated
server-side. To bypass this, use the "sig scraping" method: fetch the webpage
for the desired forecast type, extract the pre-signed URL, then request it.
The dataset query API (5838a18e295d) also requires a sig for some operations
but allows direct queries with a valid timestamp + sig from the page.

Author: Reverse-engineered via browser network interception and JS analysis
"""

import re
import json
import time
import hashlib
import urllib.parse
from typing import Optional, Union
from datetime import datetime, timezone

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

BASE_URL = "https://www.meteoblue.com"
MY_URL = "https://my.meteoblue.com"
LOCATION_SEARCH_URL = "https://locationsearch.meteoblue.com"
MAPS_API_URL = "https://maps-api.meteoblue.com"
MAPTILES_URL = "https://maptiles.meteoblue.com"

# API keys extracted from the website JS/HTML
LOCATION_SEARCH_APIKEY = "LYnNIfRrK2XWTtzw"
METEOGRAM_APIKEY = "n4UGDLso3gE6m2YI"
DATASET_APIKEY = "5838a18e295d"
MAPS_CDN_APIKEY = "1iw4Jq5NZK60Ig7O"

# Weather model domains available in multimodel
AVAILABLE_DOMAINS = [
    "IFS025",      # ECMWF IFS (European Centre)
    "ICON",        # DWD ICON (Germany)
    "GFS05",       # NOAA GFS (USA)
    "NAM12",       # NOAA NAM 12km
    "NAM5",        # NOAA NAM 5km
    "NAM3",        # NOAA NAM 3km
    "HRRR",        # NOAA HRRR (High-Res Rapid Refresh)
    "MFGLOBAL",    # Meteo-France Global
    "UMGLOBAL10",  # UK Met Office UM Global 10km
    "GEM15",       # Environment Canada GEM 15km
    "GEM2",        # Environment Canada GEM 2km
    "NBM",         # National Blend of Models
    "AIFS025",     # ECMWF AI Forecast System
    "IFSHRES",     # ECMWF IFS HRES
    "NEMSGLOBAL",  # NEMS Global
    "NEMSGLOBAL_E", # NEMS Global Ensemble
    "ERA5T",       # ERA5 reanalysis (for historical)
]

# Meteogram image types
METEOGRAM_TYPES = {
    "standard":    "/images/meteogram",
    "multimodel":  "/images/meteogram_multimodel",
    "agro":        "/images/meteogram_agro",
    "air":         "/images/meteogram_air",
    "snow":        "/images/meteogram_snow",
    "sea_7day":    "/images/meteogram_sea_7day",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.meteoblue.com/",
}


# ─────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────

def _get(url: str, params: Optional[dict] = None, timeout: int = 20) -> dict:
    """Perform a GET request and return JSON response."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=True)

    if HAS_REQUESTS:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    else:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _get_raw(url: str, params: Optional[dict] = None, timeout: int = 20) -> bytes:
    """Perform a GET request and return raw bytes."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=True)

    if HAS_REQUESTS:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    else:
        req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()


def _get_html(url: str, params: Optional[dict] = None, timeout: int = 20) -> str:
    """Perform a GET request and return HTML text."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=True)

    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    if HAS_REQUESTS:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8")


# ─────────────────────────────────────────────
# Signature Scraping
# ─────────────────────────────────────────────

def _scrape_signed_url(page_path: str, url_fragment: str) -> Optional[str]:
    """
    Scrape a pre-signed meteogram URL from a Meteoblue HTML page.

    The meteogram image APIs use server-side HMAC signatures that are
    time-limited. Since the secret is not exposed client-side, the only
    way to get valid signatures is to extract them from server-rendered
    HTML pages.

    Args:
        page_path: Path to Meteoblue page (e.g. '/en/weather/forecast/meteogramweb/...')
        url_fragment: Fragment to match in the URL (e.g. 'meteogram_multimodel')

    Returns:
        Full https URL with valid sig, or None if not found
    """
    full_url = BASE_URL + page_path
    html = _get_html(full_url)

    # Try to find data-href (unescaped) or ampersand-escaped versions
    patterns = [
        r'data-href="(//my\.meteoblue\.com/images/' + re.escape(url_fragment) + r'[^"]+)"',
        r'data-url="(//my\.meteoblue\.com/images/' + re.escape(url_fragment) + r'[^"]+)"',
    ]
    for pat in patterns:
        match = re.search(pat, html)
        if match:
            url = match.group(1).replace("&amp;", "&")
            return "https:" + url

    return None


# ─────────────────────────────────────────────
# Location Search API
# ─────────────────────────────────────────────

class LocationSearch:
    """
    Meteoblue Location Search API.

    Base URL: https://locationsearch.meteoblue.com/
    Endpoint: /en/server/search/query3
    Auth: apikey=LYnNIfRrK2XWTtzw (public)

    Returns location data with GeoNames IDs, coordinates, population, etc.
    """

    BASE = LOCATION_SEARCH_URL
    ENDPOINT = "/en/server/search/query3"
    API_KEY = LOCATION_SEARCH_APIKEY

    def search(
        self,
        query: str,
        page: int = 1,
        items_per_page: int = 10,
        lang: str = "en",
        order_by: Optional[str] = None,
    ) -> dict:
        """
        Search for locations by name, coordinates, or IATA/ICAO code.

        Args:
            query: Search query (city name, lat/lon like "47.56 7.59", IATA code)
            page: Result page number (1-based)
            items_per_page: Number of results per page (max 50)
            lang: Language code (en, de, fr, es, etc.)
            order_by: Sort order (e.g. "name ASC", "distance DESC")

        Returns:
            dict with keys: query, count, currentPage, pages, results, lat, lon, type
            Each result has: id, name, iso2, lat, lon, asl, admin1, country,
                             featureClass, featureCode, population, iata, icao,
                             url, distance, postcodes

        Example:
            >>> ls = LocationSearch()
            >>> data = ls.search("london")
            >>> print(data["results"][0]["name"])  # London
            >>> print(data["results"][0]["id"])    # 2643743
        """
        params = {
            "query": query,
            "page": page,
            "itemsPerPage": items_per_page,
            "apikey": self.API_KEY,
        }
        if order_by:
            params["orderBy"] = order_by

        url = self.BASE + f"/{lang}" + self.ENDPOINT
        return _get(url, params)

    def search_nearby(
        self,
        lat: float,
        lon: float,
        page: int = 1,
        items_per_page: int = 10,
        lang: str = "en",
    ) -> dict:
        """
        Search for locations near a coordinate.

        Args:
            lat: Latitude
            lon: Longitude
            page: Result page
            items_per_page: Results per page

        Returns:
            Same structure as search(), results sorted by distance
        """
        query = f"{lat:.3f} {lon:.3f}"
        return self.search(query, page=page, items_per_page=items_per_page, lang=lang)

    def get_by_id(self, location_id: int, lang: str = "en") -> Optional[dict]:
        """
        Get location data by GeoNames ID.

        Args:
            location_id: GeoNames location ID (e.g. 2643743 for London)

        Returns:
            Location dict or None if not found
        """
        # Use the ID directly as a search query
        results = self.search(str(location_id), lang=lang)
        for r in results.get("results", []):
            if r.get("id") == location_id:
                return r
        return None

    def build_location_slug(self, result: dict) -> str:
        """
        Build the Meteoblue URL slug from a location search result.

        Args:
            result: Location dict from search()

        Returns:
            URL slug like "london_united-kingdom_2643743"
        """
        return result.get("url", "")


# ─────────────────────────────────────────────
# Forecast Pages (HTML-scraped data endpoints)
# ─────────────────────────────────────────────

class ForecastScraper:
    """
    Scrapes forecast data URLs from Meteoblue HTML pages.

    Since main forecast data is server-rendered, this class provides
    methods to extract pre-signed API URLs from the HTML pages.

    Location slug format: {city}_{country}_{geonames_id}
    Example: "london_united-kingdom_2643743"
    """

    def _make_location_path(self, location_slug: str, lang: str = "en") -> str:
        return f"/{lang}/weather"

    def get_week_forecast_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for 7-day week forecast page."""
        return f"{BASE_URL}/{lang}/weather/week/{location_slug}"

    def get_14day_forecast_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for 14-day forecast page."""
        return f"{BASE_URL}/{lang}/weather/10-days/{location_slug}"

    def get_today_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for today's hourly weather page."""
        return f"{BASE_URL}/{lang}/weather/today/{location_slug}"

    def get_multimodel_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for multimodel comparison page."""
        return f"{BASE_URL}/{lang}/weather/forecast/multimodel/{location_slug}"

    def get_meteogram_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for meteogram page."""
        return f"{BASE_URL}/{lang}/weather/forecast/meteogramweb/{location_slug}"

    def get_air_quality_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for air quality and pollen page."""
        return f"{BASE_URL}/{lang}/weather/outdoorsports/airquality/{location_slug}"

    def get_astronomy_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for astronomy seeing conditions page."""
        return f"{BASE_URL}/{lang}/weather/outdoorsports/seeing/{location_slug}"

    def get_agriculture_url(self, location_slug: str, page_type: str = "meteogramagro", lang: str = "en") -> str:
        """
        Get URL for agriculture forecast page.

        Args:
            page_type: One of: meteogramagro, sowing, spraying, soiltrafficability
        """
        return f"{BASE_URL}/{lang}/weather/agriculture/{page_type}/{location_slug}"

    def get_aviation_url(self, location_slug: str, page_type: str = "air", lang: str = "en") -> str:
        """
        Get URL for aviation forecast page.

        Args:
            page_type: One of: air, thermal, trajectories, crosssection, stuve
        """
        return f"{BASE_URL}/{lang}/weather/aviation/{page_type}/{location_slug}"

    def get_warnings_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for weather warnings page."""
        return f"{BASE_URL}/{lang}/weather/warnings/index/{location_slug}"

    def get_climate_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for climate (modelled) page."""
        return f"{BASE_URL}/{lang}/weather/historyclimate/climatemodelled/{location_slug}"

    def get_weather_archive_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for weather archive page."""
        return f"{BASE_URL}/{lang}/weather/historyclimate/weatherarchive/{location_slug}"

    def get_seasonal_outlook_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for seasonal outlook page."""
        return f"{BASE_URL}/{lang}/weather/forecast/seasonaloutlook/{location_slug}"

    def get_maps_url(self, location_slug: str, lang: str = "en") -> str:
        """Get URL for weather maps page."""
        return f"{BASE_URL}/{lang}/weather/maps/{location_slug}"


# ─────────────────────────────────────────────
# Meteogram Image API
# ─────────────────────────────────────────────

class MeteogramAPI:
    """
    Meteoblue Meteogram Image API.

    Base URL: https://my.meteoblue.com/images/
    Auth: apikey=n4UGDLso3gE6m2YI + server-generated sig (HMAC-MD5)

    The sig parameter is an MD5 hash of the URL + a server-side secret.
    Since the secret is not publicly exposed, valid signatures must be
    scraped from server-rendered HTML pages (which this class does automatically).

    Available endpoints:
      /images/meteogram           - Standard 5-day meteogram
      /images/meteogram_multimodel - Multi-model comparison
      /images/meteogram_agro      - Agriculture meteogram
      /images/meteogram_air       - Aviation AIR meteogram
      /images/meteogram_snow      - Snow conditions meteogram
      /images/meteogram_sea_7day  - Sea & surf 7-day meteogram

    Output formats:
      - highcharts: Returns JSON data for Highcharts visualization
      - png: Returns PNG image bytes
    """

    API_KEY = METEOGRAM_APIKEY

    def _get_fresh_sig(self, page_path: str, endpoint_fragment: str) -> Optional[str]:
        """Scrape a fresh signed URL from a Meteoblue page."""
        return _scrape_signed_url(page_path, endpoint_fragment)

    def _build_base_params(
        self,
        lat: float,
        lon: float,
        asl: int,
        tz: str,
        iso2: str,
        location_name: str,
        temperature_units: str = "C",
        windspeed_units: str = "km/h",
        precipitation_units: str = "mm",
        darkmode: bool = False,
        lang: str = "en",
        fmt: str = "highcharts",
        dpi: int = 72,
    ) -> dict:
        return {
            "temperature_units": temperature_units,
            "windspeed_units": windspeed_units,
            "precipitation_units": precipitation_units,
            "darkmode": str(darkmode).lower(),
            "iso2": iso2.lower(),
            "lat": lat,
            "lon": lon,
            "asl": asl,
            "tz": tz,
            "dpi": dpi,
            "apikey": self.API_KEY,
            "lang": lang,
            "location_name": location_name,
            "format": fmt,
        }

    def get_meteogram_from_page(
        self,
        location_slug: str,
        meteogram_type: str = "standard",
        fmt: str = "highcharts",
        lang: str = "en",
    ) -> Optional[Union[dict, bytes]]:
        """
        Fetch meteogram data by scraping the pre-signed URL from the HTML page.

        This is the recommended method as it handles signature generation
        transparently by extracting fresh signed URLs from server-rendered pages.

        Args:
            location_slug: Location URL slug (e.g. "london_united-kingdom_2643743")
            meteogram_type: One of: standard, multimodel, agro, air, snow, sea_7day
            fmt: Output format - "highcharts" (JSON) or "png" (bytes)
            lang: Language code

        Returns:
            dict for highcharts format, bytes for png format, None on failure

        Example:
            >>> api = MeteogramAPI()
            >>> data = api.get_meteogram_from_page(
            ...     "london_united-kingdom_2643743",
            ...     meteogram_type="standard",
            ...     fmt="highcharts"
            ... )
            >>> print(data["title"]["text"])  # London
        """
        page_map = {
            "standard":   f"/{lang}/weather/forecast/meteogramweb/{location_slug}",
            "multimodel": f"/{lang}/weather/forecast/multimodel/{location_slug}",
            "agro":       f"/{lang}/weather/agriculture/meteogramagro/{location_slug}",
            "air":        f"/{lang}/weather/aviation/air/{location_slug}",
            "snow":       f"/{lang}/weather/outdoorsports/snow/{location_slug}",
            "sea_7day":   f"/{lang}/weather/outdoorsports/seasurf/{location_slug}",
        }
        endpoint_fragment_map = {
            "standard":   "meteogram?",
            "multimodel": "meteogram_multimodel",
            "agro":       "meteogram_agro",
            "air":        "meteogram_air",
            "snow":       "meteogram_snow",
            "sea_7day":   "meteogram_sea_7day",
        }

        if meteogram_type not in page_map:
            raise ValueError(f"Unknown meteogram_type: {meteogram_type}. "
                             f"Choose from: {list(page_map.keys())}")

        page_path = page_map[meteogram_type]
        endpoint_fragment = endpoint_fragment_map[meteogram_type]

        signed_url = self._get_fresh_sig(page_path, endpoint_fragment)
        if not signed_url:
            return None

        # Adjust format if needed
        if "format=" in signed_url:
            signed_url = re.sub(r"format=[^&]+", f"format={fmt}", signed_url)

        if fmt == "highcharts":
            return _get(signed_url)
        else:
            return _get_raw(signed_url)

    def get_multimodel_data(
        self,
        location_slug: str,
        domains: Optional[list] = None,
        forecast_days: int = 3,
        lang: str = "en",
    ) -> Optional[dict]:
        """
        Fetch multimodel comparison data as Highcharts JSON.

        Args:
            location_slug: Location URL slug
            domains: List of weather models (None = all available)
            forecast_days: Number of forecast days (3, 5, or 7)
            lang: Language code

        Returns:
            Highcharts-formatted dict with series data for each model

        Example:
            >>> api = MeteogramAPI()
            >>> data = api.get_multimodel_data(
            ...     "london_united-kingdom_2643743",
            ...     domains=["IFS025", "GFS05", "ICON"],
            ...     forecast_days=5
            ... )
        """
        return self.get_meteogram_from_page(
            location_slug, "multimodel", fmt="highcharts", lang=lang
        )


# ─────────────────────────────────────────────
# Dataset Query API (Historical + Forecast Data)
# ─────────────────────────────────────────────

class DatasetAPI:
    """
    Meteoblue Dataset Query API.

    Base URL: https://my.meteoblue.com/dataset/query
    Auth: apikey=5838a18e295d + server-generated sig (scraped from archive page)

    This powerful API supports:
    - Historical data queries (ERA5T reanalysis since 1940)
    - Custom time intervals
    - Multiple weather variables (codes)
    - Multiple locations in one request
    - Output formats: highcharts, CSV, XLSX, JSON

    The sig parameter must be scraped from the archive page or obtained
    via the Meteoblue commercial API.

    Variable codes (from archive/export page):
      11  - Temperature [2 m elevation corrected]
      12  - Dew point [2 m]
      13  - Apparent temperature [2 m]
      52  - Relative humidity [2 m]
      61  - Precipitation amount
      71  - Snowfall amount
      72  - Snowdepth
      201 - Wind speed [10 m]
      202 - Wind direction [10 m]
      203 - Wind gusts [10 m]
      111 - Total cloud cover
      117 - Low cloud cover
      118 - Mid cloud cover
      119 - High cloud cover
      401 - Solar radiation
      402 - Direct radiation
      403 - Diffuse radiation
      118 - CAPE
      120 - Pressure [mean sea level]
      500 - Evapotranspiration
      501 - Potential evapotranspiration

    Temporal resolutions:
      "hourly", "daily", "monthly", "yearly"

    Domains:
      "ERA5T" - ERA5T reanalysis (recommended for historical, since 1940)
      "IFS025" - ECMWF IFS (forecast)
      "GFS05"  - NOAA GFS (forecast)
      + all others in AVAILABLE_DOMAINS
    """

    BASE = MY_URL
    ENDPOINT = "/dataset/query"
    API_KEY = DATASET_APIKEY

    def _get_signed_url_from_archive(self) -> Optional[str]:
        """Scrape a fresh signed dataset URL from the archive/export page."""
        html = _get_html(f"{BASE_URL}/en/weather/archive/export")
        match = re.search(
            r'data-url="(//my\.meteoblue\.com/dataset/query\?[^"]+)"',
            html
        )
        if match:
            url = match.group(1).replace("&amp;", "&")
            return "https:" + url
        return None

    def _parse_signed_params(self, signed_url: str) -> tuple:
        """Extract ts and sig from a signed URL."""
        parsed = urllib.parse.urlparse(signed_url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        return params.get("ts", ""), params.get("sig", "")

    def query(
        self,
        lat: float,
        lon: float,
        asl: int,
        location_name: str,
        start_date: str,
        end_date: str,
        domain: str = "ERA5T",
        codes: Optional[list] = None,
        time_resolution: str = "hourly",
        fmt: str = "highcharts",
        temperature_unit: str = "CELSIUS",
        velocity_unit: str = "KILOMETER_PER_HOUR",
        length_unit: str = "metric",
        energy_unit: str = "watts",
    ) -> Optional[dict]:
        """
        Query historical weather data using the dataset API.

        This method scrapes the necessary signature from the archive page,
        then uses it to construct and execute an API query.

        Args:
            lat: Location latitude
            lon: Location longitude
            asl: Altitude above sea level in meters
            location_name: Human-readable location name
            start_date: Start date in "YYYY-MM-DD" format
            end_date: End date in "YYYY-MM-DD" format
            domain: Weather model/reanalysis (default: ERA5T for historical)
            codes: List of variable code dicts, each with "code" and "level" keys
                   Default: temperature at 2m
            time_resolution: "hourly", "daily", "monthly", or "yearly"
            fmt: "highcharts" (JSON), "csv", or "xlsx"
            temperature_unit: "CELSIUS" or "FAHRENHEIT"
            velocity_unit: "KILOMETER_PER_HOUR", "METER_PER_SECOND", or "MILES_PER_HOUR"
            length_unit: "metric" or "imperial"
            energy_unit: "watts" or "langley"

        Returns:
            Highcharts JSON dict, or None on failure

        Example:
            >>> api = DatasetAPI()
            >>> data = api.query(
            ...     lat=47.5584, lon=7.57327, asl=279,
            ...     location_name="Basel",
            ...     start_date="2024-01-01",
            ...     end_date="2024-03-31",
            ...     codes=[{"code": 11, "level": "2 m elevation corrected"},
            ...             {"code": 61, "level": "sfc"}],
            ...     time_resolution="daily"
            ... )
        """
        if codes is None:
            codes = [{"code": 11, "level": "2 m elevation corrected"}]

        # Get a fresh sig from the archive page
        signed_url = self._get_signed_url_from_archive()
        if not signed_url:
            raise RuntimeError("Could not scrape signed URL from archive page")

        ts, sig = self._parse_signed_params(signed_url)

        # Build the query JSON
        query_data = {
            "units": {
                "temperature": temperature_unit,
                "velocity": velocity_unit,
                "length": length_unit,
                "energy": energy_unit,
            },
            "geometry": {
                "type": "MultiPoint",
                "coordinates": [[lon, lat, asl]],
                "locationNames": [location_name],
            },
            "format": fmt,
            "timeIntervals": [f"{start_date}T+00:00/{end_date}T+00:00"],
            "timeIntervalsAlignment": "none",
            "queries": [
                {
                    "domain": domain,
                    "timeResolution": time_resolution,
                    "codes": codes,
                }
            ],
        }

        params = {
            "json": json.dumps(query_data),
            "apikey": self.API_KEY,
            "ts": ts,
            "sig": sig,
        }

        url = self.BASE + self.ENDPOINT
        return _get(url, params)

    def query_multi_location(
        self,
        locations: list,
        start_date: str,
        end_date: str,
        domain: str = "ERA5T",
        codes: Optional[list] = None,
        time_resolution: str = "daily",
        fmt: str = "highcharts",
    ) -> Optional[dict]:
        """
        Query historical weather data for multiple locations simultaneously.

        Args:
            locations: List of dicts with keys: lat, lon, asl, name
            start_date: Start date "YYYY-MM-DD"
            end_date: End date "YYYY-MM-DD"
            domain: Weather model domain
            codes: Variable codes
            time_resolution: Time resolution
            fmt: Output format

        Returns:
            API response with data for all locations

        Example:
            >>> api = DatasetAPI()
            >>> data = api.query_multi_location(
            ...     locations=[
            ...         {"lat": 47.5584, "lon": 7.57327, "asl": 279, "name": "Basel"},
            ...         {"lat": 51.5085, "lon": -0.12574, "asl": 11, "name": "London"},
            ...     ],
            ...     start_date="2024-06-01",
            ...     end_date="2024-06-30",
            ... )
        """
        if codes is None:
            codes = [{"code": 11, "level": "2 m elevation corrected"}]

        signed_url = self._get_signed_url_from_archive()
        if not signed_url:
            raise RuntimeError("Could not scrape signed URL from archive page")

        ts, sig = self._parse_signed_params(signed_url)

        coordinates = [[loc["lon"], loc["lat"], loc["asl"]] for loc in locations]
        location_names = [loc["name"] for loc in locations]

        query_data = {
            "units": {
                "temperature": "CELSIUS",
                "velocity": "KILOMETER_PER_HOUR",
                "length": "metric",
                "energy": "watts",
            },
            "geometry": {
                "type": "MultiPoint",
                "coordinates": coordinates,
                "locationNames": location_names,
            },
            "format": fmt,
            "timeIntervals": [f"{start_date}T+00:00/{end_date}T+00:00"],
            "timeIntervalsAlignment": "none",
            "queries": [
                {
                    "domain": domain,
                    "timeResolution": time_resolution,
                    "codes": codes,
                }
            ],
        }

        params = {
            "json": json.dumps(query_data),
            "apikey": self.API_KEY,
            "ts": ts,
            "sig": sig,
        }

        url = self.BASE + self.ENDPOINT
        return _get(url, params)


# ─────────────────────────────────────────────
# Maps API
# ─────────────────────────────────────────────

class MapsAPI:
    """
    Meteoblue Maps Inventory and Tile APIs.

    Base URL: https://maps-api.meteoblue.com
    Tiles URL: https://maptiles.meteoblue.com

    Provides weather map inventory data including available overlays,
    categories, color tables, and tile URL templates.

    Tile URL patterns:
      Terrain: https://maptiles.meteoblue.com/styles/terrain2/{z}/{x}/{y}.png?apikey=...
      City:    https://maptiles.meteoblue.com/data/precalculatedCityTiles2/{z}/{x}/{y}.png?apikey=...
      Hillshade: https://maptiles.meteoblue.com/data/hillshades/{z}/{x}/{y}.png?apikey=...

    For weather tiles (forecast/radar/satellite), the inventory endpoint
    returns Mapbox GL style URLs with placeholders like {timestamp}, {domain},
    {level} that get filled in dynamically.
    """

    BASE = MAPS_API_URL
    TILES_BASE = MAPTILES_URL
    # Internal API key for public access
    CDN_KEY = MAPS_CDN_APIKEY

    def get_inventory(
        self,
        maps: Optional[list] = None,
        lang: str = "en",
        temperature_unit: str = "°C",
        length_unit: str = "metric",
        internal: bool = True,
    ) -> dict:
        """
        Get the maps inventory showing available map overlays and categories.

        Args:
            maps: List of specific map IDs to filter (None = all)
                  Examples: ["satellite", "obsTemperature", "obsPrecipitation", "radar"]
            lang: Language code
            temperature_unit: "°C" or "°F"
            length_unit: "metric" or "imperial"
            internal: Include internal/restricted maps (True for website use)

        Returns:
            dict with keys: colorTables, units, attribution, overlays, categories
            - categories: list of map categories with available map layers
            - overlays: list of available overlays (domain boundaries, wind animation, etc.)

        Example:
            >>> api = MapsAPI()
            >>> inventory = api.get_inventory(maps=["satellite", "radar"])
            >>> for cat in inventory["categories"]:
            ...     for m in cat["maps"]:
            ...         print(m["id"], "-", m["name"])
        """
        params = {
            "lang": lang,
            "temperatureUnit": temperature_unit,
            "lengthUnit": length_unit,
        }
        if internal:
            params["internal"] = "true"
            params["enableOpenlayersLicensing"] = "true"
        if maps:
            params["maps"] = ",".join(maps)

        url = self.BASE + "/v1/map/inventory/filter"
        return _get(url, params)

    def get_full_inventory(self, lang: str = "en") -> dict:
        """
        Get the full maps inventory for the weather maps page.

        Returns all available weather overlays including forecast maps,
        radar, satellite, observations, and more.
        """
        return self.get_inventory(
            maps=[
                "satellite", "obsTemperature", "obsPrecipitation",
                "radar", "temperature", "precipitation", "wind",
                "clouds", "pressure", "snowdepth", "uvindex",
            ],
            lang=lang,
            internal=True,
        )

    def get_terrain_tile_url(self) -> str:
        """Get the terrain tile URL template for use with mapping libraries."""
        return f"{self.TILES_BASE}/styles/terrain2/{{z}}/{{x}}/{{y}}.png?apikey={self.CDN_KEY}"

    def get_city_tile_url(self) -> str:
        """Get the city overlay tile URL template."""
        return f"{self.TILES_BASE}/data/precalculatedCityTiles2/{{z}}/{{x}}/{{y}}.png?apikey={self.CDN_KEY}"

    def get_hillshade_tile_url(self) -> str:
        """Get the hillshade tile URL template."""
        return f"{self.TILES_BASE}/data/hillshades/{{z}}/{{x}}/{{y}}.png?apikey={self.CDN_KEY}"

    def get_mapbox_style_url(
        self,
        style: str = "mb-locationsearch.json",
        lang: str = "en",
        darkmode: bool = False,
    ) -> str:
        """
        Get Mapbox GL style URL for location search maps.

        Args:
            style: Style name - "mb-locationsearch.json" or "mb-locationsearch-dark.json"
            lang: Language code

        Returns:
            Full URL for use with mapboxgl.Map({style: ...})
        """
        if darkmode:
            style = "mb-locationsearch-dark.json"
        else:
            style = "mb-locationsearch.json"

        return (
            f"https://maps-api-cdn.meteoblue.com/v1/json/{style}"
            f"?apikey={self.CDN_KEY}&lang={lang}&internal=true"
        )


# ─────────────────────────────────────────────
# Convenience Wrapper
# ─────────────────────────────────────────────

class MeteoblueClient:
    """
    High-level Meteoblue API client combining all sub-APIs.

    Usage:
        client = MeteoblueClient()

        # Search for a location
        loc = client.search_location("Basel")
        slug = loc["results"][0]["url"]

        # Get 7-day forecast (scrapes from web page)
        forecast_url = client.get_forecast_url(slug)

        # Get meteogram data as Highcharts JSON
        data = client.get_meteogram(slug)

        # Get historical weather data
        history = client.get_historical(
            lat=47.5584, lon=7.57327, asl=279,
            name="Basel",
            start="2024-01-01", end="2024-03-31"
        )
    """

    def __init__(self):
        self.location = LocationSearch()
        self.meteogram = MeteogramAPI()
        self.dataset = DatasetAPI()
        self.maps = MapsAPI()
        self.forecast = ForecastScraper()

    def search_location(
        self,
        query: str,
        lang: str = "en",
        max_results: int = 10,
    ) -> dict:
        """Search for locations by name or coordinates."""
        return self.location.search(query, lang=lang, items_per_page=max_results)

    def get_forecast_url(self, location_slug: str, days: int = 7, lang: str = "en") -> str:
        """Get the URL for a forecast page (7-day or 14-day)."""
        if days <= 7:
            return self.forecast.get_week_forecast_url(location_slug, lang)
        else:
            return self.forecast.get_14day_forecast_url(location_slug, lang)

    def get_meteogram(
        self,
        location_slug: str,
        meteogram_type: str = "standard",
        fmt: str = "highcharts",
        lang: str = "en",
    ) -> Optional[Union[dict, bytes]]:
        """
        Get meteogram data by scraping the pre-signed URL from Meteoblue pages.

        Args:
            location_slug: Location slug from search (e.g. "london_united-kingdom_2643743")
            meteogram_type: standard|multimodel|agro|air|snow|sea_7day
            fmt: highcharts|png
            lang: Language code

        Returns:
            Highcharts JSON dict or PNG bytes
        """
        return self.meteogram.get_meteogram_from_page(
            location_slug, meteogram_type, fmt, lang
        )

    def get_multimodel(
        self,
        location_slug: str,
        domains: Optional[list] = None,
        lang: str = "en",
    ) -> Optional[dict]:
        """Get multi-model weather comparison data."""
        return self.meteogram.get_multimodel_data(location_slug, domains, lang=lang)

    def get_historical(
        self,
        lat: float,
        lon: float,
        asl: int,
        name: str,
        start: str,
        end: str,
        variables: Optional[list] = None,
        resolution: str = "daily",
        domain: str = "ERA5T",
    ) -> Optional[dict]:
        """
        Get historical weather data.

        Args:
            lat, lon: Coordinates
            asl: Altitude above sea level (meters)
            name: Location name
            start, end: Date strings "YYYY-MM-DD"
            variables: List of {"code": int, "level": str} dicts
                       Default: temperature 2m
            resolution: "hourly", "daily", "monthly"
            domain: "ERA5T" for historical reanalysis

        Returns:
            Highcharts JSON with time series data

        Example:
            >>> client = MeteoblueClient()
            >>> data = client.get_historical(
            ...     lat=51.5085, lon=-0.12574, asl=11,
            ...     name="London",
            ...     start="2023-01-01", end="2023-12-31",
            ...     variables=[
            ...         {"code": 11, "level": "2 m elevation corrected"},
            ...         {"code": 61, "level": "sfc"},  # precipitation
            ...     ],
            ...     resolution="daily"
            ... )
        """
        return self.dataset.query(
            lat=lat, lon=lon, asl=asl, location_name=name,
            start_date=start, end_date=end,
            codes=variables, time_resolution=resolution, domain=domain,
        )

    def get_maps_inventory(
        self,
        maps: Optional[list] = None,
        lang: str = "en",
    ) -> dict:
        """Get the available weather map overlays inventory."""
        return self.maps.get_inventory(maps=maps, lang=lang)


# ─────────────────────────────────────────────
# CLI / Demo
# ─────────────────────────────────────────────

def demo():
    """Run a demonstration of the Meteoblue API client."""
    print("=" * 60)
    print("Meteoblue Internal API Client - Demo")
    print("=" * 60)

    client = MeteoblueClient()

    # 1. Location Search
    print("\n[1] Searching for 'London'...")
    results = client.search_location("London", max_results=3)
    print(f"    Found {results.get('count', 0)} locations")
    for r in results.get("results", [])[:3]:
        print(f"    - {r['name']}, {r.get('admin1', '')}, {r.get('iso2', '')} "
              f"[id={r['id']}] [{r['lat']:.3f}, {r['lon']:.3f}]")

    # Get London slug
    london_slug = results["results"][0]["url"] if results.get("results") else "london_united-kingdom_2643743"
    print(f"\n    London slug: {london_slug}")

    # 2. Forecast URLs
    print("\n[2] Forecast page URLs:")
    print(f"    7-day:    {client.forecast.get_week_forecast_url(london_slug)}")
    print(f"    Today:    {client.forecast.get_today_url(london_slug)}")
    print(f"    Maps:     {client.forecast.get_maps_url(london_slug)}")
    print(f"    MultiMdl: {client.forecast.get_multimodel_url(london_slug)}")

    # 3. Maps inventory
    print("\n[3] Fetching maps inventory...")
    try:
        inventory = client.get_maps_inventory(maps=["satellite", "obsPrecipitation"])
        cats = inventory.get("categories", [])
        print(f"    Available map categories: {len(cats)}")
        for cat in cats:
            for m in cat.get("maps", []):
                print(f"    - [{m.get('id')}] {m.get('name')}")
    except Exception as e:
        print(f"    Error: {e}")

    # 4. Meteogram (requires scraping from page)
    print("\n[4] Fetching standard meteogram for London...")
    print("    (This scrapes a pre-signed URL from the Meteoblue website)")
    try:
        data = client.get_meteogram(london_slug, "standard", "highcharts")
        if data:
            title = data.get("title", {}).get("text", "N/A")
            subtitle = data.get("subtitle", {}).get("text", "")
            credits = data.get("credits", {}).get("text", "")
            print(f"    Title: {title}")
            print(f"    Subtitle: {subtitle}")
            print(f"    {credits}")
        else:
            print("    No data returned (signature scraping may have failed)")
    except Exception as e:
        print(f"    Error: {e}")

    # 5. Historical data (requires scraping sig from archive page)
    print("\n[5] Fetching historical weather data for Basel...")
    print("    (This scrapes a pre-signed sig from the archive export page)")
    try:
        history = client.get_historical(
            lat=47.5584, lon=7.57327, asl=279, name="Basel",
            start="2024-01-01", end="2024-01-07",
            variables=[{"code": 11, "level": "2 m elevation corrected"}],
            resolution="daily",
        )
        if history:
            series = history.get("series", [])
            print(f"    Got {len(series)} data series")
            if series:
                s = series[0]
                print(f"    Series name: {s.get('name', 'N/A')}")
                data_pts = s.get("data", [])
                print(f"    Data points: {len(data_pts)}")
        else:
            print("    No historical data returned")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    demo()
