# LaDOTD 511LA Traffic API — Reverse-Engineering Notes & Python Client

**Reverse-engineered from** https://www.511la.org
**Agency:** Louisiana Department of Transportation & Development (LaDOTD)
**System:** IBI Group 511 platform, version 08.01.01
**Date:** 2026-03-27
**Client file:** `ladotd_client.py`

---

## Overview

The Louisiana 511 traveler information system (511la.org) is a public-facing
web application built on the IBI Group 511 platform.  It exposes a set of
unauthenticated JSON REST endpoints that power its interactive map, list pages,
and DataTables widgets.  These endpoints return live, operationally current
data for:

- **336 traffic cameras** with JPEG snapshot images (10-second refresh) and HLS video streams
- Active **incidents**, **construction** events, and **road closures**
- **59 Variable Message Signs** (DMS) with current displayed messages
- **100 movable bridges** with open/closed status
- **5 ferry crossings** with current operational status
- **10 highway rest areas** / welcome centers with amenity information
- **NWS weather forecast** zones covering Louisiana (7 zones)
- **Waze crowd-sourced** incidents and closures (21 current reports)
- **Traffic speed tile** overlay (XYZ tile server)
- Geographic layers: parish boundary KMZ, LADOTD engineering district KMZ

**No API key is required.** All endpoints are publicly accessible without authentication.

---

## Infrastructure

| Component | Details |
|-----------|---------|
| Web server | ASP.NET (X-Powered-By: ASP.NET) |
| CDN | Amazon CloudFront |
| Map API | Google Maps JavaScript API v. quarterly |
| Google Maps Key | `AIzaSyAqkBAboYbLsHyVVa7K1lHZSQBdyWTHcFw` _(belongs to LADOTD/IBI — do not abuse)_ |
| Traffic tiles | `tiles.ibi511.com` |
| Video streaming | Three LADOTD WOWZA streaming servers (see below) |
| GIS / ArcGIS | `ladotd.maps.arcgis.com` |
| LADOTD portal | `wwwsp.dotd.la.gov`, `wwwapps.dotd.la.gov` |

### Streaming CDN Servers

All camera live video is delivered as HLS (m3u8) from three regional LADOTD ITS
streaming servers:

| Hostname | Region | Stream prefixes |
|----------|--------|-----------------|
| `ITSStreamingBR.dotd.la.gov`  | Baton Rouge 1     | `br-cam-NNN` |
| `ITSStreamingBR2.dotd.la.gov` | Baton Rouge 2     | `shr-cam-NNN`, `laf-cam-NNN`, `lkc-cam-NNN`, `mnr-cam-NNN` |
| `ITSStreamingNO.dotd.la.gov`  | New Orleans       | `nor-cam-NNN`, `hou-cam-NNN`, `ns-cam-NNN` |

Stream URL pattern:
```
https://{hostname}/public/{region-cam-NNN}.streams/playlist.m3u8
```

---

## API Endpoints

### Base URL
```
https://www.511la.org
```

---

### 1. Map Marker Positions

Returns icon positions for all items on a given map layer.  Fast, lightweight,
but returns only IDs and coordinates — no detail.

```
GET /map/mapIcons/{layerId}
```

**Response:**
```json
{
  "item1": {
    "url": "/Generated/Content/Images/511/map_camera.svg",
    "size": [29, 35],
    "origin": [0, 0],
    "anchor": [14, 34],
    "zindex": 0,
    "preventClustering": false,
    "isClickable": true,
    "rotation": 0
  },
  "item2": [
    {
      "itemId": "1",
      "location": [32.538889, -93.630833],
      "icon": { "size": [29, 35], "anchor": [14, 34], "zindex": 0, ... },
      "title": ""
    },
    ...
  ]
}
```

**Valid `layerId` values (live counts as of 2026-03-27):**

