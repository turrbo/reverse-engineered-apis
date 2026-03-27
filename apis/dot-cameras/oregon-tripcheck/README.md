# Oregon TripCheck API — Reverse-Engineering Notes & Python Client

> **Disclaimer**: This is an unofficial reverse-engineered client.
> All data belongs to Oregon DOT (ODOT) / TripCheck.
> Respect the system — don't poll more frequently than the cache intervals shown below.

---

## Discovery Methodology

1. Loaded `https://tripcheck.com/` and extracted all `<script src="…">` references.
2. Fetched and decompiled `/Scripts/map/roadconditions.min.js` — the central layer registry that maps layer names to data-feed URLs and refresh intervals.
3. Fetched every template file in `/Scripts/map/templates/*.min.js` to understand field schemas and data types.
4. Directly fetched each `*.js` data feed, inspected the EsriJSON FeatureSet structure, and documented all fields.
5. Verified image and video URL patterns by issuing `HEAD` requests against live URLs.
6. Parsed `/DynamicReports/Report/Cameras/0` HTML to confirm the camera image URL pattern (`/roadcams/cams/{filename}`).
7. Inspected the ODOT Azure API Management portal at `https://apiportal.odot.state.or.us/` to document the formal subscription-key API.

---

## Unique Feature: RWIS + Camera Co-location

TripCheck is uniquely valuable because ODOT's **221+ RWIS automated weather stations** are
deployed along the same highway corridors as **1,120+ road cameras**. This co-location means:

- A single data pull can return both a live camera snapshot **and** current road/weather readings
  (air temp, road surface temp, wind speed, precipitation, visibility)
- Weather conditions can be correlated with what the camera sees — e.g., snowy scene
  at Mt. Hood camera + RWIS shows -2°F road temp and freezing rain

```python
# Example: get RWIS stations with a camera within 1 km
pairs = client.get_rwis_with_nearby_cameras(max_distance_km=1.0)
for pair in pairs:
    ws = pair["rwis"]
    cam = pair["nearest_camera"]
    print(f"{ws.tripcheck_name}: temp={ws.curr_temp}  road={ws.road_temp}")
    print(f"  Camera: {cam.title} — {cam.image_url}")

# Example: full highway snapshot for I-84
for item in client.get_highway_snapshot("I-84"):
    cam = item["camera"]
    ws = item["rwis"]   # None if no RWIS within 2 km
    weather = f"{ws.curr_temp} road={ws.road_temp}" if ws else "no nearby RWIS"
    print(f"{cam.title}: {weather}")
    print(f"  {cam.image_url}")
```

---

## Architecture Overview

TripCheck is an ASP.NET MVC 5 application backed by ODOT's TOCS (Traffic Operations Center System).
The interactive map uses the **Esri JavaScript API (Dojo-based)** and fetches data as **EsriJSON FeatureSets** served as plain `.js` files.

```
Browser
  └── ESRI JS Map
       ├── /Basemaps/Pseudo.MapServer/…         (ArcGIS tiled basemaps)
       ├── /Scripts/map/data/*.js                (live data feeds – EsriJSON)
       └── /RoadCams/cams/*.jpg                  (camera JPEG snapshots)
                                     ↕ video
              ie.trafficland.com/v1.0/<id>/…     (TrafficLand CDN, per-token)
```

---

## Base URLs

| Resource | URL |
|---|---|
| Site root | `https://tripcheck.com` |
| Data feeds | `https://tripcheck.com/Scripts/map/data/<name>.js` |
| Camera images | `https://tripcheck.com/RoadCams/cams/<filename>` |
| Last Daylight Images (LDI) | `https://tripcheck.com/RoadCams/cams/camsLDI/<filename>` |
| Video stills (TrafficLand) | `http://ie.trafficland.com/v1.0/<webid>/{full\|half}?system=oregondot&pubtoken=<token>` |

---

## Data Feeds — Complete Inventory

All feeds accept `GET` requests with no authentication.
Append `?dt=<unix_ms>` to bust the server-side cache (the site does this itself).

