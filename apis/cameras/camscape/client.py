"""
Camscape Webcam Directory API Client
=====================================
Reverse-engineered client for https://www.camscape.com/

Discovered endpoints
--------------------
Custom REST API (camscape/v1 namespace):
  GET  /wp-json/camscape/v1/sayt/{query}    Search-as-you-type autocomplete
  GET  /wp-json/camscape/v1/iss             ISS position (lat/lng)

WordPress oEmbed (publicly accessible):
  GET  /wp-json/oembed/1.0/embed?url={webcam_url}

WordPress AJAX (admin-ajax.php):
  POST /wp/wp-admin/admin-ajax.php  action=camscape_report_webcam
  POST /wp/wp-admin/admin-ajax.php  action=camscape_update_webcam_favourites

HTML page scraping (no auth needed):
  GET  /webcam/{slug}/              Webcam detail (streams, map, taxonomy)
  GET  /showing/{slug}/             Webcams by category
  GET  /location/{slug}/            Webcams by location
  GET  /?s={query}[&paged=N]        Full-text search results
  GET  /new-webcams/                Recently added webcams
  GET  /hot-right-now/              Trending webcams
  GET  /webcam-map/                 Map page

Sitemaps (Yoast XML):
  GET  /sitemap_index.xml
  GET  /webcam-sitemap.xml          First 1000 webcam URLs
  GET  /webcam-sitemap2.xml         Remaining ~325 webcam URLs
  GET  /location-sitemap.xml        All 210 location taxonomy URLs
  GET  /showing-sitemap.xml         All 47 showing/category taxonomy URLs

Stream types (camscapePlayer.streams[].type):
  "popup"  - external URL opened in a popup window; has 'image' preview field
  "iframe" - embedded iframe (YouTube, Feratel, EarthCam, etc.)
  "player" - native HLS/MP4 stream via PlayerJS
  "mjpeg"  - MJPEG still-frame image

Sort orders for listing pages:
  pop      - Popularity (default)
  title    - Alphabetical
  newest   - Most recently added
  temp     - Current local temperature

Notes:
  The WP REST API root (/wp-json/) requires authentication for most
  standard endpoints (posts, pages, taxonomies). Only the custom
  camscape/v1 routes are publicly accessible via the REST API.
  All webcam data is obtainable via HTML scraping.
"""

from __future__ import annotations

import re
import json
import html
import time
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.camscape.com"
WP_JSON = f"{BASE_URL}/wp-json"
AJAX_URL = f"{BASE_URL}/wp/wp-admin/admin-ajax.php"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Complete list of "showing" category slugs discovered from sitemap
SHOWING_CATEGORIES: List[str] = [
    "alpacas", "animals", "sealife", "bats", "beaches", "bears", "bees",
    "big-cats", "big-dogs", "birds", "boats", "bovines", "buildings",
    "business-miscellaneous", "christmas", "cityscapes", "critters",
    "culture", "deer", "domestic-animals", "elephants", "entertainment",
    "giraffes", "goats", "horses", "landscapes", "monsters", "nature",
    "nightlife", "people", "pigs", "planes-airports", "primates",
    "religion", "rivers-seas-lakes", "roads", "scenery",
    "shopping-district", "ski-resorts", "space-astronomy", "squirrels",
    "tortoises", "tourist-attractions", "trains-railways", "transport",
    "urban-spaces", "zebras",
]

SORT_ORDERS = ("pop", "title", "newest", "temp")


