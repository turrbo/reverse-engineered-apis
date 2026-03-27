"""
Skiresort.info Webcam System Client
====================================
Reverse-engineered Python client for the Skiresort.info webcam platform.

Discovered via analysis of:
  - https://www.skiresort.info/weather/webcams/
  - JavaScript bundle: /typo3conf/ext/mg_site/Resources/Public/Release/20260324pokwx/jsFooterV3.gz.js
  - Network patterns on resort webcam detail pages
  - skiresort-service.com CDN endpoint structure

Key findings:
  - Site is powered by TYPO3 CMS (skiresort.info and skiresort-service.com)
  - Webcam images are served from https://www.skiresort-service.com/typo3temp/_processed_/_cams_/
  - Live status JSON: https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/status2.json
  - Archive index JSON: https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/archive2.json
  - Archive images: https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/{YYYY}/{MM}/{DD}/{HH_MM}.jpg
  - Archive thumbnails: same path but filename prefixed with "preview_"
  - Resort lists with webcams: /weather/webcams/{country}/ajaxlist.json
  - Pagination: /weather/webcams/{country}/page/{N}/ (50 resorts per page)
  - Feratel live streams: https://webtv.feratel.com/webtv/?design=v5&pg={guid}&cam={id}
  - Feratel thumbnails: https://wtvthmb.feratel.com/thumbnails/{cam_id}.jpeg
  - Snow report teasers: /index.php?eID=mg_skiresort_snowreportteaser&uid={uid}&l=en&type={type}
  - 1696+ resorts worldwide with webcams, 6573+ individual webcam feeds

Webcam Folder Types (data-folder attribute) and image filename patterns:
  - feratel_livestream   : livestream_37_{id}.jpg  — Feratel live video streams (most common in Alps)
  - panomax_webcams      : panomax_reduced{id}.jpg  — Panomax 360-degree panoramic webcams
  - itwms_webcams_images : itwms_{hash}.jpg         — ITWMS static webcam images (hash, not predictable)
  - webcams              : webcam_{id}.jpg           — Direct/standalone webcam images
  - youtube_livestreams  : youtube_{video_id}.jpg   — YouTube live stream thumbnails
  - roundshot_webcams    : roundshot_{id}.jpg        — Roundshot 360° panoramas
  - webcamera_webcams    : webcamera_{id}.jpg        — Webcamera.pl feeds (Poland etc.)

Usage:
    client = SkiresortWebcamClient()

    # List all resorts with webcams
    resorts = client.list_resorts_with_webcams()

    # List resorts by country
    austria_resorts = client.list_resorts_by_country("austria")

    # Get webcams for a specific resort
    webcams = client.get_resort_webcams("kitzski-kitzbuehel-kirchberg")

    # Get webcam live status
    status = client.get_webcam_status("feratel_livestream", "146")

    # Get webcam image URL
    image_url = client.get_webcam_image_url("feratel_livestream", "146")

    # Get feratel live stream URL
    stream_url = client.get_feratel_stream_url("5604")

    # Search resorts
    results = client.search_resorts("kitzbuhel")
"""

import re
import json
import time
import logging
from typing import Optional, Dict, List, Any, Generator
from urllib.parse import urlencode, quote
from html import unescape

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.parse

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants & Discovered Endpoints
# ---------------------------------------------------------------------------

BASE_URL = "https://www.skiresort.info"
SERVICE_BASE_URL = "https://www.skiresort-service.com"
FERATEL_WEBTV_BASE = "https://webtv.feratel.com/webtv"
FERATEL_THUMB_BASE = "https://wtvthmb.feratel.com/thumbnails"

# Image CDN patterns (skiresort-service.com)
# webcam image: /typo3temp/_processed_/_cams_/livestream_37_{id}.jpg
# webcam image: /typo3temp/_processed_/_cams_/webcam_{id}.jpg
# webcam image: /typo3temp/_processed_/_cams_/itwms_{hash}.jpg
WEBCAM_IMAGE_CDN = f"{SERVICE_BASE_URL}/typo3temp/_processed_/_cams_"

# Archive/status endpoint
# GET /typo3temp/_processed_/cams_archive/{folder}/{id}/status2.json
# Returns: {"status": {"live_available": bool, "isOld": bool, "last_thumbnail_success": int}}
# GET /typo3temp/_processed_/cams_archive/{folder}/{id}/archive2.json
# Returns: {"archive": {"YYYY": {"MM": {"DD": [{"resort_timestamp":int,"server_timestamp":int,"filename":"YYYY/MM/DD/HH_MM.jpg"},...]}}},"status":{...}}
# Archive image: /typo3temp/_processed_/cams_archive/{folder}/{id}/{filename_from_archive}
# Archive thumbnail (smaller): /typo3temp/_processed_/cams_archive/{folder}/{id}/{YYYY}/{MM}/{DD}/preview_{HH_MM}.jpg
WEBCAM_STATUS_ENDPOINT = f"{SERVICE_BASE_URL}/typo3temp/_processed_/cams_archive"

# AJAX list endpoint for resorts with webcams
# GET /weather/webcams/{country}/ajaxlist.json[?tx_mgskiresort_pi1[resortlist][sword]=QUERY]
# Returns: {"content": "<html>", "visible": [resort_id, ...], "pagebrowser_pageinfo_from": N, "pagebrowser_pageinfo_to": M}
WEBCAM_LIST_AJAX = f"{BASE_URL}/weather/webcams"

# TYPO3 eID endpoints
# Snow report teaser: /index.php?eID=mg_skiresort_snowreportteaser&uid={uid}&l=en&type={type}
SNOW_REPORT_TEASER_EID = f"{BASE_URL}/index.php"

# Feratel live stream
# https://webtv.feratel.com/webtv/?design=v5&pg={page_guid}&cam={cam_id}
# Feratel thumbnail:
# https://wtvthmb.feratel.com/thumbnails/{cam_id}.jpeg?t=38&dcsdesign=WTP_skiresort.de&design=v5

# Region taxonomy used in URL paths
CONTINENTS = {
    "europe": "Europe",
    "north-america": "North America",
    "south-america": "South America",
    "asia": "Asia",
    "australia-and-oceania": "Australia and Oceania",
    "africa": "Africa",
}

# Countries discovered from the regions JSON on the weather/webcams page
COUNTRIES = [
    "albania", "algeria", "andorra", "argentina", "armenia", "australia",
    "austria", "azerbaijan", "bahrain", "belarus", "belgium",
    "bosnia-and-herzegovina", "brazil", "bulgaria", "canada", "chile",
    "china", "croatia", "cyprus", "czech-republic", "denmark", "egypt",
    "estonia", "finland", "france", "georgia", "germany", "greece",
    "hungary", "iceland", "india", "iran", "ireland", "israel", "italy",
    "japan", "jordan", "kazakhstan", "kyrgyzstan", "latvia", "lebanon",
    "liechtenstein", "lithuania", "luxembourg", "macedonia", "mexico",
    "moldova", "monaco", "mongolia", "montenegro", "morocco", "nepal",
    "netherlands", "new-zealand", "north-korea", "norway", "pakistan",
    "peru", "poland", "portugal", "romania", "russia", "san-marino",
    "saudi-arabia", "serbia", "slovakia", "slovenia", "south-korea",
    "spain", "sweden", "switzerland", "tajikistan", "turkey", "ukraine",
    "united-arab-emirates", "united-kingdom", "united-states", "uzbekistan",
]

