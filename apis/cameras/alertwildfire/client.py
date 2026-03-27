"""
AlertWildfire / AlertCalifornia Camera System API Client
=========================================================

Reverse-engineered from:
  - https://www.alertwildfire.org       (ALERTWildfire — UNR operated, 128 cameras)
  - https://cameras.alertcalifornia.org (ALERTCalifornia — UCSD operated, 2072+ cameras)

Both systems use Axis PTZ cameras but have completely different backend infrastructure.

==========================================================================
ENDPOINT REFERENCE (all verified March 2026)
==========================================================================

=== ALERTWildfire (alertwildfire.org) ===

Infrastructure:
  - Nuxt 3 SPA hosted on alertwildfire.org
  - Camera data on public S3 bucket: s3-us-west-2.amazonaws.com/awf-data-public-prod
  - Camera images served from S3 (UUID-keyed), gated by Referer header
  - Timelapse streamed from tl.alertwildfire.org
  - PTZ control via {hostname}.prx.alertwildfire.org (requires Bearer token)
  - Auth API at api.alertwildfire.org (JWT Bearer tokens)
  - Chief admin panel at chief.alertwildfire.org

1. Camera List (GeoJSON FeatureCollection, 128 cameras):
   GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/all-cameras.json
   Headers: Referer: https://www.alertwildfire.org/
   Response fields (properties):
     id           : UUID, e.g. "1ac1033c-c9d8-4eed-a23b-bb6b1ff80303"
     camera_slug  : e.g. "nv-castlepeak-1"
     hostname     : Axis hostname, e.g. "axis-castlepeak"
     name         : "Castlepeak 1"
     state        : "NV", "CA", "WA", "ID", "AZ"
     county       : county name
     elevation    : meters ASL
     aboveGroundHeight : meters above ground
     az_current   : current azimuth (0=north, 90=east)
     tilt_current : current tilt in degrees
     zoom_current : current zoom level
     is_patrol_mode / is_currently_patrolling : bool
     sponsor      : "NVEnergy", "calfire", etc.
     attribution  : "ALERTWildfire"
     fireProtectionDistrict : district code
     isp          : ISP name
     last_update_at : ISO 8601 string
     last_movement_at : ISO 8601 string or null
     fov          : field of view in degrees
     fov_center / fov_lft / fov_rt : [lon, lat] arrays
     ptz          : null or PTZ capabilities object
     ProdNbr      : Axis model, e.g. "Q6075-E"
     publicNote   : public note string
   geometry.coordinates: [longitude, latitude, elevation_m]

2. Current Full Image (requires Referer header):
   GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/{camera_uuid}/latest_full.jpg
   Optional cache buster: ?x-request-time={unix_ms}
   Returns: JPEG ~200-400 KB

3. Current Thumbnail (requires Referer header):
   GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/{camera_uuid}/latest_thumb.jpg
   Optional cache buster: ?x-request-time={unix_ms}
   Returns: JPEG ~15-25 KB

4. Timelapse (streaming MJPEG, requires recently-active camera):
   GET https://tl.alertwildfire.org/timelapse?source={camera_uuid}&preset={duration}&nocache={unix_ms}
   preset options: "15m", "1h", "3h", "6h", "12h"
   Headers: Referer: https://www.alertwildfire.org/
   Response: multipart/x-mixed-replace; boundary=frame
   Each part: --frame\r\nContent-Type: image/jpeg\r\nContent-Length: N\r\n\r\n[JPEG bytes]
   Returns 204 (no content) if camera has no timelapse data (offline/stale)
   Note: source parameter uses UUID, NOT camera slug or hostname

5. Fire / Weather Metadata (public S3, no auth required):
   IRWIN fire starts:
     GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/irwin-starts.geojson
   IRWIN fire perimeters:
     GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/irwin-perimeters.geojson
   NOAA red flag areas:
     GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/noaa-red-flag-areas.geojson
   Lightning strikes:
     GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/lightning-data.geojson
   All require: Referer: https://www.alertwildfire.org/

6. Camera Control / Axis PTZ Proxy (auth required):
   Base URL: https://{hostname}.prx.alertwildfire.org/
   Example:   https://axis-castlepeak.prx.alertwildfire.org/axis-cgi/jpg/image.cgi
   Auth: Bearer JWT token from login (see below)
   Returns 401 without token; "Token expired" message on bad token
   Note: proxy subdomain uses HOSTNAME (e.g. "axis-castlepeak"), NOT UUID

7. Auth API (credentials required):
   Login:  POST https://api.alertwildfire.org/auth/login
           Body: {"email": "...", "password": "..."}  (password min 8 chars)
           Returns: {"accessToken": "...", ...}
   Profile: GET https://api.alertwildfire.org/user/me
            Header: Authorization: Bearer {accessToken}
   Token type: Bearer JWT, maxAge: 86400 seconds
   Login page: https://chief.alertwildfire.org/login/

=== ALERTCalifornia (cameras.alertcalifornia.org) ===

Infrastructure:
  - Custom web app (not Nuxt) with Leaflet.js map
  - Data at cameras.alertcalifornia.org/public-camera-data/ (Apache-served)
  - Camera IDs use hostname-style format ("Axis-BoxSprings2")
  - No authentication required for any public endpoint
  - Fire perimeters from ArcGIS: services3.arcgis.com/T4QMspbfLg3qTGWY/...

1. Camera List (GeoJSON FeatureCollection, 2072+ cameras):
   GET https://cameras.alertcalifornia.org/public-camera-data/all_cameras-v3.json?rqts={unix_sec}
   Response fields (properties):
     id           : e.g. "Axis-AlabamaHills1"
     name         : "Alabama Hills 1"
     last_frame_ts : Unix timestamp of last frame
     az_current   : azimuth degrees
     tilt_current : tilt degrees
     zoom_current : zoom level
     is_patrol_mode / is_currently_patrolling : 0 or 1
     state        : "CA" (all cameras)
     county       : county name (lowercase)
     sponsor      : e.g. "calfire"
     isp          : ISP name
     region       : region code e.g. "BDU"
     fov / fov_center / fov_lft / fov_rt : FOV data
     ProdNbr      : Axis model
   geometry.coordinates: [lon, lat, elev] — may be null for private cameras

2. Current Thumbnail:
   GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/latest-thumb.jpg?rqts={unix_sec}
   Returns: JPEG ~7 KB

3. Current Full Image:
   GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/latest-frame.jpg?rqts={unix_sec}
   Returns: JPEG ~300-400 KB
   Note: internally "full" maps to "frame" in the URL (not "full")

4. Timelapse (JSON spec + individual JPEG frames):
   Pools (capture intervals):
     "10sec" : 10-second intervals (for short durations)
     "1min"  : 1-minute intervals (for longer durations)

   Available specs (TIMELAPSE_TABLE from source):
     pool="10sec":  5-min.json, 15-min.json, 30-min.json
     pool="1min":   1-hour.json, 3-hour.json, 6-hour.json, 12-hour.json

   Timelapse spec (frame list):
   GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/{pool}/{spec_file}
   Returns JSON: {"last_updated": float, "frames": ["1774630882.000000000.jpg", ...]}
   Frame filenames are Unix nanosecond timestamps as strings

   Individual frame:
   GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/{pool}/{jpg_name}
   Returns: JPEG image

5. Panoramic Grid / 360° View:
   Spec:
   GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/panogrid/panogrid.json?rqts={ts}
   Returns: {"last_updated": float, "camera": str, "timestamps": [float, ...], "poses": [[az, tilt, zoom], ...]}
   timestamps/poses have up to 12 entries (null for unavailable positions)

   Individual pano tile:
   GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/panogrid/latest-pg-{idx}.jpg?ts={ts}
   idx: 0-based grid index

6. Data Source Config:
   GET https://cameras.alertcalifornia.org/data_source.json
   Returns: {"source": "https://cameras.alertcalifornia.org"}
   Used by client to allow data URL override

7. ArcGIS Year-to-Date Fire Perimeters:
   GET https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0
   Standard ArcGIS REST API, supports ?f=geojson for GeoJSON output

==========================================================================
IMPORTANT NOTES
==========================================================================
- AWF image S3 paths require Referer header (HTTP 403 without it)
- AWF timelapse returns HTTP 204 if camera has no recent data
- AWF timelapse source param MUST be the UUID (not slug or hostname)
- AWF proxy subdomain uses HOSTNAME (e.g. axis-castlepeak), NOT UUID
- AC camera IDs are case-sensitive (e.g. "Axis-BoxSprings2")
- AC cameras with null coordinates are private/hidden cameras
- Both systems reload camera metadata every 30 seconds in the browser
"""