| layerId | Live count | Notes |
|---------|-----------|-------|
| `Cameras` | 336 | All traffic cameras |
| `Incidents` | 4 | Active incidents |
| `Construction` | 199 | Active construction |
| `Closures` | 79 | Active closures |
| `ClosuresPolyline` | — | Closure geometry (polyline) |
| `SpecialEvents` | 0 | Special events |
| `WeatherReports` | 0 | NWS weather reports |
| `WeatherIncidents` | 0 | Weather-related incidents |
| `WeatherClosures` | 0 | Weather-related closures |
| `WeatherEvents` | 6 | Weather event polygons |
| `WeatherForecast` | 7 | NWS zone forecast points |
| `MessageSigns` | 58 | Variable message signs |
| `Bridge` | 100 | Movable bridges |
| `FerryTerminals` | 5 | Ferry crossings |
| `RestAreas` | 10 | Highway rest areas |
| `Waze` | 0 | Waze jam reports |
| `WazeIncidents` | 19 | Waze crowd incidents |
| `WazeClosures` | 0 | Waze crowd closures |

---

### 2. List / Structured Data (DataTables)

Returns paginated, rich structured records for a map layer.  This is the same
data displayed in the 511la.org list pages.

```
GET /List/GetData/{layerId}?query={JSON}&lang=en
```

**Query parameter** (`query`) is a JSON-serialised DataTables server-side request:

```json
{
  "draw": 1,
  "columns": [],
  "order": [{"column": 0, "dir": "asc"}],
  "start": 0,
  "length": 100,
  "search": {"value": "", "regex": false}
}
```

> The server hard-caps responses at **100 records** regardless of `length`.
> Paginate using `start` (0-based offset).

**Response:**
```json
{
  "draw": 1,
  "recordsTotal": 336,
  "recordsFiltered": 336,
  "data": [ ... ]
}
```

**Valid `layerId` values:** `Cameras`, `Incidents`, `Construction`, `Closures`,
`SpecialEvents`, `MessageSigns`, `Bridge`, `FerryTerminals`, `RestAreas`,
`WazeIncidents`, `WazeClosures`

#### Camera record schema

```json
{
  "DT_RowId": "1",
  "id": 1,
  "sourceId": "100",
  "source": "LADOTD",
  "location": "I-20 at I-220 Off Ramp",
  "roadway": "I-20",
  "direction": "Unknown",
  "latLng": {
    "geography": {
      "coordinateSystemId": 4326,
      "wellKnownText": "POINT (-93.630833 32.538889)"
    }
  },
  "images": [
    {
      "id": 1,
      "cameraSiteId": 1,
      "sortOrder": 0,
      "description": "Traffic closest to this camera is traveling eastbound on I-20.",
      "imageUrl": "/map/Cctv/1",
      "imageType": 0,
      "videoUrl": "https://ITSStreamingBR2.dotd.la.gov/public/shr-cam-030.streams/playlist.m3u8",
      "videoType": "application/x-mpegURL",
      "isVideoAuthRequired": false,
      "videoDisabled": false,
      "disabled": false,
      "blocked": false
    }
  ],
  "region": null,
  "state": null,
  "county": null,
  "city": null,
  "dotDistrict": null,
  "nickname": null,
  "lastUpdated": "2019-10-22T15:14:52.5866667+00:00"
}
```

#### Traffic event record schema (Incidents, Construction, Closures)

```json
{
  "DT_RowId": "200597",
  "id": 200597,
  "type": "Incidents",
  "layerName": "Incidents",
  "roadwayName": "I-10",
  "description": "Stalled Vehicle on I-10 Eastbound near Almonaster Ave MM (240). 1 Left lane blocked.",
  "sourceId": "87240",
  "source": "ERS",
  "comment": null,
  "eventSubType": "stalledvehicle",
  "startDate": "3/27/26, 3:48 PM",
  "endDate": null,
  "lastUpdated": "3/27/26, 3:50 PM",
  "isFullClosure": false,
  "severity": "Minor",
  "direction": "East",
  "locationDescription": "Almonaster Ave",
  "detourDescription": null,
  "laneDescription": "1 Left lane blocked",
  "widthRestriction": null,
  "heightRestriction": null,
  "heightUnderRestriction": null,
  "lengthRestriction": null,
  "weightRestriction": null,
  "majorEvent": null,
  "showOnMap": true
}
```

