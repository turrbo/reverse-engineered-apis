# National Weather Service API - Reverse Engineering Report

**API Base URL:** `https://api.weather.gov`
**Docs:** https://www.weather.gov/documentation/services-web-api
**OpenAPI Spec:** https://api.weather.gov/openapi.json (version 3.7.0)
**Client File:** `weather_gov_client.py`

---

## Overview

The National Weather Service (NWS) provides a **free, public, unauthenticated REST API** for weather data covering the United States and its territories. The API follows the **OGC (Open Geospatial Consortium)** standards and returns data in **GeoJSON** and **JSON-LD** formats with linked data context.

### Key Characteristics

- **No API key or authentication required** — completely public
- **User-Agent header is required** (NWS policy requires apps to identify themselves)
- **Accept header:** `application/geo+json` (recommended)
- **Base URL:** `https://api.weather.gov`
- **Rate limits:** Not officially published; liberal for reasonable use
- **Data format:** GeoJSON FeatureCollections with `@context` (JSON-LD)
- **Units:** SI units (metric) for raw values; the Python client converts to US units

### The Two-Step Forecast Lookup

The most important workflow for forecasts is a **two-step process**:

```
Step 1: GET /points/{lat},{lon}
        -> Returns: gridId (WFO code), gridX, gridY

Step 2: GET /gridpoints/{wfo}/{x},{y}/forecast
        -> Returns: 7-day forecast periods
```

This design exists because the NWS organizes forecasts by weather office grid cells rather than by lat/lon directly.

---

## Complete Endpoint Reference

All 54 endpoints discovered from the official OpenAPI spec at `https://api.weather.gov/openapi.json` (version 3.7.0):

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | Query all alerts (historical + active) |
| GET | `/alerts/active` | Get currently active alerts |
| GET | `/alerts/active/count` | Count of active alerts by area/region |
| GET | `/alerts/active/zone/{zoneId}` | Active alerts for a specific zone |
| GET | `/alerts/active/area/{area}` | Active alerts for a state (e.g. "NY") |
| GET | `/alerts/active/region/{region}` | Active alerts for a marine region |
| GET | `/alerts/types` | List of all possible alert event types |
| GET | `/alerts/{id}` | Single alert by CAP URN identifier |

**Alert filter parameters for `/alerts` and `/alerts/active`:**
- `area` - Two-letter state code ("NY", "CA", "TX")
- `zone` - NWS zone ID ("NYZ072", "TXC453")
- `point` - "lat,lon" string
- `region` - Marine region: AL, AT, GL, GM, PA, PI
- `event` - Event name ("Tornado Warning", "Winter Storm Warning")
- `severity` - Extreme, Severe, Moderate, Minor, Unknown
- `urgency` - Immediate, Expected, Future, Past, Unknown
- `certainty` - Observed, Likely, Possible, Unlikely, Unknown
- `status` - actual, exercise, system, test, draft
- `message_type` - alert, update, cancel
- `start`, `end` - ISO 8601 datetime range (for `/alerts` only)
- `limit`, `cursor` - Pagination (for `/alerts` only)

**Marine region codes:** AL=Alaska, AT=Atlantic, GL=Great Lakes, GM=Gulf of Mexico, PA=Eastern Pacific, PI=Central/Western Pacific

### Points (Lat/Lon Resolution)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/points/{latitude},{longitude}` | Resolve lat/lon to WFO grid |
| GET | `/points/{latitude},{longitude}/radio` | NOAA Weather Radio for a point |
| GET | `/points/{latitude},{longitude}/stations` | Observation stations near a point |

**Point response includes:**
```json
{
  "gridId": "OKX",
  "gridX": 33,
  "gridY": 35,
  "forecast": "https://api.weather.gov/gridpoints/OKX/33,35/forecast",
  "forecastHourly": "https://api.weather.gov/gridpoints/OKX/33,35/forecast/hourly",
  "forecastGridData": "https://api.weather.gov/gridpoints/OKX/33,35",
  "observationStations": "https://api.weather.gov/gridpoints/OKX/33,35/stations",
  "timeZone": "America/New_York",
  "radarStation": "KDIX",
  "relativeLocation": { "city": "Hoboken", "state": "NJ", ... }
}
```

