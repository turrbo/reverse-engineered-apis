# Caltrans CWWP2 Traffic Camera Client

A production-quality Python client for the California Department of Transportation (Caltrans) **Commercial Wholesale Web Portal** (CWWP2) — the public data hub serving real-time traffic camera feeds, changeable message signs, chain controls, and roadway weather information across all 12 California Caltrans districts.

**No API key required. No authentication. No third-party packages. Standard library only.**

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Data Source Overview](#data-source-overview)
3. [Reverse Engineering Notes](#reverse-engineering-notes)
4. [Discovered Endpoints](#discovered-endpoints)
5. [Data Formats and Field Descriptions](#data-formats-and-field-descriptions)
6. [Python Client API](#python-client-api)
7. [CLI Reference](#cli-reference)
8. [Caltrans Districts](#caltrans-districts)
9. [Image & Stream CDN Patterns](#image--stream-cdn-patterns)
10. [Rate Limits & Fair Use Policy](#rate-limits--fair-use-policy)
11. [Known Limitations](#known-limitations)

---

## Quick Start

```bash
# List all cameras in the Bay Area (District 4) with live video streams
python3 caltrans_client.py list --district 4 --streaming

# Show full details (including stream URL) for one camera
python3 caltrans_client.py show 7 1 --resolve-stream

# Download the current JPEG snapshot for a camera
python3 caltrans_client.py image 7 1 --output /tmp/cam.jpg

# Export all LA cameras as GeoJSON
python3 caltrans_client.py list --district 7 --format geojson > la_cameras.geojson

# Run a live end-to-end demonstration
python3 caltrans_client.py demo
```

```python
from caltrans_client import CaltransClient

client = CaltransClient()

# Get all cameras in LA (District 7)
cameras = client.get_cameras(7)
print(f"District 7: {len(cameras)} cameras")

# Cameras with live HLS video streams
streaming = client.filter_streaming(cameras)
print(f"  {len(streaming)} have live video streams")

# Print stream URLs
for cam in streaming[:3]:
    print(f"  {cam.location.location_name}")
    print(f"    Image : {cam.image_url_with_cache_bust()}")
    print(f"    Stream: {cam.streaming_video_url}")
```

---

## Data Source Overview

| Source URL | Description |
|---|---|
| `https://cwwp2.dot.ca.gov/` | Main data portal (CWWP2) |
| `https://cwwp2.dot.ca.gov/vm/iframemap.htm` | Interactive map viewer |
| `https://cwwp2.dot.ca.gov/vm/js/cctv27.js` | JS array with all ~3,165 camera locations |
| `https://cwwp2.dot.ca.gov/data/d{N}/cctv/cctvStatus{DNN}.json` | Per-district structured data |
| `https://cwwp2.dot.ca.gov/data/d{N}/cctv/image/{id}/{id}.jpg` | Live JPEG snapshots |
| `https://wzmedia.dot.ca.gov/D{N}/{stream}.stream/playlist.m3u8` | HLS video streams |

**Camera counts verified live (March 2026):**

| District | Cameras | Coverage |
|---|---|---|
| 1 | 140 | Del Norte, Humboldt, Lake, Mendocino |
| 2 | 91 | Lassen, Modoc, Shasta, Siskiyou, Tehama, Trinity |
| 3 | 271 | Sacramento, El Dorado, Placer, Yolo, Sutter + more |
| 4 | 717 | Bay Area: SF, Oakland, San Jose, Marin, Sonoma |
| 5 | 180 | Monterey, SLO, Santa Barbara, Santa Cruz |
| 6 | 128 | Fresno, Kings, Madera, Tulare (Central Valley) |
| 7 | 498 | Los Angeles, Ventura |
| 8 | 501 | Riverside, San Bernardino (Inland Empire) |
| 9 | 23 | Alpine, Inyo, Mono (Eastern Sierra) |
| 10 | 151 | Stockton/Modesto: San Joaquin, Stanislaus + more |
| 11 | 324 | San Diego, Imperial |
| 12 | 406 | Orange County |
| **Total** | **3,430** | **All of California** |

---

## Reverse Engineering Notes

### Entry Point

The main map page at `https://cwwp2.dot.ca.gov/vm/iframemap.htm` loads three JavaScript files:

```html
<script src="https://maps.google.com/maps/api/js?key=AIzaSyCzQOPSq9GEdIFxt91_KZ6742hYRhNDhL4"></script>
<script src="https://cwwp2.dot.ca.gov/vm/js/oss.js"></script>
<script src="https://cwwp2.dot.ca.gov/vm/js/cctv27.js"></script>
<script src="https://cwwp2.dot.ca.gov/vm/js/map.js"></script>
```

### cctv27.js — The Camera Index

`cctv27.js` (~400KB) contains a JavaScript array with one entry per camera. Each entry is a pipe-delimited string using the Unicode character `U+FFFD` (replacement character, `\xFF`) as a delimiter:

```javascript
cctv[10] = 'https://cwwp2.dot.ca.gov/vm/loc/d1/us101eureka5thrstreetlookingnorth.htm\xFF-124.153431\xFF40.803788\XFFUS-101 : Eureka / 5th & R Street - Looking North (C034)\xFF1';
```

**Fields (0-indexed):**

| # | Content | Example |
|---|---|---|
| 0 | Camera page URL | `https://cwwp2.dot.ca.gov/vm/loc/d1/...htm` |
| 1 | Longitude | `-124.153431` |
| 2 | Latitude | `40.803788` |
| 3 | Title / name | `US-101 : Eureka / 5th & R Street...` |
| 4 | isStreaming | `1` = has HLS stream, `0` = static only |

The array has 3,165 entries (cctv[1] through cctv[3165]).

### Per-Camera HTML Pages

Each camera has a dedicated HTML page at `https://cwwp2.dot.ca.gov/vm/loc/{district}/{camera_slug}.htm`.

These pages reveal:
- `var posterURL` — the JPEG snapshot URL
- `var videoStreamURL` — the HLS stream URL (if applicable)
- `var routePlace` — route and city context
- `var locationName` — full descriptive name
- External JS: `https://cwwp2.dot.ca.gov/vm/js/wx/{district}/{camera_slug}.js` — weather forecast data

**Non-streaming camera:**
```html
<script>
  var routePlace = "US-101 : Fortuna";
  var locationName = "US-101 : North Of SR-36 - Looking North (C003)";
  var posterURL = "https://cwwp2.dot.ca.gov/data/d1/cctv/image/us101northofsr36lookingnorth/us101northofsr36lookingnorth.jpg";
</script>
```

**Streaming camera (adds `videoStreamURL`):**
```html
<script>
  var posterURL = "https://cwwp2.dot.ca.gov/data/d1/cctv/image/us101eureka5thrstreetlookingnorth/us101eureka5thrstreetlookingnorth.jpg";
  var videoStreamURL = "https://wzmedia.dot.ca.gov/D1/eureka_5th_r_320x240.stream/playlist.m3u8";
</script>
```

### Cache Busting

The official `video.js` script appends the current time in milliseconds to all image URLs:

```javascript
function populate(isStream) {
    var today = new Date();
    document.getElementById("cctvImage").src = posterURL + "?" + today.getTime();
}
```

This pattern should be used when polling images to avoid stale cached responses.

### The Structured Data API (CWWP2 Portal)

The developer portal at `https://cwwp2.dot.ca.gov/` exposes the same data in machine-readable formats. This is the recommended integration path and is what this client uses.

---

## Discovered Endpoints

### CCTV Camera Data

```
GET https://cwwp2.dot.ca.gov/data/d{N}/cctv/cctvStatus{DNN}.json
GET https://cwwp2.dot.ca.gov/data/d{N}/cctv/cctvStatus{DNN}.csv
GET https://cwwp2.dot.ca.gov/data/d{N}/cctv/cctvStatus{DNN}.xml
GET https://cwwp2.dot.ca.gov/data/d{N}/cctv/cctvStatus{DNN}.txt
```

Where `N` = district number (1–12), `DNN` = zero-padded two-digit district (01–12).

**Examples:**
- `https://cwwp2.dot.ca.gov/data/d7/cctv/cctvStatusD07.json` — District 7 (LA)
- `https://cwwp2.dot.ca.gov/data/d4/cctv/cctvStatusD04.json` — District 4 (Bay Area)

**Response:** JSON object with `data` array of camera objects. See [Data Formats](#data-formats-and-field-descriptions).

**Update frequency:** As necessary (typically when camera metadata changes). The *image URLs* inside update independently based on `currentImageUpdateFrequency`.

---

### CCTV Live Images

```
GET https://cwwp2.dot.ca.gov/data/d{N}/cctv/image/{camera_id}/{camera_id}.jpg
```

**Response:** `image/jpeg`, typical size 20–80 KB, `Access-Control-Allow-Origin: *`

**Cache busting:** Append `?t={epoch_ms}` — the server respects this and returns a fresh image.

**Historical reference images (up to 12 frames back):**

```
GET https://cwwp2.dot.ca.gov/data/d{N}/cctv/image/{camera_id}/previous/{camera_id}-{frame}.jpg
```

Where `frame` is 1 (most recent past) through 12 (oldest).

**Update frequencies vary by camera** (field `currentImageUpdateFrequency` in minutes):
- High-traffic urban cameras: 2 minutes
- Rural/mountain cameras: 10–60 minutes
- Typical average: 10–15 minutes

---

### HLS Video Streams

```
GET https://wzmedia.dot.ca.gov/D{N}/{stream_name}.stream/playlist.m3u8
```

- CDN: `wzmedia.dot.ca.gov` (separate from `cwwp2.dot.ca.gov`)
- Response: M3U8 master playlist, `Content-Type: application/vnd.apple.mpegurl`
- CORS: `Access-Control-Allow-Origin: *`

**Master playlist content:**
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=124368,CODECS="avc1.4d001f",RESOLUTION=1280x720
chunklist_w{token}.m3u8
```

**Chunklist URL pattern:**
```
GET https://wzmedia.dot.ca.gov/D{N}/{stream_name}.stream/chunklist_w{token}.m3u8
```

The `{token}` is a session token regenerated frequently. Always resolve from the master playlist rather than hardcoding.

**Stream naming patterns observed:**
- `CCTV-{number}.stream` (most D7 cameras): `CCTV-196.stream`
- `{city}_{location}.stream` (D1/D2): `eureka_4th_l_320x240.stream`
- District prefix: `D7`, `D1`, etc.

**Playing a stream with ffplay:**
```bash
ffplay https://wzmedia.dot.ca.gov/D7/CCTV-196.stream/playlist.m3u8
```

---

### Changeable Message Signs (CMS)

```
GET https://cwwp2.dot.ca.gov/data/d{N}/cms/cmsStatus{DNN}.json
```

Same district/suffix pattern as CCTV. Contains sign locations and currently displayed messages.

---

### Chain Controls

```
GET https://cwwp2.dot.ca.gov/data/d{N}/cc/ccStatus{DNN}.json
```

Mountain pass chain requirement status. Relevant primarily for Districts 2, 3, 8, 9.

**Status codes:**

| Code | Meaning |
|---|---|
| R1 | Chains or snow tires required |
| R2 | Chains required on all vehicles except 4WD with snow tires |
| R3 | Chains required on ALL vehicles, no exceptions |
| none / empty | No chain controls in effect |

---

### Roadway Weather Information Systems (RWIS)

```
GET https://cwwp2.dot.ca.gov/data/d{N}/rwis/rwisStatus{DNN}.json
```

Only certain districts report RWIS data. Confirmed active: D2, D3, D6, D8, D10.

---

### Per-Camera Weather Forecast (JavaScript)

```
GET https://cwwp2.dot.ca.gov/vm/js/wx/{district}/{camera_slug}.js
```

**Example:** `https://cwwp2.dot.ca.gov/vm/js/wx/d7/i110196avenue26offramp.js`

**Response:** JavaScript variable assignments (not JSON). Contains NWS forecast data:

```javascript
var localDate       = "2026-03-27";
var localTime       = "12:30:00 PDT";
var periodName0     = "Friday";
var periodName1     = "Friday Night";
var weatherSummary0 = "Mostly Sunny";
var weatherSummary1 = "Patchy Fog";
var temperatureHigh = "86";
var temperatureLow  = "59";
var sunrise         = "06:47 PDT";
var sunset          = "19:09 PDT";
var elevation       = "95";   // feet
```

Note: This is a JavaScript file, not JSON — parse with regex or string splitting.

---

### Google Maps API Key

The map viewer uses a Google Maps JavaScript API key:
```
AIzaSyCzQOPSq9GEdIFxt91_KZ6742hYRhNDhL4
```
This key is embedded in the public page source and is restricted to the `cwwp2.dot.ca.gov` origin. Do not use it in your own applications.

---

## Data Formats and Field Descriptions

### CCTV JSON Response Structure

```json
{
  "data": [
    {
      "cctv": {
        "index": "1",
        "recordTimestamp": {
          "recordDate": "2024-05-07",
          "recordTime": "16:27:07",
          "recordEpoch": "1715124427"
        },
        "location": {
          "district": "7",
          "locationName": "I-110 : (196) Avenue 26 Off Ramp",
          "nearbyPlace": "Cypress Park",
          "longitude": "-118.2215",
          "latitude": "34.0837",
          "elevation": "95",
          "direction": "South",
          "county": "Alameda",
          "route": "I-110",
          "routeSuffix": "",
          "postmilePrefix": "",
          "postmile": "26.01",
          "alignment": "",
          "milepost": "25.892"
        },
        "inService": "true",
        "imageData": {
          "imageDescription": "",
          "streamingVideoURL": "https://wzmedia.dot.ca.gov/D7/CCTV-196.stream/playlist.m3u8",
          "static": {
            "currentImageUpdateFrequency": "2",
            "currentImageURL": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i110196avenue26offramp/i110196avenue26offramp.jpg",
            "referenceImageUpdateFrequency": "15",
            "referenceImage1UpdateAgoURL": "https://cwwp2.dot.ca.gov/data/d7/cctv/image/i110196avenue26offramp/previous/i110196avenue26offramp-1.jpg",
            "referenceImage2UpdatesAgoURL": "...",
            "referenceImage3UpdatesAgoURL": "...",
            ...
            "referenceImage12UpdatesAgoURL": "..."
          }
        }
      }
    }
  ]
}
```

### Field Reference

| Field | Type | Notes |
|---|---|---|
| `index` | string (int) | Sequential index within the district feed |
| `recordTimestamp.recordDate` | string | YYYY-MM-DD of last metadata update |
| `recordTimestamp.recordTime` | string | HH:MM:SS Pacific time |
| `recordTimestamp.recordEpoch` | string (int) | Unix epoch seconds (may be absent) |
| `location.district` | string (int) | Caltrans district 1–12 |
| `location.locationName` | string | Full descriptive camera name |
| `location.nearbyPlace` | string | Nearest city or landmark |
| `location.longitude` | string (float) | WGS-84 decimal degrees (negative = west) |
| `location.latitude` | string (float) | WGS-84 decimal degrees |
| `location.elevation` | string (int) | Feet above sea level |
| `location.direction` | string | Camera view direction |
| `location.county` | string | California county |
| `location.route` | string | Route prefix + number (e.g. `I-110`, `US-101`, `SR-20`) |
| `location.postmile` | string (float) | Postmile along route |
| `location.milepost` | string (float) | Alternate milepost reference |
| `inService` | string (bool) | `"true"` or `"false"` |
| `imageData.streamingVideoURL` | string | HLS M3U8 URL, empty or `"Not Reported"` if unavailable |
| `imageData.static.currentImageURL` | string | Latest JPEG snapshot URL |
| `imageData.static.currentImageUpdateFrequency` | string (int) | Minutes between image updates |
| `imageData.static.referenceImage1UpdateAgoURL` | string | Most recent historical frame |
| `imageData.static.referenceImage{N}UpdatesAgoURL` | string | N=2..12, older historical frames |

**Note:** All numeric fields come as strings from the JSON API. The Python client converts them to the appropriate types.

---

## Python Client API

### Class: `CaltransClient`

```python
CaltransClient(
    timeout: int = 30,
    user_agent: str = "Mozilla/5.0 ...",
    retry_count: int = 3,
    retry_delay: float = 1.5
)
```

#### Camera methods

| Method | Returns | Description |
|---|---|---|
| `get_cameras(district)` | `List[Camera]` | All cameras for one district |
| `iter_cameras(district)` | `Iterator[Camera]` | Iterator version |
| `get_all_cameras(districts=None, skip_errors=True)` | `List[Camera]` | Multiple/all districts |
| `fetch_image(camera, cache_bust=True)` | `bytes` | Download current JPEG |
| `fetch_reference_image(camera, frame=1)` | `bytes` | Download historical JPEG (1–12) |
| `get_hls_chunklist_url(camera)` | `str` | Resolve HLS master → chunklist URL |

#### Filter methods

| Method | Description |
|---|---|
| `filter_by_route(cameras, route)` | Filter by route (case-insensitive, partial match) |
| `filter_by_county(cameras, county)` | Filter by county name |
| `filter_streaming(cameras)` | Only cameras with HLS streams |
| `filter_in_service(cameras)` | Only cameras currently in service |
| `search(cameras, query, fields=None)` | Full-text search across metadata |

#### Other feeds

| Method | Returns | Description |
|---|---|---|
| `get_cms_signs(district)` | `List[CMSSign]` | Changeable Message Signs |
| `get_chain_controls(district)` | `List[ChainControl]` | Chain control locations/status |
| `get_district_summary()` | `dict` | Camera counts per district |

#### Static methods

| Method | Description |
|---|---|
| `CaltransClient.cameras_to_geojson(cameras)` | Convert to GeoJSON FeatureCollection |
| `CaltransClient.cctv_json_url(district)` | Build JSON endpoint URL |
| `CaltransClient.cctv_csv_url(district)` | Build CSV endpoint URL |

### Dataclasses

#### `Camera`
Core camera object with shortcuts: `.district`, `.route`, `.county`, `.coords` (lat/lon tuple).

Key attributes: `index`, `location` (CameraLocation), `timestamp` (RecordTimestamp), `in_service`, `current_image_url`, `streaming_video_url`, `has_streaming`, `static_images` (StaticImages).

#### `CameraLocation`
All geographic and administrative fields: `district`, `location_name`, `nearby_place`, `longitude`, `latitude`, `elevation`, `direction`, `county`, `route`, `postmile`, etc.

#### `StaticImages`
Image URL collection: `current_image_url`, `current_image_update_frequency`, `reference_image_update_frequency`, `reference_images` (list of 12 historical URLs).

### Usage Examples

```python
from caltrans_client import CaltransClient
import json

client = CaltransClient()

# --- Basic camera listing ---
cameras = client.get_cameras(7)          # District 7 = LA/Ventura
streaming = client.filter_streaming(cameras)
print(f"D7 total: {len(cameras)}, streaming: {len(streaming)}")

# --- Statewide I-5 cameras ---
all_cams = client.get_all_cameras()      # ~3,430 cameras, ~15s to fetch all
i5 = client.filter_by_route(all_cams, "I-5")
print(f"I-5 cameras statewide: {len(i5)}")

# --- Fetch a JPEG image ---
cam = cameras[0]
jpg_bytes = client.fetch_image(cam)
with open("snapshot.jpg", "wb") as f:
    f.write(jpg_bytes)

# --- Historical frames ---
for frame_num in range(1, 6):
    data = client.fetch_reference_image(cam, frame=frame_num)
    with open(f"frame_{frame_num}.jpg", "wb") as f:
        f.write(data)

# --- HLS stream resolution ---
if cam.has_streaming:
    chunklist = client.get_hls_chunklist_url(cam)
    print(f"Play with: ffplay {chunklist}")

# --- GeoJSON export ---
geojson = CaltransClient.cameras_to_geojson(cameras)
with open("d7_cameras.geojson", "w") as f:
    json.dump(geojson, f)

# --- Full-text search ---
results = client.search(all_cams, "Golden Gate")

# --- County filter ---
sf_cams = client.filter_by_county(cameras, "San Francisco")

# --- JSON serialization ---
data = [c.to_dict() for c in cameras]
print(json.dumps(data[0], indent=2))

# --- CMS signs ---
signs = client.get_cms_signs(7)
for sign in signs:
    if sign.message_text:
        print(f"{sign.location_name}: {sign.message_text}")

# --- Chain controls ---
cc = client.get_chain_controls(3)  # D3 = Sierra Nevada passes
active = [c for c in cc if c.status not in ("", "none", "None")]
print(f"Active chain controls in D3: {len(active)}")
```

---

## CLI Reference

```
python3 caltrans_client.py <command> [options]
```

### Commands

#### `demo`
Run a live end-to-end demonstration fetching real data.

```bash
python3 caltrans_client.py demo
```

#### `summary`
Show camera counts for all 12 districts.

```bash
python3 caltrans_client.py summary
```

#### `list`
List cameras, with optional filters.

```
python3 caltrans_client.py list [--district N] [--route ROUTE]
                                 [--county COUNTY] [--streaming]
                                 [--in-service] [--search QUERY]
                                 [--format {table,json,geojson}]
```

| Option | Description |
|---|---|
| `--district N` | Limit to one district (1–12) |
| `--route ROUTE` | Filter by route string (e.g. `I-5`, `US-101`) |
| `--county COUNTY` | Filter by county name |
| `--streaming` | Only cameras with live video streams |
| `--in-service` | Only cameras currently in service |
| `--search QUERY` | Full-text search |
| `--format` | Output format: `table` (default), `json`, `geojson` |

**Examples:**
```bash
# All streaming cameras in Orange County (D12)
python3 caltrans_client.py list --district 12 --streaming

# I-80 cameras as GeoJSON
python3 caltrans_client.py list --route I-80 --format geojson > i80.geojson

# Search for Carquinez Bridge area cameras
python3 caltrans_client.py list --search "Carquinez"

# All San Diego cameras as JSON
python3 caltrans_client.py list --district 11 --format json > sd_cameras.json
```

#### `show`
Show complete details for one camera.

```
python3 caltrans_client.py show <district> <index> [--resolve-stream]
```

| Option | Description |
|---|---|
| `district` | District number |
| `index` | Camera index number (from `list` command) |
| `--resolve-stream` | Fetch and display the HLS chunklist URL |

```bash
python3 caltrans_client.py show 7 1 --resolve-stream
```

#### `image`
Download a camera image to a file.

```
python3 caltrans_client.py image <district> <index> [--output FILE] [--frame N]
```

| Option | Description |
|---|---|
| `district` | District number |
| `index` | Camera index |
| `--output FILE` | Output filename (default: auto-generated) |
| `--frame N` | Historical frame 1–12 (default: 0 = current) |

```bash
# Get current snapshot
python3 caltrans_client.py image 7 1 --output traffic.jpg

# Get 3rd historical frame (3 updates ago)
python3 caltrans_client.py image 7 1 --frame 3 --output historical.jpg
```

---

## Caltrans Districts

| District | Number | Major Areas |
|---|---|---|
| D01 | 1 | Eureka, Redding, North Coast (Humboldt, Mendocino, Del Norte, Lake) |
| D02 | 2 | Redding, Mt. Shasta, Yreka (Shasta, Siskiyou, Trinity, Lassen) |
| D03 | 3 | Sacramento, Roseville, Auburn (Sacramento, Placer, El Dorado + more) |
| D04 | 4 | San Francisco Bay Area (all 9 Bay Area counties) |
| D05 | 5 | Santa Cruz, Monterey, San Luis Obispo, Santa Barbara |
| D06 | 6 | Fresno, Visalia, Central Valley |
| D07 | 7 | Los Angeles, Ventura |
| D08 | 8 | San Bernardino, Riverside, Inland Empire |
| D09 | 9 | Bishop, Bridgeport, Eastern Sierra (Mono, Inyo, Alpine) |
| D10 | 10 | Stockton, Modesto, San Joaquin Valley |
| D11 | 11 | San Diego, El Centro (San Diego, Imperial) |
| D12 | 12 | Orange County |

---

## Image & Stream CDN Patterns

### Static Images

**Base URL pattern:**
```
https://cwwp2.dot.ca.gov/data/d{district}/cctv/image/{camera_id}/{camera_id}.jpg
```

**Historical images:**
```
https://cwwp2.dot.ca.gov/data/d{district}/cctv/image/{camera_id}/previous/{camera_id}-{1..12}.jpg
```

**Camera ID derivation:** The camera ID in image URLs is the slug from the camera's HTML page URL. For example, camera page `us101northofsr36lookingnorth.htm` has image ID `us101northofsr36lookingnorth`.

**Image properties:**
- Format: JPEG
- Typical size: 20–80 KB
- Resolution: 320×240 to 704×480 depending on camera hardware
- CORS: `Access-Control-Allow-Origin: *`
- No authentication required

### HLS Video Streams

**CDN:** `wzmedia.dot.ca.gov` (independent from `cwwp2.dot.ca.gov`)

**Master playlist pattern:**
```
https://wzmedia.dot.ca.gov/D{N}/{stream_name}.stream/playlist.m3u8
```

**Stream name patterns:**
- D7 most cameras: `CCTV-{number}.stream`
- D1 Eureka: `eureka_{location}_{resolution}.stream`
- The stream name is derived from the camera slug in the HTML page

**Video properties:**
- Container: HLS (HTTP Live Streaming)
- Codec: H.264 (avc1.4d001f)
- Resolution: 1280×720
- Bitrate: ~124 kbps
- CORS: `Access-Control-Allow-Origin: *`

**Playing streams:**
```bash
# ffplay (part of FFmpeg)
ffplay https://wzmedia.dot.ca.gov/D7/CCTV-196.stream/playlist.m3u8

# VLC
vlc https://wzmedia.dot.ca.gov/D7/CCTV-196.stream/playlist.m3u8

# ffmpeg record 30 seconds
ffmpeg -i https://wzmedia.dot.ca.gov/D7/CCTV-196.stream/playlist.m3u8 \
       -t 30 -c copy output.mp4
```

---

## Rate Limits & Fair Use Policy

From `https://cwwp2.dot.ca.gov/closed-circuit-television-cameras.html`:

> **Usage that risks degrading the availability of the CCTV streaming service is prohibited. Bulk streaming (viewing 10 or more streams simultaneously) is permitted only with a written agreement with Caltrans Traffic Operations including the purpose and duration of the streaming.**
>
> Contact: cwwp2@dot.ca.gov

**Observed server behavior:**
- The data JSON files (`cctvStatusD07.json`) have no enforced rate limit and return instantly
- Image endpoints have `Access-Control-Allow-Origin: *` and no rate-limiting headers observed
- No `Retry-After` or `X-RateLimit-*` headers detected
- The server is nginx/1.20.1

**Practical guidelines:**
- Poll district JSON files no more than once per minute (they update infrequently)
- Images update every 2–60 minutes depending on camera; respect `currentImageUpdateFrequency`
- Do not open more than 9 simultaneous HLS streams without a written agreement
- See [Caltrans Conditions of Use](https://dot.ca.gov/conditions-of-use) for full legal terms

---

## Known Limitations

1. **No bulk search API** — There is no statewide search endpoint. The client must fetch each district's JSON separately to build a complete index.

2. **Stream name not in JSON** — The HLS stream URL is stored in the per-camera HTML page but also in the district JSON under `imageData.streamingVideoURL`. The JSON source is the authoritative and convenient one.

3. **Weather data requires JS parsing** — Per-camera weather forecasts are served as JavaScript variable assignments, not JSON. Not currently parsed by this client.

4. **RWIS coverage is limited** — Only 5 districts (2, 3, 6, 8, 10) currently publish RWIS (weather station) data.

5. **County field inconsistency** — Some cameras report the wrong county (this is a data quality issue in the source). Latitude/longitude coordinates are reliable.

6. **HLS token rotation** — The chunklist URL (`chunklist_w{token}.m3u8`) uses a rotating session token. Always re-fetch the master playlist rather than caching the chunklist URL.

7. **Image CDN path matches camera slug** — If a camera's location page URL is `https://cwwp2.dot.ca.gov/vm/loc/d7/i110196avenue26offramp.htm`, the image path slug is `i110196avenue26offramp`. The JSON provides the full URL so this mapping is transparent.

---

## Data Update Frequency Summary

| Data Type | Update Frequency |
|---|---|
| District JSON metadata | "As necessary" (can be weeks between updates) |
| Camera images (urban/freeway) | Every 2 minutes |
| Camera images (rural) | Every 10–60 minutes |
| HLS streams | Live / continuous |
| CMS sign messages | Near-real-time |
| Chain controls | Near-real-time |
| Weather forecasts (JS files) | Every 30–60 minutes |

---

## License / Data Terms

Data is provided by the California Department of Transportation (Caltrans) under the [Caltrans Conditions of Use](https://dot.ca.gov/conditions-of-use). There is no charge for data access. Attribution to Caltrans CWWP2 is appreciated.

This client is an independent open-source project and is not affiliated with or endorsed by Caltrans.