import requests
import json
import time
from datetime import datetime, timezone
from typing import Optional, Generator, List
import io


# ============================================================
# Constants
# ============================================================

# ALERTWildfire (alertwildfire.org) — UNR operated
AWF_S3_BASE = "https://s3-us-west-2.amazonaws.com/awf-data-public-prod"
AWF_CAMERA_LIST_URL = f"{AWF_S3_BASE}/all-cameras.json"
AWF_TIMELAPSE_BASE = "https://tl.alertwildfire.org"
AWF_API_BASE = "https://api.alertwildfire.org"
AWF_CHIEF_BASE = "https://chief.alertwildfire.org"

AWF_TIMELAPSE_PRESETS = ["15m", "1h", "3h", "6h", "12h"]

# S3 GeoJSON metadata files (require Referer header)
AWF_IRWIN_STARTS_URL = f"{AWF_S3_BASE}/v3-metadata/irwin-starts.geojson"
AWF_IRWIN_PERIMETERS_URL = f"{AWF_S3_BASE}/v3-metadata/irwin-perimeters.geojson"
AWF_NOAA_RED_FLAG_URL = f"{AWF_S3_BASE}/v3-metadata/noaa-red-flag-areas.geojson"
AWF_LIGHTNING_URL = f"{AWF_S3_BASE}/v3-metadata/lightning-data.geojson"

# ALERTCalifornia (cameras.alertcalifornia.org) — UCSD operated
AC_BASE_URL = "https://cameras.alertcalifornia.org"
AC_DATA_URL = f"{AC_BASE_URL}/public-camera-data"

