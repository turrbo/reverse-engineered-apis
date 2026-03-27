"""
Opentopia Public Camera Directory Client
=========================================
Reverse-engineered client for https://www.opentopia.com/

Opentopia is a public webcam directory with ~1500+ cameras worldwide.
All endpoints are HTML-scraped or use undocumented JSON APIs discovered
through network traffic analysis.

Discovered Endpoints:
  GET /hiddencam.php                          - Camera listing (HTML)
  GET /hiddencam.php?xmode=get_country_tags   - Country/tag metadata (JSON)
  GET /map.php?xmode=getcams                  - Nearest cameras by lat/lng (JSON)
  GET /webcam/{id}                            - Camera detail page (HTML)
  GET /webcam/{id}?viewmode=savedstill        - Last saved snapshot (default)
  GET /webcam/{id}?viewmode=livestill         - Current live still (HTTP only)
  GET /webcam/{id}?viewmode=refreshingstill   - Auto-refreshing still (HTTP only)
  GET /webcam/{id}?viewmode=animated          - Flipbook of 6 recent frames
  GET /webcam/{id}?viewmode=livevideo         - Live MJPEG stream (HTTP only)
  GET /search.php?q={query}&r=1              - Keyword search (HTML)
  GET /community.php                          - Latest comments (HTML)
  WS  ws.opentopia.com/websocket             - Real-time view events (WebSocket)

IMPORTANT: Live stream view modes (livestill, livevideo, refreshingstill) use
HTTP-only upstream camera URLs.  When accessed over HTTPS, Opentopia returns
a redirect comment:
    <!-- redirect to http://www.opentopia.com/webcam/{id}?viewmode=livestill&_redirected=1 -->
Use http:// and append &_redirected=1 to bypass the redirect.

Image URL patterns (images.opentopia.com):
  /cams/{id}/tiny.jpg    - ~62x48 px thumbnail
  /cams/{id}/small.jpg   - ~230x172 px small
  /cams/{id}/medium.jpg  - ~230x172 px medium (standard listing size)
  /cams/{id}/big.jpg     - ~715px wide current snapshot
  /cams/{id}/m-1.jpg     - Most recent historical snapshot
  /cams/{id}/m-2.jpg     - 2nd most recent (~3h apart)
  /cams/{id}/m-3.jpg     - 3rd most recent
  /cams/{id}/m-4.jpg     - 4th most recent
  /cams/{id}/m-5.jpg     - 5th most recent
  /cams/{id}/m-6.jpg     - 6th most recent (oldest)
  /cams/{id}/{frame_id}.jpg  - Numbered animation frames (sequential integers)

Live upstream URL patterns (extracted from viewmode=livestill / livevideo):
  Axis cameras:      http://<host>/jpg/image.jpg          (still)
                     http://<host>/mjpg/video.mjpg        (MJPEG)
  Panasonic cameras: http://<host>/snapshotJPEG?Resolution=640x480&Quality=Clarity  (still)
                     (no MJPEG stream available)
  Various cameras:   http://<host>:<port>/jpg/image.jpg   (still)
                     http://<host>:<port>/mjpg/video.mjpg (MJPEG)

Author: Reverse-engineered via browser/network analysis, March 2026
"""

import re
import json
import time
import logging
from typing import Optional, Iterator, Union
from dataclasses import dataclass, field
from urllib.parse import urlencode, quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """Represents a single Opentopia camera."""
    id: int
    title: str
    country: str = ""
    region: str = ""          # State/province
    city: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    brand: str = ""
    views: int = 0
    rating: float = 0.0
    num_votes: int = 0
    num_comments: int = 0
    live_url: str = ""        # Direct mjpeg/rtsp source URL (when available)
    # Image URLs (populated lazily or via get_camera())
    url_tiny: str = ""
    url_small: str = ""
    url_medium: str = ""
    url_big: str = ""
    # Historical snapshots
    snapshots: list = field(default_factory=list)  # [url_m1, url_m2, ...]
    # Animation frames (numbered)
    animation_frames: list = field(default_factory=list)

    def __post_init__(self):
        base = f"https://images.opentopia.com/cams/{self.id}"
        if not self.url_tiny:
            self.url_tiny = f"{base}/tiny.jpg"
        if not self.url_small:
            self.url_small = f"{base}/small.jpg"
        if not self.url_medium:
            self.url_medium = f"{base}/medium.jpg"
        if not self.url_big:
            self.url_big = f"{base}/big.jpg"
        if not self.snapshots:
            self.snapshots = [f"{base}/m-{i}.jpg" for i in range(1, 7)]


