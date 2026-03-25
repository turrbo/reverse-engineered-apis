# LightningMaps / Blitzortung API — Reverse Engineering Reference

## Overview

LightningMaps.org is a real-time global lightning strike visualization platform built on top of the
Blitzortung.org community network. The site uses a combination of WebSockets for live data and
HTTP endpoints for static/archived content.

**IMPORTANT:** Lightning data is copyright Blitzortung.org contributors. It is intended for
entertainment/educational purposes only. Commercial usage is forbidden.
Contact: `info@blitzortung.org`

---

## Discovered APIs

### 1. Real-Time WebSocket (Primary Data Feed)

**Servers:**
- `wss://live.lightningmaps.org/` (Port 443)
- `wss://live2.lightningmaps.org/` (Port 443)

Both servers are load-balanced and equivalent. The JS client picks one randomly using weighted
selection from `live.config.subdomains`.

**Protocol version:** 24 (field `v` in messages)

#### Connection Flow

```
Client -> Server:  Send initial subscription message (see below)
Server -> Client:  {"cid": 650543, "con": 56, "port": "8085", "time": 1774405882.086, "k": 573116582.436}
                   (Challenge message containing k value)
Client -> Server:  {"k": (challenge_k * 3604) % 7081 * unix_ms / 100}
                   (Challenge response)
Server -> Client:  {"time": 1774405895, "flags": {"2": 2}, "strokes": [...]}
                   (Stroke batch — repeating every ~1-5 seconds)
```

#### Initial Subscription Message (Client -> Server)

```json
{
  "v":    24,
  "i":    {},
  "s":    false,
  "x":    0,
  "w":    0,
  "tx":   0,
  "tw":   0,
  "a":    6,
  "z":    5,
  "b":    true,
  "h":    "",
  "l":    1,
  "t":    1774405882,
  "from_lightningmaps_org": true,
  "p":    [55.0, 30.0, 40.0, -10.0]
}
```

**Field descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `v` | int | Protocol version (24) |
| `i` | dict | Last seen stroke IDs per source `{src_id: last_id}` |
| `s` | bool | Request station participation data in each stroke |
| `x` | int | XHR error count |
| `w` | int | WebSocket error count |
| `tx` | int | XHR try count |
| `tw` | int | WebSocket try count |
| `a` | int | Source bitmask: `2`=Blitzortung, `4`=LightningMaps experimental, `6`=both |
| `z` | int | Map zoom level (2-15) |
| `b` | bool | Page visible |
| `h` | str | URL hash / fragment |
| `l` | int | Loop count (number of requests sent so far) |
| `t` | int | Current Unix timestamp |
| `from_lightningmaps_org` | bool | Always `true` (identifies client) |
| `p` | list | Bounding box `[N_lat, E_lon, S_lat, W_lon]` |

**Note:** After the challenge/response, send the subscription message again as a keepalive
periodically (roughly every 60 seconds). The server sends data automatically every 1-5 seconds.

#### Challenge-Response Calculation

The server sends a challenge value `k`. The client must respond with:

```python
response_k = (k * 3604) % 7081 * (time.time() * 1000) / 100
```

Send as: `{"k": <response_k>}`

#### Stroke Batch Message (Server -> Client)

```json
{
  "time": 1774405931,
  "flags": {"2": 2},
  "strokes": [
    {
      "time": 1774405664752,
      "lat":  36.238781,
      "lon":  26.560367,
      "src":  2,
      "srv":  1,
      "id":   13370274,
      "del":  1780,
      "dev":  161
    }
  ]
}
```

**Stroke field descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `time` | int | Unix timestamp in **milliseconds** (high-precision, includes sub-ms) |
| `lat` | float | Latitude in decimal degrees |
| `lon` | float | Longitude in decimal degrees |
| `src` | int | Source integer ID: `1`=LightningMaps.org pipeline, `2`=Blitzortung.org standard |
| `srv` | int | Computing server ID |
| `id` | int | Unique stroke ID (within source, monotonically increasing) |
| `del` | int | Detection/computation delay in milliseconds |
| `dev` | int | Accuracy deviation estimate in meters (lower = more accurate) |
| `alt` | float | Altitude (rarely present) |
| `sta` | dict | Station map `{station_id: status}` (only if `s=true` requested) |

**Station status bitmask (`sta` field):**
- Bit 0 (`1`): Station was assigned to this stroke
- Bit 1 (`2`): Station's data was used in calculation
- Bit 6 (`64`): Special status

