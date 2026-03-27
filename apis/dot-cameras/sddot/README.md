# SDDOT Traffic Camera Client

Reverse-engineered Python client for the South Dakota Department of
Transportation (SDDOT) traffic information system at
**https://www.sd511.org**.

No API key or authentication is required.  All data is fetched from the
public CDN and aggregator endpoints used by the sd511.org web application.
The client uses **Python standard library only** (`urllib`, `json`,
`dataclasses`).

---

## Quick start

```python
from sddot_client import SDDOTClient

client = SDDOTClient()

# List all camera locations
cameras = client.get_cameras()
print(f"{len(cameras)} camera locations, "
      f"{sum(len(c.cameras) for c in cameras)} total views")

# Print image URLs for the first location
loc = cameras[0]
print(loc.name, loc.route)
for view in loc.cameras:
    print(f"  [{view.id}] {view.name}: {view.image_url}")
```

Run the built-in demo:

```bash
python3 sddot_client.py
```

---

## Reverse-engineering notes

### Target sites

| URL | Notes |
|-----|-------|
| `https://www.sd511.org/` | Main SDDOT 511 portal (redirects from `sd511.org`) |
| `https://www.safetravelusa.com/sd` | Mirror / alternate interface (blocked externally) |

### Infrastructure

The site is built and hosted by **Iteris ATIS** (Advanced Traffic
Information System).  All dynamic data is served from two separate
origins:

| Origin | Role |
|--------|------|
| `https://sd.cdn.iteris-atis.com/` | CloudFront CDN — GeoJSON feeds + camera images |
| `https://aggregator.iteris-atis.com/` | REST aggregator — layers (rest areas, POE, etc.) |
| `https://aggregator.iteris-sd511.net/` | REST aggregator — news/alerts (SD-specific subdomain) |

The frontend is a traditional jQuery + Mapbox GL JS application.  Key
JavaScript files discovered and analyzed:

```
/atis-static.iteriscdn.com/WebApps/SD/SafeTravel4/v1.0/js/
  map_preloaders.js         — loads GeoJSON feeds, refs cams_geo / rwis_geo vars
  map_cameras.js            — camera display & carousel logic
  generate_camera_tables.js — sidebar camera list UI
  map_utilities.js          — sorting, helpers
  prefs_base.js             — auth cookie check (CR511_Authentication)
  components/cameraViewer.js — modal camera viewer
```

### How variables are set

The main HTML page injects JavaScript configuration at the bottom before
the script includes:

```javascript
var base_cdn_url   = "https://sd.cdn.iteris-atis.com/";
var cams_geo       = base_cdn_url + "geojson/icons/metadata/icons.cameras.geojson";
var rwis_geo       = base_cdn_url + "geojson/icons/metadata/icons.rwis.geojson";
var acon_geo       = base_cdn_url + "geojson/icons/metadata/icons.road-work.geojson";
// ... etc.
var newsAggr       = "https://aggregator.iteris-sd511.net/aggregator/services/news/group/sddot/current/";
var linksAggr      = "https://aggregator.iteris-atis.com/aggregator/services/elements/group/sddot/current/";
```

### Authentication

The site uses a cookie `CR511_Authentication` for user-specific features
(favorite cameras, saved map preferences).  **All public read endpoints
work without any cookie.**  The `prefs-json.pl` server-side script handles
user preferences and requires the cookie.

---

## API endpoints

All endpoints are unauthenticated HTTP GET requests returning JSON or
GeoJSON.

### GeoJSON feeds (CDN)

Base URL: `https://sd.cdn.iteris-atis.com/`

| Endpoint path | Data type | Typical feature count |
|---------------|-----------|----------------------|
| `geojson/icons/metadata/icons.cameras.geojson` | CCTV camera locations | ~43 |
| `geojson/icons/metadata/icons.rwis.geojson` | RWIS weather stations | ~132 |
| `geojson/icons/metadata/icons.road-work.geojson` | Road construction events | variable |
| `geojson/icons/metadata/icons.incidents-accidents.geojson` | Traffic incidents | variable |
| `geojson/icons/metadata/icons.restriction.geojson` | Travel restrictions | variable |
| `geojson/icons/metadata/icons.disturbances.geojson` | Road disturbances | variable |
| `geojson/icons/metadata/icons.disasters.geojson` | Disaster-related events | variable |
| `geojson/icons/metadata/icons.obstructions.geojson` | Road obstructions | variable |
| `geojson/icons/metadata/icons.scheduled-events.geojson` | Scheduled events | variable |
| `geojson/icons/metadata/active_jurisdictions.geojson` | Active jurisdictions | usually empty |

All GeoJSON feeds are standard `FeatureCollection` objects with `features`
array.  Each feature has `id`, `geometry` (Point), and `properties`.

