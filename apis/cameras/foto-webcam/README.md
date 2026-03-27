# Foto-Webcam.eu Reverse-Engineered API Client

Unofficial Python client for [Foto-Webcam.eu](https://www.foto-webcam.eu) — a network of 399 high-resolution webcams across the Alpine region and beyond, with 122M+ archived images.

## Coverage

| Country | Cameras | Notes |
|---------|---------|-------|
| Austria (at) | 201 | Main concentration |
| Germany (de) | 137 | Alps, Bavaria, N. Germany |
| Italy / South Tyrol (it) | 44 | Dolomites, Garda |
| Switzerland (ch) | 10 | |
| Liechtenstein (li) | 1 | |
| Greenland (gl) | 2 | Glacier research cameras |
| Peru (pe) | 1 | |
| United States (us) | 1 | |
| Unknown (??) | 2 | |
| **Total** | **399** | |

## Quick Start

```python
from foto_webcam_client import FotoWebcamClient

client = FotoWebcamClient()

# List all cameras
cameras = client.list_cameras()
print(len(cameras))  # 398

# Get a specific camera
cam = client.get_camera('zugspitze')
print(cam.name, cam.elevation, cam.country_name)
# Zugspitze Gipfel 2962 Germany

# Live image URL (1920px wide)
url = cam.current_image_url(1920)
# https://www.foto-webcam.eu/webcam/zugspitze/current/1920.jpg

# Download it
data = client.download_current_image('zugspitze', width=1920)
with open('zugspitze.jpg', 'wb') as f:
    f.write(data)
```

---

## API Reference

### `FotoWebcamClient(timeout, user_agent, rate_limit_delay)`

Constructor parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timeout` | `15` | HTTP request timeout in seconds |
| `user_agent` | library string | User-Agent header |
| `rate_limit_delay` | `0.5` | Minimum seconds between requests |

---

### Camera Listing

#### `list_cameras(country=None, offline=None, hidden=None, refresh=False)`

Returns all cameras, optionally filtered.

```python
# All cameras
all_cams = client.list_cameras()

# Austrian cameras only
at_cams = client.list_cameras(country='at')

# Only online cameras
online = client.list_cameras(offline=False)

# Force refresh of cache
fresh = client.list_cameras(refresh=True)
```

Country codes: `at`, `de`, `it`, `ch`, `li`, `gl`, `pe`, `si`, `hr`, `bb`, `us`

#### `get_camera(camera_id)`

Returns a `Camera` object.

```python
cam = client.get_camera('innsbruck')
```

#### `find_cameras_near(latitude, longitude, radius_km=50.0)`

Returns `[(distance_km, Camera), ...]` sorted by distance.

```python
nearby = client.find_cameras_near(47.42, 10.98, radius_km=30)
for dist, cam in nearby:
    print(f"{dist:.1f}km  {cam.id}  {cam.name}")
```

#### `list_cameras_by_country()`

Returns `{'at': [Camera, ...], 'de': [...], ...}`.

---

### Camera Object Fields

```python
cam.id               # 'zugspitze'
cam.name             # 'Zugspitze Gipfel'
cam.title            # 'Wetterwarte Zugspitze - Blick über den Gipfel nach Osten'
cam.keywords         # comma-separated keyword string
cam.country          # 'de'
cam.country_name     # 'Germany'
cam.latitude         # 47.42083
cam.longitude        # 10.98473
cam.elevation        # 2962  (metres)
cam.direction        # 80    (compass bearing camera faces)
cam.focal_len        # 18    (equivalent focal length mm)
cam.radius_km        # 15.0  (visible range)
cam.sector           # 63    (field of view degrees)
cam.capture_interval # 600   (seconds between shots)
cam.offline          # False
cam.partner          # False (sponsored camera)
cam.last_updated     # datetime object (UTC)
cam.imgurl           # 400px thumbnail URL
cam.link             # canonical page URL
```

---

### Image Information

#### `get_image_info(camera_id, timestamp='')`

Returns an `ImageInfo` object. Leave `timestamp` empty for the latest image.

```python
# Latest image
info = client.get_image_info('zugspitze')

# Specific archived image
info = client.get_image_info('zugspitze', '2024/07/15/1200')

print(info.timestamp)       # '2026/03/27/1800'
print(info.date_label)      # '27.03.26 18:00'
print(info.wx)              # '-15.8°C  88%  8km/h O'
print(info.img_exif)        # '(f/9.0  1/200s  iso100)'
print(info.huge_width)      # 6000
print(info.huge_height)     # 4000
print(info.available_suffixes())  # ['_sm', '_la', '_lm', '_hd', '_uh', '_hu']
print(info.best_url())      # highest-resolution URL

# Navigation
print(info.img_back)        # previous image timestamp
print(info.img_fwd)         # next image timestamp
print(info.day_back)        # same time yesterday
print(info.year_back)       # same time last year

# History slider (up to 200 adjacent timestamps)
print(len(info.history))    # 200
```

---

### Image URLs

#### Current / Live Images

```
https://www.foto-webcam.eu/webcam/{camera_id}/current/{width}.jpg
```

Valid widths: **150, 180, 240, 320, 400, 640, 720, 1200, 1920**

```python
url = FotoWebcamClient.current_image_url('zugspitze', 1920)
# or
url = cam.current_image_url(1920)
```

The server updates these files every ~600 seconds. The `Cache-Control: max-age=300` header means intermediate caches may serve a slightly older version. Add a cache-busting parameter when polling:

```python
import time
url = f"{cam.current_image_url(1200)}?t={int(time.time())}"
```

#### Archived Images

```
https://www.foto-webcam.eu/webcam/{camera_id}/{YYYY}/{MM}/{DD}/{HHMM}_{suffix}.jpg
```

| Suffix | Resolution | Approx Size | Notes |
|--------|------------|-------------|-------|
| `_la` | ~1200×675 px | ~57 KB | Standard default, always available |
| `_lm` | ~1200×675 px | ~57 KB | Medium HD, alt processing |
| `_hd` | 1920×1080 px | ~153 KB | Full HD |
| `_uh` | 3840×2160 px | ~576 KB | UHD/4K — camera-dependent |
| `_hu` | up to 6000×4000 px | ~1.8 MB | Huge/Max — camera-dependent |
| `_sm` | ~180×101 px | ~4 KB | Legacy thumbnail |

```python
# Static helper
url = FotoWebcamClient.archive_url('zugspitze', '2024/07/15/1200', suffix='_hu')

# Or via Camera object
url = cam.archive_image_url('2024/07/15/1200', suffix='_hd')

# Or download directly
data = client.download_archive_image('zugspitze', '2024/07/15/1200', '_hd')
```

**Important:** Not every suffix exists for every camera or date. Use `get_image_info()` to check `available_suffixes()` before downloading. Requesting a non-existent suffix returns HTTP 502.

---

### Archive Navigation

#### `list_archive_images(camera_id, mode, img='', page=0)`

| Mode | Returns |
|------|---------|
| `'img'` | Recent images (newest first) |
| `'day'` | Best-of-day representatives |
| `'year'` | One entry per month (newest first) |
| `'bestof'` | Curated best shots |

```python
# Recent images
recent = client.list_archive_images('zugspitze', mode='img')

# Images around a specific date
around = client.list_archive_images('zugspitze', mode='img', img='2024/07/15/1200')

# Paginated (page 0, 1, 2...)
page2 = client.list_archive_images('zugspitze', mode='img', page=2)

# Monthly index
months = client.list_monthly_index('zugspitze')

# Best shots
bestof = client.list_bestof('zugspitze')
```

#### `iterate_archive(camera_id, start_timestamp='', direction='back')`

Lazily walks the full archive without knowing timestamps in advance.

```python
# Walk backwards from latest image
count = 0
for ts in client.iterate_archive('zugspitze', direction='back'):
    print(ts)
    count += 1
    if count > 1000:
        break
```

---

### Overview Snapshots

#### `get_overview_snapshot(timestamp)`

Returns weather/EXIF info for all cameras at a given moment in time.

```python
snapshot = client.get_overview_snapshot('2024/07/15/1200')
print(snapshot['when'])          # '2024/07/15/1200'
print(len(snapshot['cams']))     # number of cameras with data that hour
for cam_snap in snapshot['cams'][:3]:
    print(cam_snap['id'], cam_snap['wx'])
```

---

### Resolution Inspection

#### `get_camera_resolutions(camera_id)`

```python
res = client.get_camera_resolutions('zugspitze')
# {
#   'camera_id': 'zugspitze',
#   'huge_width': 6000,
#   'huge_height': 4000,
#   'has_uhd': True,
#   'has_fhd': True,
#   'has_hd': True,
#   'available_suffixes': ['_sm', '_la', '_lm', '_hd', '_uh', '_hu']
# }
```

---

## Discovered API Endpoints

All endpoints are under `https://www.foto-webcam.eu/webcam/include/`.

### JSON Endpoints (primary API)

| Endpoint | Method | Parameters | Returns |
|----------|--------|------------|---------|
| `metadata.php` | GET | *(none)*, `center=lat,lon` | Full camera list with metadata |
| `list.php` | GET | `wc=<id>`, `img=<YYYY/MM/DD/HHMM_la.jpg>` | Image data, history, nav pointers, weather, EXIF |
| `thumb.php` | GET | `wc=<id>`, `mode=<day\|year\|bestof>`, `img=<ts_la.jpg>`, `page=<n>`, `count=<n>` | Paginated timestamp list |
| `daythumb.php` | GET | `wc=<id>`, `img=<ts_la.jpg>`, `count=<n>` | Same-hour timelapse across N days |
| `ovlist.php` | GET | `img=<YYYY/MM/DD/HHMM>` | Weather+EXIF for all cams at timestamp |
| `rrdfetch.php` | GET | `wc=<id>`, `ds=<sensors>`, `end=now`, `span=<secs>`, `rrdfile=wx.rrd`, `wcimg=<id>` | Time-series sensor data (temperature etc.) |
| `camstatus.php` | GET | `wc=<id>`, `serial=0` | Live camera operational status |

### HTML/Fragment Endpoints

| Endpoint | Parameters | Returns |
|----------|------------|---------|
| `exif.php` | `wc=<id>`, `img=<ts>` | EXIF data table (HTML) |
| `cal.php` | `wc=<id>` | Date picker calendar (HTML) |
| `wcinfos.php` | `wc=<id>` | Camera info page (HTML) |
| `map.php` | `wc=<id>` | Leaflet map iframe (HTML) |
| `share.php` | `where=web`, `wc=<id>` | Embed widget (HTML) |
| `manifest.php` | `wc=<id>` | PWA manifest (JSON) |

### `metadata.php` Response Structure

```json
{
  "cams": [
    {
      "id": "zugspitze",
      "name": "Zugspitze Gipfel",
      "title": "Wetterwarte Zugspitze - Blick über den Gipfel nach Osten",
      "keywords": "Zugspitze,Garmisch-Partenkirchen,...",
      "offline": false,
      "hidden": false,
      "imgurl": "https://www.foto-webcam.eu/webcam/zugspitze/current/400.jpg",
      "link": "https://www.foto-webcam.eu/webcam/zugspitze/",
      "localLink": "/webcam/zugspitze/",
      "modtime": 1774629005,
      "details": 20,
      "sortscore": "5.00080",
      "country": "de",
      "latitude": 47.42083,
      "longitude": 10.98473,
      "elevation": 2962,
      "direction": 80,
      "focalLen": 18,
      "radius_km": 15,
      "sector": 63,
      "partner": false,
      "captureInterval": 600
    }
  ]
}
```

### `list.php` Response Structure

```json
{
  "image": "2026/03/27/1800_la.jpg",
  "h": "abc1",
  "lrimg": "",
  "hugeimg": "2026/03/27/1800_hu.jpg",
  "hdimg":  "2026/03/27/1800_lm.jpg",
  "fhdimg": "2026/03/27/1800_hd.jpg",
  "uhdimg": "2026/03/27/1800_uh.jpg",
  "newest": true,
  "hugeWidth": "6000",
  "hugeHeight": "4000",
  "title": "Wetterwarte Zugspitze...",
  "date": "27.03.26 18:00",
  "wx": "-15.8°C  88%  8km/h O",
  "imgExif": "(f/9.0  1/200s  iso100)",
  "history": ["2026/03/26/0230", ..., "2026/03/27/1800"],
  "imgback": "2026/03/27/1750",
  "imgfwd":  "",
  "dayback": "2026/03/26/1800",
  "dayfwd":  "",
  "monback": "2026/02/27/1800",
  "monfwd":  "",
  "yearback": "2025/03/27/1800",
  "yearfwd":  "",
  "isbestof": false,
  "labels": []
}
```

### `thumb.php` Response Structure

```json
{
  "mode": "day",
  "images": [
    "2026/03/27/1800",
    "2026/03/26/1800",
    "2026/03/25/1800",
    "..."
  ]
}
```

### `rrdfetch.php` Response Structure

```json
{
  "dots": [
    [{"time": 1774545840000, "val": -15.125}, "..."],
    [{"time": 1774545840000, "val": -13.63}, "..."]
  ],
  "ds": ["temp1", "temp2"],
  "span": "1 Tag",
  "extent": [1774545619000, 1774632019000],
  "last_time": 1774632003000,
  "last_val": ["-14.6", "-13.3"],
  "images": ["2026/03/26/1820", "...", "2026/03/27/1810"],
  "factor": 0
}
```

**Known sensor names (`ds` parameter):** `temp1`, `temp2`, `temp3`

**Span values (seconds):**

| Label | Seconds |
|-------|---------|
| 3h | 10800 |
| 24h | 86400 |
| 3d | 259200 |
| 7d | 604800 |
| 30d | 2592000 |
| 90d | 7776000 |
| 1y | 31536000 |
| 3y | 94608000 |
| 9y | 283824000 |

### `camstatus.php` Response Structure

```json
[{
  "cam": "zugspitze",
  "last": "2026-03-27 18:40:33",
  "status": "ready",
  "sleeping": "0",
  "uploadhost": "daniel",
  "lastimg": "2026-03-27 18:40:33",
  "imagesize": "3093422",
  "proctime": "51775",
  "uploadrate": "553081",
  "heater": "1",
  "serial": "17746332338074",
  "lastimgstamp": "1774633233",
  "laststamp": 1774633348
}]
```

### `ovlist.php` Response Structure

```json
{
  "when": "2026/03/27/1730",
  "cams": [
    {"id": "zugspitze", "wx": "-15.4°C    88%    8km/h O", "exif": "(f/10  1/250s  iso100)", "textColor": "black"},
    {"id": "bardolino",  "wx": "23°C",                    "exif": "(f/10  1/200s  iso100)", "textColor": "black"}
  ]
}
```

---

## New Methods (v2)

### Weather Data

```python
# 24-hour temperature time series
wx = client.get_weather_data('zugspitze', sensors='temp1:temp2', span=86400)
print(wx.sensors)            # ['temp1', 'temp2']
print(wx.span_label)         # '1 Tag'
print(wx.latest_temperature(0))  # -15.4  (degrees C)

# Data points
for point in wx.dots[0][:5]:
    ts = datetime.fromtimestamp(point['time'] / 1000)
    print(f"{ts}  {point['val']:.2f}°C")

# Long-term (1 year)
wx_year = client.get_weather_data('zugspitze', span=31536000)
```

### Camera Operational Status

```python
st = client.get_camera_status('zugspitze')
print(st.status)           # 'ready'
print(st.last_img)         # '2026-03-27 18:40:33'
print(st.image_size)       # 3093422 bytes (raw capture before compression)
print(st.proc_time)        # 51775 ms
print(st.upload_rate)      # 553081 bytes/s
print(st.heater)           # 1 (housing heater active)
print(st.is_online)        # True
```

### GeoJSON Export

```python
# All German cameras as GeoJSON
geojson = client.export_geojson(country='de')
print(len(geojson['features']))  # 137

with open('cameras_de.geojson', 'w') as f:
    json.dump(geojson, f, ensure_ascii=False, indent=2)

# All active cameras
geojson_all = client.export_geojson(include_offline=False)
```

---

## Common Usage Patterns

### Bulk Download of a Day's Images

```python
client = FotoWebcamClient(rate_limit_delay=1.0)

cam_id = 'zugspitze'
date = '2024/07/15'

# Get all images from the 15th of July 2024
images = client.list_archive_images(cam_id, mode='img', img=f'{date}/1200')
day_images = [ts for ts in images if ts.startswith(date)]

for ts in day_images:
    data = client.download_archive_image(cam_id, ts, suffix='_hd')
    filename = ts.replace('/', '_') + '_hd.jpg'
    with open(filename, 'wb') as f:
        f.write(data)
    print(f"Saved {filename} ({len(data)} bytes)")
```

### Monitor a Camera for New Images

```python
import time

client = FotoWebcamClient()
cam_id = 'innsbruck'
last_ts = None

while True:
    info = client.get_image_info(cam_id)
    if info.timestamp != last_ts:
        print(f"New image: {info.timestamp}  wx={info.wx}")
        last_ts = info.timestamp
        data = client.download_current_image(cam_id, width=1920)
        with open(f'{cam_id}_{last_ts.replace("/","_")}_latest.jpg', 'wb') as f:
            f.write(data)
    time.sleep(60)
```

### Find All High-Resolution (UHD/Huge) Cameras

```python
client = FotoWebcamClient()
for cam in client.list_cameras(offline=False):
    res = client.get_camera_resolutions(cam.id)
    if res['has_uhd'] or res['huge_width'] >= 3840:
        print(f"{cam.id:30s} {res['huge_width']}x{res['huge_height']}")
```

### Export Camera Index to JSON

```python
import json
client = FotoWebcamClient()
cams = client.list_cameras()
export = [
    {
        'id': c.id, 'name': c.name, 'country': c.country,
        'lat': c.latitude, 'lon': c.longitude, 'elevation': c.elevation,
        'interval': c.capture_interval, 'offline': c.offline,
    }
    for c in cams
]
with open('cameras.json', 'w') as f:
    json.dump(export, f, ensure_ascii=False, indent=2)
```

---

## Notes & Limitations

- **No authentication required** for reading images and metadata.
- **Rate limiting:** The site does not publish rate limits. Be courteous — use `rate_limit_delay >= 0.5` for batch operations.
- **Archive depth:** Varies by camera. Some cameras have data from 2013; others from 2016+. The `list_monthly_index()` method reveals the earliest month available.
- **`_uh` (UHD) availability:** Only present on cameras equipped with 4K sensors. Check `info.uhd_img` before requesting.
- **`_hu` (Huge) availability:** Most modern cameras support this. Resolution varies: 4272×2848, 5184×3456, or 6000×4000 depending on sensor.
- **HTTP 502** is returned when a specific resolution was not captured (e.g. older archived images may lack `_uh`). This is not a server error.
- **`current/` shortcuts** only expose widths 150–1920. To get UHD or Huge of the latest image, use `get_image_info()` and follow the `hugeimg` path.
- The site renders mostly client-side via jQuery + custom `webcam` JS object. The PHP endpoints return clean JSON and are stable.

---

## File Structure

```
foto_webcam_client.py   -- Single-file Python client (no dependencies beyond stdlib)
foto_webcam_README.md   -- This file
```

Run the built-in demo:

```bash
python3 foto_webcam_client.py
```