---

### 2. XHR HTTP Polling (Fallback)

**Endpoint:** `GET https://live.lightningmaps.org/l/`
**Fallback:** `GET https://live2.lightningmaps.org/l/`

Used when WebSocket is unavailable or fails. The server supports CORS with `Access-Control-Allow-Origin: *`.

#### Request Parameters

| Parameter | Description |
|-----------|-------------|
| `v` | Protocol version (24) |
| `l` | Last sequence number from previous response (0 for first request) |
| `i` | Source bitmask (2, 4, or 6) |
| `s` | (flag, no value) Include station data |
| `m` | (flag, no value) Mobile mode |
| `e` | Error count (optional) |

**Example:** `GET https://live.lightningmaps.org/l/?v=24&l=0&i=4`

#### Response

```json
{
  "w": 500,
  "o": 5000,
  "copyright": "Lightning data copyright by Blitzortung.org contributors...",
  "x": true,
  "s": 2409624,
  "d": [
    {
      "time": -70310,
      "lat":  "35.680026",
      "lon":  "17.836861",
      "src":  2,
      "srv":  1,
      "id":   13370489,
      "del":  1816,
      "dev":  15053
    }
  ]
}
```

**Response fields:**

| Field | Description |
|-------|-------------|
| `w` | Wait ms before next request when data was present |
| `o` | Wait ms before next request when no new data |
| `s` | New sequence number — use as `l=` in next request |
| `d` | Array of stroke objects |
| `t` | Server timestamp |
| `x` | Data available flag |
| `copyright` | Copyright notice |

**Note on `time` field in XHR strokes:** The `time` field may be a negative offset from server
time rather than an absolute timestamp. Use `server_time + stroke.time` to get absolute time.

---

### 3. Stations JSON API

Retrieve all detector stations for a geographic region.

**Endpoints:**
```
GET https://www.lightningmaps.org/blitzortung/europe/index.php?stations_json
GET https://www.lightningmaps.org/blitzortung/america/index.php?stations_json
GET https://www.lightningmaps.org/blitzortung/oceania/index.php?stations_json
```

**Response:**
```json
{
  "user": "",
  "stations": {
    "1": {
      "0": 49.72,
      "1": 8.47,
      "a": "2.0",
      "c": "Bosany",
      "C": "Slovakia (Slovak Republic)",
      "s": "10"
    }
  }
}
```

**Station fields:**

| Field | Description |
|-------|-------------|
| `0` | Latitude |
| `1` | Longitude |
| `a` | Altitude in meters (string) |
| `c` | City/location name |
| `C` | Country name |
| `s` | Status: `"0"` or `"10"` = online, `"30"` = partial, `"D"` = offline |

---

### 4. Lightning Strike Density Tiles

PNG tiles with rendered lightning strike overlays, compatible with any Leaflet/Mapbox map.

**Base URL:** `https://tiles.lightningmaps.org/`

#### Recent Strikes Tiles

```
GET https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&t=5
GET https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&t=6
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `x` | Tile X coordinate |
| `y` | Tile Y coordinate |
| `z` | Zoom level (2-16) |
| `s` | Tile size in pixels (256 or 512) |
| `t` | Tile type: `5`=last ~1 hour (yellow-red), `6`=last ~24 hours (older, dimmer) |

#### Strike Counter Tiles

```
GET https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&count=5
GET https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&count=5,6
```

Parameter `count` is a comma-separated list of tile types to count.

#### Archive Tiles (Historical Time Range)

```
GET https://tiles.lightningmaps.org/?x={x}&y={y}&z={z}&s=256&from=ISO_TIMESTAMP&to=ISO_TIMESTAMP
```

**Example:**
```
GET https://tiles.lightningmaps.org/?x=8&y=10&z=5&s=256
    &from=2026-03-24T00:00:00.000Z&to=2026-03-24T23:59:59.000Z
```

Timestamps must be in ISO 8601 format: `YYYY-MM-DDTHH:MM:SS.000Z` (always UTC).

---

### 5. Background Map Tiles

Proxy/mirror tiles for background maps.

**Base URL:** `https://map.lightningmaps.org/`

#### OSM-Based Tiles

```
GET https://map.lightningmaps.org/carto/{z}/{x}/{y}.png
GET https://map.lightningmaps.org/carto-nolabels/{z}/{x}/{y}.png
GET https://map.lightningmaps.org/terrain/{z}/{x}/{y}.png
GET https://map.lightningmaps.org/trans/{z}/{y}/{x}.png
```