#### Message Sign record schema

```json
{
  "DT_RowId": "DOTD--10017",
  "roadwayName": "I-10",
  "direction": "Eastbound",
  "name": "I-10 e bef Causeway (MM 227.37)",
  "area": "N/A",
  "description": "I-10 e bef Causeway (MM 227.37)",
  "message": "TRAVEL TIME TO:<br/>SUPERDOME&nbsp;8-10 MIN<br/>I-510&nbsp;28-30 MIN",
  "message2": "",
  "message3": "",
  "phase1Image": null,
  "phase2Image": null,
  "status": "on",
  "lastUpdated": "3/27/26, 3:49 PM"
}
```

#### Movable Bridge record schema

```json
{
  "DT_RowId": "1",
  "filterAndOrderProperty1": "PROVOST",
  "filterAndOrderProperty2": "Open",
  "filterAndOrderProperty3": "Closed",
  "filterAndOrderProperty4": "02",
  "parish": "TERREBONNE",
  "schedule": "Permanently closed to marine traffic.",
  "notes": "N/A",
  "structureNumber": "200850",
  "bridgeType": "PGSWNG",
  "phone": "",
  "county": "Acadia Parish",
  "state": "Louisiana",
  "lastUpdated": "12/6/24, 1:12 PM"
}
```

`filterAndOrderProperty1` = bridge name, `filterAndOrderProperty2` = current status,
`filterAndOrderProperty3` = normal status, `filterAndOrderProperty4` = district code.

#### Ferry Terminal record schema

```json
{
  "DT_RowId": "101",
  "filterAndOrderProperty1": "Lower Algiers-Chalmette Ferry",
  "from": "Lower Algiers",
  "to": "Chalmette",
  "additionalInformation": "Out of Service",
  "status": "In service (normal operating hours)",
  "organization": "LADOT",
  "county": "St. Bernard Parish",
  "state": "Louisiana",
  "lastUpdated": "3/27/26, 4:16 AM"
}
```

---

### 3. Camera Snapshot Image

```
GET /map/Cctv/{imageId}
```

Returns a JPEG image (may be empty/0 bytes when camera is offline).

- **Cache-Control:** `max-age=10` (refreshed every 10 seconds)
- **CDN:** Amazon CloudFront
- **Response type:** `image/jpeg`
- **Headers:** `access-control-allow-origin: *` (CORS-open)

Example:
```
https://www.511la.org/map/Cctv/1
```

---

### 4. Camera Video URL Lookup

```
GET /Camera/GetVideoUrl?imageId={id}
```

Returns a JSON-encoded string with the HLS playlist URL:

```json
"https://ITSStreamingBR2.dotd.la.gov/public/shr-cam-030.streams/playlist.m3u8"
```

---

### 5. Tooltip / Detail HTML

```
GET /tooltip/{layerId}/{itemId}?lang=en
```

Returns an HTML fragment (Bootstrap card/table) for display in map pop-ups.
Content includes camera images, event details, sign messages, bridge schedules, etc.

Parameters:
- `lang`: Language code, `en` (English only for Louisiana)

Example:
```
https://www.511la.org/tooltip/Cameras/1?lang=en
https://www.511la.org/tooltip/Incidents/200597?lang=en
https://www.511la.org/tooltip/MessageSigns/DOTD--10017?lang=en
https://www.511la.org/tooltip/WeatherForecast/LAZ001?lang=en
```

---

### 6. Camera Filter Values

```
GET /List/UniqueColumnValuesForCctv/{layerId}
```

Returns available filter drop-down values for the camera list.

Example response:
```json
{
  "state": ["Louisiana"],
  "region": ["Central", "North Shore", "Northeast", "Northwest", "South Central", "Southeast", "Southwest"],
  "dotDistrict": [],
  "county": [],
  "city": [],
  "roadway": ["I-10", "I-110", "I-12", "I-20", ...]
}
```

---

### 7. Route Network Geocoding

```
GET /api/route/getlocations?latitude={lat}&longitude={lon}&zoom={zoom}
```

