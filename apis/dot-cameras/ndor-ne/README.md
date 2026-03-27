# Nebraska 511 NDOT/NDOR Traffic Camera API — Reverse Engineering Notes

Reverse-engineered from `https://511.nebraska.gov` (app version **3.19.8**, March 2026).

---

## Overview

The Nebraska 511 Travel Information system is operated by the **Nebraska Department of Transportation (NDOT/NDOR)** and powered by **Castle Rock ITS** (CARSProgram platform). It provides real-time data on traffic cameras, variable message signs, incidents, weather conditions, road closures, plow locations, and more.

The site is a single-page React/Redux/Lit application. Data is fetched via two distinct APIs:

| API | Base URL | Protocol | Auth |
|-----|----------|----------|------|
| REST API | `https://netg.carsprogram.org` | HTTPS/JSON | None required |
| GraphQL API | `https://511.nebraska.gov/api/graphql` | HTTPS/JSON POST | None required |

Camera still images are CDN-served from `https://dot511.nebraska.gov/images/`.

---

## API Architecture

### REST API — `https://netg.carsprogram.org`

Provides flat list endpoints for all resources. No authentication headers required; the `Origin` and `Referer` headers from `511.nebraska.gov` appear to be permissive (tested without them and requests still succeed).

The server stack is Java (RESTEasy / JAX-RS), fronted by nginx and CloudFront (AWS). The TLS certificate is a wildcard `*.carsprogram.org` issued by Amazon RSA 2048.

Discovered via the main JS bundle (`main-9a7ff856b1c5837a0f6b.js`), specifically the configuration object:

```js
const h = "https://netg.carsprogram.org";
const g = {
  endpoints: {
    accounts:       `${h}/publicaccounts_v1/api`,
    amber:          `${h}/amber_v1/api`,
    cameras:        `${h}/cameras_v1/api`,
    cms:            `${h}/cms_v1/api`,
    cmsConfigs:     `${h}/cms_v1/api/cms/configurations`,
    cmsGQL:         `${h}/cms_v1/api/graphql`,
    delay:          `${h}/delay_v1/api`,
    events:         `${h}/events_v1/api`,
    floodgates:     `${h}/floodgates_v1/api`,
    feedback:       `${h}/eventfeedback_v1/api`,
    fuelingStations:`${h}/fueling-stations_v1/api`,
    oversizeLoads:  `${h}/oversize-load-check-in_v1/api`,
    locations:      `${h}/locations_v1/api`,
    avl:            `${h}/avl_v2/api`,
    plowCamera:     `${h}/avl_v2/api/images`,
    restAreas:      `${h}/rest-areas_v1/api`,
    rwis:           `${h}/rwis_v1/api`,
    mountainPasses: `${h}/mountainpasses_v1/api`,
    sign:           `${h}/signs_v1/api`,
    parking:        `${h}/parking_v1/api`,
    wildfire:       `${h}/calfire_v1/api`,
    travelTimes:    `${h}/traveltimes_v1/api/travel-times`,
    customLayers:   "https://public.carsprogram.org/ne/prod",
    mileMarkers:    "https://public.carsprogram.org/ne/prod",
    osrm:           "https://osrm-ne.carsprogram.org",
    nlp:            "https://nlp.carsprogram.org/api/v1/nlp"
  }
};
```

### GraphQL API — `https://511.nebraska.gov/api/graphql`

The GraphQL endpoint is proxied through the 511 web server itself. All GraphQL queries are standard HTTP POST requests with a JSON body.

Queries are compiled into the JS bundle as tagged template literals (`h.A\`query ...\``).

Key queries discovered from the bundle:

- `MapFeatures` — main map data loader; returns paginated/clustered features for a bounding box
- `Dashboard` — loads the sidebar panel (events, favorites, cameras)
- `Camera` — single camera detail with views
- `Event` — single event/incident detail
- `RestArea` — single rest area detail
- `Sign` — single VMS sign detail
- `Notifications` — site-wide alert banners
- `CmsMessages` / `CmsDashboards` / `CmsLayers` — CMS content
- `GetBrokenCameraQuery` — fetch working image URL for broken cameras

---

## Confirmed Working Endpoints

