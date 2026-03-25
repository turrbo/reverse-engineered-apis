# OpenSnow API — Reverse Engineering Report & Python Client

## Overview

This documents the internal/hidden API used by [OpenSnow.com](https://opensnow.com), a popular ski resort weather forecast service. The API was reverse-engineered by inspecting the site's JavaScript bundles, Nuxt 3 SSR payload responses, and live network traffic.

---

## API Discovery Summary

### Method
1. Fetched the OpenSnow homepage HTML and extracted all `/_nuxt/*.js` bundle references
2. Downloaded each JS bundle (~60+ files) and extracted string literals and template literals matching API path patterns
3. Located the client initialization code revealing API base URL, API key, and request structure
4. Discovered the Nuxt 3 SSR `/_payload.json` endpoints which serve pre-rendered page data
5. Tested all discovered endpoints directly via curl to confirm working ones

### Key Findings from JS Bundles

The main API client is initialized in `/_nuxt/DCjlK3aK.js` (the Nuxt entry bundle). Relevant code:

```javascript
const jke = ps(e => {
  const {
    environment: t,
    openMountainApiKey: n,          // "60600760edf827a75df71f712b71e3f3"
    openMountainApiUrl: r,           // "https://opensnow.com/mtn"
    userApiToken: s
  } = Ws().public;

  const p = $fetch.create({
    baseURL: r,
    headers: { "User-Agent": "opensnow-web-2" },
    // ...
  });

  const x = (I = {}) => b({ v: 1, api_key: n, ...I });  // Query params builder

  return {
    provide: {
      api: {
        get(I, k = {}, N = {}) {
          return p(I, { method: "GET", query: { ...x(k) }, ...N });
        },
        post(I, k = {}, N = {}, $ = {}) {
          return p(I, { method: "POST", body: N, query: { ...x(k) }, ...$ });
        },
        // delete, put also follow same pattern
      }
    }
  }
});
```

### App Configuration (from inline `__NUXT__` config)

```javascript
window.__NUXT__.config = {
  public: {
    baseUrl: "https://opensnow.com",
    brazeSdkApiKey: "6f3b6c64-f280-4e10-87f1-4d96dcedd37e",
    brazeSdkEndpoint: "sdk.iad-06.braze.com",
    gtagId: "G-Z6F2F1ZKRY",
    mapboxAccessToken: "<MAPBOX_ACCESS_TOKEN>",
    metaPixelId: "4045686055688419",
    openMountainApiKey: "60600760edf827a75df71f712b71e3f3",
    openMountainApiUrl: "https://opensnow.com/mtn",
    recaptchaPublicKey: "6LctV-IZAAAAANhPtjDb2NRnakp3LO-iRf3ufpw3",
    stripePublicKey: "pk_live_WX7mtVbIR61hSHQn741zre7z",
    staticUrl: "https://blizzard.opensnow.com",
    // ...
  }
}
```

---

## API Reference

### Base Configuration

| Property | Value |
|----------|-------|
| Base URL | `https://opensnow.com/mtn` |
| API Key | `60600760edf827a75df71f712b71e3f3` |
| Version | `v=1` |
| User-Agent | `opensnow-web-2` |
| Auth | API key in query params (no login required for most endpoints) |

All requests require these query params: `?v=1&api_key=60600760edf827a75df71f712b71e3f3`

### Two API Types

#### 1. REST API (`/mtn/*`)

Used by the browser SPA for dynamic data fetching.

#### 2. SSR Payload API (`/{page}/_payload.json`)

Nuxt 3's server-side rendering pre-computes full page data and serves it as `/_payload.json`. This is the **richest** data source — it includes complete forecast data, snow history, and resort reports in a single request. The format is Nuxt's "RevJSON" (a flat array with cross-references to avoid duplication).

---

## Endpoint Reference

### REST API Endpoints

#### GET /mtn/meta/seed

Fetch global seed data. Returns all countries, states, and ski resort locations.

**Request:**
```
GET https://opensnow.com/mtn/meta/seed?v=1&api_key=60600760edf827a75df71f712b71e3f3
```

**Response:**
```json
{
  "cams": {"titlebar_height": 42},
  "countries": [
    {
      "id": 233,
      "code": "US",
      "name": "United States",
      "count_locations": 450,
      "states": [
        {"id": 6, "code": "US-CO", "name": "Colorado", "count_locations": 28}
      ]
    }
  ]
}
```

---

#### GET /mtn/search/locations

Search for ski resort locations by name.

**Request:**
```
GET https://opensnow.com/mtn/search/locations?q=vail&v=1&api_key=60600760edf827a75df71f712b71e3f3
```

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Search query |
| `limit` | int | Max results (optional) |

**Response:**
```json
{
  "locations": [
    {
      "id": 15,
      "name": "Vail",
      "slug": "vail",
      "type_id": 2,
      "elevation": 10784,
      "elevation_min": 8120,
      "elevation_max": 11570,
      "coordinates": {"point": [-106.3638, 39.6073]},
      "country_code": "US",
      "state_code": "US-CO",
      "state_name": "Colorado",
      "timezone": "America/Denver",
      "share_url": "https://opensnow.com/location/vail/snow-summary",
      "image_url": "https://lift.opensnow.com/location-logos/...",
      "has_resort_report": true,
      "dailysnow_agent_enabled": true,
      "avalanche_region_id": 4247
    }
  ]
}
```

---

#### GET /mtn/location/{slug}

Fetch basic location info.

**Request:**
```
GET https://opensnow.com/mtn/location/vail?v=1&api_key=60600760edf827a75df71f712b71e3f3
```

**Response:** Same location object structure as search results, wrapped in `{"location": {...}}`.

---

### SSR Payload Endpoints

These return Nuxt 3 RevJSON format. Use the `parse_payload()` function from the Python client to decode them, or read the raw data array directly.

#### GET /location/{slug}/snow-summary/_payload.json

The **most comprehensive** endpoint. Returns complete snow forecast data.

**Request:**
```
GET https://opensnow.com/location/vail/snow-summary/_payload.json
```

**Store Key Pattern:** `locationStore-fetchForecastSnowDetail-{slug}-{units}`

**Decoded Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Location ID |
| `name` | string | Resort name |
| `slug` | string | URL slug |
| `elevation` | int | Summit elevation (feet) |
| `elevation_min` | int | Base elevation (feet) |
| `elevation_max` | int | Peak elevation (feet) |
| `coordinates.point` | [lng, lat] | GPS coordinates |
| `timezone` | string | IANA timezone |
| `daily_read` | object | Latest DailySnow post |
| `forecast_snow_summary` | array | 5/10/15-day snow period summaries |
| `forecast_snow_daily` | array | Daily snowfall for 15 days |
| `forecast_current` | object | Current conditions |
| `forecast_semi_daily` | array | Morning/afternoon breakdown |
| `forecast_hourly` | array | Hourly forecast (~168 hours) |
| `history_snow_daily` | array | Past 14 days of snowfall |
| `history_snow_summary` | object | Season-to-date and average totals |
| `resort_report` | object | Official ski resort snow report |
| `history_snow_quality` | array | Past snow quality data |
| `forecast_snow_quality` | array | Upcoming snow quality forecast |
| `forecast_updated_at` | ISO datetime | When forecast was last updated |
| `forecast_source_id` | int | Forecast model source identifier |
| `weather_stations_recent_snow` | any | Weather station snow data |

**forecast_snow_summary item:**
```json
{
  "display_at": "2026-03-31T00:00:00Z",
  "display_at_local_label": "Next 6-10 Days",
  "precip_snow": 4,
  "precip_snow_min": 1,
  "precip_snow_max": 7,
  "period_count": 5,
  "alerts": [{"alert_id": 1, "level_id": 101, "color_foreground": "#9486c2"}]
}
```

**forecast_snow_daily item:**
```json
{
  "display_at": "2026-03-27T00:00:00Z",
  "display_at_local_label": "Thu 26",
  "precip_snow": 0,
  "precip_snow_min": 0,
  "precip_snow_max": 0
}
```

**resort_report object:**
```json
{
  "base_depth_max": 48,
  "base_depth_min": 36,
  "summit_depth_max": 84,
  "summit_depth_min": 72,
  "open_runs": 145,
  "total_runs": 195,
  "open_lifts": 21,
  "total_lifts": 31,
  "conditions": "Packed Powder",
  "updated_at": "2026-03-25T08:00:00Z"
}
```

---

#### GET /location/{slug}/weather/_payload.json

Detailed temperature and weather forecast.

**Store Key Pattern:** `locationStore-fetchForecastDetail-{slug}-{units}`

**Additional Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `forecast_daily` | array | 10-day daily hi/lo temps, precip |
| `forecast_hourly` | array | Hourly temp, wind, precip |
| `hazards` | array | Any weather hazard warnings |

---

#### GET /location/{slug}/snow-report/_payload.json

Official resort snow report with depth and open terrain data.

**Store Key Pattern:** `locationStore-fetchResortReport-{slug}-{units}`

---

#### GET /location/{slug}/daily-snows/_payload.json

List of DailySnow forecast posts by meteorologists.

---

#### GET /location/{slug}/avalanche-forecast/_payload.json

Regional avalanche danger forecast.

---

#### GET /location/{slug}/cams/_payload.json

Webcam list with image URLs.

---

#### GET /location/{slug}/trail-maps/_payload.json

Trail map images and info.

---

#### GET /location/{slug}/weather-stations/_payload.json

Nearby SNOTEL and weather station data.

---

#### GET /explore/powder/_payload.json

Powder map showing snow totals across all tracked resorts.

---

#### GET /explore/states/{state_code}/_payload.json

Resort listing for a US state.

**Examples:** `US-CO`, `US-UT`, `US-CA`, `US-WA`, `US-VT`

---

#### GET /explore/countries/{country_code}/_payload.json

Resort listing for a country.

**Examples:** `CA`, `AT`, `CH`, `FR`, `JP`

---

#### GET /explore/regions/{region_slug}/_payload.json

Resort listing for a geographic region.

---

#### GET /explore/season-passes/{pass_slug}/_payload.json

Resort listing by season pass (Ikon, Epic, etc.).

---

#### GET /compare/{slug1}/{slug2}/_payload.json

Side-by-side snowfall comparison for two resorts.

---

#### GET /dailysnow/{location_slug}/post/{post_id}/_payload.json

Full text of a specific DailySnow forecast post.

---

### User/Auth Endpoints (Require Session Cookie)

These endpoints require the user to be logged in (session cookie from cookie-based auth).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/mtn/user` | Get current user profile |
| GET | `/mtn/user/favorites` | Get all favorites |
| GET | `/mtn/user/favorites/ids` | Get favorite location IDs |
| GET | `/mtn/user/favorites/locations/snow-summary` | Snow summaries for favorites |
| GET | `/mtn/user/notifications/alert-areas` | Powder alert subscriptions |
| PUT | `/mtn/user/notifications/alert-areas` | Update alert area subscriptions |
| GET | `/mtn/user/notifications/daily-reads` | DailySnow subscriptions |
| GET | `/mtn/user/settings/subscription` | Subscription status |

**Auth endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/mtn/user/login` | Login with email/password |
| POST | `/mtn/user/login/link/request` | Request magic link email |
| POST | `/mtn/user/login/passcode` | Login with passcode |
| POST | `/mtn/user/register` | Create account |
| POST | `/mtn/user/logout` | Log out |

---

## Python Client Usage

### Installation

No dependencies beyond Python standard library.

```bash
# Copy opensnow_client.py to your project
```

### Quick Start

```python
from opensnow_client import OpenSnowClient

client = OpenSnowClient()

# Quick snow report
report = client.get_quick_snow_report("vail")
print(f"Vail: {report['forecast_snow_5d']}\" expected in next 5 days")

# Search locations
locations = client.search_locations("mammoth")
for loc in locations:
    print(f"{loc['name']} - {loc['state_name']}")

# Full snow summary (all data)
summary = client.get_snow_summary("mammoth-mountain")
current = summary.get("forecast_current", {})
print(f"Temp: {current.get('temp')}°F")

# Powder alerts
alerts = client.get_powder_alerts("jackson-hole")
for alert in alerts:
    print(f"{alert['date_label']}: {alert['precip_snow']}\" forecast")
```

### Metric Units

```python
client = OpenSnowClient(units="metric")
report = client.get_quick_snow_report("whistler")
# Snow depths will be in cm, temps in Celsius
```

### Bulk Fetching

```python
resorts = ["vail", "breckenridge", "keystone", "arapahoe-basin"]
reports = client.bulk_snow_summary(resorts, delay=0.5)

for slug, data in reports.items():
    if "error" not in data:
        print(f"{data['name']}: {data['forecast_snow_5d']}\" next 5 days")
```

### CLI Demo

```bash
python3 opensnow_client.py vail
python3 opensnow_client.py whistler
python3 opensnow_client.py jackson-hole
```

### Common Location Slugs

| Resort | Slug |
|--------|------|
| Vail, CO | `vail` |
| Breckenridge, CO | `breckenridge` |
| Park City, UT | `park-city` |
| Mammoth Mountain, CA | `mammoth-mountain` |
| Jackson Hole, WY | `jackson-hole` |
| Whistler Blackcomb, BC | `whistler` |
| Stowe, VT | `stowe` |
| Killington, VT | `killington` |
| Sun Valley, ID | `sun-valley` |
| Aspen Snowmass, CO | `aspen-snowmass` |
| Steamboat, CO | `steamboat` |
| Telluride, CO | `telluride` |

Use `client.search_locations("resort name")` to find any resort's slug.

---

## Notes & Caveats

### Rate Limiting
- CloudFlare sits in front of the API. Aggressive scraping may trigger rate limits or blocks.
- Recommend 0.5–1.0 second delays between requests for bulk fetching.

### API Key
- The API key (`60600760edf827a75df71f712b71e3f3`) is the **public frontend key** embedded in the JavaScript client bundle.
- It is not a secret — it's sent with every browser request.
- OpenSnow may rotate this key when they update their JS bundles. If requests start failing with 401/403, check the `openMountainApiKey` value in `window.__NUXT__.config`.

### Pro Content
- Some forecast features (extended forecasts, detailed hourly data) may require an OpenSnow All Access subscription.
- The `pro_status=f` query parameter is added by a server-side proxy for some requests.
- The SSR `/_payload.json` endpoints appear to return full data regardless of subscription status.

### Data Format
- Snow depths are in **inches** by default (add `units=metric` for cm)
- Temperatures are in **Fahrenheit** by default (metric = Celsius)
- Wind speeds are in **mph** (metric = km/h)
- Coordinates are `[longitude, latitude]` (GeoJSON order)
- All timestamps are ISO 8601 UTC

### RevJSON Decoding
The `/_payload.json` endpoints use Nuxt 3's "RevJSON" format — a flat array where repeated objects are stored once and referenced by index. The `parse_payload()` and `decode_revjson()` functions in the client handle this automatically.

---

## Static Asset CDN

| Asset Type | CDN URL |
|------------|---------|
| Location logos | `https://lift.opensnow.com/location-logos/` |
| Author photos | `https://lift.opensnow.com/author-photos/` |
| Summary images | `https://lift.opensnow.com/summary/` |
| Icons/sprites | `https://blizzard.opensnow.com/icons/` |
| Share images | `https://blizzard.opensnow.com/images/sharing/` |

---

*Reverse engineered March 2026. OpenSnow may change their API at any time.*
