"""
Regrid Parcel Data Client
=========================
Reverse-engineered client for Regrid (app.regrid.com) parcel lookup platform.

Endpoints discovered:
  - Search:          GET  /search.json?query=...&autocomplete=1
  - Place search:    GET  /search/places.json?query=...
  - Point search:    GET  /search/point.json?lat=...&lng=...&zoom=...
  - Property detail: GET  /{path}.json?source_ids=&current_region_path=
  - Lookup limits:   GET  /users/lookup_limits.json
  - Boundaries:      GET  /{path}/boundaries.json?exclude_children=true
  - Filters:         GET  /{path}/filters.json
  - Colors:          GET  /{path}/colors.json?style=...
  - Templates:       GET  /templates.json?names[]=...
  - Preferences:     GET  /preferences.json                    (auth required)
  - Profile:         GET  /profile.json?usage=1                (auth required)
  - Follows:         GET  /profile/follows.json?page=...       (auth required)
  - JWT renewal:     GET  /users/renew_jwt.json                (auth required)
  - Streetview:      GET  /{path}/streetside.jpg               (auth required)

Tile server (tiles.regrid.com):
  - TileJSON:        GET  /api/v1/parcels
  - PNG tiles:       GET  /api/v1/parcels/{z}/{x}/{y}.png
  - UTFGrid:         GET  /api/v1/parcels/{z}/{x}/{y}.json
  - MVT vector:      GET  /api/v1/parcels/{z}/{x}/{y}.mvt
  - Filtered tiles:  POST /api/v1/sources  (returns custom layer hash)
  - Static layers:   GET  /api/v1/static/{layer}/{z}/{x}/{y}.mvt?userToken=...
  - FEMA flood:      GET  /api/v1/static/fema/{z}/{x}/{y}.mvt?userToken=...
  - Wetlands:        GET  /api/v1/static/wetlands/{z}/{x}/{y}.mvt?userToken=...
  - Contours:        GET  /api/v1/static/us_contours/{z}/{x}/{y}.mvt?userToken=...
  - Esri enrichment: GET  /api/v1/static/esri_enrichments/{z}/{x}/{y}.mvt?userToken=...

Authentication:
  - Anonymous: 5 property lookups/day (tracked by _session_id cookie)
  - Free Starter account: 25 lookups/day
  - Pro account: 1,000 lookups/day
  - Team account: 2,000 lookups/day
  - Rate limit tracked by session cookie (_session_id), HttpOnly, 7-day expiry
  - Session obtained automatically on first page visit
  - CSRF token in <meta name="csrf-token"> for POST/PUT/DELETE requests
  - JWT token (window.data.jwt) for tile server and dimensions API
  - Tile token (window.data.tile_token) for filtered/premium tile layers

Path format:
  /us/{state}/{county}/{city}/{parcel_id}
  e.g. /us/nh/merrimack/hooksett/97126

Data coverage:
  - 155M+ parcels across all US states and territories
  - Canada coverage available (ds=ca)
  - 118+ fields per parcel (owner, value, zoning, tax, structure, etc.)
  - Geometry (Polygon/MultiPolygon) with centroid coordinates
  - Premium fields: FEMA flood zones, building footprints, school districts,
    cropland data, delivery point validation, LBCS land use codes
"""

