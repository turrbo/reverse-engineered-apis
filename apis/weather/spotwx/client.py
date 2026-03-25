"""
SpotWX API Client
=================
A comprehensive Python client for the SpotWX (https://spotwx.com) weather
forecast service, reverse-engineered from the site's internal API.

SpotWX provides point weather forecasts from 20+ NWP models for any
latitude/longitude on Earth. This client exposes all discovered endpoints.

Key Endpoints Discovered
------------------------
1. GET /products/spot_info2.php
   - Returns timezone info for a lat/lon

2. GET /products/spotcatalog_u2.php
   - Lists available forecast products (models, station forecasts, zone forecasts)
   - type=nm    -> Numerical Weather Models
   - type=point -> Nearest Station Forecasts
   - type=zone  -> Area Forecasts

3. GET /products/grib_polys_u.php
   - Returns grid polygon boundaries + links for each model at a point

4. GET /products/scribe_points_u.php
   - Returns nearest SCRIBE station info + links

5. GET /products/nowcast_points_u.php
   - Returns nearest NOWCAST station info + links

6. GET /products/mc_zone_u2.php
   - Returns nearest Meteocode zone identifier
   - range=short | extended

7. GET /products/grib_index.php
   - The main forecast data endpoint (returns HTML with embedded Highcharts JS)
   - Supports both chart view (default) and tabular CSV view (?display=table)
   - Parameters: model, lat, lon, tz, [label, tcid, station, zone, title]

All forecast data is embedded in the HTML as JavaScript arrays for Highcharts.
The tabular view (?display=table) provides an aDataSet variable with structured
CSV-like rows.

Units are controlled by cookies:
  tmpunits:  C | F | K
  windunits: kph | mph | kn | ms
  pcpunits:  mm | in | kg
  presunits: mb | hPa | kPa | inHg | mmHg
  altunits:  m | ft
  distunits: km | mi | NM
  timeunits: t12 | t24

Available Model IDs
-------------------
ECCC (Environment and Climate Change Canada):
  hrdps_1km_west      - HRDPS 1km West, 2-day, 1 km resolution
  hrdps_continental   - HRDPS Continental, 2-day, 2.5 km resolution
  rdps_10km           - RDPS, 3.5-day, 10 km resolution
  gdps_15km           - GDPS, 10-day, 15 km resolution
  geps_0p5_raw        - GEPS Ensemble, 16-day, 0.5 degree resolution

ECMWF:
  ecmwf_ifs           - ECMWF IFS, 15-day, 0.25 degree resolution
  ecmwf_aifs_single   - ECMWF AIFS (AI), 15-day, 0.25 degree resolution

NOAA (USA):
  hrrr_wrfprsf        - HRRR, 18/48-hr, 3 km resolution
  rap_awp130pgrbf     - RAP, 21-hr, 13 km resolution
  nam_awphys          - NAM, 3.5-day, 12 km resolution
  sref_pgrb132        - SREF Ensemble, 87-hr, 16 km resolution
  gfs_pgrb2_0p25_f    - GFS, 10-day, 0.25 degree resolution
  gfs_uv              - GFS UV Index, 5-day, 0.5 degree resolution

Station-based (ECCC):
  scribe_r            - SCRIBE Regional (based on RDPS), needs tcid param
  scribe_g            - SCRIBE Global (based on GDPS), needs tcid param
  scribe_x            - Extended SCRIBE (based on GDPS), needs tcid param
  scribe_hybrid       - Hybrid SCRIBE, needs tcid param
  nwcstg              - NOWCAST, needs tcid param

Zone-based:
  meteocode           - Meteocode zone forecast, needs zone+title params
"""

from __future__ import annotations

import re
import json
import calendar
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urlencode, urljoin

import requests

BASE_URL = "https://spotwx.com"


# ---------------------------------------------------------------------------
# Unit constants
# ---------------------------------------------------------------------------

class TempUnits:
    CELSIUS    = "C"
    FAHRENHEIT = "F"
    KELVIN     = "K"

class WindUnits:
    KPH    = "kph"
    MPH    = "mph"
    KNOTS  = "kn"
    MS     = "ms"

class PrecipUnits:
    MM  = "mm"
    IN  = "in"
    KG  = "kg"

class PressureUnits:
    MB   = "mb"
    HPA  = "hPa"
    KPA  = "kPa"
    INHG = "inHg"
    MMHG = "mmHg"

class AltUnits:
    METERS = "m"
    FEET   = "ft"

class DistUnits:
    KM = "km"
    MI = "mi"
    NM = "NM"

class TimeFormat:
    T12 = "t12"
    T24 = "t24"


# ---------------------------------------------------------------------------
# Model ID constants
# ---------------------------------------------------------------------------

