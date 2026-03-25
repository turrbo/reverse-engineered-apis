# Meteoblue Internal API — Reverse Engineering Report

**Date:** 2026-03-25
**Method:** Browser network interception + HTML/JS source analysis
**Tool:** curl, JS analysis of `main.js`, `search_55e8bd.js`, `maps-plugin.js`

---

## Summary

Meteoblue's website (`www.meteoblue.com`) exposes several internal APIs used to power its weather forecast visualizations. These APIs are not publicly documented but can be accessed with the keys discovered via JS/HTML analysis.

---

## Discovered API Endpoints

### 1. Location Search API

| Property | Value |
|----------|-------|
| Base URL | `https://locationsearch.meteoblue.com` |
| Endpoint | `/en/server/search/query3` |
| Method | GET (JSONP-capable) |
| Auth | `apikey=LYnNIfRrK2XWTtzw` |
| Source | Extracted from `search_55e8bd.js` |

**Request Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | string | Location name, lat/lon (e.g. "47.56 7.59"), IATA code |
| `apikey` | string | `LYnNIfRrK2XWTtzw` |
| `page` | int | Page number (1-based) |
| `itemsPerPage` | int | Results per page (max 50) |
| `orderBy` | string | Sort order (e.g. "name ASC", "distance DESC") |

**Example Request:**
```
GET https://locationsearch.meteoblue.com/en/server/search/query3?query=london&apikey=LYnNIfRrK2XWTtzw&page=1&itemsPerPage=10
```

**Example Response (truncated):**
```json
{
  "lat": 39.04372,
  "orderBy": "ranker DESC",
  "type": "name",
  "query": "london",
  "count": 300,
  "itemsPerPage": 10,
  "currentPage": 1,
  "pages": 30,
  "results": [
    {
      "id": 2643743,
      "name": "London",
      "iso2": "GB",
      "lat": 51.5085,
      "lon": -0.12574,
      "asl": 11,
      "admin1": "England",
      "featureClass": "P",
      "featureCode": "PPLC",
      "population": 8961989,
      "iata": "LON",
      "icao": "",
      "url": "london_united-kingdom_2643743",
      "distance": 5917.3
    }
  ]
}
```

The `url` field gives you the location slug for all other Meteoblue URLs.

---

### 2. Meteogram Image API

| Property | Value |
|----------|-------|
| Base URL | `https://my.meteoblue.com` |
| Endpoint | `/images/meteogram` (and variants) |
| Method | GET |
| Auth | `apikey=n4UGDLso3gE6m2YI` + HMAC `sig` |
| Source | Extracted from HTML page source (`data-href` attributes) |

#### Available Endpoints

| Endpoint | Description | Page Path |
|----------|-------------|-----------|
| `/images/meteogram` | Standard 5-day meteogram | `/en/weather/forecast/meteogramweb/{slug}` |
| `/images/meteogram_multimodel` | Multi-model comparison | `/en/weather/forecast/multimodel/{slug}` |
| `/images/meteogram_agro` | Agriculture meteogram | `/en/weather/agriculture/meteogramagro/{slug}` |
| `/images/meteogram_air` | Aviation AIR meteogram | `/en/weather/aviation/air/{slug}` |
| `/images/meteogram_snow` | Snow conditions | `/en/weather/outdoorsports/snow/{slug}` |
| `/images/meteogram_sea_7day` | Sea & surf forecast | `/en/weather/outdoorsports/seasurf/{slug}` |

#### Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `lat` | float | Latitude |
| `lon` | float | Longitude |
| `asl` | int | Altitude above sea level (meters) |
| `tz` | string | Timezone (e.g. "America/New_York", "Europe/Zurich") |
| `iso2` | string | Country ISO2 code |
| `location_name` | string | Display name |
| `apikey` | string | `n4UGDLso3gE6m2YI` |
| `lang` | string | Language (en, de, fr, etc.) |
| `format` | string | `highcharts` (JSON data) or `png` (image) |
| `temperature_units` | string | `C` or `F` |
| `windspeed_units` | string | `km/h`, `mph`, `m/s` |
| `precipitation_units` | string | `mm` or `inch` |
| `darkmode` | bool | `true` or `false` |
| `dpi` | int | Image DPI (72 or 100) |
| `ts` | int | Unix timestamp (generated server-side) |
| `sig` | string | HMAC-MD5 signature (generated server-side) |

