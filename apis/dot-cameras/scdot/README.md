# 511SC SCDOT Traffic Information Client

> Python client for the South Carolina Department of Transportation (SCDOT) 511SC traveler information system — cameras, incidents, DMS signs, rest areas, evacuation routes, and more.

**No API key required.** All endpoints are publicly funded, publicly accessible, and unauthenticated.

---

## What This Does

South Carolina's [511SC.org](https://www.511sc.org) is powered by the **Iteris ATIS (Advanced Traveler Information System)** platform, version 1.2.6. It exposes a set of public GeoJSON and JSON API endpoints that feed the interactive map on the site. This client wraps all discovered endpoints in a clean Python interface.

**Live data available:**
- 752 traffic cameras with live snapshots (720x480 PNG, ~10s refresh) and HLS/RTSP/RTMP streams
- Active traffic incidents (crashes, hazards)
- 14+ traffic congestion zones on major interstates
- 13 Dynamic Message Signs (DMS) + 1 Variable Speed Limit sign
- 29 rest areas and welcome centers statewide (all currently open)
- 23 hurricane evacuation route points along the coast
- Travel alerts, general information, and special event notices

---

## Quick Start

```bash
# No installation needed — pure Python stdlib
python scdot_client.py
```

```python
from scdot_client import SCDOTClient

client = SCDOTClient()

# All cameras
cameras = client.get_cameras()
print(f"{len(cameras)} cameras statewide")

# Live snapshot URL for any camera
cam = client.get_camera("50001")
print(cam.snapshot_url)
# => https://scdotsnap.us-east-1.skyvdn.com/thumbs/50001.flv.png

# Download snapshot image
img_bytes = client.download_snapshot("50001")
with open("camera.png", "wb") as f:
    f.write(img_bytes)

# Active incidents
for inc in client.get_incidents():
    print(f"{inc.route} {inc.direction}: {inc.headline}")
```

---

## Requirements

- Python 3.7+ (uses `dataclasses`, `urllib`, `json` — all stdlib)
- No third-party dependencies
- Internet access to SCDOT/Iteris endpoints

---

## CLI Usage

```
python scdot_client.py [options]
```

| Flag | Description |
|------|-------------|
| *(no flags)* | Print a full live status summary |
| `--cameras` | List all cameras |
| `--cameras --active` | Active cameras only |
| `--jurisdiction NAME` | Filter cameras by city/region |
| `--route ROUTE` | Filter by route (e.g. `I-95`, `US 501`) |
| `--camera NAME` | Show a single camera by 5-digit name |
| `--incidents` | Show active incidents |
| `--dms` | Show Dynamic Message Signs |
| `--congestion` | Show congestion zones |
| `--rest-areas` | Show rest areas and welcome centers |
| `--evac-points` | Show hurricane evacuation points |
| `--news` | Show travel alerts and notices |
| `--save-snapshot NAME FILE` | Download a camera snapshot image |
| `--json` | Output everything as JSON |
| `--timeout N` | HTTP timeout in seconds (default: 30) |

**Examples:**

```bash
# Full status dashboard
python scdot_client.py

# All cameras in Columbia area
python scdot_client.py --cameras --jurisdiction Columbia

# Cameras on I-95
python scdot_client.py --cameras --route I-95

# Single camera detail + stream URLs
python scdot_client.py --camera 50001

# Download a live snapshot
python scdot_client.py --save-snapshot 50001 /tmp/myrtle_beach.png

# Active incidents as JSON
python scdot_client.py --incidents --json

# Export everything to JSON file
python scdot_client.py --json > scdot_data.json
```

---

## API Reference

### `SCDOTClient(timeout=30)`

Constructor. All methods make synchronous HTTP requests.

---

### `get_cameras(active_only=False, jurisdiction=None, route=None) -> List[Camera]`

