"""
SkylineWebcams Python Client
============================================================
Reverse-engineered client for SkylineWebcams (skylinewebcams.com)

Discovered and verified endpoints (2026-03-27):

  Web pages (HTML scraping):
    - https://www.skylinewebcams.com/en/webcam/{country}.html
    - https://www.skylinewebcams.com/en/webcam/{country}/{region}.html
    - https://www.skylinewebcams.com/en/webcam/{country}/{region}/{city}.html
    - https://www.skylinewebcams.com/en/webcam/{country}/{region}/{city}/{slug}.html
    - https://www.skylinewebcams.com/en/live-cams-category/{category}.html
    - https://www.skylinewebcams.com/en/top-live-cams.html
    - https://www.skylinewebcams.com/en/new-livecams.html
    - https://www.skylinewebcams.com/en/webcam.html  (full directory)
    - https://www.skylinewebcams.com/en/webcam/{path}/timelapse.html  (daily time-lapse)

  HLS streaming (own cameras):
    - Source token in page JS:  source:'livee.m3u8?a={token}'
    - Actual HLS URL:           https://hd-auth.skylinewebcams.com/live.m3u8?a={token}
    - Construction (playerj.js): replace 'livee.' with 'live.' and prepend hd-auth host
    - TS segments:              https://hddn{N}.skylinewebcams.com/{camid}livic-{timestamp}.ts

  HLS time-lapse (own cameras):
    - Source token in timelapse page JS:  source:'lapse.m3u8?a={token}'
    - Actual HLS URL:                     https://hd-auth.skylinewebcams.com/lapse.m3u8?a={token}

  YouTube-embedded cameras (external cameras):
    - Page uses YouTube IFrame API: new YT.Player('live', {videoId:'XXXX', ...})
    - JSON-LD embedUrl:             https://www.youtube.com/embed/{video_id}
    - Watch URL:                    https://www.youtube.com/watch?v={video_id}

  Camera thumbnails / snapshots (CDN):
    - https://cdn.skylinewebcams.com/live{cam_id}.jpg   (live thumbnail, small, ~18KB, updated ~30s)
    - https://cdn.skylinewebcams.com/_{cam_id}.jpg      (poster / static thumbnail)
    - https://cdn.skylinewebcams.com/{cam_id}.jpg       (static page thumbnail)
    - https://cdn.skylinewebcams.com/social{cam_id}.jpg (social/OG image, 1200x628)

  Camera stats (JSON, no auth required):
    - https://cdn.skylinewebcams.com/{cam_id}.json
      Response: {"t": "52.341.534", "n": "293"}
      t = total all-time views (formatted with dots as thousands separator)
      n = current viewer count

  Photos / snapshots archive:
    - https://photo.skylinewebcams.com/pht.php?pid={cam_id}&l={lang}
      Returns HTML partial with photo thumbnails
    - https://photo.skylinewebcams.com/gallery.php?id={photo_id}&l={lang}
      Returns HTML partial with full-resolution photo carousel
    - Photo thumbnails: https://photo.skylinewebcams.com/pht/_{hash}.jpg  (small)
    - Photo full-res:   https://photo.skylinewebcams.com/pht/{hash}.jpg   (full)

  Utility / internal:
    - https://www.skylinewebcams.com/cams/rating.php?r={value}&id={cam_id}  (GET star rating)
    - https://www.skylinewebcams.com/cams/share.php?l={lang}&w={cam_id}&u={url}  (share modal)
    - https://www.skylinewebcams.com/cams/login.php?l={lang}   (login modal)
    - https://www.skylinewebcams.com/cams/info.php?l={lang}    (info modal, shown when ad fails)
    - https://www.skylinewebcams.com/click.php?l={base64(id|type|url)}  (sponsor redirect)
    - https://ad.skylinewebcams.com/ad.php  (POST id="{cam_id}_{lang}", returns ad data)
    - https://www.skylinewebcams.com/en/weather/{country}/{region}/{city}.html  (weather page)

URL slug country keys (as used on the site):
    italia, espana, ellada, deutschland, france, hrvatska, schweiz, norge,
    brasil, united-states, united-kingdom, australia, ...
    (Country slugs are in local language or common English name)

Supported languages:
    en, it, de, es, fr, pl, el, hr, sl, ru, zh

Categories:
    beach-cams, city-cams, nature-mountain-cams, seaport-cams,
    ski-cams, animals-cams, volcanoes-cams, lake-cams,
    unesco-cams, live-web-cams

Stream type detection:
    If the page contains source:'livee.m3u8?a=...' → HLS stream (own infrastructure)
    If the page contains new YT.Player or videoId:'...' → YouTube stream
    The JSON-LD embedUrl field also distinguishes the two types.

Notes on HLS token:
    Tokens appear to be session-scoped and rotate on each page load. The token
    is a 26-character alphanumeric string embedded directly in the page HTML.
    Always fetch a fresh page before starting a stream session.
"""

import re
import json
import time
import logging
from typing import Optional
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.skylinewebcams.com"
CDN_URL = "https://cdn.skylinewebcams.com"
PHOTO_URL = "https://photo.skylinewebcams.com"
HLS_AUTH_URL = "https://hd-auth.skylinewebcams.com"
AD_URL = "https://ad.skylinewebcams.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.skylinewebcams.com/",
}

CATEGORIES = {
    "beaches":    "beach-cams",
    "cities":     "city-cams",
    "landscapes": "nature-mountain-cams",
    "marinas":    "seaport-cams",
    "ski":        "ski-cams",
    "animals":    "animals-cams",
    "volcanoes":  "volcanoes-cams",
    "lakes":      "lake-cams",
    "unesco":     "unesco-cams",
    "web":        "live-web-cams",
    # Also accepted as the raw slug:
    "beach-cams": "beach-cams",
    "city-cams":  "city-cams",
    "nature-mountain-cams": "nature-mountain-cams",
    "seaport-cams": "seaport-cams",
    "ski-cams":   "ski-cams",
    "animals-cams": "animals-cams",
    "volcanoes-cams": "volcanoes-cams",
    "lake-cams":  "lake-cams",
    "unesco-cams": "unesco-cams",
    "live-web-cams": "live-web-cams",
}

