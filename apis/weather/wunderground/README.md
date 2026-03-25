# Weather Underground Internal API - Reverse Engineering Report

**Date:** 2026-03-25
**Target:** https://www.wunderground.com
**Owner:** The Weather Company / IBM
**Status:** Fully documented with working Python client

---

## Summary

Weather Underground is owned by The Weather Company (IBM) and runs on their shared weather platform. The site exposes a comprehensive set of internal APIs at `api.weather.com` (with load-balanced mirrors at `api0` through `api3`). All endpoints use a shared API key embedded in the site's JavaScript bundles.

The platform has ~250,000+ Personal Weather Stations (PWS) worldwide, accessible via specialized v2 endpoints.

---

## Architecture Overview

```
Browser (wunderground.com)
        │
        ├─── PRIMARY API ───► https://api.weather.com   (The Weather Company APIs)
        │                       └─── api0/1/2/3.weather.com (load balancers)
        │
        ├─── DSX API ────────► https://dsx.weather.com  (streaming/push data)
        │
        ├─── PROFILE API ────► https://profile.wunderground.com  (user accounts)
        │
        ├─── UPSX API ───────► https://upsx.wunderground.com     (upload/push station data)
        │
        ├─── DEVICE API ─────► https://station-management.wunderground.com (device mgmt)
        │
        └─── MAP TILES ──────► https://a/b/c/d.tiles.mapbox.com  (base map tiles)
                               https://api{0-3}.weather.com/v3/TileServer (overlay tiles)
```

---

## API Keys (Embedded in Site JavaScript)

These keys are embedded in the production JavaScript bundles at `/bundle-next/`. They may rotate with site deployments.

| Key Name | Value | Used For |
|----------|-------|----------|
| `SUN_API_KEY` | `e1f10a1e78da46f5b10a1e78da96f525` | Primary - all v2/v3 endpoints |
| `SUN_PWS_HISTORY_API_KEY` | `e1f10a1e78da46f5b10a1e78da96f525` | PWS history |
| `SUN_PWS_IDENTITY_API_KEY` | `e1f10a1e78da46f5b10a1e78da96f525` | PWS identity |
| `WX_API_KEY` | `5c241d89f91274015a577e3e17d43370` | weather.com API |
| `DSX_API_KEY` | `7bb1c920-7027-4289-9c96-ae5e263980bc` | DSX streaming |
| `UPS_API_KEY` | `3254cfcb-90e3-4af5-819f-d79ea7e2382f` | Upload/profile service |
| `WU_LEGACY_API_KEY` | `d8585d80376a429e` | Legacy WU API (defunct) |

**Where to find updated keys:** Fetch `https://www.wunderground.com/dashboard/pws/KCASANFR1753`, search for `"process.env":` in the HTML source. The full configuration object is embedded in every page.

---

## Environment Configuration (process.env)

Full environment configuration extracted from page source:

```json
{
  "WU_LEGACY_API_HOST": "https://api-ak.wunderground.com/api",
  "DSX_API_HOST": "https://dsx.weather.com",
  "UPS_API_HOST": "https://profile.wunderground.com",
  "UPSX_API_HOST": "https://upsx.wunderground.com",
  "SUN_API_HOST": "https://api.weather.com",
  "SUN_DEVICE_API_HOST": "https://station-management.wunderground.com",
  "SUN_PWS_HISTORY_API_HOST": "https://api.weather.com/v2/pws/history",
  "SUN_PWS_IDENTITY_API_HOST": "https://api.weather.com",
  "MEMBER_KEY_GEN_API_HOST": "https://www.wunderground.com/key-gen",
  "WX_API_HOST": "https://weather.com",
  "WU_API_HOST": "https://www.wunderground.com",
  "WU_LEGACY_API_KEY": "d8585d80376a429e",
  "DSX_API_KEY": "7bb1c920-7027-4289-9c96-ae5e263980bc",
  "UPS_API_KEY": "3254cfcb-90e3-4af5-819f-d79ea7e2382f",
  "SUN_API_KEY": "e1f10a1e78da46f5b10a1e78da96f525",
  "SUN_DEVICE_API_KEY": "",
  "SUN_PWS_HISTORY_API_KEY": "e1f10a1e78da46f5b10a1e78da96f525",
  "SUN_PWS_IDENTITY_API_KEY": "e1f10a1e78da46f5b10a1e78da96f525",
  "WX_API_KEY": "5c241d89f91274015a577e3e17d43370",
  "NETATMO_CLIENT_ID": "5d41ba256df87f001255caed",
  "NETATMO_API_HOST": "https://api.netatmo.com",
  "NETATMO_REDIRECT_URL": "https://www.wunderground.com/member/devices/link",
  "METRICS_API_AMPLITUDE_KEY": "65e1857125d8c35761d19ddb9c32f145",
  "SUBSCRIPTIONS_CHECKOUT_URL": "https://wunderground.com/api/v1/subs/user/checkout?experience=wu"
}
```

