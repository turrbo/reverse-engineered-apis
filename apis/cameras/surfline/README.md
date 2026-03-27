# Surfline API Client

Reverse-engineered Python client for Surfline's undocumented internal REST API
(`services.surfline.com`).

All endpoints and behaviors documented here were discovered through live HTTP
traffic analysis against `https://www.surfline.com` in March 2026.

---

## Quick Start

```bash
pip install requests
```

```python
from surfline_client import SurflineClient

client = SurflineClient()

# Search for a surf spot
spots = client.search_spots("pipeline")
pipeline_id = spots[0]["id"]   # "5842041f4e65fad6a7708890"

# Get current conditions
cond = client.get_current_conditions(pipeline_id)
print(cond["rating"])          # "FAIR", "GOOD", etc.
print(cond["wave_min_ft"])     # 3
print(cond["wave_max_ft"])     # 4
print(cond["wind_type"])       # "Offshore"

# Get cameras
for cam in cond["cameras"]:
    print(cam["title"], cam["still_url"], cam["is_premium"])

# 3-day hourly forecast
forecast = client.get_forecast_summary(pipeline_id, days=3)
for hour in forecast[:6]:
    print(hour["datetime_local"], hour["wave_min_ft"], hour["rating_key"])
```

---

## Authentication

### Public Access (no account required)

The majority of endpoints are accessible without a Surfline account. The API
server performs a lightweight same-origin check by inspecting the `Origin` and
`Referer` request headers. The `SurflineClient` automatically includes these
headers in every request:

```
Origin:  https://www.surfline.com
Referer: https://www.surfline.com/
```

Without these headers the API returns `HTTP 401`. Once the headers are present,
forecast, camera, spot, and search data all return `HTTP 200`.

### Authenticated Access (account required)

User-specific endpoints (`/user/favorites`, `/user/profile`, `/user/feeds`)
require a valid JSON Web Token (JWT) Bearer token. Obtain one by calling
`client.login()`:

```python
client.login("user@example.com", "password")
favorites = client.get_favorites()
```

**Auth Endpoint:**
```
POST https://services.surfline.com/auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
client_id=SurferApp
client_secret=SurferApp
device_id=web
email=<email>
password=<password>
```

Additional confirmed detail: the endpoint strictly requires
`application/x-www-form-urlencoded` — JSON bodies return:
`{"message": "Invalid Parameters: Method must be POST with application/x-www-form-urlencoded encoding"}`

A second OAuth client ID `5af1ce73b5acf7c6dd2592ee` was observed in the
`platform.surfline.com` authorization-code flow (used for the "Connect" SSO
login page at `https://services.surfline.com/auth/token`).  The `SurferApp`
client ID is used for the mobile/API resource-owner password grant.

On success, the response includes `access_token` (JWT Bearer token).

### Camera Stream Access (premium subscription required)

- **Still images** (`camstills.cdn-surfline.com`) — publicly accessible, no
  authentication needed.
- **HLS live streams** (`hls.cdn-surfline.com`) — gated by Cloudflare; require
  a valid Surfline premium subscription session cookie. Direct access returns
  `HTTP 403 Forbidden`.
- **Rewind clips** (`camrewinds.cdn-surfline.com`) — may require premium.
- **Highlight clips** (`highlights.cdn-surfline.com`) — may require premium.

---

## Base URL

```
https://services.surfline.com
```

### CDN Hosts

| Host | Purpose | Auth Required |
|------|---------|---------------|
| `camstills.cdn-surfline.com` | Camera still images (JPEG) | No |
| `hls.cdn-surfline.com` | Live HLS streams (m3u8) | Yes (premium) |
| `camrewinds.cdn-surfline.com` | Rewind MP4 clips | Yes (premium) |
| `highlights.cdn-surfline.com` | Highlight MP4 clips | Yes (premium) |
| `spot-thumbnails.cdn-surfline.com` | Spot background photos | No |
| `wa.cdn-surfline.com` | Weather icons, forecaster banners | No |

---

## Endpoints

### Map / Geo

