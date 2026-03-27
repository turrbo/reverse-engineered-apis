# Camscape API – Reverse Engineering Notes & Python Client

**Site:** https://www.camscape.com
**Type:** WordPress with custom `camscape` REST API plugin
**Plugin:** `dm-camscape-gutenberg` (Gutenberg blocks + REST routes)
**Theme:** `camscape` (custom theme with playerjs, Leaflet, Flickity)
**Researched:** 2026-03-27

---

## Summary

Camscape is a webcam aggregator curating 1,325+ live cameras worldwide.
The site runs on WordPress but **locks down the standard WP REST API** (401
on all `/wp-json/wp/v2/` endpoints). Data is available via:

1. **Custom REST endpoint** `/wp-json/camscape/v1/sayt/{term}` – search
2. **Custom REST endpoint** `/wp-json/camscape/v1/iss` – ISS position
3. **XML sitemaps** – full enumeration of all webcam/location/category URLs
4. **HTML page scraping** – structured JS variables embedded in each page

---

## API Endpoints

### 1. SAYT Search

```
GET https://www.camscape.com/wp-json/camscape/v1/sayt/{term}
```

**No authentication required.**

Returns up to 11 results mixing webcams, locations, and categories.

Route regex: `(?P<search_string>([a-zA-Z1-9]|.|%20|%27|%26)+)`
Supported encoded chars: spaces (`%20`), apostrophes (`%27`), ampersands (`%26`).

**Response schema:**

```json
[
  {
    "value": "Notre Dame Cathedral Webcam in Paris",
    "label": "Notre Dame Cathedral Webcam in Paris",
    "img": "https://www.camscape.com/content/uploads/.../notredame-200x113.jpg",
    "url": "https://www.camscape.com/webcam/notre-dame-cathedral-webcam-in-paris/"
  },
  {
    "value": "Paris",
    "label": "Paris",
    "location": true,
    "url": "https://www.camscape.com/location/paris/"
  },
  {
    "value": "Beaches",
    "label": "Beaches",
    "showing": true,
    "url": "https://www.camscape.com/showing/beaches/"
  }
]
```

**Result type discrimination:**
- Webcam entry → has `img` key (thumbnail URL, 200x113 px)
- Location entry → has `"location": true`
- Category entry → has `"showing": true`

**Examples:**

```bash
curl "https://www.camscape.com/wp-json/camscape/v1/sayt/paris"
curl "https://www.camscape.com/wp-json/camscape/v1/sayt/new%20york"
curl "https://www.camscape.com/wp-json/camscape/v1/sayt/london"
```

---

### 2. ISS Position

```
GET https://www.camscape.com/wp-json/camscape/v1/iss
```

Returns JSON with `latitude` and `longitude` of the International Space Station.
The endpoint proxies an upstream ISS tracking service and may return an empty
`200 OK` body when the upstream is unavailable.

**Full route list** (from `/wp-json/camscape/v1/`):
```
GET /camscape/v1/sayt/(?P<search_string>...)
GET /camscape/v1/iss
```

---

### 3. Locked WP REST Endpoints (Auth Required)

All standard WordPress REST API endpoints return `401 Authentication required`:

```
GET /wp-json/wp/v2/webcam        (listing)
GET /wp-json/wp/v2/webcam/{id}   (single webcam)
GET /wp-json/wp/v2/location/{id} (location taxonomy)
GET /wp-json/wp/v2/pages
GET /wp-json/wp/v2/posts
```

---

## Sitemap Enumeration

All 1325+ webcams can be enumerated without authentication via XML sitemaps.

| Sitemap | Count | URL |
|---------|-------|-----|
| Webcam sitemap 1 | 1,000 | `/webcam-sitemap.xml` |
| Webcam sitemap 2 | ~325 | `/webcam-sitemap2.xml` |
| Location sitemap | ~210 | `/location-sitemap.xml` |
| Category sitemap | ~47 | `/showing-sitemap.xml` |

Sitemap index: `/sitemap_index.xml`

Each `<loc>` tag in the webcam sitemaps contains the full URL, e.g.:
```
https://www.camscape.com/webcam/notre-dame-cathedral-webcam-in-paris/
```

---

## HTML Page Data (Embedded JS Variables)

Each webcam page embeds structured data as JavaScript variables.