---

## Complete API Endpoint Reference

### Base URL
`https://api.weather.com`

### Common Parameters
All endpoints accept:
- `apiKey` - Required. The API key.
- `format` - Always `json`.
- `units` - `e` (imperial/English), `m` (metric), `s` (SI), `h` (hybrid).
- `language` - `en-US`, `es`, `fr`, etc. (some endpoints use just `EN`).

---

### 1. Location APIs (`/v3/location/*`)

#### Search Locations
```
GET /v3/location/search
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `apiKey` | Yes | API key |
| `query` | Yes | Search term (city, ZIP, coords) |
| `language` | Yes | e.g. `en-US` |
| `countryCode` | No | Filter by country (e.g. `US`) |
| `adminDistrictCode` | No | Filter by state (e.g. `ny`) |

**Example:**
```
https://api.weather.com/v3/location/search?apiKey=e1f10a1e78da46f5b10a1e78da96f525&language=en-US&query=San+Francisco&format=json
```

**Response:** Arrays of matching locations including address, adminDistrict, city, country, countryCode, placeId, locId, latitude, longitude, type.

---

#### Get Location Point (Geocode Reverse)
```
GET /v3/location/point
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | One of | `lat,lon` e.g. `40.71,-74.01` |
| `pws` | One of | PWS station ID |
| `postalKey` | One of | ZIP:country e.g. `10001:US` |
| `icaoCode` | One of | Airport ICAO code |

**Example:**
```
https://api.weather.com/v3/location/point?apiKey=...&language=en-US&pws=KCASANFR1753&format=json
```

**Response:** Full location object including city, neighborhood, adminDistrict, postalCode, ianaTimeZone, dstStart, dstEnd, dmaCd, placeId, canonicalCityId, pollenId, pwsId, regionalSatellite, tideId, zoneId, icaoCode.

---

#### Find Nearby PWS Stations
```
GET /v3/location/near?product=pws
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | Yes | `lat,lon` |
| `product` | Yes | `pws` |

**Example:**
```
https://api.weather.com/v3/location/near?apiKey=...&geocode=40.713,-74.006&product=pws&format=json
```

**Response:** Arrays of nearby stations: stationId, stationName, qcStatus, updateTimeUtc, partnerId, latitude, longitude.

---

#### Find Nearby Airports
```
GET /v3/location/near?product=airport
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | Yes | `lat,lon` |
| `product` | Yes | `airport` |
| `subproduct` | No | `major` (default) or omit for all |

---

#### Get Elevation
```
GET /v3/location/elevation
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | Yes | `lat,lon` |
| `units` | Yes | Unit system |

**Response:** `{"location": {"elevation": 89}}`

---

#### Get Location DateTime / Timezone
```
GET /v3/dateTime
```
**Response:** `{"dateTime": "2026-03-24T22:32:57.162-04:00", "ianaTimeZone": "America/New_York", "timeZoneAbbreviation": "EDT"}`

---

### 2. Current Conditions (`/v3/wx/observations/current`)

```
GET /v3/wx/observations/current
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | One of | `lat,lon` |
| `icaoCode` | One of | Airport ICAO code (e.g. `KJFK`) |
| `units` | Yes | Unit system |
| `language` | Yes | Language code |

**Example:**
```
https://api.weather.com/v3/wx/observations/current?apiKey=...&geocode=40.713,-74.006&units=e&language=en-US&format=json
```

