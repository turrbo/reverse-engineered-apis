# TDOT SmartWay Traffic Client

> Python client for the Tennessee Department of Transportation (TDOT) SmartWay
> public API — live cameras, incidents, construction, message signs, rest areas,
> and weather events. No API key registration required.

---

## Why This Exists

TDOT operates the SmartWay traffic management system at
[smartway.tn.gov](https://smartway.tn.gov). The site is an Angular SPA that
loads its data from a RESTful JSON API. This client exposes all discovered
endpoints as a clean, typed Python interface so you can build dashboards,
alerting systems, or data pipelines without parsing HTML or running a browser.

**Zero external dependencies** — uses only `urllib`, `json`, and `dataclasses`
from the Python standard library.

---

## Quick Start

```python
from tdot_client import TDOTClient

client = TDOTClient()

# List all 666 active traffic cameras
cameras = client.get_cameras()
print(f"{len(cameras)} cameras")
print(cameras[0].title, cameras[0].hls_url)

# Filter by city and route
nash_i40 = client.get_cameras(route="I-40", jurisdiction="Nashville")
print(f"{len(nash_i40)} Nashville I-40 cameras")

# Live incidents
for incident in client.get_incidents():
    print(incident.description[:80])

# Message signs showing active messages
for sign in client.get_message_signs(active_only=True):
    print(sign.title, ":", sign.message_lines)
```

---

## Installation

No installation required. Copy `tdot_client.py` into your project.

**Requirements:** Python 3.8 or higher (uses `from __future__ import annotations`).

```bash
# Verify it works immediately
python3 tdot_client.py demo
```

---

## API Overview

### Reverse-Engineering Summary

The SmartWay website was reverse-engineered from these artifacts:

| Artifact | URL |
|---|---|
| App shell | `https://smartway.tn.gov` |
| Main JS bundle | `https://smartway.tn.gov/main-3OH5V55Z.js` |
| HTTP interceptor | `https://smartway.tn.gov/chunk-XAW7WIPC.js` |
| Data service | `https://smartway.tn.gov/chunk-XAW7WIPC.js` |
| **Config file** | `https://smartway.tn.gov/assets/config/config.prod.json` |

The config file contains the API base URL, API key, and all endpoint names in
plain text — no obfuscation or dynamic key generation is used.

### Authentication

All TDOT SmartWay API endpoints use a **static API key** passed in the
`ApiKey` HTTP request header:

```
ApiKey: 8d3b7a82635d476795c09b2c41facc60
```

This key is embedded in the public web application config file and requires no
registration or authentication to obtain. It appears to have no rate limiting
enforced at the current time.

### Base URL

```
https://www.tdot.tn.gov/opendata/api/public/
```

---

## Discovered Endpoints

### Core API Endpoints

All endpoints use `GET` and return `application/json`. The `ApiKey` header is
required on all requests.

| Endpoint | Returns | Typical Count |
|---|---|---|
| `GET /RoadwayCameras` | All traffic cameras | 666 |
| `GET /RoadwayCameras/{id}` | Single camera by ID | 1 |
| `GET /RoadwayIncidents` | Active traffic incidents | 5–30 |
| `GET /RoadwayOperations` | Construction / operations | 50–100 |
| `GET /RoadwaySevereImpact` | High-priority closures | 0–10 |
| `GET /RoadwayWeather` | Weather-related events | 0–20 |
| `GET /RoadwaySpecialEvents` | Special event impacts | 0–10 (may 204) |
| `GET /RoadwayMessageSigns` | Dynamic message signs | 243 |
| `GET /RestAreas` | Rest areas / welcome centers | 35 |
| `GET /SmartWayBanner` | Statewide alert message | 1 |

### ArcGIS REST Services (No Auth Required)

| Service | Description |
|---|---|
| `spatial.tdot.tn.gov/ArcGIS/.../Waze_Smartway/MapServer/0/query` | Waze crowd-sourced incident overlay |
| `services2.arcgis.com/.../Administrative_Boundaries_Prod_Data/FeatureServer/7/query` | Tennessee county polygons (95 counties) |

### Google Maps

The SmartWay web app uses a Google Maps API key embedded in `scripts-XDATTEQE.js`:

```
AIzaSyDQzQD27wKmM8DNPAmZ0qXf8XCrJA0qB4s
```

---

## Response Formats

### Camera Object

```json
{
  "id": 3165,
  "title": "I-40/75 @ West Hills",
  "description": "I-40/75 @ West Hills",
  "thumbnailUrl": "https://tnsnapshots.com/thumbs/R1_010.flv.png",
  "httpVideoUrl": "https://mcleansfs1.us-east-1.skyvdn.com:443/rtplive/R1_010/playlist.m3u8",
  "httpsVideoUrl": "https://mcleansfs1.us-east-1.skyvdn.com:443/rtplive/R1_010/playlist.m3u8",
  "rtmpVideoUrl": "rtmp://mcleansfs1.us-east-1.skyvdn.com:1935/rtplive/R1_010",
  "rtspVideoUrl": "rtsp://mcleansfs1.us-east-1.skyvdn.com:554/rtplive/R1_010",
  "clspUrl": null,
  "clspsUrl": "clsps://mcleansfs1.us-east-1.skyvdn.com:443/R1_010",
  "active": "true",
  "jurisdiction": "Knoxville",
  "route": "I-40",
  "mileMarker": "380.8",
  "lat": 35.928889,
  "lng": -84.039167,
  "location": {
    "type": "point",
    "coordinates": [{"lat": 35.928889, "lng": -84.039167}]
  }
}
```

**Camera fields:**

| Field | Type | Notes |
|---|---|---|
| `id` | int | Use with `/RoadwayCameras/{id}` |
| `title` | string | Human-readable name |
| `thumbnailUrl` | string | Static PNG snapshot, ~120 KB |
| `httpsVideoUrl` | string | HLS `.m3u8` playlist URL |
| `rtmpVideoUrl` | string | RTMP stream URL |
| `rtspVideoUrl` | string | RTSP stream URL |
| `clspsUrl` | string/null | Secure CLSP (low-latency) URL |
| `active` | string | `"true"` or `"false"` |
| `jurisdiction` | string | `"Knoxville"` \| `"Nashville"` \| `"Memphis"` \| `"Chattanooga"` |
| `route` | string | `"I-40"`, `"I-24"`, `"Briley Pkwy"`, etc. |
| `mileMarker` | string | String milepost value |

**Jurisdictions:** 266 Nashville, 140 Memphis, 131 Chattanooga, 129 Knoxville

### Stream / CDN Patterns

Thumbnail CDN (static snapshots, ~120 KB PNG, live-updated):
```
https://tnsnapshots.com/thumbs/{stream_id}.flv.png
```

HLS (HTTP Live Streaming, works in browsers with hls.js / video.js):
```
https://mcleansfs{1-5}.us-east-1.skyvdn.com:443/rtplive/{stream_id}/playlist.m3u8
```

RTMP (legacy, for OBS / FFmpeg ingestion):
```
rtmp://mcleansfs{1-5}.us-east-1.skyvdn.com:1935/rtplive/{stream_id}
```

RTSP (for VLC, ONVIF clients):
```
rtsp://mcleansfs{1-5}.us-east-1.skyvdn.com:554/rtplive/{stream_id}
```

CLSP (low-latency, for SmartWay web player):
```
clsps://mcleansfs{1-5}.us-east-1.skyvdn.com:443/{stream_id}
```

The CDN uses **5 origin servers** (mcleansfs1–5), operated by SkyVDN
(`skyvdn.com`). The stream ID prefix encodes jurisdiction:
- `R1_` — Knoxville region
- `R2_` — Chattanooga region
- `R3_` — Nashville region
- `R4_` — Memphis region

Stream IDs in the playlist (returned by HLS master playlist):
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=213850,CODECS="avc1.42c00c",RESOLUTION=320x240
chunklist_w585423897.m3u8
```

### Roadway Event Object

Used by Incidents, Construction, Weather, Severe Impact, and Special Events:

```json
{
  "id": 2226930,
  "status": "Confirmed",
  "eventTypeId": 3,
  "eventTypeName": "Incident",
  "eventSubTypeId": 0,
  "eventSubTypeDescription": "Congestion",
  "description": "Interstate 75 SB in Hamilton County - near MILE MARKER 0.2 Congestion reported at 03/27/2026 4:06 PM (ET). SB no lanes blocked.",
  "currentActivity": null,
  "locations": [
    {
      "type": "Point",
      "midPoint": {"lat": 34.988661, "lng": -85.203023},
      "coordinates": [{"lat": 34.988661, "lng": -85.203023}],
      "routeLine": [[{"lat": 34.988661, "lng": -85.203023}]],
      "oppositeImpactRouteLine": [],
      "region": 2,
      "countyId": 33,
      "countyName": "Hamilton"
    }
  ],
  "beginningDate": "2026-03-27T15:06:47.6326282-05:00",
  "endingDate": null,
  "revisedDate": "2026-03-27T15:15:08.6135604-05:00",
  "hasClosure": false,
  "impactDescription": "Southbound no lanes blocked",
  "oppositeImpactDescription": "",
  "directionDescription": "Southbound",
  "diversionDescription": "",
  "dayOfWeek": null,
  "mileMarker": "0.2",
  "isSevere": false,
  "wideArea": false,
  "memberOfWideArea": false,
  "thpReported": false,
  "primaryEventId": null,
  "parentId": null
}
```

**Event type IDs observed:**

| `eventTypeId` | `eventTypeName` |
|---|---|
| 3 | Incident |
| 6 | Operations (construction) |
| 9 | Weather |

### Message Sign Object

```json
{
  "id": "1110",
  "title": "(04)I-40W before Cherry St",
  "message": "HEAVY CONGESTION|AT MM 387|EXPECT DELAYS",
  "region": 1,
  "route": "Interstate 40",
  "location": {
    "type": "point",
    "coordinates": [{"lat": 35.997834, "lng": -83.892521}]
  },
  "graphic": null
}
```

The `message` field uses `|` as a line separator. An empty string means the
sign is currently blank. Use `MessageSign.message_lines` to get a list.

243 signs are returned; typically 50–100 have active messages at any given time.

### Rest Area Object

```json
{
  "id": 27,
  "displayName": "Rest Area on I-24 EB at MM 160",
  "isOpen": true,
  "county": null,
  "region": 2,
  "route": "Interstate 24",
  "type": "Rest Stop",
  "mile": 160,
  "lat": 35.024057,
  "lng": -85.558988,
  "begLogMile": 0,
  "sectionId": null,
  "events": [],
  "plannedClosure": null
}
```

`type` is either `"Rest Stop"` or `"Welcome Center"`.

### Banner Object

```json
[{"message": ""}]
```

Returns a 1-item list. An empty `message` string means no active alert.

---

## Python Client Reference

### `TDOTClient(api_base_url, api_key, timeout)`

```python
client = TDOTClient(
    api_base_url="https://www.tdot.tn.gov/opendata/api/public/",
    api_key="8d3b7a82635d476795c09b2c41facc60",
    timeout=20,
)
```

### Methods

#### `get_cameras(route, jurisdiction, active_only) -> list[Camera]`

Return all traffic cameras.

```python
# All active cameras (default)
all_cameras = client.get_cameras()

# Nashville I-40 only
nash_i40 = client.get_cameras(route="I-40", jurisdiction="Nashville")

# Including inactive
all_including_inactive = client.get_cameras(active_only=False)
```

#### `get_camera(camera_id) -> Camera | None`

Fetch a single camera by numeric ID.

```python
cam = client.get_camera(3165)
print(cam.hls_url)  # HLS playlist URL
print(cam.stream_id)  # "R1_010"
```

#### `get_thumbnail(camera) -> bytes | None`

Download the current PNG snapshot image.

```python
cam = client.get_camera(3165)
png_bytes = client.get_thumbnail(cam)
with open("snapshot.png", "wb") as f:
    f.write(png_bytes)
```

#### `get_incidents() -> list[RoadwayEvent]`

Active traffic incidents (crashes, congestion, lane blockages).

```python
for inc in client.get_incidents():
    if inc.has_closure:
        print("[CLOSURE]", inc.description)
```

#### `get_construction() -> list[RoadwayEvent]`

Active construction and roadway operations projects.

```python
for op in client.get_construction():
    print(op.event_subtype_desc, "—", op.description[:80])
```

#### `get_severe_impacts() -> list[RoadwayEvent]`

High-priority events: bridge closures, major crashes.

```python
for ev in client.get_severe_impacts():
    print("[SEVERE]", ev.description)
```

#### `get_weather_events() -> list[RoadwayEvent]`

Active weather-related roadway events. May return empty list when clear.

#### `get_special_events() -> list[RoadwayEvent]`

Active special events (concerts, sporting events). May return empty list.

#### `get_message_signs(active_only) -> list[MessageSign]`

All 243 DMS signs and their current messages.

```python
# Only signs with active messages
for sign in client.get_message_signs(active_only=True):
    print(sign.title)
    print("  Lines:", sign.message_lines)
```

#### `get_rest_areas(open_only) -> list[RestArea]`

All 35 Tennessee highway rest areas and welcome centers.

```python
for ra in client.get_rest_areas(open_only=True):
    print(ra.display_name, "—", ra.route)
```

#### `get_banner() -> BannerMessage | None`

System-wide alert message.

```python
banner = client.get_banner()
if banner and banner.is_active:
    print("ALERT:", banner.message)
```

#### `get_all_events() -> dict[str, list[RoadwayEvent]]`

Fetch all event types in a single call.

```python
events = client.get_all_events()
# Keys: "incidents", "construction", "severe", "weather", "special"
total = sum(len(v) for v in events.values())
print(f"{total} total active events")
```

#### `search_cameras(query) -> list[Camera]`

Case-insensitive substring search across camera title, route, and jurisdiction.

```python
cams = client.search_cameras("downtown")
```

#### `get_waze_alerts() -> list[dict]`

Waze crowd-sourced incident data from ArcGIS.

```python
for alert in client.get_waze_alerts():
    attrs = alert.get("attributes", {})
    print(attrs.get("type"), attrs.get("subtype"), attrs.get("city"))
```

#### `get_county_polygons(county_name, geometry_precision) -> dict`

Tennessee county boundary polygons from ArcGIS.

```python
# All 95 counties
all_counties = client.get_county_polygons()

# Single county
davidson = client.get_county_polygons(county_name="Davidson")
```

---

## Data Classes

### `Camera`

| Attribute | Type | Description |
|---|---|---|
| `id` | `int` | Numeric camera ID |
| `title` | `str` | Human-readable name |
| `description` | `str` | Usually same as title |
| `thumbnail_url` | `str \| None` | Static PNG snapshot URL |
| `hls_url` | `str \| None` | HLS `.m3u8` stream URL |
| `http_video_url` | `str \| None` | HTTP variant of HLS URL |
| `rtmp_url` | `str \| None` | RTMP stream URL |
| `rtsp_url` | `str \| None` | RTSP stream URL |
| `clsp_url` | `str \| None` | CLSP URL (usually null) |
| `clsps_url` | `str \| None` | Secure CLSP URL |
| `active` | `str` | `"true"` or `"false"` |
| `jurisdiction` | `str \| None` | City name |
| `route` | `str \| None` | Route identifier |
| `mile_marker` | `str \| None` | Milepost as string |
| `lat` | `float` | Latitude WGS84 |
| `lng` | `float` | Longitude WGS84 |
| `location` | `Location \| None` | Full location geometry |
| `is_active` | `bool` (property) | Parsed from `active` field |
| `stream_id` | `str \| None` (property) | e.g. `"R1_010"` |

### `RoadwayEvent`

| Attribute | Type | Description |
|---|---|---|
| `id` | `int` | Event ID |
| `status` | `str` | `"Confirmed"` or `"Unconfirmed"` |
| `event_type_id` | `int` | Type code (3=Incident, 6=Operations, 9=Weather) |
| `event_type_name` | `str` | Human-readable type |
| `event_subtype_desc` | `str` | Subtype e.g. `"Crash"`, `"Bridge Work"` |
| `description` | `str` | Full narrative |
| `current_activity` | `str \| None` | Operator notes |
| `locations` | `list[Location]` | Geometry |
| `beginning_date` | `str \| None` | ISO-8601 start datetime |
| `ending_date` | `str \| None` | ISO-8601 end datetime; None if ongoing |
| `revised_date` | `str \| None` | ISO-8601 last update |
| `has_closure` | `bool` | True if lanes are closed |
| `impact_description` | `str` | Primary direction impact |
| `direction_description` | `str` | e.g. `"Northbound"` |
| `diversion_description` | `str` | Detour text |
| `is_severe` | `bool` | Severe impact flag |
| `thp_reported` | `bool` | THP-reported flag |
| `primary_location` | `Location \| None` (property) | First location |

### `MessageSign`

| Attribute | Type | Description |
|---|---|---|
| `id` | `str` | Sign ID (numeric string) |
| `title` | `str` | Location description |
| `message` | `str` | Raw pipe-delimited message |
| `region` | `int` | TDOT region 1–4 |
| `route` | `str` | Full route name |
| `location` | `Location \| None` | Sign location |
| `message_lines` | `list[str]` (property) | Split on `\|` |
| `is_blank` | `bool` (property) | True when no message |

### `RestArea`

| Attribute | Type | Description |
|---|---|---|
| `id` | `int` | Facility ID |
| `display_name` | `str` | Human-readable name |
| `is_open` | `bool` | Open/closed status |
| `county` | `str \| None` | County name |
| `region` | `int` | TDOT region 1–4 |
| `route` | `str` | Route name |
| `type_` | `str` | `"Rest Stop"` or `"Welcome Center"` |
| `mile` | `float` | Milepost |
| `lat` | `float` | Latitude |
| `lng` | `float` | Longitude |
| `events` | `list[dict]` | Current events at facility |
| `planned_closure` | `dict \| None` | Planned closure info |

### `Location`

| Attribute | Type | Description |
|---|---|---|
| `type_` | `str` | `"Point"` or `"point"` |
| `coordinates` | `list[Coordinate]` | Coordinate list |
| `mid_point` | `Coordinate \| None` | Pre-computed midpoint |
| `route_line` | `list[list[Coordinate]]` | Polyline segments |
| `region` | `int \| None` | TDOT region |
| `county_id` | `int \| None` | County ID |
| `county_name` | `str \| None` | County name |
| `point` | `Coordinate \| None` (property) | First coordinate or mid_point |

---

## CLI Reference

```bash
# Run a full live demo of all endpoints
python3 tdot_client.py demo

# List all active cameras
python3 tdot_client.py cameras

# Filter cameras
python3 tdot_client.py cameras --route I-40
python3 tdot_client.py cameras --jurisdiction Nashville
python3 tdot_client.py cameras --route I-40 --jurisdiction Nashville --verbose

# Single camera detail
python3 tdot_client.py camera 3165

# Search cameras
python3 tdot_client.py search "Briley Pkwy"

# Events
python3 tdot_client.py incidents
python3 tdot_client.py construction
python3 tdot_client.py severe
python3 tdot_client.py weather

# Message signs
python3 tdot_client.py signs            # all 243 signs
python3 tdot_client.py signs --active   # only signs with active messages

# Rest areas
python3 tdot_client.py restareas

# System banner
python3 tdot_client.py banner
```

---

## Examples

### Download a snapshot image

```python
from tdot_client import TDOTClient

client = TDOTClient()
cam = client.get_camera(3165)
print(f"Downloading snapshot for: {cam.title}")

png_bytes = client.get_thumbnail(cam)
if png_bytes:
    with open(f"camera_{cam.id}.png", "wb") as f:
        f.write(png_bytes)
    print(f"Saved {len(png_bytes):,} bytes")
```

### Play a live stream with FFmpeg

```bash
# HLS stream (requires ffmpeg or vlc)
ffplay "https://mcleansfs1.us-east-1.skyvdn.com:443/rtplive/R1_010/playlist.m3u8"

# RTSP stream
ffplay "rtsp://mcleansfs1.us-east-1.skyvdn.com:554/rtplive/R1_010"
```

### Build a closure alert monitor

```python
import time
from tdot_client import TDOTClient

client = TDOTClient()

seen_closures = set()
print("Monitoring for new road closures (Ctrl-C to stop)...")

while True:
    for ev in client.get_incidents() + client.get_construction() + client.get_severe_impacts():
        if ev.has_closure and ev.id not in seen_closures:
            seen_closures.add(ev.id)
            loc = ev.primary_location
            county = f" ({loc.county_name})" if loc and loc.county_name else ""
            print(f"[NEW CLOSURE]{county} {ev.event_type_name}: {ev.description[:100]}")
    time.sleep(60)
```

### Export cameras to GeoJSON

```python
import json
from tdot_client import TDOTClient

client = TDOTClient()
cameras = client.get_cameras()

geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c.lng, c.lat]},
            "properties": {
                "id": c.id,
                "title": c.title,
                "jurisdiction": c.jurisdiction,
                "route": c.route,
                "mileMarker": c.mile_marker,
                "thumbnailUrl": c.thumbnail_url,
                "hlsUrl": c.hls_url,
                "streamId": c.stream_id,
            },
        }
        for c in cameras
    ],
}

