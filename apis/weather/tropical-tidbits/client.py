"""
Tropical Tidbits API Client
===========================
Reverse-engineered client for https://www.tropicaltidbits.com

This module provides programmatic access to the internal APIs of Tropical Tidbits,
a widely-used meteorology website covering tropical cyclones, weather model forecasts,
satellite imagery, and oceanographic data.

Note: All endpoints are unofficial and undocumented. They may change without notice.
Respect the site's Terms of Use: do not use this for heavy automated downloading or
embedding real-time content on other websites without permission.
Contact: levicowan@tropicaltidbits.com for special requests.

Discovered by reverse-engineering the site's JavaScript and HTML source code.
Last verified: March 2026
"""

import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Optional, Union


BASE_URL = "https://www.tropicaltidbits.com"
SAT_CDN_URL = "https://olorin.tropicaltidbits.com"

# Default headers to mimic a browser request
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ---------------------------------------------------------------------------
# Available constants
# ---------------------------------------------------------------------------

MODELS = [
    # Global models
    "ecmwf",       # ECMWF (European Centre) - runs 00z/12z
    "ec-aifs",     # EC-AIFS (ECMWF AI-based) - runs 00z/12z
    "gfs",         # GFS (NCEP Global Forecast System) - runs 00z/06z/12z/18z
    "aigfs",       # AI-GFS (NOAA's ML-enhanced GFS)
    "gem",         # CMC Global Environmental Multiscale - runs 00z/12z
    "icon",        # ICON (DWD German Weather Service) - runs 00z/06z/12z/18z
    "jma",         # JMA (Japan Meteorological Agency) - runs 00z/12z
    # Ensemble models
    "eps",         # EPS (ECMWF Ensemble) - runs 00z/12z
    "gfs-ens",     # GEFS (GFS Ensemble System) - runs 00z/06z/12z/18z
    "gem-ens",     # GEPS (CMC Ensemble) - runs 00z/12z
    # Mesoscale models
    "nam",         # NAM 32km - runs 00z/06z/12z/18z
    "namconus",    # NAM 12km CONUS nest
    "nam3km",      # NAM 3km CONUS nest
    "hrrr",        # HRRR (High-Resolution Rapid Refresh) - runs every hour
    "fv3-hires",   # FV3 Hi-Res - runs 00z/12z
    "wrf-arw",     # WRF-ARW (custom domain)
    "wrf-arw2",    # WRF-ARW2 (custom domain 2)
    "rgem",        # RGEM (Regional GEM, Canada)
    "hrdps",       # HRDPS (High-Res Deterministic Prediction System, Canada)
    # Hurricane models
    "hwrf",        # HWRF (Hurricane Weather Research and Forecasting)
    "hwrf-p",      # HWRF Parent domain
    "hafsa",       # HAFS-A (Hurricane Analysis and Forecast System A)
    "hafsa-p",     # HAFS-A Parent domain
    "hafsb",       # HAFS-B
    "hafsb-p",     # HAFS-B Parent domain
    # Climate models
    "cfs-avg",     # CFS Weekly Average
    "cfs-mon",     # CFS Monthly
    "cansips",     # CanSIPS (Canadian Seasonal to Inter-annual Prediction System)
    "nmme",        # NMME (North American Multi-Model Ensemble)
]

# Models that support soundings/cross-sections
SOUNDING_MODELS = [
    "ecmwf", "gfs", "nam3km", "hrrr", "wrf-arw", "wrf-arw2",
    "fv3-hires", "hafsa", "hafsa-p", "hafsb", "hafsb-p", "hwrf", "hwrf-p"
]

# Geographical regions
REGIONS = {
    # United States
    "us": "CONUS",
    "nwus": "Northwest U.S.",
    "ncus": "North-Central U.S.",
    "neus": "Northeast U.S.",
    "wus": "Western U.S.",
    "eus": "Eastern U.S.",
    "swus": "Southwest U.S.",
    "scus": "South-Central U.S.",
    "seus": "Southeast U.S.",
    "ak": "Alaska",
    "secan": "Southeast Canada",
    # Americas
    "namer": "North America",
    "samer": "South America",
    # Atlantic/Pacific
    "atl": "Atlantic Wide",
    "watl": "Western Atlantic",
    "catl": "Central Atlantic",    # not confirmed
    "eatl": "Eastern Atlantic",
    "nwatl": "Northwest Atlantic",
    "atlpac-wide": "Atlantic/E.Pac Combo",
    "epac": "Eastern Pacific",
    "cpac": "Central Pacific",
    "wpac": "Western Pacific",
    "swpac": "Southwestern Pacific",
    "npac": "North Pacific",
    "sepac": "Southeast Pacific",
    # Other basins
    "io": "Indian Ocean",
    "india": "Bay of Bengal/India",
    "eu": "Europe",
    "ea": "East Asia",
    "me": "Middle East",
    "nafr": "North Africa",
    "safr": "South Africa",
    "aus": "Australia",
    "nhem": "Northern Hemisphere",
    "global": "Global",
}

# Model product packages (grouped by category)
PACKAGES = {
    # Precipitation / Moisture
    "mslp_pcpn": "MSLP & Precip",
    "mslp_pcpn_frzn": "MSLP & Precip (Rain/Frozen)",
    "ref_frzn": "Radar (Rain/Frozen)",
    "apcpn24": "24-hour Accumulated Precip",
    "apcpn": "Total Accumulated Precip",
    "asnow": "Total Snowfall (10:1 SLR)",
    "asnow24": "24-Hour Snowfall (10:1 SLR)",
    "asnowd": "Total Positive Snow-Depth Change",
    "asnowd24": "24-Hour Positive Snow-Depth Change",
    "mslp_pwat": "MSLP & PWAT",
    "mslp_pwata": "PWAT Norm. Anomaly",
    "midRH": "700-300mb Relative Humidity",
    "Td2m": "2m Dewpoint",
    # Lower Dynamics
    "temp_adv_fgen_700": "700mb Temp. Adv. & FGEN",
    "temp_adv_fgen_850": "850mb Temp. Adv. & FGEN",
    "z700_vort": "Z700, Vort, & Wind",
    "z850_vort": "Z850, Vort, & Wind",
    "ow850": "850 hPa Okubo-Weiss and Dilatation Axes",
    "mslp_uv850": "850mb Height & Wind",
    "mslp_wind": "MSLP & 10m Wind",
    "mslptrend": "MSLP 48hr Forecast Trend",
    "mslpa": "MSLP Anomaly",
    "mslpaNorm": "MSLP Norm. Anomaly",
    # Upper Dynamics
    "DTpres": "2 PVU Pressure & Wind",
    "upperforcing": "200-400mb Q-Div, Streamfunc., 850mb Vort, 200mb Irr. Wind",
    "pv330K": "330K Potential Vorticity",
    "isen300K": "300K Wind, RH, Pressure",
    "isen290K": "290K Wind, RH, Pressure",
    "uv250": "250mb Wind",
    "z500trend": "Z500 48hr Forecast Trend",
    "z500a": "500mb Height Anomaly",
    "z500aNorm": "500mb Height Norm. Anomaly",
    "z500_vort": "Z500, Vort, & Wind",
    "z500_mslp": "500mb Height & MSLP",
    "ir": "Simulated IR Satellite",
    # Thermodynamics
    "cape": "SBCAPE and Wind Crossovers",
    "T700": "700mb Temperature, Wind, and MSLP",
    "T850": "850mb Temperature, Wind, and MSLP",
    "T850a": "850mb Temp Anomaly",
    "T2m": "2m Temperature (shaded)",
    "T2m_contour": "2m Temperature (contours)",
    "T2ma": "2m Temp Anomaly",
}

