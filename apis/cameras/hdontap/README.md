# HDOnTap API - Reverse Engineering Notes & Client

**HDOnTap** (https://www.hdontap.com) hosts 200+ live HD webcams covering
wildlife (eagle nests, falcons, owls, wolves, bison), beaches, scenic views,
airports, aquariums, and resort destinations worldwide.

---

## Quick Start

```python
from hdontap_client import HDOnTapClient

client = HDOnTapClient()

# List all eagle cams
for stream in client.get_eagle_cams():
    print(f"{stream.short_uuid}: {stream.title} - {stream.viewer_count} viewers")

# Get a signed HLS URL (playable with ffplay, VLC, mpv, etc.)
play = client.get_play_url("204942")   # Hanover Eagles
print(play.stream_url)
# → https://live.hdontap.com/hls/hosb4/ngrp:...playlist.m3u8?t=TOKEN&e=EXPIRY

# Play with ffplay
# ffplay "https://live.hdontap.com/hls/hosb4/ngrp:...playlist.m3u8?t=TOKEN&e=EXPIRY"

# Multi-cam streams have multiple angles
for cam in play.preview_urls:
    print(cam["url"])   # Each angle has its own signed URL

# Search
results = client.search("underwater")
```

---

## API Architecture

| Component | URL | Auth |
|-----------|-----|------|
| Main site | https://hdontap.com | None |
| REST API | https://hdontap.com/api/ | None (GET) |
| HLS CDN | https://live.hdontap.com/hls/ | Signed token (auto-obtained) |
| Snapshots | https://portal.hdontap.com/snapshot/ | None |
| Storage CDN | https://storage.hdontap.com | None |
| Timelapse | https://timelapse.hdontap.com/embed/ | None |

---

## Discovered API Endpoints

### GET /api/streams/
List all streams. Returns paginated JSON.

**Filters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tag` | string | Tag slug (see Tags section) |
| `category` | string | Category slug |
| `search` | string | Full-text search |
| `is_live` | bool | Only live streams |
| `ordering` | string | Sort field (prefix `-` for desc) |
| `page` | int | Page number |
| `page_size` | int | Results per page (max 250) |

**Example response item:**
```json
{
  "id": 299,
  "short_uuid": "162979",
  "title": "Namibia Africa Waterhole Live Cam",
  "card_title": "Namibia Africa Waterhole",
  "slug": "namibia-africa-waterhole-live-cam",
  "category": null,
  "tags": [{"id": 92, "name": "Animals", "slug": "animals", "primary": true, ...}],
  "location_display": "Hardap Region",
  "viewer_count": 1203,
  "thumbnail_url": "https://storage.hdontap.com/...",
  "is_live": true,
  "is_new": false,
  "is_featured": null,
  "curated": true
}
```

---

### GET /api/streams/{short_uuid}/
Full stream detail. Returns additional fields:

```json
{
  "description_text": "<html>...</html>",
  "contextual_description": "Watch the Hanover Eagle Nest...",
  "player_type": "hls",
  "stream_url": "https://live.hdontap.com/hls/hosb4/...",
  "fallback_url": null,
  "is_favorited": false,
  "created_at": "2021-12-03T10:11:45.356000Z",
  "updated_at": "2026-03-13T00:00:40.683130Z"
}
```

**Note:** The `stream_url` here is **unsigned** and returns HTTP 403.
Use `/play/` for a valid signed URL.

---

### GET /api/streams/{short_uuid}/play/
**Primary endpoint for getting playable HLS URLs.**

Returns a fresh signed URL valid for **approximately 12 hours**:

```json
{
  "stream_url": "https://live.hdontap.com/hls/hosb4/ngrp:hdontap_hanover-eagles_pov-mux.stream_all/playlist.m3u8?t=TOKEN&e=1774674030",
  "player_type": "hls",
  "settings": {
    "streamSrc": "...",
    "autoStart": true,
    "previews": [
      {
        "img": "https://portal.hdontap.com/snapshot/...",
        "url": "https://live.hdontap.com/hls/...",
        "abs": true
      }
    ],
    "weatherWidget": {
      "label": "Hanover, PA",
      "currently": {
        "summary": "Overcast",
        "temperature": 44.08,
        "windSpeed": 13.69,
        "humidity": 0.8
      },
      "latitude": 39.810984,
      "longitude": -76.887359,
      "timezone": "America/New_York"
    },
    "discovery": {...},
    "branding": {...},
    "overlay": {...}
  }
}
```

The signed URL contains:
- `t=` — HMAC token (base64url encoded, Wowza SecureToken v2)
- `e=` — Unix expiry timestamp (~12 hours from request time)

**Confirmed token TTL:** Tokens observed expiring ~12 hours after issuance
(e.g., issued at 17:00 UTC, expires at 05:00 UTC next day).

The player auto-refreshes via `/api/streams/{id}/play/` when the stream stalls.
This is done client-side in the browser's `selfHealing` plugin.

---

### GET /api/tags/
List all 276 tags (paginated).

**Primary tags** (shown in UI navigation):
- `4kUltraHD` — 4K Ultra HD streams
- `action` — Action/sports
- `animals` — Animals (general)
- `beaches` — Beach cameras
- `birds` — Bird cameras
- `eagles` — Eagle nest cameras
- `resorts` — Resort/hotel cameras
- `scenic` — Scenic views
- `surf` — Surf cameras

---

### GET /api/categories/
List all 10 categories:
`action`, `animals`, `beaches`, `birds`, `eagles`, `other`, `owls`, `raptors`, `resorts`, `scenic`

---

### POST /api/follow-stream/
Follow/unfollow a stream (requires authentication + CSRF token).

---

## HLS Stream Format

### Wowza Media Servers

Streams are delivered via Wowza Streaming Engine. Observed server IDs:
- `hosb1` — Primary server (Virginia?)
- `hosb3` — Secondary
- `hosb4` — 4K streams
- `hosb6lo` — Low-latency server
- `hosb6na` — North America
- `hosbdvr3` — DVR-enabled
- `hosbdvr6` — DVR-enabled 4K

### URL Structure

```
https://live.hdontap.com/hls/{server}/{stream_name}.stream/playlist.m3u8?t={token}&e={expiry}
```

Multi-cam / merged streams use `ngrp:` prefix:
```
https://live.hdontap.com/hls/hosb4/ngrp:hdontap_hanover-eagles_pov-mux.stream_all/playlist.m3u8?...
```

### Quality Variants

The master playlist contains multiple quality levels:
```
#EXT-X-STREAM-INF:BANDWIDTH=7980144,CODECS="avc1.4d4033,mp4a.40.2",RESOLUTION=3840x2160
chunklist_b7980144.m3u8?...
#EXT-X-STREAM-INF:BANDWIDTH=3428000,CODECS="avc1.640028,mp4a.40.2",RESOLUTION=1920x1080
chunklist_b3128000.m3u8?...
#EXT-X-STREAM-INF:BANDWIDTH=2163000,CODECS="avc1.64001f,mp4a.40.2",RESOLUTION=1280x720
chunklist_b1978000.m3u8?...
#EXT-X-STREAM-INF:BANDWIDTH=843000,CODECS="avc1.42c016,mp4a.40.2",RESOLUTION=640x360
chunklist_b778000.m3u8?...
```

---

## Stream Types

### HLS Streams (most streams)
- Delivered via Wowza CDN at live.hdontap.com
- Requires signed token from `/api/streams/{id}/play/`
- Token valid ~12 hours, then re-request
- Master playlist served from live.hdontap.com; chunk delivery from edge servers (e.g. edge01.virginia.nginx.hdontap.com)

### YouTube-embedded Streams
- Some cameras embed YouTube Live streams
- `/play/` returns `player_type: "youtube"` and a YouTube watch URL
- Examples: Princess Juliana Airport (093143)

### DVR/Time-shift Streams
- Streams on `hosbdvr6` server support DVR rewind
- URL contains `?DVR` before token params: `playlist.m3u8?DVR&t=...&e=...`
- Example: Malibu Point Surf Cam (190972) uses hosbdvr6 server

### Multi-cam Streams
- Multiple camera angles bundled together
- `settings.previews[]` contains each angle with its own signed URL
- Example: Hanover Eagles (204942) has POV + Upper PTZ cameras

---

## Snapshots & Thumbnails

### Live Snapshot
```
GET https://portal.hdontap.com/snapshot/{portal_embed_id}
```
Returns a fresh JPEG thumbnail (no auth, refreshed ~every 30s by CDN).

The `portal_embed_id` is found in the stream page HTML as the `portalEmbedId`
attribute in Unpoly `up-data` JSON. Format: `hdontap_{stream_name}-HDOT-{type}`

### Static Thumbnails (CDN)
```
https://storage.hdontap.com/wowza_stream_thumbnails/snapshot_{server}_{stream_name}.jpg
```
Available from the `thumbnail_url` field in the API response.

---

## Timelapse

HDOnTap records daily timelapses for most streams.

```
GET https://timelapse.hdontap.com/embed/{timelapse_id}
GET https://timelapse.hdontap.com/embed/{timelapse_id}/{YYYY-MM-DD}
```

The `timelapse_id` is an internal integer (different from `short_uuid`).
It is embedded in the stream's `/tl-player/` page HTML as:
```html
<iframe src="https://timelapse.hdontap.com/embed/1025" ...>
```

Timelapse recordings are GIF/video files stored at:
```
https://timelapse.hdontap.com/internal/storage/{date}/{...}/movies/{id}-{res}-{bitrate}-{fps}-{start}-{end}-archive:60-protect:false-remove:false.gif
```

---

## URL Patterns

| Resource | URL Pattern |
|----------|-------------|
| Stream page | `https://hdontap.com/stream/{short_uuid}/{slug}/` |
| Embed page | `https://hdontap.com/stream/{short_uuid}/{slug}/embed/` |
| Snapshot gallery | `https://hdontap.com/stream/{short_uuid}/{slug}/snapshot-gallery/` |
| Timelapse player | `https://hdontap.com/stream/{short_uuid}/{slug}/tl-player/` |
| Clip | `https://hdontap.com/stream/{short_uuid}/{slug}/clip/{clip_id}/` |
| Tag browse | `https://hdontap.com/explore/tag/{tag_slug}/` |
| Search | `https://hdontap.com/search/?q={query}` |
| Sitemap | `https://hdontap.com/sitemap.xml` |

---

## Client CLI Usage

```bash
# Run demo (top 10 streams, eagle cams, HLS URLs, tags)
python3 hdontap_client.py demo

# List all streams by viewer count
python3 hdontap_client.py list

# List streams by tag
python3 hdontap_client.py list eagles
python3 hdontap_client.py list beaches

# Get signed HLS URL + quality variants
python3 hdontap_client.py play 204942   # Hanover Eagles
python3 hdontap_client.py play 018408   # Scripps Pier Underwater

# Search
python3 hdontap_client.py search falcon
python3 hdontap_client.py search bear

# Stream detail
python3 hdontap_client.py detail 162979

# List all tags
python3 hdontap_client.py tags
python3 hdontap_client.py tags --primary   # Primary tags only
```

---

## Notable Streams

### Wildlife
| ID | Name |
|----|------|
| 204942 | Hanover Eagles Nest Live Cam (PA) |
| 114839 | Cardinal Land Conservancy Eagles (Cincinnati, OH) |
| 190216 | NE Florida Eagles Live Webcam |
| 795150 | PA Farm Country Bald Eagle Live Cams |
| 397338 | Richmond Virginia Peregrine Falcon |
| 241333 | PA Peregrine Falcon Cam |
| 018408 | Scripps Pier Underwater (San Diego, CA) |
| 162646 | Birch Aquarium Kelp Forest |
| 162979 | Namibia Africa Waterhole |
| 102875 | American Prairie Montana Bison |
| 359514 | Tennessee Elk Live Webcam |
| 696039 | Red Wolves at Wolf Conservation Center |
| 710132 | Kodiak Alaska Brown Bears |

### Beaches
| ID | Name |
|----|------|
| 158254 | El Porto Beach Roving Cam (Manhattan Beach, CA) |
| 126730 | Manhattan Beach Pier Ultra HD |
| 529804 | Cherry Grove Beach (North Myrtle Beach, SC) |
| 158132 | Turks and Caicos Seven Stars Resort |
| 541510 | Baha Mar - Nassau Bahamas |

### Airports
| ID | Name |
|----|------|
| 093143 | Princess Juliana Intl. Airport (St. Maarten) |
| 709750 | Las Vegas Airport Plane Tracking |
| 494309 | Truckee Tahoe Airport |
| 237231 | Gillespie Field Airport (El Cajon, CA) |

### Scenic / International
| ID | Name |
|----|------|
| 110906 | South Korea Seoul Lofi Live Cam |
| 216480 | St. Quens Bay Jersey Island |
| 697118 | Hawaii Kilauea Volcano USGS |
| 283808 | UK White Stork Nest (Knepp Estate, Sussex) |
| 989297 | Crystal Bay Koh Samui Thailand |

---

## Token Signing

HLS URLs use a time-limited HMAC token scheme (Wowza SecureToken v2):
- `t=` parameter: base64url-encoded HMAC signature
- `e=` parameter: Unix timestamp for expiry (~12h from issue time)

The signing key is server-side; clients must call `/api/streams/{id}/play/`
to get fresh tokens.

The Wowza SecureToken v2 format signs:
- stream path
- client IP (sometimes, per-stream configuration)
- expiry time
- shared secret (not exposed publicly)

The token is unique per-request (even for the same stream). The player's
`selfHealing` JavaScript plugin automatically fetches a fresh token when
the stream stalls, using the same `/api/streams/{id}/play/` endpoint.

**Chunklist URLs** also carry the token:
```
https://live.hdontap.com/hls/{server}/{stream}/chunklist.m3u8
    ?e={expiry}&eh={edge_hostname}&t={token}
```
The `eh=` parameter pins the request to a specific CDN edge node.

---

## Notes on Rate Limiting

- No authentication required for all listed GET endpoints
- No explicit rate limits observed, but be reasonable
- CSRF token required for POST endpoints (follow-stream, snapshot upload)
- The portal.hdontap.com API requires a Bearer token (not public)

---

## Dependencies

The client uses only Python standard library modules:
- `urllib.request` / `urllib.error` — HTTP requests
- `json` — JSON parsing
- `re` — Regex for HLS parsing
- `dataclasses` — Data models
- `time` — Token expiry checking
- `logging` — Optional debug logging

No pip packages required.