# Country name → URL slug mapping
COUNTRY_SLUGS = {
    "italy":                 "italia",
    "spain":                 "espana",
    "greece":                "ellada",
    "germany":               "deutschland",
    "france":                "france",
    "croatia":               "hrvatska",
    "switzerland":           "schweiz",
    "norway":                "norge",
    "brazil":                "brasil",
    "united states":         "united-states",
    "us":                    "united-states",
    "united kingdom":        "united-kingdom",
    "uk":                    "united-kingdom",
    "australia":             "australia",
    "austria":               "austria",
    "albania":               "albania",
    "argentina":             "argentina",
    "barbados":              "barbados",
    "belize":                "belize",
    "bermuda":               "bermuda",
    "bolivia":               "bolivia",
    "canada":                "canada",
    "caribbean netherlands": "caribbean-netherlands",
    "chile":                 "chile",
    "china":                 "china",
    "costa rica":            "costa-rica",
    "cyprus":                "cyprus",
    "czech republic":        "czech-republic",
    "dominican republic":    "dominican-republic",
    "ecuador":               "ecuador",
    "egypt":                 "egypt",
    "el salvador":           "el-salvador",
    "faroe islands":         "faroe-islands",
    "grenada":               "grenada",
    "guadeloupe":            "guadeloupe",
    "honduras":              "honduras",
    "hungary":               "hungary",
    "iceland":               "iceland",
    "ireland":               "ireland",
    "israel":                "israel",
    "jordan":                "jordan",
    "kenya":                 "kenya",
    "luxembourg":            "luxembourg",
    "maldives":              "maldives",
    "malta":                 "malta",
    "martinique":            "martinique",
    "mauritius":             "mauritius",
    "mexico":                "mexico",
    "morocco":               "morocco",
    "panama":                "panama",
    "peru":                  "peru",
    "philippines":           "philippines",
    "poland":                "poland",
    "portugal":              "portugal",
    "san marino":            "repubblica-di-san-marino",
    "romania":               "romania",
    "seychelles":            "seychelles",
    "sint maarten":          "sint-maarten",
    "slovenia":              "slovenija",
    "south africa":          "south-africa",
    "sri lanka":             "sri-lanka",
    "thailand":              "thailand",
    "turkey":                "turkey",
    "uruguay":               "uruguay",
    "us virgin islands":     "us-virgin-islands",
    "venezuela":             "venezuela",
    "vietnam":               "vietnam",
    "zambia":                "zambia",
    "zanzibar":              "zanzibar",
    "senegal":               "senegal",
    "bosnia":                "bosnia-and-herzegovina",
    "cabo verde":            "cabo-verde",
    "cape verde":            "cabo-verde",
    "bulgaria":              "bulgaria",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class WebcamInfo:
    """Metadata for a single SkylineWebcams camera."""
    cam_id: str                    # numeric string, e.g. "522"
    name: str                      # human-readable name
    description: str = ""          # subtitle / description
    url: str = ""                  # relative URL path, e.g. /en/webcam/italia/...
    country_slug: str = ""         # e.g. "italia"
    region_slug: str = ""          # e.g. "veneto"
    city_slug: str = ""            # e.g. "venezia"
    cam_slug: str = ""             # e.g. "piazza-san-marco"
    thumbnail_url: str = ""        # cdn.skylinewebcams.com/live{id}.jpg
    social_image_url: str = ""     # cdn.skylinewebcams.com/social{id}.jpg
    static_thumbnail_url: str = "" # cdn.skylinewebcams.com/{id}.jpg
    hls_token: str = ""            # auth token for HLS stream (own cameras only)
    hls_url: str = ""              # full HLS URL (own cameras only)
    youtube_video_id: str = ""     # YouTube video ID (YouTube-embedded cameras only)
    stream_type: str = ""          # "hls" | "youtube" | ""
    total_views: str = ""          # formatted string, e.g. "52.341.534"
    current_viewers: int = 0
    upload_date: str = ""          # ISO8601 from schema.org
    interaction_count: int = 0     # from schema.org VideoObject
    rating: float = 0.0            # aggregate rating (0-5)
    rating_count: int = 0          # number of ratings

    @property
    def youtube_url(self) -> str:
        """Full YouTube watch URL for YouTube-embedded cameras."""
        if self.youtube_video_id:
            return f"https://www.youtube.com/watch?v={self.youtube_video_id}"
        return ""

    @property
    def youtube_embed_url(self) -> str:
        """YouTube embed URL for YouTube-embedded cameras."""
        if self.youtube_video_id:
            return f"https://www.youtube.com/embed/{self.youtube_video_id}"
        return ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["youtube_url"] = self.youtube_url
        d["youtube_embed_url"] = self.youtube_embed_url
        return d


@dataclass
class PhotoSnapshot:
    """A user-uploaded photo snapshot for a camera."""
    photo_id: str
    cam_id: str
    thumbnail_url: str
    full_url: str
    caption: str = ""
    date_label: str = ""


@dataclass
class CameraStats:
    """Live viewer stats for a camera."""
    cam_id: str
    total_views: str    # formatted string with dots
    current_viewers: int


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, extra_headers: Optional[dict] = None, timeout: int = 15) -> str:
    """Fetch a URL and return the decoded text body."""
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            encoding = resp.headers.get_content_charset("utf-8") or "utf-8"
            return raw.decode(encoding, errors="replace")
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e


