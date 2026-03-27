# Nevada 511 / NVRoads Traffic API — Reverse Engineering Notes & Python Client

**Target site:** https://www.nvroads.com
**Operator:** Nevada Department of Transportation (NDOT)
**Platform:** Nevada 511 (ASP.NET MVC + jQuery DataTables + Google Maps)
**Reverse engineered:** 2026-03-27

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Authentication](#authentication)
4. [Discovered Endpoints](#discovered-endpoints)
   - [List Data API (primary)](#list-data-api)
   - [Camera Image / Snapshot](#camera-image--snapshot)
   - [Camera Video URL Resolver](#camera-video-url-resolver)
   - [Tooltip Fragments](#tooltip-fragments)
   - [Agency Logo](#agency-logo)
   - [KML Feed](#kml-feed)
   - [Route Planner (authenticated)](#route-planner-authenticated)
5. [Data Types](#data-types)
6. [Request / Response Formats](#request--response-formats)
7. [CDN & Streaming Infrastructure](#cdn--streaming-infrastructure)
8. [Map Initialization Options](#map-initialization-options)
9. [JavaScript Bundle Analysis](#javascript-bundle-analysis)
10. [Python Client Usage](#python-client-usage)
11. [CLI Reference](#cli-reference)
12. [Live Record Counts](#live-record-counts)
13. [I-15 / I-80 Corridor Cameras](#i-15--i-80-corridor-cameras)
14. [Known Limitations](#known-limitations)

---

## Overview

NVRoads (Nevada 511) is the official NDOT traveler information system.  It
exposes real-time data for 643 traffic cameras, 382 dynamic message signs,
126 RWIS weather stations, 434 road condition segments, and live traffic
events across Nevada.

All data is loaded via a DataTables server-side processing API that requires
no authentication.  Camera snapshots are served as JPEG files through AWS
CloudFront.  Live video streams use HLS (`application/x-mpegURL`) served from
NDOT's own ITS streaming infrastructure (`*.its.nv.gov`).

---

## Architecture

```
Browser  <──────────────>  CloudFront CDN  <──>  ASP.NET MVC backend
                            (nvroads.com)          (x-powered-by: ASP.NET)

  GET /List/GetData/{type}?query=JSON&lang=en
  ← JSON (DataTables wire format)

  GET /map/Cctv/{id}
  ← JPEG image (max-age: 60s, via CloudFront)

  GET /Camera/GetVideoUrl?imageId={id}
  ← JSON string: HLS playlist URL

  HLS player  <─────────>  d{n}wse{n}.its.nv.gov:443
                            (NDOT streaming servers)
```

The frontend is a jQuery + Google Maps application.  Map data layers are
loaded through the same `/List/GetData/` endpoint that drives the list pages.
The `data-typeidfriendlyurl` HTML attribute on each `<table>` element tells
the DataTables library which type ID to request.

---

## Authentication

**No authentication is required** for any of the endpoints documented below.

- No API key, OAuth token, or cookie session is needed.
- A standard `User-Agent` header is sufficient.
- The site sets session cookies (`session-id`, `_culture`,
  `__RequestVerificationToken`) but none of them are validated for read-only
  data requests.

> The `__RequestVerificationToken` cookie / header is only required for
> authenticated write operations (save route, manage camera lists, login).

---

## Discovered Endpoints

### List Data API

The primary data endpoint, backed by DataTables server-side processing.

```
GET  https://www.nvroads.com/List/GetData/{type}
     ?query={DataTablesQuery}
     &lang=en
```

| Parameter | Type   | Description |
|-----------|--------|-------------|
| `query`   | string | URL-encoded JSON — DataTables request object (see below) |
| `lang`    | string | Language code, always `en` on nvroads.com |

**Response:** DataTables wire format:

```json
{
  "draw": 1,
  "recordsTotal": 643,
  "recordsFiltered": 643,
  "data": [ ... ]
}
```

**Supported `{type}` values:**

| Type ID             | Description                             | Count |
|---------------------|-----------------------------------------|-------|
| `Cameras`           | Traffic camera sites                    | 643   |
| `traffic`           | All active events (umbrella)            | ~83   |
| `construction`      | Road-work / maintenance events          | ~56   |
| `Closures`          | Full/partial road closures              | ~6    |
| `Incidents`         | Accidents, hazards                      | ~4    |
| `OversizedLoads`    | Oversized/overweight load permits       | ~2    |
| `FutureRoadwork`    | Planned future construction             | ~13   |
| `SpecialEvents`     | Special events affecting traffic        | ~3    |
| `WeatherStations`   | RWIS weather station readings           | 126   |
| `RoadConditions`    | Road surface condition segments         | 434   |
| `MessageSigns`      | Dynamic message sign (DMS) content      | 382   |
| `RestAreas`         | Highway rest area facilities            | 35    |
| `TruckParking`      | Commercial truck parking locations      | 56    |
| `VisitorLocations`  | Visitor/tourist information centres     | 3     |

> **Note:** `WeatherEvents`, `ChainControls`, `TrafficSpeeds`, `Snowplow`
> return HTTP 500 when called via the list API — these layers are loaded
> differently by the map page (likely via a separate internal endpoint not
> exposed to the public frontend).

---

### Camera Image / Snapshot

```
GET  https://www.nvroads.com/map/Cctv/{camera_id}
```

Returns a JPEG image of the current camera frame.

- **Response:** `image/jpeg`
- **Cache:** CloudFront `max-age=60` (1-minute refresh)
- **Infrastructure:** AWS CloudFront → AWS Lambda (NDOT backend)
- **CORS:** `access-control-allow-origin: *`
- **Authentication:** None

**Example:**
```
https://www.nvroads.com/map/Cctv/4746
```

The `camera_id` is the numeric `id` field from the `Cameras` list data.

---

### Camera Video URL Resolver

```
GET  https://www.nvroads.com/Camera/GetVideoUrl?imageId={image_id}
```

Resolves the HLS stream URL for a given camera view.

- **Response:** JSON-encoded string or JSON object
- **Authentication:** None

**Example response** (plain string, most common):
```json
"https://d1wse4.its.nv.gov:443/vegasxcd04/163a00ed-fbd5-44f0-8b0f-2f79495de6e4_lvflirxcd04_public.stream/playlist.m3u8"
```

The `image_id` maps to `CameraImage.id` (same value as the camera site `id`
for single-view cameras; differs for multi-view sites).

> The HLS URL is also directly available in the `images[].videoUrl` field
> returned by `/List/GetData/Cameras`, so this endpoint is only needed when
> you have an image ID but not the full camera record.

---

### Tooltip Fragments

```
GET  https://www.nvroads.com/tooltip/{layer_type}/{item_id}?lang=en&noCss=true
```

Returns an HTML fragment used as the map tooltip / info-window for any item.

| Parameter    | Description |
|--------------|-------------|
| `layer_type` | Same as the List Data type ID: `Cameras`, `Construction`, `WeatherStations`, `MessageSigns`, etc. |
| `item_id`    | Numeric item ID |
| `lang`       | Language code (`en`) |
| `noCss`      | Set to `true` to omit inline CSS (returns leaner HTML) |

**Example:**
```
https://www.nvroads.com/tooltip/Cameras/4746?lang=en&noCss=true
```

Returns a Bootstrap-styled `<div class="map-tooltip camTooltip">` with the
camera image carousel, video button, and metadata table.

---

### Agency Logo

```
GET  https://www.nvroads.com/NoSession/GetCctvAgencyImage?agencyId={id}
```

Returns a PNG agency logo for cameras sourced from third-party agencies.
Only relevant for cameras where `agencyLogoEnabled` is `true`.

---

### KML Feed

```
GET  https://www.nvroads.com/NoSession/GetKml?name=Nearby511
```

Returns a KML document of nearby Nevada 511 POI.  The response body may be
empty if no KML data is configured (as observed in testing).

---

### Route Planner (authenticated)

These endpoints require a logged-in session (`__RequestVerificationToken`
header) and are **not** covered by this client:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/route/getroutes` | GET | Retrieve saved routes |
| `/api/route/getlocations` | GET | Geocode map click location |
| `/Api/Route/GetRouteByShareID` | GET | Resolve shared route link |
| `/Api/Route/GetUserRouteStatistics` | GET | Route statistics |
| `/Api/Route/SaveUserRoute` | POST | Save a route |
| `/My511/SaveQuickRouteAlert` | POST | Create route notification |
| `/My511/Login` | POST | Log in |

---

## Data Types

### Cameras response fields

```json
{
  "DT_RowId": "4746",
  "id": 4746,
  "roadway": "Silverado Ranch Blvd & I-15 SB Ramp",
  "direction": "Unknown",
  "location": "Silverado Ranch Blvd & I-15 SB Ramp",
  "region": "Las Vegas",
  "state": "Nevada",
  "latLng": {
    "geography": {
      "coordinateSystemId": 4326,
      "wellKnownText": "POINT (-115.18118 36.01316)"
    }
  },
  "images": [
    {
      "id": 4746,
      "cameraSiteId": 4746,
      "sortOrder": 0,
      "description": "Silverado Ranch Blvd & I-15 SB Ramp",
      "imageUrl": "/map/Cctv/4746",
      "imageType": 0,
      "videoUrl": "https://d1wse4.its.nv.gov:443/vegasxcd04/163a00ed-fbd5-44f0-8b0f-2f79495de6e4_lvflirxcd04_public.stream/playlist.m3u8",
      "videoType": "application/x-mpegURL",
      "isVideoAuthRequired": false,
      "videoDisabled": false,
      "disabled": false,
      "blocked": false
    }
  ],
  "source": "Cameleon",
  "sourceId": "8881",
  "type": null,
  "areaId": "LV",
  "visible": true,
  "created": "2026-01-06T17:30:16.6050043+00:00",
  "lastUpdated": null,
  "tooltipUrl": "/tooltip/Cameras/4746?lang=%7Blang%7D&noCss=true"
}
```

### Traffic event response fields

```json
{
  "DT_RowId": "75",
  "id": 75,
  "type": "Construction",
  "layerName": "Construction",
  "roadwayName": "I-80",
  "description": "Minor Emergency maintenance on I-80 Westbound...",
  "source": "ERS",
  "sourceId": "12277",
  "eventSubType": "emergencyMaintenance",
  "startDate": "9/18/24, 3:22 PM",
  "endDate": null,
  "lastUpdated": "9/18/24, 3:23 PM",
  "isFullClosure": false,
  "severity": "Minor",
  "direction": "West",
  "locationDescription": "Wadsworth Rest Area",
  "detourDescription": null,
  "laneDescription": "All Ramps Closed",
  "recurrenceDescription": "<b>Mon, Tue, Wed, Thu, Fri, Sat, Sun:</b><br/>Active all day",
  "widthRestriction": null,
  "heightRestriction": null,
  "lengthRestriction": null,
  "weightRestriction": null,
  "region": "Reno",
  "state": "Nevada",
  "showOnMap": true
}
```

### Road conditions response fields

```json
{
  "DT_RowId": 19725,
  "id": 19725,
  "area": "Reno",
  "roadway": "SR-659 (McCarran Blvd)",
  "description": "From Summit Ridge Dr to Greg St",
  "primaryCondition": "No Report",
  "secondaryConditions": [],
  "stale": false,
  "lastUpdated": "12/12/22, 10:45 AM"
}
```

**Primary condition values observed:** `Dry`, `Wet`, `Snowy`, `Icy`,
`No Report`, `Closed`

### Weather station (RWIS) response fields

```json
{
  "DT_RowId": "78837",
  "name": "US-50 Cave Rock Trailer South",
  "organization": "NV-ATMS-RWIS",
  "airTemperature": "53.5 °F",
  "surfaceTemperature": "58.6",
  "windSpeedAverage": "6.8",
  "windSpeedGust": "18.3",
  "windDirectionAverage": "NE",
  "relativeHumidity": "55 %",
  "dewPoint": "53.2 °F",
  "precipitation": "SnowSlight",
  "precipitationRate": "44.212",
  "pavementCondition": "Dry",
  "visibility": "0.3",
  "atmosphericPressure": "29.32",
  "rain": "SnowSlight",
  "wind": "NE@6.8 mph",
  "windGust": "18.3 mph",
  "status": "Ok",
  "region": "Reno",
  "state": "Nevada",
  "county": "Mineral",
  "lastUpdated": "3/27/26, 1:43 PM"
}
```

### Message sign (DMS) response fields

```json
{
  "DT_RowId": "15842",
  "name": "I-15 SB @ N OF BONAZA RD - C",
  "roadwayName": "I-15",
  "direction": "Both Directions",
  "area": "Las Vegas",
  "description": "I-15 SB @ N OF BONAZA RD - C",
  "message": "TRAVEL SAFELY",
  "message2": "",
  "message3": "",
  "phase1Image": null,
  "phase2Image": null,
  "status": "on",
  "lastUpdated": "3/27/26, 1:53 PM"
}
```

---

## Request / Response Formats

### DataTables Query Object

The `query` parameter is a JSON object:

```json
{
  "columns": [
    {
      "name": "sortOrder",
      "searchable": false,
      "search": {"value": "", "regex": false}
    },
    {
      "name": "roadway",
      "searchable": true,
      "search": {"value": "I-15", "regex": false}
    }
  ],
  "order": [
    {"column": 0, "dir": "asc"}
  ],
  "start": 0,
  "length": 25,
  "search": {
    "value": "",
    "regex": false
  }
}
```

**Key notes:**
- `columns` may be an empty array `[]` — the server returns all fields
- The server enforces a max `length` of 100
- `search.value` is a global free-text filter across searchable columns
- Per-column filtering uses `columns[n].search.value`
- `start` / `length` implement pagination (DataTables convention)
- Column index in `order[n].column` is relative to the `columns` array

### Minimal valid query (returns all fields):

```
GET /List/GetData/Cameras?query={"columns":[],"order":[{"column":0,"dir":"asc"}],"start":0,"length":100}&lang=en
```

> URL-encode the JSON in production: use `urllib.parse.urlencode` or equivalent.

---

## CDN & Streaming Infrastructure

### Camera Snapshots

Snapshots are served via **AWS CloudFront** fronting an AWS Lambda function
that proxies to the NDOT backend.

```
GET  https://www.nvroads.com/map/Cctv/{id}
     X-Cache: Hit from cloudfront  (or Miss)
     Cache-Control: max-age=60
     Access-Control-Allow-Origin: *
```

### HLS Video Streams

Live video streams use NDOT's own ITS streaming servers, all on port 443:

| Hostname Pattern | Region |
|------------------|--------|
| `d1wse1.its.nv.gov:443` | Las Vegas (cluster 1, server 1) |
| `d1wse2.its.nv.gov:443` | Las Vegas (cluster 1, server 2) |
| `d1wse3.its.nv.gov:443` | Las Vegas (cluster 1, server 3) |
| `d1wse4.its.nv.gov:443` | Las Vegas (cluster 1, server 4) |
| `d2wse1.its.nv.gov:443` | Reno/Washoe (cluster 2, server 1) |
| `d2wse2.its.nv.gov:443` | Reno/Washoe (cluster 2, server 2) |
| `d3wse1.its.nv.gov:443` | Elko/Eastern NV (cluster 3, server 1) |

**URL structure:**
```
https://{cdn_host}/{stream_key}/{uuid}_{stream_name}_public.stream/playlist.m3u8
```

**Example:**
```
https://d1wse4.its.nv.gov:443/vegasxcd04/163a00ed-fbd5-44f0-8b0f-2f79495de6e4_lvflirxcd04_public.stream/playlist.m3u8
```

- `vegasxcd04` — Las Vegas encoder/XCD unit 4
- UUID uniquely identifies the video stream source
- `lvflirxcd04` — Las Vegas FLIR thermal camera unit 4
- `_public.stream` — public (unauthenticated) stream variant
- `playlist.m3u8` — HLS master/variant playlist

All public streams use `isVideoAuthRequired: false` and require no token.

---

## Map Initialization Options

From the map page `initMap` function, the map is configured with:

```json
{
  "RoutingModel": {
    "AutoCompleteCountryCode": "US",
    "MapBottomLeftBounds": {"Latitude": 35.360186, "Longitude": -119.914112},
    "MapTopRightBounds": {"Latitude": 41.988415, "Longitude": -114.062522}
  },
  "ClustererModel": {"MaximumZoom": 12, "MinimumClusterSize": 4},
  "DefaultZoom": 7,
  "MapCenter": {"Latitude": 38.7259857, "Longitude": -118.5955792},
  "MapTypeId": "roadmap",
  "SelectedLayers": ["TrafficSpeeds", "Incidents", "Construction", "Closures", "Cameras"],
  "IconUrl": "/map/mapIcons/{0}"
}
```

**Google Maps API Key** (embedded in page source, public):
```
AIzaSyBS3OuSbmXi_b7d0Rkue7GaZW_4upHg9x4
```

**Map tile provider** (non-Google fallback):
```
https://stg.map-tiles.traveliq.co/world.json   (MapLibre GL vector tiles)
```

**SearchHere / HERE Maps API Key** (embedded in `map_resources.js`):
```
kkq87qzo7t3EbQMlTXlaKWnNM7vmYibqrzcbmXjYqM0
```

---

## JavaScript Bundle Analysis

The following bundles were analysed to discover endpoints:

| Bundle URL | Size | Key findings |
|------------|------|--------------|
| `/bundles/map511` | 46 KB | Route planner API (`/api/route/*`) |
| `/bundles/map` | 162 KB | Core map component; `/Camera/GetVideoUrl`, `/GetLatLng`, `/wta/*` |
| `/bundles/511GoogleMapComp` | 131 KB | Marker clustering; references `pa.ibi511.com` |
| `/bundles/listCctv` | 96 KB | Camera list page; `/Camera/GetVideoUrl`, `/NoSession/GetCctvAgencyImage` |
| `/bundles/datatables` | 309 KB | DataTables + `CamListConfig`; `/List/GetData/`, `/List/UniqueColumnValues*` |
| `/Scripts/map/LayerSpecific/myCameraTooltip.min.js` | small | My Cameras feature; `/Camera/AddMyCameraList`, `/Camera/SaveMyCameras` |
| `/scripts/jsresources/map/map` | 13 KB | `resources.*` config; `CameraVideoUrl`, `EnableVideoUrlRefresh` |
| `/scripts/jsresources/List/listResources` | 4 KB | List-page resources; `CameraRefreshRateMs=60000` |

**Key patterns extracted from bundles:**

```javascript
// Camera list (datatables bundle)
$.ajax("/Camera/GetUserCameraLists", {type: "GET"})
window.listPageV2("#cctvTable", "/List/UniqueColumnValuesForCctv/{typeId}", ...)
ajax: {url: "/List/GetData/" + typeId, type: "GET", ...}

// Video stream resolution (listCctv bundle)
$.ajax("/Camera/GetVideoUrl?imageId=" + id, {type: "GET", cache: false})

// Agency logo (listCctv bundle)
src="/NoSession/GetCctvAgencyImage?agencyId=" + agencyId
```

---

## Python Client Usage

The client requires **Python 3.7+** and uses only the standard library.

### Installation

No installation required. Copy `ndot_nv_client.py` to your project.

### Basic usage

```python
from ndot_nv_client import NVRoadsClient

client = NVRoadsClient()
```

### List cameras

```python
# All cameras (paginated, 100 per request)
cameras = client.list_cameras(length=50)

# Search by roadway substring
i15_cams = client.list_cameras(search="I-15")

# Filter by region
lv_cams = client.list_cameras(region="Las Vegas")

# Combine filters
i15_lv = client.list_cameras(search="I-15", region="Las Vegas")

# Get ALL cameras (handles pagination automatically)
all_cameras = client.list_cameras_all()
print(f"Total: {len(all_cameras)}")  # 643
```

### Camera properties

```python
for cam in i15_cams[:3]:
    print(cam.id)                  # 4746
    print(cam.roadway)             # "Silverado Ranch Blvd & I-15 SB Ramp"
    print(cam.region)              # "Las Vegas"
    print(cam.lat, cam.lon)        # 36.0132, -115.1812
    print(cam.snapshot_url)        # "https://www.nvroads.com/map/Cctv/4746"
    print(cam.primary_video_url)   # "https://d1wse4.its.nv.gov:443/..."
    print(cam.has_video)           # True
```

### Download camera snapshot

```python
jpeg_bytes = client.get_camera_image(4746)
with open("camera_4746.jpg", "wb") as f:
    f.write(jpeg_bytes)
# Images refresh every 60 seconds (CloudFront cache)
```

### Get HLS video stream URL

```python
# From camera object (most efficient — no extra request)
hls_url = cam.primary_video_url

# Or resolve via API (useful when you only have an image ID)
hls_url = client.get_camera_video_url(4746)
# "https://d1wse4.its.nv.gov:443/.../playlist.m3u8"

# Play with ffmpeg:
# ffplay "https://d1wse4.its.nv.gov:443/.../playlist.m3u8"
# Or VLC: vlc <url>
```

### Traffic events

```python
from ndot_nv_client import (
    LIST_TYPE_TRAFFIC, LIST_TYPE_CONSTRUCTION,
    LIST_TYPE_CLOSURES, LIST_TYPE_INCIDENTS
)

# All active events
all_events = client.list_events()
print(f"{len(all_events)} active events")

# By type
closures = client.list_events(LIST_TYPE_CLOSURES)
construction = client.list_events(LIST_TYPE_CONSTRUCTION)
incidents = client.list_events(LIST_TYPE_INCIDENTS)

# Filter I-80 events
i80_events = client.list_events(search="I-80")

# Full closures only
full_closures = [e for e in closures if e.is_full_closure]

# Event properties
for ev in closures:
    print(ev.id, ev.roadway_name, ev.description[:60])
    print(f"  Severity: {ev.severity}, Direction: {ev.direction}")
    print(f"  Full closure: {ev.is_full_closure}")
    print(f"  Start: {ev.start_date}, End: {ev.end_date}")
```

### Road conditions

```python
conditions = client.list_road_conditions(search="I-80")
for rc in conditions:
    if rc.primary_condition not in ("No Report", "Dry"):
        print(f"{rc.roadway}: {rc.primary_condition}")
        if rc.secondary_conditions:
            print(f"  Also: {', '.join(rc.secondary_conditions)}")

# All conditions (434 segments)
all_conditions = client.list_road_conditions(length=100)
```

### Weather stations (RWIS)

```python
stations = client.list_weather_stations()
for ws in stations:
    print(f"{ws.name}: {ws.air_temperature}, pavement={ws.pavement_condition}")
    print(f"  Wind: {ws.wind_direction}@{ws.wind_speed_avg} mph "
          f"(gust {ws.wind_speed_gust})")
    print(f"  Precip: {ws.precipitation}, Visibility: {ws.visibility} mi")

# Mountain pass conditions
mountain = client.list_weather_stations(search="Donner")
```

### Dynamic message signs (DMS)

```python
signs = client.list_message_signs(area="Las Vegas")

# Signs with active messages
active = [s for s in signs if s.message.strip()]
for s in active:
    print(f"{s.name}: {s.message}")
    if s.message2:
        print(f"  Line 2: {s.message2}")
```

### Count helpers

```python
print("Cameras:", client.count_cameras())          # 643
print("Events:", client.count_events())             # ~83
print("Construction:", client.count_events("construction"))  # ~56
```

### Tooltip HTML

```python
html = client.get_tooltip("Cameras", 4746)
html = client.get_tooltip("Construction", 75)
html = client.get_tooltip("WeatherStations", 78837)
```

### Pagination

```python
# Manual pagination (100 records per page max)
page1 = client.list_cameras(start=0, length=100)
page2 = client.list_cameras(start=100, length=100)

# Automatic pagination (fetch all)
all_cameras = client.list_cameras_all(region="Las Vegas")
```

---

## CLI Reference

```
python ndot_nv_client.py [OPTIONS]

Options:
  --demo             Full live API demonstration (default when no flags given)
  --cameras          Camera listing section only
  --events           Traffic events section only
  --conditions       Road conditions section only
  --weather          RWIS weather stations section only
  --signs            DMS message signs section only
  --search TERM      Full-text search term
  --region REGION    Region filter for cameras (e.g. "Las Vegas", "Reno")
  --save-image ID    Download a camera snapshot JPEG to disk
  --json             Output results as JSON instead of formatted text
  --timeout N        HTTP timeout in seconds (default: 15)
  --help             Show help
```

**Examples:**

```bash
# Full demo
python ndot_nv_client.py

# I-80 cameras as JSON
python ndot_nv_client.py --cameras --json --search "I-80"

# Download camera 4746 snapshot
python ndot_nv_client.py --save-image 4746

# Las Vegas events
python ndot_nv_client.py --events --region "Las Vegas"

# Road conditions search
python ndot_nv_client.py --conditions --search "US-50"
```

---

## Live Record Counts

As of 2026-03-27 (live counts from the API):

| Data Type       | Count |
|-----------------|-------|
| Cameras         | 643   |
| Active Events   | 83    |
| Construction    | 56    |
| Future Roadwork | 13    |
| Closures        | 6     |
| Incidents       | 4     |
| Special Events  | 3     |
| Oversized Loads | 2     |
| Message Signs   | 382   |
| Weather Stations (RWIS) | 126 |
| Road Conditions | 434   |
| Rest Areas      | 35    |
| Truck Parking   | 56    |
| Visitor Locations | 3   |

---

## I-15 / I-80 Corridor Cameras

### I-15 (Las Vegas to Utah border)

There are 55 cameras tagged with "I-15" in the roadway field, concentrated in:

- **Las Vegas metro**: Flamingo Rd, Sahara Ave, Blue Diamond, Silverado Ranch,
  Tropicana, Spring Mountain, Russell Rd interchange cameras
- **North of Las Vegas**: I-15 NB/SB at various mile markers up to the Utah border

**Example camera IDs on I-15 (Las Vegas):**
- 4746: Silverado Ranch Blvd & I-15 SB Ramp
- 4754: Flamingo Rd & I-15 SB Ramp
- 4755: Flamingo Rd & I-15 NB Ramp Arena
- 4797: Sahara Ave & I-15 NB Ramp
- 4814: I-15 NB Blue Diamond North

```python
i15_cameras = client.list_cameras(search="I-15", region="Las Vegas")
```

### I-80 (Reno to Utah border)

Cameras along I-80 cover the Sierra passes and the Elko corridor:

- **Reno/Sparks area**: I-80 at various interchange and mile-marker cameras
- **Elko corridor**: Chain-up areas, Carlin Tunnel, mountain passes
- **Wendover**: I-80 near the Utah border

**Example camera IDs on I-80 (Elko):**
- 4917: I-80 & Golconda East Bound MM196 Chain Up HU32
- 4920: I-80 West Side of Carlin Tunnel 80 Foot Pole MM285
- 4923: I-80 Emigrant W/B Chain Up MM275
- 4924: I-80 Emigrant E/B Chain Up MM263

```python
i80_cameras = client.list_cameras(search="I-80")
```

---

## Known Limitations

1. **Server-side pagination cap:** The API enforces a maximum of 100 rows per
   request.  The `list_cameras_all()` method handles this automatically.

2. **No WebSocket / push updates:** Data must be polled.  The site uses a
   60-second client-side timer for camera image refresh.

3. **ChainControls / TrafficSpeeds / WeatherEvents / Snowplow** are map-only
   layers not accessible via the `/List/GetData/` endpoint (HTTP 500).

4. **No GeoJSON endpoint discovered:** The site uses Google Maps and does not
   expose a GeoJSON feed.  Coordinates are embedded in list responses as WKT
   `POINT (lon lat)` strings.

5. **KML feed is empty:** The `/NoSession/GetKml?name=Nearby511` endpoint
   returns 200 but with an empty body as of testing.

6. **Road condition timestamps** for many segments are stale (months or years
   old).  The `stale` boolean field indicates when a reading has not been
   refreshed recently.

7. **Rate limiting:** No explicit rate limiting was observed during testing,
   but excessive polling at sub-60-second intervals is discouraged and may
   result in CloudFront throttling.

8. **Session cookies:** The site sets `session-id` and
   `__RequestVerificationToken` cookies, but they are not required for any
   read-only request.

---

## Ethical & Legal Notes

- This client only reads **publicly available data** from the same endpoints
  used by the production website.
- No authentication is bypassed; all endpoints are anonymous.
- Please respect the service by **not polling faster than necessary** (60-second
  intervals are appropriate for camera images; 5-minute intervals for event data).
- The data is provided by NDOT for public traveler information use.
- Camera images are JPEG files intended for display on the public website.
