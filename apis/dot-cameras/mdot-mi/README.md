# MDOT MiDrive API Client

A production-quality Python client for the Michigan Department of Transportation
(MDOT) **MiDrive** real-time traffic information system.

- **No API key required** — all endpoints are public and unauthenticated
- **stdlib only** — uses `urllib`, `json`, and `dataclasses` (no pip dependencies)
- **Python 3.9+** compatible
- Covers cameras, incidents, construction, DMS signs, truck parking, toll bridges, snowplows, and geocoding

---

## Background: What is MiDrive?

MiDrive is MDOT's public web application for statewide traffic monitoring:
**https://mdotjboss.state.mi.us/MiDrive/map**

It aggregates:
- 785 live traffic cameras
- Real-time incidents and crashes
- ~400 road construction zones with polyline geometry
- 487 dynamic message signs (overhead highway signs)
- Truck parking availability
- Snowplow/maintenance vehicle positions (winter only)
- Toll bridge and border crossing information
- Bing Maps-powered geocoding for Michigan cities and zip codes

The backend is a Java EE application running on JBoss/WildFly. All data APIs
return JSON and require no authentication tokens or session state.

---

## Reverse Engineering Notes

### Source Discovery Method

1. Fetched `https://mdotjboss.state.mi.us/MiDrive/map` HTML source
2. Identified JavaScript bundles in `<script>` tags
3. Analyzed `/MiDrive/js/map/mapdatabase.js` — contains all endpoint URL variables
4. Analyzed `/MiDrive/js/incidents.js` — confirmed incidents endpoint paths
5. Tested all discovered endpoints with `curl` to validate responses
6. Sampled camera detail records to document CDN image URL patterns

### Authentication Analysis

| Mechanism | Present | Notes |
|---|---|---|
| API Key (header) | No | No `X-API-Key` or similar headers required |
| API Key (query param) | No | No `api_key` parameters found |
| Session token / JWT | No | `JSESSIONID` cookie set but not validated |
| OAuth | No | Not used |
| IP rate limiting | Unknown | Not encountered during testing |
| CORS restriction | No | `Access-Control-Allow-Origin: *` |

All read endpoints are fully open and unauthenticated.

### JavaScript Sources Analyzed

| File | Purpose |
|---|---|
| `/MiDrive/js/map/mapdatabase.js?version=1` | **Primary** — all endpoint URL variables, AJAX call logic |
| `/MiDrive/js/incidents.js` | Incident list rendering, refresh timer |
| `/MiDrive/js/map/mapvars.js` | Layer variable declarations |
| `/MiDrive/js/map/mapsetup.js` | ESRI ArcGIS map initialization |
| `/MiDrive/js/map/mapextras.js` | Geocoding helper functions |
| `/MiDrive/js/map/page.js?version=83` | UI event handlers, city autocomplete |
| `/MiDrive/js/common.js?version=83` | Shared AJAX utility, layer toggle logic |

---

## Complete API Reference

### Base URL

```
https://mdotjboss.state.mi.us/MiDrive
```

All endpoints accept HTTP GET unless otherwise noted. All responses are JSON.
No authentication headers are required.

---

### Cameras

#### List All Cameras
```
GET /camera/AllForMap/
```

Returns all traffic camera map pins for Michigan.

**Note:** The `link` field is always `null` in this response. You must call
`getCameraInformation/{id}` to retrieve the live image URL.

**Response:** `Array<CameraMarker>`

```json
[
  {
    "latitude": 42.491304,
    "longitude": -83.04479,
    "id": 1129,
    "title": "11 Mile @ Mound NB",
    "icon": "https://www.michigan.gov/mdot/.../MapLayerPoint-Cameras.png",
    "link": null,
    "weatherText": null,
    "weatherId": 0,
    "orientation": null
  }
]
```

**Live stats:** ~785 cameras as of March 2026

---

#### Get Camera Detail
```
GET /camera/getCameraInformation/{id}
```

Returns full camera detail including the live image URL.

**Path parameters:**
- `id` (integer): Camera ID from the listing endpoint

**Response:** `CameraDetail`

