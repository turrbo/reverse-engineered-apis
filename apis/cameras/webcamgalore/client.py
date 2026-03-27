"""
WebcamGalore Python Client
==========================
Reverse-engineered client for https://www.webcamgalore.com

Discovered endpoints and URL patterns:
  - Homepage/country index:     https://www.webcamgalore.com/
  - Country listing:            https://www.webcamgalore.com/{Country}/countrycam-0.html
  - Country alphabetical:       https://www.webcamgalore.com/{Country}/a-1.html  (a-z, paginated)
  - State/region listing:       https://www.webcamgalore.com/{Country}/{State}/a-1.html
  - State (small, no alpha):    https://www.webcamgalore.com/{Country}/{State}/statecam-0.html
  - Webcam detail page:         https://www.webcamgalore.com/webcam/{Country}/{City}/{id}.html
  - City all-cams page:         https://www.webcamgalore.com/webcams/{City}/{id}.html
  - Search:                     https://www.webcamgalore.com/search.php?s={query}
  - Autocomplete:               https://www.webcamgalore.com/autocomplete.php?lang=EN&q={query}
  - Theme listing:              https://www.webcamgalore.com/theme.html
  - Popular (Atom feed):        https://www.webcamgalore.com/popular.xml
  - New additions (Atom feed):  https://www.webcamgalore.com/new.xml
  - Complete list (alpha):      https://www.webcamgalore.com/complete-{letter}.html
  - Geographic map API (XML):   https://www.webcamgalore.com/include/webcammap.php?lang=EN&lonmin=&lonmax=&latmin=&latmax=&w=&h=&tid=
  - 30-day archive (HTML frag): https://www.webcamgalore.com/30dj.php?id={id}&lang=EN&h=60&...
  - 365-day archive (HTML frag):https://www.webcamgalore.com/365dj.php?id={id}&lang=EN&h=60&...
  - 24h archive trigger:        https://www.webcamgalore.com/archiv24.php?id={id}
  - Sitemap index:              https://www.webcamgalore.com/sitemap.xml

Image URL patterns (all on images.webcamgalore.com):
  - Current thumbnail 40x30:   /webcamimages/40x30/{id}-pub.jpg
  - Current thumbnail 80x60:   /webcamimages/80x60/{id}-pub.jpg
  - Current thumbnail 120x90:  /webcamimages/120x90/{id}-pub.jpg
  - Current full-res:          /webcamimages/webcam-{id:06d}.jpg
  - Current named full-res:    /{id}-current-webcam-{city-slug}.jpg
  - Map thumbnail:             /images/mapthumbs/{id}.png
  - 24h archive (hourly):      /webcam-archive/{hour:02d}/webcam-80x60-{id}.jpg
  - Hourly player image:       /webcam-{city-slug}-{day}-{hour}-{id}-{width}.jpg
  - Hourly player full image:  /webcam-{city-slug}-{day}-{hour}-{id}-full.jpg
  - 30-day/365-day archive:    /oneyear/{MM-DD}/{id}.jpg

Geographic taxonomy:
  Continent > Country > State/Region > City > Webcam(s)

  day=0 means today, day=1 means yesterday, etc. (relative to site local time)
  hour = two-digit hour string (e.g. "17" for 17:xx)
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from urllib.parse import urlencode, quote
from typing import Optional, Generator

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    raise ImportError("Install requests: pip install requests")

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.webcamgalore.com"
IMAGE_HOST = "https://images.webcamgalore.com"

THEMES = {
    3: "Airports",
    13: "Animals",
    4: "Bars and Restaurants",
    7: "Beaches",
    9: "Buildings",
    17: "Castles",
    18: "Churches",
    15: "City Views",
    21: "Coasts",
    24: "Collections",
    10: "Construction Sites",
    31: "Cruise Ships",
    8: "Harbors",
    20: "Islands",
    22: "Landmarks",
    6: "Landscapes",
    19: "Mountains",
    32: "Other",
    16: "Parks, Garden",
    28: "Public Places",
    27: "Railroads",
    14: "Rivers",
    26: "Science",
    25: "Seaview",
    30: "Shopping-Malls",
    29: "Ski-Resorts",
    5: "Skyline",
    1: "Traffic",
    2: "Volcanos",
    23: "Weather",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.webcamgalore.com/",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class Webcam:
    """Represents a single webcam entry."""

    def __init__(
        self,
        cam_id: int,
        title: str,
        city: str,
        country: str,
        state: Optional[str] = None,
        description: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        operator: Optional[str] = None,
        operator_url: Optional[str] = None,
        listed_date: Optional[str] = None,
        hits: Optional[int] = None,
        theme_id: Optional[int] = None,
    ):
        self.cam_id = cam_id
        self.title = title
        self.city = city
        self.country = country
        self.state = state
        self.description = description
        self.lat = lat
        self.lon = lon
        self.operator = operator
        self.operator_url = operator_url
        self.listed_date = listed_date
        self.hits = hits
        self.theme_id = theme_id

    # --- URL helpers ---

    @property
    def page_url(self) -> str:
        """Detail page URL."""
        city_slug = self.city.replace(" ", "-").replace("/", "-")
        return f"{BASE_URL}/webcam/{self.country}/{city_slug}/{self.cam_id}.html"

    @property
    def thumbnail_40x30(self) -> str:
        return f"{IMAGE_HOST}/webcamimages/40x30/{self.cam_id}-pub.jpg"

    @property
    def thumbnail_80x60(self) -> str:
        return f"{IMAGE_HOST}/webcamimages/80x60/{self.cam_id}-pub.jpg"

    @property
    def thumbnail_120x90(self) -> str:
        return f"{IMAGE_HOST}/webcamimages/120x90/{self.cam_id}-pub.jpg"

    @property
    def current_image_url(self) -> str:
        """Full-resolution current snapshot (zero-padded 6-digit ID)."""
        return f"{IMAGE_HOST}/webcamimages/webcam-{self.cam_id:06d}.jpg"

    @property
    def map_thumbnail_url(self) -> str:
        """Small thumbnail used on the map view."""
        return f"{IMAGE_HOST}/images/mapthumbs/{self.cam_id}.png"

    def named_current_image_url(self, city_slug: Optional[str] = None) -> str:
        """
        Alternate current image URL using city slug.
        E.g. https://images.webcamgalore.com/2907-current-webcam-Altenmarkt-a-d-Alz.jpg
        """
        if city_slug is None:
            city_slug = self.city.replace(" ", "-")
        return f"{IMAGE_HOST}/{self.cam_id}-current-webcam-{city_slug}.jpg"

    def archive_daily_url(self, month: int, day: int) -> str:
        """
        URL for daily archive snapshot (one per day, stored up to ~365 days).
        Pattern: /oneyear/MM-DD/{id}.jpg
        """
        return f"{IMAGE_HOST}/oneyear/{month:02d}-{day:02d}/{self.cam_id}.jpg"

    def hourly_image_url(
        self, city_slug: str, day_offset: int, hour: int, width: int = 640
    ) -> str:
        """
        URL for hourly timelapse image from the in-page player.
        day_offset: 0=today, 1=yesterday, 2=day before, etc.
        hour: 0-23 (the hour stored on server; comes from wcgplayerHourIndex in page JS)
        width: image width (640 is default player size; use 'full' string for full res)
        """
        slug = city_slug.lower().replace(" ", "-")
        return (
            f"{IMAGE_HOST}/webcam-{slug}-{day_offset}-{hour}-{self.cam_id}-{width}.jpg"
        )

    def hourly_full_url(self, city_slug: str, day_offset: int, hour: int) -> str:
        """Full-resolution version of the hourly timelapse image."""
        slug = city_slug.lower().replace(" ", "-")
        return f"{IMAGE_HOST}/webcam-{slug}-{day_offset}-{hour}-{self.cam_id}-full.jpg"

    def archive_hourly_thumbnail(self, hour: int) -> str:
        """
        80x60 thumbnail for 24-hour archive (from ctooltip CSS pattern).
        hour: two-digit string (00-23)
        """
        return f"{IMAGE_HOST}/webcam-archive/{hour:02d}/webcam-80x60-{self.cam_id}.jpg"

    def __repr__(self) -> str:
        return (
            f"Webcam(id={self.cam_id}, title={self.title!r}, "
            f"city={self.city!r}, country={self.country!r})"
        )


# ---------------------------------------------------------------------------
# HTTP session helper
# ---------------------------------------------------------------------------

def _make_session(
    retries: int = 3,
    backoff_factor: float = 0.5,
    timeout: int = 20,
) -> "requests.Session":
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    session._default_timeout = timeout
    return session


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_int(s: str) -> Optional[int]:
    try:
        return int(re.sub(r"\D", "", s))
    except (ValueError, TypeError):
        return None


def _sanitize_xml(xml_text: str) -> str:
    """Replace bare & with &amp; in XML to handle malformed feeds."""
    return re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", xml_text)


def _extract_country_list(html: str) -> list[dict]:
    """Parse the homepage to extract all countries with their webcam counts."""
    # The actual HTML pattern uses class="wcg-idx" with either countrycam-0 or a-1
    pattern = re.compile(
        r'<a class="wcg-idx" href="/([^/]+)/(?:a-\d+|countrycam-\d+)\.html">([^<]+)</a></b>\s*\((\d+)\)'
    )
    results = []
    for m in pattern.finditer(html):
        slug, name, count = m.group(1), m.group(2).strip(), int(m.group(3))
        # Remove stray HTML entities
        name = re.sub(r"&[a-z]+;", "", name).strip()
        results.append({"slug": slug, "name": name, "count": count})
    return results


def _extract_webcam_links_from_listing(html: str) -> list[dict]:
    """
    Extract webcam links from a country/state alphabetical listing page.
    Returns list of dicts with keys: cam_id, city, country, title, description,
    operator, operator_url, hits.
    """
    results = []
    # Main listing blocks
    for m in re.finditer(
        r'href="https://www\.webcamgalore\.com/webcam/([^/]+)/([^/]+)/(\d+)\.html"',
        html,
    ):
        country, city, cam_id = m.group(1), m.group(2), int(m.group(3))
        results.append({"cam_id": cam_id, "country": country, "city": city})
    return results


def _parse_webcammap_xml(xml_text: str) -> list[Webcam]:
    """Parse the XML response from /include/webcammap.php into Webcam objects."""
    try:
        root = ET.fromstring(_sanitize_xml(xml_text))
    except ET.ParseError:
        return []

    webcams = []
    for elem in root.findall("webcam"):
        try:
            cam_id = int(elem.get("wid", 0))
            label = elem.get("label", "")
            title = elem.get("title", "")
            url = elem.get("url", "")
            desc = elem.get("desc", "")
            lat = float(elem.get("lat", 0) or 0) or None
            lon = float(elem.get("lon", 0) or 0) or None

            # Extract country + city from URL: /webcam/{Country}/{City}/{id}.html
            url_m = re.search(r"/webcam/([^/]+)/([^/]+)/\d+\.html", url)
            country = url_m.group(1) if url_m else ""
            city = url_m.group(2) if url_m else label

            webcams.append(
                Webcam(
                    cam_id=cam_id,
                    title=title,
                    city=city,
                    country=country,
                    description=desc,
                    lat=lat,
                    lon=lon,
                )
            )
        except (ValueError, AttributeError):
            continue

    return webcams


def _parse_detail_page(html: str, cam_id: int) -> Optional[Webcam]:
    """
    Parse a webcam detail page (HTML) into a Webcam object.
    Extracts all available metadata.
    """
    # Extract JSON-LD for geo coordinates
    lat, lon = None, None
    ld_match = re.search(
        r'"latitude"\s*:\s*"?([+-]?\d+\.?\d*)"?.*?"longitude"\s*:\s*"?([+-]?\d+\.?\d*)"?',
        html,
        re.DOTALL,
    )
    if ld_match:
        try:
            lat = float(ld_match.group(1))
            lon = float(ld_match.group(2))
        except ValueError:
            pass

    # Extract title from <h1>
    title_m = re.search(r"<h1[^>]*>Webcam ([^<]+?),\s*[^<]+?:\s*([^<]+)</h1>", html)
    city_from_h1 = ""
    title_from_h1 = ""
    if title_m:
        city_from_h1 = title_m.group(1).strip()
        title_from_h1 = title_m.group(2).strip()

    # Extract from OG title fallback
    og_title_m = re.search(r'property="og:title"\s+content="([^"]+)"', html)
    og_title = og_title_m.group(1) if og_title_m else ""

    # Extract description from meta
    desc_m = re.search(r'property="og:description"\s+content="([^"]+)"', html)
    description = desc_m.group(1) if desc_m else None

    # Extract country/city/state from breadcrumb
    bc_matches = re.findall(r'href="/([^"]+)"[^>]*>\s*<span itemprop="name">([^<]+)</span>', html)
    country = ""
    state = ""
    city = city_from_h1

    for href, name in bc_matches:
        if "/a-1.html" in href or "/statecam-0.html" in href:
            # This is a state link
            parts = href.split("/")
            if len(parts) >= 2:
                if not country:
                    country = parts[0]
                state = name.strip()
        elif re.match(r"^[A-Z][a-zA-Z-]+/a-\d+\.html$", href):
            country = href.split("/")[0]
        elif re.match(r"^[A-Z][a-zA-Z-]+/[A-Z][a-zA-Z-]+/a-", href):
            parts = href.split("/")
            country = parts[0]
            state = name.strip()

    # Extract operator info
    op_m = re.search(
        r'Operator:\s*<b><a href="([^"]+)"[^>]*>([^<]+)</a></b>', html
    )
    operator = op_m.group(2).strip() if op_m else None
    operator_url = op_m.group(1) if op_m else None

    # Extract listed date and hits
    listed_m = re.search(r"Listed:\s*([A-Z][a-z]{2}\s+\d+,\s*\d{4})", html)
    listed_date = listed_m.group(1) if listed_m else None

    hits_m = re.search(r"Hits:\s*(\d+)", html)
    hits = int(hits_m.group(1)) if hits_m else None

    # Extract city-slug for image URLs from JS
    city_slug_m = re.search(r"wcgplayerImageCityname='([^']+)'", html)
    city_slug = city_slug_m.group(1) if city_slug_m else None

    # Extract theme from map link
    theme_m = re.search(r"/webcam-map\?tid=(\d+)", html)
    theme_id = int(theme_m.group(1)) if theme_m else None

    # Determine country from canonical URL
    canon_m = re.search(
        r'rel="canonical"\s+href="https://www\.webcamgalore\.com/webcam/([^/]+)/([^/]+)/',
        html,
    )
    if canon_m:
        country = canon_m.group(1)
        city = canon_m.group(2).replace("-", " ")

    if not city and city_slug:
        city = city_slug.replace("-", " ").title()

    title = title_from_h1 or og_title

    return Webcam(
        cam_id=cam_id,
        title=title,
        city=city,
        country=country,
        state=state or None,
        description=description,
        lat=lat,
        lon=lon,
        operator=operator,
        operator_url=operator_url,
        listed_date=listed_date,
        hits=hits,
        theme_id=theme_id,
    )


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class WebcamGaloreClient:
    """
    Python client for WebcamGalore.com.

    Usage
    -----
    >>> client = WebcamGaloreClient()

    # Get all countries with webcam counts
    >>> countries = client.get_countries()

    # Search for a location
    >>> results = client.search("Munich")

    # Get webcams by bounding box (fastest, uses the map XML API)
    >>> cams = client.get_webcams_by_bbox(latmin=47, latmax=48, lonmin=11, lonmax=12)

    # Get webcams for a country
    >>> cams = client.get_webcams_by_country("Germany", max_pages=3)

    # Get webcam detail
    >>> cam = client.get_webcam_detail(6985)

    # Download current snapshot
    >>> data = client.download_current_image(cam, size="120x90")
    """

    def __init__(
        self,
        delay: float = 0.5,
        retries: int = 3,
        timeout: int = 20,
        lang: str = "EN",
    ):
        """
        Parameters
        ----------
        delay : float
            Seconds to sleep between HTTP requests (be polite).
        retries : int
            Number of retries on transient failures.
        timeout : int
            HTTP request timeout in seconds.
        lang : str
            Language code: EN, DE, IT, ES, FR, DK.
        """
        self.delay = delay
        self.timeout = timeout
        self.lang = lang
        self._session = _make_session(retries=retries, timeout=timeout)
        self._last_request = 0.0

    # --- Low-level HTTP ---

    def _get(self, url: str, **kwargs) -> "requests.Response":
        """Rate-limited GET request."""
        elapsed = time.time() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.time()

        timeout = kwargs.pop("timeout", self.timeout)
        resp = self._session.get(url, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp

    # -----------------------------------------------------------------------
    # Country / taxonomy
    # -----------------------------------------------------------------------

    def get_countries(self) -> list[dict]:
        """
        Return all countries listed on the homepage with webcam counts.

        Returns
        -------
        list of dicts: [{"slug": str, "name": str, "count": int}, ...]
        """
        resp = self._get(f"{BASE_URL}/")
        return _extract_country_list(resp.text)

    def get_states(self, country: str) -> list[dict]:
        """
        Return the state/region breakdown for a country.

        Parameters
        ----------
        country : str  e.g. "Germany", "Austria", "Italy"

        Returns
        -------
        list of dicts: [{"slug": str, "name": str, "count": int, "url": str}, ...]
        """
        url = f"{BASE_URL}/{country}/countrycam-0.html"
        resp = self._get(url)
        html = resp.text

        # Pattern: href="/Germany/Bavaria/a-1.html">Bavaria</a> (377)
        pattern = re.compile(
            r'href="(/[^/]+/([^/]+)/(?:a-1|statecam-0)\.html)"[^>]*>([^<]+)</a>\s*\((\d+)\)'
        )
        results = []
        seen = set()
        for m in pattern.finditer(html):
            href, slug, name, count = m.group(1), m.group(2), m.group(3).strip(), int(m.group(4))
            if slug not in seen:
                seen.add(slug)
                results.append(
                    {
                        "slug": slug,
                        "name": name,
                        "count": count,
                        "url": f"{BASE_URL}{href}",
                    }
                )
        return results

    # -----------------------------------------------------------------------
    # Webcam listing (paginated HTML scraping)
    # -----------------------------------------------------------------------

    def get_webcams_by_country(
        self,
        country: str,
        state: Optional[str] = None,
        letter: str = "a",
        max_pages: int = 10,
    ) -> list[dict]:
        """
        Scrape webcam listings for a country (or state within a country).

        URL structure (discovered via reverse engineering)
        --------------------------------------------------
        Large countries use alphabetical pagination:
          GET /{Country}/a-1.html    (page 1, ~10 webcams each)
          GET /{Country}/a-2.html    (page 2)
          ...
          GET /{Country}/a-N.html    (last page)

        Small countries use a single page:
          GET /{Country}/countrycam-0.html

        With state/region:
          GET /{Country}/{State}/a-1.html

        NOTE: The ``letter`` parameter here is the pagination prefix character
        (always "a" in practice on the live site — it is NOT an alphabetical filter).
        Page numbers are integers (1, 2, 3 ...).

        Parameters
        ----------
        country : str   e.g. "Germany"
        state : str     Optional state/region slug e.g. "Bavaria", "Lombardy"
        letter : str    Pagination prefix (default "a", always "a" on live site)
        max_pages : int Maximum number of pages to fetch

        Returns
        -------
        list of dicts with keys: cam_id, country, city, url
        """
        results = []
        base = f"{BASE_URL}/{country}"
        if state:
            base = f"{base}/{state}"

        # Try paginated a-N.html first
        for page in range(1, max_pages + 1):
            url = f"{base}/{letter}-{page}.html"
            try:
                resp = self._get(url)
            except Exception:
                if page == 1:
                    # Small country — try countrycam-0.html fallback
                    try:
                        resp = self._get(f"{base}/countrycam-0.html")
                        new = _extract_webcam_links_from_listing(resp.text)
                        results.extend(new)
                    except Exception:
                        pass
                break

            html = resp.text
            # Detect redirect to first page (pagination ended)
            if f"{letter}-{page}" not in resp.url and page > 1:
                break

            new = _extract_webcam_links_from_listing(html)
            if not new:
                break
            results.extend(new)

            # Check if more pages exist by looking at pagination links
            page_nums = {int(p) for p in re.findall(rf"/{re.escape(letter)}-(\d+)\.html", html)}
            if page_nums and page >= max(page_nums):
                break

        # Deduplicate by cam_id
        seen = set()
        unique = []
        for r in results:
            if r["cam_id"] not in seen:
                seen.add(r["cam_id"])
                unique.append(r)
        return unique

    def iter_all_webcams_for_country(
        self, country: str, state: Optional[str] = None
    ) -> Generator[dict, None, None]:
        """
        Generator that yields every webcam entry for a country (all letters, all pages).
        Memory-efficient for large countries like Germany (1,368 cams).
        """
        letters = list("abcdefghijklmnopqrstuvwxyz")
        for letter in letters:
            base = f"{BASE_URL}/{country}"
            if state:
                base = f"{base}/{state}"
            page = 1
            while True:
                url = f"{base}/{letter}-{page}.html"
                try:
                    resp = self._get(url)
                except Exception:
                    break

                html = resp.text
                # Check canonical URL to detect we were redirected back to page 1
                canon_m = re.search(r'rel="canonical"\s+href="([^"]+)"', html)
                if canon_m and f"{letter}-{page}" not in canon_m.group(1) and page > 1:
                    break

                cams = _extract_webcam_links_from_listing(html)
                if not cams:
                    break
                for cam in cams:
                    yield cam
                page += 1

    # -----------------------------------------------------------------------
    # Map / geographic API (most efficient — returns structured XML)
    # -----------------------------------------------------------------------

    def get_webcams_by_bbox(
        self,
        latmin: float,
        latmax: float,
        lonmin: float,
        lonmax: float,
        theme_id: int = 0,
        map_width: int = 1200,
        map_height: int = 900,
    ) -> list[Webcam]:
        """
        Retrieve webcams within a geographic bounding box using the map XML API.
        This is the most efficient method — returns structured data without HTML parsing.

        Parameters
        ----------
        latmin, latmax : float  Latitude range
        lonmin, lonmax : float  Longitude range
        theme_id : int          Filter by theme (0=all, see THEMES dict)
        map_width/height : int  Virtual map dimensions (affects clustering; use large values)

        Returns
        -------
        list of Webcam objects with id, title, city, country, lat, lon, description
        """
        params = {
            "lang": self.lang,
            "lonmin": lonmin,
            "lonmax": lonmax,
            "latmin": latmin,
            "latmax": latmax,
            "w": map_width,
            "h": map_height,
            "tid": theme_id,
        }
        url = f"{BASE_URL}/include/webcammap.php?{urlencode(params)}"
        headers = {"Referer": f"{BASE_URL}/webcam-map"}
        resp = self._get(url, headers=headers)
        return _parse_webcammap_xml(resp.text)

    def get_webcams_by_country_bbox(
        self, country: str, theme_id: int = 0
    ) -> list[Webcam]:
        """
        Convenience wrapper: returns all webcams in common country bounding boxes.
        Uses the map XML API.
        """
        bboxes = {
            "Germany": (47.3, 55.1, 5.9, 15.0),
            "Italy": (36.6, 47.1, 6.6, 18.5),
            "Austria": (46.4, 49.0, 9.5, 17.2),
            "France": (41.3, 51.1, -5.1, 9.6),
            "Switzerland": (45.8, 47.9, 5.9, 10.5),
            "USA": (24.5, 49.4, -125.0, -66.9),
            "Spain": (35.9, 43.8, -9.3, 4.3),
            "Croatia": (42.4, 46.6, 13.5, 19.5),
            "Norway": (57.9, 71.2, 4.5, 31.2),
            "Sweden": (55.3, 69.1, 11.1, 24.2),
            "Greece": (34.8, 41.8, 19.4, 29.6),
            "Portugal": (36.8, 42.2, -9.5, -6.2),
            "Netherlands": (50.8, 53.6, 3.3, 7.2),
            "Poland": (49.0, 54.9, 14.1, 24.2),
            "Turkey": (36.0, 42.1, 26.0, 44.8),
        }
        bbox = bboxes.get(country)
        if bbox is None:
            raise ValueError(
                f"No built-in bounding box for {country!r}. "
                "Use get_webcams_by_bbox() with explicit coordinates."
            )
        latmin, latmax, lonmin, lonmax = bbox
        return self.get_webcams_by_bbox(
            latmin=latmin, latmax=latmax, lonmin=lonmin, lonmax=lonmax,
            theme_id=theme_id
        )

    # -----------------------------------------------------------------------
    # Webcam detail page
    # -----------------------------------------------------------------------

    def get_webcam_detail(self, cam_id: int, country: str = "", city: str = "") -> Optional[Webcam]:
        """
        Fetch and parse a webcam detail page.
        If country and city are unknown you can pass empty strings — the URL
        will be constructed from the search/autocomplete first.

        Parameters
        ----------
        cam_id : int
        country : str  e.g. "Germany"
        city : str     e.g. "Munich"

        Returns
        -------
        Webcam or None
        """
        if country and city:
            city_slug = city.replace(" ", "-")
            url = f"{BASE_URL}/webcam/{country}/{city_slug}/{cam_id}.html"
        else:
            # Try to find it via search
            results = self.search(str(cam_id))
            if results:
                url = results[0].page_url
            else:
                return None

        resp = self._get(url)
        return _parse_detail_page(resp.text, cam_id)

    def get_webcam_page_metadata(self, cam_id: int, country: str, city: str) -> dict:
        """
        Parse the JS variables from a webcam detail page to extract
        timelapse player configuration (available hours, city slug, etc.).

        Returns dict with:
          city_slug, day_count, hour_count, hour_index, hour_captions,
          day_captions, player_width, player_height
        """
        city_slug = city.replace(" ", "-")
        url = f"{BASE_URL}/webcam/{country}/{city_slug}/{cam_id}.html"
        resp = self._get(url)
        html = resp.text

        meta = {"cam_id": cam_id}

        def _extract_js_var(name: str) -> Optional[str]:
            m = re.search(rf"var {re.escape(name)}=([^;]+);", html)
            return m.group(1) if m else None

        city_slug_m = re.search(r"wcgplayerImageCityname='([^']+)'", html)
        meta["city_slug"] = city_slug_m.group(1) if city_slug_m else city_slug.lower()

        day_count_m = _extract_js_var("wcgplayerDayCount")
        meta["day_count"] = int(day_count_m) if day_count_m else 5

        day_cap_m = re.search(r'wcgplayerDayCaption=(\[[^\]]+\])', html)
        if day_cap_m:
            import json
            try:
                meta["day_captions"] = json.loads(day_cap_m.group(1))
            except Exception:
                meta["day_captions"] = []

        hour_count_m = re.search(r'wcgplayerHourCount=(\[[^\]]+\])', html)
        if hour_count_m:
            import json
            try:
                meta["hour_count"] = json.loads(hour_count_m.group(1))
            except Exception:
                meta["hour_count"] = []

        hour_idx_m = re.search(r'wcgplayerHourIndex=(\[[^\]]+\])', html)
        if hour_idx_m:
            import json
            try:
                meta["hour_index"] = json.loads(hour_idx_m.group(1))
            except Exception:
                meta["hour_index"] = []

        hour_cap_m = re.search(r'wcgplayerHourCaption=(\[[^\]]+\])', html)
        if hour_cap_m:
            import json
            try:
                meta["hour_captions"] = json.loads(hour_cap_m.group(1))
            except Exception:
                meta["hour_captions"] = []

        pw_m = _extract_js_var("wcgplayerImageWidth")
        meta["player_width"] = int(pw_m) if pw_m else 640

        return meta

    # -----------------------------------------------------------------------
    # Archive APIs
    # -----------------------------------------------------------------------

    def get_archive_30d(
        self,
        cam_id: int,
        city: str = "",
        lang: Optional[str] = None,
        timezone: str = "Europe/Berlin",
        fullview_width: int = 1280,
        fullview_height: int = 960,
    ) -> list[dict]:
        """
        Fetch the 30-day image archive for a webcam.
        Returns list of dicts: [{"date": "MM/DD YY", "url": str, "thumb_url": str}, ...]
        """
        lang = lang or self.lang
        params = {
            "id": cam_id,
            "lang": lang,
            "h": 60,
            "timezone_name": timezone,
            "cityname": city,
            "fullview_width": fullview_width,
            "fullview_height": fullview_height,
        }
        url = f"{BASE_URL}/30dj.php?{urlencode(params)}"
        headers = {
            "Referer": f"{BASE_URL}/webcam/",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = self._get(url, headers=headers)

        # Response is a JSON-encoded HTML string
        html_frag = resp.text.strip('"').replace('\\"', '"').replace("\\/", "/").replace("\\n", "\n")

        results = []
        for m in re.finditer(
            r'href="(https://images\.webcamgalore\.com/oneyear/[^"]+)"[^>]*'
            r'data-title="[^"]*?([\d/]+ \d+)"[^>]*>'
            r'<img src="([^"]+)"',
            html_frag,
        ):
            results.append({
                "date": m.group(2).strip(),
                "url": m.group(1),
                "thumb_url": m.group(3),
            })
        return results

    def get_archive_365d(
        self,
        cam_id: int,
        city: str = "",
        lang: Optional[str] = None,
        timezone: str = "Europe/Berlin",
        fullview_width: int = 1280,
        fullview_height: int = 960,
    ) -> list[dict]:
        """
        Fetch the 365-day image archive for a webcam.
        Returns list of dicts: [{"date": str, "url": str, "thumb_url": str}, ...]
        """
        lang = lang or self.lang
        params = {
            "id": cam_id,
            "lang": lang,
            "h": 60,
            "timezone_name": timezone,
            "cityname": city,
            "fullview_width": fullview_width,
            "fullview_height": fullview_height,
        }
        url = f"{BASE_URL}/365dj.php?{urlencode(params)}"
        headers = {
            "Referer": f"{BASE_URL}/webcam/",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = self._get(url, headers=headers)
        html_frag = resp.text.strip('"').replace('\\"', '"').replace("\\/", "/").replace("\\n", "\n")

        results = []
        for m in re.finditer(
            r'href="(https://images\.webcamgalore\.com/oneyear/[^"]+)"[^>]*'
            r'data-title="[^"]*?([\d/.]+ ?\d*)"[^>]*>'
            r'<img src="([^"]+)"',
            html_frag,
        ):
            results.append({
                "date": m.group(2).strip(),
                "url": m.group(1),
                "thumb_url": m.group(3),
            })
        return results

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    def search(self, query: str, max_pages: int = 5) -> list[Webcam]:
        """
        Search webcams by location name or keyword.
        Uses the search.php endpoint (returns an HTML page).

        Pagination
        ----------
        Results are returned 10 per page. Use the ``start`` parameter for page N:
          GET /search.php?s={query}&start={N}   (N=1 is page 1, N=2 is page 2, etc.)

        A search for "beach" returns 71 pages (711 results total).

        Parameters
        ----------
        query     : str  Free-text search term
        max_pages : int  Maximum pages to fetch (default 5 = up to 50 results)

        Returns
        -------
        list of Webcam (partial metadata: id, city, country)
        """
        webcams = []
        seen_ids: set[int] = set()

        for page in range(1, max_pages + 1):
            if page == 1:
                url = f"{BASE_URL}/search.php?s={quote(query)}"
            else:
                url = f"{BASE_URL}/search.php?s={quote(query)}&start={page}"

            try:
                resp = self._get(url)
            except Exception:
                break

            html = resp.text

            page_cams = []
            for m in re.finditer(
                r'href="https://www\.webcamgalore\.com/webcam/([^/]+)/([^/]+)/(\d+)\.html"',
                html,
            ):
                country, city, cam_id = m.group(1), m.group(2), int(m.group(3))
                if cam_id not in seen_ids:
                    seen_ids.add(cam_id)
                    city_display = city.replace("-", " ")
                    page_cams.append(
                        Webcam(cam_id=cam_id, title="", city=city_display, country=country)
                    )

            if not page_cams:
                break  # No more results

            webcams.extend(page_cams)

            # Detect total pages from pagination links (&start=N)
            page_nums = {int(p) for p in re.findall(r"&start=(\d+)", html)}
            if page_nums and page >= max(page_nums):
                break  # Reached the last page

        # Deduplicate (safety net)
        seen = set()
        unique = []
        for w in webcams:
            if w.cam_id not in seen:
                seen.add(w.cam_id)
                unique.append(w)
        return unique

    def autocomplete(self, query: str) -> list[str]:
        """
        Location autocomplete (returns a JSON array of city+country strings).

        Returns
        -------
        list of str: e.g. ["Munich, Germany", "Munich, Indiana, USA", ...]
        """
        params = {"lang": self.lang, "q": query}
        url = f"{BASE_URL}/autocomplete.php?{urlencode(params)}"
        headers = {
            "Referer": f"{BASE_URL}/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*",
        }
        resp = self._get(url, headers=headers)
        import json
        try:
            data = json.loads(resp.text)
            if isinstance(data, list):
                return [str(x) for x in data if query.lower() in str(x).lower()]
        except Exception:
            pass
        return []

    # -----------------------------------------------------------------------
    # Complete A-Z index (all 8000+ cameras)
    # -----------------------------------------------------------------------

    def iter_all_webcam_urls(self) -> Generator[str, None, None]:
        """
        Yield every webcam detail-page URL from the A-Z complete index.

        Endpoint pattern: GET /complete-{letter}.html  (26 pages, one per letter)

        Each letter page contains hundreds of webcam links grouped by country.
        Total across all 26 letters: 8000+ unique webcam URLs.
        Deduplicates automatically.

        Yields
        ------
        str : canonical webcam detail URL
        """
        seen: set[str] = set()
        for letter in "abcdefghijklmnopqrstuvwxyz":
            try:
                resp = self._get(f"{BASE_URL}/complete-{letter}.html")
            except Exception:
                continue
            for m in re.finditer(
                r'href="(https://(?:www\.)?webcamgalore\.com/webcam/[^"]+\.html)"',
                resp.text,
            ):
                u = m.group(1)
                if u not in seen:
                    seen.add(u)
                    yield u

    def iter_all_webcams(
        self, fetch_details: bool = False
    ) -> Generator[Webcam, None, None]:
        """
        Iterate over every webcam on the site (~8000+).

        Parameters
        ----------
        fetch_details : bool
            If False (default), yields minimal Webcam objects built from URL alone.
            If True, fetches each detail page for full metadata
            (8000+ requests, ~2-3 hours with default rate limiting).

        Yields
        ------
        Webcam objects
        """
        for url in self.iter_all_webcam_urls():
            m = re.match(
                r"https://(?:www\.)?webcamgalore\.com/webcam/([^/]+)/([^/]+)/(\d+)\.html",
                url,
            )
            if not m:
                continue
            country, city_slug, cam_id = m.group(1), m.group(2), int(m.group(3))
            city = city_slug.replace("-", " ")

            if fetch_details:
                try:
                    cam = self.get_webcam_detail(cam_id, country, city_slug)
                    if cam:
                        yield cam
                except Exception:
                    pass
            else:
                yield Webcam(
                    cam_id=cam_id,
                    title="",
                    city=city,
                    country=country,
                )

    # -----------------------------------------------------------------------
    # Feeds
    # -----------------------------------------------------------------------

    def get_popular_webcams(self) -> list[dict]:
        """
        Fetch the top-20 most popular webcams in the last 24 hours (Atom feed).

        Returns
        -------
        list of dicts: [{"rank": int, "title": str, "summary": str, "url": str, "updated": str}, ...]
        """
        resp = self._get(f"{BASE_URL}/popular.xml")
        try:
            root = ET.fromstring(_sanitize_xml(resp.text))
        except ET.ParseError:
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        results = []
        for i, entry in enumerate(root.findall("atom:entry", ns), 1):
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            summary_el = entry.find("atom:summary", ns)
            updated_el = entry.find("atom:updated", ns)

            # Extract cam_id from link
            link = link_el.get("href", "") if link_el is not None else ""
            cam_id_m = re.search(r"/(\d+)\.html", link)

            results.append({
                "rank": i,
                "title": title_el.text if title_el is not None else "",
                "summary": summary_el.text if summary_el is not None else "",
                "url": link,
                "cam_id": int(cam_id_m.group(1)) if cam_id_m else None,
                "updated": updated_el.text if updated_el is not None else "",
            })
        return results

    def get_new_webcams(self, limit: int = 20) -> list[dict]:
        """
        Fetch recently added webcams (Atom feed, ~20 entries).

        Returns
        -------
        list of dicts: [{"title": str, "summary": str, "url": str, "cam_id": int, "updated": str}, ...]
        """
        resp = self._get(f"{BASE_URL}/new.xml")
        try:
            root = ET.fromstring(_sanitize_xml(resp.text))
        except ET.ParseError:
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("atom:entry", ns)[:limit]:
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            summary_el = entry.find("atom:summary", ns)
            updated_el = entry.find("atom:updated", ns)

            link = link_el.get("href", "") if link_el is not None else ""
            cam_id_m = re.search(r"/(\d+)\.html", link)

            results.append({
                "title": title_el.text if title_el is not None else "",
                "summary": summary_el.text if summary_el is not None else "",
                "url": link,
                "cam_id": int(cam_id_m.group(1)) if cam_id_m else None,
                "updated": updated_el.text if updated_el is not None else "",
            })
        return results

    # -----------------------------------------------------------------------
    # Image download
    # -----------------------------------------------------------------------

    def download_current_image(
        self,
        cam: "Webcam",
        size: str = "current",
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Download the current snapshot for a webcam.

        Parameters
        ----------
        cam : Webcam
        size : str
            "40x30"  — small thumbnail
            "80x60"  — medium thumbnail
            "120x90" — large thumbnail
            "current" — full-res current image (~webcam-{id:06d}.jpg)
        output_path : str or None
            If provided, save to this file path.

        Returns
        -------
        bytes — JPEG image data
        """
        size_map = {
            "40x30": cam.thumbnail_40x30,
            "80x60": cam.thumbnail_80x60,
            "120x90": cam.thumbnail_120x90,
            "current": cam.current_image_url,
        }
        if size not in size_map:
            raise ValueError(f"size must be one of: {list(size_map)}")

        url = size_map[size]
        resp = self._get(url, headers={"Referer": cam.page_url})

        data = resp.content
        if output_path:
            with open(output_path, "wb") as f:
                f.write(data)
        return data

    def download_archive_image(
        self,
        cam: "Webcam",
        month: int,
        day: int,
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Download a daily archive snapshot for a specific date.

        Parameters
        ----------
        cam : Webcam
        month, day : int  e.g. month=3, day=15 for March 15

        Returns
        -------
        bytes — JPEG image data
        """
        url = cam.archive_daily_url(month, day)
        resp = self._get(url, headers={"Referer": cam.page_url})
        data = resp.content
        if output_path:
            with open(output_path, "wb") as f:
                f.write(data)
        return data

    def download_hourly_image(
        self,
        cam: "Webcam",
        city_slug: str,
        day_offset: int,
        hour: int,
        width: int = 640,
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Download a specific hourly timelapse image.

        Parameters
        ----------
        cam : Webcam
        city_slug : str   lowercase hyphenated city name (from page JS: wcgplayerImageCityname)
        day_offset : int  0=today, 1=yesterday, etc.
        hour : int        0-23 (not all hours available; see page metadata for available hours)
        width : int       image width (640 default)

        Returns
        -------
        bytes — JPEG image data
        """
        url = cam.hourly_image_url(city_slug, day_offset, hour, width)
        resp = self._get(url, headers={"Referer": cam.page_url})
        data = resp.content
        if output_path:
            with open(output_path, "wb") as f:
                f.write(data)
        return data

    # -----------------------------------------------------------------------
    # Theme-based browsing via bbox
    # -----------------------------------------------------------------------

    def get_webcams_by_theme(
        self,
        theme_id: int,
        latmin: float = 35.0,
        latmax: float = 72.0,
        lonmin: float = -25.0,
        lonmax: float = 50.0,
    ) -> list[Webcam]:
        """
        Retrieve webcams filtered by theme using the map XML API.

        Parameters
        ----------
        theme_id : int   See THEMES constant (e.g. 19=Mountains, 7=Beaches, 23=Weather)
        latmin/latmax/lonmin/lonmax : float   Bounding box (defaults to all of Europe)

        Returns
        -------
        list of Webcam
        """
        return self.get_webcams_by_bbox(
            latmin=latmin, latmax=latmax, lonmin=lonmin, lonmax=lonmax,
            theme_id=theme_id
        )

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    @staticmethod
    def list_themes() -> dict[int, str]:
        """Return all known theme IDs and names."""
        return dict(THEMES)

    @staticmethod
    def build_image_url(cam_id: int, size: str = "current") -> str:
        """
        Build an image URL for a known webcam ID without needing a Webcam object.

        size: "40x30", "80x60", "120x90", or "current"
        """
        if size == "current":
            return f"{IMAGE_HOST}/webcamimages/webcam-{cam_id:06d}.jpg"
        else:
            return f"{IMAGE_HOST}/webcamimages/{size}/{cam_id}-pub.jpg"

    @staticmethod
    def build_archive_url(cam_id: int, month: int, day: int) -> str:
        """Build a daily archive image URL for a known cam_id."""
        return f"{IMAGE_HOST}/oneyear/{month:02d}-{day:02d}/{cam_id}.jpg"

    def close(self):
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def get_webcams_near(
    lat: float,
    lon: float,
    radius_deg: float = 0.5,
    theme_id: int = 0,
    delay: float = 0.5,
) -> list[Webcam]:
    """
    Quick helper: get webcams within a radius (in degrees) of a lat/lon point.

    Example
    -------
    >>> cams = get_webcams_near(47.377, 8.539, radius_deg=0.3)  # Zurich area
    """
    with WebcamGaloreClient(delay=delay) as client:
        return client.get_webcams_by_bbox(
            latmin=lat - radius_deg,
            latmax=lat + radius_deg,
            lonmin=lon - radius_deg,
            lonmax=lon + radius_deg,
            theme_id=theme_id,
        )


def get_ski_resort_webcams(
    latmin: float = 44.0,
    latmax: float = 48.5,
    lonmin: float = 6.0,
    lonmax: float = 16.0,
    delay: float = 0.5,
) -> list[Webcam]:
    """
    Retrieve ski resort webcams (theme 29) in the Alps region.
    Default bbox covers the main Alpine arc.
    """
    with WebcamGaloreClient(delay=delay) as client:
        return client.get_webcams_by_bbox(
            latmin=latmin, latmax=latmax, lonmin=lonmin, lonmax=lonmax,
            theme_id=29,  # Ski-Resorts
        )


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=== WebcamGalore Client Demo ===\n")

    client = WebcamGaloreClient(delay=0.8)

    # 1. List countries
    print("1. Top countries by webcam count:")
    countries = client.get_countries()
    top = sorted(countries, key=lambda x: x["count"], reverse=True)[:10]
    for c in top:
        print(f"   {c['name']:<30} {c['count']:>5} cams")

    print()

    # 2. Popular webcams
    print("2. Currently popular webcams (top 5):")
    popular = client.get_popular_webcams()[:5]
    for p in popular:
        print(f"   #{p['rank']} {p['title']}: {p['summary']}")

    print()

    # 3. Webcams near Innsbruck (Alpine area)
    print("3. Webcams near Innsbruck, Austria (bbox):")
    innsbruck_cams = client.get_webcams_by_bbox(
        latmin=47.1, latmax=47.4, lonmin=11.2, lonmax=11.6
    )
    for cam in innsbruck_cams[:5]:
        print(f"   [{cam.cam_id}] {cam.city} - {cam.title}")
        print(f"        Current image: {cam.current_image_url}")

    print()

    # 4. Search
    print("4. Search results for 'Innsbruck':")
    results = client.search("Innsbruck")
    for r in results[:3]:
        print(f"   [{r.cam_id}] {r.city}, {r.country}")

    print()

    # 5. New webcams
    print("5. Recently added webcams (last 3):")
    new_cams = client.get_new_webcams(limit=3)
    for cam in new_cams:
        print(f"   [{cam['cam_id']}] {cam['title']}: {cam['summary']}")

    print()

    # 6. Available themes
    print("6. Available themes:")
    for tid, tname in sorted(THEMES.items()):
        print(f"   tid={tid:2d}: {tname}")

    print()

    # 7. Build image URLs without fetching
    print("7. Image URL examples for webcam ID 2907 (Altenmarkt, Bavaria):")
    dummy = Webcam(cam_id=2907, title="Auberg-CAM", city="Altenmarkt-a-d-Alz", country="Germany")
    print(f"   Thumbnail 120x90: {dummy.thumbnail_120x90}")
    print(f"   Current full-res: {dummy.current_image_url}")
    print(f"   Today  12:00 UTC: {dummy.hourly_image_url('altenmarkt-a-d-alz', 0, 12)}")
    print(f"   Archive Mar 26:   {dummy.archive_daily_url(3, 26)}")

    client.close()
