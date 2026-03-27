# FL511 Florida Traffic Camera & Events Client

Reverse-engineered Python client for the Florida Department of Transportation (FDOT)
**FL511** real-time traffic information system at https://fl511.com.

**No API key required.** All endpoints are publicly accessible without registration.

---

## Overview

FL511 is Florida's official 511 traffic information portal, operated on behalf of FDOT
by the **IBI Group** ASP.NET MVC platform (the same platform powering 511wi.gov, 511ny.org,
511pa.com, and others). Camera feeds are powered by the **DIVAS** (Digital Integrated
Video Archiving System) platform operated by TransCore.

This client provides access to:

- **4,700+ traffic cameras** statewide with live JPEG snapshots
- **Traffic events**: incidents, construction, closures, congestion, disabled vehicles
- **Dynamic Message Signs (DMS)**: 1,100+ highway message signs with current content
- **Drawbridge status**: 18 monitored drawbridges in real time
- **Truck parking availability**: 69 FDOT-monitored facilities with space counts
- **Weather alerts**: NWS alerts and forecast zones via the FL511 weather layer
- **Traffic speed tiles**: XYZ map tiles for real-time speed overlays
- **FDOT ArcGIS open data**: Emergency detour route GeoJSON

---

## Discovered API Endpoints

All endpoints are on `https://fl511.com`. A session cookie is required (obtained
automatically by visiting the homepage).

### Session Initialization

```
GET https://fl511.com
```

Sets the `session-id` cookie. All subsequent API calls must include this cookie.
The session is unauthenticated (no login required).

---

### Camera Endpoints

#### All Camera Locations (fast, 4,700+ cameras)

```
GET /map/mapIcons/Cameras
X-Requested-With: XMLHttpRequest
```

Returns all cameras with GPS coordinates and video-enabled status.
Response is gzip-compressed JSON.

**Response:**
```json
{
  "item1": {
    "url": "/Generated/Content/Images/511/map_cameraStreams.svg",
    "size": [29, 35],
    "zindex": 1
  },
  "item2": [
    {
      "itemId": "1",
      "location": [26.17325, -80.892882],
      "icon": {"url": "/Generated/Content/Images/511/map_cameraStreams.svg"},
      "expando": {"videoEnabled": true},
      "title": ""
    }
  ]
}
```

Key fields:
- `itemId` — camera site ID (string, use as integer for detail requests)
- `location` — `[latitude, longitude]` decimal degrees
- `expando.videoEnabled` — `true` if an HLS video stream is available

---

#### Camera Full Detail

```
GET /map/data/Cameras/{id}
X-Requested-With: XMLHttpRequest
```

Returns complete camera record including image URL, video stream URL, roadway, GPS.

**Response:**
```json
{
  "id": 1,
  "sourceId": "1",
  "source": "DIVAS-District 1",
  "areaId": "COLL",
  "roadway": "I-75",
  "direction": 1,
  "location": "0517N_75_Alligator_Alley_M052",
  "latLng": {
    "geography": {
      "coordinateSystemId": 4326,
      "wellKnownText": "POINT (-80.892882 26.17325)"
    }
  },
  "images": [
    {
      "id": 1,
      "cameraSiteId": 1,
      "description": "0517N_75_Alligator_Alley_M052",
      "imageUrl": "/map/Cctv/1",
      "videoUrl": "https://dis-se18.divas.cloud:8200/chan-1_h/index.m3u8",
      "videoType": "application/x-mpegURL",
      "isVideoAuthRequired": true,
      "videoDisabled": false,
      "disabled": false,
      "blocked": false
    }
  ]
}
```

