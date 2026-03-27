"""
NPS Webcams & Air Quality Cameras — Comprehensive Client
=========================================================
Reverse-engineered client covering both NPS webcam systems:

  1. NPS Developer API (developer.nps.gov)
     - 290 total webcams across all national parks
     - Streaming cameras (Brooks Falls bear cams, Old Faithful, El Capitan, etc.)
     - Full park metadata (description, hours, fees, images, addresses, lat/lon)
     - Paginated, filterable, no registration required with DEMO_KEY

  2. NPS Air Quality (ARD) Webcam Network (www.nps.gov)
     - 22 scientific visibility cameras at 20 major parks
     - Images updated every 15 minutes; AQ data updated hourly
     - Historical image archive back to October 2005
     - 30-day hourly air quality timeseries (ozone, PM2.5, SO2, met)

-----------------------------------------------------------------------
Discovered Endpoints — System 1: NPS Developer API
-----------------------------------------------------------------------
  Base:         https://developer.nps.gov/api/v1/
  API key:      DEMO_KEY  (public, rate-limited; register free at developer.nps.gov)

  Webcams:      GET /webcams
                  ?api_key=DEMO_KEY
                  &limit=50          (max observed: 500)
                  &start=0           (pagination offset)
                  &parkCode=yose     (optional 4-letter code, comma-separated)
                  &q=bears           (optional full-text search)

  Parks:        GET /parks
                  ?api_key=DEMO_KEY
                  &limit=50
                  &start=0
                  &parkCode=yose,grca
                  &stateCode=CA
                  &q=sequoia
                  &fields=images,addresses,latLong,contacts,operatingHours

  Alerts:       GET /alerts
  Amenities:    GET /amenities
  Events:       GET /events
  NewsReleases: GET /newsreleases
  Articles:     GET /articles
  Places:       GET /places

  Response shape (webcams):
    {
      "total": "290",
      "limit": "50",
      "start": "0",
      "data": [
        {
          "id":          "D32F071A-B8F7-08A4-65F765E8BB714DCF",
          "url":         "https://www.nps.gov/media/webcam/view.htm?id=D32F071A...",
          "title":       "Brooks Falls Bearcam",
          "description": "...",
          "images":      [{"url": "https://www.nps.gov/common/uploads/cropped_image/CCBB1534...jpg",
                           "altText": "A large grizzly bear stands in a rushing river.",
                           "title": "", "caption": "", "credit": ""}],
          "relatedParks":[{"parkCode": "katm", "fullName": "Katmai National Park",
                           "url": "https://www.nps.gov/katm/index.htm",
                           "designation": "National Park & Preserve", "states": "AK"}],
          "status":        "Active",
          "statusMessage": "",
          "isStreaming":   true,
          "tags":          ["wildlife","bears","grizzly","salmon","waterfall"],
          "latitude":      null,
          "longitude":     null,
          "geometryPoiId": null,
          "credit":        ""
        }
      ]
    }

  CDN image pattern:
    https://www.nps.gov/common/uploads/webcam/{UUID}.jpg
    https://www.nps.gov/common/uploads/cropped_image/{UUID}.jpg

  Webcam view page:
    https://www.nps.gov/media/webcam/view.htm?id={webcam-id}

-----------------------------------------------------------------------
Discovered Endpoints — System 2: NPS Air Quality (ARD) Webcam Network
-----------------------------------------------------------------------
  Park list:    GET  https://www.nps.gov/featurecontent/ard/webcams/json/NPSsitelist.txt
  Per-park:     GET  https://www.nps.gov/featurecontent/ard/webcams/json/{abbr}json.txt
  Current img:  GET  https://www.nps.gov/featurecontent/ard/webcams/images/{abbr}.jpg
  Large img:    GET  https://www.nps.gov/featurecontent/ard/webcams/images/{abbr}large.jpg
  Support imgs: GET  https://www.nps.gov/features/ard/webcams/supportimages/{abbr}_clear_hazy.jpg
                GET  https://www.nps.gov/features/ard/webcams/supportimages/{abbr}_terrain_features.jpg
                GET  https://www.nps.gov/features/ard/webcams/supportimages/{abbr}_webcam_map.jpg
  Archive API:  POST https://www.nps.gov/airwebcams/api/Search/Execute
                GET  https://www.nps.gov/airwebcams/api/GetAvailableDays/{abbr}
                GET  https://www.nps.gov/airwebcams/GetAsset/{uuid}/full.jpg
                     (also: thumbmedium.jpg / thumblarge.jpg / proxy/hires)
                POST https://www.nps.gov/airwebcams/api/GetServerTime
  AQ data:      GET  https://www.nps.gov/featurecontent/ard/currentdata/json/{abbr}.json
  Smoke data:   GET  https://www.nps.gov/featurecontent/ard/currentdata/json/{abbr}_smoke.json
  AQ park list: GET  https://www.nps.gov/featurecontent/ard/currentdata/json/parklist.json

-----------------------------------------------------------------------
Usage:
    # NPS Developer API (290 webcams across all parks)
    from nps_webcams_client import NPSWebcamAPIClient
    api = NPSWebcamAPIClient()   # uses DEMO_KEY by default
    webcams = api.list_webcams(park_code="katm")
    streaming = api.list_streaming_webcams()
    parks = api.list_parks(state_code="CA")
    geojson = api.get_webcams_geojson()

    # Air Quality Webcam Network (22 scientific cameras)
    from nps_webcams_client import NPSAQWebcamsClient
    aq = NPSAQWebcamsClient()
    img_bytes = aq.get_current_image("yose")
    data = aq.get_park_info("yose")
    archives = aq.search_archive("yose", "3/27/2026")
"""