# Timelapse pool mapping (from TIMELAPSE_TABLE in alertcalifornia.js)
AC_TIMELAPSE_TABLE = [
    {"tag": "5 mins",   "spec": "5-min.json",   "pool": "10sec"},
    {"tag": "15 mins",  "spec": "15-min.json",  "pool": "10sec"},
    {"tag": "30 mins",  "spec": "30-min.json",  "pool": "10sec"},
    {"tag": "1 hour",   "spec": "1-hour.json",  "pool": "1min"},
    {"tag": "3 hours",  "spec": "3-hour.json",  "pool": "1min"},
    {"tag": "6 hours",  "spec": "6-hour.json",  "pool": "1min"},
    {"tag": "12 hours", "spec": "12-hour.json", "pool": "1min"},
]
AC_TIMELAPSE_DURATIONS = [e["tag"] for e in AC_TIMELAPSE_TABLE]


# ============================================================
# ALERTWildfire Client (alertwildfire.org)
# ============================================================

class AlertWildfireClient:
    """
    Client for the ALERTWildfire camera network (alertwildfire.org).

    Operated by University of Nevada, Reno.
    128 cameras across Nevada, California, Washington, Idaho, Arizona (as of March 2026).

    No credentials required for public data endpoints.
    All S3 image/data requests require Referer header (set automatically).

    Camera identifiers:
      - id (UUID):      "1ac1033c-c9d8-4eed-a23b-bb6b1ff80303"  — used for images & timelapse
      - camera_slug:    "nv-castlepeak-1"                       — human-readable URL fragment
      - hostname:       "axis-castlepeak"                       — used for PTZ proxy subdomain
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.alertwildfire.org/",
        })

    # ----------------------------------------------------------
    # Camera Inventory
    # ----------------------------------------------------------

    def get_cameras(self) -> dict:
        """
        Fetch the full AWF camera list as a GeoJSON FeatureCollection.

        Returns:
            dict: GeoJSON FeatureCollection.
            Each feature.properties contains: id, camera_slug, hostname, name,
            state, county, elevation, az_current, tilt_current, zoom_current,
            is_patrol_mode, sponsor, last_update_at, fov, fov_center, fov_lft,
            fov_rt, ptz, ProdNbr, attribution, fireProtectionDistrict, isp.
            geometry.coordinates: [longitude, latitude, elevation_meters]
        """
        ts = int(time.time() * 1000)
        url = f"{AWF_CAMERA_LIST_URL}?_={ts}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_cameras_by_state(self, state: str, cameras: Optional[dict] = None) -> List[dict]:
        """
        Get all cameras in a given state.

        Args:
            state: State abbreviation, e.g. "NV", "CA", "WA", "ID", "AZ"
            cameras: Optional pre-fetched camera list

        Returns:
            List of GeoJSON Feature dicts
        """
        if cameras is None:
            cameras = self.get_cameras()
        return [
            f for f in cameras.get("features", [])
            if f["properties"].get("state", "").upper() == state.upper()
        ]

    def get_camera_by_slug(self, camera_slug: str, cameras: Optional[dict] = None) -> Optional[dict]:
        """
        Find a camera by its slug identifier (e.g. "nv-castlepeak-1").

        Args:
            camera_slug: The camera_slug field value
            cameras: Optional pre-fetched camera list

        Returns:
            GeoJSON Feature dict or None
        """
        if cameras is None:
            cameras = self.get_cameras()
        for feature in cameras.get("features", []):
            if feature["properties"].get("camera_slug") == camera_slug:
                return feature
        return None

    def get_camera_by_id(self, camera_id: str, cameras: Optional[dict] = None) -> Optional[dict]:
        """
        Find a camera by its UUID.

        Args:
            camera_id: UUID like "1ac1033c-c9d8-4eed-a23b-bb6b1ff80303"
            cameras: Optional pre-fetched camera list

        Returns:
            GeoJSON Feature dict or None
        """
        if cameras is None:
            cameras = self.get_cameras()
        for feature in cameras.get("features", []):
            if feature["properties"].get("id") == camera_id:
                return feature
        return None

    # ----------------------------------------------------------
    # Current Images
    # ----------------------------------------------------------

    def get_current_image(self, camera_id: str, full_size: bool = True) -> bytes:
        """
        Fetch the current JPEG image for a camera from S3.

        Args:
            camera_id: Camera UUID (from properties.id)
            full_size: True = full resolution (~200-400 KB).
                       False = thumbnail (~15-25 KB).

        Returns:
            JPEG image bytes

        Note:
            Requires Referer header (handled automatically).
            S3 bucket returns HTTP 403 without proper Referer.
        """
        ts = int(time.time() * 1000)
        filename = "latest_full.jpg" if full_size else "latest_thumb.jpg"
        url = f"{AWF_S3_BASE}/{camera_id}/{filename}?x-request-time={ts}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def get_current_image_url(self, camera_id: str, full_size: bool = True) -> str:
        """
        Build the URL for the current camera image.

        Args:
            camera_id: Camera UUID
            full_size: True for full resolution, False for thumbnail

        Returns:
            Direct URL string (includes cache-busting timestamp)
        """
        ts = int(time.time() * 1000)
        filename = "latest_full.jpg" if full_size else "latest_thumb.jpg"
        return f"{AWF_S3_BASE}/{camera_id}/{filename}?x-request-time={ts}"

    # ----------------------------------------------------------
    # Timelapse (Streaming MJPEG)
    # ----------------------------------------------------------

    def get_timelapse_frames(
        self,
        camera_id: str,
        preset: str = "1h",
        max_frames: Optional[int] = None,
        timeout: float = 120.0,
    ) -> Generator[bytes, None, None]:
        """
        Stream timelapse JPEG frames from tl.alertwildfire.org.

        The server delivers multipart/x-mixed-replace with boundary "frame".
        Each part contains a JPEG image.

        Args:
            camera_id: Camera UUID (NOT slug or hostname — must be UUID)
            preset: Duration preset — one of "15m", "1h", "3h", "6h", "12h"
            max_frames: Stop after this many frames (None = stream until done)
            timeout: Total request timeout in seconds

        Yields:
            bytes: Raw JPEG bytes for each frame

        Raises:
            ValueError: If preset is invalid or camera has no timelapse data (204)
            requests.HTTPError: On non-2xx/non-204 HTTP errors

        Example:
            for i, frame in enumerate(client.get_timelapse_frames(cam_id, "15m")):
                with open(f"frame_{i:04d}.jpg", "wb") as f:
                    f.write(frame)
        """
        if preset not in AWF_TIMELAPSE_PRESETS:
            raise ValueError(f"preset must be one of {AWF_TIMELAPSE_PRESETS}")

        ts = int(time.time() * 1000)
        url = f"{AWF_TIMELAPSE_BASE}/timelapse?source={camera_id}&preset={preset}&nocache={ts}"

        resp = self.session.get(url, stream=True, timeout=timeout)

        if resp.status_code == 204:
            raise ValueError(
                f"No timelapse data for camera {camera_id} (camera offline or no recent frames). "
                f"Check last_update_at in camera metadata."
            )

        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "multipart" not in content_type:
            raise ValueError(f"Unexpected Content-Type: {content_type}")

        buffer = b""
        frame_count = 0
        boundary = b"--frame\r\n"

        for chunk in resp.iter_content(chunk_size=65536):
            buffer += chunk

            while True:
                start = buffer.find(boundary)
                if start == -1:
                    break

                next_start = buffer.find(boundary, start + len(boundary))
                if next_start == -1:
                    break

                frame_data = buffer[start + len(boundary):next_start]
                header_end = frame_data.find(b"\r\n\r\n")
                if header_end >= 0:
                    jpeg_data = frame_data[header_end + 4:]
                    if jpeg_data[:2] == b'\xff\xd8':  # Valid JPEG SOI marker
                        yield jpeg_data
                        frame_count += 1
                        if max_frames is not None and frame_count >= max_frames:
                            return

                buffer = buffer[next_start:]

    def download_timelapse(
        self,
        camera_id: str,
        preset: str = "1h",
        output_dir: Optional[str] = None,
    ) -> List[bytes]:
        """
        Download all timelapse frames to memory and optionally to disk.

        Args:
            camera_id: Camera UUID
            preset: Duration preset ("15m", "1h", "3h", "6h", "12h")
            output_dir: If provided, saves frames as {output_dir}/frame_NNNN.jpg

        Returns:
            List of JPEG bytes objects
        """
        import os
        frames = []
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        for i, frame in enumerate(self.get_timelapse_frames(camera_id, preset)):
            frames.append(frame)
            if output_dir:
                path = os.path.join(output_dir, f"frame_{i:04d}.jpg")
                with open(path, "wb") as f:
                    f.write(frame)
        return frames

    # ----------------------------------------------------------
    # Fire & Weather Metadata (public GeoJSON)
    # ----------------------------------------------------------

    def get_irwin_fire_starts(self) -> dict:
        """
        Fetch IRWIN active fire start locations.

        Returns:
            GeoJSON FeatureCollection. Key fields: OBJECTID, IncidentSize,
            DispatchCenterID, DiscoveryAcres, FireCause, FireCauseSpecific,
            IncidentName, UniqueFireIdentifier, etc.
        """
        resp = self.session.get(AWF_IRWIN_STARTS_URL, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_irwin_fire_perimeters(self) -> dict:
        """
        Fetch IRWIN active fire perimeter polygons.

        Returns:
            GeoJSON FeatureCollection of fire perimeter polygons.
            Key fields: poly_IncidentName, poly_GISAcres, poly_IRWINID,
            poly_DateCurrent, poly_FeatureCategory.
        """
        resp = self.session.get(AWF_IRWIN_PERIMETERS_URL, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def get_noaa_red_flag_areas(self) -> dict:
        """
        Fetch NOAA Red Flag Warning areas.

        Returns:
            GeoJSON FeatureCollection of red flag polygons.
            Key fields: Event, Severity, Summary, Start, End_, Instruction,
            Description, HrsSinceUpdated.
        """
        resp = self.session.get(AWF_NOAA_RED_FLAG_URL, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_lightning_data(self) -> dict:
        """
        Fetch recent lightning strike data.

        Returns:
            GeoJSON FeatureCollection of lightning strike points.
            May be empty if no recent strikes.
        """
        resp = self.session.get(AWF_LIGHTNING_URL, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ----------------------------------------------------------
    # PTZ Camera Control Proxy (auth required)
    # ----------------------------------------------------------

    def get_proxy_url(self, hostname: str) -> str:
        """
        Get the PTZ camera proxy URL for a camera.

        The proxy subdomain uses the camera HOSTNAME (e.g. "axis-castlepeak"),
        NOT the UUID or camera_slug. Requires a valid Bearer token.

        Args:
            hostname: Camera hostname from properties.hostname
                      (e.g. "axis-castlepeak")

        Returns:
            Base URL string, e.g. "https://axis-castlepeak.prx.alertwildfire.org/"

        Note:
            To control PTZ:
            POST /axis-cgi/com/ptz.cgi?pan={degrees}&tilt={degrees}&zoom={level}
            GET  /axis-cgi/jpg/image.cgi  — capture JPEG snapshot
        """
        return f"https://{hostname}.prx.alertwildfire.org/"

    # ----------------------------------------------------------
    # Authentication (credentials required)
    # ----------------------------------------------------------

    def login(self, email: str, password: str) -> dict:
        """
        Authenticate with the AWF API to get a Bearer token.

        Required for PTZ camera control proxy access.
        Token is valid for 86400 seconds (24 hours).

        Args:
            email: Account email address
            password: Account password (minimum 8 characters)

        Returns:
            dict with at minimum "accessToken" key

        Raises:
            requests.HTTPError: On invalid credentials (400/401)
        """
        url = f"{AWF_API_BASE}/auth/login"
        resp = self.session.post(
            url,
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # Set token on session for subsequent authenticated requests
        if "accessToken" in data:
            self.session.headers["Authorization"] = f"Bearer {data['accessToken']}"
        return data

    def get_user_profile(self) -> dict:
        """
        Get the current authenticated user profile.

        Requires prior login() call or Authorization header to be set.

        Returns:
            dict with user profile data
        """
        resp = self.session.get(f"{AWF_API_BASE}/user/me", timeout=15)
        resp.raise_for_status()
        return resp.json()


# ============================================================
# AlertCalifornia Client (cameras.alertcalifornia.org)
# ============================================================

class AlertCaliforniaClient:
    """
    Client for the ALERTCalifornia camera network (cameras.alertcalifornia.org).

    Operated by UC San Diego.
    2072+ cameras, all in California (as of March 2026).

    No authentication required. All endpoints are fully public.

    Camera IDs use hostname-style format: "Axis-BoxSprings2", "Axis-AlabamaHills1"
    Some cameras have null geometry (private/hidden cameras).
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://cameras.alertcalifornia.org/",
        })

    # ----------------------------------------------------------
    # Camera Inventory
    # ----------------------------------------------------------

    def get_cameras(self) -> dict:
        """
        Fetch the full AlertCalifornia camera list as a GeoJSON FeatureCollection.

        Returns:
            dict: GeoJSON FeatureCollection with 2072+ cameras.
            Each feature.properties contains: id, name, last_frame_ts,
            az_current, tilt_current, zoom_current, is_patrol_mode,
            is_currently_patrolling, state, county, sponsor, isp, region,
            fov, fov_center, fov_lft, fov_rt, ProdNbr.
            geometry.coordinates: [lon, lat, elev] — may be [null, null, null]

        Note:
            Cameras with null coordinates are private and have no public images.
        """
        ts = int(time.time())
        url = f"{AC_DATA_URL}/all_cameras-v3.json?rqts={ts}"
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def get_camera_by_id(self, camera_id: str, cameras: Optional[dict] = None) -> Optional[dict]:
        """
        Find a camera by its ID (case-sensitive).

        Args:
            camera_id: e.g. "Axis-AlabamaHills1"
            cameras: Optional pre-fetched camera list

        Returns:
            GeoJSON Feature dict or None
        """
        if cameras is None:
            cameras = self.get_cameras()
        for feature in cameras.get("features", []):
            if feature["properties"].get("id") == camera_id:
                return feature
        return None

    def get_cameras_by_region(self, region: str, cameras: Optional[dict] = None) -> List[dict]:
        """
        Get cameras in a specific region.

        Region codes from the data include: BDU, NEU, SCU, CZU, MTU, etc.
        These correspond to CAL FIRE Unit regions.

        Args:
            region: Region code (case-insensitive)
            cameras: Optional pre-fetched camera list

        Returns:
            List of GeoJSON Feature dicts
        """
        if cameras is None:
            cameras = self.get_cameras()
        return [
            f for f in cameras.get("features", [])
            if f["properties"].get("region", "").upper() == region.upper()
        ]

    def get_cameras_by_sponsor(self, sponsor: str, cameras: Optional[dict] = None) -> List[dict]:
        """
        Get cameras sponsored by a specific organization.

        Common sponsors: "calfire", "nvenergy", "pge", "sce", "sdge"

        Args:
            sponsor: Sponsor name (case-insensitive)
            cameras: Optional pre-fetched camera list

        Returns:
            List of GeoJSON Feature dicts
        """
        if cameras is None:
            cameras = self.get_cameras()
        return [
            f for f in cameras.get("features", [])
            if f["properties"].get("sponsor", "").lower() == sponsor.lower()
        ]

    def get_active_cameras(
        self,
        cameras: Optional[dict] = None,
        max_age_seconds: int = 300,
    ) -> List[dict]:
        """
        Get cameras that have a recent frame.

        Args:
            cameras: Optional pre-fetched camera list
            max_age_seconds: Maximum age of last frame in seconds (default: 5 min)

        Returns:
            List of active GeoJSON Feature dicts
        """
        if cameras is None:
            cameras = self.get_cameras()
        now = time.time()
        return [
            f for f in cameras.get("features", [])
            if (f["properties"].get("last_frame_ts") or 0) > (now - max_age_seconds)
        ]

    def get_cameras_with_location(self, cameras: Optional[dict] = None) -> List[dict]:
        """
        Get cameras that have valid (non-null) geographic coordinates.

        Args:
            cameras: Optional pre-fetched camera list

        Returns:
            List of GeoJSON Feature dicts with valid geometry
        """
        if cameras is None:
            cameras = self.get_cameras()
        return [
            f for f in cameras.get("features", [])
            if f["geometry"]["coordinates"][0] is not None
        ]

    # ----------------------------------------------------------
    # Current Images
    # ----------------------------------------------------------

    def get_thumbnail(self, camera_id: str) -> bytes:
        """
        Fetch the current thumbnail image for a camera.

        Args:
            camera_id: Camera ID (e.g. "Axis-AlabamaHills1")

        Returns:
            JPEG bytes (~7 KB typically)
        """
        ts = int(time.time())
        url = f"{AC_DATA_URL}/{camera_id}/latest-thumb.jpg?rqts={ts}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def get_full_image(self, camera_id: str) -> bytes:
        """
        Fetch the current full-resolution image for a camera.

        The URL endpoint uses "frame" not "full" (internal naming convention).

        Args:
            camera_id: Camera ID (e.g. "Axis-AlabamaHills1")

        Returns:
            JPEG bytes (~300-400 KB typically)
        """
        ts = int(time.time())
        url = f"{AC_DATA_URL}/{camera_id}/latest-frame.jpg?rqts={ts}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def get_image_url(self, camera_id: str, image_type: str = "frame") -> str:
        """
        Build a direct URL for a camera image.

        Args:
            camera_id: Camera ID
            image_type: "frame" (full resolution) or "thumb" (thumbnail)

        Returns:
            URL string
        """
        ts = int(time.time())
        return f"{AC_DATA_URL}/{camera_id}/latest-{image_type}.jpg?rqts={ts}"

    # ----------------------------------------------------------
    # Timelapse (JSON spec + sequential JPEG frames)
    # ----------------------------------------------------------

    def get_timelapse_spec(self, camera_id: str, duration: str = "1 hour") -> dict:
        """
        Fetch the timelapse frame index (spec) for a camera.

        Args:
            camera_id: Camera ID
            duration: One of "5 mins", "15 mins", "30 mins", "1 hour",
                      "3 hours", "6 hours", "12 hours"

        Returns:
            dict with keys:
              "last_updated": float (Unix timestamp)
              "frames": list of jpg filenames (e.g. "1774630882.000000000.jpg")
            Frame filename is a Unix timestamp with nanosecond precision.

        Raises:
            ValueError: If duration is invalid
            requests.HTTPError: If spec doesn't exist for this camera (404)
        """
        entry = next((e for e in AC_TIMELAPSE_TABLE if e["tag"] == duration), None)
        if entry is None:
            raise ValueError(f"duration must be one of {AC_TIMELAPSE_DURATIONS}")

        url = f"{AC_DATA_URL}/{camera_id}/{entry['pool']}/{entry['spec']}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_timelapse_frame(self, camera_id: str, pool: str, jpg_name: str) -> bytes:
        """
        Download a single timelapse frame image.

        Args:
            camera_id: Camera ID
            pool: "10sec" or "1min"
            jpg_name: Filename from spec.frames[], e.g. "1774630882.000000000.jpg"

        Returns:
            JPEG bytes
        """
        url = f"{AC_DATA_URL}/{camera_id}/{pool}/{jpg_name}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    def get_timelapse_frames(
        self,
        camera_id: str,
        duration: str = "1 hour",
        max_frames: Optional[int] = None,
    ) -> Generator[tuple, None, None]:
        """
        Stream all timelapse frames for a camera, in chronological order.

        Downloads the spec first, then fetches each frame image.

        Args:
            camera_id: Camera ID
            duration: Duration string (see AC_TIMELAPSE_DURATIONS)
            max_frames: Stop after this many frames (None = all)

        Yields:
            Tuple of (unix_timestamp: float, jpeg_bytes: bytes)

        Example:
            for ts, frame in client.get_timelapse_frames("Axis-AlabamaHills1", "15 mins"):
                dt = datetime.fromtimestamp(ts)
                with open(f"frame_{dt.strftime('%H%M%S')}.jpg", "wb") as f:
                    f.write(frame)
        """
        entry = next((e for e in AC_TIMELAPSE_TABLE if e["tag"] == duration), None)
        if entry is None:
            raise ValueError(f"duration must be one of {AC_TIMELAPSE_DURATIONS}")

        spec = self.get_timelapse_spec(camera_id, duration)
        frames = spec.get("frames", [])
        if max_frames is not None:
            frames = frames[:max_frames]

        pool = entry["pool"]
        for jpg_name in frames:
            # Filename format: "1774630882.000000000.jpg" (Unix timestamp, nanoseconds)
            ts = float(jpg_name.replace(".jpg", ""))
            frame_bytes = self.get_timelapse_frame(camera_id, pool, jpg_name)
            yield ts, frame_bytes

    # ----------------------------------------------------------
    # Panoramic Grid (360° composite view)
    # ----------------------------------------------------------

    def get_panogrid_spec(self, camera_id: str) -> dict:
        """
        Fetch the panoramic grid specification for a camera.

        Some cameras support a 360° view composed of up to 12 overlapping
        images captured at different pan/tilt/zoom positions.

        Args:
            camera_id: Camera ID

        Returns:
            dict with keys:
              "last_updated": float
              "camera": camera ID string
              "timestamps": list of up to 12 Unix timestamps (null = unavailable)
              "poses": list of [azimuth, tilt, zoom] arrays (null = unavailable)

        Raises:
            requests.HTTPError: 404 if camera doesn't support panogrid
        """
        ts = int(time.time())
        url = f"{AC_DATA_URL}/{camera_id}/panogrid/panogrid.json?rqts={ts}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_panogrid_images(self, camera_id: str) -> List[tuple]:
        """
        Download all available panoramic grid tile images for a camera.

        Args:
            camera_id: Camera ID

        Returns:
            List of (idx: int, azimuth: float, tilt: float, zoom: float, jpeg_bytes: bytes)
            for each available (non-null) grid position.

        Raises:
            requests.HTTPError: If camera doesn't support panogrid (404)
        """
        spec = self.get_panogrid_spec(camera_id)
        timestamps = spec.get("timestamps", [])
        poses = spec.get("poses", [])
        results = []

        for idx, (ts, pose) in enumerate(zip(timestamps, poses)):
            if ts is None or pose is None:
                continue
            try:
                url = f"{AC_DATA_URL}/{camera_id}/panogrid/latest-pg-{idx}.jpg?ts={int(ts)}"
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                az, tilt, zoom = pose
                results.append((idx, az, tilt, zoom, resp.content))
            except requests.HTTPError:
                pass  # Skip unavailable tiles

        return results

    def get_panogrid_image(
        self, camera_id: str, idx: int, timestamp: Optional[float] = None
    ) -> bytes:
        """
        Download a single panoramic grid tile.

        Args:
            camera_id: Camera ID
            idx: Grid index (0-based, typically 0-11)
            timestamp: Unix timestamp from panogrid spec (for cache busting)

        Returns:
            JPEG bytes
        """
        ts_param = f"?ts={int(timestamp)}" if timestamp else ""
        url = f"{AC_DATA_URL}/{camera_id}/panogrid/latest-pg-{idx}.jpg{ts_param}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content