Key fields:
- `id` — camera site ID
- `sourceId` — DIVAS channel ID (embedded in HLS URL)
- `source` — managing agency (e.g. `DIVAS-District 1`, `DIVAS-CFX`, `DIVAS-BCTD`)
- `areaId` — county/area code (see Area Codes section)
- `direction` — `1`=N, `2`=E, `3`=S, `4`=W
- `latLng.geography.wellKnownText` — `POINT (longitude latitude)` format
- `images[].imageUrl` — relative path; append to base URL for JPEG snapshot
- `images[].videoUrl` — HLS `.m3u8` stream URL (requires DIVAS auth)

---

#### Cameras by Area/County

```
GET /Camera/GetUserCameras?areaId={area_code}
X-Requested-With: XMLHttpRequest
```

Returns cameras filtered by county area code. Returns full detail including image URLs.

See **Area Codes** section for valid `areaId` values.

---

#### Live JPEG Camera Snapshot

```
GET /map/Cctv/{camera_id}
```

Returns a live JPEG snapshot image. **No session cookie required.** Images are
640×480 pixels, refreshed every few seconds.

Example: `https://fl511.com/map/Cctv/1`

---

### Event Endpoints

#### Get Events List (POST, DataTables format)

```
POST /list/GetData/{layer}
Content-Type: application/x-www-form-urlencoded

draw=1&start=0&length=1000
```

Returns paginated event data for the specified layer.

**Available layers:**

| Layer | Description | Typical Count |
|-------|-------------|---------------|
| `Incidents` | Traffic incidents, crashes, access restrictions | 20–100 |
| `Construction` | Active construction zones | 50–200 |
| `Closures` | Road closures | 5–30 |
| `SpecialEvents` | Planned special events | 0–20 |
| `Congestion` | Traffic queues / congestion points | 50–200 |
| `DisabledVehicles` | Stalled / disabled vehicles | 10–50 |
| `RoadConditionIncident` | Road condition incidents | 0–10 |
| `MessageSigns` | Dynamic message sign (DMS) content | ~1,145 |
| `Bridge` | Drawbridge open/close status | 18 |
| `Parking` | Truck parking availability | 69 |
| `RailCrossing` | Railroad crossing status | 20 |
| `WeatherIncidents` | Weather-related incidents | varies |

**Response (DataTables format):**
```json
{
  "draw": 1,
  "recordsTotal": 21,
  "recordsFiltered": 21,
  "data": [
    {
      "DT_RowId": "389236",
      "id": 389236,
      "tooltipUrl": "/tooltip/Incidents/389236?lang={lang}&noCss=true",
      "type": "Incidents",
      "layerName": "Incidents",
      "roadwayName": "SR-31",
      "description": "Access Restricted on SR-31 Northbound...",
      "sourceId": "7422",
      "source": "ERS",
      "comment": "North Fort Myers: Commercial Truck traffic...",
      "eventSubType": "Access Restricted",
      "startDate": "11/25/25, 10:17 AM",
      "endDate": null,
      "lastUpdated": "2/11/26, 2:49 PM",
      "isFullClosure": false,
      "severity": "Minor",
      "direction": "Northbound",
      "locationDescription": "Wilson Pigott Bridge",
      "laneDescription": "",
      "county": "Lee",
      "dotDistrict": "District 1",
      "region": "Southwest",
      "state": "Florida",
      "showOnMap": true
    }
  ]
}
```

**Pagination:** Use `start` + `length` parameters. Server supports `length` up to 1000+ records in a single request, covering all current FL511 data.

---

#### Event Full Detail

```
GET /map/data/{layer}/{id}
X-Requested-With: XMLHttpRequest
```

Returns the complete event record with additional fields not in the list endpoint:

- `latitude` / `longitude` — decimal degree coordinates
- `latLng.geography.wellKnownText` — WKT point string
- `detourPolyline` — Google-encoded polyline for the detour route
- `lanes` — JSON array of lane status objects
- `recurrence` — JSON recurrence schedule (construction only)
- `cameraIds` — nearby camera IDs
- `area.parentArea_AreaId` — FDOT district ID (e.g. `FL-D01`)