from __future__ import annotations

import json as _json
import math
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Generator, Iterator, List, Optional

import requests

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# ---------------------------------------------------------------------------
# System 1: NPS Developer API
# ---------------------------------------------------------------------------

NPS_API_BASE = "https://developer.nps.gov/api/v1"

# The public demo key — no registration required; rate limit ~1,000 req/hour
NPS_DEMO_KEY = "DEMO_KEY"

# All known streaming webcam IDs at time of discovery (March 2026)
# Includes Brooks Falls bear cams, Yellowstone Old Faithful, Yosemite El Capitan,
# Grand Teton Craig Thomas VC, Channel Islands peregrine, Katmai cams, etc.
KNOWN_STREAMING_IDS = [
    "D32F071A-B8F7-08A4-65F765E8BB714DCF",  # Brooks Falls Bearcam (Katmai)
    "D3544467-9A96-0068-4B745F74BE0F93F8",  # Dumpling Mountain Cam (Katmai)
    "D404ED1D-E46F-2D08-8729B2BF39A2CCE9",  # River Watch Cam (Katmai)
    "D3A52BBE-EBA9-6A92-2AADC5935F9D882F",  # Naknek River Cam (Katmai)
    "D3D9F63F-C70C-3004-18867136AB648DFA",  # Riffles BearCam (Katmai, replay)
    "CE843A37-74A2-4408-9176-26A8DCC97294",  # Old Faithful Livestream (Yellowstone)
    "B28D5845-C504-BBA5-17748BFF1C6CC716",  # El Capitan (Yosemite)
    "1148077C-F06F-CD3A-969692F6BC0481AC",  # Yosemite High Sierra / Half Dome
    "AF555E5C-BE40-FE91-52E98E0EDD833B68",  # Channel Islands Live (stream 1)
    "2BB1FF1F-BF6C-9F10-BFAFCCEFC8F0D861",  # Channel Islands Live (stream 2)
    "A2A1C267-FC04-CC23-EB64A73DE9B46BF2",  # streaming cam 4
    "A2BB0297-D158-D4C2-32BCEB6A869A13B7",  # streaming cam 5
]


