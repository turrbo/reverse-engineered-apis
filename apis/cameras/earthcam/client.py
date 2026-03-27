"""
EarthCam Internal API Client
=============================
Reverse-engineered Python client for EarthCam's internal API.

Discovered via static JS analysis and HTML page inspection of:
  - https://www.earthcam.com
  - https://static.earthcam.com/js/earthcam/functions.ecntemplate.js
  - https://static.earthcam.com/js/earthcam/ecnplayerhtml5/js/ecnplayerhtml5-package.js
  - https://www.earthcam.com/network/
  - https://www.earthcam.com/mapsearch/

No authentication required for any of the endpoints below.
All endpoints return JSON unless noted.

Author: Reverse-engineered 2026-03-27
"""

import requests
import json
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode, quote


class EarthCamClient:
    """
    Client for EarthCam's undocumented internal API.

    All methods return parsed JSON as Python dicts/lists.
    No API keys or authentication required.

    Key concepts:
      - group_id:  URL path identifier for a camera group (e.g. "timessquare", "niagarafalls")
      - cam_name:  Individual camera identifier within a group (e.g. "tsrobo1")
      - id:        32-char hex camera UUID used for camera metadata lookups
      - dnet:      32-char hex network ID used for archive (recorded clip) lookups
      - stream:    Full HLS m3u8 URL with a short-lived signed token (?t=...&td=...)
    """

    BASE_URL = "https://www.earthcam.com"
    STATIC_BASE = "https://static.earthcam.com"
    VIDEO_BASE = "https://videos-3.earthcam.com"
    ARCHIVE_BASE = "https://video2archives.earthcam.com"

    # Thumbnail sizes available at static.earthcam.com/camshots/{size}/{hash}.jpg
    THUMBNAIL_SIZES = ["128x72", "256x144", "512x288", "1816x1024"]

    def __init__(self, timeout: int = 30):
        self.session = requests.Session()
        self.timeout = timeout
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.earthcam.com/",
            "Origin": "https://www.earthcam.com",
            "Accept": "application/json, text/plain, */*",
        })

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Make a GET request to the EarthCam base URL and return parsed JSON."""
        url = self.BASE_URL + path
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # ECTV / Player Endpoints
    # -------------------------------------------------------------------------

    def get_config(self) -> Dict:
        """
        GET /api/ectv/config

        Returns the global ECTV app configuration including:
          - All available category names + their enabled/disabled status
          - Template URLs for all other API endpoints (with %1% placeholders)
          - Weather, notifications, and user preference settings
          - Playlist refresh rates and ad configuration

        Returns: dict with keys: status, msg, data (contains api, network, user, etc.)
        """
        return self._get("/api/ectv/config")

    def get_playlist(self, nc: Optional[str] = None) -> Dict:
        """
        GET /api/ectv/player/playlist.php?r=playlist&a=fetch[&nc=<category>]
        GET /api/ectv/player/playlist?r=playlist&a=fetch  (no .php variant also works)

        Returns the featured and trending camera playlists for the ECTV app.
        The optional `nc` param may filter but in practice seems to return the same
        trending/featured playlists regardless of value.

        Args:
            nc: Optional category filter (e.g. "beaches", "cities", "animals").
                Observed to have minimal effect on output.

        Returns: dict with keys:
            data.playlist_trending.playlist_items  - 4 currently trending cameras
            data.playlist_featured.playlist_items  - 8 featured/curated cameras

        Each playlist item contains:
            title, city, country, state, url, stream (HLS m3u8 with signed token),
            thumbnail, thumbnail_large, thumbnail_hd, latitude, longitude,
            timezone, metar, views, likes, cam_state (1=live, 0=offline),
            backup_clip, item_id, group_id, routing_name
        """
        params = {"r": "playlist", "a": "fetch"}
        if nc:
            params["nc"] = nc
        return self._get("/api/ectv/player/playlist.php", params)

    # -------------------------------------------------------------------------
    # Player / Camera Page Endpoints
    # -------------------------------------------------------------------------

    def get_camera_group(self, group_id: str) -> Dict:
        """
        GET /api/player/ecn_cameras?r=page&a=fetch&g=<group_id>

        Returns full metadata for all cameras in a group. This is the primary
        endpoint for getting live stream URLs.

        Args:
            group_id: Group identifier from the camera page URL path.
                      Examples: "timessquare", "niagarafalls", "dublin",
                                "london", "paris", "miami", "chicago"

        Returns: dict with keys:
            data.cam            - dict of {cam_name: camera_object}
            data.js_cam_list    - list of cam_name strings in order
            data.timelapse_checks - list of camera IDs with timelapse
            data.bestof_checks  - list of camera IDs with best-of archives

        Each camera object contains (notable fields):
            cam_name, id, inet, dnet
            stream              - Full HLS URL with signed token (short-lived ~1hr)
            html5_streamingdomain
            html5_streampath    - HLS path with signed token
            livestreamingpath   - Raw RTMP path (e.g. /fecnetwork/hdtimes10.flv)
            android_livepath    - HLS path without token
            streamingdomain     - RTMP domain
            archivedomain_html5 - Archive domain
            archivepath_html5   - Archive 24hr timelapse path
            backup_clip         - Fallback VOD clip URL
            thumbnail_128/256/512 - Static thumbnail URLs
            city, state, country, latitude, longitude, timezone, metar
            liveon, archiveon, timelapseon, hofon
            title, title_full, description, location
            likes, streamviews
        """
        return self._get("/api/player/ecn_cameras", {
            "r": "page", "a": "fetch", "g": group_id
        })

    def get_camera_page_info(self, group_id: str) -> Dict:
        """
        GET /api/player/ecn_page?r=page&a=fetch&x=<group_id>

        Returns page-level metadata for a camera group page (SEO/display info).

        Args:
            group_id: Group identifier (e.g. "timessquare")

        Returns: dict with keys:
            data.array.page_title, meta_keywords, meta_description,
            default_cam, extra_copy, greeting, page_background, page_header
        """
        return self._get("/api/player/ecn_page", {
            "r": "page", "a": "fetch", "x": group_id
        })

    def get_map_icon(self, state: str, country: str = "United States") -> Dict:
        """
        GET /api/player/map?s=<state>&c=<country>

        Returns the map icon path for a US state or country.

        Args:
            state: Two-letter state code (e.g. "NY") or full state name
            country: Country name

        Returns: dict with key "path" containing relative icon URL
        """
        return self._get("/api/player/map", {"s": state, "c": country})

    # -------------------------------------------------------------------------
    # dotcom / Network Endpoints
    # -------------------------------------------------------------------------

    def get_camera_by_id(self, camera_id: str) -> Dict:
        """
        GET /api/dotcom/camera.php?r=camera&a=fetch&id=<camera_id>

        Returns stream/metadata for a specific camera by its UUID.
        Returns the same structure as a playlist item.

        Args:
            camera_id: 32-char hex UUID from the camera object's "id" field

        Returns: dict with keys:
            data.playlist_items  - list with one camera item (same structure
                                   as playlist items from get_playlist())
        """
        return self._get("/api/dotcom/camera.php", {
            "r": "camera", "a": "fetch", "id": camera_id
        })

    def get_categories(self) -> Dict:
        """
        GET /api/dotcom/categories.php?r=categories&a=fetch

        Returns the list of all available camera categories with their
        enabled/disabled status.

        Returns: dict with keys:
            data.categories  - list of {item_name, item_name_full, status}

        Active categories include: animals, beaches, cities, election_day,
        featured, landmarks, lakes-rivers-oceans, nature, nye, nye_ts,
        smalltown, sports, trending, youtube
        """
        return self._get("/api/dotcom/categories.php", {
            "r": "categories", "a": "fetch"
        })

    def get_all_cameras(self) -> Dict:
        """
        GET /api/dotcom/categories_cams.php?r=categories_cams&a=fetch

        Returns a flat list of all cameras in the EarthCam network (~300 cameras).
        Does not include stream URLs - use get_camera_group() or get_camera_by_id()
        to get stream URLs for a specific camera.

        Returns: dict with keys:
            data.cam_count   - total count of cameras
            data.cam_items   - list of camera summary objects

        Each camera summary contains:
            id, title, city, state, state_full, country,
            description, cam_state, thumbnail, thumbnail_large,
            url (EarthCam page URL), category, latitude, longitude, item_type
        """
        return self._get("/api/dotcom/categories_cams.php", {
            "r": "categories_cams", "a": "fetch"
        })

    def get_timelapse(
        self,
        best: bool = False,
        timelapse_type: Optional[str] = None,
        related_id: Optional[str] = None
    ) -> Dict:
        """
        GET /api/dotcom/timelapse.php?r=timelapse&a=fetch[&best=1][&timelapse_type=general][&related_id=...]

        Returns daily timelapse videos (sunrise/sunset timelapses from EarthCam cameras).

        Args:
            best: If True, return the best-of timelapse selection
            timelapse_type: Filter by type ("sun", "general")
            related_id: Get timelapses related to a specific camera ID

        Returns: dict with keys:
            data.playlist_items  - list of timelapse items (up to 100)

        Each timelapse item contains:
            title, title-short, timelapse-date, timelapse_type, sun_type,
            stream (HLS m3u8 URL), thumbnail, camera_id, timestamp,
            city, country, timezone, description
        """
        params = {"r": "timelapse", "a": "fetch"}
        if best:
            params["best"] = "1"
        if timelapse_type:
            params["timelapse_type"] = timelapse_type
        if related_id:
            params["related_id"] = related_id
        return self._get("/api/dotcom/timelapse.php", params)

    def get_archives(self, dnet: str, myec: bool = False) -> Dict:
        """
        GET /api/dotcom/get_archives.php?netid=<dnet>[&type=myec]

        Returns the list of available recorded video clips (hourly archives)
        for a camera. Use the camera's "dnet" field as the netid.

        Note: Returns -1 (integer) if no archives exist or if the wrong ID is used.
        Must use the camera's "dnet" field, NOT "id" or "inet".

        Args:
            dnet: Camera's "dnet" value (32-char hex), NOT the "id" field
            myec: If True, use the MyEarthCam archive endpoint variant

        Returns: dict with keys:
            startdate   - Start of archive availability (YYYYMMDDHHMMSS)
            enddate     - End of archive availability ("0" = ongoing)
            curdate     - Current date (YYYYMMDDHHMMSS)
            clips       - list of hourly clip objects

        Each clip contains:
            time         - Hour (HHMMSS format, e.g. "130000" = 1pm)
            clip         - RTMP URL
            clip_html5   - HLS m3u8 URL
            thumbnail    - Relative thumbnail path (prepend archive base URL)
            thumbnail_large
            duration     - Duration in seconds (-1 if not yet available)
            date_stamp   - Full datetime stamp
        """
        params = {"netid": dnet}
        if myec:
            params["type"] = "myec"
        return self._get("/api/dotcom/get_archives.php", params)

    def get_new_cameras(self, filter_type: Optional[str] = None) -> Dict:
        """
        GET /api/dotcom/newcams.php?r=newcams&a=fetch[&filter=<type>]

        Returns recently added cameras.

        Args:
            filter_type: Optional filter string

        Returns: dict with data.cam_items list
        """
        params = {"r": "newcams", "a": "fetch"}
        if filter_type:
            params["filter"] = filter_type
        return self._get("/api/dotcom/newcams.php", params)

    def get_youtube_streams(self) -> Dict:
        """
        GET /api/dotcom/youtube.php?r=youtube&a=fetch

        Returns EarthCam's YouTube live stream listings.

        Returns: dict with data containing YouTube stream items
        """
        return self._get("/api/dotcom/youtube.php", {"r": "youtube", "a": "fetch"})

    # -------------------------------------------------------------------------
    # Network / Location Search Endpoints
    # -------------------------------------------------------------------------

    def search_by_location(
        self,
        country: str,
        state: Optional[str] = None
    ) -> Dict:
        """
        GET /api/dotcom/network_search.php?r=ecn&a=fetch&country=<country>[&state=<state>]

        Browse cameras by country and optionally by US state.
        This is the main endpoint powering the /network/ page.

        Args:
            country: Country name (e.g. "United States", "Ireland", "France")
                     Use "US" for US states. Use "featured" to get the featured playlist.
            state:   Two-letter US state code (e.g. "NY", "CA", "FL").
                     Only used when country is "United States" or "US".

        Returns: dict with keys:
            data.cam_count   - number of cameras found
            data.cam_items   - list of camera summary objects

        Each camera summary contains:
            id, title, city, state, state_full, country, description,
            cam_state, thumbnail, thumbnail_large, url, newcams_pinned,
            category, latitude, longitude, item_type
        """
        params = {"r": "ecn", "a": "fetch", "country": country}
        if state:
            params["state"] = state
        return self._get("/api/dotcom/network_search.php", params)

    # -------------------------------------------------------------------------
    # Search / Autocomplete Endpoints
    # -------------------------------------------------------------------------

    def autocomplete_search(self, term: str) -> Dict:
        """
        GET /api/dotcom-search/html/autocomplete_updated?term=<query>

        Returns autocomplete suggestions for camera search queries.
        Used by the search bar on the EarthCam website.

        Args:
            term: Search query string (partial or full camera name/location)

        Returns: dict with key "results" containing list of suggestion strings
                 Example: {"results": ["EarthCam: Times Square 4K", ...]}
        """
        return self._get("/api/dotcom-search/html/autocomplete_updated", {"term": term})

    # -------------------------------------------------------------------------
    # Map Search Endpoints
    # -------------------------------------------------------------------------

    def get_network_map_cameras(self) -> List[Dict]:
        """
        GET /api/mapsearch/get_locations_network.php?r=ecn&a=fetch

        Returns all EarthCam network cameras with their geographic coordinates
        for map display. Contains ~274 cameras.

        Returns: list with one group dict containing key "places" - a list of camera objects.
                 Each place has: name, url, posn ([lat, lng]), place_type, id,
                 icon (thumbnail URL), image, thumbnail

        Usage: data = client.get_network_map_cameras(); cameras = data[0]['places']
        """
        resp = self.session.get(
            self.BASE_URL + "/api/mapsearch/get_locations_network.php",
            params={"r": "ecn", "a": "fetch"},
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def get_cameras_in_bounds(
        self,
        nw_lat: float, nw_lng: float,
        ne_lat: float, ne_lng: float,
        se_lat: float, se_lng: float,
        sw_lat: float, sw_lng: float,
        zoom: int = 5
    ) -> List[Dict]:
        """
        GET /api/mapsearch/get_locations?nwx=<nw_lat>&nwy=<nw_lng>&...&zoom=<zoom>

        Returns all cameras (EarthCam + third-party) within a geographic bounding box.
        Returns significantly more cameras than the network-only endpoint (~1000+).

        Args:
            nw_lat/nw_lng: Northwest corner coordinates
            ne_lat/ne_lng: Northeast corner coordinates
            se_lat/se_lng: Southeast corner coordinates
            sw_lat/sw_lng: Southwest corner coordinates
            zoom: Map zoom level (2-18)

        Returns: list with one group dict containing key "places"
                 Each place has: name, icon, thumbnail, posn, place_type,
                 location, city, state, country, url

        Convenience bounds:
            USA:   nw=(49,-125), ne=(49,-65), se=(25,-65), sw=(25,-125)
            World: nw=(77,-180), ne=(77,157), se=(-40,157), sw=(-40,-180)
        """
        params = {
            "nwx": nw_lat, "nwy": nw_lng,
            "nex": ne_lat, "ney": ne_lng,
            "sex": se_lat, "sey": se_lng,
            "swx": sw_lat, "swy": sw_lng,
            "zoom": zoom
        }
        resp = self.session.get(
            self.BASE_URL + "/api/mapsearch/get_locations",
            params=params,
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # Weather Endpoint
    # -------------------------------------------------------------------------

    def get_weather(self, metar: str, icon_style: str = "simple") -> Dict:
        """
        GET /api/weather/weather.php?icons=<style>&metar=<code>

        Returns current weather conditions for a METAR weather station.
        Most EarthCam cameras include a "metar" field with the nearest station code.

        Args:
            metar: METAR station code (e.g. "KJFK" for JFK Airport, NYC;
                   "KIAG" for Niagara Falls; "EIDW" for Dublin)
            icon_style: Icon style - "simple", "cc7", "cc8_bg", or "cc8_nobg"

        Returns: dict with weather data including:
            data.Temperature (Fahrenheit, Celsius)
            data.Wind (Direction, Speed)
            data.Pressure (Millibar, InchesOfMercury)
            data.RelativeHumidity
            data.CurrentConditions (text description)
            data.ConditionType
            data.Icon (URLs for weather icons in different styles)
            data.SunInfo (Sunrise, Sunset times)
            data.MoonInfo (Phase, Illumination, Moonrise, Moonset)
            data.datetime (local and UTC timestamps)
            data.raw (raw METAR string)
        """
        return self._get("/api/weather/weather.php", {
            "icons": icon_style,
            "metar": metar
        })

    # -------------------------------------------------------------------------
    # Thumbnail / Image Helpers
    # -------------------------------------------------------------------------

    def get_thumbnail_url(self, thumbnail_hash: str, size: str = "256x144") -> str:
        """
        Build the URL for a camera thumbnail image.

        Thumbnails are static JPEGs hosted on static.earthcam.com.
        The hash comes from the camera object's id field (but NOT the same hex —
        it's a separate hash). Use the thumbnail URLs directly from API responses.

        Args:
            thumbnail_hash: Hash portion of the thumbnail filename
                           (e.g. "fc0bd5c43dfbd1a702db4b38abe484ff")
            size: Thumbnail size - one of "128x72", "256x144", "512x288", "1816x1024"

        Returns: Full thumbnail URL string
        """
        if size not in self.THUMBNAIL_SIZES:
            raise ValueError(f"Invalid size. Must be one of: {self.THUMBNAIL_SIZES}")
        return f"{self.STATIC_BASE}/camshots/{size}/{thumbnail_hash}.jpg"

    def get_stream_url(self, camera_data: Dict) -> Optional[str]:
        """
        Extract the HLS stream URL from camera data returned by get_camera_group()
        or get_camera_by_id().

        The stream URL contains a short-lived signed token (?t=...&td=YYYYMMDDHHMM).
        Tokens appear to expire around 1 hour after issuance.

        Args:
            camera_data: Camera object dict from API response

        Returns: HLS m3u8 URL string, or None if camera is offline/unavailable
        """
        # Primary stream URL (already includes token)
        stream = camera_data.get("stream")
        if stream:
            return stream.replace("\\/", "/")

        # Construct from domain + path
        domain = camera_data.get("html5_streamingdomain", "")
        path = camera_data.get("html5_streampath", "")
        if domain and path:
            return domain.replace("\\/", "/") + path.replace("\\/", "/")

        return None

    def get_archive_hls_url(self, camera_data: Dict) -> Optional[str]:
        """
        Build the 24-hour timelapse archive URL for a camera.

        Args:
            camera_data: Camera object dict from API response

        Returns: HLS m3u8 URL for the 24hr timelapse, or None
        """
        domain = camera_data.get("archivedomain_html5", "")
        path = camera_data.get("archivepath_html5", "")
        if domain and path:
            return domain.replace("\\/", "/") + path.replace("\\/", "/")
        return None

    # -------------------------------------------------------------------------
    # High-Level Convenience Methods
    # -------------------------------------------------------------------------

    def find_cameras(self, query: str) -> List[str]:
        """
        Search for cameras by name or location using autocomplete.

        Args:
            query: Search string

        Returns: List of camera title strings matching the query
        """
        result = self.autocomplete_search(query)
        return result.get("results", [])

    def get_cameras_for_state(self, state_code: str) -> List[Dict]:
        """
        Get all cameras in a US state.

        Args:
            state_code: Two-letter state code (e.g. "NY", "FL", "CA")

        Returns: List of camera summary dicts
        """
        result = self.search_by_location("United States", state_code)
        return result.get("data", {}).get("cam_items", [])

    def get_cameras_for_country(self, country: str) -> List[Dict]:
        """
        Get all cameras in a country (non-US).

        Args:
            country: Country name (e.g. "Ireland", "France", "Australia")

        Returns: List of camera summary dicts
        """
        result = self.search_by_location(country)
        return result.get("data", {}).get("cam_items", [])

    def get_trending_cameras(self) -> List[Dict]:
        """
        Get the current trending cameras.

        Returns: List of 4 trending camera items with stream URLs
        """
        result = self.get_playlist()
        return result.get("data", {}).get("playlist_trending", {}).get("playlist_items", [])

    def get_featured_cameras(self) -> List[Dict]:
        """
        Get the current featured cameras.

        Returns: List of ~8 featured camera items with stream URLs
        """
        result = self.get_playlist()
        return result.get("data", {}).get("playlist_featured", {}).get("playlist_items", [])

    def get_live_stream(self, group_id: str, cam_name: Optional[str] = None) -> Optional[str]:
        """
        Get the live HLS stream URL for a camera.

        Args:
            group_id: Camera group ID (e.g. "timessquare", "niagarafalls")
            cam_name: Optional specific camera within group (uses first camera if None)

        Returns: HLS m3u8 stream URL with signed token, or None

        Example:
            url = client.get_live_stream("timessquare", "tsrobo1")
            # Returns: https://videos-3.earthcam.com/fecnetwork/hdtimes10.flv/playlist.m3u8?t=...
        """
        result = self.get_camera_group(group_id)
        cams = result.get("data", {}).get("cam", {})

        if cam_name and cam_name in cams:
            return self.get_stream_url(cams[cam_name])
        elif cams:
            first_cam = next(iter(cams.values()))
            return self.get_stream_url(first_cam)

        return None

    def get_camera_info(self, group_id: str, cam_name: Optional[str] = None) -> Optional[Dict]:
        """
        Get full metadata for a camera including stream URL, location, and settings.

        Args:
            group_id: Camera group ID
            cam_name: Optional specific camera name (uses first if None)

        Returns: Camera metadata dict or None
        """
        result = self.get_camera_group(group_id)
        cams = result.get("data", {}).get("cam", {})

        if cam_name and cam_name in cams:
            return cams[cam_name]
        elif cams:
            return next(iter(cams.values()))

        return None


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    client = EarthCamClient()

    print("=" * 60)
    print("EarthCam API Client - Example Usage")
    print("=" * 60)

    # 1. Get trending cameras
    print("\n[1] Trending Cameras:")
    trending = client.get_trending_cameras()
    for cam in trending:
        print(f"  - {cam['title']} ({cam['city']}, {cam.get('country', cam.get('state', ''))})")
        print(f"    Stream: {cam.get('stream', 'N/A')[:80]}...")

    # 2. Search cameras
    print("\n[2] Search 'niagara':")
    results = client.find_cameras("niagara")
    for r in results:
        print(f"  - {r}")

    # 3. Get live stream for Times Square
    print("\n[3] Times Square live stream:")
    stream_url = client.get_live_stream("timessquare", "tsrobo1")
    print(f"  {stream_url}")

    # 4. Get camera info
    print("\n[4] Times Square camera info:")
    cam_info = client.get_camera_info("timessquare", "tsrobo1")
    if cam_info:
        print(f"  Title: {cam_info.get('title')}")
        print(f"  Location: {cam_info.get('city')}, {cam_info.get('state')}, {cam_info.get('country')}")
        print(f"  Lat/Long: {cam_info.get('map_lat')}, {cam_info.get('map_long')}")
        print(f"  Timezone: {cam_info.get('timezone')}")
        print(f"  METAR: {cam_info.get('metar')}")
        print(f"  Stream views: {cam_info.get('streamviews')}")
        print(f"  Likes: {cam_info.get('likes')}")

    # 5. Get weather for a camera location
    print("\n[5] Weather at JFK (KJFK):")
    weather = client.get_weather("KJFK")
    w = weather.get("data", {})
    print(f"  Temperature: {w.get('Temperature', {}).get('Fahrenheit')}°F / {w.get('Temperature', {}).get('Celsius')}°C")
    print(f"  Conditions: {w.get('CurrentConditions')}")
    wind = w.get('Wind', {})
    print(f"  Wind: {wind.get('Speed', {}).get('MilesPerHour')} mph {wind.get('Direction', {}).get('Direction')}")

    # 6. Get cameras in New York state
    print("\n[6] Cameras in New York state:")
    ny_cams = client.get_cameras_for_state("NY")
    print(f"  Found {len(ny_cams)} cameras")
    for cam in ny_cams[:5]:
        print(f"  - {cam['title']} ({cam['city']})")

    # 7. Get archives for Times Square
    print("\n[7] Archive clips for Times Square (tsrobo1):")
    cam_info = client.get_camera_info("timessquare", "tsrobo1")
    if cam_info and cam_info.get("dnet"):
        archives = client.get_archives(cam_info["dnet"])
        if isinstance(archives, dict):
            clips = archives.get("clips", [])
            print(f"  Archive date range: {archives.get('startdate')} - current")
            print(f"  Available clips: {len(clips)}")
            for clip in clips[:3]:
                print(f"    {clip['date_stamp']}: {clip['clip_html5'][:80]}...")

    # 8. Get all cameras (network overview)
    print("\n[8] All cameras overview:")
    all_cams = client.get_all_cameras()
    count = all_cams.get("data", {}).get("cam_count", 0)
    print(f"  Total cameras in EarthCam network: {count}")

    # 9. Get daily timelapse videos
    print("\n[9] Recent timelapse videos:")
    timelapses = client.get_timelapse()
    tl_items = timelapses.get("data", {}).get("playlist_items", [])
    print(f"  Found {len(tl_items)} timelapse videos")
    for tl in tl_items[:3]:
        print(f"  - {tl.get('title-short')} ({tl.get('timelapse-date')})")
        print(f"    Type: {tl.get('sun_type', tl.get('timelapse_type'))}")

    print("\n" + "=" * 60)
    print("Done!")