### Gridpoints (Forecasts)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/gridpoints/{wfo}/{x},{y}` | Raw gridded forecast data |
| GET | `/gridpoints/{wfo}/{x},{y}/forecast` | 7-day twice-daily forecast |
| GET | `/gridpoints/{wfo}/{x},{y}/forecast/hourly` | 7-day hourly forecast |
| GET | `/gridpoints/{wfo}/{x},{y}/stations` | Observation stations for grid |

**Forecast period fields:**
```json
{
  "number": 1,
  "name": "Tonight",
  "startTime": "2026-03-24T19:00:00-04:00",
  "endTime": "2026-03-25T06:00:00-04:00",
  "isDaytime": false,
  "temperature": 36,
  "temperatureUnit": "F",
  "probabilityOfPrecipitation": { "unitCode": "wmoUnit:percent", "value": 0 },
  "windSpeed": "7 to 15 mph",
  "windDirection": "SW",
  "icon": "https://api.weather.gov/icons/land/night/bkn?size=medium",
  "shortForecast": "Mostly Cloudy",
  "detailedForecast": "Mostly cloudy, with a low around 36..."
}
```

**Hourly periods add:**
- `dewpoint` - Dewpoint temperature (degC)
- `relativeHumidity` - Relative humidity (percent)

**Raw grid data** (`/gridpoints/{wfo}/{x},{y}`) returns time-series arrays for:
temperature, dewpoint, maxTemperature, minTemperature, relativeHumidity,
apparentTemperature, heatIndex, windChill, windSpeed, windDirection, windGust,
probabilityOfPrecipitation, quantitativePrecipitation, snowfallAmount,
snowLevel, iceAccumulation, visibility, weather, hazards, and many more.

### Stations & Observations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stations` | List observation stations |
| GET | `/stations/{stationId}` | Single station metadata |
| GET | `/stations/{stationId}/observations` | Historical observations |
| GET | `/stations/{stationId}/observations/latest` | Most recent observation |
| GET | `/stations/{stationId}/observations/{time}` | Observation at specific time |
| GET | `/stations/{stationId}/tafs` | Terminal Aerodrome Forecasts |
| GET | `/stations/{stationId}/tafs/{date}/{time}` | Specific TAF |

**Station list parameters:**
- `state` - Two-letter state code
- `stationId` - One or more specific station IDs
- `limit` - Max results (default 500)
- `cursor` - Pagination

**Observation fields (all in SI units):**
- `temperature` - degC
- `dewpoint` - degC
- `windDirection` - degrees (angle)
- `windSpeed` - km/h
- `windGust` - km/h
- `barometricPressure` - Pa
- `seaLevelPressure` - Pa
- `visibility` - m
- `relativeHumidity` - percent
- `windChill` - degC
- `heatIndex` - degC
- `precipitationLastHour`, `Last3Hours`, `Last6Hours` - mm
- `maxTemperatureLast24Hours`, `minTemperatureLast24Hours` - degC
- `cloudLayers` - list of {amount, base} dicts
- `rawMessage` - raw METAR string
- `textDescription` - e.g. "Clear", "Partly Cloudy"
- `qualityControl` - "V"=verified, "C"=coarse QC, "Z"=null/zeroed

### Offices (Weather Forecast Offices)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/offices/{officeId}` | WFO metadata |
| GET | `/offices/{officeId}/headlines` | Office news/headlines |
| GET | `/offices/{officeId}/headlines/{headlineId}` | Single headline |
| GET | `/offices/{officeId}/weatherstories` | Weather stories |

**Common WFO codes by region:**
- Northeast: OKX (NY), BOX (Boston), PHI (Philadelphia), BUF (Buffalo)
- Southeast: MHX (NC coast), JAX (Jacksonville), TAE (Tallahassee)
- Central: CHI (Chicago), LOT (Chicago), DVN (Davenport)
- South: FWD (Dallas-Ft Worth), SHV (Shreveport), LCH (Lake Charles)
- West: LOX (Los Angeles), SGX (San Diego), STO (Sacramento), SEW (Seattle)
- Mountain: BOU (Denver), SLC (Salt Lake City), PSR (Phoenix)

