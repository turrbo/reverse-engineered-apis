# KYTC GoKY Traffic Camera System - Reverse Engineering Notes & Python Client

Reverse-engineered from **https://goky.ky.gov** (Kentucky Transportation Cabinet GoKY traffic map).

---

## Overview

The GoKY application (`goky.ky.gov`) is a single-page app built on Google Maps, Firebase Firestore, and ArcGIS FeatureServer. It provides real-time traffic conditions across Kentucky including:

- Traffic cameras (statewide KYTC + Fayette County)
- Active incidents (crashes, hazards, work zones)
- Traffic speed segments
- Dynamic Message Signs (DMS / electronic road signs)
- Roadway Weather Information Stations (RWIS)
- Waze crowd-sourced events
- Truck parking and rest area status
- Snow & ice operations

**All data endpoints are publicly accessible with no authentication.**

---

## Reverse Engineering Methodology

### 1. HTML Source Analysis

The GoKY main page (`goky.ky.gov/`) loads a single JS bundle (`index.js`, ~245 KB minified). Key findings from the HTML:

```html
<script src="./index.js"></script>
<script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyDQEp-IWOnOoZtAH0SnMPfZnEMToDmMNcQ&..."></script>
```

### 2. JavaScript Bundle Analysis

The `index.js` bundle contains a plaintext configuration object (`ph`) with all service URLs hardcoded:

```javascript
ph = {
  cams: {
    fayette: {
      type: "fayette",
      url: "https://services1.arcgis.com/Mg7DLdfYcSWIaDnu/ArcGIS/rest/services/
            Traffic_Camera_Locations_Public_view/FeatureServer/0/query?..."
    },
    kytc: {
      type: "kytc",
      url: "https://services2.arcgis.com/CcI36Pduqd0OR4W9/ArcGIS/rest/services/
            trafficCamerasCur_Prd/FeatureServer/0/query?..."
    },
    rwis: {
      url: "https://api.objectspectrum.com/apps/vue/report:latest?token=<TOKEN>&..."
    }
  },
  firebase: {
    apiKey: "AIzaSyDQEp-IWOnOoZtAH0SnMPfZnEMToDmMNcQ",
    authDomain: "kytc-goky.firebaseapp.com",
    projectId: "kytc-goky",
    storageBucket: "kytc-goky.appspot.com",
    messagingSenderId: "911478978941",
    appId: "1:911478978941:web:b965a6c158ee5c4d17b414"
  }
}
```

The `tu()` async function loads camera data via `fetch(t.url)` and processes ArcGIS GeoJSON features. The `Sc(Zh, "realtime")` call subscribes to Firestore collection `realtime` for live event data.

### 3. Data Source Architecture

```
goky.ky.gov
├── ArcGIS FeatureServer (Esri hosted)
│   ├── services2.arcgis.com  → KYTC statewide cameras (255 cameras)
│   └── services1.arcgis.com  → Fayette County cameras (108 cameras)
├── Firebase Firestore (Google Cloud)
│   ├── Collection: "realtime"  → All live traffic events (~1,900+ docs)
│   └── Collection: "tweets"    → KYTC district social media posts
└── ObjectSpectrum API
    └── RWIS weather camera snapshots (embedded token in JS)
```

---

## API Endpoints

### Endpoint 1: KYTC Statewide Traffic Cameras

**URL:** `https://services2.arcgis.com/CcI36Pduqd0OR4W9/ArcGIS/rest/services/trafficCamerasCur_Prd/FeatureServer/0/query`

**Method:** GET
**Auth:** None
**Format:** ArcGIS REST API (pjson)

**Query Parameters:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| `where` | `1=1` | SQL WHERE clause |
| `outFields` | `name,description,snapshot,...` | Comma-separated field list |
| `returnGeometry` | `false` | Set `true` for geometry |
| `outSR` | `4326` | WGS84 coordinate system |
| `f` | `pjson` | Response format (JSON) |
| `resultRecordCount` | optional | Limit records |
| `resultOffset` | optional | Pagination offset |

