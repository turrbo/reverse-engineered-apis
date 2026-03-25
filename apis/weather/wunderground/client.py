"""
Weather Underground (WUnderground) Internal API Client
======================================================
Reverse-engineered from https://www.wunderground.com

Architecture:
- Primary API base: https://api.weather.com  (api0-api3 are load-balanced mirrors)
- PWS (Personal Weather Station) API: v2 endpoints
- Forecast/Current Conditions API: v3 endpoints
- Radar/Tile API: v3/TileServer endpoints
- Legacy WU API: https://api-ak.wunderground.com/api (deprecated, redirects)

API Keys (embedded in site, may rotate):
- SUN_API_KEY / primary: e1f10a1e78da46f5b10a1e78da96f525
- WX_API_KEY:             5c241d89f91274015a577e3e17d43370
- DSX_API_KEY:            7bb1c920-7027-4289-9c96-ae5e263980bc
- UPS_API_KEY:            3254cfcb-90e3-4af5-819f-d79ea7e2382f
- WU_LEGACY_API_KEY:      d8585d80376a429e

Internal Service Hosts (from process.env):
- WU_LEGACY_API_HOST:        https://api-ak.wunderground.com/api
- DSX_API_HOST:              https://dsx.weather.com
- UPS_API_HOST:              https://profile.wunderground.com
- UPSX_API_HOST:             https://upsx.wunderground.com
- SUN_API_HOST:              https://api.weather.com
- SUN_DEVICE_API_HOST:       https://station-management.wunderground.com
- SUN_PWS_HISTORY_API_HOST:  https://api.weather.com/v2/pws/history

Units parameter:
- "e" = imperial/English (°F, mph, inches)
- "m" = metric (°C, km/h, mm)
- "s" = SI (°C, m/s, mm)
- "h" = hybrid metric

Usage:
    client = WundergroundClient()  # uses embedded key
    # Or provide your own key:
    client = WundergroundClient(api_key="your_key_here")

    # Search for a location
    results = client.search_location("New York")

    # Get current conditions
    conditions = client.get_current_conditions(geocode="40.71,-74.01")

    # Get PWS current data
    obs = client.get_pws_current("KCASANFR1753")

    # Get 10-day forecast
    forecast = client.get_forecast_daily("40.71,-74.01", days=10)
"""

import requests
import json
from datetime import datetime, date
from typing import Optional, Union, Dict, Any, List
from urllib.parse import urlencode


# ─────────────────────────────────────────────
# Default embedded API keys (from wunderground.com source)
# These rotate occasionally - check the site for updates
# ─────────────────────────────────────────────
DEFAULT_API_KEY = "e1f10a1e78da46f5b10a1e78da96f525"   # SUN_API_KEY (primary)
WX_API_KEY      = "5c241d89f91274015a577e3e17d43370"   # WX_API_KEY
DSX_API_KEY     = "7bb1c920-7027-4289-9c96-ae5e263980bc"
UPS_API_KEY     = "3254cfcb-90e3-4af5-819f-d79ea7e2382f"
LEGACY_API_KEY  = "d8585d80376a429e"                    # WU_LEGACY_API_KEY

# API base URLs
SUN_API_BASE    = "https://api.weather.com"
WX_API_BASE     = "https://weather.com"
DSX_API_BASE    = "https://dsx.weather.com"
PROFILE_BASE    = "https://profile.wunderground.com"
UPSX_BASE       = "https://upsx.wunderground.com"
STATION_MGMT    = "https://station-management.wunderground.com"


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.wunderground.com/",
    "Origin": "https://www.wunderground.com",
}


