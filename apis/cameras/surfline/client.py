"""
Surfline API Client
===================
Reverse-engineered Python client for Surfline's undocumented REST API.

Base URL: https://services.surfline.com

Authentication:
- Most forecast and spot data endpoints require the Origin and Referer headers
  set to https://www.surfline.com/ (acts as a same-origin token).
- User-specific endpoints (favorites, profile) require a Bearer JWT token obtained
  from the /auth/token endpoint.
- Camera HLS streams (hls.cdn-surfline.com) require a premium subscription and
  are gated by Cloudflare; still images (camstills.cdn-surfline.com) are publicly
  accessible via the CDN.

Public endpoints (with Origin/Referer headers):
- GET /kbyg/mapview                       -> spots + cameras in a bounding box
- GET /kbyg/spots/reports                 -> full spot report
- GET /kbyg/spots/nearby                  -> spots near a given spot
- GET /kbyg/spots/forecasts/wave          -> hourly wave forecast (up to ~6 days)
- GET /kbyg/spots/forecasts/wind          -> hourly wind forecast
- GET /kbyg/spots/forecasts/tides         -> tide heights (HIGH/LOW/NORMAL)
- GET /kbyg/spots/forecasts/weather       -> temperature, pressure, conditions
- GET /kbyg/spots/forecasts/conditions    -> human-written forecast narrative
- GET /kbyg/spots/forecasts/rating        -> per-hour surf quality rating
- GET /kbyg/regions/overview              -> subregion overview with all spots
- GET /kbyg/regions/forecasts/conditions  -> region-level conditions
- GET /kbyg/regions/forecasts/wave        -> region-level wave forecast
- GET /search/site                        -> search spots and news articles

Auth-required endpoints:
- POST /auth/token                        -> obtain JWT Bearer token
- GET  /user/favorites                    -> saved/favorited spots
- GET  /user/profile                      -> user account profile
- GET  /user/feeds                        -> personalized feed
"""

import time
import datetime
from typing import Optional, Union
from urllib.parse import urlencode

try:
    import requests
    from requests import Session, Response
except ImportError:
    raise ImportError("requests is required: pip install requests")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://services.surfline.com"
CDN_CAM_STILLS = "https://camstills.cdn-surfline.com"
CDN_HLS = "https://hls.cdn-surfline.com"
CDN_REWINDS = "https://camrewinds.cdn-surfline.com"
CDN_HIGHLIGHTS = "https://highlights.cdn-surfline.com"
CDN_SPOT_THUMBNAILS = "https://spot-thumbnails.cdn-surfline.com"

# Rating key to human description mapping
RATING_MAP = {
    "FLAT": 0,
    "VERY_POOR": 1,
    "POOR": 1,
    "POOR_TO_FAIR": 2,
    "FAIR": 3,
    "FAIR_TO_GOOD": 4,
    "GOOD": 5,
    "VERY_GOOD": 6,
    "EPIC": 6,
}

# Wind direction type constants
WIND_OFFSHORE = "Offshore"
WIND_ONSHORE = "Onshore"
WIND_CROSS = "Cross-shore"

# Default well-known spot IDs for convenience
SPOTS = {
    "pipeline": "5842041f4e65fad6a7708890",
    "mavericks": "5842041f4e65fad6a7708864",
    "huntington_st": "58bdebbc82d034001252e3d2",
    "venice_beach": "5842041f4e65fad6a7708849",
    "rincon": "5842041f4e65fad6a77087f0",
    "trestles": "5842041f4e65fad6a7708877",
    "jaws": "5842041f4e65fad6a770900e",
    "teahupo'o": "5842041f4e65fad6a7708b15",
    "kirra": "5842041f4e65fad6a7709a43",
    "j-bay": "5842041f4e65fad6a7709e38",
}