```json
{
  "latitude": 42.491304,
  "longitude": -83.04479,
  "id": 1129,
  "title": "11 Mile @ Mound NB",
  "icon": "https://mdotnetpublic.state.mi.us/drive/mobile/images/camera_gray.png",
  "link": "https://micamerasimages.net/thumbs/semtoc_cam_253.flv.jpg?item=1",
  "weatherText": "",
  "weatherId": 0,
  "orientation": "Traffic closest to camera is traveling north."
}
```

The `icon` value `camera_gray.png` indicates the camera may be offline or showing a grey placeholder. When a camera has an active feed, `link` points to a JPEG image URL.

---

#### Get Cameras by Route
```
GET /camera/getCameraInformationByRoute/{route}---{type}
```

Returns cameras along a specific freeway or route. Uses `---` (three dashes) as a separator.

**Path parameter examples:**
- `I-75---I` — Interstate 75
- `US-23---US` — US Highway 23
- `M-59---M` — Michigan State Highway 59

**Response:** `Array<CameraDetail>` (empty array if no matches)

---

#### Get Favorite Cameras
```
POST /camera/favoriteCameras/
Content-Type: application/x-www-form-urlencoded

cameraIds=1129,1128,756
```

Returns details for a specific list of camera IDs.

**Response:** `Array<CameraDetail>`

---

### Camera Image CDN Patterns

Camera `link` URLs fall into two CDN patterns:

| CDN | Pattern | Example |
|---|---|---|
| MDOT RWIS | `https://mdotjboss.state.mi.us/docs/drive/camfiles/rwis/{id}.jpg?random={ms_timestamp}` | Road Weather Info System cameras in rural areas |
| SEM TOC | `https://micamerasimages.net/thumbs/semtoc_cam_{NNN}.flv.jpg?item=1` | Detroit metro freeway cameras |
| Grand Rapids TOC | `https://micamerasimages.net/thumbs/grand_cam_{NNN}.flv.jpg?item=1` | Grand Rapids area cameras |

The `?random=` parameter on RWIS cameras is a Unix timestamp in milliseconds used for cache-busting. Replace it with the current timestamp to force a fresh image fetch.

---

### Incidents

#### List Incidents (Map)
```
GET /incidents/AllForMap/
```

Minimal map pin data. Refreshes every 90 seconds on the live site.

**Response:** `Array<IncidentMarker>`

```json
[
  {
    "latitude": 42.228386,
    "longitude": -83.21197,
    "id": 1072124,
    "title": "Crash on SB I-75",
    "icon": "https://mdotnetpublic.state.mi.us/drive/images/inc_red_18px.png",
    "message": "<div class='stripeLight'><strong>Location: </strong>SB I-75 after Dix Hwy</div>..."
  }
]
```

---

#### List Incidents (Page / Full Detail)
```
GET /incidents/AllForPage
```

Richer incident data with full sidebar panel HTML. Refreshes every 60 seconds.

**Response:** `Array<IncidentPage>`

```json
[
  {
    "iconURL": "https://mdotnetpublic.state.mi.us/drive/images/inc_red_18px.png",
    "incidentTitle": "Crash on NB I-75",
    "incidentText": "<div class='stripeLight'><strong>Location: </strong>NB I-75 West...</div>",
    "gotoLink": "<a href='http://mdotnetpublic.state.mi.us/drive/default.aspx?...'>Go To</a>",
    "longitude": -83.24166,
    "latitude": 42.143635,
    "incidentId": 1072056
  }
]
```

---

### Construction

#### List Construction Zones
```
GET /construction/AllForMap/
```

Returns all road construction zones and closures with polyline geometry.

**Response:** `Array<ConstructionZone>`

```json
[
  {
    "latitude": 42.478044,
    "longitude": -83.111001,
    "id": "ETX-3268",
    "title": "WB I-696/NB I-75 Ramp: Total Closure",
    "icon": "1",
    "coordinatePoints": [
      [-83.109073, 42.477394],
      [-83.109572, 42.477457],
      ...
    ],
    "active": true
  }
]
```

