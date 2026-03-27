# OHGO Client — Ohio Department of Transportation Traffic API

A production-quality Python client for the **OHGO / ODOT Public Traffic API**
operated by the Ohio Department of Transportation at
[ohgo.com](https://www.ohgo.com).

- **Zero dependencies** — uses Python stdlib only (`urllib`, `json`, `dataclasses`)
- **Python 3.8+** compatible
- Covers **all nine endpoints** including live camera images, incidents,
  construction, weather sensors, digital signs, and the WZDx GeoJSON feed
- Full **dataclass-typed** responses with docstrings
- **CLI** for interactive exploration and shell scripting

---

## Table of Contents

1. [API Background](#api-background)
2. [Authentication](#authentication)
3. [Quick Start](#quick-start)
4. [Discovered Endpoints](#discovered-endpoints)
5. [Request / Response Format](#request--response-format)
6. [Filter Parameters](#filter-parameters)
7. [Client Reference](#client-reference)
8. [CLI Reference](#cli-reference)
9. [Live Image & CDN Patterns](#live-image--cdn-patterns)
10. [Error Handling](#error-handling)
11. [Known Limitations](#known-limitations)

---

## API Background

OHGO is Ohio DOT's public-facing traffic platform.  The backend API is
documented at `https://publicapi.ohgo.com`.

| Property          | Value |
|-------------------|-------|
| Base URL          | `https://publicapi.ohgo.com` |
| API version path  | `/api/v1` |
| Spec format       | OpenAPI 3.0.4 |
| Swagger UI        | `https://publicapi.ohgo.com/docs/v1/swagger/index.html` |
| Auth              | `Authorization: APIKEY <key>` header **or** `?api-key=<key>` param |
| Response format   | JSON (content-type `application/json`) |
| Protocol          | HTTPS (TLS 1.2+, served by IIS 10 / ASP.NET) |
| Rate limiting     | Not documented; contact ohgo.help@dot.ohio.gov for details |
| CDN image refresh | Every 5 seconds |

The API is public (free registration) and targets developers building
traffic-aware applications for Ohio roads.

---

## Authentication

Register for a free API key at:

```
https://publicapi.ohgo.com/accounts/registration
```

Include the key in one of two ways:

**Authorization header (recommended):**
```
Authorization: APIKEY your_key_here
```

**Query parameter:**
```
https://publicapi.ohgo.com/api/v1/cameras?api-key=your_key_here
```

Both methods work for all endpoints.  The Python client uses the header
method by default.

---

## Quick Start

### Library usage

```python
from ohgo_client import OHGOClient

client = OHGOClient(api_key="your_key_here")

# List cameras in Cleveland
result = client.get_cameras(region="cleveland")
print(f"Found {result.total_result_count} cameras")

for cam in result.results:
    print(f"  {cam.location}")
    for view in cam.camera_views:
        print(f"    [{view.direction}] {view.large_url}")
```

**Environment variable** — avoid hardcoding your key:

```bash
export OHGO_API_KEY=your_key_here
```

```python
client = OHGOClient()  # reads OHGO_API_KEY automatically
```

### Active incidents statewide

```python
result = client.get_incidents(page_all=True)
for inc in result.results:
    if inc.road_status != "Open":
        print(f"{inc.road_status}: {inc.category} on {inc.route_name} — {inc.location}")
```

### Weather hazards

```python
result = client.get_weather_sensor_sites(hazards_only=True)
for site in result.results:
    print(f"{site.location}: {site.condition}  ({site.average_air_temperature}°F)")
    for sensor in site.atmospheric_sensors:
        print(f"  wind {sensor.average_wind_speed} mph, precip: {sensor.precipitation}")
```

### Cameras within 5 miles of downtown Columbus

```python
result = client.get_cameras(radius="39.9612,-82.9988,5")
for cam in result.results:
    print(cam.location)
```

### Construction with future events

```python
result = client.get_construction(
    region="columbus",
    include_future="2026-06-30",
)
for c in result.results:
    print(f"[{c.status}] {c.route_name} — {c.description[:60]}")
```

---

## Discovered Endpoints

All endpoints are under `https://publicapi.ohgo.com`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/cameras` | All traffic cameras |
| `GET` | `/api/v1/cameras/{id}` | Camera by ID (comma-sep IDs accepted) |
| `GET` | `/api/v1/incidents` | Active traffic incidents |
| `GET` | `/api/v1/incidents/{id}` | Incident by ID |
| `GET` | `/api/v1/construction` | Active (and optionally future) construction |
| `GET` | `/api/v1/construction/{id}` | Construction by ID |
| `GET` | `/api/v1/dangerous-slowdowns` | Speed drop alerts |
| `GET` | `/api/v1/dangerous-slowdowns/{id}` | Slowdown by ID |
| `GET` | `/api/v1/digital-signs` | Dynamic message signs with current text |
| `GET` | `/api/v1/digital-signs/{id}` | Sign by ID |
| `GET` | `/api/v1/travel-delays` | Travel time & delay metrics |
| `GET` | `/api/v1/travel-delays/{id}` | Travel delay by ID |
| `GET` | `/api/v1/truck-parking` | Commercial vehicle parking |
| `GET` | `/api/v1/truck-parking/{id}` | Truck parking by ID |
| `GET` | `/api/v1/weather-sensor-sites` | RWIS weather stations |
| `GET` | `/api/v1/weather-sensor-sites/{id}` | Weather site by ID |
| `GET` | `/api/work-zones/wzdx/4.2` | WZDx 4.2 GeoJSON work zone feed |

> **Note:** The work-zones endpoint is at `/api/work-zones/…` (not `/api/v1/…`).

---

## Request / Response Format

### Standard list response envelope

Every list endpoint (`/api/v1/<resource>`) returns the same JSON envelope:

```json
{
  "links": [{"href": "...", "rel": "self"}],
  "lastUpdated": "2026-03-27T19:54:00Z",
  "accecptedFilters": [{"key": "region", "value": "cleveland"}],
  "rejectedFilters": [],
  "totalPageCount": 3,
  "totalResultCount": 1234,
  "currentResultCount": 500,
  "results": [ ... ]
}
```

> **Typo in API**: `accecptedFilters` (double 'c') is the actual field name
> in the live API and OpenAPI spec.  The Python client maps it to
> `accepted_filters` transparently.

### Camera response example

```json
{
  "id": "CAM-123-456",
  "latitude": 41.4993,
  "longitude": -81.6944,
  "location": "I-90 EB @ E 9th St",
  "description": "Fixed camera facing east",
  "cameraViews": [
    {
      "direction": "E",
      "smallUrl": "https://cdn.ohgo.com/camera/sm/CAM-123-456.jpg",
      "largeUrl": "https://cdn.ohgo.com/camera/lg/CAM-123-456.jpg",
      "mainRoute": "I-90"
    }
  ],
  "links": [
    {"href": "https://publicapi.ohgo.com/api/v1/cameras/CAM-123-456", "rel": "self"},
    {"href": "https://publicapi.ohgo.com/docs/v1/cameras", "rel": "documentation"},
    {"href": "https://www.ohgo.com/map/cameras/CAM-123-456", "rel": "redirect"}
  ]
}
```

### Incident response example

```json
{
  "id": "INC-789",
  "latitude": 39.9612,
  "longitude": -82.9988,
  "location": "I-71 NB @ SR-161",
  "description": "Multi-vehicle accident, right lane blocked",
  "category": "Accident",
  "direction": "NB",
  "routeName": "I-71",
  "roadStatus": "Partial Closure",
  "roadClosureDetails": {
    "closureStartLocation": [-82.9988, 39.9612],
    "closureEndLocation":   [-82.9988, 39.9700],
    "polyline": [[-82.9988, 39.9612], [-82.9988, 39.9700]]
  }
}
```

### WZDx work zone response example

```json
{
  "type": "FeatureCollection",
  "feedInfo": {
    "publisher": "Ohio Department of Transportation",
    "version": "4.2",
    "updateFrequency": 60,
    "license": "https://creativecommons.org/publicdomain/zero/1.0/"
  },
  "features": [
    {
      "id": "WZ-001",
      "type": "Feature",
      "properties": {
        "coreDetails": {
          "eventType": "work-zone",
          "name": "SR-315 Resurfacing",
          "direction": "northbound",
          "roadNames": ["SR-315"],
          "description": "Lane restrictions for resurfacing",
          "updateDate": "2026-03-27T18:00:00Z"
        },
        "startDate": "2026-03-01T06:00:00Z",
        "endDate": "2026-04-15T18:00:00Z",
        "locationMethod": "channel-device-method",
        "vehicleImpact": "some-lanes-closed"
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [[-83.0100, 39.9800], [-83.0100, 40.0200]]
      }
    }
  ]
}
```

---

## Filter Parameters

### Universal filters (all endpoints)

| Parameter | Type | Description |
|-----------|------|-------------|
| `region` | string | Comma-separated region names (case-insensitive) |
| `radius` | string | `"lat,lon,miles"` — results within circle |
| `map-bounds-sw` | string | `"lat,lon"` — SW corner of bounding box |
| `map-bounds-ne` | string | `"lat,lon"` — NE corner of bounding box (required with SW) |
| `page-size` | int | Max records per page (default: 500) |
| `page` | int | Zero-based page index |
| `page-all` | string | `"true"` — return all results, ignore paging |

**Valid region values:**
`akron`, `central-ohio`, `cincinnati`, `cleveland`, `columbus`, `dayton`,
`ne-ohio`, `nw-ohio`, `se-ohio`, `sw-ohio`, `toledo`

Multiple regions: `region=cleveland,akron`

### Construction-specific filters

| Parameter | Type | Description |
|-----------|------|-------------|
| `include-future` | date `yyyy-MM-dd` | Current + future construction up to date |
| `future-only` | date `yyyy-MM-dd` | Only future construction up to date |

### Digital signs filter

| Parameter | Type | Valid values |
|-----------|------|--------------|
| `sign-type` | string | `dms` / `message-board`, `ddms` / `travel-time`, `sign-queue` / `slow-traffic`, `vsl` / `variable-speed-limit`, `tp` / `truck-parking` |

Multiple types: `sign-type=dms,ddms`

### Weather sensor filter

| Parameter | Type | Description |
|-----------|------|-------------|
| `hazards-only` | string | `"true"` — only sites with rain/snow/ice/wind/visibility hazards |

---

## Client Reference

### `OHGOClient(api_key, timeout, base_url)`

Constructor.  If `api_key` is omitted the `OHGO_API_KEY` environment
variable is used.

### Methods

All list methods accept the same set of common keyword arguments.  Each
returns an `ApiResult` with `results` typed as the appropriate dataclass.

#### Common keyword arguments

```
region          str   — comma-separated region names
radius          str   — "lat,lon,miles"
map_bounds_sw   str   — "lat,lon" SW bounding-box corner
map_bounds_ne   str   — "lat,lon" NE bounding-box corner
page_size       int   — records per page
page            int   — zero-based page number
page_all        bool  — return all records
```

#### `get_cameras(**filters)` → `ApiResult[Camera]`

Returns traffic camera sites.  Each `Camera` has a `camera_views` list
where each `CameraView` contains `small_url` and `large_url` for live
JPEG images (refreshed every 5 seconds).

#### `get_camera(camera_id)` → `ApiResult[Camera]`

Single camera or comma-separated list of IDs.

#### `get_incidents(**filters)` → `ApiResult[Incident]`

Active accidents, weather events, and road hazards.  `road_closure_details`
contains GeoJSON-compatible polyline data when a road is closed.

#### `get_construction(**filters, include_future, future_only)` → `ApiResult[Construction]`

Active construction zones.  Pass `include_future="YYYY-MM-DD"` to extend
the date window.  `work_zones` and `detours` contain polyline geometry.

#### `get_dangerous_slowdowns(**filters)` → `ApiResult[DangerousSlowdown]`

Locations where `current_mph` has dropped significantly below `normal_mph`.

#### `get_digital_signs(**filters, sign_type)` → `ApiResult[DigitalSign]`

DMS signs and their current `messages` list.  `image_urls` contains JPEG
renderings of sign faces (where available).

#### `get_travel_delays(**filters)` → `ApiResult[TravelDelay]`

Segment-level travel time metrics: `travel_time`, `delay_time`,
`current_avg_speed`, `normal_avg_speed` (all in minutes or mph).

#### `get_truck_parking(**filters)` → `ApiResult[TruckParking]`

Commercial vehicle parking locations with `capacity`, `reported_available`,
`open` status, and `last_reported` timestamp.

#### `get_weather_sensor_sites(**filters, hazards_only)` → `ApiResult[WeatherSensorSite]`

RWIS stations with full `atmospheric_sensors` (temperature, wind, precip,
visibility) and `surface_sensors` (pavement/sub-surface temperature).
`severe=True` when hazardous conditions are detected.

#### `get_work_zones()` → `WorkZoneFeed`

Complete WZDx 4.2 GeoJSON FeatureCollection.  Not paged.  Typically
contains hundreds of features.

### Dataclass hierarchy

```
ApiResult
├── links: List[Link]
├── last_updated: str
├── total_page_count: int
├── total_result_count: int
├── current_result_count: int
├── accepted_filters: List[QueryParam]
├── rejected_filters: List[QueryParam]
└── results: List[<typed>]

Camera
├── id, latitude, longitude, location, description
├── links: List[Link]
└── camera_views: List[CameraView]
       ├── direction, main_route
       ├── small_url  (CDN JPEG, ~5s refresh)
       └── large_url  (CDN JPEG, ~5s refresh)

Incident
├── id, latitude, longitude, location, description
├── category, direction, route_name, road_status
├── links: List[Link]
└── road_closure_details: Optional[RoadClosureDetails]
       ├── closure_start_location: [lon, lat]
       ├── closure_end_location:   [lon, lat]
       └── polyline: [[lon, lat], ...]

Construction
├── id, latitude, longitude, location, description
├── category, direction, district, route_name, status
├── start_date, end_date
├── links: List[Link]
├── work_zones: List[ConstructionWorkZone]
│      └── start_location, end_location, polyline
└── detours: List[ConstructionDetour]
       ├── name, description, start_date, end_date
       └── detour_routes: List[ConstructionDetourRoute]
              └── road_name, start_location, end_location, polyline

DangerousSlowdown
├── id, latitude, longitude, location, description
├── normal_mph, current_mph, route_name, direction
└── links: List[Link]

DigitalSign
├── id, latitude, longitude, location, description
├── sign_type_name
├── messages: List[str]
├── image_urls: List[str]
└── links: List[Link]

TravelDelay
├── id, latitude, longitude, location, description
├── direction, route_name
├── travel_time, delay_time  (minutes)
├── start_mile_marker, end_mile_marker
├── current_avg_speed, normal_avg_speed  (mph)
└── links: List[Link]

TruckParking
├── id, latitude, longitude, location, description
├── address, capacity, reported_available
├── open: bool, last_reported: str
└── links: List[Link]

WeatherSensorSite
├── id, latitude, longitude, location, description
├── average_air_temperature, severe: bool, condition
├── atmospheric_sensors: List[AtmosphericSensor]
│      ├── air_temperature, dewpoint_temperature  (°F)
│      ├── humidity (%), pressure
│      ├── average_wind_speed, maximum_wind_speed (mph)
│      ├── wind_direction
│      ├── precipitation, precipitation_rate, precipitation_accumulation
│      ├── precipitation_intensity, visibility (miles)
│      └── last_update
├── surface_sensors: List[SurfaceSensor]
│      ├── name, status
│      ├── surface_temperature, sub_surface_temperature (°F)
│      └── last_update
└── links: List[Link]

WorkZoneFeed
├── type: "FeatureCollection"
├── feed_info: WZDxFeedInfo
│      ├── publisher, contact_name, contact_email
│      ├── license, version, update_frequency
│      └── data_sources: List[WZDxDataSource]
└── features: List[WZDxFeature]
       ├── id, type: "Feature"
       ├── geometry: WZDxGeometry
       │      ├── type: "LineString" | "MultiPoint"
       │      └── coordinates: [[lon, lat], ...]
       └── properties: WZDxProperties
              ├── start_date, end_date (RFC 3339)
              ├── location_method, vehicle_impact
              ├── is_start/end_date/position_verified: bool
              ├── beginning_accuracy, ending_accuracy
              └── core_details: WZDxCoreDetails
                     ├── data_source_id, event_type, name
                     ├── direction, road_names, description
                     └── update_date
```

---

## CLI Reference

```
python ohgo_client.py [--api-key KEY] [--timeout SECS] <command> [options]
```

**Global options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--api-key KEY` | `$OHGO_API_KEY` | Your OHGO API key |
| `--timeout SECS` | `30` | HTTP timeout in seconds |

**Commands:**

| Command | Description |
|---------|-------------|
| `cameras` | Traffic camera listing |
| `incidents` | Active incident listing |
| `construction` | Construction zone listing |
| `weather` | RWIS weather station listing |
| `slowdowns` | Dangerous slowdown listing |
| `signs` | Digital message sign listing |
| `delays` | Travel delay listing |
| `parking` | Truck parking listing |
| `work-zones` | WZDx 4.2 GeoJSON feed summary |

**Shared options (cameras / incidents / construction / weather / slowdowns / signs / delays / parking):**

| Option | Description |
|--------|-------------|
| `--region REGION` | Filter by comma-separated region names |
| `--radius LAT,LON,MILES` | Filter by radius around a point |
| `--page-size N` | Max records per page |
| `--page N` | Page number (zero-based) |
| `--page-all` | Return all records |

**construction extras:**

| Option | Description |
|--------|-------------|
| `--include-future YYYY-MM-DD` | Include future construction up to date |
| `--future-only YYYY-MM-DD` | Only future construction up to date |

**weather extras:**

| Option | Description |
|--------|-------------|
| `--hazards-only` | Show only sites with active hazards |

**signs extras:**

| Option | Description |
|--------|-------------|
| `--sign-type TYPE` | Filter by sign type (comma-separated) |

### Example commands

```bash
# Cameras in Cleveland (default page of 500)
python ohgo_client.py --api-key $KEY cameras --region cleveland

# All incidents statewide
python ohgo_client.py --api-key $KEY incidents --page-all

# Active + future construction through June
python ohgo_client.py --api-key $KEY construction \
    --region columbus --include-future 2026-06-30

# Weather hazards only
python ohgo_client.py --api-key $KEY weather --hazards-only

# Cameras within 3 miles of Akron downtown (41.08, -81.52)
python ohgo_client.py --api-key $KEY cameras --radius 41.0814,-81.5190,3

# Travel-time signs in Toledo
python ohgo_client.py --api-key $KEY signs \
    --region toledo --sign-type travel-time

# Dangerous slowdowns on all NW Ohio routes
python ohgo_client.py --api-key $KEY slowdowns --region nw-ohio

# Summary of the WZDx work zone GeoJSON feed
python ohgo_client.py --api-key $KEY work-zones
```

---

## Live Image & CDN Patterns

Camera images are served from an OHGO CDN.  Each `CameraView` provides
two direct image URLs:

| Field | Description |
|-------|-------------|
| `small_url` | Smaller thumbnail JPEG |
| `large_url` | Full-resolution JPEG |

Images are refreshed **every 5 seconds** by the CDN.  You can poll them
directly via `urllib.request.urlopen` or any HTTP client.

```python
import urllib.request

cam = result.results[0]
view = cam.camera_views[0]

# Download the current image
with urllib.request.urlopen(view.large_url) as resp:
    image_bytes = resp.read()

with open("camera.jpg", "wb") as f:
    f.write(image_bytes)
```

No authentication is required to fetch the camera image files themselves
(they are publicly accessible CDN URLs).  Only the API metadata endpoints
(`publicapi.ohgo.com/api/v1/…`) require the API key.

---

## Error Handling

The client raises `OHGOAPIError` on HTTP 4xx/5xx responses:

```python
from ohgo_client import OHGOClient, OHGOAPIError

client = OHGOClient(api_key="your_key")
try:
    result = client.get_cameras(region="cleveland")
except OHGOAPIError as e:
    print(f"HTTP {e.status}: {e.message}")
```

Common error codes:

| HTTP Status | Meaning |
|-------------|---------|
| `400 Bad Request` | Malformed request parameter |
| `401 Unauthorized` | Missing or invalid API key |
| `404 Not Found` | ID not found |
| `503 Service Unavailable` | API temporarily unavailable |

Network-level errors (DNS failure, timeout) raise `urllib.error.URLError`
from the standard library.

Rejected filter parameters are returned inside the API result envelope
rather than as errors:

```python
result = client.get_cameras(region="invalid-region")
if result.rejected_filters:
    for f in result.rejected_filters:
        print(f"Rejected: {f.key}={f.value}  ({f.error})")
```

---

## Known Limitations

- **No snowplow tracking** — The public API does not expose snowplow or
  winter maintenance vehicle tracking.  That functionality appears to be
  available only through the internal ODOT fleet management system.

- **No real-time video streams** — The API exposes JPEG snapshots only
  (refreshed every 5 seconds by CDN).  No RTSP/HLS video streams were
  found in the public API.

- **Work zones not paginated** — `GET /api/work-zones/wzdx/4.2` returns
  the full dataset in one response.  The Swagger documentation notes this
  is too large for the interactive UI.

- **`accecptedFilters` typo** — The field name in the live API JSON and
  OpenAPI schema is `accecptedFilters` (double 'c').  The Python client
  maps this to `accepted_filters`.

- **Rate limits undocumented** — ODOT has not published rate limit values.
  For high-frequency polling contact `ohgo.help@dot.ohio.gov`.

- **API key required** — Registration is required even for read-only
  access.  There is no anonymous tier.

---

## API Discovery Methodology

This client was built by:

1. Loading `https://www.ohgo.com` to locate the `PublicApiUrl` config
   variable (`http://publicapi.ohgo.com`) and `MobileApiUrl`
   (`https://api.ohgo.com`).

2. Browsing the publicly accessible developer portal at
   `https://publicapi.ohgo.com` which exposed the full sidebar menu of
   endpoints and documentation pages.

3. Fetching the OpenAPI 3.0.4 specification directly from
   `https://publicapi.ohgo.com/docs/v1/swagger.json` which provided
   the canonical endpoint list, all parameters, all response schemas,
   and security scheme definitions.

4. Verifying auth requirements: unauthenticated requests return
   `{"errorDescription": "API key required."}` with HTTP 401.
   Requests with a valid key return paginated JSON.

---

## License

This client is open for use under the MIT License.  The OHGO data itself
is provided by the Ohio Department of Transportation and is subject to
their terms of service.  Work zone data is licensed under
[CC0 1.0 (Public Domain)](https://creativecommons.org/publicdomain/zero/1.0/).
