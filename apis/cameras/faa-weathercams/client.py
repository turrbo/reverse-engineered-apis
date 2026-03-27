"""
FAA WeatherCams API Client
==========================
Reverse-engineered Python client for the FAA WeatherCams system (https://weathercams.faa.gov).

All API endpoints discovered through static analysis of the React frontend JavaScript bundle
(bundle.75ff6b6298d6cc4d6af6.js) and live HTTP traffic inspection.

API Base URL: https://weathercams.faa.gov/api
Auth: No authentication required in production; requests must include a Referer header
      pointing to https://weathercams.faa.gov/ (enforced server-side).

CDN Domains:
  - Camera images:   https://images.wcams-static.faa.gov   (CloudFront → S3)
  - Clearday images: https://cleardays.wcams-static.faa.gov (CloudFront → S3)
  - Aeronav tiles:   https://aeronav.wcams-static.faa.gov   (CloudFront → S3, requires Referer)

Image URL Patterns:
  - Current/historical camera images:
      https://images.wcams-static.faa.gov/webimages/{siteId}/{dayOfMonth}/{cameraId}-{unix_ms}.jpg
  - Clearday reference image:
      https://cleardays.wcams-static.faa.gov/{cameraId}-clearday.jpg
  - Panorama frames (equirectangular tiles):
      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/{index}.jpg
  - Panorama thumbnails:
      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/thumbnail.jpg
  - Panorama small WebP:
      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/small.webp
  - Panorama medium WebP:
      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/medium.webp
  - Clearday panorama pyramid tiles:
      https://cleardays.wcams-static.faa.gov/pano/{siteId}/pyramid/{z}/{x}/{y}.jpg
  - Clearday panorama thumbnail:
      https://cleardays.wcams-static.faa.gov/pano/{siteId}/thumbnail.jpg

Discovered Endpoints (all return JSON with {"success": bool, "payload": ..., "count": int}):
  GET /api/sites                         - All camera sites (922 total)
  GET /api/sites?bounds={s},{w}|{n},{e}  - Sites filtered by bounding box
  GET /api/sites/{siteId}                - Single site detail
  GET /api/cameras                       - All cameras (3337 total)
  GET /api/cameras/{cameraId}            - Single camera detail
  GET /api/cameras/{cameraId}/images/last/{n}   - Last N images for a camera
  GET /api/cameras/{cameraId}/images/clearday    - Clear-day reference image
  GET /api/sites/{siteId}/images         - Recent images for all cameras at a site
  GET /api/sites/{siteId}/images?startDate=...&endDate=...  - Time-filtered images
  GET /api/sites/{siteId}/images/download?startDate=...&endDate=...  - Download ZIP archive
  GET /api/site-alerts                   - Active maintenance/upgrade alerts (all sites)
  GET /api/panoramas                     - All panorama-capable sites (currently 4)
  GET /api/panoramas/{panoramaSiteId}    - Single panorama site config + clearday image
  GET /api/panoramas/{panoramaSiteId}/images/last/{n}  - Last N panorama images
  GET /api/summary?stationId={icao}      - Full summary: site+cameras+METAR+TAF+NOTAMs+PIREPs+RTMA
  GET /api/summary?siteId={siteId}       - Full summary by numeric site ID
  GET /api/metars/stations/{stationId}   - METAR observations for a station (recent)
  GET /api/tafs/stations/{stationId}     - TAF forecasts for a station
  GET /api/stations/{stationId}          - Station metadata and status
  GET /api/locations?bounds={s},{w}|{n},{e}  - Combined location data (airports+sites+stations+METARs)
  GET /api/advisory-weather?bounds={s},{w}|{n},{e}  - Advisory (non-certified) weather obs
  GET /api/aircraft-reports?bounds={s},{w}|{n},{e}  - PIREPs in bounding box
  GET /api/airsigmets?bounds={s},{w}|{n},{e}  - AIRMETs/SIGMETs
  GET /api/gairmets?bounds={s},{w}|{n},{e}    - G-AIRMETs
  GET /api/rcos?bounds={s},{w}|{n},{e}        - Remote Communication Outlets (RCOs)
  GET /api/tfrs?bounds={s},{w}|{n},{e}        - Temporary Flight Restrictions

Contact for issues: 9-AJO-WCAM-IT@faa.gov
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

try:
    import requests
    from requests import Response, Session
except ImportError as e:  # pragma: no cover
    raise ImportError("requests is required: pip install requests") from e


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://weathercams.faa.gov/api"
IMAGE_CDN = "https://images.wcams-static.faa.gov"
CLEARDAY_CDN = "https://cleardays.wcams-static.faa.gov"
AERONAV_CDN = "https://aeronav.wcams-static.faa.gov"

# Required by the server-side origin check – requests without this header return 401
DEFAULT_HEADERS: Dict[str, str] = {
    "Referer": "https://weathercams.faa.gov/",
    "Origin": "https://weathercams.faa.gov",
    "User-Agent": (
        "Mozilla/5.0 (compatible; FAA-WeatherCams-PythonClient/1.0; "
        "+https://weathercams.faa.gov)"
    ),
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_bounds(south: float, west: float, north: float, east: float) -> str:
    """Return a bounds string in the format expected by the API: 'S,W|N,E'."""
    return f"{south},{west}|{north},{east}"


def _alaska_bounds() -> str:
    """Convenience: bounding box covering the entire state of Alaska."""
    return _fmt_bounds(51.2, -179.9, 71.5, -129.0)


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------


class FAAWeatherCamsClient:
    """
    Python client for the FAA WeatherCams REST API.

    All methods that accept a ``bounds`` parameter expect it either as a
    pre-formatted string ``"S,W|N,E"`` or as individual float keyword
    arguments (south, west, north, east).

    Example usage::

        from faa_weathercams_client import FAAWeatherCamsClient

        client = FAAWeatherCamsClient()

        # List all camera sites
        sites = client.list_sites()
        print(f"Total sites: {len(sites)}")

        # Sites in Alaska only
        ak_sites = client.list_sites(bounds=FAAWeatherCamsClient.alaska_bounds())

        # Get current images for site 217 (Kotzebue)
        images = client.get_site_images(217)

        # Get last 10 images for camera 10724
        history = client.get_camera_images_last(10724, n=10)

        # Full weather summary for PAOT (Kotzebue)
        summary = client.get_summary(station_id="PAOT")
        latest_metar = summary["metars"][0]["rawText"]
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        session: Optional[Session] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """
        Perform a GET request and return the parsed payload.

        Raises ``requests.HTTPError`` for 4xx/5xx responses and
        ``ValueError`` if the API returns ``success: false``.
        """
        url = f"{self.base_url}{path}"
        resp: Response = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", True):
            err = data.get("error", {})
            raise ValueError(
                f"API error {err.get('code', '?')}: {err.get('message', 'Unknown error')}"
            )
        return data.get("payload")

    def _get_raw(self, path: str, params: Optional[Dict] = None) -> Response:
        """Return the raw ``Response`` object (for binary endpoints like download)."""
        url = f"{self.base_url}{path}"
        resp: Response = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------ #
    # Convenience                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def alaska_bounds() -> str:
        """Return the bounding box string for the entire state of Alaska."""
        return _alaska_bounds()

    @staticmethod
    def make_bounds(south: float, west: float, north: float, east: float) -> str:
        """Build a bounds string ``'S,W|N,E'`` from individual coordinates."""
        return _fmt_bounds(south, west, north, east)

    # ------------------------------------------------------------------ #
    # Camera Sites                                                          #
    # ------------------------------------------------------------------ #

    def list_sites(self, bounds: Optional[str] = None) -> List[Dict]:
        """
        Return all FAA WeatherCam sites (922 as of March 2026).

        Each site dict includes:
          siteId, siteName, siteArea, siteIdentifier (FAA ID), icao,
          latitude, longitude, elevation, state, country, timeZone,
          siteInMaintenance, siteActive, thirdParty, validated,
          sunrise, sunset, wxsrc, wxTable, displayVeia, cameras (list)

        Parameters
        ----------
        bounds : str, optional
            Restrict results to a geographic bounding box ``'S,W|N,E'``.
            Use :meth:`make_bounds` or :meth:`alaska_bounds` to build this.
        """
        params: Dict = {}
        if bounds:
            params["bounds"] = bounds
        result = self._get("/sites", params=params or None)
        return result if isinstance(result, list) else []

    def get_site(self, site_id: int) -> Dict:
        """Return metadata and camera list for a single site by its numeric ID."""
        return self._get(f"/sites/{site_id}")

    def list_sites_alaska(self) -> List[Dict]:
        """Shortcut: return all WeatherCam sites in Alaska."""
        return self.list_sites(bounds=_alaska_bounds())

    # ------------------------------------------------------------------ #
    # Cameras                                                               #
    # ------------------------------------------------------------------ #

    def list_cameras(self) -> List[Dict]:
        """
        Return all individual cameras across all sites (3337 as of March 2026).

        Each camera dict includes:
          cameraId, cameraName, cameraDirection, cameraBearing,
          cameraLastSuccess, cameraInMaintenance, cameraOutOfOrder,
          siteId, displayOrder, enableVeia, veiaProcessType,
          mapWedgeAngle, latitude, longitude
        """
        result = self._get("/cameras")
        return result if isinstance(result, list) else []

    def get_camera(self, camera_id: int) -> Dict:
        """Return metadata for a single camera by its numeric ID."""
        return self._get(f"/cameras/{camera_id}")

    # ------------------------------------------------------------------ #
    # Camera Images                                                         #
    # ------------------------------------------------------------------ #

    def get_camera_images_last(self, camera_id: int, n: int = 1) -> List[Dict]:
        """
        Return the last ``n`` images captured by a camera.

        Each image dict includes:
          cameraId, imageFilename, imageUri (CDN URL), imageDatetime

        The ``imageUri`` points to:
          https://images.wcams-static.faa.gov/webimages/{siteId}/{dayOfMonth}/{cameraId}-{unix_ms}.jpg

        Parameters
        ----------
        camera_id : int
            Numeric camera ID.
        n : int
            Number of most-recent images to retrieve (default 1, practical
            max appears to be ~96 i.e. ~8 hours at ~5-minute intervals).
        """
        result = self._get(f"/cameras/{camera_id}/images/last/{n}")
        return result if isinstance(result, list) else []

    def get_camera_clearday_image(self, camera_id: int) -> Dict:
        """
        Return the clear-day reference image for a camera.

        Returns a dict with: cameraId, imageUri, imageFilename

        The ``imageUri`` points to:
          https://cleardays.wcams-static.faa.gov/{cameraId}-clearday.jpg
        """
        return self._get(f"/cameras/{camera_id}/images/clearday")

    def get_site_images(
        self,
        site_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Return recent images for all cameras at a site (most-recent first).

        Parameters
        ----------
        site_id : int
            Numeric site ID.
        start_date : datetime, optional
            Filter to images on or after this UTC datetime.
        end_date : datetime, optional
            Filter to images on or before this UTC datetime.
        """
        params: Dict = {}
        if start_date:
            params["startDate"] = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_date:
            params["endDate"] = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        result = self._get(f"/sites/{site_id}/images", params=params or None)
        return result if isinstance(result, list) else []

    def download_site_images(
        self,
        site_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> bytes:
        """
        Download a ZIP archive of images for all cameras at a site.

        The archive structure is:
          {siteName}/{date}/{cameraId}/{HH-MM-SS.mmmZ}.jpg

        Parameters
        ----------
        site_id : int
            Numeric site ID.
        start_date : datetime, optional
            Filter to images on or after this UTC datetime.
        end_date : datetime, optional
            Filter to images on or before this UTC datetime.

        Returns
        -------
        bytes
            Raw ZIP file bytes. Use ``zipfile.ZipFile(io.BytesIO(data))`` to
            extract.
        """
        params: Dict = {}
        if start_date:
            params["startDate"] = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end_date:
            params["endDate"] = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = self._get_raw(f"/sites/{site_id}/images/download", params=params or None)
        return resp.content

    def extract_site_images_zip(
        self,
        site_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> zipfile.ZipFile:
        """Download and open the site images archive as a ``ZipFile`` object."""
        raw = self.download_site_images(site_id, start_date, end_date)
        return zipfile.ZipFile(io.BytesIO(raw))

    # ------------------------------------------------------------------ #
    # Site Alerts                                                           #
    # ------------------------------------------------------------------ #

    def list_site_alerts(self) -> List[Dict]:
        """
        Return all active site maintenance / upgrade alerts.

        Each alert dict includes:
          siteId, siteAlertId, title, alert (HTML), link,
          effectiveDate, expiredDate
        """
        result = self._get("/site-alerts")
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------ #
    # Panoramic Cameras                                                     #
    # ------------------------------------------------------------------ #

    def list_panoramas(self) -> List[Dict]:
        """
        Return all sites with 360-degree panoramic cameras (4 as of March 2026).

        Each panorama dict includes:
          panoramaSiteId, siteId, siteInMaintenance, siteActive,
          northOffset, defaultYaw, defaultHfov, minHfov, maxHfov,
          maxZoomLevel, minPitch, maxPitch, hotspots (list),
          cubeResolution, clearDayImage (pyramid URLs)
        """
        result = self._get("/panoramas")
        return result if isinstance(result, list) else []

    def get_panorama(self, panorama_site_id: int) -> Dict:
        """
        Return configuration and clear-day image URLs for a panorama site.

        The clearDayImage contains:
          imageType: "pyramid"
          imageUris.pyramid: https://cleardays.wcams-static.faa.gov/pano/{siteId}/pyramid
          imageUris.thumbnail: https://cleardays.wcams-static.faa.gov/pano/{siteId}/thumbnail.jpg
          timestamp: ISO 8601 datetime of the clear-day image
        """
        return self._get(f"/panoramas/{panorama_site_id}")

    def get_panorama_images_last(self, panorama_site_id: int, n: int = 1) -> List[Dict]:
        """
        Return the last ``n`` panoramic images for a panorama site.

        Each image dict includes:
          panoramaSiteId, imageId, imageType ("equirectangular"),
          timestamp, imageUris (small/medium/thumbnail), resourceUris.src (list of tile JPEGs)

        Image URIs follow these patterns:
          thumbnail:  https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/thumbnail.jpg
          small:      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/small.webp
          medium:     https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/medium.webp
          tiles:      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/0.jpg
                      https://images.wcams-static.faa.gov/pano/{siteId}/{unix_ms}/1.jpg
                      ... (typically 4 tiles)
        """
        result = self._get(f"/panoramas/{panorama_site_id}/images/last/{n}")
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------ #
    # Weather Summary (the "details" view)                                 #
    # ------------------------------------------------------------------ #

    def get_summary(
        self,
        station_id: Optional[str] = None,
        site_id: Optional[int] = None,
    ) -> Dict:
        """
        Return a comprehensive weather summary for a location.

        Exactly one of ``station_id`` or ``site_id`` must be provided.

        Parameters
        ----------
        station_id : str, optional
            ICAO identifier (e.g. ``"PAOT"`` for Kotzebue, Alaska).
            Used for sites that have an associated METAR station.
        site_id : int, optional
            Numeric FAA WeatherCam site ID.

        Returns a dict with top-level keys:
          site:           {site (metadata), alerts, advisoryWeather, cameras
                           (with currentImages), visibilities, observations}
          airport:        Airport facility info + chart supplements
          rtmaReports:    Real-Time Mesoscale Analysis temperature/altimeter data (list)
          station:        METAR/TAF station metadata and service status
          metars:         Recent METAR observations (list, newest first)
          notams:         Active NOTAMs for the station (list)
          tafs:           Active TAFs for the station (list)
          rco:            Remote Communication Outlet frequencies
          aircraftReports: Recent PIREPs near the location (list)
          timeZoneId:     IANA timezone string

        The ``visibilities`` list contains VEIA (Visibility Estimation from
        Image Analysis) observations – FAA automated, advisory-grade.

        METAR ``flightCategory`` values: ``"VFR"``, ``"MVFR"``, ``"IFR"``, ``"LIFR"``
        """
        if station_id is None and site_id is None:
            raise ValueError("Provide either station_id or site_id")
        if station_id and site_id:
            raise ValueError("Provide only one of station_id or site_id")
        params: Dict = {}
        if station_id:
            params["stationId"] = station_id.upper()
        else:
            params["siteId"] = site_id
        return self._get("/summary", params=params)

    # ------------------------------------------------------------------ #
    # METAR / TAF                                                           #
    # ------------------------------------------------------------------ #

    def get_metars(self, station_id: str) -> List[Dict]:
        """
        Return recent METAR observations for an ICAO station.

        Each METAR dict includes:
          metarId, rawText, stationId, observationDateTime,
          latitude, longitude, tempC, dewpointC, windDirDegrees,
          windSpeedKnots, windGustKnots, visibilityStatuteMiles,
          altimInHg, seaLevelPressureMb, wxString, skyCondition (list),
          flightCategory, ceilingFtAgl, metarType, elevationM,
          fetchTime, parsed (human-readable version)

        Parameters
        ----------
        station_id : str
            ICAO station identifier (e.g. ``"PAOT"``, ``"PAFA"``, ``"PANC"``).
        """
        result = self._get(f"/metars/stations/{station_id.upper()}")
        return result if isinstance(result, list) else []

    def get_tafs(self, station_id: str) -> List[Dict]:
        """
        Return active TAF forecasts for an ICAO station.

        Each TAF dict includes:
          tafId, rawText, stationId, stationName, issueTime,
          bulletinTime, validTimeFrom, validTimeTo, remarks,
          latitude, longitude, elevationM,
          forecast (list of forecast periods with flightCategory),
          parsed (human-readable)

        Parameters
        ----------
        station_id : str
            ICAO station identifier.
        """
        result = self._get(f"/tafs/stations/{station_id.upper()}")
        return result if isinstance(result, list) else []

    def get_station(self, station_id: str) -> Dict:
        """
        Return metadata and service status for a METAR station.

        Includes: stationId, stationName, faaId, icaoId, iataId, wmoId,
          latitude, longitude, elevationM, state, country,
          siteType (list: ["METAR", "TAF"]), facilityType, status
        """
        return self._get(f"/stations/{station_id.upper()}")

    # ------------------------------------------------------------------ #
    # Map Layer Endpoints (bounding-box queries)                           #
    # ------------------------------------------------------------------ #

    def get_locations(self, bounds: str) -> List[Dict]:
        """
        Return combined location data for a geographic bounding box.

        Each location contains a ``data`` list that may include entries of
        types: ``"airport"``, ``"cameraSite"``, ``"station"``, ``"rco"``,
        ``"metar"``.  This is the data used to render the interactive map.

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
            Example: ``"55,-165|72,-135"`` covers most of Alaska.
        """
        result = self._get("/locations", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    def get_advisory_weather(self, bounds: str) -> List[Dict]:
        """
        Return advisory (non-certified, non-aviation-grade) weather observations.

        These come from the FAA's third-party weather sensors co-located with
        camera sites.  Each observation includes:
          notice (disclaimer text), siteId, observationDateTime,
          windDirDegrees, windSpeedKnots, tempF, relativeHumidity,
          altimInHg, rainIn, hailIn, fetchDateTime

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
        """
        result = self._get("/advisory-weather", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    def get_aircraft_reports(self, bounds: str) -> List[Dict]:
        """
        Return PIREPs (pilot weather reports) within a bounding box.

        Each report includes:
          aircraftReportId, rawText, receiptTime, observationTime,
          aircraftRef, latitude, longitude, reportType,
          altitudeFtMsl, skyCondition, turbulenceCondition,
          icingCondition, visibilityStatuteMi, wxString, tempC,
          windDirDegrees, windSpeedKt, vertGustKt, parsed

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
        """
        result = self._get("/aircraft-reports", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    def get_airsigmets(self, bounds: str) -> List[Dict]:
        """
        Return AIRMETs and SIGMETs within a bounding box.

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
        """
        result = self._get("/airsigmets", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    def get_gairmets(self, bounds: str) -> List[Dict]:
        """
        Return G-AIRMETs (graphical AIRMETs) within a bounding box.

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
        """
        result = self._get("/gairmets", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    def get_rcos(self, bounds: str) -> List[Dict]:
        """
        Return Remote Communication Outlets (RCOs) within a bounding box.

        Each RCO includes:
          rcoId, rcoIdentifier, rcoName, latitude, longitude, frequencies (list of MHz)

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
        """
        result = self._get("/rcos", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    def get_tfrs(self, bounds: str) -> List[Dict]:
        """
        Return active Temporary Flight Restrictions within a bounding box.

        Parameters
        ----------
        bounds : str
            Bounding box in ``'S,W|N,E'`` format.
        """
        result = self._get("/tfrs", params={"bounds": bounds})
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------ #
    # Image URL Builders (construct CDN URLs without API calls)            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_image_url(site_id: int, camera_id: int, unix_ms: int) -> str:
        """
        Build a camera image CDN URL directly from its components.

        Parameters
        ----------
        site_id : int
            The numeric site ID (e.g. 142 for Old Harbor, AK).
        camera_id : int
            The numeric camera ID (e.g. 10415).
        unix_ms : int
            The Unix timestamp in milliseconds extracted from the filename
            (e.g. 1774629011348).

        Returns
        -------
        str
            Full CDN URL:
            ``https://images.wcams-static.faa.gov/webimages/{siteId}/{day}/{cameraId}-{unix_ms}.jpg``

        Note
        ----
        The ``day`` component in the URL path is the UTC day-of-month (1–31)
        derived from the timestamp.
        """
        day = datetime.fromtimestamp(unix_ms / 1000, tz=timezone.utc).day
        return f"{IMAGE_CDN}/webimages/{site_id}/{day}/{camera_id}-{unix_ms}.jpg"

    @staticmethod
    def build_clearday_url(camera_id: int) -> str:
        """Build the CDN URL for a camera's clear-day reference image."""
        return f"{CLEARDAY_CDN}/{camera_id}-clearday.jpg"

    @staticmethod
    def build_pano_thumbnail_url(site_id: int, unix_ms: int) -> str:
        """Build the CDN URL for a panorama thumbnail JPEG."""
        return f"{IMAGE_CDN}/pano/{site_id}/{unix_ms}/thumbnail.jpg"

    @staticmethod
    def build_pano_tile_url(site_id: int, unix_ms: int, tile_index: int) -> str:
        """
        Build the CDN URL for a panorama equirectangular tile JPEG.

        Panoramas consist of 4 tiles (indices 0–3).
        """
        return f"{IMAGE_CDN}/pano/{site_id}/{unix_ms}/{tile_index}.jpg"

    @staticmethod
    def build_clearday_pano_thumbnail_url(site_id: int) -> str:
        """Build the CDN URL for a site's clear-day panorama thumbnail."""
        return f"{CLEARDAY_CDN}/pano/{site_id}/thumbnail.jpg"

    @staticmethod
    def build_clearday_pano_pyramid_url(site_id: int) -> str:
        """
        Build the base URL for a site's clear-day panorama pyramid tile set.

        Append ``/{z}/{x}/{y}.jpg`` for individual tiles.
        """
        return f"{CLEARDAY_CDN}/pano/{site_id}/pyramid"

    # ------------------------------------------------------------------ #
    # High-level convenience methods                                        #
    # ------------------------------------------------------------------ #

    def get_current_conditions(self, station_id: str) -> Dict:
        """
        Return a concise current-conditions summary for a METAR station.

        Pulls from the full summary and returns a flat dict with:
          station_id, site_name, latitude, longitude, elevation_ft,
          time_zone, flight_category, metar_raw, ceiling_ft, visibility_sm,
          temp_c, dewpoint_c, wind_dir, wind_speed_kt, wind_gust_kt,
          altimeter_inhg, wx_string, sky_condition,
          veia_visibility_sm, veia_sky_cover, veia_confidence,
          taf_raw (most recent)
        """
        summary = self.get_summary(station_id=station_id)
        site_meta = summary.get("site", {}).get("site", {})
        metars = summary.get("metars", [])
        tafs = summary.get("tafs", [])
        vis = summary.get("site", {}).get("visibilities", [])

        metar = metars[0] if metars else {}
        taf = tafs[0] if tafs else {}
        latest_vis = vis[0] if vis else {}

        return {
            "station_id": station_id.upper(),
            "site_name": site_meta.get("siteName"),
            "latitude": site_meta.get("latitude"),
            "longitude": site_meta.get("longitude"),
            "elevation_ft": (
                round(site_meta.get("elevation", 0) * 3.28084)
                if site_meta.get("elevation") is not None
                else None
            ),
            "time_zone": summary.get("timeZoneId"),
            "flight_category": metar.get("flightCategory"),
            "metar_raw": metar.get("rawText"),
            "ceiling_ft": metar.get("ceilingFtAgl"),
            "visibility_sm": metar.get("visibilityStatuteMiles"),
            "temp_c": metar.get("tempC"),
            "dewpoint_c": metar.get("dewpointC"),
            "wind_dir": metar.get("windDirDegrees"),
            "wind_speed_kt": metar.get("windSpeedKnots"),
            "wind_gust_kt": metar.get("windGustKnots"),
            "altimeter_inhg": metar.get("altimInHg"),
            "wx_string": metar.get("wxString"),
            "sky_condition": metar.get("skyCondition"),
            "veia_visibility_sm": latest_vis.get("visibilityStatuteMi"),
            "veia_sky_cover": (
                latest_vis.get("skyCondition", {}).get("skyCover")
                if latest_vis
                else None
            ),
            "veia_confidence": latest_vis.get("confidence"),
            "taf_raw": taf.get("rawText"),
        }

    def get_alaska_camera_sites(self) -> List[Dict]:
        """Return all WeatherCam sites in Alaska with their camera lists."""
        all_sites = self.list_sites()
        return [s for s in all_sites if s.get("state") == "AK"]

    def get_latest_image_for_site(self, site_id: int) -> List[Dict]:
        """Return the single most-recent image from each camera at a site."""
        site = self.get_site(site_id)
        cameras = site.get("cameras", [])
        results = []
        for cam in cameras:
            images = self.get_camera_images_last(cam["cameraId"], n=1)
            if images:
                img = images[0].copy()
                img["cameraName"] = cam.get("cameraName")
                img["cameraDirection"] = cam.get("cameraDirection")
                img["cameraBearing"] = cam.get("cameraBearing")
                results.append(img)
        return results

    def search_sites_by_name(self, query: str) -> List[Dict]:
        """
        Search all sites by name (case-insensitive substring match).

        Parameters
        ----------
        query : str
            Search string to match against ``siteName`` and ``siteArea``.
        """
        q = query.lower()
        return [
            s
            for s in self.list_sites()
            if q in s.get("siteName", "").lower()
            or q in s.get("siteArea", "").lower()
        ]

    def get_sites_with_metar(self) -> List[Dict]:
        """Return all sites that have an associated ICAO METAR station."""
        return [s for s in self.list_sites() if s.get("icao")]

    def get_sites_with_panorama(self, panoramas: Optional[List[Dict]] = None) -> List[int]:
        """
        Return the list of site IDs that have panoramic cameras.

        Parameters
        ----------
        panoramas : list, optional
            Pre-fetched panorama list. If not provided, calls :meth:`list_panoramas`.
        """
        if panoramas is None:
            panoramas = self.list_panoramas()
        return [p["siteId"] for p in panoramas]


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------


def download_image(url: str, session: Optional[Session] = None) -> bytes:
    """
    Download a camera image (JPEG) directly from the CDN.

    Parameters
    ----------
    url : str
        Full CDN URL returned in an ``imageUri`` field.
    session : requests.Session, optional
        Reuse an existing session for connection pooling.

    Returns
    -------
    bytes
        Raw JPEG image bytes.
    """
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", DEFAULT_HEADERS["User-Agent"])
    resp = s.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def parse_image_uri(image_uri: str) -> Dict[str, Any]:
    """
    Parse a camera image URI into its component parts.

    Parameters
    ----------
    image_uri : str
        A URI like:
        ``https://images.wcams-static.faa.gov/webimages/142/27/10415-1774629011348.jpg``

    Returns
    -------
    dict
        Keys: site_id (int), day_of_month (int), camera_id (int),
              unix_ms (int), capture_time (datetime)
    """
    # e.g. /webimages/142/27/10415-1774629011348.jpg
    path = image_uri.split("wcams-static.faa.gov")[-1]
    parts = path.strip("/").split("/")
    if len(parts) < 4 or parts[0] != "webimages":
        raise ValueError(f"Unexpected image URI format: {image_uri!r}")
    site_id = int(parts[1])
    day_of_month = int(parts[2])
    filename = parts[3]  # e.g. "10415-1774629011348.jpg"
    name_no_ext = filename.rsplit(".", 1)[0]
    cam_str, ms_str = name_no_ext.split("-", 1)
    camera_id = int(cam_str)
    unix_ms = int(ms_str)
    capture_time = datetime.fromtimestamp(unix_ms / 1000, tz=timezone.utc)
    return {
        "site_id": site_id,
        "day_of_month": day_of_month,
        "camera_id": camera_id,
        "unix_ms": unix_ms,
        "capture_time": capture_time,
    }


# ---------------------------------------------------------------------------
# Example / quick-start demo
# ---------------------------------------------------------------------------


def demo() -> None:
    """Run a quick demonstration of the client against the live API."""
    client = FAAWeatherCamsClient()

    print("=" * 60)
    print("FAA WeatherCams API Client Demo")
    print("=" * 60)

    # 1. Total site count
    sites = client.list_sites()
    print(f"\n[1] Total WeatherCam sites: {len(sites)}")

    # 2. Alaska sites
    ak_sites = client.get_alaska_camera_sites()
    print(f"[2] Alaska sites: {len(ak_sites)}")
    if ak_sites:
        sample = ak_sites[0]
        print(
            f"    Sample: {sample['siteName']} (ID={sample['siteId']}, "
            f"lat={sample['latitude']}, lon={sample['longitude']})"
        )

    # 3. Current conditions at Kotzebue (PAOT)
    print("\n[3] Current conditions at Kotzebue, AK (PAOT):")
    try:
        conds = client.get_current_conditions("PAOT")
        print(f"    Flight category : {conds['flight_category']}")
        print(f"    Ceiling         : {conds['ceiling_ft']} ft")
        print(f"    Visibility      : {conds['visibility_sm']} SM")
        print(f"    Temperature     : {conds['temp_c']} °C")
        print(f"    Wind            : {conds['wind_dir']}° @ {conds['wind_speed_kt']} kt")
        print(f"    VEIA visibility : {conds['veia_visibility_sm']} SM "
              f"(confidence {conds['veia_confidence']}%)")
        print(f"    METAR           : {conds['metar_raw']}")
    except Exception as exc:
        print(f"    (error: {exc})")

    # 4. Camera images for Kotzebue
    print("\n[4] Recent images at Kotzebue (site 217):")
    try:
        images = client.get_site_images(217)
        for img in images[:3]:
            print(f"    cam={img['cameraId']} t={img['imageDatetime']} -> {img['imageUri']}")
    except Exception as exc:
        print(f"    (error: {exc})")

    # 5. Alaska bounding box advisory weather count
    print("\n[5] Advisory weather observations in Alaska:")
    try:
        wx = client.get_advisory_weather(client.alaska_bounds())
        print(f"    Count: {len(wx)}")
        if wx:
            sample_wx = wx[0]
            print(
                f"    Sample: siteId={sample_wx['siteId']}, "
                f"wind={sample_wx['windDirDegrees']}°/{sample_wx['windSpeedKnots']}kt, "
                f"temp={sample_wx['tempF']}°F"
            )
    except Exception as exc:
        print(f"    (error: {exc})")

    # 6. Panorama sites
    print("\n[6] Panorama-capable sites:")
    try:
        panos = client.list_panoramas()
        for p in panos:
            print(f"    panoramaSiteId={p['panoramaSiteId']}, siteId={p['siteId']}")
    except Exception as exc:
        print(f"    (error: {exc})")

    print("\nDone.")


if __name__ == "__main__":
    demo()
