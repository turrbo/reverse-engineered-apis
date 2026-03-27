"""
Explore.org Wildlife Camera API Client
=======================================
Reverse-engineered Python client for explore.org's live wildlife camera system.

Discovered endpoints (no authentication required for read operations):

  REST API (both hosts serve identical data):
    https://explore.org/api/...
    https://omega.explore.org/api/...   (internal/mirror host)

  Streaming CDN:
    https://d11gsgd2hj8qxd.cloudfront.net/streams.json
    https://outbound-production.explore.org/stream-production-{stream_id}/.m3u8

  Snapshot CDN:
    https://snapshots.explore.org/{template}-EDGE/{template}-EDGE-{unix_ts}.jpg
    https://snapshots.explore.org/{template}-EDGE/{template}-EDGE-{unix_ts}-scaled.jpg
    https://files.explore.org/sn/{year}/{month}/{day}/{filename}.jpg  (user-submitted)

  Media CDN:
    https://media.explore.org/stillframes/{filename}
    https://media.explore.org/posters/{filename}
    https://media.explore.org/blurred-snapshots/{slug}_blurred.jpg

  WebSocket (live snapshot feed):
    wss://snapdata.prod.explore.org/oldest/{template}-EDGE

  Comments GraphQL:
    https://comments.explore.org/graphql

Usage example:
    client = ExploreOrgClient()
    cameras = client.list_cameras()
    active = client.list_active_cameras()
    bears = client.get_cameras_by_channel('Bears')
    stream = client.get_stream_url(stream_id=216)
    results = client.search('eagle')
    snaps = client.list_snapshots(per_page=20)
"""

import time
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode

try:
    import requests
    from requests import Session
except ImportError:
    raise ImportError("Install requests: pip install requests")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_API = "https://explore.org/api"
