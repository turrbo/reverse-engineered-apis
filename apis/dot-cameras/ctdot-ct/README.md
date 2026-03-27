# CTDOT / CT Travel Smart Traffic Camera Client

Reverse-engineered Python client for the Connecticut Department of Transportation
traffic information system at **https://www.ctroads.org** (CT Travel Smart).

No API key is required. The client uses only Python stdlib (`urllib`, `json`,
`gzip`, `dataclasses`).

---

## Quick Start

```bash
# List all I-95 cameras
python3 ctdot_client.py cameras --roadway I-95

# Current traffic events
python3 ctdot_client.py events

# Variable message signs on I-84
python3 ctdot_client.py signs --roadway I-84

# Download a camera snapshot
python3 ctdot_client.py snapshot 536 --output greenwich_i95.jpg

# Full live demo
python3 ctdot_client.py demo
```

---

## Reverse Engineering Notes

### Target sites

| Site | URL | Notes |
|------|-----|-------|
| CT Travel Smart | https://www.ctroads.org | Primary public-facing site |
| CT Travel Smart (redirect) | https://www.cttravelsmart.org | Redirects to ctroads.org |
| CTDOT portal | https://portal.ct.gov/dot | Government portal, links to ctroads.org |

### Discovery methodology

1. **Page HTML** – `GET /map` and `GET /cctv` were fetched to identify all
   `<script src>` bundles and `data-*` attributes on layer checkbox elements.

2. **JavaScript bundles analysed**:
   - `/bundles/map` – route planner, `CameraLocater`, `zoomToCamera`, camera
     carousel logic, `data-jsonurl` attributes per layer
   - `/bundles/map511` – `/Api/Route/SaveUserRoute`, `/api/route/getroutes`,
     layer toggle system
   - `/bundles/511GoogleMapComp` – `apiUrls`, `tooltipBaseUrls`, feed loader
   - `/bundles/listCctv` – `/Camera/GetVideoUrl`, carousel/video logic
   - `/bundles/datatables` – `/List/GetData/`, `/List/GetMyCameras/`,
     `/Camera/AddMyCameraList`, `/Camera/SaveMyCameras`
   - `/scripts/jsresources/map/map` – `resources.*` variables including
     `SearchHereApiKey`, `Nearby511Kml`, `MapLibreTilesURL`
   - `/scripts/jsresources/List/listResources` – display config, refresh rates

3. **`data-*` attributes** on `/map` layer checkboxes:
   ```
   data-jsonurl="/map/mapIcons/Cameras"
   data-tooltipbaseurl="/tooltip/{layerId}/{id}?lang={lang}"
   data-tileurlformat="https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}"
   data-feedurl="http://ctroads.org/Content/CT/KML/town_boundaries.kmz"
   ```

4. **Live endpoint probing** – each discovered URL was tested with `curl`/
   `urllib.request`. Gzip-compressed responses (indicated by `\x1f\x8b` magic
   bytes) were handled transparently.

### Key findings

- **No authentication** is required for any public read endpoint.
- All camera images are served through **AWS CloudFront** (confirmed by
  `x-amz-cf-id` response headers). Response is `image/jpeg` regardless of
  whether the camera is online; offline cameras return 0 bytes with HTTP 200.
- The site is built on **ASP.NET MVC** with a **DataTables** server-side
  pagination pattern. The `/List/GetData/{layer}` endpoints accept standard
  DataTables POST parameters (`draw`, `start`, `length`).
- Camera data is provided by **Trafficland** (field: `"source": "TRAFFICLAND"`).
- Traffic tile overlays are served by **ibi511.com** (`tiles.ibi511.com`).
- Map tiles use **MapLibre** via `stg.map-tiles.traveliq.co`.
- The Google Maps API key embedded in the page is
  `AIzaSyD-7f8VgXp8uGoagHnCDFmC7VGBEu5ceWg` (public, browser-restricted).
- The HERE search key is `kkq87qzo7t3EbQMlTXlaKWnNM7vmYibqrzcbmXjYqM0`.

---

## API Endpoint Reference

### Base URL

```
https://www.ctroads.org
```

---

### Cameras

#### GET /map/mapIcons/Cameras

Returns lightweight map-icon entries (ID + coordinates) for all 347 cameras.

**Request**
```
GET /map/mapIcons/Cameras
Accept-Encoding: gzip
```

