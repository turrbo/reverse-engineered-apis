# KDOT KanDrive Traffic API Client

Reverse-engineered Python client for the Kansas Department of Transportation (KDOT) KanDrive traffic information system at **https://www.kandrive.gov**.

No API key or authentication is required. All endpoints are publicly accessible.

---

## What is KanDrive?

KanDrive is KDOT's real-time traveler information platform built on the **Castle Rock ITS CARS (Connected Automated Road-Side)** platform. It provides:

- Live traffic camera feeds (HLS video streams and JPEG snapshots)
- Variable Message Sign (VMS) current messages
- Snowplow / AVL fleet location tracking
- Winter road conditions (ArcGIS-hosted)
- WZDx-compliant work zone feed
- Travel time data, RWIS weather stations, and more

---

## Quick Start

```python
from kdot_client import KanDriveClient

client = KanDriveClient()

# List all cameras
cameras = client.cameras.list_cameras()
print(f"Total cameras: {len(cameras)}")

# Filter to I-70 active cameras
i70_cameras = client.cameras.list_cameras(route_id="I-70", active_only=True)

# Get a single camera's snapshot URL
cam = client.cameras.get_camera(2048)
print(cam.primary_snapshot_url)

# Check VMS signs
signs = client.signs.active_messages()
for sign in signs:
    print(f"{sign.name}: {sign.current_message}")

# Track snowplows
for plow, status in client.plows.latest_positions():
    print(f"Plow {plow.plow_id} on {status.route_designator} heading {status.heading_string}")

# Get a corridor summary
summary = client.corridor_summary("I-70")
```

---

## Installation

No dependencies beyond Python 3.7+ standard library (`urllib`, `json`, `dataclasses`).

```bash
# Copy kdot_client.py to your project, then:
python kdot_client.py   # runs built-in live demo
```

---

## Architecture

### Reverse Engineering Notes

The KanDrive app (version 3.19.10 as of 2026-02) is a Webpack SPA served from an Amazon S3 / CloudFront origin. The relevant JS bundles are:

- `https://www.kandrive.gov/shared-2e3a0d6fa144ded6c3ea.js` — configuration, shared components
- `https://www.kandrive.gov/main-292718b1e59b152f8e88.js` — application logic, GraphQL queries

Key findings from the bundles:

```javascript
// Variable g in shared bundle:
g = "https://kstg.carsprogram.org"  // All REST API base

// Variable m in shared bundle:
m = "https://public.carsprogram.org/ks/prod"  // Custom layers (S3, access-denied publicly)

// endpoints object:
endpoints = {
    cameras:      `${g}/cameras_v1/api`,
    events:       `${g}/events_v1/api`,
    rwis:         `${g}/rwis_v1/api`,
    sign:         `${g}/signs_v1/api`,
    avl:          `${g}/avl_v2/api`,
    cms:          `${g}/cms_v1/api`,
    cmsGQL:       `${g}/cms_v1/api/graphql`,
    delay:        `${g}/delay_v1/api`,
    floodgates:   `${g}/floodgates_v1/api`,
    fuelingStations: `${g}/fueling-stations_v1/api`,
    locations:    `${g}/locations_v1/api`,
    mountainPasses: `${g}/mountain-passes_v1/api`,
    parking:      g,
    plowCamera:   `${g}/avl_v2/api/images`,
    restAreas:    `${g}/rest-areas_v1/api`,
    oversizeLoads: `${g}/oversize-load-check-in_v1/api`,
    journeyTimes: `${g}/traveltimes_v1/api/travel-times`,
    osrm:         "https://osrm-ks.carsprogram.org",
    nlp:          "https://nlp.carsprogram.org/api/v1/nlp",
    regionalRoadConditions: "https://services.arcgis.com/8lRhdTsQyJpO52F1/ArcGIS/..."
}

// Primary GraphQL endpoint (SPA relative path):
graphqlUrl = "/api/graphql"  // → resolves via CloudFront to CMS GraphQL
```

The SPA also uses `cmsGQL` (`/cms_v1/api/graphql`) for content/config queries.

### Backend Technology

- **Platform**: Castle Rock ITS CARS (castlerockits.com)
- **CDN**: Amazon CloudFront
- **SPA host**: Amazon S3
- **Media**: Wowza Streaming Engine (HLS) at `cdn3.wowza.com`
- **Snapshots**: `kscam.carsprogram.org`
- **Roads GIS**: ArcGIS Online (Esri)
- **Maps**: Google Maps API (`gme-castlerockassociates` enterprise client)
- **OSRM**: `osrm-ks.carsprogram.org` (self-hosted routing)
- **WMS tiles**: `gwc.carsprogram.org` (GeoWebCache, Castle Rock ITS)