Note: `trans` uses `{z}/{y}/{x}` order (y and x are swapped).

#### Satellite Imagery

```
GET https://map.lightningmaps.org/eox_s2cloudless_2022/{z}/{y}/{x}.png
```

Sentinel-2 cloudless satellite imagery. Note `{z}/{y}/{x}` order.

#### NEXRAD Rain Radar (US only)

```
GET https://map.lightningmaps.org/radar/{z}/{x}/{y}.png
```

Valid geographic bounds: lat 0°-90°N, lon 180°W-20°W (continental US + surrounding).

#### NOAA WMS Clouds Layer

```
GET https://map.lightningmaps.org/noaa_sat/?SERVICE=WMS&REQUEST=GetMap&...
    &LAYERS=1&VERSION=1.3.0&FORMAT=image/png
```

Standard WMS protocol. Max zoom: 5.

---

### 6. Archive Image Maps (Pre-Rendered)

Pre-rendered regional map images from the MyBlitzortung archive system.

**Base URL:** `https://images.lightningmaps.org/blitzortung/`

#### Static Archive Map Image

```
GET https://images.lightningmaps.org/blitzortung/{region}/index.php?map={map_id}&date={date}
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `{region}` | `europe`, `america`, or `oceania` |
| `map` | Map area ID (see below) |
| `date` | Date in `YYYYMMDD` format |
| `hour_from` | Start hour: `0`, `6`, `12`, or `18` |
| `hour_range` | Duration: `6`, `12`, `18`, `24`, `30`, ... `72` |

**Europe map IDs:** `0`=Europe, `6`=Western Europe, `europe_full_big`, `baltic`,
`benelux`, `france`, `de2`, `de_rad`, `poland`, `switzerland`, `uk`,
`sat_europe_mpe`, `sat_europe_fire`, `sat_europe_natural`

**America map IDs:** `0`=America

**Oceania map IDs:** `0`=Oceania

**Example:**
```
GET https://images.lightningmaps.org/blitzortung/europe/index.php?map=0&date=20260324
```

#### Archive Animation (Animated GIF)

```
GET https://images.lightningmaps.org/blitzortung/{region}/index.php
    ?animation={map_id}&date={date}&hour_from={h}&hour_range={r}
```

Returns an animated GIF (typically 100KB-10MB depending on duration and activity).

---

### 7. Mini-Map Thumbnails

Small thumbnail images used in the website sidebar.

#### Static Mini-Map

```
GET https://images.lightningmaps.org/blitzortung/europe/index.php?map=5&t={unix_5min}
GET https://images.lightningmaps.org/blitzortung/europe/index.php?map=1&t={unix_5min}
GET https://images.lightningmaps.org/blitzortung/america/index.php?map=usa_mini&t={unix_5min}
GET https://images.lightningmaps.org/blitzortung/oceania/index.php?map=oceania_mini&t={unix_5min}
```

The `t` parameter is `int(time.time() / 300)` (5-minute cache invalidation key).

#### Animated Mini-Map

```
GET https://images.lightningmaps.org/blitzortung/europe/index.php?animation=5&t={unix_5min}
```

---

### 8. Signal Waveform Graphs

Individual strike waveform data from specific stations.

```
GET https://images.lightningmaps.org/blitzortung/{region}/index.php
    ?bo_graph&bo_station_id={station_id}&bo_dist={dist_meters}
    &bo_time={strike_time}&lang=en[&bo_spectrum|&bo_xy][&bo_size=3]
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `bo_graph` | (flag) Request standard time-domain signal |
| `bo_station_id` | Station ID |
| `bo_dist` | Distance from station to strike in meters |
| `bo_time` | Strike time as `YYYY-MM-DD HH:MM:SS.nnnnnnnnn` |
| `bo_spectrum` | (flag) Show frequency spectrum instead of time signal |
| `bo_xy` | (flag) Show X/Y scatter plot |
| `bo_size` | Size multiplier: `1`=thumbnail (300x150), `3`=large |
| `full` | (flag) Full-resolution version (append `&full` via mouseover) |

---

### 9. Country Borders GeoJSON

World country border polygons.

```
GET https://www.lightningmaps.org/geo.json
```

Returns a GeoJSON `FeatureCollection` (~3.85MB) with country polygon features.

---

### 10. Regional Statistics Pages (HTML)

Web pages with additional per-station statistics (not pure JSON APIs):

