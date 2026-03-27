"""
HDOnTap API Client
==================
Reverse-engineered client for https://www.hdontap.com

HDOnTap hosts 200+ live HD webcams covering wildlife (eagles, falcons, owls,
wolves, bison), beaches, scenic views, airports, aquariums, and more.

API Architecture
----------------
- Base URL: https://hdontap.com
- Main REST API: /api/  (Django REST Framework, paginated)
- Live HLS CDN: https://live.hdontap.com
- Snapshot CDN: https://portal.hdontap.com/snapshot/<stream_name>
- Timelapse: https://timelapse.hdontap.com/embed/<timelapse_id>
- Storage CDN: https://storage.hdontap.com

Key Endpoints (all public, no auth required for GET)
------------------------------------------------------
GET /api/streams/                   List all streams (paginated, 203 total)
GET /api/streams/{short_uuid}/      Stream detail with metadata
GET /api/streams/{short_uuid}/play/ Get fresh signed HLS URL (expires ~12h)
GET /api/tags/                      List all tags (276 total)
GET /api/categories/                List all categories (10 total)
GET /search/?q={query}              Search streams (HTML, redirects)
GET /explore/tag/{tag_slug}/        Browse by tag (HTML)

Filtering parameters for /api/streams/:
  ?tag={slug}            Filter by tag slug (e.g. eagles, beaches, surf)
  ?category={slug}       Filter by category slug (e.g. birds, animals)
  ?search={query}        Full-text search
  ?is_live=true          Only live streams
  ?is_live=false         Only offline streams
  ?ordering={field}      Sort by field (e.g. -viewer_count, title)
  ?page={n}              Pagination (1-based)
  ?page_size={n}         Results per page (observed max: 250+)

HLS Stream URL Format
---------------------
Unsigned (403 without token):
  https://live.hdontap.com/hls/{server}/{stream_name}.stream/playlist.m3u8

Signed (works, ~12h expiry):
  https://live.hdontap.com/hls/{server}/...playlist.m3u8?t={token}&e={unix_ts}

  Token parameter: t=  HMAC-based signed token
  Expiry parameter: e= Unix epoch timestamp (approximately 12 hours from issue)

DVR/time-shift streams:
  https://live.hdontap.com/hls/hosbdvr6/{name}.stream/playlist.m3u8?DVR&t=...&e=...
  (note the ?DVR before the token params)

Wowza servers observed:
  hosb1       - primary east-coast server
  hosb3       - primary east-coast server (largest pool)
  hosb4       - secondary server
  hosb6lo     - 6th generation lower-bitrate
  hosb6na     - 6th generation North America
  hosbdvr6    - DVR/time-shift capable server

Master playlist quality variants (example):
  #EXT-X-STREAM-INF:BANDWIDTH=434284,CODECS="avc1.640029,mp4a.40.2",RESOLUTION=1280x720
  chunklist.m3u8?e=...&eh=edge01.virginia.nginx.hdontap.com&t=...

Multi-cam streams use ngrp: prefix in stream name, e.g.:
  ngrp:hdontap_hanover-eagles_pov-mux.stream_all

Snapshot URL Format
-------------------
  https://portal.hdontap.com/snapshot/{stream_embed_id}
  Returns a live JPEG thumbnail, no auth required.
  The embed_id is found in the player-data element as `portalEmbedId`.

  Also available from storage CDN (updated every ~30s):
  https://storage.hdontap.com/wowza_stream_thumbnails/snapshot_{server}_{name}.jpg

  Static snapshots (fixed images):
  https://storage.hdontap.com/static_snapshots/{filename}.png

Embed / Widget URL Format
--------------------------
  https://hdontap.com/stream/{short_uuid}/{slug}/embed/

  Some streams return a YouTube iframe embed; others return the VideoJS/Wowza
  player. Determined by player_type field in stream detail.

  The embed page accepts no query parameters for stream selection.
  Authentication-gated partner embeds use:
  https://portal.hdontap.com/s/embed/{portal_embed_id}

Timelapse Format
----------------
  Embed page: https://timelapse.hdontap.com/embed/{timelapse_id}
  Embed with date: https://timelapse.hdontap.com/embed/{timelapse_id}/{YYYY-MM-DD}
  The timelapse_id is an internal integer, different from stream short_uuid.
  It can be found from the /stream/{id}/tl-player/ page HTML.

Authentication
--------------
  All list/detail/play/tags/categories endpoints are unauthenticated (GET).
  POST endpoints require Django session cookie + X-CSRFToken header:
    POST /api/follow-stream/     Follow a stream (requires login)
    POST /stream/{id}/snapshot/  Upload a user snapshot (requires login)

Player Data JSON
----------------
  The stream page embeds a JSON blob in <script id="player-data"> containing:
    streamSrc, previews[], overlay{}, sharing{}, ads{}, discovery{},
    weatherWidget{}, timelapses[], streamTimeout{}, toolbarLogo{}

  This is the same data returned by the /play/ API endpoint's `settings` field.
"""

