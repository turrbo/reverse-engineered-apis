# Idaho ITD / 511 Traffic Camera System – Reverse-Engineered Client

A pure Python (stdlib-only) client for the Idaho Transportation Department's
real-time traffic data at **https://511.idaho.gov**.

---

## Quick Start

```bash
# List all cameras
python3 itd_client.py cameras

# Show active incidents
python3 itd_client.py incidents

# Show current weather station readings
python3 itd_client.py weather

# Download a camera image (image_id from camera listing)
python3 itd_client.py image 1238
```

---

## System Architecture

The site is an ASP.NET MVC application behind AWS CloudFront.  Three separate
API surfaces are exposed:

| Surface | Auth | Base URL |
|---------|------|----------|
| **Session List API** | Session cookie + CSRF token (no account) | `/List/GetData/{typeId}` |
| **Developer REST API** | Registered API key | `/api/v2/get/{resource}` |
| **WZDx Feed** | None (fully public) | `/api/wzdx` |
| **Camera Images** | None (fully public) | `/map/Cctv/{imageId}` |

---

## Authentication Deep-Dive

### Session API (no account needed)

Most data endpoints use server-side DataTables rendering.  The site requires:

1. A `session-id` cookie – set by any HTTP response from the server.
2. A `__RequestVerificationToken` cookie – ASP.NET anti-CSRF token, also set automatically.
3. The *same* CSRF token value sent as a request header: `RequestVerificationToken: <value>`.

The client bootstraps by loading `/cctv`, which triggers cookie issuance and
also embeds a form-field copy of the token in the HTML for extraction.

```
GET /cctv
→ Set-Cookie: session-id=<hex>
→ Set-Cookie: __RequestVerificationToken=<base64url>
→ <input name="__RequestVerificationToken" value="<base64url>" ... />
```

Subsequent data requests send both cookies and the header:

```
GET /List/GetData/Cameras?query={...}&lang=en
Cookie: session-id=<hex>; __RequestVerificationToken=<tok>
RequestVerificationToken: <tok>
X-Requested-With: XMLHttpRequest
```

### Developer API (requires free registration)

The `/api/v2/get/*` endpoints require a `key` query parameter obtained by:

1. Creating an account at https://511.idaho.gov/my511/register
2. Visiting https://511.idaho.gov/developers/doc and requesting a key

**Rate limit:** 10 requests per 60 seconds.

```
GET /api/v2/get/cameras?key=YOUR_KEY
GET /api/v2/get/cameras?key=YOUR_KEY&format=xml
```

### Camera Images (fully public)

Static PNG images served directly – no session or key required:

```
GET https://511.idaho.gov/map/Cctv/<imageId>
→ Content-Type: image/png
→ 200–800 KB JPEG-in-PNG
```

Images are cached by CloudFront (`Cache-Control: public, max-age=86400`) but
the cache key varies by query, so appending a timestamp fragment bust the cache:

```
https://511.idaho.gov/map/Cctv/1238#1711572000
```

This matches the site's JS behaviour (`URI(url).hash(new Date().getTime())`).

---

## Discovered Endpoints

### Session List API – `/List/GetData/{typeId}`

**Method:** `GET`
**Parameters:**
- `query` – URL-encoded JSON (DataTables server-side format, modified – see below)
- `lang` – Language code, e.g. `en`

**Response format:**
```json
{
  "draw": 0,
  "recordsTotal": 450,
  "recordsFiltered": 450,
  "data": [ { ... }, ... ]
}
```

**Supported `typeId` values:**

| typeId | Records | Description |
|--------|---------|-------------|
| `Cameras` | ~450 | Traffic camera sites with image URLs |
| `traffic` | ~173 | All traffic events combined |
| `Incidents` | ~3 | Active incidents (crashes, disabled vehicles) |
| `Closures` | ~44 | Road closures |
| `Construction` | ~97 | Active construction / work zones |
| `WeatherStations` | ~128 | RWIS weather measurement stations |
| `MessageSigns` | ~57 | Variable message signs (DMS) with current text |
| `MountainPasses` | ~32 | Mountain pass conditions |
| `Advisories` | varies | Travel advisories |

**Query JSON format** (DataTables server-side, with site-specific modifications):

The site's JS strips `draw`, `search.regex`, `column.title`, `column.orderable`,
and renames `searchable` to `s` before sending.  The client reproduces this:

```json
{
  "columns": [
    {"name": "roadway", "data": "roadway", "s": true},
    {"name": "direction"}
  ],
  "order": [{"column": 0, "dir": "asc"}],
  "start": 0,
  "length": 100,
  "search": {"value": ""}
}
```

### Camera Image

```
GET /map/Cctv/{imageId}
```
Returns raw PNG bytes.  `imageId` values come from the `images[].id` field
in the Cameras list response.

### Camera Tooltip (HTML)