### camscapePlayer (stream data)

```javascript
var camscapePlayer = {
  "webcamid": "4678",
  "templatedir": "https://www.camscape.com/content/themes/camscape",
  "streams": [
    {
      "name": "Notre Dame",
      "type": "iframe",
      "url": "https://www.youtube.com/embed/k3DZKHJ4Aqg?autoplay=1",
      "show_reported_notice": false,
      "image": "",
      "description": "",
      "source": "<div>...</div>"
    }
  ],
  "ajaxurl": "https://www.camscape.com/wp/wp-admin/admin-ajax.php"
};
```

**Stream types:**

| Type | Description | How to use |
|------|-------------|------------|
| `iframe` | Embeddable player URL | `<iframe allow="autoplay" src="url">` |
| `popup` | Opens in popup window | `window.open(url, '', 'width=1000,height=700')` |
| `player` | Direct HLS/MP4 stream | Play with HLS.js or video.js |
| `mjpeg` | Direct MJPEG stream | `<img src="url">` |

Common `iframe` providers:
- YouTube (`youtube.com/embed/...`)
- IPCamLive (`ipcamlive.com/player/player.php?alias=...`)
- EarthCam (`public.earthcam.net/...`)
- ViewSurf (`broadcast.viewsurf.com/...` or `pv.viewsurf.com/...`)
- AngelCam (`v.angelcam.com/iframe?v=...`)
- Skaping (`skaping.com/...`)
- Joada (`platforms5.joada.net/embeded/...`)

### camscapeWebcamMap (geo data)

```javascript
var camscapeWebcamMap = {
  "webcam": {
    "lat": 48.8522914,
    "lng": 2.348156,
    "markers": [
      {
        "label": "Quai de Montebello, 75005 Paris, Ile-de-France France",
        "lat": 48.8523478,
        "lng": 2.3483751,
        "geocode": [],
        "uuid": "marker_65fec0da7b334"
      }
    ],
    "zoom": 12,
    "layers": ["OpenStreetMap.Mapnik"]
  },
  "templatedir": "...",
  "iss": "false",
  "siteurl": "https://www.camscape.com"
};
```

### camscapeWorldmap (global map page only)

The `/webcam-map/` page embeds all geolocated webcams in a single JS object:

```javascript
var camscapeWorldmap = {
  "webcams": {
    "4678": {
      "title": "Notre Dame Cathedral Webcam in Paris",
      "lat": 48.8522914,
      "lng": 2.348156,
      "link": "https://www.camscape.com/webcam/notre-dame-cathedral-webcam-in-paris/",
      "img": "https://www.camscape.com/content/uploads/.../notredame-200x113.jpg"
    },
    ...  // 1325 total entries
  },
  "iss": "649"   // webcam ID of the ISS entry
};
```

**This is the most efficient bulk data source** — 1,325 webcams with title,
lat/lng, URL, and thumbnail in a single HTTP request.

### camscapeFavourites (sidebar)

```javascript
var camscapeFavourites = {
  "webcamid": "4678",
  "ajaxurl": "https://www.camscape.com/wp/wp-admin/admin-ajax.php"
};
```

---

## Admin Ajax Actions

`POST https://www.camscape.com/wp/wp-admin/admin-ajax.php`

| Action | Description |
|--------|-------------|
| `camscape_update_webcam_favourites` | Toggle favourite (cookie `faveWebcams`) |
| `camscape_report_webcam` | Report a stream as broken |

Both actions appear to require user context (cookie) but do not require
server-side authentication for counting.

---

## URL Structure

| Pattern | Example |
|---------|---------|
| `/webcam/{slug}/` | `/webcam/notre-dame-cathedral-webcam-in-paris/` |
| `/location/{slug}/` | `/location/france/` |
| `/showing/{slug}/` | `/showing/beaches/` |
| `/locations/` | Lists all countries/cities |
| `/showing/` | Lists all categories |
| `/new-webcams/` | Recently added |
| `/hot-right-now/` | Trending |
| `/webcam-map/` | World map (contains all geo data) |

---

## Known Categories (43 total)