```
GET https://www.lightningmaps.org/blitzortung/europe/index.php
    ?bo_page=statistics&bo_show=station&bo_sid={station_id}

# Subtypes: station, strikes, network, longtime, other
GET https://www.lightningmaps.org/blitzortung/europe/index.php
    ?bo_page=statistics&bo_show=strikes&bo_station_id={station_id}
```

---

## Python Client Usage

### Installation

```bash
pip install requests websocket-client
```

### Quick Start

```python
from lightningmaps_client import LightningMapsClient, stream_lightning, get_recent_strokes

# Stream lightning strikes for 30 seconds
for stroke in stream_lightning(seconds=30):
    print(f"lat={stroke['lat']:.4f} lon={stroke['lon']:.4f} dev={stroke['dev']}m")

# Get 50 recent strokes quickly
strokes = get_recent_strokes(n=50)
print(f"Got {len(strokes)} strokes")
```

### WebSocket Streaming

```python
from lightningmaps_client import LightningMapsClient, SRC_BLITZORTUNG, SRC_LIGHTNINGMAPS

client = LightningMapsClient()

# Stream globally for 60 seconds
for stroke in client.stream_realtime(timeout=60.0, src_mask=SRC_BLITZORTUNG):
    ts = stroke['time'] / 1000  # to Unix seconds
    print(f"Strike: {stroke['lat']:.4f},{stroke['lon']:.4f} acc={stroke['dev']}m")

# Stream with bounding box (Europe)
for stroke in client.stream_realtime(
    bounds=(72.0, 45.0, 35.0, -12.0),  # (N, E, S, W)
    timeout=30.0
):
    print(stroke)

# Background streaming with callback
def handle_stroke(stroke):
    print(f"New strike at {stroke['lat']:.3f},{stroke['lon']:.3f}")

ws_client = client.stream_realtime_background(on_stroke=handle_stroke)
import time; time.sleep(30)
ws_client.stop()
```

### XHR Polling (no WebSocket dependency)

```python
client = LightningMapsClient()

# Single poll
data = client.poll_realtime()
strokes = data.get('d', [])
print(f"Got {len(strokes)} new strokes, next poll in {data.get('w')}ms")

# Continuous polling stream
for stroke in client.stream_realtime_xhr(timeout=60.0):
    print(f"Strike: lat={stroke['lat']} lon={stroke['lon']}")
```

### Station Data

```python
client = LightningMapsClient()

# Get European stations
data = client.get_stations('europe')
stations = data['stations']
print(f"Total European stations: {len(stations)}")

# Filter online stations
online = {sid: info for sid, info in stations.items() if info.get('s') not in ('D',)}
print(f"Online: {len(online)}")

# All regions
all_stations = client.get_all_stations()
print(f"Global stations: {len(all_stations)}")
```

### Tile Images

```python
client = LightningMapsClient()

# Get tile at zoom 5, centered on Europe
x, y = client.latlon_to_tile(48.0, 11.0, zoom=5)  # Munich
tile_png = client.get_lightning_tile(x, y, z=5, tile_type=5)
with open('lightning_tile.png', 'wb') as f:
    f.write(tile_png)

# Archive tile for specific time range
from datetime import datetime, timezone
from_dt = datetime(2026, 3, 24, 0, 0, 0, tzinfo=timezone.utc)
to_dt   = datetime(2026, 3, 24, 23, 59, 59, tzinfo=timezone.utc)
archive_png = client.get_archive_tile(x, y, z=5, from_time=from_dt, to_time=to_dt)
```

### Archive Maps

```python
client = LightningMapsClient()

# Yesterday's Europe map
img = client.get_archive_map_image('europe')
with open('europe_yesterday.png', 'wb') as f:
    f.write(img)

# Germany radar map for specific date
img = client.get_archive_map_image('europe', date='20260324', map_id='de_rad')

# 6-hour animation
gif = client.get_archive_animation('europe', date='20260324', hour_from=12, hour_range=6)
with open('europe_animation.gif', 'wb') as f:
    f.write(gif)
```

### Command-Line Demo

```bash
# Stream 60 seconds of data via WebSocket
python lightningmaps_client.py --duration 60 --method ws

# Use XHR polling fallback
python lightningmaps_client.py --duration 30 --method xhr

# Show stations info for Europe
python lightningmaps_client.py --info --region europe

# Request station data with each stroke
python lightningmaps_client.py --duration 30 --stations

# Only Blitzortung.org data (src=2)
python lightningmaps_client.py --duration 30 --src 2
```

