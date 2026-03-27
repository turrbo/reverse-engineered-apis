# Maryland CHART Traffic API Client

> Python client for the Maryland Coordinated Highways Action Response Team (CHART) public traffic data APIs — cameras, incidents, closures, message signs, speeds, weather, and more.

No API key required. No external dependencies. Python 3.8+ standard library only.

---

## What CHART Is

CHART (Coordinated Highways Action Response Team) is a joint program of the Maryland State Highway Administration (SHA) and other transportation partners. It operates a statewide Traffic Management Center network and exposes all of its real-time traffic data as a public feed at:

- **Portal**: https://www.chart.maryland.gov
- **Data API base**: `https://chartexp1.sha.maryland.gov/CHARTExportClientService/`

All feeds are publicly accessible. No registration, authentication, or API key is needed.

---

## Quick Start

```bash
# Run the CLI summary (hits all feeds)
python mdot_md_client.py

# Show live camera list with stream URLs
python mdot_md_client.py cameras

# Show active traffic incidents
python mdot_md_client.py incidents
```

```python
from mdot_md_client import CHARTClient

client = CHARTClient()

# Get all cameras and filter to online only
cameras = client.get_cameras()
online = [c for c in cameras if c.is_online]
print(f"{len(online)} cameras online")

# Print HLS stream URL for the first online camera
print(online[0].stream_url)
# https://strmr5.sha.maryland.gov/rtplive/7a00a1dc01250075004d823633235daa/playlist.m3u8
```

---

## Installation

No installation required beyond Python 3.8 or later. Copy `mdot_md_client.py` into your project.

```bash
# Verify the client works
python mdot_md_client.py
```

Expected output (values change in real time):

```
Maryland CHART — Live Traffic Summary
==========================================
  Cameras Total                    552
  Cameras Online                   484
  Incidents Total                  36
  Incidents With Alert             2
  Closures Total                   44
  Dms Total                        288
  Dms Active                       186
  Speed Sensors Total              295
  Speed Sensors Online             264
  Weather Stations Total           132
  Snow Emergencies Total           0
  Fetched At                       2026-03-27T20:22:11+00:00
```

---

## CLI Reference

| Command | What it shows |
|---------|---------------|
| `cameras` | All cameras with thumbnail and HLS stream URLs |
| `incidents` | Active traffic events (accidents, debris, police activity) |
| `closures` | Active and planned road/lane closures |
| `dms` | Dynamic Message Signs with current displayed text |
| `speeds` | Traffic speed sensor readings by location |
| `weather` | Road Weather Information System station data |
| `snow` | Active county snow emergency declarations |
| `wzdx` | WZDx v4.1 GeoJSON work-zone feed |
| `messages` | CHART system-wide portal messages |
| *(no command)* | Summary counts across all feeds |

---

## Library Reference

### `CHARTClient(timeout=30)`

Main client class. All methods perform a single synchronous HTTP GET request.

```python
client = CHARTClient(timeout=30)
```

---

### `get_cameras() → List[Camera]`

Returns all ~550 traffic cameras statewide.

```python
cameras = client.get_cameras()
```

**`Camera` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Opaque hex identifier |
| `name` | `str` | Short location code |
| `description` | `str` | Human-readable location |
| `lat` / `lon` | `float` | WGS-84 coordinates |
| `cctv_ip` | `str` | Streaming server hostname |
| `route_prefix` | `str` | `IS`, `US`, `MD` |
| `route_number` | `int` | Numeric route ID |
| `mile_post` | `float \| None` | Highway mile marker |
| `op_status` | `str` | `OK`, `COMM_FAILURE`, `COMM_MARGINAL` |
| `comm_mode` | `str` | `ONLINE`, `OFFLINE`, `MAINT_MODE` |
| `camera_categories` | `List[str]` | Regional grouping labels |
| `video_url` | `str` | CHART portal video page |
| `thumbnail_url` | `str` | JPEG snapshot URL (~10 s cadence) |
| `stream_url` | `str` | HLS m3u8 playlist URL |
| `last_cached` | `datetime \| None` | UTC cache timestamp |
| `is_online` | `bool` (property) | `True` if `op_status == OK` and `ONLINE` |

**Camera stream / thumbnail URL patterns:**

```
HLS stream:  https://{cctv_ip}/rtplive/{camera_id}/playlist.m3u8
Thumbnail:   https://chart.maryland.gov/thumbnails/{camera_id}.jpg
Video page:  https://chart.maryland.gov/Video/GetVideo/{camera_id}
```