with open("tdot_cameras.geojson", "w") as f:
    json.dump(geojson, f, indent=2)

print(f"Exported {len(cameras)} cameras to tdot_cameras.geojson")
```

### Get all active message sign content

```python
from tdot_client import TDOTClient

client = TDOTClient()
active_signs = client.get_message_signs(active_only=True)

for sign in active_signs:
    print(f"\n{sign.route} — {sign.title}")
    for i, line in enumerate(sign.message_lines, 1):
        print(f"  Line {i}: {line}")
```

### Summarise the current situation

```python
from tdot_client import TDOTClient

client = TDOTClient()

banner = client.get_banner()
if banner and banner.is_active:
    print(f"STATEWIDE ALERT: {banner.message}\n")

events = client.get_all_events()
print("Current Tennessee Roadway Status")
print(f"  Incidents    : {len(events['incidents'])}")
print(f"  Construction : {len(events['construction'])}")
print(f"  Severe       : {len(events['severe'])}")
print(f"  Weather      : {len(events['weather'])}")

closures = [
    ev for evlist in events.values()
    for ev in evlist
    if ev.has_closure
]
print(f"  Total closures: {len(closures)}")

active_signs = client.get_message_signs(active_only=True)
print(f"  Active DMS signs: {len(active_signs)}/243")
```

---

## Infrastructure Notes

### SmartWay Architecture

```
Browser → smartway.tn.gov (Angular SPA)
              ↓ ApiKey header
         tdot.tn.gov/opendata/api/public/ (ASP.NET REST API)
              ↓ camera data
         tnsnapshots.com (thumbnail CDN)
              ↓ video streams
         mcleansfs{1-5}.us-east-1.skyvdn.com (SkyVDN HLS/RTMP/RTSP CDN)
              ↓ ArcGIS services
         spatial.tdot.tn.gov (TDOT ArcGIS Server)
         services2.arcgis.com (Esri ArcGIS Online)