---

#### Map Icon Positions (All Features)

```
GET /map/mapIcons/{layer}
X-Requested-With: XMLHttpRequest
```

Returns lat/lon positions of all features on the map for a given layer.
Response may be gzip-compressed.

**Response:**
```json
{
  "item1": {
    "url": "/Generated/Content/Images/511/map_construction.svg",
    "size": [29, 35],
    "anchor": [14, 34],
    "zindex": 25,
    "isClickable": true
  },
  "item2": [
    {
      "itemId": "10",
      "location": [28.278, -81.343],
      "icon": {},
      "title": ""
    }
  ]
}
```

---

#### Tooltip HTML (Event Detail Card)

```
GET /tooltip/{layer}/{id}?lang=en&noCss=true
```

Returns an HTML fragment with the formatted tooltip card for any map feature.
This is what the FL511 web map shows when you click a map icon.

Valid `{layer}` values: `Cameras`, `Incidents`, `Construction`, `Closures`,
`SpecialEvents`, `Congestion`, `DisabledVehicles`, `MessageSigns`, `Bridge`,
`Parking`, `RailCrossing`, `WeatherEvents`, `WeatherForecast`.

---

### Weather Endpoints

#### Weather Alerts (NWS)

```
GET /map/mapIcons/WeatherEvents
```

Returns positions of active NWS weather alerts. Use tooltip endpoint for alert text.

#### Weather Forecast Zones (NWS)

```
GET /map/mapIcons/WeatherForecast
```

Returns NWS forecast zone centroids. Zone IDs are NWS zone codes (e.g. `FLZ010`).

#### Weather Radar Tiles

```
GET /map/weatherRadar/{x}/{y}/{z}
GET /map/weatherRadar/{x}/{y}/{z}?frame={n}
```

NEXRAD weather radar tiles in XYZ/TMS format. `frame` parameter (0–12) selects
the animation frame for radar loop playback.

---

### Traffic Speed Tiles

```
GET https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
```

XYZ map tiles showing real-time traffic speeds as color-coded road overlays:
- Green: free flow
- Yellow: moderate congestion
- Red: heavy congestion / stop-and-go

Zoom range: 7–16.

---

### ArcGIS Open Data (FDOT Public Feature Services)

FDOT publishes 1,400+ public datasets via ArcGIS Online:

```
https://services1.arcgis.com/O1JpcwDW8sjYuddV/ArcGIS/rest/services/
```

#### Emergency Detour Routes (GeoJSON)

```
GET https://services1.arcgis.com/O1JpcwDW8sjYuddV/ArcGIS/rest/services/
    FDOT_Emergency_Detour_Routes_Public_View/FeatureServer/0/query
    ?where=Detour='Detour'&outSR=4326&f=pgeojson&returnExceededLimitFeatures=true
```

Returns GeoJSON `FeatureCollection` of Emergency Roadway System (ERS) detour
routes. Used by FL511 for the ERS Detours layer.

Change `where=Detour='Closed'` to get closed route segments.

---

## Video Streaming

FDOT camera video streams use the **DIVAS** platform by TransCore.

**HLS Stream URL pattern:**
```
https://dis-se{N}.divas.cloud:8200/chan-{sourceId}_h/index.m3u8
```

Where:
- `{N}` is a DIVAS server number (1–30+), derived from the `videoUrl` field in the camera response
- `{sourceId}` is the DIVAS channel ID from the camera's `sourceId` field

**Authentication:** DIVAS streams return `HTTP 401` for direct access. A valid DIVAS
portal session (obtained from the FL511 web player) is required.

**Workaround:** Use the `/map/Cctv/{id}` JPEG snapshot endpoint instead — it is
freely accessible without any authentication and provides a near-live still image.

---

## Area Codes

The `areaId` field identifies county-level areas. Known codes:

| Code | Area | FDOT District |
|------|------|---------------|
| `ALA` | Alachua County | District 2 |
| `BC` | Broward County (BCTD) | District 4 |
| `BRE` | Brevard County | District 5 |
| `CIT` | Citrus County | District 5 / Turnpike |
| `CLA` | Clay County | District 2 |
| `COLL` | Collier County | District 1 |
| `COLU` | Columbia County | District 2 |
| `DUV` | Duval County (Jacksonville) | District 2 |
| `ESC` | Escambia County (Pensacola) | District 3 |
| `FLA` | Flagler County | District 5 |
| `GAD` | Gadsden County | District 3 |
| `HAM` | Hamilton County | District 2 |
| `HIL` | Hillsborough County (Tampa) | District 7 |
| `HLS` | Hillsborough / HART (District 6 sub-area) | District 6 |
| `IR` | Indian River County | District 4 / Turnpike |
| `JAC` | Jackson County | District 3 |
| `JEF` | Jefferson County | District 3 |
| `LEE` | Lee County (Fort Myers) | District 1 |
| `LEO` | Leon County (Tallahassee) | District 3 |
| `MAD` | Madison County | District 2 |
| `MAN` | Manatee County | District 7 |
| `MAR` | Martin County | District 4 / Turnpike |
| `MARI` | Marion County (Ocala) | District 5 |
| `MC` | Monroe County (Florida Keys) | District 6 |
| `MDC` | Miami-Dade County | District 6 |
| `NAS` | Nassau County | District 2 |
| `OKA` | Okaloosa County (Destin/Ft Walton) | District 3 |
| `ORA` | Orange County / CFX (Orlando) | District 5 / CFX |
| `OSC` | Osceola County (Kissimmee) | District 5 |
| `PAS` | Pasco County | District 7 |
| `PBC` | Palm Beach County | District 4 |
| `PALM` | Palm Beach County (alt) | District 4 |
| `PIN` | Pinellas County (St. Petersburg) | District 7 |
| `POL` | Polk County (Lakeland) | District 1 |
| `SAR` | Sarasota County | District 1 |
| `SEM` | Seminole County | District 5 / Turnpike |
| `SJO` | St. Johns County | District 2 |
| `SUM` | Sumter County | District 5 / Turnpike |
| `SUW` | Suwannee County | District 2 |
| `VOL` | Volusia County (Daytona Beach) | District 5 |
| `WAL` | Walton County | District 3 |
| `WAS` | Washington County | District 3 |

---

## FDOT Districts

| District | Region | Major Areas |
|----------|--------|-------------|
| District 1 | Southwest | Sarasota, Lee, Collier, Charlotte, Polk, Highlands |
| District 2 | Northeast | Jacksonville, Gainesville, Tallahassee surrounds |
| District 3 | Panhandle / Northwest | Pensacola, Tallahassee, Panama City |
| District 4 | Southeast | Palm Beach, Broward (Fort Lauderdale), Treasure Coast |
| District 5 | Central | Orlando, Daytona Beach, Space Coast, Ocala |
| District 6 | Southeast Extreme | Miami-Dade, Monroe (Keys) |
| District 7 | Tampa Bay | Tampa, St. Petersburg, Clearwater, Sarasota, New Port Richey |

---

## Source Systems

The `source` field on cameras identifies the managing agency:

| Source | Description |
|--------|-------------|
| `DIVAS-District 1` | FDOT District 1 cameras |
| `DIVAS-District 2` | FDOT District 2 cameras |
| `DIVAS-District 3-CHP` | FDOT District 3 (Panhandle) cameras |
| `DIVAS-District 4` | FDOT District 4 cameras |
| `DIVAS-District 5` | FDOT District 5 cameras |
| `DIVAS-District 6` | FDOT District 6 cameras |
| `DIVAS-District 7` | FDOT District 7 cameras |
| `DIVAS-CFX` | Central Florida Expressway Authority |
| `DIVAS-BCTD` | Broward County Transit Division |
| `DIVAS-COT` | City of Tallahassee |
| `DIVAS-MDX` | Miami-Dade Expressway Authority |
| `DIVAS-Turnpike SG C` | Florida's Turnpike Enterprise |
| `DIVAS-District I595` | I-595 Express Lanes |

