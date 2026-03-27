# SkylineWebcams Python Client

Reverse-engineered client for [SkylineWebcams](https://www.skylinewebcams.com/), a platform hosting 2,000+ live HD webcams from landmarks worldwide (100M+ total viewers). All endpoints discovered through systematic HTML/JavaScript analysis of live traffic (no browser automation required).

**Verified working: 2026-03-27.**

---

## Quick Start

```python
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()

# HLS camera: Trevi Fountain, Rome (cam_id=286)
cam = client.get_camera("italia/lazio/roma/fontana-di-trevi")
print(cam.stream_type)   # "hls"
print(cam.hls_url)       # https://hd-auth.skylinewebcams.com/live.m3u8?a=...
print(cam.rating)        # 4.8

# YouTube camera: Times Square, New York (cam_id=538)
yt_cam = client.get_camera("united-states/new-york/new-york/times-square")
print(yt_cam.stream_type)       # "youtube"
print(yt_cam.youtube_url)       # https://www.youtube.com/watch?v=rnXIjl_Rzy4
print(yt_cam.youtube_embed_url) # https://www.youtube.com/embed/rnXIjl_Rzy4

# List Italian cameras
for cam in client.list_by_country("italy")[:5]:
    print(cam.cam_id, cam.name)

# Live viewer stats
stats = client.get_stats("286")
print(f"{stats.current_viewers} watching now, {stats.total_views} total views")

# Daily time-lapse HLS stream (own cameras only)
tl_url = client.get_timelapse_url("italia/lazio/roma/fontana-di-trevi")
print(tl_url)  # https://hd-auth.skylinewebcams.com/lapse.m3u8?a=...
```

---

## Requirements

- Python 3.10+ (uses `list[X]` type hints, dataclasses)
- Standard library only: `urllib`, `re`, `json`, `dataclasses`, `logging`
- No third-party packages required

```bash
python3 skylinewebcams_client.py   # runs built-in demo
```

---

## Discovered Endpoints

All endpoints were verified working on 2026-03-27.

### Web Pages (HTML scraping)

| URL Pattern | Description |
|---|---|
| `/en/webcam.html` | Full camera directory (~900 cameras) |
| `/en/webcam/{country}.html` | Cameras by country |
| `/en/webcam/{country}/{region}.html` | Cameras by region |
| `/en/webcam/{country}/{region}/{city}.html` | Cameras by city |
| `/en/webcam/{country}/{region}/{city}/{slug}.html` | Individual camera page |
| `/en/live-cams-category/{category}.html` | Cameras by category |
| `/en/top-live-cams.html` | Editor-curated top cameras |
| `/en/new-livecams.html` | Most recently added cameras |
| `/en/weather/{country}/{region}/{city}.html` | Weather page for location |

Country slugs use native/local names:
- Italy → `italia`
- Spain → `espana`
- Greece → `ellada`
- Germany → `deutschland`
- Croatia → `hrvatska`
- Norway → `norge`
- Switzerland → `schweiz`
- Brazil → `brasil`

### HLS Live Streaming

The streaming architecture uses three components:

**1. Auth token** — extracted from the camera page JavaScript:
```javascript
var player = new Clappr.Player({
    nkey: '522.jpg',            // → camera ID is 522
    source: 'livee.m3u8?a=79gs0jtbva0holb24om3frb5h1',  // → auth token
    ...
});
```

**2. HLS playlist endpoint:**
```
GET https://hd-auth.skylinewebcams.com/live.m3u8?a={auth_token}

Headers required:
  Referer: https://www.skylinewebcams.com/

Response: HLS m3u8 playlist (#EXTM3U) listing .ts segments
```

**3. Video segments (.ts files):**
```
https://hddn{N}.skylinewebcams.com/{cam_id}livic-{unix_ms_timestamp}.ts
```
Example:
```
https://hddn57.skylinewebcams.com/0416livic-1774633226246.ts
```
- `hddn{N}` — CDN node number (varies per stream)
- `{cam_id}` — zero-padded camera ID, e.g. `0416` for cam 416
- Segments are approximately 4 seconds each; 3–8 segments in the playlist at any time

**Token rotation:** Auth tokens are session-bound and rotate on each page load. For long-running processes, re-fetch the camera page periodically (every 30–60 minutes) to refresh the token.

**Offline cameras:** When a camera is offline, the m3u8 playlist returns `#EXT-X-ENDLIST` immediately with no segments.

### Camera Thumbnails & Snapshots

All thumbnails are served without authentication.

| URL Pattern | Description | Approx Size |
|---|---|---|
| `https://cdn.skylinewebcams.com/live{cam_id}.jpg` | Live-updating thumbnail | ~18 KB |
| `https://cdn.skylinewebcams.com/{cam_id}.jpg` | Static page thumbnail | ~58 KB |
| `https://cdn.skylinewebcams.com/social{cam_id}.jpg` | OG/social image, 1200×628 | ~160 KB |
| `https://cdn.skylinewebcams.com/as/img/hosts/{cam_id}.jpg` | Camera host/sponsor logo | varies |

Live thumbnails update approximately every 30 seconds. Social images are 1200×628 JPEG.

### Camera Statistics (JSON)

```
GET https://cdn.skylinewebcams.com/{cam_id}.json

Response:
{
  "t": "52.341.534",   // total all-time views (dot-formatted string)
  "n": "293"           // current live viewer count
}
```

No authentication required. Updates approximately every 30 seconds.

Note: `t` (total views) uses dots as thousands separators (Italian convention), not commas.

### Photos / Snapshot Archive

Users can share timestamped screenshots from webcam views. Two endpoints:

**1. Photo list for a camera:**
```
GET https://photo.skylinewebcams.com/pht.php?pid={cam_id}&l={lang}

Returns: HTML partial with photo grid
```

**2. Photo gallery (carousel for a single photo entry):**
```
GET https://photo.skylinewebcams.com/gallery.php?id={photo_id}&l={lang}

Returns: HTML partial with full-resolution image carousel
```

**Photo image URLs:**
```
Thumbnail:  https://photo.skylinewebcams.com/pht/_{hash}.jpg   (small, with underscore prefix)
Full-res:   https://photo.skylinewebcams.com/pht/{hash}.jpg    (full, no underscore)
```
Example hash: `69c4d03e59618` — these appear to be Unix timestamps in hex.

### Utility Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/cams/login.php?l={lang}` | GET/POST | Login modal content |
| `/cams/info.php?l={lang}` | GET | Info/premium modal content |
| `/cams/share.php?l={lang}&w={cam_id}&u={encoded_url}` | GET | Share modal content |
| `/cams/rating.php?r={value}&id={cam_id}` | GET | Submit star rating (1-5), returns HTML msg |
| `/click.php?l={base64}` | GET | Sponsor redirect; param = base64(`{cam_id}\|{type}\|{url}`) |
| `https://ad.skylinewebcams.com/ad.php` | POST `id="{cam_id}_{lang}"` | Ad rotation, returns URL-encoded ad data |

---

## Client API Reference

### `SkylineWebcamsClient(language, request_delay, timeout)`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `language` | str | `"en"` | Language code: en, it, de, es, fr, pl, el, hr, sl, ru, zh |
| `request_delay` | float | `0.5` | Seconds between requests (rate limiting) |
| `timeout` | int | `15` | HTTP timeout in seconds |

### Camera Listing Methods

```python
# All return list[WebcamInfo] (without HLS token)

client.list_by_country("italy")           # or "italia", "espana", etc.
client.list_by_region("italy", "veneto")
client.list_by_city("italy", "veneto", "venezia")
client.list_by_category("volcanoes")      # see Categories below
client.list_top_cameras()                 # editor curated
client.list_new_cameras()                 # recently added
client.list_all_cameras()                 # full directory (~900 cameras)
```

### Individual Camera Detail

```python
# Returns WebcamInfo WITH stream fields populated (hls_url/token or youtube_video_id)
cam = client.get_camera("italia/veneto/venezia/piazza-san-marco")
cam = client.get_camera("/en/webcam/italia/veneto/venezia/piazza-san-marco.html")
cam = client.get_camera("https://www.skylinewebcams.com/en/webcam/italia/...")

# Check stream type after loading
print(cam.stream_type)   # "hls" or "youtube"
print(cam.rating)        # float, e.g. 4.8
```

### Streaming

```python
# get_stream_url() works for both stream types:
#   HLS cameras  → "https://hd-auth.skylinewebcams.com/live.m3u8?a=<token>"
#   YouTube cams → "https://www.youtube.com/watch?v=<video_id>"
url = client.get_stream_url(cam)

# HLS-specific methods (require stream_type == "hls")
playlist = client.get_m3u8_playlist(cam)    # raw m3u8 playlist text
segments = client.get_stream_segments(cam)  # list of .ts segment URLs

# Daily time-lapse HLS stream (own/HLS cameras only)
# Fetches the /timelapse.html page and extracts the lapse token
tl_url = client.get_timelapse_url("italia/lazio/roma/fontana-di-trevi")
# → "https://hd-auth.skylinewebcams.com/lapse.m3u8?a=<token>"
```

### Thumbnails

```python
# Download raw JPEG bytes
img_bytes = client.get_thumbnail(cam_id)         # live, ~18KB
img_bytes = client.get_social_image(cam_id)      # OG image, ~160KB

# Get URL without downloading
url = client.get_thumbnail_url(cam_id, size="live")    # "live" | "social" | "static"
```

### Stats

```python
stats = client.get_stats(cam_id)
print(stats.total_views)       # "52.341.534"
print(stats.current_viewers)   # 293
```

### Photos

```python
photos = client.get_photos(cam_id)
for photo in photos:
    print(photo.date_label, photo.thumbnail_url, photo.full_url)

# Full-res photos in a gallery entry
urls = client.get_photo_gallery(photo_id)

# Download
data = client.download_photo(photo.full_url)
```

### Search

```python
# Substring search on camera names/descriptions from full directory
results = client.search("venice")
results = client.search("volcano")

# Cross-filter: category + country
results = client.search_by_category_and_country("beaches", "spain")
```

### Discovery

```python
# All supported countries with slugs
countries = client.list_countries()
# → [{"name": "Italy", "slug": "italia", "url": "..."}, ...]

# All categories
categories = client.list_categories()

# Cameras on the same page (nearby tab)
nearby = client.get_nearby_cameras(cam)
```

### Utilities

```python
# HTML embed iframe
html = client.get_embed_code(cam, width=640, height=360)

# Weather page URL
url = client.get_weather_url("italia", "veneto", "venezia")
```

---

## Data Models

### `WebcamInfo`

| Field | Type | Description |
|---|---|---|
| `cam_id` | str | Numeric camera ID (e.g. `"522"`) |
| `name` | str | Camera display name |
| `description` | str | Camera description / subtitle |
| `url` | str | Full URL path of the camera page |
| `country_slug` | str | Country slug from URL (e.g. `"italia"`) |
| `region_slug` | str | Region slug from URL (e.g. `"veneto"`) |
| `city_slug` | str | City slug from URL (e.g. `"venezia"`) |
| `cam_slug` | str | Camera-specific slug from URL |
| `thumbnail_url` | str | `cdn.skylinewebcams.com/live{id}.jpg` |
| `social_image_url` | str | `cdn.skylinewebcams.com/social{id}.jpg` |
| `static_thumbnail_url` | str | `cdn.skylinewebcams.com/{id}.jpg` |
| `stream_type` | str | `"hls"` for own-infrastructure cameras; `"youtube"` for YouTube-embedded cameras (from `get_camera()` only) |
| `hls_token` | str | Auth token for HLS stream (from `get_camera()` only, `stream_type == "hls"`) |
| `hls_url` | str | Full HLS m3u8 URL (from `get_camera()` only, `stream_type == "hls"`) |
| `youtube_video_id` | str | YouTube video ID (from `get_camera()` only, `stream_type == "youtube"`) |
| `youtube_url` | str | `https://www.youtube.com/watch?v={id}` — computed property |
| `youtube_embed_url` | str | `https://www.youtube.com/embed/{id}` — computed property |
| `rating` | float | Star rating (0.0–5.0); from `get_camera()` only |
| `rating_count` | int | Number of ratings; from `get_camera()` only |
| `total_views` | str | Formatted view count string |
| `current_viewers` | int | Live viewer count |
| `upload_date` | str | ISO8601 publication date |
| `interaction_count` | int | All-time interaction count from schema.org |

### `CameraStats`

| Field | Type | Description |
|---|---|---|
| `cam_id` | str | Camera ID |
| `total_views` | str | Dot-formatted total views |
| `current_viewers` | int | Current live viewers |

### `PhotoSnapshot`

| Field | Type | Description |
|---|---|---|
| `photo_id` | str | Gallery entry ID |
| `cam_id` | str | Parent camera ID |
| `thumbnail_url` | str | Small preview JPEG URL |
| `full_url` | str | Full-resolution JPEG URL |
| `date_label` | str | Human-readable date or caption |

---

## Categories

| Friendly name | URL slug |
|---|---|
| `beaches` | `beach-cams` |
| `cities` | `city-cams` |
| `landscapes` | `nature-mountain-cams` |
| `marinas` | `seaport-cams` |
| `ski` | `ski-cams` |
| `animals` | `animals-cams` |
| `volcanoes` | `volcanoes-cams` |
| `lakes` | `lake-cams` |
| `unesco` | `unesco-cams` |
| `web` | `live-web-cams` |

---

## Country Slug Reference

The site uses local-language or irregular country slugs:

| Display Name | URL Slug |
|---|---|
| Italy | `italia` |
| Spain | `espana` |
| Greece | `ellada` |
| Germany | `deutschland` |
| Croatia | `hrvatska` |
| Norway | `norge` |
| Switzerland | `schweiz` |
| Brazil | `brasil` |
| Slovenia | `slovenija` |
| United States | `united-states` |
| United Kingdom | `united-kingdom` |
| Czech Republic | `czech-republic` |
| Dominican Republic | `dominican-republic` |
| South Africa | `south-africa` |
| US Virgin Islands | `us-virgin-islands` |
| Sint Maarten | `sint-maarten` |
| San Marino | `repubblica-di-san-marino` |
| Cape Verde | `cabo-verde` |
| Bosnia | `bosnia-and-herzegovina` |
| Caribbean Netherlands | `caribbean-netherlands` |
| Costa Rica | `costa-rica` |
| El Salvador | `el-salvador` |
| Faroe Islands | `faroe-islands` |
| Sri Lanka | `sri-lanka` |
| Vietnam | `vietnam` |
| All others | standard English slug (e.g. `france`, `portugal`, `turkey`) |

---

## Languages

| Code | Language |
|---|---|
| `en` | English (default) |
| `it` | Italiano |
| `de` | Deutsch |
| `es` | Español |
| `fr` | Français |
| `pl` | Polish |
| `el` | Ελληνικά |
| `hr` | Hrvatski |
| `sl` | Slovenski |
| `ru` | Русский |
| `zh` | 简体中文 |

---

## Notable Known Camera IDs

| ID | Name |
|---|---|
| 522 | Venice - Piazza San Marco |
| 416 | Venice - Rialto Bridge / Canal Grande |
| 286 | Rome - Trevi Fountain |
| 205 | Rome - Piazza di Spagna |
| 1151 | Rome - Colosseum |
| 435 | Etna - Summit Craters |
| 741 | Etna - Main Crater |
| 1376 | Etna - Piazzale Rifugio Sapienza |
| 474 | Stromboli Volcano |
| 340 | Playa de Los Cristianos, Tenerife |
| 339 | Las Vistas Beach, Tenerife |
| 860 | Jerusalem - Western Wall |
| 992 | Tsavo East National Park, Kenya |
| 3165 | Plitvice Lakes National Park, Croatia |
| 4344 | Great Pyramid of Giza, Egypt |
| 832 | Porto Seguro, Brazil |
| 519 | Puerta del Sol, Madrid |
| 395 | Milan Cathedral (Duomo) |

---

## Technical Architecture Notes

### Player: Clappr
The site uses the open-source [Clappr](https://github.com/clappr/clappr) HTML5 video player with a custom `SkylineWebcams` UI plugin. Player code is served from:
```
https://cdn.jsdelivr.net/gh/SkylineWebcams/web@main/playerj.js
```

The player initialization reveals the HLS source construction:
```javascript
// From playerj.js:
var t = e.sources || (void 0 !== e.source
  ? ["https://hd-auth.skylinewebcams.com/" + e.source.replace("livee.", "live.")]
  : []);
```

So `source: 'livee.m3u8?a=TOKEN'` becomes `https://hd-auth.skylinewebcams.com/live.m3u8?a=TOKEN`.

### CDN Structure
- **Static assets**: `cdn.jsdelivr.net/gh/SkylineWebcams/web@main/` (GitHub CDN)
- **Camera thumbnails**: `cdn.skylinewebcams.com`
- **HLS auth**: `hd-auth.skylinewebcams.com`
- **Video CDN nodes**: `hddn{N}.skylinewebcams.com` (e.g. `hddn57`)
- **Photos**: `photo.skylinewebcams.com`
- **Ads**: `ad.skylinewebcams.com`

### Rate Limiting
The site does not appear to enforce strict rate limiting, but:
- Default client uses 0.5 s delay between requests
- Token-authenticated HLS endpoints return 200 without rate limiting
- CDN thumbnail endpoints have `access-control-allow-origin: *` (CORS open)

### CORS Headers
HLS and stats endpoints include:
```
access-control-allow-origin: *
```
This means browser-based JavaScript can access these directly.

### HLS Playlist Response Headers
```
content-type: application/x-mpegURL
cache-control: no-store,no-cache,must-revalidate,post-check=0,pre-check=0
x-frame-options: DENY
access-control-allow-origin: *
```

---

## Usage Examples

### Download a live snapshot

```python
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
with open("venice_snapshot.jpg", "wb") as f:
    f.write(client.get_thumbnail("522"))
print("Snapshot saved!")
```

### Stream with ffmpeg

```python
import subprocess
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
cam = client.get_camera("italia/veneto/venezia/piazza-san-marco")

# Play in VLC or ffplay
subprocess.run([
    "ffplay",
    "-referer", "https://www.skylinewebcams.com/",
    cam.hls_url
])
```

### Monitor multiple cameras

```python
import time
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
cam_ids = ["522", "416", "286", "435"]  # Venice, Rialto, Trevi, Etna

while True:
    for cam_id in cam_ids:
        stats = client.get_stats(cam_id)
        print(f"Cam {cam_id}: {stats.current_viewers} watching now")
    time.sleep(30)
```

### Collect volcano cameras

```python
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
volcanoes = client.list_by_category("volcanoes")
for cam in volcanoes:
    print(f"[{cam.cam_id:>5}] {cam.name}")
    print(f"         URL: https://www.skylinewebcams.com{cam.url}")
    print(f"         Thumb: {cam.thumbnail_url}")
```

### Get all Italian beach cameras

```python
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
# Method 1: search_by_category_and_country
italy_beaches = client.search_by_category_and_country("beaches", "italy")

# Method 2: scrape beach category, filter by URL
all_beaches = client.list_by_category("beaches")
italy_beaches = [c for c in all_beaches if "italia" in (c.url or "")]

for cam in italy_beaches:
    print(cam.name, cam.cam_id)
```

### Export camera metadata as JSON

```python
import json
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
cams = client.list_by_category("volcanoes")

data = []
for cam in cams:
    full_cam = client.get_camera(cam.url)
    data.append(full_cam.to_dict())

with open("volcanoes.json", "w") as f:
    json.dump(data, f, indent=2)
print(f"Exported {len(data)} cameras")
```

### Get archive photos for a camera

```python
from skylinewebcams_client import SkylineWebcamsClient

client = SkylineWebcamsClient()
photos = client.get_photos("522")  # Venice San Marco

print(f"Found {len(photos)} archive photos")
for photo in photos[:5]:
    print(f"  {photo.date_label}")
    print(f"  Thumb: {photo.thumbnail_url}")
    print(f"  Full:  {photo.full_url}")
    print()
```

---

## Limitations

1. **No official API** — All data is scraped from HTML pages. Site changes may break patterns.

2. **HLS token expiry** — Auth tokens are session-bound. For persistent monitoring, re-fetch the camera page periodically.

3. **No search API** — The built-in `search()` method scans the main directory (~900 cameras). Cameras on less-trafficked pages may not appear in results.

4. **No pagination API** — Country/category pages serve all cameras in a single HTML response. The client parses all available cards from that single page.

5. **Premium content** — Some cameras may require a premium account. The client does not handle authentication.

6. **Rate limiting** — Be a good citizen: use the default `request_delay=0.5` or higher. The site has no documented API TOS.

7. **Language affects URL structure** — Always use the same language code when constructing URLs. The default is `"en"`.

---

## Reverse Engineering Notes

### Discovery process

1. Fetched homepage HTML → found country/category navigation structure
2. Fetched individual camera page HTML → found Clappr player initialization with `nkey` (camera ID) and `source` (HLS auth token)
3. Analyzed `playerj.js` → found the URL construction: `https://hd-auth.skylinewebcams.com/live.m3u8?a={token}`
4. Tested HLS URL → confirmed HTTP 200, valid m3u8 playlist
5. Parsed m3u8 playlist → found CDN segment URLs pattern: `hddn{N}.skylinewebcams.com/{cam_id}livic-{ts}.ts`
6. Found stats JSON endpoint in page script: `$.get("//cdn.skylinewebcams.com/{cam_id}.json", ...)`
7. Found photo endpoint: `https://photo.skylinewebcams.com/pht.php?pid={cam_id}&l={lang}`
8. Decoded `click.php` parameter: base64 of `{cam_id}|{type}|{url}`

### Key files analyzed

- `https://www.skylinewebcams.com/en/webcam/italia/veneto/venezia/piazza-san-marco.html`
- `https://cdn.jsdelivr.net/gh/SkylineWebcams/web@main/playerj.js` (401 KB, contains Clappr + custom plugin)
- `https://cdn.jsdelivr.net/gh/SkylineWebcams/web@main/sky.js` (108 KB, contains jQuery + Bootstrap + site logic)
