# IDOT Getting Around Illinois — Python API Client

A complete Python client (stdlib only) for the public Illinois Department of
Transportation traffic and road-condition data APIs powering
[gettingaroundillinois.com](https://www.gettingaroundillinois.com).

No API key. No authentication. No third-party dependencies.

---

## Contents

- [Background: How the System Works](#background-how-the-system-works)
- [Discovered Endpoints](#discovered-endpoints)
- [Data Models](#data-models)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [API Reference](#api-reference)
- [Request / Response Formats](#request--response-formats)
- [Filtering & Pagination](#filtering--pagination)
- [Camera Images](#camera-images)
- [GeoJSON Support](#geojson-support)
- [Districts](#districts)
- [Notes & Limitations](#notes--limitations)

---

## Background: How the System Works

The Getting Around Illinois website is a **Web AppBuilder (WAB) for ArcGIS** application running on top of Esri's ArcGIS Online infrastructure. There are two layers:

1. **Frontend**: A JavaScript WAB application hosted at `gettingaroundillinois.com` using ArcGIS JS API 3.25. No authentication tokens are required to read public data layers.

2. **Backend**: All live data is served through **ArcGIS FeatureServer** endpoints on Esri's ArcGIS Online, under IDOT's organization ID `aIrBD8yn1TDTEXoz`.

   Base URL: `https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/`

3. **Camera images**: Live snapshots served from `https://cctv.travelmidwest.com/snapshots/` (a Travel Midwest CDN). Images are plain JPEG, publicly accessible, refreshed approximately every 2 minutes. No authentication is needed.

4. **Dynamic Message Sign images**: Rendered sign images served from `https://travelmidwest.com/messageSign?id=<sign_id>`.

The WAB `config.json` files for each sub-site reference ArcGIS WebMap items (stored in `idot.maps.arcgis.com`) that declare which feature services to render as layers. This is how the layer URLs were discovered.

---

## Discovered Endpoints

All endpoints use the ArcGIS REST API pattern:

```
GET https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/<service>/FeatureServer/<layer>/query
```

| Service Name | Layer | Records | Description |
|---|---|---|---|
| `TrafficCamerasTM_Public` | 0 | ~3,603 | Traffic camera locations + live snapshot URLs |
| `Illinois_Roadway_Incidents` | 0 | ~600–700 | Active incidents (accidents, road closures, congestion) |
| `Road_Construction_Public` | 2 | ~61 | Active/upcoming construction zones |
| `Wrc_Maintenance_Section_Road_Condition` | 0 | 410 | Winter road conditions by maintenance section |
| `RWIS` | 0 | 36 | Roadway Weather Information System stations |
| `DynamicMessaging` | 0 | 576 | Overhead Dynamic Message Sign current messages |
| `IL_Rest_Areas` | 0 | 54 | Rest area and welcome center status |
| `Waterway_Ferries` | 0 | 3 | Illinois waterway ferry crossing status |
| `ClosureIncidents` | 0 | ~3 | Planned road closure events |
| `ClosureIncidentExtents` | 0 | ~3 | Spatial extents of closures (polyline) |
| `Travel_Midwest_Unplanned_Events` | 0 | ~1–10 | Emergency/unplanned traffic events |
| `RegularlyFloodedRoadsForPublicUse` | 0 | variable | Flood-prone road locations |
| `Winter_Trouble_Spots1` | 0 | variable | Known winter trouble spot locations |

### Additional Supporting Services

| Service | Purpose |
|---|---|
| `IDOT_Districts` / `IDOTDistricts` | IDOT district polygon boundaries |
| `Counties` | Illinois county boundaries |
| `IL_MilePost` | Mile marker reference data |
| `Flooding_Road_Closures` | Flood-driven road closures |
| `EmergencySectors` | Emergency response sector polygons |
| `DynamicMessaging` + `Dynamic_Messaging_Signs` | DMS data (two versions exist) |

### Legacy / Offline Endpoints

These endpoints appeared in page source but return 404 at time of research:

```
https://webapps.dot.illinois.gov/GAI/WinterRoads/conditionReport  (404)
https://webapps.dot.illinois.gov/GAI/WinterRoads/conditionAlert   (404)
https://webapps.dot.illinois.gov/GAI/WinterRoads/conditionDate    (404)
```

These were superseded by the ArcGIS `Wrc_Maintenance_Section_Road_Condition` feature service.

---

## Request / Response Formats

### Query Parameters

All FeatureServer query endpoints accept these parameters:

| Parameter | Type | Description |
|---|---|---|
| `where` | string | SQL WHERE clause (URL-encoded). Use `1=1` for all records |
| `outFields` | string | Comma-separated field names, or `*` for all |
| `f` | string | Response format: `json`, `geojson`, `html` |
| `resultRecordCount` | int | Records per page (max 1000) |
| `resultOffset` | int | Pagination offset |
| `returnCountOnly` | bool | `true` to return only the count |
| `geometry` | string | Spatial filter (JSON geometry) |
| `spatialRel` | string | Spatial relationship (`esriSpatialRelIntersects`, etc.) |

### Response Structure (f=json)

```json
{
  "objectIdFieldName": "OBJECTID",
  "globalIdFieldName": "",
  "geometryType": "esriGeometryPoint",
  "spatialReference": { "wkid": 4326 },
  "fields": [
    { "name": "OBJECTID", "type": "esriFieldTypeOID", "alias": "OBJECTID" },
    ...
  ],
  "features": [
    {
      "attributes": { "OBJECTID": 1, ... },
      "geometry": { "x": -90.674766, "y": 40.458799 }
    }
  ]
}
```

### Camera Record Example

```json
{
  "attributes": {
    "OBJECTID": 1,
    "ImgPath": "http://travelmidwest.com/lmiga/showCamera.jsp?id=IL-IDOTD4-camera_162&direction=E",
    "CameraLocation": "US 136 (Jackson St.) at Johnson St. (#4162)",
    "CameraDirection": "E",
    "y": 40.458799,
    "x": -90.674766,
    "SnapShot": "https://cctv.travelmidwest.com/snapshots/IL-IDOTD4_4_McDonough_EB_US-136_4045880_-9067477_1_E.jpg",
    "WarningAge": false,
    "TooOld": false,
    "AgeInMinutes": 0
  },
  "geometry": { "x": -90.674766, "y": 40.458799 }
}
```

### Incident Record Example

```json
{
  "attributes": {
    "OBJECTID": 131315188,
    "TRAFFIC_ITEM_TYPE_DESC": "ROAD_CLOSURE",
    "START_TIME": 1774461449000,
    "END_TIME": 1774720649000,
    "CRITICALITY_DESC": "critical",
    "VERIFIED": true,
    "DESCRIPTION": "Closed.",
    "ROAD_CLOSED": true,
    "TRAFFIC_ITEM_DESCRIPTION": "Closed.",
    "ORIGIN": "-87.70287 41.26607",
    "Status": null,
    "FullClosure": null
  }
}
```

### RWIS Station Example

```json
{
  "attributes": {
    "OBJECTID": 1,
    "StationID": "MX9208",
    "Displayname": "IL D7 US 50 at Greendale",
    "Latitude": 38.62981,
    "Longitude": -88.698128,
    "Temp": 39,
    "Temperature": 44,
    "DewPoint": 39,
    "WindSpeed": 0,
    "WindGusts": 0,
    "WindDirection": 0,
    "RelativeHumidity": 82,
    "PrecipYesNo": 2,
    "PrecipIntensity": 3,
    "PrecipType": 3,
    "SurfaceCondition": "",
    "SurfaceTemp": "0",
    "PrecipitationDescription": null,
    "PrecipitationLevel": null,
    "ObsDateTime_Local": 1774622400000
  }
}
```

---

## Installation

No installation required. Requires Python 3.7+. No external dependencies.

```bash
# Download the client
curl -O https://your-host/idot_client.py

# Or copy it directly and run
python3 idot_client.py
```

---

## Quick Start

```python
from idot_client import IDOTClient

client = IDOTClient()

# --- Traffic Cameras ---
cameras = client.get_cameras(max_records=20)
for cam in cameras:
    print(f"{cam.location} ({cam.direction})")
    print(f"  Snapshot: {cam.snapshot_url}")
    print(f"  Age: {cam.age_minutes} minutes")

# Get all cameras near I-90 corridor
i90_cameras = client.get_cameras(
    where="CameraLocation LIKE '%I-90%'",
    exclude_old=True,
)

# --- Road Incidents ---
incidents = client.get_incidents()
critical = client.get_incidents(critical_only=True)
closures = client.get_incidents(incident_types=["ROAD_CLOSURE"])

# --- Construction Zones ---
zones = client.get_construction(district="1", county="COOK")

# --- Winter Road Conditions ---
conditions = client.get_winter_conditions()
non_clear = [c for c in conditions if c.condition != "Clear"]
print(f"{len(non_clear)} sections not clear")

# --- RWIS Weather Stations ---
stations = client.get_rwis_stations()
for s in stations:
    print(f"{s.display_name}: {s.temp_f}°F, wind {s.wind_speed_mph} mph")

# --- Dynamic Message Signs ---
signs = client.get_dynamic_message_signs(road_name="I-55", direction="NB")
for sign in signs:
    print(f"{sign.location}: {sign.message_line1}")

# --- Rest Areas ---
open_areas = client.get_rest_areas(open_only=True)
d1_areas = client.get_rest_areas(district=1)

# --- Waterway Ferries ---
ferries = client.get_waterway_ferries()

# --- GeoJSON output (for mapping) ---
geojson = client.get_cameras_geojson(max_records=100)

# --- Service health check ---
counts = client.get_service_counts()
print(counts)
```

---

## CLI Reference

```
python3 idot_client.py [command] [--where CLAUSE] [--max N] [--json]

Commands:
  demo          Run a full demo of all endpoints (default)
  cameras       List traffic cameras
  incidents     List active road incidents
  construction  List construction zones
  winter        List winter road conditions
  rwis          List RWIS weather station readings
  dms           List dynamic message sign messages
  rest_areas    List rest area statuses
  ferries       List waterway ferry statuses
  closures      List road closure events
  counts        Show record counts for all services

Options:
  --where CLAUSE  ArcGIS SQL WHERE filter (default: "1=1")
  --max N         Maximum records to return (default: 10)
  --json          Output raw JSON instead of formatted text
```

### CLI Examples

```bash
# Full demo
python3 idot_client.py

# Get 20 incidents as JSON
python3 idot_client.py incidents --max 20 --json

# Filter construction in Cook County
python3 idot_client.py construction --where "County='COOK'" --max 50

# Critical incidents only
python3 idot_client.py incidents --where "CRITICALITY_DESC='critical'" --max 25

# Northbound I-94 DMS signs
python3 idot_client.py dms --where "road_name='I-94' AND direction='NB'"

# Open rest areas in district 1
python3 idot_client.py rest_areas --where "district=1 AND status='Open'"

# Record counts for all services
python3 idot_client.py counts
```

---

## API Reference

### `IDOTClient(timeout=30, page_size=1000)`

Main client class. All methods return typed dataclass instances.

---

### `get_cameras(where, max_records, exclude_old) -> list[Camera]`

Returns traffic cameras with live snapshot URLs. ~3,603 records total, representing multiple viewing directions per physical camera.

**Camera fields:**

| Field | Type | Description |
|---|---|---|
| `object_id` | int | ArcGIS object ID |
| `camera_id` | str | Unique ID like `IL-IDOTD1-camera_100` |
| `location` | str | Intersection/road description |
| `direction` | str | Viewing direction: N, S, E, W |
| `latitude` | float | WGS84 latitude |
| `longitude` | float | WGS84 longitude |
| `snapshot_url` | str | Live JPEG image URL |
| `view_url` | str | Travel Midwest viewer URL |
| `age_minutes` | int | Minutes since last image update |
| `too_old` | bool | True if image is stale |
| `warning_age` | bool | True if approaching staleness threshold |

**Camera ID patterns:**

- `IL-IDOTD1-camera_NNN` — IDOT District 1 (Chicago/NE)
- `IL-IDOTD4-camera_NNN` — IDOT District 4 (Peoria area)
- `IL-LAKECOUNTY-NNNNN` — Lake County DOT
- `IL-IDOTD9-camera_NNN` — IDOT District 9

---

### `get_incidents(where, max_records, incident_types, critical_only) -> list[Incident]`

Active roadway incidents. ~600–700 records, updated in near real-time.

**Incident type values:** `ROAD_CLOSURE`, `ACCIDENT`, `CONGESTION`, `HAZARD`, `CONSTRUCTION`, `WEATHER`

**Criticality values:** `critical`, `major`, `minor`, `lowImpact`

---

### `get_construction(where, max_records, district, county) -> list[ConstructionZone]`

Active construction zones with contractor info, dates, and traffic impact details.

---

### `get_winter_conditions(where, max_records, district, condition) -> list[WinterRoadCondition]`

Winter road conditions for ~410 maintenance section segments across Illinois.

**Condition values:** `Clear`, `Wet`, `Slush`, `Packed Snow`, `Icy`, `Treated`, `Untreated`

---

### `get_rwis_stations(where, max_records) -> list[RWISStation]`

Current readings from 36 Roadway Weather Information System stations.

**RWIS fields include:** temperature (°F), dew point, wind speed/gusts/direction, relative humidity, surface condition, precipitation type/intensity.

**`PrecipType` codes:** 0=None, 1=Rain, 2=Snow, 3=No precipitation

---

### `get_dynamic_message_signs(where, max_records, road_name, direction) -> list[DynamicMessageSign]`

Current messages on 576 overhead DMS signs statewide (plus Iowa border signs). Each sign has up to 3 message lines and a rendered image URL.

---

### `get_rest_areas(where, open_only, district) -> list[RestArea]`

Status of 54 Illinois rest areas and welcome centers.

---

### `get_waterway_ferries() -> list[WaterwayFerry]`

Status of the 3 state-operated waterway ferry crossings.

---

### `get_road_closures(where, max_records) -> list[RoadClosure]`

Planned road closure events (construction-driven, distinct from emergency incidents).

---

### `get_unplanned_events(where, max_records) -> list[UnplannedEvent]`

Travel Midwest emergency/unplanned events (long-duration incidents not yet resolved).

---

### `get_cameras_geojson(where, max_records) -> dict`

Returns a standard GeoJSON FeatureCollection of camera points for use with Leaflet, Folium, etc.

---

### `get_service_counts() -> dict[str, int]`

Returns current record counts for all services. Useful for monitoring or polling.

---

## Filtering & Pagination

All `get_*` methods accept an ArcGIS SQL `where` parameter. Standard SQL comparison operators and `LIKE` are supported:

```python
# Cameras on I-90
client.get_cameras(where="CameraLocation LIKE '%I-90%'")

# Critical incidents after a date
client.get_incidents(where="START_TIME > 1774461449000")

# Construction in multiple counties
client.get_construction(where="County IN ('COOK', 'DUPAGE', 'LAKE')")

# RWIS with precipitation detected
client.get_rwis_stations(where="PrecipYesNo=1")
```

Pagination is handled automatically. The underlying `_paginate()` generator fetches pages of up to 1,000 records transparently.

To retrieve all records:
```python
all_cameras = client.get_cameras(max_records=0)  # 0 = no limit
```

---

## Camera Images

Camera snapshot URLs follow this pattern:
```
https://cctv.travelmidwest.com/snapshots/<encoded_location_string>_<direction>.jpg
```

Images are:
- Format: JPEG
- Typical size: 100–200 KB
- Refresh rate: approximately every 2 minutes
- Served with `Cache-Control: public, max-age=0, must-revalidate`
- No authentication required; no CORS restrictions (served from CDN)

The `TooOld` flag indicates a camera has not updated within the expected window. The `AgeInMinutes` field shows how long ago the last image was captured.

To download a snapshot image:
```python
import urllib.request

cam = client.get_cameras(max_records=1, exclude_old=True)[0]
urllib.request.urlretrieve(cam.snapshot_url, "camera.jpg")
```

---

## GeoJSON Support

All FeatureServer endpoints support GeoJSON output via `f=geojson`. The client exposes this for cameras:

```python
geojson = client.get_cameras_geojson(max_records=200)
# geojson["type"] == "FeatureCollection"
# geojson["features"][0]["geometry"]["type"] == "Point"
# geojson["features"][0]["geometry"]["coordinates"] == [lon, lat]
```

You can also build custom GeoJSON URLs directly:
```
GET https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/
    Illinois_Roadway_Incidents/FeatureServer/0/query
    ?where=1=1&outFields=*&f=geojson
```

---

## Districts

IDOT divides Illinois into 9 districts plus the Chicago region:

| District | Region |
|---|---|
| 1 | Chicago Metro (Cook, DuPage, Kane, Lake, McHenry, Will) |
| 2 | Dixon (NW Illinois) |
| 3 | Ottawa |
| 4 | Peoria |
| 5 | Paris (east-central) |
| 6 | Springfield |
| 7 | Effingham |
| 8 | Collinsville (St. Louis metro) |
| 9 | Carbondale (southern IL) |

Filter by district in queries:
```python
# Winter conditions in District 1 (Chicago)
client.get_winter_conditions(district="1")

# Construction in District 8 (St. Louis area)
client.get_construction(district="8")
```

---

## Notes & Limitations

**Rate Limiting:** No rate limits are documented or enforced, but IDOT's ArcGIS Online account is subject to Esri's fair-use policies. Avoid polling more frequently than necessary (recommend 30–60 second intervals for live data).

**Record Limits:** Each FeatureServer layer has a `maxRecordCount` of 1,000. The client paginates automatically, but very large datasets (cameras: 3,603) require multiple requests.

**Timestamps:** All date/time fields are Unix epoch milliseconds (UTC). The client converts them to Python `datetime` objects with UTC timezone. The `ObsDateTime_Local` field in RWIS data is labeled "local" but appears to actually be stored as UTC.

**Geometry:** All coordinates are WGS84 (EPSG:4326). The ArcGIS services use `spatialReference: { wkid: 4326 }`.

**Winter data availability:** The `Winter_Trouble_Spots1` and winter condition services may return zero records outside of winter season.

**Camera coverage:** The ~3,603 camera records represent multiple directions (N/S/E/W) per physical camera location. The physical camera count is approximately 900–1,200 locations.

**Travel Midwest cameras:** Cameras with IDs like `IL-LAKECOUNTY-*` are from county-level agencies (Lake County DOT) and have snapshot URLs from different CDN hosts.

**Not available:** No streaming video URLs were found. The system serves only JPEG snapshots. No IDOT-specific authentication tokens or API keys are required or used.
