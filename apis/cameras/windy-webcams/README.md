# Windy Webcams API Python Client

> A production-quality Python client for the Windy Webcams API — the world's largest webcam repository, with 50,000+ live cameras worldwide.

## What This Does

Windy maintains a public API at `api.windy.com/webcams` that provides access to webcam metadata, live images, timelapse player embeds, and geographic taxonomy. This client wraps the API's full v3 surface area with typed Python objects, automatic pagination, proper error handling, and both sync and async interfaces.

---

## Installation

**Prerequisites:** Python 3.8+

```bash
pip install requests
# Optional: async support
pip install httpx
```

No additional packages are required for the synchronous client.

---

## Authentication

1. Create a free account at [https://api.windy.com](https://api.windy.com)
2. Generate an API key at [https://api.windy.com/keys](https://api.windy.com/keys)
3. Pass the key to the client constructor or set the `WINDY_API_KEY` environment variable

> **Note:** It may take a few minutes after key creation before it is active worldwide.

```python
from windy_webcams_client import WindyWebcamsClient

client = WindyWebcamsClient(api_key="your-api-key")
```

---

## Quick Start

```python
from windy_webcams_client import WindyWebcamsClient, IncludeField, WebcamCategory, SortKey, SortDirection

client = WindyWebcamsClient(api_key="your-api-key")

# List the most popular webcams globally
result = client.list_webcams(
    limit=10,
    sort_key=SortKey.POPULARITY,
    sort_direction=SortDirection.DESC,
    include=[IncludeField.LOCATION, IncludeField.IMAGES, IncludeField.URLS],
)
print(f"Total webcams available: {result.total}")
for cam in result.webcams:
    print(f"[{cam.webcam_id}] {cam.title}")
```

---

## API Reference

### WindyWebcamsClient

```python
WindyWebcamsClient(
    api_key: str,
    timeout: int = 30,        # HTTP request timeout in seconds
    max_retries: int = 3,     # Automatic retries on 5xx errors
    session: Session = None,  # Optional pre-configured requests.Session
)
```

---

### list_webcams()

Retrieve a paginated list of webcams with extensive filtering.

```python
result = client.list_webcams(
    limit=10,                      # 0–50, default 10
    offset=0,                      # Pagination offset
    lang="en",                     # Language code
    bbox=(51.5, 0.1, 51.4, -0.1), # (north, east, south, west) bounding box
    nearby=(48.86, 2.35, 50),      # (lat, lon, radius_km) — max 250km
    categories=["beach", "coast"], # Up to 10 categories
    continents=["EU"],             # Up to 2 continent codes
    countries=["FR", "DE"],        # Up to 10 country codes
    regions=["ile-de-france"],     # Up to 10 region codes
    cities=["paris"],              # City codes
    webcam_ids=[1179853135],       # Specific webcam IDs, up to 50
    sort_key=SortKey.POPULARITY,   # "popularity" or "createdOn"
    sort_direction=SortDirection.DESC,
    category_operation="or",       # "and" or "or" for multiple categories
    include=[                      # Optional response sections
        IncludeField.CATEGORIES,
        IncludeField.IMAGES,
        IncludeField.LOCATION,
        IncludeField.PLAYER,
        IncludeField.URLS,
    ],
)

print(result.total)          # int: total matching webcams
print(result.has_more)       # bool: more pages available?
for cam in result.webcams:
    print(cam.webcam_id, cam.title, cam.status)
```

**Returns:** `WebcamListResult`

---

### get_webcam()

Retrieve a single webcam by its numeric ID.

```python
cam = client.get_webcam(
    webcam_id=1179853135,
    lang="en",
    include=[IncludeField.IMAGES, IncludeField.LOCATION, IncludeField.PLAYER, IncludeField.URLS],
)

print(cam.title)
print(cam.location.city, cam.location.country)
print(cam.player.live)          # Embed player URL
print(cam.images.current.url)   # Current snapshot image URL
print(cam.urls.detail)          # Windy.com detail page
```

**Returns:** `Webcam`

---

### get_webcam_with_full_details()

Convenience method that fetches all optional fields in one call.

```python
cam = client.get_webcam_with_full_details(webcam_id=1179853135)
```

---

### get_map_clusters()

Retrieve webcam clusters optimized for map display at a given zoom level.

```python
webcams = client.get_map_clusters(
    north_lat=51.6,
    south_lat=51.3,
    east_lon=0.2,
    west_lon=-0.2,
    zoom=12,
    include=[IncludeField.LOCATION],
)
```

The API enforces geographic span constraints per zoom level:

| Zoom | Max lat span | Max lon span |
|------|-------------|-------------|
| 4    | 22.5°       | 45°         |
| 5    | 11.25°      | 22.5°       |
| 6    | 5.625°      | 11.25°      |
| 7    | 2.813°      | 5.625°      |

**Returns:** `list[Webcam]`

---

### Taxonomy Endpoints

These return reference data for use as filter values.

```python
categories = client.get_categories(lang="en")
# [CategoryEntry(id='airport', name='Airport'), ...]

continents = client.get_continents()
# [GeoEntry(code='EU', name='Europe'), ...]

countries = client.get_countries()
# [GeoEntry(code='US', name='United States'), ...]

regions = client.get_regions()
cities = client.get_cities()
```

---

### export_all_webcams()

Download the full webcam inventory. **Professional tier only.**

```python
export = client.export_all_webcams()
print(export["updatedOn"])     # ISO 8601 timestamp
print(len(export["webcams"]))  # Total webcam count
```

Export response shape per webcam:

```json
{
  "webcamId": 1179853135,
  "title": "Sydney - Harbour Bridge and Opera House",
  "status": "active",
  "viewCount": 1234567,
  "preview": "https://...",
  "hasPanorama": false,
  "hasLivestream": true,
  "categories": ["city", "coast"],
  "location": {
    "latitude": -33.857,
    "longitude": 151.215,
    "regionCode": "nsw",
    "countryCode": "AU",
    "continentCode": "OC"
  }
}
```

---

### Convenience Search Methods

```python
# Find webcams near coordinates
result = client.search_by_location(
    latitude=48.8566,
    longitude=2.3522,
    radius_km=50,
    limit=10,
)

# Find popular webcams in a country
result = client.search_by_country("JP", limit=20)

# Find webcams by category
result = client.search_by_category(WebcamCategory.MOUNTAIN, limit=10)

# Find webcams within a bounding box
result = client.search_by_bbox(
    north=40.9,
    east=29.2,
    south=40.8,
    west=28.9,
    limit=10,
)
```

---

### Pagination Iterator

Automatically page through large result sets:

```python
count = 0
for cam in client.paginate(
    categories=[WebcamCategory.BEACH],
    continents=[ContinentCode.EUROPE],
    include=[IncludeField.LOCATION],
    max_results=500,   # Stop after 500 total (omit to get all)
    page_size=50,      # Requests per page (max 50)
):
    print(cam.title)
    count += 1
print(f"Total: {count}")
```

---

### Player Embed Helpers

These methods do **not** require an API key call — the URLs work directly in `<iframe>` tags.

```python
# Get the embed URL for a live stream
url = WindyWebcamsClient.build_player_url(1179853135, PlayerType.LIVE)
# => "https://webcams.windy.com/webcams/public/player?webcamId=1179853135&playerType=live"

# Generate a ready-to-use HTML iframe tag
html = WindyWebcamsClient.build_player_embed_html(
    webcam_id=1179853135,
    player_type=PlayerType.DAY,   # live | day | month | year | lifetime
    width=640,
    height=360,
)
# => '<iframe src="..." width="640" height="360" frameborder="0" allowfullscreen></iframe>'
```

---

## Response Data Models

### Webcam

| Field            | Type                  | Description                                 |
|------------------|-----------------------|---------------------------------------------|
| `webcam_id`      | `int`                 | Unique numeric identifier                   |
| `title`          | `str`                 | Display name                                |
| `status`         | `str`                 | active / inactive / unapproved / etc.       |
| `view_count`     | `int`                 | All-time view count                         |
| `last_updated_on`| `str`                 | ISO 8601 timestamp of last metadata update  |
| `cluster_size`   | `int`                 | Number of webcams this clusters represents  |
| `categories`     | `list[WebcamCategory_]` | Category tags (requires `include=categories`) |
| `images`         | `WebcamImages`        | Image URLs (requires `include=images`)      |
| `location`       | `WebcamLocation`      | Geographic data (requires `include=location`)|
| `player`         | `WebcamPlayer`        | Embed URLs (requires `include=player`)      |
| `urls`           | `WebcamUrls`          | External links (requires `include=urls`)    |

### WebcamLocation

| Field            | Type   | Description                        |
|------------------|--------|------------------------------------|
| `latitude`       | `float`| WGS84 latitude                     |
| `longitude`      | `float`| WGS84 longitude                    |
| `city`           | `str`  | Localized city name                |
| `region`         | `str`  | Localized region name              |
| `country`        | `str`  | Localized country name             |
| `continent`      | `str`  | Localized continent name           |
| `country_code`   | `str`  | ISO country code                   |
| `region_code`    | `str`  | Region code                        |
| `continent_code` | `str`  | AF / AN / AS / EU / NA / OC / SA   |

### WebcamImages

| Field      | Type              | Description                                 |
|------------|-------------------|---------------------------------------------|
| `current`  | `WebcamImage`     | Most recent snapshot image                  |
| `daylight` | `WebcamImage`     | Snapshot taken during daylight hours        |
| `sizes`    | `dict`            | Available image dimensions                  |

> **Image token expiry:** Free tier: **10 minutes**. Professional tier: **24 hours**.
> Re-request the webcam endpoint (`/webcams` or `/webcams/{id}`) to get fresh image URLs when tokens expire.

### WebcamPlayer

| Field      | Type  | Description                    |
|------------|-------|--------------------------------|
| `live`     | `str` | Current live stream embed URL  |
| `day`      | `str` | Last 24-hour timelapse URL     |
| `month`    | `str` | Last 30-day timelapse URL      |
| `year`     | `str` | Last 12-month timelapse URL    |
| `lifetime` | `str` | Full historical timelapse URL  |

---

## Enums Reference

### WebcamCategory
`airport`, `beach`, `building`, `city`, `coast`, `forest`, `indoor`, `lake`, `landscape`, `meteo`, `mountain`, `observatory`, `port`, `river`, `sportArea`, `square`, `traffic`, `village`

### ContinentCode
`AF` (Africa), `AN` (Antarctica), `AS` (Asia), `EU` (Europe), `NA` (North America), `OC` (Oceania), `SA` (South America)

### WebcamStatus
`active`, `inactive`, `unapproved`, `disabled`, `rejected`, `duplicate`, `merged`

### IncludeField
`categories`, `images`, `location`, `player`, `urls`

### PlayerType
`live`, `day`, `month`, `year`, `lifetime`

### SortKey
`popularity`, `createdOn`

### SortDirection
`asc`, `desc`

---

## Async Client

If `httpx` is installed, an async client is available:

```python
import asyncio
from windy_webcams_client import AsyncWindyWebcamsClient, IncludeField

async def main():
    async with AsyncWindyWebcamsClient(api_key="your-key") as client:
        result = await client.list_webcams(
            limit=5,
            include=[IncludeField.LOCATION],
        )
        for cam in result.webcams:
            print(cam.title)

asyncio.run(main())
```

---

## Rate-Limited Client

For batch jobs, use `RateLimitedWindyWebcamsClient` to automatically throttle requests:

```python
from windy_webcams_client import RateLimitedWindyWebcamsClient

client = RateLimitedWindyWebcamsClient(
    api_key="your-key",
    min_delay_sec=1.0,   # Wait at least 1 second between requests
)
```

---

## Error Handling

```python
from windy_webcams_client import (
    WindyWebcamsError,
    WindyAuthError,
    WindyRateLimitError,
    WindyNotFoundError,
    WindyAPIError,
)

try:
    cam = client.get_webcam(99999999)
except WindyAuthError:
    print("API key is invalid or missing")
except WindyNotFoundError:
    print("Webcam not found")
except WindyRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after} seconds")
except WindyAPIError as e:
    print(f"API error {e.status_code}")
except WindyWebcamsError as e:
    print(f"Client error: {e}")
```

| Exception              | HTTP Status | When raised                             |
|------------------------|-------------|------------------------------------------|
| `WindyAuthError`       | 401, 403    | Invalid/missing API key                  |
| `WindyNotFoundError`   | 404         | Resource does not exist                  |
| `WindyRateLimitError`  | 429         | Rate limit exceeded                      |
| `WindyAPIError`        | 5xx, other  | Unexpected server error                  |
| `WindyWebcamsError`    | —           | Network error, timeout, base class       |

---

## Context Manager

```python
with WindyWebcamsClient(api_key="key") as client:
    result = client.list_webcams(limit=10)
# Session is automatically closed
```

---

## API Tiers

| Feature                      | Free              | Professional (9,990€/yr) |
|------------------------------|-------------------|--------------------------|
| Webcam listing               | Yes               | Yes                      |
| Max pagination offset        | 1,000             | 10,000                   |
| Image URL validity           | 15 minutes        | 24 hours                 |
| Bulk export endpoint         | No                | Yes                      |
| Ads in player embeds         | Yes               | No                       |
| Full-resolution images       | No                | Yes                      |

---

## Discovered Endpoints

### Official v3 API — `https://api.windy.com/webcams/api/v3`

| Method | Path                         | Description                          | Auth Required |
|--------|------------------------------|--------------------------------------|---------------|
| GET    | `/webcams`                   | List/filter webcams                  | Yes           |
| GET    | `/webcams/{webcamId}`        | Get single webcam                    | Yes           |
| GET    | `/map/clusters`              | Map-optimized cluster view           | Yes           |
| GET    | `/categories`                | List all webcam categories           | Yes           |
| GET    | `/continents`                | List continent codes                 | Yes           |
| GET    | `/countries`                 | List country codes                   | Yes           |
| GET    | `/regions`                   | List region codes                    | Yes           |
| GET    | `/cities`                    | List city codes                      | Yes           |

Special endpoint (Professional only):

| Method | Path                                                    | Description           |
|--------|---------------------------------------------------------|-----------------------|
| GET    | `https://api.windy.com/webcams/export/all-webcams.json` | Full inventory export |

Player embed URLs (no API key required):

```
https://webcams.windy.com/webcams/public/player?webcamId={ID}&playerType={live|day|month|year|lifetime}
```

---

## Undocumented Internal Endpoints

These endpoints are used by the Windy.com web application itself. They are **not officially documented** and require **no API key**. They were discovered via static analysis of Windy's JavaScript bundle (`/v/49.1.1.ind.eb7f/index.js`).

### `WindyInternalClient`

```python
from windy_webcams_client import WindyInternalClient

client = WindyInternalClient()
```

#### `get_nearby_webcams(lat, lon, limit=10, lang="en")` — node.windy.com

Returns the closest webcams to a geographic point. This is what Windy's map panel calls when you click a location.

**Richer than v3:** 5 image sizes (full, normal, preview, thumbnail, icon), subcountry in location.

```
GET https://node.windy.com/webcams/v1.0/list
    ?nearby={lat},{lon}&limit={n}&lang=en
```

```python
cams = client.get_nearby_webcams(48.8566, 2.3522, limit=10)
for cam in cams:
    print(cam.id, cam.title)
    print(cam.images.current.preview)    # ~400×224 image URL
    print(cam.images.current.full)       # up to 1920×1080
    print(cam.location.subcountry)       # e.g. "Ile-de-France"
```

#### `get_webcam_detail(webcam_id, lang="en")` — node.windy.com

Returns extended detail for a single webcam including orientation, contacts, and provider page URL.

```
GET https://node.windy.com/webcams/v1.0/detail/{webcamId}?lang=en
```

```python
detail = client.get_webcam_detail(1515017464)
print(detail.page_url)        # Original provider page
print(detail.view_count)      # All-time view count
print(detail.orientation)     # {"direction": null, "position": "unknown", "view": "unknown"}
print(detail.contacts)        # {"owner": "unknown", "caretaker": "unknown"}
print(detail.timelapse_type)  # "all"
```

#### `get_webcam_archive(webcam_id, hourly=False)` — node.windy.com

Returns historical image frames for the last 24 hours (default) or last 30 days at 1 frame/hour.

```
GET https://node.windy.com/webcams/v2.0/archive/{webcamId}            # last 24h, ~50-min intervals
GET https://node.windy.com/webcams/v2.0/archive/hourly/{webcamId}     # last 30 days, 1/hour
```

```python
# 24-hour archive (full-resolution frames)
frames = client.get_webcam_archive(1515017464)
for frame in frames:
    print(frame.timestamp_readable, frame.url)
# URL format: https://imgproxy.windy.com/_/full/plain/day/{id}/original/{ts}.jpg

# 30-day hourly archive (thumbnail frames)
hourly = client.get_webcam_archive(1515017464, hourly=True)
# URL format: https://imgproxy.windy.com/_/thumbnail/plain/month/{id}/original/{ts}.jpg
```

#### `search_views(query, lat=None, lon=None, lang="en")` — admin.windy.com

Searches for places and POIs by name. Used in the Windy webcam page's location search bar.
Returns Google Places-style `viewId` values.

```
GET https://admin.windy.com/webcams/admin/v1.0/views
    ?textQuery={q}&lang=en[&lat={lat}&lon={lon}]
```

```python
views = client.search_views("Eiffel Tower", lat=48.8566, lon=2.3522)
for v in views:
    print(v.view_id)     # "ChIJLU7jZClu5kcR4PcOOO6p3I0"
    print(v.name)        # "Eiffel Tower"
    print(v.place_type)  # "Point Of Interest, Tourist Attraction"
    print(v.distance)    # distance in metres from provided lat/lon
```

**Notes:**
- `lat`/`lon` are optional but recommended — they bias results by distance.
- Provide both or neither (raises `ValueError` if only one is given).
- The `viewId` values are Google Places-format identifiers.

### Image URL Patterns (imgproxy.windy.com)

The internal API image URLs follow a consistent pattern via `imgproxy.windy.com`:

```
https://imgproxy.windy.com/_{size}/plain/{timeframe}/{webcamId}/original[/{timestamp}].jpg
```

| Segment      | Values                                                   |
|--------------|----------------------------------------------------------|
| `{size}`     | `full`, `normal`, `preview`, `thumbnail`, `icon`        |
| `{timeframe}`| `current`, `daylight`, `day`, `month`                   |
| `{webcamId}` | Numeric webcam ID                                        |
| `{timestamp}`| Unix seconds (for archive frames only)                  |

Examples:
```
https://imgproxy.windy.com/_/full/plain/current/1515017464/original.jpg       # current full
https://imgproxy.windy.com/_/preview/plain/daylight/1515017464/original.jpg   # daylight preview
https://imgproxy.windy.com/_/full/plain/day/1515017464/original/1774562399.jpg  # archive frame
```

---

## Supported Languages

The `lang` parameter accepts these codes:
`ar`, `bg`, `bn`, `ca`, `cs`, `da`, `de`, `el`, `en`, `es`, `et`, `fa`, `fi`, `fr`, `he`, `hi`, `hr`, `hu`, `id`, `is`, `it`, `ja`, `ko`, `lt`, `nb`, `nl`, `pl`, `pt`, `ro`, `ru`, `sk`, `sl`, `sq`, `sr`, `sv`, `ta`, `th`, `tr`, `uk`, `vi`, `zh`, `zh-TW`

---

## Example: Building a Weather Dashboard

```python
import os
from windy_webcams_client import (
    WindyWebcamsClient,
    WebcamCategory,
    ContinentCode,
    IncludeField,
    SortKey,
    SortDirection,
    PlayerType,
)

client = WindyWebcamsClient(api_key=os.environ["WINDY_API_KEY"])

# 1. Get the top 10 mountain webcams in Europe with full details
mountain_cams = client.list_webcams(
    categories=[WebcamCategory.MOUNTAIN],
    continents=[ContinentCode.EUROPE],
    sort_key=SortKey.POPULARITY,
    sort_direction=SortDirection.DESC,
    limit=10,
    include=[
        IncludeField.LOCATION,
        IncludeField.IMAGES,
        IncludeField.PLAYER,
        IncludeField.URLS,
    ],
)

for cam in mountain_cams.webcams:
    print(f"\n{cam.title}")
    if cam.location:
        print(f"  Location: {cam.location.city}, {cam.location.country}")
        print(f"  Coords: {cam.location.latitude}, {cam.location.longitude}")
    if cam.images and cam.images.current.url:
        print(f"  Preview: {cam.images.current.url}")
    if cam.player:
        embed = cam.player.get_embed_html(PlayerType.LIVE, width=800, height=450)
        print(f"  Embed: {embed}")

# 2. Find all webcams near the Eiffel Tower
nearby = client.search_by_location(48.8584, 2.2945, radius_km=10)
print(f"\nWebcams near Eiffel Tower: {nearby.total}")

# 3. Iterate all beach webcams (auto-pagination)
print("\nAll beach webcams:")
for cam in client.paginate(
    categories=[WebcamCategory.BEACH],
    include=[IncludeField.LOCATION],
    max_results=100,
):
    print(f"  {cam.webcam_id}: {cam.title}")
```

---

## Running the Built-In Test

```bash
export WINDY_API_KEY=your-key
python windy_webcams_client.py
```

This runs a live smoke test against all major endpoints.

---

## Key API Behaviors

- **Pagination:** Use `limit` and `offset`. Free tier max offset is 1,000; professional is 10,000.
- **Image token expiry:** Image URLs expire and return HTTP 401. Re-fetch the webcam to get fresh URLs (**10 minutes** on free tier, **24 hours** on professional). Note: some earlier docs said 15 minutes; the current API documentation explicitly states 10 minutes.
- **`include` parameter:** Response is minimal by default. Request `location`, `images`, `player`, `urls`, and `categories` explicitly as needed to reduce bandwidth.
- **Cluster size:** The `clusterSize` field on a webcam indicates how many cameras are grouped at that location on the map.
- **Status filtering:** The API returns webcams of all statuses unless filtered. Check `cam.is_active` or `cam.status == "active"` if you only want live cameras.
- **Transport:** All endpoints use HTTPS with HTTP/2. The `via: 1.1 google` response header indicates Google Cloud CDN is in use.
- **Authentication header:** `x-windy-api-key: <YOUR_KEY>` (not a Bearer token).
- **Internal endpoints:** The `node.windy.com` and `admin.windy.com` endpoints (used by the Windy web app) require no API key and return richer data, but are undocumented and may change without notice.
- **Image proxy:** All webcam images (both official and internal API) are served through `imgproxy.windy.com` using a consistent URL pattern: `/_/{size}/plain/{timeframe}/{webcamId}/original[/{timestamp}].jpg`.
