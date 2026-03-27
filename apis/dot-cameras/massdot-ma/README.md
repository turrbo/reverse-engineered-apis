# MassDOT / Mass511 Traffic Camera API — Reverse Engineering Report & Python Client

## Overview

This document describes the reverse-engineered API used by the Massachusetts
Department of Transportation's public traffic information system at
**https://www.mass511.com** (Mass511), and provides a production-quality
Python client (`massdot_client.py`) that works with the live system.

The site is built on [CastleRock Associates'](https://castlerockits.com/)
CARS 511 platform (version 3.19.14 as of March 2026).  All data described
here is publicly accessible — **no API key, authentication, or account is
required**.

---

## Reverse Engineering Methodology

1. Fetched the site HTML and located the main JavaScript bundle
   (`/main-c233e81a56a7e756edd0.js`, ~1.1 MB minified).
2. Extracted all URL constants and endpoint configurations from the bundle.
3. Identified the GraphQL endpoint at `/api/graphql` (served through CloudFront
   CDN, proxied from an AWS API Gateway / Express backend).
4. Extracted all GraphQL query definitions embedded as template literals in
   the bundle.
5. Mapped all layer slug enum values (e.g. `NORMAL_CAMERA="normalCameras"`,
   `ROAD_REPORTS="roadReports"`) to their string values.
6. Validated each endpoint and query against the live system.

---

## Architecture

```
Browser  ──HTTPS──►  CloudFront CDN  ──►  www.mass511.com/api/graphql
                                          (AWS API Gateway + Express)
                                          │
                                          └──►  CastleRock CARS Platform
                                                 matg.carsprogram.org
                                                 (microservices)

Camera images:  public.carsprogram.org/cameras/MA/<id>-fullJpeg.jpg
```

- The frontend is a LitElement / Redux single-page app.
- All map data is retrieved through a single **GraphQL endpoint**.
- The `public.carsprogram.org/cameras/MA/` CDN is an S3+CloudFront bucket
  that serves refreshing JPEG snapshots (no auth needed).
- A secondary REST base (`matg.carsprogram.org`) hosts microservice APIs
  (accounts, events, cameras, signs, RWIS, travel times, etc.) but these
  are not directly accessible from outside the CDN — the mass511.com proxy
  must be used.

---

## Discovered API Endpoints

### Primary GraphQL Endpoint

| Item | Value |
|------|-------|
| URL | `https://www.mass511.com/api/graphql` |
| Method | `POST` |
| Content-Type | `application/json` |
| Auth | None |
| Rate limiting | None observed |

The endpoint is served via CloudFront and uses an Express GraphQL server
behind AWS API Gateway.

---

### Camera Image CDN

| Item | Value |
|------|-------|
| Base URL | `https://public.carsprogram.org/cameras/MA/` |
| Format | `<imageId>-fullJpeg.jpg` |
| Auth | None (public S3 bucket via CloudFront) |
| Cache | ~2 minute refresh cycle |
| CORS | `access-control-allow-origin: *` |

Example:
```
https://public.carsprogram.org/cameras/MA/1226-fullJpeg.jpg
```

Images may carry a cache-busting timestamp suffix added by the frontend:
```
https://public.carsprogram.org/cameras/MA/1226-fullJpeg.jpg?1774645680000
```

---

### Backend Microservice Base URLs (internal, not directly accessible)

These URLs are embedded in the JavaScript bundle and used internally by the
GraphQL resolvers.  Direct access from outside is blocked by CloudFront.

| Service | URL |
|---------|-----|
| Cameras | `https://matg.carsprogram.org/cameras_v1/api` |
| Events | `https://matg.carsprogram.org/events_v1/api` |
| Signs | `https://matg.carsprogram.org/signs_v1/api` |
| RWIS (weather stations) | `https://matg.carsprogram.org/rwis_v1/api` |
| Travel Times | `https://matg.carsprogram.org/traveltimes_v1/api/travel-times` |
| AVL (plow vehicles) | `https://matg.carsprogram.org/avl_v2/api` |
| Rest Areas | `https://matg.carsprogram.org/rest-areas_v1/api` |
| Locations | `https://matg.carsprogram.org/locations_v1/api` |
| CMS | `https://matg.carsprogram.org/cms_v1/api` |
| Accounts | `https://matg.carsprogram.org/publicaccounts_v1/api` |
| Feedback | `https://matg.carsprogram.org/eventfeedback_v1/api` |
| NLP Search | `https://nlp.carsprogram.org/api/v1/nlp` |
| Static data | `https://public.carsprogram.org/ma/prod` |

---

## GraphQL Queries

### 1. MapFeatures Query

Fetches all features (cameras, events, signs, clusters) within a geographic
bounding box for one or more layer types.

```graphql
query MapFeatures($input: MapFeaturesArgs!) {
    mapFeaturesQuery(input: $input) {
        mapFeatures {
            bbox
            title
            tooltip
            uri
            __typename
            ... on Cluster { maxZoom }
            ... on Sign { signDisplayType }
            ... on Event { priority }
            ... on Camera {
                active
                views(limit: 5) {
                    uri
                    ... on CameraView { url }
                    category
                }
            }
        }
        error { message type }
    }
}
```

**Variables:**
```json
{
  "input": {
    "north": 42.9,
    "south": 41.2,
    "east": -69.8,
    "west": -73.5,
    "zoom": 12,
    "layerSlugs": ["normalCameras"],
    "nonClusterableUris": null
  }
}
```

**Notes:**
- The `layerSlugs` field controls which data types are returned.  Each slug
  should be queried separately for best results (the app does this in parallel).
- At low zoom levels (< 10), individual camera markers collapse into `Cluster`
  objects.  Use zoom ≥ 12 for individual camera results.
- `bbox` is returned as `[west, south, east, north]` (GeoJSON convention).

---

### 2. Camera Detail Query

```graphql
query CameraDetail($cameraId: ID!) {
    cameraQuery(cameraId: $cameraId) {
        camera {
            uri
            color
            title
            bbox
            icon
            active
            agencyAttribution { agencyName }
            lastUpdated { timestamp timezone }
            location {
                primaryLinearReference
                secondaryLinearReference
            }
            views(limit: 20) {
                uri
                category
                ... on CameraView { url }
            }
        }
    }
}
```

**Variables:** `{ "cameraId": "10257" }` (numeric ID, not the full URI)

---

### 3. Event Detail Query

```graphql
query EventDetail($eventId: ID!, $layerSlugs: [String!]!) {
    eventQuery(eventId: $eventId, layerSlugs: $layerSlugs) {
        event {
            uri
            title
            description
            bbox
            location { primaryLinearReference secondaryLinearReference }
            icon
            color
            lastUpdated { timestamp timezone }
            beginTime { timestamp timezone }
            isWazeEvent
            priority
            agencyAttribution { agencyName agencyURL }
        }
    }
}
```

**Variables:** `{ "eventId": "MA-2426211456467036", "layerSlugs": ["roadReports"] }`

---

### 4. Route Search Query

Returns all traffic items and camera views along a named route corridor.

```graphql
query SearchRoute($routeId: String!, $layerSlugs: [String!]!) {
    searchRoadwayGeometryQuery(routeId: $routeId, layerSlugs: $layerSlugs) {
        geometry            # Google encoded polyline for the route
        results {
            uri
            title
            __typename
        }
        cameraViews {
            uri
            url
            title
            category
        }
        error { message type }
    }
}
```

**Variables:** `{ "routeId": "I-90", "layerSlugs": ["roadReports", "normalCameras"] }`

**Route ID format:** `I-90`, `I-93`, `I-495`, `US-6`, `RT-128`, `RT-3`, etc.

---

### 5. Notifications Query

```graphql
query {
    notificationsQuery {
        notifications {
            uri
            title
            description
            icon
            type
            lastUpdated { timestamp timezone }
            audioURL
        }
        error { message type }
    }
}
```

Returns system-wide banners/alerts (empty array when no active alerts).

---

### 6. CMS Messages Query

```graphql
query {
    cmsMessagesQuery {
        cmsMessages {
            uri
            title
            content
            priority
            messageType
            displayLocations
        }
        error { type }
    }
}
```

---

## Layer Slugs

The `layerSlugs` parameter determines which data type is returned.

| Slug | Description |
|------|-------------|
| `roadReports` | Crashes, closures, road reports |
| `constructionReports` | Active construction / roadwork |
| `towingProhibitedReports` | Towing prohibited zones |
| `truckersReports` | Truckers / commercial vehicle reports |
| `weatherWarningsAreaEvents` | NWS weather warning polygons |
| `winterDriving` | Winter driving condition reports |
| `future` | Future / scheduled construction |
| `wazeReports` | Waze crowd-sourced incident reports |
| `normalCameras` | Standard roadside traffic cameras |
| `hotCameras` | Featured / highlighted cameras |
| `plowCameras` | Snow plow vehicle cameras |
| `electronicSigns` | Electronic VMS / DMS signs |
| `electronicSignsInactive` | Inactive electronic signs |
| `postedWeightSigns` | Posted weight restriction signs |
| `bridgeHeights` | Bridge height restriction signs |
| `trafficSpeeds` | Google traffic speed overlay |
| `roadConditions` | Road surface conditions (winter) |
| `regionalRoadConditions` | Regional road condition areas |
| `restAreas` | Highway rest areas and service plazas |
| `mileMarkers` | Highway mile markers |
| `weighStations` | Commercial vehicle weigh stations |
| `ferryReports` | Ferry service status reports |
| `potholeTruckLocations` | Pothole repair truck locations |
| `fuelingStations` | EV charging / fueling stations |
| `heightRestrictions` | Vertical clearance restrictions |
| `widthRestrictions` | Width restrictions |
| `weightRestrictions` | Weight restriction advisories |
| `lengthRestrictions` | Length restrictions |
| `speedRestrictions` | Speed restrictions |

---

## Response Formats

### Camera Object

```json
{
  "uri": "camera/10257",
  "title": "I-93: Ramp CC-EB-Boston-90E x24C to 93S b",
  "bbox": [-71.05923, 42.34629, -71.05923, 42.34629],
  "active": true,
  "icon": "/images/icon-camera-fill-solid.svg",
  "color": "#707070",
  "agencyAttribution": { "agencyName": "MASSDOT" },
  "lastUpdated": { "timestamp": 1760004196234, "timezone": "America/New_York" },
  "location": { "primaryLinearReference": 16.28, "secondaryLinearReference": null },
  "views": [
    {
      "uri": "camera/10257/2089260390",
      "url": "https://public.carsprogram.org/cameras/MA/1226-fullJpeg.jpg",
      "category": "VIDEO"
    }
  ]
}
```

**Notes:**
- `primaryLinearReference` is a highway mile-marker distance in miles.
- `lastUpdated.timestamp` is milliseconds since Unix epoch.
- `views[].url` is a direct JPEG snapshot URL; refresh this URL to get
  the latest frame (no streaming, just periodic JPEG refresh).
- The `category` field is `"VIDEO"` for refreshing JPEG feeds.

### Event Object

```json
{
  "uri": "event/MA-2426211456467036",
  "title": "RT-114 eastbound: Crash.",
  "description": "<div>…</div>",
  "bbox": [-70.95307, 42.54927, -70.95307, 42.54927],
  "priority": 3,
  "icon": "/images/tg_crash_urgent.svg",
  "color": "#FF00FF",
  "lastUpdated": { "timestamp": 1774636592000, "timezone": "America/New_York" },
  "beginTime": { "timestamp": 1774636592000, "timezone": "America/New_York" },
  "isWazeEvent": false,
  "location": { "primaryLinearReference": 15.70 },
  "agencyAttribution": { "agencyName": "Massachusetts DOT", "agencyURL": null }
}
```

**Priority scale:**
- 1 = Critical (road closed with major delay)
- 2 = High
- 3 = Moderate (crash, lane closure)
- 4 = Low (minor incident)
- 5 = Informational (construction, future work)

**URI formats:**
- MassDOT events: `event/MASSDOT-<uuid>-<id>`
- Real-time incidents: `event/MA-<numeric-id>`
- Waze events: `event/<namespace>-<id>`

### Sign Object (MapFeature)

```json
{
  "__typename": "Sign",
  "uri": "electronic-sign/massachusettsBridgeHeightSigns*2LE",
  "title": "I-95: I 95 / RT128 under TRAPELO RD",
  "tooltip": "I 95 / RT128 under TRAPELO RD - 14'-1\"",
  "bbox": [-71.25729, 42.41529, -71.25729, 42.41529],
  "signDisplayType": "BRIDGE_HEIGHT"
}
```

`signDisplayType` values observed:
- `BRIDGE_HEIGHT` — vertical clearance sign
- `OVERLAY_TPIM` — travel time / VMS overlay
- `OVERLAY_TRAVEL_TIME` — travel time display
- `DEFAULT_VMS` — variable message sign

---

## CDN Camera Image Pattern

Camera snapshot URLs follow a consistent pattern:

```
https://public.carsprogram.org/cameras/MA/{imageId}-fullJpeg.jpg
```

The `imageId` is an integer (e.g. `1226`, `407968`, `432530`).  The
`camera/view` URI from the GraphQL response encodes both the camera ID and
the view/perspective ID:

```
camera/{cameraId}/{viewId}
```

To force a cache refresh, append the current Unix timestamp in milliseconds
(the frontend does this automatically for recently-updated cameras):

```
https://public.carsprogram.org/cameras/MA/1226-fullJpeg.jpg?1774645680000
```

---

## Authentication & Rate Limiting

- **No authentication** is required for any read-only query.
- No `Authorization` header or API key is needed.
- The `User-Agent` header should be set to a recognizable browser string to
  avoid potential bot blocking.
- No rate limiting has been observed during testing, but the app sends one
  request per layer slug per map move (debounced to 100 ms).
- The GraphQL endpoint is served through CloudFront with a 5-second cache TTL.
- Camera images have approximately a 2-minute refresh cycle.

---

## Python Client

### Installation

No external dependencies — uses Python 3.8+ standard library only
(`urllib`, `json`, `dataclasses`).

```bash
python massdot_client.py --help
```

### CLI Commands

```
cameras          List traffic cameras in a bounding box
events           List traffic events in a bounding box
camera <ID>      Get full details for a single camera
event <ID>       Get full details for a single event
route <ROUTE>    Get all items along a named route
signs            List electronic/height signs
notifications    Show system notifications/banners
layers           Print all known layer slugs
```

### Common Options

```
--bbox "south,north,west,east"   Geographic filter (default: all of MA)
--zoom N                          Map zoom level
--layer SLUG                      Single layer slug filter
```

### Example CLI Runs

```bash
# List cameras in the Boston metro area
python massdot_client.py cameras --bbox "42.2,42.5,-71.5,-70.9"

# All active road reports statewide
python massdot_client.py events --layer roadReports

# Full detail for a specific camera (I-93 South Boston)
python massdot_client.py camera 10257

# Full detail for a specific event
python massdot_client.py event MA-2426211456467036

# All events and cameras along I-90 (Massachusetts Turnpike)
python massdot_client.py route I-90

# Bridge height signs near Boston
python massdot_client.py signs --bbox "42.2,42.5,-71.5,-70.9"

# System notifications
python massdot_client.py notifications

# Print all layer slug names
python massdot_client.py layers
```

### Python API Usage

```python
from massdot_client import (
    BoundingBox,
    list_cameras,
    list_events,
    get_camera,
    get_event,
    search_route,
    get_notifications,
    LAYER_SLUGS,
)

# --- List cameras in a bounding box ---
boston_bbox = BoundingBox(south=42.3, north=42.4, west=-71.2, east=-71.0)
cameras = list_cameras(boston_bbox, zoom=14)
for feat in cameras:
    print(feat.title, "->", feat.views[0].url if feat.views else "no image")

# --- Get full camera details ---
cam = get_camera("10257")
print(cam.title, cam.snapshot_url)
print(f"Last updated: {cam.last_updated.isoformat()}")

# --- List road reports statewide ---
ma = BoundingBox.from_ma_statewide()
events = list_events(ma, layer_slugs=["roadReports"], zoom=8)
for feat in events:
    print(f"[P{feat.priority}] {feat.title}")

# --- Get full event details ---
ev = get_event("MA-2426211456467036")
print(ev.title, ev.description)

# --- Search along a route ---
result = search_route("I-90")
print(f"{len(result.events)} events, {len(result.camera_views)} cameras on I-90")
for cv in result.camera_views[:5]:
    print(f"  {cv.title}: {cv.url}")

# --- System notifications ---
notifs = get_notifications()
for n in notifs:
    print(n.title, n.description)

# --- Low-level GraphQL ---
from massdot_client import _graphql_request
data = _graphql_request(
    "{ cameraQuery(cameraId: \"10257\") { camera { uri title } } }"
)
```

---

## Data Refresh Rates

| Data Type | Observed Refresh |
|-----------|-----------------|
| Camera JPEG snapshots | ~2 minutes |
| Events / incidents | ~1–2 minutes (CloudFront TTL: 60s) |
| Construction reports | ~5 minutes |
| Road conditions | ~5 minutes |
| Sign messages | ~30–60 seconds |
| Notifications | ~60 seconds |

---

## Known Limitations

1. **No HLS/RTSP streams.** Camera feeds are JPEG snapshots only — there is
   no real-time video stream.  The frontend refreshes these periodically.

2. **No historical data.** The API only serves current/live data.

3. **Clusters at low zoom.** Below zoom ~10, individual camera markers are
   collapsed into `Cluster` objects.  Use zoom ≥ 12 for individual results.

4. **Route IDs are case-sensitive.** Use the format `I-90`, `US-6`, `RT-128`
   (not `i-90` or `Route 128`).

5. **`geometry.coordinates` is an encoded polyline.** The route geometry
   returned by `searchRoadwayGeometryQuery` uses Google's Encoded Polyline
   format.  Use the `polyline` library or implement the decoder to get
   lat/lon coordinates.

6. **Travel times and RWIS require internal APIs.** The travel time sign
   data and road weather station (RWIS) readings are not directly accessible
   through the public GraphQL endpoint — they appear to require queries against
   the internal microservice APIs which are blocked at the CDN level.

---

## Discovered GraphQL Types (Partial Schema)

```graphql
type Query {
    mapFeaturesQuery(input: MapFeaturesArgs!): MapFeaturesPayload
    cameraQuery(cameraId: ID!): CameraPayload
    eventQuery(eventId: ID!, layerSlugs: [String!]!): EventPayload
    searchRoadwayGeometryQuery(routeId: String!, layerSlugs: [String!]!): RoutePayload
    notificationsQuery: NotificationsPayload
    cmsMessagesQuery: CmsMessagesPayload
    cmsLayersQuery: CmsLayersPayload
    restAreaQuery(restAreaId: ID!): RestAreaPayload
    fuelingStationQuery(fuelingStationId: ID!): FuelingStationPayload
    searchBoundsQuery(n: Float!, s: Float!, e: Float!, w: Float!, layerSlugs: [String!]!): SearchBoundsPayload
    brokenCameraQuery(originalURL: String!): BrokenCameraPayload
    modalQuery(entitySlug: String!, entityId: ID!, viewId: ID!): ModalPayload
    mobileCarrierQuery: MobileCarrierPayload
}

input MapFeaturesArgs {
    north: Float!
    south: Float!
    east: Float!
    west: Float!
    zoom: Int
    layerSlugs: [String!]!
    nonClusterableUris: [String]
}

interface MapFeature {
    bbox: [Float]
    title: String
    tooltip: String
    uri: String
    features: [GeoJsonFeature]
}

type Camera implements MapFeature {
    uri: String
    title: String
    bbox: [Float]
    active: Boolean
    icon: String
    color: String
    views(limit: Int): [CameraViewInterface]
    lastUpdated: Timestamp
    location: LinearLocation
    agencyAttribution: Agency
    nearbyWeatherStation: WeatherStation
}

type Event implements MapFeature {
    uri: String
    title: String
    description: String
    bbox: [Float]
    priority: Int
    icon: String
    color: String
    isWazeEvent: Boolean
    lastUpdated: Timestamp
    beginTime: Timestamp
    location: LinearLocation
    agencyAttribution: Agency
}

type Sign implements MapFeature {
    uri: String
    title: String
    tooltip: String
    bbox: [Float]
    signDisplayType: String
}

type Cluster implements MapFeature {
    uri: String
    title: String
    bbox: [Float]
    maxZoom: Int
}

type CameraView {
    uri: String
    url: String
    category: String
}

type Timestamp {
    timestamp: Float    # milliseconds since epoch
    timezone: String
}

type LinearLocation {
    primaryLinearReference: Float
    secondaryLinearReference: Float
}

type Agency {
    agencyName: String
    agencyURL: String
    agencyIconURL: String
}
```

---

## File Manifest

| File | Description |
|------|-------------|
| `massdot_client.py` | Production Python client (stdlib only) |
| `massdot_README.md` | This documentation |

---

## Legal Notice

This client accesses publicly available data from a Massachusetts state
government website.  All data is provided for informational purposes.
Use of this client is subject to MassDOT's terms of service.  Do not use
this client in a way that places excessive load on the public infrastructure.