#### `GET /kbyg/mapview`

Return all surf spots and cameras within a geographic bounding box. This is the
primary endpoint used by the Surfline map view and camera browser.

**Auth required:** No (with Origin/Referer headers)

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `south` | float | Yes | Southern latitude bound |
| `north` | float | Yes | Northern latitude bound |
| `west` | float | Yes | Western longitude bound |
| `east` | float | Yes | Eastern longitude bound |

**Example:**
```
GET /kbyg/mapview?south=20&north=22&west=-159&east=-157
```

**Response structure:**
```json
{
  "associated": {
    "units": {"windSpeed": "KTS", "waveHeight": "FT", "tideHeight": "FT"}
  },
  "data": {
    "regionalForecast": {"iconUrl": "...", "legacyRegionId": 2144, "subregionId": "..."},
    "subregions": [{"_id": "...", "subregion": {"id": "...", "name": "North Shore Oahu"}}],
    "spots": [
      {
        "_id": "5842041f4e65fad6a7708890",
        "name": "Pipeline",
        "lat": 21.66522,
        "lon": -158.0526,
        "subregionId": "...",
        "conditions": {"value": "POOR_TO_FAIR", "sortableCondition": 2},
        "waveHeight": {"min": 3, "max": 4, "humanRelation": "Waist to chest"},
        "wind": {"speed": 8.0, "direction": 45, "directionType": "Cross-shore", "gust": 10},
        "swells": [{"height": 3.0, "period": 13, "direction": 315, ...}],
        "tide": {
          "previous": {"type": "HIGH", "height": 0.5, "timestamp": 1774614181},
          "current": {"type": "NORMAL", "height": 0.1},
          "next": {"type": "LOW", "height": 0.0, "timestamp": 1774641388}
        },
        "waterTemp": {"min": 78, "max": 78},
        "weather": {"temperature": 79, "condition": "CLEAR"},
        "cameras": [
          {
            "_id": "58349eed3421b20545c4b56c",
            "title": "HI - Pipeline",
            "alias": "hi-pipeline",
            "streamUrl": "https://hls.cdn-surfline.com/oregon/hi-pipeline/playlist.m3u8",
            "stillUrl": "https://camstills.cdn-surfline.com/us-west-2/hi-pipeline/latest_small.jpg",
            "stillUrlFull": "https://camstills.cdn-surfline.com/us-west-2/hi-pipeline/latest_full.jpg",
            "pixelatedStillUrl": "https://camstills.cdn-surfline.com/hi-pipeline/latest_small_pixelated.png",
            "rewindBaseUrl": "https://camrewinds.cdn-surfline.com/hi-pipeline/hi-pipeline",
            "rewindClip": "https://camrewinds.cdn-surfline.com/hi-pipeline/hi-pipeline.1300.2026-03-27.mp4",
            "isPremium": true,
            "isPrerecorded": false,
            "isLineupCam": false,
            "supportsHighlights": true,
            "supportsInsights": true,
            "supportsSmartRewinds": true,
            "supportsCrowds": false,
            "nighttime": false,
            "status": {"isDown": false, "message": ""},
            "highlights": {
              "url": "https://highlights.cdn-surfline.com/us-west-2/clips/58349eed...-20260327T...Z.mp4",
              "thumbUrl": "https://highlights.cdn-surfline.com/us-west-2/thumbnails/58349eed...-....jpg",
              "gifUrl": ""
            },
            "host": {"camLinkEnabled": false, "name": "", "url": "", "camLinkText": ""}
          }
        ],
        "thumbnail": "https://spot-thumbnails.cdn-surfline.com/spots/5842041f4e65fad6a7708890/5842041f4e65fad6a7708890_1500.jpg",
        "legacyId": 4750,
        "timezone": "Pacific/Honolulu",
        "hasLiveWind": true,
        "abilityLevels": ["ADVANCED"],
        "boardTypes": ["SHORTBOARD", "GUN"]
      }
    ]
  }
}
```

---

### Spot Data

#### `GET /kbyg/spots/reports`