# Mountain ranges discovered from regions JSON
MOUNTAIN_RANGES = [
    "alps", "andes", "apennine-mountains-appennini", "appalachian-mountains",
    "atlas-mountains", "black-forest-schwarzwald", "carpathian-mountains-karpaty",
    "caucasus-mountains", "central-uplands-of-germany-deutsche-mittelgebirge",
    "dinaric-alps", "french-massif-central", "great-dividing-range",
    "himalayas", "japanese-alps", "jura-mountains-massif-du-jura",
    "new-zealand-alps", "pacific-coast-ranges", "pyrenees", "rocky-mountains",
    "scandinavian-mountains", "sierra-nevada", "tatra-mountains",
    "turkish-mountains",
]

# Webcam folder types
WEBCAM_FOLDER_TYPES = {
    "feratel_livestream": "Feratel Live Stream",
    "panomax_webcams": "Panomax 360° Panoramic",
    "itwms_webcams_images": "ITWMS Static Image",
    "webcams": "Standard Webcam",
    "youtube_livestreams": "YouTube Live Stream",
    "roundshot_webcams": "Roundshot 360° Panorama",
    "webcamera_webcams": "Webcamera.pl Feed",
}

# Maps folder type to current image filename prefix on CDN
# Full URL: {WEBCAM_IMAGE_CDN}/{prefix}_{id}.jpg
# Exception: itwms uses a hash (must read from HTML data-src), youtube uses video ID
FOLDER_IMAGE_PREFIXES = {
    "feratel_livestream": "livestream_37",
    "panomax_webcams": "panomax_reduced",
    "webcams": "webcam",
    "youtube_livestreams": "youtube",
    "roundshot_webcams": "roundshot",
    "webcamera_webcams": "webcamera",
    # itwms_webcams_images uses an MD5 hash derived from source URL (not predictable)
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
}

AJAX_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


# ---------------------------------------------------------------------------
# HTTP Session Helper
# ---------------------------------------------------------------------------