**Response** (JSON, gzip-compressed)
```json
{
  "item1": {
    "url": "/Generated/Content/Images/511/map_camera.svg",
    "size": [29, 35],
    "origin": [0, 0],
    "anchor": [12, 34],
    "zindex": 0,
    "preventClustering": false,
    "isClickable": true,
    "rotation": 0
  },
  "item2": [
    {
      "itemId": "308",
      "location": [41.823175, -72.501513],
      "icon": { "size": [29, 35], "anchor": [12, 34], ... },
      "title": ""
    }
  ]
}
```

`location` is `[latitude, longitude]`. `item2` contains all camera icons.

---

#### POST /List/GetData/Cameras

Full camera records with metadata, roadway, city, images, and coordinates.
Uses DataTables server-side pagination; the server caps results at 100 per page.

**Request**
```
POST /List/GetData/Cameras
Content-Type: application/x-www-form-urlencoded

draw=1&start=0&length=100
```

Additional DataTables parameters (`columns[]`, `order[]`, `search[value]`) are
accepted but not required for a basic listing.

**Response** (JSON)
```json
{
  "draw": 1,
  "recordsTotal": 347,
  "recordsFiltered": 347,
  "data": [
    {
      "DT_RowId": "308",
      "tooltipUrl": "/tooltip/Cameras/308?lang={lang}&noCss=true",
      "id": 308,
      "sourceId": "404296",
      "source": "TRAFFICLAND",
      "type": "ConnDOT",
      "areaId": "VE",
      "sortOrder": 84728174,
      "roadway": "I-84",
      "direction": "Westbound",
      "location": "CAM 1 Vernon I-84 WB Exit 64 - Rt. 30 & 83 (Hartford Tpke.)",
      "latLng": {
        "geography": {
          "coordinateSystemId": 4326,
          "wellKnownText": "POINT (-72.501513 41.823175)"
        }
      },
      "city": "Vernon",
      "county": null,
      "region": null,
      "state": "Connecticut",
      "country": "United States",
      "sortIdDisplay": "84 - 72.8174",
      "images": [
        {
          "id": 308,
          "cameraSiteId": 308,
          "description": "Traffic closest to the camera is traveling WEST",
          "imageUrl": "/map/Cctv/308",
          "imageType": 0,
          "refreshRateMs": 10000,
          "videoUrl": null,
          "videoType": null,
          "isVideoAuthRequired": true,
          "videoDisabled": false,
          "disabled": false,
          "blocked": false
        }
      ],
      "created": "2025-04-29T10:00:00.9166667+00:00",
      "lastUpdated": "2025-04-29T10:00:00.9166667+00:00"
    }
  ]
}
```

**Notable fields**

| Field | Description |
|-------|-------------|
| `images[].imageUrl` | Relative path for the JPEG snapshot, e.g. `/map/Cctv/308` |
| `images[].refreshRateMs` | Client-side refresh rate (default 10,000 ms) |
| `images[].blocked` | `true` if the source blocks external requests |
| `latLng.geography.wellKnownText` | WKT POINT with lon, lat |
| `sortIdDisplay` | Route number and mile-marker string |

---

#### GET /map/Cctv/{camera_id}

Live JPEG snapshot for a single camera.

**Request**
```
GET /map/Cctv/308
```

**Response**
- Content-Type: `image/jpeg`
- Served via AWS CloudFront
- Size: typically 10–30 KB for active cameras; 0 bytes for offline cameras
- HTTP 200 is returned even for offline cameras (empty body)
- The site appends a cache-busting hash: `/map/Cctv/308#<timestamp>`

**CDN headers observed**
```
x-amzn-requestid: 64cdd495-...
access-control-allow-origin: *
cache-control: public, no-store, max-age=0
via: 1.1 b7dd001578b73a6989e710df24ccc0ce.cloudfront.net (CloudFront)
x-amz-cf-pop: IAD55-P10
```

---

#### POST /Camera/GetLatLng

Returns the latitude/longitude of a single camera by ID.

**Request**
```
POST /Camera/GetLatLng?id=308
Content-Type: application/x-www-form-urlencoded
(empty body)
```

**Response**
```json
{
  "latitude": 41.823175,
  "longitude": -72.501513
}
```

---

### Traffic Events

#### GET /map/mapIcons/{layer}