**Response fields:** cloudCeiling, cloudCover, cloudCoverPhrase, dayOfWeek, dayOrNight, expirationTimeUtc, iconCode, iconCodeExtend, obsQualifierCode, precip1Hour, precip6Hour, precip24Hour, pressureAltimeter, pressureChange, pressureMeanSeaLevel, pressureTendencyCode, pressureTendencyTrend, relativeHumidity, snow1Hour, snow6Hour, snow24Hour, sunriseTimeLocal, sunsetTimeLocal, temperature, temperatureChange24Hour, temperatureDewPoint, temperatureFeelsLike, temperatureHeatIndex, temperatureMax24Hour, temperatureMaxSince7Am, temperatureMin24Hour, temperatureWetBulbGlobe, temperatureWindChill, uvDescription, uvIndex, validTimeLocal, visibility, windDirection, windDirectionCardinal, windGust, windSpeed, wxPhraseLong, wxPhraseMedium, wxPhraseShort.

---

### 3. Forecast APIs

#### Daily Forecast
```
GET /v3/wx/forecast/daily/{n}day
```
where `{n}` is `3`, `5`, `7`, `10`, or `15`.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | One of | `lat,lon` |
| `icaoCode` | One of | Airport ICAO code |

**Response:** Arrays for each day: calendarDayTemperatureMax/Min, dayOfWeek, expirationTimeUtc, moonPhase, moonPhaseCode, moonPhaseDay, moonriseTimeLocal/Utc, moonsetTimeLocal/Utc, narrative, qpf, qpfIce, qpfRain, qpfSnow, sunriseTimeLocal/Utc, sunsetTimeLocal/Utc, temperatureMax, temperatureMin, validTimeLocal/Utc.

Also includes `daypart` array with hourly-level forecast by period (day/night): cloudCover, dayOrNight, daypartName, iconCode, iconCodeExtend, narrative, precipChance, precipType, qpf, qpfSnow, qualifierCode, relativeHumidity, snowRange, temperature, temperatureHeatIndex, temperatureWindChill, thunderCategory, thunderIndex, uvDescription, uvIndex, windDirection, windDirectionCardinal, windPhrase, windSpeed, wxPhraseLong, wxPhraseShort.

---

#### Hourly Forecast
```
GET /v3/wx/forecast/hourly/{period}
```
where `{period}` is `1day` or `15day`.

**Example:**
```
https://api.weather.com/v3/wx/forecast/hourly/15day?apiKey=...&geocode=40.71,-74.01&units=e&language=en-US&format=json
```

**Response:** 24 entries (1day) or 360 entries (15day) with arrays: cloudCover, dayOfWeek, dayOrNight, expirationTimeUtc, iconCode, iconCodeExtend, precipChance, precipType, qpf, relativeHumidity, temperature, temperatureDewPoint, temperatureFeelsLike, thunderCategory, thunderIndex, uvDescription, uvIndex, validTimeLocal, validTimeUtc, windDirection, windDirectionCardinal, windPhrase, windSpeed, wxPhraseLong, wxPhraseShort.

---

### 4. Historical Conditions

#### Past 24 Hours (Hourly)
```
GET /v3/wx/conditions/historical/hourly/1day
```
Returns 24 entries of actual measured conditions.

---

#### Past 30 Days (Daily Summary, Airport)
```
GET /v3/wx/conditions/historical/dailysummary/30day
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `icaoCode` | Yes | Airport ICAO code |
| `units` | Yes | Unit system |
| `language` | Yes | e.g. `EN` (uppercase) |

**Response:** Arrays of 30 days: dayOfWeek, iconCodeDay/Night, precip24Hour, rain24Hour, snow24Hour, temperatureMax, temperatureMin.

---

### 5. Almanac (Historical Climate Normals)

```
GET /v3/wx/almanac/daily/{n}day
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `icaoCode` | Yes | Airport ICAO code |
| `startMonth` | Yes | Month (e.g. `03`) |
| `startDay` | Yes | Day (e.g. `25`) |
| `units` | Yes | Unit system |

**Response:** almanacInterval, almanacRecordDate, almanacRecordPeriod, almanacRecordYearMax/Min, precipitationAverage, snowAccumulationAverage, stationId, stationName, temperatureAverageMax/Min, temperatureMean, temperatureRecordMax/Min.

---

### 6. Astronomy (Sun & Moon)

