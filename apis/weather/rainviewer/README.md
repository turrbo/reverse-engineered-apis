# RainViewer API - Reverse Engineering Documentation

Reverse engineered from: https://www.rainviewer.com/map.html
JavaScript sources analyzed: `277.js`, `327.js` (webpack chunks)
Date: 2026-03-25

---

## Overview

RainViewer exposes two tiers of API:

| Tier | Base URL | Auth | Notes |
|------|----------|------|-------|
| **Public** | `https://api.rainviewer.com/public/` | None | Documented, stable |
| **Internal** | `https://api.rainviewer.com/site/` | Session + API key | Undocumented |
| **Tile Cache** | `https://tilecache.rainviewer.com/` | None | PNG tiles |
| **CDN** | `https://cdn.rainviewer.com/` | None | WebP tiles |
| **Maps** | `https://maps.rainviewer.com/` | None | Vector tiles + styles |

---

## Authentication (Internal API)

The internal API uses a two-step token system:

### Step 1 – Create Session
```http
GET https://api.rainviewer.com/site/auth/session

Response Headers:
  X-Rv-Sid: sid-XXXXXXXXXX
  Set-Cookie: sid=sid-XXXXXXXXXX; Max-Age=7080; Path=/site; HttpOnly; Secure; SameSite=None

Response Body:
{
  "code": 0,
  "data": {
    "hasSession": true,
    "okUntil": 0,
    "tsOkUntil": 0
  }
}
```

### Step 2 – Get API Key
```http
POST https://api.rainviewer.com/site/auth/api-key
Content-Type: application/json
x-rv-sid: sid-XXXXXXXXXX

Body: {}

Response:
{
  "code": 0,
  "data": {
    "apiKey": "rv-XXXXXXXXXXXX",
    "expiresAt": 1234567890,   // Unix timestamp when key expires (~2h)
    "okUntil": 1234567890,     // Session validity
    "tsOkUntil": 1234567890
  }
}
```

### Using Auth in Requests
All `/site/*` requests require:
```http
X-RV-Token: rv-XXXXXXXXXXXX
x-rv-sid: sid-XXXXXXXXXX
```

### Error Codes
| Code | Meaning |
|------|---------|
| 0 | Success |
| 100204 | No session (need to call auth/session first) |
| 100206 | Token invalid (refresh token) |
| 11002 | Invalid parameter |
| 11099 | Parameter not supported |

---

## Public API (No Auth)

### GET /public/weather-maps.json

Returns available radar and satellite frame paths (updated every ~10 minutes).

```http
GET https://api.rainviewer.com/public/weather-maps.json

Response:
{
  "version": "2.0",
  "generated": 1774405525,
  "host": "https://tilecache.rainviewer.com",
  "radar": {
    "past": [
      {"time": 1774398000, "path": "/v2/radar/4bcfbed047ef"},
      ... (13 frames, ~2 hours)
    ],
    "nowcast": []  // Short-term precipitation forecast (when available)
  },
  "satellite": {
    "infrared": []  // Usually empty; use /site/maps for satellite
  }
}
```

**Notes:**
- `past` contains ~13 frames (~2 hours of data)
- `nowcast` contains forecast frames (usually empty)
- `satellite.infrared` is typically empty; use the authenticated `/site/maps` for satellite data

---

## Internal API (Auth Required)

### GET /site/maps

Get radar AND satellite frame paths (more complete than public API).

```http
GET https://api.rainviewer.com/site/maps
X-RV-Token: rv-...
x-rv-sid: sid-...

Response:
{
  "code": 0,
  "data": {
    "radar": {
      "past": [
        {"time": 1774398600, "path": "/v2/radar/3bfcba29dc82"},
        ... (13 frames)
      ],
      "future": []
    },
    "satellite": {
      "past": [
        {"time": 1774398600, "path": "/v2/satellite/5a565266804a"},
        ... (13 frames)
      ]
    }
  }
}
```

**Key difference from public API:** Includes `satellite.past` frames.

---

### GET /site/radars/database

Full database of global radar stations.

