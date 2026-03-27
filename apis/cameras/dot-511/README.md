# DOT 511 Unified Camera Client

A unified Python client for accessing highway traffic camera systems across multiple US states. All states use the same underlying **Iteris/RITIS platform** with an identical REST API structure.

---

## Supported States

| Code | State        | API Version | Developer Page |
|------|-------------|-------------|----------------|
| `ny` | New York    | v1 (legacy) | https://511ny.org/developers/help |
| `wi` | Wisconsin   | v2          | https://www.511wi.gov/developers/doc |
| `pa` | Pennsylvania| v2          | https://www.511pa.com/developers/doc |
| `ak` | Alaska      | v2          | https://511.alaska.gov/developers/doc |
| `ut` | Utah        | v2          | https://udottraffic.utah.gov/developers/doc |
| `mn` | Minnesota   | v2          | https://www.511mn.org/developers/doc |
| `va` | Virginia    | v2          | https://www.511va.org/developers/doc |
| `ia` | Iowa        | v2          | https://511ia.org/developers/doc |

---

## API Overview

### Authentication

Every state requires a free Developer API key obtained by registering an account at the state's `/my511/register` URL. The key is passed as a query parameter:

```
GET https://{state-host}/api/v2/get/cameras?key={YOUR_KEY}&format=json
```

**Rate limit:** 10 calls per 60 seconds per state.

### API Versions

**v1 (New York only - legacy)**
```
GET https://511ny.org/api/getcameras?key={KEY}&format=json
```
Response fields:
- `ID` - unique camera identifier
- `Name` - camera location description
- `RoadwayName` - road/highway name
- `DirectionOfTravel` - direction string
- `Latitude` / `Longitude`
- `Url` - link to 511 website detail page
- `VideoUrl` - direct HLS `.m3u8` stream URL or MJPEG URL (or `null`)
- `Disabled` / `Blocked` - boolean flags

**v2 (all other states)**
```
GET https://{state-host}/api/v2/get/cameras?key={KEY}&format=json
```
Response fields:
- `Id` - integer unique identifier
- `Source` / `SourceId` - data source info
- `Roadway` - road name
- `Direction` - direction string
- `Latitude` / `Longitude`
- `Location` - text location description
- `SortOrder` - display ordering hint
- `Views` - array of stream view objects:
  - `Url` - HLS `.m3u8` stream URL
  - `Status` - stream availability status
  - `Description` - view label

### Stream URL Patterns

**New York** (Skyline/NYSDOT CDN):
```
https://s{N}.nysdot.skyvdn.com:443/rtplive/{CAM_ID}/playlist.m3u8
```
Where `N` is a server number (51, 52, 53, 58, 7, 9) and `CAM_ID` looks like `R5_007`.

**Wisconsin** (WisDOT CCTV):
```
https://cctv1.dot.wi.gov:443/rtplive/{CAM_ID}/playlist.m3u8
```

**Other states**: Stream URLs are provided directly in the `Views[].Url` field from the API.

A small number of cameras expose MJPEG still-image streams:
```
http://live:{password}@{IP}:22250/mjpg/video.mjpg
```

---

## Installation

No external dependencies required — the client uses Python's built-in `urllib`. For better performance, install `requests`:

```bash
pip install requests
```

The file `dot_511_client.py` is self-contained with no other local dependencies.

---

## Quick Start

```python
from dot_511_client import DOT511Client

client = DOT511Client(api_keys={
    "ny": "YOUR_NY_KEY",
    "wi": "YOUR_WI_KEY",
    # add more states as needed
})

# --- List all cameras in New York ---
cameras = client.get_cameras("ny")
print(f"NY has {len(cameras)} cameras")

# --- Get only active cameras with streams ---
active = client.get_cameras("ny", active_only=True, with_stream_only=True)
for cam in active[:5]:
    print(cam.name, "->", cam.video_url)

# --- Get a specific camera ---
cam = client.get_camera_by_id("ny", "Skyline-10012")
print(cam)
# Camera(NY:'Skyline-10012' | 'NY 33 at Northampton Street' | active | stream)
print(cam.video_url)
# https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8

# --- Get just the stream URL ---
url = client.get_camera_stream_url("ny", "Skyline-10012")
print(url)
# https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8
```

---

## API Reference

### `DOT511Client(api_keys=None, rate_limit=True, timeout=30)`

Creates a new client instance.

| Parameter | Type | Description |
|-----------|------|-------------|
| `api_keys` | `dict` | Optional dict of state code -> API key |
| `rate_limit` | `bool` | Enforce 10 req/60s limit (default `True`) |
| `timeout` | `int` | HTTP timeout in seconds (default 30) |

---

### `get_cameras(state, api_key=None, *, roadway=None, direction=None, active_only=False, with_stream_only=False)`

Retrieve cameras for a state with optional filtering.

```python
# All cameras in Wisconsin
cameras = client.get_cameras("wi")

# Active I-94 cameras going northbound
cameras = client.get_cameras("wi", roadway="I-94", direction="North", active_only=True)

# All cameras with HLS streams in Alaska
cameras = client.get_cameras("ak", with_stream_only=True)
```

Returns a list of `Camera` objects.

---

### `get_camera_by_id(state, camera_id, api_key=None)`

Find a single camera by its ID.

```python
cam = client.get_camera_by_id("ny", "Skyline-10012")
if cam:
    print(cam.stream_urls)
```

---

### `get_camera_stream_url(state, camera_id, api_key=None, view_index=0)`

Get the primary HLS stream URL for a camera.

```python
url = client.get_camera_stream_url("ny", "Skyline-10012")
# Use with VLC, ffmpeg, mpegts.js, hls.js, etc.
```

---

### `get_camera_image_url(state, camera_id, api_key=None)`