`alpacas`, `bats`, `beaches`, `bears`, `bees`, `big-cats`, `big-dogs`,
`birds`, `boats`, `bovines`, `buildings`, `business-miscellaneous`,
`christmas`, `cityscapes`, `critters`, `culture`, `deer`,
`domestic-animals`, `elephants`, `entertainment`, `giraffes`, `goats`,
`horses`, `landscapes`, `monsters`, `nature`, `nightlife`, `pigs`,
`planes-airports`, `primates`, `religion`, `rivers-seas-lakes`, `roads`,
`sealife`, `shopping-district`, `ski-resorts`, `space-astronomy`,
`squirrels`, `tortoises`, `tourist-attractions`, `trains-railways`,
`urban-spaces`, `zebras`

---

## Python Client Usage

### Installation

No extra dependencies required (uses stdlib `urllib`). Optionally install
`requests` for improved reliability:

```bash
pip install requests
```

### Basic Usage

```python
from camscape_client import CamscapeClient

client = CamscapeClient(rate_limit_delay=0.5)

# --- Search ---
results = client.search("paris")
for r in results:
    rtype = "location" if r.get("location") else ("category" if r.get("showing") else "webcam")
    print(f"[{rtype}] {r['label']}  ->  {r['url']}")

# Search helpers
webcams = client.search_webcams_only("tokyo")
locations = client.search_locations_only("spain")
```

### Get a Single Webcam

```python
cam = client.get_webcam("notre-dame-cathedral-webcam-in-paris")

print(cam["title"])          # Notre Dame Cathedral Webcam in Paris
print(cam["id"])             # 4678  (WordPress post ID)
print(cam["lat"], cam["lng"]) # 48.8523 2.3482
print(cam["published"])      # 2024-03-24T20:15:33+00:00
print(cam["modified"])       # 2024-11-13T15:00:06+00:00
print(cam["thumbnail"])      # https://...notredamecathedralwebcam.jpg
print(cam["timezone"])       # Europe/Paris
print(cam["temperature"])    # 11°C
print(cam["showing"])        # [{"slug": "buildings", "name": "Buildings"}, ...]
print(cam["locations"])      # [{"slug": "france", "name": "France"}]
print(cam["description"])    # It's hard to gauge the grandeur...

for stream in cam["streams"]:
    print(f"  [{stream['type']}] {stream['name']}: {stream['url']}")
    # [iframe] Notre Dame: https://www.youtube.com/embed/k3DZKHJ4Aqg?autoplay=1
```

### Get Just Stream URLs

```python
streams = client.get_stream_urls_for_webcam("several-views-of-andratx-in-mallorca")
for s in streams:
    print(f"[{s['type']}] {s['name']}: {s['url']}")
# [iframe] Port Cam: https://www.youtube.com/embed/Qkf5KlpCrEU?autoplay=1
# [iframe] Golf Course: https://www.youtube.com/embed/jG5h0Lq8lwc?autoplay=1
# [iframe] City Cam: https://www.youtube.com/embed/-YAN1WIW7-I?autoplay=1
# [iframe] Port Cam 2: https://www.youtube.com/embed/RPTEW6-Dau0?autoplay=1
```

### Browse by Location / Category

```python
# All webcams in France (32 total)
france_cams = client.get_webcams_by_location("france")
for cam in france_cams:
    print(cam["title"], cam["timezone"])

# Beach cameras (163 total)
beach_cams = client.get_webcams_by_category("beaches")

# Trending right now
trending = client.get_trending_webcams()   # ~20 items

# Recently added
new_cams = client.get_new_webcams()        # ~8 items
```

### Get All Locations

```python
locations = client.get_all_locations()
for loc in locations[:5]:
    print(f"{loc['slug']}: {loc['name']} ({loc['count']} cams) -> {loc['url']}")
# france: France (32 cams) -> https://www.camscape.com/location/france/
# germany: Germany (43 cams) -> https://www.camscape.com/location/germany/
```

### Enumerate All Webcams (Sitemaps)

```python
# Get all 1325 webcam URLs
all_urls = client.get_all_webcam_urls()
print(f"Total: {len(all_urls)}")  # 1325

# Get just slugs
slugs = client.get_all_webcam_slugs()
print(slugs[:3])
# ['notre-dame-cathedral-webcam-in-paris', 'london-riverfront-views', ...]
```

### Get All Geolocated Webcams (Single Request)

