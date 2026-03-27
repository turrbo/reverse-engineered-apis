# WSDOT Highway Camera Client

Reverse-engineered Python client for the Washington State DOT (WSDOT) camera system.

---

## Summary of Findings

WSDOT exposes camera data through multiple tiers:

| Tier | Auth Required | Cameras | Data |
|------|--------------|---------|------|
| RSS feed | None | 1658 | title, image_url, last_updated |
| KML feed | None | 1658 | title, image_url, lat/lon, region |
| REST API | AccessCode | 1658 | all fields + milepost + road name + filtering |
| Images | None | 1658 | Direct JPEG fetch from `images.wsdot.wa.gov` |

**The camera images themselves are entirely public** — no authentication is needed to download any JPEG.

---

## API Endpoints

### Public (No Authentication)

| Endpoint | URL |
|----------|-----|
| RSS Feed | `https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/rss.aspx` |
| KML Feed | `https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/kml.aspx` |
| Camera Images | `https://images.wsdot.wa.gov/{region}/{route}vc{milepost}.jpg` |

### REST API (Requires AccessCode)

Base URL: `https://www.wsdot.wa.gov/Traffic/api/HighwayCameras/HighwayCamerasREST.svc/`

| Method | Parameters | Description |
|--------|-----------|-------------|
| `GetCamerasAsJson` | `AccessCode` | All cameras |
| `GetCameraAsJson` | `AccessCode`, `CameraID` | Single camera by ID |
| `SearchCamerasAsJson` | `AccessCode`, `StateRoute`, `Region`, `StartingMilepost`, `EndingMilepost` | Filter cameras |
| `GetCamerasAsXml` | `AccessCode` | All cameras (XML) |
| `SearchCamerasAsXML` | `AccessCode`, `StateRoute`, `Region`, `StartingMilepost`, `EndingMilepost` | Filter (XML) |

All endpoints support JSONP via `?callback={fn}`.

### Mountain Pass Conditions REST API (Requires AccessCode)

Base URL: `https://www.wsdot.wa.gov/Traffic/api/MountainPassConditions/MountainPassConditionsREST.svc/`

| Method | Parameters | Description |
|--------|-----------|-------------|
| `GetMountainPassConditionsAsJson` | `AccessCode` | All pass conditions |
| `GetMountainPassConditionAsJon` | `AccessCode`, `PassConditionID` | Single pass |

---

## Image URL Pattern

Most highway cameras follow a predictable naming scheme:

```
https://images.wsdot.wa.gov/{region}/{route_3digit}vc{milepost_5digit}.jpg
```

Where:
- `{region}` = lowercase WSDOT region code (see table below)
- `{route_3digit}` = zero-padded 3-digit state route number
- `vc` = literal "vc" (video camera)
- `{milepost_5digit}` = milepost × 100, zero-padded to 5 digits

**Examples:**

| URL | Route | Region | Milepost |
|-----|-------|--------|----------|
| `https://images.wsdot.wa.gov/sc/090vc05200.jpg` | I-90 | SC | 52.00 |
| `https://images.wsdot.wa.gov/nc/002vc06430.jpg` | US-2 | NC | 64.30 |
| `https://images.wsdot.wa.gov/nw/005vc19389.jpg` | I-5 | NW | 193.89 |
| `https://images.wsdot.wa.gov/nc/097vc16375.jpg` | US-97 | NC | 163.75 |
| `https://images.wsdot.wa.gov/nw/405vc00034.jpg` | SR-405 | NW | 0.34 |

**Special cases** (do not follow the pattern):
- Ferry terminals: `https://images.wsdot.wa.gov/wsf/{terminal}/{name}.jpg`
- Spokane area: `https://images.wsdot.wa.gov/spokane/wsdot_{route}_{milepost}_{desc}.jpg`
- Airports: `https://images.wsdot.wa.gov/airports/{name}.jpg`
- Road weather: `https://images.wsdot.wa.gov/rweather/{name}.jpg`
- Third-party cameras: Various external URLs (TripCheck Oregon, Seattle DOT, webcam.io, etc.)

---

## Region Codes

| Code | Name | Major Routes |
|------|------|-------------|
| `er` | Eastern Region | I-90 (east), US-2 (east), US-395, SR-20 (east) |
| `nc` | North Central Region | US-2 Stevens Pass, SR-20 North Cascades Hwy, US-97 |
| `nw` | Northwest Region | I-5 (Seattle area), I-405, SR-520, SR-99, SR-522 |
| `ol` | Olympic Region | US-101 (Olympic Peninsula), Hood Canal |
| `os` | Olympic/SW Region | US-101 south |
| `sc` | South Central Region | I-90 (Snoqualmie Pass), I-82, US-12, SR-410 |
| `sw` | Southwest Region | I-5 (SW WA), SR-14, US-830 |
| `wa` | Airport Cameras | Statewide airport/aviation cameras |
| `wsf` | WA State Ferries | Ferry terminal cameras |