### `GET /cameras_v1/api/cameras`

Returns all 352 traffic cameras in Nebraska.

**Response shape:**
```json
[
  {
    "id": 5,
    "public": true,
    "name": "Holdrege-Elm Creek Exit",
    "lastUpdated": 1774583406199,
    "location": {
      "fips": 31,
      "latitude": 40.69003834281258,
      "longitude": -99.38477917806385,
      "routeId": "I-80",
      "linearReference": 257.29,
      "localRoad": false,
      "cityReference": "13 miles west of the Kearney area"
    },
    "cameraOwner": {"name": "NDOR"},
    "views": [
      {
        "name": "Various",
        "type": "STILL_IMAGE",
        "url": "https://dot511.nebraska.gov/images/vid-004080257-00.jpg"
      }
    ]
  }
]
```

**View types observed:**
- `STILL_IMAGE` — static JPEG served from `https://dot511.nebraska.gov/images/`
- `WMP` — Windows Media Player stream (rare; only 1 camera out of 352)

**Camera image URL format:**
```
https://dot511.nebraska.gov/images/vid-{district}{route_padded}{milepost}-{view_index}.jpg
```
Example: `vid-004080257-00.jpg`
- District: 3-digit number (e.g., `004`)
- Route: 2-digit highway number (e.g., `08` for I-80)
- Milepost: 3-digit mile marker (e.g., `257`)
- View index: 2-digit view number (`00`, `01`, `02`, ...)

### `GET /cameras_v1/api/cameras/{id}`

Single camera by integer ID. Same shape as one list element.

### `GET /signs_v1/api/signs`

Returns all 414 variable message signs (DMS/VMS).

**Response shape:**
```json
[
  {
    "status": "DISPLAYING_MESSAGE",
    "display": {
      "pages": [
        {
          "hasImage": false,
          "lines": ["HIGH", "WIND", "WARNING"],
          "justification": "CENTER"
        },
        {
          "hasImage": false,
          "lines": ["SLOWER", "SPEEDS", "ADVISED"],
          "justification": "CENTER"
        }
      ]
    },
    "lastUpdated": 1774291280000,
    "idForDisplay": "D6-99760",
    "agencyId": "nebraskasigns",
    "agencyName": "NE Signs",
    "name": "NE-2 NB",
    "location": {
      "fips": 31,
      "latitude": 41.40323,
      "longitude": -99.62551,
      "routeId": "NE 2",
      "linearReference": 279.21330039696784,
      "cityReference": "in Broken Bow",
      "locationDescription": "NE 2 N at MP 279.2 (Broken Bow)",
      "signFacingDirection": "N",
      "perpendicularRadiansForDirectionOfTravel": -1.5705854448556489
    },
    "properties": {
      "maxSignPhases": 3,
      "phaseDwellTime": 2500,
      "phaseBlankTime": 0,
      "maxLinesPerPage": 3,
      "maxCharactersPerLine": 16,
      "sizeKnown": false
    },
    "id": "nebraskasigns*D6-99760"
  }
]
```

**Sign status values:** `"DISPLAYING_MESSAGE"`, `"BLANK"`

### `GET /cms_v1/api/cms/configurations`

Site configuration JSON (feature flags, enabled layers, CMS settings).

---

## GraphQL Queries

### MapFeatures — Map Layer Data

The primary map data query. Returns features visible within a bounding box at a given zoom level. At low zoom levels, features are clustered.

**Stable query (no inline fragments):**
```graphql
query MapFeatures($input: MapFeaturesArgs!) {
    mapFeaturesQuery(input: $input) {
        mapFeatures {
            bbox
            title
            uri
            __typename
        }
        error {
            message
            type
        }
    }
}
```

**Variables:**
```json
{
  "input": {
    "north": 41.0,
    "south": 40.7,
    "east": -96.5,
    "west": -97.0,
    "zoom": 10,
    "layerSlugs": ["normalCameras"]
  }
}
```

**Note on inline fragments:** The server returns HTTP 400 for certain combinations of inline fragments (e.g., `... on Camera { active views { url } }`). The base query without inline fragments is always stable.

