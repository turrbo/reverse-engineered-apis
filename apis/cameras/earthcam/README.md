# EarthCam Internal API — Reverse Engineering Reference

**Reverse-engineered:** 2026-03-27
**Target:** https://www.earthcam.com
**Authentication required:** None
**Rate limiting:** Not observed (Cloudflare-protected)

---

## Overview

EarthCam is the leading network of live streaming webcams with hundreds of premium cameras worldwide including Times Square, Niagara Falls, Dublin Temple Bar, Eiffel Tower, and more. This document details their internal API discovered through static JavaScript analysis and HTML page inspection.

All endpoints return JSON with a consistent envelope: `{"status": "200", "msg": "...", "data": {...}}`.

---

## Discovery Methodology

1. Fetched HTML source of `https://www.earthcam.com/usa/newyork/timessquare/?cam=tsrobo1` — found embedded `var json_base = {...}` containing full camera metadata including stream URLs
2. Downloaded and analyzed key JavaScript files:
   - `https://static.earthcam.com/js/earthcam/functions.ecntemplate.js` — camera page JS
   - `https://static.earthcam.com/js/earthcam/ecnplayerhtml5/js/ecnplayerhtml5-package.js` — player JS (~473KB)
   - `https://static.earthcam.com/js/videoLoaderFunctions.min.js` — loadMore logic
3. Analyzed `https://www.earthcam.com/network/` JavaScript for network browsing API
4. Analyzed `https://www.earthcam.com/mapsearch/` JavaScript for map/bounds API
5. Tested `https://www.earthcam.com/api/ectv/config` — returns complete API endpoint directory

---

## Key IDs Explained

Each camera has multiple IDs serving different purposes:

| Field | Description | Use Case |
|-------|-------------|----------|
| `cam_name` | Human-readable camera name (e.g. `tsrobo1`) | URL parameter (`?cam=tsrobo1`) |
| `group_id` | Group/location identifier (e.g. `timessquare`) | `ecn_cameras` API parameter |
| `id` | 32-char hex UUID | `camera.php` API lookup |
| `inet` | Internal network ID | Internal use |
| `dnet` | Archive/network ID | **Required** for `get_archives.php` |

---

## Stream URL Structure

Live stream URLs follow this pattern:
```
https://videos-3.earthcam.com/fecnetwork/<stream_name>.flv/playlist.m3u8?t=<token>&td=<YYYYMMDDHHMM>
```

- **Domain:** `videos-3.earthcam.com` (CDN)
- **Path:** `/fecnetwork/<name>.flv/playlist.m3u8`
- **Token:** `?t=<base64-signed-token>` — short-lived (~1 hour)
- **Timestamp:** `&td=YYYYMMDDHHMM` — token issue time

The token is pre-signed server-side and embedded in API responses. To refresh a stream URL, re-call `get_camera_group()` or `get_camera_by_id()`.

**Without token (Android path):**
```
/fecnetwork/hdtimes10.flv/playlist.m3u8
```
The token-free path may work for some cameras or may return 403.

---

## Archive URL Structure

Hourly recorded clips are served from `video2archives.earthcam.com`:
```
https://video2archives.earthcam.com/archives/_definst_/MP4:network/<stream_name>/<YYYY>/<MM>/<DD>/<HH>00.mp4/playlist.m3u8
```

Example for Times Square, 2pm on March 26, 2026:
```
https://video2archives.earthcam.com/archives/_definst_/MP4:network/hdtimes10/2026/03/26/1400.mp4/playlist.m3u8
```

The archive thumbnail base path is:
```
https://images.earthcam.com/network/<stream_name>/<YYYY>/<MM>/<DD>/<HH>.jpg
```

---

## Complete API Endpoint Reference

### ECTV / App Configuration

#### `GET /api/ectv/config`
Returns the global app configuration. The canonical source of all API endpoint templates.

**Response structure:**
```json
{
  "data": {
    "api": {
      "domain": "https://www.earthcam.com",
      "playlist": { "default": "/api/ectv/player/playlist.php?r=playlist&a=fetch&nc=%1%" }
    },
    "network": {
      "categories": {
        "cams": "/api/dotcom/categories_cams.php?r=categories_cams&a=fetch",
        "list": "/api/dotcom/categories.php?r=categories&a=fetch"
      },
      "camera": "/api/dotcom/camera.php?r=camera&a=fetch&id=%1%",
      "camera_archives": "/api/dotcom/get_archives.php?netid=%1%",
      "newcams": "/api/dotcom/newcams.php?r=newcams&a=fetch&filter=%1%",
      "timelapse": "/api/dotcom/timelapse.php?r=timelapse&a=fetch",
      "timelapse_best": "/api/dotcom/timelapse.php?r=timelapse&a=fetch&best=1"
    },
    "weather": "/api/weather/weather.php?icons=simple&metar=%1%"
  }
}
```

