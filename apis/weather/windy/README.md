# Windy.com API - Reverse Engineering Report

Reverse-engineered from Windy.com JS bundle v49.1.1 (build hash: `indeb7f`).
Date: 2026-03-25

---

## Summary

Windy.com operates two distinct API tiers:

1. **Internal API** (`node.windy.com`) - Used by the Windy web app itself. Many endpoints are publicly accessible without authentication. The app uses a custom `Accept` header format and Bearer token for authenticated calls.

2. **Public Developer API** (`api.windy.com`) - Official documented API requiring a key. Covers Point Forecast, Map Forecast (embed), and Webcams.

---

## Infrastructure Discovery

### Subdomains and Roles

| Host | Role |
|------|------|
| `node.windy.com` | Main backend: forecasts, services, radar, tiles |
| `ims.windy.com` | Image Map Server: weather overlay tiles |
| `tiles.windy.com` | Base map tiles (grayland, borders) |
| `sat.windy.com` | Satellite imagery data |
| `api.windy.com` | Official public API portal |
| `account.windy.com` | User authentication & accounts |
| `rdr.windy.com` | Redirect service |
| `img.windy.com` | Static images, user avatars |
| `embed.windy.com` | Embeddable map widget |
| `community.windy.com` | Community forum |
| `admin.windy.com` | Admin panel |

### Internal API Authentication

The internal API uses a two-layer auth system:

**Unauthenticated requests** (public endpoints):
```
Accept: application/json binary/gladad$indeb7f
```
The `indeb7f` suffix is the build hash of the JS bundle. It changes with each Windy release.

**Authenticated requests** (user-specific data):
```
Authorization: Bearer {userToken}
```
The `userToken` is stored in localStorage (`userToken` key) after login via `account.windy.com`.

**Tile authentication:**
```
GET /maptile/2.1/maptile/newest/satellite.day/{z}/{x}/{y}/256/jpg?token2={userToken}
```

---

## Discovered Endpoints

### 1. Internal Services (No Auth Required)

#### Location Detection
```
GET https://node.windy.com/services/umisteni?v=49.1.1&t=index&d=desktop
```
Returns IP-based geolocation (country, city, coordinates, timezone).

**Response:**
```json
{
  "country": "US",
  "region": "VA",
  "eu": "0",
  "timezone": "America/New_York",
  "city": "Ashburn",
  "ll": [39.0469, -77.4903],
  "metro": 511,
  "area": 20,
  "ip": "64.34.84.9"
}
```

#### Elevation
```
GET https://node.windy.com/services/elevation/{lat}/{lon}?v=49.1.1
```
Returns terrain elevation in meters (plain integer response).

**Example:** `GET /services/elevation/50.08/14.42` → `274`

#### Timezone
```
GET https://node.windy.com/services/v1/timezone/{lat}/{lon}?ts={ISO8601}&v=49.1.1
```
Returns timezone info including DST-aware offset.

**Response:**
```json
{
  "TZname": "Europe/Prague",
  "TZoffset": 1,
  "TZoffsetMin": 60,
  "TZoffsetFormatted": "+01:00",
  "TZabbrev": "GMT+1",
  "TZtype": "t",
  "nowObserved": "2026-03-25T01:00:00+01:00"
}
```

### 2. Forecast Metadata

#### Minifest (Model Manifest)
```
GET https://node.windy.com/metadata/v1.0/forecast/{model}/minifest.json?v=49.1.1&t=index&d=desktop
GET https://node.windy.com/metadata/v1.0/forecast/{model}/minifest.json?v=49.1.1&t=index&d=desktop&premium=true
```
Returns latest model run time, step schedule, and URL templates for data access.

**Available models:** `ecmwf-hres`, `gfs`, `nam-conus`, `nam-hawaii`, `nam-alaska`, `ecmwf-wam`, `gfs-wave`, `icon-eu`, `icon-d2`, `arome-france`, `arome-antilles`, `arome-reunion`