```
GET /tooltip/Cameras/{cameraId}?lang=en&noCss=true
```
Returns HTML snippet with the camera carousel, image data attributes
(`data-lazy`, `data-refresh-rate`), and location text.

### Other discovered internal endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /Camera/GetVideoUrl?imageId={id}` | Returns a video stream URL for video-capable cameras |
| `GET /Camera/GetLatLng?id={id}` | Returns `{latitude, longitude}` for map zoom |
| `GET /Camera/GetUserCameras` | Returns authenticated user's saved camera lists |
| `POST /Camera/SaveMyCameras` | Add/remove camera from user's saved list |
| `GET /List/UniqueColumnValuesForCctv/{columnName}` | Returns unique filter values for a column |
| `GET /NoSession/GetCctvAgencyImage?agencyId={id}` | Returns agency logo PNG |
| `GET /NoSession/GetKml?name=Nearby511` | Returns KML of nearby 511 systems |
| `GET /map/data/{layerId}/{itemId}` | Returns shape/geometry for a map item |
| `GET /map/AudioPreview?Message={text}` | Text-to-speech preview for message signs |
| `POST /My511/Login` | Account login |
| `GET /Home/SetRegion` | Set current map region |
| `GET /cms/gethtmlcontent?divId={id}` | Fetch CMS HTML content block |
| `GET /wta/wtaoptions` | Citizen reporter options (WTA = What To Avoid) |
| `POST /wta/addCitizenReport` | Submit a citizen traffic report |
| `GET /Api/Route/GetUserRouteStatistics?segmentId={id}` | Route statistics |
| `GET /api/route/getlocations?latitude={lat}` | Route location search |

### Developer REST API – `/api/v2/get/{resource}`

**Parameters:** `key=<api_key>` (required), `format=json|xml` (optional, default json)

| Resource | Description |
|----------|-------------|
| `cameras` | Camera sites (no image URLs) |
| `roadconditions` | Current road conditions |
| `restrictions` | Weight/height restrictions |
| `weatherstations` | RWIS stations |
| `messagesigns` | VMS/DMS signs |
| `mountainpasses` | Mountain pass details |
| `events` | Traffic events |
| `advisories` | Travel advisories |
| `weighstations` | Weigh stations |
| `runawaytruck` | Runaway truck ramps |
| `restareas` | Rest areas |

### WZDx Feed

```
GET https://511.idaho.gov/api/wzdx
```
Fully public GeoJSON FeatureCollection conforming to WZDx v4.1 spec.
Contains ~500 work-zone features with lane impact data.

---

## Camera Data Model

```json
{
  "id": 231,
  "sourceId": "1279",
  "source": "ITDNET",
  "roadway": "I-15",
  "direction": "Southbound",
  "location": "I-15 Northgate New Day Walton",
  "latLng": {
    "geography": {
      "coordinateSystemId": 4326,
      "wellKnownText": "POINT (-112.436615 42.9477)"
    }
  },
  "sortOrder": 0,
  "images": [
    {
      "id": 1238,
      "cameraSiteId": 231,
      "sortOrder": 0,
      "description": "D5 I-15 74.4 Northgate NewDay5-2",
      "imageUrl": "/map/Cctv/1238",
      "imageType": 0,
      "refreshRateMs": 0,
      "isVideoAuthRequired": false,
      "videoDisabled": false,
      "disabled": false,
      "blocked": false,
      "language": "en"
    }
  ],
  "state": "Idaho",
  "county": "Bannock",
  "region": "Idaho Falls/Pocatello",
  "visible": true
}
```

**Sources found in production data:**

| Source | Description |
|--------|-------------|
| `ITDNET` | ITD managed cameras |
| `ACHD` | Ada County Highway District (Boise metro) |
| `Idaho511` | Cross-border/regional cameras |
| `INET` | Intelligent Networks |

---

## Python Client API

```python
from itd_client import ITDClient

client = ITDClient()                   # No key needed for session API
client_dev = ITDClient(api_key="KEY")  # Pass key for developer API
```

### Camera methods

```python
# List all cameras (450+)
cameras = client.get_cameras()
cameras = client.get_cameras(max_records=50)  # limit for testing

# Access camera data
for cam in cameras:
    print(cam.camera_id, cam.roadway, cam.direction, cam.location)
    print(f"  Lat: {cam.latitude}, Lng: {cam.longitude}")
    for img in cam.images:
        print(f"  Image {img.image_id}: {img.description}")
        print(f"  URL: https://511.idaho.gov{img.image_url}")
        print(f"  Refresh: {img.refresh_rate_ms}ms")

# Download a camera image (PNG bytes)
png_bytes = client.get_camera_image(1238)
with open("camera.png", "wb") as f:
    f.write(png_bytes)

# Save directly to file
client.download_camera_image(1238, "camera.png")

# Get cache-busted image URL
url = client.get_camera_image_url(1238, cache_bust=True)
# → "https://511.idaho.gov/map/Cctv/1238#1711572000"

# Find cameras near a point
nearby = client.get_cameras_near(lat=43.615, lng=-116.202, radius_km=5.0)

# Find cameras on a specific road
i84_cameras = client.get_cameras_on_road("I-84")
```