CCTV servers observed: `strmr3.sha.maryland.gov`, `strmr5.sha.maryland.gov`.

**Play an HLS stream with VLC or ffplay:**

```bash
vlc "https://strmr5.sha.maryland.gov/rtplive/7a00a1dc01250075004d823633235daa/playlist.m3u8"
ffplay "https://strmr5.sha.maryland.gov/rtplive/7a00a1dc01250075004d823633235daa/playlist.m3u8"
```

---

### `get_cameras_by_route(route_prefix, route_number) → List[Camera]`

Filter cameras to a specific highway, sorted by mile post.

```python
# All cameras on I-95
i95 = client.get_cameras_by_route("IS", 95)

# All cameras on US 50
us50 = client.get_cameras_by_route("US", 50)

# All cameras on MD 97
md97 = client.get_cameras_by_route("MD", 97)
```

**Route prefix values:**

| Prefix | Meaning |
|--------|---------|
| `IS` | Interstate (I-95, I-270, I-695, …) |
| `US` | US Route (US 50, US 301, US 29, …) |
| `MD` | Maryland State Route (MD 100, MD 200, …) |

---

### `get_cameras_by_region(region) → List[Camera]`

Filter cameras by geographic region (case-insensitive substring match).

```python
dc_area = client.get_cameras_by_region("Wash. DC")
baltimore = client.get_cameras_by_region("Baltimore")
```

**Common region labels:**

| Label | Coverage |
|-------|---------|
| `Wash. DC` | DC suburbs, I-495 corridor, I-270 |
| `Baltimore` | Baltimore metro, I-695, I-95 |
| `Annapolis` | US 50 / US 301, I-97 |
| `Eastern Shore` | US 50 east of Bay Bridge |
| `Western MD` | I-68, I-70 west |
| `Southern MD` | MD 4, MD 5, MD 235 |

---

### `get_incidents() → List[Incident]`

Returns all active traffic events.

```python
incidents = client.get_incidents()
alerts = [i for i in incidents if i.traffic_alert]
```

**`Incident` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier |
| `name` | `str` | Headline (includes route and location) |
| `description` | `str` | Detailed description |
| `incident_type` | `str` | `Debris In Roadway`, `Personal Injury`, `Disabled Vehicle`, `Police Activity`, … |
| `type_code` | `int` | Numeric type code |
| `lat` / `lon` | `float` | WGS-84 coordinates |
| `county` | `str` | Maryland county |
| `direction` | `str` | `North`, `South`, `East`, `West`, `Inner Loop`, `Outer Loop` |
| `source` | `str` | Reporting entity |
| `op_center` | `str` | Operations center code |
| `closed` | `bool` | Whether cleared |
| `traffic_alert` | `bool` | Public alert issued |
| `traffic_alert_msg` | `str` | Alert text |
| `lanes_status` | `str` | Lane closure summary |
| `lanes` | `List[Lane]` | Per-lane detail |
| `participant_on_scene` | `bool` | Responder on scene |
| `vehicles` | `str` | Vehicle count description |
| `start_time` | `datetime \| None` | UTC first report time |
| `create_time` | `datetime \| None` | UTC record creation time |
| `last_cached` | `datetime \| None` | UTC cache timestamp |

---

### `get_closures() → List[Closure]`

Returns all active and planned lane closures.

```python
closures = client.get_closures()
for cl in closures:
    print(cl.tracking_number, cl.lanes_closed, cl.county)
```

**`Closure` fields** (same location/lane fields as `Incident`, plus):

| Field | Type | Description |
|-------|------|-------------|
| `tracking_number` | `str` | Permit / work-order ID, e.g. `D1-N-WO-2025-1067` |
| `planned` | `bool` | Pre-scheduled (`True`) vs. emergency (`False`) |
| `lanes_closed` | `str` | Closed lane summary |
| `lanes_status` | `str` | Current lane status |
| `source` | `str` | `Lane Closure Permits`, `SHA`, etc. |

---

### `get_speed_sensors() → List[SpeedSensor]`

Returns all Traffic Speed Sensor (TSS) stations.

```python
sensors = client.get_speed_sensors()
for s in sensors:
    for z in s.zones:
        print(f"{s.description}: {z.direction} {z.speed} MPH")
```