**Response:**
```json
{
  "dst": [[3, 3, 90], [3, 93, 144], [6, 150, 360]],
  "info": "2025080606",
  "ref": "2026-03-24T12:00:00Z",
  "update": "2026-03-24T19:55:45Z",
  "v": "2.4",
  "urls": {
    "citytile": "https://node.windy.com/citytile/v1.0/ecmwf-hres",
    "pointForecast": "https://node.windy.com/forecast/point/ecmwf-hres/v2.9",
    "imageServer": "https://ims.windy.com/im/v3.0/forecast/ecmwf-hres"
  }
}
```

**DST field explained:** `[[step_hours, from_forecast_hour, to_forecast_hour], ...]`
- `[3, 3, 90]` = 3-hour steps from forecast hour 3 to 90
- `[6, 150, 360]` = 6-hour steps from forecast hour 150 to 360

### 3. Point Forecast (Internal)

#### Current Conditions
```
GET https://node.windy.com/forecast/point/now/{model}/v1.0/{lat}/{lon}?refTime={ISO8601}
```
Returns current weather conditions at a point.

#### Full Time-Series Forecast
```
GET https://node.windy.com/forecast/point/{model}/v2.9/{lat}/{lon}
  ?refTime={ISO8601}
  &step=3
  &interpolate=true|false
  &extended=true|false   (premium)
```
For air quality models (cams/camsEu):
```
GET https://node.windy.com/forecast/airq/{model}/v1.0/{lat}/{lon}
```

**Note:** This endpoint appears to require authentication (Bearer token) for most calls. Use the public API at `api.windy.com` for unauthenticated access.

### 4. City Tile Forecast (No Auth Required)

```
GET https://node.windy.com/citytile/v1.0/{model}/{z}/{x}/{y}
  ?v=49.1.1
  &refTime={ISO8601}
  &labelsVersion=v1.7
  &step=3
```

Returns temperature forecasts (in Kelvin) for cities within a map tile. Used by the Windy app to render city temperature labels on the map.

**Response:**
```json
{
  "forecast": {
    "51.847/5.864": [288, 286, 285, 284, ...],
    "50.938/6.96": [290, 286, 284, ...]
  }
}
```
Keys are `lat/lon` strings; values are temperature arrays in Kelvin.

### 5. Radar

#### Live Radar Manifest
```
GET https://node.windy.com/radar2/composite/minifest2.json?v=49.1.1
```
Large JSON with tile availability:
```json
{
  "tiles": [
    [x, y, "lastUpdateISO", "startTimeISO"],
    ...
  ]
}
```

#### Archive Radar Manifest (Premium)
```
GET https://node.windy.com/radar2/archive/composite/minifest2.json?start={ISO8601}&end={ISO8601}
```

#### Radar Station Coverage
```
GET https://node.windy.com/radar2/composite/coverage.json
```
Returns flat array of `[lat, lon, radius_km, ...]` for ~1000+ global radar stations.

#### Radar Tiles
```
GET https://node.windy.com/radar2/composite/{timestamp}/{z}/{x}/{y}.png
```

### 6. Weather Map Tiles (Image Server)

#### Weather Overlay Tiles
```
GET https://ims.windy.com/im/v3.0/forecast/{model}/{refTime}/{level}/wm_grid_257/{z}/{x}/{y}/{overlay}-{level}.{ext}
```

**Example:**
```
GET https://ims.windy.com/im/v3.0/forecast/ecmwf-hres/2026-03-24T12:00:00Z/surface/wm_grid_257/5/16/10/wind-surface.jpg
```

- `model`: forecast model name
- `refTime`: ISO 8601 model reference time
- `level`: altitude level (`surface`, `850h`, etc.)
- `overlay`: weather parameter name
- `ext`: `jpg` for images, `gladad` for binary data

### 7. Base Map Tiles

#### Grayland Map (Windy's custom base map)
```
GET https://tiles.windy.com/tiles/v10.0/grayland/{z}/{x}/{y}.png
GET https://tiles.windy.com/tiles/v9.0/grayland/{z}/{x}/{y}.png
```

