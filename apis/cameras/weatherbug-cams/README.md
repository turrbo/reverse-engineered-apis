# WeatherBug Camera API - Reverse Engineering Report & Python Client

> Reverse-engineered from https://www.weatherbug.com/cameras/
> Discovered via static JS analysis of the bundled frontend (main.js, 4.5 MB)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Authentication (HMAC)](#authentication-hmac)
3. [Credentials](#credentials)
4. [Service Base URLs](#service-base-urls)
5. [Discovered Endpoints](#discovered-endpoints)
   - [Camera Endpoints](#camera-endpoints)
   - [Traffic Camera Endpoints](#traffic-camera-endpoints)
   - [Location Endpoints](#location-endpoints)
   - [Observation Endpoints](#observation-endpoints)
   - [Forecast Endpoints](#forecast-endpoints)
   - [Pollen Endpoint](#pollen-endpoint)
   - [Map/GIV Endpoints](#mapgiv-endpoints)
6. [CDN Patterns](#cdn-patterns)
7. [Python Client Usage](#python-client-usage)
8. [Raw HTTP Examples](#raw-http-examples)
9. [Notes and Caveats](#notes-and-caveats)

---

## Architecture Overview

WeatherBug's web frontend (weatherbug.com) is a hybrid AngularJS + React application that
communicates with a backend microservices platform called **Pulse**. Each service type has
its own subdomain under `pulse.weatherbug.net`. All API requests are authenticated with an
HMAC-SHA256 signature appended as query parameters.

The infrastructure was discovered by:
1. Downloading the HTML page (`/cameras/`) which embeds `window._config` as a JSON literal
2. Downloading the main JS bundle (`/dist/main.*.js`, ~4.5 MB)
3. Locating the `PulseHmac` class (webpack module 8349) which implements the signature algorithm
4. Locating the `window._config.Pulse` object which contains `ID` and `Secret`
5. Locating `window._config.BaseURLs` which maps service names to base URLs

---

## Authentication (HMAC)

Every request to `*.pulse.weatherbug.net` requires three additional query parameters:

| Parameter   | Description |
|-------------|-------------|
| `authid`    | Client identifier string (e.g. `WBWebV3`) |
| `timestamp` | Unix timestamp in seconds (integer) |
| `hash`      | HMAC-SHA256 of the canonical request string, Base64-encoded |

### Canonical Request Format

```
METHOD\n
/path\n
body_or_empty_string\n
timestamp
[\nSORTED_PARAM_KEY\nSORTED_PARAM_VALUE\n...]
```

Rules:
- `METHOD` is uppercase (e.g. `GET`)
- Path must start with `/`
- Body is the raw request body string, or empty string for GET requests
- Timestamp is an integer (Unix seconds)
- Query parameters are appended sorted **case-insensitively** by key
- Only non-null parameters are included in the canonical string
- Parameters in the canonical string are the business params only (not authid/timestamp/hash)
- HMAC key is the `Pulse.Secret` string (UTF-8 encoded)
- HMAC output is Base64-encoded

### Python Implementation

```python
import hmac, hashlib, base64, time

def compute_hmac(method, path, params, secret, auth_id, body="", timestamp=None):
    if timestamp is None:
        timestamp = int(time.time())
    method = method.upper()
    if not path.startswith("/"):
        path = "/" + path

    # Sort params case-insensitively, skip None values
    param_parts = []
    if params:
        for k in sorted(params.keys(), key=str.upper):
            if params[k] is not None:
                param_parts.append(f"{k}\n{params[k]}")

    message = f"{method}\n{path}\n{body or ''}\n{timestamp}"
    if param_parts:
        message += "\n" + "\n".join(param_parts)

    raw = hmac.new(secret.encode(), message.encode(), hashlib.sha256)
    return {
        "hash": base64.b64encode(raw.digest()).decode(),
        "authid": auth_id,
        "timestamp": timestamp,
    }
```

### Source Reference

Found in webpack module `8349` in `/dist/main.*.js`:

```js
{key:"getHashedURL",value:function(method, path, params, body, date=new Date()) {
    method = method.toUpperCase();
    var timestamp = Math.floor(date.getTime() / 1000);
    var paramParts = [];
    var sortedKeys = Object.keys(params);
    sortedKeys.sort((a,b) => a.toUpperCase().localeCompare(b.toUpperCase()));
    for (var k of sortedKeys) {
        if (params.hasOwnProperty(k) && params[k] != null)
            paramParts.push(k + "\n" + params[k]);
    }
    var msg = method + "\n" + (path.startsWith("/") ? path : "/" + path) + "\n" + (body||"") + "\n" + timestamp;
    if (paramParts.length > 0) msg += "\n" + paramParts.join("\n");
    return {
        hmac: CryptoJS.HmacSHA256(msg, this._secret).toString(CryptoJS.enc.Base64),
        authid: this._authId,
        timestamp: timestamp
    };
}}
```

---

## Credentials

Credentials are embedded in `window._config` on every page (injected server-side):

```json
{
  "Pulse": {
    "ID":     "WBWebV3",
    "Secret": "48f00e3e43804ffd98a112f45fc299a5"
  }
}
```

**Note**: These are the embedded web-client credentials, publicly visible in the page source.
They may be rotated by WeatherBug at any time.

Additional app metadata embedded in the page:
- `WB_AppKey`: `wxweb`
- `AppVersion`: `9.8.0`
- `AuthClientSettings.ClientId`: `wbweb_oidc` (OIDC client, OAuth2 with auth.weatherbug.com)
- `Firebase.ApiKey`: `AIzaSyA8T1zu-jM-JOT8Ph1mGEMtB9QvzBh6f1I`
- `Mapbox.PublicKey`: `<MAPBOX_PUBLIC_KEY>`

---

## Service Base URLs

From `window._config.BaseURLs`:

| Service Name   | Base URL |
|----------------|----------|
| Cameras        | `https://web-cam.pulse.weatherbug.net` |
| Traffic Cams   | `https://web-trffc.pulse.weatherbug.net` |
| Observations   | `https://web-obs.pulse.weatherbug.net` |
| Forecasts      | `https://web-for.pulse.weatherbug.net` |
| Locations      | `https://web-loc.pulse.weatherbug.net` |
| AQI            | `https://web-aqi.pulse.weatherbug.net` |
| Pollen         | `https://web-plln.pulse.weatherbug.net` |
| Maps/GIV       | `https://web-maps.pulse.weatherbug.net` |
| Maps Tile CDN  | `https://{s}web-maps.api.weatherbug.net` (s = a/b/c/d) |
| Alerts         | `https://web-alert.pulse.weatherbug.net` |
| Lightning      | `https://web-lx.pulse.weatherbug.net` |
| Hurricane      | `https://web-hur.pulse.weatherbug.net` |
| UV Index       | `https://web-uv.pulse.weatherbug.net` |
| Snow/Ski       | `https://web-snwski.pulse.weatherbug.net` |
| Lifestyle      | `https://web-life.pulse.weatherbug.net` |
| AdTargeting    | `https://web-ads.pulse.weatherbug.net` |
| Feedback/Obs   | `https://desk-obs.pulse.weatherbug.net` |
| Video/Content  | `https://web-con.pulse.weatherbug.net` |
| Stories        | `https://web-story.pulse.weatherbug.net` |
| Logging        | `https://web-clog.pulse.weatherbug.net` |
| Legal          | `https://web-legal.pulse.weatherbug.net` |
| Push/Notify    | `https://web-push.pulse.weatherbug.net` |
| Almanac        | `https://web-alm.pulse.weatherbug.net` |
| Auth           | `https://auth.weatherbug.com/` |
| Icon CDN       | `https://legacyicons-con.cdn.weatherbug.net` |

---

## Discovered Endpoints

All endpoints require HMAC authentication unless otherwise noted.

### Camera Endpoints

**Base URL**: `https://web-cam.pulse.weatherbug.net`

---

#### `GET /data/cameras/v2/CameraList`

List weather cameras within a geographic radius.

**Parameters**:

| Param | Type   | Required | Description |
|-------|--------|----------|-------------|
| `la`  | float  | Yes | Latitude of center point |
| `lo`  | float  | Yes | Longitude of center point |
| `r`   | int    | Yes | Radius in **miles** (must be > 0 and < ~3963) |
| `ns`  | int    | No  | Maximum number of stations to return |
| `ii`  | int    | No  | Include images (1=true, 0=false; default 0) |
| `verbose` | str | No | "true" for verbose response |

**Response Structure**:
```json
{
  "Code": 200,
  "ErrorMessage": null,
  "Result": [
    {
      "id": "YRKPS",
      "name": "York Prep School",
      "city": "New York",
      "state": "New York",
      "lat": 40.7741,
      "lng": -73.9795,
      "isHD": true,
      "distance": 4.46,
      "image": null,
      "images": null,
      "thumbnail": null
    }
  ]
}
```

When `ii=1`, `image`, `thumbnail`, and `images` are populated with CDN URLs.

---

#### `GET /data/cameras/v2/CameraAnimations`

Get image URLs and timelapse history for a specific weather camera.

**Parameters**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `ci`  | str  | Yes | Camera/station ID (e.g. `YRKPS`) |
| `itl` | int  | No  | Include timelapse frames (1=true; fetches ~24h of 15-min interval images) |

**Response Structure**:
```json
{
  "Code": 200,
  "Result": {
    "Id": "YRKPS",
    "Name": "York Prep School",
    "City": "New York",
    "State": "New York",
    "Lat": 40.7741,
    "Lng": -73.9795,
    "IsHD": true,
    "Image": "https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/032720261259_l.jpg",
    "Thumbnail": "https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/032720261259_t.jpg",
    "Images": [
      "https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/26/032620261314_l.jpg",
      "..."
    ]
  }
}
```

`Images` contains approximately 96 frames (every 15 minutes for the past 24 hours) when `itl=1`.

---

### Traffic Camera Endpoints

**Base URL**: `https://web-trffc.pulse.weatherbug.net`

---

#### `GET /data/traffic/v2`

List traffic cameras within a geographic area.

**Parameters**:

| Param        | Type   | Required | Description |
|--------------|--------|----------|-------------|
| `location`   | str    | Yes | `{lat},{lon}` coordinate pair |
| `locationType` | str  | Yes | Must be `latitudelongitude` |
| `radius`     | int    | No  | Search radius in **meters** (default ~804,670 = 500 miles) |
| `maxCount`   | int    | No  | Maximum cameras to return |
| `verbose`    | str    | No  | "true" for full response |

**Response Structure**:
```json
{
  "result": {
    "lastUpdatedDateUtc": 1774630840,
    "cameras": [
      {
        "cameraId": 466222,
        "name": "Brooklyn Bridge @ Centre Street",
        "latitude": 40.712423,
        "longitude": -74.004937,
        "distance": 0.06,
        "providerName": "New York City DOT",
        "hasStreamingVideo": false,
        "orientation": "UNKNOWN",
        "disabled": false,
        "smallImageUrl": "https://ie.trafficland.com/v2.0/466222/half?system=weatherbug-web&pubtoken=...&refreshRate=30000",
        "largeImageUrl": "https://ie.trafficland.com/v2.0/466222/full?system=weatherbug-web&pubtoken=...&refreshRate=30000",
        "jumboImageUrl": "https://ie.trafficland.com/v2.0/466222/huge?system=weatherbug-web&pubtoken=...&refreshRate=30000",
        "smallImageUrlCache": "https://cmn-trffc.pulse.weatherbug.net/media/trffc/v2/img/small?system=weatherbug-web&id=466222&key=...&rate=30000",
        "largeImageUrlCache": "https://cmn-trffc.pulse.weatherbug.net/media/trffc/v2/img/large?...",
        "jumboImageUrlCache": "https://cmn-trffc.pulse.weatherbug.net/media/trffc/v2/img/jumbo?...",
        "streams": null
      }
    ]
  }
}
```

**Traffic image size names**: `half` (small), `full` (large), `huge` (jumbo)

Traffic images have a token that expires; the `*UrlCache` variants via WeatherBug's proxy are more stable.

---

### Location Endpoints

**Base URL**: `https://web-loc.pulse.weatherbug.net`

---

#### `GET /data/locations/v3/location`

Search for locations by city name, postal code, or partial string.

**Parameters**:

| Param          | Type | Required | Description |
|----------------|------|----------|-------------|
| `searchString` | str  | Yes | Query string (city name, ZIP code, etc.) |
| `maxResults`   | int  | No  | Maximum results (default varies) |
| `verbose`      | str  | No  | "true" |

**Response**: Array of location objects.

```json
[
  {
    "CityId": "US36N0028",
    "CityName": "New York",
    "TerritoryName": "New York",
    "TerritoryAbbr": "NY",
    "CountryIso2Code": "US",
    "Latitude": 40.748,
    "Longitude": -73.9862,
    "PostalCode": "10001",
    "SlugName": "new-york-ny-10001",
    "DisplayCompositeName": "New York, New York"
  }
]
```

---

#### `GET /data/locations/v3/bySlugName`

Look up a location by WeatherBug slug name.

**Parameters**:

| Param      | Type | Required | Description |
|------------|------|----------|-------------|
| `slugname` | str  | Yes | WeatherBug slug (e.g. `new-york-ny-10001`) |
| `verbose`  | str  | No  | "true" |

**Response**: Single location object (same structure as above).

---

#### `GET /data/locations/v3/closestCity`

Find the closest city to given coordinates.

**Parameters**:

| Param          | Type   | Required | Description |
|----------------|--------|----------|-------------|
| `location`     | str    | Yes | `{lat},{lon}` |
| `locationtype` | str    | Yes | Must be `latitudelongitude` |
| `verbose`      | str    | No  | "true" |

**Response**:
```json
{
  "CityId": "US36N0028",
  "DisplayCompositeName": "New York City, New York",
  "SlugName": "new-york-ny-10001",
  "Latitude": 40.748,
  "Longitude": -73.9862,
  "PostalCode": "10001",
  "Dma": "501"
}
```

---

#### `GET /data/locations/v1/CityByCityId`

Fetch full city details by WeatherBug city ID.

**Parameters**:

| Param    | Type | Required | Description |
|----------|------|----------|-------------|
| `cityId` | str  | Yes | WeatherBug city ID (e.g. `US36N0028`) |
| `verbose` | str | No  | "true" |

**Response**: Extended city object including `AqiId`, `ForecastZoneId`, `PollenId`, `FipsCountry`.

---

### Observation Endpoints

**Base URL**: `https://web-obs.pulse.weatherbug.net`

---

#### `GET /data/observations/v4/current`

Get current weather conditions at a location.

**Parameters**:

| Param          | Type | Required | Description |
|----------------|------|----------|-------------|
| `location`     | str  | Yes | `{lat},{lon}` |
| `locationtype` | str  | Yes | Must be `latitudelongitude` |
| `units`        | int  | No  | `1` = Imperial (°F, mph, inches), `2` = Metric |
| `verbose`      | str  | No  | "true" |

**Response** includes:
- `observation`: Current weather fields (temperature, humidity, windSpeed, windDirection, dewPoint, pressureSeaLevel, rainDaily, iconCode, iconDescription, observationTimeUtcStr)
- `highLow`: Today's high/low values
- `station`: Observation station metadata

---

### Forecast Endpoints

**Base URL**: `https://web-for.pulse.weatherbug.net`

---

#### `GET /data/forecasts/v2/daily`

Get 10-day daily forecast.

**Parameters**: Same as observations (location, locationtype, units, verbose).

**Response** includes `dailyForecastPeriods` array with one entry per half-day (day/night).

---

#### `GET /data/forecasts/v2/hourly`

Get hourly forecast.

**Parameters**: Same as observations.

**Response** includes `hourlyForecastPeriod` array with one entry per hour.

---

### Pollen Endpoint

**Base URL**: `https://web-plln.pulse.weatherbug.net`

---

#### `GET /data/lifestyle/pollen/v1/forecast`

Get pollen forecast for a location.

**Parameters**:

| Param       | Type  | Required | Description |
|-------------|-------|----------|-------------|
| `latitude`  | float | Yes | Latitude |
| `longitude` | float | Yes | Longitude |
| `verbose`   | str   | No  | "true" |

**Response**:
```json
{
  "result": {
    "pollenIndex": 6.8,
    "cityName": "NEW YORK",
    "state": "NY",
    "techDiscussion": "Based on past pollen counts...",
    "techDiscussionToday": "..."
  }
}
```

---

### Map/GIV Endpoints

**Base URL**: `https://web-maps.pulse.weatherbug.net`

---

#### `GET /giv/layers/v1`

Get the list of available map layers for a location.

**Parameters**:

| Param                     | Type  | Required | Description |
|---------------------------|-------|----------|-------------|
| `ViewedLocationLatitude`  | float | Yes | Latitude |
| `ViewedLocationLongitude` | float | Yes | Longitude |

**Response**: Returns `r.ls` — array of layer objects:

```json
{
  "r": {
    "ls": [
      {
        "id": "Radar.Global",
        "l": "Radar",
        "vid": "radar",
        "df": "raster",
        "al": 0.7,
        "minz": 0,
        "maxz": 18,
        "d": "Global Radar",
        "b": {"e": 180, "n": 85.05, "s": -85.05, "w": -180}
      }
    ]
  }
}
```

**Known Layer IDs**:

| Layer ID | Label |
|----------|-------|
| `Radar.Global` | Radar |
| `lxflash-radar-consumer-web` | Storm Tracker (radar + lightning) |
| `GlobalSatellite` | Satellite (IR) |
| `Contour.Observed.Pollen.Blur` | Pollen |
| `nws-alerts` | NWS Alerts |
| `en-alerts` | Thunderstorm Alerts (Earth Networks DTA) |
| `lxflash-consumer` | Lightning |
| `Contour.Observed.DailyRain` | Precipitation |
| `Contour.Observed.Temperature` | Temperature |
| `Observed.Temperature` | Local Temperature (station dots) |
| `Contour.Observed.Pressure.SeaLevel` | Pressure |
| `Observed.Pressure.SeaLevel` | Local Pressure (station dots) |
| `Contour.Observed.Temperature.HeatIndex` | Heat Index |
| `Contour.Observed.WindChill` | Wind Chill |
| `Contour.Observed.Humidity` | Humidity |
| `Contour.Observed.Wind` | Wind |

---

#### `GET /giv/presentation/legenddata`

Get legend data for a specific map layer.

**Parameters**: `lid` (layer ID), `ViewedLocationLatitude`, `ViewedLocationLongitude`

---

## CDN Patterns

### Weather Camera Images

**CDN Base**: `https://cameras-cam.cdn.weatherbug.net` (no authentication required)

**URL Pattern**:
```
https://cameras-cam.cdn.weatherbug.net/{STATION_ID}/{YYYY}/{MM}/{DD}/{MMDDYYHHmm}_{size}.jpg
```

**Timestamp format**: `{MM}{DD}{YY}{HH}{mm}` — note the 2-digit year

**Size suffixes**:
| Suffix | Description | Approx. Size |
|--------|-------------|--------------|
| `_l`   | Large (full resolution) | ~150 KB |
| `_t`   | Thumbnail | ~7 KB |
| `_s`   | Small | ~16 KB |

**Example**:
```
https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/032720261259_l.jpg
                                        ^     ^    ^  ^  ^           ^
                                        ID    Year Mo Day MMDDYYHHmm size
```

Images update approximately every 15 minutes.

### Traffic Camera Images

Traffic images are sourced from **Trafficland** (a third-party traffic camera aggregator) via WeatherBug's proxy:

**Direct Trafficland URL**:
```
https://ie.trafficland.com/v2.0/{id}/{size}?system=weatherbug-web&pubtoken={token}&refreshRate=30000
```
Sizes: `half`, `full`, `huge`

**WeatherBug Proxy URL** (more stable, recommended):
```
https://cmn-trffc.pulse.weatherbug.net/media/trffc/v2/img/{size}?system=weatherbug-web&id={id}&key={token}&rate=30000
```
Sizes: `small`, `large`, `jumbo`

Tokens are per-camera and embedded in the API response. They appear to be long-lived session tokens.

### Map Tiles

**Base**: `https://{sub}web-maps.api.weatherbug.net`
**Subdomains**: `a`, `b`, `c`, `d` (for load balancing)

**URL Pattern** (standard XYZ/slippy-map tile format):
```
https://aweb-maps.api.weatherbug.net/{layerId}/{z}/{x}/{y}.png
```

**Example**:
```
https://aweb-maps.api.weatherbug.net/Radar.Global/5/8/12.png
```

Tiles require no authentication and are compatible with standard mapping libraries (Leaflet, OpenLayers, Mapbox GL).

### Weather Icons

```
https://legacyicons-con.cdn.weatherbug.net/resources/v1/resource/IconByCodeV1
  ?iconset=forecast&iconSize=svglarge&iconCode={CODE}&token=99999999-9999-9999-9999-999999999999
```

The token `99999999-9999-9999-9999-999999999999` is the public anonymous access token.

---

## Python Client Usage

### Installation

```bash
pip install requests
```

### Basic Usage

```python
from weatherbug_cams_client import WeatherBugClient

client = WeatherBugClient()
```

### Find Cameras by Location

```python
# By coordinates
cameras = client.get_weather_cameras_by_coords(
    lat=40.71, lon=-74.01,
    radius_miles=100,
    max_stations=20,
)
for cam in cameras:
    print(f"{cam['name']} ({cam['id']}) - {cam['distance']:.1f} mi")

# By ZIP code
cameras = client.get_weather_cameras_by_zip("10001", radius_miles=50)

# By any location string (city name, ZIP, or lat,lon)
cameras = client.find_cameras_near("Denver, CO", radius_miles=100)
cameras = client.find_cameras_near("80203")
cameras = client.find_cameras_near("40.71,-74.01")
```

### Get Camera Images

```python
# Get latest image URL for a camera
url = client.get_latest_camera_image_url("YRKPS", size="l")
print(url)
# => https://cameras-cam.cdn.weatherbug.net/YRKPS/2026/03/27/032720261259_l.jpg

# Get detail with 24h timelapse frames
detail = client.get_camera_detail("YRKPS", include_timelapse=True)
print(detail['Image'])       # Latest large image URL
print(detail['Thumbnail'])   # Latest thumbnail URL
for frame in detail['Images']:  # ~96 historical frames
    print(frame)

# Download the image directly (no auth needed)
import requests
resp = requests.get(url)
with open("camera.jpg", "wb") as f:
    f.write(resp.content)
```

### Traffic Cameras

```python
cams = client.get_traffic_cameras(40.71, -74.01, radius_meters=5000, max_count=10)
for cam in cams:
    print(f"{cam['name']} - {cam['providerName']}")
    print(f"  Large: {cam['largeImageUrl']}")
    print(f"  Proxy: {cam['largeImageUrlCache']}")  # more stable URL
```

### Location Search

```python
# Search by name or ZIP
results = client.search_location("Seattle, WA")
results = client.search_location("98101")  # ZIP code

# Get closest city to coordinates
city = client.get_closest_city(47.61, -122.33)
print(city['DisplayCompositeName'])   # "Seattle, Washington"
print(city['SlugName'])               # "seattle-wa-98101"

# Look up by slug
city = client.get_location_by_slug("seattle-wa-98101")
```

### Weather Data at Camera Location

```python
# Get weather and camera images together
data = client.get_camera_with_weather("YRKPS")
print(data['camera']['Name'])
print(data['observation']['observation']['temperature'])  # current temp
print(data['forecast']['dailyForecastPeriods'][0]['summaryDescription'])

# Individual weather endpoints
obs = client.get_current_observations(40.71, -74.01)
print(obs['observation']['temperature'])
print(obs['observation']['iconDescription'])

forecast = client.get_daily_forecast(40.71, -74.01, units=1)  # 1=imperial, 2=metric
hourly   = client.get_hourly_forecast(40.71, -74.01)

pollen = client.get_pollen_forecast(40.71, -74.01)
print(pollen['result']['pollenIndex'])
```

### Map Tiles

```python
# List available layers
layers = client.get_map_layers(40.71, -74.01)
for layer in layers:
    print(f"{layer['l']} ({layer['id']})")

# Build tile URL (compatible with Leaflet, OpenLayers, etc.)
tile_url = client.build_tile_url("Radar.Global", z=5, x=8, y=12, subdomain="a")
# => https://aweb-maps.api.weatherbug.net/Radar.Global/5/8/12.png

# Leaflet integration example:
# L.tileLayer('https://aweb-maps.api.weatherbug.net/Radar.Global/{z}/{x}/{y}.png', {
#     subdomains: ['a','b','c','d'],
#     attribution: 'WeatherBug'
# }).addTo(map);
```

### Custom HMAC Signing

You can sign requests manually to call any undiscovered endpoints:

```python
from weatherbug_cams_client import _compute_hmac
import requests

sig = _compute_hmac("GET", "/data/some/endpoint", {"param1": "value1"},
                    secret="48f00e3e43804ffd98a112f45fc299a5",
                    auth_id="WBWebV3")
params = {"param1": "value1", **sig}
resp = requests.get("https://web-cam.pulse.weatherbug.net/data/some/endpoint", params=params)
```

---

## Raw HTTP Examples

### Weather Cameras Near NYC

```http
GET /data/cameras/v2/CameraList?la=40.7128&lo=-74.0060&r=100&ns=20&verbose=true&authid=WBWebV3&timestamp=1774630686&hash=G3ry...%3D
Host: web-cam.pulse.weatherbug.net
Accept: application/json
Origin: https://www.weatherbug.com
Referer: https://www.weatherbug.com/
```

### Camera Detail

```http
GET /data/cameras/v2/CameraAnimations?ci=YRKPS&itl=1&authid=WBWebV3&timestamp=...&hash=...
Host: web-cam.pulse.weatherbug.net
```

### Current Weather

```http
GET /data/observations/v4/current?location=40.7128%2C-74.0060&locationtype=latitudelongitude&units=1&verbose=true&authid=WBWebV3&timestamp=...&hash=...
Host: web-obs.pulse.weatherbug.net
```

---

## Notes and Caveats

1. **Credential Rotation**: The embedded credentials (`WBWebV3` / `48f00e3e...`) are baked into
   the compiled JS bundle and may be rotated when WeatherBug updates their site. If requests
   return 401/403, re-extract from a fresh page load.

2. **Rate Limiting**: No explicit rate limits were observed during testing, but as reverse-engineered
   credentials, high request volumes may trigger blocks. The polling intervals hardcoded in the
   app are: cameras = 1800s (30 min), observations = 300s (5 min), forecasts = 3600s (1 hr).

3. **Camera Coverage**: Weather cameras are primarily US-based Earth Networks weather stations.
   Traffic cameras are sourced from Trafficland's network and cover major US metropolitan areas.

4. **Camera ID Format**: Weather camera IDs are 5-character alphanumeric station codes (e.g.
   `YRKPS`). Traffic camera IDs are numeric integers (e.g. `466222`).

5. **Image Frequency**: Weather camera images update approximately every 15 minutes. Traffic
   camera images update more frequently (typically every 30 seconds per the `refreshRate=30000`
   parameter in URLs).

6. **Timestamp in Image URLs**: The filename `032720261259` decodes as:
   `{MM=03}{DD=27}{YY=26}{HH=12}{mm=59}` = March 27, 2026 at 12:59 UTC.
   Note: The year uses 2 digits.

7. **Units**: Weather APIs accept `units=1` (Imperial: °F, mph, inches, inHg) or
   `units=2` (Metric: °C, km/h, mm, hPa). The string codes `"e"`, `"m"` from the
   Wunderground/Weather.com API do NOT work here.

8. **Location Types**: The only validated `locationtype` for most services is
   `latitudelongitude`. The format is `"{lat},{lon}"` (comma-separated, no spaces).

9. **GIV Tiles**: Map tiles are served as standard XYZ/Slippy-map tiles with no
   authentication required on the CDN. They are compatible with any web mapping library.

10. **User Authentication**: The system also supports logged-in user sessions via OIDC
    (authority: `https://auth.weatherbug.com/`, client: `wbweb_oidc`). When authenticated,
    an `Authorization: Bearer {emToken}` header is added to requests. The client in this
    module operates in anonymous mode only.

---

*Reverse-engineered from https://www.weatherbug.com (app version 9.8.0, JS bundle 2026-03-27)*