Returns road segment names and link IDs at a given coordinate.  Used by
the 511la.org map's context menu ("From here" / "To here" route planner).

Parameters:
- `latitude`: WGS-84 decimal latitude
- `longitude`: WGS-84 decimal longitude
- `zoom`: Map zoom level hint (default 16, higher = more detail)

Example response:
```json
[
  {
    "linkId": "841361787",
    "name": "St Charles",
    "isForward": true,
    "isDrivable": false,
    "point": {"latitude": 29.950123, "longitude": -90.070418},
    "travelTimeDisplay": "0 min",
    "maneuverCode": 0,
    "nameDirection": "St Charles Southbound"
  },
  ...
]
```

---

### 8. Geographic Layers

**Louisiana Parish boundaries KMZ:**
```
https://511la.org/Content/LU/KML/Parish.kmz
```

**LADOTD Engineering District boundaries KMZ:**
```
https://511la.org/Content/LU/KML/District.kmz
```

---

### 9. Traffic Speed Tile Overlay

XYZ tile server for real-time traffic speed color overlay (green/yellow/red):

```
https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
```

Compatible with Leaflet, Google Maps, MapboxGL, and any XYZ tile consumer.

---

### 10. My511 Session Endpoints (require login)

These endpoints require an authenticated session cookie (POST `/My511/Login`).
They are **not** implemented in the public client but are documented for completeness.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/My511/Login` | POST | Authenticate with email+password |
| `/my511/register` | GET | Sign-up page |
| `/My511/ResendUserConfirmation` | POST | Resend confirmation email |
| `/Camera/GetUserCameraLists` | GET | List of user's camera views |
| `/Camera/SaveMyCameras` | POST | Add/remove camera from saved view |
| `/Camera/AddMyCameraList` | POST | Create a new camera view |
| `/Camera/DeleteMyCameraList?listId=` | GET | Delete a camera view |
| `/Camera/SetDefaultList?listId=` | GET | Set default camera view |
| `/Api/Route/SaveUserRoute` | POST | Save a named route |
| `/Api/Route/GetRouteByShareID?shareId=` | GET | Load a shared route |
| `/My511/SaveQuickRouteAlert` | POST | Subscribe to route alerts |

---

## JavaScript Bundles Analyzed

The following client-side JavaScript bundles were reverse-engineered to discover
the API surface:

| Bundle URL | Purpose | Key findings |
|-----------|---------|-------------|
| `/bundles/map511` | Map page core | Route planning, context menu, `/api/route/` endpoints |
| `/bundles/map` | Map component | DataTable AJAX, `/List/GetData/` pattern |
| `/bundles/myCctv` | Camera panel | Camera carousel, `DisplayMyCameras`, `/Camera/GetUserCameraLists` |
| `/bundles/listCctv` | Camera list page | `CamListConfig`, `/Camera/GetVideoUrl` |
| `/bundles/datatables` | DataTables + custom | `listPageV2`, `/List/GetData/{typeId}` full discovery |
| `/scripts/jsresources/map/map` | Resource strings | `CameraRefreshRateMs=10000`, layer IDs, feature flags |

---

## Python Client Usage

```python
from ladotd_client import LaDOTDClient

client = LaDOTDClient()

# ── Cameras ─────────────────────────────────────────────────────────────────
cameras = client.get_cameras()
print(f"Total cameras: {len(cameras)}")

# Filter by roadway
i10_cams = client.get_cameras(roadway="I-10")

# Get all cameras with live video streams
video_cams = [c for c in cameras if c.has_video]
for cam in video_cams[:3]:
    img = cam.primary_image
    print(f"{cam.location}: {img.video_url}")
    # → https://ITSStreamingBR.dotd.la.gov/public/br-cam-004.streams/playlist.m3u8

# Download a JPEG snapshot
jpeg_bytes = client.get_camera_snapshot(image_id=1)
with open("camera_1.jpg", "wb") as f:
    f.write(jpeg_bytes)