def _fetch_bytes(url: str, extra_headers: Optional[dict] = None, timeout: int = 15) -> bytes:
    """Fetch a URL and return raw bytes."""
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _extract_cam_cards(html: str) -> list[dict]:
    """
    Extract camera cards from a listing page.
    Each card has: cam_id, name, description, url, thumbnail_url.

    The HTML structure for each card (confirmed from live pages):
        <a href="en/webcam/{country}/{region}/{city}/{slug}.html"
           class="col-xs-12 col-sm-6 col-md-4">
          <div class="cam-light">
            [<span class="lcam">World Heritage</span>]
            <img src="https://cdn.skylinewebcams.com/live{ID}.jpg"
                 loading="lazy" alt="{name}" ...>
            <p class="tcam">{name}</p>
            <p class="subt">{description}</p>
          </div>
        </a>

    Note: href values on listing pages use relative URLs without leading slash.
    On camera detail pages (nearby section), hrefs use absolute /en/webcam/... paths.
    Both formats are handled.
    """
    results = []
    seen_ids: set = set()

    # Primary pattern: matches the listing-page structure.
    # Handles both relative ("en/webcam/...") and absolute ("/en/webcam/...") hrefs.
    # The img tag's src attribute can appear anywhere within the tag.
    cam_block_re = re.compile(
        # Anchor with a webcam URL href (with or without language prefix)
        r'<a\s+href="((?:/[a-z]{2})?/webcam/[^"]+\.html|[a-z]{2}/webcam/[^"]+\.html)"'
        r'[^>]*>\s*'
        # cam-light div (class may have additional classes like "white")
        r'<div[^>]*\bclass="cam-light(?:\s[^"]*)?"\s*>'
        # Optional badge span (e.g. "World Heritage")
        r'(?:\s*<span[^>]*>[^<]*</span>)?'
        # img tag — src attribute can be anywhere in the tag
        r'\s*<img\b[^>]*\bsrc="https://cdn\.skylinewebcams\.com/live(\d+)\.jpg"'
        r'[^>]*>',
        re.S,
    )
    # We'll get the alt attribute with a secondary search in the block
    alt_re = re.compile(r'\balt="([^"]*)"')
    for m in cam_block_re.finditer(html):
        href_raw = m.group(1)
        cam_id = m.group(2)

        if cam_id in seen_ids:
            continue
        seen_ids.add(cam_id)

        # Normalise href to absolute
        if href_raw.startswith("/"):
            href = href_raw                     # already absolute
        else:
            href = "/" + href_raw               # make absolute

        # Find the block from the anchor start to the closing </a>
        block_start = m.start()
        block_end = html.find("</a>", block_start)
        if block_end == -1:
            block_end = block_start + 1000
        block_content = html[block_start:block_end]

        # Extract the img alt text from the matched region (fallback name)
        alt_m = alt_re.search(m.group(0))
        alt_text = alt_m.group(1).strip() if alt_m else ""

        name_m = re.search(r'<p[^>]*class="tcam"[^>]*>([^<]+)</p>', block_content)
        desc_m = re.search(r'<p[^>]*class="subt"[^>]*>([^<]+)</p>', block_content)

        name = name_m.group(1).strip() if name_m else alt_text
        desc = desc_m.group(1).strip() if desc_m else ""

        # Parse location slugs from the href path
        path = href.lstrip("/")                     # "en/webcam/italia/veneto/venezia/slug.html"
        path = re.sub(r"\.html$", "", path)         # remove .html
        parts = path.split("/")                     # ["en","webcam","italia","veneto","venezia","slug"]
        country_slug = parts[2] if len(parts) > 2 else ""
        region_slug  = parts[3] if len(parts) > 3 else ""
        city_slug    = parts[4] if len(parts) > 4 else ""
        cam_slug     = parts[5] if len(parts) > 5 else ""

        results.append({
            "cam_id": cam_id,
            "name": name,
            "description": desc,
            "url": href,
            "country_slug": country_slug,
            "region_slug": region_slug,
            "city_slug": city_slug,
            "cam_slug": cam_slug,
            "thumbnail_url": f"{CDN_URL}/live{cam_id}.jpg",
            "social_image_url": f"{CDN_URL}/social{cam_id}.jpg",
            "static_thumbnail_url": f"{CDN_URL}/{cam_id}.jpg",
        })

    return results