```
GET /v2/astro
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | Yes | `lat,lon` |
| `days` | Yes | Number of days (1-15) |
| `date` | Yes | Start date `YYYYMMDD` |

**Response:** Array of `astroData` objects per day, each with:
- `sun.riseSet`: riseLocal, riseUTC, setLocal, setUTC
- `sun.twilight.civil/nautical/astronomical`: dawn/dusk times
- `sun.zenith`: maximum altitude time
- `moon.riseSet`: moonrise/moonset
- `moon.phase`: phase name, illumination percentage
- `visibleLight`, `lengthOfDay`, `tomorrowDaylightDifference`

---

### 7. Weather Alerts

#### Get Alert Headlines
```
GET /v3/alerts/headlines
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `geocode` | Yes | `lat,lon` |
| `language` | Yes | e.g. `EN` (uppercase) |

Returns HTTP 204 with no body if no alerts. Returns JSON with `alerts` array if alerts exist.

---

#### Get Alert Detail
```
GET /v3/alerts/detail
```
| Parameter | Required | Description |
|-----------|----------|-------------|
| `alertId` | Yes | ID from headlines endpoint |
| `language` | Yes | Language code |

---

### 8. Personal Weather Station (PWS) APIs

All PWS endpoints are at `api.weather.com/v2/pws*`.

#### Current Observations
```
GET /v2/pws/observations/current?stationId={id}&units={units}
```

**Response:** Station metadata + unit-specific measurements:
- Metadata: stationID, obsTimeUtc, obsTimeLocal, neighborhood, softwareType, country, solarRadiation, lon, lat, uv, winddir, humidity, qcStatus, realtimeFrequency
- `imperial` or `metric` block: temp, heatIndex, dewpt, windChill, windSpeed, windGust, pressure, precipRate, precipTotal, elev

---

#### Today's Observations (All Readings)
```
GET /v2/pws/observations/all/1day?stationId={id}&numericPrecision=decimal
```
Returns all ~288 raw observations for the current day with high/low/avg per reading.

---

#### Recent Observations (1, 3 days)
```
GET /v2/pws/observations/all/{n}day       (n = 1 or 3)
GET /v2/pws/observations/hourly/{n}day    (n = 1 or 3)
```
7-day access requires premium authentication.

---

#### Daily Summary
```
GET /v2/pws/dailysummary/{period}?stationId={id}
```
where `{period}` is `1day`, `3day`, etc.

**Response:** `summaries` array with daily high/low/avg for temp, wind, humidity, pressure, UV, solar radiation, precipitation.

---

#### History - Daily Summary
```
GET /v2/pws/history/daily?stationId={id}&date={YYYYMMDD}
```

#### History - Hourly Summary
```
GET /v2/pws/history/hourly?stationId={id}&date={YYYYMMDD}
```
Returns 24 hourly aggregates.

#### History - All Readings
```
GET /v2/pws/history/all?stationId={id}&date={YYYYMMDD}
```
Returns every raw reading (~288 per day).

All history endpoints accept `numericPrecision=decimal` for float values.

---

#### PWS Identity (Station Metadata)
```
GET /v2/pwsidentity?stationId={id}
```

**Response:** ID, neighborhood, name, city, state, country, latitude, longitude, elevation, height (mounting height in ft), stationType (hardware model), surfaceType (roof type, etc.), tzName, lastUpdateTime, startTime, softwareType, goldStar (quality flag), isRecent.

---

### 9. Aggregated Multi-Product Requests

```
GET /v3/aggcommon/{products}
```
where `{products}` is a semicolon-separated list of product IDs.

**Example:**
```
https://api.weather.com/v3/aggcommon/v3alertsHeadlines;v3-wx-observations-current;v3-location-point?apiKey=...&geocodes=37.77,-122.41;40.75,-74&language=en-US&units=e&format=json
```

- `geocodes` can contain multiple locations (semicolon-separated)
- Returns a list with one object per geocode, each containing all requested products

**Common product IDs:**
- `v3alertsHeadlines` - Weather alert headlines
- `v3-wx-observations-current` - Current conditions
- `v3-location-point` - Location metadata

---

### 10. Radar & Map Tile APIs

#### Get Available Tile Series (Timestamps for Animation)
```
GET /v3/TileServer/series/productSet?productSet={setName}
```

**Available wuRadar productSet values:**
`wuRadarAlaska`, `wuRadarAustralian`, `wuRadarConus`, `wuRadarEurope`, `wuRadarFcst`, `wuRadarFcstV2`, `wuRadarFcstV3`, `wuRadarHawaii`, `wuRadarHcMosaic`, `wuRadarMosaic`, `wuRadarMosaicNS`, `seaSurfaceTemperature`