**Icon codes:**
| Value | Color | Type |
|---|---|---|
| `1` | Red | Total Closure |
| `2` | Orange | Lane Closure |
| `3` | Blue | Special Event |
| `4` | Green | Future Closure |
| `null` | Gray | Disabled / Holiday Open |

**Live stats:** ~394 zones, ~359 active as of March 2026

---

#### Get Construction Zone Detail
```
GET /construction/getConstructionInformation/{id}
```

Returns start/end dates, detour info, and full description.

**Response:** `[html_detail, title]`

```json
[
  "<div class='stripeLight'>WB I-696/NB I-75 ramp ... Total closure<br/>Detour: NB M-53...</div><div class='stripeDark'><b>Starts On: </b>02/28/2026, 7:00 AM</div><div class='stripeDark'><b>Ends On: </b>05/30/2026, 5:00 PM</div>",
  "WB I-696/NB I-75 Ramp: Total Closure"
]
```

---

### Truck Parking

#### List Parking Locations
```
GET /parking/getMapParking/
```

Returns all truck parking locations with current availability in the title.

**Response:** `Array<ParkingMarker>`

```json
[
  {
    "latitude": 42.26407,
    "longitude": -85.21991,
    "id": 17216,
    "title": "I-94 @ Minges Road - Available",
    "icon": "https://mdotnetpublic.state.mi.us/drive/images/prk.png"
  }
]
```

---

#### Get Parking Detail
```
GET /parking/getParkingInfoMap/{id}
```

**Response:** `[html_detail, title]`

```json
[
  "<div class='stripeLight'><b>Status: </b>Available</div><div class='stripeLight'><b>Name: </b>Battle Creek Rest Area 703</div><div class='stripeDark'><b>Route: </b>I-94</div><div class='stripeDark'><b>Location: </b>Minges Road</div><div class='stripeLight'><b>Open Spaces: </b>24</div><div class='stripeLight'><b>Total Spaces: </b>24</div><div class='stripeDark'><b>Updated: </b>01/02/2025, 3:34 PM</div>",
  "I-94 @ Minges Road"
]
```

---

#### Get All Parking Details
```
GET /parking/getParkingInfoMap/showAllParkings
```

Returns all parking locations in a single call as a dict.

**Response:** `Object` — keys are `"{lat} - {lon} - {title}"`, values are HTML detail strings

---

### Dynamic Message Signs (DMS)

#### List DMS Signs
```
GET /dms/AllForMap
```

Returns all overhead highway sign locations.

**Response:** `Array<DMSMarker>`

```json
[
  {
    "latitude": 42.1384,
    "longitude": -83.2411,
    "id": 2143,
    "title": "NB I-75 @ West",
    "icon": "https://www.michigan.gov/mdot/.../MapLayerPointDMS.png"
  }
]
```

**Live stats:** 487 signs as of March 2026

---

#### Get DMS Message
```
GET /dms/getDMSInfo/{id}
```

Returns the current message on a specific DMS sign.

**Response:** `[html_message, title]`

```json
[
  "<div class='dmsMessage'>   LEFT LANE CLOSED<br> RAMP TO US-24 NORTH<br><br> TRAVEL TIME TO<br> M-39     9 MI 8 MIN<br> I-96    16 MI 14 MIN</div><div class='dmstimeStamp'>Mar 27 2026, 4:01 PM</div>",
  "NB I-75 @ West"
]
```

---

### Toll Bridges / Border Crossings

#### List Toll Bridges
```
GET /tollBridges/allForMap/
```

**Response:** `Array<TollBridgeMarker>`

Known bridges (as of March 2026):
- Blue Water Bridge (Port Huron / Sarnia, ON)
- Ambassador Bridge (Detroit / Windsor, ON)
- Detroit/Windsor Tunnel
- Mackinac Bridge (state toll)
- International Bridge (Sault Ste. Marie / Sault Ste. Marie, ON)

---

#### Get Toll Bridge Message
```
GET /tollBridges/tollBridgeMessage/{id}
```

**Response:** `[html_detail]`

---

### Snowplows / Maintenance Vehicles

```
GET /plows/AllForMap/
```

