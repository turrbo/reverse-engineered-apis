# WVDOT 511WV Traffic Camera API Client

Reverse-engineered Python client for the West Virginia Department of Transportation's public 511 traffic information system at **https://www.wv511.org**.

## Overview

The 511WV system exposes a set of unauthenticated HTTP endpoints under `/wsvc/gmap.asmx/` that power the interactive traffic map. This client wraps those endpoints in a clean Python API using only the standard library (`urllib`, `json`, `html`, `re`, `xml.etree.ElementTree`, `dataclasses`).

---

## How the System Works

### Architecture

The site runs on **ASP.NET 4.x** behind **CloudFront CDN**. The interactive map is rendered in an iframe (`/webmapi.aspx`) and communicates with a backend web service layer at `/wsvc/gmap.asmx`.

Data flows like this:

```
Browser  →  /webmapi.aspx (iframe)  →  loads JS bundles
                                         │
                              ┌──────────┴──────────────┐
                              │                         │
                        /wsvc/gmap.asmx/*           Google Maps API
                        (KML / JSON / GeoJSON        (tiles, geocoding)
                         endpoints – public)
```

### Camera Data

Cameras are loaded by the JS file `/wsvc/gmap.asmx/buildCamerasJSONjs`. Despite the `.asmx` extension (indicating an ASP.NET Web Service), the response is a **JavaScript file** (not JSON) containing two variable assignments:

```javascript
var camera_data = { "count": 126, "cams": [...] };
var camera_data_ptc = { "count": N, "cams": [...] };
```

Each camera object has:

| Field | Type | Description |
|-------|------|-------------|
| `md5` | string | Camera ID, e.g. `"CAM117"` |
| `origin` | string | Internal database key |
| `title` | string | Road name, e.g. `"I-81"` |
| `description` | string | HTML-encoded blob with location label and stream type |
| `start_lat` | string | Latitude |
| `start_lng` | string | Longitude |
| `icon` | string | Icon style: `"icon_feed"`, `"icon_dead"`, `"icon_gens"` |
| `ev_radius` | null/float | Event radius (usually null) |

The `description` field contains HTML comments `<!--STREAMING:1-->` or `<!--STREAMING:0-->` that indicate whether live video is available.

### Live Video Streaming

All 126 cameras stream via **HLS (HTTP Live Streaming)**. The streaming infrastructure is hosted at `vtc1.roadsummary.com`. The URL pattern is:

```
https://vtc1.roadsummary.com/rtplive/{CAM_ID}/playlist.m3u8
```

Example: `https://vtc1.roadsummary.com/rtplive/CAM117/playlist.m3u8`

The streaming URL is confirmed in the camera player page at:
```
https://www.wv511.org/flowplayeri.aspx?CAMID={CAM_ID}
```

The player uses `hls.js` (version 1.6.10) to load and play the HLS stream.

**Note:** The `vtc1.roadsummary.com` server returned 404 for streams tested during analysis, suggesting streams may require camera hardware to be active. The HLS endpoint is still the correct format.

### Event/Incident Data (KML)

Traffic events, construction zones, and incidents are served as **KML** files. The KML namespace used is `https://www.opengis.net/kml/2.2`. Each `<Placemark>` contains:
- `id` attribute: unique event identifier
- `<name>`: event title (CDATA)
- `<description>`: detailed HTML description (CDATA)
- `<coordinates>`: `longitude,latitude,0`
- `<ExtendedData>`: additional key/value pairs (e.g., `MileRange`)

### Dynamic Message Signs (DMS)

DMS signs are returned as KML. Signs with `isActive=1` are currently displaying a message; `isActive=0` returns all signs including blank ones.

### Weather

Weather forecasts are KML placemarks, one per West Virginia county. Each description is an HTML table with 7-day forecast data pulled from the **National Weather Service API** (`api.weather.gov`).

### GeoJSON Endpoints