import re
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Iterator
from urllib.parse import urljoin, urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://hdontap.com"
API_BASE = "https://hdontap.com/api"
LIVE_CDN = "https://live.hdontap.com/hls"
STORAGE_CDN = "https://storage.hdontap.com"
PORTAL_BASE = "https://portal.hdontap.com"
TIMELAPSE_BASE = "https://timelapse.hdontap.com"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Tag:
    id: int
    name: str
    slug: str
    primary: bool
    icon: Optional[str] = None
    icon_dark_mode: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Tag":
        return cls(
            id=d["id"],
            name=d["name"],
            slug=d["slug"],
            primary=d.get("primary", False),
            icon=d.get("icon"),
            icon_dark_mode=d.get("icon_dark_mode"),
        )


@dataclass
class Category:
    id: int
    name: str
    slug: str
    image: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Category":
        return cls(
            id=d["id"],
            name=d["name"],
            slug=d["slug"],
            image=d.get("image"),
        )


@dataclass
class StreamSummary:
    """Lightweight stream info returned from list endpoints."""
    id: int
    short_uuid: str          # 6-digit identifier used in all public URLs
    title: str
    card_title: str
    slug: str
    location_display: str
    viewer_count: int
    thumbnail_url: str
    is_live: bool
    is_new: bool
    is_featured: Optional[bool]
    curated: bool
    tags: list[Tag] = field(default_factory=list)
    category: Optional[Category] = None

    @classmethod
    def from_dict(cls, d: dict) -> "StreamSummary":
        return cls(
            id=d.get("id", 0),
            short_uuid=d["short_uuid"],
            title=d["title"],
            card_title=d.get("card_title", d["title"]),
            slug=d.get("slug", ""),
            location_display=d.get("location_display", ""),
            viewer_count=d.get("viewer_count", 0),
            thumbnail_url=d.get("thumbnail_url", ""),
            is_live=d.get("is_live", False),
            is_new=d.get("is_new", False),
            is_featured=d.get("is_featured"),
            curated=d.get("curated", False),
            tags=[Tag.from_dict(t) for t in d.get("tags", [])],
            category=Category.from_dict(d["category"]) if d.get("category") else None,
        )

    @property
    def url(self) -> str:
        return f"{BASE_URL}/stream/{self.short_uuid}/{self.slug}/"

    def __repr__(self) -> str:
        status = "LIVE" if self.is_live else "offline"
        return (
            f"Stream({self.short_uuid}: {self.title!r} "
            f"[{self.location_display}] {status} {self.viewer_count}v)"
        )