**Available Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `OBJECTID` | int | ArcGIS object ID |
| `id` | int | Internal camera ID |
| `name` | string | CCTV ID (e.g. "CCTV05039") |
| `description` | string | Human-readable location |
| `snapshot` | string | URL to JPEG snapshot image |
| `status` | string | "Online", "Offline", or null |
| `state` | string | "Kentucky" or state name |
| `district` | int | KYTC district number (1-12) |
| `county` | string | County name |
| `highway` | string | Route (e.g. "I-71") |
| `milemarker` | float | Milepost |
| `direction` | string | "North-South", "East-West" |
| `latitude` | float | Decimal degrees (WGS84) |
| `longitude` | float | Decimal degrees (WGS84) |
| `updateTS` | int | Unix timestamp in milliseconds |

**Sample Response:**
```json
{
  "features": [
    {
      "attributes": {
        "name": "CCTV05039",
        "description": "I-71 at I-264",
        "snapshot": "https://www.trimarc.org/images/milestone/CCTV_05_71_0048.jpg",
        "status": "Online",
        "state": "Kentucky",
        "district": 5,
        "county": "Jefferson",
        "highway": "I-71",
        "milemarker": 4.8,
        "direction": "North-South",
        "latitude": 38.291639,
        "longitude": -85.650625,
        "updateTS": 1774580419000
      }
    }
  ]
}
```

**Camera Data Stats (live):**
- Total cameras: 255 (246 KY + 9 Indiana border cameras)
- Online: ~245
- Counties covered: 42 Kentucky counties
- Snapshot image server: `www.trimarc.org` (249), `pws.trafficwise.org` (6)

---

### Endpoint 2: Fayette County (Lexington) Cameras

**URL:** `https://services1.arcgis.com/Mg7DLdfYcSWIaDnu/ArcGIS/rest/services/Traffic_Camera_Locations_Public_view/FeatureServer/0/query`

**Method:** GET
**Auth:** None
**Format:** ArcGIS REST API (pjson)

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `location` | string | Human-readable intersection name |
| `still_url` | string | Wowza StreamLock thumbnail URL |

**Geometry:** Available (x/y in WGS84 when `outSR=4326`)

**Sample Response:**
```json
{
  "features": [
    {
      "attributes": {
        "location": "Alumni/New Circle",
        "still_url": "https://6855e4345af72.streamlock.net:1935/thumbnail?application=lexington-live&streamname=lex-cam-014.stream&fitmode=stretch&size=600x400"
      },
      "geometry": {
        "x": -84.46457,
        "y": 37.99517
      }
    }
  ]
}
```

**Camera Data Stats (live):**
- Total cameras: 108
- All in Fayette County (Lexington urban area)
- Snapshots served via Wowza StreamLock streaming server
- Stream name format: `lex-cam-NNN.stream`
- Snapshot dimensions: 600x400 (configurable via `size` param)

---

### Endpoint 3: Firebase Firestore REST API - Realtime Collection

**URL:** `https://firestore.googleapis.com/v1/projects/kytc-goky/databases/(default)/documents/realtime`

**Method:** GET
**Auth:** None (public Firestore rules allow read)
**Format:** Firestore REST API JSON

**Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `pageSize` | Documents per page (max ~300) |
| `pageToken` | Pagination token from previous response |

**Response structure:**
```json
{
  "documents": [ ... ],
  "nextPageToken": "AFTOeJ..."
}
```

Each document has Firestore-typed fields. The Python client handles deserialization.

**Top-level document fields:**

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Event type code (see table below) |
| `county` | string | Kentucky county name |
| `location` | GeoPoint | lat/lng of event |
| `display` | map | Display fields (route, mile point, speeds, etc.) |
| `source` | map | Raw source data (IDs, descriptions, timestamps) |

**Event Types:**