---

## API Reference

### Base URLs

| Service | Base URL |
|---------|----------|
| All REST APIs | `https://kstg.carsprogram.org` |
| Camera snapshots | `https://kscam.carsprogram.org` |
| Road conditions (ArcGIS) | `https://services.arcgis.com/8lRhdTsQyJpO52F1/...` |
| WZDx work zones | `https://kscars.kandrive.gov/carsapi_v1/api/wzdx` |

---

### Camera API — `/cameras_v1/api`

**Endpoints tested and confirmed working:**

#### `GET /cameras_v1/api/cameras`

Returns all 575 public cameras as a JSON array.

```
GET https://kstg.carsprogram.org/cameras_v1/api/cameras
```

**Response fields (per camera):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique camera ID |
| `public` | bool | Public visibility flag |
| `name` | string | Location description (e.g. "I-70 at Deep Creek Road MM 315") |
| `lastUpdated` | int | Unix timestamp (milliseconds) |
| `active` | bool | Operational status |
| `location.fips` | int | State FIPS code (20 = Kansas) |
| `location.latitude` | float | Decimal degrees |
| `location.longitude` | float | Decimal degrees |
| `location.routeId` | string | Route designator (e.g. "I-70", "KS 39", "US 281") |
| `location.linearReference` | float | Mile marker |
| `location.cityReference` | string | Human-readable location reference |
| `cameraOwner.name` | string | Operating agency |
| `views[].type` | string | `"WMP"` (HLS video) or `"STILL_IMAGE"` (JPEG) |
| `views[].url` | string | HLS `.m3u8` playlist URL or direct JPEG URL |
| `views[].videoPreviewUrl` | string | JPEG snapshot URL (WMP cameras only) |
| `views[].imageTimestamp` | int | Unix ms of last image update |

**Example response:**
```json
{
  "id": 2048,
  "public": true,
  "name": "I-70 at Deep Creek Road MM 315",
  "lastUpdated": 1774643106495,
  "active": true,
  "location": {
    "fips": 20,
    "latitude": 39.065494,
    "longitude": -96.507927,
    "routeId": "I-70",
    "linearReference": 315.54,
    "cityReference": "15 miles east of the Grandview Plaza area"
  },
  "cameraOwner": {"name": "KDOT ITS"},
  "views": [
    {
      "name": "I-70 at Deep Creek Road MM 315",
      "type": "WMP",
      "url": "https://cdn3.wowza.com/5/VE5YZ3J3eUtPL1I4/KDOT/1-070-3150-2-I-70atDeepCreekRoad.stream/playlist.m3u8",
      "videoPreviewUrl": "https://kscam.carsprogram.org/snapshots/GEN_1-070-3150-2-I-70atDeepCreekRoad.jpeg",
      "imageTimestamp": 1774643050000
    }
  ]
}
```

#### `GET /cameras_v1/api/cameras/{id}`

Returns a single camera by numeric ID.

```
GET https://kstg.carsprogram.org/cameras_v1/api/cameras/2048
```

**Camera types:**

| Type | Count | Description |
|------|-------|-------------|
| `WMP` | ~400 | Wowza Media Player — live HLS stream + JPEG snapshot |
| `STILL_IMAGE` | ~175 | Periodic JPEG refresh only |

**Camera owners observed:**

| Owner | Description |
|-------|-------------|
| KDOT ITS | KDOT Intelligent Transportation Systems — primary state network |
| KDOT RWIS | Road Weather Information System cameras |
| KC Scout | Kansas City regional traffic management |
| City of Topeka | Municipal cameras |
| KDOT Region | Regional KDOT cameras |

**Camera snapshot URL patterns:**
- `https://kscam.carsprogram.org/snapshots/GEN_<stream-id>.jpeg` — WMP preview
- `https://kscam.carsprogram.org/KDOT_<station-id>_IMAGE001.JPG` — RWIS still
- Direct JPEG URLs at `kscam.carsprogram.org` (no auth required)

---

### VMS Signs API — `/signs_v1/api`

#### `GET /signs_v1/api/signs`

Returns all variable message signs statewide.

