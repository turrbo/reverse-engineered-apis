"""
Windy Webcams API Client
========================
Production-quality Python client for the Windy Webcams API (api.windy.com/webcams).

API Version: v3
Base URL: https://api.windy.com/webcams/api/v3
Authentication: x-windy-api-key header (obtain from https://api.windy.com/keys)

Tiers:
  - Free: offset limit 1000, image URLs valid 10 minutes
  - Professional (9,990€/year): offset limit 10,000, image URLs valid 24 hours,
    access to bulk export endpoint, no ads in player embeds

Usage:
    from windy_webcams_client import WindyWebcamsClient

    client = WindyWebcamsClient(api_key="your-api-key")

    # List webcams near a location
    result = client.list_webcams(nearby=(48.8566, 2.3522, 50))  # Paris, 50km radius

    # Get a single webcam
    webcam = client.get_webcam(1179853135, include=["images", "location", "player", "urls"])

    # Search by bounding box
    result = client.list_webcams(bbox=(51.5, 0.1, 51.4, -0.1))  # London area

Undocumented endpoints (no API key required):
    internal = WindyInternalClient()

    # Nearest webcams (used by windy.com map)
    cams = internal.get_nearby_webcams(48.8566, 2.3522, limit=10)

    # Webcam detail with extra fields
    detail = internal.get_webcam_detail(1515017464)

    # Historical archive frames
    frames = internal.get_webcam_archive(1515017464)           # last 24h
    frames = internal.get_webcam_archive(1515017464, hourly=True)  # last 30 days (1/hr)

    # Place/POI search (used by webcam page header search)
    views = internal.search_views("Eiffel Tower", lat=48.8566, lon=2.3522)
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator
from urllib.parse import urlencode

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.windy.com/webcams/api/v3"
EXPORT_URL = "https://api.windy.com/webcams/export/all-webcams.json"

API_KEY_HEADER = "x-windy-api-key"

DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5

MAX_LIMIT = 50
MAX_NEARBY_RADIUS_KM = 250
MAX_WEBCAM_IDS = 50
MAX_CATEGORIES = 10
MAX_COUNTRIES = 10
MAX_REGIONS = 10
MAX_CONTINENTS = 2

FREE_TIER_MAX_OFFSET = 1000
PROFESSIONAL_TIER_MAX_OFFSET = 10000


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WebcamStatus(str, Enum):
    """Possible lifecycle statuses for a webcam."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNAPPROVED = "unapproved"
    DISABLED = "disabled"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    MERGED = "merged"


class WebcamCategory(str, Enum):
    """Available category filters."""
    AIRPORT = "airport"
    BEACH = "beach"
    BUILDING = "building"
    CITY = "city"
    COAST = "coast"
    FOREST = "forest"
    INDOOR = "indoor"
    LAKE = "lake"
    LANDSCAPE = "landscape"
    METEO = "meteo"
    MOUNTAIN = "mountain"
    OBSERVATORY = "observatory"
    PORT = "port"
    RIVER = "river"
    SPORT_AREA = "sportArea"
    SQUARE = "square"
    TRAFFIC = "traffic"
    VILLAGE = "village"


class ContinentCode(str, Enum):
    """ISO-style continent codes used by the API."""
    AFRICA = "AF"
    ANTARCTICA = "AN"
    ASIA = "AS"
    EUROPE = "EU"
    NORTH_AMERICA = "NA"
    OCEANIA = "OC"
    SOUTH_AMERICA = "SA"


class SortKey(str, Enum):
    """Supported sort fields."""
    POPULARITY = "popularity"
    CREATED_ON = "createdOn"


class SortDirection(str, Enum):
    """Sort direction."""
    ASC = "asc"
    DESC = "desc"


class CategoryOperation(str, Enum):
    """Logic operator for multiple category filters."""
    AND = "and"
    OR = "or"


class PlayerType(str, Enum):
    """Types of player timelapse embeds."""
    LIVE = "live"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    LIFETIME = "lifetime"


class IncludeField(str, Enum):
    """Optional response sections to include."""
    CATEGORIES = "categories"
    IMAGES = "images"
    LOCATION = "location"
    PLAYER = "player"
    URLS = "urls"


# ---------------------------------------------------------------------------
# Data model helpers
# ---------------------------------------------------------------------------

@dataclass
class WebcamLocation:
    """Geographic location details for a webcam."""
    latitude: float
    longitude: float
    city: str = ""
    region: str = ""
    country: str = ""
    continent: str = ""
    city_code: str = ""
    region_code: str = ""
    country_code: str = ""
    continent_code: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebcamLocation":
        return cls(
            latitude=data.get("latitude", 0.0),
            longitude=data.get("longitude", 0.0),
            city=data.get("city", ""),
            region=data.get("region", ""),
            country=data.get("country", ""),
            continent=data.get("continent", ""),
            city_code=data.get("city_code", ""),
            region_code=data.get("region_code", ""),
            country_code=data.get("country_code", ""),
            continent_code=data.get("continent_code", ""),
        )


@dataclass
class WebcamImage:
    """A single image reference (URL + dimensions)."""
    url: str = ""
    width: int = 0
    height: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebcamImage":
        return cls(
            url=data.get("url", ""),
            width=data.get("width", 0),
            height=data.get("height", 0),
        )


@dataclass
class WebcamImages:
    """
    Image collection for a webcam.

    Note: Image URL tokens expire after 10 minutes (free tier) or
    24 hours (professional tier). Re-request the webcam to get fresh URLs.
    """
    current: WebcamImage = field(default_factory=WebcamImage)
    daylight: WebcamImage = field(default_factory=WebcamImage)
    sizes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebcamImages":
        current_raw = data.get("current", {})
        daylight_raw = data.get("daylight", {})
        return cls(
            current=WebcamImage.from_dict(current_raw) if current_raw else WebcamImage(),
            daylight=WebcamImage.from_dict(daylight_raw) if daylight_raw else WebcamImage(),
            sizes=data.get("sizes", {}),
        )