### Zones

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/zones` | List all zones |
| GET | `/zones/{type}` | List zones by type |
| GET | `/zones/{type}/{zoneId}` | Single zone details |
| GET | `/zones/forecast/{zoneId}/forecast` | Text forecast for zone |
| GET | `/zones/forecast/{zoneId}/observations` | Recent zone observations |
| GET | `/zones/forecast/{zoneId}/stations` | Stations in a zone |

**Zone types:** `land`, `marine`, `forecast`, `public`, `coastal`, `offshore`, `fire`, `county`

**Zone ID format examples:**
- `NYZ072` - New York (Manhattan) forecast zone
- `NYC061` - Manhattan county zone
- `ANZ331` - Atlantic coastal marine zone
- `NYZ213` - New York fire weather zone

### Radar

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/radar/stations` | List all NWS WSR-88D radar stations |
| GET | `/radar/stations/{stationId}` | Single radar station details + RDA status |
| GET | `/radar/stations/{stationId}/alarms` | Active alarms for radar station |
| GET | `/radar/servers` | List of NWS radar data servers |
| GET | `/radar/queues/{host}` | Radar data queue info |
| GET | `/radar/profilers/{stationId}` | Wind profiler data |

**Radar station response includes:**
- `stationType`: "WSR-88D" (NEXRAD)
- `latency`: current, average, max data latency in seconds
- `levelTwoLastReceivedTime`: last data receipt timestamp
- `rda`: Radar Data Acquisition unit status (controlStatus, volumeCoveragePattern, buildNumber)
- `performance`: operational performance metrics

**Radar image URLs (undocumented, from ridge viewer):**
```
https://radar.weather.gov/ridge/standard/{STATION}_{FRAME}.gif
```
Example: `https://radar.weather.gov/ridge/standard/KOKX_0.gif`

### Products (Text Forecasts & Bulletins)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/products` | Search products |
| GET | `/products/{productId}` | Single product full text |
| GET | `/products/types` | All product type codes |
| GET | `/products/types/{typeId}` | Products of a specific type |
| GET | `/products/types/{typeId}/locations` | Locations that issue a type |
| GET | `/products/types/{typeId}/locations/{locationId}` | Products by type+location |
| GET | `/products/types/{typeId}/locations/{locationId}/latest` | Latest product |
| GET | `/products/locations` | All product location codes |
| GET | `/products/locations/{locationId}/types` | Types issued at a location |

**Product search parameters:**
- `type` - 3-letter product code (e.g. "AFD", "HWO", "SPS")
- `office` - 4-letter ICAO office code (e.g. "KOKX", "KLWX") -- note: 4 letters!
- `wmoid` - WMO collective ID
- `awipsid` - AWIPS product ID
- `location` - Location code
- `start`, `end` - ISO datetime range
- `limit` - Max results (default 500)

**Common product codes:**
```
AFD  Area Forecast Discussion         - Technical discussion by forecasters
ZFP  Zone Forecast Product            - Public zone forecasts
HWO  Hazardous Weather Outlook        - Upcoming hazard potential
SPS  Special Weather Statement        - Significant weather not requiring warning
SVR  Severe Thunderstorm Warning      - Tornado Warning
TOR  Tornado Warning
FWF  Fire Weather Forecast (Morning)
RFD  Fire Weather Forecast (Afternoon)
MWS  Marine Weather Statement
CFW  Coastal/Lakeshore Hazard Message
TWC  Tropical Weather Outlook
ABV  Rawinsonde Data Above 100 mb
CLI  Climatological Report (Daily)
CWF  Coastal Waters Forecast
GLF  Great Lakes Forecast
LSR  Local Storm Report
MWW  Marine Weather Message
OAV  Other Aviation Products
POE  Probability of Excessive Rainfall
RR.  Hydrometeorological Data (various)
SWR  Severe Weather Statement
TSU  Tsunami Warning/Watch/Advisory
```

### Aviation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/aviation/sigmets` | All active SIGMETs |
| GET | `/aviation/sigmets/{atsu}` | SIGMETs from specific ATSU |
| GET | `/aviation/sigmets/{atsu}/{date}` | SIGMETs for date |
| GET | `/aviation/sigmets/{atsu}/{date}/{time}` | Specific SIGMET |
| GET | `/aviation/cwsus/{cwsuId}` | Center Weather Service Unit info |
| GET | `/aviation/cwsus/{cwsuId}/cwas` | Center Weather Advisories |
| GET | `/aviation/cwsus/{cwsuId}/cwas/{date}/{sequence}` | Specific CWA |