```python
# Most efficient bulk fetch – 1325 webcams in ONE HTTP request
map_data = client.get_worldmap_data()

for cam_id, cam in list(map_data["webcams"].items())[:5]:
    print(f"[{cam_id}] {cam['title']}  "
          f"lat={cam['lat']:.4f} lng={cam['lng']:.4f}  "
          f"url={cam['link']}")

# Output:
# [4678] Notre Dame Cathedral Webcam in Paris  lat=48.8523 lng=2.3482  url=...
```

### Bulk Scrape with Progress

```python
client = CamscapeClient(rate_limit_delay=1.0)  # polite scraping

def on_progress(i, total, cam):
    status = cam.get("title", f"ERROR: {cam.get('error', '?')}")
    print(f"[{i}/{total}] {status}")

slugs = client.get_all_webcam_slugs()[:50]
cameras = client.bulk_get_webcams(slugs, on_progress=on_progress)

# Filter successful results
successful = [c for c in cameras if "error" not in c]
print(f"Fetched: {len(successful)}/{len(slugs)}")
```

### ISS Position

```python
iss = client.get_iss_position()
if iss:
    print(f"ISS: lat={iss['latitude']}, lng={iss['longitude']}")
```

---

## Data Schema Reference

### Webcam dict (from `get_webcam()`)

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | WordPress post ID |
| `slug` | str | URL slug |
| `url` | str | Full page URL |
| `title` | str | Webcam title |
| `description` | str | Plain-text description |
| `thumbnail` | str | Thumbnail image URL |
| `published` | str | ISO 8601 published datetime |
| `modified` | str | ISO 8601 last-modified datetime |
| `lat` | float\|None | Latitude |
| `lng` | float\|None | Longitude |
| `markers` | list | Location marker dicts with lat/lng/label |
| `showing` | list | Category tags `[{slug, name}]` |
| `locations` | list | Location tags `[{slug, name}]` |
| `streams` | list | Stream dicts (see below) |
| `temperature` | str\|None | Current temp, e.g. `"11°C"` |
| `timezone` | str\|None | IANA timezone, e.g. `"Europe/Paris"` |
| `favourites` | str\|None | Favourite count |
| `views` | str\|None | View count, e.g. `"5.9k"` |
| `raw_player` | dict | Raw `camscapePlayer` JS object |
| `raw_map` | dict | Raw `camscapeWebcamMap` JS object |

### Stream dict

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Display name |
| `type` | str | `iframe`, `popup`, `player`, or `mjpeg` |
| `url` | str | Stream URL |
| `image` | str | Preview image URL (popup type) |
| `description` | str | Plain-text description |
| `show_reported_notice` | bool | True if flagged as broken |

### Tile dict (from listing pages)

| Field | Type | Description |
|-------|------|-------------|
| `url` | str | Full webcam page URL |
| `slug` | str | URL slug |
| `title` | str | Webcam title |
| `thumbnail` | str | Tile thumbnail URL |
| `showing` | list | Category tags |
| `locations` | list | Location tags |
| `timezone` | str\|None | IANA timezone |

---

## Technical Notes

### Rate Limiting

Camscape does not enforce strict rate limits for public browsing, but as a
courtesy the client defaults to 0.5s between requests. For bulk scraping,
use at least 1.0s delay.

### Stream Embedding

The site uses a custom playerjs library (`playerjs.min.js`) for `player` type
streams (obfuscated, ~440KB). For `iframe` streams, a standard `<iframe>` with
`allow="autoplay"` works. For `mjpeg` streams, use `<img src="...">`. For
`popup` streams, open in a new window.

### WordPress Structure

- Post type: `webcam` (custom post type)
- Taxonomies: `location` (country/city), `showing` (category)
- Theme: `camscape` at `/content/themes/camscape/`
- Plugin: `dm-camscape-gutenberg` at `/content/plugins/dm-camscape-gutenberg/`
- WP core at non-standard path: `/wp/`

### Content Paths

WordPress media uploads are at:
`https://www.camscape.com/content/uploads/{year}/{month}/{filename}`

Theme assets at:
`https://www.camscape.com/content/themes/camscape/assets/`

---

## Running the Demo

```bash
python3 camscape_client.py
```

This runs all 9 demo sections and verifies all major endpoints are working.