| Key | Path | Refresh | Geometry | Notes |
|---|---|---|---|---|
| `cameras` | `/Scripts/map/data/cctvinventory.js` | 24 h | Point | All ODOT road cameras |
| `camera_video` | `/Scripts/map/data/TrafficVideo.js` | 24 h | — | Live-stream metadata + per-camera pubtoken |
| `road_weather` | `/Scripts/map/data/rw.js` | 15 min | Point | Crew-submitted conditions, chain laws, snow zones |
| `rwis` | `/Scripts/map/data/RWIS.js` | 2 min | Point | Automated weather station readings |
| `rw_trucking` | `/Scripts/map/data/RWTrucking.js` | 15 min | Point | Commercial vehicle restrictions |
| `events_points` | `/Scripts/map/data/EVENT.js` | 2 min | Point | Construction & planned events |
| `events_lines` | `/Scripts/map/data/EVENTLine.js` | 2 min | Polyline | Event extents on map |
| `incidents_points` | `/Scripts/map/data/INCD.js` | 2 min | Point | Active traffic incidents |
| `incidents_lines` | `/Scripts/map/data/INCDLine.js` | 2 min | Polyline | Incident extents |
| `cie_endpoints` | `/Scripts/map/data/CieEndPoint.js` | 2 min | Point | Critical incident event end-points |
| `cie_lines` | `/Scripts/map/data/CieLine.js` | 2 min | Polyline | Critical incident event lines |
| `tle_points` | `/Scripts/map/data/Tlev2-Points.js` | 2 min | Point | Local travel events (municipalities) |
| `tle_lines` | `/Scripts/map/data/Tlev2-Lines.js` | 2 min | Polyline | Local event extents |
| `travel_times` | `/Scripts/map/data/traveltime.js` | 2 min | Point | Portland-area travel time segments |
| `cvr_links` | `/Scripts/map/data/LINK.js` | 2 min | Point | Commercial vehicle restriction link icons |
| `alerts` | `/Scripts/map/data/ALRT.js` | 2 min | Polygon | Statewide travel alerts (bounding polygons) |
| `parking` | `/Scripts/map/data/mfparking.js` | 2 min | Point | Multnomah Falls parking occupancy |
| `waze_alerts` | `/Scripts/map/data/wazeAlerts.js` | 2 min | Point | Crowd-sourced Waze incident alerts |
| `waze_jams` | `/Scripts/map/data/wazeJams.js` | 2 min | Polyline | Crowd-sourced Waze traffic jams |
| `bridge_lifts` | `/Scripts/map/data/multBridge.js` | 2 min | Point | Multnomah-area bridge lift status |

---

## EsriJSON FeatureSet Format

Every data feed returns the same envelope:

```json
{
  "fields": [
    { "name": "fieldName", "alias": "Human Label", "type": "esriFieldTypeString", "length": 255 }
  ],
  "geometryType": "esriGeometryPoint",
  "spatialReference": { "wkid": 3857 },
  "features": [
    {
      "attributes": { … },
      "geometry": { "x": -13669052.7, "y": 5697265.6 }
    }
  ]
}
```

**Coordinate system**: EPSG:3857 (Web Mercator) for geometry.
Lat/long in WGS-84 are also included as separate attribute fields on most feeds.

---

## Field Schemas by Feed

### cameras — `/Scripts/map/data/cctvinventory.js`

| Field | Type | Notes |
|---|---|---|
| `cameraId` | Integer | Unique camera ID |
| `publishedImageId` | Integer | Part of the image filename |
| `filename` | String | JPEG filename, e.g. `AstoriaUS101MeglerBrNB_pid392.jpg` |
| `iconType` | Integer | Always 1 |
| `latitude` | Double | WGS-84 |
| `longitude` | Double | WGS-84 |
| `route` | String | Highway route code, e.g. `US101`, `I-205` |
| `title` | String | Human-readable location name |
| `videoId` | Integer | 0 = no video; >0 = trafficland.com webid |

**Camera image URL pattern**:
```
https://tripcheck.com/RoadCams/cams/{filename}?rand={timestamp_ms}
```

**Last Daylight Image (LDI) URL pattern**:
```
https://tripcheck.com/RoadCams/cams/camsLDI/{filename}?rand={timestamp_ms}
```

