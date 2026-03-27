# GDOT 511GA Traffic API — Reverse Engineering Report & Python Client

> Comprehensive reverse-engineered API documentation for the Georgia Department
> of Transportation (GDOT) 511GA traffic information portal at https://511ga.org.

## Table of Contents

1. [Overview](#overview)
2. [Methodology](#methodology)
3. [Infrastructure](#infrastructure)
4. [Authentication & Session Management](#authentication--session-management)
5. [Discovered API Endpoints](#discovered-api-endpoints)
   - [Map Icon Geo-Index](#1-map-icon-geo-index)
   - [List / DataTables Endpoint](#2-list--datatables-endpoint)
   - [Tooltip Detail](#3-tooltip-detail)
   - [Camera Snapshot Image](#4-camera-snapshot-image)
   - [Camera Video URL (Signed HLS)](#5-camera-video-url-signed-hls)
   - [Alerts API](#6-alerts-api)
   - [Emergency Alert](#7-emergency-alert)
   - [Traffic Speed Tiles](#8-traffic-speed-tiles)
   - [KML Static Feeds](#9-kml-static-feeds)
6. [API Keys Found](#api-keys-found)
7. [Data Schemas](#data-schemas)
   - [Camera](#camera-schema)
   - [Traffic Event](#traffic-event-schema)
   - [Message Sign](#message-sign-schema)
   - [Alert](#alert-schema)
8. [CDN & Video Streaming Infrastructure](#cdn--video-streaming-infrastructure)
9. [Python Client Usage](#python-client-usage)
10. [CLI Reference](#cli-reference)
11. [Known Limitations](#known-limitations)
12. [Legal / Terms of Use](#legal--terms-of-use)

---

## Overview

The 511GA website is built on the **TravelIQ / AlgoTraffic** platform (an ASP.NET
application deployed behind AWS CloudFront CDN). It provides real-time traffic data
for the state of Georgia including:

- **3,865+ traffic cameras** with live JPEG snapshots and HLS video streams
- **Dynamic Message Signs (DMS)** with current message text
- **Traffic incidents, construction, closures, and special events**
- **Weather forecasts** at key locations across the state
- **Rest area information**
- **Express lane status**
- **Road-condition alerts and emergency notifications**

All data is publicly accessible without a user account. Session cookie initialization
is automatic on first HTTP request.

---

## Methodology

1. **HTTP header inspection** — `curl -I https://511ga.org` to identify server stack,
   CDN, and authentication cookies.
2. **HTML source analysis** — Downloaded homepage HTML, extracted all JS bundle URLs,
   feed URLs, layer configurations, and icon paths.
3. **JavaScript bundle analysis** — Downloaded and deobfuscated the following bundles:
   - `/bundles/map511` — Route planning, AJAX endpoints
   - `/bundles/map` — Map component core
   - `/bundles/datatables` — List page DataTables configuration (revealed `/List/GetData/`)
   - `/bundles/alerts` — Alert polling endpoints
   - `/bundles/listCctv` — Camera list page scripts
   - `/scripts/jsresources/map/map` — Client-side configuration variables (revealed API keys)
   - `/scripts/jsresources/List/listResources` — List page resource strings
4. **Live endpoint probing** — Systematically tested all discovered paths with and
   without session cookies to confirm behavior.
5. **Response schema analysis** — Parsed all JSON responses to extract field names and
   types.

---

## Infrastructure

| Component | Technology |
|-----------|-----------|
| Web framework | ASP.NET (MVC, server-side rendering) |
| CDN | AWS CloudFront (`via: 1.1 xxx.cloudfront.net`) |
| Map provider | Google Maps API (key: `AIzaSyDuiuFbStuKdQHWHoWseCTC9VoN8GhF1lg`) |
| Traffic tiles | `tiles.ibi511.com` (IBI Group / AlgoTraffic) |
| Camera images | Hosted on `511ga.org` server, proxied from SKYLINE CCTV |
| Video streams | `sfs-msc-pub-lq-*.navigator.dot.ga.gov` (GDOT media servers) |
| Stream management | `stream-manager.navigator.dot.ga.gov` (internal, not externally routable) |
| Map tiles (alternative) | `stg.map-tiles.traveliq.co` (MapLibre GL vector tiles) |
| Search autocomplete | HERE Maps API (key: `kkq87qzo7t3EbQMlTXlaKWnNM7vmYibqrzcbmXjYqM0`) |
| Analytics | Google Analytics 4 (ID: `G-G8BXWB3PWG`) |
| Platform | TravelIQ / AlgoTraffic (algotraffic.com) |

---

## Authentication & Session Management

The 511GA API uses **session cookies** for state. No login or API key is required
for read-only public data access.

### Cookie Flow

1. GET any page on `511ga.org` — server sets:
   - `session-id` — opaque session token (HttpOnly, Secure)
   - `_culture` — language preference (default `en`)
   - `session` — simple marker cookie
   - `__RequestVerificationToken` — CSRF token (needed for POST requests, but the
     DataTables List endpoints accept requests without it)

2. Include all cookies in subsequent requests.

3. The `session-id` cookie is a 256-character hex string. It does not expire
   quickly — it persists across requests in a browser session window.

### Notes

- All API endpoints are served over HTTPS only (HSTS enforced, 1 year).
- Response bodies are gzip-compressed (`Content-Encoding: gzip`) even when the
  server does not echo back `Accept-Encoding`. Clients must decompress responses.
- Most JSON endpoints return `Content-Type: application/json; charset=utf-8`.
- The server is hosted behind CloudFront which may apply rate limiting; spacing
  requests by ~0.5s is recommended for bulk fetching.

---

## Discovered API Endpoints

Base URL: `https://511ga.org`

### 1. Map Icon Geo-Index

**Purpose:** Retrieve a lightweight list of all items in a map layer. Returns only
item IDs and coordinates — no detail fields. Ideal for building a spatial index.

```
GET /map/mapIcons/{layer}
```

**Layers available:**
```
Cameras, Construction, ConstructionClosures, ElectricVehicleCharger,
ExpressLanes, IncidentClosures, Incidents, MessageSigns, PortOfEntry,
RestAreas, SpecialEvents, Waze, WazeHazards, WazeIncidents, WazeReports,
WazeTraffic, WeatherEvents, WeatherForecast
```

**Request:**
```bash
curl -c cookies.txt https://511ga.org/map
curl -b cookies.txt https://511ga.org/map/mapIcons/Cameras
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
      "itemId": "11139",
      "location": [33.995518, -83.733475],
      "icon": { "size": [29, 35], "anchor": [14, 34], ... },
      "title": ""
    },
    ...
  ]
}
```

**Response sizes (observed 2026-03):**
| Layer | Count |
|-------|-------|
| Cameras | 3,865 |
| MessageSigns | 205 |
| Construction | ~30 |
| Incidents | ~19 |
| RestAreas | 26 |
| WeatherForecast | 7 |

---

### 2. List / DataTables Endpoint

**Purpose:** Paginated, sortable, detail records for any event or camera type.
Uses DataTables server-side processing protocol.

```
POST /List/GetData/{type}
Content-Type: application/x-www-form-urlencoded
```

**Types available:**
```
cameras, construction, closures, incidents, messagesigns,
specialevents, weatherevents, traffic
```

Note: `traffic` returns all event types combined (incidents + construction +
closures + special events).

**Request parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `draw` | int | DataTables draw counter (any positive integer) |
| `start` | int | Zero-based record offset |
| `length` | int | Records per page (tested up to 100 reliably) |
| `order[0][column]` | int | Column index to sort by |
| `order[0][dir]` | string | `asc` or `desc` |

**Example:**
```bash
curl -b cookies.txt -X POST https://511ga.org/List/GetData/cameras \
  --data "draw=1&start=0&length=100&order[0][column]=0&order[0][dir]=asc"
```

**Response:**
```json
{
  "draw": 1,
  "recordsTotal": 3865,
  "recordsFiltered": 3865,
  "data": [ ... ]
}
```

---

### 3. Tooltip Detail

**Purpose:** HTML-formatted detail popup for a single map item. Returns rendered
HTML (not JSON). Useful for scraping structured detail when the List endpoint
doesn't have full data.

```
GET /tooltip/{layer}/{itemId}?lang=en
```

**Example:**
```bash
curl -b cookies.txt "https://511ga.org/tooltip/Cameras/11139?lang=en"
curl -b cookies.txt "https://511ga.org/tooltip/MessageSigns/12040?lang=en"
curl -b cookies.txt "https://511ga.org/tooltip/Incidents/4469772?lang=en"
curl -b cookies.txt "https://511ga.org/tooltip/RestAreas/6?lang=en"
curl -b cookies.txt "https://511ga.org/tooltip/WeatherForecast/ALBANY?lang=en"
```

Returns an HTML fragment (`<div class="map-tooltip">...</div>`).

For cameras, this HTML contains:
- Camera description and direction
- CCTV image ID (`data-camera-id`)
- HLS video URL (`data-videourl`)
- Video MIME type (`data-streamtype`, e.g. `application/x-mpegURL`)

---

### 4. Camera Snapshot Image

**Purpose:** Live JPEG/PNG snapshot from a traffic camera. No authentication
required. Image is refreshed server-side approximately every 60 seconds
(configurable: `CameraRefreshRateMs = 60000`).

```
GET /map/Cctv/{cctv_image_id}
```

The `cctv_image_id` is the `images[n].id` field from the List/GetData/cameras
response (e.g. `18549`). This is distinct from the camera site ID.

**Example:**
```bash
curl -b cookies.txt "https://511ga.org/map/Cctv/18549" > camera.png
```

Returns a PNG image (typically 450×253 pixels, ~160 KB).

**No auth required.** The image URL is publicly accessible with any valid session
cookie.

---

### 5. Camera Video URL (Signed HLS)

**Purpose:** Obtain a short-lived signed HLS playlist URL for live video streaming.

```
GET /Camera/GetVideoUrl?imageId={cctv_image_id}
```

**Response:** A JSON string (quoted URL):
```
"https://sfs-msc-pub-lq-01.navigator.dot.ga.gov:443/rtplive/BARR-CCTV-0003/playlist.m3u8?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3NzQ2NDIyNTEsImV4cCI6MTc3NDY0MjM3MX0.LPvk2tXXP4Ds5vWDL4CGyNlMGbW_Z7NMpskZj-5C5dU"
```

**Token:** JWT (RS256/HS256). Payload contains:
- `iat` — issued at (Unix timestamp)
- `exp` — expires at (approximately 2 minutes after issue)

**Video stream servers:**
```
sfs-msc-pub-lq-01.navigator.dot.ga.gov:443  (low-quality, server 1)
sfs-msc-pub-lq-02.navigator.dot.ga.gov:443  (low-quality, server 2)
sfs-msc-pub-lq-03.navigator.dot.ga.gov:443  (low-quality, server 3)
```

All servers use valid TLS certificates (`*.navigator.dot.ga.gov`, issued by DigiCert,
organization: Georgia Department of Transportation).

**HLS stream path pattern:**
```
/rtplive/{CAMERA_NAME}/playlist.m3u8?token={JWT}
```

Where `CAMERA_NAME` is the SKYLINE camera identifier (e.g. `BARR-CCTV-0003`,
`FLYD-CCTV-0012`). The pattern is `{COUNTY_CODE}-CCTV-{NUMBER}`.

**Playing the stream:**
```bash
# Get the signed URL first
URL=$(curl -s -b cookies.txt "https://511ga.org/Camera/GetVideoUrl?imageId=18549" | tr -d '"')
# Play with ffplay (token valid ~2 min)
ffplay "$URL"
# Or with VLC
vlc "$URL"
# Or with mpv
mpv "$URL"
```

**Note:** The raw HLS URL without a token returns HTTP 401. The signed URL must
be refreshed before it expires (~2 minutes).

---

### 6. Alerts API

**Purpose:** Active road-condition alerts and notifications shown on the 511GA
website banner. Includes construction windows, lane closure schedules, and major
traffic events.

```
GET /Alert/GetUpdatedAlerts?lang=en
```

**Response:**
```json
{
  "alerts": [
    {
      "messages": {
        "messageLang1": {
          "message": "I-285/I-20 West Interchange Project: 3/23-3/29 Lane Closures",
          "additionalText": "<p>Motorists are advised to expect lane closures...</p>"
        },
        "messageLang2": { ... },
        "messageLang3": { ... }
      },
      "regions": ["13001", "13003", ...],
      "filterRegions": false,
      "highImportance": true
    }
  ],
  "emergencyAlertHash": 0
}
```

Regions are FIPS county codes (5-digit Georgia county codes starting with `13`).
When `filterRegions` is `false`, the alert applies statewide.

---

### 7. Emergency Alert

**Purpose:** Emergency-level alert banner (Amber Alerts, severe weather warnings,
major road closures).

```
GET /Alert/GetEmergencyAlert?lang=en
```

**Response (no active alert):**
```json
{"content": ""}
```

**Response (active alert):**
```json
{"content": "<div>...</div>"}
```

---

### 8. Traffic Speed Tiles

**Purpose:** Map tile overlays showing color-coded traffic speeds (green/yellow/red).

```
GET https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
```

Uses XYZ (slippy map) tile coordinates, Web Mercator projection (EPSG:3857).

**No session cookie required.** The tile server is operated by IBI Group / AlgoTraffic
as a third-party service.

**Finding tile coordinates:**
```python
import math
def lat_lng_to_tile(lat, lng, zoom):
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1/math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y, zoom

# Atlanta, GA at zoom 12
x, y, z = lat_lng_to_tile(33.749, -84.388, 12)
url = f"https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}"
```

---

### 9. KML Static Feeds

**Purpose:** Static geographic data files.

```
GET https://511ga.org/Content/GA/KML/county_layer.kmz
GET https://511ga.org/Content/GA/KML/hurricaneEvacuationRoute.kmz
```

These are KMZ (compressed KML) files containing county boundaries and hurricane
evacuation route geometry. No session cookie required.

---

## API Keys Found

These keys were found in the public JavaScript bundles served to all browsers.
They are not secret — they are intentionally included in client-side code.

| Key | Service | Value | Notes |
|-----|---------|-------|-------|
| Stream Manager | GDOT video stream server | `6MIN2CWetWLlyDNXrLBPHtmfifxvfLM7` | In `map_resources.js` |
| Google Maps | Google Maps Platform | `AIzaSyDuiuFbStuKdQHWHoWseCTC9VoN8GhF1lg` | In homepage HTML |
| HERE Maps | HERE Geocoding/Search | `kkq87qzo7t3EbQMlTXlaKWnNM7vmYibqrzcbmXjYqM0` | In `map_resources.js` |

Note: The Stream Manager API (`stream-manager.navigator.dot.ga.gov`) is on an
internal network and not externally reachable. The key is used in the browser
to request stream metadata but the actual video is obtained via the signed URL
from `/Camera/GetVideoUrl`.

---

## Data Schemas

### Camera Schema

Fields returned by `POST /List/GetData/cameras`:

```json
{
  "DT_RowId": "11139",
  "id": 11139,
  "sourceId": "10068",
  "source": "SKYLINE",
  "type": null,
  "areaId": "GA",
  "sortOrder": 2520,
  "roadway": "SR 211",
  "direction": "Eastbound",
  "location": "BARR-0003: SR 211 at Horton St (Barrow)",
  "latLng": {
    "geography": {
      "coordinateSystemId": 4326,
      "wellKnownText": "POINT (-83.733475 33.995518)"
    }
  },
  "linkId1": "1257291169T",
  "linkId2": null,
  "state": "Georgia",
  "county": null,
  "city": null,
  "dotDistrict": null,
  "country": "United States",
  "region": null,
  "jsonData": {"name": "BARR-CCTV-0003"},
  "images": [
    {
      "id": 18549,
      "cameraSiteId": 11139,
      "sortOrder": 0,
      "description": "BARR-0003: SR 211 at Horton St (Barrow)",
      "imageUrl": "/map/Cctv/18549",
      "imageType": 0,
      "videoUrl": "https://sfs-msc-pub-lq-01.navigator.dot.ga.gov:443/rtplive/BARR-CCTV-0003/playlist.m3u8",
      "videoType": "application/x-mpegURL",
      "isVideoAuthRequired": true,
      "videoDisabled": false,
      "disabled": false,
      "blocked": false,
      "language": "en"
    }
  ],
  "tooltipUrl": "/tooltip/Cameras/11139?lang={lang}&noCss=true"
}
```

**Key fields:**
- `images[n].id` — CCTV image ID used with `/map/Cctv/{id}` and `/Camera/GetVideoUrl?imageId={id}`
- `images[n].videoUrl` — Base HLS stream URL (without JWT token — requires `/Camera/GetVideoUrl` to get a signed version)
- `jsonData.name` — SKYLINE camera name (e.g. `BARR-CCTV-0003`)
- `latLng.geography.wellKnownText` — WKT `POINT(lng lat)` coordinates

### Traffic Event Schema

Fields returned by `POST /List/GetData/traffic` (and incidents, construction, etc.):

```json
{
  "DT_RowId": "2541027",
  "id": 2541027,
  "type": "Construction",
  "layerName": "Construction",
  "roadwayName": "SR 101",
  "description": "Road construction on SR 101 Southbound at W 5TH ST. Left lane blocked.",
  "sourceId": "4891182",
  "source": "GA-Events",
  "comment": null,
  "eventSubType": "road construction",
  "startDate": "8/8/25, 12:00 AM",
  "endDate": "4/30/26, 10:00 AM",
  "lastUpdated": "3/27/26, 1:56 PM",
  "isFullClosure": false,
  "severity": "minor",
  "direction": "s",
  "locationDescription": null,
  "detourDescription": null,
  "laneDescription": "Left lane blocked.",
  "recurrenceDescription": "",
  "widthRestriction": null,
  "heightRestriction": null,
  "heightUnderRestriction": null,
  "lengthRestriction": null,
  "weightRestriction": null,
  "majorEvent": null,
  "county": "Floyd",
  "region": "Georgia Statewide",
  "state": "Georgia",
  "country": "United States",
  "showOnMap": true,
  "cameras": [...]
}
```

**Event types observed:**
- `Construction` — road construction work zones
- `Construction Closures` — full road closures for construction
- `Incidents` — traffic incidents (crashes, stalled vehicles, debris)
- `Incident Closures` — full road closures due to incidents
- `Special Events` — concerts, sporting events, parades

**Severity values:** `minor`, `major`

### Message Sign Schema

Fields returned by `POST /List/GetData/messagesigns`:

```json
{
  "DT_RowId": "12122",
  "roadwayName": "I-285",
  "direction": "Northbound",
  "name": "GDOT-DMS-0215",
  "area": "N/A",
  "description": "I-285 NB before BoltonRd (MM 12.0)",
  "message": "PACES FERRY<br/>5 MILES AHEAD<br/>TIME: 21-23 MIN",
  "message2": "",
  "message3": "",
  "phase1Image": null,
  "phase2Image": null,
  "status": "on",
  "lastUpdated": "3/27/26, 4:42 PM",
  "tooltipUrl": "/tooltip/MessageSigns/12122?lang={lang}&noCss=true"
}
```

**Notes:**
- `message`, `message2`, `message3` are the three "phases" of DMS content
- HTML `<br/>` tags indicate line breaks in the physical sign
- `status` values: `on`, `off`
- `name` follows pattern `GDOT-DMS-XXXX` for permanent signs

### Alert Schema

```json
{
  "alerts": [
    {
      "messages": {
        "messageLang1": {
          "message": "Short title",
          "additionalText": "<p>Full HTML description...</p>"
        }
      },
      "regions": ["13121", "13089"],
      "filterRegions": false,
      "highImportance": true
    }
  ],
  "emergencyAlertHash": 0
}
```

---

## CDN & Video Streaming Infrastructure

### Camera Image CDN

Camera snapshots (`/map/Cctv/{id}`) are served directly from `511ga.org` through
AWS CloudFront. Response headers show:
```
X-Cache: Miss from cloudfront
Via: 1.1 xxx.cloudfront.net (CloudFront)
```

Images are PNG format, typically 450×253 pixels.

### Video Streaming Infrastructure

GDOT operates its own video streaming infrastructure at `navigator.dot.ga.gov`:

```
Stream servers (public, require JWT):
  sfs-msc-pub-lq-01.navigator.dot.ga.gov:443
  sfs-msc-pub-lq-02.navigator.dot.ga.gov:443
  sfs-msc-pub-lq-03.navigator.dot.ga.gov:443

Stream management (internal, not publicly reachable):
  stream-manager.navigator.dot.ga.gov
```

HLS stream path pattern:
```
/rtplive/{COUNTY_CODE}-CCTV-{NUMBER}/playlist.m3u8?token={JWT}
```

County code examples: `BARR` (Barrow), `BART` (Bartow), `FLYD` (Floyd),
`FULT` (Fulton), `COBB` (Cobb), `GWNN` (Gwinnett), etc.

The JWT token has a very short lifetime (~2 minutes). The 511GA website refreshes
it automatically before expiration (`EnableVideoUrlRefresh = True`). External
clients must call `/Camera/GetVideoUrl?imageId={id}` to get a fresh token
before playback.

---

## Python Client Usage

The `gdot_client.py` file requires only the Python standard library (Python 3.9+).
No third-party packages needed.

### Basic Import and Initialization

```python
from gdot_client import GDOTClient

client = GDOTClient()
# Session cookies are obtained automatically on first request
```

### List All Camera Locations (Fast)

```python
# Returns 3865+ items — just IDs and coordinates
icons = client.get_camera_map_icons()
print(f"Total cameras: {len(icons)}")
for icon in icons[:5]:
    print(f"  Camera {icon.item_id}: ({icon.lat:.4f}, {icon.lng:.4f})")
```

### Get Camera Details (Paginated)

```python
# Get first page with full detail
total, cameras = client.get_cameras(start=0, length=100)
print(f"Total: {total}, fetched: {len(cameras)}")

# Or iterate through all cameras
for cam in client.iter_cameras():
    print(cam.location, cam.roadway)
```

### Filter Cameras by County or Road

```python
# Search cameras on I-285 in Fulton County
matching = client.search_cameras(roadway="I-285", county="Fulton")
for cam in matching:
    print(cam.location)
    print("  Snapshot:", cam.snapshot_url)
```

### Download a Camera Snapshot

```python
# Download current live image (no auth, ~60s refresh)
img_bytes = client.get_camera_snapshot(18549)  # BARR-CCTV-0003
with open("traffic_cam.png", "wb") as f:
    f.write(img_bytes)
print(f"Saved {len(img_bytes):,} bytes")
```

### Get Signed HLS Video URL

```python
# Get a JWT-signed HLS playlist URL (~2 min validity)
url = client.get_camera_video_url(18549)
print(url)
# Play with: ffplay "{url}"  or  vlc "{url}"

# Refresh the token before it expires:
import time
while True:
    url = client.get_camera_video_url(18549)
    print(f"New stream URL: {url[:60]}...")
    time.sleep(90)  # Refresh every 90 seconds
```

### List Active Incidents

```python
total, incidents = client.get_traffic_events(event_type="incidents")
print(f"Active incidents: {total}")
for ev in incidents:
    print(f"  [{ev.severity}] {ev.roadway_name}: {ev.description}")
    if ev.cameras:
        print(f"    Camera: {ev.cameras[0].snapshot_url}")
```

### List All Traffic Events (Combined)

```python
# Iterate through all active events (incidents + construction + closures)
for ev in client.iter_traffic_events(event_type="traffic"):
    print(f"{ev.type}: {ev.roadway_name} ({ev.county})")
    print(f"  {ev.description[:80]}")
    print(f"  {ev.start_date} -> {ev.end_date or 'TBD'}")
```

### Read Dynamic Message Signs

```python
# All DMS signs with active messages
for sign in client.iter_message_signs():
    if sign.message:
        print(f"[{sign.roadway_name} {sign.direction}] {sign.description}")
        print(f"  {sign.full_message}")  # HTML stripped
        print(f"  Updated: {sign.last_updated}")
```

### Read Current Alerts

```python
alerts = client.get_alerts()
for alert in alerts:
    print(f"{'[HIGH]' if alert.high_importance else '[Normal]'} {alert.message}")

emergency = client.get_emergency_alert()
if emergency:
    print(f"EMERGENCY: {emergency}")
```

### Get Map Icons for Any Layer

```python
# Get locations of all message signs
signs = client.get_map_icons("MessageSigns")
print(f"Total DMS signs: {len(signs)}")

# Get locations of all incidents
incidents = client.get_map_icons("Incidents")
for inc in incidents:
    print(f"Incident {inc.item_id} at ({inc.lat:.4f}, {inc.lng:.4f})")
```

### Traffic Speed Tile URL

```python
import math

def lat_lng_to_tile(lat, lng, zoom):
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1/math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y, zoom

# Get traffic tile for Atlanta area at zoom 12
x, y, z = lat_lng_to_tile(33.749, -84.388, 12)
url = GDOTClient.traffic_tile_url(x, y, z)
print(url)
```

---

## CLI Reference

```
python gdot_client.py <command> [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `demo` | Run a full API demonstration |
| `cameras` | List traffic cameras |
| `incidents` | List active incidents |
| `construction` | List construction events |
| `messagesigns` | List Dynamic Message Signs |
| `alerts` | Show current road alerts |
| `camera-image <id> <output>` | Download camera snapshot to file |
| `camera-video-url <id>` | Print signed HLS stream URL |
| `map-icons <layer>` | Show map icon geo-index for a layer |

### Global Options

| Option | Default | Description |
|--------|---------|-------------|
| `--timeout` | 20 | HTTP timeout in seconds |

### Command Options

```bash
# Cameras
python gdot_client.py cameras --limit 20 --county Fulton --roadway I-285

# Incidents
python gdot_client.py incidents --limit 10 --county DeKalb

# Construction
python gdot_client.py construction --limit 10 --county Gwinnett

# Message Signs
python gdot_client.py messagesigns --limit 20 --roadway I-75

# Alerts (verbose shows full text)
python gdot_client.py alerts --verbose

# Download camera snapshot
python gdot_client.py camera-image 18549 /tmp/cam.png

# Get signed HLS URL (for VLC / ffplay)
python gdot_client.py camera-video-url 18549

# Map icon geo-index
python gdot_client.py map-icons Cameras --limit 10
python gdot_client.py map-icons MessageSigns --limit 20

# Full demo
python gdot_client.py demo
```

### Example Output

```
$ python gdot_client.py incidents
Fetching incidents...
Active incidents (21 shown):

  [4469772] Incidents on SR 236
   [street event] on SR 236 Eastbound at HENDERSON MILL RD. 2 right lanes are blocked.
   Severity: N/A
   Started: Mar 28 2026, 3:00 PM
   Lanes: 2 right lanes are blocked.
   County: DeKalb

$ python gdot_client.py camera-video-url 18549
Getting video URL for CCTV image 18549...
https://sfs-msc-pub-lq-01.navigator.dot.ga.gov:443/rtplive/BARR-CCTV-0003/playlist.m3u8?token=eyJ0eX...
```

---

## Known Limitations

1. **Video token expiry:** HLS video URLs expire after ~2 minutes. Applications must
   call `/Camera/GetVideoUrl` to refresh the JWT before expiry.

2. **Video server access:** The actual video streaming servers
   (`sfs-msc-pub-lq-*.navigator.dot.ga.gov`) require the JWT token. The Stream
   Manager API (`stream-manager.navigator.dot.ga.gov`) is on an internal network
   not reachable from outside GDOT infrastructure.

3. **Pagination limit:** The `/List/GetData/` endpoint returns unreliable results
   above 100 records per page. Use pagination (start + length) for large datasets.
   The `/map/mapIcons/` endpoint returns all items in a single request.

4. **Gzip encoding:** All API responses are gzip-compressed. Clients must decompress
   (the Python client handles this automatically).

5. **Session required:** While no login is needed, a valid session cookie must be
   present. The session is obtained automatically on first request in the Python client.

6. **Camera county metadata:** Some cameras return `null` for `county`. Use the
   camera name prefix (e.g. `BARR` = Barrow, `FULT` = Fulton) as a fallback.

7. **No GeoJSON endpoint:** The API does not expose a native GeoJSON endpoint.
   Geographic data is embedded in WKT format in JSON responses or in KMZ files.
   Convert using `LatLng.from_wkt()`.

8. **Rate limiting:** CloudFront/server may throttle excessive requests.
   Respect a ~0.5s delay between requests for bulk fetching.

---

## Legal / Terms of Use

This reverse engineering was conducted for **research and informational purposes**.
The data accessed is public information published by the Georgia Department of
Transportation for the benefit of Georgia motorists.

- The 511GA website and API are operated by GDOT and powered by AlgoTraffic.
- All data (camera images, traffic events, DMS messages) is public information.
- No authentication was bypassed; no protected data was accessed.
- The Google Maps API key, HERE Maps key, and Stream Manager API key are
  intentionally included in publicly served JavaScript bundles — they are not
  secret credentials.

When building applications with this API:
- Respect the server with reasonable request rates (no aggressive crawling).
- Do not redistribute or resell GDOT traffic data without appropriate licensing.
- Check GDOT's terms of service at https://www.dot.ga.gov for current policies.
- For production use of traffic data, consider GDOT's official data sharing
  programs: https://www.dot.ga.gov/GDOT/Pages/travelinfodata.aspx

---

*Report generated: 2026-03-27 | API version: 26.01.29 (from JS bundle version strings)*