# Satellite products
SAT_PRODUCTS = {
    "ir": "Longwave IR (2 km)",
    "dvorak": "Longwave IR [Dvorak] (2 km)",
    "vis": "Visible Hi-Res (0.5 km)",
    "vis_swir": "Visible / Shortwave IR (2 km)",
    "truecolor": "True Color (2 km)",
    "wv_mid": "Water Vapor [6.9 μm] (2 km)",
    "wv_rgb": "Water Vapor RGB (2 km)",
}

# Satellite regions for the full imagery page
SAT_REGIONS = {
    # Meso sectors
    "goes19-meso1": "GOES-19 Meso Sector 1",
    "goes19-meso2": "GOES-19 Meso Sector 2",
    "goes18-meso1": "GOES-18 Meso Sector 1",
    "goes18-meso2": "GOES-18 Meso Sector 2",
    "himawari9-meso": "Himawari-9 Meso Sector",
    # Atlantic
    "atlpac-wide": "Atlantic/EPAC Combo",
    "atl": "Atlantic Wide",
    "gom": "Gulf of Mexico",
    "nwatl": "Northwest Atlantic",
    "watl": "Western Atlantic",
    "catl": "Central Atlantic",
    "eatl": "Eastern Atlantic",
    # Pacific
    "epac": "Eastern Pacific",
    "cpac": "Central Pacific",
    # Land
    "us": "United States",
    "ak": "Alaska",
    "hawaii": "Hawaii",
}

# TC basins for historical data
TC_BASINS = {
    "NA": "North Atlantic",
    "EP": "East Pacific",
    "CP": "Central Pacific",
    "WP": "West Pacific",
    "NI": "North Indian",
    "SI": "South Indian",
    "SP": "South Pacific",
    "AU": "Australia",
}

# Cross-section types for vertical cross sections
XSECTION_TYPES = [
    "FGEN, Theta-e, Omega",
    "Potential Vorticity",
    "RH and Omega",
    "Normal Wind",
    "In-Plane Wind",
]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _make_request(
    url: str,
    referer: Optional[str] = None,
    timeout: int = 30,
    return_bytes: bool = False,
) -> Union[str, bytes]:
    """
    Make an HTTP GET request, returning response content.

    Args:
        url: Full URL to fetch.
        referer: Referer header value (some endpoints require it).
        timeout: Request timeout in seconds.
        return_bytes: If True, return raw bytes; otherwise decode as UTF-8.

    Returns:
        Response body as str or bytes.

    Raises:
        urllib.error.HTTPError: On non-2xx responses.
    """
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if return_bytes:
        return data
    return data.decode("utf-8")


def _build_url(path: str, params: Optional[dict] = None) -> str:
    """Construct a full URL from a path and optional query parameters."""
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


# ---------------------------------------------------------------------------
# Storm Information API
# ---------------------------------------------------------------------------

class StormInfoClient:
    """
    Access current tropical storm and disturbance information.

    Data source: ATCF (Automated Tropical Cyclone Forecast system), updated
    every 15 minutes. Reflects 6-hourly ATCF data (0z, 6z, 12z, 18z).
    """

    BASE_PATH = "/storminfo"

    def get_storm_page(self) -> str:
        """
        Fetch the raw HTML of the current storm information page.

        Returns:
            HTML source of https://www.tropicaltidbits.com/storminfo/
        """
        url = _build_url(self.BASE_PATH + "/")
        return _make_request(url)

    def parse_active_storms(self) -> list[dict]:
        """
        Parse the storm information page and return a list of active storms.

        Returns:
            List of dicts with keys: id, name, timestamp, lat, lon,
            max_winds_kt, pressure_mb.

        Example:
            >>> client = StormInfoClient()
            >>> storms = client.parse_active_storms()
            >>> for s in storms:
            ...     print(s["id"], s["name"], s["max_winds_kt"], "kt")
        """
        html = self.get_storm_page()
        storms = []

        # Extract storm wrapper divs
        storm_blocks = re.findall(
            r'<div class="stormWrapper" id="([A-Z0-9]+)">(.*?)</div>\s*<!-- End storm-wrapper -->',
            html,
            re.DOTALL,
        )
        for storm_id, block in storm_blocks:
            storm = {"id": storm_id}
            name_m = re.search(r'class="storm-name">(.*?)</span>', block)
            if name_m:
                storm["name"] = name_m.group(1).strip()
            ts_m = re.search(r'class="timestamp">As of (.*?)</span>', block)
            if ts_m:
                storm["timestamp"] = ts_m.group(1).strip()
            loc_m = re.search(r'Location:\s*([\d.]+)&deg;([NS])\s+([\d.]+)&deg;([EW])', block)
            if loc_m:
                lat = float(loc_m.group(1)) * (1 if loc_m.group(2) == "N" else -1)
                lon = float(loc_m.group(3)) * (1 if loc_m.group(4) == "E" else -1)
                storm["lat"] = lat
                storm["lon"] = lon
            wind_m = re.search(r'Maximum Winds:\s*(\d+)\s*kt', block)
            if wind_m:
                storm["max_winds_kt"] = int(wind_m.group(1))
            pres_m = re.search(r'Minimum Central Pressure:\s*(\d+)\s*mb', block)
            if pres_m:
                storm["pressure_mb"] = int(pres_m.group(1))
            storms.append(storm)

        return storms

    def get_surface_plot(
        self,
        storm_id: str,
        obs_time: Optional[str] = None,
    ) -> bytes:
        """
        Download a marine surface plot for a storm.

        Args:
            storm_id: ATCF storm identifier (e.g., "27P", "09L").
            obs_time: UTC observation time in "YYYYMMDDhh" format.
                      If None, retrieves the latest available.

        Returns:
            PNG image bytes.

        Example:
            >>> client = StormInfoClient()
            >>> img_bytes = client.get_surface_plot("09L")
            >>> with open("sfcplot_09L.png", "wb") as f:
            ...     f.write(img_bytes)
        """
        if obs_time:
            filename = f"sfcplot_{storm_id}_{obs_time}.png"
        else:
            filename = f"sfcplot_{storm_id}_latest.png"
        url = _build_url(f"{self.BASE_PATH}/sfcplots/{filename}")
        return _make_request(url, referer=BASE_URL + self.BASE_PATH + "/", return_bytes=True)

    def get_model_tracks_image(
        self,
        storm_id: str,
        model_type: str = "tracks",
        run_time: Optional[str] = None,
    ) -> bytes:
        """
        Download a model track forecast image for a storm.

        Args:
            storm_id: ATCF storm identifier (e.g., "27P", "09L").
            model_type: One of:
                - "tracks" - All global/hurricane model tracks
                - "gefs"   - GEFS ensemble tracks
                - "geps"   - GEPS ensemble tracks
                - "intensity" - Model intensity guidance
            run_time: Model run time suffix ("latest", "00z", "06z", "12z", "18z").
                      Defaults to "latest".

        Returns:
            PNG image bytes.

        Example:
            >>> client = StormInfoClient()
            >>> img = client.get_model_tracks_image("09L", "gefs")
            >>> with open("09L_gefs.png", "wb") as f:
            ...     f.write(img)
        """
        run = run_time or "latest"
        filename = f"{storm_id}_{model_type}_{run}.png"
        url = _build_url(f"{self.BASE_PATH}/{filename}")
        return _make_request(url, referer=BASE_URL + self.BASE_PATH + "/", return_bytes=True)