def _parse_cam_page(html: str, cam_url: str = "") -> Optional[WebcamInfo]:
    """
    Parse a full camera detail page and extract all metadata.

    Two stream types are supported:

    1. HLS (own cameras) — Clappr player initialized with:
         var player=new Clappr.Player({..., nkey:'522.jpg',
           source:'livee.m3u8?a=<TOKEN>', ...});
       The playerj.js transforms this to:
         https://hd-auth.skylinewebcams.com/live.m3u8?a=<TOKEN>

    2. YouTube (external cameras) — YouTube IFrame API:
         var player; function onYouTubeIframeAPIReady(){
           player=new YT.Player('live',{..., videoId:'XXXX', ...});
         }
       JSON-LD embedUrl: https://www.youtube.com/embed/XXXX
    """
    # --- Stats JSON endpoint: cdn.skylinewebcams.com/{id}.json ---
    stats_m = re.search(r'cdn\.skylinewebcams\.com/(\d+)\.json', html)
    cam_id_from_stats = stats_m.group(1) if stats_m else ""

    # --- HLS stream (Clappr player) ---
    nkey_m = re.search(r"nkey:'(\d+)\.jpg'", html)
    source_m = re.search(r"source:'livee\.m3u8\?a=([a-z0-9]+)'", html)
    cam_id = nkey_m.group(1) if nkey_m else cam_id_from_stats
    token = source_m.group(1) if source_m else ""
    hls_url = f"{HLS_AUTH_URL}/live.m3u8?a={token}" if token else ""

    # --- YouTube stream ---
    yt_video_id = ""
    yt_m = re.search(r"videoId:'([^']+)'", html)
    if yt_m:
        yt_video_id = yt_m.group(1)
    if not yt_video_id:
        # Try from JSON-LD embedUrl
        embed_m = re.search(r'"embedUrl":"https://www\.youtube\.com/embed/([^"]+)"', html)
        if embed_m:
            yt_video_id = embed_m.group(1)

    # If we couldn't detect a cam_id yet, bail out
    if not cam_id:
        return None

    # Determine stream type
    if token:
        stream_type = "hls"
    elif yt_video_id:
        stream_type = "youtube"
    else:
        stream_type = ""

    # --- Schema.org structured data ---
    name = description = upload_date = ""
    interaction_count = 0
    ld_m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if ld_m:
        try:
            ld = json.loads(ld_m.group(1))
            name = ld.get("name", "")
            description = ld.get("description", "")
            upload_date = ld.get("uploadDate", "")
            stat = ld.get("interactionStatistic", {})
            interaction_count = stat.get("userInteractionCount", 0)
        except json.JSONDecodeError:
            pass

    # Fallback name from <h1>
    if not name:
        h1_m = re.search(r"<h1[^>]*>([^<]+)", html)
        name = h1_m.group(1).strip() if h1_m else f"Camera {cam_id}"

    # --- Rating ---
    rating = 0.0
    rating_count = 0
    rating_m = re.search(r'itemprop="ratingValue">([0-9.]+)<', html)
    rating_count_m = re.search(r'itemprop="ratingCount">(\d+)<', html)
    if rating_m:
        try:
            rating = float(rating_m.group(1))
        except ValueError:
            pass
    if rating_count_m:
        try:
            rating_count = int(rating_count_m.group(1))
        except ValueError:
            pass

    # --- Breadcrumb location slugs ---
    # Extract from the <ol class="breadcrumb"> element to avoid picking up
    # mega-menu country links scattered throughout the page.
    country_slug = region_slug = city_slug = ""
    bc_section_m = re.search(r'<ol class="breadcrumb"[^>]*>(.*?)</ol>', html, re.S)
    if bc_section_m:
        bc_section = bc_section_m.group(1)
        bc_links = re.findall(
            r'href="(?:/[a-z]{2})?/webcam/([^"]+)\.html"[^>]*><span[^>]*>',
            bc_section
        )
        # bc_links is in breadcrumb order:
        #   ["italia", "italia/veneto", "italia/veneto/venezia"]
        for link in bc_links:
            parts = link.split("/")
            if len(parts) == 1:
                country_slug = parts[0]
            elif len(parts) == 2:
                region_slug = parts[1]
            elif len(parts) >= 3:
                city_slug = parts[2]

    # cam slug from canonical URL
    cam_slug = ""
    if cam_url:
        slug_m = re.search(r"/([^/]+)\.html$", cam_url)
        cam_slug = slug_m.group(1) if slug_m else ""

    return WebcamInfo(
        cam_id=cam_id,
        name=name,
        description=description,
        url=cam_url,
        country_slug=country_slug,
        region_slug=region_slug,
        city_slug=city_slug,
        cam_slug=cam_slug,
        thumbnail_url=f"{CDN_URL}/live{cam_id}.jpg",
        social_image_url=f"{CDN_URL}/social{cam_id}.jpg",
        static_thumbnail_url=f"{CDN_URL}/{cam_id}.jpg",
        hls_token=token,
        hls_url=hls_url,
        youtube_video_id=yt_video_id,
        stream_type=stream_type,
        upload_date=upload_date,
        interaction_count=interaction_count,
        rating=rating,
        rating_count=rating_count,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SkylineWebcamsClient:
    """
    Python client for SkylineWebcams.

    Usage:
        client = SkylineWebcamsClient()

        # List cameras by country
        cams = client.list_by_country("italy")

        # Get cameras by category
        cams = client.list_by_category("volcanoes")

        # Get full camera info including HLS stream URL
        cam = client.get_camera("italia/veneto/venezia/piazza-san-marco")

        # Get live stream URL
        print(cam.hls_url)

        # Get live thumbnail
        img = client.get_thumbnail(cam.cam_id)

        # Get camera stats (total views, current viewers)
        stats = client.get_stats(cam.cam_id)

        # Get archive photos
        photos = client.get_photos(cam.cam_id)

        # Get top / featured cameras
        top = client.list_top_cameras()
        newest = client.list_new_cameras()
    """

    def __init__(
        self,
        language: str = "en",
        request_delay: float = 0.5,
        timeout: int = 15,
    ):
        """
        Args:
            language: Language code for pages. One of: en, it, de, es, fr, pl,
                      el, hr, sl, ru, zh. Defaults to "en".
            request_delay: Seconds to sleep between HTTP requests (be polite).
            timeout: HTTP request timeout in seconds.
        """
        self.language = language
        self.request_delay = request_delay
        self.timeout = timeout
        self._last_request = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, extra_headers: Optional[dict] = None) -> str:
        """Rate-limited fetch."""
        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        result = _fetch(url, extra_headers=extra_headers, timeout=self.timeout)
        self._last_request = time.time()
        return result

    def _country_slug(self, country: str) -> str:
        """Normalise a country name or slug."""
        lower = country.lower().strip()
        return COUNTRY_SLUGS.get(lower, lower.replace(" ", "-"))

    def _category_slug(self, category: str) -> str:
        """Normalise a category name or slug."""
        lower = category.lower().strip()
        return CATEGORIES.get(lower, lower)

    # ------------------------------------------------------------------
    # Camera listing methods
    # ------------------------------------------------------------------

    def list_by_country(self, country: str) -> list[WebcamInfo]:
        """
        List cameras for a given country.

        Args:
            country: Country name ("italy") or slug ("italia").

        Returns:
            List of WebcamInfo objects (without HLS token — call get_camera()
            for full details including the stream URL).

        Examples:
            client.list_by_country("italy")
            client.list_by_country("greece")
            client.list_by_country("espana")     # using native slug
        """
        slug = self._country_slug(country)
        url = f"{BASE_URL}/{self.language}/webcam/{slug}.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    def list_by_region(self, country: str, region: str) -> list[WebcamInfo]:
        """
        List cameras for a country + region combination.

        Args:
            country: Country name or slug.
            region: Region slug as used in the URL, e.g. "veneto", "sicilia",
                    "canarias", "trentino-alto-adige".

        Examples:
            client.list_by_region("italy", "veneto")
            client.list_by_region("espana", "canarias")
        """
        c_slug = self._country_slug(country)
        url = f"{BASE_URL}/{self.language}/webcam/{c_slug}/{region}.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    def list_by_city(self, country: str, region: str, city: str) -> list[WebcamInfo]:
        """
        List cameras for a specific city.

        Args:
            country: Country name or slug.
            region:  Region slug.
            city:    City slug, e.g. "venezia", "roma", "catania".

        Examples:
            client.list_by_city("italia", "veneto", "venezia")
            client.list_by_city("italia", "lazio", "roma")
        """
        c_slug = self._country_slug(country)
        url = f"{BASE_URL}/{self.language}/webcam/{c_slug}/{region}/{city}.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    def list_by_category(self, category: str) -> list[WebcamInfo]:
        """
        List cameras for a given category.

        Args:
            category: Category name (friendly) or slug.
                      Friendly names: beaches, cities, landscapes, marinas,
                      ski, animals, volcanoes, lakes, unesco, web.
                      Slugs: beach-cams, city-cams, nature-mountain-cams,
                      seaport-cams, ski-cams, animals-cams, volcanoes-cams,
                      lake-cams, unesco-cams, live-web-cams.

        Examples:
            client.list_by_category("volcanoes")
            client.list_by_category("beaches")
            client.list_by_category("ski-cams")
        """
        slug = self._category_slug(category)
        url = f"{BASE_URL}/{self.language}/live-cams-category/{slug}.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    def list_top_cameras(self) -> list[WebcamInfo]:
        """Return the editor-curated TOP live cameras."""
        url = f"{BASE_URL}/{self.language}/top-live-cams.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    def list_new_cameras(self) -> list[WebcamInfo]:
        """Return the most recently added cameras."""
        url = f"{BASE_URL}/{self.language}/new-livecams.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    def list_all_cameras(self) -> list[WebcamInfo]:
        """
        Return cameras from the main directory page (first 900+ cameras
        shown on the all-webcams listing).
        """
        url = f"{BASE_URL}/{self.language}/webcam.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        cams = []
        for c in cards:
            cams.append(WebcamInfo(**{
                k: v for k, v in c.items()
                if k in WebcamInfo.__dataclass_fields__
            }))
        return cams

    # ------------------------------------------------------------------
    # Individual camera detail
    # ------------------------------------------------------------------

    def get_camera(self, path_or_url: str) -> WebcamInfo:
        """
        Fetch full camera info including HLS stream URL.

        Args:
            path_or_url: Either:
              - A path relative to /en/webcam/, e.g.
                "italia/veneto/venezia/piazza-san-marco"
              - A full relative URL, e.g.
                "/en/webcam/italia/veneto/venezia/piazza-san-marco.html"
              - A full absolute URL, e.g.
                "https://www.skylinewebcams.com/en/webcam/..."

        Returns:
            WebcamInfo with hls_url and hls_token populated.

        Examples:
            cam = client.get_camera("italia/veneto/venezia/piazza-san-marco")
            cam = client.get_camera("italia/sicilia/catania/etna-piazzale-rifugio-sapienza")
        """
        if path_or_url.startswith("https://") or path_or_url.startswith("http://"):
            url = path_or_url
        elif path_or_url.startswith("/"):
            url = BASE_URL + path_or_url
        else:
            # Assume it's country/region/city/slug
            url = f"{BASE_URL}/{self.language}/webcam/{path_or_url}.html"

        html = self._get(url)
        cam = _parse_cam_page(html, cam_url=url)
        if cam is None:
            raise ValueError(f"Could not parse camera page at: {url}")
        return cam

    def get_camera_by_id(self, cam_id: str) -> dict:
        """
        Return available data for a camera known by its numeric ID.

        This returns metadata that can be derived without fetching the full
        HTML page: thumbnails, stats endpoint URLs, etc.  It does NOT include
        the HLS auth token (for that you need get_camera() with the full URL).

        Args:
            cam_id: Numeric camera ID, e.g. "522".

        Returns:
            dict with thumbnail, social image, stats URL, photo URL.
        """
        cid = str(cam_id)
        return {
            "cam_id": cid,
            "thumbnail_url": f"{CDN_URL}/live{cid}.jpg",
            "social_image_url": f"{CDN_URL}/social{cid}.jpg",
            "static_thumbnail_url": f"{CDN_URL}/{cid}.jpg",
            "stats_url": f"{CDN_URL}/{cid}.json",
            "photos_url": f"{PHOTO_URL}/pht.php?pid={cid}&l={self.language}",
        }

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def get_stream_url(self, cam: WebcamInfo) -> str:
        """
        Return the best stream URL for a camera.

        For HLS cameras:     https://hd-auth.skylinewebcams.com/live.m3u8?a={token}
        For YouTube cameras: https://www.youtube.com/watch?v={video_id}

        The HLS URL is session-scoped. Auth tokens rotate on each page load,
        so refresh the camera object periodically for long-running sessions.

        Args:
            cam: A WebcamInfo obtained from get_camera().

        Returns:
            Stream URL string.
        """
        if cam.stream_type == "hls" and cam.hls_url:
            return cam.hls_url
        if cam.stream_type == "youtube" and cam.youtube_video_id:
            return cam.youtube_url
        if cam.hls_url:
            return cam.hls_url
        if cam.youtube_url:
            return cam.youtube_url
        raise ValueError(
            f"No stream URL for camera {cam.cam_id}. "
            "Use get_camera() (not list_by_*) to retrieve the stream URL."
        )

    def get_timelapse_url(self, cam_path_or_url: str) -> str:
        """
        Fetch the HLS time-lapse stream URL for a camera.

        SkylineWebcams generates a daily time-lapse for each own-infrastructure
        camera. The time-lapse uses a separate HLS endpoint:
          https://hd-auth.skylinewebcams.com/lapse.m3u8?a={token}

        The token is embedded in the timelapse page:
          /en/webcam/{country}/{region}/{city}/{slug}/timelapse.html

        Args:
            cam_path_or_url: Camera path (e.g. "italia/veneto/venezia/piazza-san-marco")
                             or full camera page URL.

        Returns:
            HLS time-lapse URL string.

        Raises:
            ValueError: If no time-lapse token is found (YouTube cameras don't
                        have time-lapses).
        """
        # Build the timelapse URL from the camera page URL
        if cam_path_or_url.startswith("https://") or cam_path_or_url.startswith("http://"):
            timelapse_url = cam_path_or_url.replace(".html", "/timelapse.html")
        elif cam_path_or_url.startswith("/"):
            timelapse_url = BASE_URL + cam_path_or_url.replace(".html", "/timelapse.html")
        else:
            # Assume country/region/city/slug format
            clean = cam_path_or_url.rstrip("/").replace(".html", "")
            timelapse_url = f"{BASE_URL}/{self.language}/webcam/{clean}/timelapse.html"

        html = self._get(timelapse_url)
        token_m = re.search(r"source:'lapse\.m3u8\?a=([a-z0-9]+)'", html)
        if not token_m:
            raise ValueError(
                f"No time-lapse token found at {timelapse_url}. "
                "YouTube cameras do not have time-lapses."
            )
        return f"{HLS_AUTH_URL}/lapse.m3u8?a={token_m.group(1)}"

    def get_m3u8_playlist(self, cam: WebcamInfo) -> str:
        """
        Fetch and return the raw HLS playlist (#EXTM3U) content.

        Args:
            cam: A WebcamInfo obtained from get_camera().

        Returns:
            Raw m3u8 playlist text. May be empty if the camera is offline.
        """
        url = self.get_stream_url(cam)
        return _fetch(url, extra_headers={"Referer": BASE_URL + "/"})

    def get_stream_segments(self, cam: WebcamInfo) -> list[str]:
        """
        Parse the HLS playlist and return the list of .ts segment URLs.

        Args:
            cam: A WebcamInfo obtained from get_camera().

        Returns:
            List of .ts segment URLs (usually 3-8 segments of ~4 s each).
        """
        playlist = self.get_m3u8_playlist(cam)
        return re.findall(r"(https://[^\s]+\.ts)", playlist)

    # ------------------------------------------------------------------
    # Thumbnails & snapshots
    # ------------------------------------------------------------------

    def get_thumbnail(self, cam_id: str) -> bytes:
        """
        Download the live thumbnail JPEG for a camera (~18 KB, updated ~30 s).

        Args:
            cam_id: Numeric camera ID.

        Returns:
            Raw JPEG bytes.
        """
        url = f"{CDN_URL}/live{cam_id}.jpg"
        return _fetch_bytes(url, timeout=self.timeout)

    def get_social_image(self, cam_id: str) -> bytes:
        """
        Download the large social/OG image for a camera (~160 KB, 1200×628).

        Args:
            cam_id: Numeric camera ID.

        Returns:
            Raw JPEG bytes.
        """
        url = f"{CDN_URL}/social{cam_id}.jpg"
        return _fetch_bytes(url, timeout=self.timeout)

    def get_thumbnail_url(self, cam_id: str, size: str = "live") -> str:
        """
        Return thumbnail URL without downloading.

        Args:
            cam_id: Numeric camera ID.
            size:   "live"   → live-updating small thumbnail (cdn.skylinewebcams.com/live{id}.jpg)
                    "social" → 1200×628 OG image (cdn.skylinewebcams.com/social{id}.jpg)
                    "static" → static page image (cdn.skylinewebcams.com/{id}.jpg)
        """
        if size == "social":
            return f"{CDN_URL}/social{cam_id}.jpg"
        elif size == "static":
            return f"{CDN_URL}/{cam_id}.jpg"
        else:
            return f"{CDN_URL}/live{cam_id}.jpg"

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, cam_id: str) -> CameraStats:
        """
        Fetch live viewer count and total view count.

        Args:
            cam_id: Numeric camera ID.

        Returns:
            CameraStats(cam_id, total_views, current_viewers)

        Note:
            total_views is a formatted string using dots as thousands
            separators (Italian convention), e.g. "52.341.534".
            current_viewers is the integer live viewer count.
        """
        url = f"{CDN_URL}/{cam_id}.json"
        html = _fetch(url, extra_headers={"Referer": BASE_URL + "/"})
        try:
            data = json.loads(html)
            current = int(data.get("n", 0))
        except (json.JSONDecodeError, ValueError):
            data = {}
            current = 0
        return CameraStats(
            cam_id=str(cam_id),
            total_views=data.get("t", ""),
            current_viewers=current,
        )

    # ------------------------------------------------------------------
    # Photos / archive
    # ------------------------------------------------------------------

    def get_photos(self, cam_id: str) -> list[PhotoSnapshot]:
        """
        Fetch the list of user-shared archive photos for a camera.

        Photos are snapshots taken at various times by viewers and shared
        on the site. The endpoint returns an HTML partial.

        Args:
            cam_id: Numeric camera ID.

        Returns:
            List of PhotoSnapshot objects with thumbnail and full-res URLs.
        """
        url = (
            f"{PHOTO_URL}/pht.php"
            f"?pid={cam_id}&l={self.language}"
        )
        html = self._get(url, extra_headers={
            "Referer": f"{BASE_URL}/{self.language}/webcam.html",
        })

        photos = []
        # Extract gallery links and thumbnails
        items = re.findall(
            r'href="(https://photo\.skylinewebcams\.com/gallery\.php\?id=(\d+)[^"]*)"'
            r'.*?<img src="(https://photo\.skylinewebcams\.com/pht/_([a-f0-9]+)\.jpg)"'
            r'.*?<div class="tcam">([^<]*)</div>',
            html, re.S
        )
        for gallery_url, photo_id, thumb_url, photo_hash, date_label in items:
            photos.append(PhotoSnapshot(
                photo_id=photo_id,
                cam_id=str(cam_id),
                thumbnail_url=thumb_url,
                full_url=f"{PHOTO_URL}/pht/{photo_hash}.jpg",
                date_label=date_label.strip(),
            ))
        return photos

    def get_photo_gallery(self, photo_id: str) -> list[str]:
        """
        Fetch full-resolution photo URLs for a specific gallery entry.

        Args:
            photo_id: The gallery ID from a PhotoSnapshot.photo_id.

        Returns:
            List of full-resolution JPEG URLs.
        """
        url = f"{PHOTO_URL}/gallery.php?id={photo_id}&l={self.language}"
        html = self._get(url, extra_headers={"Referer": f"{BASE_URL}/"})

        # data-src contains full-res URLs (without leading underscore)
        return re.findall(
            r'data-src="(https://photo\.skylinewebcams\.com/pht/[a-f0-9]+\.jpg)"',
            html
        )

    def download_photo(self, photo_url: str) -> bytes:
        """
        Download a photo by URL.

        Args:
            photo_url: URL from PhotoSnapshot.full_url or PhotoSnapshot.thumbnail_url.

        Returns:
            Raw JPEG bytes.
        """
        return _fetch_bytes(photo_url, timeout=self.timeout)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[WebcamInfo]:
        """
        Search for cameras by name / location keyword.

        Note: The site does not expose a proper search JSON API. This method
        fetches the main directory page and performs a case-insensitive
        substring match on camera names and descriptions. For a more complete
        result, consider crawling all country/category pages.

        Args:
            query: Search term, e.g. "venice", "beach", "volcano".

        Returns:
            List of WebcamInfo objects matching the query.
        """
        url = f"{BASE_URL}/{self.language}/webcam.html"
        html = self._get(url)
        cards = _extract_cam_cards(html)
        q = query.lower()
        results = []
        for c in cards:
            if q in c["name"].lower() or q in c["description"].lower():
                results.append(WebcamInfo(**{
                    k: v for k, v in c.items()
                    if k in WebcamInfo.__dataclass_fields__
                }))
        return results

    def search_by_category_and_country(
        self, category: str, country: str
    ) -> list[WebcamInfo]:
        """
        Find cameras matching both a category and a country.

        Fetches the category page and filters by country slug.

        Args:
            category: Category name or slug (see list_by_category()).
            country:  Country name or slug.

        Returns:
            Filtered list of WebcamInfo objects.
        """
        c_slug = self._country_slug(country)
        cams = self.list_by_category(category)
        return [c for c in cams if c_slug in (c.url or "")]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_countries(self) -> list[dict]:
        """
        Return all countries with their URL slugs by scraping the homepage nav.

        Returns:
            List of dicts with keys: name, slug, url.
        """
        html = self._get(f"{BASE_URL}/{self.language}.html")
        # Extract from the mega-menu
        entries = re.findall(
            r'<a href="/en/webcam/([a-z0-9-]+)\.html">([^<]+)</a>',
            html
        )
        results = []
        for slug, name in entries:
            # Filter out region-level links (they have slashes)
            if "/" not in slug:
                results.append({
                    "name": name.strip(),
                    "slug": slug,
                    "url": f"{BASE_URL}/{self.language}/webcam/{slug}.html",
                })
        return results

    def list_categories(self) -> list[dict]:
        """
        Return all available camera categories.

        Returns:
            List of dicts with keys: name, slug, url.
        """
        return [
            {
                "name": name.replace("-", " ").replace("cams", "cameras").title(),
                "slug": slug,
                "friendly": friendly,
                "url": f"{BASE_URL}/{self.language}/live-cams-category/{slug}.html",
            }
            for friendly, slug in CATEGORIES.items()
            if "-" in slug  # only include slug entries
        ]

    def get_embed_code(self, cam: WebcamInfo, width: int = 640, height: int = 360) -> str:
        """
        Generate an HTML iframe embed code for a camera.

        This replicates the standard embed pattern used by the site.

        Args:
            cam:    Camera info object.
            width:  Iframe width in pixels.
            height: Iframe height in pixels.

        Returns:
            HTML iframe string.
        """
        cam_url = cam.url or f"/en/webcam/{cam.country_slug}/{cam.region_slug}/{cam.city_slug}/{cam.cam_slug}.html"
        full_url = BASE_URL + cam_url if not cam_url.startswith("http") else cam_url
        return (
            f'<iframe src="{full_url}" '
            f'width="{width}" height="{height}" '
            'frameborder="0" allowfullscreen></iframe>'
        )

    def get_weather_url(self, country_slug: str, region_slug: str, city_slug: str) -> str:
        """
        Return the weather page URL for a location (page exists, returns 200).

        Args:
            country_slug: e.g. "italia"
            region_slug:  e.g. "veneto"
            city_slug:    e.g. "venezia"

        Returns:
            Full URL string.
        """
        return (
            f"{BASE_URL}/{self.language}/weather/"
            f"{country_slug}/{region_slug}/{city_slug}.html"
        )

    def get_nearby_cameras(self, cam: WebcamInfo) -> list[dict]:
        """
        Return cameras listed in the 'Nearby Webcams' tab on a camera page.

        Requires fetching the camera detail page. The nearby cameras are
        rendered server-side in the #tab_near section.

        Args:
            cam: Camera info object. If cam.url is set, uses that; otherwise
                 reconstructs the URL from slug fields.

        Returns:
            List of dicts with keys: url, name.
        """
        if cam.url:
            url = BASE_URL + cam.url if not cam.url.startswith("http") else cam.url
        else:
            url = (
                f"{BASE_URL}/{self.language}/webcam/"
                f"{cam.country_slug}/{cam.region_slug}/{cam.city_slug}/{cam.cam_slug}.html"
            )
        html = self._get(url)

        # Find the nearby section
        nearby_m = re.search(
            r'id="tab_near"(.*?)(?:</div>\s*</div>\s*</div>|id="tab_photo")',
            html, re.S
        )
        if not nearby_m:
            return []

        section = nearby_m.group(1)
        links = re.findall(
            r'<a href="(/[a-z]{2}/webcam/[^"]+\.html)"[^>]*>.*?<p[^>]*>([^<]+)</p>',
            section, re.S
        )
        return [{"url": BASE_URL + href, "name": name.strip()} for href, name in links]


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def get_stream_url(cam_page_path: str, language: str = "en") -> str:
    """
    Quick one-liner to get the HLS stream URL for a camera.

    Args:
        cam_page_path: Path portion of the camera URL, e.g.
                       "italia/veneto/venezia/piazza-san-marco"
        language:      Language code (default "en").

    Returns:
        HLS m3u8 URL string.

    Example:
        url = get_stream_url("italia/veneto/venezia/piazza-san-marco")
    """
    client = SkylineWebcamsClient(language=language)
    cam = client.get_camera(cam_page_path)
    return cam.hls_url