Returns all traffic cameras. Results are sorted by jurisdiction, then camera name.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `active_only` | `bool` | Return only cameras where `active == True` |
| `jurisdiction` | `str` | Case-insensitive filter: `"Columbia"`, `"Myrtle Beach"`, `"Charleston"`, `"Greenville"`, `"Rock Hill"`, `"Florence"`, `"Charleston Beaches"`, `"Coastal Bridges"`, `"Gaffney"` |
| `route` | `str` | Case-insensitive substring filter: `"I-95"`, `"US 501"`, `"I-26"` |

**Camera fields:**

| Field | Type | Example | Description |
|-------|------|---------|-------------|
| `id` | `str` | `"e71ff390-d2a0-11e6-8996-0123456789ab"` | UUID |
| `name` | `str` | `"50001"` | 5-digit numeric label |
| `description` | `str` | `"US 501 N @ 16th Ave"` | Location text |
| `route` | `str` | `"US 501"` | Road designation |
| `direction` | `str` | `"NB"` | NB/SB/EB/WB/Median |
| `mrm` | `float\|None` | `18.5` | Mile reference marker |
| `jurisdiction` | `str` | `"Myrtle Beach"` | City/region |
| `latitude` | `float` | `33.845627` | WGS84 latitude |
| `longitude` | `float` | `-79.062775` | WGS84 longitude |
| `active` | `bool` | `True` | Camera operational? |
| `problem_stream` | `bool` | `False` | Stream issue flag |
| `snapshot_url` | `str` *(property)* | — | Live PNG image URL |
| `hls_url` | `str` *(property)* | — | HLS M3U8 playlist |
| `image_url` | `str` | — | Raw image_url from feed |
| `https_url` | `str` | — | HTTPS HLS URL |
| `ios_url` | `str` | — | iOS/Safari HLS URL |
| `rtsp_url` | `str` | — | RTSP stream |
| `rtmp_url` | `str` | — | RTMP stream |
| `preroll_url` | `str` | — | Pre-roll HLS segment |

---

### `get_camera(name) -> Optional[Camera]`

Get a single camera by its 5-digit name string.

```python
cam = client.get_camera("50001")
if cam:
    print(cam.hls_url)
```

---

### `get_camera_by_id(camera_id) -> Optional[Camera]`

Get a single camera by UUID.

---

### `download_snapshot(camera_name) -> bytes`

Download the live camera snapshot as raw PNG bytes.

```python
png = client.download_snapshot("50001")
with open("shot.png", "wb") as f:
    f.write(png)
```

Snapshots are 720x480 pixels, RGB PNG, refreshed approximately every 10 seconds.

---

### `get_stream_urls(camera_name) -> Dict[str, str]`

Get all streaming URLs for a camera by name.

```python
urls = client.get_stream_urls("50001")
# {
#   "snapshot": "https://scdotsnap.us-east-1.skyvdn.com/thumbs/50001.flv.png",
#   "hls":      "https://s18.us-east-1.skyvdn.com:443/rtplive/50001/playlist.m3u8",
#   "rtsp":     "rtsp://s18.us-east-1.skyvdn.com:554/rtplive/50001",
#   "rtmp":     "rtmp://s18.us-east-1.skyvdn.com:1935/rtplive/50001",
#   ...
# }
```

---

### `get_incidents(route=None, direction=None) -> List[Incident]`

Fetch active traffic incidents.

**Incident fields:**

| Field | Type | Example |
|-------|------|---------|
| `event_id` | `str` | `"event_1119833"` |
| `name` | `str` | `"D6-032726-08"` |
| `route` | `str` | `"I-95"` |
| `direction` | `str` | `"N"` |
| `mrm` | `str\|None` | `"85.000"` |
| `headline` | `str` | `"Crash"` |
| `road_type` | `str` | `"Interstates/Freeways"` |
| `cross_street` | `str` | `"MM 85"` |
| `location_description` | `str` | `"I-95N: at MM 85"` |
| `icon` | `str` | `"event"` |
| `latitude` | `float` | `33.309297` |
| `longitude` | `float` | `-80.553867` |