| Type Code | Label | Count (typical) | Description |
|-----------|-------|-----------------|-------------|
| `spd` | Traffic Speed | ~1,500 | HERE-sourced speed segments |
| `wkzn` | Work Zone | ~100-200 | Active construction zones |
| `dms` | Digital Sign | ~90 | DMS electronic sign messages |
| `rwis` | Roadway Wx | ~48 | Weather station sensor readings |
| `rsta` | Rest Area | ~28 | Rest area status |
| `wzwk` | Waze Work Zone | ~20 | Waze-reported work zone |
| `wztrfc` | Waze Traffic | ~20 | Waze traffic jam |
| `trkprk` | Truck Parking | ~13 | Truck parking availability |
| `wzcrsh` | Waze Crash | ~5-15 | Waze-reported crash |
| `hzrd` | Hazard | varies | Road hazard alert |
| `crsh` | Crash | varies | KYTC/TRIMARC crash incident |
| `wzhzrd` | Waze Hazard | varies | Waze-reported hazard |
| `snic` | Snow & Ice | seasonal | Snow & ice operations |
| `fry` | Ferry | rare | Ferry status |

**Speed segment `display` fields:**
```
Route           - "I-264"
Road_Name       - "I-264 NC"
Mile_Point      - 12
Current_Speed   - 17 (mph)
Historic_Speed  - 55 (mph)
Source_Type     - "Heavy Congestion" | "Light Congestion" | "Unknown"
```

**Incident `source` fields:**
```
id          - "TRIMARC-283805"
type        - "KYTC" | "Waze" | "HERE" | "DMS"
description - Free-text description
published   - ISO 8601 timestamp
```

**Sample Speed Document (Firestore REST):**
```json
{
  "name": "projects/kytc-goky/databases/(default)/documents/realtime/+2_m0FaxBc3...",
  "fields": {
    "type": {"stringValue": "spd"},
    "county": {"stringValue": "Jefferson"},
    "location": {"geoPointValue": {"latitude": 38.190307, "longitude": -85.731247}},
    "display": {
      "mapValue": {
        "fields": {
          "Route": {"stringValue": "I-264"},
          "Road_Name": {"stringValue": "I-264 NC"},
          "Mile_Point": {"integerValue": "12"},
          "Current_Speed": {"integerValue": "17"},
          "Historic_Speed": {"integerValue": "55"},
          "Source_Type": {"stringValue": "Heavy Congestion"}
        }
      }
    },
    "source": {
      "mapValue": {
        "fields": {
          "id": {"stringValue": "121N04294"},
          "type": {"stringValue": "HERE"}
        }
      }
    }
  }
}
```

---

### Endpoint 4: Firebase Firestore - Tweets Collection

**URL:** `https://firestore.googleapis.com/v1/projects/kytc-goky/databases/(default)/documents/tweets`

**Method:** GET
**Auth:** None

Contains KYTC district social media/tweet messages keyed by district ID (`KYTCDistrict1` through `KYTCDistrict12`). Used for Snow & Ice operation updates.

**Note:** This collection may be empty outside of winter storm events.

---

### Endpoint 5: ObjectSpectrum RWIS Camera Viewer

**URL:** `https://api.objectspectrum.com/apps/vue/report:latest?token=c35886bf-9b98-4be0-b2ec-7781fdf1d90d&timezone=America/New_York&scope=vue_kdt1&camera_key=<KEY>`

**Method:** GET
**Auth:** Embedded token (public, from JS bundle)

Returns an HTML page (not JSON) with RWIS weather camera snapshot data. The `camera_key` parameter selects a specific RWIS station. Camera keys are found in Firestore RWIS documents under `source.cameraKey`.

---

## Python Client

### Installation

No external dependencies. Requires Python 3.8+.

```bash
# No installation needed - uses stdlib only
python3 kytc_client.py
```

### Quick Start

```python
from kytc_client import (
    get_kytc_cameras,
    get_fayette_cameras,
    get_all_cameras,
    get_realtime_feed,
    get_incidents,
    get_waze_events,
    get_speed_data,
    get_dms_signs,
    get_rwis_stations,
    get_truck_parking,
    FeedType,
    summarize_cameras,
    summarize_feed,
)
```

### Camera Examples