---

## Quick Start

```python
from fl511_client import FL511Client

client = FL511Client()

# Get all ~4,700 cameras statewide (location data only, one fast request)
cameras = client.get_all_cameras()
print(f"{len(cameras)} cameras total")
print(f"{sum(1 for c in cameras if c.video_enabled)} with video streams")

# Get full camera detail (location + snapshot URL + HLS stream URL)
cam = client.get_camera_detail(1)
print(cam.roadway, cam.location)
print("Snapshot:", cam.snapshot_url)
print("HLS stream:", cam.stream_url)  # requires DIVAS auth

# Download a live JPEG snapshot (no auth required)
jpeg_bytes = client.get_snapshot(1)
with open("i75_alligator_alley.jpg", "wb") as f:
    f.write(jpeg_bytes)

# Cameras by county
miami_cameras = client.get_cameras_by_area("MDC")   # Miami-Dade
tampa_cameras = client.get_cameras_by_area("HIL")   # Hillsborough / Tampa
orlando_cameras = client.get_cameras_by_area("ORA") # Orange / CFX

# Cameras near a GPS coordinate (Tampa Intl Airport)
nearby = client.get_cameras_near(27.975, -82.533, radius_miles=3.0)
for dist, cam in nearby:
    print(f"{dist:.1f}mi: {cam.roadway} - {cam.location}")

# Traffic events
incidents = client.get_events("Incidents")
for inc in incidents:
    print(f"[{inc.severity}] {inc.roadway} {inc.direction} | {inc.county}")
    print(f"  {inc.description[:80]}")

# Construction zones
construction = client.get_events("Construction")

# Congestion / queues
congestion = client.get_events("Congestion")

# Drawbridge status
bridges = client.get_events("Bridge")
open_bridges = [b for b in bridges if b.is_open_to_boats]
print(f"{len(open_bridges)} bridges currently raised for marine traffic")

# Truck parking
parking = client.get_events("Parking")
for lot in parking:
    if lot.available_spaces > 0:
        print(f"{lot.name}: {lot.available_spaces}/{lot.total_spaces} spaces ({lot.occupancy_pct:.0f}% full)")

# Dynamic message signs with active messages
signs = client.get_events("MessageSigns")
active_signs = [s for s in signs if s.status == "on" and s.display_message]
for sign in active_signs[:10]:
    print(f"{sign.roadway} {sign.direction}: {sign.display_message}")

# Weather alerts
alerts = client.get_weather_alerts()
print(f"{len(alerts)} active weather alerts")

# Forecast zones
zones = client.get_weather_forecast_zones()
print(f"{len(zones)} forecast zones")

# FDOT ArcGIS detour routes
geojson = client.get_fdot_arcgis_detour_geojson()
print(f"{len(geojson['features'])} ERS detour route features")

# Tile URLs
speed_tile = client.get_traffic_speed_tile_url()
radar_tile = client.get_weather_radar_tile_url()
print(speed_tile)   # https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
print(radar_tile)   # https://fl511.com/map/weatherRadar/{x}/{y}/{z}
```

---

## CLI Reference

```
python fl511_client.py --help
```

### List all cameras statewide

```bash
python fl511_client.py --cameras
```

### Filter cameras by county/area

```bash
python fl511_client.py --cameras --area MDC        # Miami-Dade
python fl511_client.py --cameras --area HIL        # Tampa / Hillsborough
python fl511_client.py --cameras --area ORA        # Orlando / CFX
python fl511_client.py --cameras --area PBC        # Palm Beach
python fl511_client.py --cameras --area DUV        # Jacksonville
python fl511_client.py --cameras --area LEO        # Tallahassee / Leon
```

