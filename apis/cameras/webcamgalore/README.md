# WebcamGalore Python Client

A reverse-engineered Python client for [WebcamGalore.com](https://www.webcamgalore.com) — an aggregator of 8,000+ webcams worldwide (strong Alpine/European focus: Germany 1,374 · Italy 1,339 · Austria 1,152 · France 1,096 · USA 809 · Switzerland 603+).

---

## Installation

```bash
pip install requests
# Optional: pip install beautifulsoup4  (not required but used if present)
```

Copy `webcamgalore_client.py` into your project.

---

## Quick Start

```python
from webcamgalore_client import WebcamGaloreClient, get_webcams_near

# Context manager — automatically closes the session
with WebcamGaloreClient(delay=0.8) as client:

    # Get all countries with webcam counts
    countries = client.get_countries()
    top5 = sorted(countries, key=lambda x: x['count'], reverse=True)[:5]
    # [{'slug': 'Germany', 'name': 'Germany', 'count': 1374}, ...]

    # Get webcams in a bounding box (fastest, uses the map XML API)
    cams = client.get_webcams_by_bbox(latmin=47.1, latmax=47.5, lonmin=11.2, lonmax=11.7)
    for cam in cams:
        print(cam.cam_id, cam.city, cam.title, cam.lat, cam.lon)
        print("Current image:", cam.current_image_url)

    # Search by location name
    results = client.search("Innsbruck")

    # Get popular webcams right now
    popular = client.get_popular_webcams()

    # Get recently added webcams
    new_cams = client.get_new_webcams()
```

---

## Site Architecture

### Geographic Taxonomy

```
Continent
  └── Country         (e.g. Germany, Austria, Italy)
        └── State/Region  (e.g. Bavaria, Tyrol, Lombardy)
              └── City     (e.g. Munich, Innsbruck)
                    └── Webcam(s)  (numeric ID, e.g. 2907)
```

### URL Patterns

| Resource | URL Pattern |
|---|---|
| Homepage | `https://www.webcamgalore.com/` |
| Country listing (big) | `/{Country}/a-1.html`, `/{Country}/b-1.html`, ... |
| Country listing (small) | `/{Country}/countrycam-0.html` |
| State/region (big) | `/{Country}/{State}/a-1.html` |
| State/region (small) | `/{Country}/{State}/statecam-0.html` |
| Webcam detail | `/webcam/{Country}/{City}/{id}.html` |
| City all-cams | `/webcams/{City}/{id}.html` |
| Search | `/search.php?s={query}` |
| Autocomplete | `/autocomplete.php?lang=EN&q={query}` |
| Themes | `/theme.html` |
| Popular feed | `/popular.xml` (Atom) |
| New additions feed | `/new.xml` (Atom) |
| Complete list | `/complete-{a-z}.html` |
| **Map/geo API (XML)** | `/include/webcammap.php?lang=EN&lonmin=&lonmax=&latmin=&latmax=&w=&h=&tid=` |
| 30-day archive | `/30dj.php?id={id}&lang=EN&h=60&...` |
| 365-day archive | `/365dj.php?id={id}&lang=EN&h=60&...` |

### Image URL Patterns

All images are served from `https://images.webcamgalore.com`.

| Description | Pattern |
|---|---|
| Thumbnail 40×30 | `/webcamimages/40x30/{id}-pub.jpg` |
| Thumbnail 80×60 | `/webcamimages/80x60/{id}-pub.jpg` |
| Thumbnail 120×90 | `/webcamimages/120x90/{id}-pub.jpg` |
| Current full-res | `/webcamimages/webcam-{id:06d}.jpg` |
| Current named full-res | `/{id}-current-webcam-{city-slug}.jpg` |
| Map thumbnail (PNG) | `/images/mapthumbs/{id}.png` |
| 24h archive hourly thumb | `/webcam-archive/{HH}/webcam-80x60-{id}.jpg` |
| Hourly timelapse player | `/webcam-{city-slug}-{day_offset}-{hour}-{id}-{width}.jpg` |
| Hourly timelapse full-res | `/webcam-{city-slug}-{day_offset}-{hour}-{id}-full.jpg` |
| Daily archive (up to 365d) | `/oneyear/{MM}-{DD}/{id}.jpg` |

**Notes on hourly images:**
- `day_offset`: 0 = today, 1 = yesterday, 2 = day before, etc. (up to ~5 days)
- `hour`: not all hours are stored; the available hours are embedded in the page JS (`wcgplayerHourIndex`). Use `get_webcam_page_metadata()` to retrieve them.
- `city_slug`: lowercase hyphenated city name found in `wcgplayerImageCityname` JS variable.

---

## API Reference

### `WebcamGaloreClient`

```python
client = WebcamGaloreClient(
    delay=0.5,       # Seconds between requests (be polite)
    retries=3,       # Retry count on transient failures
    timeout=20,      # HTTP timeout in seconds
    lang="EN",       # Language: EN, DE, IT, ES, FR, DK
)
```

#### Geographic / Taxonomy

| Method | Description |
|---|---|
| `get_countries()` | All countries with webcam counts |
| `get_states(country)` | State/region breakdown for a country |

#### Webcam Discovery

| Method | Description |
|---|---|
| `get_webcams_by_bbox(latmin, latmax, lonmin, lonmax, theme_id, ...)` | **Recommended.** Uses the map XML API — returns structured Webcam objects with lat/lon, no HTML parsing needed. |
| `get_webcams_by_country_bbox(country, theme_id)` | Convenience wrapper with built-in bounding boxes for 15 major countries. |
| `get_webcams_by_country(country, state, letter, max_pages)` | Scrape alphabetical HTML listings. Slower but captures all cams. |
| `iter_all_webcams_for_country(country, state)` | Generator yielding all webcams for a country (all letters, all pages). Memory-efficient. |
| `get_webcams_by_theme(theme_id, latmin, latmax, lonmin, lonmax)` | Filter by theme (ski, beach, weather, etc.) over a region. |
| `search(query)` | Search by place name. |
| `autocomplete(query)` | City name autocomplete. |

#### Webcam Detail

| Method | Description |
|---|---|
| `get_webcam_detail(cam_id, country, city)` | Full metadata from detail page. |
| `get_webcam_page_metadata(cam_id, country, city)` | Parse JS variables: available hours, city slug, player dimensions, day captions. |

#### Archives

| Method | Description |
|---|---|
| `get_archive_30d(cam_id, city, ...)` | 30 daily snapshots |
| `get_archive_365d(cam_id, city, ...)` | Up to 365 daily snapshots |

#### Feeds

| Method | Description |
|---|---|
| `get_popular_webcams()` | Top 20 most-viewed in last 24h (Atom feed) |
| `get_new_webcams(limit)` | Recently added webcams (Atom feed) |

#### Image Download

| Method | Description |
|---|---|
| `download_current_image(cam, size, output_path)` | Download current snapshot. `size`: "40x30", "80x60", "120x90", "current" |
| `download_archive_image(cam, month, day, output_path)` | Download daily archive image |
| `download_hourly_image(cam, city_slug, day_offset, hour, width, output_path)` | Download timelapse hourly image |

#### Static Helpers

| Method | Description |
|---|---|
| `WebcamGaloreClient.list_themes()` | Dict of `{theme_id: name}` |
| `WebcamGaloreClient.build_image_url(cam_id, size)` | Build image URL without network call |
| `WebcamGaloreClient.build_archive_url(cam_id, month, day)` | Build archive URL without network call |

### `Webcam` Object

```python
cam.cam_id               # int: numeric ID (e.g. 2907)
cam.title                # str: camera title
cam.city                 # str: city name
cam.country              # str: country slug (e.g. "Germany")
cam.state                # str | None: state/region
cam.description          # str | None: description text
cam.lat / cam.lon        # float | None: WGS-84 coordinates
cam.operator             # str | None: operator name
cam.operator_url         # str | None: operator website
cam.listed_date          # str | None: date added to site
cam.hits                 # int | None: page view count
cam.theme_id             # int | None: primary theme

# URL properties (no network needed):
cam.page_url             # Full detail page URL
cam.thumbnail_40x30      # Thumbnail URL
cam.thumbnail_80x60
cam.thumbnail_120x90
cam.current_image_url    # Full-res current image
cam.map_thumbnail_url    # Map marker thumbnail (PNG)

# URL methods:
cam.named_current_image_url(city_slug)
cam.archive_daily_url(month, day)
cam.hourly_image_url(city_slug, day_offset, hour, width=640)
cam.hourly_full_url(city_slug, day_offset, hour)
cam.archive_hourly_thumbnail(hour)
```

---

## Themes

| ID | Theme |
|---|---|
| 1 | Traffic |
| 2 | Volcanos |
| 3 | Airports |
| 4 | Bars and Restaurants |
| 5 | Skyline |
| 6 | Landscapes |
| 7 | Beaches |
| 8 | Harbors |
| 9 | Buildings |
| 10 | Construction Sites |
| 13 | Animals |
| 14 | Rivers |
| 15 | City Views |
| 16 | Parks, Garden |
| 17 | Castles |
| 18 | Churches |
| 19 | Mountains |
| 20 | Islands |
| 21 | Coasts |
| 22 | Landmarks |
| 23 | Weather |
| 24 | Collections |
| 25 | Seaview |
| 26 | Science |
| 27 | Railroads |
| 28 | Public Places |
| 29 | Ski-Resorts |
| 30 | Shopping-Malls |
| 31 | Cruise Ships |
| 32 | Other |

---

## Recipes

### Alpine ski resort webcams

```python
from webcamgalore_client import get_ski_resort_webcams

cams = get_ski_resort_webcams()  # All Alpine ski cams
for cam in cams:
    print(cam.city, cam.country, cam.current_image_url)
```

### Webcams within 30 km of a point

```python
from webcamgalore_client import get_webcams_near

# ~0.27 degrees ≈ 30 km
cams = get_webcams_near(lat=46.8, lon=8.2, radius_deg=0.27)  # Near Andermatt
```

### Download today's snapshot

```python
from webcamgalore_client import WebcamGaloreClient

with WebcamGaloreClient() as client:
    cams = client.get_webcams_by_bbox(47.1, 47.5, 11.2, 11.7)
    if cams:
        cam = cams[0]
        data = client.download_current_image(cam, size="current")
        with open(f"cam_{cam.cam_id}.jpg", "wb") as f:
            f.write(data)
```

### Get 30-day archive for a webcam

```python
with WebcamGaloreClient() as client:
    archive = client.get_archive_30d(2907, city="Altenmarkt a. d. Alz")
    for entry in archive:
        print(entry['date'], entry['url'])
```

### Enumerate all German webcams (memory-efficient)

```python
with WebcamGaloreClient(delay=1.0) as client:
    for cam_dict in client.iter_all_webcams_for_country("Germany"):
        print(cam_dict['cam_id'], cam_dict['city'])
```

### Get German states and their webcam counts

```python
with WebcamGaloreClient() as client:
    states = client.get_states("Germany")
    for s in states:
        print(s['name'], s['count'])
    # Bavaria: 377, Baden-Wuerttemberg: 156, etc.
```

### All Italian webcams via map API (fastest)

```python
with WebcamGaloreClient() as client:
    cams = client.get_webcams_by_country_bbox("Italy")
    print(f"Found {len(cams)} Italian webcams")
```

---

## Rate Limiting & Etiquette

- Default `delay=0.5` seconds between requests.
- For bulk scraping use `delay=1.0` or higher.
- The map XML API (`get_webcams_by_bbox`) is the most efficient — one request covers hundreds of cameras.
- Image downloads from `images.webcamgalore.com` are served via CDN (openresty) and support HTTP/2.

---

## Discovered Endpoints Summary

| Endpoint | Returns | Notes |
|---|---|---|
| `/include/webcammap.php` | XML with `<webcam>` elements | Primary data API; supports bbox + theme filter |
| `/30dj.php` | JSON-encoded HTML fragment | 30 daily archive images |
| `/365dj.php` | JSON-encoded HTML fragment | 365 daily archive images |
| `/archiv24.php` | Trigger | Registers 24h archive view |
| `/autocomplete.php` | JSON array of strings | All ~8,000 city+country combos |
| `/search.php` | HTML | Full search results page |
| `/popular.xml` | Atom feed | Top 20 most-viewed (last 24h) |
| `/new.xml` | Atom feed | ~20 most recently added |
| `/sitemap.xml` | Sitemap index | Links to sitemap0–2.xml |
| `/theme.html` | HTML | Theme listing (30 themes) |

---

## Notes on Image Freshness

- **Current images** (`webcam-{id:06d}.jpg`, `{id}-pub.jpg`) are updated at the webcam operator's refresh interval (varies: every minute to every hour).
- **Hourly archive** images are stored for ~5 days. Available hours vary by camera (not all cameras capture every hour).
- **Daily archive** images (`/oneyear/MM-DD/{id}.jpg`) are a single representative image per day, stored for approximately 365 days.
- The `?t=NNNNNN` timestamp query parameter on thumbnail URLs is a cache-buster. You can safely strip it or replace it with `int(time.time())`.
