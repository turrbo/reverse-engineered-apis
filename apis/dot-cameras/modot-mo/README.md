# MoDOT Traveler Information System — Python Client

A production-quality Python client for the **Missouri Department of Transportation (MoDOT)** Traveler Information System at [traveler.modot.org](https://traveler.modot.org).

**No authentication. No API key. No registration required.** All endpoints are public JSON feeds over HTTPS.

---

## Table of Contents

- [Overview](#overview)
- [Reverse Engineering Methodology](#reverse-engineering-methodology)
- [Discovered Endpoints](#discovered-endpoints)
  - [JSON Feed Endpoints](#json-feed-endpoints)
  - [REST Service Endpoints](#rest-service-endpoints)
  - [Static Asset Endpoints](#static-asset-endpoints)
- [Data Schemas](#data-schemas)
  - [StreamingCams2.json](#streamingcams2json)
  - [message.v2.json](#messagev2json)
  - [LinesV1.json](#linesv1json)
  - [MsgBrdV1.json](#msgbrdv1json)
  - [snapshot.json](#snapshotjson)
  - [TIS REST API](#tis-rest-api)
- [CDN & Streaming Architecture](#cdn--streaming-architecture)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [CLI Usage](#cli-usage)
- [Rate Limiting & Caching](#rate-limiting--caching)
- [Known Limitations](#known-limitations)

---

## Overview

The MoDOT Traveler Information System serves real-time traffic data for the state of Missouri via a web map application at `https://traveler.modot.org/map/`. The frontend is an Esri ArcGIS JavaScript 4.33 application that fetches data from a set of simple JSON feeds.

**What you can access:**

| Data Type | Count (live) | Format |
|-----------|-------------|--------|
| Streaming (HLS) traffic cameras | 880 cameras | HLS `.m3u8` |
| Snapshot (JPEG) traffic cameras | 20+ cameras | JPEG image |
| Traffic events (work zones, incidents) | 1,000+ events | JSON |
| Event polylines (road segment geometries) | 950+ lines | GeoJSON-style paths |
| Variable message signs (VMS/DMS) | 338 boards | JSON |
| Weather radar frames | 10 frames | PNG (georeferenced) |
| Mile marker geocoding | — | REST JSON |

---

## Reverse Engineering Methodology

### Step 1: Entry Point Discovery

Starting from `https://traveler.modot.org/` (which redirects to `/map/`), the HTML source reveals:

```html
<script src="js/site.js?v=03162026"></script>
```

The main JavaScript bundle is at:
```
https://traveler.modot.org/map/js/site.js?v=03162026
```

(The `v=` parameter is a date-based cache buster, format `MMDDYYYY`. The latest build as of 2026-03-27 is `v=03162026`.)

### Step 2: JavaScript Analysis

The `site.js` bundle (2,418 lines) contains all application logic. Key patterns found:

```javascript
// Feed URLs (all relative to https://traveler.modot.org/)
const url = "/timconfig/feed/desktop/message.v2.json";
const url = "/timconfig/feed/desktop/LinesV1.json";
const url = "/timconfig/feed/desktop/RcGeomV1.json";
const url = "/timconfig/feed/desktop/BPRV1.json";
const url = "/timconfig/feed/desktop/StreamingCams2.json";

// Config / static data
fetch("js/config.json")                      // map configuration
fetch(`js/snapshot.json?t=${timestamp}`)     // snapshot cameras

// TIS REST services
fetch(`${m_configData.MarkerFromLatTon2Service}?lat=...&lon=...&dpp=...`)
fetch(`${m_configData.LatLonFromMarkerService}?twid=...&mkr=...`)
fetch(`${m_configData.TiSvcGeometryService}?type=...&id=...`)

// Weather radar PNGs
image: `/timconfig/wxugradr${i}.png?t=${timestamp}`  // i = 0..9
```

### Step 3: Configuration File

`https://traveler.modot.org/map/js/config.json` exposes all service URLs:

```json
{
  "LatLonFromMarkerService": "/tisvc/api/Tms/LatLonFromMarker",
  "MarkerFromLatTon2Service": "/tisvc/api/Tms/MarkerFromLatLon2",
  "TiSvcGeometryService":    "/tisvc/api/Tms/GetGeometry",
  "traffic_tile_location":   "/realtimetraffic/",
  "vector_tile_url":         "https://mapsonline.modot.mo.gov/server/rest/services/..."
}
```

### Step 4: Authentication Analysis

**No authentication mechanisms exist.** The feeds return:

```
access-control-allow-origin: *
access-control-allow-methods: GET
access-control-allow-headers: *
```

CORS is fully open. There are no cookies, tokens, or API keys required. The site uses Imperva (Incapsula) CDN for DDoS protection but no application-level auth.

---

## Discovered Endpoints

All base URLs are relative to `https://traveler.modot.org`.

### JSON Feed Endpoints

These are the primary data feeds. All return `application/json`. Refresh approximately every 60 seconds.

| Endpoint | Description | Response Size |
|----------|-------------|---------------|
| `/timconfig/feed/desktop/StreamingCams2.json` | All HLS streaming cameras | ~135 KB |
| `/timconfig/feed/desktop/message.v2.json` | All traffic events (work zones, incidents) | ~512 KB |
| `/timconfig/feed/desktop/LinesV1.json` | Event polyline geometries | ~523 KB |
| `/timconfig/feed/desktop/MsgBrdV1.json` | Variable message sign readings | ~62 KB |
| `/timconfig/feed/desktop/RcCondV1.json` | Road conditions (winter/construction) | varies |
| `/timconfig/feed/desktop/RcGeomV1.json` | Road condition geometries | varies |
| `/timconfig/feed/desktop/BPRV1.json` | Bypass pavement route geometries | ~1.8 MB |
| `/map/js/snapshot.json` | Static snapshot camera index | ~3 KB |
| `/map/js/config.json` | Map application configuration | ~37 KB |

> **Note:** `/timconfig/` directory listing returns HTTP 403 (directory browsing disabled), but individual files are accessible.

### REST Service Endpoints

Base: `https://traveler.modot.org/tisvc/api/Tms/`

All return `application/json; charset=utf-8` with `access-control-allow-origin: *`.

#### `GET /tisvc/api/Tms/MarkerFromLatLon2`

Reverse-geocodes a lat/lon to the nearest highway mile marker.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | float | Yes | Latitude (WGS-84) |
| `lon` | float | Yes | Longitude (WGS-84) |
| `dpp` | float | Yes | Degrees per pixel (snap tolerance); `0.001` ≈ 100m |

**Example request:**
```
GET /tisvc/api/Tms/MarkerFromLatLon2?lat=38.627&lon=-90.199&dpp=0.001
```

**Example response:**
```json
{
  "TravelwayId": 6373,
  "SignText": "WEST IS 64 MILE 39.8",
  "Latitude": 38.622873838111,
  "Longitude": -90.1995869254996
}
```

#### `GET /tisvc/api/Tms/LatLonFromMarker`

Converts a travelway ID + mile marker to lat/lon coordinates.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `twid` | int | Yes | MoDOT travelway ID |
| `mkr` | float | Yes | Mile marker number |

**Example request:**
```
GET /tisvc/api/Tms/LatLonFromMarker?twid=19&mkr=100
```

**Example response:**
```json
{
  "TravelwayId": 19,
  "SignText": "EAST IS 70 MILE 100.0",
  "Latitude": 38.9351160718907,
  "Longitude": -92.8104167584798
}
```

#### `GET /tisvc/api/Tms/GetGeometry`

Returns the geometry for a specific traffic event by type and ID.

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `type` | string | Yes | Event type code (e.g., `WZ`, `TI`) |
| `id` | int | Yes | Event object ID |

**Example response:**
```json
{
  "Mbr": null,
  "Shape": null
}
```

> **Note:** This endpoint returns geometry when an event ID is matched. The `Mbr` (minimum bounding rectangle) and `Shape` fields may be null for events without stored geometry.

### Static Asset Endpoints

#### Weather Radar Frames

10 animated weather radar PNG images overlaid on the Missouri state map.

**Pattern:** `https://traveler.modot.org/timconfig/wxugradr{index}.png`

- Index range: `0` (oldest) to `9` (newest)
- Update interval: ~10 minutes
- Image size: 100–200 KB per frame
- Geographic extent (WGS-84): `xmin=-98.4375, ymin=31.82, xmax=-87.1875, ymax=43.07`
- Add `?t=<unix_timestamp>` to bypass cache

**Example:**
```
https://traveler.modot.org/timconfig/wxugradr9.png?t=1743110000
```

#### Snapshot Camera Images

**Pattern:** `https://traveler.modot.org/traffic_camera_snapshots/{name}/{name}.jpg`

**Example:**
```
https://traveler.modot.org/traffic_camera_snapshots/I-44@RollaHighwayPatrol/I-44@RollaHighwayPatrol.jpg
```

---

## Data Schemas

### StreamingCams2.json

Array of camera objects. 880 cameras as of 2026-03-27.

```json
[
  {
    "location": "141 AT BIG BEND, MM 17.5",
    "x": -90.500296,
    "y": 38.567,
    "rtmp": null,
    "html": "https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_203/playlist.m3u8"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `location` | string | Human-readable location label |
| `x` | float | Longitude (WGS-84) |
| `y` | float | Latitude (WGS-84) |
| `rtmp` | string\|null | Legacy RTMP stream URL (almost always null) |
| `html` | string | HLS master playlist URL |

### message.v2.json

Array of traffic event objects. 1,000+ events typical.

```json
[
  {
    "OID": 2,
    "MT": "WZ",
    "MST": "WZ",
    "LOI": "HIGH",
    "GEOM": {
      "x": -94.395,
      "y": 39.1668,
      "spatialReference": { "wkid": 4326 }
    },
    "MSG": "<div>Expect delays due to Work Zone ...</div>",
    "MSGS": "<div>Expect delays due to BRIDGE MAINTENANCE on MO-291 Northbound.</div>",
    "MSGL": "MO 291 N JACKSON"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `OID` | int | Object ID (unique in this snapshot) |
| `MT` | string | Major type: `WZ`, `TI`, `CL` |
| `MST` | string | Minor sub-type: `WZ`, `PLANNED`, `IMPACT`, `CL` |
| `LOI` | string | Level of impact (see table below) |
| `GEOM.x` | float | Longitude |
| `GEOM.y` | float | Latitude |
| `MSG` | string | Full HTML description |
| `MSGS` | string | Short HTML description |
| `MSGL` | string | Short road/location label |

**Major Type (MT) codes:**

| Code | Meaning | Count (typical) |
|------|---------|-----------------|
| `WZ` | Work Zone | ~930 |
| `TI` | Traffic Impact / Incident | ~28 |
| `CL` | Commuter Lot | ~108 |

**Level of Impact (LOI) codes:**

| Code | Meaning |
|------|---------|
| `CLOSED` | Road closed |
| `HIGH` | Expect delays |
| `MEDIUM` | Possible delays |
| `FUTURE` | Future/scheduled work zone |
| `EXPECT DELAYS` | (Planned event variant) |
| `POSSIBLE DELAYS` | (Planned event variant) |
| `CL` | Commuter lot |

### LinesV1.json

Array of polyline geometries corresponding to traffic events. ~950 items.

```json
[
  {
    "MT": "WZ",
    "MST": "WZ",
    "LOI": "MEDIUM",
    "GEOM": {
      "paths": [
        [
          [-92.1431, 37.8218],
          [-92.1436, 37.8217],
          ...
        ]
      ],
      "spatialReference": { "wkid": 4326 }
    }
  }
]
```

Coordinate pairs are `[longitude, latitude]` (GeoJSON convention).

### MsgBrdV1.json

Array of variable message sign (VMS) current readings. ~338 signs.

```json
[
  {
    "msg": "I-35 4 MIN<br />4 MILES AHEAD",
    "dev": "K10 EB at BEFORE WOODLAND",
    "pst": null,
    "x": -94.83012,
    "y": 38.94094,
    "imageurl": "https://www.kcscout.net/TransSuite.KmlFileServer/animated/29001001-2.png"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `msg` | string | Sign message text (may contain `<br />`) |
| `dev` | string | Sign device identifier / location |
| `pst` | string\|null | Posted timestamp |
| `x` | float | Longitude |
| `y` | float | Latitude |
| `imageurl` | string | URL to sign face image (animated GIF or PNG) |

> **Note:** Kansas City area VMS images are served by [KC Scout](https://www.kcscout.net/) at `https://www.kcscout.net/TransSuite.KmlFileServer/animated/...`

### snapshot.json

Object with a `cameras` array. ~20 cameras.

```json
{
  "cameras": [
    {
      "id": 1,
      "caption": "BUS-60 @ US-67 Poplar Bluff",
      "url": "/traffic_camera_snapshots/BUS-60@US-67_PoplarBluff/BUS-60@US-67_PoplarBluff.jpg",
      "location": {
        "x": -90.407865,
        "y": 36.758706
      }
    }
  ]
}
```

### TIS REST API

Response schema for `/tisvc/api/Tms/MarkerFromLatLon2` and `/tisvc/api/Tms/LatLonFromMarker`:

```json
{
  "TravelwayId": 6373,
  "SignText": "WEST IS 64 MILE 39.8",
  "Latitude": 38.622873838111,
  "Longitude": -90.1995869254996
}
```

---

## CDN & Streaming Architecture

### Live Video Streams (HLS)

MoDOT operates a fleet of Wowza Streaming Engine servers that serve HLS streams. The servers are named:

| Host | Cameras |
|------|---------|
| `sfs01-traveler.modot.mo.gov` | ~128 cameras |
| `sfs02-traveler.modot.mo.gov` | ~139 cameras |
| `sfs03-traveler.modot.mo.gov` | ~116 cameras |
| `sfs04-traveler.modot.mo.gov` | ~6 cameras |
| `sfs07-traveler.modot.mo.gov` | ~2 cameras |

**HLS Master Playlist URL pattern:**
```
https://{sfsNN}-traveler.modot.mo.gov/rtplive/{CAMERA_ID}/playlist.m3u8
```

**Chunklist URL pattern:**
```
https://{sfsNN}-traveler.modot.mo.gov/rtplive/{CAMERA_ID}/chunklist_w{session}.m3u8
```

**MPEG-TS segment URL pattern:**
```
https://{sfsNN}-traveler.modot.mo.gov/rtplive/{CAMERA_ID}/media_w{session}_{seq}.ts
```

The master playlist response:
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=232117,CODECS="avc1.42c00c",RESOLUTION=320x240
chunklist_w1478772944.m3u8
```

Streams are:
- **Resolution:** 320×240 pixels
- **Bandwidth:** ~230 kbps
- **Codec:** H.264 baseline (avc1.42c00c)
- **Segment duration:** 4–6 seconds
- **No authentication required**

### Playing a Stream

```bash
# VLC
vlc "https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8"

# ffplay
ffplay "https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8"

# ffmpeg (save to file)
ffmpeg -i "https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8" \
       -c copy output.mp4
```

---

## Quick Start

```python
from modot_client import MoDOTClient

client = MoDOTClient()

# --- Streaming cameras ---
cameras = client.get_streaming_cameras()
print(f"{len(cameras)} cameras available")

# Stream URL for the first camera:
print(cameras[0].stream_url)
# → https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8

# Filter by bounding box (St. Louis area)
stl = client.get_streaming_cameras(
    min_lat=38.35, max_lat=38.96,
    min_lon=-90.89, max_lon=-90.02,
)

# Filter by road name
i70_cams = client.get_streaming_cameras(location_filter="70 AT")

# --- Traffic events ---
# All active road closures
closures = client.get_traffic_events(level="CLOSED")
for e in closures:
    print(e.message_label, e.impact_label)

# Work zones with high impact
high_wz = client.get_traffic_events(major_type="WZ", level="HIGH")

# I-70 incidents
incidents = client.get_traffic_events(major_type="TI", location_filter="IS 70")

# --- Snapshot cameras ---
snaps = client.get_snapshot_cameras()
for s in snaps:
    print(s.caption, s.fresh_url())  # cache-busted URL

# --- Variable message signs ---
boards = client.get_message_boards()
for b in boards:
    print(b.device, b.message.replace("<br />", " | "))

# --- Mile marker geocoding ---
# Nearest mile marker to downtown St. Louis
result = client.get_marker_from_latlon(lat=38.627, lon=-90.199)
print(result.sign_text)  # "WEST IS 64 MILE 39.8"

# I-70 East at Mile 100
loc = client.get_latlon_from_marker(travelway_id=19, mile_marker=100)
print(loc.sign_text)      # "EAST IS 70 MILE 100.0"
print(loc.latitude, loc.longitude)

# --- Weather radar ---
frames = client.get_radar_frames()
latest = frames[-1]  # index 9 = most recent
print(latest.fresh_url())  # PNG with cache-busting timestamp
```

---

## API Reference

### `MoDOTClient`

```python
class MoDOTClient(timeout=30, retries=3)
```

#### Camera Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_streaming_cameras(min_lat, max_lat, min_lon, max_lon, location_filter)` | `List[StreamingCamera]` | Live HLS video cameras |
| `get_snapshot_cameras(location_filter)` | `List[SnapshotCamera]` | JPEG snapshot cameras |

#### Traffic Event Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_traffic_events(major_type, level, location_filter)` | `List[TrafficEvent]` | Work zones, incidents |
| `get_event_lines(major_type, level)` | `List[EventLine]` | Polyline geometries |

#### Sign Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_message_boards(message_filter)` | `List[MessageBoard]` | Variable message signs |

#### Geocoding Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_marker_from_latlon(lat, lon, degrees_per_pixel)` | `MileMarkerResult` | Lat/lon → mile marker |
| `get_latlon_from_marker(travelway_id, mile_marker)` | `LatLonResult` | Mile marker → lat/lon |

#### Other Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_radar_frames()` | `List[RadarFrame]` | Weather radar overlay frames |

---

## CLI Usage

```bash
# Full demo of all endpoints
python modot_client.py demo

# List all streaming cameras
python modot_client.py cameras

# Filter cameras by road name
python modot_client.py cameras --filter "I-70"

# List all traffic events
python modot_client.py events

# Filter by type and severity
python modot_client.py events --type WZ --level CLOSED

# Filter by location
python modot_client.py events --filter "IS 70"

# Get mile marker from lat/lon
python modot_client.py marker 38.627 -90.199

# List variable message signs
python modot_client.py boards

# List weather radar frame URLs
python modot_client.py radar

# List snapshot cameras
python modot_client.py snapshots
```

**Sample output:**
```
============================================================
  Streaming Cameras (sample of 10)
============================================================
Fetching from: https://traveler.modot.org/timconfig/feed/desktop/StreamingCams2.json
Total streaming cameras: 880
CDN server distribution: {'sfs02': 139, 'sfs01': 128, 'sfs03': 116, 'sfs04': 6, 'sfs07': 2}

  [MODOT_CAM_209] 141 AT 21, MM 27.1
    Coords: (38.462300, -90.424496)
    Stream: https://sfs02-traveler.modot.mo.gov/rtplive/MODOT_CAM_209/playlist.m3u8
  ...
```

---

## Rate Limiting & Caching

There are no documented rate limits. However, to be a good citizen:

- The feeds refresh every ~60 seconds; polling more frequently yields identical data.
- Cache feed responses for at least 30–60 seconds before re-fetching.
- The `timconfig` feeds are large (up to 1.8 MB); cache aggressively.
- Use the `?t=<timestamp>` cache-buster only when you genuinely need fresh data.

**Recommended polling intervals:**

| Feed | Recommended Interval |
|------|----------------------|
| `StreamingCams2.json` | 5 minutes (list rarely changes) |
| `message.v2.json` | 60 seconds |
| `LinesV1.json` | 60 seconds |
| `MsgBrdV1.json` | 30–60 seconds |
| `snapshot.json` | 5 minutes |
| Snapshot images | 2–5 minutes |
| Radar frames | 10 minutes |

---

## Known Limitations

1. **No incident detail endpoint**: The `GetGeometry` REST endpoint exists but returns sparse data (`Mbr: null, Shape: null`) for most queries. Full incident details are embedded in the HTML of `message.v2.json`.

2. **Road conditions feed**: `RcCondV1.json` and `RcGeomV1.json` return empty arrays outside of winter months or major road events. These are seasonal feeds.

3. **Snapshot camera index is static**: The `snapshot.json` file lists ~20 cameras. The actual number of snapshot cameras on the system is unknown. The list is curated by MoDOT.

4. **HLS stream latency**: Live streams have 15–30 seconds of latency inherent to HLS segmenting.

5. **RTMP field**: The `rtmp` field in `StreamingCams2.json` is always `null` in current data. RTMP streaming appears to have been deprecated.

6. **No WebSocket / push**: All data is poll-based. There is no WebSocket or server-sent events endpoint for live updates.

7. **KC Scout data**: Message board images for the Kansas City metro are served by KC Scout (`www.kcscout.net`), a separate ATMS operated by KCATA/KDOT. MoDOT only provides the sign locations and text.

8. **Real-time traffic tiles**: Traffic flow tiles are served at `/realtimetraffic/` in the Esri cache format (`L{z}/R{y}/C{x}.png`). These tiles require the Esri ArcGIS JS API coordinate system and are not standard slippy map tiles.

---

## Technical Notes

### Infrastructure

- **Web server**: Microsoft IIS (403 on directory browse, `TS01e413ea` cookie = F5 BIG-IP load balancer)
- **CDN/WAF**: Imperva (Incapsula) — `x-cdn: Imperva` response header
- **Map platform**: Esri ArcGIS JavaScript API 4.33
- **Vector tiles**: Hosted on `mapsonline.modot.mo.gov` (ArcGIS Server)
- **Streaming**: Wowza Streaming Engine on `sfsNN-traveler.modot.mo.gov`

### Request Headers

The client sets `User-Agent: MoDOT-Python-Client/1.0`. No other headers are required. The API returns `access-control-allow-origin: *`.

### Coordinate System

All coordinates are **WGS-84 (EPSG:4326)**. The Missouri state bounding box used by the application:

```
xmin: -95.9158    ymin: 35.155382
xmax: -88.981386  ymax: 41.361416
```

---

*Data is sourced from the Missouri Department of Transportation, a public agency. This client is for informational and research purposes. Respect MoDOT's infrastructure and observe rate limits.*
