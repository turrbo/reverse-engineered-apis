"""
NOAA Cameras & Imagery Client
===============================
Covers two systems:
  1. NOAA GOES Satellite CDN  – near real-time ABI imagery from GOES-18/19
  2. NOAA NDBC BuoyCAMs       – marine weather buoy panoramic cameras

Reverse-engineered from:
  - https://cdn.star.nesdis.noaa.gov/             (GOES CDN directory listings)
  - https://www.star.nesdis.noaa.gov/GOES/        (viewer pages, URL patterns)
  - https://www.ndbc.noaa.gov/buoycams.php        (JSON station feed)
  - https://www.ndbc.noaa.gov/kml/buoycams_as_kml.php  (KML with 90+ stations)
  - https://www.ndbc.noaa.gov/station_page.php    (station/camera pages)
  - https://www.ndbc.noaa.gov/data/latest_obs/    (real-time obs)
  - https://www.ndbc.noaa.gov/data/realtime2/     (45-day rolling data)
  - https://www.ndbc.noaa.gov/data/stdmet/        (historical annual archives)

CDN structure confirmed by direct directory browsing:
  - GOES19/ABI/CONUS/GEOCOLOR/   → 5-min CONUS imagery, 6 JPEG resolutions
  - GOES19/ABI/FD/GEOCOLOR/      → 10-min Full Disk imagery, 6 JPEG resolutions
  - GOES19/ABI/SECTOR/{code}/    → 5-min sector imagery, 4 JPEG resolutions
  - GOES19/GLM/CONUS/EXTENT3/    → 5-min GLM lightning, 5 JPEG resolutions
  - GOES18/ABI/CONUS/GEOCOLOR/   → same structure for West satellite

No third-party dependencies beyond the standard library.  urllib is used
for all HTTP requests; json and datetime are used for parsing.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 30  # seconds


def _get(url: str, timeout: int = _DEFAULT_TIMEOUT) -> bytes:
    """Fetch *url* and return the raw response body."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "noaa-cams-client/1.0 (python urllib)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url: str, timeout: int = _DEFAULT_TIMEOUT) -> Any:
    return json.loads(_get(url, timeout))