class CamscapeClient:
    """
    Client for the Camscape webcam directory.

    Example usage::

        client = CamscapeClient()

        # Search-as-you-type
        results = client.search("beach")

        # List webcams in a category
        cams = client.get_webcams_by_category("beaches")

        # List webcams by location
        cams = client.get_webcams_by_location("london")

        # Full webcam metadata (streams, map coords, taxonomy)
        detail = client.get_webcam_detail("abbey-road-crossing-webcam")

        # ISS position
        iss = client.get_iss_position()

        # All webcam slugs from sitemaps
        all_cams = client.list_all_webcams()
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        user_agent: str = DEFAULT_UA,
        request_delay: float = 0.5,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Referer": BASE_URL + "/",
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
        self.request_delay = request_delay
        self._last_request: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        self._last_request = time.time()
        return resp

    def _post(self, url: str, **kwargs: Any) -> requests.Response:
        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        resp = self.session.post(url, **kwargs)
        resp.raise_for_status()
        self._last_request = time.time()
        return resp

    @staticmethod
    def _extract_js_var(html_text: str, var_name: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON object JS variable assignment from page HTML."""
        pattern = rf"var\s+{re.escape(var_name)}\s*=\s*(\{{.*?\}});"
        match = re.search(pattern, html_text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_webcam_links(html_text: str) -> List[Dict[str, str]]:
        """Parse webcam tile links from a listing page HTML."""
        results: List[Dict[str, str]] = []
        seen: set = set()

        containers = re.findall(
            r'<div class="webcam-container">(.*?)</div><!-- .webcam-footer -->',
            html_text,
            re.DOTALL,
        )
        for block in containers:
            url_m = re.search(
                r'href="(https://www\.camscape\.com/webcam/([^"]+))"', block
            )
            if not url_m or url_m.group(1) in seen:
                continue
            seen.add(url_m.group(1))
            title_m = re.search(
                r'<a href="https://www\.camscape\.com/webcam/[^"]+">([^<]+)</a>', block
            )
            img_m = re.search(r'<img[^>]+src="([^"]+attachment-tile[^"]*)"', block)
            results.append(
                {
                    "url": url_m.group(1),
                    "slug": url_m.group(2).strip("/"),
                    "title": html.unescape(title_m.group(1).strip()) if title_m else "",
                    "thumbnail": img_m.group(1) if img_m else "",
                }
            )

        # Fallback: simple href scan when container pattern fails
        if not results:
            for m in re.finditer(
                r'href="(https://www\.camscape\.com/webcam/([^"]+))"', html_text
            ):
                url = m.group(1)
                if url not in seen:
                    seen.add(url)
                    results.append(
                        {
                            "url": url,
                            "slug": m.group(2).strip("/"),
                            "title": "",
                            "thumbnail": "",
                        }
                    )

        return results

    # ------------------------------------------------------------------
    # Custom REST API endpoints
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search-as-you-type (SAYT) autocomplete.

        GET /wp-json/camscape/v1/sayt/{query}

        JS origin: camscape.search_endpoint + "/" + encodeURIComponent(term)

        Each result dict has:
          value, label, url
          img      (str)  -- 200x113 thumbnail; webcam results only
          showing  (bool) -- True for "showing" category results
          location (bool) -- True for location results

        Args:
            query: Search string (recommended min 3 chars).
                   Allowed URL path chars: letters, digits, %20 %27 %26.

        Returns:
            List of up to ~11 result dicts.
        """
        if not query:
            raise ValueError("query must not be empty")
        url = f"{WP_JSON}/camscape/v1/sayt/{quote(query, safe='')}"
        return self._get(url).json()

    def get_iss_position(self) -> Optional[Dict[str, float]]:
        """
        Fetch the current ISS position.

        GET /wp-json/camscape/v1/iss

        Polled every second by the webcam-map JS when ISS overlay is active.
        Returns None when data source is temporarily unavailable.

        Returns:
            Dict with 'latitude' and 'longitude' float keys, or None.
        """
        resp = self._get(f"{WP_JSON}/camscape/v1/iss")
        text = resp.text.strip()
        if not text:
            return None
        try:
            return resp.json()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # oEmbed endpoint
    # ------------------------------------------------------------------

    def get_oembed(self, webcam_url: str) -> Dict[str, Any]:
        """
        Fetch oEmbed metadata for a webcam page URL.

        GET /wp-json/oembed/1.0/embed?url={webcam_url}

        Returns dict with: version, provider_name, provider_url,
        author_name, author_url, title, type, width, height,
        html (embed code), thumbnail_url, thumbnail_width, thumbnail_height.

        Args:
            webcam_url: Full webcam page URL.
        """
        return self._get(
            f"{WP_JSON}/oembed/1.0/embed", params={"url": webcam_url}
        ).json()

    def get_oembed_for_slug(self, slug: str) -> Dict[str, Any]:
        """Fetch oEmbed metadata by webcam slug."""
        return self.get_oembed(build_webcam_url(slug))

    # ------------------------------------------------------------------
    # HTML scraping: listing pages
    # ------------------------------------------------------------------

    def get_webcams_by_category(
        self, category_slug: str, order_by: str = "pop"
    ) -> List[Dict[str, str]]:
        """
        Return all webcams in a "showing" category.

        Scrapes: GET /showing/{slug}/?order-by={order}

        All webcams are returned in a single HTML response (no pagination
        on category pages; entire list is rendered server-side).

        Args:
            category_slug: e.g. "beaches", "cityscapes", "birds".
                           See SHOWING_CATEGORIES for the complete list.
            order_by: "pop" (default), "title", "newest", or "temp".

        Returns:
            List of dicts: url, slug, title, thumbnail.
        """
        if order_by not in SORT_ORDERS:
            raise ValueError(f"order_by must be one of {SORT_ORDERS}")
        resp = self._get(
            f"{BASE_URL}/showing/{category_slug.strip('/')}/",
            params={"order-by": order_by},
        )
        return self._extract_webcam_links(resp.text)

    def get_webcams_by_location(
        self, location_slug: str, order_by: str = "pop"
    ) -> List[Dict[str, str]]:
        """
        Return all webcams for a location.

        Scrapes: GET /location/{slug}/?order-by={order}

        Args:
            location_slug: e.g. "london", "florida", "france".
                           Use list_locations() to enumerate all 210 slugs.
            order_by: "pop" (default), "title", "newest", or "temp".

        Returns:
            List of dicts: url, slug, title, thumbnail.
        """
        if order_by not in SORT_ORDERS:
            raise ValueError(f"order_by must be one of {SORT_ORDERS}")
        resp = self._get(
            f"{BASE_URL}/location/{location_slug.strip('/')}/",
            params={"order-by": order_by},
        )
        return self._extract_webcam_links(resp.text)

    def search_html(self, query: str, page: int = 1) -> List[Dict[str, str]]:
        """
        WordPress full-text search (HTML page scrape).

        Scrapes: GET /?s={query}[&paged={page}]

        Args:
            query: Search string.
            page:  1-based page number.

        Returns:
            List of dicts: url, slug, title, thumbnail.
        """
        params: Dict[str, Any] = {"s": query}
        if page > 1:
            params["paged"] = page
        return self._extract_webcam_links(
            self._get(BASE_URL + "/", params=params).text
        )

    def get_new_webcams(self) -> List[Dict[str, str]]:
        """
        Return recently added webcams.

        Scrapes: GET /new-webcams/
        """
        return self._extract_webcam_links(
            self._get(f"{BASE_URL}/new-webcams/").text
        )

    def get_trending_webcams(self) -> List[Dict[str, str]]:
        """
        Return trending / hot-right-now webcams.

        Scrapes: GET /hot-right-now/
        """
        return self._extract_webcam_links(
            self._get(f"{BASE_URL}/hot-right-now/").text
        )

    # ------------------------------------------------------------------
    # HTML scraping: webcam detail page
    # ------------------------------------------------------------------

    def get_webcam_detail(self, slug_or_url: str) -> Dict[str, Any]:
        """
        Fetch full metadata for a single webcam.

        Scrapes the webcam detail page and extracts all embedded JS objects.

        Returned dict keys:
          slug        (str)
          page_url    (str)
          post_id     (int|None)   - WordPress post ID
          wp_rest_url (str|None)   - WP REST URL (requires auth)
          webcam_id   (str|None)   - WP post ID from camscapePlayer
          streams     (list)       - stream objects (see below)
          map         (dict|None)  - map/coordinate data
          categories  (list)       - [{slug, name}] showing taxonomy terms
          locations   (list)       - [{slug, name}] location taxonomy terms
          schema      (dict|None)  - Yoast schema.org JSON-LD graph

        Stream object keys:
          name                  (str)
          type                  (str)  "popup"|"iframe"|"player"|"mjpeg"
          url                   (str)  stream URL or external page URL
          image                 (str)  preview image (popup type)
          show_reported_notice  (bool)
          description           (str)  HTML description
          source                (str)  HTML attribution block

        Map object keys (camscapeWebcamMap):
          webcam.lat      (float)
          webcam.lng      (float)
          webcam.zoom     (int)
          webcam.markers  (list) [{label, default_label, lat, lng, uuid}]
          webcam.layers   (list) tile layer names
          iss             (str)  "true"/"false"
          siteurl         (str)

        Args:
            slug_or_url: Webcam slug or full URL.
        """
        if slug_or_url.startswith("http"):
            page_url = slug_or_url
            m = re.search(r"/webcam/([^/]+)/?$", slug_or_url)
            slug = m.group(1) if m else ""
        else:
            slug = slug_or_url.strip("/")
            page_url = f"{BASE_URL}/webcam/{slug}/"

        resp = self._get(page_url)
        h = resp.text

        result: Dict[str, Any] = {
            "slug": slug,
            "page_url": page_url,
            "post_id": None,
            "wp_rest_url": None,
            "webcam_id": None,
            "streams": [],
            "map": None,
            "categories": [],
            "locations": [],
            "schema": None,
        }

        # WP post ID
        m = re.search(
            r'href="(https://www\.camscape\.com/wp-json/wp/v2/webcam/(\d+))"', h
        )
        if m:
            result["wp_rest_url"] = m.group(1)
            result["post_id"] = int(m.group(2))

        # camscapePlayer
        player = self._extract_js_var(h, "camscapePlayer")
        if player:
            result["webcam_id"] = player.get("webcamid")
            streams = player.get("streams", [])
            for s in streams:
                if s.get("source"):
                    s["source"] = html.unescape(s["source"])
                if s.get("description"):
                    s["description"] = html.unescape(s["description"])
            result["streams"] = streams

        # camscapeWebcamMap
        map_data = self._extract_js_var(h, "camscapeWebcamMap")
        if map_data:
            result["map"] = map_data

        # Yoast schema.org JSON-LD
        sm = re.search(
            r'<script type="application/ld\+json"[^>]*class="yoast-schema-graph"[^>]*>'
            r"(.*?)</script>",
            h,
            re.DOTALL,
        )
        if sm:
            try:
                result["schema"] = json.loads(sm.group(1))
            except json.JSONDecodeError:
                pass

        result["categories"] = [
            {"slug": s, "name": html.unescape(n)}
            for s, n in re.findall(
                r'href="https://www\.camscape\.com/showing/([^/"]+)/"[^>]*>([^<]+)<', h
            )
        ]
        result["locations"] = [
            {"slug": s, "name": html.unescape(n)}
            for s, n in re.findall(
                r'href="https://www\.camscape\.com/location/([^/"]+)/"[^>]*>([^<]+)<', h
            )
        ]

        return result

    # ------------------------------------------------------------------
    # Taxonomy / directory listings via XML sitemaps
    # ------------------------------------------------------------------

    def list_categories(self) -> List[Dict[str, str]]:
        """
        Return all "showing" category slugs from the sitemap.

        Fetches /showing-sitemap.xml (47 entries).

        Returns:
            List of dicts: slug, url, lastmod.
        """
        return self._parse_sitemap(
            "https://www.camscape.com/showing-sitemap.xml", "showing"
        )

    def list_locations(self) -> List[Dict[str, str]]:
        """
        Return all location slugs from the sitemap.

        Fetches /location-sitemap.xml (210 entries).

        Returns:
            List of dicts: slug, url, lastmod.
        """
        return self._parse_sitemap(
            "https://www.camscape.com/location-sitemap.xml", "location"
        )

    def list_all_webcams(self) -> List[Dict[str, str]]:
        """
        Return all webcam slugs from the XML sitemaps.

        Fetches /webcam-sitemap.xml (~1000) + /webcam-sitemap2.xml (~325).
        Total: ~1325 webcams.

        Returns:
            List of dicts: slug, url, lastmod.
        """
        results: List[Dict[str, str]] = []
        for sitemap_url in [
            "https://www.camscape.com/webcam-sitemap.xml",
            "https://www.camscape.com/webcam-sitemap2.xml",
        ]:
            results.extend(self._parse_sitemap(sitemap_url, "webcam"))
        return results

    def _parse_sitemap(
        self, sitemap_url: str, path_segment: str
    ) -> List[Dict[str, str]]:
        resp = self._get(sitemap_url)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            logger.warning("Failed to parse XML from %s", sitemap_url)
            return []
        results = []
        for url_el in root.findall("sm:url", ns):
            loc = url_el.findtext("sm:loc", namespaces=ns) or ""
            lastmod = url_el.findtext("sm:lastmod", namespaces=ns) or ""
            slug_m = re.search(rf"/{re.escape(path_segment)}/([^/]+)/?$", loc)
            slug = slug_m.group(1) if slug_m else ""
            if loc:
                results.append({"url": loc, "slug": slug, "lastmod": lastmod})
        return results

    # ------------------------------------------------------------------
    # WordPress AJAX actions
    # ------------------------------------------------------------------

    def report_webcam(self, webcam_id: str, stream_index: int = 0) -> bool:
        """
        Submit a "not working" report for a webcam stream.

        POST /wp/wp-admin/admin-ajax.php
          action=camscape_report_webcam

        Args:
            webcam_id:    Numeric WordPress post ID string (e.g. "108").
            stream_index: Zero-based stream index to report (default 0).

        Returns:
            True if server returned a non-empty response.
        """
        resp = self._post(
            AJAX_URL,
            data={
                "action": "camscape_report_webcam",
                "webcamId": str(webcam_id),
                "webcamStream": str(stream_index),
            },
        )
        return bool(resp.text.strip())

    # ------------------------------------------------------------------
    # Convenience iterators
    # ------------------------------------------------------------------

    def iter_all_webcam_details(
        self, extra_delay: float = 0.5
    ) -> Iterator[Dict[str, Any]]:
        """
        Iterate over detail dicts for every webcam in the directory.

        Fetches ~1325 pages.  Use a generous extra_delay.

        Args:
            extra_delay: Additional seconds between requests (default 0.5).

        Yields:
            Dict from get_webcam_detail().
        """
        for entry in self.list_all_webcams():
            try:
                yield self.get_webcam_detail(entry["url"])
            except requests.HTTPError as exc:
                logger.warning("Failed %s: %s", entry["url"], exc)
            time.sleep(extra_delay)

    def get_streams_for_category(
        self, category_slug: str, order_by: str = "pop"
    ) -> Iterator[Dict[str, Any]]:
        """
        Yield stream data for every webcam in a category.

        Yields:
            Dict with keys: slug, title, streams.
        """
        for cam in self.get_webcams_by_category(category_slug, order_by):
            try:
                detail = self.get_webcam_detail(cam["slug"])
                yield {
                    "slug": cam["slug"],
                    "title": cam["title"],
                    "streams": detail.get("streams", []),
                }
            except requests.HTTPError as exc:
                logger.warning("Failed %s: %s", cam["slug"], exc)


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------

def build_webcam_url(slug: str) -> str:
    """Return the canonical webcam page URL for a slug."""
    return f"{BASE_URL}/webcam/{slug.strip('/')}/"


def build_category_url(slug: str, order_by: str = "pop") -> str:
    """Return a category listing URL."""
    url = f"{BASE_URL}/showing/{slug.strip('/')}/"
    if order_by != "pop":
        url += f"?order-by={order_by}"
    return url


def build_location_url(slug: str, order_by: str = "pop") -> str:
    """Return a location listing URL."""
    url = f"{BASE_URL}/location/{slug.strip('/')}/"
    if order_by != "pop":
        url += f"?order-by={order_by}"
    return url


def embed_url_from_slug(slug: str) -> str:
    """Return the WP oEmbed endpoint URL for a webcam slug."""
    return f"{WP_JSON}/oembed/1.0/embed?url={quote(build_webcam_url(slug), safe='')}"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Quick demonstration of all major features."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = CamscapeClient(request_delay=1.0)

    print("=" * 60)
    print("1. SAYT search for 'beach'")
    print("=" * 60)
    for r in client.search("beach")[:5]:
        kind = "category" if r.get("showing") else ("location" if r.get("location") else "webcam")
        print(f"  [{kind:8s}] {r['label']:<50s} {r['url']}")

    print()
    print("=" * 60)
    print("2. ISS position")
    print("=" * 60)
    iss = client.get_iss_position()
    if iss:
        print(f"  lat={iss.get('latitude')}, lng={iss.get('longitude')}")
    else:
        print("  ISS data not currently available")

    print()
    print("=" * 60)
    print("3. Webcam detail: abbey-road-crossing-webcam")
    print("=" * 60)
    detail = client.get_webcam_detail("abbey-road-crossing-webcam")
    print(f"  Post ID  : {detail['post_id']}")
    print(f"  Webcam ID: {detail['webcam_id']}")
    for s in detail["streams"]:
        print(f"  Stream [{s['type']:6s}] {s['name']:<30s} {s['url'][:60]}")
    if detail.get("map"):
        w = detail["map"]["webcam"]
        print(f"  Coords   : lat={w['lat']:.6f}, lng={w['lng']:.6f}")
    print(f"  Categories: {[c['name'] for c in detail['categories']]}")
    print(f"  Locations : {[l['name'] for l in detail['locations']]}")

    print()
    print("=" * 60)
    print("4. oEmbed")
    print("=" * 60)
    oe = client.get_oembed_for_slug("abbey-road-crossing-webcam")
    print(f"  Title    : {oe.get('title')}")
    print(f"  Thumbnail: {oe.get('thumbnail_url')}")

    print()
    print("=" * 60)
    print("5. Beach webcams (top 5 by popularity)")
    print("=" * 60)
    beaches = client.get_webcams_by_category("beaches")
    print(f"  Total: {len(beaches)}")
    for cam in beaches[:5]:
        print(f"  {cam['slug']}")

    print()
    print("=" * 60)
    print("6. London webcams")
    print("=" * 60)
    london = client.get_webcams_by_location("london")
    print(f"  Total: {len(london)}")
    for cam in london[:5]:
        print(f"  {cam['title'] or cam['slug']}")

    print()
    print("=" * 60)
    print("7. Categories and total webcam count")
    print("=" * 60)
    print(f"  Categories : {len(client.list_categories())}")
    print(f"  Locations  : {len(client.list_locations())}")
    print(f"  Total cams : {len(client.list_all_webcams())}")


if __name__ == "__main__":
    _demo()
