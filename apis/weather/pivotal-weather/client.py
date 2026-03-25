"""
Pivotal Weather API Client
==========================
Reverse-engineered internal API client for https://www.pivotalweather.com

Discovered via browser network interception on 2026-03-25.

Key findings:
- Site protected by AWS WAF (requires browser-like session cookies)
- Model map images served from: m1o.pivotalweather.com
- Analysis/observation maps served from: x-hv1.pivotalweather.com
- API endpoints on: www.pivotalweather.com (PHP backend)
- Global JS state object: pw_web_state, pw_global_data_status

Usage:
    client = PivotalWeatherClient()
    # Get latest model runs
    runs = client.get_latest_models()
    # Get a model map image URL
    url = client.get_model_map_url("gfs", "2026032418", 24, "prateptype_cat-imp", "conus")
    # Download a model map image
    client.download_model_map("gfs", "2026032418", 24, "prateptype_cat-imp", "conus", "output.png")
"""

import requests
import json
import os
import time
from typing import Optional, Dict, List, Any, Union
from urllib.parse import urlencode
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.pivotalweather.com"
MODEL_IMAGE_BASE = "https://m1o.pivotalweather.com"
ANALYSIS_IMAGE_BASE = "https://x-hv1.pivotalweather.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pivotalweather.com/model.php",
    "Origin": "https://www.pivotalweather.com",
}

# ---------------------------------------------------------------------------
# Model catalogue (discovered from pw_global_data_status.models.runs)
# ---------------------------------------------------------------------------