class WundergroundError(Exception):
    """Raised when the API returns an error."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class WundergroundClient:
    """
    Comprehensive Python client for Weather Underground / The Weather Company APIs.

    All endpoints discovered by reverse-engineering wunderground.com.
    """

    def __init__(
        self,
        api_key: str = DEFAULT_API_KEY,
        units: str = "e",
        language: str = "en-US",
        session: Optional[requests.Session] = None,
        timeout: int = 15,
    ):
        """
        Args:
            api_key:  The Weather Company API key (default: embedded site key).
            units:    Unit system: "e" (imperial), "m" (metric), "s" (SI), "h" (hybrid).
            language: Language code (default "en-US").
            session:  Optional requests.Session for connection pooling / auth.
            timeout:  HTTP timeout in seconds.
        """
        self.api_key = api_key
        self.units = units
        self.language = language
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    # ─────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────

    def _get(self, url: str, params: Dict = None) -> Any:
        """Make a GET request and return parsed JSON (or raise WundergroundError)."""
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise WundergroundError(f"HTTP request failed: {exc}") from exc

        if resp.status_code == 204:
            return None  # No content (e.g. no alerts)

        if not resp.ok:
            raise WundergroundError(
                f"API returned {resp.status_code}",
                status_code=resp.status_code,
                response_body=resp.text[:500],
            )

        if not resp.text:
            return None

        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise WundergroundError(
                f"Could not decode JSON: {exc}",
                status_code=resp.status_code,
                response_body=resp.text[:500],
            ) from exc

    def _sun_url(self, path: str) -> str:
        """Build a URL against the primary api.weather.com base."""
        return f"{SUN_API_BASE}/{path.lstrip('/')}"

    def _sun_params(self, extra: Dict = None) -> Dict:
        """Build common query params for api.weather.com."""
        params = {
            "apiKey": self.api_key,
            "units": self.units,
            "language": self.language,
            "format": "json",
        }
        if extra:
            params.update(extra)
        return params

    # ─────────────────────────────────────────
    # SECTION 1: Location APIs (v3/location/*)
    # ─────────────────────────────────────────

    def search_location(
        self,
        query: str,
        country_code: str = None,
        admin_district_code: str = None,
    ) -> Dict:
        """
        Search for locations by name, ZIP, coordinates, etc.

        Endpoint: GET /v3/location/search
        Example: https://api.weather.com/v3/location/search?apiKey=...&language=en-US&query=New+York&format=json

        Args:
            query:                Search term (city name, ZIP code, etc.)
            country_code:         Optional ISO country code filter (e.g. "US").
            admin_district_code:  Optional state/province code filter (e.g. "ny").

        Returns:
            dict with "location" key containing arrays of matching locations.
        """
        params = {
            "apiKey": self.api_key,
            "language": self.language,
            "query": query,
            "format": "json",
        }
        if country_code:
            params["countryCode"] = country_code
        if admin_district_code:
            params["adminDistrictCode"] = admin_district_code
        return self._get(self._sun_url("/v3/location/search"), params=params)

    def get_location_point(
        self,
        geocode: str = None,
        pws_id: str = None,
        postal_key: str = None,
        icao_code: str = None,
    ) -> Dict:
        """
        Resolve a location to a full location object (city, timezone, IDs, etc.).

        Endpoint: GET /v3/location/point
        Example: https://api.weather.com/v3/location/point?apiKey=...&language=en-US&pws=KCASANFR1753&format=json

        Args:
            geocode:    "lat,lon" string e.g. "40.71,-74.01"
            pws_id:     Personal Weather Station ID e.g. "KCASANFR1753"
            postal_key: ZIP:country e.g. "10001:US"
            icao_code:  Airport ICAO code e.g. "KJFK"

        Returns:
            dict with "location" key.
        """
        params = {
            "apiKey": self.api_key,
            "language": self.language,
            "format": "json",
        }
        if geocode:
            params["geocode"] = geocode
        elif pws_id:
            params["pws"] = pws_id
        elif postal_key:
            params["postalKey"] = postal_key
        elif icao_code:
            params["icaoCode"] = icao_code
        else:
            raise ValueError("Provide geocode, pws_id, postal_key, or icao_code")
        return self._get(self._sun_url("/v3/location/point"), params=params)

    def get_nearby_pws(self, geocode: str) -> Dict:
        """
        Find Personal Weather Stations near a geocode.

        Endpoint: GET /v3/location/near?product=pws
        Example: https://api.weather.com/v3/location/near?apiKey=...&geocode=40.713,-74.006&product=pws&format=json

        Args:
            geocode: "lat,lon" e.g. "40.71,-74.01"

        Returns:
            dict with "location" key containing stationId, stationName, latitude, longitude, etc.
        """
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "product": "pws",
            "format": "json",
        }
        return self._get(self._sun_url("/v3/location/near"), params=params)

    def get_nearby_airports(self, geocode: str, subproduct: str = "major") -> Dict:
        """
        Find airports near a geocode.

        Endpoint: GET /v3/location/near?product=airport

        Args:
            geocode:    "lat,lon"
            subproduct: "major" or "all"

        Returns:
            dict with "location" key containing airport info.
        """
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "product": "airport",
            "subproduct": subproduct,
            "format": "json",
        }
        return self._get(self._sun_url("/v3/location/near"), params=params)

    def get_location_elevation(self, geocode: str) -> Dict:
        """
        Get terrain elevation for a geocode.

        Endpoint: GET /v3/location/elevation

        Args:
            geocode: "lat,lon"

        Returns:
            dict with "location.elevation" in requested units.
        """
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "units": self.units,
            "format": "json",
        }
        return self._get(self._sun_url("/v3/location/elevation"), params=params)

    def get_datetime_for_location(self, geocode: str) -> Dict:
        """
        Get current local date/time and timezone for a geocode.

        Endpoint: GET /v3/dateTime
        Example: https://api.weather.com/v3/dateTime?apiKey=...&geocode=40.713,-74.006&format=json

        Returns:
            {"dateTime": "...", "ianaTimeZone": "America/New_York", "timeZoneAbbreviation": "EDT"}
        """
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "format": "json",
        }
        return self._get(self._sun_url("/v3/dateTime"), params=params)

    # ─────────────────────────────────────────
    # SECTION 2: Current Conditions (v3/wx/observations/*)
    # ─────────────────────────────────────────

    def get_current_conditions(
        self,
        geocode: str = None,
        icao_code: str = None,
    ) -> Dict:
        """
        Get current weather conditions for a geocode or airport.

        Endpoint: GET /v3/wx/observations/current
        Example: https://api.weather.com/v3/wx/observations/current?apiKey=...&geocode=40.71,-74.01&units=e&language=en-US&format=json

        Returns:
            Flat dict with temperature, windSpeed, humidity, wxPhraseLong, etc.
        """
        params = {
            "apiKey": self.api_key,
            "units": self.units,
            "language": self.language,
            "format": "json",
        }
        if geocode:
            params["geocode"] = geocode
        elif icao_code:
            params["icaoCode"] = icao_code
        else:
            raise ValueError("Provide geocode or icao_code")
        return self._get(self._sun_url("/v3/wx/observations/current"), params=params)

    def get_current_conditions_multi(self, geocodes: List[str]) -> List[Dict]:
        """
        Get current conditions for multiple locations in one request.

        Endpoint: GET /v3/aggcommon/v3alertsHeadlines;v3-wx-observations-current;v3-location-point
        Example: https://api.weather.com/v3/aggcommon/v3alertsHeadlines;v3-wx-observations-current;v3-location-point?apiKey=...&geocodes=37.77,-122.41;40.75,-74&language=en-US&units=e&format=json

        Args:
            geocodes: List of "lat,lon" strings (up to ~6 recommended).

        Returns:
            List of dicts, each with id, v3alertsHeadlines, v3-wx-observations-current, v3-location-point.
        """
        params = {
            "apiKey": self.api_key,
            "geocodes": ";".join(geocodes),
            "language": self.language,
            "units": self.units,
            "format": "json",
        }
        path = "/v3/aggcommon/v3alertsHeadlines;v3-wx-observations-current;v3-location-point"
        return self._get(self._sun_url(path), params=params)

    # ─────────────────────────────────────────
    # SECTION 3: Forecasts (v3/wx/forecast/*)
    # ─────────────────────────────────────────

    def get_forecast_daily(
        self,
        geocode: str = None,
        icao_code: str = None,
        days: int = 5,
    ) -> Dict:
        """
        Get daily weather forecast.

        Endpoint: GET /v3/wx/forecast/daily/{n}day
        Example: https://api.weather.com/v3/wx/forecast/daily/10day?apiKey=...&geocode=40.71,-74.01&units=e&language=en-US&format=json

        Args:
            geocode:   "lat,lon"
            icao_code: Airport ICAO code
            days:      Number of days: 3, 5, 7, 10, or 15.

        Returns:
            Dict with arrays: dayOfWeek, temperatureMax, temperatureMin, narrative,
            qpf, moonPhase, sunriseTimeLocal, sunsetTimeLocal, daypart (hourly details), etc.
        """
        if days not in (3, 5, 7, 10, 15):
            raise ValueError("days must be one of: 3, 5, 7, 10, 15")
        params = {
            "apiKey": self.api_key,
            "units": self.units,
            "language": self.language,
            "format": "json",
        }
        if geocode:
            params["geocode"] = geocode
        elif icao_code:
            params["icaoCode"] = icao_code
        else:
            raise ValueError("Provide geocode or icao_code")
        return self._get(self._sun_url(f"/v3/wx/forecast/daily/{days}day"), params=params)

    def get_forecast_hourly(
        self,
        geocode: str,
        hours: Union[int, str] = "15day",
    ) -> Dict:
        """
        Get hourly weather forecast (up to 360 hours / 15 days).

        Endpoint: GET /v3/wx/forecast/hourly/{n}
        Example: https://api.weather.com/v3/wx/forecast/hourly/15day?apiKey=...&geocode=40.71,-74.01&units=e&language=en-US&format=json

        Args:
            geocode: "lat,lon"
            hours:   "1day" or "15day" (string), or integer 1..360.

        Returns:
            Dict with 360 entries, arrays: temperature, precipChance, windSpeed, cloudCover,
            iconCode, wxPhraseLong, validTimeLocal, dayOrNight, etc.
        """
        if isinstance(hours, int):
            period = f"{hours}day"
        else:
            period = hours
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "units": self.units,
            "language": self.language,
            "format": "json",
        }
        return self._get(self._sun_url(f"/v3/wx/forecast/hourly/{period}"), params=params)

    # ─────────────────────────────────────────
    # SECTION 4: Historical Conditions
    # ─────────────────────────────────────────

    def get_historical_conditions_hourly(self, geocode: str, period: str = "1day") -> Dict:
        """
        Get historical hourly conditions for the past 1 day.

        Endpoint: GET /v3/wx/conditions/historical/hourly/1day
        Example: https://api.weather.com/v3/wx/conditions/historical/hourly/1day?apiKey=...&geocode=40.71,-74.01&units=e&language=en-US&format=json

        Args:
            geocode: "lat,lon"
            period:  "1day" (only value currently exposed)

        Returns:
            Dict with 24 hourly entries: temperature, precipChance, windSpeed, etc.
        """
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "units": self.units,
            "language": self.language,
            "format": "json",
        }
        return self._get(
            self._sun_url(f"/v3/wx/conditions/historical/hourly/{period}"), params=params
        )

    def get_historical_conditions_daily_summary(
        self,
        icao_code: str,
        period: str = "30day",
    ) -> Dict:
        """
        Get historical daily summary for the past 30 days (requires airport ICAO code).

        Endpoint: GET /v3/wx/conditions/historical/dailysummary/30day
        Example: https://api.weather.com/v3/wx/conditions/historical/dailysummary/30day?apiKey=...&icaoCode=KJRB&units=e&language=EN&format=json

        Args:
            icao_code: Airport ICAO code (e.g. "KJFK", "KJRB")
            period:    "30day"

        Returns:
            Dict with arrays: temperatureMax, temperatureMin, precip24Hour, snow24Hour,
            iconCodeDay, iconCodeNight, etc.
        """
        params = {
            "apiKey": self.api_key,
            "icaoCode": icao_code,
            "units": self.units,
            "language": self.language.split("-")[0].upper(),
            "format": "json",
        }
        return self._get(
            self._sun_url(f"/v3/wx/conditions/historical/dailysummary/{period}"), params=params
        )

    # ─────────────────────────────────────────
    # SECTION 5: Almanac (Historical Averages)
    # ─────────────────────────────────────────

    def get_almanac_daily(
        self,
        icao_code: str,
        start_month: int,
        start_day: int,
        days: int = 5,
    ) -> Dict:
        """
        Get historical climate normals / almanac data for a period.

        Endpoint: GET /v3/wx/almanac/daily/5day
        Example: https://api.weather.com/v3/wx/almanac/daily/5day?apiKey=...&icaoCode=KJRB&units=e&startMonth=03&startDay=25&format=json

        Args:
            icao_code:   Airport ICAO code.
            start_month: Month integer (1-12).
            start_day:   Day integer (1-31).
            days:        Number of days to return (typically 5 or 10).

        Returns:
            Dict with arrays: temperatureAverageMax, temperatureAverageMin,
            temperatureRecordMax, temperatureRecordMin, precipitationAverage, etc.
        """
        params = {
            "apiKey": self.api_key,
            "icaoCode": icao_code,
            "units": self.units,
            "startMonth": f"{start_month:02d}",
            "startDay": f"{start_day:02d}",
            "format": "json",
        }
        return self._get(self._sun_url(f"/v3/wx/almanac/daily/{days}day"), params=params)

    # ─────────────────────────────────────────
    # SECTION 6: Astronomy (Sun/Moon)
    # ─────────────────────────────────────────

    def get_astronomy(
        self,
        geocode: str,
        start_date: Union[date, str] = None,
        days: int = 5,
    ) -> Dict:
        """
        Get sunrise/sunset, moonrise/moonset, twilight, and moon phase data.

        Endpoint: GET /v2/astro
        Example: https://api.weather.com/v2/astro?apiKey=...&geocode=40.713,-74.006&days=5&date=20260325&format=json

        Args:
            geocode:    "lat,lon"
            start_date: date object or "YYYYMMDD" string (defaults to today).
            days:       Number of days (1-15).

        Returns:
            Dict with "astroData" list of daily entries each containing sun (rise/set/twilight/zenith)
            and moon (rise/set/phase/illumination) data.
        """
        if start_date is None:
            start_date = date.today().strftime("%Y%m%d")
        elif hasattr(start_date, "strftime"):
            start_date = start_date.strftime("%Y%m%d")
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "days": days,
            "date": start_date,
            "format": "json",
        }
        return self._get(self._sun_url("/v2/astro"), params=params)

    # ─────────────────────────────────────────
    # SECTION 7: Alerts
    # ─────────────────────────────────────────

    def get_alerts_headlines(self, geocode: str) -> Optional[Dict]:
        """
        Get active weather alert headlines for a location.

        Endpoint: GET /v3/alerts/headlines
        Example: https://api.weather.com/v3/alerts/headlines?apiKey=...&geocode=40.713,-74.006&language=EN&format=json

        Returns:
            Dict with "alerts" list, or None if no active alerts (HTTP 204).
        """
        params = {
            "apiKey": self.api_key,
            "geocode": geocode,
            "language": self.language.split("-")[0].upper(),
            "format": "json",
        }
        return self._get(self._sun_url("/v3/alerts/headlines"), params=params)

    def get_alert_detail(self, alert_id: str) -> Dict:
        """
        Get detailed information for a specific weather alert.

        Endpoint: GET /v3/alerts/detail
        Example: https://api.weather.com/v3/alerts/detail?apiKey=...&alertId=...&language=en-US&format=json

        Args:
            alert_id: Alert ID obtained from get_alerts_headlines().
        """
        params = {
            "apiKey": self.api_key,
            "alertId": alert_id,
            "language": self.language,
            "format": "json",
        }
        return self._get(self._sun_url("/v3/alerts/detail"), params=params)

    # ─────────────────────────────────────────
    # SECTION 8: PWS (Personal Weather Station) v2 APIs
    # ─────────────────────────────────────────

    def get_pws_current(self, station_id: str) -> Dict:
        """
        Get current conditions from a Personal Weather Station.

        Endpoint: GET /v2/pws/observations/current
        Example: https://api.weather.com/v2/pws/observations/current?apiKey=...&units=e&stationId=KCASANFR1753&format=json

        Response fields:
            stationID, obsTimeUtc, obsTimeLocal, neighborhood, softwareType,
            country, solarRadiation, lon, lat, uv, winddir, humidity, qcStatus,
            imperial/metric: { temp, heatIndex, dewpt, windChill, windSpeed, windGust,
                               pressure, precipRate, precipTotal, elev }

        Args:
            station_id: PWS station ID e.g. "KCASANFR1753"

        Returns:
            Dict with "observations" list (usually 1 element).
        """
        params = {
            "apiKey": self.api_key,
            "units": self.units,
            "stationId": station_id,
            "format": "json",
        }
        return self._get(self._sun_url("/v2/pws/observations/current"), params=params)

    def get_pws_observations_today(
        self,
        station_id: str,
        observation_type: str = "all",
        numeric_precision: str = "decimal",
    ) -> Dict:
        """
        Get all observations from a PWS for the current day (up to ~288 readings).

        Endpoint: GET /v2/pws/observations/all/1day
        Example: https://api.weather.com/v2/pws/observations/all/1day?apiKey=...&stationId=KCASANFR1753&numericPrecision=decimal&format=json&units=e

        Args:
            station_id:        PWS station ID.
            observation_type:  "all" (all readings), "hourly", or "daily".
            numeric_precision: "decimal" for float values.

        Returns:
            Dict with "observations" list of all readings today.
        """
        if observation_type == "all":
            path = "/v2/pws/observations/all/1day"
        elif observation_type == "hourly":
            path = "/v2/pws/observations/hourly/1day"
        else:
            path = "/v2/pws/observations/all/1day"

        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "numericPrecision": numeric_precision,
            "format": "json",
            "units": self.units,
        }
        return self._get(self._sun_url(path), params=params)

    def get_pws_observations_recent(
        self,
        station_id: str,
        observation_type: str = "all",
        days: int = 1,
    ) -> Dict:
        """
        Get recent PWS observations for 1, 3 (or up to 7 days with auth).

        Endpoints:
            /v2/pws/observations/{type}/1day
            /v2/pws/observations/{type}/3day
            /v2/pws/observations/{type}/7day  (requires premium auth)

        Args:
            station_id:       PWS station ID.
            observation_type: "all" or "hourly" or "daily".
            days:             1, 3, or 7 (7 may require authentication).

        Returns:
            Dict with "observations" list.
        """
        if days not in (1, 3, 7):
            raise ValueError("days must be 1, 3, or 7")
        obs_path = "all" if observation_type == "all" else observation_type
        path = f"/v2/pws/observations/{obs_path}/{days}day"
        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "numericPrecision": "decimal",
            "format": "json",
            "units": self.units,
        }
        return self._get(self._sun_url(path), params=params)

    def get_pws_daily_summary(self, station_id: str, period: str = "1day") -> Dict:
        """
        Get a PWS daily summary (high/low/avg for temp, wind, precip, etc.).

        Endpoint: GET /v2/pws/dailysummary/1day
        Example: https://api.weather.com/v2/pws/dailysummary/1day?apiKey=...&stationId=KCASANFR1753&numericPrecision=decimal&format=json&units=e

        Args:
            station_id: PWS station ID.
            period:     "1day", "3day", or "7day".

        Returns:
            Dict with "summaries" list containing daily highs/lows/averages.
        """
        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "numericPrecision": "decimal",
            "format": "json",
            "units": self.units,
        }
        return self._get(self._sun_url(f"/v2/pws/dailysummary/{period}"), params=params)

    def get_pws_history_daily(
        self,
        station_id: str,
        target_date: Union[date, str],
        numeric_precision: str = "decimal",
    ) -> Dict:
        """
        Get PWS daily history for a specific date.

        Endpoint: GET /v2/pws/history/daily
        Example: https://api.weather.com/v2/pws/history/daily?apiKey=...&stationId=KCASANFR1753&format=json&units=e&numericPrecision=decimal&date=20260101

        Args:
            station_id:        PWS station ID.
            target_date:       date object or "YYYYMMDD" string.
            numeric_precision: "decimal" for float values.

        Returns:
            Dict with "observations" list for the requested day.
        """
        if hasattr(target_date, "strftime"):
            date_str = target_date.strftime("%Y%m%d")
        else:
            date_str = str(target_date)
        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "format": "json",
            "units": self.units,
            "numericPrecision": numeric_precision,
            "date": date_str,
        }
        return self._get(self._sun_url("/v2/pws/history/daily"), params=params)

    def get_pws_history_hourly(
        self,
        station_id: str,
        target_date: Union[date, str],
        numeric_precision: str = "decimal",
    ) -> Dict:
        """
        Get PWS hourly history for a specific date (24 hourly summaries).

        Endpoint: GET /v2/pws/history/hourly
        Example: https://api.weather.com/v2/pws/history/hourly?apiKey=...&stationId=KCASANFR1753&format=json&units=e&numericPrecision=decimal&date=20260101

        Args:
            station_id:        PWS station ID.
            target_date:       date object or "YYYYMMDD" string.
            numeric_precision: "decimal" for float values.

        Returns:
            Dict with "observations" list of 24 hourly summaries.
        """
        if hasattr(target_date, "strftime"):
            date_str = target_date.strftime("%Y%m%d")
        else:
            date_str = str(target_date)
        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "format": "json",
            "units": self.units,
            "numericPrecision": numeric_precision,
            "date": date_str,
        }
        return self._get(self._sun_url("/v2/pws/history/hourly"), params=params)

    def get_pws_history_all(
        self,
        station_id: str,
        target_date: Union[date, str],
    ) -> Dict:
        """
        Get all raw PWS observations for a specific date (every reading, ~288/day).

        Endpoint: GET /v2/pws/history/all
        Example: https://api.weather.com/v2/pws/history/all?apiKey=...&stationId=KCASANFR1753&format=json&units=e&numericPrecision=decimal&date=20260101

        Args:
            station_id:  PWS station ID.
            target_date: date object or "YYYYMMDD" string.

        Returns:
            Dict with "observations" list of all raw readings for the date.
        """
        if hasattr(target_date, "strftime"):
            date_str = target_date.strftime("%Y%m%d")
        else:
            date_str = str(target_date)
        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "format": "json",
            "units": self.units,
            "numericPrecision": "decimal",
            "date": date_str,
        }
        return self._get(self._sun_url("/v2/pws/history/all"), params=params)

    def get_pws_identity(self, station_id: str) -> Dict:
        """
        Get metadata for a PWS station (name, location, elevation, hardware type, etc.).

        Endpoint: GET /v2/pwsidentity
        Example: https://api.weather.com/v2/pwsidentity?apiKey=...&stationId=KCASANFR1753&format=json&units=e

        Returns:
            Dict with ID, neighborhood, name, city, state, country, latitude, longitude,
            elevation, height, stationType, surfaceType, tzName, lastUpdateTime,
            softwareType, goldStar, isRecent.
        """
        params = {
            "apiKey": self.api_key,
            "stationId": station_id,
            "format": "json",
            "units": self.units,
        }
        return self._get(self._sun_url("/v2/pwsidentity"), params=params)

    # ─────────────────────────────────────────
    # SECTION 9: Radar & Satellite Tiles
    # ─────────────────────────────────────────

    def get_tile_series(self, product_set: str = None) -> Dict:
        """
        Get available radar/satellite tile series (timestamps) for animation.

        Endpoint: GET /v3/TileServer/series/productSet
        Example: https://api.weather.com/v3/TileServer/series/productSet?apiKey=...&productSet=wuRadar

        Available product sets (pass productSet=wuRadar):
            wuRadarAlaska, wuRadarAustralian, wuRadarConus, wuRadarEurope,
            wuRadarFcst, wuRadarFcstV2, wuRadarFcstV3, wuRadarHawaii,
            wuRadarHcMosaic, wuRadarMosaic, wuRadarMosaicNS, seaSurfaceTemperature

        Individual products (no productSet param):
            radar, radarFcst, radarFcstV2, radarFcstV3, temp, tempFcst,
            dewpoint, windSpeed, windSpeedFcst, precip1hrAccum, precip24hr,
            snow24hr, cloudsFcst, sat, sat_goes16, satgoes16ConusIR, etc.

        Returns:
            Dict with "seriesInfo" containing nativeZoom, maxZoom, bounding box,
            and a "series" list of timestamp objects [{ts: unix_timestamp}, ...].
        """
        params = {"apiKey": self.api_key}
        if product_set:
            params["productSet"] = product_set
        return self._get(self._sun_url("/v3/TileServer/series/productSet"), params=params)

    def get_tile_url(
        self,
        product: str,
        timestamp: int,
        x: int,
        y: int,
        zoom: int,
        forecast_timestamp: int = None,
        server_num: int = 0,
    ) -> str:
        """
        Build a tile URL for radar/satellite/weather overlays.

        Tile URL template (from source):
            //api{s}.weather.com/v3/TileServer/tile?product={productKey}&ts={ts}&fts={fts}&xyz={x}:{y}:{z}&apiKey={apiKey}

        Coordinate system: standard Slippy Map (OpenStreetMap) XYZ tiles.

        Args:
            product:            Product key e.g. "radar", "temp", "windSpeed", "precip24hr".
            timestamp:          Unix timestamp from get_tile_series() series list.
            x, y, zoom:         Tile coordinates (Slippy Map / OSM convention).
            forecast_timestamp: fts param (= timestamp for current, or future ts for forecast).
            server_num:         Load balancer 0-3 (api0 through api3).

        Returns:
            String URL for the tile image (PNG).

        Note: Direct tile access may require a browser session cookie for authentication.
        """
        if forecast_timestamp is None:
            forecast_timestamp = timestamp
        server = f"api{server_num}" if server_num > 0 else "api"
        return (
            f"https://{server}.weather.com/v3/TileServer/tile"
            f"?product={product}&ts={timestamp}&fts={forecast_timestamp}"
            f"&xyz={x}:{y}:{zoom}&apiKey={self.api_key}"
        )

    # ─────────────────────────────────────────
    # SECTION 10: Tropical Storm Tracking
    # ─────────────────────────────────────────

    def get_tropical_storms(self, basin: str = "AL") -> Optional[Dict]:
        """
        Get active tropical storm/hurricane data.

        Endpoint: GET /v2/tropical
        Example: https://api.weather.com/v2/tropical?apiKey=...&format=json&basin=AL

        Args:
            basin: Storm basin code:
                   "AL" = Atlantic, "EP" = East Pacific, "CP" = Central Pacific,
                   "WP" = West Pacific, "SP" = South Pacific, "SI" = South Indian,
                   "AS" = Arabian Sea, "BB" = Bay of Bengal, "IO" = North Indian Ocean.

        Returns:
            Dict with storm list, or None if no active storms.
        """
        params = {
            "apiKey": self.api_key,
            "format": "json",
            "basin": basin,
        }
        return self._get(self._sun_url("/v2/tropical"), params=params)

    def get_tropical_storm_track(self, storm_id: str) -> Optional[Dict]:
        """
        Get the track (past positions and forecast cone) for a tropical storm.

        Endpoint: GET /v2/tropical/track
        Example: https://api.weather.com/v2/tropical/track?apiKey=...&format=json&stormId=...

        Args:
            storm_id: Storm identifier from get_tropical_storms().

        Returns:
            Dict with track data.
        """
        params = {
            "apiKey": self.api_key,
            "format": "json",
            "stormId": storm_id,
        }
        return self._get(self._sun_url("/v2/tropical/track"), params=params)

    def get_tropical_storm_current_position(self, storm_id: str) -> Optional[Dict]:
        """
        Get the current position and intensity of a tropical storm.

        Endpoint: GET /v2/tropical/currentposition
        """
        params = {
            "apiKey": self.api_key,
            "format": "json",
            "stormId": storm_id,
        }
        return self._get(self._sun_url("/v2/tropical/currentposition"), params=params)

    def get_tropical_storm_models(self, storm_id: str) -> Optional[Dict]:
        """
        Get model forecast tracks for a tropical storm.

        Endpoint: GET /v3/tropical/models
        """
        params = {
            "apiKey": self.api_key,
            "format": "json",
            "stormId": storm_id,
        }
        return self._get(self._sun_url("/v3/tropical/models"), params=params)

    def get_tropical_storm_details(self, storm_id: str) -> Optional[Dict]:
        """
        Get detailed information about a tropical storm.

        Endpoint: GET /v3/tropical/track/details
        """
        params = {
            "apiKey": self.api_key,
            "format": "json",
            "stormId": storm_id,
        }
        return self._get(self._sun_url("/v3/tropical/track/details"), params=params)

    # ─────────────────────────────────────────
    # SECTION 11: Aggregated / Batch Requests
    # ─────────────────────────────────────────

    def get_aggcommon(
        self,
        products: List[str],
        geocodes: List[str],
    ) -> List[Dict]:
        """
        Fetch multiple data products for multiple locations in a single request.

        Endpoint: GET /v3/aggcommon/{products}
        Example: https://api.weather.com/v3/aggcommon/v3alertsHeadlines;v3-wx-observations-current;v3-location-point?apiKey=...&geocodes=37.77,-122.41;40.75,-74&language=en-US&units=e&format=json

        Common product IDs:
            v3alertsHeadlines             - Weather alert headlines
            v3-wx-observations-current    - Current conditions
            v3-location-point             - Location metadata

        Args:
            products: List of product IDs to fetch (will be joined with ";").
            geocodes: List of "lat,lon" strings (will be joined with ";").

        Returns:
            List of dicts, one per geocode, each keyed by product ID + an "id" field.
        """
        path = "/v3/aggcommon/" + ";".join(products)
        params = {
            "apiKey": self.api_key,
            "geocodes": ";".join(geocodes),
            "language": self.language,
            "units": self.units,
            "format": "json",
        }
        return self._get(self._sun_url(path), params=params)

    # ─────────────────────────────────────────
    # SECTION 12: Convenience Methods
    # ─────────────────────────────────────────

    def get_full_weather_dashboard(self, geocode: str) -> Dict:
        """
        Get a comprehensive weather dashboard for a location in one call.
        Combines current conditions, alerts, and location info.

        Args:
            geocode: "lat,lon" string.

        Returns:
            List with one dict containing v3alertsHeadlines, v3-wx-observations-current,
            v3-location-point.
        """
        return self.get_aggcommon(
            products=["v3alertsHeadlines", "v3-wx-observations-current", "v3-location-point"],
            geocodes=[geocode],
        )

    def get_pws_full_dashboard(self, station_id: str) -> Dict:
        """
        Get all PWS dashboard data (identity, current conditions, today's summary).

        Args:
            station_id: PWS station ID e.g. "KCASANFR1753"

        Returns:
            Dict with keys: identity, current, daily_summary.
        """
        identity = self.get_pws_identity(station_id)
        current = self.get_pws_current(station_id)
        daily = self.get_pws_daily_summary(station_id)
        return {
            "identity": identity,
            "current": current,
            "daily_summary": daily,
        }

    def get_pws_history_range(
        self,
        station_id: str,
        start_date: Union[date, str],
        end_date: Union[date, str],
        interval: str = "daily",
    ) -> List[Dict]:
        """
        Get PWS history over a date range by fetching day-by-day.

        Args:
            station_id:  PWS station ID.
            start_date:  Start date (inclusive).
            end_date:    End date (inclusive).
            interval:    "daily", "hourly", or "all"

        Returns:
            List of daily observation dicts.
        """
        from datetime import timedelta

        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y%m%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y%m%d").date()

        results = []
        current = start_date
        while current <= end_date:
            if interval == "hourly":
                data = self.get_pws_history_hourly(station_id, current)
            elif interval == "all":
                data = self.get_pws_history_all(station_id, current)
            else:
                data = self.get_pws_history_daily(station_id, current)

            obs_key = "observations" if "observations" in data else list(data.keys())[0]
            results.extend(data.get(obs_key, []))
            current += timedelta(days=1)
        return results


# ─────────────────────────────────────────────
# Quick CLI demonstration
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import pprint

    print("=" * 60)
    print("Weather Underground API Client - Demo")
    print("=" * 60)

    client = WundergroundClient(units="e")  # imperial units

    # 1. Search for a location
    print("\n1. Searching for 'San Francisco'...")
    results = client.search_location("San Francisco")
    locs = results.get("location", {})
    addresses = locs.get("address", [])
    print(f"   Found {len(addresses)} results. First: {addresses[0] if addresses else 'none'}")

    # 2. Get current conditions
    print("\n2. Current conditions in NYC (40.71, -74.01)...")
    conditions = client.get_current_conditions(geocode="40.71,-74.01")
    print(f"   Temperature: {conditions.get('temperature')}°F")
    print(f"   Conditions:  {conditions.get('wxPhraseLong')}")
    print(f"   Humidity:    {conditions.get('relativeHumidity')}%")
    print(f"   Wind:        {conditions.get('windSpeed')} mph {conditions.get('windDirectionCardinal')}")

    # 3. 5-day forecast
    print("\n3. 5-day forecast for NYC...")
    forecast = client.get_forecast_daily("40.71,-74.01", days=5)
    for i, (day, hi, lo, narr) in enumerate(zip(
        forecast.get("dayOfWeek", [])[:5],
        forecast.get("temperatureMax", [None]*5),
        forecast.get("temperatureMin", [None]*5),
        forecast.get("narrative", [""] * 5),
    )):
        print(f"   {day}: High {hi}°F / Low {lo}°F - {narr[:60]}...")

    # 4. PWS identity + current conditions
    STATION = "KCASANFR1753"
    print(f"\n4. PWS station {STATION} identity...")
    identity = client.get_pws_identity(STATION)
    print(f"   Name:      {identity.get('name')}")
    print(f"   Location:  {identity.get('city')}, {identity.get('state')}")
    print(f"   Elevation: {identity.get('elevation')} ft")
    print(f"   Hardware:  {identity.get('stationType')}")

    pws_obs = client.get_pws_current(STATION)
    obs = pws_obs.get("observations", [{}])[0]
    imperial = obs.get("imperial", {})
    print(f"   Current temp: {imperial.get('temp')}°F, Pressure: {imperial.get('pressure')} inHg")

    # 5. Nearby PWS stations
    print("\n5. Nearby PWS stations to downtown NYC...")
    nearby = client.get_nearby_pws("40.71,-74.01")
    loc = nearby.get("location", {})
    station_ids = loc.get("stationId", [])[:5]
    station_names = loc.get("stationName", [])[:5]
    for sid, sname in zip(station_ids, station_names):
        print(f"   {sid}: {sname}")

    # 6. Radar tile series
    print("\n6. Latest radar timestamps...")
    series = client.get_tile_series("wuRadar")
    radar_conus = series.get("seriesInfo", {}).get("wuRadarConus", {})
    latest_frames = radar_conus.get("series", [])[:3]
    for frame in latest_frames:
        ts = frame.get("ts")
        dt = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")
        print(f"   {dt} (ts={ts})")

    # 7. Astronomy
    print("\n7. Sunrise/Sunset for NYC today...")
    astro = client.get_astronomy("40.71,-74.01", days=1)
    today = astro.get("astroData", [{}])[0]
    sun = today.get("sun", {}).get("riseSet", {})
    print(f"   Sunrise: {sun.get('riseLocal', 'N/A')}")
    print(f"   Sunset:  {sun.get('setLocal', 'N/A')}")

    print("\nDemo complete!")