class SkiresortSession:
    """Manages HTTP sessions with retry logic and rate limiting."""

    def __init__(self, rate_limit_delay: float = 1.0, max_retries: int = 3):
        self.delay = rate_limit_delay
        self._last_request = 0.0

        if HAS_REQUESTS:
            self.session = requests.Session()
            retry = Retry(
                total=max_retries,
                backoff_factor=1.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
            self.session.headers.update(DEFAULT_HEADERS)
        else:
            self.session = None

    def _throttle(self):
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.time()

    def get(self, url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None,
            as_json: bool = False) -> Any:
        """GET request with throttling."""
        self._throttle()
        merged_headers = {**DEFAULT_HEADERS, **(headers or {})}

        if HAS_REQUESTS:
            resp = self.session.get(url, headers=merged_headers, params=params, timeout=30)
            resp.raise_for_status()
            if as_json:
                return resp.json()
            return resp.text
        else:
            # Fallback to urllib
            if params:
                url = url + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=merged_headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", errors="replace")
            if as_json:
                return json.loads(raw)
            return raw


# ---------------------------------------------------------------------------
# Data Parsers
# ---------------------------------------------------------------------------

def _parse_webcam_block(block_html: str) -> Dict:
    """Parse a single webcam block from HTML into structured data."""
    webcam = {}

    # data-folder and data-id
    folder_m = re.search(r'data-folder=["\']([^"\']+)["\']', block_html)
    id_m = re.search(r'data-id=["\']([^"\']+)["\']', block_html)
    if folder_m:
        webcam["folder"] = folder_m.group(1)
    if id_m:
        webcam["id"] = id_m.group(1)

    # Timezone info
    tz_m = re.search(r'data-resort-timezone=["\']([^"\']+)["\']', block_html)
    if tz_m:
        try:
            webcam["timezone"] = json.loads(unescape(tz_m.group(1)))
        except Exception:
            pass

    # Label (Live stream, Webcam, etc.)
    label_m = re.search(r'class="webcam-detail-label"[^>]*>([^<]+)', block_html)
    if label_m:
        webcam["label"] = label_m.group(1).strip()

    # Name (location/description)
    name_m = re.search(r'class="webcam-detail-name"[^>]*>.*?<span[^>]*>(.*?)</span>', block_html, re.DOTALL)
    if name_m:
        webcam["name"] = re.sub(r'<[^>]+>', '', name_m.group(1)).strip()

    # Image URL (thumbnail)
    img_m = re.search(r'data-src=["\']([^"\']+)["\']', block_html)
    img_mobile_m = re.search(r'data-src-mobile=["\']([^"\']+)["\']', block_html)
    if img_m:
        webcam["image_url"] = img_m.group(1)
    if img_mobile_m:
        webcam["image_url_mobile"] = img_mobile_m.group(1)

    # Alt text
    alt_m = re.search(r'\balt=["\']([^"\']*)["\']', block_html)
    if alt_m:
        webcam["alt_text"] = alt_m.group(1)

    # Detail page URL
    href_m = re.search(r'href=["\']([^"\']*skiresort\.info/ski-resort/[^"\']+/webcams/wcf\d+/)["\']', block_html)
    if href_m:
        webcam["detail_url"] = href_m.group(1)

    # Element id (e.g. "wferatel146")
    eid_m = re.search(r'\bid=["\']w([a-z_]+?)(\d+)["\']', block_html)
    if eid_m:
        webcam["element_id"] = f"w{eid_m.group(1)}{eid_m.group(2)}"

    # Derive image URL from folder/id pattern
    if "folder" in webcam and "id" in webcam:
        webcam["cdn_image_url"] = _build_cdn_image_url(webcam["folder"], webcam["id"])
        webcam["status_url"] = _build_status_url(webcam["folder"], webcam["id"])

    # Detect live stream type
    label = webcam.get("label", "").lower()
    webcam["is_live_stream"] = "live stream" in label or "livestream" in label
    webcam["is_360"] = "360" in label

    return webcam


def _parse_resort_list_content(html_content: str) -> List[Dict]:
    """
    Parse the HTML content from ajaxlist.json response.
    Returns list of resort objects with webcam information.
    """
    resorts = []

    # Split by resort-list-item divs
    # Each resort has class: panel panel-default resort-list-item webcam-gallery
    items = re.split(r'(?=<div class="panel panel-default resort-list-item)', html_content)

    for item in items:
        if 'resort-list-item' not in item:
            continue

        resort = {}

        # Resort name and URL
        name_link = re.search(
            r'href="(https://www\.skiresort\.info/ski-resort/([^/]+)/webcams/)"[^>]*class="h3"[^>]*>([^<]+)',
            item
        )
        if not name_link:
            name_link = re.search(
                r'class="h3"[^>]*>\s*<a href="(https://www\.skiresort\.info/ski-resort/([^/]+)/webcams/)"[^>]*>([^<]+)',
                item
            )
        if name_link:
            resort["webcam_list_url"] = name_link.group(1)
            resort["slug"] = name_link.group(2)
            resort["name"] = name_link.group(3).strip()

        # Webcam count
        count_m = re.search(r'(\d+)\s*\n?\s*Webcams?', item)
        if count_m:
            resort["webcam_count"] = int(count_m.group(1))

        # Breadcrumb location info
        breadcrumb = re.search(r'class="sub-breadcrumb"[^>]*>(.*?)</div>', item, re.DOTALL)
        if breadcrumb:
            links = re.findall(r'href="[^"]*webcams/([^/"]+)/"[^>]*>([^<]+)', breadcrumb.group(1))
            resort["location_breadcrumb"] = [{"slug": s, "name": n} for s, n in links]

        # Snow conditions (if shown in listing)
        snow_base = re.search(r'data-snow-base=["\']([^"\']+)["\']', item)
        snow_top = re.search(r'data-snow-top=["\']([^"\']+)["\']', item)
        if snow_base:
            resort["snow_base_cm"] = snow_base.group(1)
        if snow_top:
            resort["snow_top_cm"] = snow_top.group(1)

        # Preview webcam images in listing
        preview_imgs = re.findall(r'data-src=["\']([^"\']+skiresort-service\.com[^"\']+)["\']', item)
        if preview_imgs:
            resort["preview_images"] = list(dict.fromkeys(preview_imgs))  # deduplicate

        # Webcam folder/id pairs in the listing
        folder_ids = re.findall(r'data-folder=["\']([^"\']+)["\'][^>]*data-id=["\']([^"\']+)["\']', item)
        if folder_ids:
            resort["webcam_previews"] = [
                {"folder": f, "id": i, "cdn_image_url": _build_cdn_image_url(f, i)}
                for f, i in folder_ids
            ]

        if resort.get("slug"):
            resorts.append(resort)

    return resorts


def _parse_resort_webcam_page(html_content: str, resort_slug: str) -> Dict:
    """
    Parse a resort's dedicated webcam page.
    Returns full webcam listing with all metadata.
    """
    result = {
        "resort_slug": resort_slug,
        "resort_url": f"{BASE_URL}/ski-resort/{resort_slug}/",
        "webcams_url": f"{BASE_URL}/ski-resort/{resort_slug}/webcams/",
        "webcams": [],
    }

    # Split webcam sections by 'webcam-preview' divs
    # Use regex to find all webcam containers
    webcam_pattern = re.compile(
        r'<div class="(?:webcam-preview|swiper-in-overview-con-wrapper) webcam[^"]*"[^>]*data-folder=["\']([^"\']+)["\'][^>]*data-id=["\']([^"\']+)["\'].*?(?=<div class="(?:webcam-preview|swiper-in-overview-con-wrapper)|$)',
        re.DOTALL
    )

    seen_ids = set()
    for m in webcam_pattern.finditer(html_content):
        block = m.group(0)
        folder = m.group(1)
        cam_id = m.group(2)
        key = f"{folder}/{cam_id}"
        if key in seen_ids:
            continue
        seen_ids.add(key)
        webcam = _parse_webcam_block(block)
        result["webcams"].append(webcam)

    # Resort name
    title_m = re.search(r'<h1[^>]*>([^<]+)</h1>', html_content)
    if title_m:
        result["resort_name"] = title_m.group(1).strip()

    # Location/breadcrumb
    breadcrumb_items = re.findall(
        r'<li[^>]*class="[^"]*breadcrumb[^"]*"[^>]*>.*?href="([^"]+)"[^>]*>([^<]+)',
        html_content,
        re.DOTALL
    )
    if breadcrumb_items:
        result["breadcrumb"] = [{"url": u, "name": n.strip()} for u, n in breadcrumb_items]

    # Webcam count from page
    count_m = re.search(r'(\d+)\s*Webcams?\s', html_content)
    if count_m:
        result["total_webcam_count"] = int(count_m.group(1))

    return result


def _parse_webcam_detail_page(html_content: str) -> Dict:
    """
    Parse a single webcam detail page.
    Returns the webcam metadata including live stream URL if available.
    """
    webcam = {}

    # Extract hidden metadata divs
    hidden_divs = re.findall(r'id="([^"]+)"\s+data-value="([^"]*)"', html_content)
    meta = {hd[0]: unescape(hd[1]) for hd in hidden_divs}

    webcam["webcam_id"] = meta.get("webcamId")
    webcam["folder"] = meta.get("webcamFolderName")
    webcam["archive_domain"] = meta.get("webcamArchiveDomain", SERVICE_BASE_URL)

    # Live URL
    live_url_raw = meta.get("webcamLiveURL", "")
    if live_url_raw:
        webcam["live_stream_url"] = unescape(live_url_raw)
        webcam["is_live"] = True
    else:
        webcam["is_live"] = False

    # Webcam ratio
    ratio = meta.get("webcamRatio", "0")
    webcam["aspect_ratio"] = ratio

    # Live fullscreen support
    webcam["live_fullscreen"] = meta.get("webcamLiveFullscreen", "false").lower() == "true"

    # Timezone
    tz_raw = meta.get("webcamResortTimezone", "{}")
    try:
        webcam["timezone"] = json.loads(tz_raw)
    except Exception:
        webcam["timezone"] = {}

    # Feratel-specific: extract cam ID from live URL
    if webcam.get("live_stream_url"):
        feratel_cam_m = re.search(r'cam=(\d+)', webcam["live_stream_url"])
        feratel_pg_m = re.search(r'pg=([^&]+)', webcam["live_stream_url"])
        if feratel_cam_m:
            webcam["feratel_cam_id"] = feratel_cam_m.group(1)
            webcam["feratel_thumbnail_url"] = (
                f"{FERATEL_THUMB_BASE}/{feratel_cam_m.group(1)}.jpeg"
                "?t=38&dcsdesign=WTP_skiresort.de&design=v5"
            )
        if feratel_pg_m:
            webcam["feratel_page_guid"] = feratel_pg_m.group(1)

    # CDN image URL
    if webcam.get("folder") and webcam.get("webcam_id"):
        webcam["cdn_image_url"] = _build_cdn_image_url(webcam["folder"], webcam["webcam_id"])
        webcam["status_url"] = _build_status_url(webcam["folder"], webcam["webcam_id"])

    # Webcam name/title from h1/h2
    title_m = re.search(r'<h[12][^>]*>([^<]+)</h[12]>', html_content)
    if title_m:
        webcam["title"] = title_m.group(1).strip()

    # Resort info from breadcrumb
    resort_link = re.search(
        r'href="(https://www\.skiresort\.info/ski-resort/([^/]+)/webcams/)"',
        html_content
    )
    if resort_link:
        webcam["resort_webcams_url"] = resort_link.group(1)
        webcam["resort_slug"] = resort_link.group(2)

    # Image from page
    img_m = re.search(r'data-src=["\']([^"\']*wtvthmb\.feratel\.com[^"\']+)["\']', html_content)
    if not img_m:
        img_m = re.search(r'data-src=["\']([^"\']*skiresort-service\.com[^"\']+)["\']', html_content)
    if img_m:
        webcam["current_image_url"] = img_m.group(1)

    return webcam


# ---------------------------------------------------------------------------
# URL Builders
# ---------------------------------------------------------------------------

def _build_cdn_image_url(folder: str, cam_id: str) -> str:
    """
    Build the CDN image URL for a webcam.

    Patterns discovered (verified by HTTP HEAD requests):
      - feratel_livestream   -> /typo3temp/_processed_/_cams_/livestream_37_{id}.jpg
      - panomax_webcams      -> /typo3temp/_processed_/_cams_/panomax_reduced{id}.jpg
      - itwms_webcams_images -> /typo3temp/_processed_/_cams_/itwms_{md5hash}.jpg  (hash not predictable from ID)
      - webcams              -> /typo3temp/_processed_/_cams_/webcam_{id}.jpg
      - youtube_livestreams  -> /typo3temp/_processed_/_cams_/youtube_{youtube_video_id}.jpg
      - roundshot_webcams    -> /typo3temp/_processed_/_cams_/roundshot_{id}.jpg
      - webcamera_webcams    -> /typo3temp/_processed_/_cams_/webcamera_{id}.jpg

    Note: For itwms_webcams_images, the cam_id is an internal integer ID but the
    image filename uses an MD5 hash of the source URL. Pass the hash as cam_id
    if you have it from parsing the HTML data-src attribute.
    For youtube_livestreams, the cam_id in data-id is the internal ID but the
    image filename uses the actual YouTube video ID (e.g., 'dMr-Jt_K3Cc').
    Pass the YouTube video ID as cam_id if you have it from data-src parsing.
    """
    prefix = FOLDER_IMAGE_PREFIXES.get(folder)
    if prefix:
        return f"{WEBCAM_IMAGE_CDN}/{prefix}_{cam_id}.jpg"
    # itwms_webcams_images: hash is required, cam_id must be the hash
    elif folder == "itwms_webcams_images":
        return f"{WEBCAM_IMAGE_CDN}/itwms_{cam_id}.jpg"
    else:
        # Unknown folder type: best guess
        return f"{WEBCAM_IMAGE_CDN}/{folder}_{cam_id}.jpg"


def _build_status_url(folder: str, cam_id: str) -> str:
    """Build the status2.json URL for a webcam."""
    return f"{WEBCAM_STATUS_ENDPOINT}/{folder}/{cam_id}/status2.json"


def _build_resort_webcam_url(resort_slug: str) -> str:
    """Build the webcam listing URL for a resort."""
    return f"{BASE_URL}/ski-resort/{resort_slug}/webcams/"


def _build_webcam_detail_url(resort_slug: str, cam_id: str) -> str:
    """Build the detail page URL for a specific webcam."""
    return f"{BASE_URL}/ski-resort/{resort_slug}/webcams/wcf{cam_id}/"


def _build_archive_json_url(folder: str, cam_id: str) -> str:
    """Build the archive2.json URL for a webcam."""
    return f"{WEBCAM_STATUS_ENDPOINT}/{folder}/{cam_id}/archive2.json"


def _build_archive_image_url(folder: str, cam_id: str, filename: str, thumbnail: bool = False) -> str:
    """
    Build URL for a specific archived webcam image.

    Args:
        folder: Webcam folder type.
        cam_id: Webcam ID.
        filename: Relative path from archive2.json entry, e.g. "2026/03/27/11_31.jpg".
        thumbnail: If True, returns the smaller preview version.

    Returns:
        Full HTTPS URL.

    The archive stores one image per 90-minute interval during daylight.
    Filenames are in "YYYY/MM/DD/HH_MM.jpg" format (local resort time).
    Preview (thumbnail) versions live at: .../YYYY/MM/DD/preview_HH_MM.jpg
    """
    clean = filename.replace("\\", "")
    if thumbnail:
        parts = clean.rsplit("/", 1)
        if len(parts) == 2:
            clean = f"{parts[0]}/preview_{parts[1]}"
    return f"{WEBCAM_STATUS_ENDPOINT}/{folder}/{cam_id}/{clean}"


def _build_feratel_stream_url(cam_id: str, page_guid: str = "", design: str = "v5") -> str:
    """Build a Feratel live stream URL."""
    params = f"design={design}"
    if page_guid:
        params += f"&pg={page_guid}"
    params += f"&cam={cam_id}"
    return f"{FERATEL_WEBTV_BASE}/?{params}"


def _build_feratel_thumbnail_url(cam_id: str) -> str:
    """Build a Feratel thumbnail URL."""
    return f"{FERATEL_THUMB_BASE}/{cam_id}.jpeg?t=38&dcsdesign=WTP_skiresort.de&design=v5"


def _build_webcam_list_url(geography: Optional[str] = None, page: int = 1, ajax: bool = False) -> str:
    """
    Build the URL for the webcam resort listing.

    Args:
        geography: Country slug, continent slug, or mountain range slug.
                   None for worldwide.
        page: Page number (50 resorts per page).
        ajax: If True, append ajaxlist.json for JSON response.

    Examples:
        /weather/webcams/                          (all, HTML)
        /weather/webcams/austria/                  (Austria, HTML)
        /weather/webcams/austria/page/2/           (Austria page 2, HTML)
        /weather/webcams/austria/ajaxlist.json     (Austria all, JSON)
        /weather/webcams/alps/ajaxlist.json        (Alps, JSON)
    """
    base = WEBCAM_LIST_AJAX
    if geography:
        base = f"{base}/{geography}"
    if page > 1:
        base = f"{base}/page/{page}"
    if ajax:
        base = f"{base}/ajaxlist.json"
    else:
        base = f"{base}/"
    return base


# ---------------------------------------------------------------------------
# Main Client
# ---------------------------------------------------------------------------

class SkiresortWebcamClient:
    """
    Python client for the Skiresort.info webcam system.

    All methods use discovered REST-like endpoints. No official API key required.
    Rate limiting is applied automatically (default: 1 request/second).
    """

    def __init__(self, rate_limit_delay: float = 1.0, max_retries: int = 3):
        """
        Initialize the client.

        Args:
            rate_limit_delay: Seconds between requests (default: 1.0).
            max_retries: Max HTTP retries on transient errors (default: 3).
        """
        self.session = SkiresortSession(rate_limit_delay, max_retries)
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Resort Listing
    # ------------------------------------------------------------------

    def list_resorts_with_webcams(
        self,
        geography: Optional[str] = None,
        page: int = 1,
    ) -> Dict:
        """
        List ski resorts that have webcams.

        Uses the ajaxlist.json endpoint which returns JSON with HTML content
        and a list of visible resort IDs.

        Args:
            geography: Optional country/continent/mountain range slug.
                       Examples: "austria", "europe", "alps", "united-states"
                       None returns worldwide results (1696+ resorts).
            page: Page number. Each page contains ~50 resorts.

        Returns:
            Dict with:
                - resorts: List[Dict] parsed resort objects
                - from: First result index
                - to: Last result index
                - total_visible: Total number of resort IDs in this filter
                - visible_ids: List of resort ID integers

        Example:
            >>> client = SkiresortWebcamClient()
            >>> result = client.list_resorts_with_webcams("austria")
            >>> print(result["total_visible"])  # 291
        """
        url = _build_webcam_list_url(geography, page, ajax=True)
        self.logger.debug(f"Fetching: {url}")

        data = self.session.get(url, headers=AJAX_HEADERS, as_json=True)

        resorts = _parse_resort_list_content(data.get("content", ""))

        return {
            "resorts": resorts,
            "from": data.get("pagebrowser_pageinfo_from", 1),
            "to": data.get("pagebrowser_pageinfo_to"),
            "total_visible": len(data.get("visible", [])),
            "visible_ids": data.get("visible", []),
            "geography": geography,
            "page": page,
            "ajax_url": url,
        }

    def list_resorts_by_country(self, country: str, page: int = 1) -> Dict:
        """
        List ski resorts with webcams for a specific country.

        Args:
            country: Country slug (e.g., "austria", "france", "united-states")

        Returns:
            Same structure as list_resorts_with_webcams().
        """
        return self.list_resorts_with_webcams(geography=country, page=page)

    def list_resorts_by_continent(self, continent: str, page: int = 1) -> Dict:
        """
        List ski resorts with webcams for a continent.

        Args:
            continent: Continent slug (e.g., "europe", "north-america", "asia")

        Returns:
            Same structure as list_resorts_with_webcams().
        """
        return self.list_resorts_with_webcams(geography=continent, page=page)

    def list_resorts_by_mountain_range(self, range_slug: str, page: int = 1) -> Dict:
        """
        List ski resorts with webcams for a mountain range.

        Args:
            range_slug: Mountain range slug (e.g., "alps", "rocky-mountains")

        Returns:
            Same structure as list_resorts_with_webcams().
        """
        return self.list_resorts_with_webcams(geography=range_slug, page=page)

    def iterate_all_resorts(
        self,
        geography: Optional[str] = None,
        max_pages: int = 100,
    ) -> Generator[Dict, None, None]:
        """
        Generator that paginates through all resorts with webcams.

        Args:
            geography: Optional country/continent/range slug.
            max_pages: Safety limit on number of pages (default: 100).

        Yields:
            Individual resort Dict objects.

        Example:
            >>> for resort in client.iterate_all_resorts("austria"):
            ...     print(resort["name"])
        """
        for page_num in range(1, max_pages + 1):
            result = self.list_resorts_with_webcams(geography=geography, page=page_num)
            resorts = result.get("resorts", [])

            if not resorts:
                break

            for resort in resorts:
                yield resort

            # Check if we've reached the end
            page_to = result.get("to")
            total = result.get("total_visible", 0)
            if page_to and page_to >= total:
                break

    def search_resorts(self, query: str, geography: Optional[str] = None) -> List[Dict]:
        """
        Search for ski resorts by name.

        Uses the filter parameter: tx_mgskiresort_pi1[resortlist][sword]

        Args:
            query: Search term (resort name, partial name, etc.)
            geography: Optional geographic filter.

        Returns:
            List of matching resort Dicts.

        Example:
            >>> results = client.search_resorts("kitzbuhel")
            >>> print(results[0]["name"])  # "KitzSki – Kitzbühel/Kirchberg"
        """
        base_url = _build_webcam_list_url(geography, ajax=True)
        params = {"tx_mgskiresort_pi1[resortlist][sword]": query}
        url = base_url + "?" + urlencode(params)

        data = self.session.get(url, headers=AJAX_HEADERS, as_json=True)
        return _parse_resort_list_content(data.get("content", ""))

    # ------------------------------------------------------------------
    # Resort Webcams
    # ------------------------------------------------------------------

    def get_resort_webcams(self, resort_slug: str) -> Dict:
        """
        Get all webcams for a specific ski resort.

        Fetches the resort's dedicated webcam page and extracts all webcam data.

        Args:
            resort_slug: Resort URL slug (e.g., "kitzski-kitzbuehel-kirchberg")

        Returns:
            Dict with:
                - resort_slug: str
                - resort_name: str
                - webcams_url: str
                - webcams: List[Dict] containing webcam data
                - total_webcam_count: int

        Example:
            >>> webcams = client.get_resort_webcams("kitzski-kitzbuehel-kirchberg")
            >>> for cam in webcams["webcams"]:
            ...     print(cam["name"], cam["image_url"])
        """
        url = _build_resort_webcam_url(resort_slug)
        html = self.session.get(url)
        return _parse_resort_webcam_page(html, resort_slug)

    def get_webcam_detail(self, resort_slug: str, cam_id: str) -> Dict:
        """
        Get detailed information about a specific webcam.

        Fetches the webcam's detail page (wcf{id} URL) for full metadata
        including live stream URL, feratel IDs, and archive domain.

        Args:
            resort_slug: Resort URL slug.
            cam_id: Webcam ID number (e.g., "146", "41").

        Returns:
            Dict with:
                - webcam_id: str
                - folder: str (e.g., "feratel_livestream")
                - title: str
                - live_stream_url: str (if available)
                - is_live: bool
                - cdn_image_url: str
                - status_url: str
                - feratel_cam_id: str (if Feratel webcam)
                - feratel_thumbnail_url: str (if Feratel webcam)
                - timezone: Dict
                - resort_slug: str

        Example:
            >>> detail = client.get_webcam_detail("kitzski-kitzbuehel-kirchberg", "146")
            >>> print(detail["live_stream_url"])
        """
        url = _build_webcam_detail_url(resort_slug, cam_id)
        html = self.session.get(url)
        return _parse_webcam_detail_page(html)

    # ------------------------------------------------------------------
    # Live Webcam Data
    # ------------------------------------------------------------------

    def get_webcam_status(self, folder: str, cam_id: str) -> Dict:
        """
        Get live status of a webcam.

        Endpoint: https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/status2.json

        Args:
            folder: Webcam folder type (e.g., "feratel_livestream", "panomax_webcams",
                    "itwms_webcams_images", "webcams")
            cam_id: Webcam ID.

        Returns:
            Dict with:
                - live_available: bool (True if live stream is active)
                - isOld: bool (True if image is outdated)
                - last_thumbnail_success: int (Unix timestamp of last successful image)
                - folder: str
                - cam_id: str
                - status_url: str

        Example:
            >>> status = client.get_webcam_status("feratel_livestream", "146")
            >>> print(status["live_available"])  # True
            >>> print(status["last_thumbnail_success"])  # 1774629093
        """
        url = _build_status_url(folder, cam_id)
        data = self.session.get(url, as_json=True)

        status = data.get("status", {})
        return {
            "live_available": status.get("live_available", False),
            "isOld": status.get("isOld", True),
            "last_thumbnail_success": status.get("last_thumbnail_success"),
            "folder": folder,
            "cam_id": cam_id,
            "status_url": url,
            "image_url": _build_cdn_image_url(folder, cam_id),
        }

    def get_webcam_image_url(self, folder: str, cam_id: str) -> str:
        """
        Get the direct image URL for a webcam.

        Images are refreshed automatically on the CDN.
        Add a cache-busting timestamp to always get the latest.

        Args:
            folder: Webcam folder type.
            cam_id: Webcam ID.

        Returns:
            CDN image URL string.

        Example:
            >>> url = client.get_webcam_image_url("feratel_livestream", "146")
            >>> # https://www.skiresort-service.com/typo3temp/_processed_/_cams_/livestream_37_146.jpg
        """
        return _build_cdn_image_url(folder, cam_id)

    def get_webcam_image_url_with_cache_bust(self, folder: str, cam_id: str) -> str:
        """Same as get_webcam_image_url but with cache-busting timestamp."""
        base = _build_cdn_image_url(folder, cam_id)
        return f"{base}?t={int(time.time())}"

    # ------------------------------------------------------------------
    # Webcam Archive
    # ------------------------------------------------------------------

    def get_webcam_archive(self, folder: str, cam_id: str) -> Dict:
        """
        Get the full historical archive listing for a webcam.

        Endpoint: https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/{folder}/{id}/archive2.json

        The archive contains one thumbnail per ~90-minute interval during daylight hours.
        Archives go back approximately 4+ months from the current date.

        Args:
            folder: Webcam folder type (e.g., "feratel_livestream", "webcams").
            cam_id: Webcam ID.

        Returns:
            Dict with keys:
              - archive: Nested dict {YYYY: {MM: {DD: [entry, ...]}}}
                Each entry: {"resort_timestamp": int, "server_timestamp": int, "filename": "YYYY/MM/DD/HH_MM.jpg"}
              - status: Same as status2.json response
              - archive_url: The URL this data was fetched from

        Example:
            >>> archive = client.get_webcam_archive("feratel_livestream", "146")
            >>> for year, months in archive["archive"].items():
            ...     for month, days in months.items():
            ...         for day, entries in days.items():
            ...             for entry in entries:
            ...                 print(entry["filename"])
        """
        url = _build_archive_json_url(folder, cam_id)
        data = self.session.get(url, as_json=True)
        if not isinstance(data, dict):
            return {"archive": {}, "status": {}, "archive_url": url}
        data["archive_url"] = url
        return data

    def get_archive_image_url(self, folder: str, cam_id: str, filename: str,
                               thumbnail: bool = False) -> str:
        """
        Build the URL for a specific archived image (no HTTP request needed).

        Args:
            folder: Webcam folder type.
            cam_id: Webcam ID.
            filename: Relative filename from archive2.json, e.g. "2026/03/27/11_31.jpg"
            thumbnail: If True, returns the smaller preview version.

        Returns:
            Full HTTPS URL to the archived JPEG.

        Example:
            >>> url = client.get_archive_image_url("feratel_livestream", "146", "2026/03/27/11_31.jpg")
            >>> # https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/2026/03/27/11_31.jpg
            >>> thumb = client.get_archive_image_url("feratel_livestream", "146", "2026/03/27/11_31.jpg", thumbnail=True)
            >>> # https://www.skiresort-service.com/typo3temp/_processed_/cams_archive/feratel_livestream/146/2026/03/27/preview_11_31.jpg
        """
        return _build_archive_image_url(folder, cam_id, filename, thumbnail)

    def get_latest_archive_image_url(self, folder: str, cam_id: str,
                                      thumbnail: bool = False) -> Optional[str]:
        """
        Get the URL of the most recently archived image.

        Makes one HTTP request to archive2.json.

        Args:
            folder: Webcam folder type.
            cam_id: Webcam ID.
            thumbnail: If True, returns the preview (thumbnail) version.

        Returns:
            URL string or None if no archive exists.
        """
        archive_data = self.get_webcam_archive(folder, cam_id)
        archive = archive_data.get("archive", {})
        if not archive:
            return None

        latest_filename = None
        for year in sorted(archive.keys(), reverse=True):
            for month in sorted(archive[year].keys(), reverse=True):
                for day in sorted(archive[year][month].keys(), reverse=True):
                    entries = archive[year][month][day]
                    if entries:
                        latest_filename = entries[-1]["filename"]
                    if latest_filename:
                        break
                if latest_filename:
                    break
            if latest_filename:
                break

        if not latest_filename:
            return None
        return _build_archive_image_url(folder, cam_id, latest_filename, thumbnail)

    def iter_archive_images(
        self,
        folder: str,
        cam_id: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        thumbnail: bool = False,
    ) -> Generator[Dict, None, None]:
        """
        Iterate over archived images for a webcam, optionally filtered by date.

        Args:
            folder: Webcam folder type.
            cam_id: Webcam ID.
            year: Optional filter by year (e.g., 2026).
            month: Optional filter by month (1-12).
            day: Optional filter by day (1-31).
            thumbnail: If True, yields thumbnail URLs instead of full-res.

        Yields:
            Dict with keys: resort_timestamp, server_timestamp, filename, image_url, thumbnail_url.
        """
        archive_data = self.get_webcam_archive(folder, cam_id)
        archive = archive_data.get("archive", {})

        years = [str(year)] if year else sorted(archive.keys())
        for y in years:
            if y not in archive:
                continue
            months = [str(month).zfill(2)] if month else sorted(archive[y].keys())
            for m in months:
                if m not in archive[y]:
                    continue
                days = [str(day).zfill(2)] if day else sorted(archive[y][m].keys())
                for d in days:
                    if d not in archive[y][m]:
                        continue
                    for entry in archive[y][m][d]:
                        fname = entry["filename"]
                        yield {
                            "resort_timestamp": entry["resort_timestamp"],
                            "server_timestamp": entry["server_timestamp"],
                            "filename": fname,
                            "image_url": _build_archive_image_url(folder, cam_id, fname, False),
                            "thumbnail_url": _build_archive_image_url(folder, cam_id, fname, True),
                        }

    def get_feratel_stream_url(
        self,
        cam_id: str,
        page_guid: str = "",
        design: str = "v5"
    ) -> str:
        """
        Build a Feratel live stream URL (does not require HTTP request).

        Args:
            cam_id: Feratel camera ID number (e.g., "5604").
            page_guid: Optional Feratel page GUID from webcam detail page.
            design: Stream design version (default: "v5").

        Returns:
            Full Feratel WebTV URL.

        Example:
            >>> url = client.get_feratel_stream_url("5604", "20F52598-D6F3-448C-A38B-EC5071B837EA")
            >>> # https://webtv.feratel.com/webtv/?design=v5&pg=20F52598-...&cam=5604
        """
        return _build_feratel_stream_url(cam_id, page_guid, design)

    def get_feratel_thumbnail_url(self, cam_id: str) -> str:
        """
        Get the Feratel live thumbnail URL.

        Args:
            cam_id: Feratel camera ID.

        Returns:
            Feratel thumbnail URL.
        """
        return _build_feratel_thumbnail_url(cam_id)

    # ------------------------------------------------------------------
    # Webcam Listing Page (HTML-based)
    # ------------------------------------------------------------------

    def get_webcam_listing_page(
        self,
        geography: Optional[str] = None,
        page: int = 1
    ) -> Dict:
        """
        Fetch the webcam listing page (HTML version).

        Extracts:
          - Featured webcam images
          - Region navigation (continents, countries, mountain ranges)
          - Pagination info

        Args:
            geography: Optional geographic slug.
            page: Page number.

        Returns:
            Dict with page metadata.
        """
        url = _build_webcam_list_url(geography, page, ajax=False)
        html = self.session.get(url)

        result = {
            "url": url,
            "geography": geography,
            "page": page,
        }

        # Extract region navigation from embedded JS
        regions_m = re.search(r'var regions = (\{.*?\});', html, re.DOTALL)
        if regions_m:
            try:
                # Find the full JSON
                start = html.find('var regions = ') + 14
                brace_count = 0
                in_string = False
                escaped = False
                end = start
                for i, ch in enumerate(html[start:], start):
                    if escaped:
                        escaped = False
                        continue
                    if ch == '\\':
                        escaped = True
                        continue
                    if ch == '"' and not escaped:
                        in_string = not in_string
                    if not in_string:
                        if ch == '{':
                            brace_count += 1
                        elif ch == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                regions_json = html[start:end]
                result["regions"] = json.loads(regions_json)
            except Exception as e:
                self.logger.warning(f"Could not parse regions JSON: {e}")

        return result

    def get_available_countries(self) -> List[Dict]:
        """
        Get list of all countries with ski resort webcams.

        Returns:
            List of Dicts with 'name' and 'url' keys.
        """
        page_data = self.get_webcam_listing_page()
        regions = page_data.get("regions", {})

        countries = []
        childs = regions.get("childs", {})
        for key, cat in childs.items():
            if cat.get("name") == "Countries":
                areas = cat.get("areas", {})
                for _, area in areas.items():
                    countries.append({
                        "name": area["name"].strip(),
                        "url": area["url"],
                        "slug": area["url"].rstrip("/").split("/")[-1],
                    })

        return sorted(countries, key=lambda x: x["name"])

    def get_available_continents(self) -> List[Dict]:
        """Get list of continents with ski resort webcams."""
        page_data = self.get_webcam_listing_page()
        regions = page_data.get("regions", {})

        continents = []
        childs = regions.get("childs", {})
        for key, cat in childs.items():
            if cat.get("name") == "Continents":
                areas = cat.get("areas", {})
                for _, area in areas.items():
                    continents.append({
                        "name": area["name"].strip(),
                        "url": area["url"],
                        "slug": area["url"].rstrip("/").split("/")[-1],
                    })

        return continents

    def get_available_mountain_ranges(self) -> List[Dict]:
        """Get list of mountain ranges with ski resort webcams."""
        page_data = self.get_webcam_listing_page()
        regions = page_data.get("regions", {})

        ranges = []
        childs = regions.get("childs", {})
        for key, cat in childs.items():
            if cat.get("name") == "Mountain ranges":
                areas = cat.get("areas", {})
                for _, area in areas.items():
                    ranges.append({
                        "name": area["name"].strip(),
                        "url": area["url"],
                        "slug": area["url"].rstrip("/").split("/")[-1],
                    })

        return ranges

    # ------------------------------------------------------------------
    # Snow Report
    # ------------------------------------------------------------------

    def get_snow_report_teaser(self, resort_uid: int, report_type: str = "snowreport") -> str:
        """
        Get the snow report teaser HTML for a resort.

        Endpoint: /index.php?eID=mg_skiresort_snowreportteaser&uid={uid}&l=en&type={type}

        Args:
            resort_uid: Internal resort UID (integer).
            report_type: Type of teaser ("snowreport" or "resortdata").

        Returns:
            HTML content string with snow report data.

        Note:
            Resort UIDs are found as data-uid attributes in the page HTML.
            The fe_snowreport_shown array in teaserOut JS variable contains UIDs.
        """
        params = {
            "eID": "mg_skiresort_snowreportteaser",
            "uid": resort_uid,
            "l": "en",
            "type": report_type,
        }
        url = f"{BASE_URL}/index.php?" + urlencode(params)
        return self.session.get(url)

    def get_snow_reports_list(
        self,
        country: str = "austria",
        sort: Optional[str] = None,
        filter_open: bool = False,
    ) -> Dict:
        """
        Get snow reports listing for a country.

        Discovered URL patterns:
          /snow-reports/{country}/
          /snow-reports/{country}/filter/open-ski-resorts/
          /snow-reports/{country}/sorted/mountain-snow-depths/
          /snow-reports/{country}/sorted/open-lifts/
          /snow-reports/{country}/sorted/open-slopes/
          /snow-reports/{country}/sorted/valley-snow-depths/

        Args:
            country: Country slug.
            sort: Sort option ("mountain-snow-depths", "open-lifts",
                  "open-slopes", "valley-snow-depths")
            filter_open: If True, filter to only open resorts.

        Returns:
            Dict with resorts and their snow data.
        """
        base = f"{BASE_URL}/snow-reports/{country}"
        if filter_open:
            url = f"{base}/filter/open-ski-resorts/ajaxlist.json"
        elif sort:
            url = f"{base}/sorted/{sort}/ajaxlist.json"
        else:
            url = f"{base}/ajaxlist.json"

        data = self.session.get(url, headers=AJAX_HEADERS, as_json=True)

        # Parse snow report listing
        content = data.get("content", "")
        resorts = []

        # Parse snow depths from content
        items = re.split(r'(?=<div class="panel panel-default resort-list-item)', content)
        for item in items:
            if 'resort-list-item' not in item:
                continue

            resort = {}

            # Name and URL
            name_m = re.search(
                r'href="(https://www\.skiresort\.info/ski-resort/([^/]+)/snow-report/)"[^>]*>([^<]+)',
                item
            )
            if name_m:
                resort["snow_report_url"] = name_m.group(1)
                resort["slug"] = name_m.group(2)
                resort["name"] = name_m.group(3).strip()

            # Snow depths
            for pattern, key in [
                (r'snowdepth-valley[^>]*>([^<]+)', "snow_depth_valley_cm"),
                (r'snowdepth-mountain[^>]*>([^<]+)', "snow_depth_mountain_cm"),
                (r'freshsnow[^>]*>([^<]+)', "fresh_snow_cm"),
            ]:
                m = re.search(pattern, item)
                if m:
                    resort[key] = m.group(1).strip()

            # Open lifts/slopes
            lifts_m = re.search(r'lifts-open[^>]*>(\d+)\s*/\s*(\d+)', item)
            if lifts_m:
                resort["lifts_open"] = int(lifts_m.group(1))
                resort["lifts_total"] = int(lifts_m.group(2))

            slopes_m = re.search(r'slopes-open[^>]*>(\d+)\s*/\s*(\d+)', item)
            if slopes_m:
                resort["slopes_open"] = int(slopes_m.group(1))
                resort["slopes_total"] = int(slopes_m.group(2))

            if resort.get("slug"):
                resorts.append(resort)

        return {
            "country": country,
            "resorts": resorts,
            "from": data.get("pagebrowser_pageinfo_from", 1),
            "to": data.get("pagebrowser_pageinfo_to"),
            "total": len(data.get("visible", [])),
        }

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------

    def download_webcam_image(self, folder: str, cam_id: str, output_path: str) -> bool:
        """
        Download the current webcam image to a file.

        Args:
            folder: Webcam folder type.
            cam_id: Webcam ID.
            output_path: Local file path to save image.

        Returns:
            True if successful.
        """
        url = _build_cdn_image_url(folder, cam_id)

        if HAS_REQUESTS:
            resp = self.session.session.get(url, timeout=30)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
            return False
        else:
            import urllib.request
            urllib.request.urlretrieve(url, output_path)
            return True

    def get_webcam_categories_for_resort(self, resort_slug: str) -> Dict[str, List[Dict]]:
        """
        Get webcams organized by category/type for a resort.

        Categories are derived from the webcam label field.

        Args:
            resort_slug: Resort URL slug.

        Returns:
            Dict mapping category name to list of webcams.
        """
        resort_data = self.get_resort_webcams(resort_slug)
        categories = {}

        for webcam in resort_data.get("webcams", []):
            label = webcam.get("label", "Unknown")
            if label not in categories:
                categories[label] = []
            categories[label].append(webcam)

        return categories

    @staticmethod
    def get_known_countries() -> List[str]:
        """Return the list of known country slugs."""
        return sorted(COUNTRIES)

    @staticmethod
    def get_known_continents() -> List[str]:
        """Return the list of continent slugs."""
        return sorted(CONTINENTS.keys())

    @staticmethod
    def get_known_mountain_ranges() -> List[str]:
        """Return the list of mountain range slugs."""
        return sorted(MOUNTAIN_RANGES)

    @staticmethod
    def get_webcam_folder_types() -> Dict[str, str]:
        """Return the webcam folder types and their descriptions."""
        return WEBCAM_FOLDER_TYPES.copy()

    @staticmethod
    def build_cdn_image_url(folder: str, cam_id: str) -> str:
        """Public wrapper for building CDN image URLs."""
        return _build_cdn_image_url(folder, cam_id)

    @staticmethod
    def build_status_url(folder: str, cam_id: str) -> str:
        """Public wrapper for building status2.json URLs."""
        return _build_status_url(folder, cam_id)

    @staticmethod
    def build_feratel_stream_url(cam_id: str, page_guid: str = "") -> str:
        """Public wrapper for building Feratel stream URLs."""
        return _build_feratel_stream_url(cam_id, page_guid)

    @staticmethod
    def build_archive_json_url(folder: str, cam_id: str) -> str:
        """Build the archive2.json URL for a webcam (no HTTP request)."""
        return _build_archive_json_url(folder, cam_id)

    @staticmethod
    def build_archive_image_url(folder: str, cam_id: str, filename: str,
                                 thumbnail: bool = False) -> str:
        """Build the URL for a specific archived image (no HTTP request)."""
        return _build_archive_image_url(folder, cam_id, filename, thumbnail)

    @staticmethod
    def extract_youtube_id(folder: str, image_url: str) -> Optional[str]:
        """
        Extract YouTube video ID from a youtube_livestreams webcam image URL.

        Args:
            folder: Should be "youtube_livestreams".
            image_url: The data-src image URL from the page.

        Returns:
            YouTube video ID (e.g., "dMr-Jt_K3Cc") or None.
        """
        if folder != "youtube_livestreams":
            return None
        m = re.search(r"youtube_([A-Za-z0-9_-]+)\.jpg", image_url or "")
        return m.group(1) if m else None


# ---------------------------------------------------------------------------
# CLI / Demo
# ---------------------------------------------------------------------------

def _demo():
    """Quick demonstration of the client."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    client = SkiresortWebcamClient(rate_limit_delay=1.5)

    print("=" * 60)
    print("Skiresort.info Webcam Client Demo")
    print("=" * 60)

    # 1. Webcam status for a known camera
    print("\n[1] Webcam Status (feratel_livestream/146 - Hahnenkamm, Kitzbühel)")
    status = client.get_webcam_status("feratel_livestream", "146")
    print(f"    Live available: {status['live_available']}")
    print(f"    Is old: {status['isOld']}")
    print(f"    Last success timestamp: {status['last_thumbnail_success']}")
    print(f"    Image URL: {status['image_url']}")

    # 2. List Austria resorts
    print("\n[2] Austria resorts with webcams (first page)")
    result = client.list_resorts_by_country("austria")
    print(f"    Total matching resorts: {result['total_visible']}")
    print(f"    Showing: {result['from']} - {result['to']}")
    if result["resorts"]:
        r = result["resorts"][0]
        print(f"    First resort: {r.get('name', 'N/A')}")
        print(f"    Webcam count: {r.get('webcam_count', 'N/A')}")
        print(f"    URL: {r.get('webcam_list_url', 'N/A')}")

    # 3. Get resort webcams
    print("\n[3] Webcams for KitzSki")
    resort_data = client.get_resort_webcams("kitzski-kitzbuehel-kirchberg")
    print(f"    Resort: {resort_data.get('resort_name', 'N/A')}")
    print(f"    Webcam count: {len(resort_data['webcams'])}")
    if resort_data["webcams"]:
        cam = resort_data["webcams"][0]
        print(f"    First cam: {cam.get('name', 'N/A')}")
        print(f"    Folder: {cam.get('folder', 'N/A')}")
        print(f"    Image URL: {cam.get('image_url', 'N/A')}")

    # 4. Search
    print("\n[4] Search for 'innsbruck'")
    results = client.search_resorts("innsbruck")
    print(f"    Found {len(results)} resorts")
    for r in results[:3]:
        print(f"    - {r.get('name', 'N/A')}")

    # 5. URL builders (no requests needed)
    print("\n[5] URL Examples")
    print(f"    Feratel stream: {_build_feratel_stream_url('5604', '20F52598-D6F3-448C-A38B-EC5071B837EA')}")
    print(f"    Feratel thumb: {_build_feratel_thumbnail_url('5604')}")
    print(f"    CDN image (feratel): {_build_cdn_image_url('feratel_livestream', '146')}")
    print(f"    CDN image (panomax): {_build_cdn_image_url('panomax_webcams', '659')}")
    print(f"    CDN image (youtube): {_build_cdn_image_url('youtube_livestreams', 'dMr-Jt_K3Cc')}")
    print(f"    CDN image (webcamera): {_build_cdn_image_url('webcamera_webcams', '309')}")
    print(f"    Status: {_build_status_url('feratel_livestream', '146')}")
    print(f"    Archive JSON: {_build_archive_json_url('feratel_livestream', '146')}")
    print(f"    Archive image: {_build_archive_image_url('feratel_livestream', '146', '2026/03/27/11_31.jpg')}")
    print(f"    Archive thumb: {_build_archive_image_url('feratel_livestream', '146', '2026/03/27/11_31.jpg', thumbnail=True)}")
    print(f"    Austria list (AJAX): {_build_webcam_list_url('austria', ajax=True)}")
    print(f"    Alps page 2: {_build_webcam_list_url('alps', page=2)}")

    # 6. Archive demo
    print("\n[6] Archive for feratel_livestream/30575 (webcams folder)")
    latest_url = client.get_latest_archive_image_url("webcams", "30575")
    if latest_url:
        print(f"    Latest archived image: {latest_url}")

    print("\n[7] YouTube webcam example (Big Sky Resort)")
    big_sky = client.get_resort_webcams("big-sky-resort")
    yt_cams = [c for c in big_sky.get("webcams", []) if c.get("folder") == "youtube_livestreams"]
    print(f"    YouTube live streams found: {len(yt_cams)}")
    for cam in yt_cams[:2]:
        yt_id = SkiresortWebcamClient.extract_youtube_id(cam.get("folder", ""), cam.get("image_url", ""))
        print(f"    - cam {cam.get('id')}: YouTube ID={yt_id}")
        if yt_id:
            print(f"      Embed: https://www.youtube.com/embed/{yt_id}")


if __name__ == "__main__":
    _demo()