**Caching / refresh rate**: The CDN sets `Cache-Control: max-age=300`
(5 minutes) on GeoJSON files.  The sd511.org frontend polls every
`auto_refresh_rate = 120000` ms (2 minutes).

### Aggregator REST endpoints

Base URL: `https://aggregator.iteris-atis.com/`

| Full URL | Description |
|----------|-------------|
| `/aggregator/services/layers/group/sddot/current/?layer_type=rest_area` | Rest areas |
| `/aggregator/services/layers/group/sddot/current/?layer_type=Weight%20Stations%2FPorts%20of%20Entry` | Weigh stations |
| `/aggregator/services/layers/group/sddot/current/?layer_type=neighboring_state_511` | Neighboring state 511 links |
| `/aggregator/services/elements/group/sddot/current/` | Dashboard elements / site links |

News/alerts aggregator base URL: `https://aggregator.iteris-sd511.net/`

| Full URL | Description |
|----------|-------------|
| `/aggregator/services/news/group/sddot/current/` | Travel alerts by category |

### Camera image URLs

Still images are JPEG files hosted on the same CloudFront CDN:

```
https://sd.cdn.iteris-atis.com/camera_images/{LOCATION_ID}/{CAMERA_ID}/latest.jpg
```

- `LOCATION_ID`: the 6-character location code (e.g. `CSDATY`, `CSDBRD`)
- `CAMERA_ID`: integer index starting at `0` (e.g. `0`, `1`, `2`)

The `latest.jpg` filename is fixed; the file is overwritten in-place.
Images refresh every 2–5 minutes.  Headers include:

```
Cache-Control: max-age=300
Last-Modified: <timestamp>
ETag: <md5>
```

Example:
```
https://sd.cdn.iteris-atis.com/camera_images/CSDATY/1/latest.jpg
```

---

## Data structures

### Camera GeoJSON — feature schema

```json
{
  "type": "Feature",
  "id": "CSDATY",
  "geometry": {
    "type": "Point",
    "coordinates": [-97.06, 44.95]
  },
  "properties": {
    "name": "Watertown North",
    "route": "I-29",
    "mrm": "179",
    "cameras": [
      {
        "id": "0",
        "name": "Camera Looking North",
        "description": "Watertown-north of town along I-29 @ MP 179 looking north",
        "image": "https://sd.cdn.iteris-atis.com/camera_images/CSDATY/0/latest.jpg",
        "updateTime": 1774642068
      }
    ]
  }
}
```

### RWIS GeoJSON — feature schema

```json
{
  "type": "Feature",
  "id": "CSD3FK",
  "geometry": { "type": "Point", "coordinates": [-103.51337, 43.95073] },
  "properties": {
    "name": "Three Forks",
    "description": "US-16",
    "mrm": "45",
    "atmos": [{
      "air_temperature":      { "units": "Deg F",            "value": 41 },
      "wind_direction":       { "units": "Compass Degree",   "value": "ESE" },
      "wind_speed":           { "units": "Miles per Hour",   "value": 10 },
      "wind_gust":            { "units": "Miles per Hour",   "value": 18 },
      "relative_humidity":    { "units": "Percent",          "value": 39 },
      "dewpoint_temperature": { "units": "Deg F",            "value": 18 },
      "precip_rate":          { "units": "Inches per Hour",  "value": null },
      "precip_accumulated":   { "units": "Inches",           "value": null },
      "precip_type":          { "units": "Text",             "value": "None" },
      "precip_intensity":     { "units": "Text",             "value": "None" },
      "observation_time":     { "units": "Unixtime",         "value": "1774642399" }
    }],
    "surface": [{
      "elevation":            { "units": "Feet",  "value": "1445" },
      "surface_temperature":  { "units": "Deg F", "value": null },
      "surface_condition":    { "units": "",       "value": null },
      "friction":             { "units": "",       "value": null },
      "observation_time":     { "units": "Unixtime", "value": "1774642399" }
    }],
    "cameras": [ { "id": "0", "name": "...", "image": "...", "updateTime": 0 } ]
  }
}
```

### Traffic event GeoJSON — feature schema

```json
{
  "type": "Feature",
  "id": "some_id",
  "geometry": { "type": "Point", "coordinates": [-101.2, 44.3] },
  "properties": {
    "event_id":            "12891858",
    "route":               "I-90",
    "dir":                 "Both Directions",
    "headline":            "Road work: grading",
    "location_description": "I-90 from 2.75 miles west to 1 mile west of Mount Vernon",
    "report":              "Grading in the median with lanes reduced ...",
    "mrm":                 "318.414",
    "start_time":          1774273740,
    "end_time":            null,
    "url":                 "https://...",
    "label":               "I-90<br>from ..."
  }
}
```

