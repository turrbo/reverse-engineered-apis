# Opentopia Camera Directory Client

Reverse-engineered Python client for [Opentopia](https://www.opentopia.com/), a public webcam directory with 1500+ live cameras worldwide.

---

## Overview

Opentopia is a public webcam indexer that discovers and archives publicly accessible security cameras, traffic cams, and other IP cameras around the world. As of March 2026 the database contains **~1508 cameras** across 50+ countries.

This client was built through reverse engineering of:
- HTML page structure and form parameters
- JavaScript source files (`application.js`, `livehidden.js`)
- Network API calls embedded in the map and listing pages
- Image URL patterns on `images.opentopia.com`

---

## Discovered API Endpoints

### 1. Camera Listing — `GET /hiddencam.php`

Main paginated listing of all cameras.

**URL:** `https://www.opentopia.com/hiddencam.php`

**Parameters:**

| Parameter  | Values                                    | Default     | Description             |
|------------|-------------------------------------------|-------------|-------------------------|
| `showmode` | `standard`, `animated`                   | `standard`  | Display mode            |
| `country`  | Country name, `*` for all                | `*`         | Filter by country       |
| `seewhat`  | `newest`, `random`, `oftenviewed`, `highlyrated` | `highlyrated` | Sort order      |
| `p`        | Integer (1-based)                         | `1`         | Page number             |

**Response:** HTML page. ~24 cameras per page. Max ~100 pages for all cameras combined.

**Country filter examples:**
- `country=Japan` — cameras in Japan
- `country=Germany` — cameras in Germany
- `country=United States` — all US cameras
- `country=United States|California` — California only
- `country=United States|New York` — New York state only
- `country=*` — all countries

**Example URLs:**
```
https://www.opentopia.com/hiddencam.php?showmode=standard&country=Japan&seewhat=newest&p=1
https://www.opentopia.com/hiddencam.php?showmode=standard&country=United+States%7CCalifornia&seewhat=highlyrated&p=1
https://www.opentopia.com/hiddencam.php?showmode=standard&country=%2A&seewhat=random&p=1
```

**Parsed HTML structure:**
```html
<ul class="camgrid camgrid3">
  <li>
    <a href="/webcam/18334">
      <img src="https://images.opentopia.com/cams/18334/medium.jpg" alt="Webcam in Paris,France" />
    </a>
    <div class="infos">
      <div class="viewcamsname">Eiffel Tower View</div>
      <div class="location"><span>France</span> | <span>Île-de-France</span> | <span>Paris</span></div>
    </div>
  </li>
  ...
</ul>
```

---

### 2. Country / Tag Metadata — `GET /hiddencam.php?xmode=get_country_tags`

**URL:** `https://www.opentopia.com/hiddencam.php?xmode=get_country_tags`

**Response:** JSON

**JSON structure:**
```json
{
  "countries": {
    "code": {
      "JP": {
        "name": "Japan",
        "count": 273,
        "tags": [],
        "states": {
          "JP.13": {"name": "Tokyo", "count": 45, "tags": []}
        }
      },
      "US": {
        "name": "United States",
        "count": 283,
        "tags": [],
        "states": {
          "US.CA": {"name": "California", "count": 35, "tags": []},
          "US.NY": {"name": "New York", "count": 14, "tags": []}
        }
      }
    },
    "name": { "Japan": "JP", "United States": "US", ... }
  },
  "tags": {
    "1": "airport",
    "2": "animals",
    "3": "beach",
    "4": "ski",
    "5": "square",
    "6": "university",
    "7": "hotel",
    "8": "construction",
    "9": "college",
    "10": "traffic",
    "11": "port",
    "12": "river",
    "13": "bridge",
    "14": "street",
    "15": "aquarium",
    "16": "test",
    "17": "animals aquarium",
    "18": "studio"
  }
}
```

**Top countries by camera count** (as of March 2026):

| Country        | Count |
|----------------|-------|
| United States  | 283   |
| Japan          | 264+  |
| Germany        | 137   |
| Italy          | 98    |
| Austria        | 82+   |
| Taiwan         | 74+   |
| France         | 49+   |
| Norway         | 48    |
| South Korea    | 40+   |
| Switzerland    | 36+   |
| Czech Republic | 36    |

---

### 3. Map / Geographic Search — `GET /map.php?xmode=getcams`

Returns the ~40 cameras nearest to a given latitude/longitude.

**URL:** `https://www.opentopia.com/map.php`

**Parameters:**

| Parameter   | Type    | Description                           |
|-------------|---------|---------------------------------------|
| `xmode`     | string  | Must be `getcams`                     |
| `latitude`  | float   | Center latitude (decimal degrees)     |
| `longitude` | float   | Center longitude (decimal degrees)    |
| `zoom`      | int     | Map zoom level (1-20, passed to server but effect is minor) |

**Response:** JSON array

```json
[
  {
    "id": "12343",
    "title": "Staten Island Driveway Cam",
    "latitude": "40.545300",
    "longitude": "-74.178596"
  },
  ...
]
```

**Notes:**
- Returns exactly 40 cameras regardless of zoom level
- Camera selection is proximity-based (nearest 40 to the given point)
- Camera data includes only id, title, latitude, longitude (not full metadata)

**Example URLs:**
```
https://www.opentopia.com/map.php?xmode=getcams&latitude=35.68&longitude=139.69&zoom=8
https://www.opentopia.com/map.php?xmode=getcams&latitude=48.85&longitude=2.35&zoom=8
https://www.opentopia.com/map.php?xmode=getcams&latitude=40.71&longitude=-74.00&zoom=8
```

---

### 4. Camera Detail Page — `GET /webcam/{id}`

Full metadata for a single camera.

**URL:** `https://www.opentopia.com/webcam/{camera_id}`

**Example:** `https://www.opentopia.com/webcam/12343`

**View modes** (via `?viewmode=` parameter):

| Mode                | Description                                 |
|---------------------|---------------------------------------------|
| `savedstill`        | Last saved snapshot (default)               |
| `livestill`         | Current live still image                    |
| `refreshingstill`   | Auto-refreshing still                       |
| `animated`          | Flipbook of 6 recent frames                 |
| `livevideo`         | Live MJPEG/video stream                     |

**Metadata extracted from HTML/meta tags:**

```html
<!-- OpenGraph meta tags -->
<meta property="og:title" content="Staten Island Driveway Cam - a webcam in Staten Island, United States" />
<meta property="og:latitude" content="40.545300" />
<meta property="og:longitude" content="-74.178596" />
<meta property="og:country-name" content="United States" />
<meta property="og:region" content="New York" />
<meta property="og:locality" content="Staten Island" />

<!-- JavaScript variables -->
var camera_id = 12343;
var cam_title = "Staten Island Driveway Cam";
var cam_country_name = "United States";
```

**Camera info block:**
```html
<div id="caminfo" class="caminfo">
  <div><label>Facility:</label> <label>Staten Island Driveway Cam</label></div>
  <div><label>City:</label> <label class="locality">Staten Island</label></div>
  <div><label>State/Region:</label> <label class="region">New York</label></div>
  <div><label>Country:</label> <label class="country-name">United States</label></div>
  <div><label>Coordinates:</label> <label>40.545300 / -74.178596</label></div>
  <div><label>Brand:</label> <label>Axis</label></div>
  <div><label>Rating:</label> 5.00 from 3 votes</div>
</div>
```

**Live video URL** (from `?viewmode=livevideo`):
```html
<div class="big">
  <div style="z-index:100;width:715px">
    <img src="http://statenisland.dnsalias.net/mjpg/video.mjpg" />
  </div>
</div>
```

---

### 5. Search — `GET /search.php`

Keyword search across camera titles, descriptions, and locations.

**URL:** `https://www.opentopia.com/search.php`

**Parameters:**

| Parameter | Description              |
|-----------|--------------------------|
| `q`       | Search query             |
| `r`       | Set to `1` to get results |
| `p`       | Page number (1-based)    |

**Example URLs:**
```
https://www.opentopia.com/search.php?q=tokyo&r=1&p=1
https://www.opentopia.com/search.php?q=beach&r=1
https://www.opentopia.com/search.php?q=airport&r=1&p=2
```

**Response:** HTML with same camgrid structure as hiddencam.php

---

### 6. Community Feed — `GET /community.php`

Recent comments and community activity.

**URL:** `https://www.opentopia.com/community.php`

**Parameters:**

| Parameter | Description                    |
|-----------|--------------------------------|
| `q`       | Search comments by keyword     |
| `p`       | Page number                    |

---

### 7. Real-Time WebSocket — `ws://ws.opentopia.com/websocket`

WebSocket endpoint using [WebSocketRails](https://github.com/websocket-rails/websocket-rails) protocol that broadcasts live camera view events.

**Event channel:** `views`
**Event name:** `channel`

**Payload example:**
```json
{
  "info": {
    "camera_id": "12343",
    "cam_key": "12343|Staten Island Driveway Cam|United States"
  }
}
```

**Connection (JavaScript):**
```javascript
dispatcher = new WebSocketRails('ws.opentopia.com/websocket');
dispatcher.on_open = function(data) {
    vchannel = dispatcher.subscribe('views');
    vchannel.bind('channel', function(response) {
        var camera_id = parseInt(response.info['camera_id']);
        var cam_key = response.info['cam_key'];
        // cam_key format: "{id}|{title}|{country}"
    });
}
```

---

## Image URL Patterns

All camera images are served from `https://images.opentopia.com/cams/{camera_id}/`

### Standard sizes

| URL Pattern                                        | Approx. Size  | Description                           |
|----------------------------------------------------|---------------|---------------------------------------|
| `/cams/{id}/tiny.jpg`                              | ~62×48 px     | Tiny thumbnail                        |
| `/cams/{id}/small.jpg`                             | ~230×172 px   | Small (similar dimensions to medium)  |
| `/cams/{id}/medium.jpg`                            | ~230×172 px   | Medium (standard listing thumbnail)   |
| `/cams/{id}/big.jpg`                               | ~715px wide   | Full-size current snapshot            |

### Historical snapshots

| URL Pattern              | Description                          |
|--------------------------|--------------------------------------|
| `/cams/{id}/m-1.jpg`     | Most recent snapshot (~3–6 hours ago) |
| `/cams/{id}/m-2.jpg`     | ~6–9 hours ago                       |
| `/cams/{id}/m-3.jpg`     | ~9–12 hours ago                      |
| `/cams/{id}/m-4.jpg`     | ~12–15 hours ago                     |
| `/cams/{id}/m-5.jpg`     | ~15–18 hours ago                     |
| `/cams/{id}/m-6.jpg`     | ~18–21 hours ago (oldest)            |

### Animation frames

Numbered frames used in the flipbook animation view:
```
/cams/{id}/81720560.jpg
/cams/{id}/81718556.jpg
/cams/{id}/81716543.jpg
...
```
These are sequential internal IDs (not Unix timestamps). They're approximately 2000 apart, which likely represents an internal sequence counter. The frames are exposed in the `viewmode=animated` page via a `<div id="flipbook">`.

---

## Installation

```bash
pip install requests beautifulsoup4
```

---

## Quick Start

```python
from opentopia_client import OpentopiaClient

client = OpentopiaClient()

# List newest cameras worldwide
cameras = client.list_cameras(sort='newest')
for cam in cameras:
    print(cam.id, cam.country, cam.title)

# Get full metadata for a camera
cam = client.get_camera(12343)
print(cam.title)          # "Staten Island Driveway Cam"
print(cam.latitude)       # 40.5453
print(cam.longitude)      # -74.1786
print(cam.country)        # "United States"
print(cam.brand)          # "Axis"
print(cam.url_big)        # "https://images.opentopia.com/cams/12343/big.jpg"
print(cam.live_url)       # "http://statenisland.dnsalias.net/mjpg/video.mjpg"

# Get snapshot URLs
thumb = client.get_thumbnail_url(12343)    # tiny.jpg
image = client.get_snapshot_url(12343)     # big.jpg
history = client.get_historical_snapshots(12343)  # [m-1.jpg ... m-6.jpg]

# Search by keyword
results = client.search('tokyo beach')
for cam in results:
    print(cam.id, cam.title)

# Browse by country
japan_cams = list(client.iter_all_cameras(country='Japan'))
print(f"Japan has {len(japan_cams)} cameras")

# US state filter
california_cams = client.list_cameras(country='United States|California')

# Geographic search (nearest 40 cameras)
nearby = client.cameras_near(48.85, 2.35)   # Paris
for cam in nearby:
    print(cam.id, cam.title, cam.latitude, cam.longitude)

# Random camera
random_cam = client.get_random_camera()
print(random_cam.id, random_cam.country)

# All country statistics
counts = client.get_camera_count_by_country()
for country, n in sorted(counts.items(), key=lambda x: -x[1])[:10]:
    print(f"{n:4d}  {country}")

# Total camera count
total = client.get_total_camera_count()
print(f"Total: {total} cameras")
```

---

## API Reference

### Class `OpentopiaClient`

```python
OpentopiaClient(
    session=None,         # Optional requests.Session
    request_delay=0.5,    # Seconds between requests
    timeout=15            # HTTP timeout in seconds
)
```

#### Listing cameras

| Method | Description |
|--------|-------------|
| `list_cameras(country, sort, mode, page)` | One page of cameras from main listing |
| `iter_all_cameras(country, sort, max_pages)` | Generator that pages through all cameras |
| `get_top_cameras(count, country)` | Highest-rated cameras |
| `get_newest_cameras(count, country)` | Most recently added cameras |
| `get_most_viewed_cameras(count)` | Most viewed cameras |
| `cameras_in_country(country)` | ALL cameras in a country |
| `get_random_cameras(country, count)` | Random selection of cameras |
| `get_random_camera(country)` | Single random camera |

#### Camera detail

| Method | Description |
|--------|-------------|
| `get_camera(camera_id)` | Full metadata for a camera |
| `get_camera_with_live_url(camera_id)` | Metadata + live MJPEG URL |
| `get_comments(camera_id)` | All user comments |

#### Images

| Method | Description |
|--------|-------------|
| `get_thumbnail_url(camera_id)` | tiny.jpg URL (~62×48) |
| `get_small_url(camera_id)` | small.jpg URL |
| `get_medium_url(camera_id)` | medium.jpg URL |
| `get_snapshot_url(camera_id)` | big.jpg URL (current) |
| `get_historical_snapshots(camera_id)` | List of m-1 through m-6 URLs |
| `download_snapshot(camera_id, size, output_path)` | Download image bytes |

#### Search & filtering

| Method | Description |
|--------|-------------|
| `search(query, page)` | Keyword search, one page |
| `search_all(query, max_pages)` | Collect all search result pages |

#### Geography & metadata

| Method | Description |
|--------|-------------|
| `cameras_near(latitude, longitude, zoom)` | 40 nearest cameras (JSON API) |
| `get_all_camera_coords()` | Tile globe to collect all camera coordinates |
| `get_countries()` | All countries with counts from JSON API |
| `get_categories()` | Camera category tags |
| `get_camera_count_by_country()` | Dict of country → count |
| `get_total_camera_count()` | Total camera count from API |
| `count_pages(country, sort)` | Number of listing pages |

#### Community

| Method | Description |
|--------|-------------|
| `get_recent_comments(page)` | Latest community comments |
| `search_comments(query)` | Search comments by keyword |

---

### Sort orders

| Constant | Value | Description |
|----------|-------|-------------|
| `SORT_NEWEST` | `"newest"` | Most recently added |
| `SORT_RANDOM` | `"random"` | Random selection |
| `SORT_MOST_VIEWED` | `"oftenviewed"` | Most viewed |
| `SORT_HIGHEST_RATED` | `"highlyrated"` | Highest rated |

### Display modes

| Constant | Value | Description |
|----------|-------|-------------|
| `MODE_STANDARD` | `"standard"` | Last snapshot image |
| `MODE_ANIMATED` | `"animated"` | Animation of recent snapshots |

---

## CLI Usage

```bash
# Total camera count
python3 opentopia_client.py count

# List cameras (newest first)
python3 opentopia_client.py list
python3 opentopia_client.py list --country Japan
python3 opentopia_client.py list --country "United States" --sort highlyrated
python3 opentopia_client.py list --country "United States|California" --page 2

# Camera details
python3 opentopia_client.py info 12343

# Search
python3 opentopia_client.py search tokyo
python3 opentopia_client.py search "beach" --page 2

# Geographic search
python3 opentopia_client.py map 35.68 139.69          # Tokyo
python3 opentopia_client.py map 48.85 2.35            # Paris
python3 opentopia_client.py map 40.71 -74.00          # New York

# Country statistics
python3 opentopia_client.py countries
```

---

## Data Structures

### `Camera` dataclass

```python
@dataclass
class Camera:
    id: int                    # Numeric camera ID
    title: str                 # Camera title/name
    country: str               # Country name
    region: str                # State or province
    city: str                  # City/locality
    latitude: float            # GPS latitude
    longitude: float           # GPS longitude
    brand: str                 # Camera brand (Axis, Mobotix, etc.)
    views: int                 # Total view count
    rating: float              # Average rating (1.0–5.0)
    num_votes: int             # Number of rating votes
    num_comments: int          # Number of comments
    live_url: str              # Direct MJPEG/stream URL (if available)
    url_tiny: str              # images.opentopia.com/cams/{id}/tiny.jpg
    url_small: str             # .../small.jpg
    url_medium: str            # .../medium.jpg
    url_big: str               # .../big.jpg
    snapshots: list            # [m-1.jpg, m-2.jpg, ..., m-6.jpg]
    animation_frames: list     # Numbered frame URLs from flipbook
```

### `Comment` dataclass

```python
@dataclass
class Comment:
    author: str    # Username
    date: str      # Date string e.g. "09/15/24 00:55"
    text: str      # Comment text
```

---

## Known Camera Brands

The site catalogs cameras from various manufacturers:
- **Axis** (most common, ~MJPEG streaming)
- **Mobotix** (MJPEG)
- **Panasonic**
- **Sony**
- **Vivotek**
- Various generic/unknown IP cameras

---

## Pagination

- The listing (`/hiddencam.php`) returns ~24 cameras per page
- Max pages depend on filter:
  - All cameras: ~105 pages (~1508 cameras / ~15 per effective page including sidebar)
  - Japan: ~18 pages (~264 cameras)
  - United States: ~20+ pages
- The last page number shown in pagination is `100` as default, but results continue past page 100
- Use `count_pages()` to detect the actual maximum, or use `iter_all_cameras()` which stops automatically when duplicates are detected

---

## Rate Limiting & Politeness

The client defaults to a 0.5-second delay between requests (`request_delay=0.5`). For bulk operations use `iter_all_cameras()` with `page_delay=1.0` or higher:

```python
client = OpentopiaClient(request_delay=1.0)
for cam in client.iter_all_cameras(page_delay=2.0):
    process(cam)
```

---

## WebSocket (Real-time)

The site uses [WebSocketRails](https://github.com/websocket-rails/websocket-rails) at `ws://ws.opentopia.com/websocket` to broadcast real-time camera view events. When any user views a camera, an event fires on the `views` channel with the camera ID and metadata.

Example Python client using `websocket-client`:

```python
import json
import websocket

def on_message(ws, message):
    events = json.loads(message)
    for event in (events if isinstance(events, list) else [events]):
        if isinstance(event, list) and len(event) >= 2:
            name, data = event[0], event[1]
            if name == 'channel' and 'data' in data:
                info = data['data'].get('info', {})
                cam_id = info.get('camera_id')
                cam_key = info.get('cam_key', '')
                parts = cam_key.split('|')
                print(f"Viewed: cam {cam_id} - {parts[1] if len(parts) > 1 else ''}")

ws = websocket.WebSocketApp(
    "ws://ws.opentopia.com/websocket",
    on_message=on_message
)
ws.run_forever()
```

---

## Limitations

1. **No official API** — all endpoints are reverse-engineered and may change without notice.
2. **HTML scraping** — the listing and camera detail pages require HTML parsing; structure changes will break the client.
3. **Map API coverage** — `cameras_near()` returns only 40 cameras per query; getting all cameras requires the listing endpoint.
4. **Live URLs** — not all cameras expose a live MJPEG URL; many show a static saved snapshot as the "live" image. Requires loading `viewmode=livevideo` to discover.
5. **No bulk JSON API** — there is no endpoint to download all camera metadata at once; full enumeration requires ~100+ HTTP requests.
6. **Authentication** — some features (voting, favoriting, commenting) require a logged-in account; the client doesn't implement authentication.
7. **Geographic numbering** — animation frame numbers (`81720560.jpg`) are internal sequence IDs, not timestamps; you cannot predict future frame URLs.
