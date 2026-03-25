"""
World Weather Online (WWO) - Reverse-Engineered Python Client
=============================================================

This client wraps both the internal AJAX endpoints used by the
worldweatheronline.com website AND the public premium REST API
(api.worldweatheronline.com/premium/v1/).

The internal (scraper) endpoints require no API key but return HTML fragments.
The premium API endpoints require a key (available via 30-day free trial at
https://www.worldweatheronline.com/weather-api/signup.aspx) and return
structured JSON or XML.

Architecture discovered via network traffic analysis:
  Base website:  https://www.worldweatheronline.com
  Premium API:   https://api.worldweatheronline.com/premium/v1/
  CDN:           https://cdn.worldweatheronline.com/

Internal AJAX endpoints (ASP.NET WebMethod pattern: page.aspx/MethodName):
  POST /v2/weather.aspx/load_wxdn       — 14-day short-term forecast table
  POST /v2/weather.aspx/load_calendar   — 14-day calendar summary (daily)
  POST /v2/weather.aspx/loaduvindex     — UV index for coming days
  POST /search-weather.aspx/load_search — Location search (city/sport venues)
  POST /v2/root.aspx/Search             — Root city search (by area ID)
  POST /v2/region.aspx/Search           — Region-scoped city search
  POST /Default.aspx/load_hp_sports     — Homepage sports weather widget
  POST /v2/favourites.aspx/DeleteFav    — Delete a favourite location (auth)
  POST /v2/change-units.aspx/UpdateUnits— Update display unit preferences

Public premium API endpoints (require ?key=<YOUR_API_KEY>):
  GET  /premium/v1/weather.ashx         — Current + 14-day forecast
  GET  /premium/v1/past-weather.ashx    — Historical weather (from 2008-07-01)
  GET  /premium/v1/marine.ashx          — Marine/sea weather (tide, swell, etc.)
  GET  /premium/v1/ski.ashx             — Mountain & ski resort weather
  GET  /premium/v1/search.ashx          — Location autocomplete search
  GET  /premium/v1/tz.ashx              — Time zone lookup
  GET  /premium/v1/astronomy.ashx       — Sunrise/sunset, moon data

Web (scraper) endpoints — navigate full HTML pages then POST to .aspx/Method:
  GET  /v2/weather.aspx?q=<location>          — Weather forecast page
  GET  /<slug>-weather-history/<region>/<cc>.aspx — Historical weather page
  POST <history_page_url>  (with form data)   — Submit date for historical data
  GET  /<slug>-weather/<region>/<cc>.aspx?day=20&tp=1 — Hourly weather page
"""

from __future__ import annotations

import re
import time
import urllib.parse
from datetime import date, datetime
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests import Session

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.worldweatheronline.com"
API_BASE = "https://api.worldweatheronline.com/premium/v1"

# Unit mapping constants (as used internally by WWO hidden fields)
# Temperature
TEMP_CELSIUS    = 1
TEMP_FAHRENHEIT = 2

# Precipitation
PRECIP_MM     = 1
PRECIP_INCHES = 2

# Pressure
PRESSURE_MB     = 1  # also written as 2 in some pages
PRESSURE_INCHES = 2

# Wind speed
WIND_KMPH    = 1
WIND_MPH     = 2
WIND_KNOTS   = 3
WIND_BEAUFORT = 4
WIND_MS      = 5

# Visibility
VIS_KM    = 1
VIS_MILES = 2