### Rest area feature schema

```json
{
  "type": "Feature",
  "id": "RestArea_7151",
  "geometry": { "type": "Point", "coordinates": [-104.034, 44.545] },
  "properties": {
    "title":        "Northern Hills EB",
    "description":  "Welcome Center",
    "route":        "I-90",
    "dir":          "E",
    "mrm":          "1",
    "status":       "open",
    "seasonal":     "year-round",
    "amenities":    ["hc_access", "vending", "picnic", "pets", "parking"],
    "image_url":    "https://sd-west.s3.us-west-2.amazonaws.com/...",
    "facility_type": "Rest Area",
    "m_uuid":       7151
  }
}
```

Amenity codes:

| Code | Meaning |
|------|---------|
| `hc_access` | Handicap-accessible |
| `vending` | Vending machines |
| `picnic` | Picnic area |
| `pets` | Pet area |
| `parking` | Vehicle parking |
| `dump_station` | RV dump station |
| `family_rr` | Family restroom |
| `travel_info` | Travel information |
| `historical` | Historical site |

### News/alerts response schema

```json
{
  "general_information": [],
  "travel_alerts": [],
  "high_priority": [],
  "special_events": []
}
```

Each item in a category list:

```json
{
  "title": "...",
  "header": "...",
  "message": "...",
  "url": "...",
  "position": 1,
  "content_type": "HTML",
  "section": "...",
  "status": 1
}
```

---

## Client API reference

### `SDDOTClient(timeout=20)`

Constructor.  `timeout` sets the default HTTP request timeout in seconds.

#### Camera methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_cameras()` | `List[CameraLocation]` | All CCTV camera locations |
| `get_camera_image_url(location_id, camera_id)` | `str` | Build still image URL |
| `download_camera_image(location_id, camera_id, save_path)` | `str` | Download JPEG to disk |

#### RWIS methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_rwis_stations()` | `List[RWISStation]` | All RWIS stations with weather data |

#### Traffic event methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_road_work()` | `List[TrafficEvent]` | Active construction events |
| `get_incidents()` | `List[TrafficEvent]` | Active incidents/crashes |
| `get_restrictions()` | `List[TrafficEvent]` | Active travel restrictions |
| `get_disturbances()` | `List[TrafficEvent]` | Active disturbances |
| `get_disasters()` | `List[TrafficEvent]` | Active disaster events |
| `get_obstructions()` | `List[TrafficEvent]` | Active obstructions |
| `get_scheduled_events()` | `List[TrafficEvent]` | Upcoming scheduled events |
| `get_all_events()` | `List[TrafficEvent]` | All event types combined |

#### Infrastructure methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_rest_areas()` | `List[RestArea]` | All rest areas with amenities/status |
| `get_ports_of_entry()` | `List[dict]` | Raw weigh station features |
| `get_news_alerts()` | `Dict[str, List[NewsAlert]]` | Travel news by category |
| `get_site_elements()` | `List[dict]` | Dashboard content elements |

#### Convenience methods

| Method | Returns | Description |
|--------|---------|-------------|
| `filter_cameras_by_route(cameras, route)` | `List[CameraLocation]` | Filter by route name |
| `filter_events_by_route(events, route)` | `List[TrafficEvent]` | Filter events by route |
| `get_nearest_cameras(lat, lon, cameras=None, limit=5)` | `List[Tuple[float, CameraLocation]]` | Sorted by distance (km) |
| `get_route_summary(route)` | `dict` | Cameras + events for one route |

---

## Dataclasses

### `CameraLocation`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Location code (e.g. `"CSDATY"`) |
| `name` | `str` | Human-readable name |
| `route` | `str` | Highway (e.g. `"I-29"`) |
| `mile_marker` | `str` | Mile reference marker |
| `longitude` | `float` | WGS-84 longitude |
| `latitude` | `float` | WGS-84 latitude |
| `cameras` | `List[CameraView]` | Individual camera views |

### `CameraView`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | View index within location |
| `name` | `str` | Direction/type label |
| `description` | `str` | Full description text |
| `image_url` | `str` | Direct JPEG URL |
| `update_time` | `int` | Unix timestamp of last image |
| `update_dt` *(property)* | `str` | ISO-8601 formatted timestamp |

### `RWISStation`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Station code |
| `name` | `str` | Location name |
| `description` | `str` | Route/description |
| `mile_marker` | `str` | Mile reference marker |
| `longitude` / `latitude` | `float` | Coordinates |
| `cameras` | `List[CameraView]` | Attached cameras |
| `atmos` | `List[AtmosphericReading]` | Weather readings |
| `surface` | `List[SurfaceReading]` | Road surface readings |
| `latest_atmos` *(property)* | `Optional[AtmosphericReading]` | Most recent weather |
| `latest_surface` *(property)* | `Optional[SurfaceReading]` | Most recent surface |