**`__typename` values returned:** `Camera`, `Sign`, `Event`, `Plow`, `RestArea`, `Cluster`, `WeatherStation`

**`uri` format:** `camera/5`, `event/12345`, `sign/nebraskasigns*D5-80-14+EB+VSA`, etc.

### Camera Detail

```graphql
query {
    cameraQuery(cameraId: "5") {
        camera {
            uri
            title
            active
            bbox
            icon
            lastUpdated { timestamp timezone }
            views(limit: 10) {
                uri
                category
            }
        }
        error { type }
    }
}
```

**Note:** The `cameraId` must be the numeric part only (e.g., `"5"` not `"camera/5"`).

### Event Detail

```graphql
query Event($eventId: ID!, $layerSlugs: [String!]!) {
    eventQuery(eventId: $eventId, layerSlugs: $layerSlugs) {
        event {
            uri
            title
            description
            bbox
            lastUpdated { timestamp timezone }
            beginTime { timestamp timezone }
            priority
            active
            verified
            isWazeEvent
        }
        error { type }
    }
}
```

### Rest Area Detail

```graphql
query RestArea($restAreaId: ID!) {
    restAreaQuery(restAreaId: $restAreaId) {
        restArea {
            uri
            title
            status
            statusMessage
            restAreaAmenities { icon label }
        }
        error { type }
    }
}
```

---

## Layer Slugs Reference

Used as `layerSlugs` values in the `MapFeatures` GraphQL query:

| Constant | Slug Value | Description |
|----------|-----------|-------------|
| `NORMAL_CAMERA` | `normalCameras` | Standard traffic cameras |
| `HOT_CAMERA` | `hotCameras` | Severe weather cameras |
| `PLOW_CAMERA` | `plowCameras` | Snowplow cameras |
| `PLOW_LOCATION` | `plowLocations` | Plow truck GPS positions |
| `TRAFFIC_SPEED` | `trafficSpeeds` | Real-time speed segments |
| `RWIS_NORMAL` | `stationsNormal` | Road Weather Info System stations |
| `RWIS_ALERT` | `stationsAlert` | RWIS stations with alerts |
| `REST_AREAS` | `restAreas` | Rest areas |
| `SIGNS_ACTIVE` | `electronicSigns` | VMS/DMS signs (active) |
| `SIGNS_INACTIVE` | `electronicSignsInactive` | Signs (inactive) |
| `CONSTRUCTION` | `constructionReports` | Road construction |
| `ROAD_REPORTS` | `roadReports` | Road condition reports |
| `CLOSURES` | `roadClosures` | Road closures |
| `WINTER_DRIVING` | `winterDriving` | Winter driving alerts |
| `FLOOD_REPORTS` | `floodReports` | Flood events |
| `WAZE_REPORTS` | `wazeReports` | Citizen Waze reports |
| `WEATHER_WARNINGS` | `weatherWarningsAreaEvents` | NWS weather warnings |
| `METRO_TRAFFIC` | `metroTrafficMap` | Metro area critical disruptions |
| `TRUCKERS_REPORTS` | `truckersReports` | Truck-specific restrictions |
| `FUELING_STATIONS` | `fuelingStations` | Fueling stations |
| `OVERSIZE_LOADS` | `oversizeLoads` | Oversize/overweight load info |
| `BRIDGE_HEIGHTS` | `bridgeHeights` | Bridge height restrictions |
| `POSTED_BRIDGES` | `postedBridges` | Posted bridge weight limits |
| `MILE_MARKERS` | `mileMarkers` | Mile marker layer |
| `WEATHER_RADAR` | `weatherRadar` | Weather radar overlay |

---

## Nebraska State Coverage

**Total resources (as of March 2026):**
- 352 traffic cameras (all owned by NDOR)
- 414 variable message signs
- All cameras are `STILL_IMAGE` type except 1 (`WMP` video stream)

**Geographic bounds:**
```
North: 43.00°N
South: 40.00°N
East:  -95.31°W
West: -104.06°W
```

**Routes with camera coverage (top 10):**
- I-80: 124 cameras
- US 6: 14
- US 20: 14
- US 75: 14
- US 77: 14
- US 30: 12
- NE 50: 11
- US 81: 10
- US 34: 10
- US 83: 10

