# NCDOT Traffic API Client

> Python client (stdlib only) for the North Carolina Department of Transportation (NCDOT) traffic information API — powering DriveNC.gov.

No API key required. No third-party dependencies. Python 3.7+.

---

## Why This Exists

The [DriveNC.gov](https://drivenc.gov) interactive traffic map is powered by a public REST/JSON API hosted at `eapps.ncdot.gov`. This library wraps those endpoints in typed Python dataclasses, exposing live camera feeds, traffic incidents, road closures, county conditions, rest areas, and ferry routes without requiring browser automation or authentication.

---

## Quick Start

```python
from ncdot_client import NCDOTClient

client = NCDOTClient()

# List all 779 cameras statewide
cameras = client.list_cameras()
print(f"{len(cameras)} cameras found")

# Get full details for camera 5 (I-40 near Durham)
cam = client.get_camera(5)
print(cam.location_name)   # "I-40 Exit 270 - US 15 - 501"
print(cam.image_url)       # live JPEG snapshot URL

# Download the live JPEG snapshot
img_bytes = client.get_camera_image(5)
with open("i40_cam.jpg", "wb") as f:
    f.write(img_bytes)

# All active incidents statewide
incidents = client.list_incidents()
high = [i for i in incidents if i.severity == 3]
print(f"{len(high)} high-severity incidents active")

# Full incident detail
detail = client.get_incident(incidents[0].id)
print(detail.reason)     # "TWO VEHICLE ACCIDENT I77 NB MM 24.7 BOTH ML LANES BLOCKED"
print(detail.condition)  # "Lane Closed"
```

---

## Discovered API

**Reverse-engineered from:** https://drivenc.gov
**JavaScript source:** https://drivenc.gov/Scripts/app.js
**Configuration source:** https://drivenc.gov/Scripts/data.json
**Discovered:** 2026-03-27

### Base URL

```
https://eapps.ncdot.gov/services/traffic-prod/v1
```

### Authentication

None. All endpoints are fully public and unauthenticated.

### Rate Limiting

No explicit rate limiting observed, but the application polls cameras every 3 minutes (`cameraUpdateLoop: 180000ms`) and incidents every 5 minutes (`incidentUpdateLoop: 300000ms`). Respecting similar intervals is recommended.

---

## All Discovered Endpoints

### Camera Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/cameras/` | List all cameras (id + lat/lon only) |
| `GET` | `/cameras/{id}` | Full camera record including image URL |
| `GET` | `/cameras/images?filename={name}` | Fetch live JPEG snapshot binary |

#### Camera object fields (`/cameras/{id}`)

```json
{
  "id": 5,
  "locationName": "I-40 Exit 270 - US 15 - 501",
  "displayName": "",
  "mileMarker": 270.00,
  "roadId": 1,
  "countyId": 32,
  "latitude": 35.950774,
  "longitude": -78.998909,
  "imageURL": "https://eapps.ncdot.gov/services/traffic-prod/v1/cameras/images?filename=I40_US15-501.jpg",
  "isDOTCamera": true,
  "status": "OK"
}
```

**Image URL pattern:**
`https://eapps.ncdot.gov/services/traffic-prod/v1/cameras/images?filename={FILENAME}.jpg`

Filenames follow the road + junction naming convention, e.g.:
- `I40_US15-501.jpg`
- `I40_NC751.jpg`

Images are served as `image/jpeg` (typically 20-35 KB). They refresh on a time-based schedule — add a `?t={timestamp}` parameter to bypass browser caches.

---

### Incident Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/traffic/incidents` | Live map-pin list (lightweight, ~350-650 records) |
| `GET` | `/incidents/{id}` | Full incident detail record |
| `GET` | `/incidents?active=true` | Active incident ID lists and counts |
| `GET` | `/incidents/filters?...` | Paginated search with filter support |
| `GET` | `/incidents/filters/count?...` | Count incidents matching a filter |
| `GET` | `/incidents/groups` | Incident type taxonomy |
| `GET` | `/activeincidentsreport` | Download full statewide report as `.xlsx` |

#### `/traffic/incidents` — lightweight list

```json
{
  "id": 766338,
  "eventId": 1,
  "lat": 35.4482135334689,
  "long": -80.8689182558723,
  "type": "Vehicle Crash",
  "start": "2026-03-27T19:08:00Z",
  "sev": 3,
  "lastUpdate": "2026-03-27T19:52:48Z",
  "road": "I ",
  "polyline": "{\"type\": \"LineString\",\"coordinates\":[...]}"
}
```

**Severity scale:**
- `1` = Low impact (shoulder closed, minor maintenance)
- `2` = Medium impact (lane closed, significant construction)
- `3` = High impact (road closed, major crash, multiple lanes blocked)

#### `/incidents/{id}` — full detail

```json
{
  "id": 766338,
  "start": "2026-03-27T19:08:00Z",
  "end": "2026-03-27T21:08:00Z",
  "road": { "name": "I-77", "commonName": "", "suffix": "" },
  "city": "Huntersville",
  "direction": "N",
  "location": "In Huntersville / Mile Marker 24.7 to 24.7 Heading North",
  "county": { "id": 60, "name": "Mecklenburg" },
  "coords": { "latitude": 35.4482135334689, "longitude": -80.8689182558723 },
  "reason": "TWO VEHICLE ACCIDENT I77 NB MM 24.7 BOTH ML LANES BLOCKED",
  "condition": "Lane Closed",
  "severity": 3,
  "isDetour": true,
  "detour": "",
  "lanesClosed": 2,
  "lanesTotal": 4,
  "incidentType": "Vehicle Crash",
  "crossRoad": { "commonName": "", "number": "77", "prefix": "I", "suffix": "" },
  "workZoneSpeedLimit": 0,
  "concurrentIncidents": []
}
```

**Condition strings observed:**
- `Lane Closed`
- `Road Closed`
- `Road Closed with Detour`
- `Shoulder Closed`
- `Road Impassable`
- `Permanent Road Closure`
- `Local Traffic Only`
- `Ramp Closed`
- `Ferry Closed`

#### `/incidents/filters` — paginated search

Query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `pageSize` | int | Results per page (use 9999 for all) |
| `pageNumber` | int | 1-indexed page number |
| `orderBy` | string | Sort field: `Start`, `County` |
| `order` | string | `asc` or `desc` |
| `filterType` | string | See filter types below |
| `filterValue` | string | Value matching filterType |

**Valid `filterType` values for `/incidents/filters`:**

| filterType | filterValue example | Description |
|------------|---------------------|-------------|
| `COUNTY` | `60` (Mecklenburg) | Filter by county ID |
| `REGION` | `1` (Triangle) | Filter by region ID |
| `ROUTE` | `I-40` | Filter by road name |
| `ROADCLOSURE` | `true` | Only road-closure incidents |
| `CONDITION` | `Road Closed` | Filter by condition string |
| `INCIDENTTYPE` | `Construction` | Filter by incident type |
| `EVENTS` | `1` | Filter by event ID |

**Valid `filterType` values for `/incidents/filters/count`:**

`COUNTY`, `PROJECT`, `REGION`, `ROUTE`

#### Incident type groups

From `/incidents/groups`:

| Group | Types |
|-------|-------|
| Other Incidents | Vehicle Crash, Fire (Non Vehicle), Disabled Vehicle, Vehicle Fire, Special Event, Congestion, Road Obstruction, Reported Incident, Other, Weather Event, Fog, Signal Problem, Emergency Road Work |
| Road Work | Maintenance, Construction, Night Time Construction, Weekend Construction, Night Time Maintenance |
| Truck Closures | Truck Closure |

---

### County/Region/Road Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/counties/conditions` | Road conditions for all 100 NC counties |
| `GET` | `/counties/{id}/conditions` | Conditions for a single county |
| `GET` | `/traffic/regions` | Geographic region definitions |
| `GET` | `/traffic/roads` | All 342 monitored roads |
| `GET` | `/traffic/events` | Active special traffic events |

#### County conditions object

```json
{
  "id": 1,
  "name": "Alamance",
  "regions": "2",
  "roadConditions": {
    "interstate": "Clear",
    "primary": "Clear",
    "secondary": "Clear"
  },
  "status": "No Report",
  "lastUpdated": "2026-02-09T12:56:14Z"
}
```

**Road condition values:** `Clear`, `Snow/Ice`, `N/A`
**Status values:** `Clear` (active report), `No Report`

#### Region definitions

| ID | Region Name |
|----|-------------|
| 1 | Triangle |
| 2 | Triad |
| 3 | Rural Piedmont |
| 4 | Metrolina |
| 5 | Eastern Mountains |
| 6 | Western Mountains |
| 7 | Asheville Vicinity |
| 8 | Northern Coastal |
| 9 | Southern Coastal |
| 10 | Fayetteville Vicinity |

#### Road object

```json
{ "id": 1, "name": "I-40", "counties": "Alamance,Buncombe,Burke,Catawba,..." }
```

342 roads total. Use the `name` string (e.g. `"I-40"`) as `filterValue` for route-based incident searches.

---

### Rest Area Endpoint

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/restarealocations` | All NC rest areas, welcome centers, visitor centers |

#### Rest area object fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique identifier |
| `name` | string | Location name |
| `title` | string | Display title |
| `type` | string | "Rest Area", "Visitor Center", or "Welcome Center" |
| `status` | string | "closed" if not operational |
| `seasonal` | string | Seasonal operation hours |
| `phone` | string | Contact number |
| `county` | string | County name |
| `route` | string | Highway route |
| `bound` | string | Travel direction (N/S/E/W/Median) |
| `mileMarker` | string | Mile post |
| `division` | int | NCDOT division number |
| `geo` | object | `{lat: float, long: float}` |
| `accommodations` | array | Amenity strings |
| `parking` | object | `{car: int, carTrailer: int, truck: int}` |
| `image` | string | Facility photo URL |
| `information` | string | Historical/descriptive text |
| `sustainable` | bool | Environmentally certified |

57 facilities total (55 open), including rest areas, visitor centers, and welcome centers.

---

### Ferry Routes (ArcGIS)

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | ArcGIS NCDOT_FerryRoutes FeatureServer | GeoJSON ferry route geometries |

**Full URL:**
```
https://services.arcgis.com/NuWFvHYDMVmmxMeM/arcgis/rest/services/
NCDOT_FerryRoutes/FeatureServer/0/query?f=json&where=1%3D1&outFields=*
&returnGeometry=true&outSR=4326
```

Returns GeoJSON features with route geometries and attributes.

---

### Supplementary External Endpoints

These endpoints are used by the DriveNC application but are hosted on external services:

| Service | URL Pattern | Notes |
|---------|-------------|-------|
| NREL EV Charging Stations | `https://developer.nrel.gov/api/alt-fuel-stations/v1.json?...` | NC public EV chargers; includes API key in client config |
| NOAA Weather Alerts | `https://alerts.weather.gov/cap/nc.php?x=0` | Statewide weather alert feed (CAP/XML) |
| NOAA Forecast | `https://forecast.weather.gov/zipcity.php?inputstring={zip}` | Forecast by ZIP code |
| Iowa State Radar | `https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-{timestamp}/{z}/{x}/{y}.png` | Radar tile service |
| ArcGIS Mile Markers | `https://services.arcgis.com/NuWFvHYDMVmmxMeM/...NCDOT_Mile_Markers_Published_View/...` | Mile marker locations by county |
| NC Emergency Shelters | `https://spartagis.ncem.org/arcgis/rest/services/Public/ReadyNC_Shelters/MapServer/0/query` | Open emergency shelters |
| FEMA Shelters | `https://gis.fema.gov/arcgis/rest/services/NSS/FEMA_NSS/MapServer/0/query?where=STATE%3D%27NC%27` | FEMA national shelter system (NC) |

**Note on API keys found in client config:**
- **Bing Maps:** `AqEzksJZFEGOGHP6b1Ufc_WZTVsSCFI0pb4v_Bdc16O9cU71TtHeSJdSgLJCAFCk` (map display only)
- **NREL:** `U5PrTgaUgaBox02ITIQXftF1R99cZ3b0z4xsbRl2` (EV charging stations — free tier)
- **Weather:** `JRgOaVEukQa8BABlTa6mgcUSBeCskHCdj5kkXascxsA` (Yahoo Weather, deprecated)

These keys are embedded in the public-facing JavaScript and scoped to display/lookup functionality only.

---

## Installation

No installation required. Copy `ncdot_client.py` into your project. Uses only Python standard library modules:

- `urllib.request` / `urllib.error` — HTTP
- `json` — response parsing
- `dataclasses` — typed data models
- `argparse` — CLI
- `typing` — type hints

**Requirements:** Python 3.7+

---

## Usage

### Python API

```python
from ncdot_client import NCDOTClient

client = NCDOTClient()
```

#### Camera Operations

```python
# List all cameras (id + coordinates only — fast)
cameras = client.list_cameras()
# Returns: List[CameraLocation]

# Get full camera detail with image URL
cam = client.get_camera(5)
# Returns: Camera

print(cam.id)             # 5
print(cam.location_name)  # "I-40 Exit 270 - US 15 - 501"
print(cam.mile_marker)    # 270.0
print(cam.road_id)        # 1 (I-40)
print(cam.county_id)      # 32 (Durham)
print(cam.status)         # "OK"
print(cam.image_url)      # full JPEG URL
print(cam.image_filename) # "I40_US15-501.jpg"

# Download live JPEG snapshot (returns bytes)
img = client.get_camera_image(5)
with open("cam5.jpg", "wb") as f:
    f.write(img)

# Download by filename directly
img = client.get_camera_image_by_filename("I40_US15-501.jpg")

# All cameras in a specific county (slower — fetches each individually)
durham_cams = client.list_cameras_for_county(32)
```

#### Incident Operations

```python
# Live incident list (map pins, lightweight)
incidents = client.list_incidents()
# Returns: List[IncidentSummary]

# Full incident detail
detail = client.get_incident(766338)
# Returns: IncidentDetail

print(detail.road_name)     # "I-77"
print(detail.city)          # "Huntersville"
print(detail.reason)        # "TWO VEHICLE ACCIDENT..."
print(detail.condition)     # "Lane Closed"
print(detail.severity)      # 3
print(detail.lanes_closed)  # 2
print(detail.lanes_total)   # 4
print(detail.is_detour)     # True

# Quick count summary (fastest way to check impact)
summary = client.get_active_incident_summary()
print(summary.active_count)          # total active
print(len(summary.road_closed_ids))  # count of road closures
print(len(summary.lane_closed_ids))  # count of lane closures

# Search incidents by filter
results = client.search_incidents(
    filter_type="ROUTE",
    filter_value="I-40",
    page_size=100,
)
# Returns: List[IncidentSearchResult]

# All road closures statewide
closures = client.list_road_closures()

# Filter by county
mecklenburg = client.search_incidents(
    filter_type="COUNTY",
    filter_value="60",  # Mecklenburg county ID
)

# Filter by region
triangle = client.search_incidents(
    filter_type="REGION",
    filter_value="1",  # Triangle region
)

# Incident type taxonomy
groups = client.list_incident_groups()
for g in groups:
    print(g.group, g.types)
```

#### County and Road Conditions

```python
# All 100 counties
counties = client.list_counties()
# Returns: List[County]

for county in counties:
    if county.road_conditions.get("interstate") != "Clear":
        print(f"ALERT: {county.name} interstate: {county.road_conditions['interstate']}")

# Single county
durham = client.get_county(32)
print(durham.road_conditions)  # {"interstate": "Clear", "primary": "Clear", ...}

# Regions
regions = client.list_regions()
for r in regions:
    county_names = [c["name"] for c in r.counties]
    print(f"{r.name}: {county_names}")

# All 342 monitored roads
roads = client.list_roads()
for road in roads:
    print(road.name, road.county_list)
```

#### Rest Areas and Ferry Routes

```python
# Rest areas
areas = client.list_rest_areas()
open_areas = [a for a in areas if a.status != "closed"]
for area in open_areas:
    print(area.name, area.type, area.route)
    if area.parking:
        print(f"  Parking: {area.parking.car} cars, {area.parking.truck} trucks")

# Ferry routes (GeoJSON features from ArcGIS)
routes = client.list_ferry_routes()
for route in routes:
    attrs = route.get("attributes", {})
    geometry = route.get("geometry", {})
    # attrs contains route name, operator, schedule info

# Download Excel incidents report
xlsx_bytes = client.download_incidents_report()
with open("active_incidents.xlsx", "wb") as f:
    f.write(xlsx_bytes)
```

---

### Command-Line Interface

```
python ncdot_client.py <command> [options]
```

#### Commands

```bash
# Camera listing and details
python ncdot_client.py cameras
python ncdot_client.py camera 5
python ncdot_client.py camera-image 5 --save /tmp/cam5.jpg

# Incident information
python ncdot_client.py incidents
python ncdot_client.py incident 766338
python ncdot_client.py incident-summary

# Incident search
python ncdot_client.py search-incidents --filter ROUTE --value I-40
python ncdot_client.py search-incidents --filter ROADCLOSURE --value true
python ncdot_client.py search-incidents --filter REGION --value 1
python ncdot_client.py search-incidents --filter COUNTY --value 60 --page-size 100
python ncdot_client.py search-incidents --filter INCIDENTTYPE --value Construction
python ncdot_client.py search-incidents --filter CONDITION --value "Road Closed"
python ncdot_client.py incident-groups

# Geography
python ncdot_client.py counties
python ncdot_client.py county 32
python ncdot_client.py regions
python ncdot_client.py roads

# Facilities
python ncdot_client.py rest-areas
python ncdot_client.py ferry-routes
python ncdot_client.py traffic-events
```

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--base-url URL` | production URL | Override API base URL |
| `--timeout N` | `30` | Request timeout in seconds |
| `--filter TYPE` | `REGION` | Filter type for search-incidents |
| `--value V` | `1` | Filter value for search-incidents |
| `--page-size N` | `50` | Results per page |
| `--page N` | `1` | Page number |
| `--save PATH` | (prints info) | Save binary output (images, xlsx) to file |
| `--county ID` | None | Filter camera list by county ID |

---

## Data Reference

### County IDs (selected)

| ID | County | ID | County |
|----|--------|-----|--------|
| 1 | Alamance | 32 | Durham |
| 11 | Buncombe | 60 | Mecklenburg |
| 26 | Cumberland | 68 | Orange |
| 27 | Dare | 92 | Wake |
| 32 | Durham | 78 | Rowan |

Use `/counties/conditions` to retrieve the full list of all 100 county IDs.

### Region IDs

| ID | Region |
|----|--------|
| 1 | Triangle (Raleigh-Durham area) |
| 2 | Triad (Greensboro-Winston-Salem) |
| 3 | Rural Piedmont |
| 4 | Metrolina (Charlotte area) |
| 5 | Eastern Mountains |
| 6 | Western Mountains |
| 7 | Asheville Vicinity |
| 8 | Northern Coastal |
| 9 | Southern Coastal |
| 10 | Fayetteville Vicinity |

### Road Name Format for ROUTE Filter

Use the road name exactly as returned by `/traffic/roads`. Examples:
- `I-40`, `I-77`, `I-85`, `I-95`, `I-26`
- `NC-12`, `NC-54`, `NC-130`
- `US-17`, `US-64`, `US-158`
- `SR-2049` (secondary routes)

---

## Data Model Reference

### `CameraLocation`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Camera identifier |
| `latitude` | `float` | WGS-84 latitude |
| `longitude` | `float` | WGS-84 longitude |

### `Camera`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Camera identifier |
| `location_name` | `str` | Human-readable location |
| `display_name` | `str` | Optional alternate name |
| `mile_marker` | `float` | Mile post on associated road |
| `road_id` | `int` | Road identifier |
| `county_id` | `int` | County identifier |
| `latitude` | `float` | WGS-84 latitude |
| `longitude` | `float` | WGS-84 longitude |
| `image_url` | `str` | Live JPEG snapshot URL |
| `is_dot_camera` | `bool` | Official NCDOT camera |
| `status` | `str` | "OK" or "OFFLINE" |
| `image_filename` | `str` | (property) Filename from image_url |

### `IncidentSummary`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Unique identifier |
| `event_id` | `int` | Event grouping ID |
| `latitude` | `float` | WGS-84 latitude |
| `longitude` | `float` | WGS-84 longitude |
| `type` | `str` | Incident type string |
| `start` | `str` | ISO-8601 UTC start time |
| `severity` | `int` | 1-3 severity rating |
| `last_update` | `str` | ISO-8601 UTC last update |
| `road` | `str` | Road prefix ("I ", "NC", "US", "SR") |
| `polyline` | `str` | JSON-encoded GeoJSON LineString |

### `IncidentDetail`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Unique identifier |
| `start` / `end` | `str` | ISO-8601 UTC timestamps |
| `road_name` | `str` | Full road name |
| `city` | `str` | Nearest city |
| `direction` | `str` | Travel direction |
| `location` | `str` | Human-readable description |
| `county_id` / `county_name` | `int` / `str` | County info |
| `latitude` / `longitude` | `float` | Coordinates |
| `reason` | `str` | Free-text incident description |
| `condition` | `str` | Impact condition |
| `severity` | `int` | 1-3 rating |
| `is_detour` | `bool` | Detour active |
| `lanes_closed` | `int` | Closed lane count |
| `lanes_total` | `int` | Total lane count |
| `incident_type` | `str` | Type classification |
| `work_zone_speed` | `int` | Speed limit (0 if none) |
| `concurrent` | `List[int]` | Concurrent incident IDs |

### `County`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | County ID (1-100) |
| `name` | `str` | County name |
| `regions` | `str` | Comma-separated region IDs |
| `road_conditions` | `Dict[str, str]` | Keys: interstate, primary, secondary |
| `status` | `str` | "Clear" or "No Report" |
| `last_updated` | `str` | ISO-8601 UTC timestamp |

### `RestArea`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Identifier |
| `name` | `str` | Location name |
| `type` | `str` | "Rest Area", "Visitor Center", "Welcome Center" |
| `status` | `str` | "closed" if not operational |
| `seasonal` | `str` | Seasonal operation note |
| `county` | `str` | County name |
| `route` | `str` | Highway route |
| `bound` | `str` | Travel direction |
| `latitude` / `longitude` | `float` | Coordinates |
| `accommodations` | `List[str]` | Amenity list |
| `parking` | `Parking` | Car/truck/trailer capacity |
| `image_url` | `str` | Facility photo URL |
| `sustainable` | `bool` | Environmentally certified |

---

## Error Handling

```python
from ncdot_client import NCDOTClient, HTTPError, NCDOTError

client = NCDOTClient()

try:
    cam = client.get_camera(99999)
except HTTPError as exc:
    print(f"Not found: HTTP {exc.status}")  # HTTP 404
except NCDOTError as exc:
    print(f"Connection error: {exc}")
```

**Exception types:**

| Exception | When raised |
|-----------|-------------|
| `HTTPError` | Non-2xx HTTP response (has `.status` and `.body` attributes) |
| `NCDOTError` | Connection failure or JSON decode error |

---

## Polling and Refresh Intervals

Observed from `app.js` `_settings.timing`:

| Data Type | Refresh Interval | Notes |
|-----------|-----------------|-------|
| Camera images | 3 minutes | `cameraUpdateLoop: 180000ms` |
| Incidents | 5 minutes | `incidentUpdateLoop: 300000ms` |
| County conditions | 5 minutes | Polled alongside incidents |
| Full data refresh | 7 days | `clearDataForRefresh: 604800000ms` |

For live monitoring, polling incidents every 5 minutes and cameras every 3 minutes aligns with the official application behavior.

---

## Radar Tile CDN

Iowa State Mesonet serves radar tiles used by DriveNC:

```
https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-{timestamp}/{zoom}/{x}/{y}.png
```

Timestamp options (relative to current time):
- `900913-m50m` (50 min ago)
- `900913-m40m`, `900913-m30m`, `900913-m20m`, `900913-m10m`, `900913-m05m`
- `900913` (current)

The coordinate system is EPSG:900913 (Web Mercator). Use standard XYZ tile coordinates.

---

## Practical Examples

### Monitor a highway for new incidents

```python
import time
from ncdot_client import NCDOTClient

client = NCDOTClient()
seen_ids = set()

while True:
    incidents = client.search_incidents(
        filter_type="ROUTE",
        filter_value="I-40",
        page_size=200,
    )
    new = [i for i in incidents if i.id not in seen_ids]
    for inc in new:
        print(f"NEW: [{inc.id}] {inc.road} | {inc.condition} | {inc.county_name}")
        print(f"     {inc.location}")
        seen_ids.add(inc.id)
    time.sleep(300)  # 5-minute polling
```

### Download all camera images for a county

```python
import os
from ncdot_client import NCDOTClient, HTTPError

client = NCDOTClient()
cameras = client.list_cameras()
os.makedirs("images", exist_ok=True)

for loc in cameras:
    try:
        cam = client.get_camera(loc.id)
        if cam.county_id == 92 and cam.status == "OK":  # Wake County
            img = client.get_camera_image(loc.id)
            fname = f"images/cam_{cam.id}.jpg"
            with open(fname, "wb") as f:
                f.write(img)
            print(f"Saved {fname}: {cam.location_name}")
    except HTTPError:
        pass
    import time; time.sleep(0.5)
```

### Find all road closures with detours

```python
from ncdot_client import NCDOTClient

client = NCDOTClient()
closures = client.list_road_closures()

detours = [c for c in closures if "Detour" in c.condition]
print(f"{len(detours)} road closures with active detours:")
for c in detours:
    print(f"  {c.road} | {c.county_name} | {c.location}")
    print(f"  Type: {c.incident_type} | Until: {c.end[:10]}")
    print()
```

### Check winter road conditions across the mountains

```python
from ncdot_client import NCDOTClient

client = NCDOTClient()

# Get the Western Mountains region (id=6)
regions = client.list_regions()
mountain_region = next(r for r in regions if r.id == 6)
mountain_county_ids = [c["id"] for c in mountain_region.counties]

# Check road conditions
counties = client.list_counties()
mountain_counties = [c for c in counties if c.id in mountain_county_ids]

for county in mountain_counties:
    conds = county.road_conditions
    if any(v not in ("Clear", "N/A") for v in conds.values()):
        print(f"ALERT {county.name}: {conds}")
    else:
        print(f"OK    {county.name}: all clear")
```

---

## Methodology

This client was built by:

1. **Loading DriveNC.gov** and identifying the data configuration endpoint (`/Scripts/data.json`)
2. **Extracting the full config JSON** which contained all relative API paths and external service URLs
3. **Reading the minified `app.js`** to discover:
   - The base URL (`https://eapps.ncdot.gov/services/traffic-prod/v1`) injected at runtime
   - Admin URL (`https://tims.ncdot.gov/tims`)
   - Valid `filterType` enum values from server error messages
   - Polling intervals and application logic
4. **Reading `sharedWorker.js`** to understand how data is fetched and the road closure filter logic
5. **Live testing all endpoints** to document exact request/response schemas

No browser automation, proxy intercept, or reverse proxy was used — only public HTTP fetches and JavaScript source analysis.

---

## Legal Notice

This client accesses public government traffic information published by the North Carolina Department of Transportation for public safety and travel assistance. The data is freely accessible without authentication through the official DriveNC.gov platform.

- Use responsibly: respect rate limits and avoid hammering the API
- Do not use for commercial redistribution without verifying NCDOT's terms
- Camera images and incident data are real-time public safety information
- The NCDOT disclaims accuracy warranties on all real-time data

---

## Data Coverage

- **Cameras:** 779 total statewide
- **Incidents:** ~350-650 active at any time
- **Counties:** All 100 NC counties
- **Roads:** 342 monitored routes
- **Regions:** 10 geographic groupings
- **Rest Areas:** 57 facilities (55 typically open)
- **Coverage:** Statewide North Carolina

---

## Version and Stability

API version `1.23` (from project config). The NCDOT API does not appear to have formal versioning beyond the base path `/services/traffic-prod/v1`. Endpoints have been stable since at least 2022 based on community observations.

The Excel report endpoint is separate (`/activeincidentsreport`) and does not follow the JSON API versioning.