def _get_text(url: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    return _get(url, timeout).decode("utf-8", errors="replace")


def download_image(url: str, dest_path: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """
    Download *url* to *dest_path*.

    Creates parent directories as needed.
    Returns the resolved local path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    data = _get(url, timeout)
    with open(dest_path, "wb") as fh:
        fh.write(data)
    return os.path.abspath(dest_path)


# ---------------------------------------------------------------------------
# Part 1: GOES Satellite Imagery
# ---------------------------------------------------------------------------

# Base CDN URL
_GOES_CDN = "https://cdn.star.nesdis.noaa.gov"

# ── Satellites ──────────────────────────────────────────────────────────────
# GOES-16 (East, legacy; CDN redirects to GOES-19)
# GOES-18 (West, operational)
# GOES-19 (East, operational – replaced GOES-16)
GOES_SATELLITES = {
    "GOES16": {"desc": "GOES-16 East (legacy; CDN redirects to GOES-19)"},
    "GOES18": {"desc": "GOES-18 West (operational)"},
    "GOES19": {"desc": "GOES-19 East (operational)"},
}

# ── View types ───────────────────────────────────────────────────────────────
# FD    = Full Disk
# CONUS = Continental United States
# SECTOR/<code> = Regional sector
# MESO/<lat-lon> = Mesoscale (floating domain)

# ── GOES-19 East sectors (lower-case codes used in viewer URLs) ───────────────
GOES19_SECTORS = {
    "cam": "Central America",
    "can": "Canada",
    "car": "Caribbean",
    "cgl": "Central Great Lakes",
    "eep": "Eastern Equatorial Pacific",
    "eus": "Eastern United States",
    "ga":  "Gulf of Alaska",
    "mex": "Mexico",
    "na":  "North Atlantic",
    "ne":  "Northeast United States",
    "nr":  "Northern Rockies",
    "nsa": "North South America",
    "pnw": "Pacific Northwest",
    "pr":  "Puerto Rico",
    "psw": "Pacific Southwest",
    "se":  "Southeast United States",
    "smv": "Southern Mississippi Valley",
    "sp":  "Southern Plains",
    "sr":  "Southern Rockies",
    "ssa": "South South America",
    "taw": "Tropical Atlantic – Wide",
    "umv": "Upper Mississippi Valley",
}

# ── GOES-18 West sectors ──────────────────────────────────────────────────────
GOES18_SECTORS = {
    "ak":   "Alaska",
    "ar":   "Arctic",
    "cak":  "Central Alaska",
    "eep":  "Eastern Equatorial Pacific",
    "gwas": "Great Western Atlantic / Sargasso",
    "hi":   "Hawaii",
    "np":   "North Pacific",
    "pnw":  "Pacific Northwest",
    "psw":  "Pacific Southwest",
    "sea":  "Southeast Alaska",
    "tpw":  "Tropical Pacific – Wide",
    "tsp":  "Tropical South Pacific",
    "wus":  "Western United States",
}

# ── ABI Products ─────────────────────────────────────────────────────────────
# Composite / RGB products (available in CONUS, FD, SECTOR)
ABI_COMPOSITES = {
    "GEOCOLOR":               "GeoColor – True color day / IR night",
    "AirMass":                "Air Mass RGB – composite from IR and WV",
    "FireTemperature":        "Fire Temperature RGB – fire identification",
    "Dust":                   "Dust RGB",
    "Sandwich":               "Sandwich RGB – Bands 3 & 13 combo",
    "DayNightCloudMicroCombo":"Day-Night Cloud Micro Combo RGB",
    "DayConvection":          "Day Convection RGB (FD only)",
    "DayLandCloudFire":       "Day Land Cloud Fire (FD only, archived)",
    "DMW":                    "Derived Motion Winds (CONUS/FD)",
}

# Single ABI spectral bands (01-16)
ABI_BANDS = {
    "01": "Visible – blue (0.47 µm)",
    "02": "Visible – red (0.64 µm)",
    "03": "Near-IR – Veggie (0.86 µm)",
    "04": "Near-IR – cirrus (1.37 µm)",
    "05": "Near-IR – snow/ice (1.6 µm)",
    "06": "Near-IR – cloud particle size (2.2 µm)",
    "07": "IR – shortwave (3.9 µm)",
    "08": "IR – water vapor upper (6.2 µm)",
    "09": "IR – water vapor mid (6.9 µm)",
    "10": "IR – water vapor lower (7.3 µm)",
    "11": "IR – cloud-top phase (8.4 µm)",
    "12": "IR – ozone (9.6 µm)",
    "13": "IR – clean longwave (10.3 µm)",
    "14": "IR – longwave (11.2 µm)",
    "15": "IR – dirty longwave (12.3 µm)",
    "16": "IR – CO₂ longwave (13.3 µm)",
}

# GLM (Geostationary Lightning Mapper) products
GLM_PRODUCTS = {
    "EXTENT3": "GLM Flash Extent Density",
}

# ── Resolutions available per view type ──────────────────────────────────────
# Sector GEOCOLOR / composites:
#   300x300, 600x600, 1200x1200, 2400x2400  (jpg)
# Sector single bands:
#   300x300, 600x600, 1200x1200, 2400x2400  (jpg)
# CONUS composites:
#   416x250, 625x375, 1250x750, 2500x1500, 5000x3000, 10000x6000 (jpg)
#   5000x3000 (tif – full resolution GeoTIFF with checksum)
# FD composites:
#   339x339, 678x678, 1808x1808, 5424x5424, 10848x10848 (jpg / tif)
# (Actual availability depends on product; GEOCOLOR has the widest set.)

SECTOR_RESOLUTIONS = ["300x300", "600x600", "1200x1200", "2400x2400"]
CONUS_RESOLUTIONS  = ["416x250", "625x375", "1250x750", "2500x1500", "5000x3000", "10000x6000"]
FD_RESOLUTIONS     = ["339x339", "678x678", "1808x1808", "5424x5424", "10848x10848"]
# GLM products follow CONUS dimensions (5 sizes – no zip at 10000x6000)
GLM_CONUS_RESOLUTIONS = ["416x250", "625x375", "1250x750", "2500x1500", "5000x3000"]


class GOESClient:
    """
    Client for NOAA GOES ABI imagery hosted on the NESDIS STAR CDN.

    URL anatomy
    -----------
    Latest still (always updated in-place):
        {CDN}/{sat}/ABI/{view_type}/{product}/{resolution}.jpg
        {CDN}/{sat}/ABI/{view_type}/{product}/latest.jpg          (alias for largest jpg)
        {CDN}/{sat}/ABI/{view_type}/{product}/thumbnail.jpg       (smallest jpg)

    Timestamped still:
        {CDN}/{sat}/ABI/{view_type}/{product}/{timestamp}_{sat}-ABI-{sector}-{product}-{resolution}.jpg
        where {timestamp} = YYYYDDDHHMM  (DDD = day-of-year)

    Timestamped range animation:
        {CDN}/{sat}/ABI/{view_type}/{product}/{ts_start}-{ts_end}-{sat}-ABI-{SECTOR}-{PRODUCT}-{resolution}.gif
        {CDN}/{sat}/ABI/{view_type}/{product}/{ts_start}-{ts_end}-{sat}-ABI-{SECTOR}-{PRODUCT}-{resolution}.mp4

    Latest rolling animation (always updated):
        {CDN}/{sat}/ABI/{view_type}/{product}/{sat}-{SECTOR}-{PRODUCT}-{resolution}.gif
        {CDN}/{sat}/ABI/{view_type}/{product}/{sat}-{CONUS_or_sector}-{PRODUCT}-{resolution}.mp4

    GLM (lightning) products use a parallel tree:
        {CDN}/{sat}/GLM/{view_type}/{product}/{resolution}.jpg

    Sector codes in filenames use the same lower-case codes as directory names.
    CONUS path uses "CONUS" (upper), sector paths use lower-case, FD uses "FD".

    Notes
    -----
    - GOES-16 redirects to GOES-19 for all current products.
    - Mode file: {CDN}/{sat}/ABI/mode.txt  (e.g. "3\n" = Mode 3, flex-mode)
    """

    CDN = _GOES_CDN

    def __init__(self, satellite: str = "GOES19"):
        if satellite not in GOES_SATELLITES:
            raise ValueError(f"Unknown satellite {satellite!r}. Choose from {list(GOES_SATELLITES)}")
        self.satellite = satellite

    # ── URL builders ─────────────────────────────────────────────────────────

    def _base(self, view_type: str, product: str, instrument: str = "ABI") -> str:
        """Return the CDN directory URL for a product."""
        return f"{self.CDN}/{self.satellite}/{instrument}/{view_type}/{product}"

    def latest_image_url(
        self,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        resolution: str | None = None,
        sector: str | None = None,
        instrument: str = "ABI",
    ) -> str:
        """
        Return the URL of the most-recently-published image (always current).

        Parameters
        ----------
        product    : e.g. "GEOCOLOR", "FireTemperature", "08", "EXTENT3"
        view_type  : "CONUS", "FD", or "SECTOR"  (use sector= for SECTOR)
        resolution : e.g. "1250x750".  None → "latest.jpg" alias (largest).
        sector     : lower-case sector code, required when view_type="SECTOR"
        instrument : "ABI" (default) or "GLM"
        """
        vt = self._resolve_view_type(view_type, sector)
        base = self._base(vt, product, instrument)
        if resolution is None:
            return f"{base}/latest.jpg"
        return f"{base}/{resolution}.jpg"

    def thumbnail_url(
        self,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        sector: str | None = None,
        instrument: str = "ABI",
    ) -> str:
        """Return URL of the thumbnail (smallest resolution) image."""
        vt = self._resolve_view_type(view_type, sector)
        base = self._base(vt, product, instrument)
        return f"{base}/thumbnail.jpg"

    def latest_animation_url(
        self,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        resolution: str = "625x375",
        sector: str | None = None,
        fmt: str = "gif",
    ) -> str:
        """
        Return the URL of the always-current rolling animation.

        Parameters
        ----------
        fmt : "gif" or "mp4"
        """
        vt = self._resolve_view_type(view_type, sector)
        base = self._base(vt, product, "ABI")
        # Animation filenames use UPPER-CASE sector/view in the filename
        display_sector = (sector or view_type).upper()
        filename = f"{self.satellite}-{display_sector}-{product}-{resolution}.{fmt}"
        return f"{base}/{filename}"

    def timestamped_image_url(
        self,
        dt: datetime,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        resolution: str = "2500x1500",
        sector: str | None = None,
        instrument: str = "ABI",
        fmt: str = "jpg",
    ) -> str:
        """
        Return the URL for a specific observation time.

        dt should be a UTC datetime.
        The timestamp format is YYYYDDDHHSS where DDD is the day-of-year.
        """
        ts = self._datetime_to_goes_timestamp(dt)
        vt = self._resolve_view_type(view_type, sector)
        base = self._base(vt, product, instrument)
        display_sector = (sector or view_type).upper() if view_type != "SECTOR" else (sector or "ne")
        # Sector filenames use lower-case sector, CONUS/FD use upper-case
        if view_type == "SECTOR" and sector:
            file_sector = sector.lower()
        else:
            file_sector = view_type.upper()
        filename = f"{ts}_{self.satellite}-{instrument}-{file_sector}-{product}-{resolution}.{fmt}"
        return f"{base}/{filename}"

    def list_available_images(
        self,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        sector: str | None = None,
        instrument: str = "ABI",
        resolution_filter: str | None = None,
        fmt: str = "jpg",
    ) -> list[dict[str, str]]:
        """
        Parse the CDN directory listing and return metadata for all available
        timestamped image files.

        Returns a list of dicts with keys: url, filename, timestamp, resolution.
        Sorted chronologically (oldest first).
        """
        vt = self._resolve_view_type(view_type, sector)
        base = self._base(vt, product, instrument)
        html = _get_text(base + "/")
        return _parse_goes_directory(base, html, fmt=fmt, resolution_filter=resolution_filter)

    def get_latest_metadata(
        self,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        sector: str | None = None,
        instrument: str = "ABI",
    ) -> dict[str, Any]:
        """
        Return metadata for the most-recent image by querying the CDN directory.
        Includes url, filename, timestamp (datetime), resolution, size_bytes.
        """
        images = self.list_available_images(product, view_type, sector, instrument)
        if not images:
            raise RuntimeError("No images found in CDN directory.")
        return images[-1]

    def download_latest(
        self,
        dest_dir: str,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        resolution: str | None = None,
        sector: str | None = None,
        instrument: str = "ABI",
    ) -> str:
        """
        Download the latest image to *dest_dir*.
        Returns the local file path.
        """
        url = self.latest_image_url(product, view_type, resolution, sector, instrument)
        ext = "jpg"
        fname = f"{self.satellite}_{view_type}_{product}_{resolution or 'latest'}.{ext}"
        return download_image(url, os.path.join(dest_dir, fname))

    def download_image_at(
        self,
        dt: datetime,
        dest_dir: str,
        product: str = "GEOCOLOR",
        view_type: str = "CONUS",
        resolution: str = "2500x1500",
        sector: str | None = None,
        instrument: str = "ABI",
        fmt: str = "jpg",
    ) -> str:
        """Download a specific image by UTC datetime."""
        url = self.timestamped_image_url(dt, product, view_type, resolution, sector, instrument, fmt)
        fname = os.path.basename(url)
        return download_image(url, os.path.join(dest_dir, fname))

    def get_mode(self) -> str:
        """Return the current scan mode (e.g. '3' for flex mode)."""
        url = f"{self.CDN}/{self.satellite}/ABI/mode.txt"
        return _get_text(url).strip()

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_view_type(view_type: str, sector: str | None) -> str:
        """Return the CDN path segment for the given view type."""
        if view_type.upper() == "SECTOR":
            if not sector:
                raise ValueError("sector= required when view_type='SECTOR'")
            return f"SECTOR/{sector.lower()}"
        return view_type.upper()

    @staticmethod
    def _datetime_to_goes_timestamp(dt: datetime) -> str:
        """
        Convert a datetime to the GOES CDN timestamp format YYYYDDDHHSS.

        DDD is the Julian day-of-year (001–366).
        HHSS is hour + minute with no separator.
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        doy = dt.timetuple().tm_yday
        return f"{dt.year}{doy:03d}{dt.hour:02d}{dt.minute:02d}"

    @staticmethod
    def goes_timestamp_to_datetime(ts: str) -> datetime:
        """
        Parse a GOES CDN timestamp string (YYYYDDDHHSS) to a UTC datetime.
        """
        year = int(ts[0:4])
        doy  = int(ts[4:7])
        hour = int(ts[7:9])
        minu = int(ts[9:11])
        # Convert day-of-year to month/day
        base = datetime(year, 1, 1, tzinfo=timezone.utc)
        from datetime import timedelta
        dt = base + timedelta(days=doy - 1, hours=hour, minutes=minu)
        return dt

    # ── Convenience builders ──────────────────────────────────────────────────

    def sector_urls(self, sector: str, product: str = "GEOCOLOR") -> dict[str, str]:
        """Return dict of {resolution: url} for a sector product."""
        return {
            res: self.latest_image_url(product, "SECTOR", res, sector)
            for res in SECTOR_RESOLUTIONS
        }

    def conus_urls(self, product: str = "GEOCOLOR") -> dict[str, str]:
        """Return dict of {resolution: url} for CONUS product."""
        return {
            res: self.latest_image_url(product, "CONUS", res)
            for res in CONUS_RESOLUTIONS
        }

    def fulldisk_urls(self, product: str = "GEOCOLOR") -> dict[str, str]:
        """Return dict of {resolution: url} for Full Disk product."""
        return {
            res: self.latest_image_url(product, "FD", res)
            for res in FD_RESOLUTIONS
        }


# ── HTML parser for CDN directory listing ────────────────────────────────────

class _DirListParser(HTMLParser):
    """Extract file links from an Apache/nginx directory listing page."""

    def __init__(self):
        super().__init__()
        self._links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            self._links.append(href)

    @property
    def links(self) -> list[str]:
        return self._links


def _parse_goes_directory(
    base_url: str,
    html: str,
    fmt: str = "jpg",
    resolution_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Parse a GOES CDN directory page and return a sorted list of image metadata.

    Each item:
        filename  : bare filename
        url       : full URL
        timestamp : str like "20260861526"
        dt        : UTC datetime (parsed from timestamp)
        resolution: e.g. "2500x1500"
        format    : "jpg"/"tif"/etc.
    """
    parser = _DirListParser()
    parser.feed(html)

    results: list[dict[str, Any]] = []
    for link in parser.links:
        # Skip directory links and non-image links
        if link.endswith("/") or link.startswith("?") or link == "../":
            continue
        if not link.endswith("." + fmt):
            continue
        # Timestamped filename pattern: YYYYDDDHHSS_SAT-INST-SECTOR-PRODUCT-RESxRES.ext
        parts = link.replace("." + fmt, "").split("_", 1)
        if len(parts) != 2:
            continue  # e.g. static "2400x2400.jpg" – skip
        ts, rest = parts
        if len(ts) != 11 or not ts.isdigit():
            continue
        # resolution is the last dash-separated token
        rest_parts = rest.split("-")
        resolution = rest_parts[-1] if rest_parts else ""
        if resolution_filter and resolution != resolution_filter:
            continue
        try:
            dt = GOESClient.goes_timestamp_to_datetime(ts)
        except Exception:
            dt = None
        results.append({
            "filename":   link,
            "url":        f"{base_url}/{link}",
            "timestamp":  ts,
            "dt":         dt,
            "resolution": resolution,
            "format":     fmt,
        })

    results.sort(key=lambda x: x["timestamp"])
    return results


# ---------------------------------------------------------------------------
# Part 2: NDBC BuoyCAMs
# ---------------------------------------------------------------------------

_NDBC_BASE = "https://www.ndbc.noaa.gov"

# ---------------------------------------------------------------------------
# Known BuoyCAM stations discovered via KML feed (buoycams_as_kml.php).
# This list was accurate as of 2026-03-27; use get_stations() for live data.
# Format: station_id -> (name, lat, lon)
# ---------------------------------------------------------------------------
KNOWN_BUOYCAM_STATIONS: dict[str, tuple[str, float, float]] = {
    "41002": ("SOUTH HATTERAS",        31.743,  -74.955),
    "41004": ("EDISTO",                32.502,  -79.099),
    "41009": ("CANAVERAL",             28.508,  -80.185),
    "41013": ("Frying Pan Shoals, NC", 33.441,  -77.764),
    "41025": ("Diamond Shoals, NC",    35.026,  -75.380),
    "41043": ("NE PUERTO RICO",        21.090,  -64.864),
    "41044": ("NE ST MARTIN",          21.582,  -58.630),
    "41046": ("EAST BAHAMAS",          23.840,  -68.340),
    "41049": ("SOUTH BERMUDA",         27.505,  -62.271),
    "42001": ("MID GULF",              25.925,  -89.628),
    # Atlantic / Caribbean additional stations (partial list from KML)
    "44009": ("Delaware Bay",          38.457,  -74.702),
    "44013": ("Boston",                42.346,  -70.651),
    "44025": ("New York Harbor",       40.251,  -73.166),
    "44027": ("Jonesport, ME",         44.276,  -67.309),
    "44065": ("New York Harbor Entrance", 40.369, -73.703),
    "44066": ("Texas Tower 4",         39.618,  -72.644),
    # Pacific
    "46002": ("Oregon",                42.614, -130.534),
    "46005": ("Washington",            46.057, -131.019),
    "46012": ("Half Moon Bay",         37.363, -122.881),
    "46014": ("Point Arena",           39.235, -123.969),
    "46015": ("Port Orford, OR",       42.747, -124.832),
    "46022": ("Eel River",             40.749, -124.537),
    "46026": ("San Francisco",         37.759, -122.833),
    "46028": ("Cape San Martin",       35.741, -121.884),
    "46029": ("Columbia River Bar",    46.144, -124.511),
    "46047": ("TANNER BANKS",          32.430, -119.533),
    "46059": ("WEST CALIFORNIA",       38.036, -129.972),
    "46069": ("SOUTH SANTA ROSA ISL",  33.674, -120.206),
    "51001": ("NW HAWAII",             23.445, -162.279),
    "51002": ("SW HAWAII",             17.094, -157.808),
    "51003": ("WINDWARD PASSAGE",      14.917, -153.353),
    "51004": ("SE HAWAII",             17.524, -152.382),
    "51101": ("WESTERN MICRONESIA",    24.321,  143.661),
}


class BuoyCAMClient:
    """
    Client for NOAA NDBC BuoyCAM imagery and station metadata.

    Image URL pattern
    -----------------
        https://www.ndbc.noaa.gov/images/buoycam/{CAM_CODE}_{YYYY}_{MM}_{DD}_{HHMM}.jpg

        where CAM_CODE is a 4-char internal camera identifier (e.g. "Z24A")
        that is returned by the buoycams.php JSON feed.

    Latest image (live redirect):
        https://www.ndbc.noaa.gov/buoycam.php?station={STATION_ID}
        → 302 redirect to the current JPEG

    Station JSON feed:
        https://www.ndbc.noaa.gov/buoycams.php
        Returns array of {id, name, lat, lng, img, width, height}
        img may be null if no current image is available.

    KML feed:
        https://www.ndbc.noaa.gov/kml/buoycams.kml        (wrapper)
        https://www.ndbc.noaa.gov/kml/buoycams_as_kml.php (actual KML, refreshed every 30 min)

    Station weather data endpoints:
        Latest obs (text):  https://www.ndbc.noaa.gov/data/latest_obs/{STATION_ID}.txt
        Latest obs (RSS):   https://www.ndbc.noaa.gov/data/latest_obs/{STATION_ID}.rss
        Realtime 45-day:    https://www.ndbc.noaa.gov/data/realtime2/{STATION_ID}.txt
        Historical annual:  https://www.ndbc.noaa.gov/data/stdmet/{STATION_ID}/{STATION_ID}h{YEAR}.txt.gz

    Notes
    -----
    - Images are ~2880×300 panoramic JPEGs (fisheye strip).
    - Photos are taken approximately every hour during daylight hours.
    - An image older than 16 hours is considered stale; buoycam.php returns
      an error message in that case.
    - Some stations have img=null in the JSON (camera offline/night).
    """

    BASE = _NDBC_BASE
    STATIONS_URL  = f"{_NDBC_BASE}/buoycams.php"
    BUOYCAM_URL   = f"{_NDBC_BASE}/buoycam.php"
    IMAGE_BASE    = f"{_NDBC_BASE}/images/buoycam"
    KML_URL       = f"{_NDBC_BASE}/kml/buoycams_as_kml.php"

    def __init__(self):
        self._stations_cache: list[dict[str, Any]] | None = None

    # ── Station list ─────────────────────────────────────────────────────────

    def get_stations(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """
        Return all BuoyCAM stations from the live JSON feed.

        Each station dict:
            id     : str  station identifier (e.g. "41002")
            name   : str  long name
            lat    : float
            lng    : float
            img    : str | None   current image filename (or None if offline)
            width  : int | None   image pixel width
            height : int | None   image pixel height
            has_image: bool

        Sorted by station ID.
        """
        if self._stations_cache is None or force_refresh:
            raw = _get_json(self.STATIONS_URL)
            stations = []
            for stn in raw:
                stn["has_image"] = stn.get("img") is not None
                stn["id"] = stn["id"].upper()
                stations.append(stn)
            stations.sort(key=lambda s: s["id"])
            self._stations_cache = stations
        return self._stations_cache

    def get_station(self, station_id: str) -> dict[str, Any]:
        """Return metadata for a single station by ID.  Raises KeyError if not found."""
        station_id = station_id.upper()
        for stn in self.get_stations():
            if stn["id"] == station_id:
                return stn
        raise KeyError(f"Station {station_id!r} not found in BuoyCAMs feed.")

    def active_stations(self) -> list[dict[str, Any]]:
        """Return only stations that currently have an image available."""
        return [s for s in self.get_stations() if s["has_image"]]

    # ── Image URLs ────────────────────────────────────────────────────────────

    def current_image_url(self, station_id: str) -> str:
        """
        Return the URL of the current BuoyCAM image for a station.

        This calls buoycam.php which returns a 302 redirect to the actual JPEG.
        Following the redirect will deliver the latest image.
        """
        return f"{self.BUOYCAM_URL}?station={station_id.upper()}"

    def current_image_direct_url(self, station_id: str) -> str | None:
        """
        Return the direct CDN URL of the current image by looking up the
        station's img field in the JSON feed.  Returns None if no image.
        """
        stn = self.get_station(station_id)
        if not stn["has_image"]:
            return None
        return f"{self.IMAGE_BASE}/{stn['img']}"

    def image_url_from_filename(self, img_filename: str) -> str:
        """Build a direct URL given an img filename like 'Z24A_2026_03_27_1510.jpg'."""
        return f"{self.IMAGE_BASE}/{img_filename}"

    def parse_image_metadata(self, img_filename: str | None) -> dict[str, Any] | None:
        """
        Parse metadata from a BuoyCAM image filename.

        Filename format: {CAM_CODE}_{YYYY}_{MM}_{DD}_{HHMM}.jpg
        Returns dict with keys: cam_code, year, month, day, time_utc, dt, url
        """
        if not img_filename:
            return None
        name = img_filename.replace(".jpg", "")
        parts = name.split("_")
        if len(parts) != 5:
            return None
        cam_code, year, month, day, hhmm = parts
        try:
            hour = int(hhmm[:2])
            minu = int(hhmm[2:])
            dt = datetime(int(year), int(month), int(day), hour, minu,
                          tzinfo=timezone.utc)
        except (ValueError, IndexError):
            dt = None
        return {
            "cam_code": cam_code,
            "year":     year,
            "month":    month,
            "day":      day,
            "time_utc": hhmm,
            "dt":       dt,
            "url":      self.image_url_from_filename(img_filename),
        }

    # ── Weather data ──────────────────────────────────────────────────────────

    def weather_data_url(self, station_id: str, fmt: str = "txt") -> str:
        """
        Return the URL for the station's latest observations.

        fmt : "txt" (human-readable), "rss" (RSS/XML)
        """
        sid = station_id.upper()
        if fmt == "rss":
            return f"{self.BASE}/data/latest_obs/{sid}.rss"
        return f"{self.BASE}/data/latest_obs/{sid}.txt"

    def realtime_data_url(self, station_id: str) -> str:
        """
        Return the URL for the station's rolling 45-day realtime observation
        table (tab-delimited text, standard meteorological format).
        """
        return f"{self.BASE}/data/realtime2/{station_id.upper()}.txt"

    def historical_data_url(self, station_id: str, year: int, data_type: str = "stdmet") -> str:
        """
        Return the URL for the station's annual historical data (gzip-compressed).

        Parameters
        ----------
        station_id : NDBC station identifier
        year       : 4-digit year
        data_type  : One of the historical archive types:
            "stdmet"  – standard meteorological (wind, wave, pressure, temp) [default]
            "cwind"   – continuous winds (10-min samples)
            "swden"   – spectral wave density
            "swdir"   – spectral wave direction (first descriptor)
            "swdir2"  – spectral wave direction (second descriptor)
            "swr1"    – spectral wave r1 coefficient
            "swr2"    – spectral wave r2 coefficient
            "adcp"    – acoustic Doppler current profiler
            "supl"    – supplemental measurements (conductivity/salinity)

        URL pattern:
            https://www.ndbc.noaa.gov/data/historical/{data_type}/{station_id}h{year}.txt.gz
        The station ID is lower-case in the filename, upper-case in the path.
        """
        sid = station_id.upper()
        sid_lower = station_id.lower()
        # Type code appended to station ID in filename
        type_codes = {
            "stdmet": "h",
            "cwind":  "c",
            "swden":  "w",
            "swdir":  "d",
            "swdir2": "i",
            "swr1":   "j",
            "swr2":   "k",
            "adcp":   "a",
            "supl":   "s",
        }
        code = type_codes.get(data_type, "h")
        return f"{self.BASE}/data/historical/{data_type}/{sid_lower}{code}{year}.txt.gz"

    def monthly_data_url(self, station_id: str, year: int, month: int) -> str:
        """
        Return the URL for a station's monthly data file (current year only).

        Format: https://www.ndbc.noaa.gov/data/stdmet/{Mon}/{STATION_ID}.txt.gz
        where Mon is the 3-letter month abbreviation (Jan, Feb, …, Dec).
        """
        import calendar
        month_abbr = calendar.month_abbr[month]  # 'Jan', 'Feb', ...
        sid = station_id.upper()
        return f"{self.BASE}/data/stdmet/{month_abbr}/{sid}.txt.gz"

    def spectral_wave_url(self, station_id: str) -> str:
        """
        Return the URL for the station's 45-day spectral wave data.
        Format mirrors realtime2 but for the .spec file extension.
        Columns: YY MM DD hh mm WVHT SwH SwP WWH WWP SwD WWD STEEPNESS APD MWD
        """
        return f"{self.BASE}/data/realtime2/{station_id.upper()}.spec"

    def get_latest_weather(self, station_id: str) -> str:
        """Fetch and return the latest weather observations as plain text."""
        return _get_text(self.weather_data_url(station_id, "txt"))

    def get_latest_weather_rss(self, station_id: str) -> str:
        """Fetch and return the latest weather observations as RSS/XML."""
        return _get_text(self.weather_data_url(station_id, "rss"))

    def get_realtime_data(self, station_id: str) -> str:
        """Fetch and return the 45-day realtime data table as plain text."""
        return _get_text(self.realtime_data_url(station_id))

    def parse_realtime_data(self, raw_text: str) -> list[dict[str, str]]:
        """
        Parse the realtime2 text file into a list of observation dicts.

        Column headers are on lines starting with '#'; data follows.
        Returns records from newest to oldest.
        """
        lines = raw_text.splitlines()
        headers: list[str] = []
        records: list[dict[str, str]] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                # First # line = headers, second # line = units (skip units)
                if not headers:
                    headers = stripped.lstrip("#").split()
            elif stripped and headers:
                parts = stripped.split()
                if len(parts) >= len(headers):
                    records.append(dict(zip(headers, parts)))
        return records

    # ── KML feed ─────────────────────────────────────────────────────────────

    def get_kml(self) -> str:
        """Fetch the live KML feed (refreshed every 30 minutes)."""
        return _get_text(self.KML_URL)

    # ── Download helpers ──────────────────────────────────────────────────────

    def download_current_image(self, station_id: str, dest_dir: str) -> str:
        """
        Download the current BuoyCAM image for a station.

        Uses the direct CDN URL (faster, no redirect).
        Returns the local file path.
        """
        url = self.current_image_direct_url(station_id)
        if url is None:
            raise RuntimeError(f"No current image available for station {station_id}")
        stn = self.get_station(station_id)
        fname = stn["img"]
        return download_image(url, os.path.join(dest_dir, fname))

    def download_all_current_images(
        self,
        dest_dir: str,
        max_stations: int | None = None,
    ) -> Iterator[tuple[str, str]]:
        """
        Generator that downloads the current image for every active station.

        Yields (station_id, local_path) as each image is saved.
        Set max_stations to limit for testing.
        """
        stations = self.active_stations()
        if max_stations:
            stations = stations[:max_stations]
        for stn in stations:
            try:
                url = f"{self.IMAGE_BASE}/{stn['img']}"
                fname = stn["img"]
                path = download_image(url, os.path.join(dest_dir, fname))
                yield stn["id"], path
            except Exception as exc:
                yield stn["id"], f"ERROR: {exc}"

    # ── Summary helpers ───────────────────────────────────────────────────────

    def station_summary(self, station_id: str) -> dict[str, Any]:
        """
        Return a combined dict with station metadata, current image URL,
        and links to all data endpoints.
        """
        stn = dict(self.get_station(station_id))
        stn["image_url"]          = self.current_image_url(station_id)
        stn["image_direct_url"]   = self.current_image_direct_url(station_id)
        stn["image_metadata"]     = self.parse_image_metadata(stn.get("img"))
        stn["weather_txt_url"]    = self.weather_data_url(station_id, "txt")
        stn["weather_rss_url"]    = self.weather_data_url(station_id, "rss")
        stn["realtime_url"]       = self.realtime_data_url(station_id)
        stn["spectral_wave_url"]  = self.spectral_wave_url(station_id)
        stn["station_page_url"]   = f"{self.BASE}/station_page.php?station={station_id.upper()}"
        stn["historical_url_2024"] = self.historical_data_url(station_id, 2024)
        return stn


# ---------------------------------------------------------------------------
# Convenience top-level functions
# ---------------------------------------------------------------------------

def goes_latest_url(
    satellite: str = "GOES19",
    product: str = "GEOCOLOR",
    view_type: str = "CONUS",
    resolution: str | None = None,
    sector: str | None = None,
) -> str:
    """One-liner: return the latest GOES image URL."""
    return GOESClient(satellite).latest_image_url(product, view_type, resolution, sector)


def buoycam_current_url(station_id: str) -> str:
    """One-liner: return the current BuoyCAM redirect URL for a station."""
    return BuoyCAMClient().current_image_url(station_id)


def buoycam_stations() -> list[dict[str, Any]]:
    """One-liner: return all BuoyCAM station records from the live JSON feed."""
    return BuoyCAMClient().get_stations()


# ---------------------------------------------------------------------------
# CLI / quick demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    def _print_section(title: str) -> None:
        print(f"\n{'=' * 70}")
        print(f"  {title}")
        print('=' * 70)

    # ── GOES ────────────────────────────────────────────────────────────────
    _print_section("GOES-19 East – CONUS GeoColor")
    g = GOESClient("GOES19")

    print("\nLatest image URLs (CONUS GEOCOLOR):")
    for res, url in g.conus_urls("GEOCOLOR").items():
        print(f"  {res:12s}  {url}")

    print("\nLatest rolling animation (CONUS GEOCOLOR):")
    for fmt in ("gif", "mp4"):
        url = g.latest_animation_url("GEOCOLOR", "CONUS", "625x375", fmt=fmt)
        print(f"  {fmt:4s}  {url}")

    _print_section("GOES-19 East – Northeast Sector GeoColor")
    print("\nSector NE latest image URLs:")
    for res, url in g.sector_urls("ne", "GEOCOLOR").items():
        print(f"  {res:12s}  {url}")

    _print_section("GOES-18 West – Pacific Northwest Sector")
    g18 = GOESClient("GOES18")
    print("\nPNW sector latest images:")
    for res, url in g18.sector_urls("pnw", "GEOCOLOR").items():
        print(f"  {res:12s}  {url}")

    _print_section("GOES-19 Full Disk")
    print("\nFull Disk latest image URLs (GEOCOLOR):")
    for res, url in g.fulldisk_urls("GEOCOLOR").items():
        print(f"  {res:12s}  {url}")

    _print_section("GLM Lightning – GOES-19 NE Sector")
    glm_url = g.latest_image_url("EXTENT3", "SECTOR", "2400x2400", sector="ne", instrument="GLM")
    print(f"\n  GLM EXTENT3: {glm_url}")

    # ── Timestamp example ───────────────────────────────────────────────────
    _print_section("Timestamped image URL example")
    sample_dt = datetime(2026, 3, 27, 16, 21, tzinfo=timezone.utc)
    ts_url = g.timestamped_image_url(sample_dt, "GEOCOLOR", "CONUS", "2500x1500")
    print(f"\n  {sample_dt.isoformat()}  →  {ts_url}")

    # ── BuoyCAMs ────────────────────────────────────────────────────────────
    _print_section("NDBC BuoyCAMs – Station List (first 10)")
    bc = BuoyCAMClient()
    stations = bc.get_stations()
    print(f"\n  Total stations: {len(stations)}")
    active = bc.active_stations()
    print(f"  Active (with image): {len(active)}")
    print()
    for stn in stations[:10]:
        img_note = stn["img"] if stn["has_image"] else "(no image)"
        print(f"  {stn['id']:8s}  {stn['lat']:7.3f}N {stn['lng']:9.3f}E  {img_note}")

    _print_section("BuoyCAM Station 41002 – Full Summary")
    summary = bc.station_summary("41002")
    for key, val in summary.items():
        if isinstance(val, dict):
            print(f"  {key}:")
            for k2, v2 in val.items():
                print(f"    {k2}: {v2}")
        else:
            print(f"  {key}: {val}")

    _print_section("BuoyCAM Active Station Image URLs (first 5)")
    for stn in active[:5]:
        url = bc.current_image_direct_url(stn["id"])
        print(f"  {stn['id']:8s}  {url}")

    print("\nDone.")