**SIGMET fields:** issueTime, fir (Flight Information Region), atsu, sequence, phenomenon, start, end, and polygon geometry

### Miscellaneous

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/glossary` | Full NWS meteorological glossary (~500 terms) |
| GET | `/icons/{set}/{timeOfDay}/{first}` | Weather icon image |
| GET | `/icons/{set}/{timeOfDay}/{first}/{second}` | Dual condition icon |
| GET | `/icons` | List available icon sets |
| GET | `/thumbnails/satellite/{area}` | Satellite thumbnail URLs |
| GET | `/radio/{callSign}/broadcast` | NOAA Weather Radio broadcast info |

---

## Undocumented / Supplementary Endpoints

These endpoints are used by the NWS website but are not in the main API docs:

### GOES Satellite Imagery (NESDIS/STAR)

```
https://cdn.star.nesdis.noaa.gov/{satellite}/ABI/{sector}/{product}/{size}.jpg
```

**Satellite options:**
- `GOES19` - Primary East satellite (covers Eastern US, Atlantic)
- `GOES18` - Primary West satellite (covers Western US, Pacific)
- `GOES17` - Secondary West

**Sector options:**
- `CONUS` - Continental United States
- `FULL` - Full disk (Western Hemisphere)
- `MESOSCALE-1`, `MESOSCALE-2` - Rapid-scan mesoscale sectors
- `SECTOR/NE` - Northeast US
- `SECTOR/SE` - Southeast US
- `SECTOR/MW` - Midwest US
- `SECTOR/SW` - Southwest US
- `SECTOR/NW` - Northwest US

**Product options:**
- `GEOCOLOR` - True color (daytime) / multispectral (night)
- `AirMass` - Air mass RGB
- `DayConvection` - Daytime convection
- `Sandwich` - Infrared RGB sandwich
- `Band02` - Visible channel
- `Band13` - Clean Longwave IR Window

**Size options:** `625x375`, `1250x750`, `2500x1500`, `5000x3000`, `10000x6000`

**Example:**
```
https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/625x375.jpg
https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/NE/GEOCOLOR/1200x1200.jpg
```

### Legacy Forecast Pages

The legacy forecast.weather.gov site still works:
```
https://forecast.weather.gov/zipcity.php?inputstring={zipcode}
https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}&site={wfo}
```

### Weather Icons (NWS new API icons)

Icon URLs are returned directly in forecast period responses:
```
https://api.weather.gov/icons/land/{day|night}/{condition}?size={small|medium|large}
https://api.weather.gov/icons/land/{day|night}/{condition1}/{condition2}?size=medium
```

Common icon condition codes:
`skc`, `few`, `sct`, `bkn`, `ovc`, `wind_skc`, `wind_few`, `wind_sct`, `wind_bkn`, `wind_ovc`, `snow`, `rain_snow`, `fzra`, `rain_fzra`, `snow_fzra`, `sleet`, `rain_sleet`, `snow_sleet`, `blizzard`, `tsra_sct`, `tsra_hi`, `tsra`, `hurricane`, `tropical_storm`, `tornado`, `dust`, `smoke`, `haze`, `hot`, `cold`, `rain`, `rain_showers`, `rain_showers_hi`, `fog`

### Weather.gov Graphical Forecast Thumbnails

```
https://graphical.weather.gov/images/thumbnail/latest_{product}_{region}_thumbnail.png
```

Products: `MaxMinT`, `Wx`, `Pop12`, `QPF`, `Snow`
Regions: `northeast`, `southeast`, `centralgreat_lakes`, `upper_mississippi`, `ohio_valley`, `southern_plains`, `northern_plains`, `southern_rockies`, `northern_rockies`, `pacific_southwest`, `alaska`, `hawaii`

---

## Python Client Usage

### Installation

```bash
pip install requests
```

### Quick Start

```python
from weather_gov_client import NWSClient

# Initialize with a descriptive User-Agent (required by NWS policy)
client = NWSClient(user_agent="MyApp/1.0 (myemail@example.com)")

# Get a 7-day forecast for any US location
daily, hourly = client.get_forecast_by_location(40.7128, -74.0060)

# Print today's forecast
for period in daily['periods'][:4]:
    print(f"{period['name']}: {period['temperature']}°F - {period['shortForecast']}")
