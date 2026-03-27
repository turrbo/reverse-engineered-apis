# AlertWildfire / AlertCalifornia Camera API - Reverse Engineering Report

## Overview

Two camera networks cover the Western US for wildfire detection:

| System | Operator | Cameras | States |
|---|---|---|---|
| **ALERTWildfire** | University of Nevada, Reno | 128 | NV, CA, WA, ID, AZ |
| **AlertCalifornia** | UC San Diego | 2072+ | CA and surrounding |

Both systems use Axis PTZ cameras and serve live JPEG images. No authentication is needed for public image data.

---

## Reverse Engineering Methodology

### Phase 1: Camera List Endpoint Discovery

The `all-cameras.json` S3 URL was extracted from the page's embedded config in `window.__NUXT__`:

```javascript
window.__NUXT__ = {
  config: {
    imageRootUrl: "//s3-us-west-2.amazonaws.com/awf-data-public-prod",
    cameraServiceUrl: "//s3-us-west-2.amazonaws.com/awf-data-public-prod/all-cameras.json",
    timelapseBaseUrl: "//tl.alertwildfire.org",
    camerasManagerApiBaseUrl: "//api.alertwildfire.org",
    proxyLinkTemplates: {"Link 1": "//$[id].prx.alertwildfire.org"},
    // ...
  }
}
```

The S3 camera list returns 403 without a Referer header. Adding `Referer: https://www.alertwildfire.org/` unlocks it.

### Phase 2: Image URL Pattern Discovery

The site uses Nuxt.js with webpack chunking. The image URL patterns were found by downloading lazy-loaded JS chunks and searching for `imageRootUrl`:

From `69c7631.js`, `de0d8c0.js`, `fb0343b.js` (camera tile components):
```javascript
// Full image
`${this.$config.imageRootUrl}/${this.firecam.properties.id}/latest_full.jpg?x-request-time=${cacheBusterTimestamp}`

// Thumbnail
`${this.$config.imageRootUrl}/${this.firecam.properties.id}/latest_thumb.jpg?x-request-time=${cacheBusterTimestamp}`
```

Key insight: URLs use the camera's **UUID** (from `properties.id`), not the hostname or slug.

### Phase 3: Timelapse URL Discovery

From `5b9d54e.js` / `fa00f02.js` (camera viewer component):
```javascript
const url = `${this.$config.timelapseBaseUrl}/timelapse?source=${camera_id}&preset=${duration}&nocache=${Date.now()}`;
playMjpeg(url, ...);
```

Duration options: `"15m"`, `"1h"`, `"3h"`, `"6h"`, `"12h"`

The timelapse server returns `multipart/x-mixed-replace; boundary=frame` (MJPEG stream).

### Phase 4: AlertCalifornia Discovery

AlertCalifornia uses a completely different frontend (vanilla JS, Leaflet maps). The JS source is at `https://cameras.alertcalifornia.org/alertcalifornia.js`. Key discoveries:

```javascript
const DEFAULT_BASE_URL = "https://cameras.alertcalifornia.org";
let DATA_URL = `${BASE_URL}/public-camera-data`;

// Image URLs
function get_camera_url(type, camera) {
  if(type === "full") type = "frame";  // "full" → "frame" mapping!
  return `${DATA_URL}/${camera}/latest-${type}.jpg?rqts=${Math.floor(Date.now()/1000)}`;
}

// Timelapse
this.url_prefix = `${DATA_URL}/${camera_id}/${pool}`;
// spec: `${url_prefix}/${spec}` (e.g. "1-hour.json")
// frame: `${url_prefix}/${jpg_name}` (e.g. "1774630882.000000000.jpg")
```

---

## API Reference

### ALERTWildfire (alertwildfire.org)

#### Camera List

```
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/all-cameras.json
Headers:
  Referer: https://www.alertwildfire.org/
```

Returns GeoJSON FeatureCollection. Camera fields:
- `id` - UUID (use for image/timelapse URLs)
- `camera_slug` - human-readable ID like `nv-castlepeak-1`
- `hostname` - Axis device hostname like `axis-castlepeak`
- `name` - display name
- `state`, `county` - location
- `az_current`, `tilt_current`, `zoom_current` - current PTZ position
- `is_patrol_mode`, `is_currently_patrolling` - patrol status
- `last_update_at` - ISO 8601 timestamp
- `fov`, `fov_center`, `fov_lft`, `fov_rt` - field of view coordinates
- `elevation`, `aboveGroundHeight` - elevation in meters
- `sponsor` - sponsoring organization (e.g. NVEnergy, CalFire)
- `attribution` - "ALERTWildfire"

#### Current Images

```
# Full resolution (~200-400 KB)
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/{camera_uuid}/latest_full.jpg
    ?x-request-time={unix_ms}

# Thumbnail (~15-25 KB)
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/{camera_uuid}/latest_thumb.jpg
    ?x-request-time={unix_ms}
```

No auth required. No special headers needed for image fetches.

#### Timelapse (Streaming MJPEG)