---

### `get_dynamic_message_signs(icon_type=None) -> List[DynamicMessageSign]`

Fetch all DMS and Variable Speed Limit signs.

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `icon_type` | `"dms"` for message signs, `"vsl"` for speed limit signs |

**DMS fields:**

| Field | Type | Example |
|-------|------|---------|
| `event_id` | `str` | `"dms_DMS_101"` |
| `dms_name` | `str` | `"101"` |
| `route` | `str` | `"I-126"` |
| `direction` | `str` | `"W"` |
| `mrm` | `str` | `"1"` or `"unavailable"` |
| `location_description` | `str` | `"I-126W @ MM 1"` |
| `road_type` | `str` | `"Interstates/Freeways"` |
| `icon` | `str` | `"dms"` or `"vsl"` |
| `county` | `str` | county name (often empty) |
| `latitude` | `float` | |
| `longitude` | `float` | |

---

### `get_congestion(route=None) -> List[TrafficCongestion]`

Fetch current congestion zones on SC highways.

**Congestion fields:**

| Field | Type | Example |
|-------|------|---------|
| `event_id` | `str` | `"event_125M056640..."` |
| `route` | `str` | `"I-26"` |
| `direction` | `str` | `"E"` |
| `cross_street` | `str` | exit description |
| `location_description` | `str` | full segment description |
| `latitude` | `float` | |
| `longitude` | `float` | |

---

### `get_rest_areas(include_welcome_centers=True, open_only=False, route=None) -> List[RestArea]`

Fetch rest areas and welcome centers.

**RestArea fields:**

| Field | Type | Example |
|-------|------|---------|
| `m_uuid` | `int` | `1042` |
| `facility_type` | `str` | `"Rest Area"` or `"Welcome Center"` |
| `title` | `str` | `"Rest Area I-20 West - Mile 94, Lugoff"` |
| `route` | `str` | `"I-20"` |
| `direction` | `str` | `"W"` |
| `mrm` | `str` | `"94"` |
| `location` | `str` | `"Lugoff"` |
| `description` | `str` | parking capacity info |
| `status` | `str` | `"open"` / `"closed"` |
| `seasonal` | `str` | `"year-round"` / `"n/a"` |
| `amenities` | `List[str]` | `["restroom", "picnic", "vending"]` |
| `latitude` | `float` | |
| `longitude` | `float` | |

**Amenity values observed:** `restroom`, `family_rr`, `picnic`, `pets`, `vending`, `travelinfo`, `internet`, `phone`, `parking`, `shelters`, `benches`, `trash`, `weather`

---

### `get_evacuation_points() -> List[EvacuationPoint]`

Fetch hurricane evacuation points along the SC coast.

These 23 points represent SCDOT-designated evacuation route guidance stations, each with specific routing instructions for different coastal zones (North Myrtle Beach, Garden City, McClellanville, etc.).

**EvacuationPoint fields:**

| Field | Type | Example |
|-------|------|---------|
| `m_uuid` | `int` | `138` |
| `content_id` | `int` | `28` |
| `facility_type` | `str` | `"Evacuation Point"` |
| `title` | `str` | `"North Myrtle Beach and Northward"` |
| `message` | `str` | `"Use SC 9 to proceed to I-95."` |
| `description` | `str` | detailed routing instructions |
| `latitude` | `float` | |
| `longitude` | `float` | |

---

### `get_news() -> NewsResponse`

Fetch travel alerts, general information, high priority notices, and special events.

**NewsResponse fields:**

| Field | Type | Description |
|-------|------|-------------|
| `travel_alerts` | `List[dict]` | Active road-condition advisories |
| `general_information` | `List[dict]` | Standard informational notices |
| `high_priority` | `List[dict]` | Urgent / emergency notices |
| `special_events` | `List[dict]` | Planned events affecting traffic |
| `is_empty` | `bool` *(property)* | True when all lists are empty |
| `all_items` | `List[NewsItem]` *(property)* | All items as a flat list |