Returns current snowplow positions. Returns an empty array outside winter season.

**Response:** `Array<PlowMarker>` (same shape as other map markers)

---

### Geocoding

#### Geocode City or Zip Code
```
GET /map/getGeocodeLatLon/{query}
```

Geocodes a Michigan city name or zip code. Powered by Bing Maps.

**Response:** `GeocodeResult`

```json
{
  "state": "MI",
  "address": null,
  "latitude": 42.33293915,
  "longitude": -83.0478363,
  "matchInfo": null,
  "matchMethod": "Rooftop",
  "matchNote": "Match Confidence: High | EntityType: PopulatedPlace",
  "matchQuality": "Good",
  "matchSource": "Bing",
  "mgrX": 743067.538943084,
  "mgrY": 202376.06487793778,
  "zipCode": null,
  "city": "Detroit"
}
```

---

#### List Michigan Cities
```
GET /cities/
```

Returns all Michigan city names used for the MiDrive autocomplete search.

**Response:** `Array<City>`

```json
[
  { "pk": { "cityCd": 26, "cityName": "Addison" } }
]
```

**Live stats:** 533 Michigan cities

---

## Python Client Usage

### Installation

No installation required. Copy `mdot_mi_client.py` to your project directory.

**Requirements:** Python 3.9+ (standard library only)

---

### Basic Usage

```python
from mdot_mi_client import MiDriveClient

client = MiDriveClient()

# List all cameras
cameras = client.list_cameras()
print(f"{len(cameras)} cameras found")

# Get live image URL for a specific camera
detail = client.get_camera(cameras[0].id)
print(f"Camera: {detail.title}")
print(f"Image: {detail.image_url()}")

# List active incidents
incidents = client.list_incidents()
for inc in incidents:
    print(f"{inc.incident_title} at ({inc.latitude:.4f}, {inc.longitude:.4f})")

# List construction zones
zones = client.list_construction()
total_closures = [z for z in zones if z.icon == 1 and z.active]
print(f"{len(total_closures)} total road closures active")

# Get current DMS message
signs = client.list_dms()
info = client.get_dms_info(signs[0].id)
print(f"{info.title}:")
print(info.message_text())
```

---

### Finding Cameras Near a Location

```python
from mdot_mi_client import MiDriveClient, find_nearest_cameras

client = MiDriveClient()
cameras = client.list_cameras()

# Geocode a location
geo = client.geocode("Ann Arbor")

# Find 10 nearest cameras within 25 km
nearest = find_nearest_cameras(
    cameras,
    lat=geo.latitude,
    lon=geo.longitude,
    max_results=10,
    max_km=25.0,
)

for dist_km, cam in nearest:
    detail = client.get_camera(cam.id)
    print(f"{cam.title:40s}  {dist_km:.1f} km  {detail.image_url() or '(offline)'}")
```

---

### Downloading a Camera Image

```python
import urllib.request
from mdot_mi_client import MiDriveClient

client = MiDriveClient()
camera = client.get_camera(1129)

if camera.link:
    url = camera.image_url(bust_cache=True)
    urllib.request.urlretrieve(url, f"camera_{camera.id}.jpg")
    print(f"Saved: camera_{camera.id}.jpg")
```

---

### Monitoring Incidents

```python
import time
from mdot_mi_client import MiDriveClient, strip_html

client = MiDriveClient()

while True:
    incidents = client.list_incidents()
    print(f"\n--- {time.strftime('%H:%M:%S')} — {len(incidents)} active incidents ---")
    for inc in incidents:
        text = strip_html(inc.incident_text)
        print(f"  {inc.incident_title}: {text[:120]}")
    time.sleep(60)  # API refreshes every 60 seconds
```

---

### Filtering Construction by Type

```python
from mdot_mi_client import MiDriveClient, CONSTRUCTION_ICON_LABELS

client = MiDriveClient()
zones = client.list_construction()

# Group by closure type
from collections import defaultdict
by_type = defaultdict(list)
for z in zones:
    if z.active:
        by_type[z.closure_type].append(z)

for ctype, items in sorted(by_type.items()):
    print(f"{ctype}: {len(items)} zones")
    for z in items[:3]:
        print(f"  {z.id}: {z.title}")
```