**All tile products (no productSet):**
24hrMaxTempFcst, 24hrMinTempFcst, achesPainsFcst, aqi-epa-pm10, breathingFcst, cloudsFcst, ddiForecast, dewpoint, dewpointFcst, feelsLike, feelsLikeFcst, fusionPbRadarMosaic, grassPollenFcst, heatIndex, mosquitoGlobalFcst, precip1hrAccum, precip24hr, precip24hrFcst, precipAndRain1hrAccumFcst, **radar**, radarFcst, radarFcstV2, radarFcstV3, ragweedPollenFcst, sat, sat_goes16, satgoes16ConusIR, satgoes16ConusVis, satgoes16ConusWV, satgoes16FullDiskIR, satgoes16FullDiskVis, satgoes16FullDiskWV, satgoes16Meso1/2 IR/Vis/WV, satrad, satradFcst, sensibleWeather12hrFcst, sensibleWeather1hrFcst, snow1hrCumulativePrecipFcst, snow24hr, snow24hrFcst, snowCoverageConus1hr, **temp**, tempChange, tempFcst, tempHourlyFcst, thermalSat, thermalUSsat, treePollenFcst, twc250RadarMosaic, twcRadarHcMosaic, twcRadarMosaic, twcRadarMosaicV2, ussat, uv, uv_v2, uvFcst, waterTemperature*, windChill, windSpeed, windSpeed12hrFcst, windSpeedFcst, windSpeedGust, grafCloudCoverFcst, grafCumulativeIce, grafCumulativePrecip, grafCumulativeSnow, grafFeelsLikeFcst, grafRadarFcst, grafTempFcst, grafWindGustFcst, grafWindspeedFcst

**Response:** Contains `seriesInfo` with `nativeZoom`, `maxZoom`, bounding box, and `series` array of `{ts: unix_timestamp}` objects.

---

#### Fetch a Tile Image
```
GET /v3/TileServer/tile?product={product}&ts={ts}&fts={fts}&xyz={x}:{y}:{z}&apiKey={key}
```
Tile URL template from source: `//api{s}.weather.com/v3/TileServer/tile?product={productKey}&ts={ts}&fts={fts}&xyz={x}:{y}:{z}&apiKey={apiKey}`

- `s` = load balancer number (0-3, or empty for round-robin)
- `ts` = timestamp from series endpoint
- `fts` = forecast timestamp (same as ts for current, future ts for forecast)
- `xyz` = tile coordinates in `x:y:z` format (Slippy Map convention)

Note: Direct tile requests may require a valid browser session cookie.

---

### 11. Tropical Storm APIs

```
GET /v2/tropical?basin={basin}
GET /v2/tropical/currentposition?stormId={id}
GET /v2/tropical/track?stormId={id}
GET /v3/tropical/models?stormId={id}
GET /v3/tropical/track/details?stormId={id}
```

Basin codes: `AL` (Atlantic), `EP` (East Pacific), `CP` (Central Pacific), `WP` (West Pacific), `SP` (South Pacific), `SI` (South Indian), `IO` (North Indian Ocean).

---

### 12. Maps (Dynamic Satellite/Aerial)

```
GET /v2/maps/dynamic?geocode={lat,lon}&h={height}&w={width}&lod={zoom}&apiKey={key}
```
Returns a satellite imagery tile for the given geocode and zoom level.

---

## Quick Start