```python
news = client.get_news()
if not news.is_empty:
    for alert in news.travel_alerts:
        print(alert)
```

---

### `get_special_events() -> List[dict]`

Fetch special events from the aggregator API as raw GeoJSON feature dicts.

---

### `get_nws_reports() -> dict`

Fetch National Weather Service weather report overlay (GeoJSON).

---

### `get_all_data() -> dict`

Fetch all data sources in one call. Returns a dict with keys: `cameras`, `incidents`, `dms`, `congestion`, `rest_areas`, `evacuation_points`, `news`.

```python
data = client.get_all_data()
import json
print(json.dumps(data, indent=2))
```

---

### `get_jurisdictions() -> List[str]`

Return a sorted list of all unique jurisdiction names from the camera feed.

Current jurisdictions (as of March 2026):
- Charleston
- Charleston Beaches
- Coastal Bridges
- Columbia
- Florence
- Gaffney
- Greenville
- Myrtle Beach
- Rock Hill

---

## Discovered Endpoints

All endpoints are unauthenticated HTTP GET requests returning JSON/GeoJSON.

### CDN GeoJSON Feeds

Base URL: `https://sc.cdn.iteris-atis.com/geojson/icons/metadata/`

| Path | Description | Refresh |
|------|-------------|---------|
| `icons.cameras.geojson` | All 752 traffic cameras | ~120s |
| `icons.incident.geojson` | Active incidents | ~120s |
| `icons.dms.geojson` | Dynamic Message Signs | ~120s |
| `icons.congestion.geojson` | Traffic congestion zones | ~120s |
| `icons.construction.geojson` | Construction zones | ~120s |
| `icons.weather.geojson` | Weather stations | ~120s |
| `../nws_report.json` | NWS weather alerts | ~600s |

Full GeoJSON CDN URL example:
```
https://sc.cdn.iteris-atis.com/geojson/icons/metadata/icons.cameras.geojson
```

### Aggregator API (Layer Types)

Base URL: `https://aggregator.iteris-atis.com/aggregator/services/layers/group/scdot/current/`

Append `?layer_type=VALUE` to filter:

| `layer_type` | Description |
|--------------|-------------|
| `rest_area` | Rest areas + welcome centers |
| `evacuation_point` | Hurricane evacuation points |
| `special_event` | Special traffic events |
| `evacuation_route` | Evacuation routes (currently empty) |
| `hurricane_evacuation` | Hurricane evac (currently empty) |

Example:
```
https://aggregator.iteris-atis.com/aggregator/services/layers/group/scdot/current/?layer_type=rest_area
```

### News / Alerts API

```
https://aggregator.iteris-sc511.net/aggregator/services/news/group/scdot/current
```

Returns JSON with four categorized arrays: `general_information`, `travel_alerts`, `high_priority`, `special_events`.

### Camera Image/Stream CDN

| Type | URL Pattern | Notes |
|------|-------------|-------|
| **Snapshot (PNG)** | `https://scdotsnap.us-east-1.skyvdn.com/thumbs/{name}.flv.png` | 720x480, live, ~10s refresh |
| **HLS/M3U8** | `https://s18.us-east-1.skyvdn.com:443/rtplive/{name}/playlist.m3u8` | For web/mobile video players |
| **RTSP** | `rtsp://s18.us-east-1.skyvdn.com:554/rtplive/{name}` | VLC, FFmpeg, security DVRs |
| **RTMP** | `rtmp://s18.us-east-1.skyvdn.com:1935/rtplive/{name}` | Legacy streaming |
| **Pre-roll** | `https://s18.us-east-1.skyvdn.com:443/preroll/{name}/playlist.m3u8` | Pre-roll segment |
| **CLSPS** | `clsps://s18.us-east-1.skyvdn.com:443/{name}` | Proprietary SkyVDN protocol |