---

### camera_video — `/Scripts/map/data/TrafficVideo.js`

```json
{
  "cameras": [
    {
      "webid": 5419,
      "name": "ORE-217 @ Allen Blvd",
      "orientation": "NORTH",
      "tempdis": "true",
      "refreshRate": 2000,
      "cityCode": "PDX",
      "provider": "Oregon DOT",
      "location": { "longitude": -122.791452, "latitude": 45.479583, "zipCode": 97005 },
      "halfimage": "http://ie.trafficland.com/v1.0/5419/half?system=oregondot&pubtoken=<token>&refreshRate=2000",
      "fullimage": "http://ie.trafficland.com/v1.0/5419/full?system=oregondot&pubtoken=<token>&refreshRate=2000"
    }
  ]
}
```

- `fullimage` → 352×240 px JPEG updated every ~2 s
- `halfimage` → 176×120 px JPEG
- Each camera has its own `pubtoken` (SHA256-like hex string)
- These tokens are embedded in the TripCheck JS — they are effectively public

---

### rwis — `/Scripts/map/data/RWIS.js`

| Field | Type | Notes |
|---|---|---|
| `roadWeatherReportID` | OID | Station ID |
| `station-code` | String | RWIS station code, e.g. `2RW012` |
| `updateTime` | String | `MM/DD/YYYY HH:MM am/pm` |
| `altTagText` | String | Brief station description |
| `tripcheckName` | String | Full location name |
| `locationName` | String | Short location name |
| `latitude` | Double | WGS-84 |
| `longitude` | Double | WGS-84 |
| `iconType` | Integer | 14 = weather station |
| `currTemp` | String | Air temperature, e.g. `50.5F` |
| `dewPoint` | String | Dew point, e.g. `20.1F` |
| `humidity` | String | Relative humidity, e.g. `29%` |
| `precip` | String | Precipitation condition |
| `rain1hr` | String | Rainfall in last hour |
| `visibility` | String | Visibility distance |
| `windDirection` | String | Cardinal direction, e.g. `NW` |
| `windSpeed` | String | Average wind speed |
| `windSpeedGust` | String | Gust wind speed |
| `roadTemp` | String | Road surface temperature |

**Staleness rule**: TripCheck treats any RWIS report older than 1 hour as stale and shows "No Current Report".

---

### road_weather — `/Scripts/map/data/rw.js`

| Field | Type | Notes |
|---|---|---|
| `id` | OID | Report ID |
| `iconType` | Integer | See icon type table below |
| `activeReport` | String | `"true"` / `"false"` |
| `activeSnowZoneCount` | Integer | Number of active snow zones |
| `chainRestrictionCode` | Integer | 0 = none; >0 = restriction level |
| `chainRestrictionDesc` | String | Human-readable chain law text |
| `chainRestrictionStartMP` | Double | Start milepost of chain restriction |
| `chainRestrictionEndMP` | Double | End milepost |
| `commercialRestrictionCode` | Integer | 0 = none |
| `commercialRestrictionDesc` | String | Commercial vehicle restriction text |
| `furtherText` | String | Additional comments (up to 2000 chars) |
| `linkId` | String | State highway segment ID |
| `linkName` | String | Route code, e.g. `I-84` |
| `linkStartMP` | Double | Report start milepost |
| `linkEndMP` | Double | Report end milepost |
| `locationName` | String | Reporting station name |
| `pavementConditionCode` | Integer | Pavement condition code |
| `pavementConditionDesc` | String | e.g. `Wet`, `Snow Covered` |
| `rain1hr` | Double | Precipitation last hour (inches) |
| `snowfall` | Double | New snow depth (inches); -1 = trace |
| `snowDepth` | Double | Total snow on roadside (inches); -1 = trace |
| `tempCurr` | Double | Current temperature °F |
| `tempHigh` | Double | High temperature °F |
| `tempLow` | Double | Low temperature °F |
| `weatherConditionDesc` | String | e.g. `Heavy Snow`, `Freezing Rain` |
| `entryTime` | Date | ISO 8601 timestamp |
| `expirationTime` | Date | ISO 8601 expiry |
| `snowZones` | Array | Active snow zone objects |
| `latitude` | Double | WGS-84 |
| `longitude` | Double | WGS-84 |