---

## Network Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                        LightningMaps.org                           │
├──────────────────────────┬─────────────────────────────────────────┤
│  www.lightningmaps.org   │  Stations JSON, GeoJSON, Archive pages  │
│  live.lightningmaps.org  │  WebSocket + XHR real-time data         │
│  live2.lightningmaps.org │  WebSocket + XHR (load balanced)        │
│  tiles.lightningmaps.org │  PNG strike density tiles               │
│  map.lightningmaps.org   │  Background map tiles, radar            │
│  images.lightningmaps.org│  Archive images, animations, graphs     │
│  lmaps.org               │  Shortlink redirect service             │
│  counter.lightningmaps.org│ Piwik/Matomo analytics                 │
└──────────────────────────┴─────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                          Blitzortung.org                           │
├──────────────────────────┬─────────────────────────────────────────┤
│  ws1.blitzortung.org     │  Old-style WS server (port 80, no SSL)  │
│  ws2.blitzortung.org     │  Old-style WS server                    │
│  ws7.blitzortung.org     │  Old-style WS server                    │
│  ws8.blitzortung.org     │  Old-style WS server                    │
│  maps.blitzortung.org    │  Vector map (MapLibre GL, obfuscated JS)│
└──────────────────────────┴─────────────────────────────────────────┘
```

---

## Data Fields Reference

### Stroke Object

```json
{
  "time": 1774405664752,
  "lat":  36.238781,
  "lon":  26.560367,
  "src":  2,
  "srv":  1,
  "id":   13370274,
  "del":  1780,
  "dev":  161,
  "sta":  {"673": 0, "708": 1, ...}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `time` | int | UTC timestamp in **milliseconds** since epoch |
| `lat` | float | Latitude (-90 to +90) |
| `lon` | float | Longitude (-180 to +180) |
| `src` | int | Source integer: `1`=LightningMaps.org pipeline, `2`=Blitzortung.org standard |
| `srv` | int | Computing server ID |
| `id` | int | Stroke sequence ID (monotonically increasing per source) |
| `del` | int | Total detection-to-computation delay in milliseconds |
| `dev` | int | Location accuracy / standard deviation in meters |
| `sta` | dict | Map of `{station_id: status_flags}` (optional) |
| `alt` | float | Altitude estimate (rarely included) |

### Station Status Flags (in `sta` dict)

| Value | Meaning |
|-------|---------|
| `0` | Assigned but not used in calculation |
| `1` | Assigned to this stroke |
| `2` | Data used in triangulation calculation |
| `3` | Assigned and used |
| `64` | Special/flag status |
| `66` | Used + special |

### Source Bitmask Values (for `a` parameter in subscription request)

These control which data pipelines to subscribe to:

| Value | Description |
|-------|-------------|
| `2` | Blitzortung.org standard data |
| `4` | LightningMaps.org experimental data |
| `6` | Both sources (2 OR 4) — recommended |
| `8` | Testing/experimental data |

### Stroke `src` Field Values (in received stroke data)

The `src` integer in each stroke dict identifies the processing pipeline:

| Value | Description |
|-------|-------------|
| `1` | LightningMaps.org processing pipeline |
| `2` | Blitzortung.org standard processing |

The `flags` dict in each batch (`{"1": 2, "2": 2}`) indicates which src IDs are active.

---

## Known Limitations & Notes

1. **Rate limiting:** No explicit rate limiting discovered, but the servers hint at poll
   intervals (500ms-5000ms) via the `w` and `o` fields. Respect these.

2. **Archive availability:** Lightning archive data is available from 2021-03-18 onwards.

3. **Commercial use prohibited:** The copyright message explicitly forbids commercial use.

4. **ws1-8.blitzortung.org:** These old-style WebSocket servers (used by blitzortung.org's
   old raster map site) use plain WebSocket on port 80 (not WSS). They require a different
   message format from the lightningmaps.org servers.

5. **Protocol version:** The current version is 24. Using other values may cause issues.

6. **Tile cache:** Lightning tiles update approximately every 2 minutes. Archive tiles
   are static once generated.

7. **`from_lightningmaps_org: true`:** The server validates this field in WebSocket messages.
   Include it to avoid being rejected.

---

## License

Lightning data is copyright Blitzortung.org and contributors, CC-BY-SA 4.0.
This client code is provided for educational and research purposes.
See https://www.blitzortung.org for terms of use.
