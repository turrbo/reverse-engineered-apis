"""
College of DuPage NEXLAB Python Client
=======================================
Reverse-engineered client for https://weather.cod.edu (COD NEXLAB)

Provides access to:
  - NEXRAD Dual-Pol Radar imagery (all Level-3 products)
  - GOES Satellite imagery (all ABI bands + derived products)
  - Numerical Weather Prediction model data (GFS, NAM, HRRR, RAP, ECMWF, etc.)
  - Surface analysis maps and station observations
  - NWS Text products (raw + JSON)
  - Local Storm Reports (JSON)
  - Severe weather warnings (JSON)
  - Campus weather / StormReady status
  - Forecast soundings (model skew-T data)

All endpoints were discovered through static HTML/JS analysis of the COD NEXLAB
website – no login or API key is required.

Usage:
    from cod_nexlab_client import CODNexlabClient

    client = CODNexlabClient()

    # Get latest radar images for LOT (Chicago)
    result = client.get_nexrad_images("LOT", "N0B", num_images=24)
    for url in result["files"]:
        print(url)

    # Download the most recent satellite image
    url = client.get_satellite_current_image("continental", "conus", band="13")
    print(url)

    # Get GFS model image list
    result = client.get_model_images("GFS", "US", "prec", "radar", run="2026032418")
    for url in result["files"]:
        print(url)
"""

import re
import gzip
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------
BASE_URL = "https://weather.cod.edu"
WXDATA_URL = f"{BASE_URL}/wxdata"
CLIMATE_URL = "https://climate.cod.edu"
KAMALA_URL = "https://kamala.cod.edu"

# ---------------------------------------------------------------------------
# Radar product codes (NEXRAD Level-3 dual-pol)
# ---------------------------------------------------------------------------
NEXRAD_PRODUCTS = {
    # Base Reflectivity (tilts 1-4)
    "N0B": "Base Reflectivity Tilt 1",
    "N1B": "Base Reflectivity Tilt 2",
    "N2B": "Base Reflectivity Tilt 3",
    "N3B": "Base Reflectivity Tilt 4",
    # Base Velocity (tilts 1-4)
    "N0G": "Base Velocity Tilt 1",
    "N1G": "Base Velocity Tilt 2",
    "N2U": "Base Velocity Tilt 3",
    "N3U": "Base Velocity Tilt 4",
    # Storm Relative Mean Velocity
    "N0S": "Storm Relative Mean Velocity Tilt 1",
    # Differential Reflectivity (tilts 1-4)
    "N0X": "Differential Reflectivity Tilt 1",
    "N1X": "Differential Reflectivity Tilt 2",
    "N2X": "Differential Reflectivity Tilt 3",
    "N3X": "Differential Reflectivity Tilt 4",
    # Correlation Coefficient (tilts 1-4)
    "N0C": "Correlation Coefficient Tilt 1",
    "N1C": "Correlation Coefficient Tilt 2",
    "N2C": "Correlation Coefficient Tilt 3",
    "N3C": "Correlation Coefficient Tilt 4",
    # Specific Differential Phase (tilts 1-4)
    "N0K": "Specific Differential Phase Tilt 1",
    "N1K": "Specific Differential Phase Tilt 2",
    "N2K": "Specific Differential Phase Tilt 3",
    "N3K": "Specific Differential Phase Tilt 4",
    # Precipitation
    "OHA": "One-Hour Precipitation",
    "DSP": "Storm Total Precipitation",
    # Other
    "DVL": "Vertically Integrated Liquid (VIL)",
    "EET": "Echo Tops",
    "NVW": "Vertical Wind Profile (VWP)",
    "HHC": "Hybrid Hydrometeor Classification (HHC)",
    # Legacy (N0Q = base reflectivity, alias for N0B in URL routing)
    "N0Q": "Base Reflectivity (legacy alias)",
    "N0U": "Base Velocity (legacy alias)",
}

# NEXRAD radar sites (CONUS, selected)
NEXRAD_SITES_CONUS = [
    "ABR", "ABX", "ACG", "AHG", "AIH", "AKC", "AMX", "APD", "APX", "ARX",
    "ATX", "AEC", "BBC", "BGM", "BHX", "BIS", "BLX", "BMX", "BOX", "BRO",
    "BUF", "BYX", "CAE", "CBW", "CBX", "CCX", "CLE", "CLX", "CRP", "CXX",
    "CYS", "DAX", "DDC", "DFX", "DGX", "DIX", "DLH", "DMX", "DOX", "DTX",
    "DVN", "DYX", "EAX", "EMX", "ENX", "EOX", "EPZ", "EVX", "EWX", "EYX",
    "FCX", "FDR", "FDX", "FFC", "FSD", "FSX", "FTG", "FWS", "GGW", "GJX",
    "GLD", "GRB", "GRK", "GRR", "GSP", "GWX", "GYX", "HDC", "HDX", "HGX",
    "HKI", "HKM", "HMO", "HNX", "HPX", "HTX", "HWA", "ICT", "ICX", "ILN",
    "ILX", "IND", "INX", "IWA", "IWX", "JAX", "JGX", "JKL", "JUA", "GUA",
    "KJX", "LBB", "LCH", "LGX", "LNX", "LOT", "LSX", "LTX", "LVX", "LWX",
    "LZK", "MAF", "MAX", "MBX", "MHX", "MKX", "MLB", "MOB", "MPX", "MQT",
    "MRX", "MSX", "MTX", "MUX", "MVX", "MXX", "NKX", "NQA", "OAX", "OHX",
    "OKC", "OTX", "PAH", "PBZ", "PDT", "POE", "PUX", "RAX", "RGX", "RIW",
    "RLX", "RTX", "SGF", "SHV", "SJT", "SOX", "SRX", "TBW", "TFX", "TLH",
    "TLX", "TWX", "TYX", "UDX", "UEX", "VAX", "VBX", "VNX", "VTX", "VWX",
    "ABR", "ABX", "LGX", "YUX",
]

