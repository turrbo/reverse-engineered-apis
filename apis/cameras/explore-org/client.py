"""
Explore.org Live Camera API Client
===================================
Reverse-engineered Python client for explore.org's live nature camera system.
Provides access to 232 wildlife/nature cameras across 15 categories.

Website:    https://explore.org/livecams
API Base:   https://omega.explore.org/api

Discovered 2026-03-27 via JS bundle analysis of /dist/app.js.

Quick Start
-----------
    from explore_org_client import ExploreOrgClient

    client = ExploreOrgClient()

    # Print full system summary
    print(client.summary())

    # List all live cameras
    for cam in client.get_live_cameras():
        print(cam.title, cam.youtube_watch_url)

    # Get cameras by category
    bear_cams = client.get_cameras_by_channel("Bears")
    africa_cams = client.get_cameras_by_channel("Africa")
    bird_cams = client.get_cameras_by_channel("Birds")

    # Get full details for a specific camera
    cam = client.get_camera_detail(199)   # Decorah Eagles
    print(cam)

    # Search
    results = client.search("katmai")

    # Get live snapshots from a camera
    snaps = client.get_camera_snapshots(199)

API Reference
-------------
GET  /initial                             All channels, cam-groups, default livecam
GET  /channels                            Channel (category) list
GET  /get_cam_group_info.json?id=<id>     Cam-group with all feed metadata
GET  /get_livecam_info.json?id=<id>       Single camera: YouTube ID, viewers, weather
GET  /get_cam_group_snapshots.json?id=<id> Recent snapshots for cam-group
GET  /get_page.json?page=<path>           CMS page data
GET  /landing-pages/active               Landing page blocks
GET  /get_homepage_alert                 Active alert banners
GET  /events                             Calendar events
GET  /search_results.json?q=<query>      Full-text search
GET  /snapshots/all                      All recent user snapshots (paginated)
GET  /snapshots/livecam?livecam_id=<id>  Camera snapshots
GET  /snapshots/channel?channel_id=<id>  Channel snapshots
GET  /snapshots/gallery/<slug>           Gallery snapshots
GET  /snapshots/galleries                Gallery/contest listings
GET  /get_metadata.json (POST)           SEO metadata for a page path
GET  /get_user_info.json?username=<u>    Public user profile
GET  /get_grants                         Grants/funding data
GET  /get_faqs                           FAQ content
GET  /get_films                          Films listing
GET  /testimonials                       Testimonials
GET  /get_galleries                      Photo galleries
GET  /cameras/token                      Pusher token (live viewer counts)
GET  /ping                               API health check

Auth Endpoints (Bearer token required)
---------------------------------------
POST /auth/login                         { email, password } -> token
POST /auth/logout
POST /auth/register
POST /auth/forgot_password
POST /auth/reset_password
GET  /auth/get_authenticated_user_info
POST /auth/newsletter_subscribe
POST /accounts/edit_profile
POST /accounts/save_user_preferences
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://omega.explore.org/api"
SITE_BASE = "https://explore.org"
YOUTUBE_EMBED_BASE = "https://www.youtube.com/embed"
YOUTUBE_WATCH_BASE = "https://www.youtube.com/watch"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://explore.org/",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Camera:
    """A single explore.org live camera (called 'feed' internally)."""

    id: int
    title: str
    slug: str
    uuid: str
    youtube_id: str                     # YouTube video / live-stream ID
    youtube_embed_url: str              # Full embed URL (autoplay)
    youtube_watch_url: str              # Standard watch URL
    stream_id: Optional[str]            # Internal numeric stream ID
    location_text: Optional[str]        # e.g. "Decorah, Iowa, USA"
    first_location: Optional[str]       # Specific site label
    description: str                    # HTML description
    description_text: str               # Plain-text description
    tags: Optional[str]
    channel_id: Optional[int]
    channel_title: Optional[str]
    cam_group_id: Optional[int]
    cam_group_title: Optional[str]
    cam_group_slug: Optional[str]
    cam_groups: List[str]               # All cam-group names this feed belongs to
    channels: List[str]                 # All channel names this feed belongs to
    partner_id: Optional[int]
    partner_title: Optional[str]
    partner_website: Optional[str]
    is_offline: bool
    force_offline: bool
    is_offseason: bool
    canonical_url: Optional[str]
    latlong: Optional[List[str]]        # ["lat", "lng"] strings
    snapshot_url: Optional[str]         # Most recent still image
    best_viewing_start: Optional[str]
    best_viewing_end: Optional[str]
    current_viewers: Optional[int]
    meta_title: Optional[str]
    primary_cam_group_slug: Optional[str]

    @property
    def is_live(self) -> bool:
        """True when the stream is currently active."""
        return not self.is_offline and not self.force_offline

    @property
    def explore_url(self) -> str:
        """Public URL on explore.org."""
        if self.canonical_url:
            return self.canonical_url
        if self.cam_group_slug and self.slug:
            return f"{SITE_BASE}/livecams/{self.cam_group_slug}/{self.slug}"
        return f"{SITE_BASE}/livecams"

    def __str__(self) -> str:
        status = "LIVE" if self.is_live else ("SEASONAL" if self.is_offseason else "OFFLINE")
        parts = [
            f"[{status}] {self.title} (id={self.id})",
            f"  YouTube:   {self.youtube_watch_url}",
        ]
        if self.location_text:
            parts.append(f"  Location:  {self.location_text}")
        if self.channel_title:
            parts.append(f"  Channel:   {self.channel_title}")
        if self.cam_group_title:
            parts.append(f"  Cam Group: {self.cam_group_title}")
        if self.partner_title:
            parts.append(f"  Partner:   {self.partner_title}")
        if self.current_viewers is not None:
            parts.append(f"  Viewers:   {self.current_viewers:,}")
        parts.append(f"  URL:       {self.explore_url}")
        return "\n".join(parts)


@dataclass
class CamGroup:
    """A group of related cameras (e.g. 'Bald Eagles', 'Brown Bears')."""

    id: int
    title: str
    slug: str
    uuid: Optional[str]
    description: Optional[str]
    active: bool
    feed_count: int
    multi_livecam: bool
    location_text: Optional[str]
    feeds: List[Dict[str, Any]]
    channel_ids: List[int]

    def __str__(self) -> str:
        return f"CamGroup({self.id}): {self.title} ({self.feed_count} feeds)"


@dataclass
class Channel:
    """A top-level content channel / category."""

    id: int
    title: str
    cam_group_ids: List[int]

    def __str__(self) -> str:
        return f"Channel({self.id}): {self.title} ({len(self.cam_group_ids)} groups)"


@dataclass
class Snapshot:
    """A user-captured snapshot from a live camera."""

    uuid: str
    title: str
    caption: str
    thumbnail_url: str
    full_url: str
    username: str
    display_name: str
    avatar_url: str
    num_favorites: int
    timestamp: Optional[int]
    created_at: Optional[str]
    livecam_id: Optional[int]
    youtube_id: Optional[str]

    @property
    def created_datetime(self):
        if self.timestamp:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)
        return None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _request(
    path: str,
    method: str = "GET",
    params: Optional[Dict] = None,
    json_body: Optional[Dict] = None,
    form_body: Optional[Dict] = None,
    extra_headers: Optional[Dict] = None,
    timeout: int = 20,
) -> Any:
    """Make a request to the omega.explore.org API and return parsed JSON."""
    url = path if path.startswith("http") else f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        body = urllib.parse.urlencode(form_body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _make_camera(raw: Dict[str, Any], basic: Optional[Dict] = None) -> Camera:
    vid = raw.get("video_id") or ""
    embed_url = raw.get("large_feed_html") or (
        f"{YOUTUBE_EMBED_BASE}/{vid}?rel=0&showinfo=0&autoplay=1&playsinline=1" if vid else ""
    )
    watch_url = f"{YOUTUBE_WATCH_BASE}?v={vid}" if vid else ""
    ch = raw.get("channel") or {}
    cg = raw.get("cam_group") or {}
    partner = raw.get("partner") or {}
    cam_groups_list = basic.get("cam_groups", []) if basic else []
    channels_list = basic.get("channels", []) if basic else []
    desc_raw = raw.get("description") or ""
    return Camera(
        id=raw.get("id"),
        title=raw.get("title") or "",
        slug=raw.get("slug") or "",
        uuid=raw.get("uuid") or "",
        youtube_id=vid,
        youtube_embed_url=embed_url,
        youtube_watch_url=watch_url,
        stream_id=raw.get("stream_id"),
        location_text=raw.get("location_text"),
        first_location=raw.get("first_location"),
        description=desc_raw,
        description_text=_strip_html(desc_raw),
        tags=raw.get("tags"),
        channel_id=ch.get("id"),
        channel_title=ch.get("title"),
        cam_group_id=cg.get("id"),
        cam_group_title=cg.get("title"),
        cam_group_slug=raw.get("camgroup_slug") or cg.get("slug"),
        cam_groups=cam_groups_list,
        channels=channels_list,
        partner_id=partner.get("id"),
        partner_title=partner.get("title"),
        partner_website=partner.get("website"),
        is_offline=bool(raw.get("is_offline")),
        force_offline=bool(raw.get("force_offline")),
        is_offseason=bool(raw.get("is_offseason")),
        canonical_url=raw.get("canonical_url"),
        latlong=raw.get("latlong"),
        snapshot_url=raw.get("thumbnail_large_url") or raw.get("snapshot"),
        best_viewing_start=raw.get("best_viewing_start_time"),
        best_viewing_end=raw.get("best_viewing_end_time"),
        current_viewers=raw.get("current_viewers"),
        meta_title=raw.get("meta_title"),
        primary_cam_group_slug=raw.get("primary_canonical_cam_group_slug"),
    )


def _make_snapshot(raw: Dict[str, Any]) -> Snapshot:
    return Snapshot(
        uuid=raw.get("uuid", ""),
        title=raw.get("title") or "",
        caption=raw.get("caption") or "",
        thumbnail_url=raw.get("thumbnail") or "",
        full_url=raw.get("snapshot") or "",
        username=raw.get("username") or "",
        display_name=raw.get("display_name") or "",
        avatar_url=raw.get("avatar_uri") or "",
        num_favorites=raw.get("num_favorites", 0),
        timestamp=raw.get("timestamp"),
        created_at=raw.get("created_at"),
        livecam_id=raw.get("livecam_id"),
        youtube_id=raw.get("youtube_id"),
    )


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class ExploreOrgClient:
    """
    Client for the explore.org live camera API.

    Data is cached within the instance. Call ``refresh()`` to clear and
    re-fetch from the live API.
    """

    def __init__(self, auth_token: Optional[str] = None) -> None:
        self._token = auth_token
        self._initial_data: Optional[Dict] = None
        self._channels_cache: Optional[List[Channel]] = None
        self._cam_groups_cache: Optional[Dict[int, CamGroup]] = None
        self._cameras_cache: Optional[Dict[int, Camera]] = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> str:
        """Log in and return the JWT token. Token is stored for future calls."""
        resp = _request("/auth/login", method="POST",
                        json_body={"email": email, "password": password})
        if resp.get("status") == "success" and resp.get("token"):
            self._token = resp["token"]
            return self._token
        raise RuntimeError(f"Login failed: {resp.get('message')}")

    def logout(self) -> None:
        if self._token:
            _request("/auth/logout", method="POST",
                     extra_headers={"Authorization": f"Bearer {self._token}"})
        self._token = None

    def get_current_user(self) -> Dict:
        """Return info about the authenticated user."""
        self._require_auth()
        return _request(
            "/auth/get_authenticated_user_info",
            extra_headers={"Authorization": f"Bearer {self._token}"},
        ).get("data", {})

    # ------------------------------------------------------------------
    # Core data loading
    # ------------------------------------------------------------------

    def _load_initial(self) -> Dict:
        if self._initial_data is None:
            resp = _request("/initial")
            if resp.get("status") != "success":
                raise RuntimeError(f"Failed to load initial data: {resp.get('message')}")
            self._initial_data = resp["data"]
        return self._initial_data

    def refresh(self) -> None:
        """Clear all caches so the next call fetches fresh data."""
        self._initial_data = None
        self._channels_cache = None
        self._cam_groups_cache = None
        self._cameras_cache = None

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def get_channels(self) -> List[Channel]:
        """Return all top-level channels (categories)."""
        if self._channels_cache is None:
            data = self._load_initial()
            self._channels_cache = [
                Channel(id=ch["id"], title=ch["title"],
                        cam_group_ids=ch.get("cam_groups", []))
                for ch in data.get("channels", [])
            ]
        return self._channels_cache

    def get_channel(self, channel_id_or_title) -> Optional[Channel]:
        """Find a channel by ID (int) or title (str, case-insensitive)."""
        for ch in self.get_channels():
            if ch.id == channel_id_or_title or \
               ch.title.lower() == str(channel_id_or_title).lower():
                return ch
        return None

    # ------------------------------------------------------------------
    # Cam Groups
    # ------------------------------------------------------------------

    def get_cam_groups(self) -> List[CamGroup]:
        """Return all cam-groups."""
        self._ensure_cam_groups()
        return list(self._cam_groups_cache.values())

    def get_cam_group(self, cam_group_id_or_slug) -> Optional[CamGroup]:
        """Find a cam-group by id (int) or slug (str)."""
        self._ensure_cam_groups()
        for cg in self._cam_groups_cache.values():
            if cg.id == cam_group_id_or_slug or cg.slug == cam_group_id_or_slug:
                return cg
        return None

    def get_cam_group_detail(self, cam_group_id: int) -> Dict:
        """Fetch fresh full cam-group details from the API."""
        resp = _request("/get_cam_group_info.json",
                        params={"t": int(time.time()), "id": cam_group_id})
        if resp.get("status") != "success":
            raise RuntimeError(f"Failed to get cam group {cam_group_id}: {resp.get('message')}")
        return resp["data"]

    # ------------------------------------------------------------------
    # Cameras
    # ------------------------------------------------------------------

    def get_all_cameras(self) -> List[Camera]:
        """Return all 232 cameras (requires API call on first use)."""
        self._ensure_cameras()
        return list(self._cameras_cache.values())

    def get_camera(self, camera_id: int) -> Optional[Camera]:
        """Return a Camera by its numeric ID."""
        self._ensure_cameras()
        return self._cameras_cache.get(camera_id)

    def get_camera_detail(self, camera_id: int) -> Camera:
        """Fetch complete camera details from the API (always fresh)."""
        resp = _request("/get_livecam_info.json", params={"id": camera_id})
        if resp.get("status") != "success":
            raise RuntimeError(f"Camera {camera_id} not found: {resp.get('message')}")
        return _make_camera(resp["data"])

    def get_camera_by_slug(self, slug: str) -> Optional[Camera]:
        """Find a camera by its URL slug."""
        self._ensure_cameras()
        for cam in self._cameras_cache.values():
            if cam.slug == slug:
                return cam
        return None

    def get_live_cameras(self) -> List[Camera]:
        """Return only cameras that are currently streaming live."""
        return [c for c in self.get_all_cameras() if c.is_live]

    def get_offline_cameras(self) -> List[Camera]:
        """Return cameras that are currently offline or off-season."""
        return [c for c in self.get_all_cameras() if not c.is_live]

    def get_cameras_by_channel(self, channel_id_or_title) -> List[Camera]:
        """Return all cameras in a given channel / category."""
        ch = self.get_channel(channel_id_or_title)
        if ch is None:
            return []
        self._ensure_cam_groups()
        feed_ids: set = set()
        for cg_id in ch.cam_group_ids:
            cg = self._cam_groups_cache.get(cg_id)
            if cg:
                for f in cg.feeds:
                    feed_ids.add(f["id"])
        self._ensure_cameras()
        return [c for c in self._cameras_cache.values() if c.id in feed_ids]

    def get_cameras_by_cam_group(self, cam_group_id_or_slug) -> List[Camera]:
        """Return all cameras in a specific cam-group."""
        cg = self.get_cam_group(cam_group_id_or_slug)
        if cg is None:
            return []
        feed_ids = {f["id"] for f in cg.feeds}
        self._ensure_cameras()
        return [c for c in self._cameras_cache.values() if c.id in feed_ids]

    def get_cameras_by_tag(self, tag: str) -> List[Camera]:
        """Return cameras whose tags contain the given string (case-insensitive)."""
        tag_lower = tag.lower()
        return [c for c in self.get_all_cameras()
                if c.tags and tag_lower in c.tags.lower()]

    def get_cameras_by_location(self, location: str) -> List[Camera]:
        """Return cameras matching a location substring (case-insensitive)."""
        loc_lower = location.lower()
        return [c for c in self.get_all_cameras()
                if loc_lower in (c.location_text or "").lower()
                or loc_lower in (c.first_location or "").lower()]

    def get_most_popular_cameras(self, limit: int = 20) -> List[Camera]:
        """Return cameras sorted by current viewer count, descending."""
        cams = [c for c in self.get_all_cameras() if c.current_viewers is not None]
        return sorted(cams, key=lambda c: c.current_viewers or 0, reverse=True)[:limit]

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def get_recent_snapshots(self, page: int = 1, per_page: int = 20) -> List[Snapshot]:
        """Return recent user-submitted snapshots across all cameras."""
        resp = _request("/snapshots/all", params={"page": page, "first": per_page})
        return [_make_snapshot(s) for s in resp.get("data", [])]

    def get_camera_snapshots(self, camera_id: int,
                              page: int = 1, per_page: int = 20) -> List[Snapshot]:
        """Return recent snapshots for a specific camera."""
        resp = _request("/snapshots/livecam",
                        params={"livecam_id": camera_id, "page": page, "first": per_page})
        return [_make_snapshot(s) for s in resp.get("data", [])]

    def get_channel_snapshots(self, channel_id: int,
                               page: int = 1, per_page: int = 20) -> List[Snapshot]:
        """Return recent snapshots from a specific channel."""
        resp = _request("/snapshots/channel",
                        params={"channel_id": channel_id, "page": page, "first": per_page})
        return [_make_snapshot(s) for s in resp.get("data", [])]

    def get_cam_group_snapshots(self, cam_group_id: int) -> List[Dict]:
        """Return snapshot thumbnails for all feeds in a cam-group."""
        resp = _request("/get_cam_group_snapshots.json",
                        params={"t": int(time.time()), "id": cam_group_id})
        return resp.get("data", [])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> Dict[str, List]:
        """
        Full-text search across cameras, blog posts, videos, and users.

        Returns dict with keys: cameras, snapshots, blog_posts, videos, films, users.
        """
        resp = _request("/search_results.json", params={"q": query})
        data = resp.get("data", {})
        return {
            "cameras": data.get("feeds", []),
            "snapshots": data.get("snapshots", []),
            "blog_posts": data.get("blog_posts", []),
            "videos": data.get("videos", []),
            "films": data.get("films", []),
            "users": data.get("users", []),
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_page_metadata(self, path: str) -> List[Dict]:
        """
        Return SEO meta tags for any explore.org page path.

        Example: client.get_page_metadata("/livecams/bald-eagles/decorah-eagles")
        """
        resp = _request("/get_metadata.json", method="POST", json_body={"path": path})
        return resp.get("data", {}).get("meta", [])

    def get_homepage_alerts(self) -> List[Dict]:
        """Return active alert banners shown on the homepage."""
        resp = _request("/get_homepage_alert")
        return resp.get("data") or []

    def get_events(self) -> List[Dict]:
        """Return calendar events."""
        resp = _request("/events")
        raw = resp.get("data", {}).get("events", [])
        return [e for e in raw if e.get("title")]

    def get_faqs(self) -> List[Dict]:
        """Return FAQ entries."""
        return _request("/get_faqs").get("data") or []

    def get_galleries(self) -> List[Dict]:
        """Return photo gallery listings."""
        return _request("/get_galleries").get("data") or []

    def get_user_info(self, username: str) -> Dict:
        """Return public profile for a username."""
        return _request("/get_user_info.json", params={"username": username}).get("data", {})

    def ping(self) -> bool:
        """Return True if the API is reachable."""
        try:
            _request("/ping")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Convenience / reporting
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a human-readable summary of available cameras."""
        channels = self.get_channels()
        all_cams = self.get_all_cameras()
        live = [c for c in all_cams if c.is_live]

        lines = [
            "=" * 62,
            "  Explore.org Live Camera System",
            "=" * 62,
            f"  Total cameras:    {len(all_cams)}",
            f"  Currently live:   {len(live)}",
            f"  Offline/seasonal: {len(all_cams) - len(live)}",
            f"  Channels:         {len(channels)}",
            "",
            "  Channels:",
        ]
        # Use CAMERA_CATALOGUE for accurate live/offline stats
        for ch in channels:
            cams = self.get_cameras_by_channel(ch.id)
            live_cnt = sum(1 for c in cams if c.is_live)
            lines.append(f"    {ch.title:<30} {len(cams):>3} cams  ({live_cnt} live)")

        lines.append("")
        lines.append("  Top 10 most-watched cameras:")
        for i, cam in enumerate(self.get_most_popular_cameras(10), 1):
            viewers = cam.current_viewers or 0
            status = "LIVE" if cam.is_live else "OFF "
            lines.append(
                f"  {i:>2}. [{status}] {viewers:>6} viewers  {cam.title}"
            )
        lines.append("=" * 62)
        return "\n".join(lines)

    def export_camera_list(self, include_offline: bool = True) -> List[Dict]:
        """
        Export all cameras as plain dicts (suitable for JSON / pandas).

        Each record contains: id, title, slug, youtube_id, youtube_watch_url,
        youtube_embed_url, is_live, is_offseason, channel, cam_group, location,
        partner, tags, current_viewers, canonical_url, snapshot_url, description.
        """
        result = []
        for cam in self.get_all_cameras():
            if not include_offline and not cam.is_live:
                continue
            result.append({
                "id": cam.id,
                "title": cam.title,
                "slug": cam.slug,
                "youtube_id": cam.youtube_id,
                "youtube_watch_url": cam.youtube_watch_url,
                "youtube_embed_url": cam.youtube_embed_url,
                "is_live": cam.is_live,
                "is_offseason": cam.is_offseason,
                "channel": cam.channel_title,
                "cam_group": cam.cam_group_title,
                "location": cam.location_text,
                "partner": cam.partner_title,
                "tags": cam.tags,
                "current_viewers": cam.current_viewers,
                "canonical_url": cam.explore_url,
                "snapshot_url": cam.snapshot_url,
                "description": cam.description_text[:300] if cam.description_text else "",
            })
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_cam_groups(self) -> None:
        if self._cam_groups_cache is not None:
            return
        data = self._load_initial()
        self._cam_groups_cache = {
            cg["id"]: CamGroup(
                id=cg["id"], title=cg["title"], slug=cg["slug"],
                uuid=cg.get("uuid"), description=cg.get("description"),
                active=bool(cg.get("active")), feed_count=cg.get("feed_count", 0),
                multi_livecam=bool(cg.get("multi_livecam")),
                location_text=cg.get("location_text"),
                feeds=cg.get("feeds", []),
                channel_ids=cg.get("channel_ids", []),
            )
            for cg in data.get("camgroups", [])
        }

    def _ensure_cameras(self) -> None:
        """
        Build camera cache from /initial.

        The /initial endpoint only provides minimal feed info (id, title, slug,
        uuid) per cam-group feed. For full metadata (description, latlong,
        partner, viewer counts, etc.), call ``get_camera_detail(id)``.
        """
        if self._cameras_cache is not None:
            return

        self._ensure_cam_groups()
        data = self._load_initial()

        # Channel membership
        channel_lookup: Dict[int, List[str]] = {}
        for ch in data.get("channels", []):
            for cg_id in ch.get("cam_groups", []):
                channel_lookup.setdefault(cg_id, []).append(ch["title"])

        feed_cam_groups: Dict[int, List[str]] = {}
        feed_channels: Dict[int, List[str]] = {}
        for cg_id, cg in self._cam_groups_cache.items():
            for feed in cg.feeds:
                fid = feed["id"]
                feed_cam_groups.setdefault(fid, [])
                feed_channels.setdefault(fid, [])
                if cg.title not in feed_cam_groups[fid]:
                    feed_cam_groups[fid].append(cg.title)
                for ch_name in channel_lookup.get(cg_id, []):
                    if ch_name not in feed_channels[fid]:
                        feed_channels[fid].append(ch_name)

        self._cameras_cache = {}

        # default_livecam has full metadata
        default_raw = data.get("default_livecam")
        if default_raw:
            fid = default_raw.get("id")
            if fid:
                basic = {"cam_groups": feed_cam_groups.get(fid, []),
                         "channels": feed_channels.get(fid, [])}
                self._cameras_cache[fid] = _make_camera(default_raw, basic)

        # All other cameras - minimal info from /initial cam_group feeds
        for cg_id, cg in self._cam_groups_cache.items():
            for feed in cg.feeds:
                fid = feed["id"]
                if fid in self._cameras_cache:
                    continue
                # Look up in CAMERA_CATALOGUE for richer offline-status data
                cat = CAMERA_CATALOGUE.get(fid, {})
                vid = feed.get("video_id") or cat.get("youtube_id", "")
                is_off = not cat.get("live", True) if cat else False
                embed_url = (
                    f"{YOUTUBE_EMBED_BASE}/{vid}?rel=0&showinfo=0&autoplay=1&playsinline=1"
                    if vid else ""
                )
                ch_names = feed_channels.get(fid, [])
                self._cameras_cache[fid] = Camera(
                    id=fid,
                    title=feed.get("title") or cat.get("title", ""),
                    slug=feed.get("slug") or cat.get("slug", ""),
                    uuid=feed.get("uuid") or "",
                    youtube_id=vid,
                    youtube_embed_url=embed_url,
                    youtube_watch_url=f"{YOUTUBE_WATCH_BASE}?v={vid}" if vid else "",
                    stream_id=None,
                    location_text=cat.get("location"),
                    first_location=None,
                    description="",
                    description_text="",
                    tags=cat.get("tags"),
                    channel_id=None,
                    channel_title=ch_names[0] if ch_names else cat.get("channel"),
                    cam_group_id=cg_id,
                    cam_group_title=cg.title,
                    cam_group_slug=cg.slug,
                    cam_groups=feed_cam_groups.get(fid, []),
                    channels=ch_names,
                    partner_id=None,
                    partner_title=cat.get("partner"),
                    partner_website=None,
                    is_offline=is_off,
                    force_offline=False,
                    is_offseason=is_off,
                    canonical_url=cat.get("canonical_url"),
                    latlong=cat.get("latlong"),
                    snapshot_url=None,
                    best_viewing_start=None,
                    best_viewing_end=None,
                    current_viewers=None,
                    meta_title=None,
                    primary_cam_group_slug=cg.slug,
                )

    def _require_auth(self) -> None:
        if not self._token:
            raise RuntimeError("Authentication required. Call login() first.")