Two endpoints return GeoJSON FeatureCollections:
- **Waze Alerts**: crowd-sourced traffic incidents from Waze integration
- **EV Charging Stations**: alternative fuel stations filtered by connector type

---

## API Endpoints Reference

| Method | Path | Returns | Notes |
|--------|------|---------|-------|
| GET | `/wsvc/gmap.asmx/buildCamerasJSONjs` | JavaScript | Camera list (parse JSON from variable) |
| GET | `/flowplayeri.aspx?CAMID={id}` | HTML | Camera player; contains HLS URL |
| GET | `https://vtc1.roadsummary.com/rtplive/{id}/playlist.m3u8` | m3u8 | HLS stream |
| GET | `/wsvc/gmap.asmx/buildEventsKMLc` | KML | Construction events |
| GET | `/wsvc/gmap.asmx/buildEventsKMLi_Filtered?CategoryIDs=` | KML | Incidents |
| GET | `/wsvc/gmap.asmx/buildEventsKMLs` | KML | Special events |
| GET | `/wsvc/gmap.asmx/buildPlannedEventsActiveKML` | KML | Active planned events |
| GET | `/wsvc/gmap.asmx/buildPlannedEventsFutureKML` | KML | Future planned events |
| GET | `/wsvc/gmap.asmx/buildDMSKML?isActive=1` | KML | Active DMS signs |
| GET | `/wsvc/gmap.asmx/buildDMSKML?isActive=0` | KML | All DMS signs |
| GET | `/wsvc/gmap.asmx/buildWeatherKML` | KML | County weather forecasts |
| GET | `/wsvc/gmap.asmx/buildWeatherAlertsKML` | KML | NWS weather alerts |
| GET | `/wsvc/gmap.asmx/buildWeatherAlertPolysKML` | KML | Weather alert polygons |
| GET | `/wsvc/gmap.asmx/buildWinterRCPolysKML` | KML | Winter road conditions |
| GET | `/wsvc/gmap.asmx/buildRwisKML` | KML | RWIS weather stations |
| GET | `/wsvc/gmap.asmx/buildFacilitiesFilteredKML?TypesCSV=RA` | KML | Rest areas |
| GET | `/wsvc/gmap.asmx/buildFacilitiesFilteredKML?TypesCSV=IC` | KML | Welcome/info centers |
| GET | `/wsvc/gmap.asmx/buildParkRideKML` | KML | Park & ride lots |
| GET | `/wsvc/gmap.asmx/buildTollBoothsKML` | KML | Toll booths |
| GET | `/wsvc/gmap.asmx/buildTruckWeighStationsKML` | KML | Truck weigh stations |
| GET | `/wsvc/gmap.asmx/buildTruckParkingStationsKML` | KML | Truck parking |
| GET | `/wsvc/gmap.asmx/buildTruckRunawayRampsKML` | KML | Runaway truck ramps |
| GET | `/wsvc/gmap.asmx/buildTruckSteepGradesKML` | KML | Steep grades |
| GET | `/wsvc/gmap.asmx/buildRoutePolysClosedKML` | KML | Road closure polygons |
| GET | `/wsvc/gmap.asmx/buildRoutePolysRestrictionsKML` | KML | Restriction polygons |
| GET | `/wsvc/gmap.asmx/GetWazeAlertsByTypesGeoJSON?WazeTypesBitmask=65535` | GeoJSON | Waze alerts |
| GET | `/wsvc/gmap.asmx/GetAltFuelStationsByEvConnectorTypesGeoJSON?ConnectorTypesBitmask=255` | GeoJSON | EV stations |

**Cache-busting:** All KML endpoints require a `nocache` query parameter. Pass any changing value (timestamp, date string). Without it, CloudFront may serve a stale cached response.

**Authentication:** None required. All endpoints are publicly accessible.

**Rate limiting:** Not explicitly documented. The site refreshes data every 3–10 minutes on the client side. Matching that cadence is safe.