#### Orthophoto (Satellite base map)
```
GET https://tiles.windy.com/tiles/orto/v1.0/{z}/{z}-{x}-{y}.jpg
```

### 8. Satellite

#### Satellite Info
```
GET https://sat.windy.com/satellite/info.json?v=49.1.1
```

#### Satellite Archive (Premium)
```
GET https://sat.windy.com/satellite/archive/info.json?start={ISO8601}&end={ISO8601}
```

### 9. Webcams (Internal - Deprecated)

```
GET https://node.windy.com/webcams/v1.0/list?limit=50&offset=0
GET https://node.windy.com/webcams/v1.0/detail/{webcam_id}
GET https://node.windy.com/webcams/v2.0/archive/{webcam_id}?start={ISO8601}&end={ISO8601}
```

These endpoints appear deprecated. Use the official webcams API at `api.windy.com` instead.

---

## Official Public API (api.windy.com)

### Authentication

All official API endpoints require the header:
```
x-windy-api-key: YOUR_API_KEY
```
Or for Point Forecast, include `"key": "YOUR_API_KEY"` in the request body.

Get your API key at: https://api.windy.com/keys

**Note:** Different API products require different keys:
- Point Forecast API key
- Map Forecast API key
- Webcams API key

### Point Forecast API v2

```
POST https://api.windy.com/api/point-forecast/v2
Content-Type: application/json

{
  "lat": 50.4,
  "lon": 14.3,
  "model": "gfs",
  "levels": ["surface"],
  "parameters": ["temp", "wind", "precip", "pressure"],
  "key": "YOUR_API_KEY"
}
```

**Available models:** `arome`, `iconEu`, `gfs`, `gfsWave`, `namConus`, `namHawaii`, `namAlaska`, `cams`

Note: Model names in the public API differ from internal names:
- `gfs` (public) = `gfs` (internal) ✓ same
- `iconEu` (public) = `icon-eu` (internal)
- `gfsWave` (public) = `gfs-wave` (internal)
- `namConus` (public) = `nam-conus` (internal)

**Available levels:** `surface`, `1000h`, `950h`, `925h`, `900h`, `850h`, `800h`, `700h`, `600h`, `500h`, `400h`, `300h`, `200h`, `150h`

**Available parameters:**

| Parameter | Description | Unit |
|-----------|-------------|------|
| `temp` | Air temperature | K |
| `dewpoint` | Dew point temperature | K |
| `precip` | Precipitation (past 3h) | mm |
| `snowPrecip` | Snowfall (past 3h) | mm |
| `convPrecip` | Convective precipitation (past 3h) | mm |
| `wind` | Wind (returns `wind_u-*` + `wind_v-*`) | m/s |
| `windGust` | Wind gust speed | m/s |
| `cape` | Convective Available Potential Energy | J/kg |
| `ptype` | Precipitation type (0=none,1=rain,5=snow...) | code |
| `lclouds` | Low cloud coverage | % |
| `mclouds` | Medium cloud coverage | % |
| `hclouds` | High cloud coverage | % |
| `rh` | Relative humidity | % |
| `gh` | Geopotential height | m |
| `pressure` | Atmospheric pressure | Pa |
| `waves` | Wave height/period/direction | m, s, ° |
| `windWaves` | Wind wave height/period/direction | m, s, ° |
| `swell1` | Primary swell | m, s, ° |
| `swell2` | Secondary swell | m, s, ° |
| `so2sm` | SO₂ column (CAMS only) | µg/m³ |
| `dustsm` | Dust (CAMS only) | µg/m³ |
| `cosc` | CO concentration (CAMS only) | µg/m³ |

**Response structure:**
```json
{
  "ts": [1711274400000, 1711285200000, ...],
  "units": {
    "temp-surface": "K",
    "wind_u-surface": "m*s-1",
    "wind_v-surface": "m*s-1",
    "past3hprecip-surface": "mm"
  },
  "temp-surface": [285.2, 284.8, 283.1, ...],
  "wind_u-surface": [3.2, 2.8, 2.1, ...],
  "wind_v-surface": [-1.5, -2.1, -1.8, ...],
  "past3hprecip-surface": [0.0, 0.2, 1.4, ...]
}
```