### Find cameras near a GPS coordinate

```bash
python fl511_client.py --cameras-near 25.775 -80.208 --radius 3    # Downtown Miami
python fl511_client.py --cameras-near 27.975 -82.533 --radius 5    # Tampa Airport
python fl511_client.py --cameras-near 28.538 -81.379 --radius 2    # Orlando I-4
```

### Get full camera detail (with video URL)

```bash
python fl511_client.py --camera-detail 1
```

### Download live JPEG snapshot

```bash
python fl511_client.py --snapshot 1 --output camera_1.jpg
python fl511_client.py --snapshot 435 --output i95_miami.jpg
```

### Get traffic events

```bash
python fl511_client.py --events Incidents
python fl511_client.py --events Construction
python fl511_client.py --events Closures
python fl511_client.py --events Congestion
python fl511_client.py --events DisabledVehicles
python fl511_client.py --events SpecialEvents
```

### Infrastructure status

```bash
python fl511_client.py --events Bridge           # Drawbridge open/close
python fl511_client.py --events Parking          # Truck parking availability
python fl511_client.py --events RailCrossing     # Railroad crossing status
python fl511_client.py --events MessageSigns     # Highway message sign content
```

### Weather

```bash
python fl511_client.py --events WeatherEvents    # NWS weather alerts
```

### Get full event detail (with coordinates + polyline)

```bash
python fl511_client.py --event-detail Incidents 389236
python fl511_client.py --event-detail Construction 10
```

### FDOT ArcGIS detour routes

```bash
python fl511_client.py --detour-routes
```

### JSON output

```bash
python fl511_client.py --cameras --json
python fl511_client.py --events Incidents --json
python fl511_client.py --camera-detail 1 --json
```

### Utility

```bash
python fl511_client.py --list-areas      # Show all county/area codes
python fl511_client.py --list-layers     # Show all available event layers
```

---

## API Reference

### `FL511Client`

```python
client = FL511Client(timeout=30)
```

**Parameters:**
- `timeout` (int): HTTP request timeout in seconds. Default: 30.

---

### Camera Methods

#### `get_all_cameras() -> List[Camera]`

Returns all cameras statewide (~4,700+). Fast single request. Returns location
and video-enabled status only (no image/video URLs).

#### `get_camera_detail(camera_id: int) -> Camera`

Returns full camera record including snapshot URL and HLS stream URL.

#### `get_cameras_by_area(area_id: str) -> List[Camera]`

Returns cameras for a county/area. Full detail included.

#### `iter_all_camera_details(camera_ids=None, delay=0.05) -> Iterator[Camera]`

Yields full camera detail for all (or a subset of) cameras. One request per
camera. Use `delay` to throttle requests.

#### `get_cameras_near(lat, lon, radius_miles=5.0, with_detail=True) -> List[(float, Camera)]`

Returns cameras within `radius_miles` of a GPS coordinate, sorted by distance.
Returns `[(distance_miles, Camera), ...]`.

#### `get_snapshot(camera_id: int) -> bytes`

Downloads the current JPEG snapshot image. Returns raw bytes. No auth required.

---

### Event Methods

#### `get_events(layer: str, page_size=1000) -> List`

Returns typed event objects for the given layer. Returns:
- `List[TrafficEvent]` for: `Incidents`, `Construction`, `Closures`, `SpecialEvents`,
  `Congestion`, `DisabledVehicles`, `RoadConditionIncident`, `WeatherIncidents`
- `List[MessageSign]` for: `MessageSigns`
- `List[Bridge]` for: `Bridge`
- `List[ParkingFacility]` for: `Parking`

#### `get_event_detail(layer: str, event_id: int) -> dict`

Returns the raw full-detail dict for a specific event (from `/map/data/{layer}/{id}`).
Includes coordinates, polyline geometry, detour routes, lane data.