```http
GET https://api.rainviewer.com/site/radars/database
X-RV-Token: rv-...

Response:
{
  "code": 0,
  "data": {
    "radars": [
      {
        "id": "AU31",
        "country": "AU",
        "state": "WA",
        "location": "Albany",
        "status": 1,
        "latitude": -34.941111,
        "longitude": 117.815833,
        "range": 256,            // km
        "imageId": "AU31",
        "isPro": false,
        "lastUpdated": 1774405140,
        "frequency": 300,        // seconds between updates
        "isOffline": false
      },
      ...
    ],
    "hash": "..."
  }
}
```

**Statistics:** ~1016 stations across 83 countries. ~813 active.
**Top countries by station count:** US (203), CN (184), AU (57), BR (44), IN (38)

---

### GET /site/radars/{id}/products

Get available products for a specific radar.

```http
GET https://api.rainviewer.com/site/radars/AU31/products
X-RV-Token: rv-...

Response:
{
  "code": 0,
  "data": [
    {
      "id": "map",
      "product": "BR",
      "elevation": [],
      "boundingBox": [-30.24, 111.85, -39.57, 123.76],
      "formats": ["webp"],
      "version": 102,
      "types": [],
      "productDisplayName": "BR - Base Reflectivity"
    }
  ]
}
```

**Notes:** Pro radars return empty list without Pro subscription.

---

### GET /site/radars/{id}/products/{product_id}

Get available timestamps for a radar product.

```http
GET https://api.rainviewer.com/site/radars/AU31/products/map
X-RV-Token: rv-...

Response:
{
  "code": 0,
  "data": [
    {"timestamp": 1774405440, "width": 542, "height": 519}
  ]
}
```

---

### GET /site/radars/{id}/products/{product_id}/{timestamp}

Download a specific radar image.

```http
GET https://api.rainviewer.com/site/radars/AU31/products/map/1774405440
X-RV-Token: rv-...

Response: image/webp binary data
```

**Notes:** Returns WebP image of the radar sweep area.

---

### GET /site/alerts

Get active severe weather alerts worldwide.

```http
GET https://api.rainviewer.com/site/alerts
GET https://api.rainviewer.com/site/alerts?bbox={minLat},{minLon},{maxLat},{maxLon}
X-RV-Token: rv-...

Response:
{
  "code": 0,
  "data": [
    {
      "id": "uuid-...",
      "kind": "Met",
      "severity": "Moderate",
      "category": "Flood",
      "type": "Coastal Flood Statement",
      "certainty": "Likely",
      "urgency": "Future",
      "event": "Coastal Flood Statement",
      "starts": 1774479600,
      "ends": 1774565999,
      "title": "Alert title here",
      "description": "Detailed description...",
      "instruction": "Safety instructions...",
      "area": [
        {
          "description": "Area name",
          "box": [[maxLat, minLon], [minLat, maxLon]],
          "polygons": [[[lat, lon], ...]]
        }
      ],
      "source": {
        "code": "uuid",
        "name": "Source Agency",
        "email": "...",
        "url": "..."
      },
      "added": 1774350489,
      "updated": 1774393204,
      "expires": 1774565999,
      "isCancelled": false,
      "locale": "en-US",
      "union_area": [...]
    }
  ]
}
```

**Query Parameters:**
- `bbox`: Geographic filter as `minLat,minLon,maxLat,maxLon`
  - Example: `25,-125,50,-65` for continental US
  - Example: `50,-10,60,10` for Western Europe

**Severity levels:** `Minor`, `Moderate`, `Severe`, `Extreme`
**Categories include:** Flood, Wind, Tornado, Winter Storm, Fire, etc.

---

### GET /site/alerts/{id}

Get a specific alert by UUID.

```http
GET https://api.rainviewer.com/site/alerts/2fbe66e4-0b12-5374-985a-ccd6f330e894
X-RV-Token: rv-...

Response: Same structure as single alert from the list.
```

---

### GET /site/storms

Get active tropical storms and hurricanes.

```http
GET https://api.rainviewer.com/site/storms
X-RV-Token: rv-...

Response:
{
  "code": 0,
  "data": [
    {
      "name": "NARELLE",
      "category": "H4",
      "current": {
        "location": {"latitude": -17.4, "longitude": 120.0},
        "category": "TS",
        "movement": {"direction": 245, "speed": 22},
        "wind": {"speed": 102}
      },
      "track": [
        {"location": {"latitude": -12.3, "longitude": 156.6}, "category": "TS"},
        ...
      ],
      "forecast": [
        {"location": {"latitude": -17.9, "longitude": 119.2}, "category": "TS"},
        ...
      ],
      "cone": [...]
    }
  ]
}
```