---

### Checking DMS Signs Along a Corridor

```python
from mdot_mi_client import MiDriveClient

client = MiDriveClient()
signs = client.list_dms()

# Filter signs in the Detroit metro area (rough bounding box)
metro_signs = [
    s for s in signs
    if 42.0 <= s.latitude <= 42.7 and -84.0 <= s.longitude <= -82.8
]

print(f"{len(metro_signs)} DMS signs in Detroit metro area")
for sign in metro_signs[:5]:
    info = client.get_dms_info(sign.id)
    if info.message_text().strip():
        print(f"\n{info.title}:")
        print(info.message_text())
```

---

## CLI Reference

```bash
# Full live system summary
python3 mdot_mi_client.py summary

# List cameras (first 20)
python3 mdot_mi_client.py cameras

# Find cameras near a city
python3 mdot_mi_client.py cameras --near "Grand Rapids"
python3 mdot_mi_client.py cameras --near "Kalamazoo"

# Get full detail for a specific camera (by ID)
python3 mdot_mi_client.py camera 1129
python3 mdot_mi_client.py camera 756

# List active traffic incidents
python3 mdot_mi_client.py incidents

# List active construction zones
python3 mdot_mi_client.py construction

# Show DMS sign messages (first 5)
python3 mdot_mi_client.py dms

# Show all DMS signs
python3 mdot_mi_client.py dms --all

# List truck parking locations
python3 mdot_mi_client.py parking

# List toll bridges / border crossings
python3 mdot_mi_client.py bridges

# List Michigan cities
python3 mdot_mi_client.py cities

# Geocode a city or zip code
python3 mdot_mi_client.py geocode Detroit
python3 mdot_mi_client.py geocode 48226
python3 mdot_mi_client.py geocode "Grand Rapids"
```

---

## Data Classes Reference

### `CameraMarker`
Lightweight camera record from `/camera/AllForMap/`.

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Camera ID |
| `title` | `str` | Location description |
| `latitude` | `float` | WGS84 latitude |
| `longitude` | `float` | WGS84 longitude |
| `icon` | `str` | Icon image URL |
| `link` | `str \| None` | Always `None` in list response |
| `weather_text` | `str \| None` | Weather description |
| `weather_id` | `int` | Weather condition code |
| `orientation` | `str \| None` | Traffic direction note |

### `CameraDetail`
Full camera record from `/camera/getCameraInformation/{id}`.

Same fields as `CameraMarker`, but `link` is populated with the live image URL.

**Methods:**
- `image_url(bust_cache=True) -> str | None` — Returns image URL, replacing cache-busting param for RWIS cameras.

### `IncidentMarker`
From `/incidents/AllForMap/`. Fields: `id`, `title`, `latitude`, `longitude`, `icon`, `message` (HTML).

### `IncidentPage`
From `/incidents/AllForPage`. Fields: `incident_id`, `incident_title`, `latitude`, `longitude`, `icon_url`, `incident_text` (HTML), `goto_link`.

### `ConstructionZone`
From `/construction/AllForMap/`. Fields: `id` (str), `title`, `latitude`, `longitude`, `icon` (int), `active` (bool), `coordinate_points` (list of [lon,lat] pairs).

**Properties:**
- `closure_type -> str` — Human-readable type ("Total Closure", "Lane Closure", etc.)

### `ParkingMarker`
From `/parking/getMapParking/`. Fields: `id`, `title`, `latitude`, `longitude`, `icon`.

### `DMSMarker`
From `/dms/AllForMap`. Fields: `id`, `title`, `latitude`, `longitude`, `icon`.

### `DMSInfo`
From `/dms/getDMSInfo/{id}`. Fields: `id`, `title`, `message_html`, `timestamp`.

**Methods:**
- `message_text() -> str` — Strips HTML tags, returns plain text sign message.

### `TollBridgeMarker`
From `/tollBridges/allForMap/`. Fields: `id`, `title`, `latitude`, `longitude`, `icon`.