---

### Player / Camera Page Endpoints

#### `GET /api/player/ecn_cameras?r=page&a=fetch&g=<group_id>`
**Primary endpoint for live stream URLs.** Returns full camera metadata for all cameras in a group.

| Parameter | Value | Required |
|-----------|-------|----------|
| `r` | `page` | Yes |
| `a` | `fetch` | Yes |
| `g` | Group ID (e.g. `timessquare`) | Yes |

**Notable camera fields returned:**
- `stream` — Full HLS m3u8 URL with signed token
- `html5_streamingdomain` — CDN domain
- `html5_streampath` — HLS path + token
- `livestreamingpath` — Raw path without token (e.g. `/fecnetwork/hdtimes10.flv`)
- `android_livepath` — Token-free HLS path
- `archivedomain_html5` — Archive server domain
- `archivepath_html5` — 24hr timelapse archive path
- `backup_clip` — VOD fallback URL
- `dnet` — Archive network ID (use for `get_archives.php`)
- `metar` — METAR weather station code
- `hofid` — Hall of Fame ID

**Known group_ids:**
- US: `timessquare`, `niagarafalls`, `miami`, `chicago`, `losangeles`, `nashville`, `newengland`
- International: `dublin`, `london`, `paris`, `amsterdam`, `rome`, `sydney`, `hongkong`

#### `GET /api/player/ecn_page?r=page&a=fetch&x=<group_id>`
Returns page-level SEO/display metadata for a camera group.

#### `GET /api/player/map?s=<state>&c=<country>`
Returns the map icon path for a state/country.

---

### ECTV Playlist

#### `GET /api/ectv/player/playlist.php?r=playlist&a=fetch[&nc=<category>]`
**Also works without .php:** `/api/ectv/player/playlist?r=playlist&a=fetch`

Returns 4 trending + 8 featured cameras. The `nc` parameter appears to have minimal filtering effect. Playlist items include full stream URLs with tokens.

**Playlist item fields:** `title`, `city`, `country`, `stream`, `thumbnail`, `thumbnail_large`, `thumbnail_hd`, `latitude`, `longitude`, `timezone`, `metar`, `views`, `likes`, `cam_state`, `backup_clip`, `url`, `item_id`, `group_id`, `routing_name`, `description`

---

### dotcom / Network Endpoints

#### `GET /api/dotcom/camera.php?r=camera&a=fetch&id=<camera_id>`
Get stream URL + metadata for a camera by its UUID (`id` field).

Returns `data.playlist_items` array with one item (same structure as playlist items).

#### `GET /api/dotcom/categories.php?r=categories&a=fetch`
List of all camera categories with enabled/disabled status.

**Active categories (status=1):**
`america250`, `animals`, `beaches`, `cities`, `election_day`, `featured`, `landmarks`, `lakes-rivers-oceans`, `myearthcam`, `nature`, `nye`, `nye_ts`, `smalltown`, `sports`, `trending`, `youtube`

#### `GET /api/dotcom/categories_cams.php?r=categories_cams&a=fetch`
Returns all ~300 cameras in the network with summary info (no stream URLs).

Fields: `id`, `title`, `city`, `state`, `country`, `description`, `cam_state`, `thumbnail`, `thumbnail_large`, `url`, `category`, `latitude`, `longitude`

#### `GET /api/dotcom/get_archives.php?netid=<dnet>`
Returns hourly archive clips for a camera.

**IMPORTANT:** Use the camera's `dnet` field as `netid`, NOT the `id` or `inet` field.

Returns `{startdate, enddate, curdate, clips: [{time, clip, clip_html5, thumbnail, thumbnail_large, duration, date_stamp}]}`

Archive clips are available for the past ~24 hours.

#### `GET /api/dotcom/timelapse.php?r=timelapse&a=fetch[&best=1][&timelapse_type=<type>][&related_id=<id>]`
Returns daily timelapse videos (sunrise/sunset). Returns 100 items.

#### `GET /api/dotcom/newcams.php?r=newcams&a=fetch[&filter=<type>]`
Returns recently added cameras.

#### `GET /api/dotcom/youtube.php?r=youtube&a=fetch`
Returns EarthCam YouTube stream listings.

#### `GET /api/dotcom/timelapse.php?r=timelapse&a=fetch&best=1`
Returns the best-of timelapse selection.