MODELS = {
    # --- Global deterministic models ---
    "gfs": {
        "name": "GFS (Global Forecast System)",
        "provider": "NOAA/NCEP",
        "max_fhr": 384,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "aigfs": {
        "name": "AI-GFS (Machine-Learning GFS)",
        "provider": "NOAA",
        "max_fhr": 384,
        "fhr_step": 6,
        "runs": ["00", "06", "12", "18"],
    },
    "ecmwf_full": {
        "name": "ECMWF (European Centre)",
        "provider": "ECMWF",
        "max_fhr": 360,
        "fhr_step": 6,
        "runs": ["00", "12"],
    },
    "ecmwf_aifs": {
        "name": "ECMWF AI-FS (AI Forecast System)",
        "provider": "ECMWF",
        "max_fhr": 360,
        "fhr_step": 6,
        "runs": ["00", "06", "12", "18"],
    },
    "icon": {
        "name": "ICON (Icosahedral Nonhydrostatic Model)",
        "provider": "DWD",
        "max_fhr": 180,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "ukmo_global": {
        "name": "UK Met Office Global",
        "provider": "UKMO",
        "max_fhr": 168,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "gdps": {
        "name": "GDPS (Global Deterministic Prediction System)",
        "provider": "Environment Canada",
        "max_fhr": 240,
        "fhr_step": 3,
        "runs": ["00", "12"],
    },
    # --- Regional deterministic models ---
    "nam": {
        "name": "NAM (North American Mesoscale)",
        "provider": "NOAA/NCEP",
        "max_fhr": 84,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "nam4km": {
        "name": "NAM 4km Nest",
        "provider": "NOAA/NCEP",
        "max_fhr": 60,
        "fhr_step": 1,
        "runs": ["00", "06", "12", "18"],
    },
    "hrrr": {
        "name": "HRRR (High-Resolution Rapid Refresh)",
        "provider": "NOAA/NCEP",
        "max_fhr": 48,
        "fhr_step": 1,
        "runs": ["00-23"],  # Hourly
    },
    "rap": {
        "name": "RAP (Rapid Refresh)",
        "provider": "NOAA/NCEP",
        "max_fhr": 51,
        "fhr_step": 1,
        "runs": ["00-23"],  # Hourly
    },
    "rdps": {
        "name": "RDPS (Regional Deterministic Prediction System)",
        "provider": "Environment Canada",
        "max_fhr": 84,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "hrdps": {
        "name": "HRDPS (High-Resolution Deterministic Prediction System)",
        "provider": "Environment Canada",
        "max_fhr": 48,
        "fhr_step": 1,
        "runs": ["00", "06", "12", "18"],
    },
    "rrfs_a": {
        "name": "RRFS-A (Rapid Refresh Forecast System)",
        "provider": "NOAA",
        "max_fhr": 84,
        "fhr_step": 1,
        "runs": ["00", "06", "12", "18"],
    },
    # --- High-resolution WRF models ---
    "hrwarw": {
        "name": "HRW ARW (High-Resolution Window ARW)",
        "provider": "NOAA",
        "max_fhr": 48,
        "fhr_step": 1,
        "runs": ["00", "12"],
    },
    "hrwfv3": {
        "name": "HRW FV3 (High-Resolution Window FV3)",
        "provider": "NOAA",
        "max_fhr": 60,
        "fhr_step": 1,
        "runs": ["00", "12"],
    },
    "hrwnssl": {
        "name": "HRW NSSL (High-Resolution Window NSSL)",
        "provider": "NOAA/NSSL",
        "max_fhr": 48,
        "fhr_step": 1,
        "runs": ["00", "12"],
    },
    # --- MPAS research models ---
    "mpas_gsl_g": {
        "name": "MPAS GSL Global",
        "provider": "NOAA/GSL",
        "max_fhr": 84,
        "fhr_step": 3,
        "runs": ["00", "12"],
    },
    "mpas_nssl_htpo": {
        "name": "MPAS NSSL HTPO",
        "provider": "NOAA/NSSL",
        "max_fhr": 48,
        "fhr_step": 1,
        "runs": ["00", "12"],
    },
    "mpas_nssl_rn": {
        "name": "MPAS NSSL Rain",
        "provider": "NOAA/NSSL",
        "max_fhr": 84,
        "fhr_step": 3,
        "runs": ["00", "12"],
    },
    # --- Ensemble models ---
    "gefsens": {
        "name": "GEFS Ensemble",
        "provider": "NOAA/NCEP",
        "max_fhr": 840,
        "fhr_step": 6,
        "runs": ["00", "06", "12", "18"],
    },
    "cmceens": {
        "name": "CMC Ensemble",
        "provider": "Environment Canada",
        "max_fhr": 384,
        "fhr_step": 6,
        "runs": ["00", "12"],
    },
    "epsens": {
        "name": "ECMWF ENS (EPS Ensemble)",
        "provider": "ECMWF",
        "max_fhr": 360,
        "fhr_step": 6,
        "runs": ["00", "12"],
    },
    "epsens_opendata": {
        "name": "ECMWF ENS Open Data",
        "provider": "ECMWF",
        "max_fhr": 144,
        "fhr_step": 6,
        "runs": ["00", "06", "12", "18"],
    },
    "eps_aifsens": {
        "name": "ECMWF AIFS Ensemble",
        "provider": "ECMWF",
        "max_fhr": 360,
        "fhr_step": 6,
        "runs": ["00", "12"],
    },
    "iconens": {
        "name": "ICON Ensemble",
        "provider": "DWD",
        "max_fhr": 180,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "mogrepsgens": {
        "name": "MOGREPS-G Ensemble",
        "provider": "UKMO",
        "max_fhr": 198,
        "fhr_step": 3,
        "runs": ["00", "06", "12", "18"],
    },
    "srefens": {
        "name": "SREF Ensemble (Short-Range Ensemble Forecast)",
        "provider": "NOAA/NCEP",
        "max_fhr": 87,
        "fhr_step": 3,
        "runs": ["03", "09", "15", "21"],
    },
    "cfs": {
        "name": "CFS (Climate Forecast System)",
        "provider": "NOAA/NCEP",
        "max_fhr": 768,
        "fhr_step": 6,
        "runs": ["00", "06", "12", "18"],
    },
}

# ---------------------------------------------------------------------------
# Map regions (from pw_web_state.display_attributes and URL patterns)
# ---------------------------------------------------------------------------

REGIONS = {
    # CONUS and North America
    "conus": "Continental United States",
    "namussfc": "North America",
    "ne": "Northeast US",
    "se": "Southeast US",
    "mw": "Midwest US",
    "gp": "Great Plains",
    "sw": "Southwest US",
    "nw": "Northwest US",
    # State zooms (Pivotal Plus)
    "al": "Alabama", "ak": "Alaska", "az": "Arizona",
    "ar": "Arkansas", "ca": "California", "co": "Colorado",
    "ct": "Connecticut", "de": "Delaware", "fl": "Florida",
    "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
    "il": "Illinois", "in": "Indiana", "ia": "Iowa",
    "ks": "Kansas", "ky": "Kentucky", "la": "Louisiana",
    "me": "Maine", "md": "Maryland", "ma": "Massachusetts",
    "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne_state": "Nebraska",
    "nv": "Nevada", "nh": "New Hampshire", "nj": "New Jersey",
    "nm": "New Mexico", "ny": "New York", "nc": "North Carolina",
    "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island",
    "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee",
    "tx": "Texas", "ut": "Utah", "vt": "Vermont",
    "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming",
    # International
    "europe": "Europe",
    "alaska": "Alaska",
    "hawaii": "Hawaii",
    "caribbean": "Caribbean",
    "global": "Global",
}

# ---------------------------------------------------------------------------
# Common GFS parameters (from observed URL patterns and typical PW parameters)
# ---------------------------------------------------------------------------

GFS_PARAMETERS = {
    # Surface and precipitation
    "prateptype_cat-imp": "Precip Type, Rate (imperial)",
    "prateptype_cat-met": "Precip Type, Rate (metric)",
    "sfctemp-imp": "2m Temperature (F)",
    "sfctemp-met": "2m Temperature (C)",
    "sfcdewp-imp": "2m Dew Point (F)",
    "sfcdewp-met": "2m Dew Point (C)",
    "sfcrh": "2m Relative Humidity",
    "sfcwind-imp": "10m Wind (mph)",
    "sfcwind-met": "10m Wind (km/h)",
    "sfcwindgust-imp": "10m Wind Gust (mph)",
    "sfcwindgust-met": "10m Wind Gust (km/h)",
    "sfcvis-imp": "Surface Visibility (miles)",
    "mslp": "Mean Sea Level Pressure",
    "cape": "CAPE (Convective Available Potential Energy)",
    "cin": "CIN (Convective Inhibition)",
    "capecin": "CAPE + CIN",
    "lcl": "Lifted Condensation Level",
    "liftedindex": "Lifted Index",
    "totaltotals": "Total Totals Index",
    "kindex": "K-Index",
    "sweat": "SWEAT Index",
    "theta-e": "Theta-E",
    # Upper air
    "1000-500_thick": "1000-500mb Thickness",
    "500_hgt": "500mb Height",
    "500_vort": "500mb Vorticity",
    "700_hgt": "700mb Height",
    "850_hgt": "850mb Height",
    "850t": "850mb Temperature",
    "850wind": "850mb Wind",
    "250wind": "250mb Wind (Jet Stream)",
    "300wind": "300mb Wind",
    # Precipitation accumulation
    "qpf3h-imp": "3hr QPF (in)",
    "qpf3h-met": "3hr QPF (mm)",
    "qpf6h-imp": "6hr QPF (in)",
    "qpf6h-met": "6hr QPF (mm)",
    "qpf24h-imp": "24hr QPF (in)",
    "qpf24h-met": "24hr QPF (mm)",
    "snowfall3h-imp": "3hr Snowfall (in)",
    "snowfall6h-imp": "6hr Snowfall (in)",
    "snowfall24h-imp": "24hr Snowfall (in)",
    # Snow
    "snow_depth-imp": "Snow Depth (in)",
    "snow_water": "Snow Water Equivalent",
}

# ---------------------------------------------------------------------------
# Analysis/Observation Products (from x-hv1.pivotalweather.com URL patterns)
# ---------------------------------------------------------------------------

ANALYSIS_PRODUCTS = {
    # Warnings and hazards
    "warnings/nwshaz": {
        "description": "NWS Hazard Warnings",
        "url_template": "maps/warnings/nwshaz.conus.png",
    },
    "warnings/nwshaz_thumb": {
        "description": "NWS Hazard Warnings (thumbnail)",
        "url_template": "maps/warnings/thumbs/nwshaz.conus.png",
    },
    # NDFD (National Digital Forecast Database)
    "ndfd/sfctmax": {
        "description": "NDFD Day 1 Max Temperature",
        "url_template": "maps/ndfd/latest/ndfd_sfctmax.conus.png",
    },
    # WPC (Weather Prediction Center)
    "wpc/qpf_024h": {
        "description": "WPC 24hr QPF",
        "url_template": "maps/wpc/latest/wpc_qpf_024h_p.conus.png",
    },
    # CPC (Climate Prediction Center)
    "cpc/610temp": {
        "description": "CPC 6-10 Day Temperature Outlook",
        "url_template": "maps/cpc/latest/610temp.conus.png",
    },
    # SPC (Storm Prediction Center)
    "spc/d1four_panel": {
        "description": "SPC Day 1 Four-Panel Severe Weather Outlook",
        "url_template": "maps/spc/spcd1four_panel.conus.png",
    },
    "spc/d1cat": {
        "description": "SPC Day 1 Categorical Outlook",
        "url_template": "maps/spc/thumbs/spcd1cat.conus.png",
    },
    # MRMS (Multi-Radar/Multi-Sensor)
    "mrms/qpe_006h": {
        "description": "MRMS 6hr QPE",
        "url_template": "maps/mrms/latest/mrms_qpe_006h_p.conus.png",
    },
    "mrms/qpe_006h_thumb": {
        "description": "MRMS 6hr QPE (thumbnail)",
        "url_template": "maps/mrms/latest/thumbs/mrms_qpe_006h_p.conus.png",
    },
    # Stage IV QPE
    "stageiv/qpe_024h": {
        "description": "Stage IV 24hr QPE",
        "url_template": "maps/stageiv/latest/stageiv_qpe_024h_p.conus.png",
    },
    "stageiv/qpe_024h_thumb": {
        "description": "Stage IV 24hr QPE (thumbnail)",
        "url_template": "maps/stageiv/latest/thumbs/stageiv_qpe_024h_p.conus.png",
    },
    # NOHRSC (National Operational Hydrologic Remote Sensing Center)
    "nohrsc/24hsnow": {
        "description": "NOHRSC 24hr Snowfall Analysis",
        "url_template": "maps/nohrsc/latest/nohrsc_24hsnow.conus.png",
    },
    "nohrsc/24hsnow_thumb": {
        "description": "NOHRSC 24hr Snowfall Analysis (thumbnail)",
        "url_template": "maps/nohrsc/latest/thumbs/nohrsc_24hsnow.conus.png",
    },
    # RTMA (Real-Time Mesoscale Analysis)
    "rtma_ru/sfct-imp": {
        "description": "RTMA-RU Surface Temperature (imperial)",
        "url_template": "maps/rtma_ru/latest/sfct-imp.conus.png",
    },
    "rtma_ru/sfct-imp_thumb": {
        "description": "RTMA-RU Surface Temperature thumbnail",
        "url_template": "maps/rtma_ru/latest/thumbs/sfct-imp.conus.png",
    },
}


# ---------------------------------------------------------------------------
# Main Client Class
# ---------------------------------------------------------------------------

class PivotalWeatherClient:
    """
    Client for the Pivotal Weather internal API.

    Note: The site uses AWS WAF protection. This client replicates browser-like
    headers to access public-facing API endpoints. Some endpoints may require
    an active Pivotal Weather Plus subscription for full access.
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
        rate_limit_delay: float = 0.5,
    ):
        """
        Initialize the Pivotal Weather client.

        Args:
            session: Optional pre-configured requests.Session. If None, a new
                     session is created with browser-like headers.
            timeout: Request timeout in seconds (default 30).
            rate_limit_delay: Minimum seconds between requests (default 0.5).
        """
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0.0

        if session is not None:
            self.session = session
        else:
            self.session = requests.Session()
            self.session.headers.update(DEFAULT_HEADERS)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Make a rate-limited GET request."""
        self._rate_limit()
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        self._last_request_time = time.time()
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> Any:
        """Make a rate-limited GET request and return JSON."""
        resp = self._get(url, **kwargs)
        return resp.json()

    @staticmethod
    def _fmt_fhr(fhr: int) -> str:
        """Format forecast hour as zero-padded 3-digit string, e.g. 6 -> '006'."""
        return str(fhr).zfill(3)

    @staticmethod
    def _fmt_init_time(dt: Union[datetime, str]) -> str:
        """
        Format model initialization time as YYYYMMDDHH string.

        Accepts:
            - datetime object (UTC assumed)
            - string already in YYYYMMDDHH format
        """
        if isinstance(dt, datetime):
            return dt.strftime("%Y%m%d%H")
        return str(dt)

    # ------------------------------------------------------------------
    # Model run status endpoints
    # ------------------------------------------------------------------

    def get_latest_models(self) -> Dict[str, Any]:
        """
        Fetch the latest available model run information.

        Endpoint: GET /latest_models.php

        Returns JSON object with keys per model, each containing:
            - rh: Latest run hour string (YYYYMMDDHH)
            - fh: Latest forecast hour available
            - fh_final: Final forecast hour for the complete run

        Example::
            {
                "gfs": {"rh": "2026032418", "fh": 384, "fh_final": 384},
                "ecmwf_full": {"rh": "2026032412", "fh": 144, "fh_final": 360},
                ...
            }
        """
        url = f"{BASE_URL}/latest_models.php"
        return self._get_json(url)

    def get_latest_runs(self) -> Dict[str, Any]:
        """
        Fetch the latest run status for all models (lighter endpoint).

        Endpoint: GET /latest_runs.php

        Returns compact run data keyed by model name.
        """
        url = f"{BASE_URL}/latest_runs.php"
        return self._get_json(url)

    def get_model_status(self, model: str, include_soundings: bool = False) -> Dict[str, Any]:
        """
        Get data availability status for a specific model.

        Endpoint: GET /status_model.php?m={model}
                  GET /status_model.php?m={model}&s=1  (with soundings)

        Args:
            model: Model identifier (e.g., "gfs", "hrrr", "nam")
            include_soundings: If True, include sounding data availability

        Returns:
            Dict mapping forecast hours to availability status.
        """
        params: Dict[str, Any] = {"m": model.lower()}
        if include_soundings:
            params["s"] = 1
        url = f"{BASE_URL}/status_model.php?" + urlencode(params)
        return self._get_json(url)

    # ------------------------------------------------------------------
    # Model map image URL builders
    # ------------------------------------------------------------------

    def get_model_map_url(
        self,
        model: str,
        init_time: Union[str, datetime],
        fhr: int,
        parameter: str,
        region: str = "conus",
        thumbnail: bool = False,
    ) -> str:
        """
        Construct the URL for a model forecast map image.

        Image server: https://m1o.pivotalweather.com
        URL pattern:  /maps/models/{model}/{init_time}/{fhr_padded}/{parameter}.{region}.png

        Args:
            model: Model name in lowercase (e.g., "gfs", "ecmwf_full", "hrrr")
            init_time: Initialization time as YYYYMMDDHH string or datetime object
            fhr: Forecast hour (integer, e.g., 24)
            parameter: Parameter/field name (e.g., "prateptype_cat-imp", "500_hgt")
            region: Map region (default "conus"). See REGIONS dict for options.
            thumbnail: If True, return the thumbnail URL (smaller image).

        Returns:
            Full URL string to the PNG map image.

        Example::
            url = client.get_model_map_url("gfs", "2026032418", 24, "prateptype_cat-imp")
            # -> "https://m1o.pivotalweather.com/maps/models/gfs/2026032418/024/prateptype_cat-imp.conus.png"
        """
        init_str = self._fmt_init_time(init_time)
        fhr_str = self._fmt_fhr(fhr)
        model_lower = model.lower()

        if thumbnail:
            path = f"maps/models/{model_lower}/{init_str}/{fhr_str}/thumbs/{parameter}.{region}.png"
        else:
            path = f"maps/models/{model_lower}/{init_str}/{fhr_str}/{parameter}.{region}.png"

        return f"{MODEL_IMAGE_BASE}/{path}"

    def get_analysis_map_url(self, product_key: str) -> str:
        """
        Construct the URL for an analysis/observation map image.

        Image server: https://x-hv1.pivotalweather.com
        Products include: MRMS QPE, Stage IV QPE, NOHRSC Snow, SPC Outlooks, etc.

        Args:
            product_key: Key from ANALYSIS_PRODUCTS dict (e.g., "stageiv/qpe_024h")

        Returns:
            Full URL string to the PNG analysis map image.

        Raises:
            KeyError: If product_key is not in ANALYSIS_PRODUCTS.
        """
        product = ANALYSIS_PRODUCTS[product_key]
        return f"{ANALYSIS_IMAGE_BASE}/{product['url_template']}"

    def build_custom_analysis_url(self, path: str) -> str:
        """
        Build a custom analysis map URL from a relative path.

        Args:
            path: Relative path on x-hv1.pivotalweather.com, e.g.
                  "maps/mrms/latest/mrms_qpe_006h_p.conus.png"

        Returns:
            Full URL string.
        """
        return f"{ANALYSIS_IMAGE_BASE}/{path.lstrip('/')}"

    # ------------------------------------------------------------------
    # Model map image downloaders
    # ------------------------------------------------------------------

    def download_model_map(
        self,
        model: str,
        init_time: Union[str, datetime],
        fhr: int,
        parameter: str,
        region: str = "conus",
        output_path: Optional[str] = None,
        thumbnail: bool = False,
    ) -> bytes:
        """
        Download a model forecast map image.

        Args:
            model: Model name (e.g., "gfs", "hrrr", "ecmwf_full")
            init_time: Initialization time as YYYYMMDDHH string or datetime
            fhr: Forecast hour (integer)
            parameter: Parameter/field name
            region: Map region (default "conus")
            output_path: If provided, save image to this file path.
            thumbnail: If True, download thumbnail version.

        Returns:
            Image bytes (PNG).

        Example::
            data = client.download_model_map("gfs", "2026032418", 24, "sfctemp-imp")
            with open("gfs_sfctemp_f024.png", "wb") as f:
                f.write(data)
        """
        url = self.get_model_map_url(model, init_time, fhr, parameter, region, thumbnail)
        resp = self._get(url)
        image_data = resp.content

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_data)

        return image_data

    def download_analysis_map(
        self,
        product_key: str,
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Download an analysis/observation map image.

        Args:
            product_key: Key from ANALYSIS_PRODUCTS (e.g., "stageiv/qpe_024h")
            output_path: If provided, save image to this file path.

        Returns:
            Image bytes (PNG).
        """
        url = self.get_analysis_map_url(product_key)
        resp = self._get(url)
        image_data = resp.content

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_data)

        return image_data

    # ------------------------------------------------------------------
    # Batch downloading
    # ------------------------------------------------------------------

    def download_model_loop(
        self,
        model: str,
        init_time: Union[str, datetime],
        parameter: str,
        region: str = "conus",
        fhr_start: int = 0,
        fhr_end: Optional[int] = None,
        fhr_step: int = 6,
        output_dir: str = ".",
    ) -> List[str]:
        """
        Download a sequence of model forecast maps (animation loop frames).

        Args:
            model: Model name
            init_time: Initialization time
            parameter: Parameter/field name
            region: Map region
            fhr_start: Starting forecast hour (default 0)
            fhr_end: Ending forecast hour. Defaults to model's max_fhr.
            fhr_step: Step between forecast hours (default 6)
            output_dir: Directory to save images

        Returns:
            List of saved file paths.

        Example::
            paths = client.download_model_loop(
                "gfs", "2026032418", "sfctemp-imp",
                fhr_start=0, fhr_end=120, fhr_step=6,
                output_dir="/tmp/gfs_loop"
            )
        """
        model_info = MODELS.get(model.lower(), {})
        if fhr_end is None:
            fhr_end = model_info.get("max_fhr", 120)

        init_str = self._fmt_init_time(init_time)
        os.makedirs(output_dir, exist_ok=True)
        saved_paths = []

        fhr = fhr_start
        while fhr <= fhr_end:
            filename = f"{model}_{init_str}_{parameter}_{region}_f{fhr:03d}.png"
            output_path = os.path.join(output_dir, filename)

            try:
                self.download_model_map(
                    model, init_time, fhr, parameter, region, output_path
                )
                saved_paths.append(output_path)
                print(f"Downloaded: {filename}")
            except requests.HTTPError as e:
                print(f"Warning: Could not download fhr={fhr}: {e}")

            fhr += fhr_step

        return saved_paths

    # ------------------------------------------------------------------
    # Web page URL builders (for browser navigation)
    # ------------------------------------------------------------------

    def get_model_page_url(
        self,
        model: str,
        fhr: int = 0,
        field: str = "prateptype_cat-imp",
        region: str = "conus",
        init_time: Optional[str] = None,
    ) -> str:
        """
        Build the URL for a model viewer page on the Pivotal Weather website.

        URL pattern: /model.php?model={MODEL}&fhr={fhr}&field={field}&reg={region}

        Args:
            model: Model name (e.g., "GFS", "ECMWF")
            fhr: Forecast hour
            field: Field/parameter name
            region: Region code
            init_time: Optional specific run hour (YYYYMMDDHH)

        Returns:
            Full URL to the model viewer page.
        """
        params: Dict[str, Any] = {
            "model": model.upper(),
            "fhr": fhr,
            "field": field,
            "reg": region,
        }
        if init_time:
            params["rh"] = init_time
        return f"{BASE_URL}/model.php?" + urlencode(params)

    def get_sounding_page_url(
        self,
        model: str,
        init_time: Union[str, datetime],
        fhr: int,
        lat: float,
        lon: float,
        region: str = "conus",
    ) -> str:
        """
        Build the URL for a model sounding page.

        URL pattern: /sounding.php?model={model}&rh={init_time}&fh={fhr}&lat={lat}&lon={lon}

        Args:
            model: Model name in lowercase
            init_time: Initialization time
            fhr: Forecast hour
            lat: Latitude (decimal degrees)
            lon: Longitude (decimal degrees, negative for western hemisphere)
            region: Region code

        Returns:
            Full URL to the sounding page.
        """
        init_str = self._fmt_init_time(init_time)
        params = {
            "model": model.lower(),
            "rh": init_str,
            "fh": fhr,
            "lat": lat,
            "lon": lon,
            "reg": region,
        }
        return f"{BASE_URL}/sounding.php?" + urlencode(params)

    def get_maps_page_url(
        self,
        product: str,
        region: str = "conus",
    ) -> str:
        """
        Build the URL for the analysis maps viewer page.

        URL pattern: /maps.php?p={product}&r={region}

        Args:
            product: Map product identifier
            region: Region code

        Returns:
            Full URL to the maps page.
        """
        params = {"p": product, "r": region}
        return f"{BASE_URL}/maps.php?" + urlencode(params)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def list_models(self) -> Dict[str, Dict]:
        """Return the catalogue of all known models."""
        return MODELS

    def list_regions(self) -> Dict[str, str]:
        """Return the catalogue of all known map regions."""
        return REGIONS

    def list_gfs_parameters(self) -> Dict[str, str]:
        """Return the catalogue of common GFS parameters."""
        return GFS_PARAMETERS

    def list_analysis_products(self) -> Dict[str, Dict]:
        """Return the catalogue of analysis/observation map products."""
        return ANALYSIS_PRODUCTS

    def get_model_info(self, model: str) -> Optional[Dict]:
        """
        Get information about a specific model.

        Args:
            model: Model name (case-insensitive)

        Returns:
            Model info dict or None if not found.
        """
        return MODELS.get(model.lower())

    def format_init_time(self, year: int, month: int, day: int, hour: int) -> str:
        """
        Helper to format an initialization time string.

        Args:
            year, month, day, hour: UTC date/time components

        Returns:
            YYYYMMDDHH string, e.g. "2026032418"
        """
        return f"{year:04d}{month:02d}{day:02d}{hour:02d}"


# ---------------------------------------------------------------------------
# Convenience functions (module-level)
# ---------------------------------------------------------------------------

def get_latest_models(timeout: int = 30) -> Dict[str, Any]:
    """
    Convenience function: fetch latest model run info without creating a client.

    Returns:
        Dict of model run information from /latest_models.php
    """
    client = PivotalWeatherClient(timeout=timeout)
    return client.get_latest_models()


def get_model_map_url(
    model: str,
    init_time: Union[str, datetime],
    fhr: int,
    parameter: str,
    region: str = "conus",
) -> str:
    """
    Convenience function: build a model map URL without creating a client.

    Returns:
        URL string to the PNG map image.
    """
    client = PivotalWeatherClient()
    return client.get_model_map_url(model, init_time, fhr, parameter, region)


# ---------------------------------------------------------------------------
# CLI demo / quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Pivotal Weather API Client - Demo")
    print("=" * 60)

    client = PivotalWeatherClient()

    print("\n[1] Fetching latest model runs from /latest_models.php ...")
    try:
        runs = client.get_latest_models()
        print(f"    Got data for {len(runs)} models")
        # Show first 5 models
        for model_name, info in list(runs.items())[:5]:
            print(f"    {model_name}: latest run={info.get('rh', 'N/A')}, fh={info.get('fh', 'N/A')}")
    except Exception as e:
        print(f"    ERROR: {e}")

    print("\n[2] Building model map URLs ...")
    examples = [
        ("gfs", "2026032418", 24, "prateptype_cat-imp", "conus"),
        ("gfs", "2026032418", 48, "sfctemp-imp", "ne"),
        ("hrrr", "2026032500", 6, "sfctemp-imp", "conus"),
        ("ecmwf_full", "2026032412", 120, "1000-500_thick", "conus"),
        ("gefsens", "2026032418", 120, "sfctemp-imp", "conus"),
    ]
    for model, rh, fhr, param, reg in examples:
        url = client.get_model_map_url(model, rh, fhr, param, reg)
        print(f"    {model} f{fhr:03d} {param} -> {url}")

    print("\n[3] Analysis map URLs ...")
    for key in list(ANALYSIS_PRODUCTS.keys())[:4]:
        url = client.get_analysis_map_url(key)
        print(f"    {key} -> {url}")

    print("\n[4] Model page URLs ...")
    page_url = client.get_model_page_url("GFS", fhr=24, field="sfctemp-imp", region="conus")
    print(f"    GFS page: {page_url}")

    sounding_url = client.get_sounding_page_url("gfs", "2026032418", 24, 39.95, -75.17)
    print(f"    Sounding: {sounding_url}")

    print("\n[5] Available models:")
    for model_id, info in list(MODELS.items())[:8]:
        print(f"    {model_id:20s} - {info['name']}")

    print("\nDone.")