#### `get_weather_alerts() -> List[WeatherAlert]`

Returns current NWS weather alerts.

#### `get_weather_forecast_zones() -> List[WeatherForecastZone]`

Returns NWS forecast zone centroids.

---

### Utility Methods

#### `list_areas() -> Dict[str, str]`

Returns all known area codes and descriptions.

#### `list_event_layers() -> Dict[str, str]`

Returns all available event layer names and descriptions.

#### `list_districts() -> Dict[str, str]`

Returns FDOT district codes and county coverage.

#### `get_traffic_speed_tile_url() -> str`

Returns the XYZ tile URL template for traffic speed overlay tiles.

#### `get_weather_radar_tile_url() -> str`

Returns the XYZ tile URL template for NEXRAD weather radar tiles.

#### `get_fdot_arcgis_detour_geojson(detour_type='Detour') -> dict`

Fetches FDOT Emergency Roadway System detour route GeoJSON from ArcGIS Online.

---

## Dataclass Reference

### `Camera`

| Field | Type | Description |
|-------|------|-------------|
| `camera_id` | `int` | Unique camera site ID |
| `source_id` | `str` | DIVAS channel ID (embedded in HLS URL) |
| `source` | `str` | Managing agency, e.g. `DIVAS-District 1` |
| `area_id` | `str` | County/area code, e.g. `MDC` |
| `roadway` | `str` | Road name, e.g. `I-95` |
| `direction` | `int` | `1`=N, `2`=E, `3`=S, `4`=W, `0`=unknown |
| `location` | `str` | Human-readable location description |
| `latitude` | `float` | Decimal degrees (WGS-84) |
| `longitude` | `float` | Decimal degrees (WGS-84) |
| `images` | `List[CameraImage]` | Image/video records |
| `video_enabled` | `bool` | From map icon: True if HLS stream available |
| `.snapshot_url` | property | Full JPEG snapshot URL (no auth required) |
| `.stream_url` | property | HLS `.m3u8` URL (DIVAS auth required) |
| `.has_video` | property | True if any non-disabled video URL present |
| `.direction_name` | property | `Northbound` / `Eastbound` etc. |

### `CameraImage`

| Field | Type | Description |
|-------|------|-------------|
| `image_id` | `int` | Used in `/map/Cctv/{image_id}` |
| `camera_site_id` | `int` | Parent camera ID |
| `description` | `str` | DIVAS internal identifier |
| `image_url` | `str` | Relative path for JPEG snapshot |
| `video_url` | `str` | Full HLS `.m3u8` URL |
| `video_type` | `str` | `application/x-mpegURL` |
| `video_disabled` | `bool` | Administratively disabled |
| `blocked` | `bool` | Feed currently blocked |
| `.snapshot_url` | property | Absolute JPEG snapshot URL |
| `.has_video` | property | True if video URL present and not disabled |

### `TrafficEvent`

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | `int` | Unique event ID |
| `layer` | `str` | Layer name (e.g. `Incidents`) |
| `event_type` | `str` | ATIS type (e.g. `accidentsAndIncidents`) |
| `event_subtype` | `str` | Sub-type (e.g. `ScheduledRoadWork`) |
| `roadway` | `str` | Road name |
| `direction` | `str` | Direction text |
| `description` | `str` | Full HTML description |
| `comment` | `str` | Plain-text comment |
| `severity` | `str` | `Minor`, `Moderate`, `Major`, `Severe` |
| `is_full_closure` | `bool` | Full roadway closure |
| `latitude` | `float` | (populated via `get_event_detail`) |
| `longitude` | `float` | (populated via `get_event_detail`) |
| `area_id` | `str` | County/area code |
| `dot_district` | `str` | FDOT district label |
| `region` | `str` | Region (Southwest, Central, etc.) |
| `county` | `str` | County name |
| `start_date` | `str` | Start date-time |
| `last_updated` | `str` | Last updated date-time |
| `end_date` | `str\|None` | End date-time or None |
| `lane_description` | `str` | Lane impact summary |
| `detour_description` | `str` | JSON detour instructions |
| `source` | `str` | Source system (e.g. `ERS`) |

