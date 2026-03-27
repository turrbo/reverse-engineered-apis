"""
USGS Volcano Observatory Webcam & Monitoring API Client
========================================================
Reverse-engineered client covering all publicly-accessible USGS volcano APIs:

  1. VHP VSC APIs          (volcanoes.usgs.gov/vsc/api/)
     - volcanoApi       — volcano metadata, status, GeoJSON, station plots
     - observatoryApi   — observatory info & boundaries
     - hansApi          — hazard notices, VONAs (legacy endpoint)
     - hvoWebcamsApi    — HVO webcam metadata (may return empty currently)
     - volcanoMessageApi — short eruption status snippets (Kilauea only)

  2. HANS Public API       (volcanoes.usgs.gov/hans-public/api/)
     - volcano/         — elevated, monitored, individual volcano data
     - notice/          — notice retrieval, recent notices, VONAs
     - map/             — XML status for mapping
     - search/          — full-text search across historical notices

  3. HVO Legacy System     (volcanoes.usgs.gov/cams/)
     - One JPEG per camera, refreshed every 1–10 minutes
     - js.js sidecar carries last-updated timestamp

  4. AVO Ashcam API        (avo.alaska.edu/ashcam-api/)
     - webcamApi        — 386 cameras; metadata, GeoJSON
     - imageApi         — full image archive with Unix-timestamp filtering

  5. VolcView API          (volcview.wr.usgs.gov/ashcam-api/)
     - Mirror of AVO API used by CVO, YVO, CalVO cameras

No authentication required for any read operation.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Base URL constants
# ---------------------------------------------------------------------------

HVO_BASE   = "https://volcanoes.usgs.gov"
AVO_API    = "https://avo.alaska.edu/ashcam-api"
VV_API     = "https://volcview.wr.usgs.gov/ashcam-api"  # mirrors AVO; used by CVO/YVO
VSC_BASE   = "https://volcanoes.usgs.gov/vsc/api"
HANS_BASE  = "https://volcanoes.usgs.gov/hans-public/api"


# ---------------------------------------------------------------------------
# Hardcoded HVO camera inventory
# Source: https://volcanoes.usgs.gov/cams/
# ---------------------------------------------------------------------------

HVO_CAMERAS: List[Dict[str, Any]] = [
    # Kilauea – Summit
    {"cam_id": "B1cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Kilauea Caldera down-dropped block and Halemaumau from east rim", "thermal": False},
    {"cam_id": "B2cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau and lava lake from the down-dropped block", "thermal": False},
    {"cam_id": "F1cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau – thermal camera from west rim of summit caldera", "thermal": True},
    {"cam_id": "K2cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Kilauea Caldera from Uekahuna bluff", "thermal": False},
    {"cam_id": "KPcam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Kilauea Summit from Mauna Loa Strip Road", "thermal": False},
    {"cam_id": "KWcam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau and lava lake from west rim of summit caldera", "thermal": False},
    {"cam_id": "S2cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau from south side of crater", "thermal": False},
    {"cam_id": "V1cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau – temporary camera from northwest rim", "thermal": False},
    {"cam_id": "V2cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau – pan-tilt-zoom from northeast rim", "thermal": False},
    {"cam_id": "V3cam",   "volcano": "Kilauea", "region": "Summit",
     "description": "Halemaumau – pan-tilt-zoom from southern rim", "thermal": False},
    # Kilauea – East Rift Zone
    {"cam_id": "HPcam",   "volcano": "Kilauea", "region": "East Rift Zone",
     "description": "Holei Pali from Holei Pali", "thermal": False},
    {"cam_id": "KOcam",   "volcano": "Kilauea", "region": "East Rift Zone",
     "description": "Upper East Rift Zone from Maunaulu", "thermal": False},
    {"cam_id": "MUcam",   "volcano": "Kilauea", "region": "East Rift Zone",
     "description": "Mauna Ulu Cam", "thermal": False},
    {"cam_id": "PEcam",   "volcano": "Kilauea", "region": "East Rift Zone",
     "description": "Puu Oo East Flank", "thermal": False},
    {"cam_id": "PWcam",   "volcano": "Kilauea", "region": "East Rift Zone",
     "description": "Puu Oo West Flank", "thermal": False},
    {"cam_id": "R3cam",   "volcano": "Kilauea", "region": "East Rift Zone",
     "description": "Mobile Cam 3", "thermal": False},
    # Kilauea – Lower East Rift Zone
    {"cam_id": "PGcam",   "volcano": "Kilauea", "region": "Lower East Rift Zone",
     "description": "Fissures in Leilani Estates from Puu Honuaula", "thermal": False},
    # Kilauea – Southwest Rift Zone
    {"cam_id": "MITDcam", "volcano": "Kilauea", "region": "Southwest Rift Zone",
     "description": "Kilauea's SWRZ and summit from Hilina Pali", "thermal": False},
    {"cam_id": "S1cam",   "volcano": "Kilauea", "region": "Southwest Rift Zone",
     "description": "Upper Southwest Rift Zone", "thermal": False},
    # Mauna Loa – South Caldera
    {"cam_id": "MOcam",   "volcano": "Mauna Loa", "region": "South Caldera",
     "description": "Mokuaweoweo Caldera from South Rim", "thermal": False},
    {"cam_id": "SPcam",   "volcano": "Mauna Loa", "region": "South Caldera",
     "description": "South Pit from South Rim", "thermal": False},
    {"cam_id": "MSTcam",  "volcano": "Mauna Loa", "region": "South Caldera",
     "description": "South Pit and Upper Southwest Rift Zone – thermal from South Rim", "thermal": True},
    # Mauna Loa – Summit
    {"cam_id": "HLcam",   "volcano": "Mauna Loa", "region": "Summit",
     "description": "Mauna Loa northwest flank from Hualalai Volcano", "thermal": False},
    {"cam_id": "MLcam",   "volcano": "Mauna Loa", "region": "Summit",
     "description": "Mokuaweoweo Caldera from Northwest Rim", "thermal": False},
    {"cam_id": "MTcam",   "volcano": "Mauna Loa", "region": "Summit",
     "description": "Mokuaweoweo Caldera thermal from Northwest Rim", "thermal": True},
    # Mauna Loa – Northeast Rift Zone
    {"cam_id": "MKcam",   "volcano": "Mauna Loa", "region": "Northeast Rift Zone",
     "description": "Mauna Loa Summit and Northeast Rift Zone from Mauna Kea", "thermal": False},
    {"cam_id": "MK2cam",  "volcano": "Mauna Loa", "region": "Northeast Rift Zone",
     "description": "Mauna Loa Summit and Northeast Rift Zone from Mauna Kea (cam 2)", "thermal": False},
    # Mauna Loa – Southwest Rift Zone
    {"cam_id": "M2cam",   "volcano": "Mauna Loa", "region": "Southwest Rift Zone",
     "description": "Middle of Mauna Loa's Southwest Rift Zone", "thermal": False},
    {"cam_id": "M3cam",   "volcano": "Mauna Loa", "region": "Southwest Rift Zone",
     "description": "Upper of Mauna Loa's Southwest Rift Zone", "thermal": False},
    {"cam_id": "MSPcam",  "volcano": "Mauna Loa", "region": "Southwest Rift Zone",
     "description": "Mauna Loa Southwest Rift Zone from South Point area", "thermal": False},
    {"cam_id": "MDLcam",  "volcano": "Mauna Loa", "region": "Southwest Rift Zone",
     "description": "Mauna Loa middle Southwest Rift Zone", "thermal": False},
]

HVO_THERMAL_CAMS = {c["cam_id"] for c in HVO_CAMERAS if c["thermal"]}


# ---------------------------------------------------------------------------
# CVO camera inventory (via VolcView)
# ---------------------------------------------------------------------------

CVO_CAMERAS: List[Dict[str, Any]] = [
    # Mount St. Helens
    {"cam_id": "msh-dome",          "volcano": "Mount St. Helens", "description": "JRO – Dome"},
    {"cam_id": "msh-edifice",       "volcano": "Mount St. Helens", "description": "JRO – North Full View"},
    {"cam_id": "msh-glacierfront",  "volcano": "Mount St. Helens", "description": "JRO – Glacier Front"},
    {"cam_id": "msh-loowitfan",     "volcano": "Mount St. Helens", "description": "JRO – Loowit Fan"},
    {"cam_id": "msh-spiritlake",    "volcano": "Mount St. Helens", "description": "JRO – Spirit Lake"},
    {"cam_id": "msh-splblockage",   "volcano": "Mount St. Helens", "description": "JRO – Spirit Lake Blockage"},
    {"cam_id": "msh-nf100",         "volcano": "Mount St. Helens", "description": "JRO – NF100"},
    {"cam_id": "msh-GUAC",          "volcano": "Mount St. Helens", "description": "GUAC – North"},
    {"cam_id": "msh-eastwall",      "volcano": "Mount St. Helens", "description": "GUAC – East Crater Wall"},
    {"cam_id": "msh-SUG",           "volcano": "Mount St. Helens", "description": "SUG – Dome"},
    {"cam_id": "msh-westwall",      "volcano": "Mount St. Helens", "description": "SUG – West Crater Wall"},
    {"cam_id": "msh-WATCH",         "volcano": "Mount St. Helens", "description": "WATCH – North"},
    # JRO public legacy webcam (served via vsc/captures, not Ashcam)
    {"cam_id": "jro-webcam",        "volcano": "Mount St. Helens",
     "description": "Johnston Ridge Obs – looking south (legacy URL)",
     "legacy_url": f"{HVO_BASE}/vsc/captures/st_helens/jro-webcam.jpg"},
    # Mount Rainier
    {"cam_id": "rainier-mountain",              "volcano": "Mount Rainier", "description": "Paradise – South"},
    {"cam_id": "rainier-mora-west",             "volcano": "Mount Rainier", "description": "Paradise – Highway"},
    {"cam_id": "rainier-mora-east",             "volcano": "Mount Rainier", "description": "Paradise – Main Parking Lot"},
    {"cam_id": "rainier-tatoosh",               "volcano": "Mount Rainier", "description": "Paradise – Tatoosh"},
    {"cam_id": "rainier-nisqually-west",        "volcano": "Mount Rainier", "description": "Paradise – Tumtum"},
    {"cam_id": "rainier-paradise-visitor-center","volcano": "Mount Rainier", "description": "Paradise – Visitor Center"},
    {"cam_id": "rainier-crystalpana",           "volcano": "Mount Rainier", "description": "Crystal Mtn – Northeast"},
    {"cam_id": "rainier-elbe",                  "volcano": "Mount Rainier", "description": "Elbe – Highway"},
    {"cam_id": "rainier-longmire",              "volcano": "Mount Rainier", "description": "Longmire – Nisqually River"},
    {"cam_id": "rainier-sunrise",               "volcano": "Mount Rainier", "description": "Sunrise – Northeast"},
    {"cam_id": "rainier-WATCH",                 "volcano": "Mount Rainier", "description": "WATCH – South"},
    # Mount Baker
    {"cam_id": "baker-cascadia",     "volcano": "Mount Baker",     "description": "Cascadia ES – West"},
    # Mount Adams
    {"cam_id": "adams-WATCH",        "volcano": "Mount Adams",     "description": "WATCH – Northwest"},
    # Mount Hood
    {"cam_id": "hood-govtcamp",      "volcano": "Mount Hood",      "description": "Gov. Camp – South"},
    {"cam_id": "hood-mhm-vista",     "volcano": "Mount Hood",      "description": "Mount Hood Meadows – Southeast"},
    {"cam_id": "hood-palmer",        "volcano": "Mount Hood",      "description": "Palmer – South"},
    # Glacier Peak
    {"cam_id": "glacierpeak-seattle","volcano": "Glacier Peak",    "description": "Seattle – Southwest"},
    # Three Sisters
    {"cam_id": "threesis-bachelor",  "volcano": "Three Sisters",   "description": "Bachelor – South"},
    {"cam_id": "threesis-blackbutte","volcano": "Three Sisters",   "description": "Black Butte – North"},
    # Crater Lake
    {"cam_id": "crater-sinnott",     "volcano": "Crater Lake",     "description": "Sinnott Overlook – North"},
    # Mount Shasta (CalVO, but on VolcView)
    {"cam_id": "shasta-snowcrest",   "volcano": "Mount Shasta",    "description": "Snowcrest – West"},
]


# ---------------------------------------------------------------------------
# YVO camera inventory
# ---------------------------------------------------------------------------

YVO_CAMERAS: List[Dict[str, Any]] = [
    {"cam_id": "ys-bbsn",         "volcano": "Yellowstone", "description": "Black Diamond Pool / Biscuit Basin North"},
    {"cam_id": "yvoBiscuit",      "volcano": "Yellowstone", "description": "Yellowstone – Biscuit Basin"},
    {"cam_id": "yellowstone-lake","volcano": "Yellowstone", "description": "Yellowstone Lake"},
]


# ---------------------------------------------------------------------------
# Notable AVO cameras (representative subset; full list ~386 via API)
# ---------------------------------------------------------------------------

AVO_NOTABLE_CAMERAS: List[str] = [
    "augustine", "aug_mound", "aug_lagoon",
    "cleveland_clcl", "cleveland_clco", "cleveland_cles", "cleveland_clne_vis", "cleveland_nikh",
    "redoubt", "redoubt-2", "redoubt-3", "Redoubt-LL",
    "spurr_spcl", "spurr_spcr", "Spurr_ANCW",
    "iliamna_ive", "iliamna_ilcb",
    "shishaldin_brpk", "shishaldin_islz", "shishaldin_wtug2",
    "pavlof_blha", "pavlof_dol", "pavlof_ps1a",
    "okmok_okcf", "okif",
    "kanaga", "kanaga_kimd",
    "gsitkin", "gsitkin_gsck", "gsitkin_gsig",
    "lsitkin_lspa",
    "veniaminof_vncg",
    "katmai_kakn", "katmai_kabu", "katmai_kab2", "katmai_cahl",
    "wrangell_waza",
    "semi_cepe", "semi_cetu",
    "aniakchak_ansl", "aniakchak_pth",
    "akunIsland-N", "akunIsland-NW",
    "mrep",
]


# ===========================================================================
# Low-level HTTP helpers
# ===========================================================================

_DEFAULT_UA = "USGS-VolcanoCam-Client/2.0 (python urllib)"


def _get(url: str, timeout: int = 20, params: Optional[Dict] = None) -> bytes:
    """GET a URL and return raw bytes."""
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        url = f"{url}?{qs}" if "?" not in url else f"{url}&{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url: str, timeout: int = 20, params: Optional[Dict] = None) -> Any:
    raw = _get(url, timeout=timeout, params=params)
    return json.loads(raw.decode("utf-8"))


def _post_json(url: str, body: Dict, timeout: int = 20) -> Any:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "User-Agent": _DEFAULT_UA,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ===========================================================================
# VHP VSC APIs  (volcanoes.usgs.gov/vsc/api/)
# ===========================================================================

class VHPVolcanoAPI:
    """
    VHP Volcano API — volcano metadata, alert status, GeoJSON.
    Base URL: https://volcanoes.usgs.gov/vsc/api/volcanoApi/

    Key endpoints:
      GET /volcanoesUS            — all US volcanoes
      GET /volcanoesGVP           — worldwide volcanoes (Smithsonian GVP, ~1470)
      GET /vhpstatus              — alert status for all US volcanoes
      GET /vhpstatus/{id}         — status for one volcano
      GET /geojson                — all US volcanoes as GeoJSON
      GET /geojson?lat1&lat2&long1&long2 — bounding-box GeoJSON
      GET /elevated               — volcanoes above NORMAL/GREEN
      GET /volcano?vnum={v}       — single volcano by GVP number
      GET /volcano?volcanoCd={cd} — single volcano by USGS code
      GET /volcanoStationPlots/{v} — monitoring station plots
    """

    BASE = f"{VSC_BASE}/volcanoApi"

    def get_us_volcanoes(self) -> List[Dict]:
        """Return metadata for all US volcanoes.

        Fields: vnum, volcanoCd, vName, country, subregion, latitude,
                longitude, elevation_m, obsAbbr, webpage, NVEWS
        """
        return _get_json(f"{self.BASE}/volcanoesUS")

    def get_worldwide_volcanoes(self) -> List[Dict]:
        """Return all ~1470 worldwide volcanoes from Smithsonian GVP."""
        return _get_json(f"{self.BASE}/volcanoesGVP")

    def get_all_status(self, obs: Optional[str] = None) -> List[Dict]:
        """Return VHP status for all US volcanoes.

        Args:
            obs: Optional filter — avo | calvo | cvo | hvo | nmi | yvo

        Returns list of dicts with vName, alertLevel, colorCode,
        noticeSynopsis, statusIconUrl, nvewsThreat, ...
        """
        params = {"obs": obs} if obs else None
        return _get_json(f"{self.BASE}/vhpstatus", params=params)

    def get_status(self, volcano_id: str) -> Dict:
        """Return current status for a single volcano.

        Args:
            volcano_id: vnum (e.g. "332010") or volcanoCd (e.g. "hi3")
        """
        return _get_json(f"{self.BASE}/vhpstatus/{volcano_id}")

    def get_geojson(self) -> Dict:
        """Return all US volcanoes as a GeoJSON FeatureCollection.

        properties includes: volcanoName, vnum, volcanoCd, alertLevel,
        colorCode, noticeSynopsis, noticeUrl, statusIconUrl, nvewsThreat
        """
        return _get_json(f"{self.BASE}/geojson")

    def get_geojson_region(
        self,
        lat1: float, lat2: float,
        lon1: float, lon2: float,
    ) -> Dict:
        """Return GeoJSON for volcanoes within a lat/lon bounding box."""
        params = {"lat1": lat1, "lat2": lat2, "long1": lon1, "long2": lon2}
        return _get_json(f"{self.BASE}/geojson", params=params)

    def get_elevated(self, obs: Optional[str] = None) -> List[Dict]:
        """Return volcanoes with elevated activity (above NORMAL/GREEN).

        Fields: noticeId, vName, vnum, volcanoCd, nvewsThreat, alertLevel,
        colorCode, alertLevelPrev, colorCodePrev, noticeSynopsis, noticeUrl
        """
        params = {"obs": obs} if obs else None
        return _get_json(f"{self.BASE}/elevated", params=params)

    def get_volcano(
        self,
        vnum: Optional[str] = None,
        volcano_cd: Optional[str] = None,
    ) -> Dict:
        """Return detailed metadata (including boundary polygon) for one volcano.

        Provide either vnum or volcano_cd.
        Returns: volcano_name, latitude, longitude, url, vnum, volcanoCd, boundary[]
        """
        if vnum:
            params: Dict = {"vnum": vnum}
        elif volcano_cd:
            params = {"volcanoCd": volcano_cd}
        else:
            raise ValueError("Provide vnum or volcano_cd")
        return _get_json(f"{self.BASE}/volcano", params=params)

    def get_station_plots(self, vnum: str) -> Dict:
        """Return monitoring station plots for a volcano.

        The response includes seismometer, GPS, tiltmeter, and SO2 plots.
        Plot URLs follow:
          https://volcanoes.usgs.gov/vsc/captures/{volcano_name}/{STATION}-{PERIOD}.png

        Note: USGS asks that automated processes wait at least 10 minutes
        between re-querying this endpoint.

        Returns dict with metadata, volcano, stations[]:
          station, latitude, longitude, distance_km,
          plots[]: category, plot_label, plot_url, plot_age_sec,
                   approximate_update_frequency_min, file_size_bytes
        """
        return _get_json(f"{self.BASE}/volcanoStationPlots/{vnum}")


class VHPObservatoryAPI:
    """
    VHP Observatory API.
    Base URL: https://volcanoes.usgs.gov/vsc/api/observatoryApi/

    Observatories: AVO | CalVO | CVO | HVO | NMI | YVO
    """

    BASE = f"{VSC_BASE}/observatoryApi"

    def get_all(self) -> List[Dict]:
        """Return all observatories with boundary polygons.

        Fields: obsAbbr, observatory, lat, long, boundary[]
        """
        return _get_json(f"{self.BASE}/observatories")

    def get_one(self, obs_abbr: str) -> Dict:
        """Return a single observatory.

        Args:
            obs_abbr: AVO | CalVO | CVO | HVO | NMI | YVO
        """
        return _get_json(f"{self.BASE}/observatory/{obs_abbr}")


class VHPHansAPI:
    """
    Legacy HANS API via VSC.
    Base URL: https://volcanoes.usgs.gov/vsc/api/hansApi/

    Prefer HANSPublicAPI (hans-public) for newer features.
    """

    BASE = f"{VSC_BASE}/hansApi"

    def get_notice(self, notice_id: str) -> Dict:
        """Return a notice by its full identifier."""
        return _get_json(f"{self.BASE}/notice/{notice_id}")

    def get_notice_section(self, section_id: str) -> Dict:
        """Return a single-volcano section of a notice."""
        return _get_json(f"{self.BASE}/noticeSection/{section_id}")

    def get_vonas(self, obs: Optional[str] = None) -> List[Dict]:
        """Return all VONAs (newest first).

        Args:
            obs: avo | calvo | cvo | hvo | nmi | yvo
        """
        params = {"obs": obs} if obs else None
        return _get_json(f"{self.BASE}/vonas", params=params)

    def get_recent_vonas(self, days_old: int = 30, obs: Optional[str] = None) -> List[Dict]:
        """Return VONAs from the last N days."""
        url = f"{self.BASE}/vonas/{days_old}"
        params = {"obs": obs} if obs else None
        return _get_json(url, params=params)

    def get_newest(self, obs: Optional[str] = None) -> List[Dict]:
        """Return the newest notice from each observatory."""
        params = {"obs": obs} if obs else None
        return _get_json(f"{self.BASE}/newest", params=params)

    def get_newest_for_volcano(self, vnum: str) -> Dict:
        """Return the newest notice for a volcano by vnum."""
        return _get_json(f"{self.BASE}/volcNewest/{vnum}")


class VHPVolcanoMessageAPI:
    """
    Volcano Message API — short status snippets shown on USGS web pages.
    Base URL: https://volcanoes.usgs.gov/vsc/api/volcanoMessageApi/

    Currently only Kilauea (vnum=332010) has messages.
    """

    BASE = f"{VSC_BASE}/volcanoMessageApi"

    def get_newest(self, vnum: str) -> Dict:
        """Return the most recent message for a volcano.

        Returns: obsAbbr, vName, vnum, title, message, id, timestamp,
                 pubDate, pubDateHst
        """
        return _get_json(f"{self.BASE}/volcanoNewest/{vnum}")

    def get_recent(
        self,
        vnum: str,
        limit: Optional[int] = None,
        days_back: Optional[int] = None,
    ) -> List[Dict]:
        """Return recent messages.

        Args:
            limit: Max messages (most recent first)
            days_back: Return messages from last N days
        """
        params: Dict = {}
        if limit is not None:
            params["limit"] = limit
        if days_back is not None:
            params["daysBack"] = days_back
        return _get_json(f"{self.BASE}/volcanoRecent/{vnum}", params=params)


class VHPHvoWebcamsAPI:
    """
    HVO Webcams API via VSC.
    Base URL: https://volcanoes.usgs.gov/vsc/api/hvoWebcamsApi/

    Note: As of early 2026 these endpoints return empty arrays.
    Use HVOClient (legacy /cams/ system) for active camera images.
    """

    BASE = f"{VSC_BASE}/hvoWebcamsApi"

    def get_all_cams(self) -> List[Dict]:
        return _get_json(f"{self.BASE}/cams")

    def get_cams_by_region(self) -> List[Dict]:
        return _get_json(f"{self.BASE}/regionsAndCams")

    def get_webcam(self, webcam_code: str) -> Dict:
        return _get_json(f"{self.BASE}/webcam/{webcam_code}")

    def get_volcano_webcams(self, vnum: str) -> List[Dict]:
        return _get_json(f"{self.BASE}/vnum/{vnum}")


# ===========================================================================
# HANS Public API  (volcanoes.usgs.gov/hans-public/api/)
# ===========================================================================

class HANSPublicAPI:
    """
    HANS Public API — cleaner, newer facade over the HANS notification system.
    Base URL: https://volcanoes.usgs.gov/hans-public/api/

    Subsystems: volcano/ | notice/ | map/ | search/
    """

    BASE = HANS_BASE

    # ---- Volcano ----------------------------------------------------------

    def get_us_volcanoes(self) -> List[Dict]:
        """Return all US volcanoes."""
        return _get_json(f"{self.BASE}/volcano/getUSVolcanoes")

    def get_volcano(self, vnum_or_cd: str) -> Dict:
        """Return info for one volcano by vnum or volcanoCd."""
        return _get_json(f"{self.BASE}/volcano/getVolcano/{vnum_or_cd}")

    def get_elevated_volcanoes(self) -> List[Dict]:
        """Return volcanoes at elevated alert (YELLOW/ORANGE/RED).

        Fields: obs_fullname, obs_abbr, volcano_name, vnum, notice_type_cd,
                notice_identifier, sent_utc, sent_unixtime, color_code,
                alert_level, notice_url, notice_data
        """
        return _get_json(f"{self.BASE}/volcano/getElevatedVolcanoes")

    def get_monitored_volcanoes(self) -> List[Dict]:
        """Return all volcanoes actively monitored by USGS."""
        return _get_json(f"{self.BASE}/volcano/getMonitoredVolcanoes")

    def get_cap_elevated(self) -> Any:
        """Return CAP (Common Alerting Protocol) for highly elevated volcanoes."""
        return _get_json(f"{self.BASE}/volcano/getCapElevated")

    def get_newest_for_volcano(self, vnum_or_cd: str) -> List[Dict]:
        """Return notice sections for the newest notice for a volcano."""
        return _get_json(f"{self.BASE}/volcano/newestForVolcano/{vnum_or_cd}")

    # ---- Notice -----------------------------------------------------------

    def get_notice(self, notice_id: str) -> str:
        """Return HTML for a notice by identifier."""
        return _get(f"{self.BASE}/notice/getNotice/{notice_id}").decode("utf-8")

    def get_notice_formatted(self, notice_id: str, fmt: str = "json") -> Any:
        """Return a notice in requested format: json | html | text | sms."""
        url = f"{self.BASE}/notice/getNoticeFormatted/{notice_id}/{fmt}"
        raw = _get(url)
        if fmt == "json":
            return json.loads(raw.decode("utf-8"))
        return raw.decode("utf-8")

    def get_notice_parts(self, notice_id: str) -> Dict:
        """Return individual notice sections as JSON."""
        return _get_json(f"{self.BASE}/notice/getNoticeParts/{notice_id}")

    def get_recent_notices(self) -> List[Dict]:
        """Return all notices from the last ~month."""
        return _get_json(f"{self.BASE}/notice/getRecentNotices")

    def get_newest_or_recent(self) -> List[Dict]:
        """Return newest per observatory or recent if sent recently."""
        return _get_json(f"{self.BASE}/notice/getNewestOrRecent")

    def get_notices_last_day_html(self) -> str:
        """Return HTML of all notices from the last 24 hours."""
        return _get(f"{self.BASE}/notice/getNoticesLastDayHTML").decode("utf-8")

    def get_recent_notices_by_obs(self, obs: str = "all", days: int = 7) -> List[Dict]:
        """Return notices by observatory for last N days.

        Args:
            obs: all | avo | calvo | cvo | hvo | nmi | yvo
            days: integer 1–7
        """
        return _get_json(f"{self.BASE}/notice/recent/{obs}/{days}")

    def get_vona(self, notice_id: str) -> str:
        """Return HTML for a VONA."""
        return _get(f"{self.BASE}/notice/getVona/{notice_id}").decode("utf-8")

    def get_vonas_last_year(self) -> List[Dict]:
        """Return all VONAs from the last year."""
        return _get_json(f"{self.BASE}/notice/getVonasWithinLastYear")

    def get_daily_summary_data(self) -> Dict:
        """Return data for daily summary report."""
        return _get_json(f"{self.BASE}/notice/getDailySummaryData")

    # ---- Map --------------------------------------------------------------

    def get_map_highlights(self) -> str:
        """Return XML markers for volcanoes with recent notices."""
        return _get(f"{self.BASE}/map/highlights").decode("utf-8")

    def get_vhp_status_xml(self) -> str:
        """Return VHP status as XML."""
        return _get(f"{self.BASE}/map/getVhpStatus").decode("utf-8")

    # ---- Search -----------------------------------------------------------

    def get_notice_types(self) -> List[Dict]:
        """Return the list of HANS notice type codes."""
        return _get_json(f"{self.BASE}/search/getHansNoticeTypes")

    def get_volcanoes_with_notice(self) -> List[Dict]:
        """Return all volcanoes that have any HANS notice."""
        return _get_json(f"{self.BASE}/search/getAllVolcanoesWithNotice")

    def search_notices(
        self,
        obs_abbr: Optional[str] = None,
        notice_type_cd: Optional[str] = None,
        volc_cd: Optional[str] = None,
        start_unixtime: Optional[int] = None,
        end_unixtime: Optional[int] = None,
        search_text: Optional[str] = None,
        page_index: int = 0,
    ) -> Dict:
        """Search historical HANS notices.

        Args:
            obs_abbr: e.g. "avo", "hvo"
            notice_type_cd: "WU" (weekly), "DU" (daily), "IS" (info stmt),
                            "VAN" (volcanic activity notice)
            volc_cd: USGS volcano code, e.g. "ak124"
            start_unixtime, end_unixtime: Unix timestamps
            search_text: Free-text within notice body
            page_index: 0-based page for pagination

        Returns dict with count and matching notices.
        """
        body: Dict[str, Any] = {"pageIndex": page_index}
        if obs_abbr:
            body["obsAbbr"] = obs_abbr
        if notice_type_cd:
            body["noticeTypeCd"] = notice_type_cd
        if volc_cd:
            body["volcCd"] = volc_cd
        if start_unixtime is not None:
            body["startUnixtime"] = start_unixtime
        if end_unixtime is not None:
            body["endUnixtime"] = end_unixtime
        if search_text:
            body["searchText"] = search_text
        return _post_json(f"{self.BASE}/search/search", body)

    def search_preflight(
        self,
        obs_abbr: Optional[str] = None,
        notice_type_cd: Optional[str] = None,
        volc_cd: Optional[str] = None,
        start_unixtime: Optional[int] = None,
        end_unixtime: Optional[int] = None,
        search_text: Optional[str] = None,
    ) -> Dict:
        """Get result count before running a full search."""
        body: Dict[str, Any] = {}
        if obs_abbr:
            body["obsAbbr"] = obs_abbr
        if notice_type_cd:
            body["noticeTypeCd"] = notice_type_cd
        if volc_cd:
            body["volcCd"] = volc_cd
        if start_unixtime is not None:
            body["startUnixtime"] = start_unixtime
        if end_unixtime is not None:
            body["endUnixtime"] = end_unixtime
        if search_text:
            body["searchText"] = search_text
        return _post_json(f"{self.BASE}/search/preflight", body)


# ===========================================================================
# HVO Legacy System  (volcanoes.usgs.gov/cams/)
# ===========================================================================

class HVOClient:
    """
    Hawaii Volcano Observatory webcam client using the legacy /cams/ system.

    Image URL:      https://volcanoes.usgs.gov/cams/{CAMID}/images/M.jpg
    Timestamp file: https://volcanoes.usgs.gov/cams/{CAMID}/images/js.js
    Viewer page:    https://volcanoes.usgs.gov/cams/panorama.php?cam={CAMID}

    Only one size is available: M.jpg (no thumbnails/large variants).
    """

    BASE = HVO_BASE

    def list_cameras(
        self,
        volcano: Optional[str] = None,
        thermal_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return the HVO camera inventory (static list).

        Args:
            volcano: Filter by volcano name ("Kilauea" or "Mauna Loa")
            thermal_only: If True, return only thermal cameras
        """
        cams = HVO_CAMERAS
        if volcano:
            cams = [c for c in cams if c["volcano"].lower() == volcano.lower()]
        if thermal_only:
            cams = [c for c in cams if c["thermal"]]
        return cams

    def image_url(self, cam_id: str) -> str:
        """Return the current-image URL for an HVO camera."""
        return f"{self.BASE}/cams/{cam_id}/images/M.jpg"

    def viewer_url(self, cam_id: str) -> str:
        """Return the human-readable viewer page URL."""
        return f"{self.BASE}/cams/panorama.php?cam={cam_id}"

    def get_image(self, cam_id: str) -> bytes:
        """Download and return the current JPEG bytes for cam_id."""
        return _get(self.image_url(cam_id))

    def get_metadata(self, cam_id: str) -> Dict[str, Any]:
        """Parse metadata from the camera's js.js timestamp sidecar.

        Returns: cam_id, datetime_hst, frames[], image_url
        """
        js_url = f"{self.BASE}/cams/{cam_id}/images/js.js"
        raw = _get(js_url).decode("utf-8")
        dt_match = re.search(r'datetime\s*=\s*"([^"]+)"', raw)
        frames_match = re.search(r'frames\s*=\s*new Array\(([^)]*)\)', raw)
        frames: List[str] = []
        if frames_match:
            frames = [f.strip().strip('"') for f in frames_match.group(1).split(",") if f.strip()]
        return {
            "cam_id": cam_id,
            "datetime_hst": dt_match.group(1) if dt_match else None,
            "frames": frames,
            "image_url": self.image_url(cam_id),
        }

    def get_all_images(
        self,
        volcano: Optional[str] = None,
        thermal_only: bool = False,
    ) -> Iterator[Tuple[str, bytes]]:
        """Yield (cam_id, jpeg_bytes) for every matching camera.

        Skips cameras that return HTTP errors (yields empty bytes).
        """
        for cam in self.list_cameras(volcano=volcano, thermal_only=thermal_only):
            cam_id = cam["cam_id"]
            try:
                data = self.get_image(cam_id)
            except Exception:
                data = b""
            yield cam_id, data


