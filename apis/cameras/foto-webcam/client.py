"""
Foto-Webcam.eu Python Client
============================
Reverse-engineered API client for https://www.foto-webcam.eu

Coverage: 399 cameras across Austria, Germany, Italy/South Tyrol, Switzerland,
          Liechtenstein, Greenland, Peru, and more.
Archive:  122M+ images dating back to ~2013 for some cameras.
Update:   Typically every 600 seconds (10 minutes).

Image Resolutions (via `current/` shortcuts):
  150, 180, 240, 320, 400, 640, 720, 1200, 1920 pixels wide

Image Resolutions (via dated archive paths, suffix-based):
  _la  standard (~816×459 to 1200×675px, ~57 KB)
  _lm  HD medium (1200×675px, ~57 KB, slightly different processing)
  _hd  Full HD (1920×1080px, ~153 KB)
  _uh  UHD/4K (3840×2160px, ~576 KB)  -- only on cameras that support it
  _hu  Huge/Max (up to 6000×4000px, ~1.8 MB)

Note: _sm (thumbnail) suffix is documented but _la is the confirmed default.

API Endpoints (all under https://www.foto-webcam.eu/webcam/include/):
  metadata.php              -- full camera list with metadata (JSON)
  list.php?wc=<id>&img=...  -- image data + 200-entry history slider (JSON)
  thumb.php?wc=<id>&mode=<year|day|img|bestof>[&img=&reg=&page=&count=]
                            -- paginated thumbnail index (JSON)
  ovlist.php?img=<ts>       -- overview data for all cams at a timestamp (JSON)
  daythumb.php?wc=<id>&img=<ts>&count=N -- day timelapse frames (JSON)
  rrdfetch.php?wc=<id>&ds=<sensors>&end=now&span=<secs>&rrdfile=wx.rrd
                            -- time-series sensor / weather data (JSON)
  camstatus.php?wc=<id>&serial=0 -- live camera operational status (JSON)
  exif.php?wc=<id>&img=<ts> -- EXIF data (HTML fragment)
  cal.php?wc=<id>           -- date picker calendar HTML
  wcinfos.php?wc=<id>       -- camera info page (HTML)
  map.php?wc=<id>           -- Leaflet map iframe (HTML)
  share.php?where=web&wc=<id> -- embedding widget (HTML)

Image URL Patterns:
  Current:  https://www.foto-webcam.eu/webcam/{cam_id}/current/{width}.jpg
  Archive:  https://www.foto-webcam.eu/webcam/{cam_id}/{YYYY}/{MM}/{DD}/{HHMM}_{suffix}.jpg

Weather Data Sources (ds parameter for rrdfetch.php):
  temp1  -- primary external temperature sensor
  temp2  -- secondary external temperature sensor
  temp3  -- internal housing temperature

Weather Span Values (span parameter, in seconds):
  10800    -- 3 hours
  86400    -- 24 hours (1 day)
  259200   -- 3 days
  604800   -- 7 days
  2592000  -- 30 days
  7776000  -- 90 days
  31536000 -- 1 year
  94608000 -- 3 years
  283824000 -- 9 years
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.foto-webcam.eu"
API_BASE = f"{BASE_URL}/webcam/include"

# Current-image width shortcuts served directly from /current/
CURRENT_WIDTHS: Tuple[int, ...] = (150, 180, 240, 320, 400, 640, 720, 1200, 1920)

# Archive image suffixes and their approximate resolutions
# Note: _sm is legacy; _la is the confirmed standard default suffix
ARCHIVE_SUFFIXES: Dict[str, str] = {
    "_la": "standard (~1200x675, ~57 KB)",
    "_lm": "HD medium (1200x675, ~57 KB, alt processing)",
    "_hd": "Full HD (1920x1080, ~153 KB)",
    "_uh": "UHD 4K (3840x2160, ~576 KB)",
    "_hu": "Huge/Max (up to 6000x4000, ~1.8 MB)",
    "_sm": "thumbnail (~180x101, legacy)",
}

# Weather time spans in seconds
WEATHER_SPANS: Dict[str, int] = {
    "3h":  10800,
    "24h": 86400,
    "3d":  259200,
    "7d":  604800,
    "30d": 2592000,
    "90d": 7776000,
    "1y":  31536000,
    "3y":  94608000,
    "9y":  283824000,
}

# Thumb modes for paginated image list
THUMB_MODES = ("img", "day", "year", "bestof")

# Country code mapping
COUNTRY_NAMES: Dict[str, str] = {
    "at": "Austria",
    "ch": "Switzerland",
    "de": "Germany",
    "gl": "Greenland",
    "it": "Italy",
    "li": "Liechtenstein",
    "pe": "Peru",
    "si": "Slovenia",
    "hr": "Croatia",
    "bb": "Barbados",
    "us": "United States",
    "??": "Unknown",
}

DEFAULT_TIMEOUT = 15
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; foto-webcam-client/1.0; "
    "+https://github.com/example/foto-webcam-client)"
)

# Known weather sensor names for rrdfetch.php
WEATHER_SENSORS = {
    "temp1": "Primary external temperature",
    "temp2": "Secondary external temperature",
    "temp3": "Internal housing temperature",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Camera:
    """Represents a single Foto-Webcam.eu camera with its metadata."""

    id: str
    name: str
    title: str
    keywords: str
    offline: bool
    hidden: bool
    country: str
    latitude: float
    longitude: float
    elevation: int           # metres above sea level
    direction: int           # compass bearing the camera faces (degrees)
    focal_len: int           # equivalent focal length in mm
    radius_km: float         # visible radius in km
    sector: int              # angle of field of view in degrees
    partner: bool            # partner / sponsored camera
    capture_interval: int    # update interval in seconds (typically 600)
    modtime: int             # Unix timestamp of last image
    details: int             # internal quality/detail score
    sortscore: str
    imgurl: str              # 400px thumbnail URL
    link: str                # canonical page URL
    local_link: str

    # Optional fields populated lazily
    huge_width: Optional[int] = None
    huge_height: Optional[int] = None
    hd_width: Optional[int] = None
    hd_height: Optional[int] = None
    fhd_width: Optional[int] = None
    fhd_height: Optional[int] = None
    uhd_width: Optional[int] = None
    uhd_height: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Camera":
        return cls(
            id=data["id"],
            name=data["name"],
            title=data["title"],
            keywords=data.get("keywords", ""),
            offline=data.get("offline", False),
            hidden=data.get("hidden", False),
            country=data.get("country", "??"),
            latitude=data.get("latitude", 0.0),
            longitude=data.get("longitude", 0.0),
            elevation=data.get("elevation", 0),
            direction=data.get("direction", 0),
            focal_len=data.get("focalLen", 0),
            radius_km=data.get("radius_km", 0.0),
            sector=data.get("sector", 0),
            partner=data.get("partner", False),
            capture_interval=data.get("captureInterval", 600),
            modtime=data.get("modtime", 0),
            details=data.get("details", 0),
            sortscore=data.get("sortscore", "0"),
            imgurl=data.get("imgurl", ""),
            link=data.get("link", ""),
            local_link=data.get("localLink", ""),
        )

    @property
    def country_name(self) -> str:
        return COUNTRY_NAMES.get(self.country, self.country.upper())

    @property
    def last_updated(self) -> datetime:
        return datetime.fromtimestamp(self.modtime, tz=timezone.utc)

    def current_image_url(self, width: int = 1200) -> str:
        """Return the URL for the current (live) image at the given width.

        Valid widths: 150, 180, 240, 320, 400, 640, 720, 1200, 1920.
        """
        if width not in CURRENT_WIDTHS:
            raise ValueError(
                f"Invalid width {width}. Must be one of {CURRENT_WIDTHS}"
            )
        return f"{BASE_URL}/webcam/{self.id}/current/{width}.jpg"

    def archive_image_url(
        self,
        timestamp: str,
        suffix: str = "_hd",
    ) -> str:
        """Return the URL for an archived image.

        Args:
            timestamp: Image timestamp in 'YYYY/MM/DD/HHMM' format
                       (e.g. '2024/07/15/1430').
            suffix:    One of _sm, _la, _lm, _hd, _uh, _hu.
                       Use list_image_info() to check which suffixes are
                       available for a specific camera / timestamp.
        """
        if suffix not in ARCHIVE_SUFFIXES:
            raise ValueError(
                f"Invalid suffix '{suffix}'. Must be one of {list(ARCHIVE_SUFFIXES)}"
            )
        return f"{BASE_URL}/webcam/{self.id}/{timestamp}{suffix}.jpg"

    def __repr__(self) -> str:
        return (
            f"Camera(id={self.id!r}, name={self.name!r}, "
            f"country={self.country!r}, elevation={self.elevation}m)"
        )


@dataclass
class ImageInfo:
    """Detailed info about a specific camera image (from list.php)."""

    camera_id: str
    timestamp: str           # 'YYYY/MM/DD/HHMM'
    image_path: str          # relative, e.g. '2024/07/15/1430_la.jpg'
    h: str                   # hash / version token
    is_newest: bool

    lrimg: str               # low-res path (may be empty)
    huge_img: str            # _hu path (may be empty)
    hd_img: str              # _lm path (may be empty)
    fhd_img: str             # _hd path (may be empty)
    uhd_img: str             # _uh path (may be empty)

    huge_width: int
    huge_height: int

    date_label: str          # human-readable date/time
    wx: str                  # weather string (may be empty)
    img_exif: str            # EXIF summary string

    history: List[str]       # up to 200 adjacent timestamps
    img_back: str            # timestamp of previous image
    img_fwd: str             # timestamp of next image
    day_back: str
    day_fwd: str
    month_back: str
    month_fwd: str
    year_back: str
    year_fwd: str
    is_bestof: bool

    @classmethod
    def from_dict(cls, camera_id: str, data: Dict[str, Any]) -> "ImageInfo":
        raw_ts = data.get("image", "").replace("_la.jpg", "").replace("_hu.jpg", "")
        return cls(
            camera_id=camera_id,
            timestamp=raw_ts,
            image_path=data.get("image", ""),
            h=data.get("h", ""),
            is_newest=data.get("newest", False),
            lrimg=data.get("lrimg", ""),
            huge_img=data.get("hugeimg", ""),
            hd_img=data.get("hdimg", ""),
            fhd_img=data.get("fhdimg", ""),
            uhd_img=data.get("uhdimg", ""),
            huge_width=int(data.get("hugeWidth", 0) or 0),
            huge_height=int(data.get("hugeHeight", 0) or 0),
            date_label=data.get("date", ""),
            wx=data.get("wx", ""),
            img_exif=data.get("imgExif", ""),
            history=data.get("history", []),
            img_back=data.get("imgback", ""),
            img_fwd=data.get("imgfwd", ""),
            day_back=data.get("dayback", ""),
            day_fwd=data.get("dayfwd", ""),
            month_back=data.get("monback", ""),
            month_fwd=data.get("monfwd", ""),
            year_back=data.get("yearback", ""),
            year_fwd=data.get("yearfwd", ""),
            is_bestof=data.get("isbestof", False),
        )

    def available_suffixes(self) -> List[str]:
        """Return the list of archive suffixes available for this image."""
        available = ["_sm", "_la"]  # always present
        if self.hd_img:
            available.append("_lm")
        if self.fhd_img:
            available.append("_hd")
        if self.uhd_img:
            available.append("_uh")
        if self.huge_img:
            available.append("_hu")
        return available

    def best_url(self) -> str:
        """Return the highest-resolution URL available."""
        base = f"{BASE_URL}/webcam/{self.camera_id}/"
        for attr, suffix in [
            ("huge_img", "_hu"),
            ("uhd_img", "_uh"),
            ("fhd_img", "_hd"),
            ("hd_img", "_lm"),
        ]:
            val = getattr(self, attr)
            if val:
                return base + val
        return base + self.image_path


@dataclass
class WeatherData:
    """Time-series sensor data returned by rrdfetch.php."""

    sensors: List[str]              # e.g. ["temp1", "temp2"]
    span_label: str                 # human-readable, e.g. "1 Tag"
    extent: Tuple[int, int]         # [start_ms, end_ms] Unix milliseconds
    last_time: int                  # Unix ms of the most recent reading
    last_values: List[str]          # latest reading per sensor
    dots: List[List[Dict]]          # dots[sensor_idx] = [{"time": ms, "val": float}, ...]
    images: List[str]               # archive timestamps in this period

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeatherData":
        return cls(
            sensors=data.get("ds", []),
            span_label=data.get("span", ""),
            extent=tuple(data.get("extent", [0, 0])),
            last_time=data.get("last_time", 0),
            last_values=data.get("last_val", []),
            dots=data.get("dots", []),
            images=data.get("images", []),
        )

    def latest_temperature(self, sensor_idx: int = 0) -> Optional[float]:
        """Return the most recent non-None temperature reading."""
        try:
            return float(self.last_values[sensor_idx])
        except (IndexError, TypeError, ValueError):
            return None


@dataclass
class CameraStatus:
    """Live operational status returned by camstatus.php."""

    cam: str
    status: str             # "ready" | "sleeping" | …
    last_img: str           # ISO datetime of last captured image
    image_size: int         # raw bytes of last captured (pre-processing) image
    proc_time: int          # post-processing time in ms
    upload_rate: int        # bytes/s
    heater: int             # 1 = housing heater currently active
    last_img_stamp: int     # Unix timestamp of last image
    last_stamp: int         # Unix timestamp of this status record
    serial: str
    upload_host: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraStatus":
        return cls(
            cam=data.get("cam", ""),
            status=data.get("status", ""),
            last_img=data.get("lastimg", ""),
            image_size=int(data.get("imagesize") or 0),
            proc_time=int(data.get("proctime") or 0),
            upload_rate=int(data.get("uploadrate") or 0),
            heater=int(data.get("heater") or 0),
            last_img_stamp=int(data.get("lastimgstamp") or 0),
            last_stamp=int(data.get("laststamp") or 0),
            serial=data.get("serial", ""),
            upload_host=data.get("uploadhost", ""),
        )

    @property
    def is_online(self) -> bool:
        return self.status == "ready"

    @property
    def last_updated(self) -> datetime:
        return datetime.fromtimestamp(self.last_stamp, tz=timezone.utc)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http_get(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> bytes:
    """Perform a simple GET request and return raw bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Any:
    data = _http_get(url, timeout=timeout, user_agent=user_agent)
    return json.loads(data.decode("utf-8"))


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class FotoWebcamClient:
    """
    High-level client for the Foto-Webcam.eu unofficial API.

    Basic usage::

        client = FotoWebcamClient()

        # List all cameras
        cameras = client.list_cameras()
        for cam in cameras[:5]:
            print(cam.name, cam.country_name, cam.elevation)

        # Get the live 1920px image URL for a camera
        cam = client.get_camera('zugspitze')
        print(cam.current_image_url(1920))

        # Get detailed info + history for the latest image
        info = client.get_image_info('zugspitze')
        print(info.date_label, info.wx, info.best_url())

        # List available archive images
        images = client.list_archive_images('zugspitze', mode='day')
        for ts in images[:10]:
            url = client.archive_url('zugspitze', ts, suffix='_hd')
            print(url)

        # Download the current image
        data = client.download_current_image('zugspitze', width=1920)
        with open('zugspitze.jpg', 'wb') as f:
            f.write(data)
    """

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_limit_delay: float = 0.5,
    ):
        """
        Args:
            timeout:          HTTP request timeout in seconds.
            user_agent:       User-Agent header for all requests.
            rate_limit_delay: Minimum seconds between successive API calls.
                              Set to 0 to disable (not recommended).
        """
        self.timeout = timeout
        self.user_agent = user_agent
        self.rate_limit_delay = rate_limit_delay
        self._last_request: float = 0.0
        self._camera_cache: Optional[List[Camera]] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, url: str) -> bytes:
        if self.rate_limit_delay > 0:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
        result = _http_get(url, timeout=self.timeout, user_agent=self.user_agent)
        self._last_request = time.monotonic()
        return result

    def _get_json(self, url: str) -> Any:
        raw = self._get(url)
        return json.loads(raw.decode("utf-8"))

    # ------------------------------------------------------------------
    # Camera listing
    # ------------------------------------------------------------------

    def list_cameras(
        self,
        country: Optional[str] = None,
        offline: Optional[bool] = None,
        hidden: Optional[bool] = None,
        refresh: bool = False,
    ) -> List[Camera]:
        """Return all cameras, optionally filtered.

        Args:
            country:  ISO 3166-1 alpha-2 country code to filter by
                      (e.g. 'at', 'de', 'it', 'ch', 'li', 'gl', 'pe').
            offline:  If False (default None), include/exclude offline cams.
            hidden:   If False (default None), include/exclude hidden cams.
            refresh:  Force a fresh API fetch even if results are cached.
        """
        if self._camera_cache is None or refresh:
            url = f"{API_BASE}/metadata.php"
            data = self._get_json(url)
            self._camera_cache = [Camera.from_dict(c) for c in data.get("cams", [])]

        results = self._camera_cache
        if country is not None:
            results = [c for c in results if c.country == country.lower()]
        if offline is not None:
            results = [c for c in results if c.offline == offline]
        if hidden is not None:
            results = [c for c in results if c.hidden == hidden]
        return results

    def get_camera(self, camera_id: str) -> Camera:
        """Return a single Camera by its ID.

        Raises:
            KeyError: If no camera with that ID exists.
        """
        cameras = self.list_cameras()
        for cam in cameras:
            if cam.id == camera_id:
                return cam
        raise KeyError(f"Camera {camera_id!r} not found")

    def find_cameras_near(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
    ) -> List[Tuple[float, Camera]]:
        """Return cameras within radius_km of a location, sorted by distance.

        Returns:
            List of (distance_km, Camera) tuples.
        """
        from math import asin, cos, radians, sin, sqrt

        def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            R = 6371.0
            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)
            a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
            return 2 * R * asin(sqrt(a))

        results = []
        for cam in self.list_cameras():
            dist = haversine(latitude, longitude, cam.latitude, cam.longitude)
            if dist <= radius_km:
                results.append((dist, cam))
        results.sort(key=lambda x: x[0])
        return results

    def list_cameras_by_country(self) -> Dict[str, List[Camera]]:
        """Return a dict mapping country code -> list of cameras."""
        result: Dict[str, List[Camera]] = {}
        for cam in self.list_cameras():
            result.setdefault(cam.country, []).append(cam)
        return result

    # ------------------------------------------------------------------
    # Image info / history
    # ------------------------------------------------------------------

    def get_image_info(
        self,
        camera_id: str,
        timestamp: str = "",
    ) -> ImageInfo:
        """Get detailed image info for a camera.

        Args:
            camera_id: Camera ID (e.g. 'zugspitze').
            timestamp: Image timestamp in 'YYYY/MM/DD/HHMM' format.
                       Leave empty or '' for the latest image.

        Returns:
            ImageInfo with navigation links, history, available resolutions,
            EXIF data, and weather string.
        """
        url = f"{API_BASE}/list.php?wc={camera_id}&img={timestamp}"
        data = self._get_json(url)
        return ImageInfo.from_dict(camera_id, data)

    def list_archive_images(
        self,
        camera_id: str,
        mode: str = "img",
        img: str = "",
        page: int = 0,
    ) -> List[str]:
        """Return a list of available image timestamps.

        Args:
            camera_id: Camera ID.
            mode:      One of 'img' (recent), 'day' (best-of-day), 'year'
                       (monthly index), 'bestof' (curated best shots).
            img:       Reference timestamp 'YYYY/MM/DD/HHMM'.  When given,
                       the list is centered around that time.
            page:      Page number for pagination (starts at 0).

        Returns:
            List of timestamp strings in 'YYYY/MM/DD/HHMM' format,
            newest first.
        """
        if mode not in THUMB_MODES:
            raise ValueError(f"mode must be one of {THUMB_MODES}")
        parts = [f"{API_BASE}/thumb.php?wc={camera_id}&mode={mode}"]
        if img:
            parts.append(f"&img={img}")
        if page:
            parts.append(f"&page={page}")
        url = "".join(parts)
        data = self._get_json(url)
        return data.get("images", [])

    def list_bestof(self, camera_id: str) -> List[str]:
        """Return the 'Best Shots' image timestamps for a camera."""
        return self.list_archive_images(camera_id, mode="bestof")

    def list_monthly_index(self, camera_id: str) -> List[str]:
        """Return one representative timestamp per month, newest first."""
        return self.list_archive_images(camera_id, mode="year")

    def iterate_archive(
        self,
        camera_id: str,
        start_timestamp: str = "",
        direction: str = "back",
    ) -> Iterator[str]:
        """Lazily walk the full archive of a camera.

        Uses the history embedded in list.php responses and the
        imgback / imgfwd navigation pointers to page through the
        entire archive without needing to know timestamps in advance.

        Args:
            camera_id:       Camera ID.
            start_timestamp: 'YYYY/MM/DD/HHMM' to start from.  Defaults to
                             the latest image.
            direction:       'back' (oldest first within current response,
                             going backwards in time) or 'fwd'.

        Yields:
            Timestamp strings.
        """
        info = self.get_image_info(camera_id, start_timestamp)
        seen: set = set()
        while True:
            for ts in (info.history or [info.timestamp]):
                if ts not in seen:
                    seen.add(ts)
                    yield ts
            next_ts = info.img_back if direction == "back" else info.img_fwd
            if not next_ts or next_ts in seen:
                break
            info = self.get_image_info(camera_id, next_ts)

    # ------------------------------------------------------------------
    # Image URLs
    # ------------------------------------------------------------------

    @staticmethod
    def current_image_url(camera_id: str, width: int = 1200) -> str:
        """Return the URL for the current (live) image.

        The server updates this URL every ~600 seconds but the file's
        cache-control is set to max-age=300.  Add a cache-busting
        query string (e.g. ?t=<unix_ts>) when polling frequently.

        Valid widths: 150, 180, 240, 320, 400, 640, 720, 1200, 1920
        """
        if width not in CURRENT_WIDTHS:
            raise ValueError(f"Width must be one of {CURRENT_WIDTHS}")
        return f"{BASE_URL}/webcam/{camera_id}/current/{width}.jpg"

    @staticmethod
    def archive_url(
        camera_id: str,
        timestamp: str,
        suffix: str = "_hd",
    ) -> str:
        """Return the URL for a specific archived image.

        Args:
            camera_id: Camera ID.
            timestamp: 'YYYY/MM/DD/HHMM'
            suffix:    _sm | _la | _lm | _hd | _uh | _hu

        Note: Not every suffix is available for every camera or timestamp.
              Use get_image_info() first to check available_suffixes().
        """
        if suffix not in ARCHIVE_SUFFIXES:
            raise ValueError(f"suffix must be one of {list(ARCHIVE_SUFFIXES)}")
        return f"{BASE_URL}/webcam/{camera_id}/{timestamp}{suffix}.jpg"

    # ------------------------------------------------------------------
    # Downloading
    # ------------------------------------------------------------------

    def download_current_image(
        self,
        camera_id: str,
        width: int = 1200,
    ) -> bytes:
        """Download and return the current live image as raw JPEG bytes."""
        url = self.current_image_url(camera_id, width)
        return self._get(url)

    def download_archive_image(
        self,
        camera_id: str,
        timestamp: str,
        suffix: str = "_hd",
    ) -> bytes:
        """Download and return an archived image as raw JPEG bytes."""
        url = self.archive_url(camera_id, timestamp, suffix)
        return self._get(url)

    def download_best_quality(
        self,
        camera_id: str,
        timestamp: str = "",
    ) -> Tuple[str, bytes]:
        """Download the highest-resolution version of an image.

        Returns:
            (url, image_bytes) tuple.  url tells you which suffix was used.
        """
        info = self.get_image_info(camera_id, timestamp)
        url = info.best_url()
        return url, self._get(url)

    # ------------------------------------------------------------------
    # Overview / snapshot
    # ------------------------------------------------------------------

    def get_overview_snapshot(self, timestamp: str) -> Dict[str, Any]:
        """Return weather / EXIF info for all cameras at a given timestamp.

        Useful for understanding what conditions looked like at a
        specific point in time across the whole network.

        Args:
            timestamp: 'YYYY/MM/DD/HHMM'

        Returns:
            Dict with keys 'when', 'cams' (list of {id, wx, exif, textColor}).
        """
        # Strip _la.jpg suffix if accidentally passed
        ts = timestamp.replace("_la.jpg", "").replace("_lm.jpg", "")
        url = f"{API_BASE}/ovlist.php?img={ts}"
        return self._get_json(url)

    # ------------------------------------------------------------------
    # Weather / sensor data
    # ------------------------------------------------------------------

    def get_weather_data(
        self,
        camera_id: str,
        sensors: str = "temp1:temp2",
        span: int = 86400,
        rrd_file: str = "wx.rrd",
    ) -> WeatherData:
        """Fetch time-series sensor data from the camera's RRD weather database.

        Endpoint: GET /webcam/include/rrdfetch.php

        Args:
            camera_id: Camera ID.
            sensors:   Colon-separated sensor names.
                       Known: 'temp1' (ext), 'temp2' (ext2), 'temp3' (housing).
                       e.g. 'temp1:temp2' or 'temp1:temp2:temp3'
            span:      Time window in seconds.  See WEATHER_SPANS for named values.
                       e.g. 86400=1day, 604800=1week, 31536000=1year
            rrd_file:  RRD filename (typically 'wx.rrd').

        Returns:
            WeatherData with dots[sensor_idx] = [{"time": unix_ms, "val": float}, ...]
            Null readings are represented as val=None.

        Example::

            wx = client.get_weather_data('zugspitze', span=86400)
            print(wx.sensors)          # ['temp1', 'temp2']
            print(wx.latest_temperature(0))  # -15.4
            print(f"{len(wx.dots[0])} data points")  # ~360 over 24h
        """
        params = urllib.parse.urlencode({
            "wc": camera_id,
            "ds": sensors,
            "end": "now",
            "span": str(span),
            "rrdfile": rrd_file,
            "wcimg": camera_id,
        })
        url = f"{API_BASE}/rrdfetch.php?{params}"
        data = self._get_json(url)
        return WeatherData.from_dict(data)

    # ------------------------------------------------------------------
    # Camera operational status
    # ------------------------------------------------------------------

    def get_camera_status(self, camera_id: str) -> CameraStatus:
        """Return live operational status for a camera.

        Endpoint: GET /webcam/include/camstatus.php?wc={id}&serial=0

        Returns fields including: last upload time, raw image file size,
        processing time, upload rate, heater state, upload host server.

        Example::

            st = client.get_camera_status('zugspitze')
            print(st.status)       # 'ready'
            print(st.image_size)   # 3093422 bytes (raw capture)
            print(st.proc_time)    # 51775 ms
            print(st.heater)       # 1 (heater ON)
        """
        url = f"{API_BASE}/camstatus.php?wc={camera_id}&serial=0"
        data = self._get_json(url)
        if isinstance(data, list):
            data = data[0] if data else {}
        return CameraStatus.from_dict(data)

    # ------------------------------------------------------------------
    # GeoJSON export
    # ------------------------------------------------------------------

    def export_geojson(
        self,
        include_offline: bool = False,
        country: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export all cameras as a GeoJSON FeatureCollection.

        Each camera is a GeoJSON Point with elevation as Z coordinate
        and all metadata in 'properties'.

        Args:
            include_offline: Include cameras currently offline.
            country:         ISO-2 country filter, e.g. 'de', 'at', 'it'.

        Returns:
            dict — a valid GeoJSON FeatureCollection, ready for json.dumps().

        Example::

            geojson = client.export_geojson(country='de')
            with open('cameras_de.geojson', 'w') as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)
        """
        cameras = self.list_cameras(country=country, offline=None if include_offline else False)
        features = []
        for cam in cameras:
            if not include_offline and cam.offline:
                continue
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [cam.longitude, cam.latitude, cam.elevation],
                },
                "properties": {
                    "id": cam.id,
                    "name": cam.name,
                    "title": cam.title,
                    "country": cam.country,
                    "elevation": cam.elevation,
                    "direction": cam.direction,
                    "focalLen": cam.focal_len,
                    "captureInterval": cam.capture_interval,
                    "offline": cam.offline,
                    "partner": cam.partner,
                    "imgUrl": cam.imgurl,
                    "link": cam.link,
                    "modtime": cam.modtime,
                    "keywords": cam.keywords,
                },
            })
        return {"type": "FeatureCollection", "features": features}

    # ------------------------------------------------------------------
    # Camera page info
    # ------------------------------------------------------------------

    def get_camera_resolutions(self, camera_id: str) -> Dict[str, Any]:
        """Return available resolutions for a camera by checking list.php.

        Returns a dict with keys: huge_width, huge_height, has_uhd, has_fhd,
        has_hd, suffixes.
        """
        info = self.get_image_info(camera_id)
        return {
            "camera_id": camera_id,
            "huge_width": info.huge_width,
            "huge_height": info.huge_height,
            "has_uhd": bool(info.uhd_img),
            "has_fhd": bool(info.fhd_img),
            "has_hd": bool(info.hd_img),
            "available_suffixes": info.available_suffixes(),
        }


# ---------------------------------------------------------------------------
# Convenience functions (module-level)
# ---------------------------------------------------------------------------

_default_client: Optional[FotoWebcamClient] = None


def _client() -> FotoWebcamClient:
    global _default_client
    if _default_client is None:
        _default_client = FotoWebcamClient()
    return _default_client


def list_cameras(**kwargs: Any) -> List[Camera]:
    """Return all cameras (uses a cached default client)."""
    return _client().list_cameras(**kwargs)


def get_camera(camera_id: str) -> Camera:
    """Return a Camera by ID."""
    return _client().get_camera(camera_id)


def get_image_info(camera_id: str, timestamp: str = "") -> ImageInfo:
    """Return image info for a camera (latest by default)."""
    return _client().get_image_info(camera_id, timestamp)


def current_image_url(camera_id: str, width: int = 1200) -> str:
    """Return the current live image URL."""
    return FotoWebcamClient.current_image_url(camera_id, width)


def archive_url(camera_id: str, timestamp: str, suffix: str = "_hd") -> str:
    """Return an archived image URL."""
    return FotoWebcamClient.archive_url(camera_id, timestamp, suffix)


# ---------------------------------------------------------------------------
# CLI demo / quick-test
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Run a quick demo/smoke-test of the client."""
    client = FotoWebcamClient(rate_limit_delay=0.3)

    print("=" * 60)
    print("Foto-Webcam.eu Client Demo")
    print("=" * 60)

    # 1. List all cameras
    print("\n[1] Loading camera list...")
    cameras = client.list_cameras()
    print(f"    Total cameras: {len(cameras)}")

    by_country = client.list_cameras_by_country()
    for code, cams in sorted(by_country.items(), key=lambda x: -len(x[1])):
        print(f"    {code.upper()} ({COUNTRY_NAMES.get(code, code)}): {len(cams)} cameras")

    # 2. Show a specific camera
    print("\n[2] Camera details: zugspitze")
    cam = client.get_camera("zugspitze")
    print(f"    Name:      {cam.name}")
    print(f"    Title:     {cam.title}")
    print(f"    Country:   {cam.country_name}")
    print(f"    Location:  {cam.latitude:.5f}°N, {cam.longitude:.5f}°E")
    print(f"    Elevation: {cam.elevation}m")
    print(f"    Direction: {cam.direction}°")
    print(f"    Interval:  {cam.capture_interval}s")
    print(f"    Online:    {not cam.offline}")
    print(f"    Live 400:  {cam.current_image_url(400)}")
    print(f"    Live 1920: {cam.current_image_url(1920)}")

    # 3. Latest image info
    print("\n[3] Latest image info for zugspitze...")
    info = client.get_image_info("zugspitze")
    print(f"    Timestamp: {info.timestamp}")
    print(f"    Date:      {info.date_label}")
    print(f"    Weather:   {info.wx or '(none)'}")
    print(f"    EXIF:      {info.img_exif}")
    print(f"    Max size:  {info.huge_width}x{info.huge_height}")
    print(f"    Suffixes:  {info.available_suffixes()}")
    print(f"    Best URL:  {info.best_url()}")
    print(f"    History:   {len(info.history)} entries from {info.history[0]} to {info.history[-1]}")

    # 4. Archive thumbnails
    print("\n[4] Recent archive images for zugspitze (mode=day)...")
    archive = client.list_archive_images("zugspitze", mode="day")
    for ts in archive[:5]:
        url = client.archive_url("zugspitze", ts, suffix="_hd")
        print(f"    {ts}  ->  {url}")

    # 5. Best shots
    print("\n[5] Best shots for bardolino...")
    bestof = client.list_bestof("bardolino")
    print(f"    {len(bestof)} best shots found")
    for ts in bestof[:3]:
        print(f"    {ts}")

    # 6. Monthly index
    print("\n[6] Monthly index for zugspitze (last 6 months)...")
    monthly = client.list_monthly_index("zugspitze")
    for ts in monthly[:6]:
        print(f"    {ts}")

    # 7. Cameras near Innsbruck
    print("\n[7] Cameras within 40km of Innsbruck (47.26°N, 11.40°E)...")
    nearby = client.find_cameras_near(47.26, 11.40, radius_km=40)
    for dist, ncam in nearby[:5]:
        print(f"    {dist:.1f}km  {ncam.id}  ({ncam.name})")

    # 8. Resolution check
    print("\n[8] Resolutions for bardolino...")
    res = client.get_camera_resolutions("bardolino")
    print(f"    {res}")

    # 9. Weather data
    print("\n[9] Weather sensor data for zugspitze (last 24h)...")
    try:
        wx = client.get_weather_data("zugspitze", sensors="temp1:temp2", span=86400)
        print(f"    Sensors:     {wx.sensors}")
        print(f"    Span label:  {wx.span_label}")
        pts = len(wx.dots[0]) if wx.dots else 0
        print(f"    Data points: {pts} per sensor")
        print(f"    Last values: {wx.last_values}")
        t = wx.latest_temperature(0)
        print(f"    Latest temp: {t}°C")
        print(f"    Images in window: {len(wx.images)}")
    except Exception as exc:
        print(f"    Error: {exc}")

    # 10. Camera operational status
    print("\n[10] Camera status for zugspitze...")
    try:
        st = client.get_camera_status("zugspitze")
        print(f"    Status:      {st.status}")
        print(f"    Last image:  {st.last_img}")
        print(f"    Image size:  {st.image_size:,} bytes (raw capture)")
        print(f"    Proc time:   {st.proc_time} ms")
        print(f"    Upload rate: {st.upload_rate} bytes/s")
        print(f"    Heater:      {'ON' if st.heater else 'off'}")
        print(f"    Upload host: {st.upload_host}")
    except Exception as exc:
        print(f"    Error: {exc}")

    # 11. GeoJSON export
    print("\n[11] GeoJSON export (German cameras only)...")
    try:
        gj = client.export_geojson(country="de")
        print(f"    Features: {len(gj['features'])}")
        first = gj['features'][0]['properties']
        print(f"    First:    {first['name']} ({first['country']}, {first['elevation']}m)")
    except Exception as exc:
        print(f"    Error: {exc}")

    # 12. Archive URL examples (static, no HTTP)
    print("\n[12] Archive URL reference")
    ts = "2026/03/27/1730"
    for suffix, desc in ARCHIVE_SUFFIXES.items():
        print(f"    {suffix}  {desc}")
        print(f"         {FotoWebcamClient.archive_url('zugspitze', ts, suffix)}")

    print("\nDemo complete.")


if __name__ == "__main__":
    _demo()
