# DOT 511 Unified Traffic Camera Client

Reverse-engineered Python client for 8 US state DOT 511 traffic camera systems.
**No API key required.**

## Supported States

| Code | State         | Platform            | Base URL                              |
|------|--------------|---------------------|---------------------------------------|
| `wi` | Wisconsin    | IBI Group ASP.NET   | https://511wi.gov                     |
| `ny` | New York     | IBI Group ASP.NET   | https://511ny.org                     |
| `pa` | Pennsylvania | IBI Group ASP.NET   | https://www.511pa.com                 |
| `ak` | Alaska       | IBI Group ASP.NET   | https://511.alaska.gov                |
| `ut` | Utah         | IBI Group ASP.NET   | https://udottraffic.utah.gov          |
| `mn` | Minnesota    | Castle Rock CARS    | https://mntg.carsprogram.org          |
| `ia` | Iowa         | Castle Rock CARS    | https://iatg.carsprogram.org          |
| `va` | Virginia     | Iteris TTRIP        | https://511.vdot.virginia.gov         |

---

## Quick Start

```python
from dot_511_client import DOT511Client

client = DOT511Client()

# Get all Wisconsin cameras
cameras = client.get_cameras("wi")
print(len(cameras), "cameras")

# Get cameras with live HLS streams
live = client.get_cameras("mn", with_stream_only=True)
for cam in live[:5]:
    print(cam.primary_stream_url)

# Get traffic incidents
incidents = client.get_events("wi", layer="Incidents")
for evt in incidents[:5]:
    print(evt.roadway, "-", evt.description[:60])

# Get Minnesota road weather stations
stations = client.get_rwis_stations("mn")
```

---

## Platform Details

### Platform 1: IBI Group ASP.NET MVC

States: WI, NY, PA, AK, UT

All IBI states use a cookie-based ASP.NET MVC application. No authentication is needed for
camera listings or event data. The endpoints are:

#### Camera Listing

```
GET {base_url}/Camera/GetUserCameras
```

Response format:
```json
{
  "data": [
    {
      "id": 52,
      "sourceId": "CCTV-40-0042",
      "source": "ATMS",
      "roadway": "I-41/US 45",
      "direction": 0,
      "location": "I-41/US 45 at Capitol Dr",
      "latLng": {
        "geography": {
          "wellKnownText": "POINT (-88.05841 43.088111)"
        }
      },
      "images": [
        {
          "id": 988,
          "cameraSiteId": 52,
          "imageUrl": "/map/Cctv/988",
          "videoUrl": "https://cctv1.dot.wi.gov:443/rtplive/CCTV-40-0042/playlist.m3u8",
          "videoType": "application/x-mpegURL"
        }
      ]
    }
  ],
  "myCameras": false
}
```

Key fields:
- `id` — camera site ID (use for referencing the camera)
- `sourceId` — source system ID, embedded in HLS URL patterns
- `latLng.geography.wellKnownText` — `POINT (longitude latitude)` format
- `images[].videoUrl` — direct HLS `.m3u8` stream URL
- `images[].imageUrl` — relative path to static JPEG preview (append to base_url)

#### Static Preview Images

```
GET {base_url}/map/Cctv/{imageId}
```

Returns a JPEG snapshot. The `imageId` is the `images[].id` value (not the camera site ID).

#### Traffic Events

```
POST {base_url}/list/GetData/{layerName}
Content-Type: application/x-www-form-urlencoded

draw=1&start=0&length=200
```

Available layer names:
- `Incidents`
- `Construction`
- `Closures`
- `SpecialEvents`
- `IncidentClosures`
- `ConstructionClosures`
- `WeatherClosures`

Response is DataTables JSON format:
```json
{
  "draw": 1,
  "recordsTotal": 47,
  "recordsFiltered": 47,
  "data": [
    {
      "id": "12345",
      "type": "Incident",
      "roadwayName": "I-94",
      "description": "Stalled vehicle on shoulder",
      "direction": "Eastbound",
      "county": "Milwaukee",
      "startDate": "2026-03-27T10:30:00",
      "cameras": [{"id": 52}]
    }
  ]
}
```

#### HLS Stream URL Patterns

| State | Pattern |
|-------|---------|
| WI | `https://cctv1.dot.wi.gov:443/rtplive/{sourceId}/playlist.m3u8` |
| NY | `https://s52.nysdot.skyvdn.com:443/rtplive/{sourceId}/playlist.m3u8` (servers s51-s58) |
| PA | `https://pa-se2.arcadis-ivds.com:8200/chan-{id}/index.m3u8` (auth required) |
| AK | Static images only (RWIS type cameras) |
| UT | Provided in `images[].videoUrl` |

---

### Platform 2: Castle Rock ITS CARS

States: MN, IA

CARS is a RESTful microservices architecture hosted at `{state}tg.carsprogram.org`.
Full OpenAPI/Swagger documentation is available at each service's `/openapi` path.

#### Camera Listing

```
GET https://{state}tg.carsprogram.org/cameras_v1/api/cameras
```

