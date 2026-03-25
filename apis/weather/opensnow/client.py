"""
OpenSnow API Python Client
===========================
Reverse-engineered client for OpenSnow's internal API.

API Base URL: https://opensnow.com/mtn
API Key: 60600760edf827a75df71f712b71e3f3 (public frontend key)
Version: v=1
User-Agent: opensnow-web-2

The client wraps both:
1. The /mtn REST API (used by the browser SPA)
2. The /_payload.json endpoints (Nuxt 3 SSR hydration payloads)

Usage:
    client = OpenSnowClient()
    location = client.get_location("vail")
    snow_summary = client.get_snow_summary("vail")
    results = client.search_locations("mammoth")
    seed = client.get_meta_seed()

"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Any

# ─── Configuration ────────────────────────────────────────────────────────────

API_BASE_URL = "https://opensnow.com/mtn"
PAYLOAD_BASE_URL = "https://opensnow.com"
API_KEY = "60600760edf827a75df71f712b71e3f3"
API_VERSION = "1"
USER_AGENT = "opensnow-web-2"

# ─── Nuxt RevJSON Decoder ─────────────────────────────────────────────────────

def decode_revjson(flat_array: list, idx: Any, seen: Optional[set] = None, depth: int = 0) -> Any:
    """
    Decode Nuxt 3's RevJSON format.

    Nuxt 3 serializes hydration data as a flat array where values
    reference other array indices to avoid duplication. This function
    recursively resolves those references.

    The encoding rules are:
    - Dict field values and list items are always slot indices (integers pointing into flat_array)
    - Slot values that are int/float/str/bool/None are the FINAL value (not further dereferenced)
    - Slot values that are dict/list have their entries recursively dereferenced
    - Special case: ["ShallowReactive", n] unwraps to slot n

    Args:
        flat_array: The full RevJSON array
        idx: Current value — either a slot index (int pointing into flat_array)
             or a compound value (dict/list whose entries are slot indices)
        seen: Set of already-visited slot indices (prevents infinite loops)
        depth: Recursion depth guard

    Returns:
        The fully resolved Python value
    """
    if seen is None:
        seen = set()
    if depth > 30:
        return None

    # Dict: values are slot indices, recurse into each
    if isinstance(idx, dict):
        return {k: decode_revjson(flat_array, v, seen.copy(), depth + 1) for k, v in idx.items()}

    # List: items are slot indices, UNLESS it's a ShallowReactive wrapper
    if isinstance(idx, list):
        if len(idx) >= 2 and idx[0] == "ShallowReactive":
            return decode_revjson(flat_array, idx[1], seen.copy(), depth + 1)
        return [decode_revjson(flat_array, item, seen.copy(), depth + 1) for item in idx]

    # Integer: this is a slot index — look up the slot value
    if isinstance(idx, int) and not isinstance(idx, bool):
        if idx in seen or idx < 0 or idx >= len(flat_array):
            return None
        seen_copy = seen | {idx}
        val = flat_array[idx]

        # Slot value is a primitive -> this IS the final value, return directly
        if val is None or isinstance(val, (bool, str, float)):
            return val
        # Slot value is an integer primitive -> return it directly (NOT a further index)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        # Slot value is a dict or list -> recurse (its entries are slot indices)
        return decode_revjson(flat_array, val, seen_copy, depth + 1)

    # Primitive (str, float, bool, None) passed directly — return as-is
    return idx


def parse_payload(raw_array: list) -> dict:
    """
    Parse a Nuxt 3 /_payload.json response into a plain Python dict.

    The payload is a 3+ element array:
      [0] {data: <store_idx>, prerenderedAt: <timestamp>}
      [1] ["ShallowReactive", <data_idx>]
      [2] {store_key: <data_idx>, ...}
      [3..N] actual data nodes

    Returns:
        Dict mapping store_key -> resolved data
    """
    if not raw_array or not isinstance(raw_array, list) or len(raw_array) < 3:
        return {}

    store_map = raw_array[2]
    if not isinstance(store_map, dict):
        return {}

    result = {}
    for key, idx in store_map.items():
        result[key] = decode_revjson(raw_array, idx)
    return result


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

class OpenSnowAPIError(Exception):
    """Raised when the OpenSnow API returns an error."""
    def __init__(self, status_code: int, message: str, endpoint: str):
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"[{status_code}] {endpoint}: {message}")


class OpenSnowClient:
    """
    Python client for OpenSnow's internal API.

    Provides access to:
    - Location info, snow summaries, weather forecasts
    - Resort snow reports, conditions
    - Daily snow posts (DailySnow blog)
    - Avalanche forecasts
    - Snow history and quality data
    - Search and global metadata
    - Webcams and trail maps
    - Weather stations

    Authentication:
        Uses the public frontend API key. No user account required for
        most endpoints. A few endpoints (user favorites, notifications)
        require an authenticated session cookie (cookie-based auth).

    Rate Limiting:
        The API does not advertise rate limits, but CloudFlare sits in
        front of it. Be respectful — add delays between bulk requests.
    """

    def __init__(
        self,
        api_key: str = API_KEY,
        base_url: str = API_BASE_URL,
        payload_base_url: str = PAYLOAD_BASE_URL,
        user_agent: str = USER_AGENT,
        timeout: int = 30,
        units: str = "imperial",
    ):
        """
        Initialize the OpenSnow client.

        Args:
            api_key: API key (defaults to the public frontend key)
            base_url: Base URL for the /mtn REST API
            payload_base_url: Base URL for /_payload.json endpoints
            user_agent: User-Agent header value
            timeout: Request timeout in seconds
            units: "imperial" (inches/Fahrenheit) or "metric" (cm/Celsius)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.payload_base_url = payload_base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout
        self.units = units
        self.session_cookie: Optional[str] = None

    # ── Low-level HTTP ──────────────────────────────────────────────────────

    def _build_url(self, path: str, params: Optional[dict] = None) -> str:
        """Build a full API URL with required query params."""
        base_params = {"v": API_VERSION, "api_key": self.api_key}
        if self.units == "metric":
            base_params["units"] = "metric"
        if params:
            base_params.update({k: v for k, v in params.items() if v is not None})
        query = urllib.parse.urlencode(base_params)
        return f"{self.base_url}/{path.lstrip('/')}?{query}"

    def _request(self, url: str, method: str = "GET", body: Optional[dict] = None) -> Any:
        """Make an HTTP request and return parsed JSON."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie

        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            try:
                err_data = json.loads(body_text)
                msg = err_data.get("message", body_text)
            except Exception:
                msg = body_text
            raise OpenSnowAPIError(e.code, msg, url)
        except urllib.error.URLError as e:
            raise OpenSnowAPIError(0, str(e.reason), url)

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """GET request against the /mtn REST API."""
        url = self._build_url(path, params)
        return self._request(url, "GET")

    def _get_payload(self, page_path: str) -> dict:
        """
        Fetch and decode a Nuxt 3 /_payload.json for a given page path.

        The SSR payload contains fully-resolved location data including
        forecasts, snow history, and resort reports.

        Args:
            page_path: The page URL path (e.g. "/location/vail/snow-summary")

        Returns:
            Dict mapping store keys to resolved data objects
        """
        url = f"{self.payload_base_url}/{page_path.lstrip('/')}/_payload.json"
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read())
                return parse_payload(raw)
        except urllib.error.HTTPError as e:
            raise OpenSnowAPIError(e.code, e.reason, url)
        except urllib.error.URLError as e:
            raise OpenSnowAPIError(0, str(e.reason), url)

    # ── Metadata & Search ───────────────────────────────────────────────────

    def get_meta_seed(self) -> dict:
        """
        Fetch global seed metadata.

        Returns country/state lists, all ski resort locations, camera
        info, and other global configuration used to bootstrap the app.

        Returns:
            {
              "cams": {...},
              "countries": [{"id", "code", "name", "count_locations", "states": [...]}],
              ...
            }
        """
        return self._get("meta/seed")

    def search_locations(self, query: str, limit: int = 10) -> list:
        """
        Search for ski resort locations by name.

        Args:
            query: Search term (e.g. "vail", "mammoth", "whistler")
            limit: Max results to return (default 10)

        Returns:
            List of location dicts:
            [{"id", "name", "slug", "state_name", "country_code",
              "elevation", "share_url", ...}]
        """
        data = self._get("search/locations", {"q": query, "limit": limit})
        return data.get("locations", [])

    def get_location(self, slug: str) -> dict:
        """
        Fetch basic info for a ski resort location.

        Args:
            slug: Location slug (e.g. "vail", "mammoth-mountain", "whistler")

        Returns:
            {
              "location": {
                "id": int, "name": str, "slug": str,
                "elevation": int (feet), "elevation_min": int, "elevation_max": int,
                "coordinates": {"point": [lng, lat]},
                "country_code": str, "state_code": str,
                "timezone": str,
                "has_resort_report": bool,
                "dailysnow_agent_enabled": bool,
                "avalanche_region_id": int,
                ...
              }
            }
        """
        return self._get(f"location/{slug}")

    # ── Snow Summary & Forecasts (via _payload.json) ────────────────────────

    def get_snow_summary(self, slug: str) -> dict:
        """
        Fetch comprehensive snow summary for a location.

        Uses the SSR payload which includes:
        - forecast_snow_summary: 5/10/15-day snow totals
        - forecast_snow_daily: Daily snow breakdown
        - forecast_current: Current conditions
        - forecast_semi_daily: Morning/afternoon snowfall
        - forecast_hourly: Hourly forecast
        - history_snow_daily: Recent snow history
        - history_snow_summary: Seasonal snow totals
        - resort_report: Official resort snow report
        - history_snow_quality: Snow quality history
        - forecast_snow_quality: Upcoming snow quality

        Args:
            slug: Location slug (e.g. "vail", "mammoth-mountain")

        Returns:
            Fully resolved location data dict with all snow data fields
        """
        payload = self._get_payload(f"location/{slug}/snow-summary")
        for key, val in payload.items():
            if key.endswith(f"-{slug}-{self.units}") or slug in key:
                return val
        # Fallback: return first value
        return next(iter(payload.values()), {})

    def get_weather(self, slug: str) -> dict:
        """
        Fetch detailed weather forecast for a location.

        Includes:
        - forecast_current: Current temp, wind, precip
        - forecast_daily: 10-day daily forecast with hi/lo temps
        - forecast_hourly: Hourly forecast

        Args:
            slug: Location slug

        Returns:
            Location data dict with weather forecast fields
        """
        payload = self._get_payload(f"location/{slug}/weather")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_snow_report(self, slug: str) -> dict:
        """
        Fetch the official snow report for a resort.

        Includes base/summit depths, open runs, open lifts,
        snow conditions, and grooming notes.

        Args:
            slug: Location slug

        Returns:
            Location data dict with resort_report field populated
        """
        payload = self._get_payload(f"location/{slug}/snow-report")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_daily_snows(self, slug: str) -> dict:
        """
        Fetch the DailySnow forecast posts for a location.

        DailySnow posts are detailed written forecasts by OpenSnow
        meteorologists. Each post includes:
        - title, summary, author info
        - Forecast period breakdown
        - Powder alerts

        Args:
            slug: Location slug

        Returns:
            Location data dict with daily_read and related forecast posts
        """
        payload = self._get_payload(f"location/{slug}/daily-snows")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_avalanche_forecast(self, slug: str) -> dict:
        """
        Fetch avalanche forecast for a location.

        Provides the avalanche danger rating and forecast from the
        regional avalanche center.

        Args:
            slug: Location slug

        Returns:
            Location data dict with avalanche danger data
        """
        payload = self._get_payload(f"location/{slug}/avalanche-forecast")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_location_info(self, slug: str) -> dict:
        """
        Fetch informational page data for a location.

        Includes resort description, amenities, mountain stats,
        and contact/website info.

        Args:
            slug: Location slug

        Returns:
            Location data dict with info fields
        """
        payload = self._get_payload(f"location/{slug}/info")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_cams(self, slug: str) -> dict:
        """
        Fetch webcam list for a location.

        Returns camera names, URLs, thumbnail images,
        and camera location descriptions.

        Args:
            slug: Location slug

        Returns:
            Location data dict with cam data
        """
        payload = self._get_payload(f"location/{slug}/cams")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_trail_maps(self, slug: str) -> dict:
        """
        Fetch trail map data for a location.

        Args:
            slug: Location slug

        Returns:
            Location data dict with trail map images and info
        """
        payload = self._get_payload(f"location/{slug}/trail-maps")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    def get_weather_stations(self, slug: str) -> dict:
        """
        Fetch weather station data near a location.

        Returns nearby SNOTEL and other weather station readings
        including snow water equivalent, snow depth, and temperature.

        Args:
            slug: Location slug

        Returns:
            Location data dict with weather_stations data
        """
        payload = self._get_payload(f"location/{slug}/weather-stations")
        for key, val in payload.items():
            if slug in key:
                return val
        return next(iter(payload.values()), {})

    # ── Powder & Explore ────────────────────────────────────────────────────

    def get_powder_map(self) -> dict:
        """
        Fetch the powder map data showing snow totals across all resorts.

        Returns a list of all tracked locations with their current
        1-day, 3-day, 7-day, and season-to-date snowfall totals.

        Returns:
            Payload data with location snow totals for the powder map
        """
        payload = self._get_payload("explore/powder")
        return next(iter(payload.values()), {})

    def get_explore_state(self, state_code: str) -> dict:
        """
        Fetch resort listing for a US state.

        Args:
            state_code: US state code (e.g. "US-CO", "US-UT", "US-CA")

        Returns:
            Payload data with state resort listings
        """
        payload = self._get_payload(f"explore/states/{state_code}")
        return next(iter(payload.values()), {})

    def get_explore_country(self, country_code: str) -> dict:
        """
        Fetch resort listing for a country.

        Args:
            country_code: Country code (e.g. "CA", "AT", "CH")

        Returns:
            Payload data with country resort listings
        """
        payload = self._get_payload(f"explore/countries/{country_code}")
        return next(iter(payload.values()), {})

    def get_explore_region(self, region_slug: str) -> dict:
        """
        Fetch resort listing for a geographic region.

        Args:
            region_slug: Region identifier (e.g. "rocky-mountains", "sierra-nevada")

        Returns:
            Payload data with region resort listings
        """
        payload = self._get_payload(f"explore/regions/{region_slug}")
        return next(iter(payload.values()), {})

    def get_explore_season_pass(self, pass_slug: str) -> dict:
        """
        Fetch resort listing for a season pass (Ikon, Epic, etc.).

        Args:
            pass_slug: Season pass identifier (e.g. "ikon", "epic")

        Returns:
            Payload data with season pass resort listings
        """
        payload = self._get_payload(f"explore/season-passes/{pass_slug}")
        return next(iter(payload.values()), {})

    # ── DailySnow Blog ──────────────────────────────────────────────────────

    def get_daily_snow_post(self, location_slug: str, post_id: int) -> dict:
        """
        Fetch a specific DailySnow forecast post.

        DailySnow posts are detailed written forecasts by OpenSnow
        meteorologists for specific resorts.

        Args:
            location_slug: Location slug (e.g. "vail")
            post_id: Post ID (integer)

        Returns:
            Payload data with the full post content
        """
        payload = self._get_payload(f"dailysnow/{location_slug}/post/{post_id}")
        return next(iter(payload.values()), {})

    def get_daily_reads_list(self) -> dict:
        """
        Fetch the global DailySnow recent posts listing.

        Returns recent posts from all meteorologists across all
        monitored locations.

        Returns:
            Payload data with recent daily snow posts
        """
        payload = self._get_payload("daily-reads")
        return next(iter(payload.values()), {})

    # ── Forecast Current Conditions ─────────────────────────────────────────

    def get_forecast_current(self, slug: str) -> Optional[dict]:
        """
        Extract current conditions from snow summary data.

        Returns current temperature, wind speed/direction, visibility,
        weather description, and recent precipitation.

        Args:
            slug: Location slug

        Returns:
            forecast_current dict or None
        """
        data = self.get_snow_summary(slug)
        return data.get("forecast_current")

    def get_forecast_snow_summary(self, slug: str) -> Optional[list]:
        """
        Extract the 5/10/15-day snow total summaries.

        Returns period summaries showing:
        - display_at: Period end date
        - precip_snow: Expected snowfall inches/cm
        - precip_snow_min/max: Low/high range
        - alerts: Powder alerts for the period

        Args:
            slug: Location slug

        Returns:
            List of forecast_snow_summary period dicts, or None
        """
        data = self.get_snow_summary(slug)
        return data.get("forecast_snow_summary")

    def get_forecast_snow_daily(self, slug: str) -> Optional[list]:
        """
        Extract daily snowfall forecast (15 days).

        Each item contains:
        - display_at: Date
        - precip_snow: Expected snow inches/cm
        - precip_snow_min/max: Low/high range
        - alerts: Any powder alerts for that day

        Args:
            slug: Location slug

        Returns:
            List of daily forecast dicts, or None
        """
        data = self.get_snow_summary(slug)
        return data.get("forecast_snow_daily")

    def get_forecast_hourly(self, slug: str) -> Optional[list]:
        """
        Extract hourly forecast data.

        Each item contains temperature, wind, precip, snow,
        and weather condition codes.

        Args:
            slug: Location slug

        Returns:
            List of hourly forecast dicts, or None
        """
        data = self.get_snow_summary(slug)
        return data.get("forecast_hourly")

    def get_history_snow_daily(self, slug: str) -> Optional[list]:
        """
        Extract recent snow history (past 7-14 days).

        Args:
            slug: Location slug

        Returns:
            List of historical daily snow dicts, or None
        """
        data = self.get_snow_summary(slug)
        return data.get("history_snow_daily")

    def get_history_snow_summary(self, slug: str) -> Optional[dict]:
        """
        Extract season-to-date snow totals and historical averages.

        Includes:
        - season_to_date: Total snowfall this season
        - avg_season_to_date: Historical average for this date
        - annual_average: Average annual snowfall

        Args:
            slug: Location slug

        Returns:
            history_snow_summary dict or None
        """
        data = self.get_snow_summary(slug)
        return data.get("history_snow_summary")

    def get_resort_report(self, slug: str) -> Optional[dict]:
        """
        Extract the official resort snow report.

        Includes:
        - base_depth_max/min: Base snow depth (inches/cm)
        - summit_depth_max/min: Summit snow depth
        - open_runs, total_runs: Run counts
        - open_lifts, total_lifts: Lift counts
        - conditions: Snow conditions description
        - updated_at: When the report was last updated

        Args:
            slug: Location slug

        Returns:
            resort_report dict or None
        """
        data = self.get_snow_summary(slug)
        return data.get("resort_report")

    # ── Compare ─────────────────────────────────────────────────────────────

    def compare_locations(self, slug1: str, slug2: str) -> dict:
        """
        Fetch side-by-side comparison data for two locations.

        Args:
            slug1: First location slug
            slug2: Second location slug

        Returns:
            Payload data with comparison snowfall data
        """
        payload = self._get_payload(f"compare/{slug1}/{slug2}")
        return next(iter(payload.values()), {})

    # ── Snowstakes ──────────────────────────────────────────────────────────

    def get_snowstakes(self) -> dict:
        """
        Fetch the snowstake monitoring data.

        Snowstakes are physical measuring stakes at resorts that
        provide real-time snow depth photos.

        Returns:
            Payload data with snowstake location and image data
        """
        payload = self._get_payload("explore/snowstakes")
        return next(iter(payload.values()), {})

    # ── Convenience Methods ─────────────────────────────────────────────────

    def get_quick_snow_report(self, slug: str) -> dict:
        """
        Get a concise snow report combining key stats.

        Fetches the full snow summary and returns a simplified
        dict with the most important metrics.

        Args:
            slug: Location slug

        Returns:
            Dict with:
            - name: Resort name
            - slug: Resort slug
            - elevation_ft: Summit elevation (feet)
            - current_temp_f: Current temperature
            - recent_snow_24h: Past 24h snowfall
            - recent_snow_7d: Past 7-day snowfall
            - forecast_snow_5d: Next 5-day forecast
            - forecast_snow_10d: Next 10-day forecast
            - season_total: Season-to-date snowfall
            - base_depth: Current base depth
            - open_runs: Open run count
            - open_lifts: Open lift count
            - forecast_updated_at: When forecast was last updated
        """
        data = self.get_snow_summary(slug)

        # Current conditions
        current = data.get("forecast_current") or {}

        # Snow summaries — each period covers 5 days:
        # "Next 1-5 Days", "Next 6-10 Days", "Next 11-15 Days"
        summaries = data.get("forecast_snow_summary") or []
        if not isinstance(summaries, list):
            summaries = []
        s5 = next((s for s in summaries
                   if isinstance(s, dict) and "1-5" in (s.get("display_at_local_label") or "")), {})
        s10 = next((s for s in summaries
                    if isinstance(s, dict) and "6-10" in (s.get("display_at_local_label") or "")), {})

        # History — history_snow_summary is a list of period summaries
        # (Prev 1-5 Days, Prev 6-10 Days, Prev 11-15 Days)
        hist_summary_list = data.get("history_snow_summary") or []
        if isinstance(hist_summary_list, list):
            hist_prev5 = next(
                (h for h in hist_summary_list
                 if isinstance(h, dict) and "1-5" in (h.get("display_at_local_label") or "")),
                {}
            )
            season_total = sum(
                (h.get("precip_snow") or 0) for h in hist_summary_list
                if isinstance(h, dict)
            )
        elif isinstance(hist_summary_list, dict):
            hist_prev5 = hist_summary_list
            season_total = hist_summary_list.get("season_to_date")
        else:
            hist_prev5 = {}
            season_total = None

        hist_daily = data.get("history_snow_daily") or []
        if isinstance(hist_daily, list):
            recent_1d = (hist_daily[0].get("precip_snow") or 0) if hist_daily and isinstance(hist_daily[0], dict) else 0
            recent_7d = sum(
                (d.get("precip_snow") or 0) for d in hist_daily[:7]
                if isinstance(d, dict)
            )
        else:
            recent_1d = 0
            recent_7d = 0

        # Resort report
        report = data.get("resort_report")
        if not isinstance(report, dict):
            report = {}

        return {
            "name": data.get("name"),
            "slug": data.get("slug"),
            "elevation_ft": data.get("elevation"),
            "timezone": data.get("timezone"),
            "current_temp_f": current.get("temp") or current.get("temp_f"),
            "current_wind_mph": current.get("wind_speed"),
            "current_conditions": current.get("conditions_label") or current.get("phrase"),
            "recent_snow_24h": round(float(recent_1d), 1),
            "recent_snow_7d": round(float(recent_7d), 1),
            "history_prev_5d_snow": hist_prev5.get("precip_snow"),
            "history_season_approx": round(float(season_total), 1) if isinstance(season_total, (int, float)) else None,
            "forecast_snow_5d": s5.get("precip_snow"),
            "forecast_snow_5d_range": (s5.get("precip_snow_min"), s5.get("precip_snow_max")),
            "forecast_snow_10d": s10.get("precip_snow"),
            "forecast_snow_10d_range": (s10.get("precip_snow_min"), s10.get("precip_snow_max")),
            "base_depth": (report.get("base_depth_min") or report.get("base_depth_max")),
            "summit_depth": (report.get("summit_depth_min") or report.get("summit_depth_max")),
            "open_runs": report.get("runs_open") or report.get("open_runs"),
            "total_runs": report.get("runs_total") or report.get("total_runs"),
            "open_lifts": report.get("lifts_open") or report.get("open_lifts"),
            "total_lifts": report.get("lifts_total") or report.get("total_lifts"),
            "resort_status": report.get("status_display"),
            "resort_conditions": report.get("conditions"),
            "resort_percent_open": round(report["percent_open"] * 100) if report.get("percent_open") is not None else None,
            "forecast_updated_at": data.get("forecast_updated_at"),
        }

    def get_powder_alerts(self, slug: str) -> list:
        """
        Get upcoming powder alert days for a location.

        Powder alerts indicate days with significant snowfall expected
        (typically 3+ inches / 7+ cm).

        Args:
            slug: Location slug

        Returns:
            List of dicts: [{"display_at", "precip_snow", "alert_level", ...}]
        """
        daily = self.get_forecast_snow_daily(slug) or []
        alerts = []
        for day in daily:
            if day.get("alerts"):
                for alert in day["alerts"]:
                    alerts.append({
                        "display_at": day.get("display_at"),
                        "date_label": day.get("display_at_local_label"),
                        "precip_snow": day.get("precip_snow"),
                        "precip_snow_min": day.get("precip_snow_min"),
                        "precip_snow_max": day.get("precip_snow_max"),
                        "alert_id": alert.get("alert_id"),
                        "alert_level": alert.get("level_id"),
                        "alert_color": alert.get("color_foreground"),
                    })
        return alerts

    def bulk_snow_summary(self, slugs: list, delay: float = 0.5) -> dict:
        """
        Fetch snow summaries for multiple locations.

        Args:
            slugs: List of location slugs
            delay: Seconds to wait between requests (be respectful)

        Returns:
            Dict mapping slug -> quick_snow_report dict
        """
        results = {}
        for i, slug in enumerate(slugs):
            if i > 0:
                time.sleep(delay)
            try:
                results[slug] = self.get_quick_snow_report(slug)
            except OpenSnowAPIError as e:
                results[slug] = {"error": str(e)}
        return results


# ─── CLI Demo ─────────────────────────────────────────────────────────────────

def main():
    """Demo the client capabilities."""
    import sys

    client = OpenSnowClient()

    if len(sys.argv) > 1:
        slug = sys.argv[1]
    else:
        slug = "vail"

    print(f"\n{'='*60}")
    print(f"OpenSnow Quick Report: {slug}")
    print(f"{'='*60}")

    try:
        report = client.get_quick_snow_report(slug)
        print(f"Resort:          {report['name']}")
        print(f"Elevation:       {report['elevation_ft']:,} ft")
        print(f"Timezone:        {report['timezone']}")
        print(f"")
        print(f"Current Conditions:")
        print(f"  Temperature:   {report['current_temp_f']}°F")
        print(f"  Wind:          {report['current_wind_mph']} mph")
        print(f"  Description:   {report['current_conditions']}")
        print(f"")
        print(f"Recent Snow:")
        print(f"  Last 24h:      {report['recent_snow_24h']}\"")
        print(f"  Last 7 days:   {report['recent_snow_7d']}\"")
        print(f"  Prev 5-day:    {report['history_prev_5d_snow']}\"")
        print(f"  Season Approx: {report['history_season_approx']}\"")
        print(f"")
        print(f"Forecast:")
        print(f"  Next 5 days:   {report['forecast_snow_5d']}\" ({report['forecast_snow_5d_range'][0]}-{report['forecast_snow_5d_range'][1]}\")")
        print(f"  Next 10 days:  {report['forecast_snow_10d']}\" ({report['forecast_snow_10d_range'][0]}-{report['forecast_snow_10d_range'][1]}\")")
        print(f"")
        print(f"Mountain Status:")
        print(f"  Status:        {report['resort_status']}")
        print(f"  Conditions:    {report['resort_conditions']}")
        print(f"  Percent Open:  {report['resort_percent_open']}%")
        print(f"  Base Depth:    {report['base_depth']}\"")
        print(f"  Summit Depth:  {report['summit_depth']}\"")
        print(f"  Open Runs:     {report['open_runs']}/{report['total_runs']}")
        print(f"  Open Lifts:    {report['open_lifts']}/{report['total_lifts']}")
        print(f"")

        alerts = client.get_powder_alerts(slug)
        if alerts:
            print(f"Powder Alerts ({len(alerts)}):")
            for a in alerts:
                print(f"  {a['date_label']}: {a['precip_snow']}\" expected ({a['precip_snow_min']}-{a['precip_snow_max']}\")")
        else:
            print("No powder alerts in the next 15 days.")

        print(f"\nForecast updated: {report['forecast_updated_at']}")

    except OpenSnowAPIError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