**`SpeedSensor` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique sensor ID |
| `name` | `str` | Sensor code, e.g. `S315017` |
| `description` | `str` | Location description |
| `lat` / `lon` | `float` | WGS-84 coordinates |
| `speed` | `float` | Aggregate speed (MPH) |
| `direction` | `str` | Primary direction |
| `zones` | `List[SpeedZone]` | Per-direction speed readings |
| `op_status` | `str` | `OK`, `COMM_FAILURE`, `HARDWARE_FAILURE` |
| `comm_mode` | `str` | `ONLINE`, `OFFLINE`, `MAINT_MODE` |
| `owning_org` | `str` | `SHA` or `MDTA` |
| `range_only` | `bool` | Presence-only detector |
| `last_update` | `datetime \| None` | Last sensor reading |
| `last_cached` | `datetime \| None` | Cache timestamp |

**`SpeedZone` fields:** `speed` (int MPH), `bearing` (int degrees), `direction` (str).

**Note:** A value of `-1` MPH indicates the sensor is not currently reporting a valid speed.

---

### `get_message_signs() → List[DynamicMessageSign]`

Returns all Dynamic Message Signs (DMS / VMS) and their current messages.

```python
signs = client.get_message_signs()
active = [s for s in signs if s.is_active]
for s in active:
    print(s.description)
    print(s.msg_plain)
```

**`DynamicMessageSign` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique identifier |
| `name` | `str` | Sign ID code, e.g. `8829` |
| `description` | `str` | Physical location |
| `lat` / `lon` | `float` | WGS-84 coordinates |
| `msg_plain` | `str` | Plain-text message |
| `msg_multi` | `str` | NTCIP MULTI-coded message |
| `msg_html` | `str` | HTML table representation |
| `op_status` | `str` | `OK`, `HARDWARE_FAILURE`, `COMM_FAILURE`, `HARDWARE_WARNING` |
| `comm_mode` | `str` | `ONLINE`, `OFFLINE`, `MAINT_MODE` |
| `has_beacons` | `bool` | Beacon lights present |
| `beacons_enabled` | `bool` | Beacons currently active |
| `last_cached` | `datetime \| None` | Cache timestamp |
| `is_active` | `bool` (property) | `True` if OK status and non-empty message |

**NTCIP MULTI format codes used by CHART:**

| Code | Meaning |
|------|---------|
| `[nl]` | New line |
| `[np]` | New page |
| `[pt25o0]` | Page time 2.5 s, off 0 s |
| `[pt30o0]` | Page time 3.0 s, off 0 s |
| `[jl3]` | Left-justify text |
| `[fo]` | Font specification |

---

### `get_weather_stations() → List[WeatherStation]`

Returns all RWIS (Road Weather Information System) station data.

```python
stations = client.get_weather_stations()
for stn in stations:
    if stn.precip_type not in ("None", "No Data Available", ""):
        print(f"{stn.name}: {stn.precip_type}")
```

**`WeatherStation` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Station ID (numeric string) |
| `name` | `str` | Location name |
| `description` | `str` | Location description |
| `lat` / `lon` | `float` | WGS-84 coordinates |
| `air_temp` | `str` | Air temperature, e.g. `"48F"` |
| `dew_point` | `str` | Dew point, e.g. `"36F"` |
| `relative_humidity` | `str` | Humidity, e.g. `"63%"` |
| `wind_description` | `str` | Wind, e.g. `"NE 7 MPH"` |
| `gust_speed` | `str` | Gust speed, e.g. `"15 MPH"` |
| `precip_type` | `str` | `None`, `Rain`, `Snow`, `Freezing Rain`, … |
| `pavement_temp` | `str` | Pavement temp range, e.g. `"58F to 58F"` |
| `full_rwis` | `bool` | `True` = full multi-sensor RWIS station |
| `last_update` | `datetime \| None` | Last sensor reading |
| `last_cached` | `datetime \| None` | Cache timestamp |

---

### `get_snow_emergencies() → List[SnowEmergency]`

Returns active and recently lifted snow emergency declarations by county.

```python
snow = client.get_snow_emergencies()
if snow:
    for em in snow:
        print(f"Snow emergency: {em.county} County")
else:
    print("No snow emergencies active")
```

Returns an empty list outside of winter weather events.

---

### `get_road_conditions() → List[Dict[str, Any]]`

Returns weather-related road conditions reported by maintenance shops. This feed is only populated during active winter weather events. Raw dicts are returned because the schema varies by condition type.

---

### `get_wzdx() → Dict[str, Any]`

Returns the Maryland DOT WZDx v4.1 GeoJSON FeatureCollection from the RITIS aggregator.