Response format:
```json
[
  {
    "id": 464799,
    "public": true,
    "name": "T.H.5 EB @ Great Plains Blvd",
    "lastUpdated": 1774630598214,
    "location": {
      "fips": 27,
      "latitude": 44.858,
      "longitude": -93.531,
      "routeId": "MN 5",
      "cityReference": "in Chanhassen"
    },
    "cameraOwner": {
      "name": "Iris"
    },
    "views": [
      {
        "name": "T.H.5 EB @ Great Plains Blvd",
        "type": "WMP",
        "url": "https://video.dot.state.mn.us/public/C5013.stream/playlist.m3u8",
        "videoPreviewUrl": "https://public.carsprogram.org/cameras/MN/C5013"
      }
    ]
  }
]
```

Key fields:
- `id` — integer camera ID
- `location.latitude`, `location.longitude` — decimal degrees
- `location.routeId` — highway route identifier
- `views[].url` — HLS `.m3u8` stream URL
- `views[].videoPreviewUrl` — static JPEG preview at `public.carsprogram.org`

#### Static Preview Images

```
https://public.carsprogram.org/cameras/{STATE_CODE}/{cameraId}
```

Example: `https://public.carsprogram.org/cameras/MN/C5013`

#### Traffic Events

```
GET https://{state}tg.carsprogram.org/events_v1/api/eventMapFeaturesAndReports
```

Optional query parameters:
- `bbox=minLon,minLat,maxLon,maxLat` — bounding box filter

Returns GeoJSON FeatureCollection.

#### Road Weather Information System (RWIS)

```
GET https://{state}tg.carsprogram.org/rwis_v1/api/stations
GET https://{state}tg.carsprogram.org/rwis_v1/api/stationReports
```

Station data includes sensor location, route, and current conditions.

#### OpenAPI Documentation

Full machine-readable API specs are available at:
```
https://mntg.carsprogram.org/cameras_v1/openapi
https://mntg.carsprogram.org/events_v1/openapi
https://mntg.carsprogram.org/rwis_v1/openapi
https://iatg.carsprogram.org/cameras_v1/openapi
```

---

### Platform 3: Iteris TTRIP (Virginia)

Virginia uses the Iteris TTRIP platform, an Angular SPA at `https://511.vdot.virginia.gov`.

**Camera data requires authentication.** The Angular frontend calls:
```
POST https://511.vdot.virginia.gov/services/getCamerasArray
```

This Node.js proxy then forwards to:
```
https://data.511-atis-ttrip-prod.iteriscloud.com/
```

The proxy enforces session authentication. Direct API calls without a browser session
receive a 401/403 response.

#### Workaround (Best-Effort)

To use the client with Virginia, obtain session cookies from an active browser session:

1. Open `https://511.vdot.virginia.gov` in your browser
2. Open DevTools -> Application -> Cookies
3. Copy the session cookie values
4. Pass them to the client:

```python
client = DOT511Client(
    session_cookies={
        "ASP.NET_SessionId": "your-session-id",
        ".ASPXAUTH": "your-auth-token",
    }
)
cameras = client.get_cameras("va")
```

#### Config Endpoint (No Auth Required)

```
GET https://511.vdot.virginia.gov/assets/config/config.json
```

Returns:
```json
{
  "NODE_ENDPOINT": "https://511.vdot.virginia.gov/services/",
  "TTRIP_ENDPOINT": "https://data.511-atis-ttrip-prod.iteriscloud.com/"
}
```

---

## API Reference

### `DOT511Client`

```python
client = DOT511Client(
    timeout=30,              # HTTP timeout in seconds
    session_cookies=None,    # Optional dict of cookies (needed for VA)
)
```

### `get_cameras(state, *, roadway=None, direction=None, with_stream_only=False, limit=None)`

Retrieve cameras for a state.

```python
# All cameras
cams = client.get_cameras("wi")

# Cameras with live streams only
live = client.get_cameras("mn", with_stream_only=True)

# Filter by road
i94 = client.get_cameras("wi", roadway="I-94")

# Limit results
first10 = client.get_cameras("ny", limit=10)
```

### `get_camera_by_id(state, camera_id)`

Find a single camera by ID.

```python
cam = client.get_camera_by_id("wi", "52")
print(cam.primary_stream_url)
```

### `get_all_stream_urls(state, with_preview=False)`

Get all stream URLs as a flat list of dicts.

```python
for s in client.get_all_stream_urls("mn"):
    print(s["name"], "->", s["stream_url"])
```

### `get_cameras_near(state, lat, lon, radius_miles=5.0)`

Find cameras within a radius, sorted by distance.

```python
nearby = client.get_cameras_near("wi", 43.0, -88.0, radius_miles=3.0)
for dist_miles, cam in nearby:
    print(f"{dist_miles:.1f}mi - {cam.name}")
```

### `get_events(state, layer=None, page_size=200, bbox=None)`

Retrieve traffic events.