Full spot report combining metadata, cameras, current conditions, travel guide
info, and the latest forecast summary. This is the primary endpoint for a spot
detail page.

**Auth required:** No

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `spotId` | string | Yes | Surfline spot ID |

**Example:**
```
GET /kbyg/spots/reports?spotId=5842041f4e65fad6a7708890
```

**Key response fields:**
```json
{
  "associated": {
    "units": {...},
    "timezone": "Pacific/Honolulu",
    "utcOffset": -10,
    "windStation": {"name": "Pipeline", "location": {"lat": 21.66567, "lon": -158.05016}, "provider": "DAVIS"},
    "href": "https://www.surfline.com/surf-report/pipeline/5842041f4e65fad6a7708890"
  },
  "spot": {
    "_id": "...",
    "name": "Pipeline",
    "lat": 21.66522,
    "lon": -158.0526,
    "cameras": [...],
    "subregion": {"_id": "...", "name": "North Shore Oahu"},
    "breadcrumb": [{"name": "United States", "href": "..."}],
    "travelDetails": {
      "abilityLevels": {"summary": "ADVANCED", "description": "..."},
      "best": {
        "season": {"description": "Winter", "value": [...]},
        "tide": {"description": "All tides", "value": [...]},
        "swellDirection": {"description": "NW"}
      },
      "bottom": {"description": "Reef", "value": "..."},
      "crowdFactor": {"rating": 2, "summary": "Very Crowded"},
      "spotRating": {"rating": 6, "summary": "World Class"},
      "waterQuality": {"rating": 5, "summary": "Good"},
      "access": "Free parking nearby",
      "breakType": "Reef break",
      "hazards": "Shallow reef, heavy barrels"
    },
    "hasLiveWind": true,
    "insightsCameraId": "58349eed3421b20545c4b56c"
  },
  "forecast": {
    "conditions": {"value": "POOR_TO_FAIR", "sortableCondition": 2},
    "forecaster": {"name": "...", "title": "...", "iconUrl": "..."},
    "waveHeight": {"min": 3, "max": 4, "human": false, "humanRelation": "Waist to chest"},
    "wind": {"speed": 8.0, "direction": 45, "directionType": "Cross-shore", "gust": 10},
    "swells": [{"height": 3.0, "period": 13, "direction": 315, ...}],
    "tide": {"previous": {...}, "current": {...}, "next": {...}},
    "waterTemp": {"min": 78, "max": 78}
  }
}
```

---

#### `GET /kbyg/spots/nearby`

List of surf spots geographically close to a given spot.

**Auth required:** No

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `spotId` | string | Yes | Reference spot ID |

**Response:** `data.spots` — list of spot objects with current conditions.

---

### Forecast Data

All forecast endpoints share a common parameter set:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `spotId` | string | - | Surfline spot ID (required) |
| `days` | int | 5 | Forecast days (max 6 without auth) |
| `intervalHours` | int | 1 | Interval between data points (1 or 3) |
| `units[waveHeight]` | string | FT | `FT` or `M` |
| `units[swellHeight]` | string | FT | `FT` or `M` |
| `units[windSpeed]` | string | KTS | `KTS` or `MPH` or `KPH` |
| `units[temperature]` | string | F | `F` or `C` |
| `units[tideHeight]` | string | FT | `FT` or `M` |

#### `GET /kbyg/spots/forecasts/wave`

Hourly wave height and swell decomposition.

**Auth required:** No (for up to 6 days)