```python
geojson = client.get_wzdx()
features = geojson["features"]
for feat in features:
    props = feat["properties"]
    print(props["road_names"], props["vehicle_impact"])
```

**WZDx feature properties:**

| Property | Description |
|----------|-------------|
| `road_names` | List of affected road names |
| `direction` | Travel direction |
| `vehicle_impact` | `all-lanes-closed`, `some-lanes-closed`, `all-lanes-open` |
| `start_date` | ISO 8601 start datetime |
| `end_date` | ISO 8601 end datetime |
| `description` | Work zone description |
| `beginning_cross_street` | Start cross street |
| `ending_cross_street` | End cross street |
| `lanes` | Array of lane objects with `order`, `status`, `type` |
| `data_source_id` | Source system ID |
| `is_start_position_verified` | Whether start coordinates are verified |
| `is_end_position_verified` | Whether end coordinates are verified |

Feed license: **CC0 1.0 (public domain)**. Update frequency: ~60 seconds.

---

### `get_system_messages() → List[SystemMessage]`

Returns active CHART portal notifications (maintenance windows, outages).

```python
for msg in client.get_system_messages():
    print(msg.message_text)
```

---

### `get_summary() → Dict[str, Any]`

Fetches all primary feeds and returns count-level statistics. Useful for dashboards and health checks.

```python
summary = client.get_summary()
print(summary["cameras_online"], "cameras online")
print(summary["incidents_total"], "active incidents")
```

**Summary keys:** `cameras_total`, `cameras_online`, `incidents_total`, `incidents_with_alert`, `closures_total`, `closures_planned`, `dms_total`, `dms_active`, `speed_sensors_total`, `speed_sensors_online`, `weather_stations_total`, `snow_emergencies_total`, `fetched_at`.

---

## Discovered API Endpoints

All endpoints below are public (no authentication required).

### CHART Export Service
**Base:** `https://chartexp1.sha.maryland.gov/CHARTExportClientService/`

| Endpoint | Method | Returns |
|----------|--------|---------|
| `getCameraMapDataJSON.do` | GET | Camera list with stream URLs |
| `getEventMapDataJSON.do` | GET | Active traffic incidents |
| `getActiveClosureMapDataJSON.do` | GET | Active/planned road closures |
| `getTSSMapDataJSON.do` | GET | Traffic speed sensor readings |
| `getDMSMapDataJSON.do` | GET | Dynamic message sign content |
| `getRWISMapDataJSON.do` | GET | Road weather station data |
| `getSEPMapDataJSON.do` | GET | Snow emergency plans |
| `getIPSMapDataJSON.do` | GET | Winter road conditions (IPS) |
| `getWebMessagesDataJSON.do` | GET | Portal system messages |

All endpoints use the same JSON envelope:

```json
{
  "error": null,
  "data": [ ... ],
  "success": true,
  "warnings": [],
  "totalCount": 42
}
```

### CHART Web Portal
**Base:** `https://chart.maryland.gov/` or `https://www.chart.maryland.gov/`

| Endpoint | Method | Returns |
|----------|--------|---------|
| `Video/GetVideo/{camera_id}` | GET | HTML video player page |
| `thumbnails/{camera_id}.jpg` | GET | JPEG camera snapshot |
| `thumbnails/no-image-available.jpg` | GET | Fallback thumbnail |
| `DataFeeds/GetIncidentXml` | GET | Incidents as XML |
| `DataFeeds/GetClosureXml` | GET | Closures as XML |
| `DataFeeds/GetCamerasXml` | GET | Cameras as XML |
| `DataFeeds/GetTssXml` | GET | Speed sensors as XML |
| `DataFeeds/GetRwisXml` | GET | Weather stations as XML |
| `DataFeeds/GetDmsXml` | GET | Message signs as XML |
| `DataFeeds/GetSepXml` | GET | Snow emergencies as XML |
| `DataFeeds/GetIpsXml` | GET | Road conditions as XML |
| `/thumbnailHub` | WebSocket (SignalR) | Push-based thumbnail updates |

### External Feeds

| URL | Format | Description |
|-----|--------|-------------|
| `https://filter.ritis.org/wzdx_v4.1/mdot.geojson` | GeoJSON | WZDx v4.1 work zones |

---

## Camera Streaming Details

### HLS Stream URL Pattern

```
https://{cctv_ip}/rtplive/{camera_id}/playlist.m3u8
```