```

### All Available Methods

#### Forecast Methods

```python
# Two-step lookup
point = client.get_point(lat, lon)
# -> returns gridId, gridX, gridY, timeZone, radarStation, relativeLocation, ...

wfo, gx, gy = client.resolve_grid(lat, lon)
# -> returns ("OKX", 33, 35)

daily_forecast = client.get_forecast(wfo, grid_x, grid_y)
# -> returns {'periods': [...]}

hourly_forecast = client.get_forecast_hourly(wfo, grid_x, grid_y)
# -> returns {'periods': [...]} with 1-hour intervals, includes dewpoint + RH

raw_grid = client.get_grid_data(wfo, grid_x, grid_y)
# -> returns detailed time-series for 20+ meteorological variables

# One-step convenience
daily, hourly = client.get_forecast_by_location(lat, lon)
# -> automatically resolves grid, returns both forecast types
```

#### Observation Methods

```python
stations = client.get_point_stations(lat, lon)
# -> list of nearby observation stations

station_info = client.get_station("KNYC")
# -> station metadata

latest_obs = client.get_station_observation_latest("KNYC")
# -> raw dict with SI units

from weather_gov_client import format_observation
friendly_obs = format_observation(latest_obs)
# -> dict with US units (°F, mph, inHg, miles)

history = client.get_station_observations("KNYC", start="2024-01-01T00:00:00Z", limit=100)
# -> list of historical observations

metar = client.get_metar("KNYC")
# -> "KNYC 250051Z AUTO 10SM CLR 04/M06 A3037..."

current = client.get_current_conditions(lat, lon)
# -> auto-finds nearest station, returns latest observation
```

#### Alert Methods

```python
alerts = client.get_active_alerts(area="CA")
# -> {'features': [...]}

alerts = client.get_active_alerts(
    severity="Extreme",
    urgency="Immediate",
    event="Tornado Warning"
)

alerts = client.get_active_alerts_by_zone("NYZ072")
# -> alerts for Manhattan

count = client.get_active_alerts_count()
# -> {'total': 304, 'land': 71, 'marine': 233, 'areas': {...}, 'regions': {...}}

types = client.get_alert_types()
# -> ["Tornado Warning", "Winter Storm Warning", "Flash Flood Warning", ...]

marine_alerts = client.get_active_alerts_by_marine_region("AT")
# -> Atlantic marine alerts

all_alerts = client.get_alerts(
    area="NY",
    start="2024-01-01T00:00:00Z",
    end="2024-12-31T23:59:59Z",
    limit=100
)
# -> historical + active alerts with pagination
```

#### Radar Methods

```python
radars = client.get_radar_stations()
# -> list of all ~160 WSR-88D radar stations

radar = client.get_radar_station("KOKX")
# -> station details + RDA status + latency metrics

image_url = client.get_radar_image_url("KOKX")
# -> "https://radar.weather.gov/ridge/standard/KOKX_0.gif"
```

#### Office Methods

```python
office = client.get_office("OKX")
# -> name, address, phone, email, responsibleZones, ...

headlines = client.get_office_headlines("OKX")
# -> list of current office headlines
```

#### Zone Methods

```python
zones = client.get_zones(zone_type="forecast", area="NY")
# -> all NY forecast zones

zone = client.get_zone("forecast", "NYZ072")
# -> zone details with polygon geometry

zone_forecast = client.get_zone_forecast("NYZ072")
# -> text-based zone forecast

stations = client.get_zone_stations("NYZ072")
# -> observation stations in the zone
```

#### Product Methods

```python
products = client.get_products(product_type="AFD", office="KOKX")
# -> list of Area Forecast Discussions from NY office
# NOTE: office must be 4-letter ICAO code (e.g. "KOKX" not "OKX")

product = client.get_product("48be4b73-e2b1-49ad-a8be-f9d51272f89a")
# -> full text of product

types = client.get_product_types()
# -> list of 200+ product codes and names

latest_afd = client.get_latest_product("AFD", "OKX")
# -> most recent AFD from OKX office
```

#### Aviation Methods

```python
sigmets = client.get_sigmets()
# -> list of all active SIGMETs

sigmets = client.get_sigmets(atsu="KKCI")
# -> SIGMETs from Kansas City ARTCC