**Response sample:**
```json
{
  "associated": {
    "units": {"waveHeight": "FT", "swellHeight": "FT", "windSpeed": "KTS"},
    "utcOffset": -10,
    "location": {"lon": -158.0526, "lat": 21.66522},
    "forecastLocation": {"lon": -158.059, "lat": 21.668},
    "offshoreLocation": {"lon": -158.15, "lat": 21.75},
    "runInitializationTimestamp": 1774591200
  },
  "data": {
    "wave": [
      {
        "timestamp": 1774605600,
        "utcOffset": -10,
        "probability": 96.7,
        "surf": {
          "min": 4,
          "max": 5,
          "plus": false,
          "humanRelation": "Chest to head",
          "raw": {"min": 4.2979, "max": 5.15092},
          "optimalScore": 2
        },
        "power": 443.24,
        "swells": [
          {
            "height": 7.21,
            "period": 9,
            "impact": 0.371,
            "power": 293.83,
            "direction": 36.6,
            "directionMin": 21.8,
            "optimalScore": 0
          },
          {
            "height": 2.98,
            "period": 13,
            "impact": 0.52,
            "power": 147.1,
            "direction": 314.7,
            "directionMin": 308.3,
            "optimalScore": 1
          }
        ]
      }
    ]
  }
}
```

**Notes:**
- Up to 6 individual swell components are included per timestamp.
- `surf.min/max` are "human-scaled" Surfline heights (roughly face height).
- `surf.raw.min/max` are full significant wave heights in feet.
- `power` is a proprietary wave power index (useful for relative comparisons).
- `optimalScore` 0-3 indicates how optimal that swell direction is for the spot.

---

#### `GET /kbyg/spots/forecasts/wind`

Hourly wind speed, direction, and gust forecast.

**Auth required:** No

**Response sample:**
```json
{
  "associated": {
    "windStation": {
      "name": "HB Pier SS",
      "location": {"lat": 33.65662, "lon": -118.00211},
      "provider": "DAVIS"
    },
    "lastObserved": 1774629000
  },
  "data": {
    "wind": [
      {
        "timestamp": 1774594800,
        "utcOffset": -7,
        "speed": 2.94,
        "direction": 213.8,
        "directionType": "Onshore",
        "gust": 2.94,
        "optimalScore": 2
      }
    ]
  }
}
```

**`directionType` values:** `"Offshore"`, `"Onshore"`, `"Cross-shore"`

---

#### `GET /kbyg/spots/forecasts/tides`

Tide heights and HIGH/LOW tide events.

**Auth required:** No

**Parameters:** `spotId`, `days`

**Response sample:**
```json
{
  "associated": {
    "tideLocation": {
      "name": "Haleiwa, Hawaii",
      "min": -0.3,
      "max": 2.1,
      "lon": -158.1,
      "lat": 21.6,
      "mean": 0
    }
  },
  "data": {
    "tides": [
      {"timestamp": 1774605600, "utcOffset": -10, "type": "NORMAL", "height": 0.2},
      {"timestamp": 1774615943, "utcOffset": -10, "type": "LOW",    "height": 0.0},
      {"timestamp": 1774635240, "utcOffset": -10, "type": "HIGH",   "height": 0.5}
    ]
  }
}
```

**`type` values:** `"HIGH"`, `"LOW"`, `"NORMAL"`

The `NORMAL` entries appear at every `intervalHours` boundary; `HIGH` and `LOW`
appear at the exact peak/trough timestamp.

---

#### `GET /kbyg/spots/forecasts/weather`

Air temperature, barometric pressure, weather condition icons, and
sunrise/sunset times.

**Auth required:** No

**Response sample:**
```json
{
  "associated": {
    "weatherIconPath": "https://wa.cdn-surfline.com/quiver/3.0.0/weathericons",
    "runInitializationTimestamp": 1774591200
  },
  "data": {
    "sunlightTimes": [
      {
        "midnight": 1774594800,
        "dawn": 1774617748,
        "sunrise": 1774619245,
        "sunset": 1774663778,
        "dusk": 1774665275,
        "midnightUTCOffset": -7,
        "dawnUTCOffset": -7,
        "sunriseUTCOffset": -7,
        "sunsetUTCOffset": -7,
        "duskUTCOffset": -7
      }
    ],
    "weather": [
      {
        "timestamp": 1774605600,
        "utcOffset": -10,
        "temperature": 70.0,
        "condition": "NIGHT_MOSTLY_CLOUDY",
        "pressure": 1014
      }
    ]
  }
}
```