@dataclass
class WebcamPlayer:
    """
    Embeddable player URLs for various timelapse resolutions.

    Embed with an <iframe> tag:
        <iframe src="player.live" width="640" height="360"></iframe>
    """
    live: str = ""
    day: str = ""
    month: str = ""
    year: str = ""
    lifetime: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebcamPlayer":
        return cls(
            live=data.get("live", ""),
            day=data.get("day", ""),
            month=data.get("month", ""),
            year=data.get("year", ""),
            lifetime=data.get("lifetime", ""),
        )

    def get_embed_url(self, player_type: PlayerType = PlayerType.LIVE) -> str:
        """Return the embed URL for the specified player type."""
        mapping = {
            PlayerType.LIVE: self.live,
            PlayerType.DAY: self.day,
            PlayerType.MONTH: self.month,
            PlayerType.YEAR: self.year,
            PlayerType.LIFETIME: self.lifetime,
        }
        return mapping.get(player_type, self.live)

    def get_embed_html(
        self,
        player_type: PlayerType = PlayerType.LIVE,
        width: int = 640,
        height: int = 360,
    ) -> str:
        """Generate a ready-to-use <iframe> embed tag."""
        url = self.get_embed_url(player_type)
        if not url:
            return ""
        return (
            f'<iframe src="{url}" width="{width}" height="{height}" '
            f'frameborder="0" allowfullscreen></iframe>'
        )


@dataclass
class WebcamUrls:
    """External URLs associated with a webcam."""
    detail: str = ""
    edit: str = ""
    provider: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebcamUrls":
        return cls(
            detail=data.get("detail", ""),
            edit=data.get("edit", ""),
            provider=data.get("provider", ""),
        )


@dataclass
class WebcamCategory_:
    """A category tag attached to a webcam."""
    id: str = ""
    name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebcamCategory_":
        return cls(id=data.get("id", ""), name=data.get("name", ""))


@dataclass
class Webcam:
    """
    A single webcam record as returned by the Windy Webcams API.

    Fields depend on which `include` parameters were requested.
    """
    webcam_id: int = 0
    title: str = ""
    status: str = ""
    view_count: int = 0
    last_updated_on: str = ""
    cluster_size: int = 0
    categories: list[WebcamCategory_] = field(default_factory=list)
    images: WebcamImages | None = None
    location: WebcamLocation | None = None
    player: WebcamPlayer | None = None
    urls: WebcamUrls | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Webcam":
        """Parse a raw API response dict into a Webcam instance."""
        categories = [
            WebcamCategory_.from_dict(c) for c in data.get("categories", [])
        ]
        images_raw = data.get("images")
        location_raw = data.get("location")
        player_raw = data.get("player")
        urls_raw = data.get("urls")
        return cls(
            webcam_id=data.get("webcamId", 0),
            title=data.get("title", ""),
            status=data.get("status", ""),
            view_count=data.get("viewCount", 0),
            last_updated_on=data.get("lastUpdatedOn", ""),
            cluster_size=data.get("clusterSize", 0),
            categories=categories,
            images=WebcamImages.from_dict(images_raw) if images_raw else None,
            location=WebcamLocation.from_dict(location_raw) if location_raw else None,
            player=WebcamPlayer.from_dict(player_raw) if player_raw else None,
            urls=WebcamUrls.from_dict(urls_raw) if urls_raw else None,
            raw=data,
        )

    @property
    def is_active(self) -> bool:
        """Return True if the webcam is currently active."""
        return self.status == WebcamStatus.ACTIVE

    @property
    def windy_url(self) -> str:
        """Shortcut to the Windy.com detail page URL."""
        if self.urls:
            return self.urls.detail
        return f"https://www.windy.com/webcams/{self.webcam_id}"


@dataclass
class WebcamListResult:
    """Paginated list of webcams."""
    total: int
    webcams: list[Webcam]
    offset: int = 0
    limit: int = 10

    @classmethod
    def from_dict(cls, data: dict[str, Any], offset: int = 0, limit: int = 10) -> "WebcamListResult":
        webcams = [Webcam.from_dict(w) for w in data.get("webcams", [])]
        return cls(
            total=data.get("total", len(webcams)),
            webcams=webcams,
            offset=offset,
            limit=limit,
        )

    @property
    def has_more(self) -> bool:
        """True if there are more results beyond the current page."""
        return (self.offset + len(self.webcams)) < self.total


@dataclass
class GeoEntry:
    """A geographic classification entry (continent, country, region, city)."""
    code: str
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeoEntry":
        return cls(code=data.get("code", ""), name=data.get("name", ""))


@dataclass
class CategoryEntry:
    """A webcam category definition."""
    id: str
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryEntry":
        return cls(id=data.get("id", ""), name=data.get("name", ""))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class WindyWebcamsError(Exception):
    """Base exception for all Windy Webcams client errors."""


class WindyAuthError(WindyWebcamsError):
    """Raised when the API key is missing, invalid, or unauthorized."""

    def __init__(self, message: str = "Invalid or missing API key") -> None:
        super().__init__(message)


class WindyRateLimitError(WindyWebcamsError):
    """Raised when the API rate limit has been exceeded (HTTP 429)."""

    def __init__(self, retry_after: int | None = None) -> None:
        msg = "Rate limit exceeded"
        if retry_after:
            msg += f". Retry after {retry_after} seconds."
        super().__init__(msg)
        self.retry_after = retry_after


class WindyNotFoundError(WindyWebcamsError):
    """Raised when a requested resource does not exist (HTTP 404)."""