Get a still image URL if the camera exposes MJPEG (not all cameras do).

```python
img = client.get_camera_image_url("ny", "some-mjpeg-camera")
# May return None if only HLS is available
```

---

### `get_all_stream_urls(state, api_key=None, active_only=True)`

Get all stream URLs as a flat list of dicts.

```python
streams = client.get_all_stream_urls("ny")
# [{"camera_id": ..., "name": ..., "roadway": ..., "stream_url": ...}, ...]

for s in streams[:10]:
    print(f'{s["name"]:50s} {s["stream_url"]}')
```

---

### `get_cameras_near(state, lat, lon, radius_miles=5.0, api_key=None)`

Find cameras near a geographic coordinate.

```python
# Cameras within 3 miles of downtown Milwaukee
cameras = client.get_cameras_near("wi", lat=43.0389, lon=-87.9065, radius_miles=3.0)
```

---

### `list_states()`

Return metadata for all supported states.

```python
for state in client.list_states():
    print(state["code"], state["name"], state["developer_page"])
```

---

### Static helpers

```python
# Construct stream URLs manually
wi_url = DOT511Client.construct_wi_hls_url("CAM001")
# https://cctv1.dot.wi.gov:443/rtplive/CAM001/playlist.m3u8

ny_url = DOT511Client.construct_ny_hls_url("R5_007", server_num=51)
# https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8

DOT511Client.is_hls_url("https://example.com/stream/playlist.m3u8")  # True
DOT511Client.is_mjpeg_url("http://cam/mjpg/video.mjpg")              # True
```

---

### `Camera` Object

| Attribute | Type | Description |
|-----------|------|-------------|
| `state` | `str` | State code ('ny', 'wi', etc.) |
| `camera_id` | `str` | Unique camera ID |
| `name` | `str` | Camera location description |
| `roadway` | `str` | Road/highway name |
| `direction` | `str` | Direction of travel |
| `latitude` | `float` | Decimal latitude |
| `longitude` | `float` | Decimal longitude |
| `detail_url` | `str` | Link to 511 detail page (v1 only) |
| `video_url` | `str` | Primary stream URL |
| `views` | `list[CameraView]` | All available stream views |
| `disabled` | `bool` | Camera is disabled (v1 only) |
| `blocked` | `bool` | Camera is blocked (v1 only) |
| `source` | `str` | Data source name (v2) |
| `source_id` | `str` | Source-specific ID (v2) |
| `raw` | `dict` | Original API JSON payload |

| Property | Description |
|----------|-------------|
| `is_active` | `True` if not disabled and not blocked |
| `has_stream` | `True` if at least one HLS/MJPEG URL exists |
| `stream_urls` | All stream URLs as a list |

---

## CLI Usage

```bash
# List supported states
python dot_511_client.py --list-states

# List cameras in New York
python dot_511_client.py --state ny --key YOUR_KEY

# Filter by roadway
python dot_511_client.py --state ny --key YOUR_KEY --roadway "I-90" --active-only

# Get specific camera info
python dot_511_client.py --state ny --key YOUR_KEY --camera-id Skyline-10012

# List all stream URLs
python dot_511_client.py --state wi --key YOUR_KEY --streams-only --limit 50
```

---

## Playing HLS Streams

HLS streams can be played with standard video tools:

**VLC:**
```bash
vlc "https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8"
```

**ffmpeg (capture to file):**
```bash
ffmpeg -i "https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8" \
       -c copy output.mp4
```

**Python with hls-client or streamlink:**
```bash
pip install streamlink
streamlink "https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8" best
```

**In a web page (hls.js):**
```html
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<video id="video" controls></video>
<script>
  var video = document.getElementById('video');
  var hls = new Hls();
  hls.loadSource('https://s51.nysdot.skyvdn.com:443/rtplive/R5_007/playlist.m3u8');
  hls.attachMedia(video);
</script>
```

---

## Example: Multi-State Camera Survey

```python
from dot_511_client import DOT511Client

API_KEYS = {
    "ny": "YOUR_NY_KEY",
    "wi": "YOUR_WI_KEY",
    "pa": "YOUR_PA_KEY",
    "ak": "YOUR_AK_KEY",
    "ut": "YOUR_UT_KEY",
}

client = DOT511Client(api_keys=API_KEYS)

for state_code in API_KEYS:
    try:
        cameras = client.get_cameras(state_code, with_stream_only=True, active_only=True)
        print(f"{state_code.upper()}: {len(cameras)} active streaming cameras")
    except Exception as e:
        print(f"{state_code.upper()}: Error - {e}")
```

---

## Getting API Keys

1. Visit the developer page for your target state (listed in the table above)
2. Click "Sign Up for an Account" or navigate to `/my511/register`
3. Register with your email address
4. Log in and navigate back to the developer page
5. Request / view your Developer API key

All registrations are free. Keys are typically issued immediately.

---

## Notes and Limitations

- **New York (v1)**: Uses the older `/api/getcameras` endpoint. The response structure differs from v2 but is fully handled by this client. NY has ~2,900 cameras total (~1,750 with active streams).
- **Virginia**: The 511VA website uses bot-protection middleware (JWT challenge) on unauthenticated requests. Authenticated API calls with a valid key work normally.
- **Minnesota / Iowa**: Use Castle Rock Associates' newer SPA frontend; developer API docs are not at the standard `/developers/doc` path but the underlying Iteris API at `/api/v2/get/cameras` works with a valid key.
- **All states**: Stream availability (`Disabled`, `Blocked`, view `Status`) changes in real time based on camera hardware status and maintenance windows.
- **Wisconsin HLS host**: `cctv1.dot.wi.gov:443` — use this directly if you have a camera's source ID.