For `meteogram_multimodel`, additional parameters:
| Parameter | Type | Description |
|-----------|------|-------------|
| `forecast_days` | int | 3, 5, or 7 |
| `domains` | string[] | Model IDs (repeatable parameter) |

#### Signature Mechanism

The `sig` parameter is computed as:
```
sig = MD5(url_without_sig + "&secrect=" + SERVER_SECRET)
```

The server secret is **not exposed** client-side. The signature is generated server-side when rendering HTML pages. The strategy to bypass this:

1. Fetch the HTML page for the forecast type you want
2. Extract the `data-href="//my.meteoblue.com/images/..."` URL
3. Use that URL directly (the `ts` and `sig` are already baked in)
4. Sigs are time-limited — fetch fresh pages when needed

The `ts` (Unix timestamp) in URLs appears to be valid for at least ~60 seconds.

#### Example — Standard Meteogram (Highcharts JSON)

Scraped URL structure:
```
https://my.meteoblue.com/images/meteogram?temperature_units=C&windspeed_units=km%2Fh&precipitation_units=mm&darkmode=false&iso2=gb&lat=51.5085&lon=-0.12574&asl=11&tz=Europe%2FLondon&dpi=72&apikey=n4UGDLso3gE6m2YI&lang=en&location_name=London&format=highcharts&ts=TIMESTAMP&sig=HEXDIGEST
```

Response is Highcharts chart configuration JSON with embedded series data.

#### Example — MultiModel (Highcharts JSON)

```
https://my.meteoblue.com/images/meteogram_multimodel?temperature_units=C&windspeed_units=km%2Fh&precipitation_units=mm&darkmode=false&iso2=gb&lat=51.5085&lon=-0.12574&asl=11&tz=Europe%2FLondon&forecast_days=3&apikey=n4UGDLso3gE6m2YI&lang=en&location_name=London&ts=TIMESTAMP&format=highcharts&domains=IFS025&domains=ICON&domains=GFS05&domains=NAM12&domains=NAM5&domains=NAM3&domains=HRRR&domains=MFGLOBAL&domains=UMGLOBAL10&domains=GEM15&domains=GEM2&domains=NBM&domains=AIFS025&domains=IFSHRES&domains=NEMSGLOBAL&domains=NEMSGLOBAL_E&sig=HEXDIGEST
```

---

### 3. Dataset Query API (Historical + Forecast)

| Property | Value |
|----------|-------|
| Base URL | `https://my.meteoblue.com` |
| Endpoint | `/dataset/query` |
| Method | GET |
| Auth | `apikey=5838a18e295d` + `ts` + `sig` (scraped from archive page) |
| Source | Extracted from `/en/weather/archive/export` page |

This is the most powerful endpoint — it supports querying both historical reanalysis data and forecast data across many variables and locations.

#### Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `json` | string | URL-encoded JSON query body (see below) |
| `apikey` | string | `5838a18e295d` |
| `ts` | int | Unix timestamp (from scraped sig) |
| `sig` | string | Signature (from scraped page) |

#### Query JSON Structure

```json
{
  "units": {
    "temperature": "CELSIUS",
    "velocity": "KILOMETER_PER_HOUR",
    "length": "metric",
    "energy": "watts"
  },
  "geometry": {
    "type": "MultiPoint",
    "coordinates": [[lon, lat, asl]],
    "locationNames": ["LocationName"]
  },
  "format": "highcharts",
  "timeIntervals": ["2024-01-01T+00:00/2024-12-31T+00:00"],
  "timeIntervalsAlignment": "none",
  "queries": [
    {
      "domain": "ERA5T",
      "timeResolution": "daily",
      "codes": [
        {"code": 11, "level": "2 m elevation corrected"},
        {"code": 61, "level": "sfc"}
      ]
    }
  ]
}
```