**Common `condition` values:**
`CLEAR`, `MOSTLY_CLEAR`, `PARTLY_CLOUDY`, `MOSTLY_CLOUDY`, `OVERCAST`,
`FOG`, `LIGHT_RAIN`, `RAIN`, `HEAVY_RAIN`, `THUNDERSTORM`,
and `NIGHT_*` variants of each.

Weather icon URLs are formed as:
`{weatherIconPath}/{condition}.svg`

---

#### `GET /kbyg/spots/forecasts/conditions`

Human-written daily forecast narrative from a Surfline forecaster.

**Auth required:** No

**Response sample:**
```json
{
  "data": {
    "conditions": [
      {
        "timestamp": 1774594800,
        "forecastDay": "2026-03-27",
        "forecaster": {"name": "Schaler Perry", "avatar": "https://www.gravatar.com/..."},
        "human": true,
        "dayToWatch": false,
        "headline": "Clean start, light onshore texture this PM.",
        "observation": "Still a few waves to track down... [HTML allowed]",
        "am": {"timestamp": 0, "observation": "", "rating": null, "minHeight": 0, "maxHeight": 0},
        "pm": {"timestamp": 0, "observation": "", "rating": null, "minHeight": 0, "maxHeight": 0},
        "utcOffset": -7
      }
    ]
  }
}
```

---

#### `GET /kbyg/spots/forecasts/rating`

Per-hour algorithmic surf quality rating.

**Auth required:** No

**Response sample:**
```json
{
  "data": {
    "rating": [
      {
        "timestamp": 1774594800,
        "utcOffset": -7,
        "rating": {"key": "FAIR", "value": 3}
      }
    ]
  }
}
```

**Rating key to value mapping:**

| Key | Value | Description |
|-----|-------|-------------|
| `FLAT` | 0 | Flat / no surf |
| `VERY_POOR` | 1 | Very poor |
| `POOR` | 1 | Poor |
| `POOR_TO_FAIR` | 2 | Poor to fair |
| `FAIR` | 3 | Fair |
| `FAIR_TO_GOOD` | 4 | Fair to good |
| `GOOD` | 5 | Good |
| `VERY_GOOD` | 6 | Very good |
| `EPIC` | 6 | Epic |

---

### Region / Subregion Endpoints

#### `GET /kbyg/regions/overview`

Full overview of a subregion: all spots with current conditions, forecaster
info, and forecast status.

**Auth required:** No

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `subregionId` | string | Yes | Surfline subregion ID |

**Example:**
```
GET /kbyg/regions/overview?subregionId=58581a836630e24c44878fd6
```

**Response:** Returns `data.spots[]` — a list of every spot in the subregion
with current conditions, wave height, wind, tide, and camera list.

---

#### `GET /kbyg/regions/forecasts/conditions`

Region-level daily conditions forecast narrative.

**Auth required:** No

**Parameters:** `subregionId`, `days`

Same response structure as `GET /kbyg/spots/forecasts/conditions`.

---

#### `GET /kbyg/regions/forecasts/wave`

Region-level (representative offshore) wave forecast.

**Auth required:** No

**Parameters:** `subregionId`, `days`, `intervalHours`

Same response structure as `GET /kbyg/spots/forecasts/wave`.

---

### Search

#### `GET /search/site`

Search spots and news articles. Returns an Elasticsearch multi-search response
array.

**Auth required:** No

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `q` | string | - | Search query (required) |
| `querySize` | int | 10 | Max results per index |
| `suggestionSize` | int | 5 | Max autocomplete suggestions |
| `newsSearch` | bool | true | Include news article results |

**Example:**
```
GET /search/site?q=pipeline&querySize=5&suggestionSize=3&newsSearch=false
```

**Response:** A JSON array of Elasticsearch response objects.

- Index `0` contains **spot search hits** and **spot autocomplete suggestions**.
- Index `3` contains **news article hits**.

