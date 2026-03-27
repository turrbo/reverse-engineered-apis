#!/usr/bin/env python3
"""
Caltrans CWWP2 Traffic Camera Client
=====================================
A production-quality Python client for the California Department of
Transportation (Caltrans) Commercial Wholesale Web Portal (CWWP2).

This client uses only the Python standard library (urllib, json, dataclasses)
to interact with all publicly accessible Caltrans data feeds:
  - CCTV camera listings with static image and HLS video stream URLs
  - Camera images (current snapshot + 12 historical reference frames)
  - Roadway Weather Information Systems (RWIS) stations
  - Changeable Message Signs (CMS)
  - Chain Controls (CC)

No API key, authentication, or third-party libraries are required.
All data is publicly available at https://cwwp2.dot.ca.gov/

IMPORTANT – Fair Use:
  Bulk streaming (10+ simultaneous streams) requires a written agreement
  with Caltrans Traffic Operations. Contact cwwp2@dot.ca.gov.
  See https://dot.ca.gov/conditions-of-use for full conditions.

Author: Reverse-engineered from https://cwwp2.dot.ca.gov/ (March 2026)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Iterator, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://cwwp2.dot.ca.gov"
WZMEDIA_BASE = "https://wzmedia.dot.ca.gov"

#: All 12 Caltrans districts and their zero-padded file suffixes.
DISTRICTS: dict[int, str] = {
    1: "D01",
    2: "D02",
    3: "D03",
    4: "D04",
    5: "D05",
    6: "D06",
    7: "D07",
    8: "D08",
    9: "D09",
    10: "D10",
    11: "D11",
    12: "D12",
}

#: Known district → county coverage (simplified; see docs for full list).
DISTRICT_COVERAGE: dict[int, list[str]] = {
    1: ["Del Norte", "Humboldt", "Lake", "Mendocino"],
    2: ["Lassen", "Modoc", "Plumas", "Shasta", "Siskiyou", "Tehama", "Trinity"],
    3: ["Butte", "Colusa", "El Dorado", "Glenn", "Nevada", "Placer",
        "Sacramento", "Sierra", "Sutter", "Yolo", "Yuba"],
    4: ["Alameda", "Contra Costa", "Marin", "Napa", "San Francisco",
        "San Mateo", "Santa Clara", "Solano", "Sonoma"],
    5: ["Monterey", "San Benito", "San Luis Obispo", "Santa Barbara", "Santa Cruz"],
    6: ["Fresno", "Kings", "Madera", "Tulare"],
    7: ["Los Angeles", "Ventura"],
    8: ["Riverside", "San Bernardino"],
    9: ["Alpine", "Inyo", "Mono"],
    10: ["Amador", "Calaveras", "Mariposa", "Merced", "San Joaquin",
         "Stanislaus", "Tuolumne"],
    11: ["Imperial", "San Diego"],
    12: ["Orange"],
}

DEFAULT_TIMEOUT: int = 30  # seconds
DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RecordTimestamp:
    """Timestamp when the camera record was last updated in the data feed."""

    record_date: str
    """Date string in YYYY-MM-DD format."""

    record_time: str
    """Time string in HH:MM:SS format (local Pacific time)."""

    record_epoch: Optional[str] = None
    """Unix epoch seconds as a string (may be absent in some districts)."""


@dataclass
class CameraLocation:
    """Geographic and administrative location data for a camera."""

    district: int
    """Caltrans district number (1–12)."""

    location_name: str
    """Human-readable camera name, e.g. 'I-110 : (196) Avenue 26 Off Ramp'."""

    nearby_place: str
    """Nearest city or landmark, e.g. 'Cypress Park'."""

    longitude: float
    """WGS-84 longitude (negative = west)."""

    latitude: float
    """WGS-84 latitude."""

    elevation: Optional[int] = None
    """Elevation in feet above sea level."""

    direction: str = ""
    """Camera viewing direction, e.g. 'North', 'South', 'East', 'West'."""

    county: str = ""
    """California county name."""

    route: str = ""
    """Highway route designation, e.g. 'I-110', 'US-101', 'SR-20'."""

    route_suffix: str = ""
    """Route suffix modifier (rare)."""

    postmile_prefix: str = ""
    """Postmile prefix code (e.g. 'R' = reassigned)."""

    postmile: str = ""
    """Postmile along the route."""

    alignment: str = ""
    """Alignment code (rare)."""

    milepost: str = ""
    """Milepost value (different reference system from postmile)."""


@dataclass
class StaticImages:
    """Static JPEG snapshot URLs for a camera.

    Images are hosted at:
      ``https://cwwp2.dot.ca.gov/data/d{N}/cctv/image/{camera_id}/{camera_id}.jpg``

    Historical reference images live under a ``previous/`` sub-path.
    Both paths return ``Content-Type: image/jpeg`` with CORS headers
    (``Access-Control-Allow-Origin: *``).

    Cache-busting: Append ``?t=<epoch_ms>`` to force a fresh fetch and
    bypass any browser or CDN cache (this is what the official JS does).
    """

    current_image_url: str
    """URL of the most recent JPEG snapshot."""

    current_image_update_frequency: int
    """How often (minutes) the current image is refreshed."""

    reference_image_update_frequency: int
    """How often (minutes) reference/historical images are refreshed."""

    reference_images: List[str] = field(default_factory=list)
    """Historical snapshots (oldest-first).  Up to 12 frames are provided.
    Frames that haven't been captured yet are represented as an empty string
    or the sentinel value 'Not Reported'."""


@dataclass
class Camera:
    """A single Caltrans CCTV camera with full metadata.

    This is the primary object returned by :meth:`CaltransClient.get_cameras`.
    """

    index: str
    """Numeric index within the district data feed (1-based string)."""

    location: CameraLocation
    """Geographic and administrative location information."""

    timestamp: RecordTimestamp
    """When this record was last updated in the data feed."""

    in_service: bool
    """Whether the camera is currently active in the system."""

    current_image_url: str
    """Direct URL to the latest JPEG snapshot.

    Append ``?t=<epoch_ms>`` for cache-busting::

        url = camera.current_image_url + f"?t={int(time.time()*1000)}"
    """

    image_description: str = ""
    """Optional description of what the camera is looking at."""

    streaming_video_url: str = ""
    """HLS playlist URL for live video stream (empty string if not available).

    URL pattern: ``https://wzmedia.dot.ca.gov/D{N}/{stream_name}.stream/playlist.m3u8``

    The playlist is an M3U8 master manifest pointing to a chunklist with
    1280×720 H.264 video at approximately 124 kbps.  Compatible with any
    HLS-capable player (e.g. VLC, ffplay, video.js).
    """

    has_streaming: bool = False
    """True if a live HLS stream is available for this camera."""

    static_images: Optional[StaticImages] = None
    """Full static image data including historical reference frames."""

    @property
    def district(self) -> int:
        """Shortcut to district number."""
        return self.location.district

    @property
    def route(self) -> str:
        """Shortcut to highway route (e.g. 'I-5', 'US-101')."""
        return self.location.route

    @property
    def county(self) -> str:
        """Shortcut to county name."""
        return self.location.county

    @property
    def coords(self) -> tuple[float, float]:
        """(latitude, longitude) tuple for mapping."""
        return (self.location.latitude, self.location.longitude)

    def image_url_with_cache_bust(self) -> str:
        """Return current image URL with millisecond timestamp for cache busting."""
        return f"{self.current_image_url}?t={int(time.time() * 1000)}"

    def to_dict(self) -> dict:
        """Serialize camera to a plain dictionary (JSON-safe)."""
        return {
            "index": self.index,
            "district": self.location.district,
            "location_name": self.location.location_name,
            "nearby_place": self.location.nearby_place,
            "latitude": self.location.latitude,
            "longitude": self.location.longitude,
            "elevation_ft": self.location.elevation,
            "direction": self.location.direction,
            "county": self.location.county,
            "route": self.location.route,
            "postmile": self.location.postmile,
            "in_service": self.in_service,
            "has_streaming": self.has_streaming,
            "current_image_url": self.current_image_url,
            "streaming_video_url": self.streaming_video_url,
            "image_description": self.image_description,
            "record_date": self.timestamp.record_date,
            "record_time": self.timestamp.record_time,
        }


@dataclass
class CMSSign:
    """A Caltrans Changeable Message Sign (electronic highway sign).

    Data comes from ``/data/d{N}/cms/cmsStatusD{NN}.json``.
    """

    index: str
    district: int
    location_name: str
    longitude: float
    latitude: float
    county: str = ""
    route: str = ""
    in_service: bool = True
    message_text: str = ""
    """Current message displayed on the sign (may be empty/blank)."""


@dataclass
class ChainControl:
    """A Caltrans chain control location.

    Data comes from ``/data/d{N}/cc/ccStatusD{NN}.json``.
    Chain controls are road conditions that require tire chains.
    """

    index: str
    district: int
    location_name: str
    longitude: float
    latitude: float
    county: str = ""
    route: str = ""
    status: str = ""
    """Chain control status code, e.g. 'R1' (chains required), 'R2', 'R3', 'none'."""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class CaltransHTTPError(Exception):
    """Raised when a Caltrans endpoint returns an HTTP error."""

    def __init__(self, url: str, code: int, message: str) -> None:
        self.url = url
        self.code = code
        super().__init__(f"HTTP {code} fetching {url}: {message}")


class CaltransClient:
    """Client for the Caltrans CWWP2 data portal.

    All methods use only the Python standard library (urllib).  No third-party
    packages are required.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds. Default is 30.
    user_agent:
        User-Agent header sent with every request.
    retry_count:
        Number of automatic retries on transient errors (5xx, timeout).
    retry_delay:
        Seconds to wait between retry attempts.

    Examples
    --------
    Basic usage::

        from caltrans_client import CaltransClient

        client = CaltransClient()

        # List all cameras statewide
        cameras = client.get_all_cameras()
        print(f"Total cameras: {len(cameras)}")

        # Filter to I-5 cameras in District 2
        i5_cams = [c for c in cameras
                   if c.district == 2 and "I-5" in c.route]

        # Get live image URL (cache-busted)
        url = i5_cams[0].image_url_with_cache_bust()
        print(f"Image URL: {url}")

        # Fetch the JPEG bytes
        img_bytes = client.fetch_image(i5_cams[0])

        # Cameras with HLS streams
        streaming = [c for c in cameras if c.has_streaming]
        print(f"Stream URL: {streaming[0].streaming_video_url}")
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        retry_count: int = 3,
        retry_delay: float = 1.5,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.retry_count = retry_count
        self.retry_delay = retry_delay

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _get(self, url: str) -> bytes:
        """Perform a GET request with retry logic.  Returns raw bytes."""
        headers = {"User-Agent": self.user_agent}
        last_exc: Exception = RuntimeError("No attempt made")

        for attempt in range(1, self.retry_count + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                if exc.code < 500:
                    raise CaltransHTTPError(url, exc.code, str(exc.reason)) from exc
                last_exc = exc
            except Exception as exc:
                last_exc = exc

            if attempt < self.retry_count:
                time.sleep(self.retry_delay)

        raise CaltransHTTPError(url, 0, str(last_exc)) from last_exc

    def _get_json(self, url: str) -> dict:
        """Fetch a URL and parse the response as JSON."""
        raw = self._get(url)
        return json.loads(raw.decode("utf-8"))

    # ------------------------------------------------------------------
    # URL builders
    # ------------------------------------------------------------------

    @staticmethod
    def cctv_json_url(district: int) -> str:
        """Return the CCTV status JSON URL for a district.

        Pattern: ``https://cwwp2.dot.ca.gov/data/d{N}/cctv/cctvStatusD{NN}.json``
        """
        suffix = DISTRICTS[district]
        return f"{BASE_URL}/data/d{district}/cctv/cctvStatus{suffix}.json"

    @staticmethod
    def cctv_csv_url(district: int) -> str:
        """Return the CCTV status CSV URL for a district."""
        suffix = DISTRICTS[district]
        return f"{BASE_URL}/data/d{district}/cctv/cctvStatus{suffix}.csv"

    @staticmethod
    def cms_json_url(district: int) -> str:
        """Return the CMS status JSON URL for a district."""
        suffix = DISTRICTS[district]
        return f"{BASE_URL}/data/d{district}/cms/cmsStatus{suffix}.json"

    @staticmethod
    def chain_controls_json_url(district: int) -> str:
        """Return the chain controls JSON URL for a district."""
        suffix = DISTRICTS[district]
        return f"{BASE_URL}/data/d{district}/cc/ccStatus{suffix}.json"

    @staticmethod
    def rwis_json_url(district: int) -> str:
        """Return the RWIS (weather) JSON URL for a district.

        Note: Only districts 2, 3, 6, 8, 10 currently publish RWIS data.
        """
        suffix = DISTRICTS[district]
        return f"{BASE_URL}/data/d{district}/rwis/rwisStatus{suffix}.json"

    # ------------------------------------------------------------------
    # Camera parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_camera(raw: dict) -> Camera:
        """Parse a single ``cctv`` JSON object into a :class:`Camera`."""
        cctv = raw.get("cctv", raw)  # handle both wrapped and flat input

        # Timestamp
        ts_raw = cctv.get("recordTimestamp", {})
        timestamp = RecordTimestamp(
            record_date=ts_raw.get("recordDate", ""),
            record_time=ts_raw.get("recordTime", ""),
            record_epoch=ts_raw.get("recordEpoch"),
        )

        # Location
        loc_raw = cctv.get("location", {})
        try:
            lon = float(loc_raw.get("longitude", 0))
        except (ValueError, TypeError):
            lon = 0.0
        try:
            lat = float(loc_raw.get("latitude", 0))
        except (ValueError, TypeError):
            lat = 0.0
        try:
            elev = int(loc_raw.get("elevation", 0))
        except (ValueError, TypeError):
            elev = None

        location = CameraLocation(
            district=int(loc_raw.get("district", 0)),
            location_name=loc_raw.get("locationName", ""),
            nearby_place=loc_raw.get("nearbyPlace", ""),
            longitude=lon,
            latitude=lat,
            elevation=elev,
            direction=loc_raw.get("direction", ""),
            county=loc_raw.get("county", ""),
            route=loc_raw.get("route", ""),
            route_suffix=loc_raw.get("routeSuffix", ""),
            postmile_prefix=loc_raw.get("postmilePrefix", ""),
            postmile=loc_raw.get("postmile", ""),
            alignment=loc_raw.get("alignment", ""),
            milepost=loc_raw.get("milepost", ""),
        )

        # Image data
        img_data = cctv.get("imageData", {})
        stream_url = img_data.get("streamingVideoURL", "")
        if stream_url in ("", "Not Reported"):
            stream_url = ""

        static_raw = img_data.get("static", {})
        current_url = static_raw.get("currentImageURL", "")

        try:
            cur_freq = int(static_raw.get("currentImageUpdateFrequency", 0))
        except (ValueError, TypeError):
            cur_freq = 0
        try:
            ref_freq = int(static_raw.get("referenceImageUpdateFrequency", 0))
        except (ValueError, TypeError):
            ref_freq = 0

        ref_images: list[str] = []
        for i in range(1, 13):
            if i == 1:
                key = "referenceImage1UpdateAgoURL"
            else:
                key = f"referenceImage{i}UpdatesAgoURL"
            val = static_raw.get(key, "")
            if val and val != "Not Reported":
                ref_images.append(val)
            else:
                ref_images.append("")

        static_images = StaticImages(
            current_image_url=current_url,
            current_image_update_frequency=cur_freq,
            reference_image_update_frequency=ref_freq,
            reference_images=ref_images,
        )

        in_service_raw = cctv.get("inService", "false")
        in_service = str(in_service_raw).lower() == "true"

        return Camera(
            index=str(cctv.get("index", "")),
            location=location,
            timestamp=timestamp,
            in_service=in_service,
            current_image_url=current_url,
            image_description=img_data.get("imageDescription", ""),
            streaming_video_url=stream_url,
            has_streaming=bool(stream_url),
            static_images=static_images,
        )

    # ------------------------------------------------------------------
    # Public API – Cameras
    # ------------------------------------------------------------------

    def get_cameras(self, district: int) -> List[Camera]:
        """Fetch all cameras for a single Caltrans district.

        Parameters
        ----------
        district:
            District number from 1 to 12.

        Returns
        -------
        List[Camera]
            All cameras in the district, including those out of service.

        Raises
        ------
        CaltransHTTPError
            If the endpoint returns an HTTP error after all retries.
        ValueError
            If an unknown district number is provided.

        Examples
        --------
        ::

            client = CaltransClient()
            cameras = client.get_cameras(7)  # Los Angeles / Ventura
            streaming = [c for c in cameras if c.has_streaming]
            print(f"D7 streaming cameras: {len(streaming)}")
        """
        if district not in DISTRICTS:
            raise ValueError(
                f"Unknown district {district!r}. Valid values: {sorted(DISTRICTS)}"
            )
        url = self.cctv_json_url(district)
        data = self._get_json(url)
        return [self._parse_camera(item) for item in data.get("data", [])]

    def iter_cameras(self, district: int) -> Iterator[Camera]:
        """Iterator version of :meth:`get_cameras` – yields one camera at a time."""
        yield from self.get_cameras(district)

    def get_all_cameras(
        self,
        districts: Optional[List[int]] = None,
        skip_errors: bool = True,
    ) -> List[Camera]:
        """Fetch cameras from multiple (or all) districts.

        Parameters
        ----------
        districts:
            List of district numbers to fetch.  Defaults to all 12 districts.
        skip_errors:
            If True (default), log HTTP errors and continue with other
            districts.  If False, re-raise the first error encountered.

        Returns
        -------
        List[Camera]
            Combined list of all cameras from the requested districts.

        Examples
        --------
        ::

            client = CaltransClient()

            # All cameras statewide (takes ~10-15 seconds)
            all_cams = client.get_all_cameras()
            print(f"Statewide: {len(all_cams)} cameras")

            # Bay Area (D4) + LA (D7) only
            subset = client.get_all_cameras(districts=[4, 7])
        """
        if districts is None:
            districts = sorted(DISTRICTS.keys())

        cameras: list[Camera] = []
        for d in districts:
            try:
                batch = self.get_cameras(d)
                cameras.extend(batch)
            except CaltransHTTPError as exc:
                if skip_errors:
                    print(f"[WARNING] District {d}: {exc}", file=sys.stderr)
                else:
                    raise

        return cameras

    # ------------------------------------------------------------------
    # Public API – Filtering helpers
    # ------------------------------------------------------------------

    def filter_by_route(self, cameras: List[Camera], route: str) -> List[Camera]:
        """Filter cameras to those on a specific highway route.

        Parameters
        ----------
        cameras:
            List of cameras to filter (from :meth:`get_cameras` or
            :meth:`get_all_cameras`).
        route:
            Route string to match (case-insensitive partial match).
            Examples: ``'I-5'``, ``'US-101'``, ``'SR-91'``.

        Examples
        --------
        ::

            all_cams = client.get_all_cameras()
            i5_cams = client.filter_by_route(all_cams, "I-5")
        """
        route_upper = route.upper()
        return [c for c in cameras if route_upper in c.route.upper()]

    def filter_by_county(self, cameras: List[Camera], county: str) -> List[Camera]:
        """Filter cameras to those in a specific county.

        Parameters
        ----------
        county:
            County name (case-insensitive partial match).
            Example: ``'Los Angeles'``, ``'San Francisco'``.
        """
        county_lower = county.lower()
        return [c for c in cameras if county_lower in c.county.lower()]

    def filter_streaming(self, cameras: List[Camera]) -> List[Camera]:
        """Return only cameras that have a live HLS video stream."""
        return [c for c in cameras if c.has_streaming]

    def filter_in_service(self, cameras: List[Camera]) -> List[Camera]:
        """Return only cameras that are currently in service."""
        return [c for c in cameras if c.in_service]

    def search(
        self,
        cameras: List[Camera],
        query: str,
        fields: Optional[List[str]] = None,
    ) -> List[Camera]:
        """Full-text search across camera metadata fields.

        Parameters
        ----------
        cameras:
            List of cameras to search.
        query:
            Case-insensitive search string.
        fields:
            List of field names to search.  Defaults to
            ``['location_name', 'nearby_place', 'county', 'route']``.

        Examples
        --------
        ::

            all_cams = client.get_all_cameras()
            golden_gate = client.search(all_cams, "Golden Gate")
        """
        if fields is None:
            fields = ["location_name", "nearby_place", "county", "route"]

        q = query.lower()
        results = []
        for cam in cameras:
            for f in fields:
                if f == "location_name":
                    val = cam.location.location_name
                elif f == "nearby_place":
                    val = cam.location.nearby_place
                elif f == "county":
                    val = cam.location.county
                elif f == "route":
                    val = cam.location.route
                else:
                    val = str(getattr(cam, f, ""))
                if q in val.lower():
                    results.append(cam)
                    break
        return results

    # ------------------------------------------------------------------
    # Public API – Image fetching
    # ------------------------------------------------------------------

    def fetch_image(self, camera: Camera, cache_bust: bool = True) -> bytes:
        """Fetch the current JPEG snapshot for a camera.

        Parameters
        ----------
        camera:
            Camera instance from :meth:`get_cameras`.
        cache_bust:
            If True (default), appends ``?t=<epoch_ms>`` to the URL to
            bypass CDN or browser caching and get the freshest frame.

        Returns
        -------
        bytes
            Raw JPEG image bytes.

        Examples
        --------
        ::

            cam = cameras[0]
            jpg = client.fetch_image(cam)
            with open("latest.jpg", "wb") as f:
                f.write(jpg)
        """
        url = camera.current_image_url
        if not url:
            raise ValueError(f"Camera {camera.index} has no image URL")
        if cache_bust:
            url = f"{url}?t={int(time.time() * 1000)}"
        return self._get(url)

    def fetch_reference_image(
        self, camera: Camera, frame: int = 1, cache_bust: bool = False
    ) -> bytes:
        """Fetch one of the 12 historical reference JPEG frames.

        Parameters
        ----------
        camera:
            Camera instance.
        frame:
            Frame index (1 = 1 update ago, 12 = 12 updates ago).
        cache_bust:
            Whether to append a cache-busting timestamp.

        Returns
        -------
        bytes
            Raw JPEG bytes of the historical frame.

        Raises
        ------
        ValueError
            If the frame index is out of range or the URL is not available.
        """
        if not (1 <= frame <= 12):
            raise ValueError(f"frame must be between 1 and 12, got {frame}")
        if camera.static_images is None:
            raise ValueError(f"Camera {camera.index} has no static image data")
        url = camera.static_images.reference_images[frame - 1]
        if not url:
            raise ValueError(f"Camera {camera.index} frame {frame} not available")
        if cache_bust:
            url = f"{url}?t={int(time.time() * 1000)}"
        return self._get(url)

    # ------------------------------------------------------------------
    # Public API – HLS Stream info
    # ------------------------------------------------------------------

    def get_hls_chunklist_url(self, camera: Camera) -> str:
        """Resolve the HLS master playlist to the actual chunklist URL.

        Caltrans HLS streams use a two-level M3U8 structure:
          1. Master playlist at ``.../{stream_name}.stream/playlist.m3u8``
          2. Chunklist at ``.../{stream_name}.stream/chunklist_w{token}.m3u8``

        This method fetches the master playlist and extracts the chunklist URL.

        Parameters
        ----------
        camera:
            A camera with ``has_streaming=True``.

        Returns
        -------
        str
            Absolute URL of the chunklist (the actual segment index).

        Raises
        ------
        ValueError
            If the camera has no streaming URL.
        """
        if not camera.has_streaming:
            raise ValueError(f"Camera {camera.index} does not have a stream")

        master_url = camera.streaming_video_url
        raw = self._get(master_url).decode("utf-8", errors="replace")

        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # Relative URL → make absolute
                if not line.startswith("http"):
                    base = master_url.rsplit("/", 1)[0]
                    return f"{base}/{line}"
                return line

        raise ValueError(f"Could not find chunklist in master playlist for {master_url}")

    # ------------------------------------------------------------------
    # Public API – Other feeds
    # ------------------------------------------------------------------

    def get_cms_signs(self, district: int) -> List[CMSSign]:
        """Fetch Changeable Message Signs (electronic highway signs) for a district.

        Parameters
        ----------
        district:
            District number 1–12.

        Returns
        -------
        List[CMSSign]
            All CMS signs in the district with their current messages.
        """
        if district not in DISTRICTS:
            raise ValueError(f"Unknown district {district!r}")
        url = self.cms_json_url(district)
        try:
            data = self._get_json(url)
        except CaltransHTTPError:
            return []

        signs = []
        for item in data.get("data", []):
            cms = item.get("cms", item)
            loc = cms.get("location", {})
            try:
                lon = float(loc.get("longitude", 0))
                lat = float(loc.get("latitude", 0))
            except (ValueError, TypeError):
                lon, lat = 0.0, 0.0

            # Extract displayed message (varies by district/format)
            msg_data = cms.get("messageData", {})
            message = ""
            if isinstance(msg_data, dict):
                message = msg_data.get("phase", {}).get("page", {}).get("line", "") or ""
                if isinstance(message, list):
                    message = " / ".join(str(m) for m in message)

            signs.append(CMSSign(
                index=str(cms.get("index", "")),
                district=int(loc.get("district", district)),
                location_name=loc.get("locationName", ""),
                longitude=lon,
                latitude=lat,
                county=loc.get("county", ""),
                route=loc.get("route", ""),
                in_service=str(cms.get("inService", "true")).lower() == "true",
                message_text=str(message),
            ))
        return signs

    def get_chain_controls(self, district: int) -> List[ChainControl]:
        """Fetch chain control locations and statuses for a district.

        Chain controls indicate road conditions requiring tire chains on mountain passes.

        Parameters
        ----------
        district:
            District number 1–12.

        Returns
        -------
        List[ChainControl]
            Chain control locations (empty list if district has no data).
        """
        if district not in DISTRICTS:
            raise ValueError(f"Unknown district {district!r}")
        url = self.chain_controls_json_url(district)
        try:
            data = self._get_json(url)
        except CaltransHTTPError:
            return []

        controls = []
        for item in data.get("data", []):
            cc = item.get("cc", item)
            loc = cc.get("location", {})
            try:
                lon = float(loc.get("longitude", 0))
                lat = float(loc.get("latitude", 0))
            except (ValueError, TypeError):
                lon, lat = 0.0, 0.0

            controls.append(ChainControl(
                index=str(cc.get("index", "")),
                district=int(loc.get("district", district)),
                location_name=loc.get("locationName", ""),
                longitude=lon,
                latitude=lat,
                county=loc.get("county", ""),
                route=loc.get("route", ""),
                status=str(cc.get("status", "")),
            ))
        return controls

    # ------------------------------------------------------------------
    # Public API – Summary stats
    # ------------------------------------------------------------------

    def get_district_summary(self) -> dict:
        """Fetch a summary of camera counts per district.

        Returns
        -------
        dict
            Mapping of ``{district_number: camera_count}`` for all 12 districts.
            Errors are logged and that district is reported as None.

        Examples
        --------
        ::

            summary = client.get_district_summary()
            for d, count in summary.items():
                print(f"District {d}: {count} cameras")
        """
        summary: dict[int, Optional[int]] = {}
        for d in sorted(DISTRICTS):
            try:
                cameras = self.get_cameras(d)
                summary[d] = len(cameras)
            except CaltransHTTPError as exc:
                print(f"[WARNING] District {d}: {exc}", file=sys.stderr)
                summary[d] = None
        return summary

    # ------------------------------------------------------------------
    # GeoJSON export
    # ------------------------------------------------------------------

    @staticmethod
    def cameras_to_geojson(cameras: List[Camera]) -> dict:
        """Convert a list of cameras to a GeoJSON FeatureCollection.

        The returned dictionary is JSON-serializable and compatible with
        any GIS tool (QGIS, Leaflet, Mapbox, etc.).

        Parameters
        ----------
        cameras:
            List of :class:`Camera` objects.

        Returns
        -------
        dict
            GeoJSON FeatureCollection with one Feature per camera.

        Examples
        --------
        ::

            import json
            cameras = client.get_cameras(4)
            geojson = CaltransClient.cameras_to_geojson(cameras)
            with open("d4_cameras.geojson", "w") as f:
                json.dump(geojson, f, indent=2)
        """
        features = []
        for cam in cameras:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [cam.location.longitude, cam.location.latitude],
                },
                "properties": cam.to_dict(),
            })
        return {
            "type": "FeatureCollection",
            "features": features,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_list(args: argparse.Namespace, client: CaltransClient) -> None:
    """Handle the 'list' subcommand."""
    districts = [args.district] if args.district else None
    cameras = client.get_all_cameras(districts=districts, skip_errors=True)

    if args.route:
        cameras = client.filter_by_route(cameras, args.route)
    if args.county:
        cameras = client.filter_by_county(cameras, args.county)
    if args.streaming:
        cameras = client.filter_streaming(cameras)
    if args.in_service:
        cameras = client.filter_in_service(cameras)
    if args.search:
        cameras = client.search(cameras, args.search)

    if args.format == "json":
        print(json.dumps([c.to_dict() for c in cameras], indent=2))
        return

    if args.format == "geojson":
        print(json.dumps(CaltransClient.cameras_to_geojson(cameras), indent=2))
        return

    # Default: table
    print(f"{'D':>2}  {'Index':>5}  {'Route':<12}  {'Direction':<6}  {'Str':>3}  {'County':<18}  Name")
    print("-" * 120)
    for cam in cameras:
        stream_marker = "YES" if cam.has_streaming else "no"
        name = cam.location.location_name[:60]
        print(
            f"{cam.district:>2}  {cam.index:>5}  {cam.route:<12}  "
            f"{cam.location.direction:<6}  {stream_marker:>3}  "
            f"{cam.county:<18}  {name}"
        )
    print(f"\nTotal: {len(cameras)} cameras")


def _cli_show(args: argparse.Namespace, client: CaltransClient) -> None:
    """Handle the 'show' subcommand – show one camera's full details."""
    cameras = client.get_cameras(args.district)
    matches = [c for c in cameras if c.index == str(args.index)]
    if not matches:
        print(f"No camera found with index {args.index} in district {args.district}")
        sys.exit(1)

    cam = matches[0]
    print(f"Camera Index   : {cam.index}")
    print(f"District       : {cam.district}")
    print(f"Location       : {cam.location.location_name}")
    print(f"Nearby Place   : {cam.location.nearby_place}")
    print(f"Route          : {cam.route}")
    print(f"County         : {cam.county}")
    print(f"Direction      : {cam.location.direction}")
    print(f"Coordinates    : {cam.location.latitude:.6f}, {cam.location.longitude:.6f}")
    print(f"Elevation      : {cam.location.elevation} ft")
    print(f"In Service     : {cam.in_service}")
    print(f"Has Stream     : {cam.has_streaming}")
    print(f"Record Date    : {cam.timestamp.record_date} {cam.timestamp.record_time}")
    print()
    print(f"Image URL      : {cam.image_url_with_cache_bust()}")
    if cam.has_streaming:
        print(f"Stream URL     : {cam.streaming_video_url}")
        if args.resolve_stream:
            try:
                chunklist = client.get_hls_chunklist_url(cam)
                print(f"Chunklist URL  : {chunklist}")
            except Exception as exc:
                print(f"Chunklist URL  : ERROR - {exc}")
    print()
    if cam.static_images:
        print("Reference Images:")
        for i, url in enumerate(cam.static_images.reference_images, 1):
            status = url if url else "(not available)"
            print(f"  Frame {i:>2}: {status}")


def _cli_summary(client: CaltransClient) -> None:
    """Handle the 'summary' subcommand."""
    print("Fetching district summaries (may take ~30 seconds)...")
    summary = client.get_district_summary()
    total = 0
    print(f"\n{'District':>8}  {'Cameras':>8}  {'Counties'}")
    print("-" * 70)
    for d, count in summary.items():
        counties = ", ".join(DISTRICT_COVERAGE.get(d, []))
        count_str = str(count) if count is not None else "ERROR"
        if count:
            total += count
        print(f"{d:>8}  {count_str:>8}  {counties}")
    print(f"\nTotal: {total} cameras across all districts")


def _cli_image(args: argparse.Namespace, client: CaltransClient) -> None:
    """Handle the 'image' subcommand – download image to a file."""
    cameras = client.get_cameras(args.district)
    matches = [c for c in cameras if c.index == str(args.index)]
    if not matches:
        print(f"No camera with index {args.index} in district {args.district}")
        sys.exit(1)

    cam = matches[0]
    output = args.output or f"caltrans_d{args.district}_{args.index}.jpg"

    if args.frame > 0:
        print(f"Fetching reference frame {args.frame} for camera {cam.index}...")
        data = client.fetch_reference_image(cam, frame=args.frame)
    else:
        print(f"Fetching current image for camera {cam.index}...")
        data = client.fetch_image(cam)

    with open(output, "wb") as fh:
        fh.write(data)
    print(f"Saved {len(data):,} bytes to {output}")
    print(f"Camera: {cam.location.location_name}")
    print(f"Image URL: {cam.current_image_url}")


def _cli_demo(client: CaltransClient) -> None:
    """Handle the 'demo' subcommand – run a quick live data demonstration."""
    print("=" * 60)
    print("Caltrans CWWP2 Camera Client - Live Demo")
    print("=" * 60)
    print()

    print("1. Fetching District 7 (Los Angeles) cameras...")
    d7_cameras = client.get_cameras(7)
    streaming_d7 = client.filter_streaming(d7_cameras)
    print(f"   Total cameras: {len(d7_cameras)}")
    print(f"   With live video streams: {len(streaming_d7)}")
    print()

    print("2. First 5 cameras in District 7:")
    for cam in d7_cameras[:5]:
        stream_label = "[STREAM]" if cam.has_streaming else "[IMAGE]"
        print(f"   {stream_label} D{cam.district}/{cam.index:>4} | "
              f"{cam.route:<12} | {cam.location.location_name[:50]}")
    print()

    print("3. A streaming camera example:")
    if streaming_d7:
        cam = streaming_d7[0]
        print(f"   Name          : {cam.location.location_name}")
        print(f"   Route         : {cam.route}")
        print(f"   County        : {cam.county}")
        print(f"   Coordinates   : {cam.location.latitude:.6f}, {cam.location.longitude:.6f}")
        print(f"   Snapshot URL  : {cam.image_url_with_cache_bust()}")
        print(f"   Stream URL    : {cam.streaming_video_url}")
        print()
        print("   Verifying image endpoint is live...")
        try:
            img = client.fetch_image(cam)
            print(f"   OK - downloaded {len(img):,} bytes of JPEG data")
        except Exception as exc:
            print(f"   ERROR: {exc}")
    print()

    print("4. Filtering I-5 cameras statewide (Districts 2, 3)...")
    cams_23 = client.get_all_cameras(districts=[2, 3])
    i5_cams = client.filter_by_route(cams_23, "I-5")
    print(f"   I-5 cameras in D2+D3: {len(i5_cams)}")
    if i5_cams:
        print(f"   First match: {i5_cams[0].location.location_name}")
        print(f"   Snapshot: {i5_cams[0].current_image_url}")
    print()

    print("5. GeoJSON export (first 3 D7 cameras):")
    geojson = CaltransClient.cameras_to_geojson(d7_cameras[:3])
    print(f"   Generated GeoJSON with {len(geojson['features'])} features")
    print(f"   Sample feature ID field: {geojson['features'][0]['properties']['index']}")
    print()

    print("Demo complete.")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="caltrans_client",
        description=(
            "Caltrans CWWP2 Traffic Camera Client\n"
            "Data: https://cwwp2.dot.ca.gov/\n"
            "Map:  https://cwwp2.dot.ca.gov/vm/iframemap.htm"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help="HTTP request timeout in seconds (default: 30)"
    )
    parser.add_argument(
        "--retries", type=int, default=3,
        help="Number of retry attempts on error (default: 3)"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # --- demo ---
    sub.add_parser("demo", help="Run a live demonstration of the client")

    # --- summary ---
    sub.add_parser("summary", help="Show camera counts for all 12 districts")

    # --- list ---
    p_list = sub.add_parser("list", help="List cameras with optional filters")
    p_list.add_argument(
        "--district", type=int, choices=sorted(DISTRICTS),
        help="Filter to a single district (default: all)"
    )
    p_list.add_argument("--route", help="Filter by route (e.g. 'I-5', 'US-101')")
    p_list.add_argument("--county", help="Filter by county name")
    p_list.add_argument("--streaming", action="store_true",
                        help="Show only cameras with live video streams")
    p_list.add_argument("--in-service", dest="in_service", action="store_true",
                        help="Show only cameras that are in service")
    p_list.add_argument("--search", help="Full-text search across name/place/county/route")
    p_list.add_argument(
        "--format", choices=["table", "json", "geojson"], default="table",
        help="Output format (default: table)"
    )

    # --- show ---
    p_show = sub.add_parser("show", help="Show full details for one camera")
    p_show.add_argument("district", type=int, choices=sorted(DISTRICTS),
                        help="District number")
    p_show.add_argument("index", type=str, help="Camera index (e.g. '1', '42')")
    p_show.add_argument("--resolve-stream", action="store_true",
                        help="Resolve HLS chunklist URL from master playlist")

    # --- image ---
    p_img = sub.add_parser("image", help="Download a camera image to a file")
    p_img.add_argument("district", type=int, choices=sorted(DISTRICTS))
    p_img.add_argument("index", type=str, help="Camera index")
    p_img.add_argument("--output", "-o", help="Output filename (default: auto-generated)")
    p_img.add_argument(
        "--frame", type=int, default=0,
        help="Historical frame (1-12), or 0 for current (default: 0)"
    )

    return parser


def main() -> None:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    client = CaltransClient(timeout=args.timeout, retry_count=args.retries)

    if args.command == "demo":
        _cli_demo(client)
    elif args.command == "summary":
        _cli_summary(client)
    elif args.command == "list":
        _cli_list(args, client)
    elif args.command == "show":
        _cli_show(args, client)
    elif args.command == "image":
        _cli_image(args, client)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