```python
# All KYTC statewide cameras
cameras = get_kytc_cameras()
print(f"Total: {len(cameras)} cameras")

# Filter by county
jefferson = get_kytc_cameras(county="Jefferson")
print(f"Jefferson County: {len(jefferson)} cameras")

# Online cameras only
online = get_kytc_cameras(status="Online")

# Kentucky-only (exclude Indiana border cameras)
ky_only = get_kytc_cameras(state="Kentucky")

# Fayette County (Lexington)
fayette = get_fayette_cameras()
print(f"Lexington: {len(fayette)} cameras")

# Both sources combined
all_cams = get_all_cameras(ky_only=True)
print(f"Total KY cameras: {len(all_cams)}")

# Access camera properties
for cam in online[:5]:
    print(cam.name, cam.description, cam.county)
    print("  Snapshot:", cam.snapshot_url)
    print("  Coordinates:", cam.latitude, cam.longitude)
    print("  Highway:", cam.highway, "MP", cam.milemarker)

# Get camera statistics
summary = summarize_cameras(cameras)
print(f"Online: {summary['online']}, Offline: {summary['offline']}")
print("By county:", summary['by_county'])
```

### Real-time Feed Examples

```python
# Get all live events
events = get_realtime_feed()
summary = summarize_feed(events)
print(f"Total events: {summary['total']}")
print("By type:", summary['by_type'])

# Incidents only (crashes + hazards + work zones)
incidents = get_incidents()
for evt in incidents:
    print(f"{evt.event_type}: {evt.county} - {evt.road_name} MP {evt.mile_point}")
    print(f"  Description: {evt.description}")
    print(f"  Published: {evt.published}")

# Jefferson County incidents
jeff_incidents = get_incidents(county="Jefferson")

# Waze crowd-sourced events
waze = get_waze_events()
print(f"Waze events: {len(waze)}")

# Traffic speeds
speeds = get_speed_data(county="Fayette")
for seg in speeds:
    curr = seg.display.get("Current_Speed")
    hist = seg.display.get("Historic_Speed")
    congestion = seg.display.get("Source_Type")
    print(f"{seg.road_name} MP {seg.mile_point}: {curr}/{hist} mph ({congestion})")

# DMS electronic signs
signs = get_dms_signs()
for sign in signs:
    print(f"{sign.source.get('id')}: {sign.source.get('message', 'no message')}")

# RWIS weather stations
rwis = get_rwis_stations()
for station in rwis:
    print(f"{station.county}: Air {station.display.get('Air_Temp')}, "
          f"Pavement {station.display.get('Pavement_Temp')}")

# Truck parking
parking = get_truck_parking()
for p in parking:
    status = "OPEN" if p.source.get("open") else "CLOSED"
    print(f"{status}: {p.source.get('description')}")

# Custom type filter - work zones statewide
workzones = get_realtime_feed(event_types=["wkzn"])
print(f"Active work zones: {len(workzones)}")

# Multiple types
all_incidents = get_realtime_feed(event_types=["crsh", "hzrd", "wkzn", "wzcrsh"])
```

### Advanced ArcGIS Queries

```python
from kytc_client import query_arcgis, ARCGIS_KYTC_URL

# Raw ArcGIS query with custom WHERE clause
features = query_arcgis(
    service_url=ARCGIS_KYTC_URL.replace("/query", ""),
    where="county='Jefferson' AND status='Online'",
    out_fields="name,description,snapshot,highway,milemarker",
)

for feat in features:
    attrs = feat["attributes"]
    print(attrs["name"], attrs["description"])
```

### Raw Firestore Access

```python
import urllib.request
import json

# Paginate through all realtime documents
page_token = None
all_docs = []
base_url = "https://firestore.googleapis.com/v1/projects/kytc-goky/databases/(default)/documents/realtime"

while True:
    url = base_url + "?pageSize=300"
    if page_token:
        url += f"&pageToken={page_token}"
    with urllib.request.urlopen(url) as resp:
        data = json.load(resp)
    all_docs.extend(data.get("documents", []))
    page_token = data.get("nextPageToken")
    if not page_token:
        break

print(f"Total documents: {len(all_docs)}")
```

---

## Data Relationships

