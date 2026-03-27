# CDOT Traffic Data Client

A production-quality Python client for the **Colorado Department of Transportation (CDOT)** public traffic information APIs, reverse-engineered from [maps.cotrip.org](https://maps.cotrip.org).

No API key. No authentication. Pure stdlib (`urllib`, `json`, `dataclasses`).

---

## Quick Start

```bash
# Show statewide conditions summary
python3 cdot_client.py summary

# List active traffic cameras
python3 cdot_client.py cameras --limit 20

# List mountain pass conditions
python3 cdot_client.py mountain-passes

# List road closures in Denver area
python3 cdot_client.py events --layer roadClosures \
    --north 40.0 --south 39.5 --east -104.5 --west -105.5 --zoom 10

# Show travel alerts (as JSON)
python3 cdot_client.py alerts --json
```

```python
from cdot_client import CDOTClient

client = CDOTClient()

# Get all traffic cameras
cameras = client.get_cameras(active_only=True)
print(f"Active cameras: {len(cameras)}")

# Get I-70 mountain corridor cameras
i70_cams = client.get_i70_cameras()
for cam in i70_cams[:5]:
    print(f"  {cam.name}")
    print(f"  Snapshot: {cam.primary_snapshot_url}")

# Get active road closures statewide
closures = client.get_road_closures()
for c in closures:
    lat, lon = c.centroid
    print(f"  {c.title} @ {lat:.4f},{lon:.4f}")

# Get mountain pass conditions
passes = client.get_mountain_passes()
for p in passes:
    print(f"  {p.title} — {p.uri}")

# Get CDOT travel alerts
for alert in client.get_travel_alerts():
    print(f"  [{alert.priority}] {alert.title}")
```

---

## Installation

No dependencies beyond Python 3.9+ stdlib.

```bash
# Clone or copy cdot_client.py into your project
# No pip install needed
```

---

## Architecture

COtrip uses a two-tier API architecture reverse-engineered from the JavaScript bundles at `maps.cotrip.org` (version 3.19.10, March 2026).

### Tier 1 — REST Microservices

Base URL: `https://cotg.carsprogram.org`

These are direct microservice endpoints that return raw JSON arrays. No authentication required. Polled every 60 seconds by the web app.

| Endpoint | Records | Description |
|----------|---------|-------------|
| `GET /cameras_v1/api/cameras` | 1 029 | Traffic cameras with HLS stream + JPEG snapshot URLs |
| `GET /signs_v1/api/signs` | 214 | Variable message signs (VMS/DMS) with current display |
| `GET /rwis_v1/api/stations` | 135 | RWIS weather stations (metadata only) |
| `GET /rest-areas_v1/api/restAreas` | 45 | Rest areas with amenities, open/closed status |
| `GET /avl_v2/api/plows` | 50+ | Snowplow GPS tracks with heading and route |

### Tier 2 — GraphQL BFF

URL: `https://maps.cotrip.org/api/graphql`

A Backend-for-Frontend GraphQL proxy that aggregates the microservices. The primary query is `mapFeaturesQuery` which accepts a geographic bounding box, zoom level, and a `layerSlugs` list.

**Important:** The proxy applies rate limiting and returns `HTTP 400 {"errors":[{"message":"Server error."}]}` when overloaded. The client automatically retries with exponential backoff (up to 3 retries, starting at 1.5s).

---

## REST API Details

### Cameras — `/cameras_v1/api/cameras`

Returns an array of camera objects:

```json
{
  "id": 133,
  "public": true,
  "name": "I-70 MP 285.20 EB : 0.5 miles W of Tower Rd",
  "lastUpdated": 1774641031178,
  "location": {
    "fips": 8,
    "latitude": 39.762168,
    "longitude": -104.7812,
    "routeId": "Unknown",
    "localRoad": true
  },
  "cameraOwner": { "name": "Colorado DOT" },
  "views": [
    {
      "name": "I-70 MP 285.20 EB : 0.5 miles W of Tower Rd",
      "type": "WMP",
      "url": "https://publicstreamer2.cotrip.org:443/rtplive/070E28520CAM1RP2/playlist.m3u8",
      "videoPreviewUrl": "https://cocam.carsprogram.org/Snapshots/070E28520CAM1RP2.flv.png",
      "imageTimestamp": 1774641018000
    }
  ],
  "active": true
}
```

**Camera Media CDN:**
- **HLS Streams:** `https://publicstreamer2.cotrip.org:443/rtplive/<CAMERA_ID>/playlist.m3u8`
- **JPEG Snapshots:** `https://cocam.carsprogram.org/Snapshots/<CAMERA_ID>.flv.png`

Camera IDs are embedded in the URL paths (e.g. `070E28520CAM1RP2`).

### Signs — `/signs_v1/api/signs`

```json
{
  "id": "coopentms*OpenTMS-Sign465279",
  "status": "DISPLAYING_MESSAGE",
  "name": "I-70 237.00 Westbound",
  "display": {
    "pages": [
      { "hasImage": false, "justification": "CENTER", "lines": ["65", "65"] }
    ]
  },
  "location": {
    "latitude": 39.756297,
    "longitude": -105.564112,
    "routeId": "I-70",
    "linearReference": 237.0,
    "locationDescription": "I-70 W at MP 237.0"
  },
  "properties": {
    "signType": "VSLS",
    "maxLinesPerPage": 3,
    "maxCharactersPerLine": 16
  },
  "lastUpdated": 1774371151134
}
```

Sign statuses: `DISPLAYING_MESSAGE`, `BLANK`, `ERROR_OR_FAILURE`, `OUT_OF_COMMUNICATION`, `NOT_REPORTING`

### RWIS Weather Stations — `/rwis_v1/api/stations`

```json
{
  "id": 256,
  "stationIdentifier": "OpenTMS-Weather514355",
  "name": "US-24 254.35 Westbound at Wilkerson Pass",
  "timezoneId": "America/Denver",
  "lastUpdated": 1773886435061,
  "topFields": [
    "TEMP_AIR_TEMPERATURE",
    "PAVEMENT_SURFACE_STATUS",
    "VIS_VISIBILITY",
    "PRECIP_SITUATION",
    "WIND_AVG_SPEED",
    "WIND_MAX_SPEED",
    "PRECIP_PAST_HOUR"
  ],
  "location": {
    "latitude": 39.039024,
    "longitude": -105.525586,
    "routeId": "US 24",
    "linearReference": 254.33,
    "cityReference": "14 miles east of the Hartsel area"
  }
}
```

`topFields` lists the sensor types available at this station. Actual readings require the GraphQL `weatherStationQuery` with the station ID.

### Rest Areas — `/rest-areas_v1/api/restAreas`

```json
{
  "id": 3,
  "title": "Wyoming Welcome Center",
  "routeDesignator": "I-25",
  "directionOfTravel": "N",
  "isOpen": true,
  "displayLatitude": 41.05826,
  "displayLongitude": -104.8795,
  "nearbyCity": "20 miles north of the Wellington area",
  "amenities": [
    { "label": "Phone", "slug": "phone" },
    { "label": "Restrooms", "slug": "restrooms" },
    { "label": "Visitor Info", "slug": "visitor_info" },
    { "label": "Cell Service", "slug": "cell_service" }
  ],
  "statusMessage": null,
  "lastUpdate": "2021-05-10T17:13:42.641Z"
}
```

### Snowplow Tracker (AVL) — `/avl_v2/api/plows`

```json
{
  "id": "bB89",
  "statuses": [
    {
      "timestamp": 1774645082037,
      "latitude": 37.9872017,
      "longitude": -103.526482,
      "routeDesignator": "US 50",
      "linearReference": 380.7,
      "headingString": "West",
      "nearbyPointsDescription": "Between Prospect Avenue and CO 109",
      "totalTruckCount": 50,
      "plowIconName": "/None_West.png"
    }
  ]
}
```

`statuses` is ordered most-recent first. `totalTruckCount` is the fleet size, not a count for this vehicle.

---

## GraphQL API Details

### Endpoint

`POST https://maps.cotrip.org/api/graphql`

Headers: `Content-Type: application/json`

No authentication token required.

### mapFeaturesQuery

The primary query for all map data. Returns GeoJSON-style features clustered by zoom level.

```graphql
query MapFeatures($input: MapFeaturesArgs!, $plowType: String) {
    mapFeaturesQuery(input: $input) {
        mapFeatures {
            bbox
            title
            tooltip
            uri
            features {
                id
                geometry
                properties
                type
            }
            ... on Event {
                priority
            }
            __typename
        }
    }
}
```

**Variables:**
```json
{
  "input": {
    "north": 40.0,
    "south": 39.5,
    "east": -104.5,
    "west": -105.5,
    "zoom": 10,
    "layerSlugs": ["roadWork"]
  },
  "plowType": "snow-plow-camera"
}
```

**Required fields:** `north`, `south`, `east`, `west`, `zoom`, `layerSlugs`

**Zoom guidelines:**
- `3–5`: Statewide Colorado (very aggressive clustering)
- `6–8`: Regional (state quadrant)
- `9–11`: Metro area / county level
- `12–15`: Street level (individual features visible)

**Response typename values:** `Event`, `Custom`, `Cluster`, `Sign`, `Plow`, `RestArea`, `Camera`

### Valid layerSlugs

Discovered by reverse-engineering the JavaScript layer configuration array:

| Slug | Description | Typical __typename |
|------|-------------|-------------------|
| `roadReports` | Active traffic incidents (crashes, hazards) | Event |
| `roadWork` | Active construction zones | Event |
| `roadClosures` | Current road closures | Event |
| `future` | Planned / upcoming construction | Event |
| `winterDriving` | Road condition reports | Event |
| `chainLaws` | Chain / traction law requirements | Event |
| `chainStations` | Chain check and brake check stations | Custom |
| `mountainPasses` | Mountain pass conditions | Custom |
| `weatherWarnings` | NWS weather alerts on roads | Event |
| `wazeReports` | Crowd-sourced Waze incident reports | Event |
| `restrictions` | Oversize / overweight restrictions | Event |
| `weighStations` | Weigh station locations | Custom |
| `truckRamps` | Runaway truck ramp locations | Custom |
| `truckStopsPortsEntry` | Truck stops and ports of entry | Custom |
| `expressLanes` | Express lane features | Custom |
| `scenicByways` | Scenic byway markers | Custom |

### cmsMessagesQuery

Returns active CDOT travel alerts and safety announcements:

```graphql
query CmsMessages {
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

**Response example:**
```json
{
  "uri": "announcements/866",
  "title": "Travel Alert | Floyd Hill Construction",
  "content": "<p>Construction on the I-70 Floyd Hill project...</p>",
  "priority": null,
  "messageType": null
}
```

### Other GraphQL Queries

```graphql
# System notifications (Amber alerts, emergency notices)
query Notifications {
    notificationsQuery {
        notifications {
            uri title description type
            lastUpdated { timestamp timezone }
        }
    }
}

# Named route / corridor definitions
query {
    allPredefinedRoutesQuery {
        name sortOrder popular bbox
    }
}
```

---

## URI Scheme

The `uri` field in GraphQL responses identifies the resource type and ID:

| Pattern | Type |
|---------|------|
| `event/CDOT-<ID>NB` | Traffic event (directional) |
| `event/CDOT-<ID>BOTH` | Traffic event (both directions) |
| `mountainPasses/mountainPass-<N>` | Mountain pass |
| `chainStations/chainStation-<N>` | Chain station |
| `weighStations/weighStation-<N>` | Weigh station |
| `cluster/<hash>` | Cluster of nearby features |
| `announcements/<N>` | CMS travel alert |

---

## Rate Limiting

The GraphQL BFF at `maps.cotrip.org` applies rate limiting:

- **Symptom:** `HTTP 400 {"errors":[{"message":"Server error."}]}`
- **Mitigation:** The client automatically retries up to 3 times with exponential backoff (1.5s → 3s → 6s)
- **Best practice:** Space sequential requests ≥1 second apart when making many calls

The REST microservices at `cotg.carsprogram.org` appear to have no rate limiting.

---

## CLI Reference

```
usage: cdot_client.py [-h] [--layer SLUG] [--limit N] [--json] [--active-only]
                      [--north NORTH] [--south SOUTH] [--east EAST] [--west WEST]
                      [--zoom Z] [--timeout T]
                      {cameras,signs,weather-stations,rest-areas,plows,
                       events,mountain-passes,alerts,summary}

Commands:
  cameras          List traffic cameras
  signs            List variable message signs
  weather-stations List RWIS weather stations
  rest-areas       List rest areas and welcome centers
  plows            List active snowplow vehicles (winter operations)
  events           List map events for a given layer slug
  mountain-passes  List mountain pass conditions
  alerts           List CDOT travel alerts
  summary          Print statewide conditions summary

Options:
  --layer SLUG     Layer slug for the events command (default: roadReports)
  --limit N        Maximum number of results to display (default: 20)
  --json           Output raw JSON instead of formatted text
  --active-only    Filter to active cameras / open rest areas only
  --north/south/east/west FLOAT
                   Bounding box in decimal degrees (default: all of Colorado)
  --zoom Z         Map zoom level 3-15 (default: 5 for statewide)
  --timeout T      HTTP timeout in seconds (default: 20)
```

**Examples:**

```bash
# Statewide summary
python3 cdot_client.py summary

# All active cameras as JSON
python3 cdot_client.py cameras --json > cameras.json

# Signs currently displaying messages
python3 cdot_client.py signs --active-only

# Road closures in Denver metro (zoom 10 for detail)
python3 cdot_client.py events --layer roadClosures \
    --north 40.0 --south 39.5 --east -104.5 --west -105.5 --zoom 10

# Mountain pass conditions statewide
python3 cdot_client.py mountain-passes --zoom 5

# Chain law requirements near I-70 corridor
python3 cdot_client.py events --layer chainLaws \
    --north 40.0 --south 39.3 --east -105.0 --west -107.0 --zoom 8

# All active construction projects
python3 cdot_client.py events --layer roadWork --zoom 6 --limit 50

# Planned future construction statewide
python3 cdot_client.py events --layer future --zoom 5

# Weather warnings (NWS alerts affecting roads)
python3 cdot_client.py events --layer weatherWarnings --zoom 6
```

---

## Python API Reference

### `CDOTClient(timeout=20)`

Main client class.

**REST Methods** (direct microservice calls, no rate limiting):

| Method | Returns | Description |
|--------|---------|-------------|
| `get_cameras(active_only=False)` | `list[Camera]` | All traffic cameras |
| `get_signs(displaying_only=False)` | `list[Sign]` | Variable message signs |
| `get_weather_stations()` | `list[WeatherStation]` | RWIS weather stations |
| `get_rest_areas(open_only=False)` | `list[RestArea]` | Rest areas |
| `get_plows()` | `list[Plow]` | Snowplow GPS tracks |

**GraphQL Methods** (BFF, rate-limited):

| Method | Returns | Description |
|--------|---------|-------------|
| `get_events(layer_slug, *, north, south, east, west, zoom)` | `list[MapFeature]` | Generic map features by layer |
| `get_road_closures(**bbox)` | `list[MapFeature]` | Active road closures |
| `get_chain_laws(**bbox)` | `list[MapFeature]` | Chain/traction law requirements |
| `get_mountain_passes(**bbox)` | `list[MapFeature]` | Mountain pass conditions |
| `get_construction(**bbox)` | `list[MapFeature]` | Active construction zones |
| `get_incidents(**bbox)` | `list[MapFeature]` | Traffic incidents |
| `get_winter_driving(**bbox)` | `list[MapFeature]` | Road condition reports |
| `get_weather_warnings(**bbox)` | `list[MapFeature]` | NWS weather alerts |
| `get_travel_alerts()` | `list[TravelAlert]` | CDOT CMS travel alerts |
| `get_all_events(**bbox)` | `dict[str, list[MapFeature]]` | All event layers in one call |

**Convenience Methods:**

| Method | Returns | Description |
|--------|---------|-------------|
| `search_cameras_by_route(route_id)` | `list[Camera]` | Cameras on a route (e.g. "I-70") |
| `get_i70_cameras()` | `list[Camera]` | I-70 mountain corridor cameras |
| `get_mountain_pass_cameras()` | `list[Camera]` | Cameras near mountain passes |
| `get_camera_snapshot(camera)` | `bytes \| None` | Download JPEG snapshot image |
| `statewide_summary()` | `dict` | Counts across all data types |

### Data Classes

#### `Camera`
```python
@dataclass
class Camera:
    id: int
    name: str
    location: Location
    views: list[CameraView]
    active: bool
    public: bool
    owner: Optional[str]
    last_updated: Optional[int]  # Unix ms

    @property
    def primary_snapshot_url(self) -> str: ...
    @property
    def primary_stream_url(self) -> str: ...
```

#### `CameraView`
```python
@dataclass
class CameraView:
    name: str
    view_type: str          # "WMP" = HLS stream
    stream_url: str         # HLS .m3u8 live stream
    snapshot_url: str       # JPEG snapshot
    image_timestamp: Optional[int]  # Unix ms

    @property
    def snapshot_age_seconds(self) -> Optional[float]: ...
```

#### `MapFeature`
```python
@dataclass
class MapFeature:
    uri: str                # e.g. "event/CDOT-12345NB"
    title: str
    typename: str           # "Event", "Custom", "Cluster", etc.
    bbox: list[float]       # [west, south, east, north]
    features: list[dict]    # GeoJSON feature objects
    tooltip: Optional[str]
    priority: Optional[int] # Events only

    @property
    def resource_type(self) -> str: ...  # "event", "mountainPasses", etc.
    @property
    def resource_id(self) -> str: ...
    @property
    def centroid(self) -> tuple[float, float]: ...  # (lat, lon)
```

#### `Sign`
```python
@dataclass
class Sign:
    id: str
    name: str
    status: str             # "DISPLAYING_MESSAGE", "BLANK", etc.
    location: Location
    display_lines: list[list[str]]
    agency_id: Optional[str]
    agency_name: Optional[str]
    sign_type: Optional[str]
    last_updated: Optional[int]

    @property
    def current_message(self) -> str: ...  # All lines as readable string
```

#### `TravelAlert`
```python
@dataclass
class TravelAlert:
    uri: str
    title: str
    content: Optional[str]   # HTML content
    priority: Optional[str]
    message_type: Optional[str]
    display_locations: Optional[list[str]]
```

---

## Discovered Infrastructure

### API Domains

| Domain | Role |
|--------|------|
| `cotg.carsprogram.org` | REST microservices (primary data API) |
| `maps.cotrip.org` | GraphQL BFF proxy + web app |
| `www.cotrip.org` | Splash/marketing site |
| `cocam.carsprogram.org` | Camera snapshot CDN |
| `publicstreamer2.cotrip.org:443` | HLS live stream server |
| `gwc.carsprogram.org` | WMS weather radar tiles |
| `public.carsprogram.org/co/prod` | Public S3 data (GeoJSON, requires auth) |
| `nlp.carsprogram.org` | Natural language route search |
| `freight.cotrip.org` | Freight/commercial vehicle portal |
| `subscription.cotrip.org` | Alert subscriptions |

### Technology Stack

- **Platform:** CARS (Connected and Automated Roads System) by CastleRock ITS
- **Frontend:** Web Components (LitElement), Redux state management, Webpack bundles
- **Backend:** Java RESTEasy microservices behind Nginx/CloudFront
- **CDN:** AWS CloudFront
- **Maps:** Google Maps API (key: `AIzaSyAg3mTV0MQ-_91ZzNVV-qgsfGW28IQn8pY`, browser-restricted)
- **Analytics:** Google Tag Manager (`G-G221BGV94P`)

### Known Non-Public or Disabled Endpoints

| Endpoint | Notes |
|----------|-------|
| `events_v1/api/events` | Returns 404 — events served via GraphQL only |
| `mountainpasses_v1/api/mountain-passes` | Returns 404 — served via GraphQL only |
| `parking_v1/api` | Returns 404 — not enabled for CO |
| `floodgates_v1/api` | Returns 404 — not enabled for CO production |
| `fueling-stations_v1/api` | Returns 502 — EV charging data not deployed |
| `wildfire_v1/api` | Returns 404 — wildfire data via GraphQL only |
| `traveltimes_v1/api/travel-times` | Returns 404 — travel times via GraphQL |
| `amber_v1/api` | Returns 404 — amber alerts served via GraphQL |
| `public.carsprogram.org/co/prod` | HTTP 403 — requires CDN signing |

---

## Legal Notes

This client accesses only publicly available data that the COtrip website loads without authentication. The same data is available through CDOT's official 511 service and is intended for public consumption.

Do not use this client to:
- Make automated requests at rates that could harm the service
- Redistribute camera stream content commercially
- Violate the [COtrip Terms of Use](https://maps.cotrip.org/help/terms-of-use.html)

CDOT also provides official data feeds through the [Colorado Open Data catalog](https://data.colorado.gov) for bulk / batch use cases.

---

## Changelog

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | 2026-03-27 | Initial release — reverse-engineered from COtrip 3.19.10 |