Where `{name}` is the 5-digit camera name (e.g. `50001`).

All streams are served by **SkyVDN** (CDN partner) through a single server: `s18.us-east-1.skyvdn.com`.

---

## Camera Naming Conventions

Camera names follow a geographic pattern by jurisdiction:

| Name Range | Jurisdiction |
|------------|-------------|
| `10000–10999` | Columbia area |
| `30000–30999` | Greenville area |
| `40000–40999` | Rock Hill area |
| `50000–50999` | Myrtle Beach area |
| `60000–60999` | Charleston area |

---

## Playing HLS Streams

**VLC (command line):**
```bash
vlc "https://s18.us-east-1.skyvdn.com:443/rtplive/50001/playlist.m3u8"
```

**FFmpeg — capture 10 seconds:**
```bash
ffmpeg -i "https://s18.us-east-1.skyvdn.com:443/rtplive/50001/playlist.m3u8" \
       -t 10 -c copy camera_50001.mp4
```

**Python + urllib — download snapshot:**
```python
client = SCDOTClient()
img = client.download_snapshot("50001")
with open("cam.png", "wb") as f:
    f.write(img)
```

**HTML5 video (requires HLS.js for non-Safari):**
```html
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<video id="video" controls></video>
<script>
  const src = "https://s18.us-east-1.skyvdn.com:443/rtplive/50001/playlist.m3u8";
  if (Hls.isSupported()) {
    const hls = new Hls();
    hls.loadSource(src);
    hls.attachMedia(document.getElementById('video'));
  }
</script>
```

---

## Recipes

### Monitor all active incidents

```python
from scdot_client import SCDOTClient

client = SCDOTClient()
incidents = client.get_incidents()

if not incidents:
    print("No active incidents on SC highways.")
else:
    for inc in incidents:
        print(f"{inc.route:>6} {inc.direction:<2} | {inc.headline:<20} | {inc.location_description}")
```

### Find nearest rest area on I-95

```python
client = SCDOTClient()
i95_areas = client.get_rest_areas(route="I-95", open_only=True)
for area in i95_areas:
    print(f"MM {area.mrm:>6} {area.direction} — {area.title} ({', '.join(area.amenities)})")
```

### Get all cameras as GeoJSON

```python
import json
from scdot_client import SCDOTClient

client = SCDOTClient()
cameras = client.get_cameras()

geojson = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [cam.longitude, cam.latitude]
            },
            "properties": cam.to_dict()
        }
        for cam in cameras
    ]
}

with open("sc_cameras.geojson", "w") as f:
    json.dump(geojson, f)
```

### Continuous snapshot capture loop

```python
import time
from scdot_client import SCDOTClient

client = SCDOTClient()

camera_name = "50001"
interval = 30  # seconds

while True:
    try:
        img = client.download_snapshot(camera_name)
        ts = int(time.time())
        path = f"cam_{camera_name}_{ts}.png"
        with open(path, "wb") as f:
            f.write(img)
        print(f"Saved {path} ({len(img):,} bytes)")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(interval)
```

### Hurricane evacuation route lookup

```python
from scdot_client import SCDOTClient

client = SCDOTClient()
evac_points = client.get_evacuation_points()

print(f"SC Hurricane Evacuation Routes ({len(evac_points)} points)")
print()
for pt in evac_points:
    print(f"Zone: {pt.title}")
    print(f"  {pt.message}")
    print()
```

### Export full JSON snapshot of all live data

```python
import json
from scdot_client import SCDOTClient

client = SCDOTClient()
data = client.get_all_data()

with open("scdot_snapshot.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"Cameras:        {len(data['cameras'])}")
print(f"Incidents:      {len(data['incidents'])}")
print(f"DMS signs:      {len(data['dms'])}")
print(f"Congestion:     {len(data['congestion'])}")
print(f"Rest areas:     {len(data['rest_areas'])}")
print(f"Evac points:    {len(data['evacuation_points'])}")
```