Returns lightweight map-icon entries for a given event layer.

**Supported layers**

| Layer | Description |
|-------|-------------|
| `Incidents` | Road incidents (crashes, hazards) |
| `Closures` | Road closures |
| `Construction` | Active construction zones |
| `Congestion` | Traffic delays / queue warnings |
| `TransitIncidents` | Transit-related incidents |
| `TransitConstruction` | Transit-related construction |
| `WeatherAlerts` | Weather-related alerts |
| `WeatherIncidents` | Weather incidents |
| `WeatherForecast` | Weather forecast station locations |
| `MessageSigns` | Variable message sign locations |

**Request**
```
GET /map/mapIcons/Congestion
```

**Response** (same structure as Cameras icon endpoint)
```json
{
  "item1": { ... },
  "item2": [
    {
      "itemId": "40403",
      "location": [41.041648, -73.576262],
      "icon": { ... },
      "title": ""
    }
  ]
}
```

---

#### POST /List/GetData/traffic

All active traffic events across all layers in a single response.

**Request**
```
POST /List/GetData/traffic
Content-Type: application/x-www-form-urlencoded

draw=1&start=0&length=500
```

**Response**
```json
{
  "draw": 1,
  "recordsTotal": 14,
  "recordsFiltered": 14,
  "data": [
    {
      "DT_RowId": "40403",
      "tooltipUrl": "/tooltip/Congestion/40403?lang={lang}&noCss=true",
      "id": 40403,
      "type": "Delays",
      "layerName": "Congestion",
      "roadwayName": "I-95",
      "description": "GREENWICH - Delays. I-95 Southbound is congested between Exits 5 and 3 (3.0 miles). Reported Friday, March 27 at 2:24 pm.",
      "sourceId": "32726018",
      "source": "ConnDOT",
      "eventSubType": "Queue",
      "startDate": "3/27/26, 12:12 PM",
      "endDate": null,
      "lastUpdated": "3/27/26, 4:28 PM",
      "isFullClosure": false,
      "severity": "minor",
      "direction": "Southbound",
      "locationDescription": "at Exit 5 (US 1)",
      "detourDescription": null,
      "laneDescription": null,
      "widthRestriction": null,
      "heightRestriction": null,
      "majorEvent": null,
      "region": "Southwestern Connecticut/New Haven",
      "state": "Connecticut",
      "showOnMap": true,
      "estimatedDuration": "Unknown"
    }
  ]
}
```

**`type` and `layerName` values observed**

| type | layerName |
|------|-----------|
| `Delays` | `Congestion` |
| `Closure` | `Closures` |
| `Construction` | `Construction` |
| `Accident` | `Incidents` |

---

#### POST /List/GetData/{layer}

Layer-specific event listing using the same DataTables protocol. The `traffic`
endpoint (above) aggregates all layers.

Individual layer endpoints (`/List/GetData/Incidents`,
`/List/GetData/Construction`, etc.) may return HTTP 500 when the layer has
zero active events.

---

### Variable Message Signs

#### GET /map/mapIcons/MessageSigns

Icon locations for all 134 VMS/DMS signs (same format as camera icons).

---

#### POST /List/GetData/MessageSigns

Full VMS sign data including current messages.

**Request**
```
POST /List/GetData/MessageSigns
Content-Type: application/x-www-form-urlencoded

draw=1&start=0&length=100
```

**Response**
```json
{
  "draw": 1,
  "recordsTotal": 134,
  "data": [
    {
      "DT_RowId": "46",
      "tooltipUrl": "/tooltip/MessageSigns/46?lang={lang}&noCss=true",
      "roadwayName": "I-84",
      "direction": "Eastbound",
      "name": "84E Waterbury W/O Exit 18",
      "area": "N/A",
      "description": "84E Waterbury W/O Exit 18",
      "message": "TO EXIT 25A<br/>6 MILES<br/>6 MIN",
      "message2": "",
      "message3": "",
      "phase1Image": null,
      "phase2Image": null,
      "status": "OK",
      "lastUpdated": "3/27/26, 4:52 PM"
    }
  ]
}
```

`message` fields contain HTML `<br/>` line separators. Multiple display phases
use `message`, `message2`, `message3`.

---

### Tooltip / Detail HTML

#### GET /tooltip/{layer}/{id}?lang={lang}