@dataclass
class StreamDetail(StreamSummary):
    """Full stream detail including HLS URL and description."""
    description_text: str = ""
    contextual_description: str = ""
    player_type: str = "hls"
    stream_url: Optional[str] = None    # Unsigned URL (403 without token)
    fallback_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "StreamDetail":
        base = StreamSummary.from_dict(d)
        return cls(
            **{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()
               if hasattr(base, f.name)},
            description_text=d.get("description_text", ""),
            contextual_description=d.get("contextual_description", ""),
            player_type=d.get("player_type", "hls"),
            stream_url=d.get("stream_url"),
            fallback_url=d.get("fallback_url"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


@dataclass
class PlayData:
    """Response from /api/streams/{id}/play/ - includes signed HLS URL."""
    stream_url: str          # Signed URL with token + expiry
    player_type: str         # "hls" or "youtube"
    settings: dict = field(default_factory=dict)

    @property
    def expires_at(self) -> Optional[int]:
        """Unix timestamp when the token expires (from 'e=' query param)."""
        m = re.search(r"[?&]e=(\d+)", self.stream_url)
        return int(m.group(1)) if m else None

    @property
    def is_expired(self) -> bool:
        exp = self.expires_at
        return exp is not None and time.time() > exp

    @property
    def preview_urls(self) -> list[dict]:
        """Alternative camera angles (multi-cam streams)."""
        return self.settings.get("previews", [])

    @property
    def weather(self) -> Optional[dict]:
        return self.settings.get("weatherWidget")

    @classmethod
    def from_dict(cls, d: dict) -> "PlayData":
        return cls(
            stream_url=d["stream_url"],
            player_type=d.get("player_type", "hls"),
            settings=d.get("settings", {}),
        )


# ---------------------------------------------------------------------------
# Low-level HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, params: Optional[dict] = None, timeout: int = 15) -> bytes:
    """Perform a simple GET request, return raw bytes."""
    if params:
        url = url + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": DEFAULT_UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body[:200]}") from e
    except URLError as e:
        raise RuntimeError(f"Network error fetching {url}: {e.reason}") from e


def _get_json(url: str, params: Optional[dict] = None, timeout: int = 15) -> dict | list:
    return json.loads(_get(url, params, timeout))


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class HDOnTapClient:
    """
    Public API client for HDOnTap.com

    All endpoints are public (no API key required).
    Signed HLS tokens are obtained on demand and cached until expiry.

    Example usage
    -------------
    >>> client = HDOnTapClient()
    >>> streams = client.list_streams(tag="eagles")
    >>> for s in streams:
    ...     print(s)
    ...
    >>> play = client.get_play_url("204942")
    >>> print(play.stream_url)    # signed HLS URL
    >>> print(play.preview_urls)  # other camera angles

    >>> # Stream with ffplay
    >>> import subprocess
    >>> subprocess.run(["ffplay", play.stream_url])
    """

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._play_cache: dict[str, PlayData] = {}

    # ------------------------------------------------------------------
    # Streams
    # ------------------------------------------------------------------

    def list_streams(
        self,
        *,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        is_live: Optional[bool] = None,
        ordering: Optional[str] = None,
        page_size: int = 100,
    ) -> list[StreamSummary]:
        """
        Return all streams matching the given filters.

        Automatically pages through all results.

        Parameters
        ----------
        tag : str, optional
            Tag slug, e.g. 'eagles', 'beaches', 'surf', '4kUltraHD',
            'animals', 'birds', 'scenic', 'resorts', 'action'
        category : str, optional
            Category slug: 'eagles', 'birds', 'animals', 'beaches',
            'scenic', 'resorts', 'action', 'other', 'owls', 'raptors'
        search : str, optional
            Free-text search across titles and descriptions.
        is_live : bool, optional
            If True, only return currently live streams.
        ordering : str, optional
            Field to sort by. Prefix with '-' for descending.
            Options: viewer_count, title, created_at, updated_at
        page_size : int
            Results per page (max 250). Default 100.
        """
        params: dict = {"page_size": page_size}
        if tag:
            params["tag"] = tag
        if category:
            params["category"] = category
        if search:
            params["search"] = search
        if is_live is not None:
            params["is_live"] = "true" if is_live else "false"
        if ordering:
            params["ordering"] = ordering

        results: list[StreamSummary] = []
        url = f"{self.base_url}/api/streams/"
        while url:
            data = _get_json(url, params if results == [] else None)
            for item in data.get("results", []):
                results.append(StreamSummary.from_dict(item))
            url = data.get("next")

        return results

    def iter_streams(
        self,
        *,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        is_live: Optional[bool] = None,
        ordering: Optional[str] = "-viewer_count",
        page_size: int = 100,
    ) -> Iterator[StreamSummary]:
        """Lazy iterator over all matching streams (one page at a time)."""
        params: dict = {"page_size": page_size}
        if tag:
            params["tag"] = tag
        if category:
            params["category"] = category
        if search:
            params["search"] = search
        if is_live is not None:
            params["is_live"] = "true" if is_live else "false"
        if ordering:
            params["ordering"] = ordering

        url: Optional[str] = f"{self.base_url}/api/streams/"
        first = True
        while url:
            data = _get_json(url, params if first else None)
            first = False
            for item in data.get("results", []):
                yield StreamSummary.from_dict(item)
            url = data.get("next")

    def get_stream(self, stream_id: str) -> StreamDetail:
        """
        Fetch full stream detail.

        Parameters
        ----------
        stream_id : str
            The 6-digit short UUID, e.g. '204942' for Hanover Eagles.
            Also accepts numeric strings like '93143' (zero-padded to 6).
        """
        url = f"{self.base_url}/api/streams/{stream_id}/"
        return StreamDetail.from_dict(_get_json(url))

    def get_play_url(
        self,
        stream_id: str,
        *,
        use_cache: bool = True,
    ) -> PlayData:
        """
        Get a fresh signed HLS URL for a stream.

        The signed URL includes a token (`t=`) and expiry timestamp (`e=`).
        Tokens are valid for approximately 1 hour.

        Parameters
        ----------
        stream_id : str
            The 6-digit short UUID, e.g. '204942'
        use_cache : bool
            If True, return cached token if still valid. Default True.

        Returns
        -------
        PlayData
            Contains stream_url (signed HLS), player_type, and settings
            (weather, multi-cam previews, overlay config, etc.)

        Notes
        -----
        For multi-cam streams, `play_data.preview_urls` lists alternative
        camera angles, each with its own signed URL.

        For YouTube-backed streams, player_type='youtube' and stream_url
        is a YouTube embed URL.
        """
        if use_cache and stream_id in self._play_cache:
            cached = self._play_cache[stream_id]
            if not cached.is_expired:
                return cached

        url = f"{self.base_url}/api/streams/{stream_id}/play/"
        data = _get_json(url)
        play = PlayData.from_dict(data)
        self._play_cache[stream_id] = play
        return play

    # ------------------------------------------------------------------
    # Tags and categories
    # ------------------------------------------------------------------

    def list_tags(self, primary_only: bool = False) -> list[Tag]:
        """
        List all available tags (276 total).

        Primary tags (shown in UI nav):
          4kUltraHD, Action, Animals, Beaches, Birds, Eagles,
          Resorts, Scenic, Surf

        Parameters
        ----------
        primary_only : bool
            If True, return only primary/featured tags.
        """
        results: list[Tag] = []
        url = f"{self.base_url}/api/tags/"
        while url:
            data = _get_json(url)
            for item in data.get("results", []):
                tag = Tag.from_dict(item)
                if not primary_only or tag.primary:
                    results.append(tag)
            url = data.get("next")
        return results

    def list_categories(self) -> list[Category]:
        """
        List all categories (10 total):
        Action, Animals, Beaches, Birds, Eagles, Other, Owls, Raptors,
        Resorts, Scenic
        """
        data = _get_json(f"{self.base_url}/api/categories/")
        return [Category.from_dict(c) for c in data.get("results", [])]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[StreamSummary]:
        """
        Search streams by keyword.

        Uses the REST API's search filter which matches against title,
        description, and location fields.
        """
        return self.list_streams(search=query)

    # ------------------------------------------------------------------
    # Thumbnails and snapshots
    # ------------------------------------------------------------------

    def get_live_snapshot(self, portal_embed_id: str) -> str:
        """
        Return the URL for a live snapshot image from a stream.

        The portal_embed_id is found in the stream page's `portalEmbedId`
        field (e.g. 'hdontap_hanover-eagles-4k-MUX_Multicam').

        Returns a JPEG image URL at:
          https://portal.hdontap.com/snapshot/{portal_embed_id}

        This image is refreshed every ~30 seconds on the CDN.
        """
        return f"{PORTAL_BASE}/snapshot/{portal_embed_id}"

    def get_thumbnail_url(self, stream: StreamSummary) -> str:
        """Return the CDN thumbnail URL for a stream."""
        return stream.thumbnail_url

    # ------------------------------------------------------------------
    # Timelapse
    # ------------------------------------------------------------------

    def get_timelapse_embed_url(
        self,
        timelapse_id: int,
        date: Optional[str] = None,
    ) -> str:
        """
        Return the iframe embed URL for a stream's timelapse recording.

        Parameters
        ----------
        timelapse_id : int
            Internal timelapse integer ID. Found from the
            /stream/{id}/tl-player/ page HTML.
            Example: 1025 for Hanover Eagles.
        date : str, optional
            Date string 'YYYY-MM-DD'. Defaults to today's recording.

        Returns
        -------
        str
            URL to embed or fetch for timelapse data.
        """
        base = f"{TIMELAPSE_BASE}/embed/{timelapse_id}"
        if date:
            return f"{base}/{date}"
        return base

    def get_timelapse_dates(self, timelapse_id: int) -> list[str]:
        """
        Fetch available timelapse recording dates for a stream.

        Parameters
        ----------
        timelapse_id : int
            Internal timelapse ID.

        Returns
        -------
        list[str]
            List of available date paths like '1025/2026-03-26'.
        """
        url = f"{TIMELAPSE_BASE}/embed/{timelapse_id}"
        html = _get(url).decode("utf-8", errors="replace")
        dates_match = re.search(r"var DATES = (\{.+?\});", html, re.DOTALL)
        if not dates_match:
            return []
        try:
            raw = dates_match.group(1).replace("&nbsp;", " ")
            dates_dict = json.loads(raw)
            return list(dates_dict.values())
        except json.JSONDecodeError:
            return []

    # ------------------------------------------------------------------
    # Stream page helpers
    # ------------------------------------------------------------------

    def get_stream_page_url(self, stream_id: str, slug: str = "") -> str:
        """Return the canonical page URL for a stream."""
        if slug:
            return f"{self.base_url}/stream/{stream_id}/{slug}/"
        return f"{self.base_url}/stream/{stream_id}/"

    def get_embed_url(self, stream_id: str, slug: str = "") -> str:
        """Return the embed URL for a stream (iframe src)."""
        base = self.get_stream_page_url(stream_id, slug)
        return f"{base}embed/"

    def get_snapshot_gallery_url(self, stream_id: str, slug: str = "") -> str:
        """Return the snapshot gallery page URL."""
        base = self.get_stream_page_url(stream_id, slug)
        return f"{base}snapshot-gallery/"

    # ------------------------------------------------------------------
    # Convenience: category-based browsing
    # ------------------------------------------------------------------

    def get_eagle_cams(self) -> list[StreamSummary]:
        """Return all eagle nest / raptor cams."""
        return self.list_streams(tag="eagles")

    def get_falcon_cams(self) -> list[StreamSummary]:
        """Return all falcon / peregrine cams."""
        return self.list_streams(search="falcon")

    def get_beach_cams(self) -> list[StreamSummary]:
        """Return all beach cams."""
        return self.list_streams(tag="beaches")

    def get_underwater_cams(self) -> list[StreamSummary]:
        """Return underwater / aquarium cams."""
        return self.list_streams(search="underwater aquarium kelp")

    def get_wildlife_cams(self) -> list[StreamSummary]:
        """Return wildlife / animal cams."""
        return self.list_streams(tag="animals")

    def get_airport_cams(self) -> list[StreamSummary]:
        """Return airport cams."""
        return self.list_streams(search="airport")

    def get_4k_cams(self) -> list[StreamSummary]:
        """Return 4K Ultra HD cams."""
        return self.list_streams(tag="4kUltraHD")

    def get_live_streams(self, ordering: str = "-viewer_count") -> list[StreamSummary]:
        """Return all currently live streams, sorted by viewer count."""
        return self.list_streams(is_live=True, ordering=ordering)

    def get_most_popular(self, n: int = 20) -> list[StreamSummary]:
        """Return the top N streams by current viewer count."""
        streams = self.list_streams(ordering="-viewer_count", page_size=n)
        return streams[:n]


# ---------------------------------------------------------------------------
# HLS URL utilities
# ---------------------------------------------------------------------------

def extract_hls_qualities(m3u8_content: str) -> list[dict]:
    """
    Parse an HLS master playlist and return quality variants.

    Parameters
    ----------
    m3u8_content : str
        Content of the master .m3u8 playlist.

    Returns
    -------
    list[dict]
        Each dict has: bandwidth, resolution, codecs, url
    """
    variants = []
    lines = m3u8_content.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = {}
            for part in line[len("#EXT-X-STREAM-INF:"):].split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    attrs[k.strip()] = v.strip().strip('"')
            if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                attrs["url"] = lines[i + 1]
                variants.append(attrs)
                i += 2
                continue
        i += 1
    return variants


def get_hls_quality_url(m3u8_content: str, quality: str = "best") -> Optional[str]:
    """
    Select an HLS quality variant URL.

    Parameters
    ----------
    m3u8_content : str
        Master playlist content.
    quality : str
        One of: 'best', 'worst', '4k', '1080p', '720p', '360p'

    Returns
    -------
    str or None
        The variant playlist URL for the requested quality.
    """
    variants = extract_hls_qualities(m3u8_content)
    if not variants:
        return None

    # Sort by bandwidth
    variants_sorted = sorted(
        variants,
        key=lambda v: int(v.get("BANDWIDTH", 0)),
        reverse=True,
    )

    quality_map = {
        "best": variants_sorted[0],
        "worst": variants_sorted[-1],
        "4k": next((v for v in variants_sorted if "3840" in v.get("RESOLUTION", "")), None),
        "1080p": next((v for v in variants_sorted if "1920" in v.get("RESOLUTION", "")), None),
        "720p": next((v for v in variants_sorted if "1280" in v.get("RESOLUTION", "")), None),
        "360p": next((v for v in variants_sorted if "640" in v.get("RESOLUTION", "")), None),
    }

    selected = quality_map.get(quality)
    return selected["url"] if selected else None


# ---------------------------------------------------------------------------
# CLI / demo
# ---------------------------------------------------------------------------

def demo():
    """Quick demo of the client."""
    client = HDOnTapClient()

    print("=" * 70)
    print("HDOnTap API Client Demo")
    print("=" * 70)

    # Most popular streams
    print("\n[Top 10 Most-Watched Streams]")
    top = client.get_most_popular(10)
    for s in top:
        status = "LIVE" if s.is_live else "offline"
        tag_names = ", ".join(t.slug for t in s.tags[:3])
        print(f"  {s.short_uuid}  {s.viewer_count:4d}v  [{status}]  {s.title}")
        print(f"            {s.location_display}  |  tags: {tag_names}")

    # Eagle cams
    print("\n[Eagle Cams]")
    eagle_cams = client.get_eagle_cams()
    for s in eagle_cams:
        status = "LIVE" if s.is_live else "offline"
        print(f"  {s.short_uuid}  {s.viewer_count:4d}v  [{status}]  {s.title}")

    # Get HLS URL for first live stream
    live = [s for s in top if s.is_live]
    if live:
        stream = live[0]
        print(f"\n[Getting HLS URL for: {stream.title}]")
        play = client.get_play_url(stream.short_uuid)
        print(f"  Stream URL: {play.stream_url[:80]}...")
        exp = play.expires_at
        if exp:
            remaining = int(exp - time.time())
            print(f"  Token expires in: {remaining // 60}m {remaining % 60}s")
        print(f"  Player type: {play.player_type}")
        if play.preview_urls:
            print(f"  Camera angles: {len(play.preview_urls)}")
            for i, p in enumerate(play.preview_urls):
                print(f"    [{i}] {p.get('url', '')[:80]}...")

    # Categories
    print("\n[Categories]")
    cats = client.list_categories()
    for c in cats:
        print(f"  {c.id:3d}  {c.slug:15s}  {c.name}")

    # Primary tags
    print("\n[Primary Tags]")
    tags = client.list_tags(primary_only=True)
    for t in tags:
        print(f"  {t.id:3d}  {t.slug:20s}  {t.name}")

    # Search example
    print("\n[Search: 'underwater']")
    results = client.search("underwater")
    for s in results[:5]:
        print(f"  {s.short_uuid}  {s.title}  [{s.location_display}]")


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        client = HDOnTapClient()

        if cmd == "list":
            # hdontap_client.py list [tag]
            tag = sys.argv[2] if len(sys.argv) > 2 else None
            streams = client.list_streams(tag=tag, ordering="-viewer_count")
            for s in streams:
                status = "LIVE" if s.is_live else "    "
                print(f"{s.short_uuid}  {s.viewer_count:5d}v  {status}  {s.title}")

        elif cmd == "play":
            # hdontap_client.py play 204942
            stream_id = sys.argv[2]
            play = client.get_play_url(stream_id)
            if play.player_type == "youtube":
                print(f"YouTube stream: {play.stream_url}")
            else:
                print(play.stream_url)
                # Try to fetch and show quality variants
                try:
                    m3u8 = _get(play.stream_url).decode()
                    qualities = extract_hls_qualities(m3u8)
                    if qualities:
                        print("\nQuality variants:")
                        for q in qualities:
                            print(f"  {q.get('RESOLUTION', '?'):12s}  "
                                  f"{int(q.get('BANDWIDTH', 0)) // 1000:6d}k  "
                                  f"{q.get('url', '')[:60]}")
                except Exception as e:
                    print(f"(Could not fetch playlist: {e})")

        elif cmd == "search":
            # hdontap_client.py search falcon
            query = " ".join(sys.argv[2:])
            results = client.search(query)
            for s in results:
                print(f"{s.short_uuid}  {s.title}  [{s.location_display}]")

        elif cmd == "detail":
            # hdontap_client.py detail 204942
            stream_id = sys.argv[2]
            s = client.get_stream(stream_id)
            print(f"Title:     {s.title}")
            print(f"ID:        {s.short_uuid} (internal: {s.id})")
            print(f"Location:  {s.location_display}")
            print(f"Live:      {s.is_live}  ({s.viewer_count} viewers)")
            print(f"URL:       {s.url}")
            print(f"Thumbnail: {s.thumbnail_url}")
            tags = ", ".join(t.slug for t in s.tags)
            print(f"Tags:      {tags}")
            if s.category:
                print(f"Category:  {s.category.name}")

        elif cmd == "demo":
            demo()

        elif cmd == "tags":
            tags = client.list_tags(primary_only="--primary" in sys.argv)
            for t in tags:
                prim = "*" if t.primary else " "
                print(f"{prim} {t.id:4d}  {t.slug:30s}  {t.name}")

        else:
            print(f"Unknown command: {cmd}")
            print("Usage: hdontap_client.py [list|play|search|detail|demo|tags] [args...]")
            sys.exit(1)
    else:
        demo()