# ============================================================
# Convenience Functions
# ============================================================

def get_awf_cameras() -> dict:
    """Fetch all ALERTWildfire cameras as GeoJSON."""
    return AlertWildfireClient().get_cameras()


def get_ac_cameras() -> dict:
    """Fetch all AlertCalifornia cameras as GeoJSON."""
    return AlertCaliforniaClient().get_cameras()


def get_awf_current_image(camera_slug_or_id: str, full_size: bool = True) -> bytes:
    """
    Fetch the current image for an AWF camera by slug or UUID.

    Args:
        camera_slug_or_id: Either "nv-castlepeak-1" or a UUID string
        full_size: True for full res, False for thumbnail

    Returns:
        JPEG bytes
    """
    import re
    client = AlertWildfireClient()

    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                camera_slug_or_id, re.IGNORECASE):
        camera_id = camera_slug_or_id
    else:
        cameras = client.get_cameras()
        feature = client.get_camera_by_slug(camera_slug_or_id, cameras)
        if feature is None:
            raise ValueError(f"Camera not found: {camera_slug_or_id}")
        camera_id = feature["properties"]["id"]

    return client.get_current_image(camera_id, full_size)


def get_ac_current_image(camera_id: str, full_size: bool = True) -> bytes:
    """
    Fetch the current image for an AlertCalifornia camera.

    Args:
        camera_id: Camera ID like "Axis-AlabamaHills1"
        full_size: True for full res, False for thumbnail

    Returns:
        JPEG bytes
    """
    client = AlertCaliforniaClient()
    return client.get_full_image(camera_id) if full_size else client.get_thumbnail(camera_id)