---

## Camera Count by Region (as of March 2026)

| Region | Count |
|--------|-------|
| NW (Northwest) | 767 |
| SW (Southwest) | 215 |
| OL (Olympic) | 194 |
| ER (Eastern) | 160 |
| WA (Airports) | 111 |
| OS (Olympic/SW) | 66 |
| NC (North Central) | 63 |
| SC (South Central) | 82 |
| **Total** | **1658** |

---

## Camera Data Schema

```json
{
  "CameraID": 1100,
  "Title": "I-90 at MP 52: Snoqualmie Summit",
  "Description": "...",
  "Region": "SC",
  "ImageURL": "https://images.wsdot.wa.gov/sc/090VC05200.jpg",
  "ImageWidth": 320,
  "ImageHeight": 240,
  "IsActive": true,
  "CameraOwner": "WSDOT",
  "OwnerURL": "",
  "SortOrder": 0,
  "DisplayLatitude": 47.428397,
  "DisplayLongitude": -121.419659,
  "CameraLocation": {
    "Description": "...",
    "Direction": "Both",
    "Latitude": 47.428397,
    "Longitude": -121.419659,
    "MilePost": 52.0,
    "RoadName": "I-90"
  }
}
```

## Mountain Pass Schema

```json
{
  "MountainPassId": 1,
  "MountainPassName": "Snoqualmie Pass",
  "RoadCondition": "Wet",
  "WeatherCondition": "Cloudy",
  "TemperatureInFahrenheit": 34,
  "ElevationInFeet": 3022,
  "Latitude": 47.4242,
  "Longitude": -121.4119,
  "TravelAdvisoryActive": false,
  "RestrictionOne": {
    "RestrictionText": "Traction tires required",
    "TravelDirection": "Eastbound"
  },
  "RestrictionTwo": {
    "RestrictionText": "Traction tires required",
    "TravelDirection": "Westbound"
  },
  "DateUpdated": "2026-03-27T08:00:00"
}
```

---

## Usage

### No AccessCode (Public Data)

```python
from wsdot_cams_client import WSDOTCameraClient

client = WSDOTCameraClient()

# Get all 1658 cameras
cameras = client.get_all_cameras_public()
print(f"Total: {len(cameras)} cameras")

# Snoqualmie Pass (I-90 MP ~45-62)
sq_cams = client.get_snoqualmie_pass_cameras()
for c in sq_cams:
    print(f"{c.title}: {c.image_url}")

# Stevens Pass (US-2 MP ~62-65)
st_cams = client.get_stevens_pass_cameras()

# North Cascades Highway (SR-20)
nc_cams = client.get_north_cascades_cameras()

# WSF ferry terminals
ferry_cams = client.get_ferry_cameras()

# Bounding box search (e.g., Seattle metro area)
seattle_cams = client.get_cameras_by_bbox(
    min_lat=47.4, max_lat=47.8,
    min_lon=-122.5, max_lon=-122.0
)

# Download a camera image
img_bytes = client.fetch_camera_image(sq_cams[0])
with open("snoqualmie.jpg", "wb") as f:
    f.write(img_bytes)

# Export to GeoJSON
geojson = client.cameras_to_geojson(cameras)

# Export to CSV
rows = client.cameras_to_csv_rows(cameras)
```

### With AccessCode (Full REST API)

```python
from wsdot_cams_client import WSDOTCameraClient

client = WSDOTCameraClient(access_code="YOUR_ACCESS_CODE_HERE")

# All cameras (full metadata)
cameras = client.get_all_cameras()

# Single camera
cam = client.get_camera(camera_id=1100)

# Filter by route + milepost range
snoqualmie = client.search_cameras(
    state_route="090",          # I-90
    starting_milepost=45.0,
    ending_milepost=62.0,
)

# Filter by region
nw_cameras = client.search_cameras(region="NW")

# All I-5 cameras
i5_cameras = client.search_cameras(state_route="005")

# Mountain pass conditions
passes = client.get_all_pass_conditions()
for p in passes:
    print(f"{p.name}: {p.road_condition}, {p.temperature_f}°F")

# Single pass (1=Snoqualmie, 2=Stevens, 3=White, 4=Cayuse, 5=Chinook)
snq_pass = client.get_pass_condition(pass_id=1)
```

### Direct Image URL Builder