**Observed CCTV servers:**
- `strmr3.sha.maryland.gov`
- `strmr5.sha.maryland.gov`

The `cctv_ip` field in the camera JSON determines which server hosts the stream. Both servers appear to share load across the ~550 statewide cameras.

### Thumbnail URL Pattern

```
https://chart.maryland.gov/thumbnails/{camera_id}.jpg
```

Thumbnails are updated via SignalR push notifications on the `/thumbnailHub` endpoint. The web portal subscribes to the `Update` event to refresh thumbnails without polling.

### Playing Camera Streams

```bash
# VLC (GUI or headless)
vlc "https://strmr5.sha.maryland.gov/rtplive/7a00a1dc01250075004d823633235daa/playlist.m3u8"

# ffplay (part of FFmpeg)
ffplay "https://strmr5.sha.maryland.gov/rtplive/7a00a1dc01250075004d823633235daa/playlist.m3u8"

# ffmpeg — save 60 seconds to file
ffmpeg -i "https://strmr5.sha.maryland.gov/rtplive/7a00a1dc01250075004d823633235daa/playlist.m3u8" \
       -t 60 -c copy capture.mp4
```

### Python — Download a Snapshot

```python
import urllib.request
from mdot_md_client import CHARTClient

client = CHARTClient()
cameras = client.get_cameras()
cam = next(c for c in cameras if c.is_online)

# Save snapshot to disk
urllib.request.urlretrieve(cam.thumbnail_url, f"{cam.id}.jpg")
print(f"Saved snapshot: {cam.description}")
```

---

## Rate Limiting and Caching

- The CHART Export Service caches all data feeds on a ~60-second cycle.
- The `lastCachedDataUpdateTime` field on every record indicates when the cache was last refreshed.
- There is no published rate limit for these public APIs, but polling more frequently than once per 60 seconds returns identical data and wastes bandwidth.
- The CHART portal itself shows a "Data last updated" notice that reflects the cache cycle.

**Recommended polling interval:** 60–120 seconds for real-time applications.

---

## Complete Code Examples

### Find Cameras Near a Location

```python
import math
from mdot_md_client import CHARTClient

def haversine(lat1, lon1, lat2, lon2):
    """Return distance in miles between two WGS-84 points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))

client = CHARTClient()
cameras = client.get_cameras()

# BWI Airport coordinates
target_lat, target_lon = 39.1754, -76.6683

nearby = sorted(
    [(haversine(target_lat, target_lon, c.lat, c.lon), c) for c in cameras],
    key=lambda x: x[0]
)[:5]

for dist, cam in nearby:
    print(f"  {dist:.1f} mi — {cam.description}")
    print(f"            {cam.thumbnail_url}")
```

### Export All Incidents to GeoJSON

```python
import json
from mdot_md_client import CHARTClient

client = CHARTClient()
incidents = client.get_incidents()

geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [i.lon, i.lat]},
            "properties": {
                "id": i.id,
                "name": i.name,
                "incident_type": i.incident_type,
                "county": i.county,
                "direction": i.direction,
                "lanes_status": i.lanes_status,
                "traffic_alert": i.traffic_alert,
                "start_time": i.start_time.isoformat() if i.start_time else None,
            },
        }
        for i in incidents
    ],
}

with open("maryland_incidents.geojson", "w") as f:
    json.dump(geojson, f, indent=2)

print(f"Exported {len(incidents)} incidents to maryland_incidents.geojson")
```

### Monitor for Traffic Alerts

```python
import time
from mdot_md_client import CHARTClient

client = CHARTClient()
seen_ids = set()

print("Monitoring for new traffic alerts (Ctrl+C to stop)...")
while True:
    incidents = client.get_incidents()
    for incident in incidents:
        if incident.traffic_alert and incident.id not in seen_ids:
            seen_ids.add(incident.id)
            print(f"\n[ALERT] {incident.incident_type}")
            print(f"  {incident.name}")
            print(f"  County: {incident.county} | Direction: {incident.direction}")
            print(f"  Lanes: {incident.lanes_status}")
            if incident.traffic_alert_msg:
                print(f"  Message: {incident.traffic_alert_msg}")
    time.sleep(60)
```

### Get All Active DMS Travel Times

```python
from mdot_md_client import CHARTClient

client = CHARTClient()
signs = client.get_message_signs()

# Travel time signs typically contain "MILES" and "MINUTES" in plain text
travel_time_signs = [
    s for s in signs
    if s.is_active and "MINUTES" in s.msg_plain.upper()
]

print(f"Found {len(travel_time_signs)} travel-time signs:\n")
for sign in sorted(travel_time_signs, key=lambda s: s.description):
    print(f"  {sign.description}")
    print(f"  >>> {sign.msg_plain}\n")
```