**Spot hit `_source` fields:**
```json
{
  "name": "Pipeline",
  "breadCrumbs": ["United States", "Hawaii", "Honolulu County", "O'ahu"],
  "location": {"lon": -158.0526, "lat": 21.66522},
  "href": "https://www.surfline.com/surf-report/pipeline/5842041f4e65fad6a7708890",
  "cams": ["58349eed3421b20545c4b56c", "58349ef6e411dc743a5d52cc"],
  "insightsCameraId": "58349eed3421b20545c4b56c",
  "humanReported": true
}
```

**Autocomplete suggestion extraction:**
```python
results = client.search("pipe", suggestion_size=5)
options = results[0]["suggest"]["spot-suggest"][0]["options"]
for opt in options:
    print(opt["_id"], opt["_source"]["name"])
```

---

### User Endpoints (Auth Required)

#### `POST /auth/token`

Obtain a JWT Bearer token.

**Auth required:** No (this is the auth endpoint)

```
POST /auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password&client_id=SurferApp&client_secret=SurferApp
&device_id=web&email=<email>&password=<password>
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

**Note:** Using JSON body returns an error — the endpoint strictly requires
`application/x-www-form-urlencoded` encoding.

---

#### `GET /user/favorites`

List of the authenticated user's saved spots.

**Auth required:** YES — `Authorization: Bearer <token>`

---

#### `GET /user/profile`

Authenticated user's account profile.

**Auth required:** YES

---

#### `GET /user/feeds`

Authenticated user's personalized feed.

**Auth required:** YES

---

## Camera URL Patterns

### Still Images (Public)
```
https://camstills.cdn-surfline.com/{region}/{alias}/latest_small.jpg
https://camstills.cdn-surfline.com/{region}/{alias}/latest_full.jpg
```

| Variable | Example | Description |
|----------|---------|-------------|
| `region` | `us-west-2` | AWS region prefix |
| `alias` | `hi-pipeline` | Camera slug |

Still images are refreshed approximately every 5 minutes.

### Pixelated Blurred Preview (Public)
```
https://camstills.cdn-surfline.com/{alias}/latest_small_pixelated.png
```

Shown to non-subscribers. Does not include the region prefix.

### HLS Live Stream (Premium Required)
```
https://hls.cdn-surfline.com/{region}/{alias}/playlist.m3u8
```

Returns HTTP 403 without a valid Surfline premium session cookie.

The `region` prefix depends on camera location:

| Prefix | Coverage |
|--------|---------|
| `oregon` | US West Coast, Hawaii, Americas |
| `ohio` | US East Coast |
| `ireland` | Europe |
| `east-au` | Australia East |
| `west-au` | Australia West |

The correct region for each camera is embedded in the `streamUrl` field
returned by `/kbyg/mapview` and `/kbyg/spots/reports`.

### Rewind Clips (Premium Required)
```
https://camrewinds.cdn-surfline.com/{alias}/{alias}.{resolution}.{YYYY-MM-DD}.mp4
```

| Variable | Example | Description |
|----------|---------|-------------|
| `alias` | `hi-pipeline` | Camera slug |
| `resolution` | `1500` | Video quality identifier (observed: 1500) |
| `YYYY-MM-DD` | `2026-03-27` | Date |

The `rewindClip` field in API responses provides the pre-built URL.
Accessing `camrewinds.cdn-surfline.com` without auth returns HTTP 403.

### Highlight Clips (Publicly Accessible)
```
https://highlights.cdn-surfline.com/us-west-2/clips/{cameraId}-{timestampStr}.mp4
https://highlights.cdn-surfline.com/us-west-2/thumbnails/{cameraId}-{timestampStr}.jpg
```

The `timestampStr` is in the format `20260327T161639370Z`.

**Confirmed:** Highlight clips and thumbnails return HTTP 200 without any
authentication (tested March 2026). The pre-built URLs are embedded in
`cam.highlights.url` and `cam.highlights.thumbUrl` in the API response.
Only cameras with `supportsHighlights: true` have these fields populated.

---

## Spot ID Discovery

Spot IDs are MongoDB ObjectIDs (24-char hex strings). There are several ways
to obtain them:

1. **Search API:** `GET /search/site?q=<name>` — fastest method.
2. **Mapview API:** `GET /kbyg/mapview?south=...&north=...&west=...&east=...`
   — returns all spots in a bounding box.
3. **Surfline URL:** The spot ID appears at the end of any Surfline surf report
   URL, e.g. `https://www.surfline.com/surf-report/pipeline/5842041f4e65fad6a7708890`.