Returns an HTML fragment with detailed information for any map item.
This is the same content the map popup displays on icon click.

**Supported layers**: `Cameras`, `Congestion`, `Incidents`, `Closures`,
`Construction`, `MessageSigns`, `WeatherForecast`, `WeatherAlerts`, etc.

**Request**
```
GET /tooltip/Cameras/308?lang=en
```

**Response** (HTML fragment, not a full page)
```html
<div class="map-tooltip camTooltip">
  <h4><img src="/Content/Images/ic_camera.svg" alt="Camera" /> Camera</h4>
  <table class="table-condensed table-striped">
    <tbody>
      <tr>
        <td colspan="2">
          <strong>CAM 1 Vernon I-84 WB Exit 64 - Rt. 30 &amp; 83</strong>
        </td>
      </tr>
      <tr>
        <td colspan="2">
          <div class="cctvCameraCarousel setVisibility">
            <div id="carouselDiv-308">
              <div class="dirDescHeader">Traffic closest to the camera is traveling WEST</div>
              <img class="carouselCctvImage cctvImage"
                   data-lazy="/map/Cctv/308"
                   data-refresh-rate="10000"
                   id="308img"
                   alt="CAM 1 Vernon I-84 WB..." />
            </div>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

The `data-lazy` attribute in the camera tooltip HTML gives the image URL.

---

### Weather Forecast

#### GET /map/mapIcons/WeatherForecast

Returns 8 weather station locations for Connecticut (same icon format).

**Station IDs observed**: `CTC001` through `CTC015` (not all present).

Use `GET /tooltip/WeatherForecast/{station_id}?lang=en` to fetch a 5-day
forecast HTML table for any station.

---

### Traffic Speed Tiles

#### GET https://tiles.ibi511.com/Geoservice/GetTrafficTile

Traffic speed overlay tiles using standard XYZ slippy-map addressing.

```
GET https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
```

Tiles are PNG images. Empty tiles (0 bytes) are returned for areas without
traffic data.

---

### KML Feeds

#### GET http://ctroads.org/Content/CT/KML/town_boundaries.kmz

KMZ file containing Connecticut town boundary polygons.

---

### Additional Endpoints (Authenticated / Not Used by Default)

These endpoints were discovered in the JS bundles but require user login:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/My511/Login` | POST | User login |
| `/Camera/GetUserCameraLists` | GET | Retrieve saved camera views (auth) |
| `/Camera/AddMyCameraList` | POST | Create a new camera view (auth) |
| `/Camera/SaveMyCameras` | POST | Save cameras to a view (auth) |
| `/List/GetMyCameras/` | POST | List cameras in saved view (auth) |
| `/api/route/getroutes` | POST | Saved route listing (auth) |
| `/Api/Route/SaveUserRoute` | POST | Save a route (auth) |
| `/Camera/GetVideoUrl?imageId={id}` | GET | Video stream URL for camera |

---

## Camera Coverage by Highway

As of the reverse-engineering date (2026-03-27), there were **347 active cameras**:

| Highway | Count | Notes |
|---------|-------|-------|
| I-95 | 99 | Greenwich to New Haven and beyond |
| I-84 | 91+ | Danbury to Hartford and east |
| I-91 | 68 | Springfield border to New Haven |
| I-691 | 12 | Cheshire / Meriden / Southington |
| I-395 | 5 | Southeastern CT |
| RT 9 | ~30 | New Britain to I-91 |
| RT 15 (Merritt) | 3 | Stratford / Milford only |
| RT 66, RT 72, RT 8 | misc | Secondary roads |
| I-291, I-796 | 1 each | Short connectors |

**Note**: The Merritt Parkway (RT 15) has very limited camera coverage (3 cameras
only at the southern end near Milford/Stratford). Most of the Merritt does not
have CTDOT-operated traffic cameras.

---

## Python Client Reference

### Installation

No external dependencies. Python 3.8+ required.

```bash
python3 ctdot_client.py --help
```

### Programmatic Usage