**Storm categories:**
| Code | Name | Wind Speed |
|------|------|-----------|
| TD | Tropical Depression | < 63 km/h |
| TS | Tropical Storm | 63-118 km/h |
| H1 | Hurricane Cat 1 | 119-153 km/h |
| H2 | Hurricane Cat 2 | 154-177 km/h |
| H3 | Hurricane Cat 3 | 178-208 km/h |
| H4 | Hurricane Cat 4 | 209-251 km/h |
| H5 | Hurricane Cat 5 | > 252 km/h |

---

## Tile Servers

### Radar Tiles (Tilecache - PNG)

```
https://tilecache.rainviewer.com/v2/radar/{hash}/{size}/{z}/{x}/{y}/{color}/{smooth}_{snow}.png
```

**Parameters:**
| Parameter | Values | Description |
|-----------|--------|-------------|
| `hash` | 12-char hex | Frame identifier from weather-maps API |
| `size` | `256`, `512` | Tile size in pixels |
| `z` | 0-14 | Zoom level |
| `x`, `y` | integers | Tile coordinates |
| `color` | 0-8 | Color scheme (see below) |
| `smooth` | `0`, `1` | Spatial smoothing (1 = on) |
| `snow` | `0`, `1` | Show snow as blue/white (1 = on) |

**Color Schemes:**
| Code | Name |
|------|------|
| 0 | Original |
| 1 | Universal Blue |
| 2 | TITAN |
| 3 | TWC (The Weather Channel) |
| 4 | Meteored |
| 5 | NEXRAD Level III |
| 6 | Rainbow @ SELEX-SI |
| 7 | Dark Sky |
| 8 | Infrared (satellite only) |

**Example:**
```
https://tilecache.rainviewer.com/v2/radar/b5a8f36e48bd/256/5/9/12/4/1_0.png
```

---

### Radar/Satellite Tiles (CDN - WebP)

Higher quality, smaller file size. Used by the web app.

```
https://cdn.rainviewer.com/v2/radar/{hash}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp
https://cdn.rainviewer.com/v2/satellite/{hash}/{size}/{z}/{x}/{y}/255/{smooth}_1_{snow}_0.webp
```

**Notes:**
- Color is always `255` (opacity-only mode; coloring done client-side by WebGL shader)
- The `_1_` in the options string is a fixed flag
- The `_0` at the end is a fixed version marker
- Requires paths from the authenticated `/site/maps` endpoint for satellite

**Example:**
```
https://cdn.rainviewer.com/v2/radar/b5a8f36e48bd/512/5/9/12/255/1_1_0_0.webp
https://cdn.rainviewer.com/v2/satellite/73997e76e86e/512/5/9/12/255/1_1_0_0.webp
```

---

### Map Vector Tiles (MapLibre)

RainViewer uses MapLibre GL JS with custom vector tile servers.

**Map Styles:**
```
https://maps.rainviewer.com/styles/m2/style.json          # Light
https://maps.rainviewer.com/styles/m2_dark/style.json     # Dark
https://maps.rainviewer.com/styles/m2_satellite/style.json # Satellite
```

**Vector Tile Sources:**
```
https://maps.rainviewer.com/data/v3/{z}/{x}/{y}.pbf       # Main map
https://maps.rainviewer.com/data/places/{z}/{x}/{y}.pbf   # Place names
https://maps.rainviewer.com/data/coastlines/{z}/{x}/{y}.pbf # Coastlines
```

**Fonts / Glyphs:**
```
https://maps.rainviewer.com/fonts/{fontstack}/{range}.pbf
```

**Sprites:**
```
https://maps.rainviewer.com/styles/m2/sprite.json
https://maps.rainviewer.com/styles/m2/sprite.png
https://maps.rainviewer.com/styles/m2/sprite@2x.png
```

---

## Tile Coordinate System

Standard Web Mercator (EPSG:3857) tile system (same as Google Maps, OpenStreetMap).

### Lat/Lon to Tile
```python
import math

def lat_lon_to_tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y
```

### Common Zoom Levels
| Zoom | Coverage |
|------|----------|
| 0 | Whole world (1 tile) |
| 3 | Continental (8x8 tiles) |
| 5 | Country level |
| 8 | State/region level |
| 10 | City level |
| 12 | Neighborhood level |
| 14 | Max zoom for map tiles |

