"""
AerisWeather / Xweather API Python Client

Reverse-engineered from the Xweather public documentation at:
  https://www.xweather.com/docs/weather-api

Base API URL: https://data.api.xweather.com/
Authentication: client_id + client_secret query parameters (OAuth2-style)

All endpoints follow the pattern:
  GET https://data.api.xweather.com/{endpoint}/{action}?client_id={id}&client_secret={secret}&{params}

Discovered 55 endpoints covering:
  - Weather observations, forecasts, conditions, alerts
  - Severe weather: storm cells, storm reports, lightning, hail, convective outlook
  - Atmospheric hazards: fires, fire outlook, earthquakes, tropical cyclones
  - Specialty data: air quality, maritime, tides, normals, rivers, sun/moon
  - Business intelligence: indices, impacts, road weather, energy farm
  - Geographic lookups: places, countries, airports, postal codes
"""

import requests
import urllib.parse
from typing import Optional, Union, List, Dict, Any


BASE_URL = "https://data.api.xweather.com"


class AerisError(Exception):
    """Raised when the AerisWeather API returns an error response."""
    def __init__(self, code: str, description: str):
        self.code = code
        self.description = description
        super().__init__(f"AerisAPI Error [{code}]: {description}")


class AerisWarning(UserWarning):
    """Issued when the API returns a warning."""
    pass