@dataclass
class Comment:
    """A user comment on a camera."""
    author: str
    date: str
    text: str


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class OpentopiaClient:
    """
    Python client for the Opentopia public camera directory.

    Usage::

        client = OpentopiaClient()

        # List all cameras (newest first)
        for cam in client.list_cameras():
            print(cam.id, cam.title, cam.country)

        # Get a specific camera
        cam = client.get_camera(12343)
        print(cam.title, cam.latitude, cam.longitude)

        # Search by keyword
        results = client.search("japan beach")

        # Browse by country
        cams = client.list_cameras(country="Japan")

        # Map / geographic search
        nearby = client.cameras_near(35.68, 139.69, zoom=8)  # Tokyo

        # Get image snapshots
        snapshot_url = client.get_snapshot_url(cam.id)        # big.jpg
        thumb_url    = client.get_thumbnail_url(cam.id)       # tiny.jpg
    """

    BASE_URL = "https://www.opentopia.com"
    IMAGES_URL = "https://images.opentopia.com/cams"

    # Valid sort orders for list_cameras()
    SORT_NEWEST       = "newest"
    SORT_RANDOM       = "random"
    SORT_MOST_VIEWED  = "oftenviewed"
    SORT_HIGHEST_RATED = "highlyrated"

    # Valid display modes
    MODE_STANDARD  = "standard"   # Last snapshot
    MODE_ANIMATED  = "animated"   # Animation of recent snapshots

    # Known camera categories (from get_country_tags API)
    CATEGORIES = {
        "airport": 1,
        "animals": 2,
        "animals aquarium": 17,
        "aquarium": 15,
        "beach": 3,
        "bridge": 13,
        "college": 9,
        "construction": 8,
        "hotel": 7,
        "port": 11,
        "river": 12,
        "ski": 4,
        "square": 5,
        "street": 14,
        "studio": 18,
        "test": 16,
        "traffic": 10,
        "university": 6,
    }

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        request_delay: float = 0.5,
        timeout: int = 15,
    ):
        """
        Args:
            session:       Optional pre-configured requests.Session.
            request_delay: Seconds to wait between requests (be polite).
            timeout:       HTTP request timeout in seconds.
        """
        self.session = session or requests.Session()
        self.request_delay = request_delay
        self.timeout = timeout
        self._last_request = 0.0

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.opentopia.com/",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """Rate-limited GET request."""
        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Not found: {url}") from e
            raise
        finally:
            self._last_request = time.time()
        return resp

    def _soup(self, url: str, params: Optional[dict] = None) -> BeautifulSoup:
        resp = self._get(url, params=params)
        return BeautifulSoup(resp.text, "html.parser")

    def _json(self, url: str, params: Optional[dict] = None) -> Union[dict, list]:
        resp = self._get(url, params=params)
        return resp.json()

    @staticmethod
    def _parse_int(text: str, default: int = 0) -> int:
        m = re.search(r"[\d,]+", text.replace(",", ""))
        return int(m.group(0)) if m else default

    @staticmethod
    def _parse_float(text: str, default: float = 0.0) -> float:
        m = re.search(r"[\d.]+", text)
        return float(m.group(0)) if m else default

    # ------------------------------------------------------------------
    # Listing cameras  /hiddencam.php
    # ------------------------------------------------------------------

    def list_cameras(
        self,
        country: str = "*",
        sort: str = SORT_NEWEST,
        mode: str = MODE_STANDARD,
        page: int = 1,
    ) -> list["Camera"]:
        """
        Fetch one page of cameras from the main listing.

        Args:
            country: Country name (e.g. "Japan"), state variant
                     (e.g. "United States|California"), or "*" for all.
            sort:    One of SORT_NEWEST, SORT_RANDOM, SORT_MOST_VIEWED,
                     SORT_HIGHEST_RATED.
            mode:    MODE_STANDARD or MODE_ANIMATED.
            page:    Page number (1-based).  ~24 cameras per page.

        Returns:
            List of Camera objects with basic metadata.
            Full metadata requires calling get_camera() on each.
        """
        params = {
            "showmode": mode,
            "country": country,
            "seewhat": sort,
            "p": page,
        }
        soup = self._soup(f"{self.BASE_URL}/hiddencam.php", params=params)
        return self._parse_listing(soup)

    def iter_all_cameras(
        self,
        country: str = "*",
        sort: str = SORT_NEWEST,
        max_pages: int = 200,
        page_delay: float = 1.0,
    ) -> Iterator["Camera"]:
        """
        Iterator that pages through all cameras.

        Args:
            country:   Filter by country (default: all).
            sort:      Sort order.
            max_pages: Safety cap to avoid infinite loops.
            page_delay: Extra delay between pages (seconds).

        Yields:
            Camera objects from each page until no more cameras are found.

        Example::

            for cam in client.iter_all_cameras(country="Japan"):
                print(cam.id, cam.title)
        """
        page = 1
        seen_ids: set = set()

        while page <= max_pages:
            cameras = self.list_cameras(country=country, sort=sort, page=page)
            if not cameras:
                logger.info("No cameras on page %d, stopping.", page)
                break

            new_cameras = [c for c in cameras if c.id not in seen_ids]
            if not new_cameras:
                logger.info("All cameras on page %d already seen, stopping.", page)
                break

            for cam in new_cameras:
                seen_ids.add(cam.id)
                yield cam

            page += 1
            if page_delay > 0:
                time.sleep(page_delay)

    def _parse_listing(self, soup: BeautifulSoup) -> list["Camera"]:
        """Parse a camera listing page into Camera objects.

        Opentopia's listing pages use two cell types:
          - div.cell_medium  (used in list views on hiddencam.php)
          - div.cell_small   (used in sidebar / front page)
        Each cell contains an <a href="/webcam/{id}"> link and location <span> tags.
        """
        cameras = []
        seen_ids: set = set()

        # Select all camera cells from the listing
        # The real HTML uses div.cell_medium and div.cell_small
        items = soup.select("div.cell_medium, div.cell_small")

        # Fallback: legacy camgrid structure
        if not items:
            items = soup.select("ul.camgrid li")

        for item in items:
            a_tag = item.find("a", href=re.compile(r"/webcam/\d+"))
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            m = re.search(r"/webcam/(\d+)", href)
            if not m:
                continue
            cam_id = int(m.group(1))
            if cam_id in seen_ids:
                continue
            seen_ids.add(cam_id)

            # Title from <h3> or img alt
            h3 = item.find("h3")
            title = h3.get_text(strip=True) if (h3 and h3.get_text(strip=True)) else ""
            if not title:
                img = a_tag.find("img")
                title = img.get("alt", f"Camera {cam_id}") if img else f"Camera {cam_id}"

            # Location: <span>Country</span> | <span>Region</span> | <span>City</span>
            spans = item.select("div span")
            country = spans[0].get_text(strip=True) if len(spans) > 0 else ""
            region  = spans[1].get_text(strip=True) if len(spans) > 1 else ""
            city    = spans[2].get_text(strip=True) if len(spans) > 2 else ""

            cam = Camera(
                id=cam_id,
                title=title,
                country=country,
                region=region,
                city=city,
            )
            cameras.append(cam)

        return cameras

    # ------------------------------------------------------------------
    # Camera detail  /webcam/{id}
    # ------------------------------------------------------------------

    def get_camera(self, camera_id: int) -> "Camera":
        """
        Fetch full metadata for a single camera.

        Returns a Camera with all available fields populated:
        title, country, region, city, coordinates, brand, views,
        rating, num_votes, num_comments, live_url, snapshots, etc.

        Args:
            camera_id: Numeric camera ID (e.g. 12343).

        Raises:
            ValueError: If the camera page returns 404.
        """
        url = f"{self.BASE_URL}/webcam/{camera_id}"
        resp = self._get(url)
        content = resp.text
        soup = BeautifulSoup(content, "html.parser")

        cam = Camera(id=camera_id, title=f"Camera {camera_id}")

        # --- Meta tags (Open Graph + schema.org) ---
        meta_map = {}
        for m in soup.find_all("meta"):
            key = m.get("property") or m.get("itemprop") or m.get("name", "")
            val = m.get("content", "")
            if key and val:
                meta_map[key] = val

        cam.title   = meta_map.get("og:title", cam.title).split(" - a webcam")[0]
        cam.country = meta_map.get("og:country-name", "")
        cam.region  = meta_map.get("og:region", "")
        cam.city    = meta_map.get("og:locality", "")
        try:
            cam.latitude  = float(meta_map.get("og:latitude", 0))
            cam.longitude = float(meta_map.get("og:longitude", 0))
        except ValueError:
            pass

        # --- Inline JS variables ---
        js_match = re.search(
            r'var camera_id\s*=\s*(\d+).*?var cam_title\s*=\s*"([^"]*)"',
            content,
            re.DOTALL,
        )
        if js_match:
            cam.id    = int(js_match.group(1))
            cam.title = js_match.group(2)

        # --- Camera info block ---
        caminfo = soup.find("div", {"id": "caminfo"})
        if caminfo:
            text = caminfo.get_text("\n")
            brand_m = re.search(r"Brand:\s*(.+)", text)
            if brand_m:
                cam.brand = brand_m.group(1).strip()

        # --- View count ---
        views_span = soup.find("span", string=re.compile(r"\d+"))
        # More reliable: look for the views label
        views_label = soup.find("label", string=re.compile(r"views", re.I))
        if views_label:
            prev = views_label.find_previous("span")
            if prev:
                cam.views = self._parse_int(prev.get_text())
        # Try alternative pattern in content
        views_m = re.search(r'<span[^>]*>([\d,]+)</span>\s*views', content)
        if views_m and cam.views == 0:
            cam.views = self._parse_int(views_m.group(1))

        # --- Rating ---
        rating_m = re.search(
            r"Currently\s+([\d.]+)/5\s+Stars", content
        )
        if rating_m:
            cam.rating = float(rating_m.group(1))

        vote_m = re.search(r"([\d.]+)</span>\s*from\s*<span>(\d+)</span>\s*votes", content)
        if vote_m:
            cam.rating    = float(vote_m.group(1))
            cam.num_votes = int(vote_m.group(2))

        # --- Comment count ---
        comment_h2 = soup.find("h2", string=re.compile(r"Comments\s*\(\d+\)", re.I))
        if comment_h2:
            cm = re.search(r"\((\d+)\)", comment_h2.get_text())
            if cm:
                cam.num_comments = int(cm.group(1))

        # --- Live video URL ---
        # The default (savedstill) page only shows a static CDN image.
        # Live URLs are only available in livestill/livevideo view modes which
        # require HTTP + _redirected=1 (see get_camera_with_live_url / get_live_still_url).
        # We intentionally leave cam.live_url empty here for performance;
        # call get_camera_with_live_url(id) to populate it.
        big_div = soup.find("div", {"class": "big"})
        if big_div:
            live_img = big_div.find("img")
            if live_img:
                src = live_img.get("src", "")
                if (src and "opentopia.com" not in src and src != "/images/new_icon.gif"
                        and src.startswith("http")):
                    cam.live_url = src

        # --- Historical snapshot URLs (m-1 through m-6) ---
        snapshots_div = soup.find("div", {"id": "snapshots"})
        if snapshots_div:
            snap_imgs = snapshots_div.find_all("img")
            cam.snapshots = [
                img.get("src") for img in snap_imgs
                if img.get("src") and "opentopia.com/cams" in img.get("src", "")
            ]

        # --- Animation frames (numbered JPEGs from flipbook) ---
        flipbook_div = soup.find("div", {"id": "flipbook"})
        if flipbook_div:
            frame_imgs = flipbook_div.find_all("img")
            cam.animation_frames = [
                img.get("src") for img in frame_imgs
                if img.get("src") and "opentopia.com/cams" in img.get("src", "")
            ]

        # Ensure image URLs are set
        base = f"{self.IMAGES_URL}/{cam.id}"
        cam.url_tiny   = f"{base}/tiny.jpg"
        cam.url_small  = f"{base}/small.jpg"
        cam.url_medium = f"{base}/medium.jpg"
        cam.url_big    = f"{base}/big.jpg"

        return cam

    def get_camera_with_live_url(self, camera_id: int) -> "Camera":
        """
        Like get_camera() but also fetches the live MJPEG/video URL
        by loading viewmode=livevideo.

        NOTE: Live stream pages are HTTP-only on Opentopia.  The HTTPS version
        returns a redirect comment pointing to:
            http://www.opentopia.com/webcam/{id}?viewmode=livevideo&_redirected=1
        This method follows that pattern automatically.
        """
        cam = self.get_camera(camera_id)
        if cam.live_url:
            return cam

        # Live stream pages require HTTP + _redirected=1 parameter
        http_url = f"http://www.opentopia.com/webcam/{camera_id}"
        resp = self._get(http_url, params={"viewmode": "livevideo", "_redirected": "1"})
        content = resp.text

        # MJPEG stream is in: <div style="z-index:100;width:715px;background:#fff">
        #   <img src="http://host/mjpg/video.mjpg" ...>
        mjpeg_m = re.search(
            r'z-index:100;width:715px[^>]*><img\s+src="([^"]+)"',
            content
        )
        if mjpeg_m:
            src = mjpeg_m.group(1)
            if src and "opentopia.com" not in src and src != "/images/new_icon.gif":
                cam.live_url = src
                return cam

        # Also try BeautifulSoup fallback
        soup = BeautifulSoup(content, "html.parser")
        big_div = soup.find("div", {"class": "big"})
        if big_div:
            live_img = big_div.find("img")
            if live_img:
                src = live_img.get("src", "")
                if src and "opentopia.com" not in src and src != "/images/new_icon.gif":
                    cam.live_url = src
        return cam

    def get_live_still_url(self, camera_id: int) -> str:
        """
        Return the direct upstream still-image URL for the camera.

        This is the URL that Opentopia embeds in the ``livestill`` view mode.

        Examples:
          - Axis camera:      ``http://<host>/jpg/image.jpg``
          - Panasonic camera: ``http://<host>/snapshotJPEG?Resolution=640x480&Quality=Clarity``

        Returns an empty string if not available.

        NOTE: Uses HTTP with ``_redirected=1`` to bypass Opentopia's HTTPS→HTTP redirect.
        """
        http_url = f"http://www.opentopia.com/webcam/{camera_id}"
        resp = self._get(http_url, params={"viewmode": "livestill", "_redirected": "1"})
        content = resp.text

        # Still image: <img src="..." id="stillimage" ...>
        m = re.search(r'<img\s+src="([^"]+)"\s+id="stillimage"', content)
        if m:
            src = m.group(1)
            if src and "opentopia.com" not in src:
                return src
        return ""

    def get_comments(self, camera_id: int) -> list["Comment"]:
        """
        Fetch all comments for a camera.

        Args:
            camera_id: Numeric camera ID.

        Returns:
            List of Comment objects (author, date, text).
        """
        url = f"{self.BASE_URL}/webcam/{camera_id}"
        soup = self._soup(url)
        comments = []
        for div in soup.select("div.comment"):
            author = div.select_one("span.name")
            date   = div.select_one("span.date")
            text_div = div.select_one("div.content")
            comments.append(Comment(
                author=author.get_text(strip=True) if author else "",
                date=date.get_text(strip=True) if date else "",
                text=text_div.get_text(" ", strip=True) if text_div else "",
            ))
        return comments

    # ------------------------------------------------------------------
    # Image URL helpers
    # ------------------------------------------------------------------

    def get_thumbnail_url(self, camera_id: int) -> str:
        """Return the tiny thumbnail URL (~62x48 px)."""
        return f"{self.IMAGES_URL}/{camera_id}/tiny.jpg"

    def get_small_url(self, camera_id: int) -> str:
        """Return the small image URL (~230x172 px)."""
        return f"{self.IMAGES_URL}/{camera_id}/small.jpg"

    def get_medium_url(self, camera_id: int) -> str:
        """Return the medium image URL (standard listing size)."""
        return f"{self.IMAGES_URL}/{camera_id}/medium.jpg"

    def get_snapshot_url(self, camera_id: int) -> str:
        """Return the current full-size snapshot URL (~715px wide)."""
        return f"{self.IMAGES_URL}/{camera_id}/big.jpg"

    def get_historical_snapshots(self, camera_id: int) -> list[str]:
        """
        Return URLs of up to 6 historical snapshots (m-1 through m-6).
        m-1 is most recent, m-6 is oldest (roughly 3 hours apart).
        """
        return [f"{self.IMAGES_URL}/{camera_id}/m-{i}.jpg" for i in range(1, 7)]

    def download_snapshot(
        self,
        camera_id: int,
        size: str = "big",
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Download a camera snapshot image.

        Args:
            camera_id:   Camera ID.
            size:        One of "tiny", "small", "medium", "big".
            output_path: If provided, save to this file path.

        Returns:
            Raw image bytes.
        """
        url = f"{self.IMAGES_URL}/{camera_id}/{size}.jpg"
        resp = self._get(url)
        data = resp.content
        if output_path:
            with open(output_path, "wb") as f:
                f.write(data)
        return data

    # ------------------------------------------------------------------
    # Search  /search.php
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        page: int = 1,
    ) -> list["Camera"]:
        """
        Search cameras by keyword (title, description, location).

        Args:
            query: Search term (e.g. "tokyo", "beach", "airport").
            page:  Page number (1-based).

        Returns:
            List of Camera objects matching the query.
        """
        params = {"q": query, "r": 1, "p": page}
        soup = self._soup(f"{self.BASE_URL}/search.php", params=params)
        return self._parse_listing(soup)

    def search_all(
        self,
        query: str,
        max_pages: int = 50,
    ) -> list["Camera"]:
        """
        Search cameras and collect ALL pages of results.

        Args:
            query:     Search term.
            max_pages: Safety cap.

        Returns:
            All matching Camera objects.
        """
        all_cameras = []
        seen_ids: set = set()
        page = 1

        while page <= max_pages:
            results = self.search(query, page=page)
            if not results:
                break
            new = [c for c in results if c.id not in seen_ids]
            if not new:
                break
            for c in new:
                seen_ids.add(c.id)
            all_cameras.extend(new)
            page += 1

        return all_cameras

    # ------------------------------------------------------------------
    # Country / geographic browsing
    # ------------------------------------------------------------------

    def list_cameras_by_country(
        self,
        country: str,
        sort: str = SORT_NEWEST,
        page: int = 1,
    ) -> list["Camera"]:
        """
        List cameras from a specific country.

        For US states use: "United States|California"
        For other countries: "Japan", "Germany", etc.

        Args:
            country: Country name from get_countries().
            sort:    Sort order.
            page:    Page number.

        Returns:
            List of Camera objects.
        """
        return self.list_cameras(country=country, sort=sort, page=page)

    def list_cameras_by_state(
        self,
        state: str,
        country: str = "United States",
    ) -> list["Camera"]:
        """
        List cameras in a US state (or other country subdivision).

        Args:
            state:   State name (e.g. "California", "New York").
            country: Parent country (default: "United States").

        Returns:
            List of Camera objects.
        """
        return self.list_cameras(country=f"{country}|{state}")

    def get_countries(self) -> dict:
        """
        Return all countries with camera counts and metadata.

        Returns a dict keyed by ISO 3166-1 alpha-2 country code::

            {
              "US": {
                "name": "United States",
                "count": 283,
                "tags": [],
                "states": {
                  "US.CA": {"name": "California", "count": 35, "tags": []},
                  ...
                }
              },
              "JP": {"name": "Japan", "count": 264, ...},
              ...
            }

        This calls the live JSON endpoint /hiddencam.php?xmode=get_country_tags.
        """
        resp = self._get(
            f"{self.BASE_URL}/hiddencam.php",
            params={"xmode": "get_country_tags"},
        )
        data = resp.json()
        return data.get("countries", {}).get("code", {})

    def get_categories(self) -> dict:
        """
        Return available camera categories (tags).

        Returns::

            {
              "1": "airport",
              "2": "animals",
              "3": "beach",
              "4": "ski",
              ...
            }
        """
        resp = self._get(
            f"{self.BASE_URL}/hiddencam.php",
            params={"xmode": "get_country_tags"},
        )
        data = resp.json()
        return data.get("tags", {})

    def get_camera_count_by_country(self) -> dict:
        """
        Return a {country_name: count} dict for all countries with cameras.

        Example::

            {"Japan": 264, "United States": 283, "Germany": 137, ...}
        """
        countries = self.get_countries()
        return {
            info["name"]: info["count"]
            for info in countries.values()
            if info.get("count", 0) > 0
        }

    # ------------------------------------------------------------------
    # Map / geographic search  /map.php?xmode=getcams
    # ------------------------------------------------------------------

    def cameras_near(
        self,
        latitude: float,
        longitude: float,
        zoom: int = 8,
    ) -> list["Camera"]:
        """
        Find cameras nearest to a geographic coordinate.

        The API returns approximately 40 cameras closest to the given
        latitude/longitude. The zoom parameter is passed to the server
        but in practice does not significantly change the radius.

        Args:
            latitude:  Decimal degrees latitude (e.g. 35.68 for Tokyo).
            longitude: Decimal degrees longitude (e.g. 139.69 for Tokyo).
            zoom:      Map zoom level hint (1-20, default 8).

        Returns:
            List of Camera objects with id, title, latitude, longitude.

        Example::

            # Cameras near Paris
            cams = client.cameras_near(48.85, 2.35)

            # Cameras near Tokyo
            cams = client.cameras_near(35.68, 139.69)
        """
        resp = self._get(
            f"{self.BASE_URL}/map.php",
            params={
                "xmode": "getcams",
                "latitude": latitude,
                "longitude": longitude,
                "zoom": zoom,
            },
        )
        data = resp.json()
        cameras = []
        for item in data:
            try:
                cam = Camera(
                    id=int(item["id"]),
                    title=item.get("title", f"Camera {item['id']}"),
                    latitude=float(item.get("latitude", 0)),
                    longitude=float(item.get("longitude", 0)),
                )
                cameras.append(cam)
            except (KeyError, ValueError):
                continue
        return cameras

    def get_all_camera_coords(self) -> list[dict]:
        """
        Attempt to retrieve coordinates of all cameras by tiling the globe.

        Queries the map API on a grid of lat/lng points and deduplicates
        by camera ID. Returns partial coverage - for full coverage use
        iter_all_cameras() and call get_camera() on each.

        Returns:
            List of dicts: [{"id", "title", "latitude", "longitude"}, ...]
        """
        # Sample major camera-dense regions at a broader zoom
        grid_points = [
            # Japan (dense)
            (35.68, 139.69), (34.69, 135.49), (33.59, 130.36),
            (43.06, 141.35), (35.0, 136.0),
            # Europe (dense)
            (48.2, 16.37),   # Vienna (dense)
            (48.87, 2.35),   # Paris
            (52.5, 13.4),    # Berlin
            (41.9, 12.5),    # Rome
            (50.08, 14.43),  # Prague
            (59.91, 10.75),  # Oslo
            (47.37, 8.54),   # Zurich
            (48.13, 11.58),  # Munich
            (37.98, 23.73),  # Athens
            (44.83, 20.46),  # Belgrade
            (43.84, 18.36),  # Sarajevo
            # USA (dense)
            (40.71, -74.0),  # New York
            (34.05, -118.24),# Los Angeles
            (41.88, -87.63), # Chicago
            (37.77, -122.42),# San Francisco
            (47.61, -122.33),# Seattle
            (44.97, -93.27), # Minneapolis
            (41.66, -83.56), # Toledo (midwest)
            (30.33, -81.66), # Jacksonville
            (29.76, -95.37), # Houston
            (33.45, -112.07),# Phoenix
            # Korea / Taiwan
            (37.57, 126.98), # Seoul
            (25.04, 121.56), # Taipei
            # Other
            (49.2, 16.61),   # Brno
            (45.46, 9.19),   # Milan
            (55.75, 37.62),  # Moscow
            (50.45, 30.52),  # Kyiv
            (47.0, 28.86),   # Chisinau (Romania/Moldova)
            (44.43, 26.1),   # Bucharest
        ]

        seen_ids: set = set()
        results = []

        for lat, lng in grid_points:
            try:
                cams = self.cameras_near(lat, lng, zoom=8)
                for cam in cams:
                    if cam.id not in seen_ids:
                        seen_ids.add(cam.id)
                        results.append({
                            "id": cam.id,
                            "title": cam.title,
                            "latitude": cam.latitude,
                            "longitude": cam.longitude,
                        })
            except Exception as e:
                logger.warning("Error fetching cams near %s,%s: %s", lat, lng, e)

        return results

    # ------------------------------------------------------------------
    # Random camera
    # ------------------------------------------------------------------

    def get_random_cameras(
        self,
        country: str = "*",
        count: int = 24,
    ) -> list["Camera"]:
        """
        Return a random selection of cameras.

        Args:
            country: Filter by country (default: all).
            count:   Approximate number of cameras (max ~24 per page).

        Returns:
            List of randomly selected Camera objects.
        """
        return self.list_cameras(
            country=country,
            sort=self.SORT_RANDOM,
        )[:count]

    def get_random_camera(self, country: str = "*") -> Optional["Camera"]:
        """
        Return a single random camera.

        Args:
            country: Filter by country (default: all).

        Returns:
            A single Camera, or None if none found.
        """
        cameras = self.get_random_cameras(country=country, count=1)
        return cameras[0] if cameras else None

    # ------------------------------------------------------------------
    # Community / comments feed  /community.php
    # ------------------------------------------------------------------

    def get_recent_comments(self, page: int = 1) -> list[dict]:
        """
        Get recent comments from the community feed.

        Returns a list of dicts::

            [
              {
                "camera_id": 18038,
                "camera_title": "The Sauerland Pyramids",
                "author": "N Q",
                "date": "Mar 27, 2026 17:05",
                "comment": "I don't remember viewing this one before..."
              },
              ...
            ]
        """
        params = {"p": page} if page > 1 else None
        soup = self._soup(f"{self.BASE_URL}/community.php", params=params)
        results = []

        for item in soup.select("div[style*='overflow:hidden'][style*='padding']"):
            cam_link = item.find("a", href=lambda h: h and "/webcam/" in str(h))
            if not cam_link:
                continue
            href = cam_link.get("href", "")
            m = re.search(r"/webcam/(\d+)", href)
            if not m:
                continue

            cam_id = int(m.group(1))
            cam_title_el = item.find("a", href=href)
            cam_title = cam_title_el.get_text(strip=True) if cam_title_el else ""

            author_el = item.find("div", style=lambda s: s and "font-size" in str(s) and "888" in str(s))
            author_parts = author_el.get_text(" ", strip=True) if author_el else ""

            comment_el = item.find("div", style=lambda s: s and "#333" in str(s))
            comment_text = comment_el.get_text(" ", strip=True) if comment_el else ""

            results.append({
                "camera_id": cam_id,
                "camera_title": cam_title,
                "author_info": author_parts,
                "comment": comment_text,
            })

        return results

    def search_comments(self, query: str) -> list[dict]:
        """
        Search community comments by keyword.

        Args:
            query: Search term.

        Returns:
            List of comment result dicts (same format as get_recent_comments).
        """
        soup = self._soup(
            f"{self.BASE_URL}/community.php",
            params={"q": query},
        )
        return self._parse_community_page(soup)

    def _parse_community_page(self, soup: BeautifulSoup) -> list[dict]:
        """Parse community.php page into comment records."""
        results = []
        for item in soup.select("div.boxcontent > div[style]"):
            cam_link = item.find("a", href=lambda h: h and "/webcam/" in str(h))
            if not cam_link:
                continue
            href = cam_link.get("href", "")
            m = re.search(r"/webcam/(\d+)", href)
            if not m:
                continue
            cam_id = int(m.group(1))
            cam_title_el = item.find("a", {"href": href})
            cam_title = cam_title_el.get_text(strip=True) if cam_title_el else ""
            comment_el = item.find("div", {"style": lambda s: s and "color:#333" in str(s)})
            comment_text = comment_el.get_text(" ", strip=True) if comment_el else ""
            results.append({
                "camera_id": cam_id,
                "camera_title": cam_title,
                "comment": comment_text,
            })
        return results

    # ------------------------------------------------------------------
    # High-level convenience methods
    # ------------------------------------------------------------------

    def get_top_cameras(self, count: int = 50, country: str = "*") -> list["Camera"]:
        """
        Return highest-rated cameras.

        Args:
            count:   Maximum number of cameras to return.
            country: Filter by country (default: all).

        Returns:
            List of Camera objects sorted by rating.
        """
        cameras = []
        page = 1
        while len(cameras) < count:
            batch = self.list_cameras(
                country=country,
                sort=self.SORT_HIGHEST_RATED,
                page=page,
            )
            if not batch:
                break
            cameras.extend(batch)
            page += 1
        return cameras[:count]

    def get_newest_cameras(self, count: int = 50, country: str = "*") -> list["Camera"]:
        """
        Return most recently added cameras.

        Args:
            count:   Maximum number of cameras to return.
            country: Filter by country (default: all).

        Returns:
            List of Camera objects, newest first.
        """
        cameras = []
        page = 1
        while len(cameras) < count:
            batch = self.list_cameras(
                country=country,
                sort=self.SORT_NEWEST,
                page=page,
            )
            if not batch:
                break
            cameras.extend(batch)
            page += 1
        return cameras[:count]

    def get_most_viewed_cameras(self, count: int = 50) -> list["Camera"]:
        """Return most viewed cameras globally."""
        cameras = []
        page = 1
        while len(cameras) < count:
            batch = self.list_cameras(sort=self.SORT_MOST_VIEWED, page=page)
            if not batch:
                break
            cameras.extend(batch)
            page += 1
        return cameras[:count]

    def cameras_in_country(self, country: str) -> list["Camera"]:
        """
        Collect ALL cameras in a specific country across all pages.

        Warning: may make many HTTP requests for countries with many cameras.

        Args:
            country: Country name (e.g. "Japan") or state variant.

        Returns:
            All Camera objects in that country.
        """
        return list(self.iter_all_cameras(country=country))

    # ------------------------------------------------------------------
    # Pagination helper
    # ------------------------------------------------------------------

    def count_pages(self, country: str = "*", sort: str = SORT_NEWEST) -> int:
        """
        Determine the total number of pages for a given query.

        Makes a single request to page 1 and reads the pagination links.

        Args:
            country: Country filter (default: all).
            sort:    Sort order.

        Returns:
            Estimated total page count.
        """
        soup = self._soup(
            f"{self.BASE_URL}/hiddencam.php",
            params={"showmode": "standard", "country": country, "seewhat": sort, "p": 1},
        )
        content = str(soup)
        page_nums = set(int(p) for p in re.findall(r"p=(\d+)", content))
        return max(page_nums) if page_nums else 1

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_total_camera_count(self) -> int:
        """
        Return the total number of cameras by summing country counts.

        Uses the /hiddencam.php?xmode=get_country_tags JSON endpoint.
        """
        countries = self.get_countries()
        return sum(info.get("count", 0) for info in countries.values())