```python
# All incidents in WI
incidents = client.get_events("wi", layer="Incidents")

# All event types in WI
all_events = client.get_events("wi")

# MN events in bounding box (min_lon, min_lat, max_lon, max_lat)
events = client.get_events("mn", bbox=(-94.0, 44.5, -93.0, 45.5))
```

### `get_rwis_stations(state)`

Get road weather stations (MN, IA only).

```python
stations = client.get_rwis_stations("mn")
for s in stations:
    print(s.name, s.latitude, s.longitude)
```

### `get_rwis_reports(state, station_id=None)`

Get road weather sensor readings (MN, IA only).

```python
reports = client.get_rwis_reports("mn")
# or for a single station:
reports = client.get_rwis_reports("mn", station_id="123")
```

### `list_states()`

Return metadata for all supported states.

```python
for s in client.list_states():
    print(s["code"], s["name"], s["platform"])
```

### `get_event_layers(state)`

Return available event layer names for IBI states.

```python
layers = client.get_event_layers("wi")
# -> ['Incidents', 'Construction', 'Closures', 'SpecialEvents', ...]
```

### `DOT511Client.build_preview_url(state, camera_id)`

Build a static preview image URL (CARS states only).

```python
url = DOT511Client.build_preview_url("mn", "C5013")
# -> "https://public.carsprogram.org/cameras/MN/C5013"
```

---

## Camera Object Fields

| Field                | IBI States         | CARS States        | Description                        |
|----------------------|--------------------|--------------------|------------------------------------|
| `camera_id`          | camera site ID     | CARS integer ID    | Unique ID within state             |
| `name`               | location text      | camera name        | Human-readable name                |
| `roadway`            | highway name       | route ID           | Road identifier                    |
| `direction`          | compass bearing    | None               | Direction (IBI: 0-360 degrees)     |
| `location`           | location text      | camera name        | Location description               |
| `latitude`           | from WKT POINT     | direct float       | Decimal degrees                    |
| `longitude`          | from WKT POINT     | direct float       | Decimal degrees                    |
| `source_id`          | sourceId           | extracted from URL | ID used in stream URL patterns     |
| `images`             | CameraImage list   | empty              | IBI image records                  |
| `views`              | empty              | CameraView list    | CARS view records                  |
| `primary_stream_url` | first HLS URL      | first HLS URL      | Convenience property               |
| `stream_urls`        | all HLS URLs       | all HLS URLs       | All stream URLs                    |
| `preview_image_url`  | full image URL     | CDN preview URL    | Static JPEG preview                |
| `has_stream`         | bool               | bool               | True if any HLS URL available      |

---

## CLI Usage

```bash
# List supported states
python dot_511_client.py --list-states

# List cameras in Wisconsin
python dot_511_client.py --state wi --cameras

# List live streams only in New York
python dot_511_client.py --state ny --cameras --streams-only

# Filter by highway
python dot_511_client.py --state wi --cameras --roadway "I-41"

# Get traffic incidents in Wisconsin
python dot_511_client.py --state wi --events --layer Incidents

# Get all event types in Minnesota
python dot_511_client.py --state mn --events

# Get Minnesota RWIS weather stations
python dot_511_client.py --state mn --rwis

# Output JSON
python dot_511_client.py --state mn --cameras --json

# Debug logging
python dot_511_client.py --state wi --cameras -v
```

---

## Dependencies

- Python 3.7+
- `requests` (optional but recommended): `pip install requests`
- Falls back to `urllib` from the standard library if `requests` is not installed

---

## Notes on Specific States

### Wisconsin (WI)
- ~250+ cameras statewide
- HLS streams at `cctv1.dot.wi.gov`
- `direction` field is compass bearing in degrees (0 = North)
- All 7 event layers available

### New York (NY)
- Large deployment; hundreds of cameras
- Multiple streaming servers (`s51` through `s58` on `nysdot.skyvdn.com`)
- The `sourceId` determines which server; the videoUrl in the response specifies the correct server

### Pennsylvania (PA)
- PA streams use `isVideoAuthRequired: true` in some cases
- Stream URLs at `pa-se2.arcadis-ivds.com:8200`
- Some cameras may require separate authentication to play

### Alaska (AK)
- Primarily static roadway/weather cameras (RWIS type)
- Few HLS live streams; most use static image snapshots
- `images[].imageUrl` provides the preview path

### Utah (UT)
- UDOT Traffic portal
- Mix of HLS and static cameras

### Minnesota (MN)
- ~1000+ cameras in the CARS system
- MnDOT and contractor-owned cameras
- RWIS stations available for road weather data
- HLS streams at `video.dot.state.mn.us`

### Iowa (IA)
- Iowa DOT CARS deployment
- Similar structure to Minnesota

### Virginia (VA)
- Iteris TTRIP Angular SPA
- Camera data requires authenticated browser session
- Config endpoint (no auth): `https://511.vdot.virginia.gov/assets/config/config.json`
- Backend: `https://data.511-atis-ttrip-prod.iteriscloud.com/`
- Proxy: `https://511.vdot.virginia.gov/services/`
