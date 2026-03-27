# MaineDOT / New England 511 Traffic Camera Client

Reverse-engineered Python client for the **New England 511** traffic
information system (`https://newengland511.org`), which serves live traffic
camera images, incidents, road conditions, and dynamic message signs for
Maine, New Hampshire, and Vermont.

**No API key required. No login required. Stdlib only (`urllib`, `json`,
`gzip`, `dataclasses`).**

---

## Table of Contents

1. [Background & Discovery](#1-background--discovery)
2. [API Architecture](#2-api-architecture)
3. [Endpoints Reference](#3-endpoints-reference)
4. [Data Structures](#4-data-structures)
5. [Installation & Requirements](#5-installation--requirements)
6. [Quick Start](#6-quick-start)
7. [Full API Reference](#7-full-api-reference)
8. [Known Quirks & Gotchas](#8-known-quirks--gotchas)
9. [Rate Limiting & Etiquette](#9-rate-limiting--etiquette)
10. [Live Test Results](#10-live-test-results)

---

## 1. Background & Discovery

### Target Site

The primary site is **https://newengland511.org**, a multi-state 511 traffic
information portal maintained by a vendor (IBI Group / Iteris) and covering:

- **Maine** (MaineDOT)
- **New Hampshire** (NHDOT)
- **Vermont** (VTrans)

Maine's official DOT page (`maine.gov/dot`) links to this portal for live
camera feeds. There is no separate Maine-only camera API — all data flows
through the NE511 platform.

### Reverse-Engineering Process

1. **Homepage HTML** (`/`) was fetched to identify script bundle URLs.
2. **Map page** (`/map`) revealed `data-jsonurl` attributes pointing to
   `/map/mapIcons/{layer}` for each overlay layer.
3. **CCTV list page** (`/cctv`) identified the DataTables-based list with
   typeId `"Cameras"`.
4. **JS bundles** analyzed:
   - `/bundles/listCctv` — camera list rendering, image refresh logic
   - `/bundles/datatables` — DataTables initialization, **CamListConfig**
     function, and the `/List/GetData/{typeId}` endpoint URL
   - `/bundles/map` — `/Camera/GetVideoUrl` endpoint
5. **Live endpoint testing** confirmed all endpoints, pagination behavior,
   and the gzip-always response encoding.

### Key Technical Findings

| Finding | Detail |
|---------|--------|
| Auth | None required for public data |
| Response encoding | Server returns **gzip always**, even without `Accept-Encoding` header |
| DataTables protocol | Server-side, GET with `?query=<JSON>&lang=en` |
| Column search bug | Empty `search:{}` on a column causes 0 results; omit the key entirely |
| Page size cap | Max **100 records per page** (server-enforced; requests for 200+ return 100) |
| Image refresh | JPEG snapshots at `/map/Cctv/{imageId}`, `Cache-Control: max-age=10` |
| Image hosting | CloudFront CDN via AWS Lambda (evident from response headers) |
| Message signs | Uses `area` (not `state`) and `roadwayName` (not `roadway`) as column names |

---

## 2. API Architecture

```
https://newengland511.org
│
├── /map/mapIcons/{layer}           → Lightweight GeoJSON-style icon list
│   Returns: {item1: iconConfig, item2: [{itemId, location, title},...]}
│   Layers: Cameras, Incidents, Construction, MessageSigns,
│           WeatherStations, WeatherEvents, FerryTerminals, TruckRestrictions
│
├── /List/GetData/{typeId}          → Full paginated DataTables data
│   Method: GET
│   Query:  ?query={datatables_json}&lang=en
│   Types:  Cameras, traffic, construction, MessageSigns, TravelTimes
│   Notes:  Max 100 records/page; column-level search for state filtering
│
├── /map/Cctv/{imageId}             → Live camera JPEG snapshot
│   Method: GET
│   Returns: image/jpeg (0 bytes = offline/blocked)
│   Cache:  max-age=10 (10-second refresh cycle)
│
├── /tooltip/{layer}/{itemId}       → HTML popup for map markers
│   Method: GET
│   Params: ?lang=en&noCss=true
│   Returns: HTML fragment with camera title, image tag, lat/lon
│
├── /Camera/GetVideoUrl?imageId={id} → Video stream URL (auth required)
│
└── /Camera/GetUserCameraLists      → Saved "My Cameras" lists (auth required)
```

### DataTables Query Format

The `/List/GetData/{typeId}` endpoint uses the server-side DataTables
protocol. Requests are GET with a `query` parameter containing JSON:

```json
{
  "draw": 1,
  "columns": [
    {"data": "sortOrder", "name": "sortOrder", "searchable": false, "orderable": true},
    {"data": "state",     "name": "state",     "searchable": true,  "orderable": true,
     "search": {"value": "Maine", "regex": false}},
    {"data": "roadway",   "name": "roadway",   "searchable": true,  "orderable": true},
    {"data": "location",  "name": "location",  "searchable": false, "orderable": false}
  ],
  "order": [{"column": 1, "dir": "asc"}, {"column": 0, "dir": "asc"}],
  "start": 0,
  "length": 100,
  "search": {"value": "", "regex": false}
}
```

**Critical**: Only include a `"search"` sub-object on a column when the
filter value is non-empty. Sending `"search": {"value": "", "regex": false}`
causes the server to return 0 filtered results — a server-side bug in the
DataTables handler.

---

## 3. Endpoints Reference

### Map Icons
`GET /map/mapIcons/{layer}`

Returns lightweight position data for all items on a map layer.

| Layer name | Description |
|------------|-------------|
| `Cameras` | All camera positions |
| `Incidents` | Active traffic incidents |
| `Construction` | Road construction |
| `IncidentClosures` | Incident-related closures |
| `ConstructionClosures` | Construction closures |
| `MessageSigns` | Dynamic message signs |
| `WeatherStations` | Weather monitoring stations |
| `WeatherEvents` | Active weather events |
| `WeatherForecast` | Weather forecast zones |
| `FerryTerminals` | Ferry service points |
| `TruckRestrictions` | Weight/height restrictions |
| `DisplayedParking` | Park & ride facilities |
| `Wta` | Travel time segments (Weighted Travel Average) |

**Response shape:**
```json
{
  "item1": {"url": "/Generated/Content/Images/511/map_camera.svg", "size": [29,35], ...},
  "item2": [
    {"itemId": "622", "location": [44.449335, -73.199637], "title": ""},
    ...
  ]
}
```
Note: `location` is `[latitude, longitude]`.

---

### Camera List
`GET /List/GetData/Cameras?query={json}&lang=en`

Full paginated camera data. Use column search on `state` to filter by state.

**Response data item shape:**
```json
{
  "DT_RowId": "622",
  "id": 622,
  "location": "I-189 SOUTH BURLINGTON",
  "roadway": "I-189",
  "direction": "Westbound",
  "state": "Vermont",
  "county": null,
  "city": null,
  "region": null,
  "source": "Vermont",
  "latLng": {
    "geography": {
      "wellKnownText": "POINT (-73.199637 44.449335)"
    }
  },
  "images": [
    {
      "id": 1230,
      "cameraSiteId": 622,
      "imageUrl": "/map/Cctv/1230",
      "imageType": 1,
      "refreshRateMs": 10000,
      "disabled": false,
      "blocked": false
    }
  ],
  "tooltipUrl": "/tooltip/Cameras/622?lang={lang}&noCss=true",
  "visible": true,
  "lastUpdated": "2025-07-17T10:37:41.5327214+00:00"
}
```

---

### Camera Image
`GET /map/Cctv/{imageId}`

Returns a JPEG snapshot of the camera at the time of request.

- `Content-Type: image/jpeg`
- `Cache-Control: max-age=10`
- Returns **0 bytes** (empty body) when the camera is offline or blocked
- Served via AWS CloudFront CDN

---

### Tooltip HTML
`GET /tooltip/{layer}/{itemId}?lang=en&noCss=true`

Returns raw HTML for the map popup dialog. Useful for scraping camera title
and image URL without parsing the full camera list.

---

### Traffic Events
`GET /List/GetData/traffic?query={json}&lang=en`

Same DataTables protocol as cameras. Column `state` supports state filtering.

---

### Message Signs
`GET /List/GetData/MessageSigns?query={json}&lang=en`

Uses different column names than camera/event schema:

| Field | Column name | Notes |
|-------|-------------|-------|
| State/region | `area` | **Not** `state` |
| Roadway | `roadwayName` | **Not** `roadway` |
| Sign label | `name` / `description` | Both present |
| Line 1 | `message` | |
| Line 2 | `message2` | |
| Line 3 | `message3` | |
| Status | `status` | e.g. `"Device Offline"` |

---

## 4. Data Structures

### Camera

```python
@dataclass
class Camera:
    id: int                    # numeric site ID
    location: str              # human-readable location name
    roadway: str               # e.g. "I-95"
    direction: str             # "Northbound", "Southbound", etc.
    state: str                 # "Maine", "Vermont", "New Hampshire"
    county: Optional[str]
    city: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    images: List[CameraImage]  # usually 1, may be multiple for split cameras
    thumbnail_url: Optional[str]  # convenience: full URL of first image
    visible: bool
    last_updated: Optional[str]
```

### CameraImage

```python
@dataclass
class CameraImage:
    id: int                   # imageId used in /map/Cctv/{id}
    camera_site_id: int       # parent Camera.id
    image_url: str            # relative: /map/Cctv/{id}
    full_image_url: str       # absolute: https://newengland511.org/map/Cctv/{id}
    refresh_rate_ms: int      # typically 10000 (10 seconds)
    disabled: bool            # true if camera is disabled by operator
    blocked: bool             # true if feed blocked at source
```

### TrafficEvent

```python
@dataclass
class TrafficEvent:
    id: Any
    description: str          # human-readable event description
    state: Optional[str]
    roadway: Optional[str]
    direction: Optional[str]
    event_type: Optional[str] # "Roadwork", "Incident", etc.
    start_date: Optional[str]
    end_date: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
```

### MessageSign

```python
@dataclass
class MessageSign:
    id: Any
    name: Optional[str]       # sign identifier / label
    roadway_name: Optional[str]
    direction: Optional[str]
    area: Optional[str]       # state/region ("Maine", etc.)
    status: Optional[str]     # "Device Offline" or blank
    message1: Optional[str]   # line 1 of displayed text
    message2: Optional[str]   # line 2
    message3: Optional[str]   # line 3
    last_updated: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
```

---

## 5. Installation & Requirements

- **Python 3.8+**
- **No third-party packages** — uses only Python stdlib:
  `urllib`, `urllib.request`, `urllib.parse`, `urllib.error`,
  `json`, `gzip`, `time`, `dataclasses`, `typing`

```bash
# No installation needed — just copy the file
cp mainedot_client.py /your/project/
```

---

## 6. Quick Start

```python
from mainedot_client import NewEngland511Client, STATE_MAINE

client = NewEngland511Client()

# Get all Maine traffic cameras
cameras = client.get_maine_cameras()
print(f"Found {len(cameras)} Maine cameras")

# Show cameras on I-95
for cam in client.get_cameras(state=STATE_MAINE, roadway="I-95"):
    print(f"{cam.location} ({cam.direction})")
    print(f"  Image: {cam.thumbnail_url}")

# Download a camera snapshot
cam = cameras[0]
if cam.images:
    success = client.save_camera_image(cam.images[0], "camera.jpg")
    print("Saved:", success)

# Get Maine traffic incidents
for event in client.get_maine_traffic_events():
    print(f"[{event.event_type}] {event.description[:80]}")

# Get current Maine message signs
for sign in client.get_maine_message_signs():
    if sign.message1 and sign.message1.strip():
        print(f"{sign.name}: {sign.message1}")
```

---

## 7. Full API Reference

### `NewEngland511Client(base_url, timeout)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_url` | `"https://newengland511.org"` | API base URL |
| `timeout` | `20` | HTTP request timeout in seconds |

---

### Camera Methods

#### `get_camera_map_icons() -> List[MapIcon]`
Fetch lightweight camera positions for all regions (fast, ~5 KB gzipped).
Returns `MapIcon(item_id, latitude, longitude, title)` objects.

#### `get_cameras(state, roadway, page_size, delay) -> List[Camera]`
Fetch full camera data with pagination.

| Parameter | Type | Description |
|-----------|------|-------------|
| `state` | `str`, optional | Filter by state name (use `STATE_*` constants) |
| `roadway` | `str`, optional | Filter by roadway (e.g. `"I-95"`) |
| `page_size` | `int` | Records per request, max 100 |
| `delay` | `float` | Seconds between paginated requests (default 0.25) |

#### `get_maine_cameras(roadway) -> List[Camera]`
Shortcut: `get_cameras(state=STATE_MAINE, roadway=roadway)`.

#### `get_camera_image_bytes(camera_image) -> Optional[bytes]`
Download current JPEG snapshot. Returns `None` if camera is offline/blocked.

#### `save_camera_image(camera_image, path) -> bool`
Download and write JPEG to file. Returns `True` on success.

#### `get_camera_tooltip_html(camera_id) -> str`
Fetch the map popup HTML for a camera (includes image tag and title).

---

### Traffic Event Methods

#### `get_traffic_events(state, page_size, delay) -> List[TrafficEvent]`
Fetch current traffic incidents and roadwork events.

#### `get_maine_traffic_events() -> List[TrafficEvent]`
Shortcut for Maine traffic events.

#### `get_construction_events(state, page_size, delay) -> List[TrafficEvent]`
Fetch active construction events.

---

### Message Sign Methods

#### `get_message_signs(area, roadway, page_size, delay) -> List[MessageSign]`
Fetch dynamic message sign data.

| Parameter | Note |
|-----------|------|
| `area` | State/region filter (same values as `state` in cameras) |
| `roadway` | Filter by `roadwayName` field |

#### `get_maine_message_signs() -> List[MessageSign]`
Shortcut for Maine message signs.

---

### Map Icon Methods

#### `get_map_icons(layer) -> List[MapIcon]`
Fetch map icons for any layer.  Use `MAP_LAYER_*` constants.

---

### Utility Methods

#### `get_all_states() -> List[str]`
Return distinct state names in the camera database.

---

### Constants

```python
# State name strings for filtering
STATE_MAINE          = "Maine"
STATE_NEW_HAMPSHIRE  = "New Hampshire"
STATE_VERMONT        = "Vermont"

# DataTables typeId values
LIST_TYPE_CAMERAS       = "Cameras"
LIST_TYPE_TRAFFIC       = "traffic"
LIST_TYPE_CONSTRUCTION  = "construction"
LIST_TYPE_MESSAGE_SIGNS = "MessageSigns"
LIST_TYPE_TRAVEL_TIMES  = "TravelTimes"

# Map icon layer names
MAP_LAYER_CAMERAS         = "Cameras"
MAP_LAYER_INCIDENTS       = "Incidents"
MAP_LAYER_CONSTRUCTION    = "Construction"
MAP_LAYER_MESSAGE_SIGNS   = "MessageSigns"
MAP_LAYER_WEATHER_STATIONS= "WeatherStations"
MAP_LAYER_WEATHER_EVENTS  = "WeatherEvents"
MAP_LAYER_FERRY_TERMINALS = "FerryTerminals"
MAP_LAYER_TRUCK_RESTRICTIONS = "TruckRestrictions"
MAP_LAYER_TRAVEL_TIMES    = "Wta"
```

---

## 8. Known Quirks & Gotchas

### Gzip Always On
The server sends gzip-compressed responses for all endpoints regardless of
whether the client sends `Accept-Encoding: gzip`. The client detects the
`\x1f\x8b` magic bytes and decompresses automatically.

### Empty Column Search Returns 0 Results
Sending `"search": {"value": "", "regex": false}` on a DataTables column
causes the server to return 0 filtered results — a server-side bug.  The
client only includes the `search` sub-object when the filter value is
non-empty.

### Max 100 Records Per Page
The server silently caps `length` at 100 regardless of what is requested.
The client automatically handles multi-page fetches for `get_cameras()` and
similar methods.

### Message Signs Use Different Column Names
The `MessageSigns` type uses `area` (not `state`) and `roadwayName` (not
`roadway`) as column field names. The `get_message_signs()` method handles
this transparently via a separate query builder.

### Camera Images Can Be Empty (0 Bytes)
When a camera is offline or its feed is blocked at the source, the image
endpoint returns HTTP 200 with an empty body (`content-length: 0`).  The
client returns `None` in this case.

### Some Cameras Return No Location Data
Maine camera names use an internal code convention like `"95 SS 2.4 CCTV AX
MTA"` (I-95 Southbound, mile 2.4, etc.) rather than place names.  The `city`
and `county` fields are often `null` for Maine cameras.

### Total vs Filtered Record Count
The DataTables response includes both `recordsTotal` (total in DB) and
`recordsFiltered` (matching current filter). When filtering by state, the
pagination loop uses `recordsFiltered` as the stopping condition.

### Travel Times (WTA)
The `Wta` map layer serves travel time segment data. The corresponding list
typeId is `TravelTimes` but the response schema differs from cameras/events.
This client does not parse travel times; raw data is accessible via
`_fetch_list_page("TravelTimes")`.

---

## 9. Rate Limiting & Etiquette

- The site serves public infrastructure information and has no documented API
  rate limits.
- The default `delay=0.25` between paginated requests is a courtesy to avoid
  overloading the server.
- Camera images have `Cache-Control: max-age=10`, so polling more frequently
  than every 10 seconds provides no benefit.
- Identify your application in a custom `User-Agent` when building production
  scrapers.

---

## 10. Live Test Results

Tested against live endpoints on **2026-03-27**:

| Test | Result |
|------|--------|
| Map icons (all cameras) | 408 cameras total |
| Maine cameras (paginated) | **134 cameras** across 2 pages |
| Maine I-95 cameras | 56 cameras |
| Camera image download | 31,501 bytes JPEG — confirmed live |
| Maine traffic events | 59 active events |
| Maine message signs | 256 signs (area="Maine" filter) |
| Available states | Maine, New Hampshire, Vermont |

### Sample Maine Camera Data

```
ID=1580  |  95 SS 2.4 CCTV AX MTA  |  I-95 Southbound  |  Maine
  Image: https://newengland511.org/map/Cctv/2188  (refresh 10s)

ID=1583  |  95 NN 13.4 CCTV AX T   |  I-95 Northbound  |  Maine
  Image: https://newengland511.org/map/Cctv/2191  (refresh 10s)
```

### Sample Maine Traffic Event

```
[Roadwork] Old Town Stillwater Avenue, the Llewellyn Estes Bridge
           has been posted to 30 Ton
```

---

## Running the Demo

```bash
python3 mainedot_client.py
```

The `main()` function runs all seven tests against live endpoints and prints
results to stdout. No files are written unless a camera image download test
saves `camera.jpg` (it does not by default — bytes are read but not saved).