Parameter keys follow the pattern `{parameter_name}-{level}`:
- `temp-surface`, `temp-850h`, `temp-500h`
- `wind_u-surface`, `wind_v-surface` (wind split into components)

Timestamps are Unix milliseconds. Convert: `datetime.fromtimestamp(ts/1000, tz=utc)`

### Webcams API v3

```
GET https://api.windy.com/webcams/api/v3/map/clusters
  ?northLat=50&southLat=49&eastLon=15&westLon=14
  &zoom=8
  &include=location,images
  &lang=en
x-windy-api-key: YOUR_WEBCAMS_KEY
```

```
GET https://api.windy.com/webcams/api/v3/webcams/{webcamId}?include=location,images
x-windy-api-key: YOUR_WEBCAMS_KEY
```

**Zoom level constraints** (max bounding box size):
| Zoom | Max Lat Range | Max Lon Range |
|------|--------------|--------------|
| 4 | 22.5° | 45° |
| 5 | 11.25° | 22.5° |
| 6 | 5.625° | 11.25° |
| 7 | 2.8° | 5.6° |
| 8 | 1.4° | 2.8° |

**Include options:** `categories`, `images`, `location`, `player`, `urls`

### Map Forecast Embed API

Embed a live weather map in an iframe:
```html
<iframe
  src="https://embed.windy.com/embed.html?width=800&height=600&lat=50&lon=14&zoom=5&overlay=wind&product=ecmwf&level=surface&key=YOUR_MAP_KEY"
  width="800" height="600">
</iframe>
```

Documentation: https://api.windy.com/map-forecast/docs

---

## JavaScript Bundle Analysis

Key variables found in `v/49.1.1.ind.eb7f/index.js`:

```javascript
// Host assignments
fe = "https://ims.windy.com"      // Image map server
ge = "https://node.windy.com"     // Main node server
ve = "https://tiles.windy.com"    // Tile server (v1)
be = "https://tiles.windy.com"    // Tile server (v2)
ye = "https://account.windy.com"  // Account server
Se = "https://sat.windy.com"      // Satellite server

// Version constants
we = "v1.7"   // Labels version (labelsVersion param)
_e = "v10.0"  // Tiles version

// Authentication pattern
userToken = localStorage.get("userToken")  // Bearer token
// Used as:
// - Authorization: Bearer {userToken}  (for API calls)
// - ?token2={userToken}                (for satellite tiles)

// Accept header for all internal API calls
"application/json binary/gladad$indeb7f"
// where "eb7f" is the build hash
```

---

## Environment Variables Found

In the SvelteKit app config (`api.windy.com`):

```json
{
  "PUBLIC_ACCOUNT_BASE_URL": "https://account.windy.com",
  "PUBLIC_PADDLE_ENVIRONMENT": "production",
  "PUBLIC_PAYMENTS_HOST": "https://node.windy.com",
  "PUBLIC_PADDLE_TOKEN": "live_55ca92d26d9eaffe916c31c881f",
  "PUBLIC_API_BASE_URL": "https://api.windy.com"
}
```

The Paddle token is used for subscription payment processing (not for API access).

---

## Python Client Usage

### Installation

```bash
pip install requests
```

### Quick Start - Internal API (No Key)

```python
from windy_client import WindyInternalClient, kelvin_to_celsius

client = WindyInternalClient()

# Get your location
loc = client.get_location()
print(f"You're in {loc['city']}, {loc['country']}")

# Get elevation for any coordinate
elevation = client.get_elevation(50.08, 14.42)
print(f"Prague elevation: {elevation}m")

# Get timezone info
tz = client.get_timezone(50.08, 14.42, "2026-03-25T12:00:00Z")
print(f"Timezone: {tz['TZname']} ({tz['TZoffsetFormatted']})")

# Get forecast minifest (model metadata)
minifest = client.get_forecast_minifest("gfs")
print(f"Latest GFS run: {minifest['ref']}")

# Get city temperatures for a map tile
tile_data = client.get_citytile_forecast(
    model="gfs",
    z=7, x=71, y=44,  # Tile covering central Europe
    ref_time=minifest["ref"]
)
for coords, temps in list(tile_data["forecast"].items())[:3]:
    print(f"  {coords}: {kelvin_to_celsius(temps[0]):.1f}°C")
```