# ---------------------------------------------------------------------------
# Bulk fetcher (makes ~232 API requests)
# ---------------------------------------------------------------------------


def fetch_all_camera_details(delay: float = 0.1) -> List[Camera]:
    """
    Fetch full metadata for every camera (~232 API requests, ~30-60 seconds).

    Returns Camera objects with complete data: descriptions, partner info,
    coordinates, viewer counts, etc.

    Parameters
    ----------
    delay : float
        Seconds to sleep between batches of 10 requests.
    """
    client = ExploreOrgClient()
    data = client._load_initial()
    client._ensure_cam_groups()

    feed_ids: Dict[int, Dict] = {}
    for cg in data.get("camgroups", []):
        for f in cg.get("feeds", []):
            feed_ids[f["id"]] = f

    channel_lookup: Dict[int, List[str]] = {}
    for ch in data.get("channels", []):
        for cg_id in ch.get("cam_groups", []):
            channel_lookup.setdefault(cg_id, []).append(ch["title"])

    feed_cam_groups: Dict[int, List[str]] = {}
    feed_channels: Dict[int, List[str]] = {}
    for cg in data.get("camgroups", []):
        cg_id = cg["id"]
        for feed in cg.get("feeds", []):
            fid = feed["id"]
            feed_cam_groups.setdefault(fid, [])
            feed_channels.setdefault(fid, [])
            if cg["title"] not in feed_cam_groups[fid]:
                feed_cam_groups[fid].append(cg["title"])
            for ch_name in channel_lookup.get(cg_id, []):
                if ch_name not in feed_channels[fid]:
                    feed_channels[fid].append(ch_name)

    cameras = []
    for i, fid in enumerate(sorted(feed_ids.keys())):
        resp = _request("/get_livecam_info.json", params={"id": fid})
        if resp.get("status") == "success" and "data" in resp:
            basic = {"cam_groups": feed_cam_groups.get(fid, []),
                     "channels": feed_channels.get(fid, [])}
            cameras.append(_make_camera(resp["data"], basic))
        if delay and i % 10 == 9:
            time.sleep(delay)

    return cameras


# ---------------------------------------------------------------------------
# Embedded camera catalogue (as of 2026-03-27)
# 232 cameras with YouTube IDs, live status, location, and canonical URLs.
# ---------------------------------------------------------------------------