### `MessageSign`

| Field | Type | Description |
|-------|------|-------------|
| `sign_id` | `int` | Unique sign ID |
| `source_id` | `str` | Source system identifier |
| `name` | `str` | Sign location name |
| `roadway` | `str` | Road name |
| `direction` | `str` | Direction code (`e`, `w`, `n`, `s`) |
| `area_id` | `str` | County/area code |
| `county` | `str` | County name |
| `region` | `str` | Region name |
| `status` | `str` | `on` or `off` |
| `message` | `str` | Raw NTCIP sign content (phase 1) |
| `message_line2` | `str` | Phase 2 content |
| `message_line3` | `str` | Phase 3 content |
| `latitude` | `float` | Decimal degrees |
| `longitude` | `float` | Decimal degrees |
| `last_updated` | `str` | Last communication timestamp |
| `.display_message` | property | Clean plain-text message |

### `Bridge`

| Field | Type | Description |
|-------|------|-------------|
| `bridge_id` | `int` | Unique bridge ID |
| `name` | `str` | Bridge name |
| `roadway` | `str` | Road name |
| `location` | `str` | Waterway or cross-street |
| `county` | `str` | County name |
| `status` | `str` | `Bridge Up` or `Bridge Down` |
| `direction` | `str` | Direction code |
| `network` | `str` | Managing agency |
| `last_updated` | `str` | Last updated timestamp |
| `.is_open_to_boats` | property | True if bridge is raised |

### `ParkingFacility`

| Field | Type | Description |
|-------|------|-------------|
| `facility_id` | `int` | Unique facility ID |
| `name` | `str` | Facility name |
| `roadway` | `str` | Road name |
| `direction` | `str` | Direction of travel |
| `total_spaces` | `int` | Total monitored spaces |
| `available_spaces` | `int` | Currently available spaces |
| `last_updated` | `str` | Last updated timestamp |
| `.occupancy_pct` | property | `(total - available) / total * 100` |
| `.is_full` | property | True if available_spaces == 0 |

---

## Technical Notes

### Platform

FL511 runs on the **IBI Group ASP.NET MVC 511** platform, the same system used by:
Wisconsin (511wi.gov), New York (511ny.org), Pennsylvania (511pa.com),
Alaska (511.alaska.gov), and Utah (udottraffic.utah.gov).

### Session Management

The site uses ASP.NET cookie-based sessions. Visiting the homepage sets
a `session-id` cookie (not a login — just a session identifier). All API
endpoints require this cookie.

### Rate Limiting

No explicit rate limiting was observed during reverse engineering. However,
be a respectful client:
- For bulk camera detail fetches, use `delay=0.05` (50ms between requests)
- Cache results when possible — event data changes every 1–5 minutes
- Camera snapshots are typically refreshed every 5–30 seconds

### Response Compression

Most `map/mapIcons/*` responses are gzip-compressed even without an
`Accept-Encoding: gzip` request header. The client handles this automatically.

### Coordinate System

All coordinates are WGS-84 (EPSG:4326).

### Video Auth

DIVAS HLS streams (`dis-se{N}.divas.cloud:8200`) require a valid DIVAS portal
session and return `HTTP 401` for direct access. The `isVideoAuthRequired`
field in camera records is consistently set to `true`. Use the `/map/Cctv/{id}`
JPEG snapshot endpoint as the no-auth alternative.

---

## Dependencies

- Python 3.7+
- Standard library only: `urllib`, `json`, `http.cookiejar`, `gzip`, `dataclasses`, `math`
- No third-party packages required