### Well-Known Spot IDs

| Spot | ID |
|------|----|
| Pipeline, Hawaii | `5842041f4e65fad6a7708890` |
| Mavericks, California | `5842041f4e65fad6a7708864` |
| Trestles, California | `5842041f4e65fad6a7708877` |
| Rincon, California | `5842041f4e65fad6a77087f0` |
| Venice Beach, California | `5842041f4e65fad6a7708849` |
| Huntington St., OC | `58bdebbc82d034001252e3d2` |
| Jaws (Pe'ahi), Hawaii | `5842041f4e65fad6a770900e` |
| Teahupo'o, Tahiti | `5842041f4e65fad6a7708b15` |
| Kirra, Australia | `5842041f4e65fad6a7709a43` |
| Jeffreys Bay (J-Bay), SA | `5842041f4e65fad6a7709e38` |

### Well-Known Subregion IDs

| Subregion | ID |
|-----------|----|
| North Shore Oahu | `58581a836630e24c44878fcb` |
| North Orange County, CA | `58581a836630e24c44878fd6` |
| North San Diego, CA | `58581a836630e24c44878fd7` |
| South Orange County, CA | `58581a836630e24c4487900a` |
| South San Diego, CA | `58581a836630e24c4487900d` |

---

## Common Request Headers

Every request should include these headers (set automatically by `SurflineClient`):

```
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Origin: https://www.surfline.com
Referer: https://www.surfline.com/
Accept: application/json, text/plain, */*
```

For authenticated requests, also include:
```
Authorization: Bearer <token>
```

---

## Error Responses

| HTTP Status | Meaning |
|-------------|---------|
| `200 OK` | Success |
| `400 Bad Request` | Invalid parameters (e.g. `days` too large) |
| `401 Unauthorized` | Missing/invalid auth credentials |
| `403 Forbidden` | Premium-only resource (e.g. HLS stream) |
| `404 Not Found` | Endpoint or resource does not exist |

Error response body:
```json
{"message": "Error encountered"}
```

---

## Data Units

Default units returned by the API:

| Measurement | Default Unit | Alternatives |
|-------------|-------------|--------------|
| Wave height | FT (feet) | M (meters) |
| Swell height | FT (feet) | M (meters) |
| Wind speed | KTS (knots) | MPH, KPH |
| Temperature | F (Fahrenheit) | C (Celsius) |
| Tide height | FT (feet) | M (meters) |
| Pressure | MB (millibars) | — |
| Coordinates | Decimal degrees | — |
| Timestamps | Unix epoch (seconds) | — |

Override units using query parameters, e.g.:
```
?units[waveHeight]=M&units[windSpeed]=KPH&units[temperature]=C
```

---

## Client API Reference

### `SurflineClient(timeout=15, user_agent=...)`

Initialize the client. All requests include the required Origin/Referer headers
automatically.

### Authentication

| Method | Description |
|--------|-------------|
| `login(email, password)` | Authenticate and store Bearer token |
| `logout()` | Clear stored token |
| `is_authenticated` | Boolean property |

### Spot Data

| Method | Description |
|--------|-------------|
| `get_spot_report(spot_id)` | Full spot metadata + current conditions |
| `get_nearby_spots(spot_id)` | Spots near a given spot |
| `get_current_conditions(spot_id)` | Parsed current conditions dict |

### Forecasts

| Method | Description |
|--------|-------------|
| `get_wave_forecast(spot_id, days, interval_hours, units)` | Wave + swell forecast |
| `get_wind_forecast(spot_id, days, interval_hours, units)` | Wind forecast |
| `get_tide_forecast(spot_id, days)` | Tide heights |
| `get_weather_forecast(spot_id, days, interval_hours)` | Weather + sunlight |
| `get_surf_conditions(spot_id, days)` | Human-written conditions |
| `get_surf_rating(spot_id, days, interval_hours)` | Quality rating per hour |
| `get_forecast_summary(spot_id, days)` | Merged hourly forecast list |
| `get_tide_summary(spot_id, days)` | HIGH/LOW tide events only |

### Regions

| Method | Description |
|--------|-------------|
| `get_region_overview(subregion_id)` | All spots + conditions in a region |
| `get_region_conditions(subregion_id, days)` | Region forecast narrative |
| `get_region_wave_forecast(subregion_id, days, interval_hours)` | Regional wave forecast |

### Cameras

| Method | Description |
|--------|-------------|
| `get_cameras_in_bbox(south, north, west, east)` | All cameras in bounding box |
| `get_cameras_for_spot(spot_id)` | Cameras for a specific spot |
| `get_camera_still_url(alias, size, region)` | Build still image URL |
| `get_camera_stream_url(alias)` | Build HLS stream URL |
| `get_camera_rewind_url(alias, hour, date)` | Build rewind clip URL |
| `get_spot_thumbnail_url(spot_id, size)` | Build spot background photo URL |

### Search

| Method | Description |
|--------|-------------|
| `search(query, query_size, suggestion_size, include_news)` | Raw search response |
| `search_spots(query, limit)` | Simplified spot search |
| `search_suggestions(query, limit)` | Autocomplete suggestions |

### User (Auth Required)

| Method | Description |
|--------|-------------|
| `get_user_profile()` | Account profile |
| `get_favorites()` | Saved spots |
| `get_user_feeds()` | Personalized feed |

### Geo

| Method | Description |
|--------|-------------|
| `get_spots_in_bbox(south, north, west, east)` | All spots in bounding box |

---

## Global Camera Statistics (March 2026)

Confirmed by fetching `/kbyg/mapview` with global bounding box
(`south=-90, west=-180, north=90, east=180`):

| Metric | Count |
|--------|-------|
| Total surf spots | 9,042 |
| Spots with cameras | 693 |
| Total camera streams | 1,089 |
| Premium (subscription-required) cameras | 538 |
| Free cameras | 551 |

The global mapview response is approximately 22 MB uncompressed.

### Still Image CDN Regions

| CDN Bucket | Coverage |
|-----------|---------|
| `camstills.cdn-surfline.com/us-west-2/` | Americas, Hawaii, Pacific |
| `camstills.cdn-surfline.com/eu-west-1/` | Europe |

---

## Notes and Limitations

1. **Day limit:** Forecast endpoints accept up to 6 days without authentication.
   Attempting 16 days returns HTTP 400. Extended forecasts (16 days) are a
   premium feature.

2. **Rate limiting:** Surfline uses Cloudflare for DDoS protection. Aggressive
   polling will result in temporary blocks. Add `time.sleep(0.5)` between
   requests for high-volume use cases.

3. **Camera stream geo-gating:** HLS streams may also be geo-restricted in
   addition to the subscription requirement.

4. **Timestamp precision:** Tide HIGH/LOW events are returned at exact peak
   timestamps (not rounded to the hour interval).

5. **Legacy IDs:** Spots have both a MongoDB `_id` (24-char hex) and a
   `legacyId` (integer). The API uses the MongoDB ID. The legacy integer ID
   appears in some advertising/analytics fields and older URL patterns.

6. **Swell components:** Up to 6 swell train components are returned per
   timestamp. Components with `height=0` and `period=0` are padding and should
   be filtered out.

7. **`humanRelation` strings:** Wave height descriptions like
   `"Waist to shoulder"` are based on Surfline's proprietary scaling which
   differs from significant wave height. `surf.raw.min/max` gives the actual
   model heights.

---

## Terms of Service

This client uses Surfline's undocumented internal API. Usage is subject to
Surfline's Terms of Service. The API is not officially published and may change
without notice. Use responsibly and do not distribute scraped data commercially.