```

### TDOT Regions

| Region | Coverage |
|---|---|
| 1 | East Tennessee (Knoxville area) |
| 2 | Southeast Tennessee (Chattanooga area) |
| 3 | Middle Tennessee (Nashville area) |
| 4 | West Tennessee (Memphis area) |

### Refresh Intervals

The SmartWay Angular app refreshes data in the background at a configurable
interval (approximately 60 seconds). For monitoring applications, polling
every 60 seconds is sufficient. The cameras and DMS signs update more
frequently at the source.

---

## Limitations

- **Waze ArcGIS endpoint** may time out from some network environments.
- **`RoadwaySpecialEvents`** and **`RoadwayCountyWideWeather`** return HTTP 204
  (No Content) when there are no active events. The client returns an empty list.
- The API key is a **static public credential** embedded in the open-source web
  app. It is not secret, but treat it as a courtesy credential — do not make
  abusive volumes of requests.
- No pagination is implemented on any endpoint — all data is returned in a
  single response. Camera data (~509 KB) and construction data (~120 KB) are
  the largest payloads.
- Camera stream IDs use a regional prefix (`R1_`, `R2_`, `R3_`, `R4_`)
  followed by a zero-padded sequence number. The mapping between stream ID
  and CDN node (mcleansfs1–5) is determined by the API response, not a
  derivable pattern.

---

## License

This client is provided for **informational and research purposes**. Traffic
data is operated by the Tennessee Department of Transportation. Please comply
with TDOT's terms of service when using this data. Do not use this client to
disrupt TDOT systems or services.