---

## Installation

No dependencies. Requires Python 3.7+.

```bash
# Copy wvdot_client.py to your project
cp wvdot_client.py my_project/
```

---

## Usage

### Quick start

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()

# Get all cameras
cameras = client.cameras()
print(f"Found {len(cameras)} cameras")
for cam in cameras[:5]:
    print(cam)
```

### Working with cameras

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()
cameras = client.cameras()

# Find cameras on I-77
i77_cams = [c for c in cameras if "I-77" in c.title]
print(f"I-77 cameras: {len(i77_cams)}")

for cam in i77_cams:
    print(f"  {cam.cam_id}: {cam.location_label}")
    print(f"  Stream: {cam.hls_url}")
    print(f"  Player: {cam.player_url}")
    print(f"  Coords: ({cam.lat}, {cam.lng})")
    print()
```

### Getting an HLS stream URL

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()

# Method 1: Directly construct (no network call)
cam_id = "CAM117"
hls_url = f"https://vtc1.roadsummary.com/rtplive/{cam_id}/playlist.m3u8"

# Method 2: Confirm from the player page (makes an HTTP request)
confirmed_url = client.camera_stream_url("CAM117")
print(confirmed_url)
# → https://vtc1.roadsummary.com/rtplive/CAM117/playlist.m3u8

# Play with ffmpeg:
# ffmpeg -i "https://vtc1.roadsummary.com/rtplive/CAM117/playlist.m3u8" -frames:v 1 frame.jpg
```

### Traffic incidents and construction

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()

# Construction zones
construction = client.construction_events()
print(f"Active construction events: {len(construction)}")
for ev in construction:
    print(f"  [{ev.placemark_id[:8]}] {ev.name}")
    print(f"    {ev.description[:100]}")
    print(f"    Location: ({ev.lat:.5f}, {ev.lng:.5f})")

# All incidents (no category filter)
incidents = client.incident_events()
print(f"\nIncidents: {len(incidents)}")

# Planned events currently active
active = client.active_planned_events()
print(f"Active planned events: {len(active)}")
```

### Weather data

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()

# 7-day county forecasts
forecasts = client.weather_forecasts()
print(f"Counties with forecasts: {len(forecasts)}")
for f in forecasts[:5]:
    print(f"  {f.name}: ({f.lat:.4f}, {f.lng:.4f})")
    # description contains an HTML table with forecast icons/temps
    # parse it or display as-is

# Active weather alerts
alerts = client.weather_alerts()
print(f"\nActive weather alerts: {len(alerts)}")
for a in alerts:
    print(f"  {a.name}: {a.description[:80]}")
```

### Dynamic Message Signs (DMS)

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()

# Signs currently showing a message
active_signs = client.dms_signs(active_only=True)
print(f"Active DMS signs: {len(active_signs)}")
for sign in active_signs:
    print(f"  {sign.name}: {sign.description[:60]}")

# All signs, including blank/inactive
all_signs = client.dms_signs(active_only=False)
print(f"\nTotal DMS signs: {len(all_signs)}")
```

### Waze alerts and EV stations

```python
from wvdot_client import WVDOTClient

client = WVDOTClient()

# Waze crowd-sourced alerts
waze = client.waze_alerts()
print(f"Waze alerts: {len(waze)}")
for w in waze[:5]:
    props = w.properties
    print(f"  Type: {props.get('type')} | {props.get('subtype')}")
    print(f"  Location: {w.coordinates}")

# EV charging stations
ev_stations = client.ev_charging_stations()
print(f"\nEV charging stations: {len(ev_stations)}")
for s in ev_stations[:3]:
    print(f"  {s.properties.get('name') or s.feature_id}")
```

### Functional API (no class)

All functions are available as module-level calls:

```python
from wvdot_client import (
    get_cameras,
    get_construction_events,
    get_weather_forecasts,
    get_dms_signs,
    get_waze_alerts,
)

cameras = get_cameras()
events = get_construction_events()
forecasts = get_weather_forecasts()
```

### Running the built-in smoke test

```bash
python3 wvdot_client.py
```

This runs `_run_smoke_test()` which exercises all major endpoints and prints a summary.

---

## Data Classes

### `Camera`

```
Camera(
    cam_id: str,           # "CAM117"
    origin: str,           # internal DB key
    title: str,            # road name
    description_raw: str,  # raw HTML from API
    lat: float,
    lng: float,
    icon: str,             # "icon_feed" | "icon_dead" | "icon_gens"
    ev_radius: float|None,
    location_label: str,   # human-readable location, e.g. "[BER]I-81 @ 0.5"
    is_streaming: bool,    # True if live HLS stream is available
)
```

Properties:
- `.hls_url` → `str`: HLS m3u8 stream URL
- `.player_url` → `str`: embedded player page URL

### `KmlPlacemark`

```
KmlPlacemark(
    placemark_id: str,  # KML id attribute
    name: str,
    description: str,   # HTML content
    lat: float,
    lng: float,
    style_url: str,
    extra: dict,        # ExtendedData key/value pairs
)
```

### `GeoJsonFeature`

```
GeoJsonFeature(
    feature_id: str|None,
    geometry_type: str,   # "Point", "LineString", etc.
    coordinates: any,     # geometry coordinates
    properties: dict,     # all GeoJSON properties
)
```

---

## Camera Routes Available

From the site's route dropdown (for filtering camera listings):

- Interstates: I-64, I-68, I-70, I-77, I-79, I-81, I-470
- US Routes: US-19, US-35, US-50, US-60, US-119, US-219, US-340, US-460
- WV Routes: WV-7, WV-9, WV-43, WV-46, WV-48, WV-705
- Special: ChestnutRidge, Elmer Prince, University Dr.

---

## Notes on Reverse Engineering

### JavaScript files analyzed

| File | Purpose |
|------|---------|
| `/js/gmapi.min.js` | Main map initialization; loads all KML layers |
| `/js/gmapi.cams.min.js` | Camera marker clustering and click handlers |
| `/js/flowplayi.min.js` | HLS streaming player (calls `/flowplayeri.aspx`) |
| `/js/CameraListing.min.js` | Camera listing page interactions |
| `/js/cam_stream_timeout.js` | 30-minute stream timeout logic |
| `/js/getScripts.min.js` | Async script loader utility |

### Infrastructure

- **Web tier**: Microsoft IIS 10.0, ASP.NET 4.0 (`x-aspnet-version: 4.0.30319`)
- **CDN**: AWS CloudFront (`via: 1.1 ...cloudfront.net`)
- **Streaming**: `vtc1.roadsummary.com` — custom KVDS (Kite Video Delivery System?) server
- **Icons**: hosted at `www.511wv.cloud.ilchost.com`
- **Analytics**: Google Analytics (UA-47268490-2, G-9EN3T0JE03), Google Tag Manager (GTM-K594K3L)
- **Maps**: Google Maps API key `AIzaSyCZoPotiNHHwz-4uxreP0sJNrKoZ0xu3rM` (maps tiles only, not required for data)

### Authentication

No authentication is required for any data endpoint. The site has a user login system (`/personalAlerts/`) for saved preferences and camera tours, but the data APIs are fully public.

The only auth-related endpoint found:
```
GET /personalAlerts/DecryptUser.ashx?v={encrypted_cookie}
```
This decrypts a user session cookie and returns `{ "ok": true, "data": { "first_name": "..." } }`. Not needed for camera data.

---

## License / Terms

This client interacts with a public government website. All data is public information published by the West Virginia Department of Transportation. Please be respectful of server resources — cache responses appropriately and avoid excessive polling. The data refreshes approximately every 3–10 minutes on the live site.