```python
from ctdot_client import CTDOTClient, HIGHWAY_I95, HIGHWAY_I84

client = CTDOTClient()

# --- Cameras ---

# All cameras (paginated automatically, returns all 347)
all_cameras = client.get_cameras()

# Highway-specific convenience methods
i95_cams = client.get_i95_cameras()   # 99 cameras
i84_cams = client.get_i84_cameras()   # 91 cameras
i91_cams = client.get_i91_cameras()   # 68 cameras
merritt   = client.get_merritt_cameras()  # 3 cameras

# Filter by roadway string (substring match)
rt9_cams = client.get_cameras(roadway="RT 9")

# Filter by city
norwalk = client.get_cameras(city="Norwalk")

# Camera snapshot (returns JPEG bytes)
jpeg = client.get_camera_snapshot(536)
with open("cam.jpg", "wb") as f:
    f.write(jpeg)

# Camera lat/lon (fast single-item lookup)
lat, lon = client.get_camera_latlon(536)

# Continuous polling (yields every 10 seconds)
for cam_id, ts, jpeg in client.iter_camera_snapshots([536, 537, 538]):
    print(f"Camera {cam_id}: {len(jpeg)} bytes at {ts}")

# --- Traffic Events ---

events = client.get_traffic_events()
i95_events = client.get_traffic_events(roadway="I-95")
congestion = client.get_congestion()
incidents  = client.get_incidents()

# --- Message Signs ---

all_signs = client.get_message_signs()
i84_signs = client.get_message_signs(roadway="I-84")

for sign in i84_signs:
    print(sign.name, sign.message_text)  # message_text strips <br/>

# --- Weather Forecast ---

stations = client.get_weather_forecast_locations()
# Get HTML forecast for first station
html = client.get_tooltip_html("WeatherForecast", stations[0].item_id)

# --- Generic Tooltip ---

camera_html = client.get_tooltip_html("Cameras", "308")
event_html  = client.get_tooltip_html("Congestion", "40403")
sign_html   = client.get_tooltip_html("MessageSigns", "46")
```

### CLI Reference

```
usage: ctdot_client.py [-h] {cameras,events,signs,snapshot,demo} ...

subcommands:
  cameras   List traffic cameras
    --roadway ROADWAY    Filter by roadway, e.g. I-95
    --city CITY          Filter by city name
    --json               Output JSON

  events    List traffic events
    --roadway ROADWAY    Filter by roadway
    --json               Output JSON

  signs     List variable message signs
    --roadway ROADWAY    Filter by roadway
    --json               Output JSON

  snapshot  Download camera snapshot
    camera_id            Camera ID (integer)
    -o, --output FILE    Output file (default: {id}.jpg)

  demo      Run full live demo
```

### JSON output example

```bash
python3 ctdot_client.py cameras --roadway I-95 --json | python3 -m json.tool | head -30
```

```json
[
  {
    "id": 536,
    "roadway": "I-95",
    "direction": "Southbound",
    "location": "CAM 2 Greenwich I-95 SB N/O Exit 2 - N/O Delavan Ave.",
    "city": "Greenwich",
    "latitude": 41.041648,
    "longitude": -73.576262,
    "snapshot_url": "https://www.ctroads.org/map/Cctv/536",
    "source": "TRAFFICLAND"
  },
  ...
]
```

---

## Data Model Summary

### Camera

```python
@dataclass
class Camera:
    id: int                      # Camera site ID
    source_id: str               # Trafficland source ID
    source: str                  # Always "TRAFFICLAND"
    type: str                    # "ConnDOT"
    roadway: str                 # "I-95", "I-84", "RT 15", etc.
    direction: str               # "Northbound", "Southbound", etc.
    location: str                # Human-readable description
    latitude: float
    longitude: float
    city: str
    county: Optional[str]
    region: Optional[str]
    state: str                   # "Connecticut"
    sort_id_display: str         # "95 - 1.0" (route - mile marker)
    images: List[CameraImage]
    created: Optional[str]
    last_updated: Optional[str]
```

### CameraImage

```python
@dataclass
class CameraImage:
    id: int
    camera_site_id: int
    description: str             # Direction of travel note
    image_url: str               # "/map/Cctv/{id}"
    full_image_url: str          # Absolute URL (property)
    cache_bust_url: str          # URL with ?t={timestamp} (property)
    refresh_rate_ms: int         # 10000
    video_url: Optional[str]     # Usually null
    video_type: Optional[str]    # HLS stream type if present
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool                # True = source blocks external access
```

### TrafficEvent