# ---------------------------------------------------------------------------
# Forecast Models API
# ---------------------------------------------------------------------------

class ModelsClient:
    """
    Access numerical weather model forecast images.

    Image URL structure:
        https://www.tropicaltidbits.com/analysis/models/{model}/{runtime}/{model}_{package}_{region}_{index}.png

    The index maps to a specific forecast hour. The mapping is provided by
    the page's jsReloadInfo script block, accessible via get_model_metadata().

    Requires Referer header to access image files directly.
    """

    BASE_PATH = "/analysis/models"
    REFERER = BASE_URL + "/analysis/models/"

    def get_model_metadata(
        self,
        model: str = "gfs",
        region: str = "us",
        package: str = "mslp_pcpn_frzn",
        runtime: Optional[str] = None,
        fh: int = 6,
    ) -> dict:
        """
        Fetch metadata about a model run including image URLs and forecast hours.

        This calls the model page and parses the jsReloadInfo script block which
        contains the complete mapping of forecast hours to image filenames.

        Args:
            model: Model identifier (e.g., "gfs", "ecmwf", "nam").
            region: Geographic region code (e.g., "us", "atl", "nhem").
            package: Product package identifier (e.g., "mslp_pcpn_frzn").
            runtime: Model run time in "YYYYMMDDhh" format.
                     If None, uses the most recent available run.
            fh: Initial forecast hour to display (default 6).

        Returns:
            Dict with keys:
                - model: str
                - region: str
                - pkg: str
                - runtime: str (e.g., "2026032418")
                - fh: int (current forecast hour)
                - img_urls: list[str] (relative paths, in forecast-hour order)
                - img_fh: list[int] (forecast hours matching img_urls)
                - run_image_urls: dict mapping runtime -> {fh: relative_path}
                - base_url: str (prepend to img_urls for full URLs)

        Example:
            >>> client = ModelsClient()
            >>> meta = client.get_model_metadata("gfs", "us", "mslp_pcpn_frzn")
            >>> print(meta["runtime"], "has", len(meta["img_fh"]), "forecast hours")
        """
        params = {
            "model": model,
            "region": region,
            "pkg": package,
            "fh": fh,
        }
        if runtime:
            params["runtime"] = runtime

        url = _build_url(self.BASE_PATH + "/", params)
        html = _make_request(url)

        result = {
            "model": model,
            "region": region,
            "pkg": package,
            "base_url": BASE_URL + self.BASE_PATH + "/",
        }

        # Parse jsReloadInfo
        idx = html.find('<script id="jsReloadInfo">')
        if idx < 0:
            return result
        end_idx = html.find("</script>", idx)
        script = html[idx + len('<script id="jsReloadInfo">'):end_idx]

        # Extract APP variable assignments
        for var, pattern in [
            ("runtime", r"APP\.runtime\s*=\s*'([^']+)'"),
            ("model", r"APP\.model\s*=\s*'([^']+)'"),
            ("region", r"APP\.region\s*=\s*'([^']+)'"),
            ("pkg", r"APP\.pkg\s*=\s*'([^']+)'"),
        ]:
            m = re.search(pattern, script)
            if m:
                result[var] = m.group(1)

        fh_m = re.search(r"APP\.fh\s*=\s*(\d+)", script)
        if fh_m:
            result["fh"] = int(fh_m.group(1))

        urls_m = re.search(r"APP\.imgURLs\s*=\s*\[(.*?)\];", script, re.DOTALL)
        if urls_m:
            result["img_urls"] = re.findall(r"'([^']+)'", urls_m.group(1))

        fh_list_m = re.search(r"APP\.imgFH\s*=\s*\[(.*?)\];", script, re.DOTALL)
        if fh_list_m:
            raw = fh_list_m.group(1)
            result["img_fh"] = [
                int(x.strip()) for x in raw.split(",") if x.strip().lstrip("-").isdigit()
            ]

        # Parse runImageURLs (nested dict: {runtime: {fh: url}})
        run_m = re.search(r"APP\.runImageURLs\s*=\s*(\{.*?\})\s*;", script, re.DOTALL)
        if run_m:
            run_raw = run_m.group(1)
            run_dict = {}
            # Extract per-runtime blocks
            for rt_m in re.finditer(r"'(\d{10})'\s*:\s*\{([^}]+)\}", run_raw):
                rt = rt_m.group(1)
                fh_urls = {}
                for fh_entry in re.finditer(r"(-?\d+)\s*:\s*'([^']+)'", rt_m.group(2)):
                    fh_urls[int(fh_entry.group(1))] = fh_entry.group(2)
                run_dict[rt] = fh_urls
            result["run_image_urls"] = run_dict

        return result

    def get_model_image(
        self,
        model: str,
        runtime: str,
        package: str,
        region: str,
        index: int,
    ) -> bytes:
        """
        Download a specific model forecast image by its sequential index.

        The index is 1-based and corresponds to the order of forecast hours
        available for this model run (see img_urls from get_model_metadata()).

        Args:
            model: Model identifier (e.g., "gfs").
            runtime: Run time in "YYYYMMDDhh" format (e.g., "2026032418").
            package: Product package (e.g., "mslp_pcpn_frzn").
            region: Region code (e.g., "us").
            index: 1-based image index corresponding to forecast hour.

        Returns:
            PNG image bytes.

        Example:
            >>> client = ModelsClient()
            >>> # GFS 18Z Mar 24, MSLP+Precip, CONUS, forecast hour index 1 (=fh006)
            >>> img = client.get_model_image("gfs", "2026032418", "mslp_pcpn_frzn", "us", 1)
        """
        filename = f"{model}_{package}_{region}_{index}.png"
        path = f"{self.BASE_PATH}/{model}/{runtime}/{filename}"
        url = BASE_URL + path
        return _make_request(url, referer=self.REFERER, return_bytes=True)

    def get_model_image_by_fh(
        self,
        model: str,
        runtime: str,
        package: str,
        region: str,
        fh: int,
    ) -> bytes:
        """
        Download a model forecast image for a specific forecast hour.

        This method first fetches metadata to map the forecast hour to an
        image index, then downloads the image.

        Args:
            model: Model identifier.
            runtime: Run time in "YYYYMMDDhh" format.
            package: Product package.
            region: Region code.
            fh: Forecast hour (e.g., 6, 12, 24, 48, 120).

        Returns:
            PNG image bytes.

        Raises:
            ValueError: If the forecast hour is not available.

        Example:
            >>> client = ModelsClient()
            >>> img = client.get_model_image_by_fh("gfs", "2026032418", "mslp_pcpn_frzn", "us", 24)
        """
        meta = self.get_model_metadata(model, region, package, runtime, fh)
        if "img_fh" not in meta or "img_urls" not in meta:
            raise ValueError(f"Could not retrieve metadata for model={model} runtime={runtime}")

        try:
            idx_in_list = meta["img_fh"].index(fh)
        except ValueError:
            available = meta["img_fh"]
            raise ValueError(
                f"Forecast hour {fh} not available. Available: {available}"
            )

        # Index is 1-based in the filename
        # The img_urls list is 0-indexed; filename uses 1-based index
        relative_url = meta["img_urls"][idx_in_list]
        # relative_url is like "gfs/2026032418/gfs_mslp_pcpn_frzn_us_4.png"
        full_url = BASE_URL + self.BASE_PATH + "/" + relative_url
        return _make_request(full_url, referer=self.REFERER, return_bytes=True)

    def get_sounding_data_times(self) -> dict:
        """
        Fetch the JSON index of available sounding data by model and run time.

        Returns:
            Dict mapping model names to dicts of {runtime: [forecast_hours]}.
            Example:
                {
                  "gfs": {"2026032418": [0, 3, 6, ..., 384], ...},
                  "ecmwf": {"2026032418": [0, 3, 6, ..., 360], ...},
                  "hrrr": {"2026032501": [0, 1, 2, ..., 18], ...},
                  ...
                }

        Example:
            >>> client = ModelsClient()
            >>> times = client.get_sounding_data_times()
            >>> gfs_runs = list(times.get("gfs", {}).keys())
            >>> print("Latest GFS run:", max(gfs_runs))
        """
        url = _build_url(self.BASE_PATH + "/sounding_data_times.json")
        response = _make_request(url, referer=self.REFERER)
        return json.loads(response)

    def get_sounding(
        self,
        model: str,
        runtime: str,
        fh: int,
        lat: float,
        lon: float,
        mode: str = "sounding",
        station_id: str = "",
        tc: str = "",
        domain: Optional[list] = None,
    ) -> str:
        """
        Request a point sounding or area-averaged sounding image (HTML fragment).

        The server returns an HTML fragment containing an <img> tag pointing
        to the generated sounding PNG. Use parse_sounding_response() to extract
        the image URL from this fragment.

        Args:
            model: Model identifier (must be in SOUNDING_MODELS list).
            runtime: Run time in "YYYYMMDDhh" format.
            fh: Forecast hour.
            lat: Latitude in decimal degrees (positive = N).
            lon: Longitude in decimal degrees (positive = E, negative = W).
            mode: "sounding" for skew-T sounding (default).
            station_id: Optional RAOB station ID for obs comparison.
            tc: Optional tropical cyclone ID for TC-relative soundings.
            domain: Optional list [[lat1,lon1], [lat2,lon2]] for area-averaged
                    sounding (bounding box corners).

        Returns:
            HTML fragment string containing the sounding image tag.

        Example:
            >>> client = ModelsClient()
            >>> html = client.get_sounding("gfs", "2026032418", 24, 29.0, -90.0)
            >>> img_src = client.parse_sounding_response(html)
            >>> print(img_src)  # => "/analysis/models/sounding/images/gfs_...png"
        """
        params = {
            "model": model,
            "runtime": runtime,
            "fh": fh,
            "stationID": station_id,
            "tc": tc,
            "mode": mode,
        }
        if domain:
            # domain = [[lat1,lon1], [lat2,lon2]]
            flat_domain = [coord for point in domain for coord in point]
            params["domain"] = ",".join(str(x) for x in flat_domain)
        else:
            params["lat"] = lat
            params["lon"] = lon

        url = _build_url(self.BASE_PATH + "/sounding/", params)
        return _make_request(url, referer=self.REFERER)

    def parse_sounding_response(self, html_fragment: str) -> Optional[str]:
        """
        Extract the sounding image URL from a sounding HTML response fragment.

        Args:
            html_fragment: HTML returned by get_sounding().

        Returns:
            Relative URL of the sounding PNG image, or None if not found.
            Example: "/analysis/models/sounding/images/gfs_2026032418_fh24_sounding_29.00N_90.00W.png"
        """
        m = re.search(r'id="sounding-image"\s+src="([^"]+)"', html_fragment)
        return m.group(1) if m else None

    def get_sounding_image(
        self,
        model: str,
        runtime: str,
        fh: int,
        lat: float,
        lon: float,
        **kwargs,
    ) -> bytes:
        """
        Convenience method: request a sounding and download the resulting PNG.

        Args:
            model: Model identifier.
            runtime: Run time in "YYYYMMDDhh" format.
            fh: Forecast hour.
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.
            **kwargs: Additional arguments passed to get_sounding().

        Returns:
            PNG image bytes of the sounding chart.

        Example:
            >>> client = ModelsClient()
            >>> img = client.get_sounding_image("gfs", "2026032418", 24, 29.0, -90.0)
            >>> with open("sounding.png", "wb") as f:
            ...     f.write(img)
        """
        html = self.get_sounding(model, runtime, fh, lat, lon, **kwargs)
        img_path = self.parse_sounding_response(html)
        if not img_path:
            raise ValueError("Sounding image not available")
        return _make_request(BASE_URL + img_path, referer=self.REFERER, return_bytes=True)

    def get_cross_section(
        self,
        model: str,
        runtime: str,
        fh: int,
        p0: tuple[float, float],
        p1: tuple[float, float],
        xsection_type: str = "FGEN, Theta-e, Omega",
        tc: str = "",
    ) -> str:
        """
        Request a vertical cross section image (HTML fragment).

        Args:
            model: Model identifier (must be in SOUNDING_MODELS list).
            runtime: Run time in "YYYYMMDDhh" format.
            fh: Forecast hour.
            p0: Start point as (lat, lon) tuple.
            p1: End point as (lat, lon) tuple.
            xsection_type: Cross section type, one of XSECTION_TYPES.
            tc: Optional tropical cyclone ID.

        Returns:
            HTML fragment string containing the cross section image.

        Example:
            >>> client = ModelsClient()
            >>> html = client.get_cross_section(
            ...     "gfs", "2026032418", 24,
            ...     p0=(30.0, -90.0), p1=(45.0, -70.0),
            ...     xsection_type="RH and Omega"
            ... )
        """
        p0_str = f"{p0[0]},{p0[1]}"
        p1_str = f"{p1[0]},{p1[1]}"
        params = {
            "model": model,
            "runtime": runtime,
            "fh": fh,
            "p0": p0_str,
            "p1": p1_str,
            "type": xsection_type,
            "tc": tc,
        }
        url = _build_url(self.BASE_PATH + "/xsection/", params)
        return _make_request(url, referer=self.REFERER)

    def parse_xsection_response(self, html_fragment: str) -> Optional[str]:
        """
        Extract the cross section image URL from an xsection HTML response.

        Args:
            html_fragment: HTML returned by get_cross_section().

        Returns:
            Relative URL of the cross section PNG, or None if not found.
        """
        m = re.search(r'id="xsection-image"\s+src="([^"]+)"', html_fragment)
        return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Satellite Imagery API