# ---------------------------------------------------------------------------
# Satellite band / product codes
# ---------------------------------------------------------------------------
SATELLITE_BANDS = {
    "01": "Visible - Blue",
    "02": "Visible - Red",
    "03": "Visible - Green/Veggie",
    "04": "Near-IR - Cirrus",
    "05": "Near-IR - Snow/Ice",
    "06": "Near-IR - Cloud Particle Size",
    "07": "Short-Wave IR",
    "08": "Upper-level Water Vapor",
    "09": "Mid-level Water Vapor",
    "10": "Lower-level Water Vapor",
    "11": "Cloud Top Phase",
    "12": "Ozone",
    "13": "Clean Long-wave IR (10.3 µm)",
    "14": "Long-wave IR",
    "15": "Dirty Long-wave IR",
    "16": "CO2 Long-wave IR",
    # Derived / RGB composites
    "comp_radar": "Mosaic NEXRAD Radar",
    "ss_radar":   "NEXRAD Dual-Pol Radar Sites",
    "truecolor":  "True-Color RGB",
    "airmass":    "Colorized Airmass RGB",
    "ntmicro":    "Nighttime Microphysics RGB",
    "dcphase":    "Day Cloud Phase RGB",
    "simplewv":   "Simple Water Vapor RGB",
    "sandwich":   "Visible+IR Sandwich",
}

# Satellite scales, sectors, and typical URL slugs
# scale -> list of valid sector keys
SATELLITE_SCALES = {
    "global": [
        "fulldiskeast", "fulldiskwest", "northernhemi", "southernhemi",
        "northamerica", "southamerica", "atlantic", "southatlantic",
        "equatorial", "capeverde", "southpacific", "halfdiskeastnorth",
        "halfdiskeastsouth",
    ],
    "continental": [
        "conus",  # GOES-East CONUS
    ],
    "regional": [
        "us", "ne", "ma", "se", "ngp", "gl", "nil", "mw", "cgp", "sgp",
        "sw", "nw", "gbsn",
        "can", "wcan", "ecan",
        "ak", "GulfOfAK", "BeringSea",
        "hi", "Hawaii",
        "prregional",
    ],
    "subregional": [
        # All US state abbreviations are valid subregional sectors
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    ],
    "local": [
        "N_Illinois", "Chicago", "Iowa", "S_Minnesota", "Ohio",
        "Indiana", "Kansas", "Oklahoma", "Missouri", "Arkansas",
        "Tennessee", "Alabama", "Georgia", "SE_Coast", "Tri_State",
        "Houston", "Austin", "Dallas", "Denver", "Salt_Lake",
        "Portland", "Seattle", "S_California", "N_California",
        # ... many more, see site for full list
    ],
    "meso": [
        "meso1", "meso2", "meso3", "meso4",  # GOES mesoscale sectors
    ],
}

# Overlay layers available on the satellite page
SATELLITE_OVERLAYS = [
    # Static geographic overlays
    "map", "latlon", "rivers", "counties", "usstrd", "ushw", "usint",
    "cwa", "ranges", "artcc", "id",
    # Weather Watches/Warnings
    "ww",
    # Satellite-derived products (dynamic overlays)
    "sst", "lst", "tpw", "dsi_cape", "adp_dust", "adp_smoke",
    "acha", "acht", "achp", "actp", "rrqpe",
    # Radar overlay
    "radar",
    # Lightning (GLM)
    "glm_fed", "glm_toe", "glm_mfa", "glm_flash",
    # Surface analysis (mesoanalysis)
    "cape", "cin", "dew", "dvg", "gusts", "h5ana", "mdvg", "mslp",
    "pfalls", "scp", "streamlines", "temp", "thetae", "theta",
    "vort", "windv", "plot", "wsym",
    # SPC outlooks
    "spc_day1_cat", "spc_day1_tor", "spc_day1_hail", "spc_day1_wind",
    "spc_day2_cat", "spc_day2_tor", "spc_day2_hail", "spc_day2_wind",
    "spc_day3_cat", "spc_day3_prob",
]

# Colorbars available on the satellite page
SATELLITE_COLORBARS = [
    "data",    # default colorbar for the selected band
    "acha", "acht", "actp", "dsi_cape", "lst", "rrqpe", "sst", "tpw",
]