#### Weather Variable Codes

| Code | Variable |
|------|----------|
| 11 | Temperature [2 m elevation corrected] |
| 12 | Dew point [2 m] |
| 13 | Apparent temperature |
| 52 | Relative humidity [2 m] |
| 61 | Precipitation amount |
| 71 | Snowfall amount |
| 72 | Snow depth |
| 201 | Wind speed [10 m] |
| 202 | Wind direction [10 m] |
| 203 | Wind gusts [10 m] |
| 111 | Total cloud cover |
| 117 | Low cloud cover |
| 118 | Mid cloud cover |
| 119 | High cloud cover |
| 401 | Solar radiation (GHI) |
| 402 | Direct radiation |
| 403 | Diffuse radiation |
| 120 | Pressure [mean sea level] |
| 500 | Evapotranspiration |
| 501 | Potential evapotranspiration |

#### Temporal Resolutions
- `hourly` — raw hourly data
- `daily` — daily aggregates
- `monthly` — monthly aggregates
- `yearly` — annual aggregates

#### Domains (Weather Models/Reanalysis)
- `ERA5T` — ERA5 reanalysis (1940–present, 8-day delay) ← recommended for historical
- `IFS025` — ECMWF IFS (global forecast model)
- `GFS05` — NOAA GFS 0.5° (global)
- `ICON` — DWD ICON (Germany)
- `HRRR` — NOAA HRRR 3km (USA, high-res)
- `NAM12`, `NAM5`, `NAM3` — NOAA NAM models
- `GEM15`, `GEM2` — Environment Canada GEM
- `MFGLOBAL` — Météo-France Global
- `UMGLOBAL10` — UK Met Office UM 10km
- `AIFS025` — ECMWF AI Forecast System

---

### 4. Maps Inventory API

| Property | Value |
|----------|-------|
| Base URL | `https://maps-api.meteoblue.com` |
| Endpoint | `/v1/map/inventory/filter` |
| Method | GET |
| Auth | None required for `internal=true` access |

#### Request Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `maps` | comma-separated IDs | Filter to specific maps |
| `lang` | `en` | Language |
| `temperatureUnit` | `°C` or `°F` | Temperature unit for color tables |
| `lengthUnit` | `metric` or `imperial` | Length unit |
| `internal` | `true` | Include internal/website-only maps |
| `enableOpenlayersLicensing` | `true` | Enable OpenLayers tile licensing |

**Example:**
```
GET https://maps-api.meteoblue.com/v1/map/inventory/filter?maps=satellite,obsTemperature,obsPrecipitation,radar&lang=en&internal=true
```

**Response Structure:**
```json
{
  "colorTables": {...},
  "units": {...},
  "attribution": "...",
  "overlays": [...],
  "categories": [
    {
      "name": "",
      "maps": [
        {
          "id": "satellite",
          "name": "Satellite",
          "baseStyle": "https://maps-api-cdn.meteoblue.com/v1/json/...",
          "sources": [{"tiles": ["https://..."]}],
          ...
        }
      ]
    }
  ]
}
```

---

### 5. Map Tiles API

| Property | Value |
|----------|-------|
| Base URL | `https://maptiles.meteoblue.com` |
| Auth | `apikey=1iw4Jq5NZK60Ig7O` |
| Source | Extracted from `maps-plugin.js` |

#### Available Tile Sets

| URL Template | Description |
|-------------|-------------|
| `/styles/terrain2/{z}/{x}/{y}.png?apikey=...` | Terrain base map |
| `/data/precalculatedCityTiles2/{z}/{x}/{y}.png?apikey=...` | City overlay |
| `/data/hillshades/{z}/{x}/{y}.png?apikey=...` | Hillshading |

