# ALDOT / ALGO Traffic API — Reverse-Engineered Python Client

A complete, stdlib-only Python client for the Alabama Department of Transportation (ALDOT) traffic information system, as exposed by [algotraffic.com](https://algotraffic.com).

---

## Background

ALGO Traffic is a React SPA built and maintained by the University of Alabama CAPS lab on behalf of ALDOT. All public traffic data is served from `api.algotraffic.com`, an ASP.NET / IIS backend sitting behind Imperva CDN. No API key or login is required to access public read endpoints.

### How It Was Reverse-Engineered

1. **HTML source** — `algotraffic.com` serves a single-page app with one JS bundle (`/static/js/main.js`, ~8 MB).
2. **JS bundle analysis** — The bundle was downloaded and searched for:
   - `"https://api.algotraffic.com"` string literals revealing the base URL.
   - The `jr()` function and its endpoint-path mapping objects (`Nr`, `Or`, `Ur`, `_r`) which map API version strings to resource path names.
   - Version variables: `kr = "v3.0"`, `Dr = "v4.0"`, `Br = kr` (default used in most slices).
   - Embedded JSON arrays (inside `JSON.parse(...)` calls) containing 551+ pre-seeded camera records.
   - Stream URLs pointing to Wowza CDN for HLS/DASH video.
3. **OIDC discovery** — `authentication.algotraffic.com/.well-known/openid-configuration` revealed an IdentityServer4 deployment used for the admin portal; public read APIs do not require tokens.
4. **Live testing** — Every endpoint was tested directly with `urllib.request`.

---

## API Overview

### Base URL

```
https://api.algotraffic.com
```

### Versions

| Version | Status | Notes |
|---------|--------|-------|
| `v3.0`  | Legacy | Cameras endpoint returns 404; others work |
| `v4.0`  | Current | Full feature set; recommended |
| `v4`    | Alias  | Used for binary resources (snapshots, map images) |

The version is a URL path segment:

```
https://api.algotraffic.com/v4.0/Cameras
https://api.algotraffic.com/v4.0/TrafficEvents
```

Binary image URLs use the short form:

```
https://api.algotraffic.com/v4/Cameras/{id}/snapshot.jpg
https://api.algotraffic.com/v4/Cameras/{id}/map@1x.jpg
```

### Authentication

**Public read endpoints: no authentication required.**

The server runs behind Imperva CDN and sets session cookies, but these are transparent — a plain `GET` with a standard `User-Agent` header works. The following headers are recommended to avoid bot-detection rejections:

```
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Accept: application/json
Origin: https://algotraffic.com
Referer: https://algotraffic.com/
```

An IdentityServer4 OIDC provider exists at `authentication.algotraffic.com` for administrative write operations (videoboards, user management). Scopes: `algotraffic_api`, `algoadmin_api`, `algovideo_api`, `algoreports_api`.

---

## Endpoint Reference

### Cameras

#### `GET /v4.0/Cameras`

Returns all 640+ public traffic cameras.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `county` | string | Filter by county name, e.g. `Jefferson` |
| `city` | string | Filter by city name, e.g. `Birmingham` |
| `region` | string | Filter by ALDOT region (see below) |

**ALDOT responsible regions:** `North`, `EastCentral`, `WestCentral`, `Southeast`, `Southwest`

**Response item schema:**

```json
{
  "id": 1845,
  "location": {
    "latitude": 30.535105,
    "longitude": -88.23953,
    "city": "Mobile",
    "county": "Mobile",
    "displayRouteDesignator": "I-10",
    "routeDesignator": "I-10",
    "routeDesignatorType": "Interstate",
    "stateRoadways": [{"name": "I-10", "type": "Interstate", "routeNumber": 10, "specialType": "None"}],
    "displayCrossStreet": "McDonald Rd",
    "crossStreet": "",
    "crossStreetType": "Unknown",
    "intersectingStateRoadways": [],
    "direction": "East",
    "linearReference": 10.5,
    "nearestRoadwayPoints": [{"direction": "East", "latitude": 30.5368, "longitude": -88.24037}]
  },
  "responsibleRegion": "Southwest",
  "playbackUrls": {
    "hls": "https://cdn3.wowza.com/5/.../playlist.m3u8",
    "dash": "https://cdn3.wowza.com/5/.../manifest.mpd"
  },
  "accessLevel": "Public",
  "mapLayer": "Camera",
  "permLink": "https://www.algotraffic.com?cameraId=1845",
  "snapshotImageUrl": "https://api.algotraffic.com/v4/Cameras/1845/snapshot.jpg",
  "mapImageUrl": "https://api.algotraffic.com/v4/Cameras/1845/map@1x.jpg"
}
```

#### `GET /v4.0/Cameras/{id}`

Returns a single camera by ID.

#### `GET /v4/Cameras/{id}/snapshot.jpg`

Returns the latest JPEG snapshot image (live, refreshed server-side). Typical size: 50–200 KB.

#### `GET /v4/Cameras/{id}/map@{scale}.jpg`

Returns a static map thumbnail centred on the camera location. `scale` is `1x` or `2x`.

#### `GET /v4.0/TrafficEvents/{id}/Cameras`

Returns cameras near a specific traffic event.

---

### Traffic Events

#### `GET /v4.0/TrafficEvents`

Returns all active and recent traffic events.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `active` | boolean | `true` = active events only |
| `type` | string | Event type filter (see below) |
| `severity` | string | Severity filter (see below) |

**Event types:** `Roadwork`, `Crash`, `Incident`, `RoadCondition`, `RegionalEvent`, `Facility`

**Severity levels:** `MinorDelay`, `ModerateDelay`, `MajorDelay`, `Unknown`

**Response item schema (abridged):**

```json
{
  "id": 1436916,
  "responsibleRegion": "WestCentral",
  "severity": "MinorDelay",
  "type": "Roadwork",
  "start": "2022-02-10T14:00:00Z",
  "end": "2026-07-03T22:00:00Z",
  "lastUpdatedAt": "2026-03-27T20:57:33Z",
  "active": true,
  "title": "Planned Roadway Improvements",
  "subTitle": "US11 NB/SB @ MP 98.07 to MP 103.9",
  "shortSubTitle": "US11 NB/SB @ MP 98.07 to MP 103.9",
  "description": "Roadwork with intermittent lane blockage...",
  "signStyle": {"type": "Temporary Traffic Control", "backgroundColor": {...}, "glyphColor": {...}},
  "startLocation": { ...location object... },
  "endLocation": { ...location object... },
  "laneDirections": [{"direction": "North", "lanes": [{"state": "Open", "type": "ThroughLane", "placement": 0}]}],
  "mapLayer": "Roadwork",
  "permLink": "https://www.algotraffic.com?eventId=1436916",
  "mapImageUrl": "https://api.algotraffic.com/v4/TrafficEvents/1436916/map@1x.jpg"
}
```

#### `GET /v4.0/TrafficEvents/{id}`

Returns a single traffic event.

---

### Travel Times

#### `GET /v4.0/TravelTimes`

Returns loop-detector travel time segments (48 segments statewide as of March 2026).

**Response item schema:**

```json
{
  "id": 2650,
  "origin": {
    "name": "I-165 N @ US-43/AL-13/BEAUREGARD ST",
    "displayPlaceName": "I-165",
    "city": null,
    "direction": "North",
    "stateRoadways": [...],
    "intersectingStateRoadways": [...]
  },
  "destination": {
    "name": "I-165 N @ I-65",
    ...
  },
  "lastUpdated": "2026-03-27T21:02:14Z",
  "expiresAt": "2026-03-27T21:11:02Z",
  "estimatedTimeMinutes": 6,
  "averageSpeedMph": 53,
  "totalDistanceMiles": 2.83,
  "name": "Mobile to I-65",
  "congestionLevel": "Minor"
}
```

**Congestion levels:** `Free`, `Minor`, `Moderate`, `Heavy`, `Severe`

---

### Dynamic Message Signs (DMS)

#### `GET /v4.0/MessageSigns`

Returns all 73 Dynamic Message Sign (DMS) boards and their current messages.

**Response item schema (abridged):**

```json
{
  "id": 1110,
  "responsibleRegion": "Southeast",
  "heightPixels": 30,
  "widthPixels": 105,
  "characterHeightPixels": 10,
  "characterWidthPixels": 5,
  "beaconType": "None",
  "beaconOn": false,
  "location": { ...location object... },
  "pages": [
    {
      "pageOnSeconds": 5,
      "pageOffSeconds": 0,
      "alignment": "None",
      "lines": [
        {"alignment": "Center", "flashOnSeconds": null, "flashOffSeconds": null, "text": "8 MILES"},
        {"alignment": "Center", "flashOnSeconds": null, "flashOffSeconds": null, "text": "7-9 MINS"}
      ]
    }
  ],
  "mapLayer": "MessageSign",
  "permLink": "https://www.algotraffic.com?messageSignId=1110",
  "mapImageUrl": "https://api.algotraffic.com/v4/MessageSigns/1110/map@1x.jpg"
}
```

#### `GET /v4.0/MessageSigns/{id}`

Returns a single message sign.

---

### Weather Alerts

#### `GET /v4.0/WeatherAlerts`

Returns active NWS weather alerts affecting Alabama, with polygon coverage zones.

**Response item schema (abridged):**

```json
{
  "id": "urn:oid:2.49.0.1.840.0...",
  "name": "Red Flag Warning",
  "headline": "Red Flag Warning issued March 27...",
  "description": "...",
  "instruction": "...",
  "sender": "NWS Birmingham AL",
  "severity": "severe",
  "urgency": "expected",
  "certainty": "likely",
  "response": "prepare",
  "messageType": "alert",
  "sent": "2026-03-27T15:58:00Z",
  "effective": "2026-03-27T15:58:00Z",
  "onset": "2026-03-28T12:00:00Z",
  "expiration": "2026-03-28T05:00:00Z",
  "end": "2026-03-29T00:00:00Z",
  "affectedAreas": [{"id": "ALZ011", "name": "Marion", "area": "AL", "type": "land"}, ...],
  "fillColor": {"red": 242, "green": 7, "blue": 134, "alpha": 0.2, "hex": "F20786"},
  "strokeColor": {...}
}
```

---

### Facilities (Rest Areas)

#### `GET /v4.0/Facilities`

Returns 27 ALDOT facilities (rest areas, welcome centers, etc.).

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | `RestArea`, `WelcomeCenter` |

---

### Service Assistance Patrols (ASAP)

#### `GET /v4.0/ServiceAssistancePatrols`

Returns the 5 ASAP coverage regions with route geometry.

```json
{
  "id": 1,
  "region": "North",
  "title": "Alabama Service Assistance Patrol",
  "subTitle": "North Region",
  "description": "ASAP provides motorist assistance...",
  "phoneNumber": null,
  "routes": [],
  "mapLayer": "ASAPCoverage",
  "mapImageUrl": "https://api.algotraffic.com/v4/ServiceAssistancePatrols/North/map@1x.jpg"
}
```

---

### ALEA Alerts (Amber / Silver / Blue / Missing Person)

#### `GET /v4.0/AleaAlerts`

Returns active Alabama Law Enforcement Agency public safety alerts.

```json
{
  "id": 1367,
  "type": "MissingChild",
  "url": "https://app.alea.gov/Community/wfAlertFlyer.aspx?ID=...",
  "title": "Missing Child - Landon Dominy",
  "text": "Landon Dominy, a White Male was last seen...",
  "publishDate": "2026-03-26T00:00:00Z",
  "images": [{"url": "https://api.algotraffic.com/v4.0/AleaAlerts/1367/Images/1367.jpg"}]
}
```

**Alert types:** `AmberAlert`, `SilverAlert`, `BlueAlert`, `MissingChild`

---

### Ferries

#### `GET /v4.0/Ferries`

Returns status for 2 Alabama river ferries.

---

### Geographic Reference

#### `GET /v4.0/Cities`

Returns the ~150 cities tracked by the system (`{id, name}` pairs).

#### `GET /v4.0/Counties`

Returns all 58 Alabama counties (`{id, name}` pairs).

#### `GET /v4.0/Zones`

Returns all 138 NWS weather zones covering Alabama.

---

## Python Client Usage

### Installation

No dependencies beyond the Python standard library. Requires Python 3.8+.

Copy `aldot_client.py` into your project.

### Quick Start

```python
from aldot_client import ALDOTClient

client = ALDOTClient()  # defaults to v4.0

# ---- Cameras ----
cameras = client.get_cameras()
print(f"{len(cameras)} cameras")

# Filter by county
mobile_cams = client.get_cameras(county="Mobile")

# Single camera
cam = client.get_camera(1845)
print(cam.location.city, cam.snapshot_url)

# Live JPEG snapshot (returns bytes)
jpeg = client.get_camera_snapshot(1845)
with open("cam_1845.jpg", "wb") as f:
    f.write(jpeg)

# Map thumbnail
thumb = client.get_camera_map_image(1845)

# Stream URL (HLS/DASH for video players)
print(cam.playback_urls.hls)

# ---- Traffic Events ----
events = client.get_traffic_events(active=True)
roadwork = client.get_traffic_events(event_type="Roadwork")
crashes  = client.get_traffic_events(event_type="Crash")

# Cameras near an event
cams_near = client.get_cameras_near_event(1436916)

# ---- Travel Times ----
for tt in client.get_travel_times():
    print(f"{tt.name}: {tt.estimated_time_minutes} min ({tt.congestion_level})")

# ---- Dynamic Message Signs ----
for sign in client.get_message_signs():
    texts = []
    for page in sign.pages:
        texts.extend(ln.text for ln in page.lines if ln.text)
    if texts:
        print(f"Sign #{sign.id} at {sign.location.display_route_designator}: {' | '.join(texts)}")

# ---- Weather Alerts ----
for alert in client.get_weather_alerts():
    print(f"[{alert.severity}] {alert.name} — {alert.sender}")

# ---- Rest Areas ----
for fac in client.get_facilities():
    print(fac.name, "open" if fac.open else "CLOSED")

# ---- ALEA Alerts ----
for alert in client.get_alea_alerts():
    print(f"[{alert.type}] {alert.title}")

# ---- Raw access for unlisted endpoints ----
data = client.raw_get("Cameras/1845/snapshot.jpg", accept="image/jpeg")
```

### Constructor Parameters

```python
ALDOTClient(
    api_version="v4.0",   # "v3.0" or "v4.0"
    timeout=30,            # HTTP timeout in seconds
    extra_headers={},      # Additional request headers
)
```

### Error Handling

```python
from aldot_client import ALDOTClient, ALDOTError

client = ALDOTClient()
try:
    cam = client.get_camera(99999)  # non-existent
except ALDOTError as e:
    print(f"API error {e.status_code}: {e}")
```

---

## Data Model Reference

### `Camera`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Unique camera ID |
| `location` | `Location` | Geographic location |
| `responsible_region` | `str` | ALDOT district |
| `playback_urls` | `PlaybackUrls` | HLS and DASH stream URLs |
| `access_level` | `str` | `"Public"` for public feeds |
| `snapshot_url` | `str` | Direct URL to latest JPEG snapshot |
| `map_image_url` | `str` | Static map thumbnail URL |
| `perm_link` | `str` | Deep link to algotraffic.com |

### `Location`

| Field | Type | Description |
|-------|------|-------------|
| `latitude` | `float` | WGS-84 latitude |
| `longitude` | `float` | WGS-84 longitude |
| `city` | `str` | City name |
| `county` | `str` | County name |
| `display_route_designator` | `str` | Human-readable road name, e.g. `"I-65"` |
| `route_designator` | `str` | Normalized designator, e.g. `"I-65"` |
| `route_designator_type` | `str` | `"Interstate"`, `"USHighway"`, `"StateHighway"`, `"Arterial"` |
| `display_cross_street` | `str` | Cross street / interchange name |
| `direction` | `str` | Camera / event facing direction |
| `linear_reference` | `float` | Mile-post reference |
| `state_roadways` | `List[StateRoadway]` | All routes at this location |

### `TrafficEvent`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Unique event ID |
| `type` | `str` | Event classification |
| `severity` | `str` | Delay level |
| `active` | `bool` | Whether event is currently active |
| `title` | `str` | Short title |
| `description` | `str` | Detailed description |
| `start_location` | `Location` | Start of affected roadway |
| `end_location` | `Location` | End of affected roadway |
| `lane_directions` | `List[LaneDirection]` | Per-direction lane state |

### `TravelTime`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Segment ID |
| `name` | `str` | Human-readable segment name |
| `origin` / `destination` | `TravelTimeEndpoint` | Endpoints |
| `estimated_time_minutes` | `int` | Current estimate |
| `average_speed_mph` | `float` | Average detector speed |
| `total_distance_miles` | `float` | Segment distance |
| `congestion_level` | `str` | `Free`, `Minor`, `Moderate`, `Heavy`, `Severe` |

---

## Caching Behaviour

The API sets `Cache-Control: max-age=N, public` headers:

| Resource | Cache TTL |
|----------|-----------|
| Camera list (`/Cameras`) | ~3 minutes |
| Traffic events | ~1 minute |
| Travel times | ~2 minutes |
| Snapshots | Browser default (use `?ts=...` to bust) |

The `x-total-count` response header carries the total record count before any server-side filtering is applied.

---

## Video Streaming

All cameras with `accessLevel: "Public"` have Wowza-CDN HLS streams:

```
https://cdn3.wowza.com/5/{token}/{region}-fastly/{cam-slug}.stream/playlist.m3u8
```

These can be played in any HLS-compatible player (VLC, ffplay, hls.js, etc.):

```bash
ffplay "https://cdn3.wowza.com/5/QVZyN3kwWHVGNE53/mobile-fastly/mob-cam-c095.stream/playlist.m3u8"
```

DASH manifests are also available at the same base path with extension `.mpd`.

---

## OIDC / Authentication (Admin Only)

The admin portal uses IdentityServer4 at `authentication.algotraffic.com`:

| Endpoint | URL |
|----------|-----|
| Discovery | `https://authentication.algotraffic.com/.well-known/openid-configuration` |
| Authorization | `https://authentication.algotraffic.com/connect/authorize` |
| Token | `https://authentication.algotraffic.com/connect/token` |
| Revocation | `https://authentication.algotraffic.com/connect/revocation` |

Scopes: `openid`, `profile`, `algotraffic_api`, `algoadmin_api`, `algovideo_api`, `algoreports_api`, `offline_access`

Grant types: `authorization_code`, `client_credentials`, `refresh_token`, `implicit`

---

## Notes and Limitations

- **No write operations are documented here.** Create/update/delete operations require ALDOT credentials and are not reverse-engineered.
- **Rate limiting** is not documented by ALDOT. Be courteous; cache aggressively.
- The `v3.0/Cameras` endpoint returns 404; use `v4.0/Cameras` instead.
- The `AldotMessages` endpoint (`/v4.0/AldotMessages`) returned empty responses in testing and may require authentication.
- Camera IDs appear to be allocated sequentially starting around 1100; not all IDs are valid.
- Some cameras have `accessLevel: "Restricted"` and may require login to view snapshots.
- The JS bundle also references a `v3/vRqVGhVVSbtxI` path which appears to be a test/internal endpoint.

---

## Live Test Results (2026-03-27)

| Endpoint | Count | Notes |
|----------|-------|-------|
| `GET /v4.0/Cameras` | 643 cameras | Filtered by county/city works |
| `GET /v4.0/TrafficEvents` | 176 events | 176 currently active |
| `GET /v4.0/TravelTimes` | 48 segments | All with speed data |
| `GET /v4.0/MessageSigns` | 73 signs | Current messages present |
| `GET /v4.0/WeatherAlerts` | 4 alerts | Red Flag Warnings active |
| `GET /v4.0/Facilities` | 27 facilities | Rest areas |
| `GET /v4.0/ServiceAssistancePatrols` | 5 regions | ASAP coverage |
| `GET /v4.0/AleaAlerts` | 12 alerts | Missing person alerts |
| `GET /v4.0/Ferries` | 2 ferries | Status data present |
| `GET /v4/Cameras/1845/snapshot.jpg` | 97,731 bytes | Valid JPEG |

---

## File

`aldot_client.py` — single-file Python module, stdlib only, no dependencies.