**iconType values for road_weather**:

| iconType | Meaning |
|---|---|
| 8 | Road Closed |
| 11 | Severe Weather Hazard |
| 12 | Weather Warning |
| 13 | Carry Chains or Traction Tires (Snow Zone) |
| 14 | Weather Station (informational) |

---

### events / incidents — `EVENT.js` / `INCD.js` / `INCDLine.js` / `EVENTLine.js`

| Field | Type | Notes |
|---|---|---|
| `incidentId` | Integer | Unique ID |
| `tocsIncidentId` | Integer | TOCS internal ID |
| `type` | String | `EVENT` or `INCD` |
| `lastUpdated` | String | ISO 8601 |
| `startTime` | String | ISO 8601 |
| `locationName` | String | Location description |
| `route` | String | Highway route, e.g. `I-5` |
| `eventTypeId` | String | `RW` = road work, `IC` = incident, etc. |
| `eventTypeName` | String | e.g. `Road Work`, `Crash` |
| `eventSubTypeId` | Integer | Sub-type numeric code |
| `eventSubTypeName` | String | e.g. `Road Construction` |
| `odotCategoryID` | String | `C` = construction, `I` = incident, etc. |
| `odotCategoryDescript` | String | Category description |
| `odotSeverityID` | Integer | 0–9 severity scale |
| `odotSeverityDescript` | String | e.g. `Road Closed`, `Informational Only` |
| `iconType` | Integer | See icon map in the JS source |
| `beginMP` | Integer | Begin milepost |
| `beginMarker` | String | Human-readable begin location |
| `endMP` | Integer | End milepost |
| `endMarker` | String | Human-readable end location |
| `startLatitude` | Double | WGS-84 |
| `startLongitude` | Double | WGS-84 |
| `endLatitude` | Double | WGS-84 |
| `endLongitude` | Double | WGS-84 |
| `comments` | String | Detailed description |
| `publicContact` | String | Contact name/org |
| `publiContactPhone` | String | (sic — typo in source) Contact phone |
| `infoUrl` | String | Link to additional information |
| `lanesAffected` | Array | Lane-level restriction objects |
| `delayInfo` | Array | Delay information objects |

**odotSeverityID reference**:

| ID | Description |
|---|---|
| 0 | Informational Only |
| 1 | No Delay |
| 2 | Minimal Delay |
| 3 | Minor Delay (<20 min) |
| 4 | Moderate Delay (20 min–2 hr) |
| 5 | Significant Delay (>2 hr) |
| 8 | Conditional Closure |
| 9 | Closure |
| 29 | Road Closure |

---

### travel_times — `/Scripts/map/data/traveltime.js`

```json
{
  "origId": 2,
  "locationName": "[ORE217|sign-ore217.png] NB; Allen Blvd",
  "iconType": 25,
  "latitude": 45.47623,
  "longitude": -122.78904,
  "routes": [
    {
      "id": 411,
      "routeDest": "[I-405|sign-i-405.png]; via [US26|sign-us26.png]",
      "minRouteTime": 9,
      "dt": "2026-03-27T09:37:12.237-07:00",
      "travelTime": 9,
      "delay": 1,
      "failureMsg": "",
      "useAltMsg": false
    }
  ]
}
```

- `travelTime` is in **minutes**; -1 means N/A
- `delay` is in **minutes** over baseline; -1 means no comparison available
- `minRouteTime` is the historical minimum (baseline) travel time; `null` if unknown
- Location names use `[ROUTE|sign-image.png]` markup — strip brackets to get route name
- All timestamps are ISO 8601 with UTC offset

---

### alerts — `/Scripts/map/data/ALRT.js`