### Public API (Requires Key)

```python
from windy_client import WindyPublicAPIClient, kelvin_to_celsius, wind_uv_to_speed_direction, parse_forecast_timestamps

client = WindyPublicAPIClient(api_key="YOUR_KEY_HERE")

# Get GFS forecast for London
data = client.get_point_forecast(
    lat=51.5, lon=-0.12,
    model="gfs",
    levels=["surface"],
    parameters=["temp", "wind", "precip", "pressure", "windGust"]
)

# Parse timestamps
times = parse_forecast_timestamps(data["ts"])
temps = [kelvin_to_celsius(t) for t in data["temp-surface"]]

# Get wind speed and direction
u = data["wind_u-surface"]
v = data["wind_v-surface"]
speeds_and_dirs = [wind_uv_to_speed_direction(u[i], v[i]) for i in range(len(u))]

# Print 24-hour forecast
for i in range(8):  # 8 x 3h = 24 hours
    speed, direction = speeds_and_dirs[i]
    print(f"{times[i].strftime('%Y-%m-%d %H:%M')}: "
          f"{temps[i]:.1f}°C, "
          f"Wind {speed:.1f}m/s from {direction:.0f}°")

# Get wave forecast
wave_data = client.get_point_forecast(
    lat=48.0, lon=-5.0,  # Off Brittany coast
    model="gfsWave",
    levels=["surface"],
    parameters=["waves", "windWaves", "swell1"]
)

# Get multi-pressure-level atmospheric profile
profile = client.get_point_forecast_multi_level(lat=48.86, lon=2.35)

# Get webcams near Paris
webcams = client.get_webcams_nearby(lat=48.86, lon=2.35, radius_km=50)
print(f"Found {len(webcams)} webcams near Paris")

# Generate embed URL for iframe
embed_url = client.get_embed_url(
    lat=48.86, lon=2.35, zoom=6,
    overlay="rain", product="ecmwf"
)
print(f"Embed URL: {embed_url}")
```

---

## Rate Limits and Terms of Service

- The internal API (`node.windy.com`) is intended for the Windy.com web application only
- The public API (`api.windy.com`) has documented rate limits per tier (Free/Paid)
- Always check Windy's Terms of Service before using any undocumented endpoints
- The `x-windy-api-key` header is required for all official API endpoints
- Windy is now part of the Windyty, S.E. company and also integrates meteoblue APIs

---

## Forecast Models Reference

| Internal ID | Public API ID | Description | Provider |
|-------------|--------------|-------------|---------|
| `ecmwf-hres` | (premium only) | ECMWF High Resolution | ECMWF |
| `ecmwf-wam` | (premium only) | ECMWF Wave Model | ECMWF |
| `gfs` | `gfs` | GFS Global | NOAA |
| `gfs-wave` | `gfsWave` | GFS Wave Model | NOAA |
| `icon-eu` | `iconEu` | ICON Europe | DWD |
| `icon-d2` | - | ICON-D2 Germany | DWD |
| `nam-conus` | `namConus` | NAM Continental US | NOAA |
| `nam-hawaii` | `namHawaii` | NAM Hawaii | NOAA |
| `nam-alaska` | `namAlaska` | NAM Alaska | NOAA |
| `arome-france` | `arome` | AROME France | Meteo-France |
| `arome-antilles` | - | AROME Antilles | Meteo-France |
| `arome-reunion` | - | AROME Reunion | Meteo-France |
| `cams` | `cams` | CAMS Air Quality Global | Copernicus |

---

*Generated by reverse engineering Windy.com v49.1.1*