---

## Python Client Usage

```python
from rainviewer_client import RainViewerClient, lat_lon_to_tile, COLOR_SCHEMES

# Initialize client (auto-handles authentication)
client = RainViewerClient()

# ── Radar Tiles ──────────────────────────────────────────────

# Get latest radar frames
frames = client.get_latest_radar_frames()
latest = frames[-1]
print(f"Latest radar: {latest.get_timestamp_str()} - {latest.path}")

# Get tile URL for New York City at zoom 8
x, y = lat_lon_to_tile(40.7128, -74.0060, zoom=8)
url = latest.get_tile_url(z=8, x=x, y=y, color=4, smooth=1, snow=0)
print(f"NYC radar tile: {url}")

# Download radar tile
data, content_type = client.download_radar_tile(
    path=latest.path,
    z=8, x=x, y=y,
    size=256,
    color=4,   # Meteored color scheme
    smooth=1,  # With smoothing
    snow=0,    # Normal (no snow highlighting)
    fmt="png", # PNG format
)
with open("radar_tile.png", "wb") as f:
    f.write(data)

# ── Satellite Tiles ──────────────────────────────────────────

sat_frames = client.get_latest_satellite_frames()
latest_sat = sat_frames[-1]

# Download satellite tile (WebP from CDN)
sat_data, _ = client.download_satellite_tile(
    path=latest_sat.path,
    z=5, x=9, y=12,
    size=512,
    smooth=1,
)
with open("satellite_tile.webp", "wb") as f:
    f.write(sat_data)

# ── Weather Alerts ──────────────────────────────────────────

# All global alerts
alerts = client.get_alerts()
print(f"Active alerts: {len(alerts)}")

# Filter to continental US
us_alerts = client.get_alerts(bbox="25,-125,50,-65")
severe = [a for a in us_alerts if a.severity in ("Severe", "Extreme")]
print(f"Severe US alerts: {len(severe)}")

for alert in severe[:3]:
    print(f"  [{alert.severity}] {alert.title}")
    print(f"  Event: {alert.event}")
    print(f"  Source: {alert.source.get('name')}")

# ── Tropical Storms ──────────────────────────────────────────

storms = client.get_active_storms()
for storm in storms:
    wind = storm.current.get("wind", {}).get("speed", 0)
    cat = storm.current.get("category", "?")
    loc = storm.current.get("location", {})
    print(f"{storm.name}: Cat {cat}, {wind} km/h @ ({loc.get('latitude')}, {loc.get('longitude')})")
    print(f"  Track points: {len(storm.track)}")
    print(f"  Forecast points: {len(storm.forecast)}")

# ── Radar Stations ──────────────────────────────────────────

# Get all active Australian radars
au_radars = client.get_radar_stations(country="AU", active_only=True)
print(f"Active Australian radars: {len(au_radars)}")

# Get radar image for a specific station
station = au_radars[0]
products = client.internal.get_radar_products(station.id)
if products:
    prod = products[0]
    timestamps = client.internal.get_radar_product_timestamps(station.id, prod["id"])
    if timestamps:
        ts = timestamps[-1]["timestamp"]
        img_data, ct = client.internal.get_radar_product_image(station.id, prod["id"], ts)
        with open(f"{station.id}_radar.webp", "wb") as f:
            f.write(img_data)
        print(f"Saved {station.id} radar image: {len(img_data)} bytes")

# ── Map Styles ──────────────────────────────────────────────

# Get MapLibre GL style for rendering base map
import json
style = client.get_base_map_style(dark=False)
print(f"Map style layers: {len(style.get('layers', []))}")

# Get map tile URLs
coverage = client.get_coverage_layer_info()
print(f"Vector tiles: {coverage['vector_tiles']['tiles'][0]}")

# ── Direct API Access ────────────────────────────────────────

# Use the low-level HTTP client directly
response = client.internal._http.request_json("/site/maps")
print(f"Direct API response keys: {list(response.keys())}")

# Using public API without auth
from rainviewer_client import RainViewerPublicAPI
pub = RainViewerPublicAPI()
weather_maps = pub.get_weather_maps()
print(f"Public API host: {weather_maps['host']}")
```

