# NewEngland511 / NHDOT Traffic Camera API — Reverse Engineering Report

## Overview

The **New Hampshire Department of Transportation (NHDOT)** traffic camera system is
publicly accessible via **[newengland511.org](https://newengland511.org)**, a regional
511 portal covering New Hampshire, Vermont, and Maine. The site is built on a .NET
(ASP.NET / C#) backend served through AWS CloudFront.

This document describes every discovered API endpoint, the authentication model,
request/response schemas, and how to use the included Python client
(`nhdot_client.py`) to interact with the system programmatically.

---

## Target URLs

| Site | URL | Notes |
|------|-----|-------|
| New England 511 (primary) | https://newengland511.org | NH, VT, ME cameras |
| NHDOT TRIP511 link | https://www.nh.gov/dot/projects/trip511 | Redirects to NE511 |

---

## Reverse Engineering Methodology

1. **Site exploration** — Fetched the main map page and CCTV list page HTML.
2. **Layer configuration** — Extracted all `data-layerid`, `data-jsonurl`,
   `data-tooltipbaseurl`, and other `data-*` attributes from checkbox elements
   in the map legend.
3. **JS bundle analysis** — Downloaded and analyzed the following minified bundles:
   - `/bundles/listCctv` — Camera list DataTable rendering logic
   - `/bundles/map511` — Route and map layer management
   - `/bundles/map` — Google Maps integration and icon manager
   - `/bundles/newCamList` — Camera grid layout management
4. **API probing** — Tested discovered URL patterns against the live server,
   confirming responses and parameter requirements.
5. **HTML parsing** — Analyzed tooltip HTML to understand data model and image
   URL structure.

---

## Authentication

**No API key or authentication is required.** All endpoints are publicly accessible.

The server sets several cookies on initial page load:

| Cookie | Purpose |
|--------|---------|
| `session-id` | Session tracking (HttpOnly, Secure) |
| `session` | Session marker |
| `_culture` | Language preference (default `en`, 1-year expiry) |
| `__RequestVerificationToken` | CSRF token (only needed for POST mutations) |

For read-only data access (cameras, incidents, tooltips) no cookies are required.
The only required parameter is `lang=en` on data endpoints that otherwise return a
fallback PNG image.

---

## Discovered API Endpoints

### 1. Map Layer Markers — `/map/mapIcons/{layerId}?lang=en`

The primary data-discovery endpoint. Returns all map markers for a given layer as JSON.

**Method:** `GET`
**Authentication:** None
**Critical parameter:** `lang=en` (without it the server returns a PNG image)

#### Request

```
GET /map/mapIcons/Cameras?lang=en HTTP/2
Host: newengland511.org
```

#### Response Schema

```json
{
  "item1": {
    "url": "/Generated/Content/Images/511/map_camera.svg",
    "size": [29, 35],
    "origin": [0, 0],
    "anchor": [14, 34],
    "zindex": 0,
    "preventClustering": false,
    "isClickable": true,
    "rotation": 0
  },
  "item2": [
    {
      "itemId": "628",
      "location": [42.923527, -71.466947],
      "icon": {
        "size": [29, 35],
        "anchor": [14, 34],
        "zindex": 0,
        "preventClustering": false,
        "isClickable": true,
        "rotation": 0
      },
      "title": ""
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `item1` | object | Default icon SVG configuration for the layer |
| `item2` | array | Array of marker objects |
| `item2[].itemId` | string | Unique marker ID (used in tooltip endpoint) |
| `item2[].location` | [float, float] | `[latitude, longitude]` |
| `item2[].icon` | object | Per-marker icon override (usually matches item1) |
| `item2[].title` | string | Display title (typically empty; name comes from tooltip) |

**Known layer IDs:**

| Layer ID | Description | Typical Count |
|----------|-------------|---------------|
| `Cameras` | Traffic cameras (CCTV) | 408 total, ~141 in NH |
| `Incidents` | Active traffic incidents | ~24 |
| `IncidentClosures` | Incident-related closures | varies |
| `Construction` | Active construction zones | varies |
| `ConstructionClosures` | Construction closures | varies |
| `FutureRoadwork` | Scheduled future roadwork | varies |
| `FutureConstructionClosure` | Future construction closures | varies |
| `TruckRestrictions` | Truck weight/height limits | varies |
| `SpecialEvents` | Special events | varies |
| `SpecialEventClosures` | Special event closures | varies |
| `Waze` | Waze crowd-sourced reports | varies |
| `WazeIncidents` | Waze incidents | varies |
| `WazeClosures` | Waze closures | varies |
| `MessageSigns` | Dynamic message signs (DMS/VMS) | ~1,175 |
| `WeatherStations` | Roadside weather stations | varies |
| `WeatherEvents` | Weather event alerts | varies |
| `WeatherForecast` | Weather forecast points | varies |
| `DisplayedParking` | Parking availability | varies |
| `Bridge` | Bridge restrictions | varies |
| `InformationCenter` | Travel information centers | varies |
| `FerryTerminals` | Ferry terminals | varies |
| `MileMarkers` | Mile markers | varies |

---

### 2. Item Tooltip (Detail View) — `/tooltip/{layerId}/{itemId}?lang=en`

Returns an HTML snippet with full detail for a single map marker. Parsed from
the map layer URL pattern: `data-tooltipbaseurl="/tooltip/{layerId}/{id}?lang={lang}"`.

**Method:** `GET`
**Authentication:** None

#### Request

```
GET /tooltip/Cameras/628?lang=en HTTP/2
Host: newengland511.org
```

#### Response

Returns HTML (not JSON). Key elements:

```html
<div class="map-tooltip camTooltip">
  <h4><img src="/Content/Images/ic_camera.svg" /> Camera</h4>
  <table class="table-condensed table-striped">
    <tbody>
      <tr>
        <td><strong>FEE S 17.8 CCTV AX SWZ C-01</strong></td>
        ...
      </tr>
      <tr>
        <td>
          <div class="cctvCameraCarousel">
            <div id="carouselDiv-1236">
              <a href="/map/Cctv/1236" target="_blank">
                <img class="carouselCctvImage cctvImage"
                     data-lazy="/map/Cctv/1236"
                     data-fs-title="FEE S 17.8 CCTV AX SWZ C-01"
                     data-fs-desc=""
                     data-refresh-rate="10000"
                     id="1236img" />
              </a>
            </div>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
</div>
```

**Key data attributes on the `<img class="cctvImage">` element:**

| Attribute | Description |
|-----------|-------------|
| `data-lazy` | Relative URL of the live camera image: `/map/Cctv/{imageId}` |
| `data-fs-title` | Camera display name (full-screen title) |
| `data-fs-desc` | Camera description (often empty) |
| `data-refresh-rate` | Auto-refresh interval in milliseconds (default 10000 = 10 s) |
| `id` | `{imageId}img` — the numeric imageId |

**Mapping between siteId and imageId:**

The `siteId` (from `item2[].itemId` in the markers endpoint) is **not** the same as
the `imageId` used in camera image URLs. The mapping is:

```
siteId 1   → imageId 950   (WATERBURY I-89 North)
siteId 628 → imageId 1236  (FEE S 17.8 CCTV AX SWZ C-01)
siteId 220 → imageId 875   (101 WW 85.6)
siteId 800 → imageId 1408  (93 SN, MM 2.1)
```

The imageId is only discoverable by calling the tooltip endpoint for each siteId.

#### Tooltip for Other Layers

The same URL pattern works for other layers:

```
GET /tooltip/Incidents/76?lang=en
GET /tooltip/MessageSigns/441?lang=en
GET /tooltip/Construction/12345?lang=en
```

Each layer returns a different HTML template with appropriate fields.

**Incident tooltip example fields:**
- Location (road name)
- Description / event details
- Start time
- Anticipated end time
- Weight/height restrictions (if applicable)

**Message sign tooltip example fields:**
- Location (highway, direction, milepost)
- Last updated timestamp
- Current sign message text

---

### 3. Live Camera JPEG — `/map/Cctv/{imageId}`

Returns the current JPEG snapshot from a traffic camera.

**Method:** `GET`
**Authentication:** None
**Response:** `image/jpeg` (live snapshot, typically 30–200 KB)

#### Request

```
GET /map/Cctv/950 HTTP/2
Host: newengland511.org
```

#### Response

Raw JPEG bytes. The image is refreshed server-side every ~10 seconds.

To force cache-busting (as the JavaScript does), append a Unix timestamp hash:
```
GET /map/Cctv/950#1711567890
```

#### Camera image URL summary

```
https://newengland511.org/map/Cctv/{imageId}
```

where `{imageId}` is the integer from `data-lazy` in the tooltip HTML.

---

### 4. Camera Video URL — `/Camera/GetVideoUrl?imageId={imageId}`

For cameras that support streaming video (when `CctvEnableVideo=True`).

**Method:** `GET`
**Authentication:** None
**Response:** JSON with video stream configuration, or a string URL directly.

```
GET /Camera/GetVideoUrl?imageId=950
```

If a video URL is available, the client then POSTs the response to
`resources.CameraVideoUrl` to get the final stream URL. In the live environment,
`CctvEnableVideo` is currently set to `False` (disabled site-wide).

---

### 5. DataTable List Data — `/list/GetData/{typeId}`

Server-side DataTables endpoint for the camera/event list pages.

**Method:** `GET` (POST also accepted)
**Authentication:** None
**Note:** Without proper DataTables column parameters the `data` array is empty,
though `recordsTotal` and `recordsFiltered` are populated correctly.

#### Request (full parameter set)

```
GET /list/GetData/Cameras?draw=1&start=0&length=25
  &columns[0][data]=sortOrder&columns[0][name]=sortOrder
  &columns[0][orderable]=true&columns[0][searchable]=false
  &columns[1][data]=state&columns[1][name]=state
  &columns[1][searchable]=true&columns[1][orderable]=true
  &columns[2][data]=roadway&columns[2][name]=roadway
  &columns[2][searchable]=true&columns[2][orderable]=true
  &columns[3][data]=location&columns[3][name]=location
  &columns[3][searchable]=false&columns[3][orderable]=false
  &order[0][column]=1&order[0][dir]=asc
  &order[1][column]=0&order[1][dir]=asc
```

#### Response Schema

```json
{
  "draw": 1,
  "recordsTotal": 408,
  "recordsFiltered": 408,
  "data": [
    {
      "sortOrder": 1,
      "state": "New Hampshire",
      "roadway": "I-89",
      "location": "WATERBURY I-89 North",
      ...
    }
  ]
}
```

**Recommendation:** Use the `/map/mapIcons/{layer}` + `/tooltip/{layer}/{id}`
combination instead; it is simpler and more reliable.

---

### 6. Filter Values — `/List/UniqueColumnValuesForEvents/{typeId}`

Returns unique values for each filterable column in a list view.

**Method:** `GET`
**Authentication:** None

```
GET /List/UniqueColumnValuesForEvents/traffic
```

**Response:**
```json
{
  "state": ["Maine", "New Hampshire", "Vermont", ...],
  "roadway": ["I-89", "I-93", "US-1", ...],
  "severity": ["High", "Low", "Medium", "Minor", "Severe"],
  "subType": ["Construction", "Crash", "RoadClosed", ...],
  "direction": ["both directions", "east", "north", "south", "west"],
  "startDate": ["..."],
  "endDate": ["..."]
}
```

---

### 7. Geographic Routes — `/api/route/getroutes` and `/api/route/getlocations`

Route planning API (extracted from the map511 bundle).

```
GET /api/route/getlocations?latitude={lat}&longitude={lon}
GET /api/route/getroutes
POST /Api/Route/SaveUserRoute
GET /Api/Route/GetRouteByShareID?shareId={id}
GET /Api/Route/GetUserRouteStatistics?segmentId={id}
```

These require session cookies and are primarily used by authenticated users.

---

## New Hampshire Camera Network

### Geography

New Hampshire cameras are identified by geographic filtering:

| Bound | Value |
|-------|-------|
| Latitude min | 42.69° N |
| Latitude max | 45.31° N |
| Longitude min | -72.55° W |
| Longitude max | -70.95° W |

The eastern limit of -70.95° W captures the NH seacoast (I-95 corridor, MTA cameras)
while excluding most Maine cameras. A handful of cameras near the NH/ME border may
appear on either side; use camera names to confirm the state.

### Camera Statistics (live, as of 2026-03-27)

- **Total cameras in system:** 408 (all New England, with `lang=en`)
- **NH cameras (by bounding box):** ~150
- **Image refresh rate:** 10 seconds (10,000 ms)
- **Image format:** JPEG
- **Typical image size:** 30–200 KB

### Naming Convention

Camera names follow NHDOT's internal convention:
```
{ROUTE} {DIRECTION} {DESCRIPTION}
```

Examples:
- `WATERBURY I-89 North` — I-89 northbound at Waterbury
- `MILTON I-89 North` — I-89 northbound at Milton
- `FEE S 17.8 CCTV AX SWZ C-01` — Fee pond area, route S, mile 17.8
- `93 SN, MM 2.1` — US-93 southbound, milepost 2.1

---

## Python Client Usage

### Installation

No external dependencies. Requires Python 3.7+.

```bash
# No installation needed — stdlib only
python3 nhdot_client.py --help
```

### CLI Commands

#### List all cameras (quick — no names)
```bash
python3 nhdot_client.py cameras
```

Output:
```
SiteID            Lat         Lon  Title
-------------------------------------------------------
1           44.352994  -72.782259
3           44.629548  -73.147801
...
Total: 408
```

#### List NH cameras only
```bash
python3 nhdot_client.py cameras --nh
```

#### Get full detail for one camera
```bash
python3 nhdot_client.py camera 628
```

Output:
```
Site ID  : 628
Name     : FEE S 17.8 CCTV AX SWZ C-01
Views    : 1
  View 1: imageId=1236  url=https://newengland511.org/map/Cctv/1236
           refresh=10000 ms
```

#### Download a live camera image
```bash
# Show info only
python3 nhdot_client.py image 1236

# Save to file
python3 nhdot_client.py image 1236 --save waterbury.jpg
```

#### List traffic incidents
```bash
python3 nhdot_client.py incidents
python3 nhdot_client.py incidents --nh
```

#### List dynamic message signs
```bash
python3 nhdot_client.py signs
python3 nhdot_client.py signs --nh
```

#### Get plain-text tooltip for any item
```bash
python3 nhdot_client.py tooltip Cameras 628
python3 nhdot_client.py tooltip Incidents 76
python3 nhdot_client.py tooltip MessageSigns 441
```

#### List all available layer IDs
```bash
python3 nhdot_client.py layers
```

---

### Python API Usage

```python
from nhdot_client import (
    list_cameras,
    list_cameras_full,
    get_camera_tooltip,
    get_camera_image,
    get_camera_image_url,
    list_incidents,
    list_message_signs,
    get_tooltip_text,
    get_layer_markers,
)

# --- Camera discovery (fast: one HTTP request) ---
markers = list_cameras(nh_only=True)
print(f"NH cameras: {len(markers)}")
# → NH cameras: 141

for m in markers[:3]:
    print(f"  siteId={m.item_id}  lat={m.lat:.4f}  lon={m.lon:.4f}")

# --- Full camera detail (N+1 requests) ---
cam = get_camera_tooltip("628")
print(cam.name)             # FEE S 17.8 CCTV AX SWZ C-01
print(cam.primary_image_url)  # https://newengland511.org/map/Cctv/1236

# Access all view URLs
for view in cam.views:
    print(f"  imageId={view.image_id}  refresh={view.refresh_rate_ms}ms")

# --- Download live JPEG snapshot ---
jpeg_bytes = get_camera_image("1236")
with open("snapshot.jpg", "wb") as f:
    f.write(jpeg_bytes)
print(f"Saved {len(jpeg_bytes):,} bytes")

# --- Get just the URL (no download) ---
url = get_camera_image_url("950")
# → https://newengland511.org/map/Cctv/950

# --- Incidents ---
nh_incidents = list_incidents(nh_only=True)
for inc in nh_incidents:
    # Get details from tooltip
    detail = get_tooltip_text("Incidents", inc.item_id)
    print(f"Incident {inc.item_id}: {detail[:80]}")

# --- Message signs ---
nh_signs = list_message_signs(nh_only=True)
for sign in nh_signs[:5]:
    detail = get_tooltip_text("MessageSigns", sign.item_id)
    print(f"Sign {sign.item_id}: {detail[:100]}")

# --- Any layer ---
construction = get_layer_markers("Construction", lang="en")
print(f"Construction zones (all NE): {len(construction)}")

# --- Bulk NH cameras with full detail (slow: 141+ HTTP requests) ---
from nhdot_client import list_cameras_full
cameras = list_cameras_full(nh_only=True, max_cameras=10)
for cam in cameras:
    print(f"{cam.name:40s}  {cam.primary_image_url}")
```

---

## Rate Limiting & Best Practices

The server does **not** enforce rate limiting for public read-only access. However,
be considerate:

- For bulk operations, add `time.sleep(0.1)` between tooltip requests.
- Camera images refresh every 10 seconds; avoid polling more often than that.
- The marker lists (`/map/mapIcons/{layer}`) are lightweight and can be polled
  every 30–60 seconds to detect new incidents or camera status changes.
- No robots.txt restrictions apply to the data endpoints used here.

---

## Caching Strategy

For production use, consider caching:

| Endpoint | Suggested TTL |
|----------|--------------|
| `/map/mapIcons/{layer}` | 60 seconds (incidents) / 5 minutes (cameras) |
| `/tooltip/{layer}/{id}` | 5 minutes (camera names rarely change) |
| `/map/Cctv/{imageId}` | 10 seconds (live feed) |

---

## Complete Endpoint Reference

| Method | Path | Auth | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/map/mapIcons/{layer}?lang=en` | None | JSON | All markers for layer |
| GET | `/tooltip/{layer}/{id}?lang=en` | None | HTML | Detail for one marker |
| GET | `/map/Cctv/{imageId}` | None | JPEG | Live camera snapshot |
| GET | `/Camera/GetVideoUrl?imageId={id}` | None | JSON | Video stream URL |
| GET | `/list/GetData/{typeId}?...` | None | JSON | DataTable data |
| GET | `/List/UniqueColumnValuesForEvents/{typeId}` | None | JSON | Filter values |
| GET | `/api/route/getlocations?latitude=&longitude=` | Session | JSON | Route locations |
| GET | `/api/route/getroutes` | Session | JSON | Saved routes |
| GET | `/map/GetTransitRoute` | Session | JSON | Transit routing |
| GET | `/GetLatLng?id={id}` | None | JSON | Convert ID to coordinates |
| POST | `/My511/Login` | None→Session | JSON | Authenticate |
| POST | `/My511/ResendUserConfirmation` | None | JSON | Resend email |

---

## Technical Stack (Server-Side)

- **Framework:** ASP.NET (C#), MVC pattern with Razor views
- **CDN:** AWS CloudFront (`x-amz-cf-id` response header present)
- **Backend version:** 26.1.29 (from `?v=26.1.29` cache-buster on assets)
- **Data format:** JSON for API responses, HTML for tooltip views
- **JavaScript:** jQuery + Bootstrap frontend, DataTables for list views
- **Maps:** Google Maps API with custom overlay layers
- **Cameras:** JPEG snapshots (no HLS/RTSP streams for the public interface)

---

## Error Handling

| HTTP Status | Meaning |
|-------------|---------|
| 200 | Success |
| 200 + PNG body | Missing `lang=en` parameter on `/map/mapIcons/` |
| 404 | Invalid layer ID or item ID |
| 500 | Server error (rare) |

Always include `?lang=en` on `/map/mapIcons/` requests. Without it, the server
returns a `200 OK` with a PNG image body instead of JSON.

---

## Limitations

1. **No bulk camera detail endpoint.** Getting camera names and imageIds requires
   one HTTP request per camera site (N+1 problem). For 141 NH cameras this takes
   approximately 30–60 seconds of serial requests.

2. **imageId ≠ siteId.** The numeric ID in camera image URLs does not match the
   siteId from the markers endpoint. The mapping can only be obtained via the
   tooltip endpoint.

3. **Video streams disabled.** `CctvEnableVideo` is `False` in the current
   configuration. Only JPEG snapshots are available.

4. **DataTables endpoint quirk.** The `/list/GetData/Cameras` endpoint returns
   an empty `data` array unless very specific column parameter sets are provided
   (matching the exact column definitions from the page's JavaScript). The markers
   + tooltip approach is more robust.

5. **No WebSocket / real-time push.** All data must be polled via HTTP.

---

*Reverse engineered from newengland511.org on 2026-03-27.*
*No proprietary code was accessed. All data is publicly available via standard HTTP.*
