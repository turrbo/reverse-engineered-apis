# Zoom Earth API - Reverse Engineering Notes

## Overview

This document describes the internal/hidden APIs discovered in [Zoom Earth](https://zoom.earth),
a near-real-time satellite imagery and weather visualization platform by Neave Interactive.

All endpoints were discovered by:
1. Downloading the minified JS bundle (`/assets/js/app.d4802fd1.js`).
2. Decoding obfuscated URL strings (ROT-13 cipher applied to base64-encoded strings).
3. Tracing API call patterns in the application code.
4. Testing endpoints live with appropriate headers.

---

## Obfuscation Scheme

The JavaScript bundle encodes all URL strings using:

```
function t(text) {
  return text.replace(/[a-z]/gi, ch => {
    const s = ch.charCodeAt(0);
    const i = (s & 31) - 1;
    return String.fromCharCode(s - i + (i + 13) % 26);
  });
}
decoded = atob(t(encoded))
```

This is effectively: **ROT-13 applied to the base64-encoded string**, then base64-decoded.

### Python decoder:

```python
import base64

def decode(encoded: str) -> str:
    def rot13(text):
        result = []
        for c in text:
            if c.isalpha():
                s = ord(c)
                i = (s & 31) - 1
                shifted = s - i + (i + 13) % 26
                result.append(chr(shifted))
            else:
                result.append(c)
        return ''.join(result)
    return base64.b64decode(rot13(encoded)).decode('utf-8')
```

---

## Base Domains

| Variable | Decoded Value | Purpose |
|----------|---------------|---------|
| `i` | `https://zoom.earth` | Main site / data API |
| `g` | `https://tiles.zoom.earth` | Tile server |
| `M` (prefix) | `https://api.zoom.earth` | Weather API |
| `b` | `https://account.zoom.earth` | Account / auth |

---

## API Endpoints

### 1. Data API — `https://zoom.earth/data/`

All data endpoints accept GET requests and return JSON.
Headers required: `Referer: https://zoom.earth/`

#### GET `/data/time/`
Returns current server Unix timestamp.
```json
{"time": 1774406256}
```

#### GET `/data/version/`
Returns current app version hash.
```json
{"app": "d4802fd1"}
```

#### GET `/data/fires/latest.json`
Returns active wildfire and prescribed burn locations.
```json
[
  {
    "id": "us-ak-nenana-ridge-prescribed-burn",
    "name": "Nenana Ridge Prescribed Burn",
    "coordinate": [-148.69, 64.653617],
    "admin": "Yukon-Koyukuk County, Alaska, United States",
    "countryCode": "US",
    "type": "PB",
    "date": "2026-03-24T18:12Z"
  }
]
```
Fire `type` values: `WF` (Wildfire), `PB` (Prescribed Burn), `OT` (Other), `COM` (Complex).

#### GET `/data/storms/?date=YYYY-MM-DD[&to=YYYY-MM-DD]`
Returns active tropical storm IDs for a date range.
```json
{
  "storms": ["narelle-2026"],
  "disturbances": []
}
```

#### GET `/data/storms/?id=STORM_ID`
Returns detailed information about a specific storm.
```json
{
  "id": "narelle-2026",
  "name": "Narelle",
  "title": "Cyclone Narelle",
  "description": "Tropical Cyclone",
  "season": "2026",
  "type": "Cyclone",
  "track": [...]
}
```

#### GET `/data/geocode/?q=PLACE_NAME`
Forward geocode a place name. Returns approximate coordinates.
```json
{"lon": -74.0, "lat": 40.7}
```
Note: This endpoint appears to use a limited internal database and defaults to a fallback location when the query is not recognized.

#### GET `/data/notifications/`
Returns in-app notification messages (usually empty array).

#### GET `/data/outages/`
Returns current service outage information.
```json
{
  "outages": [
    {
      "id": "mtg-zero",
      "message": "There is an outage with the imagery provider...",
      "url": "#map=satellite-hd"
    }
  ],
  "radar": null
}
```

---

### 2. Tile Times API — `https://tiles.zoom.earth/times/`

These JSON files describe available tile timestamps.

#### GET `/times/geocolor.json`
Returns available satellite image timestamps per satellite.
```json
{
  "goes-west":   [1774147200, 1774147800, ...],
  "goes-east":   [1774147200, ...],
  "mtg-zero":    [...],
  "msg-zero":    [...],
  "msg-iodc":    [...],
  "himawari":    [...]
}
```
Timestamps are Unix seconds. Images are available at ~10-minute intervals.

#### GET `/times/radar.json`
Returns available radar timestamps and tile hashes.
```json
{
  "reflectivity": {
    "1774147200": "8f2891eb",
    "1774147500": "82826ea4"
  },
  "coverage": {"1773774900": "6bd55917"},
  "areas": [[lon, lat, ...]],
  "attributions": [...]
}
```
The hash string is required in radar tile URLs to identify the correct dataset.

#### GET `/times/gfs.json` and `/times/icon.json`
Returns available forecast model run times per layer and altitude level.
```json
{
  "precipitation":   {"surface": {"1773511200": [0, 1, 2, 3, ...]}},
  "wind-speed":      {"10m":     {"1773511200": [0, 1, 2, ...]}},
  "temperature":     {"2m":      {"1773511200": [0, 1, 2, ...]}},
  "temperature-feel":{"2m":      {...}},
  "humidity":        {"2m":      {...}},
  "dew-point":       {"2m":      {...}},
  "pressure":        {"msl":     {...}},
  "wind-gusts":      {"surface": {...}},
  "temperature-wet-bulb": {"2m": {...}}
}
```
Outer keys are layer names, inner keys are altitude levels, values are dicts mapping run-time Unix timestamp → list of forecast hour offsets.

---

### 3. Satellite Image Tile Server — `https://tiles.zoom.earth/`

#### Geocolor (True-Color Satellite Imagery)
```
GET /geocolor/{satellite}/{YYYY-MM-DD}/{HHMM}/{z}/{y}/{x}.jpg
```

| Parameter | Description |
|-----------|-------------|
| `satellite` | Satellite ID (see table below) |
| `YYYY-MM-DD/HHMM` | UTC date and time (10-minute intervals) |
| `z` | Zoom level (0–7 for most satellites) |
| `y` | Tile row (TMS, 0 = top/north) |
| `x` | Tile column (0 = left/west) |

**Satellite IDs:**

| ID | Satellite | Coverage |
|----|-----------|---------|
| `goes-west` | GOES-18 | Western Americas, Pacific |
| `goes-east` | GOES-16 | Eastern Americas, Atlantic |
| `mtg-zero` | MTG-I1 (Meteosat Third Generation) | Europe, Africa |
| `msg-zero` | Meteosat-11 | Europe, Africa |
| `msg-iodc` | Meteosat-8 | Indian Ocean, Middle East |
| `himawari` | Himawari-9 | Asia, Pacific |
| `geo-kompsat` | GK-2A (COMS) | East Asia |

**Example:**
```
https://tiles.zoom.earth/geocolor/goes-west/2026-03-25/0220/4/6/4.jpg
https://tiles.zoom.earth/geocolor/himawari/2026-03-25/0210/3/4/6.jpg
```

#### Blue Marble (Static Background)
```
GET /static/bluemarble/{month}/{z}/{y}/{x}.jpg
```
`month`: Three-letter month name (`jan`, `feb`, ..., `dec`).

#### Static Land / Fill Tiles
```
GET /static/land/{version}/{scale}x/webp/{z}/{y}/{x}.webp
GET /static/fill/{version}/{scale}x/webp/{z}/{y}/{x}.webp
GET /static/line/{version}/{scale}x/webp/{z}/{y}/{x}.webp
```
`version` from `/data/version/` (or config). `scale` = 1 or 2.

#### Radar Reflectivity
```
GET /radar/reflectivity/{YYYY-MM-DD}/{HHMM}/{hash}/{z}/{y}/{x}.webp
```
`hash` from `/times/radar.json` reflectivity dict. Time is 5-minute intervals.

**Example:**
```
https://tiles.zoom.earth/radar/reflectivity/2026-03-22/0240/8f2891eb/5/10/12.webp
```

#### Radar Coverage
```
GET /radar/coverage/{z}/{y}/{x}.webp
```
Static overlay showing areas with radar data coverage.

#### Heat / Fire Radiative Power
```
GET /proxy/heat/{YYYY-MM-DD}/{extent}.jpg
```
Heatspot proxy layer from FIRMS satellite data.

#### Forecast Model Tiles
```
GET /{model}/v1/{layer}/webp/{level}/{YYYY-MM-DD}/{HHMM}/f{FFF}/{z}/{y}/{x}.webp
```

| Parameter | Values |
|-----------|--------|
| `model` | `gfs`, `icon` |
| `layer` | `precipitation`, `wind-speed`, `wind-gusts`, `temperature`, `temperature-feel`, `temperature-wet-bulb`, `humidity`, `dew-point`, `pressure` |
| `level` | `surface`, `10m`, `2m`, `msl` (depends on layer) |
| `YYYY-MM-DD/HHMM` | Model run date/time (UTC) |
| `FFF` | Forecast hour, zero-padded to 3 digits (e.g. `000`, `024`, `120`) |

**Layer → Level mapping:**
```
precipitation       -> surface
wind-speed          -> 10m
wind-gusts          -> surface
temperature         -> 2m
temperature-feel    -> 2m
temperature-wet-bulb -> 2m
humidity            -> 2m
dew-point           -> 2m
pressure            -> msl
```

**Example:**
```
https://tiles.zoom.earth/gfs/v1/temperature/webp/2m/2026-03-24/1800/f000/5/10/12.webp
https://tiles.zoom.earth/icon/v1/precipitation/webp/surface/2026-03-24/0000/f024/5/10/12.webp
```

---

### 4. Weather API — `https://api.zoom.earth/weather/`

#### POST `/weather/`

Returns hourly or daily weather forecast for a latitude/longitude point.

**Authentication:** Requires a time-based `Request-Signature` header.

##### Signature Algorithm

The signature is computed as follows:

```python
import base64, time, random

def djb2_hex(text: str) -> str:
    """DJB2 hash returned as 8-character lowercase hex."""
    h = 5381
    for c in text:
        h = ((h << 5) + h + ord(c)) & 0xFFFFFFFF
    return format(h, '08x')

def rot13(text: str) -> str:
    result = []
    for c in text:
        if c.isalpha():
            s = ord(c)
            i = (s & 31) - 1
            result.append(chr(s - i + (i + 13) % 26))
        else:
            result.append(c)
    return ''.join(result)

def create_signature(lon: float, lat: float) -> str:
    r = round(lon, 3)
    o = round(lat, 3)
    ts_ms = int(time.time() * 1000)

    sig_hash = djb2_hex(f"{r}~{o}~{ts_ms}")    # 8 hex chars
    hex_ts   = format(ts_ms, '012x')             # 12 hex chars
    hex_rand = format(int(256 * random.random()), '02x')  # 2 hex chars

    m = f"{sig_hash}.{hex_ts}.{hex_rand}"
    return rot13(base64.b64encode(m.encode()).decode())
```

##### Request Body (Hourly)
```json
{
  "longitude": -74.006,
  "latitude": 40.713,
  "timeZone": true,
  "hourly": {
    "hours": ["cloud", "rain", "snow", "windSpeed", "windDirection",
              "windGusts", "temperature", "temperatureFeel",
              "temperatureWetBulb", "humidity", "dewPoint", "pressure"],
    "sunrise": true,
    "sunset": true,
    "model": "gfs",
    "modelVersion": "v1"
  }
}
```

##### Response (Hourly)
```json
{
  "metadata": {
    "longitude": -74.006,
    "latitude": 40.713,
    "timeZone": "America/New_York"
  },
  "hourly": {
    "model": "gfs",
    "modelVersion": "v1",
    "sunrise": ["2026-03-25T10:30Z", ...],
    "sunset":  ["2026-03-25T23:05Z", ...],
    "hours": [
      {
        "date": "2026-03-25T01:00Z",
        "cloud": 100,
        "rain": 0,
        "snow": 0,
        "windSpeed": 5.49,
        "windDirection": 197.29,
        "windGusts": 8.43,
        "temperature": 6.26,
        "temperatureFeel": 2.76,
        "temperatureWetBulb": 1.4,
        "humidity": 44.66,
        "dewPoint": -5.03,
        "pressure": 1028.4
      }
    ]
  }
}
```

Units: temperature in °C, wind in m/s, rain/snow in mm, pressure in hPa.

---

## Tile Coordinate System

Zoom Earth tiles use the standard **Web Mercator (EPSG:3857)** XYZ tile scheme:
- `z=0` → 1 tile covering the whole world.
- `z=1` → 4 tiles, `z=2` → 16 tiles, etc.
- `x=0` at the left edge (180°W), increases eastward.
- `y=0` at the top edge (~85.05°N), increases southward.
- Satellite tiles are available up to zoom level 7 (GOES/Himawari) or 9 (HD/GIBS).

### Convert lat/lon to tile coordinates

```python
import math

def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y
```

---

## Python Client Usage

See `zoom_earth_client.py` for the full client implementation.

### Quick Start

```python
from zoom_earth_client import ZoomEarthClient, lat_lon_to_tile, SATELLITE_GOES_WEST

client = ZoomEarthClient()

# ---- Satellite imagery ----

# Get available timestamps
times = client.get_geocolor_times()
latest_ts = times[SATELLITE_GOES_WEST][-1]
print(f"Latest GOES-West image: {latest_ts}")

# Download a tile (convert NYC to tile coords at zoom 7)
x, y = lat_lon_to_tile(lat=40.71, lon=-74.01, zoom=7)
tile_bytes = client.get_geocolor_tile(
    satellite=SATELLITE_GOES_WEST,
    timestamp=latest_ts,
    z=7, y=y, x=x
)
with open("nyc_satellite.jpg", "wb") as f:
    f.write(tile_bytes)

# ---- Radar ----

radar_tile = client.get_latest_radar_tile(z=5, y=10, x=12)
with open("radar.webp", "wb") as f:
    f.write(radar_tile)

# ---- Weather forecast ----

weather = client.get_weather(lon=-74.006, lat=40.7128, model="gfs")
for hour in weather["hourly"]["hours"][:6]:
    print(f"{hour['date']}: {hour['temperature']:.1f}°C, wind {hour['windSpeed']:.1f} m/s")

# ---- Active fires ----

fires = client.get_fires()
print(f"Active fires: {len(fires)}")

# ---- Tropical storms ----

storms = client.get_storms(date="2026-03-25")
for storm_id in storms.get("storms", []):
    details = client.get_storm_details(storm_id)
    print(f"Storm: {details['title']}")

# ---- System status ----

outages = client.get_outages()
for outage in outages.get("outages", []):
    print(f"Outage: [{outage['id']}] {outage['message']}")
```

### Run the built-in demo

```bash
python zoom_earth_client.py
```

---

## Notes and Caveats

1. **Unofficial API** — These endpoints are not documented and may change or disappear without warning.
2. **Rate limiting** — No explicit rate limit was observed, but excessive use may trigger blocking. Respect the server.
3. **Authentication** — The weather API uses a time-based signature to prevent automated abuse. The algorithm was reverse-engineered from the JS source.
4. **Tile content** — Small tiles (88 bytes) indicate empty/transparent tiles (no data for that location).
5. **Geo-Kompsat** — The GK-2A (geo-kompsat) satellite uses a different time step (10 minutes).
6. **HD Satellite** — There is a separate HD satellite layer (GIBS/NASA) served via:
   `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`
7. **CORS** — The tile server (`tiles.zoom.earth`) requires a valid `Referer: https://zoom.earth/` header in browser contexts.
8. **Terms of service** — Review Zoom Earth's ToS before commercial use. The service is free for personal use.

---

## Discovered Endpoints Summary Table

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `https://zoom.earth/data/time/` | GET | None | Server time |
| `https://zoom.earth/data/version/` | GET | None | App version |
| `https://zoom.earth/data/fires/latest.json` | GET | None | Active fires |
| `https://zoom.earth/data/storms/?date=...` | GET | None | Storm list by date |
| `https://zoom.earth/data/storms/?id=...` | GET | None | Storm details |
| `https://zoom.earth/data/geocode/?q=...` | GET | None | Forward geocode |
| `https://zoom.earth/data/search/?q=...` | GET | None | Place search (limited) |
| `https://zoom.earth/data/notifications/` | GET | None | App notifications |
| `https://zoom.earth/data/outages/` | GET | None | Service outages |
| `https://tiles.zoom.earth/times/geocolor.json` | GET | None | Satellite image times |
| `https://tiles.zoom.earth/times/radar.json` | GET | None | Radar frame times |
| `https://tiles.zoom.earth/times/gfs.json` | GET | None | GFS model run times |
| `https://tiles.zoom.earth/times/icon.json` | GET | None | ICON model run times |
| `https://tiles.zoom.earth/geocolor/{sat}/{date}/{z}/{y}/{x}.jpg` | GET | Referer | Satellite tiles |
| `https://tiles.zoom.earth/static/bluemarble/{month}/{z}/{y}/{x}.jpg` | GET | Referer | Blue Marble tiles |
| `https://tiles.zoom.earth/radar/reflectivity/{date}/{hash}/{z}/{y}/{x}.webp` | GET | Referer | Radar tiles |
| `https://tiles.zoom.earth/radar/coverage/{z}/{y}/{x}.webp` | GET | Referer | Radar coverage |
| `https://tiles.zoom.earth/{model}/v1/{layer}/webp/{level}/{run}/{fhour}/{z}/{y}/{x}.webp` | GET | Referer | Forecast tiles |
| `https://api.zoom.earth/weather/` | POST | Request-Signature | Weather forecast |
| `https://account.zoom.earth/auth/status` | GET | Cookie | Auth status |
| `https://account.zoom.earth/subscription/` | GET | Cookie | Subscription info |