# Get HLS stream URL directly
hls_url = client.get_camera_video_url(image_id=1)
# Play with: ffplay "hls_url"  or  vlc "hls_url"

# ── Traffic Events ───────────────────────────────────────────────────────────
incidents   = client.get_incidents()
construction = client.get_construction()
closures    = client.get_closures()
waze        = client.get_waze_incidents()

for event in incidents:
    print(f"[{event.severity}] {event.roadway_name}: {event.description}")

# All events at once
all_events = client.get_all_events()

# ── Variable Message Signs ───────────────────────────────────────────────────
signs = client.get_message_signs()
for sign in signs:
    print(f"{sign.name}: {sign.full_message}")

# Filter by roadway
i10_signs = client.get_message_signs(roadway="I-10")

# ── Movable Bridges ──────────────────────────────────────────────────────────
bridges = client.get_bridges()
open_bridges = [b for b in bridges if b.current_status.lower() != "open"]
for b in open_bridges:
    print(f"{b.name} ({b.parish}): {b.current_status}")

# ── Ferries ──────────────────────────────────────────────────────────────────
ferries = client.get_ferries()
for ferry in ferries:
    print(f"{ferry.name}: {ferry.status}")
    if ferry.additional_information:
        print(f"  → {ferry.additional_information}")

# ── Rest Areas ───────────────────────────────────────────────────────────────
rest_areas = client.get_rest_areas()
for area in rest_areas:
    print(f"{area.name} ({area.direction})")

# ── Map Markers (fast — IDs + coordinates only) ──────────────────────────────
markers = client.get_map_markers("Cameras")
for m in markers[:5]:
    print(f"Camera #{m.item_id}: ({m.latitude:.4f}, {m.longitude:.4f})")

# ── Weather ──────────────────────────────────────────────────────────────────
forecast_zones = client.get_weather_forecast_locations()
for zone in forecast_zones:
    print(f"NWS Zone {zone.item_id}: ({zone.latitude:.4f}, {zone.longitude:.4f})")
    # Get full forecast HTML:
    html = client.get_tooltip("WeatherForecast", zone.item_id)

# ── Geocoding / Route Planning ───────────────────────────────────────────────
roads = client.geocode_road(latitude=29.9511, longitude=-90.0715)
for road in roads:
    print(f"{road.name_direction} [{road.link_id}]")

# ── Tile URLs ────────────────────────────────────────────────────────────────
speed_tile_template = client.get_traffic_speed_tile_url()
# "https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}"

parish_kmz = client.get_parish_kmz_url()
district_kmz = client.get_district_kmz_url()

# ── Filter Values ────────────────────────────────────────────────────────────
filters = client.get_camera_filter_values()
print("Available regions:", filters["region"])
print("Available roadways:", filters["roadway"])
```

---

## CLI Demo

```bash
# List all cameras with HLS video streams
python3 ladotd_client.py cameras

# Active incidents
python3 ladotd_client.py incidents

# Active construction
python3 ladotd_client.py construction

# Active closures
python3 ladotd_client.py closures

# Variable message sign content
python3 ladotd_client.py signs

# Movable bridge open/closed status
python3 ladotd_client.py bridges

# Ferry terminal status
python3 ladotd_client.py ferries

# Highway rest areas
python3 ladotd_client.py restareas

# Waze crowd-reported incidents
python3 ladotd_client.py waze

# Weather events on map
python3 ladotd_client.py weather

# NWS zone forecast locations
python3 ladotd_client.py forecast

# Download camera snapshot (saves to camera_{id}.jpg)
python3 ladotd_client.py snapshot 1

