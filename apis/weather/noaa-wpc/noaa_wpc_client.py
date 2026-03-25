#!/usr/bin/env python3
"""
NOAA Weather Prediction Center (WPC) API Client
================================================
Reverse-engineered client for https://www.wpc.ncep.noaa.gov/

The WPC provides national weather forecasts, analyses, and guidance products
for the contiguous United States (CONUS), Alaska, Hawaii, and Puerto Rico.

All data is PUBLIC -- no authentication required.

Discovered endpoints (as of March 2026):
  - Surface analysis maps (GIF, 3-hourly)
  - QPF (Quantitative Precipitation Forecast) maps (GIF)
  - National Forecast Charts (PNG/GIF/PDF)
  - Excessive Rainfall Outlooks (GIF images + GeoJSON + KMZ)
  - Winter Weather products (WSSI, PWPF probabilities)
  - Medium Range forecast maps
  - Text discussions (Short Range, Extended, QPF, etc.)
  - Mesoscale Precipitation Discussions (MPDs)
  - National Flood Outlook (PNG + GeoJSON)
  - Heat Index forecasts
  - KML/KMZ products
  - FTP shapefiles
  - NationalForecastChart mapdata JSON (fronts, QPF polygons, ERO, snow, etc.)
  - ArcGIS MapServer layers (WPC precip hazards)
  - MPD RSS feed
"""

from __future__ import annotations

import re
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    raise ImportError("Please install requests: pip install requests")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.wpc.ncep.noaa.gov"
FTP_BASE  = "https://ftp-wpc.ncep.noaa.gov"

# ArcGIS MapServer -- WPC Precipitation Hazards (ERO layers)
ARCGIS_BASE = (
    "https://mapservices.weather.noaa.gov/vector/rest/services/"
    "hazards/wpc_precip_hazards/MapServer"
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0 "
    "noaa-wpc-client/1.0 (+https://github.com/example/noaa-wpc-client)"
)