# WWO weather condition image codes (partial list)
# Full icon URL: https://cdn.worldweatheronline.com/images/weather/small/{code}_day_sm.png
# or replace 'small' with 'large' and '_sm' with '_lg'
WEATHER_ICONS_BASE = "https://cdn.worldweatheronline.com/images/weather"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_AJAX_HEADERS = {
    "User-Agent": _DEFAULT_HEADERS["User-Agent"],
    "Content-Type": "application/json; charset=utf-8",
    "Content-Encoding": "gzip",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_hidden_fields(html: str) -> Dict[str, str]:
    """Extract all hidden <input> field values from HTML."""
    fields: Dict[str, str] = {}
    for m in re.finditer(
        r'<input[^>]+type=["\']hidden["\'][^>]*>',
        html,
        re.IGNORECASE,
    ):
        tag = m.group(0)
        id_m  = re.search(r'\bid=["\']([^"\']+)["\']',    tag)
        val_m = re.search(r'\bvalue=["\']([^"\']*)["\']', tag)
        if id_m and val_m:
            fields[id_m.group(1)] = val_m.group(1)
    return fields


def _build_forecast_payload(hidden: Dict[str, str]) -> str:
    """Build the JSON body for weather.aspx/load_wxdn and /load_calendar."""
    return "{{ 'd': '{}' }}".format(
        hidden.get("ctl00_MainContentHolder_hd14dayfx", "")
    )


def _build_currentwx_payload(hidden: Dict[str, str]) -> str:
    """Build the JSON body for weather.aspx/loaduvindex."""
    return "{{ 'd': '{}' }}".format(
        hidden.get("ctl00_MainContentHolder_hdcurrentwx", "")
    )


# ---------------------------------------------------------------------------
# Session management — shared cookies / unit preferences
# ---------------------------------------------------------------------------

class _WWOSession:
    """Thin wrapper around requests.Session that handles cookie initialisation."""

    def __init__(self) -> None:
        self._session = Session()
        self._session.headers.update(_DEFAULT_HEADERS)
        self._initialized = False

    def _ensure_init(self) -> None:
        if not self._initialized:
            # Hit the homepage to pick up the session cookies
            self._session.get(BASE_URL + "/", timeout=15)
            self._initialized = True

    def get(self, url: str, **kwargs) -> requests.Response:
        self._ensure_init()
        kwargs.setdefault("timeout", 20)
        return self._session.get(url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        self._ensure_init()
        kwargs.setdefault("timeout", 20)
        return self._session.post(url, **kwargs)

    def set_units(
        self,
        temp: int = TEMP_CELSIUS,
        precip: int = PRECIP_MM,
        pressure: int = PRESSURE_MB,
        wind: int = WIND_KMPH,
        visibility: int = VIS_KM,
    ) -> bool:
        """
        Update display units (sets a server-side cookie).

        The server uses integer codes:
          temp:       1=°C, 2=°F
          precip:     1=mm, 2=in
          pressure:   1=mb, 2=in
          wind:       1=kmph, 2=mph, 3=knots, 4=beaufort, 5=m/s
          visibility: 1=km, 2=miles
        """
        self._ensure_init()
        body = (
            "{{ 't': {}, 'p': {}, 'ps': {}, 'w': {}, 'v': {} }}"
            .format(temp, precip, pressure, wind, visibility)
        )
        resp = self._session.post(
            BASE_URL + "/v2/change-units.aspx/UpdateUnits",
            headers=_AJAX_HEADERS,
            data=body,
            timeout=15,
        )
        return resp.ok


# ---------------------------------------------------------------------------
# Location resolution
# ---------------------------------------------------------------------------

class LocationResult:
    """A single result returned from the location search."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.url: Optional[str] = None
        self.name: Optional[str] = None
        self.area_id: Optional[str] = None

        url_m = re.search(
            r'href=["\']([^"\']*worldweatheronline\.com[^"\']*\.aspx)["\']', raw
        )
        if url_m:
            self.url = url_m.group(1)
            slug_m = re.search(r'/([^/]+\.aspx)', self.url)
            if slug_m:
                self.name = slug_m.group(1).replace("-", " ").replace(".aspx", "")

    def __repr__(self) -> str:
        return f"<LocationResult name={self.name!r} url={self.url!r}>"


def search_locations(query: str, session: Optional[_WWOSession] = None) -> List[str]:
    """
    Search for locations by name.

    Returns a list of matching location URLs from worldweatheronline.com.
    These can then be passed to the weather client methods.

    Example:
        urls = search_locations("London")
        # ['https://www.worldweatheronline.com/london-weather/city-of-london-greater-london/gb.aspx', ...]
    """
    sess = session or _WWOSession()

    # Step 1: get the search page to obtain the hidden query field
    resp = sess.get(
        BASE_URL + "/search-weather.aspx",
        params={"q": query},
    )
    resp.raise_for_status()

    # Step 2: call the lazy-load search AJAX endpoint
    ajax_resp = sess.post(
        BASE_URL + "/search-weather.aspx/load_search",
        headers=_AJAX_HEADERS,
        data=f"{{ 'query': '{query}' }}",
    )
    ajax_resp.raise_for_status()

    data = ajax_resp.json()
    html = data.get("d", "")
    urls = re.findall(
        r'href=["\']([^"\']*worldweatheronline\.com[^"\']*\.aspx)["\']', html
    )
    return list(dict.fromkeys(urls))  # deduplicate while preserving order


# ---------------------------------------------------------------------------
# Weather page loader — resolves any query string to hidden-field dict
# ---------------------------------------------------------------------------

class _PageData:
    """
    Holds the parsed hidden fields from a WWO weather page.

    The hidden field ``ctl00_MainContentHolder_hd14dayfx`` encodes:
      date:areaid:name:tz_offset:lang:bool:t:p:ps:w:v:url

    The hidden field ``ctl00_MainContentHolder_hdcurrentwx`` encodes:
      datetime@areaid@name@tz_offset@lang@bool@t@p@ps@w@v@lat@lon
    """

    def __init__(
        self,
        hidden: Dict[str, str],
        source_url: str,
        raw_html: str,
    ) -> None:
        self.hidden = hidden
        self.source_url = source_url
        self.raw_html = raw_html

    @property
    def area_id(self) -> Optional[str]:
        return self.hidden.get("ctl00_areaid")

    @property
    def lat(self) -> Optional[str]:
        return self.hidden.get("ctl00_hdlat")

    @property
    def lon(self) -> Optional[str]:
        return self.hidden.get("ctl00_hdlon")

    @property
    def hd14dayfx(self) -> str:
        return self.hidden.get("ctl00_MainContentHolder_hd14dayfx", "")

    @property
    def hdcurrentwx(self) -> str:
        return self.hidden.get("ctl00_MainContentHolder_hdcurrentwx", "")

    @property
    def hdchartdata(self) -> str:
        return self.hidden.get("ctl00_MainContentHolder_hdchartdata", "")

    def forecast_body(self) -> str:
        return f"{{ 'd': '{self.hd14dayfx}' }}"

    def currentwx_body(self) -> str:
        return f"{{ 'd': '{self.hdcurrentwx}' }}"


def _load_weather_page(
    query: str,
    sess: _WWOSession,
    tp: Optional[int] = None,
    day: Optional[int] = None,
) -> _PageData:
    """
    Load a weather page for the given query and return parsed hidden fields.

    ``query`` can be:
      - A city/town name:   "London"
      - A lat,lon pair:     "51.5,-0.1"
      - A US zip code:      "10001"
      - A UK postcode:      "SW1A 1AA"
      - A direct page URL:  "https://www.worldweatheronline.com/..."
    """
    if query.startswith("http"):
        url = query
        params: Dict[str, Any] = {}
    else:
        url = BASE_URL + "/v2/weather.aspx"
        params = {"q": query}

    if tp is not None:
        params["tp"] = tp
    if day is not None:
        params["day"] = day

    resp = sess.get(url, params=params)
    resp.raise_for_status()
    hidden = _extract_hidden_fields(resp.text)
    return _PageData(hidden, resp.url, resp.text)


# ---------------------------------------------------------------------------
# Main public client
# ---------------------------------------------------------------------------

class WorldWeatherOnlineClient:
    """
    Client for World Weather Online (worldweatheronline.com).

    Two tiers of API are exposed:
      1. **Internal scraper API** — no key required, returns HTML fragments
         that are stripped to plain text.
      2. **Premium REST API** — requires an API key; returns structured JSON.

    Quick-start (scraper, no key required):
        >>> client = WorldWeatherOnlineClient()
        >>> forecast = client.get_forecast("London")
        >>> print(forecast["calendar_text"])

    Quick-start (premium API):
        >>> client = WorldWeatherOnlineClient(api_key="YOUR_API_KEY")
        >>> data = client.api_forecast("London", num_of_days=3, tp=1)
        >>> print(data)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        temp_unit: int = TEMP_CELSIUS,
        wind_unit: int = WIND_KMPH,
        precip_unit: int = PRECIP_MM,
        pressure_unit: int = PRESSURE_MB,
        vis_unit: int = VIS_KM,
        request_delay: float = 0.5,
    ) -> None:
        """
        Parameters
        ----------
        api_key:
            WWO premium API key (optional; only needed for premium API methods).
        temp_unit, wind_unit, precip_unit, pressure_unit, vis_unit:
            Unit preferences for scraper-based calls.
        request_delay:
            Seconds to wait between scraper requests (be polite).
        """
        self.api_key = api_key
        self.units = {
            "temp":     temp_unit,
            "precip":   precip_unit,
            "pressure": pressure_unit,
            "wind":     wind_unit,
            "vis":      vis_unit,
        }
        self._request_delay = request_delay
        self._sess = _WWOSession()
        self._last_request: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request = time.time()

    def _ajax_post(self, path: str, body: str) -> Dict[str, Any]:
        """POST to an internal ASP.NET WebMethod endpoint."""
        self._throttle()
        resp = self._sess.post(
            BASE_URL + path,
            headers=_AJAX_HEADERS,
            data=body,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Scraper / internal API
    # ------------------------------------------------------------------

    def get_forecast(
        self,
        query: str,
        *,
        include_uv: bool = True,
        include_calendar: bool = True,
        include_short_term: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieve the 14-day weather forecast for a location.

        This uses the internal AJAX endpoints used by the website:
          - /v2/weather.aspx/load_calendar  (daily summary, 14 days)
          - /v2/weather.aspx/load_wxdn      (short-term 4-part-day breakdown)
          - /v2/weather.aspx/loaduvindex    (UV index per day)

        Parameters
        ----------
        query:
            Location — city name, "lat,lon", postcode, or full page URL.

        Returns
        -------
        dict with keys:
          page_url        — resolved URL of the weather page
          lat, lon        — geographic coordinates
          area_id         — internal area identifier
          calendar_html   — raw HTML of the 14-day calendar (if requested)
          calendar_text   — plain-text version of the calendar
          short_term_html — raw HTML of the short-term breakdown (if requested)
          short_term_text — plain-text version
          uv_html         — raw HTML of the UV index section (if requested)
          uv_text         — plain-text version
        """
        self._throttle()
        page = _load_weather_page(query, self._sess)

        result: Dict[str, Any] = {
            "page_url": page.source_url,
            "lat":      page.lat,
            "lon":      page.lon,
            "area_id":  page.area_id,
        }

        if include_calendar:
            data = self._ajax_post(
                "/v2/weather.aspx/load_calendar",
                page.forecast_body(),
            )
            result["calendar_html"] = data.get("d", "")
            result["calendar_text"] = _strip_html(result["calendar_html"])

        if include_short_term:
            data = self._ajax_post(
                "/v2/weather.aspx/load_wxdn",
                page.forecast_body(),
            )
            result["short_term_html"] = data.get("d", "")
            result["short_term_text"] = _strip_html(result["short_term_html"])

        if include_uv:
            data = self._ajax_post(
                "/v2/weather.aspx/loaduvindex",
                page.currentwx_body(),
            )
            result["uv_html"] = data.get("d", "")
            result["uv_text"] = _strip_html(result["uv_html"])

        return result

    def get_hourly(
        self,
        query: str,
        *,
        interval_hours: int = 1,
        days_ahead: int = 20,
    ) -> Dict[str, Any]:
        """
        Retrieve hourly weather data for a location.

        Parameters
        ----------
        query:
            Location (city name, "lat,lon", postcode, or full URL).
        interval_hours:
            1 = hourly, 3 = 3-hourly, 6 = 6-hourly.
        days_ahead:
            How many days of hourly data to retrieve (max ~14).

        Returns
        -------
        dict with keys:
          page_url  — resolved page URL
          lat, lon
          area_id
          html      — raw page HTML
          tables    — list of parsed hourly weather tables (plain text)
        """
        self._throttle()
        page = _load_weather_page(
            query, self._sess, tp=interval_hours, day=days_ahead
        )
        # Extract weather tables
        tables = []
        content = page.raw_html
        start = 0
        while True:
            t_start = content.find("<table", start)
            if t_start == -1:
                break
            t_end = content.find("</table>", t_start)
            if t_end == -1:
                break
            table_html = content[t_start : t_end + 8]
            table_text = _strip_html(table_html)
            if len(table_text) > 50:
                tables.append(table_text)
            start = t_end + 1

        return {
            "page_url": page.source_url,
            "lat":      page.lat,
            "lon":      page.lon,
            "area_id":  page.area_id,
            "tables":   tables,
            "html":     page.raw_html,
        }

    def get_historical(
        self,
        query: str,
        target_date: Optional[str] = None,
        *,
        country_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve historical weather data for a date (back to 2008-07-01).

        Parameters
        ----------
        query:
            Either a full URL to a *-weather-history page, OR a city name.
            When using a city name you must also supply ``country_code``.
        target_date:
            Date string "YYYY-MM-DD" (defaults to yesterday).
        country_code:
            Two-letter ISO country code (e.g. "gb", "us") required when
            ``query`` is a plain city name.

        Returns
        -------
        dict with keys:
          page_url         — URL of the history page fetched
          target_date      — date queried
          lat, lon         — coordinates
          area_id
          history_html     — raw HTML of the history section
          history_text     — plain text

        Usage
        -----
        # Via direct page URL (recommended):
        data = client.get_historical(
            "https://www.worldweatheronline.com/london-weather-history/"
            "city-of-london-greater-london/gb.aspx",
            "2024-06-15",
        )

        # Via city name:
        data = client.get_historical("london", "2024-06-15", country_code="gb")
        """
        if target_date is None:
            from datetime import timedelta
            target_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Resolve the history page URL
        if query.startswith("http"):
            history_url = query
        else:
            # Build a slug-based URL
            slug = query.lower().replace(" ", "-")
            if country_code:
                # We need the full region path; try guessing from search results
                urls = search_locations(query, self._sess)
                history_url = None
                for u in urls:
                    if "weather-history" in u:
                        history_url = u
                        break
                if not history_url:
                    # Derive from first forecast URL by inserting "-history"
                    for u in urls:
                        if "weather/" in u or "weather-" in u.split("/")[-2]:
                            # Convert .../london-weather/region/cc.aspx
                            # to .../london-weather-history/region/cc.aspx
                            history_url = re.sub(
                                r"(/[^/]+-weather)/",
                                r"\1-history/",
                                u,
                            )
                            break
                if not history_url:
                    raise ValueError(
                        f"Could not resolve history page URL for query={query!r}. "
                        "Try passing a full URL directly."
                    )
            else:
                raise ValueError(
                    "Supply country_code when using a plain city name, "
                    "or supply the full history page URL."
                )

        # Load the history page to get VIEWSTATE
        self._throttle()
        resp = self._sess.get(history_url)
        resp.raise_for_status()
        hidden = _extract_hidden_fields(resp.text)
        lat = hidden.get("ctl00_hdlat")
        lon = hidden.get("ctl00_hdlon")
        area_id = hidden.get("ctl00_areaid")

        # POST the form with the requested date
        self._throttle()
        post_data = {
            "__VIEWSTATE":           hidden.get("__VIEWSTATE", ""),
            "__VIEWSTATEGENERATOR":  hidden.get("__VIEWSTATEGENERATOR", ""),
            "ctl00$MainContentHolder$txtPastDate": target_date,
            "ctl00$MainContentHolder$butShowPastWeather": "Get Weather",
        }
        resp2 = self._sess._session.post(
            history_url,
            data=post_data,
            headers={
                "User-Agent":   _DEFAULT_HEADERS["User-Agent"],
                "Referer":      history_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=20,
        )
        resp2.raise_for_status()

        # Extract the history section from response
        html = resp2.text
        idx  = html.find("Weather History")
        if idx == -1:
            history_html = html
        else:
            end_idx = html.find("</div>", idx + 10000)
            history_html = html[idx : end_idx + 6] if end_idx != -1 else html[idx:]

        return {
            "page_url":     history_url,
            "target_date":  target_date,
            "lat":          lat,
            "lon":          lon,
            "area_id":      area_id,
            "history_html": history_html,
            "history_text": _strip_html(history_html),
        }

    def get_ski_forecast(self, query: str) -> Dict[str, Any]:
        """
        Retrieve the ski/mountain weather forecast for a location.

        WWO ski resort pages use the same endpoint structure as city weather
        pages but set a sport-type flag of 1 in the hidden ``hd14dayfx`` field.

        Parameters
        ----------
        query:
            Either a ski resort city name (e.g. "Chamonix") or a full URL to
            a ski weather page on worldweatheronline.com.

        Returns
        -------
        Same structure as ``get_forecast()``.
        """
        # If it's not a URL, search for a ski page
        if not query.startswith("http"):
            urls = search_locations(query + " ski", self._sess)
            ski_urls = [u for u in urls if "ski" in u.lower()]
            if not ski_urls:
                ski_urls = urls
            if ski_urls:
                query = ski_urls[0]

        return self.get_forecast(query)

    def get_marine_forecast(
        self,
        lat: float,
        lon: float,
    ) -> Dict[str, Any]:
        """
        Retrieve marine/coastal weather for a geographic coordinate.

        The site resolves coordinates to the nearest land or marine area.
        Coordinates far at sea may resolve to the nearest coastal city.

        Parameters
        ----------
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

        Returns
        -------
        Same structure as ``get_forecast()``.
        """
        return self.get_forecast(f"{lat},{lon}")

    def search(self, query: str) -> List[str]:
        """
        Search for matching location URLs on worldweatheronline.com.

        Returns a list of page URLs that can be used as input to other methods.
        """
        return search_locations(query, self._sess)

    # ------------------------------------------------------------------
    # Premium REST API (requires API key)
    # ------------------------------------------------------------------

    def _api_get(
        self,
        endpoint: str,
        params: Dict[str, Any],
        *,
        fmt: str = "json",
    ) -> Any:
        """Make a request to the premium REST API."""
        if not self.api_key:
            raise RuntimeError(
                "API key required. Sign up at "
                "https://www.worldweatheronline.com/weather-api/signup.aspx"
            )
        params = {k: v for k, v in params.items() if v is not None}
        params["key"]    = self.api_key
        params["format"] = fmt
        self._throttle()
        resp = self._sess.get(
            f"{API_BASE}/{endpoint}.ashx",
            params=params,
        )
        resp.raise_for_status()
        if fmt == "json":
            return resp.json()
        return resp.text

    def api_forecast(
        self,
        q: str,
        *,
        num_of_days: int = 5,
        tp: Optional[int] = None,
        fx: int = 1,
        cc: int = 1,
        mca: int = 0,
        fx24: int = 0,
        includelocation: int = 1,
        show_comments: int = 0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/weather.ashx

        Retrieve current conditions and up-to-14-day forecast.

        Parameters
        ----------
        q:
            Location query: city name, "lat,lon", postcode, or ip address.
        num_of_days:
            Number of forecast days (1–14).
        tp:
            Time period for hourly forecast:
              None  = daily only
              1     = 1-hour intervals
              3     = 3-hour intervals
              6     = 6-hour intervals
              12    = 12-hour intervals
              24    = daily only (alias)
        fx:
            Include forecast (1=yes, 0=no).
        cc:
            Include current conditions (1=yes, 0=no).
        mca:
            Include monthly climate averages (1=yes, 0=no).
        fx24:
            Include 24-hour wind gust forecast (1=yes, 0=no).
        includelocation:
            Include location info in response (1=yes, 0=no).
        show_comments:
            Include weather description comments (1=yes, 0=no).
        extra:
            Any additional parameters to pass to the API.

        Returns
        -------
        Parsed JSON response (dict).
        """
        params: Dict[str, Any] = {
            "q":               q,
            "num_of_days":     num_of_days,
            "fx":              fx,
            "cc":              cc,
            "mca":             mca,
            "fx24":            fx24,
            "includelocation": includelocation,
            "showComments":    show_comments,
        }
        if tp is not None:
            params["tp"] = tp
        if extra:
            params.update(extra)
        return self._api_get("weather", params)

    def api_historical(
        self,
        q: str,
        date: str,
        *,
        end_date: Optional[str] = None,
        tp: Optional[int] = None,
        includelocation: int = 1,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/past-weather.ashx

        Historical weather data from 2008-07-01 to present.

        Parameters
        ----------
        q:
            Location query.
        date:
            Start date "YYYY-MM-DD" (minimum: 2008-07-01).
        end_date:
            End date "YYYY-MM-DD" (defaults to ``date``).
        tp:
            Time period: 1, 3, 6, 12, or 24 (hours).
        includelocation:
            Include location in response.
        extra:
            Additional query params.

        Returns
        -------
        Parsed JSON response.
        """
        params: Dict[str, Any] = {
            "q":               q,
            "date":            date,
            "includelocation": includelocation,
        }
        if end_date:
            params["enddate"] = end_date
        if tp is not None:
            params["tp"] = tp
        if extra:
            params.update(extra)
        return self._api_get("past-weather", params)

    def api_marine(
        self,
        q: str,
        *,
        tp: Optional[int] = None,
        tide: int = 1,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/marine.ashx

        Marine/sea weather: wave height, swell, tide, sea temperature.

        Parameters
        ----------
        q:
            "lat,lon" coordinates (e.g. "51.5,-0.1") for a sea location.
        tp:
            Time period (hours): 1, 3, 6, 12, or 24.
        tide:
            Include tide data (1=yes, 0=no).
        extra:
            Additional query params.

        Returns
        -------
        Parsed JSON response.
        """
        params: Dict[str, Any] = {
            "q":    q,
            "tide": tide,
        }
        if tp is not None:
            params["tp"] = tp
        if extra:
            params.update(extra)
        return self._api_get("marine", params)

    def api_ski(
        self,
        q: str,
        *,
        num_of_days: int = 7,
        tp: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/ski.ashx

        Mountain and ski resort weather (top, middle, bottom elevations).

        Parameters
        ----------
        q:
            Location (resort name or "lat,lon").
        num_of_days:
            1–7 days.
        tp:
            Time period (hours).

        Returns
        -------
        Parsed JSON response.
        """
        params: Dict[str, Any] = {
            "q":           q,
            "num_of_days": num_of_days,
        }
        if tp is not None:
            params["tp"] = tp
        if extra:
            params.update(extra)
        return self._api_get("ski", params)

    def api_search(
        self,
        q: str,
        *,
        num_of_results: int = 10,
        timezone: int = 1,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/search.ashx

        Location autocomplete / search API.

        Returns up to 200 matching locations with name, lat, lon, country,
        region, population, and (optionally) timezone data.

        Parameters
        ----------
        q:
            Search string (city name, postcode, zip code).
        num_of_results:
            Maximum results (1–200).
        timezone:
            Include timezone offset (1=yes, 0=no).

        Returns
        -------
        Parsed JSON response.
        """
        params: Dict[str, Any] = {
            "q":              q,
            "num_of_results": num_of_results,
            "timezone":       timezone,
        }
        if extra:
            params.update(extra)
        return self._api_get("search", params)

    def api_timezone(
        self,
        q: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/tz.ashx

        Time zone lookup — returns local time and UTC offset for a location.

        Parameters
        ----------
        q:
            Location query.

        Returns
        -------
        Parsed JSON response.
        """
        params: Dict[str, Any] = {"q": q}
        if extra:
            params.update(extra)
        return self._api_get("tz", params)

    def api_astronomy(
        self,
        q: str,
        date: str,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        GET /premium/v1/astronomy.ashx

        Sunrise, sunset, moonrise, moonset, moon phase.

        Parameters
        ----------
        q:
            Location query.
        date:
            Date string "YYYY-MM-DD".

        Returns
        -------
        Parsed JSON response.
        """
        params: Dict[str, Any] = {"q": q, "date": date}
        if extra:
            params.update(extra)
        return self._api_get("astronomy", params)


# ---------------------------------------------------------------------------
# Convenience functions (no-client, single-call wrappers)
# ---------------------------------------------------------------------------

def get_current_forecast(location: str) -> Dict[str, Any]:
    """One-shot convenience wrapper: fetch forecast without creating a client."""
    return WorldWeatherOnlineClient().get_forecast(location)


def get_historical_weather(
    history_page_url: str,
    target_date: str,
) -> Dict[str, Any]:
    """One-shot convenience wrapper: fetch historical weather."""
    return WorldWeatherOnlineClient().get_historical(history_page_url, target_date)


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    print("=== World Weather Online Client Demo ===\n")

    client = WorldWeatherOnlineClient()

    # --- Demo 1: Location search ---
    print("1) Searching for 'Paris'...")
    urls = client.search("Paris")
    print(f"   Found {len(urls)} results. First 3:")
    for u in urls[:3]:
        print(f"     {u}")

    print()

    # --- Demo 2: 14-day forecast ---
    print("2) Fetching 14-day forecast for London...")
    try:
        forecast = client.get_forecast("London", include_uv=True)
        print(f"   Page: {forecast['page_url']}")
        print(f"   Coords: lat={forecast['lat']}, lon={forecast['lon']}")
        print(f"   Area ID: {forecast['area_id']}")
        print(f"\n   UV Index:\n   {forecast.get('uv_text','N/A')}")
        print(f"\n   14-day Calendar (first 500 chars):")
        print(f"   {forecast.get('calendar_text','')[:500]}")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # --- Demo 3: Hourly weather ---
    print("3) Fetching hourly weather for London (first 2 tables)...")
    try:
        hourly = client.get_hourly("London")
        tables = hourly.get("tables", [])
        for i, t in enumerate(tables[:2]):
            print(f"   Table {i+1}: {t[:200]}")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # --- Demo 4: Historical weather ---
    print("4) Fetching historical weather for London on 2024-06-15...")
    try:
        hist = client.get_historical(
            "https://www.worldweatheronline.com/"
            "london-weather-history/city-of-london-greater-london/gb.aspx",
            "2024-06-15",
        )
        print(f"   Date: {hist['target_date']}")
        print(f"   History (first 500 chars):")
        print(f"   {hist.get('history_text','')[:500]}")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # --- Demo 5: Ski forecast ---
    print("5) Fetching ski forecast (searching 'ski Norway')...")
    try:
        ski = client.get_ski_forecast(
            "https://www.worldweatheronline.com/ski-weather/akershus/no.aspx"
        )
        print(f"   Page: {ski['page_url']}")
        print(f"   Short-term forecast (first 500 chars):")
        print(f"   {ski.get('short_term_text','')[:500]}")
    except Exception as e:
        print(f"   Error: {e}")

    print()

    # --- Demo 6: Marine weather ---
    print("6) Fetching weather for marine coordinates (English Channel 50.9,-1.4)...")
    try:
        marine = client.get_marine_forecast(50.9, -1.4)
        print(f"   Page: {marine['page_url']}")
        print(f"   Calendar (first 300 chars):")
        print(f"   {marine.get('calendar_text','')[:300]}")
    except Exception as e:
        print(f"   Error: {e}")

    print()
    print("=== Premium API Demo (requires API key) ===")
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    if api_key:
        premium = WorldWeatherOnlineClient(api_key=api_key)
        print("7) Premium: current + 3-day forecast for Tokyo...")
        try:
            data = premium.api_forecast("Tokyo", num_of_days=3, tp=3)
            print(json.dumps(data, indent=2)[:1000])
        except Exception as e:
            print(f"   Error: {e}")

        print("\n8) Premium: historical weather for New York 2024-07-04...")
        try:
            data = premium.api_historical("New York", "2024-07-04", tp=3)
            print(json.dumps(data, indent=2)[:1000])
        except Exception as e:
            print(f"   Error: {e}")

        print("\n9) Premium: marine weather at 51.5, 1.5 (Thames Estuary)...")
        try:
            data = premium.api_marine("51.5,1.5", tp=3, tide=1)
            print(json.dumps(data, indent=2)[:1000])
        except Exception as e:
            print(f"   Error: {e}")

        print("\n10) Premium: ski weather for Chamonix...")
        try:
            data = premium.api_ski("Chamonix", num_of_days=5)
            print(json.dumps(data, indent=2)[:1000])
        except Exception as e:
            print(f"   Error: {e}")
    else:
        print("  (Pass your API key as argv[1] to test premium endpoints)")

    print("\nDone.")
