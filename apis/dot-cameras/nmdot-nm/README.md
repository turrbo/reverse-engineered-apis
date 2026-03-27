# NMDOT Traffic Camera System — Python Client

Reverse-engineered Python client for the **New Mexico Department of Transportation (NMDOT)** traffic information system at [nmroads.com](https://nmroads.com).

No API key required. No third-party libraries required. Uses Python stdlib only (`urllib`, `json`, `re`, `dataclasses`).

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Endpoints Catalogue](#endpoints-catalogue)
5. [Data Models](#data-models)
6. [Usage Examples](#usage-examples)
7. [Reverse Engineering Notes](#reverse-engineering-notes)
8. [Limitations & Notes](#limitations--notes)

---

## Overview

`nmdot_client.py` provides a clean Python interface to the public-facing NMDOT data services that power [nmroads.com](https://nmroads.com). The system serves:

| Data Type | Count | Notes |
|-----------|-------|-------|
| Traffic cameras | 183 | Real-time JPEG snapshots + RTMP streams |
| Road condition events | 75+ | Live events (closures, crashes, roadwork, weather) |
| Fleet vehicles (snow plows) | 13+ | Real-time GPS positions |
| System splash messages | 1 | System-wide alert banner |

---

## Architecture

The nmroads.com frontend uses two backend services:

```
Browser / Client
       │
       ├─── https://servicev5.nmroads.com/RealMapWAR/    (Java / Apache Tomcat 8.5)
       │         JSONP responses
       │         Camera metadata, events, fleet positions, cached objects
       │
       ├─── https://lambdav5.nmroads.com/                (Node.js Lambda proxy)
       │         Plain JSON responses
       │         Health check, some cached object proxying
       │
       ├─── http://ss.nmroads.com/snapshots/             (Static file server)
       │         Direct JPEG snapshot files
       │
       └─── rtmp://video.nmroads.com/nmroads             (RTMP live streams)
                 Requires VLC or similar RTMP player
```

### JSONP Protocol

The `servicev5` backend exclusively returns JSONP (JSON with padding), wrapping JSON payload in a callback function call:

```
GET /RealMapWAR/GetCameraInfo?callback=myFunc
→  myFunc({"cameraInfo":[...]});
```

The client strips the JSONP wrapper automatically before parsing. The `callback` parameter name is required but the value does not matter.

### Coordinate System

Event coordinates (latitude/longitude fields) are in **EPSG:3857 (Web Mercator)** metres, not WGS-84 degrees. The `TrafficEvent` dataclass provides `.lat_wgs84` and `.lon_wgs84` properties that convert automatically.

---

## API Reference

### `NMDOTClient`

```python
client = NMDOTClient(
    service_base="https://servicev5.nmroads.com/RealMapWAR/",  # default
    lambda_base="https://lambdav5.nmroads.com/",               # default
    timeout=30,                                                 # seconds
)
```

#### Camera Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_cameras()` | `List[Camera]` | All 183+ traffic cameras |
| `get_camera(name)` | `Camera \| None` | Look up a single camera by name |
| `download_camera_image(camera, ts=0)` | `bytes` | JPEG image via RealMapWAR |
| `download_snapshot(camera)` | `bytes` | JPEG image direct from CDN |
| `get_camera_timestamp(camera)` | `datetime \| None` | Last image capture time |
| `search_cameras(query, district, grouping, camera_type, enabled_only)` | `List[Camera]` | Filter cameras |
| `list_groupings()` | `List[str]` | All geographic grouping names |
| `list_camera_types()` | `List[str]` | All camera hardware types |
| `cameras_by_grouping()` | `dict` | `{grouping: [Camera, ...]}` |
| `cameras_by_district()` | `dict` | `{district_id: [Camera, ...]}` |

#### Event Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_events(event_types, return_data)` | `List[TrafficEvent]` | Active road events |
| `get_events_timestamp()` | `int` | Version counter for polling |
| `get_events_by_type(event_type)` | `List[TrafficEvent]` | Single event type |
| `get_closures()` | `List[TrafficEvent]` | Road closures (type 5) |
| `get_crashes()` | `List[TrafficEvent]` | Crashes (type 6) |
| `get_roadwork()` | `List[TrafficEvent]` | Roadwork (type 9) |
| `get_weather_advisories()` | `List[TrafficEvent]` | Weather advisories (type 14) |
| `get_severe_conditions()` | `List[TrafficEvent]` | Severe conditions (type 17) |

#### Fleet / Misc Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_snow_plows()` | `List[SnowPlow]` | GPS positions of all fleet vehicles |
| `get_splash_message()` | `SplashMessage` | System-wide alert banner |
| `get_cached_object(key)` | `Any` | Raw cached object by key |
| `health_check()` | `dict` | Lambda service health |

---

## Endpoints Catalogue

All discovered endpoints, tested against production. Timestamps: March 2026.

### servicev5.nmroads.com/RealMapWAR/

| Endpoint | Method | Params | Auth | Status | Response |
|----------|--------|--------|------|--------|----------|
| `GetCameraInfo` | GET | `callback` | None | ✅ Live | JSONP — camera metadata list |
| `GetCameraImage` | GET | `cameraName`, `ts`, `callback` | None | ✅ Live | JPEG binary |
| `GetEventsJSON` | GET | `eventType`, `returnData`, `callback` | None | ✅ Live | JSONP — events array |
| `GetEventsTimestamp` | GET | `callback` | None | ✅ Live | JSONP — `{"result": <int>}` |
| `GetCachedObject` | GET | `key`, `callback` | None | ✅ Live | JSONP — varies by key |
| `GetSplashMessage` | GET | `callback` | None | ✅ Live | JSONP — splash object |
| `GetMessageSigns` | GET | `callback` | None | ⚠️ 500 | Server error (messageSigns null) |
| `GetMessageSignsJSON` | GET | `callback` | None | ❌ 404 | Not found |
| `GetCamerasJSON` | GET | `callback` | None | ❌ 404 | Not found |
| `UpdateTimestamps` | GET | — | Admin | Admin-only | |
| `AddEvent` | POST | — | Admin | Admin-only | |
| `UpdateEvent` | POST | — | Admin | Admin-only | |
| `RefreshAuthToken` | GET | — | Admin | Admin-only | |
| `AddMember` | POST | — | — | Member portal | |
| `AuthenticateMember` | POST | — | — | Member portal | |

### lambdav5.nmroads.com/

| Endpoint | Method | Params | Auth | Status | Response |
|----------|--------|--------|------|--------|----------|
| `Health` | GET | — | None | ✅ Live | JSON — `{"status":"ok",...}` |
| `getEvents` | GET | — | None | ⚠️ DB error | Handshake timeout (backend DB issue) |
| `getCachedObject` | GET | `key` | None | ✅ Live | JSON — `{"status":"ok","data":{"data":...}}` |
| `getCachedImage` | GET | `key` | None | Not tested | JSON — `{"data":{"data":"<base64>"}}` |
| `translateTextEnToEs` | POST | `textToTranslate` | None | Not tested | Translation service |
| `getRouteNow` | GET | — | Not tested | Route guidance |
| `getControllerEvents` | GET | `signalID`,`fromDate`,`toDate` | Not tested | Signal controller |
| `getDeviceLocation` | GET | `deviceID` | Not tested | Device tracking |
| `getConstructionProjects` | GET | — | Not tested | Construction |
| `getSignalData` | GET | — | Not tested | Traffic signals |
| `requestPasswordRecovery` | POST | — | Member | Password reset |

### ss.nmroads.com/snapshots/

Direct-access JPEG snapshot files named by stream filename:
```
http://ss.nmroads.com/snapshots/<sdpFileHighRes_stem>.jpg
```
Example: `http://ss.nmroads.com/snapshots/i25_lowerlabajada.jpg`

- No authentication required
- Images are 320×240 or 360×240 JPEG
- Updated approximately every 30 seconds

### RTMP Video Streams

```
rtmp://video.nmroads.com/nmroads/<sdpFileHighRes>
```
Requires an RTMP-capable client (VLC, FFmpeg, etc.)

---

## Data Models

### `Camera`

```python
@dataclass
class Camera:
    name: str              # Unique identifier e.g. "I-25@La_Bajada_Lower"
    title: str             # Human-readable e.g. "I-25 @ Lower La Bajada"
    lat: float             # WGS-84 latitude (native in camera objects)
    lon: float             # WGS-84 longitude
    grouping: str          # Geographic grouping
    district: int          # NMDOT district (0-6)
    camera_type: str       # "iDome" | "Pelco Spectra" | "RWIS2" | ""
    enabled: bool
    stream: bool           # RTMP stream available
    mobile: bool
    sort_order: int        # Display ordering hint
    snapshot_file: str     # Direct CDN URL to JPEG
    sdp_file_high_res: str # RTMP stream name
    resolution: str        # "D1" etc.
    message: str           # Optional operator message
```

**Computed properties:**
- `snapshot_url` → direct JPEG URL
- `stream_url` → full RTMP URL
- `is_rwis` → True if Road Weather Information System camera
- `image_url(ts=0)` → RealMapWAR image URL

### `TrafficEvent`

```python
@dataclass
class TrafficEvent:
    guid: str
    event_type: int        # See EVENT_TYPES dict
    title: str
    description: str
    route_name: str        # "I", "US", "NM"
    route_number: str      # "25", "40", "380"
    district: int
    county_name: str
    latitude: float        # Web Mercator Y (EPSG:3857)
    longitude: float       # Web Mercator X (EPSG:3857)
    geometry_type: str     # "point" | "polyline"
    entered_date: str
    update_date: str
    expiration_date: str
```

**Computed properties:**
- `event_type_name` → human-readable string
- `lat_wgs84` → converted to WGS-84 degrees
- `lon_wgs84` → converted to WGS-84 degrees

### `SnowPlow`

```python
@dataclass
class SnowPlow:
    device_id: str         # e.g. "b7", "bF7"
    latitude: float        # WGS-84
    longitude: float       # WGS-84
    bearing: int           # Degrees (0-360)
    speed: float           # km/h
    is_driving: bool
    is_communicating: bool
    date_time: str         # ISO 8601 UTC
    duration: str          # "HH:MM:SS" since last state change
    groups: List[str]      # e.g. ["GroupVehicleId", "GroupDieselId"]
```

### Event Types

| ID | Name |
|----|------|
| 5 | Closure |
| 6 | Crash |
| 7 | Alert |
| 8 | Lane Closure |
| 9 | Roadwork |
| 13 | Fair Driving Conditions |
| 14 | Weather Advisory |
| 16 | Difficult Driving Conditions |
| 17 | Severe Driving Conditions |
| 18 | Special Event |
| 19 | Construction Closure |
| 20 | Seasonal Closure |
| 21 | Traffic Signal Power Failure |

### Districts

| ID | Description |
|----|-------------|
| 0 | Statewide |
| 1 | District 1 (Gallup) |
| 2 | District 2 (Las Cruces) |
| 3 | District 3 (Albuquerque) |
| 4 | District 4 (Tucumcari) |
| 5 | District 5 (Santa Fe) |
| 6 | District 6 (Alamogordo) |

### Geographic Groupings

- Albuquerque Area
- Continental Divide
- Gallup
- I-10 Corridor
- Las Cruces
- Santa Fe Area
- Statewide

---

## Usage Examples

### Basic — list cameras

```python
from nmdot_client import NMDOTClient

client = NMDOTClient()
cameras = client.get_cameras()
print(f"{len(cameras)} cameras available")

for cam in cameras[:5]:
    print(f"  {cam.title:40s}  {cam.camera_type}")
```

### Download a camera snapshot

```python
from nmdot_client import NMDOTClient

client = NMDOTClient()
cam = client.get_camera("I-25@La_Bajada_Lower")

if cam:
    # Method 1: via RealMapWAR service
    img_bytes = client.download_camera_image(cam)
    with open("snapshot.jpg", "wb") as f:
        f.write(img_bytes)

    # Method 2: direct from CDN (faster)
    img_bytes = client.download_snapshot(cam)

    # Get timestamp of last capture
    ts = client.get_camera_timestamp(cam)
    print(f"Image captured at: {ts}")
```

### Fetch and print road conditions

```python
from nmdot_client import NMDOTClient

client = NMDOTClient()
events = client.get_events()

for evt in events:
    print(f"[{evt.event_type_name}] {evt.title}")
    print(f"  Route: {evt.route_name} {evt.route_number}, District {evt.district}")
    print(f"  WGS84: {evt.lat_wgs84:.4f}, {evt.lon_wgs84:.4f}")
    print()
```

### Poll for new events (change detection)

```python
import time
from nmdot_client import NMDOTClient

client = NMDOTClient()
last_ts = client.get_events_timestamp()

while True:
    time.sleep(30)
    ts = client.get_events_timestamp()
    if ts != last_ts:
        print(f"Events updated (was {last_ts}, now {ts})")
        last_ts = ts
        events = client.get_events()
        # process updated events...
```

### Filter cameras by area

```python
from nmdot_client import NMDOTClient

client = NMDOTClient()

# By geographic grouping
abq_cameras = client.search_cameras(grouping="Albuquerque Area")
print(f"Albuquerque cameras: {len(abq_cameras)}")

# By route name
i25_cameras = client.search_cameras(query="I-25")
print(f"I-25 cameras: {len(i25_cameras)}")

# By district
sf_cameras = client.search_cameras(district=5)
print(f"District 5 (Santa Fe) cameras: {len(sf_cameras)}")

# RWIS only
rwis = client.search_cameras(camera_type="RWIS2")
print(f"RWIS cameras: {len(rwis)}")
```

### Snow plow tracking

```python
from nmdot_client import NMDOTClient

client = NMDOTClient()
plows = client.get_snow_plows()

active = [p for p in plows if p.is_driving]
print(f"{len(active)} vehicles currently moving out of {len(plows)} total")

for plow in active:
    print(f"  {plow.device_id}: {plow.speed:.0f} km/h at {plow.latitude:.4f}, {plow.longitude:.4f}")
```

### Save all camera snapshots to disk

```python
import os
from nmdot_client import NMDOTClient

client = NMDOTClient()
cameras = client.get_cameras()
os.makedirs("snapshots", exist_ok=True)

for cam in cameras:
    if not cam.enabled:
        continue
    try:
        img = client.download_snapshot(cam)
        with open(f"snapshots/{cam.name}.jpg", "wb") as f:
            f.write(img)
        print(f"  Saved {cam.name}")
    except Exception as e:
        print(f"  Failed {cam.name}: {e}")
```

### Get events as GeoJSON-compatible dicts

```python
from nmdot_client import NMDOTClient, EVENT_TYPES

client = NMDOTClient()
events = client.get_events()

features = []
for evt in events:
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [evt.lon_wgs84, evt.lat_wgs84]
        },
        "properties": {
            "guid": evt.guid,
            "type": evt.event_type_name,
            "title": evt.title,
            "route": f"{evt.route_name} {evt.route_number}",
            "district": evt.district,
            "updated": evt.update_date,
        }
    })

geojson = {"type": "FeatureCollection", "features": features}
```

---

## Reverse Engineering Notes

### Discovery process

1. **Entry point**: `https://nmroads.com/` redirects to `/default.html?v=...`
2. **JS analysis**: The page loads several key JS files:
   - `js/common.js` — environment configuration, base URLs
   - `js/main.js` — ArcGIS map initialization, camera popup code
   - `js/eventsPublic.js` — all public data-fetch functions

3. **URL discovery**: `common.js` explicitly sets environment variables:
   ```javascript
   serviceUrl = "https://lambdav5.nmroads.com/"
   serviceV4Url = "https://servicev5.nmroads.com/RealMapWAR/"
   ```

4. **JSONP pattern**: All calls to `serviceV4Url` use `$.ajax({ dataType: "jsonp" })`.

5. **Camera image URL** was found in `eventsPublic.js`:
   ```javascript
   html = "<img ... src='https://servicev5.nmroads.com/RealMapWAR/GetCameraImage?ts=0&cameraName=" + cameraName + "'/>"
   ```

6. **Snapshot CDN** found in camera metadata itself (`snapshotFile` field).

7. **Snow plows**: Uses the generic `GetCachedObject?key=snowPlowLocations` endpoint.

8. **Camera timestamps**: Uses `GetCachedObject?key=<cameraName>Time`, returns Unix milliseconds.

### JS files and their roles

| File | Role |
|------|------|
| `common.js` | Environment/URL config, splash message, event fetching |
| `main.js` | ArcGIS map, camera display, popup construction |
| `eventsPublic.js` | All data-fetch functions (getEvents, getCameras, getSnowPlows, etc.) |
| `main2.js` | UI interaction handlers (nav clicks, checkbox toggles) |
| `weatherHelper.js` | NOAA weather API integration, weather popup HTML |
| `eventsAdmin.js` | Admin-only CRUD operations (requires auth token) |
| `memberSubscriptions.js` | User account / alert subscriptions |
| `constructionProjects.js` | Construction project overlays |
| `transit.js` | ABQ bus tracking (abqroads.com only) |

### Authentication

All public endpoints require no authentication. Admin endpoints (Add/Update events, manage users) require:
- A `serviceV4AuthTokenGUID` obtained from `serviceUrl + "getserviceV4AuthToken"` via the Lambda proxy
- Login via `AuthenticateMember` (JSONP, admin credentials)

The admin token is stored in `localStorage` under key `NMRoadsAdminUser`.

### Other deployment environments

The same codebase serves multiple sites, identified by hostname:

| Domain | Site | Notes |
|--------|------|-------|
| nmroads.com | NMDOT statewide | Primary public site |
| abqroads.com | City of ABQ | District 3 focus + ABQ bus tracking |
| zuniroad.com | Zuni Pueblo roads | Smaller footprint |
| test.nmroads.com | QA environment | Points to test backends |

---

## Limitations & Notes

1. **RTMP streams** require a compatible player (VLC, FFmpeg). They cannot be played in a standard browser without a plugin. HLS/DASH equivalents were not found.

2. **GetMessageSigns** returns HTTP 500 — the server-side message signs collection appears to be null/disabled on the public endpoint. The admin endpoint may work with credentials.

3. **Coordinate system**: Event lat/lon in `GetEventsJSON` are Web Mercator (EPSG:3857) metres, not degrees. Camera lat/lon are in WGS-84 degrees (native). Use the `lat_wgs84` / `lon_wgs84` properties on `TrafficEvent` for consistent coordinates.

4. **Rate limiting**: No rate-limiting was observed, but be considerate — this is a public safety system. Avoid polling more frequently than once per 30 seconds for events.

5. **Image refresh rate**: Snapshots update approximately every 30 seconds based on the `GetCachedObject` timestamps observed.

6. **No HTTPS for snapshots**: The CDN at `ss.nmroads.com` uses HTTP (not HTTPS). Images from `GetCameraImage` are served over HTTPS via the RealMapWAR proxy.

7. **Snow plow data**: Some vehicle IDs (e.g., `b9999999`) appear to be test/dummy entries injected by the backend.

8. **Geometry returnData**: When `returnData=geometry`, the events list returns raw dicts with `geometryAsJSON` (Esri JSON polylines in EPSG:3857). These require conversion to use with standard geo libraries.
