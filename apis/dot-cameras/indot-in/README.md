# INDOT TrafficWise API Client

A production-quality Python client for the **Indiana Department of Transportation (INDOT) TrafficWise** traffic monitoring system at [511in.org](https://511in.org).

No API key or authentication required.  Pure Python stdlib only — no third-party packages needed.

---

## Table of Contents

1. [Overview](#overview)
2. [Reverse-Engineering Methodology](#reverse-engineering-methodology)
3. [Architecture](#architecture)
4. [Discovered API Endpoints](#discovered-api-endpoints)
5. [GraphQL Schema (selected)](#graphql-schema-selected)
6. [Layer Slugs Reference](#layer-slugs-reference)
7. [CDN Patterns](#cdn-patterns)
8. [Quick Start](#quick-start)
9. [API Reference](#api-reference)
10. [Data Models](#data-models)
11. [CLI Demo](#cli-demo)
12. [Rate Limits and Etiquette](#rate-limits-and-etiquette)
13. [Findings Summary](#findings-summary)

---

## Overview

INDOT TrafficWise (511in.org) is Indiana's official statewide traffic information system. It exposes a **GraphQL API** (no authentication required) that serves:

| Feature | Description |
|---|---|
| Traffic Cameras | ~800+ cameras statewide, live JPEG snapshots |
| Incidents | Crashes, hazards, stalls in real-time |
| Construction | Active and planned roadwork |
| Road Closures | Full and partial road closures |
| Snowplow Tracking | AVL GPS positions for INDOT plow fleet |
| Electronic Signs | DMS / variable message sign content |
| RWIS Stations | Road weather sensors (temperature, precipitation, pavement) |
| Rest Areas | Status (open/closed), amenities |
| Travel Times | Delay and travel-time data |
| Weather Radar | Precipitation radar WMS tiles |

The system is built on the **CARS (Connected Automated Real-time Systems) platform** shared across many US state 511 systems.

---

## Reverse-Engineering Methodology

### 1. Entry Point Discovery

- `trafficwise.org` → server placeholder (no application deployed at this hostname)
- `indot.carsprogram.org` → HTTP 301 redirect to `https://511in.org/`
- Active application is at **`https://511in.org/`**

### 2. Asset Discovery via Service Worker

`https://511in.org/service-worker.js` (Workbox 6.5.4) lists all pre-cached assets, revealing the bundle filenames:

```
/main-418aeba00b01fadd90de.js    (~543 KB)
/shared-c0d2565c5e126b86560b.js  (~630 KB)
/1311-52de52a6f2c70ee4ae90.js    (component chunks)
...98 total assets
```

### 3. Configuration Extraction from Shared Bundle

The `shared-*.js` bundle contains the full runtime configuration object (minified):

```javascript
m = "https://intg.carsprogram.org"
g = {
  graphqlUrl: "/api/graphql",
  endpoints: {
    cameras:    `${m}/cameras_v1/api`,
    events:     `${m}/events_v1/api`,
    avl:        `${m}/avl_v2/api`,
    plowCamera: `${m}/avl_v2/api/images`,
    signs:      `${m}/signs_v1/api`,
    rwis:       `${m}/rwis_v1/api`,
    ...
  }
}
```

### 4. GraphQL Query Extraction from Main Bundle

The `main-*.js` bundle contains **53 GraphQL operation strings** (queries, mutations, fragments) embedded as tagged template literals (`` gql`...` ``).  Key operations extracted include `MapFeatures`, `Camera`, `Event`, `Plow`, `Sign`, `Rwis`, `Dashboard`, `SearchBounds`, and all account/auth mutations.

### 5. Live API Testing

All public (unauthenticated) queries were tested against the live production GraphQL endpoint at `https://511in.org/api/graphql`, confirming:
- No authentication headers required for read queries
- `Origin: https://511in.org` header recommended (CORS enforcement)
- Rate limiting not observed during testing

---

## Architecture

```
Browser / This Client
        │
        │  POST https://511in.org/api/graphql
        ▼
┌───────────────────┐
│  511in.org nginx  │   GraphQL proxy / BFF
│  /api/graphql     │
└────────┬──────────┘
         │  Fan-out per layer slug
         ▼
┌──────────────────────────────────────────────┐
│  https://intg.carsprogram.org  (CARS platform)│
│                                               │
│  cameras_v1/api     — camera metadata         │
│  events_v1/api      — incidents/construction  │
│  avl_v2/api         — plow AVL tracking       │
│  signs_v1/api       — DMS signs               │
│  rwis_v1/api        — road weather            │
│  rest-areas_v1/api  — rest areas              │
│  traveltimes_v1/api — travel times            │
│  locations_v1/api   — geocoding               │
└──────────────────────────────────────────────┘

Camera images:  https://public.carsprogram.org/cameras/IN/
Weather radar:  https://gwc.carsprogram.org/service/wms
NLP search:     https://nlp.carsprogram.org/api/v1/nlp
Custom layers:  https://public.carsprogram.org/in/prod
```

The application is a **React/Redux SPA** using **Web Components** for UI elements and **Workbox** for offline support.  It uses **Redux Pub/Sub pattern** with separate TRAY and MAP subscriptions for real-time polling (default interval: 60 seconds).

---

## Discovered API Endpoints

### Primary GraphQL Endpoint

| Field | Value |
|---|---|
| URL | `https://511in.org/api/graphql` |
| Method | `POST` |
| Auth | None required |
| Content-Type | `application/json` |
| CORS Origin | `https://511in.org` |

### Backend Microservices (via CARS platform)

These are called by the GraphQL proxy; you generally do not need to call them directly.

| Service | Base URL | Purpose |
|---|---|---|
| Cameras | `https://intg.carsprogram.org/cameras_v1/api` | Camera metadata |
| Events | `https://intg.carsprogram.org/events_v1/api` | Incidents, construction |
| AVL / Plows | `https://intg.carsprogram.org/avl_v2/api` | Snowplow GPS tracking |
| Plow Images | `https://intg.carsprogram.org/avl_v2/api/images` | Plow camera images |
| Signs | `https://intg.carsprogram.org/signs_v1/api` | Electronic signs |
| RWIS | `https://intg.carsprogram.org/rwis_v1/api` | Road weather |
| Rest Areas | `https://intg.carsprogram.org/rest-areas_v1/api` | Rest area status |
| Travel Times | `https://intg.carsprogram.org/traveltimes_v1/api/travel-times` | Delay data |
| Locations | `https://intg.carsprogram.org/locations_v1/api` | Geocoding |
| Accounts | `https://intg.carsprogram.org/publicaccounts_v1/api` | User accounts (auth required) |
| Event Feedback | `https://intg.carsprogram.org/eventfeedback_v1/api` | Report broken cameras |
| CMS | `https://intg.carsprogram.org/cms_v1/api` | Content management |
| NLP Search | `https://nlp.carsprogram.org/api/v1/nlp` | Natural language route search |

### CDN Endpoints

| CDN | URL Pattern | Content |
|---|---|---|
| Camera images | `https://public.carsprogram.org/cameras/IN/{name}.flv.png` | Live JPEG snapshots |
| Custom layers | `https://public.carsprogram.org/in/prod` | GeoJSON overlay layers |
| Weather radar WMS | `https://gwc.carsprogram.org/service/wms` | Precipitation tiles |

### Other

| URL | Purpose |
|---|---|
| `https://511in.org/service-worker.js` | Asset manifest (Workbox) |
| `https://511in.org/manifest.json` | PWA manifest |
| `https://511in.org/sitemap.xml` | Sitemap |

---

## GraphQL Schema (selected)

### `mapFeaturesQuery` — primary map data endpoint

**Request:**
```graphql
query MapFeatures($input: MapFeaturesArgs!, $plowType: String) {
  mapFeaturesQuery(input: $input) {
    mapFeatures {
      bbox          # [west, south, east, north]
      title
      tooltip
      uri           # e.g. "camera/18493", "event/CARSx-404897", "avl/64189"
      __typename    # Camera | Event | Plow | Sign | Station | Cluster
      features {    # GeoJSON features for map rendering
        id
        geometry
        properties
        type
      }
      ... on Camera {
        active
        views(limit: 5) {
          uri
          category       # "VIDEO" | "STILL_IMAGE"
          ... on CameraView {
            url          # JPEG snapshot URL
            sources {
              type       # MIME type e.g. "application/x-mpegURL"
              src        # HLS/FLV stream URL
            }
          }
        }
      }
      ... on Event {
        priority         # 1=critical, 3=urgent, 5=routine
      }
      ... on Plow {
        views(limit: 3, plowType: $plowType) {
          uri
          category
          ... on PlowCameraView { url }
        }
      }
      ... on Sign {
        signDisplayType  # "OVERLAY_TRAVEL_TIME" | "TEXT_ONLY" | etc.
      }
      ... on Cluster {
        maxZoom          # Zoom level at which cluster expands
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
    "north": 39.95,
    "south": 39.65,
    "east": -86.00,
    "west": -86.30,
    "zoom": 12,
    "layerSlugs": ["normalCameras"]
  },
  "plowType": "plowCameras"
}
```

**Notes:**
- The app issues one request per layer slug.  Batching all slugs in a single request may cause a server error.
- At zoom < 9, the API returns `Cluster` objects instead of individual features.
- Use zoom >= 12 for individual cameras in a city-sized bounding box.

---

### `allPredefinedAreasQuery` / `allPredefinedRoutesQuery`

```graphql
query {
  allPredefinedAreasQuery {
    name         # e.g. "Indianapolis"
    sortOrder
    popular
    bbox         # [west, south, east, north]
  }
  allPredefinedRoutesQuery {
    name         # e.g. "I-65"
    sortOrder
    popular
    bbox
  }
}
```

No variables required.  Returns reference data for the search UI.

---

### Camera detail query

```graphql
query Camera(
  $cameraId: ID!
  $layerSlugs: [String!]!
  $nearbyViewLimit: Int!
  $showCameraLastUpdated: Boolean!
  $isCamerasEnabled: Boolean!
  $showCommercialQuantities: Boolean!
) {
  cameraQuery(cameraId: $cameraId) {
    camera {
      uri title bbox icon color
      lastUpdated @include(if: $showCameraLastUpdated) {
        timestamp timezone
      }
      location { primaryLinearReference secondaryLinearReference }
      views(orderBy: LINEAR_REF_ASC) {
        uri title category
        ... on CameraView {
          url
          sources { type src original }
        }
      }
      nearbyResults(layerSlugs: $layerSlugs) {
        uri title bbox icon color __typename
      }
    }
    error { type }
  }
}
```

Variables: `cameraId` (numeric string), `layerSlugs`, `nearbyViewLimit` (int), `showCameraLastUpdated` (bool), `isCamerasEnabled` (bool), `showCommercialQuantities` (bool).

---

### Plow detail query

```graphql
query Plow(
  $plowId: ID!
  $layerSlugs: [String!]!
  $nearbyViewLimit: Int!
  $showCameraLastUpdated: Boolean!
  $isCamerasEnabled: Boolean!
  $showTotalPlows: Boolean!
  $showCommercialQuantities: Boolean!
) {
  plowQuery(plowId: $plowId) {
    plow {
      uri bbox title tooltip icon color plowType
      activeMaterialPhrase   # e.g. "Applying Salt"
      totalPlows @include(if: $showTotalPlows)
      heading                # bearing in degrees
      locationDescription    # human-readable road name
      lastUpdated { timestamp timezone }
      location { primaryLinearReference }
      markers { title geometry uri properties }
      features { id geometry properties }
    }
    error { type }
  }
}
```

---

### Event detail query

```graphql
query Event(
  $layerSlugs: [String!]!
  $eventId: ID!
  $nearbyViewLimit: Int!
  $isCamerasEnabled: Boolean!
  $showCameraLastUpdated: Boolean!
  $showCommercialQuantities: Boolean!
) {
  eventQuery(eventId: $eventId, layerSlugs: $layerSlugs) {
    event {
      uri title description bbox
      location { primaryLinearReference secondaryLinearReference }
      icon color priority
      lastUpdated { timestamp timezone }
      beginTime { timestamp timezone }
      isWazeEvent
      agencyAttribution { agencyName agencyURL agencyIconURL }
      feedbackOptions { responseId responseLabel }
    }
    error { type }
  }
}
```

---

## Layer Slugs Reference

Use these string values in the `layerSlugs` array in the `MapFeaturesArgs` input.

| Constant | Slug Value | Description |
|---|---|---|
| `LAYER_CAMERAS` | `normalCameras` | Regular roadside cameras |
| `LAYER_HOT_CAMERAS` | `hotCameras` | Featured / high-priority cameras |
| `LAYER_PLOW_CAMERAS` | `plowCameras` | Cameras on snowplow trucks |
| `LAYER_PLOW_LOCATIONS` | `plowLocations` | Snowplow GPS positions |
| `LAYER_INCIDENTS` | `incidents` | Crashes, stalls, road hazards |
| `LAYER_CONSTRUCTION` | `construction` | Active construction zones |
| `LAYER_ROADWORK` | `roadwork` | Scheduled roadwork |
| `LAYER_CLOSURES` | `closures` | Full road closures |
| `LAYER_SIGNS_ACTIVE` | `electronicSigns` | DMS signs with messages |
| `LAYER_SIGNS_INACTIVE` | `electronicSignsInactive` | Signs not currently displaying |
| `LAYER_RWIS_NORMAL` | `stationsNormal` | Weather stations (OK status) |
| `LAYER_RWIS_ALERT` | `stationsAlert` | Weather stations (alert) |
| `LAYER_TRAFFIC_SPEEDS` | `trafficSpeeds` | Traffic flow/speed data |
| `LAYER_REST_AREAS` | `restAreas` | Rest area locations and status |
| `LAYER_WEATHER_RADAR` | `weatherRadar` | Precipitation radar overlay |
| `LAYER_WINTER_DRIVING` | `winterDriving` | Winter road conditions |
| `LAYER_FLOODING` | `flooding` | Flooding events |

Additional slugs identified in the bundle (may not be active in Indiana):
- `sweeperLocations` — street sweeper tracking
- `potholeTruckLocations` — pothole truck tracking
- `mountainPasses` — not applicable in Indiana
- `parking`, `onStreetParking`, `offStreetParking`, `evParking`
- `fuelingStations` — EV charging stations
- `oversizeLoads` — oversize/overweight load routes
- `mileMarkers` — reference mile markers
- `regionalRoadConditions`
- `wildfires` — not applicable in Indiana
- `rampMeters` — ramp metering status

---

## CDN Patterns

### Traffic Camera Images

Live JPEG snapshots are served from:
```
https://public.carsprogram.org/cameras/IN/{filename}.flv.png
```

Examples from live data:
```
https://public.carsprogram.org/cameras/IN/INDOT_187_PiszCsSTcmesnVDn.flv.png
https://public.carsprogram.org/cameras/IN/INDOT_188_jt3Y85WlDSsiCoqN.flv.png
https://public.carsprogram.org/cameras/IN/INDOT_99_fOrZSEUZjxmUwvOD.flv.png
```

Pattern: `INDOT_{route_number}_{random_token}.flv.png`

The filenames contain a per-camera random token that changes when cameras are re-registered.  Always obtain URLs through the GraphQL API rather than constructing them from a camera ID.

Response characteristics:
- Content-Type: `image/png` (despite the `.flv.png` extension — it's a PNG snapshot)
- Typically ~100–200 KB per image
- `Last-Modified` and `ETag` headers present for cache validation
- Images refresh approximately every 30–60 seconds

### Inactive Camera Placeholder

Cameras that are offline return:
```
/images/icon-camera-closed-fill-solid-padded.svg
```
(a relative URL served from `https://511in.org/`)

### Weather Radar WMS

```
https://gwc.carsprogram.org/service/wms
  ?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap
  &FORMAT=image/png&TRANSPARENT=true
  &LAYERS=RadarMosaic
  &...standard WMS tile parameters...
```

---

## Quick Start

### Prerequisites

- Python 3.8 or later
- No third-party packages required (stdlib only: `urllib`, `json`, `dataclasses`)

### Installation

```bash
# Just copy the single file — no install needed
cp indot_client.py /your/project/
```

### Basic Usage

```python
from indot_client import INDOTClient

client = INDOTClient()

# Get all active incidents statewide
incidents = client.get_incidents()
for inc in incidents:
    print(f"[P{inc.priority}] {inc.title}")
    if inc.coordinates:
        lon, lat = inc.coordinates
        print(f"  Location: {lon:.4f}, {lat:.4f}")
```

### Camera Images

```python
from indot_client import INDOTClient

client = INDOTClient()

# Get cameras near Indianapolis
cameras = client.get_cameras_in_bounds(
    south=39.65, north=39.95,
    west=-86.30, east=-86.00,
    zoom=12
)

print(f"Found {len(cameras)} cameras")
for cam in cameras[:3]:
    print(f"\n{cam.title}")
    print(f"  Image URL: {cam.image_url}")

    # Download the snapshot
    img_bytes = client.download_camera_image(cam)
    if img_bytes:
        filename = f"cam_{cam.camera_id}.png"
        with open(filename, "wb") as f:
            f.write(img_bytes)
        print(f"  Saved: {filename} ({len(img_bytes):,} bytes)")
```

### Cameras for a Named Area

```python
cameras = client.get_cameras_for_area("Indianapolis")
print(f"{len(cameras)} cameras in Indianapolis")
```

### Cameras Along a Route

```python
cameras = client.get_cameras_for_route("I-65", zoom=12)
real_cameras = [c for c in cameras if hasattr(c, 'image_url')]
print(f"{len(real_cameras)} cameras along I-65")
```

### Snowplow Tracking

```python
plows = client.get_plows()
for plow in plows:
    lon, lat = plow.coordinates
    print(f"{plow.title}")
    print(f"  Position: ({lon:.4f}, {lat:.4f})")
    print(f"  Material: {plow.active_material_phrase or 'none'}")
    if plow.views:
        print(f"  Camera: {plow.views[0].url}")
```

### Electronic Signs

```python
signs = client.get_signs(
    south=39.59878, north=40.02495,
    west=-86.47613, east=-85.83893
)
for sign in signs:
    print(f"{sign.title} ({sign.sign_display_type})")
```

### RWIS Weather Stations

```python
stations = client.get_weather_stations()
print(f"{len(stations)} weather stations statewide")

# Only alert-state stations
alert_stations = client.get_weather_stations(alerts_only=True)
print(f"{len(alert_stations)} stations in alert state")
```

### Raw GraphQL Query

For advanced use cases, use the `_post_graphql` method directly:

```python
from indot_client import INDOTClient

client = INDOTClient()

data = client._post_graphql("""
    query {
        allPredefinedRoutesQuery {
            name
            bbox
            popular
        }
    }
""")
routes = data["allPredefinedRoutesQuery"]
for r in routes:
    print(r["name"])
```

---

## API Reference

### `INDOTClient`

```
INDOTClient(graphql_url=GRAPHQL_URL, timeout=30, user_agent=DEFAULT_USER_AGENT)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `graphql_url` | str | `"https://511in.org/api/graphql"` | GraphQL endpoint URL |
| `timeout` | int | `30` | HTTP request timeout in seconds |
| `user_agent` | str | Browser UA | User-Agent header value |

---

### Methods

#### `get_map_features(south, north, west, east, layer_slugs, zoom=10, plow_type=…)`

Generic method.  Returns a mixed list of Camera, TrafficEvent, Plow, Sign, WeatherStation, and Cluster objects.

| Parameter | Type | Description |
|---|---|---|
| `south`, `north`, `west`, `east` | float | Bounding box in decimal degrees |
| `layer_slugs` | list[str] | Layer slug strings (see Layer Slugs Reference) |
| `zoom` | int | Map zoom level (0–22) |
| `plow_type` | str | Plow view type for plow queries |

**Returns:** `list[Any]`

---

#### `get_cameras_in_bounds(south, north, west, east, zoom=12, include_hot=True)`

Returns Camera objects within the bounding box.  Skips Cluster objects.

**Returns:** `list[Camera]`

---

#### `get_cameras_statewide(zoom=9)`

Returns cameras (or clusters) for all of Indiana.

**Returns:** `list[Camera | Cluster]`

---

#### `get_cameras_for_area(area_name, zoom=12)`

Fetch cameras within a named area.  Valid names: "Indianapolis", "Gary", "Fort Wayne", "Evansville", "South Bend", "New Albany".

**Returns:** `list[Camera]`

---

#### `get_cameras_for_route(route_name, zoom=9)`

Fetch cameras along a named route (e.g. "I-65", "I-70", "US-31").

**Returns:** `list[Camera | Cluster]`

---

#### `get_incidents(south, north, west, east, zoom=7, include_construction=True, include_closures=True)`

Returns active incidents (and optionally construction and closures).  All bounding box parameters are optional; defaults to statewide Indiana bounds.

**Returns:** `list[TrafficEvent]`

---

#### `get_construction(south, north, west, east, zoom=7)`

Returns active construction events.  All bounding box parameters optional.

**Returns:** `list[TrafficEvent]`

---

#### `get_plows(south, north, west, east, zoom=7, include_cameras=True)`

Returns active snowplow positions.  All bounding box parameters optional.

**Returns:** `list[Plow]`

---

#### `get_signs(south, north, west, east, zoom=10)`

Returns electronic sign objects.  All bounding box parameters optional.

**Returns:** `list[Sign]`

---

#### `get_weather_stations(south, north, west, east, zoom=7, alerts_only=False)`

Returns RWIS weather station objects.

**Returns:** `list[WeatherStation]`

---

#### `get_predefined_areas()`

Returns named geographic areas for quick navigation.

**Returns:** `list[PredefinedArea]`

---

#### `get_predefined_routes()`

Returns named highway routes.

**Returns:** `list[PredefinedRoute]`

---

#### `download_camera_image(camera)`

Downloads the current snapshot image for a camera.

**Returns:** `bytes | None`

---

## Data Models

### `BBox`

```
BBox(west, south, east, north)
```
Geographic bounding box.  `.center` → `(lon, lat)` tuple.

### `Camera`

| Field | Type | Description |
|---|---|---|
| `uri` | str | `"camera/{id}"` |
| `title` | str | Location description |
| `bbox` | BBox | Geographic bounds |
| `active` | bool | Whether camera feed is live |
| `views` | list[CameraView] | Available image/stream views |
| `camera_id` | str | Numeric ID extracted from URI |
| `image_url` | str or None | First live snapshot URL |
| `coordinates` | tuple | (longitude, latitude) |

### `CameraView`

| Field | Type | Description |
|---|---|---|
| `uri` | str | `"camera/{camera_id}/{view_id}"` |
| `category` | str | `"VIDEO"` or `"STILL_IMAGE"` |
| `url` | str | JPEG snapshot URL |
| `sources` | list[dict] | HLS/FLV stream sources |
| `is_live` | bool | True if URL is a CDN image |
| `hls_url` | str or None | HLS stream URL if available |

### `TrafficEvent`

| Field | Type | Description |
|---|---|---|
| `uri` | str | `"event/{id}"` |
| `title` | str | Human-readable description |
| `priority` | int or None | 1=critical, 3=urgent, 5=routine |
| `bbox` | BBox | Location bounds |
| `features` | list[GeoFeature] | GeoJSON point/line geometry |
| `coordinates` | tuple or None | Point coordinates if available |
| `is_critical` | bool | True if priority <= 1 |

### `Plow`

| Field | Type | Description |
|---|---|---|
| `uri` | str | `"avl/{id}"` |
| `title` | str | Route and truck number |
| `plow_id` | str | Numeric AVL ID |
| `active_material_phrase` | str or None | e.g. "Applying Salt" |
| `heading` | float or None | Compass bearing (0=N, 90=E) |
| `location_description` | str or None | Road name |
| `views` | list[CameraView] | Plow camera views |
| `coordinates` | tuple | (longitude, latitude) |

### `Sign`

| Field | Type | Description |
|---|---|---|
| `uri` | str | `"electronic-sign/{id}"` |
| `title` | str | Location |
| `sign_display_type` | str or None | `"OVERLAY_TRAVEL_TIME"`, `"TEXT_ONLY"`, etc. |
| `coordinates` | tuple | (longitude, latitude) |

### `WeatherStation`

| Field | Type | Description |
|---|---|---|
| `uri` | str | `"weather-station/{id}"` |
| `title` | str | Route and milepost location |
| `station_id` | str | Numeric ID |
| `coordinates` | tuple | (longitude, latitude) |

---

## CLI Demo

Run the included demo directly:

```bash
python indot_client.py
```

Expected output (truncated):

```
============================================================
  Predefined Areas
============================================================
  Indianapolis         center=(-86.1575, 39.8119)
  Gary                 center=(-87.3544, 41.5984)
  Fort Wayne           center=(-85.1351, 41.0789)
  ...

============================================================
  Active Incidents (statewide)
============================================================
  [P?] I-70 eastbound (Mile Point 107): Rest area closed.
         event/incars-178274  coords=(-85.7080, 39.8253)
  [P3] I-465 northbound (Mile Point 20.8): Crash.
         event/CARSx-404897  coords=(-86.2687, 39.8760)
  ...

============================================================
  Traffic Cameras — Indianapolis Area (zoom=9)
============================================================
  Retrieved 31 individual cameras and 15 clusters

  Camera: I-70: 1-070-087-5-1 ARLINGTON AVE
    URI:    camera/18493  active=True
    Coords: (-86.06537, 39.80573)
    Image:  https://public.carsprogram.org/cameras/IN/INDOT_187_PiszCsSTcmesnVDn.flv.png

  ...
```

---

## Rate Limits and Etiquette

- No official rate limit is documented or observed during testing.
- The application's client-side polling interval is **60 seconds** (configurable in the bundle as `clientPollTime: 6e4`).
- Respect this interval if polling for live data.
- The server enforces a per-request timeout of **30 seconds** (`timeoutMs: 3e4`).
- Issue one layer slug per request (as the application does) to avoid server-side fan-out errors.
- Do not use this client to scrape or archive the full camera image library in bulk.

---

## Findings Summary

| Finding | Detail |
|---|---|
| Primary endpoint | `https://511in.org/api/graphql` (GraphQL POST) |
| Auth required | No (read-only operations) |
| Session cookies | Not required |
| API key | None |
| Camera CDN | `https://public.carsprogram.org/cameras/IN/` |
| Camera format | PNG snapshot (~100–200 KB), refreshed ~30–60s |
| Plow tracking | ~7–50 vehicles active depending on season |
| Total cameras (statewide) | ~800+ (confirmed via cluster data) |
| Total signs (statewide) | ~76+ (Indianapolis area alone) |
| Total RWIS stations | ~61 statewide |
| Backend platform | CARS (Connected Automated Real-time Systems) |
| Backend host | `https://intg.carsprogram.org` |
| Weather radar WMS | `https://gwc.carsprogram.org/service/wms` |
| Analytics tag | `G-X5Y1BTJN0E` (Google Analytics) |
| reCAPTCHA site key | `6Lcsu9wbAAAAAFTxe14uat2ne7q8Y1Ll7KjZIZ0D` (v3, write operations only) |
| iOS app | App Store ID `1581840840`, bundle `crc.carsapp.in` |
| NLP search | `https://nlp.carsprogram.org/api/v1/nlp` (natural language query) |

---

*Reverse-engineered from `https://511in.org` JS bundles and live API testing.  Information current as of March 2026.*