# ---------------------------------------------------------------------------
# Convenience functions (module-level)
# ---------------------------------------------------------------------------

_default_client: Optional[OpentopiaClient] = None


def get_client() -> OpentopiaClient:
    """Return the default module-level client (created on first call)."""
    global _default_client
    if _default_client is None:
        _default_client = OpentopiaClient()
    return _default_client


def list_cameras(**kwargs) -> list[Camera]:
    """Module-level shortcut for OpentopiaClient().list_cameras()."""
    return get_client().list_cameras(**kwargs)


def get_camera(camera_id: int) -> Camera:
    """Module-level shortcut for OpentopiaClient().get_camera()."""
    return get_client().get_camera(camera_id)


def search(query: str, **kwargs) -> list[Camera]:
    """Module-level shortcut for OpentopiaClient().search()."""
    return get_client().search(query, **kwargs)


def cameras_near(lat: float, lng: float, zoom: int = 8) -> list[Camera]:
    """Module-level shortcut for OpentopiaClient().cameras_near()."""
    return get_client().cameras_near(lat, lng, zoom)


def get_countries() -> dict:
    """Module-level shortcut for OpentopiaClient().get_countries()."""
    return get_client().get_countries()


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Opentopia Camera Client")
    subparsers = parser.add_subparsers(dest="command")

    # list
    p_list = subparsers.add_parser("list", help="List cameras")
    p_list.add_argument("--country", default="*", help='Country name or "*" for all')
    p_list.add_argument("--sort", default="newest", choices=["newest","random","oftenviewed","highlyrated"])
    p_list.add_argument("--page", type=int, default=1)

    # info
    p_info = subparsers.add_parser("info", help="Get camera details")
    p_info.add_argument("camera_id", type=int)

    # search
    p_search = subparsers.add_parser("search", help="Search cameras")
    p_search.add_argument("query")
    p_search.add_argument("--page", type=int, default=1)

    # map
    p_map = subparsers.add_parser("map", help="Cameras near a location")
    p_map.add_argument("latitude", type=float)
    p_map.add_argument("longitude", type=float)
    p_map.add_argument("--zoom", type=int, default=8)

    # countries
    subparsers.add_parser("countries", help="List countries with camera counts")

    # count
    subparsers.add_parser("count", help="Total camera count")

    args = parser.parse_args()

    client = OpentopiaClient(request_delay=0.5)

    if args.command == "list":
        cameras = client.list_cameras(country=args.country, sort=args.sort, page=args.page)
        for cam in cameras:
            print(f"{cam.id:6d}  {cam.country:20s}  {cam.title[:60]}")
        print(f"\n{len(cameras)} cameras")

    elif args.command == "info":
        cam = client.get_camera(args.camera_id)
        print(f"ID:       {cam.id}")
        print(f"Title:    {cam.title}")
        print(f"Country:  {cam.country}")
        print(f"Region:   {cam.region}")
        print(f"City:     {cam.city}")
        print(f"Lat/Lng:  {cam.latitude}, {cam.longitude}")
        print(f"Brand:    {cam.brand}")
        print(f"Views:    {cam.views}")
        print(f"Rating:   {cam.rating} ({cam.num_votes} votes)")
        print(f"Comments: {cam.num_comments}")
        print(f"Image:    {cam.url_big}")
        print(f"Live URL: {cam.live_url or 'N/A'}")
        print(f"Snapshots: {cam.snapshots[:3]}")

    elif args.command == "search":
        cameras = client.search(args.query, page=args.page)
        for cam in cameras:
            print(f"{cam.id:6d}  {cam.country:20s}  {cam.title[:60]}")
        print(f"\n{len(cameras)} results")

    elif args.command == "map":
        cameras = client.cameras_near(args.latitude, args.longitude, zoom=args.zoom)
        for cam in cameras:
            print(f"{cam.id:6d}  {cam.latitude:8.4f}  {cam.longitude:9.4f}  {cam.title[:50]}")
        print(f"\n{len(cameras)} cameras")

    elif args.command == "countries":
        counts = client.get_camera_count_by_country()
        for country, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"{count:4d}  {country}")
        print(f"\n{len(counts)} countries, {sum(counts.values())} total cameras")

    elif args.command == "count":
        total = client.get_total_camera_count()
        print(f"Total cameras: {total}")

    else:
        parser.print_help()
        sys.exit(1)