### `PlowMarker`
From `/plows/AllForMap/`. Fields: `id`, `title`, `latitude`, `longitude`, `icon`.

### `GeocodeResult`
From `/map/getGeocodeLatLon/{query}`. Fields: `latitude`, `longitude`, `city`, `state`, `zip_code`, `match_quality`, `match_method`, `match_note`, `match_source`, `address`.

### `City`
From `/cities/`. Fields: `city_cd` (int), `city_name` (str).

---

## Utility Functions

### `haversine_distance(lat1, lon1, lat2, lon2) -> float`
Calculate great-circle distance in kilometres between two WGS84 coordinates.

### `find_nearest_cameras(cameras, lat, lon, max_results=5, max_km=50.0) -> list[tuple[float, CameraMarker]]`
Find the nearest cameras to a target location. Returns `(distance_km, camera)` tuples sorted by distance.

### `strip_html(html) -> str`
Remove HTML tags and collapse whitespace from HTML strings (useful for processing `incidentText`, `message`, etc.).

---

## Error Handling

```python
from mdot_mi_client import MiDriveClient, MiDriveHTTPError, MiDriveConnectionError, MiDriveError

client = MiDriveClient(timeout=15.0)

try:
    cameras = client.list_cameras()
except MiDriveHTTPError as e:
    print(f"HTTP {e.code}: {e.reason} for {e.url}")
except MiDriveConnectionError as e:
    print(f"Network error: {e}")
except MiDriveError as e:
    print(f"API error: {e}")
```

| Exception | Raised when |
|---|---|
| `MiDriveHTTPError` | Server returns non-2xx HTTP status |
| `MiDriveConnectionError` | Network unreachable, DNS failure, timeout |
| `MiDriveError` | Base class; also raised on JSON decode failure |

---

## Notes and Caveats

### Data Freshness
| Data type | Live map refresh interval | Notes |
|---|---|---|
| Incidents | 60 seconds | `AllForPage` |
| Incidents (map) | 90 seconds | `AllForMap` |
| Cameras | Real-time | Image URL changes; RWIS `?random=` param |
| Snowplows | 90 seconds | Empty array off-season |
| Construction | Static | Updated by MDOT project managers |
| DMS Signs | Static listing | Message content changes in real time |
| Parking | Minutes | Space count updates from sensor data |

### Camera Image Notes
- A grey camera icon (`camera_gray.png`) in the `icon` field indicates the camera feed may be temporarily unavailable
- RWIS camera images are hosted directly on `mdotjboss.state.mi.us` and can be fetched without authentication
- `micamerasimages.net` camera images (SEM TOC / Grand Rapids TOC) are served from a third-party CDN operated by the regional traffic management centres

### Traffic Speed Layer
The live traffic speed layer is powered by ESRI ArcGIS:
```
https://utility.arcgis.com/usrsvcs/appservices/2y1TxWC4UaePZylO/rest/services/World/Traffic/MapServer
```
This service requires an ArcGIS API token (embedded in the ESRI JS SDK call) and is **not** included in this client.

### ESRI ArcGIS Integration
The MiDrive map uses ESRI ArcGIS JavaScript API 4.7 for map rendering. The
underlying data APIs are all standard REST/JSON and do not require ESRI licenses.

### Terms of Use
This client accesses public government data from a Michigan state agency website.
The data is intended for public use. Be considerate with request volume:
- Avoid polling more frequently than the native map refresh intervals
- Do not bulk-download all 785 camera images in tight loops
- Consider caching responses locally for non-real-time use cases

---

## Live Data Sample (March 27, 2026)

```
785  traffic cameras state-wide
8    active incidents (5 crashes, 3 cleared)
394  construction zones (359 active)
       111 total closures
       137 lane closures
       35  special events
       144 future closures
487  dynamic message signs
5    truck parking locations with real-time availability
5    toll bridges / border crossings
0    snowplows (off season)
533  Michigan cities in geocoding database
```

---

## File Layout

```
mdot_mi_client.py   — Python client (stdlib only, self-contained)
mdot_mi_README.md   — This documentation
```