cwas = client.get_cwas("ZNY")
# -> Center Weather Advisories from NY ARTCC
```

#### Satellite Methods

```python
url = client.get_goes_satellite_url(
    satellite="GOES19",
    sector="CONUS",
    product="GEOCOLOR",
    size="625x375"
)
# -> JPEG URL (updated every ~5-15 min)

url = client.get_goes_satellite_url("GOES19", "SECTOR/NE", "GEOCOLOR", "1200x1200")
```

#### Utilities

```python
from weather_gov_client import (
    celsius_to_fahrenheit,
    pa_to_inhg,
    ms_to_mph,
    kmh_to_mph,
    format_observation
)
```

---

## Important Implementation Notes

### User-Agent Header (Required)

The NWS requires a User-Agent header identifying your application. Without it, requests may be rejected with HTTP 403:

```python
client = NWSClient(user_agent="MyWeatherApp/1.0 (contact@mycompany.com)")
```

Recommended format: `"AppName/Version (contact@email.com)"`

### Unit System

All raw API values use **SI (metric) units**:
- Temperature: degC
- Pressure: Pa (Pascals)
- Wind speed: km/h (or m/s for some fields)
- Visibility: meters
- Precipitation: mm

Use the `format_observation()` helper to convert to US customary units.

### Quality Control Codes

Observation values include a `qualityControl` field:
- `V` = Verified - valid data
- `C` = Coarse QC applied
- `S` = Screened
- `Z` = Zeroed/null - value is None (do not use)
- `O` = Outlier
- `X` = Failed QC

Always check that `value` is not `None` before using it.

### Forecast Periods

The 7-day daily forecast returns **14 periods** (2 per day: day + night).
The 7-day hourly forecast returns **up to 168 periods** (1 per hour).

### Pagination

Endpoints that return collections support `cursor`-based pagination. The cursor token is returned in the response and should be passed back to retrieve the next page. The `limit` parameter controls page size.

### Rate Limits & Caching

- The NWS does not publish official rate limits but strongly encourages caching
- Forecasts update every 1-6 hours; cache for at least 10-15 minutes
- Observations update hourly at most stations; cache for 30+ minutes
- Alerts update frequently (every 1-5 minutes during active events)
- The client caches point lookups in memory within a session

### Error Responses

The API returns structured error responses:
```json
{
  "type": "https://api.weather.gov/problems/NotFound",
  "title": "Not Found",
  "status": 404,
  "detail": "...",
  "correlationId": "abc123",
  "instance": "https://api.weather.gov/requests/abc123"
}
```

---

## NWS Office Codes Reference

Complete list of primary NWS Weather Forecast Offices (WFOs):

| Code | Location | Code | Location |
|------|----------|------|----------|
| ABQ | Albuquerque, NM | ABR | Aberdeen, SD |
| AFC | Fairbanks, AK | AFG | Fairbanks, AK |
| AKQ | Wakefield, VA | ALY | Albany, NY |
| AMA | Amarillo, TX | APX | Gaylord, MI |
| ARX | La Crosse, WI | BGM | Binghamton, NY |
| BIS | Bismarck, ND | BMX | Birmingham, AL |
| BOU | Boulder, CO | BOX | Boston, MA |
| BRO | Brownsville, TX | BTV | Burlington, VT |
| BUF | Buffalo, NY | BYZ | Billings, MT |
| CAE | Columbia, SC | CAR | Caribou, ME |
| CHS | Charleston, SC | CLE | Cleveland, OH |
| CRP | Corpus Christi, TX | CTP | State College, PA |
| CYS | Cheyenne, WY | DDC | Dodge City, KS |
| DLH | Duluth, MN | DMX | Des Moines, IA |
| DTX | Detroit, MI | DVN | Davenport, IA |
| EAX | Pleasant Hill, MO | EKA | Eureka, CA |
| EPZ | El Paso, TX | EWX | New Braunfels, TX |
| FFC | Peachtree City, GA | FGF | Grand Forks, ND |
| FGZ | Flagstaff, AZ | FSD | Sioux Falls, SD |
| FWD | Fort Worth, TX | GGW | Glasgow, MT |
| GID | Hastings, NE | GJT | Grand Junction, CO |
| GLD | Goodland, KS | GRB | Green Bay, WI |
| GRR | Grand Rapids, MI | GSP | Greenville-Spartanburg, SC |
| GYX | Portland, ME | HFO | Honolulu, HI |
| HGX | Houston/Galveston, TX | HNX | San Joaquin Valley, CA |
| HUN | Huntsville, AL | ICT | Wichita, KS |
| ILM | Wilmington, NC | ILN | Wilmington, OH |
| ILX | Lincoln, IL | IND | Indianapolis, IN |
| IWX | Northern Indiana | JAN | Jackson, MS |
| JAX | Jacksonville, FL | JKL | Jackson, KY |
| KEY | Key West, FL | LBF | North Platte, NE |
| LCH | Lake Charles, LA | LIX | New Orleans, LA |
| LKN | Elko, NV | LMK | Louisville, KY |
| LOT | Chicago, IL | LOX | Los Angeles, CA |
| LSX | St. Louis, MO | LUB | Lubbock, TX |
| LWX | Baltimore-Washington | LZK | Little Rock, AR |
| MAF | Midland-Odessa, TX | MEG | Memphis, TN |
| MFL | Miami, FL | MFR | Medford, OR |
| MHX | Newport/Morehead City, NC | MKX | Milwaukee, WI |
| MLB | Melbourne, FL | MOB | Mobile, AL |
| MPX | Twin Cities, MN | MQT | Marquette, MI |
| MRX | Knoxville/Tri Cities, TN | MSO | Missoula, MT |
| MTR | San Francisco Bay Area, CA | OAX | Omaha, NE |
| OHX | Nashville, TN | OKX | New York, NY |
| OTX | Spokane, WA | OUN | Norman, OK |
| PAH | Paducah, KY | PBZ | Pittsburgh, PA |
| PDT | Pendleton, OR | PHI | Philadelphia, PA |
| PIH | Pocatello, ID | PQR | Portland, OR |
| PSR | Phoenix, AZ | PUB | Pueblo, CO |
| RAH | Raleigh, NC | REV | Reno, NV |
| RIW | Riverton, WY | RLX | Charleston, WV |
| RNK | Blacksburg, VA | SEW | Seattle, WA |
| SGF | Springfield, MO | SGX | San Diego, CA |
| SHV | Shreveport, LA | SJT | San Angelo, TX |
| SJU | San Juan, PR | SLC | Salt Lake City, UT |
| SMX | Santa Maria, CA | STO | Sacramento, CA |
| TAE | Tallahassee, FL | TAX | Chico, CA |
| TBW | Tampa Bay Area, FL | TFX | Great Falls, MT |
| TOP | Topeka, KS | TSA | Tulsa, OK |
| TWC | Tucson, AZ | UNR | Rapid City, SD |
| VEF | Las Vegas, NV |  |  |

---

## Real-World Examples

### Get weather for a US city

```python
from weather_gov_client import NWSClient, format_observation