import json
import math
import time
import urllib.request
import urllib.parse
import http.cookiejar
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A result from the address/place search endpoint."""
    category: str        # "parcel" or "place"
    path: str            # e.g. "/us/nh/merrimack/hooksett/97126"
    headline: str        # e.g. "1234 Hooksett Rd"
    context: str         # e.g. "Hooksett, NH"
    type: str            # "Parcel", "City", "County", etc.
    parcelnumb: Optional[str] = None
    score: float = 0.0


@dataclass
class LookupLimits:
    """Current lookup usage and limits for the session."""
    allowed: bool
    remaining: int
    used: int
    total: int
    metered: bool
    need: str            # "upgrade", "register", etc.


@dataclass
class ParcelData:
    """Full property/parcel data from a lookup."""
    id: int
    headline: str
    path: str
    fields: Dict[str, Any]
    key: Dict[str, str]
    geometry: Optional[Dict[str, Any]] = None
    centroid: Optional[List[float]] = None
    has_premium: bool = False
    formatted_addresses: Optional[List] = None
    metadata: Optional[Dict[str, Any]] = None
    streetview_url: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None
    context: Optional[List[Dict]] = None
    reference_links: Optional[Dict[str, str]] = None
    imagery: Optional[Dict[str, Any]] = None
    sources: Optional[List] = None
    premium_field_metadata: Optional[Dict] = None
    anon_field_metadata: Optional[Dict] = None


@dataclass
class BoundaryData:
    """Region boundary and tile configuration."""
    path: str
    parent: str
    parent_names: str
    tile_layer: Dict[str, Any]
    tile_key: str
    outline: Optional[Dict[str, Any]] = None
    datasets: Optional[Dict[str, str]] = None
    columns: Optional[List[Dict]] = None
    styles: Optional[Dict[str, str]] = None
    store_link: Optional[str] = None


@dataclass
class FilterOption:
    """A filterable field for a region."""
    key: str
    label: str
    type: str            # "text", "number", "select", etc.
    premium: bool = False
    disabled: bool = False
    free: bool = True


@dataclass
class TileConfig:
    """TileJSON configuration for a tile layer."""
    tilejson: str
    id: str
    max_zoom: int
    png_template: str
    grid_template: str
    mvt_template: str
    query: Optional[Dict] = None
    fields: Optional[Dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class RegridClient:
    """
    Reverse-engineered client for Regrid parcel data platform.

    Anonymous usage: 5 lookups/day. Create a free account for 25/day.
    Each property detail view consumes 1 lookup.

    Usage:
        client = RegridClient()
        results = client.search("1234 Hooksett Rd Hooksett NH")
        if results:
            parcel = client.get_property(results[0].path)
            print(parcel.fields)
    """

    APP_BASE = "https://app.regrid.com"
    TILE_BASE = "https://tiles.regrid.com"

    # Mapbox token embedded in Regrid's JS (public, for basemap tiles only)
    MAPBOX_TOKEN = "<MAPBOX_PUBLIC_TOKEN>"

    # Esri basemap key from window.data
    ESRI_KEY = "AAPK299be3bc75404f02bbe776e20f212e75oX5QWHW4q_AmGhesopDo0ynZefr7cTqo7rny0-QP3YAb3TmtD-hhb0Yi2BKGaBMx"

    # Mapbox style IDs used by Regrid (Loveland account)
    MAPBOX_STYLES = {
        "streets": "loveland/ckrm85h2a81pb",
        "satellite": "loveland/cirw7smjyb2r8",
        "base": "loveland/cifq4lvda000j8zluw5ek6hr6",
    }

    # Rate limit tiers (from window.data.limits)
    RATE_LIMITS = {
        "anonymous": 5,
        "free": 25,
        "pro": 1000,
        "team": 2000,
    }

    # Known static tile layers
    STATIC_LAYERS = [
        "fema",            # FEMA flood zones
        "wetlands",        # National wetlands inventory
        "us_contours",     # USGS elevation contours (zoom 13)
        "esri_enrichments", # Esri demographic enrichments
    ]

    # Known pre-built layer hashes
    LAYER_HASHES = {
        "zoning": "4c2c8e69c0b928c1422b0a20c1f533134345378e",
        "connectivity": "cd6432c525c9079eb71c952742a2a8aedfb6dfd1",
        "opportunity_zones": "738322d8ee22db2d04fcfc4bcbfdfabe5cf0153d",
    }

    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize client. Optionally provide credentials for higher rate limits.

        Args:
            email: Regrid account email (optional)
            password: Regrid account password (optional)
        """
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )
        self._csrf_token: Optional[str] = None
        self._jwt: Optional[str] = None
        self._tile_token: Optional[str] = None
        self._session_id: Optional[str] = None
        self._signed_in = False

        # Initialize session
        self._init_session()

        # Login if credentials provided
        if email and password:
            self.login(email, password)

    # ── Session Management ──────────────────────────────────────────────

    def _init_session(self) -> None:
        """Get a session cookie by visiting the app."""
        req = urllib.request.Request(
            f"{self.APP_BASE}/us",
            headers=self._headers()
        )
        with self._opener.open(req) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract CSRF token from meta tag
        import re
        csrf_match = re.search(
            r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html
        )
        if csrf_match:
            self._csrf_token = csrf_match.group(1)

        # Extract window.data config from inline script
        data_match = re.search(r'window\.data\s*=\s*({.*?});\s*\n', html, re.DOTALL)
        if data_match:
            try:
                data = json.loads(data_match.group(1))
                self._jwt = data.get("jwt")
                self._tile_token = data.get("tile_token")
                self._signed_in = data.get("signed_in", False)
                self._session_id = data.get("session_id", {}).get("public_id")
            except (json.JSONDecodeError, AttributeError):
                pass

    def login(self, email: str, password: str) -> bool:
        """
        Log in with email and password for higher rate limits (25/day free).

        Args:
            email: Regrid account email
            password: Account password

        Returns:
            True if login successful
        """
        # First ensure we have a CSRF token
        if not self._csrf_token:
            self._init_session()

        payload = urllib.parse.urlencode({
            "user[email]": email,
            "user[password]": password,
            "authenticity_token": self._csrf_token or "",
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.APP_BASE}/users/sign_in",
            data=payload,
            headers={
                **self._headers(),
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRF-Token": self._csrf_token or "",
            },
            method="POST",
        )

        try:
            with self._opener.open(req) as resp:
                # After login, re-extract session data
                self._init_session()
                return self._signed_in
        except urllib.error.HTTPError:
            return False

    # ── Search ──────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        autocomplete: bool = True,
        strict: bool = False,
    ) -> List[SearchResult]:
        """
        Search for addresses, parcels, or places.

        This is the main search endpoint. Does NOT consume a lookup.

        Args:
            query: Address, place name, or parcel ID to search for
            autocomplete: Enable autocomplete mode (default True)
            strict: Strict matching (default False)

        Returns:
            List of SearchResult objects
        """
        params = urllib.parse.urlencode({
            "query": query,
            "autocomplete": "1" if autocomplete else "0",
            "context": "false",
            "strict": "true" if strict else "false",
        })
        data = self._get(f"/search.json?{params}")
        if isinstance(data, list):
            return [
                SearchResult(
                    category=r.get("category", ""),
                    path=r.get("path", ""),
                    headline=r.get("headline", ""),
                    context=r.get("context", ""),
                    type=r.get("type", ""),
                    parcelnumb=r.get("parcelnumb"),
                    score=r.get("score", 0),
                )
                for r in data
            ]
        return []

    def search_places(self, query: str) -> List[SearchResult]:
        """
        Search for places (cities, counties, states) only.

        Does NOT consume a lookup.

        Args:
            query: Place name to search for

        Returns:
            List of SearchResult objects
        """
        params = urllib.parse.urlencode({"query": query})
        data = self._get(f"/search/places.json?{params}")
        if isinstance(data, list):
            return [
                SearchResult(
                    category=r.get("category", ""),
                    path=r.get("path", ""),
                    headline=r.get("headline", ""),
                    context=r.get("context", ""),
                    type=r.get("type", ""),
                    score=r.get("score", 0),
                )
                for r in data
            ]
        return []

    def search_groups(self, query: str) -> List[Dict]:
        """
        Search for Regrid groups/organizations.

        Args:
            query: Group name to search for

        Returns:
            List of group dicts
        """
        params = urllib.parse.urlencode({"query": query})
        return self._get(f"/search/groups.json?{params}") or []

    # ── Property Lookup ─────────────────────────────────────────────────

    def get_property(
        self,
        path: str,
        source_ids: str = "",
        region_path: str = "",
    ) -> Optional[ParcelData]:
        """
        Get full property/parcel data. CONSUMES 1 LOOKUP.

        Args:
            path: Parcel path (e.g. "/us/nh/merrimack/hooksett/97126")
            source_ids: Optional source IDs to include
            region_path: Optional current region path for context

        Returns:
            ParcelData object with 118+ fields, geometry, etc.
            Returns None if not found or limit exceeded.
        """
        if not path.startswith("/"):
            path = f"/{path}"

        params = urllib.parse.urlencode({
            "source_ids": source_ids,
            "current_region_path": region_path,
        })
        data = self._get(f"{path}.json?{params}")

        if not data or data.get("status") == "error":
            return None

        return ParcelData(
            id=data.get("id", 0),
            headline=data.get("headline", ""),
            path=data.get("path", path),
            fields=data.get("fields", {}),
            key=data.get("key", {}),
            geometry=data.get("geometry"),
            centroid=data.get("centroid"),
            has_premium=data.get("has_premium", False),
            formatted_addresses=data.get("formatted_addresses"),
            metadata=data.get("metadata"),
            streetview_url=data.get("streetview"),
            spec=data.get("spec"),
            context=data.get("context"),
            reference_links=data.get("reference_links"),
            imagery=data.get("imagery"),
            sources=data.get("sources"),
            premium_field_metadata=data.get("premium_field_metadata"),
            anon_field_metadata=data.get("anon_field_metadata"),
        )

    def get_lookup_limits(self) -> LookupLimits:
        """
        Check current lookup usage and remaining quota.

        Returns:
            LookupLimits with remaining count and tier info
        """
        data = self._get("/users/lookup_limits.json")
        return LookupLimits(
            allowed=data.get("allowed", False),
            remaining=data.get("remaining", 0),
            used=data.get("used", 0),
            total=data.get("total", 0),
            metered=data.get("metered", True),
            need=data.get("need", ""),
        )

    # ── Region Data ─────────────────────────────────────────────────────

    def get_boundaries(
        self,
        path: str,
        exclude_children: bool = True,
    ) -> Optional[BoundaryData]:
        """
        Get region boundary data and tile configuration.

        Does NOT consume a lookup.

        Args:
            path: Region path (e.g. "/us/nh/merrimack/hooksett")
            exclude_children: Exclude child regions from outline

        Returns:
            BoundaryData with tile config, outline geometry, columns, etc.
        """
        if not path.startswith("/"):
            path = f"/{path}"

        params = urllib.parse.urlencode({
            "exclude_children": "true" if exclude_children else "false"
        })
        data = self._get(f"{path}/boundaries.json?{params}")

        if not data or data.get("status") != "ok":
            return None

        return BoundaryData(
            path=data.get("path", path),
            parent=data.get("parent", ""),
            parent_names=data.get("parent_names", ""),
            tile_layer=data.get("tile_layer", {}),
            tile_key=data.get("tile_key", ""),
            outline=data.get("outline"),
            datasets=data.get("datasets"),
            columns=data.get("columns"),
            styles=data.get("styles"),
            store_link=data.get("store_link"),
        )

    def get_filters(self, path: str) -> List[FilterOption]:
        """
        Get available filter fields for a region.

        Does NOT consume a lookup.

        Args:
            path: Region path (e.g. "/us/nh/merrimack")

        Returns:
            List of FilterOption objects
        """
        if not path.startswith("/"):
            path = f"/{path}"

        data = self._get(f"{path}/filters.json")
        if not data or data.get("status") != "ok":
            return []

        options = []
        for source in data.get("sources", []):
            for opt in source.get("options", []):
                options.append(FilterOption(
                    key=opt.get("key", ""),
                    label=opt.get("label", ""),
                    type=opt.get("type", "text"),
                    premium=opt.get("premium", False),
                    disabled=opt.get("disabled", False),
                    free=opt.get("free", True),
                ))
        return options

    def get_colors(
        self,
        path: str,
        style: str = "default",
    ) -> Optional[Dict]:
        """
        Get thematic color map data for a region.

        Does NOT consume a lookup.

        Args:
            path: Region path
            style: Color style name

        Returns:
            Dict with styleHandler, property, data, and scale
        """
        if not path.startswith("/"):
            path = f"/{path}"

        params = urllib.parse.urlencode({"style": style})
        data = self._get(f"{path}/colors.json?{params}")
        if data and data.get("status") == "ok":
            return data
        return None

    # ── Tile Server ─────────────────────────────────────────────────────

    def get_tile_config(self) -> TileConfig:
        """
        Get the base parcel tile layer configuration (TileJSON).

        Returns:
            TileConfig with PNG/UTFGrid/MVT URL templates
        """
        data = self._get_tiles("/api/v1/parcels")
        return TileConfig(
            tilejson=data.get("tilejson", ""),
            id=data.get("id", ""),
            max_zoom=data.get("maxZoom", 21),
            png_template=data.get("tiles", [""])[0],
            grid_template=data.get("grids", [""])[0],
            mvt_template=data.get("vector", [""])[0],
        )

    def create_filtered_layer(
        self,
        fields: Dict[str, str],
        query: Optional[Dict] = None,
        styles: Optional[str] = None,
    ) -> TileConfig:
        """
        Create a filtered tile layer with custom field values.

        The tile server generates a unique hash for your filter combination.
        Use the returned tile URLs to display filtered parcels on a map.

        Does NOT consume a lookup.

        Args:
            fields: Dict of field_name -> value to filter by
                    e.g. {"owner": "Smith", "usedesc": "Residential"}
            query: Optional query parameters
            styles: Optional style string

        Returns:
            TileConfig with custom tile URLs for the filtered layer
        """
        payload = json.dumps({
            "fields": fields,
            "query": query or {},
            "styles": styles,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.TILE_BASE}/api/v1/sources",
            data=payload,
            headers={
                **self._headers(),
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with self._opener.open(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        return TileConfig(
            tilejson=data.get("tilejson", ""),
            id=data.get("id", ""),
            max_zoom=data.get("maxZoom", 21),
            png_template=data.get("tiles", [""])[0],
            grid_template=data.get("grids", [""])[0],
            mvt_template=data.get("vector", [""])[0],
            query=data.get("query"),
            fields=data.get("fields"),
        )

    def get_tile_png(self, z: int, x: int, y: int) -> bytes:
        """
        Download a parcel PNG tile.

        Args:
            z: Zoom level (11-21)
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            PNG image bytes
        """
        url = f"{self.TILE_BASE}/api/v1/parcels/{z}/{x}/{y}.png"
        req = urllib.request.Request(url, headers=self._headers())
        with self._opener.open(req) as resp:
            return resp.read()

    def get_tile_mvt(self, z: int, x: int, y: int) -> bytes:
        """
        Download a parcel MVT (Mapbox Vector Tile).

        Args:
            z: Zoom level (11-21)
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            MVT protobuf bytes
        """
        url = f"{self.TILE_BASE}/api/v1/parcels/{z}/{x}/{y}.mvt"
        req = urllib.request.Request(url, headers=self._headers())
        with self._opener.open(req) as resp:
            return resp.read()

    def get_tile_utfgrid(self, z: int, x: int, y: int) -> Dict:
        """
        Download a parcel UTFGrid (interactive JSON grid).

        Contains grid data mapping pixel positions to parcel attributes
        (path, address, owner) for map interactivity.

        Args:
            z: Zoom level (11-21)
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            UTFGrid dict with grid, keys, and data
        """
        url = f"{self.TILE_BASE}/api/v1/parcels/{z}/{x}/{y}.json"
        req = urllib.request.Request(url, headers=self._headers())
        with self._opener.open(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int]:
        """
        Convert lat/lng to tile coordinates at a given zoom level.

        Args:
            lat: Latitude
            lng: Longitude
            zoom: Zoom level

        Returns:
            (x, y) tile coordinates
        """
        n = 2 ** zoom
        x = int((lng + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        return x, y

    # ── Static Overlay Tiles ────────────────────────────────────────────

    def get_static_tile(
        self,
        layer: str,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        """
        Download a static overlay tile (FEMA, wetlands, contours, etc.).

        Requires tile_token (Pro/Team account).

        Args:
            layer: Layer name ("fema", "wetlands", "us_contours", "esri_enrichments")
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            MVT protobuf bytes
        """
        token_param = f"?userToken={self._tile_token}" if self._tile_token else ""
        url = f"{self.TILE_BASE}/api/v1/static/{layer}/{z}/{x}/{y}.mvt{token_param}"
        req = urllib.request.Request(url, headers=self._headers())
        with self._opener.open(req) as resp:
            return resp.read()

    # ── Templates ───────────────────────────────────────────────────────

    def get_templates(self, names: Optional[List[str]] = None) -> Dict:
        """
        Get UI template strings (Handlebars templates used client-side).

        Useful for understanding how Regrid renders property data.

        Args:
            names: List of template names to fetch. Defaults to common ones.

        Returns:
            Dict of template_name -> template_html
        """
        if names is None:
            names = [
                "property_detail", "property_fields", "property_foldout",
                "search_result", "search_not_found", "search_pending",
                "list_controls", "list_limits", "filterland",
                "source_details", "source_list_header", "upsell",
            ]

        params = "&".join(f"names[]={n}" for n in names)
        return self._get(f"/templates.json?{params}") or {}

    # ── Streetview ──────────────────────────────────────────────────────

    def get_streetview(self, path: str) -> Optional[bytes]:
        """
        Download streetview image for a property.

        Requires authentication. Returns 423 Locked for anonymous users.

        Args:
            path: Parcel path

        Returns:
            JPEG image bytes, or None if locked/unavailable
        """
        if not path.startswith("/"):
            path = f"/{path}"

        url = f"{self.APP_BASE}{path}/streetside.jpg"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with self._opener.open(req) as resp:
                if resp.status == 200:
                    return resp.read()
        except urllib.error.HTTPError:
            pass
        return None

    # ── Internal Helpers ────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        """Standard request headers."""
        h = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.APP_BASE}/us",
        }
        if self._csrf_token:
            h["X-CSRF-Token"] = self._csrf_token
        return h

    def _get(self, endpoint: str) -> Any:
        """GET request to app.regrid.com."""
        url = f"{self.APP_BASE}{endpoint}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with self._opener.open(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, json.JSONDecodeError):
            return None

    def _get_tiles(self, endpoint: str) -> Any:
        """GET request to tiles.regrid.com."""
        url = f"{self.TILE_BASE}{endpoint}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with self._opener.open(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, json.JSONDecodeError):
            return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI Demo
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Regrid Parcel Data Client")
    print("=" * 60)

    client = RegridClient()

    # Check limits
    limits = client.get_lookup_limits()
    print(f"\nLookup limits: {limits.used}/{limits.total} used "
          f"({limits.remaining} remaining)")
    print(f"Tier: {limits.need}")

    # Search for an address
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "1234 Hooksett Rd Hooksett NH"
    print(f"\nSearching: {query}")
    results = client.search(query)

    if not results:
        print("No results found.")
        sys.exit(0)

    for i, r in enumerate(results[:5]):
        print(f"  [{i}] {r.headline} ({r.context}) - {r.type}")
        print(f"      Path: {r.path}")

    # Get the first parcel result
    parcel_result = next((r for r in results if r.category == "parcel"), None)
    if not parcel_result:
        print("\nNo parcel results. Try a more specific address.")
        sys.exit(0)

    if limits.remaining <= 0:
        print(f"\nNo lookups remaining ({limits.total}/day limit).")
        print("Create a free account at https://app.regrid.com for 25/day.")
        sys.exit(0)

    # Get property details
    print(f"\nFetching property: {parcel_result.path}")
    parcel = client.get_property(parcel_result.path)

    if not parcel:
        print("Could not fetch property data.")
        sys.exit(1)

    print(f"\n--- {parcel.headline} ---")
    print(f"Fields: {len(parcel.fields)}")
    print(f"Has geometry: {parcel.geometry is not None}")
    print(f"Centroid: {parcel.centroid}")

    # Print key fields
    key_fields = [
        "owner", "address", "scity", "szip", "parcelnumb",
        "usedesc", "yearbuilt", "parval", "landval", "improvval",
        "gisacre", "structstyle", "zoning",
    ]
    print("\nKey fields:")
    for k in key_fields:
        v = parcel.fields.get(k)
        if v is not None:
            label = parcel.key.get(k, k)
            print(f"  {label}: {v}")

    # Get boundary/tile config
    region_path = "/".join(parcel_result.path.split("/")[:-1])
    print(f"\nRegion: {region_path}")
    boundary = client.get_boundaries(region_path)
    if boundary:
        print(f"  Parent: {boundary.parent_names}")
        print(f"  Tile layer: {boundary.tile_layer.get('url', 'N/A')}")

    # Get filters
    filters = client.get_filters(region_path)
    free_filters = [f for f in filters if f.free and not f.disabled]
    print(f"\nAvailable free filters: {len(free_filters)}")
    for f in free_filters[:10]:
        print(f"  {f.key}: {f.label} ({f.type})")

    # Test filtered tile layer
    print("\nCreating filtered tile layer (owner=Smith)...")
    try:
        tile_config = client.create_filtered_layer({"owner": "Smith"})
        print(f"  Layer hash: {tile_config.id}")
        print(f"  PNG tiles: {tile_config.png_template}")
    except Exception as e:
        print(f"  Error: {e}")

    # Check remaining limits
    limits = client.get_lookup_limits()
    print(f"\nRemaining lookups: {limits.remaining}/{limits.total}")
    print("\nDone.")