# ===========================================================================
# ASHCAM REST API client (shared base for AVO and VolcView)
# ===========================================================================

class _AshcamAPIClient:
    """
    Generic client for the ASHCAM REST API.

    AVO primary:    https://avo.alaska.edu/ashcam-api/
    VolcView mirror: https://volcview.wr.usgs.gov/ashcam-api/

    Image URL patterns:
      AVO current:   {base}/images/{CAMCODE}/current.jpg
      AVO archive:   {base}/images/{CAMCODE}/{YYYY}/{DOY}/{CAMCODE}-{ISO8601Z}.jpg
      VV  current:   {base}/images/webcams/{CAMCODE}/current.jpg  (VolcView only)
    """

    def __init__(self, api_base: str):
        self._base = api_base.rstrip("/")

    # ---- Webcam metadata --------------------------------------------------

    def list_cameras(self) -> List[Dict[str, Any]]:
        """Return all webcam objects from the API."""
        data = _get_json(f"{self._base}/webcamApi/webcams")
        return data.get("webcams", data) if isinstance(data, dict) else data

    def get_camera(self, cam_code: str) -> Dict[str, Any]:
        """Return metadata for a single camera.

        Returned dict includes:
          webcamCode, webcamName, latitude, longitude, elevationM, bearingDeg,
          vnum, vName, hasImages, imageTotal, firstImageDate, lastImageDate,
          currentImageUrl, currentMediumImageUrl, currentThumbImageUrl,
          clearImageUrl, newestImage{imageId, imageTimestamp, imageUrl,
                                     interestingCode, isNighttimeInd},
          suninfo{civil_twilight_sunrise, civil_twilight_sunset},
          organization, isPublic, hasArchiveImages, volcanoes[], lists[]
        """
        data = _get_json(f"{self._base}/webcamApi/webcam/{cam_code}")
        return data.get("webcam", data) if isinstance(data, dict) and "webcam" in data else data

    def current_image_url(self, cam_code: str, size: str = "full") -> str:
        """Return the URL for the most-recent image without downloading it.

        Args:
            cam_code: Camera code
            size: "full" | "medium" | "thumb"
        """
        cam = self.get_camera(cam_code)
        key = {"full": "currentImageUrl", "medium": "currentMediumImageUrl",
               "thumb": "currentThumbImageUrl"}.get(size)
        if not key:
            raise ValueError(f"Unknown size {size!r}")
        return cam.get(key, "")

    def get_current_image(self, cam_code: str, size: str = "full") -> bytes:
        """Download and return the current JPEG for cam_code."""
        url = self.current_image_url(cam_code, size=size)
        if not url:
            raise ValueError(f"No image URL for camera {cam_code!r}")
        return _get(url)

    def get_geojson(
        self,
        lat1: float, lat2: float,
        lon1: float, lon2: float,
    ) -> Dict[str, Any]:
        """Return GeoJSON FeatureCollection for cameras in a bounding box.

        Args:
            lat1, lat2: Latitude range (south, north)
            lon1, lon2: Longitude range (west, east) — use negative values for west
        """
        params = {"lat1": lat1, "lat2": lat2, "long1": lon1, "long2": lon2}
        return _get_json(f"{self._base}/webcamApi/geojson", params=params)

    # ---- Image retrieval --------------------------------------------------

    def list_images(
        self,
        cam_code: str,
        days: int = 1,
        order: str = "newestFirst",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return image records from the last N days.

        Returns list of dicts: imageId, md5, webcamCode, imageTimestamp,
        imageDate, isNighttimeInd, interestingCode, imageUrl, suninfo

        interestingCode: N=quiet, V=volcanic activity, U=unknown
        """
        url = f"{self._base}/imageApi/webcam/{cam_code}/{days}/{order}/{limit}"
        data = _get_json(url)
        return data.get("images", data) if isinstance(data, dict) else data

    def list_images_range(
        self,
        cam_code: str,
        start_ts: int,
        end_ts: int,
        order: str = "newestFirst",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return image records between two Unix timestamps."""
        params = {
            "webcamCode": cam_code,
            "startTimestamp": start_ts,
            "endTimestamp": end_ts,
            "order": order,
            "limit": limit,
        }
        data = _get_json(f"{self._base}/imageApi/webcam", params=params)
        return data.get("images", data) if isinstance(data, dict) else data

    def list_archive_images(
        self,
        cam_code: str,
        start_ts: int,
        end_ts: int,
        order: str = "newestFirst",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return archived historical images (max 5000 per request)."""
        params = {
            "webcamCode": cam_code,
            "startTimestamp": start_ts,
            "endTimestamp": end_ts,
            "order": order,
            "limit": limit,
        }
        data = _get_json(f"{self._base}/imageApi/archive/webcam", params=params)
        return data.get("images", data) if isinstance(data, dict) else data

    def list_all_images(self, cam_code: str) -> List[Dict[str, Any]]:
        """Return ALL image records (may be very large)."""
        data = _get_json(f"{self._base}/imageApi/webcam/{cam_code}")
        return data.get("images", data) if isinstance(data, dict) else data

    def get_recent_images(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the N most-recent images across all cameras."""
        data = _get_json(f"{self._base}/imageApi/recent/{limit}")
        return data.get("images", data) if isinstance(data, dict) else data

    def get_interesting_images(self, days: int = 30) -> List[Dict[str, Any]]:
        """Return images tagged as showing volcanic activity (interestingCode=V).

        Args:
            days: Limit to the past N days
        """
        data = _get_json(f"{self._base}/imageApi/interesting/{days}")
        return data.get("images", data) if isinstance(data, dict) else data

    def get_uninteresting_images(self, days: int = 7) -> List[Dict[str, Any]]:
        """Return images with no volcanic activity (interestingCode=N).

        Args:
            days: Required. Limit to past N days.
        """
        data = _get_json(f"{self._base}/imageApi/uninteresting/{days}")
        return data.get("images", data) if isinstance(data, dict) else data

    def download_image(self, image_record: Dict[str, Any]) -> bytes:
        """Download JPEG bytes from an image record returned by list_images."""
        url = image_record.get("imageUrl", "")
        if not url:
            raise ValueError("image_record has no imageUrl")
        return _get(url)

    # ---- Static URL helpers -----------------------------------------------

    @staticmethod
    def build_image_url(api_base: str, cam_code: str, dt: datetime) -> str:
        """Construct the archive image URL for a specific UTC datetime.

        Pattern: {base}/images/{cam}/{YYYY}/{DOY}/{cam}-{YYYYMMDD}T{HHMMSS}Z.jpg

        DOY is numeric day-of-year without leading zeros.
        """
        year = dt.strftime("%Y")
        doy = str(int(dt.strftime("%j")))  # strip leading zeros
        ts = dt.strftime("%Y%m%dT%H%M%SZ")
        return f"{api_base}/images/{cam_code}/{year}/{doy}/{cam_code}-{ts}.jpg"

    @staticmethod
    def parse_image_url(image_url: str) -> Dict[str, str]:
        """Extract components from an AVO image URL.

        Returns: webcam_code, year, day_of_year, timestamp_str
        """
        parts = image_url.rstrip("/").split("/")
        filename = parts[-1]                          # e.g. "augustine-20260327T172000Z.jpg"
        doy = parts[-2]
        year = parts[-3]
        webcam_code = parts[-4]
        ts = filename.replace(f"{webcam_code}-", "").replace(".jpg", "")
        return {
            "webcam_code": webcam_code,
            "year": year,
            "day_of_year": doy,
            "timestamp_str": ts,
        }


# ===========================================================================
# Observatory-specific ASHCAM wrappers
# ===========================================================================

class AVOClient(_AshcamAPIClient):
    """
    Alaska Volcano Observatory webcam client.
    API: https://avo.alaska.edu/ashcam-api/

    386 cameras including FAA weather cams with volcano views.
    Archives go back to 2020 for most cameras.
    """

    def __init__(self):
        super().__init__(AVO_API)

    def cameras_for_volcano(self, volcano_name: str) -> List[Dict[str, Any]]:
        """Return AVO cameras whose vName matches volcano_name (case-insensitive)."""
        name_lower = volcano_name.lower()
        return [
            c for c in self.list_cameras()
            if (c.get("vName") or "").lower() == name_lower
            or name_lower in (c.get("webcamName") or "").lower()
        ]

    def get_volcano_webcams(self, volcano_cd: str) -> List[Dict[str, Any]]:
        """Return cameras for an AVO volcano code (e.g. "ak252" for Shishaldin)."""
        data = _get_json(
            f"{self._base}/webcamApi/volcanoWebcams",
            params={"volcano": volcano_cd},
        )
        return data.get("webcams", data) if isinstance(data, dict) else data

    def get_archived_webcams(self) -> List[Dict[str, Any]]:
        """Return webcams that have historical archived images."""
        data = _get_json(f"{self._base}/webcamApi/archivedWebcams")
        return data.get("webcams", data) if isinstance(data, dict) else data

    def notable_cameras(self) -> List[str]:
        """Return the curated list of volcano-monitoring camera codes."""
        return list(AVO_NOTABLE_CAMERAS)


class CVOClient(_AshcamAPIClient):
    """
    Cascades Volcano Observatory webcam client.
    API: https://volcview.wr.usgs.gov/ashcam-api/

    Camera codes: msh-*, rainier-*, baker-*, adams-*, hood-*,
                  glacierpeak-*, threesis-*, crater-*, shasta-*

    Also maintains a legacy public webcam at:
        https://volcanoes.usgs.gov/vsc/captures/st_helens/jro-webcam.jpg
    """

    LEGACY_JRO_URL = f"{HVO_BASE}/vsc/captures/st_helens/jro-webcam.jpg"

    def __init__(self):
        super().__init__(VV_API)

    def list_cameras(self) -> List[Dict[str, Any]]:  # type: ignore[override]
        """Return static CVO camera inventory."""
        return CVO_CAMERAS

    def cameras_for_volcano(self, volcano_name: str) -> List[Dict[str, Any]]:
        lower = volcano_name.lower()
        return [c for c in CVO_CAMERAS if lower in c["volcano"].lower()]

    def get_legacy_jro_image(self) -> bytes:
        """Download the Johnston Ridge Observatory legacy JPEG."""
        return _get(self.LEGACY_JRO_URL)


class YVOClient(_AshcamAPIClient):
    """
    Yellowstone Volcano Observatory webcam client.
    API: https://volcview.wr.usgs.gov/ashcam-api/
    """

    def __init__(self):
        super().__init__(VV_API)

    def list_cameras(self) -> List[Dict[str, Any]]:  # type: ignore[override]
        """Return static YVO camera inventory."""
        return YVO_CAMERAS


# ===========================================================================
# Unified multi-observatory / multi-API client
# ===========================================================================

class USGSVolcanoCamClient:
    """
    Unified USGS Volcano Webcams and Monitoring Data Client.

    Provides access to all discovered API systems:
      .hvo       — HVO legacy webcam system (Hawaii)
      .avo       — AVO Ashcam API (Alaska, 386 cameras)
      .cvo       — CVO via VolcView (Cascades)
      .yvo       — YVO via VolcView (Yellowstone)
      .volcano   — VHP Volcano API (status, GeoJSON, metadata)
      .obs       — VHP Observatory API
      .hans_vsc  — Legacy HANS VSC API
      .hans      — HANS Public API (preferred for notices/search)
      .msg       — Volcano Message API (Kilauea snippets)
      .hvo_api   — HVO Webcams VSC API (may return empty)

    Usage:
        client = USGSVolcanoCamClient()

        # Volcano status
        status = client.get_volcano_status("332010")  # Kilauea by vnum

        # All elevated volcanoes right now
        elevated = client.get_elevated_volcanoes()

        # AVO webcams
        cams = client.avo.list_cameras()
        jpeg = client.avo.get_current_image("augustine")

        # HVO thermal cam
        jpeg = client.hvo.get_image("F1cam")

        # Recent volcanic-activity images
        hot = client.avo.get_interesting_images(days=7)

        # Historical notice search
        results = client.hans.search_notices(obs_abbr="hvo", days=30)
    """

    def __init__(self):
        self._hvo:     Optional[HVOClient]           = None
        self._avo:     Optional[AVOClient]            = None
        self._cvo:     Optional[CVOClient]            = None
        self._yvo:     Optional[YVOClient]            = None
        self._volcano: Optional[VHPVolcanoAPI]        = None
        self._obs:     Optional[VHPObservatoryAPI]    = None
        self._hans_vsc: Optional[VHPHansAPI]          = None
        self._hvo_api: Optional[VHPHvoWebcamsAPI]     = None
        self._msg:     Optional[VHPVolcanoMessageAPI] = None
        self._hans:    Optional[HANSPublicAPI]        = None

    @property
    def hvo(self) -> HVOClient:
        if self._hvo is None:
            self._hvo = HVOClient()
        return self._hvo

    @property
    def avo(self) -> AVOClient:
        if self._avo is None:
            self._avo = AVOClient()
        return self._avo

    @property
    def cvo(self) -> CVOClient:
        if self._cvo is None:
            self._cvo = CVOClient()
        return self._cvo

    @property
    def yvo(self) -> YVOClient:
        if self._yvo is None:
            self._yvo = YVOClient()
        return self._yvo

    @property
    def volcano(self) -> VHPVolcanoAPI:
        if self._volcano is None:
            self._volcano = VHPVolcanoAPI()
        return self._volcano

    @property
    def obs(self) -> VHPObservatoryAPI:
        if self._obs is None:
            self._obs = VHPObservatoryAPI()
        return self._obs

    @property
    def hans_vsc(self) -> VHPHansAPI:
        if self._hans_vsc is None:
            self._hans_vsc = VHPHansAPI()
        return self._hans_vsc

    @property
    def hvo_api(self) -> VHPHvoWebcamsAPI:
        if self._hvo_api is None:
            self._hvo_api = VHPHvoWebcamsAPI()
        return self._hvo_api

    @property
    def msg(self) -> VHPVolcanoMessageAPI:
        if self._msg is None:
            self._msg = VHPVolcanoMessageAPI()
        return self._msg

    @property
    def hans(self) -> HANSPublicAPI:
        if self._hans is None:
            self._hans = HANSPublicAPI()
        return self._hans

    # ---- Convenience pass-throughs ----------------------------------------

    def get_us_volcanoes(self) -> List[Dict]:
        """Return all US volcanoes."""
        return self.volcano.get_us_volcanoes()

    def get_volcano_status(self, volcano_id: str) -> Dict:
        """Return current alert status for a volcano (vnum or volcanoCd).

        Returns: alertLevel, colorCode, noticeSynopsis, nvewsThreat, ...
        """
        return self.volcano.get_status(volcano_id)

    def get_elevated_volcanoes(self) -> List[Dict]:
        """Return currently elevated volcanoes (HANS Public API)."""
        return self.hans.get_elevated_volcanoes()

    def get_volcanoes_geojson(self) -> Dict:
        """Return all US volcanoes as GeoJSON FeatureCollection."""
        return self.volcano.get_geojson()

    def get_recent_alerts(self, days: int = 7) -> List[Dict]:
        """Return notices from the last N days (1–7) across all observatories."""
        return self.hans.get_recent_notices_by_obs(obs="all", days=min(days, 7))

    # ---- Cross-observatory helpers ----------------------------------------

    def all_camera_inventory(self) -> Dict[str, Any]:
        """Return static camera inventory for all observatories (no network calls)."""
        return {
            "HVO": HVO_CAMERAS,
            "CVO": CVO_CAMERAS,
            "YVO": YVO_CAMERAS,
            "AVO_notable": [{"cam_id": c, "volcano": "Alaska"} for c in AVO_NOTABLE_CAMERAS],
        }

    def get_camera_image(
        self,
        observatory: str,
        cam_id: str,
        size: str = "full",
    ) -> bytes:
        """Download a current image from any observatory.

        Args:
            observatory: "HVO" | "AVO" | "CVO" | "YVO"
            cam_id: Camera code
            size: "full" | "medium" | "thumb" (medium/thumb for ASHCAM only)
        """
        obs = observatory.upper()
        if obs == "HVO":
            return self.hvo.get_image(cam_id)
        if obs == "AVO":
            return self.avo.get_current_image(cam_id, size=size)
        if obs == "CVO":
            if cam_id == "jro-webcam":
                return self.cvo.get_legacy_jro_image()
            return self.cvo.get_current_image(cam_id, size=size)
        if obs == "YVO":
            return self.yvo.get_current_image(cam_id, size=size)
        raise ValueError(f"Unknown observatory {observatory!r}")

    def get_historical_images(
        self,
        observatory: str,
        cam_id: str,
        days: int = 1,
        limit: int = 24,
    ) -> List[Dict[str, Any]]:
        """Return historical image records for AVO, CVO, or YVO cameras.

        HVO does not expose a historical image API.
        """
        obs = observatory.upper()
        if obs == "AVO":
            return self.avo.list_images(cam_id, days=days, limit=limit)
        if obs in ("CVO", "YVO"):
            client = self.cvo if obs == "CVO" else self.yvo
            return client.list_images(cam_id, days=days, limit=limit)  # type: ignore[attr-defined]
        raise ValueError(f"Historical images not available for {observatory!r}")


# ===========================================================================
# Convenience functions
# ===========================================================================

def quick_fetch_hvo(cam_id: str, save_path: Optional[str] = None) -> bytes:
    """Download the current HVO camera image. Optionally save to disk."""
    data = HVOClient().get_image(cam_id)
    if save_path:
        with open(save_path, "wb") as fh:
            fh.write(data)
    return data


def quick_fetch_avo(cam_code: str, save_path: Optional[str] = None) -> bytes:
    """Download the current AVO camera image. Optionally save to disk."""
    data = AVOClient().get_current_image(cam_code)
    if save_path:
        with open(save_path, "wb") as fh:
            fh.write(data)
    return data


def quick_fetch_yellowstone(save_path: Optional[str] = None) -> bytes:
    """Download the current Yellowstone webcam (Black Diamond Pool)."""
    data = YVOClient().get_current_image("ys-bbsn")
    if save_path:
        with open(save_path, "wb") as fh:
            fh.write(data)
    return data


def image_url_to_datetime(image_url: str) -> Optional[datetime]:
    """Parse the UTC datetime from an AVO archive image URL.

    Example:
        "…/augustine/2026/85/augustine-20260327T172000Z.jpg"
        → datetime(2026, 3, 27, 17, 20, 0, tzinfo=utc)
    """
    try:
        filename = image_url.split("/")[-1].replace(".jpg", "")
        ts = filename.split("-")[-1]   # "20260327T172000Z"
        return datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ===========================================================================
# CLI demo
# ===========================================================================

def _demo():
    print("=" * 65)
    print("USGS Volcano Webcams & Monitoring Client — Quick Demo")
    print("=" * 65)

    client = USGSVolcanoCamClient()

    # 1. US volcanoes
    us = client.get_us_volcanoes()
    print(f"\n[1] US volcanoes total: {len(us)}")

    # 2. Kilauea status
    kil = client.get_volcano_status("332010")
    print(f"\n[2] Kilauea: {kil.get('alertLevel')} / {kil.get('colorCode')}")
    print(f"    {kil.get('noticeSynopsis','')[:120]}")

    # 3. Elevated volcanoes
    elevated = client.get_elevated_volcanoes()
    print(f"\n[3] Elevated volcanoes: {len(elevated)}")
    for v in elevated:
        print(f"    {v.get('volcano_name','?'):30s}  {v.get('alert_level','?'):10s}  {v.get('color_code','?')}")

    # 4. AVO camera count + Augustine latest
    cams = client.avo.list_cameras()
    print(f"\n[4] AVO cameras total: {len(cams)}")
    aug = [c for c in cams if c.get("webcamCode") == "augustine"]
    if aug:
        ni = aug[0].get("newestImage", {})
        print(f"    Augustine latest: {ni.get('imageDate','?')}")
        print(f"    URL: {ni.get('imageUrl','?')}")

    # 5. Recent interesting (volcanic activity) images (can be slow)
    try:
        hot = client.avo.get_interesting_images(days=3)
        print(f"\n[5] AVO interesting images (last 3 days): {len(hot)}")
    except Exception as e:
        print(f"\n[5] AVO interesting images unavailable (slow endpoint): {e}")

    # 6. GeoJSON
    gj = client.get_volcanoes_geojson()
    print(f"\n[6] GeoJSON features: {len(gj.get('features', []))}")

    # 7. HVO camera list
    hvo_cams = client.hvo.list_cameras()
    thermal = [c["cam_id"] for c in hvo_cams if c["thermal"]]
    print(f"\n[7] HVO cameras: {len(hvo_cams)} total  |  thermal: {thermal}")

    # 8. Recent HANS alerts (last 3 days)
    alerts = client.get_recent_alerts(days=3)
    print(f"\n[8] HANS alerts last 3 days: {len(alerts)} notices")

    # 9. Kilauea message
    try:
        msg = client.msg.get_newest("332010")
        print(f"\n[9] Kilauea message ({msg.get('pubDateHst','?')}):")
        print(f"    {msg.get('message','')[:160]}")
    except Exception as e:
        print(f"\n[9] Kilauea message unavailable: {e}")

    print("\nDemo complete.")


if __name__ == "__main__":
    _demo()