---

## Platform Notes

The 511SC site is built on the **Iteris ATIS** (Advanced Traveler Information System) platform. Key infrastructure details:

| Component | Detail |
|-----------|--------|
| Platform | Iteris ATIS v1.2.6 |
| CDN | `sc.cdn.iteris-atis.com` (Iteris CDN) |
| Aggregator | `aggregator.iteris-atis.com` and `aggregator.iteris-sc511.net` |
| Camera CDN | SkyVDN (`scdotsnap.us-east-1.skyvdn.com`, `s18.us-east-1.skyvdn.com`) |
| Map | Mapbox GL JS |
| Analytics | Google Analytics (G-R2SK4XE9CT), Matomo (iteris-atis.com), GTM-5SC56N4 |
| Auth | None — all feeds are public |
| CORS | Open (no Origin restrictions on GeoJSON endpoints) |
| Data refresh | Every 120s for traffic feeds; 600s for radar/NWS |
| Camera count | 752 statewide (March 2026) |

The Mapbox public access token (`<MAPBOX_PUBLIC_TOKEN>

---

## Error Handling

All client methods raise standard Python exceptions:

| Exception | Cause |
|-----------|-------|
| `urllib.error.HTTPError` | Server returned 4xx/5xx |
| `urllib.error.URLError` | Network failure, DNS error, timeout |
| `json.JSONDecodeError` | Server returned malformed JSON |
| `ValueError` | Invalid parameter (e.g., camera not found in `get_stream_urls`) |

```python
import urllib.error
from scdot_client import SCDOTClient

client = SCDOTClient(timeout=10)

try:
    cameras = client.get_cameras()
except urllib.error.URLError as e:
    print(f"Network error: {e.reason}")
except urllib.error.HTTPError as e:
    print(f"Server error: {e.code} {e.reason}")
```

---

## Legal Notice

These are **publicly funded government data feeds** provided by the South Carolina Department of Transportation and published at 511sc.org for public consumption. This client accesses only the same data feeds consumed by the public-facing website, with no authentication bypass or terms of service violation. Usage should be reasonable and respectful of the public infrastructure — do not hammer endpoints at rates beyond what the site itself uses (approximately one request per feed per 120 seconds).

---

## Data Freshness

| Feed | Update Frequency |
|------|-----------------|
| Camera snapshots | ~10 seconds |
| Traffic incidents | ~120 seconds |
| Congestion zones | ~120 seconds |
| DMS signs | ~120 seconds |
| Rest areas | Static (changes rarely) |
| Evacuation points | Static (changes rarely, activated for hurricanes) |
| NWS reports | ~600 seconds |
| Travel news/alerts | ~120 seconds |

---

## Reverse Engineering Notes

The following methodology was used to discover these endpoints:

1. **HTML source analysis** — The main 511sc.org page includes inline JavaScript configuration with all GeoJSON CDN URLs, the Mapbox token, and auto-refresh intervals embedded as application config.

2. **Aggregator URL pattern** — The aggregator at `aggregator.iteris-atis.com` follows a consistent REST pattern: `/aggregator/services/layers/group/{state_code}/current/?layer_type={type}`. The `scdot` group code is inferred from the news endpoint and confirmed by testing.

3. **Two aggregator domains** — The news feed uses `aggregator.iteris-sc511.net` while layer data uses `aggregator.iteris-atis.com`. Both are Iteris infrastructure.

4. **SkyVDN camera URLs** — The camera stream URLs follow a predictable pattern: all cameras use a single SkyVDN server (`s18.us-east-1.skyvdn.com`) with the camera name as the stream key. The snapshot CDN uses a separate domain (`scdotsnap.us-east-1.skyvdn.com`).

5. **No authentication** — All endpoints return data on unauthenticated GET requests. The site does not use session cookies, Bearer tokens, or API keys for data access.