def get_thumbnail_url(cam_id: str, size: str = "live") -> str:
    """
    Quick one-liner to get thumbnail URL by camera ID.

    Args:
        cam_id: Numeric camera ID string.
        size:   "live" | "social" | "static"

    Returns:
        JPEG image URL.
    """
    client = SkylineWebcamsClient()
    return client.get_thumbnail_url(cam_id, size)


def search_cameras(query: str, language: str = "en") -> list[WebcamInfo]:
    """
    Quick search across all cameras.

    Args:
        query:    Search term.
        language: Language code.

    Returns:
        List of matching WebcamInfo objects.
    """
    client = SkylineWebcamsClient(language=language)
    return client.search(query)


# ---------------------------------------------------------------------------
# Example usage / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    client = SkylineWebcamsClient(language="en", request_delay=1.0)

    print("=" * 60)
    print("SkylineWebcams Client - Demo")
    print("=" * 60)

    # 1. HLS camera: Trevi Fountain, Rome
    print("\n[1] HLS camera: Trevi Fountain - Rome (cam_id=286)")
    cam = client.get_camera("italia/lazio/roma/fontana-di-trevi")
    print(f"  Name:         {cam.name}")
    print(f"  Camera ID:    {cam.cam_id}")
    print(f"  Stream type:  {cam.stream_type}")
    print(f"  Description:  {cam.description[:80]}")
    print(f"  Location:     {cam.country_slug} / {cam.region_slug} / {cam.city_slug}")
    print(f"  HLS URL:      {cam.hls_url}")
    print(f"  Thumbnail:    {cam.thumbnail_url}")
    print(f"  Social img:   {cam.social_image_url}")
    print(f"  Rating:       {cam.rating} ({cam.rating_count} ratings)")
    print(f"  Upload date:  {cam.upload_date}")

    # 2. YouTube camera: Times Square, New York
    print("\n[2] YouTube camera: Times Square - New York (cam_id=538)")
    yt_cam = client.get_camera("united-states/new-york/new-york/times-square")
    print(f"  Name:            {yt_cam.name}")
    print(f"  Camera ID:       {yt_cam.cam_id}")
    print(f"  Stream type:     {yt_cam.stream_type}")
    print(f"  YouTube video:   {yt_cam.youtube_video_id}")
    print(f"  YouTube URL:     {yt_cam.youtube_url}")
    print(f"  YouTube embed:   {yt_cam.youtube_embed_url}")
    print(f"  Thumbnail:       {yt_cam.thumbnail_url}")

    # 3. Live stats
    print("\n[3] Live stats for Trevi Fountain (cam 286)")
    stats = client.get_stats(cam.cam_id)
    print(f"  Total views:     {stats.total_views}")
    print(f"  Current viewers: {stats.current_viewers}")

    # 4. HLS playlist
    print("\n[4] HLS playlist segments (live stream)")
    try:
        segments = client.get_stream_segments(cam)
        if segments:
            for i, seg in enumerate(segments[:3], 1):
                print(f"  Segment {i}: {seg}")
        else:
            print("  (stream offline or empty playlist)")
    except Exception as e:
        print(f"  Error: {e}")

    # 5. Time-lapse URL
    print("\n[5] Time-lapse HLS URL for Trevi Fountain")
    try:
        tl_url = client.get_timelapse_url("italia/lazio/roma/fontana-di-trevi")
        print(f"  Timelapse URL: {tl_url}")
    except Exception as e:
        print(f"  Error: {e}")

    # 6. List Italian cameras
    print("\n[6] Italian cameras (first 5)")
    italy_cams = client.list_by_country("italy")
    for c in italy_cams[:5]:
        print(f"  [{c.cam_id}] {c.name}")
        print(f"       URL: {c.url}")

    # 7. Category - Volcanoes
    print("\n[7] Volcano cameras (first 5)")
    volcano_cams = client.list_by_category("volcanoes")
    for c in volcano_cams[:5]:
        print(f"  [{c.cam_id}] {c.name}")

    # 8. Top cameras
    print("\n[8] Top cameras (first 5)")
    top = client.list_top_cameras()
    for c in top[:5]:
        print(f"  [{c.cam_id}] {c.name}")

    # 9. Photos archive
    print("\n[9] Archive photos for Trevi Fountain (first 3)")
    photos = client.get_photos(cam.cam_id)
    for p in photos[:3]:
        print(f"  ID: {p.photo_id} | {p.date_label}")
        print(f"    Thumb: {p.thumbnail_url}")
        print(f"    Full:  {p.full_url}")

    # 10. Countries list
    print("\n[10] Available countries (first 10)")
    countries = client.list_countries()
    for c in countries[:10]:
        print(f"  {c['name']:25} → slug: {c['slug']}")

    # 11. Thumbnail URLs
    print("\n[11] Thumbnail URL patterns for cam 286 (Trevi Fountain)")
    print(f"  Live:   {client.get_thumbnail_url('286', 'live')}")
    print(f"  Social: {client.get_thumbnail_url('286', 'social')}")
    print(f"  Static: {client.get_thumbnail_url('286', 'static')}")

    # 12. Nearby cameras
    print("\n[12] Nearby cameras for Trevi Fountain")
    nearby = client.get_nearby_cameras(cam)
    for n in nearby[:5]:
        print(f"  {n['name']} → {n['url']}")

    print("\nDone!")