class AerisClient:
    """
    Python client for the AerisWeather (Xweather) Data API.

    Authentication
    --------------
    Every request requires a client_id and client_secret obtained by
    registering an application at https://www.xweather.com/account

    Usage
    -----
    >>> client = AerisClient(client_id="YOUR_ID", client_secret="YOUR_SECRET")
    >>> resp = client.observations.id("seattle,wa")
    >>> print(resp["response"]["ob"]["tempF"])

    The API key namespace must match the domain or bundle ID the credentials
    were registered under.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = BASE_URL,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": "AerisWeather-Python-Client/1.0"})

        # Attach endpoint namespaces
        self.observations = _ObservationsEndpoint(self)
        self.observations_archive = _ObservationsArchiveEndpoint(self)
        self.observations_summary = _ObservationsSummaryEndpoint(self)
        self.forecasts = _ForecastsEndpoint(self)
        self.conditions = _ConditionsEndpoint(self)
        self.conditions_summary = _ConditionsSummaryEndpoint(self)
        self.alerts = _AlertsEndpoint(self)
        self.alerts_summary = _AlertsSummaryEndpoint(self)
        self.airquality = _AirQualityEndpoint(self)
        self.airquality_forecasts = _AirQualityForecastsEndpoint(self)
        self.airquality_archive = _AirQualityArchiveEndpoint(self)
        self.airquality_index = _AirQualityIndexEndpoint(self)
        self.stormcells = _StormCellsEndpoint(self)
        self.stormcells_summary = _StormCellsSummaryEndpoint(self)
        self.stormreports = _StormReportsEndpoint(self)
        self.stormreports_summary = _StormReportsSummaryEndpoint(self)
        self.lightning = _LightningEndpoint(self)
        self.lightning_summary = _LightningSummaryEndpoint(self)
        self.lightning_archive = _LightningArchiveEndpoint(self)
        self.lightning_analytics = _LightningAnalyticsEndpoint(self)
        self.lightning_threats = _LightningThreatsEndpoint(self)
        self.lightning_flash = _LightningFlashEndpoint(self)
        self.hail_archive = _HailArchiveEndpoint(self)
        self.hail_threats = _HailThreatsEndpoint(self)
        self.fires = _FiresEndpoint(self)
        self.fires_outlook = _FiresOutlookEndpoint(self)
        self.earthquakes = _EarthquakesEndpoint(self)
        self.tropicalcyclones = _TropicalCyclonesEndpoint(self)
        self.tropicalcyclones_archive = _TropicalCyclonesArchiveEndpoint(self)
        self.convective_outlook = _ConvectiveOutlookEndpoint(self)
        self.droughts_monitor = _DroughtsMonitorEndpoint(self)
        self.tides = _TidesEndpoint(self)
        self.tides_stations = _TidesStationsEndpoint(self)
        self.maritime = _MaritimeEndpoint(self)
        self.maritime_archive = _MaritimeArchiveEndpoint(self)
        self.normals = _NormalsEndpoint(self)
        self.normals_stations = _NormalsStationsEndpoint(self)
        self.rivers = _RiversEndpoint(self)
        self.rivers_gauges = _RiversGaugesEndpoint(self)
        self.sunmoon = _SunMoonEndpoint(self)
        self.moonphases = _MoonPhasesEndpoint(self)
        self.places = _PlacesEndpoint(self)
        self.places_airports = _PlacesAirportsEndpoint(self)
        self.places_postalcodes = _PlacesPostalCodesEndpoint(self)
        self.countries = _CountriesEndpoint(self)
        self.indices = _IndicesEndpoint(self)
        self.impacts = _ImpactsEndpoint(self)
        self.roadweather = _RoadWeatherEndpoint(self)
        self.roadweather_conditions = _RoadWeatherConditionsEndpoint(self)
        self.roadweather_analytics = _RoadWeatherAnalyticsEndpoint(self)
        self.threats = _ThreatsEndpoint(self)
        self.phrases_summary = _PhrasesSummaryEndpoint(self)
        self.xcast_forecasts = _XcastForecastsEndpoint(self)
        self.energy_farm = _EnergyFarmEndpoint(self)
        self.renewables_irradiance = _RenewablesIrradianceArchiveEndpoint(self)

    def _build_params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        """Merge auth credentials into parameter dict, removing None values."""
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        for k, v in extra.items():
            if v is not None:
                if isinstance(v, list):
                    params[k] = ",".join(str(i) for i in v)
                else:
                    params[k] = v
        return params

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a GET request against the API.

        Raises AerisError on API-level errors.
        Returns the full parsed JSON response dict.
        """
        url = f"{self.base_url}{path}"
        merged = self._build_params(params)
        response = self._session.get(url, params=merged, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            err = data.get("error") or {}
            raise AerisError(
                code=err.get("code", "unknown"),
                description=err.get("description", "An unknown error occurred."),
            )

        if data.get("warning"):
            import warnings
            warn = data["warning"]
            warnings.warn(
                f"AerisAPI Warning [{warn.get('code', '?')}]: {warn.get('description', '')}",
                AerisWarning,
                stacklevel=3,
            )

        return data

    def batch(
        self,
        requests_param: List[str],
        place: Optional[str] = None,
        limit: Optional[int] = None,
        query: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute a batch request combining multiple endpoint queries.

        The batch endpoint allows up to 31 individual endpoint requests in
        a single API call. Each sub-request counts as a separate API access.

        Parameters
        ----------
        requests_param : list of str
            Each element is a sub-request path string, e.g.
            ["/observations", "/forecasts", "/alerts%3Ffilter=all"]
        place : str, optional
            A location identifier applied globally if sub-requests use :id
            action, e.g. "minneapolis,mn" or "44.9778,-93.2650"
        limit : int, optional
            Global limit applied to each sub-request (can be overridden
            per sub-request via inline params).
        query : str, optional
            Global query filter applied to each sub-request.

        Example
        -------
        >>> data = client.batch(
        ...     requests_param=["/observations", "/forecasts", "/alerts"],
        ...     place="minneapolis,mn"
        ... )
        """
        path = f"/batch/{place}" if place else "/batch"
        params = {
            "requests": ",".join(requests_param),
            "limit": limit,
            "query": query,
        }
        params.update(kwargs)
        return self._get(path, params)


# ---------------------------------------------------------------------------
# Base endpoint class
# ---------------------------------------------------------------------------

class _Endpoint:
    """Base class for all AerisWeather API endpoint wrappers."""

    #: The API path prefix, e.g. "/observations" or "/airquality/forecasts"
    ROUTE: str = ""

    def __init__(self, client: AerisClient):
        self._client = client

    def _request(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        path = f"{self.ROUTE}/{action}".rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return self._client._get(path, params)

    def id(self, place: str, **params) -> Dict[str, Any]:
        """
        Fetch data for a specific location identifier.

        Parameters
        ----------
        place : str
            City name, lat/lon ("44.97,-93.26"), postal code, station ID,
            or ICAO code.
        **params : dict
            Additional query parameters (filter, limit, fields, from, to, etc.)
        """
        return self._request(place, params)

    def closest(
        self,
        place: str,
        radius: Optional[str] = None,
        limit: Optional[int] = None,
        **params,
    ) -> Dict[str, Any]:
        """
        Find results nearest to a given location, ordered closest-first.

        Parameters
        ----------
        place : str
            Center point (city, lat/lon, postal code).
        radius : str, optional
            Search radius with unit, e.g. "50miles" or "100km".
        limit : int, optional
            Maximum number of results to return.
        """
        if place:
            params["p"] = place
        if radius:
            params["radius"] = radius
        if limit:
            params["limit"] = limit
        return self._request("closest", params)

    def within(
        self,
        place: str,
        radius: Optional[str] = None,
        limit: Optional[int] = None,
        **params,
    ) -> Dict[str, Any]:
        """
        Find all results within a circle or polygon.

        Parameters
        ----------
        place : str
            Center of the search circle (city, lat/lon, postal code).
            For polygons pass a semicolon-delimited list of lat/lon pairs.
        radius : str, optional
            Search radius with unit, e.g. "25miles" or "50km".
        limit : int, optional
            Maximum number of results.
        """
        if place:
            params["p"] = place
        if radius:
            params["radius"] = radius
        if limit:
            params["limit"] = limit
        return self._request("within", params)

    def search(
        self,
        query: Optional[str] = None,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
        **params,
    ) -> Dict[str, Any]:
        """
        Search across the full data set using query expressions.

        Parameters
        ----------
        query : str, optional
            Filter expression, e.g. "state:mn,temp:-999"
        limit : int, optional
            Maximum number of results.
        sort : str, optional
            Sort expression, e.g. "temp:-1" (descending) or "temp" (ascending).
        """
        if query:
            params["query"] = query
        if limit:
            params["limit"] = limit
        if sort:
            params["sort"] = sort
        return self._request("search", params)

    def route(
        self,
        places: Union[str, List[str]],
        **params,
    ) -> Dict[str, Any]:
        """
        Retrieve data along a custom route of coordinate waypoints.

        Parameters
        ----------
        places : str or list of str
            A single string with semicolon-delimited lat/lon pairs, or a
            list of "lat,lon" strings.
        """
        if isinstance(places, list):
            params["p"] = ";".join(places)
        else:
            params["p"] = places
        return self._request("route", params)


# ---------------------------------------------------------------------------
# Concrete endpoint implementations
# ---------------------------------------------------------------------------

class _ObservationsEndpoint(_Endpoint):
    """
    Current surface weather observations from METAR, PWS, MADIS, and
    international networks.

    Route:  /observations/{action}
    Update: 1–60+ minutes (varies by station)

    Supported actions: :id, closest, within, search, route
    Supported filters: metar (default), allstations, pws, madis, hfmetar,
                       ausbom, envca, allownosky, wxrain, wxsnow, wxice,
                       wxfog, qcok, strict, centroid, precise
    Sortable fields:  temp, dewpt, rh, pressure, wind, winddir, gust,
                      name, state, country, id, datasource, trustfactor, dt
    """
    ROUTE = "/observations"

    def recent(
        self,
        place: str,
        plimit: int = 1,
        filter: Optional[str] = None,
        **params,
    ) -> Dict[str, Any]:
        """Fetch the most recent N observations for a station/location."""
        if plimit:
            params["plimit"] = plimit
        if filter:
            params["filter"] = filter
        return self._request(place, params)


class _ObservationsArchiveEndpoint(_Endpoint):
    """
    Historical observation data.

    Route:  /observations/archive/{action}
    Supported actions: :id, closest, within
    Supported filters: allstations, official, pws, mesonet, hasprecip,
                       hassky, centroid, precise
    """
    ROUTE = "/observations/archive"


class _ObservationsSummaryEndpoint(_Endpoint):
    """
    Summarised observation data over a time range.

    Route:  /observations/summary/{action}
    Supported actions: :id, closest, within
    Supported filters: allstations, official, metar, pws, mesonet, hfmetar,
                       hasprecip, hassky, qcok, strict, centroid, precise
    """
    ROUTE = "/observations/summary"


class _ForecastsEndpoint(_Endpoint):
    """
    Up to 15-day forecasts for US and international locations.

    Route:  /forecasts/{action}
    Update: 1 hour
    Supported actions: :id, route
    Supported filters:
      day         – daily (7am-7pm), default 7 days
      daynight    – 12-hour day/night periods
      mdnt2mdnt   – midnight-to-midnight
      #hr         – hourly interval, e.g. filter=1hr, filter=3hr
      #min        – sub-hourly interval, e.g. filter=30min
      precise     – additional decimal precision
      centroid    – use zip centroid for postal code queries
    Key params: p, limit, filter, from, to, skip, plimit, pskip, fields
    """
    ROUTE = "/forecasts"

    def daily(self, place: str, days: int = 7, **params) -> Dict[str, Any]:
        """Convenience: fetch N-day daily forecast."""
        return self.id(place, filter="day", limit=days, **params)

    def hourly(self, place: str, hours: int = 24, **params) -> Dict[str, Any]:
        """Convenience: fetch N-hour hourly forecast."""
        return self.id(place, filter="1hr", limit=hours, **params)

    def daynight(self, place: str, days: int = 7, **params) -> Dict[str, Any]:
        """Convenience: fetch day/night forecast periods."""
        limit = days * 2
        return self.id(place, filter="daynight", limit=limit, **params)


class _ConditionsEndpoint(_Endpoint):
    """
    Interpolated global current, historical and forecast conditions.
    Also supports minutely precipitation forecast (up to 60 min).

    Route:  /conditions/{action}
    Update: Near real-time
    Supported actions: :id, route
    Supported filters: minutelyprecip, 15min, 1hr (hourly increments)
    Key params: p, for, plimit, psort, pskip, filter, from, to, fields
    """
    ROUTE = "/conditions"

    def minutely(self, place: str, minutes: int = 60, **params) -> Dict[str, Any]:
        """Convenience: fetch minutely precipitation forecast."""
        return self.id(place, filter="minutelyprecip", plimit=minutes, **params)

    def historical(
        self,
        place: str,
        from_dt: str,
        to_dt: Optional[str] = None,
        **params,
    ) -> Dict[str, Any]:
        """Convenience: fetch historical conditions for a date range."""
        params["from"] = from_dt
        if to_dt:
            params["to"] = to_dt
        return self.id(place, **params)


class _ConditionsSummaryEndpoint(_Endpoint):
    """
    Summarised conditions over a period.

    Route:  /conditions/summary/{action}
    Supported actions: :id, route
    Supported filters: day, #hr
    """
    ROUTE = "/conditions/summary"


class _AlertsEndpoint(_Endpoint):
    """
    Active weather alerts: NWS (US), Environment Canada, and European alerts.

    Route:  /alerts/{action}
    Update: Near real-time
    Default limit: 10 (to capture all alerts for one location)
    Supported actions: :id, route
    Supported filters:
      standard  – default combination of warning/watch/advisory
      warning   – warnings only
      watch     – watches only
      advisory  – advisories only
      outlook   – outlook statements only
      statement – all statements
      severe    – severe thunderstorm/tornado alerts
      flood     – flood-type alerts
      tropical  – tropical storm/hurricane alerts
      winter    – winter weather alerts
      fire      – fire weather alerts
      marine    – marine/coastal alerts
      geo       – include GeoJSON polygon for the alert area
      all       – all active alerts regardless of type
    Key params: p, limit, filter, query, sort, fields, lang, format
    Queryable fields: type, loc, sig, sigp, name
    """
    ROUTE = "/alerts"

    def active(
        self,
        place: str,
        filter: Optional[str] = "all",
        limit: int = 10,
        **params,
    ) -> Dict[str, Any]:
        """Convenience: all active alerts for a location."""
        return self.id(place, filter=filter, limit=limit, **params)


class _AlertsSummaryEndpoint(_Endpoint):
    """
    Summarised alert counts for a region.

    Route:  /alerts/summary/{action}
    Supported actions: :id, search, within
    Supported filters: warning, watch, advisory, outlook, statement,
                       severe, flood, tropical, winter, marine, fire
    """
    ROUTE = "/alerts/summary"


class _AirQualityEndpoint(_Endpoint):
    """
    Current air quality: AQI, category, dominant pollutant, AQHI.

    Route:  /airquality/{action}
    Update: 1 hour
    Supported actions: :id, route
    Supported filters:
      airnow   – US EPA AirNow standard (default for US locations)
      cai      – Canadian AQI
      caqi     – European Common AQI
      china    – China AQI standard
      eaqi     – European EAQI
      germany  – German UBA standard
      india    – India CPCB standard
      uk       – UK DAQI standard
    Key params: p, filter, fields, format, plimit, pskip, psort
    """
    ROUTE = "/airquality"


class _AirQualityForecastsEndpoint(_Endpoint):
    """
    Air quality forecasts.

    Route:  /airquality/forecasts/{action}
    Supported actions: :id, route
    Supported filters: day, daynight, #hr, airnow, cai, caqi, china,
                       eaqi, germany, india, uk
    """
    ROUTE = "/airquality/forecasts"


class _AirQualityArchiveEndpoint(_Endpoint):
    """
    Historical air quality data.

    Route:  /airquality/archive/{action}
    Supported actions: :id, route
    Supported filters: #hr, airnow, cai, caqi, china, eaqi, germany, india, uk
    """
    ROUTE = "/airquality/archive"


class _AirQualityIndexEndpoint(_Endpoint):
    """
    Air quality index values.

    Route:  /airquality/index/{action}
    Supported actions: :id, route
    """
    ROUTE = "/airquality/index"


class _StormCellsEndpoint(_Endpoint):
    """
    NEXRAD-derived storm cell data: position, movement, severity, rotation.

    Route:  /stormcells/{action}
    Coverage: Continental US only
    Supported actions: :id, closest, within, search, affects
    Supported filters:
      hail        – cells with hail signature
      rotating    – cells with rotation signature (meso)
      tornado     – cells with tornado vortex signature (TVS)
      threat      – cells considered a threat
      rainmoderate, rainheavy, rainintense – rain rate filters
      conus       – continental US only
    Queryable: hail, tvs, mda, posh, top, base, dbz, type
    """
    ROUTE = "/stormcells"

    def affects(self, place: str, radius: Optional[str] = None, **params) -> Dict[str, Any]:
        """Find storm cells currently affecting a location."""
        if place:
            params["p"] = place
        if radius:
            params["radius"] = radius
        return self._request("affects", params)


class _StormCellsSummaryEndpoint(_Endpoint):
    """
    Summary of storm cells in a region.

    Route:  /stormcells/summary/{action}
    Supported actions: :id, affects, search, within
    Supported filters: hail, rotating, tornado, threat, rainmoderate,
                       rainheavy, rainintense, conus, geo, noforecast
    """
    ROUTE = "/stormcells/summary"


class _StormReportsEndpoint(_Endpoint):
    """
    Storm damage/occurrence reports from NWS LSRs and spotter networks.

    Route:  /stormreports/{action}
    Update: 15 minutes
    Supported actions: :id, closest, within, search
    Supported filters (report types):
      avalanche, blizzard, dust, flood, fog, ice, hail, lightning,
      marine, rain, snow, tornado, wind, winter, wx
    Queryable: code, type, state, name, detail
    Sortable: dt, state, type
    """
    ROUTE = "/stormreports"


class _StormReportsSummaryEndpoint(_Endpoint):
    """
    Summary of storm reports for a region and time window.

    Route:  /stormreports/summary/{action}
    Supported actions: :id, within, search
    Supported filters: same as stormreports
    """
    ROUTE = "/stormreports/summary"


class _LightningEndpoint(_Endpoint):
    """
    Near real-time Vaisala global lightning strike data (last 5 minutes).

    Standard access: up to 1000 strikes per query, 5-minute window.
    Advanced access: up to 50,000 strikes, 24-hour window.

    Route:  /lightning/{action}
    Update: Real-time
    Supported actions: :id, closest, route, within
    Supported filters:
      cg  – cloud-to-ground strikes only (default)
      all – cloud-to-ground + intracloud (IC) pulses
    Key params: p, limit, radius, minradius, fields, filter, sort, skip,
                from, to, format
    """
    ROUTE = "/lightning"


class _LightningSummaryEndpoint(_Endpoint):
    """
    Strike count summary for a region.

    Route:  /lightning/summary/{action}
    Supported actions: :id, closest
    Supported filters: cg, all, negative, positive
    """
    ROUTE = "/lightning/summary"


class _LightningArchiveEndpoint(_Endpoint):
    """
    Historical lightning data (requires advanced lightning access).

    Route:  /lightning/archive/{action}
    Supported actions: :id, closest, route
    Supported filters: cg, ic, all
    """
    ROUTE = "/lightning/archive"


class _LightningAnalyticsEndpoint(_Endpoint):
    """
    Lightning analytics including ellipse zones of probable strike location.

    Route:  /lightning/analytics/{action}
    Supported actions: :id, closest, route, within
    Supported filters: cg, all, ellipse50, ellipse80, ellipse90, ellipse99
    """
    ROUTE = "/lightning/analytics"


class _LightningThreatsEndpoint(_Endpoint):
    """
    Lightning threat polygons for a location or region.

    Route:  /lightning/threats/{action}
    Supported actions: :id, closest, contains, affects, route
    Supported filters: severe, notsevere, forceutc
    """
    ROUTE = "/lightning/threats"


class _LightningFlashEndpoint(_Endpoint):
    """
    Individual flash-level lightning data.

    Route:  /lightning/flash/{action}
    Supported actions: :id, closest, route
    """
    ROUTE = "/lightning/flash"


class _HailArchiveEndpoint(_Endpoint):
    """
    Historical hail event records.

    Route:  /hail/archive/{action}
    Supported actions: :id
    Key params: limit, fields, from, to
    """
    ROUTE = "/hail/archive"


class _HailThreatsEndpoint(_Endpoint):
    """
    Hail threat forecast polygons.

    Route:  /hail/threats/{action}
    Supported actions: :id, closest, contains, route
    Supported filters: severe, notsevere, test
    """
    ROUTE = "/hail/threats"


class _FiresEndpoint(_Endpoint):
    """
    Active wildfire information including perimeter data.

    Route:  /fires/{action}
    Update: Near real-time
    Supported actions: :id, closest, within, search
    Supported filters: geo, hasperimeter, hasnoperimeter
    Queryable: id, dt, area, name, state
    Sortable: dt, area, state
    """
    ROUTE = "/fires"


class _FiresOutlookEndpoint(_Endpoint):
    """
    Fire weather outlook from NWS SPC.

    Route:  /fires/outlook/{action}
    Supported actions: :id, affects, contains, search, within
    Supported filters:
      firewx     – fire weather zones
      dryltg     – dry lightning areas
      elevated, critical, extreme – severity levels
      isodryt, sctdryt – isolated/scattered dry thunderstorms
      day1, day2, day3 – specific outlook day
      all        – all days combined
    """
    ROUTE = "/fires/outlook"


class _EarthquakesEndpoint(_Endpoint):
    """
    Earthquake data from USGS and global seismic networks.

    Route:  /earthquakes/{action}
    Update: Near real-time
    Supported actions: :id, closest, within, search, affects
    Supported filters (magnitude classes):
      mini (<2.0), minor (2.0-3.9), light (3.0-3.9),
      moderate (4.0-4.9), strong (5.0-5.9), major (6.0-6.9),
      great (>=7.0), shallow
    Queryable: id, mag, depth, state, name
    Sortable: mag, depth, dt
    """
    ROUTE = "/earthquakes"


class _TropicalCyclonesEndpoint(_Endpoint):
    """
    Active tropical cyclones: positions, tracks, forecasts.

    Route:  /tropicalcyclones/{action}
    Update: 6 hours; up to 1-3 hours for NHC storms near landfall
    Default limit: 10 (to capture all active storms in one request)
    Supported actions: :all (omit action for all), closest, search, within, affects
    Supported filters (basins):
      atlantic (al), eastpacific (ep), centralpacific (cp),
      westpacific (wp), pacific, indian, io, sh, si, au, sp
    Queryable: id, basin, origin, currentbasin, year
    Sortable: id, basin, year, windMPH, pressureMB
    """
    ROUTE = "/tropicalcyclones"

    def all_active(self, **params) -> Dict[str, Any]:
        """Return all currently active tropical cyclones globally."""
        return self._request("", params)


class _TropicalCyclonesArchiveEndpoint(_Endpoint):
    """
    Historical tropical cyclone data.

    Route:  /tropicalcyclones/archive/{action}
    Supported actions: closest, search, within, affects
    Supported filters: same as tropicalcyclones (basin filters)
    """
    ROUTE = "/tropicalcyclones/archive"


class _ConvectiveOutlookEndpoint(_Endpoint):
    """
    SPC convective outlooks: severe thunderstorm risk polygons and probabilities.

    Route:  /convective/outlook/{action}
    Coverage: US only
    Supported actions: :id, affects, contains, search
    Supported filters:
      cat      – categorical outlook polygons
      prob     – probability polygons
      conhazo  – any convective hazard
      torn     – tornado threat area
      xtorn, sigtorn, alltorn – enhanced tornado filters
      hail     – hail threat area
      xhail, sighail, allhail – enhanced hail filters
      wind     – wind threat area
      xwind, sigwind, allwind – enhanced wind filters
    """
    ROUTE = "/convective/outlook"


class _DroughtsMonitorEndpoint(_Endpoint):
    """
    US Drought Monitor data from the National Drought Mitigation Center.

    Route:  /droughts/monitor/{action}
    Coverage: US only
    Supported actions: :id, affects, contains, search
    Supported filters:
      all – all drought levels combined
      d0  – Abnormally Dry
      d1  – Moderate Drought
      d2  – Severe Drought
      d3  – Extreme Drought
      d4  – Exceptional Drought
    """
    ROUTE = "/droughts/monitor"


class _TidesEndpoint(_Endpoint):
    """
    Predicted tidal information for US locations.

    Route:  /tides/{action}
    Supported actions: :id, closest, within, search
    Supported filters: highlow, high, low
    Key params: limit, p, radius, minradius, filter, query, sort, skip,
                from, to, plimit, psort, pskip, fields
    """
    ROUTE = "/tides"


class _TidesStationsEndpoint(_Endpoint):
    """
    Tidal gauge station metadata.

    Route:  /tides/stations/{action}
    Supported actions: :id, closest, within, search
    """
    ROUTE = "/tides/stations"


class _MaritimeEndpoint(_Endpoint):
    """
    Global marine weather: wave heights/periods, ocean currents, SST,
    tidal surge, swell direction.

    Route:  /maritime/{action}
    Supported actions: :id, route
    Supported filters: #hr (e.g. 1hr, 3hr, 6hr)
    Key params: p, filter, from, to, for, pskip, psort, plimit, format
    """
    ROUTE = "/maritime"


class _MaritimeArchiveEndpoint(_Endpoint):
    """
    Historical maritime/marine weather data.

    Route:  /maritime/archive/{action}
    Supported actions: :id, route
    Supported filters: #hr
    """
    ROUTE = "/maritime/archive"


class _NormalsEndpoint(_Endpoint):
    """
    Climate normals (30-year averages) for temperature, precipitation, snow.

    Route:  /normals/{action}
    Supported actions: :id, closest, within, search, route
    Supported filters: daily, monthly, annual, hastemp, hasprecip, hassnow
    Key params: p, limit, radius, minradius, fields, filter, query, sort,
                skip, from, to, plimit, psort, pskip, pfilter, format
    """
    ROUTE = "/normals"


class _NormalsStationsEndpoint(_Endpoint):
    """
    Stations with climate normal data.

    Route:  /normals/stations/{action}
    Supported actions: :id, closest, within, search, route
    Supported filters: hastemp, hasprcp, hassnow
    """
    ROUTE = "/normals/stations"


class _RiversEndpoint(_Endpoint):
    """
    River/lake gauge observations: water level, flow, flood stages.
    Primary source: NOAA AHPS.

    Route:  /rivers/{action}
    Supported actions: :id, closest, within, search
    Supported filters:
      inservice, outofservice
      notdefined, lowthreshold, noflooding
      action, flood, minor, moderate, major – flood stage categories
      obsnotcurrent
    Queryable: id, name, state, stageFt, stageM, floodStageFt
    """
    ROUTE = "/rivers"


class _RiversGaugesEndpoint(_Endpoint):
    """
    River gauge station metadata including crest records.

    Route:  /rivers/gauges/{action}
    Supported actions: :id, closest, search, within
    Supported filters: impacts, recentcrests, historiccrests, lowwaterrecords
    """
    ROUTE = "/rivers/gauges"


class _SunMoonEndpoint(_Endpoint):
    """
    Sunrise/set, twilight, moonrise/set, and moon phase for a location.
    Up to one month of data per request.

    Route:  /sunmoon/{action}
    Supported actions: :id
    Supported filters: sun, twilight, moon, moonphase
    Key params: limit, filter, from, to, fields, skip, sort
    """
    ROUTE = "/sunmoon"


class _MoonPhasesEndpoint(_Endpoint):
    """
    Exact times for major moon phase events (new, first quarter, full, third).

    Route:  /sunmoon/moonphases/{action}
    Supported actions: :id, search, contains
    Supported filters: new, first, full, third
    Key params: p, limit, filter, from, to
    """
    ROUTE = "/sunmoon/moonphases"


class _PlacesEndpoint(_Endpoint):
    """
    Geographic location lookup: cities, POIs, counties, features.

    Route:  /places/{action}
    Supported actions: :id, closest, within, search
    Supported filters:
      airport, amusement, bridge, camp, church, county, divisions,
      feature, fort, golf, hist, lake, locale, military, mine, park,
      pop, post, rail, school, shrine, spot, summit, tower, tunnel,
      unknown, woods
    Queryable: name, state, country, id, pop, county, region
    Sortable: name, state, country, pop, elev
    """
    ROUTE = "/places"


class _PlacesAirportsEndpoint(_Endpoint):
    """
    Airport location data.

    Route:  /places/airports/{action}
    Supported actions: :id, closest, within, search
    Supported filters:
      airport, smallairport, medairport, largeairport,
      heliport, balloonport, sea, all, closed
    """
    ROUTE = "/places/airports"


class _PlacesPostalCodesEndpoint(_Endpoint):
    """
    Postal code location data.

    Route:  /places/postalcodes/{action}
    Supported actions: :id, closest, within, search
    Supported filters: us, ca (canada), standard
    """
    ROUTE = "/places/postalcodes"


class _CountriesEndpoint(_Endpoint):
    """
    Country metadata and information.

    Route:  /countries/{action}
    Supported actions: :id, search
    Key params: p, limit, query, skip, fields
    """
    ROUTE = "/countries"


class _IndicesEndpoint(_Endpoint):
    """
    Weather impact indices: arthritis, cold/flu, migraine, outdoor activities.

    Route:  /indices/:type/{action}
    Supported types:
      arthritis, coldflu, migraine, sinus, outdoor, golf, biking,
      swimming, campfire, beeactive
    Supported actions: :id, route
    Supported filters: day, daynight, #hr
    Key params: p, limit, fields, filter, from, to

    Usage: client.indices.id("seattle,wa", index_type="arthritis")
    """
    ROUTE = "/indices"

    def _request_type(
        self,
        index_type: str,
        action: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        path = f"/indices/{index_type}/{action}".rstrip("/")
        return self._client._get(path, params)

    def id(self, place: str, index_type: str = "outdoor", **params) -> Dict[str, Any]:  # type: ignore[override]
        """
        Get index values for a location.

        Parameters
        ----------
        place : str
            Location identifier.
        index_type : str
            One of: arthritis, coldflu, migraine, sinus, outdoor, golf,
            biking, swimming, campfire, beeactive.
        """
        return self._request_type(index_type, place, params)

    def route(  # type: ignore[override]
        self,
        places: Union[str, List[str]],
        index_type: str = "outdoor",
        **params,
    ) -> Dict[str, Any]:
        """Get index values along a route."""
        if isinstance(places, list):
            params["p"] = ";".join(places)
        else:
            params["p"] = places
        return self._request_type(index_type, "route", params)


class _ImpactsEndpoint(_Endpoint):
    """
    Business weather impact risk scores (0–5 scale) for various activities.

    Route:  /impacts/:activity/{action}
    Supported activities:
      general     – general outdoor activities
      trucking    – road freight/trucking logistics
      smallcraft  – small maritime vessels
      largevessel – large maritime/cruise ship operations
    Supported actions: :id, route
    Supported filters: minseverity0 through minseverity5
    """
    ROUTE = "/impacts"

    def _request_activity(
        self,
        activity: str,
        action: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        path = f"/impacts/{activity}/{action}".rstrip("/")
        return self._client._get(path, params)

    def id(self, place: str, activity: str = "general", **params) -> Dict[str, Any]:  # type: ignore[override]
        """
        Get impact scores for a location.

        Parameters
        ----------
        place : str
            Location identifier.
        activity : str
            One of: general, trucking, smallcraft, largevessel.
        """
        return self._request_activity(activity, place, params)

    def route(  # type: ignore[override]
        self,
        places: Union[str, List[str]],
        activity: str = "general",
        **params,
    ) -> Dict[str, Any]:
        """Get impact scores along a route."""
        if isinstance(places, list):
            params["p"] = ";".join(places)
        else:
            params["p"] = places
        return self._request_activity(activity, "route", params)


class _RoadWeatherEndpoint(_Endpoint):
    """
    Road surface weather conditions: pavement temperature, ice/snow risk.

    Route:  /roadweather/{action}
    Supported actions: :id, route
    Supported filters: primary, secondary, bridge, noroadcheck
    Key params: p, for, from, to, plimit, pskip, psort, fields
    """
    ROUTE = "/roadweather"


class _RoadWeatherConditionsEndpoint(_Endpoint):
    """
    Current road weather surface conditions.

    Route:  /roadweather/conditions/{action}
    Supported actions: :id, route
    Supported filters: primary, secondary, bridge, noroadcheck
    """
    ROUTE = "/roadweather/conditions"


class _RoadWeatherAnalyticsEndpoint(_Endpoint):
    """
    Road weather analytics data.

    Route:  /roadweather/analytics/{action}
    Supported actions: :id, route
    Supported filters: primary, secondary, bridge, noroadcheck, addweather
    """
    ROUTE = "/roadweather/analytics"


class _ThreatsEndpoint(_Endpoint):
    """
    Combined weather threat summary for a location.

    Route:  /threats/{action}
    Supported actions: :id
    Key params: p, radius, fields, query
    """
    ROUTE = "/threats"


class _PhrasesSummaryEndpoint(_Endpoint):
    """
    Natural-language weather condition phrases for a location.

    Route:  /phrases/summary/{action}
    Supported actions: :id
    Supported filters: metar, pws, mesonet, allstations, noob
    """
    ROUTE = "/phrases/summary"


class _XcastForecastsEndpoint(_Endpoint):
    """
    High-resolution Xcast forecast data.

    Route:  /xcast/forecasts/{action}
    Supported actions: :id
    Supported filters: 1hr, 10min
    Key params: limit, fields, filter, from, to, skip
    """
    ROUTE = "/xcast/forecasts"


class _EnergyFarmEndpoint(_Endpoint):
    """
    Solar/wind energy farm weather data.

    Route:  /energy/farm/{action}
    Supported actions: :id
    Key params: from, to, plimit, pskip
    """
    ROUTE = "/energy/farm"


class _RenewablesIrradianceArchiveEndpoint(_Endpoint):
    """
    Historical solar irradiance data for renewable energy applications.

    Route:  /renewables/irradiance/archive/{action}
    Supported actions: :id
    Supported filters: #hr
    Key params: fields, filter, from, to, tilt, azimuth, panel_mode, horizon
    """
    ROUTE = "/renewables/irradiance/archive"


# ---------------------------------------------------------------------------
# Convenience top-level functions
# ---------------------------------------------------------------------------

def get_current_conditions(
    client: AerisClient,
    place: str,
    fields: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve current weather conditions combining observations and forecasts.

    Returns a batch response with observations, forecasts, and active alerts.
    """
    sub_requests = ["/observations", "/forecasts", "/alerts"]
    params: Dict[str, Any] = {}
    if fields:
        params["fields"] = fields
    return client.batch(sub_requests, place=place, **params)


def get_severe_weather(
    client: AerisClient,
    place: str,
    radius: str = "100miles",
) -> Dict[str, Any]:
    """
    Fetch all active severe weather information for a region.

    Returns a batch with alerts, storm cells, storm reports, and lightning.
    """
    sub_requests = [
        "/alerts%3Ffilter=severe",
        f"/stormcells/within%3Fp={urllib.parse.quote(place)}&radius={radius}&filter=threat",
        f"/stormreports/within%3Fp={urllib.parse.quote(place)}&radius={radius}",
        f"/lightning/within%3Fp={urllib.parse.quote(place)}&radius={radius}",
    ]
    return client.batch(sub_requests)


def get_tropical_activity(client: AerisClient) -> Dict[str, Any]:
    """Return all currently active tropical cyclones globally."""
    return client.tropicalcyclones.all_active()


def get_fire_weather(
    client: AerisClient,
    place: str,
    radius: str = "200miles",
) -> Dict[str, Any]:
    """Fetch active fires and fire weather outlook for a region."""
    sub_requests = [
        f"/fires/closest%3Fp={urllib.parse.quote(place)}&radius={radius}",
        f"/fires/outlook/{urllib.parse.quote(place)}",
    ]
    return client.batch(sub_requests)


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os

    CLIENT_ID = os.getenv("AERIS_CLIENT_ID", "YOUR_CLIENT_ID")
    CLIENT_SECRET = os.getenv("AERIS_CLIENT_SECRET", "YOUR_CLIENT_SECRET")

    client = AerisClient(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)

    print("=== Current Observations: Seattle, WA ===")
    try:
        obs = client.observations.id("seattle,wa")
        ob = obs["response"]["ob"]
        print(f"  Temperature: {ob.get('tempF')}°F / {ob.get('tempC')}°C")
        print(f"  Weather:     {ob.get('weather')}")
        print(f"  Wind:        {ob.get('windSpeedMPH')} mph from {ob.get('windDir')}")
        print(f"  Humidity:    {ob.get('humidity')}%")
    except AerisError as e:
        print(f"  Error: {e}")
    except requests.RequestException as e:
        print(f"  Network error: {e}")

    print()
    print("=== 3-Day Daily Forecast: New York, NY ===")
    try:
        fcst = client.forecasts.daily("new york,ny", days=3)
        for period in fcst["response"][0].get("periods", [])[:3]:
            print(
                f"  {period.get('dateTimeISO','?')[:10]}: "
                f"High {period.get('maxTempF')}°F / "
                f"Low {period.get('minTempF')}°F - "
                f"{period.get('weather','?')}"
            )
    except AerisError as e:
        print(f"  Error: {e}")
    except requests.RequestException as e:
        print(f"  Network error: {e}")

    print()
    print("=== Active Alerts: Texas ===")
    try:
        alerts = client.alerts.active("texas", filter="all", limit=5)
        for alert in alerts.get("response", [])[:5]:
            print(f"  [{alert.get('type','?')}] {alert.get('details',{}).get('name','?')}")
    except AerisError as e:
        print(f"  Error: {e}")
    except requests.RequestException as e:
        print(f"  Network error: {e}")

    print()
    print("=== Air Quality: Los Angeles, CA ===")
    try:
        aq = client.airquality.id("los angeles,ca")
        resp = aq["response"]
        if isinstance(resp, list):
            resp = resp[0]
        periods = resp.get("periods") or []
        if periods:
            p = periods[0]
            print(f"  AQI: {p.get('aqi')} ({p.get('category')})")
            print(f"  Dominant pollutant: {p.get('dominant')}")
    except AerisError as e:
        print(f"  Error: {e}")
    except requests.RequestException as e:
        print(f"  Network error: {e}")

    print()
    print("=== Active Tropical Cyclones (global) ===")
    try:
        tc = client.tropicalcyclones.all_active()
        storms = tc.get("response", [])
        if storms:
            for storm in storms:
                prof = storm.get("profile", {})
                print(
                    f"  {prof.get('name','?')} ({prof.get('basin','?')}) - "
                    f"Cat {prof.get('cat','?')}, "
                    f"Winds: {prof.get('windMPH','?')} mph"
                )
        else:
            print("  No active tropical cyclones.")
    except AerisError as e:
        print(f"  Error: {e}")
    except requests.RequestException as e:
        print(f"  Network error: {e}")

    print()
    print("=== Batch Request: Minneapolis, MN ===")
    try:
        batch_data = client.batch(
            requests_param=["/observations", "/forecasts", "/alerts"],
            place="minneapolis,mn",
        )
        for idx, result in enumerate(batch_data.get("response", [])):
            ep_id = result.get("id", f"request-{idx}")
            success = result.get("success", False)
            print(f"  {ep_id}: success={success}")
    except AerisError as e:
        print(f"  Error: {e}")
    except requests.RequestException as e:
        print(f"  Network error: {e}")