---

### Network Location Search

#### `GET /api/dotcom/network_search.php?r=ecn&a=fetch&country=<country>[&state=<state>]`
Browse cameras by geographic location. Powers the `/network/` page.

| `country` value | Result |
|----------------|--------|
| `"United States"` | All US cameras (use `&state=NY` to filter) |
| `"Ireland"` | All Irish cameras |
| `"France"` | All French cameras |
| `"featured"` | Returns playlist data (same as `/api/ectv/player/playlist.php`) |

Response: `{data: {cam_count, cam_items: [{id, title, city, state, country, url, thumbnail, thumbnail_large, cam_state, latitude, longitude}]}}`

---

### Search / Autocomplete

#### `GET /api/dotcom-search/html/autocomplete_updated?term=<query>`
Returns search autocomplete suggestions.

Response: `{"results": ["EarthCam: Times Square 4K", "Times Square · NYC", ...]}`

---

### Map Search Endpoints

#### `GET /api/mapsearch/get_locations_network.php?r=ecn&a=fetch`
Returns all EarthCam network cameras with geo coordinates for map display (~274 cameras).

Response: `[{places: [{name, url, posn: [lat, lng], place_type, id, icon, thumbnail}]}]`

#### `GET /api/mapsearch/get_locations?nwx=<nw_lat>&nwy=<nw_lng>&nex=<ne_lat>&ney=<ne_lng>&sex=<se_lat>&sey=<se_lng>&swx=<sw_lat>&swy=<sw_lng>&zoom=<zoom>`
Returns all cameras (including third-party) within a bounding box. Returns 1000+ cameras for large areas.

**USA bounds example:**
```
/api/mapsearch/get_locations?nwx=49&nwy=-125&nex=49&ney=-65&sex=25&sey=-65&swx=25&swy=-125&zoom=5
```

Response: Same structure as `get_locations_network` — `[{places: [{name, icon, thumbnail, posn, place_type, location, city, state, country, url}]}]`

---

### Weather

#### `GET /api/weather/weather.php?icons=<style>&metar=<code>`
Returns detailed current weather for a METAR station.

| Parameter | Values |
|-----------|--------|
| `icons` | `simple`, `cc7`, `cc8_bg`, `cc8_nobg` |
| `metar` | METAR station code (e.g. `KJFK`, `KIAG`, `EIDW`) |

**Response includes:** Temperature (F/C), Wind (speed/direction/gusts), Pressure, Humidity, Conditions, Cloud layers, Visibility, Sunrise/Sunset, Moon phase, Weather icons at multiple CDN paths.

---

### Static Content URLs

#### Camera Thumbnails
```
https://static.earthcam.com/camshots/<size>/<hash>.jpg
```
Sizes: `128x72`, `256x144`, `512x288`, `1816x1024`

The hash is from the camera's thumbnail field (NOT the camera `id`). Example:
```
https://static.earthcam.com/camshots/256x144/fc0bd5c43dfbd1a702db4b38abe484ff.jpg
```

#### Map Tiles
```
https://static.earthcam.com/api/map/get_tiles?s={s}&z={z}&x={x}&y={y}&20230208a
```

#### Weather Icons
```
https://resource6.earthcam.net/packages/earth-cam/weather/icons/simple/<filename>.png
https://resource6.earthcam.net/packages/earth-cam/weather/icons/cc7/<filename>.png
https://resource6.earthcam.net/packages/earth-cam/weather/icons/cc8_bg/<filename>.png
https://resource6.earthcam.net/packages/earth-cam/weather/icons/cc8_nobg/<filename>.png
```

---

## Example Camera Group IDs

These were confirmed working during reverse engineering:

| Group ID | Camera Name | Location |
|----------|-------------|----------|
| `timessquare` | `tsrobo1`, `tsstreet`, `tsrobo3`, `tsnorth_hd`, `tstwo_hd2`, `gts1`, `gduffy`, `gts2_broadway`, `tspano` | New York City, NY |
| `niagarafalls` | `niagarafalls_str` | Niagara Falls, Canada |
| `dublin` | `templebar` | Dublin, Ireland |
| `london` | `newlondon` | London, UK |
| `paris` | `eiffeltower_hd` | Paris, France |
| `miami` | `brickellkey` | Miami, FL |
| `chicago` | `fieldmuseum` | Chicago, IL |

---

## Usage Examples