```python
from wunderground_client import WundergroundClient

# Create client (uses embedded site keys)
client = WundergroundClient(units="e")  # "e"=imperial, "m"=metric

# Search location
results = client.search_location("Chicago")
# results["location"]["address"][0] => "Chicago, Illinois, United States"

# Current conditions by geocode
cond = client.get_current_conditions(geocode="41.85,-87.65")
# cond["temperature"] => 45 (°F)
# cond["wxPhraseLong"] => "Partly Cloudy"

# Current conditions by airport code
cond = client.get_current_conditions(icao_code="KORD")

# 10-day forecast
fc = client.get_forecast_daily("41.85,-87.65", days=10)
# fc["dayOfWeek"] => ["Wednesday", "Thursday", ...]
# fc["temperatureMax"] => [52, 58, ...]

# Hourly forecast (360 hours)
hfc = client.get_forecast_hourly("41.85,-87.65", hours="15day")

# PWS current conditions
obs = client.get_pws_current("KILCHICA197")
# obs["observations"][0]["imperial"]["temp"] => 47

# PWS identity / metadata
info = client.get_pws_identity("KILCHICA197")
# info["name"] => "Lincoln Square"
# info["stationType"] => "Ambient Weather WS-2000"

# PWS history for a date
history = client.get_pws_history_daily("KILCHICA197", "20260101")
# history["observations"][0]["imperial"]["tempHigh"] => 38.2

# PWS hourly history
hist = client.get_pws_history_hourly("KILCHICA197", "20260101")

# Nearby PWS stations
nearby = client.get_nearby_pws("41.85,-87.65")
# nearby["location"]["stationId"] => ["KILCHICA197", ...]

# Sunrise/sunset
astro = client.get_astronomy("41.85,-87.65", days=3)
# astro["astroData"][0]["sun"]["riseSet"]["riseLocal"]

# Active alerts
alerts = client.get_alerts_headlines("41.85,-87.65")
# None if no alerts, otherwise dict with "alerts" list

# Radar tile series (get timestamps for animation)
series = client.get_tile_series("wuRadar")
# series["seriesInfo"]["wuRadarConus"]["series"][0]["ts"] => 1774406100

# Build a radar tile URL
ts = series["seriesInfo"]["wuRadarConus"]["series"][0]["ts"]
tile_url = client.get_tile_url("radar", ts, x=155, y=180, zoom=8)

# Multi-location current conditions (batch)
multi = client.get_current_conditions_multi(["40.71,-74.01", "41.85,-87.65", "34.05,-118.24"])
# Returns list of 3 dicts

# PWS history over date range (fetches day-by-day)
range_data = client.get_pws_history_range(
    "KCASANFR1753",
    start_date="20260101",
    end_date="20260110",
    interval="daily"
)
```

---

## Unit Systems

| Code | System | Temp | Wind | Pressure | Precip |
|------|--------|------|------|----------|--------|
| `e` | Imperial | °F | mph | inHg | inches |
| `m` | Metric | °C | km/h | mb/hPa | mm |
| `s` | SI | °C | m/s | mb/hPa | mm |
| `h` | Hybrid | °C | mph | inHg | inches |

---

## PWS Station ID Format

Personal Weather Station IDs follow this format: `K{STATE}{CITY}{NUMBER}`

Examples:
- `KCASANFR1753` = California, San Francisco, #1753
- `KNYNEWYO2074` = New York, New York City, #2074
- `KILCHICA197`  = Illinois, Chicago, #197

---

## Rate Limits & Notes

1. **Authentication:** The embedded API keys work without any session cookies for most endpoints.
2. **Rate limits:** Not publicly documented. The site uses load balancers (api0-api3) suggesting high-volume usage is expected.
3. **Radar tiles:** Some tile endpoints may require a valid browser session cookie (HTTP 401 without it).
4. **7-day PWS history:** Requires premium authentication beyond the embedded keys.
5. **Caching:** Many responses include `expirationTimeUtc` timestamps for client-side caching.
6. **Key rotation:** The embedded keys are updated when the site is deployed. Re-extract from `process.env` block in page source if keys stop working.

---

## How Keys Were Discovered

1. Fetched `https://www.wunderground.com` with curl, extracted JS bundle file references.
2. Fetched `https://www.wunderground.com/dashboard/pws/KCASANFR1753` to get server-rendered HTML.
3. Found `"process.env":{}` JSON block embedded in SSR (server-side rendered) page, containing all API keys and service hosts.
4. Extracted 7 unique API URLs embedded as cached responses in the SSR state.
5. Fetched and analyzed JS chunk files (`/bundle-next/chunk-UNXS23HZ.js` at 1MB, the main application bundle).
6. Found the `apiVars` object construction in the Angular app initializer, revealing all service endpoint mappings and key assignments.
7. Discovered the `get({version, features, params})` pattern used throughout, converting feature arrays like `["pws", "observations", "current"]` to URL paths.
8. Fetched hourly, forecast, history, and maps pages to discover additional cached API calls.
9. Tested each discovered endpoint directly with curl to verify functionality.

---

## Files

- `wunderground_client.py` - Complete Python client with all documented endpoints
- `wunderground_README.md` - This document

---

*Report generated by automated API reverse engineering on 2026-03-25.*