### `TrafficEvent`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Feature ID |
| `event_id` | `str` | SDDOT event identifier |
| `event_type` | `str` | Category string |
| `route` | `str` | Highway |
| `direction` | `str` | Travel direction |
| `headline` | `str` | Short description |
| `location_description` | `str` | Full text location |
| `report` | `str` | Detailed report text |
| `mile_marker` | `str` | Mile reference marker |
| `start_time` | `int` | Unix timestamp |
| `end_time` | `Optional[int]` | Unix timestamp or `None` |
| `longitude` / `latitude` | `float` | Coordinates |
| `url` | `Optional[str]` | Related URL |

---

## Usage examples

### Download a camera image

```python
from sddot_client import SDDOTClient

client = SDDOTClient()

# Download the first view of the Rapid City West camera
client.download_camera_image("CSDRCW", "0", "/tmp/rapid_city_west.jpg")
print("Saved!")
```

### Get all I-90 road work

```python
from sddot_client import SDDOTClient

client = SDDOTClient()
events = client.get_road_work()
i90_work = client.filter_events_by_route(events, "I-90")

for evt in i90_work:
    print(f"[MM {evt.mile_marker}] {evt.headline}")
    print(f"  {evt.location_description}")
    print(f"  {evt.report[:100]}...")
```

### Find cameras near a GPS location

```python
from sddot_client import SDDOTClient

client = SDDOTClient()
cameras = client.get_cameras()

# Sioux Falls, SD
nearest = client.get_nearest_cameras(43.549, -96.700, cameras=cameras, limit=5)
for dist_km, loc in nearest:
    print(f"{loc.name} ({loc.route}) — {dist_km:.1f} km")
    print(f"  Image: {loc.get_image_url()}")
```

### Current weather at RWIS stations

```python
from sddot_client import SDDOTClient

client = SDDOTClient()
stations = client.get_rwis_stations()

for st in stations:
    a = st.latest_atmos
    s = st.latest_surface
    if a and a.air_temperature is not None:
        print(f"{st.name} ({st.description} MM {st.mile_marker}): "
              f"{a.air_temperature}°F, "
              f"wind {a.wind_speed} mph {a.wind_direction}")
        if s and s.surface_condition:
            print(f"  Road: {s.surface_condition}, {s.surface_temperature}°F")
```

### Full route summary

```python
from sddot_client import SDDOTClient

client = SDDOTClient()
summary = client.get_route_summary("I-90")

print(f"I-90 Summary")
print(f"  Cameras: {len(summary['cameras'])}")
print(f"  Road work: {len(summary['road_work'])} events")
print(f"  Restrictions: {len(summary['restrictions'])} events")
print(f"  Incidents: {len(summary['incidents'])} events")
```

### Check rest area status

```python
from sddot_client import SDDOTClient

client = SDDOTClient()
rest_areas = client.get_rest_areas()

open_areas = [ra for ra in rest_areas if ra.status == "open"]
print(f"{len(open_areas)} of {len(rest_areas)} rest areas are open")

for ra in open_areas:
    print(f"  {ra.title} ({ra.route} {ra.direction})")
    print(f"    Amenities: {', '.join(ra.amenities)}")
```

---

## Limitations

- **No live video streams**: The site supports HLS / RTMP streams for some
  cameras (`http_protocol` / `rtmp_protocol` variables in the JS), but the
  stream URLs are not exposed in the public GeoJSON feed.  Only JPEG still
  images are available without authentication.

- **User-specific features require login**: Favorite cameras, saved map
  preferences, and personalized views use the `CR511_Authentication` session
  cookie and the `prefs-json.pl` server-side script.  These are not
  implemented in this client.

- **Rate limiting**: No explicit rate limiting has been observed on the CDN,
  but the site's own polling interval is 120 seconds.  Polling more
  aggressively is not recommended.

- **No historical data**: All endpoints return current/live data only.  No
  historical archive is publicly exposed.

- **Camera count may change**: The number of camera locations and views is
  determined by SDDOT's operational inventory.  Cameras are added/removed as
  infrastructure changes.

---

## Files

| File | Description |
|------|-------------|
| `sddot_client.py` | Complete Python client (stdlib only) |
| `sddot_README.md` | This documentation |

---

## Legal notice

This client uses only publicly accessible endpoints on the official South
Dakota DOT 511 system.  The data is intended for public use.  No
authentication was bypassed.  Use responsibly and in accordance with
SDDOT's terms of service.