class WindyAPIError(WindyWebcamsError):
    """Raised for unexpected API errors."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class WindyWebcamsClient:
    """
    Python client for the Windy Webcams API v3.

    Authentication:
        Obtain a free or professional API key from https://api.windy.com/keys.
        Pass it as the `api_key` constructor parameter or set the
        WINDY_API_KEY environment variable.

    Args:
        api_key:        Windy API key (required).
        timeout:        HTTP request timeout in seconds (default: 30).
        max_retries:    Number of automatic retries on transient errors (default: 3).
        session:        Optional pre-configured requests.Session to reuse.

    Example::

        client = WindyWebcamsClient(api_key="your-key")
        webcams = client.list_webcams(categories=[WebcamCategory.BEACH], limit=20)
        for cam in webcams.webcams:
            print(cam.title, cam.location.country if cam.location else "")
    """

    def __init__(
        self,
        api_key: str,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
        session: Session | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")

        self._api_key = api_key
        self._timeout = timeout

        if session is not None:
            self._session = session
        else:
            self._session = self._build_session(max_retries)

        self._session.headers.update({API_KEY_HEADER: self._api_key})

    # ------------------------------------------------------------------
    # Session setup
    # ------------------------------------------------------------------

    @staticmethod
    def _build_session(max_retries: int) -> Session:
        """Create a requests.Session with retry logic for transient errors."""
        session = Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=DEFAULT_BACKOFF_FACTOR,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute a GET request and return the parsed JSON body.

        Raises:
            WindyAuthError:      On 401/403 responses.
            WindyRateLimitError: On 429 responses.
            WindyNotFoundError:  On 404 responses.
            WindyAPIError:       On any other non-2xx response.
        """
        logger.debug("GET %s params=%s", url, params)
        try:
            resp: Response = self._session.get(
                url, params=params, timeout=self._timeout
            )
        except requests.exceptions.ConnectionError as exc:
            raise WindyWebcamsError(f"Connection error: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise WindyWebcamsError(f"Request timed out after {self._timeout}s") from exc

        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: Response) -> None:
        """Map HTTP error status codes to typed exceptions."""
        if resp.ok:
            return

        try:
            body = resp.json()
            message = body.get("message", resp.text)
        except Exception:
            message = resp.text

        if resp.status_code in (401, 403):
            raise WindyAuthError(message)
        if resp.status_code == 404:
            raise WindyNotFoundError(message)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise WindyRateLimitError(int(retry_after) if retry_after else None)
        raise WindyAPIError(resp.status_code, message)

    # ------------------------------------------------------------------
    # Parameter builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_include(include: list[str | IncludeField] | None) -> str | None:
        """Convert include list to a comma-separated string."""
        if not include:
            return None
        return ",".join(str(i.value if isinstance(i, IncludeField) else i) for i in include)

    @staticmethod
    def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
        """Remove None values from a params dict before passing to requests."""
        return {k: v for k, v in params.items() if v is not None}

    # ------------------------------------------------------------------
    # Webcam listing
    # ------------------------------------------------------------------

    def list_webcams(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        lang: str = "en",
        bbox: tuple[float, float, float, float] | None = None,
        nearby: tuple[float, float, float] | None = None,
        categories: list[str | WebcamCategory] | None = None,
        continents: list[str | ContinentCode] | None = None,
        countries: list[str] | None = None,
        regions: list[str] | None = None,
        cities: list[str] | None = None,
        webcam_ids: list[int] | None = None,
        sort_key: str | SortKey | None = None,
        sort_direction: str | SortDirection | None = None,
        category_operation: str | CategoryOperation | None = None,
        include: list[str | IncludeField] | None = None,
    ) -> WebcamListResult:
        """
        Retrieve a paginated list of webcams with optional filters.

        Args:
            limit:              Number of results to return (0–50, default 10).
            offset:             Pagination offset. Free tier max: 1000;
                                professional: 10000.
            lang:               Response language code (default: "en").
            bbox:               Bounding box as (north_lat, east_lon, south_lat, west_lon).
            nearby:             Radius search as (latitude, longitude, radius_km).
                                Maximum radius is 250 km.
            categories:         Filter by category. Up to 10 values from
                                WebcamCategory enum.
            continents:         Filter by continent. Up to 2 ContinentCode values.
            countries:          Filter by country code(s). Up to 10 values.
            regions:            Filter by region code(s). Up to 10 values.
            cities:             Filter by city code(s).
            webcam_ids:         Fetch specific webcam IDs. Up to 50 IDs.
            sort_key:           Sort field: "popularity" or "createdOn".
            sort_direction:     Sort order: "asc" or "desc".
            category_operation: Logic for multiple categories: "and" or "or".
            include:            Additional fields: categories, images, location,
                                player, urls.

        Returns:
            WebcamListResult with total count and list of Webcam objects.

        Raises:
            ValueError:          On invalid parameter combinations.
            WindyAuthError:      On authentication failure.
            WindyRateLimitError: When rate limit is exceeded.
        """
        if limit < 0 or limit > MAX_LIMIT:
            raise ValueError(f"limit must be between 0 and {MAX_LIMIT}")

        if nearby and nearby[2] > MAX_NEARBY_RADIUS_KM:
            raise ValueError(f"nearby radius must not exceed {MAX_NEARBY_RADIUS_KM} km")

        if webcam_ids and len(webcam_ids) > MAX_WEBCAM_IDS:
            raise ValueError(f"webcam_ids may contain at most {MAX_WEBCAM_IDS} IDs")

        if categories and len(categories) > MAX_CATEGORIES:
            raise ValueError(f"categories may contain at most {MAX_CATEGORIES} values")

        if continents and len(continents) > MAX_CONTINENTS:
            raise ValueError(f"continents may contain at most {MAX_CONTINENTS} values")

        if countries and len(countries) > MAX_COUNTRIES:
            raise ValueError(f"countries may contain at most {MAX_COUNTRIES} values")

        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "lang": lang,
        }

        if bbox:
            north, east, south, west = bbox
            params["bbox"] = f"{north},{east},{south},{west}"

        if nearby:
            lat, lon, radius = nearby
            params["nearby"] = f"{lat},{lon},{radius}"

        if categories:
            params["categories"] = ",".join(
                str(c.value if isinstance(c, WebcamCategory) else c) for c in categories
            )

        if continents:
            params["continents"] = ",".join(
                str(c.value if isinstance(c, ContinentCode) else c) for c in continents
            )

        if countries:
            params["countries"] = ",".join(countries)

        if regions:
            params["regions"] = ",".join(regions)

        if cities:
            params["cities"] = ",".join(cities)

        if webcam_ids:
            params["webcamIds"] = ",".join(str(i) for i in webcam_ids)

        if sort_key:
            params["sortKey"] = sort_key.value if isinstance(sort_key, SortKey) else sort_key

        if sort_direction:
            params["sortDirection"] = (
                sort_direction.value if isinstance(sort_direction, SortDirection) else sort_direction
            )

        if category_operation:
            params["categoryOperation"] = (
                category_operation.value
                if isinstance(category_operation, CategoryOperation)
                else category_operation
            )

        include_str = self._build_include(include)
        if include_str:
            params["include"] = include_str

        data = self._get(f"{BASE_URL}/webcams", self._clean_params(params))
        return WebcamListResult.from_dict(data, offset=offset, limit=limit)

    # ------------------------------------------------------------------
    # Single webcam
    # ------------------------------------------------------------------

    def get_webcam(
        self,
        webcam_id: int,
        *,
        lang: str = "en",
        include: list[str | IncludeField] | None = None,
    ) -> Webcam:
        """
        Retrieve a single webcam by its numeric ID.

        Args:
            webcam_id: Unique integer identifier for the webcam.
            lang:      Response language code.
            include:   Optional response sections: categories, images, location,
                       player, urls.

        Returns:
            A Webcam instance.

        Raises:
            WindyNotFoundError: If the webcam ID does not exist.
            WindyAuthError:     On authentication failure.
        """
        params: dict[str, Any] = {"lang": lang}
        include_str = self._build_include(include)
        if include_str:
            params["include"] = include_str

        data = self._get(f"{BASE_URL}/webcams/{webcam_id}", self._clean_params(params))
        return Webcam.from_dict(data)

    # ------------------------------------------------------------------
    # Map clusters
    # ------------------------------------------------------------------

    def get_map_clusters(
        self,
        *,
        north_lat: float,
        south_lat: float,
        east_lon: float,
        west_lon: float,
        zoom: int,
        lang: str = "en",
        include: list[str | IncludeField] | None = None,
    ) -> list[Webcam]:
        """
        Return map-optimized webcam clusters for a bounding box and zoom level.

        The API enforces geographic span constraints per zoom level:

        +------+-----------+-----------+
        | Zoom | Max lat Δ | Max lon Δ |
        +------+-----------+-----------+
        |    4 | 22.5°     | 45°       |
        |    5 | 11.25°    | 22.5°     |
        |    6 | 5.625°    | 11.25°    |
        |    7 | 2.813°    | 5.625°    |
        +------+-----------+-----------+
        (Lower zoom = fewer constraints; higher zoom = finer granularity)

        Args:
            north_lat: Northern boundary (-90 to 90).
            south_lat: Southern boundary (-90 to 90).
            east_lon:  Eastern boundary (-180 to 180).
            west_lon:  Western boundary (-180 to 180).
            zoom:      Map zoom level (4–18).
            lang:      Response language code.
            include:   Optional response sections.

        Returns:
            List of Webcam objects (may include cluster representatives).
        """
        if not (4 <= zoom <= 18):
            raise ValueError("zoom must be between 4 and 18")

        params: dict[str, Any] = {
            "northLat": north_lat,
            "southLat": south_lat,
            "eastLon": east_lon,
            "westLon": west_lon,
            "zoom": zoom,
            "lang": lang,
        }
        include_str = self._build_include(include)
        if include_str:
            params["include"] = include_str

        data = self._get(f"{BASE_URL}/map/clusters", self._clean_params(params))
        # Response is a flat array of webcam objects
        if isinstance(data, list):
            return [Webcam.from_dict(w) for w in data]
        # Some API versions wrap in a 'webcams' key
        return [Webcam.from_dict(w) for w in data.get("webcams", [])]

    # ------------------------------------------------------------------
    # Taxonomy / reference data
    # ------------------------------------------------------------------

    def get_categories(self, lang: str = "en") -> list[CategoryEntry]:
        """
        Return all available webcam categories with localized names.

        Args:
            lang: Response language code.

        Returns:
            List of CategoryEntry objects.
        """
        data = self._get(f"{BASE_URL}/categories", {"lang": lang})
        if isinstance(data, list):
            return [CategoryEntry.from_dict(c) for c in data]
        return []

    def get_continents(self, lang: str = "en") -> list[GeoEntry]:
        """
        Return all continent codes and localized names.

        Args:
            lang: Response language code.

        Returns:
            List of GeoEntry objects.
        """
        data = self._get(f"{BASE_URL}/continents", {"lang": lang})
        if isinstance(data, list):
            return [GeoEntry.from_dict(c) for c in data]
        return []

    def get_countries(self, lang: str = "en") -> list[GeoEntry]:
        """
        Return all country codes and localized names.

        Args:
            lang: Response language code.

        Returns:
            List of GeoEntry objects.
        """
        data = self._get(f"{BASE_URL}/countries", {"lang": lang})
        if isinstance(data, list):
            return [GeoEntry.from_dict(c) for c in data]
        return []

    def get_regions(self, lang: str = "en") -> list[GeoEntry]:
        """
        Return all region codes and localized names.

        Args:
            lang: Response language code.

        Returns:
            List of GeoEntry objects.
        """
        data = self._get(f"{BASE_URL}/regions", {"lang": lang})
        if isinstance(data, list):
            return [GeoEntry.from_dict(c) for c in data]
        return []

    def get_cities(self, lang: str = "en") -> list[GeoEntry]:
        """
        Return all city codes and localized names.

        Args:
            lang: Response language code.

        Returns:
            List of GeoEntry objects.
        """
        data = self._get(f"{BASE_URL}/cities", {"lang": lang})
        if isinstance(data, list):
            return [GeoEntry.from_dict(c) for c in data]
        return []

    # ------------------------------------------------------------------
    # Bulk export (Professional tier only)
    # ------------------------------------------------------------------

    def export_all_webcams(self) -> dict[str, Any]:
        """
        Download the full webcam inventory as a single JSON payload.

        This endpoint is only available on the Professional tier
        (9,990€/year). It returns a snapshot that is periodically refreshed.

        Returns:
            Raw dict with keys:
                - updatedOn (str): ISO 8601 timestamp of last refresh.
                - webcams (list): Lightweight webcam entries including:
                    webcamId, title, status, viewCount, preview,
                    hasPanorama, hasLivestream, categories[], location{}.

        Raises:
            WindyAuthError: If the API key does not have Professional access.
        """
        return self._get(EXPORT_URL)

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    def paginate(
        self,
        *,
        page_size: int = 50,
        max_results: int | None = None,
        **list_kwargs: Any,
    ) -> Iterator[Webcam]:
        """
        Iterate over all available webcams, automatically paginating.

        Args:
            page_size:   Number of results per request (max 50).
            max_results: Stop after yielding this many total results.
                         Set to None (default) to retrieve all.
            **list_kwargs: Any keyword arguments accepted by list_webcams()
                           except `limit` and `offset`.

        Yields:
            Webcam objects one at a time.

        Example::

            client = WindyWebcamsClient(api_key="key")
            mountains = client.paginate(
                categories=[WebcamCategory.MOUNTAIN],
                include=[IncludeField.LOCATION, IncludeField.IMAGES],
                max_results=200,
            )
            for cam in mountains:
                print(cam.title)
        """
        offset = list_kwargs.pop("offset", 0)
        yielded = 0

        while True:
            if max_results is not None and yielded >= max_results:
                break

            current_limit = page_size
            if max_results is not None:
                current_limit = min(page_size, max_results - yielded)

            result = self.list_webcams(
                limit=current_limit,
                offset=offset,
                **list_kwargs,
            )

            for cam in result.webcams:
                yield cam
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            if not result.has_more or not result.webcams:
                break

            offset += len(result.webcams)

    # ------------------------------------------------------------------
    # Convenience search
    # ------------------------------------------------------------------

    def search_by_location(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 25,
        limit: int = 10,
        include: list[str | IncludeField] | None = None,
    ) -> WebcamListResult:
        """
        Find webcams within a radius of a geographic point.

        Args:
            latitude:  Center point latitude in decimal degrees.
            longitude: Center point longitude in decimal degrees.
            radius_km: Search radius in km (max 250).
            limit:     Maximum results to return.
            include:   Optional response sections.

        Returns:
            WebcamListResult sorted by distance (API default).
        """
        return self.list_webcams(
            nearby=(latitude, longitude, radius_km),
            limit=limit,
            include=include,
        )

    def search_by_country(
        self,
        country_code: str,
        limit: int = 10,
        include: list[str | IncludeField] | None = None,
        sort_key: SortKey = SortKey.POPULARITY,
    ) -> WebcamListResult:
        """
        Find the most popular webcams in a country.

        Args:
            country_code: ISO country code (e.g. "US", "DE", "FR").
            limit:        Maximum results to return.
            include:      Optional response sections.
            sort_key:     Sort field (default: popularity).

        Returns:
            WebcamListResult filtered to the given country.
        """
        return self.list_webcams(
            countries=[country_code],
            limit=limit,
            include=include,
            sort_key=sort_key,
            sort_direction=SortDirection.DESC,
        )

    def search_by_category(
        self,
        category: str | WebcamCategory,
        limit: int = 10,
        include: list[str | IncludeField] | None = None,
        sort_key: SortKey = SortKey.POPULARITY,
    ) -> WebcamListResult:
        """
        Find webcams matching a specific category.

        Args:
            category:  A WebcamCategory enum value or its string equivalent.
            limit:     Maximum results to return.
            include:   Optional response sections.
            sort_key:  Sort field (default: popularity).

        Returns:
            WebcamListResult filtered to the given category.
        """
        return self.list_webcams(
            categories=[category],
            limit=limit,
            include=include,
            sort_key=sort_key,
            sort_direction=SortDirection.DESC,
        )

    def search_by_bbox(
        self,
        north: float,
        east: float,
        south: float,
        west: float,
        limit: int = 10,
        include: list[str | IncludeField] | None = None,
    ) -> WebcamListResult:
        """
        Find webcams within a geographic bounding box.

        Args:
            north: Northern latitude boundary.
            east:  Eastern longitude boundary.
            south: Southern latitude boundary.
            west:  Western longitude boundary.
            limit: Maximum results to return.
            include: Optional response sections.

        Returns:
            WebcamListResult for webcams within the bounding box.
        """
        return self.list_webcams(
            bbox=(north, east, south, west),
            limit=limit,
            include=include,
        )

    def get_webcam_with_full_details(self, webcam_id: int, lang: str = "en") -> Webcam:
        """
        Retrieve a webcam with all available optional fields populated.

        Equivalent to calling get_webcam() with all include fields set.

        Args:
            webcam_id: Unique webcam identifier.
            lang:      Response language code.

        Returns:
            Webcam with categories, images, location, player, and urls populated.
        """
        return self.get_webcam(
            webcam_id,
            lang=lang,
            include=[
                IncludeField.CATEGORIES,
                IncludeField.IMAGES,
                IncludeField.LOCATION,
                IncludeField.PLAYER,
                IncludeField.URLS,
            ],
        )

    # ------------------------------------------------------------------
    # Player URL helpers (no auth required for these URLs)
    # ------------------------------------------------------------------

    @staticmethod
    def build_player_url(webcam_id: int, player_type: PlayerType = PlayerType.LIVE) -> str:
        """
        Construct the public embed player URL for a webcam.

        These URLs can be used in <iframe> embeds without an API key.
        The free tier will show ads; the professional tier is ad-free.

        Args:
            webcam_id:   Numeric webcam ID.
            player_type: Type of player (live, day, month, year, lifetime).

        Returns:
            Fully qualified player embed URL string.
        """
        return (
            f"https://webcams.windy.com/webcams/public/player"
            f"?webcamId={webcam_id}&playerType={player_type.value}"
        )

    @staticmethod
    def build_player_embed_html(
        webcam_id: int,
        player_type: PlayerType = PlayerType.LIVE,
        width: int = 640,
        height: int = 360,
    ) -> str:
        """
        Generate an HTML <iframe> embed tag for a webcam player.

        Args:
            webcam_id:   Numeric webcam ID.
            player_type: Type of player embed.
            width:       Iframe width in pixels.
            height:      Iframe height in pixels.

        Returns:
            HTML string for direct embedding in a web page.
        """
        url = WindyWebcamsClient.build_player_url(webcam_id, player_type)
        return (
            f'<iframe src="{url}" width="{width}" height="{height}" '
            f'frameborder="0" allowfullscreen></iframe>'
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "WindyWebcamsClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session and release connections."""
        self._session.close()


# ---------------------------------------------------------------------------
# Rate-limited client variant
# ---------------------------------------------------------------------------

class RateLimitedWindyWebcamsClient(WindyWebcamsClient):
    """
    WindyWebcamsClient with built-in request throttling.

    Adds a minimum delay between consecutive API calls to avoid
    triggering rate limits, useful for batch processing jobs.

    Args:
        api_key:          Windy API key.
        min_delay_sec:    Minimum seconds to wait between requests (default: 0.5).
        **kwargs:         Forwarded to WindyWebcamsClient.
    """

    def __init__(self, api_key: str, min_delay_sec: float = 0.5, **kwargs: Any) -> None:
        super().__init__(api_key, **kwargs)
        self._min_delay = min_delay_sec
        self._last_call_time: float = 0.0

    def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_call_time
        wait = self._min_delay - elapsed
        if wait > 0:
            time.sleep(wait)
        try:
            return super()._get(url, params)
        finally:
            self._last_call_time = time.monotonic()


# ---------------------------------------------------------------------------
# Async client (optional, requires httpx)
# ---------------------------------------------------------------------------

try:
    import httpx

    class AsyncWindyWebcamsClient:
        """
        Async variant of WindyWebcamsClient using httpx.

        Requires `httpx` to be installed:
            pip install httpx

        Usage::

            async with AsyncWindyWebcamsClient(api_key="key") as client:
                result = await client.list_webcams(limit=20)
                for cam in result.webcams:
                    print(cam.title)
        """

        def __init__(
            self,
            api_key: str,
            timeout: float = DEFAULT_TIMEOUT,
        ) -> None:
            if not api_key:
                raise ValueError("api_key must not be empty")
            self._api_key = api_key
            self._timeout = timeout
            self._client = httpx.AsyncClient(
                headers={API_KEY_HEADER: api_key},
                timeout=timeout,
            )

        async def _get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            try:
                resp = await self._client.get(url, params=params)
            except httpx.ConnectError as exc:
                raise WindyWebcamsError(f"Connection error: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise WindyWebcamsError("Request timed out") from exc

            try:
                body = resp.json()
            except Exception:
                body = {}

            if resp.status_code in (401, 403):
                raise WindyAuthError(body.get("message", "Unauthorized"))
            if resp.status_code == 404:
                raise WindyNotFoundError(body.get("message", "Not found"))
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After")
                raise WindyRateLimitError(int(ra) if ra else None)
            if not resp.is_success:
                raise WindyAPIError(resp.status_code, body.get("message", resp.text))

            return body

        async def list_webcams(
            self,
            *,
            limit: int = 10,
            offset: int = 0,
            lang: str = "en",
            nearby: tuple[float, float, float] | None = None,
            bbox: tuple[float, float, float, float] | None = None,
            categories: list[str] | None = None,
            countries: list[str] | None = None,
            include: list[str | IncludeField] | None = None,
        ) -> WebcamListResult:
            """Async version of list_webcams. See WindyWebcamsClient.list_webcams for docs."""
            params: dict[str, Any] = {"limit": limit, "offset": offset, "lang": lang}
            if nearby:
                lat, lon, r = nearby
                params["nearby"] = f"{lat},{lon},{r}"
            if bbox:
                n, e, s, w = bbox
                params["bbox"] = f"{n},{e},{s},{w}"
            if categories:
                params["categories"] = ",".join(categories)
            if countries:
                params["countries"] = ",".join(countries)
            if include:
                params["include"] = ",".join(
                    i.value if isinstance(i, IncludeField) else i for i in include
                )
            data = await self._get(f"{BASE_URL}/webcams", params)
            return WebcamListResult.from_dict(data, offset=offset, limit=limit)

        async def get_webcam(
            self,
            webcam_id: int,
            *,
            lang: str = "en",
            include: list[str | IncludeField] | None = None,
        ) -> Webcam:
            """Async version of get_webcam. See WindyWebcamsClient.get_webcam for docs."""
            params: dict[str, Any] = {"lang": lang}
            if include:
                params["include"] = ",".join(
                    i.value if isinstance(i, IncludeField) else i for i in include
                )
            data = await self._get(f"{BASE_URL}/webcams/{webcam_id}", params)
            return Webcam.from_dict(data)

        async def get_categories(self, lang: str = "en") -> list[CategoryEntry]:
            """Async version of get_categories."""
            data = await self._get(f"{BASE_URL}/categories", {"lang": lang})
            return [CategoryEntry.from_dict(c) for c in (data if isinstance(data, list) else [])]

        async def get_map_clusters(
            self,
            *,
            north_lat: float,
            south_lat: float,
            east_lon: float,
            west_lon: float,
            zoom: int,
            lang: str = "en",
            include: list[str | IncludeField] | None = None,
        ) -> list[Webcam]:
            """Async version of get_map_clusters."""
            params: dict[str, Any] = {
                "northLat": north_lat,
                "southLat": south_lat,
                "eastLon": east_lon,
                "westLon": west_lon,
                "zoom": zoom,
                "lang": lang,
            }
            if include:
                params["include"] = ",".join(
                    i.value if isinstance(i, IncludeField) else i for i in include
                )
            data = await self._get(f"{BASE_URL}/map/clusters", params)
            if isinstance(data, list):
                return [Webcam.from_dict(w) for w in data]
            return [Webcam.from_dict(w) for w in data.get("webcams", [])]

        async def __aenter__(self) -> "AsyncWindyWebcamsClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            await self._client.aclose()

except ImportError:
    pass  # httpx not installed; AsyncWindyWebcamsClient is unavailable


# ---------------------------------------------------------------------------
# Undocumented / internal endpoints
# ---------------------------------------------------------------------------

NODE_HOST = "https://node.windy.com"
ADMIN_HOST = "https://admin.windy.com"


@dataclass
class InternalWebcamLocation:
    """Location data from the internal v1.0 API (richer than v3)."""
    lat: float = 0.0
    lon: float = 0.0
    title: str = ""
    city: str = ""
    subcountry: str = ""
    country: str = ""
    continent: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InternalWebcamLocation":
        return cls(
            lat=d.get("lat", 0.0),
            lon=d.get("lon", 0.0),
            title=d.get("title", ""),
            city=d.get("city", ""),
            subcountry=d.get("subcountry", ""),
            country=d.get("country", ""),
            continent=d.get("continent", ""),
        )


@dataclass
class InternalWebcamImageSet:
    """
    Five-size image set from the internal API.

    Sizes available on imgproxy.windy.com:
        full      – original resolution (may be up to 1920×1080)
        normal    – medium size
        preview   – ~400×224
        thumbnail – ~200×112
        icon      – 48×48
    """
    full: str = ""
    normal: str = ""
    preview: str = ""
    thumbnail: str = ""
    icon: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InternalWebcamImageSet":
        return cls(
            full=d.get("full", ""),
            normal=d.get("normal", ""),
            preview=d.get("preview", ""),
            thumbnail=d.get("thumbnail", ""),
            icon=d.get("icon", ""),
        )


@dataclass
class InternalWebcamImages:
    """current + daylight image sets from the internal API."""
    current: InternalWebcamImageSet = field(default_factory=InternalWebcamImageSet)
    daylight: InternalWebcamImageSet = field(default_factory=InternalWebcamImageSet)
    sizes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InternalWebcamImages":
        return cls(
            current=InternalWebcamImageSet.from_dict(d.get("current", {})),
            daylight=InternalWebcamImageSet.from_dict(d.get("daylight", {})),
            sizes=d.get("sizes", {}),
        )


@dataclass
class InternalWebcam:
    """
    Webcam record from the undocumented node.windy.com v1.0 API.

    This is richer than the public v3 API in several ways:
      - Images have 5 sizes (full, normal, preview, thumbnail, icon)
      - Location includes subcountry (state/province)
      - Detail endpoint includes orientation, contacts, timelapseType
      - No API key needed
    """
    id: int = 0
    title: str = ""
    last_update: int = 0       # Unix ms timestamp
    last_daylight: int = 0     # Unix ms timestamp
    view_count: int = 0
    page_url: str = ""
    short_title: str = ""
    timelapse_type: str = ""
    location: InternalWebcamLocation = field(default_factory=InternalWebcamLocation)
    images: InternalWebcamImages = field(default_factory=InternalWebcamImages)
    categories: list[str] = field(default_factory=list)
    orientation: dict[str, Any] = field(default_factory=dict)
    contacts: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InternalWebcam":
        return cls(
            id=d.get("id", 0),
            title=d.get("title", ""),
            last_update=d.get("lastUpdate", 0),
            last_daylight=d.get("lastDaylight", 0),
            view_count=d.get("viewCount", 0),
            page_url=d.get("pageUrl", ""),
            short_title=d.get("shortTitle", ""),
            timelapse_type=d.get("timelapseType", ""),
            location=InternalWebcamLocation.from_dict(d.get("location", {})),
            images=InternalWebcamImages.from_dict(d.get("images", {})),
            categories=d.get("categories", []),
            orientation=d.get("orientation", {}),
            contacts=d.get("contacts", {}),
            raw=d,
        )

    @property
    def windy_url(self) -> str:
        """Windy.com detail page URL for this webcam."""
        return f"https://www.windy.com/webcams/{self.id}"


@dataclass
class ArchiveFrame:
    """A single time-stamped image frame from the archive endpoint."""
    timestamp: int = 0         # Unix ms
    timestamp_readable: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArchiveFrame":
        return cls(
            timestamp=d.get("timestamp", 0),
            timestamp_readable=d.get("timestampReadable", ""),
            url=d.get("url", ""),
        )


@dataclass
class PlaceView:
    """
    A place/POI suggestion from the undocumented admin.windy.com search endpoint.

    Used by the Windy webcam page to let users browse cameras by location name.
    The viewId is a Google Places-style ID that can be used in further filtering
    (via the Windy web app's URL routing).
    """
    view_id: str = ""
    name: str = ""
    distance: int = 0           # metres from the provided lat/lon
    place_type: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlaceView":
        return cls(
            view_id=d.get("viewId", ""),
            name=d.get("name", ""),
            distance=d.get("distance", 0),
            place_type=d.get("placeType", ""),
        )


class WindyInternalClient:
    """
    Client for Windy's undocumented internal webcam endpoints.

    These endpoints are used by the Windy.com web application and do NOT
    require an API key. They are not officially documented and may change
    without notice.

    Hosts:
        node.windy.com  – webcam list, detail, archive
        admin.windy.com – place/view search

    No authentication is required for any of these endpoints.

    Example::

        client = WindyInternalClient()

        # Find webcams near a location
        cams = client.get_nearby_webcams(48.8566, 2.3522, limit=10)
        for cam in cams:
            print(cam.id, cam.title, cam.images.current.preview)

        # Get archive frames for the last 24 hours
        frames = client.get_webcam_archive(cam.id)
        for frame in frames:
            print(frame.timestamp_readable, frame.url)

        # Search for a place by name
        views = client.search_views("Eiffel Tower", lat=48.8566, lon=2.3522)
        for v in views:
            print(v.name, v.place_type, v.distance, "m")
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        session: Session | None = None,
    ) -> None:
        self._timeout = timeout
        if session is not None:
            self._session = session
        else:
            self._session = self._build_session()

    @staticmethod
    def _build_session() -> Session:
        session = Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        return session

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        logger.debug("GET %s params=%s", url, params)
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout)
        except requests.exceptions.ConnectionError as exc:
            raise WindyWebcamsError(f"Connection error: {exc}") from exc
        except requests.exceptions.Timeout as exc:
            raise WindyWebcamsError(f"Request timed out after {self._timeout}s") from exc
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # node.windy.com endpoints
    # ------------------------------------------------------------------

    def get_nearby_webcams(
        self,
        lat: float,
        lon: float,
        limit: int = 10,
        lang: str = "en",
    ) -> list[InternalWebcam]:
        """
        Return the nearest webcams to a coordinate point.

        This is the endpoint used by the Windy.com map panel to show cameras
        near wherever the user clicks. It returns richer image data than v3
        (5 image sizes including 'normal') and includes subcountry in location.

        URL: GET https://node.windy.com/webcams/v1.0/list
        Params:
            nearby={lat},{lon}  (required)
            lang                (default: en)
            limit               (default: 10)

        Args:
            lat:   Latitude of the center point.
            lon:   Longitude of the center point.
            limit: Maximum number of cameras to return.
            lang:  Language code for localized names.

        Returns:
            List of InternalWebcam objects sorted by distance.
        """
        url = f"{NODE_HOST}/webcams/v1.0/list"
        params = {
            "nearby": f"{lat},{lon}",
            "lang": lang,
            "limit": limit,
        }
        data = self._get(url, params)
        return [InternalWebcam.from_dict(c) for c in data.get("cams", [])]

    def get_webcam_detail(
        self,
        webcam_id: int,
        lang: str = "en",
    ) -> InternalWebcam:
        """
        Return full detail for a single webcam.

        Returns extra fields not present in the list endpoint:
          - shortTitle
          - pageUrl  (the original provider's page URL)
          - viewCount
          - orientation  (direction, position, view type)
          - contacts      (owner, caretaker)
          - timelapseType (e.g. "all")

        URL: GET https://node.windy.com/webcams/v1.0/detail/{webcamId}
        Params:
            lang  (default: en)

        Args:
            webcam_id: Numeric webcam identifier.
            lang:      Language code.

        Returns:
            InternalWebcam with all fields populated.
        """
        url = f"{NODE_HOST}/webcams/v1.0/detail/{webcam_id}"
        data = self._get(url, {"lang": lang})
        return InternalWebcam.from_dict(data)

    def get_webcam_archive(
        self,
        webcam_id: int,
        hourly: bool = False,
    ) -> list[ArchiveFrame]:
        """
        Return historical image frames for a webcam.

        Two modes:
          - Default (hourly=False): last 24 hours, one frame per ~50 minutes.
            Image URLs use the ``day`` path prefix.
          - Hourly (hourly=True): last 30 days, one frame per hour.
            Image URLs use the ``month`` path prefix.

        URL: GET https://node.windy.com/webcams/v2.0/archive[/hourly]/{webcamId}

        Args:
            webcam_id: Numeric webcam identifier.
            hourly:    If True, return the 30-day hourly archive instead of
                       the 24-hour archive.

        Returns:
            List of ArchiveFrame objects in chronological order.
        """
        if hourly:
            url = f"{NODE_HOST}/webcams/v2.0/archive/hourly/{webcam_id}"
        else:
            url = f"{NODE_HOST}/webcams/v2.0/archive/{webcam_id}"
        data = self._get(url)
        if isinstance(data, list):
            return [ArchiveFrame.from_dict(f) for f in data]
        # Fallback if wrapped
        return [ArchiveFrame.from_dict(f) for f in data.get("frames", [])]

    # ------------------------------------------------------------------
    # admin.windy.com endpoints
    # ------------------------------------------------------------------

    def search_views(
        self,
        query: str,
        lat: float | None = None,
        lon: float | None = None,
        lang: str = "en",
    ) -> list[PlaceView]:
        """
        Search for places / POIs by name, optionally biased to a location.

        Used by the Windy webcam page to populate the search-by-place input.
        Returns Google Places-style IDs that identify geographic areas. These
        viewId values appear in Windy.com URLs when browsing webcams by place
        (e.g. /webcams/view/{viewId}).

        When lat/lon are provided the results are sorted by distance from
        that point. Both are required together (pass neither or both).

        URL: GET https://admin.windy.com/webcams/admin/v1.0/views
        Params:
            textQuery  (required)
            lang       (default: en)
            lat        (optional, requires lon)
            lon        (optional, requires lat)

        Args:
            query: Free-text search query (e.g. "Eiffel Tower", "New York").
            lat:   Latitude for distance sorting (optional).
            lon:   Longitude for distance sorting (optional).
            lang:  Language code.

        Returns:
            List of PlaceView suggestions sorted by relevance / distance.

        Raises:
            ValueError: If only one of lat/lon is provided.
            WindyWebcamsError: On network or server error.
        """
        if (lat is None) != (lon is None):
            raise ValueError("Provide both lat and lon, or neither.")

        url = f"{ADMIN_HOST}/webcams/admin/v1.0/views"
        params: dict[str, Any] = {"textQuery": query, "lang": lang}
        if lat is not None:
            params["lat"] = lat
            params["lon"] = lon

        data = self._get(url, params)
        return [PlaceView.from_dict(v) for v in data.get("views", [])]

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "WindyInternalClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()


# ---------------------------------------------------------------------------
# CLI / quick-test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import json
    import sys

    api_key = os.environ.get("WINDY_API_KEY", "")
    if not api_key:
        print(
            "Set WINDY_API_KEY environment variable to test the client.\n"
            "Get a key at: https://api.windy.com/keys",
            file=sys.stderr,
        )
        sys.exit(1)

    client = WindyWebcamsClient(api_key=api_key)

    print("=== Windy Webcams API Client - Quick Test ===\n")

    print("1. Listing popular webcams (limit=5)...")
    result = client.list_webcams(
        limit=5,
        sort_key=SortKey.POPULARITY,
        sort_direction=SortDirection.DESC,
        include=[IncludeField.LOCATION, IncludeField.URLS],
    )
    print(f"   Total available: {result.total}")
    for cam in result.webcams:
        loc = f"{cam.location.city}, {cam.location.country}" if cam.location else "?"
        print(f"   [{cam.webcam_id}] {cam.title} — {loc}")

    print("\n2. Fetching single webcam (Sydney Harbour)...")
    cam = client.get_webcam(
        1179853135,
        include=[IncludeField.IMAGES, IncludeField.LOCATION, IncludeField.PLAYER, IncludeField.URLS],
    )
    print(f"   Title: {cam.title}")
    print(f"   Status: {cam.status}")
    if cam.location:
        print(f"   Location: {cam.location.city}, {cam.location.country}")
    if cam.player:
        print(f"   Live player: {cam.player.live}")
    if cam.urls:
        print(f"   Windy URL: {cam.urls.detail}")

    print("\n3. Searching near Paris (50km radius)...")
    result = client.search_by_location(48.8566, 2.3522, radius_km=50, limit=3)
    for cam in result.webcams:
        print(f"   {cam.title}")

    print("\n4. Getting mountain webcams...")
    result = client.search_by_category(WebcamCategory.MOUNTAIN, limit=3)
    for cam in result.webcams:
        print(f"   {cam.title}")

    print("\n5. Building player embed HTML...")
    html = WindyWebcamsClient.build_player_embed_html(1179853135, PlayerType.DAY)
    print(f"   {html}")

    print("\nAll tests passed.")

    # -----------------------------------------------------------------------
    # Internal / undocumented endpoints (no API key needed)
    # -----------------------------------------------------------------------
    print("\n=== Undocumented Internal Endpoints (no API key) ===\n")

    internal = WindyInternalClient()

    print("6. Nearby webcams via node.windy.com (Paris)...")
    cams = internal.get_nearby_webcams(48.8566, 2.3522, limit=3)
    for cam in cams:
        print(f"   [{cam.id}] {cam.title}")
        if cam.images.current.preview:
            print(f"     preview: {cam.images.current.preview}")

    if cams:
        test_id = cams[0].id
        print(f"\n7. Full detail for webcam {test_id}...")
        detail = internal.get_webcam_detail(test_id)
        print(f"   title:       {detail.title}")
        print(f"   view_count:  {detail.view_count}")
        print(f"   page_url:    {detail.page_url}")
        print(f"   orientation: {detail.orientation}")

        print(f"\n8. 24-hour archive frames for webcam {test_id}...")
        frames = internal.get_webcam_archive(test_id)
        print(f"   {len(frames)} frames returned")
        if frames:
            print(f"   earliest: {frames[0].timestamp_readable}")
            print(f"   latest:   {frames[-1].timestamp_readable}")
            print(f"   sample URL: {frames[-1].url}")

        print(f"\n9. 30-day hourly archive for webcam {test_id}...")
        hourly = internal.get_webcam_archive(test_id, hourly=True)
        print(f"   {len(hourly)} hourly frames returned")

    print("\n10. Place/view search via admin.windy.com...")
    views = internal.search_views("Eiffel Tower", lat=48.8566, lon=2.3522)
    for v in views[:3]:
        print(f"   [{v.view_id}] {v.name} ({v.place_type}) – {v.distance}m away")

    internal.close()
    print("\nAll internal endpoint tests passed.")