### I-95 Corridor Snapshot

```python
from mdot_md_client import CHARTClient

client = CHARTClient()

# Cameras on I-95, sorted by mile post
cameras = client.get_cameras_by_route("IS", 95)
print(f"I-95 cameras: {len(cameras)}")
for cam in cameras:
    status = "OK" if cam.is_online else cam.op_status
    mp = f"MP {cam.mile_post:.1f}" if cam.mile_post else "MP ?"
    print(f"  [{status:15}] {mp} — {cam.description}")

# Incidents on I-95
incidents = client.get_incidents()
i95_incidents = [i for i in incidents if "I-95" in i.name]
print(f"\nI-95 incidents: {len(i95_incidents)}")
for inc in i95_incidents:
    print(f"  {inc.incident_type} — {inc.direction} — {inc.lanes_status}")
```

---

## Error Handling

All network errors raise `urllib.error.URLError`. Data parsing errors raise `ValueError` or `RuntimeError`.

```python
import urllib.error
from mdot_md_client import CHARTClient

client = CHARTClient(timeout=15)
try:
    cameras = client.get_cameras()
except urllib.error.URLError as e:
    print(f"Network error: {e}")
except (ValueError, RuntimeError) as e:
    print(f"Data error: {e}")
```

The `get_summary()` method is the most reliable health-check because it exercises all primary endpoints in a single call.

---

## Data Update Frequencies

| Feed | Typical Update Frequency |
|------|--------------------------|
| Cameras (metadata) | ~60 seconds |
| Camera thumbnails | ~10–30 seconds (via SignalR push) |
| HLS video streams | Live / continuous |
| Incidents | ~60 seconds |
| Closures | ~60 seconds |
| Speed sensors | ~60 seconds |
| Message signs | ~60 seconds |
| Weather stations | ~5–10 minutes |
| Snow emergencies | As declared by counties |
| WZDx GeoJSON | ~60 seconds |
| System messages | On-demand by CHART staff |

---

## Architecture Notes

The CHART public API stack consists of:

1. **CHART Export Client Service** — A Java-based REST-ish service at `chartexp1.sha.maryland.gov` that serialises live CHART TMC data into JSON. All endpoints are GET requests returning the standard `{error, data, success, warnings, totalCount}` envelope.

2. **CHART Web Portal** — An ASP.NET MVC application at `chart.maryland.gov` that serves the public-facing dashboard. It calls the Export Client Service internally and also proxies some requests.

3. **Camera streaming infrastructure** — CCTV encoders push RTMP streams to the `strmrN.sha.maryland.gov` media servers, which transcode to HLS (m3u8). Thumbnails are extracted periodically and hosted at `chart.maryland.gov/thumbnails/`.

4. **SignalR hub** — The `/thumbnailHub` WebSocket endpoint on `chart.maryland.gov` pushes `Update` events to subscribed browser clients whenever new thumbnail frames are available.

5. **WZDx aggregator** — MDOT submits work-zone data to the RITIS (Regional Integrated Transportation Information System) platform at the University of Maryland CATT Lab, which re-publishes it as a public WZDx v4.1 GeoJSON feed.

6. **ArcGIS REST Services** — A spatial data server at `chartimap1.sha.maryland.gov/arcgis/rest/services/CHART` provides map tile and feature services for the interactive map component of the portal.

---

## Legal and Attribution

- All CHART data is published by the **Maryland State Highway Administration (SHA)**, a division of the **Maryland Department of Transportation (MDOT)**.
- Data is intended for public use. SHA does not restrict access to or redistribution of this data.
- The WZDx feed is published under the **CC0 1.0 Universal** license (public domain).
- No warranty is expressed or implied. Do not use for safety-critical navigation without independent verification.
- Attribution: "Data provided by Maryland CHART / MDOT SHA — https://chart.maryland.gov"

---

## Data Freshness

Live data verified on **2026-03-27** against production endpoints:

- 552 cameras indexed (484 online)
- 288 DMS signs indexed (186 with active messages)
- 295 speed sensors (264 online)
- 132 RWIS weather stations
- 36 active incidents, 44 active closures
- 49 WZDx work-zone features

---

*Client built by reverse-engineering the Maryland CHART portal at https://www.chart.maryland.gov*