# Road names at a coordinate (New Orleans French Quarter)
python3 ladotd_client.py geocode 29.9511 -90.0715
```

---

## Live Test Results (2026-03-27)

All endpoints confirmed live against production:

| Endpoint | Status | Records |
|---------|--------|---------|
| `/map/mapIcons/Cameras` | OK | 336 cameras |
| `/map/mapIcons/Incidents` | OK | 4 incidents |
| `/map/mapIcons/Construction` | OK | 199 events |
| `/map/mapIcons/Closures` | OK | 79 closures |
| `/map/mapIcons/WeatherForecast` | OK | 7 NWS zones |
| `/map/mapIcons/Bridge` | OK | 100 bridges |
| `/map/mapIcons/FerryTerminals` | OK | 5 ferries |
| `/map/mapIcons/RestAreas` | OK | 10 areas |
| `/map/mapIcons/WazeIncidents` | OK | 19 waze items |
| `/map/mapIcons/MessageSigns` | OK | 58 signs |
| `/List/GetData/Cameras` | OK | 336 total, 100/page |
| `/List/GetData/Incidents` | OK | 3–6 active |
| `/List/GetData/Construction` | OK | 224 active |
| `/List/GetData/Closures` | OK | 79–102 active |
| `/List/GetData/MessageSigns` | OK | 59 signs |
| `/List/GetData/Bridge` | OK | 100 bridges |
| `/List/GetData/FerryTerminals` | OK | 5 ferries |
| `/List/GetData/RestAreas` | OK | 10 areas |
| `/List/GetData/WazeIncidents` | OK | 16–21 active |
| `/map/Cctv/1` | OK | 17,777 bytes JPEG |
| `/Camera/GetVideoUrl?imageId=1` | OK | HLS URL returned |
| `/List/UniqueColumnValuesForCctv/Cameras` | OK | 7 regions, 35 roadways |
| `/api/route/getlocations` | OK | Road segments returned |
| `/tooltip/Cameras/1?lang=en` | OK | HTML fragment |
| `/tooltip/WeatherForecast/LAZ001?lang=en` | OK | Multi-day NWS forecast |

All 336 cameras have video stream URLs assigned.  Stream availability depends
on the individual camera hardware being online.

### HLS CDN Breakdown (live)

| Server | Cameras | Sample prefix |
|--------|---------|---------------|
| `ITSStreamingBR.dotd.la.gov` | 43 | `br-cam-004` through `br-cam-191` |
| `ITSStreamingBR2.dotd.la.gov` | 40 | `shr-cam-*`, `laf-cam-*`, `lkc-cam-*`, `mnr-cam-*` |
| `ITSStreamingNO.dotd.la.gov` | 37 | `nor-cam-*`, `hou-cam-*`, `ns-cam-*` |

---

## Rate Limiting & Etiquette

- No rate limiting headers observed on any endpoint
- `Cache-Control: max-age=10` on camera snapshots; respect this and do not
  poll faster than every 10 seconds per camera
- The API is a public service operated for Louisiana motorists; keep request
  volume reasonable (no bulk parallel scraping)
- Do not abuse the embedded Google Maps API key

---

## Known Limitations

1. **Weather Incidents / Closures** (`WeatherIncidents`, `WeatherClosures`,
   `WeatherReports`) return 0 records when no events are active; these layers
   do work when events exist.
2. **WeatherEvents** (`/List/GetData/WeatherEvents`) returns HTTP 500 — the
   list view for this layer is not implemented server-side even though the map
   layer works via `/map/mapIcons/WeatherEvents`.
3. **Coordinates** are encoded in WKT `POINT (lon lat)` format (note: longitude
   first) inside a nested JSON structure — the client handles this automatically.
4. **Pagination** is required for Cameras (336 records) and Construction
   (200+ records) as the server hard-caps responses at 100 records.
5. **Authenticated endpoints** (`/My511/*`, `/Camera/GetUserCameraLists`, etc.)
   require a session cookie obtained via `POST /My511/Login` and are not covered
   by this client.

---

## File Structure

```
outputs/
├── ladotd_client.py       # Production Python client (stdlib only)
└── ladotd_README.md       # This documentation
```

---

## Dependencies

None. The client uses Python standard library only:

- `urllib.request` / `urllib.error` / `urllib.parse` — HTTP requests
- `gzip` — response decompression (servers send gzip)
- `json` — JSON parsing
- `re` — WKT coordinate extraction
- `dataclasses` — typed response models
- `sys` — CLI entry point

**Python version:** 3.7+ (dataclasses, `from __future__ import annotations`)