```
GET https://kstg.carsprogram.org/signs_v1/api/signs
```

**Response fields (per sign):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Composite ID: `"kansassigns*<n>"` or `"kcscout*<n>"` |
| `name` | string | Location description |
| `status` | string | `"DISPLAYING_MESSAGE"`, `"BLANK"`, or `"ERROR_OR_FAILURE"` |
| `agencyId` | string | `"kansassigns"` or `"kcscout"` |
| `agencyName` | string | `"KS Signs"` or `"KC Scout"` |
| `lastUpdated` | int | Unix ms |
| `display.pages[]` | array | Rotating message pages |
| `display.pages[].lines` | string[] | Up to 3 text lines |
| `display.pages[].justification` | string | `"CENTER"` or `"LEFT"` |
| `location.routeId` | string | Route designator |
| `location.latitude/longitude` | float | Coordinates |
| `location.signFacingDirection` | string | `"E"`, `"W"`, `"N"`, or `"S"` |
| `properties.signType` | string | `"VMS_FULL"` or `"VMS_IMAGE"` |
| `properties.maxLinesPerPage` | int | Display capacity |

#### `GET /signs_v1/api/signs/{id}`

Returns a single sign. The `*` in the ID must be URL-encoded as `%2A` or left as `*`.

```
GET https://kstg.carsprogram.org/signs_v1/api/signs/kansassigns*179
```

---

### Snowplow / AVL API — `/avl_v2/api`

#### `GET /avl_v2/api/plows`

Returns all tracked plow vehicles with position history breadcrumb trail.

```
GET https://kstg.carsprogram.org/avl_v2/api/plows
```

**Response fields (per plow):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Vehicle identifier (e.g. `"2683061"`) |
| `statuses[]` | array | Position history records |
| `statuses[].timestamp` | int | Unix ms |
| `statuses[].latitude` | float | |
| `statuses[].longitude` | float | |
| `statuses[].routeDesignator` | string | Current route (e.g. `"US 281"`) |
| `statuses[].vehicleName` | string | Same as id |
| `statuses[].headingString` | string | Cardinal direction (e.g. `"Northeast"`) |
| `statuses[].nearbyPointsDescription` | string | e.g. `"Between KS 18 and I-70"` |
| `statuses[].plowIconName` | string | Icon asset path |
| `statuses[].totalTruckCount` | int | Total fleet size |

#### `GET /avl_v2/api/plows/{id}`

Returns position history for a single plow.

**Note:** Plow data is seasonal. During summer, fewer or no plows may be active.

---

### Winter Road Conditions — ArcGIS FeatureServer

This layer is maintained by multiple Midwest DOTs sharing the same ArcGIS service.

```
GET https://services.arcgis.com/8lRhdTsQyJpO52F1/ArcGIS/rest/services/
    Midwest_Winter_Road_Conditions_View/FeatureServer/0/query
    ?where=1=1&outFields=*&f=json&resultRecordCount=2000
```

**ArcGIS query parameters:**

| Parameter | Description |
|-----------|-------------|
| `where` | SQL WHERE clause (e.g. `1=1` for all records) |
| `outFields` | `*` for all fields |
| `f` | `json` |
| `resultRecordCount` | Max records (default 1000, up to 2000) |

**Feature attribute fields:**

| Field | Type | Description |
|-------|------|-------------|
| `OBJECTID` | int | ArcGIS row ID |
| `ROUTE_NAME` | string | Route designation |
| `HEADLINE` | string | Condition summary |
| `ROAD_CONDITION` | int | Numeric condition code |
| `STATUS` | string | Data status |
| `REPORT_UPDATED` | timestamp | Last update |
| `SOURCE` | string | Reporting DOT |

**Road condition codes:**

| Code | Label |
|------|-------|
| 1 | Normal / Dry |
| 2 | Wet |
| 3 | Snow / Ice Covered |
| 4 | Partially Covered |
| 5 | Completely Covered |
| 6 | Impassable |
| 7 | Not Advised |

---

### WZDx Work Zone Feed — `/carsapi_v1/api/wzdx`