```
GET https://tl.alertwildfire.org/timelapse
    ?source={camera_uuid}
    &preset={15m|1h|3h|6h|12h}
    &nocache={unix_ms}

Response: multipart/x-mixed-replace; boundary=frame
Access-Control-Allow-Origin: *
```

Each frame in the stream:
```
--frame\r\n
Content-Type: image/jpeg\r\n
Content-Length: {N}\r\n
\r\n
[JPEG bytes]
```

Notes:
- Returns 204 (No Content) if camera has no data for the requested period
- ~57 frames per 5 seconds for a 15-minute preset (all frames sent immediately then stream ends)
- Approximate frame counts: 15m=~60, 1h=~120, 3h=~220, 6h=~320, 12h=~470

#### Fire & Weather Metadata (all public S3)

```
# IRWIN active fire starts
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/irwin-starts.geojson

# IRWIN fire perimeters
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/irwin-perimeters.geojson

# NOAA Red Flag Warning areas
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/noaa-red-flag-areas.geojson

# Lightning data
GET https://s3-us-west-2.amazonaws.com/awf-data-public-prod/v3-metadata/lightning-data.geojson
```

All require `Referer: https://www.alertwildfire.org/` header.
Update frequency: ~every 5 minutes.

#### Auth-Gated Endpoints

These require a Bearer JWT token (obtain via `https://chief.alertwildfire.org/login/`):

```
# Camera control proxy (forwards to Axis camera)
GET https://{camera_uuid}.prx.alertwildfire.org/
    → Axis camera web interface

# User profile
GET https://api.alertwildfire.org/user/me
Authorization: Bearer {token}
```

---

### AlertCalifornia (cameras.alertcalifornia.org)

#### Camera List

```
GET https://cameras.alertcalifornia.org/public-camera-data/all_cameras-v3.json
    ?rqts={unix_seconds}
```

Returns GeoJSON FeatureCollection (~2.5 MB). Camera fields:
- `id` - hostname-style ID like `Axis-BoxSprings2`
- `name` - display name
- `last_frame_ts` - Unix timestamp of most recent frame
- `az_current`, `tilt_current`, `zoom_current` - current PTZ
- `is_patrol_mode`, `is_currently_patrolling` - patrol status
- `state`, `county`, `sponsor`, `region`, `isp` - metadata
- `fov`, `fov_lft`, `fov_rt`, `fov_center` - field of view

Note: ~827 cameras have null geometry (hidden/private cameras).

#### Current Images

```
# Thumbnail (~7 KB)
GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/latest-thumb.jpg
    ?rqts={unix_seconds}

# Full resolution (~300-400 KB)
GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/latest-frame.jpg
    ?rqts={unix_seconds}
```

Note: The URL uses `latest-frame.jpg` for full resolution (NOT `latest-full.jpg`).

#### Timelapse (JSON spec + JPEG frames)

AlertCalifornia's timelapse works differently from AWF - it uses a two-step approach:

**Step 1: Get the frame list (spec)**
```
GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/{pool}/{spec_file}
```

| Duration | Pool | Spec file |
|---|---|---|
| 5 mins | `10sec` | `5-min.json` |
| 15 mins | `10sec` | `15-min.json` |
| 30 mins | `10sec` | `30-min.json` |
| 1 hour | `1min` | `1-hour.json` |
| 3 hours | `1min` | `3-hour.json` |
| 6 hours | `1min` | `6-hour.json` |
| 12 hours | `1min` | `12-hour.json` |

Response:
```json
{
  "last_updated": 1774631178.187657,
  "frames": [
    "1774630882.000000000.jpg",
    "1774630927.000000000.jpg",
    ...
  ]
}
```

**Step 2: Download individual frames**
```
GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/{pool}/{jpg_name}
```

Frame filenames encode Unix timestamps with nanosecond precision (though effectively only second-level precision).

#### Panoramic Grid (360°)

Some cameras support a panoramic grid view (multiple overlapping Axis camera images):

```
# Get spec
GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/panogrid/panogrid.json
    ?rqts={unix_seconds}

Response:
{
  "last_updated": 1774631342.0,
  "camera": "Axis-BoxSprings2",
  "timestamps": [1769912495.0, 1773419263.0, ...]
}

# Get individual grid tile (idx = 0-based)
GET https://cameras.alertcalifornia.org/public-camera-data/{camera_id}/panogrid/latest-pg-{idx}.jpg
    ?ts={timestamp}
```

---

## Usage Guide

### Installation

```bash
pip install requests
```

### Basic Usage