Weather forecast tiles (temperature, precipitation, wind, etc.) are served via Mapbox GL sources defined in the maps inventory. Tile URLs have placeholders:
- `{timestamp}` — ISO timestamp of the forecast step
- `{domain}` — Weather model ID
- `{level}` — Vertical level
- `{z}/{x}/{y}` — Tile coordinates

---

### 6. User Favourites API

| Property | Value |
|----------|-------|
| Base URL | `https://www.meteoblue.com` |
| Auth | Session cookie (requires login) |

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/user/favourite/read` | GET | List favourites |
| `/user/favourite/create` | POST | Add favourite |
| `/user/favourite/delete` | POST | Remove favourite |

---

### 7. Mapbox GL Style / CDN

| Property | Value |
|----------|-------|
| Base URL | `https://maps-api-cdn.meteoblue.com` |
| Endpoint | `/v1/json/{style}?apikey={key}&lang={lang}&internal=true` |
| Key | `1iw4Jq5NZK60Ig7O` |

Available styles:
- `mb-locationsearch.json` — Light map style for location search
- `mb-locationsearch-dark.json` — Dark mode style

---

## URL Structure

### Page URLs (HTML)

All Meteoblue weather pages follow this pattern:
```
https://www.meteoblue.com/{lang}/weather/{section}/{subsection}/{slug}
```

Where `slug` = `{city-name}_{country-name}_{geonames-id}` (from location search `url` field).

| Page Type | URL Pattern |
|-----------|-------------|
| 7-day forecast | `/en/weather/week/{slug}` |
| 14-day forecast | `/en/weather/10-days/{slug}` |
| Today / hourly | `/en/weather/today/{slug}` |
| Meteograms | `/en/weather/forecast/meteogramweb/{slug}` |
| MultiModel | `/en/weather/forecast/multimodel/{slug}` |
| MultiModel Ensemble | `/en/weather/forecast/multimodelensemble/{slug}` |
| Seasonal Outlook | `/en/weather/forecast/seasonaloutlook/{slug}` |
| Weather Warnings | `/en/weather/warnings/index/{slug}` |
| Webcams | `/en/weather/webcams/{slug}` |
| Weather Maps | `/en/weather/maps/{slug}` |
| Air Quality & Pollen | `/en/weather/outdoorsports/airquality/{slug}` |
| Astronomy Seeing | `/en/weather/outdoorsports/seeing/{slug}` |
| Where to Go | `/en/weather/outdoorsports/where2go/{slug}` |
| Snow | `/en/weather/outdoorsports/snow/{slug}` |
| Sea & Surf | `/en/weather/outdoorsports/seasurf/{slug}` |
| Aviation AIR | `/en/weather/aviation/air/{slug}` |
| Thermals | `/en/weather/aviation/thermal/{slug}` |
| Trajectories | `/en/weather/aviation/trajectories/{slug}` |
| Cross-section | `/en/weather/aviation/crosssection/{slug}` |
| Stueve & Sounding | `/en/weather/aviation/stuve/{slug}` |
| Meteogram AGRO | `/en/weather/agriculture/meteogramagro/{slug}` |
| Sowing Windows | `/en/weather/agriculture/sowing/{slug}` |
| Spraying Windows | `/en/weather/agriculture/spraying/{slug}` |
| Soil Trafficability | `/en/weather/agriculture/soiltrafficability/{slug}` |
| Climate (modelled) | `/en/weather/historyclimate/climatemodelled/{slug}` |
| Climate (observed) | `/en/weather/historyclimate/climateobserved/{slug}` |
| Weather Archive | `/en/weather/historyclimate/weatherarchive/{slug}` |
| Climate Change | `/en/climate-change/{slug}` |
| Short-term Verification | `/en/weather/historyclimate/verificationshort/{slug}` |
| Climate Comparison | `/en/weather/historyclimate/climatecomparison/{slug}` |
| Year Comparison | `/en/weather/archive/yearcomparison/{slug}` |
| Data Download | `/en/weather/archive/export` |
| Histogram | `/en/weather/archive/histogram` |
| Wind Rose | `/en/weather/archive/windrose` |