| Field | Type | Notes |
|---|---|---|
| `alertId` | OID | Unique alert ID |
| `updateTime` | String | Last update timestamp |
| `startTime` | String | Alert start |
| `estClearTime` | String | Estimated clear time |
| `actualClearTime` | String | Actual clear time (empty if ongoing) |
| `alertType` | String | `ALRTINCD` / `ALRTWTH` / `ALRTCONS` / `ALRTEVENT` |
| `priority` | Integer | 1 = highest priority |
| `sourceId` | Integer | Source incident/event ID |
| `areaAffected` | String | Text description of affected area |
| `title` | String | Short title |
| `header` | String | One-line summary |
| `messageText` | String | Full markdown-capable message (up to 3900 chars) |
| `furtherInfoURL` | String | External link |
| `tripcheckOnly` | String | `"true"` if TripCheck-only (not in 511) |
| `entryTime` | String | When alert was entered |

Geometry is a polygon ring array in EPSG:3857 representing the affected region.

---

### rwis trucking — `/Scripts/map/data/RWTrucking.js`

Same schema as `road_weather` (`rw.js`) but with `type` field set to `"TRK"` and focus on `commercialRestrictionCode`/`commercialRestrictionDesc`.

---

### parking — `/Scripts/map/data/mfparking.js`

```json
{
  "iconType": "19",
  "locationName": "Multnomah Falls Parking",
  "percentFull": 59,
  "percentFullMessage": "Parking lot 60% full",
  "updateTime": "3/27/2026 9:37 AM"
}
```
iconType: `19` = space available, `28` = lot full

---

### waze_alerts — `/Scripts/map/data/wazeAlerts.js`

| Field | Type | Notes |
|---|---|---|
| `id` | OID | Waze alert ID |
| `publishDate` | String | ISO 8601 |
| `reportDate` | String | ISO 8601 |
| `typeId` | Integer | 1=Crash, 2=Hazard, 3=Road Closed, 4=Jam |
| `eventType` | String | `Crash`, `Hazard`, etc. |
| `subtypeId` | Integer | Sub-type |
| `eventSubtype` | String | Sub-type name |
| `latitude` | Double | WGS-84 |
| `longitude` | Double | WGS-84 |
| `isOdot` | Integer | 1 if confirmed by ODOT |
| `street` | String | Street name |
| `city` | String | City, state |
| `description` | String | Description |

iconType: `20`=construction, `21`=weather hazard, `22`=traffic jam, `23`=accident, `24`=road closure

---

## Camera Image System

### Snapshot Images (ODOT-hosted)

```
GET https://tripcheck.com/RoadCams/cams/{filename}?rand={timestamp_ms}
```
- Returns JPEG (confirmed `200 OK`, `Content-Type: image/jpeg`)
- `rand` parameter busts browser/CDN cache; use `int(time.time() * 1000)`
- Images updated approximately every 60 seconds during daylight hours
- Served directly from `Microsoft-IIS/10.0`

### Last Daylight Images (LDI)

```
GET https://tripcheck.com/RoadCams/cams/camsLDI/{filename}?rand={timestamp_ms}
```
- Last captured daylight image, updated once per day after dark
- Only shown in the TripCheck UI during specific monthly time windows (defined in `ldiSchedule.min.js`)

### Live Streaming Video (TrafficLand CDN)

Only cameras with `videoId > 0` have live video.

```
GET http://ie.trafficland.com/v1.0/{webid}/full?system=oregondot&pubtoken={pubtoken}&refreshRate=2000
GET http://ie.trafficland.com/v1.0/{webid}/half?system=oregondot&pubtoken={pubtoken}&refreshRate=2000
```

- `full` = 352×240 JPEG
- `half` = 176×120 JPEG
- `pubtoken` is per-camera and embedded in `TrafficVideo.js`
- `refreshRate` is in milliseconds (typically 2000 = 2 s)
- The API returns a PNG placeholder when the camera is offline (`Image-Status: 404` header)

---

## Request Headers

Recommended headers to avoid being blocked:

```python
headers = {
    "User-Agent": "Mozilla/5.0 (compatible; YourApp/1.0)",
    "Referer": "https://tripcheck.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
```

---

## Server Info

```
Server: Microsoft-IIS/10.0
X-Powered-By: ASP.NET
X-AspNetMvc-Version: 5.2
X-AspNet-Version: 4.0.30319
```

---