```python
from alertwildfire_client import AlertWildfireClient, AlertCaliforniaClient

# --- ALERTWildfire ---
awf = AlertWildfireClient()

# Get all cameras
cameras = awf.get_cameras()
print(f"Found {len(cameras['features'])} cameras")

# Get camera by slug
cam = awf.get_camera_by_slug("nv-castlepeak-1", cameras)
cam_id = cam["properties"]["id"]

# Download current image
img_bytes = awf.get_current_image(cam_id, full_size=True)
with open("castlepeak_latest.jpg", "wb") as f:
    f.write(img_bytes)

# Stream timelapse (first 10 frames of 1-hour timelapse)
for i, frame in enumerate(awf.get_timelapse_frames(cam_id, "1h", max_frames=10)):
    with open(f"frame_{i:04d}.jpg", "wb") as f:
        f.write(frame)

# --- AlertCalifornia ---
ac = AlertCaliforniaClient()

# Get camera list
cameras = ac.get_cameras()
print(f"Found {len(cameras['features'])} cameras")

# Get current image
thumbnail = ac.get_thumbnail("Axis-BoxSprings2")
full_img = ac.get_full_image("Axis-BoxSprings2")

# Get timelapse spec and download frames
spec = ac.get_timelapse_spec("Axis-BoxSprings2", "1 hour")
for ts, frame_bytes in ac.get_timelapse_frames("Axis-BoxSprings2", "1 hour", max_frames=5):
    from datetime import datetime
    dt = datetime.fromtimestamp(ts)
    print(f"Frame at {dt.strftime('%H:%M:%S')}: {len(frame_bytes)} bytes")
```

### Monitor a Camera for Smoke

```python
from alertwildfire_client import AlertWildfireClient
import time

awf = AlertWildfireClient()
cameras = awf.get_cameras()

# Find NV cameras updated in last 10 minutes
import time as t
now = time.time()
recent = []
for feat in cameras["features"]:
    p = feat["properties"]
    from datetime import datetime, timezone
    try:
        last = datetime.fromisoformat(p["last_update_at"].replace("Z", "+00:00"))
        age = now - last.timestamp()
        if age < 600:  # 10 minutes
            recent.append((age, feat))
    except:
        pass

recent.sort(key=lambda x: x[0])
print(f"Active cameras (updated <10 min): {len(recent)}")

# Get current image for most recently updated camera
if recent:
    age, cam = recent[0]
    p = cam["properties"]
    print(f"Most recent: {p['name']} (updated {age:.0f}s ago)")
    img = awf.get_current_image(p["id"], full_size=True)
    with open(f"latest_{p['camera_slug']}.jpg", "wb") as f:
        f.write(img)
```

### Download Latest AWF Timelapse as JPEG Sequence

```python
from alertwildfire_client import AlertWildfireClient

awf = AlertWildfireClient()

cam_slug = "nv-castlepeak-1"
cameras = awf.get_cameras()
cam = awf.get_camera_by_slug(cam_slug, cameras)
cam_id = cam["properties"]["id"]

print(f"Downloading 1h timelapse for {cam['properties']['name']}...")
frames = awf.download_timelapse(cam_id, preset="1h", output_path="./timelapse_frames/")
print(f"Downloaded {len(frames)} frames")
```

### Monitor AlertCalifornia for New Smoke Events

```python
from alertwildfire_client import AlertCaliforniaClient
import time

ac = AlertCaliforniaClient()
cameras = ac.get_cameras()

# Get active cameras
active = ac.get_active_cameras(cameras, max_age_seconds=120)
print(f"Cameras with images in last 2 minutes: {len(active)}")

# Sort by recency
active.sort(key=lambda f: f["properties"].get("last_frame_ts", 0), reverse=True)

# Print top 10 most recently updated
for cam in active[:10]:
    p = cam["properties"]
    age = time.time() - p.get("last_frame_ts", 0)
    print(f"  {p['id']}: {p.get('name', '?')} - {age:.0f}s ago")
```

---

## Authentication Notes

Public data (camera lists, images, timelapse) requires NO authentication.

For PTZ camera control and user settings:
- Login at: `https://chief.alertwildfire.org/login/`
- After login, an `accessToken` JWT is stored in localStorage/cookies
- Use as `Authorization: Bearer {token}` for API calls
- Token expires after 86400 seconds (24 hours)
- Authenticated endpoints: `https://api.alertwildfire.org/user/me`, camera proxy URLs

---

## Important Notes

1. **Referer header**: The AWF camera list requires `Referer: https://www.alertwildfire.org/` - without it, you get HTTP 403.

2. **Camera IDs**: AWF uses UUIDs (`1ac1033c-c9d8-4eed-a23b-bb6b1ff80303`). AlertCalifornia uses hostname-style IDs (`Axis-BoxSprings2`). Do not confuse them.

3. **Stale cameras**: AWF timelapse returns 204 for cameras with no recent data. AlertCalifornia image URLs return 404 or serve an "unavailable" placeholder image.

4. **Rate limiting**: No explicit rate limits observed, but be respectful. The metadata GeoJSON files are large (7.5 MB for fire perimeters) - cache them locally and refresh every 5+ minutes.

5. **Cache busting**: The `?x-request-time={ms}` and `?rqts={seconds}` parameters are cache busters. You can omit them but may get cached responses.

6. **CORS**: Both systems have CORS headers (`Access-Control-Allow-Origin: *`) enabling browser-based access.

7. **AlertCalifornia "full" → "frame" mapping**: The URL for the full-resolution current image is `latest-frame.jpg` NOT `latest-full.jpg`.

---

## File Structure

```
alertwildfire_client.py  - Python client with full docstrings and demo
alertwildfire_README.md  - This file
```

## Dependencies

```
requests>=2.25.0
```