client = NWSClient("MyApp/1.0 (me@example.com)")

# Los Angeles
daily, hourly = client.get_forecast_by_location(34.0522, -118.2437)
print(f"Today in LA: {daily['periods'][0]['shortForecast']}")
print(f"High: {daily['periods'][0]['temperature']}°F")

# Chicago
point = client.get_point(41.8781, -87.6298)
print(f"Chicago WFO: {point['gridId']}")  # LOT

# Miami
daily, hourly = client.get_forecast_by_location(25.7617, -80.1918)
```

### Monitor severe weather

```python
# Get all active tornado/severe thunderstorm warnings
severe = client.get_active_alerts(severity="Extreme")
for alert in severe.get('features', []):
    p = alert['properties']
    print(f"[{p['severity']}] {p['event']}: {p['areaDesc']}")
    print(f"  Expires: {p['expires']}")
    print(f"  {p.get('headline', '')}")

# Watch for specific states
states_to_watch = ["TX", "OK", "KS", "MO"]
for state in states_to_watch:
    alerts = client.get_active_alerts(area=state)
    if alerts.get('features'):
        print(f"Active alerts in {state}: {len(alerts['features'])}")
```

### Aviation weather

```python
# Get SIGMETs active over the US
sigmets = client.get_sigmets()
print(f"Active SIGMETs: {len(sigmets)}")

# Get TAF for JFK airport
taf = client.get_station_tafs("KJFK")