```python
@dataclass
class TrafficEvent:
    id: int
    type: str                    # "Delays", "Closure", "Construction"
    layer_name: str              # "Congestion", "Incidents", "Closures"
    roadway_name: str            # "I-95", "RT-15", etc.
    description: str             # Full text description
    source_id: str               # External source ID
    source: str                  # "ConnDOT"
    event_sub_type: Optional[str] # "Queue", "Accident", etc.
    start_date: Optional[str]
    end_date: Optional[str]
    last_updated: Optional[str]
    is_full_closure: bool
    severity: str                # "minor", "major", "unknown"
    direction: str
    location_description: Optional[str]
    lane_description: Optional[str]
    detour_description: Optional[str]
    region: Optional[str]
    state: str
    show_on_map: bool
    estimated_duration: Optional[str]
```

### MessageSign

```python
@dataclass
class MessageSign:
    id: int
    roadway_name: str            # "I-84", "I-95", etc.
    direction: str               # "Eastbound", "Westbound", etc.
    name: str                    # Sign identifier, e.g. "84E Waterbury W/O Exit 18"
    area: str                    # "N/A" or county/area name
    description: str
    message: str                 # Primary message (may contain <br/>)
    message2: str                # Secondary phase
    message3: str                # Tertiary phase
    status: str                  # "OK", "ERROR"
    last_updated: Optional[str]
    message_text: str            # Plain text, <br/> replaced with \n (property)
```

---

## Refresh Rates and Caching

| Data type | Refresh rate | Notes |
|-----------|-------------|-------|
| Camera snapshots | 10 seconds | `resources.CameraRefreshRateMs = '10000'` |
| Alert bar | 30 seconds | `resources.AlertRefreshInterval = '30000'` |
| CMS content | 30 seconds | `/cms/gethtmlcontent` poller |
| Map icons (events) | 30 seconds | JS timer in layer refresh system |

The `/map/mapIcons/{layer}` endpoint accepts a `?t={unix_timestamp_rounded_to_5min}`
parameter to support CDN caching at the 5-minute level. The client does not
require this parameter.

---

## Technical Stack (Site)

| Component | Technology |
|-----------|-----------|
| Backend framework | ASP.NET MVC (C#) |
| Camera image delivery | AWS CloudFront CDN |
| Map tiles | Google Maps (quarterly channel) + MapLibre |
| Traffic tile overlay | ibi511.com (`tiles.ibi511.com`) |
| Location search | HERE Maps (`kkq87qzo7t3EbQMlTXlaKWnNM7vmYibqrzcbmXjYqM0`) |
| Camera data provider | Trafficland (sourceId matches Trafficland IDs) |
| Traffic data provider | ConnDOT (Connecticut DOT) |
| Frontend table library | DataTables (server-side mode) |
| Map library | Google Maps + MapLibre (dual mode) |
| Analytics | Google Tag Manager (AW-794307424, G-858R957J72) |

---

## Notes and Limitations

1. **Camera snapshots may be empty** – A camera returning `image/jpeg` with
   0 bytes is offline, blocked at the source, or temporarily unavailable.
   The `blocked` field in `CameraImage` indicates cameras where the source
   (Trafficland) blocks external access.

2. **No video streams publicly available** – `resources.CctvEnableVideo = 'False'`
   is set site-wide. The `/Camera/GetVideoUrl` endpoint returns an empty string
   for all cameras.

3. **I-95 cameras under the Merritt Pkwy label** – The roadway field uses
   `"RT-15"` (with hyphen) in event data but `"RT 15"` (with space) in camera
   data. Filter accordingly.

4. **DataTables pagination** – The server hard-caps at 100 records per request.
   The client handles this automatically through transparent pagination.

5. **Rate limiting** – No rate limiting was observed during development, but
   respectful polling is recommended. The site's own JavaScript uses 10-second
   refresh intervals for camera images and 30-second intervals for events.

6. **CORS** – The camera image endpoint returns `Access-Control-Allow-Origin: *`,
   so images can be fetched from browser JavaScript without CORS restrictions.

7. **Travel times** – The `/traveltimes` page and `/List/GetData/TravelTimes`
   endpoint return HTTP 500 (feature may require authentication or be disabled).

8. **No GeoJSON feed** – No public GeoJSON feed was discovered. Camera
   coordinates are available via the list endpoint (WKT format) or the
   mapIcons endpoint (lat/lon array).