# ---------------------------------------------------------------------------

class SatelliteClient:
    """
    Access satellite imagery from GOES-19, GOES-18, and Himawari-9.

    Two types of endpoints:
    1. satlooper.php - The satellite loop page for a region (HTML with image list).
    2. olorin.tropicaltidbits.com CDN - The actual satellite image files.

    Satellite image URL structure (on CDN):
        https://olorin.tropicaltidbits.com/satimages/{satellite}_{product}_{region}_{datetime}.jpg

    For TC floaters, the datetime includes lat/lon:
        https://olorin.tropicaltidbits.com/satimages/{satellite}_{product}_{storm_id}_{datetime}_lat{lat}-lon{lon}.jpg

    Satellite identifiers:
        - goes19 (GOES-East, covers Americas and Atlantic)
        - goes18 (GOES-West, covers Eastern Pacific and Western U.S.)
        - himawari9 (covers Western Pacific, Indian Ocean, Australia)
    """

    SAT_BASE_PATH = "/sat"

    def get_satellite_page(self) -> str:
        """
        Fetch the satellite imagery index page HTML.

        Returns:
            HTML of https://www.tropicaltidbits.com/sat/
        """
        url = _build_url(self.SAT_BASE_PATH + "/")
        return _make_request(url)

    def parse_satellite_regions(self) -> dict[str, list[str]]:
        """
        Parse the satellite page and return available regions and products.

        Returns:
            Dict mapping region_id -> list of available product names.

        Example:
            >>> client = SatelliteClient()
            >>> regions = client.parse_satellite_regions()
            >>> print(regions.get("atl"))  # ["ir", "vis_swir", "truecolor", ...]
        """
        html = self.get_satellite_page()
        result = {}
        for cell in re.findall(r'<div class=\'cell\'>(.*?)</div>', html, re.DOTALL):
            region_m = re.search(r"id='([^']+)'", cell)
            if not region_m:
                continue
            region = region_m.group(1)
            if region.startswith("tc"):
                region = region[2:]  # Strip "tc" prefix for storm floaters
            products = re.findall(r'satlooper\.php\?region=[^&]+&product=(\w+)', cell)
            if products:
                result[region] = products
        return result

    def get_sat_loop_page(self, region: str, product: str = "ir") -> str:
        """
        Fetch the satellite loop page HTML for a region/product.

        Args:
            region: Region or storm ID (e.g., "atl", "27P", "goes19-meso1").
            product: Product type (e.g., "ir", "vis", "wv_mid").

        Returns:
            HTML of the satlooper page containing the image URL list.
        """
        params = {"region": region, "product": product}
        url = _build_url("/sat/satlooper.php", params)
        return _make_request(url)

    def parse_sat_image_urls(self, region: str, product: str = "ir") -> list[str]:
        """
        Get all satellite image URLs for a region/product combination.

        Fetches the satlooper page and extracts the APP.allImageURLs list.

        Args:
            region: Region or storm ID.
            product: Product type.

        Returns:
            List of full CDN URLs for all images in the loop, oldest to newest.

        Example:
            >>> client = SatelliteClient()
            >>> urls = client.parse_sat_image_urls("atl", "ir")
            >>> print(f"Found {len(urls)} images. Latest: {urls[-1]}")
        """
        html = self.get_sat_loop_page(region, product)
        m = re.search(r"APP\.allImageURLs\s*=\s*\[(.*?)\];", html, re.DOTALL)
        if not m:
            return []
        urls = re.findall(r"'(https?://[^']+)'", m.group(1))
        return urls

    def get_latest_sat_image(self, region: str, product: str = "ir") -> bytes:
        """
        Download the most recent satellite image for a region/product.

        Args:
            region: Region or storm ID (e.g., "atl", "27P", "us").
            product: Product type (e.g., "ir", "vis", "wv_mid", "truecolor").

        Returns:
            JPEG image bytes.

        Example:
            >>> client = SatelliteClient()
            >>> img = client.get_latest_sat_image("atl", "wv_mid")
            >>> with open("atlantic_wv.jpg", "wb") as f:
            ...     f.write(img)
        """
        urls = self.parse_sat_image_urls(region, product)
        if not urls:
            raise ValueError(f"No satellite images found for region={region} product={product}")
        latest_url = urls[-1]
        return _make_request(latest_url, return_bytes=True)

    def get_sat_image_by_url(self, image_url: str) -> bytes:
        """
        Download a satellite image by its direct CDN URL.

        Args:
            image_url: Full CDN URL from olorin.tropicaltidbits.com.

        Returns:
            JPEG image bytes.
        """
        return _make_request(image_url, return_bytes=True)

    def build_sat_image_url(
        self,
        satellite: str,
        product: str,
        region: str,
        datetime_str: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> str:
        """
        Construct a satellite image CDN URL from its components.

        For regional images:
            {satellite}_{product}_{region}_{YYYYMMDDhhmm}.jpg
        For TC floater images:
            {satellite}_{product}_{storm_id}_{YYYYMMDDhhmm}_lat{lat}-lon{lon}.jpg

        Args:
            satellite: Satellite name ("goes19", "goes18", "himawari9").
            product: Product code ("ir", "vis", "wv_mid", etc.).
            region: Region or storm ID.
            datetime_str: Datetime string in format "YYYYMMDDhhmm" (e.g., "202603250215").
            lat: Storm latitude (for TC floaters only, decimal degrees).
            lon: Storm longitude (for TC floaters only, decimal degrees).

        Returns:
            Full CDN URL string.

        Example:
            >>> client = SatelliteClient()
            >>> url = client.build_sat_image_url("goes19", "ir", "atl", "202603250215")
            >>> print(url)
            "https://olorin.tropicaltidbits.com/satimages/goes19_ir_atl_202603250215.jpg"
        """
        if lat is not None and lon is not None:
            lat_str = f"{abs(lat):.1f}" if lat >= 0 else f"-{abs(lat):.1f}"
            lon_str = f"{abs(lon):.1f}"
            filename = f"{satellite}_{product}_{region}_{datetime_str}_lat{lat_str}-lon{lon_str}.jpg"
        else:
            filename = f"{satellite}_{product}_{region}_{datetime_str}.jpg"
        return f"{SAT_CDN_URL}/satimages/{filename}"


# ---------------------------------------------------------------------------
# Surface Analysis API
# ---------------------------------------------------------------------------

class SurfaceAnalysisClient:
    """
    Access surface analysis plots and pressure change charts.

    Images are served from /analysis/sfcplots/ and are updated hourly.
    """

    BASE_PATH = "/analysis/sfcplots"
    REFERER = BASE_URL + "/analysis/sfcplots/"

    def get_sfcplots_page(self) -> str:
        """Fetch the surface analysis page HTML."""
        return _make_request(_build_url(self.BASE_PATH + "/"))

    def get_tropical_sfcplot(
        self,
        obs_time: Optional[str] = None,
    ) -> bytes:
        """
        Download the Tropical Atlantic surface observation plot.

        Args:
            obs_time: UTC observation time in "YYYYMMDDhh" format.
                      If None, downloads the latest available.

        Returns:
            PNG image bytes.

        Example:
            >>> client = SurfaceAnalysisClient()
            >>> img = client.get_tropical_sfcplot()
            >>> with open("sfcplot.png", "wb") as f:
            ...     f.write(img)
        """
        if obs_time:
            filename = f"sfcplot_{obs_time}.png"
        else:
            filename = "sfcplot_latest.png"
        url = _build_url(f"{self.BASE_PATH}/{filename}")
        return _make_request(url, referer=self.REFERER, return_bytes=True)

    def get_pressure_change_plot(
        self,
        region: str = "watl",
        obs_time: Optional[str] = None,
    ) -> bytes:
        """
        Download a 24-hour pressure change analysis plot.

        Args:
            region: Region code. Known values: "watl" (Western Atlantic),
                    "eatl" (Eastern Atlantic). More may exist.
            obs_time: UTC time in "YYYYMMDDhh" format. None = latest.

        Returns:
            PNG image bytes.

        Example:
            >>> client = SurfaceAnalysisClient()
            >>> img = client.get_pressure_change_plot("watl")
        """
        if obs_time:
            filename = f"preschange_{region}_{obs_time}.png"
        else:
            filename = f"preschange_{region}_latest.png"
        url = _build_url(f"{self.BASE_PATH}/{filename}")
        return _make_request(url, referer=self.REFERER, return_bytes=True)

    def get_storm_sfcplot(
        self,
        storm_id: str,
        obs_time: Optional[str] = None,
    ) -> bytes:
        """
        Download a marine surface plot for a specific storm.

        These are served from /storminfo/sfcplots/ and show conditions
        around the storm location. See StormInfoClient for alternative access.

        Args:
            storm_id: ATCF storm ID (e.g., "27P", "09L").
            obs_time: Optional time in "YYYYMMDDhh" format.

        Returns:
            PNG image bytes.
        """
        if obs_time:
            filename = f"sfcplot_{storm_id}_{obs_time}.png"
        else:
            filename = f"sfcplot_{storm_id}_latest.png"
        url = _build_url(f"/storminfo/sfcplots/{filename}")
        return _make_request(url, referer=BASE_URL + "/storminfo/", return_bytes=True)


# ---------------------------------------------------------------------------
# Ocean Analysis API
# ---------------------------------------------------------------------------

class OceanAnalysisClient:
    """
    Access ocean analysis products (SST, SSTA, ENSO indices).

    Images are served from /analysis/ocean/ and are updated daily.
    All use CDAS (Climate Data Assimilation System) data.
    """

    BASE_PATH = "/analysis/ocean"
    REFERER = BASE_URL + "/analysis/ocean/"

    # Available regions for SST/SSTA maps
    SST_REGIONS = [
        "global", "atl", "watl", "eatl", "epac", "cpac", "wpac", "swpac", "aus", "io", "samer"
    ]

    # ENSO time series options
    ENSO_REGIONS = [
        "nino34", "nino3", "nino4", "nino12",
        "natlssta", "catlssta", "mdrssta", "mdrglob",
        "carssta", "gom"
    ]

    def _get_image(self, filename: str) -> bytes:
        """Internal helper to fetch an ocean analysis image."""
        url = _build_url(f"{self.BASE_PATH}/{filename}")
        return _make_request(url, referer=self.REFERER, return_bytes=True)

    def get_sst_map(self, region: str = "global") -> bytes:
        """
        Download a Sea Surface Temperature (SST) map.

        Args:
            region: One of SST_REGIONS (e.g., "global", "atl", "epac").

        Returns:
            PNG image bytes.

        Example:
            >>> client = OceanAnalysisClient()
            >>> img = client.get_sst_map("atl")
        """
        return self._get_image(f"cdas-sflux_sst_{region}_1.png")

    def get_ssta_map(self, region: str = "global") -> bytes:
        """
        Download a Sea Surface Temperature Anomaly (SSTA) map.

        Args:
            region: One of SST_REGIONS.

        Returns:
            PNG image bytes.
        """
        return self._get_image(f"cdas-sflux_ssta_{region}_1.png")

    def get_ssta_7day_change(self, region: str = "global") -> bytes:
        """
        Download a 7-day SST Anomaly change map.

        Args:
            region: One of SST_REGIONS.

        Returns:
            PNG image bytes.
        """
        return self._get_image(f"cdas-sflux_ssta7diff_{region}_1.png")

    def get_ssta_relative_to_global_mean(self, region: str = "global") -> bytes:
        """
        Download the SSTA difference from global mean SSTA.

        Returns:
            PNG image bytes.
        """
        return self._get_image(f"cdas-sflux_ssta_relative_{region}_1.png")

    def get_enso_timeseries(self, region: str = "nino34") -> bytes:
        """
        Download an SST anomaly time series plot.

        Args:
            region: One of ENSO_REGIONS (e.g., "nino34", "mdrssta").

        Returns:
            PNG image bytes.

        Example:
            >>> client = OceanAnalysisClient()
            >>> img = client.get_enso_timeseries("nino34")
        """
        return self._get_image(f"{region}.png")


# ---------------------------------------------------------------------------
# Hurricane Season Analogs API
# ---------------------------------------------------------------------------

class HSAnalogClient:
    """
    Access Hurricane Season SST-based analogs data.

    Finds historical hurricane seasons with similar SST patterns to the
    current season, as a long-range forecast guidance tool.
    Based on CDAS 30-day mean SSTA analysis.
    """

    BASE_PATH = "/analysis/hsanalog"
    REFERER = BASE_URL + "/analysis/hsanalog/"

    def get_analog_page(self) -> str:
        """Fetch the hurricane season analog page HTML."""
        return _make_request(_build_url(self.BASE_PATH + "/"))

    def parse_top_analogs(self) -> list[dict]:
        """
        Parse the analog page and return the top analog years with scores.

        Returns:
            List of dicts with keys: year (int), score (float).

        Example:
            >>> client = HSAnalogClient()
            >>> analogs = client.parse_top_analogs()
            >>> for a in analogs:
            ...     print(f"Year {a['year']}: score {a['score']:.2f}")
        """
        html = self.get_analog_page()
        analogs = []
        for m in re.finditer(r'class="analogListItem[^"]*">(\d{4}):&nbsp;&nbsp;([\d.]+)', html):
            analogs.append({"year": int(m.group(1)), "score": float(m.group(2))})
        return analogs

    def get_current_ssta_analysis(self) -> bytes:
        """Download the current 30-day mean CDAS SSTA analysis map."""
        url = _build_url(f"{self.BASE_PATH}/cdas_anl.png")
        return _make_request(url, referer=self.REFERER, return_bytes=True)

    def get_analog_mean_image(self) -> bytes:
        """Download the mean hurricane track map for top analog years."""
        url = _build_url(f"{self.BASE_PATH}/analogmean_current.png")
        return _make_request(url, referer=self.REFERER, return_bytes=True)

    def get_analog_year_ssta(self, analog_rank: int) -> bytes:
        """
        Download the SSTA map for a specific analog year by its ranking.

        Args:
            analog_rank: Rank of the analog year (1 = best match, up to ~5).

        Returns:
            PNG image bytes.

        Example:
            >>> client = HSAnalogClient()
            >>> img = client.get_analog_year_ssta(1)  # Top analog year's SSTA
        """
        url = _build_url(f"{self.BASE_PATH}/analog_anl{analog_rank}_ssta.png")
        return _make_request(url, referer=self.REFERER, return_bytes=True)


# ---------------------------------------------------------------------------
# Historical TC Data API
# ---------------------------------------------------------------------------

class TCHistoryClient:
    """
    Access historical tropical cyclone track data (IBTrACS-based).

    Track map images organized by basin and year, sourced from the IBTrACS
    global TC best track database.
    """

    BASE_PATH = "/data/TC"

    # Available basins
    BASINS = TC_BASINS

    def get_track_map(self, basin: str, year: int) -> bytes:
        """
        Download the annual tropical cyclone track map for a basin.

        Args:
            basin: Basin code (e.g., "NA", "EP", "WP", "IO", "AU").
                   See BASINS dict for all options.
            year: Year (e.g., 2005). Available range varies by basin.

        Returns:
            PNG image bytes.

        Raises:
            urllib.error.HTTPError: If the requested year/basin combination
                                    is not available.

        Example:
            >>> client = TCHistoryClient()
            >>> img = client.get_track_map("NA", 2005)  # Atlantic 2005 season
            >>> with open("na_2005_tracks.png", "wb") as f:
            ...     f.write(img)
        """
        url = _build_url(f"{self.BASE_PATH}/{basin}/tracks/{year}.png")
        return _make_request(url, return_bytes=True)

    def get_global_frequency_map(self, category: str = "all") -> bytes:
        """
        Download a global TC frequency or intensity climatology map.

        Args:
            category: Map type. One of:
                - "all"       -> TCfreq_global_1979-2012.png (TC frequency)
                - "cat1"      -> cat1-freq_global_1979-2012.png (Cat 1+ frequency)
                - "cat3"      -> cat3-freq_global_1979-2012.png (Cat 3+ frequency)
                - "intensity" -> intensity_avg_global_1979-2012.png (avg intensity)
                - "ace"       -> spatialACE_global_1979-2012.png (ACE)
                - "ace_norm"  -> spatialACE_norm_global_1979-2012.png (normalized ACE)

        Returns:
            PNG image bytes.
        """
        filename_map = {
            "all": "TCfreq_global_1979-2012.png",
            "cat1": "cat1-freq_global_1979-2012.png",
            "cat3": "cat3-freq_global_1979-2012.png",
            "intensity": "intensity_avg_global_1979-2012.png",
            "ace": "spatialACE_global_1979-2012.png",
            "ace_norm": "spatialACE_norm_global_1979-2012.png",
        }
        filename = filename_map.get(category, filename_map["all"])
        url = _build_url(f"{self.BASE_PATH}/{filename}")
        return _make_request(url, return_bytes=True)


# ---------------------------------------------------------------------------
# Data Files API
# ---------------------------------------------------------------------------

class DataFilesClient:
    """
    Access static data files hosted on Tropical Tidbits.
    """

    def get_nhc_model_list(self) -> str:
        """
        Download the NHC model acronym reference list.

        Returns a text file listing all tropical cyclone model acronyms used
        in track forecast plots, with descriptions and metadata.

        Returns:
            Plain text content of /data/nhc_model_list.txt

        Example:
            >>> client = DataFilesClient()
            >>> model_list = client.get_nhc_model_list()
            >>> print(model_list[:500])
        """
        url = _build_url("/data/nhc_model_list.txt")
        return _make_request(url)


# ---------------------------------------------------------------------------
# Convenience high-level API
# ---------------------------------------------------------------------------

class TropicalTidbitsClient:
    """
    High-level client combining all Tropical Tidbits API capabilities.

    This is the recommended entry point for most use cases. It composes
    all specialized clients into a single object.

    Usage:
        >>> tt = TropicalTidbitsClient()

        # Get active storms
        >>> storms = tt.storms.parse_active_storms()

        # Download GFS forecast image
        >>> img = tt.models.get_model_image_by_fh("gfs", "2026032418", "mslp_pcpn_frzn", "us", 24)

        # Get satellite imagery
        >>> sat_urls = tt.satellite.parse_sat_image_urls("atl", "ir")

        # Get sounding
        >>> img = tt.models.get_sounding_image("gfs", "2026032418", 24, 29.0, -90.0)
    """

    def __init__(self):
        self.storms = StormInfoClient()
        self.models = ModelsClient()
        self.satellite = SatelliteClient()
        self.surface = SurfaceAnalysisClient()
        self.ocean = OceanAnalysisClient()
        self.hsanalog = HSAnalogClient()
        self.tc_history = TCHistoryClient()
        self.data = DataFilesClient()

    # --- Convenience methods ---

    def get_active_storms(self) -> list[dict]:
        """Return list of currently active tropical storms/cyclones."""
        return self.storms.parse_active_storms()

    def download_model_image(
        self,
        model: str,
        package: str,
        region: str,
        fh: int,
        runtime: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Download a model forecast image, optionally saving to a file.

        Args:
            model: Model name (e.g., "gfs", "ecmwf").
            package: Product package (e.g., "mslp_pcpn_frzn").
            region: Geographic region (e.g., "us", "atl").
            fh: Forecast hour (e.g., 24, 48, 120).
            runtime: Model run time "YYYYMMDDhh" (None = latest).
            output_path: If provided, save image bytes to this file path.

        Returns:
            PNG image bytes.

        Example:
            >>> tt = TropicalTidbitsClient()
            >>> tt.download_model_image("gfs", "mslp_pcpn_frzn", "us", 24, output_path="gfs_024.png")
        """
        img = self.models.get_model_image_by_fh(model, runtime or "", package, region, fh)
        if output_path:
            with open(output_path, "wb") as f:
                f.write(img)
        return img

    def get_latest_satellite_image(
        self,
        region: str,
        product: str = "ir",
        output_path: Optional[str] = None,
    ) -> bytes:
        """
        Get the most recent satellite image for a region.

        Args:
            region: Satellite region (e.g., "atl", "epac", "27P").
            product: Product type (e.g., "ir", "vis", "wv_mid").
            output_path: If provided, save to this file.

        Returns:
            JPEG image bytes.

        Example:
            >>> tt = TropicalTidbitsClient()
            >>> tt.get_latest_satellite_image("atl", "ir", "atlantic_ir.jpg")
        """
        img = self.satellite.get_latest_sat_image(region, product)
        if output_path:
            with open(output_path, "wb") as f:
                f.write(img)
        return img


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import os

    tt = TropicalTidbitsClient()

    print("=" * 60)
    print("Tropical Tidbits API Client - Demo")
    print("=" * 60)

    # 1. Active storms
    print("\n[1] Active Tropical Storms:")
    try:
        storms = tt.get_active_storms()
        if storms:
            for storm in storms:
                print(f"  {storm.get('id')}: {storm.get('name')}")
                print(f"    Location: {storm.get('lat'):.1f}N {storm.get('lon'):.1f}E")
                print(f"    Winds: {storm.get('max_winds_kt')} kt, Pressure: {storm.get('pressure_mb')} mb")
        else:
            print("  No active storms")
    except Exception as e:
        print(f"  Error: {e}")

    # 2. GFS model metadata
    print("\n[2] GFS Model Metadata (CONUS, MSLP+Precip):")
    try:
        meta = tt.models.get_model_metadata("gfs", "us", "mslp_pcpn_frzn")
        print(f"  Runtime: {meta.get('runtime')}")
        print(f"  Forecast hours available: {len(meta.get('img_fh', []))}")
        if meta.get("img_fh"):
            print(f"  Hour range: {meta['img_fh'][0]}h to {meta['img_fh'][-1]}h")
        print(f"  Example image URL: {meta.get('base_url', '')}{meta.get('img_urls', [''])[0]}")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Sounding data availability
    print("\n[3] Sounding Data Availability:")
    try:
        sounding_times = tt.models.get_sounding_data_times()
        models_with_soundings = list(sounding_times.keys())
        print(f"  Models with soundings: {', '.join(models_with_soundings)}")
        if "gfs" in sounding_times:
            gfs_runs = sorted(sounding_times["gfs"].keys(), reverse=True)
            print(f"  Latest GFS sounding run: {gfs_runs[0]}")
            print(f"  FH count: {len(sounding_times['gfs'][gfs_runs[0]])}")
    except Exception as e:
        print(f"  Error: {e}")

    # 4. Satellite regions
    print("\n[4] Satellite Imagery Regions:")
    try:
        sat_regions = tt.satellite.parse_satellite_regions()
        for region, products in list(sat_regions.items())[:5]:
            print(f"  {region}: {', '.join(products)}")
        print(f"  ... ({len(sat_regions)} regions total)")
    except Exception as e:
        print(f"  Error: {e}")

    # 5. Hurricane season analogs
    print("\n[5] Hurricane Season Analogs:")
    try:
        analogs = tt.hsanalog.parse_top_analogs()
        print("  Top analog years:")
        for a in analogs[:5]:
            print(f"    {a['year']}: ACC score = {a['score']}")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n" + "=" * 60)
    print("Demo complete. See docstrings for full API documentation.")
    print("=" * 60)