All 50 routes covered: I-80, I-129, I-180, I-480, I-680, I-76, NE 2, NE 4, NE 7, NE 11, NE 12, NE 14, NE 15, NE 16, NE 21, NE 23, NE 25, NE 27, NE 29, NE 35, NE 40, NE 45, NE 47, NE 50, NE 56, NE 61, NE 70, NE 71, NE 87, NE 88, NE 89, NE 91, NE 92, NE 97, NE 250, NE 370, US 6, US 20, US 26, US 30, US 34, US 75, US 77, US 81, US 83, US 136, US 183, US 275, US 281, US 385.

---

## Client Usage

The client (`ndor_client.py`) requires only Python 3.9+ stdlib (no third-party packages).

```python
from ndor_client import NDORClient

client = NDORClient(timeout=30)

# Get all cameras
cameras = client.get_cameras()
print(f"{len(cameras)} cameras")

# Filter by route
i80_cameras = client.get_cameras_by_route("I-80")
for cam in i80_cameras[:5]:
    print(cam.name, cam.location.city_reference)
    for view in cam.views:
        print(f"  Image: {view.url}")

# Get single camera
cam = client.get_camera(5)
print(cam.name, cam.image_urls)

# Download camera image
img_bytes = client.download_image(cam.image_urls[0])
with open("cam5.jpg", "wb") as f:
    f.write(img_bytes)

# Get cameras in a bounding box (Omaha area)
omaha_cams = client.get_cameras_by_bounds(
    north=41.4, south=41.1, east=-95.8, west=-96.2
)

# Get variable message signs
signs = client.get_signs()
active_signs = client.get_active_signs()
for s in active_signs[:5]:
    print(f"{s.id_for_display}: {s.current_message}")

# GraphQL: map features for an area
features = client.get_map_features(
    north=41.5, south=40.8, east=-96.0, west=-97.5,
    layer_slugs=["normalCameras", "constructionReports"]
)
for f in features:
    print(f.typename, f.uri, f.title)

# Statewide cameras via GraphQL
all_gql = client.get_statewide_cameras_gql()
print(f"{len(all_gql)} camera features statewide")

# Summary statistics
summary = client.camera_summary()
print(summary)
```

---

## Rate Limiting & Polling

From the JS bundle configuration:

```js
clientPollTime:      60000,   // 60-second data refresh interval
timeoutMs:           9000,    // 9-second request timeout
timeoutPostMs:       15000,   // 15-second POST timeout
routeSearchRPM:      20,      // Route search rate limit
shortCacheTTLSeconds: 3,      // Short-lived cache TTL
```

The app refreshes map data every 60 seconds. There is no explicit rate limit documented in the API responses, but being a reasonable client and refreshing no more frequently than every 60 seconds is appropriate.

---

## Authentication

No authentication is required for any public endpoint. The site has a `Your 511` account system for personalized features (favorite routes, SMS alerts), but all traffic camera data, sign data, and map features are publicly accessible without login.

The app uses Google reCAPTCHA v3 (`6Lcd8QsqAAAAAAPfNzLuU-jLolwYVeYYHvJLtz-d`) only for feedback form submissions.

---

## Technical Stack (Discovered from JS Bundle)

- **Frontend:** Web Components (Lit) + Redux, single-page app
- **Map:** Google Maps API (client: `gme-castlerockassociates`, channel: `NE`)
- **Backend provider:** Castle Rock ITS / CARSProgram
- **CDN:** AWS CloudFront
- **App server:** nginx + Java (RESTEasy/JAX-RS)
- **GraphQL server:** Proxied through 511.nebraska.gov
- **App version:** 3.19.8
- **Analytics:** Google Tag Manager (`G-306Q35M2N8`)
- **Routing library:** OSRM (`https://osrm-ne.carsprogram.org`)
- **Weather radar:** `https://gwc.carsprogram.org/service/wms`
- **Other 511 states using same platform:** Iowa, and likely others under carsprogram.org

---

## Files

| File | Description |
|------|-------------|
| `ndor_client.py` | Complete Python client (stdlib only) |
| `ndor_README.md` | This file |