# ============================================================
# Demo / Verification
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("ALERTWildfire + AlertCalifornia Client Demo")
    print("=" * 60)

    # ---- ALERTWildfire ----
    print("\n--- ALERTWildfire (alertwildfire.org) ---\n")
    awf = AlertWildfireClient()

    print("Fetching AWF camera list...")
    cameras = awf.get_cameras()
    features = cameras["features"]
    print(f"Total cameras: {len(features)}")

    # State breakdown
    state_counts = {}
    for f in features:
        s = f["properties"].get("state", "?")
        state_counts[s] = state_counts.get(s, 0) + 1
    print(f"By state: {dict(sorted(state_counts.items()))}")

    # Get a recently-active camera (castlepeak had movement recently)
    cam = awf.get_camera_by_slug("nv-castlepeak-1", cameras)
    if cam:
        p = cam["properties"]
        coords = cam["geometry"]["coordinates"]
        print(f"\nCamera: {p['name']} ({p['camera_slug']})")
        print(f"  UUID:    {p['id']}")
        print(f"  Hostname:{p['hostname']}")
        print(f"  Location:{coords[1]:.4f}N, {abs(coords[0]):.4f}W, {coords[2]}m ASL")
        print(f"  State/County: {p['state']}, {p['county']}")
        print(f"  Sponsor: {p['sponsor']}")
        print(f"  PTZ (az/tilt/zoom): {p['az_current']}/{p['tilt_current']}/{p['zoom_current']}")
        print(f"  Last update: {p['last_update_at']}")

        cam_id = p["id"]
        hostname = p["hostname"]

        # Current image
        print(f"\nFetching thumbnail...")
        try:
            img = awf.get_current_image(cam_id, full_size=False)
            print(f"  Thumbnail: {len(img):,} bytes JPEG")
            print(f"  Full image URL: {awf.get_current_image_url(cam_id, full_size=True)}")
        except Exception as e:
            print(f"  Error: {e}")

        # Timelapse (first 3 frames only for demo speed)
        print(f"\nStreaming 15m timelapse (first 3 frames)...")
        try:
            for i, frame in enumerate(awf.get_timelapse_frames(cam_id, "15m", max_frames=3)):
                print(f"  Frame {i+1}: {len(frame):,} bytes JPEG")
        except Exception as e:
            print(f"  {e}")

        # Proxy URL
        print(f"\nProxy URL (auth required): {awf.get_proxy_url(hostname)}")

    # Fire metadata
    print("\nFetching AWF fire metadata...")
    try:
        starts = awf.get_irwin_fire_starts()
        print(f"  Active fire starts: {len(starts.get('features', []))}")
    except Exception as e:
        print(f"  Error: {e}")

    try:
        perims = awf.get_irwin_fire_perimeters()
        print(f"  Fire perimeters: {len(perims.get('features', []))}")
    except Exception as e:
        print(f"  Error: {e}")

    try:
        noaa = awf.get_noaa_red_flag_areas()
        print(f"  NOAA red flag areas: {len(noaa.get('features', []))}")
    except Exception as e:
        print(f"  Error: {e}")

    # ---- AlertCalifornia ----
    print("\n--- AlertCalifornia (cameras.alertcalifornia.org) ---\n")
    ac = AlertCaliforniaClient()

    print("Fetching AlertCalifornia camera list...")
    ac_cams = ac.get_cameras()
    ac_features = ac_cams["features"]
    print(f"Total cameras: {len(ac_features)}")
    with_location = ac.get_cameras_with_location(ac_cams)
    print(f"  With valid coordinates: {len(with_location)}")
    active = ac.get_active_cameras(ac_cams, max_age_seconds=600)
    print(f"  Active (last 10 min): {len(active)}")

    # Sponsor breakdown
    sponsor_counts = {}
    for f in ac_features:
        s = f["properties"].get("sponsor") or "unknown"
        sponsor_counts[s] = sponsor_counts.get(s, 0) + 1
    top_sponsors = sorted(sponsor_counts.items(), key=lambda x: -x[1])[:5]
    print(f"  Top sponsors: {top_sponsors}")

    # Test a specific camera
    test_cam_id = "Axis-AlabamaHills1"
    print(f"\nFetching images for {test_cam_id}...")
    try:
        thumb = ac.get_thumbnail(test_cam_id)
        print(f"  Thumbnail: {len(thumb):,} bytes JPEG")
        full = ac.get_full_image(test_cam_id)
        print(f"  Full image: {len(full):,} bytes JPEG")
        print(f"  Image URL: {ac.get_image_url(test_cam_id, 'frame')}")
    except Exception as e:
        print(f"  Error: {e}")

    # Timelapse spec
    print(f"\nFetching 5-min timelapse spec for {test_cam_id}...")
    try:
        spec = ac.get_timelapse_spec(test_cam_id, "5 mins")
        frames = spec.get("frames", [])
        print(f"  {len(frames)} frames available")
        if frames:
            latest_ts = float(frames[-1].replace(".jpg", ""))
            dt = datetime.fromtimestamp(latest_ts)
            print(f"  Latest frame: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Pool: 10sec, Spec: 5-min.json")
    except Exception as e:
        print(f"  Error: {e}")

    # Panogrid
    print(f"\nFetching panogrid spec for {test_cam_id}...")
    try:
        pg = ac.get_panogrid_spec(test_cam_id)
        n_poses = sum(1 for p in pg.get("poses", []) if p is not None)
        print(f"  {n_poses} panoramic positions available")
        print(f"  Last updated: {datetime.fromtimestamp(pg['last_updated']).strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\nDemo complete.")