---

## Complete API Summary

### Public Endpoints (No Auth)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `https://api.rainviewer.com/public/weather-maps.json` | Radar + satellite frame paths |
| GET | `https://tilecache.rainviewer.com/v2/radar/{hash}/{size}/{z}/{x}/{y}/{color}/{sm}_{sn}.png` | Radar tile (PNG) |
| GET | `https://tilecache.rainviewer.com/v2/satellite/{hash}/{size}/{z}/{x}/{y}/{color}/{sm}_{sn}.png` | Satellite tile (PNG) |
| GET | `https://cdn.rainviewer.com/v2/radar/{hash}/{size}/{z}/{x}/{y}/255/{sm}_1_{sn}_0.webp` | Radar tile (WebP) |
| GET | `https://cdn.rainviewer.com/v2/satellite/{hash}/{size}/{z}/{x}/{y}/255/{sm}_1_{sn}_0.webp` | Satellite tile (WebP) |
| GET | `https://maps.rainviewer.com/styles/{style}/style.json` | MapLibre GL style |
| GET | `https://maps.rainviewer.com/data/v3/{z}/{x}/{y}.pbf` | Map vector tiles |
| GET | `https://maps.rainviewer.com/data/places/{z}/{x}/{y}.pbf` | Place labels |
| GET | `https://maps.rainviewer.com/data/coastlines/{z}/{x}/{y}.pbf` | Coastline vectors |
| GET | `https://maps.rainviewer.com/fonts/{fontstack}/{range}.pbf` | Map fonts/glyphs |

### Authenticated Endpoints (Session + API Key Required)

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/site/auth/session` | Create/get session (returns X-Rv-Sid) |
| POST | `/site/auth/api-key` | Get temporary API key |
| GET | `/site/maps` | Radar + satellite frames (includes satellite) |
| GET | `/site/radars/database` | All 1000+ global radar stations |
| GET | `/site/radars/{id}/products` | Products for a radar station |
| GET | `/site/radars/{id}/products/{product}` | Timestamps for a product |
| GET | `/site/radars/{id}/products/{product}/{timestamp}` | Radar image download |
| GET | `/site/alerts` | All active weather alerts |
| GET | `/site/alerts?bbox={lat1},{lon1},{lat2},{lon2}` | Alerts in bounding box |
| GET | `/site/alerts/{uuid}` | Specific alert by ID |
| GET | `/site/storms` | Active tropical storms/hurricanes |

---

## Implementation Notes

### Session Management
- Sessions set a `sid` HttpOnly cookie that must be sent with subsequent requests
- The session ID is also provided in the `X-Rv-Sid` response header
- Sessions last approximately 2 hours (`Max-Age=7080` seconds)
- Error code `100204` = session expired, refresh by calling `/site/auth/session` again

### API Key Lifecycle
1. Session created → API key obtained (both valid ~2 hours)
2. API key used in `X-RV-Token` header
3. Error code `100206` → token invalid, refresh via new session + API key
4. Error code `100204` → session expired, full re-auth needed

### Tile Caching
- Tilecache server serves PNG tiles (older/fallback format)
- CDN server serves WebP tiles (used by web app, higher quality)
- Both servers serve tiles for radar and satellite data
- Tiles are heavily cached (~10 min TTL based on update frequency)

### Satellite vs Radar
- **Radar tiles**: Standard weather radar reflectivity, shows precipitation intensity
- **Satellite tiles**: Infrared satellite imagery, shows cloud tops
- `sat-rad` layer combines both in the web app
- The CDN tile format supports both with the same URL structure

### Color Rendering (WebP)
The web app renders CDN WebP tiles using a WebGL shader:
- The raw tile data uses color=255 (grayscale intensity values)
- A color lookup table (LUT/palette) is applied per the selected color scheme
- The palette is loaded from `rainviewer_api_colors_table.json`
- For PNG tiles, colors are pre-applied server-side

---

## Known Limitations

1. **Pro features**: Many NEXRAD (US) radars require a paid Pro subscription
2. **Rate limits**: Not documented; aggressive polling may result in blocks
3. **Satellite coverage**: Not available for all regions; data gaps may exist
4. **Auth stability**: The internal API is undocumented and may change
5. **Terms of Service**: Use the public API for production applications; the internal API is reverse engineered