```
RWIS Station (Firestore "rwis" doc)
  └── source.cameraKey  →  ObjectSpectrum URL (weather camera snapshot)
  └── source.id         →  Station identifier
  └── source.imageUrl   →  Direct snapshot image URL

KYTC Camera (ArcGIS)
  └── name (e.g. "CCTV05039")  →  TRIMARC CCTV ID
  └── snapshot                 →  JPEG image at trimarc.org/images/milestone/

Crash/Hazard (Firestore "crsh"/"hzrd" doc)
  └── source.description  →  "May be viewed on CCTV_05_64_0214"  (links to camera name)
  └── source.id           →  "TRIMARC-283805"

Snow & Ice (Firestore "snic" doc)
  └── county              →  KY county
  └── tweet collection    →  KYTCDistrict1..12  (winter ops updates)
```

---

## Technical Notes

### ArcGIS FeatureServer
- Provider: Esri ArcGIS Online (hosted)
- KYTC org ID: `CcI36Pduqd0OR4W9` (trafficCamerasCur_Prd)
- Fayette org ID: `Mg7DLdfYcSWIaDnu` (Traffic_Camera_Locations_Public_view)
- Coordinate system: WGS84 (EPSG:4326)
- Max record count: 1000 per query (use `resultOffset` for pagination)
- Supports: WHERE filters, field selection, geometry return, spatial queries

### Firebase Firestore
- Project ID: `kytc-goky`
- Region: inferred US (standard Firebase)
- REST API base: `https://firestore.googleapis.com/v1/projects/kytc-goky/databases/(default)/documents/`
- Security rules: public read (no auth token required)
- The web app uses Firebase SDK `onSnapshot()` for real-time updates; the REST API requires polling
- Typical document count: ~1,900-2,000 across all types
- Page size limit: ~300 documents per request

### Snapshot Image Servers
- `www.trimarc.org/images/milestone/CCTV_*.jpg` - KYTC/TRIMARC managed cameras
- `www.trimarc.org/images/snapshots/IND_CCTV*.jpg` - Indiana border cameras
- `pws.trafficwise.org/pullover/*.jpg` - TrafficWise partner cameras
- `*.streamlock.net:1935/thumbnail?...` - Wowza live stream thumbnails (Fayette)

### Rate Limiting
No rate limiting has been observed on any endpoint. These are production public APIs. Be respectful and cache responses appropriately.

### Update Frequency
- ArcGIS camera data: updated every ~5-15 minutes (based on `updateTS` field)
- Firestore realtime: continuously updated (near-real-time events)
- RWIS weather: ~15 minute intervals typical for weather stations

---

## Credentials & Keys Found in JS Bundle

All of these are public/embedded in the client-side JavaScript:

| Key | Value | Notes |
|-----|-------|-------|
| Google Maps API Key | `AIzaSyDQEp-IWOnOoZtAH0SnMPfZnEMToDmMNcQ` | Same as Firebase `apiKey` |
| Firebase App ID | `1:911478978941:web:b965a6c158ee5c4d17b414` | GoKY web app |
| Firebase Measurement ID | `G-MJSX391PZT` | Google Analytics |
| Google Analytics ID | `G-K7E4W83L9R` | Also in main HTML |
| ObjectSpectrum Token | `c35886bf-9b98-4be0-b2ec-7781fdf1d90d` | RWIS camera viewer |

Note: Firebase `apiKey` for client-side apps is a public identifier, not a secret. Access is controlled by Firestore security rules (which allow public reads).

---

## File Structure

```
outputs/
├── kytc_client.py     # Python client (stdlib only)
└── kytc_README.md     # This file
```

---

## Live Test Results (2026-03-27)

Verified against live production endpoints:

| Endpoint | Status | Records |
|----------|--------|---------|
| KYTC ArcGIS cameras | OK | 255 cameras |
| Fayette ArcGIS cameras | OK | 108 cameras |
| Firestore realtime | OK | 1,940 documents |
| Speed segments | OK | 1,501 |
| Work zones | OK | 126 |
| DMS signs | OK | 91 |
| RWIS stations | OK | 48 |
| Active incidents | OK | 14 (crsh+hzrd) |
| Truck parking | OK | 13 locations |
