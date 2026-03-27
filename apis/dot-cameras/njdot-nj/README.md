# 511NJ Traffic API — Reverse-Engineering Notes & Python Client

> A complete reverse-engineering of the New Jersey Department of Transportation
> 511NJ traffic information system, including all discovered API endpoints,
> request/response schemas, authentication mechanisms, and a production-quality
> Python client (`njdot_client.py`).

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Discovery Method](#2-discovery-method)
3. [API Architecture](#3-api-architecture)
4. [Public Endpoints (No Auth)](#4-public-endpoints-no-auth)
5. [Authenticated Endpoints](#5-authenticated-endpoints)
6. [Admin-Only Endpoints](#6-admin-only-endpoints)
7. [Camera Streaming System](#7-camera-streaming-system)
8. [Authentication Mechanism](#8-authentication-mechanism)
9. [Request Encryption](#9-request-encryption)
10. [Data Models](#10-data-models)
11. [Python Client Usage](#11-python-client-usage)
12. [CDN and Infrastructure](#12-cdn-and-infrastructure)
13. [JavaScript Bundle Map](#13-javascript-bundle-map)
14. [Known Limitations](#14-known-limitations)

---

## 1. System Overview

**Target:** https://511nj.org
**Operator:** New Jersey Department of Transportation (NJDOT)
**Platform:** Angular 17+ Single-Page Application
**Hosting:** Azure CDN (confirmed via `x-azure-ref` response header)
**HTTP:** HTTP/2 with Azure front-door

The 511NJ system is a traffic information portal that provides:
- Live camera feeds from NJDOT and NJ Turnpike Authority cameras
- Traffic incident and event data
- Travel time information for major NJ corridors (NJ Turnpike, Garden State Parkway)
- Road condition reports and weather overlays
- Airport parking availability (EWR, JFK, LGA)
- Mega-project construction information

---

## 2. Discovery Method

### Step 1 — HTML source inspection

The homepage (`https://511nj.org/`) served via HTTP 308 redirect from `www.511nj.org`.
The HTML references three Angular entry-point bundles:

```
polyfills-5CFQRCPP.js
scripts-OX6CFOO3.js
main-3EVECEGS.js          ← 3.7 MB minified Angular application
```

And a lazy-loaded camera popup chunk:
```
camera-popup.component-5F3WZGKD.js   ← 41 KB, camera stream logic
```

### Step 2 — JavaScript bundle analysis

The main bundle (`main-3EVECEGS.js`) contains the full Angular application including:
- All HTTP service classes with their endpoint paths
- An HTTP interceptor that attaches Bearer tokens and optionally AES-encrypts request bodies
- Angular component templates with routing definitions
- A hardcoded list of endpoints that require request-body encryption
- The AES key and IV used for client-side encryption (see §9)

Extraction method: regex pattern matching against `this.http.post("/<path>")` and
`this.http.get("/<path>")` strings in the minified JS.

### Step 3 — Static asset discovery

`/assets/configs/application.json` — public, no authentication required.
Contains full map configuration including center coordinates, zoom bounds,
layer definitions, and refresh intervals.

### Step 4 — Live endpoint testing

All discovered endpoints were tested with `curl` / Node.js `https.get` to
confirm HTTP method, response envelope format, and auth requirement.

---

## 3. API Architecture

### URL structure

All API endpoints are relative to `https://511nj.org`. There is no separate
API subdomain (`api.511nj.org` does not resolve).

```
https://511nj.org/client/*       Public and user-authenticated data endpoints
https://511nj.org/account/*      Authentication and account management
https://511nj.org/admin/*        Admin-only management endpoints
https://511nj.org/master/*       Internal camera proxy endpoints
https://511nj.org/TrafficLand/*  TrafficLand image proxy
https://511nj.org/CCTV/*         NY Thruway camera status
https://511nj.org/assets/*       Static files (config JSON, HLS player HTML)
```

### Response envelope

All JSON endpoints return the same envelope:

```json
{
  "errorId": "",
  "exceptions": null,
  "data": <payload>,
  "status": 200
}
```

| `status` | Meaning                                       |
|----------|-----------------------------------------------|
| `200`    | Success                                       |
| `401`    | Not authenticated (no or invalid token)       |
| `403`    | Authenticated but insufficient permissions    |
| `500`    | Server-side error (usually bad request body)  |

Note: HTTP status code is always `200`; the API status is in the JSON body.

---

## 4. Public Endpoints (No Auth)

These endpoints return data without any authentication token.

### `GET /client/getReloadVersion`

Returns the current application version. The SPA polls this endpoint to
detect when a new deployment is available and reload automatically.

**Request:** No body, no auth.

**Response:**
```json
{
  "errorId": "",
  "exceptions": null,
  "data": {
    "id": 137,
    "key": "reloadVersion",
    "value": "\"91\"",
    "description": "reload application Version",
    "configMode": "UX",
    "parentKey": ""
  },
  "status": 200
}
```

**Live test:** `curl https://511nj.org/client/getReloadVersion`

---

### `GET /assets/configs/application.json`

Static client configuration file. Contains:

| Key | Value | Notes |
|-----|-------|-------|
| `NextRefreshInMilliSeconds` | `120000` | Event refresh interval (2 min) |
| `NextRefreshInMilliSecondsTileSpecific` | `30000` | Camera tile refresh (30 s) |
| `mapSettings.centerLonLat` | `[-74.728565, 40.08454]` | Map center (central NJ) |
| `mapSettings.defaultZoom` | `7.61` | Default zoom level |
| `mapSettings.minZoomLevel` | `6` | Minimum zoom |
| `mapSettings.maxZoomLevel` | `18` | Maximum zoom |
| `mapSettings.EventZoom` | `14` | Zoom when navigating to an event |
| `cameraPopup.zoomLevel` | `18` | Zoom when opening camera popup |

**Layer definitions** in `layers` key:

| Layer ID | Type | Description |
|----------|------|-------------|
| `speed_layer` | WMS | Live traffic speed layer (120 s refresh) |
| `roadway_ban_layer` | WMS | Roadway bans and restrictions |
| `incident_weather_detour` | Vector | Incidents, weather, detour markers |
| `construction_event` | Vector clustered | Construction event markers |
| `special_event` | Vector clustered | Special event markers |
| `congestion_event` | Vector clustered | Congestion markers |
| `camera` | Vector | Camera location markers |
| `ssp` | Vector | Safety Service Patrol vehicle locations |
| `parking_region` | Vector | Airport parking regions |
| `parking_data` | Vector | Parking availability data |
| `NJ_state_boundary` | Vector | NJ state outline |

---

### `GET /assets/configs/HLSCamera/Hls_Player.html`

Static HLS player HTML page. Used as an `<iframe>` src for HLS cameras.
The iframe receives the HLS stream URL via `localStorage` or query string.
Internally loads `hls.js` and `jquery-3.6.0.min.js`.

---

## 5. Authenticated Endpoints

All endpoints in this section return HTTP 200 with `status: 401` when called
without a valid Bearer token.

**Required header:** `Authorization: Token <accessToken>`

### `POST /client/get/event`

**The primary traffic event feed.** Returns all active NJ traffic events.

**Request body:**
```json
{"isScheduleEvent": true}
```

Set `isScheduleEvent: false` to exclude scheduled (future) events.

**Response** (`data` field is an array):
```json
[
  {
    "eventId": 12345,
    "name": "Accident - I-95 NB at Exit 8A",
    "categoryId": 1,
    "sortOrder": 10,
    "state": "NJ",
    "lastUpdateDate": "2026-03-27T14:30:00",
    "iconFile": "incident.svg",
    "latitude": 40.1234,
    "longitude": -74.5678,
    "description": "Two left lanes closed. Expect 20 min delay.",
    "isScheduleEvent": false
  }
]
```

**Event categories:**

| `categoryId` | Name |
|-------------|------|
| 1 | Incident |
| 2 | Construction |
| 3 | Special Event |
| 4 | Weather |
| 5 | Detour |
| 6 | Congestion |
| 7 | Scheduled Construction |
| 8 | Scheduled Special Event |

The Angular client filters NJ Turnpike / Garden State Parkway events using
`categoryId == 1 || categoryId == 5` with `sortOrder == 10` and `state == "NJ"`.

---

### `POST /client/category/get`

Returns the event category list used to populate filter dropdowns.

**Request body:** `null`

**Response:** Array of category objects.

---

### `POST /client/appsetting/get`

Returns server-side configuration settings. Values are stored AES-encrypted
in the database and decrypted by the server before sending.

**Request body:** `null`

**Key settings in the response:**

| Key | Description |
|-----|-------------|
| `apiUrl` | Backend API base URL (empty string = same origin) |
| `baseMapURL` | Basemap tile service URL |
| `role` | Authenticated user's role |
| `switchToElfsight` | Feature flag for Elfsight widget |
| `maxCamerasAllowsInCameraTile` | Max cameras per dashboard widget |
| `isLogCameraError` | Whether to send camera error telemetry |
| `horizontalScrollbarOptions` | UI scroll config |
| `cameraFailureWindowMilliSeconds` | Camera error detection window (5000 ms default) |
| `defaultTimezone` | System timezone string |
| `isShowTimeZone` | Whether to display timezone labels |

---

### `POST /client/trafficMap/getHlsToken`

Fetches an authenticated HLS streaming token for a Skyline Networks camera.

**Request body:**
```json
{"id": 42}
```
Where `42` is the camera's integer ID.

**Response** (`data` field):
```json
{
  "hlsToken": "eyJhbGciOiJIUzI1NiJ9...",
  "duration": 3600,
  "token": "abc123...",
  "username": "viewer",
  "type": "hls_skyline",
  "cameraId": 42,
  "camerURL": "https://skyline.njdot.gov/live/cam42/index.m3u8",
  "thruwayStatus": ""
}
```

The `camerURL` is an HLS manifest URL. Load it with `hls.js` or any
HLS-capable media player. The token expires after `duration` seconds.

---

### `POST /client/getStateBoundary`

Returns the NJ state boundary geometry for map display.

**Request body:** `{}` or a filter object

**Response:** GeoJSON geometry or coordinate array.

---

### `POST /client/getTripGeom`

Returns route geometries for popular travel links.

**Request body:** `{}` or `{"tripId": <id>}`

**Response:** GeoJSON linestring data for road segments.

---

### `POST /client/getAirportRegion`

Returns geographic regions and parking availability for Newark Liberty (EWR),
LaGuardia (LGA), and JFK airports.

**Request body:** `{}` or `{"regionCode": "EWR"}`

**Response:** Airport regions with GeoJSON polygons and parking data.

---

### `POST /client/travellink/getLinks`

Returns travel-time data for monitored road segments across NJ.

**Request body:** `null`

**Response** (`data` field is an array):
```json
[
  {
    "id": 101,
    "name": "NJ Turnpike NB Exit 8 to Exit 9",
    "normalTime": 12,
    "currentTime": 18,
    "travelIndex": 1.5
  }
]
```

---

### `POST /client/weatherwidget/getWidgetData`

Returns weather overlay data for the map.

**Request body:** `null` or filter params

---

### `POST /client/dashboard/getDefaultConfiguration`

Returns the default dashboard tile layout for new users.

**Request body:** `{}`

---

### `POST /client/get/getEventPopupData`

Returns detailed data for a single event popup panel.

**Request body:**
```json
{"eventId": 12345}
```

---

### `POST /client/camera/insertCameraErrorLog`

Client-side telemetry: logs a camera load failure back to the server.

**Request body:**
```json
{
  "cameraId": 42,
  "error": "Video failed to load: streaming playlist unavailable"
}
```

---

### `GET /master/camera/getTrafficlaneFullURL`

Returns a signed still-image URL for a TrafficLand camera.
These are typically New Jersey Turnpike Authority cameras.

**Query string:** `?id=<webId>`

**Response:**
```json
{
  "fullUrl": "https://cdn.trafficland.com/cam123/still.jpg?token=abc&expires=...",
  "isTrafficLandDown": false,
  "errorMsg": "",
  "tokenTimeoutSecond": 300
}
```

The `fullUrl` expires after `tokenTimeoutSecond` seconds. The SPA refreshes it
via `setInterval` before expiry. Append `&rnd=<epoch>` to bust CDN caching.

---

### `GET /CCTV/getThruwayStatus`

Checks whether a New York Thruway camera is operational.

**Query string:** `?CameraId=<id>`

**Response:**
```json
{"thruwayStatus": true}
```

Used by the SPA to show/hide Thruway camera feeds that cross from NJ into NY.

---

### `GET /api/v1/CCTV/getThruwayStatus`

Alternate v1 endpoint for Thruway status.

**Query string:** `?Id=<id>`

Note: This endpoint returns HTTP 403 (Access Denied) from public testing,
suggesting it requires a different auth mechanism or network allowlist.

---

### `GET /TrafficLand/getImageFromUrl`

Proxy for `imageproxy`-type cameras. The server fetches the image from a
private TrafficLand CDN upstream and returns it.

**Query string:** `?Url=<encoded_camera_url>`

Example:
```
GET /TrafficLand/getImageFromUrl?Url=https://private-cdn.example.com/cam5.jpg?rnd=0.123
```

---

## 6. Admin-Only Endpoints

These endpoints require an administrator-level access token.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/manage/admincctvcamere/getGridData` | All CCTV cameras with stream URLs |
| POST | `/admin/manage/admincctvcamere/savecameradata` | Create/update camera record |
| POST | `/admin/manage/admincctvcamere/generateCCTVReport` | Export camera CSV/PDF |
| POST | `/admin/manage/sectortripmapping/getGridData` | Trip-to-sector assignments |
| POST | `/admin/manage/travellink/getForGrid` | Travel links management |
| POST | `/admin/manage/travellink/insert` | Add travel link |
| POST | `/admin/manage/travellink/update` | Update travel link |
| POST | `/admin/manage/alert/getGridData` | System alert configuration |
| POST | `/admin/manage/alert/save` | Create/update alert |
| POST | `/admin/manage/eventtype/getForGrid` | Event type definitions |
| POST | `/admin/manage/floodgate/getGridData` | Roadway ban records |
| POST | `/admin/manage/floodgate/save` | Create/update roadway ban |
| POST | `/admin/roleMenuMapping/getMenuData` | Role permission mapping |
| POST | `/admin/roles/getGridData` | Role list |
| POST | `/admin/segment/getGridData` | Road segment definitions |
| POST | `/admin/report/getGAReport` | Google Analytics report |
| POST | `/admin/report/getPOIList` | Points of interest |
| POST | `/admin/report/IVRStatisticReport` | IVR (phone) usage statistics |
| POST | `/admin/report/voiceassistant` | Voice assistant usage |
| POST | `/admin/tool/closeincident/getGridData` | Manually closeable incidents |
| POST | `/admin/tool/closeincident/manualCloseEvent` | Force-close an incident |
| POST | `/admin/tool/usercomment/getGridData` | User-submitted comments |
| POST | `/admin/tool/usercomment/export` | Export user comments |
| POST | `/admin/dashboard/admindashboard/getEventStatistics` | Event stats chart |
| POST | `/admin/dashboard/admindashboard/getGeneralStatistics` | System-wide stats |
| POST | `/admin/dashboard/admindashboard/getIVRStatistics` | IVR call stats |
| POST | `/admin/dashboard/admindashboard/getTopRoutes` | Most-viewed routes |
| POST | `/admin/ptsprofile/profile/getGridData` | PTS alert profiles |
| POST | `/admin/ptsprofile/profile/insert` | Create alert profile |
| POST | `/admin/megaproject/getRecord` | Mega-project records |
| POST | `/admin/files/getLists` | File manager |
| POST | `/admin/files/uploadFile` | Upload a file |
| POST | `/admin/appsetting/insert` | Add app setting |
| POST | `/admin/appsetting/update` | Update app setting |
| POST | `/admin/appsetting/syncdata` | Sync settings to all nodes |
| POST | `/admin/userRole/getGridData` | User-role assignments |
| POST | `/admin/userRole/update` | Update user role |
| POST | `/admin/user/userconfiguration/getTileData` | Per-user dashboard config |
| POST | `/admin/user/userconfiguration/saveTileData` | Save dashboard config |
| POST | `/admin/developersettings/rssmenu/getForGrid` | RSS/link menu items |
| POST | `/admin/developersettings/webpages/getGridData` | Static page definitions |
| POST | `/admin/developersettings/loginuser/getGridData` | Login audit log |

### Camera admin data schema (`/admin/manage/admincctvcamere/getGridData`)

```json
[
  {
    "id": 42,
    "name": "I-295 NB at CR 656",
    "latitude": "39.9234",
    "longitude": "-75.0123",
    "iconFile": "cctv-green.png",
    "stopCameraFlag": false,
    "tourId": 3,
    "tourName": "NJDOT Main Tour",
    "deviceDescription": null,
    "cameraMainDetail": [
      {
        "camera_id": 42,
        "camera_type": "hls_skyline",
        "camera_use_flag": "Y",
        "image_refresh_rate": 0,
        "priority": 1,
        "url": "https://skyline.njdot.gov/live/cam42/index.m3u8",
        "web_id": null
      }
    ]
  }
]
```

The `iconFile` values indicate operational status:
- `cctv-green.png` — camera operational
- `cctv-red.png` — camera down / error

---

## 7. Camera Streaming System

The 511NJ camera system supports four distinct stream types:

### `hls_skyline` — Skyline Networks HLS streams

Used for NJDOT-operated cameras on the Skyline Networks platform.

**Access flow:**
1. `POST /client/trafficMap/getHlsToken` with `{"id": <cameraId>}`
2. Response contains `camerURL` — an HLS `.m3u8` playlist URL
3. Play with hls.js (browser) or ffplay/VLC (command line)

**Token lifespan:** `duration` seconds (typically 3600)

**SPA HLS player:** `/assets/configs/HLSCamera/Hls_Player.html`
Uses `hls.js` with configuration:
```js
{
  enableWorker: false,
  lowLatencyMode: false,
  latency: 1,
  maxMaxBufferLength: 60
}
```

---

### `image_skyline` — Direct JPEG still images

Cameras with a publicly accessible JPEG URL (no token required once the URL
is known). The URL is stored in `cameraMainDetail[0].url`.

**Access:**
```
GET <camera.url>?rnd=<epoch_ms>
```
Refresh at `image_refresh_rate` second intervals (stored in `cameraMainDetail`).

---

### `imageproxy` — TrafficLand proxy images

Cameras behind a private CDN, proxied through the 511NJ server.

**Access:**
```
GET /TrafficLand/getImageFromUrl?Url=<camera.url>?rnd=<random>
```

---

### `TL_Image` — TrafficLand authenticated images

Typically NJ Turnpike Authority cameras managed by the TrafficLand platform.

**Access flow:**
1. `GET /master/camera/getTrafficlaneFullURL?id=<camera.web_id>`
2. Response contains `fullUrl` — a signed JPEG URL
3. `GET <fullUrl>&rnd=<random>`
4. Refresh token before `tokenTimeoutSecond` expires

**Image refresh:** The SPA uses `setInterval` at `tokenTimeoutSecond` (or a fallback
of `trafficlaneTokenTimeout` ms) to refresh the signed URL. Each refresh
calls step 1 again.

---

### Thruway camera status

NY Thruway cameras embedded in the NJ map (cross-border coverage) have an
additional status check:

```
GET /CCTV/getThruwayStatus?CameraId=<id>
```

Response: `{"thruwayStatus": true/false}`

If `thruwayStatus == false`, the camera UI shows a "Camera Currently Not Working"
overlay image instead of attempting to load the stream.

---

## 8. Authentication Mechanism

### Account login

```
POST /account/login
Content-Type: application/json

{
  "username": "<username>",
  "password": "<password>"
}
```

Note: The Angular SPA AES-encrypts credentials before sending (see §9).

**Successful response:**
```json
{
  "data": {
    "user_data": {
      "accessToken": "eyJ...",
      "userId": 123,
      "role": "viewer"
    }
  },
  "status": 200
}
```

### Token usage

The access token is passed in the `Authorization` header:
```
Authorization: Token <accessToken>
```

The token is stored in `localStorage["511_resource"]` (encrypted) by the SPA.

### Session management

The SPA runs a `workerRefreshToken` Web Worker that periodically refreshes
the access token using the `apiUrl` from `appsetting/get`. The refresh
endpoint path follows the pattern `<apiUrl>/account/refreshToken` (not
directly observable from public endpoints).

### Anonymous access

The SPA also uses `localStorage["511_resource"]` for anonymous/guest sessions.
Some public data endpoints check for either an authenticated token or a valid
session resource key.

---

## 9. Request Encryption

The Angular HTTP interceptor (`JF` class in the main bundle) applies AES
encryption to request bodies for a specific list of sensitive endpoints.

### Encrypted endpoints

```
report/IVRStatisticReport
report/voiceassistant
report/getCustomEventGAReport
account/user/getUser
manage/twitterlogroute/getLog
tool/usercomment/export
developersettings/loginuser/getGridData
accountcountymappingroute/getCounty
trafficMap/getCameraDataByTourId
weatherwidget/getWidgetData
get/county
populartravelroute/getTripData
mytransit/getById
map/getParkingConditionData
roles/insert
roles/update
megaproject/getGridData
eventtype/insert / update / getForEdit / delete
```

### Encryption parameters (from `etH()` function in main bundle)

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-CBC |
| Key | `lIo3M)_83,ALC0Wz` (16 bytes UTF-8) |
| IV | `.%A}8Qvqm23jYVc9` (16 bytes UTF-8) |
| Padding | PKCS7 |
| Output format | Hex-encoded ciphertext |

**Note:** These keys are embedded in the public JavaScript bundle and apply only
to the client-side request body transformation. The server validates the
token separately. This is obfuscation, not security.

The WMS tile endpoints are excluded from encryption:
```js
if (request.url.includes("wms")) return next.handle(request);
```

---

## 10. Data Models

### Event object

```json
{
  "eventId": 12345,
  "name": "Accident - I-95 NB at Exit 8A",
  "categoryId": 1,
  "sortOrder": 10,
  "state": "NJ",
  "lastUpdateDate": "2026-03-27T14:30:00",
  "iconFile": "incident.svg",
  "latitude": 40.1234,
  "longitude": -74.5678,
  "description": "Two left lanes blocked.",
  "isScheduleEvent": false
}
```

### Camera object (admin endpoint)

```json
{
  "id": 42,
  "name": "I-295 NB at CR 656",
  "latitude": "39.9234",
  "longitude": "-75.0123",
  "iconFile": "cctv-green.png",
  "stopCameraFlag": false,
  "tourId": 3,
  "tourName": "NJDOT Main Tour",
  "deviceDescription": null,
  "cameraMainDetail": [
    {
      "camera_id": 42,
      "camera_type": "hls_skyline",
      "camera_use_flag": "Y",
      "image_refresh_rate": 0,
      "priority": 1,
      "url": "https://skyline.njdot.gov/live/cam42/index.m3u8",
      "web_id": null
    }
  ]
}
```

### HLS token response

```json
{
  "hlsToken": "eyJhbGciOiJIUzI1NiJ9...",
  "duration": 3600,
  "token": "abc123",
  "username": "viewer",
  "type": "hls_skyline",
  "cameraId": 42,
  "camerURL": "https://skyline.njdot.gov/live/cam42/index.m3u8",
  "thruwayStatus": ""
}
```

### TrafficLand URL response

```json
{
  "fullUrl": "https://cdn.trafficland.com/cam123/still.jpg?token=xyz&expires=1234567890",
  "isTrafficLandDown": false,
  "errorMsg": "",
  "tokenTimeoutSecond": 300
}
```

### Travel link

```json
{
  "id": 101,
  "name": "NJ Turnpike NB Exit 8 to Exit 9",
  "normalTime": 12,
  "currentTime": 18
}
```

---

## 11. Python Client Usage

The `njdot_client.py` file is a self-contained Python 3.8+ module (stdlib only).

### Installation

No installation required. Copy `njdot_client.py` to your project.

### CLI Demo

```bash
# Show all discovered endpoints and test public APIs
python3 njdot_client.py

# Verbose mode: print full JSON responses
python3 njdot_client.py --verbose

# With authentication token
python3 njdot_client.py --token eyJ...

# Print only the app version
python3 njdot_client.py --version-only
```

### Library Usage

```python
from njdot_client import NJDOTClient, Event, Camera

# Public endpoints (no auth required)
client = NJDOTClient()

# Get app version
version = client.get_reload_version()
print(f"App version: {version.value}")

# Get map configuration
config = client.get_app_config()
print(f"Map center: {config.map_settings.center_lon_lat}")
print(f"Layers: {list(config.layers.keys())}")

# Authenticated usage
auth_client = NJDOTClient(auth_token="your_bearer_token")

# Get all active events
events = auth_client.get_events(include_scheduled=False)
incidents = [e for e in events if e.category_id == 1]
print(f"Active incidents: {len(incidents)}")

# Get travel times
links = auth_client.get_travel_links()
for link in links[:5]:
    if link.current_time and link.normal_time:
        delay = link.current_time - link.normal_time
        print(f"{link.name}: +{delay} min delay")

# Admin: get all cameras
cameras = auth_client.get_cameras_admin()
hls_cameras = [c for c in cameras if c.primary_detail and
               c.primary_detail.camera_type == "hls_skyline"]
print(f"HLS cameras: {len(hls_cameras)}")

# Get HLS stream for a camera
token = auth_client.get_hls_token(camera_id=42)
print(f"Stream URL: {token.camera_url}")
# -> load token.camera_url with hls.js or VLC

# Get TrafficLand still image
tl_url = auth_client.get_trafficland_url(web_id=500)
if not tl_url.is_down:
    print(f"Image URL: {tl_url.full_url}")
    # Token expires in tl_url.token_timeout_seconds seconds
```

### Polling pattern for events

```python
import time
from njdot_client import NJDOTClient

client = NJDOTClient(auth_token="your_token")
cfg = client.get_app_config()
interval = cfg.refresh_interval_ms / 1000  # typically 120 seconds

while True:
    events = client.get_events(include_scheduled=False)
    for e in events:
        if e.category_id == 1:  # incidents only
            print(f"[{e.last_update_date}] {e.name} @ {e.lat},{e.lon}")
    time.sleep(interval)
```

---

## 12. CDN and Infrastructure

| Component | Details |
|-----------|---------|
| Primary domain | `511nj.org` (redirects from `www.511nj.org`) |
| CDN | Azure CDN (confirmed via `x-azure-ref` header) |
| HTTP | HTTP/2 |
| TLS | TLS 1.3 (Azure managed) |
| Alternate subdomain | `traffic.511nj.org` (exists, routes to Azure 404 page) |
| API auth | Azure-hosted .NET backend (inferred from response headers) |
| Camera video | Skyline Networks IPTV platform (HLS via Skyline DME) |
| Camera stills (TL) | TrafficLand LLC (commercial traffic camera network) |
| Maps | Basemap provider loaded via `configuration.baseMapURL` (encrypted config) |

---

## 13. JavaScript Bundle Map

| File | Size | Contents |
|------|------|----------|
| `main-3EVECEGS.js` | 3.7 MB | Angular application, all services, HTTP interceptor, AES crypto |
| `camera-popup.component-5F3WZGKD.js` | 41 KB | Camera popup UI, HLS/image/TL camera player logic |
| `polyfills-5CFQRCPP.js` | ~100 KB | Browser compatibility polyfills |
| `scripts-OX6CFOO3.js` | ~200 KB | Third-party scripts |
| `chunk-6OW6VGXH.js` | 195 KB | Shared state and event services |
| `chunk-CPPRAPI3.js` | shared | Angular forms/routing |
| `chunk-666ACZUV.js` | shared | Angular core runtime |
| Other `chunk-*.js` | various | Lazy-loaded Angular feature modules |
| `assets/configs/application.json` | 4 KB | Public map/layer configuration |
| `assets/configs/HLSCamera/Hls_Player.html` | 568 B | HLS iframe player template |
| `assets/scripts/Hls_Player.js` | ~8 KB | hls.js wrapper with error handling |

---

## 14. Known Limitations

1. **All data endpoints require auth.** The only public data accessible without
   a token is the app version (`/client/getReloadVersion`) and the static
   config file (`/assets/configs/application.json`). All real traffic data
   (events, cameras, travel times) requires a registered account.

2. **Camera stream URLs are ephemeral.** HLS tokens and TrafficLand URLs expire
   (typically within 300–3600 seconds) and must be refreshed by calling their
   respective token endpoints.

3. **No public RSS/GeoJSON feed found.** The 511NJ system does not expose a
   public GeoJSON or RSS data feed from the API. The admin RSS menu system
   (`/admin/developersettings/rssmenu/`) manages internal feeds.

4. **Request body encryption is not a security boundary.** The AES key and IV
   are embedded in the public JS bundle. Encrypted endpoints still require a
   valid Bearer token; the encryption is an additional obfuscation layer only.

5. **Admin camera listing requires elevated role.** The full camera database
   (`/admin/manage/admincctvcamere/getGridData`) requires an administrator
   account. Viewer-role tokens return 401/403.

6. **NJ Turnpike cameras use TrafficLand.** The signed URL system (TL_Image)
   requires the 511NJ server as an intermediary. Direct access to TrafficLand
   URLs without the signed token will be rejected.

7. **Thruway API v1 is IP-restricted.** `/api/v1/CCTV/getThruwayStatus` returns
   HTTP 403 from external IPs; it appears to be restricted to the Azure VNet.

---

## Appendix: All Discovered API Paths

```
# Public
GET  /client/getReloadVersion
GET  /assets/configs/application.json
GET  /assets/configs/HLSCamera/Hls_Player.html
GET  /assets/configs/HLSCamera/Hls_Player_homepage.html
GET  /assets/scripts/Hls_Player.js

# Authenticated (user-level token)
POST /account/login
POST /account/signup
POST /account/signup/enableUser
POST /account/signup/enableUserNumber
POST /account/signup/removePhoneNumber
POST /account/generateCode
POST /account/generateEmailCode
POST /account/generateSmsCode
POST /account/generateSmsOtp
POST /account/generateSmsPhoneNumberOtp
POST /account/verifyOtp
POST /account/verifyEmailOtp
POST /account/verifySmsOtp
POST /account/verifySmsCode
POST /account/verifySmsNumberOtp
POST /account/verifySmsNumberOtp
POST /account/verifyEmailForAccount
POST /account/changePassword
POST /account/updateEmail
POST /account/deleteAccountUser
POST /account/getUserInfo
POST /account/user/getUser
GET  /client/getReloadVersion
POST /client/appsetting/get
POST /client/basemap/get
POST /client/get/event
POST /client/category/get
POST /client/get/getEventPopupData
POST /client/getStateBoundary
POST /client/getTripGeom
POST /client/getAirportRegion
POST /client/travellink/getLinks
POST /client/weatherwidget/getWidgetData
POST /client/dashboard/getDefaultConfiguration
POST /client/trafficMap/getHlsToken
POST /client/camera/insertCameraErrorLog
POST /client/twitter/getLovData
POST /client/twitter/getTwitterGroups
GET  /master/camera/getTrafficlaneFullURL
GET  /CCTV/getThruwayStatus
GET  /api/v1/CCTV/getThruwayStatus
GET  /TrafficLand/getImageFromUrl

# Admin-only
POST /admin/roleMenuMapping/getMenuData
POST /admin/roleMenuMapping/update
POST /admin/roles/getGridData
POST /admin/roles/insert
POST /admin/roles/update
POST /admin/userRole/getGridData
POST /admin/userRole/getOrganization
POST /admin/userRole/update
POST /admin/appsetting/insert
POST /admin/appsetting/update
POST /admin/appsetting/delete
POST /admin/appsetting/syncdata
POST /admin/manage/admincctvcamere/getGridData
POST /admin/manage/admincctvcamere/savecameradata
POST /admin/manage/admincctvcamere/generateCCTVReport
POST /admin/manage/sectortripmapping/getGridData
POST /admin/manage/sectortripmapping/getAddMode
POST /admin/manage/sectortripmapping/getEditMode
POST /admin/manage/sectortripmapping/save
POST /admin/manage/sectortripmapping/delete
POST /admin/manage/travellink/getForGrid
POST /admin/manage/travellink/getForAdd
POST /admin/manage/travellink/getForEdit
POST /admin/manage/travellink/insert
POST /admin/manage/travellink/update
POST /admin/manage/travellink/delete
POST /admin/manage/alert/getGridData
POST /admin/manage/alert/getEditMode
POST /admin/manage/alert/save
POST /admin/manage/alert/delete
POST /admin/manage/alert/setOrder
POST /admin/manage/alert/setSeverityAlertOrder
POST /admin/manage/alert/getAvailablePriorityForVa
POST /admin/manage/alert/sendEmail
POST /admin/manage/eventtype/getForGrid
POST /admin/manage/eventtype/getForAdd
POST /admin/manage/eventtype/getForEdit
POST /admin/manage/eventtype/insert
POST /admin/manage/eventtype/update
POST /admin/manage/eventtype/delete
POST /admin/manage/floodgate/getGridData
POST /admin/manage/floodgate/getEditMode
POST /admin/manage/floodgate/getForFloodGateType
POST /admin/manage/floodgate/save
POST /admin/manage/floodgate/delete
POST /admin/manage/accountcountymappingroute/getCounty
POST /admin/manage/accountcountymappingroute/insertUpdateCountyAccount
POST /admin/manage/accountfacilitymappingroute/getFacility
POST /admin/manage/accountfacilitymappingroute/insertUpdateFacilityAccount
POST /admin/manage/twitteraccountroute/getActiveUser
POST /admin/manage/twitterlogroute/getLog
POST /admin/megaproject/getRecord
POST /admin/segment/getGridData
POST /admin/segment/getForAdd
POST /admin/segment/getEditMode
POST /admin/segment/insert
POST /admin/segment/update
POST /admin/segment/delete
POST /admin/ptsprofile/profile/getGridData
POST /admin/ptsprofile/profile/getForAdd
POST /admin/ptsprofile/profile/getForEdit
POST /admin/ptsprofile/profile/getPoints
POST /admin/ptsprofile/profile/getRoadway
POST /admin/ptsprofile/profile/insert
POST /admin/ptsprofile/profile/update
POST /admin/ptsprofile/profile/delete
POST /admin/report/getGAReport
POST /admin/report/getCustomEventGAReport
POST /admin/report/getPOIList
POST /admin/report/IVRStatisticReport
POST /admin/report/voiceassistant
POST /admin/tool/closeincident/getGridData
POST /admin/tool/closeincident/manualCloseEvent
POST /admin/tool/usercomment/getGridData
POST /admin/tool/usercomment/delete
POST /admin/tool/usercomment/export
POST /admin/dashboard/admindashboard/getEventStatistics
POST /admin/dashboard/admindashboard/getGeneralStatistics
POST /admin/dashboard/admindashboard/getIVRStatistics
POST /admin/dashboard/admindashboard/getTopRoutes
POST /admin/profilelog/getAllLogs
POST /admin/user/userconfiguration/InsertConfiguration
POST /admin/user/userconfiguration/getTileData
POST /admin/user/userconfiguration/saveTileData
POST /admin/files/createFolder
POST /admin/files/delete
POST /admin/files/getLists
POST /admin/files/getAllData
POST /admin/files/rename
POST /admin/files/uploadFile
POST /admin/files/uploadAudioFile
POST /admin/developersettings/exceptionlog/getForGrid
POST /admin/developersettings/loginuser/getGridData
POST /admin/developersettings/loginuser/inactiveUserNotificationMail
POST /admin/developersettings/rssmenu/getForGrid
POST /admin/developersettings/rssmenu/getForRSSDashboard
POST /admin/developersettings/rssmenu/insert
POST /admin/developersettings/rssmenu/update
POST /admin/developersettings/rssmenu/setOrder
POST /admin/developersettings/webpages/getGridData
POST /admin/developersettings/webpages/getEditMode
POST /admin/developersettings/webpages/save
POST /admin/developersettings/webpages/delete
```

---

*Reverse-engineered 2026-03-27. API endpoints and token requirements subject to change with each 511NJ deployment (version checked: 91).*