## Rate-Limit Recommendations

| Feed | Max poll rate |
|---|---|
| Camera inventory | Once per hour |
| Camera images | Once per 60 s per camera |
| Live video stills | Every 2 s (matches TripCheck's own interval) |
| RWIS, events, alerts | Once per 2 min |
| Road/weather, trucking | Once per 15 min |

---

## Python Client Usage

```python
from oregon_tripcheck_client import TripCheckClient

client = TripCheckClient(use_cache=True)

# All cameras
cameras = client.get_cameras()
for cam in cameras:
    print(cam.title, cam.route, cam.image_url)

# RWIS weather stations
stations = client.get_rwis_stations()
for s in stations:
    print(s.tripcheck_name, s.curr_temp, s.road_temp, s.wind_speed)

# RWIS + Camera co-location (unique to TripCheck)
pairs = client.get_rwis_with_nearby_cameras(max_distance_km=1.0)
for pair in pairs:
    ws = pair["rwis"]
    cam = pair["nearest_camera"]
    print(f"Station: {ws.tripcheck_name}  temp={ws.curr_temp}  road={ws.road_temp}")
    print(f"  Camera: {cam.title}  dist={pair['nearest_km']} km  {cam.image_url}")

# Full highway snapshot (cameras + weather)
for item in client.get_highway_snapshot("I-84"):
    cam = item["camera"]
    ws = item["rwis"]
    weather = f"{ws.curr_temp} road={ws.road_temp}" if ws else "no RWIS nearby"
    print(f"{cam.title}: {weather}")

# Chain/traction restrictions
for r in client.get_chain_restrictions():
    print(r.link_name, r.chain_restriction_desc, r.chain_restriction_start_mp, r.chain_restriction_end_mp)

# Road closures
for r in client.get_road_closures():
    print(r.link_name, r.location_name, r.further_text)

# Travel times
for pt in client.get_travel_times():
    for route in pt.routes:
        if route.travel_time > 0:
            print(f"{pt.location_name} -> {route.destination}: {route.travel_time} min")

# Active alerts
for a in client.get_alerts():
    print(a.title, a.area_affected, a.header)

# Events / incidents
events = client.get_events()
incidents = client.get_incidents()

# Live video cameras
for v in client.get_camera_videos():
    print(v.name, v.full_image_url)

# Raw EsriJSON access
raw = client.get_raw("waze_jams")

# Download a camera image
cam = cameras[0]
jpeg_bytes = client.download_camera_image(cam)
with open("camera.jpg", "wb") as f:
    f.write(jpeg_bytes)
```

---

## Known Limitations

1. **TrafficVideo.js malformed JSON**: The file contains bare leading-zero integers for ZIP codes (e.g. `"zipCode": 04105`), which is not valid JSON. The client automatically fixes this with a regex before parsing — `"zipCode": \d+` → `"zipCode": "<number>"`.
2. **Video tokens**: The `pubtoken` values in `TrafficVideo.js` are embedded and semi-public, but ODOT/TrafficLand could rotate them.
2. **No historical data**: All feeds are live/current only. No historical archive is exposed.
3. **Geometry CRS**: All map geometries are in EPSG:3857 (Web Mercator). Convert to WGS-84 for standard GPS use. Most feeds also include `latitude`/`longitude` attribute fields in WGS-84.
4. **LDI windows**: The Last Daylight Image URL works but the image is only "current" during specific monthly time windows defined in `ldiSchedule.min.js`.
5. **NOAA forecasts**: TripCheck embeds NOAA forecast iframes but doesn't proxy the data — fetch directly from `api.weather.gov`.
6. **ArcGIS basemaps**: `/Basemaps/Pseudo.MapServer/…` requires the ESRI JS API context and is not useful as a standalone REST endpoint.

---

## Official ODOT API (Subscription-Key Required)

ODOT offers a formal API via **Azure API Management**:

| Resource | URL |
|---|---|
| Developer portal | `https://apiportal.odot.state.or.us/` |
| API gateway | `https://api.odot.state.or.us/` |
| Getting Started guide | `https://tripcheck.com/pdfs/TripCheckAPI_Getting_Started_GuideV5.pdf` |

### Authentication

All requests to the official API require an `Ocp-Apim-Subscription-Key` header:

```
GET https://api.odot.state.or.us/{api-path}
Ocp-Apim-Subscription-Key: <your-subscription-key>
Accept: application/json
```

Sign up for a free key at the developer portal above. The key is a hex string passed as a request header.

### Official API Operations

The operations below were discovered from the portal. The API path is constructed as
`/{api-version}/{operation}` at `api.odot.state.or.us`:

| Operation | Description |
|---|---|
| `Cctv_GetInventoryFilter` | CCTV camera inventory with image URL (`cctv-url` field) |
| `Rwis_GetInventoryFilter` | RWIS station inventory |
| `Rwis_GetStatusFilter` | RWIS station live readings |
| `RW_GetReportsFilter` | Road & weather crew reports |
| `RW_GetMetadata` | Road & weather enumerated values |
| `Inc_GetIncidentsFilter` | Traffic incidents |
| `Inc_GetIncidentsFilterForWaze` | Incidents in Waze CIFS v2 format |
| `Inc_GetIncdMetadata` | Incident metadata/enumerations |
| `Dms_GetInventoryFilter` | Dynamic Message Sign inventory |
| `Dms_GetStatus` | DMS current message |
| `TD_GetInventoryFilter` | Traffic detector inventory |
| `TD_GetRoadwayDataFilter` | Traffic detector roadway data |
| `TD_GetRampDataFilter` | Traffic detector ramp data |
| `Cls_GetClsInventory` | Classified Length/Speed inventory |
| `Cls_GetClsLengthData` | Vehicle length classification data |
| `Cls_GetClsSpeedData` | Vehicle speed classification data |
| `Tle_GetLocalEventsByFilter` | Local travel events (municipalities) |
| `Tle_GetLocalEventsForWaze` | Local events in Waze CIFS v2 format |
| `Routes_GetRoutes` | Route metadata |
| `Mfp_GetMFparking` | Multnomah Falls parking occupancy |
| `WZDx_GetActivitiesFilter` | Work zone activities (WZDx v4 standard) |

### Official API vs Unofficial Data Feeds

| Feature | Official API | Unofficial Feeds |
|---|---|---|
| Auth required | Yes (Ocp-Apim-Subscription-Key) | No |
| Format | XML or JSON (selectable) | EsriJSON |
| Rate limiting | Yes (enforced by Azure APIM) | No enforced limit |
| `cctv-url` field (full image URL) | Yes | No (filename only) |
| Filter by route/region | Yes | No |
| DMS, Traffic Detectors | Yes | No |
| Refresh rates | 5 min (RWIS), 30 s (incidents) | 2 min (map feeds) |

---

## Additional Endpoints

### DynamicReports Text Reports

TripCheck also exposes text-formatted reports (HTML) at:

| URL | Description |
|---|---|
| `https://tripcheck.com/DynamicReports/Report/RoadConditions` | Statewide road conditions |
| `https://tripcheck.com/DynamicReports/Report/WeatherStations` | Weather station readings |
| `https://tripcheck.com/DynamicReports/Report/Cameras` | Camera list with image links |
| `https://tripcheck.com/DynamicReports/Report/Cameras/{0-9}` | Cameras by region (0=Northwest Oregon, 1-9=other regions) |
| `https://tripcheck.com/DynamicReports/Report/TravelTime` | Travel time summaries |

The Cameras report pages expose the image path pattern directly in the HTML:
```html
data-image-path="/roadcams/cams/{filename}"
data-ldi-path="/roadcams/cams/camsLDI/{filename}"
```

---

## Related Official Resources

- TripCheck 511: `https://tripcheck.com/`
- ODOT Developer Portal: `https://apiportal.odot.state.or.us/`
- ODOT Open Data: `https://www.oregon.gov/odot/Data/`
- RWIS Network: operated by ODOT Maintenance
- Oregon 511 phone: **511** (or 1-800-977-6368)
- Getting Started Guide: `https://tripcheck.com/pdfs/TripCheckAPI_Getting_Started_GuideV5.pdf`