OMEGA_API = "https://omega.explore.org/api"
STREAMS_CDN = "https://d11gsgd2hj8qxd.cloudfront.net"
OUTBOUND_BASE = "https://outbound-production.explore.org"
SNAPSHOTS_BASE = "https://snapshots.explore.org"
MEDIA_BASE = "https://media.explore.org"
FILES_BASE = "https://files.explore.org"
SNAPDATA_WS = "wss://snapdata.prod.explore.org/oldest"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://explore.org/livecams",
}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ExploreOrgClient:
    """
    Client for the explore.org live wildlife camera platform.

    All public methods return plain Python dicts/lists so callers can work
    with the data without any framework dependency.  Original API response
    keys are preserved unchanged.

    Camera data model (from /api/livecams):
        id, uuid, active, title, slug, offline_label,
        primary_channel_id, primary_nav_channel_id, primary_cam_group_id,
        location_id, primary_canonical_camgroup_id, date_live,
        meta_description, description, poster, thumbnail_large_url,
        stillframe { uuid, original_uri, image_set { width, height } },
        is_featured, partner_id, best_viewing_start_time,
        best_viewing_end_time, prime_all_day, prime_all_night,
        is_meditation, snapshot_enabled, is_offline, recordings_template,
        wowza_fqdn, recording_priority, twitter_text, pinterest_text,
        facebook_text, legacy_id

    Stream data model (from streams CDN):
        id, name, playlistUrl, snapshotHost, placeholderUrl,
        currentTime, state ("live" | "on_demand"), numberOfViewers

    Feed data model (from /api/get_cam_group_snapshots.json):
        id, uuid, title, slug, description, is_inactive, is_offline,
        is_meditation, is_film, force_offline, offline_label,
        thumbnail_large_url, thumb, thumb_large, stillframe_imageset,
        blurred_snapshot_url, snapshot_enabled, snapshot, current_viewers,
        recordings_template, stream_id, cam_group { id }, order,
        timestamp
    """

    def __init__(
        self,
        timeout: int = 20,
        use_omega: bool = False,
    ):
        """
        Args:
            timeout:    Default HTTP request timeout in seconds.
            use_omega:  If True, use omega.explore.org instead of explore.org.
                        Both return identical data; omega is the internal mirror.
        """
        self.timeout = timeout
        self.base = OMEGA_API if use_omega else BASE_API
        self._session = Session()
        self._session.headers.update(DEFAULT_HEADERS)

        # In-memory cache to avoid hammering the API during a session
        self._cameras_cache: Optional[List[Dict]] = None
        self._camgroups_cache: Optional[List[Dict]] = None
        self._channels_cache: Optional[List[Dict]] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[Dict] = None) -> Any:
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _api(self, path: str, params: Optional[Dict] = None) -> Any:
        return self._get(f"{self.base}/{path.lstrip('/')}", params=params)

    def _streams_cdn(self, path: str, params: Optional[Dict] = None) -> Any:
        return self._get(f"{STREAMS_CDN}/{path.lstrip('/')}", params=params)

    # ------------------------------------------------------------------
    # Cameras (livecams)
    # ------------------------------------------------------------------

    def list_cameras(self, refresh: bool = False) -> List[Dict]:
        """
        Return all 200+ cameras from /api/livecams.

        Each dict contains full metadata including stillframe image URLs,
        wowza_fqdn, recordings_template (used to build HLS/snapshot URLs),
        and is_offline status.

        Responses are cached for the lifetime of this client instance.
        Pass refresh=True to force a fresh fetch.
        """
        if self._cameras_cache is None or refresh:
            data = self._api("livecams")
            self._cameras_cache = data["data"]["livecams"]
        return self._cameras_cache

    def list_active_cameras(self) -> List[Dict]:
        """Return only cameras currently streaming (is_offline=False)."""
        return [c for c in self.list_cameras() if not c.get("is_offline")]

    def list_offline_cameras(self) -> List[Dict]:
        """Return only cameras currently offline or in off-season."""
        return [c for c in self.list_cameras() if c.get("is_offline")]

    def list_featured_cameras(self) -> List[Dict]:
        """Return cameras flagged is_featured=True."""
        return [c for c in self.list_cameras() if c.get("is_featured")]

    def get_camera_by_slug(self, slug: str) -> Optional[Dict]:
        """
        Look up a single camera by its URL slug.

        Example slugs: 'decorah-eagles', 'brooks-falls-brown-bears-underwater',
        'manatee-cam-above-water', 'puppy-cam'
        """
        for cam in self.list_cameras():
            if cam.get("slug") == slug:
                return cam
        return None

    def get_camera_by_id(self, camera_id: int) -> Optional[Dict]:
        """Look up a single camera by its numeric id."""
        for cam in self.list_cameras():
            if cam.get("id") == camera_id:
                return cam
        return None

    def get_cameras_by_channel(self, channel_name: str) -> List[Dict]:
        """
        Return cameras whose primary_channel_id matches the given channel title.

        Channel names (case-insensitive):
            'Featured', 'Africa', 'Bears', 'Birds', 'Oceans',
            'Dog Bless You', 'Cat Rescues', 'Sanctuaries', 'Zen Cams',
            'All Cams', 'Multi-View'
        """
        channels = self.list_channels()
        channel_id = None
        for ch in channels:
            if ch["title"].lower() == channel_name.lower():
                channel_id = ch["id"]
                break
        if channel_id is None:
            return []
        return [
            c for c in self.list_cameras()
            if c.get("primary_channel_id") == channel_id
        ]

    def get_cameras_with_hls(self) -> List[Dict]:
        """
        Return cameras that have HLS/Wowza streaming configured.

        These cameras have a non-null wowza_fqdn and recordings_template.
        Use get_stream_url() with the camera's stream_id for the actual
        playlist URL.
        """
        return [
            c for c in self.list_cameras()
            if c.get("wowza_fqdn") and c.get("recordings_template")
        ]

    def get_cameras_with_snapshots(self) -> List[Dict]:
        """Return cameras with snapshot capture enabled (snapshot_enabled=True)."""
        return [c for c in self.list_cameras() if c.get("snapshot_enabled")]

    # ------------------------------------------------------------------
    # Camera groups (cam_groups)
    # ------------------------------------------------------------------

    def list_camgroups(self, refresh: bool = False) -> List[Dict]:
        """
        Return all 108 camera groups (sub-categories/partnerships).

        Each group has: id, uuid, active, title, slug, image_url,
        poster_url, poster { image_set }, multi_livecam, location_text.

        Examples: 'Brown Bears', 'African Wildlife', 'Decorah Eagles',
        'Monterey Bay Aquarium', 'Kitten Rescue', 'Warrior Canine Connection'
        """
        if self._camgroups_cache is None or refresh:
            data = self._api("camgroups")
            self._camgroups_cache = data["data"]["camgroups"]
        return self._camgroups_cache

    def get_camgroup_by_slug(self, slug: str) -> Optional[Dict]:
        """Look up a camera group by its URL slug."""
        for cg in self.list_camgroups():
            if cg.get("slug") == slug:
                return cg
        return None

    def get_camgroup_by_id(self, group_id: int) -> Optional[Dict]:
        """Look up a camera group by its numeric id."""
        for cg in self.list_camgroups():
            if cg.get("id") == group_id:
                return cg
        return None

    def get_camgroup_feeds(
        self,
        group_id: int,
        timestamp: int = 0,
    ) -> List[Dict]:
        """
        Return the feed list for a camera group including live snapshot URLs,
        stream_id, current_viewers, and is_offline status.

        This is the richest single endpoint – it returns the same camera data
        the web player uses to populate the sidebar and decide what to play.

        Args:
            group_id:   Numeric camera group id (see list_camgroups()).
            timestamp:  Unix timestamp for cache-busting; 0 = latest.

        Notable group ids:
            2   = African Wildlife          5   = Decorah Eagles
            20  = Brown Bears               21  = Brooks Falls Bears
            22  = Brooks Falls Underwater   43  = Monterey Bay Aquarium (Oceans)
            75  = Polar Bears Intl          79  = All/Featured (127 feeds)
            95  = All Bears combined        122 = Manatees (Blue Spring)
        """
        data = self._api(
            "get_cam_group_snapshots.json",
            params={"t": timestamp, "id": group_id},
        )
        return data.get("data", [])

    # ------------------------------------------------------------------
    # Channels (top-level navigation categories)
    # ------------------------------------------------------------------

    def list_channels(self, refresh: bool = False) -> List[Dict]:
        """
        Return the 11 top-level navigation channels.

        Each channel has: id, title, cam_groups (list of group ids), order.

        Channels:
            id=16 Featured   id=1  Africa      id=5  Bears
            id=4  Birds       id=10 Oceans      id=8  Dog Bless You
            id=7  Cat Rescues id=18 Sanctuaries id=13 Zen Cams
            id=20 All Cams    id=21 Multi-View
        """
        if self._channels_cache is None or refresh:
            data = self._api("channels")
            self._channels_cache = data["data"]
        return self._channels_cache

    def get_channel_by_name(self, name: str) -> Optional[Dict]:
        """Return a channel dict by title (case-insensitive)."""
        for ch in self.list_channels():
            if ch["title"].lower() == name.lower():
                return ch
        return None

    # ------------------------------------------------------------------
    # Live stream URLs (HLS / m3u8)
    # ------------------------------------------------------------------

    def list_streams(self, stream_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Return live stream metadata from the streaming CDN.

        When stream_ids is None, returns all ~145 streams.
        When stream_ids is provided, returns only those streams.

        Each stream dict:
            id              Numeric stream id (matches feed.stream_id)
            name            Human-readable name
            playlistUrl     Direct HLS m3u8 URL (works without auth)
            snapshotHost    Hostname for snapshot images
            placeholderUrl  Offline placeholder image URL
            currentTime     ISO8601 timestamp at the camera's local time
            state           "live" | "on_demand"
            numberOfViewers Current concurrent viewer count

        HLS playlist URL pattern:
            https://outbound-production.explore.org/stream-production-{id}/.m3u8

        Note: The Cloudfront endpoint does NOT require authentication.
        The cameraToken / Bearer auth in the JS source is only needed for
        certain authenticated features (snapshot submission, ratings, etc.).
        """
        params: Dict[str, Any] = {}
        if stream_ids:
            # API accepts repeated q[id_in][] params
            parts = "&".join(f"q[id_in][]={sid}" for sid in stream_ids)
            url = f"{STREAMS_CDN}/streams.json?{parts}"
            data = self._get(url)
        else:
            data = self._streams_cdn("streams.json", params=params)
        return data.get("streams", [])

    def list_live_streams(self) -> List[Dict]:
        """Return only streams with state='live'."""
        return [s for s in self.list_streams() if s.get("state") == "live"]

    def list_on_demand_streams(self) -> List[Dict]:
        """Return streams with state='on_demand' (looping recorded content)."""
        return [s for s in self.list_streams() if s.get("state") == "on_demand"]

    def get_stream(self, stream_id: int) -> Optional[Dict]:
        """Return stream info for a single stream id, or None if not found."""
        streams = self.list_streams(stream_ids=[stream_id])
        for s in streams:
            if s.get("id") == stream_id:
                return s
        return None

    def get_stream_url(self, stream_id: int) -> Optional[str]:
        """
        Return the direct HLS playlist URL for a stream.

        The returned URL can be opened with any HLS-capable player
        (ffplay, VLC, hls.js, etc.) without any authentication.

        Example:
            url = client.get_stream_url(216)
            # https://outbound-production.explore.org/stream-production-216/.m3u8
        """
        stream = self.get_stream(stream_id)
        if stream:
            return stream.get("playlistUrl")
        # Construct it directly if the CDN lookup fails
        return f"{OUTBOUND_BASE}/stream-production-{stream_id}/.m3u8"

    def build_stream_url(self, stream_id: int) -> str:
        """
        Construct the HLS URL directly without an API call.

        Use this when you already know the stream_id from a camera feed.
        """
        return f"{OUTBOUND_BASE}/stream-production-{stream_id}/.m3u8"

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def build_snapshot_url(
        self,
        recordings_template: str,
        unix_timestamp: Optional[int] = None,
        scaled: bool = True,
    ) -> str:
        """
        Build a snapshot image URL from a camera's recordings_template.

        The recordings_template comes from cameras in list_cameras() or
        get_camgroup_feeds().  Each 10-second HLS segment generates a
        snapshot with the segment's UTC timestamp.

        Args:
            recordings_template:  e.g. 'EXP-STMSurface', 'EXP-FallsLow'
            unix_timestamp:       UTC unix timestamp of the snapshot.
                                  If None, uses the current time (approximate).
            scaled:               If True, returns the downscaled version.
                                  If False, returns the full-resolution image.

        Snapshot URL pattern:
            https://snapshots.explore.org/{template}-EDGE/
                {template}-EDGE-{unix_ts}[-scaled].jpg
        """
        if unix_timestamp is None:
            unix_timestamp = int(time.time())
        suffix = "-scaled" if scaled else ""
        stem = f"{recordings_template}-EDGE"
        return f"{SNAPSHOTS_BASE}/{stem}/{stem}-{unix_timestamp}{suffix}.jpg"

    def list_snapshots(
        self,
        livecam_id: Optional[int] = None,
        cam_group_id: Optional[int] = None,
        per_page: int = 20,
        cursor: Optional[str] = None,
    ) -> Dict:
        """
        Return user-submitted snapshots with cursor-based pagination.

        Args:
            livecam_id:   Filter by numeric livecam id.
            cam_group_id: Filter by cam group id.
            per_page:     Results per page (default 20).
            cursor:       Pagination cursor from previous response's
                          meta.next_cursor.

        Returns a dict with:
            data    List of snapshot dicts
            meta    { path, per_page, next_cursor, prev_cursor }
            links   { first, last, prev, next }

        Snapshot dict keys:
            title, caption, thumbnail, snapshot, num_favorites,
            username, user_id, uuid, display_name, avatar_uri,
            timezone, timestamp, local_time, created_at,
            livecam_id, youtube_id, youtube_delta

        Pagination example:
            page1 = client.list_snapshots(per_page=50)
            cursor = page1['meta']['next_cursor']
            page2 = client.list_snapshots(per_page=50, cursor=cursor)
        """
        params: Dict[str, Any] = {"per_page": per_page}
        if livecam_id is not None:
            params["livecam_id"] = livecam_id
        if cam_group_id is not None:
            params["cam_group_id"] = cam_group_id
        if cursor is not None:
            params["cursor"] = cursor
        return self._api("snapshots/all", params=params)

    def iter_snapshots(
        self,
        livecam_id: Optional[int] = None,
        cam_group_id: Optional[int] = None,
        per_page: int = 20,
        max_pages: int = 10,
    ):
        """
        Yield all snapshots across pages (generator).

        Args:
            max_pages: Safety limit on number of pages fetched.
        """
        cursor = None
        for _ in range(max_pages):
            resp = self.list_snapshots(
                livecam_id=livecam_id,
                cam_group_id=cam_group_id,
                per_page=per_page,
                cursor=cursor,
            )
            items = resp.get("data", [])
            yield from items
            cursor = resp.get("meta", {}).get("next_cursor")
            if not cursor:
                break

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> List[Dict]:
        """
        Search across cameras, camera groups, and content.

        Returns a list of feed dicts that match the query.  Each result
        includes cam_group, title, slug, recordings_template, stream_id,
        thumbnail_large_url, current_viewers, and is_inactive.

        The search endpoint is at omega.explore.org regardless of whether
        use_omega was set; the BASE_API mirror does not expose it.
        """
        params = {"q": query}
        data = self._get(
            f"{OMEGA_API}/search_results.json",
            params=params,
        )
        # Returns {"status":..., "message":..., "data": {"feeds": [...]}}
        return data.get("data", {}).get("feeds", [])

    # ------------------------------------------------------------------
    # Events / schedule
    # ------------------------------------------------------------------

    def list_events(self) -> List[Dict]:
        """
        Return the full event schedule (1 000+ entries).

        Events correspond to live chat shows, guided tours, and special
        broadcasts.  Each event has: id, event_id (Google Calendar uid),
        is_canceled, summary, description, start_time, end_time,
        created_at, updated_at, is_all_day.
        """
        data = self._api("events")
        return data.get("data", {}).get("events", [])

    def list_upcoming_events(self, after_ts: Optional[float] = None) -> List[Dict]:
        """
        Return events that start after after_ts (Unix timestamp).

        Defaults to events starting after the current time.
        """
        if after_ts is None:
            after_ts = time.time()
        from datetime import timezone, datetime
        events = self.list_events()
        result = []
        for ev in events:
            try:
                start_str = ev.get("start_time", "")
                # Handle both Z and +00:00 timezone formats
                start_str = start_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(start_str)
                if dt.timestamp() > after_ts and not ev.get("is_canceled"):
                    result.append(ev)
            except Exception:
                continue
        result.sort(key=lambda e: e.get("start_time", ""))
        return result

    # ------------------------------------------------------------------
    # Convenience / aggregation
    # ------------------------------------------------------------------

    def camera_summary(self) -> Dict:
        """
        Return a high-level summary of the camera ecosystem.

        Returns:
            {
                total_cameras:      int,
                active_cameras:     int,
                offline_cameras:    int,
                featured_cameras:   int,
                snapshot_enabled:   int,
                has_hls_stream:     int,
                total_camgroups:    int,
                total_channels:     int,
                total_live_streams: int,
                total_streams:      int,
            }
        """
        cameras = self.list_cameras()
        streams = self.list_streams()
        return {
            "total_cameras": len(cameras),
            "active_cameras": sum(1 for c in cameras if not c.get("is_offline")),
            "offline_cameras": sum(1 for c in cameras if c.get("is_offline")),
            "featured_cameras": sum(1 for c in cameras if c.get("is_featured")),
            "snapshot_enabled": sum(1 for c in cameras if c.get("snapshot_enabled")),
            "has_hls_stream": sum(
                1 for c in cameras
                if c.get("wowza_fqdn") and c.get("recordings_template")
            ),
            "total_camgroups": len(self.list_camgroups()),
            "total_channels": len(self.list_channels()),
            "total_live_streams": sum(1 for s in streams if s.get("state") == "live"),
            "total_streams": len(streams),
        }

    def most_watched(self, top_n: int = 20) -> List[Dict]:
        """
        Return streams sorted by current viewer count, descending.

        Merges stream data (numberOfViewers) with camera metadata.
        """
        streams = self.list_streams()
        streams_sorted = sorted(
            streams,
            key=lambda s: s.get("numberOfViewers", 0),
            reverse=True,
        )
        return streams_sorted[:top_n]

    def get_camera_with_stream(self, camera: Dict) -> Dict:
        """
        Enrich a camera dict with its live stream information.

        Adds a 'stream' key containing the stream object from the CDN
        (or None if no stream_id is available).

        Typically used after get_camgroup_feeds() which provides stream_id.
        """
        stream_id_raw = camera.get("stream_id")
        if stream_id_raw is None:
            camera["stream"] = None
            return camera
        try:
            stream_id = int(stream_id_raw)
        except (ValueError, TypeError):
            camera["stream"] = None
            return camera
        camera["stream"] = self.get_stream(stream_id)
        return camera

    # ------------------------------------------------------------------
    # URL builders (no network calls)
    # ------------------------------------------------------------------

    def camera_page_url(self, cam_group_slug: str, camera_slug: str) -> str:
        """Build the canonical page URL for a camera on explore.org."""
        return f"https://explore.org/livecams/{cam_group_slug}/{camera_slug}"

    def youtube_embed_url(self, youtube_id: str) -> str:
        """Build a YouTube embed URL for offline/highlights content."""
        return (
            f"https://www.youtube.com/embed/{youtube_id}"
            "?rel=0&showinfo=0&autoplay=1&playsinline=1"
        )

    def stillframe_url(self, camera: Dict, width: int = 1280) -> Optional[str]:
        """
        Extract a specific-width stillframe image URL from a camera dict.

        Args:
            camera: Camera dict from list_cameras().
            width:  Desired image width in pixels.
                    Available widths: 498, 853, 1280, 1920

        Returns URL string or None.
        """
        try:
            return camera["stillframe"]["image_set"]["width"][str(width)]
        except (KeyError, TypeError):
            return camera.get("thumbnail_large_url")

    def poster_url(self, camgroup: Dict, width: int = 480) -> Optional[str]:
        """
        Extract a poster image URL from a camera group dict.

        Args:
            camgroup: Camera group dict from list_camgroups().
            width:    Desired image width. Available: 200, 320, 480, 720
        """
        try:
            return camgroup["poster"]["image_set"]["width"][str(width)]
        except (KeyError, TypeError):
            return camgroup.get("image_url")


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _demo():
    """Quick demonstration of the client capabilities."""
    import json

    client = ExploreOrgClient()

    print("=== Explore.org Camera API Client Demo ===\n")

    # Summary
    summary = client.camera_summary()
    print("Camera Ecosystem Summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print()

    # Channels
    print("Top-Level Channels:")
    for ch in client.list_channels():
        print(f"  [{ch['id']:2d}] {ch['title']} ({len(ch['cam_groups'])} groups)")
    print()

    # Active cameras sample
    active = client.list_active_cameras()
    print(f"Active cameras (first 5 of {len(active)}):")
    for cam in active[:5]:
        template = cam.get("recordings_template", "N/A")
        print(f"  {cam['title']} | template={template}")
    print()

    # Most watched streams
    print("Top 5 most-watched streams right now:")
    for s in client.most_watched(top_n=5):
        print(
            f"  [{s['id']:4d}] {s['name']:<45} "
            f"viewers={s['numberOfViewers']:4d}  state={s['state']}"
        )
    print()

    # Search
    results = client.search("eagle")
    print(f"Search 'eagle' -> {len(results)} results (first 3):")
    for r in results[:3]:
        active_str = "inactive" if r.get("is_inactive") else "active"
        cg = r.get("cam_group", {}).get("title", "?")
        print(f"  {r['title']} [{cg}] {active_str}")
    print()

    # Bear cameras
    bear_feeds = client.get_camgroup_feeds(group_id=20)
    print(f"Brown Bears group ({len(bear_feeds)} feeds):")
    for f in bear_feeds[:4]:
        snap = f.get("snapshot", "")[-40:] if f.get("snapshot") else "none"
        print(
            f"  {f['title']:<45} stream_id={f.get('stream_id'):<6} "
            f"offline={f['is_offline']}  snap=...{snap}"
        )
    print()

    # Build example URLs
    cam = active[0]
    template = cam.get("recordings_template", "EXP-Example")
    snap_url = client.build_snapshot_url(template)
    print(f"Example snapshot URL for '{cam['title']}':")
    print(f"  {snap_url}")
    print()

    print("Recent user snapshots (3):")
    snaps_resp = client.list_snapshots(per_page=3)
    for sn in snaps_resp.get("data", []):
        print(f"  [{sn['livecam_id']}] {sn['title']} by {sn['display_name']}")
        print(f"    {sn['snapshot']}")


if __name__ == "__main__":
    _demo()