# ---------------------------------------------------------------------------
# Forecast models
# ---------------------------------------------------------------------------
MODEL_INFO = {
    "HRRR":   {"title": "High Resolution Rapid Refresh",           "server": "wxdata", "ext": ".png", "runStep": 1,  "finalRun": 23},
    "RAP":    {"title": "Rapid Refresh",                           "server": "wxdata", "ext": ".png", "runStep": 3,  "finalRun": 21},
    "NAM":    {"title": "North American Mesoscale Model",          "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
    "NAMNST": {"title": "NAM CONUS Nest 3km",                      "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
    "RDPS":   {"title": "GEM Regional Deterministic (Canada)",     "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
    "SREF":   {"title": "Short Range Ensemble Forecast",           "server": "climate","ext": ".gif", "runStep": 6,  "finalRun": 21},
    "GDPS":   {"title": "GEM Global Deterministic (Canada)",       "server": "wxdata", "ext": ".png", "runStep": 12, "finalRun": 12},
    "ECMWF":  {"title": "European Centre for Medium-Range WF",     "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
    "GFS":    {"title": "Global Forecast System",                  "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
    "GEFS":   {"title": "Global Ensemble Forecast System",         "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
    "CFS":    {"title": "Climate Forecast System",                 "server": "wxdata", "ext": ".png", "runStep": 6,  "finalRun": 18},
}

# Sectors available per model (from get-map.php responses)
MODEL_SECTORS = {
    "GFS":    ["WLD", "NA", "AO", "PO", "US", "NE", "MA", "SE", "NGP", "GL",
               "NIL", "MW", "CGP", "SGP", "AK", "WCAN", "NW", "GBSN", "SW",
               "FLT1", "FLT2"],
    "NAM":    ["US", "NE", "MA", "SE", "NGP", "GL", "NIL", "MW", "CGP", "SGP",
               "AK", "NW", "GBSN", "SW", "FLT1", "FLT2", "FLT3"],
    "HRRR":   ["CGP", "DEN", "FLT1", "FLT2", "FLT3", "GBSN", "GL", "MA",
               "MW", "NE", "NGP", "NIL", "NW", "OKC", "SE", "SGP", "SW"],
    "RAP":    ["US", "NE", "MA", "SE", "NGP", "GL", "NIL", "MW", "CGP", "SGP",
               "AK", "NW", "GBSN", "SW", "FLT1", "FLT2", "FLT3"],
    "ECMWF":  ["WLD", "NA", "AO", "PO", "US", "NE", "MA", "SE", "NGP", "GL",
               "NIL", "MW", "CGP", "SGP", "AK", "WCAN", "NW", "GBSN", "SW",
               "FLT1", "FLT2"],
    "NAMNST": ["US", "NE", "MA", "SE", "NGP", "GL", "NIL", "MW", "CGP", "SGP",
               "NW", "GBSN", "SW", "FLT1", "FLT2", "FLT3"],
    "RDPS":   ["NA", "US", "NE", "MA", "SE", "NGP", "GL", "NIL", "MW", "CGP",
               "SGP", "AK", "WCAN", "NW", "GBSN", "SW", "FLT1", "FLT2"],
    "GDPS":   ["WLD", "NA", "AO", "PO", "US", "NE", "MA", "SE", "NGP", "GL",
               "NIL", "MW", "CGP", "SGP", "AK", "WCAN", "NW", "GBSN", "SW"],
    "GEFS":   ["WLD", "NA", "AO", "PO", "US", "NE", "MA", "SE", "NGP", "GL",
               "NIL", "MW", "CGP", "SGP", "AK", "WCAN", "NW", "GBSN", "SW"],
    "CFS":    ["WLD", "NA", "AO", "PO", "US", "NE", "MA", "SE", "NGP", "GL",
               "NIL", "MW", "CGP", "SGP", "AK", "WCAN", "NW", "GBSN", "SW"],
    "SREF":   ["US", "NE", "MA", "SE", "NGP", "GL", "NIL", "MW", "CGP", "SGP",
               "AK", "NW", "GBSN", "SW"],
}

# Model product categories and products (from get-menu.php GFS response)
MODEL_PRODUCTS = {
    "sfc": {
        "temp":     "Surface Temperature",
        "tempanom": "Surface Temperature Anomaly",
        "tempsa":   "Surface Temperature Spread (ensemble)",
        "dewp":     "Surface Dewpoint",
        "rhum":     "Surface Relative Humidity",
        "thetae":   "Surface Theta-E",
        "mslpsa":   "Mean SLP Spread (ensemble)",
        "avort":    "Surface Absolute Vorticity",
        "30mbdewp": "30mb AGL Dewpoint",
        "wetblb":   "Wet Bulb Temperature",
        "vis":      "Visibility",
    },
    "prec": {
        "radar":     "Simulated Composite Radar",
        "prec":      "Precipitation Rate",
        "precacc":   "Total Precipitation Accumulation",
        "precacc6":  "6-hr Precipitation Accumulation",
        "precacc12": "12-hr Precipitation Accumulation",
        "precacc24": "24-hr Precipitation Accumulation",
        "cprec":     "Convective Precipitation",
        "pwat":      "Precipitable Water",
        "pwatsa":    "Precipitable Water Spread (ensemble)",
        "cloud":     "Cloud Cover",
    },
    "con": {
        "mlcape":   "Mixed-Layer CAPE",
        "mucape":   "Most-Unstable CAPE",
        "sbcape":   "Surface-Based CAPE",
        "3kmehi":   "0-3km EHI",
        "3kmhel":   "0-3km Storm Relative Helicity",
        "lapse57":  "500-700mb Lapse Rate",
        "lapse81":  "800-1000mb Lapse Rate",
        "shear":    "0-6km Bulk Shear",
        "scp":      "Supercell Composite Parameter",
        "lsi":      "Lifted Stability Index",
    },
    "850": {
        "temp":     "850mb Temperature",
        "tempsa":   "850mb Temperature Spread",
        "tempanom": "850mb Temperature Anomaly",
        "dewp":     "850mb Dewpoint",
        "rhum":     "850mb Relative Humidity",
        "thetae":   "850mb Theta-E",
        "tadv":     "850mb Temperature Advection",
        "vvel":     "850mb Vertical Velocity",
        "spd":      "850mb Wind Speed",
        "spdsa":    "850mb Wind Speed Spread",
        "hgtsa":    "850mb Height Spread",
    },
    "700": {
        "temp":     "700mb Temperature",
        "rhum":     "700mb Relative Humidity",
        "vvel":     "700mb Vertical Velocity",
        "avort":    "700mb Absolute Vorticity",
        "spd":      "700mb Wind Speed",
    },
    "500": {
        "temp":     "500mb Temperature",
        "tempsa":   "500mb Temperature Spread",
        "hgtsa":    "500mb Height Spread",
        "avort":    "500mb Absolute Vorticity",
        "rhum":     "500mb Relative Humidity",
        "vvel":     "500mb Vertical Velocity",
        "spd":      "500mb Wind Speed",
        "spdsa":    "500mb Wind Speed Spread",
        "uwndsa":   "500mb U-Wind Spread",
    },
    "250": {
        "spd":      "250mb Wind Speed",
        "spdsa":    "250mb Wind Speed Spread",
        "hgtsa":    "250mb Height Spread",
        "rhum":     "250mb Relative Humidity",
        "uwndsa":   "250mb U-Wind Spread",
    },
    "winter": {
        "ptype":      "Precipitation Type",
        "kuchsnow":   "Snow Accumulation (Kuchera)",
        "kuchsnow6":  "6-hr Snow Accum. (Kuchera)",
        "kuchsnow12": "12-hr Snow Accum. (Kuchera)",
        "kuchsnow24": "24-hr Snow Accum. (Kuchera)",
        "kratio":     "Kuchera Snow Ratio",
        "snow":       "Total Snow Accum. (10:1)",
        "snow6":      "6-hr Snow Accum. (10:1)",
        "snow12":     "12-hr Snow Accum. (10:1)",
        "snow24":     "24-hr Snow Accum. (10:1)",
        "sndepth":    "Snow Depth",
        "frzra":      "Freezing Rain Accumulation",
        "cthk":       "Critical Thickness",
    },
}

# ---------------------------------------------------------------------------
# Surface analysis map regions
# ---------------------------------------------------------------------------
SURFACE_REGIONS = {
    "us":   "Continental United States",
    "wcan": "Western Canada",
    "ecan": "Eastern Canada",
    "can":  "All Canada",
    "ne":   "Northeast US",
    "se":   "Southeast US",
    "mw":   "Midwest US",
    "cgp":  "Central Great Plains",
    "sgp":  "Southern Great Plains",
    "sw":   "Southwest US",
    "nw":   "Northwest US",
    "gc":   "Gulf Coast",
    "tor":  "Tornado Alley",
}

SURFACE_PRODUCTS = {
    "fronts":  "Synoptic fronts + surface analysis",
    "mdiv":    "Moisture Convergence",
    "pfalls":  "Pressure Falls",
    "thte":    "Theta-E and 10m Wind",
    "tpsl":    "Temperature and SLP",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _http_get(url: str, compressed: bool = True) -> bytes:
    """Perform a simple HTTP GET and return raw bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CODNexlabClient/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return data


def _http_get_text(url: str) -> str:
    """Fetch a URL and return text, handling gzip."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CODNexlabClient/1.0",
            "Accept-Encoding": "gzip, deflate",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        content_encoding = resp.headers.get("Content-Encoding", "")
    if content_encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _http_get_json(url: str) -> object:
    """Fetch a URL and return parsed JSON (handles gzip)."""
    return json.loads(_http_get_text(url))


def _get_current_utc() -> datetime:
    return datetime.now(timezone.utc)


def _latest_model_run(model: str, utc_now: Optional[datetime] = None) -> str:
    """
    Return the most recent valid model run string (YYYYMMDDhh) for *model*.

    GFS/NAM/ECMWF/GDPS/GEFS/CFS run at 00, 06, 12, 18Z.
    RAP/RDPS run at 03, 09, 15, 21Z (step=6, offset=3).
    HRRR runs every hour.
    NAMNST runs at 00, 06, 12, 18Z.
    SREF runs at 03, 09, 15, 21Z.
    """
    if utc_now is None:
        utc_now = _get_current_utc()
    info = MODEL_INFO.get(model.upper(), {})
    step = info.get("runStep", 6)
    # Offset from 00Z: RAP/SREF start at 03Z
    offset = 3 if model.upper() in ("RAP", "SREF", "RDPS") else 0
    h = utc_now.hour
    # Find the most recent run hour
    run_hour = ((h - offset) // step) * step + offset
    if run_hour < 0:
        run_hour += 24
        utc_now -= timedelta(days=1)
    run_dt = utc_now.replace(hour=run_hour, minute=0, second=0, microsecond=0)
    return run_dt.strftime("%Y%m%d%H")


# ---------------------------------------------------------------------------
# Main client class
# ---------------------------------------------------------------------------

class CODNexlabClient:
    """
    Thin Python wrapper around the College of DuPage NEXLAB hidden APIs.

    All methods that return lists of image URLs do so in chronological order
    (oldest first). Current-image methods return a single URL string.

    No authentication is required. The server applies rate limiting so
    please be respectful – do not hammer endpoints in tight loops.
    """

    def __init__(self):
        self.base_url = BASE_URL
        self.wxdata_url = WXDATA_URL

    # -----------------------------------------------------------------------
    # NEXRAD Radar
    # -----------------------------------------------------------------------

    def get_nexrad_images(
        self,
        site: str,
        product: str = "N0B",
        num_images: int = 24,
        rate: int = 100,
    ) -> dict:
        """
        Return a list of NEXRAD radar GIF image URLs for *site* and *product*.

        Parameters
        ----------
        site : str
            4-letter NEXRAD site identifier (e.g. "LOT", "OKX", "KFWS").
            The leading "K" is stripped automatically if present.
        product : str
            Product code. See NEXRAD_PRODUCTS for all valid codes.
            Default: "N0B" (Base Reflectivity Tilt 1).
        num_images : int
            How many images to return (3-200). Default: 24.
        rate : int
            Animation rate hint in milliseconds (used by the web UI only).

        Returns
        -------
        dict with keys:
            "files"  : list[str] – image URLs (oldest → newest)
            "img"    : [width, height] – pixel dimensions
            "err"    : bool – True if the site/product is unavailable
        """
        # Strip leading K from 4→3 char codes
        site = site.upper()
        if len(site) == 4 and site.startswith("K"):
            site = site[1:]

        product = product.upper()
        loop = 0  # don't animate on load
        parms = f"{site}-{product}-{loop}-{num_images}-{rate}"
        url = (
            f"{self.base_url}/satrad/nexrad/assets/php/get-files.php"
            f"?parms={parms}"
        )
        data = _http_get_text(url)
        if data.strip() == "error":
            return {"files": [], "img": [900, 900], "err": True}
        return json.loads(data)

    def get_nexrad_image_url(
        self,
        site: str,
        product: str,
        date: str,
        time: str,
    ) -> str:
        """
        Build a direct GIF URL for a specific NEXRAD image.

        Parameters
        ----------
        site    : str  – 3-letter site code (e.g. "LOT")
        product : str  – product code (e.g. "N0B")
        date    : str  – "YYYYMMDD"
        time    : str  – "HHMM" in UTC (e.g. "0230")

        Returns
        -------
        str – direct GIF URL
        """
        site = site.upper()
        if len(site) == 4 and site.startswith("K"):
            site = site[1:]
        product = product.upper()
        return (
            f"{self.wxdata_url}/nexrad/{site}/{product}"
            f"/{site}.{product}.{date}.{time}.gif"
        )

    def get_nexrad_gif(
        self,
        site: str,
        product: str = "N0B",
        num_frames: int = 24,
        rate: int = 100,
    ) -> str:
        """
        Request a server-rendered animated GIF of the last *num_frames* scans.

        The server renders the GIF on demand (allow 30-60 s for generation).
        Returns the URL to retrieve the finished GIF.

        Note: This endpoint may timeout for large frame counts.
        """
        site = site.upper()
        if len(site) == 4 and site.startswith("K"):
            site = site[1:]
        parms = f"{site}-{product.upper()}-{num_frames}-{rate}"
        return (
            f"{self.base_url}/satrad/nexrad/assets/php/scripts/mkgif.php"
            f"?parms={parms}"
        )

    def get_nexrad_zip(
        self,
        site: str,
        product: str = "N0B",
        num_frames: int = 24,
    ) -> str:
        """
        Return the URL of a ZIP archive of the last *num_frames* radar GIFs.
        The server packs the files on demand (allow a few seconds).
        """
        site = site.upper()
        if len(site) == 4 and site.startswith("K"):
            site = site[1:]
        parms = f"{site}-{product.upper()}-{num_frames}"
        return (
            f"{self.base_url}/satrad/nexrad/assets/php/scripts/mkzip.php"
            f"?parms={parms}"
        )

    # -----------------------------------------------------------------------
    # GOES Satellite imagery
    # -----------------------------------------------------------------------

    def get_satellite_image_list(
        self,
        scale: str,
        sector: str,
        band: str = "13",
        num_images: int = 24,
        nth: int = 1,
    ) -> list:
        """
        Return the list of satellite image URLs embedded in the satrad page.

        The COD satrad page inlines all image URLs directly in the HTML so
        this method downloads and parses the page HTML.

        Parameters
        ----------
        scale      : str  – one of: global, continental, regional,
                               subregional, local, meso
        sector     : str  – sector name, e.g. "conus", "IL", "meso1"
        band       : str  – band/product code (see SATELLITE_BANDS)
        num_images : int  – number of frames to embed
        nth        : int  – take every Nth frame (1 = every frame)

        Returns
        -------
        list[str]  – image URLs, oldest → newest
        """
        loop = 0
        rate = 100
        parms = f"{scale}-{sector}-{band}-{num_images}-{loop}-{rate}-{nth}"
        url = f"{self.base_url}/satrad/?parms={parms}&checked=map&colorbar=undefined"
        html = _http_get_text(url)

        # Images are embedded as <img src="..." id="N"> in a preloader div
        pattern = (
            r'<img[^>]+src="('
            + re.escape(self.wxdata_url)
            + r'/satellite/[^"]+\.(jpg|png|gif))"'
        )
        matches = re.findall(pattern, html)
        # matches = [(url, ext), ...]
        image_urls = [m[0] for m in matches if "/current/" not in m[0] and "/maps/" not in m[0] and "/colorbars/" not in m[0] and "/overlays/" not in m[0]]

        # Deduplicate while preserving order
        seen = set()
        result = []
        for u in image_urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    def get_satellite_current_image(
        self,
        scale: str,
        sector: str,
        band: str = "13",
    ) -> str:
        """
        Return the URL of the single most-recent satellite image.

        This endpoint is served directly from a "current" directory and
        refreshes every few minutes.

        Parameters
        ----------
        scale  : str  – "continental", "regional", "subregional", "local",
                         "meso", or "global"
        sector : str  – sector name (e.g. "conus", "IL", "ne")
        band   : str  – band/product code (see SATELLITE_BANDS)

        Returns
        -------
        str – direct JPG URL
        """
        sector_lc = sector.lower()
        band_lc = band.lower()
        return (
            f"{self.wxdata_url}/satellite/{scale}/{sector_lc}"
            f"/current/{sector_lc}.{band_lc}.jpg"
        )

    def get_satellite_image_direct(
        self,
        scale: str,
        sector: str,
        band: str,
        datetime_str: str,
    ) -> str:
        """
        Build the direct URL for a specific archived satellite image.

        Parameters
        ----------
        scale        : str  – "continental", "regional", etc.
        sector       : str  – sector name
        band         : str  – band code
        datetime_str : str  – "YYYYMMDDHHmmss" (UTC) as seen in the filename,
                               e.g. "20260325022117"

        Returns
        -------
        str – direct JPG URL

        URL pattern:
          https://weather.cod.edu/wxdata/satellite/{scale}/{sector}/{band}/
            {sector}.{band}.{date8}.{time6}.jpg
        """
        sector_lc = sector.lower()
        band_lc = band.lower()
        # Parse date8 and time6 from datetime_str
        date8 = datetime_str[:8]
        time6 = datetime_str[8:14]
        return (
            f"{self.wxdata_url}/satellite/{scale}/{sector_lc}/{band_lc}"
            f"/{sector_lc}.{band_lc}.{date8}.{time6}.jpg"
        )

    def get_satellite_overlay_url(
        self,
        scale: str,
        sector: str,
        overlay: str,
        datetime_str: str,
    ) -> str:
        """
        Build the URL for a satellite overlay image at a given time.

        GOES-derived overlays (SST, TPW, ACHA, etc.) are semi-transparent
        PNGs that are composited on top of the base satellite image.

        Parameters
        ----------
        scale        : str  – "continental", "regional", etc.
        sector       : str  – sector name
        overlay      : str  – overlay name from SATELLITE_OVERLAYS
        datetime_str : str  – "YYYYMMDDHHmmss" UTC

        Returns
        -------
        str – PNG overlay URL
        """
        sector_lc = sector.lower()
        return (
            f"{self.wxdata_url}/satellite/{scale}/{sector_lc}/overlays/{overlay}"
            f"/{sector_lc}-{overlay}.{datetime_str}.png"
        )

    def get_satellite_map_layer(self, scale: str, sector: str, layer: str = "map") -> str:
        """
        Return the URL for a static geographic map layer PNG (counties, CWAs, etc.)

        Parameters
        ----------
        scale  : str  – satellite scale
        sector : str  – sector name
        layer  : str  – one of: map, counties, cwa, latlon, rivers, usstrd,
                         ushw, usint, artcc (availability varies by sector)

        Returns
        -------
        str – PNG URL
        """
        sector_lc = sector.lower()
        return (
            f"{self.wxdata_url}/satellite/{scale}/{sector_lc}/maps"
            f"/{sector_lc}_{layer}.png"
        )

    def get_satellite_colorbar(self, colorbar: str) -> str:
        """Return URL for a satellite product colorbar PNG."""
        return f"{self.wxdata_url}/satellite/colorbars/{colorbar}.png"

    # -----------------------------------------------------------------------
    # Numerical Weather Prediction Models
    # -----------------------------------------------------------------------

    def get_model_best_run(
        self,
        model: str,
        valid_time: Optional[str] = None,
        start_hour: int = 0,
    ) -> dict:
        """
        Query the server for the best available model run for a given valid time.

        Parameters
        ----------
        model      : str            – model name (e.g. "GFS", "NAM", "HRRR")
        valid_time : str | None     – desired valid time as "YYYYMMDDhh".
                                       Defaults to the most recent run.
        start_hour : int            – initial forecast hour within that run.

        Returns
        -------
        dict with keys:
            "result"       : "YYYYMMDDHH+FH"  – e.g. "2026032418+6"
            "validIn"      : str
            "validOut"     : str
            "validMatches" : list[str] – alternative runs covering same valid time
            "code"         : str  – "00" means exact match; "10" = closest
            "formatted"    : dict – human-readable run/valid time info
        """
        if valid_time is None:
            valid_time = _latest_model_run(model)
        parms = f"{model.upper()}-{valid_time}-{start_hour}"
        url = (
            f"{self.base_url}/forecast/assets/php/scripts/get-best.php"
            f"?parms={parms}"
        )
        return _http_get_json(url)

    def get_model_images(
        self,
        model: str,
        sector: str,
        category: str,
        product: str,
        run: Optional[str] = None,
        start_hour: int = 0,
        loop: int = 0,
        rate: int = 100,
    ) -> dict:
        """
        Return the list of forecast model image URLs for a given run.

        Parameters
        ----------
        model    : str  – model name (e.g. "GFS", "NAM", "HRRR")
        sector   : str  – geographic sector (e.g. "US", "MW", "NE")
        category : str  – product category (e.g. "sfc", "prec", "500")
        product  : str  – product name within category (e.g. "temp", "radar")
        run      : str | None – run string "YYYYMMDDhh". Defaults to most recent.
        start_hour : int – initial forecast hour to display
        loop     : int  – 1 to autoplay, 0 for static
        rate     : int  – animation rate in ms

        Returns
        -------
        dict with keys:
            "files"    : list[str] – image URLs (f000, f003, …)
            "readouts" : list[str] – gzipped readout data URLs (may be absent)
            "parms"    : list      – parsed parameter array from server
            "img"      : dict      – image dimensions
            "err"      : str       – "false" if OK
        """
        if run is None:
            run = _latest_model_run(model)

        model = model.upper()
        sector = sector.upper()
        parms = f"{run}-{model}-{sector}-{category}-{product}-{start_hour}-{loop}-{rate}"
        url = (
            f"{self.base_url}/forecast/assets/php/scripts/get-files.php"
            f"?parms={parms}"
        )
        data = _http_get_text(url)
        if data.strip() == "error":
            return {"files": [], "err": "true", "parms": []}
        return json.loads(data)

    def get_model_image_direct(
        self,
        model: str,
        run: str,
        sector: str,
        category: str,
        product: str,
        fhour: int,
    ) -> str:
        """
        Build the direct URL for a single forecast model image.

        URL pattern:
          https://weather.cod.edu/wxdata/forecast/{MODEL}/{run}/{SECTOR}/
            {MODEL}{SECTOR}_{category}_{product}_{FHH}.png

        Parameters
        ----------
        model    : str  – model name
        run      : str  – run string "YYYYMMDDhh"
        sector   : str  – sector code
        category : str  – product category
        product  : str  – product name
        fhour    : int  – forecast hour (0, 3, 6, …)

        Returns
        -------
        str – direct PNG (or GIF for SREF) URL
        """
        model_u = model.upper()
        sector_u = sector.upper()
        ext = MODEL_INFO.get(model_u, {}).get("ext", ".png")
        fh_str = f"{fhour:03d}"
        return (
            f"{self.wxdata_url}/forecast/{model_u}/{run}/{sector_u}"
            f"/{model_u}{sector_u}_{category}_{product}_{fh_str}{ext}"
        )

    def get_model_readout(
        self,
        model: str,
        run: str,
        sector: str,
        category: str,
        product: str,
        fhour: int,
    ) -> str:
        """
        Build the URL for the point-readout data file (gzipped text).

        These text.gz files contain a grid of meteorological values that
        the website uses to display hover-over data values on the map.

        Returns
        -------
        str – URL of the .txt.gz readout file
        """
        model_u = model.upper()
        sector_u = sector.upper()
        fh_str = f"{fhour:03d}"
        return (
            f"{self.wxdata_url}/forecast/{model_u}/{run}/{sector_u}/readout"
            f"/{model_u}{sector_u}_{category}_{product}_{fh_str}.txt.gz"
        )

    def get_model_forecast_sounding(
        self,
        model: str,
        run: str,
        sector: str,
        category: str,
        product: str,
        fhour: int,
        lat: float,
        lon: float,
        parcel: str = "sb",
        wx_type: str = "wxdata",
    ) -> str:
        """
        Return the URL for the forecast sounding page at a given location.

        The sounding page uses GrADS-extracted vertical profile data and
        displays a SHARPpy-style skew-T log-P diagram.

        Parameters
        ----------
        model    : str   – model name
        run      : str   – run string "YYYYMMDDhh"
        sector   : str   – sector code
        category : str   – product category
        product  : str   – product name
        fhour    : int   – forecast hour
        lat      : float – latitude (decimal degrees N)
        lon      : float – longitude (decimal degrees E; use negative for W)
        parcel   : str   – "sb" (surface-based), "ml" (mixed-layer), "mu" (most-unstable)
        wx_type  : str   – "wxdata" (standard) or "severe" / "winter"

        Returns
        -------
        str – URL to the forecast sounding page (HTML, opens in browser)
        """
        type_str = (
            f"{run}|{model.upper()}|{sector.upper()}|{category}|{product}"
            f"|{fhour}|{lat:.2f},{lon:.2f}|{parcel}|{wx_type}"
        )
        encoded = urllib.parse.quote(type_str, safe="|")
        return f"{self.base_url}/forecast/fsound/index.php?type={encoded}"

    def get_model_menu(
        self,
        model: str,
        run: Optional[str] = None,
        sector: str = "null",
        category: str = "null",
        product: str = "null",
        fhour: int = 0,
        loop: int = 0,
        rate: int = 100,
    ) -> str:
        """
        Fetch the HTML fragment for the model product navigation menu.

        This is the same HTML fragment the website inserts into the sidebar.
        Useful for discovering available products/sectors for a given run.

        Returns
        -------
        str – HTML string containing product buttons and hour selector
        """
        if run is None:
            run = "current"
        parms = f"{run}-{model.upper()}-{sector}-{category}-{product}-{fhour}-{loop}-{rate}"
        url = (
            f"{self.base_url}/forecast/assets/php/scripts/get-menu.php"
            f"?parms={parms}"
        )
        return _http_get_text(url)

    # -----------------------------------------------------------------------
    # Surface Analysis
    # -----------------------------------------------------------------------

    def get_surface_analysis_gif(
        self,
        region: str = "us",
        product: str = "fronts",
        date: Optional[str] = None,
        hour: Optional[int] = None,
    ) -> str:
        """
        Build the URL for a surface analysis contour GIF image.

        Parameters
        ----------
        region  : str       – region code (see SURFACE_REGIONS)
        product : str       – product type (see SURFACE_PRODUCTS)
        date    : str|None  – "YYYYMMDD". Defaults to today UTC.
        hour    : int|None  – UTC hour (0-23). Defaults to most recent synoptic.

        Returns
        -------
        str – direct GIF URL

        URL pattern:
          https://weather.cod.edu/wxdata/surface/{REGION}/contour/
            {REGION}.{product}.{YYYYMMDD}.{HH}.gif
        """
        if date is None:
            now = _get_current_utc()
            date = now.strftime("%Y%m%d")
            hour = hour if hour is not None else now.hour
        if hour is None:
            hour = _get_current_utc().hour
        region_u = region.upper()
        return (
            f"{self.wxdata_url}/surface/{region_u}/contour"
            f"/{region_u}.{product}.{date}.{hour:02d}.gif"
        )

    def get_surface_analysis_pdf(
        self,
        region: str = "US",
        date: Optional[str] = None,
        hour: Optional[int] = None,
    ) -> str:
        """
        Build the URL for a surface analysis PDF map.

        URL pattern:
          https://weather.cod.edu/wxdata/surface/{REGION}/pdf/
            {REGION}.{YYYYMMDD}.{HH}.pdf
        """
        if date is None:
            now = _get_current_utc()
            date = now.strftime("%Y%m%d")
            hour = hour if hour is not None else now.hour
        if hour is None:
            hour = _get_current_utc().hour
        region_u = region.upper()
        return (
            f"{self.wxdata_url}/surface/{region_u}/pdf"
            f"/{region_u}.{date}.{hour:02d}.pdf"
        )

    def get_surface_hires_gif(self, region: str = "US_zoom") -> str:
        """Return the URL for the high-resolution current surface fronts GIF."""
        return f"{self.wxdata_url}/surface/{region}/contour/current/{region}.fronts.gif"

    # -----------------------------------------------------------------------
    # NWS Text Products
    # -----------------------------------------------------------------------

    def get_nws_text_raw(self, office: str, product_id: str) -> str:
        """
        Fetch raw NWS text product from the COD text archive.

        Parameters
        ----------
        office     : str  – 4-letter NWS office ID (e.g. "KLOT", "KORD")
        product_id : str  – WMO/AWIPS product header string
                            (e.g. "NOUS63_FTMLOT", "NOUS42_PNSGJT")

        Returns
        -------
        str – raw NWS text

        URL pattern:
          https://weather.cod.edu/textserv/raw/{OFFICE}/{product_id}/
        """
        url = f"{self.base_url}/textserv/raw/{office.upper()}/{product_id}/"
        return _http_get_text(url)

    def get_severe_warnings_active(self) -> list:
        """
        Return a list of currently active severe weather warnings (JSON).

        Returns empty list if no active warnings exist.

        Returns
        -------
        list[dict] – each dict has keys:
            warn_type, office, counties, time_begin, time_end,
            tornado, hail, wind, files
        """
        url = f"{self.base_url}/textserv/json/svr/active"
        return _http_get_json(url)

    def get_severe_warnings_active_v2(self) -> list:
        """
        Return active severe weather warnings with extended fields.

        Returns
        -------
        list[dict] – extended warning objects (more detail than v1)
        """
        url = f"{self.base_url}/textserv/json/svr/active-2"
        return _http_get_json(url)

    def get_severe_warnings_recent(self) -> list:
        """
        Return recently expired (non-active) severe weather warnings.

        Returns
        -------
        list[dict] – similar structure to active warnings
        """
        url = f"{self.base_url}/textserv/json/svr/nonactive-2"
        return _http_get_json(url)

    def get_local_storm_reports(self, days: int = 1) -> list:
        """
        Return Local Storm Reports (LSRs) from the past *days* days.

        The response is gzip-compressed JSON from the COD text server.

        Parameters
        ----------
        days : int  – how many days of LSRs to retrieve (default: 1)

        Returns
        -------
        list[dict] – each report has:
            county, event, latlon, local_time, location,
            magnitude_f, magnitude_str, magnitude_units,
            magnitude_qualifier, office, office_plain, remark,
            source, state, valid_time, valid_time_short, valid_time_ts
        """
        url = f"{self.base_url}/textserv/json/lsr?days={days}"
        return _http_get_json(url)

    # -----------------------------------------------------------------------
    # Campus Weather / Storm Ready Status
    # -----------------------------------------------------------------------

    def get_campus_storm_ready_status(self) -> str:
        """
        Return the current COD campus Storm Ready / Severe Weather
        condition color code.

        Returns
        -------
        str – one of: "none", "blue", "green", "yellow", "red"

        Meanings:
            none   – no threat
            blue   – CONDITION BLUE  (general severe weather threat)
            green  – CONDITION GREEN (organized storm threat approaching)
            yellow – CONDITION YELLOW (imminent severe weather threat)
            red    – CONDITION RED   (tornado or extreme danger)
        """
        url = (
            f"{self.base_url}/campusweather/assets/php/scripts/SRstatus.php"
        )
        return _http_get_text(url).strip()

    # -----------------------------------------------------------------------
    # WFO-RDA (radar site) lookup
    # -----------------------------------------------------------------------

    def get_wfo_rda_map(self) -> dict:
        """
        Return the mapping from NWS WFO office codes to NEXRAD site IDs.

        This JSON file is served from the NEXRAD page assets and maps
        3-letter WFO codes (e.g. "LOT") to lists of associated radar
        site IDs (e.g. ["KLOT", "KILX"]).

        Returns
        -------
        dict – {wfo_code: [radar_site, ...], ...}
        """
        url = f"{self.base_url}/satrad/nexrad/assets/json/wfo-rda.json"
        return _http_get_json(url)

    # -----------------------------------------------------------------------
    # Alert / site status
    # -----------------------------------------------------------------------

    def get_site_alert(self, section: str = "nexrad") -> str:
        """
        Return the current COD NEXLAB site alert message JavaScript.

        Parameters
        ----------
        section : str  – "nexrad", "satrad", or "forecast"

        Returns
        -------
        str – raw JS text (may contain alert message or empty alert)
        """
        url = f"{self.base_url}/assets/javascript/alert/{section}.js"
        return _http_get_text(url)

    # -----------------------------------------------------------------------
    # Archive helpers (Iowa State / mtarchive)
    # -----------------------------------------------------------------------

    @staticmethod
    def get_iowa_state_archive_url(
        year: int,
        month: int,
        day: int,
    ) -> str:
        """
        Return the Iowa State University mtarchive URL for a given date.

        COD archives satellite data to Iowa State after ~3-4 days.
        Navigate this URL in a browser to find archived satellite images.

        Returns
        -------
        str – Iowa State archive URL
        """
        return (
            f"https://mtarchive.geol.iastate.edu"
            f"/{year}/{month:02d}/{day:02d}/cod/sat/"
        )

    # -----------------------------------------------------------------------
    # Convenience / composite methods
    # -----------------------------------------------------------------------

    def download_latest_radar_gif(
        self,
        site: str,
        product: str = "N0B",
        save_path: Optional[str] = None,
    ) -> bytes:
        """
        Download the most recent radar GIF frame and return raw bytes.

        Parameters
        ----------
        site      : str        – 3-letter radar site code
        product   : str        – product code
        save_path : str|None   – if given, save bytes to this file path

        Returns
        -------
        bytes – raw GIF data
        """
        result = self.get_nexrad_images(site, product, num_images=1)
        if result.get("err") or not result.get("files"):
            raise ValueError(f"No radar data available for {site}/{product}")
        url = result["files"][-1]  # most recent is last
        data = _http_get(url)
        if save_path:
            with open(save_path, "wb") as fh:
                fh.write(data)
        return data

    def download_latest_satellite_image(
        self,
        scale: str = "continental",
        sector: str = "conus",
        band: str = "13",
        save_path: Optional[str] = None,
    ) -> bytes:
        """
        Download the most recent satellite image JPEG and return raw bytes.

        Parameters
        ----------
        scale     : str        – satellite scale
        sector    : str        – sector name
        band      : str        – band/product code
        save_path : str|None   – optional file path to save the image

        Returns
        -------
        bytes – raw JPEG data
        """
        url = self.get_satellite_current_image(scale, sector, band)
        data = _http_get(url)
        if save_path:
            with open(save_path, "wb") as fh:
                fh.write(data)
        return data

    def download_model_image(
        self,
        model: str,
        sector: str,
        category: str,
        product: str,
        fhour: int = 0,
        run: Optional[str] = None,
        save_path: Optional[str] = None,
    ) -> bytes:
        """
        Download a specific model forecast image and return raw bytes.

        Parameters
        ----------
        model     : str        – model name
        sector    : str        – sector code
        category  : str        – product category
        product   : str        – product code
        fhour     : int        – forecast hour
        run       : str|None   – run string; defaults to most recent
        save_path : str|None   – optional file path

        Returns
        -------
        bytes – raw PNG data
        """
        if run is None:
            best = self.get_model_best_run(model)
            run = best["result"].split("+")[0]
        url = self.get_model_image_direct(model, run, sector, category, product, fhour)
        data = _http_get(url)
        if save_path:
            with open(save_path, "wb") as fh:
                fh.write(data)
        return data

    def get_latest_lsr_summary(self, days: int = 1) -> dict:
        """
        Fetch LSRs and return a summary grouped by event type.

        Returns
        -------
        dict – {event_type: [report_dict, ...], ...}
        """
        reports = self.get_local_storm_reports(days)
        summary = {}
        for report in reports:
            evt = report.get("event", "Unknown")
            summary.setdefault(evt, []).append(report)
        return summary


# ---------------------------------------------------------------------------
# Quick demo / CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    client = CODNexlabClient()

    print("=" * 60)
    print("COD NEXLAB API Client – Quick Demo")
    print("=" * 60)
    print()

    # 1. NEXRAD radar
    print("[1] Latest 6 radar frames for LOT (Chicago) – Base Reflectivity")
    result = client.get_nexrad_images("LOT", "N0B", num_images=6)
    if not result.get("err"):
        for url in result["files"]:
            print("   ", url)
    else:
        print("    (no data)")
    print()

    # 2. Current satellite image
    print("[2] Current CONUS Band-13 (clean IR) satellite image")
    url = client.get_satellite_current_image("continental", "conus", "13")
    print("   ", url)
    print()

    # 3. GFS model images
    print("[3] Latest GFS US prec/radar images")
    best = client.get_model_best_run("GFS")
    run = best["result"].split("+")[0]
    print(f"    Best run: {run}")
    result = client.get_model_images("GFS", "US", "prec", "radar", run=run)
    if not result.get("err") or result.get("err") == "false":
        for url in result.get("files", [])[:3]:
            print("   ", url)
        print(f"    ... ({len(result.get('files', []))} total)")
    print()

    # 4. LSR summary
    print("[4] Local Storm Reports – today (event type counts)")
    try:
        summary = client.get_latest_lsr_summary(days=1)
        for event, rpts in sorted(summary.items(), key=lambda x: -len(x[1])):
            print(f"    {event}: {len(rpts)} report(s)")
    except Exception as exc:
        print(f"    Error: {exc}")
    print()

    # 5. Campus Storm Ready status
    print("[5] COD Campus Storm Ready status")
    status = client.get_campus_storm_ready_status()
    print(f"    Status: {status.upper()}")
    print()

    # 6. Severe warnings
    print("[6] Active severe weather warnings")
    warnings = client.get_severe_warnings_active()
    if warnings:
        for w in warnings:
            print(f"    {w.get('warn_type')} – {w.get('office')} – {', '.join(w.get('counties', []))}")
    else:
        print("    (none active)")
    print()

    print("Done.")
