# AerisWeather / Xweather API - Reverse Engineering Report & Python Client

## Summary

AerisWeather has rebranded to **Xweather** (https://www.xweather.com). The
underlying weather API is the same product, now served at:

```
https://data.api.xweather.com/
```

This client was reverse-engineered from the public Xweather documentation at
https://www.xweather.com/docs/weather-api using network interception and
systematic extraction of the Next.js documentation site's embedded JSON data.

---

## Authentication

Every API request requires **two query parameters**:

| Parameter       | Description                                          |
|----------------|------------------------------------------------------|
| `client_id`     | Your application's Client ID                        |
| `client_secret` | Your application's Secret Key                       |

Credentials are obtained by registering an application in the Xweather
account portal. Each credential is scoped to a **namespace**:
- Web apps: top-level domain (e.g., `myapp.com`)
- iOS/Android: reverse-DNS bundle ID (e.g., `com.mycompany.myapp`)

### Example authenticated request:
```
GET https://data.api.xweather.com/observations/seattle,wa?client_id=YOUR_ID&client_secret=YOUR_SECRET
```

---

## API Structure

### URL Pattern
```
https://data.api.xweather.com/{endpoint}/{action}?{params}
```

For sub-path endpoints:
```
https://data.api.xweather.com/{endpoint}/{sub-path}/{action}?{params}
```

For parameterized routes (indices, impacts):
```
https://data.api.xweather.com/indices/{type}/{action}?{params}
https://data.api.xweather.com/impacts/{activity}/{action}?{params}
```

### Actions (common across endpoints)
| Action     | Description                                                    |
|-----------|----------------------------------------------------------------|
| `:id`      | Fetch data for a specific location (city, lat/lon, postal code, station ID) |
| `closest`  | Return results ordered nearest-to-farthest from a point       |
| `within`   | Return all results inside a circle or polygon                 |
| `search`   | Full-text / attribute search across the dataset              |
| `route`    | Fetch data points along a custom route (semicolon-delimited coords) |
| `affects`  | Find events currently affecting a location                    |
| `contains` | Find polygons that contain a given point                      |
| `:all`     | Return all records (e.g., all active tropical cyclones)       |

### Common Query Parameters
| Parameter    | Description                                                             |
|-------------|-------------------------------------------------------------------------|
| `p`          | Location: city name, `lat,lon`, postal code, station ID, ICAO         |
| `limit`      | Max primary results (default: 1 for most endpoints)                    |
| `plimit`     | Max sub-results (e.g., periods in forecast)                            |
| `radius`     | Search radius with unit, e.g. `50miles` or `100km`                    |
| `minradius`  | Minimum search radius (donut query)                                    |
| `mindist`    | Minimum distance from the queried point                               |
| `filter`     | Comma-separated filter flags (endpoint-specific)                       |
| `query`      | Attribute query, e.g. `state:mn,temp:-999`                            |
| `sort`       | Sort field with direction, e.g. `temp:-1` (desc) or `temp` (asc)     |
| `skip`       | Skip N primary results (pagination)                                    |
| `fields`     | Comma-separated dot-notation fields to include in response             |
| `from`       | Start datetime (ISO-8601 or relative like `-24hours`)                  |
| `to`         | End datetime (ISO-8601 or relative like `+6hours`)                     |
| `for`        | Single point-in-time datetime                                          |
| `format`     | Response format: `json` (default), `geojson`, `csv`, `tsv`            |
| `lang`       | Language for alert/description text                                    |

### Query Expression Syntax
```
# Exact match:       field:value
# Not equal:         field:!value
# Starts with:       field:^prefix
# Numeric range:     field:min:max
# Numeric >=:        field:value
# Numeric <=:        field:0:max
# Null check:        field:NULL
# Not null:          field:!NULL
# AND (comma):       state:mn,temp:-999
# OR (semicolon):    name:seattle;name:austin
```

### Sort Expression Syntax
```
# Ascending (default):   sort=temp
# Descending:            sort=temp:-1
# Disable sort:          sort=temp:0
# Multi-field:           sort=state,temp:-1
```

### Response Structure
```json
{
  "success": true,
  "error": null,
  "warning": null,
  "response": { ... }   // object for :id action
}
```
```json
{
  "success": true,
  "error": null,
  "warning": null,
  "response": [ ... ]   // array for other actions
}
```

### HTTP Status Codes
| Code | Meaning                                      |
|------|----------------------------------------------|
| 200  | Success                                      |
| 401  | Invalid client_id or client_secret           |
| 404  | Endpoint or path not found                   |
| 429  | Rate limit exceeded (per-minute or period)   |
| 5xx  | Server-side error                            |

### API Error Codes
| Code                    | Description                                           |
|------------------------|-------------------------------------------------------|
| `invalid_credentials`   | Bad client_id or secret                              |
| `invalid_location`      | Location not found                                   |
| `invalid_query`         | Malformed query expression                           |
| `invalid_action`        | Action not supported for this endpoint              |
| `invalid_id`            | ID format invalid                                    |
| `invalid_coords`        | Coordinate format invalid                            |
| `api_limit_reached`     | Daily access limit exhausted                         |
| `rate_limited`          | Per-minute rate limit hit                            |
| `subscription_exceeded` | Subscription period limit reached                   |
| `access_restricted`     | Endpoint not available on your subscription         |
| `restricted_domain`     | Request from unauthorized domain/bundle ID          |
| `internal_error`        | Xweather server error                               |

---

## All Discovered Endpoints (55 total)

### Weather Observations

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Observations | `/observations` | 1–60+ min | `metar`, `allstations`, `pws`, `madis`, `hfmetar`, `ausbom`, `envca`, `wxrain`, `wxsnow`, `wxice`, `wxfog`, `qcok`, `strict` |
| Observations Archive | `/observations/archive` | – | `allstations`, `official`, `pws`, `mesonet`, `hasprecip`, `hassky` |
| Observations Summary | `/observations/summary` | – | `allstations`, `metar`, `pws`, `hfmetar`, `hasprecip`, `hassky`, `qcok`, `strict` |

### Forecasts & Conditions

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Forecasts | `/forecasts` | 1 hr | `day`, `daynight`, `mdnt2mdnt`, `#hr` (e.g. `1hr`, `3hr`), `#min` (e.g. `30min`) |
| Conditions | `/conditions` | Near real-time | `minutelyprecip`, `15min`, `1hr` |
| Conditions Summary | `/conditions/summary` | – | `day`, `#hr` |
| Xcast Forecasts | `/xcast/forecasts` | – | `1hr`, `10min` |

### Weather Alerts

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Alerts | `/alerts` | Near real-time | `warning`, `watch`, `advisory`, `outlook`, `statement`, `severe`, `flood`, `tropical`, `winter`, `fire`, `marine`, `geo`, `all` |
| Alerts Summary | `/alerts/summary` | – | `warning`, `watch`, `advisory`, `flood`, `severe`, `tropical`, `winter`, `marine` |

### Air Quality

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Air Quality | `/airquality` | 1 hr | `airnow`, `cai`, `caqi`, `china`, `eaqi`, `germany`, `india`, `uk` |
| Air Quality Forecasts | `/airquality/forecasts` | – | `day`, `daynight`, `#hr`, AQI standard filters |
| Air Quality Archive | `/airquality/archive` | – | `#hr`, AQI standard filters |
| Air Quality Index | `/airquality/index` | – | – |

### Severe Weather

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Storm Cells | `/stormcells` | Near real-time | `hail`, `rotating`, `tornado`, `threat`, `rainmoderate`, `rainheavy`, `rainintense`, `conus` |
| Storm Cells Summary | `/stormcells/summary` | – | same as storm cells + `geo`, `noforecast` |
| Storm Reports | `/stormreports` | 15 min | `avalanche`, `blizzard`, `dust`, `flood`, `fog`, `ice`, `hail`, `lightning`, `marine`, `rain`, `snow`, `tornado`, `wind`, `winter`, `wx` |
| Storm Reports Summary | `/stormreports/summary` | – | same as storm reports |
| Convective Outlook | `/convective/outlook` | – | `cat`, `prob`, `torn`, `xtorn`, `sigtorn`, `hail`, `xhail`, `sighail`, `wind`, `xwind`, `sigwind` |

### Lightning

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Lightning | `/lightning` | Real-time | `cg` (default), `all` |
| Lightning Summary | `/lightning/summary` | – | `cg`, `all`, `negative`, `positive` |
| Lightning Archive | `/lightning/archive` | – | `cg`, `ic`, `all` |
| Lightning Analytics | `/lightning/analytics` | – | `cg`, `all`, `ellipse50`, `ellipse80`, `ellipse90`, `ellipse99` |
| Lightning Threats | `/lightning/threats` | – | `severe`, `notsevere` |
| Lightning Flash | `/lightning/flash` | – | – |

### Hail

| Endpoint | Route | Key Filters |
|---------|-------|-------------|
| Hail Archive | `/hail/archive` | – |
| Hail Threats | `/hail/threats` | `severe`, `notsevere`, `test` |

### Fires & Droughts

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Fires | `/fires` | Near real-time | `geo`, `hasperimeter`, `hasnoperimeter` |
| Fires Outlook | `/fires/outlook` | – | `firewx`, `dryltg`, `elevated`, `critical`, `extreme`, `isodryt`, `sctdryt`, `day1`, `day2`, `day3`, `all` |
| Droughts Monitor | `/droughts/monitor` | – | `all`, `d0`, `d1`, `d2`, `d3`, `d4` |

### Tropical & Geological

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Tropical Cyclones | `/tropicalcyclones` | 6 hrs | `atlantic`, `eastpacific`, `centralpacific`, `westpacific`, `pacific`, `indian` |
| Tropical Cyclones Archive | `/tropicalcyclones/archive` | – | same basin filters |
| Earthquakes | `/earthquakes` | Near real-time | `mini`, `minor`, `light`, `moderate`, `strong`, `major`, `great`, `shallow` |

### Maritime & Tides

| Endpoint | Route | Update | Key Filters |
|---------|-------|--------|-------------|
| Maritime | `/maritime` | – | `#hr` |
| Maritime Archive | `/maritime/archive` | – | `#hr` |
| Tides | `/tides` | – | `highlow`, `high`, `low` |
| Tides Stations | `/tides/stations` | – | – |
| Rivers | `/rivers` | – | `inservice`, `outofservice`, `notdefined`, `lowthreshold`, `noflooding`, `action`, `flood`, `minor`, `moderate`, `major` |
| River Gauges | `/rivers/gauges` | – | `impacts`, `recentcrests`, `historiccrests`, `lowwaterrecords` |

### Climate & Astronomy

| Endpoint | Route | Key Filters |
|---------|-------|-------------|
| Normals | `/normals` | `daily`, `monthly`, `annual`, `hastemp`, `hasprecip`, `hassnow` |
| Normals Stations | `/normals/stations` | `hastemp`, `hasprcp`, `hassnow` |
| Sun Moon | `/sunmoon` | `sun`, `twilight`, `moon`, `moonphase` |
| Moon Phases | `/sunmoon/moonphases` | `new`, `first`, `full`, `third` |

### Road Weather

| Endpoint | Route | Key Filters |
|---------|-------|-------------|
| Road Weather | `/roadweather` | `primary`, `secondary`, `bridge`, `noroadcheck` |
| Road Weather Conditions | `/roadweather/conditions` | same |
| Road Weather Analytics | `/roadweather/analytics` | same + `addweather` |

### Geographic Data

| Endpoint | Route | Key Filters |
|---------|-------|-------------|
| Places | `/places` | `airport`, `county`, `lake`, `park`, `summit`, and many POI types |
| Places Airports | `/places/airports` | `smallairport`, `medairport`, `largeairport`, `heliport`, `balloonport`, `sea`, `all`, `closed` |
| Places Postal Codes | `/places/postalcodes` | `us`, `ca`, `standard` |
| Countries | `/countries` | – |

### Specialty / Business Intelligence

| Endpoint | Route | Types/Activities |
|---------|-------|-----------------|
| Indices | `/indices/:type` | `arthritis`, `coldflu`, `migraine`, `sinus`, `outdoor`, `golf`, `biking`, `swimming`, `campfire`, `beeactive` |
| Impacts | `/impacts/:activity` | `general`, `trucking`, `smallcraft`, `largevessel` |
| Threats | `/threats` | – |
| Phrases Summary | `/phrases/summary` | `metar`, `pws`, `mesonet`, `allstations` |
| Energy Farm | `/energy/farm` | – |
| Renewables Irradiance Archive | `/renewables/irradiance/archive` | `#hr` |

### Batch Requests

```
GET /batch?requests=/observations/seattle%2Cwa,/forecasts/seattle%2Cwa,/alerts/seattle%2Cwa
          &client_id=...&client_secret=...
```

Or with a shared location:
```
GET /batch/seattle,wa?requests=/observations,/forecasts,/alerts
    &client_id=...&client_secret=...
```

- Maximum **31** sub-requests per batch call
- Each sub-request counts as a separate API access
- Per-request params can be URL-encoded inline: `/forecasts%3Ffilter=1hr`

---

## Python Client Usage

### Installation

The client requires only the `requests` library:

```bash
pip install requests
```

### Initialization

```python
from aerisweather_client import AerisClient

client = AerisClient(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
)
```

Or via environment variables:

```bash
export AERIS_CLIENT_ID="your_id"
export AERIS_CLIENT_SECRET="your_secret"
```

```python
import os
from aerisweather_client import AerisClient

client = AerisClient(
    client_id=os.environ["AERIS_CLIENT_ID"],
    client_secret=os.environ["AERIS_CLIENT_SECRET"],
)
```

### Examples

#### Current observations
```python
obs = client.observations.id("seattle,wa")
ob = obs["response"]["ob"]
print(f"{ob['tempF']}°F, {ob['weather']}")
```

#### 7-day daily forecast
```python
fcst = client.forecasts.daily("chicago,il", days=7)
for period in fcst["response"][0]["periods"]:
    print(f"{period['dateTimeISO'][:10]}: High {period['maxTempF']}°F / Low {period['minTempF']}°F")
```

#### Hourly forecast
```python
fcst = client.forecasts.hourly("new york,ny", hours=24)
```

#### Active severe weather alerts
```python
alerts = client.alerts.active("kansas city,mo", filter="severe")
for alert in alerts.get("response", []):
    print(alert["details"]["name"])
```

#### All active alerts with geographic polygons
```python
alerts = client.alerts.id("florida", filter="all,geo", limit=20)
```

#### Air quality
```python
aq = client.airquality.id("los angeles,ca")
aqi = aq["response"]["periods"][0]
print(f"AQI: {aqi['aqi']} ({aqi['category']}) - {aqi['dominant']}")
```

#### Storm cells near a location
```python
cells = client.stormcells.closest("oklahoma city,ok", radius="100miles", filter="tornado,hail")
for cell in cells.get("response", []):
    print(f"  {cell.get('id')}: {cell.get('traits', {})}")
```

#### Lightning within 50 miles
```python
lightning = client.lightning.within("dallas,tx", radius="50miles", filter="cg", limit=100)
```

#### Tropical cyclones (all active globally)
```python
tc = client.tropicalcyclones.all_active()
for storm in tc.get("response", []):
    p = storm["profile"]
    print(f"{p['name']} ({p['basin']}): Cat {p.get('cat')}, {p.get('windMPH')} mph")
```

#### Historical observations
```python
archive = client.observations_archive.id("KORD", from_dt="-7days", to="now", filter="official")
```

#### Closest 5 observations to a postal code
```python
obs = client.observations.closest("98109", radius="30miles", limit=5, filter="allstations")
```

#### Search observations by attribute
```python
# Warmest US observation
warmest = client.observations.search(query="country:us,temp:-999", sort="temp:-1", limit=1)
# All tornado-warned storm cells
tornado_cells = client.stormcells.search(query="tvs:1")
```

#### Weather indices
```python
idx = client.indices.id("minneapolis,mn", index_type="arthritis")
idx_route = client.indices.route(["44.97,-93.26", "41.88,-87.63"], index_type="golf", filter="day")
```

#### Business impact scores
```python
impact = client.impacts.id("chicago,il", activity="trucking")
```

#### Road weather conditions
```python
rw = client.roadweather.id("denver,co", filter="primary,bridge")
```

#### Maritime wave data
```python
marine = client.maritime.id("25.0,-90.0", filter="3hr")
```

#### Tides
```python
tides = client.tides.id("san francisco,ca", filter="highlow", limit=10)
```

#### Sun/moon data
```python
sun = client.sunmoon.id("seattle,wa", from_dt="2025-01-01", to="2025-01-31", filter="sun")
moon = client.moonphases.id("seattle,wa", from_dt="2025-01-01", to="2025-12-31")
```

#### Climate normals
```python
normals = client.normals.id("minneapolis,mn", filter="monthly")
```

#### Drought monitor
```python
drought = client.droughts_monitor.id("california", filter="d3")
drought_affects = client.droughts_monitor.search(filter="d4", limit=20)
```

#### Batch request (multiple endpoints, one call)
```python
batch = client.batch(
    requests_param=["/observations", "/forecasts", "/alerts%3Ffilter=all"],
    place="seattle,wa",
    limit=1,
)
for result in batch.get("response", []):
    print(f"{result['id']}: success={result['success']}")
```

#### Fields filtering (reduce response size)
```python
obs = client.observations.id("seattle,wa", fields="ob.tempF,ob.weather,ob.icon,loc.long,loc.lat")
fcst = client.forecasts.id("chicago,il", fields="periods.dateTimeISO,periods.maxTempF,periods.minTempF")
```

#### Error handling
```python
from aerisweather_client import AerisClient, AerisError
import requests

client = AerisClient(client_id="...", client_secret="...")

try:
    obs = client.observations.id("nowhere,xx")
except AerisError as e:
    print(f"API error: {e.code} - {e.description}")
except requests.HTTPError as e:
    print(f"HTTP error: {e.response.status_code}")
except requests.Timeout:
    print("Request timed out")
```

---

## Request Cost Model

The API tracks usage cost via response headers. Each API access cost is
determined by three multipliers:

1. **Endpoint multiplier** – varies by data type/tier
2. **Spatial multiplier** – larger geographic queries cost more
3. **Temporal multiplier** – longer time ranges cost more

The batch endpoint counts each sub-request as a separate API access.

---

## Rate Limiting

- Per-minute rate limits depend on subscription tier
- Daily access limits reset at 00:00 UTC
- Subscription period limits are enforced separately
- HTTP 429 is returned when any limit is exceeded

---

## Output Formats

All endpoints support the `format` parameter:

| Format   | Description                                                        |
|---------|---------------------------------------------------------------------|
| `json`   | Default JSON (structured objects)                                  |
| `geojson`| GeoJSON with geometry for spatial data                            |
| `csv`    | Comma-separated values; use `fields` param to control columns     |
| `tsv`    | Tab-separated values                                               |

For CSV/TSV, use the `fields` parameter to specify columns:
```
GET /observations?format=csv&fields=ob.windMPH,ob.tempF,ob.humidity,id,obDateTime
```

---

## Data Sources (selected)

| Endpoint | Primary Data Source |
|---------|---------------------|
| Observations | ASOS/METAR, PWS (PWSweather.com), MADIS, AUSBOM, Environment Canada |
| Forecasts | NWS MOS, proprietary models |
| Conditions | Proprietary interpolation (obs + radar + NWP blended) |
| Alerts | NWS, Environment Canada, Meteoalarm (EU) |
| Lightning | Vaisala Xweather global lightning network |
| Storm Cells | NWS NEXRAD Level III products |
| Storm Reports | NWS Local Storm Reports (LSRs) + spotter networks |
| Tropical Cyclones | NHC, JTWC, RSMC advisories |
| Air Quality | EPA AirNow, CPCB India, various national agencies |
| Fires | NOAA VIIRS/MODIS satellite hotspots + incident reports |
| Earthquakes | USGS + global seismic networks |
| Tides | NOAA CO-OPS tidal prediction engine |
| Normals | WMO 30-year climate normals (1991–2020) |
| Rivers | NOAA AHPS |

---

## Notes

- The legacy domain `api.aerisapi.com` has been replaced by `data.api.xweather.com`
- Service status page: https://status.aerisweather.com/
- API documentation: https://www.xweather.com/docs/weather-api
- Support tickets: https://www.xweather.com/support/ticket