---

## API Keys Summary

| Key | Usage | Source |
|-----|-------|--------|
| `LYnNIfRrK2XWTtzw` | Location Search API | `search_55e8bd.js` |
| `n4UGDLso3gE6m2YI` | Meteogram Image API | HTML `data-href` attributes |
| `5838a18e295d` | Dataset Query API | HTML `data-url` on archive/export page |
| `1iw4Jq5NZK60Ig7O` | Maps CDN / Mapbox styles | `maps-plugin.js` |
| `AIzaSyB3JPhvySdlda2u4FoVMWKf7IfEO_scL4o` | Google Maps (location search map) | HTML `mb.settings.googleMapsApiKey` |

---

## Authentication Notes

### Public Keys (No Authentication Required)
- `LYnNIfRrK2XWTtzw` — Location search works directly with this key

### Signature-Required Keys
- `n4UGDLso3gE6m2YI` and `5838a18e295d` — require `ts` (timestamp) + `sig` (HMAC-MD5)
- The HMAC secret is server-side only and not exposed in client JS
- **Workaround:** Fetch HTML pages and extract pre-signed `data-href`/`data-url` attributes

### Session-Required
- User favourites API requires a logged-in session cookie

---

## Installation & Usage

```bash
pip install requests  # optional but recommended
```

```python
from meteoblue_client import MeteoblueClient

client = MeteoblueClient()

# Search for a city
results = client.search_location("Zurich")
slug = results["results"][0]["url"]
print(slug)  # "zurich_switzerland_2657896"

# Get the meteogram data as Highcharts JSON
data = client.get_meteogram(slug, "standard", "highcharts")
print(data["title"]["text"])  # "Zurich"

# Get multimodel comparison
multi = client.get_multimodel(slug)

# Get historical data (ERA5T reanalysis)
history = client.get_historical(
    lat=47.37689, lon=8.54169, asl=408,
    name="Zurich",
    start="2023-01-01",
    end="2023-12-31",
    variables=[
        {"code": 11, "level": "2 m elevation corrected"},  # temperature
        {"code": 61, "level": "sfc"},                      # precipitation
        {"code": 201, "level": "10 m above gnd"},          # wind speed
    ],
    resolution="daily",
)

# Get maps inventory
inventory = client.get_maps_inventory(maps=["satellite", "radar"])
```

---

## Observations & Limitations

1. **Server-side rendering**: Most forecast data is embedded in HTML, not delivered via JSON API. The main forecast pages (7-day, 14-day) deliver HTML with pre-rendered weather data — not ideal for programmatic access.

2. **Signature expiry**: Pre-signed meteogram URLs appear to expire quickly (tens of seconds to minutes based on `ts`). Fresh URLs must be scraped from the HTML pages before each request.

3. **Rate limiting**: No explicit rate limiting was observed during testing, but excessive scraping may trigger blocks.

4. **Historical data (ERA5T)**: The dataset query API provides access to ERA5T historical reanalysis data since 1940, which is extremely valuable. The free tier (Basel location) works without authentication beyond the scraped signature.

5. **Commercial API**: Meteoblue offers a commercial API (`content.meteoblue.com/en/business-solutions/weather-apis`) with proper authentication, SLAs, and more endpoints. The internal APIs documented here are intended for the website UI, not for production use.

---

## JavaScript Sources Analyzed

| File | Size | Key Findings |
|------|------|-------------|
| `https://static.meteoblue.com/build/website.780/main.js` | 235 KB | Location search apikey, favourite endpoints, settings |
| `https://static.meteoblue.com/build/website/search_55e8bd.js` | Minified | Full search module with `LYnNIfRrK2XWTtzw` apikey |
| `https://static.meteoblue.com/lib/maps-plugin/v0.x/maps-plugin.js` | 410 KB | Maps inventory URL, tile URL templates, `1iw4Jq5NZK60Ig7O` key |

---

*Report generated by reverse engineering the Meteoblue website via browser network analysis and JS code inspection.*