Provides standardized work zone data per the [FHWA WZDx specification](https://github.com/usdot-jpo-ode/wzdx).

```
GET https://kscars.kandrive.gov/carsapi_v1/api/wzdx
```

(Note: `https://ks.carsprogram.org/carsapi_v1/api/wzdx` redirects to this URL via HTTP 301.)

Returns a GeoJSON FeatureCollection where each Feature's `properties` object contains a `road_event` with fields like `event_type`, `road_name`, `direction`, `start_date`, `end_date`, and geometry coordinates.

---

## Additional API Endpoints (Discovered, Not Fully Implemented)

These endpoints exist in the JS configuration but may require specific sub-paths or POST bodies:

| Endpoint Pattern | Purpose |
|-----------------|---------|
| `GET /rwis_v1/api/...` | Road Weather Information System stations |
| `GET /traveltimes_v1/api/travel-times` | Travel time segments |
| `GET /rest-areas_v1/api/...` | Rest area information |
| `POST /cms_v1/api/graphql` | Content Management System (messages, dashboards) |
| `GET /events_v1/api/...` | Traffic incidents and construction |
| `GET /locations_v1/api/...` | Location search |
| `POST /eventfeedback_v1/api/...` | Incident feedback (POST + reCAPTCHA) |
| `GET /delay_v1/api/...` | Traffic delay data |
| `GET /fueling-stations_v1/api/...` | Truck fueling stations |
| `GET /signs_v1/api/...` | VMS signs (documented above) |

### CMS GraphQL API

The application uses Apollo Client to query a GraphQL API at `/api/graphql` (proxied through CloudFront). Key query operations identified:

```graphql
# Fetch a single camera with nearby context
query Camera($cameraId: ID!, $layerSlugs: [String!]!, $nearbyViewLimit: Int!, ...) {
  cameraQuery(cameraId: $cameraId) {
    camera { uri color title bbox icon agencyAttribution lastUpdated location views ... }
    nearbyResults { ... }
  }
}

# Fetch a single event/incident
query Event($eventId: ID!, $layerSlugs: [String!]!, ...) {
  eventQuery(eventId: $eventId) {
    event { uri title description priority laneImpacts location ... }
  }
}

# Fetch RWIS weather station
query Rwis($rwisId: ID!, $layerSlugs: [String!]!, ...) {
  weatherStationQuery(rwisId: $rwisId) {
    weatherStation { ... drivingCondition fields }
  }
}

# Dashboard (homepage summary)
query Dashboard($layerSlugs: [String!]!, $maxPriority: Int, ...) {
  dashboardQuery {
    cameraViewsPayload { cameraViews { ... } }
    cmsPayload { messages { ... } campaigns { ... } }
    collections(layerSlugs: $layerSlugs, maxPriority: $maxPriority) { ... }
    favoritesPayload { ... }
  }
}

# Map features (all layer data for viewport)
query MapFeatures($input: MapFeaturesArgs!, $plowType: String) {
  mapFeaturesQuery(input: $input) {
    mapFeatures { bbox title tooltip uri features ... }
  }
}
```

The `layerSlugs` variable controls which data layers are returned. Common slugs include camera layer identifiers for KDOT, KC Scout, and other agencies.

---

## Live Data Verification (2026-03-27)

All endpoints below were tested and confirmed returning live data:

| Endpoint | Status | Records |
|----------|--------|---------|
| `/cameras_v1/api/cameras` | 200 OK | 575 cameras |
| `/cameras_v1/api/cameras/2048` | 200 OK | Single camera |
| `/cameras_v1/api/cameras/1` | 200 OK | Single camera |
| `/signs_v1/api/signs` | 200 OK | ~50+ signs |
| `/signs_v1/api/signs/kansassigns*179` | 200 OK | Single sign |
| `/avl_v2/api/plows` | 200 OK | 10 plows |
| `/avl_v2/api/plows/2683061` | 200 OK | 72 status records |
| ArcGIS road conditions | 200 OK | Multiple segments |
| WZDx feed | 200 OK (redirect) | GeoJSON FeatureCollection |
| `kscam.carsprogram.org/snapshots/GEN_*.jpeg` | 200 OK | Live JPEG images |

---

## Usage Examples

### Download a Camera Snapshot

```python
from kdot_client import KanDriveClient

client = KanDriveClient()

# Fetch camera details
cam = client.cameras.get_camera(2048)
print(f"Camera: {cam.name}")
print(f"Route: {cam.location.route_id} MM {cam.location.linear_reference:.1f}")
print(f"Snapshot: {cam.primary_snapshot_url}")

# Download the snapshot image
if cam.primary_snapshot_url:
    client.cameras.download_snapshot(cam, "/tmp/i70_camera.jpg")
    print("Saved to /tmp/i70_camera.jpg")
```

### Find Cameras Near a Location

```python
# Find cameras near Topeka, KS (39.05, -95.68)
nearby = client.cameras.cameras_near(lat=39.05, lon=-95.68, radius_miles=10.0)
for dist, cam in nearby:
    print(f"{dist:.1f} mi — [{cam.camera_id}] {cam.name}")
```

### Monitor VMS Sign Messages

```python
signs = client.signs.active_messages()
for sign in signs:
    print(f"{sign.agency_name} | {sign.name} [{sign.location.route_id}]")
    for page in sign.pages:
        print(f"  Page: {' / '.join(page.lines)}")
```

### Get All I-70 Streaming Cameras

```python
cameras = client.cameras.list_cameras(route_id="I-70", active_only=True)
for cam in cameras:
    if cam.hls_stream_url:
        print(f"{cam.name}: {cam.hls_stream_url}")
```

### Track Plow Fleet

```python
positions = client.plows.latest_positions()
print(f"Fleet size: {positions[0][1].total_truck_count if positions else 'N/A'}")
for plow, status in positions:
    print(f"Plow {plow.plow_id}: {status.route_designator} heading {status.heading_string}")
    print(f"  Near: {status.nearby_points_description}")
    print(f"  At: {status.recorded_at.isoformat()}")
```

### WZDx Work Zone Integration

```python
features = client.work_zones.list_work_zone_features()
print(f"Active work zones: {len(features)}")
for feature in features[:5]:
    props = feature.get("properties", {})
    road_event = props.get("road_event", props)
    print(f"  {road_event.get('road_name', 'N/A')} — {road_event.get('event_type', 'N/A')}")
```

### Full Corridor Analysis

```python
summary = client.corridor_summary("I-70")
print(f"I-70 Corridor:")
print(f"  Cameras: {summary['cameras']['total']} active")
print(f"    Streaming: {summary['cameras']['streaming']}")
print(f"  Signs with messages: {summary['signs']['total']}")
for msg in summary["signs"]["messages"]:
    print(f"    > {msg}")
```

---

## Notes

### Polling Etiquette

The SPA polls every 60 seconds (`clientPollTime: 60000` ms in the JS config). Use a similar or longer interval to be a good API citizen.

### Camera Video Streams

HLS streams (`*.m3u8`) are served by Wowza Streaming Engine at `cdn3.wowza.com`. They can be played with:
- `ffplay https://cdn3.wowza.com/...playlist.m3u8`
- VLC, MPV, or any HLS-capable player
- `ffmpeg` for frame capture

### Route ID Formats

The API uses route IDs as stored in the database, not standardized formats:
- Interstates: `"I-70"`, `"I-135"`, `"I-435"`
- US Highways: `"US 281"`, `"US 56"`, `"US 40"`
- State Routes: `"KS 39"`, `"KS 99"`, `"KS 18"`

Filtering is applied client-side; the API always returns the full dataset.

### Image Freshness

- WMP cameras: snapshots typically update every 1–3 minutes
- RWIS STILL_IMAGE cameras: update every 10–60 minutes
- Use `views[].imageTimestamp` to check data age before displaying

### Plow Data Seasonality

The plow tracking system is active during winter operations (approximately November–March). The `totalTruckCount` field reflects the statewide fleet size (typically 130–140 trucks when active).

---

## Related KDOT Resources

| Resource | URL |
|----------|-----|
| KanDrive Web App | https://www.kandrive.gov |
| KDOT Main Site | https://www.ksdot.org |
| K-TRIPS (commercial vehicles) | https://k-trips.ksdot.gov |
| TPIMS Truck Parking | https://tpims.ksdot.gov |
| RWIS Data | http://rwis.ksdot.org |
| KanDrive Alerts Subscription | https://subscription.kandrive.gov/alerts/news |
| iOS App | https://apps.apple.com/us/app/id1537865653 |
| WZDx Feed (direct) | https://kscars.kandrive.gov/carsapi_v1/api/wzdx |
| KDOT Social Media | https://www.ksdot.gov/about/news-and-events/events-and-notices/kdot-social |

---

## Disclaimer

This client is reverse-engineered from publicly accessible web resources. The KDOT KanDrive platform is built and operated by **Castle Rock ITS** (castlerockits.com) on behalf of KDOT. No private APIs or authenticated endpoints are used. All data belongs to the Kansas Department of Transportation.