CAMERA_CATALOGUE: Dict[int, Dict] = {
    # --- Africa ---
    244: {'title': 'Gorilla Forest Corridor', 'slug': 'gorilla-forest-corridor', 'youtube_id': 'yfSyjwY6zSQ', 'channel': 'Africa', 'cam_group': 'GRACE Gorillas', 'cam_group_slug': 'grace-gorillas', 'live': False, 'location': 'GRACE Center, Kasugho, Eastern DRC', 'partner': 'GRACE Gorillas', 'tags': 'grace gorillas, gorillas', 'canonical_url': 'https://explore.org/livecams/grace-gorillas/gorilla-forest-corridor', 'latlong': ['0.27513889', '29.01611111']},
    247: {'title': "Rosie's Pan", 'slug': 'rosies-pan', 'youtube_id': 'ItdXaWUVF48', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Balule Nature Reserve, South Africa', 'partner': 'Africam.com', 'tags': 'africam, african wildlife, lions, elephant', 'canonical_url': 'https://explore.org/livecams/africam/rosies-pan', 'latlong': ['-24.2059306', '30.861683']},
    248: {'title': 'The Naledi Cat-EYE', 'slug': 'naledi-cat-eye', 'youtube_id': 'pZZst4BOpVI', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Olifants West Game Reserve, South Africa', 'partner': 'Africam.com', 'tags': 'live lion video, lions, africam', 'canonical_url': 'https://explore.org/livecams/africam/naledi-cat-eye', 'latlong': ['-24.2088592', '30.8913728']},
    249: {'title': 'Tembe Elephant Park', 'slug': 'tembe-elephant-park', 'youtube_id': 'VUJbDTIYlM4', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Emangusi, South Africa', 'partner': 'Africam.com', 'tags': 'elephant, africam, lions, lion', 'canonical_url': 'https://explore.org/livecams/africam/tembe-elephant-park', 'latlong': ['-27.046769', '32.448250']},
    250: {'title': 'Olifants River', 'slug': 'olifants-river', 'youtube_id': '_NXaovxB-Bk', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Emangusi, South Africa', 'partner': 'Africam.com', 'tags': 'africam, african wildlife, lions, crocodile, elephant', 'canonical_url': 'https://explore.org/livecams/africam/olifants-river', 'latlong': ['-24.1762222', '30.8693611']},
    251: {'title': '98.6% Human', 'slug': '986-human', 'youtube_id': 'NdE7bANJIz0', 'channel': 'Africa', 'cam_group': 'African Wildlife', 'cam_group_slug': 'african-wildlife', 'live': False, 'location': 'Volcanoes National Park, Rwanda', 'partner': 'Explore.org', 'tags': 'gorilla, 98.6% Human', 'canonical_url': 'https://explore.org/livecams/african-wildlife/986-human', 'latlong': ['-1.94707', '29.876381']},
    276: {'title': 'Nkorho Bush Lodge', 'slug': 'nkorho-bush-lodge', 'youtube_id': 'dIChLG4_WNs', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Sabi Sand Game Reserve, South Africa', 'partner': 'Africam.com', 'tags': 'africam, africa, elephant cam, lions', 'canonical_url': 'https://explore.org/livecams/africam/nkorho-bush-lodge', 'latlong': ['-24.731708', '31.598167']},
    284: {'title': 'Tau Waterhole', 'slug': 'tau', 'youtube_id': 'DsNtwGJXTTs', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Madikwe Game Reserve,  South Africa', 'partner': 'Africam.com', 'tags': 'africam, lion, tiger, wild dogs, giraffe', 'canonical_url': 'https://explore.org/livecams/africam/tau', 'latlong': ['-25.354380', '26.529570']},
    297: {'title': 'Africam Shows', 'slug': 'africam-shows', 'youtube_id': 'KsR7RrNGwmY', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': False, 'location': 'Emangusi, South Africa', 'partner': 'Africam.com', 'tags': 'africam, shows', 'canonical_url': 'https://explore.org/livecams/africam/africam-shows', 'latlong': ['-27.046769', '32.448250']},
    299: {'title': 'Lesser Flamingos at Kamfers Dam', 'slug': 'flamingo-cam', 'youtube_id': '3MlJEXOZTfo', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Kimberly, South Africa', 'partner': 'BirdLife South Africa & Africam', 'tags': 'flamingo, africam, bird life, bird life south africa', 'canonical_url': 'https://explore.org/livecams/africam/flamingo-cam', 'latlong': ['-28.673071', '24.7650712524049']},
    300: {'title': 'Lisbon Falls - Blyde River', 'slug': 'lisbon-falls', 'youtube_id': '-qwXenyHDN4', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': False, 'location': 'Graskop, South Africa', 'partner': 'Africam.com', 'tags': 'africam, africa, waterfall', 'canonical_url': 'https://explore.org/livecams/africam/lisbon-falls', 'latlong': ['-24.86151166212303', '30.83583164667677']},
    308: {'title': 'Black Eagles of the Selati Wilderness Foundation', 'slug': 'black-eagle', 'youtube_id': 'Z1wf0QBoAPM', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Selati Game Reserve', 'partner': 'Africam.com', 'tags': 'africam, black eagle, african black eagle', 'canonical_url': 'https://explore.org/livecams/africam/black-eagle', 'latlong': ['-24.069710', '30.841510']},
    317: {'title': 'Stony Point Penguin Colony Camera', 'slug': 'penguin-colony', 'youtube_id': 'ZRvngZiRx_g', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Stony Point Nature Reserve, South Africa', 'partner': 'BirdLife South Africa & Africam', 'tags': 'penguin, wild penguin, stony point, africam, african penguin', 'canonical_url': 'https://explore.org/livecams/africam/penguin-colony', 'latlong': ['-34.37029425534305', '18.89192768510095']},
    345: {'title': 'Outdoor Rhino Cam at HESC', 'slug': 'hesc-outdoor-rhino-cam', 'youtube_id': 'wtylzrJvCKU', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Hoedspruit, South Africa', 'partner': 'HESC and Africam.com', 'tags': 'white rhino, Rhino, africam, HESC', 'canonical_url': 'https://explore.org/livecams/africam/hesc-outdoor-rhino-cam', 'latlong': ['-24.51071117916785', '31.032269180592397']},
    349: {'title': 'Tammy the Cheetah Cam at HESC', 'slug': 'hesc-cheetah-cam-1', 'youtube_id': 'HCuB0h3vDrA', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': False, 'location': 'Hoedspruit, South Africa', 'partner': 'HESC and Africam.com', 'tags': 'cheetah, King Cheetah, africam, HESC', 'canonical_url': 'https://explore.org/livecams/africam/hesc-cheetah-cam-1', 'latlong': ['-24.51071117916785', '31.032269180592397']},
    350: {'title': 'Becky the Cheetah Cam at HESC', 'slug': 'hesc-cheetah-cam-2', 'youtube_id': 'oeOQi1N4gxc', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': False, 'location': 'Hoedspruit, South Africa', 'partner': 'HESC and Africam.com', 'tags': 'cheetah, King Cheetah, adine, africam, HESC', 'canonical_url': 'https://explore.org/livecams/africam/hesc-cheetah-cam-2', 'latlong': ['-24.51071117916785', '31.032269180592397']},
    355: {'title': 'Lola ya Bonobo Sanctuary Enclosure', 'slug': 'bonobo-sanctuary', 'youtube_id': 'T0cF-bXCOHE', 'channel': 'Africa', 'cam_group': 'Friends of Bonobos', 'cam_group_slug': 'bonobos', 'live': True, 'location': 'Kinshasa, the Democratic Republic of Congo', 'partner': 'Friends of Bonobos', 'tags': 'bonobo, friends of bonobos, bonobos, lola bonobos', 'canonical_url': 'https://explore.org/livecams/bonobos/bonobo-sanctuary', 'latlong': ['-4.492444084504458', '15.268717897282208']},
    356: {'title': 'Lola ya Bonobo Sanctuary Nursery', 'slug': 'bonobo-nursery', 'youtube_id': 'u5eVtSg2Skg', 'channel': 'Africa', 'cam_group': 'Friends of Bonobos', 'cam_group_slug': 'bonobos', 'live': True, 'location': 'Kinshasa, the Democratic Republic of Congo', 'partner': 'Friends of Bonobos', 'tags': 'bonobo, lola bonobos, friends of bonobos', 'canonical_url': 'https://explore.org/livecams/bonobos/bonobo-nursery', 'latlong': ['-4.492444084504458', '15.268717897282208']},
    364: {'title': 'Boteti River Zebra Migration', 'slug': 'zebra-migration', 'youtube_id': '7hKbyXxWT2k', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Camelthorn Farmstead, Botswana', 'partner': 'Africam and Animal Survival International', 'tags': 'africam, animal survival international, ASI, zebra, zebra migration', 'canonical_url': 'https://explore.org/livecams/africam/zebra-migration', 'latlong': ['-20.425135970985863', '24.514766190747494']},
    375: {'title': 'Kalahari Salt Pan', 'slug': 'kalahari-salt-pan', 'youtube_id': 'epZP0VOirh0', 'channel': 'Africa', 'cam_group': 'Africam', 'cam_group_slug': 'africam', 'live': True, 'location': 'Makgadikgadi Salt Pans of the Kalahari Desert', 'partner': 'Africam & The Natural Selection Foundation', 'tags': 'zebra migration, zebra, africam, natural selection, Kalahari, Kalahari Salt Pan', 'canonical_url': 'https://explore.org/livecams/africam/kalahari-salt-pan', 'latlong': ['-20.434722', '25.127500']},
    # --- Bears ---
    5: {'title': 'Polar Bear Tundra Buggy Lodge - North', 'slug': 'polar-bear-lodge-cam', 'youtube_id': 'ZGCCMkurNGc', 'channel': 'Bears', 'cam_group': 'Polar Bears International', 'cam_group_slug': 'polar-bears-international', 'live': False, 'location': 'Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'tundra buggies, where are polar bears, tundra buggy lodge, polar bear in the wild, polar bears, chur', 'canonical_url': 'https://explore.org/livecams/polar-bears-international/polar-bear-lodge-cam', 'latlong': ['58.786516', '-93.685949']},
    6: {'title': 'Polar Bear Tundra Buggy', 'slug': 'polar-bear-cam', 'youtube_id': '4XzYvaDCv7s', 'channel': 'Bears', 'cam_group': 'Polar Bears International', 'cam_group_slug': 'polar-bears-international', 'live': False, 'location': 'Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'live polar bear cam, polar bear cam, polar bear web cam live, churchill, zoo cam, polar bear watch, ', 'canonical_url': 'https://explore.org/livecams/polar-bears-international/polar-bear-cam', 'latlong': ['58.746801', '-93.815000']},
    10: {'title': 'Wolong Grove Panda Yard', 'slug': 'wolong-grove-panda-yard', 'youtube_id': 'UKkc40WQm0c', 'channel': 'Bears', 'cam_group': 'Panda Bears', 'cam_group_slug': 'panda-bears', 'live': False, 'location': 'Gengda, Sichuan, China', 'partner': 'China Conservation & Research Center for the Giant Panda', 'tags': 'giant panda cam, panda cam china, panda live stream, panda cams, china', 'canonical_url': 'https://explore.org/livecams/panda-bears/wolong-grove-panda-yard', 'latlong': ['31.030800', '103.182765']},
    11: {'title': 'Happiness Village Baby Panda Park', 'slug': 'happiness-village-baby-panda-park', 'youtube_id': 'tCcd6ZkExuo', 'channel': 'Bears', 'cam_group': 'Panda Bears', 'cam_group_slug': 'panda-bears', 'live': False, 'location': 'Gengda, Sichuan, China', 'partner': 'China Conservation & Research Center for the Giant Panda', 'tags': 'panda cam, giant panda cam, baby panda cam, live panda cam, panda webcam, panda cam in china, zoo ca', 'canonical_url': 'https://explore.org/livecams/panda-bears/happiness-village-baby-panda-park', 'latlong': ['31.030800', '103.182765']},
    14: {'title': 'Gengda Valley Panda Yard', 'slug': 'gengda-valley-panda-yard', 'youtube_id': 'BsZEOvS3qTM', 'channel': 'Bears', 'cam_group': 'Panda Bears', 'cam_group_slug': 'panda-bears', 'live': False, 'location': 'Gengda, Sichuan, China', 'partner': 'China Conservation & Research Center for the Giant Panda', 'tags': 'panda, wolong national reserve, china, bifengxia panda reserve, bear, bamboo, giant pandas', 'canonical_url': 'https://explore.org/livecams/panda-bears/gengda-valley-panda-yard', 'latlong': ['31.030800', '103.182765']},
    25: {'title': 'Brooks Falls Brown Bears', 'slug': 'brown-bear-salmon-cam-brooks-falls', 'youtube_id': '4qSRIIaOnLI', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Brooks Falls - Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'fish, salmon, katmai, alaska, bears, live, river, brooks, waterfall', 'canonical_url': 'https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-brooks-falls', 'latlong': ['58.554852', '-155.791862']},
    26: {'title': "Kat's River View", 'slug': 'brown-bear-salmon-cam-lower-river', 'youtube_id': '0ikLzeuGeOA', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'bear, alaska, katmai, river, brooks river, live, bears', 'canonical_url': 'https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-lower-river', 'latlong': ['58.552691', '-155.778219']},
    27: {'title': 'The Riffles Bear Cam', 'slug': 'brown-bear-salmon-cam-the-riffles', 'youtube_id': 'tp7PEBb2GCs', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Alaska', 'partner': 'Katmai National Park', 'tags': 'riffles, alaska, river, katmai, bears, live', 'canonical_url': 'https://explore.org/livecams/brown-bears/brown-bear-salmon-cam-the-riffles', 'latlong': ['58.554101', '-155.790901']},
    39: {'title': 'Tundra Connections Live Q&A Session', 'slug': 'my-planet-my-part', 'youtube_id': 'b2xFp7Uz4Pk', 'channel': 'Bears', 'cam_group': 'Polar Bears International', 'cam_group_slug': 'polar-bears-international', 'live': False, 'location': 'Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'churchill, canada, arctic, tundra, live, polar, bears, chat', 'canonical_url': 'https://explore.org/livecams/polar-bears-international/my-planet-my-part', 'latlong': ['58.761293', '-93.230843']},
    40: {'title': 'Polar Bears Cape South - Wapusk National Park', 'slug': 'polar-bear-cape-churchill-cam', 'youtube_id': 'wj1vuPRJsCQ', 'channel': 'Bears', 'cam_group': 'Polar Bears International', 'cam_group_slug': 'polar-bears-international', 'live': True, 'location': 'Wapusk National Park, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'churchill, canada, arctic, tundra, manitoba, pbi, wapusk, polar, bears, live', 'canonical_url': 'https://explore.org/livecams/polar-bears-international/polar-bear-cape-churchill-cam', 'latlong': ['58.761293', '-93.230843']},
    50: {'title': 'River Watch Bear Cam', 'slug': 'river-watch-brown-bear-salmon-cams', 'youtube_id': '98SZ_UMAp_Q', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'katmai, alaska, brooks river, bears, live', 'canonical_url': 'https://explore.org/livecams/brown-bears/river-watch-brown-bear-salmon-cams', 'latlong': ['58.554101', '-155.790901']},
    60: {'title': 'Polar Bear Tundra Buggy Lodge - South', 'slug': 'polar-bear-tundra-buggy-lodge-south', 'youtube_id': 'U9_Fdcp73Pc', 'channel': 'Bears', 'cam_group': 'Polar Bears International', 'cam_group_slug': 'polar-bears-international', 'live': False, 'location': 'Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'tundra buggy, polar bears, churchill, canada, arctic, pbi, live', 'canonical_url': 'https://explore.org/livecams/polar-bears-international/polar-bear-tundra-buggy-lodge-south', 'latlong': ['58.746801', '-93.815000']},
    88: {'title': 'Polar Bears Cape East - Wapusk National Park', 'slug': 'polar-bear-cape-churchill-cam-2', 'youtube_id': '1j0FjEN93wo', 'channel': 'Bears', 'cam_group': 'Polar Bears International', 'cam_group_slug': 'polar-bears-international', 'live': False, 'location': 'Wapusk National Park, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'canada, arctic, tundra, manitoba, pbi, bears, live, polar', 'canonical_url': 'https://explore.org/livecams/polar-bears-international/polar-bear-cape-churchill-cam-2', 'latlong': ['58.761293', '-93.230843']},
    122: {'title': 'Underwater Salmon Cam', 'slug': 'underwater-bear-cam-brown-bear-salmon-cams', 'youtube_id': 'n712VZuZlrM', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'fish, salmon, katmai, bears, underwater, brooks river, live, alaska', 'canonical_url': 'https://explore.org/livecams/brown-bears/underwater-bear-cam-brown-bear-salmon-cams', 'latlong': ['58.553542', '-155.778540']},
    222: {'title': 'Happiness Village Baby Panda Garden', 'slug': 'happiness-village-garden', 'youtube_id': '58aHnTp0-JY', 'channel': 'Bears', 'cam_group': 'Panda Bears', 'cam_group_slug': 'panda-bears', 'live': False, 'location': 'Gengda, Sichuan, China', 'partner': 'China Conservation & Research Center for the Giant Panda', 'tags': 'bear, panda, china, live, zoo, gengda, happiness', 'canonical_url': 'https://explore.org/livecams/panda-bears/happiness-village-garden', 'latlong': ['31.030800', '103.182765']},
    226: {'title': 'Brooks Live Chat', 'slug': 'brooks-live-chat', 'youtube_id': 'IUoi09cusmE', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Brooks Falls - Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'brooks falls, fish, salmon, alaska, brooks river, bears, live, katmai, chat', 'canonical_url': 'https://explore.org/livecams/brown-bears/brooks-live-chat', 'latlong': ['58.554852', '-155.791862']},
    229: {'title': 'Brooks Falls Brown Bears Low', 'slug': 'brooks-falls-brown-bears-low', 'youtube_id': '53vUbxn5wl8', 'channel': 'Bears', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'brooks falls, fish, salmon, katmai, alaska, bears, live, river, waterfall', 'canonical_url': 'https://explore.org/livecams/brown-bears/brooks-falls-brown-bears-low', 'latlong': ['58.554852', '-155.791862']},
    351: {'title': 'Anan Wildlife Observatory Fishing Hole 3', 'slug': 'anan-black-bear-camera-1', 'youtube_id': 'iJ1nxN1StIQ', 'channel': 'Bears', 'cam_group': 'Tongass National Forest', 'cam_group_slug': 'tongass-national-forest', 'live': False, 'location': 'Tongass National Forest, Wrangell, Alaska', 'partner': 'Anan Wildlife Observatory- Tongass National Forest', 'tags': 'Tongass National Forest, anan, black bears', 'canonical_url': 'https://explore.org/livecams/tongass-national-forest/anan-black-bear-camera-1', 'latlong': ['56.17906720580262', '-131.88362825260583']},
    352: {'title': 'Anan Wildlife Observatory Lower Falls and Caves', 'slug': 'anan-black-bear-camera-2', 'youtube_id': '2360fnKZcIQ', 'channel': 'Bears', 'cam_group': 'Tongass National Forest', 'cam_group_slug': 'tongass-national-forest', 'live': False, 'location': 'Tongass National Forest, Wrangell, Alaska', 'partner': 'Anan Wildlife Observatory- Tongass National Forest', 'tags': 'anan, black bear, Tongass, forest', 'canonical_url': 'https://explore.org/livecams/tongass-national-forest/anan-black-bear-camera-2', 'latlong': ['56.17906720580262', '-131.88362825260583']},
    365: {'title': 'Anan Wildlife Observatory Fishing Hole 4', 'slug': 'anan-fishinghole-4', 'youtube_id': 'g38goqg4xTc', 'channel': 'Bears', 'cam_group': 'Tongass National Forest', 'cam_group_slug': 'tongass-national-forest', 'live': False, 'location': 'Tongass National Forest, Wrangell, Alaska', 'partner': 'Anan Wildlife Observatory- Tongass National Forest', 'tags': 'bear, black bears, black bear, Tongass National Forest, anan, fishing hole', 'canonical_url': 'https://explore.org/livecams/tongass-national-forest/anan-fishinghole-4', 'latlong': ['56.17906720580262', '-131.88362825260583']},
    # --- Birds ---
    19: {'title': 'Penguins - Underwater View', 'slug': 'live-penguin-cam', 'youtube_id': 'KlVMg-8SIlw', 'channel': 'Birds', 'cam_group': 'Penguins', 'cam_group_slug': 'penguins', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'underwater penguin cam, live zoo penguins, penguin camera, sea world penguin cam, penguins the anima', 'canonical_url': 'https://explore.org/livecams/penguins/live-penguin-cam', 'latlong': ['33.762149', '-118.196981']},
    21: {'title': 'Penguin Beach', 'slug': 'live-penguin-cam-2', 'youtube_id': 'GSxpCbXsvtI', 'channel': 'Birds', 'cam_group': 'Penguins', 'cam_group_slug': 'penguins', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'penguin, magellanic, aquarium, birds, fish, live', 'canonical_url': 'https://explore.org/livecams/penguins/live-penguin-cam-2', 'latlong': ['33.762149', '-118.196981']},
    22: {'title': 'Puffin Burrow', 'slug': 'puffin-burrow-cam', 'youtube_id': 'LlDs56IyMwg', 'channel': 'Birds', 'cam_group': 'Puffins', 'cam_group_slug': 'puffins', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'puffin, bird, seabird, maine, audubon, burrow, nest, babies', 'canonical_url': 'https://explore.org/livecams/puffins/puffin-burrow-cam', 'latlong': ['43.893521', '-68.732796']},
    23: {'title': 'Puffin Loafing Ledge', 'slug': 'puffin-loafing-ledge-cam', 'youtube_id': 'ZY4GPM4_6rI', 'channel': 'Birds', 'cam_group': 'Puffins', 'cam_group_slug': 'puffins', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'burrow, nest, maine, live, birds, puffin, audubon', 'canonical_url': 'https://explore.org/livecams/puffins/puffin-loafing-ledge-cam', 'latlong': ['43.892642', '-68.732250']},
    37: {'title': 'Long-Eared Owl Nest', 'slug': 'long-eared-owl-cam', 'youtube_id': 'xWygD7kHTbY', 'channel': 'Birds', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': True, 'location': 'Missoula, Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'owl, bird, nest, montana, live', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/long-eared-owl-cam', 'latlong': ['46.878700', '-113.996600']},
    43: {'title': 'Charlo Great Horned Owl cam', 'slug': 'great-horned-owl-cam', 'youtube_id': '4gsz4ywAlLw', 'channel': 'Birds', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': False, 'location': 'Charlo, Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'bird, nest, owl, live, montana, horned', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/great-horned-owl-cam', 'latlong': ['47.693200', '-114.163100']},
    69: {'title': 'Puffin Boulder Berm', 'slug': 'puffin-boulder-berm-cam', 'youtube_id': 'yUE0AEwRu9s', 'channel': 'Birds', 'cam_group': 'Puffins', 'cam_group_slug': 'puffins', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'bird, seabird, maine, audubon, burrow, puffin, nesting, live', 'canonical_url': 'https://explore.org/livecams/puffins/puffin-boulder-berm-cam', 'latlong': ['43.893521', '-68.732796']},
    71: {'title': 'Guillemot Burrow', 'slug': 'guillemot-cam', 'youtube_id': 'cnYDB7ZoxAo', 'channel': 'Birds', 'cam_group': 'Birds', 'cam_group_slug': 'birds', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'guillemot, bird, seabird, maine, audubon, burrow, nest, live', 'canonical_url': 'https://explore.org/livecams/birds/guillemot-cam', 'latlong': ['43.893521', '-68.732796']},
    72: {'title': 'Arctic Snowy Owl - Nesting Cam', 'slug': 'arctic-snowy-owl-nesting-cam', 'youtube_id': '4LHbbQ5ZC58', 'channel': 'Birds', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': False, 'location': 'Utqiagvik, Alaska', 'partner': 'Owl Research Institute', 'tags': 'bird, arctic, alaska, owl, nest, live', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/arctic-snowy-owl-nesting-cam', 'latlong': ['71.292743', '-156.657489']},
    86: {'title': 'Bella Hummingbird Nest', 'slug': 'bella-hummingbird-nest', 'youtube_id': 'NXcGyKhjtbs', 'channel': 'Birds', 'cam_group': 'Hummingbirds', 'cam_group_slug': 'hummingbirds', 'live': False, 'location': 'La Verne, California, USA', 'partner': 'Hummingbirds', 'tags': 'bella, hummingbird, bird, nest, california, live', 'canonical_url': 'https://explore.org/livecams/hummingbirds/bella-hummingbird-nest', 'latlong': ['34.112015', '-117.765050']},
    93: {'title': 'Audubon Osprey Nest', 'slug': 'osprey-nest', 'youtube_id': 'O6Ir_sMsTtc', 'channel': 'Birds', 'cam_group': 'Ospreys', 'cam_group_slug': 'ospreys', 'live': True, 'location': 'Hog Island, Bremen, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'audubon, osprey, nest, maine, live, bird', 'canonical_url': 'https://explore.org/livecams/ospreys/osprey-nest', 'latlong': ['43.982194', '-69.418361']},
    108: {'title': 'Decorah North Eagles', 'slug': 'decorah-eagles-north-nest', 'youtube_id': 'GGIE1E-kaMQ', 'channel': 'Birds', 'cam_group': 'Bald Eagles', 'cam_group_slug': 'bald-eagles', 'live': True, 'location': 'Decorah, Iowa, USA', 'partner': 'Raptor Resource Project', 'tags': 'eagle, birds, nest, decorah, iowa, bald, raptor, live', 'canonical_url': 'https://explore.org/livecams/bald-eagles/decorah-eagles-north-nest', 'latlong': ['43.30331', '-91.78571']},
    109: {'title': 'Sauces Bald Eagles - Channel Islands', 'slug': 'channel-islands-national-park-sauces-bald-eagle', 'youtube_id': 'rnTsOesC6hE', 'channel': 'Birds', 'cam_group': 'Bald Eagles', 'cam_group_slug': 'bald-eagles', 'live': True, 'location': 'Santa Cruz Island, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'eagle, bird, california, nest, bald, live', 'canonical_url': 'https://explore.org/livecams/bald-eagles/channel-islands-national-park-sauces-bald-eagle', 'latlong': ['34.011170', '-119.873168']},
    114: {'title': 'Audubon Osprey Boat House', 'slug': 'audubon-boat-house-osprey-nest', 'youtube_id': 'z-eGhnlggLI', 'channel': 'Birds', 'cam_group': 'Ospreys', 'cam_group_slug': 'ospreys', 'live': True, 'location': 'Hog Island, Bremen, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'nest, osprey, birds, maine, audubon, live', 'canonical_url': 'https://explore.org/livecams/ospreys/audubon-boat-house-osprey-nest', 'latlong': ['43.982194', '-69.418361']},
    118: {'title': 'Osprey Nest - Charlo Montana', 'slug': 'charlo-montana-osprey-nest', 'youtube_id': '3VVoYO-ZFPE', 'channel': 'Birds', 'cam_group': 'Ospreys', 'cam_group_slug': 'ospreys', 'live': True, 'location': 'Charlo, Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'montana, osprey, nest, birds, live', 'canonical_url': 'https://explore.org/livecams/ospreys/charlo-montana-osprey-nest', 'latlong': ['47.438500', '-114.172300']},
    119: {'title': 'Great Spirit Bluff Falcons', 'slug': 'peregrine-falcon-cam', 'youtube_id': 'w-Vjv7Cr9Ss', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'La Crescent, Minnesota, USA', 'partner': 'Raptor Resource Project', 'tags': 'minnesota, falcons, nest, peregrine, raptor, live, birds', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/peregrine-falcon-cam', 'latlong': ['43.870853', '-91.319839']},
    133: {'title': 'Two Harbors Bald Eagle Cam', 'slug': 'bald-eagle-two-harbors', 'youtube_id': 'E5T2eHM8tcI', 'channel': 'Birds', 'cam_group': 'Bald Eagles', 'cam_group_slug': 'bald-eagles', 'live': True, 'location': 'Catalina Island, California, USA', 'partner': 'Institute for Wildlife Studies', 'tags': 'eagle, bird, california, nest, catalina, live, bald eagles', 'canonical_url': 'https://explore.org/livecams/bald-eagles/bald-eagle-two-harbors', 'latlong': ['33.434036', '-118.519806']},
    134: {'title': 'West End Bald Eagle Cam', 'slug': 'bald-eagle-west-end-catalina', 'youtube_id': 'RmmAzrAkKqI', 'channel': 'Birds', 'cam_group': 'Institute for Wildlife Studies', 'cam_group_slug': 'institute-for-wildlife-studies', 'live': True, 'location': 'Catalina Island, California, USA', 'partner': 'Institute for Wildlife Studies', 'tags': 'eagle, bird, california, nest, catalina, bald eagles, live', 'canonical_url': 'https://explore.org/livecams/institute-for-wildlife-studies/bald-eagle-west-end-catalina', 'latlong': ['33.475177', '-118.598221']},
    138: {'title': 'Anacapa Peregrine Falcon Cam', 'slug': 'peregrine-falcon-anacapa', 'youtube_id': 'zo7LeYvnCUY', 'channel': 'Birds', 'cam_group': 'Falcons', 'cam_group_slug': 'falcons', 'live': True, 'location': 'Anacapa Island - Channel Islands, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'falcons, nest, live, birds, anacapa', 'canonical_url': 'https://explore.org/livecams/falcons/peregrine-falcon-anacapa', 'latlong': ['34.016457', '-119.362151']},
    140: {'title': 'Alligator Swamp and Spoonbills', 'slug': 'alligator-spoonbill-swamp-cam', 'youtube_id': 'qopGW_Hkdd8', 'channel': 'Birds', 'cam_group': 'Spoonbills', 'cam_group_slug': 'spoonbills', 'live': True, 'location': 'St. Augustine, Florida, USA', 'partner': 'St. Augustine Alligator Farm', 'tags': 'reptiles, nest, spoonbills, storks, birds, alligators, swamp, florida, live', 'canonical_url': 'https://explore.org/livecams/spoonbills/alligator-spoonbill-swamp-cam', 'latlong': ['29.881661', '-81.288894']},
    141: {'title': "Great Blue Heron's Nest", 'slug': 'great-blue-herons-chesapeake-conservancy', 'youtube_id': 'WlFi0bjVxTo', 'channel': 'Birds', 'cam_group': 'Chesapeake Conservancy', 'cam_group_slug': 'chesapeake-conservancy', 'live': True, 'location': "Maryland's Eastern Shore", 'partner': 'Chesapeake Conservancy', 'tags': 'maryland, nest, heron, birds, live, chesapeake', 'canonical_url': 'https://explore.org/livecams/chesapeake-conservancy/great-blue-herons-chesapeake-conservancy', 'latlong': ['38.391683', '-75.164918']},
    142: {'title': 'Osprey Nest - Chesapeake Conservancy', 'slug': 'osprey-cam-chesapeake-conservancy', 'youtube_id': 'M9pA4F7J1Go', 'channel': 'Birds', 'cam_group': 'Ospreys', 'cam_group_slug': 'ospreys', 'live': True, 'location': 'Kent Island, Maryland, USA', 'partner': 'Chesapeake Conservancy', 'tags': 'maryland, nest, osprey, birds, chesapeake, live', 'canonical_url': 'https://explore.org/livecams/ospreys/osprey-cam-chesapeake-conservancy', 'latlong': ['38.974621', '-76.326424']},
    143: {'title': 'Peregrine Falcons', 'slug': 'peregrine-falcon-chesapeake-conservancy', 'youtube_id': 'Ffe3LEVSLKM', 'channel': 'Birds', 'cam_group': 'Falcons', 'cam_group_slug': 'falcons', 'live': True, 'location': 'Baltimore, Maryland, USA', 'partner': 'Chesapeake Conservancy', 'tags': 'falcons, peregrine falcon, maryland, nest, chesapeake, birds, live', 'canonical_url': 'https://explore.org/livecams/falcons/peregrine-falcon-chesapeake-conservancy', 'latlong': ['39.287291', '-76.614449']},
    145: {'title': 'West End Bald Eagle Overlook', 'slug': 'west-end-overlook-catalina', 'youtube_id': 'kad6O4nF6bg', 'channel': 'Birds', 'cam_group': 'Institute for Wildlife Studies', 'cam_group_slug': 'institute-for-wildlife-studies', 'live': True, 'location': 'Catalina Island, California, USA', 'partner': 'Institute for Wildlife Studies', 'tags': 'sunset, sunsets, oceans, eagle, bird, california, nest, catalina, live', 'canonical_url': 'https://explore.org/livecams/institute-for-wildlife-studies/west-end-overlook-catalina', 'latlong': ['33.475177', '-118.598221']},
    146: {'title': 'Great Spirit Bluff Falcons - Cliff View', 'slug': 'falcon-nest-cam', 'youtube_id': 'Vyh0NdAygyY', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'La Crescent, Minnesota, USA', 'partner': 'Raptor Resource Project', 'tags': 'minnesota, falcons, nest, peregrine falcon, birds, live, raptor, Great Spirit Bluff - Cliff View, cl', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/falcon-nest-cam', 'latlong': ['43.870853', '-91.319839']},
    153: {'title': 'Great Gray Owl Nest', 'slug': 'great-gray-owl-nest', 'youtube_id': 'lqmocuzYHfU', 'channel': 'Birds', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': False, 'location': 'Western Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'owls, owl, nest, montana, bird, birds, gray owl, live', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/great-gray-owl-nest', 'latlong': ['48.191989', '-114.316813']},
    189: {'title': 'Osprey Nest Branch View', 'slug': 'osprey-nest-branch-view', 'youtube_id': 'uV6iMXBYu6Q', 'channel': 'Birds', 'cam_group': 'National Audubon Society', 'cam_group_slug': 'national-audubon-society', 'live': False, 'location': 'Hog Island, Bremen, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'audubon, hog island, maine, bird, osprey, nest, live, birds', 'canonical_url': 'https://explore.org/livecams/national-audubon-society/osprey-nest-branch-view', 'latlong': ['43.978808', '-69.417246']},
    199: {'title': 'Decorah Eagles', 'slug': 'decorah-eagles', 'youtube_id': 'IVmL3diwJuw', 'channel': 'Birds', 'cam_group': 'Bald Eagles', 'cam_group_slug': 'bald-eagles', 'live': True, 'location': 'Decorah, Iowa, USA', 'partner': 'Raptor Resource Project', 'tags': 'eagle, birds, nest, decorah, bald eagles, iowa, raptor, live', 'canonical_url': 'https://explore.org/livecams/bald-eagles/decorah-eagles', 'latlong': ['43.275813', '-91.779292']},
    210: {'title': 'Fraser Point Bald Eagle', 'slug': 'fraser-point-bald-eagle', 'youtube_id': 'aqahkzVVsoQ', 'channel': 'Birds', 'cam_group': 'Bald Eagles', 'cam_group_slug': 'bald-eagles', 'live': False, 'location': 'Santa Cruz Island, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'birds, bald eagles, eagles, nest, channel islands, live', 'canonical_url': 'https://explore.org/livecams/bald-eagles/fraser-point-bald-eagle', 'latlong': ['34.050000', '-119.900000']},
    211: {'title': 'Two Harbors Overlook', 'slug': 'catalina-harbor-cam', 'youtube_id': '2yx7RKxpyzQ', 'channel': 'Birds', 'cam_group': 'Institute for Wildlife Studies', 'cam_group_slug': 'institute-for-wildlife-studies', 'live': True, 'location': 'Catalina Island, California, USA', 'partner': 'Institute for Wildlife Studies', 'tags': 'eagle, bird, california, nest, catalina, catalina bald eagles, ocean, live', 'canonical_url': 'https://explore.org/livecams/institute-for-wildlife-studies/catalina-harbor-cam', 'latlong': ['33.434036', '-118.519806']},
    223: {'title': 'Puffin Burrow - Exterior View', 'slug': 'puffin-burrow-exterior-view', 'youtube_id': 'uNgGsLOZKxA', 'channel': 'Birds', 'cam_group': 'Puffins', 'cam_group_slug': 'puffins', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'puffin, bird, seabird, maine, audubon, burrow, nest, live', 'canonical_url': 'https://explore.org/livecams/puffins/puffin-burrow-exterior-view', 'latlong': ['43.893521', '-68.732796']},
    228: {'title': 'Big Sur Condor Roost cam', 'slug': 'condors-castle-nest', 'youtube_id': 'T1qVUbMVuU4', 'channel': 'Birds', 'cam_group': 'California Condors', 'cam_group_slug': 'condors', 'live': True, 'location': 'Big Sur, California', 'partner': 'Ventana Wildlife Society', 'tags': 'condors, live, birds, big sur, ventana, california, nest', 'canonical_url': 'https://explore.org/livecams/condors/condors-castle-nest', 'latlong': ['36.361475', '-121.856261']},
    230: {'title': 'California Condor Sanctuary', 'slug': 'california-condor-sanctuary', 'youtube_id': 'VOFTpk2O-8U', 'channel': 'Birds', 'cam_group': 'California Condors', 'cam_group_slug': 'condors', 'live': True, 'location': 'Big Sur, California', 'partner': 'Ventana Wildlife Society', 'tags': 'condors, birds, big sur, live, california, ventana', 'canonical_url': 'https://explore.org/livecams/condors/california-condor-sanctuary', 'latlong': ['36.361475', '-121.856261']},
    231: {'title': 'Redwood Grove Condor Nest Camera', 'slug': 'california-condors-redwood-grove', 'youtube_id': 'cbF00ol0glc', 'channel': 'Birds', 'cam_group': 'California Condors', 'cam_group_slug': 'condors', 'live': True, 'location': 'Big Sur, California', 'partner': 'Ventana Wildlife Society', 'tags': 'condors, birds, live, big sur, nest, california, ventana, redwood, condor', 'canonical_url': 'https://explore.org/livecams/condors/california-condors-redwood-grove', 'latlong': ['36.361475', '-121.856261']},
    238: {'title': 'Mississippi River Flyway Cam', 'slug': 'mississippi-river-flyway-cam', 'youtube_id': 'Hkj9L-HKXJU', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'Brice Prairie, Wisconsin', 'partner': 'Raptor Resource Project', 'tags': 'mississippi, birds, river, pelicans, cranes, ducks, wisconsin, live, raptor, eagles', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/mississippi-river-flyway-cam', 'latlong': ['43.915521', '-91.317321']},
    240: {'title': 'Panama Fruit Feeder Cam at Canopy Lodge', 'slug': 'panama-fruit-feeder', 'youtube_id': 'VfFfS64rtZE', 'channel': 'Birds', 'cam_group': 'Birds', 'cam_group_slug': 'birds', 'live': True, 'location': 'Anton Valley, Panama', 'partner': 'Cornell Lab of Ornithology & The Canopy Family', 'tags': 'panama, birds, live, cornell', 'canonical_url': 'https://explore.org/livecams/birds/panama-fruit-feeder', 'latlong': ['8.621353', '-80.139592']},
    278: {'title': "Audubon's Rowe Sanctuary's Crane Camera", 'slug': 'crane-camera', 'youtube_id': 'wDYrRVUPWRo', 'channel': 'Birds', 'cam_group': 'National Audubon Society', 'cam_group_slug': 'national-audubon-society', 'live': True, 'location': 'Gibbon, NE', 'partner': "Audubon's Rowe Sanctuary", 'tags': 'national audubon society, crane, migration', 'canonical_url': 'https://explore.org/livecams/national-audubon-society/crane-camera', 'latlong': ['40.669940', '-98.884670']},
    293: {'title': 'Condor Sanctuary in San Simeon', 'slug': 'condor-san-simeon', 'youtube_id': '1a1z4M80BXg', 'channel': 'Birds', 'cam_group': 'California Condors', 'cam_group_slug': 'condors', 'live': True, 'location': 'San Simeon, CA', 'partner': 'Ventana Wildlife Society', 'tags': 'condor, live condor, ventana wildlife society, ventana condors', 'canonical_url': 'https://explore.org/livecams/condors/condor-san-simeon', 'latlong': ['35.650848', '-121.186111']},
    295: {'title': 'Perch Cam- Cape Tower, Wapusk National Park', 'slug': 'churchill-raven-nest', 'youtube_id': '_-gyL7TNVc8', 'channel': 'Birds', 'cam_group': 'Birds', 'cam_group_slug': 'birds', 'live': False, 'location': 'Wapusk National Park, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'raven, nest, bird, birds, raven nest', 'canonical_url': 'https://explore.org/livecams/birds/churchill-raven-nest', 'latlong': ['58.786516', '-93.685949']},
    298: {'title': 'Sacramento National Wildlife Refuge Webcam', 'slug': 'sacramento-wildlife-refuge-cam', 'youtube_id': 'DB4LDyWHawY', 'channel': 'Birds', 'cam_group': 'Friends of Sacramento National Wildlife Refuge', 'cam_group_slug': 'sacramento-wildlife-refuge', 'live': True, 'location': 'Willows, California', 'partner': 'Friends of Sacramento National Wildlife Refuge', 'tags': 'Friends of Sacramento, snow geese, water fowl, migration, bird', 'canonical_url': 'https://explore.org/livecams/sacramento-wildlife-refuge/sacramento-wildlife-refuge-cam', 'latlong': ['39.429400', '-122.187100']},
    309: {'title': 'Fraser Point Bald Eagle Nest 2', 'slug': 'fraser-point-bald-eagle-nest', 'youtube_id': 'OY4V_AppZ6s', 'channel': 'Birds', 'cam_group': 'Institute for Wildlife Studies', 'cam_group_slug': 'institute-for-wildlife-studies', 'live': True, 'location': 'Santa Cruz Island, California, USA', 'partner': 'Institute for Wildlife Studies', 'tags': 'fraser point, fraser point bald eagles, bald eagles, institute for wildlife studies, channel islands', 'canonical_url': 'https://explore.org/livecams/institute-for-wildlife-studies/fraser-point-bald-eagle-nest', 'latlong': ['34.050000', '-119.900000']},
    312: {'title': 'Osprey – Canada Goose at Rogers Place', 'slug': 'rogers-place-nest-camera', 'youtube_id': 'la9vMPCsTOQ', 'channel': 'Birds', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': True, 'location': 'Charlo, Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'osprey, canada goose, goose, rogers place', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/rogers-place-nest-camera', 'latlong': ['47.438500', '-114.172300']},
    320: {'title': 'Toucan TV', 'slug': 'toucan-tv', 'youtube_id': 'mZMEkuxAskU', 'channel': 'Birds', 'cam_group': 'Sloth', 'cam_group_slug': 'sloth', 'live': True, 'location': 'Heredia Province, Costa Rica', 'partner': 'Toucan Rescue Ranch', 'tags': '', 'canonical_url': 'https://explore.org/livecams/sloth/toucan-tv', 'latlong': ['10.025400', '-84.046800']},
    325: {'title': 'Decorah Goose Cam', 'slug': 'decorah-goose-cam', 'youtube_id': 'IeZGXnPcM8Q', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'Decorah, Iowa, USA', 'partner': 'Raptor Resource Project', 'tags': 'goose, canada goose, raptor resource project, Decorah Goose Cam', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/decorah-goose-cam', 'latlong': ['43.275813', '-91.779292']},
    326: {'title': 'ORI Farm Roost Camera', 'slug': 'farm-roost', 'youtube_id': 'ZXqeAhQDIfQ', 'channel': 'Birds', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': True, 'location': 'Charlo, Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'owl research institute, farm roost, farm roost camera', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/farm-roost', 'latlong': ['47.438500', '-114.172300']},
    330: {'title': 'Bracken Bat Cave Viewing Area', 'slug': 'bracken-bats-outside', 'youtube_id': 'XSBhpEzB4MM', 'channel': 'Birds', 'cam_group': 'Bat Conservation International', 'cam_group_slug': 'bci', 'live': False, 'location': 'San Antonio, TX', 'partner': 'Bat Conservation International', 'tags': 'bat, bats, Bat Conservation International, BCI', 'canonical_url': 'https://explore.org/livecams/bci/bracken-bats-outside', 'latlong': ['29.68739', '-98.35253']},
    331: {'title': 'Inside Bracken Bat Cave', 'slug': 'bracken-bats-inside', 'youtube_id': 'CY_O5xFcAqQ', 'channel': 'Birds', 'cam_group': 'Bat Conservation International', 'cam_group_slug': 'bci', 'live': False, 'location': 'San Antonio, TX', 'partner': 'Bat Conservation International', 'tags': '', 'canonical_url': 'https://explore.org/livecams/bci/bracken-bats-inside', 'latlong': ['29.68692', '-98.35252']},
    347: {'title': 'Philippine Eagles', 'slug': 'philippine-eagles', 'youtube_id': 'QoKy-rn66og', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'Mindanao, Philippine', 'partner': 'Philippine Eagle Foundation and Raptor Resource Project', 'tags': 'philippine, philippine eagle, eagle cam, Philippine Eagle Foundation, eagle, eagles', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/philippine-eagles', 'latlong': ['7.051400', '125.594770']},
    348: {'title': 'Roving Camera at Bracken Bat Cave', 'slug': 'bracken-bats-roving', 'youtube_id': '_FPfeMpvXns', 'channel': 'Birds', 'cam_group': 'Bat Conservation International', 'cam_group_slug': 'bci', 'live': False, 'location': 'San Antonio, TX', 'partner': 'Bat Conservation International', 'tags': '', 'canonical_url': 'https://explore.org/livecams/bci/bracken-bats-roving', 'latlong': ['29.68692', '-98.35252']},
    354: {'title': 'Castle Rock Falcons', 'slug': 'castle-rock-falcons', 'youtube_id': 'Pr9acykT_yY', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'Fountain City Wisconsin', 'partner': 'Raptor Resource Project', 'tags': 'falcon, peregrine falcon, raptor resource project, castle rock falcons', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/castle-rock-falcons', 'latlong': ['44.07867758776925', '-91.64209865916517']},
    357: {'title': 'Castle Rock Falcons - Cliff View', 'slug': 'castle-rock-falcons-cliff', 'youtube_id': 'fRZfmrpAAM0', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'Fountain City Wisconsin', 'partner': 'Raptor Resource Project', 'tags': 'falcon, peregrine falcons, raptor resource project, castle rock falcons', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/castle-rock-falcons-cliff', 'latlong': ['44.07867758776925', '-91.64209865916517']},
    358: {'title': 'Trempealeau Eagles', 'slug': 'trempealeau-eagles', 'youtube_id': '8bMrSm0Ap20', 'channel': 'Birds', 'cam_group': 'Raptor Resource Project', 'cam_group_slug': 'raptor-resource-project', 'live': True, 'location': 'Trempealeau, Wisconsin', 'partner': 'Raptor Resource Project', 'tags': 'raptor resource project, bald eagles, eagles, trempealeau', 'canonical_url': 'https://explore.org/livecams/raptor-resource-project/trempealeau-eagles', 'latlong': ['44.003966', '-91.442950']},
    359: {'title': 'West End Nest Low Cam', 'slug': 'bald-eagle-west-end-catalina-low', 'youtube_id': 'wfuqjSNXZ14', 'channel': 'Birds', 'cam_group': 'Institute for Wildlife Studies', 'cam_group_slug': 'institute-for-wildlife-studies', 'live': True, 'location': 'Catalina Island, California, USA', 'partner': 'Institute for Wildlife Studies', 'tags': 'bald eagles, eagle, catalina island, institute for wildlife studies', 'canonical_url': 'https://explore.org/livecams/institute-for-wildlife-studies/bald-eagle-west-end-catalina-low', 'latlong': ['33.475177', '-118.598221']},
    361: {'title': 'Panama Hummingbird Feeder at Canopy Tower', 'slug': 'panama-hummingbird-feeder', 'youtube_id': 'X5Kubf-twKw', 'channel': 'Birds', 'cam_group': 'Panama Canopy', 'cam_group_slug': 'panama-canopy', 'live': True, 'location': 'Canopy Tower, Panama', 'partner': 'Cornell Lab of Ornithology & The Canopy Family', 'tags': '', 'canonical_url': 'https://explore.org/livecams/panama-canopy/panama-hummingbird-feeder', 'latlong': ['9.0776704', '-79.6492934']},
    362: {'title': 'Macaw Feeder High Camera', 'slug': 'macaw-high', 'youtube_id': 'ietpaFoB_Nc', 'channel': 'Birds', 'cam_group': 'Macaw Recovery Network', 'cam_group_slug': 'macaw-recovery-network', 'live': True, 'location': 'Punta Islita, Costa Rica', 'partner': 'Macaw Recovery Network', 'tags': 'Macaw, MRN, Macaw Recovery Network, Scarlet Macaw', 'canonical_url': 'https://explore.org/livecams/macaw-recovery-network/macaw-high', 'latlong': ['9.8566109', '-85.3988579']},
    363: {'title': 'Macaw Feeder Low Cam', 'slug': 'macaw-low', 'youtube_id': 'vLscZvIFiLg', 'channel': 'Birds', 'cam_group': 'Macaw Recovery Network', 'cam_group_slug': 'macaw-recovery-network', 'live': True, 'location': 'Punta Islita, Costa Rica', 'partner': 'Macaw Recovery Network', 'tags': 'Macaw, Scarlet Macaw, Macaw Recovery Network, MRN', 'canonical_url': 'https://explore.org/livecams/macaw-recovery-network/macaw-low', 'latlong': ['9.8566109', '-85.3988579']},
    367: {'title': 'Condor Pen Camera', 'slug': 'condor-pen-camera', 'youtube_id': 'lxgZvK6vrC4', 'channel': 'Birds', 'cam_group': 'California Condors', 'cam_group_slug': 'condors', 'live': True, 'location': 'Big Sur, California', 'partner': 'Ventana Wildlife Society', 'tags': 'condor, Condor pen, california condor, ventana wildlife society, ventana, ventana condors', 'canonical_url': 'https://explore.org/livecams/condors/condor-pen-camera', 'latlong': ['36.1539', '-121.66']},
    370: {'title': 'Ash Canyon Bird Sanctuary Viewing Area', 'slug': 'sabo-viewing-area', 'youtube_id': 'vjpj_DXODdA', 'channel': 'Birds', 'cam_group': 'Southeastern Arizona Bird Observatory', 'cam_group_slug': 'sabo', 'live': True, 'location': 'Cochise County, Arizona', 'partner': 'Southeastern Arizona Bird Observatory, Inc.', 'tags': '', 'canonical_url': 'https://explore.org/livecams/sabo/sabo-viewing-area', 'latlong': ['31.389727', '-110.240413']},
    371: {'title': 'Ash Canyon Bird Sanctuary Back Porch', 'slug': 'sabo-back-porch', 'youtube_id': 'AwlpXN2QyjM', 'channel': 'Birds', 'cam_group': 'Southeastern Arizona Bird Observatory', 'cam_group_slug': 'sabo', 'live': True, 'location': 'Cochise County, Arizona', 'partner': 'Southeastern Arizona Bird Observatory, Inc.', 'tags': '', 'canonical_url': 'https://explore.org/livecams/sabo/sabo-back-porch', 'latlong': ['31.389727', '-110.240413']},
    372: {'title': 'Magellanic Penguin Nest - Isla Tova', 'slug': 'rewilding-penguin-nest', 'youtube_id': 'Fc2qzWsh_-M', 'channel': 'Birds', 'cam_group': 'Rewilding Argentina', 'cam_group_slug': 'rewilding-argentina', 'live': True, 'location': 'Isla Tova, Patagonia Azul Provincial Park, Chubut, Argentina', 'partner': 'Rewilding Argentina', 'tags': '', 'canonical_url': 'https://explore.org/livecams/rewilding-argentina/rewilding-penguin-nest', 'latlong': ['-45.101665', '-65.989444']},
    373: {'title': 'Imperial Cormorant Colony - Isla Tovita', 'slug': 'rewilding-cormorant', 'youtube_id': 'jvOiJ9yQH8w', 'channel': 'Birds', 'cam_group': 'Rewilding Argentina', 'cam_group_slug': 'rewilding-argentina', 'live': True, 'location': 'Isla Tova, Patagonia Azul Provincial Park, Chubut, Argentina', 'partner': 'Rewilding Argentina', 'tags': '', 'canonical_url': 'https://explore.org/livecams/rewilding-argentina/rewilding-cormorant', 'latlong': ['-45.119151', '-65.947687']},
    374: {'title': 'Southern Giant Petrel Colony - Isla Gran Robredo', 'slug': 'rewilding-petral', 'youtube_id': 'jH0CwzRf5mw', 'channel': 'Birds', 'cam_group': 'Rewilding Argentina', 'cam_group_slug': 'rewilding-argentina', 'live': False, 'location': 'Isla Gran Robredo, Patagonia Azul Provincial Park, Chubut, Argentina', 'partner': 'Rewilding Argentina', 'tags': '', 'canonical_url': 'https://explore.org/livecams/rewilding-argentina/rewilding-petral', 'latlong': ['-45.129939', '-66.059987']},
    376: {'title': 'Great Green Macaw Nest - Sarapiquí Rainforest Reserve', 'slug': 'macaw-nest', 'youtube_id': '2FdvAk95PSk', 'channel': 'Birds', 'cam_group': 'Macaw Recovery Network', 'cam_group_slug': 'macaw-recovery-network', 'live': True, 'location': 'Sarapiquí Rainforest Reserve, Heredia province, Costa Rica', 'partner': 'Macaw Recovery Network', 'tags': 'Macaw, Macaw Recovery Network, macaw nest, nest, green macaw', 'canonical_url': 'https://explore.org/livecams/macaw-recovery-network/macaw-nest', 'latlong': ['9.8566109', '-85.3988579']},
    381: {'title': 'Beatrix Hummingbird', 'slug': 'beatrix-hummingbird-santee', 'youtube_id': 'PbMU7UbONbU', 'channel': 'Birds', 'cam_group': 'Hummingbirds', 'cam_group_slug': 'hummingbirds', 'live': True, 'location': 'Santee, California', 'partner': 'Santee Hummingbirds', 'tags': 'hummingbird, beatrix, beatrix hummingbird, hummingbird nest', 'canonical_url': 'https://explore.org/livecams/hummingbirds/beatrix-hummingbird-santee', 'latlong': ['32.870656', '-116.969910']},
    382: {'title': 'Joy Hummingbird', 'slug': 'joy-hummingbird-santee', 'youtube_id': 'PCarPD6ha9g', 'channel': 'Birds', 'cam_group': 'Hummingbirds', 'cam_group_slug': 'hummingbirds', 'live': True, 'location': 'Santee, California', 'partner': 'Santee Hummingbirds', 'tags': 'joy hummingbird, joy, hummingbird, hummingbird nest, santee', 'canonical_url': 'https://explore.org/livecams/hummingbirds/joy-hummingbird-santee', 'latlong': ['32.870656', '-116.969910']},
    # --- Bison ---
    46: {'title': 'Bison Watering Hole', 'slug': 'plains-bison-grasslands-national-park-cam-1', 'youtube_id': 'tJ0fHAHihPA', 'channel': 'Bison', 'cam_group': 'Bison', 'cam_group_slug': 'bison', 'live': True, 'location': 'Val Marie, Saskatchewan, Canada', 'partner': 'Grasslands National Park', 'tags': 'bison, canada, grasslands, buffalo, live', 'canonical_url': 'https://explore.org/livecams/bison/plains-bison-grasslands-national-park-cam-1', 'latlong': ['49.198279', '-107.564093']},
    70: {'title': 'Bison Calving Plains', 'slug': 'plains-bison-grasslands-national-park-cam-3', 'youtube_id': 'T-iBupPtIFw', 'channel': 'Bison', 'cam_group': 'Bison', 'cam_group_slug': 'bison', 'live': True, 'location': 'Val Marie, Saskatchewan, Canada', 'partner': 'Grasslands National Park', 'tags': 'canada, grasslands, bison, buffalo, live', 'canonical_url': 'https://explore.org/livecams/bison/plains-bison-grasslands-national-park-cam-3', 'latlong': ['49.171716', '-107.427958']},
    # --- Cat Rescues ---
    44: {'title': 'Kitten Rescue Sanctuary', 'slug': 'kitten-rescue-cam', 'youtube_id': '-m_nQT62B4Y', 'channel': 'Cat Rescues', 'cam_group': 'Kitten Rescue', 'cam_group_slug': 'kitten-rescue', 'live': True, 'location': 'Los Angeles, California, USA', 'partner': 'Kitten Rescue', 'tags': 'kittens, cats, live, rescue, los angeles', 'canonical_url': 'https://explore.org/livecams/kitten-rescue/kitten-rescue-cam', 'latlong': ['34.051996', '-118.244576']},
    116: {'title': 'Kitten Rescue Nursery and Special Needs Cats', 'slug': 'kitten-rescue-baby-kittens', 'youtube_id': 'o8YhyLb__cI', 'channel': 'Cat Rescues', 'cam_group': 'Kitten Rescue', 'cam_group_slug': 'kitten-rescue', 'live': True, 'location': 'Los Angeles, California, USA', 'partner': 'Kitten Rescue', 'tags': 'kittens, cats, rescue, los angeles, california, live, adoption, adopt', 'canonical_url': 'https://explore.org/livecams/kitten-rescue/kitten-rescue-baby-kittens', 'latlong': ['34.051996', '-118.244576']},
    335: {'title': 'Dutchess the Tiger Cam at Turpentine Creek', 'slug': 'turpentine-creek-dutchess', 'youtube_id': '5vvWqjygRtI', 'channel': 'Cat Rescues', 'cam_group': 'Cats', 'cam_group_slug': 'cats', 'live': True, 'location': 'Eureka Springs, Arkansas', 'partner': 'Turpentine Creek Wildlife Refuge', 'tags': 'Duchess, tiger, turpentine creek', 'canonical_url': 'https://explore.org/livecams/cats/turpentine-creek-dutchess', 'latlong': ['36.310490', '-93.757550']},
    336: {'title': 'Max the Tiger Cam at Turpentine Creek', 'slug': 'turpentine-creek-max', 'youtube_id': 'PcAOecvAh1U', 'channel': 'Cat Rescues', 'cam_group': 'Cats', 'cam_group_slug': 'cats', 'live': True, 'location': 'Eureka Springs, Arkansas', 'partner': 'Turpentine Creek Wildlife Refuge', 'tags': 'max, max the tiger, turpentine creek, tiger', 'canonical_url': 'https://explore.org/livecams/cats/turpentine-creek-max', 'latlong': ['36.310490', '-93.757550']},
    337: {'title': 'Doj, Jinx, Rosie at Turpentine Creek', 'slug': 'turpentine-creek-aria', 'youtube_id': 'eeMDlq_kQpQ', 'channel': 'Cat Rescues', 'cam_group': 'Cats', 'cam_group_slug': 'cats', 'live': True, 'location': 'Eureka Springs, Arkansas', 'partner': 'Turpentine Creek Wildlife Refuge', 'tags': 'aria, aria the tiger, tiger, turpentine creek', 'canonical_url': 'https://explore.org/livecams/cats/turpentine-creek-aria', 'latlong': ['36.310490', '-93.757550']},
    338: {'title': 'Jasmine the Tiger Cam at Turpentine Creek', 'slug': 'turpentine-creek-jasmine', 'youtube_id': 'dXKCmOEq3ns', 'channel': 'Cat Rescues', 'cam_group': 'Cats', 'cam_group_slug': 'cats', 'live': True, 'location': 'Eureka Springs, Arkansas', 'partner': 'Turpentine Creek Wildlife Refuge', 'tags': 'tiger, turpentine creek, Turpentine creek wildlife rescue, Jasmine the tiger, Jasmine', 'canonical_url': 'https://explore.org/livecams/cats/turpentine-creek-jasmine', 'latlong': ['36.310490', '-93.757550']},
    339: {'title': 'FeLV Suite at Kitten Rescue, Los Angeles', 'slug': 'kitten-rescue-felv-suite', 'youtube_id': 'n_cjSaNKyFE', 'channel': 'Cat Rescues', 'cam_group': 'Kitten Rescue', 'cam_group_slug': 'kitten-rescue', 'live': True, 'location': 'Los Angeles, California, USA', 'partner': 'Kitten Rescue', 'tags': 'kitten rescue, felv suite, FeLV', 'canonical_url': 'https://explore.org/livecams/kitten-rescue/kitten-rescue-felv-suite', 'latlong': ['34.051996', '-118.244576']},
    # --- Curators ---
    110: {'title': 'Fallujah: The Opera', 'slug': 'fallujah-the-opera', 'youtube_id': 'HPZ9SHjb40A', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Long Beach, CA', 'partner': 'Explore.org', 'tags': 'opera, fallujah, long beach opera, iraq, veteran, live, explore', 'canonical_url': 'https://explore.org/livecams/documentary-films/fallujah-the-opera', 'latlong': ['33.762149', '-118.196981']},
    201: {'title': 'Explore Live Events', 'slug': 'explore-live-events', 'youtube_id': '-wvmSOs_PB4', 'channel': 'Curators', 'cam_group': 'Live Chats', 'cam_group_slug': 'live-chats', 'live': False, 'location': 'Santa Monica, CA, USA', 'partner': 'Explore.org', 'tags': 'live chats, experts', 'canonical_url': 'https://explore.org/livecams/live-chats/explore-live-events', 'latlong': ['34.015342', '-118.499083']},
    253: {'title': 'Buried Alive', 'slug': 'buried-alive', 'youtube_id': 'l2Zf3sv-VHI', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Jackson Hole, Wyoming', 'partner': 'Explore.org', 'tags': 'buried alive, avalanche', 'canonical_url': 'https://explore.org/livecams/documentary-films/buried-alive', 'latlong': ['34.015342', '-118.499083']},
    254: {'title': 'No Child is Born a Terrorist', 'slug': 'no-child-is-born-a-terrorist', 'youtube_id': 'YFWrVAF-sxk', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Palestine', 'partner': 'Explore.org', 'tags': 'Palestine, No Child Is Born a Terrorist', 'canonical_url': 'https://explore.org/livecams/documentary-films/no-child-is-born-a-terrorist', 'latlong': ['34.015342', '-118.499083']},
    255: {'title': 'Hillbillies, Coalminers, Treehuggers and God', 'slug': 'coalminers', 'youtube_id': 'FwWWG0RB7B0', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'West Virginia, US', 'partner': 'Explore.org', 'tags': 'west virginia, coalminers', 'canonical_url': 'https://explore.org/livecams/documentary-films/coalminers', 'latlong': ['38.919739', '-80.181679']},
    256: {'title': 'Spiritual India: River of Compassion', 'slug': 'spiritual-india', 'youtube_id': 'y_QedWkOOqM', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'India', 'partner': 'Explore.org', 'tags': 'india, spiritual india, Documentary films', 'canonical_url': 'https://explore.org/livecams/documentary-films/spiritual-india', 'latlong': ['21.7866', '82.794762']},
    257: {'title': 'Fish Out Of Water', 'slug': 'fish-out-of-water', 'youtube_id': 'jWe4PV8ANvw', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Sun Valley, Idaho', 'partner': 'Explore.org', 'tags': 'fish out of water, Documentary films', 'canonical_url': 'https://explore.org/livecams/documentary-films/fish-out-of-water', 'latlong': ['34.015342', '-118.499083']},
    258: {'title': 'Grand Canyon', 'slug': 'grand-canyon', 'youtube_id': '2B1QSfUoEA4', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Grand Canyon National Park', 'partner': 'Explore.org', 'tags': 'Documentary films, grand canyon', 'canonical_url': 'https://explore.org/livecams/documentary-films/grand-canyon', 'latlong': ['34.015342', '-118.499083']},
    259: {'title': 'Detroit - The Renaissance of America', 'slug': 'detroit', 'youtube_id': '9AS8gqSLlS8', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Detroit, Michigan', 'partner': 'Explore.org', 'tags': 'detroit, Documentary films, film', 'canonical_url': 'https://explore.org/livecams/documentary-films/detroit', 'latlong': ['42.33143', '-83.04575']},
    260: {'title': 'Blessissippi', 'slug': 'blessissippi', 'youtube_id': 'Z1CKwRXfwzQ', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Mississippi, USA', 'partner': 'Explore.org', 'tags': 'blessissippi, Documentary films', 'canonical_url': 'https://explore.org/livecams/documentary-films/blessissippi', 'latlong': ['32.35467', '-89.39853']},
    261: {'title': 'Father Damien of Molokai', 'slug': 'father-damien', 'youtube_id': 'o7PuqdymSdo', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Hawaii, USA', 'partner': 'Explore.org', 'tags': 'Documentary films, hawaii', 'canonical_url': 'https://explore.org/livecams/documentary-films/father-damien', 'latlong': ['19.58964', '-155.434036']},
    262: {'title': "Jack Johnson's Music Lessons", 'slug': 'jack-johnson', 'youtube_id': 'M1Y02LgPGyY', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Hawaii, USA', 'partner': 'Explore.org', 'tags': 'Documentary films', 'canonical_url': 'https://explore.org/livecams/documentary-films/jack-johnson', 'latlong': ['19.58964', '-155.434036']},
    263: {'title': 'Traveling with Jihad', 'slug': 'traveling-with-jihad', 'youtube_id': 'lNNUBfv0Rjw', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Middle East', 'partner': 'Explore.org', 'tags': 'Documentary films, islam', 'canonical_url': 'https://explore.org/livecams/documentary-films/traveling-with-jihad', 'latlong': ['34.015342', '-118.499083']},
    264: {'title': 'Sam Sullivan: Life in a Wheel', 'slug': 'life-in-a-wheel', 'youtube_id': 'ttUHcpuwgmA', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Vancouver, Canada', 'partner': 'Explore.org', 'tags': 'Documentary films, canada', 'canonical_url': 'https://explore.org/livecams/documentary-films/life-in-a-wheel', 'latlong': ['62.35873', '-96.582092']},
    265: {'title': 'Salem Witch Hunt', 'slug': 'salem-witch-hunt', 'youtube_id': 'UfQhqTTeBB4', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Salem, MA', 'partner': 'Explore.org', 'tags': 'Documentary films, salem', 'canonical_url': 'https://explore.org/livecams/documentary-films/salem-witch-hunt', 'latlong': ['42.5224', '-70.895813']},
    266: {'title': 'Rescue Foundation', 'slug': 'rescue-foundation', 'youtube_id': 'jOkRDSLBN4A', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Mumbai, India', 'partner': 'Explore.org', 'tags': 'Documentary films, india', 'canonical_url': 'https://explore.org/livecams/documentary-films/rescue-foundation', 'latlong': ['21.7866', '82.794762']},
    267: {'title': 'Two Sides of the Fence', 'slug': 'two-sides-of-the-fence', 'youtube_id': '3o8LW4EJ6Ew', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Juarez, Mexio', 'partner': 'Explore.org', 'tags': 'Documentary films, mexio', 'canonical_url': 'https://explore.org/livecams/documentary-films/two-sides-of-the-fence', 'latlong': ['23.63450', '-102.55278']},
    268: {'title': "Rita Marley's Town", 'slug': 'rita-marley', 'youtube_id': 'L8MqhCfT6KM', 'channel': 'Curators', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Ghana', 'partner': 'Explore.org', 'tags': 'Documentary films, ghana, rita marley', 'canonical_url': 'https://explore.org/livecams/documentary-films/rita-marley', 'latlong': ['7.95501', '-1.03182']},
    # --- Dog Bless You ---
    9: {'title': 'Puppy Playroom at Warrior Canine Connection', 'slug': 'service-puppy-cam', 'youtube_id': 'h-Z0wCdD3dI', 'channel': 'Dog Bless You', 'cam_group': 'Warrior Canine Connection', 'cam_group_slug': 'warrior-canine-connection', 'live': False, 'location': 'Boyds, Maryland, USA', 'partner': 'Warrior Canine Connection', 'tags': 'puppy cam, service dog puppies, golden retriever, labrador, puppy, puppies, veterans, service animal', 'canonical_url': 'https://explore.org/livecams/warrior-canine-connection/service-puppy-cam', 'latlong': ['39.146251', '-77.312351']},
    29: {'title': 'Great Danes Puppy Hill', 'slug': 'great-danes-service-puppies-puppy-hill', 'youtube_id': 'L26Os34ssTI', 'channel': 'Dog Bless You', 'cam_group': 'Service Dog Project', 'cam_group_slug': 'service-dog-project', 'live': False, 'location': 'Ipswich, Massachusetts, USA', 'partner': 'Service Dog Project', 'tags': 'dog, puppy, puppies, massachusetts, live, service, dane', 'canonical_url': 'https://explore.org/livecams/service-dog-project/great-danes-service-puppies-puppy-hill', 'latlong': ['42.673592', '-70.956619']},
    30: {'title': 'Great Danes Outdoor Kennel', 'slug': 'great-danes-outdoor-kennels-camera', 'youtube_id': 'VWRo2653Zdk', 'channel': 'Dog Bless You', 'cam_group': 'Service Dog Project', 'cam_group_slug': 'service-dog-project', 'live': False, 'location': 'Ipswich, Massachusetts, USA', 'partner': 'Service Dog Project', 'tags': 'dog, puppy, puppies, massachusetts, live, dane, service', 'canonical_url': 'https://explore.org/livecams/service-dog-project/great-danes-outdoor-kennels-camera', 'latlong': ['42.674006', '-70.956278']},
    41: {'title': 'Great Dane Indoor Puppy Room', 'slug': 'great-danes-indoor-room-puppy-cam-2', 'youtube_id': 'ioG4QDsW6dc', 'channel': 'Dog Bless You', 'cam_group': 'Service Dog Project', 'cam_group_slug': 'service-dog-project', 'live': False, 'location': 'Ipswich, Massachusetts, USA', 'partner': 'Service Dog Project', 'tags': 'dog, puppy, puppies, massachusetts, live, service, dane', 'canonical_url': 'https://explore.org/livecams/service-dog-project/great-danes-indoor-room-puppy-cam-2', 'latlong': ['42.673592', '-70.956619']},
    45: {'title': 'ECAD Puppies', 'slug': 'east-coast-assistance-dogs-cam-2', 'youtube_id': 'TrWRIynJoKk', 'channel': 'Dog Bless You', 'cam_group': 'ECAD', 'cam_group_slug': 'ecad', 'live': False, 'location': 'Winchester, CT, USA', 'partner': 'Educated Canines Assisting with Disabilities', 'tags': 'labrador, dog, puppies, ecad, live, service, retriever, connecticut', 'canonical_url': 'https://explore.org/livecams/ecad/east-coast-assistance-dogs-cam-2', 'latlong': ['41.883120', '-73.135460']},
    63: {'title': 'Great Dane Training Arena', 'slug': 'great-danes-arena-cam', 'youtube_id': 'QD1vTEw-I-I', 'channel': 'Dog Bless You', 'cam_group': 'Service Dog Project', 'cam_group_slug': 'service-dog-project', 'live': False, 'location': 'Ipswich, Massachusetts, USA', 'partner': 'Service Dog Project', 'tags': 'dog, puppy, puppies, service dog, massachusetts, dane, live', 'canonical_url': 'https://explore.org/livecams/service-dog-project/great-danes-arena-cam', 'latlong': ['42.673389', '-70.956858']},
    87: {'title': 'ECAD Whelping', 'slug': 'east-coast-assistance-dogs-cam', 'youtube_id': 'TrWRIynJoKk', 'channel': 'Dog Bless You', 'cam_group': 'ECAD', 'cam_group_slug': 'ecad', 'live': False, 'location': 'Winchester, Connecticut, USA', 'partner': 'Educated Canines Assisting with Disabilities', 'tags': 'dog, puppies, ecad, service dogs, retriever, connecticut, puppy, live', 'canonical_url': 'https://explore.org/livecams/ecad/east-coast-assistance-dogs-cam', 'latlong': ['41.800305', '-73.121172']},
    91: {'title': 'Great Dane Puppy Nursery', 'slug': 'great-danes-puppy-nursery-cam', 'youtube_id': 'lWzqCaiabkI', 'channel': 'Dog Bless You', 'cam_group': 'Service Dog Project', 'cam_group_slug': 'service-dog-project', 'live': False, 'location': 'Ipswich, Massachusetts, USA', 'partner': 'Service Dog Project', 'tags': 'dog, puppy, puppies, service dog, massachusetts, nursery, dane, live', 'canonical_url': 'https://explore.org/livecams/service-dog-project/great-danes-puppy-nursery-cam', 'latlong': ['42.673561', '-70.955358']},
    95: {'title': 'Nursery at Warrior Canine Connection', 'slug': 'service-puppy-cam-3', 'youtube_id': 'eC__seErcqo', 'channel': 'Dog Bless You', 'cam_group': 'Warrior Canine Connection', 'cam_group_slug': 'warrior-canine-connection', 'live': True, 'location': 'Boyds, Maryland, USA', 'partner': 'Warrior Canine Connection', 'tags': 'labrador, puppy, puppies, wcc, maryland, retriever, service dog, dog, live, nursery', 'canonical_url': 'https://explore.org/livecams/warrior-canine-connection/service-puppy-cam-3', 'latlong': ['39.146251', '-77.312351']},
    215: {'title': 'Puppy Whelping Room at Warrior Canine Connection', 'slug': 'puppy-whelping-room', 'youtube_id': 'dlP_vzAxX_8', 'channel': 'Dog Bless You', 'cam_group': 'Warrior Canine Connection', 'cam_group_slug': 'warrior-canine-connection', 'live': True, 'location': 'Germantown, MD', 'partner': 'Warrior Canine Connection', 'tags': 'warrior canine connection, puppy, puppies, veterans, wcc, maryland, dogs, service dog, live', 'canonical_url': 'https://explore.org/livecams/warrior-canine-connection/puppy-whelping-room', 'latlong': ['39.146251', '-77.312351']},
    216: {'title': 'Outdoor Puppy Pen at Warrior Canine Connection', 'slug': 'outdoor-puppy-pen', 'youtube_id': 'cWzkAHB1kT8', 'channel': 'Dog Bless You', 'cam_group': 'Warrior Canine Connection', 'cam_group_slug': 'warrior-canine-connection', 'live': True, 'location': 'Germantown, MD', 'partner': 'Warrior Canine Connection', 'tags': 'puppy, puppies, veterans, wcc, warrior canine connection, maryland, service dog, live, dogs', 'canonical_url': 'https://explore.org/livecams/warrior-canine-connection/outdoor-puppy-pen', 'latlong': ['39.146251', '-77.312351']},
    236: {'title': 'ECAD Class is in Session', 'slug': 'ecad-training-and-play', 'youtube_id': 'V5RfI6dXZgY', 'channel': 'Dog Bless You', 'cam_group': 'ECAD', 'cam_group_slug': 'ecad', 'live': False, 'location': 'Bethel, Connecticut, USA', 'partner': 'Educated Canines Assisting with Disabilities', 'tags': 'ecad, dogs, live, dog bless you, service', 'canonical_url': 'https://explore.org/livecams/ecad/ecad-training-and-play', 'latlong': ['41.80065', '-73.12122']},
    241: {'title': 'Guide Dogs of America Nursery Cam', 'slug': 'guide-dogs-of-america-nursery', 'youtube_id': 'QdEVb1rheRE', 'channel': 'Dog Bless You', 'cam_group': 'Dog Bless You', 'cam_group_slug': 'dog-bless-you', 'live': True, 'location': 'Sylmar, California, USA', 'partner': 'Guide Dogs Of America', 'tags': 'dog, service dog, puppies, live', 'canonical_url': 'https://explore.org/livecams/dog-bless-you/guide-dogs-of-america-nursery', 'latlong': ['34.322805', '-118.46935']},
    269: {'title': 'Guide Dogs Mobility Cam', 'slug': 'guide-dogs-mobility-cam', 'youtube_id': 'QF2ojZmSTWs', 'channel': 'Dog Bless You', 'cam_group': 'Guide Dogs of America', 'cam_group_slug': 'guide-dogs-of-america', 'live': True, 'location': 'Sylmar, California', 'partner': 'Guide Dogs Of America', 'tags': 'guide dogs of america, dogs, assistance dog, service dog', 'canonical_url': 'https://explore.org/livecams/guide-dogs-of-america/guide-dogs-mobility-cam', 'latlong': ['34.322805', '-118.46935']},
    302: {'title': 'Full House Puppy Cam at Warrior Canine Connection', 'slug': 'service-puppy-cam-full-house', 'youtube_id': 'Qeq2Kax0v64', 'channel': 'Dog Bless You', 'cam_group': 'Warrior Canine Connection', 'cam_group_slug': 'warrior-canine-connection', 'live': False, 'location': 'Boyds, Maryland, USA', 'partner': 'Warrior Canine Connection', 'tags': 'service dog, dog, warrior canine connection', 'canonical_url': 'https://explore.org/livecams/warrior-canine-connection/service-puppy-cam-full-house', 'latlong': ['39.146251', '-77.312351']},
    360: {'title': 'NEC Puppy Room', 'slug': 'nec-puppy-room', 'youtube_id': '1ju36sNu7jg', 'channel': 'Dog Bless You', 'cam_group': 'Dog Bless You', 'cam_group_slug': 'dog-bless-you', 'live': False, 'location': 'South Hampton, NH', 'partner': 'Northeast Canine', 'tags': 'puppies, dane, great dane, NEC Puppy Room, Puppy room', 'canonical_url': 'https://explore.org/livecams/dog-bless-you/nec-puppy-room', 'latlong': ['42.880657', '-70.963491']},
    # --- Farm Sanctuary ---
    135: {'title': 'Sheep Barn', 'slug': 'sheep-barn-farm-sanctuary', 'youtube_id': 'SnHke968zAA', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': False, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'rescue, farm, sheep, lamb, live', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/sheep-barn-farm-sanctuary', 'latlong': ['42.384139', '-77.033392']},
    136: {'title': 'Wisconsin Pasture', 'slug': 'wisconsin-pasture-farm-sanctuary', 'youtube_id': 'dqcCOYtHtes', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': True, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'rescue, cows, goats, alpacas, farm, live', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/wisconsin-pasture-farm-sanctuary', 'latlong': ['42.382669', '-77.031789']},
    181: {'title': 'Cattle Pond Pasture', 'slug': 'cattle-pond-pasture-farm-sanctuary', 'youtube_id': 'inDzgZjCxmQ', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': True, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'cattle, cows, farm, pasture, rescue, watkins glen, live', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/cattle-pond-pasture-farm-sanctuary', 'latlong': ['42.379847', '-77.036431']},
    182: {'title': 'Cattle Pasture Panorama', 'slug': 'cattle-pasture-panorama-farm-sanctuary', 'youtube_id': 'dKFwk3MDu74', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': False, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'cattle, cows, farm, hills, watkins glen, live', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/cattle-pasture-panorama-farm-sanctuary', 'latlong': ['42.381944', '-77.032789']},
    183: {'title': 'Charlotte’s Pasture', 'slug': 'pig-pasture-farm-sanctuary', 'youtube_id': 'ub6TVvmQnhA', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': True, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'pig, rescue, farm, piglets, watkins glen, live, pigs', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/pig-pasture-farm-sanctuary', 'latlong': ['42.384069', '-77.033581']},
    184: {'title': 'Sheep Pasture', 'slug': 'sheep-pasture-farm-sanctuary', 'youtube_id': 'K8TbCP3yeS4', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': True, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'farm, rescue, sheep, lambs, watkins glen, live', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/sheep-pasture-farm-sanctuary', 'latlong': ['42.384744', '-77.033169']},
    185: {'title': 'Chicken Barn', 'slug': 'turkey-barn-farm-sanctuary', 'youtube_id': '3bf1JDW_50k', 'channel': 'Farm Sanctuary', 'cam_group': 'Farm Sanctuary', 'cam_group_slug': 'farm-sanctuary', 'live': False, 'location': 'Watkins Glen, New York, USA', 'partner': 'Farm Sanctuary', 'tags': 'turkeys, chickens, farm, barn, birds, watkins glen, live', 'canonical_url': 'https://explore.org/livecams/farm-sanctuary/turkey-barn-farm-sanctuary', 'latlong': ['42.384744', '-77.033169']},
    # --- Grasslands ---
    64: {'title': 'African Animals', 'slug': 'african-animal-lookout-camera', 'youtube_id': '5BvAb1ux-Sg', 'channel': 'Grasslands', 'cam_group': 'African Wildlife', 'cam_group_slug': 'african-wildlife', 'live': True, 'location': 'Laikipia County, Kenya', 'partner': 'Mpala Research Centre', 'tags': 'africa, mpala, kenya, elephant, hippo, monkey, live, hippopotamus', 'canonical_url': 'https://explore.org/livecams/african-wildlife/african-animal-lookout-camera', 'latlong': ['0.317712', '36.910165']},
    65: {'title': 'African Animals - Watering Hole', 'slug': 'african-watering-hole-animal-camera', 'youtube_id': 'oORXfTviuCs', 'channel': 'Grasslands', 'cam_group': 'African Wildlife', 'cam_group_slug': 'african-wildlife', 'live': False, 'location': 'Laikipia County, Kenya', 'partner': 'Mpala Research Centre', 'tags': 'hippo, elephant, kenya, giraffe, africa, mpala, hippopotamus, live, zebra, monkey', 'canonical_url': 'https://explore.org/livecams/african-wildlife/african-watering-hole-animal-camera', 'latlong': ['0.317712', '36.910165']},
    66: {'title': 'African River Wildlife', 'slug': 'african-river-wildlife-camera', 'youtube_id': '7x5kRo1B84Y', 'channel': 'Grasslands', 'cam_group': 'African Wildlife', 'cam_group_slug': 'african-wildlife', 'live': True, 'location': 'Laikipia County, Kenya', 'partner': 'Mpala Research Centre', 'tags': 'hippo, elephant, kenya, giraffe, africa, mpala, live, river, zebra, hippopotamus', 'canonical_url': 'https://explore.org/livecams/african-wildlife/african-river-wildlife-camera', 'latlong': ['0.316818', '36.908041']},
    67: {'title': 'African Safari', 'slug': 'african-safari-camera', 'youtube_id': 'LC-DK_22eK4', 'channel': 'Grasslands', 'cam_group': 'African Wildlife', 'cam_group_slug': 'african-wildlife', 'live': True, 'location': 'Laikipia County, Kenya', 'partner': 'Mpala Research Centre', 'tags': 'african wildlife, hippo, elephant, kenya, giraffe, kudus, africa, mpala', 'canonical_url': 'https://explore.org/livecams/african-wildlife/african-safari-camera', 'latlong': ['0.317712', '36.910165']},
    # --- Nature Films ---
    12: {'title': 'Aurora Borealis - Northern Lights', 'slug': 'northern-lights-cam', 'youtube_id': 'a0i1Kg6fROg', 'channel': 'Nature Films', 'cam_group': 'Zen Den', 'cam_group_slug': 'zen-den', 'live': True, 'location': 'Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'northern lights live camera, arctic, tundra, north, aurora borealis, sky, light, zen den, churchill', 'canonical_url': 'https://explore.org/livecams/zen-den/northern-lights-cam', 'latlong': ['58.737872', '-93.819389']},
    17: {'title': 'Redwood Forest River', 'slug': 'live-redwood-cam-1', 'youtube_id': 'pLNz_Vp4Ryo', 'channel': 'Nature Films', 'cam_group': 'Zen Den', 'cam_group_slug': 'zen-den', 'live': True, 'location': 'Crescent City, California, USA', 'partner': 'Save the Redwoods League & Smith River Alliance', 'tags': 'redwood forest cam, live redwood forest camera, redwood, forest, tree, woods, smith river, jedediah ', 'canonical_url': 'https://explore.org/livecams/zen-den/live-redwood-cam-1', 'latlong': ['41.790856', '-124.072850']},
    51: {'title': 'Dumpling Mountain - Katmai National Park', 'slug': 'dumpling-mountain-brown-bear-salmon-cams', 'youtube_id': 'PGgSt7yS3JA', 'channel': 'Nature Films', 'cam_group': 'Zen Den', 'cam_group_slug': 'zen-den', 'live': False, 'location': 'Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'dumpling mountain, alaska, river, live, katmai', 'canonical_url': 'https://explore.org/livecams/zen-den/dumpling-mountain-brown-bear-salmon-cams', 'latlong': ['58.571939', '-155.861435']},
    56: {'title': 'Naknek River', 'slug': 'alaska-naknek-river', 'youtube_id': 'qR2YMtQzYNk', 'channel': 'Nature Films', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'King Salmon, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'swans, geese, ducks, sunrise, sunset, alaska, naknek, river, birds, katmai, live, belugas', 'canonical_url': 'https://explore.org/livecams/brown-bears/alaska-naknek-river', 'latlong': ['58.679049', '-156.669739']},
    # --- Oceans ---
    2: {'title': 'Tropical Fish - Coral Predators', 'slug': 'pacific-aquarium-tropical-reef-habitat-cam', 'youtube_id': 'h0F818upkgI', 'channel': 'Oceans', 'cam_group': 'Aquarium of the Pacific', 'cam_group_slug': 'aquarium-of-the-pacific', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'fish, coral, underwater, tropical, aquarium, live', 'canonical_url': 'https://explore.org/livecams/aquarium-of-the-pacific/pacific-aquarium-tropical-reef-habitat-cam', 'latlong': ['33.762149', '-118.196981']},
    3: {'title': 'Blue Cavern Aquarium', 'slug': 'aquarium-pacific-live-cam-2', 'youtube_id': 'H59B9Uoewwg', 'channel': 'Oceans', 'cam_group': 'Aquarium of the Pacific', 'cam_group_slug': 'aquarium-of-the-pacific', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'aquarium of the pacific, ocean, blue cavern, fish, underwater, animals, marine, wildlife', 'canonical_url': 'https://explore.org/livecams/aquarium-of-the-pacific/aquarium-pacific-live-cam-2', 'latlong': ['33.762149', '-118.196981']},
    4: {'title': 'Santa Monica Beach and Pier', 'slug': 'santa-monica-beach-cam', 'youtube_id': 'qmE7U1YZPQA', 'channel': 'Oceans', 'cam_group': 'Santa Monica Beach', 'cam_group_slug': 'santa-monica-beach', 'live': True, 'location': 'Santa Monica, California, USA', 'partner': 'Hotel Shangri-La', 'tags': 'santa monica beach cam, sunset, beach, landscape, palm trees, waves, ocean, zen den', 'canonical_url': 'https://explore.org/livecams/santa-monica-beach/santa-monica-beach-cam', 'latlong': ['34.015342', '-118.499083']},
    7: {'title': 'West Coast Sea Nettles - Jellyfish Tank', 'slug': 'seajelly-cam', 'youtube_id': 'IYG9fnz40-E', 'channel': 'Oceans', 'cam_group': 'Aquarium of the Pacific', 'cam_group_slug': 'aquarium-of-the-pacific', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'live jellyfish cam, west coast sea nettles, jelly cam, sea jelly, japanese sea nettles, aquarium of ', 'canonical_url': 'https://explore.org/livecams/aquarium-of-the-pacific/seajelly-cam', 'latlong': ['33.762149', '-118.196981']},
    8: {'title': 'Tropical Reef Aquarium', 'slug': 'pacific-aquarium-tropical-reef-camera', 'youtube_id': 'DHUnz4dyb54', 'channel': 'Oceans', 'cam_group': 'Aquarium of the Pacific', 'cam_group_slug': 'aquarium-of-the-pacific', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'live ocean cam, live underwater camera, live fish cam, live aquarium cam, tropical reef, underwater,', 'canonical_url': 'https://explore.org/livecams/aquarium-of-the-pacific/pacific-aquarium-tropical-reef-camera', 'latlong': ['33.762149', '-118.196981']},
    35: {'title': 'Pipeline Surfing', 'slug': 'hawaii-pipeline-cam', 'youtube_id': 'VI8Wj5EwoRM', 'channel': 'Oceans', 'cam_group': 'Hawaii', 'cam_group_slug': 'hawaii', 'live': False, 'location': 'Ehukai Beach - Oahu, Hawaii, USA', 'partner': 'North Shore Lifeguard Association', 'tags': 'pipeline, oahu, waves, ocean, hawaii, sunsets, live, surfers, zen, north shore', 'canonical_url': 'https://explore.org/livecams/hawaii/hawaii-pipeline-cam', 'latlong': ['21.662701', '-158.053295']},
    36: {'title': 'Waimea Bay & Beach', 'slug': 'hawaii-waimea-bay-cam', 'youtube_id': '6ykvQrPUxwc', 'channel': 'Oceans', 'cam_group': 'Hawaii', 'cam_group_slug': 'hawaii', 'live': False, 'location': 'Waimea Bay - Oahu, Hawaii, USA', 'partner': 'North Shore Lifeguard Association', 'tags': 'waves, surf, ocean, hawaii, sunsets, beach, oahu, waimea, live, zen', 'canonical_url': 'https://explore.org/livecams/hawaii/hawaii-waimea-bay-cam', 'latlong': ['21.639915', '-158.063142']},
    42: {'title': 'Gray Seal Pupping', 'slug': 'seal-pups-cam', 'youtube_id': 'bol0H1QWILg', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': 'maine, pups, ocean, seals, live, audubon, seal', 'canonical_url': 'https://explore.org/livecams/oceans/seal-pups-cam', 'latlong': ['43.891663', '-68.733370']},
    59: {'title': 'Shark Lagoon', 'slug': 'shark-lagoon-cam', 'youtube_id': 'YT7lH6U68S4', 'channel': 'Oceans', 'cam_group': 'Aquarium of the Pacific', 'cam_group_slug': 'aquarium-of-the-pacific', 'live': True, 'location': 'Long Beach, California, USA', 'partner': 'Aquarium of the Pacific', 'tags': 'shark, fish, live, aquarium', 'canonical_url': 'https://explore.org/livecams/aquarium-of-the-pacific/shark-lagoon-cam', 'latlong': ['33.762149', '-118.196981']},
    68: {'title': 'Cayman Reef Cam', 'slug': 'cayman-reef-cam', 'youtube_id': 'dsOlEtCYSWw', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': False, 'location': 'East End, Grand Cayman', 'partner': 'Teens4Oceans', 'tags': 'oceans, reef, fish, coral, shark, ray, teens4oceans, cayman, live', 'canonical_url': 'https://explore.org/livecams/oceans/cayman-reef-cam', 'latlong': ['19.298750', '-81.089667']},
    76: {'title': 'Beluga Boat - Underwater', 'slug': 'beluga-boat-cam-underwater', 'youtube_id': 'MthQzTUrMLs', 'channel': 'Oceans', 'cam_group': 'Beluga Whales', 'cam_group_slug': 'beluga-whales', 'live': False, 'location': 'Hudson Bay, Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'belugas, whales, hudson, pbi, underwater, churchill, live, canada', 'canonical_url': 'https://explore.org/livecams/beluga-whales/beluga-boat-cam-underwater', 'latlong': ['58.773133', '-94.210653']},
    77: {'title': 'Beluga Boat - Above Deck', 'slug': 'beluga-boat-cam-on-deck', 'youtube_id': 'XVBA9HDxuPY', 'channel': 'Oceans', 'cam_group': 'Beluga Whales', 'cam_group_slug': 'beluga-whales', 'live': False, 'location': 'Hudson Bay, Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'belugas, whales, churchill, canada, hudson, river, pbi, live', 'canonical_url': 'https://explore.org/livecams/beluga-whales/beluga-boat-cam-on-deck', 'latlong': ['58.773133', '-94.210653']},
    83: {'title': 'Sharks in the Atlantic', 'slug': 'shark-cam', 'youtube_id': 'og8bbxl0iW8', 'channel': 'Oceans', 'cam_group': 'Meditation', 'cam_group_slug': 'meditation', 'live': False, 'location': 'Cape Fear, North Carolina, USA', 'partner': 'Frying Pan Tower', 'tags': 'teens4oceans, underwater, reef, fish, shark, ocean, cape fear, carolina, live', 'canonical_url': 'https://explore.org/livecams/meditation/shark-cam', 'latlong': ['33.483333', '-77.583333']},
    94: {'title': 'Pacific Walrus Beach', 'slug': 'walrus-cam-round-island', 'youtube_id': 'VK7pmCnqhcM', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': False, 'location': 'Round Island, Alaska, USA', 'partner': 'Alaska Department of Fish & Game', 'tags': 'walrus, walruses, alaska, live', 'canonical_url': 'https://explore.org/livecams/oceans/walrus-cam-round-island', 'latlong': ['58.607704', '-159.964217']},
    96: {'title': 'OrcaLab Main Cams', 'slug': 'orcalab-base', 'youtube_id': 'hTOmWcmr2Tc', 'channel': 'Oceans', 'cam_group': 'Orcas', 'cam_group_slug': 'orcas', 'live': True, 'location': 'Hanson Island, British Columbia, Canada', 'partner': 'OrcaLab', 'tags': 'orcalab, orca, whales, canada, live', 'canonical_url': 'https://explore.org/livecams/orcas/orcalab-base', 'latlong': ['50.574249', '-126.706594']},
    98: {'title': 'Strider Rubbing Beach Underwater Orcas', 'slug': 'orcalab-rubbing-beach-underwater', 'youtube_id': 'qrssOMU9cUc', 'channel': 'Oceans', 'cam_group': 'Orcas', 'cam_group_slug': 'orcas', 'live': False, 'location': 'Hanson Island, British Columbia, Canada', 'partner': 'OrcaLab', 'tags': 'orca, orcalab, canada, whales, underwater, live', 'canonical_url': 'https://explore.org/livecams/orcas/orcalab-rubbing-beach-underwater', 'latlong': ['50.485882', '-126.519839']},
    99: {'title': 'Strider Rubbing Beach Surface Cam', 'slug': 'orcalab-rubbing-beach', 'youtube_id': 'NWWFs_mdvic', 'channel': 'Oceans', 'cam_group': 'Orcas', 'cam_group_slug': 'orcas', 'live': False, 'location': 'Hanson Island, British Columbia, Canada', 'partner': 'OrcaLab', 'tags': 'orca, orca whales, orcalab, canada, live', 'canonical_url': 'https://explore.org/livecams/orcas/orcalab-rubbing-beach', 'latlong': ['50.485882', '-126.519839']},
    107: {'title': 'Channel Islands Kelp Forest', 'slug': 'channel-islands-national-park-anacapa-ocean', 'youtube_id': 'OAJF1Ie1m_Q', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': True, 'location': 'Anacapa Island - Channel Islands, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'underwater, ocean, california, kelp, fish, channel islands, live', 'canonical_url': 'https://explore.org/livecams/oceans/channel-islands-national-park-anacapa-ocean', 'latlong': ['34.016457', '-119.362151']},
    115: {'title': 'Channel Islands Live - Nature Talks', 'slug': 'channel-islands-national-park-live-adventures', 'youtube_id': 'TU_IyFk6O28', 'channel': 'Oceans', 'cam_group': 'Channel Islands National Park', 'cam_group_slug': 'channel-islands-national-park', 'live': False, 'location': 'Anacapa Island - Channel Islands, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'underwater, ocean, california, kelp, education, chat, live, fish, channel islands', 'canonical_url': 'https://explore.org/livecams/channel-islands-national-park/channel-islands-national-park-live-adventures', 'latlong': ['34.016457', '-119.362151']},
    121: {'title': 'Pacific Ocean Meditation', 'slug': 'pacific-ocean', 'youtube_id': 'oebE0cb86n8', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': False, 'location': 'Alaska to Hawaii', 'partner': 'Explore.org', 'tags': 'ocean, zen, meditation', 'canonical_url': 'https://explore.org/livecams/oceans/pacific-ocean', 'latlong': ['37.681457', '-164.390322']},
    123: {'title': 'Anacapa Island Cove - Channel Islands National Park', 'slug': 'channel-islands-national-park-anacapa-island-cove', 'youtube_id': 'aaUERtNMn7o', 'channel': 'Oceans', 'cam_group': 'Channel Islands National Park', 'cam_group_slug': 'channel-islands-national-park', 'live': True, 'location': 'Anacapa Island - Channel Islands, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'sunrise, sunset, ocean, california, channel islands, anacapa, live', 'canonical_url': 'https://explore.org/livecams/channel-islands-national-park/channel-islands-national-park-anacapa-island-cove', 'latlong': ['34.016568', '-119.362343']},
    128: {'title': 'Sea Lion Beach at OrcaLab', 'slug': 'orcalab-steller-sea-lion-haulout', 'youtube_id': '-uooI2satIQ', 'channel': 'Oceans', 'cam_group': 'Orcas', 'cam_group_slug': 'orcas', 'live': False, 'location': 'Hanson Island, British Columbia, Canada', 'partner': 'OrcaLab', 'tags': 'orcalab, canada, sea lion, sealion, live', 'canonical_url': 'https://explore.org/livecams/orcas/orcalab-steller-sea-lion-haulout', 'latlong': ['50.568415', '-126.698024']},
    139: {'title': 'Mount Diablo on Santa Cruz', 'slug': 'mount-diablo-santa-cruz', 'youtube_id': 'f5Rjm5tiEkU', 'channel': 'Oceans', 'cam_group': 'Channel Islands National Park', 'cam_group_slug': 'channel-islands-national-park', 'live': True, 'location': 'Santa Cruz Island, California, USA', 'partner': 'Channel Islands National Park', 'tags': 'mount diablo, sunset, zen, ocean, california', 'canonical_url': 'https://explore.org/livecams/channel-islands-national-park/mount-diablo-santa-cruz', 'latlong': ['34.029159', '-119.784483']},
    193: {'title': 'Waikiki Beach Meditation', 'slug': 'waikiki-beach-meditation', 'youtube_id': '-gjQP7ABEK0', 'channel': 'Oceans', 'cam_group': 'Hawaii', 'cam_group_slug': 'hawaii', 'live': False, 'location': 'Waikiki - Oahu, Hawaii, USA', 'partner': 'North Shore Lifeguard Association', 'tags': 'hawaii, north shore, waikiki, oahu, beach, meditation, waves, ocean, live', 'canonical_url': 'https://explore.org/livecams/hawaii/waikiki-beach-meditation', 'latlong': ['21.276081', '-157.827217']},
    225: {'title': 'Walrus First Beach', 'slug': 'walrus-first-beach', 'youtube_id': 'gcr56pq8Sl0', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': False, 'location': 'Round Island, Alaska, USA', 'partner': 'Alaska Department of Fish & Game', 'tags': 'alaska, walrus, live, seabird', 'canonical_url': 'https://explore.org/livecams/oceans/walrus-first-beach', 'latlong': ['58.607704', '-159.964217']},
    252: {'title': 'Lifeguard Legends: Guardians of the Sea', 'slug': 'lifeguard-legends', 'youtube_id': 'ZfsqgK-qXSk', 'channel': 'Oceans', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Oahu, Hawaii', 'partner': 'Explore.org', 'tags': 'hawaii, lifeguard legends', 'canonical_url': 'https://explore.org/livecams/documentary-films/lifeguard-legends', 'latlong': ['34.015342', '-118.499083']},
    271: {'title': 'USC Wrigley Catalina Marine Reserve', 'slug': 'catalina-marine-reserve', 'youtube_id': 'JH_NzhSsqis', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': True, 'location': 'Big Fisherman Cove, Catalina Island, California', 'partner': 'USC Wrigley Institute for Environmental Studies', 'tags': 'catalina island, underwater', 'canonical_url': 'https://explore.org/livecams/oceans/catalina-marine-reserve', 'latlong': ['33.445000', '-118.484444']},
    272: {'title': 'Above Water Manatee-Cam at Blue Spring State Park', 'slug': 'manatee-cam-above-water', 'youtube_id': 'FbbHB9ka8Yg', 'channel': 'Oceans', 'cam_group': 'Save The Manatee', 'cam_group_slug': 'save-the-manatee', 'live': True, 'location': 'Blue Spring State Park, Orange City, FL 32763', 'partner': 'Save The Manatee Club', 'tags': 'manatee, underwater', 'canonical_url': 'https://explore.org/livecams/save-the-manatee/manatee-cam-above-water', 'latlong': ['28.943444', '-81.340944']},
    273: {'title': 'Underwater Manatee-Cam at Blue Spring State Park', 'slug': 'manatee-cam-under-water', 'youtube_id': 'h2GA3zrYeA0', 'channel': 'Oceans', 'cam_group': 'Save The Manatee', 'cam_group_slug': 'save-the-manatee', 'live': True, 'location': 'Blue Spring State Park, Orange City, FL', 'partner': 'Save The Manatee Club', 'tags': 'manatee, underwater', 'canonical_url': 'https://explore.org/livecams/save-the-manatee/manatee-cam-under-water', 'latlong': ['28.944778', '-81.339306']},
    281: {'title': 'Wild Dolphins', 'slug': 'wild-dolphins', 'youtube_id': 'sol1ehxhUIU', 'channel': 'Oceans', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'The Bahamas', 'partner': 'Explore.org', 'tags': 'dolphin', 'canonical_url': 'https://explore.org/livecams/documentary-films/wild-dolphins', 'latlong': ['24.741421', '-78.080017']},
    282: {'title': 'Orcas', 'slug': 'orcas', 'youtube_id': 'llRmQIgYhKw', 'channel': 'Oceans', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Friday Harbor, Washington', 'partner': 'Explore.org', 'tags': '', 'canonical_url': 'https://explore.org/livecams/documentary-films/orcas', 'latlong': ['47.273071', '-120.8246']},
    285: {'title': 'Homosassa Springs Above Water Manatees', 'slug': 'homosassa-manatee-above-water', 'youtube_id': 'nbF12irhVys', 'channel': 'Oceans', 'cam_group': 'Save The Manatee', 'cam_group_slug': 'save-the-manatee', 'live': True, 'location': 'ELLIE SCHILLER HOMOSASSA SPRINGS WILDLIFE STATE PARK, FL', 'partner': 'Save The Manatee Club', 'tags': 'manatee, homosassa', 'canonical_url': 'https://explore.org/livecams/save-the-manatee/homosassa-manatee-above-water', 'latlong': ['28.800739', '-82.578117']},
    286: {'title': 'Homosassa Springs Underwater Manatees', 'slug': 'homosassa-springs-underwater-manatees', 'youtube_id': 'Fz6sl9YJZE0', 'channel': 'Oceans', 'cam_group': 'Save The Manatee', 'cam_group_slug': 'save-the-manatee', 'live': True, 'location': 'ELLIE SCHILLER HOMOSASSA SPRINGS WILDLIFE STATE PARK, FL', 'partner': 'Save The Manatee Club', 'tags': 'manatee, underwater', 'canonical_url': 'https://explore.org/livecams/save-the-manatee/homosassa-springs-underwater-manatees', 'latlong': ['28.800739', '-82.578117']},
    306: {'title': 'Top-of-Wall Underwater Reef Cam', 'slug': 'utopia-village-underwater-coral', 'youtube_id': '1zcIUk66HX4', 'channel': 'Oceans', 'cam_group': 'Oceans', 'cam_group_slug': 'oceans', 'live': True, 'location': 'Utopia Village on Utila, The Bay Islands, Honduras', 'partner': 'Utopia Village', 'tags': 'Utopia Village, under water, reef', 'canonical_url': 'https://explore.org/livecams/oceans/utopia-village-underwater-coral', 'latlong': ['16.071753', '-86.951344']},
    307: {'title': 'Edge-of-Wall Underwater Reef Cam', 'slug': 'utopia-village-reef-camera', 'youtube_id': 'Sq-X4Ga1oyc', 'channel': 'Oceans', 'cam_group': 'Utopia Village', 'cam_group_slug': 'utopia-village', 'live': True, 'location': 'Utopia Village on Utila, The Bay Islands, Honduras', 'partner': 'Utopia Village', 'tags': '', 'canonical_url': 'https://explore.org/livecams/utopia-village/utopia-village-reef-camera', 'latlong': ['16.071753', '-86.951344']},
    310: {'title': 'Front-of-Dock Underwater Reef Cams', 'slug': 'utopia-village-dock-camera', 'youtube_id': 'Kf-x20Yq0_A', 'channel': 'Oceans', 'cam_group': 'Utopia Village', 'cam_group_slug': 'utopia-village', 'live': True, 'location': 'Utopia Village on Utila, The Bay Islands, Honduras', 'partner': 'Utopia Village', 'tags': 'Utopia Village, under water, dock, reef', 'canonical_url': 'https://explore.org/livecams/utopia-village/utopia-village-dock-camera', 'latlong': ['16.071753', '-86.951344']},
    316: {'title': 'Gray Seal Spine Tower Camera', 'slug': 'gray-seal-tower-cam', 'youtube_id': 'bol0H1QWILg', 'channel': 'Oceans', 'cam_group': 'Gray Seals', 'cam_group_slug': 'gray-seals', 'live': False, 'location': 'Seal Island, Maine, USA', 'partner': 'National Audubon Society', 'tags': '', 'canonical_url': 'https://explore.org/livecams/gray-seals/gray-seal-tower-cam', 'latlong': ['43.891663', '-68.733370']},
    318: {'title': 'Back-of-Dock Underwater Reef Cams', 'slug': 'utopia-village-dock-camera-alt', 'youtube_id': 'Lv9t0hZTvz4', 'channel': 'Oceans', 'cam_group': 'Utopia Village', 'cam_group_slug': 'utopia-village', 'live': True, 'location': 'Utopia Village on Utila, The Bay Islands, Honduras', 'partner': 'Utopia Village', 'tags': 'Utopia Village, under water, dock, reef', 'canonical_url': 'https://explore.org/livecams/utopia-village/utopia-village-dock-camera-alt', 'latlong': ['16.071753', '-86.951344']},
    323: {'title': 'Sandy Channel Underwater Reef Cam', 'slug': 'utopia-village-reef-channel', 'youtube_id': 'jzx_n25g3kA', 'channel': 'Oceans', 'cam_group': 'Utopia Village', 'cam_group_slug': 'utopia-village', 'live': True, 'location': 'Utopia Village on Utila, The Bay Islands, Honduras', 'partner': 'Utopia Village', 'tags': '', 'canonical_url': 'https://explore.org/livecams/utopia-village/utopia-village-reef-channel', 'latlong': ['16.071753', '-86.951344']},
    332: {'title': "Palau: Nature's Sistine Chapel", 'slug': 'palau-natures-sistine-chaple', 'youtube_id': '5AiLoS6NlPc', 'channel': 'Oceans', 'cam_group': 'Documentary Films', 'cam_group_slug': 'documentary-films', 'live': False, 'location': 'Santa Monica, CA', 'partner': 'Explore.org', 'tags': '', 'canonical_url': 'https://explore.org/livecams/documentary-films/palau-natures-sistine-chaple', 'latlong': ['34.015342', '-118.499083']},
    340: {'title': 'Silver Springs Above Water Manatee Camera', 'slug': 'silver-springs-manatee-above-water', 'youtube_id': 'jxnehowX-9Y', 'channel': 'Oceans', 'cam_group': 'Save The Manatee', 'cam_group_slug': 'save-the-manatee', 'live': True, 'location': 'Silver Springs State Park, Florida', 'partner': 'Save The Manatee Club', 'tags': 'manatee, save the manatee, silver springs', 'canonical_url': 'https://explore.org/livecams/save-the-manatee/silver-springs-manatee-above-water', 'latlong': ['29.201450', '-82.050377']},
    341: {'title': 'Silver Springs underwater Manatee Camera', 'slug': 'silver-springs-manatee-underwater', 'youtube_id': 'zPqPFZMGTF8', 'channel': 'Oceans', 'cam_group': 'Save The Manatee', 'cam_group_slug': 'save-the-manatee', 'live': False, 'location': 'Silver Springs State Park, Florida', 'partner': 'Save The Manatee Club', 'tags': 'silver springs, manatee, save the manatee, under water', 'canonical_url': 'https://explore.org/livecams/save-the-manatee/silver-springs-manatee-underwater', 'latlong': ['29.201450', '-82.050377']},
    342: {'title': 'Back Channel Underwater Reef Cams', 'slug': 'utopia-village-multi-cams', 'youtube_id': 'nmjlQlYygB4', 'channel': 'Oceans', 'cam_group': 'Utopia Village', 'cam_group_slug': 'utopia-village', 'live': True, 'location': 'Utopia Village on Utila, The Bay Islands, Honduras', 'partner': 'Utopia Village', 'tags': '', 'canonical_url': 'https://explore.org/livecams/utopia-village/utopia-village-multi-cams', 'latlong': ['16.071753', '-86.951344']},
    # --- Pollinators ---
    55: {'title': 'Honey Bee Hive', 'slug': 'honey-bee-hive-cam', 'youtube_id': 'zpkN0ycubDs', 'channel': 'Pollinators', 'cam_group': 'Honey Bees', 'cam_group_slug': 'honey-bees', 'live': True, 'location': 'Buchloe, Germany', 'partner': 'Honey Bees', 'tags': 'beehive, honey, bavaria, germany, bees, hive, live', 'canonical_url': 'https://explore.org/livecams/honey-bees/honey-bee-hive-cam', 'latlong': ['47.993797', '10.776364']},
    57: {'title': 'Honey Bee Landing Zone', 'slug': 'honey-bee-landing-zone-cam', 'youtube_id': 'o49SYbWxWE0', 'channel': 'Pollinators', 'cam_group': 'Honey Bees', 'cam_group_slug': 'honey-bees', 'live': True, 'location': 'Buchloe, Germany', 'partner': 'Honey Bees', 'tags': 'honey, bavaria, germany, bees, beehive, live', 'canonical_url': 'https://explore.org/livecams/honey-bees/honey-bee-landing-zone-cam', 'latlong': ['47.993797', '10.776364']},
    129: {'title': 'The Giant Flying Fox', 'slug': 'giant-flying-fox-bat-cam', 'youtube_id': 'ojBaem3bwsE', 'channel': 'Pollinators', 'cam_group': 'Bats', 'cam_group_slug': 'bats', 'live': True, 'location': 'Gainesville, Florida, USA', 'partner': 'Lubee Bat Conservancy', 'tags': 'fruit bats, bats, lubee, florida, live', 'canonical_url': 'https://explore.org/livecams/bats/giant-flying-fox-bat-cam', 'latlong': ['29.826064', '-82.340935']},
    130: {'title': 'The Mixed Species Flying Fox Cam', 'slug': 'flying-fox-bat-cam', 'youtube_id': 'zH0IM95ia5w', 'channel': 'Pollinators', 'cam_group': 'Bats', 'cam_group_slug': 'bats', 'live': True, 'location': 'Gainesville, Florida, USA', 'partner': 'Lubee Bat Conservancy', 'tags': 'bats, live, flying', 'canonical_url': 'https://explore.org/livecams/bats/flying-fox-bat-cam', 'latlong': ['29.826064', '-82.340935']},
    # --- Sanctuaries ---
    301: {'title': 'Sloth TV', 'slug': 'sloth-cam', 'youtube_id': 'g_L1Ay8P244', 'channel': 'Sanctuaries', 'cam_group': 'Sanctuaries', 'cam_group_slug': 'sanctuaries', 'live': True, 'location': 'Heredia Province, Costa Rica', 'partner': 'Toucan Rescue Ranch', 'tags': 'toucan rescue ranch, sloth, sloth baby', 'canonical_url': 'https://explore.org/livecams/sanctuaries/sloth-cam', 'latlong': ['10.025400', '-84.046800']},
    343: {'title': 'Stall Moments', 'slug': 'kentucky-equine-foaling-shed', 'youtube_id': 'jzsOEjXYUXo', 'channel': 'Sanctuaries', 'cam_group': 'Kentucky Equine Horses', 'cam_group_slug': 'kentucky-equine-horses', 'live': True, 'location': 'Lexington, Kentucky', 'partner': 'Kentucky Equine Adoption Center', 'tags': '', 'canonical_url': 'https://explore.org/livecams/kentucky-equine-horses/kentucky-equine-foaling-shed', 'latlong': ['37.943765', '-84.574001']},
    346: {'title': 'Mares:  Candy, Lightning, and Marsha', 'slug': 'mares-and-foals', 'youtube_id': 'xo5dO__jQa0', 'channel': 'Sanctuaries', 'cam_group': 'Kentucky Equine Horses', 'cam_group_slug': 'kentucky-equine-horses', 'live': True, 'location': 'Lexington, Kentucky', 'partner': 'Kentucky Equine Adoption Center', 'tags': 'horse, kentucky, KYEAC, foal, mare', 'canonical_url': 'https://explore.org/livecams/kentucky-equine-horses/mares-and-foals', 'latlong': ['37.943765', '-84.574001']},
    # --- Zen Cams ---
    144: {'title': 'Great  White Sharks Meditation', 'slug': 'shark-meditation', 'youtube_id': 'Ea8cfSqKOfk', 'channel': 'Zen Cams', 'cam_group': 'Meditation', 'cam_group_slug': 'meditation', 'live': False, 'location': '', 'partner': 'Ocean One Diving', 'tags': 'shark, zen, meditation, ocean, underwater', 'canonical_url': 'https://explore.org/livecams/meditation/shark-meditation', 'latlong': ['29.0525', '118.2761']},
    152: {'title': 'The Arctic', 'slug': 'the-arctic', 'youtube_id': 'wZhYW3JfUDE', 'channel': 'Zen Cams', 'cam_group': 'Meditation', 'cam_group_slug': 'meditation', 'live': False, 'location': 'Churchill, Manitoba, Canada', 'partner': 'Polar Bears International', 'tags': 'arctic, canada, pbi, meditation, zen', 'canonical_url': 'https://explore.org/livecams/meditation/the-arctic', 'latlong': ['58.746801', '-93.815000']},
    188: {'title': 'Waimea Falls to the Beach Meditation', 'slug': 'waimea-falls-and-beach-meditation', 'youtube_id': 'VTTltMVYMKI', 'channel': 'Zen Cams', 'cam_group': 'Hawaii', 'cam_group_slug': 'hawaii', 'live': False, 'location': 'Waimea Bay - Oahu, Hawaii, USA', 'partner': 'North Shore Lifeguard Association', 'tags': 'waves, surf, ocean, waimea bay, hawaii, sunsets, north shore, beach, oahu, zen, meditation, live, wa', 'canonical_url': 'https://explore.org/livecams/hawaii/waimea-falls-and-beach-meditation', 'latlong': ['21.639915', '-158.063142']},
    195: {'title': 'Brown Bears of Katmai Alaska Meditation', 'slug': 'brown-bears-meditation', 'youtube_id': 'LuImCh7wL2I', 'channel': 'Zen Cams', 'cam_group': 'Brown Bears', 'cam_group_slug': 'brown-bears', 'live': False, 'location': 'Katmai National Park, Alaska, USA', 'partner': 'Katmai National Park', 'tags': 'brooks falls, katmai, alaska, brooks river, bears, meditation, waterfall', 'canonical_url': 'https://explore.org/livecams/brown-bears/brown-bears-meditation', 'latlong': ['58.554852', '-155.791862']},
    214: {'title': 'Kentucky Equine Adoption Center (KYEAC)', 'slug': 'kentucky-equine-horses', 'youtube_id': 'xhX5m1j8oTc', 'channel': 'Zen Cams', 'cam_group': 'Kentucky Equine Horses', 'cam_group_slug': 'kentucky-equine-horses', 'live': True, 'location': 'Lexington, Kentucky', 'partner': 'Kentucky Equine Adoption Center', 'tags': 'horses, kentucky, rescue, farm, live', 'canonical_url': 'https://explore.org/livecams/kentucky-equine-horses/kentucky-equine-horses', 'latlong': ['37.943765', '-84.574001']},
    287: {'title': 'International Wolf Center North Camera', 'slug': 'wolf-cam-1', 'youtube_id': '5e4lsEe4Vew', 'channel': 'Zen Cams', 'cam_group': 'International Wolf Center', 'cam_group_slug': 'international-wolf-center', 'live': True, 'location': 'Ely, MN', 'partner': 'International Wolf Center', 'tags': 'wolf, wolf center, international wolf center', 'canonical_url': 'https://explore.org/livecams/international-wolf-center/wolf-cam-1', 'latlong': ['47.910000', '-91.830000']},
    288: {'title': 'International Wolf Center South Camera', 'slug': 'wolf-cam-2', 'youtube_id': 'DRxYSIoBusQ', 'channel': 'Zen Cams', 'cam_group': 'International Wolf Center', 'cam_group_slug': 'international-wolf-center', 'live': True, 'location': 'Ely, MN', 'partner': 'International Wolf Center', 'tags': 'wolf, wolf center, international wolf center', 'canonical_url': 'https://explore.org/livecams/international-wolf-center/wolf-cam-2', 'latlong': ['47.910000', '-91.830000']},
    311: {'title': 'Mission Mountain Range', 'slug': 'mission-mountain-range', 'youtube_id': 'owCBxykcWDo', 'channel': 'Zen Cams', 'cam_group': 'Owl Research Institute ', 'cam_group_slug': 'owl-research-institute', 'live': True, 'location': 'Charlo, Montana, USA', 'partner': 'Owl Research Institute', 'tags': 'mission mountain, owl research institute, zen cams, pond, lake', 'canonical_url': 'https://explore.org/livecams/owl-research-institute/mission-mountain-range', 'latlong': ['47.438500', '-114.172300']},
    315: {'title': 'Muskox cam', 'slug': 'muskox-cam', 'youtube_id': 'dDda88X8Bl0', 'channel': 'Zen Cams', 'cam_group': 'Zen Den', 'cam_group_slug': 'zen-den', 'live': True, 'location': 'Fairbanks, Alaska', 'partner': 'University of Alaska Fairbanks Robert G. White Large Animal Research Station', 'tags': 'muskox, musk ox, University, university of alaska, UAF, baby muskox', 'canonical_url': 'https://explore.org/livecams/zen-den/muskox-cam', 'latlong': ['64.880999', '-147.868921']},
    322: {'title': 'Fairbanks Aurora Camera', 'slug': 'aurora-cam', 'youtube_id': 'O52zDyxg5QI', 'channel': 'Zen Cams', 'cam_group': 'University of Alaska Fairbanks', 'cam_group_slug': 'UAF', 'live': True, 'location': 'Fairbanks, Alaska', 'partner': 'University of Alaska Fairbanks', 'tags': 'northern lights, aurora, aurora borealis, northern lights live camera', 'canonical_url': 'https://explore.org/livecams/UAF/aurora-cam', 'latlong': ['64.880999', '-147.868921']},
    324: {'title': 'Sloth TV Playground Cam', 'slug': 'playground-cam', 'youtube_id': 'HVB888Oabhg', 'channel': 'Zen Cams', 'cam_group': 'Sloth', 'cam_group_slug': 'sloth', 'live': True, 'location': 'Heredia Province, Costa Rica', 'partner': 'Toucan Rescue Ranch', 'tags': 'sloth, sloth tv, rewilding recess', 'canonical_url': 'https://explore.org/livecams/sloth/playground-cam', 'latlong': ['10.025400', '-84.046800']},
    328: {'title': 'Texas Wildlife in an Austin Backyard', 'slug': 'backyard-cams', 'youtube_id': 'Jng6h2xYapk', 'channel': 'Zen Cams', 'cam_group': 'Texas Backyard Wildlife', 'cam_group_slug': 'texas-backyard-wildlife', 'live': True, 'location': 'Austin, Texas', 'partner': 'Texas Backyard Wildlife', 'tags': 'Texas Backyard Wildlife, TBW, raccoon, texas backyard', 'canonical_url': 'https://explore.org/livecams/texas-backyard-wildlife/backyard-cams', 'latlong': ['30.22164', '-97.84193']},
    329: {'title': 'Gray Fox Family', 'slug': 'gray-fox-family', 'youtube_id': 'Incb_ZsJQmY', 'channel': 'Zen Cams', 'cam_group': 'Texas Backyard Wildlife', 'cam_group_slug': 'texas-backyard-wildlife', 'live': False, 'location': 'Austin, Texas', 'partner': 'Texas Backyard Wildlife', 'tags': '', 'canonical_url': 'https://explore.org/livecams/texas-backyard-wildlife/gray-fox-family', 'latlong': ['30.22164', '-97.84193']},
    334: {'title': 'Red Panda Forest Park', 'slug': 'red-panda', 'youtube_id': 'EgGoouuVRRs', 'channel': 'Zen Cams', 'cam_group': 'Zen Den', 'cam_group_slug': 'zen-den', 'live': False, 'location': 'Sichuan, China', 'partner': 'Red Panda Forest Park', 'tags': '', 'canonical_url': 'https://explore.org/livecams/zen-den/red-panda', 'latlong': ['36.894451', '104.165649']},
    353: {'title': 'Mendenhall Glacier and Mountain Goat Cam', 'slug': 'tongass-mendenhall-glacier', 'youtube_id': 'jJI5w_RVGtQ', 'channel': 'Zen Cams', 'cam_group': 'Tongass National Forest', 'cam_group_slug': 'tongass-national-forest', 'live': True, 'location': 'Mendenhall Valley, Juneau Alaska', 'partner': 'Mendenhall Glacier - Tongass National Forest', 'tags': '', 'canonical_url': 'https://explore.org/livecams/tongass-national-forest/tongass-mendenhall-glacier', 'latlong': ['58.416944', '-134.545556']},
    368: {'title': "Zeab's Den", 'slug': 'mission-wolf-zeab', 'youtube_id': 'QFQF6AH1eb0', 'channel': 'Zen Cams', 'cam_group': 'Mission Wolf', 'cam_group_slug': 'mission-wolf', 'live': True, 'location': 'Gardner, Colorado', 'partner': 'Mission:Wolf', 'tags': '', 'canonical_url': 'https://explore.org/livecams/mission-wolf/mission-wolf-zeab', 'latlong': ['37.831718', '-105.194801']},
    369: {'title': "Shaman's Rock", 'slug': 'mission-wolf-shamans-rock', 'youtube_id': 'ExKSeDuMqbs', 'channel': 'Zen Cams', 'cam_group': 'Mission Wolf', 'cam_group_slug': 'mission-wolf', 'live': True, 'location': 'Gardner, Colorado', 'partner': 'Mission:Wolf', 'tags': '', 'canonical_url': 'https://explore.org/livecams/mission-wolf/mission-wolf-shamans-rock', 'latlong': ['37.831718', '-105.194801']},
    377: {'title': 'Sen SpaceTV -1', 'slug': 'sen-spacetv', 'youtube_id': 'fO9e9jnhYK8', 'channel': 'Zen Cams', 'cam_group': 'sen', 'cam_group_slug': 'sen', 'live': False, 'location': 'International Space Station in Low Earth Orbit', 'partner': 'Sen', 'tags': '', 'canonical_url': 'https://explore.org/livecams/sen/sen-spacetv', 'latlong': ['0', '0']},
    # --- All Cams ---
    366: {'title': 'Anan Wildlife Observatory Forest View', 'slug': 'anan-forest-view', 'youtube_id': 'SoW5SrDqv-o', 'channel': 'All Cams', 'cam_group': 'Four Bears', 'cam_group_slug': 'three-bears', 'live': False, 'location': 'Anan Wildlife Observatory Forest View', 'partner': 'Anan Wildlife Observatory- Tongass National Forest', 'tags': 'anan, black bears, black bear, Tongass National Forest, forest view', 'canonical_url': 'https://explore.org/livecams/three-bears/anan-forest-view', 'latlong': ['56.17906720580262', '-131.88362825260583']},
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line interface for quick exploration."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Explore.org live camera API client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("summary", help="Print system summary")
    sub.add_parser("live", help="List all currently-live cameras")
    sub.add_parser("all", help="List all cameras")
    sub.add_parser("channels", help="List channels")

    ch_p = sub.add_parser("channel", help="Cameras in a channel")
    ch_p.add_argument("name", help="Channel name e.g. 'Bears', 'Africa', 'Birds'")

    cg_p = sub.add_parser("group", help="Cameras in a cam-group")
    cg_p.add_argument("slug_or_id", help="Cam-group slug or ID")

    cam_p = sub.add_parser("camera", help="Camera details")
    cam_p.add_argument("id_or_slug", help="Camera ID (int) or slug")

    search_p = sub.add_parser("search", help="Search cameras")
    search_p.add_argument("query")

    snap_p = sub.add_parser("snapshots", help="Recent snapshots for a camera")
    snap_p.add_argument("camera_id", type=int)
    snap_p.add_argument("--n", type=int, default=5)

    export_p = sub.add_parser("export", help="Export camera list as JSON")
    export_p.add_argument("--offline", action="store_true", help="Include offline cameras")
    export_p.add_argument("-o", "--output", default="-", help="Output file (default: stdout)")

    sub.add_parser("popular", help="Top cameras by viewer count")

    args = parser.parse_args()
    client = ExploreOrgClient()

    if args.cmd == "summary" or args.cmd is None:
        print(client.summary())

    elif args.cmd == "live":
        cameras = client.get_live_cameras()
        print(f"Live cameras: {len(cameras)}")
        for cam in sorted(cameras, key=lambda c: c.title):
            viewers = f" ({cam.current_viewers:,} watching)" if cam.current_viewers else ""
            print(f"  [{cam.id:>4}] {cam.title:<55} yt:{cam.youtube_id}{viewers}")

    elif args.cmd == "all":
        cameras = client.get_all_cameras()
        print(f"All cameras: {len(cameras)}")
        for cam in sorted(cameras, key=lambda c: c.title):
            status = "LIVE  " if cam.is_live else "OFFLN"
            print(f"  [{status}] [{cam.id:>4}] {cam.title:<52} yt:{cam.youtube_id}")

    elif args.cmd == "channels":
        for ch in client.get_channels():
            cams = client.get_cameras_by_channel(ch.id)
            live = sum(1 for c in cams if c.is_live)
            print(f"  [{ch.id:>2}] {ch.title:<30} {len(cams):>3} cams ({live} live)")

    elif args.cmd == "channel":
        cameras = client.get_cameras_by_channel(args.name)
        if not cameras:
            print(f"Channel '{args.name}' not found or empty.", file=sys.stderr)
            print("Available channels:", ", ".join(c.title for c in client.get_channels()))
            sys.exit(1)
        live = sum(1 for c in cameras if c.is_live)
        print(f"Channel '{args.name}': {len(cameras)} cameras ({live} live)")
        for cam in sorted(cameras, key=lambda c: c.title):
            status = "LIVE" if cam.is_live else "OFF"
            print(f"  [{status:>4}] {cam.title:<55} yt:{cam.youtube_id}")
            print(f"         {cam.explore_url}")

    elif args.cmd == "group":
        try:
            cg_id = int(args.slug_or_id)
        except ValueError:
            cg_id = None
        cg = client.get_cam_group(cg_id or args.slug_or_id)
        if not cg:
            print(f"Cam group '{args.slug_or_id}' not found.", file=sys.stderr)
            sys.exit(1)
        cameras = client.get_cameras_by_cam_group(cg.id)
        print(f"Cam Group '{cg.title}' ({cg.slug}): {len(cameras)} cameras")
        for cam in sorted(cameras, key=lambda c: c.title):
            status = "LIVE" if cam.is_live else "OFF"
            print(f"  [{status}] {cam.title} — {cam.youtube_watch_url}")

    elif args.cmd == "camera":
        try:
            cid = int(args.id_or_slug)
            cam = client.get_camera_detail(cid)
        except ValueError:
            cached = client.get_camera_by_slug(args.id_or_slug)
            if cached:
                cam = client.get_camera_detail(cached.id)
            else:
                cam = None
        if cam:
            print(cam)
            if cam.description_text:
                print(f"\nDescription:\n  {cam.description_text[:500]}")
            if cam.tags:
                print(f"\nTags: {cam.tags}")
        else:
            print(f"Camera '{args.id_or_slug}' not found.", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "search":
        results = client.search(args.query)
        cams = results["cameras"]
        print(f"Search '{args.query}': {len(cams)} cameras found")
        for c in cams:
            cid = c.get("id")
            # Cross-reference with catalogue to get youtube_id (search API omits it)
            cat = CAMERA_CATALOGUE.get(cid, {})
            vid = cat.get("youtube_id", "")
            status = "LIVE" if not c.get("is_inactive") else "OFF"
            yt_url = f"https://www.youtube.com/watch?v={vid}" if vid else "(see camera detail)"
            print(f"  [{status}] [{cid}] {c.get('title')}")
            print(f"         yt: {yt_url}")
            print(f"         location: {c.get('location_text', '')}")
        if results["blog_posts"]:
            print(f"\nBlog posts: {len(results['blog_posts'])}")

    elif args.cmd == "snapshots":
        snaps = client.get_camera_snapshots(args.camera_id, per_page=args.n)
        cam = client.get_camera(args.camera_id)
        print(f"Recent snapshots for camera {args.camera_id}"
              f"{' (' + cam.title + ')' if cam else ''}:")
        for s in snaps:
            user = s.display_name or s.username or "anonymous"
            print(f"  [{s.created_at}] by {user}: {s.caption or '(no caption)'}")
            print(f"    {s.full_url}")

    elif args.cmd == "export":
        data = client.export_camera_list(include_offline=args.offline)
        output = json.dumps(data, indent=2, ensure_ascii=False)
        if args.output == "-":
            print(output)
        else:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Exported {len(data)} cameras to {args.output}")

    elif args.cmd == "popular":
        print("Top 20 cameras by current viewer count:")
        for i, cam in enumerate(client.get_most_popular_cameras(20), 1):
            status = "LIVE" if cam.is_live else "OFF"
            viewers = cam.current_viewers or 0
            print(f"  {i:>2}. [{status}] {viewers:>6} viewers  {cam.title}")
            print(f"       {cam.youtube_watch_url}")


if __name__ == "__main__":
    main()