# Default well-known subregion IDs
SUBREGIONS = {
    "north_orange_county": "58581a836630e24c44878fd6",
    "north_shore_oahu": "58581a836630e24c44878fcb",
    "north_san_diego": "58581a836630e24c44878fd7",
    "south_orange_county": "58581a836630e24c4487900a",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _ts_to_dt(timestamp: int, utc_offset: int = 0) -> datetime.datetime:
    """Convert Unix timestamp to local datetime using utc_offset (hours)."""
    utc = datetime.datetime.utcfromtimestamp(timestamp)
    return utc + datetime.timedelta(hours=utc_offset)


def _cardinal(degrees: float) -> str:
    """Convert compass degrees to 16-point cardinal direction."""
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    idx = round(degrees / 22.5) % 16
    return dirs[idx]


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class SurflineClient:
    """
    Client for Surfline's undocumented API.

    Usage (unauthenticated - most data available):
        client = SurflineClient()
        wave = client.get_wave_forecast("5842041f4e65fad6a7708890", days=3)

    Usage (authenticated - user-specific data):
        client = SurflineClient()
        client.login("user@example.com", "password")
        favs = client.get_favorites()
    """

    def __init__(
        self,
        timeout: int = 15,
        user_agent: str = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    ):
        self.session = Session()
        self.timeout = timeout
        self._token: Optional[str] = None

        # These headers are required for the API to return data without
        # a proper user authentication token.  The service checks for an
        # Origin / Referer matching surfline.com as a lightweight CSRF guard.
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Origin": "https://www.surfline.com",
                "Referer": "https://www.surfline.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> dict:
        """
        Authenticate with Surfline and store the Bearer token.

        The /auth/token endpoint expects application/x-www-form-urlencoded
        POST data.  Returns the full token response dict on success.

        Endpoint: POST /auth/token
        Auth required: No (this IS the auth endpoint)

        Confirmed params (March 2026 live test):
          grant_type=password
          client_id=SurferApp   (or 5af1ce73b5acf7c6dd2592ee for platform.surfline.com)
          client_secret=SurferApp
          device_id=web
          email=<email>
          password=<password>

        Error responses:
          {"message": "Invalid Parameters: Client credentials are invalid"}
          {"message": "Invalid Parameters: Method must be POST with
                       application/x-www-form-urlencoded encoding"}
        """
        url = f"{BASE_URL}/auth/token"
        payload = {
            "grant_type": "password",
            "client_id": "SurferApp",
            "client_secret": "SurferApp",
            "device_id": "web",
            "email": email,
            "password": password,
        }
        resp = self.session.post(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if token:
            self._token = token
            self.session.headers["Authorization"] = f"Bearer {token}"
        return data

    def logout(self) -> None:
        """Clear the stored auth token."""
        self._token = None
        self.session.headers.pop("Authorization", None)

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Map / Geo Endpoints
    # ------------------------------------------------------------------

    def get_spots_in_bbox(
        self,
        south: float,
        north: float,
        west: float,
        east: float,
    ) -> dict:
        """
        Return all surf spots (with current conditions, cameras, and nearby
        subregions) within a geographic bounding box.

        Endpoint: GET /kbyg/mapview
        Auth required: No (with Origin/Referer headers)

        Returns a dict with keys:
            data.spots       -> list of spot objects (see _parse_spot_summary)
            data.subregions  -> list of subregion summaries
            data.regionalForecast -> regional forecast icon/id
            associated.units -> measurement units in use

        Example:
            spots = client.get_spots_in_bbox(
                south=20.5, north=21.9, west=-158.5, east=-157.5
            )
        """
        return self._get(
            "/kbyg/mapview",
            params={"south": south, "north": north, "west": west, "east": east},
        )

    # ------------------------------------------------------------------
    # Spot Endpoints
    # ------------------------------------------------------------------

    def get_spot_report(self, spot_id: str) -> dict:
        """
        Full spot report: metadata, cameras, current conditions, forecast
        summary, travel details, and breadcrumb.

        Endpoint: GET /kbyg/spots/reports
        Auth required: No

        Useful fields:
            spot.name, spot.lat, spot.lon
            spot.cameras[]     -> list of camera objects (see Camera section)
            spot.subregion     -> parent subregion info
            spot.travelDetails -> access, bottom, ability levels, etc.
            forecast.conditions.value   -> current rating key (e.g. "FAIR")
            forecast.waveHeight.min/max -> current wave height in ft
            forecast.wind.speed/direction/directionType
            forecast.swells[].height/period/direction
            forecast.tide.previous/current/next
            forecast.waterTemp.min/max
        """
        return self._get("/kbyg/spots/reports", params={"spotId": spot_id})

    def get_nearby_spots(self, spot_id: str) -> dict:
        """
        List of spots geographically near the given spot.

        Endpoint: GET /kbyg/spots/nearby
        Auth required: No

        Returns: data.spots -> list of spot objects with current conditions
        """
        return self._get("/kbyg/spots/nearby", params={"spotId": spot_id})

    # ------------------------------------------------------------------
    # Forecast Endpoints
    # ------------------------------------------------------------------

    def get_wave_forecast(
        self,
        spot_id: str,
        days: int = 5,
        interval_hours: int = 1,
        max_heights: bool = False,
        units: Optional[dict] = None,
    ) -> dict:
        """
        Hourly wave height and swell forecast for a surf spot.

        Endpoint: GET /kbyg/spots/forecasts/wave
        Auth required: No (for up to ~6 days)

        Parameters:
            spot_id        : Surfline spot ID
            days           : Number of days (1-6 without auth; max 6)
            interval_hours : Interval between data points (1 or 3)
            max_heights    : Include maximum height estimates
            units          : Dict of unit overrides, e.g.
                             {"waveHeight": "M", "swellHeight": "M"}

        Returns dict with:
            data.wave[].timestamp     -> Unix timestamp
            data.wave[].utcOffset     -> hours from UTC
            data.wave[].surf.min      -> min surf height (human-scaled)
            data.wave[].surf.max      -> max surf height
            data.wave[].surf.plus     -> True if "plus" (e.g. "4ft+")
            data.wave[].surf.humanRelation -> e.g. "Waist to shoulder"
            data.wave[].surf.raw.min  -> raw model min height in ft
            data.wave[].surf.raw.max  -> raw model max height in ft
            data.wave[].surf.optimalScore -> 0-3 quality score
            data.wave[].power         -> total wave power index
            data.wave[].swells[]      -> up to 6 individual swell components:
                .height, .period, .direction, .directionMin,
                .impact, .power, .optimalScore
            associated.location       -> spot lat/lon
            associated.forecastLocation -> model grid point lat/lon
            associated.offshoreLocation -> offshore model point lat/lon
            associated.units          -> units dict
        """
        params: dict = {
            "spotId": spot_id,
            "days": days,
            "intervalHours": interval_hours,
        }
        if max_heights:
            params["maxHeights"] = "true"
        if units:
            # Surfline expects bracket notation: units[waveHeight]=M
            for key, val in units.items():
                params[f"units[{key}]"] = val
        return self._get("/kbyg/spots/forecasts/wave", params=params)

    def get_wind_forecast(
        self,
        spot_id: str,
        days: int = 5,
        interval_hours: int = 1,
        units: Optional[dict] = None,
    ) -> dict:
        """
        Hourly wind forecast for a surf spot.

        Endpoint: GET /kbyg/spots/forecasts/wind
        Auth required: No

        Returns dict with:
            data.wind[].timestamp      -> Unix timestamp
            data.wind[].utcOffset
            data.wind[].speed          -> wind speed in KTS (default)
            data.wind[].direction      -> degrees (0=N, 90=E, 180=S, 270=W)
            data.wind[].directionType  -> "Offshore", "Onshore", "Cross-shore"
            data.wind[].gust           -> gust speed in KTS
            data.wind[].optimalScore   -> 0-3 quality score
            associated.windStation     -> nearest weather station name + location
            associated.lastObserved    -> Unix timestamp of last live obs
        """
        params: dict = {
            "spotId": spot_id,
            "days": days,
            "intervalHours": interval_hours,
        }
        if units:
            for key, val in units.items():
                params[f"units[{key}]"] = val
        return self._get("/kbyg/spots/forecasts/wind", params=params)

    def get_tide_forecast(
        self,
        spot_id: str,
        days: int = 5,
    ) -> dict:
        """
        Tide heights for the given spot.

        Endpoint: GET /kbyg/spots/forecasts/tides
        Auth required: No

        Returns dict with:
            data.tides[].timestamp  -> Unix timestamp
            data.tides[].utcOffset
            data.tides[].type       -> "HIGH", "LOW", or "NORMAL"
            data.tides[].height     -> tide height in FT (default)
            associated.tideLocation -> nearest NOAA tide station
                .name, .min, .max, .lon, .lat, .mean
        """
        return self._get(
            "/kbyg/spots/forecasts/tides",
            params={"spotId": spot_id, "days": days},
        )

    def get_weather_forecast(
        self,
        spot_id: str,
        days: int = 5,
        interval_hours: int = 1,
    ) -> dict:
        """
        Weather forecast (temperature, conditions, pressure) and sunlight times.

        Endpoint: GET /kbyg/spots/forecasts/weather
        Auth required: No

        Returns dict with:
            data.weather[].timestamp    -> Unix timestamp
            data.weather[].utcOffset
            data.weather[].temperature  -> air temperature in F (default)
            data.weather[].condition    -> icon key, e.g. "MOSTLY_CLOUDY",
                                           "CLEAR", "NIGHT_MOSTLY_CLOUDY"
            data.weather[].pressure     -> sea-level pressure in MB
            data.sunlightTimes[].midnight  -> Unix ts of local midnight
            data.sunlightTimes[].dawn      -> civil dawn
            data.sunlightTimes[].sunrise
            data.sunlightTimes[].sunset
            data.sunlightTimes[].dusk      -> civil dusk
            associated.weatherIconPath -> base URL for weather condition icons
        """
        return self._get(
            "/kbyg/spots/forecasts/weather",
            params={
                "spotId": spot_id,
                "days": days,
                "intervalHours": interval_hours,
            },
        )

    def get_surf_conditions(
        self,
        spot_id: str,
        days: int = 5,
    ) -> dict:
        """
        Human-written surf condition forecasts by day.

        Endpoint: GET /kbyg/spots/forecasts/conditions
        Auth required: No

        Returns dict with:
            data.conditions[].timestamp    -> Unix ts of the forecast day
            data.conditions[].forecastDay  -> "YYYY-MM-DD"
            data.conditions[].forecaster   -> {name, avatar}
            data.conditions[].human        -> True if human-written
            data.conditions[].dayToWatch   -> True if marked as special
            data.conditions[].headline     -> one-line headline string
            data.conditions[].observation  -> full forecast text (may contain HTML)
            data.conditions[].am/pm        -> AM/PM specific observations
        """
        return self._get(
            "/kbyg/spots/forecasts/conditions",
            params={"spotId": spot_id, "days": days},
        )

    def get_surf_rating(
        self,
        spot_id: str,
        days: int = 5,
        interval_hours: int = 1,
    ) -> dict:
        """
        Per-hour surf quality rating (FLAT through EPIC).

        Endpoint: GET /kbyg/spots/forecasts/rating
        Auth required: No

        Returns dict with:
            data.rating[].timestamp     -> Unix timestamp
            data.rating[].utcOffset
            data.rating[].rating.key    -> e.g. "FAIR", "GOOD", "EPIC"
            data.rating[].rating.value  -> integer 0-6

        Rating key mapping:
            FLAT=0, VERY_POOR=1, POOR=1, POOR_TO_FAIR=2, FAIR=3,
            FAIR_TO_GOOD=4, GOOD=5, VERY_GOOD=6, EPIC=6
        """
        return self._get(
            "/kbyg/spots/forecasts/rating",
            params={
                "spotId": spot_id,
                "days": days,
                "intervalHours": interval_hours,
            },
        )

    # ------------------------------------------------------------------
    # Region / Subregion Endpoints
    # ------------------------------------------------------------------

    def get_sunlight(self, spot_id: str, days: int = 5) -> dict:
        """
        Daily sunrise/sunset/dawn/dusk times for a spot.

        Endpoint: GET /kbyg/spots/forecasts/sunlight
        Auth required: No

        Returns dict with:
            data.sunlight[].midnight        -> Unix ts of local midnight
            data.sunlight[].midnightUTCOffset
            data.sunlight[].dawn            -> civil dawn timestamp
            data.sunlight[].dawnUTCOffset
            data.sunlight[].sunrise
            data.sunlight[].sunriseUTCOffset
            data.sunlight[].sunset
            data.sunlight[].sunsetUTCOffset
            data.sunlight[].dusk
            data.sunlight[].duskUTCOffset
            associated.location.lat/lon
        """
        return self._get(
            "/kbyg/spots/forecasts/sunlight",
            params={"spotId": spot_id, "days": days},
        )

    def get_all_cameras_global(self) -> list:
        """
        Fetch every Surfline camera globally using a world-spanning bounding box.

        Returns a flat list of camera objects, each augmented with:
            _spotId, _spotName, _lat, _lon

        Note: This request fetches ~22 MB of data (9000 spots, ~1089 cameras).
        As of March 2026:
            Total cameras:   1089
            Premium cameras:  538
            Free cameras:     551

        CDN region distribution by stream URL:
            hls.cdn-surfline.com/oregon/   – Americas & Pacific
            hls.cdn-surfline.com/ohio/     – US East Coast
            hls.cdn-surfline.com/ireland/  – Europe
            hls.cdn-surfline.com/east-au/  – Australia East
            hls.cdn-surfline.com/west-au/  – Australia West

        Still image CDN region distribution:
            camstills.cdn-surfline.com/us-west-2/ – Americas & Pacific
            camstills.cdn-surfline.com/eu-west-1/ – Europe
        """
        return self.get_cameras_in_bbox(south=-90, north=90, west=-180, east=180)

    def get_region_overview(self, subregion_id: str) -> dict:
        """
        Full overview of a subregion including all contained spots,
        forecast status, and forecaster info.

        Endpoint: GET /kbyg/regions/overview
        Auth required: No

        Returns dict with:
            data._id         -> subregion ID
            data.name        -> subregion name
            data.primarySpot -> ID of the primary/flagship spot
            data.breadcrumb  -> [{name, href}, ...] geographic hierarchy
            data.forecastSummary.forecaster -> {name, title, iconUrl}
            data.spots[]     -> list of all spots in region with:
                ._id, .name, .lat, .lon
                .conditions.value    -> current rating key
                .waveHeight.min/max  -> wave height range in ft
                .wind.speed/direction/directionType
                .tide.previous/current/next
                .cameras[]           -> camera objects
        """
        return self._get(
            "/kbyg/regions/overview",
            params={"subregionId": subregion_id},
        )

    def get_region_conditions(
        self,
        subregion_id: str,
        days: int = 5,
    ) -> dict:
        """
        Region-level (subregion) daily conditions forecast.

        Endpoint: GET /kbyg/regions/forecasts/conditions
        Auth required: No

        Returns same structure as get_surf_conditions() but for a whole region.
        """
        return self._get(
            "/kbyg/regions/forecasts/conditions",
            params={"subregionId": subregion_id, "days": days},
        )

    def get_region_wave_forecast(
        self,
        subregion_id: str,
        days: int = 5,
        interval_hours: int = 3,
    ) -> dict:
        """
        Region-level wave forecast (representative offshore point).

        Endpoint: GET /kbyg/regions/forecasts/wave
        Auth required: No

        Returns same structure as get_wave_forecast() but for a region centroid.
        """
        return self._get(
            "/kbyg/regions/forecasts/wave",
            params={
                "subregionId": subregion_id,
                "days": days,
                "intervalHours": interval_hours,
            },
        )

    # ------------------------------------------------------------------
    # Camera Endpoints
    # ------------------------------------------------------------------

    def get_cameras_in_bbox(
        self,
        south: float,
        north: float,
        west: float,
        east: float,
    ) -> list:
        """
        Return all camera objects found within a geographic bounding box.

        This is a convenience wrapper around get_spots_in_bbox() that extracts
        just the camera objects from all spots in the area.

        Camera object fields:
            _id               -> unique camera ID
            title             -> human-readable name
            alias             -> short slug (e.g. "hi-pipeline")
            streamUrl         -> HLS m3u8 playlist URL (premium may be blocked)
            stillUrl          -> small JPEG still URL (publicly accessible)
            stillUrlFull      -> full-size JPEG still URL
            pixelatedStillUrl -> blurred preview for non-subscribers
            rewindBaseUrl     -> base for rewind clip URLs
            rewindClip        -> URL of the most recent rewind MP4
            highlights.url    -> URL of the latest highlight clip MP4
            highlights.thumbUrl -> thumbnail for the highlight
            isPremium         -> True if a subscription is required
            isPrerecorded     -> True if cam is currently playing a recorded loop
            supportsHighlights, supportsInsights, supportsSmartRewinds
            supportsCrowds    -> True if crowd-level data available
            isLineupCam       -> True if a lineup/underwater-angle cam
            nighttime         -> True if currently night
            status.isDown     -> True if the camera is offline
            status.message    -> status message
            host.camLinkText  -> e.g. "Camera hosted by Pasea Hotel & Spa"
        """
        data = self.get_spots_in_bbox(south, north, west, east)
        cameras = []
        spots = data.get("data", {}).get("spots", [])
        for spot in spots:
            for cam in spot.get("cameras", []):
                cam["_spotId"] = spot["_id"]
                cam["_spotName"] = spot.get("name", "")
                cam["_lat"] = spot.get("lat")
                cam["_lon"] = spot.get("lon")
                cameras.append(cam)
        return cameras

    def get_cameras_for_spot(self, spot_id: str) -> list:
        """
        Return the list of camera objects associated with a specific spot.

        This is a convenience wrapper around get_spot_report().
        """
        report = self.get_spot_report(spot_id)
        return report.get("spot", {}).get("cameras", [])

    def get_camera_still_url(
        self,
        alias: str,
        size: str = "small",
        region: str = "us-west-2",
    ) -> str:
        """
        Build the URL for a camera's latest still image.

        Parameters:
            alias  : Camera alias (e.g. "hi-pipeline", "wc-huntingtonstov")
            size   : "small" (320px) or "full" (full resolution)
            region : AWS region prefix, default "us-west-2"

        Returns:
            Publicly accessible HTTPS URL to the JPEG image.

        CDN base: https://camstills.cdn-surfline.com

        Note: Still images at camstills.cdn-surfline.com are publicly
        accessible without any authentication.
        """
        if size == "full":
            filename = "latest_full.jpg"
        else:
            filename = "latest_small.jpg"
        return f"{CDN_CAM_STILLS}/{region}/{alias}/{filename}"

    def get_camera_stream_url(self, alias: str) -> str:
        """
        Build the HLS playlist URL for a live camera stream.

        Parameters:
            alias : Camera alias (e.g. "hi-pipeline")

        Returns:
            HLS m3u8 URL string.

        Note: HLS streams at hls.cdn-surfline.com are protected by Cloudflare
        and require a valid Surfline premium subscription cookie/session.
        Direct access without authentication returns HTTP 403.

        Format: https://hls.cdn-surfline.com/oregon/{alias}/playlist.m3u8
        """
        return f"{CDN_HLS}/oregon/{alias}/playlist.m3u8"

    def get_camera_rewind_url(
        self,
        alias: str,
        hour: int = 1300,
        date: Optional[str] = None,
    ) -> str:
        """
        Build the URL for a camera rewind (replay) MP4 clip.

        Parameters:
            alias : Camera alias (e.g. "hi-pipeline")
            hour  : Time of day in HHMM format (e.g. 1300 = 1:00 PM local)
            date  : Date string "YYYY-MM-DD", defaults to today UTC

        Returns:
            URL string to the MP4 rewind clip.

        Format: https://camrewinds.cdn-surfline.com/{alias}/{alias}.{HHMM}.{DATE}.mp4

        Note: Rewind clips may require a premium subscription to access.
        """
        if date is None:
            date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        return f"{CDN_REWINDS}/{alias}/{alias}.{hour}.{date}.mp4"

    def get_spot_thumbnail_url(self, spot_id: str, size: int = 1500) -> str:
        """
        Build the CDN URL for a spot's thumbnail image.

        Parameters:
            spot_id : Surfline spot ID
            size    : Image size in px (common: 300, 600, 1500)

        Returns: HTTPS URL to the JPEG thumbnail.
        """
        return (
            f"{CDN_SPOT_THUMBNAILS}/spots/{spot_id}/{spot_id}_{size}.jpg"
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        query_size: int = 10,
        suggestion_size: int = 5,
        include_news: bool = True,
    ) -> dict:
        """
        Search Surfline for spots and news articles.

        Endpoint: GET /search/site
        Auth required: No

        Parameters:
            query           : Search string
            query_size      : Max number of hit results per index
            suggestion_size : Max number of autocomplete suggestions
            include_news    : Include news article results

        Returns a list of Elasticsearch response objects.  The first element
        (index 0) contains spot hits and spot-name autocomplete suggestions.
        Index 3 contains news/article hits.

        Spot hit fields (_source):
            name             -> spot display name
            breadCrumbs      -> ["Country", "Region", ...]
            location.lat/lon -> coordinates
            href             -> full Surfline URL for the spot report page
            cams[]           -> list of camera IDs attached to this spot
            insightsCameraId -> primary insights camera ID

        Usage example:
            results = client.search("pipeline")
            spot_hits = results[0]["hits"]["hits"]
            suggestions = results[0]["suggest"]["spot-suggest"][0]["options"]
            for s in suggestions:
                spot_id = s["_id"]
                name = s["_source"]["name"]
        """
        return self._get(
            "/search/site",
            params={
                "q": query,
                "querySize": query_size,
                "suggestionSize": suggestion_size,
                "newsSearch": str(include_news).lower(),
            },
        )

    def search_spots(self, query: str, limit: int = 10) -> list:
        """
        Simplified search returning a flat list of spot dicts.

        Each dict contains:
            id, name, breadcrumbs, lat, lon, href, cam_ids, insights_camera_id
        """
        raw = self.search(query, query_size=limit, include_news=False)
        spots = []
        if not raw or not isinstance(raw, list):
            return spots
        hits = raw[0].get("hits", {}).get("hits", []) if raw else []
        for h in hits:
            src = h.get("_source", {})
            loc = src.get("location", {})
            spots.append(
                {
                    "id": h.get("_id"),
                    "name": src.get("name"),
                    "breadcrumbs": src.get("breadCrumbs", []),
                    "lat": loc.get("lat"),
                    "lon": loc.get("lon"),
                    "href": src.get("href"),
                    "cam_ids": src.get("cams", []),
                    "insights_camera_id": src.get("insightsCameraId"),
                }
            )
        return spots

    def search_suggestions(self, query: str, limit: int = 5) -> list:
        """
        Return autocomplete spot suggestions for a partial query.

        Returns list of dicts: {id, name, breadcrumbs, lat, lon}
        """
        raw = self.search(query, suggestion_size=limit, include_news=False)
        if not raw or not isinstance(raw, list):
            return []
        suggest_block = raw[0].get("suggest", {}).get("spot-suggest", [])
        options = suggest_block[0].get("options", []) if suggest_block else []
        results = []
        for opt in options[:limit]:
            src = opt.get("_source", {})
            loc = src.get("location", {})
            results.append(
                {
                    "id": opt.get("_id"),
                    "name": src.get("name"),
                    "breadcrumbs": src.get("breadCrumbs", []),
                    "lat": loc.get("lat"),
                    "lon": loc.get("lon"),
                }
            )
        return results

    # ------------------------------------------------------------------
    # Authenticated: User Endpoints
    # ------------------------------------------------------------------

    def get_user_profile(self) -> dict:
        """
        Retrieve the authenticated user's profile.

        Endpoint: GET /user/profile
        Auth required: YES - Bearer token
        """
        self._require_auth()
        return self._get("/user/profile")

    def get_favorites(self) -> dict:
        """
        Retrieve the authenticated user's saved/favorited spots.

        Endpoint: GET /user/favorites
        Auth required: YES - Bearer token

        Returns dict containing lists of favorited spots and cameras.
        """
        self._require_auth()
        return self._get("/user/favorites")

    def get_user_feeds(self) -> dict:
        """
        Retrieve the authenticated user's personalized activity feed.

        Endpoint: GET /user/feeds
        Auth required: YES - Bearer token
        """
        self._require_auth()
        return self._get("/user/feeds")

    def _require_auth(self) -> None:
        if not self.is_authenticated:
            raise RuntimeError(
                "Authentication required. Call client.login(email, password) first."
            )

    # ------------------------------------------------------------------
    # Convenience / High-Level Methods
    # ------------------------------------------------------------------

    def get_current_conditions(self, spot_id: str) -> dict:
        """
        Return a summary of current surf conditions for a spot.

        This is a convenience method that parses get_spot_report() into a
        flat, easy-to-use dict.

        Returns:
            {
                "spot_id"       : str,
                "name"          : str,
                "lat"           : float,
                "lon"           : float,
                "rating"        : str,   # e.g. "FAIR"
                "wave_min_ft"   : int,
                "wave_max_ft"   : int,
                "wave_human"    : str,   # e.g. "Waist to shoulder"
                "wind_speed_kts": float,
                "wind_direction": float, # degrees
                "wind_type"     : str,   # "Offshore"/"Onshore"/"Cross-shore"
                "wind_gust_kts" : float,
                "tide_type"     : str,   # current tide type
                "tide_height_ft": float,
                "next_tide_type": str,
                "next_tide_ft"  : float,
                "water_temp_f"  : float, # average
                "swells"        : list,  # [{height, period, direction_deg, direction_cardinal}, ...]
                "cameras"       : list,  # [{id, title, still_url, stream_url, is_premium}, ...]
                "subregion"     : str,
                "timezone"      : str,
            }
        """
        report = self.get_spot_report(spot_id)
        spot = report.get("spot", {})
        forecast = report.get("forecast", {})

        wave_height = forecast.get("waveHeight", {})
        wind = forecast.get("wind", {})
        tide = forecast.get("tide", {})
        water_temp = forecast.get("waterTemp", {})
        swells_raw = forecast.get("swells", [])
        cameras_raw = spot.get("cameras", [])
        conditions = forecast.get("conditions", {})

        swells = []
        for s in swells_raw:
            if s.get("height", 0) > 0:
                swells.append(
                    {
                        "height_ft": s["height"],
                        "period_s": s["period"],
                        "direction_deg": s["direction"],
                        "direction_cardinal": _cardinal(s["direction"]),
                    }
                )

        cameras = []
        for c in cameras_raw:
            cameras.append(
                {
                    "id": c.get("_id"),
                    "title": c.get("title"),
                    "alias": c.get("alias"),
                    "still_url": c.get("stillUrl"),
                    "still_url_full": c.get("stillUrlFull"),
                    "stream_url": c.get("streamUrl"),
                    "rewind_clip": c.get("rewindClip"),
                    "is_premium": c.get("isPremium", False),
                    "is_down": c.get("status", {}).get("isDown", False),
                    "highlights_url": (c.get("highlights") or {}).get("url"),
                    "highlights_thumb": (c.get("highlights") or {}).get("thumbUrl"),
                }
            )

        current_tide = tide.get("current", {})
        next_tide = tide.get("next", {})
        water_avg = (water_temp.get("min", 0) + water_temp.get("max", 0)) / 2

        return {
            "spot_id": spot.get("_id"),
            "name": spot.get("name"),
            "lat": spot.get("lat"),
            "lon": spot.get("lon"),
            "rating": conditions.get("value"),
            "wave_min_ft": wave_height.get("min"),
            "wave_max_ft": wave_height.get("max"),
            "wave_human": wave_height.get("humanRelation"),
            "wind_speed_kts": wind.get("speed"),
            "wind_direction": wind.get("direction"),
            "wind_type": wind.get("directionType"),
            "wind_gust_kts": wind.get("gust"),
            "tide_type": current_tide.get("type"),
            "tide_height_ft": current_tide.get("height"),
            "next_tide_type": next_tide.get("type"),
            "next_tide_ft": next_tide.get("height"),
            "water_temp_f": round(water_avg, 1) if water_avg else None,
            "swells": swells,
            "cameras": cameras,
            "subregion": spot.get("subregion", {}).get("name"),
            "timezone": report.get("associated", {}).get("timezone"),
        }

    def get_forecast_summary(
        self,
        spot_id: str,
        days: int = 3,
    ) -> list:
        """
        Return a simplified list of hourly forecast dicts for a spot.

        Each entry contains merged wave, wind, and rating data.

        Returns list of dicts:
            {
                "timestamp"      : int,
                "datetime_local" : datetime,
                "wave_min_ft"    : int,
                "wave_max_ft"    : int,
                "wave_plus"      : bool,
                "wave_human"     : str,
                "wave_power"     : float,
                "wind_speed_kts" : float,
                "wind_direction" : float,
                "wind_type"      : str,
                "wind_gust_kts"  : float,
                "rating_key"     : str,
                "rating_value"   : int,
                "swells"         : list,
            }
        """
        wave_resp = self.get_wave_forecast(spot_id, days=days, interval_hours=1)
        wind_resp = self.get_wind_forecast(spot_id, days=days, interval_hours=1)
        rating_resp = self.get_surf_rating(spot_id, days=days, interval_hours=1)

        wave_data = wave_resp.get("data", {}).get("wave", [])
        wind_data = wind_resp.get("data", {}).get("wind", [])
        rating_data = rating_resp.get("data", {}).get("rating", [])

        # Index wind and rating by timestamp
        wind_by_ts = {w["timestamp"]: w for w in wind_data}
        rating_by_ts = {r["timestamp"]: r for r in rating_data}

        result = []
        for w in wave_data:
            ts = w["timestamp"]
            utc_off = w.get("utcOffset", 0)
            surf = w.get("surf", {})
            wind = wind_by_ts.get(ts, {})
            rating = rating_by_ts.get(ts, {}).get("rating", {})

            swells = []
            for s in w.get("swells", []):
                if s.get("height", 0) > 0:
                    swells.append(
                        {
                            "height_ft": s["height"],
                            "period_s": s["period"],
                            "direction_deg": s["direction"],
                            "direction_cardinal": _cardinal(s["direction"]),
                            "power": s.get("power", 0),
                        }
                    )

            result.append(
                {
                    "timestamp": ts,
                    "datetime_local": _ts_to_dt(ts, utc_off),
                    "wave_min_ft": surf.get("min"),
                    "wave_max_ft": surf.get("max"),
                    "wave_plus": surf.get("plus", False),
                    "wave_human": surf.get("humanRelation"),
                    "wave_power": w.get("power"),
                    "wind_speed_kts": wind.get("speed"),
                    "wind_direction": wind.get("direction"),
                    "wind_type": wind.get("directionType"),
                    "wind_gust_kts": wind.get("gust"),
                    "rating_key": rating.get("key"),
                    "rating_value": rating.get("value"),
                    "swells": swells,
                }
            )
        return result

    def get_tide_summary(self, spot_id: str, days: int = 5) -> list:
        """
        Return only HIGH and LOW tide events as a list of dicts.

        Returns:
            [{"type": "HIGH"|"LOW", "height_ft": float, "datetime_local": datetime}, ...]
        """
        resp = self.get_tide_forecast(spot_id, days=days)
        tides = resp.get("data", {}).get("tides", [])
        utc_off = resp.get("associated", {}).get("utcOffset", 0)
        events = []
        for t in tides:
            if t["type"] in ("HIGH", "LOW"):
                events.append(
                    {
                        "type": t["type"],
                        "height_ft": t["height"],
                        "datetime_local": _ts_to_dt(t["timestamp"], utc_off),
                        "timestamp": t["timestamp"],
                    }
                )
        return events


# ---------------------------------------------------------------------------
# CDN URL Builders (standalone functions)
# ---------------------------------------------------------------------------

def cam_still_url(alias: str, size: str = "small", region: str = "us-west-2") -> str:
    """
    Build a publicly accessible still image URL for a camera.

    CDN: https://camstills.cdn-surfline.com/{region}/{alias}/latest_{size}.jpg

    Parameters:
        alias  : Camera alias slug (e.g. "hi-pipeline")
        size   : "small" (320px wide) or "full" (full resolution)
        region : AWS region (default "us-west-2")

    Note: Still image CDN is publicly accessible without authentication.
    """
    fname = "latest_full.jpg" if size == "full" else "latest_small.jpg"
    return f"{CDN_CAM_STILLS}/{region}/{alias}/{fname}"


def cam_pixelated_still_url(alias: str) -> str:
    """
    Build the URL for the blurred/pixelated still preview (shown to non-subscribers).

    CDN: https://camstills.cdn-surfline.com/{alias}/latest_small_pixelated.png
    """
    return f"{CDN_CAM_STILLS}/{alias}/latest_small_pixelated.png"


def cam_hls_url(alias: str, region: str = "oregon") -> str:
    """
    Build the HLS m3u8 stream URL for a live camera.

    CDN: https://hls.cdn-surfline.com/{region}/{alias}/playlist.m3u8

    Parameters:
        alias  : Camera alias slug (e.g. "hi-pipeline")
        region : CDN edge region prefix. Observed values:
                   "oregon"   – US West Coast & Hawaii
                   "ohio"     – US East Coast
                   "ireland"  – Europe
                   "east-au"  – Australia East
                   "west-au"  – Australia West
                 The correct region for a camera is available in
                 streamUrl from the mapview/spot report response.

    Note: Requires a valid Surfline premium subscription session cookie.
    Direct access returns HTTP 403 Forbidden from Cloudflare.
    """
    return f"{CDN_HLS}/{region}/{alias}/playlist.m3u8"


def cam_rewind_url(alias: str, resolution: int = 1500, date: Optional[str] = None) -> str:
    """
    Build the rewind MP4 clip URL for a camera.

    CDN: https://camrewinds.cdn-surfline.com/{alias}/{alias}.{resolution}.{YYYY-MM-DD}.mp4

    Parameters:
        alias      : Camera alias slug (e.g. "hi-pipeline")
        resolution : Video resolution/quality identifier.  Observed value: 1500.
                     The "rewindClip" field in the API response contains the
                     pre-built URL with this value already set.
        date       : Date as "YYYY-MM-DD", defaults to today UTC

    Note: The rewind clip CDN (camrewinds.cdn-surfline.com) returns HTTP 403
    without authentication.  Access requires a Surfline premium session.
    """
    if date is None:
        date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    return f"{CDN_REWINDS}/{alias}/{alias}.{resolution}.{date}.mp4"


def cam_highlight_url(camera_id: str, timestamp_str: str) -> str:
    """
    Build the URL for a camera highlight clip MP4.

    CDN: https://highlights.cdn-surfline.com/us-west-2/clips/{cameraId}-{timestampStr}.mp4

    Parameters:
        camera_id     : Camera _id hex string (e.g. "58349eed3421b20545c4b56c")
        timestamp_str : ISO-format timestamp component as it appears in the
                        highlights.url field from the API response
                        (e.g. "20260327T161450174Z")

    Note: Highlight clip MP4s and their JPEG thumbnails are PUBLICLY accessible
    (HTTP 200) without authentication, unlike HLS streams.
    The pre-built URL is available in cam.highlights.url from the API response.

    Thumbnail URL pattern:
        https://highlights.cdn-surfline.com/us-west-2/thumbnails/{cameraId}-{timestampStr}.jpg
    """
    return f"{CDN_HIGHLIGHTS}/us-west-2/clips/{camera_id}-{timestamp_str}.mp4"


def cam_highlight_thumb_url(camera_id: str, timestamp_str: str) -> str:
    """
    Build the URL for a camera highlight clip thumbnail JPEG.

    Publicly accessible (HTTP 200) without authentication.

    CDN: https://highlights.cdn-surfline.com/us-west-2/thumbnails/{cameraId}-{timestampStr}.jpg
    """
    return f"{CDN_HIGHLIGHTS}/us-west-2/thumbnails/{camera_id}-{timestamp_str}.jpg"


def spot_thumbnail_url(spot_id: str, size: int = 1500) -> str:
    """
    Build the CDN URL for a spot's background thumbnail image.

    CDN: https://spot-thumbnails.cdn-surfline.com/spots/{spotId}/{spotId}_{size}.jpg
    """
    return f"{CDN_SPOT_THUMBNAILS}/spots/{spot_id}/{spot_id}_{size}.jpg"


# ---------------------------------------------------------------------------
# Quick-start example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    client = SurflineClient()

    # ----- Search for a spot -----
    print("=== Searching for 'Pipeline' ===")
    results = client.search_spots("pipeline", limit=3)
    for r in results:
        print(f"  {r['name']} ({r['id']}) - {' > '.join(r['breadcrumbs'])}")

    pipeline_id = "5842041f4e65fad6a7708890"

    # ----- Current conditions -----
    print("\n=== Current Conditions: Pipeline ===")
    cond = client.get_current_conditions(pipeline_id)
    print(f"  Rating      : {cond['rating']}")
    print(f"  Wave height : {cond['wave_min_ft']}-{cond['wave_max_ft']} ft  ({cond['wave_human']})")
    print(f"  Wind        : {cond['wind_speed_kts']:.1f} KTS {cond['wind_type']} ({_cardinal(cond['wind_direction'] or 0)})")
    print(f"  Water temp  : {cond['water_temp_f']} F")
    print(f"  Tide        : {cond['tide_type']} at {cond['tide_height_ft']} ft -> next {cond['next_tide_type']} at {cond['next_tide_ft']} ft")
    if cond["swells"]:
        print("  Swells:")
        for s in cond["swells"]:
            print(f"    {s['height_ft']:.1f} ft @ {s['period_s']}s from {s['direction_cardinal']}")

    # ----- Cameras -----
    print("\n=== Cameras ===")
    for cam in cond["cameras"][:3]:
        print(f"  {cam['title']}  premium={cam['is_premium']}  down={cam['is_down']}")
        print(f"    still : {cam['still_url']}")
        print(f"    stream: {cam['stream_url']}")

    # ----- Tide events -----
    print("\n=== Tide Events (next 2 days) ===")
    tides = client.get_tide_summary(pipeline_id, days=2)
    for t in tides[:6]:
        print(f"  {t['type']:4s}  {t['height_ft']:5.1f} ft  {t['datetime_local'].strftime('%a %I:%M %p')}")

    # ----- Hourly forecast summary -----
    print("\n=== Hourly Forecast (first 6 hrs) ===")
    forecast = client.get_forecast_summary(pipeline_id, days=1)
    for f in forecast[:6]:
        dt = f["datetime_local"]
        print(
            f"  {dt.strftime('%H:%M')}  {f['wave_min_ft']}-{f['wave_max_ft']} ft  "
            f"wind {(f['wind_speed_kts'] or 0):.0f}KTS {f['wind_type'] or ''}  "
            f"rating {f['rating_key']}"
        )

    # ----- Spots in Hawaii bounding box -----
    print("\n=== Spots in North Shore Hawaii ===")
    hawaii_data = client.get_spots_in_bbox(
        south=21.5, north=21.8, west=-158.2, east=-157.8
    )
    spots = hawaii_data.get("data", {}).get("spots", [])
    print(f"  Found {len(spots)} spots")
    for s in spots[:5]:
        n_cams = len(s.get("cameras", []))
        print(f"  {s['name']}  ({n_cams} cameras)")