### Event methods

```python
# All traffic events
events = client.get_events()

# By type
incidents = client.get_incidents()
closures = client.get_closures()
construction = client.get_construction()

for event in incidents:
    print(event.event_id, event.roadway, event.direction)
    print(f"  {event.event_sub_type}: {event.lane_description}")
    print(f"  Since: {event.start_date}")
```

### Weather stations

```python
stations = client.get_weather_stations()
for ws in stations:
    print(f"{ws.name} ({ws.roadway})")
    print(f"  Air: {ws.air_temperature}°F  Surface: {ws.surface_temperature}°F")
    print(f"  Wind: {ws.wind_speed_average} mph {ws.wind_direction_average}")
    print(f"  Pavement: {ws.pavement_condition}")
```

### Message signs

```python
signs = client.get_message_signs()
for sign in signs:
    if sign.message and sign.message != "NO_MESSAGE":
        print(f"{sign.name} ({sign.roadway} {sign.direction}): {sign.message}")
```

### Mountain passes

```python
passes = client.get_mountain_passes()
for mp in passes:
    print(f"{mp.name}: {mp.roadway} at mile {mp.milepost}, elev {mp.elevation}ft")
```

### WZDx work zone data

```python
wzdx = client.get_wzdx()
features = wzdx["features"]
for feature in features:
    props = feature["properties"]
    core = props.get("core_details", {})
    print(f"Road: {core.get('road_names')} {core.get('direction')}")
    print(f"  Start: {props.get('start_date')}  End: {props.get('end_date')}")
    print(f"  Impact: {props.get('vehicle_impact')}")
    print(f"  Lanes: {props.get('lanes', [])}")
```

### Developer API (requires key)

```python
client = ITDClient(api_key="your_registered_key")

raw_cameras = client.api_get_cameras()
raw_events = client.api_get_events()
raw_conditions = client.api_get_road_conditions()
```

---

## CLI Reference

```
python3 itd_client.py <command> [options]

Commands:
  cameras         List all traffic cameras
  events          List all traffic events
  incidents       List active incidents only
  closures        List active road closures
  construction    List active construction zones
  weather         List all weather stations
  signs           List all message signs
  passes          List all mountain passes
  wzdx            Show WZDx work zone feed summary
  image <id>      Download camera image to cam_<id>.png

Options:
  -n, --limit N   Max records to show (default: 20)
  --key KEY       Developer API key
```

---

## Data Coverage

| Data type | Live records | Update frequency |
|-----------|-------------|-----------------|
| Cameras | ~450 sites | Images: 15–60 s per camera |
| Incidents | ~3–20 | Real-time (ERS system) |
| Closures | ~44 | As reported |
| Construction | ~97 | As reported |
| Weather stations | ~128 | ~5–15 minutes |
| Message signs | ~57 | Real-time (DMS polling) |
| Mountain passes | ~32 | Periodic |
| WZDx features | ~500 | ~30 minutes |

---

## Implementation Notes

### Session expiry
The session cookie has no explicit expiry (session-scoped).  The client
will automatically re-bootstrap if a request fails due to session expiry.
In practice, sessions persist for hours.

### Pagination
The `/List/GetData` endpoint is paginated (server-side DataTables).  The
client fetches pages of 100 records with a 0.3-second delay between pages
until `recordsFiltered` records are retrieved.

### Image refresh
Camera images are served as PNG with a 24-hour CloudFront TTL but are
effectively live because `Cache-Control` includes `no-cache="Set-Cookie"`.
To get the absolute latest frame, append a Unix-timestamp hash fragment.
The site's own JavaScript does `URI(src).hash(new Date().getTime())`.

### Geographic coordinate format
Coordinates are embedded in Well-Known Text (WKT) format:
`POINT (longitude latitude)` — note longitude first, contrary to GeoJSON.
The client parses these and stores them as `latitude`/`longitude` floats.

### API vs Session data differences
The developer API (`/api/v2/get/cameras`) returns a subset of camera
metadata without image URLs or refresh rates.  The Session List API
(`/List/GetData/Cameras`) returns richer data including per-image refresh
rates, video availability flags, and lat/lng.

---

## Legal / Usage Notes

- This client uses only publicly accessible endpoints that the site itself
  calls from every visitor's browser.
- The session-based endpoints require no account and work identically to
  what an anonymous browser visitor experiences.
- Respect the rate limits (10 req/60 s for the developer API).
- For production use of the structured developer API, register for a key
  at https://511.idaho.gov/developers/doc to comply with the site's terms.
- Camera images are subject to ITD copyright.

---

## Dependencies

**Zero external dependencies.**  Pure Python 3.7+ standard library:
`urllib`, `json`, `http.cookiejar`, `dataclasses`, `re`, `time`, `math`