```python
from earthcam_client import EarthCamClient

client = EarthCamClient()

# Get live HLS stream for Times Square
stream_url = client.get_live_stream("timessquare", "tsrobo1")
print(stream_url)
# → https://videos-3.earthcam.com/fecnetwork/hdtimes10.flv/playlist.m3u8?t=...

# Search for cameras
results = client.find_cameras("beach")
# → ["EarthCam: Bucuti Beach Cams - Eagle Beach", ...]

# Get trending cameras
trending = client.get_trending_cameras()
for cam in trending:
    print(cam['title'], '-', cam['stream'][:60])

# Browse cameras by location
ny_cams = client.get_cameras_for_state("NY")  # 41 cameras
ireland_cams = client.get_cameras_for_country("Ireland")  # 2 cameras

# Get weather at camera location
weather = client.get_weather("KJFK")
print(weather['data']['Temperature']['Fahrenheit'], "°F")

# Get hourly archive clips (last ~24 hours)
cam = client.get_camera_info("timessquare", "tsrobo1")
archives = client.get_archives(cam["dnet"])  # must use dnet, not id
for clip in archives["clips"][:3]:
    print(clip["date_stamp"], "→", clip["clip_html5"])

# Get cameras within geographic bounds (USA)
usa_cams = client.get_cameras_in_bounds(
    nw_lat=49, nw_lng=-125,
    ne_lat=49, ne_lng=-65,
    se_lat=25, se_lng=-65,
    sw_lat=25, sw_lng=-125,
    zoom=5
)
print(f"Found {len(usa_cams[0]['places'])} cameras in USA bounds")

# Get daily timelapse videos
timelapses = client.get_timelapse()
for tl in timelapses['data']['playlist_items'][:5]:
    print(tl['title-short'], tl['timelapse-date'])
```

---

## Notes and Limitations

1. **Stream tokens expire** — The `?t=...&td=...` token in stream URLs appears valid for ~1 hour. Re-fetch the camera data to get a fresh URL.

2. **Token-free paths may 403** — The `android_livepath` field provides the token-free HLS path but it may require a valid token to play.

3. **Cloudflare protection** — The site is behind Cloudflare. No rate limiting was observed during testing, but aggressive crawling may trigger challenges.

4. **`dnet` for archives** — The `get_archives.php` endpoint requires the `dnet` field, not `id`. Passing the wrong ID returns `-1`.

5. **Offline cameras** — `cam_state: 0` indicates offline. Stream URLs may still exist but return empty or static images.

6. **Search endpoint quirks** — `network_search.php` requires `r=ecn&a=fetch` (not `r=search`). Other `r` values return 400/501 errors.

7. **loadMore.php** — A `/loadMore.php?category=<id>&start=<n>&max=<n>` endpoint exists for paginating category listings on the homepage, but it requires browser-side context and returns empty responses from curl.

---

## Related Endpoints Discovered But Not Fully Explored

- `/api/ectv/user/likes.php?r=likes&a=fetch` — User likes (likely requires auth)
- `/api/ectv/user/likes.php?r=likes&a=save&uid=%1%&id=%2%` — Save likes (requires auth)
- `/api/ectv/register_device.php?id=%ID%&rid=%RID%` — Device registration (for ECTV app)
- `/api/ectv/faq.php` — FAQ content
- `/api/ectv/quickguide.php` — Quick guide content
- `/api/ectv/notice.php` — App notices
- `/api/dotcom/tos.php` — Terms of service
- `/api/dotcom/privacypolicy.php` — Privacy policy
- `/api/dotcom/myec.php?r=myec&a=fetch` — MyEarthCam cameras (may require auth)
- `/api/panorama/getpanorama?i=<group_id>` — Panoramic camera endpoint (returns HTML page)
- `/cams/common/ratecam.php?id=<id>` — Camera rating endpoint
- `//www.earthcam.com/channel.php` — Channel communication endpoint
- `/search/ft-search.php?_sbox=1&s1=1&term=<query>` — Full-text search (returns HTML)
- `/search/adv_search.php` — Advanced search (returns HTML)
- `/mapsearch_google/map_bounds.php?display=simple&map_width=<w>&map_height=<h>&id=<id>` — Google Maps display

---

## Infrastructure Notes

- **CDN:** Cloudflare
- **Streaming Server:** `videos-3.earthcam.com` (HLS)
- **Archive Server:** `video2archives.earthcam.com`, `archives.earthcam.com`
- **Image CDN:** `static.earthcam.com`
- **Resource CDN:** `resource6.earthcam.net`
- **Player:** Custom HTML5 player (`ecnplayerhtml5`) built on Video.js
- **Map:** Leaflet.js with custom tile layer at `static.earthcam.com/api/map/get_tiles`
- **Frontend:** jQuery + Bootstrap 5.3