```python
from wsdot_cams_client import WSDOTCameraClient

client = WSDOTCameraClient()

# Build URL without needing camera metadata
url = client.build_image_url(region="sc", route_number=90, milepost=52.0)
# Returns: https://images.wsdot.wa.gov/sc/090vc05200.jpg

# Fetch it directly
from wsdot_cams_client import fetch_image
img = fetch_image(url)
```

---

## Key Mountain Pass Cameras

### Snoqualmie Pass (I-90, SC region)

| Camera ID | Title | Image URL |
|-----------|-------|-----------|
| 9425 | I-90 MP 33.2: North Bend | `sc/090VC03326.jpg` |
| 9029 | I-90 MP 46.8: Denny Creek | `sc/090VC04680.jpg` |
| 9426 | I-90 MP 48.1: Asahel Curtis | `sc/090VC04810.jpg` |
| 1099 | I-90 MP 51.3: Franklin Falls | `sc/090VC05130.jpg` |
| **1100** | **I-90 MP 52: Snoqualmie Summit** | **`sc/090VC05200.jpg`** |
| 9428 | I-90 MP 53.4: East Snoqualmie Summit | `sc/090VC05347.jpg` |
| 1102 | I-90 MP 55.1: Hyak | `sc/090VC05517.jpg` |
| 9914 | I-90 MP 58.2: Avalanche Bridge | `sc/090vc05820.jpg` |

### Stevens Pass (US-2, NC region)

| Camera ID | Title | Image URL |
|-----------|-------|-----------|
| 9145 | US 2 MP 61.9: Old Faithful Avalanche Zone | `nc/002vc06190.jpg` |
| 9437 | US 2 MP 63: Big Windy | `nc/002vc06300.jpg` |
| **8063** | **US 2 MP 64.3: West Stevens Pass** | **`nc/002vc06430.jpg`** |
| **8062** | **US 2 MP 64.6: East Stevens Pass** | **`nc/002vc06458.jpg`** |
| 9718 | US 2 MP 84.5: Coles Corner West | `nc/002vc08456.jpg` |

### North Cascades Highway (SR-20, NC region)

SR-20 cameras are in the `nc` region folder. The highway is typically closed November–April.

Key cameras:
- `nc/020vc19255.jpg` — SR-20 MP 192.55
- `nc/020vc21450.jpg` — SR-20 MP 214.50 (Ross Lake area)
- `nc/020vc28872.jpg` — SR-20 MP 288.72

---

## Other WSDOT Traveler APIs

All require AccessCode registration. Base: `https://www.wsdot.wa.gov/Traffic/api/`

| API | REST Help URL |
|-----|---------------|
| Highway Alerts | `/HighwayAlerts/HighwayAlertsREST.svc/Help` |
| Traffic Flow | `/TrafficFlow/TrafficFlowREST.svc/Help` |
| Travel Times | `/TravelTimes/TravelTimesREST.svc/Help` |
| Border Crossings | `/BorderCrossings/BorderCrossingsREST.svc/Help` |
| Weather Information | `/WeatherInformation/WeatherInformationREST.svc/Help` |
| Weather Stations | `/WeatherStations/WeatherStationsREST.svc/Help` |
| CV Restrictions | `/CVRestrictions/CVRestrictionsREST.svc/Help` |
| Toll Rates | `/TollRates/TollRatesREST.svc/Help` |
| Bridge Clearances | `/Bridges/ClearanceREST.svc/Help` |

`GetEventCategoriesAsJson` on the HighwayAlerts API works **without** an AccessCode:
```
GET https://www.wsdot.wa.gov/Traffic/api/HighwayAlerts/HighwayAlertsREST.svc/GetEventCategoriesAsJson
```
Returns the full list of alert category names (accidents, weather, construction, etc.).

---

## AccessCode Registration

1. Visit: https://www.wsdot.wa.gov/Traffic/api/
2. Click "Register" or the AccessCode request link
3. Provide name, organization, intended use
4. Receive free AccessCode by email

The AccessCode is required only for the REST API endpoints. All public feeds (RSS, KML) and all camera images work without any key.

---

## Notes

- Images refresh roughly every 1–5 minutes depending on camera type
- `Last-Modified` header on images reflects the latest capture time
- Image sizes vary: typical highway cameras are 320×240 or 640×480 JPEG
- Some cameras are owned by third parties (TripCheck/ODOT, Seattle SDOT, webcam.io) and WSDOT links to their images
- The `WA` region folder contains ~111 aviation/airport cameras statewide
- WSDOT image server: `images.wsdot.wa.gov` (Microsoft IIS / ASP.NET)
- Image filenames are case-insensitive on the server (`090VC05200.jpg` == `090vc05200.jpg`)