# Get Area Forecast Discussion for flight planning
afd = client.get_latest_product("AFD", "OKX")  # New York region
print(afd.get('productText', '')[:1000])
```

### Marine weather

```python
# Atlantic marine alerts
marine = client.get_active_alerts_by_marine_region("AT")
print(f"Atlantic marine alerts: {len(marine.get('features', []))}")

# Gulf of Mexico
gulf = client.get_active_alerts_by_marine_region("GM")
```

### Weather data pipeline

```python
import json
from weather_gov_client import NWSClient, format_observation
from datetime import datetime, timezone

client = NWSClient("DataPipeline/1.0 (ops@mycompany.com)")

def get_weather_snapshot(lat: float, lon: float) -> dict:
    """Get a complete weather snapshot for any US location."""
    point = client.get_point(lat, lon)
    wfo, gx, gy = point['gridId'], point['gridX'], point['gridY']

    # Get forecast
    daily = client.get_forecast(wfo, gx, gy)
    hourly = client.get_forecast_hourly(wfo, gx, gy)

    # Get current conditions from nearest station
    stations = client.get_point_stations(lat, lon)
    obs = None
    if stations:
        sid = stations[0]['properties']['stationIdentifier']
        obs_raw = client.get_station_observation_latest(sid)
        obs = format_observation(obs_raw)

    # Get active alerts
    alerts_data = client.get_active_alerts(
        point=f"{lat},{lon}"
    )

    return {
        "location": {
            "lat": lat, "lon": lon,
            "city": point['relativeLocation']['properties']['city'],
            "state": point['relativeLocation']['properties']['state'],
            "timezone": point['timeZone'],
        },
        "current": obs,
        "forecast_7day": daily['periods'],
        "forecast_hourly_6h": hourly['periods'][:6],
        "active_alerts": len(alerts_data.get('features', [])),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

snapshot = get_weather_snapshot(40.7128, -74.0060)
print(json.dumps(snapshot, indent=2, default=str))
```

---

## API Response Formats

All API responses use **GeoJSON** format wrapped with **JSON-LD context**:

```json
{
  "@context": [
    "https://geojson.org/geojson-ld/geojson-context.jsonld",
    { "@version": "1.1", "wx": "https://api.weather.gov/ontology#" }
  ],
  "type": "FeatureCollection",
  "features": [...]
}
```

Scalar resources (e.g. a single office) use Schema.org vocabulary:
```json
{
  "@context": { "@version": "1.1", "@vocab": "https://schema.org/" },
  "@type": "GovernmentOrganization",
  "id": "...",
  ...
}
```

Unit codes follow **WMO (World Meteorological Organization)** standards:
- `wmoUnit:degC` - degrees Celsius
- `wmoUnit:km_h-1` - kilometers per hour
- `wmoUnit:Pa` - Pascals
- `wmoUnit:m` - meters
- `wmoUnit:percent` - percentage
- `wmoUnit:degree_(angle)` - angular degrees

---

## Data Freshness

| Data Type | Update Frequency |
|-----------|-----------------|
| Forecasts (daily) | Every 3-6 hours |
| Forecasts (hourly) | Every 1-3 hours |
| Observations | Every 20-60 minutes |
| Active alerts | Every 1-5 minutes |
| Radar data | Every 4-10 minutes |
| GOES satellite | Every 5-15 minutes |
| TAFs | Every 6 hours |
| Gridded data | Every 1-3 hours |
| SIGMETs | As issued |

---

## Discovered During Reverse Engineering

The following was discovered through browser network traffic interception on `forecast.weather.gov`:

1. **ArcGIS integration:** The new forecast.weather.gov uses ArcGIS basemap tiles for map displays (requires ArcGIS tokens, not replicable without key)

2. **DualImage.php:** Legacy endpoint at `forecast.weather.gov` combining two weather icons:
   ```
   https://forecast.weather.gov/DualImage.php?i={cond1}&j={cond2}&ip={pct1}&jp={pct2}
   ```

3. **DAP Analytics:** The site uses `dap.digitalgov.gov` (Federal Digital Analytics Program) for analytics

4. **GOES16/GOES19 redirect:** `cdn.star.nesdis.noaa.gov/GOES16/...` automatically redirects to `GOES19` (the current satellite)

5. **graphical.weather.gov thumbnails:** The forecast page loads regional thumbnail images:
   ```
   https://graphical.weather.gov/images/thumbnail/latest_{product}_{region}_thumbnail.png
   ```