class Models:
    # ECCC
    HRDPS_1KM_WEST    = "hrdps_1km_west"
    HRDPS_CONTINENTAL = "hrdps_continental"
    RDPS              = "rdps_10km"
    GDPS              = "gdps_15km"
    GEPS              = "geps_0p5_raw"

    # ECMWF
    ECMWF_IFS         = "ecmwf_ifs"
    ECMWF_AIFS        = "ecmwf_aifs_single"

    # NOAA
    HRRR              = "hrrr_wrfprsf"
    RAP               = "rap_awp130pgrbf"
    NAM               = "nam_awphys"
    SREF              = "sref_pgrb132"
    GFS               = "gfs_pgrb2_0p25_f"
    GFS_UV            = "gfs_uv"

    # ECCC station-based
    SCRIBE_REGIONAL   = "scribe_r"
    SCRIBE_GLOBAL     = "scribe_g"
    SCRIBE_EXTENDED   = "scribe_x"
    SCRIBE_HYBRID     = "scribe_hybrid"
    NOWCAST           = "nwcstg"

    # Zone-based
    METEOCODE         = "meteocode"

    @classmethod
    def all_gridded(cls) -> list[str]:
        """Return all gridded (lat/lon) model IDs."""
        return [
            cls.HRDPS_1KM_WEST, cls.HRDPS_CONTINENTAL,
            cls.RDPS, cls.GDPS, cls.GEPS,
            cls.ECMWF_IFS, cls.ECMWF_AIFS,
            cls.HRRR, cls.RAP, cls.NAM, cls.SREF,
            cls.GFS, cls.GFS_UV,
        ]


# ---------------------------------------------------------------------------
# Data parsing helpers
# ---------------------------------------------------------------------------

def _parse_highcharts_series(html: str) -> list[dict]:
    """
    Parse Highcharts series data embedded in SpotWX HTML pages.

    Returns a list of dicts:
        {
          "name": str,
          "data": [{"datetime": datetime (UTC), "value": float, ...}, ...]
        }

    SpotWX uses two data point formats:
      [Date.UTC(year, month0, day, hour, min), value]
      {x: Date.UTC(year, month0, day, hour, min), y: value, desc: "..."}
    """
    series_list: list[dict] = []

    # Split on chart definitions — each name: ... data: [...] block
    # We anchor on the `name:` key so we capture name + immediately following data
    raw_series = re.findall(
        r'name:\s*["\']([^"\']+)["\']\s*.*?data:\s*\[\n?(.*?)\n?\s*\]',
        html,
        re.DOTALL,
    )

    for name, raw_data in raw_series:
        points: list[dict] = []

        # Format 1: [Date.UTC(y, m0, d, H, M), value]
        for m in re.finditer(
            r'\[Date\.UTC\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\),\s*([-\d.]+)\]',
            raw_data,
        ):
            year, month0, day, hour, minute, value = m.groups()
            dt = datetime(
                int(year), int(month0) + 1, int(day),
                int(hour), int(minute), tzinfo=timezone.utc,
            )
            points.append({"datetime": dt, "value": float(value)})

        # Format 2: {x: Date.UTC(y, m0, d, H, M), y: value, desc: "..."}
        if not points:
            for m in re.finditer(
                r'\{x:\s*Date\.UTC\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\),\s*'
                r'y:\s*([-\d.]+)(?:,\s*desc:\s*["\']([^"\']*)["\'])?\}',
                raw_data,
            ):
                year, month0, day, hour, minute, value = m.groups()[:6]
                desc = m.group(7) or None
                dt = datetime(
                    int(year), int(month0) + 1, int(day),
                    int(hour), int(minute), tzinfo=timezone.utc,
                )
                entry: dict = {"datetime": dt, "value": float(value)}
                if desc:
                    entry["desc"] = desc
                points.append(entry)

        if points:
            series_list.append({"name": name, "data": points})

    return series_list


def _parse_tabular_data(html: str) -> dict:
    """
    Parse the tabular (?display=table) version of a SpotWX forecast page.

    Returns:
        {
          "columns": [str, ...],
          "rows": [[str, ...], ...]
        }
    """
    # Extract column headers
    columns = re.findall(r'"sTitle":\s*"([^"]+)"', html)

    # Extract aDataSet array rows
    rows: list[list[str]] = []
    idx = html.find("aDataSet")
    if idx >= 0:
        # Grab everything from aDataSet = [ ... ];
        chunk = html[idx:]
        end = chunk.find("];")
        if end > 0:
            chunk = chunk[:end + 1]
        # Each row is ['val1','val2',...]
        for row_match in re.finditer(r'\[([^\[\]]+)\]', chunk):
            raw = row_match.group(1)
            # Split on commas but respect single-quoted tokens
            values = re.findall(r"'([^']*)'", raw)
            if values:
                rows.append(values)

    return {"columns": columns, "rows": rows}


