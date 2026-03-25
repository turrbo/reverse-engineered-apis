"""
weather_gov_client.py
---------------------
Python client for the National Weather Service (NWS) API at api.weather.gov.

The NWS API is a FREE, PUBLIC government API that requires no authentication.
A User-Agent header identifying your application is required per NWS policy.

API Base: https://api.weather.gov
API Docs: https://www.weather.gov/documentation/services-web-api
OpenAPI:  https://api.weather.gov/openapi.json

Key workflow:
    1. Call get_point(lat, lon)  -> returns gridId, gridX, gridY, and URLs
    2. Call get_forecast(wfo, x, y) or use the convenience methods
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://api.weather.gov"
DEFAULT_USER_AGENT = (
    "NWSPythonClient/1.0 (github.com/example/nws-client; contact@example.com)"
)

# Valid NWS marine region codes
MARINE_REGIONS = ["AL", "AT", "GL", "GM", "PA", "PI"]

# Valid NWS alert region codes
ALERT_REGIONS = ["AL", "AT", "GL", "GM", "PA", "PI"]

# Valid satellite thumbnail area codes
SATELLITE_AREAS = ["us", "alaska", "hawaii", "pr", "guam"]

# Zone type codes
ZONE_TYPES = ["land", "marine", "forecast", "public", "coastal", "offshore", "fire", "county"]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class NWSClientError(Exception):
    """Base exception for NWS client errors."""


class NWSNotFoundError(NWSClientError):
    """Raised when a resource is not found (404)."""


class NWSRateLimitError(NWSClientError):
    """Raised when rate limited by the NWS API (429)."""


class NWSServerError(NWSClientError):
    """Raised on NWS server-side errors (5xx)."""


# ---------------------------------------------------------------------------
# Core Client
# ---------------------------------------------------------------------------
class NWSClient:
    """
    Python client for the National Weather Service (NWS) REST API.

    All endpoints are public and require no authentication token.
    A descriptive User-Agent string is required and appreciated by the NWS.

    Args:
        user_agent: Required. Identifies your app to the NWS.
                    Format: "AppName/Version (contact@email.com)"
        timeout:    Request timeout in seconds. Default is 30.
        retries:    Number of retry attempts on transient failures. Default is 3.

    Example:
        client = NWSClient(user_agent="MyWeatherApp/1.0 (dev@example.com)")
        point = client.get_point(40.7128, -74.0060)
        forecast = client.get_forecast_by_location(40.7128, -74.0060)
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: int = 30,
        retries: int = 3,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/geo+json",
                "Feature-Flags": "",
            }
        )
        self.timeout = timeout
        self.retries = retries
        self._point_cache: Dict[Tuple[float, float], Dict] = {}

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------
    def _get(self, url: str, params: Optional[Dict] = None) -> Any:
        """Make a GET request with retry logic and error handling."""
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as exc:
                if attempt == self.retries - 1:
                    raise NWSClientError(f"Network error: {exc}") from exc
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                raise NWSNotFoundError(
                    f"Resource not found: {url}\n{resp.text[:500]}"
                )
            elif resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                time.sleep(wait)
                continue
            elif resp.status_code >= 500:
                if attempt == self.retries - 1:
                    raise NWSServerError(
                        f"NWS server error {resp.status_code}: {resp.text[:500]}"
                    )
                time.sleep(2 ** attempt)
                continue
            else:
                raise NWSClientError(
                    f"HTTP {resp.status_code} from {url}: {resp.text[:500]}"
                )
        raise NWSClientError(f"Failed after {self.retries} attempts: {url}")

    def _build_url(self, path: str) -> str:
        return f"{BASE_URL}{path}"

    # -----------------------------------------------------------------------
    # Points (Lat/Lon -> Grid)
    # -----------------------------------------------------------------------
    def get_point(self, lat: float, lon: float) -> Dict:
        """
        Resolve a latitude/longitude to an NWS grid point.

        This is the first step in the two-step forecast lookup.
        Returns grid information including the Forecast Office (WFO),
        grid coordinates, and URLs for forecasts and observation stations.

        Args:
            lat: Latitude (decimal degrees, e.g. 40.7128)
            lon: Longitude (decimal degrees, e.g. -74.0060)

        Returns:
            dict with keys:
                - gridId (str): WFO office code, e.g. "OKX"
                - gridX (int): Grid X coordinate
                - gridY (int): Grid Y coordinate
                - forecast (str): URL for daily forecast
                - forecastHourly (str): URL for hourly forecast
                - forecastGridData (str): URL for raw grid data
                - observationStations (str): URL for nearby stations
                - timeZone (str): IANA timezone name
                - radarStation (str): Nearest radar station ID
                - relativeLocation: dict with city, state, distance, bearing
                - forecastOffice (str): Full URL for the NWS office
                - county (str): County zone URL
                - publicZone (str): Public forecast zone URL
                - fireWeatherZone (str): Fire weather zone URL
        """
        cache_key = (round(lat, 4), round(lon, 4))
        if cache_key in self._point_cache:
            return self._point_cache[cache_key]

        url = self._build_url(f"/points/{lat},{lon}")
        data = self._get(url)
        props = data.get("properties", {})
        self._point_cache[cache_key] = props
        return props

    def get_point_radio(self, lat: float, lon: float) -> Dict:
        """
        Get NOAA Weather Radio broadcast information for a lat/lon point.

        Returns information about the nearest NWS weather radio station
        including call sign, frequency, and broadcast URL.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            dict with radio station properties including callSign, frequency, name
        """
        url = self._build_url(f"/points/{lat},{lon}/radio")
        return self._get(url)

    def get_point_stations(self, lat: float, lon: float) -> List[Dict]:
        """
        Get a list of observation stations near a lat/lon point.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            List of station feature dicts, each with stationIdentifier, name,
            timeZone, elevation, and coordinates.
        """
        url = self._build_url(f"/points/{lat},{lon}/stations")
        data = self._get(url)
        return data.get("features", [])

    # -----------------------------------------------------------------------
    # Forecasts
    # -----------------------------------------------------------------------
    def get_forecast(self, wfo: str, grid_x: int, grid_y: int) -> Dict:
        """
        Get the 7-day (twice-daily) forecast for a grid point.

        Each period covers 12 hours (day or night). Use get_point() first
        to obtain the wfo/grid_x/grid_y values for a lat/lon.

        Args:
            wfo:    Forecast Office code, e.g. "OKX" (New York)
            grid_x: Grid X coordinate (from get_point)
            grid_y: Grid Y coordinate (from get_point)

        Returns:
            dict with keys:
                - periods (list): List of forecast period dicts, each containing:
                    - number, name, startTime, endTime, isDaytime
                    - temperature (int), temperatureUnit ("F" or "C")
                    - windSpeed (str), windDirection (str)
                    - icon (str): URL to weather icon image
                    - shortForecast (str): e.g. "Partly Sunny"
                    - detailedForecast (str): Full text forecast
                    - probabilityOfPrecipitation (dict with value and unitCode)
                - generatedAt (str): ISO timestamp
                - updateTime (str): ISO timestamp of last model update
                - validTimes (str): ISO duration of valid forecast window
                - elevation (dict): Elevation at grid point
        """
        url = self._build_url(f"/gridpoints/{wfo}/{grid_x},{grid_y}/forecast")
        data = self._get(url)
        return data.get("properties", data)

    def get_forecast_hourly(self, wfo: str, grid_x: int, grid_y: int) -> Dict:
        """
        Get the hourly forecast for a grid point (next 7 days, 1-hour intervals).

        Each period covers 1 hour and includes dewpoint, relative humidity,
        wind speed, wind direction, temperature, precipitation probability,
        and a short text forecast.

        Args:
            wfo:    Forecast Office code, e.g. "OKX"
            grid_x: Grid X coordinate
            grid_y: Grid Y coordinate

        Returns:
            dict with same structure as get_forecast() but with hourly periods.
            Additional fields per period:
                - dewpoint (dict): Dewpoint temperature
                - relativeHumidity (dict): Relative humidity percentage
        """
        url = self._build_url(f"/gridpoints/{wfo}/{grid_x},{grid_y}/forecast/hourly")
        data = self._get(url)
        return data.get("properties", data)

    def get_grid_data(self, wfo: str, grid_x: int, grid_y: int) -> Dict:
        """
        Get raw gridded forecast data for a grid point.

        Returns detailed time-series data for many meteorological variables
        (temperature, dewpoint, wind speed/direction, precipitation, etc.)
        as ISO 8601 duration-encoded time series.

        Args:
            wfo:    Forecast Office code
            grid_x: Grid X coordinate
            grid_y: Grid Y coordinate

        Returns:
            dict with gridded values for:
                temperature, dewpoint, maxTemperature, minTemperature,
                relativeHumidity, apparentTemperature, heatIndex, windChill,
                windSpeed, windDirection, windGust, probabilityOfPrecipitation,
                quantitativePrecipitation, snowfallAmount, snowLevel,
                iceAccumulation, visibility, weather, hazards, and more.
        """
        url = self._build_url(f"/gridpoints/{wfo}/{grid_x},{grid_y}")
        return self._get(url)

    def get_grid_stations(self, wfo: str, grid_x: int, grid_y: int) -> List[Dict]:
        """
        Get observation stations near a grid point.

        Args:
            wfo:    Forecast Office code
            grid_x: Grid X coordinate
            grid_y: Grid Y coordinate

        Returns:
            List of station feature dicts.
        """
        url = self._build_url(f"/gridpoints/{wfo}/{grid_x},{grid_y}/stations")
        data = self._get(url)
        return data.get("features", [])

    # -----------------------------------------------------------------------
    # Convenience: full location-based forecast
    # -----------------------------------------------------------------------
    def get_forecast_by_location(
        self, lat: float, lon: float
    ) -> Tuple[Dict, Dict]:
        """
        Get daily and hourly forecasts for a lat/lon location.

        Automatically performs the two-step lookup:
            1. Resolve lat/lon -> NWS grid point (wfo, x, y)
            2. Fetch both daily and hourly forecasts

        Args:
            lat: Latitude in decimal degrees (e.g. 40.7128)
            lon: Longitude in decimal degrees (e.g. -74.0060)

        Returns:
            Tuple of (daily_forecast, hourly_forecast) dicts.
            Each contains a 'periods' list.

        Example:
            daily, hourly = client.get_forecast_by_location(40.7128, -74.0060)
            for period in daily['periods']:
                print(f"{period['name']}: {period['temperature']}°F - {period['shortForecast']}")
        """
        point = self.get_point(lat, lon)
        wfo = point["gridId"]
        gx = point["gridX"]
        gy = point["gridY"]
        daily = self.get_forecast(wfo, gx, gy)
        hourly = self.get_forecast_hourly(wfo, gx, gy)
        return daily, hourly

    def get_current_conditions(self, lat: float, lon: float) -> Optional[Dict]:
        """
        Get the most recent observation for the nearest station to a lat/lon.

        Finds the nearest observation station and returns its latest reading,
        including temperature, dewpoint, wind, pressure, visibility, sky cover.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            dict with observation properties, or None if no nearby station found.
            Key properties:
                - temperature (dict with value in degC and qualityControl)
                - dewpoint, windDirection, windSpeed, windGust, barometricPressure
                - visibility, relativeHumidity, textDescription
                - rawMessage (METAR string)
                - timestamp (ISO datetime)
                - station (URL), stationName
        """
        stations = self.get_point_stations(lat, lon)
        if not stations:
            return None
        station_id = stations[0]["properties"]["stationIdentifier"]
        return self.get_station_observation_latest(station_id)

    # -----------------------------------------------------------------------
    # Alerts
    # -----------------------------------------------------------------------
    def get_alerts(
        self,
        area: Optional[str] = None,
        zone: Optional[str] = None,
        point: Optional[str] = None,
        region: Optional[str] = None,
        event: Optional[str] = None,
        severity: Optional[str] = None,
        urgency: Optional[str] = None,
        certainty: Optional[str] = None,
        status: Optional[str] = None,
        message_type: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict:
        """
        Query all alerts (historical and active) with optional filters.

        For current active alerts, prefer get_active_alerts() which is more
        efficient and supports additional filtering options.

        Args:
            area:         Two-letter state/territory code (e.g. "NY", "CA")
            zone:         NWS public zone ID (e.g. "NYZ072")
            point:        "lat,lon" string (e.g. "40.7128,-74.0060")
            region:       Marine region code: AL, AT, GL, GM, PA, PI
            event:        Event type (e.g. "Tornado Warning", "Winter Storm Warning")
            severity:     Severity filter: Extreme, Severe, Moderate, Minor, Unknown
            urgency:      Urgency filter: Immediate, Expected, Future, Past, Unknown
            certainty:    Certainty filter: Observed, Likely, Possible, Unlikely, Unknown
            status:       Status filter: actual, exercise, system, test, draft
            message_type: Message type: alert, update, cancel
            start:        ISO start time for filtering (e.g. "2024-01-01T00:00:00Z")
            end:          ISO end time for filtering
            limit:        Max number of results (default NWS limit applies)
            cursor:       Pagination cursor from previous response

        Returns:
            dict with 'features' list of alert dicts and pagination 'cursor' if applicable.
            Each alert has properties: id, areaDesc, sent, effective, onset, expires,
            ends, status, messageType, category, severity, certainty, urgency,
            event, headline, description, instruction, response.
        """
        params: Dict[str, Any] = {}
        if area:
            params["area"] = area
        if zone:
            params["zone"] = zone
        if point:
            params["point"] = point
        if region:
            params["region"] = region
        if event:
            params["event"] = event
        if severity:
            params["severity"] = severity
        if urgency:
            params["urgency"] = urgency
        if certainty:
            params["certainty"] = certainty
        if status:
            params["status"] = status
        if message_type:
            params["message_type"] = message_type
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if limit:
            params["limit"] = limit
        if cursor:
            params["cursor"] = cursor
        url = self._build_url("/alerts")
        return self._get(url, params=params or None)

    def get_active_alerts(
        self,
        area: Optional[str] = None,
        zone: Optional[str] = None,
        point: Optional[str] = None,
        region: Optional[str] = None,
        event: Optional[str] = None,
        urgency: Optional[str] = None,
        severity: Optional[str] = None,
        certainty: Optional[str] = None,
        status: Optional[str] = None,
        message_type: Optional[str] = None,
    ) -> Dict:
        """
        Get currently active weather alerts with optional filters.

        Supports the same filter parameters as get_alerts() but only returns
        currently active alerts. More efficient than get_alerts(active=True).

        Args:
            area:         Two-letter US state code (e.g. "NY", "TX", "CA")
            zone:         NWS zone ID (e.g. "NYZ072", "TXC453")
            point:        "lat,lon" string
            region:       Marine region: AL (Alaska), AT (Atlantic), GL (Great Lakes),
                          GM (Gulf of Mexico), PA (Eastern Pacific), PI (Central/West Pacific)
            event:        Event name (e.g. "Tornado Warning", "Flood Watch")
            urgency:      Immediate, Expected, Future, Past, Unknown
            severity:     Extreme, Severe, Moderate, Minor, Unknown
            certainty:    Observed, Likely, Possible, Unlikely, Unknown
            status:       actual, exercise, system, test, draft
            message_type: alert, update, cancel

        Returns:
            dict with 'features' list of active alert GeoJSON features.
        """
        params: Dict[str, Any] = {}
        if area:
            params["area"] = area
        if zone:
            params["zone"] = zone
        if point:
            params["point"] = point
        if region:
            params["region"] = region
        if event:
            params["event"] = event
        if urgency:
            params["urgency"] = urgency
        if severity:
            params["severity"] = severity
        if certainty:
            params["certainty"] = certainty
        if status:
            params["status"] = status
        if message_type:
            params["message_type"] = message_type
        url = self._build_url("/alerts/active")
        return self._get(url, params=params or None)

    def get_active_alerts_count(self) -> Dict:
        """
        Get counts of currently active alerts by region, area, and type.

        Returns:
            dict with:
                - total (int): Total count of active alerts nationwide
                - land (int): Count of land-based alerts
                - marine (int): Count of marine alerts
                - regions (dict): Count per marine region
                - areas (dict): Count per state/territory
                - zones (dict): Count per NWS zone
        """
        url = self._build_url("/alerts/active/count")
        return self._get(url)

    def get_active_alerts_by_zone(self, zone_id: str) -> Dict:
        """
        Get active alerts for a specific NWS public zone or county.

        Args:
            zone_id: NWS zone ID (e.g. "NYZ072" for Manhattan, "TXC453")

        Returns:
            dict with 'features' list of active alert dicts for that zone.
        """
        url = self._build_url(f"/alerts/active/zone/{zone_id}")
        return self._get(url)

    def get_active_alerts_by_area(self, area: str) -> Dict:
        """
        Get active alerts for a US state or territory.

        Args:
            area: Two-letter state code (e.g. "NY", "CA", "TX", "AK", "HI")

        Returns:
            dict with 'features' list of active alerts for that state.
        """
        url = self._build_url(f"/alerts/active/area/{area}")
        return self._get(url)

    def get_active_alerts_by_marine_region(self, region: str) -> Dict:
        """
        Get active alerts for a marine region.

        Args:
            region: Marine region code. Valid values:
                    AL = Alaska
                    AT = Atlantic Ocean
                    GL = Great Lakes
                    GM = Gulf of Mexico
                    PA = Eastern Pacific Ocean / West Coast
                    PI = Central/Western Pacific Ocean

        Returns:
            dict with 'features' list of marine alert dicts.
        """
        url = self._build_url(f"/alerts/active/region/{region}")
        return self._get(url)

    def get_alert_types(self) -> List[str]:
        """
        Get the full list of possible alert event type names.

        Returns:
            List of strings like ["Tornado Warning", "Winter Storm Warning", ...]
        """
        url = self._build_url("/alerts/types")
        data = self._get(url)
        return data.get("eventTypes", [])

    def get_alert(self, alert_id: str) -> Dict:
        """
        Get a single alert by its CAP identifier.

        Args:
            alert_id: NWS alert ID (the full URN, e.g.
                      "urn:oid:2.49.0.1.840.0.abc123...")

        Returns:
            dict with full alert properties.
        """
        # URL-encode the ID for the path
        import urllib.parse
        encoded = urllib.parse.quote(alert_id, safe="")
        url = self._build_url(f"/alerts/{encoded}")
        return self._get(url)

    # -----------------------------------------------------------------------
    # Stations & Observations
    # -----------------------------------------------------------------------
    def get_stations(
        self,
        state: Optional[str] = None,
        station_ids: Optional[List[str]] = None,
        limit: int = 500,
        cursor: Optional[str] = None,
    ) -> Dict:
        """
        List observation stations with optional filtering.

        Args:
            state:       Two-letter state code to filter by (e.g. "NY")
            station_ids: List of specific station IDs to retrieve
            limit:       Maximum number of results (default 500)
            cursor:      Pagination cursor from previous response

        Returns:
            dict with 'features' list of station GeoJSON features.
            Each station has: stationIdentifier, name, timeZone, elevation,
            forecast (zone URL), county (zone URL), fireWeatherZone (URL).
        """
        params: Dict[str, Any] = {"limit": limit}
        if state:
            params["state"] = state
        if station_ids:
            params["stationId"] = station_ids
        if cursor:
            params["cursor"] = cursor
        url = self._build_url("/stations")
        return self._get(url, params=params)

    def get_station(self, station_id: str) -> Dict:
        """
        Get metadata for a specific observation station.

        Args:
            station_id: ICAO-style station identifier (e.g. "KNYC", "KLAX")

        Returns:
            dict with station properties including name, elevation, timeZone,
            and zone affiliations.
        """
        url = self._build_url(f"/stations/{station_id}")
        data = self._get(url)
        return data.get("properties", data)

    def get_station_observations(
        self,
        station_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict]:
        """
        Get historical observations for a station.

        Args:
            station_id: Station identifier (e.g. "KNYC")
            start:      ISO 8601 start time (e.g. "2024-01-01T00:00:00Z")
            end:        ISO 8601 end time
            limit:      Max number of observations (default 25, max 500)

        Returns:
            List of observation dicts. Each contains temperature, dewpoint,
            windSpeed, windDirection, windGust, barometricPressure,
            relativeHumidity, textDescription, rawMessage (METAR), icon, and
            presentWeather.
        """
        params: Dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        url = self._build_url(f"/stations/{station_id}/observations")
        data = self._get(url, params=params)
        return data.get("features", [])

    def get_station_observation_latest(self, station_id: str) -> Dict:
        """
        Get the most recent observation from a station.

        Args:
            station_id: Station identifier (e.g. "KNYC", "KLAX")

        Returns:
            dict with observation properties:
                - temperature (dict): value in degC, qualityControl
                - dewpoint (dict): value in degC
                - windDirection (dict): value in degrees
                - windSpeed (dict): value in km/h
                - windGust (dict): value in km/h, may be null
                - barometricPressure (dict): value in Pa
                - seaLevelPressure (dict): value in Pa
                - visibility (dict): value in m
                - maxTemperatureLast24Hours, minTemperatureLast24Hours
                - precipitationLastHour (dict): value in mm
                - precipitationLast3Hours, precipitationLast6Hours
                - relativeHumidity (dict): value in percent
                - windChill, heatIndex
                - cloudLayers (list): altitude and amount
                - textDescription (str): e.g. "Clear"
                - rawMessage (str): raw METAR observation string
                - timestamp (str): ISO datetime
                - icon (str): weather icon URL
        """
        url = self._build_url(f"/stations/{station_id}/observations/latest")
        data = self._get(url)
        return data.get("properties", data)

    def get_station_observation_at_time(
        self, station_id: str, observation_time: str
    ) -> Dict:
        """
        Get the observation closest to a specific time.

        Args:
            station_id:       Station identifier (e.g. "KNYC")
            observation_time: ISO 8601 datetime string (e.g. "2024-01-01T12:00:00Z")

        Returns:
            dict with observation properties.
        """
        url = self._build_url(
            f"/stations/{station_id}/observations/{observation_time}"
        )
        data = self._get(url)
        return data.get("properties", data)

    def get_station_tafs(
        self, station_id: str, date: Optional[str] = None, time: Optional[str] = None
    ) -> Dict:
        """
        Get Terminal Aerodrome Forecasts (TAFs) for an airport station.

        TAFs are aviation forecasts issued for major airports.

        Args:
            station_id: Airport ICAO code (e.g. "KJFK", "KLAX")
            date:       Optional date string (YYYY-MM-DD)
            time:       Optional time string (HHmm)

        Returns:
            dict with TAF data.
        """
        if date and time:
            url = self._build_url(f"/stations/{station_id}/tafs/{date}/{time}")
        else:
            url = self._build_url(f"/stations/{station_id}/tafs")
        return self._get(url)

    # -----------------------------------------------------------------------
    # Offices
    # -----------------------------------------------------------------------
    def get_office(self, office_id: str) -> Dict:
        """
        Get metadata for an NWS Weather Forecast Office (WFO).

        Args:
            office_id: NWS office code (e.g. "OKX" = New York,
                       "LOX" = Los Angeles, "CHI" = Chicago)

        Returns:
            dict with:
                - id, name, address (streetAddress, city, state, zip)
                - telephone, faxNumber, email
                - sameAs (link to office webpage)
                - nwsRegion (er, cr, wr, sr, pr, ar)
                - parentOrganization
                - responsibleCounties (list of zone URLs)
                - responsibleForecastZones (list of zone URLs)
                - responsibleFireZones (list of zone URLs)
                - approvedObservationStations (list of station URLs)
        """
        url = self._build_url(f"/offices/{office_id}")
        return self._get(url)

    def get_office_headlines(self, office_id: str) -> List[Dict]:
        """
        Get current headlines/news from an NWS office.

        Args:
            office_id: NWS office code (e.g. "OKX")

        Returns:
            List of headline dicts with id, title, summary, issuanceTime, link.
        """
        url = self._build_url(f"/offices/{office_id}/headlines")
        data = self._get(url)
        return data.get("@graph", [])

    def get_office_headline(self, office_id: str, headline_id: str) -> Dict:
        """
        Get a specific headline from an NWS office.

        Args:
            office_id:   NWS office code
            headline_id: Headline identifier

        Returns:
            dict with full headline content.
        """
        url = self._build_url(f"/offices/{office_id}/headlines/{headline_id}")
        return self._get(url)

    # -----------------------------------------------------------------------
    # Zones
    # -----------------------------------------------------------------------
    def get_zones(
        self,
        zone_type: Optional[str] = None,
        area: Optional[str] = None,
        region: Optional[str] = None,
        include_geometry: bool = False,
        limit: int = 500,
        cursor: Optional[str] = None,
    ) -> Dict:
        """
        List NWS forecast zones.

        Args:
            zone_type:        Zone type filter. One of:
                              land, marine, forecast, public, coastal,
                              offshore, fire, county
            area:             Two-letter state code (e.g. "NY")
            region:           NWS region code
            include_geometry: Include polygon geometry in response (slower)
            limit:            Max results (default 500)
            cursor:           Pagination cursor

        Returns:
            dict with 'features' list of zone GeoJSON features.
            Each zone has: id, type, name, state, effectiveDate, expirationDate,
            forecastOffice, cwa, observationStations, radarStation.
        """
        params: Dict[str, Any] = {
            "effective": "true",
            "limit": limit,
            "include_geometry": str(include_geometry).lower(),
        }
        if area:
            params["area"] = area
        if zone_type:
            params["type"] = zone_type
        if region:
            params["region"] = region
        if cursor:
            params["cursor"] = cursor
        url = self._build_url("/zones")
        return self._get(url, params=params)

    def get_zones_by_type(
        self,
        zone_type: str,
        area: Optional[str] = None,
        limit: int = 500,
    ) -> Dict:
        """
        List NWS zones filtered by type.

        Args:
            zone_type: Zone type (land, marine, forecast, public, coastal,
                       offshore, fire, county)
            area:      Two-letter state code
            limit:     Max results

        Returns:
            dict with 'features' list of zone GeoJSON features.
        """
        params: Dict[str, Any] = {"limit": limit}
        if area:
            params["area"] = area
        url = self._build_url(f"/zones/{zone_type}")
        return self._get(url, params=params)

    def get_zone(self, zone_type: str, zone_id: str) -> Dict:
        """
        Get details for a specific NWS zone.

        Args:
            zone_type: Zone type (forecast, county, fire, etc.)
            zone_id:   Zone identifier (e.g. "NYZ072", "CTC001")

        Returns:
            dict with zone properties and polygon geometry.
        """
        url = self._build_url(f"/zones/{zone_type}/{zone_id}")
        return self._get(url)

    def get_zone_forecast(self, zone_id: str) -> Dict:
        """
        Get the textual zone forecast for a public forecast zone.

        This is the zone-area-based forecast (not gridpoint-based).

        Args:
            zone_id: Public zone ID (e.g. "NYZ072")

        Returns:
            dict with zone forecast periods.
        """
        url = self._build_url(f"/zones/forecast/{zone_id}/forecast")
        return self._get(url)

    def get_zone_observations(
        self,
        zone_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict]:
        """
        Get recent observations for a forecast zone.

        Args:
            zone_id: Forecast zone ID (e.g. "NYZ072")
            start:   ISO 8601 start time
            end:     ISO 8601 end time
            limit:   Max results

        Returns:
            List of observation feature dicts.
        """
        params: Dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        url = self._build_url(f"/zones/forecast/{zone_id}/observations")
        data = self._get(url, params=params)
        return data.get("features", [])

    def get_zone_stations(self, zone_id: str) -> List[Dict]:
        """
        Get observation stations in a forecast zone.

        Args:
            zone_id: Forecast zone ID (e.g. "NYZ072")

        Returns:
            List of station feature dicts.
        """
        url = self._build_url(f"/zones/forecast/{zone_id}/stations")
        data = self._get(url)
        return data.get("features", [])

    # -----------------------------------------------------------------------
    # Radar
    # -----------------------------------------------------------------------
    def get_radar_stations(self) -> List[Dict]:
        """
        Get a list of all NWS WSR-88D radar stations in the US.

        Returns:
            List of radar station GeoJSON features. Each has:
                - id (str): Station code (e.g. "KOKX", "KLWX")
                - name (str): City name
                - stationType (str): e.g. "WSR-88D"
                - elevation (dict): Antenna elevation
                - latency (dict): Current and average data latency
                - rda (dict): RDA (Radar Data Acquisition) status
                - performance (dict): Performance metrics
        """
        url = self._build_url("/radar/stations")
        data = self._get(url)
        return data.get("features", [])

    def get_radar_station(self, station_id: str) -> Dict:
        """
        Get details for a specific radar station.

        Args:
            station_id: Radar station code (e.g. "KOKX", "KLWX", "KRAX")

        Returns:
            dict with radar station properties including RDA status,
            performance data, and latency metrics.
        """
        url = self._build_url(f"/radar/stations/{station_id}")
        data = self._get(url)
        return data.get("properties", data)

    def get_radar_station_alarms(self, station_id: str) -> Dict:
        """
        Get active alarms for a radar station.

        Args:
            station_id: Radar station code

        Returns:
            dict with alarm information.
        """
        url = self._build_url(f"/radar/stations/{station_id}/alarms")
        return self._get(url)

    def get_radar_servers(self) -> List[Dict]:
        """
        Get a list of NWS radar data servers.

        Returns:
            List of radar server dicts.
        """
        url = self._build_url("/radar/servers")
        data = self._get(url)
        return data.get("@graph", [])

    def get_radar_image_url(
        self,
        station_id: str,
        product: str = "standard",
        frame: int = 0,
    ) -> str:
        """
        Build the URL for a radar GIF image from the NWS Ridge viewer.

        These are PNG/GIF images served from radar.weather.gov.

        Args:
            station_id: Radar station code (e.g. "KOKX", "KDIX")
            product:    Image product type. Common values:
                        "standard"    = standard reflectivity mosaic
                        "N0R"         = base reflectivity 124 nm range
                        "N0Z"         = base reflectivity 248 nm range
                        "N0V"         = base velocity
                        "N0C"         = correlation coefficient
                        "NCR"         = composite reflectivity
            frame:      Frame index (0 = most recent)

        Returns:
            URL string for the radar image GIF.
        """
        return f"https://radar.weather.gov/ridge/standard/{station_id}_{frame}.gif"

    # -----------------------------------------------------------------------
    # Products (Text Forecasts, Watches, Warnings)
    # -----------------------------------------------------------------------
    def get_products(
        self,
        product_type: Optional[str] = None,
        office: Optional[str] = None,
        wmoid: Optional[str] = None,
        awipsid: Optional[str] = None,
        location: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict]:
        """
        Search for NWS text products (forecasts, watches, warnings, discussions).

        Args:
            product_type: 3-letter product code (e.g. "AFD" = Area Forecast Discussion,
                          "FWF" = Fire Weather Forecast, "SPS" = Special Weather Statement,
                          "SWR" = Severe Weather Statement, "TWC" = Tropical Weather)
            office:       4-letter ICAO office code (e.g. "KOKX", "KLWX")
                          NOTE: This must be 4 letters (e.g. "KOKX" not "OKX")
            wmoid:        WMO ID filter
            awipsid:      AWIPS product ID filter
            location:     Location identifier filter
            start:        ISO 8601 start time
            end:          ISO 8601 end time
            limit:        Max results

        Returns:
            List of product summary dicts with:
                - id (str): UUID of the product
                - wmoCollectiveId (str)
                - issuingOffice (str): 4-letter office code
                - issuanceTime (str): ISO datetime
                - productCode (str): 3-letter type code
                - productName (str): Human-readable name
        """
        params: Dict[str, Any] = {"limit": limit}
        if product_type:
            params["type"] = product_type
        if office:
            params["office"] = office
        if wmoid:
            params["wmoid"] = wmoid
        if awipsid:
            params["awipsid"] = awipsid
        if location:
            params["location"] = location
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        url = self._build_url("/products")
        data = self._get(url, params=params)
        return data.get("@graph", [])

    def get_product(self, product_id: str) -> Dict:
        """
        Get the full text content of a specific NWS product.

        Args:
            product_id: UUID of the product (from get_products() results)

        Returns:
            dict with:
                - id, wmoCollectiveId, issuingOffice, issuanceTime
                - productCode, productName
                - productText (str): Full text of the product
        """
        url = self._build_url(f"/products/{product_id}")
        return self._get(url)

    def get_product_types(self) -> List[Dict]:
        """
        Get a list of all NWS text product type codes and names.

        Returns:
            List of dicts with 'productCode' and 'productName'.
            There are ~200+ product types including:
                AFD = Area Forecast Discussion
                CFW = Coastal/Lakeshore Hazard Message
                FWF = Routine Fire Wx Forecast (Morning)
                HWO = Hazardous Weather Outlook
                MWS = Marine Weather Statement
                RFD = Routine Fire Wx Forecast (Afternoon)
                SPS = Special Weather Statement
                SVR = Severe Thunderstorm Warning
                TOR = Tornado Warning
                TSU = Tsunami Warning
                ZFP = Zone Forecast Product
        """
        url = self._build_url("/products/types")
        data = self._get(url)
        return data.get("@graph", [])

    def get_product_type_locations(self, type_id: str) -> Dict:
        """
        Get the locations that issue a specific product type.

        Args:
            type_id: 3-letter product code (e.g. "AFD")

        Returns:
            dict mapping location codes to location names.
        """
        url = self._build_url(f"/products/types/{type_id}/locations")
        data = self._get(url)
        return data.get("locations", {})

    def get_product_locations(self) -> Dict:
        """
        Get a list of all NWS product issuance location codes.

        Returns:
            dict mapping location codes to location names or null.
        """
        url = self._build_url("/products/locations")
        data = self._get(url)
        return data.get("locations", {})

    def get_latest_product(self, type_id: str, location_id: str) -> Dict:
        """
        Get the most recent version of a product for a specific location.

        Args:
            type_id:     3-letter product code (e.g. "AFD")
            location_id: Location code (e.g. "OKX", "LOX")

        Returns:
            dict with the full text of the most recent product.
        """
        url = self._build_url(
            f"/products/types/{type_id}/locations/{location_id}/latest"
        )
        return self._get(url)

    # -----------------------------------------------------------------------
    # Aviation
    # -----------------------------------------------------------------------
    def get_sigmets(
        self,
        atsu: Optional[str] = None,
        date: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get active SIGMETs (Significant Meteorological Information).

        SIGMETs are aviation weather advisories for hazardous conditions
        affecting flight including severe turbulence, icing, and volcanic ash.

        Args:
            atsu: Air Traffic Service Unit code (e.g. "KKCI", "KZWY")
            date: Date string (YYYY-MM-DD)

        Returns:
            List of SIGMET feature dicts with: id, issueTime, fir, atsu,
            sequence, phenomenon, start, end, and geometry.
        """
        if atsu and date:
            url = self._build_url(f"/aviation/sigmets/{atsu}/{date}")
        elif atsu:
            url = self._build_url(f"/aviation/sigmets/{atsu}")
        else:
            url = self._build_url("/aviation/sigmets")
        data = self._get(url)
        return data.get("features", [])

    def get_cwas(self, cwsu_id: str) -> Dict:
        """
        Get Center Weather Advisories (CWAs) from an Air Route Traffic Control Center.

        CWAs are issued by meteorologists at FAA Air Route Traffic Control Centers.

        Args:
            cwsu_id: CWSU (Center Weather Service Unit) identifier
                     (e.g. "ZNY" = New York, "ZLA" = Los Angeles)

        Returns:
            dict with CWA data.
        """
        url = self._build_url(f"/aviation/cwsus/{cwsu_id}/cwas")
        return self._get(url)

    # -----------------------------------------------------------------------
    # Glossary
    # -----------------------------------------------------------------------
    def get_glossary(self) -> List[Dict]:
        """
        Get the NWS meteorological glossary.

        Returns:
            List of dicts with 'term' (str) and 'definition' (str) keys.
            Contains hundreds of weather-related terms and abbreviations.
        """
        url = self._build_url("/glossary")
        data = self._get(url)
        return data.get("glossary", [])

    # -----------------------------------------------------------------------
    # Icons
    # -----------------------------------------------------------------------
    def get_icon(
        self,
        icon_set: str,
        time_of_day: str,
        condition_1: str,
        condition_2: Optional[str] = None,
        size: str = "medium",
    ) -> str:
        """
        Get the URL for an NWS weather condition icon image.

        Args:
            icon_set:    "land" or "sea"
            time_of_day: "day" or "night"
            condition_1: Primary condition code (e.g. "skc", "bkn", "ra", "sn")
            condition_2: Optional secondary condition code for dual icons
            size:        "small", "medium", or "large"

        Returns:
            URL string for the icon image.

        Common condition codes:
            skc = Clear sky
            few = Few clouds
            sct = Scattered clouds
            bkn = Broken clouds
            ovc = Overcast
            wind = Windy
            snow = Snow
            rain_snow = Rain/Snow mix
            fzra = Freezing rain
            sleet = Sleet
            ra = Rain
            tsra = Thunderstorms
            fog = Fog
            smoke = Smoke
            dust = Dust
            blizzard = Blizzard
            cold = Very cold
            hot = Very hot
            tornado = Tornado
            hurricane = Hurricane
        """
        if condition_2:
            path = f"/icons/{icon_set}/{time_of_day}/{condition_1}/{condition_2}"
        else:
            path = f"/icons/{icon_set}/{time_of_day}/{condition_1}"
        params = {"size": size}
        return f"{BASE_URL}{path}?size={size}"

    # -----------------------------------------------------------------------
    # Satellite
    # -----------------------------------------------------------------------
    def get_satellite_thumbnail(self, area: str) -> Dict:
        """
        Get satellite imagery thumbnail information for a geographic area.

        Args:
            area: Area code. Known valid values include:
                  "us"     = Continental United States
                  Other codes may include regional designations.

        Returns:
            dict with thumbnail image URLs and metadata.
        """
        url = self._build_url(f"/thumbnails/satellite/{area}")
        return self._get(url)

    def get_goes_satellite_url(
        self,
        satellite: str = "GOES19",
        sector: str = "CONUS",
        product: str = "GEOCOLOR",
        size: str = "625x375",
    ) -> str:
        """
        Build a URL for a GOES satellite image from NESDIS/STAR.

        This is an undocumented but reliable endpoint used by the NWS website.
        Images are typically updated every 5-15 minutes.

        Args:
            satellite: Satellite name ("GOES19" = East, "GOES18" = West, "GOES17")
            sector:    Coverage area:
                       "CONUS"  = Continental US (full res)
                       "FULL"   = Full disk
                       "MESOSCALE-1" = Mesoscale sector 1
                       "MESOSCALE-2" = Mesoscale sector 2
                       "SECTOR/SE" = Southeast US
                       "SECTOR/MW" = Midwest US
                       "SECTOR/NE" = Northeast US
                       "SECTOR/SW" = Southwest US
                       "SECTOR/NW" = Northwest US
            product:   Image product:
                       "GEOCOLOR"     = True color daytime / multispectral
                       "AirMass"      = Air mass analysis
                       "DayConvection" = Daytime convection
                       "Sandwich"     = RGB Sandwich (infrared overlay)
                       "Band02"       = Visible
                       "Band13"       = Clean Longwave IR Window
            size:      Image dimensions (e.g. "625x375", "1250x750", "2500x1500")

        Returns:
            URL string for the satellite image (JPEG).
        """
        return (
            f"https://cdn.star.nesdis.noaa.gov/{satellite}/ABI/{sector}"
            f"/{product}/{size}.jpg"
        )

    # -----------------------------------------------------------------------
    # Helper utilities
    # -----------------------------------------------------------------------
    def resolve_grid(self, lat: float, lon: float) -> Tuple[str, int, int]:
        """
        Resolve a lat/lon to NWS grid coordinates (wfo, x, y).

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Tuple of (wfo_code, grid_x, grid_y) e.g. ("OKX", 33, 35)
        """
        point = self.get_point(lat, lon)
        return point["gridId"], point["gridX"], point["gridY"]

    def get_metar(self, station_id: str) -> str:
        """
        Get the raw METAR string from the latest station observation.

        Args:
            station_id: ICAO station code (e.g. "KNYC", "KJFK")

        Returns:
            Raw METAR string, e.g. "KNYC 250051Z AUTO 10SM CLR 04/M06 A3037..."
        """
        obs = self.get_station_observation_latest(station_id)
        return obs.get("rawMessage", "")


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------
def celsius_to_fahrenheit(celsius: Optional[float]) -> Optional[float]:
    """Convert Celsius to Fahrenheit."""
    if celsius is None:
        return None
    return round(celsius * 9 / 5 + 32, 1)


def pa_to_inhg(pascals: Optional[float]) -> Optional[float]:
    """Convert Pascals to inches of mercury."""
    if pascals is None:
        return None
    return round(pascals / 3386.389, 2)


def ms_to_mph(ms: Optional[float]) -> Optional[float]:
    """Convert m/s to mph."""
    if ms is None:
        return None
    return round(ms * 2.237, 1)


def kmh_to_mph(kmh: Optional[float]) -> Optional[float]:
    """Convert km/h to mph."""
    if kmh is None:
        return None
    return round(kmh * 0.6214, 1)


def format_observation(obs: Dict) -> Dict:
    """
    Convert an NWS observation dict to human-friendly US units.

    Args:
        obs: Raw observation properties dict from the NWS API.

    Returns:
        dict with values in Fahrenheit, mph, inHg, etc.
    """
    def _val(d: Any) -> Optional[float]:
        if isinstance(d, dict):
            return d.get("value")
        return None

    temp_c = _val(obs.get("temperature"))
    dew_c = _val(obs.get("dewpoint"))
    ws_kmh = _val(obs.get("windSpeed"))
    wg_kmh = _val(obs.get("windGust"))
    pres_pa = _val(obs.get("barometricPressure"))
    slp_pa = _val(obs.get("seaLevelPressure"))
    vis_m = _val(obs.get("visibility"))

    return {
        "station": obs.get("stationId") or obs.get("station", "").split("/")[-1],
        "station_name": obs.get("stationName", ""),
        "timestamp": obs.get("timestamp", ""),
        "description": obs.get("textDescription", ""),
        "raw_metar": obs.get("rawMessage", ""),
        "temperature_f": celsius_to_fahrenheit(temp_c),
        "temperature_c": round(temp_c, 1) if temp_c is not None else None,
        "dewpoint_f": celsius_to_fahrenheit(dew_c),
        "dewpoint_c": round(dew_c, 1) if dew_c is not None else None,
        "wind_direction_deg": _val(obs.get("windDirection")),
        "wind_speed_mph": kmh_to_mph(ws_kmh),
        "wind_gust_mph": kmh_to_mph(wg_kmh),
        "pressure_inhg": pa_to_inhg(pres_pa),
        "sea_level_pressure_inhg": pa_to_inhg(slp_pa),
        "visibility_miles": round(vis_m / 1609.34, 1) if vis_m is not None else None,
        "humidity_pct": round(_val(obs.get("relativeHumidity")), 1)
        if _val(obs.get("relativeHumidity")) is not None
        else None,
        "heat_index_f": celsius_to_fahrenheit(_val(obs.get("heatIndex"))),
        "wind_chill_f": celsius_to_fahrenheit(_val(obs.get("windChill"))),
        "icon": obs.get("icon"),
    }


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    print("=" * 70)
    print("NWS API Python Client Demo")
    print("=" * 70)

    client = NWSClient(
        user_agent="NWSClientDemo/1.0 (demo@example.com)"
    )

    # -----------------------------------------------------------------
    # 1. Point lookup (NYC)
    # -----------------------------------------------------------------
    LAT, LON = 40.7128, -74.0060
    print(f"\n[1] Resolving grid point for lat={LAT}, lon={LON} (New York City)")
    point = client.get_point(LAT, LON)
    wfo = point["gridId"]
    gx = point["gridX"]
    gy = point["gridY"]
    loc = point.get("relativeLocation", {}).get("properties", {})
    print(f"    Office: {wfo} | Grid: ({gx}, {gy})")
    print(f"    Nearest city: {loc.get('city')}, {loc.get('state')}")
    print(f"    Timezone: {point.get('timeZone')}")
    print(f"    Radar station: {point.get('radarStation')}")

    # -----------------------------------------------------------------
    # 2. 7-day forecast
    # -----------------------------------------------------------------
    print(f"\n[2] 7-Day Forecast for New York City")
    forecast = client.get_forecast(wfo, gx, gy)
    periods = forecast.get("periods", [])[:4]
    for p in periods:
        icon = "☀" if p["isDaytime"] else "🌙"
        precip = p.get("probabilityOfPrecipitation", {}).get("value") or 0
        print(
            f"    {p['name']:<20} {p['temperature']}°{p['temperatureUnit']}"
            f"  Wind: {p['windSpeed']} {p['windDirection']}"
            f"  PoP: {precip}%  |  {p['shortForecast']}"
        )

    # -----------------------------------------------------------------
    # 3. Hourly forecast (next 6 hours)
    # -----------------------------------------------------------------
    print(f"\n[3] Hourly Forecast (next 6 hours)")
    hourly = client.get_forecast_hourly(wfo, gx, gy)
    h_periods = hourly.get("periods", [])[:6]
    for h in h_periods:
        dt = h["startTime"][11:16]
        precip = h.get("probabilityOfPrecipitation", {}).get("value") or 0
        humid = h.get("relativeHumidity", {}).get("value") or 0
        print(
            f"    {dt}  {h['temperature']}°{h['temperatureUnit']}"
            f"  Wind: {h['windSpeed']} {h['windDirection']}"
            f"  PoP: {precip}%  RH: {humid}%"
            f"  |  {h['shortForecast']}"
        )

    # -----------------------------------------------------------------
    # 4. Current conditions (nearest station)
    # -----------------------------------------------------------------
    print(f"\n[4] Current Conditions at nearest station to NYC")
    try:
        obs_raw = client.get_station_observation_latest("KNYC")
        obs = format_observation(obs_raw)
        print(f"    Station: KNYC - {obs['station_name']}")
        print(f"    Time: {obs['timestamp']}")
        print(f"    Condition: {obs['description']}")
        print(f"    Temperature: {obs['temperature_f']}°F ({obs['temperature_c']}°C)")
        print(f"    Dewpoint: {obs['dewpoint_f']}°F")
        print(f"    Wind: {obs['wind_speed_mph']} mph from {obs['wind_direction_deg']}°")
        if obs["wind_gust_mph"]:
            print(f"    Gusts: {obs['wind_gust_mph']} mph")
        print(f"    Pressure: {obs['pressure_inhg']} inHg")
        print(f"    Visibility: {obs['visibility_miles']} miles")
        print(f"    Humidity: {obs['humidity_pct']}%")
        print(f"    METAR: {obs['raw_metar']}")
    except NWSClientError as e:
        print(f"    Error: {e}")

    # -----------------------------------------------------------------
    # 5. Active alerts in NY
    # -----------------------------------------------------------------
    print(f"\n[5] Active Weather Alerts for New York State")
    alerts = client.get_active_alerts(area="NY")
    feats = alerts.get("features", [])
    if feats:
        print(f"    Found {len(feats)} active alert(s):")
        for a in feats[:3]:
            p = a.get("properties", {})
            print(
                f"    [{p.get('severity', 'Unknown')}] {p.get('event')} "
                f"- {p.get('areaDesc', '')[:60]}"
            )
    else:
        print("    No active alerts for NY at this time.")

    # -----------------------------------------------------------------
    # 6. Alert count
    # -----------------------------------------------------------------
    print(f"\n[6] Nationwide Active Alert Count")
    count = client.get_active_alerts_count()
    print(f"    Total active alerts: {count.get('total')}")
    print(f"    Land alerts: {count.get('land')}")
    print(f"    Marine alerts: {count.get('marine')}")

    # -----------------------------------------------------------------
    # 7. Radar station info
    # -----------------------------------------------------------------
    print(f"\n[7] Radar Station KOKX (Brookhaven, NY)")
    try:
        radar = client.get_radar_station("KOKX")
        print(f"    Name: {radar.get('name')}")
        print(f"    Type: {radar.get('stationType')}")
        lat_r = radar.get("stationIdentifier", "")
        latency = radar.get("latency", {})
        print(f"    Last data received: {latency.get('levelTwoLastReceivedTime', 'N/A')}")
        print(f"    Radar image: {client.get_radar_image_url('KOKX')}")
    except NWSClientError as e:
        print(f"    Error: {e}")

    # -----------------------------------------------------------------
    # 8. NWS office info
    # -----------------------------------------------------------------
    print(f"\n[8] NWS Office OKX (New York)")
    office = client.get_office("OKX")
    addr = office.get("address", {})
    print(f"    Name: {office.get('name')}")
    print(f"    Address: {addr.get('streetAddress')}, {addr.get('addressLocality')}, {addr.get('addressRegion')}")
    print(f"    Phone: {office.get('telephone')}")
    print(f"    Email: {office.get('email')}")
    print(f"    Region: {office.get('nwsRegion')}")

    # -----------------------------------------------------------------
    # 9. Products (Area Forecast Discussion)
    # -----------------------------------------------------------------
    print(f"\n[9] Latest Area Forecast Discussion from KOKX")
    try:
        prods = client.get_products(product_type="AFD", office="KOKX", limit=1)
        if prods:
            p = prods[0]
            print(f"    Product: {p['productName']} ({p['productCode']})")
            print(f"    Issued: {p['issuanceTime']}")
            full = client.get_product(p["id"])
            text = full.get("productText", "")[:400]
            print(f"    Text preview:\n{text}...")
        else:
            print("    No AFD products found.")
    except NWSClientError as e:
        print(f"    Error: {e}")

    # -----------------------------------------------------------------
    # 10. Zone info
    # -----------------------------------------------------------------
    print(f"\n[10] Forecast Zone NYZ072 (Manhattan)")
    zone = client.get_zone("forecast", "NYZ072")
    zprops = zone.get("properties", zone)
    print(f"    Zone: {zprops.get('id')} - {zprops.get('name')}")
    print(f"    State: {zprops.get('state')}")
    print(f"    Office: {zprops.get('forecastOffice', '').split('/')[-1]}")

    # -----------------------------------------------------------------
    # 11. Active SIGMETs
    # -----------------------------------------------------------------
    print(f"\n[11] Active Aviation SIGMETs")
    try:
        sigmets = client.get_sigmets()
        print(f"    Active SIGMETs: {len(sigmets)}")
        for s in sigmets[:2]:
            p = s.get("properties", {})
            print(f"    [{p.get('atsu')}] {p.get('sequence')} - {p.get('start')} to {p.get('end')}")
    except NWSClientError as e:
        print(f"    Error: {e}")

    # -----------------------------------------------------------------
    # 12. GOES satellite image URL
    # -----------------------------------------------------------------
    print(f"\n[12] GOES Satellite Image URLs")
    conus_url = client.get_goes_satellite_url("GOES19", "CONUS", "GEOCOLOR", "625x375")
    ne_url = client.get_goes_satellite_url("GOES19", "SECTOR/NE", "GEOCOLOR", "1200x1200")
    print(f"    CONUS true color: {conus_url}")
    print(f"    Northeast sector: {ne_url}")

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)