class NPSWebcamAPIClient:
    """
    Client for the NPS Developer API webcam and park endpoints.

    Parameters
    ----------
    api_key : str
        NPS API key.  The public DEMO_KEY works without registration but is
        rate-limited to ~1,000 requests/hour.  Register free at:
        https://www.nps.gov/subjects/digital/nps-data-api.htm
    timeout : int
        HTTP request timeout in seconds (default 30).
    session : requests.Session or None
        Optionally inject your own session.
    """

    def __init__(
        self,
        api_key: str = NPS_DEMO_KEY,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(_DEFAULT_HEADERS)
        self._session.headers["X-Api-Key"] = api_key

    # ------------------------------------------------------------------
    # Webcams
    # ------------------------------------------------------------------

    def list_webcams(
        self,
        park_code: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
        start: int = 0,
    ) -> Dict[str, Any]:
        """
        Return webcam records from the NPS Developer API.

        Parameters
        ----------
        park_code : str or None
            4-letter park code or comma-separated list, e.g. "yose" or "katm,yell"
        query : str or None
            Full-text search, e.g. "bears", "geyser", "air quality"
        limit : int
            Results per page (50–500 observed to work; API default 50).
        start : int
            Pagination offset (0-indexed).

        Returns
        -------
        dict with keys: total (str), limit (str), start (str), data (list of webcam dicts)
        Each webcam dict has: id, url, title, description, images, relatedParks,
        status, statusMessage, isStreaming, tags, latitude, longitude,
        geometryPoiId, credit
        """
        params: Dict[str, Any] = {
            "api_key": self.api_key,
            "limit": limit,
            "start": start,
        }
        if park_code:
            params["parkCode"] = park_code.lower()
        if query:
            params["q"] = query
        return self._get("/webcams", params=params).json()

    def iter_all_webcams(
        self,
        park_code: Optional[str] = None,
        query: Optional[str] = None,
        page_size: int = 100,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Yield every webcam record, handling pagination automatically.

        Parameters
        ----------
        park_code : str or None  Optional park filter
        query : str or None      Optional full-text filter
        page_size : int          Records per API call (default 100)

        Yields
        ------
        Individual webcam dicts (same fields as list_webcams)
        """
        start = 0
        while True:
            resp = self.list_webcams(
                park_code=park_code, query=query, limit=page_size, start=start
            )
            data = resp.get("data", [])
            if not data:
                break
            yield from data
            total = int(resp.get("total", 0))
            start += len(data)
            if start >= total:
                break

    def list_streaming_webcams(
        self, park_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Return only webcams with isStreaming=True.

        Note: the 'q' parameter does not filter by streaming status; this method
        fetches all webcams and filters client-side.

        Returns
        -------
        List of webcam dicts where isStreaming is True
        """
        return [
            cam
            for cam in self.iter_all_webcams(park_code=park_code)
            if cam.get("isStreaming") is True
        ]

    def list_active_webcams(
        self, park_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return webcams with status == 'Active'."""
        return [
            cam
            for cam in self.iter_all_webcams(park_code=park_code)
            if cam.get("status") == "Active"
        ]

    def get_webcam(self, webcam_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single webcam record by its UUID.

        The API does not provide a /webcams/{id} endpoint, so this fetches
        all webcams and finds the matching one.  Prefer iter_all_webcams()
        if you need to search by ID across the full catalogue.

        Returns
        -------
        Webcam dict or None if not found.
        """
        for cam in self.iter_all_webcams():
            if cam.get("id") == webcam_id:
                return cam
        return None

    def get_webcam_image_url(self, webcam: Dict[str, Any]) -> Optional[str]:
        """
        Extract the thumbnail/preview image URL from a webcam record.

        The API stores image URLs in the 'images' array.  Most webcams have
        0 images in this array (the live feed is served separately via the
        /media/webcam/view.htm page).  Only a small fraction (~3%) have
        a static preview here.

        Returns
        -------
        str URL or None
        """
        images = webcam.get("images", [])
        if images:
            raw_url = images[0].get("url", "")
            # Fix duplicated-domain bug sometimes present in API data
            if raw_url.startswith("https://www.nps.govhttps://"):
                raw_url = raw_url.replace("https://www.nps.govhttps://", "https://")
            return raw_url or None
        return None

    def get_webcam_view_url(self, webcam_id: str) -> str:
        """
        Build the NPS webcam view page URL for a given webcam ID.

        This page embeds the live or refreshing image for the camera.

        Returns
        -------
        str  e.g. "https://www.nps.gov/media/webcam/view.htm?id=D32F071A-..."
        """
        return f"https://www.nps.gov/media/webcam/view.htm?id={webcam_id}"

    # ------------------------------------------------------------------
    # Parks
    # ------------------------------------------------------------------

    def list_parks(
        self,
        park_code: Optional[str] = None,
        state_code: Optional[str] = None,
        query: Optional[str] = None,
        fields: str = "images,addresses,latLong,contacts,operatingHours",
        limit: int = 50,
        start: int = 0,
    ) -> Dict[str, Any]:
        """
        Return park records from the NPS Developer API.

        Parameters
        ----------
        park_code : str or None
            4-letter park code or comma-separated list.
        state_code : str or None
            2-letter state code, e.g. "CA", "AK", "NY"
        query : str or None
            Full-text search.
        fields : str
            Comma-separated list of extra fields to include.
            Available: images, addresses, latLong, contacts, operatingHours,
                       activities, topics, entranceFees, entrancePasses,
                       directionsInfo, weatherInfo
        limit : int
            Results per page.
        start : int
            Pagination offset.

        Returns
        -------
        dict with total, limit, start, data (list of park dicts).
        Each park dict: id, url, fullName, parkCode, designation, description,
        latitude, longitude, latLong, states, images (array), addresses (array),
        contacts, operatingHours, directionsInfo, weatherInfo, activities,
        topics, entranceFees, entrancePasses
        """
        params: Dict[str, Any] = {
            "api_key": self.api_key,
            "limit": limit,
            "start": start,
            "fields": fields,
        }
        if park_code:
            params["parkCode"] = park_code.lower()
        if state_code:
            params["stateCode"] = state_code.upper()
        if query:
            params["q"] = query
        return self._get("/parks", params=params).json()

    def iter_all_parks(
        self,
        state_code: Optional[str] = None,
        query: Optional[str] = None,
        fields: str = "images,addresses,latLong",
        page_size: int = 100,
    ) -> Generator[Dict[str, Any], None, None]:
        """Yield every park record, handling pagination automatically."""
        start = 0
        while True:
            resp = self.list_parks(
                state_code=state_code,
                query=query,
                fields=fields,
                limit=page_size,
                start=start,
            )
            data = resp.get("data", [])
            if not data:
                break
            yield from data
            total = int(resp.get("total", 0))
            start += len(data)
            if start >= total:
                break

    def get_park(self, park_code: str) -> Optional[Dict[str, Any]]:
        """
        Return metadata for a single park by 4-letter park code.

        Returns
        -------
        Park dict or None
        """
        resp = self.list_parks(park_code=park_code)
        data = resp.get("data", [])
        return data[0] if data else None

    # ------------------------------------------------------------------
    # Other NPS Developer API endpoints
    # ------------------------------------------------------------------

    def list_alerts(
        self,
        park_code: Optional[str] = None,
        limit: int = 50,
        start: int = 0,
    ) -> Dict[str, Any]:
        """
        Return current park alerts (closures, hazards, etc.).

        Each alert has: id, url, title, description, category, parkCode, relatedParks
        """
        params: Dict[str, Any] = {"api_key": self.api_key, "limit": limit, "start": start}
        if park_code:
            params["parkCode"] = park_code.lower()
        return self._get("/alerts", params=params).json()

    def list_events(
        self,
        park_code: Optional[str] = None,
        limit: int = 50,
        start: int = 0,
    ) -> Dict[str, Any]:
        """Return scheduled events at parks."""
        params: Dict[str, Any] = {"api_key": self.api_key, "limit": limit, "start": start}
        if park_code:
            params["parkCode"] = park_code.lower()
        return self._get("/events", params=params).json()

    def list_news_releases(
        self,
        park_code: Optional[str] = None,
        limit: int = 50,
        start: int = 0,
    ) -> Dict[str, Any]:
        """Return NPS news releases."""
        params: Dict[str, Any] = {"api_key": self.api_key, "limit": limit, "start": start}
        if park_code:
            params["parkCode"] = park_code.lower()
        return self._get("/newsreleases", params=params).json()

    # ------------------------------------------------------------------
    # GeoJSON / map data
    # ------------------------------------------------------------------

    def get_webcams_geojson(
        self,
        park_code: Optional[str] = None,
        active_only: bool = True,
    ) -> Dict[str, Any]:
        """
        Build a GeoJSON FeatureCollection from webcam records.

        Only webcams with latitude/longitude coordinates are included.
        Most webcams lack coordinates; those that have them are typically
        the ARD air quality cameras (also catalogued in the Developer API).

        Parameters
        ----------
        park_code : str or None  Optional filter
        active_only : bool       Exclude Inactive webcams (default True)

        Returns
        -------
        GeoJSON FeatureCollection dict
        """
        features = []
        for cam in self.iter_all_webcams(park_code=park_code):
            if active_only and cam.get("status") != "Active":
                continue
            try:
                lat = float(cam["latitude"])
                lon = float(cam["longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            park_info = cam.get("relatedParks", [{}])[0] if cam.get("relatedParks") else {}
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": cam.get("id"),
                    "title": cam.get("title"),
                    "description": cam.get("description"),
                    "url": cam.get("url"),
                    "status": cam.get("status"),
                    "isStreaming": cam.get("isStreaming"),
                    "tags": cam.get("tags", []),
                    "parkCode": park_info.get("parkCode"),
                    "parkName": park_info.get("fullName"),
                    "image_url": self.get_webcam_image_url(cam),
                },
            }
            features.append(feature)
        return {"type": "FeatureCollection", "features": features}

    def get_parks_geojson(
        self,
        state_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a GeoJSON FeatureCollection from all NPS park records.

        Returns
        -------
        GeoJSON FeatureCollection with Point features for each park.
        """
        features = []
        for park in self.iter_all_parks(state_code=state_code, fields="images,latLong"):
            try:
                lat = float(park["latitude"])
                lon = float(park["longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "parkCode": park.get("parkCode"),
                    "fullName": park.get("fullName"),
                    "designation": park.get("designation"),
                    "states": park.get("states"),
                    "description": park.get("description"),
                    "url": park.get("url"),
                    "images": park.get("images", []),
                },
            }
            features.append(feature)
        return {"type": "FeatureCollection", "features": features}

    def save_webcams_geojson(self, output_path: str, **kwargs) -> int:
        """
        Fetch all geolocated webcams and save as a GeoJSON file.

        Returns number of features saved.
        """
        geojson = self.get_webcams_geojson(**kwargs)
        with open(output_path, "w") as f:
            _json.dump(geojson, f, indent=2)
        return len(geojson["features"])

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **kwargs) -> requests.Response:
        url = NPS_API_BASE + path
        kwargs.setdefault("timeout", self.timeout)
        resp = self._session.get(url, **kwargs)
        resp.raise_for_status()
        return resp


# ---------------------------------------------------------------------------
# System 2: NPS Air Quality (ARD) Webcam Network
# ---------------------------------------------------------------------------

_BASE_WEBCAM   = "https://www.nps.gov/featurecontent/ard/webcams"
_BASE_SUPPORT  = "https://www.nps.gov/features/ard/webcams/supportimages"
_BASE_ARCHIVE  = "https://www.nps.gov/airwebcams"
_BASE_CURRDATA = "https://www.nps.gov/featurecontent/ard/currentdata"

# Image size tokens for the archive GetAsset endpoint
ARCHIVE_IMAGE_SIZES = {
    "thumbnail_small": "thumbmedium.jpg",    # ~1–2 KB thumbnail
    "thumbnail_large": "thumblarge.jpg",     # ~4 KB thumbnail
    "full":            "full.jpg",           # full resolution (~1–3 MB)
    "hires_proxy":     "proxy/hires",        # high-res proxy (~90 KB)
}

# All 22 ARD webcam sites — abbr → (name, state, parktype)
# parktype: "1"=single-site, "2"=dual-site, "3"=HAVO multi-sensor
ARD_PARKS: Dict[str, tuple] = {
    "acad": ("Acadia National Park",                             "Maine",           "1"),
    "bibe": ("Big Bend National Park",                           "Texas",           "1"),
    "brda": ("Bryce Canyon National Park",                       "Utah",            "2"),
    "dena": ("Denali National Park",                             "Alaska",          "1"),
    "dino": ("Dinosaur National Monument",                       "Colorado/Utah",   "1"),
    "grca": ("Grand Canyon National Park",                       "Arizona",         "2"),
    "grte": ("Grand Teton National Park",                        "Wyoming",         "1"),
    "grcd": ("Great Smoky Mountains NP – Kuwohi",                "TN/NC",           "1"),
    "grsm": ("Great Smoky Mountains NP – Look Rock",             "TN/NC",           "1"),
    "grpk": ("Great Smoky Mountains NP – Purchase Knob",         "TN/NC",           "1"),
    "havo": ("Hawaii Volcanoes National Park",                    "Hawaii",          "3"),
    "jotr": ("Joshua Tree National Park",                        "California",      "1"),
    "maca": ("Mammoth Cave National Park",                       "Kentucky",        "1"),
    "mora": ("Mount Rainier National Park",                      "Washington",      "2"),
    "wash": ("National Mall and Memorial Parks",                 "DC",              "2"),
    "noca": ("North Cascades National Park",                     "Washington",      "1"),
    "olym": ("Olympic National Park",                            "Washington",      "1"),
    "pore": ("Point Reyes National Seashore",                    "California",      "1"),
    "seki": ("Sequoia and Kings Canyon National Parks",          "California",      "1"),
    "shen": ("Shenandoah National Park",                         "Virginia",        "1"),
    "thro": ("Theodore Roosevelt National Park",                 "North Dakota",    "1"),
    "yose": ("Yosemite National Park",                           "California",      "1"),
}

# Dual-site parks
ARD_DUAL_SITE_PARKS = {code for code, (_, _, pt) in ARD_PARKS.items() if pt == "2"}
# HAVO (multi-sensor SO2 parks)
ARD_HAVO_PARKS = {code for code, (_, _, pt) in ARD_PARKS.items() if pt == "3"}


def _fake_uuid() -> str:
    """Mimic NPS JS createFakeUUID() cache-busting pattern."""
    return str(uuid.uuid4())


def decode_available_days_bitmask(year: int, month: int, bitmask: int) -> List[int]:
    """
    Decode the bitmask returned by GetAvailableDays into a list of day numbers.

    The API returns {year: {month: bitmask}}.  Each bitmask is a 32-bit int
    where bit N (LSB = day 1) indicates whether that day has archive images.

    Example
    -------
    >>> decode_available_days_bitmask(2026, 3, 134217727)
    [1, 2, 3, ..., 27]
    """
    days = []
    for day in range(1, 32):
        if bitmask & (1 << (day - 1)):
            try:
                date(year, month, day)
                days.append(day)
            except ValueError:
                break
    return days


class NPSAQWebcamsClient:
    """
    Client for the NPS Air Quality (ARD) Webcam network.

    Covers 22 scientific visibility cameras at 20 major US national parks.
    Images update every 15 minutes; air quality data updates hourly.
    Historical archive extends back to October 2005.

    No API key or registration required.

    Parameters
    ----------
    timeout : int
        HTTP request timeout in seconds (default 30).
    session : requests.Session or None
        Optionally inject your own session.
    """

    def __init__(self, timeout: int = 30, session: Optional[requests.Session] = None):
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(_DEFAULT_HEADERS)
        self._session.headers["Referer"] = "https://www.nps.gov/subjects/air/webcams.htm"

    # ------------------------------------------------------------------
    # Park / camera inventory
    # ------------------------------------------------------------------

    def list_parks(self) -> List[Dict[str, Any]]:
        """
        Return the full list of parks in the ARD webcam network.

        Each dict has: abbr, name, state, imagedate, parktype
        (abbr is the 4-letter code used throughout the API)
        """
        url = f"{_BASE_WEBCAM}/json/NPSsitelist.txt"
        resp = self._get(url, params={"uuid": _fake_uuid()})
        return resp.json().get("parks", [])

    def get_park_info(self, park_code: str) -> Dict[str, Any]:
        """
        Return detailed metadata + current air quality readings for one park.

        Response includes: name, state, URL, URLarchives, imagedate, imagesite,
        viewdetail, imagefile, imagefilelarge, imageclearhazy, imagelandmarks,
        imagemapit, SITE1 (and SITE2 for dual-site parks), each with:
          OZONE, PM25, PM25PA, SO2, VISIBILITY, AT (temp), RH (humidity),
          WS (wind speed), WD (wind direction), PRECIPLASTHOUR, etc.

        Parameters
        ----------
        park_code : str  e.g. "yose", "grca", "havo"
        """
        url = f"{_BASE_WEBCAM}/json/{park_code.lower()}json.txt"
        resp = self._get(url, params={"uuid": _fake_uuid()})
        return resp.json()

    # ------------------------------------------------------------------
    # Current images
    # ------------------------------------------------------------------

    def get_current_image_url(self, park_code: str, size: str = "standard") -> str:
        """
        Return the URL for the most-recently captured webcam image.

        Parameters
        ----------
        park_code : str  e.g. "yose"
        size : str
            "standard" — regular JPEG (~150–250 KB)
            "large"    — full-resolution JPEG (~1.5–2.5 MB)
        """
        code = park_code.lower()
        filename = f"{code}large.jpg" if size == "large" else f"{code}.jpg"
        # Cache-bust timestamp mirrors browser JS behaviour
        return f"{_BASE_WEBCAM}/images/{filename}?{int(time.time() * 1000)}"

    def get_current_image(self, park_code: str, size: str = "standard") -> bytes:
        """
        Download and return the most-recent webcam image as raw bytes.

        Parameters
        ----------
        park_code : str  e.g. "yose"
        size : str  "standard" | "large"
        """
        url = self.get_current_image_url(park_code, size)
        resp = self._get(url)
        return resp.content

    def get_support_image_url(
        self, park_code: str, image_type: str = "clear_hazy"
    ) -> str:
        """
        Return URL for a static reference image for a camera site.

        Parameters
        ----------
        image_type : str
            "clear_hazy"        — side-by-side clear vs hazy reference
            "terrain_features"  — annotated terrain landmarks
            "webcam_map"        — map showing camera location + view direction
        """
        return f"{_BASE_SUPPORT}/{park_code.lower()}_{image_type}.jpg"

    def get_support_image(self, park_code: str, image_type: str = "clear_hazy") -> bytes:
        """Download and return a static support image as raw bytes."""
        return self._get(self.get_support_image_url(park_code, image_type)).content

    # ------------------------------------------------------------------
    # Archive / historical images
    # ------------------------------------------------------------------

    def get_archive_server_time(self) -> Dict[str, int]:
        """
        Return the current server time from the archive system.

        Returns dict with keys: year, month, day, hour, minute
        """
        resp = self._post(f"{_BASE_ARCHIVE}/api/GetServerTime")
        return resp.json()

    def get_available_days(self, park_code: str) -> Dict[str, Any]:
        """
        Return {year: {month: [day, ...]}} for all dates with archive images.

        The raw API uses bitmasks per year/month; this method decodes them.
        Also includes "MinDay" and "MaxDay" string keys (e.g. "10/18/2005").

        Parameters
        ----------
        park_code : str  e.g. "yose"

        Returns
        -------
        dict like {"2005": {"10": [18,19,...]}, ..., "MinDay": "10/18/2005", "MaxDay": "3/27/2026"}
        """
        url = f"{_BASE_ARCHIVE}/api/GetAvailableDays/{park_code.lower()}"
        resp = self._get(url)
        raw = resp.json()

        result: Dict[str, Any] = {}
        for key, val in raw.items():
            if key in ("MinDay", "MaxDay"):
                result[key] = val
                continue
            year = int(key)
            result[str(year)] = {}
            for month_str, bitmask in val.items():
                month = int(month_str)
                days = decode_available_days_bitmask(year, month, bitmask)
                result[str(year)][str(month)] = days
        return result

    def search_archive(
        self,
        park_code: str,
        target_date: str,
        page: int = 1,
        page_size: int = 100,
        daytime_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Search the archive for images on a specific date.

        Parameters
        ----------
        park_code : str  e.g. "yose"
        target_date : str  Date in M/D/YYYY format, e.g. "3/27/2026"
        page : int  1-indexed page number
        page_size : int  Results per page (max ~300 observed)
        daytime_only : bool  If True, filter out night images client-side

        Returns
        -------
        dict with:
          UnfilteredCount   — total images on that date
          ResultCount       — images in this response
          Results           — list of records, each with Asset dict:
            Asset.AssetID           UUID used to build image URLs
            Asset.LocalTimeString   human-readable local time
            Asset.TimeOfDay         "day" | "night"
            Asset.SolarElevationAngle
            Asset.ImageCreateDateTime  UTC datetime string
        """
        payload = {
            "SearchID": None,
            "Save": False,
            "Operand": {
                "LeftOperand": {
                    "MatchType": "Exact",
                    "Term": "LocationCode",
                    "Attribute": park_code.lower(),
                },
                "RightOperand": {
                    "CompareType": "=",
                    "Term": "ImageCreateDate",
                    "Attribute": target_date,
                },
                "Operator": "AND",
            },
            "QueryID": None,
            "ActionFilter": "Search",
            "CacheResults": False,
            "RoleFilter": None,
            "SubmitterFilter": None,
            "StatusFilter": "Active",
            "SortTerms": [{"Term": "CreateDate", "Ascending": True}],
            "PageSize": page_size,
            "ResultTerms": [
                "ImageCreateDate",
                "CustomTextFields",
                "CustomNumberFields",
                "AdditionalMetadata",
            ],
            "CurrentPage": page,
            "PageCount": 0,
        }
        resp = self._post(f"{_BASE_ARCHIVE}/api/Search/Execute", json=payload)
        data = resp.json()
        if daytime_only:
            data["Results"] = [
                r for r in data.get("Results", [])
                if r.get("Asset", {}).get("TimeOfDay") == "day"
            ]
        return data

    def search_archive_range(
        self,
        park_code: str,
        start_date: str,
        end_date: str,
        page_size: int = 300,
        daytime_only: bool = False,
    ) -> Iterator[Dict[str, Any]]:
        """
        Yield search result pages for a date range (inclusive).

        Parameters
        ----------
        start_date, end_date : str  M/D/YYYY format
        """
        fmt = "%m/%d/%Y"
        current = datetime.strptime(start_date, fmt).date()
        end = datetime.strptime(end_date, fmt).date()
        while current <= end:
            date_str = f"{current.month}/{current.day}/{current.year}"
            result = self.search_archive(
                park_code, date_str, page_size=page_size, daytime_only=daytime_only
            )
            if result.get("ResultCount", 0) > 0:
                yield result
            current += timedelta(days=1)

    def get_archive_image_url(self, asset_id: str, size: str = "full") -> str:
        """
        Build the URL for a specific archived image.

        Parameters
        ----------
        asset_id : str  UUID from search_archive() results
        size : str
            "thumbnail_small"  ~1–2 KB  (thumbmedium.jpg)
            "thumbnail_large"  ~4 KB    (thumblarge.jpg)
            "full"             ~1–3 MB  full resolution JPEG
            "hires_proxy"      ~90 KB   compressed high-res proxy

        Returns
        -------
        str  direct image URL (no auth required)
        """
        token = ARCHIVE_IMAGE_SIZES.get(size, "full.jpg")
        return f"{_BASE_ARCHIVE}/GetAsset/{asset_id}/{token}"

    def get_archive_image(self, asset_id: str, size: str = "full") -> bytes:
        """Download and return an archived image as raw bytes."""
        return self._get(self.get_archive_image_url(asset_id, size)).content

    def iter_archive_images(
        self,
        park_code: str,
        target_date: str,
        size: str = "full",
        daytime_only: bool = True,
    ) -> Iterator[tuple]:
        """
        Convenience iterator: yield (local_time_string, image_bytes) for
        every archived image on a given date.

        Parameters
        ----------
        park_code : str  e.g. "yose"
        target_date : str  M/D/YYYY
        size : str  image size token (see get_archive_image_url)
        daytime_only : bool  skip night images (default True)
        """
        result = self.search_archive(
            park_code, target_date, page_size=300, daytime_only=daytime_only
        )
        for item in result.get("Results", []):
            asset = item.get("Asset", {})
            asset_id = asset.get("AssetID")
            local_time = asset.get("LocalTimeString", "")
            if asset_id:
                img = self.get_archive_image(asset_id, size)
                yield local_time, img

    def download_day_images(
        self,
        park_code: str,
        target_date: str,
        output_dir: str,
        size: str = "full",
        daytime_only: bool = True,
    ) -> List[str]:
        """
        Download all archive images for a park on one date to a local directory.

        Returns list of paths to downloaded files.
        """
        import os
        result = self.search_archive(
            park_code, target_date, page_size=300, daytime_only=daytime_only
        )
        saved = []
        for item in result.get("Results", []):
            asset = item.get("Asset", {})
            asset_id = asset.get("AssetID")
            dt_str = (
                asset.get("ImageCreateDateTime", "")
                .replace("/", "-").replace(":", "-").replace(" ", "_")
            )
            if not asset_id:
                continue
            img_bytes = self.get_archive_image(asset_id, size)
            fname = f"{park_code}_{dt_str}_{asset_id[:8]}.jpg"
            fpath = os.path.join(output_dir, fname)
            with open(fpath, "wb") as f:
                f.write(img_bytes)
            saved.append(fpath)
        return saved

    # ------------------------------------------------------------------
    # Air quality timeseries data
    # ------------------------------------------------------------------

    def get_air_quality_data(self, park_code: str) -> Dict[str, Any]:
        """
        Return the 30-day hourly air quality timeseries for a park.

        Response structure:
          name, state, dataDate,
          locations: list of monitoring location dicts, each with:
            name, aqsId, dataDate,
            ozone     — {display, units, current, current8, data (720 floats), ...}
            airTemperature, relativeHumidity, windSpeed, windDirection,
            peakWindSpeed, barometricPressure, precipitation,
            particulateMatter25 (FEM PM2.5), particulatesPA (PurpleAir PM2.5),
            smoke

        Notes
        -----
        - -99.0 is the sentinel value for missing/unavailable data.
        - Each 'data' array has 720 hourly values (30 days), oldest first.
        - Hawaii Volcanoes additionally has SO2 data.
        """
        url = f"{_BASE_CURRDATA}/json/{park_code.lower()}.json"
        resp = self._get(url, params={"uuid": _fake_uuid()})
        text = resp.content.decode("utf-8-sig")  # strip BOM if present
        return _json.loads(text)

    def get_smoke_data(self, park_code: str) -> Dict[str, Any]:
        """
        Return smoke/fire-related data (gridded PM2.5 + smoke forecast).
        Returns {"error": ..., "raw": ...} if no smoke data is available.
        """
        url = f"{_BASE_CURRDATA}/json/{park_code.lower()}_smoke.json"
        resp = self._get(url, params={"uuid": _fake_uuid()})
        try:
            return _json.loads(resp.content.decode("utf-8-sig"))
        except _json.JSONDecodeError:
            return {"error": "no smoke data available", "raw": resp.text[:500]}

    def get_air_quality_park_list(self) -> Dict[str, Any]:
        """
        Return the full air quality monitoring park list.

        Covers more parks than the webcam network (includes AQ monitoring sites
        without cameras). Each entry has monitoring location coordinates and AQS IDs.
        """
        url = f"{_BASE_CURRDATA}/json/parklist.json"
        resp = self._get(url, params={"uuid": _fake_uuid()})
        return _json.loads(resp.content.decode("utf-8-sig"))

    # ------------------------------------------------------------------
    # Convenience / bulk methods
    # ------------------------------------------------------------------

    def get_all_current_readings(self) -> List[Dict[str, Any]]:
        """
        Fetch the lightweight per-park webcam JSON for every park in the network
        and return summarised current readings.

        Each dict: park_code, name, state, imagedate, ozone_ppb, pm25_ugm3,
        pm25pa_ugm3, so2_ppb, visibility, temperature, humidity_pct,
        wind_speed, wind_direction (None if parameter not monitored/displayed)
        """
        parks = self.list_parks()
        results = []
        for park in parks:
            code = park["abbr"]
            try:
                info = self.get_park_info(code)
                reading: Dict[str, Any] = {
                    "park_code": code,
                    "name": info.get("name"),
                    "state": info.get("state"),
                    "imagedate": info.get("imagedate"),
                    "imagesite": info.get("imagesite"),
                }
                site1 = info.get("SITE1", {})
                for param, key in [
                    ("OZONE",      "ozone_ppb"),
                    ("PM25",       "pm25_ugm3"),
                    ("PM25PA",     "pm25pa_ugm3"),
                    ("SO2",        "so2_ppb"),
                    ("VISIBILITY", "visibility"),
                    ("AT",         "temperature"),
                    ("RH",         "humidity_pct"),
                    ("WS",         "wind_speed"),
                    ("WD",         "wind_direction"),
                ]:
                    block = site1.get(param, {})
                    reading[key] = (
                        block.get("hourly") if block.get("display") == "true" else None
                    )
                results.append(reading)
            except Exception as exc:
                results.append({"park_code": code, "error": str(exc)})
        return results

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        resp = self._session.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def _post(self, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        resp = self._session.post(url, **kwargs)
        resp.raise_for_status()
        return resp


# ---------------------------------------------------------------------------
# Backwards compatibility alias
# ---------------------------------------------------------------------------
# The original client class name is preserved so existing imports still work.
NPSWebcamsClient = NPSAQWebcamsClient


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

def _demo():
    """Quick demonstration of both client systems."""
    print("=" * 70)
    print("NPS Webcams — Comprehensive API Demo")
    print("=" * 70)

    # ---------------------------------------------------------------
    # SYSTEM 1: NPS Developer API
    # ---------------------------------------------------------------
    print("\n" + "─" * 70)
    print("SYSTEM 1: NPS Developer API (developer.nps.gov)")
    print("─" * 70)

    api = NPSWebcamAPIClient()

    print("\n[A1] Total webcam count")
    resp = api.list_webcams(limit=1)
    print(f"  Total webcams in NPS Developer API: {resp['total']}")

    print("\n[A2] Katmai National Park webcams (bears / streaming)")
    katm_cams = api.list_webcams(park_code="katm")
    for cam in katm_cams["data"]:
        streaming = " [STREAMING]" if cam.get("isStreaming") else ""
        img = api.get_webcam_image_url(cam)
        print(f"  {cam['title']}{streaming}")
        print(f"    ID:  {cam['id']}")
        print(f"    URL: {cam['url']}")
        if img:
            print(f"    IMG: {img}")

    print("\n[A3] Yellowstone webcams")
    yell_resp = api.list_webcams(park_code="yell")
    print(f"  Total: {yell_resp['total']}")
    for cam in yell_resp["data"][:5]:
        tag = " [STREAMING]" if cam.get("isStreaming") else f" [{cam.get('status')}]"
        lat = cam.get("latitude") or "—"
        lon = cam.get("longitude") or "—"
        print(f"  {cam['title']}{tag}  lat={lat} lon={lon}")

    print("\n[A4] Air quality webcams (NPS Developer API)")
    aq_cams = api.list_webcams(query="air quality", limit=10)
    print(f"  Found {aq_cams['total']} webcams tagged 'air quality'")
    for cam in aq_cams["data"][:5]:
        pk = cam.get("relatedParks", [{}])[0].get("parkCode", "?") if cam.get("relatedParks") else "?"
        lat = cam.get("latitude") or "—"
        lon = cam.get("longitude") or "—"
        print(f"  [{pk}] {cam['title']}  lat={lat} lon={lon}")

    print("\n[A5] Park metadata for Yosemite (yose)")
    park = api.get_park(park_code="yose")
    if park:
        print(f"  Full name:   {park['fullName']}")
        print(f"  States:      {park.get('states')}")
        print(f"  Designation: {park.get('designation')}")
        print(f"  Lat/Lon:     {park.get('latitude')}, {park.get('longitude')}")
        imgs = park.get("images", [])
        if imgs:
            print(f"  Images:      {len(imgs)} (first: {imgs[0].get('url','?')[:80]}...)")

    # ---------------------------------------------------------------
    # SYSTEM 2: ARD Air Quality Webcam Network
    # ---------------------------------------------------------------
    print("\n" + "─" * 70)
    print("SYSTEM 2: NPS Air Quality (ARD) Webcam Network")
    print("─" * 70)

    aq = NPSAQWebcamsClient()

    print("\n[B1] ARD webcam park list")
    parks = aq.list_parks()
    print(f"  {len(parks)} parks in the ARD webcam network:")
    for p in parks:
        ptype_map = {"1": "single", "2": "dual", "3": "HAVO"}
        ptype = ptype_map.get(p.get("parktype", "1"), "?")
        print(f"    {p['abbr']:6s}  {p['name']:<52s}  {p['state']:<20s}  [{ptype}]")

    print("\n[B2] Yosemite current webcam data")
    info = aq.get_park_info("yose")
    print(f"  Park:    {info['name']}")
    print(f"  View:    {info.get('imagesite')} | {info.get('viewdetail')}")
    print(f"  Updated: {info.get('imagedate')}")
    s1 = info.get("SITE1", {})
    ozone = s1.get("OZONE", {})
    if ozone.get("display") == "true":
        print(f"  Ozone:   {ozone.get('hourly')} ppb (AQI: {ozone.get('AQItext')})")
    at = s1.get("AT", {})
    if at.get("display") == "true":
        print(f"  Temp:    {at.get('hourly')} °F")

    print("\n[B3] Current image URLs for Yosemite")
    print(f"  Standard: {aq.get_current_image_url('yose')}")
    print(f"  Large:    {aq.get_current_image_url('yose', 'large')}")
    for itype in ("clear_hazy", "terrain_features", "webcam_map"):
        print(f"  {itype:<20s}: {aq.get_support_image_url('yose', itype)}")

    print("\n[B4] Archive availability for Yosemite")
    avail = aq.get_available_days("yose")
    print(f"  Data range: {avail.get('MinDay')} — {avail.get('MaxDay')}")
    for year in sorted([k for k in avail if k not in ("MinDay", "MaxDay")])[-2:]:
        for month in sorted(avail[year])[-3:]:
            days = avail[year][month]
            print(f"    {year}/{month}: {len(days)} days with images")

    today_str = datetime.now().strftime("%-m/%-d/%Y")
    print(f"\n[B5] Archive search for Yosemite on {today_str} (daytime only)")
    result = aq.search_archive("yose", today_str, daytime_only=True)
    total = result.get("UnfilteredCount", 0)
    day_imgs = result.get("Results", [])
    print(f"  Total images: {total}  (daytime: {len(day_imgs)})")
    if day_imgs:
        first = day_imgs[0]["Asset"]
        print(f"  First image: {first.get('LocalTimeString')}")
        print(f"  AssetID:     {first.get('AssetID')}")
        for sz, token in ARCHIVE_IMAGE_SIZES.items():
            url = aq.get_archive_image_url(first["AssetID"], sz)
            print(f"  URL ({sz:<16s}): {url}")

    print("\n[B6] Air quality timeseries for Yosemite")
    aq_data = aq.get_air_quality_data("yose")
    print(f"  Park:    {aq_data['name']}")
    print(f"  Updated: {aq_data.get('dataDate')}")
    for loc in aq_data.get("locations", []):
        ozone_ts = loc.get("ozone", {})
        if ozone_ts.get("display") == "true":
            non_missing = [x for x in ozone_ts.get("data", []) if x != -99.0]
            print(f"  Location: {loc['name']}")
            print(f"    Ozone current: {ozone_ts.get('current')} ppb")
            print(f"    Ozone 8h avg:  {ozone_ts.get('current8')} ppb")
            print(f"    30-day points (non-missing): {len(non_missing)}/720")

    print("\n[B7] Archive server time")
    st = aq.get_archive_server_time()
    print(f"  {st}")

    print("\nDone.")


if __name__ == "__main__":
    _demo()