def _parse_catalog_html(html: str) -> list[dict]:
    """
    Parse a spotcatalog_u2.php response into a list of product dicts.

    Returns:
        [
          {
            "model": str,
            "label": str,
            "description": str,
            "model_datetime": str,
            "url": str,
          }, ...
        ]
    """
    products: list[dict] = []
    # Find <tr> blocks containing grib_index links
    rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        links = re.findall(r'href="(products/grib_index\.php\?[^"]+)"[^>]*>([^<]+)<', row)
        if not links:
            continue
        href, text = links[0]
        # Parse query string
        params: dict[str, str] = {}
        qs = href.split("?", 1)[1] if "?" in href else ""
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
        # Second link is description, third is model datetime
        desc = links[1][1].strip() if len(links) > 1 else ""
        model_dt = links[2][1].strip() if len(links) > 2 else ""

        products.append({
            "model": params.get("model", ""),
            "label": text.strip(),
            "description": desc,
            "model_datetime": model_dt,
            "url": urljoin(BASE_URL + "/", href),
            "params": params,
        })
    return products


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class SpotWXClient:
    """
    Client for the SpotWX internal (undocumented) API.

    Basic usage::

        from spotwx_client import SpotWXClient, Models, TempUnits

        client = SpotWXClient()

        # List all available models at a point
        models = client.list_models(lat=49.25, lon=-123.1)
        for m in models:
            print(m["label"], m["description"])

        # Fetch GFS forecast as structured data
        data = client.get_forecast(
            model=Models.GFS,
            lat=49.25, lon=-123.1,
            tz="America/Vancouver",
        )
        for series in data["series"]:
            print(series["name"], series["data"][0])

        # Fetch tabular data (easier for CSV/pandas)
        tbl = client.get_forecast_table(
            model=Models.GFS,
            lat=49.25, lon=-123.1,
            tz="America/Vancouver",
        )
        import pandas as pd
        df = pd.DataFrame(tbl["rows"], columns=tbl["columns"])
    """

    def __init__(
        self,
        *,
        temp_units: str = TempUnits.CELSIUS,
        wind_units: str = WindUnits.KPH,
        precip_units: str = PrecipUnits.MM,
        pressure_units: str = PressureUnits.MB,
        alt_units: str = AltUnits.METERS,
        dist_units: str = DistUnits.KM,
        time_format: str = TimeFormat.T12,
        session: requests.Session | None = None,
        timeout: int = 30,
    ) -> None:
        """
        Create a SpotWX client.

        Parameters
        ----------
        temp_units : str
            Temperature units. One of TempUnits.* (default: Celsius).
        wind_units : str
            Wind speed units. One of WindUnits.* (default: kph).
        precip_units : str
            Precipitation units. One of PrecipUnits.* (default: mm).
        pressure_units : str
            Pressure units. One of PressureUnits.* (default: mb).
        alt_units : str
            Altitude units. One of AltUnits.* (default: m).
        dist_units : str
            Distance units. One of DistUnits.* (default: km).
        time_format : str
            12 or 24 hour time. One of TimeFormat.* (default: t12).
        session : requests.Session, optional
            Custom requests session (e.g. for proxying/caching).
        timeout : int
            Request timeout in seconds.
        """
        self._timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": BASE_URL + "/",
        })
        # Set unit cookies — SpotWX reads these server-side
        self._session.cookies.set("tmpunits",  temp_units,     domain="spotwx.com", path="/")
        self._session.cookies.set("windunits", wind_units,     domain="spotwx.com", path="/")
        self._session.cookies.set("pcpunits",  precip_units,   domain="spotwx.com", path="/")
        self._session.cookies.set("presunits", pressure_units, domain="spotwx.com", path="/")
        self._session.cookies.set("altunits",  alt_units,      domain="spotwx.com", path="/")
        self._session.cookies.set("distunits", dist_units,     domain="spotwx.com", path="/")
        self._session.cookies.set("timeunits", time_format,    domain="spotwx.com", path="/")

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> str:
        """Issue a GET request and return response text."""
        url = BASE_URL + "/" + path.lstrip("/")
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------------
    # Location / Catalog endpoints
    # ------------------------------------------------------------------

    def get_spot_info(self, lat: float, lon: float) -> dict:
        """
        Get timezone and location information for a coordinate.

        Parameters
        ----------
        lat : float
            Latitude in decimal degrees.
        lon : float
            Longitude in decimal degrees.

        Returns
        -------
        dict
            {
              "html": str,        # Raw HTML fragment
              "lat": float,
              "lon": float,
            }
        """
        html = self._get("products/spot_info2.php", {"lat": lat, "lon": lon})
        return {"html": html.strip(), "lat": lat, "lon": lon}

    def list_models(
        self,
        lat: float,
        lon: float,
        *,
        time_units: str = TimeFormat.T12,
    ) -> list[dict]:
        """
        List all available Numerical Weather Models at a coordinate.

        Parameters
        ----------
        lat, lon : float
            Coordinate (decimal degrees).
        time_units : str
            "t12" or "t24".

        Returns
        -------
        list[dict]
            Each item has keys: model, label, description, model_datetime, url, params.
        """
        html = self._get(
            "products/spotcatalog_u2.php",
            {"lat": lat, "lon": lon, "type": "nm", "timeunits": time_units},
        )
        return _parse_catalog_html(html)

    def list_station_forecasts(
        self,
        lat: float,
        lon: float,
        *,
        time_units: str = TimeFormat.T12,
    ) -> list[dict]:
        """
        List nearest station-based forecasts (SCRIBE, NOWCAST) within 150 km.

        Returns
        -------
        list[dict]
            Same structure as list_models().
        """
        html = self._get(
            "products/spotcatalog_u2.php",
            {"lat": lat, "lon": lon, "type": "point", "timeunits": time_units},
        )
        return _parse_catalog_html(html)

    def list_zone_forecasts(
        self,
        lat: float,
        lon: float,
        *,
        time_units: str = TimeFormat.T12,
    ) -> list[dict]:
        """
        List area / zone forecasts (Meteocode) for a coordinate.

        Returns
        -------
        list[dict]
            Same structure as list_models().
        """
        html = self._get(
            "products/spotcatalog_u2.php",
            {"lat": lat, "lon": lon, "type": "zone", "timeunits": time_units},
        )
        return _parse_catalog_html(html)

    def get_grid_polygons(self, lat: float, lon: float) -> list[dict]:
        """
        Return the NWP grid cell polygons that contain the given point.

        Each polygon can be used to draw the grid cell boundary on a map.
        The response format is colon-separated with fields:
            name >>> color >>> WKT_polygon >>> url >>> description

        Returns
        -------
        list[dict]
            [
              {
                "model": str,
                "color": str,
                "polygon_wkt": str,
                "url": str,
                "description": str,
              }, ...
            ]
        """
        html = self._get("products/grib_polys_u.php", {"lat": lat, "lon": lon})
        items: list[dict] = []
        for entry in html.split(":"):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(">>>")
            if len(parts) >= 3:
                items.append({
                    "model": parts[0].strip(),
                    "color": parts[1].strip() if len(parts) > 1 else "",
                    "polygon_wkt": parts[2].strip() if len(parts) > 2 else "",
                    "url": (BASE_URL + "/" + parts[3].strip().lstrip("/")) if len(parts) > 3 else "",
                    "description": parts[4].strip() if len(parts) > 4 else "",
                })
        return items

    def get_nearest_scribe_point(self, lat: float, lon: float) -> dict | None:
        """
        Find the nearest ECCC SCRIBE observation/forecast point.

        Returns
        -------
        dict or None
            {
              "name": str,
              "tcid": str,
              "lat": float,
              "lon": float,
              "elevation_m": float,
              "products": [{"description": str, "url": str}, ...]
            }
        """
        html = self._get("products/scribe_points_u.php", {"lat": lat, "lon": lon})
        if not html or html.strip() == "":
            return None
        parts = html.strip().split(":")
        if len(parts) < 5:
            return None
        name, tcid, slat, slon, selev = parts[:5]
        products = []
        for p in parts[5:]:
            if ">>>" in p:
                desc, href = p.split(">>>", 1)
                products.append({
                    "description": desc.strip(),
                    "url": BASE_URL + "/" + href.strip().lstrip("/"),
                })
        return {
            "name": name.strip(),
            "tcid": tcid.strip(),
            "lat": float(slat),
            "lon": float(slon),
            "elevation_m": float(selev),
            "products": products,
        }

    def get_nearest_nowcast_point(self, lat: float, lon: float) -> dict | None:
        """
        Find the nearest ECCC NOWCAST observation/forecast point.

        Returns
        -------
        dict or None
            Same structure as get_nearest_scribe_point().
        """
        html = self._get("products/nowcast_points_u.php", {"lat": lat, "lon": lon})
        if not html or html.strip() == "":
            return None
        parts = html.strip().split(":")
        if len(parts) < 5:
            return None
        name, tcid, slat, slon, selev = parts[:5]
        products = []
        for p in parts[5:]:
            if ">>>" in p:
                desc, href = p.split(">>>", 1)
                products.append({
                    "description": desc.strip(),
                    "url": BASE_URL + "/" + href.strip().lstrip("/"),
                })
        return {
            "name": name.strip(),
            "tcid": tcid.strip(),
            "lat": float(slat),
            "lon": float(slon),
            "elevation_m": float(selev),
            "products": products,
        }

    def get_meteocode_zone(
        self,
        lat: float,
        lon: float,
        *,
        range: str = "short",
    ) -> str | None:
        """
        Get the Meteocode zone identifier for a coordinate.

        Parameters
        ----------
        lat, lon : float
        range : str
            "short" (short-term) or "extended".

        Returns
        -------
        str or None
            Zone identifier string (e.g., "MetroVancouver-central...")
            or None if no zone found.
        """
        html = self._get(
            "products/mc_zone_u2.php",
            {"lat": lat, "lon": lon, "range": range},
        )
        result = html.strip()
        return result if result and result.lower() != "na" else None

    # ------------------------------------------------------------------
    # Forecast data endpoints
    # ------------------------------------------------------------------

    def get_forecast(
        self,
        model: str,
        lat: float,
        lon: float,
        *,
        tz: str = "UTC",
        label: str = "",
        tcid: str | None = None,
        station: str | None = None,
        zone: str | None = None,
        title: str | None = None,
    ) -> dict:
        """
        Fetch the chart-based forecast for a model at a given coordinate.

        The data is parsed from Highcharts JavaScript embedded in the HTML.

        Parameters
        ----------
        model : str
            Model identifier. See Models.* constants or list_models() output.
        lat : float
            Latitude (used for gridded models).
        lon : float
            Longitude (used for gridded models).
        tz : str
            IANA timezone string (e.g., "America/Vancouver") or UTC offset
            (e.g., "-7"). Controls the local-time axis labels.
        label : str, optional
            Custom label for the forecast location.
        tcid : str, optional
            Station ID for SCRIBE/NOWCAST models (e.g., "YVR", "WHC").
        station : str, optional
            Station name for SCRIBE models.
        zone : str, optional
            Zone identifier for Meteocode models.
        title : str, optional
            Title/product code for Meteocode models.

        Returns
        -------
        dict
            {
              "model": str,
              "lat": float,
              "lon": float,
              "tz": str,
              "model_date": str,     # as found in page subtitle
              "model_elevation": str,
              "series": [
                {
                  "name": str,
                  "data": [
                    {
                      "datetime": datetime,   # UTC
                      "value": float,
                      "desc": str (optional)
                    }, ...
                  ]
                }, ...
              ],
              "html": str,           # raw HTML for further parsing
            }
        """
        params: dict[str, Any] = {
            "model": model,
            "lat": lat,
            "lon": lon,
            "tz": tz,
            "label": label,
        }
        if tcid is not None:
            params["tcid"] = tcid
        if station is not None:
            params["station"] = station
        if zone is not None:
            params["zone"] = zone
        if title is not None:
            params["title"] = title

        html = self._get("products/grib_index.php", params)

        series = _parse_highcharts_series(html)

        # Extract model run date and elevation from the subtitle
        model_date = ""
        model_elevation = ""
        land_proportion = ""
        subtitle_match = re.search(
            r'text:\s*[\'"]Model date: <b>([^<]+)</b>[^,]*,\s*Model elevation: <b>([^<]+)</b>[^,]*,\s*Land Proportion: <b>([^\'\"]+)',
            html,
        )
        if subtitle_match:
            model_date = subtitle_match.group(1).strip()
            model_elevation = subtitle_match.group(2).strip()
            land_proportion = subtitle_match.group(3).strip()

        return {
            "model": model,
            "lat": lat,
            "lon": lon,
            "tz": tz,
            "model_date": model_date,
            "model_elevation": model_elevation,
            "land_proportion": land_proportion,
            "series": series,
            "html": html,
        }

    def get_forecast_table(
        self,
        model: str,
        lat: float,
        lon: float,
        *,
        tz: str = "UTC",
        label: str = "",
        tcid: str | None = None,
        station: str | None = None,
        zone: str | None = None,
        title: str | None = None,
    ) -> dict:
        """
        Fetch the tabular forecast for a model at a given coordinate.

        The tabular view provides structured data as a JavaScript array
        (`aDataSet`) which is easier to convert to pandas DataFrames.

        Parameters
        ----------
        (Same as get_forecast())

        Returns
        -------
        dict
            {
              "model": str,
              "lat": float,
              "lon": float,
              "tz": str,
              "columns": [str, ...],
              "rows": [[str, ...], ...],
            }

        Column meanings (typical GFS/HRDPS/RDPS/NAM):
            DATETIME   - ISO-like local datetime string
            DATE       - Local date
            TIME       - Local time
            TMP        - 2m temperature (units per cookie)
            DPT        - Dewpoint temperature (some models)
            RH         - Relative humidity (%)
            WS         - 10m wind speed
            WD         - 10m wind direction (degrees true)
            WG         - Wind gusts
            APCP       - Accumulated precipitation (cumulative)
            CLOUD      - Cloud cover (%)
            SLP        - Sea-level pressure
            PTYPE      - Precipitation type (RA=rain, SN=snow, ZR=freezing rain, IP=ice pellets)
            RQP        - Rain quantity (cumulative)
            SQP        - Snow quantity (cumulative)
            FQP        - Freezing rain quantity (cumulative)
            IQP        - Ice pellet quantity (cumulative)
            WS925      - 925 hPa wind speed
            WD925      - 925 hPa wind direction
            TMP850     - 850 hPa temperature
            WS850      - 850 hPa wind speed
            WD850      - 850 hPa wind direction
            4LFTX      - Best 4-layer Lifted Index
            HGT_0C_DB  - Height of 0C dry bulb level
            TMP_SFC    - Surface temperature
            DSWRF      - Downward shortwave radiation (W/m2)
            USWRF      - Upward shortwave radiation (W/m2)
            DLWRF      - Downward longwave radiation (W/m2)
            ULWRF      - Upward longwave radiation (W/m2)
        """
        params: dict[str, Any] = {
            "model": model,
            "lat": lat,
            "lon": lon,
            "tz": tz,
            "label": label,
            "display": "table",
        }
        if tcid is not None:
            params["tcid"] = tcid
        if station is not None:
            params["station"] = station
        if zone is not None:
            params["zone"] = zone
        if title is not None:
            params["title"] = title

        html = self._get("products/grib_index.php", params)
        table = _parse_tabular_data(html)

        return {
            "model": model,
            "lat": lat,
            "lon": lon,
            "tz": tz,
            **table,
        }

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def get_all_available_forecasts(
        self,
        lat: float,
        lon: float,
        *,
        tz: str = "UTC",
        include_station: bool = True,
        include_zone: bool = True,
    ) -> dict:
        """
        Discover all available products at a location and fetch them all.

        This calls list_models(), list_station_forecasts(), list_zone_forecasts()
        then fetches the tabular data for each discovered model.

        Parameters
        ----------
        lat, lon : float
        tz : str
            IANA timezone.
        include_station : bool
            If True, also fetch station-based forecasts (SCRIBE, NOWCAST).
        include_zone : bool
            If True, also fetch Meteocode zone forecasts.

        Returns
        -------
        dict
            {
              "lat": float,
              "lon": float,
              "spot_info": dict,
              "numerical_models": [<forecast_table>, ...],
              "station_forecasts": [<forecast_table>, ...],
              "zone_forecasts": [<forecast_table>, ...],
            }
        """
        spot_info = self.get_spot_info(lat, lon)
        nm_catalog = self.list_models(lat, lon)

        numerical = []
        seen_nm = set()
        for product in nm_catalog:
            model_id = product["model"]
            if model_id in seen_nm:
                continue
            seen_nm.add(model_id)
            try:
                tbl = self.get_forecast_table(
                    model=model_id,
                    lat=lat,
                    lon=lon,
                    tz=tz,
                )
                tbl["label"] = product["label"]
                tbl["description"] = product["description"]
                numerical.append(tbl)
            except Exception as exc:
                numerical.append({
                    "model": model_id,
                    "label": product["label"],
                    "error": str(exc),
                })

        station_results = []
        if include_station:
            stn_catalog = self.list_station_forecasts(lat, lon)
            seen_stn = set()
            for product in stn_catalog:
                key = (product["model"], product["params"].get("tcid", ""))
                if key in seen_stn:
                    continue
                seen_stn.add(key)
                try:
                    tbl = self.get_forecast_table(
                        model=product["model"],
                        lat=lat,
                        lon=lon,
                        tz=tz,
                        tcid=product["params"].get("tcid"),
                        station=product["params"].get("station"),
                    )
                    tbl["label"] = product["label"]
                    tbl["description"] = product["description"]
                    station_results.append(tbl)
                except Exception as exc:
                    station_results.append({
                        "model": product["model"],
                        "label": product["label"],
                        "error": str(exc),
                    })

        zone_results = []
        if include_zone:
            zone_catalog = self.list_zone_forecasts(lat, lon)
            seen_zone = set()
            for product in zone_catalog:
                key = (product["model"], product["params"].get("zone", ""))
                if key in seen_zone:
                    continue
                seen_zone.add(key)
                try:
                    tbl = self.get_forecast_table(
                        model=product["model"],
                        lat=lat,
                        lon=lon,
                        tz=tz,
                        zone=product["params"].get("zone"),
                        title=product["params"].get("title"),
                    )
                    tbl["label"] = product["label"]
                    tbl["description"] = product["description"]
                    zone_results.append(tbl)
                except Exception as exc:
                    zone_results.append({
                        "model": product["model"],
                        "label": product["label"],
                        "error": str(exc),
                    })

        return {
            "lat": lat,
            "lon": lon,
            "spot_info": spot_info,
            "numerical_models": numerical,
            "station_forecasts": station_results,
            "zone_forecasts": zone_results,
        }

    def get_multi_model_comparison(
        self,
        lat: float,
        lon: float,
        *,
        tz: str = "UTC",
        models: list[str] | None = None,
    ) -> dict:
        """
        Fetch the same forecast variable from multiple models for comparison.

        Parameters
        ----------
        lat, lon : float
        tz : str
        models : list[str], optional
            List of model IDs. Defaults to all gridded models available.

        Returns
        -------
        dict
            {
              "lat": float,
              "lon": float,
              "models": {
                model_id: {
                  "series": [...],
                  "model_date": str,
                  "model_elevation": str,
                }, ...
              }
            }
        """
        if models is None:
            # Discover available models at this location
            catalog = self.list_models(lat, lon)
            models = list({p["model"] for p in catalog})

        results: dict[str, Any] = {}
        for model_id in models:
            try:
                fcst = self.get_forecast(model=model_id, lat=lat, lon=lon, tz=tz)
                results[model_id] = {
                    "series": fcst["series"],
                    "model_date": fcst["model_date"],
                    "model_elevation": fcst["model_elevation"],
                }
            except Exception as exc:
                results[model_id] = {"error": str(exc)}

        return {
            "lat": lat,
            "lon": lon,
            "models": results,
        }

    def get_scribe_forecast(
        self,
        tcid: str,
        *,
        tz: str = "UTC",
        model: str = Models.SCRIBE_REGIONAL,
        station: str = "",
    ) -> dict:
        """
        Fetch a SCRIBE station-based forecast.

        Parameters
        ----------
        tcid : str
            ECCC station ID (e.g., "WHC", "YVR", "YYC").
        tz : str
            IANA timezone or UTC offset integer.
        model : str
            One of: Models.SCRIBE_REGIONAL, Models.SCRIBE_GLOBAL,
            Models.SCRIBE_EXTENDED, Models.SCRIBE_HYBRID.
        station : str, optional
            Human-readable station name.

        Returns
        -------
        dict
            Same as get_forecast().
        """
        return self.get_forecast(
            model=model,
            lat=0.0,
            lon=0.0,
            tz=tz,
            tcid=tcid,
            station=station,
        )

    def get_nowcast_forecast(
        self,
        tcid: str,
        *,
        tz: str = "UTC",
        station: str = "",
    ) -> dict:
        """
        Fetch a SCRIBE NOWCAST (12-hour) station forecast.

        Parameters
        ----------
        tcid : str
            ECCC station ID (e.g., "YVR").
        tz : str
            IANA timezone or UTC offset integer.
        station : str, optional
            Human-readable station name.

        Returns
        -------
        dict
            Same as get_forecast().
        """
        return self.get_forecast(
            model=Models.NOWCAST,
            lat=0.0,
            lon=0.0,
            tz=tz,
            tcid=tcid,
            station=station,
        )

    def get_meteocode_forecast(
        self,
        lat: float,
        lon: float,
        *,
        tz: str = "UTC",
        range: str = "short",
    ) -> dict | None:
        """
        Fetch the Meteocode zone forecast for a coordinate.

        Parameters
        ----------
        lat, lon : float
        tz : str
        range : str
            "short" or "extended".

        Returns
        -------
        dict or None
            Forecast dict (same as get_forecast()) or None if no zone found.
        """
        # First discover the zone and product title
        zone_catalog = self.list_zone_forecasts(lat, lon)
        if not zone_catalog:
            return None

        # Pick short vs extended
        for product in zone_catalog:
            label = product["label"].lower()
            is_extended = "extended" in label
            if range == "extended" and is_extended:
                target = product
                break
            elif range == "short" and not is_extended:
                target = product
                break
        else:
            target = zone_catalog[0]

        return self.get_forecast(
            model=target["model"],
            lat=lat,
            lon=lon,
            tz=tz,
            zone=target["params"].get("zone"),
            title=target["params"].get("title"),
        )

    def series_to_dict(self, series_list: list[dict]) -> dict[str, list]:
        """
        Convert a list of series dicts (from get_forecast) into a flat dict
        keyed by series name, with datetime and value lists.

        Useful for building a pandas DataFrame::

            client = SpotWXClient()
            fcst = client.get_forecast(Models.GFS, lat=49.25, lon=-123.1, tz="America/Vancouver")
            flat = client.series_to_dict(fcst["series"])
            import pandas as pd
            df = pd.DataFrame(flat)

        Returns
        -------
        dict
            {
              "datetime": [datetime, ...],
              "Series Name 1": [float, ...],
              "Series Name 2": [float, ...],
              ...
            }
        """
        if not series_list:
            return {}
        # Use timestamps from first series as the time axis
        result: dict[str, list] = {
            "datetime": [pt["datetime"] for pt in series_list[0]["data"]]
        }
        for series in series_list:
            values = [pt["value"] for pt in series["data"]]
            name = series["name"]
            # Handle duplicate names
            if name in result:
                i = 1
                while f"{name}_{i}" in result:
                    i += 1
                name = f"{name}_{i}"
            result[name] = values
        return result


# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse
    import csv
    import io
    import sys

    parser = argparse.ArgumentParser(
        description="SpotWX API client — fetch weather forecast data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Key Endpoints")[0].strip(),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- list-models --------------------------------------------------------
    p_list = sub.add_parser("list-models", help="List available models at a location")
    p_list.add_argument("lat", type=float)
    p_list.add_argument("lon", type=float)

    # --- info ---------------------------------------------------------------
    p_info = sub.add_parser("info", help="Get location/timezone info")
    p_info.add_argument("lat", type=float)
    p_info.add_argument("lon", type=float)

    # --- forecast -----------------------------------------------------------
    p_fcst = sub.add_parser("forecast", help="Fetch model forecast as CSV")
    p_fcst.add_argument("model", help="Model ID (e.g. gfs_pgrb2_0p25_f)")
    p_fcst.add_argument("lat", type=float)
    p_fcst.add_argument("lon", type=float)
    p_fcst.add_argument("--tz", default="UTC", help="Timezone (e.g. America/Vancouver)")
    p_fcst.add_argument("--tcid", default=None, help="Station ID for SCRIBE/NOWCAST")
    p_fcst.add_argument("--units-temp", default="C", choices=["C", "F", "K"])
    p_fcst.add_argument("--units-wind", default="kph", choices=["kph", "mph", "kn", "ms"])
    p_fcst.add_argument("--units-precip", default="mm", choices=["mm", "in", "kg"])

    # --- series -------------------------------------------------------------
    p_series = sub.add_parser("series", help="Fetch model forecast as named series JSON")
    p_series.add_argument("model", help="Model ID")
    p_series.add_argument("lat", type=float)
    p_series.add_argument("lon", type=float)
    p_series.add_argument("--tz", default="UTC")
    p_series.add_argument("--tcid", default=None)
    p_series.add_argument("--units-temp", default="C", choices=["C", "F", "K"])
    p_series.add_argument("--units-wind", default="kph", choices=["kph", "mph", "kn", "ms"])

    args = parser.parse_args()

    if args.command == "info":
        client = SpotWXClient()
        info = client.get_spot_info(args.lat, args.lon)
        print(info["html"])

    elif args.command == "list-models":
        client = SpotWXClient()
        models = client.list_models(args.lat, args.lon)
        print(f"{'Model ID':<30} {'Label':<30} {'Description'}")
        print("-" * 90)
        for m in models:
            print(f"{m['model']:<30} {m['label']:<30} {m['description']}")

    elif args.command == "forecast":
        client = SpotWXClient(
            temp_units=args.units_temp,
            wind_units=args.units_wind,
            precip_units=args.units_precip,
        )
        tbl = client.get_forecast_table(
            model=args.model,
            lat=args.lat,
            lon=args.lon,
            tz=args.tz,
            tcid=args.tcid,
        )
        writer = csv.writer(sys.stdout)
        writer.writerow(tbl["columns"])
        writer.writerows(tbl["rows"])

    elif args.command == "series":
        client = SpotWXClient(
            temp_units=args.units_temp,
            wind_units=args.units_wind,
        )
        fcst = client.get_forecast(
            model=args.model,
            lat=args.lat,
            lon=args.lon,
            tz=args.tz,
            tcid=args.tcid,
        )
        out = {
            "model": fcst["model"],
            "model_date": fcst["model_date"],
            "model_elevation": fcst["model_elevation"],
            "series": [
                {
                    "name": s["name"],
                    "data": [
                        {
                            "datetime": pt["datetime"].isoformat(),
                            "value": pt["value"],
                            **({"desc": pt["desc"]} if "desc" in pt else {}),
                        }
                        for pt in s["data"]
                    ],
                }
                for s in fcst["series"]
            ],
        }
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    _cli()
