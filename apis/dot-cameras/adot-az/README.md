# ADOT AZ511 Traffic Information Client

A production-quality Python client for the Arizona Department of Transportation
(ADOT) AZ511 traveler information system at **https://www.az511.gov**.

All endpoints were reverse-engineered from the public web application's
JavaScript bundles and observed XHR/fetch network calls.  **No API key or
authentication is required** for any read-only operation.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Quick Start](#quick-start)
4. [Discovered Endpoints](#discovered-endpoints)
5. [API Reference](#api-reference)
6. [CLI Reference](#cli-reference)
7. [Data Models](#data-models)
8. [CDN & Tile Patterns](#cdn--tile-patterns)
9. [Reverse-Engineering Notes](#reverse-engineering-notes)
10. [Rate Limiting & Etiquette](#rate-limiting--etiquette)
11. [Known Limitations](#known-limitations)

---

## Features

- **604 live traffic cameras** — JPEG snapshots served from CloudFront, refreshed every 30 s
- **Active incidents**, construction zones, road closures, and special events
- **Dynamic message signs** (DMS/VMS) with current sign text
- **NWS weather alerts** including dust storm warnings, wind advisories
- **7-day weather forecasts** per NWS forecast zone
- **US–Mexico border crossing** wait times (CBP data)
- **Rest area** facility/amenity information
- **Truck restrictions** with width/height/weight limits
- **Traffic speed overlay tiles** (IBI511/TravelIQ CDN)
- **Weather radar overlay tiles** (animated, multi-frame)
- **Milepost WMS tiles**
- Stdlib-only — no third-party dependencies
- Fully typed dataclasses with docstrings
- CLI demo for every data type

---

## Requirements

- Python 3.8 or later
- No third-party packages — uses only `urllib`, `json`, `gzip`, `dataclasses`

---

## Quick Start

```bash
# Clone / download adot_client.py then:

# List all camera markers (fast, single request)
python3 adot_client.py cameras

# Detail for camera site 646 (I-17 @ Flagstaff, 2 viewpoints)
python3 adot_client.py camera 646

# Download a live camera snapshot (JPEG, 1920×1080)
python3 adot_client.py save-image 693 /tmp/i17_flagstaff.jpg

# Active incidents statewide
python3 adot_client.py incidents

# 7-day forecast for Coconino County
python3 adot_client.py weather-forecast AZZ006

# Dynamic message signs (live DMS text)
python3 adot_client.py signs

# Border crossing wait times
python3 adot_client.py crossings
```

**Use as a library:**

```python
from adot_client import ADOT511Client

client = ADOT511Client()

# All camera markers (~1 request)
markers = client.list_camera_markers()
print(f"{len(markers)} cameras found")

# Full detail for a specific camera
cam = client.get_camera(646)
print(cam.location, cam.roadway)
for img in cam.images:
    print(img.description, img.full_image_url)

# Download camera image
client.save_camera_image(693, "/tmp/i17_sb.jpg")

# I-10 corridor cameras (fetches detail for each)
i10 = client.cameras_by_corridor("I-10")

# Active incidents
for incident in client.list_incidents():
    if incident.severity in ("Major", "Moderate"):
        print(incident.roadway, incident.description[:80])

# Current DMS messages
for sign in client.list_message_signs():
    if "AIRPORT" in sign.messages or "DELAY" in sign.messages.upper():
        print(sign.name, sign.messages)

# Weather forecast (NWS zones)
forecast = client.get_weather_forecast("AZZ023")  # Maricopa County
for period in forecast.periods[:4]:
    print(f"{period.name}: {period.temperature}°F  {period.short_forecast}")

# Border crossing delays
for xing in client.list_border_crossings():
    print(f"{xing.name}: passenger={xing.passenger_delay}")
```

---

## Discovered Endpoints

All endpoints are served from `https://www.az511.gov` unless otherwise noted.

### Map Icons (lightweight markers)

Returns all map marker positions for a given layer in a single response.

```
GET /map/mapIcons/{layer}
```

**Layers:** `Cameras`, `Incidents`, `Construction`, `Closures`, `MessageSigns`,
`WeatherEvents`, `WeatherForecast`, `RestAreas`, `RestAreaClosed`,
`SpecialEvents`, `TruckRestrictions`, `MajorCrossings`

**Response schema:**
```json
{
  "item1": { "url": "/Generated/Content/Images/511/map_camera.svg", "size": [29, 35], ... },
  "item2": [
    { "itemId": "635", "location": [35.172449, -114.566108], "icon": {...}, "title": "" },
    ...
  ]
}
```

### Item Detail

```
GET /map/data/{layer}/{item_id}
```

Returns full detail for a single item.  Schema varies by layer (see
[Data Models](#data-models)).

**Example:**
```
GET /map/data/Cameras/646
GET /map/data/Incidents/711854
GET /map/data/MessageSigns/6891
GET /map/data/WeatherForecast/AZZ006
```

### Camera Image (live JPEG snapshot)

```
GET /map/Cctv/{cctv_image_id}
```

- Returns a live JPEG (`Content-Type: image/jpeg`)
- Served via **CloudFront** → **AWS Lambda@Edge** proxy
- `Cache-Control: max-age=30` — images refresh every 30 seconds
- `Last-Modified` header reflects capture time
- Resolution observed: **1920×1080**
- `cctv_image_id` comes from `images[].id` inside a camera detail response
  (this is **different** from the camera site ID)

**Example:**
```
GET https://www.az511.gov/map/Cctv/682
GET https://www.az511.gov/map/Cctv/693
```

### Weather Radar Tile

```
GET /map/weatherRadar/{z}/{x}/{y}?frame={n}
```

- Returns transparent PNG overlay tile
- `Imagedate` response header contains UTC timestamp of radar scan
- `Cache-Control: public, max-age=300`
- `frame=0` is the most recent; increment for older frames (animation)
- 204 No Content response indicates no radar data for that tile/frame

**Example:**
```
GET https://www.az511.gov/map/weatherRadar/12/803/1651?frame=0
```

### Traffic Speed Tile

```
GET https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
```

- Returns transparent PNG overlay tile (traffic speed colours)
- Served by IBI511/TravelIQ CDN via CloudFront
- **Requires `Referer: https://www.az511.gov/` header** (CORS enforcement)
- `Cache-Control: public, max-age=60`

### Milepost WMS Tile

```
GET /map/mapWMS/MileMarkers/{z}/{x}/{y}
```

Served by a GeoServer instance (`Jetty/9.4.52`). Returns WMS PNG tiles.

### Polyline / Shape Data

For layers with polyline support (`Construction`, `Incidents`, `Closures`,
`SpecialEvents`, `TruckRestrictions`), the detail response includes:

```json
{
  "polyline": "ay|iEpfbiTIySAuEG}EEyH...",
  "detourPolyline": "...",
  "secondaryLatLng": { "geography": { "wellKnownText": "POINT (...)" } }
}
```

The `polyline` field uses **Google Maps encoded polyline format**.

For weather event polygons (`WeatherEvents`), the response includes:

```json
{
  "geom": {
    "geography": {
      "wellKnownText": "POLYGON ((-109.6 32.4, ...))"
    }
  }
}
```

### Authentication Endpoints (not implemented — requires login)

These were observed in the JavaScript source but require an AZ511 account:

| Endpoint | Method | Description |
|---|---|---|
| `/My511/Login` | POST | User login |
| `/Camera/AddMyCameraList` | POST | Create saved camera list |
| `/Camera/SaveMyCameras` | POST | Add camera to saved list |
| `/My511/ResendUserConfirmation` | POST | Resend email confirmation |

---

## API Reference

### `ADOT511Client`

```python
ADOT511Client(timeout: int = 20)
```

#### Cameras

| Method | Description |
|---|---|
| `list_camera_markers()` | All 600+ camera positions (1 request, lightweight) |
| `get_camera(id)` | Full camera detail with images list |
| `list_cameras(max_cameras, delay)` | All cameras with full detail (slow, N requests) |
| `cameras_by_corridor(corridor)` | Cameras filtered by roadway name substring |
| `get_camera_image(cctv_image_id)` | Download live JPEG as bytes |
| `save_camera_image(cctv_image_id, path)` | Download and save JPEG to disk |

#### Traffic Events

| Method | Description |
|---|---|
| `list_incidents()` | Active traffic incidents |
| `list_construction()` | Active construction zones |
| `list_closures()` | Active road closures |
| `list_special_events()` | Active special events |
| `list_truck_restrictions()` | Active truck restrictions |
| `get_event_polyline(layer, id)` | Encoded polyline for an event |

#### Dynamic Message Signs

| Method | Description |
|---|---|
| `list_message_signs()` | All DMS/VMS with current text |
| `get_message_sign(id)` | Single sign detail |

#### Weather

| Method | Description |
|---|---|
| `list_weather_events()` | Active NWS alerts/advisories |
| `list_weather_forecast_zones()` | All NWS forecast zone markers |
| `get_weather_forecast(zone_id)` | 7-day forecast for a zone |
| `get_weather_radar_tile(x, y, z, frame)` | Download radar tile PNG |
| `get_traffic_tile(x, y, z)` | Download traffic speed tile PNG |

#### Infrastructure

| Method | Description |
|---|---|
| `list_rest_areas(include_closed)` | Rest areas with amenity info |
| `list_border_crossings()` | US-Mexico border crossing waits |

#### Tile URLs

| Method | Description |
|---|---|
| `traffic_tile_url_template()` | IBI511 tile URL template |
| `weather_radar_tile_url_template(frame)` | Radar tile URL template |
| `milepost_tile_url_template()` | Milepost WMS URL template |

#### Low-level

| Method | Description |
|---|---|
| `get_detail(layer, item_id)` | Raw JSON detail for any item |

---

## CLI Reference

```
python3 adot_client.py <command> [args]

cameras                       List all camera markers (fast)
camera <id>                   Full camera site detail
incidents                     Active incidents statewide
construction                  Active construction zones
closures                      Active road closures
weather-events                Active NWS weather alerts
weather-forecast <zone_id>    7-day forecast (e.g. AZZ006, AZZ023, AZZ028)
signs                         All dynamic message signs with current text
sign <id>                     Single DMS detail
rest-areas                    Rest area facilities
crossings                     US-Mexico border crossing wait times
special-events                Special events
truck-restrictions            Truck size/weight restrictions
save-image <cctv_id> <path>   Download camera JPEG to file
tile-urls                     Print tile URL templates
```

**NWS Zone IDs for major Arizona areas:**

| Zone | Area |
|---|---|
| AZZ006 | Coconino County (Flagstaff) |
| AZZ008 | Yavapai County (Prescott) |
| AZZ023 | Maricopa County (Phoenix) |
| AZZ028 | Pima County (Tucson) |
| AZZ032 | Cochise County (Sierra Vista) |
| AZZ018 | Navajo County (Holbrook) |

---

## Data Models

### `Camera`

```python
@dataclass
class Camera:
    id: int
    source_id: str          # Internal UUID
    source: str             # "AZDOT", "TRAVELIQ"
    type: str               # "DMS"
    roadway: str            # "I-17", "SR-89A", "US-60"
    location: str           # Human-readable location
    direction: int          # 0=unknown, cardinal directions
    lat: float
    lng: float
    images: List[CameraImage]
    created: Optional[str]
    last_updated: Optional[str]
    area_id: Optional[str]

    @property
    def primary_image_url(self) -> Optional[str]: ...
```

### `CameraImage`

```python
@dataclass
class CameraImage:
    id: int                          # CCTV image ID — use with /map/Cctv/{id}
    camera_site_id: int              # Parent camera site ID
    sort_order: int
    description: str                 # e.g. "I-17 SB 334.70 @Flagstaff"
    image_url: str                   # Relative: "/map/Cctv/693"
    image_type: int                  # 0 = JPEG still
    is_video_auth_required: bool
    video_disabled: bool
    disabled: bool
    blocked: bool

    @property
    def full_image_url(self) -> str: ...   # Absolute URL
```

### `TrafficEvent`

Used for incidents, construction, closures, special events, truck restrictions.

```python
@dataclass
class TrafficEvent:
    id: int
    source: str             # "ERS", "TRAVELIQ", "ADOT"
    source_id: str
    description: str
    event_type: str         # "accidentsAndIncidents", "roadwork", "closures"
    event_sub_type: str     # "Potholes", "exitclosed", "Road widening", ...
    atis_type: str
    roadway: str
    direction: str          # "East", "West", "Both", "Unknown"
    severity: str           # "Minor", "Moderate", "Major", "None"
    is_full_closure: bool
    lat: float
    lng: float
    start_date: Optional[str]
    end_date: Optional[str]
    last_updated: Optional[str]
    location_description: Optional[str]
    lane_description: Optional[str]
    polyline: Optional[str]    # Google Maps encoded polyline
    camera_ids: Optional[str]
```

### `MessageSign`

```python
@dataclass
class MessageSign:
    id: int
    source: str
    source_id: str          # UUID
    name: str               # "I-10 EB @ 35th Ave"
    description: str
    status: str             # "OK", "Error"
    roadway_name: str       # "I-10"
    direction: str          # "EB", "WB", "NB", "SB"
    messages: str           # Multi-line current sign text (CRLF-separated)
    lat: float
    lng: float
    last_comm: Optional[str]
    last_update: Optional[str]
```

### `WeatherForecastZone`

```python
@dataclass
class WeatherForecastZone:
    zone_id: str            # "AZZ006"
    location_name: str      # "Coconino County"
    lat: float
    lng: float
    grid_id: str            # NWS grid identifier
    grid_x: int
    grid_y: int
    periods: List[WeatherForecastPeriod]
    last_updated: Optional[str]

@dataclass
class WeatherForecastPeriod:
    number: str
    name: str               # "Today", "Tonight", "Saturday", ...
    start_time: str
    end_time: str
    is_day_time: bool
    temperature: int        # Fahrenheit
    wind_speed: str         # "13 mph", "6 to 22 mph"
    wind_direction: str     # "E", "SW", "NW"
    icon: str               # NWS icon URL
    short_forecast: str     # "Sunny", "Mostly Cloudy"
    detailed_forecast: str  # Full paragraph
```

### `BorderCrossing`

```python
@dataclass
class BorderCrossing:
    id: int
    source: str             # "CPB" (US Customs and Border Protection)
    name: str               # "Douglas (Raul Hector Castro)"
    hours: str              # "24 hrs/day"
    commercial_delay: str   # "no delay", "delay", "Lanes Closed"
    passenger_delay: str
    pedestrian_delay: str
    lat: float
    lng: float
    last_updated: Optional[str]
```

---

## CDN & Tile Patterns

### Camera Image CDN

Camera images are proxied through an **AWS Lambda@Edge** function behind
**Amazon CloudFront**:

```
https://www.az511.gov/map/Cctv/{cctv_image_id}
  → CloudFront → Lambda@Edge → ADOT camera backend
```

Key response headers:
- `x-amzn-requestid`: Lambda request ID
- `x-amz-cf-id`: CloudFront request ID
- `Cache-Control: max-age=30` — 30-second TTL
- `Access-Control-Allow-Origin: *` — open CORS
- `Content-Type: image/jpeg`

### Traffic Speed Tiles

```
https://tiles.ibi511.com/Geoservice/GetTrafficTile?x={x}&y={y}&z={z}
```

- Served by **IBI511** (owned by **TravelIQ** / Conduent)
- Behind CloudFront CDN
- `Cache-Control: public, max-age=60`
- **CORS enforcement**: requires `Referer: https://www.az511.gov/`
- Also requires `Origin: https://www.az511.gov` for cross-origin requests
- Returns transparent PNG

**Google/OSM tile coordinate examples at zoom 12:**
- Phoenix area: x=801-810, y=1648-1658
- Tucson area: x=805-808, y=1668-1672
- Flagstaff area: x=800-803, y=1638-1642

### Weather Radar Tiles

```
https://www.az511.gov/map/weatherRadar/{z}/{x}/{y}?frame={n}
```

- Returns transparent PNG (or 204 No Content if no data)
- Custom `Imagedate` header: UTC timestamp of radar scan (e.g. `2026-03-27T17:54:00Z`)
- Data credited to Environment Canada (NWS/NOAA for US coverage)
- `Cache-Control: public, max-age=300`
- Animated: increment `frame` parameter for older scans

### MapLibre Tiles

The site also references:
```
https://stg.map-tiles.traveliq.co/world.json
```
This is a MapLibre GL style document for the base map.

---

## Reverse-Engineering Notes

### Technology Stack

The AZ511 website is an **ASP.NET MVC** application (`X-Powered-By: ASP.NET`):
- **Frontend**: jQuery, Bootstrap, Google Maps API v3, MapLibre GL
- **Backend**: C# / ASP.NET Core with Entity Framework
- **CDN**: CloudFront for camera images and traffic tiles
- **Map tiles**: IBI511/TravelIQ for traffic; GeoServer for milepost WMS
- **Weather data**: NWS/NOAA API (`api.weather.gov`)
- **Incident data**: ADOT ERS (Emergency Response System) + SPILLMANCAD CAD
- **Construction data**: TravelIQ source (`TRAVELIQ`)
- **Border crossings**: US Customs and Border Protection (`CPB`)

### Key JS Files Analyzed

| File | Purpose |
|---|---|
| `/Scripts/map/LayerSpecific/loadEventPolyline.min.js` | `$.ajax('/map/data/{layer}/{id}')` calls for polylines |
| `/Scripts/map/LayerSpecific/loadEventPolygon.min.js` | WKT polygon extraction for weather events |
| `/Scripts/map/LayerSpecific/WeatherRadarAnimateHandler.min.js` | `/map/weatherRadar/{x}/{y}/{z}?frame={n}` calls |
| `/Scripts/map/LayerSpecific/myCameraTooltip.min.js` | `/Camera/AddMyCameraList`, `/Camera/SaveMyCameras` auth endpoints |
| `/scripts/jsresources/map/map?lang=en` | Config/resource strings including layer IDs, tile URLs, CDN paths |

### Embedded Google Maps API Key

The site uses a Google Maps API key visible in the HTML source:

```
AIzaSyDnJ06hvlt5T38t1P4mir61a1wdYTZ3Wdw
```

This key is domain-restricted to `az511.gov` and `az511.com`. It is **not**
used by this client — all data is fetched directly from the AZ511 API.

### Data Sources

| Source Code | Origin |
|---|---|
| `AZDOT` | ADOT internal camera/device management |
| `ERS` | ADOT Emergency Response System |
| `SPILLMANCAD` | Spillman CAD (computer-aided dispatch) |
| `TRAVELIQ` | Conduent/IBI511 TravelIQ platform |
| `CPB` | US Customs and Border Protection |
| `AZ` | Generic Arizona state data |

### Coordinate System

All coordinates use **WGS 84** (EPSG:4326), serialized two ways:

1. Top-level `latitude` / `longitude` floats (on event objects)
2. `latLng.geography.wellKnownText` — WKT format: `POINT (-112.134 33.462)`
   (note: **longitude first**, then latitude — standard WKT order)

The `_parse_latlng()` helper in the client handles both formats.

---

## Rate Limiting & Etiquette

The AZ511 API has no documented public rate limits. The client applies conservative
delays between batch requests (`0.03–0.05 s`). For production use:

- **Cache the map icon lists** — they rarely change within a 30-second window
- **Camera images** have a 30-second server-side TTL; polling faster wastes bandwidth
- **Batch detail fetches** — the camera markers endpoint returns all 600+ cameras
  in one response; only fetch detail records you actually need
- Set a descriptive `User-Agent` identifying your application

---

## Known Limitations

1. **Weather events count may be 0** during calm weather — this is expected behaviour,
   not a bug.

2. **`TrafficSpeeds` layer** is listed in the HTML layer checkboxes but returns an
   empty `item2` array from the `mapIcons` endpoint.  Speed data is delivered via
   the IBI511 tile CDN overlay tiles instead.

3. **`RestAreaClosed`** returns an empty list when all rest areas are open.

4. **Video streams**: The `imageType` field in `CameraImage` could theoretically
   be non-zero for streaming video, but all 604 cameras observed return
   `imageType: 0` (JPEG still).  The `isVideoAuthRequired` and `videoDisabled`
   flags suggest streaming was planned but may require an authenticated session.

5. **MileMarkers WMS** (`/map/mapWMS/MileMarkers/{z}/{x}/{y}`) returns HTTP 400
   for some tile coordinates — the underlying GeoServer has strict coordinate
   validation that the MapLibre client handles but curl/urllib does not.

6. **Authentication-gated features** (`MyCameras` saved lists, route saving,
   alerts subscriptions) require a registered AZ511 account.

7. **ATIS phone integration** is referenced in resources config but not
   accessible via the public HTTP API.