# Discussion type codes -> human-readable names
DISCUSSION_TYPES: Dict[str, str] = {
    "pmdspd":  "Short Range Public Discussion",
    "pmdepd":  "Extended Forecast Discussion",
    "pmdak":   "Alaska Public Discussion",
    "pmdhi":   "Hawaii Public Discussion",
    "nathilo": "National High/Low Synopsis",
    "qpferd":  "Excessive Rainfall Discussion",
    "qpfhsd":  "Hazardous Weather Outlook",
    "fxsa20":  "Pacific Public Discussion (FXSA20)",
    "fxsa21":  "Pacific Extended Discussion (FXSA21)",
    "fxca20":  "Caribbean Discussion (FXCA20)",
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _synoptic_hours() -> List[int]:
    """Return standard synoptic hours 00, 03, 06, 09, 12, 15, 18, 21."""
    return [0, 3, 6, 9, 12, 15, 18, 21]


def _latest_synoptic(dt: Optional[datetime] = None) -> Tuple[datetime, int]:
    """Return the (date, synoptic_hour) for the most recent 3-hourly analysis."""
    if dt is None:
        dt = _now_utc()
    hour = dt.hour
    synoptic = (hour // 3) * 3
    return dt.replace(hour=synoptic, minute=0, second=0, microsecond=0), synoptic


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class WPCClient:
    """
    Client for the NOAA Weather Prediction Center (WPC) website.

    All methods that download files write to *output_dir* (default: current
    directory).  Methods that return data return Python objects (str, dict,
    bytes).

    Usage::

        client = WPCClient(output_dir="/tmp/wpc_data")
        # Download today's Day-1 national forecast chart
        path = client.download_national_forecast_chart(day=1)
        # Get the short-range public discussion text
        text = client.get_discussion(disc_type="pmdspd")
        # Download Day-1 QPF map
        path = client.download_qpf_image(day=1)
    """

    def __init__(
        self,
        output_dir: str = ".",
        timeout: int = 30,
        verify_ssl: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        self.session.verify = verify_ssl

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET with timeout; raise on HTTP errors."""
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def _save(self, data: bytes, filename: str) -> Path:
        """Save bytes to output_dir/filename and return the path."""
        path = self.output_dir / filename
        path.write_bytes(data)
        return path

    def _url(self, path: str) -> str:
        """Build an absolute URL from a path relative to BASE_URL."""
        return urljoin(BASE_URL, path)

    # -----------------------------------------------------------------------
    # Surface Analysis
    # -----------------------------------------------------------------------

    def download_surface_analysis(
        self,
        synoptic_hour: Optional[int] = None,
        region: str = "us",
        style: str = "wbg",
    ) -> Path:
        """
        Download a current surface analysis map.

        Parameters
        ----------
        synoptic_hour:
            Analysis hour (0, 3, 6, 9, 12, 15, 18, 21 UTC).
            If None, uses the most recent synoptic hour.
        region:
            One of:
              "us"  - CONUS (namussfcHHwbg.gif)
              "ak"  - Alaska (namaksfc...)
              "ak2" - Alaska large (namak2sfc...)
              "cc"  - Central America (namccsfc...)
              "sw"  - South America (namswsfc...)
        style:
            "wbg" (color, default) or "bw" (black & white)

        Returns
        -------
        Path to the downloaded GIF.

        Examples
        --------
        Current color CONUS analysis:
            client.download_surface_analysis()
        00Z analysis:
            client.download_surface_analysis(synoptic_hour=0)
        Alaska analysis:
            client.download_surface_analysis(region="ak")
        """
        if synoptic_hour is None:
            _, synoptic_hour = _latest_synoptic()

        hour_str = f"{synoptic_hour:02d}"

        # Map region codes to filename prefixes
        prefix_map = {
            "us":  "namus",
            "ak":  "namak",
            "ak2": "namak2",
            "cc":  "namcc",
            "sw":  "namsws",
        }
        prefix = prefix_map.get(region, "namus")
        filename_base = f"{prefix}sfc{hour_str}{style}.gif"
        url = self._url(f"/sfc/{filename_base}")
        resp = self._get(url)
        return self._save(resp.content, filename_base)

    def download_surface_analysis_with_fronts(
        self,
        synoptic_hour: Optional[int] = None,
        style: str = "wbg",
    ) -> Path:
        """
        Download the CONUS surface analysis map with fronts overlay.

        Filename pattern: usfntsfc{HH}{style}.gif
        """
        if synoptic_hour is None:
            _, synoptic_hour = _latest_synoptic()
        hour_str = f"{synoptic_hour:02d}"
        filename = f"usfntsfc{hour_str}{style}.gif"
        url = self._url(f"/sfc/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_archived_surface_analysis(
        self,
        date: datetime,
        synoptic_hour: int,
        region: str = "us",
    ) -> Path:
        """
        Download an archived surface analysis map.

        Archives go back to 2006 (CONUS), with hourly coverage at 00/03/06/09/12/15/18/21Z.

        Parameters
        ----------
        date:
            The date of the analysis.
        synoptic_hour:
            Analysis hour (0, 3, 6, 9, 12, 15, 18, 21 UTC).
        region:
            "us" or "fnt" (fronts version)

        URL pattern:
            /archives/sfc/{YYYY}/namussfc{YYYYMMDD}{HH}.gif
        """
        year = date.strftime("%Y")
        date_str = date.strftime("%Y%m%d")
        hour_str = f"{synoptic_hour:02d}"

        if region == "fnt":
            filename = f"namfntsfc{date_str}{hour_str}.gif"
        else:
            filename = f"namussfc{date_str}{hour_str}.gif"

        url = self._url(f"/archives/sfc/{year}/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # QPF (Quantitative Precipitation Forecast)
    # -----------------------------------------------------------------------

    def download_qpf_image(
        self,
        day: int = 1,
        filled: bool = True,
    ) -> Path:
        """
        Download a QPF (precipitation forecast) image.

        Parameters
        ----------
        day:
            Forecast day (1-7).
        filled:
            If True, use the color-filled version (default).

        QPF image URL patterns (24-hour daily totals)
        ----------------------------------------------
        Day 1 (24hr):         /qpf/fill_94qwbg.gif   (filled)  | /qpf/94qwbg.gif
        Day 2 (24hr):         /qpf/fill_98qwbg.gif   (filled)  | /qpf/98qwbg.gif
        Day 3 (24hr):         /qpf/fill_99qwbg.gif   (filled)  | /qpf/99qwbg.gif
        Day 4 (24hr):         /qpf/day4p24iwbg_fill.gif
        Day 5 (24hr):         /qpf/day5p24iwbg_fill.gif
        Day 6 (24hr):         /qpf/day6p24iwbg_fill.gif
        Day 7 (24hr):         /qpf/day7p24iwbg_fill.gif
        Days 1-2 (48hr total): /qpf/d12_fill.gif
        Days 1-3 (72hr total): /qpf/d13_fill.gif
        Days 1-5 (5-day total): /qpf/p120i.gif
        Days 1-7 (7-day total): /qpf/p168i.gif
        """
        if day == 1:
            filename = "fill_94qwbg.gif" if filled else "94qwbg.gif"
        elif day == 2:
            filename = "fill_98qwbg.gif" if filled else "98qwbg.gif"
        elif day == 3:
            filename = "fill_99qwbg.gif" if filled else "99qwbg.gif"
        elif day in (4, 5, 6, 7):
            fill_suffix = "iwbg_fill" if filled else "iwbg"
            filename = f"day{day}p24{fill_suffix}.gif"
        else:
            raise ValueError(f"day must be 1-7, got {day}")

        url = self._url(f"/qpf/{filename}")
        resp = self._get(url)
        return self._save(resp.content, f"qpf_day{day}.gif")

    def download_qpf_multiday(
        self,
        days: int = 2,
        filled: bool = True,
    ) -> Path:
        """
        Download a multi-day QPF total image.

        Parameters
        ----------
        days:
            2 (48hr, Days 1-2), 3 (72hr, Days 1-3)

        URL patterns:
          Days 1-2 (48hr): /qpf/d12_fill.gif
          Days 1-3 (72hr): /qpf/d13_fill.gif
        """
        if days == 2:
            filename = "d12_fill.gif" if filled else "d12_wbg.gif"
        elif days == 3:
            filename = "d13_fill.gif" if filled else "d13_wbg.gif"
        else:
            raise ValueError(f"days must be 2 or 3, got {days}")
        url = self._url(f"/qpf/{filename}")
        resp = self._get(url)
        return self._save(resp.content, f"qpf_{days}day_total.gif")

    def download_qpf_total(self, days: int = 5) -> Path:
        """
        Download the multi-day accumulated QPF total map.

        Parameters
        ----------
        days: 5 (120hr) or 7 (168hr)
        """
        if days == 5:
            filename = "p120i.gif"
        elif days == 7:
            filename = "p168i.gif"
        else:
            raise ValueError("days must be 5 or 7")
        url = self._url(f"/qpf/{filename}")
        resp = self._get(url)
        return self._save(resp.content, f"qpf_total_{days}day.gif")

    def download_qpf_hourly(
        self,
        init_time: datetime,
        forecast_hour: int,
        period_hours: int = 12,
    ) -> Path:
        """
        Download a 6-hour or 12-hour QPF image using the dated naming scheme.

        URL pattern: /qpf/hpcqpf_{YYYYMMDD}{HH}_{period}hr_f{FFF}.gif

        Parameters
        ----------
        init_time:
            Model initialization time (UTC).
        forecast_hour:
            Forecast hour (012, 018, 024, ..., 072).
        period_hours:
            6 or 12 (hour accumulation period).

        Example
        -------
        Download 12hr QPF valid at f024 from 00Z initialization:
            client.download_qpf_hourly(datetime(2026,3,25,0), 24, 12)
        """
        date_str = init_time.strftime("%Y%m%d%H")
        filename = f"hpcqpf_{date_str}_{period_hours}hr_f{forecast_hour:03d}.gif"
        url = self._url(f"/qpf/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # Excessive Rainfall Outlook (ERO)
    # -----------------------------------------------------------------------

    def download_ero_image(self, day: int = 1) -> Path:
        """
        Download an Excessive Rainfall Outlook (ERO) map image.

        Parameters
        ----------
        day: 1, 2, 3, 4, or 5

        URL patterns:
          Day 1:       /qpf/94ewbg.gif
          Day 2:       /qpf/98ewbg.gif   (Days 1-until: /qpf/95ep48iwbg_fill.gif)
          Day 3:       /qpf/99ewbg.gif
          Day 4:       /qpf/ero_d45/images/d4wbg.gif
          Day 5:       /qpf/ero_d45/images/d5wbg.gif
        """
        ero_map = {
            1: "/qpf/94ewbg.gif",
            2: "/qpf/98ewbg.gif",
            3: "/qpf/99ewbg.gif",
            4: "/qpf/ero_d45/images/d4wbg.gif",
            5: "/qpf/ero_d45/images/d5wbg.gif",
        }
        if day not in ero_map:
            raise ValueError(f"day must be 1-5, got {day}")

        url = self._url(ero_map[day])
        resp = self._get(url)
        filename = f"ero_day{day}.gif"
        return self._save(resp.content, filename)

    def download_ero_image_filled(self, day: int = 1) -> Path:
        """
        Download the color-filled version of the ERO map.

        URL patterns (filled):
          Day 1-until: /qpf/fill_92ewbg.gif
          Day 1:       /qpf/fill_93ewbg.gif
          Day 2:       /qpf/fill_94qwbg.gif  (or fill_98qwbg.gif)
          Days 1-3:    /qpf/fill_9eewbg.gif  (Day 1: 9ee, Day 2: 9fe, etc.)
        """
        fill_map = {
            1: "/qpf/fill_93ewbg.gif",
            2: "/qpf/fill_94qwbg.gif",
            3: "/qpf/fill_9eewbg.gif",
            4: "/qpf/ero_d45/images/d4wbg.gif",
            5: "/qpf/ero_d45/images/d5wbg.gif",
        }
        if day not in fill_map:
            raise ValueError(f"day must be 1-5, got {day}")

        url = self._url(fill_map[day])
        resp = self._get(url)
        filename = f"ero_day{day}_fill.gif"
        return self._save(resp.content, filename)

    def get_ero_geojson(self, day: int = 1) -> Dict[str, Any]:
        """
        Fetch the ERO GeoJSON for a given forecast day.

        URL: /exper/eromap/geojson/Day{N}_Latest.geojson

        Returns a GeoJSON FeatureCollection dict.  Feature properties include:
          - dn: 0
          - PRODUCT: "Day N Excessive Rainfall Potential Forecast"
          - VALID_TIME: "01Z MM/DD/YY - 12Z MM/DD/YY"
          - OUTLOOK: "None Expected" | "Marginal" | "Slight" | "Moderate" | "High"
          - ISSUE_TIME, START_TIME, END_TIME
          - Snippet: short valid time string
        """
        if day not in (1, 2, 3, 4, 5):
            raise ValueError(f"day must be 1-5, got {day}")
        url = self._url(f"/exper/eromap/geojson/Day{day}_Latest.geojson")
        resp = self._get(url)
        return resp.json()

    def download_ero_kmz(self, day: int = 1) -> Path:
        """
        Download the ERO KMZ file for Google Earth.

        URL: /kml/ero/Day_{N}_Excessive_Rainfall_Outlook.kmz
        """
        if day not in (1, 2, 3):
            raise ValueError(f"ERO KMZ only available for days 1-3, got {day}")
        url = self._url(f"/kml/ero/Day_{day}_Excessive_Rainfall_Outlook.kmz")
        resp = self._get(url)
        filename = f"ero_day{day}.kmz"
        return self._save(resp.content, filename)

    def download_ero_shapefile(self, day: int = 1) -> Path:
        """
        Download the ERO shapefile ZIP.

        URL: https://ftp-wpc.ncep.noaa.gov/shapefiles/qpf/excessive/EXCESSIVERAIN_Day{N}_latest.zip
        """
        url = f"{FTP_BASE}/shapefiles/qpf/excessive/EXCESSIVERAIN_Day{day}_latest.zip"
        resp = self._get(url, allow_redirects=True)
        filename = f"ero_day{day}_latest.zip"
        return self._save(resp.content, filename)

    def get_ero_info(self, day: int = 1) -> str:
        """
        Fetch the ERO issuance metadata as HTML snippet.

        Returns an HTML string with valid times, issuance time, and forecaster.
        URL: /qpf/web_ero/ero_web_d{N}_info.php
        """
        if day not in (1, 2, 3, 4, 5):
            raise ValueError(f"day must be 1-5, got {day}")
        url = self._url(f"/qpf/web_ero/ero_web_d{day}_info.php")
        resp = self._get(url)
        return resp.text

    # -----------------------------------------------------------------------
    # National Forecast Charts (NOAA Charts)
    # -----------------------------------------------------------------------

    def download_national_forecast_chart(
        self,
        day: int = 1,
        format: str = "png",
        spanish: bool = False,
    ) -> Path:
        """
        Download the National Forecast Chart (NFC).

        Parameters
        ----------
        day:
            Forecast day (1, 2, or 3).
        format:
            "png" (higher quality, from /NationalForecastChart/staticmaps/),
            "gif" (from /noaa/),
            or "pdf" (from /noaa/).
        spanish:
            If True and format="png", download the Spanish-language version.

        URL patterns:
          PNG: /NationalForecastChart/staticmaps/noaad{N}.png
          PNG Spanish: /NationalForecastChart/staticmaps/sp_noaad{N}.png
          GIF: /noaa/noaad{N}.gif
          PDF: /noaa/noaad{N}.pdf
        """
        if day not in (1, 2, 3):
            raise ValueError(f"day must be 1-3, got {day}")

        if format == "png":
            prefix = "sp_noaad" if spanish else "noaad"
            url = self._url(f"/NationalForecastChart/staticmaps/{prefix}{day}.png")
            filename = f"noaa_forecast_day{day}{'_es' if spanish else ''}.png"
        elif format == "gif":
            url = self._url(f"/noaa/noaad{day}.gif")
            filename = f"noaa_forecast_day{day}.gif"
        elif format == "pdf":
            url = self._url(f"/noaa/noaad{day}.pdf")
            filename = f"noaa_forecast_day{day}.pdf"
        else:
            raise ValueError(f"format must be 'png', 'gif', or 'pdf', got {format!r}")

        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_archived_national_forecast(
        self,
        date: datetime,
        synoptic_hour: int,
        day: int = 1,
    ) -> Path:
        """
        Download an archived National Forecast Chart.

        URL pattern: /archives/noaa/{YYYY}/noaad{N}_{YYYYMMDD}{HH}.gif
        """
        year = date.strftime("%Y")
        date_str = date.strftime("%Y%m%d")
        hour_str = f"{synoptic_hour:02d}"
        filename = f"noaad{day}_{date_str}{hour_str}.gif"
        url = self._url(f"/archives/noaa/{year}/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # NationalForecastChart mapdata JSON
    # -----------------------------------------------------------------------

    def get_nfc_mapdata(self, product: str, day: int = 1) -> bytes:
        """
        Fetch NationalForecastChart interactive map data.

        These JSON files power the interactive /NationalForecastChart/map.php page.

        Parameters
        ----------
        product:
            One of:
              "qpf"      - QPF polygon data
              "rsn"      - Reason polygons (weather type text)
              "sno"      - Snow polygons
              "ww"       - Winter weather polygons
              "ero"      - ERO outlook data
              "svr"      - Severe weather
              "trw"      - Tropical weather
              "tropical" - Tropical storm tracks
              "fronts"   - Front lines (JS format: fronts{N}{f}.js)
        day:
            Forecast day (1, 2, or 3).

        URL patterns:
          /NationalForecastChart/mapdata/{product}D{N}.json
          /NationalForecastChart/mapdata/fronts9{N}f.js  (N=1->1, 2->2, 3->3)

        Note: The JSON files are not strictly valid JSON (no trailing commas
        issue) but can be read as text for polygon coordinates.
        """
        if product == "fronts":
            # Front data is stored as JS: fronts91f.js, fronts92f.js, fronts93f.js
            # The hex digit maps: day1->1, day2->2, day3->3
            day_hex = str(day)
            url = self._url(f"/NationalForecastChart/mapdata/fronts9{day_hex}f.js")
        elif product == "tropical":
            url = self._url(f"/NationalForecastChart/mapdata/tropical{day}.json")
        else:
            url = self._url(f"/NationalForecastChart/mapdata/{product}D{day}.json")

        resp = self._get(url)
        return resp.content

    def get_nfc_ero_json(self, day: int = 1) -> Dict[str, Any]:
        """
        Get the NFC ERO JSON data (simpler format, for map display).

        URL: /NationalForecastChart/mapdata/eroD{N}.json
        """
        url = self._url(f"/NationalForecastChart/mapdata/eroD{day}.json")
        resp = self._get(url)
        return resp.json()

    # -----------------------------------------------------------------------
    # Discussions (text products)
    # -----------------------------------------------------------------------

    def get_discussion(
        self,
        disc_type: str = "pmdspd",
        version: int = 0,
    ) -> str:
        """
        Fetch a WPC text discussion product.

        Parameters
        ----------
        disc_type:
            Discussion type code.  Available codes:
              "pmdspd"  - Short Range Public Discussion (issued every 6-8 hrs)
              "pmdepd"  - Extended Forecast Discussion (day 3-7)
              "pmdak"   - Alaska Public Discussion
              "pmdhi"   - Hawaii Public Discussion
              "nathilo" - National High/Low Synopsis
              "qpferd"  - Excessive Rainfall Discussion
              "qpfhsd"  - Hazardous Weather Outlook
              "fxsa20"  - Pacific Public Discussion
              "fxsa21"  - Pacific Extended Discussion
              "fxca20"  - Caribbean Discussion
        version:
            0 = latest (default), 1 = previous, 2 = two back, etc.

        Returns
        -------
        The raw discussion text (pre-formatted ASCII).

        URL: /discussions/hpcdiscussions.php?disc={type}&version={N}&fmt=reg
        """
        if disc_type not in DISCUSSION_TYPES:
            raise ValueError(
                f"Unknown discussion type {disc_type!r}. "
                f"Valid types: {list(DISCUSSION_TYPES.keys())}"
            )

        url = self._url(
            f"/discussions/hpcdiscussions.php?disc={disc_type}"
            f"&version={version}&fmt=reg"
        )
        resp = self._get(url)
        html = resp.text

        # The discussion text is inside a <pre>...</pre> block in the printarea div
        m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL | re.IGNORECASE)
        if m:
            # Clean up HTML entities and tags inside
            text = m.group(1)
            text = re.sub(r"<[^>]+>", "", text)
            text = (
                text.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
                .replace("&nbsp;", " ")
            )
            return text.strip()
        return html  # fallback: return full HTML if parsing fails

    def list_discussion_types(self) -> Dict[str, str]:
        """Return a dict of available discussion type codes -> names."""
        return dict(DISCUSSION_TYPES)

    # -----------------------------------------------------------------------
    # Mesoscale Precipitation Discussions (MPDs)
    # -----------------------------------------------------------------------

    def get_mpd_list(self) -> List[Dict[str, str]]:
        """
        Scrape the current MPD list from metwatch.

        Returns a list of dicts with keys:
          "number", "year", "area", "time"

        URL: /metwatch/metwatch_mpd.php
        """
        url = self._url("/metwatch/metwatch_mpd.php")
        resp = self._get(url)
        html = resp.text

        # Find MPD links like metwatch_mpd_multi.php?md=0063&yr=2026
        pattern = re.compile(
            r'metwatch_mpd_multi\.php\?md=(\d+)&(?:amp;)?yr=(\d+)[^>]*>([^<]+)'
        )
        results = []
        for m in pattern.finditer(html):
            label = m.group(3).strip()
            # Clean up HTML entities (including malformed ones without semicolons)
            label = re.sub(r'&nbsp;?', ' ', label)
            label = (
                label.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
            )
            label = label.strip()
            results.append({
                "number": m.group(1),
                "year": m.group(2),
                "label": label,
            })
        return results

    def get_mpd_text(self, number: int, year: Optional[int] = None) -> str:
        """
        Fetch the text of a specific MPD.

        Parameters
        ----------
        number:
            The MPD number (e.g., 63 for MPD #0063).
        year:
            The year (defaults to current year).

        Returns
        -------
        The formatted MPD discussion text.

        URL: /metwatch/metwatch_mpd_multi.php?md={NNNN}&yr={YYYY}
        """
        if year is None:
            year = _now_utc().year
        url = self._url(
            f"/metwatch/metwatch_mpd_multi.php?md={number:04d}&yr={year}"
        )
        resp = self._get(url)
        html = resp.text

        m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1)
            text = re.sub(r"<[^>]+>", "", text)
            text = (
                text.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
                .replace("&nbsp;", " ")
            )
            return text.strip()
        return html

    def download_mpd_image(self, number: int, year: Optional[int] = None) -> Path:
        """
        Download the map image for a specific MPD.

        URL pattern: /metwatch/images/mcd{NNNN}.gif
        """
        if year is None:
            year = _now_utc().year
        filename = f"mcd{number:04d}.gif"
        url = self._url(f"/metwatch/images/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def get_mpd_rss(self) -> str:
        """
        Fetch the MPD RSS feed XML.

        URL: /metwatch/mdrss.xml
        """
        url = self._url("/metwatch/mdrss.xml")
        resp = self._get(url)
        return resp.text

    # -----------------------------------------------------------------------
    # Winter Weather Products
    # -----------------------------------------------------------------------

    def download_wssi_map(self, region: str = "conus") -> Path:
        """
        Download the Winter Storm Severity Index (WSSI) map.

        Parameters
        ----------
        region:
            "conus" - CONUS overview map

        URL: /wwd/wssi/images/WSSI_Overall_CONUS.png
        """
        if region == "conus":
            filename = "WSSI_Overall_CONUS.png"
            url = self._url(f"/wwd/wssi/images/{filename}")
        else:
            raise ValueError(f"Unknown region {region!r}, only 'conus' supported")

        resp = self._get(url)
        return self._save(resp.content, f"wssi_{region}.png")

    def download_wssi_forecast(
        self,
        forecast_hour: int = 24,
        category: str = "Overall_Minor",
    ) -> Path:
        """
        Download WSSI probability forecast maps.

        Parameters
        ----------
        forecast_hour:
            Forecast hour: 24, 48, 72, 96, 120, 144, 168.
        category:
            WSSI category:  "Overall_Minor", "Overall_Moderate",
            "Overall_Major", "Overall_Extreme", "Ground_Blizzard",
            "Snow_Ice", "Wind", "Cold"

        URL pattern: /wwd/wssi/images/wssi_p_{category}_f{HHH}.png
        """
        fhh = f"{forecast_hour:03d}"
        filename = f"wssi_p_{category}_f{fhh}.png"
        url = self._url(f"/wwd/wssi/images/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_winter_composite(self, day: int = 1) -> Path:
        """
        Download the winter weather composite thumbnail map.

        Parameters
        ----------
        day: 1, 2, or 3

        URL pattern: /wwd/day{N}_composite_sm.jpg
        """
        if day not in (1, 2, 3):
            raise ValueError(f"day must be 1-3, got {day}")
        filename = f"day{day}_composite_sm.jpg"
        url = self._url(f"/wwd/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_snow_probability(
        self,
        day: int = 1,
        threshold_inches: int = 4,
        size: str = "sm",
    ) -> Path:
        """
        Download a snow accumulation probability thumbnail.

        Parameters
        ----------
        day:
            Forecast day (1-3 for thumbnail maps).
        threshold_inches:
            Accumulation threshold in inches: 4, 8, or 12.
        size:
            "sm" for small thumbnail (default).

        URL pattern: /wwd/day{N}_psnow_gt_{TT}_{size}.jpg
        Example: /wwd/day1_psnow_gt_04_sm.jpg
        """
        tt = f"{threshold_inches:02d}"
        filename = f"day{day}_psnow_gt_{tt}_{size}.jpg"
        url = self._url(f"/wwd/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_ice_probability(
        self,
        day: int = 1,
        threshold: int = 25,
        size: str = "sm",
    ) -> Path:
        """
        Download an ice accumulation probability thumbnail.

        Parameters
        ----------
        day:
            Forecast day (1-3).
        threshold:
            Threshold (hundredths of inch): 25 (0.25"), 50 (0.50").
        size:
            "sm" for small thumbnail.

        URL pattern: /wwd/day{N}_pice_gt_{TT}_{size}.jpg
        """
        tt = f"{threshold:02d}"
        filename = f"day{day}_pice_gt_{tt}_{size}.jpg"
        url = self._url(f"/wwd/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_pwpf_image(
        self,
        precip_type: str = "snow",
        threshold: str = "01",
        forecast_hour: int = 24,
        forecast_period: int = 24,
        date_cycle: Optional[str] = None,
    ) -> Path:
        """
        Download a Probabilistic Winter Precipitation Forecast (PWPF) image.

        Parameters
        ----------
        precip_type:
            "snow" or "icez" (freezing rain).
        threshold:
            Accumulation threshold code:
              Snow (24hr): "01", "02", "04", "06", "08", "12", "18"  (inches)
              Ice (24hr):  "01", "10", "25", "50"  (hundredths of inch)
        forecast_hour:
            Forecast valid ending hour: 024, 030, 036, ..., 072.
        forecast_period:
            Period length: 24 or 48 hours.
        date_cycle:
            Model cycle string like "2026032500" (YYYYMMDDhh).
            If None, uses the "latest" keyword.

        URL pattern:
            /pwpf_{period}hr/prb_{period}h{ptype}_ge{threshold}_{datecycle}f{FFF}.gif
        Example:
            /pwpf_24hr/prb_24hsnow_ge01_latestf024.gif
        """
        cycle = date_cycle if date_cycle else "latest"
        fhh = f"{forecast_hour:03d}"
        filename = (
            f"prb_{forecast_period}h{precip_type}_ge{threshold}"
            f"_{cycle}f{fhh}.gif"
        )
        url = self._url(f"/pwpf_{forecast_period}hr/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    def download_winter_shapefile(
        self,
        day: int = 1,
        product: str = "psnow_gt_04",
    ) -> Path:
        """
        Download a winter weather shapefile ZIP.

        Parameters
        ----------
        day: 1, 2, or 3
        product:
            "psnow_gt_04", "psnow_gt_08", "psnow_gt_12",
            or "picez_gt_25"

        URL:
          https://ftp-wpc.ncep.noaa.gov/shapefiles/ww/day{N}/DAY{N}_{PRODUCT}_latest.tar
        """
        day_str = f"day{day}"
        prod_upper = product.upper()
        filename = f"DAY{day}_{prod_upper}_latest.tar"
        url = f"{FTP_BASE}/shapefiles/ww/{day_str}/{filename}"
        resp = self._get(url, allow_redirects=True)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # Medium Range Forecasts (Day 3-7)
    # -----------------------------------------------------------------------

    def download_medium_range_map(
        self,
        forecast_hour: int = 72,
        product: str = "wpcwx+fronts",
    ) -> Path:
        """
        Download a medium range forecast map.

        Parameters
        ----------
        forecast_hour:
            Forecast valid hour: 72, 96, 120, 144, 168.
        product:
            "wpcwx+fronts" (WPC weather + fronts, default)

        URL pattern: /medr/display/{product}f{HHH}.gif
        Example: /medr/display/wpcwx+frontsf072.gif
        """
        fhh = f"{forecast_hour:03d}"
        filename = f"{product}f{fhh}.gif"
        url = self._url(f"/medr/display/{filename}")
        resp = self._get(url)
        safe_name = filename.replace("+", "_")
        return self._save(resp.content, safe_name)

    def download_5day_forecast(self, style: str = "wbg") -> Path:
        """
        Download the 5-day medium range forecast graphic.

        URL: /medr/5dayfcst_{style}_conus.gif
        style: "wbg" (color) or "bw" (black/white)
        """
        filename = f"5dayfcst_{style}_conus.gif"
        url = self._url(f"/medr/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # National Flood Outlook
    # -----------------------------------------------------------------------

    def download_flood_outlook_map(self) -> Path:
        """
        Download the National Flood Outlook static map.

        URL: /nationalfloodoutlook/finalfop.png
        """
        url = self._url("/nationalfloodoutlook/finalfop.png")
        resp = self._get(url)
        return self._save(resp.content, "flood_outlook.png")

    def get_flood_outlook_geojson(
        self, category: str = "occurring"
    ) -> Dict[str, Any]:
        """
        Fetch the National Flood Outlook GeoJSON data.

        Parameters
        ----------
        category:
            "occurring" - Currently occurring floods
            "likely"    - Likely in next 1-3 days
            "possible"  - Possible in next 1-3 days

        URL: /nationalfloodoutlook/{category}.geojson

        Feature properties: ID, PRODUCT, VALID_DATE, ISSUE TIME,
        START TIME, END TIME, SIG_WX_TYPE, style
        """
        if category not in ("occurring", "likely", "possible"):
            raise ValueError(
                f"category must be 'occurring', 'likely', or 'possible'"
            )
        url = self._url(f"/nationalfloodoutlook/{category}.geojson")
        resp = self._get(url)
        return resp.json()

    # -----------------------------------------------------------------------
    # Heat Index Forecasts
    # -----------------------------------------------------------------------

    def download_heat_index_image(
        self,
        variable: str = "himax",
        date_str: Optional[str] = None,
        forecast_type: str = "deterministic",
        threshold: Optional[str] = None,
    ) -> Path:
        """
        Download a WPC Heat Index forecast image.

        Parameters
        ----------
        variable:
            "himax" (maximum heat index, default),
            "hiavg" (average heat index),
            "himin" (minimum heat index)
        date_str:
            Date string in the format used by the page (e.g., "2026032512").
            If None, uses the default 72-hour forecast.
        forecast_type:
            "deterministic" (default) or "probabilistic"
        threshold:
            Required for probabilistic forecasts (e.g., "95", "100", "105").

        URL patterns:
          Deterministic: /heatindex/images/{variable}_{date}.png
          Default (no date): /heatindex/images/himax_f072.png
          Probabilistic: /heatindex/images/{variable}_prb{threshold}_{date}.png
        """
        if date_str is None:
            # Use default static image (72hr deterministic)
            filename = f"himax_f072.png"
            url = self._url(f"/heatindex/images/{filename}")
        elif forecast_type == "probabilistic" and threshold:
            filename = f"{variable}_prb{threshold}_{date_str}.png"
            url = self._url(f"/heatindex/images/{filename}")
        else:
            filename = f"{variable}_{date_str}.png"
            url = self._url(f"/heatindex/images/{filename}")

        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # KML Products
    # -----------------------------------------------------------------------

    def download_qpf_kmz(
        self,
        product: str = "QPF24hr_Day1_latest",
    ) -> Path:
        """
        Download a QPF KMZ file for Google Earth.

        Parameters
        ----------
        product:
            Available KMZ products:
              "QPF6hr_f00-f06_latest"   (6-hour QPF, first period)
              "QPF6hr_f06-f12_latest"
              "QPF6hr_f12-f18_latest"
              "QPF6hr_f18-f24_latest"
              "QPF6hr_f24-f30_latest"
              "QPF6hr_f30-f36_latest"
              "QPF6hr_f36-f42_latest"
              "QPF6hr_f42-f48_latest"
              "QPF6hr_f48-f54_latest"
              "QPF6hr_f54-f60_latest"
              "QPF6hr_f60-f66_latest"
              "QPF6hr_f66-f72_latest"
              "QPF6hr_f72-f78_latest"
              "QPF24hr_Day1_latest"
              "QPF24hr_Day2_latest"
              "QPF24hr_Day3_latest"
              "QPF48hr_Day1-2_latest"
              "QPF48hr_Day4-5_latest"
              "QPF48hr_Day6-7_latest"
              "QPF72hr_Day1-3_latest"
              "QPF120hr_Day1-5_latest"
              "QPF168hr_Day1-7_latest"

        URL: /kml/qpf/{product}.kmz
        """
        filename = f"{product}.kmz"
        url = self._url(f"/kml/qpf/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # ArcGIS MapServer (WPC Precip Hazards)
    # -----------------------------------------------------------------------

    def get_arcgis_ero_layer(
        self,
        day: int = 1,
        out_sr: int = 4326,
        out_fields: str = "*",
    ) -> Dict[str, Any]:
        """
        Query the ArcGIS MapServer for WPC ERO (Excessive Rainfall Outlook) data.

        The MapServer has 5 layers (indices 0-4) for ERO Days 1-5.

        Parameters
        ----------
        day:
            ERO day (1-5).  Maps to layer index (day - 1).
        out_sr:
            Output spatial reference (WKID).  4326 = WGS84 (default).
        out_fields:
            Fields to return ("*" = all).

        Returns a GeoJSON-style FeatureSet from the ArcGIS REST API.

        Base URL: https://mapservices.weather.noaa.gov/vector/rest/services/
                  hazards/wpc_precip_hazards/MapServer/{layer_index}/query
        """
        layer = day - 1  # layer 0 = Day 1, layer 4 = Day 5
        url = f"{ARCGIS_BASE}/{layer}/query"
        params = {
            "where": "1=1",
            "outFields": out_fields,
            "outSR": out_sr,
            "f": "geojson",
        }
        resp = self._get(url, params=params)
        return resp.json()

    def get_arcgis_service_info(self) -> Dict[str, Any]:
        """
        Get metadata about the WPC Precip Hazards MapServer service.

        Returns service info including layer names, extent, etc.
        """
        url = f"{ARCGIS_BASE}?f=json"
        resp = self._get(url)
        return resp.json()

    # -----------------------------------------------------------------------
    # Low Cluster Analysis
    # -----------------------------------------------------------------------

    def download_low_clusters(self) -> Path:
        """
        Download the WPC Low Cluster Analysis map.

        URL: /lowclusters/lowclusters_latest.png
        """
        url = self._url("/lowclusters/lowclusters_latest.png")
        resp = self._get(url)
        return self._save(resp.content, "lowclusters_latest.png")

    # -----------------------------------------------------------------------
    # Threats / Hazards D3-7
    # -----------------------------------------------------------------------

    def download_hazards_map(self) -> Path:
        """
        Download the WPC Threats & Hazards Day 3-7 contour map.

        URL: /threats/final/hazards_d3_7_contours.png
        """
        url = self._url("/threats/final/hazards_d3_7_contours.png")
        resp = self._get(url)
        return self._save(resp.content, "hazards_d3_7_contours.png")

    def download_hazards_kmz(self, hazard_type: str = "flooding") -> Path:
        """
        Download a Hazards KML file.

        Parameters
        ----------
        hazard_type:
            "flooding", "precipitation", "temperature",
            "soils", "wildfires"

        URL pattern: /threats/final/FloodingHazards.kml
        """
        name_map = {
            "flooding":      "FloodingHazards.kml",
            "precipitation": "Prcp_D3_7.kml",
            "temperature":   "Temp_D3_7.kml",
            "soils":         "Soils_D3_7.kml",
            "wildfires":     "Wildfires_D3_7.kml",
        }
        if hazard_type not in name_map:
            raise ValueError(
                f"hazard_type must be one of: {list(name_map.keys())}"
            )
        filename = name_map[hazard_type]
        url = self._url(f"/threats/final/{filename}")
        resp = self._get(url)
        return self._save(resp.content, filename)

    # -----------------------------------------------------------------------
    # Convenience / batch methods
    # -----------------------------------------------------------------------

    def download_daily_package(
        self,
        include_discussions: bool = True,
        include_qpf: bool = True,
        include_surface: bool = True,
        include_ero: bool = True,
        include_winter: bool = True,
    ) -> Dict[str, Any]:
        """
        Download a standard daily weather package.

        Downloads the most commonly used products and returns a summary dict.

        Returns
        -------
        Dict with "downloaded" (list of Path objects) and "errors" (list of
        (product_name, exception) tuples).
        """
        downloaded: List[Path] = []
        errors: List[Tuple[str, Exception]] = []

        def _try(name: str, fn, *args, **kwargs):
            try:
                path = fn(*args, **kwargs)
                downloaded.append(path)
                print(f"  [OK] {name} -> {path.name}")
            except Exception as exc:
                errors.append((name, exc))
                print(f"  [FAIL] {name}: {exc}")

        print("Downloading WPC daily package...")

        if include_surface:
            for hour in (0, 6, 12, 18):
                _try(
                    f"Surface analysis {hour:02d}Z",
                    self.download_surface_analysis,
                    synoptic_hour=hour,
                )

        if include_qpf:
            for day in range(1, 4):
                _try(f"QPF Day {day}", self.download_qpf_image, day=day)
            _try("QPF 5-day total", self.download_qpf_total, days=5)

        if include_ero:
            for day in range(1, 4):
                _try(f"ERO Day {day} image", self.download_ero_image, day=day)
                _try(f"ERO Day {day} GeoJSON", self.get_ero_geojson, day=day)

        if include_winter:
            _try("WSSI CONUS", self.download_wssi_map, region="conus")
            for day in (1, 2, 3):
                _try(
                    f"Snow prob Day {day} >=4in",
                    self.download_snow_probability,
                    day=day, threshold_inches=4,
                )

        if include_discussions:
            for disc_type, disc_name in [
                ("pmdspd", "Short Range Discussion"),
                ("pmdepd", "Extended Discussion"),
                ("qpferd", "ERO Discussion"),
            ]:
                _try(disc_name, self.get_discussion, disc_type=disc_type)

        # National forecast charts
        for day in (1, 2, 3):
            _try(
                f"National Forecast Chart Day {day}",
                self.download_national_forecast_chart,
                day=day,
            )

        print(
            f"\nComplete: {len(downloaded)} downloaded, "
            f"{len(errors)} errors."
        )
        return {"downloaded": downloaded, "errors": errors}


# ---------------------------------------------------------------------------
# Quick-reference URL builder functions
# ---------------------------------------------------------------------------

def surface_url(hour: int = 0, region: str = "us", style: str = "wbg") -> str:
    """Return the URL for a current surface analysis image."""
    prefix_map = {"us": "namus", "ak": "namak", "ak2": "namak2"}
    prefix = prefix_map.get(region, "namus")
    return f"{BASE_URL}/sfc/{prefix}sfc{hour:02d}{style}.gif"


def qpf_url(day: int = 1, filled: bool = True) -> str:
    """Return the URL for a QPF day forecast image (24-hour daily total)."""
    if day == 1:
        fname = "fill_94qwbg.gif" if filled else "94qwbg.gif"
    elif day == 2:
        fname = "fill_98qwbg.gif" if filled else "98qwbg.gif"
    elif day == 3:
        fname = "fill_99qwbg.gif" if filled else "99qwbg.gif"
    elif day in (4, 5, 6, 7):
        suffix = "iwbg_fill" if filled else "iwbg"
        fname = f"day{day}p24{suffix}.gif"
    else:
        raise ValueError(f"day must be 1-7, got {day}")
    return f"{BASE_URL}/qpf/{fname}"


def ero_geojson_url(day: int = 1) -> str:
    """Return the URL for an ERO GeoJSON endpoint."""
    return f"{BASE_URL}/exper/eromap/geojson/Day{day}_Latest.geojson"


def discussion_url(disc_type: str = "pmdspd", version: int = 0) -> str:
    """Return the URL for a WPC discussion page."""
    return (
        f"{BASE_URL}/discussions/hpcdiscussions.php"
        f"?disc={disc_type}&version={version}&fmt=reg"
    )


# ---------------------------------------------------------------------------
# CLI entry point / example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    import json

    # Use a temp directory for the demo
    tmpdir = tempfile.mkdtemp(prefix="wpc_demo_")
    print(f"Output directory: {tmpdir}\n")

    client = WPCClient(output_dir=tmpdir)

    # ------------------------------------------------------------------ #
    # 1. Get the Short Range Public Discussion
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("SHORT RANGE PUBLIC DISCUSSION (pmdspd)")
    print("=" * 60)
    text = client.get_discussion("pmdspd")
    lines = text.splitlines()
    # Print first 15 lines
    for line in lines[:15]:
        print(line)
    print(f"... [{len(lines)} total lines]")
    print()

    # ------------------------------------------------------------------ #
    # 2. Download today's surface analysis maps (latest synoptic hour)
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("SURFACE ANALYSIS MAPS")
    print("=" * 60)
    for hour in (0, 6, 12, 18):
        try:
            path = client.download_surface_analysis(synoptic_hour=hour)
            size = path.stat().st_size
            print(f"  Hour {hour:02d}Z: {path.name} ({size:,} bytes)")
        except requests.HTTPError as e:
            print(f"  Hour {hour:02d}Z: HTTP {e.response.status_code} (not yet available)")

    print()

    # ------------------------------------------------------------------ #
    # 3. Download QPF maps for days 1-3
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("QPF FORECAST MAPS (Days 1-3)")
    print("=" * 60)
    for day in (1, 2, 3):
        path = client.download_qpf_image(day=day)
        print(f"  Day {day}: {path.name} ({path.stat().st_size:,} bytes)")

    print()

    # ------------------------------------------------------------------ #
    # 4. Fetch ERO GeoJSON (Day 1)
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("EXCESSIVE RAINFALL OUTLOOK - DAY 1 (GeoJSON)")
    print("=" * 60)
    ero_data = client.get_ero_geojson(day=1)
    features = ero_data.get("features", [])
    print(f"  Features: {len(features)}")
    if features:
        props = features[0].get("properties", {})
        for k, v in props.items():
            print(f"  {k}: {v}")

    print()

    # ------------------------------------------------------------------ #
    # 5. Download National Forecast Charts (Days 1-3)
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("NATIONAL FORECAST CHARTS (Days 1-3)")
    print("=" * 60)
    for day in (1, 2, 3):
        path = client.download_national_forecast_chart(day=day, format="png")
        print(f"  Day {day}: {path.name} ({path.stat().st_size:,} bytes)")

    print()

    # ------------------------------------------------------------------ #
    # 6. Download WSSI Winter Storm Severity Index
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("WINTER STORM SEVERITY INDEX (WSSI)")
    print("=" * 60)
    try:
        path = client.download_wssi_map()
        print(f"  WSSI CONUS: {path.name} ({path.stat().st_size:,} bytes)")
    except requests.HTTPError as e:
        print(f"  WSSI: HTTP {e.response.status_code}")

    print()

    # ------------------------------------------------------------------ #
    # 7. National Flood Outlook GeoJSON
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("NATIONAL FLOOD OUTLOOK (GeoJSON)")
    print("=" * 60)
    for cat in ("occurring", "likely", "possible"):
        data = client.get_flood_outlook_geojson(category=cat)
        print(f"  {cat}: {len(data.get('features', []))} features")

    print()

    # ------------------------------------------------------------------ #
    # 8. List MPDs
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("MESOSCALE PRECIPITATION DISCUSSIONS (MPDs)")
    print("=" * 60)
    mpds = client.get_mpd_list()
    for mpd in mpds[:5]:
        print(f"  MPD #{mpd['number']} ({mpd['year']}): {mpd['label']}")
    if len(mpds) > 5:
        print(f"  ... and {len(mpds) - 5} more")

    print()

    # ------------------------------------------------------------------ #
    # 9. Quick URL builder examples
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("QUICK URL REFERENCE")
    print("=" * 60)
    print("Surface analysis URLs:")
    for h in (0, 6, 12, 18):
        print(f"  {h:02d}Z: {surface_url(h)}")
    print()
    print("QPF URLs:")
    for d in (1, 2, 3):
        print(f"  Day {d}: {qpf_url(d)}")
    print()
    print("ERO GeoJSON URLs:")
    for d in (1, 2, 3, 4, 5):
        print(f"  Day {d}: {ero_geojson_url(d)}")
    print()
    print("Discussion URLs:")
    for dt in ("pmdspd", "pmdepd", "qpferd"):
        print(f"  {dt}: {discussion_url(dt)}")

    print()
    print(f"All downloads saved to: {tmpdir}")
